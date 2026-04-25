"""Service for building proof bundles from task evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pms.models.enums import TaskStatus
from pms.models.json_types import JsonObject, JsonValue, ModelObject
from pms.models.task import Task
from pms.services.task_evidence_service import (
    TaskEvidenceItem,
    TaskEvidenceService,
    TestRunSummary,
)
from pms.services.test_run_service import TestRunRecord, TestRunService

if TYPE_CHECKING:
    from pms.services.task_service import TaskService


@dataclass
class ProofBundleSummary:
    """Summary totals for a proof bundle."""

    evidence_total: int
    evidence_types: dict[str, int]
    test_runs: int
    successful_test_runs: int
    log_bytes_total: int
    artifact_bytes_total: int

    def to_dict(self) -> ModelObject:
        return {
            "evidence_total": self.evidence_total,
            "evidence_types": self.evidence_types,
            "test_runs": self.test_runs,
            "successful_test_runs": self.successful_test_runs,
            "log_bytes_total": self.log_bytes_total,
            "artifact_bytes_total": self.artifact_bytes_total,
        }


@dataclass
class ProofBundle:
    """Structured proof bundle for a task."""

    task: Task
    generated_at: datetime
    summary: ProofBundleSummary
    evidence: list[TaskEvidenceItem]
    test_runs: list[TestRunRecord]

    def to_dict(self) -> ModelObject:
        return {
            "task": self.task.to_dict(),
            "generated_at": self.generated_at.isoformat(),
            "summary": self.summary.to_dict(),
            "evidence": [
                {
                    "evidence": item.evidence.to_dict(),
                    "test_run": self._test_run_summary_to_dict(item.test_run)
                    if item.test_run
                    else None,
                }
                for item in self.evidence
            ],
            "test_runs": [self._test_run_to_dict(record) for record in self.test_runs],
        }

    @staticmethod
    def _test_run_to_dict(record: TestRunRecord) -> ModelObject:
        return {
            "id": record.id,
            "server_id": record.server_id,
            "project_id": record.project_id,
            "success": record.success,
            "exit_code": record.exit_code,
            "duration_seconds": record.duration_seconds,
            "started_at": record.started_at.isoformat(),
            "finished_at": record.finished_at.isoformat(),
            "command": record.command,
            "runner": record.runner,
            "plan_id": record.plan_id,
            "task_ids": list(record.task_ids),
            "stdout": record.stdout,
            "stderr": record.stderr,
            "logs": record.logs or None,
            "artifacts": record.artifacts or None,
        }

    @staticmethod
    def _test_run_summary_to_dict(summary: TestRunSummary) -> ModelObject:
        return {
            "id": summary.id,
            "success": summary.success,
            "exit_code": summary.exit_code,
            "duration_seconds": summary.duration_seconds,
            "started_at": summary.started_at.isoformat(),
            "finished_at": summary.finished_at.isoformat(),
            "command": summary.command,
            "stdout": summary.stdout,
            "stderr": summary.stderr,
        }


class ProofBundleService:
    """Build proof bundles for tasks."""

    def __init__(
        self,
        task_service: TaskService,
        evidence_service: TaskEvidenceService,
        test_run_service: TestRunService,
    ) -> None:
        self._task_service = task_service
        self._evidence_service = evidence_service
        self._test_run_service = test_run_service

    async def build_task_bundle(
        self,
        task_id: str,
        include_output: bool = False,
        include_logs: bool = False,
        include_artifacts: bool = False,
    ) -> ProofBundle | None:
        task = await self._task_service.get_task(task_id)
        if task is None:
            return None

        evidence_page = await self._evidence_service.list_evidence(
            task_id=task_id,
            include_test_runs=True,
            include_output=include_output,
        )
        test_run_ids = [
            item.evidence.reference
            for item in evidence_page.items
            if item.evidence.evidence_type == "test_run"
        ]

        test_runs: dict[str, TestRunRecord] = {}
        if include_output or include_logs or include_artifacts:
            for run_id in test_run_ids:
                record = await self._test_run_service.get_test_run(
                    run_id,
                    include_output=include_output,
                    include_logs=include_logs,
                    include_artifacts=include_artifacts,
                )
                if record:
                    test_runs[run_id] = record

        summary = self._build_summary(evidence_page.items, test_runs)

        return ProofBundle(
            task=task,
            generated_at=datetime.now(UTC),
            summary=summary,
            evidence=evidence_page.items,
            test_runs=list(test_runs.values()),
        )

    @dataclass
    class SearchItem:
        """Proof bundle search item for task-level results."""

        task: Task
        summary: ProofBundleSummary
        last_evidence_at: datetime | None
        evidence: list[TaskEvidenceItem] = field(default_factory=list)
        test_runs: list[TestRunRecord] = field(default_factory=list)

        def to_dict(self) -> ModelObject:
            return {
                "task": self.task.to_dict(),
                "summary": self.summary.to_dict(),
                "last_evidence_at": self.last_evidence_at.isoformat()
                if self.last_evidence_at
                else None,
                "evidence": [
                    {
                        "evidence": item.evidence.to_dict(),
                        "test_run": ProofBundle._test_run_summary_to_dict(item.test_run)
                        if item.test_run
                        else None,
                    }
                    for item in self.evidence
                ],
                "test_runs": [
                    ProofBundle._test_run_to_dict(record) for record in self.test_runs
                ],
            }

    @dataclass
    class SearchPage:
        """Paginated proof bundle search results."""

        items: list[ProofBundleService.SearchItem]
        total_count: int
        offset: int
        limit: int

    async def search_bundles(
        self,
        task_ids: list[str] | None = None,
        task_statuses: list[TaskStatus] | None = None,
        evidence_types: list[str] | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        include_evidence: bool = False,
        include_test_runs: bool = False,
        include_output: bool = False,
        include_logs: bool = False,
        include_artifacts: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> ProofBundleService.SearchPage:
        """Search proof bundles across tasks using evidence filters."""
        if task_ids is not None and not task_ids:
            return ProofBundleService.SearchPage(
                items=[], total_count=0, offset=offset, limit=limit
            )
        matches = await self._evidence_service.search_tasks_with_evidence(
            task_ids=task_ids,
            evidence_types=evidence_types,
            created_from=created_from,
            created_to=created_to,
            task_statuses=task_statuses,
            limit=limit,
            offset=offset,
        )
        if not matches.items:
            return ProofBundleService.SearchPage(
                items=[],
                total_count=matches.total_count,
                offset=matches.offset,
                limit=matches.limit,
            )

        ordered_ids = [match.task_id for match in matches.items]
        task_map = {
            task.id: task
            for task in await self._task_service.get_tasks_by_ids(ordered_ids)
        }
        evidence_map = await self._evidence_service.list_evidence_for_tasks(
            ordered_ids,
            evidence_types=evidence_types,
            created_from=created_from,
            created_to=created_to,
            include_test_runs=include_test_runs,
            include_output=include_output,
        )

        run_ids: list[str] = []
        for evidence_group in evidence_map.values():
            for item in evidence_group:
                if item.evidence.evidence_type == "test_run":
                    run_ids.append(item.evidence.reference)
        unique_run_ids = list(dict.fromkeys(run_ids))
        run_records = await self._test_run_service.get_test_runs_by_ids(
            unique_run_ids,
            include_output=include_output,
            include_logs=include_logs,
            include_artifacts=include_artifacts,
        )

        items: list[ProofBundleService.SearchItem] = []
        for match in matches.items:
            task = task_map.get(match.task_id)
            if task is None:
                continue
            evidence_items = evidence_map.get(match.task_id, [])
            task_run_map = {
                item.evidence.reference: run_records[item.evidence.reference]
                for item in evidence_items
                if item.evidence.evidence_type == "test_run"
                and item.evidence.reference in run_records
            }
            summary = self._build_summary(evidence_items, task_run_map)
            items.append(
                ProofBundleService.SearchItem(
                    task=task,
                    summary=summary,
                    last_evidence_at=match.last_evidence_at,
                    evidence=evidence_items if include_evidence else [],
                    test_runs=list(task_run_map.values())
                    if include_output or include_logs or include_artifacts
                    else [],
                )
            )

        return ProofBundleService.SearchPage(
            items=items,
            total_count=matches.total_count,
            offset=matches.offset,
            limit=matches.limit,
        )

    def _build_summary(
        self,
        evidence_items: list[TaskEvidenceItem],
        test_runs: dict[str, TestRunRecord],
    ) -> ProofBundleSummary:
        evidence_types: dict[str, int] = {}
        log_bytes_total = 0
        artifact_bytes_total = 0
        successful_runs = 0
        runs_with_meta: set[str] = set()
        success_counted: set[str] = set()

        for item in evidence_items:
            evidence_types[item.evidence.evidence_type] = (
                evidence_types.get(item.evidence.evidence_type, 0) + 1
            )

            if item.evidence.evidence_type == "test_run":
                if item.test_run and item.test_run.success:
                    successful_runs += 1
                    success_counted.add(item.evidence.reference)

                meta = item.evidence.metadata
                if (
                    meta.get("log_bytes_total") is not None
                    or meta.get("artifact_bytes_total") is not None
                ):
                    log_bytes_total += self._coerce_int(meta.get("log_bytes_total", 0))
                    artifact_bytes_total += self._coerce_int(
                        meta.get("artifact_bytes_total", 0)
                    )
                    runs_with_meta.add(item.evidence.reference)

        for run_id, record in test_runs.items():
            if run_id in runs_with_meta:
                continue
            log_bytes_total += self._content_size(record.stdout)
            log_bytes_total += self._content_size(record.stderr)
            log_bytes_total += self._sum_payload_bytes(record.logs)
            artifact_bytes_total += self._sum_payload_bytes(record.artifacts)
            if record.success and run_id not in success_counted:
                successful_runs += 1

        test_run_count = len(
            [
                item
                for item in evidence_items
                if item.evidence.evidence_type == "test_run"
            ]
        )
        if successful_runs > test_run_count:
            successful_runs = test_run_count

        return ProofBundleSummary(
            evidence_total=len(evidence_items),
            evidence_types=evidence_types,
            test_runs=test_run_count,
            successful_test_runs=successful_runs,
            log_bytes_total=log_bytes_total,
            artifact_bytes_total=artifact_bytes_total,
        )

    def _content_size(self, content: str | None) -> int:
        if not content:
            return 0
        return len(content.encode("utf-8", errors="replace"))

    def _coerce_int(self, value: JsonValue) -> int:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            try:
                return int(float(value))
            except ValueError:
                return 0
        return 0

    def _sum_payload_bytes(self, payload: JsonObject) -> int:
        total = 0
        for entry in payload.values():
            if isinstance(entry, dict):
                total += self._coerce_int(entry.get("size_bytes", 0))
            elif entry is not None:
                total += self._content_size(str(entry))
        return total
