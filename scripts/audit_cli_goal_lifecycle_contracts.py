#!/usr/bin/env python3
"""Audit CLI goal aggregate surfaces against shared lifecycle rollups."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.db.connection import Database
from pms.services.goal_service import GoalService
from pms.services.project_service import ProjectService
from pms.services.task_service import TaskService
from pms.utils.cli_commands import cli_command
from scripts.cli_surface_audit_utils import require_success, run_cli, with_temp_env
from scripts.goal_lifecycle_contract_utils import (
    GoalLifecycleExpectation,
    goal_detail_payload_mismatch_reasons,
    goal_list_payload_mismatch_reasons,
    goal_summary_payload_mismatch_reasons,
)
from scripts.lifecycle_aggregate_fixture import (
    build_goal_lifecycle_expectations,
    seed_goal_lifecycle_fixture,
)


@dataclass(frozen=True)
class CliGoalLifecycleIssue:
    """One CLI goal lifecycle contract failure."""

    surface: str
    reason: str


def _extract_id(output: str) -> str:
    match = re.search(r"ID:\s*([0-9a-f-]{36})", output)
    if match is None:
        raise RuntimeError(f"unable to extract id from output:\n{output}")
    return match.group(1)


def _record(
    issues: list[CliGoalLifecycleIssue],
    *,
    surface: str,
    reason: str,
) -> None:
    issues.append(CliGoalLifecycleIssue(surface=surface, reason=reason))


def _goal_item(items: list[dict[str, object]], goal_id: str) -> dict[str, object]:
    for item in items:
        if item.get("id") == goal_id:
            return item
    raise RuntimeError(f"Goal {goal_id} not found in payload")


def _evaluate_goal_list_item_payload(
    surface: str,
    payload: dict[str, object],
    expectation: GoalLifecycleExpectation,
    *,
    project_id: str | None,
) -> tuple[CliGoalLifecycleIssue, ...]:
    issues: list[CliGoalLifecycleIssue] = []
    for reason in goal_list_payload_mismatch_reasons(payload, expectation):
        _record(issues, surface=surface, reason=reason)

    links = payload.get("links")
    if not isinstance(links, dict):
        _record(issues, surface=surface, reason="links missing")
    else:
        if links.get("self") != cli_command(f"goal show {expectation.goal_id}"):
            _record(issues, surface=surface, reason="self link mismatch")
        if links.get("summary") != cli_command(f"goal summary {expectation.goal_id}"):
            _record(issues, surface=surface, reason="summary link mismatch")
        if links.get("objectives") != cli_command(
            f"objective list --goal-id {expectation.goal_id}"
        ):
            _record(issues, surface=surface, reason="objectives link mismatch")
        if links.get("plans") != cli_command(
            f"plan list --goal-id {expectation.goal_id} --format json"
        ):
            _record(issues, surface=surface, reason="plans link mismatch")
        if project_id is not None:
            if links.get("project") != cli_command(
                f"project show {project_id} --format json"
            ):
                _record(issues, surface=surface, reason="project link mismatch")
            if links.get("tasks") != cli_command(
                f"task list --project {project_id} --format json"
            ):
                _record(issues, surface=surface, reason="tasks link mismatch")

    return tuple(issues)


def _evaluate_goal_show_payload(
    surface: str,
    payload: dict[str, object],
    expectation: GoalLifecycleExpectation,
    *,
    project_id: str | None,
) -> tuple[CliGoalLifecycleIssue, ...]:
    issues: list[CliGoalLifecycleIssue] = []
    for reason in goal_detail_payload_mismatch_reasons(payload, expectation):
        _record(issues, surface=surface, reason=reason)

    links = payload.get("links")
    if not isinstance(links, dict):
        _record(issues, surface=surface, reason="links missing")
    else:
        if links.get("self") != cli_command(f"goal show {expectation.goal_id}"):
            _record(issues, surface=surface, reason="self link mismatch")
        if links.get("summary") != cli_command(f"goal summary {expectation.goal_id}"):
            _record(issues, surface=surface, reason="summary link mismatch")
        if links.get("objectives") != cli_command(
            f"objective list --goal-id {expectation.goal_id}"
        ):
            _record(issues, surface=surface, reason="objectives link mismatch")
        if links.get("plans") != cli_command(
            f"plan list --goal-id {expectation.goal_id} --format json"
        ):
            _record(issues, surface=surface, reason="plans link mismatch")
        if project_id is not None:
            if links.get("project") != cli_command(
                f"project show {project_id} --format json"
            ):
                _record(issues, surface=surface, reason="project link mismatch")
            if links.get("tasks") != cli_command(
                f"task list --project {project_id} --format json"
            ):
                _record(issues, surface=surface, reason="tasks link mismatch")

    next_steps = payload.get("next_steps")
    if not isinstance(next_steps, list) or not next_steps:
        _record(issues, surface=surface, reason="next_steps missing")
    elif expectation.execution_focus_task_id is not None:
        first_step = next_steps[0]
        if not isinstance(first_step, str) or not first_step.startswith(
            cli_command("task show ")
        ):
            _record(issues, surface=surface, reason="focus-task next step mismatch")
    elif expectation.terminal_reason is not None:
        if next_steps[0] != cli_command(f"goal show {expectation.goal_id}"):
            _record(issues, surface=surface, reason="terminal next step mismatch")

    return tuple(issues)


def _evaluate_goal_summary_payload(
    surface: str,
    payload: dict[str, object],
    expectation: GoalLifecycleExpectation,
    *,
    project_id: str | None,
) -> tuple[CliGoalLifecycleIssue, ...]:
    issues: list[CliGoalLifecycleIssue] = []
    for reason in goal_summary_payload_mismatch_reasons(payload, expectation):
        _record(issues, surface=surface, reason=reason)

    links = payload.get("links")
    if not isinstance(links, dict):
        _record(issues, surface=surface, reason="links missing")
    else:
        if links.get("self") != cli_command(f"goal summary {expectation.goal_id}"):
            _record(issues, surface=surface, reason="self link mismatch")
        if links.get("goal") != cli_command(f"goal show {expectation.goal_id}"):
            _record(issues, surface=surface, reason="goal link mismatch")
        if links.get("objectives") != cli_command(
            f"objective list --goal-id {expectation.goal_id} --format json"
        ):
            _record(issues, surface=surface, reason="objectives link mismatch")
        if links.get("plans") != cli_command(
            f"plan list --goal-id {expectation.goal_id} --format json"
        ):
            _record(issues, surface=surface, reason="plans link mismatch")
        if project_id is not None:
            if links.get("project") != cli_command(
                f"project show {project_id} --format json"
            ):
                _record(issues, surface=surface, reason="project link mismatch")
            if links.get("tasks") != cli_command(
                f"task list --project {project_id} --format json"
            ):
                _record(issues, surface=surface, reason="tasks link mismatch")

    next_steps = payload.get("next_steps")
    if not isinstance(next_steps, list) or not next_steps:
        _record(issues, surface=surface, reason="next_steps missing")
    elif expectation.execution_focus_task_id is not None:
        first_step = next_steps[0]
        if not isinstance(first_step, str) or not first_step.startswith(
            cli_command("task show ")
        ):
            _record(issues, surface=surface, reason="focus-task next step mismatch")
    elif expectation.terminal_reason is not None:
        if next_steps[0] != cli_command(f"goal show {expectation.goal_id}"):
            _record(issues, surface=surface, reason="terminal next step mismatch")

    return tuple(issues)


async def run_audit() -> tuple[CliGoalLifecycleIssue, ...]:
    """Seed goals and ensure CLI aggregate surfaces expose shared lifecycle rollups."""
    env = with_temp_env("cli-goal-lifecycle-audit-")
    init_result = run_cli(["init"], env, width=120)
    require_success(init_result, args=["init"])

    db = Database(Path(env["PMS_DATABASE_PATH"]))
    await db.connect()
    issues: list[CliGoalLifecycleIssue] = []
    try:
        event_store = EventStore(db)
        revision_store = RevisionStore(db)
        metrics = MetricsCollector(db)
        project_service = ProjectService(db, event_store, revision_store, metrics)
        task_service = TaskService(db, event_store, revision_store, metrics)
        goal_service = GoalService(db, event_store, revision_store, metrics)
        fixture = await seed_goal_lifecycle_fixture(
            project_service,
            goal_service,
            task_service,
            active_project_name="CLI Goal Lifecycle Active Project",
            active_goal_name="CLI Goal Lifecycle Active Goal",
            active_task_title="CLI Goal Lifecycle Active Task",
            active_progress_percent=45,
            active_status_message="Implementing",
            active_updated_by="goal-audit",
            terminal_project_name="CLI Goal Lifecycle Terminal Project",
            terminal_goal_name="CLI Goal Lifecycle Terminal Goal",
            terminal_task_title="CLI Goal Lifecycle Terminal Task",
        )
        expectations, project_ids = await build_goal_lifecycle_expectations(
            goal_service,
            [fixture.active_goal_id, fixture.terminal_goal_id],
        )
        project_names = {
            fixture.active_goal_id: "CLI Goal Lifecycle Active Project",
            fixture.terminal_goal_id: "CLI Goal Lifecycle Terminal Project",
        }

        checked = (
            ("goal.list.active", fixture.active_goal_id),
            ("goal.list.terminal", fixture.terminal_goal_id),
            ("goal.show.active", fixture.active_goal_id),
            ("goal.show.terminal", fixture.terminal_goal_id),
            ("goal.summary.active", fixture.active_goal_id),
            ("goal.summary.terminal", fixture.terminal_goal_id),
        )

        for surface, goal_id in checked:
            if surface.startswith("goal.list"):
                project_name = project_names[goal_id]
                result = run_cli(
                    [
                        "goal",
                        "list",
                        "--project",
                        project_name,
                        "--format",
                        "json",
                    ],
                    env,
                    width=120,
                )
                require_success(
                    result,
                    args=[
                        "goal",
                        "list",
                        "--project",
                        project_name,
                        "--format",
                        "json",
                    ],
                )
                payload = json.loads(result.stdout)
                item = _goal_item(payload["items"], goal_id)
                issues.extend(
                    _evaluate_goal_list_item_payload(
                        surface,
                        item,
                        expectations[goal_id],
                        project_id=project_ids[goal_id],
                    )
                )
                continue

            if surface.startswith("goal.show"):
                result = run_cli(
                    ["goal", "show", goal_id, "--format", "json"], env, width=120
                )
                require_success(
                    result, args=["goal", "show", goal_id, "--format", "json"]
                )
                payload = json.loads(result.stdout)
                issues.extend(
                    _evaluate_goal_show_payload(
                        surface,
                        payload,
                        expectations[goal_id],
                        project_id=project_ids[goal_id],
                    )
                )
                continue

            result = run_cli(
                ["goal", "summary", goal_id, "--format", "json"], env, width=120
            )
            require_success(
                result, args=["goal", "summary", goal_id, "--format", "json"]
            )
            payload = json.loads(result.stdout)
            issues.extend(
                _evaluate_goal_summary_payload(
                    surface,
                    payload,
                    expectations[goal_id],
                    project_id=project_ids[goal_id],
                )
            )

        return tuple(issues)
    finally:
        await db.disconnect()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit CLI goal lifecycle aggregate contracts."
    )
    parser.add_argument("--check", action="store_true", help="Exit non-zero on issues.")
    args = parser.parse_args()

    issues = asyncio.run(run_audit())
    print("CLI goal lifecycle contract audit")
    print("checked=6 issues=" + str(len(issues)))
    for issue in issues:
        print(f"- {issue.surface} {issue.reason}")

    if args.check and issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
