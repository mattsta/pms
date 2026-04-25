#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/run_helpers.sh"

pms_setup_python_runtime "$ROOT_DIR"
pms_prepare_data_dir "$ROOT_DIR" "proof-bundle"
pms_use_isolated_direct_runtime

timestamp="$(date +"%Y%m%d-%H%M%S")"
suffix="${PMS_PROOF_BUNDLE_SUFFIX:-$timestamp}"
project_name="${PMS_PROOF_BUNDLE_PROJECT:-Proof Bundle Contract Project $suffix}"
task_title="${PMS_PROOF_BUNDLE_TASK:-Attach proof and verify bundle $suffix}"
actor_name="${PMS_PROOF_BUNDLE_ACTOR:-proof-operator}"

artifact_note_path="$PMS_DATA_DIR/proof-note.md"
task_list_path="$PMS_DATA_DIR/tasks.json"
test_record_path="$PMS_DATA_DIR/test-record.json"
evidence_list_path="$PMS_DATA_DIR/evidence-list.json"
proof_bundle_path="$PMS_DATA_DIR/proof-bundle.json"
proof_search_path="$PMS_DATA_DIR/proof-search.json"
summary_path="$PMS_DATA_DIR/proof-bundle.summary.json"

cat >"$artifact_note_path" <<EOF_NOTE
# Proof Bundle Contract Note

- project: $project_name
- task: $task_title
- actor: $actor_name

This maintained flow verifies that PMS proof bundles include manual evidence and
recorded test runs, and that proof-bundle search returns the same task-level
summary data.
EOF_NOTE

echo "Running proof-bundle flow"
echo "  run_mode: $RUN_MODE"
echo "  data_dir: $PMS_DATA_DIR"
echo "  project: $project_name"

pms init >/dev/null
pms project create "$project_name" >/dev/null

pms task add "$project_name" "$task_title" >/dev/null
pms task list --project "$project_name" --format json >"$task_list_path"
task_id="$(
  py scripts/json_query.py find --file "$task_list_path" --items items --match-field title --match-value "$task_title" --get id
)"
project_list_path="$PMS_DATA_DIR/projects.json"
pms project list --format json >"$project_list_path"
project_id="$(
  py scripts/json_query.py find --file "$project_list_path" --items items --match-field name --match-value "$project_name" --get id
)"

if [[ -z "$task_id" || -z "$project_id" ]]; then
  echo "Proof-bundle flow failed: missing task or project ID." >&2
  exit 1
fi

pms task start "$task_id" --by "$actor_name" >/dev/null
pms task progress "$task_id" 50 "Attached initial proof inputs" --by "$actor_name" >/dev/null
pms task evidence add "$task_id" artifact "$artifact_note_path" --created-by "$actor_name" >/dev/null

started_at="$(date -u +"%Y-%m-%dT%H:%M:%S+00:00")"
finished_at="$started_at"

pms test server ensure-local --project-id "$project_id" --format json >/dev/null

pms test record \
  --server-id local \
  --status passed \
  --started-at "$started_at" \
  --finished-at "$finished_at" \
  --project-id "$project_id" \
  --task-id "$task_id" \
  --command "pytest -q tests/integration/test_cli.py -k proof_bundle" \
  --runner "proof-contract" \
  --stdout "proof stdout" \
  --stderr "" \
  --logs '{"log_path":"proof.log","lines":12}' \
  --artifacts '{"report":"proof-report.json","bundle":"bundle.tgz"}' \
  --format json >"$test_record_path"

test_run_id="$(py scripts/json_query.py path --file "$test_record_path" --get id)"
if [[ -z "$test_run_id" ]]; then
  echo "Proof-bundle flow failed: missing test run ID." >&2
  exit 1
fi

pms task evidence add "$task_id" test_run "$test_run_id" --created-by "$actor_name" >/dev/null
pms task evidence list "$task_id" --include-test-runs --include-output --format json >"$evidence_list_path"
pms task proof-bundle "$task_id" --include-output --include-logs --include-artifacts --format json >"$proof_bundle_path"
pms task proof-bundle-search \
  --task-id "$task_id" \
  --include-evidence \
  --include-test-runs \
  --include-output \
  --include-logs \
  --include-artifacts \
  --view trace \
  --format json >"$proof_search_path"

export PMS_PROOF_BUNDLE_PROJECT_ID="$project_id"
export PMS_PROOF_BUNDLE_PROJECT_NAME="$project_name"
export PMS_PROOF_BUNDLE_TASK_ID="$task_id"
export PMS_PROOF_BUNDLE_TASK_TITLE="$task_title"
export PMS_PROOF_BUNDLE_TEST_RUN_ID="$test_run_id"
export PMS_PROOF_BUNDLE_ARTIFACT_NOTE="$artifact_note_path"
export PMS_PROOF_BUNDLE_EVIDENCE_LIST="$evidence_list_path"
export PMS_PROOF_BUNDLE_JSON="$proof_bundle_path"
export PMS_PROOF_BUNDLE_SEARCH_JSON="$proof_search_path"
export PMS_PROOF_BUNDLE_SUMMARY="$summary_path"

py - <<'PY'
import json
import os
from pathlib import Path

from pms.utils.atomic_files import write_json_atomic

summary = {
    "project": {
        "id": os.environ["PMS_PROOF_BUNDLE_PROJECT_ID"],
        "name": os.environ["PMS_PROOF_BUNDLE_PROJECT_NAME"],
    },
    "task": {
        "id": os.environ["PMS_PROOF_BUNDLE_TASK_ID"],
        "title": os.environ["PMS_PROOF_BUNDLE_TASK_TITLE"],
    },
    "test_run_id": os.environ["PMS_PROOF_BUNDLE_TEST_RUN_ID"],
    "artifacts": {
        "artifact_note": os.environ["PMS_PROOF_BUNDLE_ARTIFACT_NOTE"],
        "task_list": os.environ["PMS_DATA_DIR"] + "/tasks.json",
        "evidence_list": os.environ["PMS_PROOF_BUNDLE_EVIDENCE_LIST"],
        "proof_bundle": os.environ["PMS_PROOF_BUNDLE_JSON"],
        "proof_search": os.environ["PMS_PROOF_BUNDLE_SEARCH_JSON"],
    },
}
write_json_atomic(Path(os.environ["PMS_PROOF_BUNDLE_SUMMARY"]), summary, encoding="utf-8")
PY

echo "Proof-bundle flow completed."
echo "  summary: $summary_path"
