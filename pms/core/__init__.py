"""Core Infrastructure for PMS.

This module provides foundational infrastructure used by all other modules:
- Unified ID utilities plus explicit runtime ID-contract helpers
- Reference System: Cross-entity relationship tracking
- Entity Registry: Central entity discovery and lifecycle management
- Platform Integration: Unified access to all subsystems
- Event Sourcing: Append-only state management
- Metrics: Operation timing and tracking
- Revisions: Entity version history

Architecture:
    ┌─────────────────────────────────────────────────────────────────┐
    │                      Core Infrastructure                         │
    │  ┌───────────┐  ┌───────────┐  ┌────────────┐  ┌────────────┐  │
    │  │ ID System │  │References │  │  Registry  │  │  Platform  │  │
    │  │ (ids.py)  │  │ (refs.py) │  │(registry.py│  │(platform.py│  │
    │  └───────────┘  └───────────┘  └────────────┘  └────────────┘  │
    │  ┌───────────┐  ┌───────────┐  ┌────────────┐                  │
    │  │  Events   │  │  Metrics  │  │ Revisions  │                  │
    │  │(events.py)│  │(metrics.py│  │(revisions. │                  │
    │  └───────────┘  └───────────┘  └────────────┘                  │
    └─────────────────────────────────────────────────────────────────┘

ID Format:
    PMS currently exposes two related but different concepts:
    - namespace/prefix utilities for typed IDs such as proj_xxx or wf_xxx
    - runtime entity IDs, which remain UUID-native for most public stored
      entities and are explicitly described by pms.core.id_contract

Usage:
    from pms.core import (
        generate_id, EntityType,          # ID system
        Reference, ReferenceStore,        # References
        EntityRegistry, get_entity_registry,  # Registry
        Platform, get_platform,           # Platform integration
    )

    # Generate typed IDs
    task_id = generate_id(EntityType.TASK)

    # Track relationships
    await references.add(Reference(
        source_id=task_id,
        target_id=workflow_id,
        relation=ReferenceType.TRIGGERED_BY,
    ))

    # Use unified platform
    platform = get_platform()
    await platform.emit_task_completed(task_id)
"""

# Event sourcing
from pms.core.events import (
    DomainEvent,
    EventMetadata,
    EventStore,
    EventType,
)

# Unified ID system
from pms.core.id_contract import (
    INTERNAL_PREFIX_NATIVE_ENTITY_TYPES,
    PUBLIC_ENTITY_ID_STYLES,
    prefix_native_public_entity_types,
    public_entity_id_style,
    uuid_native_public_entity_types,
    validate_public_entity_id_style_coverage,
)
from pms.core.ids import (
    EntityType,
    IDSet,
    extract_uuid,
    generate_id,
    generate_id_with_timestamp,
    get_entity_type,
    get_prefix,
    is_type,
    is_valid_id,
    parse_id,
)

# Self-documentation and introspection
from pms.core.introspection import (
    Capability,
    SystemIntrospector,
    get_capabilities,
    get_full_documentation,
    get_health_status,
    get_introspector,
    get_system_info,
    get_system_schema,
)

# Metrics
from pms.core.metrics import (
    Metric,
    MetricsCollector,
    MetricType,
    OperationTimer,
)

# Pluggable namespace system
from pms.core.namespace import (
    Namespace,
    NamespaceRegistry,
    generate_id_for_namespace,
    get_namespace,
    get_namespace_documentation,
    get_namespace_registry,
    get_namespace_schema,
    list_namespaces,
    register_namespace,
    set_namespace_registry,
    unregister_namespace,
)

# Platform integration
from pms.core.platform import (
    Platform,
    PlatformConfig,
    get_platform,
    set_platform,
)

# Reference system
from pms.core.refs import (
    Reference,
    ReferenceStore,
    ReferenceType,
    get_inverse_relation,
    get_reference_store,
    set_reference_store,
)

# Entity registry
from pms.core.registry import (
    EntityInfo,
    EntityRegistry,
    EntityStatus,
    get_entity_registry,
    set_entity_registry,
)

# Revisions
from pms.core.revisions import (
    Revision,
    RevisionStore,
    Snapshot,
)

__all__ = [
    # Event sourcing
    "DomainEvent",
    "EventMetadata",
    "EventStore",
    "EventType",
    # Metrics
    "Metric",
    "MetricType",
    "MetricsCollector",
    "OperationTimer",
    # Revisions
    "Revision",
    "RevisionStore",
    "Snapshot",
    # Unified ID system
    "EntityType",
    "PUBLIC_ENTITY_ID_STYLES",
    "INTERNAL_PREFIX_NATIVE_ENTITY_TYPES",
    "public_entity_id_style",
    "prefix_native_public_entity_types",
    "uuid_native_public_entity_types",
    "validate_public_entity_id_style_coverage",
    "generate_id",
    "generate_id_with_timestamp",
    "parse_id",
    "get_entity_type",
    "get_prefix",
    "is_valid_id",
    "is_type",
    "extract_uuid",
    "IDSet",
    # Reference system
    "Reference",
    "ReferenceType",
    "ReferenceStore",
    "get_reference_store",
    "set_reference_store",
    "get_inverse_relation",
    # Entity registry
    "EntityInfo",
    "EntityStatus",
    "EntityRegistry",
    "get_entity_registry",
    "set_entity_registry",
    # Platform integration
    "Platform",
    "PlatformConfig",
    "get_platform",
    "set_platform",
    # Pluggable namespace system
    "Namespace",
    "NamespaceRegistry",
    "get_namespace_registry",
    "set_namespace_registry",
    "register_namespace",
    "unregister_namespace",
    "get_namespace",
    "generate_id_for_namespace",
    "list_namespaces",
    "get_namespace_schema",
    "get_namespace_documentation",
    # Self-documentation and introspection
    "Capability",
    "SystemIntrospector",
    "get_introspector",
    "get_system_info",
    "get_capabilities",
    "get_system_schema",
    "get_full_documentation",
    "get_health_status",
]
