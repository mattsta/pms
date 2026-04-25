# PMS Architecture

## Overview

PMS (Project Management System) is a local-first, graph-based coordination
platform for managing products, projects, tasks, plans, actors, and proof
surfaces across humans and AI agents.

**Key Capabilities**:

- **Multi-Level Scope Graph**: Organization → Portfolio → Program → Product → Project
- **Strategic Graph Modeling**: Goals → Objectives → Key Results → Plans → Tasks
- **Complexity-Driven Tracking**: 1-100 point scale with auto-calculated duration
- **Actor and Persona Graph**: Humans, personas, teams, service accounts, and runtime agents
- **Distributed Agent Coordination**: Task checkout with exclusive locking
- **Real-Time Progress Tracking**: Micro-updates with velocity/ETA calculation
- **Flexible State Machine**: SDLC, Agile, Product Lifecycle workflows
- **Local-First Storage**: SQLite by default with PostgreSQL backend support
- **Multiple Interface Planes**: CLI, HTTP API, MCP tools, and machine-readable JSON control planes
- **Remote Operations**: SSH, rsync, AWS spot instances for testing
- **Automation**: Event-driven workflows with triggers
- **Universal Event Tracking**: Immutable audit logs with full attribution
- **Explicit Monetary Contracts**: Numeric DB storage, `Decimal` pricing logic, decimal-string transport

Target identity architecture:

- PMS is moving toward a first-class `Actor` graph for users, personas, teams,
  service accounts, and runtime agents.
- See [`docs/ACTOR_IDENTITY_PERSONA_GRAPH_ARCHITECTURE.md`](ACTOR_IDENTITY_PERSONA_GRAPH_ARCHITECTURE.md) for the permanent
  design reference for the actor/persona graph.

Machine-interface orientation:

- For the progressive agent/operator view of these same surfaces, read
  [`docs/MACHINE_INTERFACE_GUIDE.md`](MACHINE_INTERFACE_GUIDE.md).
- For the forward contract on which text fields are closed enums, registry-backed,
  or intentionally open, read
  [`docs/VOCABULARY_GOVERNANCE.md`](VOCABULARY_GOVERNANCE.md).
- For audience-based routing through the rest of the docs, use
  [`docs/DOCUMENTATION_MAP.md`](DOCUMENTATION_MAP.md).

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              PMS Platform                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                        CLI Interface (click/rich)                   │   │
│   └────────────────────────────────┬────────────────────────────────────┘   │
│                                                                             │
│   ┌────────────────────────────────┴────────────────────────────────────┐   │
│   │                     Agent System (Claude SDK)                       │   │
│   │        ┌───────────┐        ┌──────────┐        ┌──────────┐        │   │
│   │        │Coordinator│        │ Project  │        │   Task   │        │   │
│   │        │   Agent   │        │  Agent   │        │  Agent   │        │   │
│   │        └───────────┘        └──────────┘        └──────────┘        │   │
│   └────────────────────────────────┬────────────────────────────────────┘   │
│                                                                             │
│   ┌────────────────────────────────┴────────────────────────────────────┐   │
│   │                         Platform Layer                              │   │
│   │   ┌──────────────┐   ┌───────────┐  ┌───────────┐   ┌───────────┐   │   │
│   │   │     Core     │   │ Automation│  │  Memory   │   │ Learning  │   │   │
│   │   │Infrastructure│   │           │  │  System   │   │  Engine   │   │   │
│   │   └──────────────┘   └───────────┘  └───────────┘   └───────────┘   │   │
│   └────────────────────────────────┬────────────────────────────────────┘   │
│                                                                             │
│   ┌────────────────────────────────┴────────────────────────────────────┐   │
│   │                        Service Layer                                │   │
│   │     ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    │   │
│   │     │ Project  │    │   Task   │    │  Remote  │    │   AWS    │    │   │
│   │     │ Service  │    │ Service  │    │ Service  │    │ Services │    │   │
│   │     └──────────┘    └──────────┘    └──────────┘    └──────────┘    │   │
│   └────────────────────────────────┬────────────────────────────────────┘   │
│                                                                             │
│   ┌────────────────────────────────┴────────────────────────────────────┐   │
│   │                      Repository Layer                               │   │
│   │         ┌──────────┐        ┌──────────┐        ┌──────────┐        │   │
│   │         │ Project  │        │   Task   │        │  Remote  │        │   │
│   │         │   Repo   │        │   Repo   │        │   Repo   │        │   │
│   │         └──────────┘        └──────────┘        └──────────┘        │   │
│   └────────────────────────────────┬────────────────────────────────────┘   │
│                                                                             │
│   ┌────────────────────────────────┴────────────────────────────────────┐   │
│   │                        SQLite / PostgreSQL                          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Module Overview

