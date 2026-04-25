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

pms() {
  if [[ "$RUN_MODE" == "uv" ]]; then
    uv run pms "$@"
  else
    "$PYTHON_BIN" -m pms "$@"
  fi
}

py() {
  if [[ "$RUN_MODE" == "uv" ]]; then
    uv run python "$@"
  else
    "$PYTHON_BIN" "$@"
  fi
}

timestamp="$(date +"%Y%m%d-%H%M%S")"
if [[ -n "${PMS_DATA_DIR:-}" ]]; then
  data_dir="$PMS_DATA_DIR"
else
  mkdir -p "$ROOT_DIR/.tmp"
  data_dir="$(mktemp -d "$ROOT_DIR/.tmp/docs-smoke-${timestamp}.XXXXXX")"
fi

export PMS_DATA_DIR="$data_dir"
export PMS_DATABASE_PATH="${PMS_DATABASE_PATH:-$PMS_DATA_DIR/pms.db}"
export PMS_LOG_DIR="${PMS_LOG_DIR:-$PMS_DATA_DIR/logs}"
export PMS_ENV_FILE="${PMS_ENV_FILE:-$PMS_DATA_DIR/.env}"
mkdir -p "$PMS_DATA_DIR" "$PMS_LOG_DIR"

echo "Running docs command smoke"
echo "  run_mode: $RUN_MODE"
echo "  data_dir: $PMS_DATA_DIR"

# Validate top-level command surfaces used throughout docs.
pms --help >/dev/null
pms start --help >/dev/null
pms quickstart --help >/dev/null
pms capabilities --help >/dev/null
pms capabilities docs --help >/dev/null
pms work daily --help >/dev/null
pms loop setup --help >/dev/null
pms workflow align --help >/dev/null
pms auth init --help >/dev/null
pms serve --help >/dev/null
py scripts/agent_hooks/pms_stop_audit.py --help >/dev/null

# Validate WEB_API parity/documentation integrity.
web_api_doc="$ROOT_DIR/docs/WEB_API.md"
parity_heading_count="$(rg -c '^## API vs CLI vs MCP Parity Matrix \(Appendix\)$' "$web_api_doc")"
if [[ "$parity_heading_count" -ne 1 ]]; then
  echo "Docs smoke failed: expected exactly one parity appendix heading in $web_api_doc (found $parity_heading_count)." >&2
  exit 1
fi

if rg -n --fixed-strings \
  -e "pms auth show" \
  -e "pms auth update" \
  -e "pms auth delete" \
  -e "pms auth rotate" \
  -e "/auth/keys/<id>/rotate" \
  "$web_api_doc" >/dev/null; then
  echo "Docs smoke failed: found stale auth command/endpoint references in $web_api_doc." >&2
  exit 1
fi

# Validate checked-in API endpoint catalog is in sync with runtime route inventory.
api_catalog_doc="$ROOT_DIR/docs/API_ENDPOINT_CATALOG.md"
py scripts/generate_api_endpoint_catalog.py --check --output "$api_catalog_doc" >/dev/null

# Validate checked-in API response contracts are in sync with live OpenAPI.
api_response_contracts_doc="$ROOT_DIR/docs/API_RESPONSE_CONTRACTS.md"
py scripts/generate_api_response_contracts.py --check --output "$api_response_contracts_doc" >/dev/null

# Validate API reference remains rich/manual (not reduced to thin inventory).
api_reference_doc="$ROOT_DIR/docs/API_REFERENCE.md"
if ! rg -q '^## Endpoints$' "$api_reference_doc"; then
  echo "Docs smoke failed: API reference missing '## Endpoints' section." >&2
  exit 1
fi
api_http_block_count="$(rg -c '^```http$' "$api_reference_doc")"
if [[ "$api_http_block_count" -lt 50 ]]; then
  echo "Docs smoke failed: API reference appears too sparse (only $api_http_block_count http example blocks)." >&2
  exit 1
fi

# Audit API reference coverage against live OpenAPI routes without rewriting docs.
api_reference_allow_missing="${PMS_API_REFERENCE_ALLOWED_MISSING:-0}"
api_reference_allow_extra="${PMS_API_REFERENCE_ALLOWED_EXTRA:-0}"
api_reference_allow_missing_body_examples="${PMS_API_REFERENCE_ALLOWED_MISSING_BODY_EXAMPLES:-0}"
py scripts/audit_api_reference.py \
  --api-reference "$api_reference_doc" \
  --check \
  --allow-missing "$api_reference_allow_missing" \
  --allow-extra "$api_reference_allow_extra" \
  --allow-missing-body-examples "$api_reference_allow_missing_body_examples" \
  --max-list 40

