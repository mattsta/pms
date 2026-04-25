#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/run_helpers.sh"

pms_setup_python_runtime "$ROOT_DIR"
pms_use_isolated_direct_runtime
pms_prepare_data_dir "$ROOT_DIR" "distributed-multiwriter"

SERVER_PID=""
SERVER_PORT_LEASE_JSON="$(pms_allocate_tcp_port)"
SERVER_PORT="$(printf '%s' "$SERVER_PORT_LEASE_JSON" | py -c 'import json, sys; print(json.load(sys.stdin)["port"])')"
SERVER_PORT_LEASE_PATH="$(printf '%s' "$SERVER_PORT_LEASE_JSON" | py -c 'import json, sys; print(json.load(sys.stdin)["lease_path"])')"
SERVER_URL="http://127.0.0.1:${SERVER_PORT}"
SERVER_LOG_PATH="$PMS_DATA_DIR/distributed-multiwriter-server.log"
export DISTRIBUTED_MULTIWRITER_SERVER_URL="$SERVER_URL"

cleanup() {
  pms_stop_background_pid "$SERVER_PID"
  if [[ -n "${SERVER_PORT_LEASE_PATH:-}" ]]; then
    pms_release_tcp_port "$SERVER_PORT_LEASE_PATH" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

pms init >/dev/null
SERVER_PID="$(pms_start_background_server "$SERVER_LOG_PATH" 127.0.0.1 "$SERVER_PORT")"
if ! pms_wait_for_server_health "$SERVER_URL" "$SERVER_PID"; then
  echo "Local PMS server did not become ready. Check log: $SERVER_LOG_PATH" >&2
  exit 1
fi

curl -fsS "$SERVER_URL/api/v1/health" >"$PMS_DATA_DIR/server-health.json"
./scripts/install_pms_client.sh --no-sign >/dev/null 2>&1

pms auth recover-local-admin --show-key >"$PMS_DATA_DIR/python-auth-init.txt"
ADMIN_KEY="$(pms_extract_recovered_api_key "$PMS_DATA_DIR/python-auth-init.txt")"
if [[ -z "$ADMIN_KEY" ]]; then
  echo "admin key was not present in auth recovery output" >&2
  exit 1
fi

curl -fsS \
  -H "X-API-Key: $ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"Distributed Multiwriter Project"}' \
  "$SERVER_URL/api/v1/projects" \
  >"$PMS_DATA_DIR/api-project.json"

PROJECT_ID="$(py - <<'PY'
import json
import os
from pathlib import Path
payload = json.loads((Path(os.environ["PMS_DATA_DIR"]) / "api-project.json").read_text(encoding="utf-8"))
print(payload["id"])
PY
)"

curl -fsS \
  -H "X-API-Key: $ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"project_id\":\"${PROJECT_ID}\",\"title\":\"Distributed Checkout Task\"}" \
  "$SERVER_URL/api/v1/tasks" \
  >"$PMS_DATA_DIR/api-task.json"

TASK_ID="$(py - <<'PY'
import json
import os
from pathlib import Path
payload = json.loads((Path(os.environ["PMS_DATA_DIR"]) / "api-task.json").read_text(encoding="utf-8"))
print(payload["id"])
PY
)"

pms task checkout "$TASK_ID" --agent-id py-agent >"$PMS_DATA_DIR/python-checkout.txt"

API_CONFLICT_STATUS="$(
  curl -sS \
    -o "$PMS_DATA_DIR/api-checkout-conflict.json" \
    -w '%{http_code}' \
    -H "X-API-Key: $ADMIN_KEY" \
    -H "Content-Type: application/json" \
    -d '{"agent_session_id":"api-agent","lease_seconds":300}' \
    "$SERVER_URL/api/v1/tasks/${TASK_ID}/checkout"
)"
printf '%s\n' "$API_CONFLICT_STATUS" >"$PMS_DATA_DIR/api-checkout-conflict.status.txt"

if PMS_API_KEY="$ADMIN_KEY" ./.bin/pms-client --server "$SERVER_URL" task checkout "$TASK_ID" --agent-id rust-agent >"$PMS_DATA_DIR/rust-checkout-conflict.txt" 2>&1; then
  echo "expected Rust conflicting checkout to fail" >&2
  exit 1
fi

