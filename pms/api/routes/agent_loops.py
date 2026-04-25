"""API routes for agent loops."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from pms.api.auth import Scopes, require_scope
from pms.api.dependencies import get_agent_loop_service
from pms.api.models import (
    AgentLoopListResponse,
    AgentLoopMessageResponse,
    AgentLoopMessagesResponse,
    AgentLoopSummaryResponse,
)
from pms.api.routes.discoverability import (
    QueryParamMap,
    build_query_path,
    next_page_path,
    normalize_next_steps,
    paginated_links,
)
from pms.api.types import JsonObject
from pms.models.api_key import ApiKey
from pms.services.agent_loop_service import AgentLoopService, LoopSummary
from pms.utils.money import monetary_string

router = APIRouter()


def _summary_to_response(summary: LoopSummary) -> AgentLoopSummaryResponse:
    return AgentLoopSummaryResponse(
        id=summary.session_id,
        agent=summary.agent,
        status=summary.status,
        iterations=summary.iterations,
        max_iterations=summary.max_iterations,
        max_runtime_seconds=summary.max_runtime_seconds,
        stop_reason=summary.stop_reason,
        created_at=summary.created_at,
        updated_at=summary.updated_at,
        ended_at=summary.ended_at,
        last_prompt=summary.last_prompt,
        last_response_summary=summary.last_response_summary,
    )


@router.get("/agent-loops", response_model=AgentLoopListResponse)
async def list_agent_loops(
    project_id: str | None = None,
    include_ended: bool = False,
    limit: int = 100,
    offset: int = 0,
    service: AgentLoopService = Depends(get_agent_loop_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.AGENT_LOOPS_READ)),
) -> AgentLoopListResponse:
    """List agent loops."""
    if limit < 0 or offset < 0:
        raise HTTPException(status_code=400, detail="limit and offset must be >= 0")

    loops = await service.list_loops(
        project_id=project_id,
        include_ended=include_ended,
    )
    total_count = len(loops)
    page_items = loops[offset:]
    if limit > 0:
        page_items = page_items[:limit]

    params: QueryParamMap = {
        "project_id": project_id,
        "include_ended": include_ended,
        "limit": limit,
        "offset": offset,
    }
    self_path = build_query_path("/api/v1/agent-loops", params)
    next_path = next_page_path(
        path="/api/v1/agent-loops",
        params=params,
        total_count=total_count,
        offset=offset,
        limit=limit,
    )
    links: JsonObject = paginated_links(self_path=self_path, next_path=next_path)
    links["messages_template"] = "/api/v1/agent-loops/{loop_id}/messages"
    next_steps = normalize_next_steps(
        "GET /api/v1/agent-loops/{loop_id}",
        "GET /api/v1/agent-loops/{loop_id}/messages",
        "POST /api/v1/agent-loops/{loop_id}/cancel",
    )

    return AgentLoopListResponse(
        items=[_summary_to_response(loop) for loop in page_items],
        total_count=total_count,
        offset=offset,
        limit=limit,
        links=links,
        next_steps=next_steps,
        params=params,
    )


@router.get("/agent-loops/{loop_id}", response_model=AgentLoopSummaryResponse)
async def get_agent_loop(
    loop_id: str,
    service: AgentLoopService = Depends(get_agent_loop_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.AGENT_LOOPS_READ)),
) -> AgentLoopSummaryResponse:
    """Get an agent loop summary."""
    loop = await service.get_loop(loop_id)
    if loop is None:
        raise HTTPException(status_code=404, detail="Agent loop not found")
    return _summary_to_response(loop)


@router.get("/agent-loops/{loop_id}/messages", response_model=AgentLoopMessagesResponse)
async def get_agent_loop_messages(
    loop_id: str,
    limit: int = 200,
    offset: int = 0,
    service: AgentLoopService = Depends(get_agent_loop_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.AGENT_LOOPS_READ)),
) -> AgentLoopMessagesResponse:
    """Get messages for an agent loop."""
    if limit < 0 or offset < 0:
        raise HTTPException(status_code=400, detail="limit and offset must be >= 0")

    loop = await service.get_loop(loop_id)
    if loop is None:
        raise HTTPException(status_code=404, detail="Agent loop not found")
    messages = await service.get_loop_messages(loop_id)
    total_count = len(messages)
    page_items = messages[offset:]
    if limit > 0:
        page_items = page_items[:limit]

    params: QueryParamMap = {
        "limit": limit,
        "offset": offset,
    }
    messages_path = f"/api/v1/agent-loops/{loop_id}/messages"
    self_path = build_query_path(messages_path, params)
    next_path = next_page_path(
        path=messages_path,
        params=params,
        total_count=total_count,
        offset=offset,
        limit=limit,
    )
    links: JsonObject = paginated_links(self_path=self_path, next_path=next_path)
    links["loop"] = f"/api/v1/agent-loops/{loop_id}"
    next_steps = normalize_next_steps(
        f"GET /api/v1/agent-loops/{loop_id}",
        f"POST /api/v1/agent-loops/{loop_id}/cancel",
        "GET /api/v1/agent-loops",
    )
    return AgentLoopMessagesResponse(
        items=[
            AgentLoopMessageResponse(
                id=item["id"],
                session_id=item["session_id"],
                role=item["role"],
                content=item["content"],
                tokens=item.get("tokens"),
                cost_usd=monetary_string(item.get("cost_usd")),
                timestamp=item["timestamp"],
                metadata=item.get("metadata", {}),
            )
            for item in page_items
        ],
        total_count=total_count,
        offset=offset,
        limit=limit,
        links=links,
        next_steps=next_steps,
        params={"loop_id": loop_id, **params},
    )


@router.post("/agent-loops/{loop_id}/cancel", response_model=AgentLoopSummaryResponse)
async def cancel_agent_loop(
    loop_id: str,
    service: AgentLoopService = Depends(get_agent_loop_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.AGENT_LOOPS_WRITE)),
) -> AgentLoopSummaryResponse:
    """Request cancellation for an agent loop."""
    session = await service.cancel_loop(loop_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Agent loop not found")
    summary = await service.get_loop(loop_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Agent loop not found")
    return _summary_to_response(summary)
