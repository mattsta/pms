"""ACP subprocess client for JSON-RPC messaging."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import os
import signal
from collections.abc import Callable
from typing import Any

from pms.config.logging import logger

from .protocol import ACPMessageType, ACPProtocol

DEFAULT_ACP_STREAM_LIMIT = 8 * 1024 * 1024


async def _terminate_process_group(
    process: asyncio.subprocess.Process,
    *,
    grace_seconds: float,
) -> None:
    if process.returncode is not None:
        return

    if os.name == "nt" or not hasattr(os, "killpg"):
        process.terminate()
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(process.wait(), timeout=grace_seconds)
        if process.returncode is None:
            process.kill()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(process.wait(), timeout=grace_seconds)
        return

    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGTERM)

    try:
        await asyncio.wait_for(process.wait(), timeout=grace_seconds)
        return
    except TimeoutError:
        pass

    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGKILL)

    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(process.wait(), timeout=grace_seconds)


class ACPClientError(Exception):
    """ACP client error."""


class ACPClient:
    """Manage an ACP agent subprocess and JSON-RPC routing."""

    def __init__(
        self,
        command: str,
        args: list[str] | None = None,
        timeout: int = 300,
        stream_limit: int | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        self.command = command
        self.args = args or []
        self.timeout = timeout
        env_limit = os.environ.get("PMS_ACP_STREAM_LIMIT")
        if stream_limit is not None:
            self.stream_limit = stream_limit
        elif env_limit:
            try:
                self.stream_limit = int(env_limit)
            except ValueError:
                logger.warning(
                    "Invalid PMS_ACP_STREAM_LIMIT=%r; using default %d",
                    env_limit,
                    DEFAULT_ACP_STREAM_LIMIT,
                )
                self.stream_limit = DEFAULT_ACP_STREAM_LIMIT
        else:
            self.stream_limit = DEFAULT_ACP_STREAM_LIMIT

        self._protocol = ACPProtocol()
        self._process: asyncio.subprocess.Process | None = None
        self._read_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._write_lock = asyncio.Lock()
        self._env = env or {}

        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._notification_handlers: list[Callable[[str, dict[str, Any]], None]] = []
        self._request_handlers: list[Callable[[str, dict[str, Any]], Any]] = []

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    async def start(self) -> None:
        if self.is_running:
            raise RuntimeError("ACP client already running")

        cmd = [self.command, *self.args]
        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=self.stream_limit,
            env={**os.environ, **self._env} if self._env else None,
            start_new_session=(os.name != "nt"),
        )

        self._read_task = asyncio.create_task(self._read_stdout())
        self._stderr_task = asyncio.create_task(self._read_stderr())

    async def stop(self) -> None:
        process = self._process
        read_task = self._read_task
        stderr_task = self._stderr_task

        for task in (read_task, stderr_task):
            if task and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.TimeoutError, asyncio.CancelledError):
                    await asyncio.wait_for(task, timeout=0.5)

        if process and process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                await _terminate_process_group(process, grace_seconds=2.0)

        self._process = None
        self._read_task = None
        self._stderr_task = None

        for future in self._pending.values():
            if not future.done():
                future.cancel()
        self._pending.clear()

    async def _read_stdout(self) -> None:
        if not self._process or not self._process.stdout:
            return

        try:
            while self.is_running:
                line = await self._process.stdout.readline()
                if not line:
                    break
                payload = line.decode(errors="replace").strip()
                if payload:
                    await self._handle_message(payload)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("ACP stdout loop failed: %s", exc, exc_info=True)
        finally:
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(ACPClientError("ACP subprocess exited"))
            self._pending.clear()

    async def _read_stderr(self) -> None:
        if not self._process or not self._process.stderr:
            return

        try:
            while self.is_running:
                line = await self._process.stderr.readline()
                if not line:
                    break
                message = line.decode(errors="replace").rstrip()
                if message:
                    logger.warning("ACP stderr: %s", message)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("ACP stderr loop failed: %s", exc, exc_info=True)

    async def _handle_message(self, raw: str) -> None:
        parsed = self._protocol.parse_message(raw)
        msg_type = parsed.get("type")

        match msg_type:
            case ACPMessageType.RESPONSE:
                request_id = parsed.get("id")
                if not isinstance(request_id, int):
                    logger.warning("ACP response missing integer id: %r", request_id)
                    return
                future = self._pending.pop(request_id, None)
                if future and not future.done():
                    future.set_result(parsed.get("result"))
            case ACPMessageType.ERROR:
                request_id = parsed.get("id")
                if not isinstance(request_id, int):
                    logger.warning("ACP error missing integer id: %r", request_id)
                    return
                future = self._pending.pop(request_id, None)
                if future and not future.done():
                    error = parsed.get("error") or {}
                    message = error.get("message", "ACP error")
                    future.set_exception(ACPClientError(message))
            case ACPMessageType.NOTIFICATION:
                method = parsed.get("method", "")
                params = parsed.get("params", {})
                for handler in self._notification_handlers:
                    try:
                        handler(method, params)
                    except Exception as exc:
                        logger.error(
                            "ACP notification handler failed: %s", exc, exc_info=True
                        )
            case ACPMessageType.REQUEST:
                await self._handle_request(parsed)
            case ACPMessageType.PARSE_ERROR | ACPMessageType.INVALID:
                logger.warning("ACP message parse error: %s", parsed.get("error"))
            case _:
                logger.warning("ACP message missing type: %s", raw)

    async def _handle_request(self, parsed: dict[str, Any]) -> None:
        request_id = parsed.get("id")
        if not isinstance(request_id, int):
            logger.warning("ACP request missing integer id: %r", request_id)
            return
        method = parsed.get("method", "")
        params = parsed.get("params", {})

        result = None
        for handler in self._request_handlers:
            try:
                result = handler(method, params)
                if inspect.isawaitable(result):
                    result = await result
                break
            except Exception as exc:
                response = self._protocol.create_error_response(
                    request_id, -32603, str(exc)
                )
                await self._write_message(response)
                return

        if result is None:
            result = {"error": {"code": -32601, "message": f"Unknown method: {method}"}}

        if isinstance(result, dict) and "error" in result:
            error_info = result.get("error") or {}
            code = error_info.get("code", -32603)
            message = error_info.get("message", "ACP handler error")
            response = self._protocol.create_error_response(
                request_id, code, message, error_info.get("data")
            )
        else:
            response = self._protocol.create_response(request_id, result)

        await self._write_message(response)

    async def _write_message(self, payload: str) -> None:
        if not self.is_running or not self._process or not self._process.stdin:
            raise RuntimeError("ACP client not running")

        async with self._write_lock:
            self._process.stdin.write((payload + "\n").encode())
            await self._process.stdin.drain()

    async def _send(self, request_id: int, payload: str) -> None:
        try:
            await self._write_message(payload)
        except Exception as exc:
            future = self._pending.pop(request_id, None)
            if future and not future.done():
                future.set_exception(ACPClientError(f"Failed to send request: {exc}"))

    def send_request(self, method: str, params: dict[str, Any]) -> asyncio.Future[Any]:
        request_id, payload = self._protocol.create_request(method, params)
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()
        self._pending[request_id] = future
        asyncio.create_task(self._send(request_id, payload))
        return future

    async def send_notification(self, method: str, params: dict[str, Any]) -> None:
        payload = self._protocol.create_notification(method, params)
        await self._write_message(payload)

    def on_notification(self, handler: Callable[[str, dict[str, Any]], None]) -> None:
        self._notification_handlers.append(handler)

    def on_request(self, handler: Callable[[str, dict[str, Any]], Any]) -> None:
        self._request_handlers.append(handler)
