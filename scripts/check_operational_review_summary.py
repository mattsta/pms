#!/usr/bin/env python3
"""Validate the operational-review scenario summary artifact."""

from __future__ import annotations

import json
import os
from pathlib import Path


def _require(value: object, message: str) -> None:
    if not value:
        raise SystemExit(message)


def main() -> int:
    summary_path = Path(os.environ["PMS_DATA_DIR"]) / "operational-review.summary.json"
    summary = json.loads(summary_path.read_text())

    project = summary.get("project")
    if not isinstance(project, dict):
        raise SystemExit(
            "Operational-review contract smoke failed: summary.project must be an object."
        )
    _require(
        project.get("name"),
        "Operational-review contract smoke failed: project.name is missing.",
    )
    _require(
        project.get("id"),
        "Operational-review contract smoke failed: project.id is missing.",
    )

    execution_ids = summary.get("execution_ids")
    if not isinstance(execution_ids, dict):
        raise SystemExit(
            "Operational-review contract smoke failed: summary.execution_ids must be an object."
        )
    for key in (
        "plan_id",
        "review_task_id",
        "status_task_id",
        "blocked_task_id",
        "queue_id",
    ):
        _require(
            execution_ids.get(key),
            f"Operational-review contract smoke failed: execution_ids.{key} is missing.",
        )

    artifacts = summary.get("artifacts")
    if not isinstance(artifacts, dict):
        raise SystemExit(
            "Operational-review contract smoke failed: summary.artifacts must be an object."
        )
    for key in (
        "bootstrap",
        "dashboard",
        "daily_summary",
        "review_json",
        "blocked_tasks_json",
        "ready_tasks_json",
        "queue_run_json",
        "plan_lineage_json",
        "project_report",
        "history_json",
        "metrics_csv",
    ):
        value = artifacts.get(key)
        _require(
            value,
            f"Operational-review contract smoke failed: artifacts.{key} is missing.",
        )
        artifact_path = Path(value)
        if not artifact_path.is_file() or artifact_path.stat().st_size == 0:
            raise SystemExit(
                f"Operational-review contract smoke failed: artifact {key} missing or empty: {artifact_path}"
            )

    next_steps = summary.get("next_steps")
    if not isinstance(next_steps, dict):
        raise SystemExit(
            "Operational-review contract smoke failed: summary.next_steps must be an object."
        )
    for key in ("dashboard", "daily", "review", "queue_run", "lineage"):
        value = next_steps.get(key)
        if not isinstance(value, list) or not value:
            raise SystemExit(
                f"Operational-review contract smoke failed: next_steps.{key} must be a non-empty list."
            )

    review_state = summary.get("review_state")
    if not isinstance(review_state, dict):
        raise SystemExit(
            "Operational-review contract smoke failed: summary.review_state must be an object."
        )
    _require(
        review_state.get("reviewed_at"),
        "Operational-review contract smoke failed: review_state.reviewed_at is missing.",
    )
    _require(
        review_state.get("reviewed_by"),
        "Operational-review contract smoke failed: review_state.reviewed_by is missing.",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
