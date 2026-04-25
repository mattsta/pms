"""Generate a deterministic API endpoint catalog from the live FastAPI app."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path

from pms.utils.atomic_files import write_text_atomic
from pms.utils.markdown_formatting import format_markdown_with_prettier

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, order=True)
class EndpointRoute:
    """Single HTTP method + path route entry."""

    method: str
    path: str


@dataclass(frozen=True)
class EndpointCatalog:
    """Computed endpoint inventory for documentation output."""

    routes: tuple[EndpointRoute, ...]
    api_v1_total: int
    api_v1_without_health: int


def ensure_runtime_dirs() -> None:
    """Set local runtime directories so route import is sandbox-safe."""
    if "PMS_DATA_DIR" not in os.environ:
        os.environ["PMS_DATA_DIR"] = str(REPO_ROOT / ".tmp" / "endpoint-catalog")
    if "PMS_LOG_DIR" not in os.environ:
        os.environ["PMS_LOG_DIR"] = str(Path(os.environ["PMS_DATA_DIR"]) / "logs")
    if "PMS_DATABASE_PATH" not in os.environ:
        os.environ["PMS_DATABASE_PATH"] = str(
            Path(os.environ["PMS_DATA_DIR"]) / "pms.db"
        )

    Path(os.environ["PMS_DATA_DIR"]).mkdir(parents=True, exist_ok=True)
    Path(os.environ["PMS_LOG_DIR"]).mkdir(parents=True, exist_ok=True)


def collect_api_v1_catalog() -> EndpointCatalog:
    """Collect `/api/v1/*` routes from the loaded FastAPI app."""
    ensure_runtime_dirs()

    from fastapi.routing import APIRoute

    from pms.api.app import app

    route_set: set[EndpointRoute] = set()
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not route.path.startswith("/api/v1"):
            continue
        methods = sorted(
            method for method in route.methods if method not in {"HEAD", "OPTIONS"}
        )
        for method in methods:
            route_set.add(EndpointRoute(method=method, path=route.path))

    routes = tuple(sorted(route_set))
    without_health = tuple(route for route in routes if route.path != "/api/v1/health")
    return EndpointCatalog(
        routes=routes,
        api_v1_total=len(routes),
        api_v1_without_health=len(without_health),
    )


def _route_group(path: str) -> str:
    if path == "/api/v1/health":
        return "health"
    suffix = path.removeprefix("/api/v1/")
    if not suffix:
        return "root"
    return suffix.split("/", 1)[0]


def render_catalog_markdown(catalog: EndpointCatalog) -> str:
    """Render deterministic endpoint catalog markdown."""
    grouped: dict[str, list[EndpointRoute]] = {}
    for route in catalog.routes:
        group = _route_group(route.path)
        grouped.setdefault(group, []).append(route)

    lines: list[str] = []
    lines.append("# API Endpoint Catalog")
    lines.append("")
    lines.append("Generated from live route definitions in `pms.api.app`.")
    lines.append("")
    lines.append("Regenerate:")
    lines.append("")
    lines.append("```bash")
    lines.append("uv run python scripts/generate_api_endpoint_catalog.py")
    lines.append("```")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- `/api/v1/*` method+path routes: **{catalog.api_v1_total}**")
    lines.append(
        f"- `/api/v1/*` routes excluding `/api/v1/health`: **{catalog.api_v1_without_health}**"
    )
    lines.append("")

    for group in sorted(grouped):
        routes = sorted(grouped[group])
        lines.append(f"## `{group}` ({len(routes)})")
        lines.append("")
        for route in routes:
            lines.append(f"- `{route.method} {route.path}`")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def run(output_path: Path, check_only: bool) -> int:
    """Write or check generated endpoint catalog output."""
    catalog = collect_api_v1_catalog()
    rendered = format_markdown_with_prettier(
        render_catalog_markdown(catalog),
        filepath=output_path,
    )

    if check_only:
        if not output_path.exists():
            print(f"Catalog check failed: missing file {output_path}")
            return 1
        existing = output_path.read_text()
        if existing != rendered:
            print(
                "Catalog check failed: endpoint catalog is out of date.\n"
                f"Run: uv run python scripts/generate_api_endpoint_catalog.py --output {output_path}"
            )
            return 1
        print(
            "Catalog check passed: "
            f"{output_path} (routes={catalog.api_v1_total}, without_health={catalog.api_v1_without_health})"
        )
        return 0

    write_text_atomic(output_path, rendered)
    print(
        "Wrote endpoint catalog: "
        f"{output_path} (routes={catalog.api_v1_total}, without_health={catalog.api_v1_without_health})"
    )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate `/api/v1/*` endpoint catalog from live FastAPI routes."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "docs" / "API_ENDPOINT_CATALOG.md",
        help="Output markdown path.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check mode: fail if output differs from generated content.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return run(output_path=args.output, check_only=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
