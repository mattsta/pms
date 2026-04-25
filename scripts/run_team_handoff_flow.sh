#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/run_helpers.sh"

pms_setup_python_runtime "$ROOT_DIR"
pms_prepare_data_dir "$ROOT_DIR" "team-handoff"
pms_use_isolated_direct_runtime
timestamp="$(date +"%Y%m%d-%H%M%S")"

suffix="${PMS_HANDOFF_SUFFIX:-$timestamp}"
org_name="${PMS_HANDOFF_ORG:-Handoff Org $suffix}"
portfolio_name="${PMS_HANDOFF_PORTFOLIO:-Delivery Portfolio $suffix}"
program_name="${PMS_HANDOFF_PROGRAM:-Release Program $suffix}"
product_name="${PMS_HANDOFF_PRODUCT:-Platform Product $suffix}"
build_project_name="${PMS_HANDOFF_BUILD_PROJECT:-Platform API Delivery $suffix}"
release_project_name="${PMS_HANDOFF_RELEASE_PROJECT:-Release Coordination $suffix}"
build_actor="${PMS_HANDOFF_BUILD_ACTOR:-build-bot}"
release_actor="${PMS_HANDOFF_RELEASE_ACTOR:-release-bot}"
release_task_title="${PMS_HANDOFF_RELEASE_TASK_TITLE:-Prepare release notes}"

custom_field_name="${PMS_HANDOFF_CUSTOM_FIELD:-handoff_status}"
queue_name="${PMS_HANDOFF_QUEUE_NAME:-handoff-queue-$suffix}"
automation_rule_name="${PMS_HANDOFF_RULE_NAME:-handoff-auto-comment-$suffix}"

org_daily_summary_path="$PMS_DATA_DIR/team-handoff.org-daily.json"
release_daily_summary_path="$PMS_DATA_DIR/team-handoff.release-daily.json"
build_report_path="$PMS_DATA_DIR/team-handoff.build-project-report.json"
release_report_path="$PMS_DATA_DIR/team-handoff.release-project-report.json"
metrics_path="$PMS_DATA_DIR/team-handoff.metrics.csv"
history_path="$PMS_DATA_DIR/team-handoff.history.json"
queue_run_path="$PMS_DATA_DIR/team-handoff.queue-run.json"
summary_path="$PMS_DATA_DIR/team-handoff.summary.json"

echo "Running team handoff flow"
echo "  run_mode: $RUN_MODE"
echo "  data_dir: $PMS_DATA_DIR"
echo "  org: $org_name"
echo "  build_project: $build_project_name"
echo "  release_project: $release_project_name"

pms init >/dev/null
pms quickstart \
  --defaults \
  --org "$org_name" \
  --portfolio "$portfolio_name" \
  --program "$program_name" \
  --product "$product_name" \
  --project "$build_project_name" \
  --task "Implement handoff API contract" \
  --task "Validate release readiness checklist" \
  --create-plan \
  --create-rollups >/dev/null

pms project create \
  "$release_project_name" \
  --description "Cross-team release coordination board" \
  --org "$org_name" \
  --portfolio "$portfolio_name" \
  --program "$program_name" \
  --product "$product_name" >/dev/null

pms task add "$release_project_name" "$release_task_title" -p high --format json >/dev/null
pms task add "$release_project_name" "Coordinate deployment window" -p high --format json >/dev/null

org_id="$(
  pms org list -f json | PMS_EXPECTED_ORG_NAME="$org_name" py -c \
    'import json, os, sys; payload=json.load(sys.stdin); items=payload.get("items", []); expected=os.environ["PMS_EXPECTED_ORG_NAME"]; match=next((item for item in items if item.get("name")==expected), None); print(match["id"] if match else "")'
)"
if [[ -z "$org_id" ]]; then
  echo "Team handoff flow failed: could not resolve organization ID for '$org_name'." >&2
  exit 1
fi

