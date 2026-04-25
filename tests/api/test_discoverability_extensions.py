"""Tests for discoverability wrappers on extension list/query APIs."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_comments_and_watchers_include_discoverability_wrappers(
    api_client,
) -> None:
    project_resp = await api_client.post(
        "/api/v1/projects",
        json={"name": "Discoverability Comment Project"},
    )
    project_resp.raise_for_status()
    project_id = project_resp.json()["id"]

    task_resp = await api_client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Comment Target"},
    )
    task_resp.raise_for_status()
    task_id = task_resp.json()["id"]

    comment_resp = await api_client.post(
        "/api/v1/comments",
        json={
            "entity_type": "task",
            "entity_id": task_id,
            "body": "Initial comment",
            "created_by": "tester",
            "mentions": [],
            "metadata": {},
            "watch": False,
        },
    )
    comment_resp.raise_for_status()
    assert comment_resp.json()["id"]

    watcher_resp = await api_client.post(
        "/api/v1/watchers",
        json={
            "entity_type": "task",
            "entity_id": task_id,
            "watcher": "qa@example.com",
        },
    )
    watcher_resp.raise_for_status()
    assert watcher_resp.json()["id"]

    comments_list = await api_client.get(
        "/api/v1/comments",
        params={
            "entity_type": "task",
            "entity_id": task_id,
            "include_archived": "false",
            "limit": 10,
            "offset": 0,
        },
    )
    comments_list.raise_for_status()
    comments_payload = comments_list.json()
    assert comments_payload["links"]["guide"] == "/api/v1/"
    assert comments_payload["links"]["entity"] == f"/api/v1/tasks/{task_id}"
    assert isinstance(comments_payload["next_steps"], list)
    assert comments_payload["next_steps"]
    assert comments_payload["params"]["entity_type"] == "task"

    watchers_list = await api_client.get(
        "/api/v1/watchers",
        params={
            "entity_type": "task",
            "entity_id": task_id,
            "include_archived": "false",
            "limit": 10,
            "offset": 0,
        },
    )
    watchers_list.raise_for_status()
    watchers_payload = watchers_list.json()
    assert watchers_payload["links"]["guide"] == "/api/v1/"
    assert watchers_payload["links"]["entity"] == f"/api/v1/tasks/{task_id}"
    assert isinstance(watchers_payload["next_steps"], list)
    assert watchers_payload["next_steps"]
    assert watchers_payload["params"]["entity_type"] == "task"


@pytest.mark.asyncio
async def test_comments_normalize_entity_type_alias_in_response_params(
    api_client,
) -> None:
    org_resp = await api_client.post(
        "/api/v1/organizations",
        json={"name": "Comment Alias Org"},
    )
    org_resp.raise_for_status()
    org_id = org_resp.json()["id"]

    comment_resp = await api_client.post(
        "/api/v1/comments",
        json={
            "entity_type": "org",
            "entity_id": org_id,
            "body": "Org note",
            "created_by": "tester",
            "mentions": [],
            "metadata": {},
            "watch": False,
        },
    )
    comment_resp.raise_for_status()
    assert comment_resp.json()["entity_type"] == "organization"

    comments_list = await api_client.get(
        "/api/v1/comments",
        params={"entity_type": "org", "entity_id": org_id},
    )
    comments_list.raise_for_status()
    payload = comments_list.json()
    assert payload["params"]["entity_type"] == "organization"
    assert payload["links"]["entity"] == f"/api/v1/organizations/{org_id}"


@pytest.mark.asyncio
async def test_automation_and_agent_loop_lists_include_discoverability_wrappers(
    api_client,
    api_db,
) -> None:
    project_resp = await api_client.post(
        "/api/v1/projects",
        json={"name": "Discoverability Automation Project"},
    )
    project_resp.raise_for_status()
    project_id = project_resp.json()["id"]

    rule_resp = await api_client.post(
        "/api/v1/automation/rules",
        json={
            "name": "Create Follow-up",
            "event_pattern": "task.updated",
            "action_type": "create_task",
            "action_payload": {"project_id": project_id, "title": "Follow-up"},
            "enabled": True,
        },
    )
    rule_resp.raise_for_status()
    rule_id = rule_resp.json()["id"]

    rules_list = await api_client.get(
        "/api/v1/automation/rules",
        params={
            "include_archived": "false",
            "enabled": "true",
            "limit": 10,
            "offset": 0,
        },
    )
    rules_list.raise_for_status()
    rules_payload = rules_list.json()
    assert rules_payload["links"]["guide"] == "/api/v1/"
    assert isinstance(rules_payload["next_steps"], list)
    assert rules_payload["next_steps"]
    assert rules_payload["params"]["enabled"] is True
    assert rules_payload["params"]["limit"] == 10

    runs_list = await api_client.get(
        f"/api/v1/automation/rules/{rule_id}/runs",
        params={"limit": 10, "offset": 0},
    )
    runs_list.raise_for_status()
    runs_payload = runs_list.json()
    assert runs_payload["links"]["guide"] == "/api/v1/"
    assert runs_payload["links"]["rule"] == f"/api/v1/automation/rules/{rule_id}"
    assert isinstance(runs_payload["next_steps"], list)
    assert runs_payload["next_steps"]
    assert runs_payload["params"]["rule_id"] == rule_id

    from pms.core.events import EventStore, EventType
    from pms.core.metrics import MetricsCollector
    from pms.core.revisions import RevisionStore
    from pms.models.enums import SessionStatus
    from pms.repositories.session_repository import SessionRepository

    event_store = EventStore(api_db)
    revision_store = RevisionStore(api_db)
    metrics = MetricsCollector(api_db)
    repo = SessionRepository(api_db, event_store, revision_store, metrics)

    session = await repo.create(
        project_id=project_id,
        context_summary="discoverability loop",
        initial_prompt="Proceed",
    )
    session.state = {
        "loop": {
            "agent": "fake",
            "iterations": 1,
            "max_iterations": 5,
            "max_runtime_seconds": 60,
        }
    }
    session.status = SessionStatus.ACTIVE
    await repo.save(session, EventType.SESSION_UPDATED, {"loop_started": True})
    await repo.add_message(
        session.id,
        "user",
        "Proceed",
        metadata={"iteration": 1},
    )

    loops_list = await api_client.get(
        "/api/v1/agent-loops",
        params={
            "project_id": project_id,
            "include_ended": "false",
            "limit": 10,
            "offset": 0,
        },
    )
    loops_list.raise_for_status()
    loops_payload = loops_list.json()
    assert loops_payload["links"]["guide"] == "/api/v1/"
    assert isinstance(loops_payload["next_steps"], list)
    assert loops_payload["next_steps"]
    assert loops_payload["params"]["project_id"] == project_id

    loop_id = loops_payload["items"][0]["id"]
    messages_resp = await api_client.get(
        f"/api/v1/agent-loops/{loop_id}/messages",
        params={"limit": 10, "offset": 0},
    )
    messages_resp.raise_for_status()
    messages_payload = messages_resp.json()
    assert messages_payload["links"]["guide"] == "/api/v1/"
    assert messages_payload["links"]["loop"] == f"/api/v1/agent-loops/{loop_id}"
    assert isinstance(messages_payload["next_steps"], list)
    assert messages_payload["next_steps"]
    assert messages_payload["params"]["loop_id"] == loop_id


@pytest.mark.asyncio
async def test_automation_rule_create_rejects_unknown_action_type_with_suggestion(
    api_client,
) -> None:
    response = await api_client.post(
        "/api/v1/automation/rules",
        json={
            "name": "Bad Action Rule",
            "event_pattern": "task.updated",
            "action_type": "create_taks",
            "action_payload": {"title": "Follow-up"},
            "enabled": True,
        },
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"] == "Validation error"
    assert payload["field"] == "action_type"
    assert payload["allowed_values"] == [
        "add_comment",
        "create_task",
        "update_task_status",
        "set_custom_field_value",
    ]
    assert "create_task" in payload["detail"]
    assert "create_task" in payload["suggestions"]
