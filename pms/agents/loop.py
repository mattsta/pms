"""Ralph-style agent loop configuration and adapters."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shutil
import signal
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pms.config.logging import logger


@dataclass
class AdapterConfig:
    """Configuration for a loop adapter."""

    name: str
    type: str = "command"  # claude | command | acp | codex
    enabled: bool = True
    timeout_seconds: int = 300
    max_retries: int = 3
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    prompt_mode: str = "stdin"  # stdin | arg | file
    agent_command: str | None = None
    agent_args: list[str] = field(default_factory=list)
    codex_model: str | None = None
    codex_reasoning_effort: str | None = None
    permission_mode: str = "interactive"
    permission_allowlist: list[str] = field(default_factory=list)
    allowed_roots: list[str] = field(default_factory=list)
    session_cwd: str | None = None
    mcp_servers: list[dict[str, Any]] = field(default_factory=list)
    stream_limit: int | None = None


@dataclass
class LoopConfig:
    """Configuration for an agent loop."""

    agent: str = "auto"
    agent_priority: list[str] = field(default_factory=list)
    prompt_file: Path | None = None
    prompt_text: str | None = None
    max_iterations: int = 100
    max_runtime_seconds: int = 14_400
    max_cost_usd: float = 0.0
    retry_delay_seconds: float = 2.0
    completion_promise: str | None = None
    completion_marker: str | None = None
    max_prompt_bytes: int = 10_485_760
    dry_run: bool = False
    stop_when_goals_complete: bool = False
    goal_ids: list[str] = field(default_factory=list)
    include_archived_goals: bool = False
    allow_no_goals: bool = False
    adapters: dict[str, AdapterConfig] = field(default_factory=dict)

    def prompt_source(self) -> str:
        if self.prompt_text:
            return "text"
        if self.prompt_file:
            return str(self.prompt_file)
        return "unknown"

    def load_prompt(self) -> str:
        if self.prompt_text is not None:
            return self.prompt_text
        if not self.prompt_file:
            raise ValueError("Prompt text or prompt file required")
        if not self.prompt_file.exists():
            raise FileNotFoundError(f"Prompt file not found: {self.prompt_file}")
        raw = self.prompt_file.read_text()
        if len(raw.encode("utf-8")) > self.max_prompt_bytes:
            raise ValueError("Prompt file exceeds max_prompt_bytes")
        return raw

    def completion_tag(self) -> str | None:
        if not self.completion_promise:
            return None
        return f"<promise>{self.completion_promise}</promise>"


@dataclass
class LoopResponse:
    """Adapter execution result."""

    success: bool
    output: str
    error: str | None = None
    tokens_used: int | None = None
    cost_usd: float | None = None
    duration_seconds: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class LoopAdapter:
    """Base class for loop adapters."""

    def __init__(self, name: str, config: AdapterConfig) -> None:
        self.name = name
        self.config = config
        self.available = self._check_available()

    def _check_available(self) -> bool:
        return True

    async def run(self, prompt: str) -> LoopResponse:
        raise NotImplementedError


class ClaudeLoopAdapter(LoopAdapter):
    """Adapter that executes the CoordinatorAgent."""

    def __init__(self, name: str, config: AdapterConfig, agent) -> None:  # type: ignore[no-untyped-def]
        self._agent = agent
        super().__init__(name, config)

    async def run(self, prompt: str) -> LoopResponse:
        start = time.monotonic()
        result = await self._agent.run(prompt)
        duration = time.monotonic() - start
        return LoopResponse(
            success=result.success,
            output=result.message,
            error="; ".join(result.errors) if result.errors else None,
            duration_seconds=duration,
            metadata={"tool_calls": result.tool_calls},
        )


class CommandLoopAdapter(LoopAdapter):
    """Adapter that runs an external command."""

    def _check_available(self) -> bool:
        if not self.config.command:
            return False
        return shutil.which(self.config.command) is not None

    async def _terminate_subprocess_group(
        self, proc: asyncio.subprocess.Process, *, grace_seconds: float = 1.0
    ) -> None:
        if proc.returncode is not None:
            return

        if os.name == "nt" or not hasattr(os, "killpg"):
            proc.kill()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(proc.wait(), timeout=grace_seconds)
            return

        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGTERM)

        try:
            await asyncio.wait_for(proc.wait(), timeout=grace_seconds)
            return
        except TimeoutError:
            pass

        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)

        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(proc.wait(), timeout=grace_seconds)

    async def run(self, prompt: str) -> LoopResponse:
        if not self.config.command:
            return LoopResponse(success=False, output="", error="Missing command")

        env = os.environ.copy()
        env.update(self.config.env)

        prompt_file = None
        args = list(self.config.args)
        prompt_mode = self.config.prompt_mode.lower()

        if prompt_mode == "file":
            with tempfile.NamedTemporaryFile("w+", delete=False) as temp_prompt_file:
                temp_prompt_file.write(prompt)
                temp_prompt_file.flush()
                prompt_file = Path(temp_prompt_file.name)
            env["PMS_PROMPT_FILE"] = str(prompt_file)
            args = [arg.format(prompt_file=str(prompt_file)) for arg in args]
            if "{prompt_file}" not in " ".join(self.config.args):
                args.append(str(prompt_file))
        elif prompt_mode == "arg":
            args = [arg.format(prompt=prompt) for arg in args]
            if "{prompt}" not in " ".join(self.config.args):
                args.append(prompt)
        else:
            env["PMS_PROMPT"] = prompt

        command = [self.config.command, *args]
        start = time.monotonic()
        proc = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE if prompt_mode == "stdin" else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            start_new_session=True,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(prompt.encode() if prompt_mode == "stdin" else None),
                timeout=self.config.timeout_seconds,
            )
        except TimeoutError:
            await self._terminate_subprocess_group(proc)
            return LoopResponse(
                success=False,
                output="",
                error=f"Command timed out after {self.config.timeout_seconds}s",
            )
        finally:
            if prompt_file:
                try:
                    prompt_file.unlink(missing_ok=True)
                except OSError:
                    logger.warning("Failed to remove prompt file %s", prompt_file)

        duration = time.monotonic() - start
        output_text = stdout.decode(errors="replace").strip()
        error_text = stderr.decode(errors="replace").strip()
        return LoopResponse(
            success=proc.returncode == 0,
            output=output_text,
            error=error_text or None,
            duration_seconds=duration,
            metadata={"exit_code": proc.returncode, "stderr": error_text},
        )


def load_loop_config(path: Path) -> LoopConfig:
    """Load a loop config from YAML/JSON/TOML."""
    payload = _load_config_payload(path)
    max_iterations = _coalesce(payload, "max_iterations", default=100)
    max_runtime = _coalesce(
        payload, "max_runtime", "max_runtime_seconds", default=14_400
    )
    max_cost = _coalesce(payload, "max_cost", "max_cost_usd", default=0.0)
    retry_delay = _coalesce(payload, "retry_delay", "retry_delay_seconds", default=2.0)
    max_prompt_bytes = _coalesce(
        payload, "max_prompt_size", "max_prompt_bytes", default=10_485_760
    )
    stop_when_goals_complete = bool(payload.get("stop_when_goals_complete", False))
    goal_ids = list(payload.get("goal_ids") or [])
    include_archived_goals = bool(payload.get("include_archived_goals", False))
    allow_no_goals = bool(payload.get("allow_no_goals", False))

    adapters = {}
    for name, data in (payload.get("adapters") or {}).items():
        tool_permissions = data.get("tool_permissions") or {}
        agent_command = (
            data.get("agent_command")
            or tool_permissions.get("agent_command")
            or data.get("command")
        )
        agent_args = data.get("agent_args")
        if agent_args is None:
            agent_args = tool_permissions.get("agent_args")
        if agent_args is None:
            agent_args = data.get("args", [])

        permission_mode = data.get("permission_mode") or tool_permissions.get(
            "permission_mode"
        )
        permission_allowlist = data.get("permission_allowlist")
        if permission_allowlist is None:
            permission_allowlist = tool_permissions.get("permission_allowlist")

        adapters[name] = AdapterConfig(
            name=name,
            type=data.get("type", name),
            enabled=data.get("enabled", True),
            timeout_seconds=data.get("timeout", data.get("timeout_seconds", 300)),
            max_retries=data.get("max_retries", 3),
            command=data.get("command"),
            args=list(data.get("args", [])),
            env=dict(data.get("env", {})),
            prompt_mode=data.get("prompt_mode", "stdin"),
            agent_command=agent_command,
            agent_args=list(agent_args or []),
            codex_model=data.get("codex_model"),
            codex_reasoning_effort=data.get("codex_reasoning_effort"),
            permission_mode=permission_mode or "interactive",
            permission_allowlist=list(permission_allowlist or []),
            allowed_roots=list(
                data.get("allowed_roots") or tool_permissions.get("allowed_roots") or []
            ),
            session_cwd=data.get("session_cwd") or data.get("cwd"),
            mcp_servers=list(data.get("mcp_servers", [])),
            stream_limit=data.get("stream_limit"),
        )

    prompt_file = payload.get("prompt_file")
    prompt_path = Path(prompt_file) if prompt_file else None

    return LoopConfig(
        agent=payload.get("agent", "auto"),
        agent_priority=list(payload.get("agent_priority", [])),
        prompt_file=prompt_path,
        max_iterations=int(max_iterations),
        max_runtime_seconds=int(max_runtime),
        max_cost_usd=float(max_cost or 0.0),
        retry_delay_seconds=float(retry_delay),
        completion_promise=payload.get("completion_promise"),
        completion_marker=payload.get("completion_marker"),
        max_prompt_bytes=int(max_prompt_bytes),
        dry_run=bool(payload.get("dry_run", False)),
        stop_when_goals_complete=stop_when_goals_complete,
        goal_ids=goal_ids,
        include_archived_goals=include_archived_goals,
        allow_no_goals=allow_no_goals,
        adapters=adapters,
    )


def _load_config_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")

    suffix = path.suffix.lower()
    raw = path.read_text()

    if suffix == ".json":
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("Loop config root must be a JSON object")
        return {str(key): value for key, value in payload.items()}
    if suffix == ".toml":
        import tomllib

        payload = tomllib.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("Loop config root must be a TOML table/object")
        return {str(key): value for key, value in payload.items()}
    if suffix in {".yml", ".yaml"}:
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError("Install pyyaml to load YAML configs") from exc
        payload = yaml.safe_load(raw) or {}
        if not isinstance(payload, dict):
            raise ValueError("Loop config root must be a YAML mapping/object")
        return {str(key): value for key, value in payload.items()}

    raise ValueError(f"Unsupported config format: {path.suffix}")


def _coalesce(payload: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    return default
