#!/usr/bin/env python3
"""Audit recent-terminal summary semantics across text-first CLI surfaces."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass

from scripts.cli_surface_audit_utils import (
    require_success,
    run_cli,
    run_cli_tty,
    strip_ansi,
    with_temp_env,
)


@dataclass(frozen=True)
class RecentTerminalSurfaceSpec:
    name: str
    args: tuple[str, ...]
    width: int
    required_fragments: tuple[str, ...]


@dataclass(frozen=True)
class CliRecentTerminalSummaryIssue:
    surface: str
    mode: str
    reason: str


SPECS: tuple[RecentTerminalSurfaceSpec, ...] = (
    RecentTerminalSurfaceSpec(
        name="start recent terminal summary",
        args=("start",),
        width=120,
        required_fragments=(
            "Start -> Go Guide",
            "Recent terminal work:",
            "Recently completed scoped work remains terminal",
            "latest Completed Visible Plan Project",
            'uv run pms project show "Completed Visible Plan Project" --format json',
        ),
    ),
    RecentTerminalSurfaceSpec(
        name="dashboard recent terminal summary",
        args=("dashboard",),
        width=120,
        required_fragments=(
            "Dashboard Overview",
            "Scope: Instance-wide dashboard view.",
            "Freshest Visible Activity: Completed Visible Plan Project",
            "Freshest Visible Transition: Completed Visible Plan Project",
            "Recently Completed Projects:",
            "Completed-scope shortcuts:",
            'uv run pms project show "Completed Visible Plan Project" --format json',
            'uv run pms project show "Completed Visible Project" --format json',
        ),
    ),
    RecentTerminalSurfaceSpec(
        name="plan list recent terminal summary",
        args=("plan", "list"),
        width=120,
        required_fragments=(
            "Scope: Instance-wide plan list view.",
            "Projects Without Plans",
            "These projects have fresh graph activity but no persisted plan row",
            "Recently Completed Plans:",
            "Execution State: all surfaced plans are already terminal",
            "Recently completed plans remain terminal.",
            "Completed Visible Plan [Completed Visible Plan Project]",
        ),
    ),
)


def evaluate_surface_outputs(
    spec: RecentTerminalSurfaceSpec,
    *,
    non_tty_output: str,
    tty_output: str,
) -> tuple[CliRecentTerminalSummaryIssue, ...]:
    issues: list[CliRecentTerminalSummaryIssue] = []
    if non_tty_output != strip_ansi(non_tty_output):
        issues.append(
            CliRecentTerminalSummaryIssue(
                surface=spec.name,
                mode="non_tty",
                reason="non-interactive output still contains ANSI escape sequences",
            )
        )

    normalized_outputs = {
        "non_tty": _normalize_semantic_text(strip_ansi(non_tty_output)),
        "tty": _normalize_semantic_text(strip_ansi(tty_output)),
    }
    for mode, normalized in normalized_outputs.items():
        for fragment in spec.required_fragments:
            if _normalize_semantic_text(fragment) not in normalized:
                issues.append(
                    CliRecentTerminalSummaryIssue(
                        surface=spec.name,
                        mode=mode,
                        reason=f"missing required semantic fragment: {fragment}",
                    )
                )
    return tuple(issues)


def _normalize_semantic_text(text: str) -> str:
    return " ".join(text.split())


def _extract_task_id(output: str) -> str:
    match = re.search(r"ID:\s*([0-9a-f-]{36})", output)
    if match is None:
        raise RuntimeError(f"unable to extract task id from output:\n{output}")
    return match.group(1)


def _seed_completed_project(env: dict[str, str], name: str) -> None:
    project_result = run_cli(["project", "create", name], env, width=120)
    require_success(project_result, args=["project", "create", name])
    task_result = run_cli(["task", "add", name, "Done Task"], env, width=120)
    require_success(task_result, args=["task", "add", name, "Done Task"])
    task_id = _extract_task_id(task_result.stdout)
    start_result = run_cli(["task", "start", task_id, "--by", "tester"], env, width=120)
    require_success(start_result, args=["task", "start", task_id, "--by", "tester"])
    complete_result = run_cli(
        ["task", "complete", task_id, "--by", "tester"], env, width=120
    )
    require_success(
        complete_result, args=["task", "complete", task_id, "--by", "tester"]
    )
    project_complete_result = run_cli(["project", "complete", name], env, width=120)
    require_success(project_complete_result, args=["project", "complete", name])


def _seed_fixture(env: dict[str, str]) -> None:
    init_result = run_cli(["init"], env, width=120)
    require_success(init_result, args=["init"])

    _seed_completed_project(env, "Completed Start Project")
    _seed_completed_project(env, "Completed Visible Project")

    plan_project_result = run_cli(
        ["project", "create", "Completed Visible Plan Project"], env, width=120
    )
    require_success(
        plan_project_result,
        args=["project", "create", "Completed Visible Plan Project"],
    )
    plan_result = run_cli(
        [
            "plan",
            "create",
            "Completed Visible Plan",
            "--project",
            "Completed Visible Plan Project",
            "--status",
            "completed",
            "--content",
            "{}",
        ],
        env,
        width=120,
    )
    require_success(
        plan_result,
        args=[
            "plan",
            "create",
            "Completed Visible Plan",
            "--project",
            "Completed Visible Plan Project",
            "--status",
            "completed",
            "--content",
            "{}",
        ],
    )


def run_audit() -> tuple[CliRecentTerminalSummaryIssue, ...]:
    env = with_temp_env("cli-recent-terminal-summary-audit-")
    _seed_fixture(env)
    issues: list[CliRecentTerminalSummaryIssue] = []

    for spec in SPECS:
        non_tty_result = run_cli(spec.args, env, width=spec.width)
        tty_returncode, tty_output = run_cli_tty(spec.args, env, width=spec.width)

        if non_tty_result.returncode != 0:
            issues.append(
                CliRecentTerminalSummaryIssue(
                    surface=spec.name,
                    mode="non_tty",
                    reason=f"command failed: {non_tty_result.stdout}{non_tty_result.stderr}",
                )
            )
            continue
        if tty_returncode != 0:
            issues.append(
                CliRecentTerminalSummaryIssue(
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
        description="Audit recent-terminal CLI summary contracts."
    )
    parser.add_argument("--check", action="store_true", help="Exit non-zero on issues.")
    args = parser.parse_args()

    issues = run_audit()
    print("CLI recent-terminal summary contract audit")
    print(f"checked={len(SPECS)} issues={len(issues)}")
    for issue in issues:
        print(f"- {issue.surface} [{issue.mode}] {issue.reason}")

    if args.check and issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
