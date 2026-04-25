"""Unit coverage for shared project lifecycle contract helpers."""

from datetime import UTC, datetime

from scripts.project_lifecycle_contract_utils import (
    ProjectLifecycleExpectation,
    parse_timestamp,
    project_payload_mismatch_reasons,
)


def test_project_payload_mismatch_reasons_accepts_matching_payload() -> None:
    expectation = ProjectLifecycleExpectation(
        project_id="proj-1",
        project_name="Shared Project",
        effective_status="active",
        stored_status="active",
        last_activity_at=datetime(2026, 4, 24, 18, 0, tzinfo=UTC),
        last_transition_at=datetime(2026, 4, 24, 18, 5, tzinfo=UTC),
        operator_category="active_work",
        operator_category_label="Active Work",
        operator_visibility_reason="current actionable work",
        terminal_reason=None,
        focus_task_id="task-1",
    )
    payload = {
        "id": "proj-1",
        "name": "Shared Project",
        "status": "active",
        "stored_status": "active",
        "last_activity_at": "2026-04-24T18:00:00+00:00",
        "last_transition_at": "2026-04-24T18:05:00+00:00",
        "operator_category": "active_work",
        "operator_category_label": "Active Work",
        "operator_visibility_reason": "current actionable work",
        "terminal_reason": None,
        "focus_task": {"id": "task-1"},
    }

    assert (
        project_payload_mismatch_reasons(
            payload,
            expectation,
            check_focus_task=True,
        )
        == ()
    )


def test_project_payload_mismatch_reasons_flags_focus_task_mismatch() -> None:
    expectation = ProjectLifecycleExpectation(
        project_id="proj-2",
        project_name="Terminal Project",
        effective_status="completed",
        stored_status="completed",
        last_activity_at=None,
        last_transition_at=None,
        operator_category="project_history",
        operator_category_label="Project History",
        operator_visibility_reason="retained historical lookup",
        terminal_reason="all linked execution scopes are already terminal",
        focus_task_id=None,
    )
    payload = {
        "id": "proj-2",
        "name": "Terminal Project",
        "status": "completed",
        "stored_status": "completed",
        "last_activity_at": None,
        "last_transition_at": None,
        "operator_category": "project_history",
        "operator_category_label": "Project History",
        "operator_visibility_reason": "retained historical lookup",
        "terminal_reason": "all linked execution scopes are already terminal",
        "focus_task": {"id": "task-2"},
    }

    issues = project_payload_mismatch_reasons(
        payload,
        expectation,
        check_focus_task=True,
    )

    assert "focus_task should be absent" in issues


def test_parse_timestamp_normalizes_z_suffix() -> None:
    assert parse_timestamp("2026-04-24T18:00:00Z") == datetime(
        2026,
        4,
        24,
        18,
        0,
        tzinfo=UTC,
    )
