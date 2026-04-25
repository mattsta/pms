#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/run_helpers.sh"

CONTRACT_TIMEOUT_SECONDS="${PMS_DROPIN_CONTRACT_TIMEOUT_SECONDS:-120}"
pms_setup_python_runtime "$ROOT_DIR"
pms_prepare_data_dir "$ROOT_DIR" "dropin-contract"

echo "Running drop-in contract smoke"
echo "  run_mode: $RUN_MODE"
echo "  data_dir: $PMS_DATA_DIR"
echo "  contract_timeout_seconds: $CONTRACT_TIMEOUT_SECONDS"

pms_run_contract_flow \
  "Drop-in contract smoke" \
  "$CONTRACT_TIMEOUT_SECONDS" \
  "$ROOT_DIR" \
  "$ROOT_DIR/scripts/run_dropin_start_go_extend_grow.sh"

summary_path="$PMS_DATA_DIR/dropin-grow.summary.json"
if [[ ! -s "$summary_path" ]]; then
  echo "Drop-in contract smoke failed: summary missing at $summary_path" >&2
  exit 1
fi

py - <<'PY'
import json
import os
from pathlib import Path

summary_path = Path(os.environ["PMS_DATA_DIR"]) / "dropin-grow.summary.json"
data = json.loads(summary_path.read_text())

required_ids = [
    "project_name",
    "project_id",
    "task_id",
    "custom_field_id",
    "automation_rule_id",
    "queue_id",
]
missing = [key for key in required_ids if not data.get(key)]
if missing:
    raise SystemExit(
        "Drop-in contract smoke failed: missing summary keys: "
        + ", ".join(sorted(missing))
    )

artifacts = data.get("artifacts")
if not isinstance(artifacts, dict):
    raise SystemExit(
        "Drop-in contract smoke failed: summary.artifacts must be an object."
    )

for key in ("daily_summary", "project_report"):
    artifact_path = artifacts.get(key)
    if not artifact_path:
        raise SystemExit(f"Drop-in contract smoke failed: missing artifact path {key}.")
    resolved = Path(artifact_path)
    if not resolved.is_file() or resolved.stat().st_size == 0:
        raise SystemExit(
            f"Drop-in contract smoke failed: artifact {key} not found or empty: {resolved}"
        )

loop_enabled = os.environ.get("PMS_GROWTH_RUN_LOOP_SETUP", "1") == "1"
if loop_enabled:
    for key in ("loop_config", "loop_prompt"):
        artifact_path = artifacts.get(key)
        if not artifact_path:
            raise SystemExit(
                f"Drop-in contract smoke failed: missing loop artifact path {key}."
            )
        resolved = Path(artifact_path)
        if not resolved.is_file() or resolved.stat().st_size == 0:
            raise SystemExit(
                f"Drop-in contract smoke failed: loop artifact {key} not found: {resolved}"
            )

plugin_enabled = os.environ.get("PMS_GROWTH_RUN_PLUGIN", "1") == "1"
plugin_path = artifacts.get("plugin_path")
if plugin_enabled:
    if not plugin_path:
        raise SystemExit(
            "Drop-in contract smoke failed: plugin_path missing while plugin path is enabled."
        )
    if not Path(plugin_path).is_dir():
        raise SystemExit(
            f"Drop-in contract smoke failed: plugin path does not exist: {plugin_path}"
        )
else:
    if plugin_path is not None:
        raise SystemExit(
            "Drop-in contract smoke failed: plugin_path must be null when plugin path is disabled."
        )
PY

echo "Drop-in contract smoke completed."
echo "  summary: $summary_path"
