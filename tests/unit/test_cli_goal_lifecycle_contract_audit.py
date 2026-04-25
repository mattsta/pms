"""Unit coverage for the CLI goal lifecycle contract audit."""

from datetime import UTC, datetime

from scripts.audit_cli_goal_lifecycle_contracts import (
    GoalLifecycleExpectation,
    _evaluate_goal_list_item_payload,
    _evaluate_goal_show_payload,
    _evaluate_goal_summary_payload,
)


def test_cli_goal_show_contract_accepts_matching_payload() -> None:
    expected = GoalLifecycleExpectation(
        goal_id="goal-1",
        goal_name="CLI Goal",
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
        "name": "CLI Goal",
        "status": "active",
        "progress_percent": 10,
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
            "self": "uv run pms goal show goal-1",
            "summary": "uv run pms goal summary goal-1",
            "objectives": "uv run pms objective list --goal-id goal-1",
            "plans": "uv run pms plan list --goal-id goal-1 --format json",
            "project": "uv run pms project show proj-1 --format json",
            "tasks": "uv run pms task list --project proj-1 --format json",
        },
        "next_steps": ['uv run pms task show "Task 1" --project "Project 1"'],
    }

    assert (
        _evaluate_goal_show_payload(
            "goal.show.active",
            payload,
            expected,
            project_id="proj-1",
        )
        == ()
    )


def test_cli_goal_list_contract_accepts_matching_payload() -> None:
    expected = GoalLifecycleExpectation(
        goal_id="goal-list-1",
        goal_name="CLI List Goal",
        stored_status="active",
        progress_percent=10,
        effective_progress_percent=45,
        effective_status="active",
        effective_basis="execution_projection",
        effective_reason=None,
        effective_hierarchy_average_progress=45.0,
        effective_hierarchy_basis="execution_projection",
        effective_hierarchy_reason=None,
        last_activity_at=datetime(2026, 4, 24, 11, 0, tzinfo=UTC),
        last_transition_at=datetime(2026, 4, 24, 11, 5, tzinfo=UTC),
        terminal_reason=None,
        execution_terminal_reason=None,
        execution_population_basis="goal_plan_task_graph",
        execution_scoped_goal_count=1,
        execution_total_tasks=1,
        execution_in_progress_tasks=1,
        execution_focus_task_id="task-list-1",
    )
    payload = {
        "id": "goal-list-1",
        "name": "CLI List Goal",
        "status": "active",
        "progress_percent": 10,
        "effective_rollup": {
            "progress_percent": 45,
            "status": "active",
            "basis": "execution_projection",
            "reason": None,
        },
        "last_activity_at": "2026-04-24T11:00:00+00:00",
        "last_transition_at": "2026-04-24T11:05:00+00:00",
        "terminal_reason": None,
        "links": {
            "self": "uv run pms goal show goal-list-1",
            "summary": "uv run pms goal summary goal-list-1",
            "objectives": "uv run pms objective list --goal-id goal-list-1",
            "plans": "uv run pms plan list --goal-id goal-list-1 --format json",
            "project": "uv run pms project show proj-list-1 --format json",
            "tasks": "uv run pms task list --project proj-list-1 --format json",
        },
    }

    assert (
        _evaluate_goal_list_item_payload(
            "goal.list.active",
            payload,
            expected,
            project_id="proj-list-1",
        )
        == ()
    )


