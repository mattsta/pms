"""Unit coverage for the API goal lifecycle contract audit."""

from datetime import UTC, datetime

from scripts.audit_api_goal_lifecycle_contracts import (
    GoalLifecycleExpectation,
    _evaluate_goal_detail_payload,
    _evaluate_goal_list_payload,
    _evaluate_goal_summary_payload,
)


def test_api_goal_list_contract_accepts_matching_payload() -> None:
    expected = GoalLifecycleExpectation(
        goal_id="goal-1",
        goal_name="API Goal",
        stored_status="active",
        progress_percent=10,
        effective_progress_percent=45,
        effective_status="active",
        effective_basis="execution_projection",
        effective_reason=None,
        effective_hierarchy_average_progress=45.0,
        effective_hierarchy_basis="execution_projection",
        effective_hierarchy_reason=None,
        last_activity_at=datetime(2026, 4, 24, 12, 0, tzinfo=UTC),
        last_transition_at=datetime(2026, 4, 24, 12, 5, tzinfo=UTC),
        terminal_reason=None,
        execution_terminal_reason=None,
        execution_population_basis="goal_plan_task_graph",
        execution_scoped_goal_count=1,
        execution_total_tasks=1,
        execution_in_progress_tasks=1,
        execution_focus_task_id="task-1",
    )
    payload = {
        "id": "goal-1",
        "name": "API Goal",
        "status": "active",
        "project_id": "project-1",
        "progress_percent": 10,
        "effective_rollup": {
            "progress_percent": 45,
            "status": "active",
            "basis": "execution_projection",
            "reason": None,
        },
        "last_activity_at": "2026-04-24T12:00:00+00:00",
        "last_transition_at": "2026-04-24T12:05:00+00:00",
        "terminal_reason": None,
        "links": {
            "self": "/api/v1/goals/goal-1",
            "summary": "/api/v1/goals/goal-1/summary",
            "objectives": "/api/v1/goals/goal-1/objectives",
            "plans": "/api/v1/plans?goal_id=goal-1",
            "project": "/api/v1/projects/project-1",
            "tasks": "/api/v1/tasks?project_id=project-1",
            "guide": "/api/v1/",
        },
        "next_steps": [
            "GET /api/v1/goals/goal-1/summary",
            "GET /api/v1/goals/goal-1/objectives",
            "GET /api/v1/plans?goal_id=goal-1",
            "GET /api/v1/projects/project-1",
            "GET /api/v1/tasks/task-1",
        ],
    }

    assert _evaluate_goal_list_payload("goals.list.active", payload, expected) == ()


def test_api_goal_list_contract_flags_missing_discoverability_fields() -> None:
    expected = GoalLifecycleExpectation(
        goal_id="goal-1",
        goal_name="API Goal",
        stored_status="active",
        progress_percent=10,
        effective_progress_percent=45,
        effective_status="active",
        effective_basis="execution_projection",
        effective_reason=None,
        effective_hierarchy_average_progress=45.0,
        effective_hierarchy_basis="execution_projection",
        effective_hierarchy_reason=None,
        last_activity_at=datetime(2026, 4, 24, 12, 0, tzinfo=UTC),
        last_transition_at=datetime(2026, 4, 24, 12, 5, tzinfo=UTC),
        terminal_reason=None,
        execution_terminal_reason=None,
        execution_population_basis="goal_plan_task_graph",
        execution_scoped_goal_count=1,
        execution_total_tasks=1,
        execution_in_progress_tasks=1,
        execution_focus_task_id="task-1",
    )
    payload = {
        "id": "goal-1",
        "name": "API Goal",
        "status": "active",
        "project_id": "project-1",
        "progress_percent": 10,
        "effective_rollup": {
            "progress_percent": 45,
            "status": "active",
            "basis": "execution_projection",
            "reason": None,
        },
        "last_activity_at": "2026-04-24T12:00:00+00:00",
        "last_transition_at": "2026-04-24T12:05:00+00:00",
        "terminal_reason": None,
        "links": {
            "self": "/api/v1/goals/goal-1",
            "summary": "/api/v1/goals/goal-1/summary",
            "objectives": "/api/v1/goals/goal-1/objectives",
        },
        "next_steps": ["GET /api/v1/goals/goal-1/summary"],
    }

    issues = _evaluate_goal_list_payload("goals.list.active", payload, expected)

    assert any("plans link mismatch" in issue.reason for issue in issues)
    assert any("focus task next_step mismatch" in issue.reason for issue in issues)


