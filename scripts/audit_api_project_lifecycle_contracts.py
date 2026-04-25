#!/usr/bin/env python3
"""Audit project API surfaces against the shared lifecycle rollup contract."""

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
from pms.services.plan_service import PlanService
from pms.services.project_service import ProjectService
from pms.services.task_service import TaskService
from scripts.lifecycle_aggregate_fixture import seed_project_lifecycle_fixture
from scripts.project_lifecycle_contract_utils import (
    ProjectLifecycleExpectation as ProjectPayloadExpectation,
)
from scripts.project_lifecycle_contract_utils import (
    expectation_from_summary,
    project_payload_mismatch_reasons,
)


@dataclass(frozen=True)
class ApiProjectLifecycleIssue:
    """One API project lifecycle contract failure."""

    surface: str
    reason: str


def evaluate_project_payload(
    surface: str,
    payload: dict[str, object],
    expectation: ProjectPayloadExpectation,
) -> tuple[ApiProjectLifecycleIssue, ...]:
    """Compare one serialized project payload against the expected lifecycle contract."""
    issues: list[ApiProjectLifecycleIssue] = []

    def record(condition: bool, reason: str) -> None:
        if not condition:
            issues.append(ApiProjectLifecycleIssue(surface=surface, reason=reason))

    for reason in project_payload_mismatch_reasons(
        payload,
        expectation,
        check_focus_task=True,
    ):
        record(False, reason)
    record(
        isinstance(payload.get("links"), dict)
        and str(payload["links"].get("self", "")).endswith(
            f"/api/v1/projects/{expectation.project_id}"
        ),
        "missing canonical self link",
    )
    record(
        isinstance(payload.get("next_steps"), list) and len(payload["next_steps"]) > 0,
        "missing next_steps",
    )

    return tuple(issues)


async def _make_api_client(db: Database) -> tuple[AsyncClient, str]:
    repo = ApiKeyRepository(db)
    service = AuthService(repo)
    api_key, _ = await service.create_api_key(
        name="API lifecycle audit admin",
        scopes=["*"],
        expires_in_days=None,
        rate_limit=None,
    )
    app.state.db = db
    app.state.start_time = time.time()
    client = AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-API-Key": api_key},
    )
    return client, api_key


def _project_item(items: list[dict[str, object]], project_id: str) -> dict[str, object]:
    for item in items:
        if item.get("id") == project_id:
            return item
    raise RuntimeError(f"Project {project_id} not found in list payload")


