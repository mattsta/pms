#!/usr/bin/env python3
"""Audit execution-backed goal rollup specs for stale hierarchy drift."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from scripts.sync_goal_execution_backed_rollups import _load_spec, collect_drift

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_DIR = REPO_ROOT / "scripts" / "specs"


def run_audit() -> tuple[str, ...]:
    issues: list[str] = []
    for spec_path in sorted(SPEC_DIR.glob("*rollups.json")):
        spec = _load_spec(spec_path)
        try:
            drifts = asyncio.run(collect_drift(spec, actor="audit"))
        except LookupError:
            continue
        for drift in drifts:
            issues.append(
                f"{spec_path.name}: {drift.mapping.label} drifted from task "
                f"{drift.task_title} ({drift.task_progress_percent}%/{drift.task_status}) "
                f"to key result {drift.key_result_name} "
                f"({drift.key_result_progress_percent}%/{drift.key_result_status})"
            )
    return tuple(issues)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Exit nonzero when issues are found"
    )
    args = parser.parse_args()

    issues = run_audit()
    payload = {"issue_count": len(issues), "issues": list(issues)}
    print(json.dumps(payload, indent=2))
    return 1 if args.check and issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
