"""API tests for workflow endpoints."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_workflow_show_endpoint(api_client) -> None:
    resp = await api_client.get("/api/v1/workflows/sdlc", params={"view": "overview"})
    resp.raise_for_status()
    data = resp.json()
    assert data["id"] == "wf_sdlc"
    assert data["states_count"] > 0
