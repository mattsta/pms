"""Unit coverage for the MCP key-result lifecycle contract audit."""

from datetime import UTC, datetime

from scripts.audit_mcp_key_result_lifecycle_contracts import (
    KeyResultLifecycleExpectation,
    _evaluate_key_result_detail_payload,
    _evaluate_key_result_list_payload,
)


def test_mcp_key_result_list_contract_accepts_matching_payload() -> None:
    expected = KeyResultLifecycleExpectation(
        key_result_id="kr-1",
        objective_id="objective-1",
        goal_id="goal-1",
        project_id="project-1",
        key_result_name="MCP Key Result",
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
        "name": "MCP Key Result",
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
            "self": {"tool": "get_key_result", "args": {"key_result_id": "kr-1"}},
            "objective": {
                "tool": "get_objective",
                "args": {"objective_id": "objective-1"},
            },
            "key_results": {
                "tool": "list_key_results",
                "args": {"objective_id": "objective-1"},
            },
            "goal": {"tool": "get_goal", "args": {"identifier": "goal-1"}},
            "goal_summary": {
                "tool": "get_goal_summary",
                "args": {"identifier": "goal-1"},
            },
            "project": {"tool": "get_project", "args": {"identifier": "project-1"}},
        },
        "next_steps": [
            "Use get_key_result with key_result_id=kr-1",
            "Use get_objective with objective_id=objective-1",
            "Use list_key_results with objective_id=objective-1",
            "Use get_goal with identifier=goal-1",
            "Use get_goal_summary with identifier=goal-1",
            "Use get_project with identifier=project-1",
            "Use update_key_result with key_result_id=kr-1",
        ],
    }

    assert (
        _evaluate_key_result_list_payload("key_results.list.active", payload, expected)
        == ()
    )


def test_mcp_key_result_detail_contract_flags_missing_goal_summary_link() -> None:
    expected = KeyResultLifecycleExpectation(
        key_result_id="kr-2",
        objective_id="objective-2",
        goal_id="goal-2",
        project_id="project-2",
        key_result_name="MCP Terminal Key Result",
        stored_status="completed",
        progress_percent=100,
        effective_progress_percent=100,
        effective_status="completed",
        effective_basis="stored_key_result",
        effective_reason=None,
        last_activity_at=None,
        last_transition_at=None,
        terminal_reason="key result is already marked completed",
    )
    payload = {
        "id": "kr-2",
        "objective_id": "objective-2",
        "goal_id": "goal-2",
        "project_id": "project-2",
        "name": "MCP Terminal Key Result",
        "status": "completed",
        "progress_percent": 100,
        "effective_rollup": {
            "progress_percent": 100,
            "status": "completed",
            "basis": "stored_key_result",
            "reason": None,
        },
        "terminal_reason": "key result is already marked completed",
        "completion_context": {
            "summary": "This key result is terminal.",
            "next_steps": ["Use get_key_result with key_result_id=kr-2"],
        },
        "links": {
            "self": {"tool": "get_key_result", "args": {"key_result_id": "kr-2"}},
            "objective": {
                "tool": "get_objective",
                "args": {"objective_id": "objective-2"},
            },
            "key_results": {
                "tool": "list_key_results",
                "args": {"objective_id": "objective-2"},
            },
            "goal": {"tool": "get_goal", "args": {"identifier": "goal-2"}},
            "project": {"tool": "get_project", "args": {"identifier": "project-2"}},
        },
        "next_steps": ["Use get_key_result with key_result_id=kr-2"],
    }

    issues = _evaluate_key_result_detail_payload(
        "key_results.detail.terminal",
        payload,
        expected,
    )

    assert any("goal_summary link mismatch" in issue.reason for issue in issues)
