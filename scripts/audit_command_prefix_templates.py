"""Audit interop guidance surfaces for invocation-agnostic CLI command templates."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROUTE_ROOT = REPO_ROOT / "pms" / "api" / "routes"
CLI_APP_PATH = REPO_ROOT / "pms" / "cli" / "app.py"
WORK_DAILY_SERVICE_PATH = REPO_ROOT / "pms" / "services" / "work_daily_service.py"
RUST_CLIENT_MAIN_PATH = REPO_ROOT / "client-rust" / "src" / "main.rs"
RUST_CLIENT_HANDLERS_PATH = REPO_ROOT / "client-rust" / "src" / "handlers.rs"
CLI_COMMAND_ASSIGNMENT_RE = re.compile(r"cli_command\s*=\s*(.+)")
CLI_HELPER_BLOCKS = (
    "class CommandFocusTarget:",
    "def _scope_resolution_next_steps(",
    '@cli.command(name="quickstart")',
    '@loop.command("prompt")',
    '@auth.command("init")',
    '@auth.command("recover-local-admin")',
    "@runtime.command(",
    '@queue.command("list")',
    '@queue.command("run")',
    '@task.command("available")',
    '@task.command("stale")',
)
SERVICE_HELPER_BLOCKS = {
    WORK_DAILY_SERVICE_PATH: ("def to_dict(self) -> ModelObject:",),
}
RUST_GUIDANCE_PATHS = (
    RUST_CLIENT_MAIN_PATH,
    RUST_CLIENT_HANDLERS_PATH,
)


@dataclass(frozen=True)
class CommandPrefixTemplateIssue:
    file: str
    line: int
    reason: str


def run_audit() -> tuple[CommandPrefixTemplateIssue, ...]:
    issues: list[CommandPrefixTemplateIssue] = []

    for path in sorted(API_ROUTE_ROOT.glob("*.py")):
        for line_number, line in enumerate(path.read_text().splitlines(), start=1):
            match = CLI_COMMAND_ASSIGNMENT_RE.search(line)
            if match is None:
                continue
            assignment = match.group(1).strip()
            if "cli_command_template(" in assignment:
                continue
            if '"uv run pms' in assignment or "'uv run pms" in assignment:
                issues.append(
                    CommandPrefixTemplateIssue(
                        file=str(path.relative_to(REPO_ROOT)),
                        line=line_number,
                        reason="hardcoded uv run pms in API cli_command guidance",
                    )
                )
                continue
            if '"pms ' in assignment or "'pms " in assignment:
                issues.append(
                    CommandPrefixTemplateIssue(
                        file=str(path.relative_to(REPO_ROOT)),
                        line=line_number,
                        reason="bare pms command in API cli_command guidance",
                    )
                )

    issues.extend(_cli_helper_issues())
    issues.extend(_service_helper_issues())
    issues.extend(_rust_guidance_issues())

    return tuple(issues)


def _cli_helper_issues() -> list[CommandPrefixTemplateIssue]:
    issues: list[CommandPrefixTemplateIssue] = []
    lines = CLI_APP_PATH.read_text().splitlines()
    in_relevant_block = False

    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if any(stripped.startswith(block) for block in CLI_HELPER_BLOCKS):
            in_relevant_block = True
        elif in_relevant_block and (
            stripped.startswith("def ")
            or stripped.startswith("class ")
            or stripped.startswith("@cli.command(")
        ):
            in_relevant_block = False
            if any(stripped.startswith(block) for block in CLI_HELPER_BLOCKS):
                in_relevant_block = True

        if not in_relevant_block:
            continue
        if '"uv run pms' in line or "'uv run pms" in line:
            issues.append(
                CommandPrefixTemplateIssue(
                    file=str(CLI_APP_PATH.relative_to(REPO_ROOT)),
                    line=line_number,
                    reason="hardcoded uv run pms in shared CLI guidance surface",
                )
            )
            continue
        if '"pms ' in line or "'pms " in line:
            issues.append(
                CommandPrefixTemplateIssue(
                    file=str(CLI_APP_PATH.relative_to(REPO_ROOT)),
                    line=line_number,
                    reason="bare pms command in shared CLI guidance surface",
                )
            )
    return issues


def _service_helper_issues() -> list[CommandPrefixTemplateIssue]:
    issues: list[CommandPrefixTemplateIssue] = []
    for path, blocks in SERVICE_HELPER_BLOCKS.items():
        lines = path.read_text().splitlines()
        in_relevant_block = False
        for line_number, line in enumerate(lines, start=1):
            stripped = line.strip()
            if any(stripped.startswith(block) for block in blocks):
                in_relevant_block = True
            elif in_relevant_block and stripped.startswith("def "):
                in_relevant_block = False
                if any(stripped.startswith(block) for block in blocks):
                    in_relevant_block = True

            if not in_relevant_block:
                continue
            if '"uv run pms' in line or "'uv run pms" in line:
                issues.append(
                    CommandPrefixTemplateIssue(
                        file=str(path.relative_to(REPO_ROOT)),
                        line=line_number,
                        reason="hardcoded uv run pms in service-generated guidance surface",
                    )
                )
                continue
            if '"pms ' in line or "'pms " in line:
                issues.append(
                    CommandPrefixTemplateIssue(
                        file=str(path.relative_to(REPO_ROOT)),
                        line=line_number,
                        reason="bare pms command in service-generated guidance surface",
                    )
                )
        return issues
    return issues


def _rust_guidance_issues() -> list[CommandPrefixTemplateIssue]:
    issues: list[CommandPrefixTemplateIssue] = []
    for path in RUST_GUIDANCE_PATHS:
        for line_number, line in enumerate(path.read_text().splitlines(), start=1):
            if '"uv run pms' in line:
                issues.append(
                    CommandPrefixTemplateIssue(
                        file=str(path.relative_to(REPO_ROOT)),
                        line=line_number,
                        reason="hardcoded uv run pms in Rust-generated guidance surface",
                    )
                )
                continue
            if '"pms ' in line:
                issues.append(
                    CommandPrefixTemplateIssue(
                        file=str(path.relative_to(REPO_ROOT)),
                        line=line_number,
                        reason="bare pms command in Rust-generated guidance surface",
                    )
                )
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit interop guidance surfaces for command-template usage."
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON payload")
    parser.add_argument("--check", action="store_true", help="Exit non-zero on issues")
    args = parser.parse_args()

    issues = run_audit()
    checked = sum(1 for _ in API_ROUTE_ROOT.glob("*.py"))
    if args.json:
        print(
            json.dumps(
                {
                    "checked": checked,
                    "issues": [
                        {"file": issue.file, "line": issue.line, "reason": issue.reason}
                        for issue in issues
                    ],
                },
                indent=2,
            )
        )
    else:
        print(f"Command prefix template audit\nchecked={checked} issues={len(issues)}")
        for issue in issues:
            print(f"- {issue.file}:{issue.line}: {issue.reason}")

    if args.check and issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
