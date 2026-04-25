"""Shared helpers for user-facing CLI command rendering."""

from __future__ import annotations

from pathlib import Path


def cli_command_prefix() -> str:
    value = (
        _env_value("PMS_INVOKE_ARGV0")
        or _env_value("PMS_CLI_ARGV0")
        or _env_value("PMS_ARGV0")
    )
    return value or "uv run pms"


def alternate_cli_command_prefix() -> str | None:
    value = _env_value("PMS_ALT_CLI_ARGV0")
    if value:
        return value
    installed_binary = Path.cwd() / ".bin" / "pms-client"
    if installed_binary.exists():
        from pms.config import get_settings

        settings = get_settings()
        return f"./.bin/pms-client --server {settings.server_base_url}"
    return None


def prefix_cli_command(command: str) -> str:
    candidate = command.strip()
    if candidate == "pms":
        return cli_command_prefix()
    if candidate.startswith("pms "):
        return f"{cli_command_prefix()} {candidate[4:]}"
    return candidate


def cli_command(command: str) -> str:
    candidate = command.strip()
    if not candidate:
        return candidate
    shell_prefixes = ("export ", "unset ", "cd ", "source ", "eval ")
    if candidate.startswith(shell_prefixes):
        return candidate
    canonical_prefix = cli_command_prefix()
    alternate_prefix = alternate_cli_command_prefix()
    if candidate == canonical_prefix or candidate.startswith(f"{canonical_prefix} "):
        return candidate
    if alternate_prefix and (
        candidate == alternate_prefix or candidate.startswith(f"{alternate_prefix} ")
    ):
        return candidate
    if candidate == "pms" or candidate.startswith("pms "):
        return prefix_cli_command(candidate)
    head = candidate.split(" ", 1)[0]
    if candidate.startswith("./") or candidate.startswith("/") or "=" in head:
        return candidate
    return prefix_cli_command(f"pms {candidate}")


def normalize_next_steps(*steps: str) -> list[str]:
    normalized_steps: list[str] = []
    seen: set[str] = set()
    for step in steps:
        candidate = cli_command(step.strip()) if step else ""
        if not candidate or candidate.lower() in {"-", "none", "n/a"}:
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        normalized_steps.append(candidate)
    return normalized_steps


def normalize_command_links(links: dict[str, str | None]) -> dict[str, str | None]:
    normalized: dict[str, str | None] = {}
    for key, value in links.items():
        normalized[key] = cli_command(value) if value is not None else None
    return normalized


def _env_value(name: str) -> str | None:
    from os import getenv

    value = getenv(name)
    if value:
        return value
    return None
