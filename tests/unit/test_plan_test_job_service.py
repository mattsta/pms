"""Unit tests for plan test jobs."""

from __future__ import annotations

import shlex
import sys
from types import SimpleNamespace

import pytest

from pms.core.events import EventStore, EventType
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.models import PlanFormat, PlanStatus
from pms.models.workflow_state import get_workflow_registry
from pms.repositories.task_repository import TaskRepository
from pms.services.plan_service import PlanService
from pms.services.plan_test_job_service import (
    PLAN_TEST_JOB_STREAM_OUTPUT_MESSAGE,
    PlanTestJobService,
)
from pms.services.project_service import ProjectService
from pms.services.task_service import TaskService
from pms.services.test_run_service import TestRunService


async def _assign_task_workflow(
    task_repo, task, workflow_name: str, state: str
) -> None:
    workflow = get_workflow_registry()[workflow_name]
    task.assign_workflow(workflow.id, state)
    await task_repo.save(
        task,
        EventType.TASK_UPDATED,
        {"workflow_assigned": workflow.name},
    )


@pytest.mark.asyncio
async def test_plan_test_job_run_local(db, tmp_path):
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)

    plan_service = PlanService(db, event_store, revision_store, metrics)
    plan = await plan_service.create_plan(
        name="Test Plan",
        description=None,
        status=PlanStatus.DRAFT,
        format=PlanFormat.JSON,
        content={"stages": ["plan", "test"]},
        project_id=None,
    )

    test_command = f"{shlex.quote(sys.executable)} -c \"print('ok')\""

    job_service = PlanTestJobService(db, event_store, revision_store, metrics)
    job = await job_service.create_job(
        plan_id=plan.id,
        name="Local Job",
        mode="local",
        project_path=str(tmp_path),
        test_command=test_command,
    )

    run = await job_service.run_job(job.id)
    assert run is not None
    assert run.result.success is True

    test_run_service = TestRunService(db, metrics)
    record = await test_run_service.get_test_run(
        run.result.run_id,
        include_output=True,
        include_logs=False,
        include_artifacts=False,
    )
    assert record is not None
    assert record.plan_id == plan.id


@pytest.mark.asyncio
async def test_plan_test_job_run_bubbles_workflow_transition_into_plan_and_project(
    db,
    tmp_path,
):
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)

    project_service = ProjectService(db, event_store, revision_store, metrics)
    task_service = TaskService(db, event_store, revision_store, metrics)
    task_repo = TaskRepository(db, event_store, revision_store, metrics)
    plan_service = PlanService(db, event_store, revision_store, metrics)
    job_service = PlanTestJobService(db, event_store, revision_store, metrics)

    project = await project_service.create_project(name="Workflow Job Project")
    task = await task_service.create_task(project.id, "Workflow Job Task")
    await _assign_task_workflow(task_repo, task, "sdlc", "unit_testing")
    plan = await plan_service.create_plan(
        name="Workflow Job Plan",
        description=None,
        status=PlanStatus.ACTIVE,
        format=PlanFormat.JSON,
        content={"stages": ["test"]},
        project_id=project.id,
        task_ids=[task.id],
    )

    before_plan_transition = (await plan_service.get_last_transition_map([plan.id]))[
        plan.id
    ]
    before_project_transition = (
        await project_service.get_last_transition_map([project.id])
    )[project.id]

    test_command = f"{shlex.quote(sys.executable)} -c \"print('ok')\""
    job = await job_service.create_job(
        plan_id=plan.id,
        name="Workflow Transition Job",
        mode="local",
        project_path=str(tmp_path),
        test_command=test_command,
        task_ids=(task.id,),
        transition_on_success="integration_testing",
        transition_by="tester",
        transition_reason="job passed",
    )

    run = await job_service.run_job(job.id)
    task_transition = (await task_repo.get_last_transition_map([task.id]))[task.id]
    after_plan_transition = (await plan_service.get_last_transition_map([plan.id]))[
        plan.id
    ]
    after_project_transition = (
        await project_service.get_last_transition_map([project.id])
    )[project.id]
    refreshed_task = await task_repo.get_by_id(task.id)

    assert run is not None
    assert run.result.success is True
    assert refreshed_task is not None
    assert refreshed_task.current_state == "integration_testing"
    assert task_transition is not None
    assert before_plan_transition is not None
    assert before_project_transition is not None
    assert after_plan_transition == task_transition
    assert after_project_transition == task_transition
    assert after_plan_transition > before_plan_transition
    assert after_project_transition > before_project_transition


