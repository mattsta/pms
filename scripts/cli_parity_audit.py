"""Audit parity between Python CLI and Rust CLI command trees."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

ALIASES = {
    "auth list": "auth keys list",
    "auth create": "auth keys create",
    "auth revoke": "auth keys deactivate",
    "auth deactivate": "auth keys deactivate",
    "auth restore": "auth keys restore",
    "auth get": "auth keys get",
    "auth keys delete": "auth keys deactivate",
    "task add": "task create",
    "project add": "project create",
    "project archive": "project delete",
    "task cleanup-checkouts": "task checkout-cleanup",
    "task merge-duplicates": "task duplicates-merge",
    "task merge-preview": "task duplicates-preview",
    "evidence gate add": "evidence gate create",
    "evidence bundle-search": "task proof-bundle-search",
    "goal workflow-assign": "workflow assign",
    "goal workflow-transition": "workflow transition",
    "objective workflow-assign": "workflow assign",
    "objective workflow-transition": "workflow transition",
    "health": "capabilities health",
    "label assign": "label assignment create",
    "label remove": "label assignment remove",
    "label list-entity": "label assignment list",
    "queue preset": "queue presets",
    "test-run list": "test list",
    "test-run show": "test show",
    "test-run run": "test run",
    "test-run prune": "test prune",
    "test-run retention": "test retention",
    "test-run record": "test record",
    "test-run retention-policy list": "test retention-policy list",
    "test-run retention-policy show": "test retention-policy show",
    "test-run retention-policy set": "test retention-policy set",
    "test-run retention-policy update": "test retention-policy update",
    "test-run retention-policy archive": "test retention-policy archive",
    "test-run retention-policy restore": "test retention-policy restore",
    "test-run server ensure-local": "test server ensure-local",
}

SHOW_ALIASES = {
    "goal",
    "objective",
    "keyresult",
    "label",
    "label category",
    "label gate",
    "org",
    "team",
    "portfolio",
    "program",
    "product",
    "project",
    "plan",
    "plan test-job",
    "queue",
    "task",
}

ADD_ALIASES = {
    "plan test-job",
    "label gate",
}


def _kebab(name: str) -> str:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", name)
    return value.replace("_", "-").lower()


def normalize_path(path: str) -> str:
    if path in ALIASES:
        return ALIASES[path]
    if path.endswith(" show"):
        prefix = path[: -len(" show")]
        if prefix in SHOW_ALIASES:
            return f"{prefix} get"
    if path.endswith(" add"):
        prefix = path[: -len(" add")]
        if prefix in ADD_ALIASES:
            return f"{prefix} create"
    return path


def normalize_paths(paths: Iterable[str]) -> set[str]:
    return {normalize_path(path) for path in paths}


def collect_python_cli_commands() -> set[str]:
    import click

    from pms.cli.app import cli

    def walk(cmd: click.Command, prefix: str = "") -> set[str]:
        paths: set[str] = set()
        if isinstance(cmd, click.Group):
            for name, sub in cmd.commands.items():
                path = f"{prefix}{name}".strip()
                if isinstance(sub, click.Group) and sub.commands:
                    paths.update(walk(sub, f"{path} "))
                else:
                    paths.add(path)
        return paths

    return walk(cli)


@dataclass
class RustVariant:
    name: str
    cli_name: str
    subcommand_enum: str | None = None


def _parse_rust_enums(text: str) -> dict[str, list[RustVariant]]:
    enums: dict[str, list[RustVariant]] = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        enum_match = re.match(r"\s*enum\s+(\w+)\s*{", line)
        if not enum_match:
            i += 1
            continue
        enum_name = enum_match.group(1)
        variants: list[RustVariant] = []
        pending_name: str | None = None
        depth = line.count("{") - line.count("}")
        i += 1
        while i < len(lines) and depth > 0:
            line = lines[i]
            depth += line.count("{") - line.count("}")
            name_match = re.search(r'#\[\s*command\s*\(\s*name\s*=\s*"([^"]+)"', line)
            if name_match:
                pending_name = name_match.group(1)
                i += 1
                continue
            variant_match = re.match(r"\s*([A-Z][A-Za-z0-9_]*)\s*(\{|,|$)", line)
            if variant_match:
                variant_name = variant_match.group(1)
                cli_name = pending_name or _kebab(variant_name)
                pending_name = None
                subcommand_enum: str | None = None
                variant_depth = line.count("{") - line.count("}")
                j = i + 1
                while variant_depth > 0 and j < len(lines):
                    inner = lines[j]
                    action_match = re.search(r"\baction\s*:\s*(\w+Commands)\b", inner)
                    if action_match:
                        subcommand_enum = action_match.group(1)
                    variant_depth += inner.count("{") - inner.count("}")
                    j += 1
                variants.append(
                    RustVariant(
                        name=variant_name,
                        cli_name=cli_name,
                        subcommand_enum=subcommand_enum,
                    )
                )
            i += 1
        enums[enum_name] = variants
    return enums


def collect_rust_cli_commands() -> set[str]:
    rust_path = REPO_ROOT / "client-rust" / "src" / "main.rs"
    text = rust_path.read_text()
    enums = _parse_rust_enums(text)

    def walk(enum_name: str, prefix: str = "") -> set[str]:
        paths: set[str] = set()
        for variant in enums.get(enum_name, []):
            path = f"{prefix}{variant.cli_name}".strip()
            if variant.subcommand_enum:
                paths.update(walk(variant.subcommand_enum, f"{path} "))
            else:
                paths.add(path)
        return paths

    return walk("Commands")


def _load_allowlist(path: Path) -> dict[str, list[str]]:
    payload = json.loads(path.read_text())
    return {
        "exclude_prefixes": payload.get("exclude_prefixes", []),
        "python": payload.get("python", []),
        "rust": payload.get("rust", []),
    }


def _apply_excludes(paths: Iterable[str], prefixes: Iterable[str]) -> set[str]:
    cleaned: set[str] = set()
    for path in paths:
        if any(path == prefix or path.startswith(f"{prefix} ") for prefix in prefixes):
            continue
        cleaned.add(path)
    return cleaned


def audit_parity() -> dict[str, list[str]]:
    python_paths = normalize_paths(collect_python_cli_commands())
    rust_paths = normalize_paths(collect_rust_cli_commands())
    return {
        "python_commands": sorted(python_paths),
        "rust_commands": sorted(rust_paths),
    }


def _compare_allowlist(
    missing_python: set[str],
    missing_rust: set[str],
    allowlist: dict[str, list[str]],
) -> list[str]:
    errors = []
    allowed_rust = set(allowlist.get("rust", []))

    if missing_rust != allowed_rust:
        unexpected = sorted(missing_rust - allowed_rust)
        stale = sorted(allowed_rust - missing_rust)
        if unexpected:
            errors.append(f"Unexpected Rust CLI gaps: {unexpected}")
        if stale:
            errors.append(f"Stale Rust CLI allowlist entries: {stale}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Python/Rust CLI parity.")
    parser.add_argument("--json", action="store_true", help="Output JSON payload")
    parser.add_argument(
        "--allowlist",
        type=Path,
        default=REPO_ROOT / "scripts" / "cli_parity_allowlist.json",
        help="Allowlist JSON for missing commands",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero when allowlist mismatches",
    )
    args = parser.parse_args()

    audit = audit_parity()
    allowlist = _load_allowlist(args.allowlist)
    python_paths = _apply_excludes(
        audit["python_commands"], allowlist.get("exclude_prefixes", [])
    )
    rust_paths = _apply_excludes(
        audit["rust_commands"], allowlist.get("exclude_prefixes", [])
    )

    missing_rust = sorted(python_paths - rust_paths)
    missing_python = sorted(rust_paths - python_paths)

    if args.json:
        print(
            json.dumps(
                {
                    "python_commands": sorted(python_paths),
                    "rust_commands": sorted(rust_paths),
                    "missing_rust": missing_rust,
                    "missing_python": missing_python,
                    "exclude_prefixes": allowlist.get("exclude_prefixes", []),
                },
                indent=2,
            )
        )
    else:
        print(f"Python CLI commands: {len(python_paths)}")
        print(f"Rust CLI commands: {len(rust_paths)}")
        print(f"Missing in Rust: {len(missing_rust)}")
        print(f"Missing in Python: {len(missing_python)}")
        if missing_rust:
            print("Rust gaps:")
            for item in missing_rust:
                print(f"  - {item}")
        if missing_python:
            print("Python gaps:")
            for item in missing_python:
                print(f"  - {item}")

    if args.check:
        errors = _compare_allowlist(set(missing_python), set(missing_rust), allowlist)
        if errors:
            for error in errors:
                print(error)
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
