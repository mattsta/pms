from __future__ import annotations

import os
import subprocess
from pathlib import Path


def test_network_interop_benchmark_contract_smoke(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PMS_DATA_DIR"] = str(tmp_path / "pms-data")
    env["PMS_NETWORK_INTEROP_ARTIFACT_ROOT"] = str(tmp_path / "artifacts")
    env["PMS_NETWORK_INTEROP_BENCHMARK_LIMIT"] = "10"
    env["PMS_NETWORK_INTEROP_BENCHMARK_REPETITIONS"] = "1"

    subprocess.run(
        ["bash", "./scripts/run_network_interop_benchmark_contract_smoke.sh"],
        check=True,
        env=env,
        timeout=240,
    )

    latest = (
        Path(env["PMS_NETWORK_INTEROP_ARTIFACT_ROOT"])
        / "latest"
        / "benchmark-bundle.summary.json"
    )
    assert latest.is_file()
    assert latest.parent.is_symlink()
    copied_summary = Path(env["PMS_DATA_DIR"]) / "benchmark-bundle.summary.json"
    assert copied_summary.is_file()
    assert copied_summary.read_text(encoding="utf-8") == latest.read_text(
        encoding="utf-8"
    )
