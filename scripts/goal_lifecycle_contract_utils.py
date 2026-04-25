#!/usr/bin/env python3
"""Shared helpers for goal lifecycle contract audits."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pms.services.goal_service import GoalSummary, goal_lifecycle_terminal_reason


@dataclass(frozen=True)
class GoalLifecycleExpectation:
    """Expected lifecycle contract for a goal aggregate payload."""

    goal_id: str
    goal_name: str
    stored_status: str
    progress_percent: int
    effective_progress_percent: int
    effective_status: str
    effective_basis: str
    effective_reason: str | None
    effective_hierarchy_average_progress: float
    effective_hierarchy_basis: str
    effective_hierarchy_reason: str | None
    last_activity_at: datetime | None
    last_transition_at: datetime | None
    terminal_reason: str | None
    execution_terminal_reason: str | None
    execution_population_basis: str | None
    execution_scoped_goal_count: int | None
    execution_total_tasks: int | None
    execution_in_progress_tasks: int | None
    execution_focus_task_id: str | None


def parse_timestamp(value: object) -> datetime | None:
    """Parse serialized timestamps used by CLI/API/MCP surfaces."""
    if value is None:
        return None
    text = str(value)
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    return datetime.fromisoformat(text)


def expectation_from_summary(
    summary: GoalSummary,
    *,
    last_activity_at: datetime | None,
    last_transition_at: datetime | None,
) -> GoalLifecycleExpectation:
    """Build a shared goal lifecycle expectation from one goal summary."""
    execution = summary.execution
    return GoalLifecycleExpectation(
        goal_id=summary.goal.id,
        goal_name=summary.goal.name,
        stored_status=summary.goal.status.value,
        progress_percent=summary.goal.progress_percent,
        effective_progress_percent=summary.effective_rollup.progress_percent,
        effective_status=summary.effective_rollup.status,
        effective_basis=summary.effective_rollup.basis,
        effective_reason=summary.effective_rollup.reason,
        effective_hierarchy_average_progress=(
            summary.effective_hierarchy.average_progress
        ),
        effective_hierarchy_basis=summary.effective_hierarchy.basis,
        effective_hierarchy_reason=summary.effective_hierarchy.reason,
        last_activity_at=last_activity_at,
        last_transition_at=last_transition_at,
        terminal_reason=goal_lifecycle_terminal_reason(
            summary.goal,
            effective_rollup=summary.effective_rollup,
            execution=execution,
        ),
        execution_terminal_reason=(
            execution.terminal_reason if execution is not None else None
        ),
        execution_population_basis=(
            execution.population_basis if execution is not None else None
        ),
        execution_scoped_goal_count=(
            execution.scoped_goal_count if execution is not None else None
        ),
        execution_total_tasks=execution.total_tasks if execution is not None else None,
        execution_in_progress_tasks=(
            execution.in_progress_tasks if execution is not None else None
        ),
        execution_focus_task_id=(
            execution.focus_task.id
            if execution is not None and execution.focus_task is not None
            else None
        ),
    )


def goal_list_payload_mismatch_reasons(
    payload: dict[str, object],
    expectation: GoalLifecycleExpectation,
) -> tuple[str, ...]:
    """Compare one serialized goal list item against the shared lifecycle fields."""
    issues: list[str] = []

    def record(condition: bool, reason: str) -> None:
        if not condition:
            issues.append(reason)

    effective_rollup = payload.get("effective_rollup")
    record(payload.get("id") == expectation.goal_id, "goal id mismatch")
    record(payload.get("name") == expectation.goal_name, "goal name mismatch")
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


def goal_detail_payload_mismatch_reasons(
    payload: dict[str, object],
    expectation: GoalLifecycleExpectation,
) -> tuple[str, ...]:
    """Compare one serialized goal detail payload against shared lifecycle fields."""
    issues = list(goal_list_payload_mismatch_reasons(payload, expectation))

    def record(condition: bool, reason: str) -> None:
        if not condition:
            issues.append(reason)

    effective_hierarchy = payload.get("effective_hierarchy")
    execution = payload.get("execution")

    record(isinstance(effective_hierarchy, dict), "effective_hierarchy missing")
    if isinstance(effective_hierarchy, dict):
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

    if expectation.execution_population_basis is None:
        record(execution is None, "execution should be absent")
    else:
        record(isinstance(execution, dict), "execution payload missing")
        if isinstance(execution, dict):
            record(
                execution.get("terminal_reason")
                == expectation.execution_terminal_reason,
                "execution terminal_reason mismatch",
            )
            record(
                execution.get("population_basis")
                == expectation.execution_population_basis,
                "execution population_basis mismatch",
            )
            record(
                execution.get("scoped_goal_count")
                == expectation.execution_scoped_goal_count,
                "execution scoped_goal_count mismatch",
            )
            record(
                execution.get("total_tasks") == expectation.execution_total_tasks,
                "execution total_tasks mismatch",
            )
            record(
                execution.get("in_progress_tasks")
                == expectation.execution_in_progress_tasks,
                "execution in_progress_tasks mismatch",
            )
            focus_task = execution.get("focus_task")
            if expectation.execution_focus_task_id is None:
                record(focus_task is None, "execution focus_task should be absent")
            else:
                record(isinstance(focus_task, dict), "execution focus_task missing")
                if isinstance(focus_task, dict):
                    record(
                        focus_task.get("id") == expectation.execution_focus_task_id,
                        "execution focus_task id mismatch",
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


def goal_summary_payload_mismatch_reasons(
    payload: dict[str, object],
    expectation: GoalLifecycleExpectation,
) -> tuple[str, ...]:
    """Compare one serialized goal summary payload against shared lifecycle fields."""
    issues: list[str] = []

    def record(condition: bool, reason: str) -> None:
        if not condition:
            issues.append(reason)

    goal_payload = payload.get("goal")
    effective_rollup = payload.get("effective_rollup")
    effective_hierarchy = payload.get("effective_hierarchy")
    execution = payload.get("execution")

    record(isinstance(goal_payload, dict), "goal payload missing")
    if isinstance(goal_payload, dict):
        record(goal_payload.get("id") == expectation.goal_id, "goal id mismatch")
        record(
            goal_payload.get("name") == expectation.goal_name,
            "goal name mismatch",
        )
        record(
            goal_payload.get("status") == expectation.stored_status,
            "stored status mismatch",
        )
        record(
            goal_payload.get("progress_percent") == expectation.progress_percent,
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

    if expectation.execution_population_basis is None:
        record(execution is None, "execution should be absent")
    else:
        record(isinstance(execution, dict), "execution payload missing")
        if isinstance(execution, dict):
            record(
                execution.get("terminal_reason")
                == expectation.execution_terminal_reason,
                "execution terminal_reason mismatch",
            )
            record(
                execution.get("population_basis")
                == expectation.execution_population_basis,
                "execution population_basis mismatch",
            )
            record(
                execution.get("scoped_goal_count")
                == expectation.execution_scoped_goal_count,
                "execution scoped_goal_count mismatch",
            )
            record(
                execution.get("total_tasks") == expectation.execution_total_tasks,
                "execution total_tasks mismatch",
            )
            record(
                execution.get("in_progress_tasks")
                == expectation.execution_in_progress_tasks,
                "execution in_progress_tasks mismatch",
            )
            focus_task = execution.get("focus_task")
            if expectation.execution_focus_task_id is None:
                record(focus_task is None, "execution focus_task should be absent")
            else:
                record(isinstance(focus_task, dict), "execution focus_task missing")
                if isinstance(focus_task, dict):
                    record(
                        focus_task.get("id") == expectation.execution_focus_task_id,
                        "execution focus_task id mismatch",
                    )

    return tuple(issues)
