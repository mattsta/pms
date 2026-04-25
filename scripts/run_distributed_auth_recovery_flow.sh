#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/run_helpers.sh"

pms_setup_python_runtime "$ROOT_DIR"
pms_use_isolated_direct_runtime
pms_prepare_data_dir "$ROOT_DIR" "distributed-auth-recovery"

SERVER_PID=""
SERVER_PORT_LEASE_JSON="$(pms_allocate_tcp_port)"
SERVER_PORT="$(printf '%s' "$SERVER_PORT_LEASE_JSON" | py -c 'import json, sys; print(json.load(sys.stdin)["port"])')"
SERVER_PORT_LEASE_PATH="$(printf '%s' "$SERVER_PORT_LEASE_JSON" | py -c 'import json, sys; print(json.load(sys.stdin)["lease_path"])')"
SERVER_URL="http://127.0.0.1:${SERVER_PORT}"
SERVER_LOG_PATH="$PMS_DATA_DIR/distributed-auth-server.log"

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
export DISTRIBUTED_AUTH_DATA_DIR="$PMS_DATA_DIR"
export DISTRIBUTED_AUTH_SERVER_URL="$SERVER_URL"
export DISTRIBUTED_ADMIN_KEY_PREFIX=""
export DISTRIBUTED_LIMITED_KEY_ID=""
export DISTRIBUTED_LIMITED_KEY_PREFIX=""

ADMIN_KEY="$(pms_extract_recovered_api_key "$PMS_DATA_DIR/python-auth-init.txt")"
if [[ -z "$ADMIN_KEY" ]]; then
  echo "admin key was not present in auth recovery output" >&2
  exit 1
fi

curl -fsS -H "X-API-Key: $ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"Distributed Reader","scopes":["tasks:read"],"metadata":{"created_by":"distributed_auth_recovery"}}' \
  "$SERVER_URL/api/v1/auth/keys" \
  >"$PMS_DATA_DIR/api-auth-create.json"
LIMITED_KEY_ID="$(py - <<'PY'
import json
import os
from pathlib import Path
payload = json.loads((Path(os.environ["DISTRIBUTED_AUTH_DATA_DIR"]) / "api-auth-create.json").read_text(encoding="utf-8"))
value = payload.get("key_info", {}).get("id")
if not value:
    raise SystemExit("limited key id not found in api auth create output")
print(value)
PY
)"
LIMITED_KEY="$(py - <<'PY'
import json
import os
from pathlib import Path
payload = json.loads((Path(os.environ["DISTRIBUTED_AUTH_DATA_DIR"]) / "api-auth-create.json").read_text(encoding="utf-8"))
value = payload.get("api_key")
if not value:
    raise SystemExit("limited key not found in api auth create output")
print(value)
PY
)"
export DISTRIBUTED_ADMIN_KEY_PREFIX="${ADMIN_KEY:0:12}"
export DISTRIBUTED_LIMITED_KEY_ID="$LIMITED_KEY_ID"
export DISTRIBUTED_LIMITED_KEY_PREFIX="${LIMITED_KEY:0:12}"

curl -fsS -H "X-API-Key: $ADMIN_KEY" \
  "$SERVER_URL/api/v1/auth/keys?include_inactive=true&include_archived=false" \
  >"$PMS_DATA_DIR/api-keys-list.json"
curl -fsS -H "X-API-Key: $ADMIN_KEY" \
  "$SERVER_URL/api/v1/auth/keys/$LIMITED_KEY_ID" \
  >"$PMS_DATA_DIR/api-key-before.json"

PMS_API_KEY="$ADMIN_KEY" ./.bin/pms-client --server "$SERVER_URL" auth keys get "$LIMITED_KEY_ID" \
  >"$PMS_DATA_DIR/rust-auth-get.txt"
PMS_API_KEY="$ADMIN_KEY" ./.bin/pms-client --server "$SERVER_URL" auth keys deactivate "$LIMITED_KEY_ID" \
  >"$PMS_DATA_DIR/rust-auth-deactivate.txt"
curl -fsS -H "X-API-Key: $ADMIN_KEY" \
  "$SERVER_URL/api/v1/auth/keys/$LIMITED_KEY_ID" \
  >"$PMS_DATA_DIR/api-key-deactivated.json"
PMS_API_KEY="$ADMIN_KEY" ./.bin/pms-client --server "$SERVER_URL" auth keys restore "$LIMITED_KEY_ID" \
  >"$PMS_DATA_DIR/rust-auth-restore.txt"
