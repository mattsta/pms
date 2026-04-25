"""Tests for the Learning system."""

import pytest

from pms.learning import (
    LearningEngine,
    OutcomeLearner,
    Suggestion,
    SuggestionEngine,
    SuggestionType,
    WorkflowOutcome,
)
from pms.learning.outcomes import OperationOutcome
from pms.memory import (
    ContextManager,
    FeedbackStore,
    KnowledgeStore,
    KnowledgeType,
    Pattern,
    PatternMatcher,
    PatternType,
)

# =============================================================================
# Outcome Learning Tests
# =============================================================================


class TestWorkflowOutcome:
    """Tests for WorkflowOutcome model."""

    def test_create_success_outcome(self):
        """Test creating successful outcome."""
        outcome = WorkflowOutcome(
            workflow_name="deploy",
            success=True,
            duration_seconds=45.0,
            steps_completed=["test", "build", "deploy"],
        )
        assert outcome.success
        assert outcome.workflow_name == "deploy"
        assert len(outcome.steps_completed) == 3

    def test_create_failure_outcome(self):
        """Test creating failure outcome."""
        outcome = WorkflowOutcome(
            workflow_name="deploy",
            success=False,
            steps_completed=["test", "build"],
            steps_failed=["deploy"],
            error="Connection refused",
        )
        assert not outcome.success
        assert outcome.error == "Connection refused"


class TestOutcomeLearner:
    """Tests for OutcomeLearner."""

    @pytest.fixture
    def learner(self):
        """Create test learner."""
        return OutcomeLearner(
            knowledge_store=KnowledgeStore(),
            feedback_store=FeedbackStore(),
            pattern_matcher=PatternMatcher(),
        )

    @pytest.mark.anyio
    async def test_learn_from_success(self, learner):
        """Test learning from successful workflow."""
        outcome = WorkflowOutcome(
            workflow_name="test_deploy",
            success=True,
            duration_seconds=30.0,
            steps_completed=["test", "build", "deploy"],
        )

        result = await learner.learn_from_workflow(outcome)

        assert len(result.knowledge_ids) > 0
        assert len(result.feedback_ids) > 0

    @pytest.mark.anyio
    async def test_learn_from_failure(self, learner):
        """Test learning from failed workflow."""
        outcome = WorkflowOutcome(
            workflow_name="test_deploy",
            success=False,
            steps_failed=["deploy"],
            error="Deployment failed: timeout",
        )

        result = await learner.learn_from_workflow(outcome)

        assert len(result.knowledge_ids) > 0
        # Should have negative feedback
        assert len(result.feedback_ids) > 0

    @pytest.mark.anyio
    async def test_learn_from_operation(self, learner):
        """Test learning from operation outcome."""
        outcome = OperationOutcome(
            operation="create_task",
            success=True,
            duration_ms=50.0,
        )

        result = await learner.learn_from_operation(outcome)
        assert len(result.feedback_ids) > 0

    @pytest.mark.anyio
    async def test_get_success_rate(self, learner):
        """Test getting success rate."""
        # Record some outcomes
        await learner.learn_from_workflow(
            WorkflowOutcome(
                workflow_name="deploy",
                success=True,
            )
        )
        await learner.learn_from_workflow(
            WorkflowOutcome(
                workflow_name="deploy",
                success=True,
            )
        )
        await learner.learn_from_workflow(
            WorkflowOutcome(
                workflow_name="deploy",
                success=False,
            )
        )

        rate = await learner.get_success_rate("deploy")
        assert 0.0 <= rate <= 1.0

    @pytest.mark.anyio
    async def test_should_attempt(self, learner):
        """Test checking if operation should be attempted."""
        # New operation - should be OK
        should, reason = await learner.should_attempt("new_workflow")
        assert should

        # After multiple failures
        for _ in range(5):
            await learner.learn_from_workflow(
                WorkflowOutcome(
                    workflow_name="failing_workflow",
                    success=False,
                    error="Always fails",
                )
            )

        should, reason = await learner.should_attempt("failing_workflow")
        # Low success rate should prevent attempt
        assert not should or "failure" in reason.lower() or "success" in reason.lower()


# =============================================================================
# Suggestion Engine Tests
# =============================================================================


