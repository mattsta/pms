#!/usr/bin/env python3
"""Reusable JSON path/query helper for shell automation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_json(path: str) -> Any:
    return json.loads(Path(path).read_text())


def _resolve_path(payload: Any, path: str) -> Any:
    current = payload
    if not path:
        return current
    for segment in path.split("."):
        if isinstance(current, list):
            try:
                current = current[int(segment)]
            except (ValueError, IndexError) as exc:
                raise KeyError(f"list segment {segment!r} not found") from exc
            continue
        if not isinstance(current, dict) or segment not in current:
            raise KeyError(f"path segment {segment!r} not found")
        current = current[segment]
    return current


def _print_value(value: Any) -> None:
    if value is None:
        return
    if isinstance(value, (dict, list)):
        print(json.dumps(value))
        return
    print(value)


def _cmd_path(args: argparse.Namespace) -> int:
    payload = _load_json(args.file)
    _print_value(_resolve_path(payload, args.get))
    return 0


def _cmd_find(args: argparse.Namespace) -> int:
    payload = _load_json(args.file)
    items = _resolve_path(payload, args.items)
    if not isinstance(items, list):
        raise SystemExit(f"{args.items!r} did not resolve to a list")
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            match_value = _resolve_path(item, args.match_field)
        except KeyError:
            continue
        if str(match_value) == args.match_value:
            _print_value(_resolve_path(item, args.get))
            return 0
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Query JSON files from shell automation."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    path_parser = subparsers.add_parser(
        "path", help="Read a dotted path from a JSON file"
    )
    path_parser.add_argument("--file", required=True, help="Path to JSON file")
    path_parser.add_argument("--get", required=True, help="Dotted path to extract")
    path_parser.set_defaults(func=_cmd_path)

    find_parser = subparsers.add_parser(
        "find", help="Find an item in a JSON list and extract a path"
    )
    find_parser.add_argument("--file", required=True, help="Path to JSON file")
    find_parser.add_argument(
        "--items", required=True, help="Dotted path resolving to a list"
    )
    find_parser.add_argument(
        "--match-field", required=True, help="Dotted path evaluated per item"
    )
    find_parser.add_argument(
        "--match-value", required=True, help="String value to match"
    )
    find_parser.add_argument(
        "--get", required=True, help="Dotted path to extract from the matching item"
    )
    find_parser.set_defaults(func=_cmd_find)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