api_reference_depth_allow_uncovered="${PMS_API_REFERENCE_DEPTH_ALLOWED_UNCOVERED:-0}"
api_reference_depth_min_local_percent="${PMS_API_REFERENCE_DEPTH_MIN_LOCAL_PERCENT:-30}"
py scripts/audit_api_reference_depth.py \
  --api-reference "$api_reference_doc" \
  --contracts "$api_response_contracts_doc" \
  --check \
  --allow-uncovered "$api_reference_depth_allow_uncovered" \
  --min-local-percent "$api_reference_depth_min_local_percent" \
  --max-list 40

# Validate discoverability wrappers for paginated route payloads.
py scripts/audit_discoverability_wrappers.py --check --max-list 40

# Validate discoverability links for endpoint catalog across entry docs.
for discover_doc in README.md docs/WEB_API.md docs/IMMEDIATE_START_GO.md; do
  if ! rg -q --fixed-strings "docs/API_ENDPOINT_CATALOG.md" "$ROOT_DIR/$discover_doc"; then
    echo "Docs smoke failed: missing endpoint catalog link in $discover_doc." >&2
    exit 1
  fi
  if ! rg -q --fixed-strings "docs/API_RESPONSE_CONTRACTS.md" "$ROOT_DIR/$discover_doc"; then
    echo "Docs smoke failed: missing API response contracts link in $discover_doc." >&2
    exit 1
  fi
  if ! rg -q --fixed-strings "docs/API_REFERENCE.md" "$ROOT_DIR/$discover_doc"; then
    echo "Docs smoke failed: missing API reference link in $discover_doc." >&2
    exit 1
  fi
done

# Validate drop-in growth discoverability across entry docs.
for discover_doc in README.md GETTING_STARTED.md docs/IMMEDIATE_START_GO.md; do
  if ! rg -q --fixed-strings "./scripts/run_dropin_start_go_extend_grow.sh" "$ROOT_DIR/$discover_doc"; then
    echo "Docs smoke failed: missing drop-in growth script link in $discover_doc." >&2
    exit 1
  fi
  if ! rg -q --fixed-strings "./scripts/run_dropin_contract_smoke.sh" "$ROOT_DIR/$discover_doc"; then
    echo "Docs smoke failed: missing drop-in contract smoke link in $discover_doc." >&2
    exit 1
  fi
  if ! rg -q --fixed-strings "examples/real_world/README.md" "$ROOT_DIR/$discover_doc"; then
    echo "Docs smoke failed: missing drop-in growth guide link in $discover_doc." >&2
    exit 1
  fi
  if ! rg -q --fixed-strings "examples/real_world/dropin.env.example" "$ROOT_DIR/$discover_doc"; then
    echo "Docs smoke failed: missing real-world env example link in $discover_doc." >&2
    exit 1
  fi
done

# Validate agent harness integration discoverability across entry docs.
for discover_doc in README.md GETTING_STARTED.md docs/DOCUMENTATION_MAP.md; do
  if ! rg -q --fixed-strings "AGENT_INTEGRATION_GUIDE.md" "$ROOT_DIR/$discover_doc"; then
    echo "Docs smoke failed: missing agent integration guide link in $discover_doc." >&2
    exit 1
  fi
done

if ! rg -q --fixed-strings "scripts/agent_hooks/pms_stop_audit.py" "$ROOT_DIR/docs/AGENT_INTEGRATION_GUIDE.md"; then
  echo "Docs smoke failed: agent integration guide missing stop-audit helper reference." >&2
  exit 1
fi

# Validate team handoff discoverability across entry docs.
for discover_doc in README.md GETTING_STARTED.md docs/IMMEDIATE_START_GO.md; do
  if ! rg -q --fixed-strings "./scripts/run_team_handoff_flow.sh" "$ROOT_DIR/$discover_doc"; then
    echo "Docs smoke failed: missing team handoff flow script link in $discover_doc." >&2
    exit 1
  fi
  if ! rg -q --fixed-strings "./scripts/run_team_handoff_contract_smoke.sh" "$ROOT_DIR/$discover_doc"; then
    echo "Docs smoke failed: missing team handoff contract smoke link in $discover_doc." >&2
    exit 1
  fi
  if ! rg -q --fixed-strings "examples/real_world/README.md" "$ROOT_DIR/$discover_doc"; then
    echo "Docs smoke failed: missing team handoff guide link in $discover_doc." >&2
    exit 1
  fi
  if ! rg -q --fixed-strings "examples/real_world/team_handoff.env.example" "$ROOT_DIR/$discover_doc"; then
    echo "Docs smoke failed: missing team handoff env example link in $discover_doc." >&2
    exit 1
  fi
