"""Workflow label gate rules."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pms.models.base import BaseModel


class LabelGateRuleType(StrEnum):
    """Types of label gate rules."""

    REQUIRE_LABEL = "require_label"
    FORBID_LABEL = "forbid_label"
    REQUIRE_CATEGORY = "require_category"
    FORBID_CATEGORY = "forbid_category"


@dataclass
class LabelGateRule(BaseModel):
    """Gate rule linking workflow transitions to label requirements."""

    workflow_id: str = ""
    entity_type: str = "task"
    from_state: str = ""
    to_state: str = ""
    rule_type: LabelGateRuleType = LabelGateRuleType.REQUIRE_LABEL
    label_id: str | None = None
    category_id: str | None = None
    message: str | None = None
