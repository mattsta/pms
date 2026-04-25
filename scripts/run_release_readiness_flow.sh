#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/run_helpers.sh"

pms_setup_python_runtime "$ROOT_DIR"
pms_prepare_data_dir "$ROOT_DIR" "release-readiness"
pms_use_isolated_direct_runtime
timestamp="$(date +"%Y%m%d-%H%M%S")"

suffix="${PMS_RELEASE_SUFFIX:-$timestamp}"
org_name="${PMS_RELEASE_ORG:-Release Org $suffix}"
portfolio_name="${PMS_RELEASE_PORTFOLIO:-Launch Portfolio $suffix}"
program_name="${PMS_RELEASE_PROGRAM:-Launch Program $suffix}"
product_name="${PMS_RELEASE_PRODUCT:-Payments Platform $suffix}"
project_name="${PMS_RELEASE_PROJECT:-Release Readiness $suffix}"
actor_name="${PMS_RELEASE_ACTOR:-release-manager}"
smoke_server_id="${PMS_RELEASE_TEST_SERVER:-local-smoke}"
queue_name="${PMS_RELEASE_QUEUE_NAME:-release-ready-$suffix}"
goal_name="${PMS_RELEASE_GOAL:-Launch $project_name}"
objective_name="${PMS_RELEASE_OBJECTIVE:-Clear release gate for $project_name}"
release_status_field="${PMS_RELEASE_STATUS_FIELD:-release_status}"
release_rule_name="${PMS_RELEASE_RULE_NAME:-release-ready-comment-$suffix}"

release_notes_task="${PMS_RELEASE_NOTES_TASK:-Finalize release notes}"
smoke_task="${PMS_RELEASE_SMOKE_TASK:-Run final smoke validation}"
approval_task="${PMS_RELEASE_APPROVAL_TASK:-Approve go/no-go decision}"

bootstrap_path="$PMS_DATA_DIR/release-readiness.bootstrap.json"
start_path="$PMS_DATA_DIR/release-readiness.start.json"
dashboard_path="$PMS_DATA_DIR/release-readiness.dashboard.json"
daily_path="$PMS_DATA_DIR/release-readiness.daily.json"
project_report_path="$PMS_DATA_DIR/release-readiness.project-report.json"
metrics_path="$PMS_DATA_DIR/release-readiness.metrics.csv"
queue_run_path="$PMS_DATA_DIR/release-readiness.queue-run.json"
test_server_path="$PMS_DATA_DIR/release-readiness.test-server.json"
test_record_path="$PMS_DATA_DIR/release-readiness.test-record.json"
test_show_path="$PMS_DATA_DIR/release-readiness.test-show.json"
summary_path="$PMS_DATA_DIR/release-readiness.summary.json"

echo "Running release-readiness flow"
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
  --task "$release_notes_task" \
  --task "$smoke_task" \
  --task "$approval_task" \
  --create-plan \
  --create-rollups \
  --format json >"$bootstrap_path"

pms start --format json >"$start_path"
pms dashboard --format json >"$dashboard_path"

project_id="$(
  PMS_BOOTSTRAP_PATH="$bootstrap_path" py -c \
    'import json, os, pathlib; data=json.loads(pathlib.Path(os.environ["PMS_BOOTSTRAP_PATH"]).read_text()); print(data["artifacts_created"]["project"]["id"])'
)"
plan_id="$(
  PMS_BOOTSTRAP_PATH="$bootstrap_path" py -c \
    'import json, os, pathlib; data=json.loads(pathlib.Path(os.environ["PMS_BOOTSTRAP_PATH"]).read_text()); plan=data["artifacts_created"].get("plan"); print(plan["id"] if isinstance(plan, dict) else "")'
)"
if [[ -z "$project_id" || -z "$plan_id" ]]; then
  echo "Release readiness flow failed: bootstrap artifacts missing project or plan IDs." >&2
  exit 1
fi

