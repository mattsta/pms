#!/usr/bin/env python3
"""Build the agent-execution-loop scenario summary artifact."""

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
        value = payload.get("next_steps")
        if isinstance(value, list):
            return value
    return []


def _extract_links(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        value = payload.get("links")
        if isinstance(value, dict):
            return value
    return {}


def main() -> int:
    guard = _load("PMS_AGENT_LOOP_GUARD_PATH")
    loop_show = _load("PMS_AGENT_LOOP_LOOP_SHOW_PATH")
    loop_messages = _load("PMS_AGENT_LOOP_LOOP_MESSAGES_PATH")
    evidence_list = _load("PMS_AGENT_LOOP_EVIDENCE_LIST_PATH")
    proof_bundle = _load("PMS_AGENT_LOOP_PROOF_BUNDLE_PATH")
    task_complete = _load("PMS_AGENT_LOOP_TASK_COMPLETE_PATH")
    goal_summary = _load("PMS_AGENT_LOOP_GOAL_SUMMARY_PATH")
    work_review = _load("PMS_AGENT_LOOP_WORK_REVIEW_PATH")
    test_record = _load("PMS_AGENT_LOOP_TEST_RECORD_PATH")

    loop_payload = loop_show.get("loop") if isinstance(loop_show, dict) else {}
    proof_summary = (
        proof_bundle.get("summary") if isinstance(proof_bundle, dict) else {}
    )
    messages_count = len(loop_messages) if isinstance(loop_messages, list) else 0
    evidence_items = (
        evidence_list.get("items") if isinstance(evidence_list, dict) else []
    )

    summary = {
        "project": {
            "name": os.environ["PMS_AGENT_LOOP_PROJECT_NAME"],
            "id": os.environ["PMS_AGENT_LOOP_PROJECT_ID"],
        },
        "goal": {
            "name": os.environ["PMS_AGENT_LOOP_GOAL_NAME"],
            "id": os.environ["PMS_AGENT_LOOP_GOAL_ID"],
        },
        "objective": {
            "name": os.environ["PMS_AGENT_LOOP_OBJECTIVE_NAME"],
            "id": os.environ["PMS_AGENT_LOOP_OBJECTIVE_ID"],
        },
        "execution_ids": {
            "plan_id": os.environ["PMS_AGENT_LOOP_PLAN_ID"],
            "primary_task_id": os.environ["PMS_AGENT_LOOP_PRIMARY_TASK_ID"],
            "closure_task_id": os.environ["PMS_AGENT_LOOP_CLOSURE_TASK_ID"],
            "loop_id": os.environ["PMS_AGENT_LOOP_LOOP_ID"],
            "test_run_id": os.environ["PMS_AGENT_LOOP_TEST_RUN_ID"],
        },
        "artifacts": {
            "config": os.environ["PMS_AGENT_LOOP_CONFIG_PATH"],
            "prompt": os.environ["PMS_AGENT_LOOP_PROMPT_PATH"],
            "setup_log": os.environ["PMS_AGENT_LOOP_SETUP_LOG_PATH"],
            "guard_json": os.environ["PMS_AGENT_LOOP_GUARD_PATH"],
            "loop_run_log": os.environ["PMS_AGENT_LOOP_LOOP_RUN_LOG_PATH"],
            "loop_list_json": os.environ["PMS_AGENT_LOOP_LOOPS_PATH"],
            "loop_show_json": os.environ["PMS_AGENT_LOOP_LOOP_SHOW_PATH"],
            "loop_messages_json": os.environ["PMS_AGENT_LOOP_LOOP_MESSAGES_PATH"],
            "test_server_json": os.environ["PMS_AGENT_LOOP_TEST_SERVER_PATH"],
            "test_record_json": os.environ["PMS_AGENT_LOOP_TEST_RECORD_PATH"],
            "evidence_json": os.environ["PMS_AGENT_LOOP_EVIDENCE_LIST_PATH"],
            "proof_bundle_json": os.environ["PMS_AGENT_LOOP_PROOF_BUNDLE_PATH"],
            "task_complete_json": os.environ["PMS_AGENT_LOOP_TASK_COMPLETE_PATH"],
            "goal_summary_json": os.environ["PMS_AGENT_LOOP_GOAL_SUMMARY_PATH"],
            "work_review_json": os.environ["PMS_AGENT_LOOP_WORK_REVIEW_PATH"],
            "summary_note": os.environ["PMS_AGENT_LOOP_SUMMARY_NOTE_PATH"],
        },
        "next_steps": {
            "guard": _extract_next_steps(guard),
            "task_complete": _extract_next_steps(task_complete),
            "goal_summary": _extract_next_steps(goal_summary),
            "work_review": _extract_next_steps(work_review),
        },
        "links": {
            "task_complete": _extract_links(task_complete),
            "goal_summary": _extract_links(goal_summary),
            "work_review": _extract_links(work_review),
        },
        "loop_state": {
            "loop_status": loop_payload.get("status"),
            "stop_reason": loop_payload.get("stop_reason"),
            "iterations": loop_payload.get("iterations"),
            "messages_count": messages_count,
            "guard_blocked": guard.get("blocked") if isinstance(guard, dict) else None,
            "proof_evidence_total": proof_summary.get("evidence_total"),
            "proof_test_runs": proof_summary.get("test_runs"),
            "proof_successful_test_runs": proof_summary.get("successful_test_runs"),
            "attached_evidence_items": len(evidence_items)
            if isinstance(evidence_items, list)
            else 0,
            "recorded_test_command": test_record.get("command")
            if isinstance(test_record, dict)
            else None,
        },
    }

    write_json_atomic(Path(os.environ["PMS_AGENT_LOOP_SUMMARY_PATH"]), summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
