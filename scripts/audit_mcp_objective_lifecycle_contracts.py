#!/usr/bin/env python3
"""Audit MCP objective lifecycle surfaces against shared lifecycle rollups."""

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
from pms.tools.project_tools import get_objective, list_objectives, set_services
from scripts.lifecycle_aggregate_fixture import (
    build_objective_lifecycle_expectations,
    seed_objective_lifecycle_fixture,
)
from scripts.objective_lifecycle_contract_utils import (
    ObjectiveLifecycleExpectation,
    objective_detail_payload_mismatch_reasons,
    objective_list_payload_mismatch_reasons,
)


@dataclass(frozen=True)
class McpObjectiveLifecycleIssue:
    """One MCP objective lifecycle contract failure."""

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


def evaluate_objective_list_item_payload(
    surface: str,
    payload: dict[str, object],
    expectation: ObjectiveLifecycleExpectation,
    *,
    project_id: str | None,
) -> tuple[McpObjectiveLifecycleIssue, ...]:
    """Compare one MCP objective list item against the shared lifecycle contract."""
    issues: list[McpObjectiveLifecycleIssue] = []

    def record(condition: bool, reason: str) -> None:
        if not condition:
            issues.append(McpObjectiveLifecycleIssue(surface=surface, reason=reason))

    for reason in objective_list_payload_mismatch_reasons(payload, expectation):
        record(False, reason)

    links = payload.get("links")
    record(isinstance(links, dict), "links missing")
    if isinstance(links, dict):
        record(
            links.get("self")
            == {
                "tool": "get_objective",
                "args": {"objective_id": expectation.objective_id},
            },
            "self link mismatch",
        )
        record(
            links.get("goal")
            == {"tool": "get_goal", "args": {"identifier": expectation.goal_id}},
            "goal link mismatch",
        )
        record(
            links.get("goal_summary")
            == {
                "tool": "get_goal_summary",
                "args": {"identifier": expectation.goal_id},
            },
            "goal_summary link mismatch",
        )
        record(
            links.get("key_results")
            == {
                "tool": "list_key_results",
                "args": {"objective_id": expectation.objective_id},
            },
            "key_results link mismatch",
        )
        if project_id is not None:
            record(
                links.get("project")
                == {"tool": "get_project", "args": {"identifier": project_id}},
                "project link mismatch",
            )

    next_steps = payload.get("next_steps")
    record(isinstance(next_steps, list) and bool(next_steps), "next_steps missing")
    if isinstance(next_steps, list) and next_steps:
        record(
            next_steps[0]
            == f"Use get_objective with objective_id={expectation.objective_id}",
            "detail next step mismatch",
        )
        record(
            f"Use list_key_results with objective_id={expectation.objective_id}"
            in next_steps,
            "key_results next step mismatch",
        )
        record(
            f"Use get_goal with identifier={expectation.goal_id}" in next_steps,
            "goal next step mismatch",
        )
        record(
            f"Use get_goal_summary with identifier={expectation.goal_id}" in next_steps,
            "goal_summary next step mismatch",
        )
        if project_id is not None:
            record(
                f"Use get_project with identifier={project_id}" in next_steps,
                "project next step mismatch",
            )
        if expectation.terminal_reason is None:
            record(
                f"Use update_objective with objective_id={expectation.objective_id}"
                in next_steps,
                "update_objective next step mismatch",
            )
        else:
            record(
                (
                    f"Use list_objectives with goal_id={expectation.goal_id} "
                    "status=completed"
                )
                in next_steps,
                "completed objective list next step mismatch",
            )

    return tuple(issues)


