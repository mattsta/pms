"""Unit coverage for the MCP goal lifecycle contract audit."""

from datetime import UTC, datetime

from scripts.audit_mcp_goal_lifecycle_contracts import (
    GoalLifecycleExpectation,
    evaluate_goal_detail_payload,
    evaluate_goal_list_item_payload,
    evaluate_goal_summary_payload,
)


def test_mcp_goal_lifecycle_contract_accepts_matching_payload() -> None:
    expected = GoalLifecycleExpectation(
        goal_id="goal-1",
        goal_name="MCP Goal",
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
        "goal": {
            "id": "goal-1",
            "name": "MCP Goal",
            "status": "active",
            "progress_percent": 10,
        },
        "effective_rollup": {
            "progress_percent": 45,
            "status": "active",
            "basis": "execution_projection",
            "reason": None,
        },
        "effective_hierarchy": {
            "average_progress": 45.0,
            "basis": "execution_projection",
            "reason": None,
        },
        "execution": {
            "terminal_reason": None,
            "population_basis": "goal_plan_task_graph",
            "scoped_goal_count": 1,
            "total_tasks": 1,
            "in_progress_tasks": 1,
            "focus_task": {"id": "task-1"},
        },
        "last_activity_at": "2026-04-24T12:00:00+00:00",
        "last_transition_at": "2026-04-24T12:05:00+00:00",
        "terminal_reason": None,
        "completion_context": None,
        "links": {
            "self": {"tool": "get_goal_summary", "args": {"identifier": "goal-1"}},
            "goal": {"tool": "get_goal", "args": {"identifier": "goal-1"}},
            "objectives": {"tool": "list_objectives", "args": {"goal_id": "goal-1"}},
            "plans": {"tool": "list_plans", "args": {"goal_id": "goal-1"}},
            "project": {"tool": "get_project", "args": {"identifier": "proj-1"}},
            "tasks": {"tool": "list_tasks", "args": {"project": "proj-1"}},
        },
        "next_steps": ["Use get_task with identifier=task-1"],
    }

    assert (
        evaluate_goal_summary_payload(
            "get_goal_summary.active",
            payload,
            expected,
            project_id="proj-1",
        )
        == ()
    )


def test_mcp_goal_lifecycle_contract_flags_missing_goal_link() -> None:
    expected = GoalLifecycleExpectation(
        goal_id="goal-2",
        goal_name="Terminal Goal",
        stored_status="completed",
        progress_percent=100,
        effective_progress_percent=100,
        effective_status="completed",
        effective_basis="execution_terminal",
        effective_reason=None,
        effective_hierarchy_average_progress=100.0,
        effective_hierarchy_basis="execution_terminal",
        effective_hierarchy_reason=None,
        last_activity_at=None,
        last_transition_at=None,
        terminal_reason="all execution tasks are already complete",
        execution_terminal_reason="all execution tasks are already complete",
        execution_population_basis="goal_plan_task_graph",
        execution_scoped_goal_count=1,
        execution_total_tasks=1,
        execution_in_progress_tasks=0,
        execution_focus_task_id=None,
    )
    payload = {
        "goal": {
            "id": "goal-2",
            "name": "Terminal Goal",
            "status": "completed",
            "progress_percent": 100,
        },
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
        "last_activity_at": None,
        "last_transition_at": None,
        "terminal_reason": "all execution tasks are already complete",
        "completion_context": {
            "summary": "This goal is terminal.",
            "next_steps": ["Use get_goal with identifier=goal-2"],
        },
        "links": {
            "self": {"tool": "get_goal_summary", "args": {"identifier": "goal-2"}},
            "goal": {"tool": "get_goal", "args": {"identifier": "wrong"}},
            "objectives": {"tool": "list_objectives", "args": {"goal_id": "goal-2"}},
            "plans": {"tool": "list_plans", "args": {"goal_id": "goal-2"}},
        },
        "next_steps": ["Use get_goal with identifier=goal-2"],
    }

    issues = evaluate_goal_summary_payload(
        "get_goal_summary.terminal",
        payload,
        expected,
        project_id=None,
    )

    assert any("goal link mismatch" in issue.reason for issue in issues)


