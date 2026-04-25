"""Portfolio repository with event sourcing."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from pms.core.events import EventType
from pms.models import Portfolio, PortfolioStatus
from pms.repositories.base import EventSourcedRepository, QueryResult

if TYPE_CHECKING:
    from pms.core.events import EventStore
    from pms.core.metrics import MetricsCollector
    from pms.core.revisions import RevisionStore
    from pms.db.connection import Database


class PortfolioRepository(EventSourcedRepository[Portfolio]):
    """Repository for Portfolio entities."""

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
        return "portfolio"

    @property
    def table_name(self) -> str:
        return "portfolios"

    def _model_from_row(self, row: dict[str, Any]) -> Portfolio:
        tags_raw = row.get("tags", "[]")
        tags = json.loads(tags_raw) if isinstance(tags_raw, str) else tags_raw

        return Portfolio(
            id=row["id"],
            org_id=row.get("org_id"),
            name=row["name"],
            description=row.get("description"),
            status=PortfolioStatus(row["status"]),
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

    def _row_from_model(self, model: Portfolio) -> dict[str, Any]:
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

    async def create(
        self,
        name: str,
        org_id: str | None = None,
        description: str | None = None,
        owner: str | None = None,
        owner_id: str | None = None,
        goal_ids: list[str] | None = None,
        objective_ids: list[str] | None = None,
        tags: list[str] | None = None,
        message: str | None = None,
    ) -> Portfolio:
        """Create a new portfolio."""

        async def _create() -> Portfolio:
            return await self._create_in_transaction(
                name=name,
                org_id=org_id,
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
        description: str | None = None,
        owner: str | None = None,
        owner_id: str | None = None,
        goal_ids: list[str] | None = None,
        objective_ids: list[str] | None = None,
        tags: list[str] | None = None,
        message: str | None = None,
    ) -> Portfolio:
        """Create a new portfolio assuming the caller owns the transaction."""
        self._assert_owned_transaction("_create_in_transaction")
        portfolio = Portfolio(
            org_id=org_id,
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
            "name": name,
            "description": description,
            "owner": owner,
            "owner_id": owner_id,
            "goal_ids": goal_ids or [],
            "objective_ids": objective_ids or [],
            "tags": tags or [],
        }

        saved = await self._save_in_transaction(
            model=portfolio,
            event_type=EventType.PORTFOLIO_CREATED,
            payload=payload,
            message=message or f"Created portfolio '{name}'",
        )
        await self._sync_goal_links_in_transaction(saved.id, goal_ids or [])
        await self._sync_objective_links_in_transaction(saved.id, objective_ids or [])
        return await self.get_by_id(saved.id) or saved

    async def update(
        self,
        portfolio_id: str,
        name: str | None = None,
        description: str | None = None,
        status: PortfolioStatus | None = None,
        owner: str | None = None,
        owner_id: str | None = None,
        clear_owner: bool = False,
        goal_ids: list[str] | None = None,
        objective_ids: list[str] | None = None,
        tags: list[str] | None = None,
        message: str | None = None,
    ) -> Portfolio | None:
        """Update a portfolio."""

        async def _update() -> Portfolio | None:
            return await self._update_in_transaction(
                portfolio_id=portfolio_id,
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
        portfolio_id: str,
        name: str | None = None,
        description: str | None = None,
        status: PortfolioStatus | None = None,
        owner: str | None = None,
        owner_id: str | None = None,
        clear_owner: bool = False,
        goal_ids: list[str] | None = None,
        objective_ids: list[str] | None = None,
        tags: list[str] | None = None,
        message: str | None = None,
    ) -> Portfolio | None:
        """Update a portfolio assuming the caller owns the transaction."""
        self._assert_owned_transaction("_update_in_transaction")
        portfolio = await self.get_by_id(portfolio_id)
        if portfolio is None:
            return None

        current_goal_ids = await self._load_direct_goal_ids(portfolio_id)
        current_objective_ids = await self._load_direct_objective_ids(portfolio_id)

        changes: dict[str, Any] = {}
        if name is not None and name != portfolio.name:
            changes["name"] = (portfolio.name, name)
            portfolio.name = name
        if description is not None and description != portfolio.description:
            changes["description"] = (portfolio.description, description)
            portfolio.description = description
        if status is not None and status != portfolio.status:
            changes["status"] = (portfolio.status.value, status.value)
            portfolio.status = status
        if clear_owner:
            if portfolio.owner is not None or portfolio.owner_id is not None:
                changes["owner"] = (portfolio.owner, None)
                changes["owner_id"] = (portfolio.owner_id, None)
                portfolio.owner = None
                portfolio.owner_id = None
        elif owner is not None and (
            owner != portfolio.owner or owner_id != portfolio.owner_id
        ):
            changes["owner"] = (portfolio.owner, owner)
            changes["owner_id"] = (portfolio.owner_id, owner_id)
            portfolio.owner = owner
            portfolio.owner_id = owner_id
        if goal_ids is not None and tuple(goal_ids) != current_goal_ids:
            changes["goal_ids"] = (list(current_goal_ids), goal_ids)
            portfolio.goal_ids = tuple(goal_ids)
            portfolio.effective_goal_ids = ()
        if objective_ids is not None and tuple(objective_ids) != current_objective_ids:
            changes["objective_ids"] = (list(current_objective_ids), objective_ids)
            portfolio.objective_ids = tuple(objective_ids)
            portfolio.effective_objective_ids = ()
        if tags is not None and tuple(tags) != portfolio.tags:
            changes["tags"] = (list(portfolio.tags), tags)
            portfolio.tags = tuple(tags)

        if not changes:
            return portfolio

        portfolio.touch()

        saved = await self._save_in_transaction(
            model=portfolio,
            event_type=EventType.PORTFOLIO_UPDATED,
            payload={"changes": changes},
            message=message,
        )
        if goal_ids is not None:
            await self._sync_goal_links_in_transaction(saved.id, goal_ids)
        if objective_ids is not None:
            await self._sync_objective_links_in_transaction(saved.id, objective_ids)
        return await self.get_by_id(saved.id) or saved

    async def archive(
        self, portfolio_id: str, message: str | None = None
    ) -> Portfolio | None:
        """Archive a portfolio."""
        portfolio = await self.get_by_id(portfolio_id)
        if portfolio is None:
            return None

        old_status = portfolio.status
        portfolio.archive()

        return await self.save(
            portfolio,
            EventType.PORTFOLIO_ARCHIVED,
            {"old_status": old_status.value, "new_status": portfolio.status.value},
            message=message or "Portfolio archived",
        )

    async def get_by_id(self, portfolio_id: str) -> Portfolio | None:
        """Get a portfolio by id with derived scope ids."""
        portfolio = await super().get_by_id(portfolio_id)
        if portfolio is None:
            return None
        await self._hydrate_scope_ids([portfolio])
        return portfolio

    async def get_by_name(self, name: str) -> Portfolio | None:
        """Get a portfolio by name."""
        row = await self.db.fetch_one(
            "SELECT * FROM portfolios WHERE name = ?",
            (name,),
        )
        if row is None:
            return None
        portfolio = self._model_from_row(row)
        await self._hydrate_scope_ids([portfolio])
        return portfolio

    async def get_by_org(
        self,
        org_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Portfolio]:
        """Get portfolios for an organization."""
        count_result = await self.db.fetch_one(
            "SELECT COUNT(*) as count FROM portfolios WHERE org_id = ?",
            (org_id,),
        )
        total = count_result["count"] if count_result else 0

        rows = await self.db.fetch_all(
            """
            SELECT * FROM portfolios
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
        status: PortfolioStatus,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Portfolio]:
        """Get portfolios by status."""
        count_result = await self.db.fetch_one(
            "SELECT COUNT(*) as count FROM portfolios WHERE status = ?",
            (status.value,),
        )
        total = count_result["count"] if count_result else 0

        rows = await self.db.fetch_all(
            """
            SELECT * FROM portfolios
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
        status: PortfolioStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Portfolio]:
        """List portfolios with combined optional filters."""
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
            f"SELECT COUNT(*) as count FROM portfolios {where_sql}",
            tuple(params),
        )
        total = count_result["count"] if count_result else 0

        rows = await self.db.fetch_all(
            f"""
            SELECT * FROM portfolios
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
    ) -> QueryResult[Portfolio]:
        """Get all portfolios."""
        count_result = await self.db.fetch_one(
            "SELECT COUNT(*) as count FROM portfolios"
        )
        total = count_result["count"] if count_result else 0

        order_dir = "DESC" if order_desc else "ASC"
        rows = await self.db.fetch_all(
            f"""
            SELECT * FROM portfolios
            ORDER BY {order_by} {order_dir}
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        items = [self._model_from_row(row) for row in rows]
        await self._hydrate_scope_ids(items)
        return QueryResult(items=items, total_count=total, offset=offset, limit=limit)

    async def _hydrate_scope_ids(self, portfolios: list[Portfolio]) -> None:
        """Hydrate effective scope ids from direct and project-derived relations."""
        if not portfolios:
            return

        portfolio_ids = [portfolio.id for portfolio in portfolios]
        portfolio_by_id = {portfolio.id: portfolio for portfolio in portfolios}
        project_map: dict[str, list[str]] = {
            portfolio.id: [] for portfolio in portfolios
        }
        goal_map: dict[str, list[str]] = {portfolio.id: [] for portfolio in portfolios}
        direct_goal_map: dict[str, list[str]] = {
            portfolio.id: [] for portfolio in portfolios
        }
        objective_map: dict[str, list[str]] = {
            portfolio.id: [] for portfolio in portfolios
        }
        direct_objective_map: dict[str, list[str]] = {
            portfolio.id: [] for portfolio in portfolios
        }
        goal_seen: dict[str, set[str]] = {
            portfolio.id: set() for portfolio in portfolios
        }
        objective_seen: dict[str, set[str]] = {
            portfolio.id: set() for portfolio in portfolios
        }
        placeholders = ", ".join("?" * len(portfolio_ids))

        project_rows = await self.db.fetch_all(
            f"""
            SELECT id, portfolio_id
            FROM projects
            WHERE portfolio_id IN ({placeholders})
            ORDER BY updated_at DESC, id
            """,
            tuple(portfolio_ids),
        )
        for row in project_rows:
            scoped_portfolio_id = row.get("portfolio_id")
            if scoped_portfolio_id in project_map:
                project_map[scoped_portfolio_id].append(row["id"])

        direct_goal_rows = await self.db.fetch_all(
            f"""
            SELECT portfolio_id, goal_id
            FROM portfolio_goals
            WHERE portfolio_id IN ({placeholders})
            ORDER BY portfolio_id ASC, position ASC
            """,
            tuple(portfolio_ids),
        )
        for row in direct_goal_rows:
            scoped_portfolio_id = row.get("portfolio_id")
            goal_id = row["goal_id"]
            if (
                scoped_portfolio_id in goal_map
                and goal_id not in goal_seen[scoped_portfolio_id]
            ):
                direct_goal_map[scoped_portfolio_id].append(goal_id)
                goal_map[scoped_portfolio_id].append(goal_id)
                goal_seen[scoped_portfolio_id].add(goal_id)

        goal_rows = await self.db.fetch_all(
            f"""
            SELECT g.id, p.portfolio_id
            FROM goals g
            INNER JOIN projects p ON p.id = g.project_id
            WHERE p.portfolio_id IN ({placeholders})
            ORDER BY g.updated_at DESC, g.id
            """,
            tuple(portfolio_ids),
        )
        for row in goal_rows:
            scoped_portfolio_id = row.get("portfolio_id")
            goal_id = row["id"]
            if (
                scoped_portfolio_id in goal_map
                and goal_id not in goal_seen[scoped_portfolio_id]
            ):
                goal_map[scoped_portfolio_id].append(goal_id)
                goal_seen[scoped_portfolio_id].add(goal_id)

        direct_objective_rows = await self.db.fetch_all(
            f"""
            SELECT portfolio_id, objective_id
            FROM portfolio_objectives
            WHERE portfolio_id IN ({placeholders})
            ORDER BY portfolio_id ASC, position ASC
            """,
            tuple(portfolio_ids),
        )
        for row in direct_objective_rows:
            scoped_portfolio_id = row.get("portfolio_id")
            objective_id = row["objective_id"]
            if (
                scoped_portfolio_id in objective_map
                and objective_id not in objective_seen[scoped_portfolio_id]
            ):
                direct_objective_map[scoped_portfolio_id].append(objective_id)
                objective_map[scoped_portfolio_id].append(objective_id)
                objective_seen[scoped_portfolio_id].add(objective_id)

        objective_rows = await self.db.fetch_all(
            f"""
            SELECT o.id, p.portfolio_id
            FROM objectives o
            INNER JOIN goals g ON g.id = o.goal_id
            INNER JOIN projects p ON p.id = g.project_id
            WHERE p.portfolio_id IN ({placeholders})
            ORDER BY o.updated_at DESC, o.id
            """,
            tuple(portfolio_ids),
        )
        for row in objective_rows:
            scoped_portfolio_id = row.get("portfolio_id")
            objective_id = row["id"]
            if (
                scoped_portfolio_id in objective_map
                and objective_id not in objective_seen[scoped_portfolio_id]
            ):
                objective_map[scoped_portfolio_id].append(objective_id)
                objective_seen[scoped_portfolio_id].add(objective_id)

        for portfolio_id, portfolio in portfolio_by_id.items():
            portfolio.project_ids = tuple(project_map[portfolio_id])
            portfolio.goal_ids = tuple(direct_goal_map[portfolio_id])
            portfolio.objective_ids = tuple(direct_objective_map[portfolio_id])
            portfolio.effective_goal_ids = tuple(goal_map[portfolio_id])
            portfolio.effective_objective_ids = tuple(objective_map[portfolio_id])

    async def _load_direct_goal_ids(self, portfolio_id: str) -> tuple[str, ...]:
        rows = await self.db.fetch_all(
            """
            SELECT goal_id
            FROM portfolio_goals
            WHERE portfolio_id = ?
            ORDER BY position ASC
            """,
            (portfolio_id,),
        )
        return tuple(str(row["goal_id"]) for row in rows)

    async def _load_direct_objective_ids(self, portfolio_id: str) -> tuple[str, ...]:
        rows = await self.db.fetch_all(
            """
            SELECT objective_id
            FROM portfolio_objectives
            WHERE portfolio_id = ?
            ORDER BY position ASC
            """,
            (portfolio_id,),
        )
        return tuple(str(row["objective_id"]) for row in rows)

    async def _sync_goal_links_in_transaction(
        self, portfolio_id: str, goal_ids: list[str]
    ) -> None:
        self._assert_owned_transaction("_sync_goal_links_in_transaction")
        await self.db.execute(
            "DELETE FROM portfolio_goals WHERE portfolio_id = ?",
            (portfolio_id,),
        )
        if not goal_ids:
            return
        await self.db.execute_many(
            """
            INSERT INTO portfolio_goals (portfolio_id, goal_id, position)
            VALUES (?, ?, ?)
            """,
            [
                (portfolio_id, goal_id, position)
                for position, goal_id in enumerate(goal_ids)
            ],
        )

    async def _sync_objective_links_in_transaction(
        self,
        portfolio_id: str,
        objective_ids: list[str],
    ) -> None:
        self._assert_owned_transaction("_sync_objective_links_in_transaction")
        await self.db.execute(
            "DELETE FROM portfolio_objectives WHERE portfolio_id = ?",
            (portfolio_id,),
        )
        if not objective_ids:
            return
        await self.db.execute_many(
            """
            INSERT INTO portfolio_objectives (portfolio_id, objective_id, position)
            VALUES (?, ?, ?)
            """,
            [
                (portfolio_id, objective_id, position)
                for position, objective_id in enumerate(objective_ids)
            ],
        )

    async def _apply_events(self, events: list[Any]) -> Portfolio | None:
        """Rebuild portfolio state from events."""
        if not events:
            return None

        portfolio: Portfolio | None = None

        for event in events:
            payload = event.payload
            match event.event_type:
                case EventType.PORTFOLIO_CREATED:
                    portfolio = Portfolio(
                        id=event.aggregate_id,
                        org_id=payload.get("org_id"),
                        name=payload.get("name", ""),
                        description=payload.get("description"),
                        status=PortfolioStatus.ACTIVE,
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
                case EventType.PORTFOLIO_UPDATED if portfolio:
                    changes = payload.get("changes", {})
                    for field, (_, new_val) in changes.items():
                        match field:
                            case "name":
                                portfolio.name = new_val
                            case "description":
                                portfolio.description = new_val
                            case "status":
                                portfolio.status = PortfolioStatus(new_val)
                            case "owner":
                                portfolio.owner = new_val
                            case "owner_id":
                                portfolio.owner_id = new_val
                            case "project_ids":
                                portfolio.project_ids = tuple(new_val)
                            case "goal_ids":
                                portfolio.goal_ids = tuple(new_val)
                            case "objective_ids":
                                portfolio.objective_ids = tuple(new_val)
                            case "effective_goal_ids":
                                portfolio.effective_goal_ids = tuple(new_val)
                            case "effective_objective_ids":
                                portfolio.effective_objective_ids = tuple(new_val)
                            case "tags":
                                portfolio.tags = tuple(new_val)
                            case _:
                                pass
                case EventType.PORTFOLIO_ARCHIVED if portfolio:
                    portfolio.status = PortfolioStatus.ARCHIVED

        return portfolio
