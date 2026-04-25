#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/run_helpers.sh"

pms_setup_python_runtime "$ROOT_DIR"
pms_use_isolated_direct_runtime
pms_prepare_data_dir "$ROOT_DIR" "rust-runtime-recovery"

SERVER_PID=""
SERVER_PORT_LEASE_JSON="$(pms_allocate_tcp_port)"
SERVER_PORT="$(printf '%s' "$SERVER_PORT_LEASE_JSON" | py -c 'import json, sys; print(json.load(sys.stdin)["port"])')"
SERVER_PORT_LEASE_PATH="$(printf '%s' "$SERVER_PORT_LEASE_JSON" | py -c 'import json, sys; print(json.load(sys.stdin)["lease_path"])')"
SERVER_URL="http://127.0.0.1:${SERVER_PORT}"
RUST_PREFIX="./.bin/pms-client --server $SERVER_URL"

cleanup() {
  pms_stop_background_pid "$SERVER_PID"
  if [[ -n "${SERVER_PORT_LEASE_PATH:-}" ]]; then
    pms_release_tcp_port "$SERVER_PORT_LEASE_PATH" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

pms init >/dev/null
SERVER_PID="$(pms_start_background_server "$PMS_DATA_DIR/rust-runtime-server.log" 127.0.0.1 "$SERVER_PORT")"
if ! pms_wait_for_server_health "$SERVER_URL" "$SERVER_PID"; then
  echo "Local PMS server did not become ready. Check log: $PMS_DATA_DIR/rust-runtime-server.log" >&2
  exit 1
fi

curl -fsS "$SERVER_URL/api/v1/health" >"$PMS_DATA_DIR/server-health.json"
./scripts/install_pms_client.sh --no-sign >/dev/null 2>&1
pms auth recover-local-admin --show-key >"$PMS_DATA_DIR/python-auth-recover.txt"
ADMIN_KEY="$(pms_extract_recovered_api_key "$PMS_DATA_DIR/python-auth-recover.txt")"
if [[ -z "$ADMIN_KEY" ]]; then
  echo "admin key was not present in auth recovery output" >&2
  exit 1
fi

PMS_API_KEY="$ADMIN_KEY" \
PMS_CLI_ARGV0="$RUST_PREFIX" \
./.bin/pms-client --server "$SERVER_URL" start --format json \
  >"$PMS_DATA_DIR/rust-start.json"

PMS_WRITE_MODE="prefer_server" \
PMS_SERVER_BASE_URL="http://127.0.0.1:1" \
PMS_API_KEY="$ADMIN_KEY" \
PMS_CLI_ARGV0="./.bin/pms-client" \
./.bin/pms-client runtime status --format json \
  >"$PMS_DATA_DIR/rust-runtime-status.json"

if PMS_API_KEY="$ADMIN_KEY" \
  ./.bin/pms-client --server "http://127.0.0.1:1" start --format json \
  >"$PMS_DATA_DIR/rust-stale-endpoint.txt" 2>&1; then
  echo "expected stale rust start to fail" >&2
  exit 1
fi

py - <<'PY'
import json
import os
from pathlib import Path

from pms.utils.atomic_files import write_json_atomic

base = Path(os.environ["PMS_DATA_DIR"])
start_payload = json.loads((base / "rust-start.json").read_text(encoding="utf-8"))
runtime_status = json.loads((base / "rust-runtime-status.json").read_text(encoding="utf-8"))
stale_text = (base / "rust-stale-endpoint.txt").read_text(encoding="utf-8")

summary = {
    "server": {
        "url": start_payload.get("links", {}).get("guide"),
        "health_artifact": str(base / "server-health.json"),
    },
    "start": {
        "canonical_prefix": start_payload.get("cli", {}).get("canonical_prefix"),
        "has_focus_task_key": "focus_task" in start_payload,
        "has_next_steps": bool(start_payload.get("next_steps")),
    },
    "runtime_status": {
        "canonical_prefix": runtime_status.get("cli", {}).get("canonical_prefix"),
        "state": runtime_status.get("coordination", {}).get("state"),
        "recommended_next_steps": runtime_status.get("coordination", {}).get("recommended_next_steps", []),
    },
    "stale_recovery": {
        "mentions_config_show": "config show --format json" in stale_text,
        "mentions_runtime_status": "runtime status --format json" in stale_text,
        "mentions_prefer_server": "runtime prefer-server --host 127.0.0.1 --port " in stale_text,
    },
    "artifacts": {
        "server_health": str(base / "server-health.json"),
        "python_auth_recover": str(base / "python-auth-recover.txt"),
        "rust_start": str(base / "rust-start.json"),
        "rust_runtime_status": str(base / "rust-runtime-status.json"),
        "rust_stale_endpoint": str(base / "rust-stale-endpoint.txt"),
    },
}

write_json_atomic(base / "rust-runtime-recovery.summary.json", summary, encoding="utf-8")
PY

echo "Rust degraded-runtime recovery flow completed."
echo "  summary: $PMS_DATA_DIR/rust-runtime-recovery.summary.json"
