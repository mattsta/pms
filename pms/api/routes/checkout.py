"""Checkout API routes."""

from datetime import datetime
from typing import Any, TypedDict

from fastapi import APIRouter, Depends, HTTPException

from pms.api.actor_payloads import checkout_payload, resolved_actor_payload
from pms.api.auth import Scopes, require_scope
from pms.api.dependencies import get_db
from pms.api.models import CheckoutRequest, CheckoutResponse
from pms.api.types import JsonObject
from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.db.connection import Database
from pms.exceptions.base import TaskCheckoutBlocked, TaskCheckoutConflict
from pms.models.api_key import ApiKey
from pms.repositories.task_repository import TaskRepository
from pms.services.actor_service import ActorService

router = APIRouter()


class RenewCheckoutResponse(TypedDict):
    """Checkout renewal response."""

    status: str
    lease_until: datetime | None


class AvailableTaskItem(TypedDict):
    """Simplified available task payload."""

    id: str
    title: str
    project_id: str | None
    complexity_points: int | None
    priority: str


class AvailableTasksResponse(TypedDict):
    """Available checkouts response."""

    available_tasks: list[AvailableTaskItem]
    count: int


class CheckoutStatusItem(TypedDict):
    """Checkout status row."""

    id: str
    title: str
    project_id: str | None
    checkout: JsonObject | None


class CheckoutStatusResponse(TypedDict):
    """Checkout status response."""

    agent_session_id: str
    checkouts: list[CheckoutStatusItem]
    count: int


class CheckoutCleanupResponse(TypedDict):
    """Cleanup checkouts response."""

    expired_task_ids: list[str]
    count: int
    dry_run: bool


class CheckoutLogResponse(TypedDict):
    """Checkout log response."""

    entries: list[JsonObject]
    count: int


@router.post("/tasks/{task_id}/checkout", response_model=CheckoutResponse)
async def checkout_task(
    task_id: str,
    data: CheckoutRequest,
    db: Database = Depends(get_db),
    _api_key: ApiKey = Depends(require_scope(Scopes.TASKS_WRITE)),
) -> CheckoutResponse:
    """Checkout a task for exclusive work."""
    # Get task repository
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)
    task_repo = TaskRepository(db, event_store, revision_store, metrics)
    actor_service = ActorService(db, event_store, revision_store, metrics)

    try:
        checkout_actor = await actor_service.resolve_checkout_actor(
            agent_session_id=data.agent_session_id,
            actor=data.actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    checkout_actor_id: str | None = checkout_actor.id

    try:
        task = await task_repo.checkout_task(
            task_id=task_id,
            agent_session_id=data.agent_session_id,
            lease_seconds=data.lease_seconds,
            checkout_actor_id=checkout_actor_id,
        )

        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        if (
            task.checkout_agent_session_id is None
            or task.checked_out_at is None
            or task.checkout_lease_until is None
        ):
            raise HTTPException(status_code=500, detail="Checkout state not persisted")
        if checkout_actor is None and task.checkout_actor_id:
            checkout_actor = await actor_service.get_actor(task.checkout_actor_id)

        return CheckoutResponse(
            task_id=task.id,
            checkout=checkout_payload(
                agent_session_id=task.checkout_agent_session_id,
                actor_obj=checkout_actor,
                checked_out_at=task.checked_out_at,
                lease_until=task.checkout_lease_until,
                version=task.checkout_version,
                expired=task.checkout_expired,
            ),
        )

    except TaskCheckoutConflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    except TaskCheckoutBlocked as e:
        raise HTTPException(status_code=423, detail=str(e))


@router.post("/tasks/{task_id}/checkout/renew")
async def renew_checkout(
    task_id: str,
    agent_session_id: str,
    lease_seconds: int = 300,
    actor: str | None = None,
    db: Database = Depends(get_db),
    _api_key: ApiKey = Depends(require_scope(Scopes.TASKS_WRITE)),
) -> RenewCheckoutResponse:
    """Renew checkout lease (heartbeat)."""
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)
    task_repo = TaskRepository(db, event_store, revision_store, metrics)
    actor_service = ActorService(db, event_store, revision_store, metrics)
    try:
        checkout_actor = await actor_service.resolve_checkout_actor(
            agent_session_id=agent_session_id,
            actor=actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    checkout_actor_id: str | None = checkout_actor.id

    try:
        task = await task_repo.renew_checkout(
            task_id,
            agent_session_id,
            lease_seconds,
            checkout_actor_id=checkout_actor_id,
        )

        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")

        return {"status": "renewed", "lease_until": task.checkout_lease_until}

    except TaskCheckoutConflict as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/tasks/{task_id}/checkout/release")
async def release_checkout(
    task_id: str,
    agent_session_id: str,
    db: Database = Depends(get_db),
    _api_key: ApiKey = Depends(require_scope(Scopes.TASKS_WRITE)),
) -> dict[str, str]:
    """Release checkout lock."""
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)
    task_repo = TaskRepository(db, event_store, revision_store, metrics)

    try:
        task = await task_repo.release_checkout(task_id, agent_session_id)

        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")

        return {"status": "released", "task_id": task.id}

    except TaskCheckoutConflict as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/tasks/{task_id}/checkout/force-release")
