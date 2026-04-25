"""Context Management - Track and retrieve conversation context.

This module manages contextual information across conversations:
- Active project/task context
- Recent operations and decisions
- Open questions and pending items
- Session state

Usage:
    from pms.memory import ContextManager, ConversationContext

    ctx = ContextManager()

    # Set context
    ctx.set_active_project("myproject")
    ctx.add_recent_action("Created task #123")
    ctx.add_decision("Using pytest for testing", reason="Team standard")

    # Get context for agent
    summary = ctx.get_context_summary()
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Context Types
# =============================================================================


class ContextItemType(Enum):
    """Types of context items."""

    ACTION = "action"  # Something that was done
    DECISION = "decision"  # A decision that was made
    QUESTION = "question"  # An open question
    NOTE = "note"  # General note
    ERROR = "error"  # An error that occurred
    PREFERENCE = "preference"  # A stated preference


# =============================================================================
# Context Models
# =============================================================================


@dataclass
class ContextItem:
    """An item in the context history.

    Attributes:
        type: Type of context item
        content: Main content
        metadata: Additional structured data
        timestamp: When recorded
        id: Unique identifier
    """

    type: ContextItemType
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "type": self.type.value,
            "content": self.content,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContextItem:
        """Create from dictionary."""
        return cls(
            id=data["id"],
            type=ContextItemType(data["type"]),
            content=data["content"],
            metadata=data.get("metadata", {}),
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )


@dataclass
class Decision:
    """A recorded decision.

    Attributes:
        description: What was decided
        reason: Why this decision was made
        alternatives: Other options considered
        reversible: Whether this can be undone
        timestamp: When decided
    """

    description: str
    reason: str = ""
    alternatives: list[str] = field(default_factory=list)
    reversible: bool = True
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "reason": self.reason,
            "alternatives": self.alternatives,
            "reversible": self.reversible,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class ConversationContext:
    """Full context for a conversation session.

    Attributes:
        session_id: Unique session identifier
        active_project: Currently focused project
        active_task: Currently focused task
        active_files: Files currently being worked on
        recent_items: Recent context items
        decisions: Decisions made this session
        open_questions: Unanswered questions
        goals: Current goals/objectives
        constraints: Known constraints
        preferences: Stated preferences
        started_at: Session start time
    """

    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    active_project: str | None = None
    active_task: str | None = None
    active_files: list[str] = field(default_factory=list)
    recent_items: list[ContextItem] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    goals: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    preferences: dict[str, Any] = field(default_factory=dict)
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "session_id": self.session_id,
            "active_project": self.active_project,
            "active_task": self.active_task,
            "active_files": self.active_files,
            "recent_items": [i.to_dict() for i in self.recent_items],
            "decisions": [d.to_dict() for d in self.decisions],
            "open_questions": self.open_questions,
            "goals": self.goals,
            "constraints": self.constraints,
            "preferences": self.preferences,
            "started_at": self.started_at.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConversationContext:
        """Create from dictionary."""
        return cls(
            session_id=data["session_id"],
            active_project=data.get("active_project"),
            active_task=data.get("active_task"),
            active_files=data.get("active_files", []),
            recent_items=[
                ContextItem.from_dict(i) for i in data.get("recent_items", [])
            ],
            decisions=[
                Decision(
                    description=d["description"],
                    reason=d.get("reason", ""),
                    alternatives=d.get("alternatives", []),
                    reversible=d.get("reversible", True),
                    timestamp=datetime.fromisoformat(d["timestamp"]),
                )
                for d in data.get("decisions", [])
            ],
            open_questions=data.get("open_questions", []),
            goals=data.get("goals", []),
            constraints=data.get("constraints", []),
            preferences=data.get("preferences", {}),
            started_at=datetime.fromisoformat(data["started_at"]),
            metadata=data.get("metadata", {}),
        )


# =============================================================================
# Context Manager
# =============================================================================


class ContextManager:
    """Manages conversation context.

    Features:
    - Track active project/task
    - Record actions, decisions, questions
    - Generate context summaries
    - Persist across sessions
    """

    def __init__(
        self,
        storage_path: Path | str | None = None,
        max_recent_items: int = 50,
        auto_save: bool = True,
    ):
        """Initialize context manager.

        Args:
            storage_path: Path to persist context
            max_recent_items: Maximum recent items to keep
            auto_save: Whether to save after changes
        """
        self._context = ConversationContext()
        self._storage_path = Path(storage_path) if storage_path else None
        self._max_recent = max_recent_items
        self._auto_save = auto_save

        if self._storage_path and self._storage_path.exists():
            self._load()

    # -------------------------------------------------------------------------
    # Active Context
    # -------------------------------------------------------------------------

    def set_active_project(self, project_id: str | None) -> None:
        """Set the active project."""
        self._context.active_project = project_id
        if project_id:
            self._add_item(ContextItemType.ACTION, f"Switched to project: {project_id}")
        if self._auto_save:
            self._save()

    def set_active_task(self, task_id: str | None) -> None:
        """Set the active task."""
        self._context.active_task = task_id
        if task_id:
            self._add_item(ContextItemType.ACTION, f"Focusing on task: {task_id}")
        if self._auto_save:
            self._save()

    def add_active_file(self, file_path: str) -> None:
        """Add a file to active files."""
        if file_path not in self._context.active_files:
            self._context.active_files.append(file_path)
            # Keep only last 10 files
            self._context.active_files = self._context.active_files[-10:]
        if self._auto_save:
            self._save()

    def remove_active_file(self, file_path: str) -> None:
        """Remove a file from active files."""
        if file_path in self._context.active_files:
            self._context.active_files.remove(file_path)
        if self._auto_save:
            self._save()

    def get_active_project(self) -> str | None:
        """Get active project ID."""
        return self._context.active_project

    def get_active_task(self) -> str | None:
        """Get active task ID."""
        return self._context.active_task

    def get_active_files(self) -> list[str]:
        """Get list of active files."""
        return list(self._context.active_files)

    # -------------------------------------------------------------------------
    # Recording Items
    # -------------------------------------------------------------------------

    def _add_item(
        self,
        item_type: ContextItemType,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Add a context item."""
        item = ContextItem(
            type=item_type,
            content=content,
            metadata=metadata or {},
        )
        self._context.recent_items.append(item)

        # Trim to max
        if len(self._context.recent_items) > self._max_recent:
            self._context.recent_items = self._context.recent_items[-self._max_recent :]

        return item.id

    def add_action(
        self, description: str, metadata: dict[str, Any] | None = None
    ) -> str:
        """Record an action that was taken.

        Args:
            description: What was done
            metadata: Additional data

        Returns:
            Item ID
        """
        item_id = self._add_item(ContextItemType.ACTION, description, metadata)
        if self._auto_save:
            self._save()
        return item_id

    def add_decision(
        self,
        description: str,
        reason: str = "",
        alternatives: list[str] | None = None,
    ) -> None:
        """Record a decision.

        Args:
            description: What was decided
            reason: Why this decision was made
            alternatives: Other options considered
        """
        decision = Decision(
            description=description,
            reason=reason,
            alternatives=alternatives or [],
        )
        self._context.decisions.append(decision)
        self._add_item(
            ContextItemType.DECISION,
            description,
            {"reason": reason, "alternatives": alternatives or []},
        )
        if self._auto_save:
            self._save()

    def add_question(self, question: str) -> None:
        """Add an open question.

        Args:
            question: The question to track
        """
        if question not in self._context.open_questions:
            self._context.open_questions.append(question)
            self._add_item(ContextItemType.QUESTION, question)
        if self._auto_save:
            self._save()

    def resolve_question(self, question: str, answer: str = "") -> bool:
        """Mark a question as resolved.

        Args:
            question: The question to resolve
            answer: Optional answer

        Returns:
            True if question was found and removed
        """
        if question in self._context.open_questions:
            self._context.open_questions.remove(question)
            if answer:
                self._add_item(
                    ContextItemType.NOTE,
                    f"Resolved: {question}",
                    {"answer": answer},
                )
            if self._auto_save:
                self._save()
            return True
        return False

    def add_error(self, error: str, context: dict[str, Any] | None = None) -> str:
        """Record an error that occurred.

        Args:
            error: Error description
            context: Additional context

        Returns:
            Item ID
        """
        item_id = self._add_item(ContextItemType.ERROR, error, context)
        if self._auto_save:
            self._save()
        return item_id

    def add_note(self, note: str, metadata: dict[str, Any] | None = None) -> str:
        """Add a general note.

        Args:
            note: The note content
            metadata: Additional data

        Returns:
            Item ID
        """
        item_id = self._add_item(ContextItemType.NOTE, note, metadata)
        if self._auto_save:
            self._save()
        return item_id

    # -------------------------------------------------------------------------
    # Goals & Constraints
    # -------------------------------------------------------------------------

    def add_goal(self, goal: str) -> None:
        """Add a goal for the session."""
        if goal not in self._context.goals:
            self._context.goals.append(goal)
        if self._auto_save:
            self._save()

    def remove_goal(self, goal: str) -> bool:
        """Remove a goal (e.g., when completed)."""
        if goal in self._context.goals:
            self._context.goals.remove(goal)
            if self._auto_save:
                self._save()
            return True
        return False

    def add_constraint(self, constraint: str) -> None:
        """Add a constraint to consider."""
        if constraint not in self._context.constraints:
            self._context.constraints.append(constraint)
        if self._auto_save:
            self._save()

    def set_preference(self, key: str, value: Any) -> None:
        """Set a preference."""
        self._context.preferences[key] = value
        self._add_item(
            ContextItemType.PREFERENCE,
            f"Preference: {key} = {value}",
        )
        if self._auto_save:
            self._save()

    def get_preference(self, key: str, default: Any = None) -> Any:
        """Get a preference value."""
        return self._context.preferences.get(key, default)

    # -------------------------------------------------------------------------
    # Context Summaries
    # -------------------------------------------------------------------------

    def get_context_summary(self, max_items: int = 10) -> str:
        """Generate a summary of current context.

        Args:
            max_items: Maximum recent items to include

        Returns:
            Formatted context summary
        """
        lines = []

        # Active focus
        if self._context.active_project or self._context.active_task:
            lines.append("## Current Focus")
            if self._context.active_project:
                lines.append(f"- Project: {self._context.active_project}")
            if self._context.active_task:
                lines.append(f"- Task: {self._context.active_task}")
            lines.append("")

        # Active files
        if self._context.active_files:
            lines.append("## Active Files")
            for f in self._context.active_files[-5:]:
                lines.append(f"- {f}")
            lines.append("")

        # Goals
        if self._context.goals:
            lines.append("## Goals")
            for goal in self._context.goals:
                lines.append(f"- {goal}")
            lines.append("")

        # Constraints
        if self._context.constraints:
            lines.append("## Constraints")
            for constraint in self._context.constraints:
                lines.append(f"- {constraint}")
            lines.append("")

        # Open questions
        if self._context.open_questions:
            lines.append("## Open Questions")
            for q in self._context.open_questions:
                lines.append(f"- {q}")
            lines.append("")

        # Recent decisions
        recent_decisions = self._context.decisions[-3:]
        if recent_decisions:
            lines.append("## Recent Decisions")
            for d in recent_decisions:
                lines.append(f"- {d.description}")
                if d.reason:
                    lines.append(f"  Reason: {d.reason}")
            lines.append("")

        # Recent actions
        recent_actions = [
            i
            for i in self._context.recent_items[-max_items:]
            if i.type == ContextItemType.ACTION
        ][-5:]
        if recent_actions:
            lines.append("## Recent Actions")
            for a in recent_actions:
                lines.append(f"- {a.content}")
            lines.append("")

        return "\n".join(lines) if lines else "No context recorded yet."

    def get_full_context(self) -> ConversationContext:
        """Get the full context object."""
        return self._context

    # -------------------------------------------------------------------------
    # Session Management
    # -------------------------------------------------------------------------

    def compact(self, preserve_project: bool = True, max_items: int = 20) -> str:
        """Snapshot current context summary and start a new session."""
        summary = self.get_context_summary(max_items=max_items)
        self.new_session(preserve_project=preserve_project)
        return summary

    def new_session(self, preserve_project: bool = True) -> str:
        """Start a new session.

        Args:
            preserve_project: Whether to keep active project

        Returns:
            New session ID
        """
        old_project = self._context.active_project if preserve_project else None
        old_preferences = dict(self._context.preferences)

        self._context = ConversationContext()

        if old_project:
            self._context.active_project = old_project
        self._context.preferences = old_preferences

        if self._auto_save:
            self._save()

        logger.info(f"Started new session: {self._context.session_id}")
        return self._context.session_id

    def get_session_id(self) -> str:
        """Get current session ID."""
        return self._context.session_id

    def get_session_duration(self) -> float:
        """Get session duration in seconds."""
        return (datetime.now(UTC) - self._context.started_at).total_seconds()

    # -------------------------------------------------------------------------
    # Persistence
    # -------------------------------------------------------------------------

    def _save(self) -> None:
        """Save context to disk."""
        if not self._storage_path:
            return

        self._storage_path.parent.mkdir(parents=True, exist_ok=True)

        with self._storage_path.open("w") as f:
            json.dump(self._context.to_dict(), f, indent=2)

    def _load(self) -> None:
        """Load context from disk."""
        if not self._storage_path or not self._storage_path.exists():
            return

        try:
            with self._storage_path.open() as f:
                data = json.load(f)
            self._context = ConversationContext.from_dict(data)
            logger.info(f"Loaded context for session: {self._context.session_id}")
        except Exception as e:
            logger.error(f"Failed to load context: {e}")


# =============================================================================
# Global Instance
# =============================================================================

_global_context_manager: ContextManager | None = None


def get_context_manager() -> ContextManager:
    """Get the global context manager instance."""
    global _global_context_manager
    if _global_context_manager is None:
        from pms.config.settings import get_settings

        settings = get_settings()
        storage_path = settings.ensure_data_dir() / "context.json"
        _global_context_manager = ContextManager(storage_path=storage_path)
    return _global_context_manager


def set_context_manager(manager: ContextManager) -> None:
    """Set the global context manager instance."""
    global _global_context_manager
    _global_context_manager = manager
