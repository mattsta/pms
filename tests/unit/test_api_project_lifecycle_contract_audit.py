"""Unit coverage for the API project lifecycle contract audit."""

from datetime import UTC, datetime

from scripts.audit_api_project_lifecycle_contracts import (
    ProjectPayloadExpectation,
    evaluate_project_payload,
)


def test_api_project_lifecycle_contract_accepts_matching_payload() -> None:
    expected = ProjectPayloadExpectation(
        project_id="proj-1",
        project_name="API Project",
        effective_status="active",
        stored_status="active",
        last_activity_at=datetime(2026, 4, 24, 12, 0, tzinfo=UTC),
        last_transition_at=datetime(2026, 4, 24, 12, 5, tzinfo=UTC),
        operator_category="active_work",
        operator_category_label="Active Work",
        operator_visibility_reason="current actionable work",
        terminal_reason=None,
        focus_task_id="task-1",
    )
    payload = {
        "id": "proj-1",
        "name": "API Project",
        "status": "active",
        "stored_status": "active",
        "last_activity_at": "2026-04-24T12:00:00+00:00",
        "last_transition_at": "2026-04-24T12:05:00+00:00",
        "operator_category": "active_work",
        "operator_category_label": "Active Work",
        "operator_visibility_reason": "current actionable work",
        "terminal_reason": None,
        "focus_task": {"id": "task-1"},
        "links": {"self": "/api/v1/projects/proj-1"},
        "next_steps": ["GET /api/v1/projects/proj-1/summary"],
    }

    assert evaluate_project_payload("detail", payload, expected) == ()


def test_api_project_lifecycle_contract_flags_focus_task_on_terminal_payload() -> None:
    expected = ProjectPayloadExpectation(
        project_id="proj-2",
        project_name="API Terminal Project",
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
        "name": "API Terminal Project",
        "status": "completed",
        "stored_status": "completed",
        "last_activity_at": None,
        "last_transition_at": None,
        "operator_category": "project_history",
        "operator_category_label": "Project History",
        "operator_visibility_reason": "retained historical lookup",
        "terminal_reason": "all linked execution scopes are already terminal",
        "focus_task": {"id": "task-2"},
        "links": {"self": "/api/v1/projects/proj-2"},
        "next_steps": ["GET /api/v1/projects/proj-2/summary"],
    }

    issues = evaluate_project_payload("detail", payload, expected)

    assert any("focus_task should be absent" in issue.reason for issue in issues)
