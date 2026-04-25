"""Integration tests for MCP test run tools."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.services.project_service import ProjectService
from pms.services.task_service import TaskService
from pms.services.test_run_retention_service import TestRunRetentionService
from pms.services.test_run_service import TestRunService
from pms.tools.project_tools import (
    create_test_run,
    get_test_run,
    get_test_run_retention,
    list_test_runs,
    prune_test_runs,
    set_services,
)


async def _ensure_local_test_server(db) -> None:
    row = await db.fetch_one(
        "SELECT id FROM test_servers WHERE id = ?",
        ("local",),
    )
    if row:
        return
    await db.execute(
        """
        INSERT INTO test_servers (
            id, name, config, state, region,
            availability_zone, hourly_price, estimated_cost, launched_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "local",
            "local",
            '{"kind": "local"}',
            "running",
            "local",
            "local",
            0.0,
            0.0,
            datetime.now(UTC).isoformat(),
        ),
    )
    await db.commit()


@pytest.mark.asyncio
async def test_mcp_test_run_tools(db):
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)

    project_service = ProjectService(db, event_store, revision_store, metrics)
    task_service = TaskService(db, event_store, revision_store, metrics)
    test_run_service = TestRunService(db, metrics)
    retention_service = TestRunRetentionService(db, metrics)

    set_services(
        project_service=project_service,
        task_service=task_service,
        test_run_service=test_run_service,
        test_run_retention_service=retention_service,
    )

    project = await project_service.create_project(name="MCP Test Runs")
    await _ensure_local_test_server(db)

    run_id = "run-mcp-1"
    started = datetime.now(UTC)
    finished = started + timedelta(seconds=2)
    create_result = await create_test_run.handler(
        {
            "run_id": run_id,
            "server_id": "local",
            "project_id": project.id,
            "success": "passed",
            "exit_code": 0,
            "started_at": started.isoformat(),
            "finished_at": finished.isoformat(),
            "command": "pytest -q",
            "runner": "mcp",
            "logs": json.dumps({"/tmp/mcp.log": "mcp-log"}),
            "artifacts": json.dumps({}),
        }
    )
    create_text = create_result["content"][0]["text"]
    assert run_id in create_text

    list_result = await list_test_runs.handler({"project_id": project.id})
    list_text = list_result["content"][0]["text"]
    assert run_id in list_text

    detail_result = await get_test_run.handler({"run_id": run_id, "include_logs": True})
    detail_text = detail_result["content"][0]["text"]
    assert "Test Run:" in detail_text
    assert "mcp-log" in detail_text

    prune_result = await prune_test_runs.handler({"max_log_bytes": 1, "dry_run": True})
    prune_text = prune_result["content"][0]["text"]
    assert "Test Run Prune" in prune_text

    retention_result = await get_test_run_retention.handler(
        {"limit": 5, "sort": "largest"}
    )
    retention_text = retention_result["content"][0]["text"]
    assert "Test Run Retention" in retention_text
    assert run_id in retention_text
