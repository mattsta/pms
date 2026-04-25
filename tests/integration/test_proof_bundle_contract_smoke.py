from __future__ import annotations

import os
import subprocess
from pathlib import Path


def test_proof_bundle_contract_smoke(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PMS_DATA_DIR"] = str(tmp_path / "pms-data")

    subprocess.run(
        ["bash", "./scripts/run_proof_bundle_contract_smoke.sh"],
        check=True,
        env=env,
        timeout=180,
    )

    assert (Path(env["PMS_DATA_DIR"]) / "proof-bundle.summary.json").is_file()
