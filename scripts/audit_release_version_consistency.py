#!/usr/bin/env python3
"""Audit release-facing version surfaces for consistency."""

from __future__ import annotations

import argparse
import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CHANGELOG_PENDING_LABEL = "Pending public release cut"
ISO_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class ReleaseVersionIssue:
    file: str
    line: int
    reason: str


def _relative_file(path: Path, root_dir: Path) -> str:
    try:
        return str(path.relative_to(root_dir))
    except ValueError:
        return str(path)


def _toml_version(path: Path, *keys: str) -> str:
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    value = payload
    for key in keys:
        value = value[key]
    if not isinstance(value, str):
        raise TypeError(f"{path} {'/'.join(keys)} did not resolve to a string")
    return value


def _regex_value(
    path: Path,
    pattern: re.Pattern[str],
    *,
    root_dir: Path,
    reason: str,
) -> tuple[str | None, ReleaseVersionIssue | None]:
    source = path.read_text(encoding="utf-8")
    match = pattern.search(source)
    if match is None:
        return None, ReleaseVersionIssue(
            file=_relative_file(path, root_dir),
            line=1,
            reason=reason,
        )
    return match.group("value"), None


def run_audit(*, root_dir: Path = REPO_ROOT) -> tuple[ReleaseVersionIssue, ...]:
    issues: list[ReleaseVersionIssue] = []

    pyproject_path = root_dir / "pyproject.toml"
    expected_version = _toml_version(pyproject_path, "project", "version")

    version_sources: tuple[tuple[Path, str], ...] = (
        (
            root_dir / "client-rust" / "Cargo.toml",
            _toml_version(
                root_dir / "client-rust" / "Cargo.toml", "package", "version"
            ),
        ),
    )

    regex_sources: tuple[tuple[Path, re.Pattern[str], str], ...] = (
        (
            root_dir / "pms" / "__init__.py",
            re.compile(r'^__version__\s*=\s*"(?P<value>[^"]+)"', re.MULTILINE),
            "missing __version__ declaration",
        ),
        (
            root_dir / "docs" / "CAPABILITIES_REFERENCE.md",
            re.compile(r"^\*\*Version:\*\*\s+(?P<value>\S+)", re.MULTILINE),
            "missing capabilities reference version line",
        ),
        (
            root_dir / "docs" / "SERVER_DEPLOYMENT.md",
            re.compile(r"^\*\*Version\*\*:\s+(?P<value>\S+)", re.MULTILINE),
            "missing server deployment version line",
        ),
    )

    for path, actual_version in version_sources:
        if actual_version != expected_version:
            issues.append(
                ReleaseVersionIssue(
                    file=_relative_file(path, root_dir),
                    line=1,
                    reason=(
                        f"version {actual_version!r} does not match project version "
                        f"{expected_version!r}"
                    ),
                )
            )

    for path, pattern, missing_reason in regex_sources:
        actual_version, issue = _regex_value(
            path,
            pattern,
            root_dir=root_dir,
            reason=missing_reason,
        )
        if issue is not None:
            issues.append(issue)
            continue
        assert actual_version is not None
        if actual_version != expected_version:
            issues.append(
                ReleaseVersionIssue(
                    file=_relative_file(path, root_dir),
                    line=1,
                    reason=(
                        f"version {actual_version!r} does not match project version "
                        f"{expected_version!r}"
                    ),
                )
            )

    changelog_path = root_dir / "CHANGELOG.md"
    if changelog_path.is_file():
        changelog_source = changelog_path.read_text(encoding="utf-8")
        changelog_pattern = re.compile(
            rf"^## \[{re.escape(expected_version)}\] - (?P<value>.+)$",
            re.MULTILINE,
        )
        changelog_match = changelog_pattern.search(changelog_source)
        if changelog_match is None:
            issues.append(
                ReleaseVersionIssue(
                    file=_relative_file(changelog_path, root_dir),
                    line=1,
                    reason=f"missing changelog entry for version {expected_version!r}",
                )
            )
        else:
            release_label = changelog_match.group("value").strip()
            if (
                release_label != CHANGELOG_PENDING_LABEL
                and ISO_DATE_PATTERN.fullmatch(release_label) is None
            ):
                line = changelog_source.count("\n", 0, changelog_match.start()) + 1
                issues.append(
                    ReleaseVersionIssue(
                        file=_relative_file(changelog_path, root_dir),
                        line=line,
                        reason=(
                            "changelog release label must be an ISO date or "
                            f"{CHANGELOG_PENDING_LABEL!r}, found {release_label!r}"
                        ),
                    )
                )

    return tuple(issues)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit release-facing version surfaces for consistency."
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON payload")
    parser.add_argument("--check", action="store_true", help="Exit non-zero on issues")
    args = parser.parse_args()

    issues = run_audit()
    checked = 5 + int((REPO_ROOT / "CHANGELOG.md").is_file())
    if args.json:
        print(
            json.dumps(
                {
                    "checked": checked,
                    "issues": [
                        {
                            "file": issue.file,
                            "line": issue.line,
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
            f"Release version consistency audit\nchecked={checked} issues={len(issues)}"
        )
        for issue in issues:
            print(f"- {issue.file}:{issue.line} {issue.reason}")

    if args.check and issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
