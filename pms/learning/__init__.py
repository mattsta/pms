"""Learning System - Integrates memory with automation for self-improvement.

This module connects the Memory system with the Automation system to enable:
- Learning from workflow outcomes
- Pattern recognition in operations
- Automatic improvement suggestions
- Feedback-driven behavior adjustment

Architecture:
    ┌──────────────────────────────────────────────────────────────┐
    │                    Learning System                            │
    │  ┌────────────────────────────────────────────────────────┐  │
    │  │              Outcome Learning                           │  │
    │  │  Workflows → Success/Failure → Knowledge + Feedback     │  │
    │  └────────────────────────────────────────────────────────┘  │
    │  ┌────────────────────────────────────────────────────────┐  │
    │  │              Pattern Recognition                        │  │
    │  │  Operations → Patterns → Suggestions                    │  │
    │  └────────────────────────────────────────────────────────┘  │
    │  ┌────────────────────────────────────────────────────────┐  │
    │  │              Adaptive Behavior                          │  │
    │  │  Feedback → Preferences → Adjusted Actions              │  │
    │  └────────────────────────────────────────────────────────┘  │
    └──────────────────────────────────────────────────────────────┘

Usage:
    from pms.learning import LearningEngine, OutcomeLearner

    # Create learning engine
    engine = LearningEngine()

    # Learn from workflow outcome
    await engine.learn_from_workflow(workflow_run)

    # Get suggestions for an operation
    suggestions = await engine.get_suggestions("deploy to production")

    # Check if approach is recommended
    if await engine.is_recommended("code_style", "type_hints"):
        # Use type hints
        pass
"""

from pms.learning.engine import (
    LearningEngine,
    get_learning_engine,
    set_learning_engine,
)
from pms.learning.outcomes import (
    OutcomeLearner,
    WorkflowOutcome,
)
from pms.learning.suggestions import (
    Suggestion,
    SuggestionEngine,
    SuggestionType,
)

__all__ = [
    # Engine
    "LearningEngine",
    "get_learning_engine",
    "set_learning_engine",
    # Outcomes
    "OutcomeLearner",
    "WorkflowOutcome",
    # Suggestions
    "Suggestion",
    "SuggestionType",
    "SuggestionEngine",
]
