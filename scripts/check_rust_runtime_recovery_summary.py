#!/usr/bin/env python3
"""Validate the Rust degraded-runtime recovery summary artifact."""

from __future__ import annotations

import json
import os
from pathlib import Path


def main() -> int:
    base = Path(os.environ["PMS_DATA_DIR"])
    summary = json.loads(
        (base / "rust-runtime-recovery.summary.json").read_text(encoding="utf-8")
    )

    start = summary["start"]
    assert isinstance(start["canonical_prefix"], str)
    assert start["canonical_prefix"].startswith(
        "./.bin/pms-client --server http://127.0.0.1:"
    )
    assert start["has_focus_task_key"] is True
    assert start["has_next_steps"] is True

    runtime_status = summary["runtime_status"]
    assert runtime_status["canonical_prefix"] == "./.bin/pms-client"
    assert runtime_status["state"] == "degraded_server_unreachable"
    assert any(
        isinstance(step, str) and step.startswith("./.bin/pms-client ")
        for step in runtime_status["recommended_next_steps"]
    )

    stale = summary["stale_recovery"]
    assert stale["mentions_config_show"] is True
    assert stale["mentions_runtime_status"] is True
    assert stale["mentions_prefer_server"] is True

    for artifact in summary["artifacts"].values():
        assert Path(artifact).is_file(), artifact

    print("Rust degraded-runtime recovery summary is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
