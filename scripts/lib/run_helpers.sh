#!/usr/bin/env bash

# Shared helpers for maintained run_* scripts.

pms_use_isolated_direct_runtime() {
  export PMS_WRITE_MODE="direct"
  unset PMS_SERVER_BASE_URL
  unset PMS_API_KEY
  unset PMS_API_KEY_PATH
}

pms_setup_python_runtime() {
  local root_dir="$1"

  if [[ -x "$root_dir/.venv/bin/python" ]]; then
    RUN_MODE="venv"
    PYTHON_BIN="$root_dir/.venv/bin/python"
  elif command -v uv >/dev/null 2>&1; then
    RUN_MODE="uv"
    PYTHON_BIN=""
  elif command -v python3 >/dev/null 2>&1; then
    RUN_MODE="system"
    PYTHON_BIN="$(command -v python3)"
  else
    echo "No supported Python runtime found (.venv/bin/python, uv, or python3)." >&2
    return 1
  fi
}

py() {
  if [[ "${RUN_MODE:-}" == "uv" ]]; then
    uv run python "$@"
  else
    "${PYTHON_BIN:?PYTHON_BIN is not set}" "$@"
  fi
}

pms() {
  if [[ "${RUN_MODE:-}" == "uv" ]]; then
    uv run pms "$@"
  else
    "${PYTHON_BIN:?PYTHON_BIN is not set}" -m pms "$@"
  fi
}

pms_prepare_data_dir() {
  local root_dir="$1"
  local prefix="$2"
  local timestamp
  local data_dir

  timestamp="$(date +"%Y%m%d-%H%M%S")"
  if [[ -n "${PMS_DATA_DIR:-}" ]]; then
    data_dir="$PMS_DATA_DIR"
  else
    mkdir -p "$root_dir/.tmp"
    data_dir="$(mktemp -d "$root_dir/.tmp/${prefix}-${timestamp}.XXXXXX")"
  fi

  export PMS_DATA_DIR="$data_dir"
  export PMS_DATABASE_PATH="${PMS_DATABASE_PATH:-$PMS_DATA_DIR/pms.db}"
  export PMS_LOG_DIR="${PMS_LOG_DIR:-$PMS_DATA_DIR/logs}"
  export PMS_ENV_FILE="${PMS_ENV_FILE:-$PMS_DATA_DIR/.env}"
  mkdir -p "$PMS_DATA_DIR" "$PMS_LOG_DIR"
}

pms_run_bounded_script() {
  local timeout_seconds="$1"
  local cwd="$2"
  shift 2

  py scripts/run_with_timeout.py \
    --timeout-seconds "$timeout_seconds" \
    --cwd "$cwd" \
    -- \
    "$@"
}

pms_run_contract_flow() {
  local label="$1"
  local timeout_seconds="$2"
  local cwd="$3"
  shift 3

  set +e
  pms_run_bounded_script "$timeout_seconds" "$cwd" "$@"
  local flow_exit_code=$?
  set -e
  if [[ "$flow_exit_code" -eq 124 ]]; then
    echo "$label failed: flow exceeded ${timeout_seconds}s timeout." >&2
    return 124
  fi
  if [[ "$flow_exit_code" -ne 0 ]]; then
    echo "$label failed: flow exited with code $flow_exit_code." >&2
    return "$flow_exit_code"
  fi
}

pms_parallel_headroom_value() {
  local default_value="$1"
  local xdist_value="$2"

  if [[ -n "${PYTEST_XDIST_WORKER:-}" ]]; then
    printf '%s' "$xdist_value"
  else
    printf '%s' "$default_value"
  fi
}

pms_allocate_tcp_port() {
  local owner_pid="${1:-$$}"
  shift || true

  py scripts/lease_tcp_port.py allocate --owner-pid "$owner_pid" "$@"
}

pms_release_tcp_port() {
  local lease_path="$1"
  py scripts/lease_tcp_port.py release --lease-path "$lease_path"
}

pms_copy_file_atomic() {
  local source_path="$1"
  local target_path="$2"
  local target_dir
  local target_name
  local temp_path

  target_dir="$(dirname "$target_path")"
  target_name="$(basename "$target_path")"
  mkdir -p "$target_dir"
  temp_path="$(mktemp "$target_dir/.${target_name}.XXXXXX.tmp")"

  cleanup() {
    rm -f "$temp_path"
  }
  trap cleanup RETURN

  if ! cp "$source_path" "$temp_path"; then
    return 1
  fi
  if ! mv -f "$temp_path" "$target_path"; then
    return 1
  fi

  trap - RETURN
}

