#!/usr/bin/env python3
"""Write a structured fast-path benchmark report from a TSV metrics file."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from datetime import UTC, datetime
from pathlib import Path

from pms.utils.atomic_files import write_json_atomic


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metrics-file", required=True)
    parser.add_argument("--report-file", required=True)
    parser.add_argument("--server-url", required=True)
    parser.add_argument("--project-id", default="")
    parser.add_argument("--project", default="")
    parser.add_argument("--repetitions", type=int, default=1)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    metrics_path = Path(args.metrics_file)
    rows: list[dict[str, str]] = []
    with metrics_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(
            handle,
            fieldnames=[
                "scenario",
                "interface",
                "command",
                "run_index",
                "real_seconds",
            ],
            delimiter="\t",
        )
        rows.extend(reader)

    scenarios: dict[str, dict[str, object]] = {}
    for row in rows:
        scenario = row["scenario"]
        scenarios.setdefault(scenario, {})
        entry = scenarios[scenario].setdefault(
            row["interface"],
            {
                "command": row["command"],
                "runs": [],
            },
        )
        assert isinstance(entry, dict)
        runs = entry.setdefault("runs", [])
        assert isinstance(runs, list)
        runs.append(float(row["real_seconds"]))

    for interfaces in scenarios.values():
        for entry in interfaces.values():
            if not isinstance(entry, dict):
                continue
            runs = [float(value) for value in entry.get("runs", [])]
            if not runs:
                continue
            entry["run_count"] = len(runs)
            entry["median_seconds"] = statistics.median(runs)
            entry["mean_seconds"] = statistics.fmean(runs)
            entry["min_seconds"] = min(runs)
            entry["max_seconds"] = max(runs)

    payload = {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "server_url": args.server_url,
        "project_id": args.project_id or None,
        "project": args.project or None,
        "repetitions": args.repetitions,
        "scenarios": scenarios,
        "notes": [
            "Python path measures direct CLI startup plus local data access.",
            "Rust path measures the installed compiled client against a warm local PMS API server.",
            "API path measures direct HTTP latency against the same warm server.",
            "These scenarios are intended for repeated read-path comparison, including paginated list views.",
            "Statistics aggregate repeated runs for each scenario/interface pair.",
        ],
    }

    report_path = Path(args.report_file)
    write_json_atomic(report_path, payload, encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
