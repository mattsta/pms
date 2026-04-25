"""Context priming helpers for agent sessions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pms.memory.context import ContextManager, get_context_manager
from pms.memory.knowledge import (
    Knowledge,
    KnowledgeStore,
    KnowledgeType,
    get_knowledge_store,
)


@dataclass(frozen=True)
class ContextPrimerConfig:
    """Configuration for building context primers."""

    max_items: int = 10
    header: str = "Context Primer"


class ContextPrimer:
    """Build primers and snapshots from the active context."""

    def __init__(
        self,
        context_manager: ContextManager,
        knowledge_store: KnowledgeStore | None = None,
        config: ContextPrimerConfig | None = None,
    ) -> None:
        self._context_manager = context_manager
        self._knowledge_store = knowledge_store
        self._config = config or ContextPrimerConfig()

    def build_primer(self, max_items: int | None = None) -> str:
        """Build a primer summary for agent system prompts."""
        summary = self._context_manager.get_context_summary(
            max_items=max_items or self._config.max_items
        )
        if summary == "No context recorded yet.":
            return ""
        return f"## {self._config.header}\n{summary}"

    async def snapshot(
        self,
        reason: str,
        tags: list[str] | None = None,
        max_items: int = 20,
    ) -> str | None:
        """Persist a context snapshot to the knowledge store."""
        if self._knowledge_store is None:
            return None

        summary, metadata = self._build_snapshot_payload(reason, max_items=max_items)
        if not summary:
            return None

        knowledge = Knowledge(
            type=KnowledgeType.CONTEXT,
            title=f"Context snapshot: {reason}",
            content=summary,
            tags=tags or [],
            source="context_snapshot",
            metadata=metadata,
        )
        return await self._knowledge_store.add(knowledge)

    async def compact_and_snapshot(
        self,
        reason: str,
        tags: list[str] | None = None,
        preserve_project: bool = True,
        max_items: int = 20,
    ) -> str | None:
        """Snapshot the current context, then start a new session."""
        summary, metadata = self._build_snapshot_payload(reason, max_items=max_items)
        self._context_manager.new_session(preserve_project=preserve_project)

        if self._knowledge_store is None or not summary:
            return None

        knowledge = Knowledge(
            type=KnowledgeType.CONTEXT,
            title=f"Context snapshot: {reason}",
            content=summary,
            tags=tags or [],
            source="context_snapshot",
            metadata=metadata,
        )
        return await self._knowledge_store.add(knowledge)

    def _build_snapshot_payload(
        self, reason: str, max_items: int
    ) -> tuple[str, dict[str, Any]]:
        summary = self._context_manager.get_context_summary(max_items=max_items)
        if summary == "No context recorded yet.":
            return "", {}

        context = self._context_manager.get_full_context()
        metadata = {
            "session_id": context.session_id,
            "active_project": context.active_project,
            "active_task": context.active_task,
            "started_at": context.started_at.isoformat(),
            "reason": reason,
        }
        return summary, metadata


def get_default_context_primer() -> ContextPrimer:
    """Get a context primer using the global memory stores."""
    return ContextPrimer(get_context_manager(), get_knowledge_store())
