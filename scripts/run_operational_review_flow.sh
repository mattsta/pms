#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/run_helpers.sh"

pms_setup_python_runtime "$ROOT_DIR"
pms_prepare_data_dir "$ROOT_DIR" "operational-review"
pms_use_isolated_direct_runtime
timestamp="$(date +"%Y%m%d-%H%M%S")"

suffix="${PMS_OPERATIONS_SUFFIX:-$timestamp}"
org_name="${PMS_OPERATIONS_ORG:-Operational Review Org $suffix}"
portfolio_name="${PMS_OPERATIONS_PORTFOLIO:-Operational Review Portfolio $suffix}"
program_name="${PMS_OPERATIONS_PROGRAM:-Operational Review Program $suffix}"
product_name="${PMS_OPERATIONS_PRODUCT:-Operational Review Product $suffix}"
project_name="${PMS_OPERATIONS_PROJECT:-Operational Review Project $suffix}"
actor_name="${PMS_OPERATIONS_ACTOR:-ops-reviewer}"
queue_name="${PMS_OPERATIONS_QUEUE_NAME:-ops-review-$suffix}"
review_note="${PMS_OPERATIONS_REVIEW_NOTE:-Weekly operational review checkpoint}"
review_metadata="${PMS_OPERATIONS_REVIEW_METADATA:-{\"session\":\"operational-review\",\"cadence\":\"weekly\"}}"

review_task="${PMS_OPERATIONS_REVIEW_TASK:-Review blocker queue}"
status_task="${PMS_OPERATIONS_STATUS_TASK:-Refresh status notes}"
blocked_task="${PMS_OPERATIONS_BLOCKED_TASK:-Resolve escalated dependency}"
next_task="${PMS_OPERATIONS_NEXT_TASK:-Prepare next operator actions}"

bootstrap_path="$PMS_DATA_DIR/operational-review.bootstrap.json"
dashboard_path="$PMS_DATA_DIR/operational-review.dashboard.json"
daily_path="$PMS_DATA_DIR/operational-review.daily.json"
review_path="$PMS_DATA_DIR/operational-review.review.json"
blocked_path="$PMS_DATA_DIR/operational-review.blocked.json"
ready_path="$PMS_DATA_DIR/operational-review.ready.json"
queue_run_path="$PMS_DATA_DIR/operational-review.queue-run.json"
lineage_path="$PMS_DATA_DIR/operational-review.lineage.json"
project_report_path="$PMS_DATA_DIR/operational-review.project-report.json"
history_path="$PMS_DATA_DIR/operational-review.history.json"
metrics_path="$PMS_DATA_DIR/operational-review.metrics.csv"
summary_path="$PMS_DATA_DIR/operational-review.summary.json"

echo "Running operational review flow"
echo "  run_mode: $RUN_MODE"
echo "  data_dir: $PMS_DATA_DIR"
echo "  project: $project_name"

pms init >/dev/null
pms quickstart \
  --defaults \
  --org "$org_name" \
  --portfolio "$portfolio_name" \
  --program "$program_name" \
  --product "$product_name" \
  --project "$project_name" \
  --task "$review_task" \
  --task "$status_task" \
  --task "$blocked_task" \
  --task "$next_task" \
  --create-plan \
  --create-rollups \
  --format json >"$bootstrap_path"

project_id="$(
  py scripts/json_query.py path --file "$bootstrap_path" --get artifacts_created.project.id
)"
plan_id="$(
  py scripts/json_query.py path --file "$bootstrap_path" --get artifacts_created.plan.id
)"

if [[ -z "$project_id" || -z "$plan_id" ]]; then
  echo "Operational review flow failed: bootstrap artifacts missing project or plan IDs." >&2
  exit 1
fi

review_task_id="$(
  pms task list --project "$project_name" --format json >"$ready_path.tmp" && \
  py scripts/json_query.py find --file "$ready_path.tmp" --items items --match-field title --match-value "$review_task" --get id
)"
status_task_id="$(
  py scripts/json_query.py find --file "$ready_path.tmp" --items items --match-field title --match-value "$status_task" --get id
)"
blocked_task_id="$(
  py scripts/json_query.py find --file "$ready_path.tmp" --items items --match-field title --match-value "$blocked_task" --get id
)"
rm -f "$ready_path.tmp"

if [[ -z "$review_task_id" || -z "$status_task_id" || -z "$blocked_task_id" ]]; then
  echo "Operational review flow failed: could not resolve task IDs." >&2
  exit 1
