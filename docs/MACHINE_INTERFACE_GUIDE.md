# Machine Interface Guide

PMS is not only a human task tracker. It is a machine-interface API and control
plane for language models, autonomous agents, and mixed human/agent teams.

The public docs should make two things clear at the same time:

- humans can start with a few workflows and understand the system progressively
- advanced agents can discover a much deeper graph surface and operate against
  it directly, including nested JSON payloads, UUID-native graph traversal,
  actor-aware assignment, proof collection, and time-based readback

This guide explains how to use PMS that way.

## Read Order

If you are building an agent runtime or machine integration, read these in this
order:

1. [`README.md`](../README.md)
2. [`docs/IMMEDIATE_START_GO.md`](IMMEDIATE_START_GO.md)
3. [`docs/MACHINE_INTERFACE_GUIDE.md`](MACHINE_INTERFACE_GUIDE.md)
4. [`docs/AGENT_INTEGRATION_GUIDE.md`](AGENT_INTEGRATION_GUIDE.md)
5. [`docs/CLIENT_GUIDE.md`](CLIENT_GUIDE.md)
6. [`docs/WEB_API.md`](WEB_API.md)
7. [`docs/API_REFERENCE.md`](API_REFERENCE.md)
8. [`docs/ARCHITECTURE.md`](ARCHITECTURE.md)
9. [`docs/ACTOR_IDENTITY_PERSONA_GRAPH_ARCHITECTURE.md`](ACTOR_IDENTITY_PERSONA_GRAPH_ARCHITECTURE.md)
10. [`docs/VOCABULARY_GOVERNANCE.md`](VOCABULARY_GOVERNANCE.md)
11. [`docs/CAPABILITIES_REFERENCE.md`](CAPABILITIES_REFERENCE.md)

That sequence gives you:

- operator-facing entrypoints first
- harness integration patterns and hook automation next
- machine-readable continuation contracts second
- deeper package and graph semantics third
- the broad generated inventory last

## Which Interface To Use

Choose the interface based on where the agent runs and how much coordination it
needs.

- CLI
  - best for a local agent already operating in the repo/workspace
  - strongest operator parity
  - exposes review-first text plus machine-readable JSON
- HTTP API
  - best for multi-process, remote, or service-to-service integrations
  - better when many agents or runtimes need one shared coordinated state
- MCP
  - best when the host agent platform wants tool search and tool-call routing
  - keeps PMS as a discoverable external capability plane

Design rule:

- do not hardcode one interface unless you need to
- keep your internal control logic aligned to PMS concepts, not transport

## Progressive Usage Levels

### Level 0: Discover The Live Workspace

Start with control planes, not CRUD.

CLI:

```bash
uv run pms start --format json
uv run pms dashboard --format json
uv run pms capabilities info
uv run pms capabilities list --format json
```

API:

```text
GET /api/v1/discoverability/graph
GET /api/v1/observability/overview
```

At this level, the agent should answer:

- is there active visible work?
- is there a focus task?
- what should I run next?
- which docs or scenario packs should I inspect?

### Level 1: Follow The Focus Task Loop

Once PMS provides a `focus_task`, follow its continuation links instead of
reconstructing the next command yourself.

Typical loop:

```bash
uv run pms start --format json
uv run pms task show <task-id> --include-linked --format json
uv run pms task progress <task-ref> <percent> <message> --by <actor>
uv run pms task evidence list <task-ref> --format json
uv run pms work daily --scope-type project --scope <project> --format json
```

Core machine-readable fields:

- `focus_task`
- `next_steps`
- `links`
- `graph_navigation`
- `runtime`
- `runtime_write` on mutation responses

### Level 2: Traverse The Graph Instead Of Flattening It

PMS is intentionally graph-native. A strong agent should move across related
entities instead of reducing everything to a flat task list.

Typical graph traversal sequence:

```bash
uv run pms task show <task-id> --include-linked --format json
uv run pms plan list --task-id <task-id> --format json
uv run pms project show <project-id> --format json
uv run pms goal summary <goal-id> --format json
uv run pms work graph-report --scope-type project --scope-id <project-id> --format json
```

Useful reverse edges already exposed:

