"""Transition timeline API routes."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from pms.api.auth import Scopes, require_scope
from pms.api.dependencies import get_db, get_label_service
from pms.api.models import StateTransitionResponse, TransitionTimelineResponse
from pms.core.entity_type_contract import validate_entity_type
from pms.db.connection import Database
from pms.models.api_key import ApiKey
from pms.models.state_transition import TransitionTimeline
from pms.repositories.state_transition_repository import StateTransitionRepository
from pms.services.label_service import LabelService

router = APIRouter()

_ALLOWED_ENTITY_TYPES = {
    "task",
    "goal",
    "objective",
    "project",
    "product",
    "plan",
    "program",
    "portfolio",
    "organization",
}


def _validate_entity_type(entity_type: str) -> str:
    try:
        return validate_entity_type(entity_type, allowed=_ALLOWED_ENTITY_TYPES)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _timeline_to_response(
    *,
    entity_type: str,
    kind: str,
    timeline: TransitionTimeline,
) -> TransitionTimelineResponse:
    return TransitionTimelineResponse(
        entity_type=entity_type,
        entity_id=timeline.entity_id,
        kind=kind,
        total_duration_seconds=timeline.total_duration_seconds,
        total_duration_hours=timeline.total_duration_hours,
        average_state_duration_hours=timeline.average_state_duration_hours,
        state_durations=timeline.state_durations,
        transitions=[
            StateTransitionResponse(
                id=transition.id,
                entity_type=transition.entity_type,
                entity_id=transition.entity_id,
                from_state=transition.from_state,
                to_state=transition.to_state,
                timestamp=transition.timestamp,
                triggered_by=transition.triggered_by,
                reason=transition.reason,
                duration_in_state_seconds=transition.duration_in_state_seconds,
                metadata=transition.metadata,
            )
            for transition in timeline.transitions
        ],
    )


def _empty_timeline(
    *,
    entity_type: str,
    entity_id: str,
    kind: str,
) -> TransitionTimelineResponse:
    return TransitionTimelineResponse(
        entity_type=entity_type,
        entity_id=entity_id,
        kind=kind,
        total_duration_seconds=0,
        total_duration_hours=0.0,
        average_state_duration_hours=0.0,
        state_durations={},
        transitions=[],
    )


async def _resolve_label_ids(
    label_refs: list[str],
    label_service: LabelService,
) -> list[str]:
    label_ids: list[str] = []
    for label_ref in label_refs:
        label_obj = await label_service.get_label(label_ref)
        if label_obj is None:
            label_obj = await label_service.get_label_by_name(label_ref)
        if label_obj is None:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown label '{label_ref}'",
            )
        label_ids.append(label_obj.id)
    return label_ids


async def _label_filter_allows(
    *,
    label_service: LabelService,
    entity_type: str,
    entity_id: str,
    label_ids: list[str] | None,
) -> bool:
    if not label_ids:
        return True
    labels = await label_service.list_entity_labels(entity_type, entity_id)
    assigned_ids = {label.id for label in labels}
    return bool(assigned_ids.intersection(label_ids))


@router.get(
    "/transitions/workflow/{entity_type}/{entity_id}",
    response_model=TransitionTimelineResponse,
)
async def get_workflow_timeline(
    entity_type: str,
    entity_id: str,
    triggered_by: str | None = None,
    from_state: str | None = None,
    to_state: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    transition_type: str | None = None,
    label: list[str] | None = None,
    db: Database = Depends(get_db),
    label_service: LabelService = Depends(get_label_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.WORKFLOWS_READ)),
) -> TransitionTimelineResponse:
    """Get workflow transition timeline for an entity."""
    normalized = _validate_entity_type(entity_type)
    if transition_type and transition_type != "workflow":
        return _empty_timeline(
            entity_type=normalized, entity_id=entity_id, kind="workflow"
        )
    label_ids = await _resolve_label_ids(label, label_service) if label else None
    if not await _label_filter_allows(
        label_service=label_service,
        entity_type=normalized,
        entity_id=entity_id,
        label_ids=label_ids,
    ):
        return _empty_timeline(
            entity_type=normalized, entity_id=entity_id, kind="workflow"
        )
    repo = StateTransitionRepository(db)
    timeline = await repo.get_timeline_for_kind(
        normalized,
        entity_id,
        kind="workflow",
        triggered_by=triggered_by,
        from_state=from_state,
        to_state=to_state,
        start_time=start_time,
        end_time=end_time,
        transition_kind=transition_type,
    )
    return _timeline_to_response(
        entity_type=normalized, kind="workflow", timeline=timeline
    )


@router.get(
    "/transitions/status/{entity_type}/{entity_id}",
    response_model=TransitionTimelineResponse,
)
async def get_status_timeline(
    entity_type: str,
    entity_id: str,
    triggered_by: str | None = None,
    from_state: str | None = None,
    to_state: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    transition_type: str | None = None,
    label: list[str] | None = None,
    db: Database = Depends(get_db),
    label_service: LabelService = Depends(get_label_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.WORKFLOWS_READ)),
) -> TransitionTimelineResponse:
    """Get status transition timeline for an entity."""
    normalized = _validate_entity_type(entity_type)
    if transition_type and transition_type != "status":
        return _empty_timeline(
            entity_type=normalized, entity_id=entity_id, kind="status"
        )
    label_ids = await _resolve_label_ids(label, label_service) if label else None
    if not await _label_filter_allows(
        label_service=label_service,
        entity_type=normalized,
        entity_id=entity_id,
        label_ids=label_ids,
    ):
        return _empty_timeline(
            entity_type=normalized, entity_id=entity_id, kind="status"
        )
    repo = StateTransitionRepository(db)
    timeline = await repo.get_timeline_for_kind(
        normalized,
        entity_id,
        kind="status",
        triggered_by=triggered_by,
        from_state=from_state,
        to_state=to_state,
        start_time=start_time,
        end_time=end_time,
        transition_kind=transition_type,
    )
    return _timeline_to_response(
        entity_type=normalized, kind="status", timeline=timeline
    )
