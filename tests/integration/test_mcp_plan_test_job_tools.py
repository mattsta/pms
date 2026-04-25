"""Integration tests for plan test job MCP tools."""

from __future__ import annotations

import shlex
import sys

import pytest

from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.models import PlanFormat, PlanStatus
from pms.services.plan_service import PlanService
from pms.services.plan_test_job_service import PlanTestJobService
from pms.services.project_service import ProjectService
from pms.services.task_service import TaskService
from pms.tools.project_tools import (
    create_plan_test_job,
    get_plan_test_job,
    list_plan_test_jobs,
    run_plan_test_job,
    set_services,
)


@pytest.mark.asyncio
async def test_plan_test_job_tools(db, tmp_path):
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)

    project_service = ProjectService(db, event_store, revision_store, metrics)
    task_service = TaskService(db, event_store, revision_store, metrics)
    plan_service = PlanService(db, event_store, revision_store, metrics)
    plan_test_job_service = PlanTestJobService(db, event_store, revision_store, metrics)

    set_services(
        project_service=project_service,
        task_service=task_service,
        plan_service=plan_service,
        plan_test_job_service=plan_test_job_service,
    )

    plan = await plan_service.create_plan(
        name="Tool Plan",
        description=None,
        status=PlanStatus.DRAFT,
        format=PlanFormat.JSON,
        content={"stages": ["plan", "test"]},
    )

    test_command = f"{shlex.quote(sys.executable)} -c \"print('ok')\""
    create_result = await create_plan_test_job.handler(
        {
            "plan_id": plan.id,
            "name": "Tool Job",
            "mode": "local",
            "project_path": str(tmp_path),
            "test_command": test_command,
        }
    )
    create_text = create_result["content"][0]["text"]
    assert "Created plan test job" in create_text
    job_id = create_text.split("ID:")[-1].strip()

    list_result = await list_plan_test_jobs.handler({"plan_id": plan.id})
    list_text = list_result["content"][0]["text"]
    assert job_id in list_text

    get_result = await get_plan_test_job.handler({"job_id": job_id})
    get_text = get_result["content"][0]["text"]
    assert "Plan Test Job" in get_text
    assert job_id in get_text

    run_result = await run_plan_test_job.handler({"job_id": job_id})
    run_text = run_result["content"][0]["text"]
    assert "Status:" in run_text
    assert "Run ID:" in run_text


@pytest.mark.asyncio
async def test_plan_test_job_tools_reject_deprecated_stream_output(db, tmp_path):
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)

    project_service = ProjectService(db, event_store, revision_store, metrics)
    task_service = TaskService(db, event_store, revision_store, metrics)
    plan_service = PlanService(db, event_store, revision_store, metrics)
    plan_test_job_service = PlanTestJobService(db, event_store, revision_store, metrics)

    set_services(
        project_service=project_service,
        task_service=task_service,
        plan_service=plan_service,
        plan_test_job_service=plan_test_job_service,
    )

    plan = await plan_service.create_plan(
        name="Tool Deprecated Stream Plan",
        description=None,
        status=PlanStatus.DRAFT,
        format=PlanFormat.JSON,
        content={"stages": ["plan", "test"]},
    )

    result = await create_plan_test_job.handler(
        {
            "plan_id": plan.id,
            "name": "Deprecated Stream Tool Job",
            "mode": "aws",
            "project_path": str(tmp_path),
            "server_name": "aws-test",
            "stream_output": True,
        }
    )

    assert result["is_error"] is True
    assert "stream_output is not supported" in result["content"][0]["text"]
