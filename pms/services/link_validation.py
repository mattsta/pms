"""Shared validation for optional linked entity IDs."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from pms.exceptions import ValidationError

_NULLISH_REFERENCE_LITERALS = {"null", "none", "nil", "undefined"}
_SUGGESTION_LIMIT = 5


@dataclass(frozen=True)
class ReferenceSuggestion:
    """Suggested canonical entity reference."""

    ref: str
    label: str | None = None
    match_kind: str = "candidate"

    def render(self) -> str:
        if self.label and self.label != self.ref:
            return f"{self.ref} ({self.label})"
        return self.ref


def normalize_optional_reference_id(
    value: str | None,
    *,
    field_name: str,
) -> str | None:
    """Normalize optional linked IDs and reject malformed literal placeholders."""
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        raise ValidationError(f"{field_name} cannot be empty", field_name)
    if normalized.lower() in _NULLISH_REFERENCE_LITERALS:
        raise ValidationError(
            f"{field_name} cannot be the literal placeholder '{normalized}'",
            field_name,
        )
    return normalized


async def validate_optional_reference_id(
    repo: Any,
    value: str | None,
    *,
    field_name: str,
    entity_label: str,
) -> str | None:
    """Ensure an optional linked ID is well-formed and resolves to a real entity."""
    normalized = normalize_optional_reference_id(value, field_name=field_name)
    if normalized is None:
        return None
    entity = await repo.get_by_id(normalized)
    if entity is None:
        suggestions = await suggest_reference_matches(repo, normalized)
        raise ValidationError(
            _format_missing_reference_message(
                normalized,
                field_name=field_name,
                entity_label=entity_label,
                suggestions=suggestions,
            ),
            field_name,
            details={
                "entity_label": entity_label,
                "value": normalized,
                "suggestions": [suggestion.render() for suggestion in suggestions],
            },
        )
    return normalized


async def validate_reference_ids(
    repo: Any,
    values: list[str] | tuple[str, ...] | None,
    *,
    field_name: str,
    entity_label: str,
) -> list[str] | None:
    """Validate a list of linked IDs, preserving order and removing duplicates."""
    if values is None:
        return None

    normalized_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = await validate_optional_reference_id(
            repo,
            value,
            field_name=field_name,
            entity_label=entity_label,
        )
        if normalized is None or normalized in seen:
            continue
        normalized_values.append(normalized)
        seen.add(normalized)
    return normalized_values


async def suggest_reference_matches(
    repo: Any,
    value: str,
    *,
    limit: int = _SUGGESTION_LIMIT,
) -> list[ReferenceSuggestion]:
    """Suggest likely entity references for a missing linked ID."""
    db = getattr(repo, "db", None)
    table_name = getattr(repo, "table_name", None)
    if db is None or not table_name:
        return []

    columns = await _get_table_columns(repo)
    if not columns:
        return []

    label_column = (
        "name" if "name" in columns else "title" if "title" in columns else None
    )
    order_column = (
        "updated_at"
        if "updated_at" in columns
        else "created_at"
        if "created_at" in columns
        else "id"
    )
    normalized_value = _normalize_search_text(value)
    compact_value = normalized_value.replace(" ", "")

    predicates = [
        "LOWER(id) = LOWER(?)",
        "LOWER(id) LIKE LOWER(?)",
        "LOWER(id) LIKE LOWER(?)",
    ]
    params: list[Any] = [value, f"{value}%", f"%{value}%"]

    if label_column:
        predicates.extend(
            [
                f"LOWER({label_column}) = LOWER(?)",
                f"LOWER({label_column}) LIKE LOWER(?)",
                f"LOWER({label_column}) LIKE LOWER(?)",
                f"REPLACE(LOWER({label_column}), ' ', '') LIKE ?",
            ]
        )
        params.extend([value, f"{value}%", f"%{value}%", f"%{compact_value}%"])

    query = f"""
        SELECT id, {label_column or "NULL"} AS label
        FROM {table_name}
        WHERE {" OR ".join(predicates)}
        ORDER BY {order_column} DESC
        LIMIT ?
    """
    rows = await db.fetch_all(query, tuple([*params, max(limit * 4, limit)]))

    suggestions: list[ReferenceSuggestion] = []
    seen: set[str] = set()
    for row in rows:
        ref = str(row["id"])
        if ref in seen:
            continue
        label = str(row["label"]) if row.get("label") is not None else None
        suggestions.append(
            ReferenceSuggestion(
                ref=ref,
                label=label,
                match_kind=_match_kind(value, ref, label),
            )
        )
        seen.add(ref)

    suggestions.sort(
        key=lambda suggestion: (
            -_match_score(value, suggestion.ref, suggestion.label),
            suggestion.label or "",
            suggestion.ref,
        )
    )
    return suggestions[:limit]


async def _get_table_columns(repo: Any) -> set[str]:
    db = getattr(repo, "db", None)
    table_name = getattr(repo, "table_name", None)
    if db is None or not table_name:
        return set()
    rows = await db.fetch_all(f"PRAGMA table_info({table_name})")
    return {str(row["name"]) for row in rows}


def _format_missing_reference_message(
    value: str,
    *,
    field_name: str,
    entity_label: str,
    suggestions: list[ReferenceSuggestion],
) -> str:
    entity_label_lower = entity_label.lower()
    exact_name_match = next(
        (
            suggestion
            for suggestion in suggestions
            if suggestion.match_kind == "exact_label"
        ),
        None,
    )
    if exact_name_match and exact_name_match.label:
        return (
            f"{field_name} expects a {entity_label_lower} ID. "
            f"'{value}' matches the {entity_label_lower} name '{exact_name_match.label}'. "
            f"Use '{exact_name_match.ref}' instead."
        )

    message = f"{entity_label} '{value}' not found for {field_name}"
    if suggestions:
        rendered = "; ".join(suggestion.render() for suggestion in suggestions)
        message += f". Did you mean: {rendered}?"
    return message


def _match_kind(value: str, ref: str, label: str | None) -> str:
    normalized_value = _normalize_search_text(value)
    normalized_ref = _normalize_search_text(ref)
    normalized_label = _normalize_search_text(label or "")

    if normalized_value == normalized_ref:
        return "exact_ref"
    if normalized_label and normalized_value == normalized_label:
        return "exact_label"
    if normalized_ref.startswith(normalized_value):
        return "prefix_ref"
    if normalized_label.startswith(normalized_value):
        return "prefix_label"
    if normalized_value in normalized_ref:
        return "contains_ref"
    if normalized_label and normalized_value in normalized_label:
        return "contains_label"
    return "fuzzy"


def _match_score(value: str, ref: str, label: str | None) -> int:
    normalized_value = _normalize_search_text(value)
    normalized_ref = _normalize_search_text(ref)
    normalized_label = _normalize_search_text(label or "")

    if normalized_value == normalized_ref:
        return 1000
    if normalized_label and normalized_value == normalized_label:
        return 950
    if normalized_ref.startswith(normalized_value):
        return 900
    if normalized_label.startswith(normalized_value):
        return 850
    if normalized_value in normalized_ref:
        return 800
    if normalized_label and normalized_value in normalized_label:
        return 750

    ref_ratio = SequenceMatcher(a=normalized_value, b=normalized_ref).ratio()
    label_ratio = (
        SequenceMatcher(a=normalized_value, b=normalized_label).ratio()
        if normalized_label
        else 0.0
    )
    return int(max(ref_ratio, label_ratio) * 100)


def _normalize_search_text(value: str) -> str:
    return " ".join(value.strip().lower().split())
