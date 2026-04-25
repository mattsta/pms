"""Label API routes."""

from __future__ import annotations

from datetime import datetime
from typing import TypedDict

from fastapi import APIRouter, Depends, HTTPException, Query

from pms.api.auth import Scopes, require_scope
from pms.api.dependencies import get_label_service
from pms.api.models import (
    LabelAssignmentCreate,
    LabelAssignmentResponse,
    LabelCategoryCreate,
    LabelCategoryResponse,
    LabelCategoryUpdate,
    LabelCreate,
    LabelGateRuleCreate,
    LabelGateRuleResponse,
    LabelResponse,
    LabelUpdate,
)
from pms.api.types import JsonObject
from pms.models.api_key import ApiKey
from pms.models.label_gate_rule import LabelGateRuleType
from pms.services.label_service import LabelService

router = APIRouter()


class LabelAssignmentInfoPayload(TypedDict):
    """Label assignment metadata payload."""

    id: str
    entity_type: str
    entity_id: str
    label_id: str
    applied_by: str | None
    applied_at: datetime
    created_at: datetime
    updated_at: datetime


class LabelAssignmentListItemPayload(TypedDict):
    """Label with label-assignment metadata."""

    id: str
    name: str
    description: str | None
    category_id: str | None
    color: str | None
    is_system: bool
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None
    assignment: LabelAssignmentInfoPayload


class LabelAssignmentsPagePayload(TypedDict):
    """Pagination metadata for label assignments."""

    total_count: int
    limit: int
    offset: int
    has_more: bool
    next_offset: int | None


class LabelAssignmentsResponsePayload(TypedDict):
    """Label assignments response payload."""

    items: list[LabelAssignmentListItemPayload]
    page: LabelAssignmentsPagePayload


class LabelAssignmentHistoryResponsePayload(TypedDict):
    """Label assignment history response payload."""

    assignment: LabelAssignmentInfoPayload
    items: list[JsonObject]
    page: LabelAssignmentsPagePayload


@router.post(
    "/labels/categories", response_model=LabelCategoryResponse, status_code=201
)
async def create_label_category(
    data: LabelCategoryCreate,
    service: LabelService = Depends(get_label_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.LABELS_WRITE)),
) -> LabelCategoryResponse:
    """Create a label category."""
    category = await service.create_category(
        name=data.name,
        description=data.description,
        is_exclusive=data.is_exclusive,
        sort_order=data.sort_order,
    )
    return LabelCategoryResponse(
        id=category.id,
        name=category.name,
        description=category.description,
        is_exclusive=category.is_exclusive,
        sort_order=category.sort_order,
        created_at=category.created_at,
        updated_at=category.updated_at,
    )


@router.get("/labels/categories")
async def list_label_categories(
    include_archived: bool = False,
    service: LabelService = Depends(get_label_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.LABELS_READ)),
) -> dict[str, list[LabelCategoryResponse]]:
    """List label categories."""
    categories = await service.list_categories(include_archived=include_archived)
    return {
        "items": [
            LabelCategoryResponse(
                id=category.id,
                name=category.name,
                description=category.description,
                is_exclusive=category.is_exclusive,
                sort_order=category.sort_order,
                created_at=category.created_at,
                updated_at=category.updated_at,
                archived_at=category.archived_at,
            )
            for category in categories
        ]
    }


@router.get("/labels/categories/{category_id}", response_model=LabelCategoryResponse)
async def get_label_category(
    category_id: str,
    service: LabelService = Depends(get_label_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.LABELS_READ)),
) -> LabelCategoryResponse:
    """Get a label category."""
    category = await service.get_category(category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Label category not found")
    return LabelCategoryResponse(
        id=category.id,
        name=category.name,
        description=category.description,
        is_exclusive=category.is_exclusive,
        sort_order=category.sort_order,
        created_at=category.created_at,
        updated_at=category.updated_at,
        archived_at=category.archived_at,
    )


@router.patch("/labels/categories/{category_id}", response_model=LabelCategoryResponse)
async def update_label_category(
    category_id: str,
    data: LabelCategoryUpdate,
    service: LabelService = Depends(get_label_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.LABELS_WRITE)),
) -> LabelCategoryResponse:
    """Update a label category."""
    category = await service.update_category(
        category_id=category_id,
        name=data.name,
        description=data.description,
        is_exclusive=data.is_exclusive,
        sort_order=data.sort_order,
    )
    if category is None:
        raise HTTPException(status_code=404, detail="Label category not found")
    return LabelCategoryResponse(
        id=category.id,
        name=category.name,
        description=category.description,
        is_exclusive=category.is_exclusive,
        sort_order=category.sort_order,
        created_at=category.created_at,
        updated_at=category.updated_at,
        archived_at=category.archived_at,
    )


