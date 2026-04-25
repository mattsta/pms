"""Tests for the shared automation action_type contract."""

from __future__ import annotations

import pytest

from pms.core.automation_action_contract import (
    automation_action_type_values,
    validate_automation_action_type,
)
from pms.exceptions import ValidationError
from pms.models.automation_rule import AutomationActionType


def test_automation_action_type_values_match_enum() -> None:
    assert automation_action_type_values() == [
        AutomationActionType.ADD_COMMENT.value,
        AutomationActionType.CREATE_TASK.value,
        AutomationActionType.UPDATE_TASK_STATUS.value,
        AutomationActionType.SET_CUSTOM_FIELD_VALUE.value,
    ]


def test_validate_automation_action_type_accepts_canonical_value() -> None:
    assert (
        validate_automation_action_type("create_task")
        == AutomationActionType.CREATE_TASK
    )


def test_validate_automation_action_type_rejects_unknown_value_with_suggestion() -> (
    None
):
    with pytest.raises(ValidationError) as exc_info:
        validate_automation_action_type("create_taks")

    exc = exc_info.value
    assert exc.details["field"] == "action_type"
    assert "Allowed values" in exc.message
    assert "create_task" in exc.message
    assert "create_task" in exc.details["suggestions"]
