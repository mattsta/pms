"""Tests for Core Infrastructure - IDs, References, Registry, Platform."""

import pytest

from pms.core import (
    # Registry
    EntityInfo,
    EntityRegistry,
    EntityStatus,
    # IDs
    EntityType,
    IDSet,
    # Platform
    Platform,
    PlatformConfig,
    # References
    Reference,
    ReferenceStore,
    ReferenceType,
    generate_id,
    get_entity_type,
    get_inverse_relation,
    is_type,
    is_valid_id,
    parse_id,
)

# =============================================================================
# ID System Tests
# =============================================================================


class TestIDSystem:
    """Tests for unified ID system."""

    def test_generate_id(self):
        """Test generating typed IDs."""
        task_id = generate_id(EntityType.TASK)
        assert task_id.startswith("task_")
        assert len(task_id) > 5

    def test_generate_different_types(self):
        """Test generating IDs for different types."""
        project_id = generate_id(EntityType.PROJECT)
        workflow_id = generate_id(EntityType.WORKFLOW)
        knowledge_id = generate_id(EntityType.KNOWLEDGE)

        assert project_id.startswith("proj_")
        assert workflow_id.startswith("wf_")
        assert knowledge_id.startswith("know_")

    def test_parse_id(self):
        """Test parsing IDs."""
        task_id = generate_id(EntityType.TASK)
        entity_type, uuid_part = parse_id(task_id)

        assert entity_type == EntityType.TASK
        assert len(uuid_part) == 36  # UUID format

    def test_get_entity_type(self):
        """Test getting entity type from ID."""
        task_id = generate_id(EntityType.TASK)
        assert get_entity_type(task_id) == EntityType.TASK

        project_id = generate_id(EntityType.PROJECT)
        assert get_entity_type(project_id) == EntityType.PROJECT

    def test_is_valid_id(self):
        """Test ID validation."""
        task_id = generate_id(EntityType.TASK)

        assert is_valid_id(task_id)
        assert is_valid_id(task_id, EntityType.TASK)
        assert not is_valid_id(task_id, EntityType.PROJECT)
        assert not is_valid_id("invalid_id")

    def test_is_type(self):
        """Test type checking."""
        task_id = generate_id(EntityType.TASK)

        assert is_type(task_id, EntityType.TASK)
        assert is_type(task_id, EntityType.TASK, EntityType.PROJECT)
        assert not is_type(task_id, EntityType.PROJECT)

    def test_id_set(self):
        """Test IDSet collection."""
        id_set = IDSet()

        task1 = generate_id(EntityType.TASK)
        task2 = generate_id(EntityType.TASK)
        project = generate_id(EntityType.PROJECT)

        id_set.add(task1)
        id_set.add(task2)
        id_set.add(project)

        assert len(id_set) == 3
        assert task1 in id_set

        tasks = id_set.get_by_type(EntityType.TASK)
        assert len(tasks) == 2
        assert task1 in tasks

        projects = id_set.get_by_type(EntityType.PROJECT)
        assert len(projects) == 1


# =============================================================================
# Reference System Tests
# =============================================================================


class TestReferenceSystem:
    """Tests for reference system."""

    @pytest.fixture
    def store(self):
        """Create test reference store."""
        return ReferenceStore(auto_inverse=False)

    def test_create_reference(self):
        """Test creating references."""
        ref = Reference(
            source_id="task_xxx",
            target_id="wf_yyy",
            relation=ReferenceType.TRIGGERED_BY,
        )

        assert ref.source_id == "task_xxx"
        assert ref.target_id == "wf_yyy"
        assert ref.relation == ReferenceType.TRIGGERED_BY

    def test_inverse_relations(self):
        """Test inverse relation lookup."""
        assert get_inverse_relation(ReferenceType.PARENT_OF) == ReferenceType.CHILD_OF
        assert (
            get_inverse_relation(ReferenceType.TRIGGERS) == ReferenceType.TRIGGERED_BY
        )
        assert (
            get_inverse_relation(ReferenceType.SIMILAR_TO) == ReferenceType.SIMILAR_TO
        )

    @pytest.mark.anyio
    async def test_add_and_find_reference(self, store):
        """Test adding and finding references."""
        ref = Reference(
            source_id="task_xxx",
            target_id="wf_yyy",
            relation=ReferenceType.TRIGGERED_BY,
        )

        ref_id = await store.add(ref)
        found = await store.find(source_id="task_xxx")

        assert len(found) == 1
        assert found[0].id == ref_id

    @pytest.mark.anyio
    async def test_get_targets(self, store):
        """Test getting targets from source."""
        await store.add(
            Reference(
                source_id="task_xxx",
                target_id="wf_aaa",
                relation=ReferenceType.TRIGGERS,
            )
        )
        await store.add(
            Reference(
                source_id="task_xxx",
                target_id="wf_bbb",
                relation=ReferenceType.TRIGGERS,
            )
        )

        targets = await store.get_targets("task_xxx", ReferenceType.TRIGGERS)
        assert len(targets) == 2
        assert "wf_aaa" in targets
        assert "wf_bbb" in targets

    @pytest.mark.anyio
    async def test_has_relation(self, store):
        """Test checking relation existence."""
        await store.add(
            Reference(
                source_id="task_xxx",
                target_id="proj_yyy",
                relation=ReferenceType.BELONGS_TO,
            )
        )

        assert await store.has_relation("task_xxx", "proj_yyy")
        assert await store.has_relation(
            "task_xxx", "proj_yyy", ReferenceType.BELONGS_TO
        )
        assert not await store.has_relation("task_xxx", "proj_zzz")

    @pytest.mark.anyio
    async def test_auto_inverse(self):
        """Test automatic inverse reference creation."""
        store = ReferenceStore(auto_inverse=True)

        await store.add(
            Reference(
                source_id="proj_xxx",
                target_id="task_yyy",
                relation=ReferenceType.CONTAINS,
            )
        )

        # Should have created inverse BELONGS_TO
        sources = await store.get_sources("proj_xxx", ReferenceType.BELONGS_TO)
        assert "task_yyy" in sources

    @pytest.mark.anyio
    async def test_reference_graph(self, store):
        """Test getting reference graph."""
        await store.add(
            Reference(
                source_id="task_a",
                target_id="task_b",
                relation=ReferenceType.DEPENDS_ON,
            )
        )
        await store.add(
            Reference(
                source_id="task_b",
                target_id="task_c",
                relation=ReferenceType.DEPENDS_ON,
            )
        )

        graph = await store.get_reference_graph("task_a", depth=2)

        assert "task_a" in graph["nodes"]
        assert len(graph["edges"]) >= 2


