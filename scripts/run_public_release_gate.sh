#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

source "$ROOT_DIR/scripts/lib/run_helpers.sh"
pms_setup_python_runtime "$ROOT_DIR"
pms_use_isolated_direct_runtime

echo "Regenerating capabilities reference"
pms capabilities docs --output docs/CAPABILITIES_REFERENCE.md

echo "Regenerating API endpoint catalog"
py scripts/generate_api_endpoint_catalog.py --output docs/API_ENDPOINT_CATALOG.md

echo "Regenerating API response contracts"
py scripts/generate_api_response_contracts.py --output docs/API_RESPONSE_CONTRACTS.md

echo "Running docs runtime-truth audit"
py scripts/audit_docs_runtime_truth.py --check

echo "Running release version consistency audit"
py scripts/audit_release_version_consistency.py --check

echo "Running server deployment doc truth audit"
py scripts/audit_server_deployment_doc_truth.py --check

echo "Running local server surface truth audit"
py scripts/audit_local_server_surface_truth.py --check

echo "Running docs smoke"
"$ROOT_DIR/scripts/run_docs_smoke.sh"

echo "Running Ruff lint"
py -m ruff check .

echo "Running Ruff format check"
py -m ruff format --check .

echo "Running Rust client compile check"
cargo check --manifest-path client-rust/Cargo.toml

# These end-to-end wrappers launch heavyweight real subprocess flows and are
# more sensitive to host-level contention than the API/CLI/unit matrix.
# Keep them in the gate, but run them serially outside xdist so the gate stays
# deterministic on busy CI and local release-candidate machines.
serial_contract_smokes=(
  tests/integration/test_*contract_smoke.py
  tests/integration/test_distributed_audit_sequence.py
)

echo "Running full visible test suite"
pytest_args=(-x -vv -s -n 20)
for test_ref in "${serial_contract_smokes[@]}"; do
  pytest_args+=(--deselect "$test_ref")
done
py -m pytest "${pytest_args[@]}"

echo "Running serial contract smokes"
py -m pytest -x -vv -s "${serial_contract_smokes[@]}"

echo "Verifying public release checkpoint"
py scripts/verify_public_release_checkpoint.py --check

echo "Public release gate completed."