- task -> plans
- task -> project
- task -> parent/subtasks
- task -> dependencies/dependents
- plan -> project / goal / objective / tasks
- project / goal / objective / plan -> linked tasks and execution rollups

For stable lifecycle reads, prefer the maintained JSON aggregate surfaces:

- goals:
  - CLI `goal list/show/summary --format json`
  - API `GET /api/v1/goals`, `GET /api/v1/goals/<id>`,
    `GET /api/v1/goals/<id>/summary`
  - MCP `list_goals`, `get_goal`, `get_goal_summary`
- projects:
  - CLI `project show/summary --format json`
  - API `GET /api/v1/projects/<id>`, `GET /api/v1/projects/<id>/summary`
  - MCP `get_project`, `get_project_summary`

Do not treat every surface as part of that maintained aggregate contract:

- `start` is an operator guide, not a lifecycle aggregate parity surface
- text/table/csv output is human-facing, not schema-stable
- widened linked/history/generated variants need their own explicit audit before
  you treat them as interchangeable machine contracts

### Level 3: Use Actors, Memberships, And Checkout Identity

Agents should not collapse ownership and execution into one free-form string.
Use the actor model.

```bash
uv run pms actor create "Release Bot" --kind runtime_agent --handle release-bot --format json
uv run pms actor create "QA Persona" --kind persona --handle qa-persona --format json
uv run pms actor membership add qa-persona release-bot --role representative --format json
uv run pms config set --current-actor release-bot
uv run pms task list --mine --format json
uv run pms task checkout <task-ref> --actor release-bot --agent-id release-loop-01
```

Important payload families:

- `assignee`
- `checkout`
- `ownership`
- `actor_rollups`
- `project_workloads`

Read these as separate meanings:

- assignee: who the work is for
- checkout: who is actively executing it right now
- ownership: who is responsible for the container or strategic node

### Level 4: Operate On Deep Structured Payloads

Human readers usually stop at titles, statuses, and next steps. Agents do not
have to.

PMS can carry deeply structured content and machine correlations directly:

- plan `content`
- evidence `metadata`
- report and graph surfaces
- linked IDs across projects, goals, plans, tasks, actors, and results

Example API body for a plan with nested machine-native structure:

```json
{
  "name": "Release Coordination Plan",
  "format": "json",
  "project_id": "613b1e6d-370d-4633-a420-f5e077aa67f5",
  "content": {
    "external_correlation": {
      "run_id": "release-run-2026-04-14-01",
      "source_system": "agent-orchestrator",
      "upstream_refs": ["wf_2026_04_14_main", "proof_bundle_pending"]
    },
    "execution": {
      "lanes": [
        {
          "name": "release",
          "actor": "release-bot",
          "tasks": ["<task-id-publish-notes>", "<task-id-approve-launch>"]
        },
        {
          "name": "qa",
          "actor": "qa-persona",
          "tasks": ["<task-id-smoke-tests>"]
        }
      ],
      "handoffs": [
        {
          "from": "release",
          "to": "qa",
          "proof_required": true
        }
      ]
    }
  }
}
```

Guideline:

- if PMS gives you a stable ID field, use it
- if you need additional machine correlation, store it in explicit structured
  payloads instead of encoding it into titles

### Level 5: Use Graph Reports As The High-Density Surface

`work graph-report` is the broadest current machine-facing readback surface for
scoped execution.

```bash
uv run pms work graph-report --scope-type project --scope-id <project-id> --format json
```

It already unifies:

- `projects`
- `goals`
- `objectives`
- `key_results`
- `plans`
- `tasks`
- `results`
- `focus_task`
- `graph_navigation`
- `actor_rollups`

This is the right surface when an agent wants one scoped export instead of many
entity-by-entity reads.

## Core Contract Fields To Depend On

The most important machine-readable fields are consistent across major entry
surfaces.

### Continuation Fields

- `links`
  - direct runnable follow-up commands or related surfaces
- `next_steps`
  - prioritized runnable continuations
- `graph_navigation`
  - task-centered or scope-centered traversal bundle

### Focus And Scope Fields

- `focus_task`
  - best actionable task for the current entry surface
- `scope`
  - what the current surface is about
