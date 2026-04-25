#!/usr/bin/env python3
"""PermissionRequest hook allowlist for PMS CLI/MCP usage."""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any

DEFAULT_COMMAND_PATTERNS = [
    r"^uv run pms\b",
    r"^pms\b",
]
DEFAULT_TOOL_PREFIXES = ["mcp__pms__"]


def _load_allow_patterns() -> list[str]:
    raw = os.environ.get("PMS_HOOK_ALLOWLIST_REGEX", "")
    if not raw:
        return DEFAULT_COMMAND_PATTERNS
    parts = [p.strip() for p in re.split(r"[,\n]+", raw) if p.strip()]
    return parts or DEFAULT_COMMAND_PATTERNS


def _allow_for_tool_name(tool_name: str) -> bool:
    for prefix in DEFAULT_TOOL_PREFIXES:
        if tool_name.startswith(prefix):
            return True
    return False


def _allow_for_command(command: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        if re.search(pattern, command):
            return True
    return False


def _emit_allow() -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PermissionRequest",
            "decision": {"behavior": "allow"},
        }
    }
    print(json.dumps(payload))


def main() -> int:
    try:
        payload: dict[str, Any] = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0

    tool_name = payload.get("tool_name", "") or ""
    tool_input = payload.get("tool_input") or {}
    command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""

    patterns = _load_allow_patterns()

    if _allow_for_tool_name(tool_name):
        _emit_allow()
        return 0

    if tool_name == "Bash" and command and _allow_for_command(command, patterns):
        _emit_allow()
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
