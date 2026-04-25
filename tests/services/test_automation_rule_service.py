"""Transactional tests for AutomationRuleService."""

from __future__ import annotations

import pytest

from pms.core.events import DomainEvent, EventType
from pms.models.automation_rule import AutomationActionType
from pms.services.automation_rule_service import AutomationRuleService


async def _count_rows(db, table_name: str) -> int:
    row = await db.fetch_one(f"SELECT COUNT(*) AS count FROM {table_name}")
    return int(row["count"]) if row else 0


@pytest.mark.asyncio
async def test_run_rule_rolls_back_action_when_run_record_fails(
    db,
    metrics_collector,
    sample_task,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Late automation run-record failure must roll back the triggered action."""
    service = AutomationRuleService(db, metrics_collector)
    rule = await service.create_rule(
        name="Auto comment",
        event_pattern="task.status_changed",
        action_type=AutomationActionType.ADD_COMMENT,
        action_payload={
            "entity_type": "task",
            "entity_id": sample_task.id,
            "body": "Automated comment",
            "created_by": "automation",
        },
    )
    event = DomainEvent(
        event_type=EventType.TASK_STATUS_CHANGED,
        aggregate_type="task",
        aggregate_id=sample_task.id,
        payload={},
    )

    async def fail_record(*args, **kwargs):
        raise RuntimeError("run record failed")

    monkeypatch.setattr(service._run_repo, "record", fail_record)

    with pytest.raises(RuntimeError, match="run record failed"):
        await service._run_rule_for_event(rule, event)

    assert await _count_rows(db, "comments") == 0
    assert await _count_rows(db, "automation_rule_runs") == 0
