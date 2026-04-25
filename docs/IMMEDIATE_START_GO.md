# Immediate Start -> Go

This guide gives the fastest path from an empty environment to a real, usable PMS workflow.

Use this guide when you need four answers quickly:

- what PMS is for in a real operator workflow
- the fastest command to run right now
- which artifacts or state it will create
- what command should come next after it finishes

For the long-form identity and persona architecture behind "my work",
assignment, and reporting flows, see:

- `docs/ACTOR_IDENTITY_PERSONA_GRAPH_ARCHITECTURE.md`

Current actor-aware workflow entry points already available:

- `uv run pms actor create "Alice Example" --kind human --format json`
- `uv run pms config set --current-actor alice-example`
- `uv run pms actor show me --format json`
- `uv run pms task list --mine --format json`
- `uv run pms task search --mine --format json`
- `uv run pms task add "<project>" "<title>" --assigned-to alice-example --format json`
- `uv run pms task update <task> --assigned-to security-persona --format json`
- `uv run pms task ready --format json`
- `uv run pms queue presets --format json --view detail`
- `uv run pms dashboard --format json`
- `uv run pms goal show <goal> --format json`
- `uv run pms org show <org> --format json`
- `uv run pms team show <team> --format json`
- `uv run pms portfolio summary <portfolio> --format json`
- `uv run pms program summary <program> --format json`
- `uv run pms queue show <queue> --format json`
- `uv run pms project show <project> --format json`

Those commands already support inherited persona/team memberships through the
actor graph, so "my tasks" is no longer limited to a flat direct-assignment
view.

Public actor contract:

- write requests use semantic role keys such as `owner`, `members`,
  `assignee`, and `actor`
- read payloads use the same role keys, and actor payloads themselves use
  `ref`, `id`, `actor`, and `links`
- actor rollups and graph-navigation links are available directly from the main
  review surfaces

## One-Command Demo (Recommended)

Run a full local smoke flow in an isolated data directory:

```bash
./scripts/run_demo_smoke.sh
```

What this does automatically:

1. Initializes PMS in `.tmp/demo-smoke-*`
2. Runs `pms quickstart` to create org/product/project/tasks/plan
3. Starts, progresses, and completes a task
4. Exports a daily summary and capability inventory

Artifacts are written into the generated `PMS_DATA_DIR` (printed by the script).

If you want a live "where do I go next" map first, run:

```bash
uv run pms start
```

What `uv run pms start` now guarantees:

- purpose: practical start -> go entry point for discovering live state, fastest first action, and where to extend next
- creates: no new state; this is a read-only guide over your current PMS workspace
- returns: `live_state`, `observability_paths`, `scenario_paths`, `focus_task`, and `next_steps`
- what comes next:
  - empty workspace: `uv run pms quickstart --defaults`
  - repeated bootstrap runs reuse the generated quickstart plan/tasks instead of creating another duplicate live quickstart plan
  - active task in progress: `uv run pms task progress ...`
  - ready task with no active execution: `uv run pms task start ...`
  - broader inspection: `uv run pms work daily --scope-type project --scope <name> --format json`

Before running anything destructive or experimental, inspect the resolved state:

```bash
uv run pms config show
```

For mutation commands that distinguish stored content from rendered output,
remember:

- `--format` controls stored content shape
- `--output-format` controls mutation result rendering
- compatibility shortcut: `plan create ... --format json` also emits
  machine-readable JSON when no explicit output format is chosen

Example:

```bash
<invoke-prefix> plan create "Runtime Truth Plan" --content '{}' --output-format json
```

If you want one local PMS process to coordinate writes for multiple shells or
agents, start the API server and persist the preferred runtime mode:

```bash
uv run pms runtime prefer-server --host 127.0.0.1 --port 27541
```

That command starts or reuses the local server, refreshes `.pms-admin-key` if
needed, and persists `prefer_server` for the current workspace.

When you need mutation provenance, use JSON output and read the returned
`runtime_write` block.

That tells you the truth about where the write actually landed:

- `server_delegated` -> the CLI delegated through the configured PMS API server

Validation contract:

- conflicting selector pairs such as `--project` plus `--project-id`, or
  `--goal` plus `--goal-id`, should fail nonzero instead of printing a warning
  and continuing
- in `--format json` mode, expect `{"error": ...}` for those failures across
  loop, task-update, retention, and other operator surfaces
- `direct_file` -> the CLI wrote straight to the workspace SQLite file

Interactive contract:

