"""Plan repository with event sourcing."""

from __future__ import annotations

import json
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

from pms.core.events import DomainEvent, EventType
from pms.models import Plan, PlanFormat, PlanStatus
from pms.repositories.base import EventSourcedRepository, QueryResult

if TYPE_CHECKING:
    from pms.core.events import EventStore
    from pms.core.metrics import MetricsCollector
    from pms.core.revisions import RevisionStore
    from pms.db.connection import Database

_PLAN_PROJECTION_EVENT_TYPE: ContextVar[EventType | None] = ContextVar(
    "plan_projection_event_type",
    default=None,
)
_PLAN_PROJECTION_PAYLOAD: ContextVar[dict[str, Any] | None] = ContextVar(
    "plan_projection_payload",
    default=None,
)


class PlanRepository(EventSourcedRepository[Plan]):
    """Repository for plan artifacts with full event sourcing."""

    def __init__(
        self,
        db: Database,
        event_store: EventStore,
        revision_store: RevisionStore,
        metrics: MetricsCollector,
    ) -> None:
        super().__init__(db, event_store, revision_store, metrics)

    @property
    def entity_type(self) -> str:
        return "plan"

    @property
    def table_name(self) -> str:
        return "plans"

    @staticmethod
    def _parse_list(value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            return tuple(json.loads(value))
        return tuple(str(item) for item in value)

    def _model_from_row(self, row: dict[str, Any]) -> Plan:
        """Convert database row to Plan."""
        tags = self._parse_list(row.get("tags"))
        task_ids = self._parse_list(row.get("task_ids"))

        return Plan(
            id=row["id"],
            name=row["name"],
            description=row.get("description"),
            status=PlanStatus(row.get("status", PlanStatus.DRAFT.value)),
            format=PlanFormat(row.get("format", PlanFormat.JSON.value)),
            content=row.get("content", ""),
            product_id=row.get("product_id"),
            project_id=row.get("project_id"),
            goal_id=row.get("goal_id"),
            objective_id=row.get("objective_id"),
            task_ids=tuple(task_ids or ()),
            tags=tuple(tags or ()),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_event_sequence=row.get("last_event_sequence", 0),
            last_revision_number=row.get("last_revision_number", 0),
        )

    def _row_from_model(self, model: Plan) -> dict[str, Any]:
        """Convert Plan to database row."""
        return {
            "id": model.id,
            "name": model.name,
            "description": model.description,
            "status": model.status.value,
            "format": model.format.value,
            "content": model.content,
            "product_id": model.product_id,
            "project_id": model.project_id,
            "goal_id": model.goal_id,
            "objective_id": model.objective_id,
            "tags": json.dumps(list(model.tags)),
            "created_at": model.created_at.isoformat()
            if hasattr(model.created_at, "isoformat")
            else model.created_at,
            "updated_at": model.updated_at.isoformat()
            if hasattr(model.updated_at, "isoformat")
            else model.updated_at,
            "last_event_sequence": model.last_event_sequence,
            "last_revision_number": model.last_revision_number,
        }

    async def _hydrate_task_links(self, plans: list[Plan]) -> None:
        if not plans:
            return

        ids = [plan.id for plan in plans]
        placeholders = ", ".join("?" for _ in ids)
        rows = await self.db.fetch_all(
            f"""
            SELECT plan_id, task_id
            FROM plan_tasks
            WHERE plan_id IN ({placeholders})
            ORDER BY plan_id ASC, position ASC
            """,
            tuple(ids),
        )

        if not rows:
            return

        task_map: dict[str, list[str]] = {plan.id: [] for plan in plans}
        for row in rows:
            task_map.setdefault(str(row["plan_id"]), []).append(str(row["task_id"]))

        for plan in plans:
            if task_map.get(plan.id):
                plan.task_ids = tuple(task_map[plan.id])

    async def get_by_ids(self, plan_ids: list[str]) -> list[Plan]:
        """Get plans by ids preserving input order."""
        unique_ids = list(dict.fromkeys(plan_id for plan_id in plan_ids if plan_id))
        if not unique_ids:
            return []

        placeholders = ", ".join("?" * len(unique_ids))
        rows = await self.db.fetch_all(
            f"SELECT * FROM {self.table_name} WHERE id IN ({placeholders})",
            tuple(unique_ids),
        )
        plans = [self._model_from_row(row) for row in rows]
        await self._hydrate_task_links(plans)
        plan_map = {plan.id: plan for plan in plans}
        return [plan_map[plan_id] for plan_id in unique_ids if plan_id in plan_map]

    async def _sync_task_links(self, plan: Plan) -> None:
        await self.db.execute("DELETE FROM plan_tasks WHERE plan_id = ?", (plan.id,))
        if not plan.task_ids:
            return
        await self.db.execute_many(
            """
            INSERT INTO plan_tasks (plan_id, task_id, position)
            VALUES (?, ?, ?)
            """,
            [
                (plan.id, task_id, position)
                for position, task_id in enumerate(plan.task_ids)
            ],
        )

    @staticmethod
    def _preserve_unchanged_fields(
        plan: Plan,
        current: Plan,
        changed_fields: set[str],
    ) -> None:
        """Keep fields owned by a newer projection when this event did not change them."""
        for field in (
            "name",
            "description",
            "status",
            "format",
            "content",
            "product_id",
            "project_id",
            "goal_id",
            "objective_id",
            "task_ids",
            "tags",
        ):
            if field in changed_fields:
                continue
            setattr(plan, field, getattr(current, field))

        if current.created_at and current.created_at != plan.created_at:
            plan.created_at = current.created_at

    async def save(
        self,
        model: Plan,
        event_type: EventType,
        payload: dict[str, Any],
        message: str | None = None,
    ) -> Plan:
        """Persist a plan while exposing the event type to projection merge logic."""
        event_type_token = _PLAN_PROJECTION_EVENT_TYPE.set(event_type)
        payload_token = _PLAN_PROJECTION_PAYLOAD.set(payload)
        try:
            return await super().save(model, event_type, payload, message)
        finally:
            _PLAN_PROJECTION_PAYLOAD.reset(payload_token)
            _PLAN_PROJECTION_EVENT_TYPE.reset(event_type_token)

    async def _update_projection(self, model: Plan, is_create: bool) -> None:
        """Update plan projection while preserving newer fields not owned by this event."""
        if not is_create:
            current = await self.get_by_id(model.id)
            event_type = _PLAN_PROJECTION_EVENT_TYPE.get()
            payload = _PLAN_PROJECTION_PAYLOAD.get() or {}

            if current is not None and event_type == EventType.PLAN_UPDATED:
                changes = payload.get("changes", {})
                changed_fields = set(changes.keys())
                self._preserve_unchanged_fields(model, current, changed_fields)

        await super()._update_projection(model, is_create)
        await self._sync_task_links(model)

    async def create(
        self,
        name: str,
        description: str | None,
        status: PlanStatus,
        format: PlanFormat,
        content: str,
        product_id: str | None = None,
        project_id: str | None = None,
        goal_id: str | None = None,
        objective_id: str | None = None,
        task_ids: list[str] | None = None,
        tags: list[str] | None = None,
        message: str | None = None,
    ) -> Plan:
        """Create a new plan."""
        plan = Plan(
            name=name,
            description=description,
            status=status,
            format=format,
            content=content,
            product_id=product_id,
            project_id=project_id,
            goal_id=goal_id,
            objective_id=objective_id,
            task_ids=tuple(task_ids) if task_ids else (),
            tags=tuple(tags) if tags else (),
        )

        payload = {
            "name": name,
            "description": description,
            "status": status.value,
            "format": format.value,
            "content": content,
            "product_id": product_id,
            "project_id": project_id,
            "goal_id": goal_id,
            "objective_id": objective_id,
            "task_ids": task_ids or [],
            "tags": tags or [],
        }

        return await self.save(
            plan,
            EventType.PLAN_CREATED,
            payload,
            message=message or f"Created plan '{name}'",
        )

    async def update(
        self,
        plan_id: str,
        name: str | None = None,
        description: str | None = None,
        status: PlanStatus | None = None,
        format: PlanFormat | None = None,
        content: str | None = None,
        product_id: str | None = None,
        project_id: str | None = None,
        goal_id: str | None = None,
        objective_id: str | None = None,
        task_ids: list[str] | None = None,
        tags: list[str] | None = None,
        message: str | None = None,
    ) -> Plan | None:
        """Update a plan."""
        plan = await self.get_by_id(plan_id)
        if plan is None:
            return None

        changes: dict[str, Any] = {}

        if name is not None and name != plan.name:
            changes["name"] = (plan.name, name)
            plan.name = name
        if description is not None and description != plan.description:
            changes["description"] = (plan.description, description)
            plan.description = description
        if status is not None and status != plan.status:
            changes["status"] = (plan.status.value, status.value)
            plan.status = status
        if format is not None and format != plan.format:
            changes["format"] = (plan.format.value, format.value)
            plan.format = format
        if content is not None and content != plan.content:
            changes["content"] = (plan.content, content)
            plan.content = content
        if product_id is not None and product_id != plan.product_id:
            changes["product_id"] = (plan.product_id, product_id)
            plan.product_id = product_id
        if project_id is not None and project_id != plan.project_id:
            changes["project_id"] = (plan.project_id, project_id)
            plan.project_id = project_id
        if goal_id is not None and goal_id != plan.goal_id:
            changes["goal_id"] = (plan.goal_id, goal_id)
            plan.goal_id = goal_id
        if objective_id is not None and objective_id != plan.objective_id:
            changes["objective_id"] = (plan.objective_id, objective_id)
            plan.objective_id = objective_id
        if task_ids is not None and tuple(task_ids) != plan.task_ids:
            changes["task_ids"] = (list(plan.task_ids), task_ids)
            plan.task_ids = tuple(task_ids)
        if tags is not None and tuple(tags) != plan.tags:
            changes["tags"] = (list(plan.tags), tags)
            plan.tags = tuple(tags)

        if not changes:
            return plan

        plan.touch()

        return await self.save(
            plan,
            EventType.PLAN_UPDATED,
            {"changes": changes},
            message=message,
        )

    async def get_by_id(self, entity_id: str) -> Plan | None:
        plan = await super().get_by_id(entity_id)
        if plan is None:
            return None
        await self._hydrate_task_links([plan])
        return plan

    async def get_by_name(self, name: str) -> Plan | None:
        """Get plan by name."""
        row = await self.db.fetch_one(
            "SELECT * FROM plans WHERE name = ?",
            (name,),
        )
        if row is None:
            return None
        plan = self._model_from_row(row)
        await self._hydrate_task_links([plan])
        return plan

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
        where = ["1=1"]
        params: list[Any] = []

        if status:
            where.append("status = ?")
            params.append(status.value)
        if project_id:
            where.append("project_id = ?")
            params.append(project_id)
        if product_id:
            where.append("product_id = ?")
            params.append(product_id)
        if goal_id:
            where.append("goal_id = ?")
            params.append(goal_id)
        if objective_id:
            where.append("objective_id = ?")
            params.append(objective_id)
        if task_id:
            where.append(
                "EXISTS (SELECT 1 FROM plan_tasks WHERE plan_tasks.plan_id = plans.id AND plan_tasks.task_id = ?)"
            )
            params.append(task_id)

        where_sql = " AND ".join(where)
        count_result = await self.db.fetch_one(
            f"SELECT COUNT(*) as count FROM plans WHERE {where_sql}",
            tuple(params),
        )
        total = count_result["count"] if count_result else 0

        rows = await self.db.fetch_all(
            f"""
            SELECT * FROM plans
            WHERE {where_sql}
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
            """,
            tuple(params + [limit, offset]),
        )

        plans = [self._model_from_row(row) for row in rows]
        await self._hydrate_task_links(plans)

        return QueryResult(
            items=plans,
            total_count=total,
            offset=offset,
            limit=limit,
        )

    async def list_by_task_id(self, task_id: str) -> list[Plan]:
        """List plans that reference a specific task ID."""
        rows = await self.db.fetch_all(
            """
            SELECT DISTINCT p.*
            FROM plans p
            JOIN plan_tasks pt
              ON pt.plan_id = p.id
            WHERE pt.task_id = ?
            ORDER BY p.updated_at DESC
            """,
            (task_id,),
        )
        plans = [self._model_from_row(row) for row in rows]
        await self._hydrate_task_links(plans)
        return plans

    async def _apply_events(
        self, events: list[DomainEvent[dict[str, Any]]]
    ) -> Plan | None:
        """Rebuild plan state from events."""
        if not events:
            return None

        plan = None

        for event in events:
            match event.event_type:
                case EventType.PLAN_CREATED:
                    payload = event.payload
                    plan = Plan(
                        id=event.aggregate_id,
                        name=payload.get("name", ""),
                        description=payload.get("description"),
                        status=PlanStatus(
                            payload.get("status", PlanStatus.DRAFT.value)
                        ),
                        format=PlanFormat(payload.get("format", PlanFormat.JSON.value)),
                        content=payload.get("content", ""),
                        product_id=payload.get("product_id"),
                        project_id=payload.get("project_id"),
                        goal_id=payload.get("goal_id"),
                        objective_id=payload.get("objective_id"),
                        task_ids=tuple(payload.get("task_ids", [])),
                        tags=tuple(payload.get("tags", [])),
                    )
                case EventType.PLAN_UPDATED if plan:
                    payload = event.payload
                    changes = payload.get("changes", {})
                    for field, (_, new_val) in changes.items():
                        match field:
                            case "name":
                                plan.name = new_val
                            case "description":
                                plan.description = new_val
                            case "status":
                                plan.status = PlanStatus(new_val)
                            case "format":
                                plan.format = PlanFormat(new_val)
                            case "content":
                                plan.content = new_val
                            case "product_id":
                                plan.product_id = new_val
                            case "project_id":
                                plan.project_id = new_val
                            case "goal_id":
                                plan.goal_id = new_val
                            case "objective_id":
                                plan.objective_id = new_val
                            case "task_ids":
                                plan.task_ids = tuple(new_val)
                            case "tags":
                                plan.tags = tuple(new_val)
                            case _:
                                pass
                case EventType.PLAN_ARCHIVED if plan:
                    plan.status = PlanStatus.ARCHIVED

        return plan
