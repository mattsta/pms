#!/usr/bin/env python3
"""Audit MCP goal summary surfaces against shared lifecycle rollups."""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.db.connection import Database
from pms.db.schema import initialize_schema
from pms.services.goal_service import GoalService
from pms.services.project_service import ProjectService
from pms.services.task_service import TaskService
from pms.tools.project_tools import get_goal, get_goal_summary, list_goals, set_services
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
class McpGoalLifecycleIssue:
    """One MCP goal lifecycle contract failure."""

    surface: str
    reason: str


def _tool_payload(result: dict[str, object]) -> dict[str, object]:
    content = result.get("content")
    if not isinstance(content, list) or not content:
        raise RuntimeError("Tool returned no content")
    item = content[0]
    if not isinstance(item, dict):
        raise RuntimeError("Tool content item is not a dict")
    return json.loads(str(item["text"]))


def evaluate_goal_summary_payload(
    surface: str,
    payload: dict[str, object],
    expectation: GoalLifecycleExpectation,
    *,
    project_id: str | None,
) -> tuple[McpGoalLifecycleIssue, ...]:
    """Compare one MCP goal summary payload against the shared lifecycle contract."""
    issues: list[McpGoalLifecycleIssue] = []

    def record(condition: bool, reason: str) -> None:
        if not condition:
            issues.append(McpGoalLifecycleIssue(surface=surface, reason=reason))

    for reason in goal_summary_payload_mismatch_reasons(payload, expectation):
        record(False, reason)

    links = payload.get("links")
    record(isinstance(links, dict), "links missing")
    if isinstance(links, dict):
        record(
            links.get("self")
            == {
                "tool": "get_goal_summary",
                "args": {"identifier": expectation.goal_id},
            },
            "self link mismatch",
        )
        record(
            links.get("goal")
            == {"tool": "get_goal", "args": {"identifier": expectation.goal_id}},
            "goal link mismatch",
        )
        record(
            links.get("objectives")
            == {"tool": "list_objectives", "args": {"goal_id": expectation.goal_id}},
            "objectives link mismatch",
        )
        record(
            links.get("plans")
            == {"tool": "list_plans", "args": {"goal_id": expectation.goal_id}},
            "plans link mismatch",
        )
        if project_id is not None:
            record(
                links.get("project")
                == {"tool": "get_project", "args": {"identifier": project_id}},
                "project link mismatch",
            )
            record(
                links.get("tasks")
                == {"tool": "list_tasks", "args": {"project": project_id}},
                "tasks link mismatch",
            )

    next_steps = payload.get("next_steps")
    record(isinstance(next_steps, list) and bool(next_steps), "next_steps missing")
    if isinstance(next_steps, list) and next_steps:
        if expectation.execution_focus_task_id is not None:
            record(
                next_steps[0]
                == f"Use get_task with identifier={expectation.execution_focus_task_id}",
                "focus-task next step mismatch",
            )
        elif expectation.terminal_reason is not None:
            record(
                next_steps[0] == f"Use get_goal with identifier={expectation.goal_id}",
                "terminal next step mismatch",
            )

    return tuple(issues)


