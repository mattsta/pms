"""Repository for task evidence records."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pms.models.enums import TaskStatus
from pms.models.task_evidence import TaskEvidence
from pms.repositories.base import QueryResult

if TYPE_CHECKING:
    from pms.db.connection import Database


@dataclass
class EvidenceTaskMatch:
    """Evidence search result grouped by task."""

    task_id: str
    last_evidence_at: datetime | None
    evidence_count: int


class TaskEvidenceRepository:
    """Repository for task evidence (append-only)."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def create(
        self,
        task_id: str,
        evidence_type: str,
        reference: str,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
        created_by: str = "system",
    ) -> TaskEvidence:
        """Create a new evidence record."""
        evidence = TaskEvidence(
            task_id=task_id,
            evidence_type=evidence_type,
            reference=reference,
            description=description,
            metadata=metadata or {},
            created_by=created_by,
        )

        await self.db.execute(
            """
            INSERT INTO task_evidence (
                id, task_id, evidence_type, reference, description,
                metadata, created_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                evidence.id,
                evidence.task_id,
                evidence.evidence_type,
                evidence.reference,
                evidence.description,
                json.dumps(evidence.metadata),
                evidence.created_by,
                evidence.created_at.isoformat(),
            ),
        )
        return evidence

    async def list_by_task(
        self,
        task_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[TaskEvidence]:
        """List evidence records for a task."""
        count_row = await self.db.fetch_one(
            "SELECT COUNT(*) as count FROM task_evidence WHERE task_id = ?",
            (task_id,),
        )
        total = count_row["count"] if count_row else 0

        rows = await self.db.fetch_all(
            """
            SELECT * FROM task_evidence
            WHERE task_id = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (task_id, limit, offset),
        )

        items = [self._row_to_model(row) for row in rows]
        return QueryResult(items=items, total_count=total, offset=offset, limit=limit)

    async def list_by_task_ids(
        self,
        task_ids: list[str],
        evidence_types: list[str] | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> list[TaskEvidence]:
        """List evidence for multiple task IDs with optional filters."""
        if not task_ids:
            return []

        unique_ids = list(dict.fromkeys(task_ids))
        where_clauses = []
        params: list[Any] = []
        placeholders = ", ".join("?" * len(unique_ids))
        where_clauses.append(f"task_id IN ({placeholders})")
        params.extend(unique_ids)

        if evidence_types:
            type_placeholders = ", ".join("?" * len(evidence_types))
            where_clauses.append(f"evidence_type IN ({type_placeholders})")
            params.extend(evidence_types)

        if created_from:
            where_clauses.append("created_at >= ?")
            params.append(created_from.isoformat())
        if created_to:
            where_clauses.append("created_at <= ?")
            params.append(created_to.isoformat())

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        rows = await self.db.fetch_all(
            f"""
            SELECT * FROM task_evidence
            WHERE {where_sql}
            ORDER BY created_at DESC
            """,
            tuple(params),
        )
        return [self._row_to_model(row) for row in rows]

    async def search_tasks(
        self,
        task_ids: list[str] | None = None,
        evidence_types: list[str] | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        task_statuses: list[TaskStatus] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[EvidenceTaskMatch]:
        """Search for tasks with evidence filtered by criteria."""
        where_clauses = []
        params: list[Any] = []
        join_sql = ""

        if task_ids:
            unique_ids = list(dict.fromkeys(task_ids))
            placeholders = ", ".join("?" * len(unique_ids))
            where_clauses.append(f"te.task_id IN ({placeholders})")
            params.extend(unique_ids)

        if evidence_types:
            type_placeholders = ", ".join("?" * len(evidence_types))
            where_clauses.append(f"te.evidence_type IN ({type_placeholders})")
            params.extend(evidence_types)

        if created_from:
            where_clauses.append("te.created_at >= ?")
            params.append(created_from.isoformat())
        if created_to:
            where_clauses.append("te.created_at <= ?")
            params.append(created_to.isoformat())

        if task_statuses:
            join_sql = "INNER JOIN tasks t ON t.id = te.task_id"
            status_placeholders = ", ".join("?" * len(task_statuses))
            where_clauses.append(f"t.status IN ({status_placeholders})")
            params.extend([status.value for status in task_statuses])

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        count_row = await self.db.fetch_one(
            f"""
            SELECT COUNT(*) as count FROM (
                SELECT te.task_id
                FROM task_evidence te
                {join_sql}
                WHERE {where_sql}
                GROUP BY te.task_id
            ) as grouped
            """,
            tuple(params),
        )
        total = count_row["count"] if count_row else 0

        rows = await self.db.fetch_all(
            f"""
            SELECT
                te.task_id,
                MAX(te.created_at) as last_evidence_at,
                COUNT(*) as evidence_count
            FROM task_evidence te
            {join_sql}
            WHERE {where_sql}
            GROUP BY te.task_id
            ORDER BY last_evidence_at DESC
            LIMIT ? OFFSET ?
            """,
            tuple([*params, limit, offset]),
        )

        items = [
            EvidenceTaskMatch(
                task_id=row["task_id"],
                last_evidence_at=(
                    datetime.fromisoformat(row["last_evidence_at"])
                    if row.get("last_evidence_at")
                    else None
                ),
                evidence_count=row.get("evidence_count") or 0,
            )
            for row in rows
        ]
        return QueryResult(items=items, total_count=total, offset=offset, limit=limit)

    def _row_to_model(self, row: dict[str, Any]) -> TaskEvidence:
        metadata_raw = row.get("metadata", "{}")
        metadata = (
            json.loads(metadata_raw) if isinstance(metadata_raw, str) else metadata_raw
        )
        return TaskEvidence(
            id=row["id"],
            task_id=row["task_id"],
            evidence_type=row["evidence_type"],
            reference=row["reference"],
            description=row.get("description"),
            metadata=metadata or {},
            created_by=row.get("created_by", "system"),
            created_at=_parse_datetime_required(row.get("created_at"), "created_at"),
            updated_at=_parse_datetime_required(row.get("created_at"), "created_at"),
        )


def _parse_datetime_required(value: Any, field_name: str) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    msg = f"Invalid datetime value for {field_name}: {value!r}"
    raise ValueError(msg)
