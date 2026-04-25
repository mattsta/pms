"""API routes for automation rules."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from pms.api.auth import Scopes, require_scope
from pms.api.dependencies import get_automation_rule_service
from pms.api.models import (
    AutomationRuleCreate,
    AutomationRuleListResponse,
    AutomationRuleResponse,
    AutomationRuleRunListResponse,
    AutomationRuleRunRequest,
    AutomationRuleRunResponse,
    AutomationRuleUpdate,
)
from pms.api.routes.discoverability import (
    QueryParamMap,
    build_query_path,
    next_page_path,
    normalize_next_steps,
    paginated_links,
)
from pms.api.types import JsonObject
from pms.core.automation_action_contract import validate_automation_action_type
from pms.exceptions import ValidationError
from pms.models.api_key import ApiKey
from pms.models.automation_rule import AutomationRule, AutomationRuleRun
from pms.services.automation_rule_service import AutomationRuleService

router = APIRouter()


def _rule_response(rule: AutomationRule) -> AutomationRuleResponse:
    return AutomationRuleResponse(
        id=rule.id,
        name=rule.name,
        description=rule.description,
        event_pattern=rule.event_pattern,
        aggregate_type=rule.aggregate_type,
        aggregate_id=rule.aggregate_id,
        action_type=rule.action_type.value,
        action_payload=rule.action_payload,
        enabled=rule.enabled,
        cooldown_seconds=rule.cooldown_seconds,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
        archived_at=rule.archived_at,
    )


def _run_response(run: AutomationRuleRun) -> AutomationRuleRunResponse:
    return AutomationRuleRunResponse(
        id=run.id,
        rule_id=run.rule_id,
        event_id=run.event_id,
        status=run.status,
        started_at=run.started_at,
        completed_at=run.completed_at,
        error=run.error,
        output=run.output,
    )


@router.post(
    "/automation/rules", response_model=AutomationRuleResponse, status_code=201
)
async def create_automation_rule(
    data: AutomationRuleCreate,
    service: AutomationRuleService = Depends(get_automation_rule_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.AUTOMATION_WRITE)),
) -> AutomationRuleResponse:
    """Create an automation rule."""
    action_type = validate_automation_action_type(data.action_type)
    try:
        rule = await service.create_rule(
            name=data.name,
            description=data.description,
            event_pattern=data.event_pattern,
            aggregate_type=data.aggregate_type,
            aggregate_id=data.aggregate_id,
            action_type=action_type,
            action_payload=data.action_payload,
            enabled=data.enabled,
            cooldown_seconds=data.cooldown_seconds,
        )
    except ValidationError:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _rule_response(rule)


@router.get("/automation/rules", response_model=AutomationRuleListResponse)
async def list_automation_rules(
    include_archived: bool = False,
    enabled: bool | None = None,
    limit: int = 100,
    offset: int = 0,
    service: AutomationRuleService = Depends(get_automation_rule_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.AUTOMATION_READ)),
) -> AutomationRuleListResponse:
    """List automation rules."""
    if limit < 0 or offset < 0:
        raise HTTPException(status_code=400, detail="limit and offset must be >= 0")

    rules = await service.list_rules(
        include_archived=include_archived,
        enabled=enabled,
    )
    total_count = len(rules)
    page_items = rules[offset:]
    if limit > 0:
        page_items = page_items[:limit]

    params: QueryParamMap = {
        "include_archived": include_archived,
        "enabled": enabled,
        "limit": limit,
        "offset": offset,
    }
    self_path = build_query_path("/api/v1/automation/rules", params)
    next_path = next_page_path(
        path="/api/v1/automation/rules",
        params=params,
        total_count=total_count,
        offset=offset,
        limit=limit,
    )
    links: JsonObject = paginated_links(self_path=self_path, next_path=next_path)
    links["runs_template"] = "/api/v1/automation/rules/{rule_id}/runs"
    next_steps = normalize_next_steps(
        "GET /api/v1/automation/rules/{rule_id}",
        "POST /api/v1/automation/run",
        "GET /api/v1/automation/rules/{rule_id}/runs",
    )

    return AutomationRuleListResponse(
        items=[_rule_response(rule) for rule in page_items],
        total_count=total_count,
        offset=offset,
        limit=limit,
        links=links,
        next_steps=next_steps,
        params=params,
    )


@router.get("/automation/rules/{rule_id}", response_model=AutomationRuleResponse)
async def get_automation_rule(
    rule_id: str,
    service: AutomationRuleService = Depends(get_automation_rule_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.AUTOMATION_READ)),
) -> AutomationRuleResponse:
    """Get an automation rule by ID."""
    rule = await service.get_rule(rule_id, include_archived=True)
    if rule is None:
        raise HTTPException(status_code=404, detail="Automation rule not found")
    return _rule_response(rule)


@router.patch("/automation/rules/{rule_id}", response_model=AutomationRuleResponse)
async def update_automation_rule(
    rule_id: str,
    data: AutomationRuleUpdate,
    service: AutomationRuleService = Depends(get_automation_rule_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.AUTOMATION_WRITE)),
) -> AutomationRuleResponse:
    """Update an automation rule."""
    action_type = None
    if data.action_type is not None:
        action_type = validate_automation_action_type(data.action_type)
    try:
        rule = await service.update_rule(
            rule_id,
            name=data.name,
            description=data.description,
            event_pattern=data.event_pattern,
            aggregate_type=data.aggregate_type,
            aggregate_id=data.aggregate_id,
            action_type=action_type,
            action_payload=data.action_payload,
            enabled=data.enabled,
            cooldown_seconds=data.cooldown_seconds,
        )
    except ValidationError:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if rule is None:
        raise HTTPException(status_code=404, detail="Automation rule not found")
    return _rule_response(rule)


@router.delete("/automation/rules/{rule_id}")
async def delete_automation_rule(
    rule_id: str,
    service: AutomationRuleService = Depends(get_automation_rule_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.AUTOMATION_DELETE)),
) -> dict[str, str]:
    """Archive an automation rule."""
    deleted = await service.delete_rule(rule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Automation rule not found")
    return {"status": "deleted", "rule_id": rule_id}


@router.post(
    "/automation/rules/{rule_id}/restore", response_model=AutomationRuleResponse
)
async def restore_automation_rule(
    rule_id: str,
    service: AutomationRuleService = Depends(get_automation_rule_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.AUTOMATION_WRITE)),
) -> AutomationRuleResponse:
    """Restore an automation rule."""
    rule = await service.restore_rule(rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Automation rule not found")
    return _rule_response(rule)


@router.post("/automation/run", response_model=list[AutomationRuleRunResponse])
async def run_automation_rules(
    data: AutomationRuleRunRequest,
    service: AutomationRuleService = Depends(get_automation_rule_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.AUTOMATION_WRITE)),
) -> list[AutomationRuleRunResponse]:
    """Run automation rules for an event."""
    try:
        results = await service.run_for_event_id(
            data.event_id,
            rule_id=data.rule_id,
            dry_run=data.dry_run,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [_run_response(result.run) for result in results]


@router.get(
    "/automation/rules/{rule_id}/runs",
    response_model=AutomationRuleRunListResponse,
)
async def list_automation_rule_runs(
    rule_id: str,
    limit: int = 100,
    offset: int = 0,
    service: AutomationRuleService = Depends(get_automation_rule_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.AUTOMATION_READ)),
) -> AutomationRuleRunListResponse:
    """List run history for an automation rule."""
    page = await service.list_runs(rule_id, limit=limit, offset=offset)
    params: QueryParamMap = {
        "limit": limit,
        "offset": offset,
    }
    runs_path = f"/api/v1/automation/rules/{rule_id}/runs"
    self_path = build_query_path(runs_path, params)
    next_path = next_page_path(
        path=runs_path,
        params=params,
        total_count=page.total_count,
        offset=page.offset,
        limit=page.limit,
    )
    links: JsonObject = paginated_links(self_path=self_path, next_path=next_path)
    links["rule"] = f"/api/v1/automation/rules/{rule_id}"
    next_steps = normalize_next_steps(
        f"GET /api/v1/automation/rules/{rule_id}",
        "POST /api/v1/automation/run",
        "GET /api/v1/automation/rules",
    )
    return AutomationRuleRunListResponse(
        items=[_run_response(run) for run in page.items],
        total_count=page.total_count,
        offset=page.offset,
        limit=page.limit,
        links=links,
        next_steps=next_steps,
        params={"rule_id": rule_id, **params},
    )
