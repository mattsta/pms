"""Audit docs/API_REFERENCE.md against live /api/v1 route inventory."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HTTP_METHODS: frozenset[str] = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})


@dataclass(frozen=True, order=True)
class ApiRoute:
    """Single HTTP method + path route entry."""

    method: str
    path: str


@dataclass(frozen=True)
class DocumentedRoutes:
    """Routes parsed from API reference markdown."""

    routes: tuple[ApiRoute, ...]
    routes_with_inline_json_body: tuple[ApiRoute, ...]
    http_block_count: int


@dataclass(frozen=True)
class ApiReferenceAudit:
    """Audit results comparing runtime routes vs documented examples."""

    openapi_routes: tuple[ApiRoute, ...]
    documented_routes: tuple[ApiRoute, ...]
    missing_routes: tuple[ApiRoute, ...]
    extra_routes: tuple[ApiRoute, ...]
    missing_body_example_routes: tuple[ApiRoute, ...]
    http_block_count: int
    endpoint_section_count: int
    body_routes_total: int
    body_routes_with_examples: int

    @property
    def openapi_total(self) -> int:
        return len(self.openapi_routes)

    @property
    def documented_total(self) -> int:
        return len(self.documented_routes)

    @property
    def missing_total(self) -> int:
        return len(self.missing_routes)

    @property
    def extra_total(self) -> int:
        return len(self.extra_routes)

    @property
    def coverage_percent(self) -> float:
        if self.openapi_total == 0:
            return 100.0
        covered = self.openapi_total - self.missing_total
        return (covered / self.openapi_total) * 100.0

    @property
    def missing_body_example_total(self) -> int:
        return len(self.missing_body_example_routes)

    @property
    def body_example_coverage_percent(self) -> float:
        if self.body_routes_total == 0:
            return 100.0
        return (self.body_routes_with_examples / self.body_routes_total) * 100.0


@dataclass(frozen=True)
class OpenApiInventory:
    """Route inventory collected from the live FastAPI app."""

    routes: tuple[ApiRoute, ...]
    body_routes: tuple[ApiRoute, ...]


def ensure_runtime_dirs() -> None:
    """Set local runtime directories so route import is sandbox-safe."""
    if "PMS_DATA_DIR" not in os.environ:
        os.environ["PMS_DATA_DIR"] = str(REPO_ROOT / ".tmp" / "api-reference-audit")
    if "PMS_LOG_DIR" not in os.environ:
        os.environ["PMS_LOG_DIR"] = str(Path(os.environ["PMS_DATA_DIR"]) / "logs")
    if "PMS_DATABASE_PATH" not in os.environ:
        os.environ["PMS_DATABASE_PATH"] = str(
            Path(os.environ["PMS_DATA_DIR"]) / "pms.db"
        )

    Path(os.environ["PMS_DATA_DIR"]).mkdir(parents=True, exist_ok=True)
    Path(os.environ["PMS_LOG_DIR"]).mkdir(parents=True, exist_ok=True)


def collect_openapi_inventory() -> OpenApiInventory:
    """Collect /api/v1 routes and body-bearing routes from live app routes."""
    ensure_runtime_dirs()

    from fastapi.routing import APIRoute

    from pms.api.app import app

    route_set: set[ApiRoute] = set()
    body_route_set: set[ApiRoute] = set()
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not route.path.startswith("/api/v1"):
            continue
        methods = sorted(
            method for method in route.methods if method not in {"HEAD", "OPTIONS"}
        )
        for method in methods:
            route_entry = ApiRoute(method=method, path=route.path)
            route_set.add(route_entry)
            if method in {"POST", "PUT", "PATCH"} and route.body_field is not None:
                body_route_set.add(route_entry)

    return OpenApiInventory(
        routes=tuple(sorted(route_set)),
        body_routes=tuple(sorted(body_route_set)),
    )


def _normalize_path(path: str) -> str:
    return path.split("?", maxsplit=1)[0]


def _parse_http_route_line(line: str) -> ApiRoute | None:
    parts = line.split(maxsplit=1)
    if len(parts) != 2:
        return None

    method, raw_path = parts
    if method not in HTTP_METHODS:
        return None
    if not raw_path.startswith("/api/v1"):
        return None

    return ApiRoute(method=method, path=_normalize_path(raw_path))


def extract_documented_routes(markdown: str) -> DocumentedRoutes:
    """Extract method+path examples from ```http code fences."""
    in_http_block = False
    http_block_count = 0
    route_set: set[ApiRoute] = set()
    inline_json_body_set: set[ApiRoute] = set()
    block_routes: list[ApiRoute] = []
    block_has_inline_json = False

    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if line == "```http":
            in_http_block = True
            http_block_count += 1
            block_routes = []
            block_has_inline_json = False
            continue
        if in_http_block and line.startswith("```"):
            if block_has_inline_json:
                for route in block_routes:
                    if route.method in {"POST", "PUT", "PATCH"}:
                        inline_json_body_set.add(route)
            in_http_block = False
            block_routes = []
            block_has_inline_json = False
            continue
        if not in_http_block:
            continue

        if line.startswith("{"):
            block_has_inline_json = True

        route = _parse_http_route_line(line)
        if route is not None:
            route_set.add(route)
            block_routes.append(route)

    return DocumentedRoutes(
        routes=tuple(sorted(route_set)),
        routes_with_inline_json_body=tuple(sorted(inline_json_body_set)),
        http_block_count=http_block_count,
    )


