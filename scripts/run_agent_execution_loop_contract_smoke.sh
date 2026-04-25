#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/scenario_env.sh"
source "$ROOT_DIR/scripts/lib/run_helpers.sh"

CONTRACT_TIMEOUT_SECONDS="${PMS_AGENT_LOOP_CONTRACT_TIMEOUT_SECONDS:-$(pms_parallel_headroom_value 240 360)}"
pms_setup_python_runtime "$ROOT_DIR"
pms_prepare_data_dir "$ROOT_DIR" "agent-loop-contract"
pms_use_isolated_direct_runtime

echo "Running agent-loop contract smoke"
echo "  run_mode: $RUN_MODE"
echo "  data_dir: $PMS_DATA_DIR"
echo "  contract_timeout_seconds: $CONTRACT_TIMEOUT_SECONDS"

pms_run_contract_flow \
  "Agent-loop contract smoke" \
  "$CONTRACT_TIMEOUT_SECONDS" \
  "$ROOT_DIR" \
  "$ROOT_DIR/scripts/run_agent_execution_loop_flow.sh"

summary_path="$PMS_DATA_DIR/agent-loop.summary.json"
if [[ ! -s "$summary_path" ]]; then
  echo "Agent-loop contract smoke failed: summary missing at $summary_path" >&2
  exit 1
fi

py scripts/check_agent_execution_loop_summary.py

echo "Agent-loop contract smoke completed."
echo "  summary: $summary_path"
