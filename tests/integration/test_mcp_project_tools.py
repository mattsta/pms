"""Integration tests for MCP project lifecycle tools."""

from __future__ import annotations

import json

import pytest

from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.models import PlanFormat, PlanStatus, ProjectStatus
from pms.services.plan_service import PlanService
from pms.services.project_service import ProjectService
from pms.services.task_service import TaskService
from pms.tools.project_tools import (
    get_dashboard,
    get_project,
    get_project_summary,
    list_projects,
    set_services,
)


def _project_item(items: list[dict[str, object]], project_id: str) -> dict[str, object]:
    for item in items:
        if item.get("id") == project_id:
            return item
    raise AssertionError(f"Project {project_id} not found in payload")


@pytest.mark.asyncio
async def test_mcp_project_tools_expose_lifecycle_rollups(db):
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)

    project_service = ProjectService(db, event_store, revision_store, metrics)
    task_service = TaskService(db, event_store, revision_store, metrics)
    plan_service = PlanService(db, event_store, revision_store, metrics)

    set_services(
        project_service=project_service,
        task_service=task_service,
        plan_service=plan_service,
    )

    active_project = await project_service.create_project(name="MCP Active Project")
    active_task = await task_service.create_task(active_project.id, "MCP Active Task")
    await task_service.start_task(active_task.id)

    terminal_project = await project_service.create_project(name="MCP Terminal Project")
    terminal_task = await task_service.create_task(
        terminal_project.id, "MCP Terminal Task"
    )
    await task_service.start_task(terminal_task.id)
    await task_service.complete_task(terminal_task.id)
    await plan_service.create_plan(
        name="MCP Residual Draft Plan",
        description=None,
        status=PlanStatus.DRAFT,
        format=PlanFormat.JSON,
        content={"steps": ["residual planning only"]},
        project_id=terminal_project.id,
    )
    await project_service.update_project(
        terminal_project.id,
        status=ProjectStatus.COMPLETED,
    )

    list_result = await list_projects.handler({})
    list_payload = json.loads(list_result["content"][0]["text"])
    active_item = _project_item(list_payload["items"], active_project.id)
    terminal_item = _project_item(list_payload["items"], terminal_project.id)

    assert active_item["status"] == "active"
    assert active_item["stored_status"] == "active"
    assert active_item["last_activity_at"] is not None
    assert active_item["last_transition_at"] is not None
    assert active_item["terminal_reason"] is None

    assert terminal_item["status"] == "completed"
    assert terminal_item["stored_status"] == "completed"
    assert terminal_item["last_activity_at"] is not None
    assert terminal_item["last_transition_at"] is not None
    assert (
        terminal_item["terminal_reason"]
        == "all linked execution scopes are already terminal"
    )

    active_detail = await get_project.handler({"identifier": active_project.id})
    active_detail_payload = json.loads(active_detail["content"][0]["text"])
    assert active_detail_payload["status"] == "active"
    assert active_detail_payload["stored_status"] == "active"
    assert active_detail_payload["focus_task"]["id"] == active_task.id

    terminal_detail = await get_project.handler({"identifier": terminal_project.id})
    terminal_detail_payload = json.loads(terminal_detail["content"][0]["text"])
    assert terminal_detail_payload["status"] == "completed"
    assert terminal_detail_payload["stored_status"] == "completed"
    assert terminal_detail_payload["focus_task"] is None
    assert (
        terminal_detail_payload["terminal_reason"]
        == "all linked execution scopes are already terminal"
    )

    terminal_summary = await get_project_summary.handler(
        {"identifier": terminal_project.id}
    )
    terminal_summary_payload = json.loads(terminal_summary["content"][0]["text"])
    assert terminal_summary_payload["project"]["status"] == "completed"
    assert terminal_summary_payload["project"]["stored_status"] == "completed"
    assert (
        terminal_summary_payload["project"]["terminal_reason"]
        == "all linked execution scopes are already terminal"
    )
    assert terminal_summary_payload["stats"]["completed_tasks"] == 1

    dashboard_result = await get_dashboard.handler({})
    dashboard_payload = json.loads(dashboard_result["content"][0]["text"])
    assert dashboard_payload["scope"]["population"] == "all_non_archived_retained"
    assert (
        _project_item(dashboard_payload["active_projects"], active_project.id)["status"]
        == "active"
    )
    completed_item = _project_item(
        dashboard_payload["recently_completed_projects"], terminal_project.id
    )
    assert completed_item["status"] == "completed"
    assert completed_item["stored_status"] == "completed"
    assert completed_item["terminal_reason"] == (
        "all linked execution scopes are already terminal"
    )


@pytest.mark.asyncio
async def test_mcp_project_dashboard_reports_terminal_reason_when_all_projects_are_terminal(
    db,
):
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)

    project_service = ProjectService(db, event_store, revision_store, metrics)
    task_service = TaskService(db, event_store, revision_store, metrics)

    set_services(project_service=project_service, task_service=task_service)

    project = await project_service.create_project(
        name="MCP Completed Dashboard Project"
    )
    task = await task_service.create_task(project.id, "MCP Completed Dashboard Task")
    await task_service.start_task(task.id)
    await task_service.complete_task(task.id)
    await project_service.update_project(project.id, status=ProjectStatus.COMPLETED)

    dashboard_result = await get_dashboard.handler({})
    dashboard_payload = json.loads(dashboard_result["content"][0]["text"])

    assert dashboard_payload["active_projects"] == []
    assert dashboard_payload["terminal_reason"] == (
        "all surfaced projects are already terminal"
    )
    completed_item = _project_item(
        dashboard_payload["recently_completed_projects"], project.id
    )
    assert completed_item["status"] == "completed"
    assert completed_item["terminal_reason"] == (
        "all linked execution scopes are already terminal"
    )
