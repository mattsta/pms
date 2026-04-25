#!/usr/bin/env python3
"""Audit CLI JSON branches for accidental rich console rendering."""

from __future__ import annotations

import argparse
import ast
import json
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CLI_APP_PATH = Path("pms/cli/app.py")


@dataclass(frozen=True)
class CliJsonOutputIssue:
    file: str
    function: str
    line: int
    reason: str


def _relative_file(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _is_output_format_name(node: ast.AST) -> bool:
    return isinstance(node, ast.Name) and node.id == "output_format"


def _is_json_constant(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value == "json"


def _is_json_branch_test(node: ast.AST) -> bool:
    if isinstance(node, ast.BoolOp):
        return any(_is_json_branch_test(value) for value in node.values)
    if not isinstance(node, ast.Compare):
        return False
    if len(node.ops) != 1 or len(node.comparators) != 1:
        return False
    if not isinstance(node.ops[0], ast.Eq):
        return False
    left = node.left
    right = node.comparators[0]
    return (_is_output_format_name(left) and _is_json_constant(right)) or (
        _is_json_constant(left) and _is_output_format_name(right)
    )


def _console_method_name(node: ast.Call) -> str | None:
    if not isinstance(node.func, ast.Attribute):
        return None
    owner = node.func.value
    if not isinstance(owner, ast.Name) or owner.id != "console":
        return None
    return node.func.attr


class _JsonBranchConsoleVisitor(ast.NodeVisitor):
    def __init__(self, *, relative_file: str) -> None:
        self.relative_file = relative_file
        self.function_stack: list[str] = []
        self.json_branch_depth = 0
        self.issues: list[CliJsonOutputIssue] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.function_stack.append(node.name)
        self.generic_visit(node)
        self.function_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.function_stack.append(node.name)
        self.generic_visit(node)
        self.function_stack.pop()

    def visit_If(self, node: ast.If) -> None:
        if _is_json_branch_test(node.test):
            self.json_branch_depth += 1
            for statement in node.body:
                self.visit(statement)
            self.json_branch_depth -= 1
            for statement in node.orelse:
                self.visit(statement)
            return
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if self.json_branch_depth > 0:
            method_name = _console_method_name(node)
            if method_name is not None:
                self.issues.append(
                    CliJsonOutputIssue(
                        file=self.relative_file,
                        function=self.function_stack[-1]
                        if self.function_stack
                        else "<module>",
                        line=node.lineno,
                        reason=(
                            f"JSON branch renders through console.{method_name}(); "
                            "emit machine output with click.echo(json.dumps(...)) instead"
                        ),
                    )
                )
        self.generic_visit(node)


def audit_source(source: str, *, path: Path) -> tuple[CliJsonOutputIssue, ...]:
    tree = ast.parse(source, filename=str(path))
    visitor = _JsonBranchConsoleVisitor(relative_file=_relative_file(path))
    visitor.visit(tree)
    return tuple(visitor.issues)


def run_audit(root_dir: Path = REPO_ROOT) -> tuple[CliJsonOutputIssue, ...]:
    path = root_dir / CLI_APP_PATH
    return audit_source(path.read_text(encoding="utf-8"), path=path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit CLI JSON branches for accidental rich console rendering."
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON payload")
    parser.add_argument("--check", action="store_true", help="Exit non-zero on issues")
    args = parser.parse_args()

    issues = run_audit()
    checked = 1
    if args.json:
        print(
            json.dumps(
                {
                    "checked": checked,
                    "issues": [
                        {
                            "file": issue.file,
                            "function": issue.function,
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
            f"CLI JSON output rendering audit\nchecked={checked} issues={len(issues)}"
        )
        for issue in issues:
            print(f"- {issue.file}:{issue.line} {issue.function}: {issue.reason}")

    if args.check and issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
