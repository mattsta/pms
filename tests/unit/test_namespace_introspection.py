"""Tests for Namespace System and Introspection."""

import pytest

from pms.core import (
    # Namespace
    Namespace,
    NamespaceRegistry,
    SystemIntrospector,
    generate_id_for_namespace,
    get_capabilities,
    get_full_documentation,
    get_health_status,
    get_namespace,
    get_namespace_documentation,
    get_namespace_schema,
    # Introspection
    get_system_info,
    get_system_schema,
    list_namespaces,
)

# =============================================================================
# Namespace Tests
# =============================================================================


class TestNamespace:
    """Tests for Namespace model."""

    def test_create_namespace(self):
        """Test creating a namespace."""
        ns = Namespace(
            prefix="test",
            name="test_entity",
            description="Test entity type",
        )
        assert ns.prefix == "test"
        assert ns.name == "test_entity"

    def test_generate_id(self):
        """Test generating ID from namespace."""
        ns = Namespace(prefix="myns", name="my_entity", description="Test")
        id1 = ns.generate_id()
        id2 = ns.generate_id()

        assert id1.startswith("myns_")
        assert id2.startswith("myns_")
        assert id1 != id2  # Unique

    def test_is_valid_id(self):
        """Test validating IDs."""
        ns = Namespace(prefix="myns", name="my_entity", description="Test")

        assert ns.is_valid_id("myns_xxx")
        assert not ns.is_valid_id("other_xxx")

    def test_to_from_dict(self):
        """Test serialization."""
        ns = Namespace(
            prefix="ser",
            name="serialized",
            description="Test serialization",
            schema={"fields": ["a", "b"]},
        )

        data = ns.to_dict()
        restored = Namespace.from_dict(data)

        assert restored.prefix == ns.prefix
        assert restored.name == ns.name
        assert restored.schema == ns.schema


class TestNamespaceRegistry:
    """Tests for NamespaceRegistry."""

    @pytest.fixture
    def registry(self):
        """Create test registry."""
        return NamespaceRegistry()

    def test_builtin_namespaces_exist(self, registry):
        """Test that built-in namespaces are registered."""
        namespaces = registry.list_all()
        prefixes = [ns.prefix for ns in namespaces]

        assert "proj" in prefixes
        assert "task" in prefixes
        assert "wf" in prefixes
        assert "know" in prefixes
        assert "apikey" in prefixes

    def test_register_custom_namespace(self, registry):
        """Test registering custom namespace."""
        ns = Namespace(
            prefix="custom",
            name="custom_entity",
            description="Custom entity",
            module="test_module",
        )

        registry.register(ns)

        retrieved = registry.get("custom")
        assert retrieved is not None
        assert retrieved.name == "custom_entity"

    def test_cannot_override_builtin(self, registry):
        """Test that built-in namespaces cannot be overridden."""
        with pytest.raises(ValueError):
            registry.register(
                Namespace(
                    prefix="proj",  # Built-in
                    name="project_override",
                    description="Try to override",
                )
            )

    def test_unregister_custom(self, registry):
        """Test unregistering custom namespace."""
        registry.register(
            Namespace(
                prefix="temp",
                name="temporary",
                description="Temporary",
            )
        )

        assert registry.exists("temp")
        registry.unregister("temp")
        assert not registry.exists("temp")

    def test_cannot_unregister_builtin(self, registry):
        """Test that built-in namespaces cannot be unregistered."""
        with pytest.raises(ValueError):
            registry.unregister("proj")

    def test_generate_id(self, registry):
        """Test generating ID through registry."""
        task_id = registry.generate_id("task")
        assert task_id.startswith("task_")

    def test_parse_id(self, registry):
        """Test parsing ID through registry."""
        task_id = registry.generate_id("task")
        ns, uuid_part = registry.parse_id(task_id)

        assert ns is not None
        assert ns.prefix == "task"
        assert len(uuid_part) == 36

    def test_get_schema(self, registry):
        """Test getting namespace schema."""
        schema = registry.get_schema()

        assert "version" in schema
        assert "namespaces" in schema
        assert "proj" in schema["namespaces"]
        assert "id_format" not in schema["namespaces"]["proj"]
        assert (
            schema["namespaces"]["proj"]["namespace_generated_id_format"]
            == "proj_<uuid>"
        )
        assert schema["namespaces"]["proj"]["namespace_generated_id_kind"] == (
            "prefix_uuid"
        )
        assert schema["namespaces"]["proj"]["runtime_row_id_contract_scope"] == (
            "public_stored_entity_family"
        )
        assert schema["namespaces"]["proj"]["runtime_row_id_style"] == "uuid_native"
        assert schema["namespaces"]["apikey"]["runtime_row_id_style"] == (
            "prefix_native"
        )
        assert schema["namespaces"]["wf"]["runtime_row_id_contract_scope"] == (
            "internal_or_non_public_namespace"
        )
        assert schema["namespaces"]["wf"]["runtime_row_id_style"] is None

    def test_get_documentation(self, registry):
        """Test getting documentation."""
        docs = registry.get_documentation()

        assert "Namespace Registry" in docs
        assert "proj" in docs
        assert "task" in docs
        assert "Namespace-generated IDs follow the format" in docs
        assert "All entity IDs follow the format" not in docs


