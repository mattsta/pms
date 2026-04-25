"""Integration test for team handoff contract smoke automation."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def test_team_handoff_contract_smoke(tmp_path: Path) -> None:
    data_dir = tmp_path / "team-handoff-contract"
    env = os.environ.copy()
    env["PMS_DATA_DIR"] = str(data_dir)
    env["PMS_DATABASE_PATH"] = str(data_dir / "pms.db")
    env["PMS_LOG_DIR"] = str(data_dir / "logs")
    env["PMS_HANDOFF_SUFFIX"] = "pytest"

    result = subprocess.run(
        ["./scripts/run_team_handoff_contract_smoke.sh"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)

    summary_path = data_dir / "team-handoff.summary.json"
    summary = json.loads(summary_path.read_text())

    assert summary["organization"]["name"]
    assert summary["organization"]["id"]
    assert summary["projects"]["build"]["id"]
    assert summary["projects"]["release"]["id"]
    assert summary["tasks"]["build_task_id"]
    assert summary["tasks"]["release_task_id"]
    assert summary["extension_ids"]["custom_field_id"]
    assert summary["extension_ids"]["automation_rule_id"]
    assert summary["extension_ids"]["queue_id"]

    artifacts = summary["artifacts"]
    for key in (
        "organization_daily_summary",
        "release_project_daily_summary",
        "build_project_report",
        "release_project_report",
        "metrics_csv",
        "history_json",
        "queue_run_json",
    ):
        assert Path(artifacts[key]).is_file()
