#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/run_helpers.sh"

CONTRACT_TIMEOUT_SECONDS="${PMS_PROOF_BUNDLE_CONTRACT_TIMEOUT_SECONDS:-180}"
pms_setup_python_runtime "$ROOT_DIR"
pms_prepare_data_dir "$ROOT_DIR" "proof-bundle-contract"

echo "Running proof-bundle contract smoke"
echo "  run_mode: $RUN_MODE"
echo "  data_dir: $PMS_DATA_DIR"
echo "  contract_timeout_seconds: $CONTRACT_TIMEOUT_SECONDS"

pms_run_contract_flow \
  "Proof-bundle contract smoke" \
  "$CONTRACT_TIMEOUT_SECONDS" \
  "$ROOT_DIR" \
  bash \
  "$ROOT_DIR/scripts/run_proof_bundle_flow.sh"

[ -s "$PMS_DATA_DIR/proof-bundle.summary.json" ]
py scripts/check_proof_bundle_contract.py

echo "Proof-bundle contract smoke completed."
