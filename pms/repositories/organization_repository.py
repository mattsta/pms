"""Organization repository with event sourcing."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from pms.core.events import EventType
from pms.models import Organization, OrganizationStatus
from pms.repositories.base import EventSourcedRepository, QueryResult

if TYPE_CHECKING:
    from pms.core.events import EventStore
    from pms.core.metrics import MetricsCollector
    from pms.core.revisions import RevisionStore
    from pms.db.connection import Database


class OrganizationRepository(EventSourcedRepository[Organization]):
    """Repository for Organization entities."""

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
        return "organization"

    @property
    def table_name(self) -> str:
        return "organizations"

    @staticmethod
    def _parse_list(value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            return tuple(json.loads(value))
        return tuple(str(item) for item in value)

    def _model_from_row(self, row: dict[str, Any]) -> Organization:
        members = self._parse_list(row.get("members"))
        member_ids = self._parse_list(row.get("member_ids"))
        tags = self._parse_list(row.get("tags"))

        return Organization(
            id=row["id"],
            name=row["name"],
            description=row.get("description"),
            status=OrganizationStatus(row["status"]),
            owner=row.get("owner"),
            owner_id=row.get("owner_id"),
            members=tuple(members),
            member_ids=tuple(member_ids),
            tags=tuple(tags),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_event_sequence=row.get("last_event_sequence", 0),
            last_revision_number=row.get("last_revision_number", 0),
        )

    def _row_from_model(self, model: Organization) -> dict[str, Any]:
        return {
            "id": model.id,
            "name": model.name,
            "description": model.description,
            "status": model.status.value,
            "owner": model.owner,
            "owner_id": model.owner_id,
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

    async def _hydrate_members(self, organizations: list[Organization]) -> None:
        if not organizations:
            return

        ids = [organization.id for organization in organizations]
        placeholders = ", ".join("?" for _ in ids)
        rows = await self.db.fetch_all(
            f"""
            SELECT
                om.organization_id,
                om.actor_id,
                COALESCE(a.handle, a.name, a.id) AS actor_ref
            FROM organization_members om
            LEFT JOIN actors a ON a.id = om.actor_id
            WHERE om.organization_id IN ({placeholders})
            ORDER BY om.organization_id ASC, om.position ASC
            """,
            tuple(ids),
        )

        if not rows:
            return

        member_map: dict[str, list[str]] = {
            organization.id: [] for organization in organizations
        }
        member_id_map: dict[str, list[str]] = {
            organization.id: [] for organization in organizations
        }
        for row in rows:
            organization_id = str(row["organization_id"])
            member_id_map.setdefault(organization_id, []).append(str(row["actor_id"]))
            actor_ref = row.get("actor_ref")
            member_map.setdefault(organization_id, []).append(
                str(actor_ref) if actor_ref else str(row["actor_id"])
            )

        for organization in organizations:
            if member_id_map.get(organization.id):
                organization.member_ids = tuple(member_id_map[organization.id])
                organization.members = tuple(member_map[organization.id])

    async def _sync_members(self, organization: Organization) -> None:
        await self.db.execute(
            "DELETE FROM organization_members WHERE organization_id = ?",
            (organization.id,),
        )
        if not organization.member_ids:
            return
        await self.db.execute_many(
            """
            INSERT INTO organization_members (organization_id, actor_id, position)
            VALUES (?, ?, ?)
            """,
            [
                (organization.id, actor_id, position)
                for position, actor_id in enumerate(organization.member_ids)
            ],
        )

    async def _update_projection(self, model: Organization, is_create: bool) -> None:
        await super()._update_projection(model, is_create)
        await self._sync_members(model)

    async def create(
        self,
        name: str,
        description: str | None = None,
        owner: str | None = None,
        owner_id: str | None = None,
        members: list[str] | None = None,
        member_ids: list[str] | None = None,
        tags: list[str] | None = None,
        message: str | None = None,
    ) -> Organization:
        """Create a new organization."""
        org = Organization(
            name=name,
            description=description,
            owner=owner,
            owner_id=owner_id,
            members=tuple(members) if members else (),
            member_ids=tuple(member_ids) if member_ids else (),
            tags=tuple(tags) if tags else (),
        )

        payload = {
            "name": name,
            "description": description,
            "owner": owner,
            "owner_id": owner_id,
            "members": members or [],
            "member_ids": member_ids or [],
            "tags": tags or [],
        }

        return await self.save(
            org,
            EventType.ORGANIZATION_CREATED,
            payload,
            message=message or f"Created organization '{name}'",
        )

    async def update(
        self,
        org_id: str,
        name: str | None = None,
        description: str | None = None,
        status: OrganizationStatus | None = None,
        owner: str | None = None,
        owner_id: str | None = None,
        clear_owner: bool = False,
        members: list[str] | None = None,
        member_ids: list[str] | None = None,
        clear_members: bool = False,
        tags: list[str] | None = None,
        message: str | None = None,
    ) -> Organization | None:
        """Update an organization."""
        org = await self.get_by_id(org_id)
        if org is None:
            return None

        changes: dict[str, Any] = {}
        if name is not None and name != org.name:
            changes["name"] = (org.name, name)
            org.name = name
        if description is not None and description != org.description:
            changes["description"] = (org.description, description)
            org.description = description
        if status is not None and status != org.status:
            changes["status"] = (org.status.value, status.value)
            org.status = status
        if clear_owner:
            if org.owner is not None or org.owner_id is not None:
                changes["owner"] = (org.owner, None)
                changes["owner_id"] = (org.owner_id, None)
                org.owner = None
                org.owner_id = None
        elif owner is not None and (owner != org.owner or owner_id != org.owner_id):
            changes["owner"] = (org.owner, owner)
            changes["owner_id"] = (org.owner_id, owner_id)
            org.owner = owner
            org.owner_id = owner_id
        if clear_members:
            if org.members or org.member_ids:
                changes["members"] = (list(org.members), [])
                changes["member_ids"] = (list(org.member_ids), [])
                org.members = ()
                org.member_ids = ()
        elif members is not None and (
            tuple(members) != org.members or tuple(member_ids or []) != org.member_ids
        ):
            changes["members"] = (list(org.members), members)
            changes["member_ids"] = (
                list(org.member_ids),
                member_ids or [],
            )
            org.members = tuple(members)
            org.member_ids = tuple(member_ids or [])
        if tags is not None and tuple(tags) != org.tags:
            changes["tags"] = (list(org.tags), tags)
            org.tags = tuple(tags)

        if not changes:
            return org

        org.touch()

        return await self.save(
            org,
            EventType.ORGANIZATION_UPDATED,
            {"changes": changes},
            message=message,
        )

    async def archive(
        self, org_id: str, message: str | None = None
    ) -> Organization | None:
        """Archive an organization."""
        org = await self.get_by_id(org_id)
        if org is None:
            return None

        old_status = org.status
        org.archive()

        return await self.save(
            org,
            EventType.ORGANIZATION_ARCHIVED,
            {"old_status": old_status.value, "new_status": org.status.value},
            message=message or "Organization archived",
        )

    async def get_by_id(self, entity_id: str) -> Organization | None:
        organization = await super().get_by_id(entity_id)
        if organization is None:
            return None
        await self._hydrate_members([organization])
        return organization

    async def get_by_name(self, name: str) -> Organization | None:
        """Get an organization by name."""
        row = await self.db.fetch_one(
            "SELECT * FROM organizations WHERE name = ?",
            (name,),
        )
        if row is None:
            return None
        organization = self._model_from_row(row)
        await self._hydrate_members([organization])
        return organization

    async def get_by_status(
        self, status: OrganizationStatus, limit: int = 100, offset: int = 0
    ) -> QueryResult[Organization]:
        """Get organizations by status."""
        count_result = await self.db.fetch_one(
            "SELECT COUNT(*) as count FROM organizations WHERE status = ?",
            (status.value,),
        )
        total = count_result["count"] if count_result else 0

        rows = await self.db.fetch_all(
            """
            SELECT * FROM organizations
            WHERE status = ?
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
            """,
            (status.value, limit, offset),
        )

        organizations = [self._model_from_row(row) for row in rows]
        await self._hydrate_members(organizations)

        return QueryResult(
            items=organizations,
            total_count=total,
            offset=offset,
            limit=limit,
        )

    async def get_all(
        self,
        limit: int = 100,
        offset: int = 0,
        order_by: str = "updated_at",
        order_desc: bool = True,
    ) -> QueryResult[Organization]:
        """Get all organizations."""
        count_result = await self.db.fetch_one(
            "SELECT COUNT(*) as count FROM organizations"
        )
        total = count_result["count"] if count_result else 0

        order_dir = "DESC" if order_desc else "ASC"
        rows = await self.db.fetch_all(
            f"""
            SELECT * FROM organizations
            ORDER BY {order_by} {order_dir}
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )

        organizations = [self._model_from_row(row) for row in rows]
        await self._hydrate_members(organizations)

        return QueryResult(
            items=organizations,
            total_count=total,
            offset=offset,
            limit=limit,
        )

    async def _apply_events(self, events: list[Any]) -> Organization | None:
        """Rebuild organization state from events."""
        if not events:
            return None

        org: Organization | None = None

        for event in events:
            payload = event.payload
            match event.event_type:
                case EventType.ORGANIZATION_CREATED:
                    org = Organization(
                        id=event.aggregate_id,
                        name=payload.get("name", ""),
                        description=payload.get("description"),
                        status=OrganizationStatus.ACTIVE,
                        owner=payload.get("owner"),
                        owner_id=payload.get("owner_id"),
                        members=tuple(payload.get("members", [])),
                        member_ids=tuple(payload.get("member_ids", [])),
                        tags=tuple(payload.get("tags", [])),
                    )
                case EventType.ORGANIZATION_UPDATED if org:
                    changes = payload.get("changes", {})
                    for field, (_, new_val) in changes.items():
                        match field:
                            case "name":
                                org.name = new_val
                            case "description":
                                org.description = new_val
                            case "status":
                                org.status = OrganizationStatus(new_val)
                            case "owner":
                                org.owner = new_val
                            case "owner_id":
                                org.owner_id = new_val
                            case "members":
                                org.members = tuple(new_val)
                            case "member_ids":
                                org.member_ids = tuple(new_val)
                            case "tags":
                                org.tags = tuple(new_val)
                            case _:
                                pass
                case EventType.ORGANIZATION_ARCHIVED if org:
                    org.status = OrganizationStatus.ARCHIVED

        return org
