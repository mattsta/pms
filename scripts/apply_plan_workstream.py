"""Apply a structured workstream spec into PMS."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.db.connection import init_database
from pms.models import GoalHorizon, PlanFormat, PlanStatus, Priority
from pms.models.json_types import JsonObject
from pms.repositories.base import RepositoryContext
from pms.repositories.task_repository import TaskRepository
from pms.services.goal_service import GoalService
from pms.services.plan_service import PlanService
from pms.services.project_service import ProjectService
from pms.services.task_service import TaskService


@dataclass(frozen=True)
class GoalSpec:
    name: str
    description: str
    owner: str


@dataclass(frozen=True)
class TaskSpec:
    title: str
    description: str
    priority: str
    done_when: tuple[str, ...]
    depends_on: tuple[str, ...]


@dataclass(frozen=True)
class InitialProgressSpec:
    task_title: str
    percent: int
    message: str


@dataclass(frozen=True)
class PlanWorkstreamSpec:
    plan_id: str
    project_ref: str
    goal: GoalSpec
    plan_content: JsonObject
    initial_progress: InitialProgressSpec
    tasks: tuple[TaskSpec, ...]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec_path", help="Path to the workstream JSON spec")
    parser.add_argument(
        "--actor",
        default="codex",
        help="Actor/user id recorded in PMS context and progress updates",
    )
    return parser.parse_args()


def _load_spec(path: Path) -> PlanWorkstreamSpec:
    raw = json.loads(path.read_text(encoding="utf-8"))
    goal_raw = raw["goal"]
    progress_raw = raw["initial_progress"]
    task_specs = tuple(
        TaskSpec(
            title=item["title"],
            description=item["description"],
            priority=item["priority"],
            done_when=tuple(item["done_when"]),
            depends_on=tuple(item.get("depends_on", [])),
        )
        for item in raw["tasks"]
    )
    return PlanWorkstreamSpec(
        plan_id=raw["plan_id"],
        project_ref=raw["project_ref"],
        goal=GoalSpec(
            name=goal_raw["name"],
            description=goal_raw["description"],
            owner=goal_raw["owner"],
        ),
        plan_content=raw["plan_content"],
        initial_progress=InitialProgressSpec(
            task_title=progress_raw["task_title"],
            percent=progress_raw["percent"],
            message=progress_raw["message"],
        ),
        tasks=task_specs,
    )


def _priority(value: str) -> Priority:
    return Priority(value)


async def _run(spec: PlanWorkstreamSpec, actor: str) -> JsonObject:
    db = await init_database()
    try:
        event_store = EventStore(db)
        revision_store = RevisionStore(db)
        metrics = MetricsCollector(db)

        goal_service = GoalService(
            db, event_store, revision_store, metrics
        ).with_context(user_id=actor)
        plan_service = PlanService(
            db, event_store, revision_store, metrics
        ).with_context(user_id=actor)
        project_service = ProjectService(
            db, event_store, revision_store, metrics
        ).with_context(user_id=actor)
        task_service = TaskService(
            db, event_store, revision_store, metrics
        ).with_context(user_id=actor)
        task_repo = TaskRepository(
            db, event_store, revision_store, metrics
        ).with_context(RepositoryContext(user_id=actor))

        project = await project_service.get_project(spec.project_ref)
        if project is None:
            project = await project_service.get_project_by_name(spec.project_ref)
        if project is None:
            raise ValueError(f"Project '{spec.project_ref}' not found")

        goals = await goal_service.list_goals(
            project_id=project.id, limit=500, offset=0
        )
        goal = next((item for item in goals.items if item.name == spec.goal.name), None)
        if goal is None:
            goal = await goal_service.create_goal(
                name=spec.goal.name,
                description=spec.goal.description,
                horizon=GoalHorizon.SHORT_TERM,
                owner=spec.goal.owner,
                project_id=project.id,
            )

        task_result = await task_service.list_tasks(
            project_id=project.id, limit=500, offset=0
        )
        tasks_by_title = {task.title: task for task in task_result.items}
        ensured_task_ids: dict[str, str] = {}

        for task_spec in spec.tasks:
            task = tasks_by_title.get(task_spec.title)
            if task is None:
                task = await task_service.create_task(
                    project_id=project.id,
                    title=task_spec.title,
                    description=task_spec.description,
                    priority=_priority(task_spec.priority),
                )
            task = await task_service.update_task(
                task_id=task.id,
                description=task_spec.description,
                priority=_priority(task_spec.priority),
                completion_criteria=list(task_spec.done_when),
            )
            if task is None:
                raise ValueError(f"Failed to ensure task '{task_spec.title}'")
            ensured_task_ids[task_spec.title] = task.id

        for task_spec in spec.tasks:
            task_id = ensured_task_ids[task_spec.title]
            existing_deps = await task_repo.get_dependencies(task_id)
            existing_dep_ids = {dep.depends_on_id for dep in existing_deps}
            for depends_on_title in task_spec.depends_on:
                depends_on_id = ensured_task_ids[depends_on_title]
                if depends_on_id in existing_dep_ids:
                    continue
                await task_service.add_dependency(task_id, depends_on_id)

        updated_plan = await plan_service.update_plan(
            plan_id=spec.plan_id,
            status=PlanStatus.ACTIVE,
            format=PlanFormat.JSON,
            content=spec.plan_content,
            project_id=project.id,
            goal_id=goal.id,
            task_ids=[ensured_task_ids[item.title] for item in spec.tasks],
        )
        if updated_plan is None:
            raise ValueError(f"Plan '{spec.plan_id}' not found")

        focus_task_id = ensured_task_ids[spec.initial_progress.task_title]
        focus_task = await task_service.get_task(focus_task_id)
        if focus_task is None:
            raise ValueError("Focus task missing after ensure")
        if focus_task.status.value == "todo":
            await task_service.start_task(
                focus_task_id, reason="Activated by plan workstream"
            )
        await task_service.update_task_progress(
            task_id=focus_task_id,
            percent_complete=spec.initial_progress.percent,
            status_message=spec.initial_progress.message,
            updated_by=actor,
        )

        return {
            "plan_id": updated_plan.id,
            "goal_id": goal.id,
            "project_id": project.id,
            "task_ids": [ensured_task_ids[item.title] for item in spec.tasks],
            "focus_task_id": focus_task_id,
        }
    finally:
        await db.disconnect()


def main() -> None:
    args = _parse_args()
    spec = _load_spec(Path(args.spec_path))
    result = asyncio.run(_run(spec, args.actor))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
