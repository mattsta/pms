#!/usr/bin/env python3
"""Audit maintained client operator-surface method semantics."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class ClientOperatorSurfaceIssue:
    file: str
    reason: str


CLIENT_OPERATOR_SURFACE_CONTRACTS: dict[str, dict[str, tuple[str, ...]]] = {
    "pms/client/http_client.py": {
        "required": (
            "async def get_dashboard(self) -> dict[str, Any]:",
            'response = await client.get("/api/v1/dashboard")',
            "async def get_dashboard_html(self) -> str:",
            'response = await client.get("/dashboard")',
            "async def get_organization_dashboard(",
            '"/api/v1/organizations/dashboard",',
            "async def get_portfolio_dashboard(",
            '"/api/v1/portfolios/dashboard",',
            "async def get_program_dashboard(",
            '"/api/v1/programs/dashboard",',
        ),
        "forbidden": (),
    },
    "client-rust/src/client.rs": {
        "required": (
            "pub async fn get_dashboard(&self) -> Result<Value> {",
            '.get(format!("{}/api/v1/dashboard", self.base_url))',
            "pub async fn get_dashboard_html(&self) -> Result<String> {",
            '.get(format!("{}/dashboard", self.base_url))',
            "pub async fn get_organization_dashboard(",
            '"{}/api/v1/organizations/dashboard{}",',
            "pub async fn get_portfolio_dashboard(",
            '"{}/api/v1/portfolios/dashboard{}",',
            "pub async fn get_program_dashboard(",
            '"{}/api/v1/programs/dashboard{}",',
        ),
        "forbidden": ("pub async fn get_dashboard(&self) -> Result<String> {",),
    },
}


def audit_source(
    source: str,
    *,
    path: Path,
    required_patterns: tuple[str, ...],
    forbidden_patterns: tuple[str, ...] = (),
) -> tuple[ClientOperatorSurfaceIssue, ...]:
    issues: list[ClientOperatorSurfaceIssue] = []
    try:
        relative_file = str(path.relative_to(REPO_ROOT))
    except ValueError:
        relative_file = str(path)

    for pattern in required_patterns:
        if pattern not in source:
            issues.append(
                ClientOperatorSurfaceIssue(
                    file=relative_file,
                    reason=f"missing required client contract snippet: {pattern}",
                )
            )
    for pattern in forbidden_patterns:
        if pattern in source:
            issues.append(
                ClientOperatorSurfaceIssue(
                    file=relative_file,
                    reason=f"forbidden client contract snippet present: {pattern}",
                )
            )
    return tuple(issues)


def run_audit(root_dir: Path = REPO_ROOT) -> tuple[ClientOperatorSurfaceIssue, ...]:
    issues: list[ClientOperatorSurfaceIssue] = []
    for relative_path, contract in CLIENT_OPERATOR_SURFACE_CONTRACTS.items():
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
        description="Audit maintained client operator-surface contracts."
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON payload")
    parser.add_argument("--check", action="store_true", help="Exit non-zero on issues")
    args = parser.parse_args()

    issues = run_audit()
    checked = len(CLIENT_OPERATOR_SURFACE_CONTRACTS)
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
            "Client operator surface contract audit\n"
            f"checked={checked} issues={len(issues)}"
        )
        for issue in issues:
            print(f"- {issue.file}: {issue.reason}")

    if args.check and issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
