#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/lib/run_helpers.sh"

BENCH_LIMIT="${PMS_NETWORK_INTEROP_BENCHMARK_LIMIT:-25}"
BENCH_REPETITIONS="${PMS_NETWORK_INTEROP_BENCHMARK_REPETITIONS:-2}"
ARTIFACT_ROOT="${PMS_NETWORK_INTEROP_ARTIFACT_ROOT:-$ROOT_DIR/artifacts/network_interop}"

pms_setup_python_runtime "$ROOT_DIR"
pms_use_isolated_direct_runtime
pms_prepare_data_dir "$ROOT_DIR" "network-interop-benchmark"

mkdir -p "$ARTIFACT_ROOT"

timestamp="$(date +"%Y%m%d-%H%M%S")"
bundle_dir="$ARTIFACT_ROOT/$timestamp"
latest_dir="$ARTIFACT_ROOT/latest"
bench_dir="$PMS_DATA_DIR/bench"
mkdir -p "$bundle_dir" "$bench_dir"

echo "Running network interop benchmark bundle"
echo "  run_mode: $RUN_MODE"
echo "  data_dir: $PMS_DATA_DIR"
echo "  artifact_dir: $bundle_dir"
echo "  limit: $BENCH_LIMIT"
echo "  repetitions: $BENCH_REPETITIONS"

quickstart_file="$PMS_DATA_DIR/quickstart.json"
pms quickstart \
  --defaults \
  --org "Network Interop Org $timestamp" \
  --product "Network Interop Product $timestamp" \
  --project "Network Interop Benchmark Project $timestamp" \
  --task "Warm Benchmark Queue" \
  --task "Benchmark Plan Readback" \
  --create-plan \
  --create-rollups \
  --format json \
  >"$quickstart_file"

read -r project_id project_name <<EOF
$(py - <<'PY' "$quickstart_file"
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
project = payload["artifacts_created"]["project"]
print(project["id"], project["name"])
PY
)
EOF

for index in $(seq 1 12); do
  pms task add "$project_name" "Benchmark Artifact Task $index" --format json >/dev/null
done

bash "$ROOT_DIR/scripts/run_rust_server_benchmark.sh" \
  --project-id "$project_id" \
  --report-dir "$bench_dir" \
  --limit "$BENCH_LIMIT" \
  --repetitions "$BENCH_REPETITIONS" \
  >"$PMS_DATA_DIR/benchmark-report.stdout.json"

report_file="$(ls -1t "$bench_dir"/rust-server-benchmark-*.json | head -n 1)"
metrics_file="$(ls -1t "$bench_dir"/rust-server-benchmark-*.tsv | head -n 1)"

pms_copy_file_atomic "$quickstart_file" "$bundle_dir/quickstart.json"
pms_copy_file_atomic "$report_file" "$bundle_dir/benchmark-report.json"
pms_copy_file_atomic "$metrics_file" "$bundle_dir/benchmark-metrics.tsv"

export NETWORK_INTEROP_BENCHMARK_PROJECT_ID="$project_id"
export NETWORK_INTEROP_BENCHMARK_PROJECT_NAME="$project_name"
export NETWORK_INTEROP_BENCHMARK_BUNDLE_DIR="$bundle_dir"
export NETWORK_INTEROP_BENCHMARK_REPORT_FILE="$bundle_dir/benchmark-report.json"
export NETWORK_INTEROP_BENCHMARK_METRICS_FILE="$bundle_dir/benchmark-metrics.tsv"
export NETWORK_INTEROP_BENCHMARK_QUICKSTART_FILE="$bundle_dir/quickstart.json"

py - <<'PY'
import json
import os
from pathlib import Path

from pms.utils.atomic_files import write_json_atomic

report = json.loads(Path(os.environ["NETWORK_INTEROP_BENCHMARK_REPORT_FILE"]).read_text(encoding="utf-8"))
bundle_dir = Path(os.environ["NETWORK_INTEROP_BENCHMARK_BUNDLE_DIR"])

summary = {
    "generated_at": report["generated_at"],
    "project": {
        "id": os.environ["NETWORK_INTEROP_BENCHMARK_PROJECT_ID"],
        "name": os.environ["NETWORK_INTEROP_BENCHMARK_PROJECT_NAME"],
    },
    "artifacts": {
        "quickstart": os.environ["NETWORK_INTEROP_BENCHMARK_QUICKSTART_FILE"],
        "benchmark_report": os.environ["NETWORK_INTEROP_BENCHMARK_REPORT_FILE"],
        "benchmark_metrics": os.environ["NETWORK_INTEROP_BENCHMARK_METRICS_FILE"],
    },
    "benchmark": {
        "server_url": report["server_url"],
        "repetitions": report["repetitions"],
        "scenarios": {
            scenario: sorted(interfaces.keys())
            for scenario, interfaces in report["scenarios"].items()
        },
    },
}

write_json_atomic(bundle_dir / "benchmark-bundle.summary.json", summary, encoding="utf-8")
PY

pms_publish_symlink_atomic "$bundle_dir" "$latest_dir"

echo "Network interop benchmark bundle completed."
echo "  summary: $bundle_dir/benchmark-bundle.summary.json"
echo "  latest: $latest_dir/benchmark-bundle.summary.json"
