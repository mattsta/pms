#!/usr/bin/env python3
"""Reconcile live plan and project lifecycle state against linked execution."""

from __future__ import annotations

import argparse
import asyncio
import json

from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.db.connection import get_database
from pms.models import GoalStatus, PlanStatus, ProjectStatus, TaskStatus
from pms.repositories.goal_repository import GoalRepository
from pms.repositories.plan_repository import PlanRepository
from pms.repositories.project_repository import ProjectRepository
from pms.repositories.task_repository import TaskRepository
from pms.services.generated_artifacts import is_quickstart_generated_plan


async def _run(apply_changes: bool) -> dict[str, object]:
    db = get_database()
    await db.connect()
    try:
        event_store = EventStore(db)
        revision_store = RevisionStore(db)
        metrics = MetricsCollector(db)
        plan_repo = PlanRepository(db, event_store, revision_store, metrics)
        project_repo = ProjectRepository(db, event_store, revision_store, metrics)
        goal_repo = GoalRepository(db, event_store, revision_store, metrics)
        task_repo = TaskRepository(db, event_store, revision_store, metrics)

        updated_plan_ids: list[str] = []
        updated_project_ids: list[str] = []
        plans = (await plan_repo.list_plans(limit=1000)).items

        quickstart_by_project: dict[str, list] = {}
        for plan in plans:
            if not is_quickstart_generated_plan(
                plan, plan_name="Quickstart Project Plan"
            ):
                continue
            if plan.status == PlanStatus.ARCHIVED:
                continue
            project_key = plan.project_id or "__none__"
            quickstart_by_project.setdefault(project_key, []).append(plan)

        for duplicate_group in quickstart_by_project.values():
            if len(duplicate_group) <= 1:
                continue
            duplicate_group.sort(
                key=lambda plan: str(plan.updated_at),
                reverse=True,
            )
            for duplicate in duplicate_group[1:]:
                if apply_changes:
                    updated = await plan_repo.update(
                        plan_id=duplicate.id,
                        status=PlanStatus.ARCHIVED,
                        message="Archived duplicate quickstart plan during reconciliation",
                    )
                    if updated is not None:
                        updated_plan_ids.append(updated.id)

        for plan in plans:
            if plan.status == PlanStatus.ARCHIVED:
                continue

            linked_tasks = await task_repo.get_by_ids(list(plan.task_ids))
            has_linked_tasks = bool(plan.task_ids)
            any_started = any(
                task.status != TaskStatus.TODO or task.current_progress_percent > 0
                for task in linked_tasks
            )
            all_terminal = has_linked_tasks and all(
                task.status.is_terminal for task in linked_tasks
            )

            goal_completed = True
            if plan.goal_id is not None:
                goal = await goal_repo.get_by_id(plan.goal_id)
                goal_completed = (
                    goal is not None and goal.status == GoalStatus.COMPLETED
                )

            target_plan_status = plan.status
            if all_terminal and goal_completed:
                target_plan_status = PlanStatus.COMPLETED
            elif has_linked_tasks and (
                any_started or plan.status == PlanStatus.COMPLETED
            ):
                target_plan_status = PlanStatus.ACTIVE

            if apply_changes and target_plan_status != plan.status:
                updated = await plan_repo.update(
                    plan_id=plan.id,
                    status=target_plan_status,
                    message="Reconciled plan lifecycle from linked execution state",
                )
                if updated is not None:
                    updated_plan_ids.append(updated.id)

            project_id = plan.project_id
            if project_id is None:
                continue

            project = await project_repo.get_by_id(project_id)
            if project is None or project.status == ProjectStatus.ARCHIVED:
                continue

            task_rollup = await db.fetch_one(
                """
                SELECT
                    COUNT(*) AS total_tasks,
                    SUM(
                        CASE WHEN status IN ('done', 'cancelled') THEN 1 ELSE 0 END
                    ) AS terminal_tasks
                FROM tasks
                WHERE project_id = ?
                """,
                (project_id,),
            )
            goal_rollup = await db.fetch_one(
                """
                SELECT
                    COUNT(*) AS total_goals,
                    SUM(
                        CASE WHEN status = 'completed' THEN 1 ELSE 0 END
                    ) AS completed_goals
                FROM goals
                WHERE project_id = ?
                  AND status != 'archived'
                """,
                (project_id,),
            )

            total_tasks = int(task_rollup["total_tasks"] or 0) if task_rollup else 0
            terminal_tasks = (
                int(task_rollup["terminal_tasks"] or 0) if task_rollup else 0
            )
            total_goals = int(goal_rollup["total_goals"] or 0) if goal_rollup else 0
            completed_goals = (
                int(goal_rollup["completed_goals"] or 0) if goal_rollup else 0
            )

            all_tasks_terminal = total_tasks > 0 and terminal_tasks == total_tasks
            all_goals_completed = total_goals == 0 or completed_goals == total_goals

            if apply_changes and all_tasks_terminal and all_goals_completed:
                if project.status != ProjectStatus.COMPLETED:
                    updated = await project_repo.complete(
                        project_id,
                        message="Reconciled project lifecycle from linked execution state",
                    )
                    if updated is not None:
                        updated_project_ids.append(updated.id)
            elif apply_changes and project.status == ProjectStatus.COMPLETED:
                updated = await project_repo.reactivate(
                    project_id,
                    message="Reopened project because linked execution is no longer terminal",
                )
                if updated is not None:
                    updated_project_ids.append(updated.id)

        return {
            "apply_changes": apply_changes,
            "updated_plan_ids": sorted(set(updated_plan_ids)),
            "updated_project_ids": sorted(set(updated_project_ids)),
        }
    finally:
        await db.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    result = asyncio.run(_run(args.apply))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
