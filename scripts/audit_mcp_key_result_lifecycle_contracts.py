#!/usr/bin/env python3
"""Audit MCP key-result lifecycle surfaces against shared lifecycle rollups."""

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
from pms.tools.project_tools import get_key_result, list_key_results, set_services
from scripts.key_result_lifecycle_contract_utils import (
    KeyResultLifecycleExpectation,
    key_result_detail_payload_mismatch_reasons,
    key_result_list_payload_mismatch_reasons,
)
from scripts.lifecycle_aggregate_fixture import (
    build_key_result_lifecycle_expectations,
    seed_key_result_lifecycle_fixture,
)


@dataclass(frozen=True)
class McpKeyResultLifecycleIssue:
    """One MCP key-result lifecycle contract failure."""

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


def _record(
    issues: list[McpKeyResultLifecycleIssue],
    *,
    surface: str,
    reason: str,
) -> None:
    issues.append(McpKeyResultLifecycleIssue(surface=surface, reason=reason))


def _evaluate_key_result_list_payload(
    surface: str,
    payload: dict[str, object],
    expectation: KeyResultLifecycleExpectation,
) -> tuple[McpKeyResultLifecycleIssue, ...]:
    issues: list[McpKeyResultLifecycleIssue] = []
    for reason in key_result_list_payload_mismatch_reasons(payload, expectation):
        _record(issues, surface=surface, reason=reason)

    links = payload.get("links")
    if not isinstance(links, dict):
        _record(issues, surface=surface, reason="links missing")
    else:
        if links.get("self") != {
            "tool": "get_key_result",
            "args": {"key_result_id": expectation.key_result_id},
        }:
            _record(issues, surface=surface, reason="self link mismatch")
        if links.get("objective") != {
            "tool": "get_objective",
            "args": {"objective_id": expectation.objective_id},
        }:
            _record(issues, surface=surface, reason="objective link mismatch")
        if links.get("key_results") != {
            "tool": "list_key_results",
            "args": {"objective_id": expectation.objective_id},
        }:
            _record(issues, surface=surface, reason="key_results link mismatch")
        if links.get("goal") != {
            "tool": "get_goal",
            "args": {"identifier": expectation.goal_id},
        }:
            _record(issues, surface=surface, reason="goal link mismatch")
        if links.get("goal_summary") != {
            "tool": "get_goal_summary",
            "args": {"identifier": expectation.goal_id},
        }:
            _record(issues, surface=surface, reason="goal_summary link mismatch")
        if expectation.project_id is not None and (
            links.get("project")
            != {"tool": "get_project", "args": {"identifier": expectation.project_id}}
        ):
            _record(issues, surface=surface, reason="project link mismatch")

    next_steps = payload.get("next_steps")
    if not isinstance(next_steps, list) or not next_steps:
        _record(issues, surface=surface, reason="next_steps missing")
    else:
        if next_steps[0] != (
            f"Use get_key_result with key_result_id={expectation.key_result_id}"
        ):
            _record(issues, surface=surface, reason="detail next_step mismatch")
        if (
            f"Use get_objective with objective_id={expectation.objective_id}"
            not in next_steps
        ):
            _record(issues, surface=surface, reason="objective next_step mismatch")
        if (
            f"Use list_key_results with objective_id={expectation.objective_id}"
            not in next_steps
        ):
            _record(issues, surface=surface, reason="key_results next_step mismatch")
        if f"Use get_goal with identifier={expectation.goal_id}" not in next_steps:
            _record(issues, surface=surface, reason="goal next_step mismatch")
        if (
            f"Use get_goal_summary with identifier={expectation.goal_id}"
            not in next_steps
        ):
            _record(issues, surface=surface, reason="goal_summary next_step mismatch")
        if expectation.project_id is not None and (
            f"Use get_project with identifier={expectation.project_id}"
            not in next_steps
        ):
            _record(issues, surface=surface, reason="project next_step mismatch")
        if expectation.terminal_reason is None:
            if (
                f"Use update_key_result with key_result_id={expectation.key_result_id}"
                not in next_steps
            ):
                _record(issues, surface=surface, reason="update next_step mismatch")
        else:
            if (
                "Use list_key_results with objective_id="
                f"{expectation.objective_id} status=completed"
            ) not in next_steps:
                _record(
                    issues,
                    surface=surface,
                    reason="completed key_results next_step mismatch",
                )

    return tuple(issues)


