"""Integration test for user start -> go -> observe contract smoke automation."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def test_user_start_go_observe_contract_smoke(tmp_path: Path) -> None:
    data_dir = tmp_path / "user-contract"
    env = os.environ.copy()
    env["PMS_DATA_DIR"] = str(data_dir)
    env["PMS_DATABASE_PATH"] = str(data_dir / "pms.db")
    env["PMS_LOG_DIR"] = str(data_dir / "logs")
    env["PMS_USER_FLOW_SUFFIX"] = "pytest"

    result = subprocess.run(
        ["./scripts/run_user_start_go_observe_contract_smoke.sh"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)

    summary_path = data_dir / "user-start.summary.json"
    summary = json.loads(summary_path.read_text())

    assert summary["project"]["name"]
    assert summary["project"]["id"]
    assert summary["task"]["title"]
    assert summary["task"]["id"]

    artifacts = summary["artifacts"]
    assert Path(artifacts["start_guide"]).is_file()
    assert Path(artifacts["dashboard"]).is_file()
    assert Path(artifacts["daily_summary"]).is_file()

    next_steps = summary["next_steps"]
    assert isinstance(next_steps["guide"], list)
    assert isinstance(next_steps["dashboard"], list)
    assert isinstance(next_steps["daily"], list)