notes_task_id="$(
  pms task list --project "$project_name" --format json | PMS_EXPECTED_TASK="$release_notes_task" py -c \
    'import json, os, sys; data=json.load(sys.stdin); match=next((item for item in data.get("items", []) if item.get("title")==os.environ["PMS_EXPECTED_TASK"]), None); print(match["id"] if match else "")'
)"
smoke_task_id="$(
  pms task list --project "$project_name" --format json | PMS_EXPECTED_TASK="$smoke_task" py -c \
    'import json, os, sys; data=json.load(sys.stdin); match=next((item for item in data.get("items", []) if item.get("title")==os.environ["PMS_EXPECTED_TASK"]), None); print(match["id"] if match else "")'
)"
approval_task_id="$(
  pms task list --project "$project_name" --format json | PMS_EXPECTED_TASK="$approval_task" py -c \
    'import json, os, sys; data=json.load(sys.stdin); match=next((item for item in data.get("items", []) if item.get("title")==os.environ["PMS_EXPECTED_TASK"]), None); print(match["id"] if match else "")'
)"
if [[ -z "$notes_task_id" || -z "$smoke_task_id" || -z "$approval_task_id" ]]; then
  echo "Release readiness flow failed: could not resolve release task IDs." >&2
  exit 1
fi

pms goal create "$goal_name" --project "$project_name" --owner "$actor_name" >/dev/null
goal_id="$(
  pms goal list --project "$project_name" --format json | PMS_EXPECTED_GOAL="$goal_name" py -c \
    'import json, os, sys; data=json.load(sys.stdin); match=next((item for item in data.get("items", []) if item.get("name")==os.environ["PMS_EXPECTED_GOAL"]), None); print(match["id"] if match else "")'
)"
if [[ -z "$goal_id" ]]; then
  echo "Release readiness flow failed: could not resolve goal ID." >&2
  exit 1
fi

pms objective create "$objective_name" --goal "$goal_name" >/dev/null
objective_id="$(
  pms objective list --goal "$goal_name" --format json | PMS_EXPECTED_OBJECTIVE="$objective_name" py -c \
    'import json, os, sys; data=json.load(sys.stdin); match=next((item for item in data.get("items", []) if item.get("name")==os.environ["PMS_EXPECTED_OBJECTIVE"]), None); print(match["id"] if match else "")'
)"
if [[ -z "$objective_id" ]]; then
  echo "Release readiness flow failed: could not resolve objective ID." >&2
  exit 1
fi

pms task start "$release_notes_task" --project "$project_name" --by "$actor_name" --format json >/dev/null
pms task progress "$release_notes_task" 100 "Release notes locked for launch" --project "$project_name" --by "$actor_name" --format json >/dev/null
pms task complete "$release_notes_task" --project "$project_name" --by "$actor_name" --format json >/dev/null

pms task start "$smoke_task" --project "$project_name" --by "$actor_name" --format json >/dev/null
pms task progress "$smoke_task" 90 "Smoke validation completed; awaiting recorded result" --project "$project_name" --by "$actor_name" --format json >/dev/null

pms test server ensure-local --project "$project_name" --format json >"$test_server_path"
smoke_server_id="$(
  PMS_TEST_SERVER_PATH="$test_server_path" py -c \
    'import json, os, pathlib; data=json.loads(pathlib.Path(os.environ["PMS_TEST_SERVER_PATH"]).read_text()); print(data["server"]["id"])'
)"
if [[ -z "$smoke_server_id" ]]; then
  echo "Release readiness flow failed: local test server registration did not produce an ID." >&2
  exit 1
fi

started_at="$(date -u +"%Y-%m-%dT%H:%M:%S+00:00")"
finished_at="$(date -u +"%Y-%m-%dT%H:%M:%S+00:00")"
pms test record \
  --server-id "$smoke_server_id" \
  --status passed \
  --started-at "$started_at" \
  --finished-at "$finished_at" \
  --project-id "$project_id" \
  --command "release-smoke --project \"$project_name\"" \
  --runner "$actor_name" \
  --plan-id "$plan_id" \
  --task-id "$smoke_task_id" \
  --stdout "release smoke passed" \
  --artifacts '{"report":"release-smoke.txt"}' \
  --format json >"$test_record_path"

test_run_id="$(
  PMS_TEST_RECORD_PATH="$test_record_path" py -c \
    'import json, os, pathlib; data=json.loads(pathlib.Path(os.environ["PMS_TEST_RECORD_PATH"]).read_text()); print(data["id"])'
)"
if [[ -z "$test_run_id" ]]; then
  echo "Release readiness flow failed: test record did not produce a run ID." >&2
  exit 1
fi

pms test show "$test_run_id" --format json >"$test_show_path"

pms task complete "$smoke_task" --project "$project_name" --by "$actor_name" --format json >/dev/null
pms task start "$approval_task" --project "$project_name" --by "$actor_name" --format json >/dev/null
pms task progress "$approval_task" 50 "Go/no-go review in progress" --project "$project_name" --by "$actor_name" --format json >/dev/null

