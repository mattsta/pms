#!/usr/bin/env python3
"""Audit end-to-end graph summary timestamp bubble-up behavior across CLI surfaces."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


@dataclass(frozen=True)
class GraphSummarySurfaceIssue:
    """Single graph-summary surface issue."""

    surface: str
    reason: str


@dataclass(frozen=True)
class GraphSummarySurfaceContext:
    """Stable names for one audit workspace."""

    organization: str
    portfolio: str
    program: str
    older_project: str
    goal_project: str
    planless_project: str
    generated_planless_project: str
    completed_project: str
    older_task: str
    planless_task: str
    generated_planless_task: str
    completed_task: str
    completed_plan: str
    goal_name: str
    objective_name: str
    older_plan: str
    fresher_plan: str


def _with_temp_env() -> dict[str, str]:
    temp_dir = Path(
        tempfile.mkdtemp(prefix="graph-summary-audit-", dir=REPO_ROOT / ".tmp")
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


def _context(env: dict[str, str]) -> GraphSummarySurfaceContext:
    suffix = Path(env["PMS_DATA_DIR"]).name.replace("graph-summary-audit-", "")
    return GraphSummarySurfaceContext(
        organization=f"Graph Summary Org {suffix}",
        portfolio=f"Graph Summary Portfolio {suffix}",
        program=f"Graph Summary Program {suffix}",
        older_project=f"Graph Summary Older Project {suffix}",
        goal_project=f"Graph Summary Goal Project {suffix}",
        planless_project=f"Graph Summary Planless Project {suffix}",
        generated_planless_project=f"Audit Project graph-summary-{suffix}",
        completed_project=f"Graph Summary Completed Project {suffix}",
        older_task=f"Graph Summary Older Task {suffix}",
        planless_task=f"Graph Summary Planless Task {suffix}",
        generated_planless_task=f"Graph Summary Generated Planless Task {suffix}",
        completed_task=f"Graph Summary Completed Task {suffix}",
        completed_plan=f"Graph Summary Completed Plan {suffix}",
        goal_name=f"Graph Summary Goal {suffix}",
        objective_name=f"Graph Summary Objective {suffix}",
        older_plan=f"Graph Summary Older Plan {suffix}",
        fresher_plan=f"Graph Summary Fresher Plan {suffix}",
    )


def _run_cli(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "pms", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _invoke_json(
    args: list[str],
    env: dict[str, str],
) -> dict[str, object]:
    result = _run_cli(args, env)
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(args)}\n{result.stdout}{result.stderr}"
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Command emitted invalid JSON: {' '.join(args)}\n{result.stdout}"
        ) from exc


def _record(
    issues: list[GraphSummarySurfaceIssue],
    *,
    surface: str,
    condition: bool,
    reason: str,
) -> None:
    if not condition:
        issues.append(GraphSummarySurfaceIssue(surface=surface, reason=reason))


def _project_names_in_order(items: list[dict[str, object]]) -> list[str]:
    return [str(item.get("name")) for item in items]


def _dashboard_project_names_in_order(items: list[dict[str, object]]) -> list[str]:
    return [str(item.get("project_name") or item.get("name")) for item in items]


def _has_project_summary_shape(item: dict[str, object]) -> bool:
    required = {
        "id",
        "name",
        "project_id",
        "project_name",
        "status",
        "updated_at",
        "last_activity_at",
        "last_transition_at",
        "total_tasks",
        "completed_tasks",
        "in_progress_tasks",
        "blocked_tasks",
        "completion_percent",
        "health_score",
        "links",
    }
    return required.issubset(item) and item.get("id") == item.get("project_id")


def _has_plan_summary_shape(item: dict[str, object]) -> bool:
    required = {
        "id",
        "name",
        "status",
        "stored_status",
        "format",
        "project_id",
        "project_name",
        "product_id",
        "product_name",
        "goal_id",
        "goal_name",
        "objective_id",
        "objective_name",
        "created_at",
        "updated_at",
        "last_activity_at",
        "last_transition_at",
        "terminal_reason",
        "links",
    }
    return required.issubset(item)


def _max_project_item_by_timestamp(
    items: list[dict[str, object]], key: str
) -> dict[str, object]:
    return max(items, key=lambda item: str(item.get(key) or ""))


def _max_surface_item_by_timestamp(
    items: list[dict[str, object]], key: str
) -> dict[str, object]:
    return max(items, key=lambda item: str(item.get(key) or ""))


def run_audit() -> tuple[GraphSummarySurfaceIssue, ...]:
    env = _with_temp_env()
    ctx = _context(env)
    issues: list[GraphSummarySurfaceIssue] = []

    try:
        init_result = _run_cli(["init"], env)
        if init_result.returncode != 0:
            return (
                GraphSummarySurfaceIssue(
                    surface="setup",
                    reason=f"pms init failed\n{init_result.stdout}{init_result.stderr}",
                ),
            )

        org = _invoke_json(
            ["org", "create", ctx.organization, "--format", "json"],
            env,
        )["organization"]
        org_id = str(org["id"])

        portfolio = _invoke_json(
            [
                "portfolio",
                "create",
                ctx.portfolio,
                "--org-id",
                org_id,
                "--format",
                "json",
            ],
            env,
        )["portfolio"]
        portfolio_id = str(portfolio["id"])

        program = _invoke_json(
            [
                "program",
                "create",
                ctx.program,
                "--org-id",
                org_id,
                "--portfolio-id",
                portfolio_id,
                "--format",
                "json",
            ],
            env,
        )["program"]
        program_id = str(program["id"])

        older_project = _invoke_json(
            [
                "project",
                "create",
                ctx.older_project,
                "--org",
                org_id,
                "--portfolio",
                portfolio_id,
                "--program",
                program_id,
                "--format",
                "json",
            ],
            env,
        )["project"]
        older_project_id = str(older_project["id"])
        older_task = _invoke_json(
            ["task", "add", older_project_id, ctx.older_task, "--format", "json"],
            env,
        )["task"]
        older_task_id = str(older_task["id"])
        older_plan = _invoke_json(
            [
                "plan",
                "create",
                ctx.older_plan,
                "--project-id",
                older_project_id,
                "--status",
                "active",
                "--task-id",
                older_task_id,
                "--content",
                "{}",
                "--output-format",
                "json",
            ],
            env,
        )["plan"]
        older_plan_id = str(older_plan["id"])
        archived_plan = _invoke_json(
            [
                "plan",
                "create",
                f"{ctx.older_plan} Archived",
                "--project-id",
                older_project_id,
                "--status",
                "active",
                "--content",
                "{}",
                "--output-format",
                "json",
            ],
            env,
        )["plan"]
        archived_plan_id = str(archived_plan["id"])
        _invoke_json(
            [
                "plan",
                "update",
                archived_plan_id,
                "--status",
                "archived",
                "--output-format",
                "json",
            ],
            env,
        )

        time.sleep(0.05)

        goal_project = _invoke_json(
            [
                "project",
                "create",
                ctx.goal_project,
                "--org",
                org_id,
                "--portfolio",
                portfolio_id,
                "--program",
                program_id,
                "--format",
                "json",
            ],
            env,
        )["project"]
        goal_project_id = str(goal_project["id"])
        goal = _invoke_json(
            [
                "goal",
                "create",
                ctx.goal_name,
                "--project-id",
                goal_project_id,
                "--format",
                "json",
            ],
            env,
        )["goal"]
        goal_id = str(goal["id"])
        objective = _invoke_json(
            [
                "objective",
                "create",
                ctx.objective_name,
                "--goal-id",
                goal_id,
                "--format",
                "json",
            ],
            env,
        )["objective"]
        objective_id = str(objective["id"])
        fresher_plan = _invoke_json(
            [
                "plan",
                "create",
                ctx.fresher_plan,
                "--project-id",
                goal_project_id,
                "--status",
                "active",
                "--content",
                "{}",
                "--output-format",
                "json",
            ],
            env,
        )["plan"]
        fresher_plan_id = str(fresher_plan["id"])
        objective_update = _invoke_json(
            [
                "objective",
                "update",
                objective_id,
                "--status",
                "on_hold",
                "--progress",
                "25",
                "--format",
                "json",
            ],
            env,
        )["objective"]

        time.sleep(0.05)

        planless_project = _invoke_json(
            [
                "project",
                "create",
                ctx.planless_project,
                "--org",
                org_id,
                "--portfolio",
                portfolio_id,
                "--program",
                program_id,
                "--format",
                "json",
            ],
            env,
        )["project"]
        planless_project_id = str(planless_project["id"])
        planless_task = _invoke_json(
            ["task", "add", planless_project_id, ctx.planless_task, "--format", "json"],
            env,
        )["task"]
        planless_task_id = str(planless_task["id"])
        _invoke_json(
            [
                "task",
                "start",
                planless_task_id,
                "--by",
                "graph-audit",
                "--format",
                "json",
            ],
            env,
        )
        _invoke_json(
            [
                "task",
                "progress",
                planless_task_id,
                "60",
                "Graph summary freshest activity",
                "--by",
                "graph-audit",
                "--format",
                "json",
            ],
            env,
        )

        generated_planless_project = _invoke_json(
            [
                "project",
                "create",
                ctx.generated_planless_project,
                "--org",
                org_id,
                "--portfolio",
                portfolio_id,
                "--program",
                program_id,
                "--format",
                "json",
            ],
            env,
        )["project"]
        generated_planless_project_id = str(generated_planless_project["id"])
        generated_planless_task = _invoke_json(
            [
                "task",
                "add",
                generated_planless_project_id,
                ctx.generated_planless_task,
                "--format",
                "json",
            ],
            env,
        )["task"]
        generated_planless_task_id = str(generated_planless_task["id"])
        _invoke_json(
            [
                "task",
                "start",
                generated_planless_task_id,
                "--by",
                "graph-audit",
                "--format",
                "json",
            ],
            env,
        )
        _invoke_json(
            [
                "task",
                "progress",
                generated_planless_task_id,
                "80",
                "Generated graph summary activity",
                "--by",
                "graph-audit",
                "--format",
                "json",
            ],
            env,
        )

        completed_project = _invoke_json(
            [
                "project",
                "create",
                ctx.completed_project,
                "--org",
                org_id,
                "--portfolio",
                portfolio_id,
                "--program",
                program_id,
                "--format",
                "json",
            ],
            env,
        )["project"]
        completed_project_id = str(completed_project["id"])
        completed_task = _invoke_json(
            [
                "task",
                "add",
                completed_project_id,
                ctx.completed_task,
                "--format",
                "json",
            ],
            env,
        )["task"]
        completed_task_id = str(completed_task["id"])
        _invoke_json(
            [
                "task",
                "complete",
                completed_task_id,
                "--by",
                "graph-audit",
                "--format",
                "json",
            ],
            env,
        )
        completed_plan = _invoke_json(
            [
                "plan",
                "create",
                ctx.completed_plan,
                "--project-id",
                completed_project_id,
                "--status",
                "completed",
                "--task-id",
                completed_task_id,
                "--content",
                "{}",
                "--output-format",
                "json",
            ],
            env,
        )["plan"]
        completed_plan_id = str(completed_plan["id"])
        complete_project_result = _run_cli(
            ["project", "complete", ctx.completed_project],
            env,
        )
        if complete_project_result.returncode != 0:
            raise RuntimeError(
                "Command failed: project complete\n"
                f"{complete_project_result.stdout}{complete_project_result.stderr}"
            )
        completed_task_comment = _run_cli(
            [
                "comment",
                "add",
                "task",
                completed_task_id,
                "Terminal graph follow-up comment",
                "--by",
                "graph-audit",
            ],
            env,
        )
        if completed_task_comment.returncode != 0:
            raise RuntimeError(
                "Command failed: comment add\n"
                f"{completed_task_comment.stdout}{completed_task_comment.stderr}"
            )

        project_list = _invoke_json(["project", "list", "--format", "json"], env)
        paged_project_list = _invoke_json(
            ["project", "list", "--format", "json", "--limit", "1", "--offset", "1"],
            env,
        )
        plan_list = _invoke_json(["plan", "list", "--format", "json"], env)
        paged_plan_list = _invoke_json(
            ["plan", "list", "--format", "json", "--limit", "1", "--offset", "1"],
            env,
        )
        archived_plan_show = _invoke_json(
            ["plan", "show", archived_plan_id, "--format", "json"],
            env,
        )
        archived_plan_lineage = _invoke_json(
            ["plan", "lineage", "--plan-id", archived_plan_id, "--format", "json"],
            env,
        )
        dashboard = _invoke_json(["dashboard", "--format", "json"], env)
        start_payload = _invoke_json(["start", "--format", "json"], env)
        org_dashboard = _invoke_json(["org", "dashboard", "--format", "json"], env)
        portfolio_dashboard = _invoke_json(
            [
                "portfolio",
                "dashboard",
                "--org-id",
                org_id,
                "--format",
                "json",
            ],
            env,
        )
        program_dashboard = _invoke_json(
            [
                "program",
                "dashboard",
                "--org-id",
                org_id,
                "--portfolio-id",
                portfolio_id,
                "--format",
                "json",
            ],
            env,
        )

        all_project_items = [
            item
            for item in project_list["items"]
            if item["id"]
            in {
                older_project_id,
                goal_project_id,
                planless_project_id,
                completed_project_id,
            }
        ]
        project_items = [
            item
            for item in all_project_items
            if item["id"] in {older_project_id, goal_project_id, planless_project_id}
        ]
        _record(
            issues,
            surface="project list",
            condition=_project_names_in_order(project_items[:3])
            == [ctx.planless_project, ctx.goal_project, ctx.older_project],
            reason=(
                "project list should order visible projects by bubbled graph activity "
                "across task and goal/objective subtrees"
            ),
        )

        goal_project_item = next(
            item for item in project_items if item["id"] == goal_project_id
        )
        planless_project_item = next(
            item for item in project_items if item["id"] == planless_project_id
        )
        completed_project_item = next(
            item for item in all_project_items if item["id"] == completed_project_id
        )
        older_project_item = next(
            item for item in project_items if item["id"] == older_project_id
        )
        freshest_visible_project_activity = _max_project_item_by_timestamp(
            all_project_items, "last_activity_at"
        )
        freshest_visible_project_transition = _max_project_item_by_timestamp(
            all_project_items, "last_transition_at"
        )
        _record(
            issues,
            surface="project list",
            condition=bool(goal_project_item["last_activity_at"])
            and bool(planless_project_item["last_activity_at"])
            and bool(older_project_item["last_activity_at"]),
            reason="project list should surface last_activity_at for bubbled project recency",
        )
        _record(
            issues,
            surface="project list",
            condition=bool(goal_project_item["last_transition_at"])
            and bool(planless_project_item["last_transition_at"]),
            reason="project list should surface last_transition_at for deep graph transitions",
        )
        _record(
            issues,
            surface="project list",
            condition=_has_project_summary_shape(planless_project_item),
            reason="project list items should expose canonical and aliased project summary fields",
        )
        _record(
            issues,
            surface="project list",
            condition=completed_project_item["status"] == "completed"
            and completed_project_item["operator_category"] != "active_work"
            and project_list["freshest_visible_activity"]["project_id"]
            == completed_project_id,
            reason=(
                "project list should keep completed projects terminal even when a "
                "nested completed task becomes the freshest visible activity"
            ),
        )
        _record(
            issues,
            surface="project list",
            condition=all(
                item["project_name"] != ctx.generated_planless_project
                for item in project_list["items"]
            )
            and project_list["suppressed_generated_count"] >= 1,
            reason=(
                "project list should suppress generated projects by default and "
                "report the suppression count"
            ),
        )
        _record(
            issues,
            surface="project list",
            condition=project_list["freshest_visible_activity"]["project_id"]
            == freshest_visible_project_activity["project_id"]
            and _has_project_summary_shape(project_list["freshest_visible_activity"]),
            reason=(
                "project list should expose the freshest visible project activity "
                "as a canonical project summary payload"
            ),
        )
        _record(
            issues,
            surface="project list",
            condition=project_list["freshest_visible_transition"]["project_id"]
            == freshest_visible_project_transition["project_id"]
            and _has_project_summary_shape(project_list["freshest_visible_transition"]),
            reason=(
                "project list should expose the freshest visible project transition "
                "as a canonical project summary payload"
            ),
        )
        _record(
            issues,
            surface="project list",
            condition=paged_project_list["freshest_visible_activity"]["project_id"]
            == project_list["freshest_visible_activity"]["project_id"]
            and paged_project_list["freshest_visible_transition"]["project_id"]
            == project_list["freshest_visible_transition"]["project_id"]
            and _has_project_summary_shape(
                paged_project_list["freshest_visible_activity"]
            )
            and _has_project_summary_shape(
                paged_project_list["freshest_visible_transition"]
            ),
            reason=(
                "project list freshest visible activity and transition should be "
                "stable across pagination offsets"
            ),
        )

        plan_items = [
            item
            for item in plan_list["items"]
            if item["id"] in {older_plan_id, fresher_plan_id}
        ]
        _record(
            issues,
            surface="plan list",
            condition=[str(item["id"]) for item in plan_items[:2]]
            == [fresher_plan_id, older_plan_id],
            reason=(
                "plan list should order active plans by bubbled project/goal/objective "
                "activity, not raw plan row timestamps"
            ),
        )
        freshest_visible_plan_activity = _max_surface_item_by_timestamp(
            plan_list["items"], "last_activity_at"
        )
        freshest_visible_plan_transition = _max_surface_item_by_timestamp(
            plan_list["items"], "last_transition_at"
        )
        freshest_unplanned_project_activity = _max_project_item_by_timestamp(
            plan_list["projects_without_plans"], "last_activity_at"
        )
        freshest_unplanned_project_transition = _max_project_item_by_timestamp(
            plan_list["projects_without_plans"], "last_transition_at"
        )
        expected_freshest_activity = freshest_visible_plan_activity
        expected_freshest_activity_kind = "plan"
        if str(freshest_unplanned_project_activity["last_activity_at"]) > str(
            freshest_visible_plan_activity["last_activity_at"] or ""
        ):
            expected_freshest_activity = freshest_unplanned_project_activity
            expected_freshest_activity_kind = "project_without_plan"
        expected_freshest_transition = freshest_visible_plan_transition
        expected_freshest_transition_kind = "plan"
        if str(freshest_unplanned_project_transition["last_transition_at"]) > str(
            freshest_visible_plan_transition["last_transition_at"] or ""
        ):
            expected_freshest_transition = freshest_unplanned_project_transition
            expected_freshest_transition_kind = "project_without_plan"

        _record(
            issues,
            surface="plan list",
            condition=plan_list["freshest_visible_activity"]["kind"]
            == expected_freshest_activity_kind
            and (
                plan_list["freshest_visible_activity"]["plan_id"]
                == expected_freshest_activity["id"]
                if expected_freshest_activity_kind == "plan"
                else plan_list["freshest_visible_activity"]["project_id"]
                == expected_freshest_activity["project_id"]
            ),
            reason=(
                "plan list freshest visible activity should identify the freshest "
                "visible entity across planned and planless work"
            ),
        )
        _record(
            issues,
            surface="plan list",
            condition=plan_list["freshest_visible_transition"]["kind"]
            == expected_freshest_transition_kind
            and (
                plan_list["freshest_visible_transition"]["plan_id"]
                == expected_freshest_transition["id"]
                if expected_freshest_transition_kind == "plan"
                else plan_list["freshest_visible_transition"]["project_id"]
                == expected_freshest_transition["project_id"]
            ),
            reason=(
                "plan list freshest visible transition should identify the freshest "
                "visible lifecycle transition across planned and planless work"
            ),
        )
        _record(
            issues,
            surface="plan list",
            condition=paged_plan_list["freshest_visible_activity"]["kind"]
            == plan_list["freshest_visible_activity"]["kind"]
            and paged_plan_list["freshest_visible_transition"]["kind"]
            == plan_list["freshest_visible_transition"]["kind"]
            and (
                paged_plan_list["freshest_visible_activity"]["plan_id"]
                == plan_list["freshest_visible_activity"]["plan_id"]
                if plan_list["freshest_visible_activity"]["kind"] == "plan"
                else paged_plan_list["freshest_visible_activity"]["project_id"]
                == plan_list["freshest_visible_activity"]["project_id"]
            )
            and (
                paged_plan_list["freshest_visible_transition"]["plan_id"]
                == plan_list["freshest_visible_transition"]["plan_id"]
                if plan_list["freshest_visible_transition"]["kind"] == "plan"
                else paged_plan_list["freshest_visible_transition"]["project_id"]
                == plan_list["freshest_visible_transition"]["project_id"]
            ),
            reason=(
                "plan list freshest visible activity and transition should be stable "
                "across pagination offsets"
            ),
        )
        planless_entry = next(
            item
            for item in plan_list["projects_without_plans"]
            if item["id"] == planless_project_id
        )
        _record(
            issues,
            surface="plan list",
            condition=_has_project_summary_shape(planless_entry),
            reason=(
                "plan list projects_without_plans should expose canonical and aliased "
                "project summary fields"
            ),
        )
        _record(
            issues,
            surface="plan list",
            condition=all(
                item["project_name"] != ctx.generated_planless_project
                for item in plan_list["projects_without_plans"]
            )
            and plan_list["projects_without_plans_summary"][
                "suppressed_generated_count"
            ]
            >= 1,
            reason=(
                "plan list projects_without_plans should suppress generated planless "
                "projects by default and report the suppression count"
            ),
        )
        _record(
            issues,
            surface="plan list",
            condition=plan_list["projects_without_plans_summary"]["displayed_count"]
            == len(plan_list["projects_without_plans"])
            and plan_list["projects_without_plans_summary"]["total_count"]
            >= len(plan_list["projects_without_plans"])
            and plan_list["projects_without_plans_by_category"]["active_work"][0]["id"]
            == planless_project_id,
            reason=(
                "plan list should expose planless project visibility summary metadata "
                "and operator-category grouping"
            ),
        )
        _record(
            issues,
            surface="plan list",
            condition=all(
                plan_list["status_groups"][status_key]
                == len(plan_list["items_by_status"][status_key])
                for status_key in ("active", "draft", "completed", "archived")
            ),
            reason=(
                "plan list status_groups should match items_by_status counts for the "
                "visible plan population"
            ),
        )
        completed_plan_entry = next(
            item
            for item in plan_list["recently_completed_plans"]
            if item["id"] == completed_plan_id
        )
        completed_plan_active_ids = {
            item["id"] for item in plan_list["items_by_status"]["active"]
        }
        completed_plan_completed_ids = {
            item["id"] for item in plan_list["items_by_status"]["completed"]
        }
        _record(
            issues,
            surface="plan list",
            condition=_has_plan_summary_shape(completed_plan_entry)
            and completed_plan_entry["status"] == "completed"
            and completed_plan_entry["terminal_reason"]
            == "plan is already marked completed"
            and completed_plan_id not in completed_plan_active_ids
            and completed_plan_id in completed_plan_completed_ids
            and plan_list["freshest_visible_activity"]["kind"] == "plan"
            and plan_list["freshest_visible_activity"]["plan_id"] == completed_plan_id,
            reason=(
                "plan list recently_completed_plans should reuse the authoritative "
                "plan summary shape with terminal lifecycle context even when "
                "nested completed-task activity is freshest"
            ),
        )
        archived_plan_entry = next(
            item
            for item in plan_list["items_by_status"]["archived"]
            if item["id"] == archived_plan_id
        )
        archived_lineage_item = next(
            item
            for item in archived_plan_lineage["items"]
            if item["plan"]["id"] == archived_plan_id
        )
        _record(
            issues,
            surface="archived plan parity",
            condition=_has_plan_summary_shape(archived_plan_entry)
            and archived_plan_entry["status"] == "archived"
            and archived_plan_entry["stored_status"] == "archived"
            and archived_plan_entry["terminal_reason"] == "plan is already archived"
            and archived_plan_show["status"] == "archived"
            and archived_plan_show["stored_status"] == "archived"
            and archived_plan_show["terminal_reason"] == "plan is already archived"
            and archived_plan_show["last_transition_at"]
            == archived_plan_entry["last_transition_at"]
            and archived_plan_lineage["terminal_reason"] == "plan is already archived"
            and archived_lineage_item["plan"]["status"] == "archived"
            and archived_lineage_item["plan"]["stored_status"] == "archived"
            and archived_lineage_item["plan"]["terminal_reason"]
            == "plan is already archived"
            and archived_lineage_item["plan"]["last_transition_at"]
            == archived_plan_entry["last_transition_at"],
            reason=(
                "archived plans should keep the same terminal lifecycle and "
                "transition metadata across list, show, and lineage surfaces"
            ),
        )

        active_projects = [
            item
            for item in dashboard["active_projects"]
            if item["project_id"]
            in {older_project_id, goal_project_id, planless_project_id}
        ]
        dashboard_planless_item = next(
            item
            for item in active_projects
            if item["project_id"] == planless_project_id
        )
        _record(
            issues,
            surface="dashboard",
            condition=_dashboard_project_names_in_order(active_projects[:3])
            == [ctx.planless_project, ctx.goal_project, ctx.older_project],
            reason=(
                "dashboard active_projects should order visible projects by bubbled "
                "graph recency"
            ),
        )
        _record(
            issues,
            surface="dashboard",
            condition=all(_has_project_summary_shape(item) for item in active_projects),
            reason=(
                "dashboard active_projects should expose canonical and aliased "
                "project summary fields"
            ),
        )
        _record(
            issues,
            surface="planless parity",
            condition=planless_entry["status"]
            == planless_project_item["status"]
            == dashboard_planless_item["status"]
            and planless_entry["last_transition_at"]
            == planless_project_item["last_transition_at"]
            == dashboard_planless_item["last_transition_at"]
            and planless_entry["last_activity_at"]
            == planless_project_item["last_activity_at"]
            == dashboard_planless_item["last_activity_at"],
            reason=(
                "planless projects should keep identical status/activity/transition "
                "story across plan list, project list, and dashboard"
            ),
        )
        dashboard_freshest_project_activity = _max_project_item_by_timestamp(
            [*dashboard["active_projects"], *dashboard["recently_completed_projects"]],
            "last_activity_at",
        )
        dashboard_freshest_project_transition = _max_project_item_by_timestamp(
            [*dashboard["active_projects"], *dashboard["recently_completed_projects"]],
            "last_transition_at",
        )
        _record(
            issues,
            surface="dashboard",
            condition=dashboard["freshest_visible_activity"]["project_id"]
            == dashboard_freshest_project_activity["project_id"]
            and _has_project_summary_shape(dashboard["freshest_visible_activity"]),
            reason=(
                "dashboard should expose the freshest visible project activity as a "
                "canonical project summary payload"
            ),
        )
        _record(
            issues,
            surface="dashboard",
            condition=dashboard["freshest_visible_transition"]["project_id"]
            == dashboard_freshest_project_transition["project_id"]
            and _has_project_summary_shape(dashboard["freshest_visible_transition"]),
            reason=(
                "dashboard should expose the freshest visible project transition as a "
                "canonical project summary payload"
            ),
        )

        completed_dashboard_item = next(
            item
            for item in dashboard["recently_completed_projects"]
            if item["project_id"] == completed_project_id
        )
        dashboard_completion_item = dashboard["completion_context"]["items"][0]
        _record(
            issues,
            surface="dashboard",
            condition=_has_project_summary_shape(completed_dashboard_item)
            and completed_dashboard_item["status"] == "completed",
            reason=(
                "dashboard recently_completed_projects should expose canonical and "
                "aliased project summary fields with terminal status"
            ),
        )
        _record(
            issues,
            surface="dashboard",
            condition=_has_project_summary_shape(dashboard_completion_item)
            and dashboard_completion_item["project_id"] == completed_project_id
            and dashboard_completion_item["last_transition_at"]
            == completed_dashboard_item["last_transition_at"]
            and bool(dashboard_completion_item.get("next_steps")),
            reason=(
                "dashboard completion_context items should keep canonical project "
                "summary fields, transition truth, and actionable next steps"
            ),
        )
        _record(
            issues,
            surface="dashboard",
            condition=completed_project_id
            not in {item["project_id"] for item in dashboard["active_projects"]}
            and dashboard["freshest_visible_activity"]["project_id"]
            == completed_project_id,
            reason=(
                "dashboard should keep completed projects out of active_projects "
                "even when nested completed-task activity is freshest"
            ),
        )

        start_freshest_project_activity = _max_project_item_by_timestamp(
            [
                *start_payload["active_projects"],
                *start_payload["recently_completed_projects"],
            ],
            "last_activity_at",
        )
        start_freshest_project_transition = _max_project_item_by_timestamp(
            [
                *start_payload["active_projects"],
                *start_payload["recently_completed_projects"],
            ],
            "last_transition_at",
        )
        completed_start_item = next(
            item
            for item in start_payload["recently_completed_projects"]
            if item["project_id"] == completed_project_id
        )
        start_completion_item = start_payload["completion_context"]["items"][0]
        _record(
            issues,
            surface="start",
            condition=_has_project_summary_shape(completed_start_item)
            and completed_start_item["status"] == "completed"
            and start_payload["focus_task"] is not None,
            reason=(
                "start should expose canonical recent terminal project payloads "
                "without dropping active focus"
            ),
        )
        _record(
            issues,
            surface="start",
            condition=_has_project_summary_shape(start_completion_item)
            and start_completion_item["project_id"] == completed_project_id
            and start_completion_item["last_transition_at"]
            == completed_start_item["last_transition_at"]
            and bool(start_completion_item.get("next_steps")),
            reason=(
                "start completion_context items should keep canonical project "
                "summary fields, transition truth, and actionable next steps"
            ),
        )
        _record(
            issues,
            surface="start",
            condition=start_payload["freshest_visible_activity"]["project_id"]
            == start_freshest_project_activity["project_id"]
            and _has_project_summary_shape(start_payload["freshest_visible_activity"]),
            reason=(
                "start should expose the freshest visible project activity as a "
                "canonical project summary payload"
            ),
        )
        _record(
            issues,
            surface="start",
            condition=start_payload["freshest_visible_transition"]["project_id"]
            == start_freshest_project_transition["project_id"]
            and _has_project_summary_shape(
                start_payload["freshest_visible_transition"]
            ),
            reason=(
                "start should expose the freshest visible project transition as a "
                "canonical project summary payload"
            ),
        )
        _record(
            issues,
            surface="start",
            condition="Recently completed scoped work remains terminal"
            in start_payload["completion_context"]["summary"],
            reason=(
                "start should retain recent terminal work context alongside active focus"
            ),
        )

        org_item = org_dashboard["items"][0]
        portfolio_item = portfolio_dashboard["items"][0]
        program_item = program_dashboard["items"][0]

        for surface_name, item in (
            ("org dashboard", org_item),
            ("portfolio dashboard", portfolio_item),
            ("program dashboard", program_item),
        ):
            _record(
                issues,
                surface=surface_name,
                condition=item["last_activity_at"]
                == freshest_visible_project_activity["last_activity_at"],
                reason=(
                    f"{surface_name} should bubble the freshest nested project activity "
                    "all the way up the graph"
                ),
            )
            _record(
                issues,
                surface=surface_name,
                condition=item["last_transition_at"]
                == freshest_visible_project_transition["last_transition_at"],
                reason=(
                    f"{surface_name} should bubble the freshest nested project transition "
                    "all the way up the graph"
                ),
            )

        program_review = _invoke_json(
            [
                "work",
                "review",
                "--scope-type",
                "program",
                "--scope-id",
                program_id,
                "--reviewed-by",
                "graph-audit",
                "--note",
                "Program review propagation",
                "--format",
                "json",
            ],
            env,
        )
        org_after_program_review = _invoke_json(
            ["org", "dashboard", "--format", "json"],
            env,
        )["items"][0]
        portfolio_after_program_review = _invoke_json(
            [
                "portfolio",
                "dashboard",
                "--org-id",
                org_id,
                "--format",
                "json",
            ],
            env,
        )["items"][0]
        program_after_program_review = _invoke_json(
            [
                "program",
                "dashboard",
                "--org-id",
                org_id,
                "--portfolio-id",
                portfolio_id,
                "--format",
                "json",
            ],
            env,
        )["items"][0]
        for surface_name, item, baseline_transition in (
            (
                "program dashboard",
                program_after_program_review,
                program_item["last_transition_at"],
            ),
            (
                "portfolio dashboard",
                portfolio_after_program_review,
                portfolio_item["last_transition_at"],
            ),
            (
                "org dashboard",
                org_after_program_review,
                org_item["last_transition_at"],
            ),
        ):
            _record(
                issues,
                surface=surface_name,
                condition=item["last_activity_at"] == program_review["reviewed_at"],
                reason=(
                    f"{surface_name} should bubble direct program work reviews into "
                    "summary activity timestamps"
                ),
            )
            _record(
                issues,
                surface=surface_name,
                condition=item["last_transition_at"] == baseline_transition,
                reason=(
                    f"{surface_name} should keep lifecycle transition timestamps stable "
                    "when only work review activity changes"
                ),
            )

        portfolio_review = _invoke_json(
            [
                "work",
                "review",
                "--scope-type",
                "portfolio",
                "--scope-id",
                portfolio_id,
                "--reviewed-by",
                "graph-audit",
                "--note",
                "Portfolio review propagation",
                "--format",
                "json",
            ],
            env,
        )
        org_after_portfolio_review = _invoke_json(
            ["org", "dashboard", "--format", "json"],
            env,
        )["items"][0]
        portfolio_after_portfolio_review = _invoke_json(
            [
                "portfolio",
                "dashboard",
                "--org-id",
                org_id,
                "--format",
                "json",
            ],
            env,
        )["items"][0]
        _record(
            issues,
            surface="portfolio dashboard",
            condition=portfolio_after_portfolio_review["last_activity_at"]
            == portfolio_review["reviewed_at"],
            reason=(
                "portfolio dashboard should bubble direct portfolio reviews into "
                "summary activity timestamps"
            ),
        )
        _record(
            issues,
            surface="org dashboard",
            condition=org_after_portfolio_review["last_activity_at"]
            == portfolio_review["reviewed_at"],
            reason=(
                "org dashboard should bubble child portfolio reviews into "
                "summary activity timestamps"
            ),
        )
        _record(
            issues,
            surface="portfolio dashboard",
            condition=portfolio_after_portfolio_review["last_transition_at"]
            == portfolio_item["last_transition_at"],
            reason=(
                "portfolio dashboard should keep transition timestamps stable when "
                "a direct review is the freshest change"
            ),
        )
        _record(
            issues,
            surface="org dashboard",
            condition=org_after_portfolio_review["last_transition_at"]
            == org_item["last_transition_at"],
            reason=(
                "org dashboard should keep transition timestamps stable when a child "
                "portfolio review is the freshest change"
            ),
        )

        org_review = _invoke_json(
            [
                "work",
                "review",
                "--scope-type",
                "organization",
                "--scope-id",
                org_id,
                "--reviewed-by",
                "graph-audit",
                "--note",
                "Organization review propagation",
                "--format",
                "json",
            ],
            env,
        )
        org_after_org_review = _invoke_json(
            ["org", "dashboard", "--format", "json"],
            env,
        )["items"][0]
        _record(
            issues,
            surface="org dashboard",
            condition=org_after_org_review["last_activity_at"]
            == org_review["reviewed_at"],
            reason=(
                "org dashboard should bubble direct organization reviews into "
                "summary activity timestamps"
            ),
        )
        _record(
            issues,
            surface="org dashboard",
            condition=org_after_org_review["last_transition_at"]
            == org_item["last_transition_at"],
            reason=(
                "org dashboard should keep transition timestamps stable when only "
                "organization review activity changes"
            ),
        )

        _record(
            issues,
            surface="goal subtree mutation",
            condition=str(objective_update["status"]) == "on_hold"
            and int(objective_update["progress_percent"]) == 25,
            reason="goal/objective mutation setup did not produce the expected nested state change",
        )
    except Exception as exc:  # pragma: no cover - surfaced as audit issue
        issues.append(
            GraphSummarySurfaceIssue(
                surface="setup",
                reason=str(exc),
            )
        )

    return tuple(issues)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit graph summary surfaces for end-to-end bubbled recency truth."
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON payload")
    parser.add_argument("--check", action="store_true", help="Exit non-zero on issues")
    args = parser.parse_args()

    issues = run_audit()
    if args.json:
        print(
            json.dumps(
                {
                    "checked": 6,
                    "issues": [
                        {"surface": issue.surface, "reason": issue.reason}
                        for issue in issues
                    ],
                },
                indent=2,
            )
        )
    else:
        print(f"Graph summary surface truth audit\nchecked=6 issues={len(issues)}")
        for issue in issues:
            print(f"- {issue.surface}: {issue.reason}")

    if args.check and issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
