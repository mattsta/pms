"""Database error translation helpers."""

from __future__ import annotations

import re
import sqlite3

from pms.exceptions import ConstraintViolationError

_UNIQUE_RE = re.compile(r"UNIQUE constraint failed: (?P<targets>.+)")
_NOT_NULL_RE = re.compile(r"NOT NULL constraint failed: (?P<target>.+)")
_CHECK_RE = re.compile(r"CHECK constraint failed(?:: (?P<target>.+))?", re.DOTALL)
_JSON_VALID_RE = re.compile(r"json_valid\((?P<column>[a-zA-Z_][a-zA-Z0-9_]*)\)")
_BOOLEAN_IN_RE = re.compile(r"(?P<column>[a-zA-Z_][a-zA-Z0-9_]*)\s+IN\s+\(0,\s*1\)")
_TEXT_ENUM_IN_RE = re.compile(
    r"(?P<column>[a-zA-Z_][a-zA-Z0-9_]*)\s+IN\s+\(\s*(?P<values>'[^']+'(?:\s*,\s*'[^']+')+)\s*\)"
)
_PERCENT_RANGE_RE = re.compile(
    r"(?P<column>[a-zA-Z_][a-zA-Z0-9_]*)\s*>=\s*0\s+AND\s+(?P=column)\s*<=\s*100"
)
_NULLABLE_NON_NEGATIVE_RE = re.compile(
    r"(?P<column>[a-zA-Z_][a-zA-Z0-9_]*)\s+IS\s+NULL\s+OR\s+(?P=column)\s*>=\s*0"
)
_NON_NEGATIVE_RE = re.compile(r"(?P<column>[a-zA-Z_][a-zA-Z0-9_]*)\s*>=\s*0")


def translate_sqlite_integrity_error(
    exc: sqlite3.IntegrityError,
) -> ConstraintViolationError:
    """Translate a raw SQLite integrity error into a structured PMS error."""
    raw_message = str(exc)

    if match := _UNIQUE_RE.search(raw_message):
        targets = [target.strip() for target in match.group("targets").split(",")]
        parsed = [_split_target(target) for target in targets]
        table = parsed[0][0] if parsed and parsed[0][0] else None
        columns = [column for _, column in parsed if column]
        joined_columns = ", ".join(columns) if columns else "the constrained field(s)"
        return ConstraintViolationError(
            f"Unique value required for {joined_columns}. Use a different value or fetch the existing record first.",
            constraint_kind="unique",
            table=table,
            columns=columns,
            raw_message=raw_message,
            suggestions=[
                "Use a different value for the conflicting field.",
                "If this record may already exist, fetch or update it instead of creating a duplicate.",
            ],
        )

    if match := _NOT_NULL_RE.search(raw_message):
        table, column = _split_target(match.group("target").strip())
        column_label = column or "the required field"
        return ConstraintViolationError(
            f"Missing required value for {column_label}. Provide that field and retry.",
            constraint_kind="not_null",
            table=table,
            columns=[column] if column else [],
            raw_message=raw_message,
            suggestions=[
                "Provide a non-null value for the required field.",
            ],
        )

    if "FOREIGN KEY constraint failed" in raw_message:
        return ConstraintViolationError(
            "Linked record validation failed. One or more referenced IDs do not exist or are not currently valid.",
            constraint_kind="foreign_key",
            raw_message=raw_message,
            suggestions=[
                "Verify each referenced ID exists before writing.",
                "If you passed a human-readable name where an ID is required, resolve the canonical ID first.",
            ],
        )

    if match := _CHECK_RE.search(raw_message):
        target = (match.group("target") or "").strip() or None
        return _translate_check_constraint(raw_message, target)

    return ConstraintViolationError(
        f"Database integrity check failed: {raw_message}",
        constraint_kind="integrity",
        raw_message=raw_message,
    )


def _split_target(target: str) -> tuple[str | None, str | None]:
    if "." not in target:
        return None, target or None
    table, column = target.split(".", 1)
    return table or None, column or None