@router.delete("/labels/categories/{category_id}")
async def delete_label_category(
    category_id: str,
    service: LabelService = Depends(get_label_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.LABELS_DELETE)),
) -> dict[str, str]:
    """Delete a label category."""
    await service.delete_category(category_id)
    return {"status": "deleted", "category_id": category_id}


@router.post("/labels/categories/{category_id}/restore")
async def restore_label_category(
    category_id: str,
    service: LabelService = Depends(get_label_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.LABELS_WRITE)),
) -> LabelCategoryResponse:
    """Restore a label category."""
    category = await service.restore_category(category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Label category not found")
    return LabelCategoryResponse(
        id=category.id,
        name=category.name,
        description=category.description,
        is_exclusive=category.is_exclusive,
        sort_order=category.sort_order,
        created_at=category.created_at,
        updated_at=category.updated_at,
        archived_at=category.archived_at,
    )


@router.post("/labels", response_model=LabelResponse, status_code=201)
async def create_label(
    data: LabelCreate,
    service: LabelService = Depends(get_label_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.LABELS_WRITE)),
) -> LabelResponse:
    """Create a label."""
    label = await service.create_label(
        name=data.name,
        description=data.description,
        category_id=data.category_id,
        color=data.color,
        is_system=data.is_system,
    )
    return LabelResponse(
        id=label.id,
        name=label.name,
        description=label.description,
        category_id=label.category_id,
        color=label.color,
        is_system=label.is_system,
        created_at=label.created_at,
        updated_at=label.updated_at,
    )


@router.get("/labels")
async def list_labels(
    category_id: str | None = None,
    include_archived: bool = False,
    service: LabelService = Depends(get_label_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.LABELS_READ)),
) -> dict[str, list[LabelResponse]]:
    """List labels with optional category filter."""
    labels = await service.list_labels(
        category_id=category_id, include_archived=include_archived
    )
    return {
        "items": [
            LabelResponse(
                id=label.id,
                name=label.name,
                description=label.description,
                category_id=label.category_id,
                color=label.color,
                is_system=label.is_system,
                created_at=label.created_at,
                updated_at=label.updated_at,
                archived_at=label.archived_at,
            )
            for label in labels
        ]
    }


@router.get("/labels/{label_id}", response_model=LabelResponse)
async def get_label(
    label_id: str,
    service: LabelService = Depends(get_label_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.LABELS_READ)),
) -> LabelResponse:
    """Get a label."""
    label = await service.get_label(label_id)
    if label is None:
        raise HTTPException(status_code=404, detail="Label not found")
    return LabelResponse(
        id=label.id,
        name=label.name,
        description=label.description,
        category_id=label.category_id,
        color=label.color,
        is_system=label.is_system,
        created_at=label.created_at,
        updated_at=label.updated_at,
        archived_at=label.archived_at,
    )


@router.patch("/labels/{label_id}", response_model=LabelResponse)
async def update_label(
    label_id: str,
    data: LabelUpdate,
    service: LabelService = Depends(get_label_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.LABELS_WRITE)),
) -> LabelResponse:
    """Update a label."""
    label = await service.update_label(
        label_id=label_id,
        name=data.name,
        description=data.description,
        category_id=data.category_id,
        color=data.color,
        is_system=data.is_system,
    )
    if label is None:
        raise HTTPException(status_code=404, detail="Label not found")
    return LabelResponse(
        id=label.id,
        name=label.name,
        description=label.description,
        category_id=label.category_id,
        color=label.color,
        is_system=label.is_system,
        created_at=label.created_at,
        updated_at=label.updated_at,
        archived_at=label.archived_at,
    )


