#!/usr/bin/env python3
"""Build the operational-review scenario summary artifact."""

from __future__ import annotations

import json
import os
from pathlib import Path

from pms.utils.atomic_files import write_json_atomic


def _load(path_env: str) -> dict:
    return json.loads(Path(os.environ[path_env]).read_text())


def _count_items(payload: object) -> int:
    if isinstance(payload, dict):
        items = payload.get("items")
        if isinstance(items, list):
            return payload.get("total_count", len(items))
        total_count = payload.get("total_count")
        if isinstance(total_count, int):
            return total_count
        return 0
    if isinstance(payload, list):
        return len(payload)
    return 0


def main() -> int:
    dashboard = _load("PMS_OPERATIONS_DASHBOARD_PATH")
    daily = _load("PMS_OPERATIONS_DAILY_PATH")
    review = _load("PMS_OPERATIONS_REVIEW_PATH")
    blocked = _load("PMS_OPERATIONS_BLOCKED_PATH")
    ready = _load("PMS_OPERATIONS_READY_PATH")
    queue_run = _load("PMS_OPERATIONS_QUEUE_RUN_PATH")
    lineage = _load("PMS_OPERATIONS_LINEAGE_PATH")

    summary = {
        "project": {
            "name": os.environ["PMS_OPERATIONS_PROJECT_NAME"],
            "id": os.environ["PMS_OPERATIONS_PROJECT_ID"],
        },
        "execution_ids": {
            "plan_id": os.environ["PMS_OPERATIONS_PLAN_ID"],
            "review_task_id": os.environ["PMS_OPERATIONS_REVIEW_TASK_ID"],
            "status_task_id": os.environ["PMS_OPERATIONS_STATUS_TASK_ID"],
            "blocked_task_id": os.environ["PMS_OPERATIONS_BLOCKED_TASK_ID"],
            "queue_id": os.environ["PMS_OPERATIONS_QUEUE_ID"],
        },
        "artifacts": {
            "bootstrap": os.environ["PMS_OPERATIONS_BOOTSTRAP_PATH"],
            "dashboard": os.environ["PMS_OPERATIONS_DASHBOARD_PATH"],
            "daily_summary": os.environ["PMS_OPERATIONS_DAILY_PATH"],
            "review_json": os.environ["PMS_OPERATIONS_REVIEW_PATH"],
            "blocked_tasks_json": os.environ["PMS_OPERATIONS_BLOCKED_PATH"],
            "ready_tasks_json": os.environ["PMS_OPERATIONS_READY_PATH"],
            "queue_run_json": os.environ["PMS_OPERATIONS_QUEUE_RUN_PATH"],
            "plan_lineage_json": os.environ["PMS_OPERATIONS_LINEAGE_PATH"],
            "project_report": os.environ["PMS_OPERATIONS_PROJECT_REPORT_PATH"],
            "history_json": os.environ["PMS_OPERATIONS_HISTORY_PATH"],
            "metrics_csv": os.environ["PMS_OPERATIONS_METRICS_PATH"],
        },
        "next_steps": {
            "dashboard": dashboard.get("next_steps", []),
            "daily": daily.get("next_steps", []),
            "review": review.get("next_steps", []),
            "queue_run": queue_run.get("next_steps", []),
            "lineage": lineage.get("next_steps", []),
        },
        "links": {
            "dashboard": dashboard.get("links", {}),
            "daily": daily.get("links", {}),
            "review": review.get("links", {}),
            "queue_run": queue_run.get("links", {}),
            "lineage": lineage.get("links", {}),
        },
        "review_state": {
            "blocked_count": _count_items(blocked),
            "ready_count": _count_items(ready),
            "reviewed_at": review.get("reviewed_at"),
            "reviewed_by": review.get("reviewed_by"),
        },
    }

    write_json_atomic(Path(os.environ["PMS_OPERATIONS_SUMMARY_PATH"]), summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