@pytest.mark.asyncio
async def test_plan_test_job_reads_and_run_ignore_observational_metrics_flush_failures(
    db,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)

    plan_service = PlanService(db, event_store, revision_store, metrics)
    plan = await plan_service.create_plan(
        name="Observational Job Plan",
        description=None,
        status=PlanStatus.DRAFT,
        format=PlanFormat.JSON,
        content={"stages": ["plan", "test"]},
        project_id=None,
    )

    job_service = PlanTestJobService(db, event_store, revision_store, metrics)
    job = await job_service.create_job(
        plan_id=plan.id,
        name="Observational Job",
        mode="local",
        project_path=str(tmp_path),
    )

    class _FakeExecution:
        async def run(self, config):
            return SimpleNamespace(success=True)

    async def build_fake_execution(mode: str):
        return _FakeExecution()

    async def fail_flush(*args, **kwargs):
        raise RuntimeError("metrics flush failed")

    monkeypatch.setattr(job_service, "_build_execution", build_fake_execution)
    monkeypatch.setattr(job_service.metrics, "flush", fail_flush)

    fetched = await job_service.get_job(job.id)
    listed = await job_service.list_jobs(plan_id=plan.id)
    run = await job_service.run_job(job.id)

    assert fetched is not None
    assert fetched.id == job.id
    assert listed.total_count == 1
    assert run is not None
    assert run.job.id == job.id
    assert run.result.success is True


@pytest.mark.asyncio
async def test_plan_test_job_create_rolls_back_when_metrics_flush_fails(
    db,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)

    plan_service = PlanService(db, event_store, revision_store, metrics)
    plan = await plan_service.create_plan(
        name="Atomic Job Plan",
        description=None,
        status=PlanStatus.DRAFT,
        format=PlanFormat.JSON,
        content={"stages": ["plan", "test"]},
        project_id=None,
    )

    job_service = PlanTestJobService(db, event_store, revision_store, metrics)

    async def fail_flush(*args, **kwargs):
        raise RuntimeError("metrics flush failed")

    monkeypatch.setattr(job_service.metrics, "flush", fail_flush)

    with pytest.raises(RuntimeError, match="metrics flush failed"):
        await job_service.create_job(
            plan_id=plan.id,
            name="Atomic Job",
            mode="local",
            project_path=str(tmp_path),
        )

    jobs = await job_service._repo.list(plan_id=plan.id, include_archived=True)
    assert jobs.total_count == 0


@pytest.mark.asyncio
async def test_plan_test_job_update_rolls_back_when_metrics_flush_fails(
    db,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)

    plan_service = PlanService(db, event_store, revision_store, metrics)
    plan = await plan_service.create_plan(
        name="Atomic Update Plan",
        description=None,
        status=PlanStatus.DRAFT,
        format=PlanFormat.JSON,
        content={"stages": ["plan", "test"]},
        project_id=None,
    )

    job_service = PlanTestJobService(db, event_store, revision_store, metrics)
    job = await job_service.create_job(
        plan_id=plan.id,
        name="Job Before Update",
        mode="local",
        project_path=str(tmp_path),
    )

    async def fail_flush(*args, **kwargs):
        raise RuntimeError("metrics flush failed")

    monkeypatch.setattr(job_service.metrics, "flush", fail_flush)

    with pytest.raises(RuntimeError, match="metrics flush failed"):
        await job_service.update_job(job.id, name="Job After Update")

    refreshed = await job_service._repo.get_by_id(job.id)
    assert refreshed is not None
    assert refreshed.name == "Job Before Update"


@pytest.mark.asyncio
async def test_plan_test_job_delete_rolls_back_when_metrics_flush_fails(
    db,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)

    plan_service = PlanService(db, event_store, revision_store, metrics)
    plan = await plan_service.create_plan(
        name="Atomic Delete Plan",
        description=None,
        status=PlanStatus.DRAFT,
        format=PlanFormat.JSON,
        content={"stages": ["plan", "test"]},
        project_id=None,
    )

    job_service = PlanTestJobService(db, event_store, revision_store, metrics)
    job = await job_service.create_job(
        plan_id=plan.id,
        name="Job Before Delete",
        mode="local",
        project_path=str(tmp_path),
    )

    async def fail_flush(*args, **kwargs):
        raise RuntimeError("metrics flush failed")

    monkeypatch.setattr(job_service.metrics, "flush", fail_flush)

    with pytest.raises(RuntimeError, match="metrics flush failed"):
        await job_service.delete_job(job.id)

    refreshed = await job_service._repo.get_by_id(job.id)
    assert refreshed is not None
    assert refreshed.archived_at is None


