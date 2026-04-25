#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/run_helpers.sh"

pms_setup_python_runtime "$ROOT_DIR"
pms_prepare_data_dir "$ROOT_DIR" "backlog-triage"
pms_use_isolated_direct_runtime
timestamp="$(date +"%Y%m%d-%H%M%S")"

suffix="${PMS_BACKLOG_SUFFIX:-$timestamp}"
org_name="${PMS_BACKLOG_ORG:-Backlog Triage Org $suffix}"
portfolio_name="${PMS_BACKLOG_PORTFOLIO:-Backlog Triage Portfolio $suffix}"
program_name="${PMS_BACKLOG_PROGRAM:-Backlog Triage Program $suffix}"
product_name="${PMS_BACKLOG_PRODUCT:-Backlog Triage Product $suffix}"
project_name="${PMS_BACKLOG_PROJECT:-Backlog Triage Project $suffix}"
actor_name="${PMS_BACKLOG_ACTOR:-triage-lead}"
queue_name="${PMS_BACKLOG_QUEUE_NAME:-backlog-triage-$suffix}"

critical_task="${PMS_BACKLOG_CRITICAL_TASK:-Triage top customer issue}"
high_task="${PMS_BACKLOG_HIGH_TASK:-Refine API pagination backlog}"
duplicate_task="${PMS_BACKLOG_DUPLICATE_TASK:-Consolidate queue filter naming}"
low_task="${PMS_BACKLOG_LOW_TASK:-Remove stale label alias}"

bootstrap_path="$PMS_DATA_DIR/backlog-triage.bootstrap.json"
dashboard_path="$PMS_DATA_DIR/backlog-triage.dashboard.json"
ready_path="$PMS_DATA_DIR/backlog-triage.ready.json"
available_path="$PMS_DATA_DIR/backlog-triage.available.json"
duplicates_path="$PMS_DATA_DIR/backlog-triage.duplicates.json"
merge_preview_path="$PMS_DATA_DIR/backlog-triage.merge-preview.json"
queue_presets_path="$PMS_DATA_DIR/backlog-triage.queue-presets.json"
queue_run_path="$PMS_DATA_DIR/backlog-triage.queue-run.json"
daily_path="$PMS_DATA_DIR/backlog-triage.daily.json"
lineage_path="$PMS_DATA_DIR/backlog-triage.lineage.json"
project_report_path="$PMS_DATA_DIR/backlog-triage.project-report.json"
metrics_path="$PMS_DATA_DIR/backlog-triage.metrics.csv"
summary_path="$PMS_DATA_DIR/backlog-triage.summary.json"
tasks_list_path="$PMS_DATA_DIR/backlog-triage.tasks.json"

echo "Running backlog triage flow"
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
  --task "$critical_task" \
  --task "$high_task" \
  --task "$duplicate_task" \
  --task "$low_task" \
  --create-plan \
  --create-rollups \
  --format json >"$bootstrap_path"

pms task add "$project_name" "$duplicate_task" --priority medium --complexity 3 >/dev/null

project_id="$(
  py scripts/json_query.py path --file "$bootstrap_path" --get artifacts_created.project.id
)"
plan_id="$(
  py scripts/json_query.py path --file "$bootstrap_path" --get artifacts_created.plan.id
)"
if [[ -z "$project_id" || -z "$plan_id" ]]; then
  echo "Backlog triage flow failed: bootstrap artifacts missing project or plan IDs." >&2
  exit 1
fi

pms task list --project "$project_name" --format json >"$tasks_list_path"
critical_task_id="$(
  py scripts/json_query.py find --file "$tasks_list_path" --items items --match-field title --match-value "$critical_task" --get id
)"
high_task_id="$(
  py scripts/json_query.py find --file "$tasks_list_path" --items items --match-field title --match-value "$high_task" --get id
)"
low_task_id="$(
  py scripts/json_query.py find --file "$tasks_list_path" --items items --match-field title --match-value "$low_task" --get id
)"
if [[ -z "$critical_task_id" || -z "$high_task_id" || -z "$low_task_id" ]]; then
  echo "Backlog triage flow failed: could not resolve task IDs." >&2
  exit 1
fi

pms task update "$critical_task" --project "$project_name" --priority critical --complexity-points 13 --format json >/dev/null
pms task update "$high_task" --project "$project_name" --priority high --complexity-points 8 --format json >/dev/null
pms task update "$low_task" --project "$project_name" --priority low --complexity-points 1 --format json >/dev/null

pms task start "$critical_task" --project "$project_name" --by "$actor_name" --format json >/dev/null
pms task progress "$critical_task" 25 "Customer impact triaged; priority lock in progress" --project "$project_name" --by "$actor_name" --format json >/dev/null

pms queue create \
  "$queue_name" \
  --scope-type project \
  --scope "$project_name" \
  --description "Backlog triage queue for ready and active prioritization work" \
  --filters '{"statuses":["todo","in_progress"]}' >/dev/null

