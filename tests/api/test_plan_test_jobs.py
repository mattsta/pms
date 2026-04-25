"""API tests for plan test job endpoints."""

from __future__ import annotations

import shlex
import sys

import pytest


@pytest.mark.asyncio
async def test_plan_test_job_api_flow(api_client, tmp_path):
    plan_resp = await api_client.post(
        "/api/v1/plans",
        json={
            "name": "API Plan",
            "description": "Plan for test jobs",
            "status": "draft",
            "format": "json",
            "content": {"stages": ["plan", "test"]},
        },
    )
    assert plan_resp.status_code == 201
    plan_id = plan_resp.json()["id"]

    test_command = f"{shlex.quote(sys.executable)} -c \"print('ok')\""
    job_resp = await api_client.post(
        f"/api/v1/plans/{plan_id}/test-jobs",
        json={
            "name": "API Job",
            "mode": "local",
            "project_path": str(tmp_path),
            "test_command": test_command,
            "capture_logs": [],
            "save_artifacts": [],
            "task_ids": [],
        },
    )
    assert job_resp.status_code == 201
    job_id = job_resp.json()["id"]

    list_resp = await api_client.get(f"/api/v1/plans/{plan_id}/test-jobs")
    assert list_resp.status_code == 200
    list_payload = list_resp.json()
    assert any(item["id"] == job_id for item in list_payload["items"])
    assert "links" in list_payload
    assert "next_steps" in list_payload
    assert "params" in list_payload
    assert list_payload["links"]["guide"] == "/api/v1/"
    assert list_payload["links"]["self"].startswith(
        f"/api/v1/plans/{plan_id}/test-jobs?"
    )

    run_resp = await api_client.post(f"/api/v1/plans/{plan_id}/test-jobs/{job_id}/run")
    assert run_resp.status_code == 200
    run_data = run_resp.json()
    assert run_data["job"]["id"] == job_id
    assert run_data["test_run"]["plan_id"] == plan_id
    assert run_data["test_run"]["success"] is True


@pytest.mark.asyncio
async def test_plan_test_job_api_rejects_deprecated_stream_output(api_client, tmp_path):
    plan_resp = await api_client.post(
        "/api/v1/plans",
        json={
            "name": "Deprecated Stream API Plan",
            "description": "Plan for test jobs",
            "status": "draft",
            "format": "json",
            "content": {"stages": ["plan", "test"]},
        },
    )
    assert plan_resp.status_code == 201
    plan_id = plan_resp.json()["id"]

    create_resp = await api_client.post(
        f"/api/v1/plans/{plan_id}/test-jobs",
        json={
            "name": "Deprecated Stream API Job",
            "mode": "aws",
            "project_path": str(tmp_path),
            "server_name": "aws-test",
            "stream_output": True,
        },
    )
    assert create_resp.status_code == 400
    assert "stream_output is not supported" in create_resp.json()["detail"]
