"""Retention service for pruning test run logs and artifacts."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from pms.config.settings import get_settings
from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.models.json_types import JsonObject, JsonValue, ModelObject
from pms.models.test_run_retention_policy import TestRunRetentionPolicy
from pms.models.value_contracts import RETENTION_USAGE_SORTS, RetentionUsageSort
from pms.repositories.test_run_repository import TestRunRepository
from pms.repositories.test_run_retention_policy_repository import (
    TestRunRetentionPolicyRepository,
)
from pms.services.hierarchy_scope_service import HierarchyScopeService

if TYPE_CHECKING:
    from pms.db.connection import Database

logger = logging.getLogger(__name__)

type TestRunLogPayload = dict[str, JsonValue]
type TestRunArtifactPayload = dict[str, JsonValue]
type RetentionAlertDetails = dict[str, JsonValue]


@dataclass
class TestRunPruneSummary:
    """Summary of a test run prune operation."""

    __test__ = False

    runs_scanned: int
    runs_pruned: int
    runs_logs_pruned: int
    runs_artifacts_pruned: int
    stdout_pruned: int
    stderr_pruned: int
    log_bytes_before: int
    log_bytes_after: int
    artifact_bytes_before: int
    artifact_bytes_after: int
    dry_run: bool
    pruned_run_ids: list[str] = field(default_factory=list)
    scopes: list[TestRunPruneScopeSummary] = field(default_factory=list)

    @property
    def log_bytes_pruned(self) -> int:
        return max(0, self.log_bytes_before - self.log_bytes_after)

    @property
    def artifact_bytes_pruned(self) -> int:
        return max(0, self.artifact_bytes_before - self.artifact_bytes_after)

    def to_dict(self) -> ModelObject:
        """Convert summary to a serializable dictionary."""
        return {
            "runs_scanned": self.runs_scanned,
            "runs_pruned": self.runs_pruned,
            "runs_logs_pruned": self.runs_logs_pruned,
            "runs_artifacts_pruned": self.runs_artifacts_pruned,
            "stdout_pruned": self.stdout_pruned,
            "stderr_pruned": self.stderr_pruned,
            "log_bytes_before": self.log_bytes_before,
            "log_bytes_after": self.log_bytes_after,
            "log_bytes_pruned": self.log_bytes_pruned,
            "artifact_bytes_before": self.artifact_bytes_before,
            "artifact_bytes_after": self.artifact_bytes_after,
            "artifact_bytes_pruned": self.artifact_bytes_pruned,
            "dry_run": self.dry_run,
            "pruned_run_ids": list(self.pruned_run_ids),
            "scopes": [scope.to_dict() for scope in self.scopes],
        }


@dataclass
class TestRunPruneScopeSummary:
    """Per-scope prune summary for retention policies."""

    scope_type: str
    scope_id: str
    policy_id: str | None
    max_log_bytes: int
    max_artifact_bytes: int
    max_age_days: int
    runs_scanned: int
    runs_pruned: int
    runs_logs_pruned: int
    runs_artifacts_pruned: int
    stdout_pruned: int
    stderr_pruned: int
    log_bytes_before: int
    log_bytes_after: int
    artifact_bytes_before: int
    artifact_bytes_after: int
    pruned_run_ids: list[str] = field(default_factory=list)

    @property
    def log_bytes_pruned(self) -> int:
        return max(0, self.log_bytes_before - self.log_bytes_after)

    @property
    def artifact_bytes_pruned(self) -> int:
        return max(0, self.artifact_bytes_before - self.artifact_bytes_after)

    def to_dict(self) -> ModelObject:
        return {
            "scope_type": self.scope_type,
            "scope_id": self.scope_id,
            "policy_id": self.policy_id,
            "max_log_bytes": self.max_log_bytes,
            "max_artifact_bytes": self.max_artifact_bytes,
            "max_age_days": self.max_age_days,
            "runs_scanned": self.runs_scanned,
            "runs_pruned": self.runs_pruned,
            "runs_logs_pruned": self.runs_logs_pruned,
            "runs_artifacts_pruned": self.runs_artifacts_pruned,
            "stdout_pruned": self.stdout_pruned,
            "stderr_pruned": self.stderr_pruned,
            "log_bytes_before": self.log_bytes_before,
            "log_bytes_after": self.log_bytes_after,
            "log_bytes_pruned": self.log_bytes_pruned,
            "artifact_bytes_before": self.artifact_bytes_before,
            "artifact_bytes_after": self.artifact_bytes_after,
            "artifact_bytes_pruned": self.artifact_bytes_pruned,
            "pruned_run_ids": list(self.pruned_run_ids),
        }


@dataclass
class TestRunUsageItem:
    """Per-run storage usage summary."""

    run_id: str
    finished_at: datetime
    server_id: str
    project_id: str | None
    stdout_bytes: int
    stderr_bytes: int
    log_bytes: int
    artifact_bytes: int
    artifact_recorded_bytes: int
    artifacts_missing: int

    @property
    def log_total_bytes(self) -> int:
        return self.stdout_bytes + self.stderr_bytes + self.log_bytes

    @property
    def total_bytes(self) -> int:
        return self.log_total_bytes + self.artifact_bytes

    def to_dict(self) -> ModelObject:
        return {
            "run_id": self.run_id,
            "finished_at": self.finished_at.isoformat(),
            "server_id": self.server_id,
            "project_id": self.project_id,
            "stdout_bytes": self.stdout_bytes,
            "stderr_bytes": self.stderr_bytes,
            "log_bytes": self.log_bytes,
            "log_total_bytes": self.log_total_bytes,
            "artifact_bytes": self.artifact_bytes,
            "artifact_recorded_bytes": self.artifact_recorded_bytes,
            "artifacts_missing": self.artifacts_missing,
            "total_bytes": self.total_bytes,
        }


@dataclass
class TestRunRetentionPolicyUsage:
    """Aggregate retention usage for a scope policy."""

    policy_id: str
    scope_type: str
    scope_id: str
    max_log_bytes: int
    max_artifact_bytes: int
    max_age_days: int
    total_log_bytes: int
    total_artifact_bytes: int
    total_bytes: int
    run_count: int
    older_than_max_age: int
    project_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> ModelObject:
        return {
            "policy_id": self.policy_id,
            "scope_type": self.scope_type,
            "scope_id": self.scope_id,
            "max_log_bytes": self.max_log_bytes,
            "max_artifact_bytes": self.max_artifact_bytes,
            "max_age_days": self.max_age_days,
            "total_log_bytes": self.total_log_bytes,
            "total_artifact_bytes": self.total_artifact_bytes,
            "total_bytes": self.total_bytes,
            "run_count": self.run_count,
            "older_than_max_age": self.older_than_max_age,
            "project_ids": list(self.project_ids),
        }


@dataclass
class TestRunRetentionAlert:
    """Alert emitted when a retention budget is exceeded."""

    policy_id: str
    scope_type: str
    scope_id: str
    metric: str
    current_value: int
    limit_value: int
    ratio: float
    severity: str
    details: RetentionAlertDetails = field(default_factory=dict)

    def to_dict(self) -> ModelObject:
        return {
            "policy_id": self.policy_id,
            "scope_type": self.scope_type,
            "scope_id": self.scope_id,
            "metric": self.metric,
            "current_value": self.current_value,
            "limit_value": self.limit_value,
            "ratio": self.ratio,
            "severity": self.severity,
            "details": dict(self.details),
        }


@dataclass
class TestRunUsageSummary:
    """Aggregate usage summary for test run outputs."""

    total_runs: int
    total_stdout_bytes: int
    total_stderr_bytes: int
    total_log_bytes: int
    total_log_bytes_combined: int
    total_artifact_bytes: int
    total_artifact_recorded_bytes: int
    max_log_bytes: int
    max_artifact_bytes: int
    max_age_days: int
    sorted_by: RetentionUsageSort
    items: list[TestRunUsageItem]
    policies: list[TestRunRetentionPolicyUsage] = field(default_factory=list)
    alerts: list[TestRunRetentionAlert] = field(default_factory=list)

    @property
    def total_bytes(self) -> int:
        return self.total_log_bytes_combined + self.total_artifact_bytes

    def to_dict(self) -> ModelObject:
        return {
            "total_runs": self.total_runs,
            "total_stdout_bytes": self.total_stdout_bytes,
            "total_stderr_bytes": self.total_stderr_bytes,
            "total_log_bytes": self.total_log_bytes,
            "total_log_bytes_combined": self.total_log_bytes_combined,
            "total_artifact_bytes": self.total_artifact_bytes,
            "total_artifact_recorded_bytes": self.total_artifact_recorded_bytes,
            "total_bytes": self.total_bytes,
            "max_log_bytes": self.max_log_bytes,
            "max_artifact_bytes": self.max_artifact_bytes,
            "max_age_days": self.max_age_days,
            "sorted_by": self.sorted_by,
            "items": [item.to_dict() for item in self.items],
            "policies": [policy.to_dict() for policy in self.policies],
            "alerts": [alert.to_dict() for alert in self.alerts],
        }


@dataclass
class _RunState:
    run_id: str
    finished_at: datetime
    server_id: str
    project_id: str | None
    stdout: str
    stderr: str
    logs: TestRunLogPayload
    artifacts: TestRunArtifactPayload
    log_bytes: int
    artifact_bytes: int
    prune_logs: bool = False
    prune_artifacts: bool = False


@dataclass
class _RetentionScope:
    scope_type: str
    scope_id: str
    policy_id: str | None
    project_ids: list[str]
    max_log_bytes: int
    max_artifact_bytes: int
    max_age_days: int


class TestRunRetentionService:
    """Prune test run logs/artifacts by age or size."""

    __test__ = False

    def __init__(
        self,
        db: Database,
        metrics: MetricsCollector,
        interval_seconds: int | None = None,
    ) -> None:
        self.db = db
        self.metrics = metrics
        self._repo = TestRunRepository(db)
        self._policy_repo = TestRunRetentionPolicyRepository(db)
        event_store = EventStore(db)
        revision_store = RevisionStore(db)
        self._hierarchy = HierarchyScopeService(
            db,
            event_store,
            revision_store,
            metrics,
        )
        settings = get_settings()
        self.interval_seconds = (
            interval_seconds
            if interval_seconds is not None
            else settings.test_run_prune_interval_seconds
        )
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the background prune loop."""
        if self._running:
            logger.warning("Test run retention service already running")
            return

        if self.interval_seconds <= 0:
            logger.info("Test run retention service disabled (interval <= 0)")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "Test run retention service started (interval=%ss)",
            self.interval_seconds,
        )

    async def stop(self) -> None:
        """Stop the background prune loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("Test run retention service stopped")

    async def run_once(self, dry_run: bool = False) -> TestRunPruneSummary:
        """Run the prune process once using configured defaults."""
        settings = get_settings()
        return await self.prune(
            max_log_bytes=settings.test_run_log_max_bytes,
            max_artifact_bytes=settings.test_run_artifact_max_bytes,
            max_age_days=settings.test_run_retention_days,
            dry_run=dry_run,
        )

    async def prune(
        self,
        max_log_bytes: int | None = None,
        max_artifact_bytes: int | None = None,
        max_age_days: int | None = None,
        dry_run: bool = False,
        project_ids: list[str] | None = None,
        org_id: str | None = None,
        use_policies: bool = True,
    ) -> TestRunPruneSummary:
        """Prune test run outputs based on retention policies."""
        settings = get_settings()
        explicit_limits = (
            max_log_bytes is not None
            or max_artifact_bytes is not None
            or max_age_days is not None
        )
        if explicit_limits:
            use_policies = False

        max_log_bytes = (
            settings.test_run_log_max_bytes if max_log_bytes is None else max_log_bytes
        )
        max_artifact_bytes = (
            settings.test_run_artifact_max_bytes
            if max_artifact_bytes is None
            else max_artifact_bytes
        )
        max_age_days = (
            settings.test_run_retention_days if max_age_days is None else max_age_days
        )

        resolved_project_ids = project_ids
        if org_id:
            resolved_project_ids = await self._resolve_org_project_ids(org_id)

        runs = await self._load_runs(project_ids=resolved_project_ids)
        pending_artifact_deletions: list[Path] = []

        async def _run_prune_once() -> TestRunPruneSummary:
            scope_summaries: list[TestRunPruneScopeSummary] = []

            if use_policies:
                scope_defs = await self._resolve_prune_scopes(
                    project_ids=resolved_project_ids,
                    org_id=org_id,
                    default_limits=(max_log_bytes, max_artifact_bytes, max_age_days),
                )
                scope_summaries = await self._prune_scopes(
                    scope_defs,
                    runs=runs,
                    dry_run=dry_run,
                    default_limits=(max_log_bytes, max_artifact_bytes, max_age_days),
                    pending_artifact_deletions=pending_artifact_deletions,
                )
            else:
                scope_type, scope_id = self._default_scope_label(
                    resolved_project_ids,
                    org_id,
                )
                scope = _RetentionScope(
                    scope_type=scope_type,
                    scope_id=scope_id,
                    policy_id=None,
                    project_ids=resolved_project_ids or [],
                    max_log_bytes=max_log_bytes,
                    max_artifact_bytes=max_artifact_bytes,
                    max_age_days=max_age_days,
                )
                scope_summary = await self._prune_scope(
                    scope,
                    runs=runs,
                    dry_run=dry_run,
                    pending_artifact_deletions=pending_artifact_deletions,
                )
                scope_summaries.append(scope_summary)

            summary = self._summarize_scope_summaries(
                scope_summaries,
                dry_run=dry_run,
            )

            await self.metrics.record_counter(
                "test_run.prune_runs",
                value=summary.runs_pruned,
            )
            await self.metrics.record_gauge(
                "test_run.prune_log_bytes",
                summary.log_bytes_pruned,
                unit="bytes",
            )
            await self.metrics.record_gauge(
                "test_run.prune_artifact_bytes",
                summary.artifact_bytes_pruned,
                unit="bytes",
            )
            await self.metrics.flush()
            return summary

        if dry_run:
            return await _run_prune_once()

        async with self.db.transaction():
            summary = await _run_prune_once()

        self._delete_artifact_files(pending_artifact_deletions)
        return summary

    async def get_usage(
        self,
        limit: int = 20,
        sort: RetentionUsageSort = "largest",
        project_ids: list[str] | None = None,
        org_id: str | None = None,
    ) -> TestRunUsageSummary:
        """Get storage usage totals and per-run breakdown."""
        settings = get_settings()
        resolved_project_ids = project_ids
        if org_id:
            resolved_project_ids = await self._resolve_org_project_ids(org_id)

        runs = await self._load_runs(project_ids=resolved_project_ids)

        items: list[TestRunUsageItem] = []
        for run in runs:
            stdout_bytes = self._content_size(run.stdout)
            stderr_bytes = self._content_size(run.stderr)
            log_bytes = 0
            for entry in run.logs.values():
                log_bytes += self._log_entry_size(entry)

            artifact_bytes, artifact_recorded_bytes, artifacts_missing = (
                self._artifact_sizes(run.artifacts)
            )

            items.append(
                TestRunUsageItem(
                    run_id=run.run_id,
                    finished_at=run.finished_at,
                    server_id=run.server_id,
                    project_id=run.project_id,
                    stdout_bytes=stdout_bytes,
                    stderr_bytes=stderr_bytes,
                    log_bytes=log_bytes,
                    artifact_bytes=artifact_bytes,
                    artifact_recorded_bytes=artifact_recorded_bytes,
                    artifacts_missing=artifacts_missing,
                )
            )

        if sort not in RETENTION_USAGE_SORTS:
            raise ValueError(
                f"Unsupported retention sort '{sort}'. "
                f"Use one of: {', '.join(RETENTION_USAGE_SORTS)}."
            )

        if sort == "recent":
            items.sort(key=lambda item: item.finished_at, reverse=True)
        else:
            items.sort(key=lambda item: item.total_bytes, reverse=True)

        total_stdout = sum(item.stdout_bytes for item in items)
        total_stderr = sum(item.stderr_bytes for item in items)
        total_logs = sum(item.log_bytes for item in items)
        total_log_combined = sum(item.log_total_bytes for item in items)
        total_artifacts = sum(item.artifact_bytes for item in items)
        total_artifacts_recorded = sum(item.artifact_recorded_bytes for item in items)

        policy_usage, alerts = await self._build_policy_usage(
            runs=runs,
            project_ids=resolved_project_ids,
            org_id=org_id,
        )

        return TestRunUsageSummary(
            total_runs=len(items),
            total_stdout_bytes=total_stdout,
            total_stderr_bytes=total_stderr,
            total_log_bytes=total_logs,
            total_log_bytes_combined=total_log_combined,
            total_artifact_bytes=total_artifacts,
            total_artifact_recorded_bytes=total_artifacts_recorded,
            max_log_bytes=settings.test_run_log_max_bytes,
            max_artifact_bytes=settings.test_run_artifact_max_bytes,
            max_age_days=settings.test_run_retention_days,
            sorted_by=sort,
            items=items[: max(limit, 0)] if limit else items,
            policies=policy_usage,
            alerts=alerts,
        )

    def _default_scope_label(
        self,
        project_ids: list[str] | None,
        org_id: str | None,
    ) -> tuple[str, str]:
        if org_id:
            return "organization", org_id
        if project_ids and len(project_ids) == 1:
            return "project", project_ids[0]
        return "default", "all"

    async def _resolve_prune_scopes(
        self,
        *,
        project_ids: list[str] | None,
        org_id: str | None,
        default_limits: tuple[int, int, int],
    ) -> list[_RetentionScope]:
        policy_result = await self._policy_repo.list(
            limit=1000,
            offset=0,
            include_archived=False,
        )
        policies = policy_result.items

        if project_ids is not None:
            project_set = set(project_ids)
            policies = [
                policy
                for policy in policies
                if (policy.scope_type == "project" and policy.scope_id in project_set)
                or (
                    org_id
                    and policy.scope_type == "organization"
                    and policy.scope_id == org_id
                )
            ]
        elif org_id:
            policies = [
                policy
                for policy in policies
                if policy.scope_type == "organization" and policy.scope_id == org_id
            ]

        scopes: list[_RetentionScope] = []
        project_policy_ids: set[str] = set()
        org_project_cache: dict[str, list[str]] = {}

        for policy in policies:
            if policy.scope_type == "project":
                project_policy_ids.add(policy.scope_id)

        for policy in policies:
            if policy.scope_type == "project":
                scope_project_ids = [policy.scope_id]
            else:
                if policy.scope_id not in org_project_cache:
                    org_project_cache[
                        policy.scope_id
                    ] = await self._resolve_org_project_ids(policy.scope_id)
                scope_project_ids = [
                    project_id
                    for project_id in org_project_cache[policy.scope_id]
                    if project_id not in project_policy_ids
                ]

            scopes.append(
                _RetentionScope(
                    scope_type=policy.scope_type,
                    scope_id=policy.scope_id,
                    policy_id=policy.id,
                    project_ids=scope_project_ids,
                    max_log_bytes=policy.max_log_bytes,
                    max_artifact_bytes=policy.max_artifact_bytes,
                    max_age_days=policy.max_age_days,
                )
            )

        return scopes

    async def _prune_scopes(
        self,
        scopes: list[_RetentionScope],
        *,
        runs: list[_RunState],
        dry_run: bool,
        default_limits: tuple[int, int, int],
        pending_artifact_deletions: list[Path],
    ) -> list[TestRunPruneScopeSummary]:
        if not scopes:
            max_log_bytes, max_artifact_bytes, max_age_days = default_limits
            scope_type, scope_id = self._default_scope_label(None, None)
            fallback_scope = _RetentionScope(
                scope_type=scope_type,
                scope_id=scope_id,
                policy_id=None,
                project_ids=[],
                max_log_bytes=max_log_bytes,
                max_artifact_bytes=max_artifact_bytes,
                max_age_days=max_age_days,
            )
            return [
                await self._prune_scope(
                    fallback_scope,
                    runs=runs,
                    dry_run=dry_run,
                    pending_artifact_deletions=pending_artifact_deletions,
                )
            ]

        if not runs:
            return [
                TestRunPruneScopeSummary(
                    scope_type=scope.scope_type,
                    scope_id=scope.scope_id,
                    policy_id=scope.policy_id,
                    max_log_bytes=scope.max_log_bytes,
                    max_artifact_bytes=scope.max_artifact_bytes,
                    max_age_days=scope.max_age_days,
                    runs_scanned=0,
                    runs_pruned=0,
                    runs_logs_pruned=0,
                    runs_artifacts_pruned=0,
                    stdout_pruned=0,
                    stderr_pruned=0,
                    log_bytes_before=0,
                    log_bytes_after=0,
                    artifact_bytes_before=0,
                    artifact_bytes_after=0,
                    pruned_run_ids=[],
                )
                for scope in scopes
            ]

        runs_by_project: dict[str, list[_RunState]] = {}
        unscoped_runs: list[_RunState] = []
        for run in runs:
            if run.project_id:
                runs_by_project.setdefault(run.project_id, []).append(run)
            else:
                unscoped_runs.append(run)

        scope_summaries: list[TestRunPruneScopeSummary] = []
        covered_projects: set[str] = set()

        for scope in scopes:
            if scope.project_ids:
                scope_runs: list[_RunState] = []
                for project_id in scope.project_ids:
                    scope_runs.extend(runs_by_project.get(project_id, []))
                    covered_projects.add(project_id)
            else:
                scope_runs = []

            scope_summary = await self._prune_scope(
                scope,
                runs=scope_runs,
                dry_run=dry_run,
                pending_artifact_deletions=pending_artifact_deletions,
            )
            scope_summaries.append(scope_summary)

        remaining_runs: list[_RunState] = list(unscoped_runs)
        for project_id, project_runs in runs_by_project.items():
            if project_id in covered_projects:
                continue
            remaining_runs.extend(project_runs)

        if remaining_runs:
            max_log_bytes, max_artifact_bytes, max_age_days = default_limits
            scope_type, scope_id = self._default_scope_label(None, None)
            fallback_scope = _RetentionScope(
                scope_type=scope_type,
                scope_id=scope_id,
                policy_id=None,
                project_ids=[],
                max_log_bytes=max_log_bytes,
                max_artifact_bytes=max_artifact_bytes,
                max_age_days=max_age_days,
            )
            scope_summaries.append(
                await self._prune_scope(
                    fallback_scope,
                    runs=remaining_runs,
                    dry_run=dry_run,
                    pending_artifact_deletions=pending_artifact_deletions,
                )
            )

        return scope_summaries

    async def _prune_scope(
        self,
        scope: _RetentionScope,
        *,
        runs: list[_RunState],
        dry_run: bool,
        pending_artifact_deletions: list[Path],
    ) -> TestRunPruneScopeSummary:
        runs = list(runs)
        runs.sort(key=lambda run: run.finished_at)

        total_log_bytes = sum(run.log_bytes for run in runs)
        total_artifact_bytes = sum(run.artifact_bytes for run in runs)
        log_bytes_before = total_log_bytes
        artifact_bytes_before = total_artifact_bytes

        cutoff = None
        if scope.max_age_days and scope.max_age_days > 0:
            cutoff = datetime.now(UTC) - timedelta(days=scope.max_age_days)

        if cutoff:
            for run in runs:
                if run.finished_at < cutoff:
                    if run.log_bytes > 0:
                        run.prune_logs = True
                        total_log_bytes -= run.log_bytes
                        run.log_bytes = 0
                    if run.artifact_bytes > 0:
                        run.prune_artifacts = True
                        total_artifact_bytes -= run.artifact_bytes
                        run.artifact_bytes = 0

        if (
            scope.max_log_bytes
            and scope.max_log_bytes > 0
            and total_log_bytes > scope.max_log_bytes
        ):
            for run in runs:
                if run.prune_logs or run.log_bytes <= 0:
                    continue
                run.prune_logs = True
                total_log_bytes -= run.log_bytes
                run.log_bytes = 0
                if total_log_bytes <= scope.max_log_bytes:
                    break

        if (
            scope.max_artifact_bytes
            and scope.max_artifact_bytes > 0
            and total_artifact_bytes > scope.max_artifact_bytes
        ):
            for run in runs:
                if run.prune_artifacts or run.artifact_bytes <= 0:
                    continue
                run.prune_artifacts = True
                total_artifact_bytes -= run.artifact_bytes
                run.artifact_bytes = 0
                if total_artifact_bytes <= scope.max_artifact_bytes:
                    break

        return await self._apply_prune_plan(
            runs,
            scope_type=scope.scope_type,
            scope_id=scope.scope_id,
            policy_id=scope.policy_id,
            max_log_bytes=scope.max_log_bytes,
            max_artifact_bytes=scope.max_artifact_bytes,
            max_age_days=scope.max_age_days,
            log_bytes_before=log_bytes_before,
            artifact_bytes_before=artifact_bytes_before,
            log_bytes_after=total_log_bytes,
            artifact_bytes_after=total_artifact_bytes,
            dry_run=dry_run,
            pending_artifact_deletions=pending_artifact_deletions,
        )

    def _summarize_scope_summaries(
        self,
        scopes: list[TestRunPruneScopeSummary],
        *,
        dry_run: bool,
    ) -> TestRunPruneSummary:
        pruned_run_ids: list[str] = []
        seen_ids: set[str] = set()
        for scope in scopes:
            for run_id in scope.pruned_run_ids:
                if run_id in seen_ids:
                    continue
                seen_ids.add(run_id)
                pruned_run_ids.append(run_id)

        return TestRunPruneSummary(
            runs_scanned=sum(scope.runs_scanned for scope in scopes),
            runs_pruned=sum(scope.runs_pruned for scope in scopes),
            runs_logs_pruned=sum(scope.runs_logs_pruned for scope in scopes),
            runs_artifacts_pruned=sum(scope.runs_artifacts_pruned for scope in scopes),
            stdout_pruned=sum(scope.stdout_pruned for scope in scopes),
            stderr_pruned=sum(scope.stderr_pruned for scope in scopes),
            log_bytes_before=sum(scope.log_bytes_before for scope in scopes),
            log_bytes_after=sum(scope.log_bytes_after for scope in scopes),
            artifact_bytes_before=sum(scope.artifact_bytes_before for scope in scopes),
            artifact_bytes_after=sum(scope.artifact_bytes_after for scope in scopes),
            dry_run=dry_run,
            pruned_run_ids=pruned_run_ids,
            scopes=scopes,
        )

    async def _run_loop(self) -> None:
        while self._running:
            try:
                await self.run_once(dry_run=False)
                await asyncio.sleep(self.interval_seconds)
            except Exception as exc:
                logger.error("Error in test run retention loop: %s", exc, exc_info=True)
                await asyncio.sleep(self.interval_seconds)

    async def _load_runs(self, project_ids: list[str] | None = None) -> list[_RunState]:
        if project_ids is not None and not project_ids:
            return []

        params: list[str] = []
        where_clause = ""
        if project_ids:
            placeholders = ", ".join("?" * len(project_ids))
            where_clause = f"WHERE project_id IN ({placeholders})"
            params = list(project_ids)

        rows = await self.db.fetch_all(
            f"""
            SELECT id, server_id, project_id, stdout, stderr, logs, artifacts, finished_at
            FROM test_runs
            {where_clause}
            ORDER BY finished_at ASC
            """,
            tuple(params),
        )
        runs: list[_RunState] = []
        for row in rows:
            finished_at = self._as_datetime(
                row.get("finished_at"),
                fallback=datetime.now(UTC),
            )
            stdout = self._as_text(row.get("stdout"))
            stderr = self._as_text(row.get("stderr"))
            logs = self._safe_json(row.get("logs"))
            artifacts = self._safe_json(row.get("artifacts"))

            log_bytes = self._log_bytes(stdout, stderr, logs)
            artifact_bytes = self._artifact_bytes(artifacts)

            runs.append(
                _RunState(
                    run_id=self._as_text(row.get("id")),
                    finished_at=finished_at,
                    server_id=self._as_text(row.get("server_id")),
                    project_id=self._as_optional_text(row.get("project_id")),
                    stdout=stdout,
                    stderr=stderr,
                    logs=logs,
                    artifacts=artifacts,
                    log_bytes=log_bytes,
                    artifact_bytes=artifact_bytes,
                )
            )
        return runs

    async def _resolve_org_project_ids(self, org_id: str) -> list[str]:
        return await self._hierarchy.get_project_ids_for_scope("organization", org_id)

    async def _build_policy_usage(
        self,
        *,
        runs: list[_RunState],
        project_ids: list[str] | None,
        org_id: str | None,
    ) -> tuple[list[TestRunRetentionPolicyUsage], list[TestRunRetentionAlert]]:
        policy_result = await self._policy_repo.list(
            limit=1000,
            offset=0,
            include_archived=False,
        )
        policies = policy_result.items
        if project_ids is not None:
            project_set = set(project_ids)
            policies = [
                policy
                for policy in policies
                if (policy.scope_type == "project" and policy.scope_id in project_set)
                or (
                    org_id
                    and policy.scope_type == "organization"
                    and policy.scope_id == org_id
                )
            ]
        elif org_id:
            policies = [
                policy
                for policy in policies
                if policy.scope_type == "organization" and policy.scope_id == org_id
            ]

        if not policies:
            return [], []

        runs_by_project: dict[str, list[_RunState]] = {}
        for run in runs:
            if not run.project_id:
                continue
            runs_by_project.setdefault(run.project_id, []).append(run)

        policy_usage: list[TestRunRetentionPolicyUsage] = []
        alerts: list[TestRunRetentionAlert] = []
        now = datetime.now(UTC)
        org_project_cache: dict[str, list[str]] = {}

        for policy in policies:
            if policy.scope_type == "project":
                scope_project_ids = [policy.scope_id]
            else:
                if policy.scope_id not in org_project_cache:
                    org_project_cache[
                        policy.scope_id
                    ] = await self._resolve_org_project_ids(policy.scope_id)
                scope_project_ids = org_project_cache[policy.scope_id]

            scope_runs: list[_RunState] = []
            for project_id in scope_project_ids:
                scope_runs.extend(runs_by_project.get(project_id, []))

            total_log_bytes = sum(run.log_bytes for run in scope_runs)
            total_artifact_bytes = sum(run.artifact_bytes for run in scope_runs)
            total_bytes = total_log_bytes + total_artifact_bytes
            older_than_max_age = 0
            if policy.max_age_days > 0:
                cutoff = now - timedelta(days=policy.max_age_days)
                older_than_max_age = sum(
                    1 for run in scope_runs if run.finished_at < cutoff
                )

            usage = TestRunRetentionPolicyUsage(
                policy_id=policy.id,
                scope_type=policy.scope_type,
                scope_id=policy.scope_id,
                max_log_bytes=policy.max_log_bytes,
                max_artifact_bytes=policy.max_artifact_bytes,
                max_age_days=policy.max_age_days,
                total_log_bytes=total_log_bytes,
                total_artifact_bytes=total_artifact_bytes,
                total_bytes=total_bytes,
                run_count=len(scope_runs),
                older_than_max_age=older_than_max_age,
                project_ids=scope_project_ids,
            )
            policy_usage.append(usage)

            alerts.extend(
                self._build_policy_alerts(
                    policy=policy,
                    usage=usage,
                    scope_runs=scope_runs,
                    now=now,
                )
            )

        return policy_usage, alerts

    def _build_policy_alerts(
        self,
        *,
        policy: TestRunRetentionPolicy,
        usage: TestRunRetentionPolicyUsage,
        scope_runs: list[_RunState],
        now: datetime,
    ) -> list[TestRunRetentionAlert]:
        alerts: list[TestRunRetentionAlert] = []

        def maybe_alert(metric: str, current: int, limit: int) -> None:
            if limit <= 0:
                return
            ratio = current / limit if limit else 0
            if ratio < 0.9:
                return
            severity = "critical" if ratio >= 1.0 else "warning"
            alerts.append(
                TestRunRetentionAlert(
                    policy_id=policy.id,
                    scope_type=policy.scope_type,
                    scope_id=policy.scope_id,
                    metric=metric,
                    current_value=current,
                    limit_value=limit,
                    ratio=ratio,
                    severity=severity,
                )
            )

        maybe_alert("log_bytes", usage.total_log_bytes, usage.max_log_bytes)
        maybe_alert(
            "artifact_bytes",
            usage.total_artifact_bytes,
            usage.max_artifact_bytes,
        )

        if usage.max_age_days > 0 and scope_runs:
            oldest_age_days = max(
                int((now - run.finished_at).total_seconds() // 86400)
                for run in scope_runs
            )
            if oldest_age_days >= usage.max_age_days:
                ratio = (
                    oldest_age_days / usage.max_age_days if usage.max_age_days else 0
                )
                severity = "critical" if ratio >= 1.0 else "warning"
                alerts.append(
                    TestRunRetentionAlert(
                        policy_id=policy.id,
                        scope_type=policy.scope_type,
                        scope_id=policy.scope_id,
                        metric="max_age_days",
                        current_value=oldest_age_days,
                        limit_value=usage.max_age_days,
                        ratio=ratio,
                        severity=severity,
                        details={"older_than_max_age": usage.older_than_max_age},
                    )
                )

        return alerts

    async def _apply_prune_plan(
        self,
        runs: list[_RunState],
        *,
        scope_type: str,
        scope_id: str,
        policy_id: str | None,
        max_log_bytes: int,
        max_artifact_bytes: int,
        max_age_days: int,
        log_bytes_before: int,
        artifact_bytes_before: int,
        log_bytes_after: int,
        artifact_bytes_after: int,
        dry_run: bool,
        pending_artifact_deletions: list[Path],
    ) -> TestRunPruneScopeSummary:
        runs_pruned = 0
        runs_logs_pruned = 0
        runs_artifacts_pruned = 0
        stdout_pruned = 0
        stderr_pruned = 0
        pruned_run_ids: list[str] = []
        now = datetime.now(UTC)

        for run in runs:
            if not (run.prune_logs or run.prune_artifacts):
                continue

            new_stdout = run.stdout
            new_stderr = run.stderr
            new_logs = run.logs
            new_artifacts = run.artifacts

            if run.prune_logs:
                runs_logs_pruned += 1
                pruned_run_ids.append(run.run_id)
                if run.stdout:
                    stdout_pruned += 1
                if run.stderr:
                    stderr_pruned += 1
                new_stdout = ""
                new_stderr = ""
                new_logs = self._prune_logs_payload(
                    run.logs,
                    fallback_time=run.finished_at,
                    pruned_at=now,
                )

            if run.prune_artifacts:
                runs_artifacts_pruned += 1
                if run.run_id not in pruned_run_ids:
                    pruned_run_ids.append(run.run_id)
                new_artifacts, artifact_paths = self._prune_artifacts_payload(
                    run.artifacts,
                    pruned_at=now,
                )
                pending_artifact_deletions.extend(artifact_paths)

            runs_pruned += 1

            if not dry_run:
                await self._repo.update_payloads(
                    run_id=run.run_id,
                    stdout=new_stdout,
                    stderr=new_stderr,
                    logs=new_logs,
                    artifacts=new_artifacts,
                )

        return TestRunPruneScopeSummary(
            scope_type=scope_type,
            scope_id=scope_id,
            policy_id=policy_id,
            max_log_bytes=max_log_bytes,
            max_artifact_bytes=max_artifact_bytes,
            max_age_days=max_age_days,
            runs_scanned=len(runs),
            runs_pruned=runs_pruned,
            runs_logs_pruned=runs_logs_pruned,
            runs_artifacts_pruned=runs_artifacts_pruned,
            stdout_pruned=stdout_pruned,
            stderr_pruned=stderr_pruned,
            log_bytes_before=log_bytes_before,
            log_bytes_after=log_bytes_after,
            artifact_bytes_before=artifact_bytes_before,
            artifact_bytes_after=artifact_bytes_after,
            pruned_run_ids=pruned_run_ids,
        )

    def _log_bytes(self, stdout: str, stderr: str, logs: TestRunLogPayload) -> int:
        total = self._content_size(stdout) + self._content_size(stderr)
        for entry in logs.values():
            content = self._log_entry_content(entry)
            total += self._content_size(content)
        return total

    def _artifact_bytes(self, artifacts: TestRunArtifactPayload) -> int:
        total = 0
        for entry in artifacts.values():
            local_path = self._artifact_local_path(entry)
            if not local_path:
                continue
            path = Path(local_path)
            if path.exists():
                total += path.stat().st_size
        return total

    def _artifact_sizes(
        self, artifacts: TestRunArtifactPayload
    ) -> tuple[int, int, int]:
        total_bytes = 0
        recorded_bytes = 0
        missing = 0
        for entry in artifacts.values():
            local_path = self._artifact_local_path(entry)
            entry_recorded = 0
            entry_obj = self._as_json_object(entry)
            if entry_obj is not None:
                entry_recorded = self._as_int(entry_obj.get("size_bytes"))
            if local_path:
                path = Path(local_path)
                if path.exists():
                    size = path.stat().st_size
                    total_bytes += size
                    recorded_bytes += entry_recorded or size
                else:
                    missing += 1
                    recorded_bytes += entry_recorded
            else:
                recorded_bytes += entry_recorded
        return total_bytes, recorded_bytes, missing

    def _log_entry_content(self, entry: JsonValue) -> str:
        entry_obj = self._as_json_object(entry)
        if entry_obj is not None:
            return self._as_text(entry_obj.get("content"))
        return self._as_text(entry)

    def _log_entry_size(self, entry: JsonValue) -> int:
        entry_obj = self._as_json_object(entry)
        if entry_obj is not None:
            if "content" in entry_obj:
                return self._content_size(self._as_text(entry_obj.get("content")))
            return self._as_int(entry_obj.get("size_bytes"))
        if entry is None:
            return 0
        return self._content_size(self._as_text(entry))

    def _artifact_local_path(self, entry: JsonValue) -> str:
        entry_obj = self._as_json_object(entry)
        if entry_obj is not None:
            return self._as_text(entry_obj.get("local_path"))
        return self._as_text(entry)

    def _prune_logs_payload(
        self,
        logs: TestRunLogPayload,
        fallback_time: datetime,
        pruned_at: datetime,
    ) -> TestRunLogPayload:
        pruned_at_iso = pruned_at.isoformat()
        fallback_iso = fallback_time.isoformat()
        payload: TestRunLogPayload = {}
        for path, entry in logs.items():
            entry_obj = self._as_json_object(entry)
            if entry_obj is not None:
                new_entry = dict(entry_obj)
                if new_entry.get("content"):
                    new_entry["content"] = ""
                    new_entry["pruned_at"] = pruned_at_iso
                payload[path] = new_entry
                continue

            content = self._as_text(entry)
            payload[path] = {
                "content": "",
                "size_bytes": self._content_size(content),
                "captured_at": fallback_iso,
                "pruned_at": pruned_at_iso,
            }
        return payload

    def _prune_artifacts_payload(
        self,
        artifacts: TestRunArtifactPayload,
        pruned_at: datetime,
    ) -> tuple[TestRunArtifactPayload, list[Path]]:
        pruned_at_iso = pruned_at.isoformat()
        payload: TestRunArtifactPayload = {}
        artifact_paths: list[Path] = []
        for path, entry in artifacts.items():
            entry_obj = self._as_json_object(entry)
            entry_dict: JsonObject
            if entry_obj is not None:
                entry_dict = dict(entry_obj)
            else:
                entry_dict = {"local_path": self._as_text(entry)}

            local_path = self._as_text(entry_dict.get("local_path"))
            if local_path:
                path_obj = Path(local_path)
                if path_obj.exists():
                    artifact_paths.append(path_obj)
                    entry_dict["pruned_at"] = pruned_at_iso
            payload[path] = entry_dict
        return payload, artifact_paths

    def _delete_artifact_files(self, artifact_paths: list[Path]) -> None:
        seen: set[Path] = set()
        for path in artifact_paths:
            if path in seen:
                continue
            seen.add(path)
            with contextlib.suppress(OSError):
                path.unlink()

    def _safe_json(self, raw: JsonValue | datetime | None) -> JsonObject:
        if raw is None:
            return {}
        if isinstance(raw, dict):
            payload: JsonObject = {}
            for key, value in raw.items():
                payload[str(key)] = self._coerce_json_value(value)
            return payload
        if isinstance(raw, str):
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                data = json.loads(raw)
                if isinstance(data, dict):
                    payload = {}
                    for key, value in data.items():
                        payload[str(key)] = self._coerce_json_value(value)
                    return payload
        return {}

    def _content_size(self, content: str) -> int:
        return len(content.encode("utf-8", errors="replace"))

    def _as_json_object(self, entry: JsonValue) -> JsonObject | None:
        if not isinstance(entry, dict):
            return None
        payload: JsonObject = {}
        for key, value in entry.items():
            payload[str(key)] = self._coerce_json_value(value)
        return payload

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

    def _as_text(self, value: JsonValue | datetime | None) -> str:
        if value is None:
            return ""
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, (str, int, float, bool)):
            return str(value)
        return str(value)

    def _as_optional_text(self, value: JsonValue | datetime | None) -> str | None:
        if value is None:
            return None
        text = self._as_text(value)
        return text or None

    def _as_int(self, value: JsonValue | None) -> int:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            with contextlib.suppress(ValueError):
                return int(float(value))
        return 0

    def _as_datetime(
        self, value: JsonValue | datetime | None, *, fallback: datetime
    ) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            with contextlib.suppress(ValueError):
                return datetime.fromisoformat(value)
        return fallback

    def _as_text_list(self, value: JsonValue | datetime | None) -> list[str]:
        if isinstance(value, str):
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return [
                        self._as_text(item) for item in parsed if self._as_text(item)
                    ]
            return []
        if isinstance(value, list):
            return [self._as_text(item) for item in value if self._as_text(item)]
        return []
