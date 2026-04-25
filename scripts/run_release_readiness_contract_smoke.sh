#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/run_helpers.sh"

CONTRACT_TIMEOUT_SECONDS="${PMS_RELEASE_READINESS_CONTRACT_TIMEOUT_SECONDS:-120}"
pms_setup_python_runtime "$ROOT_DIR"
pms_prepare_data_dir "$ROOT_DIR" "release-readiness-contract"

echo "Running release-readiness contract smoke"
echo "  run_mode: $RUN_MODE"
echo "  data_dir: $PMS_DATA_DIR"
echo "  contract_timeout_seconds: $CONTRACT_TIMEOUT_SECONDS"

pms_run_contract_flow \
  "Release-readiness contract smoke" \
  "$CONTRACT_TIMEOUT_SECONDS" \
  "$ROOT_DIR" \
  "$ROOT_DIR/scripts/run_release_readiness_flow.sh"

summary_path="$PMS_DATA_DIR/release-readiness.summary.json"
if [[ ! -s "$summary_path" ]]; then
  echo "Release-readiness contract smoke failed: summary missing at $summary_path" >&2
  exit 1
fi

py - <<'PY'
import json
import os
from pathlib import Path

summary_path = Path(os.environ["PMS_DATA_DIR"]) / "release-readiness.summary.json"
summary = json.loads(summary_path.read_text())

project = summary.get("project")
if not isinstance(project, dict):
    raise SystemExit(
        "Release-readiness contract smoke failed: summary.project must be an object."
    )
for key in ("name", "id"):
    if not project.get(key):
        raise SystemExit(
            f"Release-readiness contract smoke failed: project.{key} is missing."
        )

execution_ids = summary.get("execution_ids")
if not isinstance(execution_ids, dict):
    raise SystemExit(
        "Release-readiness contract smoke failed: summary.execution_ids must be an object."
    )
for key in (
    "plan_id",
    "goal_id",
    "objective_id",
    "notes_task_id",
    "smoke_task_id",
    "approval_task_id",
    "test_run_id",
):
    if not execution_ids.get(key):
        raise SystemExit(
            f"Release-readiness contract smoke failed: execution_ids.{key} is missing."
        )

extension_ids = summary.get("extension_ids")
if not isinstance(extension_ids, dict):
    raise SystemExit(
        "Release-readiness contract smoke failed: summary.extension_ids must be an object."
    )
for key in ("custom_field_id", "automation_rule_id", "queue_id"):
    if not extension_ids.get(key):
        raise SystemExit(
            f"Release-readiness contract smoke failed: extension_ids.{key} is missing."
        )

artifacts = summary.get("artifacts")
if not isinstance(artifacts, dict):
    raise SystemExit(
        "Release-readiness contract smoke failed: summary.artifacts must be an object."
    )
for key in (
    "bootstrap",
    "start_guide",
    "dashboard",
    "daily_summary",
    "project_report",
    "metrics_csv",
    "queue_run_json",
    "test_record_json",
    "test_show_json",
):
    value = artifacts.get(key)
    if not value:
        raise SystemExit(
            f"Release-readiness contract smoke failed: artifacts.{key} is missing."
        )
    path = Path(value)
    if not path.is_file() or path.stat().st_size == 0:
        raise SystemExit(
            f"Release-readiness contract smoke failed: artifact {key} missing or empty: {path}"
        )

next_steps = summary.get("next_steps")
if not isinstance(next_steps, dict):
    raise SystemExit(
        "Release-readiness contract smoke failed: summary.next_steps must be an object."
    )
for key in ("bootstrap", "start", "dashboard", "daily"):
    if not isinstance(next_steps.get(key), list) or not next_steps.get(key):
        raise SystemExit(
            f"Release-readiness contract smoke failed: next_steps.{key} must be a non-empty list."
        )
PY

echo "Release-readiness contract smoke completed."
echo "  summary: $summary_path"
