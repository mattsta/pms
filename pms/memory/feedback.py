"""Feedback and Reinforcement System - Learn from positive and negative signals.

This module enables PMS to learn from feedback:
- Track positive outcomes (rewards, likes, successes)
- Track negative outcomes (dislikes, failures, rejections)
- Score operations and approaches by historical success
- Nudge behavior toward preferred patterns

Usage:
    from pms.memory.feedback import FeedbackStore, Feedback, FeedbackType

    store = FeedbackStore()

    # Record positive feedback
    await store.add(Feedback(
        type=FeedbackType.POSITIVE,
        category="code_style",
        subject="use_type_hints",
        signal=0.8,
        context={"file": "service.py"},
        reason="User praised type annotations",
    ))

    # Record negative feedback
    await store.add(Feedback(
        type=FeedbackType.NEGATIVE,
        category="behavior",
        subject="verbose_output",
        signal=-0.6,
        reason="User asked for more concise responses",
    ))

    # Get score for an operation
    score = await store.get_preference_score("code_style", "use_type_hints")
    # Returns positive number if preferred, negative if avoided
"""

from __future__ import annotations

import json
import logging
import math
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Feedback Types
# =============================================================================


class FeedbackType(Enum):
    """Types of feedback signals."""

    POSITIVE = "positive"  # Reward, success, liked
    NEGATIVE = "negative"  # Penalty, failure, disliked
    NEUTRAL = "neutral"  # Informational, no preference


class FeedbackCategory(Enum):
    """Categories of feedback."""

    BEHAVIOR = "behavior"  # How the agent behaves
    CODE_STYLE = "code_style"  # Coding preferences
    COMMUNICATION = "communication"  # Response style
    WORKFLOW = "workflow"  # Process preferences
    TOOL_USE = "tool_use"  # Tool usage patterns
    ARCHITECTURE = "architecture"  # Design decisions
    TESTING = "testing"  # Testing approach
    DOCUMENTATION = "documentation"  # Doc style
    PERFORMANCE = "performance"  # Speed/efficiency
    SAFETY = "safety"  # Safety considerations


# =============================================================================
# Feedback Model
# =============================================================================


@dataclass
class Feedback:
    """A feedback signal.

    Attributes:
        type: Positive, negative, or neutral
        category: What area this feedback applies to
        subject: Specific thing being rated (e.g., "use_type_hints")
        signal: Strength of feedback (-1.0 to 1.0)
        context: Situational context
        reason: Why this feedback was given
        source: Who/what generated this feedback
        weight: How important this feedback is
        created_at: When recorded
        id: Unique identifier
    """

    type: FeedbackType
    category: str  # Can be FeedbackCategory value or custom string
    subject: str
    signal: float = 0.0  # -1.0 (very bad) to 1.0 (very good)
    context: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    source: str = "user"  # user, system, outcome, agent
    weight: float = 1.0  # Importance multiplier
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        # Normalize signal based on type
        match self.type:
            case FeedbackType.POSITIVE if self.signal == 0.0:
                self.signal = 0.5
            case FeedbackType.NEGATIVE if self.signal == 0.0:
                self.signal = -0.5
            case _:
                pass

        # Clamp signal to valid range
        self.signal = max(-1.0, min(1.0, self.signal))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "type": self.type.value,
            "category": self.category,
            "subject": self.subject,
            "signal": self.signal,
            "context": self.context,
            "reason": self.reason,
            "source": self.source,
            "weight": self.weight,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Feedback:
        """Create from dictionary."""
        return cls(
            id=data["id"],
            type=FeedbackType(data["type"]),
            category=data["category"],
            subject=data["subject"],
            signal=data.get("signal", 0.0),
            context=data.get("context", {}),
            reason=data.get("reason", ""),
            source=data.get("source", "user"),
            weight=data.get("weight", 1.0),
            created_at=datetime.fromisoformat(data["created_at"]),
        )


# =============================================================================
# Preference Score
# =============================================================================