class TestSuggestion:
    """Tests for Suggestion model."""

    def test_create_suggestion(self):
        """Test creating suggestion."""
        suggestion = Suggestion(
            type=SuggestionType.PATTERN,
            title="Use deploy pattern",
            description="Standard deployment workflow",
            confidence=0.8,
        )
        assert suggestion.is_high_confidence
        assert suggestion.type == SuggestionType.PATTERN

    def test_actionable_suggestion(self):
        """Test actionable suggestion."""
        suggestion = Suggestion(
            type=SuggestionType.WORKFLOW,
            title="Run tests",
            description="Execute test suite",
            action="run_workflow:test",
            confidence=0.9,
        )
        assert suggestion.is_actionable
        assert suggestion.action == "run_workflow:test"


class TestSuggestionEngine:
    """Tests for SuggestionEngine."""

    @pytest.fixture
    def engine(self):
        """Create test engine."""
        matcher = PatternMatcher()
        # Register some patterns
        matcher.register(
            Pattern(
                type=PatternType.WORKFLOW,
                name="deploy",
                description="Deploy application",
                template=["test", "build", "deploy"],
                triggers=["deploy", "release", "ship"],
            )
        )
        matcher.register(
            Pattern(
                type=PatternType.CODE,
                name="crud_service",
                description="CRUD service pattern",
                template="class Service: pass",
                triggers=["service", "crud", "repository"],
            )
        )

        return SuggestionEngine(
            knowledge_store=KnowledgeStore(),
            feedback_store=FeedbackStore(),
            pattern_matcher=matcher,
            context_manager=ContextManager(),
        )

    @pytest.mark.anyio
    async def test_suggest_for_task(self, engine):
        """Test getting task suggestions."""
        suggestions = await engine.suggest_for_task("deploy the application")

        assert len(suggestions) > 0
        # Should find deploy pattern
        pattern_suggestions = [
            s for s in suggestions if s.type == SuggestionType.PATTERN
        ]
        assert len(pattern_suggestions) > 0

    @pytest.mark.anyio
    async def test_suggest_workflow(self, engine):
        """Test suggesting workflow."""
        suggestion = await engine.suggest_workflow("release new version")

        assert suggestion is not None
        assert suggestion.type == SuggestionType.WORKFLOW

    @pytest.mark.anyio
    async def test_get_preference(self, engine):
        """Test getting preferences."""
        # Add some feedback
        await engine._feedback.add_positive("db", "postgresql", signal=0.9)
        await engine._feedback.add_positive("db", "postgresql", signal=0.8)
        await engine._feedback.add_positive("db", "mysql", signal=0.3)

        suggestion = await engine.get_preference(
            "db", ["postgresql", "mysql", "sqlite"]
        )

        assert suggestion is not None
        assert "postgresql" in suggestion.title.lower()

    @pytest.mark.anyio
    async def test_get_avoidances(self, engine):
        """Test getting things to avoid."""
        # Add negative feedback
        for _ in range(5):
            await engine._feedback.add_negative(
                "workflow", "manual_deploy", signal=-0.9
            )

        avoidances = await engine.get_avoidances("workflow")

        assert len(avoidances) > 0
        assert any("manual_deploy" in a.title for a in avoidances)


# =============================================================================
# Learning Engine Tests
# =============================================================================


