#!/usr/bin/env python3
"""Audit text-summary semantics across TTY and non-interactive execution."""

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
class TextSummarySurfaceSpec:
    name: str
    args: tuple[str, ...]
    width: int
    required_fragments: tuple[str, ...]


@dataclass(frozen=True)
class CliTextSummaryIssue:
    surface: str
    mode: str
    reason: str


SPECS: tuple[TextSummarySurfaceSpec, ...] = (
    TextSummarySurfaceSpec(
        name="task timeline summary",
        args=("task", "timeline", "{task_id}"),
        width=120,
        required_fragments=(
            "Task: Timeline Focus Task",
            "Project: CLI Text Summary Project",
            "Progress: 35% | Updates: 1",
        ),
    ),
    TextSummarySurfaceSpec(
        name="project summary",
        args=("project", "summary", "{project}"),
        width=120,
        required_fragments=(
            "CLI Text Summary Project",
            "Status: active",
            "Recent Activity: 1",
            "Execution Focus: Timeline Focus Task",
            "Next:",
        ),
    ),
    TextSummarySurfaceSpec(
        name="goal summary",
        args=("goal", "summary", "{goal_id}"),
        width=120,
        required_fragments=(
            "CLI Text Goal",
            "Goal State: active | Progress: 0%",
            "Effective Rollup: active | 35%",
            "Execution Focus: Timeline Focus Task",
            "Completion Criteria: 0 defined",
            "Next:",
        ),
    ),
    TextSummarySurfaceSpec(
        name="plan show summary",
        args=("plan", "show", "CLI Text Plan", "--project", "{project}"),
        width=120,
        required_fragments=(
            "CLI Text Plan",
            "Status: draft",
            "Tasks (1):",
            "Execution Focus: Timeline Focus Task",
            "Content:",
            "{}",
            "Next:",
        ),
    ),
    TextSummarySurfaceSpec(
        name="work daily summary",
        args=("work", "daily", "--scope-type", "project", "--scope", "{project}"),
        width=120,
        required_fragments=(
            "Daily Review (project)",
            "Scope: CLI Text Summary Project",
            "Focus: Timeline Focus Task",
            "Why: active execution in progress",
            "Creates: no new state; this command reads and summarizes accumulated live state.",
            "Next:",
        ),
    ),
)


def evaluate_surface_outputs(
    spec: TextSummarySurfaceSpec,
    *,
    non_tty_output: str,
    tty_output: str,
) -> tuple[CliTextSummaryIssue, ...]:
    issues: list[CliTextSummaryIssue] = []
    if non_tty_output != strip_ansi(non_tty_output):
        issues.append(
            CliTextSummaryIssue(
                surface=spec.name,
                mode="non_tty",
                reason="non-interactive output still contains ANSI escape sequences",
            )
        )

    normalized_outputs = {
        "non_tty": strip_ansi(non_tty_output),
        "tty": strip_ansi(tty_output),
    }
    for mode, normalized in normalized_outputs.items():
        for fragment in spec.required_fragments:
            if fragment not in normalized:
                issues.append(
                    CliTextSummaryIssue(
                        surface=spec.name,
                        mode=mode,
                        reason=f"missing required semantic fragment: {fragment}",
                    )
                )
    return tuple(issues)


def _seed_fixture(env: dict[str, str]) -> dict[str, str]:
    project_name = "CLI Text Summary Project"

    init_result = run_cli(["init"], env, width=120)
    require_success(init_result, args=["init"])

    project_result = run_cli(["project", "create", project_name], env, width=120)
    require_success(project_result, args=["project", "create", project_name])

    task_result = run_cli(
        ["task", "add", project_name, "Timeline Focus Task", "--format", "json"],
        env,
        width=120,
    )
    require_success(
        task_result,
        args=["task", "add", project_name, "Timeline Focus Task", "--format", "json"],
    )
    task_id = json.loads(task_result.stdout)["task"]["id"]

    start_result = run_cli(["task", "start", task_id], env, width=120)
    require_success(start_result, args=["task", "start", task_id])

    progress_result = run_cli(
        ["task", "progress", task_id, "35", "Working", "--by", "tester"],
        env,
        width=120,
    )
    require_success(
        progress_result,
        args=["task", "progress", task_id, "35", "Working", "--by", "tester"],
    )

    goal_result = run_cli(
        [
            "goal",
            "create",
            "CLI Text Goal",
            "--project",
            project_name,
            "--format",
            "json",
        ],
        env,
        width=120,
    )
    require_success(
        goal_result,
        args=[
            "goal",
            "create",
            "CLI Text Goal",
            "--project",
            project_name,
            "--format",
            "json",
        ],
    )
    goal_id = json.loads(goal_result.stdout)["goal"]["id"]

    plan_result = run_cli(
        [
            "plan",
            "create",
            "CLI Text Plan",
            "--project",
            project_name,
            "--task-id",
            task_id,
            "--content",
            "{}",
            "--output-format",
            "json",
        ],
        env,
        width=120,
    )
    require_success(
        plan_result,
        args=[
            "plan",
            "create",
            "CLI Text Plan",
            "--project",
            project_name,
            "--task-id",
            task_id,
            "--content",
            "{}",
            "--output-format",
            "json",
        ],
    )

    return {
        "project": project_name,
        "task_id": task_id,
        "goal_id": goal_id,
    }


def run_audit() -> tuple[CliTextSummaryIssue, ...]:
    env = with_temp_env("cli-text-summary-audit-")
    fixture = _seed_fixture(env)
    issues: list[CliTextSummaryIssue] = []

    for spec in SPECS:
        rendered_args = [arg.format(**fixture) for arg in spec.args]
        non_tty_result = run_cli(rendered_args, env, width=spec.width)
        tty_returncode, tty_output = run_cli_tty(rendered_args, env, width=spec.width)

        if non_tty_result.returncode != 0:
            issues.append(
                CliTextSummaryIssue(
                    surface=spec.name,
                    mode="non_tty",
                    reason=f"command failed: {non_tty_result.stdout}{non_tty_result.stderr}",
                )
            )
            continue
        if tty_returncode != 0:
            issues.append(
                CliTextSummaryIssue(
                    surface=spec.name,
                    mode="tty",
                    reason=f"command failed: {tty_output}",
                )
            )
            continue

        issues.extend(
            evaluate_surface_outputs(
                spec,
                non_tty_output=non_tty_result.stdout,
                tty_output=tty_output,
            )
        )

    return tuple(issues)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit text-summary CLI semantics across TTY and non-interactive execution."
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
        print(
            f"CLI text summary contract audit\nchecked={checked} issues={len(issues)}"
        )
        for issue in issues:
            print(f"- {issue.surface} [{issue.mode}]: {issue.reason}")

    if args.check and issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
