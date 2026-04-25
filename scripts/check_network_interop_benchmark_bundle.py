#!/usr/bin/env python3
"""Validate the network interop benchmark bundle summary and report artifacts."""

from __future__ import annotations

import json
import os
from pathlib import Path


def main() -> int:
    base = Path(os.environ["PMS_DATA_DIR"])
    summary_path = base / "benchmark" / "benchmark-bundle.summary.json"
    if not summary_path.is_file():
        summary_path = base / "benchmark-bundle.summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    for artifact in summary["artifacts"].values():
        assert Path(artifact).is_file(), artifact

    report = json.loads(
        Path(summary["artifacts"]["benchmark_report"]).read_text(encoding="utf-8")
    )
    scenarios = report["scenarios"]

    assert {"start_json", "task_list_json", "plan_list_json"} <= set(scenarios)
    assert {"python_cli", "rust_client"} <= set(scenarios["start_json"])
    assert {"python_cli", "rust_client", "api_http"} <= set(scenarios["task_list_json"])
    assert {"python_cli", "rust_client", "api_http"} <= set(scenarios["plan_list_json"])

    for scenario_interfaces in scenarios.values():
        for entry in scenario_interfaces.values():
            assert entry["run_count"] >= 1
            assert entry["median_seconds"] >= 0
            assert entry["max_seconds"] >= entry["min_seconds"] >= 0

    print("Network interop benchmark bundle is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
