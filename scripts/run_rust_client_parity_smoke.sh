#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT_DIR/scripts/lib/run_helpers.sh"
TMP_DIR="${PMS_RUST_PARITY_TMP_DIR:-$(mktemp -d "$ROOT_DIR/.tmp/rust-client-parity.XXXXXX")}"
ENV_FILE="$TMP_DIR/.env"
DATA_DIR="$TMP_DIR/data"
START_JSON="$TMP_DIR/start.json"
TASK_JSON="$TMP_DIR/task-list.json"
PLAN_JSON="$TMP_DIR/plan-list.json"
TASK_START_JSON="$TMP_DIR/task-start.json"
TASK_PROGRESS_JSON="$TMP_DIR/task-progress.json"
TASK_COMPLETE_JSON="$TMP_DIR/task-complete.json"
FIXTURE_ENV="$TMP_DIR/fixture.env"
AUTH_LOG="$TMP_DIR/auth.log"
SERVER_PID=""

mkdir -p "$TMP_DIR"
mkdir -p "$DATA_DIR"
pms_setup_python_runtime "$ROOT_DIR"

export PMS_ENV_FILE="$ENV_FILE"
export PMS_DATA_DIR="$DATA_DIR"
export PMS_DATABASE_PATH="$DATA_DIR/pms.db"
export PMS_LOG_DIR="$DATA_DIR/logs"
export PMS_WRITE_MODE=direct

cleanup() {
  pms_stop_background_pid "$SERVER_PID"
  if [[ -n "${SERVER_PORT_LEASE_PATH:-}" ]]; then
    pms_release_tcp_port "$SERVER_PORT_LEASE_PATH" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

if [[ -n "${PMS_SERVER_BASE_URL:-}" ]]; then
  SERVER_URL="$PMS_SERVER_BASE_URL"
else
  if [[ -n "${PMS_RUST_PARITY_PORT:-}" ]]; then
    SERVER_PORT="$PMS_RUST_PARITY_PORT"
  else
    SERVER_PORT_LEASE_JSON="$(pms_allocate_tcp_port)"
    SERVER_PORT="$(printf '%s' "$SERVER_PORT_LEASE_JSON" | py -c 'import json, sys; print(json.load(sys.stdin)["port"])')"
    SERVER_PORT_LEASE_PATH="$(printf '%s' "$SERVER_PORT_LEASE_JSON" | py -c 'import json, sys; print(json.load(sys.stdin)["lease_path"])')"
  fi
  SERVER_URL="http://127.0.0.1:${SERVER_PORT}"
  cd "$ROOT_DIR"
  SERVER_PID="$(pms_start_background_server "$TMP_DIR/server.log" 127.0.0.1 "$SERVER_PORT")"
  if ! pms_wait_for_server_health "$SERVER_URL" "$SERVER_PID"; then
    echo "Local PMS server did not become ready. Check log: $TMP_DIR/server.log" >&2
    exit 1
  fi
fi

cd "$ROOT_DIR"
./scripts/install_pms_client.sh --no-sign >/tmp/pms-rust-install.log 2>&1
pms auth recover-local-admin --show-key >"$AUTH_LOG"
ADMIN_KEY="$(pms_extract_recovered_api_key "$AUTH_LOG")"
if [[ -z "$ADMIN_KEY" ]]; then
  echo "admin key was not present in auth recovery output" >&2
  exit 1
fi
py scripts/setup_rust_client_parity_fixture.py --output-env "$FIXTURE_ENV"

# shellcheck disable=SC1090
source "$FIXTURE_ENV"

PMS_API_KEY="$ADMIN_KEY" ./.bin/pms-client --server "$SERVER_URL" start --format json >"$START_JSON"
PMS_API_KEY="$ADMIN_KEY" ./.bin/pms-client --server "$SERVER_URL" task list --project-id "$PROJECT_ID" --format json >"$TASK_JSON"
PMS_API_KEY="$ADMIN_KEY" ./.bin/pms-client --server "$SERVER_URL" plan list --project-id "$PROJECT_ID" --format json >"$PLAN_JSON"
PMS_API_KEY="$ADMIN_KEY" ./.bin/pms-client --server "$SERVER_URL" task start "$STARTABLE_TASK_ID" --by rust-smoke --format json >"$TASK_START_JSON"
PMS_API_KEY="$ADMIN_KEY" ./.bin/pms-client --server "$SERVER_URL" task progress "$STARTABLE_TASK_ID" 25 "Rust parity smoke progress update" --by rust-smoke --format json >"$TASK_PROGRESS_JSON"
PMS_API_KEY="$ADMIN_KEY" ./.bin/pms-client --server "$SERVER_URL" task complete "$STARTABLE_TASK_ID" --by rust-smoke --format json >"$TASK_COMPLETE_JSON"

py scripts/check_rust_client_output.py --start-json "$START_JSON" --task-list-json "$TASK_JSON" --plan-list-json "$PLAN_JSON" --task-start-json "$TASK_START_JSON" --task-progress-json "$TASK_PROGRESS_JSON" --task-complete-json "$TASK_COMPLETE_JSON"
