"""Unit coverage for the CLI key-result lifecycle contract audit."""

from datetime import UTC, datetime

from scripts.audit_cli_key_result_lifecycle_contracts import (
    KeyResultLifecycleExpectation,
    _evaluate_key_result_list_payload,
    _evaluate_key_result_show_payload,
)


def test_cli_key_result_list_contract_accepts_matching_payload() -> None:
    expected = KeyResultLifecycleExpectation(
        key_result_id="kr-1",
        objective_id="objective-1",
        goal_id="goal-1",
        project_id="project-1",
        key_result_name="CLI Key Result",
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
        "name": "CLI Key Result",
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
            "self": "uv run pms keyresult show kr-1",
            "objective": "uv run pms objective show objective-1",
            "key_results": (
                "uv run pms keyresult list --objective-id objective-1 --format json"
            ),
            "goal": "uv run pms goal show goal-1",
            "goal_summary": "uv run pms goal summary goal-1",
            "project": "uv run pms project show project-1 --format json",
        },
        "next_steps": [
            "uv run pms keyresult show kr-1",
            "uv run pms objective show objective-1",
            "uv run pms keyresult list --objective-id objective-1 --format json",
            "uv run pms goal show goal-1",
            "uv run pms goal summary goal-1",
            "uv run pms project show project-1 --format json",
            "uv run pms keyresult update kr-1",
        ],
    }

    assert (
        _evaluate_key_result_list_payload("keyresult.list.active", payload, expected)
        == ()
    )


def test_cli_key_result_show_contract_flags_missing_key_results_link() -> None:
    expected = KeyResultLifecycleExpectation(
        key_result_id="kr-2",
        objective_id="objective-2",
        goal_id="goal-2",
        project_id="project-2",
        key_result_name="CLI Terminal Key Result",
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
        "name": "CLI Terminal Key Result",
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
            "next_steps": ["uv run pms keyresult show kr-2"],
        },
        "links": {
            "self": "uv run pms keyresult show kr-2",
            "objective": "uv run pms objective show objective-2",
            "goal": "uv run pms goal show goal-2",
            "goal_summary": "uv run pms goal summary goal-2",
            "project": "uv run pms project show project-2 --format json",
        },
        "next_steps": ["uv run pms keyresult show kr-2"],
    }

    issues = _evaluate_key_result_show_payload(
        "keyresult.show.terminal",
        payload,
        expected,
    )

    assert any("key_results link mismatch" in issue.reason for issue in issues)
