"""API tests for task evidence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pms.core.metrics import MetricsCollector
from pms.repositories.test_run_repository import TestRunRepository
from pms.services.task_evidence_service import TaskEvidenceService


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
async def test_task_evidence_endpoints(api_client, api_db) -> None:
    project_resp = await api_client.post(
        "/api/v1/projects",
        json={"name": "Evidence Project", "description": "API test"},
    )
    project_resp.raise_for_status()
    project_id = project_resp.json()["id"]

    task_resp = await api_client.post(
        "/api/v1/tasks",
        json={
            "project_id": project_id,
            "title": "Evidence Task",
            "priority": "medium",
            "complexity_points": 5,
        },
    )
    task_resp.raise_for_status()
    task_id = task_resp.json()["id"]

    evidence_resp = await api_client.post(
        f"/api/v1/tasks/{task_id}/evidence",
        json={
            "evidence_type": "scm_commit",
            "reference": "abc123",
            "description": "Manual commit reference",
            "metadata": {"scm": "git"},
            "created_by": "tester",
        },
    )
    evidence_resp.raise_for_status()
    data = evidence_resp.json()
    assert data["evidence_type"] == "scm_commit"
    assert data["reference"] == "abc123"

    list_resp = await api_client.get(f"/api/v1/tasks/{task_id}/evidence")
    list_resp.raise_for_status()
    list_data = list_resp.json()
    assert list_data["total_count"] == 1
    assert list_data["items"][0]["reference"] == "abc123"


@pytest.mark.asyncio
async def test_task_evidence_include_test_runs(api_client, api_db) -> None:
    project_resp = await api_client.post(
        "/api/v1/projects",
        json={"name": "Test Runs Project"},
    )
    project_resp.raise_for_status()
    project_id = project_resp.json()["id"]

    task_resp = await api_client.post(
        "/api/v1/tasks",
        json={
            "project_id": project_id,
            "title": "Run Evidence Task",
            "priority": "high",
            "complexity_points": 3,
        },
    )
    task_resp.raise_for_status()
    task_id = task_resp.json()["id"]

    await _ensure_local_test_server(api_db)

    run_repo = TestRunRepository(api_db)
    run_id = "api-run-1"
    started = datetime.now(UTC)
    finished = started + timedelta(seconds=2)
    await run_repo.create(
        run_id=run_id,
        server_id="local",
        project_id=project_id,
        config={"test_command": "pytest", "task_ids": [task_id]},
        success=False,
        exit_code=1,
        stdout="failing tests",
        stderr="traceback",
        duration_seconds=2.0,
        started_at=started.isoformat(),
        finished_at=finished.isoformat(),
        logs={},
        artifacts={},
    )

    evidence_service = TaskEvidenceService(api_db, MetricsCollector(api_db))
    await evidence_service.add_test_run_evidence(task_id, run_id)

    list_resp = await api_client.get(
        f"/api/v1/tasks/{task_id}/evidence",
        params={"include_test_runs": True, "include_output": True},
    )
    list_resp.raise_for_status()
    payload = list_resp.json()
    assert payload["total_count"] == 1
    evidence_item = payload["items"][0]
    assert evidence_item["test_run"]["id"] == run_id
    assert evidence_item["test_run"]["stdout"] == "failing tests"


@pytest.mark.asyncio
async def test_task_proof_bundle(api_client, api_db, tmp_path) -> None:
    project_resp = await api_client.post(
        "/api/v1/projects",
        json={"name": "Proof Bundle Project"},
    )
    project_resp.raise_for_status()
    project_id = project_resp.json()["id"]

    task_resp = await api_client.post(
        "/api/v1/tasks",
        json={
            "project_id": project_id,
            "title": "Proof Bundle Task",
            "priority": "medium",
            "complexity_points": 8,
        },
    )
    task_resp.raise_for_status()
    task_id = task_resp.json()["id"]

    await _ensure_local_test_server(api_db)
    artifact_path = tmp_path / "bundle.txt"
    artifact_path.write_text("bundle")

    run_repo = TestRunRepository(api_db)
    run_id = "bundle-run-1"
    started = datetime.now(UTC)
    finished = started + timedelta(seconds=2)
    await run_repo.create(
        run_id=run_id,
        server_id="local",
        project_id=project_id,
        config={"test_command": "pytest", "task_ids": [task_id]},
        success=True,
        exit_code=0,
        stdout="passing tests",
        stderr="",
        duration_seconds=2.0,
        started_at=started.isoformat(),
        finished_at=finished.isoformat(),
        logs={"/tmp/bundle.log": "log-data"},
        artifacts={"bundle.txt": str(artifact_path)},
    )

    evidence_service = TaskEvidenceService(api_db, MetricsCollector(api_db))
    await evidence_service.add_test_run_evidence(
        task_id,
        run_id,
        metadata={"log_bytes_total": 8, "artifact_bytes_total": 6},
    )

    bundle_resp = await api_client.get(
        f"/api/v1/tasks/{task_id}/proof-bundle",
        params={
            "include_output": True,
            "include_logs": True,
            "include_artifacts": True,
        },
    )
    bundle_resp.raise_for_status()
    payload = bundle_resp.json()
    assert payload["task"]["id"] == task_id
    assert payload["summary"]["evidence_total"] == 1
    assert payload["summary"]["test_runs"] == 1
    assert payload["summary"]["successful_test_runs"] == 1
    assert payload["summary"]["log_bytes_total"] == 8
    assert payload["summary"]["artifact_bytes_total"] == 6
    assert payload["test_runs"][0]["id"] == run_id
    assert payload["test_runs"][0]["logs"] is not None
    assert payload["test_runs"][0]["artifacts"] is not None


@pytest.mark.asyncio
async def test_evidence_bundle_search(api_client) -> None:
    project_resp = await api_client.post(
        "/api/v1/projects",
        json={"name": "Bundle Search Project"},
    )
    project_resp.raise_for_status()
    project_id = project_resp.json()["id"]

    task_one = await api_client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Bundle Task One"},
    )
    task_two = await api_client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Bundle Task Two"},
    )
    task_one_id = task_one.json()["id"]
    task_two_id = task_two.json()["id"]

    start_resp = await api_client.post(f"/api/v1/tasks/{task_one_id}/start")
    start_resp.raise_for_status()

    plan_resp = await api_client.post(
        "/api/v1/plans",
        json={
            "name": "Bundle Search Plan",
            "status": "active",
            "format": "json",
            "content": {"steps": ["plan", "deliver"]},
            "project_id": project_id,
            "task_ids": [task_one_id, task_two_id],
        },
    )
    plan_resp.raise_for_status()
    plan_id = plan_resp.json()["id"]

    evidence_one = await api_client.post(
        f"/api/v1/tasks/{task_one_id}/evidence",
        json={
            "evidence_type": "scm_commit",
            "reference": "bundle-commit-1",
        },
    )
    evidence_one.raise_for_status()

    evidence_two = await api_client.post(
        f"/api/v1/tasks/{task_two_id}/evidence",
        json={
            "evidence_type": "note",
            "reference": "bundle-note-1",
        },
    )
    evidence_two.raise_for_status()

    since = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    search_resp = await api_client.get(
        "/api/v1/evidence/bundles",
        params=[
            ("plan_id", plan_id),
            ("status", "in_progress"),
            ("evidence_type", "scm_commit"),
            ("created_from", since),
            ("include_evidence", "true"),
        ],
    )
    search_resp.raise_for_status()
    payload = search_resp.json()
    assert payload["total_count"] == 1
    assert payload["items"][0]["task"]["id"] == task_one_id
    assert payload["items"][0]["summary"]["evidence_total"] == 1
    assert payload["items"][0]["evidence"][0]["evidence_type"] == "scm_commit"
