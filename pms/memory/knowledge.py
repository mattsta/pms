"""Knowledge Store - Persistent storage for learned information.

The Knowledge Store enables PMS to:
- Remember solutions to problems
- Store code patterns and templates
- Track entity relationships
- Learn from successful operations

Usage:
    from pms.memory import KnowledgeStore, Knowledge, KnowledgeType

    store = KnowledgeStore()

    # Store knowledge
    await store.add(Knowledge(
        type=KnowledgeType.SOLUTION,
        title="Fix import cycle",
        content="Move shared types to a separate module",
        tags=["python", "imports", "architecture"],
        source="user_feedback",
    ))

    # Search knowledge
    results = await store.search("how to fix circular imports")
    for item, score in results:
        print(f"{item.title}: {score:.2f}")
"""

from __future__ import annotations

import json
import logging
import math
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Knowledge Types
# =============================================================================


class KnowledgeType(Enum):
    """Types of knowledge that can be stored."""

    PATTERN = "pattern"  # Reusable code/design patterns
    SOLUTION = "solution"  # Solutions to specific problems
    PROCEDURE = "procedure"  # Step-by-step instructions
    ENTITY = "entity"  # Information about entities (projects, services)
    CONTEXT = "context"  # Conversation/session context
    PREFERENCE = "preference"  # User preferences
    TEMPLATE = "template"  # Code/document templates
    NOTE = "note"  # General notes and observations
    TOOL_USAGE = "tool_usage"  # How to use specific tools
    ERROR_FIX = "error_fix"  # Fixes for known errors


# =============================================================================
# Knowledge Model
# =============================================================================


@dataclass
class Knowledge:
    """A piece of stored knowledge.

    Attributes:
        type: Category of knowledge
        title: Short descriptive title
        content: Main content (text, code, JSON)
        tags: Searchable tags
        metadata: Additional structured data
        source: Where this knowledge came from
        confidence: How reliable this knowledge is (0-1)
        access_count: Number of times retrieved
        last_accessed: When last retrieved
        created_at: When first stored
        expires_at: Optional expiration
        id: Unique identifier
    """

    type: KnowledgeType
    title: str
    content: str
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    source: str = "system"
    confidence: float = 1.0
    access_count: int = 0
    last_accessed: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def is_expired(self) -> bool:
        """Check if knowledge has expired."""
        if not self.expires_at:
            return False
        return datetime.now(UTC) > self.expires_at

    def relevance_score(self, query_terms: set[str]) -> float:
        """Calculate relevance score for a query.

        Uses TF-IDF-like scoring with:
        - Term frequency in title (high weight)
        - Term frequency in content
        - Tag matches (high weight)
        - Recency boost
        - Access frequency boost
        """
        score = 0.0

        # Normalize query terms
        query_lower = {t.lower() for t in query_terms}

        # Title matches (high weight)
        title_lower = self.title.lower()
        title_terms = set(re.findall(r"\w+", title_lower))
        title_matches = len(query_lower & title_terms)
        score += title_matches * 3.0

        # Tag matches (high weight)
        tags_lower = {t.lower() for t in self.tags}
        tag_matches = len(query_lower & tags_lower)
        score += tag_matches * 2.5

        # Content matches
        content_lower = self.content.lower()
        content_terms = set(re.findall(r"\w+", content_lower))
        content_matches = len(query_lower & content_terms)
        # Normalize by content length
        if content_terms:
            score += content_matches * (1.0 / math.log(len(content_terms) + 1))

        # Confidence factor
        score *= self.confidence

        # Recency boost (items accessed recently score higher)
        if self.last_accessed:
            age_hours = (datetime.now(UTC) - self.last_accessed).total_seconds() / 3600
            recency_boost = 1.0 / (1.0 + math.log(age_hours + 1))
            score *= 1.0 + recency_boost * 0.2

        # Access frequency boost (popular items score higher)
        if self.access_count > 0:
            popularity_boost = math.log(self.access_count + 1) * 0.1
            score *= 1.0 + popularity_boost

        return score

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "type": self.type.value,
            "title": self.title,
            "content": self.content,
            "tags": self.tags,
            "metadata": self.metadata,
            "source": self.source,
            "confidence": self.confidence,
            "access_count": self.access_count,
            "last_accessed": self.last_accessed.isoformat()
            if self.last_accessed
            else None,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Knowledge:
        """Create from dictionary."""
        return cls(
            id=data["id"],
            type=KnowledgeType(data["type"]),
            title=data["title"],
            content=data["content"],
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
            source=data.get("source", "system"),
            confidence=data.get("confidence", 1.0),
            access_count=data.get("access_count", 0),
            last_accessed=datetime.fromisoformat(data["last_accessed"])
            if data.get("last_accessed")
            else None,
            created_at=datetime.fromisoformat(data["created_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"])
            if data.get("expires_at")
            else None,
        )


