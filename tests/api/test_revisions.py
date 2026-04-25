"""API tests for revision diff."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_revision_diff_endpoint(api_client) -> None:
    project_resp = await api_client.post(
        "/api/v1/projects",
        json={"name": "Revision Diff Project"},
    )
    project_resp.raise_for_status()
    project_id = project_resp.json()["id"]

    update_resp = await api_client.patch(
        f"/api/v1/projects/{project_id}",
        json={"name": "Revision Diff Project v2"},
    )
    update_resp.raise_for_status()

    diff_resp = await api_client.get(
        f"/api/v1/revisions/project/{project_id}/diff",
        params={"from_revision": 1, "to_revision": 2},
    )
    diff_resp.raise_for_status()
    payload = diff_resp.json()
    assert payload["entity_id"] == project_id
    assert payload["from_revision"] == 1
    assert payload["to_revision"] == 2
    assert any(change["field_name"] == "name" for change in payload["changes"])


@pytest.mark.asyncio
async def test_revision_history_bundle_endpoint(api_client) -> None:
    project_resp = await api_client.post(
        "/api/v1/projects",
        json={"name": "Revision Bundle Project"},
    )
    project_resp.raise_for_status()
    project_id = project_resp.json()["id"]

    task_resp = await api_client.post(
        "/api/v1/tasks",
        json={"title": "Bundle Task", "project_id": project_id},
    )
    task_resp.raise_for_status()
    task_id = task_resp.json()["id"]

    update_resp = await api_client.patch(
        f"/api/v1/projects/{project_id}",
        json={"description": "Updated description"},
    )
    update_resp.raise_for_status()

    bundle_resp = await api_client.get(
        f"/api/v1/revisions/project/{project_id}/bundle",
        params={
            "include_linked": True,
            "include_linked_history": True,
            "history_limit": 10,
            "linked_limit": 10,
        },
    )
    bundle_resp.raise_for_status()
    payload = bundle_resp.json()
    assert payload["entity_id"] == project_id
    assert payload["history"]["page"]["total_count"] >= 2
    linked_tasks = payload.get("linked", {}).get("tasks", [])
    assert any(task["id"] == task_id for task in linked_tasks)
