#!/usr/bin/env python3
"""Audit parity between MCP registry metadata and server-exported tool names."""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from pms.tools.registry import TOOL_REGISTRY
from pms.tools.server import PMS_TOOL_NAMES


@dataclass(frozen=True)
class McpToolParityIssue:
    """Single MCP parity issue."""

    reason: str


def run_audit() -> tuple[McpToolParityIssue, ...]:
    """Return MCP parity issues between registry and server export lists."""
    registry_names = {tool.mcp_name for tool in TOOL_REGISTRY}
    server_names = set(PMS_TOOL_NAMES)

    issues: list[McpToolParityIssue] = []

    missing_in_server = sorted(registry_names - server_names)
    missing_in_registry = sorted(server_names - registry_names)

    if missing_in_server:
        issues.append(
            McpToolParityIssue(
                reason="Registry tools missing from server exports: "
                + ", ".join(missing_in_server)
            )
        )
    if missing_in_registry:
        issues.append(
            McpToolParityIssue(
                reason="Server-exported tools missing from registry metadata: "
                + ", ".join(missing_in_registry)
            )
        )

    return tuple(issues)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Exit non-zero on issues")
    args = parser.parse_args()

    issues = run_audit()
    print(f"MCP tool parity audit\nchecked={len(TOOL_REGISTRY)} issues={len(issues)}")
    for issue in issues:
        print(f"- {issue.reason}")

    if args.check and issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
