"""Integration test for agent-execution-loop contract smoke automation."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def test_agent_execution_loop_contract_smoke(tmp_path: Path) -> None:
    data_dir = tmp_path / "agent-loop-contract"
    env = os.environ.copy()
    env["PMS_DATA_DIR"] = str(data_dir)
    env["PMS_DATABASE_PATH"] = str(data_dir / "pms.db")
    env["PMS_LOG_DIR"] = str(data_dir / "logs")
    env["PMS_AGENT_LOOP_SUFFIX"] = "pytest"

    result = subprocess.run(
        ["./scripts/run_agent_execution_loop_contract_smoke.sh"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=480,
    )
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)

    summary_path = data_dir / "agent-loop.summary.json"
    summary = json.loads(summary_path.read_text())

    assert summary["project"]["name"]
    assert summary["project"]["id"]
    assert summary["goal"]["id"]
    assert summary["objective"]["id"]
    assert summary["execution_ids"]["plan_id"]
    assert summary["execution_ids"]["primary_task_id"]
    assert summary["execution_ids"]["loop_id"]
    assert summary["execution_ids"]["test_run_id"]
    assert summary["loop_state"]["messages_count"] >= 2
    assert summary["loop_state"]["proof_successful_test_runs"] >= 1

    artifacts = summary["artifacts"]
    for key in (
        "config",
        "prompt",
        "guard_json",
        "loop_show_json",
        "loop_messages_json",
        "test_record_json",
        "evidence_json",
        "proof_bundle_json",
        "task_complete_json",
        "goal_summary_json",
        "work_review_json",
    ):
        assert Path(artifacts[key]).is_file()
