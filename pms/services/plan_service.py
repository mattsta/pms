"""Plan service for plan artifact operations."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, replace
from datetime import datetime
from typing import TYPE_CHECKING

from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.exceptions import ValidationError
from pms.models import Plan, PlanFormat, PlanStatus
from pms.models.enums import GoalStatus, ProjectStatus, TaskStatus
from pms.models.json_types import JsonValue
from pms.repositories.base import QueryResult, RepositoryContext
from pms.repositories.goal_repository import GoalRepository
from pms.repositories.objective_repository import ObjectiveRepository
from pms.repositories.plan_repository import PlanRepository
from pms.repositories.product_repository import ProductRepository
from pms.repositories.project_repository import ProjectRepository
from pms.repositories.task_repository import TaskRepository
from pms.services.generated_artifacts import (
    is_quickstart_generated_plan,
)
from pms.services.link_validation import validate_optional_reference_id
from pms.services.rollup_utils import max_datetime

if TYPE_CHECKING:
    from pms.db.connection import Database

type PlanContentInput = JsonValue
type TimestampSource = JsonValue | datetime

AUTO_LINK_PLAN_TASK_MESSAGE = "Auto-linked new project task into active plan lineage"


@dataclass
class QuickstartPlanUpsertResult:
    """Result of reconciling quickstart-generated plans for a project."""

    plan: Plan
    reused_existing: bool
    archived_duplicate_plan_ids: list[str]


@dataclass(frozen=True)
class PlanLifecycleRollup:
    """Derived lifecycle state for a plan from its linked execution graph."""

    effective_status: PlanStatus
    terminal_reason: str | None = None


class PlanService:
    """Service for plan artifact management."""

    def __init__(
        self,
        db: Database,
        event_store: EventStore,
        revision_store: RevisionStore,
        metrics: MetricsCollector,
    ) -> None:
        self.db = db
        self.events = event_store
        self.revisions = revision_store
        self.metrics = metrics

        self._plan_repo = PlanRepository(db, event_store, revision_store, metrics)
        self._product_repo = ProductRepository(db, event_store, revision_store, metrics)
        self._project_repo = ProjectRepository(db, event_store, revision_store, metrics)
        self._goal_repo = GoalRepository(db, event_store, revision_store, metrics)
        self._objective_repo = ObjectiveRepository(
            db, event_store, revision_store, metrics
        )
        self._task_repo = TaskRepository(db, event_store, revision_store, metrics)
        self._context = RepositoryContext()

    def with_context(
        self,
        user_id: str | None = None,
        session_id: str | None = None,
        correlation_id: str | None = None,
    ) -> PlanService:
        """Set context for subsequent operations."""
        self._context = RepositoryContext(
            user_id=user_id,
            session_id=session_id,
            correlation_id=correlation_id,
        )
        self._plan_repo.with_context(self._context)
        self._task_repo.with_context(self._context)
        return self

    def _normalize_content(self, format: PlanFormat, content: PlanContentInput) -> str:
        """Normalize plan content into a serialized string."""
        match format:
            case PlanFormat.JSON:
                parsed = json.loads(content) if isinstance(content, str) else content
                return json.dumps(parsed, indent=2, sort_keys=True)
            case PlanFormat.YAML:
                if not isinstance(content, str):
                    raise ValidationError("YAML content must be a string", "content")
                return content
            case _:
                return str(content)

    async def _reconcile_scope_projects_for_plans(
        self, plans: list[Plan | None]
    ) -> None:
        """Reconcile project lifecycle for the project scopes touched by plans."""
        scoped_plans = [plan for plan in plans if plan is not None]
        if not scoped_plans:
            return

        scope_project_map = await self._plan_scope_project_map(scoped_plans)
        project_ids = sorted(
            {
                project_id
                for project_id in scope_project_map.values()
                if project_id is not None
            }
        )
        if not project_ids:
            return

        from pms.services.project_service import ProjectService

        project_service = ProjectService(
            self.db,
            self.events,
            self.revisions,
            self.metrics,
        )
        for project_id in project_ids:
            await project_service.reconcile_project_lifecycle(project_id)

    async def create_plan(
        self,
        name: str,
        description: str | None,
        status: PlanStatus,
        format: PlanFormat,
        content: PlanContentInput,
        product_id: str | None = None,
        project_id: str | None = None,
        goal_id: str | None = None,
        objective_id: str | None = None,
        task_ids: list[str] | None = None,
        tags: list[str] | None = None,
        message: str | None = None,
    ) -> Plan:
        """Create a new plan artifact."""
        content_str = self._normalize_content(format, content)
        validated_product_id = await validate_optional_reference_id(
            self._product_repo,
            product_id,
            field_name="product_id",
            entity_label="Product",
        )
        validated_project_id = await validate_optional_reference_id(
            self._project_repo,
            project_id,
            field_name="project_id",
            entity_label="Project",
        )
        validated_goal_id = await validate_optional_reference_id(
            self._goal_repo,
            goal_id,
            field_name="goal_id",
            entity_label="Goal",
        )
        validated_objective_id = await validate_optional_reference_id(
            self._objective_repo,
            objective_id,
            field_name="objective_id",
            entity_label="Objective",
        )
        if validated_goal_id and validated_project_id:
            goal = await self._goal_repo.get_by_id(validated_goal_id)
            if goal and goal.project_id and goal.project_id != validated_project_id:
                raise ValidationError(
                    "goal_id must belong to the same project_id",
                    "goal_id",
                )
        if validated_objective_id and validated_goal_id:
            objective = await self._objective_repo.get_by_id(validated_objective_id)
            if objective and objective.goal_id != validated_goal_id:
                raise ValidationError(
                    "objective_id must belong to the same goal_id",
                    "objective_id",
                )

        async with self._plan_repo.db.transaction():
            plan = await self._plan_repo.create(
                name=name,
                description=description,
                status=status,
                format=format,
                content=content_str,
                product_id=validated_product_id,
                project_id=validated_project_id,
                goal_id=validated_goal_id,
                objective_id=validated_objective_id,
                task_ids=task_ids,
                tags=tags,
                message=message,
            )

            await self._reconcile_scope_projects_for_plans([plan])
            await self.metrics.record_counter("plan.created")
            await self.metrics.flush()

        return plan

    async def get_plan(self, plan_id: str) -> Plan | None:
        """Get a plan by ID."""
        return await self._plan_repo.get_by_id(plan_id)

    async def get_plan_by_name(self, name: str) -> Plan | None:
        """Get a plan by name."""
        return await self._plan_repo.get_by_name(name)

    async def list_quickstart_plans(
        self,
        project_id: str,
        plan_name: str,
    ) -> list[Plan]:
        """List quickstart-generated plans for a project."""
        result = await self._plan_repo.list_plans(project_id=project_id, limit=1000)
        return [
            plan
            for plan in result.items
            if is_quickstart_generated_plan(plan, plan_name=plan_name)
        ]

    async def list_plans(
        self,
        status: PlanStatus | None = None,
        project_id: str | None = None,
        product_id: str | None = None,
        goal_id: str | None = None,
        objective_id: str | None = None,
        task_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Plan]:
        """List plans with optional filters."""
        return await self._plan_repo.list_plans(
            status=status,
            project_id=project_id,
            product_id=product_id,
            goal_id=goal_id,
            objective_id=objective_id,
            task_id=task_id,
            limit=limit,
            offset=offset,
        )

    async def update_plan(
        self,
        plan_id: str,
        name: str | None = None,
        description: str | None = None,
        status: PlanStatus | None = None,
        format: PlanFormat | None = None,
        content: PlanContentInput | None = None,
        product_id: str | None = None,
        project_id: str | None = None,
        goal_id: str | None = None,
        objective_id: str | None = None,
        task_ids: list[str] | None = None,
        tags: list[str] | None = None,
        message: str | None = None,
    ) -> Plan | None:
        """Update a plan artifact."""
        existing = await self._plan_repo.get_by_id(plan_id)
        if existing is None:
            return None

        if format is not None and content is None:
            raise ValidationError("Format updates require new content", "format")

        content_str = None
        if content is not None:
            content_str = self._normalize_content(format or existing.format, content)
        validated_product_id = await validate_optional_reference_id(
            self._product_repo,
            product_id,
            field_name="product_id",
            entity_label="Product",
        )
        validated_project_id = await validate_optional_reference_id(
            self._project_repo,
            project_id,
            field_name="project_id",
            entity_label="Project",
        )
        validated_goal_id = await validate_optional_reference_id(
            self._goal_repo,
            goal_id,
            field_name="goal_id",
            entity_label="Goal",
        )
        validated_objective_id = await validate_optional_reference_id(
            self._objective_repo,
            objective_id,
            field_name="objective_id",
            entity_label="Objective",
        )
        effective_project_id = validated_project_id or existing.project_id
        effective_goal_id = validated_goal_id or existing.goal_id
        if effective_goal_id and effective_project_id:
            goal = await self._goal_repo.get_by_id(effective_goal_id)
            if goal and goal.project_id and goal.project_id != effective_project_id:
                raise ValidationError(
                    "goal_id must belong to the same project_id",
                    "goal_id",
                )
        effective_objective_id = validated_objective_id or existing.objective_id
        if effective_objective_id and effective_goal_id:
            objective = await self._objective_repo.get_by_id(effective_objective_id)
            if objective and objective.goal_id != effective_goal_id:
                raise ValidationError(
                    "objective_id must belong to the same goal_id",
                    "objective_id",
                )

        async with self._plan_repo.db.transaction():
            plan = await self._plan_repo.update(
                plan_id=plan_id,
                name=name,
                description=description,
                status=status,
                format=format,
                content=content_str,
                product_id=validated_product_id,
                project_id=validated_project_id,
                goal_id=validated_goal_id,
                objective_id=validated_objective_id,
                task_ids=task_ids,
                tags=tags,
                message=message,
            )

            if plan is None:
                return None

            await self._reconcile_scope_projects_for_plans([existing, plan])
            await self.metrics.record_counter("plan.updated")
            await self.metrics.flush()

        return plan

    async def upsert_quickstart_plan(
        self,
        *,
        name: str,
        description: str,
        status: PlanStatus,
        format: PlanFormat,
        content: PlanContentInput,
        product_id: str | None,
        project_id: str,
        task_ids: list[str] | None,
    ) -> QuickstartPlanUpsertResult:
        """Create or update the canonical quickstart plan and archive duplicates."""
        async with self._plan_repo.db.transaction():
            existing_plans = await self.list_quickstart_plans(project_id, name)
            reusable_plans = [
                plan for plan in existing_plans if plan.status != PlanStatus.ARCHIVED
            ]
            reusable_plans.sort(
                key=lambda plan: (
                    self._parse_timestamp(plan.updated_at)
                    or self._parse_timestamp(plan.created_at)
                    or datetime.min
                ),
                reverse=True,
            )

            archived_duplicate_plan_ids: list[str] = []
            canonical_plan: Plan
            reused_existing = bool(reusable_plans)
            if reusable_plans:
                canonical_plan = (
                    await self.update_plan(
                        reusable_plans[0].id,
                        description=description,
                        status=status,
                        format=format,
                        content=content,
                        product_id=product_id,
                        project_id=project_id,
                        task_ids=task_ids,
                        tags=["generated", "quickstart"],
                    )
                    or reusable_plans[0]
                )
            else:
                canonical_plan = await self.create_plan(
                    name=name,
                    description=description,
                    status=status,
                    format=format,
                    content=content,
                    product_id=product_id,
                    project_id=project_id,
                    task_ids=task_ids,
                    tags=["generated", "quickstart"],
                )

            for duplicate in existing_plans:
                if (
                    duplicate.id == canonical_plan.id
                    or duplicate.status == PlanStatus.ARCHIVED
                ):
                    continue
                updated = await self.update_plan(
                    duplicate.id,
                    status=PlanStatus.ARCHIVED,
                    message="Archived duplicate quickstart plan",
                )
                if updated is not None:
                    archived_duplicate_plan_ids.append(updated.id)

            return QuickstartPlanUpsertResult(
                plan=canonical_plan,
                reused_existing=reused_existing,
                archived_duplicate_plan_ids=sorted(archived_duplicate_plan_ids),
            )

    def _parse_timestamp(self, value: TimestampSource) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return None

    @staticmethod
    def _is_omnibus_import_plan(plan: Plan) -> bool:
        return "claudo-import" in plan.tags or plan.name.startswith("Claudo Import:")

    @staticmethod
    def _decode_revision_task_ids(value: object) -> set[str]:
        current = value
        for _ in range(2):
            if not isinstance(current, str):
                break
            try:
                current = json.loads(current)
            except TypeError, ValueError:
                return set()
        if not isinstance(current, list):
            return set()
        return {str(item) for item in current if str(item)}

    async def _auto_linked_task_ids_by_plan(
        self,
        plan_ids: list[str],
    ) -> dict[str, set[str]]:
        unique_ids = list(dict.fromkeys(plan_id for plan_id in plan_ids if plan_id))
        if not unique_ids:
            return {}

        placeholders = ", ".join("?" * len(unique_ids))
        rows = await self.db.fetch_all(
            f"""
            SELECT entity_id, changes
            FROM revisions
            WHERE entity_type = 'plan'
              AND entity_id IN ({placeholders})
              AND message = ?
            """,
            (*unique_ids, AUTO_LINK_PLAN_TASK_MESSAGE),
        )
        auto_linked: dict[str, set[str]] = {plan_id: set() for plan_id in unique_ids}
        for row in rows:
            plan_id = str(row["entity_id"])
            try:
                changes = json.loads(str(row["changes"]))
            except TypeError, ValueError:
                continue
            if not isinstance(changes, list):
                continue
            for change in changes:
                if (
                    not isinstance(change, dict)
                    or change.get("field_name") != "task_ids"
                ):
                    continue
                old_ids = self._decode_revision_task_ids(change.get("old_value"))
                new_ids = self._decode_revision_task_ids(change.get("new_value"))
                auto_linked.setdefault(plan_id, set()).update(new_ids - old_ids)
        return auto_linked

    def _task_rollup_ids_by_plan(
        self,
        plans: list[Plan],
        auto_linked_task_ids: dict[str, set[str]],
    ) -> dict[str, tuple[str, ...]]:
        """Drop old ambiguous fan-out auto-links from per-plan recency rollups."""
        auto_linked_counts: Counter[str] = Counter()
        for plan in plans:
            if self._is_omnibus_import_plan(plan):
                continue
            auto_linked_counts.update(auto_linked_task_ids.get(plan.id, set()))

        task_ids_by_plan: dict[str, tuple[str, ...]] = {}
        for plan in plans:
            if self._is_omnibus_import_plan(plan):
                task_ids_by_plan[plan.id] = plan.task_ids
                continue
            ambiguous_auto_links = {
                task_id
                for task_id in auto_linked_task_ids.get(plan.id, set())
                if auto_linked_counts[task_id] > 1
            }
            task_ids_by_plan[plan.id] = tuple(
                task_id
                for task_id in plan.task_ids
                if task_id not in ambiguous_auto_links
            )
        return task_ids_by_plan

    async def _plan_direct_activity_map(
        self,
        plans: list[Plan],
    ) -> dict[str, datetime | None]:
        """Return direct plan activity without broad auto-link bookkeeping updates."""
        plan_ids = [plan.id for plan in plans]
        if not plan_ids:
            return {}

        activity = {plan.id: self._parse_timestamp(plan.created_at) for plan in plans}
        placeholders = ", ".join("?" * len(plan_ids))
        rows = await self.db.fetch_all(
            f"""
            SELECT entity_id, MAX(created_at) as ts
            FROM revisions
            WHERE entity_type = 'plan'
              AND entity_id IN ({placeholders})
              AND (message IS NULL OR message != ?)
            GROUP BY entity_id
            """,
            (*plan_ids, AUTO_LINK_PLAN_TASK_MESSAGE),
        )
        for row in rows:
            plan_id = str(row["entity_id"])
            activity[plan_id] = max_datetime(
                [activity.get(plan_id), self._parse_timestamp(row.get("ts"))]
            )
        return activity

    async def _linked_entity_activity_map(
        self,
        table_name: str,
        entity_type: str,
        entity_ids: list[str | None],
    ) -> dict[str, datetime | None]:
        """Fetch direct activity timestamps for linked entities."""
        unique_ids = list(
            dict.fromkeys(entity_id for entity_id in entity_ids if entity_id)
        )
        if not unique_ids:
            return {}

        placeholders = ", ".join("?" * len(unique_ids))
        rows = await self.db.fetch_all(
            f"SELECT id, updated_at FROM {table_name} WHERE id IN ({placeholders})",
            tuple(unique_ids),
        )
        activity_map = {
            row["id"]: self._parse_timestamp(row.get("updated_at")) for row in rows
        }

        for query in (
            f"""
            SELECT entity_id, MAX(updated_at) as ts
            FROM custom_field_values
            WHERE entity_type = '{entity_type}' AND entity_id IN ({placeholders})
            GROUP BY entity_id
            """,
            f"""
            SELECT entity_id, MAX(updated_at) as ts
            FROM comments
            WHERE entity_type = '{entity_type}' AND entity_id IN ({placeholders})
            GROUP BY entity_id
            """,
            f"""
            SELECT entity_id, MAX(COALESCE(archived_at, updated_at, created_at)) as ts
            FROM label_assignments
            WHERE entity_type = '{entity_type}' AND entity_id IN ({placeholders})
            GROUP BY entity_id
            """,
            f"""
            SELECT entity_id, MAX(COALESCE(archived_at, updated_at, created_at)) as ts
            FROM entity_watchers
            WHERE entity_type = '{entity_type}' AND entity_id IN ({placeholders})
            GROUP BY entity_id
            """,
        ):
            related_rows = await self.db.fetch_all(query, tuple(unique_ids))
            for row in related_rows:
                entity_id = row["entity_id"]
                activity_map[entity_id] = max_datetime(
                    [
                        activity_map.get(entity_id),
                        self._parse_timestamp(row.get("ts")),
                    ]
                )

        return activity_map

    async def _linked_entity_transition_map(
        self,
        entity_type: str,
        entity_ids: list[str | None],
    ) -> dict[str, datetime | None]:
        unique_ids = list(
            dict.fromkeys(entity_id for entity_id in entity_ids if entity_id)
        )
        if not unique_ids:
            return {}
        from pms.repositories.state_transition_repository import (
            StateTransitionRepository,
        )

        state_repo = StateTransitionRepository(self.db)
        return await state_repo.get_last_transition_map(
            f"{entity_type}_status",
            unique_ids,
        )

    async def _plan_scope_project_map(
        self,
        plans: list[Plan],
    ) -> dict[str, str | None]:
        """Resolve the project scope that should bubble activity into each plan."""
        goal_ids = list(dict.fromkeys(plan.goal_id for plan in plans if plan.goal_id))
        objective_ids = list(
            dict.fromkeys(plan.objective_id for plan in plans if plan.objective_id)
        )

        goal_project_map: dict[str, str | None] = {}
        if goal_ids:
            placeholders = ", ".join("?" * len(goal_ids))
            rows = await self.db.fetch_all(
                f"SELECT id, project_id FROM goals WHERE id IN ({placeholders})",
                tuple(goal_ids),
            )
            goal_project_map = {row["id"]: row.get("project_id") for row in rows}

        objective_project_map: dict[str, str | None] = {}
        if objective_ids:
            placeholders = ", ".join("?" * len(objective_ids))
            rows = await self.db.fetch_all(
                f"""
                SELECT o.id, g.project_id
                FROM objectives o
                LEFT JOIN goals g ON o.goal_id = g.id
                WHERE o.id IN ({placeholders})
                """,
                tuple(objective_ids),
            )
            objective_project_map = {row["id"]: row.get("project_id") for row in rows}

        return {
            plan.id: (
                plan.project_id
                or goal_project_map.get(plan.goal_id)
                or objective_project_map.get(plan.objective_id)
            )
            for plan in plans
        }

    async def _fetch_status_map(
        self,
        table_name: str,
        entity_ids: list[str | None],
    ) -> dict[str, str]:
        """Fetch status strings for a set of graph entities."""
        unique_ids = list(
            dict.fromkeys(entity_id for entity_id in entity_ids if entity_id)
        )
        if not unique_ids:
            return {}
        placeholders = ", ".join("?" * len(unique_ids))
        rows = await self.db.fetch_all(
            f"SELECT id, status FROM {table_name} WHERE id IN ({placeholders})",
            tuple(unique_ids),
        )
        return {
            row["id"]: str(row["status"])
            for row in rows
            if row.get("status") is not None
        }

    async def get_lifecycle_rollup_map(
        self,
        plans: list[Plan],
    ) -> dict[str, PlanLifecycleRollup]:
        """Derive plan lifecycle from the linked execution graph."""
        if not plans:
            return {}

        unique_task_ids = list(
            dict.fromkeys(task_id for plan in plans for task_id in plan.task_ids)
        )
        task_map = {
            task.id: task for task in await self._task_repo.get_by_ids(unique_task_ids)
        }
        scope_project_map = await self._plan_scope_project_map(plans)
        project_status_map = await self._fetch_status_map(
            "projects",
            [scope_project_map.get(plan.id) for plan in plans],
        )
        goal_status_map = await self._fetch_status_map(
            "goals",
            [plan.goal_id for plan in plans],
        )
        objective_status_map = await self._fetch_status_map(
            "objectives",
            [plan.objective_id for plan in plans],
        )

        rollups: dict[str, PlanLifecycleRollup] = {}
        for plan in plans:
            if plan.status == PlanStatus.ARCHIVED:
                rollups[plan.id] = PlanLifecycleRollup(
                    effective_status=PlanStatus.ARCHIVED,
                    terminal_reason="plan is already archived",
                )
                continue
            if plan.status == PlanStatus.COMPLETED:
                rollups[plan.id] = PlanLifecycleRollup(
                    effective_status=PlanStatus.COMPLETED,
                    terminal_reason="plan is already marked completed",
                )
                continue
            if plan.status == PlanStatus.DRAFT:
                rollups[plan.id] = PlanLifecycleRollup(
                    effective_status=PlanStatus.DRAFT
                )
                continue

            linked_tasks = [
                task_map[task_id] for task_id in plan.task_ids if task_id in task_map
            ]
            has_task_scope = bool(plan.task_ids)
            all_tasks_terminal = (
                has_task_scope
                and len(linked_tasks) == len(plan.task_ids)
                and all(task.status.is_terminal for task in linked_tasks)
            )

            if all_tasks_terminal:
                rollups[plan.id] = PlanLifecycleRollup(
                    effective_status=PlanStatus.COMPLETED,
                    terminal_reason="all linked tasks are already terminal",
                )
                continue

            scope_project_id = scope_project_map.get(plan.id)
            objective_status = (
                objective_status_map.get(plan.objective_id)
                if plan.objective_id
                else None
            )
            goal_status = goal_status_map.get(plan.goal_id) if plan.goal_id else None
            project_status = (
                project_status_map.get(scope_project_id) if scope_project_id else None
            )

            if objective_status in {
                GoalStatus.COMPLETED.value,
                GoalStatus.ARCHIVED.value,
            }:
                rollups[plan.id] = PlanLifecycleRollup(
                    effective_status=PlanStatus.COMPLETED,
                    terminal_reason="linked objective is already terminal",
                )
                continue

            if goal_status in {
                GoalStatus.COMPLETED.value,
                GoalStatus.ARCHIVED.value,
            }:
                rollups[plan.id] = PlanLifecycleRollup(
                    effective_status=PlanStatus.COMPLETED,
                    terminal_reason="linked goal is already terminal",
                )
                continue

            if project_status in {
                ProjectStatus.COMPLETED.value,
                ProjectStatus.ARCHIVED.value,
            }:
                rollups[plan.id] = PlanLifecycleRollup(
                    effective_status=PlanStatus.COMPLETED,
                    terminal_reason="linked project is already terminal",
                )
                continue

            if has_task_scope:
                rollups[plan.id] = PlanLifecycleRollup(
                    effective_status=PlanStatus.ACTIVE
                )
                continue

            if objective_status in {
                GoalStatus.ACTIVE.value,
                GoalStatus.ON_HOLD.value,
            }:
                rollups[plan.id] = PlanLifecycleRollup(
                    effective_status=PlanStatus.ACTIVE
                )
                continue

            if goal_status in {
                GoalStatus.ACTIVE.value,
                GoalStatus.ON_HOLD.value,
            }:
                rollups[plan.id] = PlanLifecycleRollup(
                    effective_status=PlanStatus.ACTIVE
                )
                continue

            if project_status in {
                ProjectStatus.ACTIVE.value,
                ProjectStatus.ON_HOLD.value,
            }:
                rollups[plan.id] = PlanLifecycleRollup(
                    effective_status=PlanStatus.ACTIVE
                )
                continue

            if any(
                task.status
                in {
                    TaskStatus.IN_PROGRESS,
                    TaskStatus.IN_REVIEW,
                    TaskStatus.BLOCKED,
                }
                or task.current_progress_percent > 0
                for task in linked_tasks
            ):
                rollups[plan.id] = PlanLifecycleRollup(
                    effective_status=PlanStatus.ACTIVE
                )
                continue

            rollups[plan.id] = PlanLifecycleRollup(effective_status=plan.status)

        return rollups

    async def list_effective_plans(
        self,
        *,
        status: PlanStatus | None = None,
        project_id: str | None = None,
        product_id: str | None = None,
        goal_id: str | None = None,
        objective_id: str | None = None,
        task_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[
        QueryResult[Plan], dict[str, PlanLifecycleRollup], dict[str, PlanStatus]
    ]:
        """List plans using effective graph lifecycle status instead of stored rows."""
        batch_size = max(limit if limit > 0 else 100, 100)
        source_offset = 0
        all_items: list[Plan] = []

        while True:
            result = await self._plan_repo.list_plans(
                status=None,
                project_id=project_id,
                product_id=product_id,
                goal_id=goal_id,
                objective_id=objective_id,
                task_id=task_id,
                limit=batch_size,
                offset=source_offset,
            )
            all_items.extend(result.items)
            if not result.has_more:
                break
            source_offset += result.limit

        lifecycle_rollups = await self.get_lifecycle_rollup_map(all_items)
        stored_status_map = {plan.id: plan.status for plan in all_items}
        effective_items = [
            replace(
                plan,
                status=(
                    lifecycle_rollups.get(plan.id).effective_status
                    if lifecycle_rollups.get(plan.id) is not None
                    else plan.status
                ),
            )
            for plan in all_items
        ]
        if status is not None:
            effective_items = [
                plan for plan in effective_items if plan.status == status
            ]

        paged_items = (
            effective_items[offset:]
            if limit <= 0
            else effective_items[offset : offset + limit]
        )
        return (
            QueryResult(
                items=paged_items,
                total_count=len(effective_items),
                offset=offset,
                limit=limit,
            ),
            lifecycle_rollups,
            stored_status_map,
        )

    async def get_last_activity_map(
        self,
        plans: list[Plan],
    ) -> dict[str, datetime | None]:
        """Get last activity timestamps for plans with task/test job rollups."""
        if not plans:
            return {}

        plan_ids = [plan.id for plan in plans]
        auto_linked_task_ids = await self._auto_linked_task_ids_by_plan(plan_ids)
        rollup_task_ids_by_plan = self._task_rollup_ids_by_plan(
            plans,
            auto_linked_task_ids,
        )
        task_ids = [
            task_id
            for plan_task_ids in rollup_task_ids_by_plan.values()
            for task_id in plan_task_ids
        ]

        task_activity = await self._task_repo.get_last_activity_map(task_ids)
        from pms.services.goal_service import GoalService
        from pms.services.project_service import ProjectService

        plan_direct_activity = await self._plan_direct_activity_map(plans)
        scope_project_map = await self._plan_scope_project_map(plans)
        project_service = ProjectService(
            self.db,
            self.events,
            self.revisions,
            self.metrics,
        )
        scope_project_ids = [
            project_id
            for project_id in scope_project_map.values()
            if project_id is not None
        ]
        project_activity = await project_service.get_last_activity_map(
            scope_project_ids
        )
        direct_project_activity = await self._linked_entity_activity_map(
            "projects",
            "project",
            scope_project_ids,
        )
        goal_service = GoalService(
            self.db,
            self.events,
            self.revisions,
            self.metrics,
        )
        goal_ids = [plan.goal_id for plan in plans if plan.goal_id]
        goal_activity = await goal_service.get_last_activity_map(goal_ids)
        direct_goal_activity = await self._linked_entity_activity_map(
            "goals",
            "goal",
            goal_ids,
        )
        objective_ids = [plan.objective_id for plan in plans if plan.objective_id]
        objective_activity = await goal_service.get_objective_last_activity_map(
            objective_ids
        )
        direct_objective_activity = await self._linked_entity_activity_map(
            "objectives",
            "objective",
            objective_ids,
        )
        product_activity = await self._linked_entity_activity_map(
            "products",
            "product",
            [plan.product_id for plan in plans],
        )

        job_activity: dict[str, datetime | None] = {
            plan_id: None for plan_id in plan_ids
        }
        placeholders = ", ".join("?" * len(plan_ids))
        rows = await self.db.fetch_all(
            f"""
            SELECT plan_id, MAX(updated_at) as ts
            FROM plan_test_jobs
            WHERE plan_id IN ({placeholders})
              AND archived_at IS NULL
            GROUP BY plan_id
            """,
            tuple(plan_ids),
        )
        for row in rows:
            job_activity[row["plan_id"]] = self._parse_timestamp(row.get("ts"))

        plan_field_activity: dict[str, datetime | None] = {
            plan_id: None for plan_id in plan_ids
        }
        field_rows = await self.db.fetch_all(
            f"""
            SELECT entity_id, MAX(updated_at) as ts
            FROM custom_field_values
            WHERE entity_type = 'plan' AND entity_id IN ({placeholders})
            GROUP BY entity_id
            """,
            tuple(plan_ids),
        )
        for row in field_rows:
            plan_field_activity[row["entity_id"]] = self._parse_timestamp(row.get("ts"))

        plan_comment_activity: dict[str, datetime | None] = {
            plan_id: None for plan_id in plan_ids
        }
        comment_rows = await self.db.fetch_all(
            f"""
            SELECT entity_id, MAX(updated_at) as ts
            FROM comments
            WHERE entity_type = 'plan' AND entity_id IN ({placeholders})
            GROUP BY entity_id
            """,
            tuple(plan_ids),
        )
        for row in comment_rows:
            plan_comment_activity[row["entity_id"]] = self._parse_timestamp(
                row.get("ts")
            )

        plan_label_activity: dict[str, datetime | None] = {
            plan_id: None for plan_id in plan_ids
        }
        label_rows = await self.db.fetch_all(
            f"""
            SELECT entity_id,
                   MAX(COALESCE(archived_at, updated_at, created_at)) as ts
            FROM label_assignments
            WHERE entity_type = 'plan' AND entity_id IN ({placeholders})
            GROUP BY entity_id
            """,
            tuple(plan_ids),
        )
        for row in label_rows:
            plan_label_activity[row["entity_id"]] = self._parse_timestamp(row.get("ts"))

        plan_watcher_activity: dict[str, datetime | None] = {
            plan_id: None for plan_id in plan_ids
        }
        watcher_rows = await self.db.fetch_all(
            f"""
            SELECT entity_id,
                   MAX(COALESCE(archived_at, updated_at, created_at)) as ts
            FROM entity_watchers
            WHERE entity_type = 'plan' AND entity_id IN ({placeholders})
            GROUP BY entity_id
            """,
            tuple(plan_ids),
        )
        for row in watcher_rows:
            plan_watcher_activity[row["entity_id"]] = self._parse_timestamp(
                row.get("ts")
            )

        plan_activity: dict[str, datetime | None] = {}
        for plan in plans:
            task_ts = max_datetime(
                task_activity.get(task_id)
                for task_id in rollup_task_ids_by_plan.get(plan.id, ())
            )
            has_task_scope = bool(plan.task_ids)
            scoped_project_activity = (
                direct_project_activity if has_task_scope else project_activity
            )
            scoped_goal_activity = (
                direct_goal_activity if has_task_scope else goal_activity
            )
            scoped_objective_activity = (
                direct_objective_activity if has_task_scope else objective_activity
            )
            plan_activity[plan.id] = max_datetime(
                [
                    plan_direct_activity.get(plan.id),
                    task_ts,
                    job_activity.get(plan.id),
                    plan_field_activity.get(plan.id),
                    plan_comment_activity.get(plan.id),
                    plan_label_activity.get(plan.id),
                    plan_watcher_activity.get(plan.id),
                    scoped_project_activity.get(scope_project_map.get(plan.id))
                    if scope_project_map.get(plan.id)
                    else None,
                    product_activity.get(plan.product_id) if plan.product_id else None,
                    scoped_goal_activity.get(plan.goal_id) if plan.goal_id else None,
                    scoped_objective_activity.get(plan.objective_id)
                    if plan.objective_id
                    else None,
                ]
            )

        return plan_activity

    async def get_last_transition_map(
        self,
        plan_ids: list[str],
    ) -> dict[str, datetime | None]:
        """Get deep transition timestamps for plans and their linked graph."""
        unique_ids = list(dict.fromkeys(plan_id for plan_id in plan_ids if plan_id))
        if not unique_ids:
            return {}

        plans = await self._plan_repo.get_by_ids(unique_ids)
        transition_map: dict[str, datetime | None] = {
            plan_id: None for plan_id in unique_ids
        }
        if not plans:
            return transition_map

        from pms.repositories.state_transition_repository import (
            StateTransitionRepository,
        )
        from pms.services.goal_service import GoalService
        from pms.services.project_service import ProjectService

        state_repo = StateTransitionRepository(self.db)
        auto_linked_task_ids = await self._auto_linked_task_ids_by_plan(unique_ids)
        rollup_task_ids_by_plan = self._task_rollup_ids_by_plan(
            plans,
            auto_linked_task_ids,
        )
        task_ids = [
            task_id
            for plan_task_ids in rollup_task_ids_by_plan.values()
            for task_id in plan_task_ids
        ]
        task_transitions = await self._task_repo.get_last_transition_map(task_ids)
        scope_project_map = await self._plan_scope_project_map(plans)
        project_service = ProjectService(
            self.db,
            self.events,
            self.revisions,
            self.metrics,
        )
        scope_project_ids = [
            project_id
            for project_id in scope_project_map.values()
            if project_id is not None
        ]
        project_transitions = await project_service.get_last_transition_map(
            scope_project_ids
        )
        direct_project_transitions = await self._linked_entity_transition_map(
            "project",
            scope_project_ids,
        )
        goal_service = GoalService(
            self.db,
            self.events,
            self.revisions,
            self.metrics,
        )
        goal_ids = [plan.goal_id for plan in plans if plan.goal_id]
        goal_transitions = await goal_service.get_last_transition_map(goal_ids)
        direct_goal_transitions = await self._linked_entity_transition_map(
            "goal",
            goal_ids,
        )
        objective_ids = [plan.objective_id for plan in plans if plan.objective_id]
        objective_transitions = await goal_service.get_objective_last_transition_map(
            objective_ids
        )
        direct_objective_transitions = await self._linked_entity_transition_map(
            "objective",
            objective_ids,
        )
        plan_status = await state_repo.get_last_transition_map(
            "plan_status", unique_ids
        )
        product_status = await state_repo.get_last_transition_map(
            "product_status",
            [plan.product_id for plan in plans if plan.product_id],
        )

        for plan in plans:
            task_ts = max_datetime(
                task_transitions.get(task_id)
                for task_id in rollup_task_ids_by_plan.get(plan.id, ())
            )
            has_task_scope = bool(plan.task_ids)
            scoped_project_transitions = (
                direct_project_transitions if has_task_scope else project_transitions
            )
            scoped_goal_transitions = (
                direct_goal_transitions if has_task_scope else goal_transitions
            )
            scoped_objective_transitions = (
                direct_objective_transitions
                if has_task_scope
                else objective_transitions
            )
            transition_map[plan.id] = max_datetime(
                [
                    plan_status.get(plan.id),
                    task_ts,
                    scoped_project_transitions.get(scope_project_map.get(plan.id))
                    if scope_project_map.get(plan.id)
                    else None,
                    scoped_goal_transitions.get(plan.goal_id) if plan.goal_id else None,
                    scoped_objective_transitions.get(plan.objective_id)
                    if plan.objective_id
                    else None,
                    product_status.get(plan.product_id) if plan.product_id else None,
                ]
            )

        return transition_map
