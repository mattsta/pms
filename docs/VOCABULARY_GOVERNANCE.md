# Vocabulary Governance

PMS does not treat every text field the same.

Some text values are true closed vocabularies and should be enforced directly in
the database. Some are registry-backed and should stay extensible through
explicit catalogs. Others are intentionally open because they model user or
plugin-defined semantics.

This document is the forward contract for deciding which is which.

## Why This Exists

Without a governance rule, text fields drift into three bad states:

- a closed enum exists in code but the database still accepts anything
- a field is actually extension-facing, but someone freezes it by accident
- machine clients cannot tell whether a value should be normalized, looked up,
  or treated as free-form input

The goal is to keep PMS well-encapsulated:

- closed vocabularies are enforced natively
- extensible vocabularies have an explicit authority source
- intentionally open fields are documented as open
- generated contract docs preserve closed literal domains instead of flattening
  them to generic `string` or `unknown`
- generated contract docs expand referenced schemas transitively so enum-backed
  field types also show up as first-class schema entries with explicit allowed
  values

## Current Classes

### 1. Closed Vocabularies Enforced In SQLite

These already have native schema checks and should remain DB-authoritative:

- `actors.kind`
- `actors.status`
- `actor_memberships.role`
- `projects.status`
- `milestones.status`
- `tasks.status`
- `tasks.priority`
- `task_dependencies.dependency_type`
- `organizations.status`
- `teams.status`
- `portfolios.status`
- `programs.status`
- `products.status`
- `goals.status`
- `goals.horizon`
- `objectives.status`
- `key_results.status`
- `plans.status`
- `plans.format`
- `remote_hosts.host_type`
- `sync_configs.sync_mode`
- `sync_history.direction`
- `sync_history.status`
- `test_servers.state`
- `test_run_retention_policies.scope_type`
- `saved_searches.sort_dir`

### 2. Closed Vocabularies Enforced By Code And Now Hardened In Schema

These behave like closed sets in the active interfaces and are safe to enforce
at the DB layer:

- `automation_rules.action_type`
  - `add_comment`, `create_task`, `update_task_status`, `set_custom_field_value`
- `automation_rule_runs.status`
  - `running`, `skipped`, `dry_run`, `success`, `failed`
- queue preset `population`
  - `visible_operator`, `scoped_project`
- `plan_test_jobs.mode`
  - `local`, `aws`
- rollup and snapshot `risk_level`
  - `low`, `medium`, `high`
- `custom_field_definitions.field_type`
  - `text`, `number`, `boolean`, `date`, `datetime`, `enum`, `json`, `url`
- `documents.doc_type`
  - `readme`, `api_doc`, `changelog`, `architecture`, `contributing`, `license`, `custom`
- test-run retention `sorted_by`
  - `largest`, `recent`
- `work_snapshot_reviews.scope_type`
  - `organization`, `portfolio`, `program`, `project`
- `saved_searches.scope_type`
  - `global`, `organization`, `program`, `project`

Generated contract docs should also preserve those closed sets directly. For
example, `plan_test_jobs.mode` should render as `local | aws` in generated API
contract references, not as a generic string. Referenced enum schemas like
`TaskStatus`, `ProjectStatus`, `GoalHorizon`, and `PlanFormat` should also be
present in generated contract docs with explicit allowed values.

### 3. Registry-Backed Or Catalog-Backed Vocabularies

These should not be frozen with ad hoc string checks because their authority
belongs in first-class tables or registries:

- workflow state names
  - authority: `workflow_states`
- workflow transition edges
  - authority: `workflow_transitions`
- label names and categories
  - authority: `labels`, `label_categories`
- actor handles and aliases
  - authority: `actors`, `actor_aliases`
- extension-facing `entity_type` surfaces
  - authority: PMS namespace registry as the canonical type catalog, plus
    explicit DB-backed extras when the interface accepts a real stored entity
    that is not namespace-generated today
  - current canonical aliasing:
    - `org` -> `organization`
    - `keyresult` -> `key_result`
    - `key-results` -> `key_result`

Namespace-backed `entity_type` families participate in the namespace registry
and `namespace generate-id`, but that is still separate from the runtime row-ID
style for most public entities today.

Current DB-backed non-namespace extras are:

- `actor`
- `automation_rule`
- `product`

Current namespace-backed extras beyond the original registry core now include:

- `api_key`

Current namespace-backed `entity_type` surfaces:

- `comments.entity_type`
- `entity_watchers.entity_type`
- `label_assignments.entity_type`
- `label_gate_rules.entity_type`
- `custom_field_definitions.entity_type`
- `custom_field_values.entity_type`
- transition timeline path/query surfaces
- workflow-alignment surfaces

When a field belongs in this class, the correct move is:

1. define the authority table or registry
2. validate against it in services and APIs
3. add DB FKs where the authority is row-backed and local to the database

Forward rule for namespace coverage:

