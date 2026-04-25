#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  RUN_MODE="venv"
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
elif command -v uv >/dev/null 2>&1; then
  RUN_MODE="uv"
  PYTHON_BIN=""
elif command -v python3 >/dev/null 2>&1; then
  RUN_MODE="system"
  PYTHON_BIN="$(command -v python3)"
else
  echo "No supported Python runtime found (.venv/bin/python, uv, or python3)." >&2
  exit 1
fi

timestamp="$(date +"%Y%m%d-%H%M%S")"
if [[ -n "${PMS_DATA_DIR:-}" ]]; then
  data_dir="$PMS_DATA_DIR"
else
  mkdir -p "$ROOT_DIR/.tmp"
  data_dir="$(mktemp -d "$ROOT_DIR/.tmp/demo-suite-${timestamp}.XXXXXX")"
fi

export PMS_DATA_DIR="$data_dir"
export PMS_DATABASE_PATH="${PMS_DATABASE_PATH:-$PMS_DATA_DIR/pms.db}"
export PMS_LOG_DIR="${PMS_LOG_DIR:-$PMS_DATA_DIR/logs}"
export PMS_ENV_FILE="${PMS_ENV_FILE:-$PMS_DATA_DIR/.env}"
mkdir -p "$PMS_LOG_DIR"

py() {
  if [[ "$RUN_MODE" == "uv" ]]; then
    uv run python "$@"
  else
    "$PYTHON_BIN" "$@"
  fi
}

echo "1/9 Running smoke demo"
"$ROOT_DIR/scripts/run_demo_smoke.sh"

echo "2/9 Running drop-in growth contract smoke"
"$ROOT_DIR/scripts/run_dropin_contract_smoke.sh"

echo "3/9 Running team handoff contract smoke"
"$ROOT_DIR/scripts/run_team_handoff_contract_smoke.sh"

echo "4/9 Running incident response contract smoke"
"$ROOT_DIR/scripts/run_incident_response_contract_smoke.sh"

echo "5/9 Running user start -> go -> observe contract smoke"
"$ROOT_DIR/scripts/run_user_start_go_observe_contract_smoke.sh"

echo "6/9 Running docs command smoke"
"$ROOT_DIR/scripts/run_docs_smoke.sh"

echo "7/9 Running CLI parity audit"
py scripts/cli_parity_audit.py --check

echo "8/9 Running API/client parity audit"
py scripts/client_parity_audit.py --check

echo "9/9 Running regression tests"
py -m pytest tests/integration/test_cli.py::TestTaskCheckoutCommands::test_task_list_detail_json_without_history -q

if [[ "${PMS_RUN_FULL_TESTS:-0}" == "1" ]]; then
  echo "Running full test suite (PMS_RUN_FULL_TESTS=1)"
  py -m pytest -q
fi

echo "Demo suite completed."
