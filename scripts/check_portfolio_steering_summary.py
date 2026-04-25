#!/usr/bin/env python3
"""Validate the portfolio-steering scenario summary artifact."""

from __future__ import annotations

import json
import os
from pathlib import Path


def _require(value: object, message: str) -> None:
    if not value:
        raise SystemExit(message)


def main() -> int:
    summary_path = Path(os.environ["PMS_DATA_DIR"]) / "portfolio-steering.summary.json"
    summary = json.loads(summary_path.read_text())

    for section in ("organization", "portfolio", "program"):
        payload = summary.get(section)
        if not isinstance(payload, dict):
            raise SystemExit(
                f"Portfolio-steering contract smoke failed: summary.{section} must be an object."
            )
        _require(
            payload.get("name"),
            f"Portfolio-steering contract smoke failed: {section}.name is missing.",
        )
        _require(
            payload.get("id"),
            f"Portfolio-steering contract smoke failed: {section}.id is missing.",
        )

    execution_ids = summary.get("execution_ids")
    if not isinstance(execution_ids, dict):
        raise SystemExit(
            "Portfolio-steering contract smoke failed: summary.execution_ids must be an object."
        )
    for key in ("api_goal_id", "ui_goal_id", "api_task_id", "ui_task_id"):
        _require(
            execution_ids.get(key),
            f"Portfolio-steering contract smoke failed: execution_ids.{key} is missing.",
        )

    artifacts = summary.get("artifacts")
    if not isinstance(artifacts, dict):
        raise SystemExit(
            "Portfolio-steering contract smoke failed: summary.artifacts must be an object."
        )
    for key in (
        "bootstrap",
        "org_dashboard",
        "portfolio_dashboard",
        "program_dashboard",
        "portfolio_summary",
        "program_summary",
        "portfolio_daily",
        "program_daily",
        "task_graph",
        "api_project_report",
        "ui_project_report",
        "metrics_csv",
    ):
        value = artifacts.get(key)
        _require(
            value,
            f"Portfolio-steering contract smoke failed: artifacts.{key} is missing.",
        )
        artifact_path = Path(value)
        if not artifact_path.is_file() or artifact_path.stat().st_size == 0:
            raise SystemExit(
                f"Portfolio-steering contract smoke failed: artifact {key} missing or empty: {artifact_path}"
            )

    next_steps = summary.get("next_steps")
    if not isinstance(next_steps, dict):
        raise SystemExit(
            "Portfolio-steering contract smoke failed: summary.next_steps must be an object."
        )
    for key in (
        "org_dashboard",
        "portfolio_dashboard",
        "program_dashboard",
        "portfolio_daily",
        "program_daily",
    ):
        value = next_steps.get(key)
        if not isinstance(value, list) or not value:
            raise SystemExit(
                f"Portfolio-steering contract smoke failed: next_steps.{key} must be a non-empty list."
            )

    steering_state = summary.get("steering_state")
    if not isinstance(steering_state, dict):
        raise SystemExit(
            "Portfolio-steering contract smoke failed: summary.steering_state must be an object."
        )
    blocked_by = steering_state.get("task_blocked_by")
    if not isinstance(blocked_by, list) or not blocked_by:
        raise SystemExit(
            "Portfolio-steering contract smoke failed: task_blocked_by must show at least one cross-project dependency."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
