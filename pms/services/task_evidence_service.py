"""Service for task evidence management."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from pms.core.metrics import MetricsCollector
from pms.models.enums import TaskStatus
from pms.models.json_types import JsonObject
from pms.models.task_evidence import TaskEvidence
from pms.repositories.base import QueryResult
from pms.repositories.task_evidence_repository import (
    EvidenceTaskMatch,
    TaskEvidenceRepository,
)
from pms.repositories.test_run_repository import TestRunRepository

if TYPE_CHECKING:
    from pms.db.connection import Database

type TestRunConfigPayload = JsonObject


@dataclass
class TestRunSummary:
    """Summary of a test run linked to evidence."""

    id: str
    success: bool
    exit_code: int | None
    duration_seconds: float | None
    started_at: datetime
    finished_at: datetime
    command: str | None = None
    stdout: str | None = None
    stderr: str | None = None


@dataclass
class TaskEvidenceItem:
    """Evidence record with optional test run data."""

    evidence: TaskEvidence
    test_run: TestRunSummary | None = None


@dataclass
class TaskEvidencePage:
    """Paginated evidence results."""

    items: list[TaskEvidenceItem]
    total_count: int
    offset: int
    limit: int


class TaskEvidenceService:
    """Service for adding and retrieving task evidence."""

    def __init__(self, db: Database, metrics: MetricsCollector) -> None:
        self.db = db
        self.metrics = metrics
        self._repo = TaskEvidenceRepository(db)
        self._test_runs = TestRunRepository(db)

    async def add_evidence(
        self,
        task_id: str,
        evidence_type: str,
        reference: str,
        description: str | None = None,
        metadata: JsonObject | None = None,
        created_by: str = "system",
    ) -> TaskEvidence:
        """Add a new evidence record."""
        async with self.db.transaction():
            evidence = await self._add_evidence_in_transaction(
                task_id=task_id,
                evidence_type=evidence_type,
                reference=reference,
                description=description,
                metadata=metadata,
                created_by=created_by,
            )
            await self.metrics.record_counter(
                "task.evidence_added",
                labels={"task_id": task_id, "type": evidence_type},
            )
            await self.metrics.flush()
        return evidence

    async def add_test_run_evidence(
        self,
        task_id: str,
        run_id: str,
        metadata: JsonObject | None = None,
        created_by: str = "test_runner",
    ) -> TaskEvidence:
        """Add evidence linking a task to a test run."""
        return await self.add_evidence(
            task_id=task_id,
            evidence_type="test_run",
            reference=run_id,
            description="Test run attached",
            metadata=metadata,
            created_by=created_by,
        )

    async def add_test_run_evidence_batch(
        self,
        task_ids: Iterable[str],
        run_id: str,
        metadata: JsonObject | None = None,
        created_by: str = "test_runner",
    ) -> list[TaskEvidence]:
        """Add test run evidence for multiple tasks, skipping missing tasks."""
        unique_ids = list(dict.fromkeys(task_ids))
        if not unique_ids:
            return []

        placeholders = ", ".join("?" * len(unique_ids))
        rows = await self.db.fetch_all(
            f"SELECT id FROM tasks WHERE id IN ({placeholders})",
            tuple(unique_ids),
        )
        existing_ids = {row["id"] for row in rows}

        evidence_items: list[TaskEvidence] = []
        async with self.db.transaction():
            for task_id in unique_ids:
                if task_id not in existing_ids:
                    continue
                evidence_items.append(
                    await self._add_evidence_in_transaction(
                        task_id=task_id,
                        evidence_type="test_run",
                        reference=run_id,
                        description="Test run attached",
                        metadata=metadata,
                        created_by=created_by,
                    )
                )
                await self.metrics.record_counter(
                    "task.evidence_added",
                    labels={"task_id": task_id, "type": "test_run"},
                )
            if evidence_items:
                await self.metrics.flush()
        return evidence_items

    async def list_evidence(
        self,
        task_id: str,
        limit: int = 100,
        offset: int = 0,
        include_test_runs: bool = False,
        include_output: bool = False,
    ) -> TaskEvidencePage:
        """List evidence with optional test run details."""
        result = await self._repo.list_by_task(task_id, limit=limit, offset=offset)
        items = [TaskEvidenceItem(evidence=evidence) for evidence in result.items]

        if include_test_runs:
            run_ids = [
                item.evidence.reference
                for item in items
                if item.evidence.evidence_type == "test_run"
            ]
            run_map = await self._fetch_test_run_map(
                run_ids, include_output=include_output
            )
            for item in items:
                if item.evidence.evidence_type == "test_run":
                    item.test_run = run_map.get(item.evidence.reference)

        return TaskEvidencePage(
            items=items,
            total_count=result.total_count,
            offset=result.offset,
            limit=result.limit,
        )

    async def list_evidence_for_tasks(
        self,
        task_ids: list[str],
        evidence_types: list[str] | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        include_test_runs: bool = False,
        include_output: bool = False,
    ) -> dict[str, list[TaskEvidenceItem]]:
        """List evidence for multiple tasks with optional filters."""
        evidence_items = await self._repo.list_by_task_ids(
            task_ids,
            evidence_types=evidence_types,
            created_from=created_from,
            created_to=created_to,
        )
        items = [TaskEvidenceItem(evidence=item) for item in evidence_items]

        if include_test_runs:
            run_ids = [
                item.evidence.reference
                for item in items
                if item.evidence.evidence_type == "test_run"
            ]
            run_map = await self._fetch_test_run_map(
                run_ids, include_output=include_output
            )
            for item in items:
                if item.evidence.evidence_type == "test_run":
                    item.test_run = run_map.get(item.evidence.reference)

        grouped: dict[str, list[TaskEvidenceItem]] = {
            task_id: [] for task_id in task_ids
        }
        for item in items:
            grouped.setdefault(item.evidence.task_id, []).append(item)

        for entries in grouped.values():
            entries.sort(
                key=lambda item: str(item.evidence.created_at),
                reverse=True,
            )

        return grouped

    async def search_tasks_with_evidence(
        self,
        task_ids: list[str] | None = None,
        evidence_types: list[str] | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        task_statuses: list[TaskStatus] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[EvidenceTaskMatch]:
        """Search tasks that have evidence matching filters."""
        return await self._repo.search_tasks(
            task_ids=task_ids,
            evidence_types=evidence_types,
            created_from=created_from,
            created_to=created_to,
            task_statuses=task_statuses,
            limit=limit,
            offset=offset,
        )

    async def _fetch_test_run_map(
        self,
        run_ids: list[str],
        include_output: bool = False,
    ) -> dict[str, TestRunSummary]:
        rows = await self._test_runs.get_by_ids(run_ids)
        summaries: dict[str, TestRunSummary] = {}
        for row in rows:
            config_raw = row.get("config", "{}")
            config: TestRunConfigPayload = {}
            if isinstance(config_raw, str):
                parsed = json.loads(config_raw)
                if isinstance(parsed, dict):
                    config = parsed
            elif isinstance(config_raw, dict):
                config = config_raw

            command_raw = config.get("test_command") or config.get("command")
            command = command_raw if isinstance(command_raw, str) else None

            exit_code_raw = row.get("exit_code")
            exit_code = exit_code_raw if isinstance(exit_code_raw, int) else None

            duration_raw = row.get("duration_seconds")
            duration_seconds = (
                float(duration_raw) if isinstance(duration_raw, (int, float)) else None
            )

            started_raw = row.get("started_at")
            finished_raw = row.get("finished_at")
            if not isinstance(started_raw, str) or not isinstance(finished_raw, str):
                continue

            stdout_raw = row.get("stdout")
            stderr_raw = row.get("stderr")
            summary = TestRunSummary(
                id=str(row["id"]),
                success=bool(row.get("success")),
                exit_code=exit_code,
                duration_seconds=duration_seconds,
                started_at=datetime.fromisoformat(started_raw),
                finished_at=datetime.fromisoformat(finished_raw),
                command=command,
                stdout=stdout_raw
                if include_output and isinstance(stdout_raw, str)
                else None,
                stderr=stderr_raw
                if include_output and isinstance(stderr_raw, str)
                else None,
            )
            summaries[summary.id] = summary
        return summaries

    async def _add_evidence_in_transaction(
        self,
        task_id: str,
        evidence_type: str,
        reference: str,
        description: str | None = None,
        metadata: JsonObject | None = None,
        created_by: str = "system",
    ) -> TaskEvidence:
        """Insert an evidence row while the caller owns the transaction."""
        return await self._repo.create(
            task_id=task_id,
            evidence_type=evidence_type,
            reference=reference,
            description=description,
            metadata=metadata,
            created_by=created_by,
        )