- batch/json validation failures should stop and return nonzero
- interactive prompt flows intentionally retry in place instead of degrading into machine-readable errors
- maintained examples:
  - `uv run pms loop setup` retries invalid dependency task numbers
  - `uv run pms task show <title> --project <project> --pick` retries invalid row selections

Do not infer the write path from `write_mode` alone. `prefer_server` can still
fall back to direct-file writes if the server is unreachable or the API key is
missing.

Execution lifecycle is also enforced during progress updates:

- `task progress ... 0 ...` can leave a task in `todo`
- `task progress ... <positive percent> ...` auto-starts a `todo` task and
  returns `status = in_progress` on immediate readback
- if a newer progress update revises a task downward, immediate project/task
  readbacks should follow the newest update rather than keeping the old higher
  estimate

If `runtime status` reports a reachable but unmanaged localhost target, treat
that as a safety warning. Rebind PMS to a managed local server instead of
assuming that any reachable `127.0.0.1` endpoint shares this workspace's auth
and state.

If `runtime status --format json` reports `unmanaged_local_processes`, PMS has
detected workspace-local server leftovers that are outside managed runtime
tracking. Use `uv run pms runtime cleanup --include-unmanaged-local --format json`
to stop those explicitly.
Use `--unmanaged-port <port>` or `--unmanaged-pid <pid>` when you want to clear
specific leaked local PMS server processes without broad unmanaged cleanup.
`runtime cleanup` now preserves the configured preferred managed local server by
default. Use `--stop-all-managed` only when you intentionally want to tear down
every tracked managed runtime slot.
If `runtime cleanup --format json` reports `failed_managed`, PMS could not stop
one or more tracked managed local servers and intentionally preserved their
runtime state so follow-up recovery stays truthful.

`runtime prefer-server` should also clear a stale `PMS_API_KEY` env override in
the current process so runtime auth converges on the file-backed local admin key.
Managed local runtime bootstrap should inherit the resolved workspace
`database_path` and `log_dir`, not silently assume `data_dir/pms.db`.
Explicit `serve` / `runtime prefer-server` host+port requests are authoritative:
PMS keeps one active local server per `PMS_DATA_DIR` and replaces the previous
active server cleanly when you intentionally rebind the workspace to a new
port.
If multiple healthy managed local servers are tracked, runtime diagnostics
should prefer the configured `server_base_url` when reporting the discovered
managed runtime.

Apply that check to create and update flows too, not just task execution:

- `<invoke-prefix> project create ...`
- `<invoke-prefix> task add ...`
- `<invoke-prefix> plan create ...`
- `<invoke-prefix> plan update ...`

Architecture and fallback details:

- `docs/WRITE_COORDINATION_ARCHITECTURE.md`

If you want the preferred low-latency server-backed binary path for repeated reads and reports:

```bash
./scripts/install_pms_client.sh
export PATH="$PWD/.bin:$PATH"
export PMS_API_KEY="$(cat .pms-admin-key)"
pms-client start --format json
```

If you do not want to touch your normal PMS workspace, initialize a scratch
root first:

```bash
uv run pms init --data-dir ./.pms-scratch
PMS_DATA_DIR=$PWD/.pms-scratch PMS_DATABASE_PATH=$PWD/.pms-scratch/pms.db \
  uv run pms start --format json
```

If you want bootstrap plus structured artifact readback in one command, run:

```bash
uv run pms quickstart --defaults --format json
```

This creates starter state and returns the created project/task/plan artifacts,
plus exact `next_steps` for project inspection, daily review, dashboard entry,
and the broader `uv run pms start --format json` control plane.

If you need maintained proof that the server-backed Python CLI, HTTP API, and
Rust client are all still cooperating correctly, run:

```bash
bash ./scripts/run_network_interop_benchmark_contract_smoke.sh
bash ./scripts/run_proof_bundle_contract_smoke.sh
```

Then inspect:

- `artifacts/network_interop/latest/benchmark-bundle.summary.json`
- `$PMS_DATA_DIR/proof-bundle.summary.json`
- `client-rust/README.md`
- `examples/real_world/README.md`

`artifacts/network_interop/latest` is a convenience symlink to the newest
timestamped benchmark bundle; the timestamped bundle remains authoritative.

Customize it with environment variables:

```bash
PMS_DEMO_ORG="Acme Org" \
PMS_DEMO_PRODUCT="Payments Platform" \
PMS_DEMO_PROJECT="Gateway Hardening Sprint" \
PMS_DEMO_ACTOR="release-bot" \
./scripts/run_demo_smoke.sh
```

