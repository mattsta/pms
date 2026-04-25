"""Outcome Learning - Learn from workflow and operation outcomes.

This module analyzes outcomes of operations to:
- Store successful approaches as knowledge
- Record failures for avoidance
- Update feedback scores based on results
- Identify patterns in success/failure

Usage:
    from pms.learning import OutcomeLearner, WorkflowOutcome

    learner = OutcomeLearner()

    # Learn from a workflow run
    outcome = WorkflowOutcome(
        workflow_name="deploy",
        success=True,
        duration_seconds=45.0,
        steps_completed=["test", "build", "deploy"],
    )
    await learner.learn(outcome)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pms.memory import (
    FeedbackStore,
    KnowledgeStore,
    PatternMatcher,
    get_feedback_store,
    get_knowledge_store,
    get_pattern_matcher,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Result Models
# =============================================================================


@dataclass
class LearningResult:
    """Result of learning from an outcome."""

    knowledge_ids: list[str] = field(default_factory=list)
    feedback_ids: list[str] = field(default_factory=list)
    patterns_updated: list[str] = field(default_factory=list)


# =============================================================================
# Outcome Models
# =============================================================================


@dataclass
class WorkflowOutcome:
    """Outcome of a workflow execution.

    Attributes:
        workflow_name: Name of the workflow
        workflow_id: Unique run ID
        success: Whether workflow succeeded
        duration_seconds: How long it took
        steps_completed: Steps that completed successfully
        steps_failed: Steps that failed
        error: Error message if failed
        inputs: Workflow inputs
        outputs: Workflow outputs
        context: Additional context
        timestamp: When workflow completed
    """

    workflow_name: str
    success: bool
    workflow_id: str = ""
    duration_seconds: float = 0.0
    steps_completed: list[str] = field(default_factory=list)
    steps_failed: list[str] = field(default_factory=list)
    error: str | None = None
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class OperationOutcome:
    """Outcome of a single operation/tool use.

    Attributes:
        operation: Name of operation
        success: Whether it succeeded
        duration_ms: How long it took
        error: Error if failed
        inputs: Operation inputs
        output: Operation output
        context: Additional context
    """

    operation: str
    success: bool
    duration_ms: float = 0.0
    error: str | None = None
    inputs: dict[str, Any] = field(default_factory=dict)
    output: Any = None
    context: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


# =============================================================================
# Outcome Learner
# =============================================================================


class OutcomeLearner:
    """Learns from operation outcomes.

    Features:
    - Store successful patterns as knowledge
    - Record feedback for success/failure
    - Identify common failure patterns
    - Suggest improvements based on outcomes
    """

    def __init__(
        self,
        knowledge_store: KnowledgeStore | None = None,
        feedback_store: FeedbackStore | None = None,
        pattern_matcher: PatternMatcher | None = None,
    ):
        """Initialize outcome learner.

        Args:
            knowledge_store: Store for learned knowledge
            feedback_store: Store for feedback signals
            pattern_matcher: Pattern matcher for recognition
        """
        self._knowledge = knowledge_store or get_knowledge_store()
        self._feedback = feedback_store or get_feedback_store()
        self._patterns = pattern_matcher or get_pattern_matcher()

        # Track recent outcomes for pattern detection
        self._recent_outcomes: list[WorkflowOutcome | OperationOutcome] = []
        self._max_recent = 100

    async def learn_from_workflow(self, outcome: WorkflowOutcome) -> LearningResult:
        """Learn from a workflow outcome.

        Args:
            outcome: The workflow outcome to learn from

        Returns:
            Learning summary with IDs of created resources
        """
        result = LearningResult()

        # Track recent outcome
        self._recent_outcomes.append(outcome)
        if len(self._recent_outcomes) > self._max_recent:
            self._recent_outcomes.pop(0)

        # Record feedback for the workflow
        feedback_id = await self._feedback.record_outcome(
            operation=outcome.workflow_name,
            success=outcome.success,
            category="workflow",
            context={
                "duration": outcome.duration_seconds,
                "steps": len(outcome.steps_completed),
            },
        )
        result.feedback_ids.append(feedback_id)

        if outcome.success:
            # Learn from success
            await self._learn_success(outcome, result)
        else:
            # Learn from failure
            await self._learn_failure(outcome, result)

        # Update pattern statistics
        await self._update_patterns(outcome, result)

        logger.info(
            f"Learned from workflow '{outcome.workflow_name}': "
            f"success={outcome.success}, "
            f"knowledge={len(result.knowledge_ids)}, "
            f"feedback={len(result.feedback_ids)}"
        )

        return result

    async def learn_from_operation(self, outcome: OperationOutcome) -> LearningResult:
        """Learn from an operation outcome.

        Args:
            outcome: The operation outcome

        Returns:
            Learning summary
        """
        result = LearningResult()

        # Record feedback
        feedback_id = await self._feedback.record_outcome(
            operation=outcome.operation,
            success=outcome.success,
            category="tool_use",
            context={
                "duration_ms": outcome.duration_ms,
                **outcome.context,
            },
        )
        result.feedback_ids.append(feedback_id)

        # If failure with error, store as potential knowledge
        if not outcome.success and outcome.error:
            k_id = await self._knowledge.learn_from_failure(
                operation=outcome.operation,
                error=outcome.error,
                tags=[outcome.operation, "error"],
            )
            result.knowledge_ids.append(k_id)

        return result

    async def _learn_success(
        self,
        outcome: WorkflowOutcome,
        result: LearningResult,
    ) -> None:
        """Learn from successful workflow."""
        # Store successful workflow as solution
        k_id = await self._knowledge.learn_from_success(
            operation=outcome.workflow_name,
            context={
                "inputs": outcome.inputs,
                "steps": outcome.steps_completed,
                "duration": outcome.duration_seconds,
            },
            outcome="Workflow completed successfully",
            tags=["workflow", outcome.workflow_name, "success"],
        )
        result.knowledge_ids.append(k_id)

        # Record positive feedback for each successful step
        for step in outcome.steps_completed:
            f_id = await self._feedback.add_positive(
                category="workflow_step",
                subject=step,
                signal=0.3,  # Small positive signal
                reason=f"Step completed in workflow {outcome.workflow_name}",
            )
            result.feedback_ids.append(f_id)

        # Check if this is a fast execution (good performance)
        if outcome.duration_seconds < 60:  # Less than a minute
            f_id = await self._feedback.add_positive(
                category="performance",
                subject=outcome.workflow_name,
                signal=0.5,
                reason=f"Fast execution: {outcome.duration_seconds:.1f}s",
            )
            result.feedback_ids.append(f_id)

    async def _learn_failure(
        self,
        outcome: WorkflowOutcome,
        result: LearningResult,
    ) -> None:
        """Learn from failed workflow."""
        # Store failure as known issue
        k_id = await self._knowledge.learn_from_failure(
            operation=outcome.workflow_name,
            error=outcome.error or "Unknown error",
            tags=["workflow", outcome.workflow_name, "failure"],
        )
        result.knowledge_ids.append(k_id)

        # Record negative feedback for failed steps
        for step in outcome.steps_failed:
            f_id = await self._feedback.add_negative(
                category="workflow_step",
                subject=step,
                signal=-0.5,
                reason=f"Step failed in workflow {outcome.workflow_name}",
                context={"error": outcome.error},
            )
            result.feedback_ids.append(f_id)

    async def _update_patterns(
        self,
        outcome: WorkflowOutcome,
        result: LearningResult,
    ) -> None:
        """Update pattern statistics based on outcome."""
        # Find matching patterns
        patterns = await self._patterns.match(outcome.workflow_name, limit=3)

        for pattern, score in patterns:
            if score > 0.3:
                pattern.record_use(success=outcome.success)
                result.patterns_updated.append(pattern.name)

    async def get_success_rate(self, operation: str) -> float:
        """Get success rate for an operation.

        Args:
            operation: Operation name

        Returns:
            Success rate from 0.0 to 1.0
        """
        score = await self._feedback.get_preference_score("workflow", operation)
        if score.total_signals == 0:
            return 0.5  # Unknown, assume neutral

        # Convert score (-1 to 1) to rate (0 to 1)
        return (score.score + 1.0) / 2.0

    async def get_common_failures(
        self,
        category: str = "workflow",
        limit: int = 5,
    ) -> list[tuple[str, int]]:
        """Get most common failure operations.

        Args:
            category: Category to check
            limit: Maximum results

        Returns:
            List of (operation, failure_count) tuples
        """
        avoided = await self._feedback.get_avoided(category, limit=limit)
        return [(s.subject, s.negative_count) for s in avoided]

    async def should_attempt(
        self,
        operation: str,
        min_success_rate: float = 0.3,
    ) -> tuple[bool, str]:
        """Check if an operation should be attempted.

        Based on historical success rate and feedback.

        Args:
            operation: Operation to check
            min_success_rate: Minimum success rate to attempt

        Returns:
            (should_attempt, reason) tuple
        """
        success_rate = await self.get_success_rate(operation)

        if success_rate < min_success_rate:
            return False, f"Low success rate ({success_rate:.0%})"

        # Check for recent consecutive failures
        recent_failures = sum(
            1
            for o in self._recent_outcomes[-5:]
            if isinstance(o, WorkflowOutcome)
            and o.workflow_name == operation
            and not o.success
        )

        if recent_failures >= 3:
            return False, f"Recent consecutive failures ({recent_failures})"

        return True, "OK"


# =============================================================================
# Global Instance
# =============================================================================

_global_learner: OutcomeLearner | None = None


def get_outcome_learner() -> OutcomeLearner:
    """Get the global outcome learner instance."""
    global _global_learner
    if _global_learner is None:
        _global_learner = OutcomeLearner()
    return _global_learner


def set_outcome_learner(learner: OutcomeLearner) -> None:
    """Set the global outcome learner instance."""
    global _global_learner
    _global_learner = learner
