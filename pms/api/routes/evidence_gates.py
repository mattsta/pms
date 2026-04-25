"""API routes for evidence gate rules."""

from __future__ import annotations

from typing import TypedDict

from fastapi import APIRouter, Depends, HTTPException

from pms.api.auth import Scopes, require_scope
from pms.api.dependencies import get_evidence_gate_service
from pms.api.models import EvidenceGateRuleCreate, EvidenceGateRuleResponse
from pms.models.api_key import ApiKey
from pms.services.evidence_gate_service import EvidenceGateService

router = APIRouter()


class DeleteEvidenceGateRuleResponse(TypedDict):
    """Delete response payload for evidence gate rules."""

    status: str
    id: str


@router.post(
    "/evidence/gates", response_model=EvidenceGateRuleResponse, status_code=201
)
async def create_evidence_gate_rule(
    data: EvidenceGateRuleCreate,
    service: EvidenceGateService = Depends(get_evidence_gate_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.WORKFLOWS_WRITE)),
) -> EvidenceGateRuleResponse:
    """Create an evidence gate rule."""
    try:
        rule = await service.add_gate_rule(
            workflow_id=data.workflow_id,
            entity_type=data.entity_type,
            from_state=data.from_state,
            to_state=data.to_state,
            evidence_type=data.evidence_type,
            min_count=data.min_count,
            require_success=data.require_success,
            message=data.message,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return EvidenceGateRuleResponse(
        id=rule.id,
        workflow_id=rule.workflow_id,
        entity_type=rule.entity_type,
        from_state=rule.from_state,
        to_state=rule.to_state,
        evidence_type=rule.evidence_type,
        min_count=rule.min_count,
        require_success=rule.require_success,
        message=rule.message,
        created_at=rule.created_at,
    )


@router.get("/evidence/gates", response_model=list[EvidenceGateRuleResponse])
async def list_evidence_gate_rules(
    workflow_id: str,
    entity_type: str,
    from_state: str,
    to_state: str,
    service: EvidenceGateService = Depends(get_evidence_gate_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.WORKFLOWS_READ)),
) -> list[EvidenceGateRuleResponse]:
    """List evidence gate rules for a workflow transition."""
    try:
        rules = await service.list_gate_rules(
            workflow_id=workflow_id,
            entity_type=entity_type,
            from_state=from_state,
            to_state=to_state,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [
        EvidenceGateRuleResponse(
            id=rule.id,
            workflow_id=rule.workflow_id,
            entity_type=rule.entity_type,
            from_state=rule.from_state,
            to_state=rule.to_state,
            evidence_type=rule.evidence_type,
            min_count=rule.min_count,
            require_success=rule.require_success,
            message=rule.message,
            created_at=rule.created_at,
        )
        for rule in rules
    ]


@router.delete("/evidence/gates/{rule_id}")
async def delete_evidence_gate_rule(
    rule_id: str,
    service: EvidenceGateService = Depends(get_evidence_gate_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.WORKFLOWS_WRITE)),
) -> DeleteEvidenceGateRuleResponse:
    """Delete an evidence gate rule."""
    await service.remove_gate_rule(rule_id)
    return {"status": "deleted", "id": rule_id}