Supported customization variables:

- `PMS_DATA_DIR`, `PMS_DATABASE_PATH`, `PMS_LOG_DIR`
- `PMS_DEMO_ORG`, `PMS_DEMO_PORTFOLIO`, `PMS_DEMO_PROGRAM`, `PMS_DEMO_PRODUCT`, `PMS_DEMO_PROJECT`
- `PMS_DEMO_ACTOR`, `PMS_DEMO_SUFFIX`

## One-Command Real-World Onboarding

Run the end-to-end practical flow (`drop in -> start -> go -> extend -> grow`):

```bash
./scripts/run_dropin_start_go_extend_grow.sh
```

Run the same flow with strict output-contract checks:

```bash
./scripts/run_dropin_contract_smoke.sh
```

For team-specific values, copy and edit:

- `examples/real_world/dropin.env.example`
- `examples/real_world/README.md#scenario-dropin`

## One-Command Team Handoff Validation

Run a real-world multi-project handoff flow (`build -> release`):

```bash
./scripts/run_team_handoff_flow.sh
```

Run the same flow with strict output-contract checks:

```bash
./scripts/run_team_handoff_contract_smoke.sh
```

For team-specific values, copy and edit:

- `examples/real_world/team_handoff.env.example`
- `examples/real_world/README.md#scenario-team-handoff`

## One-Command Incident Response Validation

Run the incident response flow (`triage -> mitigation -> comms -> postmortem`):

```bash
./scripts/run_incident_response_flow.sh
```

Run the same flow with strict output-contract checks:

```bash
./scripts/run_incident_response_contract_smoke.sh
```

For team-specific values, copy and edit:

- `examples/real_world/incident_response.env.example`
- `examples/real_world/README.md#scenario-incident-response`

## One-Command User Bootstrap + Observability Validation

Run the user-centric bootstrap path (`start -> go -> observe`):

```bash
./scripts/run_user_start_go_observe_flow.sh
```

Run the same path with strict output-contract checks:

```bash
./scripts/run_user_start_go_observe_contract_smoke.sh
```

For team-specific values, copy and edit:

- `examples/real_world/user_start_go_observe.env.example`
- `examples/real_world/README.md#scenario-user-start-go-observe`

## One-Command Operational Review Validation

Run the recurring operator-review path (`review -> decide -> continue`):

```bash
./scripts/run_operational_review_flow.sh
```

Run the same path with strict output-contract checks:

```bash
./scripts/run_operational_review_contract_smoke.sh
```

For team-specific values, copy and edit:

- `examples/real_world/operational_review.env.example`
- `examples/real_world/README.md#scenario-operational-review`

## One-Command Backlog Triage Validation

Run the backlog triage / prioritization path (`prioritize -> de-duplicate -> continue`):

```bash
./scripts/run_backlog_triage_flow.sh
```

If the instance may contain old fixture, repro, or API-test residue, classify it first:

```bash
uv run python scripts/cleanup_fixture_backlog.py
```

If that report shows only known fixture categories and orphan lifecycle mismatches, normalize the state before starting the next real branch:

```bash
uv run python scripts/cleanup_fixture_backlog.py --apply
```

Run the same path with strict output-contract checks:

```bash
./scripts/run_backlog_triage_contract_smoke.sh
```

For team-specific values, copy and edit:

- `examples/real_world/backlog_triage.env.example`
- `examples/real_world/README.md#scenario-backlog-triage`

## One-Command Portfolio Steering Validation

Run the multi-project steering path (`roll up -> inspect -> coordinate`):

```bash
./scripts/run_portfolio_steering_flow.sh
```

Run the same path with strict output-contract checks:

```bash
./scripts/run_portfolio_steering_contract_smoke.sh
```

For team-specific values, copy and edit:

- `examples/real_world/portfolio_steering.env.example`
- `examples/real_world/README.md#scenario-portfolio-steering`

## One-Command Agent Execution Loop Validation

Run the agent-driven execution loop path (`plan -> loop -> prove -> close`):

```bash
./scripts/run_agent_execution_loop_flow.sh
```

Run the same path with strict output-contract checks:

```bash
./scripts/run_agent_execution_loop_contract_smoke.sh
```

For team-specific values, copy and edit:

- `examples/real_world/agent_execution_loop.env.example`
- `examples/real_world/README.md#scenario-agent-execution-loop`

