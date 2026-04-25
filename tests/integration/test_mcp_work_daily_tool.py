"""Integration tests for work daily MCP tool."""

import json

import pytest

from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.services.lineage_service import LineageService
from pms.services.organization_service import OrganizationService
from pms.services.portfolio_service import PortfolioService
from pms.services.program_service import ProgramService
from pms.services.project_service import ProjectService
from pms.services.queue_service import QueueService
from pms.services.task_service import TaskService
from pms.services.test_run_retention_service import TestRunRetentionService
from pms.services.work_snapshot_service import WorkSnapshotService
from pms.tools.project_tools import get_work_daily, set_services


@pytest.mark.asyncio
async def test_work_daily_tool(db):
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)

    project_service = ProjectService(db, event_store, revision_store, metrics)
    task_service = TaskService(db, event_store, revision_store, metrics)
    organization_service = OrganizationService(db, event_store, revision_store, metrics)
    portfolio_service = PortfolioService(db, event_store, revision_store, metrics)
    program_service = ProgramService(db, event_store, revision_store, metrics)
    lineage_service = LineageService(db, event_store, revision_store, metrics)
    retention_service = TestRunRetentionService(db, metrics)
    snapshot_service = WorkSnapshotService(
        db,
        metrics,
        project_service=project_service,
        organization_service=organization_service,
        program_service=program_service,
        portfolio_service=portfolio_service,
        lineage_service=lineage_service,
        retention_service=retention_service,
    )
    queue_service = QueueService(task_service)

    set_services(
        project_service=project_service,
        task_service=task_service,
        organization_service=organization_service,
        portfolio_service=portfolio_service,
        program_service=program_service,
        queue_service=queue_service,
        work_snapshot_service=snapshot_service,
    )

    project = await project_service.create_project(name="Daily Tool Project")
    await task_service.create_task(project.id, "Daily Tool Task")

    result = await get_work_daily.handler(
        {"scope_type": "project", "scope_id": project.id, "queue_limit": 3}
    )
    payload = json.loads(result["content"][0]["text"])
    assert "snapshot" in payload
    assert "queues" in payload
