#!/usr/bin/env python3
"""Audit authoritative hierarchy edge reads against removed cache columns."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class HierarchyEdgeAuthorityIssue:
    reason: str


def _with_temp_env() -> dict[str, str]:
    temp_dir = Path(
        tempfile.mkdtemp(prefix="hierarchy-edge-audit-", dir=REPO_ROOT / ".tmp")
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
            return stripped.split("ID:", 1)[1].strip().rstrip("...")
    raise RuntimeError(f"unable to extract ID from output:\n{output}")


def _seed_fixture(env: dict[str, str]) -> dict[str, str]:
    init_result = _run_cli(["init"], env)
    if init_result.returncode != 0:
        raise RuntimeError(init_result.stdout + init_result.stderr)

    org_name = "Hierarchy Audit Org"
    portfolio_name = "Hierarchy Audit Portfolio"
    program_name = "Hierarchy Audit Program"
    project_name = "Hierarchy Audit Project"

    _run_cli(["org", "create", org_name], env)
    portfolio_id = _extract_id(
        _run_cli(["portfolio", "create", portfolio_name, "--org", org_name], env).stdout
    )
    program_id = _extract_id(
        _run_cli(
            [
                "program",
                "create",
                program_name,
                "--org",
                org_name,
                "--portfolio",
                portfolio_name,
            ],
            env,
        ).stdout
    )
    project_id = _extract_id(
        _run_cli(
            [
                "project",
                "create",
                project_name,
                "--org",
                org_name,
                "--portfolio",
                portfolio_name,
                "--program",
                program_name,
            ],
            env,
        ).stdout
    )
    goal_payload = _invoke_json(
        [
            "goal",
            "create",
            "Hierarchy Audit Goal",
            "--project",
            project_name,
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
            "Hierarchy Audit Objective",
            "--goal-id",
            goal_id,
            "--format",
            "json",
        ],
        env,
    )
    objective_id = objective_payload["objective"]["id"]
    return {
        "org_name": org_name,
        "portfolio_name": portfolio_name,
        "program_name": program_name,
        "portfolio_id": portfolio_id,
        "program_id": program_id,
        "project_id": project_id,
        "goal_id": goal_id,
        "objective_id": objective_id,
    }


def _cache_columns_present(
    env: dict[str, str],
) -> tuple[HierarchyEdgeAuthorityIssue, ...]:
    issues: list[HierarchyEdgeAuthorityIssue] = []
    with sqlite3.connect(env["PMS_DATABASE_PATH"]) as conn:
        portfolio_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(portfolios)")
        }
        program_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(programs)")
        }

    for column in ("project_ids", "goal_ids", "objective_ids"):
        if column in portfolio_columns:
            issues.append(
                HierarchyEdgeAuthorityIssue(
                    f"portfolio cache column '{column}' still exists in the fresh schema"
                )
            )
        if column in program_columns:
            issues.append(
                HierarchyEdgeAuthorityIssue(
                    f"program cache column '{column}' still exists in the fresh schema"
                )
            )
    return tuple(issues)


def run_audit() -> tuple[HierarchyEdgeAuthorityIssue, ...]:
    env = _with_temp_env()
    ids = _seed_fixture(env)
    issues: list[HierarchyEdgeAuthorityIssue] = list(_cache_columns_present(env))

    portfolio_show = _invoke_json(
        [
            "portfolio",
            "show",
            ids["portfolio_name"],
            "--format",
            "json",
            "--include-linked",
        ],
        env,
    )
    if portfolio_show["project_ids"] != [ids["project_id"]]:
        issues.append(
            HierarchyEdgeAuthorityIssue(
                "portfolio show exposed cached project_ids instead of authoritative linked projects"
            )
        )
    if portfolio_show["goal_ids"] != []:
        issues.append(
            HierarchyEdgeAuthorityIssue(
                "portfolio show exposed non-direct goal_ids for project-derived scope"
            )
        )
    if portfolio_show["objective_ids"] != []:
        issues.append(
            HierarchyEdgeAuthorityIssue(
                "portfolio show exposed non-direct objective_ids for project-derived scope"
            )
        )
    if portfolio_show["effective_goal_ids"] != [ids["goal_id"]]:
        issues.append(
            HierarchyEdgeAuthorityIssue(
                "portfolio show effective_goal_ids did not derive from authoritative linked goals"
            )
        )
    if portfolio_show["effective_objective_ids"] != [ids["objective_id"]]:
        issues.append(
            HierarchyEdgeAuthorityIssue(
                "portfolio show effective_objective_ids did not derive from authoritative linked objectives"
            )
        )
    if portfolio_show["linked"]["projects"][0]["id"] != ids["project_id"]:
        issues.append(
            HierarchyEdgeAuthorityIssue(
                "portfolio linked projects did not derive from project foreign-key assignments"
            )
        )

    program_show = _invoke_json(
        [
            "program",
            "show",
            ids["program_name"],
            "--format",
            "json",
            "--include-linked",
        ],
        env,
    )
    if program_show["project_ids"] != [ids["project_id"]]:
        issues.append(
            HierarchyEdgeAuthorityIssue(
                "program show exposed cached project_ids instead of authoritative linked projects"
            )
        )
    if program_show["goal_ids"] != []:
        issues.append(
            HierarchyEdgeAuthorityIssue(
                "program show exposed non-direct goal_ids for project-derived scope"
            )
        )
    if program_show["objective_ids"] != []:
        issues.append(
            HierarchyEdgeAuthorityIssue(
                "program show exposed non-direct objective_ids for project-derived scope"
            )
        )
    if program_show["effective_goal_ids"] != [ids["goal_id"]]:
        issues.append(
            HierarchyEdgeAuthorityIssue(
                "program show effective_goal_ids did not derive from authoritative linked goals"
            )
        )
    if program_show["effective_objective_ids"] != [ids["objective_id"]]:
        issues.append(
            HierarchyEdgeAuthorityIssue(
                "program show effective_objective_ids did not derive from authoritative linked objectives"
            )
        )
    if program_show["linked"]["goals"][0]["id"] != ids["goal_id"]:
        issues.append(
            HierarchyEdgeAuthorityIssue(
                "program linked goals did not derive from project-linked goals"
            )
        )

    portfolio_summary = _invoke_json(
        ["portfolio", "summary", ids["portfolio_name"], "--format", "json"],
        env,
    )
    portfolio_stats = portfolio_summary["stats"]
    if portfolio_stats["total_projects"] != 1:
        issues.append(
            HierarchyEdgeAuthorityIssue(
                "portfolio summary total_projects still depends on cached project_ids"
            )
        )
    if portfolio_stats["total_goals"] != 1 or portfolio_stats["total_objectives"] != 1:
        issues.append(
            HierarchyEdgeAuthorityIssue(
                "portfolio summary goal/objective totals still depend on cached hierarchy arrays"
            )
        )

    program_summary = _invoke_json(
        ["program", "summary", ids["program_name"], "--format", "json"],
        env,
    )
    program_stats = program_summary["stats"]
    if program_stats["total_projects"] != 1:
        issues.append(
            HierarchyEdgeAuthorityIssue(
                "program summary total_projects still depends on cached project_ids"
            )
        )
    if program_stats["total_goals"] != 1 or program_stats["total_objectives"] != 1:
        issues.append(
            HierarchyEdgeAuthorityIssue(
                "program summary goal/objective totals still depend on cached hierarchy arrays"
            )
        )

    work_daily = _invoke_json(
        [
            "work",
            "daily",
            "--scope-type",
            "portfolio",
            "--scope",
            ids["portfolio_name"],
            "--format",
            "json",
        ],
        env,
    )
    if work_daily["snapshot"]["totals"]["total_projects"] != 1:
        issues.append(
            HierarchyEdgeAuthorityIssue(
                "work daily portfolio scope still derives project totals from cached hierarchy arrays"
            )
        )

    revision_bundle = _invoke_json(
        [
            "revision",
            "bundle",
            "portfolio",
            ids["portfolio_id"],
            "--include-linked",
            "--format",
            "json",
        ],
        env,
    )
    linked_projects = revision_bundle["linked"].get("projects", [])
    if not linked_projects or linked_projects[0]["id"] != ids["project_id"]:
        issues.append(
            HierarchyEdgeAuthorityIssue(
                "revision bundle linked hierarchy still reflects cached portfolio child arrays"
            )
        )

    return tuple(issues)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail on audit issues")
    args = parser.parse_args()

    issues = run_audit()
    if issues:
        for issue in issues:
            print(f"- {issue.reason}")
        return 1 if args.check else 0

    print("checked=1 issues=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
