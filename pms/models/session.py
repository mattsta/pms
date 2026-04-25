"""Session model for agent context persistence."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Self

from pms.models.base import BaseModel, generate_id, now_utc
from pms.models.enums import SessionStatus
from pms.models.json_types import JsonObject, ModelObject


@dataclass
class SessionMessage:
    """A single message in a session conversation."""

    id: str = field(default_factory=generate_id)
    session_id: str = ""
    # Preferred built-ins are system/user/assistant/tool, but custom roles stay
    # valid for planner, reviewer, plugin, or other extension-mediated transcripts.
    role: str = ""
    content: str = ""
    tokens: int | None = None
    cost_usd: float | None = None
    timestamp: datetime = field(default_factory=now_utc)
    metadata: JsonObject = field(default_factory=dict)

    def to_dict(self) -> ModelObject:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "tokens": self.tokens,
            "cost_usd": self.cost_usd,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class Session(BaseModel):
    """
    An agent session for context persistence.

    Sessions track:
    - Conversation history
    - Cost and token usage
    - Project context
    - Claude SDK session ID for forking
    """

    project_id: str | None = None
    claude_session_id: str | None = None  # For SDK session forking
    context_summary: str | None = None
    last_prompt: str | None = None
    last_response_summary: str | None = None
    status: SessionStatus = SessionStatus.ACTIVE
    cost_usd: float = 0.0
    token_count: int = 0
    message_count: int = 0
    ended_at: datetime | None = None
    state: JsonObject = field(default_factory=dict)

    def add_message(
        self,
        role: str,
        content: str,
        tokens: int | None = None,
        cost_usd: float | None = None,
    ) -> SessionMessage:
        """Create and track a new message."""
        self.message_count += 1
        if tokens:
            self.token_count += tokens
        if cost_usd:
            self.cost_usd += cost_usd
        self.updated_at = now_utc()

        return SessionMessage(
            session_id=self.id,
            role=role,
            content=content,
            tokens=tokens,
            cost_usd=cost_usd,
        )

    def update_summary(self, summary: str) -> Self:
        """Update context summary."""
        self.context_summary = summary
        self.updated_at = now_utc()
        return self

    def pause(self) -> Self:
        """Pause the session."""
        self.status = SessionStatus.PAUSED
        self.updated_at = now_utc()
        return self

    def resume(self) -> Self:
        """Resume a paused session."""
        if self.status == SessionStatus.ENDED:
            raise ValueError("Cannot resume ended session")
        self.status = SessionStatus.ACTIVE
        self.updated_at = now_utc()
        return self

    def end(self) -> Self:
        """End the session."""
        self.status = SessionStatus.ENDED
        self.ended_at = now_utc()
        self.updated_at = now_utc()
        return self

    @property
    def is_active(self) -> bool:
        """Check if session is active."""
        return self.status == SessionStatus.ACTIVE

    @property
    def duration_seconds(self) -> float | None:
        """Calculate session duration."""
        end = self.ended_at or now_utc()
        return (end - self.created_at).total_seconds()

    @property
    def avg_cost_per_message(self) -> float:
        """Calculate average cost per message."""
        if self.message_count == 0:
            return 0.0
        return self.cost_usd / self.message_count

    def to_dict(self) -> ModelObject:
        """Convert to dictionary."""
        data = super().to_dict()
        data["status"] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: ModelObject) -> Self:
        """Create from dictionary."""
        if "status" in data and isinstance(data["status"], str):
            data["status"] = SessionStatus(data["status"])
        return super().from_dict(data)


@dataclass
class SessionStats:
    """Aggregated statistics across sessions."""

    total_sessions: int = 0
    active_sessions: int = 0
    total_cost_usd: float = 0.0
    total_tokens: int = 0
    total_messages: int = 0
    avg_session_duration_seconds: float = 0.0
    avg_cost_per_session: float = 0.0

    @property
    def avg_cost_per_message(self) -> float:
        """Calculate average cost per message."""
        if self.total_messages == 0:
            return 0.0
        return self.total_cost_usd / self.total_messages
