"""Unit coverage for the API key result lifecycle contract audit."""

from datetime import UTC, datetime

from scripts.audit_api_key_result_lifecycle_contracts import (
    KeyResultLifecycleExpectation,
    _evaluate_key_result_detail_payload,
    _evaluate_key_result_list_payload,
)


def test_api_key_result_list_contract_accepts_matching_payload() -> None:
    expected = KeyResultLifecycleExpectation(
        key_result_id="kr-1",
        objective_id="objective-1",
        goal_id="goal-1",
        project_id="project-1",
        key_result_name="API Key Result",
        stored_status="active",
        progress_percent=35,
        effective_progress_percent=35,
        effective_status="active",
        effective_basis="stored_key_result",
        effective_reason=None,
        last_activity_at=datetime(2026, 4, 24, 12, 0, tzinfo=UTC),
        last_transition_at=datetime(2026, 4, 24, 12, 5, tzinfo=UTC),
        terminal_reason=None,
    )
    payload = {
        "id": "kr-1",
        "objective_id": "objective-1",
        "goal_id": "goal-1",
        "project_id": "project-1",
        "name": "API Key Result",
        "status": "active",
        "progress_percent": 35,
        "effective_rollup": {
            "progress_percent": 35,
            "status": "active",
            "basis": "stored_key_result",
            "reason": None,
        },
        "last_activity_at": "2026-04-24T12:00:00+00:00",
        "last_transition_at": "2026-04-24T12:05:00+00:00",
        "terminal_reason": None,
        "links": {
            "self": "/api/v1/key-results/kr-1",
            "objective": "/api/v1/objectives/objective-1",
            "objective_key_results": "/api/v1/objectives/objective-1/key-results",
            "goal": "/api/v1/goals/goal-1",
            "goal_summary": "/api/v1/goals/goal-1/summary",
            "project": "/api/v1/projects/project-1",
            "guide": "/api/v1/",
        },
        "next_steps": [
            "GET /api/v1/key-results/kr-1",
            "GET /api/v1/objectives/objective-1",
            "GET /api/v1/objectives/objective-1/key-results",
            "GET /api/v1/goals/goal-1",
            "GET /api/v1/goals/goal-1/summary",
            "GET /api/v1/projects/project-1",
        ],
    }

    assert (
        _evaluate_key_result_list_payload("key_results.list.active", payload, expected)
        == ()
    )


def test_api_key_result_list_contract_flags_missing_objective_collection_link() -> None:
    expected = KeyResultLifecycleExpectation(
        key_result_id="kr-1",
        objective_id="objective-1",
        goal_id="goal-1",
        project_id="project-1",
        key_result_name="API Key Result",
        stored_status="active",
        progress_percent=35,
        effective_progress_percent=35,
        effective_status="active",
        effective_basis="stored_key_result",
        effective_reason=None,
        last_activity_at=None,
        last_transition_at=None,
        terminal_reason=None,
    )
    payload = {
        "id": "kr-1",
        "objective_id": "objective-1",
        "goal_id": "goal-1",
        "project_id": "project-1",
        "name": "API Key Result",
        "status": "active",
        "progress_percent": 35,
        "effective_rollup": {
            "progress_percent": 35,
            "status": "active",
            "basis": "stored_key_result",
            "reason": None,
        },
        "terminal_reason": None,
        "links": {
            "self": "/api/v1/key-results/kr-1",
            "objective": "/api/v1/objectives/objective-1",
            "goal": "/api/v1/goals/goal-1",
            "goal_summary": "/api/v1/goals/goal-1/summary",
            "project": "/api/v1/projects/project-1",
            "guide": "/api/v1/",
        },
        "next_steps": ["GET /api/v1/key-results/kr-1"],
    }

    issues = _evaluate_key_result_list_payload(
        "key_results.list.active", payload, expected
    )

    assert any(
        "objective_key_results link mismatch" in issue.reason for issue in issues
    )
    assert any("goal next_step mismatch" in issue.reason for issue in issues)


def test_api_key_result_detail_contract_accepts_terminal_payload() -> None:
    expected = KeyResultLifecycleExpectation(
        key_result_id="kr-2",
        objective_id="objective-2",
        goal_id="goal-2",
        project_id="project-2",
        key_result_name="API Terminal Key Result",
        stored_status="completed",
        progress_percent=100,
        effective_progress_percent=100,
        effective_status="completed",
        effective_basis="stored_key_result",
        effective_reason=None,
        last_activity_at=datetime(2026, 4, 24, 13, 0, tzinfo=UTC),
        last_transition_at=datetime(2026, 4, 24, 13, 5, tzinfo=UTC),
        terminal_reason="key result is already marked completed",
    )
    payload = {
        "id": "kr-2",
        "objective_id": "objective-2",
        "goal_id": "goal-2",
        "project_id": "project-2",
        "name": "API Terminal Key Result",
        "status": "completed",
        "progress_percent": 100,
        "effective_rollup": {
            "progress_percent": 100,
            "status": "completed",
            "basis": "stored_key_result",
            "reason": None,
        },
        "last_activity_at": "2026-04-24T13:00:00+00:00",
        "last_transition_at": "2026-04-24T13:05:00+00:00",
        "terminal_reason": "key result is already marked completed",
        "completion_context": {
            "summary": "This key result is terminal. key result is already marked completed.",
            "next_steps": ["GET /api/v1/key-results/kr-2"],
        },
        "links": {
            "self": "/api/v1/key-results/kr-2",
            "objective": "/api/v1/objectives/objective-2",
            "objective_key_results": "/api/v1/objectives/objective-2/key-results",
            "goal": "/api/v1/goals/goal-2",
            "goal_summary": "/api/v1/goals/goal-2/summary",
            "project": "/api/v1/projects/project-2",
            "guide": "/api/v1/",
        },
        "next_steps": [
            "GET /api/v1/key-results/kr-2",
            "GET /api/v1/objectives/objective-2",
        ],
    }

    assert (
        _evaluate_key_result_detail_payload(
            "key_results.detail.terminal",
            payload,
            expected,
        )
        == ()
    )
