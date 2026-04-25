"""Task and TaskDependency models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Self

from pms.models.base import BaseModel, generate_id, now_utc
from pms.models.enums import DependencyType, Priority, TaskStatus
from pms.models.json_types import JsonObject, ModelObject


@dataclass
class Task(BaseModel):
    """
    A task represents a unit of work within a project.

    Tasks can:
    - Belong to a milestone
    - Have subtasks (via parent_id)
    - Have dependencies on other tasks (including cross-project)
    - Track time estimates and actuals
    """

    project_id: str = ""
    milestone_id: str | None = None
    parent_id: str | None = None  # For subtasks
    title: str = ""
    description: str | None = None
    status: TaskStatus = TaskStatus.TODO
    priority: Priority = Priority.MEDIUM

    # Complexity tracking (1-100 scale)
    complexity_points: int | None = None
    actual_hours: float | None = None

    # Progressive effort tracking
    current_progress_percent: int = 0  # 0-100
    last_progress_update_at: datetime | None = None

    # Note: Progress history tracked in task_progress_updates table (immutable log)
    # Note: Open/close timestamps tracked in task_state_transitions table (immutable log)
    # Use repository methods to query transition/progress history

    # Checkout/ownership for distributed agents
    checkout_agent_session_id: str | None = None  # Agent session ID
    checkout_actor_id: str | None = None
    checked_out_at: datetime | None = None
    checkout_lease_until: datetime | None = None
    checkout_attempts: int = 0  # Number of checkout attempts
    checkout_version: int = 0  # Optimistic locking counter

    # Workflow/state machine integration
    workflow_id: str | None = None  # Assigned workflow
    current_state: str | None = None  # Current workflow state
    workflow_metadata: JsonObject = field(default_factory=dict)  # State-specific data

    due_date: datetime | None = None
    assignee: str | None = None
    assignee_id: str | None = None
    tags: tuple[str, ...] = ()
    sort_order: int = 0
    completed_at: datetime | None = None

    # Validation
    def __post_init__(self) -> None:
        """Validate task state."""
        if self.status == TaskStatus.DONE and self.completed_at is None:
            self.completed_at = now_utc()

    def start(self) -> Self:
        """Mark task as in progress.

        Note: Timestamp recorded in state_transitions table by repository.
        """
        if self.status.is_terminal:
            raise ValueError(f"Cannot start task in {self.status} status")
        self.status = TaskStatus.IN_PROGRESS
        self.updated_at = now_utc()
        return self

    def block(self, reason: str | None = None) -> Self:
        """Mark task as blocked."""
        if self.status.is_terminal:
            raise ValueError(f"Cannot block task in {self.status} status")
        self.status = TaskStatus.BLOCKED
        self.updated_at = now_utc()
        # Reason would be tracked in event
        return self

    def unblock(self) -> Self:
        """Remove blocked status."""
        if self.status != TaskStatus.BLOCKED:
            raise ValueError("Task is not blocked")
        self.status = TaskStatus.IN_PROGRESS
        self.updated_at = now_utc()
        return self

    def submit_for_review(self) -> Self:
        """Submit task for review."""
        if self.status != TaskStatus.IN_PROGRESS:
            raise ValueError("Can only submit in-progress tasks for review")
        self.status = TaskStatus.IN_REVIEW
        self.updated_at = now_utc()
        return self

    def complete(self) -> Self:
        """Mark task as completed.

        Note: Timestamp and duration recorded in state_transitions table by repository.
        """
        if self.status.is_terminal:
            raise ValueError(f"Cannot complete task in {self.status} status")
        self.status = TaskStatus.DONE
        self.completed_at = now_utc()
        self.updated_at = now_utc()
        return self

    def cancel(self) -> Self:
        """Cancel the task.

        Note: Timestamp and duration recorded in state_transitions table by repository.
        """
        if self.status == TaskStatus.DONE:
            raise ValueError("Cannot cancel completed task")
        self.status = TaskStatus.CANCELLED
        self.updated_at = now_utc()
        return self

    def reopen(self) -> Self:
        """Reopen a completed or cancelled task.

        Note: Reopen event recorded in state_transitions table by repository.
        Previous open/close cycles preserved in transition history.
        """
        if not self.status.is_terminal:
            raise ValueError("Task is not in terminal status")
        self.status = TaskStatus.TODO
        self.completed_at = None
        self.updated_at = now_utc()
        return self

    def assign(self, assignee: str, *, actor_id: str | None = None) -> Self:
        """Assign task to someone."""
        self.assignee = assignee
        self.assignee_id = actor_id
        self.updated_at = now_utc()
        return self

    def unassign(self) -> Self:
        """Remove assignment."""
        self.assignee = None
        self.assignee_id = None
        self.updated_at = now_utc()
        return self

    def set_priority(self, priority: Priority) -> Self:
        """Update task priority."""
        self.priority = priority
        self.updated_at = now_utc()
        return self

    def add_tag(self, tag: str) -> Self:
        """Add a tag to the task."""
        if tag not in self.tags:
            self.tags = (*self.tags, tag)
            self.updated_at = now_utc()
        return self

    def remove_tag(self, tag: str) -> Self:
        """Remove a tag from the task."""
        self.tags = tuple(t for t in self.tags if t != tag)
        self.updated_at = now_utc()
        return self

    @property
    def is_subtask(self) -> bool:
        """Check if this is a subtask."""
        return self.parent_id is not None

    @property
    def is_overdue(self) -> bool:
        """Check if task is overdue."""
        if self.due_date is None or self.status.is_terminal:
            return False
        return now_utc() > self.due_date

    # Progress methods
    def update_progress(self, percent: int, message: str, updated_by: str) -> Self:
        """
        Update progress (convenience method).

        Note: Full update with deltas recorded by repository.
        """
        if not 0 <= percent <= 100:
            raise ValueError(f"Progress percent must be 0-100, got {percent}")

        self.current_progress_percent = percent
        self.last_progress_update_at = now_utc()
        self.touch()

        # Auto-complete if reached 100%
        if percent >= 100 and not self.status.is_terminal:
            self.complete()

        return self

    @property
    def is_started(self) -> bool:
        """Check if any progress has been made."""
        return self.current_progress_percent > 0

    @property
    def is_nearly_complete(self) -> bool:
        """Check if task is nearly complete (>= 90%)."""
        return self.current_progress_percent >= 90

    # Checkout methods
    def checkout(
        self,
        agent_session_id: str,
        lease_seconds: int = 300,
        *,
        actor_id: str | None = None,
    ) -> Self:
        """Check out task for exclusive work."""
        from datetime import timedelta

        now = now_utc()
        self.checkout_agent_session_id = agent_session_id
        self.checkout_actor_id = actor_id
        self.checked_out_at = now
        self.checkout_lease_until = now + timedelta(seconds=lease_seconds)
        self.checkout_version += 1
        self.touch()
        return self

    def renew_checkout(
        self,
        agent_session_id: str,
        lease_seconds: int = 300,
        *,
        actor_id: str | None = None,
    ) -> Self:
        """Renew checkout lease (heartbeat)."""
        from datetime import timedelta

        if self.checkout_agent_session_id != agent_session_id:
            raise ValueError("Cannot renew: task not checked out by this agent")
        now = now_utc()
        if actor_id is not None:
            self.checkout_actor_id = actor_id
        self.checkout_lease_until = now + timedelta(seconds=lease_seconds)
        self.touch()
        return self

    def release_checkout(self, agent_session_id: str) -> Self:
        """Release checkout lock."""
        if self.checkout_agent_session_id != agent_session_id:
            raise ValueError("Cannot release: task not checked out by this agent")
        self.checkout_agent_session_id = None
        self.checkout_actor_id = None
        self.checked_out_at = None
        self.checkout_lease_until = None
        self.touch()
        return self

    @property
    def is_checked_out(self) -> bool:
        """Check if task is currently checked out (lease not expired)."""
        if self.checkout_agent_session_id is None or self.checkout_lease_until is None:
            return False
        return now_utc() < self.checkout_lease_until

    @property
    def checkout_expired(self) -> bool:
        """Check if checkout lease has expired."""
        if self.checkout_lease_until is None:
            return False
        return now_utc() >= self.checkout_lease_until

    # Workflow transition methods
    def assign_workflow(self, workflow_id: str, initial_state: str) -> Self:
        """Assign a workflow to this task."""
        self.workflow_id = workflow_id
        self.current_state = initial_state
        self.touch()
        return self

    def transition_to(
        self, new_state: str, triggered_by: str, reason: str | None = None
    ) -> Self:
        """Transition to a new workflow state (validation done by repository)."""
        self.current_state = new_state
        self.touch()
        return self

    @property
    def is_in_terminal_state(self) -> bool:
        """Check if in terminal workflow state (requires workflow context)."""
        # This would need to query the workflow definition to check if current_state is terminal
        # For now, use the simple status check
        return self.status.is_terminal

    # Note: Duration and efficiency metrics calculated from state_transitions log
    # by repository methods: get_task_duration(), get_efficiency_score()

    def to_dict(self) -> ModelObject:
        """Convert to dictionary with enum serialization."""
        data = super().to_dict()
        data["status"] = self.status.value
        data["priority"] = self.priority.value
        data["tags"] = list(self.tags)
        return data

    @classmethod
    def from_dict(cls, data: ModelObject) -> Self:
        """Create from dictionary."""
        if "status" in data and isinstance(data["status"], str):
            data["status"] = TaskStatus(data["status"])
        if "priority" in data and isinstance(data["priority"], str):
            data["priority"] = Priority(data["priority"])
        if "tags" in data and isinstance(data["tags"], list):
            data["tags"] = tuple(data["tags"])
        return super().from_dict(data)


@dataclass
class TaskDependency(BaseModel):
    """
    Represents a dependency between two tasks.

    Supports cross-project dependencies.
    """

    id: str = field(default_factory=generate_id)
    task_id: str = ""  # The task that has the dependency
    depends_on_id: str = ""  # The task it depends on
    dependency_type: DependencyType = DependencyType.BLOCKS

    def to_dict(self) -> ModelObject:
        """Convert to dictionary."""
        data = super().to_dict()
        data["dependency_type"] = self.dependency_type.value
        return data

    @classmethod
    def from_dict(cls, data: ModelObject) -> Self:
        """Create from dictionary."""
        if "dependency_type" in data and isinstance(data["dependency_type"], str):
            data["dependency_type"] = DependencyType(data["dependency_type"])
        return super().from_dict(data)


@dataclass
class DuplicateTaskGroup:
    """Group of tasks that share the same normalized title."""

    normalized_title: str
    tasks: list[Task] = field(default_factory=list)
    suggested_primary_id: str | None = None
    suggested_primary_reason: str | None = None

    @property
    def count(self) -> int:
        """Number of tasks in the group."""
        return len(self.tasks)


@dataclass
class TaskWithContext:
    """Task with additional context for display."""

    task: Task
    subtasks: list[Task] = field(default_factory=list)
    dependencies: list[TaskDependency] = field(default_factory=list)
    dependents: list[TaskDependency] = field(
        default_factory=list
    )  # Tasks depending on this
    project_name: str = ""
    milestone_name: str | None = None
    parent_title: str | None = None

    @property
    def blocking_count(self) -> int:
        """Number of tasks this task is blocking."""
        return len(self.dependents)

    @property
    def blocked_by_count(self) -> int:
        """Number of tasks blocking this task."""
        return len(self.dependencies)
