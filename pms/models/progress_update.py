"""Progress update model for tracking micro-updates on tasks."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from pms.models.base import BaseModel, now_utc
from pms.models.json_types import JsonObject, ModelObject


@dataclass
class ProgressUpdate(BaseModel):
    """
    A single progress update for a task.

    Immutable record in the progress timeline showing:
    - Current completion percentage
    - Status message describing progress
    - Who made the update
    - When it was made
    - Delta from previous update
    """

    # Required fields first
    task_id: str = ""
    percent_complete: int = 0  # 0-100
    status_message: str = ""
    updated_by: str = ""  # agent_id or user_id

    # Optional fields with defaults
    timestamp: datetime = field(default_factory=now_utc)

    # Calculated fields
    duration_since_last_update_seconds: int | None = None
    percent_delta: int | None = None

    # Flexible metadata for context
    metadata: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate progress percentage."""
        if not 0 <= self.percent_complete <= 100:
            raise ValueError(
                f"percent_complete must be 0-100, got {self.percent_complete}"
            )

    @property
    def duration_since_last_update_hours(self) -> float | None:
        """Get duration since last update in hours."""
        if self.duration_since_last_update_seconds is None:
            return None
        return self.duration_since_last_update_seconds / 3600.0

    def to_dict(self) -> ModelObject:
        """Convert to dictionary."""
        data = super().to_dict()
        data["timestamp"] = self.timestamp.isoformat()
        return data


@dataclass
class ProgressTimeline:
    """Complete progress timeline for a task."""

    task_id: str
    updates: list[ProgressUpdate]
    current_percent: int = 0
    total_duration_seconds: int = 0
    average_velocity_percent_per_hour: float = 0.0  # Percent progress per hour
    estimated_completion_time: datetime | None = None

    @property
    def total_duration_hours(self) -> float:
        """Get total duration in hours."""
        return self.total_duration_seconds / 3600.0

    @property
    def is_complete(self) -> bool:
        """Check if task has reached 100%."""
        return self.current_percent >= 100

    @property
    def is_on_track(self) -> bool:
        """
        Simple heuristic for whether progress is on track.

        On track if velocity > 0 and consistent updates.
        """
        return self.average_velocity_percent_per_hour > 0

    def get_velocity_trend(self) -> str:
        """
        Get velocity trend (accelerating, stable, decelerating).

        Returns:
            'accelerating', 'stable', or 'decelerating'
        """
        if len(self.updates) < 3:
            return "stable"

        # Compare recent velocity to earlier velocity
        recent = self.updates[:3]
        earlier = self.updates[3:6] if len(self.updates) > 5 else self.updates[3:]

        if not earlier:
            return "stable"

        recent_deltas = [u.percent_delta for u in recent if u.percent_delta]
        earlier_deltas = [u.percent_delta for u in earlier if u.percent_delta]

        if not recent_deltas or not earlier_deltas:
            return "stable"

        recent_avg = sum(recent_deltas) / len(recent_deltas)
        earlier_avg = sum(earlier_deltas) / len(earlier_deltas)

        if recent_avg > earlier_avg * 1.2:
            return "accelerating"
        elif recent_avg < earlier_avg * 0.8:
            return "decelerating"
        return "stable"


@dataclass
class ProgressQuery:
    """Query parameters for progress updates."""

    task_id: str | None = None
    updated_by: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    limit: int = 100
    offset: int = 0
