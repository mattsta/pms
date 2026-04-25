# Actor Identity and Persona Graph Architecture

## Purpose

PMS uses `Actor` as the canonical identity node across strategy, execution,
ownership, memberships, and runtime checkout.

This document describes the active forward architecture for identity in PMS.
It is not an upgrade note and it is not a compatibility guide.

## Why `Actor`

A single `Actor` model keeps identity coherent across:

- assignment
- ownership
- memberships
- persona delegation
- team rollups
- runtime execution leases
- graph traversal
- workload math and review surfaces

`Actor` is broader and more correct than a narrow `user` concept because PMS
needs to represent:

- humans
- personas
- teams
- service accounts
- runtime agents

## Core Model

### Canonical Node: `Actor`

Required fields:

- `id`
- `kind`
- `name`
- `handle`
- `status`
- `metadata`
- `created_at`
- `updated_at`

Common kinds:

- `human`
- `persona`
- `team`
- `service_account`
- `runtime_agent`

### Supporting Nodes

PMS also uses:

- `ActorAlias`
- `ActorMembership`

These support:

- handle aliases
- persona-to-human representation
- team membership
- inherited workload views
- actor graph traversal

## Public Contract

The public contract is actor-native.

### Write surfaces

Public write requests use semantic role keys:

- `owner`
- `members`
- `assignee`
- `actor` for checkout flows where an explicit actor is supplied

CLI mutation flags stay concise too:

- `--owner`
- `--member`
- `--assigned-to`

Those inputs still accept actor handles or IDs, but the public contract names
the role instead of repeating the actor type in every field.

### Read surfaces

Public read payloads also use semantic role keys:

- `owner`
- `members`
- `assignee`

Actor payloads use:

- `ref`
- `id`
- `actor`
- `links`

Design rule:

- role keys describe meaning
- actor payloads describe identity
- `Actor` is already the identity model, so repeating `actor` in every role key
  is redundant and makes the surface noisier for both humans and machines

## Current Implemented Surfaces

### CLI

Available actor commands include:

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

Actor-aware execution and review surfaces include:

- `task show --format json`
- `task ready --format json`
- `task stale --format json`
- `task blocked --format json`
- `task duplicates --format json`
- `queue run --format json`
- `queue presets --view detail --format json`
- `dashboard --format json`
- `start --format json`
- `work daily --format json`
- `work review --format json`
- `work graph-report --format json`

### HTTP API

Available actor routes include:

- `POST /api/v1/actors`
- `GET /api/v1/actors`
- `GET /api/v1/actors/{actor}`
- `POST /api/v1/actors/{actor}/aliases`
- `POST /api/v1/actors/{actor}/memberships`

Actor-aware surfaces include:

- task detail and task search
- queue definitions and queue runs
- organization, team, portfolio, and program reads
- product, goal, objective, and key-result reads
- project, plan, dashboard, and review/control surfaces

### MCP

Actor graph MCP tools include:

- `create_actor`
- `list_actors`
- `get_actor`
- `add_actor_alias`
- `add_actor_membership`

## Workload Semantics

`actor show --format json` exposes workload populations split into:

- `direct`
- `effective`
- `inherited_only`

Interpretation:

- `direct`: work assigned directly to the actor
- `effective`: direct work plus inherited persona/team membership scope
- `inherited_only`: effective minus direct

Actor workload reads also expose:

- owned entity counts and items
- per-project workload rollups
- checkout lease rollups
- `graph_navigation`

## Graph Traversal

Identity is part of the main work graph.

Important traversal patterns:

- actor -> assigned tasks
- actor -> owned goals/projects/products/queues
- task -> assignee actor
- task -> checkout actor
- organization/team -> member actors
- goal/objective/key-result -> owner actor
- queue -> owner actor
- project/dashboard/start -> actor rollups

Primary graph/reporting surfaces expose:

- `links`
- `next_steps`
- `graph_navigation`
- `actor_rollups`
- `focus_task`

## Runtime and Checkout Identity

Checkout identity is actor-aware.

Public checkout reads expose:

- checkout metadata with resolved actor identity
- lease timestamps
- current agent session id
- actor links back into the identity graph

This keeps execution attribution aligned with the same actor model used for
assignment and ownership.

## Storage Notes

The stable schema persists canonical actor ids for internal consistency and fast
joins.

That storage detail is not the public interface. Public consumers should depend
on actor-native request and response fields.

## Design Rules

1. Identity is graph-native, not an annotation layer.
2. Public identity inputs should be actor refs.
3. Public identity outputs should be actor payloads.
4. Workload math must remain explicit about direct vs inherited populations.
5. Review, queue, dashboard, and graph-report surfaces must preserve actor
   navigation.
6. Runtime checkout identity must use the same actor model as ownership and
   assignment.

## Related Docs

- [`README.md`](../README.md)
- [`docs/MACHINE_INTERFACE_GUIDE.md`](MACHINE_INTERFACE_GUIDE.md)
- [`docs/CLIENT_GUIDE.md`](CLIENT_GUIDE.md)
- [`docs/WEB_API.md`](WEB_API.md)
- [`docs/ARCHITECTURE.md`](ARCHITECTURE.md)
