#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/run_helpers.sh"

CONTRACT_TIMEOUT_SECONDS="${PMS_INCIDENT_RESPONSE_CONTRACT_TIMEOUT_SECONDS:-$(pms_parallel_headroom_value 180 300)}"
pms_setup_python_runtime "$ROOT_DIR"
pms_prepare_data_dir "$ROOT_DIR" "incident-contract"

echo "Running incident response contract smoke"
echo "  run_mode: $RUN_MODE"
echo "  data_dir: $PMS_DATA_DIR"
echo "  contract_timeout_seconds: $CONTRACT_TIMEOUT_SECONDS"

pms_run_contract_flow \
  "Incident response contract smoke" \
  "$CONTRACT_TIMEOUT_SECONDS" \
  "$ROOT_DIR" \
  "$ROOT_DIR/scripts/run_incident_response_flow.sh"

summary_path="$PMS_DATA_DIR/incident.summary.json"
if [[ ! -s "$summary_path" ]]; then
  echo "Incident contract smoke failed: summary missing at $summary_path" >&2
  exit 1
fi

py - <<'PY'
import json
import os
from pathlib import Path

summary_path = Path(os.environ["PMS_DATA_DIR"]) / "incident.summary.json"
summary = json.loads(summary_path.read_text())

project = summary.get("project")
if not isinstance(project, dict):
    raise SystemExit(
        "Incident contract smoke failed: summary.project must be an object."
    )
for key in ("name", "id"):
    if not project.get(key):
        raise SystemExit(f"Incident contract smoke failed: project.{key} is missing.")

task_ids = summary.get("task_ids")
if not isinstance(task_ids, dict):
    raise SystemExit(
        "Incident contract smoke failed: summary.task_ids must be an object."
    )
for key in ("triage", "mitigation", "comms", "postmortem"):
    if not task_ids.get(key):
        raise SystemExit(f"Incident contract smoke failed: task_ids.{key} is missing.")

extension_ids = summary.get("extension_ids")
if not isinstance(extension_ids, dict):
    raise SystemExit(
        "Incident contract smoke failed: summary.extension_ids must be an object."
    )
for key in ("custom_field_id", "automation_rule_id", "queue_id"):
    if not extension_ids.get(key):
        raise SystemExit(
            f"Incident contract smoke failed: extension_ids.{key} is missing."
        )

artifacts = summary.get("artifacts")
if not isinstance(artifacts, dict):
    raise SystemExit(
        "Incident contract smoke failed: summary.artifacts must be an object."
    )
artifact_keys = (
    "daily_summary",
    "project_report",
    "history_json",
    "metrics_csv",
    "queue_run_json",
)
for key in artifact_keys:
    value = artifacts.get(key)
    if not value:
        raise SystemExit(
            f"Incident contract smoke failed: artifacts.{key} is missing."
        )
    path = Path(value)
    if not path.is_file() or path.stat().st_size == 0:
        raise SystemExit(
            f"Incident contract smoke failed: artifact {key} missing or empty: {path}"
        )
PY

echo "Incident response contract smoke completed."
echo "  summary: $summary_path"
