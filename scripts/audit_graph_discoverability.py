#!/usr/bin/env python3
"""Audit graph-discoverability contracts on primary CLI show surfaces."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class GraphDiscoverabilityIssue:
    reason: str


def _with_temp_env() -> dict[str, str]:
    temp_dir = Path(
        tempfile.mkdtemp(prefix="graph-discoverability-audit-", dir=REPO_ROOT / ".tmp")
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


def _extract_id(output: str) -> str:
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("ID:"):
            return stripped.split("ID:", 1)[1].strip().rstrip("...")
    raise RuntimeError(f"unable to extract ID from output:\n{output}")


def _invoke_json(args: list[str], env: dict[str, str]) -> object:
    result = _run_cli(args, env)
    if result.returncode != 0:
        raise RuntimeError(
            f"command failed: {' '.join(args)}\n{result.stdout}{result.stderr}"
        )
    return json.loads(result.stdout)


def _seed_fixture(env: dict[str, str]) -> dict[str, str]:
    project_name = "Graph Discoverability Project"

    init_result = _run_cli(["init"], env)
    if init_result.returncode != 0:
        raise RuntimeError(init_result.stdout + init_result.stderr)

    project_result = _run_cli(["project", "create", project_name], env)
    if project_result.returncode != 0:
        raise RuntimeError(project_result.stdout + project_result.stderr)
    project_id = _extract_id(project_result.stdout)

    actor_payload = _invoke_json(
        [
            "actor",
            "create",
            "Graph Owner",
            "--kind",
            "human",
            "--format",
            "json",
        ],
        env,
    )
    actor_id = actor_payload["actor"]["id"]
    actor_handle = actor_payload["actor"]["handle"]

    goal_payload = _invoke_json(
        [
            "goal",
            "create",
            "Graph Goal",
            "--project",
            project_name,
            "--owner",
            actor_handle,
            "--format",
            "json",
        ],
        env,
    )
    goal_id = goal_payload["goal"]["id"]

    objective_payload = _invoke_json(
        [
            "objective",
            "create",
            "Graph Objective",
            "--goal-id",
            goal_id,
            "--format",
            "json",
        ],
        env,
    )
    objective_id = objective_payload["objective"]["id"]

    key_result_result = _run_cli(
        [
            "keyresult",
            "create",
            "Graph Key Result",
            "--objective-id",
            objective_id,
        ],
        env,
    )
    if key_result_result.returncode != 0:
        raise RuntimeError(key_result_result.stdout + key_result_result.stderr)
    key_result_id = _extract_id(key_result_result.stdout)

    blocker_payload = _invoke_json(
        ["task", "add", project_name, "Graph Blocker Task", "--format", "json"],
        env,
    )
    blocker_task_id = blocker_payload["task"]["id"]

    parent_payload = _invoke_json(
        ["task", "add", project_name, "Graph Parent Task", "--format", "json"],
        env,
    )
    parent_task_id = parent_payload["task"]["id"]

    child_payload = _invoke_json(
        [
            "task",
            "add",
            project_name,
            "Graph Child Task",
            "--parent-id",
            parent_task_id,
            "--format",
            "json",
        ],
        env,
    )
    child_task_id = child_payload["task"]["id"]

    dependency_result = _run_cli(
        ["task", "dep", "add", parent_task_id, blocker_task_id],
        env,
    )
    if dependency_result.returncode != 0:
        raise RuntimeError(dependency_result.stdout + dependency_result.stderr)

    plan_payload = _invoke_json(
        [
            "plan",
            "create",
            "Graph Plan",
            "--project",
            project_name,
            "--goal-id",
            goal_id,
            "--objective-id",
            objective_id,
            "--task-id",
            parent_task_id,
            "--task-id",
            child_task_id,
            "--content",
            "{}",
            "--format",
            "json",
            "--output-format",
            "json",
        ],
        env,
    )
    plan_id = plan_payload["plan"]["id"]

    queue_result = _run_cli(
        [
            "queue",
            "create",
            "Graph Queue",
            "--scope-type",
            "project",
            "--scope",
            project_name,
            "--owner",
            actor_handle,
            "--filters",
            '{"status":["todo","in_progress"]}',
        ],
        env,
    )
    if queue_result.returncode != 0:
        raise RuntimeError(queue_result.stdout + queue_result.stderr)
    queue_id = _extract_id(queue_result.stdout)

    milestone_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    with sqlite3.connect(env["PMS_DATABASE_PATH"]) as conn:
        conn.executemany(
            "UPDATE tasks SET assignee = ?, assignee_id = ? WHERE id = ?",
            [
                (actor_handle, actor_id, blocker_task_id),
                (actor_handle, actor_id, parent_task_id),
                (actor_handle, actor_id, child_task_id),
            ],
        )
        conn.execute(
            """
            INSERT INTO milestones (
                id,
                project_id,
                name,
                description,
                due_date,
                status,
                sort_order,
                created_at,
                updated_at,
                last_event_sequence
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                milestone_id,
                project_id,
                "Graph Milestone",
                "Graph milestone for task context coverage",
                None,
                "pending",
                0,
                now,
                now,
                0,
            ),
        )
        conn.execute(
            "UPDATE tasks SET milestone_id = ? WHERE id = ?",
            (milestone_id, parent_task_id),
        )
        conn.execute(
            """
            UPDATE tasks
            SET status = ?, current_progress_percent = ?, last_progress_update_at = ?, updated_at = ?
            WHERE id = ?
            """,
            ("in_progress", 40, now, now, parent_task_id),
        )
        conn.commit()

    return {
        "project_id": project_id,
        "goal_id": goal_id,
        "actor_id": actor_id,
        "actor_handle": actor_handle,
        "objective_id": objective_id,
        "key_result_id": key_result_id,
        "plan_id": plan_id,
        "queue_id": queue_id,
        "blocker_task_id": blocker_task_id,
        "parent_task_id": parent_task_id,
        "child_task_id": child_task_id,
        "milestone_id": milestone_id,
    }


