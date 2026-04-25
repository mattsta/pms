# PMS Client - Compiled Rust Binary

**Zero-latency native client for PMS API server**

## Features

- **Native Performance**: Compiled to machine code, no interpreter
- **Zero Startup**: < 1ms startup time
- **Small Binary**: ~2-5MB (statically linked)
- **Cross-Platform**: Linux, macOS, Windows

## Build

```bash
# Install into a stable repo-local binary path
./scripts/install_pms_client.sh

# Installed binary location
./.bin/pms-client
```

## Usage

```bash
# Start a local PMS API server once
uv run pms serve --host 127.0.0.1 --port 27541

# Bootstrap or refresh an admin key for the current PMS database
uv run pms auth init --show-key
export PMS_API_KEY="$(cat .pms-admin-key)"

# Runtime entity IDs are opaque canonical tokens.
# Unless a family is explicitly documented as prefix-native, use the live UUIDs
# returned by PMS or generic placeholders like <task-id> in automation/docs.

# Create task
./.bin/pms-client --server http://127.0.0.1:27541 task create <project-id> "My Task" -c 50

# Bootstrap admin key (first run)
./.bin/pms-client --server http://127.0.0.1:27541 auth init --show-key

# Start guide with live-state next steps
./.bin/pms-client --server http://127.0.0.1:27541 start --format json

# Lifecycle list parity examples
./.bin/pms-client --server http://127.0.0.1:27541 task list --project-id <project-id> --status in_progress --limit 20 --offset 0 --format json
./.bin/pms-client --server http://127.0.0.1:27541 plan list --project-id <project-id> --task-id <task-id> --limit 20 --offset 0 --format json

# Actor graph
./.bin/pms-client --server http://127.0.0.1:27541 actor create "Alice Example" --kind human --format json
./.bin/pms-client --server http://127.0.0.1:27541 actor create "Security Persona" --kind persona --format json
./.bin/pms-client --server http://127.0.0.1:27541 actor membership add security-persona alice-example --role representative --format json
./.bin/pms-client --server http://127.0.0.1:27541 actor show security-persona --format json

# Checkout task
./.bin/pms-client --server http://127.0.0.1:27541 task checkout <task-id> --agent-id <agent-session-id>

# Update progress
./.bin/pms-client --server http://127.0.0.1:27541 task progress <task-id> 75 "Almost done" --by <agent-session-id>

# Block/unblock task
./.bin/pms-client --server http://127.0.0.1:27541 task block <task-id> --reason "Waiting on review" --by <agent-session-id>
./.bin/pms-client --server http://127.0.0.1:27541 task unblock <task-id> --by <agent-session-id>

# Task dependencies + graph
./.bin/pms-client --server http://127.0.0.1:27541 task dep add <task-id> <task-id-2> --dependency-type blocks
./.bin/pms-client --server http://127.0.0.1:27541 task graph <task-id>
./.bin/pms-client --server http://127.0.0.1:27541 task tree --project-id <project-id>

# Create product
./.bin/pms-client --server http://127.0.0.1:27541 product create "MyService" -d "Core service"

# Update product
./.bin/pms-client --server http://127.0.0.1:27541 product update <product-id> --status active --tag platform

# List products
./.bin/pms-client --server http://127.0.0.1:27541 product list

# Create project with scope links
./.bin/pms-client --server http://127.0.0.1:27541 project create "Q1 2026" --org-id <org-id> --portfolio-id <portfolio-id> --program-id <program-id> --product-id <product-id> -t backend -t infra

# Update project status
./.bin/pms-client --server http://127.0.0.1:27541 project update <project-id> --status archived

# Complete/delete project
./.bin/pms-client --server http://127.0.0.1:27541 project complete <project-id>
./.bin/pms-client --server http://127.0.0.1:27541 project delete <project-id>

# Project summary
./.bin/pms-client --server http://127.0.0.1:27541 project summary <project-id>

# Create organization
./.bin/pms-client --server http://127.0.0.1:27541 org create "Acme" --owner lead@example.com --member lead@example.com

# List portfolios for an org
./.bin/pms-client --server http://127.0.0.1:27541 portfolio list --org-id <org-id>

# Program summary
./.bin/pms-client --server http://127.0.0.1:27541 program summary <program-id>

# Create a plan with JSON content
./.bin/pms-client --server http://127.0.0.1:27541 plan create "Release Plan" --project-id <project-id> --content '{"milestones":["alpha","beta"]}'

# List plan test jobs
./.bin/pms-client --server http://127.0.0.1:27541 plan test-job list <plan-id>

# Run a plan test job with output
./.bin/pms-client --server http://127.0.0.1:27541 plan test-job run <plan-id> <job-id> --include-output

# Create a saved queue with filters
./.bin/pms-client --server http://127.0.0.1:27541 queue create "ready" --filters '{"status":"ready"}'

# Run queue preset
./.bin/pms-client --server http://127.0.0.1:27541 queue preset ready --project-id <project-id>

# Run local tests (delegates to uv run pms)
./.bin/pms-client --server http://127.0.0.1:27541 test run . --command "pytest -q"

# Record a remote test run
./.bin/pms-client --server http://127.0.0.1:27541 test record --server-id local --status passed \
  --started-at 2026-01-01T00:00:00Z --finished-at 2026-01-01T00:00:05Z \
  --project-id <project-id> --command "pytest -q" --runner remote

# List test runs
./.bin/pms-client --server http://127.0.0.1:27541 test list --project-id <project-id> --include-output

# Retention summary
./.bin/pms-client --server http://127.0.0.1:27541 test retention --project-id <project-id>

# Run an agent loop (delegates to uv run pms)
./.bin/pms-client --server http://127.0.0.1:27541 loop run "Draft roadmap updates" --max-iterations 3

# Initialize loop config
./.bin/pms-client --server http://127.0.0.1:27541 loop init --config pms-loop.yml --prompt-file PROMPT.md

# List agent loops
./.bin/pms-client --server http://127.0.0.1:27541 loop list --include-ended

# Show loop messages
./.bin/pms-client --server http://127.0.0.1:27541 loop messages <loop-id> --limit 5

# Align workflow to status
./.bin/pms-client --server http://127.0.0.1:27541 workflow align <task-id> --by "agent@example.com" --entity-type task

# Show workflow detail
./.bin/pms-client --server http://127.0.0.1:27541 workflow show sdlc --format json

# Checkout status/log maintenance
./.bin/pms-client --server http://127.0.0.1:27541 task checkout-status --agent-id <agent-session-id>
./.bin/pms-client --server http://127.0.0.1:27541 task checkout-log --agent-id <agent-session-id> --limit 10
./.bin/pms-client --server http://127.0.0.1:27541 task checkout-cleanup --dry-run

# Task evidence and proof bundles
./.bin/pms-client --server http://127.0.0.1:27541 task evidence add <task-id> "manual" "notes.md" --description "Manual notes"
./.bin/pms-client --server http://127.0.0.1:27541 task evidence list <task-id> --include-test-runs
./.bin/pms-client --server http://127.0.0.1:27541 task proof-bundle <task-id> --include-output

# Transition timelines
./.bin/pms-client --server http://127.0.0.1:27541 timeline workflow task <task-id>
./.bin/pms-client --server http://127.0.0.1:27541 timeline status task <task-id> --label release:ready

# Revision history
./.bin/pms-client --server http://127.0.0.1:27541 revision diff task <task-id> 1 2
./.bin/pms-client --server http://127.0.0.1:27541 revision bundle task <task-id> --include-linked --history-limit 10

# Work snapshots
./.bin/pms-client --server http://127.0.0.1:27541 work snapshot project <project-id>
./.bin/pms-client --server http://127.0.0.1:27541 work review project <project-id> --note "Reviewed weekly"

# Daily review summary
./.bin/pms-client --server http://127.0.0.1:27541 work daily project <project-id> --format text

# Dashboard HTML
./.bin/pms-client --server http://127.0.0.1:27541 dashboard
```