def test_api_goal_detail_contract_accepts_matching_payload() -> None:
    expected = GoalLifecycleExpectation(
        goal_id="goal-2",
        goal_name="API Detail Goal",
        stored_status="completed",
        progress_percent=100,
        effective_progress_percent=100,
        effective_status="completed",
        effective_basis="execution_terminal",
        effective_reason=None,
        effective_hierarchy_average_progress=100.0,
        effective_hierarchy_basis="execution_terminal",
        effective_hierarchy_reason=None,
        last_activity_at=datetime(2026, 4, 24, 13, 0, tzinfo=UTC),
        last_transition_at=datetime(2026, 4, 24, 13, 5, tzinfo=UTC),
        terminal_reason="all execution tasks are already complete",
        execution_terminal_reason="all execution tasks are already complete",
        execution_population_basis="goal_plan_task_graph",
        execution_scoped_goal_count=1,
        execution_total_tasks=1,
        execution_in_progress_tasks=0,
        execution_focus_task_id=None,
    )
    payload = {
        "id": "goal-2",
        "name": "API Detail Goal",
        "status": "completed",
        "project_id": "project-2",
        "progress_percent": 100,
        "effective_rollup": {
            "progress_percent": 100,
            "status": "completed",
            "basis": "execution_terminal",
            "reason": None,
        },
        "effective_hierarchy": {
            "average_progress": 100.0,
            "basis": "execution_terminal",
            "reason": None,
        },
        "execution": {
            "terminal_reason": "all execution tasks are already complete",
            "population_basis": "goal_plan_task_graph",
            "scoped_goal_count": 1,
            "total_tasks": 1,
            "in_progress_tasks": 0,
            "focus_task": None,
        },
        "last_activity_at": "2026-04-24T13:00:00+00:00",
        "last_transition_at": "2026-04-24T13:05:00+00:00",
        "terminal_reason": "all execution tasks are already complete",
        "completion_context": {
            "summary": "This goal is terminal.",
            "next_steps": ["GET /api/v1/goals/goal-2"],
        },
        "links": {
            "self": "/api/v1/goals/goal-2",
            "summary": "/api/v1/goals/goal-2/summary",
            "objectives": "/api/v1/goals/goal-2/objectives",
            "plans": "/api/v1/plans?goal_id=goal-2",
        },
        "next_steps": ["GET /api/v1/goals/goal-2/summary"],
    }

    assert (
        _evaluate_goal_detail_payload("goals.detail.terminal", payload, expected) == ()
    )


def test_api_goal_summary_contract_flags_goal_link_mismatch() -> None:
    expected = GoalLifecycleExpectation(
        goal_id="goal-3",
        goal_name="API Summary Goal",
        stored_status="active",
        progress_percent=20,
        effective_progress_percent=60,
        effective_status="active",
        effective_basis="execution_projection",
        effective_reason=None,
        effective_hierarchy_average_progress=60.0,
        effective_hierarchy_basis="execution_projection",
        effective_hierarchy_reason=None,
        last_activity_at=None,
        last_transition_at=None,
        terminal_reason=None,
        execution_terminal_reason=None,
        execution_population_basis="goal_plan_task_graph",
        execution_scoped_goal_count=1,
        execution_total_tasks=2,
        execution_in_progress_tasks=1,
        execution_focus_task_id="task-3",
    )
    payload = {
        "goal": {
            "id": "goal-3",
            "name": "API Summary Goal",
            "status": "active",
            "project_id": "project-3",
            "progress_percent": 20,
        },
        "effective_rollup": {
            "progress_percent": 60,
            "status": "active",
            "basis": "execution_projection",
            "reason": None,
        },
        "effective_hierarchy": {
            "average_progress": 60.0,
            "basis": "execution_projection",
            "reason": None,
        },
        "execution": {
            "terminal_reason": None,
            "population_basis": "goal_plan_task_graph",
            "scoped_goal_count": 1,
            "total_tasks": 2,
            "in_progress_tasks": 1,
            "focus_task": {"id": "task-3"},
        },
        "last_activity_at": None,
        "last_transition_at": None,
        "terminal_reason": None,
        "completion_context": None,
        "links": {
            "self": "/api/v1/goals/goal-3/summary",
            "goal": "/api/v1/goals/wrong",
            "objectives": "/api/v1/goals/goal-3/objectives",
            "plans": "/api/v1/plans?goal_id=goal-3",
        },
        "next_steps": ["GET /api/v1/goals/goal-3"],
    }

    issues = _evaluate_goal_summary_payload("goals.summary.active", payload, expected)

    assert any("goal link mismatch" in issue.reason for issue in issues)
