"""Shared value-set contracts for non-enum closed vocabularies."""

from __future__ import annotations

from typing import Final, Literal

SortDirection = Literal["asc", "desc"]
SORT_DIRECTIONS: Final[tuple[SortDirection, SortDirection]] = ("asc", "desc")

QueuePopulation = Literal["visible_operator", "scoped_project"]
QUEUE_POPULATIONS: Final[tuple[QueuePopulation, QueuePopulation]] = (
    "visible_operator",
    "scoped_project",
)

RiskLevel = Literal["low", "medium", "high"]
RISK_LEVELS: Final[tuple[RiskLevel, RiskLevel, RiskLevel]] = (
    "low",
    "medium",
    "high",
)

RetentionUsageSort = Literal["largest", "recent"]
RETENTION_USAGE_SORTS: Final[tuple[RetentionUsageSort, RetentionUsageSort]] = (
    "largest",
    "recent",
)