- `params`
  - explicit rendering/filter parameters on list/report surfaces
- `page`
  - pagination metadata for collections

### Population Truth Fields

- `population_basis`
- `visible_totals`
- `instance_totals`
- `execution.population_basis`
- `execution.readiness_state`
- `execution.consistency_status`

These fields exist so an agent does not have to guess what a rollup actually
means.

Lifecycle aggregate note:

- maintained goal, objective, project, and key-result JSON surfaces all expose
  `links`, `next_steps`, bubbled `last_activity_at`, bubbled
  `last_transition_at`, and top-level `terminal_reason`
- key results are leaf lifecycle surfaces, so they intentionally stop at
  `effective_rollup`; they do not expose `effective_hierarchy` or `execution`

### Runtime Truth Fields

- `runtime.coordination`
- `runtime.managed_servers`
- `runtime_write`

These matter when the same graph may be read and written through direct SQLite,
managed local server delegation, or remote HTTP clients.

Runtime guardrail:

- PMS keeps one active local server per `PMS_DATA_DIR`
- an explicit rebind to a new host/port replaces the previous active server
  cleanly instead of leaving duplicate local runtime processes behind

## Illustrated JSON Progression

### `start --format json`

This is the top-level entrypoint for autonomous discovery.

```json
{
  "purpose": "Practical start -> go entry point for discovering live state, fastest first action, and where to extend next.",
  "live_state": {
    "projects": 1,
    "tasks": 2,
    "ready_tasks": 1,
    "in_progress_tasks": 1
  },
  "focus_task": {
    "id": "96183fb8-4de8-4cfc-8cf3-521bf7d13ccd",
    "title": "Docs Active Task",
    "status": "in_progress",
    "project_name": "Docs Project"
  },
  "graph_navigation": {
    "basis": "focus_task",
    "task_id": "96183fb8-4de8-4cfc-8cf3-521bf7d13ccd"
  },
  "links": {
    "dashboard": "uv run pms dashboard --format json",
    "guide": "uv run pms start --format json",
    "quickstart": "uv run pms quickstart --defaults"
  }
}
```

### `task show --include-linked --format json`

Use task detail to move from execution into the surrounding graph.

```json
{
  "id": "96183fb8-4de8-4cfc-8cf3-521bf7d13ccd",
  "title": "Docs Active Task",
  "status": "in_progress",
  "current_progress_percent": 10,
  "context": {
    "project": {
      "id": "613b1e6d-370d-4633-a420-f5e077aa67f5",
      "name": "Docs Project"
    },
    "subtask_count": 0,
    "dependency_count": 0,
    "dependent_count": 0
  },
  "linked_plan_count": 1,
  "links": {
    "project": "uv run pms project show 613b1e6d-370d-4633-a420-f5e077aa67f5 --format json",
    "plans": "uv run pms plan list --task-id 96183fb8-4de8-4cfc-8cf3-521bf7d13ccd --format json"
  }
}
```

### `work graph-report --format json`

Use graph-report when you want a scoped export rather than a single-entity
inspection.

```json
{
  "scope": {
    "kind": "work_graph_report",
    "scope_type": "project",
    "scope_name": "Docs Project"
  },
  "projects": {
    "population_basis": "project_visible_projects"
  },
  "plans": {
    "population_basis": "project_scope_plans"
  },
  "tasks": {
    "population_basis": "project_scope_all_tasks"
  },
  "focus_task": {
    "id": "96183fb8-4de8-4cfc-8cf3-521bf7d13ccd",
    "title": "Docs Active Task",
    "status": "in_progress"
  },
  "actor_rollups": {
    "population_basis": "project_graph_visible_entities"
  }
}
```

## Rules For Robust Autonomous Use

Treat these as hard operational rules.

1. Prefer IDs over titles when an ID is available.
2. Prefer `links` and `next_steps` over reconstructing commands from memory.
3. Read `population_basis` before interpreting counts or rollups.
4. Read `runtime_write` after mutations instead of assuming where the write landed.
5. Use semantic role keys such as `owner`, `members`, `assignee`, and checkout
   metadata, and treat actor payload objects with `ref`, `id`, `actor`, and
   `links` as the durable identity surface.
