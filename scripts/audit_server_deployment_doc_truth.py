#!/usr/bin/env python3
"""Audit deployment-guide claims against the live PMS server/runtime contract."""

from __future__ import annotations

import argparse
import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class ServerDeploymentDocIssue:
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


def _find_constant(path: Path, pattern: re.Pattern[str]) -> str:
    match = pattern.search(path.read_text(encoding="utf-8"))
    if match is None:
        raise ValueError(f"missing expected pattern in {path}")
    return match.group("value")


def _find_default_port(root_dir: Path) -> str:
    defaults_path = root_dir / "pms" / "runtime" / "defaults.py"
    if defaults_path.exists():
        try:
            return _find_constant(
                defaults_path,
                re.compile(
                    r"^LOCAL_SERVER_DEFAULT_PORT = (?P<value>\d+)$", re.MULTILINE
                ),
            )
        except ValueError:
            pass

    cli_app_path = root_dir / "pms" / "cli" / "app.py"
    return _find_constant(
        cli_app_path,
        re.compile(r"^LOCAL_RUNTIME_DEFAULT_PORT = (?P<value>\d+)$", re.MULTILINE),
    )


def run_audit(*, root_dir: Path = REPO_ROOT) -> tuple[ServerDeploymentDocIssue, ...]:
    issues: list[ServerDeploymentDocIssue] = []

    doc_path = root_dir / "docs" / "SERVER_DEPLOYMENT.md"
    source = doc_path.read_text(encoding="utf-8")

    expected_version = tomllib.loads(
        (root_dir / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]["version"]
    if not isinstance(expected_version, str):
        raise TypeError("pyproject.toml project.version must be a string")

    default_port = _find_default_port(root_dir)

    version_match = re.search(
        r"^\*\*Version\*\*:\s+(?P<value>\S+)", source, re.MULTILINE
    )
    if version_match is None:
        issues.append(
            ServerDeploymentDocIssue(
                file=_relative_file(doc_path, root_dir),
                line=1,
                reason="missing version line",
            )
        )
    elif version_match.group("value") != expected_version:
        issues.append(
            ServerDeploymentDocIssue(
                file=_relative_file(doc_path, root_dir),
                line=_line_for_index(source, version_match.start()),
                reason=(
                    f"version {version_match.group('value')!r} does not match project "
                    f"version {expected_version!r}"
                ),
            )
        )

    required_snippets = (
        (f"http://127.0.0.1:{default_port}/docs", "missing default local docs URL"),
        (
            f"http://127.0.0.1:{default_port}/openapi.json",
            "missing default local OpenAPI URL",
        ),
        (
            f"http://127.0.0.1:{default_port}/dashboard",
            "missing default local dashboard URL",
        ),
        (
            f"http://127.0.0.1:{default_port}/api/v1/health",
            "missing default local health URL",
        ),
        ("PMS_DATA_DIR", "missing PMS_DATA_DIR guidance"),
        ("PMS_DATABASE_PATH", "missing PMS_DATABASE_PATH guidance"),
        ("PMS_WRITE_MODE", "missing PMS_WRITE_MODE guidance"),
        ("PMS_SERVER_BASE_URL", "missing PMS_SERVER_BASE_URL guidance"),
        ("uv run pms auth init --show-key", "missing auth bootstrap command"),
        ("X-API-Key", "missing API key header guidance"),
        ("docs/API_ENDPOINT_CATALOG.md", "missing endpoint-catalog reference"),
        (
            "docs/WRITE_COORDINATION_ARCHITECTURE.md",
            "missing write-coordination reference",
        ),
        (
            "PMS_DATABASE_PATH=postgresql://",
            "missing PostgreSQL example using PMS_DATABASE_PATH",
        ),
    )

    for needle, reason in required_snippets:
        index = source.find(needle)
        if index == -1:
            issues.append(
                ServerDeploymentDocIssue(
                    file=_relative_file(doc_path, root_dir),
                    line=1,
                    reason=reason,
                )
            )

    forbidden_patterns: tuple[tuple[re.Pattern[str], str], ...] = (
        (
            re.compile(r"\b\d+\s+API Endpoints\b"),
            "deployment guide must not hardcode endpoint counts",
        ),
        (
            re.compile(r"\b100\+\s+simultaneous requests\b"),
            "deployment guide must not claim unsupported concurrency benchmarks",
        ),
        (
            re.compile(r"~50ms \(p99\)"),
            "deployment guide must not claim unsupported latency benchmarks",
        ),
        (
            re.compile(r"\b100\+\s+req/s\b"),
            "deployment guide must not claim unsupported throughput benchmarks",
        ),
        (
            re.compile(r"\b10-50 connections\b"),
            "deployment guide must not claim unsupported pool-sizing guidance as fact",
        ),
        (
            re.compile(r"\bBuilt-in MetricsCollector\b"),
            "deployment guide must not claim built-in monitoring components that are not documented elsewhere as authoritative runtime contracts",
        ),
        (
            re.compile(r"\bProduction deployment ready\b"),
            "deployment guide must not claim release/hardening readiness as a fixed fact",
        ),
        (
            re.compile(r"^DATABASE_URL=", re.MULTILINE),
            "deployment guide must use PMS_DATABASE_PATH rather than DATABASE_URL",
        ),
        (
            re.compile(r"^API_HOST=", re.MULTILINE),
            "deployment guide must not document non-existent API_HOST env usage",
        ),
        (
            re.compile(r"^API_PORT=", re.MULTILINE),
            "deployment guide must not document non-existent API_PORT env usage",
        ),
    )

    for pattern, reason in forbidden_patterns:
        match = pattern.search(source)
        if match is None:
            continue
        issues.append(
            ServerDeploymentDocIssue(
                file=_relative_file(doc_path, root_dir),
                line=_line_for_index(source, match.start()),
                reason=reason,
            )
        )

    return tuple(issues)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit the server deployment guide against the live PMS contract."
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON payload")
    parser.add_argument("--check", action="store_true", help="Exit non-zero on issues")
    args = parser.parse_args()

    issues = run_audit()
    checked = 24
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
            f"Server deployment doc truth audit\nchecked={checked} issues={len(issues)}"
        )
        for issue in issues:
            print(f"- {issue.file}:{issue.line} {issue.reason}")

    if args.check and issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
