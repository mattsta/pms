"""Revision tracking and snapshot management for multi-version documents."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, TypeVar

from pms.exceptions.base import DatabaseError

if TYPE_CHECKING:
    from pms.db.connection import Database


class ChangeType(StrEnum):
    """Type of change in a revision."""

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    RESTORE = "restore"


T = TypeVar("T")


@dataclass(frozen=True)
class Change:
    """A single field change within a revision."""

    field_name: str
    old_value: str | None
    new_value: str | None
    change_type: ChangeType


@dataclass(frozen=True)
class Revision[T]:
    """
    A revision represents a point-in-time state of an entity.

    Revisions are immutable and form a linked list through parent_id.
    The current state is always the latest revision.
    """

    revision_id: str
    entity_type: str  # e.g., "project", "task", "document"
    entity_id: str
    revision_number: int
    parent_revision_id: str | None  # Links to previous revision
    content: T  # The full state at this revision
    content_hash: str  # SHA-256 of content for integrity
    changes: tuple[Change, ...]  # What changed from parent
    change_type: ChangeType
    created_at: datetime
    created_by: str | None = None
    message: str | None = None  # Revision message/description
    metadata: dict[str, str] = field(default_factory=dict)

    @classmethod
    def create_initial(
        cls,
        entity_type: str,
        entity_id: str,
        content: T,
        created_by: str | None = None,
        message: str | None = None,
    ) -> Revision[T]:
        """Create the first revision of an entity."""
        content_json = json.dumps(content, sort_keys=True, default=str)
        content_hash = hashlib.sha256(content_json.encode()).hexdigest()

        return cls(
            revision_id=str(uuid.uuid4()),
            entity_type=entity_type,
            entity_id=entity_id,
            revision_number=1,
            parent_revision_id=None,
            content=content,
            content_hash=content_hash,
            changes=(),
            change_type=ChangeType.CREATE,
            created_at=datetime.now(UTC),
            created_by=created_by,
            message=message or "Initial revision",
        )

    @classmethod
    def create_from_parent(
        cls,
        parent: Revision[T],
        new_content: T,
        changes: list[Change],
        created_by: str | None = None,
        message: str | None = None,
    ) -> Revision[T]:
        """Create a new revision based on a parent revision."""
        content_json = json.dumps(new_content, sort_keys=True, default=str)
        content_hash = hashlib.sha256(content_json.encode()).hexdigest()

        return cls(
            revision_id=str(uuid.uuid4()),
            entity_type=parent.entity_type,
            entity_id=parent.entity_id,
            revision_number=parent.revision_number + 1,
            parent_revision_id=parent.revision_id,
            content=new_content,
            content_hash=content_hash,
            changes=tuple(changes),
            change_type=ChangeType.UPDATE,
            created_at=datetime.now(UTC),
            created_by=created_by,
            message=message,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize revision to dictionary."""
        return {
            "revision_id": self.revision_id,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "revision_number": self.revision_number,
            "parent_revision_id": self.parent_revision_id,
            "content": self.content,
            "content_hash": self.content_hash,
            "changes": [
                {
                    "field_name": c.field_name,
                    "old_value": c.old_value,
                    "new_value": c.new_value,
                    "change_type": c.change_type.value,
                }
                for c in self.changes
            ],
            "change_type": self.change_type.value,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "message": self.message,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class Snapshot[T]:
    """
    A snapshot is a periodic capture of computed state.

    Snapshots optimize read performance by avoiding full event replay.
    They are created periodically and can be used as starting points
    for state reconstruction.
    """

    snapshot_id: str
    entity_type: str
    entity_id: str
    state: T  # The computed state at snapshot time
    state_hash: str
    last_event_sequence: int  # Events processed up to this point
    last_revision_number: int  # Revision at snapshot time
    created_at: datetime
    metadata: dict[str, str] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        entity_type: str,
        entity_id: str,
        state: T,
        last_event_sequence: int,
        last_revision_number: int,
    ) -> Snapshot[T]:
        """Create a new snapshot of current state."""
        state_json = json.dumps(state, sort_keys=True, default=str)
        state_hash = hashlib.sha256(state_json.encode()).hexdigest()

        return cls(
            snapshot_id=str(uuid.uuid4()),
            entity_type=entity_type,
            entity_id=entity_id,
            state=state,
            state_hash=state_hash,
            last_event_sequence=last_event_sequence,
            last_revision_number=last_revision_number,
            created_at=datetime.now(UTC),
        )


@dataclass
class RevisionDiff:
    """Difference between two revisions."""

    from_revision: int
    to_revision: int
    entity_type: str
    entity_id: str
    changes: list[Change]
    intermediate_revisions: list[str]  # Revision IDs between from and to


