#!/usr/bin/env python3
"""Audit goal execution scoping in isolated multi-goal and explicit-link scenarios."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class GoalExecutionScopeIssue:
    reason: str


def _with_temp_env() -> dict[str, str]:
    temp_dir = Path(
        tempfile.mkdtemp(prefix="goal-execution-scope-audit-", dir=REPO_ROOT / ".tmp")
    )
    env = os.environ.copy()
    env["PMS_DATA_DIR"] = str(temp_dir)
    env["PMS_DATABASE_PATH"] = str(temp_dir / "audit.db")
    env["PMS_LOG_DIR"] = str(temp_dir / "logs")
    env["PMS_ENV_FILE"] = str(temp_dir / ".env")
    env["PMS_WRITE_MODE"] = "direct"
    env["PMS_CLI_ARGV0"] = "uv run pms"
    env.pop("PMS_SERVER_BASE_URL", None)
    env.pop("PMS_API_KEY", None)
    env.pop("PMS_API_KEY_PATH", None)
    return env


def _run_cli(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "pms", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _invoke_json(args: list[str], env: dict[str, str]) -> object:
    result = _run_cli(args, env)
    if result.returncode != 0:
        raise RuntimeError(
            f"command failed: {' '.join(args)}\n{result.stdout}{result.stderr}"
        )
    return json.loads(result.stdout)


def _seed_fixture(env: dict[str, str]) -> dict[str, object]:
    init_result = _run_cli(["init"], env)
    if init_result.returncode != 0:
        raise RuntimeError(init_result.stdout + init_result.stderr)

    project_payload = _invoke_json(
        ["project", "create", "Goal Scope Audit Project", "--format", "json"],
        env,
    )
    project_id = str(project_payload["project"]["id"])

    goal_one_payload = _invoke_json(
        [
            "goal",
            "create",
            "Goal Scope Audit One",
            "--project-id",
            project_id,
            "--format",
            "json",
        ],
        env,
    )
    goal_two_payload = _invoke_json(
        [
            "goal",
            "create",
            "Goal Scope Audit Two",
            "--project-id",
            project_id,
            "--format",
            "json",
        ],
        env,
    )
    goal_one_id = str(goal_one_payload["goal"]["id"])
    goal_two_id = str(goal_two_payload["goal"]["id"])

    task_payload = _invoke_json(
        ["task", "add", project_id, "Shared Execution Task", "--format", "json"],
        env,
    )
    task_id = str(task_payload["task"]["id"])

    start_result = _run_cli(["task", "start", task_id, "--by", "audit"], env)
    if start_result.returncode != 0:
        raise RuntimeError(start_result.stdout + start_result.stderr)

    progress_result = _run_cli(
        [
            "task",
            "progress",
            task_id,
            "35",
            "Working",
            "--by",
            "audit",
            "--format",
            "json",
        ],
        env,
    )
    if progress_result.returncode != 0:
        raise RuntimeError(progress_result.stdout + progress_result.stderr)

    unlinked_goal_one = _invoke_json(
        ["goal", "summary", goal_one_id, "--format", "json"],
        env,
    )
    unlinked_goal_two = _invoke_json(
        ["goal", "summary", goal_two_id, "--format", "json"],
        env,
    )

    _invoke_json(
        [
            "plan",
            "create",
            "Goal Scope Audit Plan",
            "--project-id",
            project_id,
            "--goal-id",
            goal_one_id,
            "--task-id",
            task_id,
            "--content",
            "{}",
            "--output-format",
            "json",
        ],
        env,
    )

    linked_goal_one = _invoke_json(
        ["goal", "summary", goal_one_id, "--format", "json"],
        env,
    )
    linked_goal_two = _invoke_json(
        ["goal", "summary", goal_two_id, "--format", "json"],
        env,
    )
    return {
        "goal_one_id": goal_one_id,
        "goal_two_id": goal_two_id,
        "task_id": task_id,
        "unlinked_goal_one": unlinked_goal_one,
        "unlinked_goal_two": unlinked_goal_two,
        "linked_goal_one": linked_goal_one,
        "linked_goal_two": linked_goal_two,
    }


def run_audit() -> tuple[str, ...]:
    issues: list[str] = []
    fixture = _seed_fixture(_with_temp_env())
    task_id = str(fixture["task_id"])

    for label in ("unlinked_goal_one", "unlinked_goal_two"):
        payload = fixture[label]
        execution = payload.get("execution") if isinstance(payload, dict) else None
        if not isinstance(execution, dict):
            issues.append(f"{label} did not include execution summary payload")
            continue
        if execution.get("population_basis") != "goal_scope_requires_explicit_links":
            issues.append(
                f"{label} should require explicit links in multi-goal projects; "
                f"found population_basis={execution.get('population_basis')!r}"
            )
        if execution.get("readiness_state") != "execution_scope_unlinked":
            issues.append(
                f"{label} should be execution_scope_unlinked; "
                f"found {execution.get('readiness_state')!r}"
            )
        if execution.get("consistency_status") != "unlinked_goal_execution_scope":
            issues.append(
                f"{label} should surface unlinked_goal_execution_scope; "
                f"found {execution.get('consistency_status')!r}"
            )
        if execution.get("focus_task") is not None:
            issues.append(
                f"{label} should not expose a focus task before explicit links"
            )

    linked_goal_one = fixture["linked_goal_one"]
    execution = (
        linked_goal_one.get("execution") if isinstance(linked_goal_one, dict) else None
    )
    if not isinstance(execution, dict):
        issues.append("linked_goal_one did not include execution summary payload")
    else:
        if execution.get("population_basis") != "goal_plan_task_graph":
            issues.append(
                "linked_goal_one should switch to goal_plan_task_graph after a goal-linked plan"
            )
        if execution.get("total_tasks") != 1:
            issues.append(
                f"linked_goal_one should expose exactly one linked task; found {execution.get('total_tasks')!r}"
            )
        focus_task = execution.get("focus_task")
        if not isinstance(focus_task, dict) or focus_task.get("id") != task_id:
            issues.append(
                "linked_goal_one should focus the explicitly linked execution task"
            )

    linked_goal_two = fixture["linked_goal_two"]
    execution = (
        linked_goal_two.get("execution") if isinstance(linked_goal_two, dict) else None
    )
    if not isinstance(execution, dict):
        issues.append("linked_goal_two did not include execution summary payload")
    else:
        if execution.get("population_basis") != "goal_scope_requires_explicit_links":
            issues.append(
                "linked_goal_two should remain unlinked when only the sibling goal has a linked plan"
            )
        if execution.get("focus_task") is not None:
            issues.append(
                "linked_goal_two should not inherit the sibling goal's focus task"
            )

    return tuple(issues)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Exit nonzero when issues are found"
    )
    args = parser.parse_args()

    issues = run_audit()
    payload = {"issue_count": len(issues), "issues": list(issues)}
    print(json.dumps(payload, indent=2))
    return 1 if args.check and issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
