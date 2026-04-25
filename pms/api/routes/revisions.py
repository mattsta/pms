"""Revision diff API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from pms.api.auth import AuthorizationError, Scopes, check_rate_limit, get_api_key
from pms.api.dependencies import get_db, get_history_bundle_service
from pms.api.models import (
    RevisionChangeResponse,
    RevisionDiffResponse,
    RevisionHistoryBundleResponse,
)
from pms.core.revisions import RevisionStore
from pms.db.connection import Database
from pms.models.api_key import ApiKey
from pms.services.history_bundle_service import HistoryBundleService

router = APIRouter()


def _required_scope(entity_type: str) -> str | None:
    match entity_type:
        case "task":
            return Scopes.TASKS_READ
        case "project":
            return Scopes.PROJECTS_READ
        case "plan":
            return Scopes.PLANS_READ
        case "goal" | "objective" | "key_result":
            return Scopes.GOALS_READ
        case "organization":
            return Scopes.ORGS_READ
        case "team":
            return Scopes.TEAMS_READ
        case "portfolio":
            return Scopes.PORTFOLIOS_READ
        case "program":
            return Scopes.PROGRAMS_READ
        case "product":
            return Scopes.PRODUCTS_READ
        case "label" | "label_category" | "label_gate_rule" | "evidence_gate_rule":
            return Scopes.LABELS_READ
        case "automation_rule":
            return Scopes.AUTOMATION_READ
        case "saved_search":
            return Scopes.TASKS_READ
        case "plan_test_job":
            return Scopes.PLANS_READ
        case _:
            return None


async def require_revision_read(
    entity_type: str,
    api_key: ApiKey = Depends(get_api_key),
) -> ApiKey:
    """Require scope-aware read access for revision endpoints."""
    scope = _required_scope(entity_type)
    if scope is None:
        raise HTTPException(
            status_code=400,
            detail="Unsupported entity type for revision endpoint",
        )
    if not api_key.matches_scope(scope):
        raise AuthorizationError(f"Missing required scope: {scope}")
    await check_rate_limit(api_key)
    return api_key


@router.get(
    "/revisions/{entity_type}/{entity_id}/diff",
    response_model=RevisionDiffResponse,
)
async def diff_revisions(
    entity_type: str,
    entity_id: str,
    from_revision: int,
    to_revision: int,
    db: Database = Depends(get_db),
    _api_key: ApiKey = Depends(require_revision_read),
) -> RevisionDiffResponse:
    """Diff two revisions for a specific entity."""
    if from_revision < 1 or to_revision < 1:
        raise HTTPException(status_code=400, detail="Revision numbers must be >= 1")
    if from_revision >= to_revision:
        raise HTTPException(
            status_code=400,
            detail="from_revision must be less than to_revision",
        )

    store = RevisionStore(db)
    total = await store.get_revision_count(entity_type, entity_id)
    if total == 0:
        raise HTTPException(status_code=404, detail="Revisions not found")
    if to_revision > total:
        raise HTTPException(
            status_code=400,
            detail=f"to_revision exceeds latest revision ({total})",
        )

    diff = await store.diff(entity_type, entity_id, from_revision, to_revision)
    return RevisionDiffResponse(
        entity_type=diff.entity_type,
        entity_id=diff.entity_id,
        from_revision=diff.from_revision,
        to_revision=diff.to_revision,
        changes=[
            RevisionChangeResponse(
                field_name=change.field_name,
                old_value=change.old_value,
                new_value=change.new_value,
                change_type=change.change_type.value,
            )
            for change in diff.changes
        ],
        intermediate_revisions=diff.intermediate_revisions,
    )


@router.get(
    "/revisions/{entity_type}/{entity_id}/bundle",
    response_model=RevisionHistoryBundleResponse,
)
async def revision_history_bundle(
    entity_type: str,
    entity_id: str,
    include_linked: bool = False,
    include_linked_history: bool = False,
    history_limit: int = 20,
    history_offset: int = 0,
    linked_limit: int = 20,
    linked_history_limit: int | None = None,
    history_service: HistoryBundleService = Depends(get_history_bundle_service),
    _api_key: ApiKey = Depends(require_revision_read),
) -> RevisionHistoryBundleResponse:
    """Export revision history bundle for an entity and linked items."""
    bundle = await history_service.build_bundle(
        entity_type=entity_type,
        entity_id=entity_id,
        include_linked=include_linked,
        include_linked_history=include_linked_history,
        history_limit=history_limit,
        history_offset=history_offset,
        linked_limit=linked_limit,
        linked_history_limit=linked_history_limit,
    )
    if bundle is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    return RevisionHistoryBundleResponse(**bundle.to_dict())
