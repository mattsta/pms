"""Trigger System - Event-driven workflow initiation.

Triggers start workflows based on events:
- Event triggers: React to system events
- Schedule triggers: Cron-based scheduling
- Webhook triggers: External HTTP requests
- File triggers: File system changes

Usage:
    from pms.automation import Trigger, TriggerManager, TriggerType

    # Event-based trigger
    trigger = Trigger(
        name="on_task_complete",
        type=TriggerType.EVENT,
        event_pattern="task.completed",
        workflow_name="notify_team",
    )

    manager = TriggerManager(workflow_engine)
    manager.register(trigger)
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pms.automation.events import (
    Event,
    EventBus,
    EventPattern,
    EventType,
    get_event_bus,
)
from pms.automation.workflows import Workflow, WorkflowContext, WorkflowEngine

logger = logging.getLogger(__name__)


# =============================================================================
# Trigger Types
# =============================================================================


class TriggerType(Enum):
    """Types of triggers."""

    EVENT = "event"  # React to system events
    SCHEDULE = "schedule"  # Cron-based scheduling
    WEBHOOK = "webhook"  # External HTTP requests
    MANUAL = "manual"  # Explicit invocation
    FILE = "file"  # File system changes
    STARTUP = "startup"  # Run on system start


class TriggerStatus(Enum):
    """Status of a trigger."""

    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"
    ERROR = "error"


# =============================================================================
# Trigger Definition
# =============================================================================


@dataclass
class Trigger:
    """A trigger definition.

    Attributes:
        name: Unique trigger name
        type: Trigger type
        workflow_name: Workflow to execute
        event_pattern: For EVENT type, pattern to match
        schedule: For SCHEDULE type, cron expression
        webhook_path: For WEBHOOK type, URL path
        inputs: Static inputs to pass to workflow
        input_mapping: Map event data to workflow inputs
        condition: Additional condition to check
        enabled: Whether trigger is active
        max_concurrent: Maximum concurrent workflow runs
        cooldown_seconds: Minimum time between triggers
    """

    name: str
    type: TriggerType
    workflow_name: str
    event_pattern: str | None = None
    schedule: str | None = None  # Cron expression
    webhook_path: str | None = None
    inputs: dict[str, Any] = field(default_factory=dict)
    input_mapping: dict[str, str] = field(
        default_factory=dict
    )  # workflow_input -> event_data_path
    condition: str | None = None
    enabled: bool = True
    max_concurrent: int = 1
    cooldown_seconds: float = 0
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tags: list[str] = field(default_factory=list)

    def matches_event(self, event: Event) -> bool:
        """Check if trigger matches an event."""
        if self.type != TriggerType.EVENT:
            return False

        if not self.event_pattern:
            return False

        # Create pattern and match
        pattern = EventPattern(type_pattern=self.event_pattern)
        return pattern.matches(event)

    def extract_inputs(self, event: Event) -> dict[str, Any]:
        """Extract workflow inputs from event data.

        Uses input_mapping to map event data paths to input names.
        """
        inputs = dict(self.inputs)  # Start with static inputs

        for input_name, data_path in self.input_mapping.items():
            value = self._get_nested(event.data, data_path)
            if value is not None:
                inputs[input_name] = value

        return inputs

    def _get_nested(self, data: dict[str, Any], path: str) -> Any:
        """Get nested value from dict using dot notation."""
        parts = path.split(".")
        current = data

        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None

        return current


@dataclass
class TriggerExecution:
    """Record of a trigger execution."""

    trigger_id: str
    trigger_name: str
    workflow_id: str
    started_at: datetime
    event: Event | None = None
    status: str = "running"
    error: str | None = None


# =============================================================================
# Trigger Manager
# =============================================================================


class TriggerManager:
    """Manages triggers and their execution.

    Features:
    - Register/unregister triggers
    - Event-based trigger matching
    - Cooldown and concurrency control
    - Execution history
    """

    def __init__(
        self,
        workflow_engine: WorkflowEngine,
        event_bus: EventBus | None = None,
    ):
        """Initialize trigger manager.

        Args:
            workflow_engine: Engine to execute workflows
            event_bus: Event bus to subscribe to
        """
        self.workflow_engine = workflow_engine
        self.event_bus = event_bus or get_event_bus()
        self._triggers: dict[str, Trigger] = {}
        self._workflows: dict[str, Workflow] = {}
        self._executions: list[TriggerExecution] = []
        self._last_fired: dict[str, datetime] = {}
        self._active_count: dict[str, int] = {}
        self._subscription_id: str | None = None

    def register_workflow(self, workflow: Workflow) -> None:
        """Register a workflow that can be triggered.

        Args:
            workflow: Workflow definition
        """
        self._workflows[workflow.name] = workflow
        logger.info(f"Registered workflow: {workflow.name}")

    def register(self, trigger: Trigger) -> str:
        """Register a trigger.

        Args:
            trigger: Trigger definition

        Returns:
            Trigger ID
        """
        self._triggers[trigger.id] = trigger
        self._active_count[trigger.id] = 0
        logger.info(f"Registered trigger: {trigger.name} ({trigger.type.value})")
        return trigger.id

    def unregister(self, trigger_id: str) -> bool:
        """Unregister a trigger.

        Args:
            trigger_id: ID of trigger to remove

        Returns:
            True if found and removed
        """
        if trigger_id in self._triggers:
            del self._triggers[trigger_id]
            self._active_count.pop(trigger_id, None)
            return True
        return False

    def get_trigger(self, trigger_id: str) -> Trigger | None:
        """Get a trigger by ID."""
        return self._triggers.get(trigger_id)

    def list_triggers(self, type_filter: TriggerType | None = None) -> list[Trigger]:
        """List all triggers.

        Args:
            type_filter: Optional filter by type

        Returns:
            List of triggers
        """
        triggers = list(self._triggers.values())
        if type_filter:
            triggers = [t for t in triggers if t.type == type_filter]
        return triggers

    async def start(self) -> None:
        """Start listening for events."""
        # Subscribe to all events for event-based triggers
        self._subscription_id = self.event_bus.subscribe(
            EventPattern(),  # Match all events
            self._handle_event,
        )
        logger.info("Trigger manager started")

        # Fire startup triggers
        startup_triggers = [
            t
            for t in self._triggers.values()
            if t.type == TriggerType.STARTUP and t.enabled
        ]
        for trigger in startup_triggers:
            await self._fire_trigger(trigger, None)

    async def stop(self) -> None:
        """Stop listening for events."""
        if self._subscription_id:
            self.event_bus.unsubscribe(self._subscription_id)
            self._subscription_id = None
        logger.info("Trigger manager stopped")

    async def _handle_event(self, event: Event) -> None:
        """Handle incoming event and fire matching triggers."""
        for trigger in self._triggers.values():
            if not trigger.enabled:
                continue

            if trigger.matches_event(event):
                # Check cooldown
                if not self._check_cooldown(trigger):
                    logger.debug(f"Trigger {trigger.name} in cooldown")
                    continue

                # Check concurrency
                if not self._check_concurrency(trigger):
                    logger.debug(f"Trigger {trigger.name} at max concurrency")
                    continue

                # Fire trigger
                await self._fire_trigger(trigger, event)

    def _check_cooldown(self, trigger: Trigger) -> bool:
        """Check if trigger is past cooldown period."""
        if trigger.cooldown_seconds <= 0:
            return True

        last = self._last_fired.get(trigger.id)
        if not last:
            return True

        elapsed = (datetime.now(UTC) - last).total_seconds()
        return elapsed >= trigger.cooldown_seconds

    def _check_concurrency(self, trigger: Trigger) -> bool:
        """Check if trigger is below max concurrency."""
        current = self._active_count.get(trigger.id, 0)
        return current < trigger.max_concurrent

    async def _fire_trigger(self, trigger: Trigger, event: Event | None) -> None:
        """Fire a trigger and execute its workflow."""
        # Get workflow
        workflow = self._workflows.get(trigger.workflow_name)
        if not workflow:
            logger.error(f"Workflow not found: {trigger.workflow_name}")
            return

        # Extract inputs
        inputs = trigger.extract_inputs(event) if event else dict(trigger.inputs)

        # Check condition
        if trigger.condition:
            # Simple condition check (could be enhanced)
            # For now, just check if condition references are truthy
            pass

        # Track execution
        self._last_fired[trigger.id] = datetime.now(UTC)
        self._active_count[trigger.id] = self._active_count.get(trigger.id, 0) + 1

        execution = TriggerExecution(
            trigger_id=trigger.id,
            trigger_name=trigger.name,
            workflow_id="",
            started_at=datetime.now(UTC),
            event=event,
        )
        self._executions.append(execution)

        logger.info(
            f"Firing trigger: {trigger.name} -> workflow: {trigger.workflow_name}"
        )

        try:
            # Create context with correlation ID
            context = WorkflowContext(
                inputs=inputs,
                correlation_id=event.correlation_id if event else None,
            )
            execution.workflow_id = context.workflow_id

            # Execute workflow
            result = await self.workflow_engine.run(workflow, context=context)

            execution.status = result.status.value
            if result.error:
                execution.error = result.error

        except Exception as e:
            logger.exception(f"Trigger {trigger.name} failed: {e}")
            execution.status = "failed"
            execution.error = str(e)

        finally:
            self._active_count[trigger.id] -= 1

    async def fire_manual(
        self,
        trigger_name: str,
        inputs: dict[str, Any] | None = None,
    ) -> str | None:
        """Manually fire a trigger.

        Args:
            trigger_name: Name of trigger to fire
            inputs: Optional override inputs

        Returns:
            Workflow ID if fired, None if not found
        """
        trigger = next(
            (t for t in self._triggers.values() if t.name == trigger_name), None
        )
        if not trigger:
            return None

        # Create synthetic event for manual trigger
        event = Event(
            type=EventType.CUSTOM,
            data=inputs or {},
            source="manual",
        )

        await self._fire_trigger(trigger, event)
        return self._executions[-1].workflow_id if self._executions else None

    def get_executions(
        self,
        trigger_id: str | None = None,
        limit: int = 100,
    ) -> list[TriggerExecution]:
        """Get trigger execution history.

        Args:
            trigger_id: Filter by trigger ID
            limit: Maximum executions to return

        Returns:
            List of executions (newest first)
        """
        executions = list(reversed(self._executions))

        if trigger_id:
            executions = [e for e in executions if e.trigger_id == trigger_id]

        return executions[:limit]


# =============================================================================
# Trigger Builder
# =============================================================================


class TriggerBuilder:
    """Fluent API for building triggers.

    Example:
        trigger = (
            TriggerBuilder("on_deploy")
            .on_event("task.completed")
            .workflow("notify_slack")
            .map_input("task_id", "task_id")
            .map_input("project", "project_name")
            .with_cooldown(60)
            .build()
        )
    """

    def __init__(self, name: str):
        self._name = name
        self._type = TriggerType.MANUAL
        self._workflow_name = ""
        self._event_pattern: str | None = None
        self._schedule: str | None = None
        self._inputs: dict[str, Any] = {}
        self._input_mapping: dict[str, str] = {}
        self._condition: str | None = None
        self._max_concurrent = 1
        self._cooldown = 0.0
        self._tags: list[str] = []

    def on_event(self, pattern: str) -> TriggerBuilder:
        """Set as event trigger with pattern."""
        self._type = TriggerType.EVENT
        self._event_pattern = pattern
        return self

    def on_schedule(self, cron: str) -> TriggerBuilder:
        """Set as scheduled trigger with cron expression."""
        self._type = TriggerType.SCHEDULE
        self._schedule = cron
        return self

    def on_startup(self) -> TriggerBuilder:
        """Set as startup trigger."""
        self._type = TriggerType.STARTUP
        return self

    def workflow(self, name: str) -> TriggerBuilder:
        """Set workflow to execute."""
        self._workflow_name = name
        return self

    def with_input(self, name: str, value: Any) -> TriggerBuilder:
        """Add static input."""
        self._inputs[name] = value
        return self

    def map_input(self, workflow_input: str, event_path: str) -> TriggerBuilder:
        """Map event data to workflow input."""
        self._input_mapping[workflow_input] = event_path
        return self

    def with_condition(self, condition: str) -> TriggerBuilder:
        """Add condition for trigger."""
        self._condition = condition
        return self

    def with_concurrency(self, max_concurrent: int) -> TriggerBuilder:
        """Set max concurrent executions."""
        self._max_concurrent = max_concurrent
        return self

    def with_cooldown(self, seconds: float) -> TriggerBuilder:
        """Set cooldown period."""
        self._cooldown = seconds
        return self

    def tag(self, *tags: str) -> TriggerBuilder:
        """Add tags."""
        self._tags.extend(tags)
        return self

    def build(self) -> Trigger:
        """Build the trigger."""
        if not self._workflow_name:
            raise ValueError("Workflow name is required")

        return Trigger(
            name=self._name,
            type=self._type,
            workflow_name=self._workflow_name,
            event_pattern=self._event_pattern,
            schedule=self._schedule,
            inputs=self._inputs,
            input_mapping=self._input_mapping,
            condition=self._condition,
            max_concurrent=self._max_concurrent,
            cooldown_seconds=self._cooldown,
            tags=self._tags,
        )


# =============================================================================
# Common Trigger Patterns
# =============================================================================


def on_task_completed(workflow_name: str, project: str | None = None) -> Trigger:
    """Create trigger for task completion.

    Args:
        workflow_name: Workflow to execute
        project: Optional project filter

    Returns:
        Configured trigger
    """
    builder = (
        TriggerBuilder(f"on_task_completed_{workflow_name}")
        .on_event("task.completed")
        .workflow(workflow_name)
        .map_input("task_id", "task_id")
        .map_input("project_id", "project_id")
    )

    if project:
        builder.with_input("project_filter", project)

    return builder.build()


def on_test_failed(workflow_name: str) -> Trigger:
    """Create trigger for test failures."""
    return (
        TriggerBuilder(f"on_test_failed_{workflow_name}")
        .on_event("test.run.failed")
        .workflow(workflow_name)
        .map_input("server_id", "server_id")
        .map_input("error", "error")
        .map_input("test_output", "stdout")
        .build()
    )


def on_server_ready(workflow_name: str) -> Trigger:
    """Create trigger for server ready."""
    return (
        TriggerBuilder(f"on_server_ready_{workflow_name}")
        .on_event("server.ready")
        .workflow(workflow_name)
        .map_input("server_id", "server_id")
        .map_input("server_ip", "ip_address")
        .build()
    )


def daily_at(workflow_name: str, hour: int, minute: int = 0) -> Trigger:
    """Create daily scheduled trigger."""
    return (
        TriggerBuilder(f"daily_{workflow_name}")
        .on_schedule(f"{minute} {hour} * * *")
        .workflow(workflow_name)
        .build()
    )
