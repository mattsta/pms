"""Repository for actor membership edges."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from pms.core.events import EventType
from pms.models import ActorMembership, ActorMembershipRole
from pms.models.base import now_utc
from pms.repositories.base import EventSourcedRepository

if TYPE_CHECKING:
    from pms.core.events import EventStore
    from pms.core.metrics import MetricsCollector
    from pms.core.revisions import RevisionStore
    from pms.db.connection import Database


class ActorMembershipRepository(EventSourcedRepository[ActorMembership]):
    """Repository for actor membership edges."""

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
        return "actor_membership"

    @property
    def table_name(self) -> str:
        return "actor_memberships"

    @property
    def archive_column(self) -> str | None:
        return "archived_at"

    def _model_from_row(self, row: dict[str, Any]) -> ActorMembership:
        archived_at = row.get("archived_at")
        if isinstance(archived_at, str):
            archived_at = datetime.fromisoformat(archived_at)
        return ActorMembership(
            id=row["id"],
            parent_actor_id=row["parent_actor_id"],
            member_actor_id=row["member_actor_id"],
            role=ActorMembershipRole(row["role"]),
            archived_at=archived_at,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_event_sequence=row.get("last_event_sequence", 0),
            last_revision_number=row.get("last_revision_number", 0),
        )

    def _row_from_model(self, model: ActorMembership) -> dict[str, Any]:
        return {
            "id": model.id,
            "parent_actor_id": model.parent_actor_id,
            "member_actor_id": model.member_actor_id,
            "role": model.role.value,
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
        parent_actor_id: str,
        member_actor_id: str,
        role: ActorMembershipRole = ActorMembershipRole.MEMBER,
        message: str | None = None,
    ) -> ActorMembership:
        membership = ActorMembership(
            parent_actor_id=parent_actor_id,
            member_actor_id=member_actor_id,
            role=role,
        )
        return await self.save(
            membership,
            EventType.ACTOR_MEMBERSHIP_CREATED,
            {
                "parent_actor_id": parent_actor_id,
                "member_actor_id": member_actor_id,
                "role": role.value,
            },
            message=message or "Added actor membership",
        )

    async def list_by_parent(self, parent_actor_id: str) -> list[ActorMembership]:
        rows = await self.db.fetch_all(
            """
            SELECT * FROM actor_memberships
            WHERE parent_actor_id = ? AND archived_at IS NULL
            ORDER BY created_at
            """,
            (parent_actor_id,),
        )
        return [self._model_from_row(row) for row in rows]

    async def list_by_member(self, member_actor_id: str) -> list[ActorMembership]:
        rows = await self.db.fetch_all(
            """
            SELECT * FROM actor_memberships
            WHERE member_actor_id = ? AND archived_at IS NULL
            ORDER BY created_at
            """,
            (member_actor_id,),
        )
        return [self._model_from_row(row) for row in rows]

    async def archive(
        self,
        membership_id: str,
        message: str | None = None,
    ) -> ActorMembership | None:
        membership = await self.get_by_id(membership_id)
        if membership is None:
            return None
        membership.archived_at = now_utc()
        membership.touch()
        return await self.save(
            membership,
            EventType.ACTOR_MEMBERSHIP_ARCHIVED,
            {
                "parent_actor_id": membership.parent_actor_id,
                "member_actor_id": membership.member_actor_id,
                "role": membership.role.value,
            },
            message=message or "Archived actor membership",
        )

    async def _apply_events(self, events: list[Any]) -> ActorMembership | None:
        """Rebuild membership state from events."""
        if not events:
            return None

        membership: ActorMembership | None = None

        for event in events:
            payload = event.payload
            match event.event_type:
                case EventType.ACTOR_MEMBERSHIP_CREATED:
                    membership = ActorMembership(
                        id=event.aggregate_id,
                        created_at=event.metadata.timestamp,
                        updated_at=event.metadata.timestamp,
                        parent_actor_id=payload.get("parent_actor_id", ""),
                        member_actor_id=payload.get("member_actor_id", ""),
                        role=ActorMembershipRole(
                            payload.get("role", ActorMembershipRole.MEMBER.value)
                        ),
                    )
                case EventType.ACTOR_MEMBERSHIP_ARCHIVED if membership:
                    membership.archived_at = event.metadata.timestamp
                    membership.updated_at = event.metadata.timestamp

        return membership
