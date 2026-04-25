#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/run_helpers.sh"

pms_setup_python_runtime "$ROOT_DIR"
pms_prepare_data_dir "$ROOT_DIR" "dropin-grow"
pms_use_isolated_direct_runtime
timestamp="$(date +"%Y%m%d-%H%M%S")"

suffix="${PMS_GROWTH_SUFFIX:-$timestamp}"
org_name="${PMS_GROWTH_ORG:-Growth Org $suffix}"
portfolio_name="${PMS_GROWTH_PORTFOLIO:-Growth Portfolio $suffix}"
program_name="${PMS_GROWTH_PROGRAM:-Growth Program $suffix}"
product_name="${PMS_GROWTH_PRODUCT:-Growth Product $suffix}"
project_name="${PMS_GROWTH_PROJECT:-Growth Project $suffix}"
actor_name="${PMS_GROWTH_ACTOR:-growth-bot}"

goal_name="${PMS_GROWTH_GOAL:-Ship $project_name}"
objective_name="${PMS_GROWTH_OBJECTIVE:-Deliver $project_name objective}"
criterion_text="${PMS_GROWTH_CRITERION:-Core flow shipped with evidence}"
extra_task_title="${PMS_GROWTH_EXTRA_TASK:-Harden release checklist}"

custom_field_name="${PMS_GROWTH_CUSTOM_FIELD:-risk_level}"
queue_name="${PMS_GROWTH_QUEUE_NAME:-growth-ready-$suffix}"
automation_rule_name="${PMS_GROWTH_RULE_NAME:-auto-comment-$suffix}"

plugin_template="${PMS_GROWTH_PLUGIN_TEMPLATE:-basic}"
plugin_name="${PMS_GROWTH_PLUGIN_NAME:-growth-plugin-$suffix}"
run_plugin_path="${PMS_GROWTH_RUN_PLUGIN:-1}"
run_loop_path="${PMS_GROWTH_RUN_LOOP_SETUP:-1}"

daily_summary_path="$PMS_DATA_DIR/dropin-grow.daily.json"
project_report_path="$PMS_DATA_DIR/dropin-grow.project-report.json"
summary_path="$PMS_DATA_DIR/dropin-grow.summary.json"
loop_dir="$PMS_DATA_DIR/dropin-grow.loop"
plugin_dir="$PMS_DATA_DIR/dropin-grow.plugins"

echo "Running drop-in -> start -> go -> extend -> grow scenario"
echo "  run_mode: $RUN_MODE"
echo "  data_dir: $PMS_DATA_DIR"
echo "  project: $project_name"
echo "  plugin_path: $run_plugin_path"
echo "  loop_setup_path: $run_loop_path"

# Drop in: one-shot bootstrap.
pms init >/dev/null
pms quickstart \
  --defaults \
  --org "$org_name" \
  --portfolio "$portfolio_name" \
  --program "$program_name" \
  --product "$product_name" \
  --project "$project_name" \
  --task "Define delivery scope" \
  --task "Ship first increment" \
  --create-plan \
  --create-rollups >/dev/null

project_id="$(
  pms project list -f json | PMS_EXPECTED_PROJECT_NAME="$project_name" py -c \
    'import json, os, sys; payload=json.load(sys.stdin); expected=os.environ["PMS_EXPECTED_PROJECT_NAME"]; items=payload.get("items", []); match=next((item for item in items if item.get("name")==expected), None); print(match["id"] if match else "")'
)"
if [[ -z "$project_id" ]]; then
  echo "Drop-in scenario failed: project '$project_name' not found." >&2
  exit 1
fi

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
  echo "Drop-in scenario failed: no task available for execution." >&2
  exit 1
fi

# Start -> go: execute a real task lifecycle.
pms task start "$task_title" --project "$project_name" --by "$actor_name" --format json >/dev/null
pms task progress "$task_title" 60 "Initial increment delivered" --project "$project_name" --by "$actor_name" --format json >/dev/null
pms task complete "$task_title" --project "$project_name" --by "$actor_name" --format json >/dev/null

