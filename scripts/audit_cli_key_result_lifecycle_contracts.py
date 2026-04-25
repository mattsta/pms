#!/usr/bin/env python3
"""Audit CLI key-result aggregate surfaces against shared lifecycle rollups."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.db.connection import Database
from pms.services.goal_service import GoalService
from pms.services.project_service import ProjectService
from pms.utils.cli_commands import cli_command
from scripts.cli_surface_audit_utils import require_success, run_cli, with_temp_env
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
class CliKeyResultLifecycleIssue:
    """One CLI key-result lifecycle contract failure."""

    surface: str
    reason: str


def _record(
    issues: list[CliKeyResultLifecycleIssue],
    *,
    surface: str,
    reason: str,
) -> None:
    issues.append(CliKeyResultLifecycleIssue(surface=surface, reason=reason))


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
) -> tuple[CliKeyResultLifecycleIssue, ...]:
    issues: list[CliKeyResultLifecycleIssue] = []
    for reason in key_result_list_payload_mismatch_reasons(payload, expectation):
        _record(issues, surface=surface, reason=reason)

    links = payload.get("links")
    if not isinstance(links, dict):
        _record(issues, surface=surface, reason="links missing")
    else:
        if links.get("self") != cli_command(
            f"keyresult show {expectation.key_result_id}"
        ):
            _record(issues, surface=surface, reason="self link mismatch")
        if links.get("objective") != cli_command(
            f"objective show {expectation.objective_id}"
        ):
            _record(issues, surface=surface, reason="objective link mismatch")
        if links.get("key_results") != cli_command(
            f"keyresult list --objective-id {expectation.objective_id} --format json"
        ):
            _record(issues, surface=surface, reason="key_results link mismatch")
        if links.get("goal") != cli_command(f"goal show {expectation.goal_id}"):
            _record(issues, surface=surface, reason="goal link mismatch")
        if links.get("goal_summary") != cli_command(
            f"goal summary {expectation.goal_id}"
        ):
            _record(issues, surface=surface, reason="goal_summary link mismatch")
        if expectation.project_id is not None and (
            links.get("project")
            != cli_command(f"project show {expectation.project_id} --format json")
        ):
            _record(issues, surface=surface, reason="project link mismatch")

    next_steps = payload.get("next_steps")
    if not isinstance(next_steps, list) or not next_steps:
        _record(issues, surface=surface, reason="next_steps missing")
    else:
        if next_steps[0] != cli_command(f"keyresult show {expectation.key_result_id}"):
            _record(issues, surface=surface, reason="detail next_step mismatch")
        if cli_command(f"objective show {expectation.objective_id}") not in next_steps:
            _record(issues, surface=surface, reason="objective next_step mismatch")
        if (
            cli_command(
                f"keyresult list --objective-id {expectation.objective_id} --format json"
            )
            not in next_steps
        ):
            _record(issues, surface=surface, reason="key_results next_step mismatch")
        if cli_command(f"goal show {expectation.goal_id}") not in next_steps:
            _record(issues, surface=surface, reason="goal next_step mismatch")
        if cli_command(f"goal summary {expectation.goal_id}") not in next_steps:
            _record(issues, surface=surface, reason="goal_summary next_step mismatch")
        if expectation.project_id is not None and (
            cli_command(f"project show {expectation.project_id} --format json")
            not in next_steps
        ):
            _record(issues, surface=surface, reason="project next_step mismatch")
        if expectation.terminal_reason is None:
            if (
                cli_command(f"keyresult update {expectation.key_result_id}")
                not in next_steps
            ):
                _record(issues, surface=surface, reason="update next_step mismatch")
        else:
            if (
                cli_command(
                    f"keyresult list --objective-id {expectation.objective_id} --status completed --format json"
                )
                not in next_steps
            ):
                _record(
                    issues,
                    surface=surface,
                    reason="completed key_results next_step mismatch",
                )

    return tuple(issues)


def _evaluate_key_result_show_payload(
    surface: str,
    payload: dict[str, object],
    expectation: KeyResultLifecycleExpectation,
) -> tuple[CliKeyResultLifecycleIssue, ...]:
    issues: list[CliKeyResultLifecycleIssue] = []
    for reason in key_result_detail_payload_mismatch_reasons(payload, expectation):
        _record(issues, surface=surface, reason=reason)

    links = payload.get("links")
    if not isinstance(links, dict):
        _record(issues, surface=surface, reason="links missing")
    else:
        if links.get("self") != cli_command(
            f"keyresult show {expectation.key_result_id}"
        ):
            _record(issues, surface=surface, reason="self link mismatch")
        if links.get("objective") != cli_command(
            f"objective show {expectation.objective_id}"
        ):
            _record(issues, surface=surface, reason="objective link mismatch")
        if links.get("key_results") != cli_command(
            f"keyresult list --objective-id {expectation.objective_id} --format json"
        ):
            _record(issues, surface=surface, reason="key_results link mismatch")
        if links.get("goal") != cli_command(f"goal show {expectation.goal_id}"):
            _record(issues, surface=surface, reason="goal link mismatch")
        if links.get("goal_summary") != cli_command(
            f"goal summary {expectation.goal_id}"
        ):
            _record(issues, surface=surface, reason="goal_summary link mismatch")
        if expectation.project_id is not None and (
            links.get("project")
            != cli_command(f"project show {expectation.project_id} --format json")
        ):
            _record(issues, surface=surface, reason="project link mismatch")

    next_steps = payload.get("next_steps")
    if not isinstance(next_steps, list) or not next_steps:
        _record(issues, surface=surface, reason="next_steps missing")
    elif next_steps[0] != cli_command(f"keyresult show {expectation.key_result_id}"):
        _record(issues, surface=surface, reason="detail next_step mismatch")

    return tuple(issues)


async def run_audit() -> tuple[CliKeyResultLifecycleIssue, ...]:
    """Seed key results and ensure CLI aggregate surfaces expose lifecycle rollups."""
    env = with_temp_env("cli-key-result-lifecycle-audit-")
    init_result = run_cli(["init"], env, width=120)
    require_success(init_result, args=["init"])

    db = Database(Path(env["PMS_DATABASE_PATH"]))
    await db.connect()
    issues: list[CliKeyResultLifecycleIssue] = []
    try:
        event_store = EventStore(db)
        revision_store = RevisionStore(db)
        metrics = MetricsCollector(db)
        project_service = ProjectService(db, event_store, revision_store, metrics)
        goal_service = GoalService(db, event_store, revision_store, metrics)

        fixture = await seed_key_result_lifecycle_fixture(
            project_service,
            goal_service,
            active_project_name="CLI Key Result Lifecycle Active Project",
            active_goal_name="CLI Key Result Lifecycle Active Goal",
            active_objective_name="CLI Key Result Lifecycle Active Objective",
            active_key_result_name="CLI Key Result Lifecycle Active KR",
            terminal_project_name="CLI Key Result Lifecycle Terminal Project",
            terminal_goal_name="CLI Key Result Lifecycle Terminal Goal",
            terminal_objective_name="CLI Key Result Lifecycle Terminal Objective",
            terminal_key_result_name="CLI Key Result Lifecycle Terminal KR",
        )
        expectations = await build_key_result_lifecycle_expectations(
            goal_service,
            [fixture.active_key_result_id, fixture.terminal_key_result_id],
        )

        active_list_result = run_cli(
            [
                "keyresult",
                "list",
                "--objective-id",
                fixture.active_objective_id,
                "--format",
                "json",
                "--limit",
                "50",
                "--offset",
                "0",
            ],
            env,
            width=120,
        )
        require_success(
            active_list_result,
            args=[
                "keyresult",
                "list",
                "--objective-id",
                fixture.active_objective_id,
                "--format",
                "json",
            ],
        )
        active_list_payload = json.loads(active_list_result.stdout)
        issues.extend(
            _evaluate_key_result_list_payload(
                "keyresult.list.active",
                _key_result_item(
                    active_list_payload["items"],
                    fixture.active_key_result_id,
                ),
                expectations[fixture.active_key_result_id],
            )
        )

        terminal_list_result = run_cli(
            [
                "keyresult",
                "list",
                "--objective-id",
                fixture.terminal_objective_id,
                "--format",
                "json",
                "--limit",
                "50",
                "--offset",
                "0",
            ],
            env,
            width=120,
        )
        require_success(
            terminal_list_result,
            args=[
                "keyresult",
                "list",
                "--objective-id",
                fixture.terminal_objective_id,
                "--format",
                "json",
            ],
        )
        terminal_list_payload = json.loads(terminal_list_result.stdout)
        issues.extend(
            _evaluate_key_result_list_payload(
                "keyresult.list.terminal",
                _key_result_item(
                    terminal_list_payload["items"],
                    fixture.terminal_key_result_id,
                ),
                expectations[fixture.terminal_key_result_id],
            )
        )

        active_show_result = run_cli(
            ["keyresult", "show", fixture.active_key_result_id, "--format", "json"],
            env,
            width=120,
        )
        require_success(
            active_show_result,
            args=[
                "keyresult",
                "show",
                fixture.active_key_result_id,
                "--format",
                "json",
            ],
        )
        issues.extend(
            _evaluate_key_result_show_payload(
                "keyresult.show.active",
                json.loads(active_show_result.stdout),
                expectations[fixture.active_key_result_id],
            )
        )

        terminal_show_result = run_cli(
            ["keyresult", "show", fixture.terminal_key_result_id, "--format", "json"],
            env,
            width=120,
        )
        require_success(
            terminal_show_result,
            args=[
                "keyresult",
                "show",
                fixture.terminal_key_result_id,
                "--format",
                "json",
            ],
        )
        issues.extend(
            _evaluate_key_result_show_payload(
                "keyresult.show.terminal",
                json.loads(terminal_show_result.stdout),
                expectations[fixture.terminal_key_result_id],
            )
        )
    finally:
        await db.disconnect()

    return tuple(issues)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit CLI key-result lifecycle payloads against shared lifecycle rollups."
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
            "CLI key result lifecycle contract audit\n"
            f"checked={checked} issues={len(issues)}"
        )
        for issue in issues:
            print(f"- {issue.surface}: {issue.reason}")
    if args.check and issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
