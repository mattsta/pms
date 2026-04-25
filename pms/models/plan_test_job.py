"""Plan-linked test job definition."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pms.models.base import BaseModel
from pms.models.json_types import ModelObject

PlanTestJobMode = Literal["local", "aws"]


@dataclass
class PlanTestJob(BaseModel):
    """Stored test job configuration tied to a plan."""

    plan_id: str = ""
    name: str = ""
    description: str | None = None
    mode: PlanTestJobMode = "local"
    project_path: str = "."
    test_command: str = "pytest"
    setup_command: str | None = None
    working_dir: str | None = None
    env_vars: tuple[tuple[str, str], ...] = ()
    timeout: float = 600.0
    capture_logs: tuple[str, ...] = ()
    save_artifacts: tuple[str, ...] = ()
    task_ids: tuple[str, ...] = ()
    transition_on_success: str | None = None
    transition_on_failure: str | None = None
    transition_by: str | None = None
    transition_reason: str | None = None
    project_id: str | None = None
    server_id: str | None = None
    server_name: str | None = None
    remote_path: str = "/home/ec2-user/project"
    exclude_patterns: tuple[str, ...] | None = None
    stream_output: bool = False  # Deprecated; persisted jobs do not stream live output
    archived_at: datetime | None = None

    def to_dict(self) -> ModelObject:
        data = super().to_dict()
        data["env_vars"] = [list(pair) for pair in self.env_vars]
        data["capture_logs"] = list(self.capture_logs)
        data["save_artifacts"] = list(self.save_artifacts)
        data["task_ids"] = list(self.task_ids)
        data["exclude_patterns"] = (
            list(self.exclude_patterns) if self.exclude_patterns is not None else None
        )
        data["stream_output"] = self.stream_output
        return data

    @classmethod
    def from_dict(cls, data: ModelObject) -> PlanTestJob:
        if "env_vars" in data and isinstance(data["env_vars"], list):
            data["env_vars"] = tuple(
                tuple(item) for item in data["env_vars"] if isinstance(item, list)
            )
        if "capture_logs" in data and isinstance(data["capture_logs"], list):
            data["capture_logs"] = tuple(data["capture_logs"])
        if "save_artifacts" in data and isinstance(data["save_artifacts"], list):
            data["save_artifacts"] = tuple(data["save_artifacts"])
        if "task_ids" in data and isinstance(data["task_ids"], list):
            data["task_ids"] = tuple(data["task_ids"])
        if "exclude_patterns" in data and isinstance(data["exclude_patterns"], list):
            data["exclude_patterns"] = tuple(data["exclude_patterns"])
        return super().from_dict(data)
