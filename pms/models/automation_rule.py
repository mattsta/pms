"""Models for automation rules and execution history."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from pms.models.base import BaseModel, generate_id, now_utc

type JsonScalar = str | int | float | bool | datetime | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]


class AutomationActionType(StrEnum):
    """Supported automation action types."""

    ADD_COMMENT = "add_comment"
    CREATE_TASK = "create_task"
    UPDATE_TASK_STATUS = "update_task_status"
    SET_CUSTOM_FIELD_VALUE = "set_custom_field_value"


@dataclass
class AutomationRule(BaseModel):
    """Automation rule definition."""

    name: str = ""
    description: str | None = None
    event_pattern: str = ""
    aggregate_type: str | None = None
    aggregate_id: str | None = None
    action_type: AutomationActionType = AutomationActionType.ADD_COMMENT
    action_payload: JsonObject = field(default_factory=dict)
    enabled: bool = True
    cooldown_seconds: float = 0.0
    archived_at: datetime | None = None

    def is_active(self) -> bool:
        """Check if rule is active."""
        return self.enabled and self.archived_at is None


@dataclass
class AutomationRuleRun:
    """Automation rule execution record."""

    rule_id: str
    status: str
    event_id: str | None = None
    id: str = field(default_factory=generate_id)
    started_at: datetime = field(default_factory=now_utc)
    completed_at: datetime | None = None
    error: str | None = None
    output: JsonObject = field(default_factory=dict)
