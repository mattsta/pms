"""Shared API typing primitives."""

from __future__ import annotations

from datetime import datetime
from typing import NotRequired, TypedDict

type JsonScalar = str | int | float | bool | datetime | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]


class PaginatedResponse[T](TypedDict):
    """Standard page payload used by list endpoints."""

    items: list[T]
    total_count: int
    offset: int
    limit: int
    links: NotRequired[JsonObject]
    next_steps: NotRequired[list[str]]
    params: NotRequired[JsonObject]