## Current Code Structure

These packages are the main release-facing layers in the current codebase.

| Path                | Responsibility                                                           |
| ------------------- | ------------------------------------------------------------------------ |
| `pms/cli/`          | CLI entrypoints, text UX, and JSON response shaping                      |
| `pms/api/`          | FastAPI routes, request/response models, auth, and server app wiring     |
| `pms/client/`       | Programmatic HTTP client helpers                                         |
| `pms/models/`       | Domain models and enums                                                  |
| `pms/repositories/` | Persistence/query layer                                                  |
| `pms/services/`     | Business logic, graph math, rollups, orchestration, and validation       |
| `pms/db/`           | Schema, backend selection, database connections, and persistence support |
| `pms/tools/`        | MCP tool registry, server glue, and agent-facing tool handlers           |
| `pms/runtime/`      | Managed local runtime/server coordination                                |
| `pms/reporting/`    | Higher-order reporting helpers                                           |
| `pms/workflows/`    | Workflow definitions and workflow/state-machine support                  |
| `pms/automation/`   | Event-driven automation rules and orchestration                          |
| `pms/testing/`      | Test helpers and test-server integration support                         |
| `pms/aws/`          | AWS spot/test-server integration                                         |

Extended or more specialized modules currently present:

| Path            | Responsibility                               |
| --------------- | -------------------------------------------- |
| `pms/agents/`   | Agent integrations and ACP-related support   |
| `pms/plugins/`  | Plugin-oriented extensions                   |
| `pms/learning/` | Standalone learning/recommendation subsystem |
| `pms/memory/`   | Standalone memory/knowledge subsystem        |
| `pms/utils/`    | Shared utilities                             |

The public documentation should frame PMS around the first table, while the
second table is better treated as advanced or specialized surface area.

## Machine-Facing Contract Layers

The machine-facing contract should be understood in layers, not as one giant
flat command list.

- control-plane layer
  - `start`
  - `dashboard`
  - `work daily`
  - `work review`
- graph-detail layer
  - `task show --include-linked`
  - `plan show --include-linked`
  - `project show`
  - `goal summary`
- graph-export layer
  - `work graph-report`
  - API discoverability and observability routes
- identity layer
  - actor ownership, assignment, membership, and checkout payloads
- runtime-truth layer
  - `runtime.coordination`
  - `runtime_write`

This layering is what lets a human start simply while an advanced agent still
has access to deep graph traversal, explicit scope math, and stable
continuation contracts.

## Integrity And Validation Layers

PMS should not rely on only one layer of correctness.

Current design target:

- input/reference layer
  - resolve canonical IDs and reject ambiguous linked writes early
  - return useful suggestions when an ID is missing or almost correct
- service/business-rule layer
  - enforce graph semantics that are broader than one table constraint
  - examples: goal/objective/project consistency, workflow/state legality
- database integrity layer
  - SQLite/PostgreSQL foreign keys, uniqueness, and `CHECK` constraints are the
    final guardrail
  - SQLite foreign-key enforcement must remain enabled
- interface error layer
  - CLI and API should translate validation and constraint failures into
    structured, actionable operator/machine feedback rather than leaking raw DB
    exceptions
  - when PMS can identify likely intended linked entities, include those as
    suggestions instead of forcing callers to guess again

Design rule:

- pre-write validation improves usability
- database enforcement preserves integrity
- neither replaces the other

