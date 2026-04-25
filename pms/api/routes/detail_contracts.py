"""Shared helpers for API detail-route operator contracts."""

from __future__ import annotations

from collections.abc import Iterable

from pms.api.types import JsonObject
from pms.models import Task, TaskStatus


def build_task_detail_links(task_id: str) -> JsonObject:
    """Build standard discoverability links for a task detail surface."""
    return {
        "self": f"/api/v1/tasks/{task_id}",
        "plans": f"/api/v1/plans?task_id={task_id}",
        "graph": f"/api/v1/tasks/{task_id}/graph",
        "evidence": f"/api/v1/tasks/{task_id}/evidence",
        "proof_bundle": f"/api/v1/tasks/{task_id}/proof-bundle",
        "duplicates": "/api/v1/tasks/duplicates",
        "guide": "/api/v1/",
    }


def build_task_detail_next_steps(task_id: str) -> list[str]:
    """Build standard continuation hints for a task detail surface."""
    return [
        f"GET /api/v1/plans?task_id={task_id}",
        f"GET /api/v1/tasks/{task_id}/graph",
        f"GET /api/v1/tasks/{task_id}/evidence",
        f"GET /api/v1/tasks/{task_id}/proof-bundle",
    ]


def build_plan_detail_links(plan_id: str) -> JsonObject:
    """Build standard discoverability links for a plan detail surface."""
    return {
        "self": f"/api/v1/plans/{plan_id}",
        "lineage": f"/api/v1/plans/lineage?plan_id={plan_id}",
        "test_jobs": f"/api/v1/plans/{plan_id}/test-jobs",
        "guide": "/api/v1/",
    }


def build_plan_detail_next_steps(
    plan_id: str, *, focus_task_id: str | None
) -> list[str]:
    """Build standard continuation hints for a plan detail surface."""
    steps = [
        f"GET /api/v1/plans/lineage?plan_id={plan_id}",
        f"GET /api/v1/plans/{plan_id}/test-jobs",
    ]
    if focus_task_id:
        steps.append(f"GET /api/v1/tasks/{focus_task_id}")
    return steps


def task_focus_payload(task: Task) -> JsonObject:
    """Convert a task into a minimal operator-focus payload."""
    return {
        "id": task.id,
        "title": task.title,
        "status": task.status.value,
        "current_progress_percent": task.current_progress_percent,
        "reason": task_focus_reason(task.status),
    }


def select_focus_task(tasks: Iterable[Task]) -> Task | None:
    """Select the best available focus task from a task collection."""
    task_list = list(tasks)
    active = [task for task in task_list if task.status not in _TERMINAL_STATUSES]
    if not active:
        return None
    return min(
        active,
        key=lambda task: (
            task_focus_rank(task.status),
            -(task.current_progress_percent or 0),
            task.updated_at,
            task.created_at,
            task.id,
        ),
    )


def plan_terminal_reason(tasks: Iterable[Task]) -> str | None:
    """Return an execution terminal reason when a plan has no active focus task."""
    task_list = list(tasks)
    if not task_list:
        return None
    if all(task.status in _TERMINAL_STATUSES for task in task_list):
        return "all execution tasks are already complete"
    return None


_TERMINAL_STATUSES = {TaskStatus.DONE, TaskStatus.CANCELLED}


def task_focus_rank(status: TaskStatus) -> int:
    """Rank task statuses for operator focus selection."""
    if status == TaskStatus.IN_PROGRESS:
        return 0
    if status == TaskStatus.IN_REVIEW:
        return 1
    if status == TaskStatus.TODO:
        return 2
    if status == TaskStatus.BLOCKED:
        return 3
    if status == TaskStatus.DONE:
        return 4
    if status == TaskStatus.CANCELLED:
        return 5
    return 6


def task_focus_reason(status: TaskStatus) -> str:
    """Describe why a task is the chosen focus."""
    if status == TaskStatus.IN_PROGRESS:
        return "already in progress"
    if status == TaskStatus.IN_REVIEW:
        return "ready for review or validation"
    if status == TaskStatus.TODO:
        return "best available ready task"
    if status == TaskStatus.BLOCKED:
        return "best available blocked task needing unblock action"
    if status == TaskStatus.DONE:
        return "already completed"
    if status == TaskStatus.CANCELLED:
        return "already cancelled"
    return "best available task focus"
