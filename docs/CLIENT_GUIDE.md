# PMS Client Guide

**Client**: HTTP client library for PMS API server
**Language**: Python (async)
**Library**: httpx

---

## Installation

```bash
# Client is included in PMS
pip install pms

# Or just httpx for standalone client
pip install httpx
```

---

## Usage

This guide is the detailed command/client reference for PMS.

Read it after:

- [`README.md`](../README.md)
- [`docs/IMMEDIATE_START_GO.md`](IMMEDIATE_START_GO.md)
- [`docs/MACHINE_INTERFACE_GUIDE.md`](MACHINE_INTERFACE_GUIDE.md)

Use it when you want:

- the detailed CLI and HTTP client surface
- machine-readable JSON contract details
- cross-interface parity guidance between CLI, API, and MCP

If you are building an autonomous integration, do not start here first. Start
with [`docs/MACHINE_INTERFACE_GUIDE.md`](MACHINE_INTERFACE_GUIDE.md), then come
back here for command-level details.

## Actor Identity Architecture

PMS uses a first-class actor graph covering:

- humans
- personas
- teams
- service accounts
- runtime agents

Architecture reference:

- [`docs/ACTOR_IDENTITY_PERSONA_GRAPH_ARCHITECTURE.md`](ACTOR_IDENTITY_PERSONA_GRAPH_ARCHITECTURE.md)

Public identity contract:

- write requests use semantic role keys such as `owner`,
  `members`, `assignee`, and `actor` where checkout needs an explicit actor
- API read payloads use the same semantic role keys, and actor payloads use
  `ref`, `id`, `actor`, and `links`
- CLI actor-resolved payloads use that same nested actor payload shape even
  where wrapper keys still reflect the surrounding surface context
- CLI flags like `--owner`, `--member`, and `--assigned-to` remain concise
  operator inputs, but they accept actor handles or IDs

## Entity Type Contract

PMS now treats extension-facing `entity_type` inputs as a shared contract, not a
route-by-route string accident.

Current rule:

- comments, watchers, label assignments, label gates, custom field definitions,
  custom field values, transition timelines, and workflow alignment use one
  canonical namespace-backed validator
- common aliases are normalized to canonical values:
  - `org` -> `organization`
  - `keyresult` -> `key_result`
  - `key-results` -> `key_result`
- when the surface requires a real stored entity, PMS also checks the
  relational table behind that entity type
- namespace-backed entity families participate in `pms namespace ...`
  introspection and typed-ID utilities, but that does not automatically mean
  their runtime row IDs are prefix-native today
- `actor`, `automation_rule`, and `product` are still valid public
  `entity_type` values, but they are currently DB-backed extras rather than
  namespace-generated families because their IDs remain UUID-native
- `api_key` now participates in both the relational contract and the built-in
  namespace registry because its ID contract is already prefix-native
- task evidence gates are intentionally narrower and currently accept only
  `task`, because the proof model is task-native today

Design reference:

- [`docs/VOCABULARY_GOVERNANCE.md`](VOCABULARY_GOVERNANCE.md)
- [`docs/ARCHITECTURE.md`](ARCHITECTURE.md)

Current implemented actor surfaces:

- `actor create`
- `actor list`
- `actor show`
- `actor alias add`
- `actor membership add`
- `config set --current-actor <actor>`
- `task list --actor <actor> --format json`
- `task list --mine --format json`
- `task search --actor <actor> --format json`
- `task search --mine --format json`
- `task ready --format json`
- `task stale --format json`
- `task blocked --format json`
- `task duplicates --format json`
- `queue run <queue-ref> --format json`
- `queue presets --format json --view detail`
- `dashboard --format json`
- `project show <project-ref> --format json`
- `project summary <project-ref> --format json`
- `plan show <plan-ref> --format json`
- `goal show <goal-ref> --format json`
- `goal summary <goal-ref> --format json`
- `objective show <objective-ref> --format json`
- `keyresult show <key-result-ref> --format json`
- `product show/list/summary --format json`
- `org show/list/summary --format json`
- `team show/list --format json`
- `portfolio show/list/summary --format json`
- `program show/list/summary --format json`
- `queue show/list --format json`
- `task show <task-ref> --format json`
- `task add/create <project> <title> --assigned-to <actor> --format json`
- `task update <task-ref> --assigned-to <actor> --format json`
- `goal create/update ... --owner <actor> --format json`
- `objective create/update ... --owner <actor> --format json`
- `keyresult create/update ... --owner <actor>`
- `product create/update ... --owner <actor> --format json`
- `org create/update ... --owner <actor> --member <actor> --format json`
- `team create/update ... --owner <actor> --member <actor> --format json`
- `portfolio create/update ... --owner <actor> --format json`
- `program create/update ... --owner <actor> --format json`
- `queue create/update ... --owner <actor> --format json`
- `POST /api/v1/actors`
- `GET /api/v1/actors`
- `GET /api/v1/actors/<actor>`
- `POST /api/v1/actors/<actor>/aliases`
- `POST /api/v1/actors/<actor>/memberships`
- MCP:
  - `create_actor`
  - `list_actors`
  - `get_actor`
  - `add_actor_alias`
  - `add_actor_membership`

Current machine-readable contracts:

- `actor show --format json` exposes:
  - actor aliases
  - parent and child memberships
  - workload rollups split into `direct`, `effective`, and `inherited_only`
  - workload task links back into `task show` and `project show`
  - owned strategic and management entities through:
    - `ownership.counts`
    - `ownership.items`
  - per-project assignment and checkout rollups through:
    - `project_workloads[]`
  - actor-scoped graph traversal through:
    - `graph_navigation`
  - direct checkout lease reporting using:
    - `workload.checkout_scope = "direct_only"`
    - `workload.checkouts`
    - `workload.checkout_tasks[]`
- `task show --format json` exposes:
  - actor-resolved assignee payloads
  - checkout metadata
  - `links.actor`
  - `context.project`
  - `context.milestone`
  - `context.parent`
  - `context.subtasks`
  - `links.plans`
  - `linked_plan_count`
  - `linked_plans[]`
- primary graph detail surfaces now expose symmetric machine links for up/down traversal:
  - `project show --include-linked --format json`
  - `project summary --format json`
  - `goal show --include-linked --format json`
  - `goal summary --format json`
  - `objective show --include-linked --format json`
  - `keyresult show --include-linked --format json`
  - `plan show --include-linked --format json`
  - `task show --include-linked --format json`
- `task show --include-linked --format json` now carries the task context graph directly:
  - `linked.project`
  - `linked.milestone`
  - `linked.parent`
  - `linked.subtasks`
  - `linked.dependencies`
  - `linked.dependents`
- `GET /api/v1/tasks/<task_id>` and `GET /api/v1/tasks/search` now expose the
  same assignee contract on task payloads
- `GET /api/v1/tasks/<task_id>` also exposes reverse plan traversal through:
  - `links.plans`
  - `linked_plan_count`
  - `linked_plans[]`
- `plan list --task-id <task-id> --format json` and `GET /api/v1/plans?task_id=<task_id>`
  provide the symmetric reverse edge from a task back to its linked plans
- `task show --format json`, `task checkout-status --format json`, and API
  checkout/status surfaces now also expose:
  - checkout actor identity metadata
- `task checkout-log --format json`, CSV, and API checkout-log responses now
  expose canonical lease identity too:
  - checkout actor identity metadata
- `task list --format json`, `task search --format json`, `task ready --format json`,
  `task stale --format json`, `task blocked --format json`, and
  `task duplicates --format json` expose the same assignee payload for each task
  row when assignee resolution succeeds
- `queue run --format json`, `queue presets --format json --view detail`, and
  `dashboard --format json` expose that same actor-resolved assignee payload
  and actor links on task rows in queue/focus/reporting surfaces
- `project show --format json`, `project summary --format json`,
  `goal show --format json`, `goal summary --format json`,
  `objective show --format json`, `plan show --format json`,
  `dashboard --format json`, `start --format json`, `queue run --format json`,
  `queue presets --format json --view detail`, `work daily --format json`, and
  `work graph-report --format json` now also expose top-level `actor_rollups`
  with explicit `population_basis` plus ownership/assignment/checkout rollups
- `work graph-report --scope-type project --scope-id <project-id> --format json`
  now provides a unified graph readback across:
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
- `GET /api/v1/queues`, `GET /api/v1/queues/<queue_id>`, and
  `GET /api/v1/queues/<queue_id>/run` now expose:
  - actor-resolved owner payloads
  - actor-resolved task assignee payloads on queue result rows
- `goal show --format json`, `goal summary --format json`,
  `objective show --format json`, and `keyresult show --format json` expose:
  - actor-resolved owner payloads
  - actor navigation via owner links
- `GET /api/v1/objectives/<objective_id>/key-results` and
  `GET /api/v1/key-results/<key_result_id>` now expose:
  - `effective_rollup`
  - bubbled `last_activity_at`
  - bubbled `last_transition_at`
  - `terminal_reason`
  - discoverability `links`
  - `next_steps`
  - detail-only `completion_context`
- `product`, `organization`, `team`, `portfolio`, `program`, and `queue`
  show/list/summary JSON surfaces expose the same actor-resolved ownership
  contract
- `organization` and `team` JSON surfaces also expose:
  - actor-resolved member payloads
- `project show --format json`, `project summary --format json`, and
  `plan show --format json` expose actor-resolved assignee payloads on:
  - `focus_task`
  - `execution.active_tasks`
  - linked task rows where applicable
- `goal summary --format json` and `GET /api/v1/goals/<goal_id>/summary`
  explicitly declare linked execution scope using:
  - `execution.population_basis`
  - `execution.scoped_goal_count`
  - `execution.population_basis = goal_plan_task_graph` when execution is linked
    through `plan.goal_id` or `plan.objective_id`
  - `execution.population_basis = project_scoped_execution_alias` only when a
    single-goal project legitimately aliases project execution
  - `execution.population_basis = goal_scope_requires_explicit_links` when
    multiple retained goals share a project and the goal has no explicit
    goal/objective-linked plan graph
  - those multi-goal unlinked summaries expose:
    - `execution.readiness_state = execution_scope_unlinked`
    - `execution.consistency_status = unlinked_goal_execution_scope`
    - a `consistency_reason` telling the operator to link tasks through
      goal/objective plans

Interpretation:

- `direct` means the task is assigned straight to the actor's own tokens
- `effective` means direct plus inherited persona/team memberships
- `inherited_only` is the difference between `effective` and `direct`

Checkout semantics:

- checkout mutations resolve a canonical checkout actor in this order:
  - explicit actor ref
  - existing actor matching the checkout session token
  - auto-created `runtime_agent` actor for the checkout session

