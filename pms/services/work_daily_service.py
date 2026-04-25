"""Service for daily review summaries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, TypedDict

from pms.models import Project, Task
from pms.models.json_types import ModelObject
from pms.models.state_transition import StateTransition
from pms.models.work_snapshot import WorkSnapshotReview
from pms.repositories.base import QueryResult
from pms.repositories.state_transition_repository import StateTransitionRepository
from pms.services.queue_service import QueueService, QueueSummary
from pms.services.task_service import TaskService
from pms.services.test_run_service import TestRunService
from pms.services.work_snapshot_service import (
    WorkSnapshot,
    WorkSnapshotRunHighlight,
    WorkSnapshotService,
)
from pms.utils.atomic_files import write_text_atomic
from pms.utils.cli_commands import normalize_command_links, normalize_next_steps


class ProjectLookupService(Protocol):
    async def get_project(self, project_id: str) -> Project | None: ...


class WorkDailyParams(TypedDict):
    scope_type: str
    scope_id: str
    task_limit: int
    test_limit: int
    queue_limit: int
    stale_days: int
    at_risk_days: int
    include_timeline: bool
    timeline_limit: int
    include_history: bool
    history_limit: int
    view: str


@dataclass
class WorkDailySummary:
    """Daily review summary with snapshot, queues, and timelines."""

    snapshot: WorkSnapshot
    queues: list[QueueSummary]
    ready_summary: QueueSummary | None
    blocked_summary: QueueSummary | None
    recent_runs: list[WorkSnapshotRunHighlight]
    run_window: str
    transitions: list[StateTransition]
    timeline_window: str
    review_history: QueryResult[WorkSnapshotReview] | None
    project_names: dict[str, str | None]
    task_titles: dict[str, str]
    scope_project_ids: list[str]
    queue_limit: int
    include_timeline: bool
    include_history: bool
    view: str
    params: WorkDailyParams

    def to_dict(self) -> ModelObject:
        """Convert summary to JSON-ready dict."""
        snapshot_payload = self.snapshot.to_dict()
        if self.view == "overview":
            snapshot_payload["recent_tasks"] = []
            snapshot_payload["recent_test_runs"] = []

        def _task_payload(task_obj: Task) -> ModelObject:
            data = task_obj.to_dict()
            if task_obj.project_id:
                data["project_name"] = self.project_names.get(task_obj.project_id)
            return data

        def _task_overview(task_obj: Task) -> ModelObject:
            status_value = (
                task_obj.status.value
                if hasattr(task_obj.status, "value")
                else task_obj.status
            )
            return {
                "id": task_obj.id,
                "title": task_obj.title,
                "status": status_value,
                "project_id": task_obj.project_id,
                "project_name": self.project_names.get(task_obj.project_id)
                if task_obj.project_id
                else None,
                "updated_at": task_obj.updated_at.isoformat(),
            }

        queue_payload = []
        for summary in self.queues:
            queue_item: ModelObject = {
                "name": summary.name,
                "description": summary.description,
                "total_count": summary.total_count,
            }
            if self.view != "overview":
                queue_item["items"] = [
                    _task_payload(task_obj) for task_obj in summary.items
                ]
            queue_payload.append(queue_item)

        digest = self.snapshot.digest
        evidence = self.snapshot.evidence

        payload: ModelObject = {
            "snapshot": snapshot_payload,
            "queues": queue_payload,
            "test_run_window": self.run_window,
            "recent_test_runs": [
                {
                    **item.to_dict(),
                    "project_name": self.project_names.get(item.project_id)
                    if item.project_id
                    else None,
                }
                for item in self.recent_runs
            ],
            "evidence_delta": {
                "since_last_review": digest.evidence_added,
                "total": evidence.total_count,
            },
            "next_actions": [
                _task_overview(task_obj)
                if self.view == "overview"
                else _task_payload(task_obj)
                for task_obj in (
                    self.ready_summary.items if self.ready_summary else []
                )[: self.queue_limit]
            ],
            "blockers": [
                _task_overview(task_obj)
                if self.view == "overview"
                else _task_payload(task_obj)
                for task_obj in (
                    self.blocked_summary.items if self.blocked_summary else []
                )[: self.queue_limit]
            ],
        }

        if self.include_timeline:
            payload["timeline_window"] = self.timeline_window
            payload["recent_transitions"] = [
                {
                    **transition.to_dict(),
                    "task_title": self.task_titles.get(transition.entity_id),
                    "kind": "workflow"
                    if transition.entity_type.endswith("_workflow")
                    else "status"
                    if transition.entity_type.endswith("_status")
                    else "state",
                }
                for transition in self.transitions
            ]

        if self.include_history and self.review_history:
            payload["review_history"] = [
                review.to_dict() for review in self.review_history.items
            ]

        scope_arg = (
            f'--scope "{self.snapshot.scope_name}"'
            if self.snapshot.scope_name
            else f"--scope-id {self.snapshot.scope_id}"
        )
        base_cmd = (
            "work daily --scope-type "
            f"{self.snapshot.scope_type} --scope-id {self.snapshot.scope_id} "
            "--format json"
        )
        base_cmd += (
            f" --task-limit {self.params['task_limit']}"
            f" --test-limit {self.params['test_limit']}"
            f" --queue-limit {self.queue_limit}"
            f" --stale-days {self.params['stale_days']}"
            f" --at-risk-days {self.params['at_risk_days']}"
            f" --timeline-limit {self.params['timeline_limit']}"
            f" --history-limit {self.params['history_limit']}"
        )
        if self.include_timeline:
            base_cmd += " --include-timeline"
        if self.include_history:
            base_cmd += " --include-history"
        if self.view != "detail":
            base_cmd += f" --view {self.view}"

        payload["links"] = normalize_command_links(
            {
                "self": base_cmd,
                "snapshot": (
                    "work snapshot --scope-type "
                    f"{self.snapshot.scope_type} --scope-id {self.snapshot.scope_id} "
                    "--format json"
                ),
                "review": (
                    "work review --scope-type "
                    f"{self.snapshot.scope_type} --scope-id {self.snapshot.scope_id}"
                ),
            }
        )
        payload["next_steps"] = normalize_next_steps(
            f"work review --scope-type {self.snapshot.scope_type} {scope_arg} "
            "--reviewed-by <you>",
            f"work snapshot --scope-type {self.snapshot.scope_type} {scope_arg}",
        )
        payload["params"] = self.params
        return payload


@dataclass
class WorkDailyExportResult:
    """Result of exporting a daily review artifact."""

    path: Path
    size_bytes: int
    exported_at: datetime
    modified_at: datetime
    attached_task: Task | None = None


class WorkDailyService:
    """Build daily review summaries from existing services."""

    def __init__(
        self,
        snapshot_service: WorkSnapshotService,
        queue_service: QueueService,
        task_service: TaskService,
        project_service: ProjectLookupService,
        transition_repo: StateTransitionRepository,
        test_run_service: TestRunService,
    ) -> None:
        self._snapshot_service = snapshot_service
        self._queue_service = queue_service
        self._task_service = task_service
        self._project_service = project_service
        self._transition_repo = transition_repo
        self._test_run_service = test_run_service

    async def export_report(
        self,
        *,
        scope_type: str,
        scope_id: str,
        scope_name: str | None,
        generated_at: datetime,
        output_format: str,
        content: str,
        export_path: str,
        attach_task_id: str | None = None,
    ) -> WorkDailyExportResult:
        """Export a daily review report and optionally attach it as evidence."""
        export_file = self._resolve_export_file(
            export_path=export_path,
            scope_type=scope_type,
            scope_id=scope_id,
            generated_at=generated_at,
            output_format=output_format,
        )
        export_file.parent.mkdir(parents=True, exist_ok=True)
        self._write_export_atomically(export_file, content)

        resolved_export = export_file.resolve()
        stat = resolved_export.stat()
        exported_at = datetime.now(UTC)
        modified_at = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
        attached_task: Task | None = None

        if attach_task_id is not None:
            attached_task = await self._task_service.get_task(attach_task_id)
            if attached_task is None:
                self._cleanup_export_file(
                    resolved_export,
                    cause=ValueError(
                        f"Task not found for attachment: {attach_task_id}"
                    ),
                )
                raise ValueError(f"Task not found for attachment: {attach_task_id}")

            from pms.services.task_evidence_service import TaskEvidenceService

            evidence_service = TaskEvidenceService(
                self._task_service.db,
                self._task_service.metrics,
            )
            metadata = {
                "scope_type": scope_type,
                "scope_id": scope_id,
                "scope_name": scope_name,
                "format": output_format,
                "generated_at": generated_at.isoformat(),
                "exported_at": exported_at.isoformat(),
                "file_modified_at": modified_at.isoformat(),
                "file_size_bytes": stat.st_size,
            }

            try:
                await evidence_service.add_evidence(
                    task_id=attached_task.id,
                    evidence_type="work_daily_report",
                    reference=str(resolved_export),
                    description="Daily review export",
                    metadata=metadata,
                    created_by="work_daily",
                )
            except Exception as exc:
                self._cleanup_export_file(resolved_export, cause=exc)
                raise

        return WorkDailyExportResult(
            path=resolved_export,
            size_bytes=stat.st_size,
            exported_at=exported_at,
            modified_at=modified_at,
            attached_task=attached_task,
        )

    async def build_summary(
        self,
        *,
        scope_type: str,
        scope_id: str,
        task_limit: int,
        test_limit: int,
        queue_limit: int,
        stale_days: int,
        at_risk_days: int,
        include_timeline: bool,
        timeline_limit: int,
        include_history: bool,
        history_limit: int,
        view: str,
    ) -> WorkDailySummary | None:
        """Build a daily review summary."""
        if view == "trace":
            include_history = True
            include_timeline = True

        snapshot = await self._snapshot_service.get_snapshot(
            scope_type=scope_type,
            scope_id=scope_id,
            task_limit=task_limit,
            test_limit=test_limit,
        )
        if snapshot is None:
            return None

        scope_project_ids = await self._snapshot_service._get_project_ids(
            scope_type, scope_id
        )
        project_filter = scope_id if scope_type == "project" else None
        queues = await self._queue_service.list_presets(
            project_id=project_filter,
            limit=queue_limit,
            stale_days=stale_days,
            at_risk_days=at_risk_days,
        )
        queue_map = {summary.name: summary for summary in queues}
        ready_summary = queue_map.get("ready")
        blocked_summary = queue_map.get("blocked")

        project_names: dict[str, str | None] = {}
        project_ids: set[str] = set()
        for snapshot_task in snapshot.recent_tasks:
            if snapshot_task.project_id:
                project_ids.add(snapshot_task.project_id)
        for run in snapshot.recent_test_runs:
            if run.project_id:
                project_ids.add(run.project_id)
        for summary in queues:
            for task_obj in summary.items:
                if task_obj.project_id:
                    project_ids.add(task_obj.project_id)
        project_ids.update(scope_project_ids)
        for project_id in project_ids:
            project = await self._project_service.get_project(project_id)
            if project:
                project_names[project_id] = project.name

        review_history = None
        if include_history:
            review_history = await self._snapshot_service.list_reviews(
                scope_type=scope_type,
                scope_id=scope_id,
                limit=history_limit,
                offset=0,
            )

        recent_runs = list(snapshot.recent_test_runs)
        run_window = "since last review"
        if not recent_runs:
            runs: list[WorkSnapshotRunHighlight] = []
            if scope_project_ids:
                if scope_type == "project":
                    result = await self._test_run_service.list_test_runs(
                        project_id=scope_id,
                        limit=test_limit,
                        offset=0,
                    )
                else:
                    seed_limit = max(test_limit * 5, 50)
                    result = await self._test_run_service.list_test_runs(
                        limit=seed_limit,
                        offset=0,
                    )
                for run_record in result.items:
                    if (
                        run_record.project_id
                        and run_record.project_id not in scope_project_ids
                    ):
                        continue
                    runs.append(
                        WorkSnapshotRunHighlight(
                            id=run_record.id,
                            project_id=run_record.project_id,
                            success=run_record.success,
                            finished_at=run_record.finished_at,
                            command=run_record.command,
                        )
                    )
                    if len(runs) >= test_limit:
                        break
            recent_runs = runs
            run_window = "latest"

        transitions: list[StateTransition] = []
        timeline_window = "since last review"
        if include_timeline and scope_project_ids:
            transitions = await self._transition_repo.get_task_transitions_for_projects(
                project_ids=scope_project_ids,
                start_time=snapshot.last_reviewed_at,
                limit=timeline_limit,
            )
            if snapshot.last_reviewed_at and not transitions:
                transitions = (
                    await self._transition_repo.get_task_transitions_for_projects(
                        project_ids=scope_project_ids,
                        start_time=None,
                        limit=timeline_limit,
                    )
                )
                timeline_window = "latest"
            elif snapshot.last_reviewed_at is None:
                timeline_window = "latest"

        task_titles: dict[str, str] = {}
        if transitions:
            transition_ids = list({transition.entity_id for transition in transitions})
            tasks = await self._task_service.get_tasks_by_ids(transition_ids)
            task_titles = {task_obj.id: task_obj.title for task_obj in tasks}

        params: WorkDailyParams = {
            "scope_type": scope_type,
            "scope_id": scope_id,
            "task_limit": task_limit,
            "test_limit": test_limit,
            "queue_limit": queue_limit,
            "stale_days": stale_days,
            "at_risk_days": at_risk_days,
            "include_timeline": include_timeline,
            "timeline_limit": timeline_limit,
            "include_history": include_history,
            "history_limit": history_limit,
            "view": view,
        }

        return WorkDailySummary(
            snapshot=snapshot,
            queues=queues,
            ready_summary=ready_summary,
            blocked_summary=blocked_summary,
            recent_runs=recent_runs,
            run_window=run_window,
            transitions=transitions,
            timeline_window=timeline_window,
            review_history=review_history,
            project_names=project_names,
            task_titles=task_titles,
            scope_project_ids=scope_project_ids,
            queue_limit=queue_limit,
            include_timeline=include_timeline,
            include_history=include_history,
            view=view,
            params=params,
        )

    def _resolve_export_file(
        self,
        *,
        export_path: str,
        scope_type: str,
        scope_id: str,
        generated_at: datetime,
        output_format: str,
    ) -> Path:
        export_root = Path(export_path)
        ext = (
            "json"
            if output_format == "json"
            else "csv"
            if output_format == "csv"
            else "txt"
        )
        filename = (
            f"work-daily-{scope_type}-{scope_id}-{generated_at:%Y%m%d-%H%M%S}.{ext}"
        )

        if export_root.exists() and export_root.is_dir():
            return export_root / filename
        if export_root.suffix:
            return export_root
        return export_root / filename

    def _write_export_atomically(self, export_file: Path, content: str) -> None:
        write_text_atomic(export_file, content, encoding="utf-8")

    def _cleanup_export_file(self, export_file: Path, *, cause: Exception) -> None:
        try:
            export_file.unlink()
        except FileNotFoundError:
            return
        except OSError as exc:
            raise RuntimeError(
                f"Failed to clean up daily review export after attachment failure: "
                f"{export_file} ({exc})"
            ) from cause
