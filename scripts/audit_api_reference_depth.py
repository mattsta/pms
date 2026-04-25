"""Audit response-documentation depth for docs/API_REFERENCE.md."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from scripts.audit_api_reference import ApiRoute

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class SectionBlock:
    """Markdown subsection block keyed by #### heading."""

    title: str
    start_line: int
    lines: tuple[str, ...]


@dataclass(frozen=True, order=True)
class RouteLocation:
    """Single documented route and its subsection location."""

    method: str
    path: str
    section_title: str
    line: int


@dataclass(frozen=True)
class DepthAudit:
    """Depth audit result for API reference response documentation."""

    route_locations: tuple[RouteLocation, ...]
    local_response_routes: tuple[ApiRoute, ...]
    contract_covered_routes: tuple[ApiRoute, ...]
    uncovered_routes: tuple[RouteLocation, ...]

    @property
    def total_routes(self) -> int:
        return len(self.route_locations)

    @property
    def local_total(self) -> int:
        return len(self.local_response_routes)

    @property
    def contract_covered_total(self) -> int:
        return len(self.contract_covered_routes)

    @property
    def uncovered_total(self) -> int:
        return len(self.uncovered_routes)

    @property
    def local_percent(self) -> float:
        if self.total_routes == 0:
            return 100.0
        return (self.local_total / self.total_routes) * 100.0

    @property
    def coverage_percent(self) -> float:
        if self.total_routes == 0:
            return 100.0
        covered = self.total_routes - self.uncovered_total
        return (covered / self.total_routes) * 100.0


def _split_sections(markdown: str) -> tuple[SectionBlock, ...]:
    lines = markdown.splitlines()
    sections: list[SectionBlock] = []

    current_title = "ROOT"
    start = 0
    for index, line in enumerate(lines):
        if line.startswith("#### "):
            if index > start:
                sections.append(
                    SectionBlock(
                        title=current_title,
                        start_line=start + 1,
                        lines=tuple(lines[start:index]),
                    )
                )
            current_title = line[5:].strip()
            start = index

    if start < len(lines):
        sections.append(
            SectionBlock(
                title=current_title,
                start_line=start + 1,
                lines=tuple(lines[start:]),
            )
        )

    return tuple(sections)


def _section_routes(section: SectionBlock) -> tuple[RouteLocation, ...]:
    routes: list[RouteLocation] = []
    in_http_block = False

    for offset, raw_line in enumerate(section.lines):
        line = raw_line.strip()
        if line == "```http":
            in_http_block = True
            continue
        if in_http_block and line.startswith("```"):
            in_http_block = False
            continue
        if not in_http_block:
            continue

        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            continue
        method, path = parts
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            continue
        if not path.startswith("/api/v1"):
            continue
        normalized_path = path.split("?", maxsplit=1)[0]
        routes.append(
            RouteLocation(
                method=method,
                path=normalized_path,
                section_title=section.title,
                line=section.start_line + offset,
            )
        )

    return tuple(routes)


def _has_local_response_detail(section: SectionBlock) -> bool:
    text = "\n".join(section.lines)
    if "**Response**" in text:
        return True
    if "No response body" in text:
        return True
    return "Returns " in text


def _parse_contract_routes(contract_markdown: str) -> tuple[ApiRoute, ...]:
    routes: set[ApiRoute] = set()
    for raw_line in contract_markdown.splitlines():
        line = raw_line.strip()
        if not line.startswith("| `"):
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) < 4:
            continue
        method_cell = parts[1]
        path_cell = parts[2]
        if not (method_cell.startswith("`") and method_cell.endswith("`")):
            continue
        if not (path_cell.startswith("`") and path_cell.endswith("`")):
            continue
        method = method_cell.removeprefix("`").removesuffix("`")
        path = path_cell.removeprefix("`").removesuffix("`")
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            continue
        if not path.startswith("/api/v1"):
            continue
        routes.add(ApiRoute(method=method, path=path))
    return tuple(sorted(routes))


def audit_api_reference_depth(
    api_reference_path: Path,
    contract_path: Path,
) -> DepthAudit:
    """Audit local response detail depth plus contract coverage."""
    api_markdown = api_reference_path.read_text()
    contract_markdown = contract_path.read_text()

    sections = _split_sections(api_markdown)
    contract_routes = set(_parse_contract_routes(contract_markdown))

    route_locations: list[RouteLocation] = []
    local_routes: set[ApiRoute] = set()
    contract_covered_routes: set[ApiRoute] = set()
    uncovered: list[RouteLocation] = []

    for section in sections:
        section_routes = _section_routes(section)
        if not section_routes:
            continue

        route_locations.extend(section_routes)
        has_local_response = _has_local_response_detail(section)

        for route_location in section_routes:
            route = ApiRoute(method=route_location.method, path=route_location.path)
            if has_local_response:
                local_routes.add(route)
                continue
            if route in contract_routes:
                contract_covered_routes.add(route)
                continue
            uncovered.append(route_location)

    return DepthAudit(
        route_locations=tuple(route_locations),
        local_response_routes=tuple(sorted(local_routes)),
        contract_covered_routes=tuple(sorted(contract_covered_routes)),
        uncovered_routes=tuple(sorted(uncovered)),
    )


def render_report(audit: DepthAudit, max_list: int) -> str:
    """Render depth audit summary report."""
    lines: list[str] = []
    lines.append("API reference response-depth audit")
    lines.append(
        "routes="
        f"{audit.total_routes} "
        f"local_response_routes={audit.local_total} "
        f"contract_covered_routes={audit.contract_covered_total} "
        f"uncovered={audit.uncovered_total} "
        f"local_percent={audit.local_percent:.2f}% "
        f"coverage={audit.coverage_percent:.2f}%"
    )

    if audit.uncovered_routes:
        lines.append("")
        lines.append(
            "Uncovered routes (no local response detail and no contract entry):"
        )
        for route in audit.uncovered_routes[:max_list]:
            lines.append(
                f"- {route.method} {route.path} "
                f"(section='{route.section_title}', line={route.line})"
            )
        remaining = audit.uncovered_total - min(audit.uncovered_total, max_list)
        if remaining > 0:
            lines.append(f"- ... {remaining} more uncovered routes")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit response-documentation depth for API reference."
    )
    parser.add_argument(
        "--api-reference",
        type=Path,
        default=REPO_ROOT / "docs" / "API_REFERENCE.md",
        help="Path to manual API reference markdown.",
    )
    parser.add_argument(
        "--contracts",
        type=Path,
        default=REPO_ROOT / "docs" / "API_RESPONSE_CONTRACTS.md",
        help="Path to generated API response contracts markdown.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if uncovered routes exceed threshold or local coverage is too low.",
    )
    parser.add_argument(
        "--allow-uncovered",
        type=int,
        default=0,
        help="Allowed uncovered route count in check mode.",
    )
    parser.add_argument(
        "--min-local-percent",
        type=float,
        default=20.0,
        help="Minimum local response-detail coverage percent in check mode.",
    )
    parser.add_argument(
        "--max-list",
        type=int,
        default=40,
        help="Maximum uncovered routes to print.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    audit = audit_api_reference_depth(
        api_reference_path=args.api_reference,
        contract_path=args.contracts,
    )
    print(render_report(audit, max_list=args.max_list))

    if not args.check:
        return 0
    if audit.uncovered_total > args.allow_uncovered:
        return 1
    if audit.local_percent < args.min_local_percent:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