This matters because PMS is a graph coordination system. A dangling edge is not
just bad storage hygiene; it corrupts traversal, rollups, and machine
continuation logic.

## Transactional Ownership Model

Authoritative write safety follows one ownership rule:

- one logical mutation -> one explicit atomic owner
- single-aggregate repository writes may own that boundary themselves
- broader service flows that span multiple repository calls, table families, or
  follow-up mutations must own one outer `db.transaction()` and use explicit
  in-transaction helpers underneath

Current design contract:

- repository layer
  - public event-sourced aggregate writes should be safe to call directly
  - if a service already owns the wider logical mutation, repositories should
    expose `_..._in_transaction()` helpers instead of opening a second
    independent boundary
  - internal `_..._in_transaction()` helpers now assert that the current task
    already owns an active transaction, so atomic ownership is runtime-enforced
    instead of implied by naming alone
  - lower-level stores and repositories should not call `db.commit()` to imply
    a private inner commit boundary; the outer transaction owner or backend
    autocommit mode is the real persistence authority
- service layer
  - if the success contract spans more than one authoritative write, the
    service owns the boundary
  - metrics, revision writes, event appends, relationship sync, and similar
    required follow-up state belong inside that same logical boundary when a
    late failure must roll the mutation back
- external side effects
  - the database remains authoritative
  - destructive file/process/network cleanup should happen after commit unless
    it is itself represented as authoritative state inside the same atomic unit
- read-only telemetry
  - list/get/show/search counters are observational, not graph truth
  - they may run after a read without being treated as transactional debt
  - if observational metric storage fails late, the read/result should still be
    returned and the telemetry failure should be logged instead of changing the
    business outcome

Good pattern:

```python
async def assign_label(self, request: LabelAssignmentRequest) -> LabelAssignment:
    async with self.db.transaction():
        assignment = await self._assignment_repo.replace_in_transaction(request)
        await self.metrics.flush()
    return assignment
```

Anti-pattern:

```python
assignment = await self._assignment_repo.replace(request)
await self._watcher_repo.add(...)
await self.metrics.flush()
```

The anti-pattern above is wrong because each public write can commit
independently. If the later call fails, PMS can persist a partial logical
mutation.

See `docs/archive/audits/TRANSACTIONAL_CORRECTNESS_AUDIT.md` for the ranked audit, completed
fixes, and remaining proof work.

## Target Graph Model

Current PMS already has a usable graph backbone:

- structural scope:
  - organization
  - portfolio
  - program
  - product
  - project
- strategic execution:
  - goal
  - objective
  - key result
  - plan
  - task

The next architecture step is to make these nodes fully traversable in both
directions and to add a first-class actor graph for ownership, assignment,
membership, persona routing, and runtime execution attribution.

Target graph families:

- structural graph:
  - org -> portfolio -> program -> project
- strategic graph:
  - project -> goal -> objective -> key result
- execution graph:
  - project -> plan -> task
  - task -> parent/subtask
  - task -> dependency/dependent
- identity graph:
  - actor -> membership / alias / delegation / representation
  - actor -> owned work / assigned work / checked-out work

Design rule:

- every relationship edge should have one authoritative source
- every primary `show --format json` surface should expose symmetric machine
  links up and down the graph
- every rollup should declare its population and graph basis explicitly

Related rule for persistence:

- non-polymorphic `_id` edges should be foreign-keyed where practical
- structured JSON fields should be explicitly validated as JSON
- derived arrays or caches should not pretend to be the authoritative graph
- if a reference is owned by an application catalog instead of a database table
  today, treat it as a validated soft reference until that catalog becomes
  database-authoritative
- namespace registration should only cover entity families that actually
  participate in the prefix/native ID contract
- valid public `entity_type` values may be broader than the namespace registry
  when PMS still has UUID-native first-class entities; those must be documented
  and tested as DB-backed extras rather than implied namespaces

Current implemented examples of native authoritative edges:

- `organization_members`
- `team_members`
- `plan_tasks`
- `plan_test_job_tasks`
- `portfolio_goals`
- `portfolio_objectives`
- `program_goals`
- `program_objectives`
- `network_environment_servers`

