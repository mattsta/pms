#!/usr/bin/env python3
"""Validate the agent-execution-loop scenario summary artifact."""

from __future__ import annotations

import json
import os
from pathlib import Path


def _require(value: object, message: str) -> None:
    if not value:
        raise SystemExit(message)


def main() -> int:
    summary_path = Path(os.environ["PMS_DATA_DIR"]) / "agent-loop.summary.json"
    summary = json.loads(summary_path.read_text())

    for section in ("project", "goal", "objective"):
        payload = summary.get(section)
        if not isinstance(payload, dict):
            raise SystemExit(
                f"Agent-loop contract smoke failed: summary.{section} must be an object."
            )
        _require(
            payload.get("name"),
            f"Agent-loop contract smoke failed: {section}.name is missing.",
        )
        _require(
            payload.get("id"),
            f"Agent-loop contract smoke failed: {section}.id is missing.",
        )

    execution_ids = summary.get("execution_ids")
    if not isinstance(execution_ids, dict):
        raise SystemExit(
            "Agent-loop contract smoke failed: summary.execution_ids must be an object."
        )
    for key in (
        "plan_id",
        "primary_task_id",
        "closure_task_id",
        "loop_id",
        "test_run_id",
    ):
        _require(
            execution_ids.get(key),
            f"Agent-loop contract smoke failed: execution_ids.{key} is missing.",
        )

    artifacts = summary.get("artifacts")
    if not isinstance(artifacts, dict):
        raise SystemExit(
            "Agent-loop contract smoke failed: summary.artifacts must be an object."
        )
    for key in (
        "config",
        "prompt",
        "setup_log",
        "guard_json",
        "loop_run_log",
        "loop_list_json",
        "loop_show_json",
        "loop_messages_json",
        "test_server_json",
        "test_record_json",
        "evidence_json",
        "proof_bundle_json",
        "task_complete_json",
        "goal_summary_json",
        "work_review_json",
        "summary_note",
    ):
        value = artifacts.get(key)
        _require(
            value,
            f"Agent-loop contract smoke failed: artifacts.{key} is missing.",
        )
        artifact_path = Path(value)
        if not artifact_path.is_file() or artifact_path.stat().st_size == 0:
            raise SystemExit(
                f"Agent-loop contract smoke failed: artifact {key} missing or empty: {artifact_path}"
            )

    next_steps = summary.get("next_steps")
    if not isinstance(next_steps, dict):
        raise SystemExit(
            "Agent-loop contract smoke failed: summary.next_steps must be an object."
        )
    for key in ("task_complete", "goal_summary", "work_review"):
        value = next_steps.get(key)
        if not isinstance(value, list) or not value:
            raise SystemExit(
                f"Agent-loop contract smoke failed: next_steps.{key} must be a non-empty list."
            )

    loop_state = summary.get("loop_state")
    if not isinstance(loop_state, dict):
        raise SystemExit(
            "Agent-loop contract smoke failed: summary.loop_state must be an object."
        )
    _require(
        loop_state.get("loop_status"),
        "Agent-loop contract smoke failed: loop_state.loop_status is missing.",
    )
    if (
        not isinstance(loop_state.get("messages_count"), int)
        or loop_state["messages_count"] < 2
    ):
        raise SystemExit(
            "Agent-loop contract smoke failed: loop_state.messages_count must be at least 2."
        )
    if (
        not isinstance(loop_state.get("proof_evidence_total"), int)
        or loop_state["proof_evidence_total"] < 3
    ):
        raise SystemExit(
            "Agent-loop contract smoke failed: proof bundle must include at least three evidence entries."
        )
    if (
        not isinstance(loop_state.get("proof_successful_test_runs"), int)
        or loop_state["proof_successful_test_runs"] < 1
    ):
        raise SystemExit(
            "Agent-loop contract smoke failed: proof bundle must include a successful test run."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
