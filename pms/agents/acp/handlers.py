"""ACP permission, filesystem, and terminal handlers."""

from __future__ import annotations

import contextlib
import fnmatch
import os
import re
import signal
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pms.config.logging import logger

ERROR_INVALID_PARAMS = -32602
ERROR_PERMISSION_DENIED = -32001
ERROR_NOT_FOUND = -32002
ERROR_ACCESS = -32003
ERROR_TERMINAL = -32004
ERROR_INTERNAL = -32603


@dataclass
class PermissionRequest:
    """Parsed permission request."""

    operation: str
    path: str | None = None
    command: list[str] | None = None
    arguments: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_params(cls, params: dict[str, Any]) -> PermissionRequest:
        return cls(
            operation=params.get("operation", ""),
            path=params.get("path"),
            command=params.get("command"),
            arguments=params,
        )


@dataclass
class PermissionDecision:
    """Result of permission evaluation."""

    approved: bool
    reason: str | None = None
    mode: str = "unknown"


@dataclass
class TerminalHandle:
    """Track a terminal subprocess."""

    terminal_id: str
    process: subprocess.Popen[str]
    output_buffer: str = ""

    @property
    def is_running(self) -> bool:
        return self.process.poll() is None

    def read_output(self) -> str:
        import select

        new_output = ""
        for stream in (self.process.stdout, self.process.stderr):
            if stream is None:
                continue
            try:
                while True:
                    ready, _, _ = select.select([stream], [], [], 0)
                    if not ready:
                        break
                    chunk = stream.read(4096)
                    if not chunk:
                        break
                    new_output += chunk
            except OSError:
                break
        if new_output:
            self.output_buffer += new_output
        return new_output

    def kill(self) -> None:
        if not self.is_running:
            return
        if os.name == "nt" or not hasattr(os, "killpg"):
            self.process.terminate()
            try:
                self.process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
            return

        with contextlib.suppress(ProcessLookupError):
            os.killpg(self.process.pid, signal.SIGTERM)

        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            if not self.is_running:
                return
            time.sleep(0.05)

        with contextlib.suppress(ProcessLookupError):
            os.killpg(self.process.pid, signal.SIGKILL)
        with contextlib.suppress(subprocess.TimeoutExpired):
            self.process.wait(timeout=1.0)

    def wait(self, timeout: float | None = None) -> int:
        return self.process.wait(timeout=timeout)


