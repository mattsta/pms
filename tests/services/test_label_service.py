"""Transactional tests for LabelService."""

from __future__ import annotations

import pytest

from pms.repositories.label_assignment_repository import LabelAssignmentRepository
from pms.services.label_service import LabelService


@pytest.mark.asyncio
async def test_label_assignment_helpers_require_owned_transaction(db) -> None:
    repo = LabelAssignmentRepository(db)

    with pytest.raises(RuntimeError, match="requires an active transaction"):
        await repo._assign_in_transaction(
            entity_type="task",
            entity_id="task-123",
            label_id="label-123",
        )

    with pytest.raises(RuntimeError, match="requires an active transaction"):
        await repo._remove_in_transaction(
            entity_type="task",
            entity_id="task-123",
            label_id="label-123",
        )

    with pytest.raises(RuntimeError, match="requires an active transaction"):
        await repo._remove_by_category_in_transaction(
            entity_type="task",
            entity_id="task-123",
            category_id="category-123",
        )


@pytest.mark.asyncio
async def test_create_category_rolls_back_when_metrics_flush_fails(
    db,
    metrics_collector,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Category creation should roll back if metrics flush fails late."""
    service = LabelService(db, metrics_collector)

    async def fail_flush(*args, **kwargs):
        raise RuntimeError("metrics flush failed")

    monkeypatch.setattr(service.metrics, "flush", fail_flush)

    with pytest.raises(RuntimeError, match="metrics flush failed"):
        await service.create_category(name="Atomic Category", is_exclusive=True)

    assert await service.get_category_by_name("Atomic Category") is None


@pytest.mark.asyncio
async def test_create_label_rolls_back_when_metrics_flush_fails(
    db,
    metrics_collector,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Label creation should roll back if metrics flush fails late."""
    service = LabelService(db, metrics_collector)

    async def fail_flush(*args, **kwargs):
        raise RuntimeError("metrics flush failed")

    monkeypatch.setattr(service.metrics, "flush", fail_flush)

    with pytest.raises(RuntimeError, match="metrics flush failed"):
        await service.create_label(name="atomic-label")

    assert await service.get_label_by_name("atomic-label") is None


@pytest.mark.asyncio
async def test_assign_label_rolls_back_exclusive_replacement_when_new_assignment_fails(
    db,
    metrics_collector,
    sample_task,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exclusive-category replacement must leave the old assignment intact on failure."""
    service = LabelService(db, metrics_collector)

    category = await service.create_category(
        name="Exclusive Status",
        description="Only one label from this category should apply",
        is_exclusive=True,
    )
    old_label = await service.create_label(
        name="old-status",
        description="Existing label",
        category_id=category.id,
    )
    new_label = await service.create_label(
        name="new-status",
        description="Replacement label",
        category_id=category.id,
    )

    await service.assign_label(
        "task", sample_task.id, old_label.id, applied_by="tester"
    )

    async def fail_assign(
        *, entity_type: str, entity_id: str, label_id: str, applied_by=None
    ):
        raise RuntimeError("assignment failed")

    monkeypatch.setattr(service._assignments, "_assign_in_transaction", fail_assign)

    with pytest.raises(RuntimeError, match="assignment failed"):
        await service.assign_label(
            "task",
            sample_task.id,
            new_label.id,
            applied_by="tester",
        )

    assignments = await service.list_entity_label_assignments("task", sample_task.id)
    assert len(assignments) == 1
    assignment, label = assignments[0]
    assert assignment.label_id == old_label.id
    assert label.id == old_label.id


@pytest.mark.asyncio
async def test_assign_label_rolls_back_when_metrics_flush_fails(
    db,
    metrics_collector,
    sample_task,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Label assignment should roll back if metrics flush fails late."""
    service = LabelService(db, metrics_collector)
    label = await service.create_label(name="atomic-assignment")

    async def fail_flush(*args, **kwargs):
        raise RuntimeError("metrics flush failed")

    monkeypatch.setattr(service.metrics, "flush", fail_flush)

    with pytest.raises(RuntimeError, match="metrics flush failed"):
        await service.assign_label(
            "task", sample_task.id, label.id, applied_by="tester"
        )

    assignments = await service.list_entity_label_assignments("task", sample_task.id)
    assert assignments == []
