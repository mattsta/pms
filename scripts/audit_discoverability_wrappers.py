"""Audit paginated API routes for discoverability wrapper completeness."""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HTTP_METHODS: frozenset[str] = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})
PAGINATION_KEYS: frozenset[str] = frozenset({"items", "total_count", "offset", "limit"})
DISCOVERABILITY_KEYS: frozenset[str] = frozenset({"links", "next_steps", "params"})

type DictKeySet = frozenset[str]
type DictAssignments = dict[str, tuple[DictKeySet, ...]]


@dataclass(frozen=True, order=True)
class RouteTarget:
    """Single route target for a paginated endpoint function."""

    file_path: str
    function_name: str
    method: str
    path: str


@dataclass(frozen=True, order=True)
class WrapperAuditIssue:
    """Missing wrapper-key issue for a paginated route target."""

    target: RouteTarget
    reason: str
    missing_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class WrapperAuditResult:
    """Discoverability wrapper audit output."""

    route_targets: tuple[RouteTarget, ...]
    issues: tuple[WrapperAuditIssue, ...]
    files_scanned: int

    @property
    def route_total(self) -> int:
        return len(self.route_targets)

    @property
    def issue_total(self) -> int:
        return len(self.issues)

    @property
    def coverage_percent(self) -> float:
        if self.route_total == 0:
            return 100.0
        covered = self.route_total - self.issue_total
        return (covered / self.route_total) * 100.0


def _iter_function_body_nodes(
    function_node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[ast.AST, ...]:
    """Iterate nodes in a function body while skipping nested defs/classes."""
    nodes: list[ast.AST] = []
    stack: list[ast.AST] = list(function_node.body)
    while stack:
        node = stack.pop()
        nodes.append(node)
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
        ):
            continue
        stack.extend(ast.iter_child_nodes(node))
    return tuple(nodes)


def _is_paginated_annotation(annotation: ast.expr | None) -> bool:
    """Return True when annotation resolves to PaginatedResponse[...]"""
    if annotation is None:
        return False
    if isinstance(annotation, ast.Subscript):
        return _is_paginated_annotation(annotation.value)
    if isinstance(annotation, ast.Name):
        return annotation.id == "PaginatedResponse"
    if isinstance(annotation, ast.Attribute):
        return annotation.attr == "PaginatedResponse"
    return False


def _string_constant(value: ast.expr | None) -> str | None:
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        return value.value
    return None