The Rust client talks to a running PMS API server. It is fast for repeated
reads when the server is already warm; it is not a direct SQLite reader. On
this machine, a release-build `task list` against a warm local server measured
about `0.01s`, versus about `1.04s` for `uv run pms task list ...` on the
direct Python CLI path.

Maintained lifecycle-list parity currently guarantees:

- Rust `PMSClient::list_tasks()` matches Python `PMSClient.list_tasks()` for:
  - `project_id`
  - `status`
  - `limit`
  - `offset`
- Rust `PMSClient::list_plans()` matches Python `PMSClient.list_plans()` for:
  - `status`
  - `project_id`
  - `product_id`
  - `goal_id`
  - `objective_id`
  - `task_id`
  - `limit`
  - `offset`
- `pms-client task list` and `pms-client plan list` mirror those maintained
  list filters at the CLI layer

This guarantee is checked by:

- `scripts/audit_client_lifecycle_list_surface_contracts.py`
- `scripts/audit_client_lifecycle_list_payload_parity.py`

Explicit exclusion:

- `start` is supported by the compiled Rust CLI as an operator surface, but it
  is not part of the maintained Python-vs-Rust client-library parity contract

PMS JSON control-plane payloads keep canonical `uv run pms ...` suggestions,
but they can also advertise the installed binary path through:

```bash
export PMS_ALT_CLI_ARGV0="$PWD/.bin/pms-client --server http://127.0.0.1:27541"
```

## Performance

**Measured**:

- Startup: < 1ms (native binary)
- Request: ~10-50ms (HTTP roundtrip)
- Binary size: ~3MB (release build with strip)

**vs Python**:

- Python: ~100-200ms startup (interpreter + imports)
- Rust: < 1ms startup (compiled binary)
- **200x faster startup!**

## Build Optimizations

The `Cargo.toml` is configured for minimal binary size:

- `opt-level = "z"` - Size optimization
- `lto = true` - Link-time optimization
- `strip = true` - Remove debug symbols
- `codegen-units = 1` - Better optimization

## Installation

```bash
# Install to the repo-local stable path and print shell exports
./scripts/install_pms_client.sh

# Optional: add the installed binary to PATH for this shell
export PATH="$PWD/.bin:$PATH"
export PMS_ALT_CLI_ARGV0="$PWD/.bin/pms-client --server http://127.0.0.1:27541"

# Now use from the installed path or from PATH
./.bin/pms-client --help
pms-client --help
```

**Status**: ✅ Production-ready compiled client
