"""Memory and Knowledge System for PMS.

This module provides:
- Knowledge Store: Persistent storage for learned information
- Pattern Learning: Recognize and reuse successful patterns
- Context Management: Track and retrieve conversation context
- Feedback System: Positive/negative reinforcement learning
- Semantic Search: Find relevant knowledge by meaning

Architecture:
    ┌─────────────────────────────────────────────────────────┐
    │                  Memory System                           │
    │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐ │
    │  │Knowledge │  │ Patterns │  │ Feedback │  │ Context │ │
    │  │  Store   │  │ Matcher  │  │  Store   │  │ Manager │ │
    │  └──────────┘  └──────────┘  └──────────┘  └─────────┘ │
    │        │            │              │            │       │
    │        └────────────┴──────────────┴────────────┘       │
    │                          │                               │
    │              ┌───────────┴───────────┐                  │
    │              │  Learning & Retrieval │                  │
    │              └───────────────────────┘                  │
    └─────────────────────────────────────────────────────────┘

Usage:
    from pms.memory import (
        KnowledgeStore, Knowledge, KnowledgeType,
        PatternMatcher, Pattern, PatternType,
        FeedbackStore, Feedback, FeedbackType,
        ContextManager, ConversationContext,
    )

    # Store learned knowledge
    store = KnowledgeStore()
    await store.add(Knowledge(
        type=KnowledgeType.SOLUTION,
        title="Fix import cycles",
        content="Move shared types to types.py",
    ))

    # Match patterns
    matcher = PatternMatcher()
    patterns = await matcher.match("deploy the app")

    # Track feedback for reinforcement
    feedback = FeedbackStore()
    await feedback.add_positive("code_style", "type_hints")
    await feedback.add_negative("behavior", "verbose_output")

    # Check preferences
    score = await feedback.get_preference_score("code_style", "type_hints")
    if score.is_preferred:
        # Use type hints
        pass
"""

from pms.memory.context import (
    ContextItem,
    ContextItemType,
    ContextManager,
    ConversationContext,
    Decision,
    get_context_manager,
    set_context_manager,
)
from pms.memory.feedback import (
    Feedback,
    FeedbackCategory,
    FeedbackStore,
    FeedbackType,
    PreferenceScore,
    get_feedback_store,
    set_feedback_store,
)
from pms.memory.knowledge import (
    Knowledge,
    KnowledgeStore,
    KnowledgeType,
    get_knowledge_store,
    set_knowledge_store,
)
from pms.memory.patterns import (
    Pattern,
    PatternMatcher,
    PatternType,
    get_builtin_patterns,
    get_pattern_matcher,
    set_pattern_matcher,
)
from pms.memory.priming import (
    ContextPrimer,
    ContextPrimerConfig,
    get_default_context_primer,
)

__all__ = [
    # Knowledge
    "Knowledge",
    "KnowledgeStore",
    "KnowledgeType",
    "get_knowledge_store",
    "set_knowledge_store",
    # Patterns
    "Pattern",
    "PatternMatcher",
    "PatternType",
    "get_pattern_matcher",
    "set_pattern_matcher",
    "get_builtin_patterns",
    # Priming
    "ContextPrimer",
    "ContextPrimerConfig",
    "get_default_context_primer",
    # Context
    "ConversationContext",
    "ContextManager",
    "ContextItem",
    "ContextItemType",
    "Decision",
    "get_context_manager",
    "set_context_manager",
    # Feedback
    "Feedback",
    "FeedbackStore",
    "FeedbackType",
    "FeedbackCategory",
    "PreferenceScore",
    "get_feedback_store",
    "set_feedback_store",
]
