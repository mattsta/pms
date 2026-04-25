"""Unit coverage for the API objective lifecycle contract audit."""

from datetime import UTC, datetime

from scripts.audit_api_objective_lifecycle_contracts import (
    ObjectiveLifecycleExpectation,
    _evaluate_objective_detail_payload,
    _evaluate_objective_list_payload,
)


def test_api_objective_list_contract_accepts_matching_payload() -> None:
    expected = ObjectiveLifecycleExpectation(
        objective_id="objective-1",
        goal_id="goal-1",
        project_id="project-1",
        objective_name="API Objective",
        stored_status="active",
        progress_percent=45,
        effective_progress_percent=45,
        effective_status="active",
        effective_basis="key_result_rollup",
        effective_reason="derived from linked key results",
        effective_hierarchy_average_progress=45.0,
        effective_hierarchy_basis="key_result_rollup",
        effective_hierarchy_reason="derived from linked key results",
        key_result_count=2,
        completed_key_results=0,
        last_activity_at=datetime(2026, 4, 24, 12, 0, tzinfo=UTC),
        last_transition_at=datetime(2026, 4, 24, 12, 5, tzinfo=UTC),
        terminal_reason=None,
    )
    payload = {
        "id": "objective-1",
        "goal_id": "goal-1",
        "project_id": "project-1",
        "name": "API Objective",
        "status": "active",
        "progress_percent": 45,
        "effective_rollup": {
            "progress_percent": 45,
            "status": "active",
            "basis": "key_result_rollup",
            "reason": "derived from linked key results",
        },
        "effective_hierarchy": {
            "key_result_count": 2,
            "completed_key_results": 0,
            "average_progress": 45.0,
            "basis": "key_result_rollup",
            "reason": "derived from linked key results",
        },
        "last_activity_at": "2026-04-24T12:00:00+00:00",
        "last_transition_at": "2026-04-24T12:05:00+00:00",
        "terminal_reason": None,
        "links": {
            "self": "/api/v1/objectives/objective-1",
            "goal": "/api/v1/goals/goal-1",
            "goal_summary": "/api/v1/goals/goal-1/summary",
            "key_results": "/api/v1/objectives/objective-1/key-results",
            "project": "/api/v1/projects/project-1",
            "guide": "/api/v1/",
        },
        "next_steps": [
            "GET /api/v1/objectives/objective-1",
            "GET /api/v1/objectives/objective-1/key-results",
            "GET /api/v1/goals/goal-1",
            "GET /api/v1/goals/goal-1/summary",
            "GET /api/v1/projects/project-1",
        ],
    }

    assert (
        _evaluate_objective_list_payload("objectives.list.active", payload, expected)
        == ()
    )


def test_api_objective_list_contract_flags_missing_key_result_link() -> None:
    expected = ObjectiveLifecycleExpectation(
        objective_id="objective-1",
        goal_id="goal-1",
        project_id="project-1",
        objective_name="API Objective",
        stored_status="active",
        progress_percent=45,
        effective_progress_percent=45,
        effective_status="active",
        effective_basis="key_result_rollup",
        effective_reason="derived from linked key results",
        effective_hierarchy_average_progress=45.0,
        effective_hierarchy_basis="key_result_rollup",
        effective_hierarchy_reason="derived from linked key results",
        key_result_count=2,
        completed_key_results=0,
        last_activity_at=None,
        last_transition_at=None,
        terminal_reason=None,
    )
    payload = {
        "id": "objective-1",
        "goal_id": "goal-1",
        "project_id": "project-1",
        "name": "API Objective",
        "status": "active",
        "progress_percent": 45,
        "effective_rollup": {
            "progress_percent": 45,
            "status": "active",
            "basis": "key_result_rollup",
            "reason": "derived from linked key results",
        },
        "effective_hierarchy": {
            "key_result_count": 2,
            "completed_key_results": 0,
            "average_progress": 45.0,
            "basis": "key_result_rollup",
            "reason": "derived from linked key results",
        },
        "terminal_reason": None,
        "links": {
            "self": "/api/v1/objectives/objective-1",
            "goal": "/api/v1/goals/goal-1",
            "goal_summary": "/api/v1/goals/goal-1/summary",
            "project": "/api/v1/projects/project-1",
            "guide": "/api/v1/",
        },
        "next_steps": ["GET /api/v1/objectives/objective-1"],
    }

    issues = _evaluate_objective_list_payload(
        "objectives.list.active", payload, expected
    )

    assert any("key_results link mismatch" in issue.reason for issue in issues)
    assert any("goal next_step mismatch" in issue.reason for issue in issues)


def test_api_objective_detail_contract_accepts_terminal_payload() -> None:
    expected = ObjectiveLifecycleExpectation(
        objective_id="objective-2",
        goal_id="goal-2",
        project_id="project-2",
        objective_name="API Terminal Objective",
        stored_status="completed",
        progress_percent=100,
        effective_progress_percent=100,
        effective_status="completed",
        effective_basis="key_result_rollup",
        effective_reason="all linked key results are already complete",
        effective_hierarchy_average_progress=100.0,
        effective_hierarchy_basis="key_result_rollup",
        effective_hierarchy_reason="all linked key results are already complete",
        key_result_count=1,
        completed_key_results=1,
        last_activity_at=datetime(2026, 4, 24, 13, 0, tzinfo=UTC),
        last_transition_at=datetime(2026, 4, 24, 13, 5, tzinfo=UTC),
        terminal_reason="all linked key results are already complete",
    )
    payload = {
        "id": "objective-2",
        "goal_id": "goal-2",
        "project_id": "project-2",
        "name": "API Terminal Objective",
        "status": "completed",
        "progress_percent": 100,
        "effective_rollup": {
            "progress_percent": 100,
            "status": "completed",
            "basis": "key_result_rollup",
            "reason": "all linked key results are already complete",
        },
        "effective_hierarchy": {
            "key_result_count": 1,
            "completed_key_results": 1,
            "average_progress": 100.0,
            "basis": "key_result_rollup",
            "reason": "all linked key results are already complete",
        },
        "stats": {
            "key_result_count": 1,
            "completed_key_results": 1,
            "average_progress": 100.0,
        },
        "last_activity_at": "2026-04-24T13:00:00+00:00",
        "last_transition_at": "2026-04-24T13:05:00+00:00",
        "terminal_reason": "all linked key results are already complete",
        "completion_context": {
            "summary": "This objective is terminal. all linked key results are already complete.",
            "next_steps": ["GET /api/v1/objectives/objective-2"],
        },
        "links": {
            "self": "/api/v1/objectives/objective-2",
            "goal": "/api/v1/goals/goal-2",
            "goal_summary": "/api/v1/goals/goal-2/summary",
            "key_results": "/api/v1/objectives/objective-2/key-results",
            "project": "/api/v1/projects/project-2",
            "guide": "/api/v1/",
        },
        "next_steps": [
            "GET /api/v1/objectives/objective-2",
            "GET /api/v1/objectives/objective-2/key-results",
        ],
    }

    assert (
        _evaluate_objective_detail_payload(
            "objectives.detail.terminal",
            payload,
            expected,
        )
        == ()
    )
