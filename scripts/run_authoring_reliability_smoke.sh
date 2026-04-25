#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/run_helpers.sh"
pms_setup_python_runtime "$ROOT_DIR"
pms_use_isolated_direct_runtime

timestamp="$(date +"%Y%m%d-%H%M%S")"
if [[ -n "${PMS_DATA_DIR:-}" ]]; then
  data_dir="$PMS_DATA_DIR"
else
  mkdir -p "$ROOT_DIR/.tmp"
  data_dir="$(mktemp -d "$ROOT_DIR/.tmp/authoring-reliability-${timestamp}.XXXXXX")"
fi

export PMS_DATA_DIR="$data_dir"
export PMS_DATABASE_PATH="${PMS_DATABASE_PATH:-$PMS_DATA_DIR/pms.db}"
export PMS_LOG_DIR="${PMS_LOG_DIR:-$PMS_DATA_DIR/logs}"
export PMS_ENV_FILE="${PMS_ENV_FILE:-$PMS_DATA_DIR/.env}"
mkdir -p "$PMS_DATA_DIR" "$PMS_LOG_DIR"

suffix="${PMS_AUTHORING_SUFFIX:-$timestamp}"
product_name="Authoring Reliability Product $suffix"
project_name="Authoring Reliability Project $suffix"
goal_name="Authoring Reliability Goal $suffix"
objective_active_name="Authoring Active Objective $suffix"
objective_archived_name="Authoring Archived Objective $suffix"

echo "Running authoring reliability smoke"
echo "  run_mode: $RUN_MODE"
echo "  data_dir: $PMS_DATA_DIR"
echo "  database: $PMS_DATABASE_PATH"

pms init >/dev/null
pms product create "$product_name" --owner codex >/dev/null
pms project create "$project_name" --product "$product_name" >/dev/null
pms goal create "$goal_name" --owner codex --project "$project_name" >/dev/null
pms objective create "$objective_active_name" --goal "$goal_name" >/dev/null
pms objective create "$objective_archived_name" --goal "$goal_name" >/dev/null
pms objective archive "$objective_archived_name" --goal "$goal_name" >/dev/null

summary_path="$PMS_DATA_DIR/goal-summary.txt"
pms goal summary "$goal_name" >"$summary_path"

if ! rg -q "Objectives: 0/1 \| Key Results: 0/0" "$summary_path"; then
  echo "Authoring reliability smoke failed: goal summary did not exclude archived objectives." >&2
  cat "$summary_path" >&2
  exit 1
fi

pytest_target=(
  "tests/unit/test_services.py::TestGoalService::test_goal_summary_excludes_archived_objectives_and_key_results"
  "tests/test_database_init.py::test_concurrent_goal_rollup_updates_retry_revision_conflicts"
)

if [[ "$RUN_MODE" == "uv" ]]; then
  uv run pytest "${pytest_target[@]}" -q
else
  "$PYTHON_BIN" -m pytest "${pytest_target[@]}" -q
fi

echo "Authoring reliability smoke completed successfully."
echo "  summary: $summary_path"