- only register a built-in namespace when the entity family truly participates
  in the namespace/type-catalog contract
- do not register UUID-native entities in the namespace registry just to make
  capability counts look broader
- if a UUID-native entity remains a valid public `entity_type`, classify it as
  a DB-backed extra explicitly and test that distinction
- treat runtime row-ID style as a separate contract; namespace registration
  alone does not imply prefix-native runtime IDs

## Intentionally Open Fields

These are still open on purpose and should not receive enum checks until PMS has
an explicit catalog or public compatibility contract for them:

- `products.product_type`
  - today this is descriptive categorization, not a frozen product taxonomy
  - covered by fresh-schema and live API regression tests so custom values stay
    accepted on purpose
- `workflow_definitions.entity_type`
  - this is extension-facing and may grow with new workflow-governed entities
  - covered by fresh-schema regression tests; it remains open until workflow
    entity families have a first-class registry contract
- `task_evidence.evidence_type`
- `session_messages.role`
  - preferred built-ins today are `system`, `user`, `assistant`, and `tool`
  - custom roles such as `planner`, `reviewer`, or plugin-defined transcript
    participants remain valid and are intentionally not normalized away
  - covered by repository round-trip regression and fresh-schema bootstrap proof
- `activity_log.entity_type`
  - this is an intentionally open coarse-audit family, not a closed entity
    registry mirror
  - future writers may emit plugin-defined families or derived audit families
    such as `task_status` and `task_workflow`
- `activity_log.action`
  - this is an intentionally open coarse-audit action label
  - do not freeze it until PMS has real multi-producer activity-log writers and
    a stable action catalog worth enforcing
- `network_environment_servers.server_role`
- `automation_rules.event_pattern`
  - intentionally open wildcard/event selector, not a closed enum

For these fields, PMS should prefer:

- service-layer validation
- clearer documentation
- future registry introduction where the value set stops being genuinely open
- regression tests that prove fresh schema bootstrap still accepts representative
  custom values instead of silently freezing the field into an enum later

Current decision for transcript/activity vocabulary:

- `session_messages.role`
  - contract mode: open with recommended built-ins
  - forward rule: document and preserve preferred roles, but keep custom roles
    valid for agent, planner, reviewer, and plugin transcripts
- `activity_log.entity_type`
  - contract mode: open coarse-audit family
  - forward rule: do not add enum checks until activity logging has a real
    producer catalog or registry-backed authority source
- `activity_log.action`
  - contract mode: open coarse-audit verb/event label
  - forward rule: do not freeze action names while the audit surface is still
    sparse and future integrations may introduce valid new verbs

## Explicit Exceptions

Some fields look similar but are intentionally narrower today:

- `evidence_gate_rules.entity_type`
  - currently task-only
  - reason: evidence-gate enforcement is task-native because the active proof
    model and transition enforcement path operate on task evidence
  - forward rule: do not widen this until non-task evidence authority exists as
    a first-class relational model

## Forward Rule

Before adding a new DB `CHECK` on a text field, answer these questions:

1. Is the value set already closed in the CLI/API/service layer?
2. Is there a first-class authority source for the vocabulary?
3. Would freezing this field block valid extensions or plugin-defined behavior?
4. Can the DB error be translated into a useful operator/machine message?

If the answer pattern is:

- closed + stable + already normalized: add the DB check
- dynamic but authoritative through rows: add or use a registry table
- open-ended or extension-facing: document it and leave it open for now

## PMS Managing PMS

This governance work is tracked inside PMS itself:

- `dd88b583-b72b-4cea-91b3-9ac8d21fbd91`
  - completed monetary precision contract hardening
- `939d7d38-e321-4218-91a5-87b7260e738f`
  - active vocabulary-governance umbrella task
- `8bf4656d-5fb5-4647-84e9-4967ee3e091b`
  - inventory open vocabulary fields
- `0998bf77-f1a9-4031-8b09-03c59895ae1a`
  - promote stable vocabularies into native registries or DB constraints
- `13f2ffa8-8aac-4c46-b0f2-d58d84e50ab5`
  - document vocabulary governance and add regression coverage
- `d7b36f6f-e6df-40c4-af65-5b7fc1347e2d`
  - harden automation-rule `action_type` as a DB-authoritative closed vocabulary
- `581dcc59-d127-4e11-b8c2-a68326e987eb`
  - document and regression-test intentionally open vocabulary surfaces
- `6b718c2e-5da1-419c-85fd-5f38326148ea`
  - clarify and regression-test extension-facing open vocabularies
- `fc973530-803f-4a84-b9ec-7c8456edc343`
  - align namespace-registry coverage with DB-backed `entity_type` extras
- `4b0c2bac-6568-4f78-8a9f-bc67c4c0f511`
  - tighten remaining closed response-string vocabularies in API models

That is intentional. PMS should be able to describe not only the platform state,
but also the governance rules used to evolve the platform itself.
