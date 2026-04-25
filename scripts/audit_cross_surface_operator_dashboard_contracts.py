#!/usr/bin/env python3
"""Audit aggregate operator dashboard parity across CLI, API, and MCP surfaces."""

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
from pms.models import PlanFormat, PlanStatus, ProjectStatus
from pms.repositories.api_key_repository import ApiKeyRepository
from pms.services.auth_service import AuthService
from pms.services.comment_service import CommentService
from pms.services.plan_service import PlanService
from pms.services.project_service import ProjectService
from pms.services.task_service import TaskService
from pms.tools.project_tools import get_dashboard, set_services
from scripts.cli_surface_audit_utils import require_success, run_cli, with_temp_env
from scripts.project_lifecycle_contract_utils import (
    ProjectLifecycleExpectation,
    expectation_from_summary,
    project_payload_mismatch_reasons,
)


@dataclass(frozen=True)
class AggregateDashboardIssue:
    """One aggregate dashboard parity failure."""

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
    issues: list[AggregateDashboardIssue],
    *,
    surface: str,
    reason: str,
) -> None:
    issues.append(AggregateDashboardIssue(surface=surface, reason=reason))


def _evaluate_project_payload(
    surface: str,
    payload: dict[str, object],
    expectation: ProjectLifecycleExpectation,
    *,
    issues: list[AggregateDashboardIssue],
    require_links: bool = True,
) -> None:
    for reason in project_payload_mismatch_reasons(
        payload,
        expectation,
        check_focus_task=False,
    ):
        _record(issues, surface=surface, reason=reason)
    if require_links and not isinstance(payload.get("links"), dict):
        _record(issues, surface=surface, reason="missing links")


async def _make_api_client(db: Database) -> AsyncClient:
    repo = ApiKeyRepository(db)
    service = AuthService(repo)
    api_key, _ = await service.create_api_key(
        name="Cross-surface dashboard audit admin",
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


async def _seed_graph(
    project_service: ProjectService,
    task_service: TaskService,
    plan_service: PlanService,
    comment_service: CommentService,
) -> tuple[str, str]:
    active_project = await project_service.create_project(
        name="Cross Surface Dashboard Active Project"
    )
    active_task = await task_service.create_task(
        active_project.id,
        "Cross Surface Dashboard Active Task",
    )
    await task_service.start_task(active_task.id)

    terminal_project = await project_service.create_project(
        name="Cross Surface Dashboard Terminal Project"
    )
    terminal_task = await task_service.create_task(
        terminal_project.id,
        "Cross Surface Dashboard Terminal Task",
    )
    await task_service.start_task(terminal_task.id)
    await task_service.complete_task(terminal_task.id)
    await plan_service.create_plan(
        name="Cross Surface Dashboard Draft Residue Plan",
        description=None,
        status=PlanStatus.DRAFT,
        format=PlanFormat.JSON,
        content={"steps": ["residual planning only"]},
        project_id=terminal_project.id,
    )
    await project_service.update_project(
        terminal_project.id,
        status=ProjectStatus.COMPLETED,
    )
    await comment_service.add_comment(
        "task",
        terminal_task.id,
        "Fresh terminal dashboard activity",
        "cross-surface-dashboard-audit",
    )
    return active_project.id, terminal_project.id


def _evaluate_dashboard_payload(
    payload: dict[str, object],
    *,
    active_expectation: ProjectLifecycleExpectation,
    terminal_expectation: ProjectLifecycleExpectation,
    surface_prefix: str,
    issues: list[AggregateDashboardIssue],
) -> None:
    if payload.get("scope", {}).get("active_visible_projects") != 1:
        _record(
            issues,
            surface=surface_prefix,
            reason="active_visible_projects count mismatch",
        )
    active_item = _project_item(
        payload["active_projects"], active_expectation.project_id
    )
    completed_item = _project_item(
        payload["recently_completed_projects"],
        terminal_expectation.project_id,
    )
    _evaluate_project_payload(
        f"{surface_prefix}.active",
        active_item,
        active_expectation,
        issues=issues,
    )
    _evaluate_project_payload(
        f"{surface_prefix}.completed",
        completed_item,
        terminal_expectation,
        issues=issues,
    )
    freshest_activity = payload.get("freshest_visible_activity")
    if not isinstance(freshest_activity, dict):
        _record(
            issues, surface=surface_prefix, reason="missing freshest_visible_activity"
        )
    freshest_transition = payload.get("freshest_visible_transition")
    if not isinstance(freshest_transition, dict):
        _record(
            issues,
            surface=surface_prefix,
            reason="missing freshest_visible_transition",
        )


async def _run_audit_async() -> tuple[AggregateDashboardIssue, ...]:
    env = with_temp_env("cross-surface-operator-dashboard-")
    temp_dir = Path(env["PMS_DATA_DIR"])
    issues: list[AggregateDashboardIssue] = []

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

        active_project_id, terminal_project_id = await _seed_graph(
            project_service,
            task_service,
            plan_service,
            comment_service,
        )
        active_summary = await project_service.get_project_summary(active_project_id)
        terminal_summary = await project_service.get_project_summary(
            terminal_project_id
        )
        if active_summary is None or terminal_summary is None:
            raise RuntimeError("Seeded dashboard summaries were not available")

        active_expectation = expectation_from_summary(
            active_summary,
            focus_task_id=None,
        )
        terminal_expectation = expectation_from_summary(
            terminal_summary,
            focus_task_id=None,
        )

        cli_dashboard_result = run_cli(
            ["dashboard", "--format", "json"], env, width=160
        )
        require_success(
            cli_dashboard_result,
            args=["dashboard", "--format", "json"],
        )
        cli_dashboard = json.loads(cli_dashboard_result.stdout)
        _evaluate_dashboard_payload(
            cli_dashboard,
            active_expectation=active_expectation,
            terminal_expectation=terminal_expectation,
            surface_prefix="cli.dashboard",
            issues=issues,
        )

        api_client = await _make_api_client(db)
        api_dashboard_response = await api_client.get("/api/v1/dashboard")
        api_dashboard_response.raise_for_status()
        api_dashboard = api_dashboard_response.json()
        _evaluate_dashboard_payload(
            api_dashboard,
            active_expectation=active_expectation,
            terminal_expectation=terminal_expectation,
            surface_prefix="api.dashboard",
            issues=issues,
        )
        if api_dashboard.get("links", {}).get("self") != "/api/v1/dashboard":
            _record(issues, surface="api.dashboard", reason="self link mismatch")

        mcp_dashboard = _tool_payload(await get_dashboard.handler({}))
        _evaluate_dashboard_payload(
            mcp_dashboard,
            active_expectation=active_expectation,
            terminal_expectation=terminal_expectation,
            surface_prefix="mcp.dashboard",
            issues=issues,
        )
    finally:
        if api_client is not None:
            await api_client.aclose()
        await db.disconnect()
        shutil.rmtree(temp_dir, ignore_errors=True)

    return tuple(issues)


def run_audit() -> tuple[AggregateDashboardIssue, ...]:
    """Run the aggregate dashboard parity audit."""
    return asyncio.run(_run_audit_async())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail on any issue")
    args = parser.parse_args()

    issues = run_audit()
    print("Cross-surface aggregate operator dashboard audit")
    print(f"checked=3 issues={len(issues)}")
    for issue in issues:
        print(f"- {issue.surface}: {issue.reason}")

    if args.check and issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