pms custom-field create \
  "$release_status_field" \
  --entity-type task \
  --type enum \
  --option draft \
  --option validated \
  --option approved \
  -d "Tracks release gate state" >/dev/null
custom_field_id="$(
  pms custom-field list --entity-type task --format json | PMS_EXPECTED_FIELD="$release_status_field" py -c \
    'import json, os, sys; data=json.load(sys.stdin); match=next((item for item in data.get("items", []) if item.get("name")==os.environ["PMS_EXPECTED_FIELD"]), None); print(match["id"] if match else "")'
)"
if [[ -z "$custom_field_id" ]]; then
  echo "Release readiness flow failed: could not resolve custom field ID." >&2
  exit 1
fi

pms custom-field value set \
  "$custom_field_id" \
  --entity-type task \
  --entity-id "$smoke_task_id" \
  --value validated \
  --created-by "$actor_name" >/dev/null

pms automation rule create \
  "$release_rule_name" \
  "task.completed" \
  "add_comment" \
  --description "Annotate completed release gates" \
  --aggregate-type task \
  --aggregate-id "$smoke_task_id" \
  --action-payload-json "{\"body\":\"Automation: release gate completed\",\"created_by\":\"$actor_name\"}" >/dev/null
automation_rule_id="$(
  pms automation rule list --format json | PMS_EXPECTED_RULE="$release_rule_name" py -c \
    'import json, os, sys; data=json.load(sys.stdin); match=next((item for item in data.get("items", []) if item.get("name")==os.environ["PMS_EXPECTED_RULE"]), None); print(match["id"] if match else "")'
)"
if [[ -z "$automation_rule_id" ]]; then
  echo "Release readiness flow failed: could not resolve automation rule ID." >&2
  exit 1
fi

pms queue create \
  "$queue_name" \
  --scope-type project \
  --scope "$project_name" \
  --description "Release gate queue for launch-control follow-up" \
  --filters '{"statuses":["todo","in_progress"]}' >/dev/null
queue_id="$(
  pms queue list --format json | PMS_EXPECTED_QUEUE="$queue_name" py -c \
    'import json, os, sys; data=json.load(sys.stdin); match=next((item for item in data.get("items", []) if item.get("name")==os.environ["PMS_EXPECTED_QUEUE"]), None); print(match["id"] if match else "")'
)"
if [[ -z "$queue_id" ]]; then
  echo "Release readiness flow failed: could not resolve queue ID." >&2
  exit 1
fi
pms queue run "$queue_id" --format json >"$queue_run_path"

pms work daily \
  --scope-type project \
  --scope "$project_name" \
  --format json \
  --no-attach \
  --export "$daily_path" >/dev/null
pms report project "$project_id" --format json -o "$project_report_path" >/dev/null
pms report metrics --project "$project_id" --format csv -o "$metrics_path" >/dev/null

[ -s "$bootstrap_path" ]
[ -s "$start_path" ]
[ -s "$dashboard_path" ]
[ -s "$daily_path" ]
[ -s "$project_report_path" ]
[ -s "$metrics_path" ]
[ -s "$queue_run_path" ]
[ -s "$test_server_path" ]
[ -s "$test_record_path" ]
[ -s "$test_show_path" ]

export PMS_RELEASE_PROJECT_NAME="$project_name"
export PMS_RELEASE_PROJECT_ID="$project_id"
export PMS_RELEASE_PLAN_ID="$plan_id"
export PMS_RELEASE_GOAL_ID="$goal_id"
export PMS_RELEASE_OBJECTIVE_ID="$objective_id"
export PMS_RELEASE_NOTES_TASK_ID="$notes_task_id"
export PMS_RELEASE_SMOKE_TASK_ID="$smoke_task_id"
export PMS_RELEASE_APPROVAL_TASK_ID="$approval_task_id"
export PMS_RELEASE_TEST_RUN_ID="$test_run_id"
export PMS_RELEASE_CUSTOM_FIELD_ID="$custom_field_id"
export PMS_RELEASE_RULE_ID="$automation_rule_id"
export PMS_RELEASE_QUEUE_ID="$queue_id"
export PMS_RELEASE_BOOTSTRAP_PATH="$bootstrap_path"
export PMS_RELEASE_START_PATH="$start_path"
export PMS_RELEASE_DASHBOARD_PATH="$dashboard_path"
export PMS_RELEASE_DAILY_PATH="$daily_path"
export PMS_RELEASE_PROJECT_REPORT_PATH="$project_report_path"
export PMS_RELEASE_METRICS_PATH="$metrics_path"
export PMS_RELEASE_QUEUE_RUN_PATH="$queue_run_path"
export PMS_RELEASE_TEST_SERVER_PATH="$test_server_path"
export PMS_RELEASE_TEST_RECORD_PATH="$test_record_path"
export PMS_RELEASE_TEST_SHOW_PATH="$test_show_path"
export PMS_RELEASE_SUMMARY_PATH="$summary_path"

