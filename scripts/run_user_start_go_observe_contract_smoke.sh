#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/run_helpers.sh"

CONTRACT_TIMEOUT_SECONDS="${PMS_USER_START_GO_OBSERVE_CONTRACT_TIMEOUT_SECONDS:-120}"
pms_setup_python_runtime "$ROOT_DIR"
pms_prepare_data_dir "$ROOT_DIR" "user-contract"

echo "Running user start -> go -> observe contract smoke"
echo "  run_mode: $RUN_MODE"
echo "  data_dir: $PMS_DATA_DIR"
echo "  contract_timeout_seconds: $CONTRACT_TIMEOUT_SECONDS"

pms_run_contract_flow \
  "User start -> go -> observe contract smoke" \
  "$CONTRACT_TIMEOUT_SECONDS" \
  "$ROOT_DIR" \
  "$ROOT_DIR/scripts/run_user_start_go_observe_flow.sh"

summary_path="$PMS_DATA_DIR/user-start.summary.json"
if [[ ! -s "$summary_path" ]]; then
  echo "User flow contract smoke failed: summary missing at $summary_path" >&2
  exit 1
fi

py - <<'PY'
import json
import os
from pathlib import Path

from scripts.contract_assertions import canonical_cli_command, matches_canonical_cli_command

summary_path = Path(os.environ["PMS_DATA_DIR"]) / "user-start.summary.json"
summary = json.loads(summary_path.read_text())

project = summary.get("project")
if not isinstance(project, dict):
    raise SystemExit("Contract failed: summary.project must be an object.")
for key in ("name", "id"):
    if not project.get(key):
        raise SystemExit(f"Contract failed: project.{key} is missing.")

task = summary.get("task")
if not isinstance(task, dict):
    raise SystemExit("Contract failed: summary.task must be an object.")
for key in ("title", "id"):
    if not task.get(key):
        raise SystemExit(f"Contract failed: task.{key} is missing.")

artifacts = summary.get("artifacts")
if not isinstance(artifacts, dict):
    raise SystemExit("Contract failed: summary.artifacts must be an object.")
for key in ("start_guide", "ready_tasks", "dashboard", "daily_summary"):
    value = artifacts.get(key)
    if not value:
        raise SystemExit(f"Contract failed: artifacts.{key} is missing.")
    artifact_path = Path(value)
    if not artifact_path.is_file() or artifact_path.stat().st_size == 0:
        raise SystemExit(f"Contract failed: artifact missing/empty: {artifact_path}")

next_steps = summary.get("next_steps")
if not isinstance(next_steps, dict):
    raise SystemExit("Contract failed: summary.next_steps must be an object.")
for key in ("guide", "ready", "dashboard", "daily"):
    value = next_steps.get(key)
    if not isinstance(value, list):
        raise SystemExit(f"Contract failed: next_steps.{key} must be a list.")

links = summary.get("links")
if not isinstance(links, dict):
    raise SystemExit("Contract failed: summary.links must be an object.")
for key in ("guide", "ready", "dashboard", "daily"):
    value = links.get(key)
    if not isinstance(value, dict):
        raise SystemExit(f"Contract failed: links.{key} must be an object.")

guide_payload = json.loads(Path(artifacts["start_guide"]).read_text())
if not isinstance(guide_payload.get("links"), dict):
    raise SystemExit("Contract failed: start guide must include links.")
if not isinstance(guide_payload.get("next_steps"), list):
    raise SystemExit("Contract failed: start guide must include next_steps list.")

dashboard_payload = json.loads(Path(artifacts["dashboard"]).read_text())
if not isinstance(dashboard_payload.get("links"), dict):
    raise SystemExit("Contract failed: dashboard must include links.")
if not isinstance(dashboard_payload.get("next_steps"), list):
    raise SystemExit("Contract failed: dashboard must include next_steps list.")

daily_payload = json.loads(Path(artifacts["daily_summary"]).read_text())
if not isinstance(daily_payload.get("links"), dict):
    raise SystemExit("Contract failed: daily summary must include links.")
if not isinstance(daily_payload.get("next_steps"), list):
    raise SystemExit("Contract failed: daily summary must include next_steps list.")

ready_payload = json.loads(Path(artifacts["ready_tasks"]).read_text())
if not isinstance(ready_payload, dict):
    raise SystemExit("Contract failed: ready tasks payload must be an object wrapper.")
if not isinstance(ready_payload.get("items"), list):
    raise SystemExit("Contract failed: ready tasks payload must expose items[].")
if not isinstance(ready_payload.get("links"), dict):
    raise SystemExit("Contract failed: ready tasks payload must include links.")
if not isinstance(ready_payload.get("next_steps"), list):
    raise SystemExit("Contract failed: ready tasks payload must include next_steps.")
ready_items = ready_payload["items"]
if ready_items:
    first_ready = ready_items[0]
    if not isinstance(first_ready, dict):
        raise SystemExit("Contract failed: first ready task must be an object.")
    first_ready_links = first_ready.get("links")
    if not isinstance(first_ready_links, dict):
        raise SystemExit("Contract failed: first ready task must include links.")
    if not matches_canonical_cli_command(first_ready_links.get("guide"), "start --format json"):
        raise SystemExit("Contract failed: ready task links.guide mismatch.")
    if not str(first_ready_links.get("self", "")).startswith(canonical_cli_command("task show ")):
        raise SystemExit("Contract failed: first ready task links.self mismatch.")
PY

echo "User start -> go -> observe contract smoke completed."
echo "  summary: $summary_path"
