"""API tests for project endpoints."""

import pytest


def _project_item(items: list[dict[str, object]], project_id: str) -> dict[str, object]:
    for item in items:
        if item.get("id") == project_id:
            return item
    raise AssertionError(f"Project {project_id} not found in payload")


def _assert_project_payload(
    payload: dict[str, object],
    *,
    project_id: str,
    expected_status: str,
    expected_stored_status: str,
    expected_terminal_reason: str | None,
    expected_focus_task_id: str | None,
) -> None:
    assert payload["id"] == project_id
    assert payload["status"] == expected_status
    assert payload["stored_status"] == expected_stored_status
    assert payload["last_activity_at"] is not None
    assert payload["last_transition_at"] is not None
    assert payload["operator_category"]
    assert payload["operator_category_label"]
    assert payload["operator_visibility_reason"]
    assert payload["terminal_reason"] == expected_terminal_reason
    assert payload["links"]["self"].endswith(f"/api/v1/projects/{project_id}")
    assert payload["links"]["summary"].endswith(
        f"/api/v1/projects/{project_id}/summary"
    )
    assert payload["links"]["operator_overview"].endswith(
        f"/api/v1/projects/{project_id}/operator-overview"
    )
    assert payload["next_steps"]
    if expected_focus_task_id is None:
        assert payload.get("focus_task") is None
    else:
        focus_task = payload.get("focus_task")
        assert focus_task is not None
        assert focus_task["id"] == expected_focus_task_id


@pytest.mark.asyncio
async def test_project_summary(api_client):
    """Project summary endpoint returns stats."""
    create = await api_client.post(
        "/api/v1/projects",
        json={"name": "API Project", "description": "Summary test"},
    )
    create.raise_for_status()
    project_id = create.json()["id"]

    summary = await api_client.get(f"/api/v1/projects/{project_id}/summary")
    summary.raise_for_status()
    payload = summary.json()
    assert payload["project"]["id"] == project_id
    assert "health_score" in payload


@pytest.mark.asyncio
async def test_project_operator_overview(api_client):
    """Project operator overview should unify summary, daily review, lineage, and history."""
    create = await api_client.post(
        "/api/v1/projects",
        json={"name": "Operator Project", "description": "Operator wrapper test"},
    )
    create.raise_for_status()
    project_id = create.json()["id"]

    task = await api_client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Operator Task"},
    )
    task.raise_for_status()
    task_id = task.json()["id"]

    await api_client.post(f"/api/v1/tasks/{task_id}/start")

    plan = await api_client.post(
        "/api/v1/plans",
        json={
            "name": "Operator Plan",
            "status": "active",
            "format": "json",
            "content": {"steps": ["wrap"]},
            "project_id": project_id,
            "task_ids": [task_id],
        },
    )
    plan.raise_for_status()

    response = await api_client.get(
        f"/api/v1/projects/{project_id}/operator-overview"
        "?task_limit=3&test_limit=2&queue_limit=2&lineage_limit=2"
        "&history_limit=4&include_timeline=true&view=overview"
    )
    response.raise_for_status()
    payload = response.json()

    assert payload["project"]["id"] == project_id
    assert "health_score" in payload
    assert payload["daily"]["snapshot"]["scope_id"] == project_id
    assert payload["lineage"]["totals"]["total_plans"] >= 1
    assert payload["history"]["entity_type"] == "project"
    assert payload["links"]["self"].startswith(
        f"/api/v1/projects/{project_id}/operator-overview?"
    )
    assert payload["links"]["daily"].startswith(
        f"/api/v1/work-snapshots/project/{project_id}/daily?"
    )
    assert payload["links"]["lineage"].startswith("/api/v1/plans/lineage?")
    assert payload["links"]["history_bundle"].startswith(
        f"/api/v1/revisions/project/{project_id}/bundle?"
    )
    assert payload["next_steps"]