@router.delete("/labels/{label_id}")
async def delete_label(
    label_id: str,
    service: LabelService = Depends(get_label_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.LABELS_DELETE)),
) -> dict[str, str]:
    """Delete a label."""
    await service.delete_label(label_id)
    return {"status": "deleted", "label_id": label_id}


@router.post("/labels/{label_id}/restore", response_model=LabelResponse)
async def restore_label(
    label_id: str,
    service: LabelService = Depends(get_label_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.LABELS_WRITE)),
) -> LabelResponse:
    """Restore a label."""
    label = await service.restore_label(label_id)
    if label is None:
        raise HTTPException(status_code=404, detail="Label not found")
    return LabelResponse(
        id=label.id,
        name=label.name,
        description=label.description,
        category_id=label.category_id,
        color=label.color,
        is_system=label.is_system,
        created_at=label.created_at,
        updated_at=label.updated_at,
        archived_at=label.archived_at,
    )


@router.post(
    "/labels/assignments",
    response_model=LabelAssignmentResponse,
    status_code=201,
)
async def assign_label(
    data: LabelAssignmentCreate,
    service: LabelService = Depends(get_label_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.LABELS_WRITE)),
) -> LabelAssignmentResponse:
    """Assign a label to an entity."""
    try:
        assignment = await service.assign_label(
            entity_type=data.entity_type,
            entity_id=data.entity_id,
            label_id=data.label_id,
            applied_by=data.applied_by,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return LabelAssignmentResponse(
        id=assignment.id,
        entity_type=assignment.entity_type,
        entity_id=assignment.entity_id,
        label_id=assignment.label_id,
        applied_by=assignment.applied_by,
        applied_at=assignment.applied_at,
    )


@router.get("/labels/assignments")
async def list_label_assignments(
    entity_type: str,
    entity_id: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    service: LabelService = Depends(get_label_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.LABELS_READ)),
) -> LabelAssignmentsResponsePayload:
    """List labels assigned to an entity."""
    try:
        assignments = await service.list_entity_label_assignments(
            entity_type, entity_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    total_count = len(assignments)
    if limit <= 0:
        view_items = assignments[offset:]
    else:
        view_items = assignments[offset : offset + limit]

    items: list[LabelAssignmentListItemPayload] = []
    for assignment, label in view_items:
        assignee_payload: LabelAssignmentInfoPayload = {
            "id": assignment.id,
            "entity_type": assignment.entity_type,
            "entity_id": assignment.entity_id,
            "label_id": assignment.label_id,
            "applied_by": assignment.applied_by,
            "applied_at": assignment.applied_at,
            "created_at": assignment.created_at,
            "updated_at": assignment.updated_at,
        }
        item_payload: LabelAssignmentListItemPayload = {
            "id": label.id,
            "name": label.name,
            "description": label.description,
            "category_id": label.category_id,
            "color": label.color,
            "is_system": label.is_system,
            "created_at": label.created_at,
            "updated_at": label.updated_at,
            "archived_at": label.archived_at,
            "assignment": assignee_payload,
        }
        items.append(item_payload)

    has_more = offset + limit < total_count if limit > 0 else False
    return {
        "items": items,
        "page": {
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
            "has_more": has_more,
            "next_offset": offset + limit if has_more else None,
        },
    }


@router.get("/labels/assignments/{assignment_id}/history")
async def get_label_assignment_history(
    assignment_id: str,
    limit: int = Query(20, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    service: LabelService = Depends(get_label_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.LABELS_READ)),
) -> LabelAssignmentHistoryResponsePayload:
    """Get label assignment revision history."""
    assignment = await service.get_assignment(assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found")

    total_count = await service.get_assignment_history_count(assignment_id)
    history = await service.get_assignment_history(
        assignment_id, limit=limit, offset=offset
    )
    has_more = offset + limit < total_count
    assignee_payload: LabelAssignmentInfoPayload = {
        "id": assignment.id,
        "entity_type": assignment.entity_type,
        "entity_id": assignment.entity_id,
        "label_id": assignment.label_id,
        "applied_by": assignment.applied_by,
        "applied_at": assignment.applied_at,
        "created_at": assignment.created_at,
        "updated_at": assignment.updated_at,
    }
    return {
        "assignment": assignee_payload,
        "items": [
            {
                "revision_id": rev.revision_id,
                "entity_type": rev.entity_type,
                "entity_id": rev.entity_id,
                "revision_number": rev.revision_number,
                "parent_revision_id": rev.parent_revision_id,
                "content": {key: value for key, value in rev.content.items()},
                "content_hash": rev.content_hash,
                "changes": [
                    {
                        "field_name": change.field_name,
                        "old_value": change.old_value,
                        "new_value": change.new_value,
                        "change_type": change.change_type.value,
                    }
                    for change in rev.changes
                ],
                "change_type": rev.change_type.value,
                "created_at": rev.created_at.isoformat(),
                "created_by": rev.created_by,
                "message": rev.message,
                "metadata": dict(rev.metadata),
            }
            for rev in history
        ],
        "page": {
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
            "has_more": has_more,
            "next_offset": offset + limit if has_more else None,
        },
    }


@router.delete("/labels/assignments")
async def remove_label_assignment(
    entity_type: str,
    entity_id: str,
    label_id: str,
    service: LabelService = Depends(get_label_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.LABELS_WRITE)),
) -> dict[str, str]:
    """Remove a label assignment."""
    try:
        await service.remove_label(entity_type, entity_id, label_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "removed", "label_id": label_id}


@router.post("/labels/gates", response_model=LabelGateRuleResponse, status_code=201)
async def create_label_gate_rule(
    data: LabelGateRuleCreate,
    service: LabelService = Depends(get_label_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.LABELS_WRITE)),
) -> LabelGateRuleResponse:
    """Create a label gate rule."""
    try:
        rule_type = LabelGateRuleType(data.rule_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid rule type") from exc

    try:
        rule = await service.add_gate_rule(
            workflow_id=data.workflow_id,
            entity_type=data.entity_type,
            from_state=data.from_state,
            to_state=data.to_state,
            rule_type=rule_type,
            label_id=data.label_id,
            category_id=data.category_id,
            message=data.message,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return LabelGateRuleResponse(
        id=rule.id,
        workflow_id=rule.workflow_id,
        entity_type=rule.entity_type,
        from_state=rule.from_state,
        to_state=rule.to_state,
        rule_type=rule.rule_type.value,
        label_id=rule.label_id,
        category_id=rule.category_id,
        message=rule.message,
        created_at=rule.created_at,
    )


@router.get("/labels/gates")
async def list_label_gate_rules(
    workflow_id: str,
    entity_type: str,
    from_state: str,
    to_state: str,
    service: LabelService = Depends(get_label_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.LABELS_READ)),
) -> dict[str, list[LabelGateRuleResponse]]:
    """List label gate rules for a workflow transition."""
    try:
        rules = await service.list_gate_rules(
            workflow_id=workflow_id,
            entity_type=entity_type,
            from_state=from_state,
            to_state=to_state,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "items": [
            LabelGateRuleResponse(
                id=rule.id,
                workflow_id=rule.workflow_id,
                entity_type=rule.entity_type,
                from_state=rule.from_state,
                to_state=rule.to_state,
                rule_type=rule.rule_type.value,
                label_id=rule.label_id,
                category_id=rule.category_id,
                message=rule.message,
                created_at=rule.created_at,
            )
            for rule in rules
        ]
    }


@router.delete("/labels/gates/{rule_id}")
async def delete_label_gate_rule(
    rule_id: str,
    service: LabelService = Depends(get_label_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.LABELS_DELETE)),
) -> dict[str, str]:
    """Delete a label gate rule."""
    await service.remove_gate_rule(rule_id)
    return {"status": "deleted", "rule_id": rule_id}