async def run_audit() -> tuple[ApiProjectLifecycleIssue, ...]:
    """Seed a nested graph and ensure API project surfaces expose shared rollups."""
    tmp_root = REPO_ROOT / ".tmp"
    tmp_root.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(
        tempfile.mkdtemp(prefix="api-project-lifecycle-audit-", dir=tmp_root)
    )
    db = Database(temp_dir / "audit.db")
    await db.connect()
    await initialize_schema(db)
    await init_services(db)

    issues: list[ApiProjectLifecycleIssue] = []
    client: AsyncClient | None = None
    try:
        client, _ = await _make_api_client(db)

        event_store = EventStore(db)
        revision_store = RevisionStore(db)
        metrics = MetricsCollector(db)
        project_service = ProjectService(db, event_store, revision_store, metrics)
        task_service = TaskService(db, event_store, revision_store, metrics)
        plan_service = PlanService(db, event_store, revision_store, metrics)
        fixture = await seed_project_lifecycle_fixture(
            project_service,
            task_service,
            plan_service,
            active_project_name="API Lifecycle Active Project",
            active_task_title="API Lifecycle Active Task",
            start_active_task=True,
            terminal_project_name="API Lifecycle Terminal Project",
            terminal_task_title="API Lifecycle Terminal Task",
            terminal_plan_name="API Lifecycle Residue Plan",
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
                ApiProjectLifecycleIssue(
                    surface="setup",
                    reason="failed to compute project summaries for seeded audit graph",
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

        listing = await client.get("/api/v1/projects")
        listing.raise_for_status()
        listing_payload = listing.json()
        if not listing_payload.get("next_steps"):
            issues.append(
                ApiProjectLifecycleIssue(
                    surface="projects.list",
                    reason="list payload missing next_steps",
                )
            )
        issues.extend(
            evaluate_project_payload(
                "projects.list.active",
                _project_item(listing_payload["items"], fixture.active_project_id),
                ProjectPayloadExpectation(
                    **{
                        **active_expectation.__dict__,
                        "focus_task_id": None,
                    }
                ),
            )
        )
        issues.extend(
            evaluate_project_payload(
                "projects.list.terminal",
                _project_item(listing_payload["items"], fixture.terminal_project_id),
                terminal_expectation,
            )
        )

        active_detail = await client.get(
            f"/api/v1/projects/{fixture.active_project_id}"
        )
        active_detail.raise_for_status()
        issues.extend(
            evaluate_project_payload(
                "projects.detail.active",
                active_detail.json(),
                active_expectation,
            )
        )

        terminal_detail = await client.get(
            f"/api/v1/projects/{fixture.terminal_project_id}"
        )
        terminal_detail.raise_for_status()
        issues.extend(
            evaluate_project_payload(
                "projects.detail.terminal",
                terminal_detail.json(),
                terminal_expectation,
            )
        )

        active_summary_payload = await client.get(
            f"/api/v1/projects/{fixture.active_project_id}/summary"
        )
        active_summary_payload.raise_for_status()
        active_summary_json = active_summary_payload.json()
        issues.extend(
            evaluate_project_payload(
                "projects.summary.active",
                active_summary_json["project"],
                active_expectation,
            )
        )

        terminal_summary_payload = await client.get(
            f"/api/v1/projects/{fixture.terminal_project_id}/summary"
        )
        terminal_summary_payload.raise_for_status()
        terminal_summary_json = terminal_summary_payload.json()
        issues.extend(
            evaluate_project_payload(
                "projects.summary.terminal",
                terminal_summary_json["project"],
                terminal_expectation,
            )
        )

        active_overview = await client.get(
            f"/api/v1/projects/{fixture.active_project_id}/operator-overview"
        )
        active_overview.raise_for_status()
        active_overview_json = active_overview.json()
        issues.extend(
            evaluate_project_payload(
                "projects.operator_overview.active",
                active_overview_json["project"],
                active_expectation,
            )
        )
        if (
            active_overview_json.get("focus_task", {}).get("id")
            != active_expectation.focus_task_id
        ):
            issues.append(
                ApiProjectLifecycleIssue(
                    surface="projects.operator_overview.active",
                    reason="top-level focus_task id mismatch",
                )
            )

        terminal_overview = await client.get(
            f"/api/v1/projects/{fixture.terminal_project_id}/operator-overview"
        )
        terminal_overview.raise_for_status()
        terminal_overview_json = terminal_overview.json()
        issues.extend(
            evaluate_project_payload(
                "projects.operator_overview.terminal",
                terminal_overview_json["project"],
                terminal_expectation,
            )
        )
        if terminal_overview_json.get("focus_task") is not None:
            issues.append(
                ApiProjectLifecycleIssue(
                    surface="projects.operator_overview.terminal",
                    reason="top-level focus_task should be absent for terminal payload",
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
        description="Audit project API lifecycle payloads against shared rollups."
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    issues = asyncio.run(run_audit())
    if args.json:
        print(
            json.dumps(
                {
                    "checked": 8,
                    "issues": [
                        {"surface": issue.surface, "reason": issue.reason}
                        for issue in issues
                    ],
                },
                indent=2,
            )
        )
    else:
        print(f"API project lifecycle contract audit\nchecked=8 issues={len(issues)}")
        for issue in issues:
            print(f"- {issue.surface}: {issue.reason}")
    if args.check and issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
