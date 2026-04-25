"""Integration test for portfolio-steering contract smoke automation."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def test_portfolio_steering_contract_smoke(tmp_path: Path) -> None:
    data_dir = tmp_path / "portfolio-steering-contract"
    env = os.environ.copy()
    env["PMS_DATA_DIR"] = str(data_dir)
    env["PMS_DATABASE_PATH"] = str(data_dir / "pms.db")
    env["PMS_LOG_DIR"] = str(data_dir / "logs")
    env["PMS_STEERING_SUFFIX"] = "pytest"

    result = subprocess.run(
        ["./scripts/run_portfolio_steering_contract_smoke.sh"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)

    summary_path = data_dir / "portfolio-steering.summary.json"
    summary = json.loads(summary_path.read_text())

    assert summary["organization"]["id"]
    assert summary["portfolio"]["id"]
    assert summary["program"]["id"]
    assert summary["execution_ids"]["api_goal_id"]
    assert summary["execution_ids"]["ui_goal_id"]
    assert summary["execution_ids"]["api_task_id"]
    assert summary["execution_ids"]["ui_task_id"]
    assert summary["steering_state"]["task_blocked_by"]

    artifacts = summary["artifacts"]
    for key in (
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
        assert Path(artifacts[key]).is_file()