## One-Command Release Readiness Validation

Run the launch-control / release-readiness flow:

```bash
./scripts/run_release_readiness_flow.sh
```

Run the same flow with strict output-contract checks:

```bash
./scripts/run_release_readiness_contract_smoke.sh
```

For team-specific values, copy and edit:

- `examples/real_world/release_readiness.env.example`
- `examples/real_world/README.md#scenario-release-readiness`

## Full Audit Check Command

Run a broad platform validation pass:

```bash
./scripts/run_audit_checks.sh
./scripts/run_audit_checks.sh --list-stages
./scripts/run_audit_checks.sh all-preflight
```

That maintained audit pass includes planning-state lifecycle checks, so retained
task history is verified for non-zero-progress/non-active drift and done-task
progress drift.

The maintained runner is stage-aware. The default `./scripts/run_audit_checks.sh`
call still runs every maintained stage, but CI now splits that work into
clearer buckets so one long preflight job does not hide progress. The current
stage map is:

1. `validate-docs-and-parity`
2. `scenario-contract-smokes-a`
3. `scenario-contract-smokes-b`
4. `scenario-contract-smokes-c`
5. `docs-discoverability-audits`
6. `runtime-integrity-audits`
7. `surface-parity-audits`
8. `lifecycle-rollup-audits`
9. `full-test-suite`

Use targeted stage runs when you only need one slice:

```bash
./scripts/run_audit_checks.sh validate-docs-and-parity
./scripts/run_audit_checks.sh docs-discoverability-audits runtime-integrity-audits
PMS_AUDIT_SKIP_TESTS=1 ./scripts/run_audit_checks.sh all-preflight
```

Skip full tests when you need a faster preflight:

```bash
PMS_AUDIT_SKIP_TESTS=1 ./scripts/run_audit_checks.sh all
```

## Public Release Gate

When you are cutting the public release rather than running a broad platform
audit, use the dedicated gate:

```bash
./scripts/run_public_release_gate.sh
```

That command regenerates the public generated docs, runs the docs/runtime and
Rust checks, runs the full visible pytest suite, and verifies that the
release-readiness project plus `start`/`dashboard`/runtime surfaces are still
truthful on the exact commit being shipped.

Run only docs/discoverability checks:

```bash
./scripts/run_docs_smoke.sh
```

The fastest truth-check for the entry surface itself is:

```bash
uv run pms start --format json
uv run pms dashboard --format json
uv run pms work daily --scope-type project --scope "<project>" --format json
```

These commands should all agree on the current operator focus and should not create new state.
For dashboard output, top-level totals are the visible operator totals; `instance_totals` is the
full non-archived retained population. For task output, `task list --status <value>` must return
the same logical population whether or not `--project` is supplied.
Dashboard JSON now also exposes this contract explicitly:

- `visible_totals.population = "visible_operator"`
- `instance_totals.population = "all_non_archived_retained"`
- archived projects are excluded from `instance_totals`
- default global `task list --format json` now uses `scope.population = "visible_operator"`
- global `task list --include-generated --format json` switches `scope.population` and `population_totals.population` to `all_retained` while preserving `visible_totals.population = "visible_operator"`
- text `task list` now defaults to `--view review` so `uv run pms task list`
  works as an at-a-glance audit surface instead of a flat dense export table
- `task search`, `task ready`, `task stale`, and `task blocked` now default to
  that same review-first text surface; use `--view overview` if you need the
  older dense table on those entry surfaces
- `task list --format json` now includes `graph_navigation` so the current
  focus task can be replayed into `task show`, `task graph`, `task timeline`,
  `plan list --task-id`, `task evidence list`, `actor show`, `project show`,
  `task tree --project`, and `work review`
- default global `task search --format json` now uses that same `visible_operator` population contract
- global `task search --include-generated --format json` switches `scope.population` and `population_totals.population` to `all_retained`
- global `task ready`, `task stale`, and `task blocked` now use the same top-level visible-versus-retained contract family
- `task search --format json`, `task ready --format json`,
  `task stale --format json`, and `task blocked --format json` now also expose
  top-level `focus_task` plus `graph_navigation`
- `queue run --format json`, `queue presets --format json`,
  `work daily --format json`, and `work review --format json` now follow the
  same graph-traversal posture:
  - queue and daily surfaces expose actor-aware `focus_task` payloads plus
    top-level `graph_navigation`
  - review surfaces expose scope-based `graph_navigation` back into the
    project graph when there is no single focus task