## Runtime Truth For Mutations

Machine-readable mutation surfaces expose the effective write target, not just
the configured intent.

- JSON mutation responses include `runtime_write`
- text mutation responses suppress successful runtime plumbing and only emit degraded or blocked coordination messages

Read these fields after writes:

- `runtime_write.write_mode`
- `runtime_write.write_path`
- `runtime_write.target_kind`
- `runtime_write.target_location`
- `runtime_write.coordination_state`
- `runtime_write.workspace`

Interpretation:

- `write_mode=prefer_server` means PMS will try server delegation first
- `write_path=server_delegated` means the mutation actually went through the
  server
- `write_path=direct_file` means the mutation actually landed in the workspace
  SQLite database

For machine users, request JSON and treat `runtime_write.write_path` as the
source of truth for where the mutation landed.

The contract is not limited to task execution. It also applies to user-visible
create and update flows such as:

- `<invoke-prefix> project create ...`
- `<invoke-prefix> task add ...`
- `<invoke-prefix> plan create ...`
- `<invoke-prefix> plan update ...`

Some mutation surfaces are still local-only. When PMS is configured with
`prefer_server`, those commands must still report `runtime_write.write_path =
direct_file` until true server delegation exists. A healthy server nearby does
not make a local-only mutation magically delegated.

When a command separates stored content from rendered output, use
`--output-format json` for the mutation response and keep `--format` for stored
content shape. Example:

```bash
<invoke-prefix> plan create "Runtime Truth Plan" --content '{}' --output-format json
```

Compatibility shortcut:

```bash
<invoke-prefix> plan create "Runtime Truth Plan" --content '{}' --format json
```

`plan create` now treats explicit `--format json` as machine-readable output when
no separate output format is chosen, because `json` is already the default stored
plan format and callers routinely use the standard mutation pattern.

Execution against tasks linked to a draft plan is intentionally blocked. Those
blocked `task start` and `task progress` paths should now fail non-zero and
return machine-readable error payloads in JSON mode.

The same non-zero, machine-readable contract applies to delegated auth
failures. If server-backed task execution hits `Invalid API key`, the command
should fail instead of returning a fake success code.

Progress updates are now lifecycle-aligned:

- progressing a `todo` task above `0%` automatically transitions it to
  `in_progress`
- the returned task payload and follow-up guidance reflect the new
  `in_progress` state immediately
- direct and delegated progress paths share the same rule

Strategic list filters are now combined predicates rather than first-match
shortcuts:

- `goal list`
- `objective list`
- `keyresult list`

When you pass multiple supported filters such as `--status` with `--project`,
`--goal`, or `--objective-id`, PMS now applies all of them together on the same
query path.

Default operator suppression also now composes with pagination on:

- `project list`
- `goal list`
- `plan list`

That means `--limit` and `page.total_count` describe the visible/operator
population after suppression, not an under-filled raw page.

The same rule now applies to structural hierarchy lists:

- `team list`
- `portfolio list`

Conflicting scope selectors now fail loudly instead of silently succeeding:

- `plan list --goal ... --goal-id ...`
- `objective list --goal ... --goal-id ...`
- `keyresult list --objective ... --objective-id ...`
- `loop list --project ... --project-id ...`
- `test server ensure-local --project ... --project-id ...`
- `objective create` without `--goal` / `--goal-id`
- `keyresult create` without `--objective` / `--objective-id`
- `objective update` with an invalid `--target-date`
- `objective create` / `objective update` with invalid `--progress`
- `keyresult create` / `keyresult update` with invalid `--progress`

In `--format json` mode, these validation failures return a machine-readable
`{"error": ...}` payload and a non-zero exit status.

Constraint-backed failures use the same machine-readable contract. PMS preserves
the constraint type and suggestions instead of flattening them into a generic
database error. Common categories now include:

- `foreign_key`
- `unique`
- `not_null`
- `check`

For `check` failures, PMS should tell you whether the problem was invalid JSON,
a boolean `0/1` storage flag, a non-negative field, a bounded range such as
progress percentage or port number, or a closed enum with the allowed stored
values listed explicitly.

Current boundary:

- stable lifecycle and operational enums should be enforced at the database
  layer
- open-ended workflow state names and extension-facing entity-type vocabularies
  should not be frozen by storage checks unless PMS first promotes them to a
  governed catalog
- monetary values should be treated separately from generic floats:
  - database storage may remain native numeric
  - domain pricing logic may use `Decimal`
  - machine-readable transport should prefer plain decimal strings for money

The same fail-loud contract now covers several lower-frequency operator paths
that previously printed a red line and exited `0`:

- `queue show`, `queue update`, and `queue run` when the saved queue is missing
- `task proof-bundle-search` with invalid `--created-from` / `--created-to`
- `revision diff` when revision bounds are invalid or history is absent
- `task tree` when `--root-task-id` is outside the selected project
- `comment add --metadata-json ...` with invalid JSON
- `automation rule create --action-payload-json ...` with invalid JSON
- admin auth surfaces like `auth list` / `auth get` now fail non-zero for
  missing or unauthorized admin API keys instead of returning a false success
- non-interactive AWS / generate / plugin guards now fail non-zero too:
  - `aws logs` requires at least one log path
  - `generate module` requires at least one tool description
  - `plugin test` requires a `plugin.json` manifest
- queue and plan authoring guards now follow the same rule:
  - `queue create` / `queue list` conflicting or incomplete scope selectors fail non-zero
  - `plan create --plan-format yaml` requires explicit content
  - `plan test-job run` rejects invalid argument shape with a non-zero exit
- adjacent label/remote lookup guards now do the same:
  - `label create` rejects conflicting `--category` / `--category-id`
  - `remote show --format json` returns `{"error": ...}` and exits non-zero when the host is missing
- plugin/generator validation now reports truthfully too:
  - `plugin validate` exits non-zero when validation errors are present
  - `generate tool` exits non-zero when generation itself fails
- remaining task/project/workflow validation guards now do the same:
  - `task evidence add --metadata ...` requires valid JSON
  - `task dep add` fails non-zero when dependency creation is rejected
  - `project complete` fails non-zero if the update does not actually land
  - delegated `goal create --format json` fails if the server mutation succeeds but local reload truth cannot be recovered
  - `workflow align` fails non-zero when no current workflow state exists

Intentional exception:

- the dependency-number prompts inside the interactive loop authoring flow remain
  interactive prompt validation, not machine-readable CLI contracts
- those prompts are part of a live wizard, so invalid task-number input is still
  handled in-place instead of terminating the whole command with JSON error output

Runtime coordination now distinguishes a reachable server from an authorized
delegation path:

- `runtime status --format json`
- `config show --format json`

If the configured key file exists but the server rejects it, coordination
surfaces report `degraded_invalid_api_key` instead of `server_coordinated`.

Admin key mutation commands now support machine-readable success and failure
contracts too:

- `auth create --format json`
- `auth deactivate --format json`
- `auth restore --format json`
- `auth revoke --format json`

These commands now exit non-zero on authorization/validation failure and emit
JSON payloads on success instead of relying on text-only operator output.

`task show --format json` now reconciles terminal progress truth too:

- when a task is `done`, `progress.current_percent` is `100`
- `progress.last_update` is reconciled to the completion state instead of
  exposing an older partial-progress metric as the final update
- `program list`

Scope filters like `--org-id` or `--portfolio-id` now compose with `--status`
instead of silently overriding one another.

`project list --format json` now mirrors dashboard population clarity:

- top-level `visible_totals.population = "visible_operator"`
- default top-level `scope.population = "visible_operator"`
- default top-level `population_totals.population = "visible_operator"`
- `project list --include-generated --format json` switches:
  - `scope.population = "all_retained"`
  - `population_totals.population = "all_retained"`
  - while keeping `visible_totals.population = "visible_operator"` as the operator-visible baseline
- `project list --format json` now separates raw active status from actionable active work:
  - `visible_totals.active_projects` counts status=`active`
  - `visible_totals.active_work_projects` counts operator-visible actionable work
  - `scope.active_work_visible_projects` matches the actionable `active_work` rows surfaced in the list
- generated audit/repro/benchmark projects keep their artifact categories even when active; they do not relabel as `active_work`
- known zero-task strategic filter fixtures are now treated as retained history instead of current `active_work`
- stale `Recent Progress Project` fixture residue also ages into retained history so old test fixtures stop owning `start` and `dashboard`
- when `visible_totals.active_work_projects = 0`, `project list --format json` stops narrating retained active/history rows as actionable work and instead guides operators toward `dashboard`, `quickstart`, or `project list --include-generated --format json`
- empty global task surfaces such as `task list --format json` and `task ready --format json` now do the same when `suppressed_hidden_count > 0`: they explain that only retained history is hidden, instead of implying there is simply no work anywhere
- machine-readable task surface links now preserve active filters on replay-oriented commands such as `task list`, `task ready`, `task search`, and `task stale`, so `links.self` and widened retained-view hops keep the active query/day/status context instead of collapsing to a generic command
- `project list --format json` now preserves active view/filter context in widened retained-history next steps, so replaying a no-actionable-work response does not drop flags such as `--view detail`
- `project list --view detail --include-linked --format json` now uses normalized machine-readable task links inside linked task payloads, and the top-level self link preserves linked/history replay flags
- `project show --include-linked --format json` and `project summary --format json` now use the same normalized machine-readable command contract for nested task links and project follow-up links, instead of mixing in raw `pms ...` strings
- `project show --format json`, `project summary --format json`,
  `dashboard --format json`, and `start --format json` now expose top-level
  `graph_navigation` for the current focus task, so control-plane payloads can
  jump directly into graph, timeline, proof, plan, actor, and review follow-up
- `project update --format json` now returns normalized project/task follow-up commands in both `links` and `next_steps`, matching the rest of the project-surface contract
- `plan create` now fails early and explicitly when `--format json` content is not valid JSON, instead of surfacing an opaque parse traceback or delegated 400 path
- each item still carries nested `stats`
- each item also exposes flattened completion fields for easier machine use:
  - `total_tasks`
  - `completed_tasks`
  - `in_progress_tasks`
  - `blocked_tasks`
  - `completion_percent`
- `project show --format json` also reconciles top-level `total_tasks`, `completed_tasks`,
  `in_progress_tasks`, and `blocked_tasks` with the `execution` block instead of leaving them null
- `goal summary --format json` now promotes terminal execution state into top-level
  `terminal_reason` and `completion_context` instead of hiding it only inside `execution`
- `GET /api/v1/goals` now surfaces per-goal `effective_rollup`,
  `last_activity_at`, `last_transition_at`, and `terminal_reason` so machine
  clients do not need summary fan-out just to rank goal lifecycle state; goal
  list items now also expose the maintained discoverability `links` and
  per-item `next_steps` contract used by the richer goal detail surfaces
