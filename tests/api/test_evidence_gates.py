"""API tests for evidence gate rules."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pms.repositories.test_run_repository import TestRunRepository


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
async def test_evidence_gate_blocks_and_allows_transition(api_client, api_db) -> None:
    project_resp = await api_client.post(
        "/api/v1/projects",
        json={"name": "Evidence Gate Project", "description": "API test"},
    )
    project_resp.raise_for_status()
    project_id = project_resp.json()["id"]

    task_resp = await api_client.post(
        "/api/v1/tasks",
        json={
            "project_id": project_id,
            "title": "Evidence Gate Task",
            "priority": "high",
            "complexity_points": 5,
        },
    )
    task_resp.raise_for_status()
    task_id = task_resp.json()["id"]

    rule_resp = await api_client.post(
        "/api/v1/evidence/gates",
        json={
            "workflow_id": "wf_sdlc",
            "entity_type": "task",
            "from_state": "code_review",
            "to_state": "unit_testing",
            "evidence_type": "test_run",
            "min_count": 1,
            "require_success": True,
            "message": "Attach a successful test run before unit testing",
        },
    )
    rule_resp.raise_for_status()

    assign_resp = await api_client.post(
        f"/api/v1/tasks/{task_id}/workflow/assign",
        json={"workflow_name": "sdlc", "initial_state": "code_review"},
    )
    assign_resp.raise_for_status()

    blocked_resp = await api_client.post(
        f"/api/v1/tasks/{task_id}/workflow/transition",
        json={"to_state": "unit_testing", "triggered_by": "tester"},
    )
    assert blocked_resp.status_code == 400
    assert "successful test run" in blocked_resp.json()["detail"]

    await _ensure_local_test_server(api_db)
    run_repo = TestRunRepository(api_db)
    started = datetime.now(UTC)
    finished = started + timedelta(seconds=1)

    await run_repo.create(
        run_id="evidence-fail-1",
        server_id="local",
        project_id=project_id,
        config={"test_command": "pytest", "task_ids": [task_id]},
        success=False,
        exit_code=1,
        stdout="failing tests",
        stderr="traceback",
        duration_seconds=1.0,
        started_at=started.isoformat(),
        finished_at=finished.isoformat(),
        logs={},
        artifacts={},
    )

    evidence_resp = await api_client.post(
        f"/api/v1/tasks/{task_id}/evidence",
        json={
            "evidence_type": "test_run",
            "reference": "evidence-fail-1",
            "description": "Failed run",
        },
    )
    evidence_resp.raise_for_status()

    blocked_resp = await api_client.post(
        f"/api/v1/tasks/{task_id}/workflow/transition",
        json={"to_state": "unit_testing", "triggered_by": "tester"},
    )
    assert blocked_resp.status_code == 400
    assert "successful test run" in blocked_resp.json()["detail"]

    await run_repo.create(
        run_id="evidence-pass-1",
        server_id="local",
        project_id=project_id,
        config={"test_command": "pytest", "task_ids": [task_id]},
        success=True,
        exit_code=0,
        stdout="passing tests",
        stderr="",
        duration_seconds=1.0,
        started_at=started.isoformat(),
        finished_at=finished.isoformat(),
        logs={},
        artifacts={},
    )

    evidence_resp = await api_client.post(
        f"/api/v1/tasks/{task_id}/evidence",
        json={
            "evidence_type": "test_run",
            "reference": "evidence-pass-1",
            "description": "Successful run",
        },
    )
    evidence_resp.raise_for_status()

    allowed_resp = await api_client.post(
        f"/api/v1/tasks/{task_id}/workflow/transition",
        json={"to_state": "unit_testing", "triggered_by": "tester"},
    )
    allowed_resp.raise_for_status()
    assert allowed_resp.json()["to_state"] == "unit_testing"


@pytest.mark.asyncio
async def test_evidence_gate_rule_rejects_unknown_entity_type_with_suggestion(
    api_client,
) -> None:
    response = await api_client.post(
        "/api/v1/evidence/gates",
        json={
            "workflow_id": "wf_sdlc",
            "entity_type": "tas",
            "from_state": "code_review",
            "to_state": "unit_testing",
            "evidence_type": "test_run",
            "min_count": 1,
            "require_success": True,
        },
    )
    assert response.status_code == 400
    assert "Unknown entity_type 'tas'." in response.json()["detail"]
    assert "Did you mean 'task'?" in response.json()["detail"]