class ACPHandlers:
    """Handle ACP permission and tool requests."""

    VALID_PERMISSION_MODES = ("auto_approve", "deny_all", "allowlist", "interactive")

    def __init__(
        self,
        permission_mode: str = "interactive",
        permission_allowlist: list[str] | None = None,
        allowed_roots: list[str] | None = None,
        base_dir: str | None = None,
        on_permission_log: Callable[[str], None] | None = None,
    ) -> None:
        if permission_mode not in self.VALID_PERMISSION_MODES:
            raise ValueError(
                f"Invalid permission_mode: {permission_mode}. "
                f"Expected one of {', '.join(self.VALID_PERMISSION_MODES)}"
            )

        self.permission_mode = permission_mode
        self.allowlist = permission_allowlist or []
        self.on_permission_log = on_permission_log

        self.base_dir = Path(base_dir or Path.cwd()).resolve()
        self.allowed_roots = [Path(root).resolve() for root in (allowed_roots or [])]
        if not self.allowed_roots:
            self.allowed_roots = [self.base_dir]

        self._history: list[tuple[PermissionRequest, PermissionDecision]] = []
        self._approved: set[str] = set()
        self._terminals: dict[str, TerminalHandle] = {}

    def _terminal_snapshot(
        self,
        terminal_id: str,
        terminal: TerminalHandle,
        *,
        auto_release: bool = False,
    ) -> dict[str, Any]:
        """Return terminal state and optionally release completed handles."""

        terminal.read_output()
        exit_code = terminal.process.poll()
        done = exit_code is not None

        payload: dict[str, Any] = {
            "output": terminal.output_buffer,
            "done": done,
        }
        if done:
            payload["exitCode"] = exit_code

        if auto_release and done:
            self._terminals.pop(terminal_id, None)
            payload["released"] = True

        return payload

    def handle_permission_request(self, params: dict[str, Any]) -> dict[str, Any]:
        request = PermissionRequest.from_params(params)
        decision = self._evaluate_permission(request)
        self._log_decision(request, decision)
        self._history.append((request, decision))

        options = params.get("options", [])
        if decision.approved:
            option_id = self._choose_allow_option(options)
            self._approved.add(self._approval_key(request))
            return {"outcome": {"outcome": "selected", "optionId": option_id}}
        return {"outcome": {"outcome": "cancelled"}}

    def handle_read_text_file(self, params: dict[str, Any]) -> dict[str, Any]:
        path_str = params.get("path")
        if not path_str:
            return {"error": {"code": ERROR_INVALID_PARAMS, "message": "Missing path"}}

        resolved = self._resolve_path(path_str)
        if isinstance(resolved, dict):
            return resolved

        permission_error = self._require_permission(
            "fs/read_text_file", path=str(resolved)
        )
        if permission_error:
            return permission_error

        if not resolved.exists():
            return {"content": None, "exists": False}
        if not resolved.is_file():
            return {
                "error": {"code": ERROR_NOT_FOUND, "message": f"Not a file: {resolved}"}
            }

        try:
            return {"content": resolved.read_text(encoding="utf-8")}
        except PermissionError:
            return {
                "error": {
                    "code": ERROR_ACCESS,
                    "message": f"Permission denied: {resolved}",
                }
            }
        except UnicodeDecodeError:
            return {
                "error": {"code": ERROR_TERMINAL, "message": f"Not UTF-8: {resolved}"}
            }
        except OSError as exc:
            return {"error": {"code": ERROR_INTERNAL, "message": f"Read failed: {exc}"}}

    def handle_write_text_file(self, params: dict[str, Any]) -> dict[str, Any]:
        path_str = params.get("path")
        content = params.get("content")
        if not path_str:
            return {"error": {"code": ERROR_INVALID_PARAMS, "message": "Missing path"}}
        if content is None:
            return {
                "error": {"code": ERROR_INVALID_PARAMS, "message": "Missing content"}
            }

        resolved = self._resolve_path(path_str)
        if isinstance(resolved, dict):
            return resolved

        permission_error = self._require_permission(
            "fs/write_text_file", path=str(resolved)
        )
        if permission_error:
            return permission_error

        if resolved.exists() and resolved.is_dir():
            return {
                "error": {
                    "code": ERROR_NOT_FOUND,
                    "message": f"Path is a directory: {resolved}",
                }
            }

        try:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(content, encoding="utf-8")
            return {"success": True}
        except PermissionError:
            return {
                "error": {
                    "code": ERROR_ACCESS,
                    "message": f"Permission denied: {resolved}",
                }
            }
        except OSError as exc:
            return {
                "error": {"code": ERROR_INTERNAL, "message": f"Write failed: {exc}"}
            }

    def handle_terminal_create(self, params: dict[str, Any]) -> dict[str, Any]:
        command = params.get("command")
        if not command:
            return {
                "error": {"code": ERROR_INVALID_PARAMS, "message": "Missing command"}
            }
        if not isinstance(command, list):
            return {
                "error": {
                    "code": ERROR_INVALID_PARAMS,
                    "message": "command must be a list",
                }
            }
        if not command:
            return {
                "error": {"code": ERROR_INVALID_PARAMS, "message": "command list empty"}
            }

        permission_error = self._require_permission("terminal/create", command=command)
        if permission_error:
            return permission_error

        cwd = params.get("cwd")
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                cwd=cwd,
                text=True,
                bufsize=0,
                start_new_session=True,
            )
        except FileNotFoundError:
            return {
                "error": {
                    "code": ERROR_NOT_FOUND,
                    "message": f"Command not found: {command[0]}",
                }
            }
        except PermissionError:
            return {
                "error": {
                    "code": ERROR_ACCESS,
                    "message": f"Permission denied: {command[0]}",
                }
            }
        except OSError as exc:
            return {
                "error": {
                    "code": ERROR_INTERNAL,
                    "message": f"Terminal create failed: {exc}",
                }
            }

        terminal_id = str(uuid.uuid4())
        self._terminals[terminal_id] = TerminalHandle(terminal_id, process)
        return {"terminalId": terminal_id}

    def handle_terminal_output(self, params: dict[str, Any]) -> dict[str, Any]:
        terminal_id = params.get("terminalId")
        if not terminal_id:
            return {
                "error": {"code": ERROR_INVALID_PARAMS, "message": "Missing terminalId"}
            }

        terminal = self._terminals.get(terminal_id)
        if not terminal:
            return {
                "error": {
                    "code": ERROR_NOT_FOUND,
                    "message": f"Terminal not found: {terminal_id}",
                }
            }

        return self._terminal_snapshot(
            terminal_id,
            terminal,
            auto_release=True,
        )

    def handle_terminal_wait_for_exit(self, params: dict[str, Any]) -> dict[str, Any]:
        terminal_id = params.get("terminalId")
        if not terminal_id:
            return {
                "error": {"code": ERROR_INVALID_PARAMS, "message": "Missing terminalId"}
            }

        terminal = self._terminals.get(terminal_id)
        if not terminal:
            return {
                "error": {
                    "code": ERROR_NOT_FOUND,
                    "message": f"Terminal not found: {terminal_id}",
                }
            }

        timeout = params.get("timeout")
        try:
            terminal.wait(timeout=timeout)
            return self._terminal_snapshot(
                terminal_id,
                terminal,
                auto_release=True,
            )
        except subprocess.TimeoutExpired:
            return {
                "error": {
                    "code": ERROR_INTERNAL,
                    "message": f"Timeout after {timeout}s",
                }
            }

    def handle_terminal_kill(self, params: dict[str, Any]) -> dict[str, Any]:
        terminal_id = params.get("terminalId")
        if not terminal_id:
            return {
                "error": {"code": ERROR_INVALID_PARAMS, "message": "Missing terminalId"}
            }

        terminal = self._terminals.get(terminal_id)
        if not terminal:
            return {
                "error": {
                    "code": ERROR_NOT_FOUND,
                    "message": f"Terminal not found: {terminal_id}",
                }
            }

        terminal.kill()
        payload = self._terminal_snapshot(
            terminal_id,
            terminal,
            auto_release=True,
        )
        payload["success"] = True
        return payload

    def handle_terminal_release(self, params: dict[str, Any]) -> dict[str, Any]:
        terminal_id = params.get("terminalId")
        if not terminal_id:
            return {
                "error": {"code": ERROR_INVALID_PARAMS, "message": "Missing terminalId"}
            }

        terminal = self._terminals.get(terminal_id)
        if not terminal:
            return {"success": True, "alreadyReleased": True}

        if terminal.is_running:
            try:
                terminal.kill()
            except OSError as exc:
                logger.warning("Failed to kill terminal %s: %s", terminal_id, exc)

        self._terminals.pop(terminal_id, None)
        return {"success": True}

    def shutdown(self) -> None:
        for terminal in list(self._terminals.values()):
            with contextlib.suppress(OSError):
                terminal.kill()
        self._terminals.clear()

    def _evaluate_permission(self, request: PermissionRequest) -> PermissionDecision:
        match self.permission_mode:
            case "auto_approve":
                return PermissionDecision(True, "auto_approve", "auto_approve")
            case "deny_all":
                return PermissionDecision(False, "deny_all", "deny_all")
            case "allowlist":
                return self._evaluate_allowlist(request)
            case "interactive":
                return self._evaluate_interactive(request)
            case _:
                return PermissionDecision(False, "unknown", "unknown")

    def _evaluate_allowlist(self, request: PermissionRequest) -> PermissionDecision:
        candidates = [request.operation]
        if request.path:
            candidates.append(f"{request.operation}:{request.path}")
        if request.command:
            candidates.append(f"{request.operation}:{' '.join(request.command)}")

        for pattern in self.allowlist:
            for candidate in candidates:
                if self._matches_pattern(candidate, pattern):
                    return PermissionDecision(True, f"allowlist {pattern}", "allowlist")
        return PermissionDecision(False, "not in allowlist", "allowlist")

    def _evaluate_interactive(self, request: PermissionRequest) -> PermissionDecision:
        if not sys.stdin.isatty():
            return PermissionDecision(False, "no tty", "interactive")

        prompt = self._format_permission_prompt(request)
        sys.stdout.write(prompt)
        sys.stdout.flush()
        answer = sys.stdin.readline().strip().lower()
        approved = answer in {"y", "yes"}
        reason = "approved" if approved else "denied"
        return PermissionDecision(approved, reason, "interactive")

    def _format_permission_prompt(self, request: PermissionRequest) -> str:
        lines = [
            "\nPermission request:",
            f"  operation: {request.operation}",
        ]
        if request.path:
            lines.append(f"  path: {request.path}")
        if request.command:
            lines.append(f"  command: {' '.join(request.command)}")
        for key, value in request.arguments.items():
            if key in {"operation", "path", "command"}:
                continue
            lines.append(f"  {key}: {value}")
        lines.append("Approve? [y/N]: ")
        return "\n".join(lines)

    def _matches_pattern(self, value: str, pattern: str) -> bool:
        if pattern.startswith("/") and pattern.endswith("/") and len(pattern) > 2:
            try:
                return re.match(pattern[1:-1], value) is not None
            except re.error:
                return False
        return fnmatch.fnmatch(value, pattern)

    def _choose_allow_option(self, options: list[dict[str, Any]]) -> str:
        for option in options:
            if option.get("type") == "allow":
                return str(option.get("id", "proceed_once"))
        if options:
            return str(options[0].get("id", "proceed_once"))
        return "proceed_once"

    def _approval_key(self, request: PermissionRequest) -> str:
        if request.path:
            return f"{request.operation}:{request.path}"
        if request.command:
            return f"{request.operation}:{' '.join(request.command)}"
        return request.operation

    def _log_decision(
        self, request: PermissionRequest, decision: PermissionDecision
    ) -> None:
        if not self.on_permission_log:
            return
        status = "APPROVED" if decision.approved else "DENIED"
        message = (
            f"Permission {status}: {request.operation} "
            f"[mode={decision.mode}, reason={decision.reason}]"
        )
        self.on_permission_log(message)

    def _require_permission(
        self,
        operation: str,
        path: str | None = None,
        command: list[str] | None = None,
    ) -> dict[str, Any] | None:
        request = PermissionRequest(operation=operation, path=path, command=command)
        if self._approval_key(request) in self._approved:
            return None
        decision = self._evaluate_permission(request)
        if decision.approved:
            return None
        return {
            "error": {
                "code": ERROR_PERMISSION_DENIED,
                "message": f"Permission denied for {operation}",
            }
        }

    def _resolve_path(self, path_str: str) -> Path | dict[str, Any]:
        path = Path(path_str)
        if not path.is_absolute():
            path = (self.base_dir / path).resolve()
        else:
            path = path.resolve()

        if not self._is_allowed_path(path):
            return {
                "error": {
                    "code": ERROR_PERMISSION_DENIED,
                    "message": f"Path not allowed: {path}",
                }
            }
        return path

    def _is_allowed_path(self, path: Path) -> bool:
        for root in self.allowed_roots:
            try:
                path.relative_to(root)
                return True
            except ValueError:
                continue
        return False
