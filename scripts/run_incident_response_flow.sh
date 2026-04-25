#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/run_helpers.sh"

pms_setup_python_runtime "$ROOT_DIR"
pms_prepare_data_dir "$ROOT_DIR" "incident-flow"
pms_use_isolated_direct_runtime
timestamp="$(date +"%Y%m%d-%H%M%S")"

suffix="${PMS_INCIDENT_SUFFIX:-$timestamp}"
org_name="${PMS_INCIDENT_ORG:-Incident Org $suffix}"
portfolio_name="${PMS_INCIDENT_PORTFOLIO:-Operations Portfolio $suffix}"
program_name="${PMS_INCIDENT_PROGRAM:-Reliability Program $suffix}"
product_name="${PMS_INCIDENT_PRODUCT:-Core Platform $suffix}"
project_name="${PMS_INCIDENT_PROJECT:-Incident 2026-02-21 $suffix}"
incident_commander="${PMS_INCIDENT_COMMANDER:-incident-commander}"
oncall_actor="${PMS_INCIDENT_ONCALL:-oncall-engineer}"
comms_actor="${PMS_INCIDENT_COMMS:-status-comms}"
postmortem_actor="${PMS_INCIDENT_POSTMORTEM:-incident-reviewer}"

triage_task_title="${PMS_INCIDENT_TRIAGE_TASK:-Triage production impact}"
mitigation_task_title="${PMS_INCIDENT_MITIGATION_TASK:-Mitigate customer impact}"
comms_task_title="${PMS_INCIDENT_COMMS_TASK:-Publish status update}"
postmortem_task_title="${PMS_INCIDENT_POSTMORTEM_TASK:-Run postmortem and action items}"

custom_field_name="${PMS_INCIDENT_CUSTOM_FIELD:-incident_severity}"
queue_name="${PMS_INCIDENT_QUEUE_NAME:-incident-active-$suffix}"
automation_rule_name="${PMS_INCIDENT_RULE_NAME:-incident-auto-comment-$suffix}"

quickstart_path="$PMS_DATA_DIR/incident.quickstart.json"
daily_summary_path="$PMS_DATA_DIR/incident.daily.json"
project_report_path="$PMS_DATA_DIR/incident.project-report.json"
history_path="$PMS_DATA_DIR/incident.history.json"
metrics_path="$PMS_DATA_DIR/incident.metrics.csv"
queue_run_path="$PMS_DATA_DIR/incident.queue-run.json"
summary_path="$PMS_DATA_DIR/incident.summary.json"

echo "Running incident response flow"
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
  --task "$triage_task_title" \
  --task "$mitigation_task_title" \
  --task "$comms_task_title" \
  --task "$postmortem_task_title" \
  --create-plan \
  --create-rollups \
  --format json >"$quickstart_path"

incident_ids_env="$PMS_DATA_DIR/incident.ids.env"
py - "$quickstart_path" "$project_name" "$triage_task_title" "$mitigation_task_title" "$comms_task_title" "$postmortem_task_title" >"$incident_ids_env" <<'PY'
import json
import shlex
import sys
from pathlib import Path

quickstart_path, project_name, triage_title, mitigation_title, comms_title, postmortem_title = sys.argv[1:7]
payload = json.loads(Path(quickstart_path).read_text())
artifacts = payload.get("artifacts_created") or {}
project = artifacts.get("project") or {}
tasks = artifacts.get("tasks") or []

task_ids = {item.get("title"): item.get("id") for item in tasks}
required = {
    "PROJECT_ID": project.get("id"),
    "TRIAGE_TASK_ID": task_ids.get(triage_title),
    "MITIGATION_TASK_ID": task_ids.get(mitigation_title),
    "COMMS_TASK_ID": task_ids.get(comms_title),
    "POSTMORTEM_TASK_ID": task_ids.get(postmortem_title),
}

missing = [name for name, value in required.items() if not value]
if missing:
    raise SystemExit(
        "Incident flow failed: missing quickstart identifiers for "
        + ", ".join(missing)
        + f" in project {project_name!r}."
    )

for name, value in required.items():
    print(f"{name}={shlex.quote(str(value))}")
PY
source "$incident_ids_env"

project_id="$PROJECT_ID"
triage_task_id="$TRIAGE_TASK_ID"
mitigation_task_id="$MITIGATION_TASK_ID"
comms_task_id="$COMMS_TASK_ID"
postmortem_task_id="$POSTMORTEM_TASK_ID"

pms task start "$triage_task_title" --project "$project_name" --by "$incident_commander" --format json >/dev/null
pms task progress "$triage_task_title" 70 "Impact identified and blast radius defined" --project "$project_name" --by "$incident_commander" --format json >/dev/null
pms task complete "$triage_task_title" --project "$project_name" --by "$incident_commander" --format json >/dev/null