@dataclass
class PreferenceScore:
    """Aggregated preference score for a subject.

    Attributes:
        category: Category of preference
        subject: What this score is for
        score: Aggregated score (-1.0 to 1.0)
        confidence: How confident we are in this score
        positive_count: Number of positive signals
        negative_count: Number of negative signals
        last_updated: When last calculated
    """

    category: str
    subject: str
    score: float = 0.0
    confidence: float = 0.0
    positive_count: int = 0
    negative_count: int = 0
    last_updated: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def total_signals(self) -> int:
        return self.positive_count + self.negative_count

    @property
    def is_preferred(self) -> bool:
        """Whether this is preferred (positive score with confidence)."""
        return self.score > 0.1 and self.confidence > 0.3

    @property
    def is_avoided(self) -> bool:
        """Whether this should be avoided (negative score with confidence)."""
        return self.score < -0.1 and self.confidence > 0.3

    @property
    def is_neutral(self) -> bool:
        """Whether we have no strong preference."""
        return abs(self.score) <= 0.1 or self.confidence <= 0.3


# =============================================================================
# Feedback Store
# =============================================================================


class FeedbackStore:
    """Store and aggregate feedback signals.

    Features:
    - Record positive/negative feedback
    - Aggregate into preference scores
    - Decay old feedback over time
    - Query preferences by category/subject
    """

    def __init__(
        self,
        storage_path: Path | str | None = None,
        decay_half_life_days: float = 30.0,
        auto_save: bool = True,
    ):
        """Initialize feedback store.

        Args:
            storage_path: Path to JSON storage file
            decay_half_life_days: How quickly old feedback loses influence
            auto_save: Whether to save after each modification
        """
        self._feedback: list[Feedback] = []
        self._storage_path = Path(storage_path) if storage_path else None
        self._decay_half_life = decay_half_life_days
        self._auto_save = auto_save
        self._score_cache: dict[tuple[str, str], PreferenceScore] = {}

        if self._storage_path and self._storage_path.exists():
            self._load()

    # -------------------------------------------------------------------------
    # Recording Feedback
    # -------------------------------------------------------------------------

    async def add(self, feedback: Feedback) -> str:
        """Add feedback signal.

        Args:
            feedback: Feedback to record

        Returns:
            Feedback ID
        """
        self._feedback.append(feedback)
        self._invalidate_cache(feedback.category, feedback.subject)

        logger.info(
            f"Recorded {feedback.type.value} feedback: "
            f"{feedback.category}/{feedback.subject} = {feedback.signal:.2f}"
        )

        if self._auto_save:
            self._save()

        return feedback.id

    async def add_positive(
        self,
        category: str,
        subject: str,
        signal: float = 0.5,
        reason: str = "",
        context: dict[str, Any] | None = None,
    ) -> str:
        """Convenience method to add positive feedback.

        Args:
            category: Feedback category
            subject: What is being praised
            signal: Strength (0.0 to 1.0)
            reason: Why this is good
            context: Additional context

        Returns:
            Feedback ID
        """
        return await self.add(
            Feedback(
                type=FeedbackType.POSITIVE,
                category=category,
                subject=subject,
                signal=abs(signal),  # Ensure positive
                reason=reason,
                context=context or {},
            )
        )

    async def add_negative(
        self,
        category: str,
        subject: str,
        signal: float = -0.5,
        reason: str = "",
        context: dict[str, Any] | None = None,
    ) -> str:
        """Convenience method to add negative feedback.

        Args:
            category: Feedback category
            subject: What is being criticized
            signal: Strength (-1.0 to 0.0)
            reason: Why this is bad
            context: Additional context

        Returns:
            Feedback ID
        """
        return await self.add(
            Feedback(
                type=FeedbackType.NEGATIVE,
                category=category,
                subject=subject,
                signal=-abs(signal),  # Ensure negative
                reason=reason,
                context=context or {},
            )
        )

    async def record_outcome(
        self,
        operation: str,
        success: bool,
        category: str = "workflow",
        context: dict[str, Any] | None = None,
    ) -> str:
        """Record outcome of an operation as feedback.

        Args:
            operation: What operation was performed
            success: Whether it succeeded
            category: Category for the feedback
            context: Additional context

        Returns:
            Feedback ID
        """
        return await self.add(
            Feedback(
                type=FeedbackType.POSITIVE if success else FeedbackType.NEGATIVE,
                category=category,
                subject=operation,
                signal=0.7 if success else -0.7,
                reason=f"Operation {'succeeded' if success else 'failed'}",
                source="outcome",
                context=context or {},
            )
        )

    # -------------------------------------------------------------------------
    # Querying Preferences
    # -------------------------------------------------------------------------

    async def get_preference_score(
        self,
        category: str,
        subject: str,
    ) -> PreferenceScore:
        """Get aggregated preference score for a subject.

        Uses time-decayed weighted average of all feedback.

        Args:
            category: Category to query
            subject: Subject to query

        Returns:
            Aggregated preference score
        """
        cache_key = (category, subject)
        if cache_key in self._score_cache:
            return self._score_cache[cache_key]

        # Get relevant feedback
        relevant = [
            f for f in self._feedback if f.category == category and f.subject == subject
        ]

        if not relevant:
            return PreferenceScore(category=category, subject=subject)

        # Calculate time-decayed weighted average
        now = datetime.now(UTC)
        total_weight = 0.0
        weighted_sum = 0.0
        positive_count = 0
        negative_count = 0

        for feedback in relevant:
            # Calculate time decay
            age_days = (now - feedback.created_at).total_seconds() / 86400
            decay = math.pow(0.5, age_days / self._decay_half_life)

            # Calculate effective weight
            effective_weight = feedback.weight * decay

            # Accumulate
            weighted_sum += feedback.signal * effective_weight
            total_weight += effective_weight

            if feedback.signal > 0:
                positive_count += 1
            elif feedback.signal < 0:
                negative_count += 1

        # Calculate final score
        score = weighted_sum / total_weight if total_weight > 0 else 0.0

        # Calculate confidence based on amount and consistency of feedback
        confidence = min(1.0, math.log(len(relevant) + 1) / 3)

        # Reduce confidence if signals are inconsistent
        if positive_count > 0 and negative_count > 0:
            consistency = abs(positive_count - negative_count) / (
                positive_count + negative_count
            )
            confidence *= consistency

        result = PreferenceScore(
            category=category,
            subject=subject,
            score=score,
            confidence=confidence,
            positive_count=positive_count,
            negative_count=negative_count,
            last_updated=now,
        )

        self._score_cache[cache_key] = result
        return result

    async def get_category_preferences(
        self,
        category: str,
        min_confidence: float = 0.3,
    ) -> list[PreferenceScore]:
        """Get all preference scores in a category.

        Args:
            category: Category to query
            min_confidence: Minimum confidence to include

        Returns:
            List of preference scores, sorted by score
        """
        # Get unique subjects in this category
        subjects = set(f.subject for f in self._feedback if f.category == category)

        # Get scores for each
        scores = []
        for subject in subjects:
            score = await self.get_preference_score(category, subject)
            if score.confidence >= min_confidence:
                scores.append(score)

        # Sort by score (highest first)
        scores.sort(key=lambda s: s.score, reverse=True)
        return scores

    async def get_preferred(
        self,
        category: str,
        limit: int = 10,
    ) -> list[PreferenceScore]:
        """Get preferred items in a category.

        Args:
            category: Category to query
            limit: Maximum results

        Returns:
            List of preferred items
        """
        scores = await self.get_category_preferences(category)
        return [s for s in scores if s.is_preferred][:limit]

    async def get_avoided(
        self,
        category: str,
        limit: int = 10,
    ) -> list[PreferenceScore]:
        """Get avoided items in a category.

        Args:
            category: Category to query
            limit: Maximum results

        Returns:
            List of avoided items
        """
        scores = await self.get_category_preferences(category)
        return [s for s in scores if s.is_avoided][:limit]

    async def should_use(
        self,
        category: str,
        subject: str,
        default: bool = True,
    ) -> bool:
        """Check if something should be used based on feedback.

        Args:
            category: Category to check
            subject: Subject to check
            default: Default if no strong preference

        Returns:
            True if should use, False if should avoid
        """
        score = await self.get_preference_score(category, subject)

        if score.is_avoided:
            return False
        if score.is_preferred:
            return True
        return default

    async def get_recommendation(
        self,
        category: str,
        options: list[str],
    ) -> str | None:
        """Get best option based on feedback history.

        Args:
            category: Category to check
            options: Available options

        Returns:
            Best option, or None if no preference
        """
        scores = []
        for option in options:
            score = await self.get_preference_score(category, option)
            scores.append((option, score.score, score.confidence))

        # Sort by score, weighted by confidence
        scores.sort(key=lambda x: x[1] * x[2], reverse=True)

        if scores and scores[0][2] > 0.3:  # Min confidence
            return scores[0][0]
        return None

    # -------------------------------------------------------------------------
    # Nudging
    # -------------------------------------------------------------------------

    async def get_nudges(
        self,
        context: dict[str, str] | None = None,
    ) -> list[str]:
        """Get behavioral nudges based on feedback history.

        Returns suggestions for how to behave based on learned preferences.

        Args:
            context: Optional context (category, task type, etc.)

        Returns:
            List of nudge suggestions
        """
        nudges = []

        # Get categories to check
        categories = (
            [context.get("category")]
            if context and "category" in context
            else [c.value for c in FeedbackCategory]
        )

        for category in categories:
            if not category:
                continue

            # Get strong preferences
            prefs = await self.get_category_preferences(category, min_confidence=0.5)

            for pref in prefs[:3]:  # Top 3 per category
                if pref.is_preferred:
                    nudges.append(
                        f"[{category}] Prefer: {pref.subject} (score: {pref.score:.2f})"
                    )
                elif pref.is_avoided:
                    nudges.append(
                        f"[{category}] Avoid: {pref.subject} (score: {pref.score:.2f})"
                    )

        return nudges

    # -------------------------------------------------------------------------
    # History & Stats
    # -------------------------------------------------------------------------

    def get_recent_feedback(
        self,
        limit: int = 20,
        category: str | None = None,
    ) -> list[Feedback]:
        """Get recent feedback entries.

        Args:
            limit: Maximum entries
            category: Optional category filter

        Returns:
            Recent feedback (newest first)
        """
        feedback = list(reversed(self._feedback))

        if category:
            feedback = [f for f in feedback if f.category == category]

        return feedback[:limit]

    def get_stats(self) -> dict[str, Any]:
        """Get feedback statistics."""
        by_type: dict[str, int] = {}
        by_category: dict[str, int] = {}

        for f in self._feedback:
            by_type[f.type.value] = by_type.get(f.type.value, 0) + 1
            by_category[f.category] = by_category.get(f.category, 0) + 1

        return {
            "total_feedback": len(self._feedback),
            "by_type": by_type,
            "by_category": by_category,
            "cached_scores": len(self._score_cache),
        }

    # -------------------------------------------------------------------------
    # Maintenance
    # -------------------------------------------------------------------------

    def _invalidate_cache(self, category: str, subject: str) -> None:
        """Invalidate cache for a category/subject."""
        cache_key = (category, subject)
        self._score_cache.pop(cache_key, None)

    async def prune_old_feedback(self, max_age_days: int = 365) -> int:
        """Remove very old feedback.

        Args:
            max_age_days: Maximum age to keep

        Returns:
            Number of entries removed
        """
        cutoff = datetime.now(UTC)
        original_count = len(self._feedback)

        self._feedback = [
            f for f in self._feedback if (cutoff - f.created_at).days <= max_age_days
        ]

        removed = original_count - len(self._feedback)

        if removed > 0:
            self._score_cache.clear()
            if self._auto_save:
                self._save()
            logger.info(f"Pruned {removed} old feedback entries")

        return removed

    # -------------------------------------------------------------------------
    # Persistence
    # -------------------------------------------------------------------------

    def _save(self) -> None:
        """Save to disk."""
        if not self._storage_path:
            return

        self._storage_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "version": 1,
            "feedback": [f.to_dict() for f in self._feedback],
        }

        with self._storage_path.open("w") as f:
            json.dump(data, f, indent=2)

    def _load(self) -> None:
        """Load from disk."""
        if not self._storage_path or not self._storage_path.exists():
            return

        try:
            with self._storage_path.open() as f:
                data = json.load(f)

            for entry in data.get("feedback", []):
                self._feedback.append(Feedback.from_dict(entry))

            logger.info(f"Loaded {len(self._feedback)} feedback entries")

        except Exception as e:
            logger.error(f"Failed to load feedback store: {e}")


# =============================================================================
# Global Instance
# =============================================================================

_global_feedback_store: FeedbackStore | None = None


def get_feedback_store() -> FeedbackStore:
    """Get the global feedback store instance."""
    global _global_feedback_store
    if _global_feedback_store is None:
        _global_feedback_store = FeedbackStore()
    return _global_feedback_store


def set_feedback_store(store: FeedbackStore) -> None:
    """Set the global feedback store instance."""
    global _global_feedback_store
    _global_feedback_store = store
