"""Integration test for authoring reliability smoke automation."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def test_authoring_reliability_smoke_ignores_prefer_server_runtime(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "authoring-reliability"
    env = os.environ.copy()
    env["PMS_DATA_DIR"] = str(data_dir)
    env["PMS_DATABASE_PATH"] = str(data_dir / "pms.db")
    env["PMS_LOG_DIR"] = str(data_dir / "logs")
    env["PMS_WRITE_MODE"] = "prefer_server"
    env["PMS_SERVER_BASE_URL"] = "http://127.0.0.1:8000"

    result = subprocess.run(
        ["bash", "./scripts/run_authoring_reliability_smoke.sh"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=180,
    )
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)

    summary_path = data_dir / "goal-summary.txt"
    assert summary_path.is_file()
    assert "Objectives: 0/1 | Key Results: 0/0" in summary_path.read_text(
        encoding="utf-8"
    )
