"""Authoritative hierarchy scope resolution across portfolio/program/org graphs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.models import Goal, Objective, Project
from pms.repositories.base import QueryResult
from pms.repositories.goal_repository import GoalRepository
from pms.repositories.objective_repository import ObjectiveRepository
from pms.repositories.project_repository import ProjectRepository

if TYPE_CHECKING:
    from pms.db.connection import Database


@dataclass
class HierarchyScopeSnapshot:
    """Derived linked entities for a hierarchy scope."""

    projects: QueryResult[Project]
    goals: QueryResult[Goal]
    objectives: QueryResult[Objective]


class HierarchyScopeService:
    """Resolve authoritative scope relationships from foreign-key graph edges."""

    def __init__(
        self,
        db: Database,
        event_store: EventStore,
        revision_store: RevisionStore,
        metrics: MetricsCollector,
    ) -> None:
        self.db = db
        self._project_repo = ProjectRepository(db, event_store, revision_store, metrics)
        self._goal_repo = GoalRepository(db, event_store, revision_store, metrics)
        self._objective_repo = ObjectiveRepository(
            db, event_store, revision_store, metrics
        )

    def _project_where(
        self,
        *,
        org_id: str | None = None,
        portfolio_id: str | None = None,
        program_id: str | None = None,
        project_id: str | None = None,
    ) -> tuple[str, tuple[Any, ...]]:
        conditions: list[str] = []
        params: list[Any] = []
        if project_id is not None:
            conditions.append("id = ?")
            params.append(project_id)
        if org_id is not None:
            conditions.append("org_id = ?")
            params.append(org_id)
        if portfolio_id is not None:
            conditions.append("portfolio_id = ?")
            params.append(portfolio_id)
        if program_id is not None:
            conditions.append("program_id = ?")
            params.append(program_id)
        if not conditions:
            return "", ()
        return f"WHERE {' AND '.join(conditions)}", tuple(params)

    def _goal_where(
        self,
        *,
        org_id: str | None = None,
        portfolio_id: str | None = None,
        program_id: str | None = None,
        project_id: str | None = None,
    ) -> tuple[str, tuple[Any, ...]]:
        conditions: list[str] = []
        params: list[Any] = []
        if project_id is not None:
            conditions.append("g.project_id = ?")
            params.append(project_id)
        if org_id is not None:
            conditions.append("p.org_id = ?")
            params.append(org_id)
        if portfolio_id is not None:
            conditions.append("p.portfolio_id = ?")
            params.append(portfolio_id)
        if program_id is not None:
            conditions.append("p.program_id = ?")
            params.append(program_id)
        if not conditions:
            return "", ()
        return f"WHERE {' AND '.join(conditions)}", tuple(params)

    def _objective_where(
        self,
        *,
        org_id: str | None = None,
        portfolio_id: str | None = None,
        program_id: str | None = None,
        project_id: str | None = None,
    ) -> tuple[str, tuple[Any, ...]]:
        conditions: list[str] = []
        params: list[Any] = []
        if project_id is not None:
            conditions.append("p.id = ?")
            params.append(project_id)
        if org_id is not None:
            conditions.append("p.org_id = ?")
            params.append(org_id)
        if portfolio_id is not None:
            conditions.append("p.portfolio_id = ?")
            params.append(portfolio_id)
        if program_id is not None:
            conditions.append("p.program_id = ?")
            params.append(program_id)
        if not conditions:
            return "", ()
        return f"WHERE {' AND '.join(conditions)}", tuple(params)

    async def list_projects(
        self,
        *,
        org_id: str | None = None,
        portfolio_id: str | None = None,
        program_id: str | None = None,
        project_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Project]:
        """List projects in authoritative hierarchy scope."""
        where_sql, params = self._project_where(
            org_id=org_id,
            portfolio_id=portfolio_id,
            program_id=program_id,
            project_id=project_id,
        )
        if not where_sql:
            return QueryResult(items=[], total_count=0, offset=offset, limit=limit)
        count_row = await self.db.fetch_one(
            f"SELECT COUNT(*) AS count FROM projects {where_sql}",
            params,
        )
        total = int(count_row["count"] or 0) if count_row else 0
        rows = await self.db.fetch_all(
            f"""
            SELECT * FROM projects
            {where_sql}
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        )
        return QueryResult(
            items=[self._project_repo._model_from_row(row) for row in rows],
            total_count=total,
            offset=offset,
            limit=limit,
        )

    async def list_goals(
        self,
        *,
        org_id: str | None = None,
        portfolio_id: str | None = None,
        program_id: str | None = None,
        project_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Goal]:
        """List goals in authoritative hierarchy scope."""
        if portfolio_id is not None and project_id is None and program_id is None:
            return await self._list_portfolio_goals(
                portfolio_id=portfolio_id,
                org_id=org_id,
                limit=limit,
                offset=offset,
            )
        if program_id is not None and project_id is None:
            return await self._list_program_goals(
                program_id=program_id,
                org_id=org_id,
                portfolio_id=portfolio_id,
                limit=limit,
                offset=offset,
            )
        where_sql, params = self._goal_where(
            org_id=org_id,
            portfolio_id=portfolio_id,
            program_id=program_id,
            project_id=project_id,
        )
        if not where_sql:
            return QueryResult(items=[], total_count=0, offset=offset, limit=limit)
        count_row = await self.db.fetch_one(
            f"""
            SELECT COUNT(*) AS count
            FROM goals g
            INNER JOIN projects p ON p.id = g.project_id
            {where_sql}
            """,
            params,
        )
        total = int(count_row["count"] or 0) if count_row else 0
        rows = await self.db.fetch_all(
            f"""
            SELECT g.*
            FROM goals g
            INNER JOIN projects p ON p.id = g.project_id
            {where_sql}
            ORDER BY g.updated_at DESC
            LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        )
        return QueryResult(
            items=[self._goal_repo._model_from_row(row) for row in rows],
            total_count=total,
            offset=offset,
            limit=limit,
        )

    async def list_objectives(
        self,
        *,
        org_id: str | None = None,
        portfolio_id: str | None = None,
        program_id: str | None = None,
        project_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Objective]:
        """List objectives in authoritative hierarchy scope."""
        if portfolio_id is not None and project_id is None and program_id is None:
            return await self._list_portfolio_objectives(
                portfolio_id=portfolio_id,
                org_id=org_id,
                limit=limit,
                offset=offset,
            )
        if program_id is not None and project_id is None:
            return await self._list_program_objectives(
                program_id=program_id,
                org_id=org_id,
                portfolio_id=portfolio_id,
                limit=limit,
                offset=offset,
            )
        where_sql, params = self._objective_where(
            org_id=org_id,
            portfolio_id=portfolio_id,
            program_id=program_id,
            project_id=project_id,
        )
        if not where_sql:
            return QueryResult(items=[], total_count=0, offset=offset, limit=limit)
        count_row = await self.db.fetch_one(
            f"""
            SELECT COUNT(*) AS count
            FROM objectives o
            INNER JOIN goals g ON g.id = o.goal_id
            INNER JOIN projects p ON p.id = g.project_id
            {where_sql}
            """,
            params,
        )
        total = int(count_row["count"] or 0) if count_row else 0
        rows = await self.db.fetch_all(
            f"""
            SELECT o.*
            FROM objectives o
            INNER JOIN goals g ON g.id = o.goal_id
            INNER JOIN projects p ON p.id = g.project_id
            {where_sql}
            ORDER BY o.updated_at DESC
            LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        )
        return QueryResult(
            items=[self._objective_repo._model_from_row(row) for row in rows],
            total_count=total,
            offset=offset,
            limit=limit,
        )

    async def _list_portfolio_goals(
        self,
        *,
        portfolio_id: str,
        org_id: str | None,
        limit: int,
        offset: int,
    ) -> QueryResult[Goal]:
        base_filters = ["pfo.id = ?"]
        params: list[Any] = [portfolio_id]
        if org_id is not None:
            base_filters.append("pfo.org_id = ?")
            params.append(org_id)
        where_clause = " AND ".join(base_filters)

        count_row = await self.db.fetch_one(
            f"""
            WITH scoped_goals AS (
                SELECT g.id
                FROM goals g
                INNER JOIN projects p ON p.id = g.project_id
                INNER JOIN portfolios pfo ON pfo.id = p.portfolio_id
                WHERE {where_clause}
                UNION
                SELECT g.id
                FROM portfolio_goals pg
                INNER JOIN goals g ON g.id = pg.goal_id
                INNER JOIN portfolios pfo ON pfo.id = pg.portfolio_id
                WHERE {where_clause}
            )
            SELECT COUNT(*) AS count
            FROM scoped_goals
            """,
            tuple([*params, *params]),
        )
        total = int(count_row["count"] or 0) if count_row else 0
        rows = await self.db.fetch_all(
            f"""
            WITH scoped_goals AS (
                SELECT g.id
                FROM goals g
                INNER JOIN projects p ON p.id = g.project_id
                INNER JOIN portfolios pfo ON pfo.id = p.portfolio_id
                WHERE {where_clause}
                UNION
                SELECT g.id
                FROM portfolio_goals pg
                INNER JOIN goals g ON g.id = pg.goal_id
                INNER JOIN portfolios pfo ON pfo.id = pg.portfolio_id
                WHERE {where_clause}
            )
            SELECT g.*
            FROM goals g
            INNER JOIN scoped_goals sg ON sg.id = g.id
            ORDER BY g.updated_at DESC, g.id
            LIMIT ? OFFSET ?
            """,
            tuple([*params, *params, limit, offset]),
        )
        return QueryResult(
            items=[self._goal_repo._model_from_row(row) for row in rows],
            total_count=total,
            offset=offset,
            limit=limit,
        )

    async def _list_program_goals(
        self,
        *,
        program_id: str,
        org_id: str | None,
        portfolio_id: str | None,
        limit: int,
        offset: int,
    ) -> QueryResult[Goal]:
        base_filters = ["pr.id = ?"]
        params: list[Any] = [program_id]
        if org_id is not None:
            base_filters.append("pr.org_id = ?")
            params.append(org_id)
        if portfolio_id is not None:
            base_filters.append("pr.portfolio_id = ?")
            params.append(portfolio_id)
        where_clause = " AND ".join(base_filters)

        count_row = await self.db.fetch_one(
            f"""
            WITH scoped_goals AS (
                SELECT g.id
                FROM goals g
                INNER JOIN projects p ON p.id = g.project_id
                INNER JOIN programs pr ON pr.id = p.program_id
                WHERE {where_clause}
                UNION
                SELECT g.id
                FROM program_goals pg
                INNER JOIN goals g ON g.id = pg.goal_id
                INNER JOIN programs pr ON pr.id = pg.program_id
                WHERE {where_clause}
            )
            SELECT COUNT(*) AS count
            FROM scoped_goals
            """,
            tuple([*params, *params]),
        )
        total = int(count_row["count"] or 0) if count_row else 0
        rows = await self.db.fetch_all(
            f"""
            WITH scoped_goals AS (
                SELECT g.id
                FROM goals g
                INNER JOIN projects p ON p.id = g.project_id
                INNER JOIN programs pr ON pr.id = p.program_id
                WHERE {where_clause}
                UNION
                SELECT g.id
                FROM program_goals pg
                INNER JOIN goals g ON g.id = pg.goal_id
                INNER JOIN programs pr ON pr.id = pg.program_id
                WHERE {where_clause}
            )
            SELECT g.*
            FROM goals g
            INNER JOIN scoped_goals sg ON sg.id = g.id
            ORDER BY g.updated_at DESC, g.id
            LIMIT ? OFFSET ?
            """,
            tuple([*params, *params, limit, offset]),
        )
        return QueryResult(
            items=[self._goal_repo._model_from_row(row) for row in rows],
            total_count=total,
            offset=offset,
            limit=limit,
        )

    async def _list_portfolio_objectives(
        self,
        *,
        portfolio_id: str,
        org_id: str | None,
        limit: int,
        offset: int,
    ) -> QueryResult[Objective]:
        base_filters = ["pfo.id = ?"]
        params: list[Any] = [portfolio_id]
        if org_id is not None:
            base_filters.append("pfo.org_id = ?")
            params.append(org_id)
        where_clause = " AND ".join(base_filters)

        count_row = await self.db.fetch_one(
            f"""
            WITH scoped_objectives AS (
                SELECT o.id
                FROM objectives o
                INNER JOIN goals g ON g.id = o.goal_id
                INNER JOIN projects p ON p.id = g.project_id
                INNER JOIN portfolios pfo ON pfo.id = p.portfolio_id
                WHERE {where_clause}
                UNION
                SELECT o.id
                FROM portfolio_objectives po
                INNER JOIN objectives o ON o.id = po.objective_id
                INNER JOIN portfolios pfo ON pfo.id = po.portfolio_id
                WHERE {where_clause}
            )
            SELECT COUNT(*) AS count
            FROM scoped_objectives
            """,
            tuple([*params, *params]),
        )
        total = int(count_row["count"] or 0) if count_row else 0
        rows = await self.db.fetch_all(
            f"""
            WITH scoped_objectives AS (
                SELECT o.id
                FROM objectives o
                INNER JOIN goals g ON g.id = o.goal_id
                INNER JOIN projects p ON p.id = g.project_id
                INNER JOIN portfolios pfo ON pfo.id = p.portfolio_id
                WHERE {where_clause}
                UNION
                SELECT o.id
                FROM portfolio_objectives po
                INNER JOIN objectives o ON o.id = po.objective_id
                INNER JOIN portfolios pfo ON pfo.id = po.portfolio_id
                WHERE {where_clause}
            )
            SELECT o.*
            FROM objectives o
            INNER JOIN scoped_objectives so ON so.id = o.id
            ORDER BY o.updated_at DESC, o.id
            LIMIT ? OFFSET ?
            """,
            tuple([*params, *params, limit, offset]),
        )
        return QueryResult(
            items=[self._objective_repo._model_from_row(row) for row in rows],
            total_count=total,
            offset=offset,
            limit=limit,
        )

    async def _list_program_objectives(
        self,
        *,
        program_id: str,
        org_id: str | None,
        portfolio_id: str | None,
        limit: int,
        offset: int,
    ) -> QueryResult[Objective]:
        base_filters = ["pr.id = ?"]
        params: list[Any] = [program_id]
        if org_id is not None:
            base_filters.append("pr.org_id = ?")
            params.append(org_id)
        if portfolio_id is not None:
            base_filters.append("pr.portfolio_id = ?")
            params.append(portfolio_id)
        where_clause = " AND ".join(base_filters)

        count_row = await self.db.fetch_one(
            f"""
            WITH scoped_objectives AS (
                SELECT o.id
                FROM objectives o
                INNER JOIN goals g ON g.id = o.goal_id
                INNER JOIN projects p ON p.id = g.project_id
                INNER JOIN programs pr ON pr.id = p.program_id
                WHERE {where_clause}
                UNION
                SELECT o.id
                FROM program_objectives po
                INNER JOIN objectives o ON o.id = po.objective_id
                INNER JOIN programs pr ON pr.id = po.program_id
                WHERE {where_clause}
            )
            SELECT COUNT(*) AS count
            FROM scoped_objectives
            """,
            tuple([*params, *params]),
        )
        total = int(count_row["count"] or 0) if count_row else 0
        rows = await self.db.fetch_all(
            f"""
            WITH scoped_objectives AS (
                SELECT o.id
                FROM objectives o
                INNER JOIN goals g ON g.id = o.goal_id
                INNER JOIN projects p ON p.id = g.project_id
                INNER JOIN programs pr ON pr.id = p.program_id
                WHERE {where_clause}
                UNION
                SELECT o.id
                FROM program_objectives po
                INNER JOIN objectives o ON o.id = po.objective_id
                INNER JOIN programs pr ON pr.id = po.program_id
                WHERE {where_clause}
            )
            SELECT o.*
            FROM objectives o
            INNER JOIN scoped_objectives so ON so.id = o.id
            ORDER BY o.updated_at DESC, o.id
            LIMIT ? OFFSET ?
            """,
            tuple([*params, *params, limit, offset]),
        )
        return QueryResult(
            items=[self._objective_repo._model_from_row(row) for row in rows],
            total_count=total,
            offset=offset,
            limit=limit,
        )

    async def get_project_ids_for_scope(
        self, scope_type: str, scope_id: str
    ) -> list[str]:
        """Return authoritative project ids for a hierarchy scope."""
        match scope_type:
            case "project":
                result = await self.list_projects(
                    project_id=scope_id, limit=100000, offset=0
                )
            case "portfolio":
                result = await self.list_projects(
                    portfolio_id=scope_id, limit=100000, offset=0
                )
            case "program":
                result = await self.list_projects(
                    program_id=scope_id, limit=100000, offset=0
                )
            case "organization":
                result = await self.list_projects(
                    org_id=scope_id, limit=100000, offset=0
                )
            case _:
                return []
        return [project.id for project in result.items]

    async def get_portfolio_snapshot(
        self,
        portfolio_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> HierarchyScopeSnapshot:
        """Return authoritative linked entities for a portfolio."""
        return HierarchyScopeSnapshot(
            projects=await self.list_projects(
                portfolio_id=portfolio_id, limit=limit, offset=offset
            ),
            goals=await self.list_goals(
                portfolio_id=portfolio_id, limit=limit, offset=offset
            ),
            objectives=await self.list_objectives(
                portfolio_id=portfolio_id, limit=limit, offset=offset
            ),
        )

    async def get_program_snapshot(
        self,
        program_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> HierarchyScopeSnapshot:
        """Return authoritative linked entities for a program."""
        return HierarchyScopeSnapshot(
            projects=await self.list_projects(
                program_id=program_id, limit=limit, offset=offset
            ),
            goals=await self.list_goals(
                program_id=program_id, limit=limit, offset=offset
            ),
            objectives=await self.list_objectives(
                program_id=program_id, limit=limit, offset=offset
            ),
        )

    async def get_organization_snapshot(
        self,
        org_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> HierarchyScopeSnapshot:
        """Return authoritative linked entities for an organization."""
        return HierarchyScopeSnapshot(
            projects=await self.list_projects(
                org_id=org_id, limit=limit, offset=offset
            ),
            goals=await self.list_goals(org_id=org_id, limit=limit, offset=offset),
            objectives=await self.list_objectives(
                org_id=org_id, limit=limit, offset=offset
            ),
        )
