"""Self-Documentation and Introspection System.

This module provides:
- System-wide capability discovery
- Auto-generated documentation
- Schema introspection
- Health and status reporting

Usage:
    from pms.core.introspection import (
        SystemIntrospector,
        get_system_info,
        get_capabilities,
        get_full_documentation,
    )

    # Get system info
    info = get_system_info()
    print(f"PMS v{info['version']} with {info['total_capabilities']} capabilities")

    # Discover capabilities
    caps = get_capabilities()
    for cap in caps['namespaces']:
        print(f"  - {cap['prefix']}: {cap['description']}")

    # Generate full documentation
    docs = get_full_documentation()
    print(docs)  # Markdown documentation
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pms import __version__

logger = logging.getLogger(__name__)


@dataclass
class Capability:
    """A discoverable capability in the system.

    Attributes:
        name: Capability name
        category: Category (namespace, tool, workflow, pattern, etc.)
        description: Human-readable description
        module: Source module
        version: Capability version
        schema: Optional schema
        examples: Usage examples
        metadata: Additional metadata
    """

    name: str
    category: str
    description: str
    module: str = ""
    version: str = __version__
    schema: dict[str, Any] = field(default_factory=dict)
    examples: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "module": self.module,
            "version": self.version,
            "schema": self.schema,
            "examples": self.examples,
            "metadata": self.metadata,
        }


class SystemIntrospector:
    """Introspects the PMS system to discover capabilities.

    Features:
    - Discover all namespaces
    - Discover all tools
    - Discover all patterns
    - Discover all event types
    - Generate unified documentation
    """

    def __init__(self) -> None:
        """Initialize introspector."""
        self._cache: dict[str, Any] = {}
        self._cache_time: datetime | None = None
        self._cache_ttl_seconds = 60

    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid."""
        if not self._cache_time:
            return False
        age = (datetime.now(UTC) - self._cache_time).total_seconds()
        return age < self._cache_ttl_seconds

    def get_system_info(self) -> dict[str, Any]:
        """Get basic system information.

        Returns:
            System info dictionary with capability counts by category
        """
        caps = self.get_capabilities()

        # Build capability counts by category
        capability_counts = {
            key: len(caps.get(key, []))
            for key in [
                "namespaces",
                "tools",
                "patterns",
                "event_types",
                "reference_types",
                "knowledge_types",
                "feedback_categories",
            ]
        }

        return {
            "name": "PMS - Project Management System",
            "version": __version__,
            "description": "Self-evolving autonomous development platform",
            "modules": [
                "pms.core",
                "pms.automation",
                "pms.memory",
                "pms.learning",
                "pms.services",
                "pms.tools",
            ],
            "capabilities": capability_counts,
            "total_capabilities": sum(capability_counts.values()),
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def get_capabilities(self) -> dict[str, list[dict[str, Any]]]:
        """Get all system capabilities.

        Returns:
            Dictionary of capability lists by category
        """
        if self._is_cache_valid() and "capabilities" in self._cache:
            cached_caps: dict[str, list[dict[str, Any]]] = self._cache["capabilities"]
            return cached_caps

        capabilities = {
            "namespaces": self._discover_namespaces(),
            "tools": self._discover_tools(),
            "patterns": self._discover_patterns(),
            "event_types": self._discover_event_types(),
            "reference_types": self._discover_reference_types(),
            "knowledge_types": self._discover_knowledge_types(),
            "feedback_categories": self._discover_feedback_categories(),
        }

        self._cache["capabilities"] = capabilities
        self._cache_time = datetime.now(UTC)

        return capabilities

    def _discover_namespaces(self) -> list[dict[str, Any]]:
        """Discover all namespaces."""
        try:
            from pms.core.id_contract import namespace_id_contract
            from pms.core.namespace import get_namespace_registry

            registry = get_namespace_registry()
            return [
                {
                    "prefix": ns.prefix,
                    "name": ns.name,
                    "description": ns.description,
                    "module": ns.module,
                    "is_builtin": ns.is_builtin,
                    "schema": ns.schema,
                    **namespace_id_contract(ns.prefix, ns.name),
                }
                for ns in registry.list_all()
            ]
        except Exception as e:
            logger.warning(f"Failed to discover namespaces: {e}")
            return []

    def _discover_tools(self) -> list[dict[str, Any]]:
        """Discover all MCP tools."""
        try:
            from pms.tools import ALL_PROJECT_TOOLS, ALL_REMOTE_TOOLS

            tools = list(ALL_PROJECT_TOOLS) + list(ALL_REMOTE_TOOLS)

            # Try to add AWS tools if available
            try:
                from pms.tools import ALL_AWS_TOOLS

                tools.extend(ALL_AWS_TOOLS)
            except ImportError:
                pass

            return [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "category": self._categorize_tool(tool.name),
                }
                for tool in tools
            ]
        except Exception as e:
            logger.warning(f"Failed to discover tools: {e}")
            return []

    def _categorize_tool(self, tool_name: str) -> str:
        """Categorize a tool by name."""
        if "project" in tool_name or tool_name in ["create_project", "list_projects"]:
            return "project"
        elif "task" in tool_name:
            return "task"
        elif "remote" in tool_name or "sync" in tool_name or "ssh" in tool_name:
            return "remote"
        elif "spot" in tool_name or "server" in tool_name or "aws" in tool_name:
            return "aws"
        return "general"

    def _discover_patterns(self) -> list[dict[str, Any]]:
        """Discover all patterns."""
        try:
            from pms.memory import get_pattern_matcher

            matcher = get_pattern_matcher()
            return [
                {
                    "name": p.name,
                    "type": p.type.value,
                    "description": p.description,
                    "triggers": p.triggers,
                    "use_count": p.use_count,
                }
                for p in matcher.list_patterns()
            ]
        except Exception as e:
            logger.warning(f"Failed to discover patterns: {e}")
            return []

    def _discover_event_types(self) -> list[dict[str, Any]]:
        """Discover all event types."""
        try:
            from pms.automation.events import EventType

            return [
                {
                    "name": et.name,
                    "value": et.value,
                    "category": et.value.split(".")[0],
                }
                for et in EventType
            ]
        except Exception as e:
            logger.warning(f"Failed to discover event types: {e}")
            return []

    def _discover_reference_types(self) -> list[dict[str, Any]]:
        """Discover all reference types."""
        try:
            from pms.core.refs import ReferenceType, get_inverse_relation

            result = []
            for rt in ReferenceType:
                inverse_rel = get_inverse_relation(rt)
                result.append(
                    {
                        "name": rt.name,
                        "value": rt.value,
                        "inverse": inverse_rel.value if inverse_rel else None,
                    }
                )
            return result
        except Exception as e:
            logger.warning(f"Failed to discover reference types: {e}")
            return []

    def _discover_knowledge_types(self) -> list[dict[str, Any]]:
        """Discover all knowledge types."""
        try:
            from pms.memory.knowledge import KnowledgeType

            return [
                {
                    "name": kt.name,
                    "value": kt.value,
                }
                for kt in KnowledgeType
            ]
        except Exception as e:
            logger.warning(f"Failed to discover knowledge types: {e}")
            return []

    def _discover_feedback_categories(self) -> list[dict[str, Any]]:
        """Discover feedback categories."""
        try:
            from pms.memory.feedback import FeedbackCategory

            return [
                {
                    "name": fc.name,
                    "value": fc.value,
                }
                for fc in FeedbackCategory
            ]
        except Exception as e:
            logger.warning(f"Failed to discover feedback categories: {e}")
            return []

    def get_schema(self) -> dict[str, Any]:
        """Get full system schema.

        Returns:
            Complete schema documentation
        """
        caps = self.get_capabilities()

        return {
            "version": __version__,
            "generated_at": datetime.now(UTC).isoformat(),
            "namespaces": {ns["prefix"]: ns for ns in caps["namespaces"]},
            "tools": {t["name"]: t for t in caps["tools"]},
            "events": {e["value"]: e for e in caps["event_types"]},
            "references": {r["value"]: r for r in caps["reference_types"]},
            "knowledge_types": {k["value"]: k for k in caps["knowledge_types"]},
        }

    def get_documentation(self, format: str = "markdown") -> str:
        """Generate full system documentation.

        Args:
            format: Output format ("markdown" or "text")

        Returns:
            Documentation string
        """
        if format == "markdown":
            return self._generate_markdown_docs()
        return self._generate_text_docs()

    def _generate_markdown_docs(self) -> str:
        """Generate Markdown documentation."""
        caps = self.get_capabilities()
        info = self.get_system_info()

        lines = [
            f"# {info['name']}",
            "",
            f"**Version:** {info['version']}",
            f"**Total Capabilities:** {info['total_capabilities']}",
            "",
            info["description"],
            "",
            "---",
            "",
            "## Namespaces (Entity Types)",
            "",
            "| Prefix | Name | Description |",
            "|--------|------|-------------|",
        ]

        for ns in caps["namespaces"]:
            lines.append(f"| `{ns['prefix']}` | {ns['name']} | {ns['description']} |")

        lines.extend(
            [
                "",
                "Namespace-generated IDs use the typed-ID `{prefix}_{uuid}` format for",
                "families that participate in that utility layer. That registry surface is",
                "separate from the full public runtime row-ID contract.",
            ]
        )

        namespace_details = self._render_namespace_schema_markdown(caps["namespaces"])
        if namespace_details:
            lines.extend(namespace_details)

        lines.extend(
            [
                "",
                "## MCP Tools",
                "",
            ]
        )

        # Group tools by category
        tools_by_cat: dict[str, list[Any]] = {}
        for tool in caps["tools"]:
            cat = tool.get("category", "general")
            if cat not in tools_by_cat:
                tools_by_cat[cat] = []
            tools_by_cat[cat].append(tool)

        for cat, tools in sorted(tools_by_cat.items()):
            lines.append(f"### {cat.title()} Tools")
            lines.append("")
            for tool in tools:
                lines.append(f"- **{tool['name']}**: {tool['description']}")
            lines.append("")

        lines.extend(
            [
                "## Built-in Patterns",
                "",
            ]
        )

        for pattern in caps["patterns"]:
            lines.append(
                f"- **{pattern['name']}** ({pattern['type']}): {pattern['description']}"
            )

        lines.extend(
            [
                "",
                "## Event Types",
                "",
            ]
        )

        # Group events by category
        events_by_cat: dict[str, list[Any]] = {}
        for event in caps["event_types"]:
            cat = event.get("category", "other")
            if cat not in events_by_cat:
                events_by_cat[cat] = []
            events_by_cat[cat].append(event)

        for cat, events in sorted(events_by_cat.items()):
            lines.append(f"### {cat.title()} Events")
            for event in events:
                lines.append(f"- `{event['value']}`")
            lines.append("")

        lines.extend(
            [
                "## Reference Types",
                "",
                "| Type | Inverse |",
                "|------|---------|",
            ]
        )

        for ref in caps["reference_types"]:
            inverse = ref.get("inverse", "-")
            lines.append(f"| `{ref['value']}` | `{inverse}` |")

        lines.extend(
            [
                "",
                "## Knowledge Types",
                "",
            ]
        )

        for kt in caps["knowledge_types"]:
            lines.append(f"- `{kt['value']}`")

        lines.extend(
            [
                "",
                "## Feedback Categories",
                "",
            ]
        )

        for fc in caps["feedback_categories"]:
            lines.append(f"- `{fc['value']}`")

        lines.append("")

        return "\n".join(lines)

    def _generate_text_docs(self) -> str:
        """Generate plain text documentation."""
        caps = self.get_capabilities()
        info = self.get_system_info()

        lines = [
            f"{info['name']}",
            "=" * len(info["name"]),
            "",
            f"Version: {info['version']}",
            f"Total Capabilities: {info['total_capabilities']}",
            "",
            info["description"],
            "",
            "NAMESPACES",
            "-" * 40,
        ]

        for ns in caps["namespaces"]:
            lines.append(f"  {ns['prefix']}: {ns['name']} - {ns['description']}")

        lines.extend(
            [
                "",
                "Namespace-generated IDs use the typed-ID {prefix}_{uuid} format for",
                "families that participate in that utility layer. That registry surface is",
                "separate from the full public runtime row-ID contract.",
            ]
        )

        namespace_details = self._render_namespace_schema_text(caps["namespaces"])
        if namespace_details:
            lines.extend(namespace_details)

        lines.extend(
            [
                "",
                "TOOLS",
                "-" * 40,
            ]
        )

        for tool in caps["tools"]:
            lines.append(f"  {tool['name']}: {tool['description']}")

        return "\n".join(lines)

    def _render_namespace_schema_markdown(
        self, namespaces: list[dict[str, Any]]
    ) -> list[str]:
        """Render namespace schema details for markdown documentation."""
        detailed = [ns for ns in namespaces if ns.get("schema")]
        if not detailed:
            return []

        lines = [
            "",
            "### Namespace Schema Details",
            "",
        ]

        for ns in detailed:
            schema = ns["schema"]
            fields = schema.get("fields", [])
            required = schema.get("required", [])
            field_notes = schema.get("field_notes", {})
            contract_scope = ns.get("runtime_row_id_contract_scope")
            runtime_style = ns.get("runtime_row_id_style")

            lines.append(f"#### `{ns['name']}` (`{ns['prefix']}`)")
            lines.append("")
            lines.append(
                f"- Namespace-generated ID format: `{ns['namespace_generated_id_format']}`"
            )
            if contract_scope:
                lines.append(f"- Runtime row-ID contract scope: `{contract_scope}`")
            lines.append(
                "- Runtime row-ID style: "
                + (f"`{runtime_style}`" if runtime_style else "not applicable")
            )

            if fields:
                lines.append(f"- Fields: {', '.join(f'`{field}`' for field in fields)}")
            if required:
                lines.append(
                    f"- Required: {', '.join(f'`{field}`' for field in required)}"
                )
            if field_notes:
                lines.append("- Field roles:")
                for field in fields:
                    note = field_notes.get(field)
                    if note:
                        lines.append(f"  - `{field}`: {note}")
                for field, note in field_notes.items():
                    if field not in fields:
                        lines.append(f"  - `{field}`: {note}")

            lines.append("")

        return lines

    def _render_namespace_schema_text(
        self, namespaces: list[dict[str, Any]]
    ) -> list[str]:
        """Render namespace schema details for text documentation."""
        detailed = [ns for ns in namespaces if ns.get("schema")]
        if not detailed:
            return []

        lines = [
            "",
            "NAMESPACE SCHEMA DETAILS",
            "-" * 40,
        ]

        for ns in detailed:
            schema = ns["schema"]
            fields = schema.get("fields", [])
            required = schema.get("required", [])
            field_notes = schema.get("field_notes", {})
            contract_scope = ns.get("runtime_row_id_contract_scope")
            runtime_style = ns.get("runtime_row_id_style")

            lines.append(f"  {ns['name']} ({ns['prefix']})")
            lines.append(
                f"    Namespace-generated ID format: {ns['namespace_generated_id_format']}"
            )
            if contract_scope:
                lines.append(f"    Runtime row-ID contract scope: {contract_scope}")
            lines.append(
                "    Runtime row-ID style: " + (runtime_style or "not applicable")
            )
            if fields:
                lines.append(f"    Fields: {', '.join(fields)}")
            if required:
                lines.append(f"    Required: {', '.join(required)}")
            if field_notes:
                lines.append("    Field roles:")
                for field in fields:
                    note = field_notes.get(field)
                    if note:
                        lines.append(f"      - {field}: {note}")
                for field, note in field_notes.items():
                    if field not in fields:
                        lines.append(f"      - {field}: {note}")
            lines.append("")

        return lines

    def get_health_status(self) -> dict[str, Any]:
        """Get system health status.

        Returns:
            Health status dictionary
        """
        status: dict[str, Any] = {
            "healthy": True,
            "timestamp": datetime.now(UTC).isoformat(),
            "components": {},
        }

        # Check core
        try:
            from pms.core.namespace import get_namespace_registry

            registry = get_namespace_registry()
            components: dict[str, Any] = status["components"]
            components["namespace_registry"] = {
                "healthy": True,
                "count": len(registry.list_all()),
            }
        except Exception as e:
            components = status["components"]
            components["namespace_registry"] = {
                "healthy": False,
                "error": str(e),
            }
            status["healthy"] = False

        # Check memory
        try:
            from pms.memory import get_feedback_store, get_knowledge_store

            ks = get_knowledge_store()
            fs = get_feedback_store()
            components = status["components"]
            components["memory"] = {
                "healthy": True,
                "knowledge_entries": ks.get_stats()["total_entries"],
                "feedback_entries": fs.get_stats()["total_feedback"],
            }
        except Exception as e:
            components = status["components"]
            components["memory"] = {"healthy": False, "error": str(e)}
            status["healthy"] = False

        # Check learning
        try:
            from pms.learning import get_learning_engine

            engine = get_learning_engine()
            components = status["components"]
            components["learning"] = {
                "healthy": True,
                "stats": engine.get_stats(),
            }
        except Exception as e:
            components = status["components"]
            components["learning"] = {"healthy": False, "error": str(e)}
            status["healthy"] = False

        return status


# =============================================================================
# Global Instance & Convenience Functions
# =============================================================================

_global_introspector: SystemIntrospector | None = None


def get_introspector() -> SystemIntrospector:
    """Get the global system introspector."""
    global _global_introspector
    if _global_introspector is None:
        _global_introspector = SystemIntrospector()
    return _global_introspector


def get_system_info() -> dict[str, Any]:
    """Get system information."""
    return get_introspector().get_system_info()


def get_capabilities() -> dict[str, list[dict[str, Any]]]:
    """Get all system capabilities."""
    return get_introspector().get_capabilities()


def get_system_schema() -> dict[str, Any]:
    """Get full system schema."""
    return get_introspector().get_schema()


def get_full_documentation(format: str = "markdown") -> str:
    """Get full system documentation."""
    return get_introspector().get_documentation(format)


def get_health_status() -> dict[str, Any]:
    """Get system health status."""
    return get_introspector().get_health_status()
