"""Unified ID System - Type-safe identifiers across all PMS modules.

All entities in PMS use prefixed UUIDs for:
- Type safety: Immediately know what type an ID refers to
- Traceability: Easy to search/filter by entity type
- Cross-referencing: Safe references between different entity types

ID Format: {prefix}_{uuid}
- proj_a1b2c3d4-e5f6-7890-abcd-ef1234567890
- task_b2c3d4e5-f6a7-8901-bcde-f23456789012

Usage:
    from pms.core import generate_id, EntityType, parse_id

    # Generate typed ID
    task_id = generate_id(EntityType.TASK)

    # Parse existing ID
    entity_type, uuid_part = parse_id(task_id)

    # Validate ID
    if is_valid_id(some_id, EntityType.TASK):
        # Safe to use as task ID
        pass
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum


class EntityType(Enum):
    """Types of entities in the PMS system.

    Each type has a short prefix used in ID generation.
    """

    # Core entities
    PRODUCT = "prod"
    ORGANIZATION = "org"
    TEAM = "team"
    PORTFOLIO = "port"
    PROGRAM = "prog"
    PROJECT = "proj"
    GOAL = "goal"
    OBJECTIVE = "obj"
    KEY_RESULT = "kr"
    PLAN = "plan"
    TASK = "task"
    MILESTONE = "mile"
    TAG = "tag"
    API_KEY = "apikey"

    # Remote/AWS entities
    REMOTE_HOST = "host"
    TEST_SERVER = "srv"
    TEST_RUN = "trun"

    # Automation entities
    WORKFLOW = "wf"
    WORKFLOW_RUN = "wfrun"
    WORKFLOW_STEP = "step"
    EVENT = "evt"
    TRIGGER = "trig"

    # Memory entities
    KNOWLEDGE = "know"
    PATTERN = "pat"
    FEEDBACK = "fb"
    CONTEXT = "ctx"
    CONTEXT_ITEM = "ctxi"

    # Learning entities
    OUTCOME = "out"
    SUGGESTION = "sug"

    # Reference/relation entities
    REFERENCE = "ref"
    DEPENDENCY = "dep"

    # Session entities
    SESSION = "sess"

    # Document entities
    DOCUMENT = "doc"
    REVISION = "rev"

    # Metric entities
    METRIC = "met"


# Reverse mapping for parsing
_PREFIX_TO_TYPE = {t.value: t for t in EntityType}


def generate_id(entity_type: EntityType) -> str:
    """Generate a new typed ID.

    Args:
        entity_type: Type of entity

    Returns:
        Prefixed UUID string

    Example:
        >>> generate_id(EntityType.TASK)
        'task_a1b2c3d4-e5f6-7890-abcd-ef1234567890'
    """
    return f"{entity_type.value}_{uuid.uuid4()}"


def generate_id_with_timestamp(entity_type: EntityType) -> tuple[str, datetime]:
    """Generate ID with creation timestamp.

    Args:
        entity_type: Type of entity

    Returns:
        Tuple of (id, timestamp)
    """
    ts = datetime.now(UTC)
    return f"{entity_type.value}_{uuid.uuid4()}", ts


def parse_id(entity_id: str) -> tuple[EntityType | None, str]:
    """Parse a typed ID into its components.

    Args:
        entity_id: The ID to parse

    Returns:
        Tuple of (entity_type, uuid_part)
        entity_type is None if prefix is unknown

    Example:
        >>> parse_id('task_a1b2c3d4-e5f6-7890-abcd-ef1234567890')
        (EntityType.TASK, 'a1b2c3d4-e5f6-7890-abcd-ef1234567890')
    """
    if "_" not in entity_id:
        return None, entity_id

    prefix, uuid_part = entity_id.split("_", 1)
    entity_type = _PREFIX_TO_TYPE.get(prefix)

    return entity_type, uuid_part


def get_entity_type(entity_id: str) -> EntityType | None:
    """Get the entity type from an ID.

    Args:
        entity_id: The ID to check

    Returns:
        EntityType or None if unknown
    """
    entity_type, _ = parse_id(entity_id)
    return entity_type


def get_prefix(entity_id: str) -> str:
    """Get the prefix from an ID.

    Args:
        entity_id: The ID to check

    Returns:
        Prefix string
    """
    if "_" not in entity_id:
        return ""
    return entity_id.split("_", 1)[0]


def is_valid_id(entity_id: str, expected_type: EntityType | None = None) -> bool:
    """Check if an ID is valid.

    Args:
        entity_id: ID to validate
        expected_type: Optional expected type

    Returns:
        True if valid
    """
    entity_type, uuid_part = parse_id(entity_id)

    # Must have a recognized type
    if entity_type is None:
        return False

    # If expected type specified, must match
    if expected_type is not None and entity_type != expected_type:
        return False

    # UUID part should be valid UUID format
    try:
        uuid.UUID(uuid_part)
        return True
    except ValueError:
        return False


def is_type(entity_id: str, *types: EntityType) -> bool:
    """Check if ID is one of the specified types.

    Args:
        entity_id: ID to check
        *types: Expected types

    Returns:
        True if ID matches any of the types

    Example:
        >>> is_type(task_id, EntityType.TASK, EntityType.PROJECT)
        True
    """
    entity_type = get_entity_type(entity_id)
    return entity_type in types


def extract_uuid(entity_id: str) -> str:
    """Extract just the UUID part from an ID.

    Args:
        entity_id: Full entity ID

    Returns:
        UUID part only
    """
    _, uuid_part = parse_id(entity_id)
    return uuid_part


def same_entity(id1: str, id2: str) -> bool:
    """Check if two IDs refer to the same entity.

    Args:
        id1: First ID
        id2: Second ID

    Returns:
        True if same entity
    """
    return id1 == id2


def entities_related(id1: str, id2: str) -> bool:
    """Check if two IDs might be related (same UUID base).

    This can happen when entities share lineage.

    Args:
        id1: First ID
        id2: Second ID

    Returns:
        True if potentially related
    """
    return extract_uuid(id1) == extract_uuid(id2)


# =============================================================================
# ID Collections and Utilities
# =============================================================================


class IDSet:
    """A set of entity IDs with type filtering.

    Useful for tracking collections of entities across types.
    """

    def __init__(self) -> None:
        self._ids: set[str] = set()

    def add(self, entity_id: str) -> None:
        """Add an ID to the set."""
        self._ids.add(entity_id)

    def remove(self, entity_id: str) -> bool:
        """Remove an ID from the set."""
        if entity_id in self._ids:
            self._ids.discard(entity_id)
            return True
        return False

    def contains(self, entity_id: str) -> bool:
        """Check if ID is in set."""
        return entity_id in self._ids

    def get_by_type(self, entity_type: EntityType) -> set[str]:
        """Get all IDs of a specific type."""
        return {id for id in self._ids if get_entity_type(id) == entity_type}

    def filter_types(self, *types: EntityType) -> set[str]:
        """Get IDs matching any of the specified types."""
        return {id for id in self._ids if get_entity_type(id) in types}

    def all(self) -> set[str]:
        """Get all IDs."""
        return set(self._ids)

    def __len__(self) -> int:
        return len(self._ids)

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self._ids)

    def __contains__(self, item: str) -> bool:
        return item in self._ids
