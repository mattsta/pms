"""Shared validation for automation action_type values."""

from __future__ import annotations

from difflib import get_close_matches

from pms.exceptions import ValidationError
from pms.models.automation_rule import AutomationActionType


def automation_action_type_values() -> list[str]:
    """Return canonical automation action_type values."""
    return [action_type.value for action_type in AutomationActionType]


def validate_automation_action_type(
    value: str,
    *,
    field_name: str = "action_type",
) -> AutomationActionType:
    """Validate and normalize an automation action_type token."""
    normalized = value.strip()
    if not normalized:
        raise ValidationError(f"{field_name} cannot be empty", field_name)

    try:
        return AutomationActionType(normalized)
    except ValueError as exc:
        allowed_values = automation_action_type_values()
        suggestions = get_close_matches(normalized, allowed_values, n=3, cutoff=0.5)
        message = (
            f"Invalid {field_name} '{value}'. "
            f"Allowed values: {', '.join(allowed_values)}."
        )
        if suggestions:
            rendered = ", ".join(f"'{suggestion}'" for suggestion in suggestions)
            message += f" Did you mean {rendered}?"
        raise ValidationError(
            message,
            field_name,
            details={
                "value": value,
                "allowed_values": allowed_values,
                "suggestions": suggestions,
            },
        ) from exc
