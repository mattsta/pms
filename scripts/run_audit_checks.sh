#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  RUN_MODE="venv"
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
elif command -v uv >/dev/null 2>&1; then
  RUN_MODE="uv"
  PYTHON_BIN=""
elif command -v python3 >/dev/null 2>&1; then
  RUN_MODE="system"
  PYTHON_BIN="$(command -v python3)"
else
  echo "No supported Python runtime found (.venv/bin/python, uv, or python3)." >&2
  exit 1
fi

timestamp="$(date +"%Y%m%d-%H%M%S")"
if [[ -n "${PMS_DATA_DIR:-}" ]]; then
  data_dir="$PMS_DATA_DIR"
else
  mkdir -p "$ROOT_DIR/.tmp"
  data_dir="$(mktemp -d "$ROOT_DIR/.tmp/audit-checks-${timestamp}.XXXXXX")"
fi

export PMS_DATA_DIR="$data_dir"
export PMS_DATABASE_PATH="${PMS_DATABASE_PATH:-$PMS_DATA_DIR/pms.db}"
export PMS_LOG_DIR="${PMS_LOG_DIR:-$PMS_DATA_DIR/logs}"
export PMS_ENV_FILE="${PMS_ENV_FILE:-$PMS_DATA_DIR/.env}"
mkdir -p "$PMS_LOG_DIR"

py() {
  if [[ "$RUN_MODE" == "uv" ]]; then
    uv run python "$@"
  else
    "$PYTHON_BIN" "$@"
  fi
}

run_cmd() {
  local label="$1"
  shift
  echo "Running $label"
  "$@"
}

run_py() {
  local label="$1"
  shift
  echo "Running $label"
  py "$@"
}

readonly PREFLIGHT_STAGES=(
  "validate-docs-and-parity"
  "scenario-contract-smokes-a"
  "scenario-contract-smokes-b"
  "scenario-contract-smokes-c"
  "docs-discoverability-audits"
  "runtime-integrity-audits"
  "surface-parity-audits"
  "lifecycle-rollup-audits"
)
readonly ALL_STAGES=("${PREFLIGHT_STAGES[@]}" "full-test-suite")

print_usage() {
  cat <<'EOF'
Usage: ./scripts/run_audit_checks.sh [STAGE...]

Run maintained audit and contract-smoke stages.

Stage selectors:
  all                 Run every stage, including full-test-suite.
  all-preflight       Run every preflight stage, excluding full-test-suite.
  validate-docs-and-parity
  scenario-contract-smokes-a
  scenario-contract-smokes-b
  scenario-contract-smokes-c
  docs-discoverability-audits
  runtime-integrity-audits
  surface-parity-audits
  lifecycle-rollup-audits
  full-test-suite

Options:
  --list-stages       Print available stage names and exit.
  -h, --help          Show this help text and exit.

Examples:
  ./scripts/run_audit_checks.sh
  ./scripts/run_audit_checks.sh all-preflight
  ./scripts/run_audit_checks.sh validate-docs-and-parity docs-discoverability-audits
  PMS_AUDIT_SKIP_TESTS=1 ./scripts/run_audit_checks.sh full-test-suite
EOF
}

append_unique_stage() {
  local candidate="$1"
  local existing
  for existing in "${SELECTED_STAGES[@]:-}"; do
    if [[ "$existing" == "$candidate" ]]; then
      return 0
    fi
  done
  SELECTED_STAGES+=("$candidate")
}