6. In multi-goal projects, read `execution.population_basis` before assuming a
   goal owns all project execution.
7. Treat hidden/history/operator-visible distinctions as real state boundaries.
8. Use structured JSON payloads for correlation and provenance instead of
   inventing title-parsing conventions.
9. Use JSON for document-like payloads, metadata, and proof, but expect
   authoritative graph links to resolve through canonical IDs and native
   relational edges.
10. Treat `_id` fields as canonical-ID fields, not fuzzy name fields.
11. Expect PMS to reject invalid linked writes with structured validation or
    constraint errors instead of silently coercing them.
12. Do not assume every valid `entity_type` appears in `pms namespace list`.
    The namespace registry is a type catalog and typed-ID utility surface, not
    a guarantee about runtime row-ID style for every public entity family.
13. Treat runtime entity IDs as opaque canonical tokens. Unless PMS documents a
    family as prefix-native, expect live stored IDs to be UUID-native today.

## Validation And Constraint Contract

For machine integrations, write safety should be explicit.

PMS uses a layered contract:

1. reference validation before write
   - catches obvious missing or invalid linked IDs
   - may suggest likely canonical IDs when the input is close
2. database enforcement at write time
   - foreign keys
   - uniqueness
   - `CHECK` constraints for ranges and structured fields such as JSON
3. structured error responses
   - validation failures should tell you which field was wrong
   - constraint failures should tell you what kind of integrity rule failed

Operational rules:

- if a field is named `*_id`, send the canonical ID
- if a response includes suggestions, prefer those over retrying with guessed values
- do not assume a failed write was partial; read back the graph state explicitly
- when automating retries, distinguish validation errors from checkout conflicts and from duplicate/unique violations
- when PMS suggests likely canonical IDs, treat them as recovery candidates
  rather than free-form hint text

This is part of PMS being a machine interface rather than just a CLI wrapper.
The platform should not let agents create broken graph edges and then force
them to debug raw database strings afterward.

## PMS Managing PMS

PMS is already being used to manage PMS itself. That matters because the machine
interface is not hypothetical.

Hard rule for autonomous use:

- do not refactor or normalize "by feeling"
- create explicit tasks for audit, implementation, docs, and validation
- move those tasks through `start`, `progress`, evidence capture, and `complete`

Typical self-management loop:

```bash
uv run pms start --format json
uv run pms task show <focus-task-id> --include-linked --format json
uv run pms task start <focus-task-ref> --by <actor>
uv run pms task progress <focus-task-ref> <percent> <message> --by <actor>
uv run pms task evidence add <focus-task-ref> note <reference> --description <text>
uv run pms task complete <focus-task-ref> --by <actor>
uv run pms work graph-report --scope-type project --scope-id <project-id> --format json
uv run pms dashboard --format json
```

For PMS evolving PMS, split the work intentionally:

1. audit residue
2. normalize code and interfaces
3. update docs and examples
4. run tests, smoke flows, and contract audits
5. capture evidence on the tracked tasks before marking the checkpoint complete

For framework-internal passes, keep schema/bootstrap alignment and generated
contract refresh explicit too. When the platform vocabulary changes, represent
these as separate tracked tasks:

- schema/bootstrap alignment
- reference validation and constraint translation
- helper and payload normalization
- generated contract/doc refresh
- validation and proof capture

For integrity hardening specifically, track these separately:

- reference validation and suggestion rollout
- foreign-key and `CHECK` hardening
- native edge-table conversion for authoritative relationship fields
- fixture and seed alignment under stricter constraints
- final full-suite verification under the hardened schema

When `CHECK` hardening expands, document the exact classes of failures that are
now database-authoritative instead of leaving them as vague "bad input"
conditions:

- invalid JSON text for structured columns
- boolean storage flags that must be `0` or `1`
- non-negative counters, token counts, costs, durations, and transfer metrics
- bounded ranges such as progress percentages and network ports
- stable closed enums such as lifecycle statuses, plan format, actor kind/role,
  sync direction/mode, and host type

Also document what PMS deliberately leaves open:

- workflow state names
- generic entity-type strings used by extension-capable subsystems
- any vocabulary that is not yet governed by a first-class catalog or enum

