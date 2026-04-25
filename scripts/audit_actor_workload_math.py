#!/usr/bin/env python3
"""Audit actor workload math and actor-reference consistency in an isolated workspace."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from pms.config.settings import reload_settings
from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.db.connection import Database, set_database
from pms.db.schema import initialize_schema
from pms.services.actor_service import ActorService
from scripts.audit_actor_reference_integrity import run_audit as run_ref_integrity_audit

REPO_ROOT = Path(__file__).resolve().parents[1]
_ENV_KEYS = (
    "PMS_DATA_DIR",
    "PMS_DATABASE_PATH",
    "PMS_LOG_DIR",
    "PMS_ENV_FILE",
    "PMS_WRITE_MODE",
    "PMS_CLI_ARGV0",
    "PMS_SERVER_BASE_URL",
    "PMS_API_KEY",
    "PMS_API_KEY_PATH",
)


@dataclass(frozen=True)
class ActorWorkloadMathIssue:
    reason: str


def _with_temp_env() -> dict[str, str]:
    temp_dir = Path(
        tempfile.mkdtemp(prefix="actor-workload-audit-", dir=REPO_ROOT / ".tmp")
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


@contextmanager
def _activated_env(env: dict[str, str]):
    saved = {key: os.environ.get(key) for key in _ENV_KEYS}
    try:
        for key in _ENV_KEYS:
            if key in env:
                os.environ[key] = env[key]
            else:
                os.environ.pop(key, None)
        reload_settings()
        set_database(None)
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        reload_settings()
        set_database(None)


def _seed_fixture(env: dict[str, str]) -> dict[str, str]:
    project_name = "Actor Math Project"
    second_project_name = "Actor Math Secondary"
    org_name = "Actor Math Org"
    portfolio_name = "Actor Math Portfolio"

    init_result = _run_cli(["init"], env)
    if init_result.returncode != 0:
        raise RuntimeError(init_result.stdout + init_result.stderr)

    for args in (
        ["actor", "create", "Alice Example", "--kind", "human", "--format", "json"],
        [
            "actor",
            "create",
            "Security Persona",
            "--kind",
            "persona",
            "--format",
            "json",
        ],
        ["actor", "alias", "add", "alice-example", "alice", "--format", "json"],
        [
            "actor",
            "membership",
            "add",
            "security-persona",
            "alice-example",
            "--role",
            "representative",
            "--format",
            "json",
        ],
    ):
        result = _run_cli(args, env)
        if result.returncode != 0:
            raise RuntimeError(result.stdout + result.stderr)

    project_id = _extract_id(_run_cli(["project", "create", project_name], env).stdout)
    second_project_id = _extract_id(
        _run_cli(["project", "create", second_project_name], env).stdout
    )

    goal_payload = _invoke_json(
        [
            "goal",
            "create",
            "Actor Math Goal",
            "--project",
            project_name,
            "--format",
            "json",
        ],
        env,
    )
    objective_payload = _invoke_json(
        [
            "objective",
            "create",
            "Actor Math Objective",
            "--goal-id",
            goal_payload["goal"]["id"],
            "--format",
            "json",
        ],
        env,
    )
    key_result_id = _extract_id(
        _run_cli(
            [
                "keyresult",
                "create",
                "Actor Math KR",
                "--objective-id",
                objective_payload["objective"]["id"],
            ],
            env,
        ).stdout
    )

    product_payload = _invoke_json(
        ["product", "create", "Actor Math Product", "--format", "json"], env
    )
    org_payload = _invoke_json(["org", "create", org_name, "--format", "json"], env)
    team_payload = _invoke_json(
        ["team", "create", "Actor Math Team", "--org", org_name, "--format", "json"],
        env,
    )
    portfolio_payload = _invoke_json(
        ["portfolio", "create", portfolio_name, "--org", org_name, "--format", "json"],
        env,
    )
    program_payload = _invoke_json(
        [
            "program",
            "create",
            "Actor Math Program",
            "--org",
            org_name,
            "--portfolio",
            portfolio_name,
            "--format",
            "json",
        ],
        env,
    )
    queue_payload = _invoke_json(
        ["queue", "create", "Actor Math Queue", "--filters", "{}", "--format", "json"],
        env,
    )

    direct_task_payload = _invoke_json(
        ["task", "add", project_name, "Direct Legacy Task", "--format", "json"],
        env,
    )
    inherited_task_payload = _invoke_json(
        ["task", "add", project_name, "Inherited Legacy Task", "--format", "json"],
        env,
    )
    second_task_payload = _invoke_json(
        [
            "task",
            "add",
            second_project_name,
            "Secondary Persona Task",
            "--format",
            "json",
        ],
        env,
    )

    progress_result = _run_cli(
        [
            "task",
            "progress",
            inherited_task_payload["task"]["id"],
            "40",
            "Started inherited persona work",
            "--by",
            "tester",
        ],
        env,
    )
    if progress_result.returncode != 0:
        raise RuntimeError(progress_result.stdout + progress_result.stderr)

    with sqlite3.connect(env["PMS_DATABASE_PATH"]) as conn:
        conn.execute(
            "UPDATE products SET owner = ?, owner_id = NULL WHERE id = ?",
            ("alice", product_payload["product"]["id"]),
        )
        conn.execute(
            """
            UPDATE organizations
            SET owner = ?, owner_id = NULL
            WHERE id = ?
            """,
            ("Alice Example", org_payload["organization"]["id"]),
        )
        conn.execute(
            """
            UPDATE teams
            SET owner = ?, owner_id = NULL
            WHERE id = ?
            """,
            ("security-persona", team_payload["team"]["id"]),
        )
        conn.execute(
            "UPDATE portfolios SET owner = ?, owner_id = NULL WHERE id = ?",
            ("alice", portfolio_payload["portfolio"]["id"]),
        )
        conn.execute(
            "UPDATE programs SET owner = ?, owner_id = NULL WHERE id = ?",
            ("Security Persona", program_payload["program"]["id"]),
        )
        conn.execute(
            "UPDATE saved_searches SET owner = ?, owner_id = NULL WHERE id = ?",
            ("alice", queue_payload["queue"]["id"]),
        )
        conn.execute(
            "UPDATE goals SET owner = ?, owner_id = NULL WHERE id = ?",
            ("Alice Example", goal_payload["goal"]["id"]),
        )
        conn.execute(
            "UPDATE objectives SET owner = ?, owner_id = NULL WHERE id = ?",
            ("security-persona", objective_payload["objective"]["id"]),
        )
        conn.execute(
            "UPDATE key_results SET owner = ?, owner_id = NULL WHERE id = ?",
            ("alice", key_result_id),
        )
        conn.executemany(
            "UPDATE tasks SET assignee = ?, assignee_id = NULL WHERE id = ?",
            [
                ("Alice Example", direct_task_payload["task"]["id"]),
                ("Security Persona", inherited_task_payload["task"]["id"]),
                ("security-persona", second_task_payload["task"]["id"]),
            ],
        )
        conn.commit()

    return {
        "project_id": project_id,
        "second_project_id": second_project_id,
        "goal_id": goal_payload["goal"]["id"],
        "objective_id": objective_payload["objective"]["id"],
        "key_result_id": key_result_id,
        "product_id": product_payload["product"]["id"],
        "organization_id": org_payload["organization"]["id"],
        "team_id": team_payload["team"]["id"],
        "portfolio_id": portfolio_payload["portfolio"]["id"],
        "program_id": program_payload["program"]["id"],
        "queue_id": queue_payload["queue"]["id"],
        "direct_task_id": direct_task_payload["task"]["id"],
        "inherited_task_id": inherited_task_payload["task"]["id"],
        "second_task_id": second_task_payload["task"]["id"],
    }


async def _validate_actor_workload_math(fixture: dict[str, str]) -> tuple[str, ...]:
    db = Database()
    await db.connect()
    await initialize_schema(db)
    try:
        event_store = EventStore(db)
        revision_store = RevisionStore(db)
        metrics = MetricsCollector(db)
        actor_service = ActorService(db, event_store, revision_store, metrics)

        alice = await actor_service.get_actor("alice-example")
        if alice is None:
            return ("alice-example should resolve after normalization",)

        summary = await actor_service.get_workload_summary(
            alice.id,
            include_inherited=True,
        )
        scoped_summary = await actor_service.get_workload_summary(
            alice.id,
            include_inherited=True,
            project_id=fixture["project_id"],
        )
        graph = await actor_service.get_actor_graph(
            alice.id,
            include_inherited=True,
            task_limit=10,
        )

        issues: list[str] = []
        if summary.direct.total_tasks != 1:
            issues.append("actor direct workload should count one direct task")
        if summary.effective.total_tasks != 3:
            issues.append(
                "actor effective workload should count direct plus inherited tasks"
            )
        if summary.inherited_only.total_tasks != 2:
            issues.append(
                "actor inherited_only workload should be effective minus direct"
            )
        if summary.effective.todo_tasks != 2:
            issues.append(
                "actor effective todo count should include the direct and secondary persona tasks"
            )
        if summary.effective.in_progress_tasks != 1:
            issues.append(
                "actor effective in_progress count should include the inherited started task"
            )

        if scoped_summary.direct.total_tasks != 1:
            issues.append(
                "project-scoped direct workload should stay bounded to the primary project"
            )
        if scoped_summary.effective.total_tasks != 2:
            issues.append(
                "project-scoped effective workload should exclude secondary project work"
            )
        if scoped_summary.inherited_only.total_tasks != 1:
            issues.append(
                "project-scoped inherited workload should match the primary project inherited task"
            )

        if graph is None or graph.assigned_tasks is None:
            issues.append(
                "actor graph should include assigned tasks after normalization"
            )
        else:
            if graph.assigned_tasks.total_count != 3:
                issues.append(
                    "actor graph assigned task count should match effective workload"
                )
        if graph is None or graph.workload is None:
            issues.append("actor graph should include workload summary")
        elif graph.workload.effective.total_tasks != summary.effective.total_tasks:
            issues.append("actor graph workload should match direct workload summary")

        return tuple(issues)
    finally:
        await db.disconnect()


def run_audit() -> tuple[ActorWorkloadMathIssue, ...]:
    env = _with_temp_env()
    fixture = _seed_fixture(env)
    issues: list[ActorWorkloadMathIssue] = []

    with _activated_env(env):
        ref_issues = run_ref_integrity_audit()
        for issue in ref_issues:
            issues.append(ActorWorkloadMathIssue(issue))

        workload_issues = asyncio.run(_validate_actor_workload_math(fixture))
        for issue in workload_issues:
            issues.append(ActorWorkloadMathIssue(issue))

    return tuple(issues)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Exit nonzero on issues")
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
        print(f"Actor workload math audit\nchecked=1 issues={len(issues)}")
        for issue in issues:
            print(f"- {issue.reason}")

    if args.check and issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
