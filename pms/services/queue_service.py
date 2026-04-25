"""Service for smart task queues and presets."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from pms.models import Task
from pms.repositories.base import QueryResult
from pms.services.task_service import TaskService


@dataclass
class QueueSummary:
    """Summary of a smart queue preset."""

    name: str
    description: str
    total_count: int
    items: list[Task]

    @property
    def displayed_count(self) -> int:
        return len(self.items)

    @property
    def is_truncated(self) -> bool:
        return self.displayed_count < self.total_count


class QueueService:
    """Service for built-in queue presets."""

    def __init__(self, task_service: TaskService) -> None:
        self._task_service = task_service

    async def list_presets(
        self,
        project_id: str | None = None,
        limit: int = 5,
        stale_days: int = 14,
        at_risk_days: int = 7,
    ) -> list[QueueSummary]:
        presets = ["ready", "stale", "blocked", "overdue", "at_risk"]
        summaries = []
        for name in presets:
            summary = await self.get_preset(
                name=name,
                project_id=project_id,
                limit=limit,
                stale_days=stale_days,
                at_risk_days=at_risk_days,
            )
            if summary:
                summaries.append(summary)
        return summaries

    async def get_preset(
        self,
        name: str,
        project_id: str | None = None,
        limit: int = 10,
        offset: int = 0,
        stale_days: int = 14,
        at_risk_days: int = 7,
    ) -> QueueSummary | None:
        name = name.lower().strip()
        match name:
            case "ready":
                result = await self._task_service.list_ready_tasks(
                    project_id=project_id,
                    limit=limit,
                    offset=offset,
                )
                return self._build_summary(
                    "ready",
                    "Tasks ready to start (no blocking dependencies).",
                    result,
                )
            case "stale":
                result = await self._task_service.list_stale_tasks(
                    project_id=project_id,
                    stale_after_days=stale_days,
                    limit=limit,
                    offset=offset,
                )
                return self._build_summary(
                    "stale",
                    f"Tasks with no updates in {stale_days}+ days.",
                    result,
                )
            case "blocked":
                tasks = await self._task_service.get_blocked_tasks(
                    project_id=project_id
                )
                items = tasks[offset : offset + limit] if limit > 0 else tasks[offset:]
                return QueueSummary(
                    name="blocked",
                    description="Tasks blocked by dependencies or execution locks.",
                    total_count=len(tasks),
                    items=items,
                )
            case "overdue":
                now = datetime.now(UTC)
                result = await self._task_service.search_tasks(
                    project_id=project_id,
                    due_to=now,
                    include_terminal=False,
                    limit=limit,
                    offset=offset,
                )
                return self._build_summary(
                    "overdue",
                    "Tasks past their due date.",
                    result,
                )
            case "at_risk":
                now = datetime.now(UTC)
                horizon = now + timedelta(days=at_risk_days)
                result = await self._task_service.search_tasks(
                    project_id=project_id,
                    due_from=now,
                    due_to=horizon,
                    include_terminal=False,
                    limit=limit,
                    offset=offset,
                )
                return self._build_summary(
                    "at_risk",
                    f"Tasks due within the next {at_risk_days} days.",
                    result,
                )
            case _:
                return None

    def _build_summary(
        self,
        name: str,
        description: str,
        result: QueryResult[Task],
    ) -> QueueSummary:
        return QueueSummary(
            name=name,
            description=description,
            total_count=result.total_count,
            items=result.items,
        )
