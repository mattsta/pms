"""Entity Registry - Central registry for entity discoverability.

The registry provides:
- Entity registration and lookup
- Type-safe entity access
- Lifecycle tracking (created, updated, deleted)
- Cross-module entity discovery

Usage:
    from pms.core import EntityRegistry, EntityInfo

    registry = get_entity_registry()

    # Register an entity
    registry.register(EntityInfo(
        id="task_xxx",
        type=EntityType.TASK,
        name="My Task",
        metadata={"project_id": "proj_yyy"},
    ))

    # Look up entity
    info = registry.get("task_xxx")

    # Find by type
    all_tasks = registry.find_by_type(EntityType.TASK)
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pms.core.ids import EntityType, get_entity_type

logger = logging.getLogger(__name__)


class EntityStatus(Enum):
    """Status of an entity in the registry."""

    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


@dataclass
class EntityInfo:
    """Information about a registered entity.

    Attributes:
        id: Entity ID
        type: Entity type
        name: Human-readable name
        description: Optional description
        status: Current status
        metadata: Additional metadata
        created_at: When registered
        updated_at: When last updated
        deleted_at: When deleted (if applicable)
        parent_id: Optional parent entity
        tags: Searchable tags
    """

    id: str
    type: EntityType
    name: str
    description: str = ""
    status: EntityStatus = EntityStatus.ACTIVE
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    deleted_at: datetime | None = None
    parent_id: str | None = None
    tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Auto-detect type from ID if not specified
        if self.type is None:
            detected = get_entity_type(self.id)
            if detected:
                self.type = detected

    def is_active(self) -> bool:
        """Check if entity is active."""
        return self.status == EntityStatus.ACTIVE

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "type": self.type.value,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
            "parent_id": self.parent_id,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EntityInfo:
        """Create from dictionary."""
        return cls(
            id=data["id"],
            type=EntityType(data["type"]),
            name=data["name"],
            description=data.get("description", ""),
            status=EntityStatus(data.get("status", "active")),
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            deleted_at=datetime.fromisoformat(data["deleted_at"])
            if data.get("deleted_at")
            else None,
            parent_id=data.get("parent_id"),
            tags=data.get("tags", []),
        )


# Type for entity change listeners
EntityChangeListener = Callable[[str, EntityInfo | None, str], None]


class EntityRegistry:
    """Central registry for all entities.

    Features:
    - Register/unregister entities
    - Lookup by ID, type, or tags
    - Lifecycle tracking
    - Change notifications
    - Persistence
    """

    def __init__(
        self,
        storage_path: Path | str | None = None,
        auto_save: bool = True,
    ):
        """Initialize entity registry.

        Args:
            storage_path: Path for persistence
            auto_save: Save after modifications
        """
        self._entities: dict[str, EntityInfo] = {}
        self._by_type: dict[EntityType, set[str]] = {}
        self._by_parent: dict[str, set[str]] = {}
        self._by_tag: dict[str, set[str]] = {}
        self._listeners: list[EntityChangeListener] = []
        self._storage_path = Path(storage_path) if storage_path else None
        self._auto_save = auto_save

        if self._storage_path and self._storage_path.exists():
            self._load()

    def register(self, info: EntityInfo) -> str:
        """Register an entity.

        Args:
            info: Entity information

        Returns:
            Entity ID
        """
        self._entities[info.id] = info
        self._index_entity(info)
        self._notify_change(info.id, info, "registered")

        logger.debug(f"Registered entity: {info.id} ({info.type.value})")

        if self._auto_save:
            self._save()

        return info.id

    def _index_entity(self, info: EntityInfo) -> None:
        """Index entity for fast lookup."""
        # Index by type
        if info.type not in self._by_type:
            self._by_type[info.type] = set()
        self._by_type[info.type].add(info.id)

        # Index by parent
        if info.parent_id:
            if info.parent_id not in self._by_parent:
                self._by_parent[info.parent_id] = set()
            self._by_parent[info.parent_id].add(info.id)

        # Index by tags
        for tag in info.tags:
            tag_lower = tag.lower()
            if tag_lower not in self._by_tag:
                self._by_tag[tag_lower] = set()
            self._by_tag[tag_lower].add(info.id)

    def update(self, entity_id: str, **updates: Any) -> EntityInfo | None:
        """Update entity information.

        Args:
            entity_id: ID of entity to update
            **updates: Fields to update

        Returns:
            Updated entity or None if not found
        """
        info = self._entities.get(entity_id)
        if not info:
            return None

        # Remove from old indices
        self._unindex_entity(info)

        # Apply updates
        for key, value in updates.items():
            if hasattr(info, key):
                setattr(info, key, value)

        info.updated_at = datetime.now(UTC)

        # Re-index
        self._index_entity(info)
        self._notify_change(entity_id, info, "updated")

        if self._auto_save:
            self._save()

        return info

    def _unindex_entity(self, info: EntityInfo) -> None:
        """Remove entity from indices."""
        self._by_type.get(info.type, set()).discard(info.id)

        if info.parent_id:
            self._by_parent.get(info.parent_id, set()).discard(info.id)

        for tag in info.tags:
            self._by_tag.get(tag.lower(), set()).discard(info.id)

    def unregister(self, entity_id: str, soft_delete: bool = True) -> bool:
        """Unregister an entity.

        Args:
            entity_id: ID of entity to unregister
            soft_delete: If True, mark as deleted; if False, remove entirely

        Returns:
            True if found and unregistered
        """
        info = self._entities.get(entity_id)
        if not info:
            return False

        if soft_delete:
            info.status = EntityStatus.DELETED
            info.deleted_at = datetime.now(UTC)
            self._notify_change(entity_id, info, "deleted")
        else:
            self._unindex_entity(info)
            del self._entities[entity_id]
            self._notify_change(entity_id, None, "removed")

        if self._auto_save:
            self._save()

        return True

    def get(self, entity_id: str) -> EntityInfo | None:
        """Get entity by ID.

        Args:
            entity_id: Entity ID

        Returns:
            Entity info or None
        """
        return self._entities.get(entity_id)

    def exists(self, entity_id: str) -> bool:
        """Check if entity exists."""
        return entity_id in self._entities

    def is_active(self, entity_id: str) -> bool:
        """Check if entity exists and is active."""
        info = self._entities.get(entity_id)
        return info is not None and info.is_active()

    def find_by_type(
        self,
        entity_type: EntityType,
        active_only: bool = True,
    ) -> list[EntityInfo]:
        """Find all entities of a type.

        Args:
            entity_type: Type to find
            active_only: Only return active entities

        Returns:
            List of matching entities
        """
        entity_ids = self._by_type.get(entity_type, set())
        entities = [self._entities[eid] for eid in entity_ids if eid in self._entities]

        if active_only:
            entities = [e for e in entities if e.is_active()]

        return entities

    def find_by_parent(
        self,
        parent_id: str,
        active_only: bool = True,
    ) -> list[EntityInfo]:
        """Find all children of a parent entity.

        Args:
            parent_id: Parent entity ID
            active_only: Only return active entities

        Returns:
            List of child entities
        """
        entity_ids = self._by_parent.get(parent_id, set())
        entities = [self._entities[eid] for eid in entity_ids if eid in self._entities]

        if active_only:
            entities = [e for e in entities if e.is_active()]

        return entities

    def find_by_tag(
        self,
        tag: str,
        active_only: bool = True,
    ) -> list[EntityInfo]:
        """Find entities by tag.

        Args:
            tag: Tag to search for
            active_only: Only return active entities

        Returns:
            List of matching entities
        """
        entity_ids = self._by_tag.get(tag.lower(), set())
        entities = [self._entities[eid] for eid in entity_ids if eid in self._entities]

        if active_only:
            entities = [e for e in entities if e.is_active()]

        return entities

    def search(
        self,
        query: str,
        types: list[EntityType] | None = None,
        active_only: bool = True,
        limit: int = 50,
    ) -> list[EntityInfo]:
        """Search entities by name/description.

        Args:
            query: Search query
            types: Optional type filter
            active_only: Only return active entities
            limit: Maximum results

        Returns:
            Matching entities
        """
        query_lower = query.lower()
        results = []

        for info in self._entities.values():
            if active_only and not info.is_active():
                continue

            if types and info.type not in types:
                continue

            # Match name, description, or tags
            if (
                query_lower in info.name.lower()
                or query_lower in info.description.lower()
                or any(query_lower in tag.lower() for tag in info.tags)
            ):
                results.append(info)

        # Sort by relevance (name match first)
        results.sort(
            key=lambda e: (
                0 if query_lower in e.name.lower() else 1,
                e.name.lower(),
            )
        )

        return results[:limit]

    def add_listener(self, listener: EntityChangeListener) -> None:
        """Add a change listener.

        Args:
            listener: Callback function(entity_id, info, change_type)
        """
        self._listeners.append(listener)

    def remove_listener(self, listener: EntityChangeListener) -> None:
        """Remove a change listener."""
        if listener in self._listeners:
            self._listeners.remove(listener)

    def _notify_change(
        self,
        entity_id: str,
        info: EntityInfo | None,
        change_type: str,
    ) -> None:
        """Notify listeners of a change."""
        for listener in self._listeners:
            try:
                listener(entity_id, info, change_type)
            except Exception as e:
                logger.error(f"Listener error: {e}")

    def get_stats(self) -> dict[str, Any]:
        """Get registry statistics."""
        by_type = {t.value: len(ids) for t, ids in self._by_type.items()}
        active = sum(1 for e in self._entities.values() if e.is_active())

        return {
            "total_entities": len(self._entities),
            "active_entities": active,
            "by_type": by_type,
            "unique_tags": len(self._by_tag),
        }

    def _save(self) -> None:
        """Save to disk."""
        if not self._storage_path:
            return

        self._storage_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "version": 1,
            "entities": [e.to_dict() for e in self._entities.values()],
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

            for entity_data in data.get("entities", []):
                info = EntityInfo.from_dict(entity_data)
                self._entities[info.id] = info
                self._index_entity(info)

            logger.info(f"Loaded {len(self._entities)} entities")

        except Exception as e:
            logger.error(f"Failed to load entity registry: {e}")


# =============================================================================
# Global Instance
# =============================================================================

_global_registry: EntityRegistry | None = None


def get_entity_registry() -> EntityRegistry:
    """Get the global entity registry instance."""
    global _global_registry
    if _global_registry is None:
        _global_registry = EntityRegistry()
    return _global_registry


def set_entity_registry(registry: EntityRegistry) -> None:
    """Set the global entity registry instance."""
    global _global_registry
    _global_registry = registry
