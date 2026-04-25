"""API tests for saved searches and smart queues."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.models.actor import ActorKind
from pms.models.enums import TaskStatus
from pms.repositories.task_repository import TaskRepository
from pms.services.actor_service import ActorService


@pytest.mark.asyncio
async def test_saved_search_crud(api_client, api_db):
    actor_service = ActorService(
        api_db,
        EventStore(api_db),
        RevisionStore(api_db),
        MetricsCollector(api_db),
    )
    owner = await actor_service.create_actor(
        name="Queue Persona",
        kind=ActorKind.PERSONA,
    )
    project_resp = await api_client.post(
        "/api/v1/projects",
        json={"name": "Queue Project", "description": "Queues", "tags": []},
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    event_store = EventStore(api_db)
    revision_store = RevisionStore(api_db)
    metrics = MetricsCollector(api_db)
    task_repo = TaskRepository(api_db, event_store, revision_store, metrics)

    task_alpha = await task_repo.create(
        project_id=project_id,
        title="Alpha Task",
        tags=["backend"],
    )
    await task_repo.create(
        project_id=project_id,
        title="Beta Task",
        tags=["frontend"],
    )

    create_resp = await api_client.post(
        "/api/v1/queues",
        json={
            "name": "Backend Queue",
            "description": "Backend tasks",
            "owner": owner.handle,
            "filters": {"tags": ["backend"]},
            "sort_dir": "desc",
        },
    )
    assert create_resp.status_code == 201
    create_payload = create_resp.json()
    queue_id = create_payload["id"]
    assert create_payload["owner"]["id"] == owner.id
    assert create_payload["owner"]["actor"]["handle"] == owner.handle
    assert create_payload["sort_dir"] == "desc"

    await api_db.execute(
        "UPDATE tasks SET assignee = ?, assignee_id = ? WHERE id = ?",
        (owner.handle, owner.id, task_alpha.id),
    )

    run_resp = await api_client.get(f"/api/v1/queues/{queue_id}/run")
    assert run_resp.status_code == 200
    payload = run_resp.json()
    assert payload["total_count"] == 1
    assert payload["items"][0]["id"] == task_alpha.id
    assert payload["saved_search"]["owner"]["actor"]["handle"] == owner.handle
    assert payload["items"][0]["assignee"]["id"] == owner.id
    assert payload["items"][0]["assignee"]["actor"]["handle"] == owner.handle
    assert payload["items"][0]["links"]["actor"] == f"/api/v1/actors/{owner.handle}"

    update_resp = await api_client.put(
        f"/api/v1/queues/{queue_id}",
        json={"name": "Updated Queue"},
    )
    assert update_resp.status_code == 200
    update_payload = update_resp.json()
    assert update_payload["name"] == "Updated Queue"
    assert update_payload["owner"]["actor"]["handle"] == owner.handle

    list_resp = await api_client.get("/api/v1/queues")
    assert list_resp.status_code == 200
    listed_item = next(
        item for item in list_resp.json()["items"] if item["id"] == queue_id
    )
    assert listed_item["owner"]["actor"]["handle"] == owner.handle

    delete_resp = await api_client.delete(f"/api/v1/queues/{queue_id}")
    assert delete_resp.status_code == 200


@pytest.mark.asyncio
async def test_saved_search_rejects_invalid_sort_dir(api_client) -> None:
    project_resp = await api_client.post(
        "/api/v1/projects",
        json={"name": "Invalid Queue Sort", "description": "Queues", "tags": []},
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    create_resp = await api_client.post(
        "/api/v1/queues",
        json={
            "name": "Broken Queue",
            "scope_type": "project",
            "scope_id": project_id,
            "sort_dir": "sideways",
        },
    )
    assert create_resp.status_code == 422


@pytest.mark.asyncio
async def test_queue_presets(api_client, api_db):
    project_resp = await api_client.post(
        "/api/v1/projects",
        json={"name": "Preset Project", "description": "Queues", "tags": []},
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    event_store = EventStore(api_db)
    revision_store = RevisionStore(api_db)
    metrics = MetricsCollector(api_db)
    task_repo = TaskRepository(api_db, event_store, revision_store, metrics)

    now = datetime.now(UTC)
    overdue = await task_repo.create(
        project_id=project_id,
        title="Overdue Task",
        due_date=now - timedelta(days=2),
    )
    at_risk = await task_repo.create(
        project_id=project_id,
        title="At Risk Task",
        due_date=now + timedelta(days=2),
    )
    blocked = await task_repo.create(
        project_id=project_id,
        title="Blocked Task",
    )
    await task_repo.update_status(blocked.id, TaskStatus.BLOCKED)

    presets_resp = await api_client.get(
        "/api/v1/queues/presets",
        params={"project_id": project_id, "limit": 5},
    )
    assert presets_resp.status_code == 200
    preset_payload = presets_resp.json()
    names = {item["name"] for item in preset_payload}
    assert {"ready", "stale", "blocked", "overdue", "at_risk"}.issubset(names)
    first_preset = preset_payload[0]
    assert first_preset["links"]["guide"] == "/api/v1/"
    assert isinstance(first_preset["next_steps"], list)
    assert first_preset["next_steps"]
    assert first_preset["params"]["project_id"] == project_id
    assert all(item["population"] == "scoped_project" for item in preset_payload)

    overdue_resp = await api_client.get(
        "/api/v1/queues/presets/overdue",
        params={"project_id": project_id},
    )
    assert overdue_resp.status_code == 200
    overdue_payload = overdue_resp.json()
    assert overdue_payload["total_count"] >= 1
    assert overdue_payload["links"]["guide"] == "/api/v1/"
    assert isinstance(overdue_payload["next_steps"], list)
    assert overdue_payload["next_steps"]
    assert overdue_payload["population"] == "scoped_project"
    overdue_ids = {item["id"] for item in overdue_payload["items"]}
    assert overdue.id in overdue_ids

    at_risk_resp = await api_client.get(
        "/api/v1/queues/presets/at_risk",
        params={"project_id": project_id},
    )
    assert at_risk_resp.status_code == 200
    at_risk_payload = at_risk_resp.json()
    assert at_risk_payload["population"] == "scoped_project"
    at_risk_ids = {item["id"] for item in at_risk_payload["items"]}
    assert at_risk.id in at_risk_ids