def _translate_check_constraint(
    raw_message: str, target: str | None
) -> ConstraintViolationError:
    normalized_target = (target or "").strip()
    collapsed_target = " ".join(normalized_target.split())

    if match := _JSON_VALID_RE.search(collapsed_target):
        column = match.group("column")
        return ConstraintViolationError(
            f"Structured value for {column} must be valid JSON text.",
            constraint_kind="check",
            columns=[column],
            raw_message=raw_message,
            suggestions=[
                "Provide valid JSON such as {} for an object or [] for a list.",
                "If you passed a plain string, wrap it in JSON or use the non-JSON field instead.",
            ],
        )

    if match := _PERCENT_RANGE_RE.search(collapsed_target):
        column = match.group("column")
        return ConstraintViolationError(
            f"Percentage value for {column} must be between 0 and 100.",
            constraint_kind="check",
            columns=[column],
            raw_message=raw_message,
            suggestions=[
                "Use an integer percentage from 0 through 100.",
                "If you mean progress, update the corresponding lifecycle state consistently as well.",
            ],
        )

    if "port > 0" in collapsed_target and "port <= 65535" in collapsed_target:
        return ConstraintViolationError(
            "Port must be within the valid network range 1-65535.",
            constraint_kind="check",
            columns=["port"],
            raw_message=raw_message,
            suggestions=[
                "Use a port number between 1 and 65535.",
                "If you intended the default SSH port, use 22.",
            ],
        )

    if match := _BOOLEAN_IN_RE.search(collapsed_target):
        column = match.group("column")
        return ConstraintViolationError(
            f"Boolean field {column} must use 0 or 1 at the database boundary.",
            constraint_kind="check",
            columns=[column],
            raw_message=raw_message,
            suggestions=[
                "Use 1 for true and 0 for false.",
                "If you are writing through the API or CLI, pass a boolean value and let PMS normalize it.",
            ],
        )

    if match := _TEXT_ENUM_IN_RE.search(collapsed_target):
        column = match.group("column")
        allowed_values = [
            value.strip().strip("'")
            for value in match.group("values").split(",")
            if value.strip()
        ]
        allowed_label = ", ".join(allowed_values)
        return ConstraintViolationError(
            f"Value for {column} must be one of: {allowed_label}.",
            constraint_kind="check",
            columns=[column],
            raw_message=raw_message,
            suggestions=[
                f"Use one of the allowed values: {allowed_label}.",
                "If you are mapping from a higher-level interface, normalize to the canonical stored value before writing.",
            ],
        )

    nullable_non_negative_match = _NULLABLE_NON_NEGATIVE_RE.search(collapsed_target)
    non_negative_match = _NON_NEGATIVE_RE.search(collapsed_target)
    if nullable_non_negative_match or non_negative_match:
        column = (
            nullable_non_negative_match.group("column")
            if nullable_non_negative_match
            else non_negative_match.group("column")
        )
        return ConstraintViolationError(
            f"Value for {column} must be non-negative.",
            constraint_kind="check",
            columns=[column],
            raw_message=raw_message,
            suggestions=[
                "Provide 0 or a positive value.",
                "If this is a derived count or cost, recompute it before writing instead of decrementing below zero.",
            ],
        )

    table, column = (
        _split_target(collapsed_target)
        if _looks_like_column_target(collapsed_target)
        else (None, None)
    )
    suggestions = [
        "Review allowed values and ranges for the affected fields.",
        "If this field stores JSON or structured content, verify the payload shape before retrying.",
    ]
    return ConstraintViolationError(
        "Constraint validation failed for the provided values. Review ranges, enums, and structured field formats.",
        constraint_kind="check",
        table=table,
        columns=[column] if column else [],
        raw_message=raw_message,
        suggestions=suggestions,
    )


def _looks_like_column_target(target: str) -> bool:
    if not target:
        return False
    if "." in target:
        return True
    return target.isidentifier()
