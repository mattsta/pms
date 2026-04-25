#!/usr/bin/env python3
"""Audit MCP project tools against the shared lifecycle rollup contract."""

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
from pms.models import ProjectStatus
from pms.services.plan_service import PlanService
from pms.services.project_service import ProjectService
from pms.services.task_service import TaskService
from pms.tools.project_tools import (
    get_dashboard,
    get_project,
    get_project_summary,
    list_projects,
    set_services,
)
from scripts.lifecycle_aggregate_fixture import seed_project_lifecycle_fixture
from scripts.project_lifecycle_contract_utils import (
    ProjectLifecycleExpectation as ProjectPayloadExpectation,
)
from scripts.project_lifecycle_contract_utils import (
    expectation_from_summary,
    project_payload_mismatch_reasons,
)


@dataclass(frozen=True)
class McpProjectLifecycleIssue:
    """One MCP project lifecycle contract failure."""

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


def evaluate_project_payload(
    surface: str,
    payload: dict[str, object],
    expectation: ProjectPayloadExpectation,
) -> tuple[McpProjectLifecycleIssue, ...]:
    """Compare one MCP project payload against the shared lifecycle contract."""
    issues: list[McpProjectLifecycleIssue] = []

    def record(condition: bool, reason: str) -> None:
        if not condition:
            issues.append(McpProjectLifecycleIssue(surface=surface, reason=reason))

    for reason in project_payload_mismatch_reasons(
        payload,
        expectation,
        check_focus_task=True,
    ):
        record(False, reason)
    record(
        payload.get("project_id") == expectation.project_id,
        "project_id alias mismatch",
    )
    record(
        payload.get("project_name") == expectation.project_name,
        "project_name alias mismatch",
    )
    record(isinstance(payload.get("links"), dict), "missing links")
    record(isinstance(payload.get("next_steps"), list), "missing next_steps")

    return tuple(issues)


def _project_item(items: list[dict[str, object]], project_id: str) -> dict[str, object]:
    for item in items:
        if item.get("id") == project_id:
            return item
    raise RuntimeError(f"Project {project_id} not found in payload")


async def _run_audit_async() -> tuple[McpProjectLifecycleIssue, ...]:
    tmp_root = REPO_ROOT / ".tmp"
    tmp_root.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(
        tempfile.mkdtemp(prefix="mcp-project-lifecycle-audit-", dir=tmp_root)
    )
    db = Database(temp_dir / "audit.db")
    await db.connect()
    await initialize_schema(db)

    issues: list[McpProjectLifecycleIssue] = []
    try:
        event_store = EventStore(db)
        revision_store = RevisionStore(db)
        metrics = MetricsCollector(db)

        project_service = ProjectService(db, event_store, revision_store, metrics)
        task_service = TaskService(db, event_store, revision_store, metrics)
        plan_service = PlanService(db, event_store, revision_store, metrics)
        set_services(
            project_service=project_service,
            task_service=task_service,
            plan_service=plan_service,
        )
        fixture = await seed_project_lifecycle_fixture(
            project_service,
            task_service,
            plan_service,
            active_project_name="MCP Lifecycle Active Project",
            active_task_title="MCP Lifecycle Active Task",
            start_active_task=True,
            terminal_project_name="MCP Lifecycle Terminal Project",
            terminal_task_title="MCP Lifecycle Terminal Task",
            terminal_plan_name="MCP Lifecycle Draft Residue Plan",
            terminal_plan_content={"steps": ["planning residue"]},
        )

        active_summary = await project_service.get_project_summary(
            fixture.active_project_id
        )
        terminal_summary = await project_service.get_project_summary(
            fixture.terminal_project_id
        )
        if active_summary is None or terminal_summary is None:
            return (
                McpProjectLifecycleIssue(
                    surface="setup",
                    reason="failed to compute project summaries",
                ),
            )

        active_expectation = expectation_from_summary(
            active_summary,
            focus_task_id=fixture.active_task_id,
        )
        terminal_expectation = expectation_from_summary(
            terminal_summary,
            focus_task_id=None,
        )

        list_payload = _tool_payload(await list_projects.handler({}))
        issues.extend(
            evaluate_project_payload(
                "list_projects.active",
                _project_item(list_payload["items"], fixture.active_project_id),
                ProjectPayloadExpectation(
                    **{**active_expectation.__dict__, "focus_task_id": None}
                ),
            )
        )
        issues.extend(
            evaluate_project_payload(
                "list_projects.terminal",
                _project_item(list_payload["items"], fixture.terminal_project_id),
                ProjectPayloadExpectation(
                    **{**terminal_expectation.__dict__, "focus_task_id": None}
                ),
            )
        )

        active_detail = _tool_payload(
            await get_project.handler({"identifier": fixture.active_project_id})
        )
        issues.extend(
            evaluate_project_payload(
                "get_project.active",
                active_detail,
                active_expectation,
            )
        )

        terminal_detail = _tool_payload(
            await get_project.handler({"identifier": fixture.terminal_project_id})
        )
        issues.extend(
            evaluate_project_payload(
                "get_project.terminal",
                terminal_detail,
                terminal_expectation,
            )
        )

        terminal_summary_payload = _tool_payload(
            await get_project_summary.handler(
                {"identifier": fixture.terminal_project_id}
            )
        )
        issues.extend(
            evaluate_project_payload(
                "get_project_summary.terminal",
                terminal_summary_payload["project"],
                terminal_expectation,
            )
        )

        dashboard_payload = _tool_payload(await get_dashboard.handler({}))
        issues.extend(
            evaluate_project_payload(
                "get_dashboard.active",
                _project_item(
                    dashboard_payload["active_projects"],
                    fixture.active_project_id,
                ),
                ProjectPayloadExpectation(
                    **{**active_expectation.__dict__, "focus_task_id": None}
                ),
            )
        )
        issues.extend(
            evaluate_project_payload(
                "get_dashboard.recently_completed",
                _project_item(
                    dashboard_payload["recently_completed_projects"],
                    fixture.terminal_project_id,
                ),
                ProjectPayloadExpectation(
                    **{**terminal_expectation.__dict__, "focus_task_id": None}
                ),
            )
        )

        await task_service.complete_task(fixture.active_task_id)
        await project_service.update_project(
            fixture.active_project_id,
            status=ProjectStatus.COMPLETED,
        )
        terminal_dashboard_payload = _tool_payload(await get_dashboard.handler({}))
        if terminal_dashboard_payload.get("terminal_reason") != (
            "all surfaced projects are already terminal"
        ):
            issues.append(
                McpProjectLifecycleIssue(
                    surface="get_dashboard.terminal",
                    reason="dashboard terminal_reason mismatch",
                )
            )
    finally:
        await db.disconnect()
        shutil.rmtree(temp_dir, ignore_errors=True)

    return tuple(issues)


def run_audit() -> tuple[McpProjectLifecycleIssue, ...]:
    """Run the MCP project lifecycle contract audit."""
    return asyncio.run(_run_audit_async())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit MCP project lifecycle payloads against shared rollups."
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    issues = run_audit()
    if args.json:
        print(
            json.dumps(
                {
                    "checked": 7,
                    "issues": [
                        {"surface": issue.surface, "reason": issue.reason}
                        for issue in issues
                    ],
                },
                indent=2,
            )
        )
    else:
        print(f"MCP project lifecycle contract audit\nchecked=7 issues={len(issues)}")
        for issue in issues:
            print(f"- {issue.surface}: {issue.reason}")
    if args.check and issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
