"""Rollup helpers for portfolio, program, and organization summaries."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol

from pms.models import Goal, GoalHorizon, GoalStatus, Objective, Task, TaskStatus
from pms.models.value_contracts import RiskLevel
from pms.repositories.base import QueryResult

if TYPE_CHECKING:
    from pms.db.connection import Database


class _HasId(Protocol):
    id: str


class _HasProgressPercent(Protocol):
    @property
    def progress_percent(self) -> int: ...


class _HasUpdatedAt(Protocol):
    @property
    def updated_at(self) -> datetime | str: ...


class GoalLookupRepository(Protocol):
    async def get_by_id(self, goal_id: str) -> Goal | None: ...

    async def get_by_project(
        self, project_id: str, limit: int = 100, offset: int = 0
    ) -> QueryResult[Goal]: ...


class ObjectiveLookupRepository(Protocol):
    async def get_by_id(self, objective_id: str) -> Objective | None: ...

    async def get_by_goal(
        self, goal_id: str, limit: int = 100, offset: int = 0
    ) -> QueryResult[Objective]: ...


class TaskLookupRepository(Protocol):
    async def get_by_project(
        self,
        project_id: str,
        status: TaskStatus | None = None,
        include_subtasks: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Task]: ...


@dataclass
class RollupMetrics:
    """Aggregated metrics for goals, objectives, and tasks."""

    total_goals: int
    completed_goals: int
    avg_goal_progress: float
    total_objectives: int
    completed_objectives: int
    avg_objective_progress: float
    total_tasks: int
    blocked_tasks: int
    horizon_breakdown: dict[str, int]
    horizon_completion: dict[str, float]
    risk_score: float
    risk_level: RiskLevel


class _EffectiveGoalRollup(Protocol):
    progress_percent: int
    status: str


def dedupe_by_id[TItem: _HasId](items: Iterable[TItem]) -> list[TItem]:
    """Return a list of items de-duplicated by id."""
    seen: dict[str, TItem] = {}
    for item in items:
        seen[item.id] = item
    return list(seen.values())


def apply_effective_goal_rollups(
    goals: Sequence[Goal],
    effective_rollups: dict[str, _EffectiveGoalRollup],
) -> list[Goal]:
    """Return goal copies with effective progress/status applied when available."""
    effective_goals: list[Goal] = []
    for goal in goals:
        effective = effective_rollups.get(goal.id)
        if effective is None:
            effective_goals.append(goal)
            continue
        effective_goals.append(
            replace(
                goal,
                progress_percent=effective.progress_percent,
                status=GoalStatus(effective.status),
            )
        )
    return effective_goals


def _avg_progress(items: Sequence[_HasProgressPercent]) -> float:
    if not items:
        return 0.0
    total = sum(item.progress_percent for item in items)
    return total / len(items)


def parse_timestamp(value: object) -> datetime | None:
    """Normalize stored timestamps into timezone-aware datetimes."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def max_datetime(values: Iterable[datetime | str | None]) -> datetime | None:
    """Return the most recent datetime from a list of values."""
    candidates: list[datetime] = []
    for value in values:
        parsed = parse_timestamp(value)
        if parsed is None:
            continue
        value = parsed
        candidates.append(value)
    return max(candidates) if candidates else None


def max_updated_at(items: Iterable[_HasUpdatedAt]) -> datetime | None:
    """Return the most recent updated_at from a list of models."""
    return max_datetime(item.updated_at for item in items)


def sort_timestamp(value: datetime | str | None) -> float:
    """Return a numeric sort key for timestamps, newest first when negated."""
    parsed = parse_timestamp(value)
    if parsed is None:
        return float("-inf")
    return parsed.timestamp()


def sort_items_by_bubbled_recency[TItem](
    items: Sequence[TItem],
    *,
    activity_of: Callable[[TItem], datetime | str | None],
    transition_of: Callable[[TItem], datetime | str | None] | None = None,
    updated_of: Callable[[TItem], datetime | str | None] | None = None,
    label_of: Callable[[TItem], str] | None = None,
    id_of: Callable[[TItem], str] | None = None,
) -> list[TItem]:
    """Sort items by bubbled activity first, then transition, then stable labels."""

    def _activity(item: TItem) -> datetime | None:
        return max_datetime(
            [
                activity_of(item),
                updated_of(item) if updated_of is not None else None,
            ]
        )

    def _transition(item: TItem) -> datetime | str | None:
        if transition_of is None:
            return None
        return transition_of(item)

    def _label(item: TItem) -> str:
        if label_of is None:
            return ""
        return label_of(item).lower()

    def _id(item: TItem) -> str:
        if id_of is None:
            return ""
        return id_of(item)

    return sorted(
        items,
        key=lambda item: (
            -sort_timestamp(_activity(item)),
            -sort_timestamp(_transition(item)),
            _label(item),
            _id(item),
        ),
    )


