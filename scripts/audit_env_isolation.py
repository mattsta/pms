"""Audit maintained shell harnesses for isolated PMS env-file binding."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES: dict[str, tuple[str, ...]] = {
    "scripts/lib/run_helpers.sh": (
        'export PMS_ENV_FILE="${PMS_ENV_FILE:-$PMS_DATA_DIR/.env}"',
    ),
    "scripts/run_audit_checks.sh": (
        'export PMS_ENV_FILE="${PMS_ENV_FILE:-$PMS_DATA_DIR/.env}"',
    ),
    "scripts/run_demo_smoke.sh": (
        'export PMS_ENV_FILE="${PMS_ENV_FILE:-$PMS_DATA_DIR/.env}"',
    ),
    "scripts/run_docs_smoke.sh": (
        'export PMS_ENV_FILE="${PMS_ENV_FILE:-$PMS_DATA_DIR/.env}"',
    ),
    "scripts/run_demo_suite.sh": (
        'export PMS_ENV_FILE="${PMS_ENV_FILE:-$PMS_DATA_DIR/.env}"',
    ),
    "scripts/run_authoring_reliability_smoke.sh": (
        'export PMS_ENV_FILE="${PMS_ENV_FILE:-$PMS_DATA_DIR/.env}"',
    ),
    "scripts/run_agent_execution_loop_flow.sh": (
        "PMS_ENV_FILE=$(printf '%q' \"${PMS_ENV_FILE:-$PMS_DATA_DIR/.env}\")",
    ),
}


@dataclass(frozen=True)
class EnvIsolationIssue:
    path: str
    reason: str


def run_audit() -> tuple[EnvIsolationIssue, ...]:
    issues: list[EnvIsolationIssue] = []
    for relative_path, required_terms in REQUIRED_FILES.items():
        path = REPO_ROOT / relative_path
        if not path.is_file():
            issues.append(EnvIsolationIssue(relative_path, "missing file"))
            continue
        text = path.read_text(encoding="utf-8")
        for term in required_terms:
            if term not in text:
                issues.append(
                    EnvIsolationIssue(
                        relative_path,
                        f"missing required env-isolation term: {term}",
                    )
                )
    return tuple(issues)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit maintained shell harnesses for isolated PMS env binding."
    )
    parser.add_argument("--check", action="store_true", help="Exit non-zero on issues")
    parser.add_argument("--json", action="store_true", help="Emit JSON payload")
    args = parser.parse_args()

    issues = run_audit()
    if args.json:
        print(
            json.dumps(
                {
                    "checked": len(REQUIRED_FILES),
                    "issues": [
                        {"path": issue.path, "reason": issue.reason} for issue in issues
                    ],
                },
                indent=2,
            )
        )
    else:
        print(
            f"Env isolation audit\nchecked={len(REQUIRED_FILES)} issues={len(issues)}"
        )
        for issue in issues:
            print(f"- {issue.path}: {issue.reason}")

    if args.check and issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
