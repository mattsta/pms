#!/usr/bin/env python3
"""Audit objective API aggregate surfaces against shared lifecycle rollups."""

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
class ApiObjectiveLifecycleIssue:
    """One API objective lifecycle contract failure."""

    surface: str
    reason: str


def _record(
    issues: list[ApiObjectiveLifecycleIssue],
    *,
    surface: str,
    reason: str,
) -> None:
    issues.append(ApiObjectiveLifecycleIssue(surface=surface, reason=reason))


def _objective_item(
    items: list[dict[str, object]],
    objective_id: str,
) -> dict[str, object]:
    for item in items:
        if item.get("id") == objective_id:
            return item
    raise RuntimeError(f"Objective {objective_id} not found in payload")


def _evaluate_objective_list_payload(
    surface: str,
    payload: dict[str, object],
    expectation: ObjectiveLifecycleExpectation,
) -> tuple[ApiObjectiveLifecycleIssue, ...]:
    issues: list[ApiObjectiveLifecycleIssue] = []
    for reason in objective_list_payload_mismatch_reasons(payload, expectation):
        _record(issues, surface=surface, reason=reason)
    links = payload.get("links")
    if not isinstance(links, dict):
        _record(issues, surface=surface, reason="links missing")
    else:
        if links.get("self") != f"/api/v1/objectives/{expectation.objective_id}":
            _record(issues, surface=surface, reason="self link mismatch")
        if links.get("goal") != f"/api/v1/goals/{expectation.goal_id}":
            _record(issues, surface=surface, reason="goal link mismatch")
        if links.get("goal_summary") != f"/api/v1/goals/{expectation.goal_id}/summary":
            _record(issues, surface=surface, reason="goal_summary link mismatch")
        if (
            links.get("key_results")
            != f"/api/v1/objectives/{expectation.objective_id}/key-results"
        ):
            _record(issues, surface=surface, reason="key_results link mismatch")
        if links.get("guide") != "/api/v1/":
            _record(issues, surface=surface, reason="guide link mismatch")
        if expectation.project_id is not None:
            if links.get("project") != f"/api/v1/projects/{expectation.project_id}":
                _record(issues, surface=surface, reason="project link mismatch")
    next_steps = payload.get("next_steps")
    if not isinstance(next_steps, list) or not next_steps:
        _record(issues, surface=surface, reason="next_steps missing")
    else:
        if next_steps[0] != f"GET /api/v1/objectives/{expectation.objective_id}":
            _record(issues, surface=surface, reason="detail next_step mismatch")
        if (
            f"GET /api/v1/objectives/{expectation.objective_id}/key-results"
            not in next_steps
        ):
            _record(issues, surface=surface, reason="key_results next_step mismatch")
        if f"GET /api/v1/goals/{expectation.goal_id}" not in next_steps:
            _record(issues, surface=surface, reason="goal next_step mismatch")
        if f"GET /api/v1/goals/{expectation.goal_id}/summary" not in next_steps:
            _record(issues, surface=surface, reason="goal_summary next_step mismatch")
        if expectation.project_id is not None and (
            f"GET /api/v1/projects/{expectation.project_id}" not in next_steps
        ):
            _record(issues, surface=surface, reason="project next_step mismatch")
        if expectation.terminal_reason is not None and (
            f"GET /api/v1/goals/{expectation.goal_id}/objectives?status=completed"
            not in next_steps
        ):
            _record(
                issues,
                surface=surface,
                reason="completed objectives next_step mismatch",
            )
    return tuple(issues)


def _evaluate_objective_detail_payload(
    surface: str,
    payload: dict[str, object],
    expectation: ObjectiveLifecycleExpectation,
) -> tuple[ApiObjectiveLifecycleIssue, ...]:
    issues: list[ApiObjectiveLifecycleIssue] = []
    for reason in objective_detail_payload_mismatch_reasons(payload, expectation):
        _record(issues, surface=surface, reason=reason)
    links = payload.get("links")
    if not isinstance(links, dict):
        _record(issues, surface=surface, reason="links missing")
    else:
        if links.get("self") != f"/api/v1/objectives/{expectation.objective_id}":
            _record(issues, surface=surface, reason="self link mismatch")
        if links.get("goal") != f"/api/v1/goals/{expectation.goal_id}":
            _record(issues, surface=surface, reason="goal link mismatch")
        if links.get("goal_summary") != f"/api/v1/goals/{expectation.goal_id}/summary":
            _record(issues, surface=surface, reason="goal_summary link mismatch")
        if (
            links.get("key_results")
            != f"/api/v1/objectives/{expectation.objective_id}/key-results"
        ):
            _record(issues, surface=surface, reason="key_results link mismatch")
        if expectation.project_id is not None:
            if links.get("project") != f"/api/v1/projects/{expectation.project_id}":
                _record(issues, surface=surface, reason="project link mismatch")
    next_steps = payload.get("next_steps")
    if not isinstance(next_steps, list) or not next_steps:
        _record(issues, surface=surface, reason="next_steps missing")
    else:
        if next_steps[0] != f"GET /api/v1/objectives/{expectation.objective_id}":
            _record(issues, surface=surface, reason="detail next_step mismatch")
    return tuple(issues)


