"""Audit parity between API routes and client endpoints."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def _normalize(paths: Iterable[str]) -> set[str]:
    normalized = set()
    for path in paths:
        if not path:
            continue
        clean = path.split("?", 1)[0].rstrip("/")
        clean = re.sub(r"\{[^}]*\}", "{param}", clean)
        clean = clean.replace("{}", "{param}")
        if clean.endswith("{param}") and not clean.endswith("/{param}"):
            clean = clean[: -len("{param}")]
        normalized.add(clean)
    return normalized


def collect_api_routes() -> set[str]:
    app_path = REPO_ROOT / "pms" / "api" / "app.py"
    routes_dir = REPO_ROOT / "pms" / "api" / "routes"

    include_pattern = re.compile(
        r'app\.include_router\((?P<module>\w+)\.router(?:,\s*prefix="(?P<prefix>[^"]+)")?',
        re.MULTILINE,
    )
    router_pattern = re.compile(r"APIRouter\((?P<args>[^)]*)\)")
    prefix_pattern = re.compile(r'prefix\s*=\s*["\'](?P<prefix>[^"\']+)["\']')
    route_pattern = re.compile(
        r'@router\.(get|post|put|patch|delete)\(\s*(["\'])(?P<path>[^"\']+)\2',
        re.DOTALL,
    )
    app_route_pattern = re.compile(
        r'@app\.(get|post|put|patch|delete)\(\s*(["\'])(?P<path>[^"\']+)\2',
        re.DOTALL,
    )

    app_text = app_path.read_text()
    module_prefixes: dict[str, str] = {}
    for match in include_pattern.finditer(app_text):
        module = match.group("module")
        prefix = match.group("prefix") or ""
        module_prefixes[module] = prefix

    def join_prefix(prefix: str, path: str) -> str:
        if not prefix:
            return path
        if prefix.endswith("/") and path.startswith("/"):
            return prefix[:-1] + path
        return prefix + path

    routes = set()
    for module, app_prefix in module_prefixes.items():
        module_path = routes_dir / f"{module}.py"
        if not module_path.exists():
            continue
        text = module_path.read_text()
        router_prefix = ""
        router_match = router_pattern.search(text)
        if router_match:
            prefix_match = prefix_pattern.search(router_match.group("args"))
            if prefix_match:
                router_prefix = prefix_match.group("prefix")

        full_prefix = f"{app_prefix}{router_prefix}"
        for match in route_pattern.finditer(text):
            route_path = match.group("path")
            routes.add(join_prefix(full_prefix, route_path))

    for match in app_route_pattern.finditer(app_text):
        route_path = match.group("path")
        if route_path.startswith("/api/v1") or route_path == "/dashboard":
            routes.add(route_path)

    return _normalize(routes)


def _collect_paths_from_text(text: str) -> set[str]:
    paths = set()
    for match in re.findall(r"/api/v1[^\"']+|/dashboard", text):
        paths.add(match)
    return _normalize(paths)


def collect_python_client_paths() -> set[str]:
    text = (REPO_ROOT / "pms" / "client" / "http_client.py").read_text()
    return _collect_paths_from_text(text)


def collect_rust_client_paths() -> set[str]:
    paths = set()
    for path in (REPO_ROOT / "client-rust" / "src").rglob("*.rs"):
        paths.update(_collect_paths_from_text(path.read_text()))
    normalized = _normalize(paths)
    # Generic action helper template in Rust handlers is not an API route.
    normalized.discard("/api/v1/tasks/{param}/{param}")
    return normalized


def audit_parity() -> dict[str, list[str]]:
    api_routes = collect_api_routes()
    python_paths = collect_python_client_paths()
    rust_paths = collect_rust_client_paths()

    missing_python = sorted(api_routes - python_paths)
    missing_rust = sorted(api_routes - rust_paths)

    extra_python = sorted(python_paths - api_routes)
    extra_rust = sorted(rust_paths - api_routes)

    return {
        "api_routes": sorted(api_routes),
        "missing_python": missing_python,
        "missing_rust": missing_rust,
        "extra_python": extra_python,
        "extra_rust": extra_rust,
    }


def _load_allowlist(path: Path) -> dict[str, list[str]]:
    payload = json.loads(path.read_text())
    return {
        "python": payload.get("python", []),
        "rust": payload.get("rust", []),
    }


def _compare_allowlist(
    audit: dict[str, list[str]], allowlist: dict[str, list[str]]
) -> list[str]:
    errors = []
    missing_python = set(audit["missing_python"])
    missing_rust = set(audit["missing_rust"])
    allowed_python = set(allowlist.get("python", []))
    allowed_rust = set(allowlist.get("rust", []))

    if missing_python != allowed_python:
        unexpected = sorted(missing_python - allowed_python)
        stale = sorted(allowed_python - missing_python)
        if unexpected:
            errors.append(f"Unexpected Python client gaps: {unexpected}")
        if stale:
            errors.append(f"Stale Python allowlist entries: {stale}")

    if missing_rust != allowed_rust:
        unexpected = sorted(missing_rust - allowed_rust)
        stale = sorted(allowed_rust - missing_rust)
        if unexpected:
            errors.append(f"Unexpected Rust client gaps: {unexpected}")
        if stale:
            errors.append(f"Stale Rust allowlist entries: {stale}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit API/client parity.")
    parser.add_argument("--json", action="store_true", help="Output JSON payload")
    parser.add_argument(
        "--allowlist",
        type=Path,
        default=REPO_ROOT / "scripts" / "client_parity_allowlist.json",
        help="Allowlist JSON for missing endpoints",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero when allowlist mismatches",
    )
    args = parser.parse_args()

    audit = audit_parity()

    if args.json:
        print(json.dumps(audit, indent=2))
    else:
        print(f"API routes: {len(audit['api_routes'])}")
        print(f"Missing Python: {len(audit['missing_python'])}")
        print(f"Missing Rust: {len(audit['missing_rust'])}")
        if audit["missing_python"]:
            print("Python gaps:")
            for item in audit["missing_python"]:
                print(f"  - {item}")
        if audit["missing_rust"]:
            print("Rust gaps:")
            for item in audit["missing_rust"]:
                print(f"  - {item}")
        if audit["extra_python"]:
            print("Extra Python endpoints:")
            for item in audit["extra_python"]:
                print(f"  - {item}")
        if audit["extra_rust"]:
            print("Extra Rust endpoints:")
            for item in audit["extra_rust"]:
                print(f"  - {item}")

    if args.check:
        allowlist = _load_allowlist(args.allowlist)
        errors = _compare_allowlist(audit, allowlist)
        if errors:
            for error in errors:
                print(error)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
