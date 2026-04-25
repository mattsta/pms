"""API tests for test run endpoints."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from pms.repositories.test_run_repository import TestRunRepository

PLAN_ID_SAMPLE = "6c4c7184-b537-489a-a5c1-ecdc4c2f6935"
TASK_ID_SAMPLE = "f14aa66c-1f7e-44af-b12b-6c55f55f4d1d"


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
async def test_list_and_get_test_runs(api_client, api_db):
    project_resp = await api_client.post(
        "/api/v1/projects",
        json={"name": "API Test Runs", "description": "Runs", "tags": []},
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    await _ensure_local_test_server(api_db)

    run_repo = TestRunRepository(api_db)
    run_id = "run-api-1"
    started = datetime.now(UTC)
    finished = started + timedelta(seconds=1)
    await run_repo.create(
        run_id=run_id,
        server_id="local",
        project_id=project_id,
        config={
            "test_command": "pytest -v",
            "runner": "local",
            "plan_id": PLAN_ID_SAMPLE,
            "task_ids": [TASK_ID_SAMPLE],
        },
        success=False,
        exit_code=1,
        stdout="out",
        stderr="err",
        duration_seconds=1.0,
        started_at=started.isoformat(),
        finished_at=finished.isoformat(),
        logs={"/tmp/api.log": "log-data"},
        artifacts={"artifact.txt": "/tmp/artifact.txt"},
    )

    list_resp = await api_client.get(
        "/api/v1/test-runs",
        params={"project_id": project_id, "include_logs": True},
    )
    assert list_resp.status_code == 200
    payload = list_resp.json()
    assert payload["total_count"] == 1
    assert payload["items"][0]["id"] == run_id
    assert payload["items"][0]["logs"] is not None

    detail_resp = await api_client.get(
        f"/api/v1/test-runs/{run_id}",
        params={
            "include_output": True,
            "include_logs": True,
            "include_artifacts": True,
        },
    )
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["stdout"] == "out"
    log_entry = detail["logs"]["/tmp/api.log"]
    assert log_entry["content"] == "log-data"
    artifact_entry = detail["artifacts"]["artifact.txt"]
    assert artifact_entry["local_path"] == "/tmp/artifact.txt"


@pytest.mark.asyncio
async def test_create_test_run(api_client, api_db):
    project_resp = await api_client.post(
        "/api/v1/projects",
        json={"name": "API Test Run Create", "description": "Runs", "tags": []},
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    await _ensure_local_test_server(api_db)

    started = datetime.now(UTC)
    finished = started + timedelta(seconds=2)
    resp = await api_client.post(
        "/api/v1/test-runs",
        json={
            "server_id": "local",
            "project_id": project_id,
            "success": True,
            "exit_code": 0,
            "duration_seconds": 2.0,
            "started_at": started.isoformat(),
            "finished_at": finished.isoformat(),
            "command": "pytest -q",
            "runner": "remote",
            "plan_id": PLAN_ID_SAMPLE,
            "task_ids": [TASK_ID_SAMPLE],
            "stdout": "ok",
            "stderr": "",
            "logs": {"/tmp/run.log": {"content": "log-data"}},
            "artifacts": {"artifact.txt": {"local_path": "/tmp/artifact.txt"}},
        },
    )
    assert resp.status_code == 201
    payload = resp.json()
    assert payload["server_id"] == "local"
    assert payload["project_id"] == project_id
    assert payload["command"] == "pytest -q"
    assert payload["runner"] == "remote"
    assert payload["task_ids"] == [TASK_ID_SAMPLE]
    assert payload["logs"]["/tmp/run.log"]["content"] == "log-data"


@pytest.mark.asyncio
async def test_prune_test_runs(api_client, api_db, tmp_path: Path):
    await _ensure_local_test_server(api_db)

    artifact_path = tmp_path / "artifact.txt"
    artifact_path.write_text("artifact-data")

    run_repo = TestRunRepository(api_db)
    run_id = "run-prune-1"
    started = datetime.now(UTC)
    finished = started + timedelta(seconds=1)
    await run_repo.create(
        run_id=run_id,
        server_id="local",
        project_id=None,
        config={"test_command": "pytest"},
        success=True,
        exit_code=0,
        stdout="output",
        stderr="",
        duration_seconds=1.0,
        started_at=started.isoformat(),
        finished_at=finished.isoformat(),
        logs={"/tmp/prune.log": "log-data"},
        artifacts={"artifact.txt": str(artifact_path)},
    )

    resp = await api_client.post(
        "/api/v1/test-runs/prune",
        params={"max_log_bytes": 1, "max_artifact_bytes": 1},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["runs_pruned"] >= 1
    assert payload["scopes"]
    assert payload["scopes"][0]["scope_type"] == "default"
    assert payload["scopes"][0]["scope_id"] == "all"

    row = await run_repo.get_by_id(run_id)
    assert row is not None
    logs = json.loads(row["logs"])
    log_entry = logs["/tmp/prune.log"]
    assert log_entry["content"] == ""
    assert row["stdout"] == ""
    assert not artifact_path.exists()


@pytest.mark.asyncio
async def test_get_test_run_retention(api_client, api_db, tmp_path: Path):
    await _ensure_local_test_server(api_db)

    artifact_path = tmp_path / "artifact.bin"
    artifact_path.write_text("data")

    run_repo = TestRunRepository(api_db)
    run_id = "run-retention-1"
    started = datetime.now(UTC)
    finished = started + timedelta(seconds=1)
    await run_repo.create(
        run_id=run_id,
        server_id="local",
        project_id=None,
        config={"test_command": "pytest"},
        success=True,
        exit_code=0,
        stdout="out",
        stderr="err",
        duration_seconds=1.0,
        started_at=started.isoformat(),
        finished_at=finished.isoformat(),
        logs={"/tmp/retain.log": "log"},
        artifacts={"artifact.bin": str(artifact_path)},
    )

    resp = await api_client.get(
        "/api/v1/test-runs/retention",
        params={"limit": 5, "sort": "largest"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total_runs"] == 1
    assert payload["sorted_by"] == "largest"
    assert payload["total_bytes"] == 13
    assert len(payload["items"]) == 1
    item = payload["items"][0]
    assert item["run_id"] == run_id
    assert item["log_total_bytes"] == 9
    assert item["artifact_bytes"] == 4


@pytest.mark.asyncio
async def test_get_test_run_retention_accepts_recent_sort(api_client, api_db) -> None:
    await _ensure_local_test_server(api_db)

    run_repo = TestRunRepository(api_db)
    started = datetime.now(UTC)
    finished = started + timedelta(seconds=1)
    await run_repo.create(
        run_id="run-retention-recent",
        server_id="local",
        project_id=None,
        config={"test_command": "pytest"},
        success=True,
        exit_code=0,
        stdout="out",
        stderr="err",
        duration_seconds=1.0,
        started_at=started.isoformat(),
        finished_at=finished.isoformat(),
        logs={},
        artifacts={},
    )

    resp = await api_client.get(
        "/api/v1/test-runs/retention",
        params={"limit": 5, "sort": "recent"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["sorted_by"] == "recent"


@pytest.mark.asyncio
async def test_get_test_run_retention_rejects_invalid_sort(api_client) -> None:
    resp = await api_client.get(
        "/api/v1/test-runs/retention",
        params={"limit": 5, "sort": "oldest"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_retention_policy_crud(api_client):
    create_resp = await api_client.post(
        "/api/v1/test-runs/retention/policies",
        params={
            "scope_type": "project",
            "scope_id": "proj-budget",
            "max_log_bytes": 100,
            "max_artifact_bytes": 200,
            "max_age_days": 7,
            "notes": "test policy",
        },
    )
    assert create_resp.status_code == 200
    created = create_resp.json()
    assert created["scope_type"] == "project"
    assert created["scope_id"] == "proj-budget"
    policy_id = created["id"]

    list_resp = await api_client.get(
        "/api/v1/test-runs/retention/policies",
        params={"scope_type": "project"},
    )
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    assert any(item["id"] == policy_id for item in items)

    update_resp = await api_client.patch(
        f"/api/v1/test-runs/retention/policies/{policy_id}",
        params={"max_log_bytes": 150},
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["max_log_bytes"] == 150

    archive_resp = await api_client.post(
        f"/api/v1/test-runs/retention/policies/{policy_id}/archive"
    )
    assert archive_resp.status_code == 200
    assert archive_resp.json()["archived"] is True

    restore_resp = await api_client.post(
        f"/api/v1/test-runs/retention/policies/{policy_id}/restore"
    )
    assert restore_resp.status_code == 200
    restored = restore_resp.json()
    assert restored["id"] == policy_id
