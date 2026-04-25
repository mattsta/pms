#!/usr/bin/env python3
"""Shared seeded graphs for lifecycle aggregate audit surfaces."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pms.models import GoalStatus, PlanFormat, PlanStatus, ProjectStatus
from pms.services.comment_service import CommentService
from pms.services.goal_service import GoalService
from pms.services.plan_service import PlanService
from pms.services.project_service import ProjectService
from pms.services.task_service import TaskService
from scripts.goal_lifecycle_contract_utils import (
    GoalLifecycleExpectation,
)
from scripts.goal_lifecycle_contract_utils import (
    expectation_from_summary as goal_expectation_from_summary,
)
from scripts.key_result_lifecycle_contract_utils import (
    KeyResultLifecycleExpectation,
    expectation_from_key_result,
)
from scripts.objective_lifecycle_contract_utils import (
    ObjectiveLifecycleExpectation,
)
from scripts.objective_lifecycle_contract_utils import (
    expectation_from_summary as objective_expectation_from_summary,
)


@dataclass(frozen=True)
class GoalLifecycleFixture:
    """Stable references for one seeded goal lifecycle graph."""

    active_project_id: str
    active_goal_id: str
    active_task_id: str
    terminal_project_id: str
    terminal_goal_id: str
    terminal_task_id: str


@dataclass(frozen=True)
class ObjectiveLifecycleFixture:
    """Stable references for one seeded objective lifecycle graph."""

    active_project_id: str
    active_goal_id: str
    active_objective_id: str
    active_key_result_ids: tuple[str, ...]
    terminal_project_id: str
    terminal_goal_id: str
    terminal_objective_id: str
    terminal_key_result_id: str


@dataclass(frozen=True)
class KeyResultLifecycleFixture:
    """Stable references for one seeded key-result lifecycle graph."""

    active_project_id: str
    active_goal_id: str
    active_objective_id: str
    active_key_result_id: str
    terminal_project_id: str
    terminal_goal_id: str
    terminal_objective_id: str
    terminal_key_result_id: str


@dataclass(frozen=True)
class ProjectLifecycleFixture:
    """Stable references for one seeded project lifecycle graph."""

    active_project_id: str
    active_task_id: str
    terminal_project_id: str
    terminal_task_id: str


async def seed_goal_lifecycle_fixture(
    project_service: ProjectService,
    goal_service: GoalService,
    task_service: TaskService,
    *,
    active_project_name: str,
    active_goal_name: str,
    active_task_title: str,
    active_goal_progress_percent: int = 10,
    start_active_task: bool = True,
    active_progress_percent: int | None = 45,
    active_status_message: str = "Implementing",
    active_updated_by: str = "lifecycle-audit",
    terminal_project_name: str,
    terminal_goal_name: str,
    terminal_task_title: str,
) -> GoalLifecycleFixture:
    """Seed one active and one terminal goal graph through shared services."""
    active_project = await project_service.create_project(name=active_project_name)
    active_goal = await goal_service.create_goal(
        name=active_goal_name,
        project_id=active_project.id,
        progress_percent=active_goal_progress_percent,
    )
    active_task = await task_service.create_task(
        active_project.id,
        active_task_title,
    )
    if start_active_task:
        await task_service.start_task(active_task.id)
    if active_progress_percent is not None:
        await task_service.update_task_progress(
            active_task.id,
            active_progress_percent,
            active_status_message,
            active_updated_by,
        )

    terminal_project = await project_service.create_project(name=terminal_project_name)
    terminal_goal = await goal_service.create_goal(
        name=terminal_goal_name,
        project_id=terminal_project.id,
    )
    terminal_task = await task_service.create_task(
        terminal_project.id,
        terminal_task_title,
    )
    await task_service.start_task(terminal_task.id)
    await task_service.complete_task(terminal_task.id)

    return GoalLifecycleFixture(
        active_project_id=active_project.id,
        active_goal_id=active_goal.id,
        active_task_id=active_task.id,
        terminal_project_id=terminal_project.id,
        terminal_goal_id=terminal_goal.id,
        terminal_task_id=terminal_task.id,
    )


async def build_goal_lifecycle_expectations(
    goal_service: GoalService,
    goal_ids: Sequence[str],
) -> tuple[dict[str, GoalLifecycleExpectation], dict[str, str | None]]:
    """Build shared goal lifecycle expectations for seeded audit graphs."""
    goal_id_list = list(goal_ids)
    activity_map = await goal_service.get_last_activity_map(goal_id_list)
    transition_map = await goal_service.get_last_transition_map(goal_id_list)

    expectations: dict[str, GoalLifecycleExpectation] = {}
    project_ids: dict[str, str | None] = {}
    for goal_id in goal_id_list:
        summary = await goal_service.get_goal_summary(goal_id)
        if summary is None:
            raise RuntimeError(f"failed to compute goal summary for {goal_id}")
        expectations[goal_id] = goal_expectation_from_summary(
            summary,
            last_activity_at=activity_map.get(goal_id),
            last_transition_at=transition_map.get(goal_id),
        )
        project_ids[goal_id] = summary.goal.project_id

    return expectations, project_ids


async def seed_objective_lifecycle_fixture(
    project_service: ProjectService,
    goal_service: GoalService,
    *,
    active_project_name: str,
    active_goal_name: str,
    active_objective_name: str,
    active_objective_progress_percent: int = 10,
    active_key_result_a_name: str,
    active_key_result_b_name: str,
    active_key_result_a_progress_percent: int = 20,
    active_key_result_b_progress_percent: int = 70,
    active_transition_status: GoalStatus = GoalStatus.ON_HOLD,
    active_transition_message: str = (
        "Put one key result on hold to force transition bubbling"
    ),
    terminal_project_name: str,
    terminal_goal_name: str,
    terminal_objective_name: str,
    terminal_key_result_name: str,
    terminal_key_result_progress_percent: int = 100,
) -> ObjectiveLifecycleFixture:
    """Seed one active and one terminal objective graph through shared services."""
    active_project = await project_service.create_project(name=active_project_name)
    active_goal = await goal_service.create_goal(
        name=active_goal_name,
        project_id=active_project.id,
    )
    active_objective = await goal_service.create_objective(
        goal_id=active_goal.id,
        name=active_objective_name,
        progress_percent=active_objective_progress_percent,
    )
    active_key_result_a = await goal_service.create_key_result(
        objective_id=active_objective.id,
        name=active_key_result_a_name,
        progress_percent=active_key_result_a_progress_percent,
    )
    active_key_result_b = await goal_service.create_key_result(
        objective_id=active_objective.id,
        name=active_key_result_b_name,
        progress_percent=active_key_result_b_progress_percent,
    )
    await goal_service.update_key_result(
        active_key_result_a.id,
        status=active_transition_status,
        progress_percent=active_key_result_a_progress_percent,
        message=active_transition_message,
    )

    terminal_project = await project_service.create_project(name=terminal_project_name)
    terminal_goal = await goal_service.create_goal(
        name=terminal_goal_name,
        project_id=terminal_project.id,
    )
    terminal_objective = await goal_service.create_objective(
        goal_id=terminal_goal.id,
        name=terminal_objective_name,
    )
    terminal_key_result = await goal_service.create_key_result(
        objective_id=terminal_objective.id,
        name=terminal_key_result_name,
        progress_percent=terminal_key_result_progress_percent,
    )
    await goal_service.complete_key_result(terminal_key_result.id)

    return ObjectiveLifecycleFixture(
        active_project_id=active_project.id,
        active_goal_id=active_goal.id,
        active_objective_id=active_objective.id,
        active_key_result_ids=(active_key_result_a.id, active_key_result_b.id),
        terminal_project_id=terminal_project.id,
        terminal_goal_id=terminal_goal.id,
        terminal_objective_id=terminal_objective.id,
        terminal_key_result_id=terminal_key_result.id,
    )


async def build_objective_lifecycle_expectations(
    goal_service: GoalService,
    objective_ids: Sequence[str],
) -> dict[str, ObjectiveLifecycleExpectation]:
    """Build shared objective lifecycle expectations for seeded audit graphs."""
    objective_id_list = list(objective_ids)
    activity_map = await goal_service.get_objective_last_activity_map(objective_id_list)
    transition_map = await goal_service.get_objective_last_transition_map(
        objective_id_list
    )

    expectations: dict[str, ObjectiveLifecycleExpectation] = {}
    for objective_id in objective_id_list:
        summary = await goal_service.get_objective_summary(objective_id)
        if summary is None:
            raise RuntimeError(
                f"failed to compute objective summary for {objective_id}"
            )
        goal = await goal_service.get_goal(summary.objective.goal_id)
        expectations[objective_id] = objective_expectation_from_summary(
            summary,
            project_id=goal.project_id if goal is not None else None,
            last_activity_at=activity_map.get(objective_id),
            last_transition_at=transition_map.get(objective_id),
        )

    return expectations


async def seed_key_result_lifecycle_fixture(
    project_service: ProjectService,
    goal_service: GoalService,
    *,
    active_project_name: str,
    active_goal_name: str,
    active_objective_name: str,
    active_key_result_name: str,
    active_key_result_progress_percent: int = 35,
    active_transition_status: GoalStatus = GoalStatus.ON_HOLD,
    active_transition_message: str = "Pause active key result to force transition bubbling",
    active_resume_message: str = "Resume active key result after hold transition",
    terminal_project_name: str,
    terminal_goal_name: str,
    terminal_objective_name: str,
    terminal_key_result_name: str,
    terminal_key_result_progress_percent: int = 100,
) -> KeyResultLifecycleFixture:
    """Seed one active and one terminal key-result graph through shared services."""
    active_project = await project_service.create_project(name=active_project_name)
    active_goal = await goal_service.create_goal(
        name=active_goal_name,
        project_id=active_project.id,
    )
    active_objective = await goal_service.create_objective(
        goal_id=active_goal.id,
        name=active_objective_name,
    )
    active_key_result = await goal_service.create_key_result(
        objective_id=active_objective.id,
        name=active_key_result_name,
        progress_percent=active_key_result_progress_percent,
    )
    await goal_service.update_key_result(
        active_key_result.id,
        status=active_transition_status,
        progress_percent=active_key_result_progress_percent,
        message=active_transition_message,
    )
    await goal_service.update_key_result(
        active_key_result.id,
        status=GoalStatus.ACTIVE,
        progress_percent=active_key_result_progress_percent,
        message=active_resume_message,
    )

    terminal_project = await project_service.create_project(name=terminal_project_name)
    terminal_goal = await goal_service.create_goal(
        name=terminal_goal_name,
        project_id=terminal_project.id,
    )
    terminal_objective = await goal_service.create_objective(
        goal_id=terminal_goal.id,
        name=terminal_objective_name,
    )
    terminal_key_result = await goal_service.create_key_result(
        objective_id=terminal_objective.id,
        name=terminal_key_result_name,
        progress_percent=terminal_key_result_progress_percent,
    )
    await goal_service.complete_key_result(terminal_key_result.id)

    return KeyResultLifecycleFixture(
        active_project_id=active_project.id,
        active_goal_id=active_goal.id,
        active_objective_id=active_objective.id,
        active_key_result_id=active_key_result.id,
        terminal_project_id=terminal_project.id,
        terminal_goal_id=terminal_goal.id,
        terminal_objective_id=terminal_objective.id,
        terminal_key_result_id=terminal_key_result.id,
    )


async def build_key_result_lifecycle_expectations(
    goal_service: GoalService,
    key_result_ids: Sequence[str],
) -> dict[str, KeyResultLifecycleExpectation]:
    """Build shared key-result lifecycle expectations for seeded audit graphs."""
    key_result_id_list = list(key_result_ids)
    activity_map = await goal_service.get_key_result_last_activity_map(
        key_result_id_list
    )
    transition_map = await goal_service.get_key_result_last_transition_map(
        key_result_id_list
    )

    expectations: dict[str, KeyResultLifecycleExpectation] = {}
    for key_result_id in key_result_id_list:
        key_result = await goal_service.get_key_result(key_result_id)
        if key_result is None:
            raise RuntimeError(f"failed to load key result {key_result_id}")
        objective = await goal_service.get_objective(key_result.objective_id)
        goal_id = objective.goal_id if objective is not None else ""
        goal = await goal_service.get_goal(goal_id) if goal_id else None
        expectations[key_result_id] = expectation_from_key_result(
            key_result,
            goal_id=goal_id,
            project_id=goal.project_id if goal is not None else None,
            last_activity_at=activity_map.get(key_result_id),
            last_transition_at=transition_map.get(key_result_id),
        )

    return expectations


async def seed_project_lifecycle_fixture(
    project_service: ProjectService,
    task_service: TaskService,
    plan_service: PlanService,
    *,
    active_project_name: str,
    active_task_title: str,
    start_active_task: bool = True,
    active_progress_percent: int | None = None,
    active_status_message: str = "Active execution progress",
    active_updated_by: str = "lifecycle-audit",
    terminal_project_name: str,
    terminal_task_title: str,
    terminal_plan_name: str,
    terminal_plan_content: dict[str, object] | None = None,
    comment_service: CommentService | None = None,
    terminal_comment_body: str | None = None,
    terminal_comment_author: str = "lifecycle-audit",
) -> ProjectLifecycleFixture:
    """Seed one active and one terminal project graph through shared services."""
    active_project = await project_service.create_project(name=active_project_name)
    active_task = await task_service.create_task(
        active_project.id,
        active_task_title,
    )
    if start_active_task:
        await task_service.start_task(active_task.id)
    if active_progress_percent is not None:
        await task_service.update_task_progress(
            active_task.id,
            active_progress_percent,
            active_status_message,
            active_updated_by,
        )

    terminal_project = await project_service.create_project(name=terminal_project_name)
    terminal_task = await task_service.create_task(
        terminal_project.id,
        terminal_task_title,
    )
    await task_service.start_task(terminal_task.id)
    await task_service.complete_task(terminal_task.id)
    await plan_service.create_plan(
        name=terminal_plan_name,
        description=None,
        status=PlanStatus.DRAFT,
        format=PlanFormat.JSON,
        content=terminal_plan_content or {"steps": ["planning residue"]},
        project_id=terminal_project.id,
    )
    await project_service.update_project(
        terminal_project.id,
        status=ProjectStatus.COMPLETED,
    )
    if terminal_comment_body is not None and comment_service is not None:
        await comment_service.add_comment(
            "task",
            terminal_task.id,
            terminal_comment_body,
            terminal_comment_author,
        )

    return ProjectLifecycleFixture(
        active_project_id=active_project.id,
        active_task_id=active_task.id,
        terminal_project_id=terminal_project.id,
        terminal_task_id=terminal_task.id,
    )
