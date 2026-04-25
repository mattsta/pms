#!/usr/bin/env python3
"""Audit shared project lifecycle truth across CLI, API, and MCP surfaces."""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from httpx import ASGITransport, AsyncClient

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from pms.api.app import app
from pms.api.dependencies import init_services
from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.db.connection import Database
from pms.db.schema import initialize_schema
from pms.models import ProjectStatus
from pms.repositories.api_key_repository import ApiKeyRepository
from pms.services.auth_service import AuthService
from pms.services.comment_service import CommentService
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
from scripts.cli_surface_audit_utils import require_success, run_cli, with_temp_env
from scripts.lifecycle_aggregate_fixture import seed_project_lifecycle_fixture
from scripts.project_lifecycle_contract_utils import (
    ProjectLifecycleExpectation,
    expectation_from_summary,
    project_payload_mismatch_reasons,
)


@dataclass(frozen=True)
class CrossSurfaceProjectLifecycleIssue:
    """One cross-surface lifecycle contract failure."""

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


def _project_item(items: list[dict[str, object]], project_id: str) -> dict[str, object]:
    for item in items:
        if item.get("id") == project_id or item.get("project_id") == project_id:
            return item
    raise RuntimeError(f"Project {project_id} not found in payload")


def _record(
    issues: list[CrossSurfaceProjectLifecycleIssue],
    *,
    surface: str,
    reason: str,
) -> None:
    issues.append(CrossSurfaceProjectLifecycleIssue(surface=surface, reason=reason))


def _evaluate_project_payload(
    surface: str,
    payload: dict[str, object],
    expectation: ProjectLifecycleExpectation,
    *,
    issues: list[CrossSurfaceProjectLifecycleIssue],
    check_focus_task: bool = False,
    require_links: bool = False,
    require_next_steps: bool = False,
) -> None:
    for reason in project_payload_mismatch_reasons(
        payload,
        expectation,
        check_focus_task=check_focus_task,
    ):
        _record(issues, surface=surface, reason=reason)
    if "project_id" in payload and payload.get("project_id") != expectation.project_id:
        _record(issues, surface=surface, reason="project_id alias mismatch")
    if (
        "project_name" in payload
        and payload.get("project_name") != expectation.project_name
    ):
        _record(issues, surface=surface, reason="project_name alias mismatch")
    if require_links and not isinstance(payload.get("links"), dict):
        _record(issues, surface=surface, reason="missing links")
    if require_next_steps:
        next_steps = payload.get("next_steps")
        if not isinstance(next_steps, list) or not next_steps:
            _record(issues, surface=surface, reason="missing next_steps")


async def _make_api_client(db: Database) -> AsyncClient:
    repo = ApiKeyRepository(db)
    service = AuthService(repo)
    api_key, _ = await service.create_api_key(
        name="Cross-surface lifecycle audit admin",
        scopes=["*"],
        expires_in_days=None,
        rate_limit=None,
    )
    app.state.db = db
    app.state.start_time = time.time()
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-API-Key": api_key},
    )