async def force_release_checkout(
    task_id: str,
    released_by: str | None = None,
    reason: str | None = None,
    db: Database = Depends(get_db),
    _api_key: ApiKey = Depends(require_scope(Scopes.CHECKOUT_WRITE)),
) -> dict[str, str]:
    """Force release a checkout lock."""
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)
    task_repo = TaskRepository(db, event_store, revision_store, metrics)

    task = await task_repo.force_release_checkout(
        task_id=task_id,
        released_by=released_by,
        reason=reason,
    )

    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    return {
        "status": "force_released",
        "task_id": task.id,
        "released_by": released_by or "system",
    }


@router.get("/checkout/available")
async def get_available_tasks(
    project_id: str | None = None,
    limit: int = 100,
    db: Database = Depends(get_db),
    _api_key: ApiKey = Depends(require_scope(Scopes.TASKS_READ)),
) -> AvailableTasksResponse:
    """Get tasks available for checkout."""
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)
    task_repo = TaskRepository(db, event_store, revision_store, metrics)

    tasks = await task_repo.get_available_tasks(
        project_id=project_id,
        limit=limit,
    )

    return {
        "available_tasks": [
            {
                "id": t.id,
                "title": t.title,
                "project_id": t.project_id,
                "complexity_points": t.complexity_points,
                "priority": t.priority.value,
            }
            for t in tasks
        ],
        "count": len(tasks),
    }


@router.get("/checkout/status")
async def get_checkout_status(
    agent_session_id: str,
    include_expired: bool = False,
    db: Database = Depends(get_db),
    _api_key: ApiKey = Depends(require_scope(Scopes.TASKS_READ)),
) -> CheckoutStatusResponse:
    """Get all tasks checked out by an agent."""
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)
    task_repo = TaskRepository(db, event_store, revision_store, metrics)
    actor_service = ActorService(db, event_store, revision_store, metrics)

    tasks = await task_repo.get_agent_checkouts(
        agent_session_id=agent_session_id,
        include_expired=include_expired,
    )
    checkout_actor_map: dict[str, Any | None] = {}
    for task in tasks:
        if task.checkout_actor_id and task.checkout_actor_id not in checkout_actor_map:
            actor = await actor_service.get_actor(task.checkout_actor_id)
            checkout_actor_map[task.checkout_actor_id] = actor

    return {
        "agent_session_id": agent_session_id,
        "checkouts": [
            {
                "id": t.id,
                "title": t.title,
                "project_id": t.project_id,
                "checkout": checkout_payload(
                    agent_session_id=t.checkout_agent_session_id,
                    actor_obj=(
                        checkout_actor_map.get(t.checkout_actor_id)
                        if t.checkout_actor_id
                        else None
                    ),
                    checked_out_at=t.checked_out_at,
                    lease_until=t.checkout_lease_until,
                    version=t.checkout_version,
                    expired=t.checkout_expired,
                ),
            }
            for t in tasks
        ],
        "count": len(tasks),
    }


@router.post("/checkout/cleanup")
async def cleanup_expired_checkouts(
    dry_run: bool = False,
    db: Database = Depends(get_db),
    _api_key: ApiKey = Depends(require_scope(Scopes.CHECKOUT_WRITE)),
) -> CheckoutCleanupResponse:
    """Cleanup expired checkouts."""
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)
    task_repo = TaskRepository(db, event_store, revision_store, metrics)

    expired_ids = await task_repo.cleanup_expired_checkouts(dry_run=dry_run)

    return {
        "expired_task_ids": expired_ids,
        "count": len(expired_ids),
        "dry_run": dry_run,
    }


@router.get("/checkout/log")
async def get_checkout_log(
    task_id: str | None = None,
    agent_session_id: str | None = None,
    action: str | None = None,
    success: bool | None = None,
    limit: int = 100,
    offset: int = 0,
    include_metadata: bool = False,
    db: Database = Depends(get_db),
    _api_key: ApiKey = Depends(require_scope(Scopes.TASKS_READ)),
) -> CheckoutLogResponse:
    """Get checkout audit log entries."""
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)
    task_repo = TaskRepository(db, event_store, revision_store, metrics)
    actor_service = ActorService(db, event_store, revision_store, metrics)

    entries = await task_repo.get_checkout_log(
        task_id=task_id,
        agent_session_id=agent_session_id,
        action=action,
        success=success,
        limit=limit,
        offset=offset,
        include_metadata=include_metadata,
    )
    checkout_actor_map: dict[str, Any | None] = {}
    for entry in entries:
        checkout_actor_id = entry.get("checkout_actor_id")
        if checkout_actor_id and checkout_actor_id not in checkout_actor_map:
            actor = await actor_service.get_actor(str(checkout_actor_id))
            checkout_actor_map[str(checkout_actor_id)] = actor

    return {
        "entries": [
            {
                **{
                    key: value
                    for key, value in entry.items()
                    if key != "checkout_actor_id"
                },
                "actor": resolved_actor_payload(
                    checkout_actor_map.get(str(entry["checkout_actor_id"]))
                    if entry.get("checkout_actor_id")
                    else None
                ),
            }
            for entry in entries
        ],
        "count": len(entries),
    }