pms task start "$mitigation_task_title" --project "$project_name" --by "$oncall_actor" --format json >/dev/null
pms task progress "$mitigation_task_title" 80 "Rollback and containment in progress" --project "$project_name" --by "$oncall_actor" --format json >/dev/null
pms task complete "$mitigation_task_title" --project "$project_name" --by "$oncall_actor" --format json >/dev/null

pms task start "$comms_task_title" --project "$project_name" --by "$comms_actor" --format json >/dev/null
pms task progress "$comms_task_title" 60 "Customer-facing update drafted and reviewed" --project "$project_name" --by "$comms_actor" --format json >/dev/null
pms task complete "$comms_task_title" --project "$project_name" --by "$comms_actor" --format json >/dev/null

pms task start "$postmortem_task_title" --project "$project_name" --by "$postmortem_actor" --format json >/dev/null
pms task progress "$postmortem_task_title" 40 "Timeline assembled and owners identified" --project "$project_name" --by "$postmortem_actor" --format json >/dev/null

pms comment add task "$mitigation_task_id" "Mitigation completed. Comms task unblocked for publication." --by "$oncall_actor" --mention "$comms_actor" --watch >/dev/null
pms watcher add task "$postmortem_task_id" "$incident_commander" >/dev/null
pms comment list task "$mitigation_task_id" --format json >/dev/null
pms watcher list task "$postmortem_task_id" --format json >/dev/null

custom_field_id="$(
  pms custom-field list --entity-type task --format json | PMS_EXPECTED_FIELD_NAME="$custom_field_name" py -c \
    'import json, os, sys; payload=json.load(sys.stdin); items=payload.get("items", []); expected=os.environ["PMS_EXPECTED_FIELD_NAME"]; match=next((item for item in items if item.get("name")==expected), None); print(match["id"] if match else "")'
)"
if [[ -z "$custom_field_id" ]]; then
  pms custom-field create \
    "$custom_field_name" \
    --entity-type task \
    --type enum \
    --option sev1 \
    --option sev2 \
    --option sev3 \
    -d "Incident severity classification" >/dev/null
  custom_field_id="$(
    pms custom-field list --entity-type task --format json | PMS_EXPECTED_FIELD_NAME="$custom_field_name" py -c \
      'import json, os, sys; payload=json.load(sys.stdin); items=payload.get("items", []); expected=os.environ["PMS_EXPECTED_FIELD_NAME"]; match=next((item for item in items if item.get("name")==expected), None); print(match["id"] if match else "")'
  )"
fi
if [[ -z "$custom_field_id" ]]; then
  echo "Incident flow failed: could not resolve custom field ID for '$custom_field_name'." >&2
  exit 1
fi

pms custom-field value set \
  "$custom_field_id" \
  --entity-type task \
  --entity-id "$mitigation_task_id" \
  --value sev1 \
  --created-by "$incident_commander" >/dev/null
pms custom-field value set \
  "$custom_field_id" \
  --entity-type task \
  --entity-id "$postmortem_task_id" \
  --value sev1 \
  --created-by "$postmortem_actor" >/dev/null

automation_rule_id="$(
  pms automation rule list --format json | PMS_EXPECTED_RULE_NAME="$automation_rule_name" py -c \
    'import json, os, sys; payload=json.load(sys.stdin); items=payload.get("items", []); expected=os.environ["PMS_EXPECTED_RULE_NAME"]; match=next((item for item in items if item.get("name")==expected), None); print(match["id"] if match else "")'
)"
if [[ -z "$automation_rule_id" ]]; then
  pms automation rule create \
    "$automation_rule_name" \
    "task.completed" \
    "add_comment" \
    --description "Annotate incident task completion events" \
    --aggregate-type task \
    --aggregate-id "$mitigation_task_id" \
    --action-payload-json "{\"body\":\"Automation: incident task completed\",\"created_by\":\"$incident_commander\"}" >/dev/null
  automation_rule_id="$(
    pms automation rule list --format json | PMS_EXPECTED_RULE_NAME="$automation_rule_name" py -c \
      'import json, os, sys; payload=json.load(sys.stdin); items=payload.get("items", []); expected=os.environ["PMS_EXPECTED_RULE_NAME"]; match=next((item for item in items if item.get("name")==expected), None); print(match["id"] if match else "")'
  )"
fi
if [[ -z "$automation_rule_id" ]]; then
  echo "Incident flow failed: could not resolve automation rule ID for '$automation_rule_name'." >&2
  exit 1
fi

