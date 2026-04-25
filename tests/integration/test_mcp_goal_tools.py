"""Integration tests for MCP goal lifecycle tools."""

from __future__ import annotations

import json

import pytest

from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.services.goal_service import GoalService
from pms.services.project_service import ProjectService
from pms.services.task_service import TaskService
from pms.tools.project_tools import get_goal, get_goal_summary, list_goals, set_services


@pytest.mark.asyncio
async def test_mcp_goal_summary_exposes_lifecycle_rollups(db) -> None:
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

    active_project = await project_service.create_project(
        name="MCP Goal Active Project"
    )
    active_goal = await goal_service.create_goal(
        name="MCP Goal Active Goal",
        project_id=active_project.id,
        progress_percent=10,
    )
    active_task = await task_service.create_task(active_project.id, "Execution Task")
    await task_service.start_task(active_task.id)
    await task_service.update_task_progress(
        active_task.id,
        percent_complete=45,
        status_message="Implementing",
        updated_by="tester",
    )

    active_result = await get_goal_summary.handler({"identifier": active_goal.id})
    active_payload = json.loads(active_result["content"][0]["text"])

    assert active_payload["goal"]["id"] == active_goal.id
    assert active_payload["goal"]["status"] == "active"
    assert active_payload["effective_rollup"]["progress_percent"] == 45
    assert active_payload["effective_rollup"]["status"] == "active"
    assert active_payload["effective_rollup"]["basis"] == "execution_projection"
    assert active_payload["last_activity_at"] is not None
    assert active_payload["last_transition_at"] is not None
    assert active_payload["terminal_reason"] is None
    assert active_payload["completion_context"] is None
    assert active_payload["execution"]["focus_task"]["id"] == active_task.id
    assert active_payload["links"]["self"] == {
        "tool": "get_goal_summary",
        "args": {"identifier": active_goal.id},
    }
    assert active_payload["links"]["goal"] == {
        "tool": "get_goal",
        "args": {"identifier": active_goal.id},
    }
    assert active_payload["links"]["project"] == {
        "tool": "get_project",
        "args": {"identifier": active_project.id},
    }
    assert active_payload["next_steps"][0] == (
        f"Use get_task with identifier={active_task.id}"
    )

    list_result = await list_goals.handler({"limit": 50, "offset": 0})
    list_payload = json.loads(list_result["content"][0]["text"])
    list_item = next(
        item for item in list_payload["items"] if item["id"] == active_goal.id
    )

    assert list_payload["scope"]["kind"] == "mcp_goal_list"
    assert list_payload["page"]["total_count"] >= 1
    assert list_item["effective_rollup"]["progress_percent"] == 45
    assert list_item["effective_rollup"]["status"] == "active"
    assert list_item["last_activity_at"] is not None
    assert list_item["last_transition_at"] is not None
    assert list_item["terminal_reason"] is None
    assert list_item["links"]["self"] == {
        "tool": "get_goal",
        "args": {"identifier": active_goal.id},
    }
    assert list_item["links"]["summary"] == {
        "tool": "get_goal_summary",
        "args": {"identifier": active_goal.id},
    }
    assert (
        list_item["next_steps"][0] == f"Use get_task with identifier={active_task.id}"
    )

    detail_result = await get_goal.handler({"identifier": active_goal.id})
    detail_payload = json.loads(detail_result["content"][0]["text"])

    assert detail_payload["id"] == active_goal.id
    assert detail_payload["stats"]["objective_count"] == 0
    assert detail_payload["effective_rollup"]["progress_percent"] == 45
    assert detail_payload["effective_hierarchy"]["average_progress"] == 45.0
    assert detail_payload["execution"]["focus_task"]["id"] == active_task.id
    assert detail_payload["terminal_reason"] is None
    assert detail_payload["links"]["self"] == {
        "tool": "get_goal",
        "args": {"identifier": active_goal.id},
    }
    assert detail_payload["links"]["summary"] == {
        "tool": "get_goal_summary",
        "args": {"identifier": active_goal.id},
    }


@pytest.mark.asyncio
async def test_mcp_goal_summary_promotes_terminal_reason_and_completion_context(
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

    project = await project_service.create_project(name="MCP Goal Terminal Project")
    goal = await goal_service.create_goal(
        name="MCP Goal Terminal Goal",
        project_id=project.id,
    )
    task = await task_service.create_task(project.id, "Done Task")
    await task_service.start_task(task.id)
    await task_service.complete_task(task.id)

    result = await get_goal_summary.handler({"identifier": goal.id})
    payload = json.loads(result["content"][0]["text"])

    assert payload["goal"]["id"] == goal.id
    assert payload["effective_rollup"]["progress_percent"] == 100
    assert payload["effective_rollup"]["status"] == "completed"
    assert payload["effective_rollup"]["basis"] == "execution_terminal"
    assert payload["execution"]["terminal_reason"] == (
        "all execution tasks are already complete"
    )
    assert payload["execution"]["focus_task"] is None
    assert payload["terminal_reason"] == "all execution tasks are already complete"
    assert "This goal is terminal." in payload["completion_context"]["summary"]
    assert payload["last_activity_at"] is not None
    assert payload["last_transition_at"] is not None
    assert payload["next_steps"][0] == f"Use get_goal with identifier={goal.id}"
    assert "Use list_goals with status=completed" in payload["next_steps"]

    list_result = await list_goals.handler({"limit": 50, "offset": 0})
    list_payload = json.loads(list_result["content"][0]["text"])
    list_item = next(item for item in list_payload["items"] if item["id"] == goal.id)

    assert list_item["effective_rollup"]["progress_percent"] == 100
    assert list_item["effective_rollup"]["status"] == "completed"
    assert list_item["terminal_reason"] == "all execution tasks are already complete"
    assert list_item["next_steps"][0] == f"Use get_goal with identifier={goal.id}"
    assert "Use list_goals with status=completed" in list_item["next_steps"]

    detail_result = await get_goal.handler({"identifier": goal.id})
    detail_payload = json.loads(detail_result["content"][0]["text"])

    assert detail_payload["id"] == goal.id
    assert detail_payload["effective_rollup"]["basis"] == "execution_terminal"
    assert detail_payload["execution"]["terminal_reason"] == (
        "all execution tasks are already complete"
    )
    assert (
        detail_payload["terminal_reason"] == "all execution tasks are already complete"
    )
    assert "This goal is terminal." in detail_payload["completion_context"]["summary"]
    assert detail_payload["next_steps"][0] == f"Use get_goal with identifier={goal.id}"
