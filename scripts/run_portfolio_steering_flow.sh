#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/run_helpers.sh"

pms_setup_python_runtime "$ROOT_DIR"
pms_prepare_data_dir "$ROOT_DIR" "portfolio-steering"
pms_use_isolated_direct_runtime
timestamp="$(date +"%Y%m%d-%H%M%S")"

suffix="${PMS_STEERING_SUFFIX:-$timestamp}"
org_name="${PMS_STEERING_ORG:-Steering Org $suffix}"
portfolio_name="${PMS_STEERING_PORTFOLIO:-Customer Experience $suffix}"
program_name="${PMS_STEERING_PROGRAM:-Q3 Launch $suffix}"
api_product_name="${PMS_STEERING_API_PRODUCT:-Checkout API $suffix}"
ui_product_name="${PMS_STEERING_UI_PRODUCT:-Web Store $suffix}"
api_project_name="${PMS_STEERING_API_PROJECT:-Checkout API v2 $suffix}"
ui_project_name="${PMS_STEERING_UI_PROJECT:-Web Store v5 $suffix}"
api_goal_name="${PMS_STEERING_API_GOAL:-Ship Checkout API v2 $suffix}"
ui_goal_name="${PMS_STEERING_UI_GOAL:-Ship Web Store v5 $suffix}"
api_task_title="${PMS_STEERING_API_TASK:-Implement payment endpoint}"
ui_task_title="${PMS_STEERING_UI_TASK:-Checkout UI integration}"
actor_name="${PMS_STEERING_ACTOR:-steering-bot}"

bootstrap_path="$PMS_DATA_DIR/portfolio-steering.bootstrap.json"
org_dashboard_path="$PMS_DATA_DIR/portfolio-steering.org-dashboard.json"
portfolio_dashboard_path="$PMS_DATA_DIR/portfolio-steering.portfolio-dashboard.json"
program_dashboard_path="$PMS_DATA_DIR/portfolio-steering.program-dashboard.json"
portfolio_summary_path="$PMS_DATA_DIR/portfolio-steering.portfolio-summary.json"
program_summary_path="$PMS_DATA_DIR/portfolio-steering.program-summary.json"
portfolio_daily_path="$PMS_DATA_DIR/portfolio-steering.portfolio-daily.json"
program_daily_path="$PMS_DATA_DIR/portfolio-steering.program-daily.json"
task_graph_path="$PMS_DATA_DIR/portfolio-steering.task-graph.json"
api_report_path="$PMS_DATA_DIR/portfolio-steering.api-project-report.json"
ui_report_path="$PMS_DATA_DIR/portfolio-steering.ui-project-report.json"
metrics_path="$PMS_DATA_DIR/portfolio-steering.metrics.csv"
summary_path="$PMS_DATA_DIR/portfolio-steering.summary.json"

echo "Running portfolio steering flow"
echo "  run_mode: $RUN_MODE"
echo "  data_dir: $PMS_DATA_DIR"
echo "  portfolio: $portfolio_name"

pms init >/dev/null
pms quickstart \
  --defaults \
  --org "$org_name" \
  --portfolio "$portfolio_name" \
  --program "$program_name" \
  --product "$api_product_name" \
  --project "$api_project_name" \
  --task "$api_task_title" \
  --task "Publish API docs" \
  --create-plan \
  --create-rollups \
  --format json >"$bootstrap_path"

pms product create "$ui_product_name" >/dev/null
pms project create \
  "$ui_project_name" \
  --description "Cross-project UI launch coordination board" \
  --org "$org_name" \
  --portfolio "$portfolio_name" \
  --program "$program_name" \
  --product "$ui_product_name" >/dev/null

pms task add "$ui_project_name" "$ui_task_title" -p high --format json >/dev/null
pms task add "$ui_project_name" "E2E purchase flow tests" -p high --format json >/dev/null

org_id="$(
  pms org list -f json >"$PMS_DATA_DIR/orgs.json" && \
  py scripts/json_query.py find --file "$PMS_DATA_DIR/orgs.json" --items items --match-field name --match-value "$org_name" --get id
)"
portfolio_id="$(
  pms portfolio list --org "$org_name" --format json >"$PMS_DATA_DIR/portfolios.json" && \
  py scripts/json_query.py find --file "$PMS_DATA_DIR/portfolios.json" --items items --match-field name --match-value "$portfolio_name" --get id
)"
program_id="$(
  pms program list --org "$org_name" --portfolio "$portfolio_name" --format json >"$PMS_DATA_DIR/programs.json" && \
  py scripts/json_query.py find --file "$PMS_DATA_DIR/programs.json" --items items --match-field name --match-value "$program_name" --get id
)"
api_project_id="$(
  py scripts/json_query.py path --file "$bootstrap_path" --get artifacts_created.project.id
)"
ui_project_id="$(
  pms project list -f json >"$PMS_DATA_DIR/projects.json" && \
  py scripts/json_query.py find --file "$PMS_DATA_DIR/projects.json" --items items --match-field name --match-value "$ui_project_name" --get id
)"

if [[ -z "$org_id" || -z "$portfolio_id" || -z "$program_id" || -z "$api_project_id" || -z "$ui_project_id" ]]; then
  echo "Portfolio steering flow failed: could not resolve scope IDs." >&2
  exit 1
fi

pms goal create "$api_goal_name" --project "$api_project_name" --owner "$actor_name" >/dev/null
pms goal create "$ui_goal_name" --project "$ui_project_name" --owner "$actor_name" >/dev/null

