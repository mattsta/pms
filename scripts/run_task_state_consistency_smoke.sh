#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/run_helpers.sh"

CONTRACT_TIMEOUT_SECONDS="${PMS_TASK_STATE_CONTRACT_TIMEOUT_SECONDS:-120}"
pms_setup_python_runtime "$ROOT_DIR"
pms_prepare_data_dir "$ROOT_DIR" "task-state-consistency"
pms_use_isolated_direct_runtime

timestamp="$(date +"%Y%m%d-%H%M%S")"
suffix="${PMS_TASK_STATE_SUFFIX:-$timestamp}"
iterations="${PMS_TASK_STATE_ITERATIONS:-3}"
actor_name="${PMS_TASK_STATE_ACTOR:-codex}"
project_name="Task State Consistency Project $suffix"
goal_name="Task State Consistency Goal $suffix"

echo "Running task state consistency smoke"
echo "  run_mode: $RUN_MODE"
echo "  data_dir: $PMS_DATA_DIR"
echo "  iterations: $iterations"
echo "  contract_timeout_seconds: $CONTRACT_TIMEOUT_SECONDS"

pms init >/dev/null
pms project create "$project_name" --format json >"$PMS_DATA_DIR/project.json"
pms goal create "$goal_name" --project "$project_name" --owner "$actor_name" --format json >"$PMS_DATA_DIR/goal.json"
pms objective create "Execution Consistency Objective A $suffix" --goal "$goal_name" --format json >"$PMS_DATA_DIR/objective-a.json"
pms objective create "Execution Consistency Objective B $suffix" --goal "$goal_name" --format json >"$PMS_DATA_DIR/objective-b.json"

for iteration in $(seq 1 "$iterations"); do
  raced_task_title="Race Task $suffix $iteration"
  ready_task_title="Ready Follow-Up $suffix $iteration"
  metadata_task_title="Metadata Race Task $suffix $iteration"
  raced_task_file="$PMS_DATA_DIR/raced-task-$iteration.json"
  ready_task_file="$PMS_DATA_DIR/ready-task-$iteration.json"
  metadata_task_file="$PMS_DATA_DIR/metadata-task-$iteration.json"
  progress_file="$PMS_DATA_DIR/progress-$iteration.json"
  complete_file="$PMS_DATA_DIR/complete-$iteration.json"
  metadata_update_file="$PMS_DATA_DIR/metadata-update-$iteration.json"
  task_file="$PMS_DATA_DIR/task-$iteration.json"
  metadata_show_file="$PMS_DATA_DIR/metadata-show-$iteration.json"
  list_file="$PMS_DATA_DIR/task-list-$iteration.json"
  project_file="$PMS_DATA_DIR/project-show-$iteration.json"
  summary_file="$PMS_DATA_DIR/goal-summary-$iteration.json"
  objective_file="$PMS_DATA_DIR/objective-list-$iteration.json"
dashboard_file="$PMS_DATA_DIR/dashboard-$iteration.json"

  pms task create "$project_name" "$raced_task_title" --format json >"$raced_task_file"
  pms task create "$project_name" "$ready_task_title" --format json >"$ready_task_file"
  pms task create "$project_name" "$metadata_task_title" --format json >"$metadata_task_file"

  raced_task_id="$(
    py - <<'PY' "$raced_task_file"
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
print(payload["task"]["id"])
PY
  )"
  ready_task_id="$(
    py - <<'PY' "$ready_task_file"
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
print(payload["task"]["id"])
PY
  )"
  metadata_task_id="$(
    py - <<'PY' "$metadata_task_file"
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
print(payload["task"]["id"])
PY
  )"
  metadata_criterion="Preserve started status $iteration"

  pms task start "$raced_task_id" --project "$project_name" --by "$actor_name" --format json >"$PMS_DATA_DIR/start-$iteration.json"

  pms task update "$metadata_task_id" --project "$project_name" --done-when "$metadata_criterion" --format json >"$metadata_update_file" &
  metadata_update_pid=$!
  pms task start "$metadata_task_id" --project "$project_name" --by "$actor_name" --format json >/dev/null &
  metadata_start_pid=$!
  wait "$metadata_update_pid"
  wait "$metadata_start_pid"

  pms task progress "$raced_task_id" 100 "Late progress update $iteration" --project "$project_name" --by "$actor_name" --format json >"$progress_file" &
  progress_pid=$!
  pms task complete "$raced_task_id" --project "$project_name" --by "$actor_name" --format json >"$complete_file" &
  complete_pid=$!
  wait "$progress_pid"
  wait "$complete_pid"

  pms task show "$raced_task_id" --format json >"$task_file"
  pms task show "$metadata_task_id" --format json >"$metadata_show_file"
  pms task list --project "$project_name" --format json >"$list_file"
  pms project show "$project_name" --format json >"$project_file"
  pms goal summary "$goal_name" --format json >"$summary_file"
  pms objective list --goal "$goal_name" --format json >"$objective_file"
  pms dashboard --format json >"$dashboard_file"

  py - <<'PY' "$PMS_DATA_DIR/goal.json" "$PMS_DATA_DIR/start-$iteration.json" "$progress_file" "$complete_file" "$task_file" "$metadata_show_file" "$list_file" "$project_file" "$summary_file" "$objective_file" "$dashboard_file" "$raced_task_id" "$ready_task_id" "$metadata_task_id" "$metadata_criterion" "$project_name" "$PMS_DATABASE_PATH"