def _extract_route_targets(
    *,
    file_path: Path,
    function_node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[RouteTarget, ...]:
    """Extract route targets from FastAPI decorators."""
    targets: list[RouteTarget] = []
    for decorator in function_node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        if not isinstance(decorator.func, ast.Attribute):
            continue

        method = decorator.func.attr.upper()
        if method not in HTTP_METHODS:
            continue

        path = _string_constant(decorator.args[0]) if decorator.args else None
        if path is None:
            for keyword in decorator.keywords:
                if keyword.arg == "path":
                    path = _string_constant(keyword.value)
                    break
        if path is None:
            continue

        targets.append(
            RouteTarget(
                file_path=str(file_path),
                function_name=function_node.name,
                method=method,
                path=path,
            )
        )
    return tuple(sorted(set(targets)))


def _dict_literal_keys(value: ast.expr) -> DictKeySet | None:
    if not isinstance(value, ast.Dict):
        return None
    keys: list[str] = []
    for key_node in value.keys:
        if key_node is None:
            return None
        key = _string_constant(key_node)
        if key is None:
            return None
        keys.append(key)
    return frozenset(keys)


def _collect_dict_assignments(
    function_node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> DictAssignments:
    """Collect assignments of literal dict payloads by variable name."""
    assignments: dict[str, list[DictKeySet]] = {}
    for node in _iter_function_body_nodes(function_node):
        name: str | None = None
        value_node: ast.expr | None = None

        if isinstance(node, ast.Assign):
            if len(node.targets) != 1:
                continue
            target = node.targets[0]
            if isinstance(target, ast.Name):
                name = target.id
                value_node = node.value
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                name = node.target.id
                value_node = node.value

        if name is None or value_node is None:
            continue

        key_set = _dict_literal_keys(value_node)
        if key_set is None:
            continue
        assignments.setdefault(name, []).append(key_set)

    return {
        variable_name: tuple(key_sets)
        for variable_name, key_sets in assignments.items()
    }


def _return_key_sets(
    return_node: ast.Return,
    assignments: DictAssignments,
) -> tuple[DictKeySet, ...]:
    value = return_node.value
    if value is None:
        return ()

    key_set = _dict_literal_keys(value)
    if key_set is not None:
        return (key_set,)

    if isinstance(value, ast.Name):
        return assignments.get(value.id, ())

    return ()


def _paginated_return_key_sets(
    function_node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[DictKeySet, ...]:
    assignments = _collect_dict_assignments(function_node)
    page_returns: list[DictKeySet] = []
    for node in _iter_function_body_nodes(function_node):
        if not isinstance(node, ast.Return):
            continue
        key_sets = _return_key_sets(node, assignments)
        for key_set in key_sets:
            if PAGINATION_KEYS.issubset(key_set):
                page_returns.append(key_set)
    return tuple(page_returns)


def audit_route_source(
    source: str,
    *,
    file_path: Path,
) -> tuple[tuple[RouteTarget, ...], tuple[WrapperAuditIssue, ...]]:
    """Audit a single route module source string."""
    tree = ast.parse(source)
    route_targets: list[RouteTarget] = []
    issues: list[WrapperAuditIssue] = []

    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        targets = _extract_route_targets(file_path=file_path, function_node=node)
        if not targets:
            continue
        if not _is_paginated_annotation(node.returns):
            continue

        route_targets.extend(targets)
        page_returns = _paginated_return_key_sets(node)
        if not page_returns:
            for target in targets:
                issues.append(
                    WrapperAuditIssue(
                        target=target,
                        reason="No static paginated return payload found",
                    )
                )
            continue

        for key_set in page_returns:
            missing_keys = tuple(sorted(DISCOVERABILITY_KEYS - key_set))
            if not missing_keys:
                continue
            for target in targets:
                issues.append(
                    WrapperAuditIssue(
                        target=target,
                        reason="Missing discoverability wrapper keys",
                        missing_keys=missing_keys,
                    )
                )

    return tuple(sorted(set(route_targets))), tuple(sorted(set(issues)))


def audit_discoverability_wrappers(routes_dir: Path) -> WrapperAuditResult:
    """Audit all route modules for paginated discoverability wrappers."""
    route_targets: list[RouteTarget] = []
    issues: list[WrapperAuditIssue] = []
    files_scanned = 0

    for route_file in sorted(routes_dir.glob("*.py")):
        if route_file.name == "__init__.py":
            continue
        files_scanned += 1
        source = route_file.read_text()
        module_targets, module_issues = audit_route_source(source, file_path=route_file)
        route_targets.extend(module_targets)
        issues.extend(module_issues)

    return WrapperAuditResult(
        route_targets=tuple(sorted(set(route_targets))),
        issues=tuple(sorted(set(issues))),
        files_scanned=files_scanned,
    )


def render_report(audit: WrapperAuditResult, max_list: int) -> str:
    """Render a deterministic text report."""
    lines: list[str] = []
    lines.append("Paginated discoverability wrapper audit")
    lines.append(
        f"routes={audit.route_total} "
        f"issues={audit.issue_total} "
        f"coverage={audit.coverage_percent:.2f}% "
        f"files_scanned={audit.files_scanned}"
    )

    if audit.issues:
        lines.append("")
        lines.append("Issues:")
        for issue in audit.issues[:max_list]:
            missing_suffix = (
                f" missing={','.join(issue.missing_keys)}" if issue.missing_keys else ""
            )
            lines.append(
                f"- {issue.target.method} {issue.target.path} "
                f"({issue.target.file_path}:{issue.target.function_name}) "
                f"{issue.reason}{missing_suffix}"
            )
        remaining = audit.issue_total - min(audit.issue_total, max_list)
        if remaining > 0:
            lines.append(f"- ... {remaining} more issues")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit that PaginatedResponse endpoints include discoverability wrappers."
    )
    parser.add_argument(
        "--routes-dir",
        type=Path,
        default=REPO_ROOT / "pms" / "api" / "routes",
        help="Directory containing API route modules.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail with non-zero exit when issue count exceeds --allow-issues.",
    )
    parser.add_argument(
        "--allow-issues",
        type=int,
        default=0,
        help="Maximum allowed issue count for --check mode.",
    )
    parser.add_argument(
        "--max-list",
        type=int,
        default=40,
        help="Maximum issue rows to print.",
    )
    return parser.parse_args()


def run(
    *,
    routes_dir: Path,
    check_only: bool,
    allow_issues: int,
    max_list: int,
) -> int:
    audit = audit_discoverability_wrappers(routes_dir)
    print(render_report(audit, max_list=max_list))

    if not check_only:
        return 0
    if audit.issue_total <= allow_issues:
        return 0
    return 1


def main() -> int:
    args = parse_args()
    return run(
        routes_dir=args.routes_dir,
        check_only=args.check,
        allow_issues=args.allow_issues,
        max_list=args.max_list,
    )


if __name__ == "__main__":
    raise SystemExit(main())
