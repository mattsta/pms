"""Base model with common fields and behaviors."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Self

from pms.models.json_types import ModelObject


def generate_id() -> str:
    """Generate a new UUID string."""
    return str(uuid.uuid4())


def now_utc() -> datetime:
    """Get current UTC timestamp."""
    return datetime.now(UTC)


@dataclass
class BaseModel:
    """
    Base class for all domain models.

    Provides:
    - Automatic ID generation
    - Timestamps (created_at, updated_at)
    - Event tracking (last_event_sequence)
    - Revision tracking (last_revision_number)
    - Serialization helpers
    """

    id: str = field(default_factory=generate_id)
    created_at: datetime = field(default_factory=now_utc)
    updated_at: datetime = field(default_factory=now_utc)
    last_event_sequence: int = 0
    last_revision_number: int = 0

    def to_dict(self) -> ModelObject:
        """Convert model to dictionary for serialization."""
        raw = asdict(self)
        data: ModelObject = {}
        # Convert datetime objects to ISO strings
        for key, value in raw.items():
            if isinstance(value, datetime):
                data[key] = value.isoformat()
            elif isinstance(value, tuple):
                data[key] = [item for item in value]
            else:
                data[key] = value
        return data

    @classmethod
    def from_dict(cls, data: ModelObject) -> Self:
        """Create model from dictionary."""
        # Convert ISO strings back to datetime
        processed: ModelObject = {}
        for key, value in data.items():
            if key in (
                "created_at",
                "updated_at",
                "completed_at",
                "due_date",
                "target_date",
                "ended_at",
            ):
                if value and isinstance(value, str):
                    processed[key] = datetime.fromisoformat(value)
                else:
                    processed[key] = value
            else:
                processed[key] = value
        factory: Callable[..., Self] = cls
        return factory(**processed)

    def touch(self) -> Self:
        """Update the updated_at timestamp."""
        self.updated_at = now_utc()
        return self

    def with_event(self, sequence: int) -> Self:
        """Update last event sequence number."""
        self.last_event_sequence = sequence
        self.updated_at = now_utc()
        return self

    def with_revision(self, revision: int) -> Self:
        """Update last revision number."""
        self.last_revision_number = revision
        self.updated_at = now_utc()
        return self


@dataclass
class VersionedModel(BaseModel):
    """
    Model with explicit version tracking for optimistic locking.

    Version is incremented on every save, preventing concurrent modifications.
    """

    version: int = 1

    def increment_version(self) -> Self:
        """Increment version for next save."""
        self.version += 1
        self.updated_at = now_utc()
        return self
