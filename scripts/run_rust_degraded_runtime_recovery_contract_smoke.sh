#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/run_helpers.sh"

CONTRACT_TIMEOUT_SECONDS="${PMS_RUST_RUNTIME_CONTRACT_TIMEOUT_SECONDS:-180}"
pms_setup_python_runtime "$ROOT_DIR"
pms_prepare_data_dir "$ROOT_DIR" "rust-runtime-contract"

echo "Running Rust degraded-runtime recovery contract smoke"
echo "  run_mode: $RUN_MODE"
echo "  data_dir: $PMS_DATA_DIR"
echo "  contract_timeout_seconds: $CONTRACT_TIMEOUT_SECONDS"

pms_run_contract_flow \
  "Rust degraded-runtime recovery contract smoke" \
  "$CONTRACT_TIMEOUT_SECONDS" \
  "$ROOT_DIR" \
  "$ROOT_DIR/scripts/run_rust_degraded_runtime_recovery_flow.sh"

summary_path="$PMS_DATA_DIR/rust-runtime-recovery.summary.json"
if [[ ! -s "$summary_path" ]]; then
  echo "Rust degraded-runtime recovery contract smoke failed: summary missing at $summary_path" >&2
  exit 1
fi

py scripts/check_rust_runtime_recovery_summary.py

echo "Rust degraded-runtime recovery contract smoke completed."
echo "  summary: $summary_path"
