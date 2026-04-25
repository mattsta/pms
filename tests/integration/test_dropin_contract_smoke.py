"""Integration test for drop-in growth contract smoke automation."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def test_dropin_growth_contract_smoke(tmp_path: Path) -> None:
    data_dir = tmp_path / "dropin-contract"
    env = os.environ.copy()
    env["PMS_DATA_DIR"] = str(data_dir)
    env["PMS_DATABASE_PATH"] = str(data_dir / "pms.db")
    env["PMS_LOG_DIR"] = str(data_dir / "logs")
    env["PMS_GROWTH_RUN_PLUGIN"] = "0"
    env["PMS_GROWTH_RUN_LOOP_SETUP"] = "0"
    env["PMS_GROWTH_SUFFIX"] = "pytest"

    result = subprocess.run(
        ["./scripts/run_dropin_contract_smoke.sh"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)

    summary_path = data_dir / "dropin-grow.summary.json"
    summary = json.loads(summary_path.read_text())

    assert summary["project_name"]
    assert summary["project_id"]
    assert summary["task_id"]
    assert summary["custom_field_id"]
    assert summary["automation_rule_id"]
    assert summary["queue_id"]

    artifacts = summary["artifacts"]
    assert Path(artifacts["daily_summary"]).is_file()
    assert Path(artifacts["project_report"]).is_file()
    assert artifacts["plugin_path"] is None
    assert artifacts["loop_config"] is None
    assert artifacts["loop_prompt"] is None
