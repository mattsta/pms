#!/usr/bin/env python3
"""Audit goal API aggregate surfaces against shared lifecycle rollups."""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
import tempfile
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
from pms.repositories.api_key_repository import ApiKeyRepository
from pms.services.auth_service import AuthService
from pms.services.goal_service import GoalService
from pms.services.project_service import ProjectService
from pms.services.task_service import TaskService
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
class ApiGoalLifecycleIssue:
    """One API goal lifecycle contract failure."""

    surface: str
    reason: str


def _record(
    issues: list[ApiGoalLifecycleIssue],
    *,
    surface: str,
    reason: str,
) -> None:
    issues.append(ApiGoalLifecycleIssue(surface=surface, reason=reason))


def _goal_item(items: list[dict[str, object]], goal_id: str) -> dict[str, object]:
    for item in items:
        if item.get("id") == goal_id:
            return item
    raise RuntimeError(f"Goal {goal_id} not found in payload")


def _evaluate_goal_list_payload(
    surface: str,
    payload: dict[str, object],
    expectation: GoalLifecycleExpectation,
) -> tuple[ApiGoalLifecycleIssue, ...]:
    issues: list[ApiGoalLifecycleIssue] = []
    for reason in goal_list_payload_mismatch_reasons(payload, expectation):
        _record(issues, surface=surface, reason=reason)
    links = payload.get("links")
    project_id = payload.get("project_id")
    if not isinstance(links, dict):
        _record(issues, surface=surface, reason="links missing")
    else:
        if links.get("self") != f"/api/v1/goals/{expectation.goal_id}":
            _record(issues, surface=surface, reason="self link mismatch")
        if links.get("summary") != f"/api/v1/goals/{expectation.goal_id}/summary":
            _record(issues, surface=surface, reason="summary link mismatch")
        if links.get("objectives") != f"/api/v1/goals/{expectation.goal_id}/objectives":
            _record(issues, surface=surface, reason="objectives link mismatch")
        if links.get("plans") != f"/api/v1/plans?goal_id={expectation.goal_id}":
            _record(issues, surface=surface, reason="plans link mismatch")
        if links.get("guide") != "/api/v1/":
            _record(issues, surface=surface, reason="guide link mismatch")
        if project_id:
            if links.get("project") != f"/api/v1/projects/{project_id}":
                _record(issues, surface=surface, reason="project link mismatch")
            if links.get("tasks") != f"/api/v1/tasks?project_id={project_id}":
                _record(issues, surface=surface, reason="tasks link mismatch")
    next_steps = payload.get("next_steps")
    if not isinstance(next_steps, list) or not next_steps:
        _record(issues, surface=surface, reason="next_steps missing")
    else:
        if next_steps[0] != f"GET /api/v1/goals/{expectation.goal_id}/summary":
            _record(issues, surface=surface, reason="summary next_step mismatch")
        if f"GET /api/v1/goals/{expectation.goal_id}/objectives" not in next_steps:
            _record(issues, surface=surface, reason="objectives next_step mismatch")
        if f"GET /api/v1/plans?goal_id={expectation.goal_id}" not in next_steps:
            _record(issues, surface=surface, reason="plans next_step mismatch")
        if project_id and f"GET /api/v1/projects/{project_id}" not in next_steps:
            _record(issues, surface=surface, reason="project next_step mismatch")
        if expectation.execution_focus_task_id is not None:
            if (
                f"GET /api/v1/tasks/{expectation.execution_focus_task_id}"
                not in next_steps
            ):
                _record(issues, surface=surface, reason="focus task next_step mismatch")
        elif expectation.terminal_reason is not None and project_id:
            if f"GET /api/v1/tasks?project_id={project_id}" not in next_steps:
                _record(
                    issues,
                    surface=surface,
                    reason="terminal tasks next_step mismatch",
                )
        if expectation.terminal_reason is not None:
            if "GET /api/v1/goals?status=completed" not in next_steps:
                _record(
                    issues,
                    surface=surface,
                    reason="completed goals next_step mismatch",
                )
    return tuple(issues)


def _evaluate_goal_summary_payload(
    surface: str,
    payload: dict[str, object],
    expectation: GoalLifecycleExpectation,
) -> tuple[ApiGoalLifecycleIssue, ...]:
    issues: list[ApiGoalLifecycleIssue] = []
    for reason in goal_summary_payload_mismatch_reasons(payload, expectation):
        _record(issues, surface=surface, reason=reason)
    links = payload.get("links")
    if not isinstance(links, dict):
        _record(issues, surface=surface, reason="links missing")
    else:
        if links.get("self") != f"/api/v1/goals/{expectation.goal_id}/summary":
            _record(issues, surface=surface, reason="self link mismatch")
        if links.get("goal") != f"/api/v1/goals/{expectation.goal_id}":
            _record(issues, surface=surface, reason="goal link mismatch")
        if links.get("objectives") != f"/api/v1/goals/{expectation.goal_id}/objectives":
            _record(issues, surface=surface, reason="objectives link mismatch")
        if links.get("plans") != f"/api/v1/plans?goal_id={expectation.goal_id}":
            _record(issues, surface=surface, reason="plans link mismatch")
    next_steps = payload.get("next_steps")
    if not isinstance(next_steps, list) or not next_steps:
        _record(issues, surface=surface, reason="next_steps missing")
    return tuple(issues)


