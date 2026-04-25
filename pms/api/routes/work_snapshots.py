"""API routes for work snapshot views."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from pms.api.auth import AuthorizationError, Scopes, check_rate_limit, get_api_key
from pms.api.dependencies import (
    get_db,
    get_project_service,
    get_queue_service,
    get_task_service,
    get_test_run_service,
    get_work_snapshot_service,
)
from pms.api.models import (
    WorkSnapshotResponse,
    WorkSnapshotReviewPreviewResponse,
    WorkSnapshotReviewRequest,
    WorkSnapshotReviewResponse,
)
from pms.api.routes.discoverability import (
    QueryParamMap,
    build_query_path,
    normalize_next_steps,
)
from pms.api.types import JsonObject
from pms.db.connection import Database
from pms.models.api_key import ApiKey
from pms.repositories.state_transition_repository import StateTransitionRepository
from pms.services.project_service import ProjectService
from pms.services.queue_service import QueueService
from pms.services.task_service import TaskService
from pms.services.test_run_service import TestRunService
from pms.services.work_daily_service import WorkDailyService
from pms.services.work_snapshot_service import WorkSnapshotService

router = APIRouter()

type WorkDailyPayload = JsonObject


def _snapshot_path(scope_type: str, scope_id: str) -> str:
    return f"/api/v1/work-snapshots/{scope_type}/{scope_id}"


def _required_scope(scope_type: str, write: bool) -> str | None:
    match scope_type.lower():
        case "organization":
            return Scopes.ORGS_WRITE if write else Scopes.ORGS_READ
        case "portfolio":
            return Scopes.PORTFOLIOS_WRITE if write else Scopes.PORTFOLIOS_READ
        case "program":
            return Scopes.PROGRAMS_WRITE if write else Scopes.PROGRAMS_READ
        case "project":
            return Scopes.PROJECTS_WRITE if write else Scopes.PROJECTS_READ
        case _:
            return None


async def _authorize_snapshot(
    scope_type: str,
    api_key: ApiKey,
    write: bool,
) -> None:
    required = _required_scope(scope_type, write)
    if required is None:
        raise HTTPException(
            status_code=400,
            detail="Invalid scope_type. Use organization, portfolio, program, or project.",
        )
    if not api_key.matches_scope(required):
        raise AuthorizationError(f"Missing required scope: {required}")
    await check_rate_limit(api_key)


async def require_snapshot_read(
    scope_type: str,
    api_key: ApiKey = Depends(get_api_key),
) -> ApiKey:
    """Require scope-aware read access for snapshots."""
    await _authorize_snapshot(scope_type, api_key, write=False)
    return api_key


async def require_snapshot_write(
    scope_type: str,
    api_key: ApiKey = Depends(get_api_key),
) -> ApiKey:
    """Require scope-aware write access for snapshot reviews."""
    await _authorize_snapshot(scope_type, api_key, write=True)
    return api_key


@router.get(
    "/work-snapshots/{scope_type}/{scope_id}",
    response_model=WorkSnapshotResponse,
)
async def get_work_snapshot(
    scope_type: str,
    scope_id: str,
    task_limit: int = 5,
    test_limit: int = 5,
    include_history: bool = True,
    history_limit: int = 3,
    snapshot_service: WorkSnapshotService = Depends(get_work_snapshot_service),
    _api_key: ApiKey = Depends(require_snapshot_read),
) -> WorkSnapshotResponse:
    """Get a unified work snapshot for a scope."""
    normalized_scope_type = scope_type.lower()
    snapshot = await snapshot_service.get_snapshot(
        scope_type=normalized_scope_type,
        scope_id=scope_id,
        task_limit=task_limit,
        test_limit=test_limit,
    )
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Work snapshot not found")

    review_history_preview: list[WorkSnapshotReviewPreviewResponse] = []
    if include_history:
        reviews = await snapshot_service.list_reviews(
            scope_type=normalized_scope_type,
            scope_id=scope_id,
            limit=history_limit,
            offset=0,
        )
        review_history_preview = [
            WorkSnapshotReviewPreviewResponse(
                id=review.id,
                reviewed_at=review.reviewed_at,
                reviewed_by=review.reviewed_by,
                note=review.note,
                metadata=review.metadata,
            )
            for review in reviews.items
        ]

    params: QueryParamMap = {
        "task_limit": task_limit,
        "test_limit": test_limit,
        "include_history": include_history,
        "history_limit": history_limit,
    }
    base_path = _snapshot_path(normalized_scope_type, scope_id)
    self_path = build_query_path(base_path, params)
    links: JsonObject = {
        "self": self_path,
        "daily": f"{base_path}/daily",
        "review": f"{base_path}/review",
        "dashboard": "/dashboard",
        "queues": "/api/v1/queues/presets",
        "guide": "/api/v1/",
    }
    next_steps = normalize_next_steps(
        f"GET {base_path}/daily",
        f"POST {base_path}/review",
        "GET /api/v1/queues/presets",
        "GET /api/v1/plans/lineage",
    )

    payload = snapshot.to_dict()
    payload["review_history_preview"] = [
        {
            "id": review.id,
            "reviewed_at": review.reviewed_at.isoformat(),
            "reviewed_by": review.reviewed_by,
            "note": review.note,
            "metadata": review.metadata,
        }
        for review in review_history_preview
    ]
    payload["links"] = links
    payload["next_steps"] = next_steps
    payload["params"] = params
    return WorkSnapshotResponse(**payload)


@router.get("/work-snapshots/{scope_type}/{scope_id}/daily")
async def get_work_daily(
    scope_type: str,
    scope_id: str,
    task_limit: int = 5,
    test_limit: int = 5,
    queue_limit: int = 3,
    stale_days: int = 14,
    at_risk_days: int = 7,
    include_timeline: bool = False,
    timeline_limit: int = 5,
    include_history: bool = False,
    history_limit: int = 3,
    view: str = "detail",
    db: Database = Depends(get_db),
    snapshot_service: WorkSnapshotService = Depends(get_work_snapshot_service),
    queue_service: QueueService = Depends(get_queue_service),
    task_service: TaskService = Depends(get_task_service),
    project_service: ProjectService = Depends(get_project_service),
    test_run_service: TestRunService = Depends(get_test_run_service),
    _api_key: ApiKey = Depends(require_snapshot_read),
) -> WorkDailyPayload:
    """Get a daily review summary for a scope."""
    normalized_scope_type = scope_type.lower()
    if view not in {"overview", "detail", "trace"}:
        raise HTTPException(status_code=400, detail="Invalid view")

    daily_service = WorkDailyService(
        snapshot_service=snapshot_service,
        queue_service=queue_service,
        task_service=task_service,
        project_service=project_service,
        transition_repo=StateTransitionRepository(db),
        test_run_service=test_run_service,
    )
    summary = await daily_service.build_summary(
        scope_type=normalized_scope_type,
        scope_id=scope_id,
        task_limit=task_limit,
        test_limit=test_limit,
        queue_limit=queue_limit,
        stale_days=stale_days,
        at_risk_days=at_risk_days,
        include_timeline=include_timeline,
        timeline_limit=timeline_limit,
        include_history=include_history,
        history_limit=history_limit,
        view=view,
    )
    if summary is None:
        raise HTTPException(status_code=404, detail="Work snapshot not found")

    params: QueryParamMap = {
        "task_limit": task_limit,
        "test_limit": test_limit,
        "queue_limit": queue_limit,
        "stale_days": stale_days,
        "at_risk_days": at_risk_days,
        "include_timeline": include_timeline,
        "timeline_limit": timeline_limit,
        "include_history": include_history,
        "history_limit": history_limit,
        "view": view,
    }
    daily_path = f"{_snapshot_path(normalized_scope_type, scope_id)}/daily"
    daily_self_path = build_query_path(daily_path, params)
    payload = summary.to_dict()
    payload["api_links"] = {
        "self": daily_self_path,
        "snapshot": _snapshot_path(normalized_scope_type, scope_id),
        "review": f"{_snapshot_path(normalized_scope_type, scope_id)}/review",
        "dashboard": "/dashboard",
        "queues": "/api/v1/queues/presets",
        "guide": "/api/v1/",
    }
    payload["next_steps_api"] = normalize_next_steps(
        f"POST /api/v1/work-snapshots/{normalized_scope_type}/{scope_id}/review",
        f"GET /api/v1/work-snapshots/{normalized_scope_type}/{scope_id}",
        f"GET /api/v1/work-snapshots/{normalized_scope_type}/{scope_id}/daily",
        "GET /api/v1/queues/presets",
    )
    payload["params"] = params
    return payload


@router.post(
    "/work-snapshots/{scope_type}/{scope_id}/review",
    response_model=WorkSnapshotReviewResponse,
    status_code=201,
)
async def mark_work_snapshot_reviewed(
    scope_type: str,
    scope_id: str,
    data: WorkSnapshotReviewRequest,
    snapshot_service: WorkSnapshotService = Depends(get_work_snapshot_service),
    _api_key: ApiKey = Depends(require_snapshot_write),
) -> WorkSnapshotReviewResponse:
    """Record a snapshot review checkpoint."""
    normalized_scope_type = scope_type.lower()
    review = await snapshot_service.mark_reviewed(
        scope_type=normalized_scope_type,
        scope_id=scope_id,
        reviewed_by=data.reviewed_by,
        note=data.note,
        metadata=data.metadata,
    )
    if review is None:
        raise HTTPException(status_code=404, detail="Work snapshot not found")
    base_path = _snapshot_path(normalized_scope_type, scope_id)
    links: JsonObject = {
        "self": f"{base_path}/review",
        "snapshot": base_path,
        "daily": f"{base_path}/daily",
        "guide": "/api/v1/",
    }
    next_steps = normalize_next_steps(
        f"GET {base_path}",
        f"GET {base_path}/daily",
        "GET /api/v1/queues/presets",
    )
    params: QueryParamMap = {
        "scope_type": normalized_scope_type,
        "scope_id": scope_id,
    }
    return WorkSnapshotReviewResponse(
        id=review.id,
        scope_type=review.scope_type,
        scope_id=review.scope_id,
        reviewed_at=review.reviewed_at,
        reviewed_by=review.reviewed_by,
        note=review.note,
        metadata=review.metadata,
        links=links,
        next_steps=next_steps,
        params=params,
    )
