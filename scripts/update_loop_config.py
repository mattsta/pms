#!/usr/bin/env python3
"""Update selected keys in a PMS loop config file."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml

from pms.utils.atomic_files import write_text_atomic


def _coerce(value: str) -> Any:
    lowered = value.strip().lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered == "null":
        return None
    try:
        return int(value)
    except ValueError:
        return value


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Update simple top-level loop config keys."
    )
    parser.add_argument("--file", required=True, help="Path to loop config file")
    parser.add_argument(
        "--set",
        dest="assignments",
        action="append",
        required=True,
        help="Assignment in key=value form; repeatable",
    )
    args = parser.parse_args()

    config_path = Path(args.file)
    payload = yaml.safe_load(config_path.read_text()) or {}
    if not isinstance(payload, dict):
        raise SystemExit("Loop config update failed: config root must be a mapping.")

    for assignment in args.assignments:
        if "=" not in assignment:
            raise SystemExit(
                f"Loop config update failed: invalid assignment '{assignment}'."
            )
        key, raw_value = assignment.split("=", 1)
        payload[key.strip()] = _coerce(raw_value)

    write_text_atomic(config_path, yaml.safe_dump(payload, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
