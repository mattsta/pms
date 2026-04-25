"""Integration tests for MCP workflow/checkout/progress tools."""

import pytest

from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.services.project_service import ProjectService
from pms.services.task_service import TaskService
from pms.tools.project_tools import (
    add_task_evidence,
    assign_workflow,
    checkout_task,
    release_task_checkout,
    renew_task_checkout,
    set_services,
    transition_workflow,
    update_task_progress,
)


@pytest.mark.asyncio
async def test_mcp_workflow_and_checkout_tools(db):
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)

    project_service = ProjectService(db, event_store, revision_store, metrics)
    task_service = TaskService(db, event_store, revision_store, metrics)

    set_services(project_service=project_service, task_service=task_service)

    project = await project_service.create_project(name="Workflow Tool Project")
    task = await task_service.create_task(project.id, "Workflow Task")

    assign_result = await assign_workflow.handler(
        {
            "entity_id": task.id,
            "workflow_name": "sdlc",
            "initial_state": "concept",
            "entity_type": "task",
        }
    )
    assert "Assigned workflow" in assign_result["content"][0]["text"]

    transition_result = await transition_workflow.handler(
        {
            "entity_id": task.id,
            "to_state": "idea",
            "triggered_by": "tester",
            "entity_type": "task",
        }
    )
    assert "concept -> idea" in transition_result["content"][0]["text"]

    progress_result = await update_task_progress.handler(
        {
            "task_id": task.id,
            "percent_complete": 20,
            "status_message": "Started exploration",
            "updated_by": "tester",
        }
    )
    assert "Updated progress" in progress_result["content"][0]["text"]

    checkout_result = await checkout_task.handler(
        {"task_id": task.id, "agent_session_id": "agent-a", "lease_seconds": 120}
    )
    assert "Checked out task" in checkout_result["content"][0]["text"]

    renew_result = await renew_task_checkout.handler(
        {"task_id": task.id, "agent_session_id": "agent-a", "lease_seconds": 180}
    )
    assert "Renewed checkout" in renew_result["content"][0]["text"]

    evidence_result = await add_task_evidence.handler(
        {
            "task_id": task.id,
            "evidence_type": "note",
            "reference": "manual-check",
            "description": "Exploration notes added",
            "created_by": "tester",
        }
    )
    assert "Added evidence" in evidence_result["content"][0]["text"]

    release_result = await release_task_checkout.handler(
        {"task_id": task.id, "agent_session_id": "agent-a"}
    )
    assert "Released checkout" in release_result["content"][0]["text"]
