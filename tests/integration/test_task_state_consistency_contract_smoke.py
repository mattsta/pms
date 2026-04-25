from __future__ import annotations

import os
import subprocess
from pathlib import Path


def test_task_state_consistency_contract_smoke(tmp_path: Path) -> None:
    data_dir = tmp_path / "task-state-contract"
    env = os.environ.copy()
    env["PMS_DATA_DIR"] = str(data_dir)
    env["PMS_DATABASE_PATH"] = str(data_dir / "pms.db")
    env["PMS_LOG_DIR"] = str(data_dir / "logs")
    env["PMS_TASK_STATE_ITERATIONS"] = "1"

    result = subprocess.run(
        ["bash", "./scripts/run_task_state_consistency_smoke.sh"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=180,
    )
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)

    assert (data_dir / "task-list-1.json").is_file()
    assert (data_dir / "project-show-1.json").is_file()
    assert (data_dir / "goal-summary-1.json").is_file()
    assert (data_dir / "objective-list-1.json").is_file()
    assert (data_dir / "dashboard-1.json").is_file()
