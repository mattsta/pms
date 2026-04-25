"""Integration tests for task proof bundle MCP tool."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.repositories.test_run_repository import TestRunRepository
from pms.services.project_service import ProjectService
from pms.services.task_evidence_service import TaskEvidenceService
from pms.services.task_service import TaskService
from pms.services.test_run_service import TestRunService
from pms.tools.project_tools import get_task_proof_bundle, set_services


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
async def test_mcp_task_proof_bundle_tool(db) -> None:
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)

    project_service = ProjectService(db, event_store, revision_store, metrics)
    task_service = TaskService(db, event_store, revision_store, metrics)
    test_run_service = TestRunService(db, metrics)
    set_services(
        project_service=project_service,
        task_service=task_service,
        test_run_service=test_run_service,
    )

    project = await project_service.create_project(name="Proof Bundle Tool Project")
    task = await task_service.create_task(project.id, "Proof Bundle Tool Task")

    await _ensure_local_test_server(db)
    run_repo = TestRunRepository(db)
    run_id = "tool-proof-run"
    started = datetime.now(UTC)
    finished = started + timedelta(seconds=1)
    await run_repo.create(
        run_id=run_id,
        server_id="local",
        project_id=project.id,
        config={"test_command": "pytest", "task_ids": [task.id]},
        success=True,
        exit_code=0,
        stdout="ok",
        stderr="",
        duration_seconds=1.0,
        started_at=started.isoformat(),
        finished_at=finished.isoformat(),
        logs={},
        artifacts={},
    )

    evidence_service = TaskEvidenceService(db, metrics)
    await evidence_service.add_test_run_evidence(
        task.id,
        run_id,
        metadata={"log_bytes_total": 2, "artifact_bytes_total": 3},
    )

    result = await get_task_proof_bundle.handler({"task_id": task.id})
    text = result["content"][0]["text"]
    assert "Proof Bundle" in text
    assert task.id in text