curl -fsS -H "X-API-Key: $ADMIN_KEY" \
  "$SERVER_URL/api/v1/auth/keys/$LIMITED_KEY_ID" \
  >"$PMS_DATA_DIR/api-key-restored.json"

LIMITED_KEY_ADMIN_STATUS="$(curl -sS -o "$PMS_DATA_DIR/limited-key-admin-denied.json" -w '%{http_code}' \
  -H "X-API-Key: $LIMITED_KEY" \
  "$SERVER_URL/api/v1/auth/keys")"
printf '%s\n' "$LIMITED_KEY_ADMIN_STATUS" >"$PMS_DATA_DIR/limited-key-admin-status.txt"

if ./.bin/pms-client --server "http://127.0.0.1:1" start --format json >"$PMS_DATA_DIR/rust-stale-endpoint.txt" 2>&1; then
  echo "expected rust stale-endpoint call to fail" >&2
  exit 1
fi

PMS_WRITE_MODE="prefer_server" \
PMS_SERVER_BASE_URL="http://127.0.0.1:1" \
PMS_API_KEY="$ADMIN_KEY" \
pms start --format json >"$PMS_DATA_DIR/python-stale-start.json"

py - <<'PY'
import json
import os
from pathlib import Path

from pms.utils.atomic_files import write_json_atomic

base = Path(os.environ["DISTRIBUTED_AUTH_DATA_DIR"])
before = json.loads((base / "api-key-before.json").read_text())
deactivated = json.loads((base / "api-key-deactivated.json").read_text())
restored = json.loads((base / "api-key-restored.json").read_text())
python_stale = json.loads((base / "python-stale-start.json").read_text())
rust_stale = (base / "rust-stale-endpoint.txt").read_text(encoding="utf-8")

summary = {
    "server": {
        "url": os.environ["DISTRIBUTED_AUTH_SERVER_URL"],
        "health_artifact": str(base / "server-health.json"),
    },
    "auth": {
        "admin_key_prefix": os.environ["DISTRIBUTED_ADMIN_KEY_PREFIX"],
        "limited_key_id": os.environ["DISTRIBUTED_LIMITED_KEY_ID"],
        "limited_key_prefix": os.environ["DISTRIBUTED_LIMITED_KEY_PREFIX"],
        "before_active": before.get("is_active"),
        "after_deactivate_active": deactivated.get("is_active"),
        "after_restore_active": restored.get("is_active"),
        "limited_key_admin_status": (base / "limited-key-admin-status.txt").read_text(encoding="utf-8").strip(),
    },
    "stale_recovery": {
        "python_recovery_kind": (
            python_stale.get("runtime", {})
            .get("coordination", {})
            .get("recovery", {})
            .get("kind")
        ),
        "python_recovery_summary": (
            python_stale.get("runtime", {})
            .get("coordination", {})
            .get("recovery", {})
            .get("summary")
        ),
        "rust_mentions_config_show": "config show --format json" in rust_stale,
        "rust_mentions_runtime_status": "runtime status --format json" in rust_stale,
        "rust_mentions_prefer_server": "runtime prefer-server --host 127.0.0.1 --port " in rust_stale,
    },
    "artifacts": {
        "python_auth_init": str(base / "python-auth-init.txt"),
        "api_auth_create": str(base / "api-auth-create.json"),
        "api_keys_list": str(base / "api-keys-list.json"),
        "api_key_before": str(base / "api-key-before.json"),
        "rust_auth_get": str(base / "rust-auth-get.txt"),
        "rust_auth_deactivate": str(base / "rust-auth-deactivate.txt"),
        "api_key_deactivated": str(base / "api-key-deactivated.json"),
        "rust_auth_restore": str(base / "rust-auth-restore.txt"),
        "api_key_restored": str(base / "api-key-restored.json"),
        "limited_key_admin_denied": str(base / "limited-key-admin-denied.json"),
        "limited_key_admin_status": str(base / "limited-key-admin-status.txt"),
        "rust_stale_endpoint": str(base / "rust-stale-endpoint.txt"),
        "python_stale_start": str(base / "python-stale-start.json"),
    },
}

write_json_atomic(base / "distributed-auth-recovery.summary.json", summary, encoding="utf-8")
PY

echo "Distributed auth recovery flow completed."
echo "  summary: $PMS_DATA_DIR/distributed-auth-recovery.summary.json"