pms task release "$TASK_ID" --agent-id py-agent >"$PMS_DATA_DIR/python-release.txt"
PMS_API_KEY="$ADMIN_KEY" ./.bin/pms-client --server "$SERVER_URL" task checkout "$TASK_ID" --agent-id rust-agent >"$PMS_DATA_DIR/rust-checkout-success.txt"

curl -fsS \
  -H "X-API-Key: $ADMIN_KEY" \
  "$SERVER_URL/api/v1/checkout/status?agent_session_id=rust-agent" \
  >"$PMS_DATA_DIR/api-rust-checkout-status.json"

curl -fsS -X POST \
  -H "X-API-Key: $ADMIN_KEY" \
  "$SERVER_URL/api/v1/tasks/${TASK_ID}/checkout/force-release?released_by=api-admin&reason=handoff" \
  >"$PMS_DATA_DIR/api-force-release.json"

pms task checkout "$TASK_ID" --agent-id py-agent-2 >"$PMS_DATA_DIR/python-recheckout.txt"

curl -fsS \
  -H "X-API-Key: $ADMIN_KEY" \
  "$SERVER_URL/api/v1/checkout/log?task_id=${TASK_ID}&limit=20&include_metadata=true" \
  >"$PMS_DATA_DIR/api-checkout-log.json"

py - <<'PY'
import json
import os
from pathlib import Path

from pms.utils.atomic_files import write_json_atomic

base = Path(os.environ["PMS_DATA_DIR"])
api_conflict = json.loads((base / "api-checkout-conflict.json").read_text(encoding="utf-8"))
rust_status = json.loads((base / "api-rust-checkout-status.json").read_text(encoding="utf-8"))
force_release = json.loads((base / "api-force-release.json").read_text(encoding="utf-8"))
log_payload = json.loads((base / "api-checkout-log.json").read_text(encoding="utf-8"))
rust_conflict_text = (base / "rust-checkout-conflict.txt").read_text(encoding="utf-8")
rust_success_text = (base / "rust-checkout-success.txt").read_text(encoding="utf-8")
python_recheckout = (base / "python-recheckout.txt").read_text(encoding="utf-8")

summary = {
    "server": {
        "url": os.environ["DISTRIBUTED_MULTIWRITER_SERVER_URL"],
        "health_artifact": str(base / "server-health.json"),
    },
    "checkout": {
        "api_conflict_status": (base / "api-checkout-conflict.status.txt").read_text(encoding="utf-8").strip(),
        "api_conflict_detail": api_conflict.get("detail"),
        "rust_conflict_mentions_checkout_status": "task checkout-status --agent-id rust-agent" in rust_conflict_text,
        "rust_conflict_mentions_force_release": "task force-release" in rust_conflict_text,
        "rust_conflict_mentions_task_show": "task show " in rust_conflict_text,
        "rust_success_checked_out": "Checked out task" in rust_success_text,
        "rust_status_count": rust_status.get("count"),
        "force_release_status": force_release.get("status"),
        "python_recheckout_succeeded": "Checked out:" in python_recheckout,
        "log_actions": sorted({entry.get("action") for entry in log_payload.get("entries", []) if entry.get("action")}),
    },
    "artifacts": {
        "python_auth_init": str(base / "python-auth-init.txt"),
        "api_project": str(base / "api-project.json"),
        "api_task": str(base / "api-task.json"),
        "python_checkout": str(base / "python-checkout.txt"),
        "api_checkout_conflict_status": str(base / "api-checkout-conflict.status.txt"),
        "api_checkout_conflict": str(base / "api-checkout-conflict.json"),
        "rust_checkout_conflict": str(base / "rust-checkout-conflict.txt"),
        "python_release": str(base / "python-release.txt"),
        "rust_checkout_success": str(base / "rust-checkout-success.txt"),
        "api_rust_checkout_status": str(base / "api-rust-checkout-status.json"),
        "api_force_release": str(base / "api-force-release.json"),
        "python_recheckout": str(base / "python-recheckout.txt"),
        "api_checkout_log": str(base / "api-checkout-log.json"),
    },
}

write_json_atomic(base / "distributed-multiwriter.summary.json", summary, encoding="utf-8")
PY

echo "Distributed multiwriter flow completed."
echo "  summary: $PMS_DATA_DIR/distributed-multiwriter.summary.json"