import json
import sys
from pathlib import Path

goal_create_payload = json.loads(Path(sys.argv[1]).read_text())
start_payload = json.loads(Path(sys.argv[2]).read_text())
progress_payload = json.loads(Path(sys.argv[3]).read_text())
complete_payload = json.loads(Path(sys.argv[4]).read_text())
task_payload = json.loads(Path(sys.argv[5]).read_text())
metadata_payload = json.loads(Path(sys.argv[6]).read_text())
task_list_payload = json.loads(Path(sys.argv[7]).read_text())
project_payload = json.loads(Path(sys.argv[8]).read_text())
goal_summary_payload = json.loads(Path(sys.argv[9]).read_text())
objective_list_payload = json.loads(Path(sys.argv[10]).read_text())
dashboard_payload = json.loads(Path(sys.argv[11]).read_text())
raced_task_id = sys.argv[12]
ready_task_id = sys.argv[13]
metadata_task_id = sys.argv[14]
metadata_criterion = sys.argv[15]
project_name = sys.argv[16]
database_path = sys.argv[17]

for mutation_payload, label in (
    (goal_create_payload, "goal create"),
    (start_payload, "task start"),
    (progress_payload, "task progress"),
    (complete_payload, "task complete"),
):
    runtime_write = mutation_payload.get("runtime_write")
    if not isinstance(runtime_write, dict):
        raise SystemExit(f"Task state smoke failed: {label} missing runtime_write.")
    if runtime_write.get("write_path") != "direct_file":
        raise SystemExit(f"Task state smoke failed: {label} did not report direct_file write path.")
    if runtime_write.get("target_kind") != "workspace_sqlite":
        raise SystemExit(f"Task state smoke failed: {label} did not report workspace_sqlite target kind.")
    if runtime_write.get("target_location") != database_path:
        raise SystemExit(f"Task state smoke failed: {label} target_location drifted from PMS_DATABASE_PATH.")

if task_payload["id"] != raced_task_id:
    raise SystemExit("Task state smoke failed: wrong task read back.")
if task_payload["status"] != "done":
    raise SystemExit("Task state smoke failed: raced task did not stay done.")
if task_payload["current_progress_percent"] != 100:
    raise SystemExit("Task state smoke failed: raced task progress is not 100.")

if metadata_payload["id"] != metadata_task_id:
    raise SystemExit("Task state smoke failed: wrong metadata task read back.")
if metadata_payload["status"] != "in_progress":
    raise SystemExit("Task state smoke failed: metadata update race reverted started task.")
criteria = metadata_payload.get("completion_criteria")
if not isinstance(criteria, list) or metadata_criterion not in criteria:
    raise SystemExit("Task state smoke failed: metadata completion criteria missing.")

task_focus = task_list_payload.get("focus_task")
if not isinstance(task_focus, dict):
    raise SystemExit("Task state smoke failed: task list focus missing.")
if task_focus.get("id") != metadata_task_id:
    raise SystemExit("Task state smoke failed: task list focus did not stay on active metadata work.")
if task_focus.get("status") != "in_progress":
    raise SystemExit("Task state smoke failed: task list focus is not in_progress.")

project_focus = project_payload.get("focus_task")
if not isinstance(project_focus, dict):
    raise SystemExit("Task state smoke failed: project show focus missing.")
if project_focus.get("id") != metadata_task_id:
    raise SystemExit("Task state smoke failed: project show focus drifted away from active metadata work.")
if project_focus.get("status") != "in_progress":
    raise SystemExit("Task state smoke failed: project show focus is not in_progress.")

execution = goal_summary_payload.get("execution")
if not isinstance(execution, dict):
    raise SystemExit("Task state smoke failed: goal summary execution missing.")
goal_focus = execution.get("focus_task")
if not isinstance(goal_focus, dict):
    raise SystemExit("Task state smoke failed: goal focus missing.")
if goal_focus.get("id") != metadata_task_id:
    raise SystemExit("Task state smoke failed: goal focus did not stay on active metadata work.")
if goal_focus.get("status") != "in_progress":
    raise SystemExit("Task state smoke failed: goal focus is not in_progress.")

objective_items = objective_list_payload.get("items")
if not isinstance(objective_items, list) or not objective_items:
    raise SystemExit("Task state smoke failed: objective list missing items.")
objective_progress = {item.get("progress_percent") for item in objective_items}
if len(objective_progress) != 1:
    raise SystemExit("Task state smoke failed: objective progress is inconsistent across execution-backed objectives.")
goal_progress = goal_summary_payload["goal"]["progress_percent"]
if objective_progress != {goal_progress}:
    raise SystemExit("Task state smoke failed: objective progress does not match goal rollup.")

dashboard_focus = dashboard_payload.get("focus_task")
if not isinstance(dashboard_focus, dict):
    raise SystemExit("Task state smoke failed: dashboard focus missing.")
if dashboard_focus.get("id") != metadata_task_id:
    raise SystemExit("Task state smoke failed: dashboard focus drifted away from active metadata work.")
if dashboard_focus.get("project_name") != project_name:
    raise SystemExit("Task state smoke failed: dashboard focus project mismatch.")
PY
done

echo "Task state consistency smoke completed successfully."
echo "  project: $project_name"
echo "  goal: $goal_name"
