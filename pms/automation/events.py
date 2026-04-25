"""Event Bus - Pub/sub messaging system for PMS automation.

The Event Bus enables decoupled communication between components:
- Tools can emit events when actions complete
- Workflows can subscribe to events
- Triggers can fire based on event patterns

Usage:
    from pms.automation import EventBus, Event, EventType

    bus = EventBus()

    # Subscribe to events
    @bus.on(EventType.TASK_COMPLETED)
    async def on_task_done(event: Event):
        print(f"Task {event.data['task_id']} completed!")

    # Emit events
    await bus.emit(Event(
        type=EventType.TASK_COMPLETED,
        data={"task_id": "123", "project": "myproject"}
    ))
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Event Types
# =============================================================================


class EventType(Enum):
    """Types of events in the PMS system."""

    # Lifecycle events
    SYSTEM_STARTED = "system.started"
    SYSTEM_STOPPED = "system.stopped"

    # Project events
    PROJECT_CREATED = "project.created"
    PROJECT_UPDATED = "project.updated"
    PROJECT_ARCHIVED = "project.archived"
    PROJECT_COMPLETED = "project.completed"

    # Task events
    TASK_CREATED = "task.created"
    TASK_STARTED = "task.started"
    TASK_COMPLETED = "task.completed"
    TASK_BLOCKED = "task.blocked"
    TASK_UNBLOCKED = "task.unblocked"
    TASK_CANCELLED = "task.cancelled"

    # Remote events
    REMOTE_COMMAND_STARTED = "remote.command.started"
    REMOTE_COMMAND_COMPLETED = "remote.command.completed"
    REMOTE_COMMAND_FAILED = "remote.command.failed"
    SYNC_STARTED = "sync.started"
    SYNC_COMPLETED = "sync.completed"
    SYNC_FAILED = "sync.failed"

    # AWS events
    SERVER_LAUNCHED = "server.launched"
    SERVER_READY = "server.ready"
    SERVER_TERMINATED = "server.terminated"
    TEST_RUN_STARTED = "test.run.started"
    TEST_RUN_COMPLETED = "test.run.completed"
    TEST_RUN_FAILED = "test.run.failed"

    # Workflow events
    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_STEP_STARTED = "workflow.step.started"
    WORKFLOW_STEP_COMPLETED = "workflow.step.completed"
    WORKFLOW_STEP_FAILED = "workflow.step.failed"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_FAILED = "workflow.failed"

    # Agent events
    AGENT_STARTED = "agent.started"
    AGENT_COMPLETED = "agent.completed"
    AGENT_FAILED = "agent.failed"
    AGENT_HANDOFF = "agent.handoff"

    # Tool events
    TOOL_INVOKED = "tool.invoked"
    TOOL_COMPLETED = "tool.completed"
    TOOL_FAILED = "tool.failed"
    TOOL_GENERATED = "tool.generated"

    # Custom/user events
    CUSTOM = "custom"


# =============================================================================
# Event Data Model
# =============================================================================


@dataclass
class Event:
    """An event in the PMS system.

    Attributes:
        type: The type of event
        data: Event payload (varies by type)
        source: Component that emitted the event
        correlation_id: ID linking related events (e.g., workflow run)
        timestamp: When the event occurred
        id: Unique event identifier
    """

    type: EventType
    data: dict[str, Any] = field(default_factory=dict)
    source: str = "unknown"
    correlation_id: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def matches(self, pattern: EventPattern) -> bool:
        """Check if event matches a pattern."""
        return pattern.matches(self)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "type": self.type.value,
            "data": self.data,
            "source": self.source,
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Event:
        """Create from dictionary."""
        return cls(
            id=data["id"],
            type=EventType(data["type"]),
            data=data.get("data", {}),
            source=data.get("source", "unknown"),
            correlation_id=data.get("correlation_id"),
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )


@dataclass
class EventPattern:
    """Pattern for matching events.

    Supports:
    - Exact type match
    - Wildcard type match (e.g., "task.*")
    - Data field matching
    """

    type_pattern: str | EventType | None = None
    data_patterns: dict[str, Any] = field(default_factory=dict)
    source_pattern: str | None = None

    def matches(self, event: Event) -> bool:
        """Check if an event matches this pattern."""
        # Type matching
        if self.type_pattern is not None:
            if isinstance(self.type_pattern, EventType):
                if event.type != self.type_pattern:
                    return False
            elif isinstance(self.type_pattern, str):
                event_type_str = event.type.value
                if self.type_pattern.endswith(".*"):
                    # Wildcard match
                    prefix = self.type_pattern[:-2]
                    if not event_type_str.startswith(prefix):
                        return False
                elif event_type_str != self.type_pattern:
                    return False

        # Source matching
        if self.source_pattern is not None:
            if self.source_pattern.endswith("*"):
                if not event.source.startswith(self.source_pattern[:-1]):
                    return False
            elif event.source != self.source_pattern:
                return False

        # Data field matching
        for key, expected in self.data_patterns.items():
            if key not in event.data:
                return False
            if event.data[key] != expected:
                return False

        return True


# =============================================================================
# Event Handler
# =============================================================================


EventHandler = Callable[[Event], Coroutine[Any, Any, None]]


@dataclass
class Subscription:
    """A subscription to events."""

    id: str
    pattern: EventPattern
    handler: EventHandler
    priority: int = 0  # Higher = called first
    once: bool = False  # Unsubscribe after first match


# =============================================================================
# Event Bus
# =============================================================================


class EventBus:
    """Central event bus for PMS.

    Provides pub/sub messaging with:
    - Pattern-based subscriptions
    - Priority ordering
    - Async handlers
    - Event history
    - Dead letter queue for failed events

    Example:
        bus = EventBus()

        # Subscribe with decorator
        @bus.on(EventType.TASK_COMPLETED)
        async def handle_task(event):
            print(f"Task done: {event.data}")

        # Subscribe with pattern
        bus.subscribe(
            EventPattern(type_pattern="task.*"),
            my_handler
        )

        # Emit event
        await bus.emit(Event(
            type=EventType.TASK_COMPLETED,
            data={"task_id": "123"}
        ))
    """

    def __init__(
        self,
        history_size: int = 1000,
        enable_dead_letter: bool = True,
    ):
        """Initialize event bus.

        Args:
            history_size: Number of events to keep in history
            enable_dead_letter: Whether to store failed events
        """
        self._subscriptions: list[Subscription] = []
        self._history: list[Event] = []
        self._history_size = history_size
        self._dead_letter: list[tuple[Event, Exception]] = []
        self._enable_dead_letter = enable_dead_letter
        self._lock = asyncio.Lock()

        # Stats
        self._stats = {
            "events_emitted": 0,
            "events_delivered": 0,
            "events_failed": 0,
        }

    def on(
        self,
        event_type: EventType | str,
        priority: int = 0,
        once: bool = False,
    ) -> Callable[[EventHandler], EventHandler]:
        """Decorator to subscribe to events.

        Args:
            event_type: Event type or pattern string
            priority: Handler priority (higher = called first)
            once: Unsubscribe after first match

        Example:
            @bus.on(EventType.TASK_COMPLETED)
            async def handle_task(event):
                print(event.data)

            @bus.on("task.*")
            async def handle_all_tasks(event):
                print(f"Task event: {event.type}")
        """

        def decorator(handler: EventHandler) -> EventHandler:
            if isinstance(event_type, EventType):
                pattern = EventPattern(type_pattern=event_type)
            else:
                pattern = EventPattern(type_pattern=event_type)

            self.subscribe(pattern, handler, priority=priority, once=once)
            return handler

        return decorator

    def subscribe(
        self,
        pattern: EventPattern,
        handler: EventHandler,
        priority: int = 0,
        once: bool = False,
    ) -> str:
        """Subscribe to events matching a pattern.

        Args:
            pattern: Event pattern to match
            handler: Async function to call
            priority: Handler priority
            once: Unsubscribe after first match

        Returns:
            Subscription ID
        """
        sub_id = str(uuid.uuid4())
        subscription = Subscription(
            id=sub_id,
            pattern=pattern,
            handler=handler,
            priority=priority,
            once=once,
        )

        # Insert in priority order
        inserted = False
        for i, existing in enumerate(self._subscriptions):
            if subscription.priority > existing.priority:
                self._subscriptions.insert(i, subscription)
                inserted = True
                break

        if not inserted:
            self._subscriptions.append(subscription)

        logger.debug(f"Subscribed {sub_id} to pattern {pattern}")
        return sub_id

    def unsubscribe(self, subscription_id: str) -> bool:
        """Unsubscribe by ID.

        Args:
            subscription_id: ID returned from subscribe()

        Returns:
            True if found and removed
        """
        for i, sub in enumerate(self._subscriptions):
            if sub.id == subscription_id:
                self._subscriptions.pop(i)
                logger.debug(f"Unsubscribed {subscription_id}")
                return True
        return False

    async def emit(self, event: Event) -> int:
        """Emit an event to all matching subscribers.

        Args:
            event: Event to emit

        Returns:
            Number of handlers that processed the event
        """
        async with self._lock:
            self._stats["events_emitted"] += 1

            # Add to history
            self._history.append(event)
            if len(self._history) > self._history_size:
                self._history.pop(0)

        # Find matching subscriptions
        to_remove: list[str] = []
        handlers_called = 0

        for sub in self._subscriptions:
            if sub.pattern.matches(event):
                try:
                    await sub.handler(event)
                    handlers_called += 1
                    self._stats["events_delivered"] += 1

                    if sub.once:
                        to_remove.append(sub.id)

                except Exception as e:
                    logger.error(f"Handler {sub.id} failed for {event.type}: {e}")
                    self._stats["events_failed"] += 1

                    if self._enable_dead_letter:
                        self._dead_letter.append((event, e))

        # Remove one-time subscriptions
        for sub_id in to_remove:
            self.unsubscribe(sub_id)

        logger.debug(
            f"Event {event.type.value} delivered to {handlers_called} handlers"
        )
        return handlers_called

    async def emit_many(self, events: list[Event]) -> int:
        """Emit multiple events.

        Args:
            events: Events to emit

        Returns:
            Total handlers called
        """
        total = 0
        for event in events:
            total += await self.emit(event)
        return total

    def get_history(
        self,
        event_type: EventType | None = None,
        limit: int = 100,
    ) -> list[Event]:
        """Get recent events from history.

        Args:
            event_type: Filter by type (optional)
            limit: Maximum events to return

        Returns:
            List of events (newest first)
        """
        events = self._history[::-1]  # Reverse for newest first

        if event_type:
            events = [e for e in events if e.type == event_type]

        return events[:limit]

    def get_dead_letter(self) -> list[tuple[Event, Exception]]:
        """Get failed events from dead letter queue."""
        return list(self._dead_letter)

    def clear_dead_letter(self) -> int:
        """Clear dead letter queue.

        Returns:
            Number of events cleared
        """
        count = len(self._dead_letter)
        self._dead_letter.clear()
        return count

    def get_stats(self) -> dict[str, int]:
        """Get event bus statistics."""
        return {
            **self._stats,
            "subscriptions": len(self._subscriptions),
            "history_size": len(self._history),
            "dead_letter_size": len(self._dead_letter),
        }


# =============================================================================
# Global Event Bus Instance
# =============================================================================

_global_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """Get the global event bus instance."""
    global _global_bus
    if _global_bus is None:
        _global_bus = EventBus()
    return _global_bus


def set_event_bus(bus: EventBus) -> None:
    """Set the global event bus instance."""
    global _global_bus
    _global_bus = bus
