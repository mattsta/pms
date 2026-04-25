"""Audit CLI option parity for key command families."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import click

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from pms.cli.app import cli  # noqa: E402


@dataclass(frozen=True)
class CommandOptionExpectation:
    """Expected options for a CLI command path."""

    path: str
    required_options: tuple[str, ...]


EXPECTATIONS: tuple[CommandOptionExpectation, ...] = (
    CommandOptionExpectation(
        path="project create",
        required_options=("product", "org", "portfolio", "program", "format"),
    ),
    CommandOptionExpectation(
        path="project add",
        required_options=("product", "org", "portfolio", "program", "format"),
    ),
    CommandOptionExpectation(
        path="goal create",
        required_options=("project", "project-id", "product", "product-id", "format"),
    ),
    CommandOptionExpectation(
        path="task show",
        required_options=("project", "pick", "format"),
    ),
    CommandOptionExpectation(
        path="task update",
        required_options=("project", "pick", "format"),
    ),
    CommandOptionExpectation(
        path="task complete",
        required_options=("project", "pick", "by", "format"),
    ),
    CommandOptionExpectation(
        path="task start",
        required_options=("project", "pick", "by", "format"),
    ),
    CommandOptionExpectation(
        path="task block",
        required_options=("project", "pick", "by"),
    ),
    CommandOptionExpectation(
        path="task unblock",
        required_options=("project", "pick", "by"),
    ),
    CommandOptionExpectation(
        path="task review",
        required_options=("project", "pick", "by"),
    ),
    CommandOptionExpectation(
        path="task reopen",
        required_options=("project", "pick", "by"),
    ),
    CommandOptionExpectation(
        path="task resolve",
        required_options=("project", "pick", "format"),
    ),
    CommandOptionExpectation(
        path="work snapshot",
        required_options=("scope-type", "scope", "scope-id", "format"),
    ),
    CommandOptionExpectation(
        path="work review",
        required_options=("scope-type", "scope", "scope-id", "format"),
    ),
    CommandOptionExpectation(
        path="work daily",
        required_options=("scope-type", "scope", "scope-id", "format"),
    ),
    CommandOptionExpectation(
        path="test server ensure-local",
        required_options=("project", "project-id", "format"),
    ),
    CommandOptionExpectation(
        path="quickstart",
        required_options=("format",),
    ),
    CommandOptionExpectation(
        path="start",
        required_options=("format",),
    ),
    CommandOptionExpectation(
        path="dashboard",
        required_options=("format",),
    ),
    CommandOptionExpectation(
        path="capabilities info",
        required_options=("format",),
    ),
)


def _resolve_command(root: click.BaseCommand, path: str) -> click.Command | None:
    current: click.BaseCommand = root
    for part in path.split():
        if not isinstance(current, click.Group):
            return None
        child = current.commands.get(part)
        if child is None:
            return None
        current = child
    if isinstance(current, click.Command):
        return current
    return None


def _option_names(command: click.Command) -> set[str]:
    names: set[str] = set()
    for param in command.params:
        if not isinstance(param, click.Option):
            continue
        for opt in param.opts + param.secondary_opts:
            if not opt.startswith("--"):
                continue
            names.add(opt[2:])
    return names


def audit_option_parity() -> dict[str, object]:
    issues: list[dict[str, object]] = []
    checked_commands: list[dict[str, object]] = []

    for expectation in EXPECTATIONS:
        command = _resolve_command(cli, expectation.path)
        if command is None:
            issues.append(
                {
                    "path": expectation.path,
                    "missing_command": True,
                    "missing_options": list(expectation.required_options),
                }
            )
            continue

        option_names = _option_names(command)
        missing_options = sorted(
            option
            for option in expectation.required_options
            if option not in option_names
        )
        checked_commands.append(
            {
                "path": expectation.path,
                "required_options": list(expectation.required_options),
                "actual_options": sorted(option_names),
                "missing_options": missing_options,
            }
        )
        if missing_options:
            issues.append(
                {
                    "path": expectation.path,
                    "missing_command": False,
                    "missing_options": missing_options,
                }
            )

    return {
        "checked": len(EXPECTATIONS),
        "issues": issues,
        "commands": checked_commands,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit CLI option parity.")
    parser.add_argument("--json", action="store_true", help="Emit JSON payload")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero when any expected option is missing",
    )
    args = parser.parse_args()

    audit = audit_option_parity()
    if args.json:
        print(json.dumps(audit, indent=2))
    else:
        print(
            "CLI option parity audit\n"
            f"checked={audit['checked']} issues={len(audit['issues'])}"
        )
        for issue in audit["issues"]:
            print(f"- {issue['path']}: missing {', '.join(issue['missing_options'])}")

    if args.check and audit["issues"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