async def _run_audit_async() -> tuple[CrossSurfaceProjectLifecycleIssue, ...]:
    env = with_temp_env("cross-surface-project-lifecycle-")
    temp_dir = Path(env["PMS_DATA_DIR"])
    issues: list[CrossSurfaceProjectLifecycleIssue] = []

    init_result = run_cli(["init"], env, width=160)
    require_success(init_result, args=["init"])

    db = Database(Path(env["PMS_DATABASE_PATH"]))
    await db.connect()
    await initialize_schema(db)
    await init_services(db)

    api_client: AsyncClient | None = None
    try:
        event_store = EventStore(db)
        revision_store = RevisionStore(db)
        metrics = MetricsCollector(db)
        project_service = ProjectService(db, event_store, revision_store, metrics)
        task_service = TaskService(db, event_store, revision_store, metrics)
        plan_service = PlanService(db, event_store, revision_store, metrics)
        comment_service = CommentService(db, metrics)
        set_services(
            project_service=project_service,
            task_service=task_service,
            plan_service=plan_service,
        )
        api_client = await _make_api_client(db)
        graph = await seed_project_lifecycle_fixture(
            project_service,
            task_service,
            plan_service,
            active_project_name="Cross Surface Active Project",
            active_task_title="Cross Surface Active Task",
            start_active_task=False,
            active_progress_percent=40,
            active_status_message="Active execution progress",
            active_updated_by="cross-surface-audit",
            terminal_project_name="Cross Surface Terminal Project",
            terminal_task_title="Cross Surface Terminal Task",
            terminal_plan_name="Cross Surface Draft Residue Plan",
            terminal_plan_content={"steps": ["planning residue only"]},
            comment_service=comment_service,
            terminal_comment_body="Fresh terminal activity after project completion",
            terminal_comment_author="cross-surface-audit",
        )

        active_summary = await project_service.get_project_summary(
            graph.active_project_id
        )
        terminal_summary = await project_service.get_project_summary(
            graph.terminal_project_id
        )
        if active_summary is None or terminal_summary is None:
            return (
                CrossSurfaceProjectLifecycleIssue(
                    surface="setup",
                    reason="failed to compute seeded project summaries",
                ),
            )

        active_expectation = expectation_from_summary(
            active_summary,
            focus_task_id=graph.active_task_id,
        )
        terminal_expectation = expectation_from_summary(
            terminal_summary,
            focus_task_id=None,
        )

        cli_list = json.loads(
            run_cli(["project", "list", "--format", "json"], env, width=160).stdout
        )
        _evaluate_project_payload(
            "cli.project_list.active",
            _project_item(cli_list["items"], graph.active_project_id),
            active_expectation,
            issues=issues,
            require_links=True,
        )
        _evaluate_project_payload(
            "cli.project_list.terminal",
            _project_item(cli_list["items"], graph.terminal_project_id),
            terminal_expectation,
            issues=issues,
            require_links=True,
        )

        cli_show_active = json.loads(
            run_cli(
                ["project", "show", graph.active_project_id, "--format", "json"],
                env,
                width=160,
            ).stdout
        )
        _evaluate_project_payload(
            "cli.project_show.active",
            cli_show_active,
            active_expectation,
            issues=issues,
            check_focus_task=True,
            require_links=True,
            require_next_steps=True,
        )
        cli_show_terminal = json.loads(
            run_cli(
                ["project", "show", graph.terminal_project_id, "--format", "json"],
                env,
                width=160,
            ).stdout
        )
        _evaluate_project_payload(
            "cli.project_show.terminal",
            cli_show_terminal,
            terminal_expectation,
            issues=issues,
            check_focus_task=True,
            require_links=True,
            require_next_steps=True,
        )

        cli_summary_active = json.loads(
            run_cli(
                ["project", "summary", graph.active_project_id, "--format", "json"],
                env,
                width=160,
            ).stdout
        )
        _evaluate_project_payload(
            "cli.project_summary.active",
            cli_summary_active["project"],
            active_expectation,
            issues=issues,
            check_focus_task=True,
            require_links=True,
            require_next_steps=True,
        )
        cli_summary_terminal = json.loads(
            run_cli(
                ["project", "summary", graph.terminal_project_id, "--format", "json"],
                env,
                width=160,
            ).stdout
        )
        _evaluate_project_payload(
            "cli.project_summary.terminal",
            cli_summary_terminal["project"],
            terminal_expectation,
            issues=issues,
            check_focus_task=True,
            require_links=True,
            require_next_steps=True,
        )

        cli_dashboard = json.loads(
            run_cli(["dashboard", "--format", "json"], env, width=160).stdout
        )
        _evaluate_project_payload(
            "cli.dashboard.active",
            _project_item(cli_dashboard["active_projects"], graph.active_project_id),
            active_expectation,
            issues=issues,
            require_links=True,
        )
        _evaluate_project_payload(
            "cli.dashboard.recently_completed",
            _project_item(
                cli_dashboard["recently_completed_projects"],
                graph.terminal_project_id,
            ),
            terminal_expectation,
            issues=issues,
            require_links=True,
        )
        if cli_dashboard.get("focus_task", {}).get("id") != graph.active_task_id:
            _record(
                issues,
                surface="cli.dashboard",
                reason="dashboard focus_task id mismatch",
            )

        api_list = await api_client.get("/api/v1/projects")
        api_list.raise_for_status()
        api_list_payload = api_list.json()
        _evaluate_project_payload(
            "api.projects_list.active",
            _project_item(api_list_payload["items"], graph.active_project_id),
            active_expectation,
            issues=issues,
            require_links=True,
            require_next_steps=True,
        )
        _evaluate_project_payload(
            "api.projects_list.terminal",
            _project_item(api_list_payload["items"], graph.terminal_project_id),
            terminal_expectation,
            issues=issues,
            require_links=True,
            require_next_steps=True,
        )

        api_active_detail = await api_client.get(
            f"/api/v1/projects/{graph.active_project_id}"
        )
        api_active_detail.raise_for_status()
        _evaluate_project_payload(
            "api.project_detail.active",
            api_active_detail.json(),
            active_expectation,
            issues=issues,
            check_focus_task=True,
            require_links=True,
            require_next_steps=True,
        )
        api_terminal_detail = await api_client.get(
            f"/api/v1/projects/{graph.terminal_project_id}"
        )
        api_terminal_detail.raise_for_status()
        _evaluate_project_payload(
            "api.project_detail.terminal",
            api_terminal_detail.json(),
            terminal_expectation,
            issues=issues,
            check_focus_task=True,
            require_links=True,
            require_next_steps=True,
        )

        api_active_summary = await api_client.get(
            f"/api/v1/projects/{graph.active_project_id}/summary"
        )
        api_active_summary.raise_for_status()
        _evaluate_project_payload(
            "api.project_summary.active",
            api_active_summary.json()["project"],
            active_expectation,
            issues=issues,
            check_focus_task=True,
            require_links=True,
            require_next_steps=True,
        )
        api_terminal_summary = await api_client.get(
            f"/api/v1/projects/{graph.terminal_project_id}/summary"
        )
        api_terminal_summary.raise_for_status()
        _evaluate_project_payload(
            "api.project_summary.terminal",
            api_terminal_summary.json()["project"],
            terminal_expectation,
            issues=issues,
            check_focus_task=True,
            require_links=True,
            require_next_steps=True,
        )

        api_active_overview = await api_client.get(
            f"/api/v1/projects/{graph.active_project_id}/operator-overview"
        )
        api_active_overview.raise_for_status()
        api_active_overview_payload = api_active_overview.json()
        _evaluate_project_payload(
            "api.project_operator_overview.active",
            api_active_overview_payload["project"],
            active_expectation,
            issues=issues,
            check_focus_task=True,
            require_links=True,
            require_next_steps=True,
        )
        if (
            api_active_overview_payload.get("focus_task", {}).get("id")
            != graph.active_task_id
        ):
            _record(
                issues,
                surface="api.project_operator_overview.active",
                reason="top-level focus_task id mismatch",
            )

        api_terminal_overview = await api_client.get(
            f"/api/v1/projects/{graph.terminal_project_id}/operator-overview"
        )
        api_terminal_overview.raise_for_status()
        api_terminal_overview_payload = api_terminal_overview.json()
        _evaluate_project_payload(
            "api.project_operator_overview.terminal",
            api_terminal_overview_payload["project"],
            terminal_expectation,
            issues=issues,
            check_focus_task=True,
            require_links=True,
            require_next_steps=True,
        )
        if api_terminal_overview_payload.get("focus_task") is not None:
            _record(
                issues,
                surface="api.project_operator_overview.terminal",
                reason="top-level focus_task should be absent",
            )

        mcp_list = _tool_payload(await list_projects.handler({}))
        _evaluate_project_payload(
            "mcp.list_projects.active",
            _project_item(mcp_list["items"], graph.active_project_id),
            active_expectation,
            issues=issues,
            require_links=True,
            require_next_steps=True,
        )
        _evaluate_project_payload(
            "mcp.list_projects.terminal",
            _project_item(mcp_list["items"], graph.terminal_project_id),
            terminal_expectation,
            issues=issues,
            require_links=True,
            require_next_steps=True,
        )

        mcp_active_detail = _tool_payload(
            await get_project.handler({"identifier": graph.active_project_id})
        )
        _evaluate_project_payload(
            "mcp.get_project.active",
            mcp_active_detail,
            active_expectation,
            issues=issues,
            check_focus_task=True,
            require_links=True,
            require_next_steps=True,
        )
        mcp_terminal_detail = _tool_payload(
            await get_project.handler({"identifier": graph.terminal_project_id})
        )
        _evaluate_project_payload(
            "mcp.get_project.terminal",
            mcp_terminal_detail,
            terminal_expectation,
            issues=issues,
            check_focus_task=True,
            require_links=True,
            require_next_steps=True,
        )

        mcp_active_summary = _tool_payload(
            await get_project_summary.handler({"identifier": graph.active_project_id})
        )
        _evaluate_project_payload(
            "mcp.get_project_summary.active",
            mcp_active_summary["project"],
            active_expectation,
            issues=issues,
            check_focus_task=True,
            require_links=True,
            require_next_steps=True,
        )
        mcp_terminal_summary = _tool_payload(
            await get_project_summary.handler({"identifier": graph.terminal_project_id})
        )
        _evaluate_project_payload(
            "mcp.get_project_summary.terminal",
            mcp_terminal_summary["project"],
            terminal_expectation,
            issues=issues,
            check_focus_task=True,
            require_links=True,
            require_next_steps=True,
        )

        mcp_dashboard = _tool_payload(await get_dashboard.handler({}))
        _evaluate_project_payload(
            "mcp.get_dashboard.active",
            _project_item(mcp_dashboard["active_projects"], graph.active_project_id),
            active_expectation,
            issues=issues,
            require_links=True,
            require_next_steps=True,
        )
        _evaluate_project_payload(
            "mcp.get_dashboard.recently_completed",
            _project_item(
                mcp_dashboard["recently_completed_projects"],
                graph.terminal_project_id,
            ),
            terminal_expectation,
            issues=issues,
            require_links=True,
            require_next_steps=True,
        )

        await task_service.complete_task(graph.active_task_id)
        await project_service.update_project(
            graph.active_project_id,
            status=ProjectStatus.COMPLETED,
        )

        cli_terminal_dashboard = json.loads(
            run_cli(["dashboard", "--format", "json"], env, width=160).stdout
        )
        if cli_terminal_dashboard.get("terminal_reason") != (
            "all surfaced projects are already terminal"
        ):
            _record(
                issues,
                surface="cli.dashboard.terminal",
                reason="dashboard terminal_reason mismatch",
            )

        mcp_terminal_dashboard = _tool_payload(await get_dashboard.handler({}))
        if mcp_terminal_dashboard.get("terminal_reason") != (
            "all surfaced projects are already terminal"
        ):
            _record(
                issues,
                surface="mcp.get_dashboard.terminal",
                reason="dashboard terminal_reason mismatch",
            )
    finally:
        if api_client is not None:
            await api_client.aclose()
        await db.disconnect()
        shutil.rmtree(temp_dir, ignore_errors=True)

    return tuple(issues)


def run_audit() -> tuple[CrossSurfaceProjectLifecycleIssue, ...]:
    """Run the cross-surface project lifecycle contract audit."""
    return asyncio.run(_run_audit_async())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit shared project lifecycle truth across CLI, API, and MCP."
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    issues = run_audit()
    if args.json:
        print(
            json.dumps(
                {
                    "checked": 20,
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
            "Cross-surface project lifecycle contract audit\n"
            f"checked=20 issues={len(issues)}"
        )
        for issue in issues:
            print(f"- {issue.surface}: {issue.reason}")
    if args.check and issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
