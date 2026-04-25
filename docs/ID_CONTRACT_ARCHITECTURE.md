# ID Contract Architecture

PMS currently has two related but different ID layers:

1. type-catalog / typed-ID utilities
   - driven by `pms.core.namespace` and `pms.core.ids`
   - supports prefixed IDs such as `proj_<uuid>` or `wf_<uuid>`
   - useful for extension registration, capability discovery, and internal typed
     ID helpers
2. runtime row IDs for stored entities
   - the IDs that actually appear in live project/task/goal/product/actor rows
   - currently UUID-native for most public first-class entities

Those layers are not yet fully converged. This document is the forward contract
for treating that fact explicitly instead of letting interfaces imply the wrong
thing.

## Current Rule

For machine clients and operator tooling:

- treat live entity IDs as opaque canonical IDs
- do not infer row-ID format from `entity_type`
- do not infer row-ID format from namespace registration alone
- unless PMS explicitly documents a family as `prefix_native`, expect live
  stored IDs to be `uuid_native`

## Current Public Runtime Styles

These are the public stored entity families currently accepted across primary
CLI/API/MCP surfaces and their runtime ID styles.

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

Current internal/supporting prefix-native families used in active codepaths:

- `event`
- `metric`

## Namespace Coverage Is Not Runtime ID Coverage

Today:

- some namespace-registered families are still UUID-native at runtime
  - example: `project`, `task`, `goal`
- some valid public entity families are not namespace-registered
  - example: `actor`, `product`, `automation_rule`
- one public family currently participates in both layers cleanly
  - `api_key`

That means these questions are separate:

1. is this a valid public `entity_type`?
2. does this family participate in the namespace/type-catalog registry?
3. what is the runtime row-ID style for this family?

PMS must answer all three explicitly instead of treating one answer as proof of
the others.

Machine-readable namespace schema now exposes that split directly:

- `namespace_generated_id_format`
- `namespace_generated_id_kind`
- `runtime_row_id_contract_scope`
- `runtime_row_id_style`

That prevents the old mistake of reading a namespace utility prefix as proof of
the public runtime row-ID contract.

Interpret the runtime fields together:

- `runtime_row_id_contract_scope = public_stored_entity_family`
  - the namespace family participates in the public runtime row-ID contract
- `runtime_row_id_contract_scope = internal_or_non_public_namespace`
  - the namespace exists in the type catalog, but its public runtime row-ID
    contract is intentionally out of scope
- `runtime_row_id_style = null`
  - only means “no public runtime row-ID style applies here,” not “unknown”

## Documentation Rule

When writing CLI/API/MCP docs:

- prefer `<task-id>`, `<project-id>`, `<goal-id>`, etc. for generic examples
- only use explicit prefix-native examples like `api_key_...` when the runtime
  ID contract for that family is actually prefix-native
- if a document is discussing namespace utilities specifically, prefixed
  examples are correct there

## Interface Rule

When implementing services, validators, or generated clients:

- do not parse public runtime IDs by prefix unless the contract for that family
  explicitly says the runtime IDs are prefix-native
- treat `_id` fields as opaque canonical identifiers
- if an entity family is UUID-native, suggestion/error handling should still
  resolve and display the canonical stored ID without trying to coerce a
  prefixed shape

## Promotion Rule

Do not promote a UUID-native public entity family into prefix-native runtime IDs
by accident.

Promotion requires a deliberate plan that covers:

1. model/repository creation paths
2. API/CLI/MCP request and response examples
3. docs and generated references
4. tests and fixture data
5. compatibility stance for already-created data

Until that plan exists, keep the family explicitly classified as `uuid_native`.

## PMS Managing PMS

This contract is tracked in PMS itself:

- `72aace5c-5193-4480-9d59-0214ba44df69`
  - define typed-ID promotion policy for UUID-native first-class entities
- `fc973530-803f-4a84-b9ec-7c8456edc343`
  - completed namespace coverage vs DB-backed `entity_type` alignment
- `0998bf77-f1a9-4031-8b09-03c59895ae1a`
  - stable vocabulary/native registry umbrella

That is intentional. PMS should not only store work; it should make the
framework’s own interface contracts inspectable and governable from inside the
same system.