class RevisionStore:
    """
    Store for managing entity revisions.

    Provides versioning, history tracking, and diff capabilities.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    @staticmethod
    def is_revision_conflict_error(exc: DatabaseError) -> bool:
        """Return True when a revision insert collides on revision numbering."""
        message = str(exc).lower()
        return (
            "unique constraint failed" in message
            and "revisions.entity_type" in message
            and "revisions.entity_id" in message
            and "revisions.revision_number" in message
        )

    async def save_revision(self, revision: Revision[Any]) -> Revision[Any]:
        """Save a revision to the store."""
        await self.db.execute(
            """
            INSERT INTO revisions (
                revision_id, entity_type, entity_id, revision_number,
                parent_revision_id, content, content_hash, changes,
                change_type, created_at, created_by, message, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                revision.revision_id,
                revision.entity_type,
                revision.entity_id,
                revision.revision_number,
                revision.parent_revision_id,
                json.dumps(revision.content, default=str),
                revision.content_hash,
                json.dumps(
                    [
                        {
                            "field_name": c.field_name,
                            "old_value": c.old_value,
                            "new_value": c.new_value,
                            "change_type": c.change_type.value,
                        }
                        for c in revision.changes
                    ]
                ),
                revision.change_type.value,
                revision.created_at.isoformat(),
                revision.created_by,
                revision.message,
                json.dumps(revision.metadata),
            ),
        )
        return revision

    async def get_revision(
        self,
        entity_type: str,
        entity_id: str,
        revision_number: int | None = None,
    ) -> Revision[Any] | None:
        """
        Get a specific revision, or the latest if revision_number is None.
        """
        if revision_number is None:
            row = await self.db.fetch_one(
                """
                SELECT * FROM revisions
                WHERE entity_type = ? AND entity_id = ?
                ORDER BY revision_number DESC
                LIMIT 1
                """,
                (entity_type, entity_id),
            )
        else:
            row = await self.db.fetch_one(
                """
                SELECT * FROM revisions
                WHERE entity_type = ? AND entity_id = ? AND revision_number = ?
                """,
                (entity_type, entity_id, revision_number),
            )

        if row is None:
            return None

        return self._row_to_revision(row)

    async def get_revision_by_id(self, revision_id: str) -> Revision[Any] | None:
        """Get a revision by its ID."""
        row = await self.db.fetch_one(
            "SELECT * FROM revisions WHERE revision_id = ?",
            (revision_id,),
        )
        if row is None:
            return None
        return self._row_to_revision(row)

    async def get_history(
        self,
        entity_type: str,
        entity_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Revision[Any]]:
        """Get revision history for an entity, newest first."""
        rows = await self.db.fetch_all(
            """
            SELECT * FROM revisions
            WHERE entity_type = ? AND entity_id = ?
            ORDER BY revision_number DESC
            LIMIT ? OFFSET ?
            """,
            (entity_type, entity_id, limit, offset),
        )
        return [self._row_to_revision(row) for row in rows]

    async def get_revision_count(self, entity_type: str, entity_id: str) -> int:
        """Get total number of revisions for an entity."""
        result = await self.db.fetch_one(
            """
            SELECT COUNT(*) as count FROM revisions
            WHERE entity_type = ? AND entity_id = ?
            """,
            (entity_type, entity_id),
        )
        return result["count"] if result else 0

    async def diff(
        self,
        entity_type: str,
        entity_id: str,
        from_revision: int,
        to_revision: int,
    ) -> RevisionDiff:
        """Compute diff between two revisions."""
        # Get all revisions in range
        rows = await self.db.fetch_all(
            """
            SELECT * FROM revisions
            WHERE entity_type = ? AND entity_id = ?
            AND revision_number > ? AND revision_number <= ?
            ORDER BY revision_number ASC
            """,
            (entity_type, entity_id, from_revision, to_revision),
        )

        all_changes: list[Change] = []
        revision_ids: list[str] = []

        for row in rows:
            revision_ids.append(row["revision_id"])
            changes_data = json.loads(row["changes"])
            for c in changes_data:
                all_changes.append(
                    Change(
                        field_name=c["field_name"],
                        old_value=c["old_value"],
                        new_value=c["new_value"],
                        change_type=ChangeType(c["change_type"]),
                    )
                )

        return RevisionDiff(
            from_revision=from_revision,
            to_revision=to_revision,
            entity_type=entity_type,
            entity_id=entity_id,
            changes=all_changes,
            intermediate_revisions=revision_ids,
        )

    async def save_snapshot(self, snapshot: Snapshot[Any]) -> Snapshot[Any]:
        """Save a state snapshot."""
        await self.db.execute(
            """
            INSERT INTO snapshots (
                snapshot_id, entity_type, entity_id, state, state_hash,
                last_event_sequence, last_revision_number, created_at, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot.snapshot_id,
                snapshot.entity_type,
                snapshot.entity_id,
                json.dumps(snapshot.state, default=str),
                snapshot.state_hash,
                snapshot.last_event_sequence,
                snapshot.last_revision_number,
                snapshot.created_at.isoformat(),
                json.dumps(snapshot.metadata),
            ),
        )
        return snapshot

    async def get_latest_snapshot(
        self,
        entity_type: str,
        entity_id: str,
    ) -> Snapshot[Any] | None:
        """Get the most recent snapshot for an entity."""
        row = await self.db.fetch_one(
            """
            SELECT * FROM snapshots
            WHERE entity_type = ? AND entity_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (entity_type, entity_id),
        )
        if row is None:
            return None
        return self._row_to_snapshot(row)

    def _row_to_revision(self, row: dict[str, Any]) -> Revision[Any]:
        """Convert database row to Revision."""
        changes_data = json.loads(row["changes"])
        return Revision(
            revision_id=row["revision_id"],
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            revision_number=row["revision_number"],
            parent_revision_id=row["parent_revision_id"],
            content=json.loads(row["content"]),
            content_hash=row["content_hash"],
            changes=tuple(
                Change(
                    field_name=c["field_name"],
                    old_value=c["old_value"],
                    new_value=c["new_value"],
                    change_type=ChangeType(c["change_type"]),
                )
                for c in changes_data
            ),
            change_type=ChangeType(row["change_type"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            created_by=row["created_by"],
            message=row["message"],
            metadata=json.loads(row["metadata"]),
        )

    def _row_to_snapshot(self, row: dict[str, Any]) -> Snapshot[Any]:
        """Convert database row to Snapshot."""
        return Snapshot(
            snapshot_id=row["snapshot_id"],
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            state=json.loads(row["state"]),
            state_hash=row["state_hash"],
            last_event_sequence=row["last_event_sequence"],
            last_revision_number=row["last_revision_number"],
            created_at=datetime.fromisoformat(row["created_at"]),
            metadata=json.loads(row["metadata"]),
        )
