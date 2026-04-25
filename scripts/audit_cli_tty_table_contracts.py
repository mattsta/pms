#!/usr/bin/env python3
"""Audit task table semantics across TTY and non-interactive execution."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass

from scripts.cli_surface_audit_utils import (
    require_success,
    run_cli,
    run_cli_tty,
    strip_ansi,
    with_temp_env,
)


@dataclass(frozen=True)
class TableSurfaceSpec:
    name: str
    args: tuple[str, ...]
    width: int
    required_fragments: tuple[str, ...]


@dataclass(frozen=True)
class CliTtyTableIssue:
    surface: str
    mode: str
    reason: str


SPECS: tuple[TableSurfaceSpec, ...] = (
    TableSurfaceSpec(
        name="task review table",
        args=("task", "list", "--project", "{project}"),
        width=80,
        required_fragments=(
            "Task Review",
            "Focus",
            "Shown summary (current limit/page: 4 tasks): todo 2 | in_progress 1",
            "Total summary (all 4 matching tasks): todo 2 | in_progress 1",
            "graph walk:",
            "Ready",
            "Blocked",
        ),
    ),
    TableSurfaceSpec(
        name="task overview table",
        args=("task", "list", "--project", "{project}", "--view", "overview"),
        width=160,
        required_fragments=("Tasks", "Workflow", "Ref", "Overview Task"),
    ),
)


def _seed_fixture(env: dict[str, str]) -> str:
    project_name = "CLI Table Determinism Project"

    init_result = run_cli(["init"], env, width=120)
    require_success(init_result, args=["init"])

    project_result = run_cli(["project", "create", project_name], env, width=120)
    require_success(project_result, args=["project", "create", project_name])

    focus_result = run_cli(
        ["task", "add", project_name, "Focus Review Task", "--format", "json"],
        env,
        width=120,
    )
    require_success(
        focus_result,
        args=["task", "add", project_name, "Focus Review Task", "--format", "json"],
    )
    focus_task_id = json.loads(focus_result.stdout)["task"]["id"]

    overview_result = run_cli(
        ["task", "add", project_name, "Overview Task", "--format", "json"],
        env,
        width=120,
    )
    require_success(
        overview_result,
        args=["task", "add", project_name, "Overview Task", "--format", "json"],
    )

    start_result = run_cli(["task", "start", focus_task_id], env, width=120)
    require_success(start_result, args=["task", "start", focus_task_id])

    ready_result = run_cli(
        ["task", "add", project_name, "Ready Review Task"],
        env,
        width=120,
    )
    require_success(
        ready_result, args=["task", "add", project_name, "Ready Review Task"]
    )

    blocked_result = run_cli(
        ["task", "add", project_name, "Blocked Review Task", "--format", "json"],
        env,
        width=120,
    )
    require_success(
        blocked_result,
        args=["task", "add", project_name, "Blocked Review Task", "--format", "json"],
    )
    blocked_task_id = json.loads(blocked_result.stdout)["task"]["id"]

    block_result = run_cli(
        ["task", "block", blocked_task_id, "--reason", "waiting"],
        env,
        width=120,
    )
    require_success(
        block_result,
        args=["task", "block", blocked_task_id, "--reason", "waiting"],
    )

    return project_name


def run_audit() -> tuple[CliTtyTableIssue, ...]:
    env = with_temp_env("cli-tty-table-audit-")
    project_name = _seed_fixture(env)
    issues: list[CliTtyTableIssue] = []

    for spec in SPECS:
        rendered_args = [arg.format(project=project_name) for arg in spec.args]
        non_tty_result = run_cli(rendered_args, env, width=spec.width)
        tty_returncode, tty_output = run_cli_tty(rendered_args, env, width=spec.width)

        if non_tty_result.returncode != 0:
            issues.append(
                CliTtyTableIssue(
                    surface=spec.name,
                    mode="non_tty",
                    reason=f"command failed: {non_tty_result.stdout}{non_tty_result.stderr}",
                )
            )
            continue
        if tty_returncode != 0:
            issues.append(
                CliTtyTableIssue(
                    surface=spec.name,
                    mode="tty",
                    reason=f"command failed: {tty_output}",
                )
            )
            continue

        if non_tty_result.stdout != strip_ansi(non_tty_result.stdout):
            issues.append(
                CliTtyTableIssue(
                    surface=spec.name,
                    mode="non_tty",
                    reason="non-interactive output still contains ANSI escape sequences",
                )
            )

        normalized_outputs = {
            "non_tty": strip_ansi(non_tty_result.stdout),
            "tty": strip_ansi(tty_output),
        }
        for mode, normalized in normalized_outputs.items():
            for fragment in spec.required_fragments:
                if fragment not in normalized:
                    issues.append(
                        CliTtyTableIssue(
                            surface=spec.name,
                            mode=mode,
                            reason=f"missing required semantic fragment: {fragment}",
                        )
                    )
    return tuple(issues)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit task-table semantics across TTY and non-interactive execution."
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON payload")
    parser.add_argument("--check", action="store_true", help="Exit non-zero on issues")
    args = parser.parse_args()

    issues = run_audit()
    checked = len(SPECS)
    if args.json:
        print(
            json.dumps(
                {
                    "checked": checked,
                    "issues": [
                        {
                            "surface": issue.surface,
                            "mode": issue.mode,
                            "reason": issue.reason,
                        }
                        for issue in issues
                    ],
                },
                indent=2,
            )
        )
    else:
        print(f"CLI TTY table contract audit\nchecked={checked} issues={len(issues)}")
        for issue in issues:
            print(f"- {issue.surface} [{issue.mode}]: {issue.reason}")

    if args.check and issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