def test_mcp_goal_list_contract_accepts_matching_payload() -> None:
    expected = GoalLifecycleExpectation(
        goal_id="goal-3",
        goal_name="List Goal",
        stored_status="active",
        progress_percent=20,
        effective_progress_percent=55,
        effective_status="active",
        effective_basis="execution_projection",
        effective_reason=None,
        effective_hierarchy_average_progress=55.0,
        effective_hierarchy_basis="execution_projection",
        effective_hierarchy_reason=None,
        last_activity_at=datetime(2026, 4, 24, 13, 0, tzinfo=UTC),
        last_transition_at=datetime(2026, 4, 24, 13, 5, tzinfo=UTC),
        terminal_reason=None,
        execution_terminal_reason=None,
        execution_population_basis="goal_plan_task_graph",
        execution_scoped_goal_count=1,
        execution_total_tasks=2,
        execution_in_progress_tasks=1,
        execution_focus_task_id="task-3",
    )
    payload = {
        "id": "goal-3",
        "name": "List Goal",
        "status": "active",
        "progress_percent": 20,
        "effective_rollup": {
            "progress_percent": 55,
            "status": "active",
            "basis": "execution_projection",
            "reason": None,
        },
        "last_activity_at": "2026-04-24T13:00:00+00:00",
        "last_transition_at": "2026-04-24T13:05:00+00:00",
        "terminal_reason": None,
        "links": {
            "self": {"tool": "get_goal", "args": {"identifier": "goal-3"}},
            "summary": {"tool": "get_goal_summary", "args": {"identifier": "goal-3"}},
            "objectives": {"tool": "list_objectives", "args": {"goal_id": "goal-3"}},
            "plans": {"tool": "list_plans", "args": {"goal_id": "goal-3"}},
            "project": {"tool": "get_project", "args": {"identifier": "proj-3"}},
            "tasks": {"tool": "list_tasks", "args": {"project": "proj-3"}},
        },
        "next_steps": ["Use get_task with identifier=task-3"],
    }

    assert (
        evaluate_goal_list_item_payload(
            "list_goals.active",
            payload,
            expected,
            project_id="proj-3",
        )
        == ()
    )


def test_mcp_goal_detail_contract_accepts_matching_payload() -> None:
    expected = GoalLifecycleExpectation(
        goal_id="goal-4",
        goal_name="Detail Goal",
        stored_status="completed",
        progress_percent=100,
        effective_progress_percent=100,
        effective_status="completed",
        effective_basis="execution_terminal",
        effective_reason=None,
        effective_hierarchy_average_progress=100.0,
        effective_hierarchy_basis="execution_terminal",
        effective_hierarchy_reason=None,
        last_activity_at=datetime(2026, 4, 24, 14, 0, tzinfo=UTC),
        last_transition_at=datetime(2026, 4, 24, 14, 5, tzinfo=UTC),
        terminal_reason="all execution tasks are already complete",
        execution_terminal_reason="all execution tasks are already complete",
        execution_population_basis="goal_plan_task_graph",
        execution_scoped_goal_count=1,
        execution_total_tasks=1,
        execution_in_progress_tasks=0,
        execution_focus_task_id=None,
    )
    payload = {
        "id": "goal-4",
        "name": "Detail Goal",
        "status": "completed",
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
        "last_activity_at": "2026-04-24T14:00:00+00:00",
        "last_transition_at": "2026-04-24T14:05:00+00:00",
        "terminal_reason": "all execution tasks are already complete",
        "completion_context": {
            "summary": "This goal is terminal.",
            "next_steps": ["Use get_goal with identifier=goal-4"],
        },
        "links": {
            "self": {"tool": "get_goal", "args": {"identifier": "goal-4"}},
            "summary": {"tool": "get_goal_summary", "args": {"identifier": "goal-4"}},
            "objectives": {"tool": "list_objectives", "args": {"goal_id": "goal-4"}},
            "plans": {"tool": "list_plans", "args": {"goal_id": "goal-4"}},
        },
        "next_steps": ["Use get_goal with identifier=goal-4"],
    }

    assert (
        evaluate_goal_detail_payload(
            "get_goal.terminal",
            payload,
            expected,
            project_id=None,
        )
        == ()
    )
