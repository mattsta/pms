"""API tests for aggregate dashboard endpoints."""

import pytest


def _project_item(items: list[dict[str, object]], project_id: str) -> dict[str, object]:
    for item in items:
        if item.get("id") == project_id:
            return item
    raise AssertionError(f"Project {project_id} not found in payload")


@pytest.mark.asyncio
async def test_api_dashboard_exposes_instance_lifecycle_rollups(api_client):
    """The API dashboard should expose active and recent terminal project rollups."""
    active_project = await api_client.post(
        "/api/v1/projects",
        json={"name": "API Dashboard Active Project"},
    )
    active_project.raise_for_status()
    active_project_id = active_project.json()["id"]

    active_task = await api_client.post(
        "/api/v1/tasks",
        json={"project_id": active_project_id, "title": "API Dashboard Active Task"},
    )
    active_task.raise_for_status()
    active_task_id = active_task.json()["id"]
    start_active = await api_client.post(f"/api/v1/tasks/{active_task_id}/start")
    start_active.raise_for_status()

    terminal_project = await api_client.post(
        "/api/v1/projects",
        json={"name": "API Dashboard Terminal Project"},
    )
    terminal_project.raise_for_status()
    terminal_project_id = terminal_project.json()["id"]

    terminal_task = await api_client.post(
        "/api/v1/tasks",
        json={
            "project_id": terminal_project_id,
            "title": "API Dashboard Terminal Task",
        },
    )
    terminal_task.raise_for_status()
    terminal_task_id = terminal_task.json()["id"]
    await api_client.post(f"/api/v1/tasks/{terminal_task_id}/start")
    await api_client.post(f"/api/v1/tasks/{terminal_task_id}/complete")
    draft_plan = await api_client.post(
        "/api/v1/plans",
        json={
            "name": "API Dashboard Draft Residue Plan",
            "status": "draft",
            "format": "json",
            "content": {"steps": ["residual planning only"]},
            "project_id": terminal_project_id,
        },
    )
    draft_plan.raise_for_status()
    complete_terminal_project = await api_client.patch(
        f"/api/v1/projects/{terminal_project_id}",
        json={"status": "completed"},
    )
    complete_terminal_project.raise_for_status()

    response = await api_client.get("/api/v1/dashboard")
    response.raise_for_status()
    payload = response.json()

    assert payload["scope"]["kind"] == "instance_dashboard"
    assert payload["scope"]["population"] == "all_non_archived_retained"
    assert payload["scope"]["active_visible_projects"] == 1
    assert payload["scope"]["recently_completed_projects"] >= 1
    assert payload["totals"]["total_projects"] >= 2
    assert payload["totals"]["total_tasks"] >= 2
    assert payload["links"]["self"] == "/api/v1/dashboard"
    assert payload["links"]["dashboard_ui"] == "/dashboard"
    assert "GET /api/v1/projects" in payload["next_steps"]

    active_item = _project_item(payload["active_projects"], active_project_id)
    assert active_item["status"] == "active"
    assert active_item["stored_status"] == "active"
    assert active_item["terminal_reason"] is None
    assert active_item["last_activity_at"] is not None
    assert active_item["last_transition_at"] is not None
    assert active_item["links"]["self"].endswith(
        f"/api/v1/projects/{active_project_id}"
    )

    terminal_item = _project_item(
        payload["recently_completed_projects"],
        terminal_project_id,
    )
    assert terminal_item["status"] == "completed"
    assert terminal_item["stored_status"] == "completed"
    assert terminal_item["terminal_reason"] == (
        "all linked execution scopes are already terminal"
    )
    assert terminal_item["last_activity_at"] is not None
    assert terminal_item["last_transition_at"] is not None
    assert payload["completion_context"]["items"][0]["id"] == terminal_item["id"]
    assert payload["terminal_reason"] is None


@pytest.mark.asyncio
async def test_api_dashboard_reports_terminal_reason_when_all_projects_are_terminal(
    api_client,
):
    """The API dashboard should report terminal context when no active work remains."""
    project = await api_client.post(
        "/api/v1/projects",
        json={"name": "API Dashboard Completed Project"},
    )
    project.raise_for_status()
    project_id = project.json()["id"]

    task = await api_client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "API Dashboard Completed Task"},
    )
    task.raise_for_status()
    task_id = task.json()["id"]
    await api_client.post(f"/api/v1/tasks/{task_id}/start")
    await api_client.post(f"/api/v1/tasks/{task_id}/complete")
    await api_client.patch(
        f"/api/v1/projects/{project_id}",
        json={"status": "completed"},
    )

    response = await api_client.get("/api/v1/dashboard")
    response.raise_for_status()
    payload = response.json()

    assert payload["active_projects"] == []
    assert payload["terminal_reason"] == "all surfaced projects are already terminal"
    completed_item = _project_item(payload["recently_completed_projects"], project_id)
    assert completed_item["status"] == "completed"
    assert completed_item["terminal_reason"] == (
        "all linked execution scopes are already terminal"
    )
    assert (
        "No other visible active work is currently surfaced"
        in payload["completion_context"]["summary"]
    )
