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

pms() {
  if [[ "$RUN_MODE" == "uv" ]]; then
    uv run pms "$@"
  else
    "$PYTHON_BIN" -m pms "$@"
  fi
}

py() {
  if [[ "$RUN_MODE" == "uv" ]]; then
    uv run python "$@"
  else
    "$PYTHON_BIN" "$@"
  fi
}

timestamp="$(date +"%Y%m%d-%H%M%S")"
if [[ -n "${PMS_DATA_DIR:-}" ]]; then
  data_dir="$PMS_DATA_DIR"
else
  mkdir -p "$ROOT_DIR/.tmp"
  data_dir="$(mktemp -d "$ROOT_DIR/.tmp/demo-smoke-${timestamp}.XXXXXX")"
fi

export PMS_DATA_DIR="$data_dir"
export PMS_DATABASE_PATH="${PMS_DATABASE_PATH:-$PMS_DATA_DIR/pms.db}"
export PMS_LOG_DIR="${PMS_LOG_DIR:-$PMS_DATA_DIR/logs}"
export PMS_ENV_FILE="${PMS_ENV_FILE:-$PMS_DATA_DIR/.env}"

mkdir -p "$PMS_DATA_DIR" "$PMS_LOG_DIR"

suffix="${PMS_DEMO_SUFFIX:-$timestamp}"
org_name="${PMS_DEMO_ORG:-Demo Org $suffix}"
portfolio_name="${PMS_DEMO_PORTFOLIO:-Demo Portfolio $suffix}"
program_name="${PMS_DEMO_PROGRAM:-Demo Program $suffix}"
product_name="${PMS_DEMO_PRODUCT:-Demo Product $suffix}"
project_name="${PMS_DEMO_PROJECT:-Demo Project $suffix}"
actor_name="${PMS_DEMO_ACTOR:-demo-bot}"

echo "Running PMS smoke demo"
echo "  run_mode: $RUN_MODE"
echo "  data_dir: $PMS_DATA_DIR"
echo "  database: $PMS_DATABASE_PATH"

pms init >/dev/null

start_guide_path="$PMS_DATA_DIR/start-guide.json"
pms start --format json >"$start_guide_path"
[ -s "$start_guide_path" ]

pms quickstart \
  --defaults \
  --org "$org_name" \
  --portfolio "$portfolio_name" \
  --program "$program_name" \
  --product "$product_name" \
  --project "$project_name" \
  --task "Bootstrap environment" \
  --task "Ship first endpoint" \
  --create-plan \
  --create-rollups >/dev/null

ready_json="$(pms task ready --project "$project_name" --format json)"
task_title="$(
  printf '%s' "$ready_json" | py -c \
    'import json,sys; payload=json.load(sys.stdin); items=payload if isinstance(payload, list) else payload.get("items", []) if isinstance(payload, dict) else []; print(items[0]["title"] if items else "")'
)"

if [[ -z "$task_title" ]]; then
  list_json="$(pms task list --project "$project_name" --format json)"
  task_title="$(
    printf '%s' "$list_json" | py -c \
      'import json,sys; payload=json.load(sys.stdin); items=payload.get("items", []); print(items[0]["title"] if items else "")'
  )"
fi

if [[ -z "$task_title" ]]; then
  echo "Smoke demo failed: no task available for start/progress/complete flow." >&2
  exit 1
fi

pms task start "$task_title" --project "$project_name" --by "$actor_name" --format json >/dev/null
pms task progress "$task_title" --project "$project_name" 60 "Smoke demo progress update" --by "$actor_name" --format json >/dev/null
pms task complete "$task_title" --project "$project_name" --by "$actor_name" --format json >/dev/null

daily_summary_path="$PMS_DATA_DIR/daily-summary.json"
project_list_path="$PMS_DATA_DIR/projects.json"
capabilities_path="$PMS_DATA_DIR/capabilities.json"

pms work daily \
  --scope-type project \
  --scope "$project_name" \
  --format json \
  --export "$daily_summary_path" \
  --no-attach >/dev/null

pms project list -f json >"$project_list_path"
pms capabilities list --format json --limit 1000 >"$capabilities_path"

echo "Smoke demo completed successfully."
echo "  project: $project_name"
echo "  completed_task: $task_title"
echo "  start_guide: $start_guide_path"
echo "  daily_summary: $daily_summary_path"
echo "  project_list: $project_list_path"
echo "  capabilities: $capabilities_path"