def count_endpoint_sections(markdown: str) -> int:
    """Count top-level API groups (`### * API`) in the reference."""
    count = 0
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if line.startswith("### ") and line.endswith(" API"):
            count += 1
    return count


def audit_api_reference(api_reference_path: Path) -> ApiReferenceAudit:
    """Build completeness audit for API reference markdown."""
    markdown = api_reference_path.read_text()
    documented = extract_documented_routes(markdown)
    openapi_inventory = collect_openapi_inventory()
    openapi_routes = openapi_inventory.routes

    openapi_set = set(openapi_routes)
    documented_set = set(documented.routes)
    openapi_body_set = set(openapi_inventory.body_routes)
    documented_body_set = set(documented.routes_with_inline_json_body)

    missing_routes = tuple(sorted(openapi_set - documented_set))
    extra_routes = tuple(sorted(documented_set - openapi_set))
    missing_body_example_routes = tuple(sorted(openapi_body_set - documented_body_set))
    body_routes_with_examples = len(openapi_body_set) - len(missing_body_example_routes)

    return ApiReferenceAudit(
        openapi_routes=openapi_routes,
        documented_routes=documented.routes,
        missing_routes=missing_routes,
        extra_routes=extra_routes,
        missing_body_example_routes=missing_body_example_routes,
        http_block_count=documented.http_block_count,
        endpoint_section_count=count_endpoint_sections(markdown),
        body_routes_total=len(openapi_body_set),
        body_routes_with_examples=body_routes_with_examples,
    )


def _resource_group(path: str) -> str:
    if path == "/api/v1/health":
        return "health"
    suffix = path.removeprefix("/api/v1/")
    if not suffix:
        return "root"
    return suffix.split("/", maxsplit=1)[0]


def _summarize_groups(routes: tuple[ApiRoute, ...]) -> tuple[tuple[str, int], ...]:
    counts: dict[str, int] = {}
    for route in routes:
        key = _resource_group(route.path)
        counts[key] = counts.get(key, 0) + 1
    return tuple(sorted(counts.items(), key=lambda pair: (-pair[1], pair[0])))


def render_report(audit: ApiReferenceAudit, max_list: int) -> str:
    """Render human-readable audit report."""
    lines: list[str] = []
    lines.append("API reference completeness audit")
    lines.append(
        "openapi_routes="
        f"{audit.openapi_total} documented_routes={audit.documented_total} "
        f"missing={audit.missing_total} extra={audit.extra_total} "
        f"coverage={audit.coverage_percent:.2f}%"
    )
    lines.append(
        f"http_example_blocks={audit.http_block_count} endpoint_api_sections={audit.endpoint_section_count}"
    )
    lines.append(
        "body_routes="
        f"{audit.body_routes_total} "
        f"body_examples={audit.body_routes_with_examples} "
        f"missing_body_examples={audit.missing_body_example_total} "
        f"body_coverage={audit.body_example_coverage_percent:.2f}%"
    )

    if audit.missing_routes:
        lines.append("")
        lines.append("Missing routes by resource:")
        for group, count in _summarize_groups(audit.missing_routes):
            lines.append(f"- {group}: {count}")

        lines.append("")
        lines.append("Missing routes:")
        for route in audit.missing_routes[:max_list]:
            lines.append(f"- {route.method} {route.path}")
        remaining = audit.missing_total - min(audit.missing_total, max_list)
        if remaining > 0:
            lines.append(f"- ... {remaining} more missing routes")

    if audit.extra_routes:
        lines.append("")
        lines.append("Documented routes not present in OpenAPI:")
        for route in audit.extra_routes[:max_list]:
            lines.append(f"- {route.method} {route.path}")
        remaining = audit.extra_total - min(audit.extra_total, max_list)
        if remaining > 0:
            lines.append(f"- ... {remaining} more extra routes")

    if audit.missing_body_example_routes:
        lines.append("")
        lines.append("Routes missing inline JSON body examples:")
        for route in audit.missing_body_example_routes[:max_list]:
            lines.append(f"- {route.method} {route.path}")
        remaining = audit.missing_body_example_total - min(
            audit.missing_body_example_total, max_list
        )
        if remaining > 0:
            lines.append(f"- ... {remaining} more routes missing body examples")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit docs/API_REFERENCE.md against live FastAPI /api/v1 routes."
    )
    parser.add_argument(
        "--api-reference",
        type=Path,
        default=REPO_ROOT / "docs" / "API_REFERENCE.md",
        help="Path to API reference markdown file.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail with exit code 1 when missing/extra routes exceed allowed thresholds.",
    )
    parser.add_argument(
        "--allow-missing",
        type=int,
        default=0,
        help="Allowed missing route count in check mode.",
    )
    parser.add_argument(
        "--allow-extra",
        type=int,
        default=0,
        help="Allowed extra route count in check mode.",
    )
    parser.add_argument(
        "--allow-missing-body-examples",
        type=int,
        default=0,
        help="Allowed count of body-bearing routes without inline JSON request examples.",
    )
    parser.add_argument(
        "--max-list",
        type=int,
        default=200,
        help="Maximum missing/extra routes to print.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    audit = audit_api_reference(api_reference_path=args.api_reference)
    print(render_report(audit, max_list=args.max_list))

    if not args.check:
        return 0

    if audit.missing_total > args.allow_missing:
        return 1
    if audit.extra_total > args.allow_extra:
        return 1
    if audit.missing_body_example_total > args.allow_missing_body_examples:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
