#!/usr/bin/env python3
"""Shared helpers for key result lifecycle contract audits."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pms.models import KeyResult
from pms.services.goal_service import key_result_lifecycle_terminal_reason


@dataclass(frozen=True)
class KeyResultLifecycleExpectation:
    """Expected lifecycle contract for a key result payload."""

    key_result_id: str
    objective_id: str
    goal_id: str
    project_id: str | None
    key_result_name: str
    stored_status: str
    progress_percent: int
    effective_progress_percent: int
    effective_status: str
    effective_basis: str
    effective_reason: str | None
    last_activity_at: datetime | None
    last_transition_at: datetime | None
    terminal_reason: str | None


def parse_timestamp(value: object) -> datetime | None:
    """Parse serialized timestamps used by CLI/API/MCP surfaces."""
    if value is None:
        return None
    text = str(value)
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    return datetime.fromisoformat(text)


def expectation_from_key_result(
    key_result: KeyResult,
    *,
    goal_id: str,
    project_id: str | None,
    last_activity_at: datetime | None,
    last_transition_at: datetime | None,
) -> KeyResultLifecycleExpectation:
    """Build a shared key result lifecycle expectation from one stored key result."""
    return KeyResultLifecycleExpectation(
        key_result_id=key_result.id,
        objective_id=key_result.objective_id,
        goal_id=goal_id,
        project_id=project_id,
        key_result_name=key_result.name,
        stored_status=key_result.status.value,
        progress_percent=key_result.progress_percent,
        effective_progress_percent=key_result.progress_percent,
        effective_status=key_result.status.value,
        effective_basis="stored_key_result",
        effective_reason=None,
        last_activity_at=last_activity_at,
        last_transition_at=last_transition_at,
        terminal_reason=key_result_lifecycle_terminal_reason(key_result),
    )


def key_result_list_payload_mismatch_reasons(
    payload: dict[str, object],
    expectation: KeyResultLifecycleExpectation,
) -> tuple[str, ...]:
    """Compare one serialized key result list item against shared lifecycle fields."""
    issues: list[str] = []

    def record(condition: bool, reason: str) -> None:
        if not condition:
            issues.append(reason)

    effective_rollup = payload.get("effective_rollup")
    record(payload.get("id") == expectation.key_result_id, "key result id mismatch")
    record(
        payload.get("objective_id") == expectation.objective_id,
        "objective id mismatch",
    )
    record(payload.get("goal_id") == expectation.goal_id, "goal id mismatch")
    record(payload.get("project_id") == expectation.project_id, "project id mismatch")
    record(payload.get("name") == expectation.key_result_name, "name mismatch")
    record(payload.get("status") == expectation.stored_status, "stored status mismatch")
    record(
        payload.get("progress_percent") == expectation.progress_percent,
        "stored progress mismatch",
    )
    record(isinstance(effective_rollup, dict), "effective_rollup missing")
    if isinstance(effective_rollup, dict):
        record(
            effective_rollup.get("progress_percent")
            == expectation.effective_progress_percent,
            "effective progress mismatch",
        )
        record(
            effective_rollup.get("status") == expectation.effective_status,
            "effective status mismatch",
        )
        record(
            effective_rollup.get("basis") == expectation.effective_basis,
            "effective basis mismatch",
        )
        record(
            effective_rollup.get("reason") == expectation.effective_reason,
            "effective reason mismatch",
        )
    record(
        parse_timestamp(payload.get("last_activity_at"))
        == expectation.last_activity_at,
        "last_activity_at mismatch",
    )
    record(
        parse_timestamp(payload.get("last_transition_at"))
        == expectation.last_transition_at,
        "last_transition_at mismatch",
    )
    record(
        payload.get("terminal_reason") == expectation.terminal_reason,
        "terminal_reason mismatch",
    )
    return tuple(issues)


def key_result_detail_payload_mismatch_reasons(
    payload: dict[str, object],
    expectation: KeyResultLifecycleExpectation,
) -> tuple[str, ...]:
    """Compare one serialized key result detail payload against shared lifecycle fields."""
    issues = list(key_result_list_payload_mismatch_reasons(payload, expectation))

    def record(condition: bool, reason: str) -> None:
        if not condition:
            issues.append(reason)

    if expectation.terminal_reason is None:
        record(
            payload.get("completion_context") is None,
            "completion_context should be absent",
        )
    else:
        record(
            isinstance(payload.get("completion_context"), dict),
            "completion_context missing",
        )
    return tuple(issues)