async def fetch_grouped_max_timestamps(
    db: Database,
    query: str,
    params: tuple[object, ...],
    *,
    key_name: str = "entity_id",
) -> dict[str, datetime | None]:
    """Run a grouped timestamp query and parse its timestamp column."""
    rows = await db.fetch_all(query, params)
    return {
        row[key_name]: parse_timestamp(row.get("ts"))
        for row in rows
        if row.get(key_name)
    }


async def fetch_grouped_review_activity(
    db: Database,
    *,
    scope_type: str,
    params: tuple[object, ...],
    key_name: str,
    select_key_sql: str,
    where_sql: str,
    join_sql: str = "",
) -> dict[str, datetime | None]:
    """Fetch grouped review activity timestamps for direct or joined scope rollups."""
    where_clause = " AND ".join(
        clause for clause in ("review.scope_type = ?", where_sql.strip()) if clause
    )
    query = f"""
        SELECT {select_key_sql} as {key_name}, MAX(review.reviewed_at) as ts
        FROM work_snapshot_reviews review
        {join_sql}
        WHERE {where_clause}
        GROUP BY {select_key_sql}
    """
    return await fetch_grouped_max_timestamps(
        db,
        query,
        (scope_type, *params),
        key_name=key_name,
    )


def compute_horizon_rollup(
    goals: Sequence[Goal],
) -> tuple[dict[str, int], dict[str, float]]:
    """Compute horizon counts and completion percentages for goals."""
    counts = {h.value: 0 for h in GoalHorizon}
    completed = {h.value: 0 for h in GoalHorizon}

    for goal in goals:
        horizon = goal.horizon.value
        counts[horizon] += 1
        if goal.status == GoalStatus.COMPLETED:
            completed[horizon] += 1

    completion = {}
    for horizon, total in counts.items():
        completion[horizon] = (completed[horizon] / total) * 100 if total else 0.0

    return counts, completion


def compute_risk(total_tasks: int, blocked_tasks: int) -> tuple[float, RiskLevel]:
    """Compute a simple risk score and level from blocked tasks."""
    if total_tasks <= 0:
        return 0.0, "low"

    ratio = blocked_tasks / total_tasks
    if ratio >= 0.3:
        return ratio, "high"
    if ratio >= 0.1:
        return ratio, "medium"
    return ratio, "low"


def build_rollup_metrics(
    goals: Sequence[Goal],
    objectives: Sequence[Objective],
    tasks: Sequence[Task],
) -> RollupMetrics:
    """Build rollup metrics from goal/objective/task sets."""
    total_goals = len(goals)
    completed_goals = sum(1 for g in goals if g.status == GoalStatus.COMPLETED)
    avg_goal_progress = _avg_progress(goals)

    total_objectives = len(objectives)
    completed_objectives = sum(
        1 for obj in objectives if obj.status == GoalStatus.COMPLETED
    )
    avg_objective_progress = _avg_progress(objectives)

    total_tasks = len(tasks)
    blocked_tasks = sum(1 for task in tasks if task.status == TaskStatus.BLOCKED)

    horizon_breakdown, horizon_completion = compute_horizon_rollup(goals)
    risk_score, risk_level = compute_risk(total_tasks, blocked_tasks)

    return RollupMetrics(
        total_goals=total_goals,
        completed_goals=completed_goals,
        avg_goal_progress=avg_goal_progress,
        total_objectives=total_objectives,
        completed_objectives=completed_objectives,
        avg_objective_progress=avg_objective_progress,
        total_tasks=total_tasks,
        blocked_tasks=blocked_tasks,
        horizon_breakdown=horizon_breakdown,
        horizon_completion=horizon_completion,
        risk_score=risk_score,
        risk_level=risk_level,
    )


async def collect_rollup_entities(
    goal_repo: GoalLookupRepository,
    objective_repo: ObjectiveLookupRepository,
    task_repo: TaskLookupRepository,
    goal_ids: Sequence[str] | None,
    objective_ids: Sequence[str] | None,
    project_ids: Sequence[str] | None,
) -> tuple[list[Goal], list[Objective], list[Task]]:
    """Collect and de-duplicate goals, objectives, and tasks for rollups."""
    goals: list[Goal] = []
    objectives: list[Objective] = []
    tasks: list[Task] = []

    for goal_id in goal_ids or []:
        goal = await goal_repo.get_by_id(goal_id)
        if goal:
            goals.append(goal)

    for project_id in project_ids or []:
        goal_result = await goal_repo.get_by_project(project_id, limit=1000, offset=0)
        goals.extend(goal_result.items)

    goals = dedupe_by_id(goals)

    for objective_id in objective_ids or []:
        objective = await objective_repo.get_by_id(objective_id)
        if objective:
            objectives.append(objective)

    for goal in goals:
        objective_result = await objective_repo.get_by_goal(
            goal.id, limit=1000, offset=0
        )
        objectives.extend(objective_result.items)

    objectives = dedupe_by_id(objectives)

    for project_id in project_ids or []:
        task_result = await task_repo.get_by_project(project_id, limit=1000, offset=0)
        tasks.extend(task_result.items)

    tasks = dedupe_by_id(tasks)

    return goals, objectives, tasks