class TestNamespaceConvenienceFunctions:
    """Tests for namespace convenience functions."""

    def test_list_namespaces(self):
        """Test listing namespaces."""
        namespaces = list_namespaces()
        assert len(namespaces) > 0

    def test_get_namespace(self):
        """Test getting namespace."""
        ns = get_namespace("task")
        assert ns is not None
        assert ns.name == "task"

    def test_generate_id_for_namespace(self):
        """Test generating ID for namespace."""
        task_id = generate_id_for_namespace("task")
        assert task_id.startswith("task_")

    def test_get_namespace_schema(self):
        """Test getting schema."""
        schema = get_namespace_schema()
        assert "namespaces" in schema
        portfolio_ns = schema["namespaces"]["port"]
        assert portfolio_ns["namespace_generated_id_format"] == "port_<uuid>"
        assert portfolio_ns["runtime_row_id_style"] == "uuid_native"
        portfolio_schema = schema["namespaces"]["port"]["schema"]
        assert "effective_goal_ids" in portfolio_schema["fields"]
        assert "effective_objective_ids" in portfolio_schema["fields"]
        assert "field_notes" in portfolio_schema
        assert (
            "direct portfolio-to-goal strategic links"
            in portfolio_schema["field_notes"]["goal_ids"].lower()
        )

    def test_get_namespace_documentation(self):
        """Test getting documentation."""
        docs = get_namespace_documentation()
        assert "# PMS Namespace Registry" in docs


# =============================================================================
# Introspection Tests
# =============================================================================


class TestIntrospection:
    """Tests for system introspection."""

    def test_get_system_info(self):
        """Test getting system info."""
        info = get_system_info()

        assert "name" in info
        assert "version" in info
        assert "total_capabilities" in info
        assert info["total_capabilities"] > 0

    def test_get_capabilities(self):
        """Test getting capabilities."""
        caps = get_capabilities()

        assert "namespaces" in caps
        assert "tools" in caps
        assert "patterns" in caps
        assert "event_types" in caps
        assert "reference_types" in caps

        # Should have namespaces
        assert len(caps["namespaces"]) > 0
        project_namespace = next(
            ns for ns in caps["namespaces"] if ns["prefix"] == "proj"
        )
        assert project_namespace["namespace_generated_id_format"] == "proj_<uuid>"
        assert project_namespace["namespace_generated_id_kind"] == "prefix_uuid"
        assert project_namespace["runtime_row_id_contract_scope"] == (
            "public_stored_entity_family"
        )
        assert project_namespace["runtime_row_id_style"] == "uuid_native"
        workflow_namespace = next(
            ns for ns in caps["namespaces"] if ns["prefix"] == "wf"
        )
        assert workflow_namespace["runtime_row_id_contract_scope"] == (
            "internal_or_non_public_namespace"
        )
        assert workflow_namespace["runtime_row_id_style"] is None

    def test_get_system_schema(self):
        """Test getting system schema."""
        schema = get_system_schema()

        assert "version" in schema
        assert "namespaces" in schema
        assert "events" in schema
        assert "references" in schema
        assert (
            schema["namespaces"]["proj"]["namespace_generated_id_format"]
            == "proj_<uuid>"
        )
        assert schema["namespaces"]["proj"]["runtime_row_id_contract_scope"] == (
            "public_stored_entity_family"
        )
        assert schema["namespaces"]["proj"]["runtime_row_id_style"] == "uuid_native"
        assert schema["namespaces"]["wf"]["runtime_row_id_contract_scope"] == (
            "internal_or_non_public_namespace"
        )
        assert schema["namespaces"]["wf"]["runtime_row_id_style"] is None

    def test_get_full_documentation_markdown(self):
        """Test getting markdown documentation."""
        docs = get_full_documentation(format="markdown")

        assert "# PMS" in docs
        assert "## Namespaces" in docs
        assert "## MCP Tools" in docs
        assert "### Namespace Schema Details" in docs
        assert "`effective_goal_ids`" in docs
        assert "Hydrated scope readback only" in docs
        assert "Namespace-generated IDs use the typed-ID" in docs
        assert "Runtime row-ID contract scope" in docs
        assert "`public_stored_entity_family`" in docs
        assert "`internal_or_non_public_namespace`" in docs
        assert "Runtime row-ID style: not applicable" in docs
        assert "Generated at" not in docs

    def test_get_full_documentation_text(self):
        """Test getting text documentation."""
        docs = get_full_documentation(format="text")

        assert "PMS" in docs
        assert "NAMESPACES" in docs
        assert "NAMESPACE SCHEMA DETAILS" in docs
        assert "effective_goal_ids" in docs
        assert "Hydrated scope readback only" in docs
        assert "Namespace-generated IDs use the typed-ID" in docs
        assert "Runtime row-ID contract scope" in docs
        assert "public_stored_entity_family" in docs
        assert "internal_or_non_public_namespace" in docs
        assert "Runtime row-ID style: not applicable" in docs

    def test_get_health_status(self):
        """Test getting health status."""
        status = get_health_status()

        assert "healthy" in status
        assert "timestamp" in status
        assert "components" in status


