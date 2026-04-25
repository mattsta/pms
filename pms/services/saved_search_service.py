"""Service for managing saved search queries and running them."""

from __future__ import annotations

import builtins
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, TypeVar

from pms.core.metrics import MetricsCollector
from pms.models.enums import Priority, TaskStatus
from pms.models.saved_search import SavedSearch
from pms.models.task import Task
from pms.repositories.base import QueryResult
from pms.repositories.saved_search_repository import SavedSearchRepository
from pms.services.task_service import TaskService

if TYPE_CHECKING:
    from pms.db.connection import Database

type JsonScalar = str | int | float | bool | datetime | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]

E = TypeVar("E", bound=Enum)


@dataclass
class SavedSearchRun:
    """Saved search with execution result."""

    saved_search: SavedSearch
    result: QueryResult[Task]


@dataclass
class SearchTaskParams:
    """Typed parameters for TaskService.search_tasks."""

    query: str | None = None
    project_id: str | None = None
    statuses: list[TaskStatus] | None = None
    priorities: list[Priority] | None = None
    assignee: str | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None
    updated_from: datetime | None = None
    updated_to: datetime | None = None
    due_from: datetime | None = None
    due_to: datetime | None = None
    tags: list[str] | None = None
    label_ids: list[str] | None = None
    label_category_ids: list[str] | None = None
    include_terminal: bool = False
    sort_by: str | None = None
    sort_dir: str | None = None
    limit: int = 100
    offset: int = 0


