"""Unit coverage for the CLI objective lifecycle contract audit."""

from datetime import UTC, datetime

from scripts.audit_cli_objective_lifecycle_contracts import (
    ObjectiveLifecycleExpectation,
    _evaluate_objective_list_payload,
    _evaluate_objective_show_payload,
)


def test_cli_objective_list_contract_accepts_matching_payload() -> None:
    expected = ObjectiveLifecycleExpectation(
        objective_id="objective-1",
        goal_id="goal-1",
        project_id="project-1",
        objective_name="CLI Objective",
        stored_status="active",
        progress_percent=10,
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
        "name": "CLI Objective",
        "status": "active",
        "progress_percent": 10,
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
            "self": "uv run pms objective show objective-1",
            "goal": "uv run pms goal show goal-1",
            "goal_summary": "uv run pms goal summary goal-1",
            "key_results": (
                "uv run pms keyresult list --objective-id objective-1 --format json"
            ),
            "project": "uv run pms project show project-1 --format json",
        },
        "next_steps": [
            "uv run pms objective show objective-1",
            "uv run pms keyresult list --objective-id objective-1 --format json",
            "uv run pms goal show goal-1",
            "uv run pms goal summary goal-1",
            "uv run pms project show project-1 --format json",
            "uv run pms objective update objective-1",
        ],
    }

    assert (
        _evaluate_objective_list_payload(
            "objective.list.active",
            payload,
            expected,
        )
        == ()
    )


def test_cli_objective_show_contract_flags_missing_key_results_link() -> None:
    expected = ObjectiveLifecycleExpectation(
        objective_id="objective-2",
        goal_id="goal-2",
        project_id="project-2",
        objective_name="CLI Terminal Objective",
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
        "name": "CLI Terminal Objective",
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
        "terminal_reason": "all linked key results are already complete",
        "completion_context": {
            "summary": "This objective is terminal.",
            "next_steps": ["uv run pms objective show objective-2"],
        },
        "links": {
            "self": "uv run pms objective show objective-2",
            "goal": "uv run pms goal show goal-2",
            "goal_summary": "uv run pms goal summary goal-2",
            "project": "uv run pms project show project-2 --format json",
        },
        "next_steps": ["uv run pms objective show objective-2"],
    }

    issues = _evaluate_objective_show_payload(
        "objective.show.terminal",
        payload,
        expected,
    )

    assert any("key_results link mismatch" in issue.reason for issue in issues)
