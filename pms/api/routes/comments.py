"""Comment and watcher API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from pms.api.auth import Scopes, require_scope
from pms.api.dependencies import get_comment_service
from pms.api.models import (
    CommentCreate,
    CommentListResponse,
    CommentResponse,
    WatcherCreate,
    WatcherListResponse,
    WatcherResponse,
)
from pms.api.routes.discoverability import (
    QueryParamMap,
    build_query_path,
    next_page_path,
    normalize_next_steps,
    paginated_links,
)
from pms.api.types import JsonObject
from pms.core.entity_type_contract import normalize_entity_type
from pms.models.api_key import ApiKey
from pms.models.comment import EntityWatcher
from pms.services.comment_service import CommentItem, CommentService

router = APIRouter()


def _comment_response(item: CommentItem) -> CommentResponse:
    comment = item.comment
    return CommentResponse(
        id=comment.id,
        entity_type=comment.entity_type,
        entity_id=comment.entity_id,
        body=comment.body,
        created_by=comment.created_by,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
        archived_at=comment.archived_at,
        metadata=comment.metadata,
        mentions=[mention.mention for mention in item.mentions],
    )


def _watcher_response(watcher: EntityWatcher) -> WatcherResponse:
    return WatcherResponse(
        id=watcher.id,
        entity_type=watcher.entity_type,
        entity_id=watcher.entity_id,
        watcher=watcher.watcher,
        created_at=watcher.created_at,
        updated_at=watcher.updated_at,
        archived_at=watcher.archived_at,
    )


def _entity_api_path(entity_type: str, entity_id: str) -> str | None:
    normalized = entity_type.strip().lower()
    if normalized == "task":
        return f"/api/v1/tasks/{entity_id}"
    if normalized == "project":
        return f"/api/v1/projects/{entity_id}"
    if normalized == "goal":
        return f"/api/v1/goals/{entity_id}"
    if normalized == "objective":
        return f"/api/v1/objectives/{entity_id}"
    if normalized == "key_result":
        return f"/api/v1/key-results/{entity_id}"
    if normalized == "plan":
        return f"/api/v1/plans/{entity_id}"
    if normalized == "product":
        return f"/api/v1/products/{entity_id}"
    if normalized == "organization":
        return f"/api/v1/organizations/{entity_id}"
    if normalized == "team":
        return f"/api/v1/teams/{entity_id}"
    if normalized == "portfolio":
        return f"/api/v1/portfolios/{entity_id}"
    if normalized == "program":
        return f"/api/v1/programs/{entity_id}"
    return None


@router.post("/comments", response_model=CommentResponse, status_code=201)
async def add_comment(
    data: CommentCreate,
    service: CommentService = Depends(get_comment_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.TASKS_WRITE)),
) -> CommentResponse:
    """Add a comment to an entity."""
    try:
        item = await service.add_comment(
            entity_type=data.entity_type,
            entity_id=data.entity_id,
            body=data.body,
            created_by=data.created_by,
            mentions=data.mentions,
            metadata=data.metadata,
            watch=data.watch,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _comment_response(item)


@router.get("/comments", response_model=CommentListResponse)
async def list_comments(
    entity_type: str,
    entity_id: str,
    include_archived: bool = False,
    limit: int = 100,
    offset: int = 0,
    service: CommentService = Depends(get_comment_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.TASKS_READ)),
) -> CommentListResponse:
    """List comments for an entity."""
    try:
        page = await service.list_comments(
            entity_type=entity_type,
            entity_id=entity_id,
            include_archived=include_archived,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    normalized_type = normalize_entity_type(entity_type)
    params: QueryParamMap = {
        "entity_type": normalized_type,
        "entity_id": entity_id,
        "include_archived": include_archived,
        "limit": limit,
        "offset": offset,
    }
    self_path = build_query_path("/api/v1/comments", params)
    next_path = next_page_path(
        path="/api/v1/comments",
        params=params,
        total_count=page.total_count,
        offset=page.offset,
        limit=page.limit,
    )
    links: JsonObject = paginated_links(self_path=self_path, next_path=next_path)
    links["entity"] = _entity_api_path(normalized_type, entity_id)
    links["watchers"] = build_query_path("/api/v1/watchers", params)
    next_steps = normalize_next_steps(
        "POST /api/v1/comments",
        "GET /api/v1/comments/{comment_id}",
        "GET /api/v1/watchers",
    )

    return CommentListResponse(
        items=[_comment_response(item) for item in page.items],
        total_count=page.total_count,
        offset=page.offset,
        limit=page.limit,
        links=links,
        next_steps=next_steps,
        params=params,
    )


@router.get("/comments/{comment_id}", response_model=CommentResponse)
async def get_comment(
    comment_id: str,
    service: CommentService = Depends(get_comment_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.TASKS_READ)),
) -> CommentResponse:
    """Get a comment by ID."""
    item = await service.get_comment(comment_id, include_archived=True)
    if item is None:
        raise HTTPException(status_code=404, detail="Comment not found")
    return _comment_response(item)


@router.delete("/comments/{comment_id}")
async def delete_comment(
    comment_id: str,
    service: CommentService = Depends(get_comment_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.TASKS_DELETE)),
) -> dict[str, str]:
    """Archive a comment."""
    deleted = await service.delete_comment(comment_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Comment not found")
    return {"status": "deleted", "comment_id": comment_id}


@router.post("/comments/{comment_id}/restore", response_model=CommentResponse)
async def restore_comment(
    comment_id: str,
    service: CommentService = Depends(get_comment_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.TASKS_WRITE)),
) -> CommentResponse:
    """Restore a comment."""
    comment = await service.restore_comment(comment_id)
    if comment is None:
        raise HTTPException(status_code=404, detail="Comment not found")
    item = await service.get_comment(comment_id, include_archived=True)
    if item is None:
        raise HTTPException(status_code=404, detail="Comment not found")
    return _comment_response(item)


@router.post("/watchers", response_model=WatcherResponse, status_code=201)
async def add_watcher(
    data: WatcherCreate,
    service: CommentService = Depends(get_comment_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.TASKS_WRITE)),
) -> WatcherResponse:
    """Add a watcher for an entity."""
    try:
        watcher = await service.add_watcher(
            entity_type=data.entity_type,
            entity_id=data.entity_id,
            watcher=data.watcher,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _watcher_response(watcher)


@router.get("/watchers", response_model=WatcherListResponse)
async def list_watchers(
    entity_type: str,
    entity_id: str,
    include_archived: bool = False,
    limit: int = 100,
    offset: int = 0,
    service: CommentService = Depends(get_comment_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.TASKS_READ)),
) -> WatcherListResponse:
    """List watchers for an entity."""
    try:
        page = await service.list_watchers(
            entity_type=entity_type,
            entity_id=entity_id,
            include_archived=include_archived,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    normalized_type = normalize_entity_type(entity_type)
    params: QueryParamMap = {
        "entity_type": normalized_type,
        "entity_id": entity_id,
        "include_archived": include_archived,
        "limit": limit,
        "offset": offset,
    }
    self_path = build_query_path("/api/v1/watchers", params)
    next_path = next_page_path(
        path="/api/v1/watchers",
        params=params,
        total_count=page.total_count,
        offset=page.offset,
        limit=page.limit,
    )
    links: JsonObject = paginated_links(self_path=self_path, next_path=next_path)
    links["entity"] = _entity_api_path(normalized_type, entity_id)
    links["comments"] = build_query_path("/api/v1/comments", params)
    next_steps = normalize_next_steps(
        "POST /api/v1/watchers",
        "DELETE /api/v1/watchers?entity_type=<entity_type>&entity_id=<entity_id>&watcher=<user>",
        "GET /api/v1/comments",
    )

    return WatcherListResponse(
        items=[_watcher_response(item) for item in page.items],
        total_count=page.total_count,
        offset=page.offset,
        limit=page.limit,
        links=links,
        next_steps=next_steps,
        params=params,
    )


@router.delete("/watchers")
async def remove_watcher(
    entity_type: str,
    entity_id: str,
    watcher: str,
    service: CommentService = Depends(get_comment_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.TASKS_DELETE)),
) -> dict[str, str]:
    """Remove a watcher from an entity."""
    try:
        removed = await service.remove_watcher(entity_type, entity_id, watcher)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not removed:
        raise HTTPException(status_code=404, detail="Watcher not found")
    return {"status": "deleted", "watcher": watcher}


@router.post("/watchers/{watcher_id}/restore", response_model=WatcherResponse)
async def restore_watcher(
    watcher_id: str,
    service: CommentService = Depends(get_comment_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.TASKS_WRITE)),
) -> WatcherResponse:
    """Restore a watcher subscription."""
    watcher = await service.restore_watcher(watcher_id)
    if watcher is None:
        raise HTTPException(status_code=404, detail="Watcher not found")
    return _watcher_response(watcher)