- `GET /api/v1/goals/<goal_id>/summary` now also includes top-level
  `last_activity_at`, `last_transition_at`, `links`, and `next_steps`
- `mcp__pms__get_goal_summary` now returns the same lifecycle aggregate
  primitives for machine consumers: `effective_rollup`, `effective_hierarchy`,
  `execution`, top-level `terminal_reason`, bubbled timestamps, `links`, and
  `next_steps`
- `mcp__pms__list_goals` and `mcp__pms__get_goal` now also return
  machine-readable lifecycle payloads instead of prose-only text, including
  effective rollups, bubbled timestamps, terminal reasoning, structured links,
  and next-step hints
- `goal show --format json` now follows the same maintained goal-detail
  lifecycle contract as the API and MCP goal detail surfaces: `stats`,
  `effective_rollup`, `effective_hierarchy`, `execution`, bubbled
  `last_activity_at` / `last_transition_at`, top-level `terminal_reason`,
  `completion_context`, structured `links`, and `next_steps`
- `goal list --format json` items now expose the maintained goal-list
  lifecycle fields too: `effective_rollup`, bubbled timestamps,
  top-level `terminal_reason`, and machine-readable discoverability `links`
- `objective list --format json`, `objective show --format json`,
  `GET /api/v1/goals/<goal_id>/objectives`,
  `GET /api/v1/objectives/<objective_id>`,
  `mcp__pms__list_objectives`, and `mcp__pms__get_objective` now expose the
  maintained objective lifecycle aggregate contract: `stats` on detail
  surfaces, `effective_rollup`, `effective_hierarchy`, bubbled
  `last_activity_at` / `last_transition_at`, top-level `terminal_reason`,
  terminal `completion_context` on detail surfaces, structured `links`, and
  machine-readable `next_steps`

### Python Client

```python
import asyncio
from pms.client.http_client import PMSClient

async def main():
    async with PMSClient(
        base_url="http://127.0.0.1:27541",
        api_key="your-api-key",
    ) as client:
        # Create product
        product = await client.create_product(
            name="MyService",
            vision="Build amazing things",
            product_type="internal_platform",
        )
        print(f"Created product: {product['id']}")

        # Update product tags/status
        await client.update_product(
            product_id=product["id"],
            status="active",
            tags=["platform"]
        )

        # Create org + team + portfolio + program
        org = await client.create_organization(
            name="Acme Org",
            owner="owner@example.com",
            members=["owner@example.com"]
        )
        team = await client.create_team(
            name="Core Team",
            org_id=org["id"],
            owner="lead@example.com"
        )
        portfolio = await client.create_portfolio(
            name="Platform Portfolio",
            org_id=org["id"]
        )
        program = await client.create_program(
            name="Delivery Program",
            org_id=org["id"],
            portfolio_id=portfolio["id"]
        )
        print(f"Created org/team/portfolio/program: {org['id']} / {team['id']} / {portfolio['id']} / {program['id']}")

        # Create project
        project = await client.create_project(
            name="API Platform",
            description="Backend services",
            org_id=org["id"],
            portfolio_id=portfolio["id"],
            program_id=program["id"],
        )
        project_id = project["id"]

        # Create goal + objective + key result
        goal = await client.create_goal(
            name="Launch V1",
            horizon="short_term"
        )
        objective = await client.create_objective(
            goal_id=goal["id"],
            name="Complete onboarding flow"
        )
        await client.create_key_result(
            objective_id=objective["id"],
            name="Activation rate",
            current_value=35,
            target_value=60,
            unit="%"
        )

        # Create task
        task = await client.create_task(
            project_id=project_id,
            title="Implement feature",
            complexity_points=75,
            priority="high"
        )
        print(f"Created task: {task['id']}")

        # Fetch task tree (hierarchy)
        tree = await client.get_task_tree(project_id=project_id)
        print(f"Task tree roots: {len(tree['nodes'])}")

        # Checkout task
        checkout = await client.checkout_task(
            task_id=task['id'],
            agent_session_id="<agent-session-id>",
            lease_seconds=300
        )
        print(f"Checked out until: {checkout['checkout_lease_until']}")

        # Update progress
        progress = await client.update_progress(
            task_id=task['id'],
            percent_complete=50,
            status_message="Halfway done",
            updated_by="<agent-session-id>"
        )

        # Agent loop summaries
        loops = await client.list_agent_loops(project_id=project_id)
        if loops["items"]:
            loop_id = loops["items"][0]["id"]
            details = await client.get_agent_loop(loop_id)
            messages = await client.get_agent_loop_messages(loop_id, limit=5)
            print(f"Loop {loop_id} status: {details['status']}")
        print(f"Progress: {progress['percent_complete']}%")

        # Add manual evidence (self-declared)
        evidence = await client.add_task_evidence(
            task_id=task['id'],
            evidence_type="scm_commit",
            reference="abc123",
            description="Manual commit reference",
            metadata={"scm": "git"}
        )
        print(f"Evidence: {evidence['id']}")

        # Custom fields
        field = await client.create_custom_field(
            name="risk_level",
            entity_type="task",
            field_type="select",
            options=["low", "medium", "high"]
        )
        await client.set_custom_field_value(
            field_id=field["id"],
            entity_type="task",
            entity_id=task["id"],
            value="high",
            created_by="automation",
        )

        # Comments + watchers
        comment = await client.add_comment(
            entity_type="task",
            entity_id=task["id"],
            body="Blocking on API credentials from ops",
            created_by="alice",
            mentions=["ops-team"],
            watch=True,
        )
        print(f"Comment: {comment['id']}")
        await client.add_watcher(
            entity_type="task",
            entity_id=task["id"],
            watcher="alice",
        )

        # Automation rules (event-driven actions)
        rule = await client.create_automation_rule(
            name="comment-on-task-complete",
            event_pattern="task.completed",
            action_type="add_comment",
            action_payload={
                "body": "Automation: task completed.",
                "created_by": "automation"
            }
        )
        # action_type is a closed vocabulary:
        # add_comment, create_task, update_task_status, set_custom_field_value
        await client.run_automation_rules(event_id="<event-id>", rule_id=rule["id"], dry_run=True)

        # List evidence with test run details
        evidence_page = await client.list_task_evidence(
            task_id=task['id'],
            include_test_runs=True,
            include_output=False
        )
        print(f"Evidence items: {len(evidence_page['items'])}")

        # Export a proof bundle summary
        bundle = await client.get_task_proof_bundle(
            task_id=task['id'],
            include_output=False,
            include_logs=False,
            include_artifacts=False,
        )
        print(f"Proof bundle evidence: {bundle['summary']['evidence_total']}")

        # Search proof bundles by task + status
        bundles = await client.search_evidence_bundles(
            task_id=[task["id"]],
            status=["in_progress"],
            created_from="2025-01-01T00:00:00Z",
            include_evidence=True
        )
        print(f"Proof bundles found: {bundles['total_count']}")

        # Diff revisions for a project
        diff = await client.get_revision_diff(
            entity_type="project",
            entity_id=project_id,
            from_revision=1,
            to_revision=2
        )
        print(f"Revision changes: {len(diff['changes'])}")

        # Export revision history bundle with linked items
        bundle = await client.get_revision_history_bundle(
            entity_type="project",
            entity_id=project_id,
            include_linked=True,
            include_linked_history=True,
            history_limit=20,
            linked_limit=10,
        )
        print(f"History revisions: {bundle['history']['page']['total_count']}")

        # Record a remote test run
        created_run = await client.create_test_run(
            server_id="local",
            project_id=project_id,
            success=True,
            started_at="2026-01-01T00:00:00Z",
            finished_at="2026-01-01T00:00:05Z",
            command="pytest -q",
            runner="remote",
            logs={"/tmp/run.log": {"content": "ok"}}
        )
        print(f"Recorded test run: {created_run['id']}")

        # List test runs
        test_runs = await client.list_test_runs(
            project_id=project["id"],
            include_logs=True
        )
        print(f"Test runs: {test_runs['total_count']}")

        # Get a specific test run with output
        if test_runs["items"]:
            run_id = test_runs["items"][0]["id"]
            run_detail = await client.get_test_run(
                run_id,
                include_output=True,
                include_logs=True,
                include_artifacts=True
            )
            print(f"Run {run_id} status: {run_detail['success']}")

        # Prune stored test outputs (dry run)
        prune_summary = await client.prune_test_runs(
            max_log_bytes=50_000_000,
            max_artifact_bytes=200_000_000,
            max_age_days=30,
            dry_run=True,
        )
        print(f"Prune would remove {prune_summary['log_bytes_pruned']} bytes")

        # Fetch retention usage summary (optionally scoped)
        retention = await client.get_test_run_retention(
            limit=10,
            sort="largest",
            project_id=project_id,
        )
        print(f"Stored logs: {retention['total_log_bytes_combined']}")

        # Set a project-level retention budget
        policy = await client.upsert_test_run_retention_policy(
            scope_type="project",
            scope_id=project_id,
            max_log_bytes=50_000_000,
            max_artifact_bytes=200_000_000,
            max_age_days=30,
            notes="Default project budget",
        )
        print(f"Retention policy: {policy['id']}")

asyncio.run(main())
```

---

## End-to-End Workflow Quick Path

For a complete, real-world walkthrough (product -> project -> goal/objective/key
result -> plan -> tasks -> workflows -> dependencies -> evidence -> completion), see:

- [`docs/END_TO_END_WORKFLOWS.md`](END_TO_END_WORKFLOWS.md)
- [`docs/WEB_API.md`](WEB_API.md) for the API-first walkthrough

---

## API vs CLI vs MCP (Quick Reference)

Use this table to map common actions across interfaces.

| Intent              | CLI                                                                     | MCP Tool                         | API Endpoint                                  |
| ------------------- | ----------------------------------------------------------------------- | -------------------------------- | --------------------------------------------- |
| Create project      | `pms project create "<name>"`                                           | `mcp__pms__create_project`       | `POST /api/v1/projects`                       |
| List tasks          | `pms task list --project "<name>"`                                      | `mcp__pms__list_tasks`           | `GET /api/v1/tasks?project_id=<id>`           |
| Assign workflow     | `pms workflow assign <id> sdlc concept --entity-type task`              | `mcp__pms__assign_workflow`      | `POST /api/v1/tasks/<id>/workflow/assign`     |
| Transition workflow | `pms workflow transition <id> idea --by <user>`                         | `mcp__pms__transition_workflow`  | `POST /api/v1/tasks/<id>/workflow/transition` |
| Update progress     | `pms task progress <task> --project "<name>" <pct> "<msg>" --by <user>` | `mcp__pms__update_task_progress` | `POST /api/v1/tasks/<id>/progress`            |
| Add evidence        | `pms task evidence add <task> <type> <ref>`                             | `mcp__pms__add_task_evidence`    | `POST /api/v1/tasks/<id>/evidence`            |
| Work snapshot       | `pms work snapshot --scope-type project --scope "<name>"`               | `mcp__pms__get_work_snapshot`    | `GET /api/v1/work-snapshots/project/<id>`     |
| Goal summary        | `pms goal summary "<goal>"`                                             | `mcp__pms__get_goal_summary`     | `GET /api/v1/goals/<id>/summary`              |

