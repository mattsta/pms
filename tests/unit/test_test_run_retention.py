"""Tests for TestRunRetentionService."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from pms.repositories.test_run_repository import TestRunRepository
from pms.services.test_run_retention_service import TestRunRetentionService


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
async def test_prune_by_size(
    db,
    metrics_collector,
    project_repo,
    temp_dir: Path,
) -> None:
    project = await project_repo.create(name="Retention Project")
    await _ensure_local_test_server(db)

    artifact_old = temp_dir / "artifact_old.bin"
    artifact_new = temp_dir / "artifact_new.bin"
    artifact_old.write_bytes(b"x" * 200)
    artifact_new.write_bytes(b"y" * 10)

    run_repo = TestRunRepository(db)
    now = datetime.now(UTC)
    older = now - timedelta(days=2)
    newer = now - timedelta(days=1)

    await run_repo.create(
        run_id="run-old",
        server_id="local",
        project_id=project.id,
        config={"test_command": "pytest"},
        success=True,
        exit_code=0,
        stdout="old-out",
        stderr="",
        duration_seconds=1.0,
        started_at=older.isoformat(),
        finished_at=older.isoformat(),
        logs={str(temp_dir / "old.log"): "x" * 100},
        artifacts={"artifact_old.bin": str(artifact_old)},
    )
    await run_repo.create(
        run_id="run-new",
        server_id="local",
        project_id=project.id,
        config={"test_command": "pytest"},
        success=True,
        exit_code=0,
        stdout="new-out",
        stderr="",
        duration_seconds=1.0,
        started_at=newer.isoformat(),
        finished_at=newer.isoformat(),
        logs={str(temp_dir / "new.log"): "y" * 10},
        artifacts={"artifact_new.bin": str(artifact_new)},
    )

    service = TestRunRetentionService(db, metrics_collector)
    summary = await service.prune(
        max_log_bytes=50,
        max_artifact_bytes=50,
        max_age_days=0,
        dry_run=False,
    )

    assert summary.runs_pruned >= 1
    assert summary.log_bytes_pruned > 0
    assert summary.artifact_bytes_pruned > 0

    row_old = await run_repo.get_by_id("run-old")
    assert row_old is not None
    logs_old = json.loads(row_old["logs"])
    log_entry = logs_old[str(temp_dir / "old.log")]
    assert log_entry["content"] == ""
    assert "pruned_at" in log_entry
    assert row_old["stdout"] == ""

    assert not artifact_old.exists()

    row_new = await run_repo.get_by_id("run-new")
    assert row_new is not None
    logs_new = json.loads(row_new["logs"])
    assert logs_new[str(temp_dir / "new.log")] == "y" * 10
    assert artifact_new.exists()


@pytest.mark.asyncio
async def test_prune_rolls_back_when_metrics_flush_fails(
    db,
    metrics_collector,
    project_repo,
    temp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await project_repo.create(name="Retention Atomic Metrics Project")
    await _ensure_local_test_server(db)

    artifact_path = temp_dir / "atomic-artifact.bin"
    artifact_path.write_bytes(b"x" * 200)

    run_repo = TestRunRepository(db)
    finished = datetime.now(UTC) - timedelta(days=2)
    await run_repo.create(
        run_id="run-atomic-metrics",
        server_id="local",
        project_id=project.id,
        config={"test_command": "pytest"},
        success=True,
        exit_code=0,
        stdout="before-out",
        stderr="before-err",
        duration_seconds=1.0,
        started_at=finished.isoformat(),
        finished_at=finished.isoformat(),
        logs={str(temp_dir / "atomic.log"): "x" * 100},
        artifacts={"atomic-artifact.bin": str(artifact_path)},
    )

    service = TestRunRetentionService(db, metrics_collector)

    async def fail_flush(*args, **kwargs):
        raise RuntimeError("metrics flush failed")

    monkeypatch.setattr(service.metrics, "flush", fail_flush)

    with pytest.raises(RuntimeError, match="metrics flush failed"):
        await service.prune(
            max_log_bytes=1,
            max_artifact_bytes=1,
            max_age_days=0,
            dry_run=False,
        )

    row = await run_repo.get_by_id("run-atomic-metrics")
    assert row is not None
    assert row["stdout"] == "before-out"
    assert row["stderr"] == "before-err"
    assert json.loads(row["logs"]) == {str(temp_dir / "atomic.log"): "x" * 100}
    assert json.loads(row["artifacts"]) == {"atomic-artifact.bin": str(artifact_path)}
    assert artifact_path.exists()


@pytest.mark.asyncio
async def test_prune_rolls_back_all_runs_when_late_update_fails(
    db,
    metrics_collector,
    project_repo,
    temp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await project_repo.create(name="Retention Atomic Update Project")
    await _ensure_local_test_server(db)

    artifact_one = temp_dir / "artifact-one.bin"
    artifact_two = temp_dir / "artifact-two.bin"
    artifact_one.write_bytes(b"a" * 200)
    artifact_two.write_bytes(b"b" * 180)

    run_repo = TestRunRepository(db)
    finished_one = datetime.now(UTC) - timedelta(days=3)
    finished_two = datetime.now(UTC) - timedelta(days=2)
    await run_repo.create(
        run_id="run-atomic-one",
        server_id="local",
        project_id=project.id,
        config={"test_command": "pytest"},
        success=True,
        exit_code=0,
        stdout="one-out",
        stderr="one-err",
        duration_seconds=1.0,
        started_at=finished_one.isoformat(),
        finished_at=finished_one.isoformat(),
        logs={str(temp_dir / "one.log"): "a" * 90},
        artifacts={"artifact-one.bin": str(artifact_one)},
    )
    await run_repo.create(
        run_id="run-atomic-two",
        server_id="local",
        project_id=project.id,
        config={"test_command": "pytest"},
        success=True,
        exit_code=0,
        stdout="two-out",
        stderr="two-err",
        duration_seconds=1.0,
        started_at=finished_two.isoformat(),
        finished_at=finished_two.isoformat(),
        logs={str(temp_dir / "two.log"): "b" * 80},
        artifacts={"artifact-two.bin": str(artifact_two)},
    )

    service = TestRunRetentionService(db, metrics_collector)
    original_update_payloads = service._repo.update_payloads
    call_count = 0

    async def fail_second_update(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("payload update failed")
        return await original_update_payloads(*args, **kwargs)

    monkeypatch.setattr(service._repo, "update_payloads", fail_second_update)

    with pytest.raises(RuntimeError, match="payload update failed"):
        await service.prune(
            max_log_bytes=1,
            max_artifact_bytes=1,
            max_age_days=0,
            dry_run=False,
        )

    row_one = await run_repo.get_by_id("run-atomic-one")
    row_two = await run_repo.get_by_id("run-atomic-two")
    assert row_one is not None
    assert row_two is not None
    assert row_one["stdout"] == "one-out"
    assert row_two["stdout"] == "two-out"
    assert json.loads(row_one["logs"]) == {str(temp_dir / "one.log"): "a" * 90}
    assert json.loads(row_two["logs"]) == {str(temp_dir / "two.log"): "b" * 80}
    assert json.loads(row_one["artifacts"]) == {"artifact-one.bin": str(artifact_one)}
    assert json.loads(row_two["artifacts"]) == {"artifact-two.bin": str(artifact_two)}
    assert artifact_one.exists()
    assert artifact_two.exists()


@pytest.mark.asyncio
async def test_get_usage_summary(
    db,
    metrics_collector,
    project_repo,
    temp_dir: Path,
) -> None:
    project = await project_repo.create(name="Usage Summary Project")
    await _ensure_local_test_server(db)

    artifact_path = temp_dir / "artifact_big.bin"
    artifact_path.write_bytes(b"a" * 10)
    missing_path = temp_dir / "missing.bin"

    run_repo = TestRunRepository(db)
    now = datetime.now(UTC)
    older = now - timedelta(minutes=5)

    await run_repo.create(
        run_id="run-big",
        server_id="local",
        project_id=project.id,
        config={"test_command": "pytest"},
        success=True,
        exit_code=0,
        stdout="out1",
        stderr="err1",
        duration_seconds=1.0,
        started_at=older.isoformat(),
        finished_at=older.isoformat(),
        logs={"log1": "abcd"},
        artifacts={
            "artifact_big.bin": {
                "local_path": str(artifact_path),
                "size_bytes": 12,
            },
            "missing.bin": {"local_path": str(missing_path), "size_bytes": 7},
        },
    )
    await run_repo.create(
        run_id="run-small",
        server_id="local",
        project_id=project.id,
        config={"test_command": "pytest"},
        success=True,
        exit_code=0,
        stdout="o",
        stderr="",
        duration_seconds=1.0,
        started_at=now.isoformat(),
        finished_at=now.isoformat(),
        logs={"log2": {"content": "zz"}},
        artifacts={},
    )

    service = TestRunRetentionService(db, metrics_collector)
    summary = await service.get_usage(limit=10, sort="largest")

    assert summary.total_runs == 2
    assert summary.sorted_by == "largest"
    assert summary.total_stdout_bytes == 5
    assert summary.total_stderr_bytes == 4
    assert summary.total_log_bytes == 6
    assert summary.total_log_bytes_combined == 15
    assert summary.total_artifact_bytes == 10
    assert summary.total_artifact_recorded_bytes == 19

    assert len(summary.items) == 2
    assert summary.items[0].run_id == "run-big"
    assert summary.items[0].artifact_recorded_bytes == 19
    assert summary.items[0].artifacts_missing == 1
    assert summary.items[1].run_id == "run-small"


@pytest.mark.asyncio
async def test_get_usage_rejects_invalid_sort(db, metrics_collector):
    service = TestRunRetentionService(db, metrics_collector)

    with pytest.raises(ValueError, match="Unsupported retention sort 'oldest'"):
        await service.get_usage(limit=10, sort="oldest")  # type: ignore[arg-type]
