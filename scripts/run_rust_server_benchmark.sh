#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/run_helpers.sh"
pms_setup_python_runtime "$ROOT_DIR"

PROJECT_ID=""
PROJECT_NAME=""
REPORT_DIR="$ROOT_DIR/.tmp"
LIST_LIMIT=50
LIST_OFFSET=0
REPETITIONS=3
SERVER_PID=""

if [[ -n "${PMS_SERVER_BASE_URL:-}" ]]; then
  SERVER_URL="$PMS_SERVER_BASE_URL"
  SERVER_PORT=""
else
  SERVER_PORT_LEASE_JSON="$(pms_allocate_tcp_port)"
  SERVER_PORT="$(printf '%s' "$SERVER_PORT_LEASE_JSON" | py -c 'import json, sys; print(json.load(sys.stdin)["port"])')"
  SERVER_PORT_LEASE_PATH="$(printf '%s' "$SERVER_PORT_LEASE_JSON" | py -c 'import json, sys; print(json.load(sys.stdin)["lease_path"])')"
  SERVER_URL="http://127.0.0.1:${SERVER_PORT}"
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-id)
      PROJECT_ID="$2"
      shift 2
      ;;
    --project)
      PROJECT_NAME="$2"
      shift 2
      ;;
    --server-url)
      SERVER_URL="$2"
      shift 2
      ;;
    --report-dir)
      REPORT_DIR="$2"
      shift 2
      ;;
    --limit)
      LIST_LIMIT="$2"
      shift 2
      ;;
    --offset)
      LIST_OFFSET="$2"
      shift 2
      ;;
    --repetitions)
      REPETITIONS="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1" >&2
      echo "Usage: $0 (--project <name> | --project-id <id>) [--server-url <url>] [--report-dir <dir>] [--limit <n>] [--offset <n>] [--repetitions <n>]" >&2
      exit 2
      ;;
  esac
done

if [[ -n "$PROJECT_ID" && -n "$PROJECT_NAME" ]]; then
  echo "Use --project or --project-id, not both" >&2
  exit 2
fi

if [[ -z "$PROJECT_ID" && -z "$PROJECT_NAME" ]]; then
  echo "--project or --project-id is required" >&2
  exit 2
fi

mkdir -p "$REPORT_DIR"
REPORT_FILE="$REPORT_DIR/rust-server-benchmark-$(date +%Y%m%d-%H%M%S).json"
METRICS_FILE="$REPORT_DIR/rust-server-benchmark-$(date +%Y%m%d-%H%M%S).tsv"
SERVER_LOG_PATH="$REPORT_DIR/pms-rust-benchmark-server.log"
SERVER_STARTED=0

cleanup() {
  if [[ "${SERVER_STARTED}" -eq 1 ]]; then
    pms_stop_background_pid "${SERVER_PID}"
  fi
  if [[ -n "${SERVER_PORT_LEASE_PATH:-}" ]]; then
    pms_release_tcp_port "$SERVER_PORT_LEASE_PATH" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

if [[ -n "${SERVER_PORT}" ]] && ! curl -fsS "$SERVER_URL/api/v1/health" >/dev/null 2>&1; then
  SERVER_PID="$(pms_start_background_server "$SERVER_LOG_PATH" 127.0.0.1 "$SERVER_PORT")"
  SERVER_STARTED=1
  if ! pms_wait_for_server_health "$SERVER_URL" "$SERVER_PID"; then
    echo "Local PMS server did not become ready. Check log: $SERVER_LOG_PATH" >&2
    exit 1
  fi
fi

./scripts/install_pms_client.sh >/tmp/pms-client-install.log 2>&1
pms auth recover-local-admin --show-key >/tmp/pms-auth-recover.log 2>&1
export PMS_API_KEY="$(pms_extract_recovered_api_key /tmp/pms-auth-recover.log)"

measure_shell_command() {
  local scenario="$1"
  local interface="$2"
  local command="$3"
  local output_file="$4"
  local run_index
  for run_index in $(seq 1 "$REPETITIONS"); do
    local time_file
    time_file="$(mktemp)"

    /usr/bin/time -p bash -lc "$command" >"$output_file" 2>"$time_file"
    local real_seconds
    real_seconds="$(awk '/^real / {print $2}' "$time_file" | tail -n 1)"
    rm -f "$time_file"
    printf '%s\t%s\t%s\t%s\t%s\n' "$scenario" "$interface" "$command" "$run_index" "$real_seconds" >>"$METRICS_FILE"
  done
}

measure_http_command() {
  local scenario="$1"
  local command="$2"
  local url="$3"
  local output_file="$4"
  local run_index
  for run_index in $(seq 1 "$REPETITIONS"); do
    local real_seconds

    real_seconds="$(
      curl -sS \
        -H "X-API-Key: $PMS_API_KEY" \
        -o "$output_file" \
        -w '%{time_total}' \
        "$url"
    )"
    printf '%s\tapi_http\t%s\t%s\t%s\n' "$scenario" "$command" "$run_index" "$real_seconds" >>"$METRICS_FILE"
  done
}

