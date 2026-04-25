#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/run_helpers.sh"

LOOP_TIMEOUT_SECONDS="${PMS_AGENT_LOOP_TIMEOUT_SECONDS:-$(pms_parallel_headroom_value 150 240)}"
LOOP_MAX_RUNTIME_SECONDS="${PMS_AGENT_LOOP_MAX_RUNTIME_SECONDS:-$(pms_parallel_headroom_value 90 150)}"
LOOP_MAX_ITERATIONS="${PMS_AGENT_LOOP_MAX_ITERATIONS:-2}"

pms_setup_python_runtime "$ROOT_DIR"

loop_python_command() {
  if [[ "$RUN_MODE" == "uv" ]]; then
    printf '%s' "uv run pms"
  else
    printf '%q %q %s' "$PYTHON_BIN" "-m" "pms"
  fi
}

pms_prepare_data_dir "$ROOT_DIR" "agent-loop"
pms_use_isolated_direct_runtime
timestamp="$(date +"%Y%m%d-%H%M%S")"

suffix="${PMS_AGENT_LOOP_SUFFIX:-$timestamp}"
org_name="${PMS_AGENT_LOOP_ORG:-Agent Loop Org $suffix}"
product_name="${PMS_AGENT_LOOP_PRODUCT:-Agent Loop Product $suffix}"
project_name="${PMS_AGENT_LOOP_PROJECT:-Agent Loop Project $suffix}"
goal_name="${PMS_AGENT_LOOP_GOAL:-Ship Agent Loop Proof Closure $suffix}"
objective_name="${PMS_AGENT_LOOP_OBJECTIVE:-Close loop evidence cleanly $suffix}"
primary_task_title="${PMS_AGENT_LOOP_PRIMARY_TASK:-Implement loop-guided delivery slice}"
closure_task_title="${PMS_AGENT_LOOP_CLOSURE_TASK:-Attach proof and close the delivery slice}"
actor_name="${PMS_AGENT_LOOP_ACTOR:-loop-operator}"

config_path="$PMS_DATA_DIR/pms-loop.yml"
prompt_path="$PMS_DATA_DIR/PROMPT.md"
setup_log_path="$PMS_DATA_DIR/agent-loop.setup.log"
projects_path="$PMS_DATA_DIR/agent-loop.projects.json"
goals_path="$PMS_DATA_DIR/agent-loop.goals.json"
objectives_path="$PMS_DATA_DIR/agent-loop.objectives.json"
plans_path="$PMS_DATA_DIR/agent-loop.plans.json"
tasks_path="$PMS_DATA_DIR/agent-loop.tasks.json"
guard_path="$PMS_DATA_DIR/agent-loop.guard.json"
task_start_path="$PMS_DATA_DIR/agent-loop.task-start.json"
task_progress_path="$PMS_DATA_DIR/agent-loop.task-progress.json"
loop_run_log_path="$PMS_DATA_DIR/agent-loop.run.log"
loops_path="$PMS_DATA_DIR/agent-loop.list.json"
loop_show_path="$PMS_DATA_DIR/agent-loop.show.json"
loop_messages_path="$PMS_DATA_DIR/agent-loop.messages.json"
test_server_path="$PMS_DATA_DIR/agent-loop.test-server.json"
test_record_path="$PMS_DATA_DIR/agent-loop.test-record.json"
evidence_list_path="$PMS_DATA_DIR/agent-loop.evidence.json"
proof_bundle_path="$PMS_DATA_DIR/agent-loop.proof-bundle.json"
task_complete_path="$PMS_DATA_DIR/agent-loop.task-complete.json"
goal_summary_path="$PMS_DATA_DIR/agent-loop.goal-summary.json"
work_review_path="$PMS_DATA_DIR/agent-loop.work-review.json"
summary_note_path="$PMS_DATA_DIR/agent-loop.summary-note.md"
summary_path="$PMS_DATA_DIR/agent-loop.summary.json"

echo "Running agent-driven execution-loop flow"
echo "  run_mode: $RUN_MODE"
echo "  data_dir: $PMS_DATA_DIR"
echo "  project: $project_name"
echo "  loop_timeout_seconds: $LOOP_TIMEOUT_SECONDS"

loop_runner_pid=""

cleanup() {
  if [[ -n "$loop_runner_pid" ]]; then
    kill "$loop_runner_pid" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

chmod +x "$ROOT_DIR/scripts/fake_agent_loop_runner.py"

pms init >/dev/null
pms org create "$org_name" >/dev/null
pms product create "$product_name" >/dev/null
pms project create "$project_name" --org "$org_name" --product "$product_name" >/dev/null
pms loop setup \
  --defaults \
  --project "$project_name" \
  --goal "$goal_name" \
  --objective "$objective_name" \
  --criterion "Loop prompt and config are generated from live PMS state" \
  --criterion "Agent loop runs and records persisted loop messages" \
  --criterion "Proof bundle includes evidence plus a recorded test run" \
  --task "$primary_task_title" \
  --task "$closure_task_title" \
  --config "$config_path" \
  --prompt-file "$prompt_path" \
  --force >"$setup_log_path"
py scripts/update_loop_config.py \
  --file "$config_path" \
  --set stop_when_goals_complete=false \
  --set max_iterations="$LOOP_MAX_ITERATIONS" \
  --set max_runtime_seconds="$LOOP_MAX_RUNTIME_SECONDS"

pms project list --format json >"$projects_path"
project_id="$(
  py scripts/json_query.py find --file "$projects_path" --items items --match-field name --match-value "$project_name" --get id
)"

