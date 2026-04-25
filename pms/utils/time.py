"""Time formatting helpers."""

from __future__ import annotations

from datetime import UTC, datetime

from pms.models.base import now_utc


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def format_relative(
    value: datetime | str | None,
    now: datetime | None = None,
    *,
    include_absolute: bool = True,
) -> str:
    """Format a datetime as relative age, optionally including the absolute timestamp."""
    if value is None:
        return "-"

    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return str(value)

    ref = _to_utc(now or now_utc())
    timestamp = _to_utc(value)
    delta = ref - timestamp
    seconds = int(delta.total_seconds())

    prefix = ""
    suffix = "ago"
    if seconds < 0:
        prefix = "in "
        suffix = ""
        seconds = abs(seconds)

    if seconds < 60:
        relative = f"{prefix}{seconds}s {suffix}".strip()
    elif seconds < 3600:
        relative = f"{prefix}{seconds // 60}m {suffix}".strip()
    elif seconds < 86400:
        relative = f"{prefix}{seconds // 3600}h {suffix}".strip()
    else:
        relative = f"{prefix}{seconds // 86400}d {suffix}".strip()

    if not include_absolute:
        return relative

    iso_stamp = timestamp.isoformat(timespec="minutes")
    if iso_stamp.endswith("+00:00"):
        iso_stamp = iso_stamp.replace("+00:00", "Z")
    return f"{relative} ({iso_stamp})"
