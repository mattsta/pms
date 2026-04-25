"""Integration test for backlog-triage contract smoke automation."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def test_backlog_triage_contract_smoke(tmp_path: Path) -> None:
    data_dir = tmp_path / "backlog-triage-contract"
    env = os.environ.copy()
    env["PMS_DATA_DIR"] = str(data_dir)
    env["PMS_DATABASE_PATH"] = str(data_dir / "pms.db")
    env["PMS_LOG_DIR"] = str(data_dir / "logs")
    env["PMS_BACKLOG_SUFFIX"] = "pytest"

    result = subprocess.run(
        ["./scripts/run_backlog_triage_contract_smoke.sh"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)

    summary_path = data_dir / "backlog-triage.summary.json"
    summary = json.loads(summary_path.read_text())

    assert summary["project"]["name"]
    assert summary["project"]["id"]
    assert summary["execution_ids"]["plan_id"]
    assert summary["execution_ids"]["critical_task_id"]
    assert summary["execution_ids"]["duplicate_primary_id"]
    assert summary["execution_ids"]["queue_id"]
    assert summary["triage_state"]["duplicate_group_count"] >= 1

    artifacts = summary["artifacts"]
    for key in (
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
        assert Path(artifacts[key]).is_file()
