"""Suggestion Engine - Provide intelligent suggestions based on learning.

This module generates suggestions based on:
- Historical patterns
- Feedback preferences
- Knowledge base
- Current context

Usage:
    from pms.learning import SuggestionEngine, SuggestionType

    engine = SuggestionEngine()

    # Get suggestions for a task
    suggestions = await engine.suggest_for_task("deploy to production")

    # Get workflow suggestions
    workflow = await engine.suggest_workflow("test and deploy")

    # Get code style suggestions
    style = await engine.get_style_preferences()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pms.memory import (
    ContextManager,
    FeedbackStore,
    KnowledgeStore,
    KnowledgeType,
    PatternMatcher,
    PatternType,
    get_context_manager,
    get_feedback_store,
    get_knowledge_store,
    get_pattern_matcher,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Suggestion Types
# =============================================================================


class SuggestionType(Enum):
    """Types of suggestions."""

    PATTERN = "pattern"  # Use this pattern
    WORKFLOW = "workflow"  # Execute this workflow
    APPROACH = "approach"  # Take this approach
    AVOID = "avoid"  # Avoid this thing
    PREFERENCE = "preference"  # Based on user preference
    KNOWLEDGE = "knowledge"  # From knowledge base
    CONTEXTUAL = "contextual"  # Based on current context


# =============================================================================
# Suggestion Model
# =============================================================================


@dataclass
class Suggestion:
    """A suggestion from the learning system.

    Attributes:
        type: Category of suggestion
        title: Short title
        description: Full description
        confidence: How confident we are (0-1)
        action: Suggested action to take
        source: Where this suggestion came from
        metadata: Additional data
        created_at: When generated
    """

    type: SuggestionType
    title: str
    description: str
    confidence: float = 0.5
    action: str | None = None
    source: str = "system"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_high_confidence(self) -> bool:
        """Whether this is a high-confidence suggestion."""
        return self.confidence >= 0.7

    @property
    def is_actionable(self) -> bool:
        """Whether this suggestion has an action."""
        return self.action is not None


# =============================================================================
# Suggestion Engine
# =============================================================================


class SuggestionEngine:
    """Generates suggestions based on learning.

    Features:
    - Pattern-based suggestions
    - Preference-aware recommendations
    - Context-sensitive advice
    - Knowledge-based answers
    """

    def __init__(
        self,
        knowledge_store: KnowledgeStore | None = None,
        feedback_store: FeedbackStore | None = None,
        pattern_matcher: PatternMatcher | None = None,
        context_manager: ContextManager | None = None,
    ):
        """Initialize suggestion engine.

        Args:
            knowledge_store: Store for knowledge lookup
            feedback_store: Store for preference lookup
            pattern_matcher: Matcher for patterns
            context_manager: Manager for context
        """
        self._knowledge = knowledge_store or get_knowledge_store()
        self._feedback = feedback_store or get_feedback_store()
        self._patterns = pattern_matcher or get_pattern_matcher()
        self._context = context_manager or get_context_manager()

    async def suggest_for_task(
        self,
        task_description: str,
        limit: int = 5,
    ) -> list[Suggestion]:
        """Get suggestions for a task.

        Args:
            task_description: Description of the task
            limit: Maximum suggestions

        Returns:
            List of suggestions
        """
        suggestions: list[Suggestion] = []

        # Get pattern suggestions
        patterns = await self._patterns.match(task_description, limit=3)
        for pattern, score in patterns:
            suggestions.append(
                Suggestion(
                    type=SuggestionType.PATTERN,
                    title=f"Use pattern: {pattern.name}",
                    description=pattern.description,
                    confidence=min(score, pattern.success_rate),
                    action=f"apply_pattern:{pattern.id}",
                    source="pattern_matcher",
                    metadata={
                        "pattern_id": pattern.id,
                        "pattern_type": pattern.type.value,
                        "use_count": pattern.use_count,
                    },
                )
            )

        # Get knowledge suggestions
        knowledge = await self._knowledge.search(task_description, limit=3)
        for item, score in knowledge:
            suggestions.append(
                Suggestion(
                    type=SuggestionType.KNOWLEDGE,
                    title=item.title,
                    description=item.content[:200] + "..."
                    if len(item.content) > 200
                    else item.content,
                    confidence=score * item.confidence,
                    source="knowledge_store",
                    metadata={
                        "knowledge_id": item.id,
                        "knowledge_type": item.type.value,
                    },
                )
            )

        # Add contextual suggestions
        ctx_suggestions = await self._get_contextual_suggestions(task_description)
        suggestions.extend(ctx_suggestions)

        # Sort by confidence
        suggestions.sort(key=lambda s: s.confidence, reverse=True)

        return suggestions[:limit]

    async def suggest_workflow(
        self,
        goal: str,
    ) -> Suggestion | None:
        """Suggest a workflow for a goal.

        Args:
            goal: What to achieve

        Returns:
            Workflow suggestion or None
        """
        # Find matching workflow patterns
        patterns = await self._patterns.match(
            goal,
            type_filter=PatternType.WORKFLOW,
            limit=1,
        )

        if patterns:
            pattern, score = patterns[0]
            return Suggestion(
                type=SuggestionType.WORKFLOW,
                title=f"Workflow: {pattern.name}",
                description=pattern.description,
                confidence=min(score, pattern.success_rate),
                action=f"run_workflow:{pattern.name}",
                source="pattern_matcher",
                metadata={
                    "pattern_id": pattern.id,
                    "template": pattern.template,
                    "parameters": pattern.parameters,
                },
            )

        return None

    async def get_preference(
        self,
        category: str,
        options: list[str],
    ) -> Suggestion | None:
        """Get preferred option based on feedback history.

        Args:
            category: Category to check
            options: Available options

        Returns:
            Suggestion for preferred option
        """
        recommendation = await self._feedback.get_recommendation(category, options)

        if recommendation:
            score = await self._feedback.get_preference_score(category, recommendation)
            return Suggestion(
                type=SuggestionType.PREFERENCE,
                title=f"Preferred: {recommendation}",
                description=f"Based on {score.total_signals} feedback signals",
                confidence=score.confidence,
                action=f"use:{recommendation}",
                source="feedback_store",
                metadata={
                    "category": category,
                    "score": score.score,
                    "positive_count": score.positive_count,
                    "negative_count": score.negative_count,
                },
            )

        return None

    async def get_avoidances(
        self,
        category: str | None = None,
        limit: int = 5,
    ) -> list[Suggestion]:
        """Get things to avoid based on negative feedback.

        Args:
            category: Optional category filter
            limit: Maximum suggestions

        Returns:
            List of avoidance suggestions
        """
        suggestions = []

        # Get from all feedback categories if none specified
        categories = (
            [category]
            if category
            else ["workflow", "code_style", "behavior", "tool_use"]
        )

        for cat in categories:
            avoided = await self._feedback.get_avoided(cat, limit=2)
            for score in avoided:
                suggestions.append(
                    Suggestion(
                        type=SuggestionType.AVOID,
                        title=f"Avoid: {score.subject}",
                        description=f"Negative feedback in {cat} ({score.negative_count} signals)",
                        confidence=abs(score.score) * score.confidence,
                        source="feedback_store",
                        metadata={
                            "category": cat,
                            "score": score.score,
                        },
                    )
                )

        suggestions.sort(key=lambda s: s.confidence, reverse=True)
        return suggestions[:limit]

    async def get_style_preferences(self) -> dict[str, Any]:
        """Get code style preferences from feedback.

        Returns:
            Dictionary of style preferences
        """
        preferences = {}

        # Check common style preferences
        style_options = {
            "type_hints": ["use_type_hints", "no_type_hints"],
            "docstrings": [
                "detailed_docstrings",
                "minimal_docstrings",
                "no_docstrings",
            ],
            "formatting": ["black", "yapf", "ruff", "manual"],
            "error_handling": ["exceptions", "result_types", "error_codes"],
        }

        for pref_name, options in style_options.items():
            suggestion = await self.get_preference("code_style", options)
            if suggestion:
                # Extract the chosen option from the action
                chosen = (
                    suggestion.action.replace("use:", "") if suggestion.action else None
                )
                preferences[pref_name] = {
                    "chosen": chosen,
                    "confidence": suggestion.confidence,
                }

        return preferences

    async def _get_contextual_suggestions(
        self,
        task_description: str,
    ) -> list[Suggestion]:
        """Get suggestions based on current context.

        Args:
            task_description: The task

        Returns:
            Contextual suggestions
        """
        suggestions = []
        context = self._context.get_full_context()

        # Suggest based on active project
        if context.active_project and (
            context.active_project.lower() in task_description.lower()
        ):
            suggestions.append(
                Suggestion(
                    type=SuggestionType.CONTEXTUAL,
                    title=f"Active project: {context.active_project}",
                    description="Task relates to currently active project",
                    confidence=0.6,
                    source="context_manager",
                )
            )

        # Suggest based on recent decisions
        for decision in context.decisions[-2:]:
            if any(
                word in task_description.lower()
                for word in decision.description.lower().split()
            ):
                suggestions.append(
                    Suggestion(
                        type=SuggestionType.CONTEXTUAL,
                        title=f"Previous decision: {decision.description[:50]}",
                        description=f"Reason: {decision.reason}"
                        if decision.reason
                        else "Consider previous decision",
                        confidence=0.5,
                        source="context_manager",
                    )
                )

        # Suggest based on open questions
        for question in context.open_questions:
            suggestions.append(
                Suggestion(
                    type=SuggestionType.CONTEXTUAL,
                    title="Open question",
                    description=question,
                    confidence=0.3,
                    source="context_manager",
                    metadata={"type": "question"},
                )
            )

        return suggestions

    async def get_improvement_suggestions(
        self,
        operation: str,
    ) -> list[Suggestion]:
        """Get suggestions to improve an operation.

        Based on historical failures and successful alternatives.

        Args:
            operation: Operation to improve

        Returns:
            Improvement suggestions
        """
        suggestions = []

        # Check failure history
        score = await self._feedback.get_preference_score("workflow", operation)

        if score.is_avoided:
            # Look for successful alternatives
            alternatives = await self._knowledge.search(
                f"{operation} alternative solution",
                type_filter=KnowledgeType.SOLUTION,
                limit=3,
            )

            for alt, alt_score in alternatives:
                if alt_score > 0.3:
                    suggestions.append(
                        Suggestion(
                            type=SuggestionType.APPROACH,
                            title=f"Alternative: {alt.title}",
                            description=alt.content[:200],
                            confidence=alt_score * alt.confidence,
                            source="knowledge_store",
                            metadata={"knowledge_id": alt.id},
                        )
                    )

            # Add generic improvement suggestion
            suggestions.append(
                Suggestion(
                    type=SuggestionType.AVOID,
                    title=f"Consider alternatives to {operation}",
                    description=f"This operation has low success rate ({(score.score + 1) / 2:.0%})",
                    confidence=abs(score.score) * score.confidence,
                    source="feedback_analysis",
                )
            )

        return suggestions


# =============================================================================
# Global Instance
# =============================================================================

_global_engine: SuggestionEngine | None = None


def get_suggestion_engine() -> SuggestionEngine:
    """Get the global suggestion engine instance."""
    global _global_engine
    if _global_engine is None:
        _global_engine = SuggestionEngine()
    return _global_engine


def set_suggestion_engine(engine: SuggestionEngine) -> None:
    """Set the global suggestion engine instance."""
    global _global_engine
    _global_engine = engine
