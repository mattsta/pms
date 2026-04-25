#!/usr/bin/env python3
"""Audit tracked secret-bearing files that must stay local-only."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DISALLOWED_TRACKED_PATHS = (
    ".pms-admin-key",
    ".env",
    ".env.local",
)


def run_audit() -> tuple[str, ...]:
    process = subprocess.run(
        ["git", "ls-files", "--", *DISALLOWED_TRACKED_PATHS],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if process.returncode != 0:
        message = (
            process.stderr.strip() or process.stdout.strip() or "git ls-files failed"
        )
        return (f"unable to audit tracked secrets: {message}",)

    tracked = tuple(
        line.strip() for line in process.stdout.splitlines() if line.strip()
    )
    return tuple(
        f"tracked secret file must be removed from git index: {path}"
        for path in tracked
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Exit nonzero when issues are found"
    )
    args = parser.parse_args()

    issues = run_audit()
    if issues:
        for issue in issues:
            print(issue, file=sys.stderr)
        return 1 if args.check else 0

    print("tracked_secret_issues=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