pms_publish_symlink_atomic() {
  local target_path="$1"
  local link_path="$2"
  local link_dir
  local link_name
  local temp_link
  local legacy_backup=""

  link_dir="$(dirname "$link_path")"
  link_name="$(basename "$link_path")"
  mkdir -p "$link_dir"
  temp_link="$(mktemp "$link_dir/.${link_name}.XXXXXX.tmp")"
  rm -f "$temp_link"

  cleanup() {
    rm -f "$temp_link"
    if [[ -n "$legacy_backup" && -e "$legacy_backup" ]]; then
      mv "$legacy_backup" "$link_path" 2>/dev/null || true
    fi
  }
  trap cleanup RETURN

  ln -s "$target_path" "$temp_link"

  if [[ -e "$link_path" && ! -L "$link_path" ]]; then
    legacy_backup="$link_dir/.${link_name}.legacy.$$"
    mv "$link_path" "$legacy_backup"
  fi

  mv -f "$temp_link" "$link_path"

  if [[ -n "$legacy_backup" ]]; then
    rm -rf "$legacy_backup"
    legacy_backup=""
  fi

  trap - RETURN
}

pms_extract_recovered_api_key() {
  local log_path="$1"
  awk '/^pms_[A-Za-z0-9_-]+$/ { print; exit }' "$log_path"
}

pms_pid_status() {
  local pid="$1"
  ps -o stat= -p "$pid" 2>/dev/null | awk 'NR==1 {gsub(/^[[:space:]]+|[[:space:]]+$/, "", $0); print; exit}'
}

pms_pid_is_running() {
  local pid="$1"
  local status
  status="$(pms_pid_status "$pid")"
  [[ -n "$status" && "${status#Z}" == "$status" ]]
}

pms_process_group_id() {
  local pid="$1"
  ps -o pgid= -p "$pid" 2>/dev/null | awk 'NR==1 {gsub(/^[[:space:]]+|[[:space:]]+$/, "", $0); print; exit}'
}

pms_start_background_server() {
  local log_path="$1"
  local host="$2"
  local port="$3"

  py - "$log_path" "$host" "$port" "${RUN_MODE:-}" "${PYTHON_BIN:-}" <<'PY'
import subprocess
import sys

log_path, host, port, run_mode, python_bin = sys.argv[1:6]
if run_mode == "uv":
    cmd = [
        "uv",
        "run",
        "python",
        "-m",
        "uvicorn",
        "pms.api.app:app",
        "--host",
        host,
        "--port",
        port,
        "--log-level",
        "info",
    ]
else:
    if not python_bin:
        raise SystemExit("PYTHON_BIN is not set for non-uv mode")
    cmd = [
        python_bin,
        "-m",
        "uvicorn",
        "pms.api.app:app",
        "--host",
        host,
        "--port",
        port,
        "--log-level",
        "info",
    ]

with open(log_path, "ab", buffering=0) as log_handle:
    process = subprocess.Popen(
        cmd,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
print(process.pid)
PY
}

pms_wait_for_server_health() {
  local server_url="$1"
  local pid="${2:-}"
  local timeout_seconds="${3:-${PMS_LOCAL_SERVER_STARTUP_TIMEOUT_SECONDS:-60}}"

  py - "$server_url" "$pid" "$timeout_seconds" <<'PY'
import math
import os
import signal
import sys
import time

import httpx

server_url, pid_text, timeout_text = sys.argv[1:4]
pid = int(pid_text) if pid_text else None
timeout_seconds = float(timeout_text)
deadline = time.monotonic() + timeout_seconds
attempt_timeout = min(5.0, max(1.0, timeout_seconds / 12.0))

while time.monotonic() < deadline:
    if pid is not None:
        try:
            os.kill(pid, 0)
        except OSError:
            raise SystemExit(1)
    try:
        response = httpx.get(
            f"{server_url.rstrip('/')}/api/v1/health",
            timeout=attempt_timeout,
        )
        response.raise_for_status()
        raise SystemExit(0)
    except httpx.HTTPError:
        time.sleep(0.5)

raise SystemExit(1)
PY
}

pms_wait_for_pid_exit() {
  local pid="$1"
  local timeout_seconds="${2:-5}"
  local waited=0

  while pms_pid_is_running "$pid"; do
    if (( waited * 10 >= timeout_seconds * 10 )); then
      return 1
    fi
    sleep 0.1
    waited=$((waited + 1))
  done
  return 0
}

pms_stop_background_pid() {
  local pid="${1:-}"
  local timeout_seconds="${2:-5}"
  local pgid=""
  local kill_group=0

  if [[ -z "$pid" ]]; then
    return 0
  fi

  if ! pms_pid_is_running "$pid"; then
    return 0
  fi

  pgid="$(pms_process_group_id "$pid")"
  if [[ -n "$pgid" && "$pgid" == "$pid" ]]; then
    kill_group=1
  fi

  if [[ "$kill_group" -eq 1 ]]; then
    kill -TERM -- "-$pgid" >/dev/null 2>&1 || true
  else
    kill -TERM "$pid" >/dev/null 2>&1 || true
  fi
  if pms_wait_for_pid_exit "$pid" "$timeout_seconds"; then
    return 0
  fi

  if [[ "$kill_group" -eq 1 ]]; then
    kill -KILL -- "-$pgid" >/dev/null 2>&1 || true
  else
    kill -KILL "$pid" >/dev/null 2>&1 || true
  fi
  pms_wait_for_pid_exit "$pid" 2 >/dev/null 2>&1 || true
}