def evaluate_goal_list_item_payload(
    surface: str,
    payload: dict[str, object],
    expectation: GoalLifecycleExpectation,
    *,
    project_id: str | None,
) -> tuple[McpGoalLifecycleIssue, ...]:
    """Compare one MCP goal list item against the shared lifecycle contract."""
    issues: list[McpGoalLifecycleIssue] = []

    def record(condition: bool, reason: str) -> None:
        if not condition:
            issues.append(McpGoalLifecycleIssue(surface=surface, reason=reason))

    for reason in goal_list_payload_mismatch_reasons(payload, expectation):
        record(False, reason)

    links = payload.get("links")
    record(isinstance(links, dict), "links missing")
    if isinstance(links, dict):
        record(
            links.get("self")
            == {"tool": "get_goal", "args": {"identifier": expectation.goal_id}},
            "self link mismatch",
        )
        record(
            links.get("summary")
            == {
                "tool": "get_goal_summary",
                "args": {"identifier": expectation.goal_id},
            },
            "summary link mismatch",
        )
        record(
            links.get("objectives")
            == {"tool": "list_objectives", "args": {"goal_id": expectation.goal_id}},
            "objectives link mismatch",
        )
        record(
            links.get("plans")
            == {"tool": "list_plans", "args": {"goal_id": expectation.goal_id}},
            "plans link mismatch",
        )
        if project_id is not None:
            record(
                links.get("project")
                == {"tool": "get_project", "args": {"identifier": project_id}},
                "project link mismatch",
            )
            record(
                links.get("tasks")
                == {"tool": "list_tasks", "args": {"project": project_id}},
                "tasks link mismatch",
            )

    next_steps = payload.get("next_steps")
    record(isinstance(next_steps, list) and bool(next_steps), "next_steps missing")
    if isinstance(next_steps, list) and next_steps:
        if expectation.execution_focus_task_id is not None:
            record(
                next_steps[0]
                == f"Use get_task with identifier={expectation.execution_focus_task_id}",
                "focus-task next step mismatch",
            )
        elif expectation.terminal_reason is not None:
            record(
                next_steps[0] == f"Use get_goal with identifier={expectation.goal_id}",
                "terminal next step mismatch",
            )

    return tuple(issues)


def evaluate_goal_detail_payload(
    surface: str,
    payload: dict[str, object],
    expectation: GoalLifecycleExpectation,
    *,
    project_id: str | None,
) -> tuple[McpGoalLifecycleIssue, ...]:
    """Compare one MCP goal detail payload against the shared lifecycle contract."""
    issues: list[McpGoalLifecycleIssue] = []

    def record(condition: bool, reason: str) -> None:
        if not condition:
            issues.append(McpGoalLifecycleIssue(surface=surface, reason=reason))

    for reason in goal_detail_payload_mismatch_reasons(payload, expectation):
        record(False, reason)

    links = payload.get("links")
    record(isinstance(links, dict), "links missing")
    if isinstance(links, dict):
        record(
            links.get("self")
            == {"tool": "get_goal", "args": {"identifier": expectation.goal_id}},
            "self link mismatch",
        )
        record(
            links.get("summary")
            == {
                "tool": "get_goal_summary",
                "args": {"identifier": expectation.goal_id},
            },
            "summary link mismatch",
        )
        record(
            links.get("objectives")
            == {"tool": "list_objectives", "args": {"goal_id": expectation.goal_id}},
            "objectives link mismatch",
        )
        record(
            links.get("plans")
            == {"tool": "list_plans", "args": {"goal_id": expectation.goal_id}},
            "plans link mismatch",
        )
        if project_id is not None:
            record(
                links.get("project")
                == {"tool": "get_project", "args": {"identifier": project_id}},
                "project link mismatch",
            )
            record(
                links.get("tasks")
                == {"tool": "list_tasks", "args": {"project": project_id}},
                "tasks link mismatch",
            )

    next_steps = payload.get("next_steps")
    record(isinstance(next_steps, list) and bool(next_steps), "next_steps missing")
    if isinstance(next_steps, list) and next_steps:
        if expectation.execution_focus_task_id is not None:
            record(
                next_steps[0]
                == f"Use get_task with identifier={expectation.execution_focus_task_id}",
                "focus-task next step mismatch",
            )
        elif expectation.terminal_reason is not None:
            record(
                next_steps[0] == f"Use get_goal with identifier={expectation.goal_id}",
                "terminal next step mismatch",
            )

    return tuple(issues)


