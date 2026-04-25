#!/usr/bin/env python3
"""Classify and normalize fixture/test backlog residue in the current PMS instance."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path
from typing import Any

from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.db.connection import Database
from pms.db.schema import initialize_schema
from pms.models import PlanStatus, ProjectStatus, TaskStatus
from pms.repositories.base import RepositoryContext
from pms.repositories.goal_repository import GoalRepository
from pms.repositories.key_result_repository import KeyResultRepository
from pms.repositories.objective_repository import ObjectiveRepository
from pms.repositories.plan_repository import PlanRepository
from pms.repositories.project_repository import ProjectRepository
from pms.repositories.task_repository import TaskRepository

REPO_ROOT = Path(__file__).resolve().parents[1]

KNOWN_FIXTURE_PROJECTS: dict[str, str] = {
    "Audit Active Project": "audit_fixture",
    "Goal Filter Project A": "filter_fixture",
    "Goal Filter Project B": "filter_fixture",
    "Objective Filter Project": "filter_fixture",
    "Key Result Filter Project": "filter_fixture",
    "Recent Progress Project": "recent_progress_fixture",
    "Output Fix Validation Project": "validation_fixture",
    "Quickstart Project": "quickstart_fixture",
}

FIXTURE_PROJECT_PREFIXES: tuple[tuple[str, str], ...] = (
    ("Audit Project ", "audit_fixture"),
    ("Runtime Repro Project", "runtime_repro_fixture"),
)


def classify_fixture_project(name: str) -> str | None:
    """Return the cleanup category for a known fixture project."""
    if name in KNOWN_FIXTURE_PROJECTS:
        return KNOWN_FIXTURE_PROJECTS[name]
    for prefix, category in FIXTURE_PROJECT_PREFIXES:
        if name.startswith(prefix):
            return category
    return None


async def _open_database(database_path: Path | None) -> Database:
    db = Database(database_path) if database_path is not None else Database()
    await db.connect()
    await initialize_schema(db)
    return db


async def _count_open_tasks(db: Database) -> int:
    row = await db.fetch_one(
        """
        SELECT COUNT(*) AS count
        FROM tasks
        WHERE status IN ('todo', 'in_progress', 'blocked', 'in_review')
        """
    )
    return int(row["count"] or 0) if row else 0


async def _count_active_goals(db: Database) -> int:
    row = await db.fetch_one(
        "SELECT COUNT(*) AS count FROM goals WHERE status = 'active'"
    )
    return int(row["count"] or 0) if row else 0


async def _count_active_objectives(db: Database) -> int:
    row = await db.fetch_one(
        "SELECT COUNT(*) AS count FROM objectives WHERE status = 'active'"
    )
    return int(row["count"] or 0) if row else 0


async def _count_active_key_results(db: Database) -> int:
    row = await db.fetch_one(
        "SELECT COUNT(*) AS count FROM key_results WHERE status = 'active'"
    )
    return int(row["count"] or 0) if row else 0


async def _count_active_projects(db: Database) -> int:
    row = await db.fetch_one(
        "SELECT COUNT(*) AS count FROM projects WHERE status = 'active'"
    )
    return int(row["count"] or 0) if row else 0


async def _count_nonterminal_plans(db: Database) -> int:
    row = await db.fetch_one(
        "SELECT COUNT(*) AS count FROM plans WHERE status IN ('draft', 'active')"
    )
    return int(row["count"] or 0) if row else 0


async def _collect_fixture_project_rows(db: Database) -> list[dict[str, Any]]:
    rows = await db.fetch_all(
        """
        SELECT id, name, status, updated_at
        FROM projects
        WHERE status = 'active'
        ORDER BY updated_at DESC, name ASC
        """
    )
    return [
        row for row in rows if classify_fixture_project(str(row["name"])) is not None
    ]


async def _collect_fixture_project_counts(db: Database) -> dict[str, dict[str, int]]:
    goal_rows = await db.fetch_all(
        """
        SELECT project_id, COUNT(*) AS count
        FROM goals
        WHERE status = 'active' AND project_id IS NOT NULL
        GROUP BY project_id
        """
    )
    objective_rows = await db.fetch_all(
        """
        SELECT g.project_id AS project_id, COUNT(*) AS count
        FROM objectives o
        JOIN goals g ON g.id = o.goal_id
        WHERE o.status = 'active' AND g.project_id IS NOT NULL
        GROUP BY g.project_id
        """
    )
    key_result_rows = await db.fetch_all(
        """
        SELECT g.project_id AS project_id, COUNT(*) AS count
        FROM key_results kr
        JOIN objectives o ON o.id = kr.objective_id
        JOIN goals g ON g.id = o.goal_id
        WHERE kr.status = 'active' AND g.project_id IS NOT NULL
        GROUP BY g.project_id
        """
    )
    task_rows = await db.fetch_all(
        """
        SELECT project_id, COUNT(*) AS count
        FROM tasks
        WHERE status IN ('todo', 'in_progress', 'blocked', 'in_review')
        GROUP BY project_id
        """
    )
    plan_rows = await db.fetch_all(
        """
        SELECT project_id, COUNT(*) AS count
        FROM plans
        WHERE status IN ('draft', 'active') AND project_id IS NOT NULL
        GROUP BY project_id
        """
    )
    counts = {
        "goals": {row["project_id"]: int(row["count"] or 0) for row in goal_rows},
        "objectives": {
            row["project_id"]: int(row["count"] or 0) for row in objective_rows
        },
        "key_results": {
            row["project_id"]: int(row["count"] or 0) for row in key_result_rows
        },
        "tasks": {row["project_id"]: int(row["count"] or 0) for row in task_rows},
        "plans": {row["project_id"]: int(row["count"] or 0) for row in plan_rows},
    }
    return counts


async def _collect_orphans(db: Database) -> dict[str, list[dict[str, Any]]]:
    return {
        "tasks": await db.fetch_all(
            """
            SELECT t.id, t.title, t.status, p.id AS project_id, p.name AS project_name, p.status AS project_status
            FROM tasks t
            LEFT JOIN projects p ON p.id = t.project_id
            WHERE t.status IN ('todo', 'in_progress', 'blocked', 'in_review')
              AND COALESCE(p.status, '') != 'active'
            ORDER BY p.updated_at DESC, t.updated_at DESC
            """
        ),
        "goals": await db.fetch_all(
            """
            SELECT g.id, g.name, g.status, p.id AS project_id, p.name AS project_name, p.status AS project_status
            FROM goals g
            LEFT JOIN projects p ON p.id = g.project_id
            WHERE g.status = 'active'
              AND COALESCE(p.status, '') != 'active'
            ORDER BY p.updated_at DESC, g.updated_at DESC
            """
        ),
        "objectives": await db.fetch_all(
            """
            SELECT o.id, o.name, o.status, g.id AS goal_id, g.name AS goal_name,
                   p.id AS project_id, p.name AS project_name, p.status AS project_status
            FROM objectives o
            LEFT JOIN goals g ON g.id = o.goal_id
            LEFT JOIN projects p ON p.id = g.project_id
            WHERE o.status = 'active'
              AND COALESCE(p.status, '') != 'active'
            ORDER BY p.updated_at DESC, o.updated_at DESC
            """
        ),
        "key_results": await db.fetch_all(
            """
            SELECT kr.id, kr.name, kr.status, o.id AS objective_id, o.name AS objective_name,
                   g.id AS goal_id, g.name AS goal_name,
                   p.id AS project_id, p.name AS project_name, p.status AS project_status
            FROM key_results kr
            LEFT JOIN objectives o ON o.id = kr.objective_id
            LEFT JOIN goals g ON g.id = o.goal_id
            LEFT JOIN projects p ON p.id = g.project_id
            WHERE kr.status = 'active'
              AND COALESCE(p.status, '') != 'active'
            ORDER BY p.updated_at DESC, kr.updated_at DESC
            """
        ),
        "plans": await db.fetch_all(
            """
            SELECT pl.id, pl.name, pl.status, p.id AS project_id, p.name AS project_name, p.status AS project_status
            FROM plans pl
            LEFT JOIN projects p ON p.id = pl.project_id
            WHERE pl.status IN ('draft', 'active')
              AND COALESCE(p.status, '') != 'active'
            ORDER BY p.updated_at DESC, pl.updated_at DESC
            """
        ),
    }


async def _build_report(db: Database) -> dict[str, Any]:
    fixture_projects = await _collect_fixture_project_rows(db)
    counts = await _collect_fixture_project_counts(db)
    orphans = await _collect_orphans(db)

    category_counter = Counter(
        classify_fixture_project(str(project["name"])) for project in fixture_projects
    )
    categorized_projects = []
    for project in fixture_projects:
        project_id = str(project["id"])
        categorized_projects.append(
            {
                "project_id": project_id,
                "project_name": project["name"],
                "category": classify_fixture_project(str(project["name"])),
                "active_goals": counts["goals"].get(project_id, 0),
                "active_objectives": counts["objectives"].get(project_id, 0),
                "active_key_results": counts["key_results"].get(project_id, 0),
                "open_tasks": counts["tasks"].get(project_id, 0),
                "nonterminal_plans": counts["plans"].get(project_id, 0),
                "updated_at": project.get("updated_at"),
            }
        )

    active_project_names = {
        str(project["name"])
        for project in await db.fetch_all(
            """
            SELECT name
            FROM projects
            WHERE status = 'active'
            """
        )
    }
    unknown_active_projects = sorted(
        name for name in active_project_names if classify_fixture_project(name) is None
    )

    summary = {
        "active_projects": await _count_active_projects(db),
        "active_goals": await _count_active_goals(db),
        "active_objectives": await _count_active_objectives(db),
        "active_key_results": await _count_active_key_results(db),
        "open_tasks": await _count_open_tasks(db),
        "nonterminal_plans": await _count_nonterminal_plans(db),
        "fixture_project_count": len(categorized_projects),
        "fixture_project_categories": dict(category_counter),
        "unknown_active_project_count": len(unknown_active_projects),
        "orphan_open_task_count": len(orphans["tasks"]),
        "orphan_active_goal_count": len(orphans["goals"]),
        "orphan_active_objective_count": len(orphans["objectives"]),
        "orphan_active_key_result_count": len(orphans["key_results"]),
        "orphan_nonterminal_plan_count": len(orphans["plans"]),
        "recommended_action": (
            "apply_cleanup"
            if not unknown_active_projects
            else "review_unknown_projects"
        ),
    }

    return {
        "summary": summary,
        "fixture_projects": categorized_projects,
        "unknown_active_projects": unknown_active_projects,
        "orphan_integrity_issues": orphans,
    }


async def _apply_cleanup(db: Database, report: dict[str, Any]) -> dict[str, Any]:
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)
    context = RepositoryContext(user_id="fixture-backlog-cleanup")

    project_repo = ProjectRepository(
        db, event_store, revision_store, metrics
    ).with_context(context)
    goal_repo = GoalRepository(db, event_store, revision_store, metrics).with_context(
        context
    )
    objective_repo = ObjectiveRepository(
        db, event_store, revision_store, metrics
    ).with_context(context)
    key_result_repo = KeyResultRepository(
        db, event_store, revision_store, metrics
    ).with_context(context)
    plan_repo = PlanRepository(db, event_store, revision_store, metrics).with_context(
        context
    )
    task_repo = TaskRepository(db, event_store, revision_store, metrics).with_context(
        context
    )

    actions = Counter()

    for orphan in report["orphan_integrity_issues"]["key_results"]:
        async with db.transaction():
            project_status = orphan.get("project_status")
            if project_status == ProjectStatus.COMPLETED.value:
                updated = await key_result_repo.complete(
                    str(orphan["id"]),
                    message="Completed key result under completed project during fixture backlog cleanup",
                )
                if updated is not None:
                    actions["orphan_key_results_completed"] += 1
            else:
                updated = await key_result_repo.archive(
                    str(orphan["id"]),
                    message="Archived key result under terminal parent during fixture backlog cleanup",
                )
                if updated is not None:
                    actions["orphan_key_results_archived"] += 1

    for orphan in report["orphan_integrity_issues"]["objectives"]:
        async with db.transaction():
            project_status = orphan.get("project_status")
            if project_status == ProjectStatus.COMPLETED.value:
                updated = await objective_repo.complete(
                    str(orphan["id"]),
                    message="Completed objective under completed project during fixture backlog cleanup",
                )
                if updated is not None:
                    actions["orphan_objectives_completed"] += 1
            else:
                updated = await objective_repo.archive(
                    str(orphan["id"]),
                    message="Archived objective under terminal parent during fixture backlog cleanup",
                )
                if updated is not None:
                    actions["orphan_objectives_archived"] += 1

    for orphan in report["orphan_integrity_issues"]["goals"]:
        async with db.transaction():
            project_status = orphan.get("project_status")
            if project_status == ProjectStatus.COMPLETED.value:
                updated = await goal_repo.complete(
                    str(orphan["id"]),
                    message="Completed goal under completed project during fixture backlog cleanup",
                )
                if updated is not None:
                    actions["orphan_goals_completed"] += 1
            else:
                updated = await goal_repo.archive(
                    str(orphan["id"]),
                    message="Archived goal under terminal parent during fixture backlog cleanup",
                )
                if updated is not None:
                    actions["orphan_goals_archived"] += 1

    for orphan in report["orphan_integrity_issues"]["plans"]:
        async with db.transaction():
            updated = await plan_repo.update(
                str(orphan["id"]),
                status=PlanStatus.ARCHIVED,
                message="Archived nonterminal plan under terminal parent during fixture backlog cleanup",
            )
            if updated is not None:
                actions["orphan_plans_archived"] += 1

    for orphan in report["orphan_integrity_issues"]["tasks"]:
        async with db.transaction():
            updated = await task_repo.update_status(
                str(orphan["id"]),
                TaskStatus.CANCELLED,
                reason="Terminal parent cleanup",
                message="Task cancelled under terminal parent during fixture backlog cleanup",
            )
            if updated is not None:
                actions["orphan_tasks_cancelled"] += 1

    for project in report["fixture_projects"]:
        project_id = str(project["project_id"])
        async with db.transaction():
            key_result_rows = await db.fetch_all(
                """
                SELECT kr.id
                FROM key_results kr
                JOIN objectives o ON o.id = kr.objective_id
                JOIN goals g ON g.id = o.goal_id
                WHERE g.project_id = ? AND kr.status = 'active'
                """,
                (project_id,),
            )
            for row in key_result_rows:
                updated = await key_result_repo.archive(
                    str(row["id"]),
                    message="Archived key result as part of fixture backlog cleanup",
                )
                if updated is not None:
                    actions["fixture_key_results_archived"] += 1

            objective_rows = await db.fetch_all(
                """
                SELECT o.id
                FROM objectives o
                JOIN goals g ON g.id = o.goal_id
                WHERE g.project_id = ? AND o.status = 'active'
                """,
                (project_id,),
            )
            for row in objective_rows:
                updated = await objective_repo.archive(
                    str(row["id"]),
                    message="Archived objective as part of fixture backlog cleanup",
                )
                if updated is not None:
                    actions["fixture_objectives_archived"] += 1

            goal_rows = await db.fetch_all(
                """
                SELECT id
                FROM goals
                WHERE project_id = ? AND status = 'active'
                """,
                (project_id,),
            )
            for row in goal_rows:
                updated = await goal_repo.archive(
                    str(row["id"]),
                    message="Archived goal as part of fixture backlog cleanup",
                )
                if updated is not None:
                    actions["fixture_goals_archived"] += 1

            plan_rows = await db.fetch_all(
                """
                SELECT id
                FROM plans
                WHERE project_id = ? AND status IN ('draft', 'active')
                """,
                (project_id,),
            )
            for row in plan_rows:
                updated = await plan_repo.update(
                    str(row["id"]),
                    status=PlanStatus.ARCHIVED,
                    message="Archived plan as part of fixture backlog cleanup",
                )
                if updated is not None:
                    actions["fixture_plans_archived"] += 1

            task_rows = await db.fetch_all(
                """
                SELECT id
                FROM tasks
                WHERE project_id = ? AND status IN ('todo', 'in_progress', 'blocked', 'in_review')
                """,
                (project_id,),
            )
            for row in task_rows:
                updated = await task_repo.update_status(
                    str(row["id"]),
                    TaskStatus.CANCELLED,
                    reason="Fixture backlog cleanup",
                    message="Task cancelled as part of fixture backlog cleanup",
                )
                if updated is not None:
                    actions["fixture_tasks_cancelled"] += 1

            archived = await project_repo.archive(
                project_id,
                message="Archived project as part of fixture backlog cleanup",
            )
            if archived is not None:
                actions["fixture_projects_archived"] += 1

    after = await _build_report(db)
    return {
        "before": report["summary"],
        "actions": dict(actions),
        "after": after["summary"],
        "remaining_unknown_active_projects": after["unknown_active_projects"],
        "remaining_fixture_projects": after["fixture_projects"],
        "remaining_orphan_integrity_issues": after["orphan_integrity_issues"],
    }


async def _run(database_path: Path | None, apply: bool) -> dict[str, Any]:
    db = await _open_database(database_path)
    try:
        report = await _build_report(db)
        if not apply:
            return report
        return await _apply_cleanup(db, report)
    finally:
        await db.disconnect()


def run_report(database_path: Path | None = None) -> dict[str, Any]:
    """Return a machine-readable cleanup classification report."""
    return asyncio.run(_run(database_path, apply=False))


def run_cleanup(database_path: Path | None = None) -> dict[str, Any]:
    """Apply fixture backlog cleanup and return before/after summary."""
    return asyncio.run(_run(database_path, apply=True))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-path",
        type=Path,
        help="Operate on an explicit database path instead of the configured PMS database.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply cleanup instead of only reporting candidates.",
    )
    args = parser.parse_args()
    result = (
        run_cleanup(args.database_path)
        if args.apply
        else run_report(args.database_path)
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