These tables now hold the real graph links for org/team membership and
plan-to-task execution relationships, plus direct portfolio/program strategic
links. `network_environment_servers` also replaces the last server-membership
JSON array in the schema so role-aware network environments can be queried with
native joins and CTEs. Projection rows may still expose `members`,
`member_ids`, `task_ids`, `goal_ids`, or `objective_ids` in API/CLI payloads,
but those are hydrated views over native edge tables or effective-scope unions,
not JSON-array authority in the core projection tables.

Remaining JSON columns are kept only where the data is genuinely document-like,
config-like, or label-like rather than a first-class graph edge. Current
examples:

- tags, service URLs, descriptive team labels
- workflow metadata and approval-role lists
- capture-log / artifact / exclude pattern lists for test jobs
- automation payload/config blobs and other structured metadata documents

Current remaining normalization debt:

- any other JSON-array field that is truly an authoritative graph edge should
  be converted the same way instead of accumulating more pre/post-processing
  logic
- AWS/test-server pricing now uses native numeric columns; keep following that
  rule anywhere the system sorts, aggregates, or compares numeric values at
  runtime
- `products.team` is currently retained as descriptive metadata, not as an
  authoritative relation to `teams`; if product-to-team ownership becomes a
  first-class graph edge later, it should move to its own edge table rather
  than reusing a JSON string list
- project membership remains authoritative through project foreign keys
  (`projects.portfolio_id`, `projects.program_id`) rather than child-array
  columns on parent rows
- bootstrap helpers should therefore assign portfolio/program membership by
  updating the child project foreign keys, not by writing parent `project_ids`
  arrays as if they were authoritative storage
- portfolio/program `goal_ids` and `objective_ids` are the direct strategic
  links stored through native edge tables
- portfolio/program `effective_goal_ids` and `effective_objective_ids` are the
  hydrated scope outputs built from those direct links plus linked project scope
- portfolio/program `project_ids` remains the effective project scope readback
- the namespace registry documents namespace-generated typed IDs and schema
  metadata, but it is not the full runtime row-ID contract for every public
  entity family

Related rule for failure handling:

- preserve database integrity failures as typed PMS errors
- keep CLI and API error contracts aligned around validation, constraint, and
  workflow/business-rule failures
- prefer database-authoritative checks for stable invariants:
  - JSON validity for structured fields
  - boolean `0/1` flags at the storage boundary
  - non-negative counters, costs, and durations
  - bounded ranges such as progress percentages and network ports
  - stable stored enums such as task/project/goal lifecycle states, actor
    identity kinds/roles, sync direction/mode, host type, plan format, and
    other closed operational vocabularies
- do not freeze intentionally extensible vocabularies at the database layer
  until PMS promotes them to an authoritative catalog
  - examples: workflow state names, generic entity types, plugin-facing labels
    or extension concepts
- if a stricter schema reveals dangling test/fixture assumptions, repair the
  fixtures rather than weakening the authoritative graph model

PMS should use this same model on itself. Schema hardening, constraint
translation, fixture repair, and generated-contract refresh should be tracked
as explicit PMS work items, not handled as informal cleanup.

### Core Infrastructure (`pms/core/`)

Foundational infrastructure used by all modules.

| Component      | Purpose                              | Key Classes                    |
| -------------- | ------------------------------------ | ------------------------------ |
| `ids.py`       | Unified ID system with type prefixes | `EntityType`, `generate_id()`  |
| `refs.py`      | Cross-entity relationship tracking   | `Reference`, `ReferenceStore`  |
| `registry.py`  | Entity discovery and lifecycle       | `EntityInfo`, `EntityRegistry` |
| `platform.py`  | Unified access to all subsystems     | `Platform`, `get_platform()`   |
| `events.py`    | Domain event sourcing                | `DomainEvent`, `EventStore`    |
| `metrics.py`   | Operation timing and tracking        | `MetricsCollector`             |
| `revisions.py` | Entity version history               | `RevisionStore`                |

### Automation (`pms/automation/`)