py - <<'PY'
import json
import os
from pathlib import Path

from pms.utils.atomic_files import write_json_atomic

bootstrap = json.loads(Path(os.environ["PMS_RELEASE_BOOTSTRAP_PATH"]).read_text())
start = json.loads(Path(os.environ["PMS_RELEASE_START_PATH"]).read_text())
dashboard = json.loads(Path(os.environ["PMS_RELEASE_DASHBOARD_PATH"]).read_text())
daily = json.loads(Path(os.environ["PMS_RELEASE_DAILY_PATH"]).read_text())
test_show = json.loads(Path(os.environ["PMS_RELEASE_TEST_SHOW_PATH"]).read_text())

summary = {
    "project": {
        "name": os.environ["PMS_RELEASE_PROJECT_NAME"],
        "id": os.environ["PMS_RELEASE_PROJECT_ID"],
    },
    "execution_ids": {
        "plan_id": os.environ["PMS_RELEASE_PLAN_ID"],
        "goal_id": os.environ["PMS_RELEASE_GOAL_ID"],
        "objective_id": os.environ["PMS_RELEASE_OBJECTIVE_ID"],
        "notes_task_id": os.environ["PMS_RELEASE_NOTES_TASK_ID"],
        "smoke_task_id": os.environ["PMS_RELEASE_SMOKE_TASK_ID"],
        "approval_task_id": os.environ["PMS_RELEASE_APPROVAL_TASK_ID"],
        "test_run_id": os.environ["PMS_RELEASE_TEST_RUN_ID"],
    },
    "extension_ids": {
        "custom_field_id": os.environ["PMS_RELEASE_CUSTOM_FIELD_ID"],
        "automation_rule_id": os.environ["PMS_RELEASE_RULE_ID"],
        "queue_id": os.environ["PMS_RELEASE_QUEUE_ID"],
    },
    "artifacts": {
        "bootstrap": os.environ["PMS_RELEASE_BOOTSTRAP_PATH"],
        "start_guide": os.environ["PMS_RELEASE_START_PATH"],
        "dashboard": os.environ["PMS_RELEASE_DASHBOARD_PATH"],
        "daily_summary": os.environ["PMS_RELEASE_DAILY_PATH"],
        "project_report": os.environ["PMS_RELEASE_PROJECT_REPORT_PATH"],
        "metrics_csv": os.environ["PMS_RELEASE_METRICS_PATH"],
        "queue_run_json": os.environ["PMS_RELEASE_QUEUE_RUN_PATH"],
        "test_server_json": os.environ["PMS_RELEASE_TEST_SERVER_PATH"],
        "test_record_json": os.environ["PMS_RELEASE_TEST_RECORD_PATH"],
        "test_show_json": os.environ["PMS_RELEASE_TEST_SHOW_PATH"],
    },
    "next_steps": {
        "bootstrap": bootstrap.get("next_steps", []),
        "start": start.get("next_steps", []),
        "dashboard": dashboard.get("next_steps", []),
        "daily": daily.get("next_steps", []),
        "test_show": test_show.get("next_steps", []),
    },
    "links": {
        "bootstrap": bootstrap.get("links", {}),
        "start": start.get("links", {}),
        "dashboard": dashboard.get("links", {}),
        "daily": daily.get("links", {}),
    },
}
write_json_atomic(Path(os.environ["PMS_RELEASE_SUMMARY_PATH"]), summary)
PY

echo "Release readiness flow completed successfully."
echo "  project_id: $project_id"
echo "  plan_id: $plan_id"
echo "  goal_id: $goal_id"
echo "  objective_id: $objective_id"
echo "  test_run_id: $test_run_id"
echo "  queue_id: $queue_id"
echo "  summary: $summary_path"