queue_id="$(
  pms queue list --format json | PMS_EXPECTED_QUEUE_NAME="$queue_name" py -c \
    'import json, os, sys; payload=json.load(sys.stdin); items=payload.get("items", []); expected=os.environ["PMS_EXPECTED_QUEUE_NAME"]; match=next((item for item in items if item.get("name")==expected), None); print(match["id"] if match else "")'
)"
if [[ -z "$queue_id" ]]; then
  pms queue create \
    "$queue_name" \
    --scope-type project \
    --scope "$project_name" \
    --description "Incident active work queue" \
    --filters '{"statuses":["todo","in_progress"]}' >/dev/null
  queue_id="$(
    pms queue list --format json | PMS_EXPECTED_QUEUE_NAME="$queue_name" py -c \
      'import json, os, sys; payload=json.load(sys.stdin); items=payload.get("items", []); expected=os.environ["PMS_EXPECTED_QUEUE_NAME"]; match=next((item for item in items if item.get("name")==expected), None); print(match["id"] if match else "")'
  )"
fi
if [[ -z "$queue_id" ]]; then
  echo "Incident flow failed: could not resolve queue ID for '$queue_name'." >&2
  exit 1
fi
pms queue run "$queue_id" --format json >"$queue_run_path"

pms work daily \
  --scope-type project \
  --scope "$project_name" \
  --format json \
  --no-attach \
  --export "$daily_summary_path" >/dev/null
pms report project "$project_id" --format json -o "$project_report_path" >/dev/null
pms report history --days 14 --format json -o "$history_path" >/dev/null
pms report metrics --format csv -o "$metrics_path" >/dev/null

[ -s "$daily_summary_path" ]
[ -s "$project_report_path" ]
[ -s "$history_path" ]
[ -s "$metrics_path" ]
[ -s "$queue_run_path" ]

export PMS_INCIDENT_PROJECT_NAME="$project_name"
export PMS_INCIDENT_PROJECT_ID="$project_id"
export PMS_INCIDENT_TRIAGE_TASK_ID="$triage_task_id"
export PMS_INCIDENT_MITIGATION_TASK_ID="$mitigation_task_id"
export PMS_INCIDENT_COMMS_TASK_ID="$comms_task_id"
export PMS_INCIDENT_POSTMORTEM_TASK_ID="$postmortem_task_id"
export PMS_INCIDENT_CUSTOM_FIELD_ID="$custom_field_id"
export PMS_INCIDENT_AUTOMATION_RULE_ID="$automation_rule_id"
export PMS_INCIDENT_QUEUE_ID="$queue_id"
export PMS_INCIDENT_DAILY_PATH="$daily_summary_path"
export PMS_INCIDENT_PROJECT_REPORT_PATH="$project_report_path"
export PMS_INCIDENT_HISTORY_PATH="$history_path"
export PMS_INCIDENT_METRICS_PATH="$metrics_path"
export PMS_INCIDENT_QUEUE_RUN_PATH="$queue_run_path"

py - <<'PY'
import json
import os
from pathlib import Path

from pms.utils.atomic_files import write_json_atomic

summary_path = Path(os.environ["PMS_DATA_DIR"]) / "incident.summary.json"
data = {
    "project": {
        "name": os.environ["PMS_INCIDENT_PROJECT_NAME"],
        "id": os.environ["PMS_INCIDENT_PROJECT_ID"],
    },
    "task_ids": {
        "triage": os.environ["PMS_INCIDENT_TRIAGE_TASK_ID"],
        "mitigation": os.environ["PMS_INCIDENT_MITIGATION_TASK_ID"],
        "comms": os.environ["PMS_INCIDENT_COMMS_TASK_ID"],
        "postmortem": os.environ["PMS_INCIDENT_POSTMORTEM_TASK_ID"],
    },
    "extension_ids": {
        "custom_field_id": os.environ["PMS_INCIDENT_CUSTOM_FIELD_ID"],
        "automation_rule_id": os.environ["PMS_INCIDENT_AUTOMATION_RULE_ID"],
        "queue_id": os.environ["PMS_INCIDENT_QUEUE_ID"],
    },
    "artifacts": {
        "daily_summary": os.environ["PMS_INCIDENT_DAILY_PATH"],
        "project_report": os.environ["PMS_INCIDENT_PROJECT_REPORT_PATH"],
        "history_json": os.environ["PMS_INCIDENT_HISTORY_PATH"],
        "metrics_csv": os.environ["PMS_INCIDENT_METRICS_PATH"],
        "queue_run_json": os.environ["PMS_INCIDENT_QUEUE_RUN_PATH"],
    },
}
write_json_atomic(summary_path, data)
PY

echo "Incident response flow completed successfully."
echo "  project_id: $project_id"
echo "  triage_task_id: $triage_task_id"
echo "  mitigation_task_id: $mitigation_task_id"
echo "  comms_task_id: $comms_task_id"
echo "  postmortem_task_id: $postmortem_task_id"
echo "  custom_field_id: $custom_field_id"
echo "  automation_rule_id: $automation_rule_id"
echo "  queue_id: $queue_id"
echo "  summary: $summary_path"
