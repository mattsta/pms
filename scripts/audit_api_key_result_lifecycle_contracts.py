#!/usr/bin/env python3
"""Audit key result API aggregate surfaces against maintained lifecycle fields."""

from __future__ import annotations

import argparse
import asyncio
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
class ApiKeyResultLifecycleIssue:
    """One API key result lifecycle contract failure."""

    surface: str
    reason: str


def _record(
    issues: list[ApiKeyResultLifecycleIssue],
    *,
    surface: str,
    reason: str,
) -> None:
    issues.append(ApiKeyResultLifecycleIssue(surface=surface, reason=reason))


def _key_result_item(
    items: list[dict[str, object]],
    key_result_id: str,
) -> dict[str, object]:
    for item in items:
        if item.get("id") == key_result_id:
            return item
    raise RuntimeError(f"Key result {key_result_id} not found in payload")


def _evaluate_key_result_list_payload(
    surface: str,
    payload: dict[str, object],
    expectation: KeyResultLifecycleExpectation,
) -> tuple[ApiKeyResultLifecycleIssue, ...]:
    issues: list[ApiKeyResultLifecycleIssue] = []
    for reason in key_result_list_payload_mismatch_reasons(payload, expectation):
        _record(issues, surface=surface, reason=reason)
    links = payload.get("links")
    if not isinstance(links, dict):
        _record(issues, surface=surface, reason="links missing")
    else:
        if links.get("self") != f"/api/v1/key-results/{expectation.key_result_id}":
            _record(issues, surface=surface, reason="self link mismatch")
        if links.get("objective") != f"/api/v1/objectives/{expectation.objective_id}":
            _record(issues, surface=surface, reason="objective link mismatch")
        if (
            links.get("objective_key_results")
            != f"/api/v1/objectives/{expectation.objective_id}/key-results"
        ):
            _record(
                issues,
                surface=surface,
                reason="objective_key_results link mismatch",
            )
        if links.get("goal") != f"/api/v1/goals/{expectation.goal_id}":
            _record(issues, surface=surface, reason="goal link mismatch")
        if links.get("goal_summary") != f"/api/v1/goals/{expectation.goal_id}/summary":
            _record(issues, surface=surface, reason="goal_summary link mismatch")
        if expectation.project_id is not None and (
            links.get("project") != f"/api/v1/projects/{expectation.project_id}"
        ):
            _record(issues, surface=surface, reason="project link mismatch")
        if links.get("guide") != "/api/v1/":
            _record(issues, surface=surface, reason="guide link mismatch")
    next_steps = payload.get("next_steps")
    if not isinstance(next_steps, list) or not next_steps:
        _record(issues, surface=surface, reason="next_steps missing")
    else:
        if next_steps[0] != f"GET /api/v1/key-results/{expectation.key_result_id}":
            _record(issues, surface=surface, reason="detail next_step mismatch")
        if (
            f"GET /api/v1/objectives/{expectation.objective_id}/key-results"
            not in next_steps
        ):
            _record(issues, surface=surface, reason="collection next_step mismatch")
        if f"GET /api/v1/objectives/{expectation.objective_id}" not in next_steps:
            _record(issues, surface=surface, reason="objective next_step mismatch")
        if f"GET /api/v1/goals/{expectation.goal_id}" not in next_steps:
            _record(issues, surface=surface, reason="goal next_step mismatch")
        if f"GET /api/v1/goals/{expectation.goal_id}/summary" not in next_steps:
            _record(issues, surface=surface, reason="goal_summary next_step mismatch")
        if expectation.project_id is not None and (
            f"GET /api/v1/projects/{expectation.project_id}" not in next_steps
        ):
            _record(issues, surface=surface, reason="project next_step mismatch")
        if expectation.terminal_reason is not None and (
            f"GET /api/v1/objectives/{expectation.objective_id}/key-results?status=completed"
            not in next_steps
        ):
            _record(
                issues,
                surface=surface,
                reason="completed key results next_step mismatch",
            )
    return tuple(issues)


