"""Repository for actor aliases."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from pms.core.events import EventType
from pms.models import ActorAlias
from pms.models.base import now_utc
from pms.repositories.base import EventSourcedRepository

if TYPE_CHECKING:
    from pms.core.events import EventStore
    from pms.core.metrics import MetricsCollector
    from pms.core.revisions import RevisionStore
    from pms.db.connection import Database


class ActorAliasRepository(EventSourcedRepository[ActorAlias]):
    """Repository for actor aliases."""

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
        return "actor_alias"

    @property
    def table_name(self) -> str:
        return "actor_aliases"

    @property
    def archive_column(self) -> str | None:
        return "archived_at"

    def _model_from_row(self, row: dict[str, Any]) -> ActorAlias:
        archived_at = row.get("archived_at")
        if isinstance(archived_at, str):
            archived_at = datetime.fromisoformat(archived_at)
        return ActorAlias(
            id=row["id"],
            actor_id=row["actor_id"],
            alias=row["alias"],
            normalized_alias=row["normalized_alias"],
            archived_at=archived_at,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_event_sequence=row.get("last_event_sequence", 0),
            last_revision_number=row.get("last_revision_number", 0),
        )

    def _row_from_model(self, model: ActorAlias) -> dict[str, Any]:
        return {
            "id": model.id,
            "actor_id": model.actor_id,
            "alias": model.alias,
            "normalized_alias": model.normalized_alias,
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
        actor_id: str,
        alias: str,
        normalized_alias: str,
        message: str | None = None,
    ) -> ActorAlias:
        model = ActorAlias(
            actor_id=actor_id,
            alias=alias,
            normalized_alias=normalized_alias,
        )
        return await self.save(
            model,
            EventType.ACTOR_ALIAS_CREATED,
            {
                "actor_id": actor_id,
                "alias": alias,
                "normalized_alias": normalized_alias,
            },
            message=message or f"Added actor alias '{alias}'",
        )

    async def get_by_alias(self, alias: str) -> ActorAlias | None:
        row = await self.db.fetch_one(
            """
            SELECT * FROM actor_aliases
            WHERE normalized_alias = ? AND archived_at IS NULL
            LIMIT 1
            """,
            (alias.casefold(),),
        )
        return self._model_from_row(row) if row else None

    async def list_by_actor(self, actor_id: str) -> list[ActorAlias]:
        rows = await self.db.fetch_all(
            """
            SELECT * FROM actor_aliases
            WHERE actor_id = ? AND archived_at IS NULL
            ORDER BY normalized_alias
            """,
            (actor_id,),
        )
        return [self._model_from_row(row) for row in rows]

    async def archive(
        self, alias_id: str, message: str | None = None
    ) -> ActorAlias | None:
        alias = await self.get_by_id(alias_id)
        if alias is None:
            return None
        alias.archived_at = now_utc()
        alias.touch()
        return await self.save(
            alias,
            EventType.ACTOR_ALIAS_ARCHIVED,
            {"alias": alias.alias},
            message=message or "Archived actor alias",
        )

    async def _apply_events(self, events: list[Any]) -> ActorAlias | None:
        """Rebuild alias state from events."""
        if not events:
            return None

        alias: ActorAlias | None = None

        for event in events:
            payload = event.payload
            match event.event_type:
                case EventType.ACTOR_ALIAS_CREATED:
                    alias = ActorAlias(
                        id=event.aggregate_id,
                        created_at=event.metadata.timestamp,
                        updated_at=event.metadata.timestamp,
                        actor_id=payload.get("actor_id", ""),
                        alias=payload.get("alias", ""),
                        normalized_alias=payload.get("normalized_alias", ""),
                    )
                case EventType.ACTOR_ALIAS_ARCHIVED if alias:
                    alias.archived_at = event.metadata.timestamp
                    alias.updated_at = event.metadata.timestamp

        return alias