class TestSystemIntrospector:
    """Tests for SystemIntrospector class."""

    @pytest.fixture
    def introspector(self):
        """Create test introspector."""
        return SystemIntrospector()

    def test_caching(self, introspector):
        """Test that capabilities are cached."""
        # First call
        caps1 = introspector.get_capabilities()

        # Second call should use cache
        caps2 = introspector.get_capabilities()

        # Should be same object (cached)
        assert caps1 is caps2

    def test_discover_namespaces(self, introspector):
        """Test namespace discovery."""
        caps = introspector.get_capabilities()
        namespaces = caps["namespaces"]

        # Should find built-in namespaces
        prefixes = [ns["prefix"] for ns in namespaces]
        assert "proj" in prefixes
        assert "task" in prefixes

    def test_discover_reference_types(self, introspector):
        """Test reference type discovery."""
        caps = introspector.get_capabilities()
        refs = caps["reference_types"]

        # Should find reference types
        values = [r["value"] for r in refs]
        assert "belongs_to" in values
        assert "depends_on" in values

    def test_discover_event_types(self, introspector):
        """Test event type discovery."""
        caps = introspector.get_capabilities()
        events = caps["event_types"]

        # Should find event types
        values = [e["value"] for e in events]
        assert "task.completed" in values


# =============================================================================
# Integration Tests
# =============================================================================


class TestNamespaceIntrospectionIntegration:
    """Integration tests for namespace and introspection."""

    def test_custom_namespace_appears_in_introspection(self):
        """Test that custom namespaces appear in introspection."""
        # Create a fresh registry and introspector
        registry = NamespaceRegistry()
        introspector = SystemIntrospector()

        # Register custom namespace
        registry.register(
            Namespace(
                prefix="inttest",
                name="integration_test",
                description="Integration test entity",
                module="test",
            )
        )

        # Should appear in schema
        schema = registry.get_schema()
        assert "inttest" in schema["namespaces"]

    def test_documentation_includes_all_types(self):
        """Test that documentation includes all entity types."""
        docs = get_full_documentation()

        # Should mention various entity types
        assert "project" in docs.lower()
        assert "task" in docs.lower()
        assert "workflow" in docs.lower()
        assert "knowledge" in docs.lower()

    def test_schema_is_complete(self):
        """Test that schema includes all necessary components."""
        schema = get_system_schema()

        # All major sections
        assert "namespaces" in schema
        assert "events" in schema
        assert "references" in schema
        assert "knowledge_types" in schema

        # Namespaces have required fields
        for prefix, ns in schema["namespaces"].items():
            assert "name" in ns
            assert "description" in ns