class SavedSearchService:
    """Service for saving and executing task search queries."""

    def __init__(
        self,
        repo: SavedSearchRepository,
        task_service: TaskService,
        metrics: MetricsCollector,
        db: Database | None = None,
    ) -> None:
        self._repo = repo
        self._task_service = task_service
        self.metrics = metrics
        self._db = db

    async def _resolve_owner_identity(
        self,
        owner: str | None,
    ) -> tuple[str | None, str | None]:
        """Resolve owner input to canonical actor-facing value plus actor id."""
        if owner is None:
            return None, None
        if self._db is None:
            return owner, None
        from pms.core.events import EventStore
        from pms.core.revisions import RevisionStore
        from pms.services.actor_service import ActorService

        actor_service = ActorService(
            self._db,
            EventStore(self._db),
            RevisionStore(self._db),
            self.metrics,
        )
        return await actor_service.canonicalize_actor_reference(owner)

    async def create(
        self,
        name: str,
        description: str | None = None,
        owner: str | None = None,
        scope_type: str = "global",
        scope_id: str | None = None,
        filters: JsonObject | None = None,
        sort_by: str | None = None,
        sort_dir: str | None = None,
    ) -> SavedSearch:
        canonical_owner, owner_id = await self._resolve_owner_identity(owner)
        async with self._repo.db.transaction():
            saved = await self._repo.create(
                name=name,
                description=description,
                owner=canonical_owner,
                owner_id=owner_id,
                scope_type=scope_type,
                scope_id=scope_id,
                filters=filters or {},
                sort_by=sort_by,
                sort_dir=sort_dir,
            )
            await self.metrics.record_counter(
                "saved_search.created",
                labels={"scope_type": saved.scope_type},
            )
            await self.metrics.flush()
        return saved

    async def update(
        self,
        search_id: str,
        name: str | None = None,
        description: str | None = None,
        owner: str | None = None,
        clear_owner: bool = False,
        scope_type: str | None = None,
        scope_id: str | None = None,
        filters: JsonObject | None = None,
        sort_by: str | None = None,
        sort_dir: str | None = None,
    ) -> SavedSearch | None:
        canonical_owner, owner_id = await self._resolve_owner_identity(owner)
        async with self._repo.db.transaction():
            saved = await self._repo.update(
                search_id=search_id,
                name=name,
                description=description,
                owner=canonical_owner,
                owner_id=owner_id,
                clear_owner=clear_owner,
                scope_type=scope_type,
                scope_id=scope_id,
                filters=filters,
                sort_by=sort_by,
                sort_dir=sort_dir,
            )
            if saved:
                await self.metrics.record_counter(
                    "saved_search.updated",
                    labels={"scope_type": saved.scope_type},
                )
                await self.metrics.flush()
        return saved

    async def delete(self, search_id: str) -> bool:
        async with self._repo.db.transaction():
            deleted = await self._repo.delete(search_id)
            if deleted:
                await self.metrics.record_counter("saved_search.deleted")
                await self.metrics.flush()
        return deleted

    async def restore(self, search_id: str) -> SavedSearch | None:
        async with self._repo.db.transaction():
            restored = await self._repo.restore(search_id)
            if restored:
                await self.metrics.record_counter("saved_search.restored")
                await self.metrics.flush()
        return restored

    async def get(self, search_id: str) -> SavedSearch | None:
        return await self._repo.get_by_id(search_id)

    async def get_by_name(
        self, name: str, *, include_archived: bool = False
    ) -> SavedSearch | None:
        return await self._repo.get_by_name(name, include_archived=include_archived)

    async def list(
        self,
        owner: str | None = None,
        scope_type: str | None = None,
        scope_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
        *,
        include_archived: bool = False,
    ) -> QueryResult[SavedSearch]:
        canonical_owner, owner_id = await self._resolve_owner_identity(owner)
        return await self._repo.list(
            owner=canonical_owner,
            owner_id=owner_id,
            scope_type=scope_type,
            scope_id=scope_id,
            limit=limit,
            offset=offset,
            include_archived=include_archived,
        )

    async def run(
        self,
        search_id: str,
        overrides: JsonObject | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> SavedSearchRun | None:
        saved = await self._repo.get_by_id(search_id)
        if not saved:
            return None

        filters = dict(saved.filters)
        if overrides:
            filters.update(overrides)

        query_params = self._build_query_params(filters)
        query_params.sort_by = self._as_str(filters.get("sort_by")) or saved.sort_by
        query_params.sort_dir = self._as_str(filters.get("sort_dir")) or saved.sort_dir

        if limit is not None:
            query_params.limit = limit
        if offset is not None:
            query_params.offset = offset

        result = await self._task_service.search_tasks(
            query=query_params.query,
            project_id=query_params.project_id,
            statuses=query_params.statuses,
            priorities=query_params.priorities,
            assignee=query_params.assignee,
            created_from=query_params.created_from,
            created_to=query_params.created_to,
            updated_from=query_params.updated_from,
            updated_to=query_params.updated_to,
            due_from=query_params.due_from,
            due_to=query_params.due_to,
            tags=query_params.tags,
            label_ids=query_params.label_ids,
            label_category_ids=query_params.label_category_ids,
            include_terminal=query_params.include_terminal,
            sort_by=query_params.sort_by,
            sort_dir=query_params.sort_dir,
            limit=query_params.limit,
            offset=query_params.offset,
        )

        await self.metrics.record_counter(
            "saved_search.run",
            labels={"scope_type": saved.scope_type},
        )
        await self.metrics.flush_best_effort(context="saved_search.run")

        return SavedSearchRun(saved_search=saved, result=result)

    def _build_query_params(self, filters: JsonObject) -> SearchTaskParams:
        status_value = filters.get("statuses")
        if status_value is None:
            status_value = filters.get("status")

        priority_value = filters.get("priorities")
        if priority_value is None:
            priority_value = filters.get("priority")

        label_ids = filters.get("label_ids")
        if label_ids is None:
            label_ids = filters.get("label_id")

        label_category_ids = filters.get("label_category_ids")
        if label_category_ids is None:
            label_category_ids = filters.get("label_category_id")

        return SearchTaskParams(
            query=self._as_str(filters.get("query")),
            project_id=self._as_str(filters.get("project_id")),
            statuses=self._parse_enum_list(status_value, TaskStatus),
            priorities=self._parse_enum_list(priority_value, Priority),
            assignee=self._as_str(filters.get("assignee")),
            created_from=self._parse_datetime(filters.get("created_from")),
            created_to=self._parse_datetime(filters.get("created_to")),
            updated_from=self._parse_datetime(filters.get("updated_from")),
            updated_to=self._parse_datetime(filters.get("updated_to")),
            due_from=self._parse_datetime(filters.get("due_from")),
            due_to=self._parse_datetime(filters.get("due_to")),
            tags=self._parse_list(filters.get("tags")),
            label_ids=self._parse_list(label_ids),
            label_category_ids=self._parse_list(label_category_ids),
            include_terminal=bool(filters.get("include_terminal", False)),
            limit=self._as_int(filters.get("limit"), 100),
            offset=self._as_int(filters.get("offset"), 0),
        )

    def _as_str(self, value: JsonValue | None) -> str | None:
        if isinstance(value, str):
            return value
        if value is None:
            return None
        return str(value)

    def _as_int(self, value: JsonValue | None, default: int) -> int:
        if value is None:
            return default
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                return default
        return default

    def _parse_datetime(self, value: JsonValue | None) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return None

    def _parse_list(self, value: JsonValue | None) -> builtins.list[str] | None:
        if value is None:
            return None
        if isinstance(value, list):
            return [str(item) for item in value if str(item)]
        if isinstance(value, str):
            items = [item.strip() for item in value.split(",") if item.strip()]
            return items or None
        return [str(value)]

    def _parse_enum_list(
        self, value: JsonValue | None, enum_cls: type[E]
    ) -> builtins.list[E] | None:
        items = self._parse_list(value)
        if not items:
            return None
        parsed: builtins.list[E] = []
        for item in items:
            try:
                parsed.append(enum_cls(str(item)))
            except ValueError:
                continue
        return parsed or None
