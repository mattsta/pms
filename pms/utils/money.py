"""Canonical money and price serialization helpers."""

from __future__ import annotations

from decimal import Decimal


def monetary_string(value: Decimal | float | int | str | None) -> str | None:
    """Serialize a monetary value into a plain decimal string for transport."""
    if value is None:
        return None

    decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
    rendered = format(decimal_value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    if rendered in {"", "-0"}:
        return "0"
    return rendered