async def run_audit() -> tuple[McpGoalLifecycleIssue, ...]:
    """Seed goals and ensure MCP summary surfaces expose shared lifecycle rollups."""
    tmp_root = REPO_ROOT / ".tmp"
    tmp_root.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix="mcp-goal-lifecycle-audit-", dir=tmp_root))
    db = Database(temp_dir / "audit.db")
    await db.connect()
    await initialize_schema(db)

    issues: list[McpGoalLifecycleIssue] = []
    try:
        event_store = EventStore(db)
        revision_store = RevisionStore(db)
        metrics = MetricsCollector(db)

        project_service = ProjectService(db, event_store, revision_store, metrics)
        task_service = TaskService(db, event_store, revision_store, metrics)
        goal_service = GoalService(db, event_store, revision_store, metrics)
        set_services(
            project_service=project_service,
            task_service=task_service,
            goal_service=goal_service,
        )
        fixture = await seed_goal_lifecycle_fixture(
            project_service,
            goal_service,
            task_service,
            active_project_name="MCP Goal Lifecycle Active Project",
            active_goal_name="MCP Goal Lifecycle Active Goal",
            active_task_title="MCP Goal Lifecycle Active Task",
            active_progress_percent=45,
            active_status_message="Implementing",
            active_updated_by="goal-audit",
            terminal_project_name="MCP Goal Lifecycle Terminal Project",
            terminal_goal_name="MCP Goal Lifecycle Terminal Goal",
            terminal_task_title="MCP Goal Lifecycle Terminal Task",
        )
        expectations, _ = await build_goal_lifecycle_expectations(
            goal_service,
            [fixture.active_goal_id, fixture.terminal_goal_id],
        )

        list_payload = _tool_payload(
            await list_goals.handler(
                {
                    "limit": 50,
                    "offset": 0,
                }
            )
        )
        issues.extend(
            evaluate_goal_list_item_payload(
                "list_goals.active",
                next(
                    item
                    for item in list_payload["items"]
                    if item["id"] == fixture.active_goal_id
                ),
                expectations[fixture.active_goal_id],
                project_id=fixture.active_project_id,
            )
        )
        issues.extend(
            evaluate_goal_list_item_payload(
                "list_goals.terminal",
                next(
                    item
                    for item in list_payload["items"]
                    if item["id"] == fixture.terminal_goal_id
                ),
                expectations[fixture.terminal_goal_id],
                project_id=fixture.terminal_project_id,
            )
        )

        active_detail = _tool_payload(
            await get_goal.handler({"identifier": fixture.active_goal_id})
        )
        issues.extend(
            evaluate_goal_detail_payload(
                "get_goal.active",
                active_detail,
                expectations[fixture.active_goal_id],
                project_id=fixture.active_project_id,
            )
        )

        terminal_detail = _tool_payload(
            await get_goal.handler({"identifier": fixture.terminal_goal_id})
        )
        issues.extend(
            evaluate_goal_detail_payload(
                "get_goal.terminal",
                terminal_detail,
                expectations[fixture.terminal_goal_id],
                project_id=fixture.terminal_project_id,
            )
        )

        active_summary = _tool_payload(
            await get_goal_summary.handler({"identifier": fixture.active_goal_id})
        )
        issues.extend(
            evaluate_goal_summary_payload(
                "get_goal_summary.active",
                active_summary,
                expectations[fixture.active_goal_id],
                project_id=fixture.active_project_id,
            )
        )

        terminal_summary = _tool_payload(
            await get_goal_summary.handler({"identifier": fixture.terminal_goal_id})
        )
        issues.extend(
            evaluate_goal_summary_payload(
                "get_goal_summary.terminal",
                terminal_summary,
                expectations[fixture.terminal_goal_id],
                project_id=fixture.terminal_project_id,
            )
        )
    finally:
        await db.disconnect()
        shutil.rmtree(temp_dir, ignore_errors=True)

    return tuple(issues)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit MCP goal summary payloads against shared lifecycle rollups."
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    issues = asyncio.run(run_audit())
    checked = 6
    if args.json:
        print(
            json.dumps(
                {
                    "checked": checked,
                    "issues": [
                        {"surface": issue.surface, "reason": issue.reason}
                        for issue in issues
                    ],
                },
                indent=2,
            )
        )
    else:
        print(
            f"MCP goal lifecycle contract audit\nchecked={checked} issues={len(issues)}"
        )
        for issue in issues:
            print(f"- {issue.surface}: {issue.reason}")
    if args.check and issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