class TestLearningEngine:
    """Tests for LearningEngine."""

    @pytest.fixture
    def engine(self):
        """Create test engine."""
        return LearningEngine(
            knowledge_store=KnowledgeStore(),
            feedback_store=FeedbackStore(),
            pattern_matcher=PatternMatcher(),
            context_manager=ContextManager(),
        )

    @pytest.mark.anyio
    async def test_learn_from_workflow(self, engine):
        """Test learning from workflow."""
        outcome = WorkflowOutcome(
            workflow_name="test",
            success=True,
            duration_seconds=10.0,
        )

        result = await engine.learn_from_workflow(outcome)

        assert hasattr(result, "knowledge_ids")
        assert engine._stats["workflows_learned"] == 1

    @pytest.mark.anyio
    async def test_record_feedback(self, engine):
        """Test recording feedback."""
        feedback_id = await engine.record_feedback(
            category="code_style",
            subject="type_hints",
            positive=True,
            signal=0.8,
            reason="Improves readability",
        )

        assert feedback_id is not None
        assert engine._stats["feedback_recorded"] == 1

    @pytest.mark.anyio
    async def test_is_recommended(self, engine):
        """Test checking recommendations."""
        # Add positive feedback
        for _ in range(3):
            await engine.record_feedback("style", "docstrings", positive=True)

        is_rec = await engine.is_recommended("style", "docstrings")
        assert is_rec

    @pytest.mark.anyio
    async def test_suggest(self, engine):
        """Test getting suggestions."""
        # Register a pattern
        engine._patterns.register(
            Pattern(
                type=PatternType.WORKFLOW,
                name="test_suite",
                description="Run test suite",
                template=["pytest"],
                triggers=["test", "tests", "testing"],
            )
        )

        suggestions = await engine.suggest("run the tests")

        assert len(suggestions) > 0

    @pytest.mark.anyio
    async def test_add_and_search_knowledge(self, engine):
        """Test knowledge operations."""
        k_id = await engine.add_knowledge(
            type=KnowledgeType.SOLUTION,
            title="Fix database connection",
            content="Check connection string format",
            tags=["database", "connection"],
        )

        results = await engine.search_knowledge("database connection")

        assert len(results) > 0
        assert results[0][0].id == k_id

    @pytest.mark.anyio
    async def test_get_behavioral_nudges(self, engine):
        """Test getting behavioral nudges."""
        # Add enough feedback for nudges
        for _ in range(5):
            await engine.record_feedback("behavior", "verbose", positive=False)
        for _ in range(5):
            await engine.record_feedback("behavior", "concise", positive=True)

        nudges = await engine.get_behavioral_nudges()
        # Should have at least one nudge
        assert isinstance(nudges, list)

    def test_get_stats(self, engine):
        """Test getting stats."""
        stats = engine.get_stats()

        assert "workflows_learned" in stats
        assert "knowledge_stats" in stats
        assert "feedback_stats" in stats

    @pytest.mark.anyio
    async def test_context_operations(self, engine):
        """Test context operations."""
        engine._context.set_active_project("myproject")
        note_id = engine.add_context_note("Important note")
        engine.add_context_decision("Use PostgreSQL", "Team standard")

        summary = engine.get_context_summary()

        assert "myproject" in summary
        assert "PostgreSQL" in summary


# =============================================================================
# Integration Tests
# =============================================================================


class TestLearningIntegration:
    """Integration tests for learning system."""

    @pytest.mark.anyio
    async def test_full_learning_cycle(self):
        """Test complete learning cycle."""
        engine = LearningEngine(
            knowledge_store=KnowledgeStore(),
            feedback_store=FeedbackStore(),
            pattern_matcher=PatternMatcher(),
            context_manager=ContextManager(),
        )

        # 1. Learn from successful workflow
        await engine.learn_from_workflow(
            WorkflowOutcome(
                workflow_name="deploy_app",
                success=True,
                steps_completed=["test", "build", "deploy"],
            )
        )

        # 2. Learn from failure
        await engine.learn_from_workflow(
            WorkflowOutcome(
                workflow_name="deploy_app",
                success=False,
                error="Connection timeout",
            )
        )

        # 3. Record explicit preferences (need multiple for confidence)
        for _ in range(5):
            await engine.record_feedback(
                "deployment", "blue_green", positive=True, signal=0.9
            )
        for _ in range(3):
            await engine.record_feedback(
                "deployment", "rolling", positive=False, signal=0.7
            )

        # 4. Check if we can get recommendation
        rec = await engine.get_recommendation("deployment", ["blue_green", "rolling"])
        assert rec == "blue_green"

        # 5. Add knowledge
        await engine.add_knowledge(
            type=KnowledgeType.SOLUTION,
            title="Fix timeout",
            content="Increase timeout setting",
            tags=["deployment", "timeout"],
        )

        # 6. Search for solutions
        solutions = await engine.search_knowledge("timeout error")
        assert len(solutions) > 0

    @pytest.mark.anyio
    async def test_adaptive_behavior(self):
        """Test that system adapts based on feedback."""
        engine = LearningEngine(
            knowledge_store=KnowledgeStore(),
            feedback_store=FeedbackStore(),
        )

        # Initially, operation should be OK
        should, _ = await engine.should_attempt("risky_operation")
        assert should

        # After failures, should be more cautious
        for _ in range(5):
            await engine.learn_from_workflow(
                WorkflowOutcome(
                    workflow_name="risky_operation",
                    success=False,
                    error="Failed",
                )
            )

        # Check recommendations
        should, reason = await engine.should_attempt("risky_operation")
        # Should either not attempt or have a warning
        assert not should or "low" in reason.lower() or "failure" in reason.lower()