---

## Acceptance Criteria Mapping (Quick Reference)

PMS does not store acceptance criteria as a standalone entity. Use this mapping:

- Goal: the outcome you want.
- Objective: "acceptance criteria" objective under the goal.
- Key Results: each criterion as a measurable key result.
- Plan: structured criteria + links to tasks.
- Tasks: execution units with workflow states and evidence.

Example flow:

```bash
uv run pms goal create "Launch resume hosting MVP" --project "Resume Hosting Site"
uv run pms objective create "MVP acceptance criteria" --goal "Launch resume hosting MVP"
uv run pms keyresult create "Landing page + upload flow" \
  --objective "MVP acceptance criteria" --goal "Launch resume hosting MVP"
```

---

## ACP Loop Adapters

Use ACP adapters in loop configs to run protocol-level agents (Codex/Qwen/GLM):

```yaml
adapters:
  acp:
    type: acp
    enabled: true
    command: codex-acp
    args: []
    permission_mode: interactive
    permission_allowlist:
      - fs/read_text_file
      - fs/write_text_file
      - terminal/*
```

ACP terminal lifecycle rules:

- `terminal/output` returns `done`, final `exitCode` when available, and
  auto-releases completed finite commands.
- `terminal/wait_for_exit` returns final `output`, `done`, `exitCode`, and
  auto-releases the terminal handle.
- `terminal/release` is idempotent so older clients can still call it after a
  completed command without failing.
- if the ACP subprocess dies between prompts, PMS tears down the stale client
  and reinitializes it on the next loop run instead of reusing dead state.

---

## General Loop Adapter

Use the command adapter to wrap any CLI agent:

```yaml
adapters:
  command:
    type: command
    enabled: true
    command: /path/to/agent
    args: []
    prompt_mode: stdin
```

---

## Codex Loop Adapter

Codex is exposed as a first-class loop adapter (built on ACP):

```yaml
adapters:
  codex:
    type: codex
    enabled: true
    command: codex-acp
    codex_model: null
    codex_reasoning_effort: null
    permission_mode: interactive
```

CLI convenience:

```bash
uv run pms loop run --agent codex --codex-model gpt-5 --codex-reasoning-effort medium
```

---

## End-to-end Loop Example: Resume Hosting Site (Claude)

This example pre-loads a product/project/goals/objectives/key results/tasks, then
runs a Claude loop that iterates until the goal and key results are complete and
records evidence.

### 1) Bootstrap project context

```bash
uv run pms init --reset --force

uv run pms product create "Resume Hosting"
uv run pms project create "Resume Hosting Site" --product "Resume Hosting" \
  -d "Static resume site with upload and hosting workflow"

uv run pms goal create "Launch resume hosting MVP" \
  --project "Resume Hosting Site" \
  --horizon short_term \
  -d "Deliver a working site with upload, hosting, and basic admin review"

uv run pms objective create "MVP acceptance criteria" \
  --goal "Launch resume hosting MVP" \
  -d "Acceptance criteria tracked as key results"

uv run pms keyresult create "Landing page + upload flow" \
  --objective "MVP acceptance criteria" --goal "Launch resume hosting MVP" \
  -d "Landing page, resume preview, and upload form work"
uv run pms keyresult create "Upload API stub works locally" \
  --objective "MVP acceptance criteria" --goal "Launch resume hosting MVP" \
  -d "Local storage stub is wired and returns success"
uv run pms keyresult create "README + run instructions complete" \
  --objective "MVP acceptance criteria" --goal "Launch resume hosting MVP" \
  -d "Setup and run instructions documented"
uv run pms keyresult create "Evidence captured for all tasks" \
  --objective "MVP acceptance criteria" --goal "Launch resume hosting MVP" \
  -d "Each completed task has evidence attached"

cat > plan.yml <<'EOF'
acceptance_criteria:
  - id: ac-1
    description: Public landing page with resume preview + upload flow
  - id: ac-2
    description: Upload API stub wired to local storage (no external services)
  - id: ac-3
    description: README with run instructions and architecture notes
  - id: ac-4
    description: Every task has status updates + evidence
  - id: ac-5
    description: Tests (or smoke checks) are recorded as evidence
EOF

uv run pms plan create "Resume Hosting MVP Plan" \
  --project "Resume Hosting Site" \
  --goal "Launch resume hosting MVP" \
  --objective "MVP acceptance criteria" \
  --format yaml \
  --file plan.yml

uv run pms task create "Resume Hosting Site" "Define UX and requirements"
uv run pms task create "Resume Hosting Site" "Write information architecture + page flow"
uv run pms task create "Resume Hosting Site" "Draft wireframes and copy"
uv run pms task create "Resume Hosting Site" "Implement static site skeleton"
uv run pms task create "Resume Hosting Site" "Build resume upload form (client)"
uv run pms task create "Resume Hosting Site" "Add upload + storage stub API"
uv run pms task create "Resume Hosting Site" "Create resume preview page"
uv run pms task create "Resume Hosting Site" "Add basic admin review page"
uv run pms task create "Resume Hosting Site" "Write README and run instructions"
uv run pms task create "Resume Hosting Site" "Run tests / smoke checks and capture evidence"

uv run pms plan update "Resume Hosting MVP Plan" \
  --project "Resume Hosting Site" \
  --task "Define UX and requirements" \
  --task "Write information architecture + page flow" \
  --task "Draft wireframes and copy" \
  --task "Implement static site skeleton" \
  --task "Build resume upload form (client)" \
  --task "Add upload + storage stub API" \
  --task "Create resume preview page" \
  --task "Add basic admin review page" \
  --task "Write README and run instructions" \
  --task "Run tests / smoke checks and capture evidence"
```

### 2) Create prompt with goals + acceptance criteria

```bash
cat > PROMPT.md <<'EOF'
# Project
Resume Hosting Site (product: Resume Hosting)

# Goal
Launch resume hosting MVP.

# Acceptance criteria
Tracked as key results under the "MVP acceptance criteria" objective and
recorded in the "Resume Hosting MVP Plan". Keep both updated as work completes.

# Loop rules
1) Read PMS state first:
   - `pms product show "Resume Hosting"`
   - `pms project show "Resume Hosting Site"`
   - `pms goal list --project "Resume Hosting Site"`
   - `pms objective list --goal "Launch resume hosting MVP"`
   - `pms keyresult list --objective "MVP acceptance criteria" --goal "Launch resume hosting MVP"`
   - `pms plan show "Resume Hosting MVP Plan" --project "Resume Hosting Site"`
   - `pms task list --project "Resume Hosting Site"`
2) Pick the next task, mark progress, and update status:
   - `pms task start <task> --project "Resume Hosting Site"`
   - `pms task progress <task> --project "Resume Hosting Site" <percent> <message> --by loop-agent`
   - `pms task complete <task> --project "Resume Hosting Site"`
3) If you discover missing work, add tasks immediately:
   - `pms task create "Resume Hosting Site" "<new task title>"`
4) Record evidence for each completed task:
   - `pms task evidence add <task> artifact <path> --project "Resume Hosting Site"`
   - For tests: `pms test run .` then `pms task evidence add <task> test_run <run_id>`
5) Update key results/objective progress as acceptance criteria are met:
   - `pms keyresult update <keyresult> --goal "Launch resume hosting MVP" --progress <percent>`
   - `pms objective update "MVP acceptance criteria" --goal "Launch resume hosting MVP" --progress <percent>`
6) Use `pms goal summary "Launch resume hosting MVP"` each iteration to confirm
   rollups and remaining work.
7) When all key results are complete, complete the goal:
   - `pms goal complete "Launch resume hosting MVP"`
8) When all acceptance criteria are met, output <promise>DONE</promise>.
EOF
```

### 3) Run the Claude loop

```bash
uv run pms loop run --agent claude --project "Resume Hosting Site" \
  --prompt-file PROMPT.md \
  --completion-promise DONE
```

Example commands the agent should execute during the loop:

```bash
uv run pms task list --project "Resume Hosting Site"
uv run pms task progress "Define UX and requirements" --project "Resume Hosting Site" \
  50 "Drafted requirements" --by loop-agent
uv run pms task complete "Define UX and requirements" --project "Resume Hosting Site"
uv run pms task evidence add "Define UX and requirements" artifact docs/requirements.md \
  --project "Resume Hosting Site"
```

Maintained audits now enforce the same lifecycle/progress contract on retained
history:

- non-zero progress cannot remain in a non-active task state
- `done` tasks must read back at `100` percent progress

### 4) Inspect progress + artifacts

```bash
uv run pms task list --project "Resume Hosting Site" --format table
uv run pms task evidence list "<task_id_or_title>" --project "Resume Hosting Site"
uv run pms task proof-bundle "<task_id>"
```

---

## End-to-end Loop Example: Resume Hosting Site (Codex)

Codex runs the same loop through the ACP adapter with identical PMS commands.
Use the same project and prompt file, then switch to Codex:

```bash
uv run pms loop run --agent codex --project "Resume Hosting Site" \
  --prompt-file PROMPT.md \
  --completion-promise DONE \
  --codex-model gpt-5 \
  --codex-reasoning-effort medium
```

If you want Codex to run with an allowlist, add a codex adapter block in a config file:

```yaml
adapters:
  codex:
    type: codex
    enabled: true
    permission_mode: allowlist
    permission_allowlist:
      - fs/read_text_file
      - fs/write_text_file
      - terminal/*
```

---

## Prompt-to-Loop Setup Wizard

Use `pms loop setup` to capture goals, acceptance criteria, tasks, and
dependencies interactively, then generate a loop prompt + config.

Defaults (no prompts):

```bash
uv run pms loop setup --defaults
```

Interactive setup with goal + tasks:

```bash
uv run pms loop setup \
  --org "Acme Org" \
  --product "Resume Hosting" \
  --project "Resume Hosting Site" \
  --goal "Launch resume hosting MVP" \
  --goal-horizon short_term
```

Outputs:

