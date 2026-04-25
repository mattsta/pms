#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

echo "Running complete system integration checks"
echo "  - smoke demo"
echo "  - parity audits"
echo "  - regression guard"

"$ROOT_DIR/scripts/run_demo_suite.sh"

echo "Complete system integration checks passed."
