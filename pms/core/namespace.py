"""Pluggable Namespace System - Dynamic entity type registration.

This module enables:
- Dynamic registration of new entity types (namespaces)
- Plugin-based namespace extensions
- Self-documenting namespace schema
- Namespace discovery and introspection

Usage:
    from pms.core.namespace import (
        NamespaceRegistry,
        Namespace,
        register_namespace,
        get_namespace,
    )

    # Register a custom namespace
    register_namespace(Namespace(
        prefix="cust",
        name="custom_entity",
        description="My custom entity type",
        module="my_plugin",
        schema={
            "fields": ["name", "value"],
            "required": ["name"],
        },
    ))

    # Generate IDs for custom type
    from pms.core import generate_id_for_namespace
    custom_id = generate_id_for_namespace("cust")  # "cust_xxx..."

    # Discover all namespaces
    registry = get_namespace_registry()
    for ns in registry.list_all():
        print(f"{ns.prefix}: {ns.description}")
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Namespace:
    """A registered namespace (entity type).

    Attributes:
        prefix: Short prefix for IDs (e.g., "proj", "task")
        name: Full name (e.g., "project", "task")
        description: Human-readable description
        module: Module that registered this namespace
        version: Namespace version
        schema: Optional JSON schema for validation
        metadata: Additional metadata
        validators: Custom validation functions
        created_at: When registered
        is_builtin: Whether this is a built-in namespace
    """

    prefix: str
    name: str
    description: str = ""
    module: str = "pms.core"
    version: str = "1.0.0"
    schema: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    validators: list[Callable[[str, Any], bool]] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    is_builtin: bool = False

    def generate_id(self) -> str:
        """Generate a new ID for this namespace."""
        return f"{self.prefix}_{uuid.uuid4()}"

    def is_valid_id(self, entity_id: str) -> bool:
        """Check if an ID belongs to this namespace."""
        return entity_id.startswith(f"{self.prefix}_")

    def validate(self, entity_id: str, data: Any = None) -> tuple[bool, str]:
        """Validate an entity ID and optional data.

        Returns:
            (is_valid, error_message)
        """
        if not self.is_valid_id(entity_id):
            return False, f"ID must start with '{self.prefix}_'"

        # Run custom validators
        for validator in self.validators:
            try:
                if not validator(entity_id, data):
                    return False, f"Custom validation failed"
            except Exception as e:
                return False, f"Validation error: {e}"

        return True, ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "prefix": self.prefix,
            "name": self.name,
            "description": self.description,
            "module": self.module,
            "version": self.version,
            "schema": self.schema,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "is_builtin": self.is_builtin,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Namespace:
        """Create from dictionary."""
        return cls(
            prefix=data["prefix"],
            name=data["name"],
            description=data.get("description", ""),
            module=data.get("module", "unknown"),
            version=data.get("version", "1.0.0"),
            schema=data.get("schema", {}),
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"])
            if "created_at" in data
            else datetime.now(UTC),
            is_builtin=data.get("is_builtin", False),
        )


class NamespaceRegistry:
    """Registry for all namespaces in the system.

    Features:
    - Register/unregister namespaces dynamically
    - Discover all available namespaces
    - Generate schema documentation
    - Plugin integration
    """

    def __init__(self, storage_path: Path | str | None = None):
        """Initialize namespace registry.

        Args:
            storage_path: Optional path for persistence
        """
        self._namespaces: dict[str, Namespace] = {}
        self._by_name: dict[str, Namespace] = {}
        self._storage_path = Path(storage_path) if storage_path else None
        self._change_listeners: list[Callable[[str, Namespace, str], None]] = []

        # Register built-in namespaces
        self._register_builtins()

        # Load custom namespaces
        if self._storage_path and self._storage_path.exists():
            self._load()

    def _register_builtins(self) -> None:
        """Register built-in namespaces."""
        builtins = [
            # Core entities
            Namespace(
                prefix="org",
                name="organization",
                description="Organization containers and ownership",
                is_builtin=True,
                schema={
                    "fields": ["name", "description", "owner", "members", "status"],
                    "required": ["name"],
                },
            ),
            Namespace(
                prefix="team",
                name="team",
                description="Organization teams and membership",
                is_builtin=True,
                schema={
                    "fields": ["org_id", "name", "description", "members", "status"],
                    "required": ["name"],
                },
            ),
            Namespace(
                prefix="port",
                name="portfolio",
                description="Portfolio grouping of projects and goals",
                is_builtin=True,
                schema={
                    "fields": [
                        "name",
                        "description",
                        "project_ids",
                        "goal_ids",
                        "objective_ids",
                        "effective_goal_ids",
                        "effective_objective_ids",
                        "status",
                    ],
                    "required": ["name"],
                    "field_notes": {
                        "project_ids": "Bulk scope-assignment input; portfolio readbacks expose authoritative project membership from child project foreign keys.",
                        "goal_ids": "Direct portfolio-to-goal strategic links stored through native edge tables.",
                        "objective_ids": "Direct portfolio-to-objective strategic links stored through native edge tables.",
                        "effective_goal_ids": "Hydrated scope readback only: direct goal links plus project-derived goal scope.",
                        "effective_objective_ids": "Hydrated scope readback only: direct objective links plus project-derived objective scope.",
                    },
                },
            ),
            Namespace(
                prefix="prog",
                name="program",
                description="Program grouping under a portfolio",
                is_builtin=True,
                schema={
                    "fields": [
                        "name",
                        "description",
                        "portfolio_id",
                        "project_ids",
                        "goal_ids",
                        "objective_ids",
                        "effective_goal_ids",
                        "effective_objective_ids",
                        "status",
                    ],
                    "required": ["name"],
                    "field_notes": {
                        "project_ids": "Bulk scope-assignment input; program readbacks expose authoritative project membership from child project foreign keys.",
                        "goal_ids": "Direct program-to-goal strategic links stored through native edge tables.",
                        "objective_ids": "Direct program-to-objective strategic links stored through native edge tables.",
                        "effective_goal_ids": "Hydrated scope readback only: direct goal links plus project-derived goal scope.",
                        "effective_objective_ids": "Hydrated scope readback only: direct objective links plus project-derived objective scope.",
                    },
                },
            ),
            Namespace(
                prefix="proj",
                name="project",
                description="Project containers",
                is_builtin=True,
                schema={
                    "fields": ["name", "description", "status"],
                    "required": ["name"],
                },
            ),
            Namespace(
                prefix="goal",
                name="goal",
                description="Strategic goals with time horizons",
                is_builtin=True,
                schema={
                    "fields": ["name", "description", "status", "horizon"],
                    "required": ["name", "horizon"],
                },
            ),
            Namespace(
                prefix="obj",
                name="objective",
                description="Goal objectives with measurable outcomes",
                is_builtin=True,
                schema={
                    "fields": ["goal_id", "name", "description", "status"],
                    "required": ["goal_id", "name"],
                },
            ),
            Namespace(
                prefix="plan",
                name="plan",
                description="Plan artifacts for execution and decomposition",
                is_builtin=True,
                schema={
                    "fields": [
                        "name",
                        "description",
                        "format",
                        "content",
                        "project_id",
                        "task_ids",
                    ],
                    "required": ["name", "format", "content"],
                },
            ),
            Namespace(
                prefix="kr",
                name="key_result",
                description="Objective key results with measurable targets",
                is_builtin=True,
                schema={
                    "fields": ["objective_id", "name", "status", "target_value"],
                    "required": ["objective_id", "name"],
                },
            ),
            Namespace(
                prefix="task",
                name="task",
                description="Work items and subtasks",
                is_builtin=True,
                schema={
                    "fields": ["title", "description", "status", "priority"],
                    "required": ["title"],
                },
            ),
            Namespace(
                prefix="mile",
                name="milestone",
                description="Project milestones",
                is_builtin=True,
                schema={"fields": ["name", "due_date", "status"], "required": ["name"]},
            ),
            Namespace(
                prefix="tag", name="tag", description="Entity tags", is_builtin=True
            ),
            Namespace(
                prefix="apikey",
                name="api_key",
                description="API keys and authentication credentials",
                is_builtin=True,
                schema={
                    "fields": [
                        "name",
                        "scopes",
                        "rate_limit",
                        "expires_at",
                        "is_active",
                    ],
                    "required": ["name", "scopes"],
                },
            ),
            # Remote/AWS entities
            Namespace(
                prefix="host",
                name="remote_host",
                description="SSH remote hosts",
                is_builtin=True,
                schema={
                    "fields": ["name", "hostname", "username"],
                    "required": ["name", "hostname"],
                },
            ),
            Namespace(
                prefix="srv",
                name="test_server",
                description="AWS test servers",
                is_builtin=True,
            ),
            Namespace(
                prefix="trun",
                name="test_run",
                description="Test execution runs",
                is_builtin=True,
            ),
            # Automation entities
            Namespace(
                prefix="wf",
                name="workflow",
                description="Workflow definitions",
                is_builtin=True,
                schema={
                    "fields": ["name", "description", "steps"],
                    "required": ["name", "steps"],
                },
            ),
            Namespace(
                prefix="wfrun",
                name="workflow_run",
                description="Workflow executions",
                is_builtin=True,
            ),
            Namespace(
                prefix="step",
                name="workflow_step",
                description="Workflow steps",
                is_builtin=True,
            ),
            Namespace(
                prefix="evt", name="event", description="System events", is_builtin=True
            ),
            Namespace(
                prefix="trig",
                name="trigger",
                description="Workflow triggers",
                is_builtin=True,
            ),
            # Memory entities
            Namespace(
                prefix="know",
                name="knowledge",
                description="Knowledge entries",
                is_builtin=True,
                schema={
                    "fields": ["type", "title", "content", "tags"],
                    "required": ["type", "title"],
                },
            ),
            Namespace(
                prefix="pat",
                name="pattern",
                description="Reusable patterns",
                is_builtin=True,
            ),
            Namespace(
                prefix="fb",
                name="feedback",
                description="Feedback signals",
                is_builtin=True,
            ),
            Namespace(
                prefix="ctx",
                name="context",
                description="Context sessions",
                is_builtin=True,
            ),
            Namespace(
                prefix="ctxi",
                name="context_item",
                description="Context items",
                is_builtin=True,
            ),
            # Learning entities
            Namespace(
                prefix="out",
                name="outcome",
                description="Operation outcomes",
                is_builtin=True,
            ),
            Namespace(
                prefix="sug",
                name="suggestion",
                description="System suggestions",
                is_builtin=True,
            ),
            # Reference/relation entities
            Namespace(
                prefix="ref",
                name="reference",
                description="Entity relationships",
                is_builtin=True,
                schema={
                    "fields": ["source_id", "target_id", "relation"],
                    "required": ["source_id", "target_id", "relation"],
                },
            ),
            Namespace(
                prefix="dep",
                name="dependency",
                description="Task dependencies",
                is_builtin=True,
            ),
            # Session entities
            Namespace(
                prefix="sess",
                name="session",
                description="User sessions",
                is_builtin=True,
            ),
            # Document entities
            Namespace(
                prefix="doc", name="document", description="Documents", is_builtin=True
            ),
            Namespace(
                prefix="rev",
                name="revision",
                description="Entity revisions",
                is_builtin=True,
            ),
            # Metric entities
            Namespace(
                prefix="met", name="metric", description="Metrics", is_builtin=True
            ),
        ]

        for ns in builtins:
            self._namespaces[ns.prefix] = ns
            self._by_name[ns.name] = ns

    def register(self, namespace: Namespace) -> str:
        """Register a new namespace.

        Args:
            namespace: Namespace to register

        Returns:
            Namespace prefix

        Raises:
            ValueError: If prefix or name already exists
        """
        if namespace.prefix in self._namespaces:
            existing = self._namespaces[namespace.prefix]
            if existing.is_builtin:
                raise ValueError(
                    f"Cannot override built-in namespace: {namespace.prefix}"
                )
            logger.warning(f"Overwriting namespace: {namespace.prefix}")

        if namespace.name in self._by_name:
            existing = self._by_name[namespace.name]
            if existing.is_builtin:
                raise ValueError(
                    f"Cannot override built-in namespace name: {namespace.name}"
                )

        self._namespaces[namespace.prefix] = namespace
        self._by_name[namespace.name] = namespace

        logger.info(
            f"Registered namespace: {namespace.prefix} ({namespace.name}) from {namespace.module}"
        )

        # Notify listeners
        for listener in self._change_listeners:
            try:
                listener(namespace.prefix, namespace, "registered")
            except Exception as e:
                logger.error(f"Listener error: {e}")

        self._save()
        return namespace.prefix

    def unregister(self, prefix: str) -> bool:
        """Unregister a namespace.

        Args:
            prefix: Namespace prefix to remove

        Returns:
            True if found and removed
        """
        ns = self._namespaces.get(prefix)
        if not ns:
            return False

        if ns.is_builtin:
            raise ValueError(f"Cannot unregister built-in namespace: {prefix}")

        del self._namespaces[prefix]
        self._by_name.pop(ns.name, None)

        # Notify listeners
        for listener in self._change_listeners:
            try:
                listener(prefix, ns, "unregistered")
            except Exception as e:
                logger.error(f"Listener error: {e}")

        self._save()
        return True

    def get(self, prefix: str) -> Namespace | None:
        """Get namespace by prefix."""
        return self._namespaces.get(prefix)

    def get_by_name(self, name: str) -> Namespace | None:
        """Get namespace by name."""
        return self._by_name.get(name)

    def exists(self, prefix: str) -> bool:
        """Check if namespace exists."""
        return prefix in self._namespaces

    def list_all(self, include_builtin: bool = True) -> list[Namespace]:
        """List all namespaces.

        Args:
            include_builtin: Whether to include built-in namespaces

        Returns:
            List of namespaces
        """
        namespaces = list(self._namespaces.values())
        if not include_builtin:
            namespaces = [ns for ns in namespaces if not ns.is_builtin]
        return sorted(namespaces, key=lambda ns: ns.prefix)

    def list_prefixes(self) -> list[str]:
        """List all namespace prefixes."""
        return sorted(self._namespaces.keys())

    def generate_id(self, prefix: str) -> str:
        """Generate ID for a namespace.

        Args:
            prefix: Namespace prefix

        Returns:
            New ID

        Raises:
            ValueError: If namespace not found
        """
        ns = self._namespaces.get(prefix)
        if not ns:
            raise ValueError(f"Unknown namespace: {prefix}")
        return ns.generate_id()

    def parse_id(self, entity_id: str) -> tuple[Namespace | None, str]:
        """Parse an ID to get namespace and UUID.

        Args:
            entity_id: Entity ID to parse

        Returns:
            (namespace, uuid_part)
        """
        if "_" not in entity_id:
            return None, entity_id

        prefix, uuid_part = entity_id.split("_", 1)
        return self._namespaces.get(prefix), uuid_part

    def get_namespace_for_id(self, entity_id: str) -> Namespace | None:
        """Get namespace for an ID."""
        ns, _ = self.parse_id(entity_id)
        return ns

    def add_change_listener(
        self, listener: Callable[[str, Namespace, str], None]
    ) -> None:
        """Add a namespace change listener.

        Args:
            listener: Callback(prefix, namespace, change_type)
        """
        self._change_listeners.append(listener)

    # -------------------------------------------------------------------------
    # Schema & Documentation
    # -------------------------------------------------------------------------

    def get_schema(self) -> dict[str, Any]:
        """Get full schema documentation for all namespaces.

        Returns:
            Schema dictionary
        """
        from pms.core.id_contract import namespace_id_contract

        return {
            "version": "1.0.0",
            "namespaces": {
                ns.prefix: {
                    "name": ns.name,
                    "description": ns.description,
                    "module": ns.module,
                    "version": ns.version,
                    "schema": ns.schema,
                    "is_builtin": ns.is_builtin,
                    **namespace_id_contract(ns.prefix, ns.name),
                }
                for ns in self._namespaces.values()
            },
        }

    def get_documentation(self) -> str:
        """Generate human-readable documentation.

        Returns:
            Markdown documentation
        """
        lines = [
            "# PMS Namespace Registry",
            "",
            "## Available Namespaces",
            "",
            "| Prefix | Name | Description | Module |",
            "|--------|------|-------------|--------|",
        ]

        for ns in sorted(self._namespaces.values(), key=lambda n: n.prefix):
            builtin = " (built-in)" if ns.is_builtin else ""
            lines.append(
                f"| `{ns.prefix}` | {ns.name} | {ns.description}{builtin} | {ns.module} |"
            )

        lines.extend(
            [
                "",
                "## ID Format",
                "",
                "Namespace-generated IDs follow the format: `{prefix}_{uuid}`",
                "",
                "This registry documents typed-ID utilities for namespace-backed families.",
                "It is not the full runtime row-ID contract for every public entity family.",
                "Some public entities remain UUID-native even when they participate in other",
                "machine-readable capability surfaces.",
                "",
                "Examples:",
            ]
        )

        for ns in sorted(self._namespaces.values(), key=lambda n: n.prefix)[:5]:
            example_id = ns.generate_id()
            lines.append(f"- `{example_id}` ({ns.name})")

        lines.extend(
            [
                "",
                "## Registering Custom Namespaces",
                "",
                "```python",
                "from pms.core.namespace import register_namespace, Namespace",
                "",
                "register_namespace(Namespace(",
                '    prefix="myns",',
                '    name="my_entity",',
                '    description="My custom entity type",',
                '    module="my_plugin",',
                "    schema={",
                '        "fields": ["name", "value"],',
                '        "required": ["name"],',
                "    },",
                "))",
                "```",
            ]
        )

        return "\n".join(lines)

    # -------------------------------------------------------------------------
    # Persistence
    # -------------------------------------------------------------------------

    def _save(self) -> None:
        """Save custom namespaces to disk."""
        if not self._storage_path:
            return

        self._storage_path.parent.mkdir(parents=True, exist_ok=True)

        # Only save non-builtin namespaces
        custom = [ns.to_dict() for ns in self._namespaces.values() if not ns.is_builtin]

        data = {
            "version": 1,
            "namespaces": custom,
        }

        with self._storage_path.open("w") as f:
            json.dump(data, f, indent=2)

    def _load(self) -> None:
        """Load custom namespaces from disk."""
        if not self._storage_path or not self._storage_path.exists():
            return

        try:
            with self._storage_path.open() as f:
                data = json.load(f)

            for ns_data in data.get("namespaces", []):
                ns = Namespace.from_dict(ns_data)
                self._namespaces[ns.prefix] = ns
                self._by_name[ns.name] = ns

            logger.info(f"Loaded {len(data.get('namespaces', []))} custom namespaces")

        except Exception as e:
            logger.error(f"Failed to load namespaces: {e}")


# =============================================================================
# Global Instance & Convenience Functions
# =============================================================================

_global_registry: NamespaceRegistry | None = None


def get_namespace_registry() -> NamespaceRegistry:
    """Get the global namespace registry."""
    global _global_registry
    if _global_registry is None:
        _global_registry = NamespaceRegistry()
    return _global_registry


def set_namespace_registry(registry: NamespaceRegistry) -> None:
    """Set the global namespace registry."""
    global _global_registry
    _global_registry = registry


def register_namespace(namespace: Namespace) -> str:
    """Register a namespace in the global registry."""
    return get_namespace_registry().register(namespace)


def unregister_namespace(prefix: str) -> bool:
    """Unregister a namespace from the global registry."""
    return get_namespace_registry().unregister(prefix)


def get_namespace(prefix: str) -> Namespace | None:
    """Get a namespace from the global registry."""
    return get_namespace_registry().get(prefix)


def generate_id_for_namespace(prefix: str) -> str:
    """Generate ID for a namespace."""
    return get_namespace_registry().generate_id(prefix)


def list_namespaces() -> list[Namespace]:
    """List all namespaces."""
    return get_namespace_registry().list_all()


def get_namespace_schema() -> dict[str, Any]:
    """Get namespace schema documentation."""
    return get_namespace_registry().get_schema()


def get_namespace_documentation() -> str:
    """Get human-readable namespace documentation."""
    return get_namespace_registry().get_documentation()
