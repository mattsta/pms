"""Integration tests for MCP queue tools."""

from __future__ import annotations

import json

import pytest

from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.repositories.saved_search_repository import SavedSearchRepository
from pms.services.project_service import ProjectService
from pms.services.queue_service import QueueService
from pms.services.saved_search_service import SavedSearchService
from pms.services.task_service import TaskService
from pms.tools.project_tools import (
    create_saved_search,
    get_dashboard,
    get_queue_preset,
    list_queue_presets,
    run_saved_search,
    set_services,
)


@pytest.mark.asyncio
async def test_mcp_queue_tools(db):
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)

    project_service = ProjectService(db, event_store, revision_store, metrics)
    task_service = TaskService(db, event_store, revision_store, metrics)
    saved_repo = SavedSearchRepository(db)
    saved_service = SavedSearchService(saved_repo, task_service, metrics, db)
    queue_service = QueueService(task_service)

    set_services(
        project_service=project_service,
        task_service=task_service,
        saved_search_service=saved_service,
        queue_service=queue_service,
    )

    project = await project_service.create_project(name="Queue Tool Project")
    task = await task_service.create_task(project.id, "Queue Task One")
    await task_service.create_task(project.id, "Queue Task Two")

    create_result = await create_saved_search.handler(
        {
            "name": "Queue Tool Search",
            "filters": json.dumps({"query": "Queue Task One"}),
        }
    )
    create_text = create_result["content"][0]["text"]
    assert "Saved search created" in create_text

    queue_id = create_text.split("ID:")[-1].strip(" )")

    run_result = await run_saved_search.handler({"queue_id": queue_id, "limit": 5})
    run_text = run_result["content"][0]["text"]
    assert task.id in run_text

    presets_result = await list_queue_presets.handler({"limit": 5})
    presets_payload = json.loads(presets_result["content"][0]["text"])
    assert presets_payload["items"]

    dashboard_result = await get_dashboard.handler({})
    dashboard_payload = json.loads(dashboard_result["content"][0]["text"])
    assert dashboard_payload["scope"]["population"] == "all_non_archived_retained"
    assert dashboard_payload["active_projects"]

    preset_result = await get_queue_preset.handler({"preset": "ready", "limit": 5})
    preset_payload = json.loads(preset_result["content"][0]["text"])
    assert preset_payload["preset"]["name"] == "ready"