- `PROMPT.md`: detailed loop instructions for the agent.
- `pms-loop.yml`: loop config with goal guard enabled.

The wizard also:

- Creates a goal + objective + key results for acceptance criteria.
- Creates tasks and optional dependencies.
- Stores acceptance criteria + task mapping in the plan content.

If you already have a plan, render a prompt with IDs prefilled:

```bash
uv run pms loop prompt-template \
  --project "Resume Hosting Site" \
  --goal "Launch resume hosting MVP" \
  --plan "Resume Hosting MVP Plan" \
  --prompt-file PROMPT.md \
  --force
```

Validation contract:

- `pms loop prompt-template` fails nonzero if you mix name and ID selectors for
  the same entity, for example `--goal` with `--goal-id`.
- `pms loop prompt-template` also fails nonzero when the required project/goal/
  objective/plan chain cannot be resolved.
- `pms work snapshot`, `pms work review`, and `pms work daily` now use the same
  nonzero contract for conflicting `--scope` and `--scope-id` selectors.
- in `--format json` mode, those work-surface validation failures return
  `{"error": ...}` instead of a fake success.
- `pms loop run` fails nonzero when neither inline prompt text nor `--prompt-file`
  is provided.
- `pms test retention-policy update --format json` fails nonzero with
  `{"error": ...}` when no update fields are supplied.
- `pms program create`, `pms program list`, and `pms program dashboard` now use
  the same nonzero contract for conflicting `--org`/`--org-id` and
  `--portfolio`/`--portfolio-id` selectors.
- `pms team create`, `pms portfolio create`, and `pms portfolio list` now use
  the same nonzero contract for conflicting `--org` and `--org-id` selectors.
- `pms plan lineage` and `pms plan update --output-format json` now use the same
  nonzero contract for conflicting project/goal/objective selector pairs.

Interactive plan builder prompt (agent intake):

- Use [`docs/AGENT_PROMPT_INTERACTIVE_PLAN.md`](AGENT_PROMPT_INTERACTIVE_PLAN.md) as the agent's starting prompt.
- It walks the agent through intake questions, creates the full PMS graph, and
  generates a loop prompt + config for the execution loop.

Prompt templates you can reuse:

- [`docs/AGENT_PROMPT_MINIMAL.md`](AGENT_PROMPT_MINIMAL.md) for a short intake flow.
- [`docs/AGENT_PROMPT_MCP_LOOP.md`](AGENT_PROMPT_MCP_LOOP.md) for MCP-only agents.

To start immediately, add `--run`. Otherwise run:

```bash
uv run pms loop run --config pms-loop.yml
```

---

## Claude Code Stop Hook: Keep Working Until Goals Are Complete

Use a Claude Code `Stop` hook to block stopping until all PMS goals in scope are
completed. This prevents the agent from asking "what next?" mid-flight.

For the maintained live harness guide, including generic wrappers and MCP-only
hosts, see [`docs/AGENT_INTEGRATION_GUIDE.md`](AGENT_INTEGRATION_GUIDE.md).

Preferred `.claude/settings.local.json` snippet when you want both the stop
decision and a PMS audit bundle:

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
    ]
  }
}
```

Minimal direct-guard form:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "cd \"$CLAUDE_PROJECT_DIR\" && uv run pms loop guard --project \"Resume Hosting Site\" --hook"
          }
        ]
      }
    ]
  }
}
```

Notes:

- `scripts/agent_hooks/pms_stop_audit.py` captures `start`, `dashboard`,
  `task ready`, project task list, `work daily`, and goal summaries into a
  deterministic bundle under `PMS_DATA_DIR/hook-audits/`.
- `pms loop guard` blocks stop when goals are incomplete and returns Claude Code
  `Stop` hook JSON when `--hook` is set.
- `pms loop guard --format json` fails nonzero with `{"error": ...}` if you do
  not provide either `--project`/`--project-id` or at least one goal selector.
- Use `--goal-id <id>` (repeatable) to pin the guard to explicit goals.
- Add `--allow-no-goals` if you want to allow stopping when no goals exist.
- If permission prompts interrupt the loop, add a Claude Code `PermissionRequest`
  hook allowlist or use the Codex adapter `permission_allowlist`.

---

## Loop Guard in the Runner (Soft-Stop Gate)

If you want the loop runner itself to ignore completion markers/promises until
goals are complete, enable the guard in your loop config or CLI command:

```bash
uv run pms loop run --agent claude --project "Resume Hosting Site" \
  --prompt-file PROMPT.md \
  --completion-promise DONE \
  --stop-when-goals-complete \
  --goal "Launch resume hosting MVP"
```

Config form (`pms-loop.yml`):

```yaml
stop_when_goals_complete: true
goal_ids:
  - <goal-id>
include_archived_goals: false
allow_no_goals: false
```

Hard stops (max runtime, max cost, cancel) still apply. The guard only blocks
completion markers/promises until goals are complete.

---

## Claude Code PermissionRequest Allowlist Hook

Use this hook to auto-approve safe PMS commands and MCP tool calls so the agent
does not stall on permissions.

1. Add the helper script in this repo:

`scripts/claude_hooks/pms_permission_allowlist.py`

2. Configure the hook in `.claude/settings.local.json`:

