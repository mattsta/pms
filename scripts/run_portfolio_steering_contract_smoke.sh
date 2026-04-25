#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/run_helpers.sh"

CONTRACT_TIMEOUT_SECONDS="${PMS_PORTFOLIO_STEERING_CONTRACT_TIMEOUT_SECONDS:-120}"
pms_setup_python_runtime "$ROOT_DIR"
pms_prepare_data_dir "$ROOT_DIR" "portfolio-steering-contract"

echo "Running portfolio-steering contract smoke"
echo "  run_mode: $RUN_MODE"
echo "  data_dir: $PMS_DATA_DIR"
echo "  contract_timeout_seconds: $CONTRACT_TIMEOUT_SECONDS"

pms_run_contract_flow \
  "Portfolio-steering contract smoke" \
  "$CONTRACT_TIMEOUT_SECONDS" \
  "$ROOT_DIR" \
  "$ROOT_DIR/scripts/run_portfolio_steering_flow.sh"

summary_path="$PMS_DATA_DIR/portfolio-steering.summary.json"
if [[ ! -s "$summary_path" ]]; then
  echo "Portfolio-steering contract smoke failed: summary missing at $summary_path" >&2
  exit 1
fi

py scripts/check_portfolio_steering_summary.py

echo "Portfolio-steering contract smoke completed."
echo "  summary: $summary_path"
