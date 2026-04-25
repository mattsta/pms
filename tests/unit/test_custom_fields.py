"""Unit tests for custom field service."""

from __future__ import annotations

import pytest

from pms.models.custom_field import CustomFieldType
from pms.services.custom_field_service import CustomFieldService


@pytest.mark.asyncio
async def test_custom_field_enum_validation(
    db,
    metrics_collector,
    project_repo,
    task_repo,
) -> None:
    project = await project_repo.create("Custom Field Project")
    task = await task_repo.create(project_id=project.id, title="Custom Field Task")

    service = CustomFieldService(db, metrics_collector)
    definition = await service.create_definition(
        name="stage",
        entity_type="task",
        field_type=CustomFieldType.ENUM,
        options=["alpha", "beta"],
        is_required=True,
    )

    item = await service.set_value(
        definition.id,
        entity_type="task",
        entity_id=task.id,
        value="alpha",
        created_by="tester",
    )
    assert item.value.value == "alpha"

    with pytest.raises(ValueError):
        await service.set_value(
            definition.id,
            entity_type="task",
            entity_id=task.id,
            value="gamma",
            created_by="tester",
        )


@pytest.mark.asyncio
async def test_create_definition_rolls_back_when_metrics_flush_fails(
    db,
    metrics_collector,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Definition creation should roll back if metrics flush fails late."""
    service = CustomFieldService(db, metrics_collector)

    async def fail_flush(*args, **kwargs):
        raise RuntimeError("metrics flush failed")

    monkeypatch.setattr(service.metrics, "flush", fail_flush)

    with pytest.raises(RuntimeError, match="metrics flush failed"):
        await service.create_definition(
            name="atomic-field",
            entity_type="task",
            field_type=CustomFieldType.TEXT,
        )

    assert (
        await service.get_definition_by_name(
            "atomic-field",
            "task",
            include_archived=True,
        )
        is None
    )


@pytest.mark.asyncio
async def test_set_value_rolls_back_when_metrics_flush_fails(
    db,
    metrics_collector,
    project_repo,
    task_repo,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Value creation should roll back if metrics flush fails late."""
    project = await project_repo.create("Atomic Custom Field Project")
    task = await task_repo.create(
        project_id=project.id, title="Atomic Custom Field Task"
    )

    service = CustomFieldService(db, metrics_collector)
    definition = await service.create_definition(
        name="atomic-stage",
        entity_type="task",
        field_type=CustomFieldType.TEXT,
    )

    async def fail_flush(*args, **kwargs):
        raise RuntimeError("metrics flush failed")

    monkeypatch.setattr(service.metrics, "flush", fail_flush)

    with pytest.raises(RuntimeError, match="metrics flush failed"):
        await service.set_value(
            definition.id,
            entity_type="task",
            entity_id=task.id,
            value="in-progress",
            created_by="tester",
        )

    page = await service.list_values_for_entity(entity_type="task", entity_id=task.id)
    assert page.items == []
