"""Learning Engine - Central coordination for learning system.

The Learning Engine integrates:
- Outcome learning from workflows and operations
- Suggestion generation based on patterns and feedback
- Adaptive behavior based on preferences
- Continuous improvement through feedback loops

Usage:
    from pms.learning import LearningEngine

    engine = LearningEngine()

    # Learn from outcomes
    await engine.learn_from_workflow(workflow_run)
    await engine.learn_from_operation(tool_result)

    # Get intelligent suggestions
    suggestions = await engine.suggest("deploy to production")

    # Check recommendations
    if await engine.is_recommended("code_style", "type_hints"):
        # Use type hints
        pass

    # Get nudges for behavior adjustment
    nudges = await engine.get_behavioral_nudges()
"""

from __future__ import annotations

import logging
from typing import Any

from pms.learning.outcomes import (
    LearningResult,
    OperationOutcome,
    OutcomeLearner,
    WorkflowOutcome,
    get_outcome_learner,
)
from pms.learning.suggestions import (
    Suggestion,
    SuggestionEngine,
    get_suggestion_engine,
)
from pms.memory import (
    ContextManager,
    FeedbackStore,
    Knowledge,
    KnowledgeStore,
    KnowledgeType,
    Pattern,
    PatternMatcher,
    get_context_manager,
    get_feedback_store,
    get_knowledge_store,
    get_pattern_matcher,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Learning Engine
# =============================================================================


class LearningEngine:
    """Central learning engine for PMS.

    Coordinates all learning activities:
    - Outcome tracking and analysis
    - Pattern recognition and storage
    - Suggestion generation
    - Behavioral adaptation
    """

    def __init__(
        self,
        knowledge_store: KnowledgeStore | None = None,
        feedback_store: FeedbackStore | None = None,
        pattern_matcher: PatternMatcher | None = None,
        context_manager: ContextManager | None = None,
        outcome_learner: OutcomeLearner | None = None,
        suggestion_engine: SuggestionEngine | None = None,
    ):
        """Initialize learning engine.

        Args:
            knowledge_store: Knowledge storage
            feedback_store: Feedback storage
            pattern_matcher: Pattern matcher
            context_manager: Context manager
            outcome_learner: Outcome learner
            suggestion_engine: Suggestion engine
        """
        self._knowledge = knowledge_store or get_knowledge_store()
        self._feedback = feedback_store or get_feedback_store()
        self._patterns = pattern_matcher or get_pattern_matcher()
        self._context = context_manager or get_context_manager()
        self._outcomes = outcome_learner or get_outcome_learner()
        self._suggestions = suggestion_engine or get_suggestion_engine()

        # Stats tracking
        self._stats = {
            "workflows_learned": 0,
            "operations_learned": 0,
            "suggestions_generated": 0,
            "feedback_recorded": 0,
        }

    # -------------------------------------------------------------------------
    # Learning from Outcomes
    # -------------------------------------------------------------------------

    async def learn_from_workflow(self, outcome: WorkflowOutcome) -> LearningResult:
        """Learn from a workflow outcome.

        Records knowledge, feedback, and updates patterns.

        Args:
            outcome: Workflow outcome

        Returns:
            Learning result summary
        """
        result = await self._outcomes.learn_from_workflow(outcome)
        self._stats["workflows_learned"] += 1
        return result

    async def learn_from_operation(self, outcome: OperationOutcome) -> LearningResult:
        """Learn from an operation outcome.

        Args:
            outcome: Operation outcome

        Returns:
            Learning result summary
        """
        result = await self._outcomes.learn_from_operation(outcome)
        self._stats["operations_learned"] += 1
        return result

    async def record_feedback(
        self,
        category: str,
        subject: str,
        positive: bool,
        signal: float = 0.5,
        reason: str = "",
    ) -> str:
        """Record explicit feedback.

        Args:
            category: Feedback category
            subject: What is being rated
            positive: Whether positive or negative
            signal: Strength of feedback
            reason: Why this feedback

        Returns:
            Feedback ID
        """
        if positive:
            feedback_id = await self._feedback.add_positive(
                category=category,
                subject=subject,
                signal=signal,
                reason=reason,
            )
        else:
            feedback_id = await self._feedback.add_negative(
                category=category,
                subject=subject,
                signal=-signal,
                reason=reason,
            )

        self._stats["feedback_recorded"] += 1
        return feedback_id

    # -------------------------------------------------------------------------
    # Getting Suggestions
    # -------------------------------------------------------------------------

    async def suggest(
        self,
        task_description: str,
        limit: int = 5,
    ) -> list[Suggestion]:
        """Get suggestions for a task.

        Args:
            task_description: What needs to be done
            limit: Maximum suggestions

        Returns:
            List of suggestions
        """
        suggestions = await self._suggestions.suggest_for_task(task_description, limit)
        self._stats["suggestions_generated"] += len(suggestions)
        return suggestions

    async def suggest_workflow(self, goal: str) -> Suggestion | None:
        """Suggest a workflow for a goal.

        Args:
            goal: What to achieve

        Returns:
            Workflow suggestion or None
        """
        suggestion = await self._suggestions.suggest_workflow(goal)
        if suggestion:
            self._stats["suggestions_generated"] += 1
        return suggestion

    async def get_improvements(self, operation: str) -> list[Suggestion]:
        """Get improvement suggestions for an operation.

        Args:
            operation: Operation to improve

        Returns:
            Improvement suggestions
        """
        return await self._suggestions.get_improvement_suggestions(operation)

    # -------------------------------------------------------------------------
    # Checking Recommendations
    # -------------------------------------------------------------------------

    async def is_recommended(
        self,
        category: str,
        subject: str,
        default: bool = True,
    ) -> bool:
        """Check if something is recommended.

        Args:
            category: Category to check
            subject: Subject to check
            default: Default if no strong preference

        Returns:
            True if recommended
        """
        return await self._feedback.should_use(category, subject, default)

    async def get_recommendation(
        self,
        category: str,
        options: list[str],
    ) -> str | None:
        """Get recommended option from choices.

        Args:
            category: Category to check
            options: Available options

        Returns:
            Recommended option or None
        """
        return await self._feedback.get_recommendation(category, options)

    async def get_style_preferences(self) -> dict[str, Any]:
        """Get code style preferences.

        Returns:
            Dictionary of preferences
        """
        return await self._suggestions.get_style_preferences()

    # -------------------------------------------------------------------------
    # Behavioral Nudges
    # -------------------------------------------------------------------------

    async def get_behavioral_nudges(
        self,
        context: dict[str, str] | None = None,
    ) -> list[str]:
        """Get behavioral nudges based on feedback history.

        Args:
            context: Optional context

        Returns:
            List of nudge messages
        """
        return await self._feedback.get_nudges(context)

    async def should_attempt(
        self,
        operation: str,
        min_success_rate: float = 0.3,
    ) -> tuple[bool, str]:
        """Check if an operation should be attempted.

        Based on historical success rate.

        Args:
            operation: Operation to check
            min_success_rate: Minimum success rate

        Returns:
            (should_attempt, reason) tuple
        """
        return await self._outcomes.should_attempt(operation, min_success_rate)

    # -------------------------------------------------------------------------
    # Knowledge Operations
    # -------------------------------------------------------------------------

    async def search_knowledge(
        self,
        query: str,
        type_filter: KnowledgeType | None = None,
        limit: int = 5,
    ) -> list[tuple[Knowledge, float]]:
        """Search the knowledge base.

        Args:
            query: Search query
            type_filter: Optional type filter
            limit: Maximum results

        Returns:
            List of (knowledge, score) tuples
        """
        return await self._knowledge.search(query, type_filter, limit=limit)

    async def add_knowledge(
        self,
        type: KnowledgeType,
        title: str,
        content: str,
        tags: list[str] | None = None,
    ) -> str:
        """Add knowledge to the store.

        Args:
            type: Knowledge type
            title: Short title
            content: Knowledge content
            tags: Optional tags

        Returns:
            Knowledge ID
        """
        knowledge = Knowledge(
            type=type,
            title=title,
            content=content,
            tags=tags or [],
        )
        return await self._knowledge.add(knowledge)

    async def get_error_solutions(self, error: str) -> list[tuple[Knowledge, float]]:
        """Find solutions for an error.

        Args:
            error: Error message

        Returns:
            Potential solutions
        """
        return await self._knowledge.get_solutions_for_error(error)

    # -------------------------------------------------------------------------
    # Pattern Operations
    # -------------------------------------------------------------------------

    async def match_patterns(
        self,
        query: str,
        limit: int = 5,
    ) -> list[tuple[Pattern, float]]:
        """Match patterns for a query.

        Args:
            query: Query to match
            limit: Maximum results

        Returns:
            List of (pattern, score) tuples
        """
        return await self._patterns.match(query, limit=limit)

    def register_pattern(self, pattern: Pattern) -> str:
        """Register a new pattern.

        Args:
            pattern: Pattern to register

        Returns:
            Pattern ID
        """
        return self._patterns.register(pattern)

    # -------------------------------------------------------------------------
    # Context Operations
    # -------------------------------------------------------------------------

    def get_context_summary(self) -> str:
        """Get summary of current context.

        Returns:
            Context summary string
        """
        return self._context.get_context_summary()

    def add_context_note(self, note: str) -> str:
        """Add a note to context.

        Args:
            note: Note to add

        Returns:
            Note ID
        """
        return self._context.add_note(note)

    def add_context_decision(
        self,
        description: str,
        reason: str = "",
    ) -> None:
        """Add a decision to context.

        Args:
            description: Decision description
            reason: Why this decision
        """
        self._context.add_decision(description, reason)

    # -------------------------------------------------------------------------
    # Stats & Maintenance
    # -------------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Get learning engine statistics.

        Returns:
            Statistics dictionary
        """
        return {
            **self._stats,
            "knowledge_stats": self._knowledge.get_stats(),
            "feedback_stats": self._feedback.get_stats(),
            "pattern_stats": self._patterns.get_stats(),
        }

    async def cleanup(self) -> dict[str, int]:
        """Perform cleanup operations.

        Returns:
            Cleanup results
        """
        results = {}

        # Cleanup expired knowledge
        results["knowledge_expired"] = await self._knowledge.cleanup_expired()

        # Decay old feedback confidence
        results["feedback_decayed"] = await self._knowledge.decay_confidence()

        # Prune old feedback
        results["feedback_pruned"] = await self._feedback.prune_old_feedback()

        return results


# =============================================================================
# Global Instance
# =============================================================================

_global_engine: LearningEngine | None = None


def get_learning_engine() -> LearningEngine:
    """Get the global learning engine instance."""
    global _global_engine
    if _global_engine is None:
        _global_engine = LearningEngine()
    return _global_engine


def set_learning_engine(engine: LearningEngine) -> None:
    """Set the global learning engine instance."""
    global _global_engine
    _global_engine = engine