done

# Validate incident response discoverability across entry docs.
for discover_doc in README.md GETTING_STARTED.md docs/IMMEDIATE_START_GO.md; do
  if ! rg -q --fixed-strings "./scripts/run_incident_response_flow.sh" "$ROOT_DIR/$discover_doc"; then
    echo "Docs smoke failed: missing incident response flow script link in $discover_doc." >&2
    exit 1
  fi
  if ! rg -q --fixed-strings "./scripts/run_incident_response_contract_smoke.sh" "$ROOT_DIR/$discover_doc"; then
    echo "Docs smoke failed: missing incident contract smoke link in $discover_doc." >&2
    exit 1
  fi
  if ! rg -q --fixed-strings "examples/real_world/README.md" "$ROOT_DIR/$discover_doc"; then
    echo "Docs smoke failed: missing incident guide link in $discover_doc." >&2
    exit 1
  fi
  if ! rg -q --fixed-strings "examples/real_world/incident_response.env.example" "$ROOT_DIR/$discover_doc"; then
    echo "Docs smoke failed: missing incident env example link in $discover_doc." >&2
    exit 1
  fi
done

# Validate user start->go->observe discoverability across entry docs.
for discover_doc in README.md GETTING_STARTED.md docs/IMMEDIATE_START_GO.md; do
  if ! rg -q --fixed-strings "./scripts/run_user_start_go_observe_flow.sh" "$ROOT_DIR/$discover_doc"; then
    echo "Docs smoke failed: missing user start-go-observe flow script link in $discover_doc." >&2
    exit 1
  fi
  if ! rg -q --fixed-strings "./scripts/run_user_start_go_observe_contract_smoke.sh" "$ROOT_DIR/$discover_doc"; then
    echo "Docs smoke failed: missing user start-go-observe contract smoke link in $discover_doc." >&2
    exit 1
  fi
  if ! rg -q --fixed-strings "examples/real_world/README.md" "$ROOT_DIR/$discover_doc"; then
    echo "Docs smoke failed: missing user start-go-observe guide link in $discover_doc." >&2
    exit 1
  fi
  if ! rg -q --fixed-strings "examples/real_world/user_start_go_observe.env.example" "$ROOT_DIR/$discover_doc"; then
    echo "Docs smoke failed: missing user start-go-observe env example link in $discover_doc." >&2
    exit 1
  fi
done

# Validate operational-review discoverability across entry docs.
for discover_doc in README.md GETTING_STARTED.md docs/IMMEDIATE_START_GO.md; do
  if ! rg -q --fixed-strings "./scripts/run_operational_review_flow.sh" "$ROOT_DIR/$discover_doc"; then
    echo "Docs smoke failed: missing operational-review flow script link in $discover_doc." >&2
    exit 1
  fi
  if ! rg -q --fixed-strings "./scripts/run_operational_review_contract_smoke.sh" "$ROOT_DIR/$discover_doc"; then
    echo "Docs smoke failed: missing operational-review contract smoke link in $discover_doc." >&2
    exit 1
  fi
  if ! rg -q --fixed-strings "examples/real_world/README.md" "$ROOT_DIR/$discover_doc"; then
    echo "Docs smoke failed: missing operational-review guide link in $discover_doc." >&2
    exit 1
  fi
  if ! rg -q --fixed-strings "examples/real_world/operational_review.env.example" "$ROOT_DIR/$discover_doc"; then
    echo "Docs smoke failed: missing operational-review env example link in $discover_doc." >&2
    exit 1
  fi
done

