#!/usr/bin/env python3
"""Audit service-layer mutation methods for explicit outer transaction ownership."""

from __future__ import annotations

import argparse
import ast
import json
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SERVICES_DIR = REPO_ROOT / "pms" / "services"
MUTATION_PREFIXES: tuple[str, ...] = (
    "create",
    "update",
    "delete",
    "archive",
    "restore",
    "add",
    "remove",
    "run",
    "mark",
    "complete",
    "assign",
    "record",
    "set",
    "sync",
    "execute",
    "upsert",
    "replace",
    "prune",
    "expire",
    "renew",
    "release",
    "force",
)
DB_MUTATION_METHODS: frozenset[str] = frozenset(
    {"execute", "execute_update", "execute_many"}
)
EXEMPT_METHODS: frozenset[tuple[str, str]] = frozenset(
    {
        ("pms/services/agent_loop_service.py", "run_loop"),
    }
)


@dataclass(frozen=True)
class ServiceTransactionBoundaryIssue:
    file: str
    line: int
    method: str
    mutation_calls: tuple[str, ...]
    reason: str


def _normalized_name(name: str) -> str:
    return name.lstrip("_")


def _is_mutation_name(name: str) -> bool:
    normalized = _normalized_name(name)
    return any(normalized.startswith(prefix) for prefix in MUTATION_PREFIXES)


def _attribute_chain(expr: ast.AST) -> list[str] | None:
    parts: list[str] = []
    current = expr
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
        return list(reversed(parts))
    return None


def _has_explicit_transaction(fn: ast.AsyncFunctionDef) -> bool:
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        chain = _attribute_chain(node.func)
        if chain and chain[0] == "self" and chain[-1] == "transaction":
            return True
    return False


def _collect_mutation_calls(fn: ast.AsyncFunctionDef) -> tuple[str, ...]:
    mutation_calls: set[str] = set()
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        chain = _attribute_chain(node.func)
        if not chain or chain[0] != "self":
            continue
        if len(chain) == 2:
            method_name = chain[1]
            if _is_mutation_name(method_name):
                mutation_calls.add(f"self.{method_name}")
            continue

        owner = chain[1]
        method_name = chain[-1]
        if owner == "db" and method_name in DB_MUTATION_METHODS:
            mutation_calls.add(f"self.db.{method_name}")
            continue
        if (
            owner.endswith("_repo") or owner.endswith("_service")
        ) and _is_mutation_name(method_name):
            mutation_calls.add(f"self.{owner}.{method_name}")
    return tuple(sorted(mutation_calls))


def audit_service_source(
    source: str,
    *,
    path: Path,
) -> tuple[ServiceTransactionBoundaryIssue, ...]:
    issues: list[ServiceTransactionBoundaryIssue] = []
    module = ast.parse(source)
    for node in module.body:
        if not isinstance(node, ast.ClassDef):
            continue
        for fn in node.body:
            if not isinstance(fn, ast.AsyncFunctionDef):
                continue
            if not _is_mutation_name(fn.name):
                continue
            try:
                relative_file = str(path.relative_to(REPO_ROOT))
            except ValueError:
                relative_file = str(path)
            if (relative_file, fn.name) in EXEMPT_METHODS:
                continue
            if fn.name.endswith("_in_transaction"):
                continue
            mutation_calls = _collect_mutation_calls(fn)
            if len(mutation_calls) < 2:
                continue
            if _has_explicit_transaction(fn):
                continue
            issues.append(
                ServiceTransactionBoundaryIssue(
                    file=relative_file,
                    line=fn.lineno,
                    method=fn.name,
                    mutation_calls=mutation_calls,
                    reason=(
                        "mutation method performs multiple mutation-like calls "
                        "without an explicit outer transaction"
                    ),
                )
            )
    return tuple(issues)


def run_audit() -> tuple[ServiceTransactionBoundaryIssue, ...]:
    issues: list[ServiceTransactionBoundaryIssue] = []
    for path in sorted(SERVICES_DIR.glob("*.py")):
        issues.extend(audit_service_source(path.read_text(), path=path))
    return tuple(issues)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit service-layer transaction ownership boundaries."
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON payload")
    parser.add_argument("--check", action="store_true", help="Exit non-zero on issues")
    args = parser.parse_args()

    issues = run_audit()
    if args.json:
        print(
            json.dumps(
                {
                    "checked": len(tuple(SERVICES_DIR.glob("*.py"))),
                    "issues": [
                        {
                            "file": issue.file,
                            "line": issue.line,
                            "method": issue.method,
                            "mutation_calls": list(issue.mutation_calls),
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
            "Service transaction boundary audit\n"
            f"checked={len(tuple(SERVICES_DIR.glob('*.py')))} issues={len(issues)}"
        )
        for issue in issues:
            calls = ", ".join(issue.mutation_calls)
            print(
                f"- {issue.file}:{issue.line} {issue.method}: {issue.reason} [{calls}]"
            )

    if args.check and issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
