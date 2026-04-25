"""Regression coverage for distributed audit legs sharing one audit workspace."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def test_distributed_auth_then_multiwriter_smokes_share_one_workspace(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "distributed-sequence"
    env = os.environ.copy()
    env["PMS_DATA_DIR"] = str(data_dir)
    env["PMS_DATABASE_PATH"] = str(data_dir / "pms.db")
    env["PMS_LOG_DIR"] = str(data_dir / "logs")

    first = subprocess.run(
        ["bash", "./scripts/run_distributed_auth_recovery_contract_smoke.sh"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
    )
    if first.returncode != 0:
        raise AssertionError(first.stdout + first.stderr)

    second = subprocess.run(
        ["bash", "./scripts/run_distributed_multiwriter_contract_smoke.sh"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
    )
    if second.returncode != 0:
        raise AssertionError(second.stdout + second.stderr)

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
