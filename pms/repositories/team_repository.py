"""Team repository with event sourcing."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from pms.core.events import EventType
from pms.models import Team, TeamStatus
from pms.repositories.base import EventSourcedRepository, QueryResult

if TYPE_CHECKING:
    from pms.core.events import EventStore
    from pms.core.metrics import MetricsCollector
    from pms.core.revisions import RevisionStore
    from pms.db.connection import Database


class TeamRepository(EventSourcedRepository[Team]):
    """Repository for Team entities."""

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
        return "team"

    @property
    def table_name(self) -> str:
        return "teams"

    @staticmethod
    def _parse_list(value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            return tuple(json.loads(value))
        return tuple(str(item) for item in value)

    def _model_from_row(self, row: dict[str, Any]) -> Team:
        members = self._parse_list(row.get("members"))
        member_ids = self._parse_list(row.get("member_ids"))
        tags = self._parse_list(row.get("tags"))

        return Team(
            id=row["id"],
            org_id=row.get("org_id"),
            name=row["name"],
            description=row.get("description"),
            status=TeamStatus(row["status"]),
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

    def _row_from_model(self, model: Team) -> dict[str, Any]:
        return {
            "id": model.id,
            "org_id": model.org_id,
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

    async def _hydrate_members(self, teams: list[Team]) -> None:
        if not teams:
            return

        ids = [team.id for team in teams]
        placeholders = ", ".join("?" for _ in ids)
        rows = await self.db.fetch_all(
            f"""
            SELECT
                tm.team_id,
                tm.actor_id,
                COALESCE(a.handle, a.name, a.id) AS actor_ref
            FROM team_members tm
            LEFT JOIN actors a ON a.id = tm.actor_id
            WHERE tm.team_id IN ({placeholders})
            ORDER BY tm.team_id ASC, tm.position ASC
            """,
            tuple(ids),
        )

        if not rows:
            return

        member_map: dict[str, list[str]] = {team.id: [] for team in teams}
        member_id_map: dict[str, list[str]] = {team.id: [] for team in teams}
        for row in rows:
            team_id = str(row["team_id"])
            member_id_map.setdefault(team_id, []).append(str(row["actor_id"]))
            actor_ref = row.get("actor_ref")
            member_map.setdefault(team_id, []).append(
                str(actor_ref) if actor_ref else str(row["actor_id"])
            )

        for team in teams:
            if member_id_map.get(team.id):
                team.member_ids = tuple(member_id_map[team.id])
                team.members = tuple(member_map[team.id])

    async def _sync_members(self, team: Team) -> None:
        await self.db.execute(
            "DELETE FROM team_members WHERE team_id = ?",
            (team.id,),
        )
        if not team.member_ids:
            return
        await self.db.execute_many(
            """
            INSERT INTO team_members (team_id, actor_id, position)
            VALUES (?, ?, ?)
            """,
            [
                (team.id, actor_id, position)
                for position, actor_id in enumerate(team.member_ids)
            ],
        )

    async def _update_projection(self, model: Team, is_create: bool) -> None:
        await super()._update_projection(model, is_create)
        await self._sync_members(model)

    async def create(
        self,
        name: str,
        org_id: str | None = None,
        description: str | None = None,
        owner: str | None = None,
        owner_id: str | None = None,
        members: list[str] | None = None,
        member_ids: list[str] | None = None,
        tags: list[str] | None = None,
        message: str | None = None,
    ) -> Team:
        """Create a new team."""
        team = Team(
            org_id=org_id,
            name=name,
            description=description,
            owner=owner,
            owner_id=owner_id,
            members=tuple(members) if members else (),
            member_ids=tuple(member_ids) if member_ids else (),
            tags=tuple(tags) if tags else (),
        )

        payload = {
            "org_id": org_id,
            "name": name,
            "description": description,
            "owner": owner,
            "owner_id": owner_id,
            "members": members or [],
            "member_ids": member_ids or [],
            "tags": tags or [],
        }

        return await self.save(
            team,
            EventType.TEAM_CREATED,
            payload,
            message=message or f"Created team '{name}'",
        )

    async def update(
        self,
        team_id: str,
        name: str | None = None,
        description: str | None = None,
        status: TeamStatus | None = None,
        owner: str | None = None,
        owner_id: str | None = None,
        clear_owner: bool = False,
        members: list[str] | None = None,
        member_ids: list[str] | None = None,
        clear_members: bool = False,
        tags: list[str] | None = None,
        message: str | None = None,
    ) -> Team | None:
        """Update a team."""
        team = await self.get_by_id(team_id)
        if team is None:
            return None

        changes: dict[str, Any] = {}
        if name is not None and name != team.name:
            changes["name"] = (team.name, name)
            team.name = name
        if description is not None and description != team.description:
            changes["description"] = (team.description, description)
            team.description = description
        if status is not None and status != team.status:
            changes["status"] = (team.status.value, status.value)
            team.status = status
        if clear_owner:
            if team.owner is not None or team.owner_id is not None:
                changes["owner"] = (team.owner, None)
                changes["owner_id"] = (team.owner_id, None)
                team.owner = None
                team.owner_id = None
        elif owner is not None and (owner != team.owner or owner_id != team.owner_id):
            changes["owner"] = (team.owner, owner)
            changes["owner_id"] = (team.owner_id, owner_id)
            team.owner = owner
            team.owner_id = owner_id
        if clear_members:
            if team.members or team.member_ids:
                changes["members"] = (list(team.members), [])
                changes["member_ids"] = (list(team.member_ids), [])
                team.members = ()
                team.member_ids = ()
        elif members is not None and (
            tuple(members) != team.members or tuple(member_ids or []) != team.member_ids
        ):
            changes["members"] = (list(team.members), members)
            changes["member_ids"] = (
                list(team.member_ids),
                member_ids or [],
            )
            team.members = tuple(members)
            team.member_ids = tuple(member_ids or [])
        if tags is not None and tuple(tags) != team.tags:
            changes["tags"] = (list(team.tags), tags)
            team.tags = tuple(tags)

        if not changes:
            return team

        team.touch()

        return await self.save(
            team,
            EventType.TEAM_UPDATED,
            {"changes": changes},
            message=message,
        )

    async def archive(self, team_id: str, message: str | None = None) -> Team | None:
        """Archive a team."""
        team = await self.get_by_id(team_id)
        if team is None:
            return None

        old_status = team.status
        team.archive()

        return await self.save(
            team,
            EventType.TEAM_ARCHIVED,
            {"old_status": old_status.value, "new_status": team.status.value},
            message=message or "Team archived",
        )

    async def get_by_id(self, entity_id: str) -> Team | None:
        team = await super().get_by_id(entity_id)
        if team is None:
            return None
        await self._hydrate_members([team])
        return team

    async def get_by_name(self, name: str) -> Team | None:
        """Get a team by name."""
        row = await self.db.fetch_one(
            "SELECT * FROM teams WHERE name = ?",
            (name,),
        )
        if row is None:
            return None
        team = self._model_from_row(row)
        await self._hydrate_members([team])
        return team

    async def get_by_org(
        self,
        org_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Team]:
        """Get teams for an organization."""
        count_result = await self.db.fetch_one(
            "SELECT COUNT(*) as count FROM teams WHERE org_id = ?",
            (org_id,),
        )
        total = count_result["count"] if count_result else 0

        rows = await self.db.fetch_all(
            """
            SELECT * FROM teams
            WHERE org_id = ?
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
            """,
            (org_id, limit, offset),
        )

        teams = [self._model_from_row(row) for row in rows]
        await self._hydrate_members(teams)

        return QueryResult(
            items=teams,
            total_count=total,
            offset=offset,
            limit=limit,
        )

    async def get_by_status(
        self,
        status: TeamStatus,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Team]:
        """Get teams by status."""
        count_result = await self.db.fetch_one(
            "SELECT COUNT(*) as count FROM teams WHERE status = ?",
            (status.value,),
        )
        total = count_result["count"] if count_result else 0

        rows = await self.db.fetch_all(
            """
            SELECT * FROM teams
            WHERE status = ?
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
            """,
            (status.value, limit, offset),
        )

        teams = [self._model_from_row(row) for row in rows]
        await self._hydrate_members(teams)

        return QueryResult(
            items=teams,
            total_count=total,
            offset=offset,
            limit=limit,
        )

    async def list_filtered(
        self,
        *,
        org_id: str | None = None,
        status: TeamStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Team]:
        """List teams with combined optional filters."""
        conditions: list[str] = []
        params: list[Any] = []

        if org_id is not None:
            conditions.append("org_id = ?")
            params.append(org_id)
        if status is not None:
            conditions.append("status = ?")
            params.append(status.value)

        where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        count_result = await self.db.fetch_one(
            f"SELECT COUNT(*) as count FROM teams {where_sql}",
            tuple(params),
        )
        total = count_result["count"] if count_result else 0

        rows = await self.db.fetch_all(
            f"""
            SELECT * FROM teams
            {where_sql}
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        )

        teams = [self._model_from_row(row) for row in rows]
        await self._hydrate_members(teams)

        return QueryResult(
            items=teams,
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
    ) -> QueryResult[Team]:
        """Get all teams."""
        count_result = await self.db.fetch_one("SELECT COUNT(*) as count FROM teams")
        total = count_result["count"] if count_result else 0

        order_dir = "DESC" if order_desc else "ASC"
        rows = await self.db.fetch_all(
            f"""
            SELECT * FROM teams
            ORDER BY {order_by} {order_dir}
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )

        teams = [self._model_from_row(row) for row in rows]
        await self._hydrate_members(teams)

        return QueryResult(
            items=teams,
            total_count=total,
            offset=offset,
            limit=limit,
        )

    async def _apply_events(self, events: list[Any]) -> Team | None:
        """Rebuild team state from events."""
        if not events:
            return None

        team: Team | None = None

        for event in events:
            payload = event.payload
            match event.event_type:
                case EventType.TEAM_CREATED:
                    team = Team(
                        id=event.aggregate_id,
                        org_id=payload.get("org_id"),
                        name=payload.get("name", ""),
                        description=payload.get("description"),
                        status=TeamStatus.ACTIVE,
                        owner=payload.get("owner"),
                        owner_id=payload.get("owner_id"),
                        members=tuple(payload.get("members", [])),
                        member_ids=tuple(payload.get("member_ids", [])),
                        tags=tuple(payload.get("tags", [])),
                    )
                case EventType.TEAM_UPDATED if team:
                    changes = payload.get("changes", {})
                    for field, (_, new_val) in changes.items():
                        match field:
                            case "name":
                                team.name = new_val
                            case "description":
                                team.description = new_val
                            case "status":
                                team.status = TeamStatus(new_val)
                            case "owner":
                                team.owner = new_val
                            case "owner_id":
                                team.owner_id = new_val
                            case "members":
                                team.members = tuple(new_val)
                            case "member_ids":
                                team.member_ids = tuple(new_val)
                            case "tags":
                                team.tags = tuple(new_val)
                            case _:
                                pass
                case EventType.TEAM_ARCHIVED if team:
                    team.status = TeamStatus.ARCHIVED

        return team