@pytest.mark.asyncio
async def test_project_detail_summary_and_list_surface_expose_active_rollups(
    api_client,
):
    """Project lifecycle fields should stay aligned across API detail surfaces."""
    create = await api_client.post(
        "/api/v1/projects",
        json={"name": "Active Lifecycle API Project"},
    )
    create.raise_for_status()
    create_payload = create.json()
    project_id = create_payload["id"]
    _assert_project_payload(
        create_payload,
        project_id=project_id,
        expected_status="active",
        expected_stored_status="active",
        expected_terminal_reason=None,
        expected_focus_task_id=None,
    )

    task = await api_client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Active Lifecycle API Task"},
    )
    task.raise_for_status()
    task_id = task.json()["id"]

    start = await api_client.post(f"/api/v1/tasks/{task_id}/start")
    start.raise_for_status()

    detail = await api_client.get(f"/api/v1/projects/{project_id}")
    detail.raise_for_status()
    detail_payload = detail.json()
    _assert_project_payload(
        detail_payload,
        project_id=project_id,
        expected_status="active",
        expected_stored_status="active",
        expected_terminal_reason=None,
        expected_focus_task_id=task_id,
    )
    assert detail_payload["operator_category"] == "active_work"

    summary = await api_client.get(f"/api/v1/projects/{project_id}/summary")
    summary.raise_for_status()
    summary_payload = summary.json()
    _assert_project_payload(
        summary_payload["project"],
        project_id=project_id,
        expected_status="active",
        expected_stored_status="active",
        expected_terminal_reason=None,
        expected_focus_task_id=task_id,
    )
    assert summary_payload["links"]["self"].endswith(f"/api/v1/projects/{project_id}")
    assert summary_payload["next_steps"]

    overview = await api_client.get(f"/api/v1/projects/{project_id}/operator-overview")
    overview.raise_for_status()
    overview_payload = overview.json()
    _assert_project_payload(
        overview_payload["project"],
        project_id=project_id,
        expected_status="active",
        expected_stored_status="active",
        expected_terminal_reason=None,
        expected_focus_task_id=task_id,
    )
    assert overview_payload["focus_task"]["id"] == task_id

    listing = await api_client.get("/api/v1/projects")
    listing.raise_for_status()
    listing_payload = listing.json()
    project_item = _project_item(listing_payload["items"], project_id)
    _assert_project_payload(
        project_item,
        project_id=project_id,
        expected_status="active",
        expected_stored_status="active",
        expected_terminal_reason=None,
        expected_focus_task_id=None,
    )
    assert listing_payload["next_steps"]


@pytest.mark.asyncio
async def test_project_api_surfaces_keep_completed_status_when_only_draft_plan_residue_remains(
    api_client,
):
    """Draft plans should not reopen terminal projects on API list/detail/summary surfaces."""
    create = await api_client.post(
        "/api/v1/projects",
        json={"name": "Completed Lifecycle API Project"},
    )
    create.raise_for_status()
    project_id = create.json()["id"]

    task = await api_client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Completed Lifecycle API Task"},
    )
    task.raise_for_status()
    task_id = task.json()["id"]

    start = await api_client.post(f"/api/v1/tasks/{task_id}/start")
    start.raise_for_status()
    complete = await api_client.post(f"/api/v1/tasks/{task_id}/complete")
    complete.raise_for_status()

    plan = await api_client.post(
        "/api/v1/plans",
        json={
            "name": "Completed Lifecycle Residue Plan",
            "status": "draft",
            "format": "json",
            "content": {"steps": ["residual planning only"]},
            "project_id": project_id,
        },
    )
    plan.raise_for_status()

    update = await api_client.patch(
        f"/api/v1/projects/{project_id}",
        json={"status": "completed"},
    )
    update.raise_for_status()
    update_payload = update.json()
    _assert_project_payload(
        update_payload,
        project_id=project_id,
        expected_status="completed",
        expected_stored_status="completed",
        expected_terminal_reason="all linked execution scopes are already terminal",
        expected_focus_task_id=None,
    )
    assert update_payload["operator_category"] == "project_history"

    detail = await api_client.get(f"/api/v1/projects/{project_id}")
    detail.raise_for_status()
    _assert_project_payload(
        detail.json(),
        project_id=project_id,
        expected_status="completed",
        expected_stored_status="completed",
        expected_terminal_reason="all linked execution scopes are already terminal",
        expected_focus_task_id=None,
    )

    summary = await api_client.get(f"/api/v1/projects/{project_id}/summary")
    summary.raise_for_status()
    summary_payload = summary.json()
    _assert_project_payload(
        summary_payload["project"],
        project_id=project_id,
        expected_status="completed",
        expected_stored_status="completed",
        expected_terminal_reason="all linked execution scopes are already terminal",
        expected_focus_task_id=None,
    )

    overview = await api_client.get(f"/api/v1/projects/{project_id}/operator-overview")
    overview.raise_for_status()
    overview_payload = overview.json()
    _assert_project_payload(
        overview_payload["project"],
        project_id=project_id,
        expected_status="completed",
        expected_stored_status="completed",
        expected_terminal_reason="all linked execution scopes are already terminal",
        expected_focus_task_id=None,
    )
    assert overview_payload["focus_task"] is None

    listing = await api_client.get("/api/v1/projects")
    listing.raise_for_status()
    project_item = _project_item(listing.json()["items"], project_id)
    _assert_project_payload(
        project_item,
        project_id=project_id,
        expected_status="completed",
        expected_stored_status="completed",
        expected_terminal_reason="all linked execution scopes are already terminal",
        expected_focus_task_id=None,
    )
