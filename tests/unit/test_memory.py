"""Tests for the Memory and Knowledge system."""

from datetime import UTC, datetime, timedelta

import pytest

from pms.memory import (
    ContextManager,
    ContextPrimer,
    Feedback,
    FeedbackStore,
    FeedbackType,
    Knowledge,
    KnowledgeStore,
    KnowledgeType,
    Pattern,
    PatternMatcher,
    PatternType,
    get_builtin_patterns,
)

# =============================================================================
# Knowledge Store Tests
# =============================================================================


class TestKnowledge:
    """Tests for Knowledge model."""

    def test_create_knowledge(self):
        """Test creating knowledge."""
        k = Knowledge(
            type=KnowledgeType.SOLUTION,
            title="Test Solution",
            content="This is a test",
            tags=["test", "example"],
        )
        assert k.type == KnowledgeType.SOLUTION
        assert k.title == "Test Solution"
        assert k.content == "This is a test"
        assert "test" in k.tags

    def test_knowledge_not_expired(self):
        """Test knowledge that hasn't expired."""
        k = Knowledge(
            type=KnowledgeType.PATTERN,
            title="Test",
            content="Content",
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        assert not k.is_expired()

    def test_knowledge_expired(self):
        """Test expired knowledge."""
        k = Knowledge(
            type=KnowledgeType.PATTERN,
            title="Test",
            content="Content",
            expires_at=datetime.now(UTC) - timedelta(days=1),
        )
        assert k.is_expired()

    def test_relevance_score(self):
        """Test relevance scoring."""
        k = Knowledge(
            type=KnowledgeType.SOLUTION,
            title="Fix circular imports",
            content="Move types to separate module",
            tags=["python", "imports", "architecture"],
        )

        # High score for matching query
        score = k.relevance_score({"circular", "imports"})
        assert score > 0

        # Tag matches should boost score
        score_with_tag = k.relevance_score({"python", "imports"})
        score_without_tag = k.relevance_score({"fix", "error"})
        assert score_with_tag > score_without_tag

    def test_to_from_dict(self):
        """Test serialization."""
        k = Knowledge(
            type=KnowledgeType.TOOL_USAGE,
            title="Using grep",
            content="grep -r pattern .",
            tags=["cli", "search"],
        )

        data = k.to_dict()
        restored = Knowledge.from_dict(data)

        assert restored.id == k.id
        assert restored.type == k.type
        assert restored.title == k.title
        assert restored.tags == k.tags


class TestKnowledgeStore:
    """Tests for KnowledgeStore."""

    @pytest.fixture
    def store(self):
        """Create test store."""
        return KnowledgeStore()

    @pytest.mark.anyio
    async def test_add_and_get(self, store):
        """Test adding and getting knowledge."""
        k = Knowledge(
            type=KnowledgeType.SOLUTION,
            title="Test",
            content="Content",
        )

        k_id = await store.add(k)
        retrieved = await store.get(k_id)

        assert retrieved is not None
        assert retrieved.title == "Test"
        assert retrieved.access_count == 1

    @pytest.mark.anyio
    async def test_search(self, store):
        """Test searching knowledge."""
        await store.add(
            Knowledge(
                type=KnowledgeType.SOLUTION,
                title="Fix import cycle",
                content="Move shared types to separate module",
                tags=["python", "imports"],
            )
        )
        await store.add(
            Knowledge(
                type=KnowledgeType.SOLUTION,
                title="Fix database error",
                content="Check connection string",
                tags=["database", "error"],
            )
        )

        results = await store.search("import cycle python")
        assert len(results) > 0
        assert results[0][0].title == "Fix import cycle"

    @pytest.mark.anyio
    async def test_delete(self, store):
        """Test deleting knowledge."""
        k = Knowledge(
            type=KnowledgeType.NOTE,
            title="Temporary",
            content="Will be deleted",
        )
        k_id = await store.add(k)

        deleted = await store.delete(k_id)
        assert deleted

        retrieved = await store.get(k_id)
        assert retrieved is None

    @pytest.mark.anyio
    async def test_list_with_filters(self, store):
        """Test listing with filters."""
        await store.add(
            Knowledge(
                type=KnowledgeType.PATTERN, title="P1", content="c", tags=["python"]
            )
        )
        await store.add(
            Knowledge(
                type=KnowledgeType.SOLUTION, title="S1", content="c", tags=["python"]
            )
        )
        await store.add(
            Knowledge(
                type=KnowledgeType.PATTERN, title="P2", content="c", tags=["rust"]
            )
        )

        # Filter by type
        patterns = await store.list_all(type_filter=KnowledgeType.PATTERN)
        assert len(patterns) == 2

        # Filter by tag
        python_items = await store.list_all(tag_filter="python")
        assert len(python_items) == 2

    @pytest.mark.anyio
    async def test_learn_from_success(self, store):
        """Test learning from success."""
        k_id = await store.learn_from_success(
            operation="run tests",
            context={"command": "pytest"},
            outcome="All tests passed",
            tags=["testing"],
        )

        k = await store.get(k_id)
        assert k is not None
        assert "success_count" in k.metadata


# =============================================================================
# Pattern Tests
# =============================================================================


class TestPattern:
    """Tests for Pattern model."""

    def test_create_pattern(self):
        """Test creating a pattern."""
        p = Pattern(
            type=PatternType.WORKFLOW,
            name="test_deploy",
            description="Test then deploy",
            template=["test", "build", "deploy"],
            triggers=["deploy", "release"],
        )
        assert p.type == PatternType.WORKFLOW
        assert p.name == "test_deploy"

    def test_match_score(self):
        """Test pattern match scoring."""
        p = Pattern(
            type=PatternType.WORKFLOW,
            name="deploy_app",
            description="Deploy the application",
            template=[],
            triggers=["deploy", "release", "ship"],
        )

        # High score for trigger match
        score = p.match_score("deploy the app")
        assert score > 0.3

        # Lower score for no match
        score_low = p.match_score("fix a bug")
        assert score_low < score

    def test_apply_string_template(self):
        """Test applying string template."""
        p = Pattern(
            type=PatternType.CODE,
            name="function",
            description="Function template",
            template="def {{name}}():\n    pass",
            parameters=["name"],
        )

        result = p.apply(name="my_function")
        assert "def my_function():" in result

    def test_apply_list_template(self):
        """Test applying list template."""
        p = Pattern(
            type=PatternType.WORKFLOW,
            name="deploy",
            description="Deploy workflow",
            template=["test {{env}}", "build", "deploy {{env}}"],
            parameters=["env"],
        )

        result = p.apply(env="production")
        assert result[0] == "test production"
        assert result[2] == "deploy production"

    def test_record_use(self):
        """Test recording pattern use."""
        p = Pattern(
            type=PatternType.CODE,
            name="test",
            description="Test pattern",
            template="",
        )

        original_success = p.success_rate
        p.record_use(success=True)

        assert p.use_count == 1
        assert p.last_used is not None


class TestPatternMatcher:
    """Tests for PatternMatcher."""

    @pytest.fixture
    def matcher(self):
        """Create test matcher."""
        return PatternMatcher()

    def test_register_pattern(self, matcher):
        """Test registering patterns."""
        p = Pattern(
            type=PatternType.WORKFLOW,
            name="test",
            description="Test pattern",
            template=[],
        )
        p_id = matcher.register(p)

        retrieved = matcher.get(p_id)
        assert retrieved is not None
        assert retrieved.name == "test"

    @pytest.mark.anyio
    async def test_match(self, matcher):
        """Test matching patterns."""
        matcher.register(
            Pattern(
                type=PatternType.WORKFLOW,
                name="deploy",
                description="Deploy application",
                template=[],
                triggers=["deploy", "release"],
            )
        )
        matcher.register(
            Pattern(
                type=PatternType.CODE,
                name="service",
                description="Service class pattern",
                template="",
                triggers=["service", "crud"],
            )
        )

        results = await matcher.match("deploy the app")
        assert len(results) > 0
        assert results[0][0].name == "deploy"

    def test_builtin_patterns(self):
        """Test built-in patterns exist."""
        patterns = get_builtin_patterns()
        assert len(patterns) > 0

        # Check different types exist
        types = {p.type for p in patterns}
        assert PatternType.WORKFLOW in types
        assert PatternType.CODE in types
        assert PatternType.ERROR in types


# =============================================================================
# Context Manager Tests
# =============================================================================


class TestContextManager:
    """Tests for ContextManager."""

    @pytest.fixture
    def ctx(self):
        """Create test context manager."""
        return ContextManager()

    def test_set_active_project(self, ctx):
        """Test setting active project."""
        ctx.set_active_project("myproject")
        assert ctx.get_active_project() == "myproject"

    def test_set_active_task(self, ctx):
        """Test setting active task."""
        ctx.set_active_task("task-123")
        assert ctx.get_active_task() == "task-123"

    def test_add_action(self, ctx):
        """Test adding actions."""
        ctx.add_action("Created new file")
        ctx.add_action("Ran tests")

        summary = ctx.get_context_summary()
        assert "Recent Actions" in summary

    def test_add_decision(self, ctx):
        """Test adding decisions."""
        ctx.add_decision(
            description="Use pytest for testing",
            reason="Team standard",
            alternatives=["unittest", "nose"],
        )

        context = ctx.get_full_context()
        assert len(context.decisions) == 1
        assert context.decisions[0].description == "Use pytest for testing"

    def test_add_question(self, ctx):
        """Test adding and resolving questions."""
        ctx.add_question("Which database to use?")
        assert "Which database to use?" in ctx.get_full_context().open_questions

        ctx.resolve_question("Which database to use?", "PostgreSQL")
        assert "Which database to use?" not in ctx.get_full_context().open_questions

    def test_goals_and_constraints(self, ctx):
        """Test goals and constraints."""
        ctx.add_goal("Implement user auth")
        ctx.add_constraint("Must use OAuth 2.0")

        context = ctx.get_full_context()
        assert "Implement user auth" in context.goals
        assert "Must use OAuth 2.0" in context.constraints

        ctx.remove_goal("Implement user auth")
        assert "Implement user auth" not in ctx.get_full_context().goals

    def test_preferences(self, ctx):
        """Test preferences."""
        ctx.set_preference("output_format", "json")
        assert ctx.get_preference("output_format") == "json"
        assert ctx.get_preference("missing", "default") == "default"

    def test_new_session(self, ctx):
        """Test starting new session."""
        ctx.set_active_project("project1")
        ctx.add_action("Some action")

        old_session = ctx.get_session_id()
        new_session = ctx.new_session(preserve_project=True)

        assert new_session != old_session
        assert ctx.get_active_project() == "project1"  # Preserved

    def test_compact_session(self, ctx):
        """Test compacting context and resetting session."""
        ctx.set_active_project("project1")
        ctx.add_action("Wrote docs")

        old_session = ctx.get_session_id()
        summary = ctx.compact(preserve_project=True, max_items=5)

        assert old_session != ctx.get_session_id()
        assert ctx.get_active_project() == "project1"
        assert "Wrote docs" in summary

    def test_context_summary(self, ctx):
        """Test generating context summary."""
        ctx.set_active_project("myproject")
        ctx.set_active_task("task-1")
        ctx.add_goal("Build feature X")
        ctx.add_action("Created model")
        ctx.add_decision("Use SQLAlchemy", reason="ORM support")

        summary = ctx.get_context_summary()

        assert "myproject" in summary
        assert "task-1" in summary
        assert "Build feature X" in summary
        assert "SQLAlchemy" in summary


class TestContextPrimer:
    """Tests for ContextPrimer."""

    @pytest.mark.anyio
    async def test_snapshot_and_compact(self):
        ctx = ContextManager()
        store = KnowledgeStore(auto_save=False)
        primer = ContextPrimer(ctx, store)

        ctx.set_active_project("project-a")
        ctx.add_action("Planned roadmap")

        primer_text = primer.build_primer()
        assert "Context Primer" in primer_text
        assert "project-a" in primer_text

        snapshot_id = await primer.snapshot("unit-test")
        assert snapshot_id is not None
        stored = await store.get(snapshot_id)
        assert stored is not None
        assert stored.type == KnowledgeType.CONTEXT

        compact_id = await primer.compact_and_snapshot(
            "compact-test", preserve_project=True
        )
        assert compact_id is not None
        assert ctx.get_active_project() == "project-a"


# =============================================================================
# Feedback Tests
# =============================================================================


class TestFeedback:
    """Tests for Feedback model."""

    def test_create_positive_feedback(self):
        """Test creating positive feedback."""
        f = Feedback(
            type=FeedbackType.POSITIVE,
            category="code_style",
            subject="type_hints",
            reason="Makes code clearer",
        )
        assert f.type == FeedbackType.POSITIVE
        assert f.signal > 0

    def test_create_negative_feedback(self):
        """Test creating negative feedback."""
        f = Feedback(
            type=FeedbackType.NEGATIVE,
            category="behavior",
            subject="verbose_output",
            reason="Too much text",
        )
        assert f.type == FeedbackType.NEGATIVE
        assert f.signal < 0

    def test_signal_clamping(self):
        """Test signal is clamped to valid range."""
        f = Feedback(
            type=FeedbackType.POSITIVE,
            category="test",
            subject="test",
            signal=5.0,  # Too high
        )
        assert f.signal <= 1.0

        f2 = Feedback(
            type=FeedbackType.NEGATIVE,
            category="test",
            subject="test",
            signal=-5.0,  # Too low
        )
        assert f2.signal >= -1.0


class TestFeedbackStore:
    """Tests for FeedbackStore."""

    @pytest.fixture
    def store(self):
        """Create test store."""
        return FeedbackStore()

    @pytest.mark.anyio
    async def test_add_positive(self, store):
        """Test adding positive feedback."""
        f_id = await store.add_positive(
            category="code_style",
            subject="docstrings",
            signal=0.8,
            reason="Good documentation",
        )
        assert f_id is not None

        score = await store.get_preference_score("code_style", "docstrings")
        assert score.score > 0

    @pytest.mark.anyio
    async def test_add_negative(self, store):
        """Test adding negative feedback."""
        await store.add_negative(
            category="behavior",
            subject="auto_commit",
            signal=-0.7,
            reason="Want manual control",
        )

        score = await store.get_preference_score("behavior", "auto_commit")
        assert score.score < 0

    @pytest.mark.anyio
    async def test_preference_aggregation(self, store):
        """Test that multiple feedback is aggregated."""
        # Add multiple positive
        await store.add_positive("test", "feature_a", signal=0.8)
        await store.add_positive("test", "feature_a", signal=0.6)
        await store.add_positive("test", "feature_a", signal=0.7)

        score = await store.get_preference_score("test", "feature_a")
        assert score.positive_count == 3
        assert score.score > 0.5
        assert score.confidence > 0.3

    @pytest.mark.anyio
    async def test_mixed_signals(self, store):
        """Test mixed positive and negative signals."""
        await store.add_positive("test", "mixed", signal=0.5)
        await store.add_negative("test", "mixed", signal=-0.5)

        score = await store.get_preference_score("test", "mixed")
        # Should have lower confidence due to inconsistency
        assert score.confidence < 0.5

    @pytest.mark.anyio
    async def test_should_use(self, store):
        """Test should_use helper."""
        await store.add_positive("style", "tabs", signal=0.9)
        await store.add_positive("style", "tabs", signal=0.8)
        await store.add_negative("style", "spaces", signal=-0.9)
        await store.add_negative("style", "spaces", signal=-0.8)

        assert await store.should_use("style", "tabs") is True
        assert await store.should_use("style", "spaces") is False
        assert await store.should_use("style", "unknown", default=True) is True

    @pytest.mark.anyio
    async def test_get_preferred_and_avoided(self, store):
        """Test getting preferred and avoided items."""
        await store.add_positive("cat", "good1", signal=0.9)
        await store.add_positive("cat", "good1", signal=0.8)
        await store.add_positive("cat", "good2", signal=0.7)
        await store.add_positive("cat", "good2", signal=0.7)
        await store.add_negative("cat", "bad1", signal=-0.8)
        await store.add_negative("cat", "bad1", signal=-0.9)

        preferred = await store.get_preferred("cat")
        assert len(preferred) >= 1
        assert any(p.subject == "good1" for p in preferred)

        avoided = await store.get_avoided("cat")
        assert len(avoided) >= 1
        assert any(a.subject == "bad1" for a in avoided)

    @pytest.mark.anyio
    async def test_get_recommendation(self, store):
        """Test getting recommendations."""
        await store.add_positive("db", "postgresql", signal=0.9)
        await store.add_positive("db", "postgresql", signal=0.8)
        await store.add_positive("db", "mysql", signal=0.3)

        recommendation = await store.get_recommendation(
            "db",
            ["postgresql", "mysql", "sqlite"],
        )
        assert recommendation == "postgresql"

    @pytest.mark.anyio
    async def test_record_outcome(self, store):
        """Test recording operation outcomes."""
        await store.record_outcome("deploy", success=True)
        await store.record_outcome("deploy", success=True)
        await store.record_outcome("deploy", success=False)

        score = await store.get_preference_score("workflow", "deploy")
        assert score.positive_count == 2
        assert score.negative_count == 1

    @pytest.mark.anyio
    async def test_get_nudges(self, store):
        """Test getting behavioral nudges."""
        # Add enough signals to build confidence (>0.5)
        for _ in range(5):
            await store.add_positive("code_style", "type_hints", signal=0.9)
        for _ in range(5):
            await store.add_negative("behavior", "auto_format", signal=-0.9)

        nudges = await store.get_nudges()
        assert len(nudges) >= 1

    def test_stats(self, store):
        """Test getting stats."""
        stats = store.get_stats()
        assert "total_feedback" in stats
        assert "by_type" in stats
        assert "by_category" in stats


# =============================================================================
# Integration Tests
# =============================================================================


class TestMemoryIntegration:
    """Integration tests for memory system."""

    @pytest.mark.anyio
    async def test_learn_and_recall_pattern(self):
        """Test learning and recalling patterns."""
        store = KnowledgeStore()
        matcher = PatternMatcher()

        # Store knowledge about a successful operation
        k_id = await store.learn_from_success(
            operation="sync and test",
            context={"host": "test-server", "command": "pytest"},
            outcome="Tests passed",
            tags=["sync", "test", "remote"],
        )

        # Later, search for relevant knowledge
        results = await store.search("sync to server and test")
        assert len(results) > 0

    @pytest.mark.anyio
    async def test_context_with_feedback(self):
        """Test context and feedback integration."""
        ctx = ContextManager()
        feedback = FeedbackStore()

        # Record context
        ctx.set_active_project("myproject")
        ctx.add_action("Deployed to production")

        # Record feedback on the action
        await feedback.record_outcome("deploy", success=True)

        # Check preferences
        score = await feedback.get_preference_score("workflow", "deploy")
        assert score.score > 0