```json
{
  "hooks": {
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

3. (Optional) Extend the allowlist with regex patterns:

```
export PMS_HOOK_ALLOWLIST_REGEX="^uv run pms\\b,^pms\\b"
```

The hook auto-allows:

- `Bash` commands matching the allowlist regex.
- MCP tools whose names start with `mcp__pms__`.

---

## Authentication

All API calls require `X-API-Key`. Bootstrap the first key locally:

```bash
uv run pms auth init --show-key
```

---

## Client API

### Auth

```python
await client.get_available_scopes()
await client.create_api_key(name, scopes=["tasks:read"], expires_in_days=30, rate_limit=1000, metadata={"owner": "cli"})
await client.list_api_keys(include_inactive=False, include_archived=False)
await client.get_api_key(key_id)
await client.deactivate_api_key(key_id)
await client.restore_api_key(key_id)
await client.delete_api_key(key_id)
await client.get_dashboard()
await client.get_dashboard_html()
```

Use `get_dashboard()` for the JSON operator surface at `/api/v1/dashboard`
and `get_dashboard_html()` for the rendered web dashboard at `/dashboard`.
The maintained Python and Rust clients are dynamically parity-audited for
`get_dashboard()`, `get_dashboard_html()`, `get_organization_dashboard()`,
`get_portfolio_dashboard()`, and `get_program_dashboard()` against one shared
live fixture during the release gate.

Maintained lifecycle-list parity is narrower and explicit:

- the maintained Python client and maintained Rust client are release-gate
  audited for `list_tasks()` and `list_plans()` semantics
- current guaranteed shared filters:
  - `list_tasks(project_id, status, limit, offset)`
  - `list_plans(status, project_id, product_id, goal_id, objective_id, task_id, limit, offset)`
- that parity is guarded two ways:
  - dynamic live audit:
    - `scripts/audit_client_lifecycle_list_payload_parity.py`
  - static source-contract audit:
    - `scripts/audit_client_lifecycle_list_surface_contracts.py`
    - checks the exact Python method blocks, Rust client functions, and Rust CLI
      list variants that define the maintained lifecycle-list contract
- `start` is intentionally not part of maintained Python-vs-Rust client-library
  parity:
  - the Python async client exposes data-plane HTTP methods
  - `start` remains an operator CLI surface
  - the compiled Rust binary may expose `start`, but treat that as CLI behavior,
    not a shared library contract

### Products

```python
await client.create_product(name, description=None, vision=None, repository_url=None, owner=None, product_type=None, tags=None)
await client.list_products(status=None, limit=100)
await client.get_product(product_id)
await client.get_product_summary(product_id)
await client.update_product(product_id, name=None, description=None, vision=None, repository_url=None, owner=None, product_type=None, status=None, tags=None)
await client.archive_product(product_id)
```

`product_type` remains intentionally open. Treat it as descriptive
categorization, not a closed taxonomy.

### Projects

```python
await client.create_project(name, description=None, tags=None, org_id=None, portfolio_id=None, program_id=None, product_id=None)
await client.list_projects(status=None, limit=100)
await client.get_project(project_id)
await client.update_project(project_id, name=None, description=None, status=None, tags=None, org_id=None, portfolio_id=None, program_id=None, product_id=None)
await client.get_project_summary(project_id)
```

### Organizations

```python
await client.create_organization(
    name,
    description=None,
    owner=None,
    members=None,
    tags=None,
)
await client.list_organizations(status=None, limit=100)
await client.get_organization(org_id)
await client.update_organization(
    org_id,
    name=None,
    description=None,
    status=None,
    owner=None,
    members=None,
    tags=None,
)
await client.get_organization_summary(org_id)
await client.get_organization_dashboard(status=None, limit=100, offset=0)
```

### Teams

```python
await client.create_team(
    name,
    org_id=None,
    description=None,
    owner=None,
    members=None,
    tags=None,
)
await client.list_teams(status=None, org_id=None, limit=100)
await client.get_team(team_id)
await client.update_team(
    team_id,
    name=None,
    description=None,
    status=None,
    owner=None,
    members=None,
    tags=None,
)
```

### Portfolios

```python
await client.create_portfolio(
    name,
    org_id=None,
    description=None,
    owner=None,
    project_ids=None,
    goal_ids=None,
    objective_ids=None,
    tags=None,
)
await client.list_portfolios(status=None, org_id=None, limit=100)
await client.get_portfolio(portfolio_id)
await client.update_portfolio(
    portfolio_id,
    name=None,
    description=None,
    status=None,
    owner=None,
    project_ids=None,
    goal_ids=None,
    objective_ids=None,
    tags=None,
)
await client.get_portfolio_summary(portfolio_id)
await client.get_portfolio_dashboard(status=None, org_id=None, limit=100, offset=0)
```

### Programs

```python
await client.create_program(
    name,
    org_id=None,
    portfolio_id=None,
    description=None,
    owner=None,
    project_ids=None,
    goal_ids=None,
    objective_ids=None,
    tags=None,
)
await client.list_programs(status=None, org_id=None, portfolio_id=None, limit=100)
await client.get_program(program_id)
await client.update_program(
    program_id,
    name=None,
    description=None,
    status=None,
    owner=None,
    project_ids=None,
    goal_ids=None,
    objective_ids=None,
    tags=None,
)
await client.get_program_summary(program_id)
await client.get_program_dashboard(status=None, org_id=None, portfolio_id=None, limit=100, offset=0)
```

Portfolio/program readbacks now split direct strategic links from hydrated
effective scope.

- `project_ids` reflect project foreign-key assignments into the
  portfolio/program scope.
- `goal_ids` / `objective_ids` are the direct portfolio/program strategic links
  stored in native edge tables.
- `effective_goal_ids` / `effective_objective_ids` are the hydrated union of:
  - direct portfolio/program links
  - project-derived goal/objective scope

Treat the `effective_*` fields as the authoritative read-model scope outputs,
not as cached child-array columns on the portfolio/program rows.

### Goals

```python
await client.create_goal(name, description=None, horizon="short_term", owner=None)
await client.list_goals(status=None, horizon=None, product_id=None, project_id=None)
await client.get_goal(goal_id)
await client.update_goal(goal_id, progress_percent=50, owner=None)
await client.complete_goal(goal_id)
await client.archive_goal(goal_id)
await client.get_goal_summary(goal_id)
await client.assign_goal_workflow(goal_id, workflow_name, initial_state)
await client.transition_goal_workflow(goal_id, to_state, triggered_by, reason=None, approved_by=None)
```

### Plans

```python
await client.create_plan(
    name,
    description=None,
    status="draft",
    format="json",
    content={"stages": ["plan", "implement", "test"]},
    project_id=None,
)
await client.list_plans(status=None, project_id=None, product_id=None)
await client.get_plan_lineage(status=None, project_id=None, plan_id=None)
await client.get_plan(plan_id)
await client.update_plan(plan_id, status="active", content={"stages": ["plan", "ship"]})
await client.create_plan_test_job(
    plan_id,
    name="Local smoke tests",
    project_path=".",
    test_command="python -m pytest -q",
)
await client.list_plan_test_jobs(plan_id)
await client.get_plan_test_job(plan_id, job_id)
await client.update_plan_test_job(plan_id, job_id, timeout=900)
await client.run_plan_test_job(plan_id, job_id)
await client.delete_plan_test_job(plan_id, job_id)
```

### Objectives

```python
await client.create_objective(goal_id, name, description=None, owner=None)
await client.list_objectives(goal_id, status=None)
await client.get_objective(objective_id)
await client.update_objective(objective_id, progress_percent=50, owner=None)
await client.complete_objective(objective_id)
await client.archive_objective(objective_id)
await client.assign_objective_workflow(objective_id, workflow_name, initial_state)
await client.transition_objective_workflow(objective_id, to_state, triggered_by, reason=None, approved_by=None)
```

### Key Results

```python
await client.create_key_result(
    objective_id,
    name,
    current_value=10,
    target_value=20,
    owner=None,
)
await client.list_key_results(objective_id, status=None)
await client.get_key_result(key_result_id)
await client.update_key_result(
    key_result_id,
    current_value=20,
    target_value=20,
    owner=None,
)
await client.complete_key_result(key_result_id)
await client.archive_key_result(key_result_id)
```

### Tasks

```python
await client.create_task(
    project_id,
    title,
    complexity_points=None,
    priority="medium",
)
await client.list_tasks(project_id=None, limit=100)
await client.search_tasks(
    query=None,
    project_id=None,
    status=None,
    priority=None,
    assignee=None,
)
await client.list_duplicate_tasks(project_id=None, status=None, include_terminal=False, min_count=2)
await client.preview_duplicate_merge(primary_task_id, [dup_id1, dup_id2])
await client.merge_duplicate_tasks(primary_task_id, [dup_id1, dup_id2], cancel_duplicates=True)
await client.list_ready_tasks(project_id=None, status=None, exclude_checked_out=True)
await client.list_stale_tasks(project_id=None, status=None, stale_after_days=14)
await client.start_task(task_id)
await client.complete_task(task_id, notes=None)
await client.update_task(task_id, title=None, description=None, priority=None, complexity_points=None)
await client.transition_task_workflow(task_id, to_state, triggered_by, reason=None, approved_by=None)
await client.align_workflow(entity_id, entity_type, triggered_by, to_state=None, reason=None, approved_by=None, auto=True, dry_run=False)
await client.align_task_workflow(task_id, triggered_by, to_state=None, reason=None, approved_by=None, auto=True, dry_run=False)
await client.add_task_evidence(task_id, evidence_type, reference, description=None, metadata=None, created_by=None)
await client.list_task_evidence(task_id, include_test_runs=False, include_output=False, limit=100, offset=0)
await client.get_revision_diff(entity_type, entity_id, from_revision, to_revision)
await client.get_revision_history_bundle(entity_type, entity_id, include_linked=False, include_linked_history=False, history_limit=20, history_offset=0, linked_limit=20, linked_history_limit=20)
await client.search_evidence_bundles(task_id=None, plan_id=None, status=None, evidence_type=None, created_from=None, created_to=None, include_evidence=False, include_test_runs=False, include_output=False, include_logs=False, include_artifacts=False, limit=50, offset=0)
await client.get_task_proof_bundle(task_id, include_output=False, include_logs=False, include_artifacts=False)
await client.list_test_runs(project_id=None, server_id=None, success=None, include_output=False, include_logs=False, include_artifacts=False, limit=100, offset=0)
await client.prune_test_runs(
    max_log_bytes=None,
    max_artifact_bytes=None,
    max_age_days=None,
    dry_run=False,
    project_id=None,
    org_id=None,
    use_policies=True,
)
await client.get_test_run_retention(limit=20, sort="largest", project_id=None, org_id=None)
await client.list_test_run_retention_policies(scope_type=None, scope_id=None, include_archived=False)
await client.upsert_test_run_retention_policy("project", project_id, max_log_bytes=0, max_artifact_bytes=0, max_age_days=0)
await client.get_test_run_retention_policy(policy_id)
await client.update_test_run_retention_policy(policy_id, max_log_bytes=0)
await client.archive_test_run_retention_policy(policy_id)
await client.restore_test_run_retention_policy(policy_id)
await client.get_test_run(run_id, include_output=True, include_logs=True, include_artifacts=True)
await client.get_work_snapshot("project", project_id, task_limit=5, test_limit=5)
await client.mark_work_snapshot_reviewed(
    "project",
    project_id,
    reviewed_by="alice@example.com",
    note="Weekly review",
    metadata={"session": "weekly-review"},
)
await client.create_saved_search(
    name="Backend Queue",
    filters={"tags": ["backend"], "statuses": ["todo", "in_progress"]},
    sort_by="priority",
    sort_dir="desc",
)
await client.list_saved_searches(
    owner=None,
    scope_type=None,
    scope_id=None,
    limit=100,
    offset=0,
)
await client.get_saved_search(queue_id)
await client.update_saved_search(queue_id, name="Updated Queue")
await client.run_saved_search(queue_id, limit=25, offset=0)
await client.delete_saved_search(queue_id)
await client.list_queue_presets(project_id=None, limit=5)
await client.get_queue_preset("ready", project_id=None, limit=10, offset=0)
```

Closed value reminders for these client surfaces:

- `create_saved_search(..., sort_dir=...)` and `update_saved_search(..., sort_dir=...)`
  use `asc` or `desc`
- `get_test_run_retention(sort=...)` uses `largest` or `recent`

### Labels

```python
await client.create_label_category(name, description=None, is_exclusive=False, sort_order=0)
await client.list_label_categories()
await client.get_label_category(category_id)
await client.update_label_category(category_id, name=None, description=None, is_exclusive=None, sort_order=None)
await client.delete_label_category(category_id)
await client.restore_label_category(category_id)

await client.create_label(name, description=None, category_id=None, color=None, is_system=False)
await client.list_labels(category_id=None)
await client.get_label(label_id)
await client.update_label(label_id, name=None, description=None, category_id=None, color=None, is_system=None)
await client.delete_label(label_id)
await client.restore_label(label_id)

await client.assign_label(entity_type, entity_id, label_id, applied_by=None)
await client.list_label_assignments(entity_type, entity_id, limit=100, offset=0)
await client.get_label_assignment_history(assignment_id, limit=20, offset=0)
await client.remove_label_assignment(entity_type, entity_id, label_id)

await client.create_label_gate_rule(
    workflow_id,
    entity_type,
    from_state,
    to_state,
    rule_type,
    label_id=None,
    category_id=None,
    message=None,
)
await client.list_label_gate_rules(workflow_id, entity_type, from_state, to_state)
await client.delete_label_gate_rule(rule_id)

await client.create_evidence_gate_rule(
    workflow_id,
    entity_type,
    from_state,
    to_state,
    evidence_type,
    min_count=1,
    require_success=False,
    message=None,
)
await client.list_evidence_gate_rules(workflow_id, entity_type, from_state, to_state)
await client.delete_evidence_gate_rule(rule_id)
```

### Checkout

```python
await client.checkout_task(task_id, agent_session_id, lease_seconds=300)
await client.renew_checkout(task_id, agent_session_id, lease_seconds=300)
await client.release_checkout(task_id, agent_session_id)
await client.force_release_checkout(task_id, released_by="admin", reason=None)
await client.list_available_tasks(project_id=None, limit=100)
await client.list_agent_checkouts(agent_session_id, include_expired=False)
await client.cleanup_expired_checkouts(dry_run=False)
await client.get_checkout_log(task_id=task_id, limit=50, success=True, include_metadata=False)
async for entry in client.iter_checkout_log(task_id=task_id, page_size=50):
    print(entry["action"])
```

CLI examples:

```bash
# Dashboards (Rust CLI)
./pms-client org dashboard --limit 5
./pms-client portfolio dashboard --org-id <org-id> --limit 5
./pms-client program dashboard --portfolio-id <portfolio-id> --limit 5

# Plans, queues, and test runs (Rust CLI)
./pms-client plan create "Release Plan" --project-id <project-id> --content '{"milestones":["alpha","beta"]}'
./pms-client plan test-job run <plan-id> <job-id> --include-output
./pms-client queue create "ready" --filters '{"status":"ready"}'
./pms-client queue preset ready --project-id <project-id>
./pms-client task tree --project-id <project-id>
./pms-client test-run record --server-id local --status passed \
  --started-at 2026-01-01T00:00:00Z --finished-at 2026-01-01T00:00:05Z \
  --project-id <project-id> --command "pytest -q"
./pms-client test-run list --project-id <project-id> --include-output
./pms-client test-run retention --project-id <project-id>

