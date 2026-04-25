#!/usr/bin/env python3
"""Validate the backlog-triage scenario summary artifact."""

from __future__ import annotations

import json
import os
from pathlib import Path


def _require(value: object, message: str) -> None:
    if not value:
        raise SystemExit(message)


def main() -> int:
    summary_path = Path(os.environ["PMS_DATA_DIR"]) / "backlog-triage.summary.json"
    summary = json.loads(summary_path.read_text())

    project = summary.get("project")
    if not isinstance(project, dict):
        raise SystemExit(
            "Backlog-triage contract smoke failed: summary.project must be an object."
        )
    _require(
        project.get("name"),
        "Backlog-triage contract smoke failed: project.name is missing.",
    )
    _require(
        project.get("id"),
        "Backlog-triage contract smoke failed: project.id is missing.",
    )

    execution_ids = summary.get("execution_ids")
    if not isinstance(execution_ids, dict):
        raise SystemExit(
            "Backlog-triage contract smoke failed: summary.execution_ids must be an object."
        )
    for key in (
        "plan_id",
        "critical_task_id",
        "high_task_id",
        "duplicate_primary_id",
        "duplicate_secondary_id",
        "queue_id",
    ):
        _require(
            execution_ids.get(key),
            f"Backlog-triage contract smoke failed: execution_ids.{key} is missing.",
        )

    artifacts = summary.get("artifacts")
    if not isinstance(artifacts, dict):
        raise SystemExit(
            "Backlog-triage contract smoke failed: summary.artifacts must be an object."
        )
    for key in (
        "bootstrap",
        "dashboard",
        "ready_json",
        "available_json",
        "duplicates_json",
        "merge_preview_json",
        "queue_presets_json",
        "queue_run_json",
        "daily_summary",
        "plan_lineage_json",
        "project_report",
        "metrics_csv",
    ):
        value = artifacts.get(key)
        _require(
            value, f"Backlog-triage contract smoke failed: artifacts.{key} is missing."
        )
        artifact_path = Path(value)
        if not artifact_path.is_file() or artifact_path.stat().st_size == 0:
            raise SystemExit(
                f"Backlog-triage contract smoke failed: artifact {key} missing or empty: {artifact_path}"
            )

    next_steps = summary.get("next_steps")
    if not isinstance(next_steps, dict):
        raise SystemExit(
            "Backlog-triage contract smoke failed: summary.next_steps must be an object."
        )
    for key in (
        "ready",
        "available",
        "duplicates",
        "merge_preview",
        "queue_run",
        "daily",
        "lineage",
    ):
        value = next_steps.get(key)
        if not isinstance(value, list) or not value:
            raise SystemExit(
                f"Backlog-triage contract smoke failed: next_steps.{key} must be a non-empty list."
            )

    triage_state = summary.get("triage_state")
    if not isinstance(triage_state, dict):
        raise SystemExit(
            "Backlog-triage contract smoke failed: summary.triage_state must be an object."
        )
    _require(
        triage_state.get("duplicate_group_count", 0) >= 1,
        "Backlog-triage contract smoke failed: duplicate_group_count must be at least 1.",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
