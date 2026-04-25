#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/run_helpers.sh"

CONTRACT_TIMEOUT_SECONDS="${PMS_DISTRIBUTED_AUTH_CONTRACT_TIMEOUT_SECONDS:-180}"
pms_setup_python_runtime "$ROOT_DIR"
pms_prepare_data_dir "$ROOT_DIR" "distributed-auth-contract"

echo "Running distributed-auth recovery contract smoke"
echo "  run_mode: $RUN_MODE"
echo "  data_dir: $PMS_DATA_DIR"
echo "  contract_timeout_seconds: $CONTRACT_TIMEOUT_SECONDS"

pms_run_contract_flow \
  "Distributed auth recovery contract smoke" \
  "$CONTRACT_TIMEOUT_SECONDS" \
  "$ROOT_DIR" \
  "$ROOT_DIR/scripts/run_distributed_auth_recovery_flow.sh"

summary_path="$PMS_DATA_DIR/distributed-auth-recovery.summary.json"
if [[ ! -s "$summary_path" ]]; then
  echo "Distributed auth recovery contract smoke failed: summary missing at $summary_path" >&2
  exit 1
fi

py scripts/check_distributed_auth_recovery_summary.py

echo "Distributed auth recovery contract smoke completed."
echo "  summary: $summary_path"
