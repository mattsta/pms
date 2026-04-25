"""Integration test for incident response contract smoke automation."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def test_incident_response_contract_smoke(tmp_path: Path) -> None:
    data_dir = tmp_path / "incident-contract"
    env = os.environ.copy()
    env["PMS_DATA_DIR"] = str(data_dir)
    env["PMS_DATABASE_PATH"] = str(data_dir / "pms.db")
    env["PMS_LOG_DIR"] = str(data_dir / "logs")
    env["PMS_INCIDENT_SUFFIX"] = "pytest"

    result = subprocess.run(
        ["./scripts/run_incident_response_contract_smoke.sh"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)

    summary_path = data_dir / "incident.summary.json"
    summary = json.loads(summary_path.read_text())

    assert summary["project"]["name"]
    assert summary["project"]["id"]
    assert summary["task_ids"]["triage"]
    assert summary["task_ids"]["mitigation"]
    assert summary["task_ids"]["comms"]
    assert summary["task_ids"]["postmortem"]
    assert summary["extension_ids"]["custom_field_id"]
    assert summary["extension_ids"]["automation_rule_id"]
    assert summary["extension_ids"]["queue_id"]

    artifacts = summary["artifacts"]
    for key in (
        "daily_summary",
        "project_report",
        "history_json",
        "metrics_csv",
        "queue_run_json",
    ):
        assert Path(artifacts[key]).is_file()
