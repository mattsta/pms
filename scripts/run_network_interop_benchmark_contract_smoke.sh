#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/run_helpers.sh"

CONTRACT_TIMEOUT_SECONDS="${PMS_NETWORK_INTEROP_BENCHMARK_CONTRACT_TIMEOUT_SECONDS:-240}"
pms_setup_python_runtime "$ROOT_DIR"
pms_prepare_data_dir "$ROOT_DIR" "network-interop-benchmark-contract"

echo "Running network interop benchmark contract smoke"
echo "  run_mode: $RUN_MODE"
echo "  data_dir: $PMS_DATA_DIR"
echo "  contract_timeout_seconds: $CONTRACT_TIMEOUT_SECONDS"

export PMS_NETWORK_INTEROP_BENCHMARK_LIMIT="${PMS_NETWORK_INTEROP_BENCHMARK_LIMIT:-10}"
export PMS_NETWORK_INTEROP_BENCHMARK_REPETITIONS="${PMS_NETWORK_INTEROP_BENCHMARK_REPETITIONS:-1}"
export PMS_NETWORK_INTEROP_ARTIFACT_ROOT="${PMS_NETWORK_INTEROP_ARTIFACT_ROOT:-$PMS_DATA_DIR/artifacts}"

pms_run_contract_flow \
  "Network interop benchmark contract smoke" \
  "$CONTRACT_TIMEOUT_SECONDS" \
  "$ROOT_DIR" \
  bash \
  "$ROOT_DIR/scripts/run_network_interop_benchmark_bundle.sh"

summary_path="$(find "$PMS_NETWORK_INTEROP_ARTIFACT_ROOT" -name benchmark-bundle.summary.json -print | head -n 1)"
if [[ -z "$summary_path" || ! -s "$summary_path" ]]; then
  echo "Network interop benchmark contract smoke failed: summary missing" >&2
  exit 1
fi

pms_copy_file_atomic "$summary_path" "$PMS_DATA_DIR/benchmark-bundle.summary.json"
py scripts/check_network_interop_benchmark_bundle.py

echo "Network interop benchmark contract smoke completed."
echo "  summary: $summary_path"