build_project_id="$(
  pms project list -f json | PMS_EXPECTED_PROJECT_NAME="$build_project_name" py -c \
    'import json, os, sys; payload=json.load(sys.stdin); items=payload.get("items", []); expected=os.environ["PMS_EXPECTED_PROJECT_NAME"]; match=next((item for item in items if item.get("name")==expected), None); print(match["id"] if match else "")'
)"
release_project_id="$(
  pms project list -f json | PMS_EXPECTED_PROJECT_NAME="$release_project_name" py -c \
    'import json, os, sys; payload=json.load(sys.stdin); items=payload.get("items", []); expected=os.environ["PMS_EXPECTED_PROJECT_NAME"]; match=next((item for item in items if item.get("name")==expected), None); print(match["id"] if match else "")'
)"
if [[ -z "$build_project_id" || -z "$release_project_id" ]]; then
  echo "Team handoff flow failed: could not resolve project IDs." >&2
  exit 1
fi

build_ready_json="$(pms task ready --project "$build_project_name" --format json)"
build_task_title="$(
  printf '%s' "$build_ready_json" | py -c \
    'import json,sys; payload=json.load(sys.stdin); items=payload if isinstance(payload, list) else payload.get("items", []) if isinstance(payload, dict) else []; print(items[0]["title"] if items else "")'
)"
if [[ -z "$build_task_title" ]]; then
  build_task_title="$(
    pms task list --project "$build_project_name" --format json | py -c \
      'import json,sys; payload=json.load(sys.stdin); items=payload.get("items", []); print(items[0]["title"] if items else "")'
  )"
fi
if [[ -z "$build_task_title" ]]; then
  echo "Team handoff flow failed: no build task available for lifecycle flow." >&2
  exit 1
fi

pms task start "$build_task_title" --project "$build_project_name" --by "$build_actor" --format json >/dev/null
pms task progress "$build_task_title" 80 "Build handoff complete and ready for release" --project "$build_project_name" --by "$build_actor" --format json >/dev/null
pms task complete "$build_task_title" --project "$build_project_name" --by "$build_actor" --format json >/dev/null

build_task_id="$(
  pms task list --project "$build_project_name" --format json | PMS_EXPECTED_TASK_TITLE="$build_task_title" py -c \
    'import json, os, sys; payload=json.load(sys.stdin); items=payload.get("items", []); expected=os.environ["PMS_EXPECTED_TASK_TITLE"]; match=next((item for item in items if item.get("title")==expected), None); print(match["id"] if match else "")'
)"
if [[ -z "$build_task_id" ]]; then
  echo "Team handoff flow failed: could not resolve build task ID for '$build_task_title'." >&2
  exit 1
fi

pms task start "$release_task_title" --project "$release_project_name" --by "$release_actor" --format json >/dev/null
pms task progress "$release_task_title" 40 "Release prep started from upstream handoff" --project "$release_project_name" --by "$release_actor" --format json >/dev/null

release_task_id="$(
  pms task list --project "$release_project_name" --format json | PMS_EXPECTED_TASK_TITLE="$release_task_title" py -c \
    'import json, os, sys; payload=json.load(sys.stdin); items=payload.get("items", []); expected=os.environ["PMS_EXPECTED_TASK_TITLE"]; match=next((item for item in items if item.get("title")==expected), None); print(match["id"] if match else "")'
)"
if [[ -z "$release_task_id" ]]; then
  echo "Team handoff flow failed: could not resolve release task ID for '$release_task_title'." >&2
  exit 1
fi

pms comment add task "$build_task_id" "Handoff complete. Release team can proceed." --by "$build_actor" --mention "$release_actor" --watch >/dev/null
pms watcher add task "$build_task_id" "$release_actor" >/dev/null
pms comment list task "$build_task_id" --format json >/dev/null
pms watcher list task "$build_task_id" --format json >/dev/null

custom_field_id="$(
  pms custom-field list --entity-type task --format json | PMS_EXPECTED_FIELD_NAME="$custom_field_name" py -c \
    'import json, os, sys; payload=json.load(sys.stdin); items=payload.get("items", []); expected=os.environ["PMS_EXPECTED_FIELD_NAME"]; match=next((item for item in items if item.get("name")==expected), None); print(match["id"] if match else "")'
)"
if [[ -z "$custom_field_id" ]]; then
  pms custom-field create \
    "$custom_field_name" \
    --entity-type task \
    --type enum \
    --option queued \
    --option accepted \
    --option released \
    -d "Tracks cross-team handoff state" >/dev/null
  custom_field_id="$(
    pms custom-field list --entity-type task --format json | PMS_EXPECTED_FIELD_NAME="$custom_field_name" py -c \
      'import json, os, sys; payload=json.load(sys.stdin); items=payload.get("items", []); expected=os.environ["PMS_EXPECTED_FIELD_NAME"]; match=next((item for item in items if item.get("name")==expected), None); print(match["id"] if match else "")'
  )"
