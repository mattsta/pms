# Project Management System

Project Management System (pms) is a graph-based project management and execution system
for humans, AI agents, and mixed teams.

PMS keeps scope, strategy, execution, ownership, proof, and review in one system,
then exposes the same live graph through a local-first CLI, an HTTP API, MCP tools,
and machine-readable JSON control planes.

PMS is built for two readers at once:

- human operators who need a few clear workflows and strong at-a-glance review
- advanced agents that need a broad, introspectable interface surface they can explore on their own

## Table of Contents

- [Installation](#installation)
- [Configuration And Environment](#configuration-and-environment)
- [Quick Start](#quick-start)
- [Immediate Start (Automated)](#immediate-start-automated)
- [Quick Agent Integration Snippets](#quick-agent-integration-snippets)
- [Feature Inventory](#feature-inventory)
- [Machine-Interface Progression](#machine-interface-progression)
- [Actor Identity And "My Work"](#actor-identity-and-my-work)
- [CLI Commands](#cli-commands)
  - [Actor Commands](#actor-commands)
  - [Project Commands](#project-commands)
  - [Organization Commands](#organization-commands)
  - [Team Commands](#team-commands)
  - [Portfolio Commands](#portfolio-commands)
  - [Program Commands](#program-commands)
  - [Product Commands](#product-commands)
  - [Goal/OKR Commands](#goalokr-commands)
  - [Plan Commands](#plan-commands)
  - [Task Commands](#task-commands)
  - [Queue And Work Commands](#queue-and-work-commands)
  - [Comment, Custom Field, And Collaboration Commands](#comment-custom-field-and-collaboration-commands)
  - [Evidence, Label, Workflow, And Automation Commands](#evidence-label-workflow-and-automation-commands)
  - [Report, Revision, Timeline, And Watcher Commands](#report-revision-timeline-and-watcher-commands)
  - [Test Commands](#test-commands)
  - [Remote Commands](#remote-commands)
  - [AWS Commands](#aws-commands)
  - [Agent And Loop Commands](#agent-and-loop-commands)
  - [Config, Auth, Runtime, And Install Commands](#config-auth-runtime-and-install-commands)
  - [Generate And Meta-Programming Commands](#generate-and-meta-programming-commands)
  - [Capabilities, Namespace, And Plugin Commands](#capabilities-namespace-and-plugin-commands)
- [MCP / Agent Integration](#mcp--agent-integration)
- [Python API And Clients](#python-api-and-clients)
- [Architecture](#architecture)
- [Runtime And Write Truth](#runtime-and-write-truth)
- [Constraint And Reference Truth](#constraint-and-reference-truth)
- [How PMS Is Used To Manage PMS Itself](#how-pms-is-used-to-manage-pms-itself)
- [Documentation Map](#documentation-map)
- [API And Contract References](#api-and-contract-references)
- [Real-World Scenario Packs](#real-world-scenario-packs)
- [When To Use / When Not To Use](#when-to-use--when-not-to-use)
- [Development And Validation](#development-and-validation)
- [Release Snapshot And Compatibility Notes](#release-snapshot-and-compatibility-notes)

## Installation

### Prerequisites

- Python `3.14`
- [`uv`](https://github.com/astral-sh/uv)
- `rsync` and SSH client for remote operations
- optional: Rust toolchain if you want to build and validate the Rust client locally

### Install From Source

```bash
git clone https://github.com/mattsta/pms
cd pms
uv sync
```

If you want PostgreSQL-backed operation from a source checkout, install the
optional driver too:

```bash
uv sync --extra postgres
```

### Verify Installation

```bash
uv run pms --version
uv run pms capabilities info
uv run pms config show --format json
```

### Initialize PMS

```bash
uv run pms init
```

This checkout also includes repo-pinned shell runners that work from any
directory:

```bash
./pms.sh config show
./pms-app.sh --app-root /path/to/app init
```

Use `pms.sh` when you only need this repo's PMS executable. Use `pms-app.sh`
when each application should keep its own `.pms` data directory, database, logs,
and env file. See [`docs/RUNNERS_AND_ENV.md`](docs/RUNNERS_AND_ENV.md).

If you want an isolated scratch workspace instead of your default local PMS state:

```bash
PMS_DATA_DIR=$PWD/.pms-scratch \
PMS_DATABASE_PATH=$PWD/.pms-scratch/pms.db \
PMS_LOG_DIR=$PWD/.pms-scratch/logs \
PMS_ENV_FILE=$PWD/.pms-scratch/.env \
uv run pms init
```

## Configuration And Environment

PMS reads `PMS_*` settings from the resolved env target for the current workspace.
Use this when you want demos, release checks, or agent loops to land in an
isolated state directory instead of your default local store.

### Core environment variables

| Variable            | Default         | Purpose                                  |
| ------------------- | --------------- | ---------------------------------------- |
| `PMS_DATA_DIR`      | `~/.pms`        | base data directory                      |
| `PMS_DATABASE_PATH` | `~/.pms/pms.db` | primary database path                    |
| `PMS_LOG_DIR`       | `~/.pms/logs`   | runtime and captured log output          |
| `PMS_ENV_FILE`      | `.env`          | persisted config target for `config set` |

### Inspect the resolved runtime target

```bash
uv run pms config show
uv run pms config show --format json
```

Useful fields to check before demos, audits, or destructive experiments:

- `paths.env_file`
- `paths.data_dir`
- `paths.database_path`
- `runtime.coordination`

### Safe scratch workflow

```bash
export PMS_DATA_DIR=$PWD/.pms-scratch
export PMS_DATABASE_PATH=$PWD/.pms-scratch/pms.db
export PMS_LOG_DIR=$PWD/.pms-scratch/logs
export PMS_ENV_FILE=$PWD/.pms-scratch/.env

uv run pms init
uv run pms start --format json
```

If multiple local writers may touch the same PMS state, prefer a managed local
server path and persist that expectation explicitly:

```bash
uv run pms serve --host 127.0.0.1 --port 27541
uv run pms config set --write-mode prefer_server --server-url http://127.0.0.1:27541
uv run pms runtime status --format json
```

Runtime rule:

- PMS keeps one active local server per `PMS_DATA_DIR`
- if you explicitly run `uv run pms serve --host ... --port ...` or
  `uv run pms runtime prefer-server --host ... --port ...` on a different port
  for the same workspace, PMS now replaces the previous active local server
  instead of silently ignoring the requested port or leaving duplicate servers

## Quick Agent Integration Snippets

If you want to plug PMS into an existing agent workflow quickly, use these
first. The maintained detailed guide is
[`docs/AGENT_INTEGRATION_GUIDE.md`](docs/AGENT_INTEGRATION_GUIDE.md).
The repo-local agent spec is [`SKILL.md`](SKILL.md).

### Session-Start Read Set

Use this at the start of an agent run so the harness reads live PMS state before
acting:

```bash
uv run pms start --format json
uv run pms dashboard --format json
uv run pms task ready --format json
uv run pms task list --project "Resume Hosting Site" --format json
uv run pms work daily --scope-type project --scope "Resume Hosting Site" --format json --no-attach
uv run pms goal summary "Launch resume hosting MVP" --format json
```

### Claude Code: MCP + Stop Hook + Permission Allowlist

MCP server config:

```json
{
  "mcpServers": {
    "pms": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/path/to/pms",
        "python",
        "-m",
        "pms.tools.server"
      ],
      "env": {
        "PMS_DATA_DIR": "/path/to/your/.pms"
      }
    }
  }
}
```

Project-local hook config in `.claude/settings.local.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "cd \"$CLAUDE_PROJECT_DIR\" && python3 scripts/agent_hooks/pms_stop_audit.py --project \"Resume Hosting Site\" --goal \"Launch resume hosting MVP\" --emit-claude-stop-payload"
          }
        ]
      }
    ],
    "PermissionRequest": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "cd \"$CLAUDE_PROJECT_DIR\" && python3 scripts/claude_hooks/pms_permission_allowlist.py"
          }
        ]
      }
    ]
  }
}
```

What this gives you:

- PMS MCP tools available inside Claude Code
- a deterministic stop-time bundle with `start`, `dashboard`, `task ready`,
  scoped task list, `work daily`, and goal summary JSON
- stop is blocked until `pms loop guard` says the scoped goals are complete

### Generic Shell-Wrapped Agent

Use this when your agent runner does not have a native hook protocol but you
still want PMS artifacts after each run:

```bash
#!/usr/bin/env bash
set -euo pipefail

agent_exit=0
"$@" || agent_exit=$?

python3 scripts/agent_hooks/pms_stop_audit.py \
  --project "Resume Hosting Site" \
  --goal "Launch resume hosting MVP" \
  > .tmp/pms-stop-audit.json || true

exit "$agent_exit"
```

This works well around Codex CLI, Aider, OpenCode, Cline, or internal agent
wrappers.

### MCP-Only Host

If the host can load MCP tools but not shell hooks, use PMS as the server and
make these calls part of the host workflow:

```json
{
  "mcpServers": {
    "pms": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/path/to/pms",
        "python",
        "-m",
        "pms.tools.server"
      ]
    }
  }
}
```

Recommended MCP read sequence:

- `start`
- `dashboard`
- `list_tasks`
- `get_work_daily`
- `get_goal_summary`

### CI / Post-Run Audit Artifact

Use this when you want every automation run to leave behind a PMS state bundle:

```bash
python3 scripts/agent_hooks/pms_stop_audit.py \
  --project "Release Coordination" \
  --goal "Cut 0.1.0"
```

Publish the resulting directory under `PMS_DATA_DIR/hook-audits/` as a CI
artifact.

## Quick Start

### 1. Ask PMS what to do next

```bash
uv run pms start
uv run pms start --format json
```

Use `start` first when you want PMS to tell you:

- what runtime is active
- what work is in focus
- whether there is any operator-visible backlog
- which command to run next

Current `start` contract:

- purpose: a live start -> go -> observe control plane, not a static tutorial
- creates: no new state; it reads the current workspace and recommends next steps
- outputs: live counts, focus task, runtime coordination state, docs/scenario links, and concrete command continuations
- next step shape: usually `task progress`, `task show`, `work daily`, `queue presets`, or `dashboard --format json`

Interactive contract:

- batch and `--format json` flows should fail nonzero with machine-readable errors when validation cannot be honored
- interactive flows intentionally retry local prompt mistakes in place
- `uv run pms loop setup` and `uv run pms task show <title> --project <project> --pick` are deliberately different from strict batch JSON paths

### 2. Bootstrap a usable workspace immediately

```bash
uv run pms quickstart --defaults --format json
```

That creates a real starter workspace and returns machine-readable artifacts for:

- organization
- product
- project
- starter tasks
- starter plan
- linked next steps back into `start`, `dashboard`, and project/task surfaces

Re-running `quickstart --defaults` is meant to reuse the generated starter plan/task set instead of duplicating another bootstrap graph in the same workspace.

### 3. Set your current actor

```bash
uv run pms actor create "Matt" --kind human --handle matt --format json
uv run pms config set --current-actor matt
uv run pms actor show me --format json
```

### 4. Create a project, strategy, and execution graph manually

```bash
uv run pms project create "Gateway Launch" \
  -d "Release control for the public API launch" \
  --format json

uv run pms goal create "Ship Gateway v1" \
  --project "Gateway Launch" \
  --horizon short_term \
  --owner matt \
  --format json

uv run pms objective create "Stabilize launch flow" \
  --goal "Ship Gateway v1" \
  --owner matt \
  --format json

uv run pms keyresult create "Launch checklist completion" \
  --objective "Stabilize launch flow" \
  --current 0 \
  --target 100 \
  --unit percent \
  --owner matt \
  --format json

uv run pms plan create "Gateway Launch Plan" \
  --project "Gateway Launch" \
  --goal "Ship Gateway v1" \
  --format yaml \
  --content $'phases:\n  - name: prep\n  - name: launch\n  - name: followup\n' \
  --output-format json
```

### 5. Add and run tasks

```bash
uv run pms task add "Gateway Launch" "Publish release notes" \
  --assigned-to matt \
  -p high \
  --format json

uv run pms task add "Gateway Launch" "Run smoke tests" \
  --assigned-to qa-persona \
  -p high \
  --format json

uv run pms task list --project "Gateway Launch"
uv run pms task ready --project "Gateway Launch" --format json
uv run pms task start "Publish release notes" --project "Gateway Launch" --by matt
uv run pms task progress "Publish release notes" --project "Gateway Launch" 50 "Draft complete" --by matt
uv run pms task complete "Publish release notes" --project "Gateway Launch" --by matt
```

### 6. Review the live graph

```bash
uv run pms dashboard --format json
uv run pms work daily --scope-type project --scope "Gateway Launch" --format json
uv run pms work graph-report --scope-type project --scope "Gateway Launch" --format json
uv run pms goal summary "Ship Gateway v1" --format json
uv run pms task show "Run smoke tests" --project "Gateway Launch" --include-linked --format json
```

### 7. Add governance and review surfaces

```bash
uv run pms label category create "Risk" --exclusive
uv run pms label create "needs-review" --category-id <category-id> --color "#f0b860"
uv run pms label assign task <task-id> needs-review

uv run pms label gate add \
  --workflow-id wf_sdlc \
  --entity-type task \
  --from-state code_review \
  --to-state unit_testing \
  --rule-type require_label \
  --label needs-review

uv run pms queue presets --view detail --format json
uv run pms work review --scope-type project --scope "Gateway Launch" --reviewed-by matt --note "Weekly review" --format json
```

### 8. Attach proof

```bash
uv run pms task evidence add "Run smoke tests" \
  log \
  logs/smoke.txt \
  --project "Gateway Launch" \
  --description "Latest smoke run output"
```

### 9. Inspect lineage and prefer a stable local server path when needed

```bash
uv run pms plan lineage --format json
uv run pms serve --host 127.0.0.1 --port 27541
uv run pms runtime prefer-server --host 127.0.0.1 --port 27541
./scripts/install_pms_client.sh
```

If you keep the local server running, the repo-local Rust client is useful for
repeated reads, reports, and dashboard-style queries:

```bash
export PATH="$PWD/.bin:$PATH"
export PMS_API_KEY="$(cat .pms-admin-key)"
```

## Immediate Start (Automated)

Use these when you want a realistic path through PMS immediately, not just an installed binary.

### Fastest demo

```bash
./scripts/run_demo_smoke.sh
```

### Production-like onboarding

```bash
./scripts/run_dropin_start_go_extend_grow.sh
./scripts/run_dropin_contract_smoke.sh
```

### Cross-team delivery handoff

```bash
./scripts/run_team_handoff_flow.sh
./scripts/run_team_handoff_contract_smoke.sh
```

### Incident response

```bash
./scripts/run_incident_response_flow.sh
./scripts/run_incident_response_contract_smoke.sh
```

### User-centric bootstrap / observability

```bash
./scripts/run_user_start_go_observe_flow.sh
./scripts/run_user_start_go_observe_contract_smoke.sh
```

### Release readiness

```bash
./scripts/run_release_readiness_flow.sh
./scripts/run_release_readiness_contract_smoke.sh
```

### Agent execution loop

```bash
./scripts/run_agent_execution_loop_flow.sh
./scripts/run_agent_execution_loop_contract_smoke.sh
```

### Operational review

```bash
./scripts/run_operational_review_flow.sh
./scripts/run_operational_review_contract_smoke.sh
```

### Backlog triage

```bash
./scripts/run_backlog_triage_flow.sh
./scripts/run_backlog_triage_contract_smoke.sh
```

### Portfolio steering

```bash
./scripts/run_portfolio_steering_flow.sh
./scripts/run_portfolio_steering_contract_smoke.sh
```

### Full maintained audit gate

```bash
./scripts/run_audit_checks.sh
./scripts/run_audit_checks.sh --list-stages
./scripts/run_audit_checks.sh all-preflight
./scripts/run_audit_checks.sh validate-docs-and-parity docs-discoverability-audits
```

### Docs and contract-only validation

```bash
./scripts/run_docs_smoke.sh
uv run python scripts/audit_api_reference.py --check --api-reference docs/API_REFERENCE.md
uv run python scripts/audit_api_reference_depth.py --check --api-reference docs/API_REFERENCE.md --contracts docs/API_RESPONSE_CONTRACTS.md
uv run python scripts/audit_discoverability_wrappers.py --check
```

Reference docs:

- [`docs/IMMEDIATE_START_GO.md`](docs/IMMEDIATE_START_GO.md)
- [`examples/real_world/README.md`](examples/real_world/README.md)
- [`docs/DOCUMENTATION_MAP.md`](docs/DOCUMENTATION_MAP.md)
- [`docs/archive/README.md`](docs/archive/README.md)

Practical discovery path:

1. Start now: `./scripts/run_demo_smoke.sh`
2. Inspect live state without creating anything: `uv run pms start --format json`
3. If the workspace is empty, bootstrap it: `uv run pms quickstart --defaults --format json`
4. If the workspace already has active work, follow the returned `focus_task`, `graph_navigation`, and `next_steps`
5. If the workspace is noisy from fixtures or API-test residue, classify it first with `uv run python scripts/cleanup_fixture_backlog.py`
6. If that dry run shows only known fixture/orphan state, normalize it with `uv run python scripts/cleanup_fixture_backlog.py --apply`
7. If you want a scenario with stronger proof expectations, jump directly to the relevant flow script above instead of hand-building the graph

For machine-readable mutation provenance, request JSON and read the returned runtime truth:

- JSON output: `runtime_write`

Text mutation output intentionally omits successful runtime plumbing to keep repeated agent loops compact. Degraded or blocked runtime coordination is still printed as a warning/error.

## Feature Inventory

PMS is intentionally broad and inter-connected instead of just being a linear list of "things to do."

### Core graph model

- organization -> portfolio -> program -> product -> project scope graph
- goal -> objective -> key result strategy graph
- plan -> task -> subtask / dependency execution graph
- actor -> persona / team / membership / assignment / ownership identity graph
- evidence -> test run -> review -> proof bundle completion graph

### Control planes

- `start` for fast "what next"
- `dashboard` for operator-wide state
- `work daily` for scoped daily review
- `work review` for explicit review checkpoints
- `work graph-report` for unified graph export across strategy, plans, tasks, actors, and evidence
- `queue run` and `queue presets` for reusable workload views

### Operator usability work already built into PMS

- review-first task surfaces by default for at-a-glance audits
- machine-readable `links`, `next_steps`, and `graph_navigation`
- explicit population/scope metadata on list/report surfaces
- canonical actor-aware assignee payloads across task and strategic surfaces
- explicit runtime-write truth on mutation responses

### Execution proof, review, and audit surfaces

- plan-linked test jobs that can push proof directly into execution artifacts
- task evidence capture for logs, commits, files, and explicit proof references
- work snapshots, daily reviews, and review checkpoints for scoped operational control
- revision bundles, diffs, and timelines for field-level history and transition analysis
- comments, watchers, and custom fields for richer collaboration without leaving the graph

### Remote, server, and interop surfaces

- local-first CLI with optional managed server-backed coordination
- HTTP API for service and agent integrations
- MCP tools for Claude/Codex-style runtimes
- repo-local compiled Rust client for repeated reads against a warm server
- SSH/rsync remote operations and AWS-backed test-server validation

### Extensibility and self-description

- generated capability inventory and schema export
- pluggable namespaces for PMS type catalogs and typed-ID utilities
- plugin system for dynamic tools and integrations
- code generation paths for new tool modules
- learning and memory subsystems that remain part of the broader platform model
- explicit runtime ID-contract documentation so namespace coverage and live row
  ID format do not get conflated

### Current generated capability snapshot

As of the current release audit, PMS exposes:

- `277` total capabilities
- `34` namespaces
- `150` tools
- `8` patterns
- `39` event types
- `26` reference types
- `10` knowledge types
- `10` feedback categories

Regenerate that inventory with:

```bash
uv run pms capabilities info
uv run pms capabilities docs --output docs/CAPABILITIES_REFERENCE.md
```

## Machine-Interface Progression

PMS is designed so a machine can start simple and become more graph-native over
time instead of needing every advanced feature explained up front.

Recommended progression:

1. discover live state with `start` and `dashboard`
2. follow `focus_task`, `links`, and `next_steps`
3. traverse reverse and forward graph edges from `task show --include-linked`
4. use actors, memberships, assignments, and checkout identity instead of
   relying on free-form owner strings
5. move to `work graph-report` when you want a dense project graph export
6. use structured JSON in plan content and evidence metadata when your agent
   needs deep correlation or external IDs

The most important machine-readable contract families are:

- `focus_task`
- `links`
- `next_steps`
- `graph_navigation`
- `actor_rollups`
- `population_basis`
- `runtime.coordination`
- `runtime_write`

A machine-native planning artifact can be much denser than a human-authored note.
PMS is intentionally fine with that:

```bash
uv run pms plan create "Agent Rollout Plan" \
  --project "Gateway Launch" \
  --goal "Ship Gateway v1" \
  --format json \
  --content '{"execution_graph":{"waves":[{"id":"wave-1","actors":["alice-example","security-persona"]}],"external_correlations":{"ticket":"EXT-42"}}}' \
  --output-format json

uv run pms work graph-report --scope-type project --scope "Gateway Launch" --format json
```

The important practice is to treat returned IDs, `links`, and `graph_navigation`
as the continuation surface instead of scraping human-readable prose.

Read these guides together:

- [`docs/MACHINE_INTERFACE_GUIDE.md`](docs/MACHINE_INTERFACE_GUIDE.md)
- [`docs/CLIENT_GUIDE.md`](docs/CLIENT_GUIDE.md)
- [`docs/WEB_API.md`](docs/WEB_API.md)
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

Entity-type nuance that matters for machine clients:

- namespace-backed entity families participate in `pms namespace ...`
  introspection and typed-ID utilities, but that is separate from the runtime
  row-ID contract for most public entities today
- unless PMS explicitly documents a family as prefix-native, treat live stored
  entity IDs as UUID-native opaque IDs
- PMS also accepts a small set of DB-backed UUID-native entity families where
  that is already the real storage contract today:
  - `actor`
  - `automation_rule`
  - `product`
- `api_key` now participates in both the relational contract and the built-in
  namespace registry because its ID contract is already prefix-native

## Actor Identity And "My Work"

PMS now has a first-class actor model instead of treating owners and assignees as only free-form labels.

Available now:

```bash
uv run pms actor create "Alice Example" --kind human --handle alice-example --format json
uv run pms actor create "Security Persona" --kind persona --handle security-persona --format json
uv run pms actor membership add security-persona alice-example --role representative --format json
uv run pms config set --current-actor alice-example
uv run pms actor show me --format json
uv run pms task list --mine --format json
uv run pms task search --mine --format json
```

Current actor-aware behavior includes:

- canonical actor resolution through handles and aliases
- persona and team membership traversal in `--mine`
- direct vs inherited vs effective workload rollups in `actor show`
- public request and response surfaces use semantic role keys such as
  `owner`, `members`, `assignee`, and `actor` for explicit checkout identity
- actor payloads themselves use `ref`, `id`, `actor`, and `links`
- actor-aware ownership and assignee payloads across task, queue, project, goal, objective, plan, and other management surfaces

API actor graph surfaces now include:

- `POST /api/v1/actors`
- `GET /api/v1/actors`
- `GET /api/v1/actors/{actor}`
- `POST /api/v1/actors/{actor}/aliases`
- `POST /api/v1/actors/{actor}/memberships`

MCP actor graph tools include:

- `create_actor`
- `list_actors`
- `get_actor`
- `add_actor_alias`
- `add_actor_membership`

Machine-facing actor detail worth knowing:

- `actor show --format json` exposes direct, inherited, and effective workload rollups
- `task show`, `task list`, `task search`, `task ready`, `task stale`, and `task blocked` expose actor-resolved assignee payloads
- `queue run`, `queue presets`, `work daily`, `work review`, `dashboard`, and `start` propagate actor-aware focus/navigation contracts
- `work graph-report --format json` exposes unified graph slices plus `actor_rollups`
- checkout flows auto-resolve canonical actors for lease ownership and surface that in checkout metadata

Verification helper:

- `uv run python scripts/audit_actor_workload_math.py --check`

Long-form design target:

- [`docs/ACTOR_IDENTITY_PERSONA_GRAPH_ARCHITECTURE.md`](docs/ACTOR_IDENTITY_PERSONA_GRAPH_ARCHITECTURE.md)

## CLI Commands

PMS has a broad CLI. This section restores the broad command-map shape on purpose.
Use it as an index and feature dump, then go deeper in [`docs/CLIENT_GUIDE.md`](docs/CLIENT_GUIDE.md).

### Global commands

```bash
uv run pms --help
uv run pms --version
uv run pms <command> --help
```

For export-oriented examples, see [`docs/CLI_EXPORTS.md`](docs/CLI_EXPORTS.md).

### Actor Commands

Use actor commands when identity, assignment, membership, and "my work" semantics matter more than flat owner strings.

```bash
uv run pms actor create "Alice Example" --kind human --handle alice-example --format json
uv run pms actor list --format json
uv run pms actor show alice-example --format json
uv run pms actor alias add alice-example "alice" --format json
uv run pms actor membership add security-persona alice-example --role representative --format json
```

### Project Commands

Use project commands when the project is your main execution container.

Common commands:

```bash
uv run pms project create "Web API" -d "RESTful API for mobile app" -t backend -t python
uv run pms project list
uv run pms project list --format json
uv run pms project show "Web API" --format json
uv run pms project summary "Web API" --format json
uv run pms project history "Web API"
uv run pms project update "Web API" --status on_hold --format json
uv run pms project complete "Web API" --by matt
```

Use `project show` and `project summary` when you want linked execution and rollups. They now expose machine links and actor rollups, not just names and counts.

See also:

- [`docs/CLIENT_GUIDE.md`](docs/CLIENT_GUIDE.md)
- [`docs/END_TO_END_WORKFLOWS.md`](docs/END_TO_END_WORKFLOWS.md)

### Organization Commands

Use organizations when you need a top-level boundary for teams, portfolios, products, and programs.

```bash
uv run pms org create "Acme Org" --owner matt --member matt --format json
uv run pms org list --format json
uv run pms org show "Acme Org" --format json
uv run pms org summary "Acme Org" --format json
uv run pms org update "Acme Org" --member qa-persona --format json
```

### Team Commands

Use teams when you want an actor grouping or delivery unit under an org.

```bash
uv run pms team create "Core Team" --org "Acme Org" --owner matt --member matt --format json
uv run pms team list --org "Acme Org" --format json
uv run pms team show "Core Team" --format json
uv run pms team update "Core Team" --member qa-persona --format json
```

### Portfolio Commands

Use portfolios when you want rollups across multiple programs or projects.

```bash
uv run pms portfolio create "Platform Portfolio" --org "Acme Org" --owner matt \
  --goal-id <goal-id> --objective-id <objective-id> --format json
uv run pms portfolio list --format json
uv run pms portfolio show "Platform Portfolio" --format json
uv run pms portfolio summary "Platform Portfolio" --format json
uv run pms portfolio dashboard "Platform Portfolio" --format json
```

`goal_ids` and `objective_ids` for portfolios are direct first-class links
backed by native edge tables. `project_ids` on portfolio readbacks is effective
project scope, while `effective_goal_ids` and `effective_objective_ids` expose
the hydrated union of:

- direct portfolio links
- project-derived goal/objective scope

Rule of thumb:

- if an `*_ids` array appears on a read surface, treat it as a hydrated view
  unless the schema documentation explicitly names an edge table as the
  authority
- for portfolios/programs specifically:
  - `goal_ids` / `objective_ids` are the direct strategic links
  - `effective_goal_ids` / `effective_objective_ids` are the hydrated scope
    readbacks
- bootstrap and quickstart flows should link projects by updating the child
  project's scope foreign keys, not by treating parent `project_ids` readbacks
  as the authoritative write source
- remaining JSON columns are kept for descriptive/config payloads, not for core
  graph relationships

### Program Commands

Use programs for a coordinated set of projects inside a portfolio.

```bash
uv run pms program create "Delivery Program" --org "Acme Org" \
  --portfolio "Platform Portfolio" --owner matt \
  --goal-id <goal-id> --objective-id <objective-id> --format json
uv run pms program list --format json
uv run pms program show "Delivery Program" --format json
uv run pms program summary "Delivery Program" --format json
uv run pms program dashboard "Delivery Program" --format json
```

Programs use the same forward model: direct strategic links are stored natively,
while read surfaces expose effective scope across both direct links and linked
projects.

### Product Commands

Use products when you want a product-level home for goals, plans, and projects.

```bash
uv run pms product create "Gateway Platform" --owner matt --format json
uv run pms product list --format json
uv run pms product show "Gateway Platform" --format json
uv run pms product summary "Gateway Platform" --format json
```

### Goal/OKR Commands

Use goals, objectives, and key results when you want strategy to resolve into execution rather than living in a separate system.

```bash
uv run pms goal create "Launch V1" --project "Gateway Launch" --horizon short_term --owner matt --format json
uv run pms goal list --format json
uv run pms goal show "Launch V1" --format json
uv run pms goal summary "Launch V1" --format json

uv run pms objective create "Complete onboarding flow" --goal "Launch V1" --owner matt --format json
uv run pms objective show "Complete onboarding flow" --format json

uv run pms keyresult create "Activation rate" --objective "Complete onboarding flow" --current 35 --target 60 --unit percent --owner matt --format json
uv run pms keyresult show "Activation rate" --format json
```

`goal summary` now distinguishes true goal-linked execution from project-scoped aliases in multi-goal projects. That is intentional and documented, not hidden.

### Plan Commands

Plans are explicit planning artifacts linked into the execution graph.

```bash
uv run pms plan create "Release Plan" --project "Gateway Launch" --format json --content '{"stages":["plan","implement","test"]}' --output-format json
uv run pms plan list --project "Gateway Launch" --format json
uv run pms plan list --task-id <task-id> --format json
uv run pms plan show <plan-id> --format json
uv run pms plan update <plan-id> --status active --format json
uv run pms plan lineage --format json
```

Test-job support exists for plan-linked execution proof too:

```bash
uv run pms plan test-job add <plan-id> "Local smoke tests" . --command "uv run pytest -q"
uv run pms plan test-job run <job-id>
uv run pms plan test-job list <plan-id>
```

### Task Commands

Tasks are the day-to-day execution layer. PMS puts a lot of surface area here because task usability is the control plane.

Common commands:

```bash
uv run pms task add "Gateway Launch" "Implement authentication" -p high -c 8 -t auth
uv run pms task list
uv run pms task list --project "Gateway Launch"
uv run pms task list --project "Gateway Launch" --format json
uv run pms task list --project "Gateway Launch" --view overview
uv run pms task show "Implement authentication" --project "Gateway Launch" --include-linked --format json
uv run pms task search --query auth --format json
uv run pms task ready --project "Gateway Launch" --format json
uv run pms task stale --days 14 --format json
uv run pms task blocked --format json
uv run pms task duplicates --project "Gateway Launch" --format json
uv run pms task graph <task-id> --format json
uv run pms task tree --project "Gateway Launch"
uv run pms task timeline <task-id> --format json
```

Lifecycle commands:

```bash
uv run pms task start <task-id> --by matt --format json
uv run pms task progress <task-id> 25 "Started implementation" --by matt --format json
uv run pms task review <task-id> --by matt
uv run pms task complete <task-id> --by matt --format json
uv run pms task block <task-id> --reason "Waiting for API spec" --by matt
uv run pms task unblock <task-id> --by matt
```

Dependency and duplicate-management commands:

```bash
uv run pms task dep add <task-id> <depends-on-id>
uv run pms task merge-preview <primary-id> --duplicate-id <dup-id>
uv run pms task merge-duplicates <primary-id> --duplicate-id <dup-id> --cancel-duplicates
```

Checkout / active execution lease commands:

```bash
uv run pms task checkout <task-id> --agent-id codex-run-01 --actor matt
uv run pms task renew <task-id> --agent-id codex-run-01
uv run pms task checkout-status --agent-id codex-run-01 --format json
uv run pms task checkout-log --task-id <task-id> --format json
```

Evidence commands:

```bash
uv run pms task evidence add <task-id> scm_commit abc123 --description "Manual commit"
uv run pms task evidence list <task-id> --include-test-runs --format json
```

### Queue And Work Commands

Queues and work surfaces are the main review/control surfaces above raw task CRUD.

```bash
uv run pms queue create "Backend Queue" --filters '{"tags":["backend"],"statuses":["todo","in_progress"]}' --sort-by priority --sort-dir desc
uv run pms queue list --format json
uv run pms queue show <queue-id> --format json
uv run pms queue run <queue-id> --format json
uv run pms queue presets --view detail --format json

uv run pms work snapshot --scope-type project --scope "Gateway Launch" --format json
uv run pms work daily --scope-type project --scope "Gateway Launch" --format json
uv run pms work review --scope-type project --scope "Gateway Launch" --reviewed-by matt --note "Weekly review" --format json
uv run pms work graph-report --scope-type project --scope "Gateway Launch" --format json

uv run pms dashboard --format json
uv run pms start --format json
```

### Comment, Custom Field, And Collaboration Commands

These commands cover collaboration detail that should live next to the work graph instead of in disconnected side systems.

```bash
uv run pms comment add task <task-id> "Need security review" --by alice-example
uv run pms comment list task <task-id> --format json

uv run pms custom-field create "Deployment Window" --entity-type project --type text
uv run pms custom-field list --format json
uv run pms custom-field value set "Deployment Window" --entity-type project --entity-id <project-id> --value "2026-Q2"

uv run pms watcher add task <task-id> alice@example.com
uv run pms watcher list task <task-id> --format json
```

### Evidence, Label, Workflow, And Automation Commands

Use these when you want richer governance than tags and status alone.

```bash
uv run pms label category create "Risk" --exclusive
uv run pms label create "needs-review" --category-id <category-id> --color "#f0b860"
uv run pms label assign task <task-id> needs-review
uv run pms label gate add --workflow-id wf_sdlc --entity-type task --from-state code_review --to-state unit_testing --rule-type require_label --label needs-review

uv run pms evidence gate list --workflow-id wf_sdlc --entity-type task --from-state code_review --to-state unit_testing --format json
uv run pms workflow list --format json
uv run pms workflow show sdlc --format json
uv run pms workflow transition <task-id> code_review --entity-type task --by matt
uv run pms automation rule list --format json
```

PMS also supports label gates and workflow-aware transitions so review/compliance can be expressed directly in the task system.
Automation rule `action_type` is a closed contract:
`add_comment`, `create_task`, `update_task_status`, `set_custom_field_value`.

### Report, Revision, Timeline, And Watcher Commands

These are for history, diffs, exports, and read-model auditing.

```bash
uv run pms report project <project-id> --format json
uv run pms report history --format json
uv run pms report metrics --project <project-id> --format json
uv run pms revision diff task <task-id> --from 1 --to 2 --format json
uv run pms revision bundle task <task-id> --include-linked --format json
uv run pms timeline status task <task-id> --format json
uv run pms timeline workflow task <task-id> --format json
uv run pms watcher list task <task-id> --format json
```

### Test Commands

Use test commands when you want PMS to store test output as first-class proof.

```bash
uv run pms test run . -c "uv run pytest -q" --task-id <task-id>
uv run pms test list --format json
uv run pms test show <run-id> --include-output --include-artifacts
uv run pms test prune --max-age-days 30
uv run pms test retention --format json
```

### Remote Commands

Remote commands support SSH/rsync-style deployment and inspection.

```bash
uv run pms remote add staging 192.168.1.50 deploy -k ~/.ssh/id_rsa -r /var/www/app
uv run pms remote list
uv run pms remote show staging
uv run pms remote test staging
uv run pms remote exec staging "ls -la /var/www/app"
uv run pms remote sync push staging ./src -r /var/www/app/src --dry-run
uv run pms remote sync pull staging /var/log/app ./logs --dry-run
```

### AWS Commands

AWS commands are for test-server provisioning and remote validation.

```bash
uv run pms aws spot find --vcpus 4 --memory 8 --max-price 0.05
uv run pms aws server launch mytest --type t3.large --max-hours 2 --docker
uv run pms aws server list
uv run pms aws server show mytest
uv run pms aws test run mytest . -s "uv sync" -c "uv run pytest -q"
uv run pms aws logs mytest /var/log/app/error.log -f
```

### Agent And Loop Commands

Use these when you want natural-language orchestration or a maintained agent loop around the graph.

```bash
uv run pms run "create a project called MyApp with tasks for auth, database, and API"
uv run pms context show
uv run pms context compact --reason "weekly-reset"
uv run pms loop setup
uv run pms loop show --format json
```

### Config, Auth, Runtime, And Install Commands

These commands control how PMS authenticates, where it writes, and how it integrates with a local Claude/Desktop-style runtime.

```bash
uv run pms config show --format json
uv run pms config set --current-actor alice-example

uv run pms auth init --show-key
uv run pms auth scopes
uv run pms auth list --format json

uv run pms runtime status --format json
uv run pms runtime prefer-server --host 127.0.0.1 --port 27541
uv run pms runtime cleanup

uv run pms install --name pms
uv run pms verify-install --name pms
uv run pms uninstall --name pms
uv run pms serve --host 127.0.0.1 --port 27541
```

### Generate And Meta-Programming Commands

Use these when you want PMS to help create or scaffold more PMS capability.

```bash
uv run pms generate spec "A tool that exports actor workload heatmaps"
uv run pms generate tool "Create a tool that summarizes stale release tasks"
uv run pms generate module ops_reports "List stale releases" "Summarize actor workload" --preview
```

### Capabilities, Namespace, And Plugin Commands

These commands make PMS self-describing.

```bash
uv run pms capabilities info
uv run pms capabilities list --format json
uv run pms capabilities schema --output schema.json
uv run pms capabilities docs --output docs/CAPABILITIES_REFERENCE.md
uv run pms capabilities health --format json

uv run pms namespace list
uv run pms namespace show task
uv run pms namespace schema
uv run pms namespace register cust custom_entity --description "Custom entity type"
uv run pms namespace generate-id task --count 3
uv run pms namespace unregister cust

uv run pms plugin list --format json
uv run pms plugin discover ~/.pms/plugins
uv run pms plugin show <name>
uv run pms plugin new my-plugin
uv run pms plugin tools --format json
uv run pms plugin call <tool-name> --arg key=value
uv run pms plugin validate ./plugins/my-plugin
uv run pms plugin test ./plugins/my-plugin
uv run pms plugin stats
```

`pms namespace show` documents namespace-generated typed-ID families, schema
metadata, and the runtime row-ID contract scope/style for a family. It is
not a blanket claim every public runtime entity family is prefix-native.

Machine-readable namespace schema now exposes separation explicitly through
`namespace_generated_id_format`, `namespace_generated_id_kind`,
`runtime_row_id_contract_scope`, and `runtime_row_id_style`.

Those same fields now surface in `pms namespace show --format json|csv`, so the
interactive text view and machine-readable exports stay aligned. `pms namespace
list --format json|csv` now exports the same contract metadata at list scope.

Interpret those together:

- `runtime_row_id_contract_scope = public_stored_entity_family` means the
  namespace family participates in the public runtime row-ID contract
- `runtime_row_id_contract_scope = internal_or_non_public_namespace` means the
  namespace is visible in the type catalog, but the public runtime row-ID
  contract does not apply there

For deeper command coverage, use [`docs/CLIENT_GUIDE.md`](docs/CLIENT_GUIDE.md).

## MCP / Agent Integration

PMS exposes a broad MCP tool surface so agent platforms can operate PMS directly instead of screen-scraping CLI text.

The README intentionally does not hardcode a giant static MCP tool table anymore.
The live source of truth is the generated capability inventory and the running
server surface.

What matters for release readers:

- PMS exports MCP tools for project, task, plan, queue, actor, and related operations
- PMS also exposes remote and AWS tool families when those integrations are enabled
- PMS includes generated capability metadata and parity audits for the MCP surface
- agent-facing JSON surfaces carry `links`, `next_steps`, `graph_navigation`, `actor_rollups`, and population metadata so agents can continue without bespoke hardcoding

Recommended local integration path:

```bash
uv run pms install --name pms
uv run pms verify-install --name pms
uv run pms serve --host 127.0.0.1 --port 27541
uv run pms capabilities docs --output docs/CAPABILITIES_REFERENCE.md
```

Tool-search and self-discovery path:

```bash
uv run pms capabilities info
uv run pms capabilities list --format json
uv run pms namespace list
uv run pms plugin tools --format json
```

Useful entry points:

```bash
uv run pms run "show me all blocked tasks across projects"
uv run pms start --format json
uv run pms dashboard --format json
```

Relevant docs:

- [`docs/AGENT_INTEGRATION_GUIDE.md`](docs/AGENT_INTEGRATION_GUIDE.md)
- [`docs/WEB_API.md`](docs/WEB_API.md)
- [`docs/CAPABILITIES_REFERENCE.md`](docs/CAPABILITIES_REFERENCE.md)
- [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md)

## Python API And Clients

PMS has multiple client/use paths:

- CLI: primary operator surface
- HTTP API: primary integration surface
- Python HTTP client helpers in [`pms/client/`](pms/client)
- Rust client in [`client-rust/`](client-rust)

Python HTTP client example:

```python
import asyncio

from pms.client.http_client import PMSClient


async def main() -> None:
    async with PMSClient("http://127.0.0.1:27541", api_key="YOUR_API_KEY") as client:
        project = await client.create_project(
            name="Gateway Launch",
            description="Release control for the public API launch",
            tags=["release", "gateway"],
        )
        task = await client.create_task(
            project_id=project["id"],
            title="Publish release notes",
            priority="high",
            tags=["docs"],
        )
        await client.start_task(task["id"], updated_by="alice-example")
        await client.update_progress(
            task["id"], 50, "Draft complete", updated_by="alice-example"
        )


asyncio.run(main())
```

For in-process integrations, PMS also exposes service-layer types such as
[`pms/services/project_service.py`](pms/services/project_service.py) and
[`pms/services/task_service.py`](pms/services/task_service.py), plus repository
and model layers for lower-level control.

Rust client quick path:

```bash
./scripts/install_pms_client.sh
uv run pms auth init --show-key
export PATH="$PWD/.bin:$PATH"
export PMS_API_KEY="$(cat .pms-admin-key)"
pms-client --server http://127.0.0.1:27541 start --format json
```

Useful docs:

- [`docs/CLIENT_GUIDE.md`](docs/CLIENT_GUIDE.md)
- [`docs/WEB_API.md`](docs/WEB_API.md)
- [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md)
- [`client-rust/README.md`](client-rust/README.md)
- [`examples/real_world/README.md`](examples/real_world/README.md)
- [`docs/archive/README.md`](docs/archive/README.md)

The Rust client is kept in parity with the Python CLI through maintained parity audits and smoke flows.

For the maintained network/runtime benchmark proof path, use:

```bash
bash ./scripts/run_network_interop_benchmark_contract_smoke.sh
```

## Architecture

PMS is a local-first graph coordination platform.

### Core design goals

- keep planning and execution in the same graph
- keep ownership and actor identity explicit
- keep proof and review tied to work, not to separate spreadsheets or chat logs
- keep human and agent interfaces aligned
- keep readback truth explicit when runtime/write coordination changes
- keep authoritative graph links in native relational structures instead of
  JSON-array storage; reserve JSON for document content, metadata, and proof
  payloads

### Event-sourcing and revision model

PMS keeps current projections for usability, but it also keeps revision-aware
history so state can be explained instead of only displayed.

Practical consequences:

- revision bundles and diffs can reconstruct why a field changed
- timelines can explain status/workflow movement over time
- audit/report surfaces do not need to guess from the latest row alone

### Typed IDs and graph traversal

PMS uses prefixed IDs across entity families so machines can correlate objects
without brittle text matching.

Examples:

- `proj_<uuid>`
- `task_<uuid>`
- `goal_<uuid>`
- `plan_<uuid>`
- `actor_<uuid>`

The typed-ID model is part of why `graph_navigation`, `links`, and scoped
population metadata can stay consistent across CLI, API, MCP, and generated docs.

### Package structure

| Path                                                          | Responsibility                                     |
| ------------------------------------------------------------- | -------------------------------------------------- |
| [`pms/cli/`](pms/cli)                                         | CLI entrypoints, text views, JSON response shaping |
| [`pms/api/`](pms/api)                                         | FastAPI routes, auth, response models              |
| [`pms/client/`](pms/client)                                   | HTTP client helpers                                |
| [`pms/models/`](pms/models)                                   | domain entities and enums                          |
| [`pms/repositories/`](pms/repositories)                       | storage/query layer                                |
| [`pms/services/`](pms/services)                               | graph math, rollups, orchestration, business logic |
| [`pms/db/`](pms/db)                                           | schema bootstrap, backend setup                    |
| [`pms/tools/`](pms/tools)                                     | MCP tool registry and handlers                     |
| [`pms/runtime/`](pms/runtime)                                 | managed server/runtime coordination                |
| [`pms/reporting/`](pms/reporting)                             | report generation                                  |
| [`pms/workflows/`](pms/workflows)                             | workflow/state-machine definitions                 |
| [`pms/automation/`](pms/automation)                           | event-driven automation                            |
| [`pms/testing/`](pms/testing)                                 | testing helpers and harnesses                      |
| [`pms/aws/`](pms/aws)                                         | AWS test-server support                            |
| [`pms/agents/`](pms/agents)                                   | agent-facing orchestration helpers                 |
| [`pms/plugins/`](pms/plugins)                                 | plugin extension system                            |
| [`pms/learning/`](pms/learning) / [`pms/memory/`](pms/memory) | learning and memory subsystems                     |

### Architecture references

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`docs/WRITE_COORDINATION_ARCHITECTURE.md`](docs/WRITE_COORDINATION_ARCHITECTURE.md)
- [`docs/ACTOR_IDENTITY_PERSONA_GRAPH_ARCHITECTURE.md`](docs/ACTOR_IDENTITY_PERSONA_GRAPH_ARCHITECTURE.md)
- [`docs/VOCABULARY_GOVERNANCE.md`](docs/VOCABULARY_GOVERNANCE.md)
- [`docs/DASHBOARD_USAGE.md`](docs/DASHBOARD_USAGE.md)

## Runtime And Write Truth

PMS is explicit about how writes happen and which runtime handled them.

For mutating commands, request JSON when you need runtime truth:

- JSON output: `runtime_write`

Do not assume `prefer_server` means the server handled the mutation. PMS tells you which path actually wrote.

This matters across create and update surfaces such as:

- `project create`
- `goal create`
- `plan create`
- `task add`
- `task start`
- `task progress`
- `task complete`

Useful runtime commands:

```bash
uv run pms config show --format json
uv run pms runtime prefer-server --host 127.0.0.1 --port 27541
uv run pms serve --host 127.0.0.1 --port 27541
```

Explicit runtime host/port requests are authoritative. PMS keeps a single active
local server per workspace and replaces the previous one cleanly when you
rebind the same `PMS_DATA_DIR` to a new port.

For runtime architecture details, read [`docs/WRITE_COORDINATION_ARCHITECTURE.md`](docs/WRITE_COORDINATION_ARCHITECTURE.md).

## Constraint And Reference Truth

PMS uses layered validation on purpose.

When a write targets linked graph data such as `project_id`, `goal_id`,
`objective_id`, `owner_id`, or `assignee_id`, PMS should validate it at more
than one layer:

1. service-layer reference validation
   - detect obvious bad references before the write
   - suggest likely canonical IDs when the input is close but wrong
   - tell the caller directly if a name/handle was used where an ID is required
2. database constraint enforcement
   - SQLite foreign keys, `CHECK` constraints, and uniqueness are the final
     guardrail
   - these remain active even if a service bug or concurrent write bypasses a
     friendlier validation path

Meaning the operator and machine contract is:

- use canonical IDs when a field is an `_id` field
- expect structured validation failures, not silent coercion
- expect constraint failures to explain what kind of integrity rule failed
- expect common `CHECK` failures to identify the actual category:
  - invalid JSON payloads
  - boolean database flags that must resolve to `0` or `1`
  - non-negative counters, costs, and durations
  - bounded ranges such as `0..100` progress percentages
  - bounded network ports such as `1..65535`
  - stable stored enums such as lifecycle status, sync direction/mode, host
    type, and plan format
- expect likely intended canonical IDs to be suggested when PMS can identify
  them safely
- keep SQLite foreign-key enforcement enabled

This matters especially for machine-driven use, where bad references should
fail with useful recovery hints instead of leaving dangling graph edges in the
state store.

Current rule of thumb:

- stable lifecycle/storage vocabularies should be database-authoritative
- intentionally extensible vocabularies such as workflow state names,
  extension-facing entity types, and plugin-defined concepts should remain
  open unless PMS first promotes them to a governed catalog
- monetary storage and monetary transport use different contracts on purpose:
  - authoritative database columns may use native numeric storage
  - pricing/cost logic may use `Decimal` in service/domain code
  - machine-readable CLI/API/event payloads should emit plain decimal strings
    rather than JSON floats when the value is conceptually money

Transactional rule of thumb:

- one repository write against one event-sourced aggregate should be safe to
  call directly because the public repository write owns its own transaction
- one higher-level logical mutation that spans multiple repositories or tables
  should own one outer service transaction and call explicit in-transaction
  helpers rather than chaining independent public writes and hoping they commit
  together
- on SQLite, concurrent tasks share one physical connection, so PMS now
  serializes connection ownership during an open transaction instead of letting
  background work interleave statements into someone else's atomic unit
- CLI, runner, and orchestration layers can record telemetry after a logical
  result is already committed or returned, but that telemetry is observational;
  late storage failure there should be logged and dropped instead of changing
  the underlying command/result outcome
- on PostgreSQL, an open transaction is now scoped to the owning asyncio task,
  so child tasks do not inherit and accidentally reuse a pooled transaction
  connection after the parent scope exits
- when one logical mutation also touches the filesystem, the database
  transaction remains authoritative and external file cleanup should happen
  after commit, not before, so rollback cannot leave the database claiming
  state that external side effects already destroyed

Good transactional patterns:

```python
# Repository-owned atomic write for one aggregate.
async def save_comment(self, model: Comment) -> Comment:
    async def _save() -> Comment:
        return await self._save_in_transaction(
            model,
            event_type="comment.saved",
            payload=model.model_dump(mode="json"),
        )
    return await self._run_in_owned_transaction(_save, operation_name="save_comment")
```

```python
# Service-owned atomic write for one logical mutation spanning multiple writes.
async def add_comment_with_mentions(self, create: CommentCreate) -> Comment:
    async with self.db.transaction():
        comment = await self._comment_repo.create_in_transaction(create)
        await self._mention_repo.replace_for_comment_in_transaction(
            comment.id,
            create.mentions,
        )
        await self.metrics.flush()
    return comment
```

Bad transactional patterns:

- chaining two public repository writes and assuming they commit together
- calling an internal repository `_..._in_transaction()` helper without already
  owning the outer transaction
- mutating authoritative database state and then doing a required follow-up
  write outside the same outer transaction
- deleting files or external artifacts before the database commit that proves
  the delete should exist
- treating read-only telemetry as authoritative state; `list`, `get`, `show`,
  and search-style metrics can happen after the read because they do not define
  graph truth
  - if those observational metrics fail late, log and drop the telemetry
    failure instead of replacing the underlying read/operation result

## How PMS Is Used To Manage PMS Itself

PMS is being used to manage PMS development itself.

Including branches such as:

- graph workflow architecture consistency
- actor/persona rollout
- goal-scoped execution and unified graph reporting
- release readiness and public documentation

The internal loop is the same public loop:

```bash
uv run pms project create "PMS Release Readiness and Public Documentation"
uv run pms goal create "Make PMS release-ready for public readers" \
  --project "PMS Release Readiness and Public Documentation"
uv run pms plan create "PMS Release Documentation Plan" \
  --project "PMS Release Readiness and Public Documentation" \
  --format yaml \
  --content $'deliverables:\n  - README\n  - documentation map\n  - release audit\n'
uv run pms task add "PMS Release Readiness and Public Documentation" \
  "Rewrite README for public release"
uv run pms work graph-report --scope-type project \
  --scope "PMS Release Readiness and Public Documentation" \
  --format json
```

That loop should be explicit. PMS work should not be done "by feeling".

When PMS is being used to evolve PMS itself, the work should be represented as
separate tracked tasks such as:

- audit contract residue
- normalize interfaces
- decide open-vs-closed vocabulary contracts before adding schema checks
- update docs and examples
- run validation and collect proof

Typical self-management execution loop:

```bash
uv run pms task add "PMS Release Readiness and Public Documentation" \
  "Audit public contract residue"
uv run pms task add "PMS Release Readiness and Public Documentation" \
  "Normalize CLI and API payloads"
uv run pms task add "PMS Release Readiness and Public Documentation" \
  "Update self-hosting and machine-interface docs"
uv run pms task add "PMS Release Readiness and Public Documentation" \
  "Run validation checkpoint"

uv run pms task start "Normalize CLI and API payloads" \
  --project "PMS Release Readiness and Public Documentation" \
  --by codex
uv run pms task progress "Normalize CLI and API payloads" \
  --project "PMS Release Readiness and Public Documentation" \
  65 "Normalized assignee, ownership, members, and checkout payloads" \
  --by codex
uv run pms task evidence add "Normalize CLI and API payloads" \
  note normalization-pass-01 \
  --project "PMS Release Readiness and Public Documentation" \
  --description "Updated CLI/API/docs/tests to semantic role keys"
uv run pms task complete "Normalize CLI and API payloads" \
  --project "PMS Release Readiness and Public Documentation" \
  --by codex
```

For schema and integrity work, split the work more explicitly:

- audit schema/layout gaps
- implement reference validation and constraint translation
- tighten schema checks and indexes
- convert authoritative JSON-array links into native relational tables
- govern extension-facing open vocabularies so they stay open by contract until
  a real registry or closed enum exists
- tighten closed response-model vocabularies and regenerate contract docs so
  examples and machine-readable schemas stay aligned
- repair fixtures and examples under the stricter integrity model
- refresh generated contracts and docs
- run proof-oriented validation slices

Example hardening loop:

```bash
uv run pms task add "PMS Platform Evolution" \
  "Plan schema hardening and constraint error UX"
uv run pms task add "PMS Platform Evolution" \
  "Implement structured constraint translation and reference suggestions"
uv run pms task add "PMS Platform Evolution" \
  "Normalize schema relationships and add stronger checks"
uv run pms task add "PMS Platform Evolution" \
  "Relationalize org/team memberships and plan task links"
uv run pms task add "PMS Platform Evolution" \
  "Relationalize portfolio/program goal and objective links"
uv run pms task add "PMS Platform Evolution" \
  "Convert network environment server membership to a native edge table"
uv run pms task add "PMS Platform Evolution" \
  "Audit and standardize monetary precision semantics across DB and interfaces"
uv run pms task add "PMS Platform Evolution" \
  "Clarify and regression-test extension-facing open vocabularies"
uv run pms task add "PMS Platform Evolution" \
  "Audit and normalize product team semantics away from relation-like JSON if authoritative"

uv run pms task start "Implement structured constraint translation and reference suggestions" \
  --project "PMS Platform Evolution" \
  --by codex
uv run pms task progress "Implement structured constraint translation and reference suggestions" \
  --project "PMS Platform Evolution" \
  70 "API and DB failures now render as structured validation or constraint errors with suggestions" \
  --by codex
uv run pms task progress "Normalize schema relationships and add stronger checks" \
  --project "PMS Platform Evolution" \
  70 "FK-sensitive tests and examples now create canonical projects and actors under the hardened schema" \
  --by codex
uv run pms task progress "Relationalize org/team memberships and plan task links" \
  --project "PMS Platform Evolution" \
  65 "organization_members, team_members, plan_tasks, and plan_test_job_tasks now hold authoritative graph edges" \
  --by codex
uv run pms task progress "Relationalize portfolio/program goal and objective links" \
  --project "PMS Platform Evolution" \
  60 "portfolio_goals, portfolio_objectives, program_goals, and program_objectives now hold direct strategic links while readbacks merge them with project scope" \
  --by codex
uv run pms task progress "Convert network environment server membership to a native edge table" \
  --project "PMS Platform Evolution" \
  70 "network_environment_servers now holds the authoritative environment -> server edges so role-aware network environments can use native joins" \
  --by codex
uv run pms task progress "Audit and standardize monetary precision semantics across DB and interfaces" \
  --project "PMS Platform Evolution" \
  30 "Confirmed authoritative pricing/cost columns are already native numeric values; remaining work is aligning DB REAL storage, in-memory Decimal use, and JSON/event string transport semantics deliberately" \
  --by codex
uv run pms task progress "Audit and normalize product team semantics away from relation-like JSON if authoritative" \
  --project "PMS Platform Evolution" \
  60 "products.team is now explicitly treated as descriptive metadata rather than a hidden Team-entity relation" \
  --by codex
uv run pms task evidence add "Implement structured constraint translation and reference suggestions" \
  note constraint-hardening-pass-01 \
  --project "PMS Platform Evolution" \
  --description "Typed integrity translation, reference suggestions, FK/json checks, and regression slices passing"
uv run pms task complete "Implement structured constraint translation and reference suggestions" \
  --project "PMS Platform Evolution" \
  --by codex
```

That matters for a public reader because PMS is actively used to manage:

- architecture refactors
- discoverability and graph-surface work
- actor identity rollout
- release-audit and documentation branches

The point is not only tracking status. The point is that PMS should be able to
tell an operator or an agent:

- what the current task is
- what changed
- what proof exists
- what remains next

## Documentation Map

Start here, in this order:

1. [`README.md`](README.md)
   - public overview, common workflows, command map
2. [`docs/IMMEDIATE_START_GO.md`](docs/IMMEDIATE_START_GO.md)
   - fastest entrypoint for live operator use
3. [`docs/MACHINE_INTERFACE_GUIDE.md`](docs/MACHINE_INTERFACE_GUIDE.md)
   - progressive machine-first operating model for agents and integrations
4. [`docs/AGENT_INTEGRATION_GUIDE.md`](docs/AGENT_INTEGRATION_GUIDE.md)
   - hook, wrapper, and automation integration patterns for common agent harnesses
5. [`docs/END_TO_END_WORKFLOWS.md`](docs/END_TO_END_WORKFLOWS.md)
   - richer end-to-end project modeling flows
6. [`docs/CLIENT_GUIDE.md`](docs/CLIENT_GUIDE.md)
   - detailed CLI and machine-readable behavior
7. [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
   - architecture and package-level design
8. [`docs/ID_CONTRACT_ARCHITECTURE.md`](docs/ID_CONTRACT_ARCHITECTURE.md)
   - current runtime ID styles, namespace/type-catalog split, and forward
     promotion rules
9. [`docs/VOCABULARY_GOVERNANCE.md`](docs/VOCABULARY_GOVERNANCE.md)
   - which text fields are closed enums, registry-backed, or intentionally open
10. [`docs/ACTOR_IDENTITY_PERSONA_GRAPH_ARCHITECTURE.md`](docs/ACTOR_IDENTITY_PERSONA_GRAPH_ARCHITECTURE.md)

- actor/persona graph architecture reference

11. [`docs/WEB_API.md`](docs/WEB_API.md) and [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md)

- HTTP integration surface

12. [`docs/CAPABILITIES_REFERENCE.md`](docs/CAPABILITIES_REFERENCE.md)

- generated capability inventory

13. [`docs/DOCUMENTATION_MAP.md`](docs/DOCUMENTATION_MAP.md)

- audience-based routing through the docs set

14. [`docs/archive/README.md`](docs/archive/README.md)

- historical plans, audits, and superseded scenario writeups kept out of the live operator path

## API And Contract References

If you are evaluating PMS as an integration surface, these are the highest-value references:

- [`docs/API_ENDPOINT_CATALOG.md`](docs/API_ENDPOINT_CATALOG.md)
- [`docs/API_RESPONSE_CONTRACTS.md`](docs/API_RESPONSE_CONTRACTS.md)
- [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md)
- [`docs/WEB_API.md`](docs/WEB_API.md)

Use them together:

- [`docs/API_ENDPOINT_CATALOG.md`](docs/API_ENDPOINT_CATALOG.md) is the generated route inventory
- [`docs/API_RESPONSE_CONTRACTS.md`](docs/API_RESPONSE_CONTRACTS.md) is the generated response wrapper/schema inventory
- [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md) is the richer human-written walkthrough
- [`docs/WEB_API.md`](docs/WEB_API.md) explains how to run and use the server

Regenerate generated API docs with:

```bash
uv run python scripts/generate_api_endpoint_catalog.py --output docs/API_ENDPOINT_CATALOG.md
uv run python scripts/generate_api_response_contracts.py --output docs/API_RESPONSE_CONTRACTS.md
```

## Real-World Scenario Packs

These are the best way to see PMS behave under realistic operating conditions without forcing every detail into the README.

### Drop-In Growth

- flow: [`./scripts/run_dropin_start_go_extend_grow.sh`](./scripts/run_dropin_start_go_extend_grow.sh)
- contract smoke: [`./scripts/run_dropin_contract_smoke.sh`](./scripts/run_dropin_contract_smoke.sh)
- guide: [`examples/real_world/README.md#scenario-dropin`](examples/real_world/README.md#scenario-dropin)
- env example: [`examples/real_world/dropin.env.example`](examples/real_world/dropin.env.example)

### Team Handoff

- flow: [`./scripts/run_team_handoff_flow.sh`](./scripts/run_team_handoff_flow.sh)
- contract smoke: [`./scripts/run_team_handoff_contract_smoke.sh`](./scripts/run_team_handoff_contract_smoke.sh)
- guide: [`examples/real_world/README.md#scenario-team-handoff`](examples/real_world/README.md#scenario-team-handoff)
- env example: [`examples/real_world/team_handoff.env.example`](examples/real_world/team_handoff.env.example)

### Incident Response

- flow: [`./scripts/run_incident_response_flow.sh`](./scripts/run_incident_response_flow.sh)
- contract smoke: [`./scripts/run_incident_response_contract_smoke.sh`](./scripts/run_incident_response_contract_smoke.sh)
- guide: [`examples/real_world/README.md#scenario-incident-response`](examples/real_world/README.md#scenario-incident-response)
- env example: [`examples/real_world/incident_response.env.example`](examples/real_world/incident_response.env.example)

### User Start -> Go -> Observe

- flow: [`./scripts/run_user_start_go_observe_flow.sh`](./scripts/run_user_start_go_observe_flow.sh)
- contract smoke: [`./scripts/run_user_start_go_observe_contract_smoke.sh`](./scripts/run_user_start_go_observe_contract_smoke.sh)
- guide: [`examples/real_world/README.md#scenario-user-start-go-observe`](examples/real_world/README.md#scenario-user-start-go-observe)
- env example: [`examples/real_world/user_start_go_observe.env.example`](examples/real_world/user_start_go_observe.env.example)

### Operational Review

- flow: [`./scripts/run_operational_review_flow.sh`](./scripts/run_operational_review_flow.sh)
- contract smoke: [`./scripts/run_operational_review_contract_smoke.sh`](./scripts/run_operational_review_contract_smoke.sh)
- guide: [`examples/real_world/README.md#scenario-operational-review`](examples/real_world/README.md#scenario-operational-review)
- env example: [`examples/real_world/operational_review.env.example`](examples/real_world/operational_review.env.example)

### Backlog Triage

- flow: [`./scripts/run_backlog_triage_flow.sh`](./scripts/run_backlog_triage_flow.sh)
- contract smoke: [`./scripts/run_backlog_triage_contract_smoke.sh`](./scripts/run_backlog_triage_contract_smoke.sh)
- guide: [`examples/real_world/README.md#scenario-backlog-triage`](examples/real_world/README.md#scenario-backlog-triage)
- env example: [`examples/real_world/backlog_triage.env.example`](examples/real_world/backlog_triage.env.example)

### Portfolio Steering

- flow: [`./scripts/run_portfolio_steering_flow.sh`](./scripts/run_portfolio_steering_flow.sh)
- contract smoke: [`./scripts/run_portfolio_steering_contract_smoke.sh`](./scripts/run_portfolio_steering_contract_smoke.sh)
- guide: [`examples/real_world/README.md#scenario-portfolio-steering`](examples/real_world/README.md#scenario-portfolio-steering)
- env example: [`examples/real_world/portfolio_steering.env.example`](examples/real_world/portfolio_steering.env.example)

### Agent Execution Loop

- flow: [`./scripts/run_agent_execution_loop_flow.sh`](./scripts/run_agent_execution_loop_flow.sh)
- contract smoke: [`./scripts/run_agent_execution_loop_contract_smoke.sh`](./scripts/run_agent_execution_loop_contract_smoke.sh)
- guide: [`examples/real_world/README.md#scenario-agent-execution-loop`](examples/real_world/README.md#scenario-agent-execution-loop)
- env example: [`examples/real_world/agent_execution_loop.env.example`](examples/real_world/agent_execution_loop.env.example)

## When To Use / When Not To Use

### Use PMS when

- you need planning and execution in one graph
- you want goals, plans, tasks, evidence, and review to resolve into each other
- you want humans and agents to operate against the same truth surface
- you need machine-readable command continuations, not just text output
- you want local-first control with optional managed server coordination
- you need proof and auditability, not just status fields

### Do not start with PMS when

- you only need a flat checklist with no graph or reporting needs
- you do not care about traceability from goals/plans down to tasks and proof
- you want a narrow SaaS-only workflow with minimal local control
- you are unwilling to use a system that exposes a large surface area for advanced operators and agents

### Use direct CRUD vs agentic commands deliberately

Use direct CLI commands for:

- fast, deterministic CRUD
- scripts and automation
- release and audit flows
- precise machine-readable control

Use agent/loop surfaces for:

- natural-language orchestration
- self-directed execution loops
- exploratory multi-step continuation where the agent benefits from graph discovery

### Feature decision guide

| Need                         | Prefer                                             | Avoid                                   |
| ---------------------------- | -------------------------------------------------- | --------------------------------------- |
| Create a project quickly     | `pms project create`                               | `pms run` for simple CRUD               |
| Bootstrap a real workspace   | `pms quickstart --defaults`                        | hand-creating every starter object      |
| Check live state             | `pms start` or `pms dashboard`                     | reading only `project list`             |
| Review scoped execution      | `pms work daily` / `pms work review`               | a flat task dump with no review context |
| Explore the graph            | `task show --include-linked` / `work graph-report` | manually correlating titles             |
| Enforce review gates         | `label gate add` / `workflow transition`           | ad hoc status conventions in chat       |
| Remote deployment inspection | `pms remote exec` / `pms remote sync`              | manual SSH/rsync muscle memory          |
| Repeated warm-server reads   | `pms-client`                                       | repeated cold-start CLI invocations     |

## Development And Validation

Useful commands:

```bash
uv run pytest
uv run pytest tests/integration/test_cli.py -v
uv run mypy pms/
uv run ruff check pms tests scripts
uv run ruff format pms tests scripts
./scripts/run_audit_checks.sh
uv run python scripts/audit_docs_runtime_truth.py --check
uv run python scripts/audit_release_version_consistency.py --check
uv run pms capabilities docs --output docs/CAPABILITIES_REFERENCE.md
```

Tooling and extension development:

- [`docs/TOOL_DEVELOPMENT.md`](docs/TOOL_DEVELOPMENT.md) for adding or evolving tools cleanly
- `uv run pms generate spec ...`, `uv run pms generate tool ...`, and `uv run pms generate module ...` for meta-programming support
- `uv run pms plugin new`, `uv run pms plugin validate`, and `uv run pms plugin test` for plugin workflows

Release/readiness helpers:

```bash
./scripts/run_docs_smoke.sh
./scripts/run_audit_checks.sh --list-stages
./scripts/run_audit_checks.sh validate-docs-and-parity
PMS_AUDIT_SKIP_TESTS=1 ./scripts/run_audit_checks.sh all-preflight
./scripts/run_release_readiness_flow.sh
./scripts/run_release_readiness_contract_smoke.sh
```

If you accumulate fixture/test residue in a development workspace, classify it first:

```bash
uv run python scripts/cleanup_fixture_backlog.py
uv run python scripts/cleanup_fixture_backlog.py --apply
```

## Release Snapshot And Compatibility Notes

Current public-release positioning:

- version: `0.1.0`
- capability inventory is generated from the live CLI/API surface
- CLI/API/MCP parity and contract audits are part of the maintained audit gate
- Rust client parity is audited against the Python CLI surface

Platform notes:

- the public identity model is `Actor`
- actor identity is the only exposed identity model across the active platform surface
- public request and response surfaces are actor-native
- PMS defaults to local-first SQLite but also supports PostgreSQL-backed operation
- some advanced surfaces are intentionally broad because PMS is designed for self-discovering agent use, not only human tutorial reading

If you want the strongest public-release gate before tagging a release, run:

```bash
./scripts/run_public_release_gate.sh
```
