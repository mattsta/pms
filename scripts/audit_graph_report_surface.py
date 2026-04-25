#!/usr/bin/env python3
"""Audit the unified work graph-report surface in an isolated project-scoped scenario."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _with_temp_env() -> dict[str, str]:
    temp_dir = Path(
        tempfile.mkdtemp(prefix="graph-report-audit-", dir=REPO_ROOT / ".tmp")
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


def _extract_id(output: str) -> str:
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("ID:"):
            return stripped.split("ID:", 1)[1].strip()
    raise RuntimeError(f"unable to extract ID from output:\n{output}")


def _seed_fixture(env: dict[str, str]) -> dict[str, str]:
    init_result = _run_cli(["init"], env)
    if init_result.returncode != 0:
        raise RuntimeError(init_result.stdout + init_result.stderr)

    _invoke_json(
        ["actor", "create", "Alice Example", "--kind", "human", "--format", "json"],
        env,
    )
    _invoke_json(
        [
            "actor",
            "create",
            "Security Persona",
            "--kind",
            "persona",
            "--format",
            "json",
        ],
        env,
    )

    project_payload = _invoke_json(
        ["project", "create", "Graph Report Audit Project", "--format", "json"],
        env,
    )
    project_id = str(project_payload["project"]["id"])

    task_payload = _invoke_json(
        ["task", "add", project_id, "Graph Report Audit Task", "--format", "json"],
        env,
    )
    task_id = str(task_payload["task"]["id"])
    task_update_result = _run_cli(
        [
            "task",
            "update",
            task_id,
            "--assigned-to",
            "alice-example",
            "--format",
            "json",
        ],
        env,
    )
    if task_update_result.returncode != 0:
        raise RuntimeError(task_update_result.stdout + task_update_result.stderr)

    goal_payload = _invoke_json(
        [
            "goal",
            "create",
            "Graph Report Audit Goal",
            "--project-id",
            project_id,
            "--owner",
            "alice-example",
            "--format",
            "json",
        ],
        env,
    )
    goal_id = str(goal_payload["goal"]["id"])

    objective_payload = _invoke_json(
        [
            "objective",
            "create",
            "Graph Report Audit Objective",
            "--goal-id",
            goal_id,
            "--owner",
            "security-persona",
            "--format",
            "json",
        ],
        env,
    )
    objective_id = str(objective_payload["objective"]["id"])

    key_result_result = _run_cli(
        [
            "keyresult",
            "create",
            "Graph Report Audit KR",
            "--objective-id",
            objective_id,
            "--owner",
            "alice-example",
        ],
        env,
    )
    if key_result_result.returncode != 0:
        raise RuntimeError(key_result_result.stdout + key_result_result.stderr)
    key_result_id = _extract_id(key_result_result.stdout)

    start_result = _run_cli(["task", "start", task_id, "--by", "audit"], env)
    if start_result.returncode != 0:
        raise RuntimeError(start_result.stdout + start_result.stderr)

    progress_result = _run_cli(
        [
            "task",
            "progress",
            task_id,
            "45",
            "Unified graph report in progress",
            "--by",
            "audit",
            "--format",
            "json",
        ],
        env,
    )
    if progress_result.returncode != 0:
        raise RuntimeError(progress_result.stdout + progress_result.stderr)

    checkout_result = _run_cli(
        [
            "task",
            "checkout",
            task_id,
            "--agent-id",
            "graph-report-runner",
            "--actor",
            "alice-example",
        ],
        env,
    )
    if checkout_result.returncode != 0:
        raise RuntimeError(checkout_result.stdout + checkout_result.stderr)

    evidence_result = _run_cli(
        [
            "task",
            "evidence",
            "add",
            task_id,
            "artifact",
            "docs/proof.txt",
        ],
        env,
    )
    if evidence_result.returncode != 0:
        raise RuntimeError(evidence_result.stdout + evidence_result.stderr)

    plan_payload = _invoke_json(
        [
            "plan",
            "create",
            "Graph Report Audit Plan",
            "--project-id",
            project_id,
            "--goal-id",
            goal_id,
            "--objective-id",
            objective_id,
            "--task-id",
            task_id,
            "--output-format",
            "json",
        ],
        env,
    )
    plan_id = str(plan_payload["plan"]["id"])

    return {
        "project_id": project_id,
        "task_id": task_id,
        "goal_id": goal_id,
        "objective_id": objective_id,
        "key_result_id": key_result_id,
        "plan_id": plan_id,
    }


def run_audit() -> tuple[str, ...]:
    issues: list[str] = []
    env = _with_temp_env()
    fixture = _seed_fixture(env)
    payload = _invoke_json(
        [
            "work",
            "graph-report",
            "--scope-type",
            "project",
            "--scope-id",
            fixture["project_id"],
            "--format",
            "json",
        ],
        env,
    )

    if payload.get("scope", {}).get("kind") != "work_graph_report":
        issues.append("graph report should declare scope.kind=work_graph_report")
    if payload.get("scope", {}).get("detail_level") != "project_full_graph":
        issues.append(
            "project-scoped graph report should use project_full_graph detail"
        )
    if payload.get("focus_task", {}).get("id") != fixture["task_id"]:
        issues.append("graph report should focus the seeded task")

    graph_navigation = payload.get("graph_navigation")
    if not isinstance(graph_navigation, dict):
        issues.append("graph report should include graph_navigation")
    else:
        if graph_navigation.get("basis") != "focus_task":
            issues.append("graph report should navigate from the focus task")
        plans_link = graph_navigation.get("links", {}).get("plans")
        expected_plans = f"plan list --task-id {fixture['task_id']} --format json"
        if not isinstance(plans_link, str) or expected_plans not in plans_link:
            issues.append(
                "graph report should replay into linked plan listing from the focus task"
            )

    project_items = payload.get("projects", {}).get("items", [])
    if not project_items or project_items[0].get("id") != fixture["project_id"]:
        issues.append("graph report should include the scoped project")

    goal_items = payload.get("goals", {}).get("items", [])
    if not goal_items or goal_items[0].get("id") != fixture["goal_id"]:
        issues.append("graph report should include the linked goal")

    objective_items = payload.get("objectives", {}).get("items", [])
    if not objective_items or objective_items[0].get("id") != fixture["objective_id"]:
        issues.append("graph report should include the linked objective")

    key_result_items = payload.get("key_results", {}).get("items", [])
    if (
        not key_result_items
        or key_result_items[0].get("id") != fixture["key_result_id"]
    ):
        issues.append("graph report should include the linked key result")

    plan_items = payload.get("plans", {}).get("items", [])
    if not plan_items or plan_items[0].get("id") != fixture["plan_id"]:
        issues.append("graph report should include the linked plan")

    task_items = payload.get("tasks", {}).get("items", [])
    if not task_items or task_items[0].get("id") != fixture["task_id"]:
        issues.append("graph report should include the seeded task")
    else:
        task_item = task_items[0]
        if int(task_item.get("linked_plan_count") or 0) < 1:
            issues.append("graph report should include linked plan counts on task rows")
        if int(task_item.get("evidence_count") or 0) < 1:
            issues.append("graph report should include evidence counts on task rows")

    evidence_total = payload.get("results", {}).get("evidence", {}).get("total_count")
    if int(evidence_total or 0) < 1:
        issues.append("graph report should surface evidence totals in results")

    actor_rollups = payload.get("actor_rollups")
    if not isinstance(actor_rollups, dict):
        issues.append("graph report should include actor_rollups")
    else:
        if actor_rollups.get("population_basis") != "project_graph_visible_entities":
            issues.append(
                "graph report should declare project_graph_visible_entities actor rollups"
            )
        ownership_handles = {
            actor["handle"]
            for actor in actor_rollups.get("ownership", {}).get("actors", [])
            if isinstance(actor, dict) and actor.get("handle")
        }
        if ownership_handles != {"alice-example", "security-persona"}:
            issues.append(
                "graph report should aggregate both ownership actors across goal/objective/key result"
            )
        assignment_handles = {
            actor["handle"]
            for actor in actor_rollups.get("assignments", {}).get("actors", [])
            if isinstance(actor, dict) and actor.get("handle")
        }
        if assignment_handles != {"alice-example"}:
            issues.append("graph report should aggregate the task assignee actor")
        checkout_handles = {
            actor["handle"]
            for actor in actor_rollups.get("checkouts", {}).get("actors", [])
            if isinstance(actor, dict) and actor.get("handle")
        }
        if checkout_handles != {"alice-example"}:
            issues.append("graph report should aggregate the checkout actor")

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
