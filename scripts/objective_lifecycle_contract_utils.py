#!/usr/bin/env python3
"""Shared helpers for objective lifecycle contract audits."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pms.services.goal_service import (
    ObjectiveSummary,
    objective_lifecycle_terminal_reason,
)


@dataclass(frozen=True)
class ObjectiveLifecycleExpectation:
    """Expected lifecycle contract for an objective aggregate payload."""

    objective_id: str
    goal_id: str
    project_id: str | None
    objective_name: str
    stored_status: str
    progress_percent: int
    effective_progress_percent: int
    effective_status: str
    effective_basis: str
    effective_reason: str | None
    effective_hierarchy_average_progress: float
    effective_hierarchy_basis: str
    effective_hierarchy_reason: str | None
    key_result_count: int
    completed_key_results: int
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


def expectation_from_summary(
    summary: ObjectiveSummary,
    *,
    project_id: str | None,
    last_activity_at: datetime | None,
    last_transition_at: datetime | None,
) -> ObjectiveLifecycleExpectation:
    """Build a shared objective lifecycle expectation from one objective summary."""
    return ObjectiveLifecycleExpectation(
        objective_id=summary.objective.id,
        goal_id=summary.objective.goal_id,
        project_id=project_id,
        objective_name=summary.objective.name,
        stored_status=summary.objective.status.value,
        progress_percent=summary.objective.progress_percent,
        effective_progress_percent=summary.effective_rollup.progress_percent,
        effective_status=summary.effective_rollup.status,
        effective_basis=summary.effective_rollup.basis,
        effective_reason=summary.effective_rollup.reason,
        effective_hierarchy_average_progress=(
            summary.effective_hierarchy.average_progress
        ),
        effective_hierarchy_basis=summary.effective_hierarchy.basis,
        effective_hierarchy_reason=summary.effective_hierarchy.reason,
        key_result_count=summary.key_result_count,
        completed_key_results=summary.completed_key_results,
        last_activity_at=last_activity_at,
        last_transition_at=last_transition_at,
        terminal_reason=objective_lifecycle_terminal_reason(
            summary.objective,
            effective_rollup=summary.effective_rollup,
        ),
    )


def objective_list_payload_mismatch_reasons(
    payload: dict[str, object],
    expectation: ObjectiveLifecycleExpectation,
) -> tuple[str, ...]:
    """Compare one serialized objective list item against shared lifecycle fields."""
    issues: list[str] = []

    def record(condition: bool, reason: str) -> None:
        if not condition:
            issues.append(reason)

    effective_rollup = payload.get("effective_rollup")
    effective_hierarchy = payload.get("effective_hierarchy")
    record(payload.get("id") == expectation.objective_id, "objective id mismatch")
    record(payload.get("goal_id") == expectation.goal_id, "goal id mismatch")
    record(
        payload.get("project_id") == expectation.project_id,
        "project id mismatch",
    )
    record(
        payload.get("name") == expectation.objective_name,
        "objective name mismatch",
    )
    record(
        payload.get("status") == expectation.stored_status,
        "stored status mismatch",
    )
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
    record(isinstance(effective_hierarchy, dict), "effective_hierarchy missing")
    if isinstance(effective_hierarchy, dict):
        record(
            effective_hierarchy.get("key_result_count") == expectation.key_result_count,
            "effective hierarchy key_result_count mismatch",
        )
        record(
            effective_hierarchy.get("completed_key_results")
            == expectation.completed_key_results,
            "effective hierarchy completed_key_results mismatch",
        )
        record(
            float(effective_hierarchy.get("average_progress", -1))
            == expectation.effective_hierarchy_average_progress,
            "effective hierarchy average progress mismatch",
        )
        record(
            effective_hierarchy.get("basis") == expectation.effective_hierarchy_basis,
            "effective hierarchy basis mismatch",
        )
        record(
            effective_hierarchy.get("reason") == expectation.effective_hierarchy_reason,
            "effective hierarchy reason mismatch",
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


def objective_detail_payload_mismatch_reasons(
    payload: dict[str, object],
    expectation: ObjectiveLifecycleExpectation,
) -> tuple[str, ...]:
    """Compare one serialized objective detail payload against shared lifecycle fields."""
    issues = list(objective_list_payload_mismatch_reasons(payload, expectation))

    def record(condition: bool, reason: str) -> None:
        if not condition:
            issues.append(reason)

    stats = payload.get("stats")
    record(isinstance(stats, dict), "stats missing")
    if isinstance(stats, dict):
        record(
            stats.get("key_result_count") == expectation.key_result_count,
            "stats key_result_count mismatch",
        )
        record(
            stats.get("completed_key_results") == expectation.completed_key_results,
            "stats completed_key_results mismatch",
        )
        record(
            float(stats.get("average_progress", -1))
            == expectation.effective_hierarchy_average_progress,
            "stats average_progress mismatch",
        )

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
