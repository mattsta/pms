#!/usr/bin/env python3
"""Audit interactive chooser retry semantics across duplicate-entity CLI surfaces."""

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
class InteractiveChooserSurfaceSpec:
    name: str
    args: tuple[str, ...]
    width: int
    input_text: str
    required_fragments: tuple[str, ...]


@dataclass(frozen=True)
class CliInteractiveChooserIssue:
    surface: str
    mode: str
    reason: str


SPECS: tuple[InteractiveChooserSurfaceSpec, ...] = (
    InteractiveChooserSurfaceSpec(
        name="task chooser",
        args=("task", "show", "Duplicate Task", "--project", "{project}", "--pick"),
        width=120,
        input_text="9\n2\n",
        required_fragments=(
            "Matching Tasks",
            "Pick task:",
            "Error: 9 is not in the range 1<=x<=2.",
            "Duplicate Task",
            "Project: Pick Project",
            "Status: todo",
            "Next:",
        ),
    ),
    InteractiveChooserSurfaceSpec(
        name="goal chooser",
        args=("goal", "summary", "Duplicate Goal", "--pick"),
        width=120,
        input_text="9\n2\n",
        required_fragments=(
            "Matching Goals",
            "Pick goal:",
            "Error: 9 is not in the range 1<=x<=2.",
            "Duplicate Goal",
            "Goal State: active | Progress: 0%",
            "Execution Consistency: unlinked_goal_execution_scope",
        ),
    ),
    InteractiveChooserSurfaceSpec(
        name="plan chooser",
        args=("plan", "show", "Duplicate Plan", "--project", "{project}", "--pick"),
        width=120,
        input_text="9\n2\n",
        required_fragments=(
            "Matching Plans",
            "Pick plan:",
            "Error: 9 is not in the range 1<=x<=2.",
            "Duplicate Plan",
            "Status: draft",
            "Content:",
            "{}",
        ),
    ),
    InteractiveChooserSurfaceSpec(
        name="objective chooser",
        args=("objective", "show", "Duplicate Objective", "--goal", "Goal A", "--pick"),
        width=120,
        input_text="9\n2\n",
        required_fragments=(
            "Matching Objectives",
            "Pick objective:",
            "Error: 9 is not in the range 1<=x<=2.",
            "Duplicate Objective",
            "Status: active",
            "Goal: Goal A",
            "Next:",
        ),
    ),
    InteractiveChooserSurfaceSpec(
        name="key-result chooser",
        args=(
            "keyresult",
            "show",
            "Duplicate KR",
            "--objective",
            "KR Parent",
            "--goal",
            "Goal A",
            "--pick",
        ),
        width=120,
        input_text="9\n2\n",
        required_fragments=(
            "Matching Key Results",
            "Pick key result:",
            "Error: 9 is not in the range 1<=x<=2.",
            "Duplicate KR",
            "Status: active",
            "Objective: KR Parent",
            "Next:",
        ),
    ),
)