- maintained actor rollup math coverage now runs under:
  `uv run python scripts/audit_actor_workload_math.py --check`
- global `task duplicates` now uses that same top-level visible-versus-retained contract family
- their `--include-generated` variants switch `scope.population` and `population_totals.population` to `all_retained`
- project-scoped `task list --project ... --format json` uses `scope.population = "scoped_project"`
- default instance-wide task lists suppress generated/history-only project tasks and expose `suppressed_hidden_count`
- default instance-wide task searches suppress generated/history-only project tasks and expose `suppressed_hidden_count`
- task rows now expose project visibility metadata: `project_operator_category`, `project_operator_category_label`, `project_operator_visibility_reason`
- `task timeline` reconciles terminal snapshot-backed completion progress instead of falsely reporting `0% | Updates: 0`
- `project list --format json` defaults to `scope.population = "visible_operator"`
- `project list --include-generated --format json` switches `scope.population` and `population_totals.population` to `all_retained` while preserving `visible_totals.population = "visible_operator"`
- `project list --format json` separates raw active status from actionable `active_work` with:
  - `visible_totals.active_projects`
  - `visible_totals.active_work_projects`
  - `scope.active_work_visible_projects`
- active generated artifact projects keep artifact categories such as `audit_artifact`; they do not silently relabel as `active_work`
- stale `Recent Progress Project` fixture residue ages into retained history so old fixtures stop driving `start` and `dashboard`
- known zero-task strategic filter fixtures are treated as retained history instead of active work in default operator surfaces
- when `scope.active_work_visible_projects = 0`, `project list --format json` now treats the surface as no-actionable-work guidance rather than steering you into retained history as if it were current work
- default empty global task surfaces such as `task list --format json` and `task ready --format json` now say when retained history is being hidden and point to `--include-generated`/`quickstart` instead of implying the system has no residual state
- `task list --format json`, `task ready --format json`, `task search --format json`, and `task stale --format json` now preserve active filters inside `links.self` and retained-view next steps, so machine users can replay or widen the exact filtered view without rebuilding the command by hand
- `plan create --format json` now rejects invalid JSON content before write delegation, so bootstrap and automation flows fail with an explicit machine-readable error instead of an opaque parse failure
- `project list --view detail --include-linked --format json` now keeps linked/history replay flags in `links.self` and emits normalized linked-task commands for machine follow-up
- `project show --include-linked --format json` and `project summary --format json` now expose normalized project/task command links for machine follow-up, matching the broader replay contract
- `project show --format json`, `project summary --format json`,
  `dashboard --format json`, and `start --format json` now expose top-level
  `graph_navigation` for the current focus task, so the main control planes can
  jump directly into graph, proof, actor, plan, and review follow-up
- `actor show --format json` now exposes:
  - `ownership.counts`
  - `ownership.items`
  - `project_workloads`
  - `graph_navigation`
    so actor/persona nodes are traversable workload and accountability surfaces,
    not just identity records
- `project update --format json` now emits normalized follow-up commands instead of mixing raw `pms ...` strings into mutation next steps
- default `queue presets --format json` uses that same visible operator population
- `goal list --format json` defaults to the same operator-visible posture; add `--include-generated` when you intentionally need retained audit/history goals
- `uv run python scripts/report_active_goal_backlog.py` gives a live severity summary of active goals so you can decide whether to finish current work or move on to larger branches
- its JSON payload exposes named presets under top-level `items[]`, so compare dashboard `queue_presets[]` entries to standalone `items[]` entries by `name`
- `goal_horizon_stats_population = "all_non_archived_retained"`
- `visible_goal_horizon_stats_population = "visible_operator"`
- use `visible_goal_horizon_stats` when you need the horizon rollup for the current operator-visible surface instead of the retained instance-wide population
- `/api/v1/observability/overview` exposes the retained-basis project rollup under `rollups.projects.population = "all_non_archived_retained"`
- the MCP `get_dashboard` tool uses that same retained population basis; it is not the operator-filtered CLI dashboard projection
- `project show --format json` and `project summary --format json` now expose an `execution` block with active-task counts and active task rows for direct verification of project execution state
- `project show --format json` also keeps top-level `total_tasks`, `completed_tasks`, `in_progress_tasks`, and `blocked_tasks` aligned with that `execution` block
- `goal summary --format json` now exposes top-level `terminal_reason` and `completion_context` when linked execution is already terminal
- `goal summary --format json` now also exposes a symmetric `links` block so machine clients can move back to the goal, project, objectives, tasks, and linked plans without reconstructing commands
- `config set` writes to the resolved env file for the current execution context, and the command output prints that exact target path; set `PMS_ENV_FILE` when you want an isolated config target
- `config show` exposes the resolved env file path too, so JSON/text readbacks can verify which config target is actually in use
- admin key mutation commands now expose machine-readable contracts too:
  `auth create|deactivate|restore|revoke --format json`
