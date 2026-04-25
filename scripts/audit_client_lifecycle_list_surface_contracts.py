#!/usr/bin/env python3
"""Audit maintained client lifecycle list source contracts."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

from scripts.source_contract_audit_utils import (
    SourceBlockContract,
    audit_block_contracts,
)


@dataclass(frozen=True)
class ClientLifecycleListSurfaceIssue:
    file: str
    reason: str


CLIENT_LIFECYCLE_LIST_SURFACE_CONTRACTS: dict[str, tuple[SourceBlockContract, ...]] = {
    "pms/client/http_client.py": (
        SourceBlockContract(
            anchor="async def list_tasks(",
            block_kind="python_def",
            required=(
                "project_id: str | None = None,",
                "status: str | None = None,",
                "limit: int = 100,",
                "offset: int = 0,",
                '"/api/v1/tasks",',
                '"project_id": project_id,',
                '"status": status,',
                '"limit": limit,',
                '"offset": offset,',
            ),
        ),
        SourceBlockContract(
            anchor="async def list_plans(",
            block_kind="python_def",
            required=(
                "task_id: str | None = None,",
                '"/api/v1/plans",',
                '"task_id": task_id,',
                '"limit": limit,',
                '"offset": offset,',
            ),
        ),
    ),
    "client-rust/src/client.rs": (
        SourceBlockContract(
            anchor="pub(crate) fn task_list_query_params(",
            required=(
                "status: Option<&str>,",
                "limit: Option<u32>,",
                "offset: Option<u32>,",
                'params.push(("status", value.to_string()));',
                'params.push(("limit", value.to_string()));',
                'params.push(("offset", value.to_string()));',
            ),
        ),
        SourceBlockContract(
            anchor="pub async fn list_tasks(",
            required=(
                "status: Option<&str>,",
                "limit: Option<u32>,",
                "offset: Option<u32>,",
                "let params = task_list_query_params(project_id, status, limit, offset);",
                '.get(format!("{}/api/v1/tasks", self.base_url))',
                ".query(&params)",
            ),
        ),
        SourceBlockContract(
            anchor="pub(crate) fn plan_list_query_params(",
            required=(
                "task_id: Option<&str>,",
                'params.push(("task_id", value.to_string()));',
                'params.push(("limit", value.to_string()));',
                'params.push(("offset", value.to_string()));',
            ),
        ),
        SourceBlockContract(
            anchor="pub async fn list_plans(",
            required=(
                "task_id: Option<&str>,",
                "let params = plan_list_query_params(",
                "task_id,",
                '.get(format!("{}/api/v1/plans", self.base_url))',
                ".query(&params)",
            ),
        ),
    ),
    "client-rust/src/main.rs": (
        SourceBlockContract(
            anchor="/// List tasks\n    List {",
            required=(
                "#[arg(long)]\n        status: Option<String>,",
                '#[arg(long, default_value = "100")]\n        limit: u32,',
                '#[arg(long, default_value = "0")]\n        offset: u32,',
            ),
        ),
        SourceBlockContract(
            anchor="TaskCommands::List {",
            block_kind="match_arm",
            required=(
                "status,",
                "limit,",
                "offset,",
                "handle_task_list(",
                "project, project_id, status, limit, offset, &format, api_key,",
            ),
        ),
        SourceBlockContract(
            anchor="/// List plans\n    List {",
            required=(
                "#[arg(long)]\n        task_id: Option<String>,",
                '#[arg(long, default_value = "100")]\n        limit: u32,',
                '#[arg(long, default_value = "0")]\n        offset: u32,',
            ),
        ),
        SourceBlockContract(
            anchor="PlanCommands::List {",
            block_kind="match_arm",
            required=(
                "task_id,",
                "limit,",
                "offset,",
                "handle_plan_list(",
                "task_id,",
                "Some(limit),",
                "Some(offset),",
            ),
        ),
    ),
}


def audit_source(
    source: str,
    *,
    path: Path,
    block_contracts: tuple[SourceBlockContract, ...],
) -> tuple[ClientLifecycleListSurfaceIssue, ...]:
    issues: list[ClientLifecycleListSurfaceIssue] = []
    try:
        relative_file = str(path.relative_to(REPO_ROOT))
    except ValueError:
        relative_file = str(path)

    for reason in audit_block_contracts(
        source,
        block_contracts=block_contracts,
        contract_label="lifecycle-list contract",
    ):
        issues.append(
            ClientLifecycleListSurfaceIssue(file=relative_file, reason=reason)
        )
    return tuple(issues)


def run_audit(
    root_dir: Path = REPO_ROOT,
) -> tuple[ClientLifecycleListSurfaceIssue, ...]:
    issues: list[ClientLifecycleListSurfaceIssue] = []
    for (
        relative_path,
        block_contracts,
    ) in CLIENT_LIFECYCLE_LIST_SURFACE_CONTRACTS.items():
        path = root_dir / relative_path
        source = path.read_text(encoding="utf-8")
        issues.extend(
            audit_source(
                source,
                path=path,
                block_contracts=block_contracts,
            )
        )
    return tuple(issues)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit maintained client lifecycle list source contracts."
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON payload")
    parser.add_argument("--check", action="store_true", help="Exit non-zero on issues")
    args = parser.parse_args()

    issues = run_audit()
    checked = len(CLIENT_LIFECYCLE_LIST_SURFACE_CONTRACTS)
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
        print(
            "Client lifecycle list surface contract audit\n"
            f"checked={checked} issues={len(issues)}"
        )
        for issue in issues:
            print(f"- {issue.file}: {issue.reason}")

    if args.check and issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