task_id="$(
  pms task list --project "$project_name" --format json | PMS_EXPECTED_TASK_TITLE="$task_title" py -c \
    'import json, os, sys; payload=json.load(sys.stdin); expected=os.environ["PMS_EXPECTED_TASK_TITLE"]; items=payload.get("items", []); match=next((item for item in items if item.get("title")==expected), None); print(match["id"] if match else "")'
)"
if [[ -z "$task_id" ]]; then
  echo "Drop-in scenario failed: could not resolve task ID for '$task_title'." >&2
  exit 1
fi

# Extend: custom fields + comments + watchers + automation + queue.
pms custom-field create \
  "$custom_field_name" \
  --entity-type task \
  --type enum \
  --option low \
  --option medium \
  --option high \
  -d "Execution risk level" >/dev/null

field_id="$(
  pms custom-field list --entity-type task --format json | PMS_EXPECTED_FIELD_NAME="$custom_field_name" py -c \
    'import json, os, sys; payload=json.load(sys.stdin); expected=os.environ["PMS_EXPECTED_FIELD_NAME"]; items=payload.get("items", []); match=next((item for item in items if item.get("name")==expected), None); print(match["id"] if match else "")'
)"
if [[ -z "$field_id" ]]; then
  echo "Drop-in scenario failed: could not resolve custom field ID for '$custom_field_name'." >&2
  exit 1
fi

pms custom-field value set \
  "$field_id" \
  --entity-type task \
  --entity-id "$task_id" \
  --value medium \
  --created-by "$actor_name" >/dev/null
pms custom-field value list --entity-type task --entity-id "$task_id" --format json >/dev/null

pms comment add task "$task_id" "Tracking extension path for $project_name" --by "$actor_name" --watch >/dev/null
pms comment list task "$task_id" --format json >/dev/null
pms watcher add task "$task_id" "$actor_name" >/dev/null
pms watcher list task "$task_id" --format json >/dev/null

pms automation rule create \
  "$automation_rule_name" \
  "task.completed" \
  "add_comment" \
  --description "Auto-comment on completion in growth scenario" \
  --action-payload-json "{\"body\":\"Automation: task completed\",\"created_by\":\"$actor_name\"}" >/dev/null

rule_id="$(
  pms automation rule list --format json | PMS_EXPECTED_RULE_NAME="$automation_rule_name" py -c \
    'import json, os, sys; payload=json.load(sys.stdin); items=payload.get("items", []); expected=os.environ["PMS_EXPECTED_RULE_NAME"]; match=next((item for item in items if item.get("name")==expected), None); print(match["id"] if match else "")'
)"
if [[ -z "$rule_id" ]]; then
  echo "Drop-in scenario failed: could not resolve automation rule ID for '$automation_rule_name'." >&2
  exit 1
fi

pms queue create \
  "$queue_name" \
  --scope-type project \
  --scope "$project_name" \
  --description "Growth scenario queue" \
  --filters '{"statuses":["todo","in_progress"]}' >/dev/null

queue_id="$(
  pms queue list --format json | PMS_EXPECTED_QUEUE_NAME="$queue_name" py -c \
    'import json, os, sys; payload=json.load(sys.stdin); items=payload.get("items", []); expected=os.environ["PMS_EXPECTED_QUEUE_NAME"]; match=next((item for item in items if item.get("name")==expected), None); print(match["id"] if match else "")'
)"
if [[ -z "$queue_id" ]]; then
  echo "Drop-in scenario failed: could not resolve queue ID for '$queue_name'." >&2
  exit 1
fi
pms queue run "$queue_id" --format json >/dev/null

# Grow: reporting, snapshots, loop setup, and plugin extension path.
pms work daily \
  --scope-type project \
  --scope "$project_name" \
  --format json \
  --no-attach \
  --export "$daily_summary_path" >/dev/null

pms report project "$project_id" --format json -o "$project_report_path" >/dev/null

if [[ "$run_plugin_path" == "1" ]]; then
  mkdir -p "$plugin_dir"
  pms plugin new "$plugin_name" --template "$plugin_template" -o "$plugin_dir" >/dev/null
  pms plugin validate "$plugin_dir/$plugin_name" >/dev/null
  pms plugin test "$plugin_dir/$plugin_name" --dry-run >/dev/null
  pms plugin discover "$plugin_dir" >/dev/null
  pms plugin list --format json >/dev/null
fi