pms goal list --format json >"$PMS_DATA_DIR/goals.json"
api_goal_id="$(
  py scripts/json_query.py find --file "$PMS_DATA_DIR/goals.json" --items items --match-field name --match-value "$api_goal_name" --get id
)"
ui_goal_id="$(
  py scripts/json_query.py find --file "$PMS_DATA_DIR/goals.json" --items items --match-field name --match-value "$ui_goal_name" --get id
)"
if [[ -z "$api_goal_id" || -z "$ui_goal_id" ]]; then
  echo "Portfolio steering flow failed: could not resolve goal IDs." >&2
  exit 1
fi

pms program update "$program_id" --goal-id "$api_goal_id" --goal-id "$ui_goal_id" --format json >/dev/null
pms portfolio update "$portfolio_id" --goal-id "$api_goal_id" --goal-id "$ui_goal_id" --format json >/dev/null

pms task list --project "$api_project_name" --format json >"$PMS_DATA_DIR/api-tasks.json"
pms task list --project "$ui_project_name" --format json >"$PMS_DATA_DIR/ui-tasks.json"
api_task_id="$(
  py scripts/json_query.py find --file "$PMS_DATA_DIR/api-tasks.json" --items items --match-field title --match-value "$api_task_title" --get id
)"
ui_task_id="$(
  py scripts/json_query.py find --file "$PMS_DATA_DIR/ui-tasks.json" --items items --match-field title --match-value "$ui_task_title" --get id
)"
if [[ -z "$api_task_id" || -z "$ui_task_id" ]]; then
  echo "Portfolio steering flow failed: could not resolve cross-project task IDs." >&2
  exit 1
fi

pms task dep add "$ui_task_id" "$api_task_id" --type blocks >/dev/null
pms task start "$api_task_title" --project "$api_project_name" --by "$actor_name" --format json >/dev/null
pms task progress "$api_task_title" 55 "API rollout underway for portfolio launch" --project "$api_project_name" --by "$actor_name" --format json >/dev/null

pms org dashboard --format json >"$org_dashboard_path"
pms portfolio dashboard --org "$org_name" --format json >"$portfolio_dashboard_path"
pms program dashboard --org "$org_name" --portfolio "$portfolio_name" --format json >"$program_dashboard_path"
pms portfolio summary "$portfolio_name" --format json >"$portfolio_summary_path"
pms program summary "$program_name" --format json >"$program_summary_path"
pms work daily --scope-type portfolio --scope "$portfolio_name" --format json --no-attach --export "$portfolio_daily_path" >/dev/null
pms work daily --scope-type program --scope "$program_name" --format json --no-attach --export "$program_daily_path" >/dev/null
pms task graph "$ui_task_id" --format json >"$task_graph_path"
pms report project "$api_project_id" --format json -o "$api_report_path" >/dev/null
pms report project "$ui_project_id" --format json -o "$ui_report_path" >/dev/null
pms report metrics --format csv -o "$metrics_path" >/dev/null

[ -s "$bootstrap_path" ]
[ -s "$org_dashboard_path" ]
[ -s "$portfolio_dashboard_path" ]
[ -s "$program_dashboard_path" ]
[ -s "$portfolio_summary_path" ]
[ -s "$program_summary_path" ]
[ -s "$portfolio_daily_path" ]
[ -s "$program_daily_path" ]
[ -s "$task_graph_path" ]
[ -s "$api_report_path" ]
[ -s "$ui_report_path" ]
[ -s "$metrics_path" ]

export PMS_STEERING_ORG_NAME="$org_name"
export PMS_STEERING_ORG_ID="$org_id"
export PMS_STEERING_PORTFOLIO_NAME="$portfolio_name"
export PMS_STEERING_PORTFOLIO_ID="$portfolio_id"
export PMS_STEERING_PROGRAM_NAME="$program_name"
export PMS_STEERING_PROGRAM_ID="$program_id"
export PMS_STEERING_API_PROJECT_NAME="$api_project_name"
export PMS_STEERING_API_PROJECT_ID="$api_project_id"
export PMS_STEERING_UI_PROJECT_NAME="$ui_project_name"
export PMS_STEERING_UI_PROJECT_ID="$ui_project_id"
export PMS_STEERING_API_GOAL_ID="$api_goal_id"
export PMS_STEERING_UI_GOAL_ID="$ui_goal_id"
export PMS_STEERING_API_TASK_ID="$api_task_id"
export PMS_STEERING_UI_TASK_ID="$ui_task_id"
export PMS_STEERING_BOOTSTRAP_PATH="$bootstrap_path"
export PMS_STEERING_ORG_DASHBOARD_PATH="$org_dashboard_path"
export PMS_STEERING_PORTFOLIO_DASHBOARD_PATH="$portfolio_dashboard_path"
export PMS_STEERING_PROGRAM_DASHBOARD_PATH="$program_dashboard_path"
export PMS_STEERING_PORTFOLIO_SUMMARY_PATH="$portfolio_summary_path"
export PMS_STEERING_PROGRAM_SUMMARY_PATH="$program_summary_path"
export PMS_STEERING_PORTFOLIO_DAILY_PATH="$portfolio_daily_path"
export PMS_STEERING_PROGRAM_DAILY_PATH="$program_daily_path"
export PMS_STEERING_TASK_GRAPH_PATH="$task_graph_path"
export PMS_STEERING_API_REPORT_PATH="$api_report_path"
export PMS_STEERING_UI_REPORT_PATH="$ui_report_path"
export PMS_STEERING_METRICS_PATH="$metrics_path"
export PMS_STEERING_SUMMARY_PATH="$summary_path"

py scripts/write_portfolio_steering_summary.py

echo "Portfolio steering flow completed."
echo "  portfolio dashboard: $portfolio_dashboard_path"
echo "  program dashboard: $program_dashboard_path"
echo "  task graph: $task_graph_path"
echo "  summary: $summary_path"
