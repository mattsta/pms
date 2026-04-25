"""State transition tracking - immutable time-series log of all state changes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from pms.models.base import BaseModel, now_utc
from pms.models.json_types import JsonObject, ModelObject, ModelValue

type TransitionInitValue = ModelValue


@dataclass
class StateTransition(BaseModel):
    """
    Immutable record of a state transition for any entity.

    This is a universal time-series log that records:
    - What changed (from_state → to_state)
    - When it changed (timestamp)
    - Who triggered it (triggered_by)
    - Why it changed (reason)
    - What caused it (caused_by_event_id)
    - Context metadata (arbitrary key-value data)
    - How long in previous state (duration_in_state_seconds)

    Used across all entity types: tasks, projects, products, workflows, etc.
    """

    # Required fields (no defaults) must come first
    entity_type: str = ""  # task, project, product, workflow, etc.
    entity_id: str = ""
    to_state: str = ""

    # Optional fields with defaults
    from_state: str | None = None  # None for initial state
    timestamp: datetime = field(default_factory=now_utc)

    # Attribution
    triggered_by: str = "system"  # agent_id, user_id, or 'system'
    reason: str | None = None  # Human-readable explanation

    # Causality
    caused_by_event_id: str | None = None  # Event that triggered this transition
    correlation_id: str | None = None  # Groups related transitions

    # Duration tracking
    duration_in_state_seconds: int | None = None  # Time spent in from_state

    # Flexible metadata
    metadata: JsonObject = field(default_factory=dict)

    @property
    def duration_in_state_hours(self) -> float | None:
        """Get duration in previous state as hours."""
        if self.duration_in_state_seconds is None:
            return None
        return self.duration_in_state_seconds / 3600.0

    def to_dict(self) -> ModelObject:
        """Convert to dictionary."""
        data = super().to_dict()
        data["timestamp"] = self.timestamp.isoformat()
        return data


@dataclass
class StateTransitionQuery:
    """Query parameters for state transition log."""

    entity_type: str | None = None
    entity_id: str | None = None
    from_state: str | None = None
    to_state: str | None = None
    triggered_by: str | None = None
    transition_kind: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    limit: int = 100
    offset: int = 0


@dataclass
class TaskStateTransition(StateTransition):
    """Task-specific state transition with task context."""

    # Task is entity_type='task', entity_id=task_id

    def __init__(
        self,
        task_id: str,
        from_state: str | None,
        to_state: str,
        triggered_by: str = "system",
        reason: str | None = None,
        **kwargs: TransitionInitValue,
    ):
        super().__init__(
            entity_type="task",
            entity_id=task_id,
            from_state=from_state,
            to_state=to_state,
            triggered_by=triggered_by,
            reason=reason,
            **kwargs,
        )


@dataclass
class ProjectStateTransition(StateTransition):
    """Project-specific state transition."""

    def __init__(
        self,
        project_id: str,
        from_state: str | None,
        to_state: str,
        triggered_by: str = "system",
        reason: str | None = None,
        **kwargs: TransitionInitValue,
    ):
        super().__init__(
            entity_type="project",
            entity_id=project_id,
            from_state=from_state,
            to_state=to_state,
            triggered_by=triggered_by,
            reason=reason,
            **kwargs,
        )


@dataclass
class ProductStateTransition(StateTransition):
    """Product-specific state transition."""

    def __init__(
        self,
        product_id: str,
        from_state: str | None,
        to_state: str,
        triggered_by: str = "system",
        reason: str | None = None,
        **kwargs: TransitionInitValue,
    ):
        super().__init__(
            entity_type="product",
            entity_id=product_id,
            from_state=from_state,
            to_state=to_state,
            triggered_by=triggered_by,
            reason=reason,
            **kwargs,
        )


@dataclass
class TransitionTimeline:
    """Timeline view of state transitions for an entity."""

    entity_type: str
    entity_id: str
    transitions: list[StateTransition]
    total_duration_seconds: int = 0
    state_durations: dict[str, int] = field(
        default_factory=dict
    )  # state -> total seconds

    @property
    def total_duration_hours(self) -> float:
        """Get total duration in hours."""
        return self.total_duration_seconds / 3600.0

    @property
    def average_state_duration_hours(self) -> float:
        """Get average time spent in each state."""
        if not self.state_durations:
            return 0.0
        avg_seconds = sum(self.state_durations.values()) / len(self.state_durations)
        return avg_seconds / 3600.0

    def get_state_duration_hours(self, state: str) -> float:
        """Get total time spent in a specific state (hours)."""
        seconds = self.state_durations.get(state, 0)
        return seconds / 3600.0

    def get_time_to_state(self, target_state: str) -> int | None:
        """
        Calculate time from first transition to reaching target state.

        Returns seconds, or None if state never reached.
        """
        if not self.transitions:
            return None

        first_timestamp = self.transitions[0].timestamp

        for transition in self.transitions:
            if transition.to_state == target_state:
                delta = transition.timestamp - first_timestamp
                return int(delta.total_seconds())

        return None  # State never reached