run_stage() {
  local stage="$1"
  case "$stage" in
    validate-docs-and-parity)
      run_cmd "docs command smoke" "$ROOT_DIR/scripts/run_docs_smoke.sh"
      run_py "CLI parity audit" scripts/cli_parity_audit.py --check
      run_py "API/client parity audit" scripts/client_parity_audit.py --check
      run_cmd \
        "generator guard tests" \
        py -m pytest -q \
        tests/unit/test_api_endpoint_catalog_generator.py \
        tests/unit/test_api_reference_audit.py \
        tests/unit/test_api_reference_depth_audit.py \
        tests/unit/test_api_response_contract_generator.py \
        tests/integration/test_client_parity.py
      ;;
    scenario-contract-smokes-a)
      run_cmd "platform smoke flow" "$ROOT_DIR/scripts/run_demo_smoke.sh"
      run_cmd "drop-in growth contract smoke" "$ROOT_DIR/scripts/run_dropin_contract_smoke.sh"
      run_cmd "team handoff contract smoke" "$ROOT_DIR/scripts/run_team_handoff_contract_smoke.sh"
      run_cmd "incident response contract smoke" "$ROOT_DIR/scripts/run_incident_response_contract_smoke.sh"
      run_cmd "user start -> go -> observe contract smoke" "$ROOT_DIR/scripts/run_user_start_go_observe_contract_smoke.sh"
      ;;
    scenario-contract-smokes-b)
      run_cmd "release-readiness contract smoke" "$ROOT_DIR/scripts/run_release_readiness_contract_smoke.sh"
      run_cmd "operational-review contract smoke" "$ROOT_DIR/scripts/run_operational_review_contract_smoke.sh"
      run_cmd "backlog-triage contract smoke" "$ROOT_DIR/scripts/run_backlog_triage_contract_smoke.sh"
      run_cmd "portfolio-steering contract smoke" "$ROOT_DIR/scripts/run_portfolio_steering_contract_smoke.sh"
      run_cmd "agent-loop contract smoke" "$ROOT_DIR/scripts/run_agent_execution_loop_contract_smoke.sh"
      ;;
    scenario-contract-smokes-c)
      run_cmd "distributed-auth recovery contract smoke" "$ROOT_DIR/scripts/run_distributed_auth_recovery_contract_smoke.sh"
      run_cmd "distributed multiwriter contract smoke" bash "$ROOT_DIR/scripts/run_distributed_multiwriter_contract_smoke.sh"
      run_cmd "Rust degraded-runtime recovery contract smoke" bash "$ROOT_DIR/scripts/run_rust_degraded_runtime_recovery_contract_smoke.sh"
      run_cmd "network interop benchmark contract smoke" bash "$ROOT_DIR/scripts/run_network_interop_benchmark_contract_smoke.sh"
      run_cmd "proof-bundle contract smoke" bash "$ROOT_DIR/scripts/run_proof_bundle_contract_smoke.sh"
      run_cmd "authoring reliability smoke" bash "$ROOT_DIR/scripts/run_authoring_reliability_smoke.sh"
      run_cmd "task state consistency smoke" bash "$ROOT_DIR/scripts/run_task_state_consistency_smoke.sh"
      ;;
    docs-discoverability-audits)
      run_py "continuation quality audit" scripts/audit_continuation_quality.py --check
      run_py "scenario package audit" scripts/audit_scenario_packages.py --check
      run_py "paginated discoverability wrapper audit" scripts/audit_discoverability_wrappers.py --check
      run_py "command prefix template audit" scripts/audit_command_prefix_templates.py --check
      run_py "docs runtime-truth audit" scripts/audit_docs_runtime_truth.py --check
      run_py "graph discoverability audit" scripts/audit_graph_discoverability.py --check
      run_py "release version consistency audit" scripts/audit_release_version_consistency.py --check
      run_py "server deployment doc truth audit" scripts/audit_server_deployment_doc_truth.py --check
      ;;
    runtime-integrity-audits)
      run_py "runtime guard audit" scripts/audit_runtime_guards.py --check
      run_py "hierarchy edge authority audit" scripts/audit_hierarchy_edge_authority.py --check
      run_py "env isolation audit" scripts/audit_env_isolation.py --check
      run_py "planning state audit" scripts/audit_planning_state.py --check
      run_py "secret hygiene audit" scripts/audit_secret_hygiene.py --check
      run_py "service transaction boundary audit" scripts/audit_service_transaction_boundaries.py --check
      run_py "atomic artifact write audit" scripts/audit_atomic_artifact_writes.py --check
      run_py "local server surface truth audit" scripts/audit_local_server_surface_truth.py --check
      run_py "actor reference integrity audit" scripts/audit_actor_reference_integrity.py --check
      run_py "actor surface truth audit" scripts/audit_actor_surface_truth.py --check
      run_py "actor workload math audit" scripts/audit_actor_workload_math.py --check
      ;;
    surface-parity-audits)
      run_py "MCP tool parity audit" scripts/audit_mcp_tool_parity.py --check
      run_py "visibility population audit" scripts/audit_visibility_population_contracts.py --check
      run_py "CLI JSON mutation parity audit" scripts/audit_cli_json_mutation_parity.py
      run_py "CLI JSON output rendering audit" scripts/audit_cli_json_output_rendering.py --check
      run_py "CLI TTY table contract audit" scripts/audit_cli_tty_table_contracts.py --check
      run_py "CLI text summary contract audit" scripts/audit_cli_text_summary_contracts.py --check
      run_py "CLI interactive chooser contract audit" scripts/audit_cli_interactive_chooser_contracts.py --check
      run_py "CLI recent-terminal summary contract audit" scripts/audit_cli_recent_terminal_summary_contracts.py --check
      run_py "CLI option parity audit" scripts/audit_cli_option_parity.py --check
      run_py "maintained client operator surface contract audit" scripts/audit_client_operator_surface_contracts.py --check
      run_py "dynamic maintained client operator payload parity audit" scripts/audit_client_operator_payload_parity.py --check
      run_py "dynamic maintained client lifecycle list payload parity audit" scripts/audit_client_lifecycle_list_payload_parity.py --check
      run_py "maintained client lifecycle list source-contract audit" scripts/audit_client_lifecycle_list_surface_contracts.py --check
      run_py "CLI surface contract audit" scripts/audit_cli_surface_contracts.py --check
      run_cmd "Rust client parity smoke" "$ROOT_DIR/scripts/run_rust_client_parity_smoke.sh"
      ;;
    lifecycle-rollup-audits)
      run_py "MCP project lifecycle contract audit" scripts/audit_mcp_project_lifecycle_contracts.py --check
      run_py "MCP goal lifecycle contract audit" scripts/audit_mcp_goal_lifecycle_contracts.py --check
      run_py "MCP objective lifecycle contract audit" scripts/audit_mcp_objective_lifecycle_contracts.py --check
      run_py "MCP key result lifecycle contract audit" scripts/audit_mcp_key_result_lifecycle_contracts.py --check
      run_py "CLI goal lifecycle contract audit" scripts/audit_cli_goal_lifecycle_contracts.py --check
      run_py "CLI objective lifecycle contract audit" scripts/audit_cli_objective_lifecycle_contracts.py --check
      run_py "CLI key result lifecycle contract audit" scripts/audit_cli_key_result_lifecycle_contracts.py --check
      run_py "API project lifecycle contract audit" scripts/audit_api_project_lifecycle_contracts.py --check
      run_py "API goal lifecycle contract audit" scripts/audit_api_goal_lifecycle_contracts.py --check
      run_py "API objective lifecycle contract audit" scripts/audit_api_objective_lifecycle_contracts.py --check
      run_py "API key result lifecycle contract audit" scripts/audit_api_key_result_lifecycle_contracts.py --check
      run_py "execution-backed rollup audit" scripts/audit_execution_backed_rollups.py --check
      run_py "goal execution scope audit" scripts/audit_goal_execution_scope.py --check
      run_py "graph timestamp rollup audit" scripts/audit_graph_timestamp_rollups.py --check
      run_py "graph report surface audit" scripts/audit_graph_report_surface.py --check
      run_py "graph summary surface truth audit" scripts/audit_graph_summary_surface_truth.py --check
      run_py "cross-surface project lifecycle contract audit" scripts/audit_cross_surface_project_lifecycle_contracts.py --check
      run_py "cross-surface lifecycle aggregate source contract audit" scripts/audit_cross_surface_lifecycle_aggregate_source_contracts.py --check
      run_py "cross-surface operator dashboard contract audit" scripts/audit_cross_surface_operator_dashboard_contracts.py --check
      ;;
    full-test-suite)
      if [[ "${PMS_AUDIT_SKIP_TESTS:-0}" != "1" ]]; then
        run_cmd "full test suite" py -m pytest -q
      else
        echo "Skipping full test suite (PMS_AUDIT_SKIP_TESTS=1)"
      fi
      ;;
    *)
      echo "Unknown audit stage: $stage" >&2
      return 2
      ;;
  esac
}

