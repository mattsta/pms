"""Tests for task evidence and local test runner."""

from __future__ import annotations

import contextlib
import os
import shlex
import signal
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from pms.repositories.task_evidence_repository import TaskEvidenceRepository
from pms.repositories.test_run_repository import TestRunRepository
from pms.services.task_evidence_service import TaskEvidenceService
from pms.testing import LocalTestConfig, LocalTestRunner


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _wait_for_pid_exit(pid: int, *, timeout_seconds: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not _pid_exists(pid):
            return True
        time.sleep(0.05)
    return not _pid_exists(pid)


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


async def _count_task_evidence_rows(db, task_ids: list[str]) -> int:
    placeholders = ", ".join("?" * len(task_ids))
    row = await db.fetch_one(
        f"SELECT COUNT(*) AS count FROM task_evidence WHERE task_id IN ({placeholders})",
        tuple(task_ids),
    )
    return int(row["count"]) if row else 0


@pytest.mark.asyncio
async def test_task_evidence_includes_test_run(
    db,
    metrics_collector,
    project_repo,
    task_repo,
) -> None:
    project = await project_repo.create(name="Evidence Project")
    task = await task_repo.create(project.id, "Evidence Task")

    await _ensure_local_test_server(db)

    run_repo = TestRunRepository(db)
    run_id = "run-evidence-1"
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

    evidence_service = TaskEvidenceService(db, metrics_collector)
    await evidence_service.add_test_run_evidence(task.id, run_id)

    page = await evidence_service.list_evidence(
        task_id=task.id,
        include_test_runs=True,
        include_output=True,
    )

    assert page.items
    item = page.items[0]
    assert item.test_run is not None
    assert item.test_run.id == run_id
    assert item.test_run.stdout == "ok"


@pytest.mark.asyncio
async def test_local_test_runner_attaches_evidence(
    db,
    event_store,
    metrics_collector,
    project_repo,
    task_repo,
    temp_dir: Path,
) -> None:
    project = await project_repo.create(name="Local Test Project")
    task = await task_repo.create(project.id, "Local Test Task")

    runner = LocalTestRunner(db=db, event_store=event_store, metrics=metrics_collector)
    command = f"{sys.executable} -c \"print('ok')\""
    log_path = temp_dir / "run.log"
    artifact_path = temp_dir / "artifact.txt"
    log_path.write_text("log-data")
    artifact_path.write_text("artifact-data")
    config = LocalTestConfig(
        project_path=temp_dir,
        test_command=command,
        project_id=project.id,
        task_ids=(task.id,),
        capture_logs=(str(log_path),),
        save_artifacts=(str(artifact_path),),
    )

    result = await runner.run(config)

    assert result.success is True

    evidence_repo = TaskEvidenceRepository(db)
    evidence_page = await evidence_repo.list_by_task(task.id)
    assert evidence_page.items
    assert evidence_page.items[0].evidence_type == "test_run"
    assert evidence_page.items[0].reference == result.run_id
    evidence_metadata = evidence_page.items[0].metadata
    assert evidence_metadata["stdout_bytes"] > 0
    assert str(log_path) in evidence_metadata["logs"]
    log_meta = evidence_metadata["logs"][str(log_path)]
    assert log_meta["size_bytes"] == log_path.stat().st_size
    assert "captured_at" in log_meta
    assert str(artifact_path) in evidence_metadata["artifacts"]
    artifact_meta = evidence_metadata["artifacts"][str(artifact_path)]
    assert artifact_meta["size_bytes"] == artifact_path.stat().st_size

    run_repo = TestRunRepository(db)
    rows = await run_repo.get_by_ids([result.run_id])
    assert rows
    assert "ok" in (rows[0].get("stdout") or "")


@pytest.mark.asyncio
async def test_local_test_runner_kills_spawned_children_on_timeout(
    db,
    event_store,
    metrics_collector,
    temp_dir: Path,
) -> None:
    runner = LocalTestRunner(db=db, event_store=event_store, metrics=metrics_collector)
    child_pid_file = temp_dir / "child.pid"
    parent_script = temp_dir / "spawn_child.py"
    parent_script.write_text(
        (
            "import pathlib, subprocess, sys, time\n"
            "pid_path = pathlib.Path(sys.argv[1])\n"
            "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
            "pid_path.write_text(str(child.pid), encoding='utf-8')\n"
            "time.sleep(30)\n"
        ),
        encoding="utf-8",
    )
    command = (
        f"{shlex.quote(sys.executable)} "
        f"{shlex.quote(str(parent_script))} "
        f"{shlex.quote(str(child_pid_file))}"
    )
    config = LocalTestConfig(
        project_path=temp_dir,
        test_command=command,
        timeout=1.0,
    )

    result = await runner.run(config)

    assert result.success is False
    assert "Timed out after 1s" in (result.stderr or "")
    child_pid = int(child_pid_file.read_text(encoding="utf-8"))
    assert _wait_for_pid_exit(child_pid), (
        "child subprocess leaked after LocalTestRunner timeout"
    )

    with contextlib.suppress(OSError):
        os.kill(child_pid, signal.SIGKILL)


@pytest.mark.asyncio
async def test_local_test_runner_ignores_observational_metrics_flush_failures(
    db,
    event_store,
    metrics_collector,
    temp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = LocalTestRunner(db=db, event_store=event_store, metrics=metrics_collector)
    command = f"{sys.executable} -c \"print('ok')\""
    config = LocalTestConfig(
        project_path=temp_dir,
        test_command=command,
    )

    async def fail_flush(*args, **kwargs):
        raise RuntimeError("metrics flush failed")

    monkeypatch.setattr(runner.metrics, "flush", fail_flush)

    result = await runner.run(config)

    assert result.success is True

    run_repo = TestRunRepository(db)
    rows = await run_repo.get_by_ids([result.run_id])
    assert rows
    assert "ok" in (rows[0].get("stdout") or "")


@pytest.mark.asyncio
async def test_add_evidence_rolls_back_when_metrics_flush_fails(
    db,
    metrics_collector,
    project_repo,
    task_repo,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Single evidence add should roll back on late metrics failure."""
    project = await project_repo.create(name="Atomic Evidence Project")
    task = await task_repo.create(project.id, "Atomic Evidence Task")
    service = TaskEvidenceService(db, metrics_collector)

    async def fail_flush(*args, **kwargs):
        raise RuntimeError("metrics flush failed")

    monkeypatch.setattr(service.metrics, "flush", fail_flush)

    with pytest.raises(RuntimeError, match="metrics flush failed"):
        await service.add_evidence(
            task_id=task.id,
            evidence_type="log",
            reference="artifact://log",
            description="atomic evidence",
            created_by="tester",
        )

    assert await _count_task_evidence_rows(db, [task.id]) == 0


@pytest.mark.asyncio
async def test_add_test_run_evidence_batch_rolls_back_when_metrics_flush_fails(
    db,
    metrics_collector,
    project_repo,
    task_repo,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Batch test-run evidence attach should be all-or-nothing on late failure."""
    project = await project_repo.create(name="Atomic Evidence Batch Project")
    first = await task_repo.create(project.id, "First Evidence Task")
    second = await task_repo.create(project.id, "Second Evidence Task")
    service = TaskEvidenceService(db, metrics_collector)

    async def fail_flush(*args, **kwargs):
        raise RuntimeError("metrics flush failed")

    monkeypatch.setattr(service.metrics, "flush", fail_flush)

    with pytest.raises(RuntimeError, match="metrics flush failed"):
        await service.add_test_run_evidence_batch(
            task_ids=[first.id, second.id],
            run_id="run-batch-atomic",
            metadata={"suite": "atomic"},
            created_by="tester",
        )

    assert await _count_task_evidence_rows(db, [first.id, second.id]) == 0