fi
if [[ -z "$custom_field_id" ]]; then
  echo "Team handoff flow failed: could not resolve custom field ID for '$custom_field_name'." >&2
  exit 1
fi

pms custom-field value set \
  "$custom_field_id" \
  --entity-type task \
  --entity-id "$build_task_id" \
  --value accepted \
  --created-by "$build_actor" >/dev/null
pms custom-field value set \
  "$custom_field_id" \
  --entity-type task \
  --entity-id "$release_task_id" \
  --value queued \
  --created-by "$release_actor" >/dev/null

automation_rule_id="$(
  pms automation rule list --format json | PMS_EXPECTED_RULE_NAME="$automation_rule_name" py -c \
    'import json, os, sys; payload=json.load(sys.stdin); items=payload.get("items", []); expected=os.environ["PMS_EXPECTED_RULE_NAME"]; match=next((item for item in items if item.get("name")==expected), None); print(match["id"] if match else "")'
)"
if [[ -z "$automation_rule_id" ]]; then
  pms automation rule create \
    "$automation_rule_name" \
    "task.completed" \
    "add_comment" \
    --description "Annotate completion events for team handoff tracking" \
    --aggregate-type task \
    --aggregate-id "$build_task_id" \
    --action-payload-json "{\"body\":\"Automation: build task completed\",\"created_by\":\"$release_actor\"}" >/dev/null
  automation_rule_id="$(
    pms automation rule list --format json | PMS_EXPECTED_RULE_NAME="$automation_rule_name" py -c \
      'import json, os, sys; payload=json.load(sys.stdin); items=payload.get("items", []); expected=os.environ["PMS_EXPECTED_RULE_NAME"]; match=next((item for item in items if item.get("name")==expected), None); print(match["id"] if match else "")'
  )"
fi
if [[ -z "$automation_rule_id" ]]; then
  echo "Team handoff flow failed: could not resolve automation rule ID for '$automation_rule_name'." >&2
  exit 1
fi

queue_id="$(
  pms queue list --format json | PMS_EXPECTED_QUEUE_NAME="$queue_name" py -c \
    'import json, os, sys; payload=json.load(sys.stdin); items=payload.get("items", []); expected=os.environ["PMS_EXPECTED_QUEUE_NAME"]; match=next((item for item in items if item.get("name")==expected), None); print(match["id"] if match else "")'
)"
if [[ -z "$queue_id" ]]; then
  pms queue create \
    "$queue_name" \
    --scope-type organization \
    --scope "$org_name" \
    --description "Cross-team handoff queue for release readiness" \
    --filters '{"statuses":["todo","in_progress"]}' >/dev/null
  queue_id="$(
    pms queue list --format json | PMS_EXPECTED_QUEUE_NAME="$queue_name" py -c \
      'import json, os, sys; payload=json.load(sys.stdin); items=payload.get("items", []); expected=os.environ["PMS_EXPECTED_QUEUE_NAME"]; match=next((item for item in items if item.get("name")==expected), None); print(match["id"] if match else "")'
  )"
fi
if [[ -z "$queue_id" ]]; then
  echo "Team handoff flow failed: could not resolve queue ID for '$queue_name'." >&2
  exit 1
fi
pms queue run "$queue_id" --format json >"$queue_run_path"

pms work daily \
  --scope-type organization \
  --scope "$org_name" \
  --format json \
  --no-attach \
  --export "$org_daily_summary_path" >/dev/null
pms work daily \
  --scope-type project \
  --scope "$release_project_name" \
  --format json \
  --no-attach \
  --export "$release_daily_summary_path" >/dev/null

pms report project "$build_project_id" --format json -o "$build_report_path" >/dev/null
pms report project "$release_project_id" --format json -o "$release_report_path" >/dev/null
pms report metrics --format csv -o "$metrics_path" >/dev/null
pms report history --days 30 --format json -o "$history_path" >/dev/null

