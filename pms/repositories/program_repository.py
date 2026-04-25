"""Program repository with event sourcing."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from pms.core.events import EventType
from pms.models import Program, ProgramStatus
from pms.repositories.base import EventSourcedRepository, QueryResult

if TYPE_CHECKING:
    from pms.core.events import EventStore
    from pms.core.metrics import MetricsCollector
    from pms.core.revisions import RevisionStore
    from pms.db.connection import Database


class ProgramRepository(EventSourcedRepository[Program]):
    """Repository for Program entities."""

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
        return "program"

    @property
    def table_name(self) -> str:
        return "programs"

    def _model_from_row(self, row: dict[str, Any]) -> Program:
        tags_raw = row.get("tags", "[]")
        tags = json.loads(tags_raw) if isinstance(tags_raw, str) else tags_raw

        return Program(
            id=row["id"],
            org_id=row.get("org_id"),
            portfolio_id=row.get("portfolio_id"),
            name=row["name"],
            description=row.get("description"),
            status=ProgramStatus(row["status"]),
            owner=row.get("owner"),
            owner_id=row.get("owner_id"),
            project_ids=(),
            goal_ids=(),
            objective_ids=(),
            effective_goal_ids=(),
            effective_objective_ids=(),
            tags=tuple(tags),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_event_sequence=row.get("last_event_sequence", 0),
            last_revision_number=row.get("last_revision_number", 0),
        )

    def _row_from_model(self, model: Program) -> dict[str, Any]:
        return {
            "id": model.id,
            "org_id": model.org_id,
            "portfolio_id": model.portfolio_id,
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

    async def create(
        self,
        name: str,
        org_id: str | None = None,
        portfolio_id: str | None = None,
        description: str | None = None,
        owner: str | None = None,
        owner_id: str | None = None,
        goal_ids: list[str] | None = None,
        objective_ids: list[str] | None = None,
        tags: list[str] | None = None,
        message: str | None = None,
    ) -> Program:
        """Create a new program."""

        async def _create() -> Program:
            return await self._create_in_transaction(
                name=name,
                org_id=org_id,
                portfolio_id=portfolio_id,
                description=description,
                owner=owner,
                owner_id=owner_id,
                goal_ids=goal_ids,
                objective_ids=objective_ids,
                tags=tags,
                message=message,
            )

        return await self._run_in_owned_transaction(
            _create,
            operation_name="create",
        )

    async def _create_in_transaction(
        self,
        *,
        name: str,
        org_id: str | None = None,
        portfolio_id: str | None = None,
        description: str | None = None,
        owner: str | None = None,
        owner_id: str | None = None,
        goal_ids: list[str] | None = None,
        objective_ids: list[str] | None = None,
        tags: list[str] | None = None,
        message: str | None = None,
    ) -> Program:
        """Create a new program assuming the caller owns the transaction."""
        self._assert_owned_transaction("_create_in_transaction")
        program = Program(
            org_id=org_id,
            portfolio_id=portfolio_id,
            name=name,
            description=description,
            owner=owner,
            owner_id=owner_id,
            goal_ids=tuple(goal_ids) if goal_ids else (),
            objective_ids=tuple(objective_ids) if objective_ids else (),
            effective_goal_ids=(),
            effective_objective_ids=(),
            tags=tuple(tags) if tags else (),
        )

        payload = {
            "org_id": org_id,
            "portfolio_id": portfolio_id,
            "name": name,
            "description": description,
            "owner": owner,
            "owner_id": owner_id,
            "goal_ids": goal_ids or [],
            "objective_ids": objective_ids or [],
            "tags": tags or [],
        }

        saved = await self._save_in_transaction(
            model=program,
            event_type=EventType.PROGRAM_CREATED,
            payload=payload,
            message=message or f"Created program '{name}'",
        )
        await self._sync_goal_links_in_transaction(saved.id, goal_ids or [])
        await self._sync_objective_links_in_transaction(saved.id, objective_ids or [])
        return await self.get_by_id(saved.id) or saved

    async def update(
        self,
        program_id: str,
        name: str | None = None,
        description: str | None = None,
        status: ProgramStatus | None = None,
        owner: str | None = None,
        owner_id: str | None = None,
        clear_owner: bool = False,
        goal_ids: list[str] | None = None,
        objective_ids: list[str] | None = None,
        tags: list[str] | None = None,
        message: str | None = None,
    ) -> Program | None:
        """Update a program."""

        async def _update() -> Program | None:
            return await self._update_in_transaction(
                program_id=program_id,
                name=name,
                description=description,
                status=status,
                owner=owner,
                owner_id=owner_id,
                clear_owner=clear_owner,
                goal_ids=goal_ids,
                objective_ids=objective_ids,
                tags=tags,
                message=message,
            )

        return await self._run_in_owned_transaction(
            _update,
            operation_name="update",
        )

    async def _update_in_transaction(
        self,
        *,
        program_id: str,
        name: str | None = None,
        description: str | None = None,
        status: ProgramStatus | None = None,
        owner: str | None = None,
        owner_id: str | None = None,
        clear_owner: bool = False,
        goal_ids: list[str] | None = None,
        objective_ids: list[str] | None = None,
        tags: list[str] | None = None,
        message: str | None = None,
    ) -> Program | None:
        """Update a program assuming the caller owns the transaction."""
        self._assert_owned_transaction("_update_in_transaction")
        program = await self.get_by_id(program_id)
        if program is None:
            return None

        current_goal_ids = await self._load_direct_goal_ids(program_id)
        current_objective_ids = await self._load_direct_objective_ids(program_id)

        changes: dict[str, Any] = {}
        if name is not None and name != program.name:
            changes["name"] = (program.name, name)
            program.name = name
        if description is not None and description != program.description:
            changes["description"] = (program.description, description)
            program.description = description
        if status is not None and status != program.status:
            changes["status"] = (program.status.value, status.value)
            program.status = status
        if clear_owner:
            if program.owner is not None or program.owner_id is not None:
                changes["owner"] = (program.owner, None)
                changes["owner_id"] = (program.owner_id, None)
                program.owner = None
                program.owner_id = None
        elif owner is not None and (
            owner != program.owner or owner_id != program.owner_id
        ):
            changes["owner"] = (program.owner, owner)
            changes["owner_id"] = (program.owner_id, owner_id)
            program.owner = owner
            program.owner_id = owner_id
        if goal_ids is not None and tuple(goal_ids) != current_goal_ids:
            changes["goal_ids"] = (list(current_goal_ids), goal_ids)
            program.goal_ids = tuple(goal_ids)
            program.effective_goal_ids = ()
        if objective_ids is not None and tuple(objective_ids) != current_objective_ids:
            changes["objective_ids"] = (list(current_objective_ids), objective_ids)
            program.objective_ids = tuple(objective_ids)
            program.effective_objective_ids = ()
        if tags is not None and tuple(tags) != program.tags:
            changes["tags"] = (list(program.tags), tags)
            program.tags = tuple(tags)

        if not changes:
            return program

        program.touch()

        saved = await self._save_in_transaction(
            model=program,
            event_type=EventType.PROGRAM_UPDATED,
            payload={"changes": changes},
            message=message,
        )
        if goal_ids is not None:
            await self._sync_goal_links_in_transaction(saved.id, goal_ids)
        if objective_ids is not None:
            await self._sync_objective_links_in_transaction(saved.id, objective_ids)
        return await self.get_by_id(saved.id) or saved

    async def archive(
        self, program_id: str, message: str | None = None
    ) -> Program | None:
        """Archive a program."""
        program = await self.get_by_id(program_id)
        if program is None:
            return None

        old_status = program.status
        program.archive()

        return await self.save(
            program,
            EventType.PROGRAM_ARCHIVED,
            {"old_status": old_status.value, "new_status": program.status.value},
            message=message or "Program archived",
        )

    async def get_by_id(self, program_id: str) -> Program | None:
        """Get a program by id with derived scope ids."""
        program = await super().get_by_id(program_id)
        if program is None:
            return None
        await self._hydrate_scope_ids([program])
        return program

    async def get_by_name(self, name: str) -> Program | None:
        """Get a program by name."""
        row = await self.db.fetch_one(
            "SELECT * FROM programs WHERE name = ?",
            (name,),
        )
        if row is None:
            return None
        program = self._model_from_row(row)
        await self._hydrate_scope_ids([program])
        return program

    async def get_by_portfolio(
        self,
        portfolio_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Program]:
        """Get programs for a portfolio."""
        count_result = await self.db.fetch_one(
            "SELECT COUNT(*) as count FROM programs WHERE portfolio_id = ?",
            (portfolio_id,),
        )
        total = count_result["count"] if count_result else 0

        rows = await self.db.fetch_all(
            """
            SELECT * FROM programs
            WHERE portfolio_id = ?
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
            """,
            (portfolio_id, limit, offset),
        )
        items = [self._model_from_row(row) for row in rows]
        await self._hydrate_scope_ids(items)
        return QueryResult(items=items, total_count=total, offset=offset, limit=limit)

    async def get_by_org(
        self,
        org_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Program]:
        """Get programs for an organization."""
        count_result = await self.db.fetch_one(
            "SELECT COUNT(*) as count FROM programs WHERE org_id = ?",
            (org_id,),
        )
        total = count_result["count"] if count_result else 0

        rows = await self.db.fetch_all(
            """
            SELECT * FROM programs
            WHERE org_id = ?
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
            """,
            (org_id, limit, offset),
        )
        items = [self._model_from_row(row) for row in rows]
        await self._hydrate_scope_ids(items)
        return QueryResult(items=items, total_count=total, offset=offset, limit=limit)

    async def get_by_status(
        self,
        status: ProgramStatus,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Program]:
        """Get programs by status."""
        count_result = await self.db.fetch_one(
            "SELECT COUNT(*) as count FROM programs WHERE status = ?",
            (status.value,),
        )
        total = count_result["count"] if count_result else 0

        rows = await self.db.fetch_all(
            """
            SELECT * FROM programs
            WHERE status = ?
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
            """,
            (status.value, limit, offset),
        )
        items = [self._model_from_row(row) for row in rows]
        await self._hydrate_scope_ids(items)
        return QueryResult(items=items, total_count=total, offset=offset, limit=limit)

    async def list_filtered(
        self,
        *,
        org_id: str | None = None,
        portfolio_id: str | None = None,
        status: ProgramStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Program]:
        """List programs with combined optional filters."""
        conditions: list[str] = []
        params: list[Any] = []

        if org_id is not None:
            conditions.append("org_id = ?")
            params.append(org_id)
        if portfolio_id is not None:
            conditions.append("portfolio_id = ?")
            params.append(portfolio_id)
        if status is not None:
            conditions.append("status = ?")
            params.append(status.value)

        where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        count_result = await self.db.fetch_one(
            f"SELECT COUNT(*) as count FROM programs {where_sql}",
            tuple(params),
        )
        total = count_result["count"] if count_result else 0

        rows = await self.db.fetch_all(
            f"""
            SELECT * FROM programs
            {where_sql}
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        )
        items = [self._model_from_row(row) for row in rows]
        await self._hydrate_scope_ids(items)
        return QueryResult(items=items, total_count=total, offset=offset, limit=limit)

    async def get_all(
        self,
        limit: int = 100,
        offset: int = 0,
        order_by: str = "updated_at",
        order_desc: bool = True,
    ) -> QueryResult[Program]:
        """Get all programs."""
        count_result = await self.db.fetch_one("SELECT COUNT(*) as count FROM programs")
        total = count_result["count"] if count_result else 0

        order_dir = "DESC" if order_desc else "ASC"
        rows = await self.db.fetch_all(
            f"""
            SELECT * FROM programs
            ORDER BY {order_by} {order_dir}
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        items = [self._model_from_row(row) for row in rows]
        await self._hydrate_scope_ids(items)
        return QueryResult(items=items, total_count=total, offset=offset, limit=limit)

    async def _hydrate_scope_ids(self, programs: list[Program]) -> None:
        """Hydrate effective scope ids from direct and project-derived relations."""
        if not programs:
            return

        program_ids = [program.id for program in programs]
        program_by_id = {program.id: program for program in programs}
        project_map: dict[str, list[str]] = {program.id: [] for program in programs}
        goal_map: dict[str, list[str]] = {program.id: [] for program in programs}
        direct_goal_map: dict[str, list[str]] = {program.id: [] for program in programs}
        objective_map: dict[str, list[str]] = {program.id: [] for program in programs}
        direct_objective_map: dict[str, list[str]] = {
            program.id: [] for program in programs
        }
        goal_seen: dict[str, set[str]] = {program.id: set() for program in programs}
        objective_seen: dict[str, set[str]] = {
            program.id: set() for program in programs
        }
        placeholders = ", ".join("?" * len(program_ids))

        project_rows = await self.db.fetch_all(
            f"""
            SELECT id, program_id
            FROM projects
            WHERE program_id IN ({placeholders})
            ORDER BY updated_at DESC, id
            """,
            tuple(program_ids),
        )
        for row in project_rows:
            scoped_program_id = row.get("program_id")
            if scoped_program_id in project_map:
                project_map[scoped_program_id].append(row["id"])

        direct_goal_rows = await self.db.fetch_all(
            f"""
            SELECT program_id, goal_id
            FROM program_goals
            WHERE program_id IN ({placeholders})
            ORDER BY program_id ASC, position ASC
            """,
            tuple(program_ids),
        )
        for row in direct_goal_rows:
            scoped_program_id = row.get("program_id")
            goal_id = row["goal_id"]
            if (
                scoped_program_id in goal_map
                and goal_id not in goal_seen[scoped_program_id]
            ):
                direct_goal_map[scoped_program_id].append(goal_id)
                goal_map[scoped_program_id].append(goal_id)
                goal_seen[scoped_program_id].add(goal_id)

        goal_rows = await self.db.fetch_all(
            f"""
            SELECT g.id, p.program_id
            FROM goals g
            INNER JOIN projects p ON p.id = g.project_id
            WHERE p.program_id IN ({placeholders})
            ORDER BY g.updated_at DESC, g.id
            """,
            tuple(program_ids),
        )
        for row in goal_rows:
            scoped_program_id = row.get("program_id")
            goal_id = row["id"]
            if (
                scoped_program_id in goal_map
                and goal_id not in goal_seen[scoped_program_id]
            ):
                goal_map[scoped_program_id].append(goal_id)
                goal_seen[scoped_program_id].add(goal_id)

        direct_objective_rows = await self.db.fetch_all(
            f"""
            SELECT program_id, objective_id
            FROM program_objectives
            WHERE program_id IN ({placeholders})
            ORDER BY program_id ASC, position ASC
            """,
            tuple(program_ids),
        )
        for row in direct_objective_rows:
            scoped_program_id = row.get("program_id")
            objective_id = row["objective_id"]
            if (
                scoped_program_id in objective_map
                and objective_id not in objective_seen[scoped_program_id]
            ):
                direct_objective_map[scoped_program_id].append(objective_id)
                objective_map[scoped_program_id].append(objective_id)
                objective_seen[scoped_program_id].add(objective_id)

        objective_rows = await self.db.fetch_all(
            f"""
            SELECT o.id, p.program_id
            FROM objectives o
            INNER JOIN goals g ON g.id = o.goal_id
            INNER JOIN projects p ON p.id = g.project_id
            WHERE p.program_id IN ({placeholders})
            ORDER BY o.updated_at DESC, o.id
            """,
            tuple(program_ids),
        )
        for row in objective_rows:
            scoped_program_id = row.get("program_id")
            objective_id = row["id"]
            if (
                scoped_program_id in objective_map
                and objective_id not in objective_seen[scoped_program_id]
            ):
                objective_map[scoped_program_id].append(objective_id)
                objective_seen[scoped_program_id].add(objective_id)

        for program_id, program in program_by_id.items():
            program.project_ids = tuple(project_map[program_id])
            program.goal_ids = tuple(direct_goal_map[program_id])
            program.objective_ids = tuple(direct_objective_map[program_id])
            program.effective_goal_ids = tuple(goal_map[program_id])
            program.effective_objective_ids = tuple(objective_map[program_id])

    async def _load_direct_goal_ids(self, program_id: str) -> tuple[str, ...]:
        rows = await self.db.fetch_all(
            """
            SELECT goal_id
            FROM program_goals
            WHERE program_id = ?
            ORDER BY position ASC
            """,
            (program_id,),
        )
        return tuple(str(row["goal_id"]) for row in rows)

    async def _load_direct_objective_ids(self, program_id: str) -> tuple[str, ...]:
        rows = await self.db.fetch_all(
            """
            SELECT objective_id
            FROM program_objectives
            WHERE program_id = ?
            ORDER BY position ASC
            """,
            (program_id,),
        )
        return tuple(str(row["objective_id"]) for row in rows)

    async def _sync_goal_links_in_transaction(
        self, program_id: str, goal_ids: list[str]
    ) -> None:
        self._assert_owned_transaction("_sync_goal_links_in_transaction")
        await self.db.execute(
            "DELETE FROM program_goals WHERE program_id = ?",
            (program_id,),
        )
        if not goal_ids:
            return
        await self.db.execute_many(
            """
            INSERT INTO program_goals (program_id, goal_id, position)
            VALUES (?, ?, ?)
            """,
            [
                (program_id, goal_id, position)
                for position, goal_id in enumerate(goal_ids)
            ],
        )

    async def _sync_objective_links_in_transaction(
        self,
        program_id: str,
        objective_ids: list[str],
    ) -> None:
        self._assert_owned_transaction("_sync_objective_links_in_transaction")
        await self.db.execute(
            "DELETE FROM program_objectives WHERE program_id = ?",
            (program_id,),
        )
        if not objective_ids:
            return
        await self.db.execute_many(
            """
            INSERT INTO program_objectives (program_id, objective_id, position)
            VALUES (?, ?, ?)
            """,
            [
                (program_id, objective_id, position)
                for position, objective_id in enumerate(objective_ids)
            ],
        )

    async def _apply_events(self, events: list[Any]) -> Program | None:
        """Rebuild program state from events."""
        if not events:
            return None

        program: Program | None = None

        for event in events:
            payload = event.payload
            match event.event_type:
                case EventType.PROGRAM_CREATED:
                    program = Program(
                        id=event.aggregate_id,
                        org_id=payload.get("org_id"),
                        portfolio_id=payload.get("portfolio_id"),
                        name=payload.get("name", ""),
                        description=payload.get("description"),
                        status=ProgramStatus.ACTIVE,
                        owner=payload.get("owner"),
                        owner_id=payload.get("owner_id"),
                        project_ids=tuple(payload.get("project_ids", [])),
                        goal_ids=tuple(payload.get("goal_ids", [])),
                        objective_ids=tuple(payload.get("objective_ids", [])),
                        effective_goal_ids=tuple(payload.get("effective_goal_ids", [])),
                        effective_objective_ids=tuple(
                            payload.get("effective_objective_ids", [])
                        ),
                        tags=tuple(payload.get("tags", [])),
                    )
                case EventType.PROGRAM_UPDATED if program:
                    changes = payload.get("changes", {})
                    for field, (_, new_val) in changes.items():
                        match field:
                            case "name":
                                program.name = new_val
                            case "description":
                                program.description = new_val
                            case "status":
                                program.status = ProgramStatus(new_val)
                            case "owner":
                                program.owner = new_val
                            case "owner_id":
                                program.owner_id = new_val
                            case "project_ids":
                                program.project_ids = tuple(new_val)
                            case "goal_ids":
                                program.goal_ids = tuple(new_val)
                            case "objective_ids":
                                program.objective_ids = tuple(new_val)
                            case "effective_goal_ids":
                                program.effective_goal_ids = tuple(new_val)
                            case "effective_objective_ids":
                                program.effective_objective_ids = tuple(new_val)
                            case "tags":
                                program.tags = tuple(new_val)
                            case _:
                                pass
                case EventType.PROGRAM_ARCHIVED if program:
                    program.status = ProgramStatus.ARCHIVED

        return program
