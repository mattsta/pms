"""Integration tests for actor MCP tools."""

from __future__ import annotations

import re

import pytest

from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.services.goal_service import GoalService
from pms.services.project_service import ProjectService
from pms.services.task_service import TaskService
from pms.tools.project_tools import (
    add_actor_alias,
    add_actor_membership,
    create_actor,
    get_actor,
    list_actors,
    set_services,
)


def _extract_id(text: str) -> str:
    match = re.search(r"ID: ([a-f0-9-]+)", text)
    assert match, f"Expected ID in tool output: {text}"
    return match.group(1)


@pytest.mark.asyncio
async def test_actor_tools_create_list_and_graph(db):
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)

    project_service = ProjectService(db, event_store, revision_store, metrics)
    task_service = TaskService(db, event_store, revision_store, metrics)
    goal_service = GoalService(db, event_store, revision_store, metrics)

    set_services(
        project_service=project_service,
        task_service=task_service,
        goal_service=goal_service,
    )

    persona_result = await create_actor.handler(
        {
            "name": "Security Persona",
            "kind": "persona",
            "handle": "security-persona",
            "description": "Security routing persona",
            "tags": "security,persona",
        }
    )
    persona_id = _extract_id(persona_result["content"][0]["text"])

    human_result = await create_actor.handler(
        {
            "name": "Alice Example",
            "kind": "human",
            "handle": "alice-example",
            "description": "Primary owner",
            "tags": "human",
        }
    )
    human_id = _extract_id(human_result["content"][0]["text"])

    alias_result = await add_actor_alias.handler(
        {"actor": "security-persona", "alias": "sec"}
    )
    assert "Added alias" in alias_result["content"][0]["text"]

    membership_result = await add_actor_membership.handler(
        {
            "parent": "security-persona",
            "member": "alice-example",
            "role": "member",
        }
    )
    assert "Created membership" in membership_result["content"][0]["text"]

    listed = await list_actors.handler({})
    listed_text = listed["content"][0]["text"]
    assert persona_id in listed_text
    assert human_id in listed_text

    actor_details = await get_actor.handler({"identifier": "alice-example"})
    detail_text = actor_details["content"][0]["text"]
    assert "Actor: Alice Example" in detail_text
    assert "Handle: alice-example" in detail_text
    assert "Parents: 1" in detail_text
