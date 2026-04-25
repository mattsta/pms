"""Service for unified work snapshots and review digests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.models.json_types import JsonObject, JsonValue, ModelObject
from pms.models.task import Task
from pms.models.value_contracts import RiskLevel
from pms.models.work_snapshot import WorkSnapshotReview
from pms.repositories.base import QueryResult
from pms.repositories.portfolio_repository import PortfolioRepository
from pms.repositories.program_repository import ProgramRepository
from pms.repositories.work_snapshot_review_repository import (
    WorkSnapshotReviewRepository,
)
from pms.services.evidence_gate_service import (
    EvidenceGateIndicator,
    EvidenceGateService,
)
from pms.services.hierarchy_scope_service import HierarchyScopeService
from pms.services.lineage_service import LineageService
from pms.services.organization_service import OrganizationService
from pms.services.portfolio_service import PortfolioService
from pms.services.program_service import ProgramService
from pms.services.project_service import ProjectService, ProjectSummary
from pms.services.task_service import TaskService
from pms.services.test_run_retention_service import TestRunRetentionService
from pms.utils.cli_commands import normalize_command_links

if TYPE_CHECKING:
    from pms.db.connection import Database

type WorkSnapshotRetentionPayload = ModelObject
type WorkSnapshotLineagePayload = ModelObject
type WorkSnapshotActionPayload = ModelObject
type SqlParam = str | int
type SqlParams = list[SqlParam]


@dataclass
class WorkSnapshotDigest:
    """Digest of changes since the last review."""

    since: datetime | None
    note: str | None
    tasks_created: int
    tasks_completed: int
    tasks_updated: int
    plans_created: int
    plans_updated: int
    test_runs: int
    failed_test_runs: int
    evidence_added: int

    def to_dict(self) -> ModelObject:
        return {
            "since": self.since.isoformat() if self.since else None,
            "note": self.note,
            "tasks_created": self.tasks_created,
            "tasks_completed": self.tasks_completed,
            "tasks_updated": self.tasks_updated,
            "plans_created": self.plans_created,
            "plans_updated": self.plans_updated,
            "test_runs": self.test_runs,
            "failed_test_runs": self.failed_test_runs,
            "evidence_added": self.evidence_added,
        }


@dataclass
class WorkSnapshotDigestResult:
    """Digest summary for a snapshot scope."""

    scope_type: str
    scope_id: str
    last_reviewed_at: datetime | None
    digest: WorkSnapshotDigest

    def to_dict(self) -> ModelObject:
        return {
            "scope_type": self.scope_type,
            "scope_id": self.scope_id,
            "last_reviewed_at": self.last_reviewed_at.isoformat()
            if self.last_reviewed_at
            else None,
            "digest": self.digest.to_dict(),
        }


@dataclass
class WorkSnapshotUsageSummary:
    """Evidence + retention summary for a snapshot scope."""

    scope_type: str
    scope_id: str
    last_reviewed_at: datetime | None
    evidence: WorkSnapshotEvidence
    retention: WorkSnapshotRetentionPayload | None

    def to_dict(self) -> ModelObject:
        return {
            "scope_type": self.scope_type,
            "scope_id": self.scope_id,
            "last_reviewed_at": self.last_reviewed_at.isoformat()
            if self.last_reviewed_at
            else None,
            "evidence": self.evidence.to_dict(),
            "retention": self.retention,
        }


@dataclass
class WorkSnapshotTotals:
    """Totals for a snapshot scope."""

    total_projects: int | None = None
    total_goals: int | None = None
    total_objectives: int | None = None
    total_tasks: int | None = None
    completed_tasks: int | None = None
    blocked_tasks: int | None = None
    overdue_tasks: int | None = None
    health_score: float | None = None
    risk_level: RiskLevel | None = None

    def to_dict(self) -> ModelObject:
        return {
            "total_projects": self.total_projects,
            "total_goals": self.total_goals,
            "total_objectives": self.total_objectives,
            "total_tasks": self.total_tasks,
            "completed_tasks": self.completed_tasks,
            "blocked_tasks": self.blocked_tasks,
            "overdue_tasks": self.overdue_tasks,
            "health_score": self.health_score,
            "risk_level": self.risk_level,
        }


@dataclass
class WorkSnapshotTaskHighlight:
    """Recent task update summary."""

    id: str
    title: str
    status: str
    project_id: str
    updated_at: datetime
    evidence_gate: EvidenceGateIndicator | None = None

    def to_dict(self) -> ModelObject:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "project_id": self.project_id,
            "updated_at": self.updated_at.isoformat(),
            "evidence_gate": (
                self.evidence_gate.to_dict() if self.evidence_gate else None
            ),
        }


@dataclass
class WorkSnapshotRunHighlight:
    """Recent test run summary."""

    id: str
    project_id: str | None
    success: bool
    finished_at: datetime
    command: str | None

    def to_dict(self) -> ModelObject:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "success": self.success,
            "finished_at": self.finished_at.isoformat(),
            "command": self.command,
        }


@dataclass
class WorkSnapshotEvidence:
    """Evidence summary for a snapshot scope."""

    total_count: int
    new_count: int

    def to_dict(self) -> ModelObject:
        return {
            "total_count": self.total_count,
            "new_count": self.new_count,
        }


@dataclass
class WorkSnapshot:
    """Unified work snapshot response."""

    scope_type: str
    scope_id: str
    scope_name: str | None
    generated_at: datetime
    last_reviewed_at: datetime | None
    totals: WorkSnapshotTotals
    digest: WorkSnapshotDigest
    evidence: WorkSnapshotEvidence
    retention: WorkSnapshotRetentionPayload | None
    lineage: WorkSnapshotLineagePayload | None
    recent_tasks: list[WorkSnapshotTaskHighlight]
    recent_test_runs: list[WorkSnapshotRunHighlight]

    def to_dict(self) -> ModelObject:
        return {
            "scope_type": self.scope_type,
            "scope_id": self.scope_id,
            "scope_name": self.scope_name,
            "generated_at": self.generated_at.isoformat(),
            "last_reviewed_at": self.last_reviewed_at.isoformat()
            if self.last_reviewed_at
            else None,
            "totals": self.totals.to_dict(),
            "digest": self.digest.to_dict(),
            "evidence": self.evidence.to_dict(),
            "retention": self.retention,
            "lineage": self.lineage,
            "recent_tasks": [item.to_dict() for item in self.recent_tasks],
            "recent_test_runs": [item.to_dict() for item in self.recent_test_runs],
        }


class WorkSnapshotService:
    """Service for unified snapshot views and review tracking."""

    def __init__(
        self,
        db: Database,
        metrics: MetricsCollector,
        project_service: ProjectService,
        organization_service: OrganizationService,
        program_service: ProgramService,
        portfolio_service: PortfolioService,
        lineage_service: LineageService,
        retention_service: TestRunRetentionService,
    ) -> None:
        self.db = db
        self.metrics = metrics
        self._project_service = project_service
        self._organization_service = organization_service
        self._program_service = program_service
        self._portfolio_service = portfolio_service
        self._lineage_service = lineage_service
        self._retention_service = retention_service

        self._review_repo = WorkSnapshotReviewRepository(db)
        event_store = EventStore(db)
        revision_store = RevisionStore(db)
        self._hierarchy = HierarchyScopeService(
            db, event_store, revision_store, metrics
        )
        self._program_repo = ProgramRepository(db, event_store, revision_store, metrics)
        self._portfolio_repo = PortfolioRepository(
            db, event_store, revision_store, metrics
        )

    async def get_snapshot(
        self,
        scope_type: str,
        scope_id: str,
        task_limit: int = 5,
        test_limit: int = 5,
    ) -> WorkSnapshot | None:
        scope_type = scope_type.lower()
        if scope_type not in {"organization", "portfolio", "program", "project"}:
            return None

        project_ids = await self._get_project_ids(scope_type, scope_id)
        scope_name = await self._get_scope_name(scope_type, scope_id)
        if scope_name is None:
            return None
        last_review = await self._review_repo.get_latest(scope_type, scope_id)
        since = last_review.reviewed_at if last_review else None

        totals = await self._get_totals(scope_type, scope_id)
        digest = await self._build_digest(project_ids, since)
        evidence = await self._build_evidence(project_ids, since)
        retention = await self._build_retention(project_ids)
        lineage = await self._build_lineage(project_ids, scope_type, scope_id)
        recent_tasks = await self._get_recent_tasks(project_ids, since, task_limit)
        recent_runs = await self._get_recent_runs(project_ids, since, test_limit)

        await self.metrics.record_counter(
            "work_snapshot.viewed",
            labels={"scope_type": scope_type},
        )
        await self.metrics.flush_best_effort(context="work_snapshot.get_snapshot")

        return WorkSnapshot(
            scope_type=scope_type,
            scope_id=scope_id,
            scope_name=scope_name,
            generated_at=datetime.now(UTC),
            last_reviewed_at=since,
            totals=totals,
            digest=digest,
            evidence=evidence,
            retention=retention,
            lineage=lineage,
            recent_tasks=recent_tasks,
            recent_test_runs=recent_runs,
        )

    async def get_digest(
        self,
        scope_type: str,
        scope_id: str,
    ) -> WorkSnapshotDigestResult | None:
        scope_type = scope_type.lower()
        if scope_type not in {"organization", "portfolio", "program", "project"}:
            return None
        if await self._get_scope_name(scope_type, scope_id) is None:
            return None

        project_ids = await self._get_project_ids(scope_type, scope_id)
        last_review = await self._review_repo.get_latest(scope_type, scope_id)
        since = last_review.reviewed_at if last_review else None
        digest = await self._build_digest(project_ids, since)

        return WorkSnapshotDigestResult(
            scope_type=scope_type,
            scope_id=scope_id,
            last_reviewed_at=since,
            digest=digest,
        )

    async def get_usage_summary(
        self,
        scope_type: str,
        scope_id: str,
    ) -> WorkSnapshotUsageSummary | None:
        """Fetch evidence + retention usage for a scope."""
        scope_type = scope_type.lower()
        if scope_type not in {"organization", "portfolio", "program", "project"}:
            return None
        if await self._get_scope_name(scope_type, scope_id) is None:
            return None

        project_ids = await self._get_project_ids(scope_type, scope_id)
        last_review = await self._review_repo.get_latest(scope_type, scope_id)
        since = last_review.reviewed_at if last_review else None
        evidence = await self._build_evidence(project_ids, since)
        retention = await self._build_retention(project_ids)

        return WorkSnapshotUsageSummary(
            scope_type=scope_type,
            scope_id=scope_id,
            last_reviewed_at=since,
            evidence=evidence,
            retention=retention,
        )

    async def get_project_ids_for_scope(
        self,
        scope_type: str,
        scope_id: str,
    ) -> list[str]:
        scope_type = scope_type.lower()
        if scope_type not in {"organization", "portfolio", "program", "project"}:
            return []
        return await self._get_project_ids(scope_type, scope_id)

    async def get_next_actions(
        self,
        scope_type: str,
        scope_id: str,
        task_service: TaskService,
        project_service: ProjectService,
        limit: int = 3,
    ) -> list[WorkSnapshotActionPayload]:
        project_ids = await self.get_project_ids_for_scope(scope_type, scope_id)
        if not project_ids or limit <= 0:
            return []

        per_project_limit = max(1, min(limit, 3))
        candidates: list[Task] = []
        for project_id in project_ids:
            result = await task_service.list_ready_tasks(
                project_id=project_id,
                limit=per_project_limit,
                offset=0,
            )
            candidates.extend(result.items)

        if not candidates:
            return []

        unique: dict[str, Task] = {task.id: task for task in candidates}
        tasks = list(unique.values())

        priority_rank = {"critical": 3, "high": 2, "medium": 1, "low": 0}
        tasks.sort(
            key=lambda task: (
                priority_rank.get(task.priority.value, 0),
                task.updated_at or datetime.min.replace(tzinfo=UTC),
            ),
            reverse=True,
        )
        tasks = tasks[:limit]

        project_names: dict[str, str | None] = {}
        for task in tasks:
            if task.project_id and task.project_id not in project_names:
                project = await project_service.get_project(task.project_id)
                project_names[task.project_id] = project.name if project else None

        task_ids = [task.id for task in tasks]
        activity_map = await task_service.get_last_activity_map(task_ids)
        workflow_map = await task_service.get_last_transition_map(
            task_ids, kind="workflow"
        )
        status_map = await task_service.get_last_transition_map(task_ids, kind="status")

        payload: list[WorkSnapshotActionPayload] = []
        for task in tasks:
            last_transition = (
                workflow_map.get(task.id)
                if task.workflow_id
                else status_map.get(task.id)
            )
            payload.append(
                {
                    "id": task.id,
                    "title": task.title,
                    "status": task.status.value,
                    "priority": task.priority.value,
                    "project_id": task.project_id,
                    "project_name": project_names.get(task.project_id),
                    "updated_at": task.updated_at.isoformat()
                    if task.updated_at
                    else None,
                    "last_activity_at": activity_map.get(task.id).isoformat()
                    if activity_map.get(task.id)
                    else None,
                    "last_transition_at": last_transition.isoformat()
                    if last_transition
                    else None,
                    "links": normalize_command_links(
                        {
                            "self": f"pms task show {task.id}",
                            "timeline": f"pms task timeline {task.id}",
                        }
                    ),
                }
            )

        return payload

    async def mark_reviewed(
        self,
        scope_type: str,
        scope_id: str,
        reviewed_by: str | None = None,
        note: str | None = None,
        metadata: JsonObject | None = None,
    ) -> WorkSnapshotReview | None:
        scope_type = scope_type.lower()
        if scope_type not in {"organization", "portfolio", "program", "project"}:
            return None
        if await self._get_scope_name(scope_type, scope_id) is None:
            return None

        async with self.db.transaction():
            review = await self._review_repo.create(
                scope_type=scope_type,
                scope_id=scope_id,
                reviewed_by=reviewed_by,
                note=note,
                metadata=metadata,
            )
            await self.metrics.record_counter(
                "work_snapshot.reviewed",
                labels={"scope_type": scope_type},
            )
            await self.metrics.flush()
        return review

    async def list_reviews(
        self,
        scope_type: str,
        scope_id: str,
        limit: int = 5,
        offset: int = 0,
    ) -> QueryResult[WorkSnapshotReview]:
        """List review history for a snapshot scope."""
        return await self._review_repo.list_reviews(
            scope_type=scope_type,
            scope_id=scope_id,
            limit=limit,
            offset=offset,
        )

    async def _get_scope_name(self, scope_type: str, scope_id: str) -> str | None:
        match scope_type:
            case "project":
                project = await self._project_service.get_project(scope_id)
                return project.name if project else None
            case "portfolio":
                portfolio = await self._portfolio_service.get_portfolio(scope_id)
                return portfolio.name if portfolio else None
            case "program":
                program = await self._program_service.get_program(scope_id)
                return program.name if program else None
            case "organization":
                org = await self._organization_service.get_organization(scope_id)
                return org.name if org else None
            case _:
                return None

    async def _get_project_ids(self, scope_type: str, scope_id: str) -> list[str]:
        match scope_type:
            case "project":
                return [scope_id]
            case "portfolio":
                return await self._hierarchy.get_project_ids_for_scope(
                    "portfolio",
                    scope_id,
                )
            case "program":
                return await self._hierarchy.get_project_ids_for_scope(
                    "program",
                    scope_id,
                )
            case "organization":
                return await self._hierarchy.get_project_ids_for_scope(
                    "organization",
                    scope_id,
                )
            case _:
                return []

    async def _get_totals(self, scope_type: str, scope_id: str) -> WorkSnapshotTotals:
        match scope_type:
            case "project":
                summary: (
                    ProjectSummary | None
                ) = await self._project_service.get_project_summary(scope_id)
                if summary is None:
                    return WorkSnapshotTotals()
                stats = summary.stats
                return WorkSnapshotTotals(
                    total_projects=1,
                    total_goals=stats.total_goals,
                    total_tasks=stats.total_tasks,
                    completed_tasks=stats.completed_tasks,
                    blocked_tasks=stats.blocked_tasks,
                    overdue_tasks=stats.overdue_tasks,
                    health_score=summary.health_score,
                )
            case "program":
                summary = await self._program_service.get_program_summary(scope_id)
                if summary is None:
                    return WorkSnapshotTotals()
                stats = summary.stats
                return WorkSnapshotTotals(
                    total_projects=stats.total_projects,
                    total_goals=stats.total_goals,
                    total_objectives=stats.total_objectives,
                    total_tasks=stats.total_tasks,
                    blocked_tasks=stats.blocked_tasks,
                    risk_level=summary.risk_level,
                )
            case "portfolio":
                summary = await self._portfolio_service.get_portfolio_summary(scope_id)
                if summary is None:
                    return WorkSnapshotTotals()
                stats = summary.stats
                return WorkSnapshotTotals(
                    total_projects=stats.total_projects,
                    total_goals=stats.total_goals,
                    total_objectives=stats.total_objectives,
                    total_tasks=stats.total_tasks,
                    blocked_tasks=stats.blocked_tasks,
                    risk_level=summary.risk_level,
                )
            case "organization":
                summary = await self._organization_service.get_organization_summary(
                    scope_id
                )
                if summary is None:
                    return WorkSnapshotTotals()
                stats = summary.stats
                return WorkSnapshotTotals(
                    total_projects=stats.total_projects,
                    total_goals=stats.total_goals,
                    total_objectives=stats.total_objectives,
                    total_tasks=stats.total_tasks,
                    blocked_tasks=stats.blocked_tasks,
                    risk_level=summary.risk_level,
                )
            case _:
                return WorkSnapshotTotals()

    async def _build_digest(
        self,
        project_ids: list[str],
        since: datetime | None,
    ) -> WorkSnapshotDigest:
        note = None
        if since is None:
            note = "No prior review recorded. Counts reflect all history."

        tasks_created = await self._count_tasks(project_ids, "created_at", since)
        tasks_completed = await self._count_tasks(project_ids, "completed_at", since)
        tasks_updated = await self._count_tasks(
            project_ids, "updated_at", since, exclude_created=True
        )
        plans_created = await self._count_plans(project_ids, "created_at", since)
        plans_updated = await self._count_plans(
            project_ids, "updated_at", since, exclude_created=True
        )
        test_runs, failed_runs = await self._count_test_runs(project_ids, since)
        evidence_added = await self._count_evidence(project_ids, since)

        return WorkSnapshotDigest(
            since=since,
            note=note,
            tasks_created=tasks_created,
            tasks_completed=tasks_completed,
            tasks_updated=tasks_updated,
            plans_created=plans_created,
            plans_updated=plans_updated,
            test_runs=test_runs,
            failed_test_runs=failed_runs,
            evidence_added=evidence_added,
        )

    async def _build_evidence(
        self,
        project_ids: list[str],
        since: datetime | None,
    ) -> WorkSnapshotEvidence:
        total_count = await self._count_evidence(project_ids, None)
        new_count = await self._count_evidence(project_ids, since)
        return WorkSnapshotEvidence(total_count=total_count, new_count=new_count)

    async def _build_retention(
        self, project_ids: list[str]
    ) -> WorkSnapshotRetentionPayload | None:
        if not project_ids:
            return None
        summary = await self._retention_service.get_usage(
            limit=5, sort="largest", project_ids=project_ids
        )
        return summary.to_dict()

    async def _build_lineage(
        self,
        project_ids: list[str],
        scope_type: str,
        scope_id: str,
    ) -> WorkSnapshotLineagePayload | None:
        if not project_ids:
            return None

        items: list[ModelObject] = []
        total_plans = 0
        total_tasks = 0
        total_test_runs = 0
        failed_test_runs = 0

        for project_id in project_ids[:5]:
            dashboard = await self._lineage_service.get_plan_lineage_dashboard(
                project_id=project_id,
                limit=3,
                task_limit=3,
                test_limit=2,
            )
            total_plans += dashboard.total_plans
            total_tasks += dashboard.total_tasks
            total_test_runs += dashboard.total_test_runs
            failed_test_runs += dashboard.failed_test_runs
            for item in dashboard.items:
                items.append(
                    {
                        "plan": {
                            "id": item.plan.id,
                            "name": item.plan.name,
                            "status": item.plan.status.value,
                            "project_id": item.plan.project_id,
                        },
                        "stats": {
                            "total_tasks": item.total_tasks,
                            "completed_tasks": item.completed_tasks,
                            "blocked_tasks": item.blocked_tasks,
                            "total_test_runs": item.total_test_runs,
                            "latest_test_success": item.latest_test_success,
                        },
                    }
                )

        return {
            "scope_type": scope_type,
            "scope_id": scope_id,
            "items": items,
            "totals": {
                "total_plans": total_plans,
                "total_tasks": total_tasks,
                "total_test_runs": total_test_runs,
                "failed_test_runs": failed_test_runs,
            },
        }

    async def _get_recent_tasks(
        self,
        project_ids: list[str],
        since: datetime | None,
        limit: int,
    ) -> list[WorkSnapshotTaskHighlight]:
        if not project_ids:
            return []
        placeholders = ", ".join("?" * len(project_ids))
        params: SqlParams = list(project_ids)

        where = f"project_id IN ({placeholders})"
        if since:
            where += " AND updated_at >= ?"
            params.append(since.isoformat())

        rows = await self.db.fetch_all(
            f"""
            SELECT id, title, status, project_id, updated_at, workflow_id, current_state
            FROM tasks
            WHERE {where}
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (*params, limit),
        )
        gate_service = EvidenceGateService(self.db, self.metrics)
        results: list[WorkSnapshotTaskHighlight] = []
        for row in rows:
            task_id = self._as_text(row.get("id"))
            evidence_gate = await gate_service.get_task_indicator(
                task_id=task_id,
                workflow_id=self._as_optional_text(row.get("workflow_id")),
                current_state=self._as_optional_text(row.get("current_state")),
            )
            results.append(
                WorkSnapshotTaskHighlight(
                    id=task_id,
                    title=self._as_text(row.get("title")),
                    status=self._as_text(row.get("status")),
                    project_id=self._as_text(row.get("project_id")),
                    updated_at=self._as_datetime(
                        row.get("updated_at"),
                        fallback=datetime.now(UTC),
                    ),
                    evidence_gate=evidence_gate,
                )
            )
        return results

    async def _get_recent_runs(
        self,
        project_ids: list[str],
        since: datetime | None,
        limit: int,
    ) -> list[WorkSnapshotRunHighlight]:
        if not project_ids:
            return []
        placeholders = ", ".join("?" * len(project_ids))
        params: SqlParams = list(project_ids)

        where = f"project_id IN ({placeholders})"
        if since:
            where += " AND finished_at >= ?"
            params.append(since.isoformat())

        rows = await self.db.fetch_all(
            f"""
            SELECT id, project_id, success, finished_at, config
            FROM test_runs
            WHERE {where}
            ORDER BY finished_at DESC
            LIMIT ?
            """,
            (*params, limit),
        )

        results: list[WorkSnapshotRunHighlight] = []
        for row in rows:
            config = self._safe_json(row.get("config"))
            command = self._as_optional_text(config.get("test_command"))
            results.append(
                WorkSnapshotRunHighlight(
                    id=self._as_text(row.get("id")),
                    project_id=self._as_optional_text(row.get("project_id")),
                    success=self._as_bool(row.get("success")),
                    finished_at=self._as_datetime(
                        row.get("finished_at"),
                        fallback=datetime.now(UTC),
                    ),
                    command=command,
                )
            )
        return results

    async def _count_tasks(
        self,
        project_ids: list[str],
        column: str,
        since: datetime | None,
        exclude_created: bool = False,
    ) -> int:
        if not project_ids:
            return 0
        placeholders = ", ".join("?" * len(project_ids))
        params: SqlParams = list(project_ids)

        where = f"project_id IN ({placeholders}) AND {column} IS NOT NULL"
        if since:
            where += f" AND {column} >= ?"
            params.append(since.isoformat())
            if exclude_created and column == "updated_at":
                where += " AND created_at < ?"
                params.append(since.isoformat())

        row = await self.db.fetch_one(
            f"SELECT COUNT(*) as count FROM tasks WHERE {where}",
            tuple(params),
        )
        return self._row_count(row)

    async def _count_plans(
        self,
        project_ids: list[str],
        column: str,
        since: datetime | None,
        exclude_created: bool = False,
    ) -> int:
        if not project_ids:
            return 0
        placeholders = ", ".join("?" * len(project_ids))
        params: SqlParams = list(project_ids)

        where = f"project_id IN ({placeholders}) AND {column} IS NOT NULL"
        if since:
            where += f" AND {column} >= ?"
            params.append(since.isoformat())
            if exclude_created and column == "updated_at":
                where += " AND created_at < ?"
                params.append(since.isoformat())

        row = await self.db.fetch_one(
            f"SELECT COUNT(*) as count FROM plans WHERE {where}",
            tuple(params),
        )
        return self._row_count(row)

    async def _count_test_runs(
        self,
        project_ids: list[str],
        since: datetime | None,
    ) -> tuple[int, int]:
        if not project_ids:
            return 0, 0
        placeholders = ", ".join("?" * len(project_ids))
        params: SqlParams = list(project_ids)

        where = f"project_id IN ({placeholders}) AND finished_at IS NOT NULL"
        if since:
            where += " AND finished_at >= ?"
            params.append(since.isoformat())

        rows = await self.db.fetch_all(
            f"SELECT success FROM test_runs WHERE {where}",
            tuple(params),
        )
        total = len(rows)
        failed = sum(1 for row in rows if not self._as_bool(row.get("success")))
        return total, failed

    async def _count_evidence(
        self,
        project_ids: list[str],
        since: datetime | None,
    ) -> int:
        if not project_ids:
            return 0
        placeholders = ", ".join("?" * len(project_ids))
        params: SqlParams = list(project_ids)

        where = f"t.project_id IN ({placeholders})"
        if since:
            where += " AND e.created_at >= ?"
            params.append(since.isoformat())

        row = await self.db.fetch_one(
            f"""
            SELECT COUNT(*) as count
            FROM task_evidence e
            JOIN tasks t ON t.id = e.task_id
            WHERE {where}
            """,
            tuple(params),
        )
        return self._row_count(row)

    def _safe_json(self, raw: JsonValue | datetime | None) -> JsonObject:
        if raw is None:
            return {}
        if isinstance(raw, dict):
            payload: JsonObject = {}
            for key, value in raw.items():
                payload[str(key)] = self._coerce_json_value(value)
            return payload
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    payload = {}
                    for key, value in parsed.items():
                        payload[str(key)] = self._coerce_json_value(value)
                    return payload
                return {}
            except json.JSONDecodeError:
                return {}
        return {}

    def _coerce_json_value(self, raw: JsonValue | None) -> JsonValue:
        if isinstance(raw, dict):
            payload: JsonObject = {}
            for key, value in raw.items():
                payload[str(key)] = self._coerce_json_value(value)
            return payload
        if isinstance(raw, list):
            return [self._coerce_json_value(value) for value in raw]
        if isinstance(raw, (str, int, float, bool)) or raw is None:
            return raw
        return str(raw)

    def _as_text(self, raw: JsonValue | datetime | None) -> str:
        if raw is None:
            return ""
        if isinstance(raw, datetime):
            return raw.isoformat()
        if isinstance(raw, (str, int, float, bool)):
            return str(raw)
        return str(raw)

    def _as_optional_text(self, raw: JsonValue | datetime | None) -> str | None:
        if raw is None:
            return None
        text = self._as_text(raw)
        return text or None

    def _as_bool(self, raw: JsonValue | datetime | None) -> bool:
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, int):
            return raw != 0
        if isinstance(raw, float):
            return raw != 0.0
        if isinstance(raw, str):
            return raw.lower() in {"1", "true", "yes", "y"}
        return False

    def _as_int(self, raw: JsonValue | datetime | None) -> int:
        if isinstance(raw, bool):
            return int(raw)
        if isinstance(raw, int):
            return raw
        if isinstance(raw, float):
            return int(raw)
        if isinstance(raw, str):
            try:
                return int(float(raw))
            except ValueError:
                return 0
        return 0

    def _as_datetime(
        self, raw: JsonValue | datetime | None, *, fallback: datetime
    ) -> datetime:
        if isinstance(raw, datetime):
            return raw
        if isinstance(raw, str):
            try:
                return datetime.fromisoformat(raw)
            except ValueError:
                return fallback
        return fallback

    def _row_count(self, row: dict[str, JsonValue] | None) -> int:
        if row is None:
            return 0
        return self._as_int(row.get("count"))