pms goal list --project "$project_name" --format json >"$goals_path"
goal_id="$(
  py scripts/json_query.py find --file "$goals_path" --items items --match-field name --match-value "$goal_name" --get id
)"

pms objective list --goal "$goal_name" --format json >"$objectives_path"
objective_id="$(
  py scripts/json_query.py find --file "$objectives_path" --items items --match-field name --match-value "$objective_name" --get id
)"

pms plan list --project "$project_name" --format json >"$plans_path"
plan_id="$(
  py scripts/json_query.py find --file "$plans_path" --items items --match-field name --match-value "$project_name Plan" --get id
)"

pms task list --project "$project_name" --format json >"$tasks_path"
primary_task_id="$(
  py scripts/json_query.py find --file "$tasks_path" --items items --match-field title --match-value "$primary_task_title" --get id
)"
closure_task_id="$(
  py scripts/json_query.py find --file "$tasks_path" --items items --match-field title --match-value "$closure_task_title" --get id
)"

if [[ -z "$project_id" || -z "$goal_id" || -z "$objective_id" || -z "$plan_id" || -z "$primary_task_id" || -z "$closure_task_id" ]]; then
  echo "Agent-loop flow failed: could not resolve required IDs." >&2
  exit 1
fi

pms task start "$primary_task_id" --by "$actor_name" --format json >"$task_start_path"
pms task progress "$primary_task_id" 40 "Loop config generated; agent execution starting" --by "$actor_name" --format json >"$task_progress_path"
pms loop guard --project "$project_name" --goal "$goal_name" --format json >"$guard_path"

LOOP_PMS_COMMAND="$(loop_python_command)"

py scripts/run_with_timeout.py \
  --timeout-seconds "$LOOP_TIMEOUT_SECONDS" \
  --cwd "$ROOT_DIR" \
  --stdout-file "$loop_run_log_path" \
  --stderr-file "$loop_run_log_path" \
  -- \
  bash -lc \
  "export PMS_DATA_DIR=$(printf '%q' "$PMS_DATA_DIR") PMS_DATABASE_PATH=$(printf '%q' "$PMS_DATABASE_PATH") PMS_LOG_DIR=$(printf '%q' "$PMS_LOG_DIR") PMS_ENV_FILE=$(printf '%q' "${PMS_ENV_FILE:-$PMS_DATA_DIR/.env}"); \
   $LOOP_PMS_COMMAND loop run \
   --config $(printf '%q' "$config_path") \
   --project $(printf '%q' "$project_name") \
   --prompt-file $(printf '%q' "$prompt_path") \
   --agent command \
   --agent-command $(printf '%q' "$ROOT_DIR/scripts/fake_agent_loop_runner.py") \
   --prompt-mode stdin \
   --max-iterations $(printf '%q' "$LOOP_MAX_ITERATIONS") \
   --max-runtime $(printf '%q' "$LOOP_MAX_RUNTIME_SECONDS") \
   --completion-promise DONE"

loop_exit_code=$?
if [[ "$loop_exit_code" -eq 124 ]]; then
  echo "Agent-loop flow failed: loop run exceeded ${LOOP_TIMEOUT_SECONDS}s timeout." >&2
  exit 124
fi
if [[ "$loop_exit_code" -ne 0 ]]; then
  echo "Agent-loop flow failed: loop run exited with code $loop_exit_code." >&2
  exit "$loop_exit_code"
fi

pms loop list --project "$project_name" --include-ended --format json >"$loops_path"
loop_id="$(
  py scripts/json_query.py path --file "$loops_path" --get 0.id
)"
if [[ -z "$loop_id" ]]; then
  echo "Agent-loop flow failed: no loop session was recorded." >&2
  exit 1
fi

pms loop show "$loop_id" --include-messages --format json >"$loop_show_path"
pms loop messages "$loop_id" --format json >"$loop_messages_path"

pms test server ensure-local --project-id "$project_id" --format json >"$test_server_path"

started_at="$(date -u +"%Y-%m-%dT%H:%M:%S+00:00")"
finished_at="$started_at"

cat >"$summary_note_path" <<EOF_NOTE
# Agent Loop Proof Note

- project: $project_name
- goal: $goal_name
- objective: $objective_name
- primary_task_id: $primary_task_id
- loop_id: $loop_id
- actor: $actor_name