# =============================================================================
# Knowledge Store
# =============================================================================


class KnowledgeStore:
    """Persistent storage for knowledge with search capabilities.

    Features:
    - Add/update/delete knowledge entries
    - Search by query with relevance scoring
    - Filter by type, tags, source
    - Track access patterns
    - Automatic expiration cleanup
    - JSON file persistence
    """

    def __init__(
        self,
        storage_path: Path | str | None = None,
        auto_save: bool = True,
    ):
        """Initialize knowledge store.

        Args:
            storage_path: Path to JSON storage file
            auto_save: Whether to save after each modification
        """
        self._entries: dict[str, Knowledge] = {}
        self._storage_path = Path(storage_path) if storage_path else None
        self._auto_save = auto_save

        # Load existing data
        if self._storage_path and self._storage_path.exists():
            self._load()

    # -------------------------------------------------------------------------
    # CRUD Operations
    # -------------------------------------------------------------------------

    async def add(self, knowledge: Knowledge) -> str:
        """Add knowledge to the store.

        Args:
            knowledge: Knowledge entry to add

        Returns:
            Knowledge ID
        """
        self._entries[knowledge.id] = knowledge
        logger.info(f"Added knowledge: {knowledge.title} ({knowledge.type.value})")

        if self._auto_save:
            self._save()

        return knowledge.id

    async def get(self, knowledge_id: str) -> Knowledge | None:
        """Get knowledge by ID.

        Updates access tracking.
        """
        knowledge = self._entries.get(knowledge_id)
        if knowledge:
            knowledge.access_count += 1
            knowledge.last_accessed = datetime.now(UTC)
            if self._auto_save:
                self._save()
        return knowledge

    async def update(
        self,
        knowledge_id: str,
        **updates: Any,
    ) -> Knowledge | None:
        """Update knowledge entry.

        Args:
            knowledge_id: ID of entry to update
            **updates: Fields to update

        Returns:
            Updated knowledge or None if not found
        """
        knowledge = self._entries.get(knowledge_id)
        if not knowledge:
            return None

        for key, value in updates.items():
            if hasattr(knowledge, key):
                setattr(knowledge, key, value)

        if self._auto_save:
            self._save()

        return knowledge

    async def delete(self, knowledge_id: str) -> bool:
        """Delete knowledge entry.

        Returns:
            True if found and deleted
        """
        if knowledge_id in self._entries:
            del self._entries[knowledge_id]
            if self._auto_save:
                self._save()
            return True
        return False

    async def list_all(
        self,
        type_filter: KnowledgeType | None = None,
        tag_filter: str | None = None,
        limit: int = 100,
    ) -> list[Knowledge]:
        """List all knowledge entries.

        Args:
            type_filter: Filter by type
            tag_filter: Filter by tag
            limit: Maximum entries to return

        Returns:
            List of knowledge entries
        """
        entries = list(self._entries.values())

        # Filter expired
        entries = [e for e in entries if not e.is_expired()]

        # Apply filters
        if type_filter:
            entries = [e for e in entries if e.type == type_filter]

        if tag_filter:
            tag_lower = tag_filter.lower()
            entries = [
                e for e in entries if any(tag_lower in t.lower() for t in e.tags)
            ]

        # Sort by access count (most popular first)
        entries.sort(key=lambda e: e.access_count, reverse=True)

        return entries[:limit]

    # -------------------------------------------------------------------------
    # Search
    # -------------------------------------------------------------------------

    async def search(
        self,
        query: str,
        type_filter: KnowledgeType | None = None,
        min_score: float = 0.1,
        limit: int = 10,
    ) -> list[tuple[Knowledge, float]]:
        """Search knowledge by query.

        Uses relevance scoring based on:
        - Title/content/tag matches
        - Recency and popularity
        - Confidence level

        Args:
            query: Search query
            type_filter: Optional type filter
            min_score: Minimum relevance score
            limit: Maximum results

        Returns:
            List of (knowledge, score) tuples, sorted by score
        """
        # Tokenize query
        query_terms = set(re.findall(r"\w+", query.lower()))
        if not query_terms:
            return []

        results: list[tuple[Knowledge, float]] = []

        for knowledge in self._entries.values():
            # Skip expired
            if knowledge.is_expired():
                continue

            # Apply type filter
            if type_filter and knowledge.type != type_filter:
                continue

            # Calculate score
            score = knowledge.relevance_score(query_terms)

            if score >= min_score:
                results.append((knowledge, score))

        # Sort by score descending
        results.sort(key=lambda x: x[1], reverse=True)

        # Update access tracking for returned results
        for knowledge, _ in results[:limit]:
            knowledge.access_count += 1
            knowledge.last_accessed = datetime.now(UTC)

        if self._auto_save and results:
            self._save()

        return results[:limit]

    async def find_similar(
        self,
        knowledge_id: str,
        limit: int = 5,
    ) -> list[tuple[Knowledge, float]]:
        """Find knowledge similar to a given entry.

        Args:
            knowledge_id: ID of knowledge to find similar to
            limit: Maximum results

        Returns:
            List of (knowledge, similarity) tuples
        """
        source = self._entries.get(knowledge_id)
        if not source:
            return []

        # Use title and tags as query
        query = f"{source.title} {' '.join(source.tags)}"
        results = await self.search(query, type_filter=source.type, limit=limit + 1)

        # Filter out the source entry
        return [(k, s) for k, s in results if k.id != knowledge_id][:limit]

    # -------------------------------------------------------------------------
    # Specialized Queries
    # -------------------------------------------------------------------------

    async def get_solutions_for_error(
        self, error_message: str
    ) -> list[tuple[Knowledge, float]]:
        """Find solutions for an error message.

        Args:
            error_message: The error message to search for

        Returns:
            Relevant solutions sorted by score
        """
        return await self.search(
            error_message,
            type_filter=KnowledgeType.ERROR_FIX,
            limit=5,
        )

    async def get_patterns_for_task(
        self, task_description: str
    ) -> list[tuple[Knowledge, float]]:
        """Find relevant patterns for a task.

        Args:
            task_description: Description of the task

        Returns:
            Relevant patterns sorted by score
        """
        return await self.search(
            task_description,
            type_filter=KnowledgeType.PATTERN,
            limit=5,
        )

    async def get_tool_usage(self, tool_name: str) -> Knowledge | None:
        """Get usage information for a tool.

        Args:
            tool_name: Name of the tool

        Returns:
            Tool usage knowledge if found
        """
        results = await self.search(
            tool_name,
            type_filter=KnowledgeType.TOOL_USAGE,
            limit=1,
        )
        return results[0][0] if results else None

    # -------------------------------------------------------------------------
    # Learning Operations
    # -------------------------------------------------------------------------

    async def learn_from_success(
        self,
        operation: str,
        context: dict[str, Any],
        outcome: str,
        tags: list[str] | None = None,
    ) -> str:
        """Learn from a successful operation.

        Creates or updates knowledge based on what worked.

        Args:
            operation: What operation succeeded
            context: Context of the operation
            outcome: What the outcome was
            tags: Optional tags

        Returns:
            Knowledge ID
        """
        # Check for existing similar knowledge
        existing = await self.search(operation, limit=1)

        if existing and existing[0][1] > 2.0:
            # Update existing knowledge
            knowledge = existing[0][0]
            knowledge.confidence = min(1.0, knowledge.confidence + 0.1)
            knowledge.metadata.setdefault("success_count", 0)
            knowledge.metadata["success_count"] += 1
            knowledge.metadata["last_success"] = datetime.now(UTC).isoformat()

            if self._auto_save:
                self._save()

            return knowledge.id

        # Create new knowledge
        knowledge = Knowledge(
            type=KnowledgeType.SOLUTION,
            title=operation,
            content=f"Context: {json.dumps(context, indent=2)}\n\nOutcome: {outcome}",
            tags=tags or [],
            source="success_learning",
            confidence=0.7,  # Start with moderate confidence
            metadata={
                "success_count": 1,
                "last_success": datetime.now(UTC).isoformat(),
            },
        )

        return await self.add(knowledge)

    async def learn_from_failure(
        self,
        operation: str,
        error: str,
        fix: str | None = None,
        tags: list[str] | None = None,
    ) -> str:
        """Learn from a failed operation.

        Args:
            operation: What operation failed
            error: The error that occurred
            fix: Optional fix that worked
            tags: Optional tags

        Returns:
            Knowledge ID
        """
        if fix:
            # Store as error fix
            knowledge = Knowledge(
                type=KnowledgeType.ERROR_FIX,
                title=f"Fix for: {error[:50]}...",
                content=f"Error: {error}\n\nFix: {fix}",
                tags=["error", "fix"] + (tags or []),
                source="failure_learning",
                confidence=0.8,
                metadata={
                    "operation": operation,
                    "error_type": error.split(":")[0] if ":" in error else "unknown",
                },
            )
        else:
            # Store as known issue (negative knowledge)
            knowledge = Knowledge(
                type=KnowledgeType.ERROR_FIX,
                title=f"Known issue: {error[:50]}...",
                content=f"Operation: {operation}\n\nError: {error}\n\nNo fix known yet.",
                tags=["error", "unresolved"] + (tags or []),
                source="failure_learning",
                confidence=0.5,
                metadata={
                    "operation": operation,
                    "resolved": False,
                },
            )

        return await self.add(knowledge)

    # -------------------------------------------------------------------------
    # Maintenance
    # -------------------------------------------------------------------------

    async def cleanup_expired(self) -> int:
        """Remove expired knowledge entries.

        Returns:
            Number of entries removed
        """
        expired_ids = [k_id for k_id, k in self._entries.items() if k.is_expired()]

        for k_id in expired_ids:
            del self._entries[k_id]

        if expired_ids and self._auto_save:
            self._save()

        logger.info(f"Cleaned up {len(expired_ids)} expired knowledge entries")
        return len(expired_ids)

    async def decay_confidence(self, decay_rate: float = 0.01) -> int:
        """Decay confidence of unused knowledge.

        Knowledge that hasn't been accessed loses confidence over time.

        Args:
            decay_rate: Amount to decay per call

        Returns:
            Number of entries decayed
        """
        decayed = 0
        now = datetime.now(UTC)

        for knowledge in self._entries.values():
            if knowledge.last_accessed:
                # Decay if not accessed in last 7 days
                age = (now - knowledge.last_accessed).days
                if age > 7:
                    knowledge.confidence = max(0.1, knowledge.confidence - decay_rate)
                    decayed += 1

        if decayed and self._auto_save:
            self._save()

        return decayed

    def get_stats(self) -> dict[str, Any]:
        """Get knowledge store statistics."""
        by_type: dict[str, int] = {}
        total_access = 0

        for k in self._entries.values():
            by_type[k.type.value] = by_type.get(k.type.value, 0) + 1
            total_access += k.access_count

        return {
            "total_entries": len(self._entries),
            "by_type": by_type,
            "total_accesses": total_access,
            "storage_path": str(self._storage_path) if self._storage_path else None,
        }

    # -------------------------------------------------------------------------
    # Persistence
    # -------------------------------------------------------------------------

    def _save(self) -> None:
        """Save to disk."""
        if not self._storage_path:
            return

        self._storage_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "version": 1,
            "entries": [k.to_dict() for k in self._entries.values()],
        }

        with self._storage_path.open("w") as f:
            json.dump(data, f, indent=2)

        logger.debug(
            f"Saved {len(self._entries)} knowledge entries to {self._storage_path}"
        )

    def _load(self) -> None:
        """Load from disk."""
        if not self._storage_path or not self._storage_path.exists():
            return

        try:
            with self._storage_path.open() as f:
                data = json.load(f)

            for entry_data in data.get("entries", []):
                knowledge = Knowledge.from_dict(entry_data)
                self._entries[knowledge.id] = knowledge

            logger.info(
                f"Loaded {len(self._entries)} knowledge entries from {self._storage_path}"
            )

        except Exception as e:
            logger.error(f"Failed to load knowledge store: {e}")


# =============================================================================
# Global Instance
# =============================================================================

_global_store: KnowledgeStore | None = None


def get_knowledge_store() -> KnowledgeStore:
    """Get the global knowledge store instance."""
    global _global_store
    if _global_store is None:
        from pms.config.settings import get_settings

        settings = get_settings()
        storage_path = settings.ensure_data_dir() / "knowledge.json"
        _global_store = KnowledgeStore(storage_path=storage_path)
    return _global_store


def set_knowledge_store(store: KnowledgeStore) -> None:
    """Set the global knowledge store instance."""
    global _global_store
    _global_store = store
