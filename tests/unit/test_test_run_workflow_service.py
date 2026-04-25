"""Unit tests for TestRunWorkflowService."""

from __future__ import annotations

import pytest

from pms.core.events import EventType
from pms.models.workflow_state import get_workflow_registry
from pms.repositories.task_repository import TaskRepository
from pms.services.project_service import ProjectService
from pms.services.task_service import TaskService
from pms.services.test_run_workflow_service import (
    TestRunWorkflowService,
    TestRunWorkflowTransition,
)


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


async def _count_task_workflow_transitions(db, task_ids: list[str]) -> int:
    placeholders = ", ".join("?" * len(task_ids))
    row = await db.fetch_one(
        f"""
        SELECT COUNT(*) AS count
        FROM task_state_transitions
        WHERE task_id IN ({placeholders})
        """,
        tuple(task_ids),
    )
    return int(row["count"]) if row else 0


@pytest.mark.asyncio
async def test_test_run_workflow_service_transitions_task(
    db,
    event_store,
    revision_store,
    metrics_collector,
) -> None:
    project_service = ProjectService(db, event_store, revision_store, metrics_collector)
    task_service = TaskService(db, event_store, revision_store, metrics_collector)
    task_repo = TaskRepository(db, event_store, revision_store, metrics_collector)

    project = await project_service.create_project(name="Workflow Service Project")
    task = await task_service.create_task(project.id, "Workflow Service Task")

    await _assign_task_workflow(task_repo, task, "sdlc", "unit_testing")

    service = TestRunWorkflowService(db, metrics_collector)
    transition = TestRunWorkflowTransition(
        on_success_state="integration_testing",
        triggered_by="tester",
        reason="tests passed",
    )
    result = await service.apply(
        task_ids=[task.id],
        success=True,
        transition=transition,
        run_id="run-test-1",
    )

    assert result.tasks_transitioned == 1
    updated = await task_repo.get_by_id(task.id)
    assert updated is not None
    assert updated.current_state == "integration_testing"


@pytest.mark.asyncio
async def test_test_run_workflow_service_rolls_back_when_metrics_flush_fails(
    db,
    event_store,
    revision_store,
    metrics_collector,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Late metrics failure must roll back the workflow transition write."""
    project_service = ProjectService(db, event_store, revision_store, metrics_collector)
    task_service = TaskService(db, event_store, revision_store, metrics_collector)
    task_repo = TaskRepository(db, event_store, revision_store, metrics_collector)

    project = await project_service.create_project(name="Workflow Metrics Rollback")
    task = await task_service.create_task(project.id, "Workflow Metrics Task")
    await _assign_task_workflow(task_repo, task, "sdlc", "unit_testing")

    service = TestRunWorkflowService(db, metrics_collector)

    async def fail_flush(*args, **kwargs):
        raise RuntimeError("metrics flush failed")

    monkeypatch.setattr(service.metrics, "flush", fail_flush)

    with pytest.raises(RuntimeError, match="metrics flush failed"):
        await service.apply(
            task_ids=[task.id],
            success=True,
            transition=TestRunWorkflowTransition(
                on_success_state="integration_testing",
                triggered_by="tester",
            ),
            run_id="run-metrics-fail",
        )

    updated = await task_repo.get_by_id(task.id)
    assert updated is not None
    assert updated.current_state == "unit_testing"
    assert await _count_task_workflow_transitions(db, [task.id]) == 0


@pytest.mark.asyncio
async def test_test_run_workflow_service_rolls_back_earlier_transitions_when_later_save_fails(
    db,
    event_store,
    revision_store,
    metrics_collector,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A later task save failure must roll back earlier transitioned tasks too."""
    project_service = ProjectService(db, event_store, revision_store, metrics_collector)
    task_service = TaskService(db, event_store, revision_store, metrics_collector)
    task_repo = TaskRepository(db, event_store, revision_store, metrics_collector)

    project = await project_service.create_project(name="Workflow Partial Rollback")
    first = await task_service.create_task(project.id, "Workflow First Task")
    second = await task_service.create_task(project.id, "Workflow Second Task")
    await _assign_task_workflow(task_repo, first, "sdlc", "unit_testing")
    await _assign_task_workflow(task_repo, second, "sdlc", "unit_testing")

    service = TestRunWorkflowService(db, metrics_collector)
    original_save = service._task_repo.save
    save_calls = 0

    async def fail_second_save(*args, **kwargs):
        nonlocal save_calls
        save_calls += 1
        if save_calls == 2:
            raise RuntimeError("second save failed")
        return await original_save(*args, **kwargs)

    monkeypatch.setattr(service._task_repo, "save", fail_second_save)

    with pytest.raises(RuntimeError, match="second save failed"):
        await service.apply(
            task_ids=[first.id, second.id],
            success=True,
            transition=TestRunWorkflowTransition(
                on_success_state="integration_testing",
                triggered_by="tester",
            ),
            run_id="run-save-fail",
        )

    refreshed_first = await task_repo.get_by_id(first.id)
    refreshed_second = await task_repo.get_by_id(second.id)
    assert refreshed_first is not None
    assert refreshed_second is not None
    assert refreshed_first.current_state == "unit_testing"
    assert refreshed_second.current_state == "unit_testing"
    assert await _count_task_workflow_transitions(db, [first.id, second.id]) == 0