- conflicting strategic scope selectors now fail non-zero instead of printing a warning and exiting `0`
- in `--format json` mode, these validation failures return `{"error": ...}` for `plan list`, `objective list`, `keyresult list`, `objective create`, and `objective update`
- invalid strategic progress/date input now fails non-zero on both create and update flows instead of returning a fake success
- loop/test automation surfaces now follow that same rule for conflicting project selectors instead of returning a fake success
- runtime coordination also verifies delegated auth now: a reachable server with a rejected API key reports `degraded_invalid_api_key` instead of `server_coordinated`
- `task show --format json` now reconciles terminal progress summaries so a `done` task does not expose an older partial-progress metric as its final `progress.last_update`
- `task show --format json` now exposes a real task context graph through `context.project`, `context.milestone`, `context.parent`, and `context.subtasks`, and `--include-linked` widens that into linked parent/subtask/dependency/dependent traversal
- maintained graph traversal coverage now exists under `scripts/audit_graph_discoverability.py --check`

## Real-World Usage Recipes

### Recipe 1: New Feature Delivery

```bash
uv run pms init
uv run pms quickstart --defaults --org "Acme Org" --product "Acme API" --project "Feature X"
uv run pms task ready --project "Feature X"
uv run pms task start "Ship first endpoint" --project "Feature X" --by "dev1"
uv run pms task progress "Ship first endpoint" --project "Feature X" 70 "Core paths implemented" --by "dev1"
uv run pms task complete "Ship first endpoint" --project "Feature X" --by "dev1"
uv run pms work daily --scope-type project --scope "Feature X" --format json
```

### Recipe 2: Daily Review / Standup Snapshot

```bash
uv run pms work daily \
  --scope-type project \
  --scope "Feature X" \
  --include-timeline \
  --format json \
  --export reports/feature-x-daily.json
```

### Recipe 3: Incident Response Coordination

```bash
uv run pms project create "Incident 2026-02-21" -d "Production outage triage"
uv run pms task add "Incident 2026-02-21" "Triage and mitigate" -p high
uv run pms task add "Incident 2026-02-21" "Publish incident update" -p high
uv run pms task start "Triage and mitigate" --project "Incident 2026-02-21" --by "oncall"
uv run pms task progress "Triage and mitigate" --project "Incident 2026-02-21" 50 "Mitigation deployed" --by "oncall"
uv run pms work daily --scope-type project --scope "Incident 2026-02-21"
```

### Recipe 4: Agent-Driven Loop Setup

```bash
uv run pms loop setup --defaults --project "Feature X" --goal "Ship Feature X"
```

This produces loop config + prompt files for immediate agent execution.

## Full Capability and Feature Documentation

Use the generated capability catalog for full platform coverage:

- `docs/CAPABILITIES_REFERENCE.md`
- `docs/API_REFERENCE.md`
- `docs/API_ENDPOINT_CATALOG.md`
- `docs/API_RESPONSE_CONTRACTS.md`

Regenerate it at any time:

```bash
uv run pms capabilities docs --output docs/CAPABILITIES_REFERENCE.md
uv run python scripts/generate_api_endpoint_catalog.py --output docs/API_ENDPOINT_CATALOG.md
uv run python scripts/generate_api_response_contracts.py --output docs/API_RESPONSE_CONTRACTS.md
uv run python scripts/audit_api_reference.py --check --api-reference docs/API_REFERENCE.md
uv run python scripts/audit_api_reference_depth.py --check --api-reference docs/API_REFERENCE.md --contracts docs/API_RESPONSE_CONTRACTS.md
uv run python scripts/audit_discoverability_wrappers.py --check
```

`audit_api_reference.py` is read-only and enforces route + request-body example completeness.
`audit_api_reference_depth.py` is read-only and enforces response-depth coverage (local docs + contract fallback).
`audit_discoverability_wrappers.py` enforces `links`/`next_steps`/`params` wrappers on paginated API payloads.

For full command export coverage:

- `docs/CLI_EXPORTS.md`
