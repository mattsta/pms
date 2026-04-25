"""Repository for actor identity nodes."""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pms.core.events import EventType
from pms.models import Actor, ActorKind, ActorStatus
from pms.models.base import now_utc
from pms.repositories.base import EventSourcedRepository, QueryResult

if TYPE_CHECKING:
    from pms.core.events import EventStore
    from pms.core.metrics import MetricsCollector
    from pms.core.revisions import RevisionStore
    from pms.db.connection import Database


class ActorRepository(EventSourcedRepository[Actor]):
    """Repository for actor entities."""

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
        return "actor"

    @property
    def table_name(self) -> str:
        return "actors"

    @property
    def archive_column(self) -> str | None:
        return "archived_at"

    def _model_from_row(self, row: dict[str, Any]) -> Actor:
        tags_raw = row.get("tags", "[]")
        tags = json.loads(tags_raw) if isinstance(tags_raw, str) else tags_raw
        metadata_raw = row.get("metadata", "{}")
        metadata = (
            json.loads(metadata_raw)
            if isinstance(metadata_raw, str)
            else (metadata_raw or {})
        )
        archived_at = row.get("archived_at")
        if isinstance(archived_at, str):
            archived_at = datetime.fromisoformat(archived_at)

        return Actor(
            id=row["id"],
            kind=ActorKind(row["kind"]),
            name=row["name"],
            handle=row["handle"],
            description=row.get("description"),
            status=ActorStatus(row["status"]),
            tags=tuple(tags),
            metadata=metadata,
            archived_at=archived_at,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_event_sequence=row.get("last_event_sequence", 0),
            last_revision_number=row.get("last_revision_number", 0),
        )

    def _row_from_model(self, model: Actor) -> dict[str, Any]:
        return {
            "id": model.id,
            "kind": model.kind.value,
            "name": model.name,
            "handle": model.handle,
            "normalized_handle": model.handle.casefold(),
            "description": model.description,
            "status": model.status.value,
            "tags": json.dumps(list(model.tags)),
            "metadata": json.dumps(model.metadata),
            "archived_at": model.archived_at.isoformat() if model.archived_at else None,
            "created_at": model.created_at.isoformat()
            if hasattr(model.created_at, "isoformat")
            else model.created_at,
            "updated_at": model.updated_at.isoformat()
            if hasattr(model.updated_at, "isoformat")
            else model.updated_at,
            "last_event_sequence": model.last_event_sequence,
            "last_revision_number": model.last_revision_number,
        }

    async def create(
        self,
        *,
        kind: ActorKind,
        name: str,
        handle: str,
        description: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        message: str | None = None,
    ) -> Actor:
        actor = Actor(
            kind=kind,
            name=name,
            handle=handle,
            description=description,
            tags=tuple(tags) if tags else (),
            metadata=metadata or {},
        )
        payload = {
            "kind": kind.value,
            "name": name,
            "handle": handle,
            "description": description,
            "tags": tags or [],
            "metadata": metadata or {},
        }
        return await self.save(
            actor,
            EventType.ACTOR_CREATED,
            payload,
            message=message or f"Created actor '{name}'",
        )

    async def update(
        self,
        actor_id: str,
        *,
        name: str | None = None,
        handle: str | None = None,
        description: str | None = None,
        status: ActorStatus | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        message: str | None = None,
    ) -> Actor | None:
        actor = await self.get_by_id(actor_id)
        if actor is None:
            return None

        changes: dict[str, Any] = {}
        if name is not None and name != actor.name:
            changes["name"] = (actor.name, name)
            actor.name = name
        if handle is not None and handle != actor.handle:
            changes["handle"] = (actor.handle, handle)
            actor.handle = handle
        if description is not None and description != actor.description:
            changes["description"] = (actor.description, description)
            actor.description = description
        if status is not None and status != actor.status:
            changes["status"] = (actor.status.value, status.value)
            actor.status = status
            actor.archived_at = now_utc() if status == ActorStatus.ARCHIVED else None
        if tags is not None and tuple(tags) != actor.tags:
            changes["tags"] = (list(actor.tags), tags)
            actor.tags = tuple(tags)
        if metadata is not None and metadata != actor.metadata:
            changes["metadata"] = (actor.metadata, metadata)
            actor.metadata = metadata

        if not changes:
            return actor

        actor.touch()
        return await self.save(
            actor,
            EventType.ACTOR_UPDATED,
            {"changes": changes},
            message=message or "Updated actor",
        )

    async def archive(self, actor_id: str, message: str | None = None) -> Actor | None:
        actor = await self.get_by_id(actor_id)
        if actor is None:
            return None
        old_status = actor.status
        actor.archive()
        return await self.save(
            actor,
            EventType.ACTOR_ARCHIVED,
            {"old_status": old_status.value, "new_status": actor.status.value},
            message=message or "Archived actor",
        )

    async def get_by_handle(self, handle: str) -> Actor | None:
        row = await self.db.fetch_one(
            """
            SELECT * FROM actors
            WHERE normalized_handle = ? AND archived_at IS NULL
            LIMIT 1
            """,
            (handle.casefold(),),
        )
        return self._model_from_row(row) if row else None

    async def list_filtered(
        self,
        *,
        kind: ActorKind | None = None,
        status: ActorStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Actor]:
        conditions: list[str] = []
        params: list[Any] = []
        if kind is not None:
            conditions.append("kind = ?")
            params.append(kind.value)
        if status is not None:
            conditions.append("status = ?")
            params.append(status.value)
        else:
            conditions.append("archived_at IS NULL")
        where_sql = " AND ".join(conditions)

        count_row = await self.db.fetch_one(
            f"SELECT COUNT(*) AS count FROM actors WHERE {where_sql}",
            tuple(params),
        )
        total = int(count_row["count"] or 0) if count_row else 0
        rows = await self.db.fetch_all(
            f"""
            SELECT * FROM actors
            WHERE {where_sql}
            ORDER BY kind, normalized_handle
            LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        )
        return QueryResult(
            items=[self._model_from_row(row) for row in rows],
            total_count=total,
            offset=offset,
            limit=limit,
        )

    async def _apply_events(self, events: list[Any]) -> Actor | None:
        """Rebuild actor state from events."""
        if not events:
            return None

        actor: Actor | None = None

        for event in events:
            payload = event.payload
            match event.event_type:
                case EventType.ACTOR_CREATED:
                    actor = Actor(
                        id=event.aggregate_id,
                        created_at=event.metadata.timestamp,
                        updated_at=event.metadata.timestamp,
                        kind=ActorKind(payload.get("kind", ActorKind.HUMAN.value)),
                        name=payload.get("name", ""),
                        handle=payload.get("handle", ""),
                        description=payload.get("description"),
                        status=ActorStatus.ACTIVE,
                        tags=tuple(payload.get("tags", [])),
                        metadata=payload.get("metadata", {}),
                    )
                case EventType.ACTOR_UPDATED if actor:
                    changes = payload.get("changes", {})
                    for field, (_, new_val) in changes.items():
                        match field:
                            case "name":
                                actor.name = new_val
                            case "handle":
                                actor.handle = new_val
                            case "description":
                                actor.description = new_val
                            case "status":
                                actor.status = ActorStatus(new_val)
                                if actor.status != ActorStatus.ARCHIVED:
                                    actor.archived_at = None
                            case "tags":
                                actor.tags = tuple(new_val)
                            case "metadata":
                                actor.metadata = new_val
                            case _:
                                pass
                    actor.updated_at = event.metadata.timestamp
                case EventType.ACTOR_ARCHIVED if actor:
                    actor.status = ActorStatus.ARCHIVED
                    actor.archived_at = event.metadata.timestamp
                    actor.updated_at = event.metadata.timestamp

        return actor
