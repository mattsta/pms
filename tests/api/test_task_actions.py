"""API tests for task actions and dependencies."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_task_status_actions(api_client) -> None:
    project_resp = await api_client.post(
        "/api/v1/projects",
        json={"name": "Action Project"},
    )
    project_resp.raise_for_status()
    project_id = project_resp.json()["id"]

    task_resp = await api_client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Action Task"},
    )
    task_resp.raise_for_status()
    task_id = task_resp.json()["id"]

    block_resp = await api_client.post(
        f"/api/v1/tasks/{task_id}/block",
        json={"reason": "waiting", "updated_by": "tester"},
    )
    assert block_resp.status_code == 200
    task_state = await api_client.get(f"/api/v1/tasks/{task_id}")
    assert task_state.json()["status"] == "blocked"

    unblock_resp = await api_client.post(
        f"/api/v1/tasks/{task_id}/unblock",
        json={"updated_by": "tester"},
    )
    assert unblock_resp.status_code == 200
    task_state = await api_client.get(f"/api/v1/tasks/{task_id}")
    assert task_state.json()["status"] == "todo"

    start_resp = await api_client.post(
        f"/api/v1/tasks/{task_id}/start",
        json={"updated_by": "tester"},
    )
    assert start_resp.status_code == 200
    task_state = await api_client.get(f"/api/v1/tasks/{task_id}")
    assert task_state.json()["status"] == "in_progress"

    review_resp = await api_client.post(
        f"/api/v1/tasks/{task_id}/review",
        json={"updated_by": "tester"},
    )
    assert review_resp.status_code == 200
    task_state = await api_client.get(f"/api/v1/tasks/{task_id}")
    assert task_state.json()["status"] == "in_review"

    reopen_resp = await api_client.post(
        f"/api/v1/tasks/{task_id}/reopen",
        json={"updated_by": "tester"},
    )
    assert reopen_resp.status_code == 200
    task_state = await api_client.get(f"/api/v1/tasks/{task_id}")
    assert task_state.json()["status"] == "todo"

    cancel_resp = await api_client.post(
        f"/api/v1/tasks/{task_id}/cancel",
        json={"reason": "stop", "updated_by": "tester"},
    )
    assert cancel_resp.status_code == 200
    task_state = await api_client.get(f"/api/v1/tasks/{task_id}")
    assert task_state.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_task_complete_accepts_actual_hours(api_client) -> None:
    project_resp = await api_client.post(
        "/api/v1/projects",
        json={"name": "Completion Project"},
    )
    project_resp.raise_for_status()
    project_id = project_resp.json()["id"]

    task_resp = await api_client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Completion Task"},
    )
    task_resp.raise_for_status()
    task_id = task_resp.json()["id"]

    start_resp = await api_client.post(
        f"/api/v1/tasks/{task_id}/start",
        json={"updated_by": "tester"},
    )
    assert start_resp.status_code == 200

    complete_resp = await api_client.post(
        f"/api/v1/tasks/{task_id}/complete",
        json={"updated_by": "tester", "actual_hours": 2.5},
    )
    assert complete_resp.status_code == 200

    task_state = await api_client.get(f"/api/v1/tasks/{task_id}")
    payload = task_state.json()
    assert payload["status"] == "done"
    assert payload["actual_hours"] == 2.5


@pytest.mark.asyncio
async def test_task_complete_returns_conflict_when_task_is_already_done(
    api_client,
) -> None:
    project_resp = await api_client.post(
        "/api/v1/projects",
        json={"name": "Already Done Project"},
    )
    project_resp.raise_for_status()
    project_id = project_resp.json()["id"]

    task_resp = await api_client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Already Done Task"},
    )
    task_resp.raise_for_status()
    task_id = task_resp.json()["id"]

    first_complete = await api_client.post(
        f"/api/v1/tasks/{task_id}/complete",
        json={"updated_by": "tester"},
    )
    assert first_complete.status_code == 200

    second_complete = await api_client.post(
        f"/api/v1/tasks/{task_id}/complete",
        json={"updated_by": "tester"},
    )
    assert second_complete.status_code == 409
    assert "Cannot complete task in done status" in second_complete.json()["detail"]


@pytest.mark.asyncio
async def test_task_start_returns_conflict_when_task_is_already_done(
    api_client,
) -> None:
    project_resp = await api_client.post(
        "/api/v1/projects",
        json={"name": "Already Done Start Project"},
    )
    project_resp.raise_for_status()
    project_id = project_resp.json()["id"]

    task_resp = await api_client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Already Done Start Task"},
    )
    task_resp.raise_for_status()
    task_id = task_resp.json()["id"]

    complete_resp = await api_client.post(
        f"/api/v1/tasks/{task_id}/complete",
        json={"updated_by": "tester"},
    )
    assert complete_resp.status_code == 200

    start_resp = await api_client.post(
        f"/api/v1/tasks/{task_id}/start",
        json={"updated_by": "tester"},
    )
    assert start_resp.status_code == 409
    assert "Cannot start task in done status" in start_resp.json()["detail"]


@pytest.mark.asyncio
async def test_task_complete_surfaces_newly_unblocked_dependents(api_client) -> None:
    project_resp = await api_client.post(
        "/api/v1/projects",
        json={"name": "Completion Effects Project"},
    )
    project_resp.raise_for_status()
    project_id = project_resp.json()["id"]

    blocker_resp = await api_client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Finish Blocker"},
    )
    blocker_resp.raise_for_status()
    blocker_id = blocker_resp.json()["id"]

    dependent_resp = await api_client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Ready After Blocker"},
    )
    dependent_resp.raise_for_status()
    dependent_id = dependent_resp.json()["id"]

    add_dep_resp = await api_client.post(
        f"/api/v1/tasks/{dependent_id}/dependencies",
        json={"depends_on_id": blocker_id, "dependency_type": "blocks"},
    )
    assert add_dep_resp.status_code == 201

    complete_resp = await api_client.post(
        f"/api/v1/tasks/{blocker_id}/complete",
        json={"updated_by": "tester"},
    )
    assert complete_resp.status_code == 200
    payload = complete_resp.json()
    assert payload["status"] == "completed"
    assert payload["task_id"] == blocker_id
    assert len(payload["newly_unblocked"]) == 1
    first = payload["newly_unblocked"][0]
    assert first["id"] == dependent_id
    assert first["status"] == "todo"

    dependent_state = await api_client.get(f"/api/v1/tasks/{dependent_id}")
    assert dependent_state.status_code == 200
    assert dependent_state.json()["status"] == "todo"


@pytest.mark.asyncio
async def test_task_complete_skips_draft_locked_dependents(api_client) -> None:
    project_resp = await api_client.post(
        "/api/v1/projects",
        json={"name": "Completion Draft-Locked Project"},
    )
    project_resp.raise_for_status()
    project_id = project_resp.json()["id"]

    blocker_resp = await api_client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Draft-Locked Blocker"},
    )
    blocker_resp.raise_for_status()
    blocker_id = blocker_resp.json()["id"]

    dependent_resp = await api_client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Draft-Locked Dependent"},
    )
    dependent_resp.raise_for_status()
    dependent_id = dependent_resp.json()["id"]

    add_dep_resp = await api_client.post(
        f"/api/v1/tasks/{dependent_id}/dependencies",
        json={"depends_on_id": blocker_id, "dependency_type": "blocks"},
    )
    assert add_dep_resp.status_code == 201

    block_resp = await api_client.post(
        f"/api/v1/tasks/{dependent_id}/block",
        json={"reason": "waiting", "updated_by": "tester"},
    )
    assert block_resp.status_code == 200

    plan_resp = await api_client.post(
        "/api/v1/plans",
        json={
            "name": "Draft-Locked Dependent Plan",
            "status": "draft",
            "format": "json",
            "content": {"steps": []},
            "project_id": project_id,
            "task_ids": [dependent_id],
        },
    )
    assert plan_resp.status_code == 201

    complete_resp = await api_client.post(
        f"/api/v1/tasks/{blocker_id}/complete",
        json={"updated_by": "tester"},
    )
    assert complete_resp.status_code == 200
    payload = complete_resp.json()
    assert payload["status"] == "completed"
    assert payload["task_id"] == blocker_id
    assert payload["newly_unblocked"] == []

    dependent_state = await api_client.get(f"/api/v1/tasks/{dependent_id}")
    assert dependent_state.status_code == 200
    assert dependent_state.json()["status"] == "blocked"


@pytest.mark.asyncio
async def test_task_dependency_endpoints(api_client) -> None:
    project_resp = await api_client.post(
        "/api/v1/projects",
        json={"name": "Dependency Project"},
    )
    project_resp.raise_for_status()
    project_id = project_resp.json()["id"]

    task_a_resp = await api_client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Depends Task"},
    )
    task_a_resp.raise_for_status()
    task_a_id = task_a_resp.json()["id"]

    task_b_resp = await api_client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Dependency Task"},
    )
    task_b_resp.raise_for_status()
    task_b_id = task_b_resp.json()["id"]

    add_resp = await api_client.post(
        f"/api/v1/tasks/{task_a_id}/dependencies",
        json={"depends_on_id": task_b_id, "dependency_type": "blocks"},
    )
    assert add_resp.status_code == 201

    graph_resp = await api_client.get(f"/api/v1/tasks/{task_a_id}/graph")
    assert graph_resp.status_code == 200
    graph = graph_resp.json()
    assert task_b_id in graph["blocked_by"]

    remove_resp = await api_client.delete(
        f"/api/v1/tasks/{task_a_id}/dependencies/{task_b_id}"
    )
    assert remove_resp.status_code == 200
