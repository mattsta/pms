"""Unit coverage for the MCP objective lifecycle contract audit."""

from datetime import UTC, datetime

from scripts.audit_mcp_objective_lifecycle_contracts import (
    ObjectiveLifecycleExpectation,
    evaluate_objective_detail_payload,
    evaluate_objective_list_item_payload,
)


def test_mcp_objective_list_contract_accepts_matching_payload() -> None:
    expected = ObjectiveLifecycleExpectation(
        objective_id="objective-1",
        goal_id="goal-1",
        project_id="project-1",
        objective_name="MCP Objective",
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
        "name": "MCP Objective",
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
            "self": {"tool": "get_objective", "args": {"objective_id": "objective-1"}},
            "goal": {"tool": "get_goal", "args": {"identifier": "goal-1"}},
            "goal_summary": {
                "tool": "get_goal_summary",
                "args": {"identifier": "goal-1"},
            },
            "key_results": {
                "tool": "list_key_results",
                "args": {"objective_id": "objective-1"},
            },
            "project": {"tool": "get_project", "args": {"identifier": "project-1"}},
        },
        "next_steps": [
            "Use get_objective with objective_id=objective-1",
            "Use list_key_results with objective_id=objective-1",
            "Use get_goal with identifier=goal-1",
            "Use get_goal_summary with identifier=goal-1",
            "Use get_project with identifier=project-1",
            "Use update_objective with objective_id=objective-1",
        ],
    }

    assert (
        evaluate_objective_list_item_payload(
            "list_objectives.active",
            payload,
            expected,
            project_id="project-1",
        )
        == ()
    )


def test_mcp_objective_detail_contract_flags_missing_key_results_link() -> None:
    expected = ObjectiveLifecycleExpectation(
        objective_id="objective-2",
        goal_id="goal-2",
        project_id="project-2",
        objective_name="Terminal Objective",
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
        last_activity_at=None,
        last_transition_at=None,
        terminal_reason="all linked key results are already complete",
    )
    payload = {
        "id": "objective-2",
        "goal_id": "goal-2",
        "project_id": "project-2",
        "name": "Terminal Objective",
        "status": "completed",
        "progress_percent": 100,
        "stats": {
            "key_result_count": 1,
            "completed_key_results": 1,
            "average_progress": 100.0,
        },
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
        "terminal_reason": "all linked key results are already complete",
        "completion_context": {
            "summary": "This objective is terminal.",
            "next_steps": ["Use get_objective with objective_id=objective-2"],
        },
        "links": {
            "self": {"tool": "get_objective", "args": {"objective_id": "objective-2"}},
            "goal": {"tool": "get_goal", "args": {"identifier": "goal-2"}},
            "goal_summary": {
                "tool": "get_goal_summary",
                "args": {"identifier": "goal-2"},
            },
            "project": {"tool": "get_project", "args": {"identifier": "project-2"}},
        },
        "next_steps": ["Use get_objective with objective_id=objective-2"],
    }

    issues = evaluate_objective_detail_payload(
        "get_objective.terminal",
        payload,
        expected,
        project_id="project-2",
    )

    assert any("key_results link mismatch" in issue.reason for issue in issues)
