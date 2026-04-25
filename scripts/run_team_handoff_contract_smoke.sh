#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/run_helpers.sh"

CONTRACT_TIMEOUT_SECONDS="${PMS_TEAM_HANDOFF_CONTRACT_TIMEOUT_SECONDS:-120}"
pms_setup_python_runtime "$ROOT_DIR"
pms_prepare_data_dir "$ROOT_DIR" "team-handoff-contract"

echo "Running team handoff contract smoke"
echo "  run_mode: $RUN_MODE"
echo "  data_dir: $PMS_DATA_DIR"
echo "  contract_timeout_seconds: $CONTRACT_TIMEOUT_SECONDS"

pms_run_contract_flow \
  "Team handoff contract smoke" \
  "$CONTRACT_TIMEOUT_SECONDS" \
  "$ROOT_DIR" \
  "$ROOT_DIR/scripts/run_team_handoff_flow.sh"

summary_path="$PMS_DATA_DIR/team-handoff.summary.json"
if [[ ! -s "$summary_path" ]]; then
  echo "Team handoff contract smoke failed: summary missing at $summary_path" >&2
  exit 1
fi

py - <<'PY'
import json
import os
from pathlib import Path

summary_path = Path(os.environ["PMS_DATA_DIR"]) / "team-handoff.summary.json"
summary = json.loads(summary_path.read_text())

organization = summary.get("organization")
if not isinstance(organization, dict):
    raise SystemExit(
        "Team handoff contract smoke failed: summary.organization must be an object."
    )
for key in ("name", "id"):
    if not organization.get(key):
        raise SystemExit(
            f"Team handoff contract smoke failed: organization.{key} is missing."
        )

projects = summary.get("projects")
if not isinstance(projects, dict):
    raise SystemExit(
        "Team handoff contract smoke failed: summary.projects must be an object."
    )
for project_key in ("build", "release"):
    project = projects.get(project_key)
    if not isinstance(project, dict):
        raise SystemExit(
            f"Team handoff contract smoke failed: projects.{project_key} must be an object."
        )
    for key in ("name", "id"):
        if not project.get(key):
            raise SystemExit(
                f"Team handoff contract smoke failed: projects.{project_key}.{key} is missing."
            )

tasks = summary.get("tasks")
if not isinstance(tasks, dict):
    raise SystemExit("Team handoff contract smoke failed: summary.tasks must be an object.")
for key in ("build_task_id", "release_task_id"):
    if not tasks.get(key):
        raise SystemExit(f"Team handoff contract smoke failed: tasks.{key} is missing.")

extension_ids = summary.get("extension_ids")
if not isinstance(extension_ids, dict):
    raise SystemExit(
        "Team handoff contract smoke failed: summary.extension_ids must be an object."
    )
for key in ("custom_field_id", "automation_rule_id", "queue_id"):
    if not extension_ids.get(key):
        raise SystemExit(
            f"Team handoff contract smoke failed: extension_ids.{key} is missing."
        )

artifacts = summary.get("artifacts")
if not isinstance(artifacts, dict):
    raise SystemExit(
        "Team handoff contract smoke failed: summary.artifacts must be an object."
    )
artifact_keys = (
    "organization_daily_summary",
    "release_project_daily_summary",
    "build_project_report",
    "release_project_report",
    "metrics_csv",
    "history_json",
    "queue_run_json",
)
for key in artifact_keys:
    value = artifacts.get(key)
    if not value:
        raise SystemExit(
            f"Team handoff contract smoke failed: artifacts.{key} is missing."
        )
    path = Path(value)
    if not path.is_file() or path.stat().st_size == 0:
        raise SystemExit(
            f"Team handoff contract smoke failed: artifact {key} missing or empty: {path}"
        )
PY

echo "Team handoff contract smoke completed."
echo "  summary: $summary_path"