def evaluate_surface_outputs(
    spec: InteractiveChooserSurfaceSpec,
    *,
    non_tty_output: str,
    tty_output: str,
) -> tuple[CliInteractiveChooserIssue, ...]:
    issues: list[CliInteractiveChooserIssue] = []
    if non_tty_output != strip_ansi(non_tty_output):
        issues.append(
            CliInteractiveChooserIssue(
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
                    CliInteractiveChooserIssue(
                        surface=spec.name,
                        mode=mode,
                        reason=f"missing required semantic fragment: {fragment}",
                    )
                )
    return tuple(issues)


def _seed_fixture(env: dict[str, str]) -> dict[str, str]:
    project_name = "Pick Project"

    init_result = run_cli(["init"], env, width=120)
    require_success(init_result, args=["init"])

    project_result = run_cli(["project", "create", project_name], env, width=120)
    require_success(project_result, args=["project", "create", project_name])

    run_cli(["task", "create", project_name, "Duplicate Task"], env, width=120)
    second_task_result = run_cli(
        ["task", "create", project_name, "Duplicate Task", "--format", "json"],
        env,
        width=120,
    )
    require_success(
        second_task_result,
        args=["task", "create", project_name, "Duplicate Task", "--format", "json"],
    )

    first_goal_result = run_cli(
        [
            "goal",
            "create",
            "Duplicate Goal",
            "--project",
            project_name,
            "--format",
            "json",
        ],
        env,
        width=120,
    )
    require_success(
        first_goal_result,
        args=[
            "goal",
            "create",
            "Duplicate Goal",
            "--project",
            project_name,
            "--format",
            "json",
        ],
    )
    first_goal_id = json.loads(first_goal_result.stdout)["goal"]["id"]
    second_goal_result = run_cli(
        [
            "goal",
            "create",
            "Duplicate Goal",
            "--project",
            project_name,
            "--format",
            "json",
        ],
        env,
        width=120,
    )
    require_success(
        second_goal_result,
        args=[
            "goal",
            "create",
            "Duplicate Goal",
            "--project",
            project_name,
            "--format",
            "json",
        ],
    )
    complete_goal_result = run_cli(["goal", "complete", first_goal_id], env, width=120)
    require_success(complete_goal_result, args=["goal", "complete", first_goal_id])

    goal_a_result = run_cli(
        ["goal", "create", "Goal A", "--project", project_name, "--format", "json"],
        env,
        width=120,
    )
    require_success(
        goal_a_result,
        args=[
            "goal",
            "create",
            "Goal A",
            "--project",
            project_name,
            "--format",
            "json",
        ],
    )

    first_objective_result = run_cli(
        [
            "objective",
            "create",
            "Duplicate Objective",
            "--goal",
            "Goal A",
            "--format",
            "json",
        ],
        env,
        width=120,
    )
    require_success(
        first_objective_result,
        args=[
            "objective",
            "create",
            "Duplicate Objective",
            "--goal",
            "Goal A",
            "--format",
            "json",
        ],
    )
    first_objective_id = json.loads(first_objective_result.stdout)["objective"]["id"]
    second_objective_result = run_cli(
        [
            "objective",
            "create",
            "Duplicate Objective",
            "--goal",
            "Goal A",
            "--format",
            "json",
        ],
        env,
        width=120,
    )
    require_success(
        second_objective_result,
        args=[
            "objective",
            "create",
            "Duplicate Objective",
            "--goal",
            "Goal A",
            "--format",
            "json",
        ],
    )
    complete_objective_result = run_cli(
        ["objective", "complete", first_objective_id, "--goal", "Goal A"],
        env,
        width=120,
    )
    require_success(
        complete_objective_result,
        args=["objective", "complete", first_objective_id, "--goal", "Goal A"],
    )

    kr_parent_result = run_cli(
        ["objective", "create", "KR Parent", "--goal", "Goal A", "--format", "json"],
        env,
        width=120,
    )
    require_success(
        kr_parent_result,
        args=[
            "objective",
            "create",
            "KR Parent",
            "--goal",
            "Goal A",
            "--format",
            "json",
        ],
    )
    first_key_result_result = run_cli(
        [
            "keyresult",
            "create",
            "Duplicate KR",
            "--objective",
            "KR Parent",
            "--goal",
            "Goal A",
        ],
        env,
        width=120,
    )
    require_success(
        first_key_result_result,
        args=[
            "keyresult",
            "create",
            "Duplicate KR",
            "--objective",
            "KR Parent",
            "--goal",
            "Goal A",
        ],
    )
    second_key_result_result = run_cli(
        [
            "keyresult",
            "create",
            "Duplicate KR",
            "--objective",
            "KR Parent",
            "--goal",
            "Goal A",
        ],
        env,
        width=120,
    )
    require_success(
        second_key_result_result,
        args=[
            "keyresult",
            "create",
            "Duplicate KR",
            "--objective",
            "KR Parent",
            "--goal",
            "Goal A",
        ],
    )

    first_plan_result = run_cli(
        [
            "plan",
            "create",
            "Duplicate Plan",
            "--project",
            project_name,
            "--content",
            "{}",
            "--output-format",
            "json",
        ],
        env,
        width=120,
    )
    require_success(
        first_plan_result,
        args=[
            "plan",
            "create",
            "Duplicate Plan",
            "--project",
            project_name,
            "--content",
            "{}",
            "--output-format",
            "json",
        ],
    )
    second_plan_result = run_cli(
        [
            "plan",
            "create",
            "Duplicate Plan",
            "--project",
            project_name,
            "--content",
            "{}",
            "--output-format",
            "json",
        ],
        env,
        width=120,
    )
    require_success(
        second_plan_result,
        args=[
            "plan",
            "create",
            "Duplicate Plan",
            "--project",
            project_name,
            "--content",
            "{}",
            "--output-format",
            "json",
        ],
    )

    return {"project": project_name}


def run_audit() -> tuple[CliInteractiveChooserIssue, ...]:
    env = with_temp_env("cli-interactive-chooser-audit-")
    fixture = _seed_fixture(env)
    issues: list[CliInteractiveChooserIssue] = []

    for spec in SPECS:
        rendered_args = [arg.format(**fixture) for arg in spec.args]
        non_tty_result = run_cli(
            rendered_args,
            env,
            width=spec.width,
            input_text=spec.input_text,
        )
        tty_returncode, tty_output = run_cli_tty(
            rendered_args,
            env,
            width=spec.width,
            input_text=spec.input_text,
        )

        if non_tty_result.returncode != 0:
            issues.append(
                CliInteractiveChooserIssue(
                    surface=spec.name,
                    mode="non_tty",
                    reason=f"command failed: {non_tty_result.stdout}{non_tty_result.stderr}",
                )
            )
            continue
        if tty_returncode != 0:
            issues.append(
                CliInteractiveChooserIssue(
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
        description="Audit interactive duplicate-entity chooser contracts across CLI surfaces."
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
            f"CLI interactive chooser contract audit\nchecked={checked} issues={len(issues)}"
        )
        for issue in issues:
            print(f"- {issue.surface} [{issue.mode}]: {issue.reason}")

    if args.check and issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
