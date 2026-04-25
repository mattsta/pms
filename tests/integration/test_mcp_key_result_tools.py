"""Integration tests for MCP key-result lifecycle tools."""

from __future__ import annotations

import json

import pytest

from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.models import GoalStatus
from pms.services.goal_service import GoalService
from pms.services.project_service import ProjectService
from pms.services.task_service import TaskService
from pms.tools.project_tools import get_key_result, list_key_results, set_services


@pytest.mark.asyncio
async def test_mcp_key_result_list_and_detail_expose_lifecycle_rollups(db) -> None:
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

    project = await project_service.create_project(name="MCP Key Result Active Project")
    goal = await goal_service.create_goal(
        name="MCP Key Result Active Goal",
        project_id=project.id,
    )
    objective = await goal_service.create_objective(
        goal_id=goal.id,
        name="MCP Key Result Active Objective",
    )
    key_result = await goal_service.create_key_result(
        objective_id=objective.id,
        name="MCP Key Result Active KR",
        progress_percent=35,
    )
    await goal_service.update_key_result(
        key_result.id,
        status=GoalStatus.ON_HOLD,
        progress_percent=35,
        message="Pause one key result to force a bubbled transition timestamp",
    )
    await goal_service.update_key_result(
        key_result.id,
        status=GoalStatus.ACTIVE,
        progress_percent=35,
        message="Resume key result after hold transition",
    )

    list_result = await list_key_results.handler(
        {"objective_id": objective.id, "limit": 50, "offset": 0}
    )
    list_payload = json.loads(list_result["content"][0]["text"])
    item = list_payload["items"][0]

    assert list_payload["scope"]["kind"] == "mcp_key_result_list"
    assert list_payload["scope"]["objective_id"] == objective.id
    assert list_payload["page"]["total_count"] == 1
    assert list_payload["terminal_reason"] is None
    assert item["id"] == key_result.id
    assert item["objective_id"] == objective.id
    assert item["goal_id"] == goal.id
    assert item["goal_name"] == goal.name
    assert item["project_id"] == project.id
    assert item["project_name"] == project.name
    assert item["effective_rollup"]["progress_percent"] == 35
    assert item["effective_rollup"]["status"] == "active"
    assert item["effective_rollup"]["basis"] == "stored_key_result"
    assert item["last_activity_at"] is not None
    assert item["last_transition_at"] is not None
    assert item["terminal_reason"] is None
    assert item["links"]["self"] == {
        "tool": "get_key_result",
        "args": {"key_result_id": key_result.id},
    }
    assert item["links"]["objective"] == {
        "tool": "get_objective",
        "args": {"objective_id": objective.id},
    }
    assert item["links"]["key_results"] == {
        "tool": "list_key_results",
        "args": {"objective_id": objective.id},
    }
    assert item["links"]["goal"] == {
        "tool": "get_goal",
        "args": {"identifier": goal.id},
    }
    assert item["links"]["goal_summary"] == {
        "tool": "get_goal_summary",
        "args": {"identifier": goal.id},
    }
    assert item["links"]["project"] == {
        "tool": "get_project",
        "args": {"identifier": project.id},
    }
    assert item["next_steps"][0] == (
        f"Use get_key_result with key_result_id={key_result.id}"
    )
    assert (
        f"Use update_key_result with key_result_id={key_result.id}"
        in item["next_steps"]
    )

    detail_result = await get_key_result.handler({"key_result_id": key_result.id})
    detail_payload = json.loads(detail_result["content"][0]["text"])

    assert detail_payload["id"] == key_result.id
    assert detail_payload["goal_id"] == goal.id
    assert detail_payload["goal_name"] == goal.name
    assert detail_payload["project_id"] == project.id
    assert detail_payload["project_name"] == project.name
    assert detail_payload["effective_rollup"]["progress_percent"] == 35
    assert detail_payload["effective_rollup"]["status"] == "active"
    assert detail_payload["last_activity_at"] is not None
    assert detail_payload["last_transition_at"] is not None
    assert detail_payload["terminal_reason"] is None
    assert detail_payload["completion_context"] is None
    assert detail_payload["links"]["project"] == {
        "tool": "get_project",
        "args": {"identifier": project.id},
    }
    assert detail_payload["next_steps"][0] == (
        f"Use get_key_result with key_result_id={key_result.id}"
    )


@pytest.mark.asyncio
async def test_mcp_key_result_detail_promotes_terminal_reason_and_completion_context(
    db,
) -> None:
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

    project = await project_service.create_project(
        name="MCP Key Result Terminal Project"
    )
    goal = await goal_service.create_goal(
        name="MCP Key Result Terminal Goal",
        project_id=project.id,
    )
    objective = await goal_service.create_objective(
        goal_id=goal.id,
        name="MCP Key Result Terminal Objective",
    )
    key_result = await goal_service.create_key_result(
        objective_id=objective.id,
        name="MCP Key Result Terminal KR",
        progress_percent=100,
    )
    await goal_service.complete_key_result(key_result.id)

    list_result = await list_key_results.handler(
        {"objective_id": objective.id, "limit": 50, "offset": 0}
    )
    list_payload = json.loads(list_result["content"][0]["text"])
    item = list_payload["items"][0]

    assert (
        list_payload["terminal_reason"]
        == "all surfaced key results are already terminal"
    )
    assert item["effective_rollup"]["progress_percent"] == 100
    assert item["effective_rollup"]["status"] == "completed"
    assert item["terminal_reason"] == "key result is already marked completed"
    assert item["next_steps"][0] == (
        f"Use get_key_result with key_result_id={key_result.id}"
    )
    assert (
        f"Use list_key_results with objective_id={objective.id} status=completed"
        in item["next_steps"]
    )

    detail_result = await get_key_result.handler({"key_result_id": key_result.id})
    detail_payload = json.loads(detail_result["content"][0]["text"])

    assert detail_payload["id"] == key_result.id
    assert detail_payload["status"] == "completed"
    assert detail_payload["terminal_reason"] == "key result is already marked completed"
    assert (
        "This key result is terminal."
        in detail_payload["completion_context"]["summary"]
    )
    assert detail_payload["next_steps"][0] == (
        f"Use get_key_result with key_result_id={key_result.id}"
    )
    assert (
        f"Use list_key_results with objective_id={objective.id} status=completed"
        in detail_payload["next_steps"]
    )
