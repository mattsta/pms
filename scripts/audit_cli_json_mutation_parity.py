from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

APP_PATH = Path("pms/cli/app.py")
TARGET_COMMANDS: tuple[tuple[str, str], ...] = (
    ("queue", "create"),
    ("queue", "update"),
    ("project", "update"),
    ("product", "create"),
    ("product", "update"),
    ("org", "create"),
    ("org", "update"),
    ("team", "create"),
    ("team", "update"),
    ("portfolio", "create"),
    ("portfolio", "update"),
    ("program", "create"),
    ("program", "update"),
    ("goal", "update"),
    ("objective", "create"),
    ("objective", "update"),
)


@dataclass(frozen=True)
class AuditIssue:
    command_group: str
    action: str
    message: str


def _command_blocks() -> dict[tuple[str, str], str]:
    text = APP_PATH.read_text(encoding="utf-8")
    lines = text.splitlines()
    blocks: dict[tuple[str, str], str] = {}
    index = 0
    while index < len(lines):
        match = re.search(r'@(\w+)\.command\("(create|update)"\)', lines[index])
        if match is None:
            index += 1
            continue
        command_group = match.group(1)
        action = match.group(2)
        start = index
        cursor = index + 1
        while cursor < len(lines) and not lines[cursor].startswith("@async_command"):
            cursor += 1
        while cursor < len(lines) and not lines[cursor].lstrip().startswith(
            "async def "
        ):
            cursor += 1
        while cursor < len(lines) and not (
            lines[cursor].startswith("@") and not lines[cursor].startswith("@click")
        ):
            cursor += 1
        blocks[(command_group, action)] = "\n".join(lines[start:cursor])
        index = cursor
    return blocks


def run_audit() -> tuple[AuditIssue, ...]:
    blocks = _command_blocks()
    issues: list[AuditIssue] = []
    for command_group, action in TARGET_COMMANDS:
        block = blocks.get((command_group, action))
        if block is None:
            issues.append(
                AuditIssue(
                    command_group, action, "command block not found in pms/cli/app.py"
                )
            )
            continue
        if "--format" not in block:
            issues.append(AuditIssue(command_group, action, "missing --format option"))
        if "_payload_with_normalized_next_steps(" not in block:
            issues.append(
                AuditIssue(
                    command_group,
                    action,
                    "missing normalized machine-readable payload contract",
                )
            )
        if "_normalize_command_links(" not in block:
            issues.append(
                AuditIssue(
                    command_group,
                    action,
                    "missing normalized links in machine-readable payload",
                )
            )
    return tuple(issues)


def main() -> None:
    issues = run_audit()
    if issues:
        for issue in issues:
            print(f"{issue.command_group}.{issue.action}: {issue.message}")
        raise SystemExit(1)
    print(f"checked={len(TARGET_COMMANDS)} issues=0")


if __name__ == "__main__":
    main()