Event-driven workflow orchestration.

| Component      | Purpose                  | Key Classes                                     |
| -------------- | ------------------------ | ----------------------------------------------- |
| `events.py`    | Pub/sub messaging        | `EventBus`, `Event`, `EventPattern`             |
| `workflows.py` | Multi-step orchestration | `Workflow`, `WorkflowEngine`, `WorkflowBuilder` |
| `triggers.py`  | Event-driven initiation  | `Trigger`, `TriggerManager`, `TriggerBuilder`   |

### Memory System (`pms/memory/`)

Persistent storage for learned information.
These modules are present in code but not yet wired into the main CLI/API flows.

| Component      | Purpose                         | Key Classes                   |
| -------------- | ------------------------------- | ----------------------------- |
| `knowledge.py` | Knowledge storage and search    | `Knowledge`, `KnowledgeStore` |
| `patterns.py`  | Pattern matching and reuse      | `Pattern`, `PatternMatcher`   |
| `feedback.py`  | Positive/negative reinforcement | `Feedback`, `FeedbackStore`   |
| `context.py`   | Conversation context tracking   | `ContextManager`              |

### Learning System (`pms/learning/`)

Continuous improvement through feedback loops.
These modules are standalone today and are not invoked by default services.

| Component        | Purpose                       | Key Classes                         |
| ---------------- | ----------------------------- | ----------------------------------- |
| `engine.py`      | Central learning coordination | `LearningEngine`                    |
| `outcomes.py`    | Learn from operation results  | `OutcomeLearner`, `WorkflowOutcome` |
| `suggestions.py` | Intelligent recommendations   | `SuggestionEngine`, `Suggestion`    |

## ID Contract

PMS currently has two related but different ID layers:

1. namespace/prefix utilities
   - typed IDs such as `proj_<uuid>` or `wf_<uuid>`
   - used by the namespace registry, typed-ID helpers, and some internal/system
     entity families
2. runtime row IDs for public stored entities
   - currently UUID-native for most first-class operator-facing entities

That distinction matters. The namespace registry is a type catalog and prefix-ID
utility surface today. It is not yet the authoritative runtime row-ID contract
for most public entities.

Current public runtime ID rule:

- treat public stored entity IDs as opaque canonical IDs
- do not infer a prefix from `entity_type`
- unless PMS documents an entity family as prefix-native, expect runtime IDs to
  be UUID-native

Machine-readable namespace schema exposes the same distinction with:

- `namespace_generated_id_format`
- `namespace_generated_id_kind`
- `runtime_row_id_contract_scope`
- `runtime_row_id_style`

Current public runtime styles:

| Entity Family     | Runtime ID Style |
| ----------------- | ---------------- |
| `api_key`         | `prefix_native`  |
| `actor`           | `uuid_native`    |
| `organization`    | `uuid_native`    |
| `team`            | `uuid_native`    |
| `portfolio`       | `uuid_native`    |
| `program`         | `uuid_native`    |
| `product`         | `uuid_native`    |
| `project`         | `uuid_native`    |
| `plan`            | `uuid_native`    |
| `goal`            | `uuid_native`    |
| `objective`       | `uuid_native`    |
| `key_result`      | `uuid_native`    |
| `task`            | `uuid_native`    |
| `milestone`       | `uuid_native`    |
| `remote_host`     | `uuid_native`    |
| `test_server`     | `uuid_native`    |
| `test_run`        | `uuid_native`    |
| `session`         | `uuid_native`    |
| `automation_rule` | `uuid_native`    |

Current internal prefix-native families used in active codepaths include:

- `event`
- `metric`

Namespace/prefix examples are still real, but they apply to the typed-ID
utility layer:

```
proj_a1b2c3d4-e5f6-7890-abcd-ef1234567890
wf_c3d4e5f6-a789-0123-cdef-345678901234
evt_d4e5f6a7-8901-2345-def0-456789012345
```

Forward rule:

- do not treat namespace registration as proof of runtime prefix-native IDs
- do not fabricate prefix-shaped placeholder IDs in public docs unless that
  entity family truly uses them at runtime