def _evaluate_goal_detail_payload(
    surface: str,
    payload: dict[str, object],
    expectation: GoalLifecycleExpectation,
) -> tuple[ApiGoalLifecycleIssue, ...]:
    issues: list[ApiGoalLifecycleIssue] = []
    for reason in goal_detail_payload_mismatch_reasons(payload, expectation):
        _record(issues, surface=surface, reason=reason)
    links = payload.get("links")
    if not isinstance(links, dict):
        _record(issues, surface=surface, reason="links missing")
    else:
        if links.get("self") != f"/api/v1/goals/{expectation.goal_id}":
            _record(issues, surface=surface, reason="self link mismatch")
        if links.get("summary") != f"/api/v1/goals/{expectation.goal_id}/summary":
            _record(issues, surface=surface, reason="summary link mismatch")
        if links.get("objectives") != f"/api/v1/goals/{expectation.goal_id}/objectives":
            _record(issues, surface=surface, reason="objectives link mismatch")
        if links.get("plans") != f"/api/v1/plans?goal_id={expectation.goal_id}":
            _record(issues, surface=surface, reason="plans link mismatch")
    next_steps = payload.get("next_steps")
    if not isinstance(next_steps, list) or not next_steps:
        _record(issues, surface=surface, reason="next_steps missing")
    return tuple(issues)


async def _make_api_client(db: Database) -> AsyncClient:
    repo = ApiKeyRepository(db)
    service = AuthService(repo)
    api_key, _ = await service.create_api_key(
        name="API goal lifecycle audit admin",
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


async def run_audit() -> tuple[ApiGoalLifecycleIssue, ...]:
    """Seed goals and ensure API aggregate surfaces expose shared lifecycle rollups."""
    tmp_root = REPO_ROOT / ".tmp"
    tmp_root.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix="api-goal-lifecycle-audit-", dir=tmp_root))
    db = Database(temp_dir / "audit.db")
    await db.connect()
    await initialize_schema(db)
    await init_services(db)

    issues: list[ApiGoalLifecycleIssue] = []
    client: AsyncClient | None = None
    try:
        client = await _make_api_client(db)
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
            active_project_name="API Goal Lifecycle Active Project",
            active_goal_name="API Goal Lifecycle Active Goal",
            active_task_title="API Goal Lifecycle Active Task",
            active_progress_percent=45,
            active_status_message="Implementing",
            active_updated_by="goal-audit",
            terminal_project_name="API Goal Lifecycle Terminal Project",
            terminal_goal_name="API Goal Lifecycle Terminal Goal",
            terminal_task_title="API Goal Lifecycle Terminal Task",
        )
        expectations, _ = await build_goal_lifecycle_expectations(
            goal_service,
            [fixture.active_goal_id, fixture.terminal_goal_id],
        )

        list_payload = await client.get("/api/v1/goals")
        list_payload.raise_for_status()
        list_json = list_payload.json()
        issues.extend(
            _evaluate_goal_list_payload(
                "goals.list.active",
                _goal_item(list_json["items"], fixture.active_goal_id),
                expectations[fixture.active_goal_id],
            )
        )
        issues.extend(
            _evaluate_goal_list_payload(
                "goals.list.terminal",
                _goal_item(list_json["items"], fixture.terminal_goal_id),
                expectations[fixture.terminal_goal_id],
            )
        )

        active_detail = await client.get(f"/api/v1/goals/{fixture.active_goal_id}")
        active_detail.raise_for_status()
        issues.extend(
            _evaluate_goal_detail_payload(
                "goals.detail.active",
                active_detail.json(),
                expectations[fixture.active_goal_id],
            )
        )

        terminal_detail = await client.get(f"/api/v1/goals/{fixture.terminal_goal_id}")
        terminal_detail.raise_for_status()
        issues.extend(
            _evaluate_goal_detail_payload(
                "goals.detail.terminal",
                terminal_detail.json(),
                expectations[fixture.terminal_goal_id],
            )
        )

        active_summary = await client.get(
            f"/api/v1/goals/{fixture.active_goal_id}/summary"
        )
        active_summary.raise_for_status()
        issues.extend(
            _evaluate_goal_summary_payload(
                "goals.summary.active",
                active_summary.json(),
                expectations[fixture.active_goal_id],
            )
        )

        terminal_summary = await client.get(
            f"/api/v1/goals/{fixture.terminal_goal_id}/summary"
        )
        terminal_summary.raise_for_status()
        issues.extend(
            _evaluate_goal_summary_payload(
                "goals.summary.terminal",
                terminal_summary.json(),
                expectations[fixture.terminal_goal_id],
            )
        )
    finally:
        if client is not None:
            await client.aclose()
        await db.disconnect()
        shutil.rmtree(temp_dir, ignore_errors=True)

    return tuple(issues)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit goal API aggregate payloads against shared lifecycle rollups."
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
            f"API goal lifecycle contract audit\nchecked={checked} issues={len(issues)}"
        )
        for issue in issues:
            print(f"- {issue.surface}: {issue.reason}")
    if args.check and issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