# Validate backlog-triage discoverability across entry docs.
for discover_doc in README.md GETTING_STARTED.md docs/IMMEDIATE_START_GO.md; do
  if ! rg -q --fixed-strings "./scripts/run_backlog_triage_flow.sh" "$ROOT_DIR/$discover_doc"; then
    echo "Docs smoke failed: missing backlog-triage flow script link in $discover_doc." >&2
    exit 1
  fi
  if ! rg -q --fixed-strings "./scripts/run_backlog_triage_contract_smoke.sh" "$ROOT_DIR/$discover_doc"; then
    echo "Docs smoke failed: missing backlog-triage contract smoke link in $discover_doc." >&2
    exit 1
  fi
  if ! rg -q --fixed-strings "examples/real_world/README.md" "$ROOT_DIR/$discover_doc"; then
    echo "Docs smoke failed: missing backlog-triage guide link in $discover_doc." >&2
    exit 1
  fi
  if ! rg -q --fixed-strings "examples/real_world/backlog_triage.env.example" "$ROOT_DIR/$discover_doc"; then
    echo "Docs smoke failed: missing backlog-triage env example link in $discover_doc." >&2
    exit 1
  fi
done

# Validate portfolio-steering discoverability across entry docs.
for discover_doc in README.md GETTING_STARTED.md docs/IMMEDIATE_START_GO.md; do
  if ! rg -q --fixed-strings "./scripts/run_portfolio_steering_flow.sh" "$ROOT_DIR/$discover_doc"; then
    echo "Docs smoke failed: missing portfolio-steering flow script link in $discover_doc." >&2
    exit 1
  fi
  if ! rg -q --fixed-strings "./scripts/run_portfolio_steering_contract_smoke.sh" "$ROOT_DIR/$discover_doc"; then
    echo "Docs smoke failed: missing portfolio-steering contract smoke link in $discover_doc." >&2
    exit 1
  fi
  if ! rg -q --fixed-strings "examples/real_world/README.md" "$ROOT_DIR/$discover_doc"; then
    echo "Docs smoke failed: missing portfolio-steering guide link in $discover_doc." >&2
    exit 1
  fi
  if ! rg -q --fixed-strings "examples/real_world/portfolio_steering.env.example" "$ROOT_DIR/$discover_doc"; then
    echo "Docs smoke failed: missing portfolio-steering env example link in $discover_doc." >&2
    exit 1
  fi
done

# Validate agent-loop discoverability across entry docs.
for discover_doc in README.md GETTING_STARTED.md docs/IMMEDIATE_START_GO.md; do
  if ! rg -q --fixed-strings "./scripts/run_agent_execution_loop_flow.sh" "$ROOT_DIR/$discover_doc"; then
    echo "Docs smoke failed: missing agent-loop flow script link in $discover_doc." >&2
    exit 1
  fi
  if ! rg -q --fixed-strings "./scripts/run_agent_execution_loop_contract_smoke.sh" "$ROOT_DIR/$discover_doc"; then
    echo "Docs smoke failed: missing agent-loop contract smoke link in $discover_doc." >&2
    exit 1
  fi
  if ! rg -q --fixed-strings "examples/real_world/README.md" "$ROOT_DIR/$discover_doc"; then
    echo "Docs smoke failed: missing agent-loop guide link in $discover_doc." >&2
    exit 1
  fi
  if ! rg -q --fixed-strings "examples/real_world/agent_execution_loop.env.example" "$ROOT_DIR/$discover_doc"; then
    echo "Docs smoke failed: missing agent-loop env example link in $discover_doc." >&2
    exit 1
  fi
done

# Validate version consistency across CLI, introspection, and API app metadata.
cli_version="$(
  pms version | py -c \
    'import re,sys; text=sys.stdin.read(); m=re.search(r"Version:\s*(\S+)", text); print(m.group(1) if m else "")'
)"
caps_version="$(
  pms capabilities info -f json | py -c \
    'import json,sys; print(json.load(sys.stdin).get("version", ""))'
)"

if [[ -z "$cli_version" || -z "$caps_version" ]]; then
  echo "Docs smoke failed: could not resolve CLI/capabilities versions." >&2
  exit 1
fi

if [[ "$cli_version" != "$caps_version" ]]; then
  echo "Docs smoke failed: version mismatch CLI=$cli_version capabilities=$caps_version" >&2
  exit 1
fi

py - <<'PY'
from pms import __version__
from pms.api.app import app

if app.version != __version__:
    raise SystemExit(
        f"Docs smoke failed: API app version mismatch app={app.version} package={__version__}"
    )
PY

# Validate documentation generation command.
cap_docs_path="$PMS_DATA_DIR/capabilities-reference.md"
pms capabilities docs --output "$cap_docs_path" >/dev/null
if [[ ! -s "$cap_docs_path" ]]; then
  echo "Docs smoke failed: capabilities documentation file was not generated." >&2
  exit 1
fi

echo "Docs smoke completed successfully."
echo "  version: $cli_version"
echo "  generated_capabilities_doc: $cap_docs_path"
