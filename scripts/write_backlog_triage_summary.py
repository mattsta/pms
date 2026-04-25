#!/usr/bin/env python3
"""Build the backlog-triage scenario summary artifact."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pms.utils.atomic_files import write_json_atomic


def _load(path_env: str) -> Any:
    return json.loads(Path(os.environ[path_env]).read_text())


def _extract_next_steps(payload: Any) -> list[str]:
    if isinstance(payload, dict):
        steps = payload.get("next_steps")
        if isinstance(steps, list):
            return steps
        items = payload.get("items")
        if isinstance(items, list) and items and isinstance(items[0], dict):
            child_steps = items[0].get("next_steps")
            if isinstance(child_steps, list):
                return child_steps
        return []
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        steps = payload[0].get("next_steps")
        if isinstance(steps, list):
            return steps
    return []


def _extract_links(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        links = payload.get("links")
        if isinstance(links, dict):
            return links
        items = payload.get("items")
        if isinstance(items, list) and items and isinstance(items[0], dict):
            child_links = items[0].get("links")
            if isinstance(child_links, dict):
                return child_links
        return {}
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        links = payload[0].get("links")
        if isinstance(links, dict):
            return links
    return {}


def _extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        items = payload.get("items")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def main() -> int:
    dashboard = _load("PMS_BACKLOG_DASHBOARD_PATH")
    ready = _load("PMS_BACKLOG_READY_PATH")
    available = _load("PMS_BACKLOG_AVAILABLE_PATH")
    duplicates = _load("PMS_BACKLOG_DUPLICATES_PATH")
    merge_preview = _load("PMS_BACKLOG_MERGE_PREVIEW_PATH")
    queue_presets = _load("PMS_BACKLOG_QUEUE_PRESETS_PATH")
    queue_run = _load("PMS_BACKLOG_QUEUE_RUN_PATH")
    daily = _load("PMS_BACKLOG_DAILY_PATH")
    lineage = _load("PMS_BACKLOG_LINEAGE_PATH")

    summary = {
        "project": {
            "name": os.environ["PMS_BACKLOG_PROJECT_NAME"],
            "id": os.environ["PMS_BACKLOG_PROJECT_ID"],
        },
        "execution_ids": {
            "plan_id": os.environ["PMS_BACKLOG_PLAN_ID"],
            "critical_task_id": os.environ["PMS_BACKLOG_CRITICAL_TASK_ID"],
            "high_task_id": os.environ["PMS_BACKLOG_HIGH_TASK_ID"],
            "duplicate_primary_id": os.environ["PMS_BACKLOG_DUPLICATE_PRIMARY_ID"],
            "duplicate_secondary_id": os.environ["PMS_BACKLOG_DUPLICATE_SECONDARY_ID"],
            "queue_id": os.environ["PMS_BACKLOG_QUEUE_ID"],
        },
        "artifacts": {
            "bootstrap": os.environ["PMS_BACKLOG_BOOTSTRAP_PATH"],
            "dashboard": os.environ["PMS_BACKLOG_DASHBOARD_PATH"],
            "ready_json": os.environ["PMS_BACKLOG_READY_PATH"],
            "available_json": os.environ["PMS_BACKLOG_AVAILABLE_PATH"],
            "duplicates_json": os.environ["PMS_BACKLOG_DUPLICATES_PATH"],
            "merge_preview_json": os.environ["PMS_BACKLOG_MERGE_PREVIEW_PATH"],
            "queue_presets_json": os.environ["PMS_BACKLOG_QUEUE_PRESETS_PATH"],
            "queue_run_json": os.environ["PMS_BACKLOG_QUEUE_RUN_PATH"],
            "daily_summary": os.environ["PMS_BACKLOG_DAILY_PATH"],
            "plan_lineage_json": os.environ["PMS_BACKLOG_LINEAGE_PATH"],
            "project_report": os.environ["PMS_BACKLOG_PROJECT_REPORT_PATH"],
            "metrics_csv": os.environ["PMS_BACKLOG_METRICS_PATH"],
        },
        "next_steps": {
            "dashboard": _extract_next_steps(dashboard),
            "ready": _extract_next_steps(ready),
            "available": _extract_next_steps(available),
            "duplicates": _extract_next_steps(duplicates),
            "merge_preview": _extract_next_steps(merge_preview),
            "queue_presets": _extract_next_steps(queue_presets),
            "queue_run": _extract_next_steps(queue_run),
            "daily": _extract_next_steps(daily),
            "lineage": _extract_next_steps(lineage),
        },
        "links": {
            "dashboard": _extract_links(dashboard),
            "ready": _extract_links(ready),
            "available": _extract_links(available),
            "duplicates": _extract_links(duplicates),
            "merge_preview": _extract_links(merge_preview),
            "queue_presets": _extract_links(queue_presets),
            "queue_run": _extract_links(queue_run),
            "daily": _extract_links(daily),
            "lineage": _extract_links(lineage),
        },
        "triage_state": {
            "duplicate_group_count": len(_extract_items(duplicates)),
            "available_count": len(_extract_items(available)),
            "ready_count": len(_extract_items(ready)),
        },
    }

    write_json_atomic(Path(os.environ["PMS_BACKLOG_SUMMARY_PATH"]), summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
