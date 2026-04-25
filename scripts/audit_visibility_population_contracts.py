#!/usr/bin/env python3
"""Audit visible-vs-retained population contracts on operator list surfaces."""

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
class VisibilityPopulationIssue:
    reason: str


def _with_temp_env() -> dict[str, str]:
    temp_dir = Path(
        tempfile.mkdtemp(prefix="visibility-population-audit-", dir=REPO_ROOT / ".tmp")
    )
    env = os.environ.copy()
    env["PMS_DATA_DIR"] = str(temp_dir)
    env["PMS_DATABASE_PATH"] = str(temp_dir / "audit.db")
    env["PMS_LOG_DIR"] = str(temp_dir / "logs")
    env["PMS_ENV_FILE"] = str(temp_dir / ".env")
    env["PMS_WRITE_MODE"] = "direct"
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


def run_audit() -> tuple[VisibilityPopulationIssue, ...]:
    env = _with_temp_env()
    issues: list[VisibilityPopulationIssue] = []

    _run_cli(["init"], env)
    _run_cli(["project", "create", "Operator Project"], env)
    _run_cli(["project", "create", "Audit Project audit123"], env)
    _run_cli(["project", "create", "Archived Project"], env)
    _run_cli(["project", "create", "Goal Filter Project A"], env)
    _run_cli(["project", "create", "Recent Progress Project"], env)
    _run_cli(["project", "update", "Archived Project", "--status", "archived"], env)

    default_payload = _invoke_json(["project", "list", "--format", "json"], env)
    include_generated_payload = _invoke_json(
        ["project", "list", "--include-generated", "--format", "json"],
        env,
    )
    operator_task_result = _run_cli(
        ["task", "add", "Operator Project", "Operator Task"], env
    )
    audit_task_result = _run_cli(
        ["task", "add", "Audit Project audit123", "Audit Task"], env
    )
    archived_task_result = _run_cli(
        ["task", "add", "Archived Project", "Archived Task"], env
    )
    recent_progress_task_result = _run_cli(
        ["task", "add", "Recent Progress Project", "Recent Progress Task"],
        env,
    )
    for result in (operator_task_result, audit_task_result, archived_task_result):
        if result.returncode != 0:
            raise RuntimeError(result.stdout + result.stderr)
    if recent_progress_task_result.returncode != 0:
        raise RuntimeError(
            recent_progress_task_result.stdout + recent_progress_task_result.stderr
        )
    operator_task_id = (
        operator_task_result.stdout.split("ID: ")[-1].splitlines()[0].strip()
    )
    audit_task_id = audit_task_result.stdout.split("ID: ")[-1].splitlines()[0].strip()
    archived_task_id = (
        archived_task_result.stdout.split("ID: ")[-1].splitlines()[0].strip()
    )
    recent_progress_task_id = (
        recent_progress_task_result.stdout.split("ID: ")[-1].splitlines()[0].strip()
    )
    default_ready_payload = _invoke_json(["task", "ready", "--format", "json"], env)
    include_generated_ready_payload = _invoke_json(
        ["task", "ready", "--include-generated", "--format", "json"],
        env,
    )
    for task_id in (
        operator_task_id,
        audit_task_id,
        archived_task_id,
        recent_progress_task_id,
    ):
        result = _run_cli(["task", "start", task_id, "--by", "audit"], env)
        if result.returncode != 0:
            raise RuntimeError(result.stdout + result.stderr)

    dashboard_payload = _invoke_json(["dashboard", "--format", "json"], env)
    default_task_payload = _invoke_json(
        ["task", "list", "--status", "in_progress", "--format", "json"],
        env,
    )
    default_stale_payload = _invoke_json(
        ["task", "stale", "--days", "0", "--format", "json"], env
    )
    include_generated_stale_payload = _invoke_json(
        ["task", "stale", "--days", "0", "--include-generated", "--format", "json"],
        env,
    )
    default_blocked_payload = _invoke_json(["task", "blocked", "--format", "json"], env)
    include_generated_blocked_payload = _invoke_json(
        ["task", "blocked", "--include-generated", "--format", "json"],
        env,
    )
    default_search_payload = _invoke_json(
        ["task", "search", "--query", "Task", "--format", "json"],
        env,
    )
    include_generated_task_payload = _invoke_json(
        [
            "task",
            "list",
            "--status",
            "in_progress",
            "--include-generated",
            "--format",
            "json",
        ],
        env,
    )
    include_generated_search_payload = _invoke_json(
        [
            "task",
            "search",
            "--query",
            "Task",
            "--include-generated",
            "--format",
            "json",
        ],
        env,
    )
    duplicate_operator_a = _run_cli(
        ["task", "add", "Operator Project", "Shared Duplicate Task"],
        env,
    )
    duplicate_operator_b = _run_cli(
        ["task", "add", "Operator Project", "Shared Duplicate Task"],
        env,
    )
    duplicate_audit = _run_cli(
        ["task", "add", "Audit Project audit123", "Shared Duplicate Task"],
        env,
    )
    duplicate_archived = _run_cli(
        ["task", "add", "Archived Project", "Shared Duplicate Task"],
        env,
    )
    for result in (
        duplicate_operator_a,
        duplicate_operator_b,
        duplicate_audit,
        duplicate_archived,
    ):
        if result.returncode != 0:
            raise RuntimeError(result.stdout + result.stderr)
    default_duplicates_payload = _invoke_json(
        ["task", "duplicates", "--format", "json"],
        env,
    )
    include_generated_duplicates_payload = _invoke_json(
        ["task", "duplicates", "--include-generated", "--format", "json"],
        env,
    )

    if default_payload["scope"]["population"] != "visible_operator":
        issues.append(
            VisibilityPopulationIssue(
                "default project list scope.population must be visible_operator"
            )
        )
    if default_payload["visible_totals"]["population"] != "visible_operator":
        issues.append(
            VisibilityPopulationIssue(
                "default project list visible_totals.population must be visible_operator"
            )
        )
    if default_payload["population_totals"]["population"] != "visible_operator":
        issues.append(
            VisibilityPopulationIssue(
                "default project list population_totals.population must be visible_operator"
            )
        )
    if {item["name"] for item in default_payload["items"]} != {
        "Operator Project",
        "Archived Project",
        "Goal Filter Project A",
        "Recent Progress Project",
    }:
        issues.append(
            VisibilityPopulationIssue(
                "default project list should suppress generated project rows only"
            )
        )
    if default_payload["suppressed_generated_count"] != 1:
        issues.append(
            VisibilityPopulationIssue(
                "default project list should report exactly one suppressed generated project"
            )
        )
    if default_payload["visible_totals"]["active_work_projects"] != 2:
        issues.append(
            VisibilityPopulationIssue(
                "default project list visible_totals.active_work_projects should reflect actionable active_work rows only"
            )
        )
    if default_payload["scope"]["active_work_visible_projects"] != 2:
        issues.append(
            VisibilityPopulationIssue(
                "default project list scope.active_work_visible_projects should match actionable visible project rows"
            )
        )

    if include_generated_payload["scope"]["population"] != "all_retained":
        issues.append(
            VisibilityPopulationIssue(
                "include-generated project list scope.population must be all_retained"
            )
        )
    if include_generated_payload["population_totals"]["population"] != "all_retained":
        issues.append(
            VisibilityPopulationIssue(
                "include-generated project list population_totals.population must be all_retained"
            )
        )
    if include_generated_payload["visible_totals"]["population"] != "visible_operator":
        issues.append(
            VisibilityPopulationIssue(
                "include-generated project list must keep visible_totals on visible_operator"
            )
        )
    if include_generated_payload["visible_totals"]["total_projects"] != 4:
        issues.append(
            VisibilityPopulationIssue(
                "include-generated project list visible_totals should still reflect the operator-visible population"
            )
        )
    if include_generated_payload["population_totals"]["total_projects"] != 5:
        issues.append(
            VisibilityPopulationIssue(
                "include-generated project list population_totals should reflect all retained rows"
            )
        )
    if include_generated_payload["visible_totals"]["active_work_projects"] != 2:
        issues.append(
            VisibilityPopulationIssue(
                "include-generated project list visible_totals.active_work_projects should preserve the visible operator baseline"
            )
        )
    if include_generated_payload["population_totals"]["active_work_projects"] != 2:
        issues.append(
            VisibilityPopulationIssue(
                "include-generated project list population_totals.active_work_projects should count only actionable active_work rows"
            )
        )

    include_items = {item["name"]: item for item in include_generated_payload["items"]}
    audit_item = include_items.get("Audit Project audit123")
    if audit_item is None:
        issues.append(
            VisibilityPopulationIssue(
                "include-generated project list should include the generated audit project"
            )
        )
    else:
        if audit_item["operator_category"] != "audit_artifact":
            issues.append(
                VisibilityPopulationIssue(
                    "audit-generated active project must classify as audit_artifact"
                )
            )

    if include_generated_payload["category_counts"].get("audit_artifact") != 1:
        issues.append(
            VisibilityPopulationIssue(
                "include-generated category_counts should count audit_artifact rows"
            )
        )

    if (
        dashboard_payload["instance_totals"]["population"]
        != "all_non_archived_retained"
    ):
        issues.append(
            VisibilityPopulationIssue(
                "dashboard instance_totals.population must remain all_non_archived_retained"
            )
        )
    if dashboard_payload["instance_totals"]["total_projects"] != 4:
        issues.append(
            VisibilityPopulationIssue(
                "dashboard instance_totals must exclude archived projects"
            )
        )

    if default_task_payload["scope"]["population"] != "visible_operator":
        issues.append(
            VisibilityPopulationIssue(
                "default task list scope.population must be visible_operator"
            )
        )
    if default_task_payload["visible_totals"]["population"] != "visible_operator":
        issues.append(
            VisibilityPopulationIssue(
                "default task list visible_totals.population must be visible_operator"
            )
        )
    if default_task_payload["population_totals"]["population"] != "visible_operator":
        issues.append(
            VisibilityPopulationIssue(
                "default task list population_totals.population must be visible_operator"
            )
        )
    if {item["project_name"] for item in default_task_payload["items"]} != {
        "Operator Project",
        "Recent Progress Project",
    }:
        issues.append(
            VisibilityPopulationIssue(
                "default task list should suppress audit and archived project tasks"
            )
        )
    if default_task_payload["suppressed_hidden_count"] != 2:
        issues.append(
            VisibilityPopulationIssue(
                "default task list should report exactly two suppressed hidden tasks"
            )
        )

    if include_generated_task_payload["scope"]["population"] != "all_retained":
        issues.append(
            VisibilityPopulationIssue(
                "include-generated task list scope.population must be all_retained"
            )
        )
    if (
        include_generated_task_payload["population_totals"]["population"]
        != "all_retained"
    ):
        issues.append(
            VisibilityPopulationIssue(
                "include-generated task list population_totals.population must be all_retained"
            )
        )
    if include_generated_task_payload["visible_totals"]["total_tasks"] != 2:
        issues.append(
            VisibilityPopulationIssue(
                "include-generated task list visible_totals should still reflect the operator-visible population"
            )
        )
    if include_generated_task_payload["population_totals"]["total_tasks"] != 4:
        issues.append(
            VisibilityPopulationIssue(
                "include-generated task list population_totals should reflect all retained rows"
            )
        )
    task_items = {
        item["project_name"]: item for item in include_generated_task_payload["items"]
    }
    if (
        task_items.get("Audit Project audit123", {}).get("project_operator_category")
        != "audit_artifact"
    ):
        issues.append(
            VisibilityPopulationIssue(
                "include-generated audit task should expose audit_artifact project category"
            )
        )

    if default_ready_payload["scope"]["population"] != "visible_operator":
        issues.append(
            VisibilityPopulationIssue(
                "default task ready scope.population must be visible_operator"
            )
        )
    if default_ready_payload["suppressed_hidden_count"] != 2:
        issues.append(
            VisibilityPopulationIssue(
                "default task ready should report exactly two suppressed hidden tasks"
            )
        )
    if include_generated_ready_payload["population_totals"]["total_tasks"] != 4:
        issues.append(
            VisibilityPopulationIssue(
                "include-generated task ready population_totals should reflect all retained rows"
            )
        )

    if default_stale_payload["scope"]["population"] != "visible_operator":
        issues.append(
            VisibilityPopulationIssue(
                "default task stale scope.population must be visible_operator"
            )
        )
    if default_stale_payload["suppressed_hidden_count"] != 2:
        issues.append(
            VisibilityPopulationIssue(
                "default task stale should report exactly two suppressed hidden tasks"
            )
        )
    if include_generated_stale_payload["population_totals"]["total_tasks"] != 4:
        issues.append(
            VisibilityPopulationIssue(
                "include-generated task stale population_totals should reflect all retained rows"
            )
        )

    if default_blocked_payload["scope"]["population"] != "visible_operator":
        issues.append(
            VisibilityPopulationIssue(
                "default task blocked scope.population must be visible_operator"
            )
        )
    if default_blocked_payload["suppressed_hidden_count"] != 0:
        issues.append(
            VisibilityPopulationIssue(
                "default task blocked should not report hidden tasks without blocked retained rows"
            )
        )
    if include_generated_blocked_payload["population_totals"]["blocked_tasks"] != 0:
        issues.append(
            VisibilityPopulationIssue(
                "include-generated task blocked population_totals should reflect blocked retained rows"
            )
        )

    if default_search_payload["scope"]["population"] != "visible_operator":
        issues.append(
            VisibilityPopulationIssue(
                "default task search scope.population must be visible_operator"
            )
        )
    if default_search_payload["visible_totals"]["population"] != "visible_operator":
        issues.append(
            VisibilityPopulationIssue(
                "default task search visible_totals.population must be visible_operator"
            )
        )
    if default_search_payload["population_totals"]["population"] != "visible_operator":
        issues.append(
            VisibilityPopulationIssue(
                "default task search population_totals.population must be visible_operator"
            )
        )
    if {item["project_name"] for item in default_search_payload["items"]} != {
        "Operator Project",
        "Recent Progress Project",
    }:
        issues.append(
            VisibilityPopulationIssue(
                "default task search should suppress audit and archived project tasks"
            )
        )
    if default_search_payload["suppressed_hidden_count"] != 2:
        issues.append(
            VisibilityPopulationIssue(
                "default task search should report exactly two suppressed hidden tasks"
            )
        )

    if include_generated_search_payload["scope"]["population"] != "all_retained":
        issues.append(
            VisibilityPopulationIssue(
                "include-generated task search scope.population must be all_retained"
            )
        )
    if (
        include_generated_search_payload["population_totals"]["population"]
        != "all_retained"
    ):
        issues.append(
            VisibilityPopulationIssue(
                "include-generated task search population_totals.population must be all_retained"
            )
        )
    if include_generated_search_payload["visible_totals"]["total_tasks"] != 2:
        issues.append(
            VisibilityPopulationIssue(
                "include-generated task search visible_totals should still reflect the operator-visible population"
            )
        )
    if include_generated_search_payload["population_totals"]["total_tasks"] != 4:
        issues.append(
            VisibilityPopulationIssue(
                "include-generated task search population_totals should reflect all retained rows"
            )
        )

    if default_duplicates_payload["scope"]["population"] != "visible_operator":
        issues.append(
            VisibilityPopulationIssue(
                "default task duplicates scope.population must be visible_operator"
            )
        )
    if default_duplicates_payload["visible_totals"]["duplicate_groups"] != 1:
        issues.append(
            VisibilityPopulationIssue(
                "default task duplicates should keep exactly one operator-visible duplicate group"
            )
        )
    if default_duplicates_payload["visible_totals"]["duplicate_tasks"] != 2:
        issues.append(
            VisibilityPopulationIssue(
                "default task duplicates should keep exactly two operator-visible duplicate tasks"
            )
        )
    if default_duplicates_payload["suppressed_hidden_count"] != 2:
        issues.append(
            VisibilityPopulationIssue(
                "default task duplicates should report exactly two suppressed hidden duplicate tasks"
            )
        )

    if include_generated_duplicates_payload["scope"]["population"] != "all_retained":
        issues.append(
            VisibilityPopulationIssue(
                "include-generated task duplicates scope.population must be all_retained"
            )
        )
    if include_generated_duplicates_payload["visible_totals"]["duplicate_tasks"] != 2:
        issues.append(
            VisibilityPopulationIssue(
                "include-generated task duplicates visible_totals should still reflect the operator-visible population"
            )
        )
    if (
        include_generated_duplicates_payload["population_totals"]["duplicate_tasks"]
        != 4
    ):
        issues.append(
            VisibilityPopulationIssue(
                "include-generated task duplicates population_totals should reflect all retained duplicate tasks"
            )
        )
    duplicate_group = include_generated_duplicates_payload["items"][0]
    duplicate_tasks = {
        item["project_name"]: item
        for item in duplicate_group["tasks"]
        if item["project_name"]
    }
    if (
        duplicate_tasks.get("Audit Project audit123", {}).get(
            "project_operator_category"
        )
        != "audit_artifact"
    ):
        issues.append(
            VisibilityPopulationIssue(
                "include-generated duplicate tasks should expose audit_artifact project category"
            )
        )
    search_items = {
        item["project_name"]: item for item in include_generated_search_payload["items"]
    }
    if (
        search_items.get("Audit Project audit123", {}).get("project_operator_category")
        != "audit_artifact"
    ):
        issues.append(
            VisibilityPopulationIssue(
                "include-generated audit task search row should expose audit_artifact project category"
            )
        )

    return tuple(issues)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Exit non-zero on issues")
    parser.add_argument("--json", action="store_true", help="Emit JSON payload")
    args = parser.parse_args()

    issues = run_audit()
    if args.json:
        print(
            json.dumps(
                {
                    "checked": 1,
                    "issues": [{"reason": issue.reason} for issue in issues],
                },
                indent=2,
            )
        )
    else:
        print(f"Visibility population audit\nchecked=1 issues={len(issues)}")
        for issue in issues:
            print(f"- {issue.reason}")

    if args.check and issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