def _evaluate_key_result_detail_payload(
    surface: str,
    payload: dict[str, object],
    expectation: KeyResultLifecycleExpectation,
) -> tuple[McpKeyResultLifecycleIssue, ...]:
    issues: list[McpKeyResultLifecycleIssue] = []
    for reason in key_result_detail_payload_mismatch_reasons(payload, expectation):
        _record(issues, surface=surface, reason=reason)

    links = payload.get("links")
    if not isinstance(links, dict):
        _record(issues, surface=surface, reason="links missing")
    else:
        if links.get("self") != {
            "tool": "get_key_result",
            "args": {"key_result_id": expectation.key_result_id},
        }:
            _record(issues, surface=surface, reason="self link mismatch")
        if links.get("objective") != {
            "tool": "get_objective",
            "args": {"objective_id": expectation.objective_id},
        }:
            _record(issues, surface=surface, reason="objective link mismatch")
        if links.get("key_results") != {
            "tool": "list_key_results",
            "args": {"objective_id": expectation.objective_id},
        }:
            _record(issues, surface=surface, reason="key_results link mismatch")
        if links.get("goal") != {
            "tool": "get_goal",
            "args": {"identifier": expectation.goal_id},
        }:
            _record(issues, surface=surface, reason="goal link mismatch")
        if links.get("goal_summary") != {
            "tool": "get_goal_summary",
            "args": {"identifier": expectation.goal_id},
        }:
            _record(issues, surface=surface, reason="goal_summary link mismatch")
        if expectation.project_id is not None and (
            links.get("project")
            != {"tool": "get_project", "args": {"identifier": expectation.project_id}}
        ):
            _record(issues, surface=surface, reason="project link mismatch")

    next_steps = payload.get("next_steps")
    if not isinstance(next_steps, list) or not next_steps:
        _record(issues, surface=surface, reason="next_steps missing")
    elif next_steps[0] != (
        f"Use get_key_result with key_result_id={expectation.key_result_id}"
    ):
        _record(issues, surface=surface, reason="detail next_step mismatch")

    return tuple(issues)


async def run_audit() -> tuple[McpKeyResultLifecycleIssue, ...]:
    """Seed key results and ensure MCP detail/list surfaces expose lifecycle rollups."""
    tmp_root = REPO_ROOT / ".tmp"
    tmp_root.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(
        tempfile.mkdtemp(prefix="mcp-key-result-lifecycle-audit-", dir=tmp_root)
    )
    db = Database(temp_dir / "audit.db")
    await db.connect()
    await initialize_schema(db)

    issues: list[McpKeyResultLifecycleIssue] = []
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

        fixture = await seed_key_result_lifecycle_fixture(
            project_service,
            goal_service,
            active_project_name="MCP Key Result Lifecycle Active Project",
            active_goal_name="MCP Key Result Lifecycle Active Goal",
            active_objective_name="MCP Key Result Lifecycle Active Objective",
            active_key_result_name="MCP Key Result Lifecycle Active KR",
            terminal_project_name="MCP Key Result Lifecycle Terminal Project",
            terminal_goal_name="MCP Key Result Lifecycle Terminal Goal",
            terminal_objective_name="MCP Key Result Lifecycle Terminal Objective",
            terminal_key_result_name="MCP Key Result Lifecycle Terminal KR",
        )
        expectations = await build_key_result_lifecycle_expectations(
            goal_service,
            [fixture.active_key_result_id, fixture.terminal_key_result_id],
        )

        active_list_payload = _tool_payload(
            await list_key_results.handler(
                {"objective_id": fixture.active_objective_id, "limit": 50, "offset": 0}
            )
        )
        issues.extend(
            _evaluate_key_result_list_payload(
                "list_key_results.active",
                active_list_payload["items"][0],
                expectations[fixture.active_key_result_id],
            )
        )

        terminal_list_payload = _tool_payload(
            await list_key_results.handler(
                {
                    "objective_id": fixture.terminal_objective_id,
                    "limit": 50,
                    "offset": 0,
                }
            )
        )
        issues.extend(
            _evaluate_key_result_list_payload(
                "list_key_results.terminal",
                terminal_list_payload["items"][0],
                expectations[fixture.terminal_key_result_id],
            )
        )

        active_detail = _tool_payload(
            await get_key_result.handler(
                {"key_result_id": fixture.active_key_result_id}
            )
        )
        issues.extend(
            _evaluate_key_result_detail_payload(
                "get_key_result.active",
                active_detail,
                expectations[fixture.active_key_result_id],
            )
        )

        terminal_detail = _tool_payload(
            await get_key_result.handler(
                {"key_result_id": fixture.terminal_key_result_id}
            )
        )
        issues.extend(
            _evaluate_key_result_detail_payload(
                "get_key_result.terminal",
                terminal_detail,
                expectations[fixture.terminal_key_result_id],
            )
        )
    finally:
        await db.disconnect()
        shutil.rmtree(temp_dir, ignore_errors=True)

    return tuple(issues)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit MCP key-result lifecycle payloads against shared lifecycle rollups."
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
            "MCP key result lifecycle contract audit\n"
            f"checked={checked} issues={len(issues)}"
        )
        for issue in issues:
            print(f"- {issue.surface}: {issue.reason}")
    if args.check and issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
