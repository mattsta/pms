"""Synchronize execution-backed key results to live task progress.

This script is intentionally spec-driven so plan hierarchies can be kept in sync
without ad hoc shell fragments. Each mapping ties one key result to one task.
Updating the key result lets the existing goal-service rollup logic propagate
objective and goal progress automatically.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.db.connection import init_database
from pms.models import GoalStatus, TaskStatus
from pms.models.json_types import JsonObject
from pms.services.goal_service import GoalService
from pms.services.task_service import TaskService


@dataclass(frozen=True)
class RollupMapping:
    key_result_id: str
    task_id: str
    label: str


@dataclass(frozen=True)
class RollupSyncSpec:
    goal_id: str
    mappings: tuple[RollupMapping, ...]


@dataclass(frozen=True)
class RollupDrift:
    mapping: RollupMapping
    task_id: str
    task_title: str
    task_status: str
    task_progress_percent: int
    key_result_id: str
    key_result_name: str
    key_result_status: str
    key_result_progress_percent: int
    target_status: str
    target_progress_percent: int


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec_path", help="Path to the rollup sync spec JSON")
    parser.add_argument(
        "--actor",
        default="codex",
        help="Actor/user id recorded in PMS history",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report drift and exit nonzero without mutating key results",
    )
    return parser.parse_args()


def _load_spec(path: Path) -> RollupSyncSpec:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return RollupSyncSpec(
        goal_id=raw["goal_id"],
        mappings=tuple(
            RollupMapping(
                key_result_id=item["key_result_id"],
                task_id=item["task_id"],
                label=item.get("label", item["key_result_id"]),
            )
            for item in raw["mappings"]
        ),
    )


def _key_result_status_for_task(task_status: TaskStatus) -> GoalStatus:
    if task_status == TaskStatus.DONE:
        return GoalStatus.COMPLETED
    if task_status == TaskStatus.CANCELLED:
        return GoalStatus.ARCHIVED
    return GoalStatus.ACTIVE


async def collect_drift(spec: RollupSyncSpec, actor: str) -> tuple[RollupDrift, ...]:
    db = await init_database()
    try:
        event_store = EventStore(db)
        revision_store = RevisionStore(db)
        metrics = MetricsCollector(db)
        goal_service = GoalService(
            db, event_store, revision_store, metrics
        ).with_context(user_id=actor)
        task_service = TaskService(
            db, event_store, revision_store, metrics
        ).with_context(user_id=actor)

        goal = await goal_service.get_goal(spec.goal_id)
        if goal is None:
            raise LookupError(f"Unknown goal: {spec.goal_id}")

        drifts: list[RollupDrift] = []
        for mapping in spec.mappings:
            key_result = await goal_service.get_key_result(mapping.key_result_id)
            if key_result is None:
                raise RuntimeError(f"Unknown key result: {mapping.key_result_id}")
            task = await task_service.get_task(mapping.task_id)
            if task is None:
                raise RuntimeError(f"Unknown task: {mapping.task_id}")

            target_progress = int(task.current_progress_percent)
            target_status = _key_result_status_for_task(task.status)
            if (
                key_result.progress_percent != target_progress
                or key_result.status != target_status
            ):
                drifts.append(
                    RollupDrift(
                        mapping=mapping,
                        task_id=task.id,
                        task_title=task.title,
                        task_status=task.status.value,
                        task_progress_percent=target_progress,
                        key_result_id=key_result.id,
                        key_result_name=key_result.name,
                        key_result_status=key_result.status.value,
                        key_result_progress_percent=key_result.progress_percent,
                        target_status=target_status.value,
                        target_progress_percent=target_progress,
                    )
                )
        return tuple(drifts)
    finally:
        await db.disconnect()


async def _run(spec: RollupSyncSpec, actor: str) -> JsonObject:
    db = await init_database()
    try:
        event_store = EventStore(db)
        revision_store = RevisionStore(db)
        metrics = MetricsCollector(db)
        goal_service = GoalService(
            db, event_store, revision_store, metrics
        ).with_context(user_id=actor)
        task_service = TaskService(
            db, event_store, revision_store, metrics
        ).with_context(user_id=actor)

        updates: list[dict[str, Any]] = []
        for mapping in spec.mappings:
            key_result = await goal_service.get_key_result(mapping.key_result_id)
            if key_result is None:
                raise RuntimeError(f"Unknown key result: {mapping.key_result_id}")
            task = await task_service.get_task(mapping.task_id)
            if task is None:
                raise RuntimeError(f"Unknown task: {mapping.task_id}")

            target_progress = int(task.current_progress_percent)
            target_status = _key_result_status_for_task(task.status)
            target_value = (
                float(key_result.target_value)
                if task.status == TaskStatus.DONE
                and key_result.target_value is not None
                else key_result.current_value
            )

            changed = (
                key_result.progress_percent != target_progress
                or key_result.status != target_status
                or target_value != key_result.current_value
            )
            if changed:
                updated = await goal_service.update_key_result(
                    key_result_id=key_result.id,
                    status=target_status,
                    current_value=target_value,
                    progress_percent=target_progress,
                    message=(
                        f"Sync execution-backed rollup from task "
                        f"{task.title} ({task.id})"
                    ),
                )
                if updated is None:
                    raise RuntimeError(f"Failed to update key result: {key_result.id}")

            updates.append(
                {
                    "label": mapping.label,
                    "task": {
                        "id": task.id,
                        "title": task.title,
                        "status": task.status.value,
                        "progress_percent": task.current_progress_percent,
                    },
                    "key_result": {
                        "id": key_result.id,
                        "name": key_result.name,
                        "previous_status": key_result.status.value,
                        "new_status": target_status.value,
                        "previous_progress_percent": key_result.progress_percent,
                        "new_progress_percent": target_progress,
                    },
                    "changed": changed,
                }
            )

        goal_summary = await goal_service.get_goal_summary(spec.goal_id)
        if goal_summary is None:
            raise RuntimeError(f"Unknown goal: {spec.goal_id}")

        return {
            "goal_id": spec.goal_id,
            "updated_count": sum(1 for item in updates if item["changed"]),
            "updates": updates,
            "goal_summary": {
                "goal_id": goal_summary.goal.id,
                "stored_progress_percent": goal_summary.goal.progress_percent,
                "stored_status": goal_summary.goal.status.value,
                "objective_count": goal_summary.objective_count,
                "completed_objectives": goal_summary.completed_objectives,
                "key_result_count": goal_summary.key_result_count,
                "completed_key_results": goal_summary.completed_key_results,
                "average_progress": goal_summary.average_progress,
            },
        }
    finally:
        await db.disconnect()


def main() -> None:
    args = _parse_args()
    spec = _load_spec(Path(args.spec_path))
    if args.check:
        drifts = asyncio.run(collect_drift(spec, args.actor))
        payload = {
            "goal_id": spec.goal_id,
            "issue_count": len(drifts),
            "issues": [
                {
                    "label": drift.mapping.label,
                    "task": {
                        "id": drift.task_id,
                        "title": drift.task_title,
                        "status": drift.task_status,
                        "progress_percent": drift.task_progress_percent,
                    },
                    "key_result": {
                        "id": drift.key_result_id,
                        "name": drift.key_result_name,
                        "status": drift.key_result_status,
                        "progress_percent": drift.key_result_progress_percent,
                    },
                    "target": {
                        "status": drift.target_status,
                        "progress_percent": drift.target_progress_percent,
                    },
                }
                for drift in drifts
            ],
        }
        print(json.dumps(payload, indent=2))
        raise SystemExit(1 if drifts else 0)

    result = asyncio.run(_run(spec, args.actor))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