async def _make_api_client(db: Database) -> AsyncClient:
    repo = ApiKeyRepository(db)
    service = AuthService(repo)
    api_key, _ = await service.create_api_key(
        name="API objective lifecycle audit admin",
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


async def run_audit() -> tuple[ApiObjectiveLifecycleIssue, ...]:
    """Seed objectives and ensure API aggregate surfaces expose lifecycle rollups."""
    tmp_root = REPO_ROOT / ".tmp"
    tmp_root.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(
        tempfile.mkdtemp(prefix="api-objective-lifecycle-audit-", dir=tmp_root)
    )
    db = Database(temp_dir / "audit.db")
    await db.connect()
    await initialize_schema(db)
    await init_services(db)

    issues: list[ApiObjectiveLifecycleIssue] = []
    client: AsyncClient | None = None
    try:
        client = await _make_api_client(db)
        event_store = EventStore(db)
        revision_store = RevisionStore(db)
        metrics = MetricsCollector(db)
        project_service = ProjectService(db, event_store, revision_store, metrics)
        goal_service = GoalService(db, event_store, revision_store, metrics)

        fixture = await seed_objective_lifecycle_fixture(
            project_service,
            goal_service,
            active_project_name="Objective API Lifecycle Active Project",
            active_goal_name="Objective API Lifecycle Active Goal",
            active_objective_name="Objective API Lifecycle Active Objective",
            active_key_result_a_name="Objective API Lifecycle KR A",
            active_key_result_b_name="Objective API Lifecycle KR B",
            terminal_project_name="Objective API Lifecycle Terminal Project",
            terminal_goal_name="Objective API Lifecycle Terminal Goal",
            terminal_objective_name="Objective API Lifecycle Terminal Objective",
            terminal_key_result_name="Objective API Lifecycle Terminal KR",
        )
        expectations = await build_objective_lifecycle_expectations(
            goal_service,
            [fixture.active_objective_id, fixture.terminal_objective_id],
        )
        active_expectation = expectations[fixture.active_objective_id]
        terminal_expectation = expectations[fixture.terminal_objective_id]

        active_list_response = await client.get(
            f"/api/v1/goals/{fixture.active_goal_id}/objectives"
        )
        active_list_response.raise_for_status()
        active_list_item = _objective_item(
            active_list_response.json()["items"],
            fixture.active_objective_id,
        )
        issues.extend(
            _evaluate_objective_list_payload(
                "objectives.list.active",
                active_list_item,
                active_expectation,
            )
        )

        terminal_list_response = await client.get(
            f"/api/v1/goals/{fixture.terminal_goal_id}/objectives"
        )
        terminal_list_response.raise_for_status()
        terminal_list_item = _objective_item(
            terminal_list_response.json()["items"],
            fixture.terminal_objective_id,
        )
        issues.extend(
            _evaluate_objective_list_payload(
                "objectives.list.terminal",
                terminal_list_item,
                terminal_expectation,
            )
        )

        active_detail_response = await client.get(
            f"/api/v1/objectives/{fixture.active_objective_id}"
        )
        active_detail_response.raise_for_status()
        issues.extend(
            _evaluate_objective_detail_payload(
                "objectives.detail.active",
                active_detail_response.json(),
                active_expectation,
            )
        )

        terminal_detail_response = await client.get(
            f"/api/v1/objectives/{fixture.terminal_objective_id}"
        )
        terminal_detail_response.raise_for_status()
        issues.extend(
            _evaluate_objective_detail_payload(
                "objectives.detail.terminal",
                terminal_detail_response.json(),
                terminal_expectation,
            )
        )
    finally:
        if client is not None:
            await client.aclose()
        await db.disconnect()
        shutil.rmtree(temp_dir, ignore_errors=True)

    return tuple(issues)


def main() -> int:
    """Run the objective API lifecycle audit."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero when lifecycle contract issues are found.",
    )
    args = parser.parse_args()

    issues = asyncio.run(run_audit())
    payload = {
        "checked": 4,
        "issues": [
            {"surface": issue.surface, "reason": issue.reason} for issue in issues
        ],
    }
    print(json.dumps(payload, indent=2))
    if args.check and issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