if [[ "$run_loop_path" == "1" ]]; then
  mkdir -p "$loop_dir"
  (
    cd "$loop_dir"
    pms loop setup \
      --defaults \
      --project "$project_name" \
      --goal "$goal_name" \
      --objective "$objective_name" \
      --criterion "$criterion_text" \
      --task "$extra_task_title" \
      --no-run \
      --config pms-loop.yml \
      --prompt-file PROMPT.md >/dev/null
  )
fi

[ -s "$daily_summary_path" ]
[ -s "$project_report_path" ]
if [[ "$run_loop_path" == "1" ]]; then
  [ -s "$loop_dir/pms-loop.yml" ]
  [ -s "$loop_dir/PROMPT.md" ]
fi

export PMS_GROWTH_PROJECT_NAME_RESOLVED="$project_name"
export PMS_GROWTH_PROJECT_ID_RESOLVED="$project_id"
export PMS_GROWTH_TASK_ID_RESOLVED="$task_id"
export PMS_GROWTH_CUSTOM_FIELD_ID_RESOLVED="$field_id"
export PMS_GROWTH_AUTOMATION_RULE_ID_RESOLVED="$rule_id"
export PMS_GROWTH_QUEUE_ID_RESOLVED="$queue_id"
export PMS_GROWTH_SUMMARY_PATH="$summary_path"
export PMS_GROWTH_DAILY_SUMMARY_PATH="$daily_summary_path"
export PMS_GROWTH_PROJECT_REPORT_PATH="$project_report_path"
export PMS_GROWTH_LOOP_DIR="$loop_dir"
export PMS_GROWTH_PLUGIN_DIR="$plugin_dir/$plugin_name"
export PMS_GROWTH_RUN_PLUGIN="$run_plugin_path"
export PMS_GROWTH_RUN_LOOP_SETUP="$run_loop_path"

py - <<'PY'
import json
import os
from pathlib import Path

from pms.utils.atomic_files import write_json_atomic

summary_path = Path(os.environ["PMS_DATA_DIR"]) / "dropin-grow.summary.json"
loop_enabled = os.environ.get("PMS_GROWTH_RUN_LOOP_SETUP", "1") == "1"
plugin_enabled = os.environ.get("PMS_GROWTH_RUN_PLUGIN", "1") == "1"
data = {
    "project_name": os.environ["PMS_GROWTH_PROJECT_NAME_RESOLVED"],
    "project_id": os.environ["PMS_GROWTH_PROJECT_ID_RESOLVED"],
    "task_id": os.environ["PMS_GROWTH_TASK_ID_RESOLVED"],
    "custom_field_id": os.environ["PMS_GROWTH_CUSTOM_FIELD_ID_RESOLVED"],
    "automation_rule_id": os.environ["PMS_GROWTH_AUTOMATION_RULE_ID_RESOLVED"],
    "queue_id": os.environ["PMS_GROWTH_QUEUE_ID_RESOLVED"],
    "artifacts": {
        "daily_summary": os.environ["PMS_GROWTH_DAILY_SUMMARY_PATH"],
        "project_report": os.environ["PMS_GROWTH_PROJECT_REPORT_PATH"],
        "loop_config": str(Path(os.environ["PMS_GROWTH_LOOP_DIR"]) / "pms-loop.yml")
        if loop_enabled
        else None,
        "loop_prompt": str(Path(os.environ["PMS_GROWTH_LOOP_DIR"]) / "PROMPT.md")
        if loop_enabled
        else None,
        "plugin_path": os.environ["PMS_GROWTH_PLUGIN_DIR"] if plugin_enabled else None,
    },
}
write_json_atomic(summary_path, data)
PY

echo "Drop-in scenario completed successfully."
echo "  project_id: $project_id"
echo "  task_id: $task_id"
echo "  custom_field_id: $field_id"
echo "  automation_rule_id: $rule_id"
echo "  queue_id: $queue_id"
echo "  daily_summary: $daily_summary_path"
echo "  project_report: $project_report_path"
if [[ "$run_loop_path" == "1" ]]; then
  echo "  loop_config: $loop_dir/pms-loop.yml"
  echo "  loop_prompt: $loop_dir/PROMPT.md"
fi
if [[ "$run_plugin_path" == "1" ]]; then
  echo "  plugin_dir: $plugin_dir/$plugin_name"
fi
echo "  summary: $summary_path"