[ -s "$org_daily_summary_path" ]
[ -s "$release_daily_summary_path" ]
[ -s "$build_report_path" ]
[ -s "$release_report_path" ]
[ -s "$metrics_path" ]
[ -s "$history_path" ]
[ -s "$queue_run_path" ]

export PMS_HANDOFF_ORG_NAME="$org_name"
export PMS_HANDOFF_ORG_ID="$org_id"
export PMS_HANDOFF_BUILD_PROJECT_NAME="$build_project_name"
export PMS_HANDOFF_BUILD_PROJECT_ID="$build_project_id"
export PMS_HANDOFF_RELEASE_PROJECT_NAME="$release_project_name"
export PMS_HANDOFF_RELEASE_PROJECT_ID="$release_project_id"
export PMS_HANDOFF_BUILD_TASK_ID="$build_task_id"
export PMS_HANDOFF_RELEASE_TASK_ID="$release_task_id"
export PMS_HANDOFF_CUSTOM_FIELD_ID="$custom_field_id"
export PMS_HANDOFF_AUTOMATION_RULE_ID="$automation_rule_id"
export PMS_HANDOFF_QUEUE_ID="$queue_id"
export PMS_HANDOFF_ORG_DAILY_PATH="$org_daily_summary_path"
export PMS_HANDOFF_RELEASE_DAILY_PATH="$release_daily_summary_path"
export PMS_HANDOFF_BUILD_REPORT_PATH="$build_report_path"
export PMS_HANDOFF_RELEASE_REPORT_PATH="$release_report_path"
export PMS_HANDOFF_METRICS_PATH="$metrics_path"
export PMS_HANDOFF_HISTORY_PATH="$history_path"
export PMS_HANDOFF_QUEUE_RUN_PATH="$queue_run_path"

py - <<'PY'
import json
import os
from pathlib import Path

from pms.utils.atomic_files import write_json_atomic

summary_path = Path(os.environ["PMS_DATA_DIR"]) / "team-handoff.summary.json"
data = {
    "organization": {
        "name": os.environ["PMS_HANDOFF_ORG_NAME"],
        "id": os.environ["PMS_HANDOFF_ORG_ID"],
    },
    "projects": {
        "build": {
            "name": os.environ["PMS_HANDOFF_BUILD_PROJECT_NAME"],
            "id": os.environ["PMS_HANDOFF_BUILD_PROJECT_ID"],
        },
        "release": {
            "name": os.environ["PMS_HANDOFF_RELEASE_PROJECT_NAME"],
            "id": os.environ["PMS_HANDOFF_RELEASE_PROJECT_ID"],
        },
    },
    "tasks": {
        "build_task_id": os.environ["PMS_HANDOFF_BUILD_TASK_ID"],
        "release_task_id": os.environ["PMS_HANDOFF_RELEASE_TASK_ID"],
    },
    "extension_ids": {
        "custom_field_id": os.environ["PMS_HANDOFF_CUSTOM_FIELD_ID"],
        "automation_rule_id": os.environ["PMS_HANDOFF_AUTOMATION_RULE_ID"],
        "queue_id": os.environ["PMS_HANDOFF_QUEUE_ID"],
    },
    "artifacts": {
        "organization_daily_summary": os.environ["PMS_HANDOFF_ORG_DAILY_PATH"],
        "release_project_daily_summary": os.environ["PMS_HANDOFF_RELEASE_DAILY_PATH"],
        "build_project_report": os.environ["PMS_HANDOFF_BUILD_REPORT_PATH"],
        "release_project_report": os.environ["PMS_HANDOFF_RELEASE_REPORT_PATH"],
        "metrics_csv": os.environ["PMS_HANDOFF_METRICS_PATH"],
        "history_json": os.environ["PMS_HANDOFF_HISTORY_PATH"],
        "queue_run_json": os.environ["PMS_HANDOFF_QUEUE_RUN_PATH"],
    },
}
write_json_atomic(summary_path, data)
PY

echo "Team handoff flow completed successfully."
echo "  org_id: $org_id"
echo "  build_project_id: $build_project_id"
echo "  release_project_id: $release_project_id"
echo "  build_task_id: $build_task_id"
echo "  release_task_id: $release_task_id"
echo "  custom_field_id: $custom_field_id"
echo "  automation_rule_id: $automation_rule_id"
echo "  queue_id: $queue_id"
echo "  summary: $summary_path"
