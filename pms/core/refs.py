"""Reference System - Track relationships between entities.

References enable:
- Cross-entity relationships (task -> workflow, event -> knowledge)
- Bidirectional traversal (find all tasks triggered by a workflow)
- Relationship metadata (when created, why, by whom)
- Temporal tracking (relationship history)

Usage:
    from pms.core import Reference, ReferenceType, ReferenceStore

    store = ReferenceStore()

    # Create a reference
    ref = Reference(
        source_id="task_xxx",
        target_id="wf_yyy",
        relation=ReferenceType.TRIGGERED_BY,
        metadata={"reason": "Task completion"},
    )
    await store.add(ref)

    # Find related entities
    workflows = await store.get_targets("task_xxx", ReferenceType.TRIGGERED_BY)
    tasks = await store.get_sources("wf_yyy", ReferenceType.TRIGGERED_BY)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pms.core.ids import EntityType, generate_id, get_entity_type

logger = logging.getLogger(__name__)


class ReferenceType(Enum):
    """Types of relationships between entities."""

    # Hierarchical
    PARENT_OF = "parent_of"
    CHILD_OF = "child_of"
    CONTAINS = "contains"
    BELONGS_TO = "belongs_to"

    # Dependency
    DEPENDS_ON = "depends_on"
    BLOCKS = "blocks"
    REQUIRED_BY = "required_by"

    # Causal
    TRIGGERED_BY = "triggered_by"
    TRIGGERS = "triggers"
    CAUSED_BY = "caused_by"
    CAUSES = "causes"

    # Association
    RELATED_TO = "related_to"
    REFERENCES = "references"
    USES = "uses"
    USED_BY = "used_by"

    # Workflow/Automation
    EXECUTES = "executes"
    EXECUTED_BY = "executed_by"
    PRODUCES = "produces"
    PRODUCED_BY = "produced_by"

    # Learning/Knowledge
    LEARNED_FROM = "learned_from"
    TEACHES = "teaches"
    SIMILAR_TO = "similar_to"
    DERIVED_FROM = "derived_from"

    # Feedback
    POSITIVE_FOR = "positive_for"
    NEGATIVE_FOR = "negative_for"
    FEEDBACK_ON = "feedback_on"


# Inverse relationships for bidirectional traversal
_INVERSE_RELATIONS = {
    ReferenceType.PARENT_OF: ReferenceType.CHILD_OF,
    ReferenceType.CHILD_OF: ReferenceType.PARENT_OF,
    ReferenceType.CONTAINS: ReferenceType.BELONGS_TO,
    ReferenceType.BELONGS_TO: ReferenceType.CONTAINS,
    ReferenceType.DEPENDS_ON: ReferenceType.REQUIRED_BY,
    ReferenceType.BLOCKS: ReferenceType.DEPENDS_ON,
    ReferenceType.REQUIRED_BY: ReferenceType.DEPENDS_ON,
    ReferenceType.TRIGGERED_BY: ReferenceType.TRIGGERS,
    ReferenceType.TRIGGERS: ReferenceType.TRIGGERED_BY,
    ReferenceType.CAUSED_BY: ReferenceType.CAUSES,
    ReferenceType.CAUSES: ReferenceType.CAUSED_BY,
    ReferenceType.USES: ReferenceType.USED_BY,
    ReferenceType.USED_BY: ReferenceType.USES,
    ReferenceType.EXECUTES: ReferenceType.EXECUTED_BY,
    ReferenceType.EXECUTED_BY: ReferenceType.EXECUTES,
    ReferenceType.PRODUCES: ReferenceType.PRODUCED_BY,
    ReferenceType.PRODUCED_BY: ReferenceType.PRODUCES,
    ReferenceType.LEARNED_FROM: ReferenceType.TEACHES,
    ReferenceType.TEACHES: ReferenceType.LEARNED_FROM,
    ReferenceType.RELATED_TO: ReferenceType.RELATED_TO,
    ReferenceType.SIMILAR_TO: ReferenceType.SIMILAR_TO,
}


def get_inverse_relation(relation: ReferenceType) -> ReferenceType | None:
    """Get the inverse of a relation type."""
    return _INVERSE_RELATIONS.get(relation)


@dataclass
class Reference:
    """A reference between two entities.

    Attributes:
        source_id: ID of the source entity
        target_id: ID of the target entity
        relation: Type of relationship
        metadata: Additional relationship data
        strength: Relationship strength (0-1)
        created_at: When reference was created
        created_by: Who/what created it
        expires_at: Optional expiration
        id: Unique reference ID
    """

    source_id: str
    target_id: str
    relation: ReferenceType
    metadata: dict[str, Any] = field(default_factory=dict)
    strength: float = 1.0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    created_by: str = "system"
    expires_at: datetime | None = None
    id: str = field(default_factory=lambda: generate_id(EntityType.REFERENCE))

    @property
    def source_type(self) -> EntityType | None:
        """Get source entity type."""
        return get_entity_type(self.source_id)

    @property
    def target_type(self) -> EntityType | None:
        """Get target entity type."""
        return get_entity_type(self.target_id)

    def is_expired(self) -> bool:
        """Check if reference has expired."""
        if not self.expires_at:
            return False
        return datetime.now(UTC) > self.expires_at

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation": self.relation.value,
            "metadata": self.metadata,
            "strength": self.strength,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Reference:
        """Create from dictionary."""
        return cls(
            id=data["id"],
            source_id=data["source_id"],
            target_id=data["target_id"],
            relation=ReferenceType(data["relation"]),
            metadata=data.get("metadata", {}),
            strength=data.get("strength", 1.0),
            created_at=datetime.fromisoformat(data["created_at"]),
            created_by=data.get("created_by", "system"),
            expires_at=datetime.fromisoformat(data["expires_at"])
            if data.get("expires_at")
            else None,
        )


class ReferenceStore:
    """Store and query entity references.

    Features:
    - Add/remove references
    - Query by source, target, or relation
    - Bidirectional traversal
    - Automatic inverse relationships
    - Persistence
    """

    def __init__(
        self,
        storage_path: Path | str | None = None,
        auto_inverse: bool = True,
        auto_save: bool = True,
    ):
        """Initialize reference store.

        Args:
            storage_path: Path for persistence
            auto_inverse: Automatically create inverse references
            auto_save: Save after modifications
        """
        self._references: dict[str, Reference] = {}
        self._by_source: dict[str, set[str]] = {}  # source_id -> ref_ids
        self._by_target: dict[str, set[str]] = {}  # target_id -> ref_ids
        self._by_relation: dict[ReferenceType, set[str]] = {}  # relation -> ref_ids
        self._storage_path = Path(storage_path) if storage_path else None
        self._auto_inverse = auto_inverse
        self._auto_save = auto_save

        if self._storage_path and self._storage_path.exists():
            self._load()

    async def add(self, reference: Reference) -> str:
        """Add a reference.

        Args:
            reference: Reference to add

        Returns:
            Reference ID
        """
        # Store reference
        self._references[reference.id] = reference

        # Index by source
        if reference.source_id not in self._by_source:
            self._by_source[reference.source_id] = set()
        self._by_source[reference.source_id].add(reference.id)

        # Index by target
        if reference.target_id not in self._by_target:
            self._by_target[reference.target_id] = set()
        self._by_target[reference.target_id].add(reference.id)

        # Index by relation
        if reference.relation not in self._by_relation:
            self._by_relation[reference.relation] = set()
        self._by_relation[reference.relation].add(reference.id)

        logger.debug(
            f"Added reference: {reference.source_id} "
            f"--[{reference.relation.value}]--> {reference.target_id}"
        )

        # Create inverse if enabled
        if self._auto_inverse:
            inverse_relation = get_inverse_relation(reference.relation)
            if inverse_relation and inverse_relation != reference.relation:
                # Check if inverse already exists
                existing = await self.find(
                    source_id=reference.target_id,
                    target_id=reference.source_id,
                    relation=inverse_relation,
                )
                if not existing:
                    inverse = Reference(
                        source_id=reference.target_id,
                        target_id=reference.source_id,
                        relation=inverse_relation,
                        metadata={"inverse_of": reference.id, **reference.metadata},
                        strength=reference.strength,
                        created_by=reference.created_by,
                    )
                    # Add without recursion
                    self._references[inverse.id] = inverse
                    self._index_reference(inverse)

        if self._auto_save:
            self._save()

        return reference.id

    def _index_reference(self, ref: Reference) -> None:
        """Index a reference without creating inverse."""
        if ref.source_id not in self._by_source:
            self._by_source[ref.source_id] = set()
        self._by_source[ref.source_id].add(ref.id)

        if ref.target_id not in self._by_target:
            self._by_target[ref.target_id] = set()
        self._by_target[ref.target_id].add(ref.id)

        if ref.relation not in self._by_relation:
            self._by_relation[ref.relation] = set()
        self._by_relation[ref.relation].add(ref.id)

    async def remove(self, reference_id: str) -> bool:
        """Remove a reference.

        Args:
            reference_id: ID of reference to remove

        Returns:
            True if found and removed
        """
        ref = self._references.get(reference_id)
        if not ref:
            return False

        # Remove from indices
        self._by_source.get(ref.source_id, set()).discard(reference_id)
        self._by_target.get(ref.target_id, set()).discard(reference_id)
        self._by_relation.get(ref.relation, set()).discard(reference_id)

        del self._references[reference_id]

        if self._auto_save:
            self._save()

        return True

    async def get(self, reference_id: str) -> Reference | None:
        """Get a reference by ID."""
        return self._references.get(reference_id)

    async def find(
        self,
        source_id: str | None = None,
        target_id: str | None = None,
        relation: ReferenceType | None = None,
    ) -> list[Reference]:
        """Find references matching criteria.

        Args:
            source_id: Filter by source
            target_id: Filter by target
            relation: Filter by relation type

        Returns:
            Matching references
        """
        # Start with all references or filtered set
        ref_ids: set[str] | None = None

        if source_id:
            ref_ids = self._by_source.get(source_id, set())

        if target_id:
            target_refs = self._by_target.get(target_id, set())
            ref_ids = ref_ids & target_refs if ref_ids else target_refs

        if relation:
            relation_refs = self._by_relation.get(relation, set())
            ref_ids = ref_ids & relation_refs if ref_ids else relation_refs

        if ref_ids is None:
            ref_ids = set(self._references.keys())

        # Filter expired
        return [
            self._references[rid]
            for rid in ref_ids
            if rid in self._references and not self._references[rid].is_expired()
        ]

    async def get_targets(
        self,
        source_id: str,
        relation: ReferenceType | None = None,
    ) -> list[str]:
        """Get all target IDs from a source.

        Args:
            source_id: Source entity ID
            relation: Optional relation filter

        Returns:
            List of target IDs
        """
        refs = await self.find(source_id=source_id, relation=relation)
        return [ref.target_id for ref in refs]

    async def get_sources(
        self,
        target_id: str,
        relation: ReferenceType | None = None,
    ) -> list[str]:
        """Get all source IDs pointing to a target.

        Args:
            target_id: Target entity ID
            relation: Optional relation filter

        Returns:
            List of source IDs
        """
        refs = await self.find(target_id=target_id, relation=relation)
        return [ref.source_id for ref in refs]

    async def get_related(
        self,
        entity_id: str,
        relation: ReferenceType | None = None,
    ) -> list[str]:
        """Get all entities related to an entity (as source or target).

        Args:
            entity_id: Entity to find relations for
            relation: Optional relation filter

        Returns:
            List of related entity IDs
        """
        targets = await self.get_targets(entity_id, relation)
        sources = await self.get_sources(entity_id, relation)
        return list(set(targets + sources))

    async def has_relation(
        self,
        source_id: str,
        target_id: str,
        relation: ReferenceType | None = None,
    ) -> bool:
        """Check if a relation exists between two entities.

        Args:
            source_id: Source entity
            target_id: Target entity
            relation: Optional specific relation

        Returns:
            True if relation exists
        """
        refs = await self.find(
            source_id=source_id, target_id=target_id, relation=relation
        )
        return len(refs) > 0

    async def get_reference_graph(
        self,
        entity_id: str,
        depth: int = 2,
    ) -> dict[str, Any]:
        """Get reference graph starting from an entity.

        Args:
            entity_id: Starting entity
            depth: How many levels to traverse

        Returns:
            Graph structure with nodes and edges
        """
        visited: set[str] = set()
        edges: list[dict[str, Any]] = []

        async def traverse(current_id: str, current_depth: int) -> None:
            if current_depth > depth or current_id in visited:
                return
            visited.add(current_id)

            refs = await self.find(source_id=current_id)
            for ref in refs:
                edges.append(
                    {
                        "source": ref.source_id,
                        "target": ref.target_id,
                        "relation": ref.relation.value,
                        "strength": ref.strength,
                    }
                )
                await traverse(ref.target_id, current_depth + 1)

            refs = await self.find(target_id=current_id)
            for ref in refs:
                edges.append(
                    {
                        "source": ref.source_id,
                        "target": ref.target_id,
                        "relation": ref.relation.value,
                        "strength": ref.strength,
                    }
                )
                await traverse(ref.source_id, current_depth + 1)

        await traverse(entity_id, 0)

        return {
            "root": entity_id,
            "nodes": list(visited),
            "edges": edges,
        }

    def get_stats(self) -> dict[str, Any]:
        """Get reference store statistics."""
        by_relation = {rel.value: len(ids) for rel, ids in self._by_relation.items()}
        return {
            "total_references": len(self._references),
            "unique_sources": len(self._by_source),
            "unique_targets": len(self._by_target),
            "by_relation": by_relation,
        }

    def _save(self) -> None:
        """Save to disk."""
        if not self._storage_path:
            return

        self._storage_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "version": 1,
            "references": [ref.to_dict() for ref in self._references.values()],
        }

        with self._storage_path.open("w") as f:
            json.dump(data, f, indent=2)

    def _load(self) -> None:
        """Load from disk."""
        if not self._storage_path or not self._storage_path.exists():
            return

        try:
            with self._storage_path.open() as f:
                data = json.load(f)

            for ref_data in data.get("references", []):
                ref = Reference.from_dict(ref_data)
                self._references[ref.id] = ref
                self._index_reference(ref)

            logger.info(f"Loaded {len(self._references)} references")

        except Exception as e:
            logger.error(f"Failed to load reference store: {e}")


# =============================================================================
# Global Instance
# =============================================================================

_global_store: ReferenceStore | None = None


def get_reference_store() -> ReferenceStore:
    """Get the global reference store instance."""
    global _global_store
    if _global_store is None:
        _global_store = ReferenceStore()
    return _global_store


def set_reference_store(store: ReferenceStore) -> None:
    """Set the global reference store instance."""
    global _global_store
    _global_store = store
