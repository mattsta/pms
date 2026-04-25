"""Lineage service for plan → task → test dashboards."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime
from typing import TYPE_CHECKING

from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.models import Plan, PlanStatus, TaskStatus
from pms.models.json_types import JsonObject, JsonValue
from pms.models.task_evidence import TaskEvidence
from pms.repositories.base import RepositoryContext
from pms.repositories.plan_repository import PlanRepository
from pms.repositories.task_evidence_repository import TaskEvidenceRepository
from pms.repositories.task_repository import TaskRepository
from pms.services.evidence_gate_service import (
    EvidenceGateIndicator,
    EvidenceGateService,
)
from pms.services.plan_service import PlanService
from pms.services.rollup_utils import max_datetime

if TYPE_CHECKING:
    from pms.db.connection import Database

type TestRunRow = dict[str, JsonValue]
type TimestampSource = JsonValue | datetime


@dataclass
class LineageTaskSummary:
    """Compact task summary for lineage views."""

    id: str
    title: str
    status: str
    project_id: str
    assignee: str | None = None
    assignee_id: str | None = None
    due_date: datetime | None = None
    evidence_gate: EvidenceGateIndicator | None = None


@dataclass
class LineageTestRunSummary:
    """Compact test run summary for lineage views."""

    id: str
    server_id: str
    success: bool
    exit_code: int | None
    duration_seconds: float | None
    started_at: datetime
    finished_at: datetime
    project_id: str | None
    plan_id: str | None
    task_ids: tuple[str, ...]
    command: str | None = None


@dataclass
class LineageEvidenceSummary:
    """Evidence rollup summary for lineage views."""

    total: int
    types: dict[str, int]
    code_total: int
    latest_code_reference: str | None
    latest_code_created_at: datetime | None


@dataclass
class PlanLineageItem:
    """Lineage view for a plan with tasks and test runs."""

    plan: Plan
    tasks: list[LineageTaskSummary]
    test_runs: list[LineageTestRunSummary]
    total_tasks: int
    completed_tasks: int
    blocked_tasks: int
    total_test_runs: int
    latest_test_success: bool | None
    latest_test_run_id: str | None
    evidence: LineageEvidenceSummary
    stored_status: str | None = None
    terminal_reason: str | None = None
    last_activity_at: datetime | None = None
    last_transition_at: datetime | None = None


@dataclass
class PlanLineageDashboard:
    """Dashboard of plan lineage rollups."""

    items: list[PlanLineageItem]
    total_plans: int
    total_tasks: int
    total_test_runs: int
    failed_test_runs: int
    total_evidence: int
    total_code_evidence: int
    offset: int
    limit: int


class LineageService:
    """Service for cross-entity lineage views."""

    def __init__(
        self,
        db: Database,
        event_store: EventStore,
        revision_store: RevisionStore,
        metrics: MetricsCollector,
    ) -> None:
        self.db = db
        self.events = event_store
        self.revisions = revision_store
        self.metrics = metrics

        self._plan_repo = PlanRepository(db, event_store, revision_store, metrics)
        self._task_repo = TaskRepository(db, event_store, revision_store, metrics)
        self._evidence_repo = TaskEvidenceRepository(db)
        self._plan_service = PlanService(db, event_store, revision_store, metrics)
        self._context = RepositoryContext()

    def with_context(
        self,
        user_id: str | None = None,
        session_id: str | None = None,
        correlation_id: str | None = None,
    ) -> LineageService:
        """Set context for subsequent operations."""
        self._context = RepositoryContext(
            user_id=user_id,
            session_id=session_id,
            correlation_id=correlation_id,
        )
        self._plan_repo.with_context(self._context)
        self._task_repo.with_context(self._context)
        return self

    async def get_plan_lineage_dashboard(
        self,
        status: PlanStatus | None = None,
        project_id: str | None = None,
        plan_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
        task_limit: int = 10,
        test_limit: int = 5,
    ) -> PlanLineageDashboard:
        """Get plan → task → test lineage dashboard."""
        if plan_id:
            raw_plan = await self._plan_repo.get_by_id(plan_id)
            plans: list[Plan] = []
            total_plans = 0
            result_offset = offset
            result_limit = limit
            lifecycle_rollups = {}
            stored_status_map: dict[str, str] = {}
            if raw_plan is not None and (
                project_id is None or raw_plan.project_id == project_id
            ):
                lifecycle_rollups = await self._plan_service.get_lifecycle_rollup_map(
                    [raw_plan]
                )
                effective_plan = raw_plan
                rollup = lifecycle_rollups.get(raw_plan.id)
                if rollup is not None:
                    effective_plan = replace(raw_plan, status=rollup.effective_status)
                if status is None or effective_plan.status == status:
                    plans = [effective_plan]
                    total_plans = 1
                    stored_status_map[raw_plan.id] = raw_plan.status.value
        else:
            (
                plan_result,
                lifecycle_rollups,
                stored_status_enum_map,
            ) = await self._plan_service.list_effective_plans(
                status=status,
                project_id=project_id,
                limit=limit,
                offset=offset,
            )
            plans = plan_result.items
            total_plans = plan_result.total_count
            result_offset = plan_result.offset
            result_limit = plan_result.limit
            stored_status_map = {
                plan_id: stored_status.value
                for plan_id, stored_status in stored_status_enum_map.items()
            }

        all_task_ids = [task_id for plan in plans for task_id in plan.task_ids]
        tasks = await self._task_repo.get_by_ids(all_task_ids)
        task_map = {task.id: task for task in tasks}
        task_activity = await self._task_repo.get_last_activity_map(all_task_ids)

        plan_ids = [plan.id for plan in plans]
        plan_activity_map = await self._plan_service.get_last_activity_map(plans)
        plan_job_activity: dict[str, datetime | None] = {
            plan_id: None for plan_id in plan_ids
        }
        if plan_ids:
            placeholders = ", ".join("?" * len(plan_ids))
            job_rows = await self.db.fetch_all(
                f"""
                SELECT plan_id, MAX(updated_at) as ts
                FROM plan_test_jobs
                WHERE plan_id IN ({placeholders})
                  AND archived_at IS NULL
                GROUP BY plan_id
                """,
                tuple(plan_ids),
            )
            for row in job_rows:
                ts_raw = row.get("ts")
                plan_job_activity[row["plan_id"]] = (
                    datetime.fromisoformat(ts_raw) if ts_raw else None
                )

        plan_transitions = await self._plan_service.get_last_transition_map(plan_ids)

        evidence_items = await self._evidence_repo.list_by_task_ids(all_task_ids)
        evidence_by_task: dict[str, list[TaskEvidence]] = {}
        for evidence in evidence_items:
            evidence_by_task.setdefault(evidence.task_id, []).append(evidence)

        gate_service = EvidenceGateService(self.db, self.metrics)

        project_ids: set[str] = {plan.project_id for plan in plans if plan.project_id}
        project_ids.update(task.project_id for task in tasks if task.project_id)

        all_test_runs = await self._fetch_test_runs(
            list(project_ids), per_project_limit=test_limit
        )
        run_success_by_id = {run.id: run.success for run in all_test_runs}

        items: list[PlanLineageItem] = []
        unique_task_ids: set[str] = set()
        unique_run_ids: set[str] = set()
        unique_evidence_ids: set[str] = set()
        unique_code_evidence_ids: set[str] = set()

        for plan in plans:
            plan_tasks = [
                task_map[task_id] for task_id in plan.task_ids if task_id in task_map
            ]
            unique_task_ids.update(task.id for task in plan_tasks)

            plan_task_ids = set(plan.task_ids)
            plan_project_ids = {plan.project_id} if plan.project_id else set()
            plan_project_ids.update(task.project_id for task in plan_tasks)

            plan_evidence: list[TaskEvidence] = []
            for task_id in plan.task_ids:
                plan_evidence.extend(evidence_by_task.get(task_id, []))
            for evidence in plan_evidence:
                unique_evidence_ids.add(evidence.id)
                if self._is_code_evidence(evidence.evidence_type):
                    unique_code_evidence_ids.add(evidence.id)

            evidence_summary = self._summarize_evidence(plan_evidence)

            matching_runs = [
                run
                for run in all_test_runs
                if self._matches_plan(run, plan.id, plan_task_ids, plan_project_ids)
            ]
            unique_run_ids.update(run.id for run in matching_runs)

            latest_run = matching_runs[0] if matching_runs else None
            tasks_summary: list[LineageTaskSummary] = []
            for task in plan_tasks[:task_limit]:
                evidence_gate = await gate_service.get_task_indicator(
                    task_id=task.id,
                    workflow_id=task.workflow_id,
                    current_state=task.current_state,
                )
                tasks_summary.append(
                    LineageTaskSummary(
                        id=task.id,
                        title=task.title,
                        status=task.status.value,
                        project_id=task.project_id,
                        assignee=task.assignee,
                        assignee_id=task.assignee_id,
                        due_date=task.due_date,
                        evidence_gate=evidence_gate,
                    )
                )

            items.append(
                PlanLineageItem(
                    plan=plan,
                    tasks=tasks_summary,
                    test_runs=matching_runs[:test_limit],
                    total_tasks=len(plan.task_ids),
                    completed_tasks=sum(
                        1 for task in plan_tasks if task.status == TaskStatus.DONE
                    ),
                    blocked_tasks=sum(
                        1 for task in plan_tasks if task.status == TaskStatus.BLOCKED
                    ),
                    total_test_runs=len(matching_runs),
                    latest_test_success=latest_run.success if latest_run else None,
                    latest_test_run_id=latest_run.id if latest_run else None,
                    evidence=evidence_summary,
                    stored_status=stored_status_map.get(plan.id, plan.status.value),
                    terminal_reason=(
                        lifecycle_rollups.get(plan.id).terminal_reason
                        if lifecycle_rollups.get(plan.id) is not None
                        else None
                    ),
                    last_activity_at=max_datetime(
                        [
                            plan_activity_map.get(plan.id),
                            plan_job_activity.get(plan.id),
                        ]
                    ),
                    last_transition_at=plan_transitions.get(plan.id),
                )
            )

        failed_test_runs = sum(
            1 for run_id in unique_run_ids if not run_success_by_id.get(run_id, True)
        )

        return PlanLineageDashboard(
            items=items,
            total_plans=total_plans,
            total_tasks=len(unique_task_ids),
            total_test_runs=len(unique_run_ids),
            failed_test_runs=failed_test_runs,
            total_evidence=len(unique_evidence_ids),
            total_code_evidence=len(unique_code_evidence_ids),
            offset=result_offset,
            limit=result_limit,
        )

    async def _fetch_test_runs(
        self,
        project_ids: list[str],
        per_project_limit: int = 5,
    ) -> list[LineageTestRunSummary]:
        """Fetch recent test runs by project."""
        if not project_ids or per_project_limit <= 0:
            return []

        unique_ids = list(dict.fromkeys(pid for pid in project_ids if pid))
        if not unique_ids:
            return []

        placeholders = ", ".join("?" * len(unique_ids))
        overall_limit = max(per_project_limit * len(unique_ids), 25)

        rows = await self.db.fetch_all(
            f"""
            SELECT * FROM test_runs
            WHERE project_id IN ({placeholders})
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (*unique_ids, overall_limit),
        )

        return [self._row_to_test_run(row) for row in rows]

    def _row_to_test_run(self, row: TestRunRow) -> LineageTestRunSummary:
        """Convert test run row to summary."""
        config_raw = row.get("config", "{}")
        config: JsonObject = {}
        if isinstance(config_raw, str):
            parsed = json.loads(config_raw)
            if isinstance(parsed, dict):
                config = parsed
        elif isinstance(config_raw, dict):
            config = config_raw

        task_ids_raw = config.get("task_ids", [])
        task_ids = (
            tuple(str(task_id) for task_id in task_ids_raw)
            if isinstance(task_ids_raw, list)
            else ()
        )
        plan_id_raw = config.get("plan_id")
        plan_id = plan_id_raw if isinstance(plan_id_raw, str) else None
        command = config.get("test_command") or config.get("command")

        exit_code_raw = row.get("exit_code")
        exit_code = exit_code_raw if isinstance(exit_code_raw, int) else None

        duration_raw = row.get("duration_seconds")
        duration_seconds = (
            float(duration_raw) if isinstance(duration_raw, (int, float)) else None
        )

        project_id_raw = row.get("project_id")
        project_id = project_id_raw if isinstance(project_id_raw, str) else None

        return LineageTestRunSummary(
            id=str(row["id"]),
            server_id=str(row["server_id"]),
            success=bool(row.get("success")),
            exit_code=exit_code,
            duration_seconds=duration_seconds,
            started_at=datetime.fromisoformat(str(row["started_at"])),
            finished_at=datetime.fromisoformat(str(row["finished_at"])),
            project_id=project_id,
            plan_id=plan_id,
            task_ids=task_ids,
            command=command if isinstance(command, str) else None,
        )

    def _summarize_evidence(
        self, evidence_items: list[TaskEvidence]
    ) -> LineageEvidenceSummary:
        types: dict[str, int] = {}
        code_total = 0
        latest_code_reference: str | None = None
        latest_code_created_at: datetime | None = None

        for evidence in evidence_items:
            types[evidence.evidence_type] = types.get(evidence.evidence_type, 0) + 1
            if self._is_code_evidence(evidence.evidence_type):
                code_total += 1
                created_at = self._parse_timestamp(evidence.created_at)
                if created_at and (
                    latest_code_created_at is None
                    or created_at > latest_code_created_at
                ):
                    latest_code_created_at = created_at
                    latest_code_reference = evidence.reference

        return LineageEvidenceSummary(
            total=len(evidence_items),
            types=types,
            code_total=code_total,
            latest_code_reference=latest_code_reference,
            latest_code_created_at=latest_code_created_at,
        )

    @staticmethod
    def _is_code_evidence(evidence_type: str) -> bool:
        return evidence_type.startswith("scm_")

    @staticmethod
    def _parse_timestamp(value: TimestampSource) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None
        return None

    @staticmethod
    def _matches_plan(
        run: LineageTestRunSummary,
        plan_id: str,
        plan_task_ids: set[str],
        plan_project_ids: set[str],
    ) -> bool:
        """Check if a test run should be linked to a plan."""
        if run.plan_id or run.task_ids:
            if run.plan_id == plan_id:
                return True
            return bool(plan_task_ids.intersection(run.task_ids))

        if run.project_id:
            return run.project_id in plan_project_ids

        return False
