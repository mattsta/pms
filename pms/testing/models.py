"""Models for local test execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LocalTestConfig:
    """Configuration for a local test run."""

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


@dataclass
class LocalTestResult:
    """Result of a local test run."""

    run_id: str
    server_id: str
    success: bool
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    started_at: datetime
    finished_at: datetime
    logs: dict[str, str] = field(default_factory=dict)
    artifacts: dict[str, Path] = field(default_factory=dict)
    workflow_transition: Any | None = None

    @property
    def summary(self) -> str:
        """Generate a brief summary of the test result."""
        status = "PASSED" if self.success else "FAILED"
        return f"{status} (exit code {self.exit_code}) in {self.duration_seconds:.1f}s"
