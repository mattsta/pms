#!/usr/bin/env python3
"""Shared helpers for project lifecycle contract audits."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pms.services.generated_artifacts import (
    classify_project_operator_category,
    project_operator_category_label,
    project_operator_visibility_reason,
)
from pms.services.project_service import ProjectSummary


@dataclass(frozen=True)
class ProjectLifecycleExpectation:
    """Expected lifecycle contract for a project payload."""

    project_id: str
    project_name: str
    effective_status: str
    stored_status: str
    last_activity_at: datetime | None
    last_transition_at: datetime | None
    operator_category: str
    operator_category_label: str
    operator_visibility_reason: str
    terminal_reason: str | None
    focus_task_id: str | None


def parse_timestamp(value: object) -> datetime | None:
    """Parse serialized timestamps used by CLI/API/MCP surfaces."""
    if value is None:
        return None
    text = str(value)
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    return datetime.fromisoformat(text)


def expectation_from_summary(
    summary: ProjectSummary,
    *,
    focus_task_id: str | None,
) -> ProjectLifecycleExpectation:
    """Build a shared lifecycle expectation from a project summary."""
    effective_status = summary.effective_status or summary.project.status
    category = classify_project_operator_category(
        summary.project,
        effective_status=effective_status.value,
    )
    return ProjectLifecycleExpectation(
        project_id=summary.project.id,
        project_name=summary.project.name,
        effective_status=effective_status.value,
        stored_status=summary.project.status.value,
        last_activity_at=summary.last_activity_at,
        last_transition_at=summary.last_transition_at,
        operator_category=category,
        operator_category_label=project_operator_category_label(category),
        operator_visibility_reason=project_operator_visibility_reason(category),
        terminal_reason=summary.terminal_reason,
        focus_task_id=focus_task_id,
    )


def project_payload_mismatch_reasons(
    payload: dict[str, object],
    expectation: ProjectLifecycleExpectation,
    *,
    check_focus_task: bool = False,
) -> tuple[str, ...]:
    """Compare one serialized payload against the shared project lifecycle fields."""
    issues: list[str] = []

    def record(condition: bool, reason: str) -> None:
        if not condition:
            issues.append(reason)

    record(payload.get("id") == expectation.project_id, "project id mismatch")
    record(payload.get("name") == expectation.project_name, "project name mismatch")
    record(
        payload.get("status") == expectation.effective_status,
        "effective status mismatch",
    )
    record(
        payload.get("stored_status") == expectation.stored_status,
        "stored status mismatch",
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
        payload.get("operator_category") == expectation.operator_category,
        "operator_category mismatch",
    )
    record(
        payload.get("operator_category_label") == expectation.operator_category_label,
        "operator_category_label mismatch",
    )
    record(
        payload.get("operator_visibility_reason")
        == expectation.operator_visibility_reason,
        "operator_visibility_reason mismatch",
    )
    record(
        payload.get("terminal_reason") == expectation.terminal_reason,
        "terminal_reason mismatch",
    )

    if check_focus_task:
        focus_task = payload.get("focus_task")
        if expectation.focus_task_id is None:
            record(focus_task is None, "focus_task should be absent")
        else:
            record(isinstance(focus_task, dict), "focus_task missing")
            if isinstance(focus_task, dict):
                record(
                    focus_task.get("id") == expectation.focus_task_id,
                    "focus_task id mismatch",
                )

    return tuple(issues)