def run_audit() -> tuple[GraphDiscoverabilityIssue, ...]:
    env = _with_temp_env()
    issues: list[GraphDiscoverabilityIssue] = []
    fixture = _seed_fixture(env)
    cli_prefix = env["PMS_CLI_ARGV0"]

    task_payload = _invoke_json(
        [
            "task",
            "show",
            fixture["parent_task_id"],
            "--include-linked",
            "--format",
            "json",
        ],
        env,
    )
    if task_payload["context"]["milestone"]["name"] != "Graph Milestone":
        issues.append(
            GraphDiscoverabilityIssue("task show should surface milestone context")
        )
    if task_payload["context"]["subtask_count"] != 1:
        issues.append(
            GraphDiscoverabilityIssue("task show should surface subtask counts")
        )
    if task_payload["links"]["plans"] != (
        f"{cli_prefix} plan list --task-id {fixture['parent_task_id']} --format json"
    ):
        issues.append(
            GraphDiscoverabilityIssue(
                "task show should link back to reverse plan references"
            )
        )
    if task_payload["linked"]["dependencies"][0]["id"] != fixture["blocker_task_id"]:
        issues.append(
            GraphDiscoverabilityIssue(
                "task show linked dependencies should expose blocker tasks"
            )
        )
    if task_payload["linked"]["subtasks"][0]["id"] != fixture["child_task_id"]:
        issues.append(
            GraphDiscoverabilityIssue(
                "task show linked subtasks should expose child tasks"
            )
        )

    project_payload = _invoke_json(
        [
            "project",
            "show",
            fixture["project_id"],
            "--include-linked",
            "--format",
            "json",
        ],
        env,
    )
    if project_payload["links"]["goals"] != (
        f"{cli_prefix} goal list --project-id {fixture['project_id']} --format json"
    ):
        issues.append(
            GraphDiscoverabilityIssue("project show should expose goal traversal links")
        )
    if project_payload["links"]["plans"] != (
        f"{cli_prefix} plan list --project-id {fixture['project_id']} --format json"
    ):
        issues.append(
            GraphDiscoverabilityIssue("project show should expose plan traversal links")
        )
    if project_payload["linked"]["goals"][0]["id"] != fixture["goal_id"]:
        issues.append(
            GraphDiscoverabilityIssue(
                "project show linked goals should include the seeded goal"
            )
        )
    if project_payload["linked"]["plans"][0]["id"] != fixture["plan_id"]:
        issues.append(
            GraphDiscoverabilityIssue(
                "project show linked plans should include the seeded plan"
            )
        )
    if project_payload["graph_navigation"]["links"]["plans"] != (
        f"{cli_prefix} plan list --task-id {project_payload['graph_navigation']['task_id']} --format json"
    ):
        issues.append(
            GraphDiscoverabilityIssue(
                "project show should expose focus-task graph navigation"
            )
        )

    project_summary_payload = _invoke_json(
        ["project", "summary", fixture["project_id"], "--format", "json"],
        env,
    )
    if (
        project_summary_payload["graph_navigation"]["task_id"]
        != (project_summary_payload["focus_task"]["id"])
    ):
        issues.append(
            GraphDiscoverabilityIssue(
                "project summary graph navigation should align with the focus task"
            )
        )

    dashboard_payload = _invoke_json(["dashboard", "--format", "json"], env)
    if dashboard_payload["graph_navigation"]["basis"] != "focus_task":
        issues.append(
            GraphDiscoverabilityIssue(
                "dashboard should expose focus-task graph navigation"
            )
        )
    if (
        dashboard_payload["graph_navigation"]["task_id"]
        != (dashboard_payload["focus_task"]["id"])
    ):
        issues.append(
            GraphDiscoverabilityIssue(
                "dashboard graph navigation should align with the focus task"
            )
        )

    start_payload = _invoke_json(["start", "--format", "json"], env)
    if start_payload["graph_navigation"]["basis"] != "focus_task":
        issues.append(
            GraphDiscoverabilityIssue("start should expose focus-task graph navigation")
        )
    if (
        start_payload["graph_navigation"]["task_id"]
        != start_payload["focus_task"]["id"]
    ):
        issues.append(
            GraphDiscoverabilityIssue(
                "start graph navigation should align with the focus task"
            )
        )

    queue_run_payload = _invoke_json(
        ["queue", "run", fixture["queue_id"], "--format", "json"],
        env,
    )
    if (
        queue_run_payload["graph_navigation"]["task_id"]
        != (queue_run_payload["focus_task"]["id"])
    ):
        issues.append(
            GraphDiscoverabilityIssue(
                "queue run graph navigation should align with the focus task"
            )
        )
    if queue_run_payload["focus_task"]["assignee"]["actor"] is None:
        issues.append(
            GraphDiscoverabilityIssue(
                "queue run focus task should expose assignee payloads"
            )
        )

    queue_presets_payload = _invoke_json(
        [
            "queue",
            "presets",
            "--project",
            "Graph Discoverability Project",
            "--format",
            "json",
            "--view",
            "detail",
        ],
        env,
    )
    if (
        queue_presets_payload["graph_navigation"]["task_id"]
        != (queue_presets_payload["focus_task"]["id"])
    ):
        issues.append(
            GraphDiscoverabilityIssue(
                "queue presets graph navigation should align with the focus task"
            )
        )
    if queue_presets_payload["focus_task"]["assignee"]["actor"] is None:
        issues.append(
            GraphDiscoverabilityIssue(
                "queue presets focus task should expose assignee payloads"
            )
        )

    work_review_payload = _invoke_json(
        [
            "work",
            "review",
            "--scope-type",
            "project",
            "--scope-id",
            fixture["project_id"],
            "--reviewed-by",
            "tester",
            "--format",
            "json",
        ],
        env,
    )
    if work_review_payload["graph_navigation"]["basis"] != "scope":
        issues.append(
            GraphDiscoverabilityIssue(
                "work review should expose scope-based graph navigation"
            )
        )
    if work_review_payload["graph_navigation"]["links"]["project"] != (
        f"{cli_prefix} project show {fixture['project_id']} --format json"
    ):
        issues.append(
            GraphDiscoverabilityIssue("work review should link back to project scope")
        )

    work_daily_payload = _invoke_json(
        [
            "work",
            "daily",
            "--scope-type",
            "project",
            "--scope-id",
            fixture["project_id"],
            "--format",
            "json",
        ],
        env,
    )
    if (
        work_daily_payload["graph_navigation"]["task_id"]
        != (work_daily_payload["focus_task"]["id"])
    ):
        issues.append(
            GraphDiscoverabilityIssue(
                "work daily graph navigation should align with the focus task"
            )
        )
    if work_daily_payload["focus_task"]["assignee"]["actor"] is None:
        issues.append(
            GraphDiscoverabilityIssue(
                "work daily focus task should expose assignee payloads"
            )
        )

    actor_payload = _invoke_json(
        ["actor", "show", fixture["actor_handle"], "--format", "json"],
        env,
    )
    if actor_payload["graph_navigation"]["basis"] != "actor":
        issues.append(
            GraphDiscoverabilityIssue(
                "actor show should expose actor-based graph navigation"
            )
        )
    if actor_payload["ownership"]["counts"].get("goals", 0) < 1:
        issues.append(
            GraphDiscoverabilityIssue(
                "actor show should expose owned strategic entities"
            )
        )
    if actor_payload["ownership"]["counts"].get("queues", 0) < 1:
        issues.append(
            GraphDiscoverabilityIssue("actor show should expose owned queue entities")
        )
    if not actor_payload["project_workloads"]:
        issues.append(
            GraphDiscoverabilityIssue(
                "actor show should expose per-project workload rollups"
            )
        )
    elif actor_payload["project_workloads"][0]["links"]["project"] != (
        f"{cli_prefix} project show {fixture['project_id']} --format json"
    ):
        issues.append(
            GraphDiscoverabilityIssue(
                "actor project workload should link back to the owning project"
            )
        )

    goal_summary_payload = _invoke_json(
        ["goal", "summary", fixture["goal_id"], "--format", "json"],
        env,
    )
    if goal_summary_payload["links"]["goal"] != (
        f"{cli_prefix} goal show {fixture['goal_id']}"
    ):
        issues.append(
            GraphDiscoverabilityIssue("goal summary should expose a goal self-link")
        )
    if goal_summary_payload["links"]["plans"] != (
        f"{cli_prefix} plan list --goal-id {fixture['goal_id']} --format json"
    ):
        issues.append(
            GraphDiscoverabilityIssue("goal summary should expose plan traversal links")
        )
    if goal_summary_payload["execution"]["population_basis"] != "goal_plan_task_graph":
        issues.append(
            GraphDiscoverabilityIssue(
                "goal summary should declare goal-scoped execution population basis"
            )
        )

    objective_payload = _invoke_json(
        [
            "objective",
            "show",
            fixture["objective_id"],
            "--include-linked",
            "--format",
            "json",
        ],
        env,
    )
    if objective_payload["links"]["goal_summary"] != (
        f"{cli_prefix} goal summary {fixture['goal_id']}"
    ):
        issues.append(
            GraphDiscoverabilityIssue("objective show should link back to goal summary")
        )
    if objective_payload["linked"]["key_results"][0]["id"] != fixture["key_result_id"]:
        issues.append(
            GraphDiscoverabilityIssue(
                "objective show should include linked key results"
            )
        )

    key_result_payload = _invoke_json(
        [
            "keyresult",
            "show",
            fixture["key_result_id"],
            "--include-linked",
            "--format",
            "json",
        ],
        env,
    )
    if key_result_payload["links"]["project"] != (
        f"{cli_prefix} project show {fixture['project_id']} --format json"
    ):
        issues.append(
            GraphDiscoverabilityIssue(
                "key result show should link back to project context"
            )
        )
    if key_result_payload["linked"]["goal"]["id"] != fixture["goal_id"]:
        issues.append(
            GraphDiscoverabilityIssue(
                "key result show should include linked goal context"
            )
        )

    plan_payload = _invoke_json(
        [
            "plan",
            "show",
            fixture["plan_id"],
            "--include-linked",
            "--format",
            "json",
        ],
        env,
    )
    plan_task_ids = {item["id"] for item in plan_payload["linked"]["tasks"]}
    if plan_payload["links"]["goal"] != f"{cli_prefix} goal show {fixture['goal_id']}":
        issues.append(
            GraphDiscoverabilityIssue("plan show should link back to its goal")
        )
    if plan_payload["links"]["objective"] != (
        f"{cli_prefix} objective show {fixture['objective_id']}"
    ):
        issues.append(
            GraphDiscoverabilityIssue("plan show should link back to its objective")
        )
    if plan_task_ids != {fixture["parent_task_id"], fixture["child_task_id"]}:
        issues.append(
            GraphDiscoverabilityIssue(
                "plan show should include linked task graph members"
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
        print(f"Graph discoverability audit\nchecked=1 issues={len(issues)}")
        for issue in issues:
            print(f"- {issue.reason}")

    if args.check and issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