# Evidence, timelines, revisions, and work snapshots (Rust CLI)
./pms-client task evidence add <task-id> "manual" "notes.md" --description "Manual notes"
./pms-client task evidence list <task-id> --include-test-runs
./pms-client task proof-bundle <task-id> --include-output
./pms-client task block <task-id> --reason "Waiting on review" --by alice
./pms-client task dep add <task-id> <task-id-2> --dependency-type blocks
./pms-client evidence gate list <workflow-id> task todo done
./pms-client evidence bundle-search --plan-id <plan-id> --include-evidence
./pms-client workflow show sdlc --format json
./pms-client timeline workflow task <task-id>
./pms-client revision bundle task <task-id> --include-linked
./pms-client work snapshot project <project-id>
./pms-client work daily project <project-id> --format text
./pms-client dashboard
```

For maintained production-style proof across the Rust client, server API, and
Python CLI, use the repo-level evidence path instead of ad hoc spot checks:

```bash
bash ./scripts/run_rust_client_parity_smoke.sh
bash ./scripts/run_rust_degraded_runtime_recovery_contract_smoke.sh
bash ./scripts/run_network_interop_benchmark_contract_smoke.sh
bash ./scripts/run_proof_bundle_contract_smoke.sh
```

Latest benchmark and readiness artifacts:

- `artifacts/network_interop/latest/benchmark-bundle.summary.json`
- `$PMS_DATA_DIR/proof-bundle.summary.json`
- [`client-rust/README.md`](../client-rust/README.md)
- [`examples/real_world/README.md`](../examples/real_world/README.md)

`artifacts/network_interop/latest` is a convenience symlink to the newest
timestamped benchmark bundle, not a separate authoritative copy.

```
pms quickstart --defaults
pms task list --project "My Project" --view overview --format json
pms task checkout-log --task-id <task-id> --format csv --include-metadata
pms task checkout-log --task-id <task-id> --verbose --include-metadata
pms task checkout-status --agent-id <agent-session-id> --format json
pms task checkout-status --agent-id <agent-session-id> --format csv
pms task available --project "My Project" --format json
pms task timeline <task-id> --format csv
pms timeline workflow task <task-id> --format csv
pms timeline status task <task-id> --format csv
pms task list --project "My Project" --format csv
pms task blocked --project "My Project" --format json
pms task show <task-id> --format json
pms task graph <task-id> --format csv
pms project list --format csv
pms product list --format csv
pms goal list --format csv
pms objective list --goal-id <goal-id> --format csv
pms keyresult list --objective-id <objective-id> --format csv
pms project show "Project Name" --format json
pms project summary "Project Name" --format json
pms product show <product-id> --format csv
pms goal show <goal-id> --format json
pms project history "Project Name" --format csv
pms product summary <product-id> --format json
pms goal summary <goal-id> --format json
pms workflow list --format json
pms remote list --format csv
pms remote show myhost --format json
pms auth list --api-key $PMS_API_KEY --format csv
pms capabilities list --format csv
pms capabilities health --format csv
pms namespace list --format csv
pms namespace show task --format json
pms plugin list --format csv
pms plugin show my-plugin --format csv
pms plugin tools --format csv
pms plugin stats --format json
pms capabilities info --format csv
pms aws server list --format csv
pms aws server show myserver --format json
pms dashboard --format json
pms org dashboard --format json
pms portfolio dashboard --org-id <org-id> --format json
pms program dashboard --org-id <org-id> --portfolio-id <portfolio-id> --format json
pms org list --view overview --format json
pms org show <org-id> --view detail --include-history --format json
pms team list --view overview --format json
pms portfolio show <portfolio-id> --view trace --include-linked --include-linked-history --format json
pms program show <program-id> --view detail --include-linked --format json
pms plan list --view overview --format json
pms plan show <plan-id> --view trace --include-linked --format json
pms goal show <goal-id> --view detail --include-history --format json
pms objective show <objective-id> --view trace --include-linked --format json
pms keyresult show <key-result-id> --view detail --format json
pms aws spot find --format csv
```

`pms namespace show` describes namespace-generated typed-ID families plus the
schema metadata and runtime row-ID contract scope/style PMS exposes for them.
It is not the full runtime row-ID contract for every public entity family.

Machine-readable schema surfaces now make that split explicit with:

- `namespace_generated_id_format`
- `namespace_generated_id_kind`
- `runtime_row_id_contract_scope`
- `runtime_row_id_style`

`pms namespace show --format json|csv` now exports those same fields so the
interactive and machine-readable `namespace show` surfaces stay in parity.
`pms namespace list --format json|csv` now exports the same contract metadata at
list scope.

Read the runtime fields together:

- `runtime_row_id_contract_scope = public_stored_entity_family`
  - this namespace family participates in the public runtime row-ID contract
- `runtime_row_id_contract_scope = internal_or_non_public_namespace`
  - this namespace is cataloged for type/introspection purposes, but the public
    runtime row-ID contract does not apply there

Task list JSON overview fields: `id`, `title`, `status`, `priority`, `description`, `project_id`,
`project_name`, `created_at`, `updated_at`, `due_date`, `completed_at`, `assignee`, `tags`,
`labels`, `current_progress_percent`, `workflow_id`, `current_state`, `is_overdue`,
`last_activity_at`, `last_transition_at`, `links`.

`task list --status <value>` must honor the same status predicate on both the instance-wide path
and the project-scoped path. Terminal task rows are emitted as `status: "done"` in CLI JSON.
Global `task list --format json` now also uses explicit population contracts:

Maintained client parity for lifecycle lists currently guarantees:

- Python `PMSClient.list_tasks()` and Rust `PMSClient::list_tasks()` accept the
  same task-list filter and pagination surface:
  - `project_id`
  - `status`
  - `limit`
  - `offset`
- Python `PMSClient.list_plans()` and Rust `PMSClient::list_plans()` accept the
  same plan-list filter and pagination surface:
  - `status`
  - `project_id`
  - `product_id`
  - `goal_id`
  - `objective_id`
  - `task_id`
  - `limit`
  - `offset`
- the maintained Rust CLI mirrors those lifecycle-list filters on:
  - `pms-client task list`
  - `pms-client plan list`
- `start` is not part of this maintained lifecycle-list contract, because it is
  an operator guide surface rather than a shared client-library method

Maintained cross-surface lifecycle aggregate parity is a separate contract from
that lifecycle-list client parity.

Included goal aggregate JSON surfaces:

- CLI:
  - `goal list --format json`
  - `goal show --format json`
  - `goal summary --format json`
- API:
  - `GET /api/v1/goals`
  - `GET /api/v1/goals/<goal_id>`
  - `GET /api/v1/goals/<goal_id>/summary`
- MCP:
  - `mcp__pms__list_goals`
  - `mcp__pms__get_goal`
  - `mcp__pms__get_goal_summary`

Included objective aggregate JSON surfaces:

- CLI:
  - `objective list --format json`
  - `objective show --format json`
- API:
  - `GET /api/v1/goals/<goal_id>/objectives`
  - `GET /api/v1/objectives/<objective_id>`
- MCP:
  - `mcp__pms__list_objectives`
  - `mcp__pms__get_objective`

Included key result aggregate JSON surfaces:

- CLI:
  - `keyresult list --format json`
  - `keyresult show --format json`
- API:
  - `GET /api/v1/objectives/<objective_id>/key-results`
  - `GET /api/v1/key-results/<key_result_id>`
- MCP:
  - `mcp__pms__list_key_results`
  - `mcp__pms__get_key_result`

Included project aggregate JSON surfaces:

- CLI:
  - `project show --format json`
  - `project summary --format json`
- API:
  - `GET /api/v1/projects/<project_id>`
  - `GET /api/v1/projects/<project_id>/summary`
- MCP:
  - `mcp__pms__get_project`
  - `mcp__pms__get_project_summary`

Maintained goal aggregate guarantees:

- goal list items expose:
  - `effective_rollup`
  - bubbled `last_activity_at`
  - bubbled `last_transition_at`
  - top-level `terminal_reason`
  - machine-readable `links`
  - machine-readable `next_steps`
- goal detail and summary surfaces expose:
  - `stats`
  - `effective_rollup`
  - `effective_hierarchy`
  - `execution`
  - bubbled `last_activity_at`
  - bubbled `last_transition_at`
  - top-level `terminal_reason`
  - terminal `completion_context`
  - machine-readable `links`
  - machine-readable `next_steps`

Maintained objective aggregate guarantees:

- objective list items expose:
  - `effective_rollup`
  - `effective_hierarchy`
  - bubbled `last_activity_at`
  - bubbled `last_transition_at`
  - top-level `terminal_reason`
  - machine-readable `links`
  - machine-readable `next_steps`
- objective detail surfaces expose the same lifecycle fields plus:
  - `stats`
  - `completion_context`

Maintained key result aggregate guarantees:

- key result list items expose:
  - `effective_rollup`
  - bubbled `last_activity_at`
  - bubbled `last_transition_at`
  - top-level `terminal_reason`
  - machine-readable `links`
  - machine-readable `next_steps`
- key result detail surfaces expose the same lifecycle fields plus:
  - `completion_context`
- explicit leaf-surface exclusions:
  - no `effective_hierarchy`
  - no `execution`
  - no nested rollup claims beyond the stored key result leaf itself

Maintained project aggregate guarantees:

- project detail and summary surfaces keep lifecycle-aware status semantics
  instead of reporting only stored row state
- terminal projects stay terminal when only passive planning residue remains
- project aggregate payloads keep:
  - bubbled `last_activity_at`
  - bubbled `last_transition_at`
  - top-level `terminal_reason`
  - canonical detail `links`
  - machine-readable `next_steps`

Guardrails:

- static source contract:
  - `uv run python scripts/audit_cross_surface_lifecycle_aggregate_source_contracts.py --check`
- dynamic surface contracts:
  - `uv run python scripts/audit_cli_goal_lifecycle_contracts.py --check`
  - `uv run python scripts/audit_cli_key_result_lifecycle_contracts.py --check`
  - `uv run python scripts/audit_api_goal_lifecycle_contracts.py --check`
  - `uv run python scripts/audit_api_key_result_lifecycle_contracts.py --check`
  - `uv run python scripts/audit_mcp_goal_lifecycle_contracts.py --check`
  - `uv run python scripts/audit_mcp_key_result_lifecycle_contracts.py --check`
  - `uv run python scripts/audit_cross_surface_project_lifecycle_contracts.py --check`
  - `uv run python scripts/audit_cross_surface_operator_dashboard_contracts.py --check`

Explicit exclusions:

- `start` is an operator guide surface, not a maintained lifecycle aggregate
  parity target
- text, table, and CSV renderings are human-facing and not schema-stable
- widened linked/history/generated variants are not parity targets unless a
  dedicated audit names them explicitly
- Rust client and Rust CLI collection parity is tracked separately by the
  lifecycle-list contract above; do not infer aggregate parity from collection
  parity alone

- default instance-wide `scope.population = "visible_operator"`
- default instance-wide `population_totals.population = "visible_operator"`
- `task list --include-generated --format json` switches:
  - `scope.population = "all_retained"`
  - `population_totals.population = "all_retained"`
  - while keeping `visible_totals.population = "visible_operator"` as the operator-visible baseline
- project-scoped `task list --project ... --format json` uses `scope.population = "scoped_project"`
- default instance-wide task lists suppress tasks from generated/history-only projects and report `suppressed_hidden_count`
- task rows now expose:
  - `project_operator_category`
  - `project_operator_category_label`
  - `project_operator_visibility_reason`
- text `task list` now defaults to `--view review`, which is grouped for
  at-a-glance auditing:
  - `Focus`
  - `In Progress`
  - `In Review`
  - `Blocked`
  - `Ready`
  - `Recently Done`
  - `Cancelled`
- use `task list --view overview` when you intentionally want the older dense
  table view
- `task search`, `task ready`, `task stale`, and `task blocked` now default to
  the same review-first text surface; use `--view overview` when you want the
  older dense table on those entry surfaces
- `task list --format json` now exposes `graph_navigation` for the current
  focus task, with replayable commands and machine links for:
  - `task show`
  - `task graph`
  - `task timeline`
  - `plan list --task-id`
  - `task evidence list`
  - `actor show`
  - `project show`
  - `task tree --project`
  - `work review --scope-type project --scope-id ...`

`task search --format json` now follows the same top-level object contract instead of a bare array:

- default instance-wide `scope.population = "visible_operator"`
- `task search --include-generated --format json` switches `scope.population` and `population_totals.population` to `all_retained`
- default instance-wide task searches suppress generated/history-only project tasks and report `suppressed_hidden_count`
- search result rows surface the same project visibility metadata fields as `task list`
- `task ready`, `task stale`, and `task blocked` now use that same top-level population contract family instead of bare arrays
- `task duplicates` now uses that same top-level population contract family instead of a bare array
- their default instance-wide views are `visible_operator`; `--include-generated` switches retained totals to `all_retained`
- `task search --format json`, `task ready --format json`,
  `task stale --format json`, and `task blocked --format json` now also expose
  top-level `focus_task` plus `graph_navigation`
- `queue run --format json`, `queue presets --format json`,
  `work daily --format json`, and `work review --format json` now extend that
  graph contract into operator queue and review surfaces:
  - queue and daily payloads expose actor-aware `focus_task` payloads plus
    top-level `graph_navigation`
  - review payloads expose scope-based `graph_navigation` back into the project
    graph when there is no single focus task
- maintained actor-rollup math coverage now lives in
  `uv run python scripts/audit_actor_workload_math.py --check`
- `task timeline` now reconciles terminal task progress into the timeline view even when the task only has snapshot-backed completion state

Project show JSON stats fields (when present): `total_tasks`, `completed_tasks`, `in_progress_tasks`,
`blocked_tasks`, `total_milestones`, `completed_milestones`, `total_complexity_points`,
`avg_complexity_per_task`, `total_duration_hours`, `avg_duration_per_task`, `avg_efficiency_score`,
`overdue_tasks`, `total_goals`, `completed_goals`, `avg_goal_progress`, `completion_percent`,
`complexity_velocity`, `health_score`.

Dashboard JSON uses two task/project populations intentionally:

- top-level `total_projects`, `total_tasks`, `completed_tasks`, `blocked_tasks`, `overdue_tasks`
  describe the current visible operator surface
- `instance_totals` describes all non-archived retained project/task state across the instance
- archived projects are excluded from `instance_totals`
- `visible_totals.population` is `visible_operator`
- `instance_totals.population` is `all_non_archived_retained`
- queue preset counts in dashboard JSON are scoped to the visible operator population
- standalone `queue presets --format json` uses that same visible operator population by default
- `goal list --format json` now follows the same contract family:
  default output is `visible_operator`, while `--include-generated` widens to `all_retained`
- use `uv run python scripts/report_active_goal_backlog.py` when you need a severity-ranked view of active goals versus retained fixture residue before starting more work
- use `uv run python scripts/cleanup_fixture_backlog.py` to classify active fixture/test residue and orphaned nonterminal state before deciding that the PMS instance has real backlog
- use `uv run python scripts/cleanup_fixture_backlog.py --apply` only after the dry run shows known fixture categories or orphan lifecycle mismatches you intend to normalize
- `/api/v1/queues/presets` and `/api/v1/queues/presets/{preset}` now expose the same queue `population` contract:
  `visible_operator` instance-wide, `scoped_project` when `project_id` is provided
- its JSON contract is a top-level `items` array; each entry is a named preset such as `ready`, `stale`, `blocked`, `overdue`, or `at_risk`
- compare queue counts by matching `queue_presets[].name` from dashboard with `items[].name` from standalone `queue presets`
- `goal_horizon_stats_population` is `all_non_archived_retained`
- `visible_goal_horizon_stats_population` is `visible_operator`
- `visible_goal_horizon_stats` gives the operator-visible horizon rollup so goal counts do not silently mix retained hidden history into the live dashboard view
- `/api/v1/observability/overview` now exposes `rollups.projects.population = "all_non_archived_retained"`
- the MCP `get_dashboard` tool reports the same retained-population basis in its text output; it is not the operator-filtered CLI dashboard projection
- `project show --format json` and `project summary --format json` now include `execution`, which exposes active-task counts and the current active task rows directly instead of only a single `focus_task`
- `config set` persists to the resolved env file for the current execution context; if `PMS_ENV_FILE` is set, the command output names that target path explicitly
- `config show` now exposes that same resolved env file path under `paths.env_file` in JSON and prints it in text output
- `runtime prefer-server` uses that same resolved env target for persisted runtime bootstrap settings and returns the exact path as `config_path`
- `runtime prefer-server` also clears any stale `PMS_API_KEY` env override in the current process so file-backed local runtime auth can converge cleanly
- managed local runtime bootstrap now inherits the resolved `data_dir`, `database_path`, and `log_dir` for the current workspace instead of assuming `data_dir/pms.db`
- explicit `serve` / `runtime prefer-server` host+port requests now replace the current active local server for the same `PMS_DATA_DIR` instead of silently reusing an old port; PMS still keeps exactly one active local server per workspace
- `runtime status --format json` now also surfaces `unmanaged_local_processes` for workspace-local PMS server leftovers that are not tracked as managed runtime slots
- `runtime cleanup --include-unmanaged-local --format json` can stop those leftover workspace-local PMS server processes explicitly
- `runtime cleanup --include-unmanaged-local --unmanaged-port <port>` or `--unmanaged-pid <pid>` can target specific leaked local PMS server processes instead of broad cleanup
- `runtime cleanup` now preserves the configured preferred managed local server by default; use `--stop-all-managed` if you really want to tear down every tracked managed server
- `runtime cleanup --format json` now also surfaces `failed_managed` when a tracked managed local PMS server could not be stopped; PMS preserves pid/runtime state in that case instead of falsely claiming the server was cleaned up
- when multiple healthy managed local servers are tracked, runtime coordination now prefers the configured `server_base_url` instead of arbitrarily picking the first healthy port

Most list/detail commands support `--format table|json|csv` (or `text|json|csv` for
single-entity views), so you can script exports without extra tooling.
Machine-readable JSON list/detail surfaces are emitted as raw JSON, not Rich-rendered text, so
long names remain parseable with `jq`/`json.loads`.
Progress readbacks should follow latest-update truth as well:

- if a newer progress update revises a task from a higher estimate to a lower one,
  `task show`, `project show`, and `project summary` should all report the newer value

See [`docs/CLI_EXPORTS.md`](CLI_EXPORTS.md) for a full command matrix.

### Progress

```python
await client.update_progress(task_id, percent_complete, status_message, updated_by)
await client.get_progress_timeline(task_id)
```

### Workflows

```python
await client.list_workflows()
await client.assign_workflow(task_id, workflow_name, initial_state)
await client.get_workflow_timeline("task", task_id)
await client.get_status_timeline("task", task_id)
```

### Health

```python
health = await client.health_check()
print(health['status'])  # "healthy" or "degraded"
```

---

## Error Handling

```python
import httpx

