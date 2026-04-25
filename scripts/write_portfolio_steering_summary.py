#!/usr/bin/env python3
"""Build the portfolio-steering scenario summary artifact."""

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


def _extract_links(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        links = payload.get("links")
        if isinstance(links, dict):
            return links
    return {}


def main() -> int:
    org_dashboard = _load("PMS_STEERING_ORG_DASHBOARD_PATH")
    portfolio_dashboard = _load("PMS_STEERING_PORTFOLIO_DASHBOARD_PATH")
    program_dashboard = _load("PMS_STEERING_PROGRAM_DASHBOARD_PATH")
    portfolio_summary = _load("PMS_STEERING_PORTFOLIO_SUMMARY_PATH")
    program_summary = _load("PMS_STEERING_PROGRAM_SUMMARY_PATH")
    portfolio_daily = _load("PMS_STEERING_PORTFOLIO_DAILY_PATH")
    program_daily = _load("PMS_STEERING_PROGRAM_DAILY_PATH")
    task_graph = _load("PMS_STEERING_TASK_GRAPH_PATH")

    summary = {
        "organization": {
            "name": os.environ["PMS_STEERING_ORG_NAME"],
            "id": os.environ["PMS_STEERING_ORG_ID"],
        },
        "portfolio": {
            "name": os.environ["PMS_STEERING_PORTFOLIO_NAME"],
            "id": os.environ["PMS_STEERING_PORTFOLIO_ID"],
        },
        "program": {
            "name": os.environ["PMS_STEERING_PROGRAM_NAME"],
            "id": os.environ["PMS_STEERING_PROGRAM_ID"],
        },
        "projects": {
            "api": {
                "name": os.environ["PMS_STEERING_API_PROJECT_NAME"],
                "id": os.environ["PMS_STEERING_API_PROJECT_ID"],
            },
            "ui": {
                "name": os.environ["PMS_STEERING_UI_PROJECT_NAME"],
                "id": os.environ["PMS_STEERING_UI_PROJECT_ID"],
            },
        },
        "execution_ids": {
            "api_goal_id": os.environ["PMS_STEERING_API_GOAL_ID"],
            "ui_goal_id": os.environ["PMS_STEERING_UI_GOAL_ID"],
            "api_task_id": os.environ["PMS_STEERING_API_TASK_ID"],
            "ui_task_id": os.environ["PMS_STEERING_UI_TASK_ID"],
        },
        "artifacts": {
            "bootstrap": os.environ["PMS_STEERING_BOOTSTRAP_PATH"],
            "org_dashboard": os.environ["PMS_STEERING_ORG_DASHBOARD_PATH"],
            "portfolio_dashboard": os.environ["PMS_STEERING_PORTFOLIO_DASHBOARD_PATH"],
            "program_dashboard": os.environ["PMS_STEERING_PROGRAM_DASHBOARD_PATH"],
            "portfolio_summary": os.environ["PMS_STEERING_PORTFOLIO_SUMMARY_PATH"],
            "program_summary": os.environ["PMS_STEERING_PROGRAM_SUMMARY_PATH"],
            "portfolio_daily": os.environ["PMS_STEERING_PORTFOLIO_DAILY_PATH"],
            "program_daily": os.environ["PMS_STEERING_PROGRAM_DAILY_PATH"],
            "task_graph": os.environ["PMS_STEERING_TASK_GRAPH_PATH"],
            "api_project_report": os.environ["PMS_STEERING_API_REPORT_PATH"],
            "ui_project_report": os.environ["PMS_STEERING_UI_REPORT_PATH"],
            "metrics_csv": os.environ["PMS_STEERING_METRICS_PATH"],
        },
        "next_steps": {
            "org_dashboard": _extract_next_steps(org_dashboard),
            "portfolio_dashboard": _extract_next_steps(portfolio_dashboard),
            "program_dashboard": _extract_next_steps(program_dashboard),
            "portfolio_daily": _extract_next_steps(portfolio_daily),
            "program_daily": _extract_next_steps(program_daily),
        },
        "links": {
            "org_dashboard": _extract_links(org_dashboard),
            "portfolio_dashboard": _extract_links(portfolio_dashboard),
            "program_dashboard": _extract_links(program_dashboard),
        },
        "steering_state": {
            "portfolio_risk_level": portfolio_summary.get("risk_level"),
            "program_risk_level": program_summary.get("risk_level"),
            "task_blocked_by": task_graph.get("blocked_by", []),
            "task_blocking": task_graph.get("blocking", []),
        },
    }

    write_json_atomic(Path(os.environ["PMS_STEERING_SUMMARY_PATH"]), summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
