"""Progress tracking API routes."""

from typing import TypedDict

from fastapi import APIRouter, Depends, HTTPException

from pms.api.auth import Scopes, require_scope
from pms.api.dependencies import get_task_service
from pms.api.models import ProgressResponse, ProgressUpdate
from pms.models.api_key import ApiKey
from pms.services.task_service import TaskService

router = APIRouter()


class ProgressTimelinePayload(TypedDict):
    """Progress timeline payload."""

    task_id: str
    current_percent: int
    total_duration_hours: float
    velocity_percent_per_hour: float
    estimated_completion: str | None
    updates_count: int
    velocity_trend: str


@router.post("/tasks/{task_id}/progress", response_model=ProgressResponse)
async def update_task_progress(
    task_id: str,
    data: ProgressUpdate,
    task_service: TaskService = Depends(get_task_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.TASKS_WRITE)),
) -> ProgressResponse:
    """Update task progress."""
    task = await task_service.update_task_progress(
        task_id=task_id,
        percent_complete=data.percent_complete,
        status_message=data.status_message,
        updated_by=data.updated_by,
        metadata=data.metadata,
    )

    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    return ProgressResponse(
        task_id=task.id,
        percent_complete=task.current_progress_percent,
        status_message=data.status_message,
        updated_by=data.updated_by,
        timestamp=task.last_progress_update_at or task.updated_at,
    )


@router.get("/tasks/{task_id}/progress/timeline")
async def get_progress_timeline(
    task_id: str,
    task_service: TaskService = Depends(get_task_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.TASKS_READ)),
) -> ProgressTimelinePayload:
    """Get complete progress timeline with velocity/ETA."""
    timeline = await task_service.get_progress_timeline(task_id)

    return {
        "task_id": timeline.task_id,
        "current_percent": timeline.current_percent,
        "total_duration_hours": timeline.total_duration_hours,
        "velocity_percent_per_hour": timeline.average_velocity_percent_per_hour,
        "estimated_completion": timeline.estimated_completion_time.isoformat()
        if timeline.estimated_completion_time
        else None,
        "updates_count": len(timeline.updates),
        "velocity_trend": timeline.get_velocity_trend(),
    }
