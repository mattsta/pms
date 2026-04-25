"""Repository for saved search queries."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from pms.core.events import DomainEvent, EventStore, EventType
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.models.saved_search import SavedSearch
from pms.repositories.base import EventSourcedRepository, QueryResult

if TYPE_CHECKING:
    from pms.db.connection import Database

SavedSearchEvents = list[DomainEvent[dict[str, Any]]]


class SavedSearchRepository(EventSourcedRepository[SavedSearch]):
    """Repository for saved search queries."""

    def __init__(self, db: Database) -> None:
        super().__init__(
            db,
            EventStore(db),
            RevisionStore(db),
            MetricsCollector(db),
        )

    @property
    def entity_type(self) -> str:
        return "saved_search"

    @property
    def table_name(self) -> str:
        return "saved_searches"

    @property
    def archive_column(self) -> str | None:
        return "archived_at"

    async def create(
        self,
        name: str,
        description: str | None = None,
        owner: str | None = None,
        owner_id: str | None = None,
        scope_type: str = "global",
        scope_id: str | None = None,
        filters: dict[str, Any] | None = None,
        sort_by: str | None = None,
        sort_dir: str | None = None,
    ) -> SavedSearch:
        saved = SavedSearch(
            name=name,
            description=description,
            owner=owner,
            owner_id=owner_id,
            scope_type=scope_type,
            scope_id=scope_id,
            filters=filters or {},
            sort_by=sort_by,
            sort_dir=sort_dir or "desc",
        )
        payload = {
            "name": name,
            "description": description,
            "owner": owner,
            "owner_id": owner_id,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "filters": saved.filters,
            "sort_by": sort_by,
            "sort_dir": sort_dir or "desc",
        }

        return await self.save(
            saved,
            EventType.SAVED_SEARCH_CREATED,
            payload,
            message=f"Created saved search '{name}'",
        )

    async def update(
        self,
        search_id: str,
        name: str | None = None,
        description: str | None = None,
        owner: str | None = None,
        owner_id: str | None = None,
        clear_owner: bool = False,
        scope_type: str | None = None,
        scope_id: str | None = None,
        filters: dict[str, Any] | None = None,
        sort_by: str | None = None,
        sort_dir: str | None = None,
    ) -> SavedSearch | None:
        existing = await self.get_by_id(search_id)
        if not existing:
            return None

        updated = SavedSearch(
            id=existing.id,
            name=name if name is not None else existing.name,
            description=description
            if description is not None
            else existing.description,
            owner=(
                None if clear_owner else owner if owner is not None else existing.owner
            ),
            owner_id=(
                None
                if clear_owner
                else owner_id
                if owner is not None or owner_id is not None
                else existing.owner_id
            ),
            scope_type=scope_type if scope_type is not None else existing.scope_type,
            scope_id=scope_id if scope_id is not None else existing.scope_id,
            filters=filters if filters is not None else existing.filters,
            sort_by=sort_by if sort_by is not None else existing.sort_by,
            sort_dir=sort_dir if sort_dir is not None else existing.sort_dir,
            created_at=existing.created_at,
            updated_at=datetime.now(UTC),
            last_event_sequence=existing.last_event_sequence,
            last_revision_number=existing.last_revision_number,
        )

        changes: dict[str, Any] = {}
        if name is not None and name != existing.name:
            changes["name"] = (existing.name, name)
        if description is not None and description != existing.description:
            changes["description"] = (existing.description, description)
        if clear_owner:
            if existing.owner is not None or existing.owner_id is not None:
                changes["owner"] = (existing.owner, None)
                changes["owner_id"] = (existing.owner_id, None)
        elif owner is not None and (
            owner != existing.owner or owner_id != existing.owner_id
        ):
            changes["owner"] = (existing.owner, owner)
            changes["owner_id"] = (existing.owner_id, owner_id)
        if scope_type is not None and scope_type != existing.scope_type:
            changes["scope_type"] = (existing.scope_type, scope_type)
        if scope_id is not None and scope_id != existing.scope_id:
            changes["scope_id"] = (existing.scope_id, scope_id)
        if filters is not None and filters != existing.filters:
            changes["filters"] = (existing.filters, filters)
        if sort_by is not None and sort_by != existing.sort_by:
            changes["sort_by"] = (existing.sort_by, sort_by)
        if sort_dir is not None and sort_dir != existing.sort_dir:
            changes["sort_dir"] = (existing.sort_dir, sort_dir)

        if not changes:
            return existing

        return await self.save(
            updated,
            EventType.SAVED_SEARCH_UPDATED,
            {"changes": changes},
            message="Updated saved search",
        )

    async def delete(
        self,
        search_id: str,
        soft_delete: bool = True,
        message: str | None = None,
    ) -> bool:
        return await super().delete(
            search_id,
            soft_delete=soft_delete,
            message=message or "Deleted saved search",
        )

    async def get_by_id(self, search_id: str) -> SavedSearch | None:
        row = await self.db.fetch_one(
            "SELECT * FROM saved_searches WHERE id = ? AND archived_at IS NULL",
            (search_id,),
        )
        return self._row_to_model(row) if row else None

    async def get_by_name(
        self, name: str, *, include_archived: bool = False
    ) -> SavedSearch | None:
        where_sql = "name = ?"
        if not include_archived:
            where_sql += " AND archived_at IS NULL"
        row = await self.db.fetch_one(
            f"""
            SELECT * FROM saved_searches
            WHERE {where_sql}
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (name,),
        )
        return self._row_to_model(row) if row else None

    async def list(
        self,
        owner: str | None = None,
        owner_id: str | None = None,
        scope_type: str | None = None,
        scope_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
        *,
        include_archived: bool = False,
    ) -> QueryResult[SavedSearch]:
        where_clauses = []
        params: list[Any] = []

        if owner and owner_id:
            where_clauses.append("(owner = ? OR owner_id = ?)")
            params.extend([owner, owner_id])
        elif owner:
            where_clauses.append("owner = ?")
            params.append(owner)
        elif owner_id:
            where_clauses.append("owner_id = ?")
            params.append(owner_id)
        if scope_type:
            where_clauses.append("scope_type = ?")
            params.append(scope_type)
        if scope_id:
            where_clauses.append("scope_id = ?")
            params.append(scope_id)

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        if not include_archived:
            where_sql = f"{where_sql} AND archived_at IS NULL"

        count_row = await self.db.fetch_one(
            f"SELECT COUNT(*) as count FROM saved_searches WHERE {where_sql}",
            tuple(params),
        )
        total = count_row["count"] if count_row else 0

        rows = await self.db.fetch_all(
            f"""
            SELECT * FROM saved_searches
            WHERE {where_sql}
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        )

        return QueryResult(
            items=[self._row_to_model(row) for row in rows],
            total_count=total,
            offset=offset,
            limit=limit,
        )

    def _row_to_model(self, row: dict[str, Any]) -> SavedSearch:
        return SavedSearch(
            id=row["id"],
            name=row["name"],
            description=row.get("description"),
            owner=row.get("owner"),
            owner_id=row.get("owner_id"),
            scope_type=row.get("scope_type") or "global",
            scope_id=row.get("scope_id"),
            filters=json.loads(row.get("filters") or "{}"),
            sort_by=row.get("sort_by"),
            sort_dir=row.get("sort_dir") or "desc",
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            archived_at=datetime.fromisoformat(row["archived_at"])
            if row.get("archived_at")
            else None,
            last_event_sequence=row.get("last_event_sequence", 0),
            last_revision_number=row.get("last_revision_number", 0),
        )

    def _model_from_row(self, row: dict[str, Any]) -> SavedSearch:
        return self._row_to_model(row)

    def _row_from_model(self, model: SavedSearch) -> dict[str, Any]:
        return {
            "id": model.id,
            "name": model.name,
            "description": model.description,
            "owner": model.owner,
            "owner_id": model.owner_id,
            "scope_type": model.scope_type,
            "scope_id": model.scope_id,
            "filters": json.dumps(model.filters),
            "sort_by": model.sort_by,
            "sort_dir": model.sort_dir,
            "created_at": model.created_at.isoformat(),
            "updated_at": model.updated_at.isoformat(),
            "archived_at": model.archived_at.isoformat() if model.archived_at else None,
            "last_event_sequence": model.last_event_sequence,
            "last_revision_number": model.last_revision_number,
        }

    async def _apply_events(self, events: SavedSearchEvents) -> SavedSearch | None:
        if not events:
            return None

        saved: SavedSearch | None = None
        for event in events:
            match event.event_type:
                case EventType.SAVED_SEARCH_CREATED:
                    payload = event.payload
                    saved = SavedSearch(
                        id=event.aggregate_id,
                        name=payload.get("name", ""),
                        description=payload.get("description"),
                        owner=payload.get("owner"),
                        owner_id=payload.get("owner_id"),
                        scope_type=payload.get("scope_type", "global"),
                        scope_id=payload.get("scope_id"),
                        filters=payload.get("filters", {}) or {},
                        sort_by=payload.get("sort_by"),
                        sort_dir=payload.get("sort_dir") or "desc",
                    )
                case EventType.SAVED_SEARCH_UPDATED if saved:
                    changes = event.payload.get("changes", {})
                    for field, (old_val, new_val) in changes.items():
                        match field:
                            case "name":
                                saved.name = new_val
                            case "description":
                                saved.description = new_val
                            case "owner":
                                saved.owner = new_val
                            case "owner_id":
                                saved.owner_id = new_val
                            case "scope_type":
                                saved.scope_type = new_val
                            case "scope_id":
                                saved.scope_id = new_val
                            case "filters":
                                saved.filters = new_val or {}
                            case "sort_by":
                                saved.sort_by = new_val
                            case "sort_dir":
                                saved.sort_dir = new_val
                case EventType.SAVED_SEARCH_DELETED:
                    saved = None
                case EventType.SAVED_SEARCH_RESTORED:
                    payload = event.payload
                    content = payload.get("content") or {}
                    content.setdefault("id", event.aggregate_id)
                    saved = SavedSearch.from_dict(content)

        return saved
