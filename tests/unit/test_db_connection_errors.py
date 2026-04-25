"""Tests for translated database integrity errors."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

import pytest

from pms.db.connection import Database
from pms.db.errors import translate_sqlite_integrity_error
from pms.exceptions import ConstraintViolationError


@pytest.mark.asyncio
async def test_unique_constraint_errors_are_translated(db: Database):
    now = datetime.now(UTC).isoformat()
    await db.execute(
        """
        INSERT INTO projects (
            id, name, description, status, tags, created_at, updated_at,
            last_event_sequence, last_revision_number, workflow_metadata
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "proj_unique_one",
            "Duplicate Project",
            None,
            "active",
            "[]",
            now,
            now,
            0,
            0,
            "{}",
        ),
    )

    with pytest.raises(ConstraintViolationError) as exc_info:
        await db.execute(
            """
            INSERT INTO projects (
                id, name, description, status, tags, created_at, updated_at,
                last_event_sequence, last_revision_number, workflow_metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "proj_unique_two",
                "Duplicate Project",
                None,
                "active",
                "[]",
                now,
                now,
                0,
                0,
                "{}",
            ),
        )

    exc = exc_info.value
    assert exc.constraint_kind == "unique"
    assert exc.table == "projects"
    assert exc.columns == ["name"]
    assert "Unique value required" in str(exc)


@pytest.mark.asyncio
async def test_foreign_key_errors_are_translated(db: Database):
    with pytest.raises(ConstraintViolationError) as exc_info:
        await db.execute(
            """
            INSERT INTO task_evidence (
                id, task_id, evidence_type, reference, description, metadata, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "evidence_missing_task",
                "task_missing",
                "log",
                "logs/missing.txt",
                None,
                "{}",
                "tester",
            ),
        )

    exc = exc_info.value
    assert exc.constraint_kind == "foreign_key"
    assert "Linked record validation failed" in str(exc)
    assert exc.suggestions


def test_check_constraint_translation_identifies_invalid_json() -> None:
    exc = translate_sqlite_integrity_error(
        sqlite3.IntegrityError("CHECK constraint failed: json_valid(tags)")
    )

    assert exc.constraint_kind == "check"
    assert exc.columns == ["tags"]
    assert "valid JSON" in str(exc)
    assert any("Provide valid JSON" in suggestion for suggestion in exc.suggestions)


def test_check_constraint_translation_identifies_boolean_flags() -> None:
    exc = translate_sqlite_integrity_error(
        sqlite3.IntegrityError("CHECK constraint failed: is_default IN (0, 1)")
    )

    assert exc.constraint_kind == "check"
    assert exc.columns == ["is_default"]
    assert "0 or 1" in str(exc)
    assert any(
        "Use 1 for true and 0 for false" in suggestion for suggestion in exc.suggestions
    )


def test_check_constraint_translation_identifies_string_enums() -> None:
    exc = translate_sqlite_integrity_error(
        sqlite3.IntegrityError(
            "CHECK constraint failed: action_type IN (\n"
            "    'add_comment',\n"
            "    'create_task',\n"
            "    'update_task_status',\n"
            "    'set_custom_field_value'\n"
            ")"
        )
    )

    assert exc.constraint_kind == "check"
    assert exc.columns == ["action_type"]
    assert "must be one of" in str(exc)
    assert (
        "add_comment, create_task, update_task_status, set_custom_field_value"
        in str(exc)
    )
    assert any("allowed values" in suggestion for suggestion in exc.suggestions)


def test_check_constraint_translation_identifies_non_negative_values() -> None:
    exc = translate_sqlite_integrity_error(
        sqlite3.IntegrityError("CHECK constraint failed: token_count >= 0")
    )

    assert exc.constraint_kind == "check"
    assert exc.columns == ["token_count"]
    assert "non-negative" in str(exc)
    assert any(
        "Provide 0 or a positive value" in suggestion for suggestion in exc.suggestions
    )


def test_check_constraint_translation_identifies_port_range() -> None:
    exc = translate_sqlite_integrity_error(
        sqlite3.IntegrityError("CHECK constraint failed: port > 0 AND port <= 65535")
    )

    assert exc.constraint_kind == "check"
    assert exc.columns == ["port"]
    assert "1-65535" in str(exc)
    assert any("default SSH port" in suggestion for suggestion in exc.suggestions)