# =============================================================================
# Entity Registry Tests
# =============================================================================


class TestEntityRegistry:
    """Tests for entity registry."""

    @pytest.fixture
    def registry(self):
        """Create test registry."""
        return EntityRegistry()

    def test_register_entity(self, registry):
        """Test registering entities."""
        task_id = generate_id(EntityType.TASK)
        info = EntityInfo(
            id=task_id,
            type=EntityType.TASK,
            name="My Task",
            tags=["important"],
        )

        registered_id = registry.register(info)
        assert registered_id == task_id

    def test_get_entity(self, registry):
        """Test getting entities."""
        task_id = generate_id(EntityType.TASK)
        registry.register(
            EntityInfo(
                id=task_id,
                type=EntityType.TASK,
                name="Test Task",
            )
        )

        info = registry.get(task_id)
        assert info is not None
        assert info.name == "Test Task"

    def test_find_by_type(self, registry):
        """Test finding by type."""
        task1 = generate_id(EntityType.TASK)
        task2 = generate_id(EntityType.TASK)
        project = generate_id(EntityType.PROJECT)

        registry.register(EntityInfo(id=task1, type=EntityType.TASK, name="Task 1"))
        registry.register(EntityInfo(id=task2, type=EntityType.TASK, name="Task 2"))
        registry.register(
            EntityInfo(id=project, type=EntityType.PROJECT, name="Project")
        )

        tasks = registry.find_by_type(EntityType.TASK)
        assert len(tasks) == 2

        projects = registry.find_by_type(EntityType.PROJECT)
        assert len(projects) == 1

    def test_find_by_tag(self, registry):
        """Test finding by tag."""
        task1 = generate_id(EntityType.TASK)
        task2 = generate_id(EntityType.TASK)

        registry.register(
            EntityInfo(id=task1, type=EntityType.TASK, name="Task 1", tags=["urgent"])
        )
        registry.register(
            EntityInfo(id=task2, type=EntityType.TASK, name="Task 2", tags=["normal"])
        )

        urgent = registry.find_by_tag("urgent")
        assert len(urgent) == 1
        assert urgent[0].id == task1

    def test_search(self, registry):
        """Test searching entities."""
        task1 = generate_id(EntityType.TASK)
        task2 = generate_id(EntityType.TASK)

        registry.register(
            EntityInfo(id=task1, type=EntityType.TASK, name="Deploy to production")
        )
        registry.register(
            EntityInfo(id=task2, type=EntityType.TASK, name="Write tests")
        )

        results = registry.search("deploy")
        assert len(results) == 1
        assert results[0].id == task1

    def test_soft_delete(self, registry):
        """Test soft deleting entities."""
        task_id = generate_id(EntityType.TASK)
        registry.register(EntityInfo(id=task_id, type=EntityType.TASK, name="Task"))

        registry.unregister(task_id, soft_delete=True)

        info = registry.get(task_id)
        assert info is not None
        assert info.status == EntityStatus.DELETED

        # Should not appear in active searches
        active = registry.find_by_type(EntityType.TASK, active_only=True)
        assert len(active) == 0

    def test_parent_child_relationship(self, registry):
        """Test parent-child relationships."""
        project_id = generate_id(EntityType.PROJECT)
        task_id = generate_id(EntityType.TASK)

        registry.register(
            EntityInfo(id=project_id, type=EntityType.PROJECT, name="Project")
        )
        registry.register(
            EntityInfo(
                id=task_id, type=EntityType.TASK, name="Task", parent_id=project_id
            )
        )

        children = registry.find_by_parent(project_id)
        assert len(children) == 1
        assert children[0].id == task_id


