"""Repository for work snapshot review records."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from pms.models.work_snapshot import WorkSnapshotReview
from pms.repositories.base import QueryResult

if TYPE_CHECKING:
    from pms.db.connection import Database


class WorkSnapshotReviewRepository:
    """Repository for work snapshot reviews."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def create(
        self,
        scope_type: str,
        scope_id: str,
        reviewed_by: str | None = None,
        note: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> WorkSnapshotReview:
        review = WorkSnapshotReview(
            scope_type=scope_type,
            scope_id=scope_id,
            reviewed_by=reviewed_by,
            note=note,
            metadata=metadata or {},
            reviewed_at=datetime.now(UTC),
        )

        await self.db.execute(
            """
            INSERT INTO work_snapshot_reviews (
                id, scope_type, scope_id, reviewed_at, reviewed_by, note, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                review.id,
                review.scope_type,
                review.scope_id,
                review.reviewed_at.isoformat(),
                review.reviewed_by,
                review.note,
                json.dumps(review.metadata),
            ),
        )
        return review

    async def get_latest(
        self, scope_type: str, scope_id: str
    ) -> WorkSnapshotReview | None:
        row = await self.db.fetch_one(
            """
            SELECT * FROM work_snapshot_reviews
            WHERE scope_type = ? AND scope_id = ?
            ORDER BY reviewed_at DESC
            LIMIT 1
            """,
            (scope_type, scope_id),
        )
        return self._row_to_model(row) if row else None

    async def list_reviews(
        self,
        scope_type: str,
        scope_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> QueryResult[WorkSnapshotReview]:
        count_row = await self.db.fetch_one(
            """
            SELECT COUNT(*) as count FROM work_snapshot_reviews
            WHERE scope_type = ? AND scope_id = ?
            """,
            (scope_type, scope_id),
        )
        total = count_row["count"] if count_row else 0

        rows = await self.db.fetch_all(
            """
            SELECT * FROM work_snapshot_reviews
            WHERE scope_type = ? AND scope_id = ?
            ORDER BY reviewed_at DESC
            LIMIT ? OFFSET ?
            """,
            (scope_type, scope_id, limit, offset),
        )
        return QueryResult(
            items=[self._row_to_model(row) for row in rows],
            total_count=total,
            offset=offset,
            limit=limit,
        )

    def _row_to_model(self, row: dict[str, Any]) -> WorkSnapshotReview:
        return WorkSnapshotReview(
            id=row["id"],
            scope_type=row["scope_type"],
            scope_id=row["scope_id"],
            reviewed_at=datetime.fromisoformat(row["reviewed_at"]),
            reviewed_by=row.get("reviewed_by"),
            note=row.get("note"),
            metadata=json.loads(row.get("metadata") or "{}"),
        )