@pytest.mark.asyncio
async def test_plan_test_job_restore_rolls_back_when_metrics_flush_fails(
    db,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)

    plan_service = PlanService(db, event_store, revision_store, metrics)
    plan = await plan_service.create_plan(
        name="Atomic Restore Plan",
        description=None,
        status=PlanStatus.DRAFT,
        format=PlanFormat.JSON,
        content={"stages": ["plan", "test"]},
        project_id=None,
    )

    job_service = PlanTestJobService(db, event_store, revision_store, metrics)
    job = await job_service.create_job(
        plan_id=plan.id,
        name="Job Before Restore",
        mode="local",
        project_path=str(tmp_path),
    )
    await job_service._repo.delete(job.id)

    async def fail_flush(*args, **kwargs):
        raise RuntimeError("metrics flush failed")

    monkeypatch.setattr(job_service.metrics, "flush", fail_flush)

    with pytest.raises(RuntimeError, match="metrics flush failed"):
        await job_service.restore_job(job.id)

    row = await db.fetch_one(
        "SELECT archived_at FROM plan_test_jobs WHERE id = ?",
        (job.id,),
    )
    assert row is not None
    assert row["archived_at"] is not None


@pytest.mark.asyncio
async def test_plan_test_job_create_rejects_deprecated_stream_output(
    db,
    tmp_path,
):
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)

    plan_service = PlanService(db, event_store, revision_store, metrics)
    plan = await plan_service.create_plan(
        name="Deprecated Stream Plan",
        description=None,
        status=PlanStatus.DRAFT,
        format=PlanFormat.JSON,
        content={"stages": ["plan", "test"]},
        project_id=None,
    )

    job_service = PlanTestJobService(db, event_store, revision_store, metrics)

    with pytest.raises(ValueError, match="stream_output is not supported"):
        await job_service.create_job(
            plan_id=plan.id,
            name="Deprecated Stream Job",
            mode="aws",
            project_path=str(tmp_path),
            stream_output=True,
        )


@pytest.mark.asyncio
async def test_plan_test_job_update_rejects_deprecated_stream_output(
    db,
    tmp_path,
):
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)

    plan_service = PlanService(db, event_store, revision_store, metrics)
    plan = await plan_service.create_plan(
        name="Deprecated Stream Update Plan",
        description=None,
        status=PlanStatus.DRAFT,
        format=PlanFormat.JSON,
        content={"stages": ["plan", "test"]},
        project_id=None,
    )

    job_service = PlanTestJobService(db, event_store, revision_store, metrics)
    job = await job_service.create_job(
        plan_id=plan.id,
        name="Job Before Deprecated Update",
        mode="local",
        project_path=str(tmp_path),
    )

    with pytest.raises(ValueError, match="stream_output is not supported"):
        await job_service.update_job(job.id, stream_output=True)

    refreshed = await job_service.get_job(job.id)
    assert refreshed is not None
    assert refreshed.stream_output is False


@pytest.mark.asyncio
async def test_plan_test_job_run_ignores_legacy_stream_output_flag(
    db,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)

    plan_service = PlanService(db, event_store, revision_store, metrics)
    plan = await plan_service.create_plan(
        name="Legacy Stream Plan",
        description=None,
        status=PlanStatus.DRAFT,
        format=PlanFormat.JSON,
        content={"stages": ["plan", "test"]},
        project_id=None,
    )

    job_service = PlanTestJobService(db, event_store, revision_store, metrics)
    job = await job_service.create_job(
        plan_id=plan.id,
        name="Legacy Stream Job",
        mode="local",
        project_path=str(tmp_path),
    )
    await job_service._repo.update(job.id, stream_output=True)

    seen = {}

    class _FakeExecution:
        async def run(self, config):
            seen["stream_output"] = config.stream_output
            return SimpleNamespace(run_id="run", success=True)

    async def build_fake_execution(mode: str):
        return _FakeExecution()

    monkeypatch.setattr(job_service, "_build_execution", build_fake_execution)

    run = await job_service.run_job(job.id)

    assert run is not None
    assert seen["stream_output"] is False
    assert PLAN_TEST_JOB_STREAM_OUTPUT_MESSAGE
