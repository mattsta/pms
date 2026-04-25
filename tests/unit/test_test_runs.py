"""Tests for TestRunService."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from pms.repositories.test_run_repository import TestRunRepository
from pms.services.test_run_service import TestRunService


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
async def test_list_and_get_test_runs(
    db,
    metrics_collector,
    project_repo,
) -> None:
    project = await project_repo.create(name="Test Run Project")
    await _ensure_local_test_server(db)

    run_repo = TestRunRepository(db)
    run_id = "run-service-1"
    started = datetime.now(UTC)
    finished = started + timedelta(seconds=2)
    await run_repo.create(
        run_id=run_id,
        server_id="local",
        project_id=project.id,
        config={"test_command": "pytest", "runner": "local", "task_ids": []},
        success=True,
        exit_code=0,
        stdout="ok",
        stderr="",
        duration_seconds=2.0,
        started_at=started.isoformat(),
        finished_at=finished.isoformat(),
        logs={"/tmp/test.log": "log-content"},
        artifacts={"artifact.txt": "/tmp/artifact.txt"},
    )

    service = TestRunService(db, metrics_collector)

    listed = await service.list_test_runs(
        project_id=project.id,
        include_output=False,
        include_logs=False,
        include_artifacts=False,
    )

    assert listed.total_count == 1
    record = listed.items[0]
    assert record.command == "pytest"
    assert record.stdout is None
    assert record.logs == {}
    assert record.artifacts == {}

    fetched = await service.get_test_run(
        run_id,
        include_output=True,
        include_logs=True,
        include_artifacts=True,
    )

    assert fetched is not None
    assert fetched.stdout == "ok"
    log_entry = fetched.logs["/tmp/test.log"]
    assert log_entry["content"] == "log-content"
    assert log_entry["size_bytes"] == len(b"log-content")
    artifact_entry = fetched.artifacts["artifact.txt"]
    assert artifact_entry["local_path"] == "/tmp/artifact.txt"


@pytest.mark.asyncio
async def test_list_and_get_test_runs_ignore_observational_metrics_flush_failures(
    db,
    metrics_collector,
    project_repo,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await project_repo.create(name="Test Run Observational Project")
    await _ensure_local_test_server(db)

    run_repo = TestRunRepository(db)
    run_id = "run-service-observational"
    started = datetime.now(UTC)
    finished = started + timedelta(seconds=2)
    await run_repo.create(
        run_id=run_id,
        server_id="local",
        project_id=project.id,
        config={"test_command": "pytest", "runner": "local", "task_ids": []},
        success=True,
        exit_code=0,
        stdout="ok",
        stderr="",
        duration_seconds=2.0,
        started_at=started.isoformat(),
        finished_at=finished.isoformat(),
        logs={},
        artifacts={},
    )

    service = TestRunService(db, metrics_collector)

    async def fail_flush() -> int:
        raise RuntimeError("metrics flush failed")

    monkeypatch.setattr(service.metrics, "flush", fail_flush)

    listed = await service.list_test_runs(project_id=project.id)
    fetched = await service.get_test_run(run_id)

    assert listed.total_count == 1
    assert listed.items[0].id == run_id
    assert fetched is not None
    assert fetched.id == run_id


@pytest.mark.asyncio
async def test_create_rolls_back_when_revision_save_fails(
    db,
    project_repo,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await project_repo.create(name="Test Run Rollback Project")
    await _ensure_local_test_server(db)

    run_repo = TestRunRepository(db)
    run_id = "run-create-rollback"
    started = datetime.now(UTC)
    finished = started + timedelta(seconds=1)

    async def fail_revision_save(*args, **kwargs):
        raise RuntimeError("revision save failed")

    monkeypatch.setattr(run_repo._revisions, "save_revision", fail_revision_save)

    with pytest.raises(RuntimeError, match="revision save failed"):
        await run_repo.create(
            run_id=run_id,
            server_id="local",
            project_id=project.id,
            config={"test_command": "pytest"},
            success=True,
            exit_code=0,
            stdout="out",
            stderr="",
            duration_seconds=1.0,
            started_at=started.isoformat(),
            finished_at=finished.isoformat(),
            logs={"/tmp/create.log": "log"},
            artifacts={"artifact.txt": "/tmp/artifact.txt"},
        )

    row = await run_repo.get_by_id(run_id)
    assert row is None
    events = await run_repo._events.get_events("test_run", run_id)
    assert events == []
    assert await run_repo._revisions.get_revision_count("test_run", run_id) == 0


@pytest.mark.asyncio
async def test_create_in_transaction_requires_owned_transaction(db) -> None:
    run_repo = TestRunRepository(db)

    with pytest.raises(RuntimeError, match="requires an active transaction"):
        await run_repo._create_in_transaction(
            run_id="run-direct-helper",
            server_id="local",
            project_id=None,
            config={"test_command": "pytest"},
            success=True,
            exit_code=0,
            stdout="out",
            stderr="",
            duration_seconds=1.0,
            started_at=datetime.now(UTC).isoformat(),
            finished_at=datetime.now(UTC).isoformat(),
            logs={},
            artifacts={},
        )


@pytest.mark.asyncio
async def test_update_payloads_rolls_back_when_event_append_fails(
    db,
    project_repo,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await project_repo.create(name="Test Run Update Rollback Project")
    await _ensure_local_test_server(db)

    run_repo = TestRunRepository(db)
    run_id = "run-update-rollback"
    started = datetime.now(UTC)
    finished = started + timedelta(seconds=1)
    await run_repo.create(
        run_id=run_id,
        server_id="local",
        project_id=project.id,
        config={"test_command": "pytest"},
        success=True,
        exit_code=0,
        stdout="before-out",
        stderr="before-err",
        duration_seconds=1.0,
        started_at=started.isoformat(),
        finished_at=finished.isoformat(),
        logs={"/tmp/before.log": "before"},
        artifacts={"artifact.txt": "/tmp/before.txt"},
    )

    async def fail_event_append(*args, **kwargs):
        raise RuntimeError("event append failed")

    monkeypatch.setattr(run_repo._events, "append", fail_event_append)

    with pytest.raises(RuntimeError, match="event append failed"):
        await run_repo.update_payloads(
            run_id=run_id,
            stdout="after-out",
            stderr="after-err",
            logs={"/tmp/after.log": "after"},
            artifacts={"artifact.txt": "/tmp/after.txt"},
        )

    row = await run_repo.get_by_id(run_id)
    assert row is not None
    assert row["stdout"] == "before-out"
    assert row["stderr"] == "before-err"
    assert json.loads(row["logs"]) == {"/tmp/before.log": "before"}
    assert json.loads(row["artifacts"]) == {"artifact.txt": "/tmp/before.txt"}
    assert await run_repo._revisions.get_revision_count("test_run", run_id) == 1


@pytest.mark.asyncio
async def test_update_payloads_in_transaction_requires_owned_transaction(
    db,
    project_repo,
) -> None:
    project = await project_repo.create(name="Test Run Update Direct Helper Project")
    await _ensure_local_test_server(db)

    run_repo = TestRunRepository(db)
    run_id = "run-update-direct-helper"
    started = datetime.now(UTC)
    finished = started + timedelta(seconds=1)
    await run_repo.create(
        run_id=run_id,
        server_id="local",
        project_id=project.id,
        config={"test_command": "pytest"},
        success=True,
        exit_code=0,
        stdout="before-out",
        stderr="before-err",
        duration_seconds=1.0,
        started_at=started.isoformat(),
        finished_at=finished.isoformat(),
        logs={},
        artifacts={},
    )

    with pytest.raises(RuntimeError, match="requires an active transaction"):
        await run_repo._update_payloads_in_transaction(
            run_id=run_id,
            stdout="after-out",
            stderr="after-err",
            logs={},
            artifacts={},
        )


@pytest.mark.asyncio
async def test_service_create_rolls_back_when_metrics_flush_fails(
    db,
    metrics_collector,
    project_repo,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await project_repo.create(name="Test Run Service Rollback Project")
    await _ensure_local_test_server(db)

    service = TestRunService(db, metrics_collector)
    run_id = "run-service-rollback"
    started = datetime.now(UTC)
    finished = started + timedelta(seconds=1)

    async def fail_flush() -> int:
        raise RuntimeError("metrics flush failed")

    monkeypatch.setattr(service.metrics, "flush", fail_flush)

    with pytest.raises(RuntimeError, match="metrics flush failed"):
        await service.create_test_run(
            run_id=run_id,
            server_id="local",
            project_id=project.id,
            config={"test_command": "pytest"},
            success=True,
            exit_code=0,
            stdout="out",
            stderr="",
            duration_seconds=1.0,
            started_at=started,
            finished_at=finished,
            logs={"/tmp/service.log": "log"},
            artifacts={"artifact.txt": "/tmp/service.txt"},
        )

    row = await service._repo.get_by_id(run_id)
    assert row is None
    assert await service._repo._revisions.get_revision_count("test_run", run_id) == 0