queue_id="$(
  pms queue list --format json >"$queue_run_path.tmp" && \
  py scripts/json_query.py find --file "$queue_run_path.tmp" --items items --match-field name --match-value "$queue_name" --get id
)"
rm -f "$queue_run_path.tmp"
if [[ -z "$queue_id" ]]; then
  echo "Backlog triage flow failed: could not resolve queue ID." >&2
  exit 1
fi

pms dashboard --format json >"$dashboard_path"
pms task ready --project "$project_name" --format json >"$ready_path"
pms task available --project "$project_name" --format json >"$available_path"
pms task duplicates --project "$project_name" --format json >"$duplicates_path"

duplicate_primary_id="$(
  py scripts/json_query.py path --file "$duplicates_path" --get items.0.suggested_primary_id 2>/dev/null || true
)"
if [[ -z "$duplicate_primary_id" ]]; then
  duplicate_primary_id="$(
    py scripts/json_query.py path --file "$duplicates_path" --get 0.suggested_primary_id 2>/dev/null || true
  )"
fi
if [[ -z "$duplicate_primary_id" ]]; then
  duplicate_primary_id="$(
    py scripts/json_query.py path --file "$duplicates_path" --get items.0.tasks.0.id 2>/dev/null || true
  )"
fi
if [[ -z "$duplicate_primary_id" ]]; then
  duplicate_primary_id="$(
    py scripts/json_query.py path --file "$duplicates_path" --get 0.tasks.0.id 2>/dev/null || true
  )"
fi
duplicate_secondary_id="$(
  py scripts/json_query.py path --file "$duplicates_path" --get items.0.tasks.1.id 2>/dev/null || true
)"
if [[ -z "$duplicate_secondary_id" ]]; then
  duplicate_secondary_id="$(
    py scripts/json_query.py path --file "$duplicates_path" --get 0.tasks.1.id 2>/dev/null || true
  )"
fi
if [[ -z "$duplicate_primary_id" || -z "$duplicate_secondary_id" ]]; then
  echo "Backlog triage flow failed: duplicate detection did not produce merge candidates." >&2
  exit 1
fi

pms task merge-preview "$duplicate_primary_id" --duplicate-id "$duplicate_secondary_id" --format json >"$merge_preview_path"
pms queue presets --project "$project_name" --view detail --format json >"$queue_presets_path"
pms queue run "$queue_id" --format json >"$queue_run_path"
pms work daily \
  --scope-type project \
  --scope "$project_name" \
  --include-history \
  --format json \
  --no-attach \
  --export "$daily_path" >/dev/null
pms plan lineage --project "$project_name" --format json >"$lineage_path"
pms report project "$project_id" --format json -o "$project_report_path" >/dev/null
pms report metrics --project "$project_id" --format csv -o "$metrics_path" >/dev/null

[ -s "$bootstrap_path" ]
[ -s "$dashboard_path" ]
[ -s "$ready_path" ]
[ -s "$available_path" ]
[ -s "$duplicates_path" ]
[ -s "$merge_preview_path" ]
[ -s "$queue_presets_path" ]
[ -s "$queue_run_path" ]
[ -s "$daily_path" ]
[ -s "$lineage_path" ]
[ -s "$project_report_path" ]
[ -s "$metrics_path" ]

export PMS_BACKLOG_PROJECT_NAME="$project_name"
export PMS_BACKLOG_PROJECT_ID="$project_id"
export PMS_BACKLOG_PLAN_ID="$plan_id"
export PMS_BACKLOG_CRITICAL_TASK_ID="$critical_task_id"
export PMS_BACKLOG_HIGH_TASK_ID="$high_task_id"
export PMS_BACKLOG_DUPLICATE_PRIMARY_ID="$duplicate_primary_id"
export PMS_BACKLOG_DUPLICATE_SECONDARY_ID="$duplicate_secondary_id"
export PMS_BACKLOG_QUEUE_ID="$queue_id"
export PMS_BACKLOG_BOOTSTRAP_PATH="$bootstrap_path"
export PMS_BACKLOG_DASHBOARD_PATH="$dashboard_path"
export PMS_BACKLOG_READY_PATH="$ready_path"
export PMS_BACKLOG_AVAILABLE_PATH="$available_path"
export PMS_BACKLOG_DUPLICATES_PATH="$duplicates_path"
export PMS_BACKLOG_MERGE_PREVIEW_PATH="$merge_preview_path"
export PMS_BACKLOG_QUEUE_PRESETS_PATH="$queue_presets_path"
export PMS_BACKLOG_QUEUE_RUN_PATH="$queue_run_path"
export PMS_BACKLOG_DAILY_PATH="$daily_path"
export PMS_BACKLOG_LINEAGE_PATH="$lineage_path"
export PMS_BACKLOG_PROJECT_REPORT_PATH="$project_report_path"
export PMS_BACKLOG_METRICS_PATH="$metrics_path"
export PMS_BACKLOG_SUMMARY_PATH="$summary_path"

py scripts/write_backlog_triage_summary.py

echo "Backlog triage flow completed."
echo "  dashboard: $dashboard_path"
echo "  duplicates: $duplicates_path"
echo "  merge preview: $merge_preview_path"
echo "  summary: $summary_path"