Monetary values are also a separate transport category:

- database storage may use native numeric columns
- pricing/cost calculations may use `Decimal` in domain code
- machine-readable CLI/API/event payloads should emit plain decimal strings for
  money instead of JSON floats

Example:

```bash
uv run pms task add "PMS Platform Evolution" "Audit public payload residue"
uv run pms task add "PMS Platform Evolution" "Normalize CLI and API contracts"
uv run pms task add "PMS Platform Evolution" "Update README and machine docs"
uv run pms task add "PMS Platform Evolution" "Run validation checkpoint"
uv run pms task add "PMS Platform Evolution" "Relationalize org/team memberships and plan task links"
uv run pms task add "PMS Platform Evolution" "Relationalize portfolio/program goal and objective links"
uv run pms task add "PMS Platform Evolution" "Convert network environment server membership to a native edge table"
uv run pms task add "PMS Platform Evolution" "Audit and standardize monetary precision semantics across DB and interfaces"
uv run pms task add "PMS Platform Evolution" "Audit and normalize product team semantics away from relation-like JSON if authoritative"

uv run pms task start "Normalize CLI and API contracts" \
  --project "PMS Platform Evolution" \
  --by codex
uv run pms task progress "Normalize CLI and API contracts" \
  --project "PMS Platform Evolution" \
  70 "Removed storage-era fields from active public surfaces" \
  --by codex
uv run pms task progress "Relationalize org/team memberships and plan task links" \
  --project "PMS Platform Evolution" \
  65 "Native edge tables now hold the authoritative membership and plan-task graph links" \
  --by codex
uv run pms task progress "Relationalize portfolio/program goal and objective links" \
  --project "PMS Platform Evolution" \
  60 "Direct portfolio/program strategic links now live in native edge tables and readbacks merge them with project-derived scope" \
  --by codex
uv run pms task progress "Convert network environment server membership to a native edge table" \
  --project "PMS Platform Evolution" \
  70 "network_environment_servers now holds authoritative environment -> server edges for native queries and role-aware traversal" \
  --by codex
uv run pms task progress "Audit and standardize monetary precision semantics across DB and interfaces" \
  --project "PMS Platform Evolution" \
  30 "Authoritative pricing/cost columns are already native numeric values; the remaining work is making DB, Decimal, and JSON/event transport semantics explicit and consistent" \
  --by codex
uv run pms task progress "Audit and normalize product team semantics away from relation-like JSON if authoritative" \
  --project "PMS Platform Evolution" \
  60 "products.team is explicitly documented as descriptive metadata until a real product -> team edge exists" \
  --by codex
uv run pms task progress "Codify relation-authority audits for derived read-model arrays versus native edge tables" \
  --project "PMS Platform Evolution" \
  55 "schema tests now lock in which *_ids arrays are derived read-model outputs and which graph edges must remain native relational tables" \
  --by codex
uv run pms task evidence add "Normalize CLI and API contracts" \
  note contract-audit-01 \
  --project "PMS Platform Evolution" \
  --description "Targeted pytest slices passing; contract docs regenerated"
uv run pms task complete "Normalize CLI and API contracts" \
  --project "PMS Platform Evolution" \
  --by codex
```

This is the intended pattern for wider distribution too: PMS should help agents
manage their own work, their teams, and the proof of their execution.

## What To Read Next

- [`docs/CLIENT_GUIDE.md`](CLIENT_GUIDE.md) for the detailed CLI/client surface
- [`docs/WEB_API.md`](WEB_API.md) for server and HTTP usage
- [`docs/API_REFERENCE.md`](API_REFERENCE.md) for endpoint-level reference
- [`docs/END_TO_END_WORKFLOWS.md`](END_TO_END_WORKFLOWS.md) for broader project scenarios
- [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) for package and graph design
- [`docs/ACTOR_IDENTITY_PERSONA_GRAPH_ARCHITECTURE.md`](ACTOR_IDENTITY_PERSONA_GRAPH_ARCHITECTURE.md) for the identity model
- [`docs/VOCABULARY_GOVERNANCE.md`](VOCABULARY_GOVERNANCE.md) for closed vs registry-backed vs intentionally open text fields
