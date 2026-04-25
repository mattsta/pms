"""Unit tests for TestExecutionService."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from pms.aws.models import RemoteTestConfig, RemoteTestResult
from pms.services.test_execution_service import (
    TestExecutionConfig,
    TestExecutionService,
)
from pms.testing.models import LocalTestConfig, LocalTestResult


class DummyLocalRunner:
    """Capture local test config without executing real tests."""

    def __init__(self) -> None:
        self.received: LocalTestConfig | None = None

    async def run(self, config: LocalTestConfig) -> LocalTestResult:
        self.received = config
        now = datetime.now(UTC)
        return LocalTestResult(
            run_id="run_local",
            server_id="local",
            success=True,
            exit_code=0,
            stdout="ok",
            stderr="",
            duration_seconds=1.2,
            started_at=now,
            finished_at=now,
        )


class DummyRemoteRunner:
    """Capture remote test config without hitting AWS."""

    def __init__(self) -> None:
        self.received: RemoteTestConfig | None = None
        self.received_callback = None

    async def sync_and_run(
        self,
        config: RemoteTestConfig,
        *,
        on_output_line=None,
    ) -> RemoteTestResult:
        self.received = config
        self.received_callback = on_output_line
        now = datetime.now(UTC)
        return RemoteTestResult(
            run_id="run_remote",
            server_id=config.server_id,
            success=True,
            exit_code=0,
            stdout="remote ok",
            stderr="",
            duration_seconds=2.3,
            started_at=now,
            finished_at=now,
        )


@pytest.mark.asyncio
async def test_local_execution_config_mapping() -> None:
    runner = DummyLocalRunner()
    service = TestExecutionService(local_runner=runner)

    config = TestExecutionConfig(
        mode="local",
        project_path=Path(),
        test_command="pytest -q",
        setup_command="pip install -r requirements.txt",
        working_dir="src",
        env_vars=(("ENV", "1"),),
        timeout=12.5,
        capture_logs=("logs/test.log",),
        save_artifacts=("dist/report.html",),
        project_id="proj_123",
        plan_id="plan_123",
        task_ids=("task_1", "task_2"),
    )

    result = await service.run(config)

    assert runner.received is not None
    assert runner.received.project_path == Path()
    assert runner.received.test_command == "pytest -q"
    assert runner.received.setup_command == "pip install -r requirements.txt"
    assert runner.received.working_dir == "src"
    assert runner.received.env_vars == (("ENV", "1"),)
    assert runner.received.timeout == 12.5
    assert runner.received.capture_logs == ("logs/test.log",)
    assert runner.received.save_artifacts == ("dist/report.html",)
    assert runner.received.project_id == "proj_123"
    assert runner.received.plan_id == "plan_123"
    assert runner.received.task_ids == ("task_1", "task_2")
    assert result.run_id == "run_local"


@pytest.mark.asyncio
async def test_remote_execution_config_mapping() -> None:
    runner = DummyRemoteRunner()
    service = TestExecutionService(remote_runner=runner)
    emitted: list[tuple[str, str]] = []

    async def callback(source: str, line: str) -> None:
        emitted.append((source, line))

    config = TestExecutionConfig(
        mode="aws",
        server_id="srv_123",
        project_path=Path("/tmp/project"),
        remote_path="/opt/project",
        test_command="pytest -q",
        setup_command="pip install -r requirements.txt",
        timeout=45.0,
        stream_output=True,
        exclude_patterns=("*.cache",),
        project_id="proj_123",
        plan_id="plan_123",
        task_ids=("task_1",),
    )

    result = await service.run(config, on_output_line=callback)

    assert runner.received is not None
    assert runner.received_callback is callback
    assert runner.received.server_id == "srv_123"
    assert runner.received.project_path == Path("/tmp/project")
    assert runner.received.remote_path == "/opt/project"
    assert runner.received.test_command == "pytest -q"
    assert runner.received.setup_command == "pip install -r requirements.txt"
    assert runner.received.timeout == 45.0
    assert runner.received.stream_output is True
    assert runner.received.exclude_patterns == ("*.cache",)
    assert runner.received.project_id == "proj_123"
    assert runner.received.plan_id == "plan_123"
    assert runner.received.task_ids == ("task_1",)
    assert result.run_id == "run_remote"
    assert emitted == []
