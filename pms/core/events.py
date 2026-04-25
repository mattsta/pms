"""Event-sourcing infrastructure for append-only state management."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, is_dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, TypeVar

from pms.exceptions.base import DatabaseError

if TYPE_CHECKING:
    from pms.db.connection import Database


class EventType(StrEnum):
    """Types of domain events."""

    # Actor events
    ACTOR_CREATED = "actor.created"
    ACTOR_UPDATED = "actor.updated"
    ACTOR_ARCHIVED = "actor.archived"
    ACTOR_ALIAS_CREATED = "actor_alias.created"
    ACTOR_ALIAS_ARCHIVED = "actor_alias.archived"
    ACTOR_MEMBERSHIP_CREATED = "actor_membership.created"
    ACTOR_MEMBERSHIP_ARCHIVED = "actor_membership.archived"

    # Product events
    PRODUCT_CREATED = "product.created"
    PRODUCT_UPDATED = "product.updated"
    PRODUCT_ARCHIVED = "product.archived"
    PRODUCT_SUNSET = "product.sunset"
    PRODUCT_DELETED = "product.deleted"

    # Project events
    PROJECT_CREATED = "project.created"
    PROJECT_UPDATED = "project.updated"
    PROJECT_ARCHIVED = "project.archived"
    PROJECT_DELETED = "project.deleted"
    PROJECT_ASSIGNED_TO_PRODUCT = "project.assigned_to_product"
    PROJECT_ASSIGNED_TO_ORG = "project.assigned_to_org"
    PROJECT_ASSIGNED_TO_PORTFOLIO = "project.assigned_to_portfolio"
    PROJECT_ASSIGNED_TO_PROGRAM = "project.assigned_to_program"

    # Goal events
    GOAL_CREATED = "goal.created"
    GOAL_UPDATED = "goal.updated"
    GOAL_COMPLETED = "goal.completed"
    GOAL_ARCHIVED = "goal.archived"
    GOAL_DELETED = "goal.deleted"

    # Objective events
    OBJECTIVE_CREATED = "objective.created"
    OBJECTIVE_UPDATED = "objective.updated"
    OBJECTIVE_COMPLETED = "objective.completed"
    OBJECTIVE_ARCHIVED = "objective.archived"
    OBJECTIVE_DELETED = "objective.deleted"

    # Key result events
    KEY_RESULT_CREATED = "key_result.created"
    KEY_RESULT_UPDATED = "key_result.updated"
    KEY_RESULT_COMPLETED = "key_result.completed"
    KEY_RESULT_ARCHIVED = "key_result.archived"
    KEY_RESULT_DELETED = "key_result.deleted"

    # Plan events
    PLAN_CREATED = "plan.created"
    PLAN_UPDATED = "plan.updated"
    PLAN_ARCHIVED = "plan.archived"
    PLAN_DELETED = "plan.deleted"

    # Organization events
    ORGANIZATION_CREATED = "organization.created"
    ORGANIZATION_UPDATED = "organization.updated"
    ORGANIZATION_ARCHIVED = "organization.archived"
    ORGANIZATION_DELETED = "organization.deleted"

    # Team events
    TEAM_CREATED = "team.created"
    TEAM_UPDATED = "team.updated"
    TEAM_ARCHIVED = "team.archived"
    TEAM_DELETED = "team.deleted"

    # Portfolio events
    PORTFOLIO_CREATED = "portfolio.created"
    PORTFOLIO_UPDATED = "portfolio.updated"
    PORTFOLIO_ARCHIVED = "portfolio.archived"
    PORTFOLIO_DELETED = "portfolio.deleted"

    # Program events
    PROGRAM_CREATED = "program.created"
    PROGRAM_UPDATED = "program.updated"
    PROGRAM_ARCHIVED = "program.archived"
    PROGRAM_DELETED = "program.deleted"

    # Task events
    TASK_CREATED = "task.created"
    TASK_UPDATED = "task.updated"
    TASK_STATUS_CHANGED = "task.status_changed"
    TASK_ASSIGNED = "task.assigned"
    TASK_COMPLETED = "task.completed"
    TASK_BLOCKED = "task.blocked"
    TASK_UNBLOCKED = "task.unblocked"
    TASK_PROGRESS_UPDATED = "task.progress_updated"
    TASK_DELETED = "task.deleted"

    # Task checkout events
    TASK_CHECKED_OUT = "task.checked_out"
    TASK_CHECKOUT_RENEWED = "task.checkout_renewed"
    TASK_CHECKOUT_RELEASED = "task.checkout_released"
    TASK_CHECKOUT_EXPIRED = "task.checkout_expired"
    TASK_CHECKOUT_CONFLICT = "task.checkout_conflict"

    # Label events
    LABEL_CATEGORY_CREATED = "label_category.created"
    LABEL_CATEGORY_UPDATED = "label_category.updated"
    LABEL_CATEGORY_DELETED = "label_category.deleted"
    LABEL_CATEGORY_RESTORED = "label_category.restored"
    LABEL_CREATED = "label.created"
    LABEL_UPDATED = "label.updated"
    LABEL_DELETED = "label.deleted"
    LABEL_RESTORED = "label.restored"
    LABEL_ASSIGNMENT_CREATED = "label_assignment.created"
    LABEL_ASSIGNMENT_DELETED = "label_assignment.deleted"
    LABEL_ASSIGNMENT_RESTORED = "label_assignment.restored"
    LABEL_GATE_RULE_CREATED = "label_gate_rule.created"
    LABEL_GATE_RULE_UPDATED = "label_gate_rule.updated"
    LABEL_GATE_RULE_DELETED = "label_gate_rule.deleted"
    LABEL_GATE_RULE_RESTORED = "label_gate_rule.restored"

    # Custom field events
    CUSTOM_FIELD_CREATED = "custom_field.created"
    CUSTOM_FIELD_UPDATED = "custom_field.updated"
    CUSTOM_FIELD_DELETED = "custom_field.deleted"
    CUSTOM_FIELD_RESTORED = "custom_field.restored"
    CUSTOM_FIELD_VALUE_SET = "custom_field.value_set"

    # Comment and watcher events
    COMMENT_CREATED = "comment.created"
    COMMENT_DELETED = "comment.deleted"
    COMMENT_RESTORED = "comment.restored"
    WATCHER_ADDED = "watcher.added"
    WATCHER_REMOVED = "watcher.removed"
    WATCHER_RESTORED = "watcher.restored"

    # Automation rule events
    AUTOMATION_RULE_CREATED = "automation_rule.created"
    AUTOMATION_RULE_UPDATED = "automation_rule.updated"
    AUTOMATION_RULE_DELETED = "automation_rule.deleted"
    AUTOMATION_RULE_RESTORED = "automation_rule.restored"

    # Evidence gate events
    EVIDENCE_GATE_RULE_CREATED = "evidence_gate_rule.created"
    EVIDENCE_GATE_RULE_UPDATED = "evidence_gate_rule.updated"
    EVIDENCE_GATE_RULE_DELETED = "evidence_gate_rule.deleted"
    EVIDENCE_GATE_RULE_RESTORED = "evidence_gate_rule.restored"

    # Saved search events
    SAVED_SEARCH_CREATED = "saved_search.created"
    SAVED_SEARCH_UPDATED = "saved_search.updated"
    SAVED_SEARCH_DELETED = "saved_search.deleted"
    SAVED_SEARCH_RESTORED = "saved_search.restored"

    # Plan test job events
    PLAN_TEST_JOB_CREATED = "plan_test_job.created"
    PLAN_TEST_JOB_UPDATED = "plan_test_job.updated"
    PLAN_TEST_JOB_DELETED = "plan_test_job.deleted"
    PLAN_TEST_JOB_RESTORED = "plan_test_job.restored"

    # API key events
    API_KEY_CREATED = "api_key.created"
    API_KEY_UPDATED = "api_key.updated"
    API_KEY_DEACTIVATED = "api_key.deactivated"
    API_KEY_DELETED = "api_key.deleted"
    API_KEY_RESTORED = "api_key.restored"

    # Milestone events
    MILESTONE_CREATED = "milestone.created"
    MILESTONE_UPDATED = "milestone.updated"
    MILESTONE_STATUS_CHANGED = "milestone.status_changed"
    MILESTONE_COMPLETED = "milestone.completed"
    MILESTONE_DELETED = "milestone.deleted"

    # Dependency events
    DEPENDENCY_ADDED = "dependency.added"
    DEPENDENCY_REMOVED = "dependency.removed"

    # Remote host events
    REMOTE_HOST_ADDED = "remote_host.added"
    REMOTE_HOST_UPDATED = "remote_host.updated"
    REMOTE_HOST_REMOVED = "remote_host.removed"

    # Session events
    SESSION_STARTED = "session.started"
    SESSION_UPDATED = "session.updated"
    SESSION_ENDED = "session.ended"

    # Sync events
    SYNC_STARTED = "sync.started"
    SYNC_COMPLETED = "sync.completed"
    SYNC_FAILED = "sync.failed"

    # Document events
    DOCUMENT_CREATED = "document.created"
    DOCUMENT_UPDATED = "document.updated"
    DOCUMENT_DELETED = "document.deleted"

    # AWS Test Server events
    SERVER_LAUNCHING = "server.launching"
    SERVER_LAUNCHED = "server.launched"
    SERVER_RUNNING = "server.running"
    SERVER_STOPPING = "server.stopping"
    SERVER_TERMINATED = "server.terminated"
    SERVER_INTERRUPTED = "server.interrupted"
    SERVER_ACTIVITY = "server.activity"
    SERVER_COST_RECORDED = "server.cost_recorded"

    # AWS Test Run events
    TEST_RUN_STARTED = "test_run.started"
    TEST_RUN_COMPLETED = "test_run.completed"
    TEST_RUN_FAILED = "test_run.failed"
    TEST_RUN_UPDATED = "test_run.updated"

    # Test run retention policy events
    TEST_RUN_RETENTION_POLICY_CREATED = "test_run_retention_policy.created"
    TEST_RUN_RETENTION_POLICY_UPDATED = "test_run_retention_policy.updated"
    TEST_RUN_RETENTION_POLICY_DELETED = "test_run_retention_policy.deleted"
    TEST_RUN_RETENTION_POLICY_RESTORED = "test_run_retention_policy.restored"

    # Network Environment events
    NETWORK_ENV_CREATING = "network_env.creating"
    NETWORK_ENV_READY = "network_env.ready"
    NETWORK_ENV_DESTROYED = "network_env.destroyed"


@dataclass(frozen=True)
class EventMetadata:
    """Metadata attached to every event."""

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    source: str = "pms"  # Component that generated the event
    correlation_id: str | None = None  # Links related events
    causation_id: str | None = None  # Event that caused this one
    user_id: str | None = None  # User who triggered the event
    session_id: str | None = None  # Session context

    def to_dict(self) -> dict[str, str | None]:
        """Serialize metadata to dictionary."""
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, str | None]) -> EventMetadata:
        """Deserialize metadata from dictionary."""
        timestamp_str = data.get("timestamp")
        return cls(
            event_id=data.get("event_id") or str(uuid.uuid4()),
            timestamp=datetime.fromisoformat(timestamp_str)
            if timestamp_str
            else datetime.now(UTC),
            source=data.get("source") or "pms",
            correlation_id=data.get("correlation_id"),
            causation_id=data.get("causation_id"),
            user_id=data.get("user_id"),
            session_id=data.get("session_id"),
        )


T = TypeVar("T")


@dataclass(frozen=True)
class DomainEvent[T]:
    """
    Base domain event with typed payload.

    Events are immutable, append-only records of state changes.
    The current state is computed by replaying events in order.
    """

    event_type: EventType
    aggregate_type: str  # e.g., "project", "task", "milestone"
    aggregate_id: str  # ID of the entity this event affects
    payload: T  # Type-safe event data
    metadata: EventMetadata = field(default_factory=EventMetadata)
    sequence_number: int = 0  # Order within aggregate stream

    def to_dict(self) -> dict[str, Any]:
        """Serialize event for storage."""
        return {
            "event_type": self.event_type.value,
            "aggregate_type": self.aggregate_type,
            "aggregate_id": self.aggregate_id,
            "payload": self.payload
            if isinstance(self.payload, dict)
            else self._serialize_payload(),
            "metadata": self.metadata.to_dict(),
            "sequence_number": self.sequence_number,
        }

    def _serialize_payload(self) -> dict[str, Any]:
        """Serialize dataclass payload to dict."""
        if is_dataclass(self.payload):
            serialized = {str(key): value for key, value in vars(self.payload).items()}
            return serialized
        return {"value": self.payload}


# Specific event payload types
@dataclass(frozen=True)
class ProjectCreatedPayload:
    """Payload for PROJECT_CREATED event."""

    name: str
    description: str | None = None
    tags: tuple[str, ...] = ()
    org_id: str | None = None
    portfolio_id: str | None = None
    program_id: str | None = None
    product_id: str | None = None


@dataclass(frozen=True)
class ProjectUpdatedPayload:
    """Payload for PROJECT_UPDATED event."""

    changes: dict[str, tuple[Any, Any]]  # field -> (old_value, new_value)


@dataclass(frozen=True)
class GoalCreatedPayload:
    """Payload for GOAL_CREATED event."""

    name: str
    description: str | None = None
    horizon: str = "short_term"
    target_date: str | None = None
    owner: str | None = None
    product_id: str | None = None
    project_id: str | None = None
    tags: tuple[str, ...] = ()
    progress_percent: int = 0


@dataclass(frozen=True)
class GoalUpdatedPayload:
    """Payload for GOAL_UPDATED event."""

    changes: dict[str, tuple[Any, Any]]  # field -> (old_value, new_value)


@dataclass(frozen=True)
class ObjectiveCreatedPayload:
    """Payload for OBJECTIVE_CREATED event."""

    goal_id: str
    name: str
    description: str | None = None
    target_date: str | None = None
    owner: str | None = None
    tags: tuple[str, ...] = ()
    progress_percent: int = 0


@dataclass(frozen=True)
class ObjectiveUpdatedPayload:
    """Payload for OBJECTIVE_UPDATED event."""

    changes: dict[str, tuple[Any, Any]]  # field -> (old_value, new_value)


@dataclass(frozen=True)
class KeyResultCreatedPayload:
    """Payload for KEY_RESULT_CREATED event."""

    objective_id: str
    name: str
    description: str | None = None
    current_value: float | None = None
    target_value: float | None = None
    unit: str | None = None
    owner: str | None = None
    tags: tuple[str, ...] = ()
    progress_percent: int = 0


@dataclass(frozen=True)
class KeyResultUpdatedPayload:
    """Payload for KEY_RESULT_UPDATED event."""

    changes: dict[str, tuple[Any, Any]]  # field -> (old_value, new_value)


@dataclass(frozen=True)
class PlanCreatedPayload:
    """Payload for PLAN_CREATED event."""

    name: str
    description: str | None = None
    status: str = "draft"
    format: str = "json"
    content: str = ""
    product_id: str | None = None
    project_id: str | None = None
    goal_id: str | None = None
    objective_id: str | None = None
    task_ids: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlanUpdatedPayload:
    """Payload for PLAN_UPDATED event."""

    changes: dict[str, tuple[Any, Any]]  # field -> (old_value, new_value)


@dataclass(frozen=True)
class TaskCreatedPayload:
    """Payload for TASK_CREATED event."""

    project_id: str
    title: str
    description: str | None = None
    milestone_id: str | None = None
    parent_id: str | None = None
    priority: str = "medium"
    complexity_points: int | None = None
    due_date: str | None = None
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class TaskStatusChangedPayload:
    """Payload for TASK_STATUS_CHANGED event."""

    old_status: str
    new_status: str
    reason: str | None = None


@dataclass(frozen=True)
class TaskCompletedPayload:
    """Payload for TASK_COMPLETED event."""

    notes: str | None = None
    completion_notes: str | None = None  # Deprecated, use notes


@dataclass(frozen=True)
class DependencyPayload:
    """Payload for dependency events."""

    task_id: str
    depends_on_id: str
    dependency_type: str = "blocks"  # blocks, relates_to, etc.


# AWS Event Payloads


@dataclass(frozen=True)
class ServerLaunchingPayload:
    """Payload for SERVER_LAUNCHING event."""

    name: str
    instance_type: str
    region: str
    availability_zone: str
    config_json: str  # Serialized SpotServerConfig


@dataclass(frozen=True)
class ServerLaunchedPayload:
    """Payload for SERVER_LAUNCHED event."""

    instance_id: str
    public_ip: str | None
    private_ip: str | None
    hourly_price: str  # Decimal as string


@dataclass(frozen=True)
class ServerTerminatedPayload:
    """Payload for SERVER_TERMINATED event."""

    reason: str
    total_runtime_hours: float
    total_cost: str  # Decimal as string


@dataclass(frozen=True)
class ServerInterruptedPayload:
    """Payload for SERVER_INTERRUPTED event."""

    instance_id: str
    warning_time: str  # ISO timestamp


@dataclass(frozen=True)
class ServerCostRecordedPayload:
    """Payload for SERVER_COST_RECORDED event."""

    hours: float
    cost_usd: str  # Decimal as string
    instance_type: str


@dataclass(frozen=True)
class TestRunStartedPayload:
    """Payload for TEST_RUN_STARTED event."""

    server_id: str
    command: str
    project_path: str


@dataclass(frozen=True)
class TestRunCompletedPayload:
    """Payload for TEST_RUN_COMPLETED event."""

    server_id: str
    success: bool
    exit_code: int
    duration_seconds: float
    stdout_preview: str  # First N chars
    stderr_preview: str


class EventStore:
    """
    Append-only event store with streaming and replay capabilities.

    Events are never modified or deleted - only appended.
    State is computed by replaying events.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    @staticmethod
    def _is_event_sequence_conflict(exc: DatabaseError) -> bool:
        message = str(exc).lower()
        return (
            "unique constraint failed" in message
            and "events.aggregate_type" in message
            and "events.aggregate_id" in message
            and "events.sequence_number" in message
        )

    async def append(self, event: DomainEvent[Any]) -> DomainEvent[Any]:
        """
        Append an event to the store.

        Returns the event with its assigned sequence number.
        """
        max_attempts = 3
        for attempt in range(max_attempts):
            sequenced_event = await self._build_sequenced_event(event)
            try:
                await self.db.execute(
                    """
                    INSERT INTO events (
                        event_id, event_type, aggregate_type, aggregate_id,
                        payload, metadata, sequence_number, timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sequenced_event.metadata.event_id,
                        sequenced_event.event_type.value,
                        sequenced_event.aggregate_type,
                        sequenced_event.aggregate_id,
                        json.dumps(sequenced_event.to_dict()["payload"]),
                        json.dumps(sequenced_event.metadata.to_dict()),
                        sequenced_event.sequence_number,
                        sequenced_event.metadata.timestamp.isoformat(),
                    ),
                )
                return sequenced_event
            except DatabaseError as exc:
                if (
                    not self._is_event_sequence_conflict(exc)
                    or attempt + 1 >= max_attempts
                ):
                    raise

        raise RuntimeError("Event append retry loop exhausted unexpectedly")

    async def _build_sequenced_event(self, event: DomainEvent[Any]) -> DomainEvent[Any]:
        """Assign the next aggregate sequence number to an event."""
        result = await self.db.fetch_one(
            """
            SELECT COALESCE(MAX(sequence_number), 0) + 1 as next_seq
            FROM events
            WHERE aggregate_type = ? AND aggregate_id = ?
            """,
            (event.aggregate_type, event.aggregate_id),
        )
        next_seq = result["next_seq"] if result else 1
        return DomainEvent(
            event_type=event.event_type,
            aggregate_type=event.aggregate_type,
            aggregate_id=event.aggregate_id,
            payload=event.payload,
            metadata=event.metadata,
            sequence_number=next_seq,
        )

    async def get_events(
        self,
        aggregate_type: str,
        aggregate_id: str,
        from_sequence: int = 0,
        to_sequence: int | None = None,
    ) -> list[DomainEvent[Any]]:
        """Get events for an aggregate, optionally within a sequence range."""
        query = """
            SELECT event_id, event_type, aggregate_type, aggregate_id,
                   payload, metadata, sequence_number
            FROM events
            WHERE aggregate_type = ? AND aggregate_id = ?
            AND sequence_number > ?
        """
        params: list[Any] = [aggregate_type, aggregate_id, from_sequence]

        if to_sequence is not None:
            query += " AND sequence_number <= ?"
            params.append(to_sequence)

        query += " ORDER BY sequence_number ASC"

        rows = await self.db.fetch_all(query, tuple(params))
        return [self._row_to_event(row) for row in rows]

    async def get_event_by_id(self, event_id: str) -> DomainEvent[Any] | None:
        """Get a single event by its ID."""
        row = await self.db.fetch_one(
            """
            SELECT event_id, event_type, aggregate_type, aggregate_id,
                   payload, metadata, sequence_number
            FROM events
            WHERE event_id = ?
            """,
            (event_id,),
        )
        return self._row_to_event(row) if row else None

    async def get_all_events(
        self,
        event_types: list[EventType] | None = None,
        since: datetime | None = None,
        limit: int = 1000,
    ) -> list[DomainEvent[Any]]:
        """Get events across all aggregates with optional filtering."""
        query = "SELECT * FROM events WHERE 1=1"
        params: list[Any] = []

        if event_types:
            placeholders = ",".join("?" * len(event_types))
            query += f" AND event_type IN ({placeholders})"
            params.extend(et.value for et in event_types)

        if since:
            query += " AND timestamp > ?"
            params.append(since.isoformat())

        query += " ORDER BY timestamp ASC LIMIT ?"
        params.append(limit)

        rows = await self.db.fetch_all(query, tuple(params))
        return [self._row_to_event(row) for row in rows]

    async def get_aggregate_ids(self, aggregate_type: str) -> list[str]:
        """Get all aggregate IDs of a given type."""
        rows = await self.db.fetch_all(
            "SELECT DISTINCT aggregate_id FROM events WHERE aggregate_type = ?",
            (aggregate_type,),
        )
        return [row["aggregate_id"] for row in rows]

    def _row_to_event(self, row: dict[str, Any]) -> DomainEvent[Any]:
        """Convert database row to DomainEvent."""
        return DomainEvent(
            event_type=EventType(row["event_type"]),
            aggregate_type=row["aggregate_type"],
            aggregate_id=row["aggregate_id"],
            payload=json.loads(row["payload"]),
            metadata=EventMetadata.from_dict(json.loads(row["metadata"])),
            sequence_number=row["sequence_number"],
        )
