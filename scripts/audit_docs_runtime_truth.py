"""Audit key user guides for runtime-truth mutation guidance."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_DOC_RULES: dict[str, tuple[str, ...]] = {
    "README.md": (
        "runtime_write",
        "Text mutation output intentionally omits successful runtime plumbing",
    ),
    "docs/IMMEDIATE_START_GO.md": (
        "runtime_write",
        "use JSON output",
        "prefer_server",
    ),
    "docs/CLIENT_GUIDE.md": (
        "runtime_write",
        "write_path",
        "target_location",
    ),
    "docs/WRITE_COORDINATION_ARCHITECTURE.md": (
        "Mutation Truth Contract",
        "runtime_write",
        "text mutation output suppresses successful runtime plumbing",
    ),
    "SKILL.md": (
        "runtime_write",
        "successful runtime plumbing is intentionally omitted",
        "write_mode",
    ),
}


@dataclass(frozen=True)
class DocsRuntimeTruthIssue:
    path: str
    reason: str


def run_audit() -> tuple[DocsRuntimeTruthIssue, ...]:
    issues: list[DocsRuntimeTruthIssue] = []
    for relative_path, required_terms in REQUIRED_DOC_RULES.items():
        path = REPO_ROOT / relative_path
        if not path.is_file():
            issues.append(DocsRuntimeTruthIssue(relative_path, "missing file"))
            continue
        text = path.read_text(encoding="utf-8")
        for term in required_terms:
            if term not in text:
                issues.append(
                    DocsRuntimeTruthIssue(
                        relative_path,
                        f"missing required runtime-truth term: {term}",
                    )
                )
    return tuple(issues)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit key docs for runtime-truth mutation guidance."
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON payload")
    parser.add_argument("--check", action="store_true", help="Exit non-zero on issues")
    args = parser.parse_args()

    issues = run_audit()
    if args.json:
        print(
            json.dumps(
                {
                    "checked": len(REQUIRED_DOC_RULES),
                    "issues": [
                        {"path": issue.path, "reason": issue.reason} for issue in issues
                    ],
                },
                indent=2,
            )
        )
    else:
        print(
            "Docs runtime-truth audit\n"
            f"checked={len(REQUIRED_DOC_RULES)} issues={len(issues)}"
        )
        for issue in issues:
            print(f"- {issue.path}: {issue.reason}")

    if args.check and issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
