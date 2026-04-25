#!/usr/bin/env python3
"""Audit deep activity/transition rollup contracts across graph summary surfaces."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class GraphTimestampRollupIssue:
    file: str
    reason: str


ROLLUP_CONTRACTS: dict[str, dict[str, tuple[str, ...]]] = {
    "pms/repositories/task_repository.py": {
        "required": (
            "async def get_last_activity_map(",
            "async def get_last_transition_map(",
            "state_repo.get_last_transition_map(",
        ),
        "forbidden": (),
    },
    "pms/services/goal_service.py": {
        "required": (
            "async def get_objective_last_activity_map(",
            "async def get_last_activity_map(",
            "async def get_objective_last_transition_map(",
            "async def get_last_transition_map(",
        ),
        "forbidden": (),
    },
    "pms/services/project_service.py": {
        "required": (
            "self._task_repo.get_last_activity_map(",
            "self._task_repo.get_last_transition_map(",
            "goal_service.get_last_activity_map(",
            "goal_service.get_last_transition_map(",
        ),
        "forbidden": (),
    },
    "pms/services/plan_service.py": {
        "required": (
            "self._task_repo.get_last_activity_map(",
            "self._task_repo.get_last_transition_map(",
            "project_service.get_last_activity_map(",
            "project_service.get_last_transition_map(",
            "goal_service.get_last_activity_map(",
            "goal_service.get_last_transition_map(",
            "goal_service.get_objective_last_activity_map(",
            "goal_service.get_objective_last_transition_map(",
        ),
        "forbidden": (),
    },
    "pms/services/organization_service.py": {
        "required": (
            "project_service.get_last_activity_map(",
            "project_service.get_last_transition_map(",
            "goal_service.get_last_activity_map(",
            "goal_service.get_last_transition_map(",
            "goal_service.get_objective_last_activity_map(",
            "goal_service.get_objective_last_transition_map(",
        ),
        "forbidden": (),
    },
    "pms/services/portfolio_service.py": {
        "required": (
            "project_service.get_last_activity_map(",
            "project_service.get_last_transition_map(",
            "goal_service.get_last_activity_map(",
            "goal_service.get_last_transition_map(",
            "goal_service.get_objective_last_activity_map(",
            "goal_service.get_objective_last_transition_map(",
        ),
        "forbidden": (),
    },
    "pms/services/program_service.py": {
        "required": (
            "project_service.get_last_activity_map(",
            "project_service.get_last_transition_map(",
            "goal_service.get_last_activity_map(",
            "goal_service.get_last_transition_map(",
            "goal_service.get_objective_last_activity_map(",
            "goal_service.get_objective_last_transition_map(",
        ),
        "forbidden": (),
    },
    "pms/services/lineage_service.py": {
        "required": (
            "self._plan_service.get_last_activity_map(",
            "self._plan_service.get_last_transition_map(",
        ),
        "forbidden": (
            'get_last_transition_map("plan_status",',
            "from pms.repositories.state_transition_repository import StateTransitionRepository",
        ),
    },
    "pms/cli/app.py": {
        "required": (
            "_list_plans_for_display(",
            "service.get_last_transition_map(plan_ids)",
            '"freshest_visible_activity"',
            '"freshest_visible_transition"',
        ),
        "forbidden": (),
    },
}


def audit_source(
    source: str,
    *,
    path: Path,
    required_patterns: tuple[str, ...],
    forbidden_patterns: tuple[str, ...] = (),
) -> tuple[GraphTimestampRollupIssue, ...]:
    issues: list[GraphTimestampRollupIssue] = []
    try:
        relative_file = str(path.relative_to(REPO_ROOT))
    except ValueError:
        relative_file = str(path)

    for pattern in required_patterns:
        if pattern not in source:
            issues.append(
                GraphTimestampRollupIssue(
                    file=relative_file,
                    reason=f"missing required rollup contract snippet: {pattern}",
                )
            )
    for pattern in forbidden_patterns:
        if pattern in source:
            issues.append(
                GraphTimestampRollupIssue(
                    file=relative_file,
                    reason=f"forbidden shallow rollup snippet present: {pattern}",
                )
            )
    return tuple(issues)


def run_audit(root_dir: Path = REPO_ROOT) -> tuple[GraphTimestampRollupIssue, ...]:
    issues: list[GraphTimestampRollupIssue] = []
    for relative_path, contract in ROLLUP_CONTRACTS.items():
        path = root_dir / relative_path
        source = path.read_text(encoding="utf-8")
        issues.extend(
            audit_source(
                source,
                path=path,
                required_patterns=contract["required"],
                forbidden_patterns=contract["forbidden"],
            )
        )
    return tuple(issues)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit deep graph timestamp rollup contracts."
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON payload")
    parser.add_argument("--check", action="store_true", help="Exit non-zero on issues")
    args = parser.parse_args()

    issues = run_audit()
    checked = len(ROLLUP_CONTRACTS)
    if args.json:
        print(
            json.dumps(
                {
                    "checked": checked,
                    "issues": [
                        {
                            "file": issue.file,
                            "reason": issue.reason,
                        }
                        for issue in issues
                    ],
                },
                indent=2,
            )
        )
    else:
        print(f"Graph timestamp rollup audit\nchecked={checked} issues={len(issues)}")
        for issue in issues:
            print(f"- {issue.file}: {issue.reason}")

    if args.check and issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
