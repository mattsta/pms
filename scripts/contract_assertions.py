"""Shared assertions for scenario contract scripts."""

from __future__ import annotations

CANONICAL_CLI_PREFIX = "uv run pms"


def canonical_cli_command(command_suffix: str) -> str:
    """Return the canonical runnable CLI command for a command suffix."""
    return f"{CANONICAL_CLI_PREFIX} {command_suffix}".strip()


def matches_canonical_cli_command(
    value: object,
    command_suffix: str,
) -> bool:
    """Return whether a value matches the canonical runnable CLI command."""
    if not isinstance(value, str):
        return False
    return value == canonical_cli_command(command_suffix)
