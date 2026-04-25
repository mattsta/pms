"""API tests for task search, ready, and stale endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.models.enums import DependencyType
from pms.repositories.task_repository import TaskRepository


@pytest.mark.asyncio
async def test_task_ready_stale_and_search(api_client, api_db):
    project_resp = await api_client.post(
        "/api/v1/projects",
        json={"name": "Query Project", "description": "Query tests", "tags": []},
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    task_ready_resp = await api_client.post(
        "/api/v1/tasks",
        json={
            "project_id": project_id,
            "title": "Ready Task",
            "description": "Ready to work",
            "priority": "medium",
            "complexity_points": 3,
            "tags": ["ready"],
        },
    )
    assert task_ready_resp.status_code == 201
    ready_task_id = task_ready_resp.json()["id"]

    task_blocked_resp = await api_client.post(
        "/api/v1/tasks",
        json={
            "project_id": project_id,
            "title": "Blocked Task",
            "description": "Waiting",
            "priority": "high",
            "complexity_points": 5,
            "tags": ["blocked"],
        },
    )
    assert task_blocked_resp.status_code == 201
    blocked_task_id = task_blocked_resp.json()["id"]

    event_store = EventStore(api_db)
    revision_store = RevisionStore(api_db)
    metrics = MetricsCollector(api_db)
    task_repo = TaskRepository(api_db, event_store, revision_store, metrics)
    await task_repo.add_dependency(
        task_id=blocked_task_id,
        depends_on_id=ready_task_id,
        dependency_type=DependencyType.BLOCKS,
    )

    list_resp = await api_client.get(
        "/api/v1/tasks",
        params={"project_id": project_id},
    )
    assert list_resp.status_code == 200
    list_payload = list_resp.json()
    assert "links" in list_payload
    assert "next_steps" in list_payload
    assert "params" in list_payload
    assert list_payload["links"]["guide"] == "/api/v1/"

    ready_resp = await api_client.get(
        "/api/v1/tasks/ready",
        params={"project_id": project_id},
    )
    assert ready_resp.status_code == 200
    ready_payload = ready_resp.json()
    assert "links" in ready_payload
    assert "next_steps" in ready_payload
    assert "params" in ready_payload
    assert ready_payload["links"]["guide"] == "/api/v1/"
    ready_ids = [item["id"] for item in ready_payload["items"]]
    assert ready_task_id in ready_ids
    assert blocked_task_id not in ready_ids

    complete_resp = await api_client.post(
        f"/api/v1/tasks/{ready_task_id}/complete",
    )
    assert complete_resp.status_code == 200

    ready_after_resp = await api_client.get(
        "/api/v1/tasks/ready",
        params={"project_id": project_id},
    )
    assert ready_after_resp.status_code == 200
    ready_after_payload = ready_after_resp.json()
    assert "links" in ready_after_payload
    assert "next_steps" in ready_after_payload
    assert "params" in ready_after_payload
    ready_after_ids = [item["id"] for item in ready_after_payload["items"]]
    assert blocked_task_id in ready_after_ids

    stale_time = task_blocked_resp.json()["updated_at"]
    stale_dt = datetime.fromisoformat(stale_time) - timedelta(days=30)
    await api_db.execute(
        "UPDATE tasks SET updated_at = ? WHERE id = ?",
        (stale_dt.isoformat(), blocked_task_id),
    )
    await api_db.commit()

    stale_resp = await api_client.get(
        "/api/v1/tasks/stale",
        params={"project_id": project_id, "stale_after_days": 14},
    )
    assert stale_resp.status_code == 200
    stale_payload = stale_resp.json()
    assert "links" in stale_payload
    assert "next_steps" in stale_payload
    assert "params" in stale_payload
    assert stale_payload["links"]["guide"] == "/api/v1/"
    stale_ids = [item["id"] for item in stale_payload["items"]]
    assert blocked_task_id in stale_ids

    search_resp = await api_client.get(
        "/api/v1/tasks/search",
        params={"project_id": project_id, "query": "Ready", "include_terminal": True},
    )
    assert search_resp.status_code == 200
    search_payload = search_resp.json()
    assert "links" in search_payload
    assert "next_steps" in search_payload
    assert "params" in search_payload
    assert search_payload["links"]["guide"] == "/api/v1/"
    search_ids = [item["id"] for item in search_payload["items"]]
    assert ready_task_id in search_ids


@pytest.mark.asyncio
async def test_task_duplicates_and_merge(api_client):
    project_resp = await api_client.post(
        "/api/v1/projects",
        json={"name": "Duplicate Project", "description": "Dup tests", "tags": []},
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    primary_resp = await api_client.post(
        "/api/v1/tasks",
        json={
            "project_id": project_id,
            "title": "Duplicate Task",
            "description": "Primary",
            "priority": "medium",
            "complexity_points": 3,
            "tags": [],
        },
    )
    assert primary_resp.status_code == 201
    primary_id = primary_resp.json()["id"]

    duplicate_ids = []
    for idx in range(2):
        dup_resp = await api_client.post(
            "/api/v1/tasks",
            json={
                "project_id": project_id,
                "title": "Duplicate Task",
                "description": f"Duplicate {idx}",
                "priority": "medium",
                "complexity_points": 2,
                "tags": [],
            },
        )
        assert dup_resp.status_code == 201
        duplicate_ids.append(dup_resp.json()["id"])

    duplicates_resp = await api_client.get(
        "/api/v1/tasks/duplicates",
        params={"project_id": project_id},
    )
    assert duplicates_resp.status_code == 200
    payload = duplicates_resp.json()
    assert payload["total_count"] == 1
    assert "links" in payload
    assert "next_steps" in payload
    assert "params" in payload
    assert payload["links"]["guide"] == "/api/v1/"
    assert payload["items"][0]["count"] == 3
    group = payload["items"][0]
    assert group["suggested_primary_id"] in {primary_id, *duplicate_ids}
    assert group["suggested_primary_reason"]
    assert group["last_activity_at"] is not None
    assert "links" in group
    assert "next_steps" in group

    preview_resp = await api_client.post(
        "/api/v1/tasks/duplicates/preview",
        json={
            "primary_task_id": primary_id,
            "duplicate_task_ids": duplicate_ids,
        },
    )
    assert preview_resp.status_code == 200
    preview_payload = preview_resp.json()
    assert preview_payload["primary_task"]["id"] == primary_id
    assert len(preview_payload["duplicates"]) == 2
    assert preview_payload["can_merge"] is True
    assert "links" in preview_payload
    assert "next_steps" in preview_payload
    assert preview_payload["links"]["guide"] == "/api/v1/"

    merge_resp = await api_client.post(
        "/api/v1/tasks/duplicates/merge",
        json={
            "primary_task_id": primary_id,
            "duplicate_task_ids": duplicate_ids,
            "cancel_duplicates": True,
        },
    )
    assert merge_resp.status_code == 200
    merge_payload = merge_resp.json()
    assert merge_payload["links_added"] == 2
    assert merge_payload["duplicates_cancelled"] == 2
    assert "links" in merge_payload
    assert "next_steps" in merge_payload
    assert merge_payload["links"]["guide"] == "/api/v1/"
    for task in merge_payload["duplicate_tasks"]:
        assert task["status"] == "cancelled"
