"""Integration tests for task duplicate MCP tools."""

import pytest

from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.services.project_service import ProjectService
from pms.services.task_service import TaskService
from pms.tools.project_tools import (
    find_duplicate_tasks,
    merge_duplicate_tasks,
    preview_merge_duplicate_tasks,
    set_services,
)


@pytest.mark.asyncio
async def test_mcp_duplicate_tools(db):
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)

    project_service = ProjectService(db, event_store, revision_store, metrics)
    task_service = TaskService(db, event_store, revision_store, metrics)
    set_services(project_service=project_service, task_service=task_service)

    project = await project_service.create_project(name="Dup Tool Project")
    primary = await task_service.create_task(project.id, "Duplicate Tool Task")
    dup_one = await task_service.create_task(project.id, "Duplicate Tool Task")
    dup_two = await task_service.create_task(project.id, "Duplicate Tool Task")

    duplicates_result = await find_duplicate_tasks.handler({"project": project.id})
    duplicates_text = duplicates_result["content"][0]["text"]
    assert "Found 1 duplicate group(s)" in duplicates_text
    assert "Suggested primary" in duplicates_text
    assert primary.id in duplicates_text

    preview_result = await preview_merge_duplicate_tasks.handler(
        {
            "primary_task_id": primary.id,
            "duplicate_task_ids": f"{dup_one.id},{dup_two.id}",
        }
    )
    preview_text = preview_result["content"][0]["text"]
    assert "Duplicate Merge Preview" in preview_text

    merge_result = await merge_duplicate_tasks.handler(
        {
            "primary_task_id": primary.id,
            "duplicate_task_ids": f"{dup_one.id},{dup_two.id}",
            "cancel_duplicates": True,
        }
    )
    merge_text = merge_result["content"][0]["text"]
    assert "Links added: 2" in merge_text
    assert "Duplicates cancelled: 2" in merge_text