def evaluate_objective_detail_payload(
    surface: str,
    payload: dict[str, object],
    expectation: ObjectiveLifecycleExpectation,
    *,
    project_id: str | None,
) -> tuple[McpObjectiveLifecycleIssue, ...]:
    """Compare one MCP objective detail payload against the shared lifecycle contract."""
    issues: list[McpObjectiveLifecycleIssue] = []

    def record(condition: bool, reason: str) -> None:
        if not condition:
            issues.append(McpObjectiveLifecycleIssue(surface=surface, reason=reason))

    for reason in objective_detail_payload_mismatch_reasons(payload, expectation):
        record(False, reason)

    links = payload.get("links")
    record(isinstance(links, dict), "links missing")
    if isinstance(links, dict):
        record(
            links.get("self")
            == {
                "tool": "get_objective",
                "args": {"objective_id": expectation.objective_id},
            },
            "self link mismatch",
        )
        record(
            links.get("goal")
            == {"tool": "get_goal", "args": {"identifier": expectation.goal_id}},
            "goal link mismatch",
        )
        record(
            links.get("goal_summary")
            == {
                "tool": "get_goal_summary",
                "args": {"identifier": expectation.goal_id},
            },
            "goal_summary link mismatch",
        )
        record(
            links.get("key_results")
            == {
                "tool": "list_key_results",
                "args": {"objective_id": expectation.objective_id},
            },
            "key_results link mismatch",
        )
        if project_id is not None:
            record(
                links.get("project")
                == {"tool": "get_project", "args": {"identifier": project_id}},
                "project link mismatch",
            )

    next_steps = payload.get("next_steps")
    record(isinstance(next_steps, list) and bool(next_steps), "next_steps missing")
    if isinstance(next_steps, list) and next_steps:
        record(
            next_steps[0]
            == f"Use get_objective with objective_id={expectation.objective_id}",
            "detail next step mismatch",
        )

    return tuple(issues)


async def run_audit() -> tuple[McpObjectiveLifecycleIssue, ...]:
    """Seed objectives and ensure MCP detail/list surfaces expose lifecycle rollups."""
    tmp_root = REPO_ROOT / ".tmp"
    tmp_root.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(
        tempfile.mkdtemp(prefix="mcp-objective-lifecycle-audit-", dir=tmp_root)
    )
    db = Database(temp_dir / "audit.db")
    await db.connect()
    await initialize_schema(db)

    issues: list[McpObjectiveLifecycleIssue] = []
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

        fixture = await seed_objective_lifecycle_fixture(
            project_service,
            goal_service,
            active_project_name="MCP Objective Lifecycle Active Project",
            active_goal_name="MCP Objective Lifecycle Active Goal",
            active_objective_name="MCP Objective Lifecycle Active Objective",
            active_key_result_a_name="MCP Objective Lifecycle KR A",
            active_key_result_b_name="MCP Objective Lifecycle KR B",
            terminal_project_name="MCP Objective Lifecycle Terminal Project",
            terminal_goal_name="MCP Objective Lifecycle Terminal Goal",
            terminal_objective_name="MCP Objective Lifecycle Terminal Objective",
            terminal_key_result_name="MCP Objective Lifecycle Terminal KR",
        )
        expectations = await build_objective_lifecycle_expectations(
            goal_service,
            [fixture.active_objective_id, fixture.terminal_objective_id],
        )
        active_expectation = expectations[fixture.active_objective_id]
        terminal_expectation = expectations[fixture.terminal_objective_id]

        active_list_payload = _tool_payload(
            await list_objectives.handler(
                {"goal_id": fixture.active_goal_id, "limit": 50, "offset": 0}
            )
        )
        issues.extend(
            evaluate_objective_list_item_payload(
                "list_objectives.active",
                active_list_payload["items"][0],
                active_expectation,
                project_id=fixture.active_project_id,
            )
        )

        terminal_list_payload = _tool_payload(
            await list_objectives.handler(
                {"goal_id": fixture.terminal_goal_id, "limit": 50, "offset": 0}
            )
        )
        issues.extend(
            evaluate_objective_list_item_payload(
                "list_objectives.terminal",
                terminal_list_payload["items"][0],
                terminal_expectation,
                project_id=fixture.terminal_project_id,
            )
        )

        active_detail = _tool_payload(
            await get_objective.handler({"objective_id": fixture.active_objective_id})
        )
        issues.extend(
            evaluate_objective_detail_payload(
                "get_objective.active",
                active_detail,
                active_expectation,
                project_id=fixture.active_project_id,
            )
        )

        terminal_detail = _tool_payload(
            await get_objective.handler({"objective_id": fixture.terminal_objective_id})
        )
        issues.extend(
            evaluate_objective_detail_payload(
                "get_objective.terminal",
                terminal_detail,
                terminal_expectation,
                project_id=fixture.terminal_project_id,
            )
        )
    finally:
        await db.disconnect()
        shutil.rmtree(temp_dir, ignore_errors=True)

    return tuple(issues)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit MCP objective lifecycle payloads against shared lifecycle rollups."
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    issues = asyncio.run(run_audit())
    checked = 4
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
            "MCP objective lifecycle contract audit\n"
            f"checked={checked} issues={len(issues)}"
        )
        for issue in issues:
            print(f"- {issue.surface}: {issue.reason}")
    if args.check and issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
