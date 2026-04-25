#!/usr/bin/env python3
"""Report active-goal severity and cleanup candidates for the current PMS instance."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_cli_json(args: list[str], env: dict[str, str] | None = None) -> dict[str, Any]:
    result = subprocess.run(
        ["uv", "run", "pms", *args],
        cwd=REPO_ROOT,
        env=env or os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"command failed: {' '.join(args)}\n{result.stdout}{result.stderr}"
        )
    return json.loads(result.stdout)


def _fetch_all_items(
    base_args: list[str], env: dict[str, str] | None = None
) -> list[dict[str, Any]]:
    offset = 0
    items: list[dict[str, Any]] = []
    while True:
        payload = _run_cli_json(
            [*base_args, "--limit", "200", "--offset", str(offset)], env
        )
        items.extend(payload.get("items", []))
        page = payload.get("page", {})
        next_offset = page.get("next_offset")
        if next_offset is None:
            break
        offset = int(next_offset)
    return items


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace(" ", "T")
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _goal_severity(goal: dict[str, Any]) -> str:
    category = goal.get("project_operator_category")
    if category in (None, "active_work"):
        return "high"
    if category == "project_history":
        return "medium"
    return "low"


def run_report(env: dict[str, str] | None = None) -> dict[str, Any]:
    dashboard = _run_cli_json(["dashboard", "--format", "json"], env)
    goals = _fetch_all_items(
        ["goal", "list", "--include-generated", "--format", "json"], env
    )
    projects = _fetch_all_items(
        ["project", "list", "--include-generated", "--format", "json"], env
    )

    active_goals = [goal for goal in goals if goal.get("status") == "active"]
    active_projects = [
        project for project in projects if project.get("status") == "active"
    ]
    severity_counts = Counter(_goal_severity(goal) for goal in active_goals)
    category_counts = Counter(
        goal.get("project_operator_category") or "unscoped" for goal in active_goals
    )

    now = datetime.now(UTC)
    closure_candidates: list[dict[str, Any]] = []
    for project in active_projects:
        category = project.get("operator_category")
        updated_at = _parse_dt(project.get("updated_at"))
        age_days = None
        if updated_at is not None:
            age_days = round((now - updated_at).total_seconds() / 86400, 1)
        if category not in {"project_history", "audit_artifact"}:
            continue
        closure_candidates.append(
            {
                "project_id": project["id"],
                "project_name": project["name"],
                "operator_category": category,
                "in_progress_tasks": project.get("stats", {}).get(
                    "in_progress_tasks", 0
                ),
                "total_goals": project.get("stats", {}).get("total_goals", 0),
                "updated_at": project.get("updated_at"),
                "age_days": age_days,
            }
        )

    visible_active_projects = dashboard.get("scope", {}).get(
        "active_visible_projects", 0
    )
    if visible_active_projects == 0 and severity_counts.get("high", 0) == 0:
        recommendation = "move_on_to_bigger_things"
    elif severity_counts.get("high", 0) > 0:
        recommendation = "finish_current_active_work"
    else:
        recommendation = "cleanup_residual_active_history"

    return {
        "summary": {
            "visible_active_projects": visible_active_projects,
            "active_goal_count": len(active_goals),
            "active_project_count": len(active_projects),
            "severity_counts": dict(severity_counts),
            "category_counts": dict(category_counts),
            "recommendation": recommendation,
        },
        "active_goals": [
            {
                "id": goal["id"],
                "name": goal["name"],
                "project_name": goal.get("project_name"),
                "project_operator_category": goal.get("project_operator_category"),
                "severity": _goal_severity(goal),
                "updated_at": goal.get("updated_at"),
            }
            for goal in active_goals
        ],
        "closure_candidates": closure_candidates,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(json.dumps(run_report(), indent=2))


if __name__ == "__main__":
    main()