try:
    task = await client.create_task(...)
except httpx.HTTPStatusError as e:
    if e.response.status_code == 404:
        print("Not found")
    elif e.response.status_code == 409:
        print("Conflict (already checked out)")
    elif e.response.status_code == 423:
        print("Locked (dependencies not met)")
```

---

## Configuration

```python
# Custom server URL
client = PMSClient(base_url="https://pms.company.com")

# With API key
client = PMSClient(
    base_url="https://pms.company.com",
    api_key="your-api-key",
)
```

---

## Transactional Write Pattern For Contributors

This client guide is primarily about public interfaces, but PMS extension work
also needs one stable write rule:

- one aggregate write can use a self-transactional public repository method
- one logical mutation spanning multiple authoritative writes should own one
  outer service transaction
- internal repository `_..._in_transaction()` helpers are only for callers that
  already own that outer transaction; PMS now guards that contract at runtime
- read-only metrics on `get`/`list`/`search` flows are observational and are
  not part of the authoritative transactional boundary
  - if those observational metrics fail late, PMS should still return the
    underlying read result instead of surfacing a telemetry-only failure
- CLI wrappers and orchestration runners follow the same rule for post-result
  telemetry: once the authoritative write or returned result already exists, a
  late metric-storage failure should be logged instead of replacing that result

Good pattern:

```python
async def restore_key(self, key_id: str) -> APIKey | None:
    async with self.api_key_repo.db.transaction():
        restored = await self.api_key_repo.restore(key_id)
        if restored is None:
            return None
        await self.audit_repo.record_reactivation_in_transaction(restored.id)
        await self.metrics.flush()
    return restored
```

Bad pattern:

```python
restored = await self.api_key_repo.restore(key_id)
await self.audit_repo.record_reactivation(restored.id)
await self.metrics.flush()
```

The bad pattern is wrong because a later failure can leave the restored row
committed without the follow-up state that makes the logical mutation complete.

If a workflow also touches files or subprocesses, commit authoritative database
state first and run destructive cleanup after commit so rollback cannot leave
PMS claiming work that an external side effect already removed.

---

## Examples

See `pms/client/http_client.py` for complete client implementation.

---

**Status**: Client library ready for use
Interactive wizard note:

- Interactive setup flows such as `loop setup` intentionally use in-place retry prompts for bad transient input, for example invalid dependency task numbers. That is a different contract from batch/json commands, which should fail nonzero with machine-readable errors instead of retrying.
- Interactive chooser flows such as `task show --pick` follow the same pattern: invalid numeric selections stay inside the chooser until the operator enters a valid row number.
- The same retry-in-place chooser contract applies to strategic selectors too, for example `goal summary --pick` and `plan show --pick`.
- That same chooser contract also applies inside goal hierarchies, including `objective show --pick` and `keyresult show --pick`.
