"""Repository for managing progress updates."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from pms.core.ids import EntityType, generate_id
from pms.models.base import now_utc
from pms.models.progress_update import ProgressQuery, ProgressTimeline, ProgressUpdate

if TYPE_CHECKING:
    from pms.db.connection import Database


class ProgressRepository:
    """
    Repository for progress update tracking.

    Manages the immutable timeline of progress updates for tasks,
    enabling micro-updates, velocity tracking, and ETA estimation.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    async def record_progress(
        self,
        task_id: str,
        percent_complete: int,
        status_message: str,
        updated_by: str,
        metadata: dict[str, Any] | None = None,
    ) -> ProgressUpdate:
        """
        Record a progress update (append-only).

        Args:
            task_id: Task being updated
            percent_complete: Current completion percentage (0-100)
            status_message: Human-readable status update
            updated_by: Who made this update (agent_id or user_id)
            metadata: Optional context data

        Returns:
            The created ProgressUpdate

        Raises:
            ValueError: If percent_complete not in 0-100 range
        """
        if not 0 <= percent_complete <= 100:
            raise ValueError(f"percent_complete must be 0-100, got {percent_complete}")

        now = now_utc()

        # Use task snapshot to calculate deltas (avoids scanning progress history)
        task_row = await self.db.fetch_one(
            """
            SELECT current_progress_percent, last_progress_update_at
            FROM tasks
            WHERE id = ?
            """,
            (task_id,),
        )
        percent_delta = None
        duration_since_last_seconds = None

        if task_row and task_row.get("last_progress_update_at"):
            prev_percent = task_row.get("current_progress_percent", 0) or 0
            prev_timestamp = task_row["last_progress_update_at"]
            prev_dt = (
                datetime.fromisoformat(prev_timestamp)
                if isinstance(prev_timestamp, str)
                else prev_timestamp
            )
            percent_delta = percent_complete - prev_percent
            duration_since_last_seconds = int((now - prev_dt).total_seconds())

        # Create progress update
        update = ProgressUpdate(
            id=generate_id(EntityType.METRIC),
            task_id=task_id,
            percent_complete=percent_complete,
            status_message=status_message,
            updated_by=updated_by,
            timestamp=now,
            duration_since_last_update_seconds=duration_since_last_seconds,
            percent_delta=percent_delta,
            metadata=metadata or {},
        )

        # Insert into database
        await self.db.execute(
            """
            INSERT INTO task_progress_updates (
                id, task_id, percent_complete, status_message,
                updated_by, timestamp, duration_since_last_update_seconds,
                percent_delta, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                update.id,
                task_id,
                percent_complete,
                status_message,
                updated_by,
                now.isoformat(),
                duration_since_last_seconds,
                percent_delta,
                json.dumps(metadata or {}),
            ),
        )

        return update

    async def get_updates(self, query: ProgressQuery) -> list[ProgressUpdate]:
        """
        Query progress updates with flexible filtering.

        Args:
            query: Query parameters

        Returns:
            List of matching updates, ordered by timestamp DESC
        """
        sql = "SELECT * FROM task_progress_updates WHERE 1=1"
        params: list[Any] = []

        if query.task_id:
            sql += " AND task_id = ?"
            params.append(query.task_id)

        if query.updated_by:
            sql += " AND updated_by = ?"
            params.append(query.updated_by)

        if query.start_time:
            sql += " AND timestamp >= ?"
            params.append(query.start_time.isoformat())

        if query.end_time:
            sql += " AND timestamp <= ?"
            params.append(query.end_time.isoformat())

        sql += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([query.limit, query.offset])

        rows = await self.db.fetch_all(sql, tuple(params))

        return [self._row_to_update(row) for row in rows]

    async def get_timeline(self, task_id: str) -> ProgressTimeline:
        """
        Get complete progress timeline for a task with analytics.

        Calculates:
        - All updates in order
        - Current completion percentage
        - Average velocity (percent per hour)
        - Estimated completion time
        """
        updates = await self.get_updates(ProgressQuery(task_id=task_id, limit=1000))

        if not updates:
            return ProgressTimeline(
                task_id=task_id,
                updates=[],
                current_percent=0,
            )

        # Reverse to chronological order for calculations
        updates_chrono = list(reversed(updates))

        # Calculate total duration and velocity
        if len(updates_chrono) >= 2:
            first = updates_chrono[0]
            last = updates_chrono[-1]

            total_duration = (last.timestamp - first.timestamp).total_seconds()
            percent_gained = last.percent_complete - first.percent_complete

            if total_duration > 0 and percent_gained > 0:
                velocity = percent_gained / (total_duration / 3600.0)
            else:
                velocity = 0.0
        else:
            total_duration = 0
            velocity = 0.0

        # Estimate completion time
        current_percent = updates[0].percent_complete  # Most recent
        eta = None

        if velocity > 0 and current_percent < 100:
            remaining_percent = 100 - current_percent
            hours_remaining = remaining_percent / velocity
            eta = now_utc() + timedelta(hours=hours_remaining)

        return ProgressTimeline(
            task_id=task_id,
            updates=updates,  # Keep in DESC order
            current_percent=current_percent,
            total_duration_seconds=int(total_duration),
            average_velocity_percent_per_hour=velocity,
            estimated_completion_time=eta,
        )

    async def _get_latest_update(self, task_id: str) -> ProgressUpdate | None:
        """Get most recent progress update for a task."""
        row = await self.db.fetch_one(
            """
            SELECT * FROM task_progress_updates
            WHERE task_id = ?
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            (task_id,),
        )

        if row:
            return self._row_to_update(row)
        return None

    def _row_to_update(self, row: dict[str, Any]) -> ProgressUpdate:
        """Convert database row to ProgressUpdate."""
        metadata_raw = row.get("metadata", "{}")
        metadata = (
            json.loads(metadata_raw) if isinstance(metadata_raw, str) else metadata_raw
        )

        return ProgressUpdate(
            id=row["id"],
            task_id=row["task_id"],
            percent_complete=row["percent_complete"],
            status_message=row.get("status_message", ""),
            updated_by=row["updated_by"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            duration_since_last_update_seconds=row.get(
                "duration_since_last_update_seconds"
            ),
            percent_delta=row.get("percent_delta"),
            metadata=metadata,
        )