# =============================================================================
# Platform Tests
# =============================================================================


class TestPlatform:
    """Tests for platform integration."""

    @pytest.fixture
    def platform(self):
        """Create test platform."""
        config = PlatformConfig(enable_events=False, enable_learning=False)
        return Platform(config)

    @pytest.mark.anyio
    async def test_register_entity(self, platform):
        """Test registering entities through platform."""
        task_id = generate_id(EntityType.TASK)

        info = await platform.register_entity(
            entity_id=task_id,
            name="My Task",
            tags=["test"],
        )

        assert info.id == task_id
        assert info.name == "My Task"

    @pytest.mark.anyio
    async def test_get_related_entities(self, platform):
        """Test getting related entities."""
        project_id = generate_id(EntityType.PROJECT)
        task_id = generate_id(EntityType.TASK)

        await platform.register_entity(project_id, "Project")
        await platform.register_entity(task_id, "Task", parent_id=project_id)

        # Link them explicitly
        await platform.link_entities(task_id, project_id, ReferenceType.BELONGS_TO)

        related = await platform.get_related_entities(task_id)
        # Should have at least the project
        related_ids = [e.id for e in related]
        assert project_id in related_ids

    @pytest.mark.anyio
    async def test_entity_graph(self, platform):
        """Test getting entity graph."""
        proj = generate_id(EntityType.PROJECT)
        task1 = generate_id(EntityType.TASK)
        task2 = generate_id(EntityType.TASK)

        await platform.register_entity(proj, "Project")
        await platform.register_entity(task1, "Task 1")
        await platform.register_entity(task2, "Task 2")

        await platform.link_entities(task1, proj, ReferenceType.BELONGS_TO)
        await platform.link_entities(task2, proj, ReferenceType.BELONGS_TO)
        await platform.link_entities(task2, task1, ReferenceType.DEPENDS_ON)

        graph = await platform.get_entity_graph(proj, depth=2)

        assert len(graph["nodes"]) >= 1
        assert "edges" in graph

    def test_context_operations(self, platform):
        """Test context operations."""
        project_id = generate_id(EntityType.PROJECT)
        task_id = generate_id(EntityType.TASK)

        platform.set_context(project_id=project_id, task_id=task_id)
        platform.add_decision("Use PostgreSQL", "Team standard")

        summary = platform.get_context_summary()
        assert project_id in summary

    def test_get_stats(self, platform):
        """Test getting platform stats."""
        stats = platform.get_stats()

        assert "events_emitted" in stats
        assert "entities_registered" in stats
        assert "registry" in stats
        assert "references" in stats


# =============================================================================
# Integration Tests
# =============================================================================


class TestCoreIntegration:
    """Integration tests for core infrastructure."""

    @pytest.mark.anyio
    async def test_full_entity_lifecycle(self):
        """Test complete entity lifecycle."""
        platform = Platform(PlatformConfig(enable_events=False, enable_learning=False))

        # Create project
        project_id = generate_id(EntityType.PROJECT)
        await platform.register_entity(project_id, "My Project", tags=["important"])

        # Create tasks
        task1_id = generate_id(EntityType.TASK)
        task2_id = generate_id(EntityType.TASK)

        await platform.register_entity(task1_id, "Task 1", parent_id=project_id)
        await platform.register_entity(task2_id, "Task 2", parent_id=project_id)

        # Link task dependency
        await platform.link_entities(task2_id, task1_id, ReferenceType.DEPENDS_ON)

        # Query relationships
        related = await platform.get_related_entities(task2_id)
        related_ids = [e.id for e in related]

        assert task1_id in related_ids

        # Get graph
        graph = await platform.get_entity_graph(project_id, depth=2)
        node_ids = [n["id"] for n in graph["nodes"]]

        assert project_id in node_ids

    @pytest.mark.anyio
    async def test_cross_type_references(self):
        """Test references between different entity types."""
        store = ReferenceStore()

        task_id = generate_id(EntityType.TASK)
        workflow_id = generate_id(EntityType.WORKFLOW)
        knowledge_id = generate_id(EntityType.KNOWLEDGE)

        # Task triggered workflow
        await store.add(
            Reference(
                source_id=task_id,
                target_id=workflow_id,
                relation=ReferenceType.TRIGGERS,
            )
        )

        # Workflow produced knowledge
        await store.add(
            Reference(
                source_id=workflow_id,
                target_id=knowledge_id,
                relation=ReferenceType.PRODUCES,
            )
        )

        # Can trace the chain
        workflow_targets = await store.get_targets(task_id, ReferenceType.TRIGGERS)
        assert workflow_id in workflow_targets

        knowledge_targets = await store.get_targets(workflow_id, ReferenceType.PRODUCES)
        assert knowledge_id in knowledge_targets
