"""Unified test execution service for local and remote runs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pms.aws.models import RemoteTestConfig, RemoteTestResult
from pms.testing.models import LocalTestConfig, LocalTestResult

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pms.aws.test_runner import TestRunner
    from pms.testing.local_runner import LocalTestRunner


TestExecutionMode = Literal["local", "aws"]


@dataclass(frozen=True)
class TestExecutionConfig:
    """Configuration for unified test execution."""

    __test__ = False

    mode: TestExecutionMode
    project_path: Path
    test_command: str = "pytest"
    setup_command: str | None = None
    working_dir: str | None = None
    env_vars: tuple[tuple[str, str], ...] = ()
    timeout: float = 600.0
    capture_logs: tuple[str, ...] = ()
    save_artifacts: tuple[str, ...] = ()
    project_id: str | None = None
    plan_id: str | None = None
    task_ids: tuple[str, ...] = ()
    transition_on_success: str | None = None
    transition_on_failure: str | None = None
    transition_by: str | None = None
    transition_reason: str | None = None

    # Remote-only options
    server_id: str | None = None
    server_name: str | None = None
    remote_path: str = "/home/ec2-user/project"
    exclude_patterns: tuple[str, ...] | None = None
    stream_output: bool = False  # Live output requires a caller-provided sink


class TestExecutionService:
    """Unified runner that dispatches to local or AWS execution."""

    __test__ = False

    def __init__(
        self,
        local_runner: LocalTestRunner | None = None,
        remote_runner: TestRunner | None = None,
    ) -> None:
        self._local_runner = local_runner
        self._remote_runner = remote_runner

    async def run(
        self,
        config: TestExecutionConfig,
        *,
        on_output_line: Callable[[str, str], Awaitable[None] | None] | None = None,
    ) -> LocalTestResult | RemoteTestResult:
        """Run tests based on the selected mode."""
        match config.mode:
            case "local":
                if self._local_runner is None:
                    raise RuntimeError("Local test runner not configured")
                return await self._local_runner.run(
                    LocalTestConfig(
                        project_path=config.project_path,
                        test_command=config.test_command,
                        setup_command=config.setup_command,
                        working_dir=config.working_dir,
                        env_vars=config.env_vars,
                        timeout=config.timeout,
                        capture_logs=config.capture_logs,
                        save_artifacts=config.save_artifacts,
                        project_id=config.project_id,
                        plan_id=config.plan_id,
                        task_ids=config.task_ids,
                        transition_on_success=config.transition_on_success,
                        transition_on_failure=config.transition_on_failure,
                        transition_by=config.transition_by,
                        transition_reason=config.transition_reason,
                    )
                )
            case "aws":
                if self._remote_runner is None:
                    raise RuntimeError("Remote test runner not configured")
                server_id = config.server_id or await self._resolve_server_id(
                    config.server_name
                )
                if server_id is None:
                    if config.server_name:
                        raise RuntimeError(
                            f"Test server '{config.server_name}' not found"
                        )
                    raise RuntimeError("Server ID or name is required for AWS runs")
                remote_kwargs = {
                    "server_id": server_id,
                    "project_path": config.project_path,
                    "remote_path": config.remote_path,
                    "project_id": config.project_id,
                    "plan_id": config.plan_id,
                    "task_ids": config.task_ids,
                    "transition_on_success": config.transition_on_success,
                    "transition_on_failure": config.transition_on_failure,
                    "transition_by": config.transition_by,
                    "transition_reason": config.transition_reason,
                    "test_command": config.test_command,
                    "setup_command": config.setup_command,
                    "working_dir": config.working_dir,
                    "env_vars": config.env_vars,
                    "timeout": config.timeout,
                    "stream_output": config.stream_output,
                    "capture_logs": config.capture_logs,
                    "save_artifacts": config.save_artifacts,
                }
                if config.exclude_patterns is not None:
                    remote_kwargs["exclude_patterns"] = config.exclude_patterns
                return await self._remote_runner.sync_and_run(
                    RemoteTestConfig(**remote_kwargs),
                    on_output_line=on_output_line,
                )
            case _:
                raise ValueError(f"Unsupported test execution mode: {config.mode}")

    async def _resolve_server_id(self, server_name: str | None) -> str | None:
        if not server_name or self._remote_runner is None:
            return None

        servers = await self._remote_runner.fleet.list_servers()
        server = next((s for s in servers if s.name == server_name), None)
        if server is None:
            server = await self._remote_runner.fleet.get_server(server_name)
        if server is None:
            return None
        return server.id