- promote a UUID-native family into the prefix-native runtime contract only
  through a deliberate interface/test/doc conversion plan

## Cross-Reference System

Entities can reference each other through typed relationships:

```python
from pms.core import Reference, ReferenceType, get_reference_store

store = get_reference_store()

# Task belongs to project
await store.add(Reference(
    source_id="task_xxx",
    target_id="proj_yyy",
    relation=ReferenceType.BELONGS_TO,
))

# Task triggered workflow
await store.add(Reference(
    source_id="task_xxx",
    target_id="wf_zzz",
    relation=ReferenceType.TRIGGERS,
))

# Query relationships
targets = await store.get_targets("task_xxx", ReferenceType.TRIGGERS)
graph = await store.get_reference_graph("task_xxx", depth=2)
```

### Relationship Types

| Type         | Inverse     | Description      |
| ------------ | ----------- | ---------------- |
| PARENT_OF    | CHILD_OF    | Hierarchical     |
| CONTAINS     | BELONGS_TO  | Containment      |
| DEPENDS_ON   | REQUIRED_BY | Dependencies     |
| TRIGGERED_BY | TRIGGERS    | Causal           |
| CAUSED_BY    | CAUSES      | Direct causation |
| USES         | USED_BY     | Resource usage   |
| LEARNED_FROM | TEACHES     | Knowledge source |
| SIMILAR_TO   | SIMILAR_TO  | Similarity       |

## Event Flow

Events propagate through the system enabling reactive automation:

```
┌─────────┐    emit     ┌─────────┐   subscribe   ┌─────────────┐
│ Service │ ──────────> │EventBus │ <───────────> │   Trigger   │
└─────────┘             └─────────┘               │   Manager   │
                             │                    └──────┬──────┘
                             │                           │
                             │ history                   │ fire
                             ▼                           ▼
                        ┌─────────┐              ┌─────────────┐
                        │ Memory  │              │  Workflow   │
                        │ System  │ <─────────── │   Engine    │
                        └─────────┘   learn      └─────────────┘
```

### Event Types

- **Lifecycle**: `system.started`, `system.stopped`
- **Project**: `project.created`, `project.completed`
- **Task**: `task.created`, `task.completed`, `task.blocked`
- **Workflow**: `workflow.started`, `workflow.completed`, `workflow.failed`
- **Remote**: `remote.command.completed`, `sync.completed`
- **Server**: `server.launched`, `server.terminated`

## Learning Loop

The learning system creates a continuous improvement cycle:

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Learning Loop                                │
│                                                                     │
│        ┌──────────┐        ┌───────────┐       ┌───────────┐        │
│        │ Operation│ ────── │  Outcome  │ ───── │   Learn   │        │
│        │ Execute  │        │  Capture  │       │   Store   │        │
│        └──────────┘        └───────────┘       └─────┬─────┘        │
│             ▲                                        │              │
│             │                                        ▼              │
│        ┌────┴─────┐        ┌───────────┐       ┌───────────┐        │
│        │ Suggest  │ ────── │  Analyze  │ ───── │  Pattern  │        │
│        │ Improve  │        │  Feedback │       │   Match   │        │
│        └──────────┘        └───────────┘       └───────────┘        │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Feedback Reinforcement

```python
from pms.learning import get_learning_engine

engine = get_learning_engine()

# Learn from success
await engine.learn_from_workflow(WorkflowOutcome(
    workflow_name="deploy",
    success=True,
    duration_seconds=45.0,
))

# Record explicit feedback
await engine.record_feedback(
    category="code_style",
    subject="type_hints",
    positive=True,
    reason="Improves readability",
)

# Check recommendations
if await engine.is_recommended("code_style", "type_hints"):
    # Use type hints
    pass

# Get suggestions
suggestions = await engine.suggest("deploy to production")
```

## Platform Integration

The `Platform` class provides unified access to all subsystems:

```python
from pms.core import get_platform

platform = get_platform()

# Register entities
await platform.register_entity(task_id, "My Task", tags=["urgent"])

# Emit events (triggers automation + learning)
await platform.emit_task_completed(task_id, project_id)

# Link entities
await platform.link_entities(task_id, workflow_id, ReferenceType.TRIGGERED_BY)

# Get relationship graph
graph = await platform.get_entity_graph(task_id, depth=2)

# Learning operations
await platform.record_positive_feedback("code_style", "docstrings")
suggestions = await platform.get_suggestions("deploy application")

# Context management
platform.set_context(project_id=project_id)
platform.add_decision("Use PostgreSQL", "Team standard")
```

## Data Persistence

### SQLite Database

Core entities (projects, tasks, milestones) use SQLite:

```
~/.pms/pms.db
  ├── projects
  ├── tasks
  ├── milestones
  ├── task_dependencies
  ├── remote_hosts
  └── sessions
```

### JSON Storage

Memory and learning data use JSON files:

```

Design rule:

- JSON is appropriate for document content, metadata, automation payloads,
  proof bundles, and other semi-structured artifacts
- JSON is not the right authority for first-class graph edges when the system
  needs native joins, foreign keys, ordering, and CTE-friendly traversal
~/.pms/
  ├── knowledge/
  │   └── store.json      # Knowledge entries
  ├── feedback/
  │   └── store.json      # Feedback signals
  ├── patterns/
  │   └── store.json      # Learned patterns
  ├── references/
  │   └── store.json      # Entity references
  └── registry/
      └── store.json      # Entity registry
```

## Dashboards and Rollups

PMS exposes rollup dashboards for organizations, portfolios, programs, and
projects. Each dashboard combines:

- **Totals**: projects, goals, objectives, tasks, and blocked task counts.
- **Risk**: aggregate risk score/level from rollup metrics.
- **Activity/Transition**: last activity and last workflow/state transition
  timestamps that roll up from nested entities.

Dashboards are served in three channels using the same service layer:

- **CLI**: `pms org/portfolio/program dashboard` for table/json/csv outputs.
- **API**: `/api/v1/organizations|portfolios|programs/dashboard`.
- **GUI**: the `/dashboard` web UI uses the same endpoints.

Rollup calculations live in `pms/services/*_service.py` and
`pms/services/rollup_utils.py` to keep logic centralized and consistent.

## MCP Tool Integration

PMS exposes 31+ tools through MCP:

### Core Tools (Always Loaded)

- `create_project`, `list_projects`, `get_project`, `get_dashboard`
- `create_task`, `list_tasks`, `start_task`, `complete_task`

### Extended Tools (Discoverable via Tool Search)

- **Remote**: `execute_remote_command`, `sync_push`, `sync_pull`
- **AWS**: `find_spot_instances`, `launch_test_server`, `run_tests_on_server`
- **Project**: `add_task_dependency`, `bulk_create_tasks`

### Tool Search Support

```python
from pms.tools.server import ServerMode, get_tool_search_tools_config

# Get configuration for Claude's tool search
config = get_tool_search_tools_config()
# Returns: tool_search_tool + mcp_toolset with defer_loading
```

## Test Coverage

300+ tests covering:

- Unit tests for all components
- Integration tests for cross-module interactions
- Service layer tests
- Tool tests
- Automation tests (events, workflows, triggers)
- Memory tests (knowledge, patterns, feedback, context)
- Learning tests (outcomes, suggestions, engine)
- Core infrastructure tests (IDs, references, registry, platform)

Run tests:

```bash
uv run pytest tests/ -v
```

## Future Roadmap

See [`docs/archive/plans/VISION_ROADMAP.md`](archive/plans/VISION_ROADMAP.md) for the historical 8-phase evolution plan:

1. **Meta-Programming Engine** - Self-writing tools
2. **Multi-Agent Orchestration** - Specialized agent collaboration
3. **Workflow Automation** - Event-driven workflows ✅
4. **Knowledge & Memory** - Learning system ✅
5. **Self-Deployment & GitOps** - Automatic deployment
6. **Plugin Ecosystem** - Community extensions
7. **Observability & Analytics** - Full visibility
8. **Security & Governance** - Enterprise-ready