The loop prompt and config were generated from live PMS state, the loop ran with a
deterministic command adapter, and the closure path records evidence plus a test
run before task completion.
EOF_NOTE

pms task evidence add "$primary_task_id" artifact "$prompt_path" --created-by "$actor_name" >/dev/null
pms task evidence add "$primary_task_id" artifact "$config_path" --created-by "$actor_name" >/dev/null
pms task evidence add "$primary_task_id" artifact "$loop_show_path" --created-by "$actor_name" >/dev/null

pms test record \
  --server-id local \
  --status passed \
  --started-at "$started_at" \
  --finished-at "$finished_at" \
  --project-id "$project_id" \
  --task-id "$primary_task_id" \
  --command "pytest -q tests/services/test_agent_loop_service.py" \
  --runner "agent-loop-scenario" \
  --format json >"$test_record_path"

test_run_id="$(
  py scripts/json_query.py path --file "$test_record_path" --get id
)"
if [[ -z "$test_run_id" ]]; then
  echo "Agent-loop flow failed: test run ID missing from recorded test run." >&2
  exit 1
fi

pms task evidence add "$primary_task_id" test_run "$test_run_id" --created-by "$actor_name" >/dev/null
pms task evidence list "$primary_task_id" --include-test-runs --format json >"$evidence_list_path"
pms task proof-bundle "$primary_task_id" --format json >"$proof_bundle_path"
pms task complete "$primary_task_id" --by "$actor_name" --format json >"$task_complete_path"
pms goal summary "$goal_id" --format json >"$goal_summary_path"
pms work review --scope-type project --scope "$project_name" --reviewed-by "$actor_name" --note "Loop proof reviewed and closure path recorded" --format json >"$work_review_path"

[ -s "$config_path" ]
[ -s "$prompt_path" ]
[ -s "$setup_log_path" ]
[ -s "$guard_path" ]
[ -s "$loop_run_log_path" ]
[ -s "$loops_path" ]
[ -s "$loop_show_path" ]
[ -s "$loop_messages_path" ]
[ -s "$test_server_path" ]
[ -s "$test_record_path" ]
[ -s "$evidence_list_path" ]
[ -s "$proof_bundle_path" ]
[ -s "$task_complete_path" ]
[ -s "$goal_summary_path" ]
[ -s "$work_review_path" ]

export PMS_AGENT_LOOP_PROJECT_NAME="$project_name"
export PMS_AGENT_LOOP_PROJECT_ID="$project_id"
export PMS_AGENT_LOOP_GOAL_NAME="$goal_name"
export PMS_AGENT_LOOP_GOAL_ID="$goal_id"
export PMS_AGENT_LOOP_OBJECTIVE_NAME="$objective_name"
export PMS_AGENT_LOOP_OBJECTIVE_ID="$objective_id"
export PMS_AGENT_LOOP_PLAN_ID="$plan_id"
export PMS_AGENT_LOOP_PRIMARY_TASK_ID="$primary_task_id"
export PMS_AGENT_LOOP_CLOSURE_TASK_ID="$closure_task_id"
export PMS_AGENT_LOOP_LOOP_ID="$loop_id"
export PMS_AGENT_LOOP_TEST_RUN_ID="$test_run_id"
export PMS_AGENT_LOOP_CONFIG_PATH="$config_path"
export PMS_AGENT_LOOP_PROMPT_PATH="$prompt_path"
export PMS_AGENT_LOOP_SETUP_LOG_PATH="$setup_log_path"
export PMS_AGENT_LOOP_GUARD_PATH="$guard_path"
export PMS_AGENT_LOOP_LOOP_RUN_LOG_PATH="$loop_run_log_path"
export PMS_AGENT_LOOP_LOOPS_PATH="$loops_path"
export PMS_AGENT_LOOP_LOOP_SHOW_PATH="$loop_show_path"
export PMS_AGENT_LOOP_LOOP_MESSAGES_PATH="$loop_messages_path"
export PMS_AGENT_LOOP_TEST_SERVER_PATH="$test_server_path"
export PMS_AGENT_LOOP_TEST_RECORD_PATH="$test_record_path"
export PMS_AGENT_LOOP_EVIDENCE_LIST_PATH="$evidence_list_path"
export PMS_AGENT_LOOP_PROOF_BUNDLE_PATH="$proof_bundle_path"
export PMS_AGENT_LOOP_TASK_COMPLETE_PATH="$task_complete_path"
export PMS_AGENT_LOOP_GOAL_SUMMARY_PATH="$goal_summary_path"
export PMS_AGENT_LOOP_WORK_REVIEW_PATH="$work_review_path"
export PMS_AGENT_LOOP_SUMMARY_NOTE_PATH="$summary_note_path"
export PMS_AGENT_LOOP_SUMMARY_PATH="$summary_path"

py scripts/write_agent_execution_loop_summary.py

echo "Agent-loop flow completed."
echo "  loop show: $loop_show_path"
echo "  proof bundle: $proof_bundle_path"
echo "  summary: $summary_path"
