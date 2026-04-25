"""Integration test for distributed multiwriter contract smoke automation."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def test_distributed_multiwriter_contract_smoke(tmp_path: Path) -> None:
    data_dir = tmp_path / "distributed-multiwriter-contract"
    env = os.environ.copy()
    env["PMS_DATA_DIR"] = str(data_dir)
    env["PMS_DATABASE_PATH"] = str(data_dir / "pms.db")
    env["PMS_LOG_DIR"] = str(data_dir / "logs")

    result = subprocess.run(
        ["bash", "./scripts/run_distributed_multiwriter_contract_smoke.sh"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
    )
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)

    summary_path = data_dir / "distributed-multiwriter.summary.json"
    summary = json.loads(summary_path.read_text())

    assert summary["checkout"]["api_conflict_status"] == "409"
    assert summary["checkout"]["rust_conflict_mentions_checkout_status"] is True
    assert summary["checkout"]["rust_conflict_mentions_force_release"] is True
    assert summary["checkout"]["rust_success_checked_out"] is True
    assert summary["checkout"]["rust_status_count"] == 1
    assert summary["checkout"]["force_release_status"] == "force_released"
    assert summary["checkout"]["python_recheckout_succeeded"] is True

    for artifact in summary["artifacts"].values():
        assert Path(artifact).is_file()

    runtime = subprocess.run(
        ["uv", "run", "pms", "runtime", "status", "--format", "json"],
        check=False,
        capture_output=True,
        text=True,
        env={**env, "PMS_WRITE_MODE": "direct"},
        timeout=30,
    )
    if runtime.returncode != 0:
        raise AssertionError(runtime.stdout + runtime.stderr)
    payload = json.loads(runtime.stdout)
    assert payload["unmanaged_local_processes"] == []
