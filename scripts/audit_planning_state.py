#!/usr/bin/env python3
"""Audit PMS planning-state lifecycle and machine-readable contract correctness."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime

from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.db.connection import Database, get_database
from pms.models import GoalStatus, PlanStatus, ProjectStatus, TaskStatus
from pms.repositories.goal_repository import GoalRepository
from pms.repositories.plan_repository import PlanRepository
from pms.repositories.project_repository import ProjectRepository
from pms.repositories.task_repository import TaskRepository
from pms.services.generated_artifacts import (
    is_audit_generated_project,
    is_quickstart_generated_plan,
)


@dataclass
class AuditIssue:
    code: str
    message: str
    entity_type: str
    entity_id: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "code": self.code,
            "message": self.message,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
        }


async def _build_repositories(
    db: Database,
) -> tuple[PlanRepository, ProjectRepository, GoalRepository, TaskRepository]:
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)
    return (
        PlanRepository(db, event_store, revision_store, metrics),
        ProjectRepository(db, event_store, revision_store, metrics),
        GoalRepository(db, event_store, revision_store, metrics),
        TaskRepository(db, event_store, revision_store, metrics),
    )


def _run_cli_json_command(args: list[str]) -> AuditIssue | None:
    process = subprocess.run(
        args,
        capture_output=True,
        text=True,
        check=False,
    )
    if process.returncode != 0:
        return AuditIssue(
            code="cli_command_failed",
            message=process.stderr.strip()
            or process.stdout.strip()
            or "command failed",
            entity_type="cli",
        )
    try:
        json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        return AuditIssue(
            code="invalid_json",
            message=f"{' '.join(args)} emitted invalid JSON: {exc}",
            entity_type="cli",
        )
    return None


def _sort_timestamp(value: datetime | str | None) -> float:
    if isinstance(value, datetime):
        return value.timestamp()
    if isinstance(value, str):
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(normalized).timestamp()
        except ValueError:
            return 0.0
    return 0.0


async def run_audit_async() -> tuple[AuditIssue, ...]:
    db = get_database()
    await db.connect()
    plan_repo, project_repo, goal_repo, task_repo = await _build_repositories(db)

    issues: list[AuditIssue] = []

    project_list_process = subprocess.run(
        ["uv", "run", "pms", "project", "list", "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    project_json_issue = None
    project_list_payload: dict[str, object] | None = None
    if project_list_process.returncode != 0:
        project_json_issue = AuditIssue(
            code="cli_command_failed",
            message=(
                project_list_process.stderr.strip()
                or project_list_process.stdout.strip()
                or "command failed"
            ),
            entity_type="cli",
        )
    else:
        try:
            parsed_project_payload = json.loads(project_list_process.stdout)
        except json.JSONDecodeError as exc:
            project_json_issue = AuditIssue(
                code="invalid_json",
                message=(
                    f"uv run pms project list --format json emitted invalid JSON: {exc}"
                ),
                entity_type="cli",
            )
        else:
            if isinstance(parsed_project_payload, dict):
                project_list_payload = parsed_project_payload
            else:
                project_json_issue = AuditIssue(
                    code="invalid_json_shape",
                    message="uv run pms project list --format json did not emit an object",
                    entity_type="cli",
                )
    if project_json_issue is not None:
        issues.append(project_json_issue)

    plan_list_payload_issue = _run_cli_json_command(
        ["uv", "run", "pms", "plan", "list", "--format", "json"]
    )
    if plan_list_payload_issue is not None:
        issues.append(plan_list_payload_issue)

    plans = (await plan_repo.list_plans(limit=1000)).items
    projects = (await project_repo.get_all(limit=1000)).items
    tasks = (await task_repo.get_all(limit=5000)).items

    for task in tasks:
        progress = int(task.current_progress_percent or 0)
        if progress > 0 and task.status not in (
            TaskStatus.IN_PROGRESS,
            TaskStatus.DONE,
        ):
            issues.append(
                AuditIssue(
                    code="nonzero_progress_nonactive_task",
                    message=(
                        "task has non-zero progress while lifecycle is not active "
                        "or terminal"
                    ),
                    entity_type="task",
                    entity_id=task.id,
                )
            )

        if task.status == TaskStatus.DONE and progress != 100:
            issues.append(
                AuditIssue(
                    code="done_task_progress_not_complete",
                    message="task is done but current_progress_percent is not 100",
                    entity_type="task",
                    entity_id=task.id,
                )
            )

    for plan in plans:
        linked_tasks = await task_repo.get_by_ids(list(plan.task_ids))
        has_tasks = bool(plan.task_ids)
        all_terminal = has_tasks and all(
            task.status in (TaskStatus.DONE, TaskStatus.CANCELLED)
            for task in linked_tasks
        )
        any_started = any(
            task.current_progress_percent > 0
            or task.status
            not in (
                TaskStatus.TODO,
                TaskStatus.BLOCKED,
            )
            for task in linked_tasks
        )
        goal_completed = True
        if plan.goal_id is not None:
            goal = await goal_repo.get_by_id(plan.goal_id)
            goal_completed = goal is not None and goal.status == GoalStatus.COMPLETED

        if plan.status == PlanStatus.ACTIVE and all_terminal and goal_completed:
            issues.append(
                AuditIssue(
                    code="stale_active_plan",
                    message="plan is active even though linked execution is terminal",
                    entity_type="plan",
                    entity_id=plan.id,
                )
            )

        if plan.status == PlanStatus.DRAFT and any_started:
            issues.append(
                AuditIssue(
                    code="draft_plan_has_execution_progress",
                    message="draft plan has linked task execution progress",
                    entity_type="plan",
                    entity_id=plan.id,
                )
            )

        if (
            plan.goal_id is not None
            and not plan.task_ids
            and plan.status != PlanStatus.ARCHIVED
        ):
            issues.append(
                AuditIssue(
                    code="plan_without_task_links",
                    message="plan is linked to a goal but has no task_ids",
                    entity_type="plan",
                    entity_id=plan.id,
                )
            )

    ranked_plans = sorted(
        plans,
        key=lambda plan: (
            0
            if plan.status == PlanStatus.ACTIVE
            else 1
            if plan.status == PlanStatus.DRAFT
            else 2
            if plan.status == PlanStatus.COMPLETED
            else 3,
            -_sort_timestamp(plan.updated_at),
        ),
    )
    if ranked_plans:
        highest_ranked = ranked_plans[0]
        if highest_ranked.status == PlanStatus.ARCHIVED and any(
            plan.status != PlanStatus.ARCHIVED for plan in ranked_plans
        ):
            issues.append(
                AuditIssue(
                    code="archived_plan_ranked_ahead_of_live_plan",
                    message=(
                        "default plan list ordering would surface an archived plan "
                        "ahead of live plans in human control surfaces"
                    ),
                    entity_type="plan",
                    entity_id=highest_ranked.id,
                )
            )

    for project in projects:
        task_rollup = await db.fetch_one(
            """
            SELECT
                COUNT(*) AS total_tasks,
                SUM(CASE WHEN status IN ('done', 'cancelled') THEN 1 ELSE 0 END) AS terminal_tasks
            FROM tasks
            WHERE project_id = ?
            """,
            (project.id,),
        )
        goal_rollup = await db.fetch_one(
            """
            SELECT
                COUNT(*) AS total_goals,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed_goals
            FROM goals
            WHERE project_id = ?
              AND status != 'archived'
            """,
            (project.id,),
        )

        total_tasks = int(task_rollup["total_tasks"] or 0) if task_rollup else 0
        terminal_tasks = int(task_rollup["terminal_tasks"] or 0) if task_rollup else 0
        total_goals = int(goal_rollup["total_goals"] or 0) if goal_rollup else 0
        completed_goals = int(goal_rollup["completed_goals"] or 0) if goal_rollup else 0

        all_tasks_terminal = total_tasks > 0 and total_tasks == terminal_tasks
        all_goals_completed = total_goals == 0 or total_goals == completed_goals

        if (
            project.status == ProjectStatus.ACTIVE
            and all_tasks_terminal
            and all_goals_completed
        ):
            issues.append(
                AuditIssue(
                    code="stale_active_project",
                    message="project is active even though linked execution is terminal",
                    entity_type="project",
                    entity_id=project.id,
                )
            )

        if project.status == ProjectStatus.COMPLETED and not (
            all_tasks_terminal and all_goals_completed
        ):
            issues.append(
                AuditIssue(
                    code="stale_completed_project",
                    message="project is completed even though linked execution has reopened",
                    entity_type="project",
                    entity_id=project.id,
                )
            )

    if project_list_payload is not None:
        payload_items = project_list_payload.get("items")
        if isinstance(payload_items, list):
            visible_generated_projects = []
            for item in payload_items:
                if not isinstance(item, dict):
                    continue
                project_id = item.get("id")
                if not isinstance(project_id, str):
                    continue
                project = await project_repo.get_by_id(project_id)
                if project is not None and is_audit_generated_project(project):
                    visible_generated_projects.append(project.id)
            if visible_generated_projects:
                issues.append(
                    AuditIssue(
                        code="visible_audit_generated_projects",
                        message=(
                            "default project list is surfacing audit-generated "
                            "ephemeral projects in operator views"
                        ),
                        entity_type="project_collection",
                        entity_id=visible_generated_projects[0],
                    )
                )

    quickstart_by_project: dict[str, list[str]] = {}
    for plan in plans:
        if not is_quickstart_generated_plan(plan, plan_name="Quickstart Project Plan"):
            continue
        if plan.status == PlanStatus.ARCHIVED:
            continue
        project_key = plan.project_id or "__none__"
        quickstart_by_project.setdefault(project_key, []).append(plan.id)

    for project_id, plan_ids in quickstart_by_project.items():
        if len(plan_ids) > 1:
            issues.append(
                AuditIssue(
                    code="duplicate_live_quickstart_plans",
                    message=(
                        f"found {len(plan_ids)} non-archived quickstart plans for "
                        f"project {project_id}; live planning view is cluttered"
                    ),
                    entity_type="plan_collection",
                    entity_id=project_id,
                )
            )

    await db.disconnect()
    return tuple(issues)


def run_audit() -> tuple[AuditIssue, ...]:
    """Run the planning-state audit and return any issues."""
    return asyncio.run(run_audit_async())


async def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    issues = list(await run_audit_async())
    payload = {
        "checked": {
            "plans": True,
            "projects": True,
            "tasks": True,
            "project_list_json": True,
            "plan_list_json": True,
            "plan_list_ordering": True,
        },
        "issue_count": len(issues),
        "issues": [issue.to_dict() for issue in issues],
    }
    print(json.dumps(payload, indent=2))

    if args.check and issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
