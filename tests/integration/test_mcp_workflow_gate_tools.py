"""Integration tests for MCP workflow evidence gate enforcement."""

import pytest

from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.services.project_service import ProjectService
from pms.services.task_service import TaskService
from pms.tools.project_tools import (
    add_task_evidence,
    assign_workflow,
    create_evidence_gate_rule,
    set_services,
    transition_workflow,
)


@pytest.mark.asyncio
async def test_mcp_transition_blocked_by_evidence_gate(db):
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)

    project_service = ProjectService(db, event_store, revision_store, metrics)
    task_service = TaskService(db, event_store, revision_store, metrics)

    set_services(project_service=project_service, task_service=task_service)

    project = await project_service.create_project(name="Evidence Gate Project")
    task = await task_service.create_task(project.id, "Evidence Gate Task")

    assign_result = await assign_workflow.handler(
        {
            "entity_id": task.id,
            "workflow_name": "sdlc",
            "initial_state": "idea",
            "entity_type": "task",
        }
    )
    assert "Assigned workflow" in assign_result["content"][0]["text"]

    gate_result = await create_evidence_gate_rule.handler(
        {
            "workflow_id": "wf_sdlc",
            "entity_type": "task",
            "from_state": "idea",
            "to_state": "planning",
            "evidence_type": "note",
            "min_count": 1,
            "require_success": False,
            "message": "Need a note before planning",
        }
    )
    assert "Created evidence gate rule" in gate_result["content"][0]["text"]

    blocked_result = await transition_workflow.handler(
        {
            "entity_id": task.id,
            "to_state": "planning",
            "triggered_by": "tester",
            "entity_type": "task",
        }
    )
    assert blocked_result.get("is_error") is True
    assert "Need a note before planning" in blocked_result["content"][0]["text"]

    evidence_result = await add_task_evidence.handler(
        {
            "task_id": task.id,
            "evidence_type": "note",
            "reference": "design-note",
            "description": "Planning notes added",
            "created_by": "tester",
        }
    )
    assert "Added evidence" in evidence_result["content"][0]["text"]

    allowed_result = await transition_workflow.handler(
        {
            "entity_id": task.id,
            "to_state": "planning",
            "triggered_by": "tester",
            "entity_type": "task",
        }
    )
    assert "idea -> planning" in allowed_result["content"][0]["text"]