REQUESTED_STAGES=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --list-stages)
      printf '%s\n' "${ALL_STAGES[@]}"
      exit 0
      ;;
    -h|--help)
      print_usage
      exit 0
      ;;
    all|all-preflight|validate-docs-and-parity|scenario-contract-smokes-a|scenario-contract-smokes-b|scenario-contract-smokes-c|docs-discoverability-audits|runtime-integrity-audits|surface-parity-audits|lifecycle-rollup-audits|full-test-suite)
      REQUESTED_STAGES+=("$1")
      ;;
    *)
      echo "Unknown argument: $1" >&2
      print_usage >&2
      exit 2
      ;;
  esac
  shift
done

if [[ "${#REQUESTED_STAGES[@]}" -eq 0 ]]; then
  REQUESTED_STAGES=("all")
fi

SELECTED_STAGES=()
for requested_stage in "${REQUESTED_STAGES[@]}"; do
  case "$requested_stage" in
    all)
      for stage in "${ALL_STAGES[@]}"; do
        append_unique_stage "$stage"
      done
      ;;
    all-preflight)
      for stage in "${PREFLIGHT_STAGES[@]}"; do
        append_unique_stage "$stage"
      done
      ;;
    *)
      append_unique_stage "$requested_stage"
      ;;
  esac
done

echo "Selected audit stages: ${SELECTED_STAGES[*]}"
for selected_stage in "${SELECTED_STAGES[@]}"; do
  run_stage "$selected_stage"
done

echo "Audit checks completed."
