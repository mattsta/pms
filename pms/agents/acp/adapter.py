"""ACP loop adapter."""

from __future__ import annotations

import asyncio
import shutil
import time
from pathlib import Path
from typing import Any

from pms import __version__
from pms.agents.loop import LoopAdapter, LoopResponse
from pms.config.logging import logger

from .client import ACPClient, ACPClientError
from .handlers import ACPHandlers
from .session import ACPSessionState

ACP_PROTOCOL_VERSION = 1


class ACPLoopAdapter(LoopAdapter):
    """Loop adapter that speaks ACP JSON-RPC to an agent."""

    def __init__(self, name, config) -> None:  # type: ignore[no-untyped-def]
        self._agent_command = config.agent_command or config.command
        self._agent_args = list(config.agent_args or config.args)
        self._env = dict(config.env or {})
        self._timeout = config.timeout_seconds
        self._session_cwd = config.session_cwd or str(Path.cwd())
        self._mcp_servers = list(config.mcp_servers or [])
        self._stream_limit = config.stream_limit
        self._permission_mode = config.permission_mode
        self._permission_allowlist = list(config.permission_allowlist or [])
        self._allowed_roots = list(config.allowed_roots or [])

        self._client: ACPClient | None = None
        self._session_id: str | None = None
        self._initialized = False
        self._state = ACPSessionState()
        self._handlers = ACPHandlers(
            permission_mode=self._permission_mode,
            permission_allowlist=self._permission_allowlist,
            allowed_roots=self._allowed_roots,
            base_dir=self._session_cwd,
            on_permission_log=self._log_permission,
        )

        super().__init__(name, config)

    def _check_available(self) -> bool:
        if not self._agent_command:
            return False
        return shutil.which(self._agent_command) is not None

    async def run(self, prompt: str) -> LoopResponse:
        if not self.available:
            return LoopResponse(
                success=False,
                output="",
                error="ACP adapter unavailable",
            )

        start = time.monotonic()
        try:
            await self._ensure_initialized()
            response = await self._execute_prompt(prompt)
            response.duration_seconds = time.monotonic() - start
            return response
        except ACPClientError as exc:
            duration = time.monotonic() - start
            return LoopResponse(
                success=False,
                output=self._state.output,
                error=f"ACP error: {exc}",
                duration_seconds=duration,
            )
        except Exception as exc:
            duration = time.monotonic() - start
            return LoopResponse(
                success=False,
                output=self._state.output,
                error=str(exc),
                duration_seconds=duration,
            )

    async def close(self) -> None:
        self._handlers.shutdown()
        if self._client:
            await self._client.stop()
        self._client = None
        self._session_id = None
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        if self._initialized:
            if self._client and self._client.is_running and self._session_id:
                return
            await self.close()
        if not self._agent_command:
            raise ACPClientError("Missing ACP agent command")

        effective_args = list(self._agent_args)
        if (
            Path(self._agent_command).name == "gemini"
            and "--experimental-acp" not in effective_args
        ):
            effective_args.append("--experimental-acp")

        self._client = ACPClient(
            command=self._agent_command,
            args=effective_args,
            timeout=self._timeout,
            stream_limit=self._stream_limit,
            env=self._env,
        )

        await self._client.start()
        self._client.on_notification(self._handle_notification)
        self._client.on_request(self._handle_request)

        try:
            init_future = self._client.send_request(
                "initialize",
                {
                    "protocolVersion": ACP_PROTOCOL_VERSION,
                    "clientCapabilities": {
                        "fs": {"readTextFile": True, "writeTextFile": True},
                        "terminal": True,
                    },
                    "clientInfo": {
                        "name": "pms",
                        "title": "PMS",
                        "version": __version__,
                    },
                },
            )
            init_response = await asyncio.wait_for(init_future, timeout=self._timeout)
            if "protocolVersion" not in init_response:
                raise ACPClientError("ACP initialize response missing protocolVersion")

            session_future = self._client.send_request(
                "session/new",
                {
                    "cwd": self._session_cwd,
                    "mcpServers": self._mcp_servers,
                },
            )
            session_response = await asyncio.wait_for(
                session_future, timeout=self._timeout
            )
            self._session_id = session_response.get("sessionId")
            if not self._session_id:
                raise ACPClientError("ACP session/new response missing sessionId")

            self._initialized = True
        except Exception:
            await self.close()
            raise

    async def _execute_prompt(self, prompt: str) -> LoopResponse:
        if not self._client or not self._session_id:
            raise ACPClientError("ACP client not initialized")

        self._state.reset()
        prompt_blocks = [{"type": "text", "text": prompt}]

        future = self._client.send_request(
            "session/prompt",
            {
                "sessionId": self._session_id,
                "prompt": prompt_blocks,
            },
        )
        response = await asyncio.wait_for(future, timeout=self._timeout)

        stop_reason = (
            response.get("stopReason") or response.get("stop_reason") or "unknown"
        )
        error_message = None
        success = True

        if stop_reason == "error":
            error_obj = response.get("error") or {}
            error_message = error_obj.get("message", "ACP agent error")
            success = False

        return LoopResponse(
            success=success,
            output=self._state.output,
            error=error_message,
            metadata={
                "adapter": "acp",
                "agent": self._agent_command,
                "session_id": self._session_id,
                "stop_reason": stop_reason,
                "tool_calls": self._state.tool_calls,
            },
        )

    def _handle_notification(self, method: str, params: dict[str, Any]) -> None:
        if method != "session/update":
            return

        update_raw = params.get("update")
        update: dict[str, Any] = update_raw if isinstance(update_raw, dict) else params
        kind = update.get("sessionUpdate") or update.get("kind")
        if not kind:
            return

        content = update.get("content")
        if isinstance(content, dict):
            content_text = content.get("text", "")
        else:
            content_text = str(content) if content is not None else ""

        tool_name = update.get("toolName")
        tool_call_id = update.get("toolCallId")
        arguments = update.get("arguments")
        status = update.get("status")
        result = update.get("result")
        error = update.get("error")

        match kind:
            case "agent_message_chunk":
                self._state.add_message(content_text)
            case "agent_thought_chunk":
                self._state.add_thought(content_text)
            case "tool_call":
                self._state.register_tool_call(tool_name, tool_call_id, arguments)
            case "tool_call_update":
                self._state.update_tool_call(tool_call_id, status, result, error)
            case _:
                return

    def _handle_request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        match method:
            case "session/request_permission":
                return self._handlers.handle_permission_request(params)
            case "fs/read_text_file":
                return self._handlers.handle_read_text_file(params)
            case "fs/write_text_file":
                return self._handlers.handle_write_text_file(params)
            case "terminal/create":
                return self._handlers.handle_terminal_create(params)
            case "terminal/output":
                return self._handlers.handle_terminal_output(params)
            case "terminal/wait_for_exit":
                return self._handlers.handle_terminal_wait_for_exit(params)
            case "terminal/kill":
                return self._handlers.handle_terminal_kill(params)
            case "terminal/release":
                return self._handlers.handle_terminal_release(params)
            case _:
                logger.warning("ACP request method not handled: %s", method)
                return {
                    "error": {"code": -32601, "message": f"Unknown method: {method}"}
                }

    def _log_permission(self, message: str) -> None:
        logger.info(message)