def test_cli_goal_summary_contract_accepts_matching_payload() -> None:
    expected = GoalLifecycleExpectation(
        goal_id="goal-2",
        goal_name="CLI Summary Goal",
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
        "goal": {
            "id": "goal-2",
            "name": "CLI Summary Goal",
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
        "last_activity_at": "2026-04-24T13:00:00+00:00",
        "last_transition_at": "2026-04-24T13:05:00+00:00",
        "terminal_reason": "all execution tasks are already complete",
        "completion_context": {
            "summary": "This goal is terminal.",
            "next_steps": ["uv run pms goal show goal-2"],
        },
        "links": {
            "self": "uv run pms goal summary goal-2",
            "goal": "uv run pms goal show goal-2",
            "objectives": "uv run pms objective list --goal-id goal-2 --format json",
            "plans": "uv run pms plan list --goal-id goal-2 --format json",
            "project": "uv run pms project show proj-2 --format json",
            "tasks": "uv run pms task list --project proj-2 --format json",
        },
        "next_steps": ["uv run pms goal show goal-2"],
    }

    assert (
        _evaluate_goal_summary_payload(
            "goal.summary.terminal",
            payload,
            expected,
            project_id="proj-2",
        )
        == ()
    )


def test_cli_goal_show_contract_flags_summary_link_mismatch() -> None:
    expected = GoalLifecycleExpectation(
        goal_id="goal-3",
        goal_name="Broken Goal",
        stored_status="active",
        progress_percent=5,
        effective_progress_percent=25,
        effective_status="active",
        effective_basis="execution_projection",
        effective_reason=None,
        effective_hierarchy_average_progress=25.0,
        effective_hierarchy_basis="execution_projection",
        effective_hierarchy_reason=None,
        last_activity_at=None,
        last_transition_at=None,
        terminal_reason=None,
        execution_terminal_reason=None,
        execution_population_basis="goal_plan_task_graph",
        execution_scoped_goal_count=1,
        execution_total_tasks=1,
        execution_in_progress_tasks=1,
        execution_focus_task_id="task-3",
    )
    payload = {
        "id": "goal-3",
        "name": "Broken Goal",
        "status": "active",
        "progress_percent": 5,
        "effective_rollup": {
            "progress_percent": 25,
            "status": "active",
            "basis": "execution_projection",
            "reason": None,
        },
        "effective_hierarchy": {
            "average_progress": 25.0,
            "basis": "execution_projection",
            "reason": None,
        },
        "execution": {
            "terminal_reason": None,
            "population_basis": "goal_plan_task_graph",
            "scoped_goal_count": 1,
            "total_tasks": 1,
            "in_progress_tasks": 1,
            "focus_task": {"id": "task-3"},
        },
        "last_activity_at": None,
        "last_transition_at": None,
        "terminal_reason": None,
        "completion_context": None,
        "links": {
            "self": "uv run pms goal show goal-3",
            "summary": "uv run pms goal summary wrong",
            "objectives": "uv run pms objective list --goal-id goal-3",
            "plans": "uv run pms plan list --goal-id goal-3 --format json",
        },
        "next_steps": ["uv run pms task show task-3"],
    }

    issues = _evaluate_goal_show_payload(
        "goal.show.active",
        payload,
        expected,
        project_id=None,
    )

    assert any("summary link mismatch" in issue.reason for issue in issues)


def test_cli_goal_list_contract_flags_plans_link_mismatch() -> None:
    expected = GoalLifecycleExpectation(
        goal_id="goal-list-2",
        goal_name="Broken List Goal",
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
        "id": "goal-list-2",
        "name": "Broken List Goal",
        "status": "completed",
        "progress_percent": 100,
        "effective_rollup": {
            "progress_percent": 100,
            "status": "completed",
            "basis": "execution_terminal",
            "reason": None,
        },
        "last_activity_at": None,
        "last_transition_at": None,
        "terminal_reason": "all execution tasks are already complete",
        "links": {
            "self": "uv run pms goal show goal-list-2",
            "summary": "uv run pms goal summary goal-list-2",
            "objectives": "uv run pms objective list --goal-id goal-list-2",
            "plans": "uv run pms plan list wrong",
        },
    }

    issues = _evaluate_goal_list_item_payload(
        "goal.list.terminal",
        payload,
        expected,
        project_id=None,
    )

    assert any("plans link mismatch" in issue.reason for issue in issues)
