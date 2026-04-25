"""API tests for work snapshots."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_work_snapshot_endpoints(api_client) -> None:
    project_resp = await api_client.post(
        "/api/v1/projects",
        json={"name": "Snapshot Project"},
    )
    project_resp.raise_for_status()
    project_id = project_resp.json()["id"]

    task_resp = await api_client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Snapshot Task"},
    )
    task_resp.raise_for_status()

    snapshot_resp = await api_client.get(f"/api/v1/work-snapshots/project/{project_id}")
    snapshot_resp.raise_for_status()
    snapshot = snapshot_resp.json()
    assert snapshot["scope_type"] == "project"
    assert snapshot["scope_id"] == project_id
    assert snapshot["totals"]["total_tasks"] == 1
    assert snapshot["totals"]["risk_level"] in {None, "low", "medium", "high"}
    assert snapshot["recent_tasks"]
    assert "evidence_gate" in snapshot["recent_tasks"][0]
    assert snapshot["links"]["guide"] == "/api/v1/"
    assert (
        snapshot["links"]["daily"]
        == f"/api/v1/work-snapshots/project/{project_id}/daily"
    )
    assert isinstance(snapshot["next_steps"], list)
    assert snapshot["next_steps"]
    assert snapshot["params"]["include_history"] is True
    assert snapshot["review_history_preview"] == []

    review_resp = await api_client.post(
        f"/api/v1/work-snapshots/project/{project_id}/review",
        json={"reviewed_by": "tester", "note": "First review"},
    )
    review_resp.raise_for_status()
    review = review_resp.json()
    assert review["scope_id"] == project_id
    assert review["reviewed_by"] == "tester"
    assert review["links"]["snapshot"] == f"/api/v1/work-snapshots/project/{project_id}"
    assert isinstance(review["next_steps"], list)
    assert review["next_steps"]

    snapshot_resp = await api_client.get(f"/api/v1/work-snapshots/project/{project_id}")
    snapshot_resp.raise_for_status()
    snapshot = snapshot_resp.json()
    assert snapshot["last_reviewed_at"] is not None
    assert snapshot["review_history_preview"]
    assert snapshot["review_history_preview"][0]["reviewed_by"] == "tester"


@pytest.mark.asyncio
async def test_work_daily_endpoint(api_client) -> None:
    project_resp = await api_client.post(
        "/api/v1/projects",
        json={"name": "Daily Snapshot Project"},
    )
    project_resp.raise_for_status()
    project_id = project_resp.json()["id"]

    task_resp = await api_client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Daily Task"},
    )
    task_resp.raise_for_status()

    daily_resp = await api_client.get(
        f"/api/v1/work-snapshots/project/{project_id}/daily",
        params={"view": "overview"},
    )
    daily_resp.raise_for_status()
    payload = daily_resp.json()
    assert "snapshot" in payload
    assert payload["snapshot"]["scope_id"] == project_id
    assert "queues" in payload
    assert (
        payload["api_links"]["snapshot"]
        == f"/api/v1/work-snapshots/project/{project_id}"
    )
    assert isinstance(payload["next_steps_api"], list)
    assert payload["next_steps_api"]


@pytest.mark.asyncio
async def test_work_snapshot_portfolio_scope(api_client) -> None:
    project_resp = await api_client.post(
        "/api/v1/projects",
        json={"name": "Portfolio Snapshot Project"},
    )
    project_resp.raise_for_status()
    project_id = project_resp.json()["id"]

    task_resp = await api_client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Portfolio Snapshot Task"},
    )
    task_resp.raise_for_status()

    portfolio_resp = await api_client.post(
        "/api/v1/portfolios",
        json={"name": "Snapshot Portfolio"},
    )
    portfolio_resp.raise_for_status()
    portfolio_id = portfolio_resp.json()["id"]

    update_resp = await api_client.patch(
        f"/api/v1/portfolios/{portfolio_id}",
        json={"project_ids": [project_id]},
    )
    update_resp.raise_for_status()

    snapshot_resp = await api_client.get(
        f"/api/v1/work-snapshots/portfolio/{portfolio_id}"
    )
    snapshot_resp.raise_for_status()
    snapshot = snapshot_resp.json()
    assert snapshot["scope_type"] == "portfolio"
    assert snapshot["scope_id"] == portfolio_id
    assert snapshot["totals"]["total_projects"] == 1
    assert snapshot["totals"]["risk_level"] in {None, "low", "medium", "high"}
    assert snapshot["recent_tasks"]