fi

pms task start "$review_task" --project "$project_name" --by "$actor_name" --format json >/dev/null
pms task progress "$review_task" 60 "Blocker queue triaged; escalations identified" --project "$project_name" --by "$actor_name" --format json >/dev/null
pms task evidence add "$review_task" note operational-review --description "Weekly review notes captured" --project "$project_name" >/dev/null

pms task start "$status_task" --project "$project_name" --by "$actor_name" --format json >/dev/null
pms task progress "$status_task" 35 "Status notes refreshed for operators" --project "$project_name" --by "$actor_name" --format json >/dev/null

pms task block "$blocked_task" --project "$project_name" --reason "Waiting on upstream dependency confirmation" --by "$actor_name" >/dev/null

pms queue create \
  "$queue_name" \
  --scope-type project \
  --scope "$project_name" \
  --description "Operational review queue for active and blocked work" \
  --filters '{"statuses":["in_progress","blocked","todo"]}' >/dev/null

queue_id="$(
  pms queue list --format json >"$queue_run_path.tmp" && \
  py scripts/json_query.py find --file "$queue_run_path.tmp" --items items --match-field name --match-value "$queue_name" --get id
)"
rm -f "$queue_run_path.tmp"
if [[ -z "$queue_id" ]]; then
  echo "Operational review flow failed: could not resolve queue ID." >&2
  exit 1
fi

pms dashboard --format json >"$dashboard_path"
pms work daily \
  --scope-type project \
  --scope "$project_name" \
  --include-timeline \
  --include-history \
  --format json \
  --no-attach \
  --export "$daily_path" >/dev/null
pms work review \
  --scope-type project \
  --scope "$project_name" \
  --reviewed-by "$actor_name" \
  --note "$review_note" \
  --metadata "$review_metadata" \
  --view detail \
  --include-history \
  --format json >"$review_path"
pms task blocked --project "$project_name" --format json >"$blocked_path"
pms task ready --project "$project_name" --format json >"$ready_path"
pms queue run "$queue_id" --format json >"$queue_run_path"
pms plan lineage --project "$project_name" --format json >"$lineage_path"
pms report project "$project_id" --format json -o "$project_report_path" >/dev/null
pms report history --days 14 --format json -o "$history_path" >/dev/null
pms report metrics --project "$project_id" --format csv -o "$metrics_path" >/dev/null

[ -s "$bootstrap_path" ]
[ -s "$dashboard_path" ]
[ -s "$daily_path" ]
[ -s "$review_path" ]
[ -s "$blocked_path" ]
[ -s "$ready_path" ]
[ -s "$queue_run_path" ]
[ -s "$lineage_path" ]
[ -s "$project_report_path" ]
[ -s "$history_path" ]
[ -s "$metrics_path" ]

export PMS_OPERATIONS_PROJECT_NAME="$project_name"
export PMS_OPERATIONS_PROJECT_ID="$project_id"
export PMS_OPERATIONS_PLAN_ID="$plan_id"
export PMS_OPERATIONS_REVIEW_TASK_ID="$review_task_id"
export PMS_OPERATIONS_STATUS_TASK_ID="$status_task_id"
export PMS_OPERATIONS_BLOCKED_TASK_ID="$blocked_task_id"
export PMS_OPERATIONS_QUEUE_ID="$queue_id"
export PMS_OPERATIONS_BOOTSTRAP_PATH="$bootstrap_path"
export PMS_OPERATIONS_DASHBOARD_PATH="$dashboard_path"
export PMS_OPERATIONS_DAILY_PATH="$daily_path"
export PMS_OPERATIONS_REVIEW_PATH="$review_path"
export PMS_OPERATIONS_BLOCKED_PATH="$blocked_path"
export PMS_OPERATIONS_READY_PATH="$ready_path"
export PMS_OPERATIONS_QUEUE_RUN_PATH="$queue_run_path"
export PMS_OPERATIONS_LINEAGE_PATH="$lineage_path"
export PMS_OPERATIONS_PROJECT_REPORT_PATH="$project_report_path"
export PMS_OPERATIONS_HISTORY_PATH="$history_path"
export PMS_OPERATIONS_METRICS_PATH="$metrics_path"
export PMS_OPERATIONS_SUMMARY_PATH="$summary_path"

py scripts/write_operational_review_summary.py

echo "Operational review flow completed."
echo "  dashboard: $dashboard_path"
echo "  daily: $daily_path"
echo "  review: $review_path"
echo "  summary: $summary_path"