def _evaluate_key_result_detail_payload(
    surface: str,
    payload: dict[str, object],
    expectation: KeyResultLifecycleExpectation,
) -> tuple[ApiKeyResultLifecycleIssue, ...]:
    issues: list[ApiKeyResultLifecycleIssue] = []
    for reason in key_result_detail_payload_mismatch_reasons(payload, expectation):
        _record(issues, surface=surface, reason=reason)
    links = payload.get("links")
    if not isinstance(links, dict):
        _record(issues, surface=surface, reason="links missing")
    else:
        if links.get("self") != f"/api/v1/key-results/{expectation.key_result_id}":
            _record(issues, surface=surface, reason="self link mismatch")
        if links.get("objective") != f"/api/v1/objectives/{expectation.objective_id}":
            _record(issues, surface=surface, reason="objective link mismatch")
        if (
            links.get("objective_key_results")
            != f"/api/v1/objectives/{expectation.objective_id}/key-results"
        ):
            _record(
                issues,
                surface=surface,
                reason="objective_key_results link mismatch",
            )
        if links.get("goal") != f"/api/v1/goals/{expectation.goal_id}":
            _record(issues, surface=surface, reason="goal link mismatch")
        if links.get("goal_summary") != f"/api/v1/goals/{expectation.goal_id}/summary":
            _record(issues, surface=surface, reason="goal_summary link mismatch")
        if expectation.project_id is not None and (
            links.get("project") != f"/api/v1/projects/{expectation.project_id}"
        ):
            _record(issues, surface=surface, reason="project link mismatch")
        if links.get("guide") != "/api/v1/":
            _record(issues, surface=surface, reason="guide link mismatch")
    next_steps = payload.get("next_steps")
    if not isinstance(next_steps, list) or not next_steps:
        _record(issues, surface=surface, reason="next_steps missing")
    else:
        if next_steps[0] != f"GET /api/v1/key-results/{expectation.key_result_id}":
            _record(issues, surface=surface, reason="detail next_step mismatch")
    return tuple(issues)


async def _make_api_client(db: Database) -> AsyncClient:
    repo = ApiKeyRepository(db)
    service = AuthService(repo)
    api_key, _ = await service.create_api_key(
        name="API key result lifecycle audit admin",
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


async def run_audit() -> tuple[ApiKeyResultLifecycleIssue, ...]:
    """Seed key results and ensure API surfaces expose lifecycle fields."""
    tmp_root = REPO_ROOT / ".tmp"
    tmp_root.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(
        tempfile.mkdtemp(prefix="api-key-result-lifecycle-audit-", dir=tmp_root)
    )
    db = Database(temp_dir / "audit.db")
    await db.connect()
    await initialize_schema(db)
    await init_services(db)

    issues: list[ApiKeyResultLifecycleIssue] = []
    client: AsyncClient | None = None
    try:
        client = await _make_api_client(db)
        event_store = EventStore(db)
        revision_store = RevisionStore(db)
        metrics = MetricsCollector(db)
        project_service = ProjectService(db, event_store, revision_store, metrics)
        goal_service = GoalService(db, event_store, revision_store, metrics)
        fixture = await seed_key_result_lifecycle_fixture(
            project_service,
            goal_service,
            active_project_name="API Key Result Lifecycle Active Project",
            active_goal_name="API Key Result Lifecycle Active Goal",
            active_objective_name="API Key Result Lifecycle Active Objective",
            active_key_result_name="API Key Result Lifecycle Active Key Result",
            terminal_project_name="API Key Result Lifecycle Terminal Project",
            terminal_goal_name="API Key Result Lifecycle Terminal Goal",
            terminal_objective_name="API Key Result Lifecycle Terminal Objective",
            terminal_key_result_name="API Key Result Lifecycle Terminal Key Result",
        )
        expectations = await build_key_result_lifecycle_expectations(
            goal_service,
            [fixture.active_key_result_id, fixture.terminal_key_result_id],
        )
        active_expectation = expectations[fixture.active_key_result_id]
        terminal_expectation = expectations[fixture.terminal_key_result_id]

        active_list_response = await client.get(
            f"/api/v1/objectives/{fixture.active_objective_id}/key-results"
        )
        active_list_response.raise_for_status()
        issues.extend(
            _evaluate_key_result_list_payload(
                "key_results.list.active",
                _key_result_item(
                    active_list_response.json()["items"],
                    fixture.active_key_result_id,
                ),
                active_expectation,
            )
        )

        terminal_list_response = await client.get(
            f"/api/v1/objectives/{fixture.terminal_objective_id}/key-results"
        )
        terminal_list_response.raise_for_status()
        issues.extend(
            _evaluate_key_result_list_payload(
                "key_results.list.terminal",
                _key_result_item(
                    terminal_list_response.json()["items"],
                    fixture.terminal_key_result_id,
                ),
                terminal_expectation,
            )
        )

        active_detail_response = await client.get(
            f"/api/v1/key-results/{fixture.active_key_result_id}"
        )
        active_detail_response.raise_for_status()
        issues.extend(
            _evaluate_key_result_detail_payload(
                "key_results.detail.active",
                active_detail_response.json(),
                active_expectation,
            )
        )

        terminal_detail_response = await client.get(
            f"/api/v1/key-results/{fixture.terminal_key_result_id}"
        )
        terminal_detail_response.raise_for_status()
        issues.extend(
            _evaluate_key_result_detail_payload(
                "key_results.detail.terminal",
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero when contract issues are found.",
    )
    args = parser.parse_args()

    issues = asyncio.run(run_audit())
    print("API key result lifecycle contract audit")
    print(f"checked=4 issues={len(issues)}")
    for issue in issues:
        print(f"- {issue.surface}: {issue.reason}")

    if args.check and issues:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
