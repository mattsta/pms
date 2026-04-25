#!/usr/bin/env python3
"""Audit local-server default URL consistency across docs and client surfaces."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path

from pms.runtime.defaults import LOCAL_SERVER_DEFAULT_BASE_URL

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class LocalServerSurfaceIssue:
    file: str
    line: int
    reason: str


def _relative_file(path: Path, root_dir: Path) -> str:
    try:
        return str(path.relative_to(root_dir))
    except ValueError:
        return str(path)


def _line_for_index(source: str, index: int) -> int:
    return source.count("\n", 0, index) + 1


REQUIRED_SNIPPETS: dict[str, tuple[tuple[str, str], ...]] = {
    "docs/WEB_API.md": (
        (f"{LOCAL_SERVER_DEFAULT_BASE_URL}/docs", "missing default docs URL"),
        (
            f"{LOCAL_SERVER_DEFAULT_BASE_URL}/api/v1/health",
            "missing default health URL",
        ),
        ("PMS_DATABASE_PATH=postgresql://", "missing PMS_DATABASE_PATH example"),
        ("PMS_SERVER_BASE_URL", "missing PMS_SERVER_BASE_URL guidance"),
    ),
    "docs/API_REFERENCE.md": (
        (LOCAL_SERVER_DEFAULT_BASE_URL, "missing default API base URL"),
        ("PMS_DATABASE_PATH=postgresql://", "missing PMS_DATABASE_PATH example"),
        ("PMS_SERVER_BASE_URL", "missing PMS_SERVER_BASE_URL guidance"),
    ),
    "docs/DASHBOARD_USAGE.md": (
        (
            f"{LOCAL_SERVER_DEFAULT_BASE_URL}/dashboard",
            "missing default dashboard URL",
        ),
    ),
    "docs/CLIENT_GUIDE.md": (
        (
            f'base_url="{LOCAL_SERVER_DEFAULT_BASE_URL}"',
            "missing default Python client base URL",
        ),
    ),
    "docs/WRITE_COORDINATION_ARCHITECTURE.md": (
        (LOCAL_SERVER_DEFAULT_BASE_URL, "missing default delegated server URL"),
    ),
    "examples/real_world/README.md": (
        (
            f"{LOCAL_SERVER_DEFAULT_BASE_URL}/api/v1/observability/overview",
            "missing default observability overview URL",
        ),
    ),
    "docs/END_TO_END_WORKFLOWS.md": (
        (
            f"{LOCAL_SERVER_DEFAULT_BASE_URL}/api/v1/tasks",
            "missing default task API example URL",
        ),
    ),
    "client-rust/README.md": (
        (LOCAL_SERVER_DEFAULT_BASE_URL, "missing default Rust client server URL"),
    ),
    "pms/config/settings.py": (
        (
            "LOCAL_SERVER_DEFAULT_BASE_URL",
            "settings must derive the default server URL from shared runtime defaults",
        ),
    ),
    "pms/client/cli.py": (
        (
            "LOCAL_SERVER_DEFAULT_BASE_URL",
            "client CLI must derive the default server URL from shared runtime defaults",
        ),
    ),
    "pms/client/http_client.py": (
        (
            "LOCAL_SERVER_DEFAULT_BASE_URL",
            "HTTP client must derive the default server URL from shared runtime defaults",
        ),
    ),
    "pms/api/app.py": (
        (
            'print("📚 API docs: /docs")',
            "startup banner must avoid stale absolute URLs",
        ),
    ),
}

FORBIDDEN_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"localhost:8000"),
        "stale localhost:8000 default URL remains",
    ),
    (
        re.compile(r"127\.0\.0\.1:8000"),
        "stale 127.0.0.1:8000 default URL remains",
    ),
    (
        re.compile(r"^DATABASE_URL=", re.MULTILINE),
        "stale DATABASE_URL guidance remains; use PMS_DATABASE_PATH",
    ),
)


def run_audit(*, root_dir: Path = REPO_ROOT) -> tuple[LocalServerSurfaceIssue, ...]:
    issues: list[LocalServerSurfaceIssue] = []

    for relative_path, snippets in REQUIRED_SNIPPETS.items():
        path = root_dir / relative_path
        source = path.read_text(encoding="utf-8")

        for needle, reason in snippets:
            index = source.find(needle)
            if index != -1:
                continue
            issues.append(
                LocalServerSurfaceIssue(
                    file=_relative_file(path, root_dir),
                    line=1,
                    reason=reason,
                )
            )

        for pattern, reason in FORBIDDEN_PATTERNS:
            match = pattern.search(source)
            if match is None:
                continue
            issues.append(
                LocalServerSurfaceIssue(
                    file=_relative_file(path, root_dir),
                    line=_line_for_index(source, match.start()),
                    reason=reason,
                )
            )

    return tuple(issues)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Audit local-server default URL consistency across operator docs and "
            "client/config surfaces."
        )
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON payload")
    parser.add_argument("--check", action="store_true", help="Exit non-zero on issues")
    args = parser.parse_args()

    issues = run_audit()
    checked = sum(len(snippets) for snippets in REQUIRED_SNIPPETS.values()) + (
        len(REQUIRED_SNIPPETS) * len(FORBIDDEN_PATTERNS)
    )
    if args.json:
        print(
            json.dumps(
                {
                    "checked": checked,
                    "issues": [
                        {"file": issue.file, "line": issue.line, "reason": issue.reason}
                        for issue in issues
                    ],
                },
                indent=2,
            )
        )
    else:
        print(
            f"Local server surface truth audit\nchecked={checked} issues={len(issues)}"
        )
        for issue in issues:
            print(f"- {issue.file}:{issue.line} {issue.reason}")

    if args.check and issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
