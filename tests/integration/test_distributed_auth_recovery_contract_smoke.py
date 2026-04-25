"""Integration test for distributed auth recovery contract smoke automation."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def test_distributed_auth_recovery_contract_smoke(tmp_path: Path) -> None:
    data_dir = tmp_path / "distributed-auth-contract"
    env = os.environ.copy()
    env["PMS_DATA_DIR"] = str(data_dir)
    env["PMS_DATABASE_PATH"] = str(data_dir / "pms.db")
    env["PMS_LOG_DIR"] = str(data_dir / "logs")

    result = subprocess.run(
        ["./scripts/run_distributed_auth_recovery_contract_smoke.sh"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
    )
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)

    summary_path = data_dir / "distributed-auth-recovery.summary.json"
    summary = json.loads(summary_path.read_text())

    assert summary["server"]["url"]
    assert summary["auth"]["limited_key_id"]
    assert summary["auth"]["before_active"] is True
    assert summary["auth"]["after_deactivate_active"] is False
    assert summary["auth"]["after_restore_active"] is True
    assert summary["auth"]["limited_key_admin_status"] == "403"
    assert (
        summary["stale_recovery"]["python_recovery_kind"] == "restore_preferred_server"
    )
    assert summary["stale_recovery"]["rust_mentions_config_show"] is True
    assert summary["stale_recovery"]["rust_mentions_runtime_status"] is True
    assert summary["stale_recovery"]["rust_mentions_prefer_server"] is True

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
