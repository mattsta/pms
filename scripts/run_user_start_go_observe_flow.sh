#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/run_helpers.sh"

pms_setup_python_runtime "$ROOT_DIR"
pms_prepare_data_dir "$ROOT_DIR" "user-start-go"
pms_use_isolated_direct_runtime
timestamp="$(date +"%Y%m%d-%H%M%S")"

suffix="${PMS_USER_FLOW_SUFFIX:-$timestamp}"
org_name="${PMS_USER_FLOW_ORG:-User Flow Org $suffix}"
portfolio_name="${PMS_USER_FLOW_PORTFOLIO:-User Flow Portfolio $suffix}"
program_name="${PMS_USER_FLOW_PROGRAM:-User Flow Program $suffix}"
product_name="${PMS_USER_FLOW_PRODUCT:-User Flow Product $suffix}"
project_name="${PMS_USER_FLOW_PROJECT:-User Flow Project $suffix}"
actor_name="${PMS_USER_FLOW_ACTOR:-user-flow-bot}"

guide_path="$PMS_DATA_DIR/user-start.guide.json"
ready_path="$PMS_DATA_DIR/user-start.ready.json"
dashboard_path="$PMS_DATA_DIR/user-start.dashboard.json"
daily_path="$PMS_DATA_DIR/user-start.daily.json"
summary_path="$PMS_DATA_DIR/user-start.summary.json"

echo "Running user start -> go -> observe flow"
echo "  run_mode: $RUN_MODE"
echo "  data_dir: $PMS_DATA_DIR"
echo "  project: $project_name"

# Start: show discoverability and next actions.
pms init >/dev/null
pms start --format json > "$guide_path"
[ -s "$guide_path" ]

# Go: create practical workspace data and execute a task lifecycle.
pms quickstart \
  --defaults \
  --org "$org_name" \
  --portfolio "$portfolio_name" \
  --program "$program_name" \
  --product "$product_name" \
  --project "$project_name" \
  --task "Capture baseline requirements" \
  --task "Execute first delivery slice" \
  --task "Review observability outputs" \
  --create-plan \
  --create-rollups >/dev/null

pms task ready --project "$project_name" --format json > "$ready_path"
[ -s "$ready_path" ]

task_title="$(
  PMS_READY_PATH="$ready_path" py -c \
    'import json, os; payload=json.loads(open(os.environ["PMS_READY_PATH"]).read()); items=payload if isinstance(payload, list) else payload.get("items", []) if isinstance(payload, dict) else []; print(items[0]["title"] if items else "")'
)"
if [[ -z "$task_title" ]]; then
  task_title="$(
    pms task list --project "$project_name" --format json | py -c \
      'import json,sys; payload=json.load(sys.stdin); items=payload.get("items", []); print(items[0]["title"] if items else "")'
  )"
fi
if [[ -z "$task_title" ]]; then
  echo "User flow failed: no task available in $project_name." >&2
  exit 1
fi

pms task start "$task_title" --project "$project_name" --by "$actor_name" --format json >/dev/null
pms task progress "$task_title" 40 "Initial execution underway" --project "$project_name" --by "$actor_name" --format json >/dev/null

# Observe: dashboard + daily digest with exported artifact.
pms dashboard --format json > "$dashboard_path"
[ -s "$dashboard_path" ]

pms work daily \
  --scope-type project \
  --scope "$project_name" \
  --include-timeline \
  --include-history \
  --format json \
  --no-attach \
  --export "$daily_path" >/dev/null
[ -s "$daily_path" ]

project_id="$(
  pms project list -f json | PMS_EXPECTED_PROJECT_NAME="$project_name" py -c \
    'import json, os, sys; payload=json.load(sys.stdin); expected=os.environ["PMS_EXPECTED_PROJECT_NAME"]; items=payload.get("items", []); match=next((item for item in items if item.get("name")==expected), None); print(match["id"] if match else "")'
)"
if [[ -z "$project_id" ]]; then
  echo "User flow failed: project '$project_name' not found." >&2
  exit 1
fi

task_id="$(
  pms task list --project "$project_name" --format json | PMS_EXPECTED_TASK_TITLE="$task_title" py -c \
    'import json, os, sys; payload=json.load(sys.stdin); expected=os.environ["PMS_EXPECTED_TASK_TITLE"]; items=payload.get("items", []); match=next((item for item in items if item.get("title")==expected), None); print(match["id"] if match else "")'
)"
if [[ -z "$task_id" ]]; then
  echo "User flow failed: task '$task_title' not found." >&2
  exit 1
fi

export PMS_USER_FLOW_GUIDE_PATH="$guide_path"
export PMS_USER_FLOW_READY_PATH="$ready_path"
export PMS_USER_FLOW_DASHBOARD_PATH="$dashboard_path"
export PMS_USER_FLOW_DAILY_PATH="$daily_path"
export PMS_USER_FLOW_SUMMARY_PATH="$summary_path"
export PMS_USER_FLOW_PROJECT_NAME="$project_name"
export PMS_USER_FLOW_PROJECT_ID="$project_id"
export PMS_USER_FLOW_TASK_TITLE="$task_title"
export PMS_USER_FLOW_TASK_ID="$task_id"

py - <<'PY'
import json
import os
from pathlib import Path

from pms.utils.atomic_files import write_json_atomic

guide = json.loads(Path(os.environ["PMS_USER_FLOW_GUIDE_PATH"]).read_text())
ready = json.loads(Path(os.environ["PMS_USER_FLOW_READY_PATH"]).read_text())
dashboard = json.loads(Path(os.environ["PMS_USER_FLOW_DASHBOARD_PATH"]).read_text())
daily = json.loads(Path(os.environ["PMS_USER_FLOW_DAILY_PATH"]).read_text())
ready_first = (
    ready[0] if isinstance(ready, list) and ready and isinstance(ready[0], dict) else {}
)

summary = {
    "project": {
        "name": os.environ["PMS_USER_FLOW_PROJECT_NAME"],
        "id": os.environ["PMS_USER_FLOW_PROJECT_ID"],
    },
    "task": {
        "title": os.environ["PMS_USER_FLOW_TASK_TITLE"],
        "id": os.environ["PMS_USER_FLOW_TASK_ID"],
    },
    "artifacts": {
        "start_guide": os.environ["PMS_USER_FLOW_GUIDE_PATH"],
        "ready_tasks": os.environ["PMS_USER_FLOW_READY_PATH"],
        "dashboard": os.environ["PMS_USER_FLOW_DASHBOARD_PATH"],
        "daily_summary": os.environ["PMS_USER_FLOW_DAILY_PATH"],
    },
    "next_steps": {
        "guide": guide.get("next_steps", []),
        "ready": ready_first.get("next_steps", []),
        "dashboard": dashboard.get("next_steps", []),
        "daily": daily.get("next_steps", []),
    },
    "links": {
        "guide": guide.get("links", {}),
        "ready": ready_first.get("links", {}),
        "dashboard": dashboard.get("links", {}),
        "daily": daily.get("links", {}),
    },
}
write_json_atomic(Path(os.environ["PMS_USER_FLOW_SUMMARY_PATH"]), summary)
PY

echo "User start -> go -> observe flow completed."
echo "  guide: $guide_path"
echo "  ready: $ready_path"
echo "  dashboard: $dashboard_path"
echo "  daily: $daily_path"
echo "  summary: $summary_path"