measure_shell_command \
  "start_json" \
  "python_cli" \
  "uv run pms start --format json" \
  "/tmp/pms-python-start-benchmark.out"

measure_shell_command \
  "start_json" \
  "rust_client" \
  "./.bin/pms-client --server \"$SERVER_URL\" start --format json" \
  "/tmp/pms-rust-start-benchmark.out"

if [[ -n "$PROJECT_NAME" ]]; then
  measure_shell_command \
    "task_list_json" \
    "python_cli" \
    "uv run pms task list --project \"$PROJECT_NAME\" --format json --limit $LIST_LIMIT --offset $LIST_OFFSET" \
    "/tmp/pms-python-task-list-benchmark.out"
  measure_shell_command \
    "task_list_json" \
    "rust_client" \
    "./.bin/pms-client --server \"$SERVER_URL\" task list --project \"$PROJECT_NAME\" --format json" \
    "/tmp/pms-rust-task-list-benchmark.out"
else
  measure_shell_command \
    "task_list_json" \
    "python_cli" \
    "uv run pms task list --project \"$PROJECT_ID\" --format json --limit $LIST_LIMIT --offset $LIST_OFFSET" \
    "/tmp/pms-python-task-list-benchmark.out"
  measure_shell_command \
    "task_list_json" \
    "rust_client" \
    "./.bin/pms-client --server \"$SERVER_URL\" task list --project-id \"$PROJECT_ID\" --format json" \
    "/tmp/pms-rust-task-list-benchmark.out"
  measure_http_command \
    "task_list_json" \
    "curl -H X-API-Key:<redacted> \"$SERVER_URL/api/v1/tasks?project_id=$PROJECT_ID&limit=$LIST_LIMIT&offset=$LIST_OFFSET\"" \
    "$SERVER_URL/api/v1/tasks?project_id=$PROJECT_ID&limit=$LIST_LIMIT&offset=$LIST_OFFSET" \
    "/tmp/pms-api-task-list-benchmark.out"

  measure_shell_command \
    "plan_list_json" \
    "python_cli" \
    "uv run pms plan list --project-id \"$PROJECT_ID\" --format json --limit $LIST_LIMIT --offset $LIST_OFFSET" \
    "/tmp/pms-python-plan-list-benchmark.out"
  measure_shell_command \
    "plan_list_json" \
    "rust_client" \
    "./.bin/pms-client --server \"$SERVER_URL\" plan list --project-id \"$PROJECT_ID\" --format json --limit $LIST_LIMIT --offset $LIST_OFFSET" \
    "/tmp/pms-rust-plan-list-benchmark.out"
  measure_http_command \
    "plan_list_json" \
    "curl -H X-API-Key:<redacted> \"$SERVER_URL/api/v1/plans?project_id=$PROJECT_ID&limit=$LIST_LIMIT&offset=$LIST_OFFSET\"" \
    "$SERVER_URL/api/v1/plans?project_id=$PROJECT_ID&limit=$LIST_LIMIT&offset=$LIST_OFFSET" \
    "/tmp/pms-api-plan-list-benchmark.out"
fi

py scripts/write_rust_server_benchmark_report.py \
  --metrics-file "$METRICS_FILE" \
  --report-file "$REPORT_FILE" \
  --server-url "$SERVER_URL" \
  --project-id "$PROJECT_ID" \
  --project "$PROJECT_NAME" \
  --repetitions "$REPETITIONS"
