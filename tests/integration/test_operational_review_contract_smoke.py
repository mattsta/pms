"""Integration test for operational-review contract smoke automation."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def test_operational_review_contract_smoke(tmp_path: Path) -> None:
    data_dir = tmp_path / "operational-review-contract"
    env = os.environ.copy()
    env["PMS_DATA_DIR"] = str(data_dir)
    env["PMS_DATABASE_PATH"] = str(data_dir / "pms.db")
    env["PMS_LOG_DIR"] = str(data_dir / "logs")
    env["PMS_OPERATIONS_SUFFIX"] = "pytest"

    result = subprocess.run(
        ["./scripts/run_operational_review_contract_smoke.sh"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)

    summary_path = data_dir / "operational-review.summary.json"
    summary = json.loads(summary_path.read_text())

    assert summary["project"]["name"]
    assert summary["project"]["id"]
    assert summary["execution_ids"]["plan_id"]
    assert summary["execution_ids"]["review_task_id"]
    assert summary["execution_ids"]["queue_id"]
    assert summary["review_state"]["reviewed_at"]
    assert summary["review_state"]["reviewed_by"]

    artifacts = summary["artifacts"]
    for key in (
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
        assert Path(artifacts[key]).is_file()
