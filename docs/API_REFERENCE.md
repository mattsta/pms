# PMS Web API Reference

**Base URL**: `http://127.0.0.1:27541` (default)
**API Version**: v1
**Format**: JSON (REST)

---

## Quick Start

### Start Server

```bash
# Development (default local bind http://127.0.0.1:27541)
uv run pms serve

# PostgreSQL-backed local server
uv sync --extra postgres
PMS_DATABASE_PATH=postgresql://user:pass@localhost/pms \
uv run pms serve --host 0.0.0.0 --port 27541

# With auto-reload
uv run pms serve --reload
```

Examples below assume the default local server URL
`http://127.0.0.1:27541`. If your deployment uses a different public URL,
substitute that value or set `PMS_SERVER_BASE_URL` accordingly for CLI and
client flows.

### Access API Docs

**Interactive Swagger UI**: http://127.0.0.1:27541/docs
**ReDoc**: http://127.0.0.1:27541/redoc
**OpenAPI Schema**: http://127.0.0.1:27541/openapi.json

---

## Authentication

All endpoints require an API key in the `X-API-Key` header, except
`GET /api/v1/auth/scopes` which is public.

Bootstrap the first admin key locally:

```bash
uv run pms auth init --show-key
```

Then include it on requests:

```http
X-API-Key: <your-api-key>
```

Admin key management is available under `/api/v1/auth/*` (see below).

Common scopes you will use:

- `orgs:read`, `orgs:write`
- `teams:read`, `teams:write`
- `portfolios:read`, `portfolios:write`
- `programs:read`, `programs:write`
- `labels:read`, `labels:write`

---

Typed request/response contracts for every endpoint are in:
`docs/API_RESPONSE_CONTRACTS.md`.

---

## Pagination Discoverability Wrapper

Most list/search endpoints return the standard page fields:

- `items`, `total_count`, `offset`, `limit`
- `links` (`self`, `next`, `guide`, and endpoint-specific related links when relevant)
- `next_steps` (practical follow-up calls)
- `params` (echo of active query parameters)

This applies to core collections such as organizations, teams, portfolios,
programs, products, projects, goals, objectives, key results, plans, queues,
and task query endpoints.

---

## Endpoints

### Discoverability API

#### Discoverability Graph

```http
GET /api/v1/discoverability/graph?include_entry_points=true&include_observability=true&include_scenarios=true&max_next_steps=8&path_contains=plans
X-API-Key: <your-api-key>
```

Returns a structured graph of practical API entry points and continuation edges.

**Response highlights:**

- `nodes` with `category`, `why`, and bounded `what_next` actions
- `edges` connecting each entry point to concrete follow-up operations
- `scenarios` for real-world start->go flows (`drop-in`, `handoff`, `incident`, `observe`)
- `links`, `next_steps`, `params` for iterative graph exploration

#### Observability Overview

```http
GET /api/v1/observability/overview?include_rollups=true&include_queues=true&include_lineage=true&include_retention=true&include_event_timeline=true&queue_limit=5&lineage_limit=20&retention_limit=10&timeline_days=14
X-API-Key: <your-api-key>
```

Returns a unified live-state overview for operators and automation.

**Response highlights:**

- `health` with computed status and blocked/overdue/completion ratios
- `attention_summary` with a stable “what needs attention now” export contract
- `attention_items` with concrete issue records, API paths, and CLI continuation commands
- `top_risks_now`, `stalled_flows`, and `needs_review` to separate immediate operator work by intent
- `recommended_actions` with the next best API/CLI jump instead of generic follow-up guessing
- `rollups` across project/org/portfolio/program scopes (when allowed by key scopes)
- `queues` with ready/stale/blocked/overdue/at-risk counts + sample tasks
- `lineage` and `retention` totals for evidence/test-output health
- `event_timeline` with per-day event counts for recent activity windows
- `permissions` + `warnings` to show exactly which sections were omitted by scope
- `links`, `next_steps`, `params` for direct continuation into detailed dashboards

**Example response** (200):

```json
{
  "generated_at": "2026-04-03T23:42:00+00:00",
  "health": {
    "status": "attention",
    "blocked_task_ratio": 0.25,
    "overdue_task_ratio": 0.08,
    "completion_ratio": 0.54,
    "retention_alert_count": 1
  },
  "attention_summary": {
    "overall_status": "attention",
    "highest_severity": "high",
    "total_attention_items": 4,
    "top_risk_count": 2,
    "stalled_flow_count": 1,
    "needs_review_count": 1
  },
  "attention_items": [
    {
      "id": "retention-alerts",
      "category": "retention",
      "severity": "high",
      "title": "Retention alerts require cleanup",
      "summary": "1 retention alert(s) are active across 18 stored run(s).",
      "why": "Stored logs and artifacts are above one or more retention guardrails.",
      "api_path": "/api/v1/test-runs/retention",
      "cli_command": "uv run pms test-run retention --format json"
    }
  ],
  "top_risks_now": [
    {
      "id": "retention-alerts",
      "category": "retention",
      "severity": "high",
      "title": "Retention alerts require cleanup",
      "summary": "1 retention alert(s) are active across 18 stored run(s).",
      "why": "Stored logs and artifacts are above one or more retention guardrails.",
      "api_path": "/api/v1/test-runs/retention",
      "cli_command": "uv run pms test-run retention --format json"
    }
  ],
  "stalled_flows": [
    {
      "id": "blocked-work",
      "category": "execution",
      "severity": "high",
      "title": "Blocked work needs operator attention",
      "summary": "3 blocked task(s) across 12 total task(s).",
      "why": "Blocked tasks slow delivery and usually indicate missing decisions or dependencies.",
      "api_path": "/api/v1/queues/presets",
      "cli_command": "uv run pms queue preset list --format json"
    }
  ],
  "needs_review": [
    {
      "id": "failed-test-runs",
      "category": "quality",
      "severity": "medium",
      "title": "Failed test runs need investigation",
      "summary": "2 failed test run(s) across 8 total lineage-linked run(s).",
      "why": "Recent delivery evidence includes failing validation that may block release or merge.",
      "api_path": "/api/v1/plans/lineage",
      "cli_command": "uv run pms plan lineage --format json"
    }
  ],
  "recommended_actions": [
    {
      "id": "risk-retention-alerts",
      "title": "Reduce the highest live risk",
      "why": "Stored logs and artifacts are above one or more retention guardrails.",
      "api_call": "GET /api/v1/test-runs/retention",
      "cli_command": "uv run pms test-run retention --format json"
    }
  ],
  "permissions": {
    "rollups": true,
    "queues": true,
    "lineage": true,
    "retention": true,
    "event_timeline": true
  },
  "warnings": [],
  "rollups": {
    "projects": {
      "total_projects": 4,
      "total_tasks": 12,
      "completed_tasks": 6,
      "blocked_tasks": 3,
      "overdue_tasks": 1
    }
  },
  "queues": [],
  "lineage": {
    "total_plans": 3,
    "total_tasks": 9,
    "total_test_runs": 8,
    "failed_test_runs": 2,
    "total_evidence": 11,
    "total_code_evidence": 4
  },
  "retention": {
    "total_runs": 18,
    "total_bytes": 40960,
    "total_log_bytes_combined": 20480,
    "total_artifact_bytes": 20480,
    "alert_count": 1,
    "policy_count": 2
  },
  "event_timeline": {
    "window_days": 14,
    "points": []
  },
  "links": {
    "self": "/api/v1/observability/overview?include_rollups=true&include_queues=true&include_lineage=true&include_retention=true&include_event_timeline=true&queue_limit=5&lineage_limit=20&retention_limit=10&timeline_days=14",
    "root": "/",
    "dashboard": "/dashboard",
    "api_dashboard": "/api/v1/dashboard",
    "discoverability_graph": "/api/v1/discoverability/graph",
    "organizations_dashboard": "/api/v1/organizations/dashboard",
    "plans_lineage": "/api/v1/plans/lineage",
    "test_run_retention": "/api/v1/test-runs/retention"
  },
  "next_steps": [
    "GET /api/v1/test-runs/retention",
    "GET /api/v1/queues/presets",
    "GET /api/v1/plans/lineage"
  ],
  "params": {
    "include_rollups": true,
    "include_queues": true,
    "include_lineage": true,
    "include_retention": true,
    "include_event_timeline": true,
    "queue_limit": 5,
    "lineage_limit": 20,
    "retention_limit": 10,
    "timeline_days": 14
  }
}
```

---

### Actors API

#### Create Actor

```http
POST /api/v1/actors
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "name": "Security Persona",
  "kind": "persona",
  "handle": "security-persona",
  "description": "Shared security review persona for platform work",
  "tags": ["security", "persona"],
  "metadata": {
    "tier": "shared",
    "domain": "platform"
  }
}
```

#### List Actors

```http
GET /api/v1/actors?kind=persona&status=active&limit=50&offset=0
X-API-Key: <your-api-key>
```

**Response highlights:**

- paginated wrapper with `items`, `links`, `next_steps`, and `params`
- use `links.next` for pagination and `GET /api/v1/actors/{actor}` for graph expansion

#### Get Actor

```http
GET /api/v1/actors/{actor}?include_inherited=true&task_limit=25
X-API-Key: <your-api-key>
```

**Response highlights:**

- `actor`, `aliases`, and `memberships` expose the canonical identity graph
- `workload` separates assignment and checkout views
- `ownership` and `project_workloads` surface actor accountability across strategic and delivery entities
- `graph_navigation`, `links`, and `next_steps` provide traversable follow-up commands/endpoints

#### Add Actor Alias

```http
POST /api/v1/actors/{actor}/aliases
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "alias": "security"
}
```

#### Add Actor Membership

```http
POST /api/v1/actors/{actor}/memberships
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "member": "alice-example",
  "role": "member"
}
```

---

### Organizations API

#### Create Organization

```http
POST /api/v1/organizations
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "name": "Acme Org",
  "description": "Primary org",
  "owner": "owner@example.com",
  "members": ["owner@example.com"],
  "tags": ["platform"]
}
```

#### List Organizations

```http
GET /api/v1/organizations?status=active&limit=50&offset=0
X-API-Key: <your-api-key>
```

#### Organization Dashboard

```http
GET /api/v1/organizations/dashboard?status=active&limit=50&offset=0&include_digest=true&include_next_actions=true&include_evidence=true&include_retention=true&next_limit=3
X-API-Key: <your-api-key>
```

**Response highlights:**

- `links`, `next_steps`, `params` for scoped dashboard continuation
- `links.self` reflects the exact query used for this dashboard view

#### Get Organization

```http
GET /api/v1/organizations/{org_id}
X-API-Key: <your-api-key>
```

#### Update Organization

```http
PATCH /api/v1/organizations/{org_id}
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "name": "Acme Org",
  "status": "archived",
  "owner": "owner@example.com",
  "members": ["owner@example.com", "ops@example.com"],
  "tags": ["platform", "delivery"]
}
```

#### Organization Summary

```http
GET /api/v1/organizations/{org_id}/summary
X-API-Key: <your-api-key>
```

**Response highlights:**

- `links`, `next_steps`, `params` for summary-to-dashboard continuation
- `links.work_daily` for scoped daily rollup review

---

### Teams API

#### Create Team

```http
POST /api/v1/teams
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "name": "Core Team",
  "org_id": "<org-id>",
  "owner": "lead@example.com",
  "members": ["lead@example.com"]
}
```

#### List Teams

```http
GET /api/v1/teams?org_id=<org-id>&status=active&limit=50&offset=0
X-API-Key: <your-api-key>
```

#### Get Team

```http
GET /api/v1/teams/{team_id}
X-API-Key: <your-api-key>
```

#### Update Team

```http
PATCH /api/v1/teams/{team_id}
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "status": "archived",
  "owner": "lead@example.com",
  "members": ["lead@example.com", "dev@example.com"]
}
```

---

### Portfolios API

#### Create Portfolio

```http
POST /api/v1/portfolios
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "name": "Platform Portfolio",
  "org_id": "<org-id>",
  "project_ids": ["<project-id>"],
  "goal_ids": ["<goal-id>"],
  "objective_ids": ["<objective-id>"]
}
```

Notes:

- `project_ids` assigns projects into the portfolio through project foreign-key
  links.
- `goal_ids` and `objective_ids` create direct portfolio-to-goal and
  portfolio-to-objective links backed by native edge tables.
- `GET /api/v1/portfolios/{portfolio_id}` and portfolio summary/dashboard
  surfaces return:
  - `goal_ids` / `objective_ids` as those direct strategic links
  - `effective_goal_ids` / `effective_objective_ids` as the hydrated scope that
    combines direct links with project-derived scope

#### List Portfolios

```http
GET /api/v1/portfolios?org_id=<org-id>&status=active&limit=50&offset=0
X-API-Key: <your-api-key>
```

#### Portfolio Dashboard

```http
GET /api/v1/portfolios/dashboard?org_id=<org-id>&status=active&limit=50&offset=0&include_digest=true&include_next_actions=true&include_evidence=true&include_retention=true&next_limit=3
X-API-Key: <your-api-key>
```

**Response highlights:**

- `links`, `next_steps`, `params` for scoped dashboard continuation
- `links.self` reflects the exact query used for this dashboard view

#### Get Portfolio

```http
GET /api/v1/portfolios/{portfolio_id}
X-API-Key: <your-api-key>
```

**Response highlights:**

- `goal_ids` / `objective_ids`: direct strategic links
- `effective_goal_ids` / `effective_objective_ids`: hydrated scope readbacks
- `project_ids`: effective project scope

#### Update Portfolio

```http
PATCH /api/v1/portfolios/{portfolio_id}
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "status": "archived",
  "project_ids": ["<project-id>", "<project-id-2>"],
  "goal_ids": ["<goal-id>", "<goal-id-2>"],
  "objective_ids": ["<objective-id>", "<objective-id-2>"]
}
```

#### Portfolio Summary

```http
GET /api/v1/portfolios/{portfolio_id}/summary
X-API-Key: <your-api-key>
```

**Response highlights:**

- `links`, `next_steps`, `params` for summary-to-dashboard continuation
- `links.work_daily` for scoped daily rollup review

---

### Programs API

#### Create Program

```http
POST /api/v1/programs
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "name": "Delivery Program",
  "org_id": "<org-id>",
  "portfolio_id": "<portfolio-id>",
  "project_ids": ["<project-id>"],
  "goal_ids": ["<goal-id>"],
  "objective_ids": ["<objective-id>"]
}
```

Notes:

- `project_ids` assigns projects into the program through project foreign-key
  links.
- `goal_ids` and `objective_ids` create direct program-to-goal and
  program-to-objective links backed by native edge tables.
- `GET /api/v1/programs/{program_id}` and program summary/dashboard surfaces
  return:
  - `goal_ids` / `objective_ids` as those direct strategic links
  - `effective_goal_ids` / `effective_objective_ids` as the hydrated scope that
    combines direct links with project-derived scope

#### List Programs

```http
GET /api/v1/programs?portfolio_id=<portfolio-id>&status=active&limit=50&offset=0
X-API-Key: <your-api-key>
```

#### Program Dashboard

```http
GET /api/v1/programs/dashboard?portfolio_id=<portfolio-id>&status=active&limit=50&offset=0&include_digest=true&include_next_actions=true&include_evidence=true&include_retention=true&next_limit=3
X-API-Key: <your-api-key>
```

**Response highlights:**

- `links`, `next_steps`, `params` for scoped dashboard continuation
- `links.self` reflects the exact query used for this dashboard view

#### Get Program

```http
GET /api/v1/programs/{program_id}
X-API-Key: <your-api-key>
```

**Response highlights:**

- `goal_ids` / `objective_ids`: direct strategic links
- `effective_goal_ids` / `effective_objective_ids`: hydrated scope readbacks
- `project_ids`: effective project scope

#### Update Program

```http
PATCH /api/v1/programs/{program_id}
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "status": "archived",
  "project_ids": ["<project-id>", "<project-id-2>"],
  "goal_ids": ["<goal-id>", "<goal-id-2>"],
  "objective_ids": ["<objective-id>", "<objective-id-2>"]
}
```

#### Program Summary

```http
GET /api/v1/programs/{program_id}/summary
X-API-Key: <your-api-key>
```

**Response highlights:**

- `links`, `next_steps`, `params` for summary-to-dashboard continuation
- `links.work_daily` for scoped daily rollup review

---

### Work Snapshots API

#### Get Work Snapshot

```http
GET /api/v1/work-snapshots/{scope_type}/{scope_id}?task_limit=5&test_limit=5&include_history=true&history_limit=3
X-API-Key: <your-api-key>
```

Scopes:

- `scope_type` = `organization`, `portfolio`, `program`, or `project`

**Response highlights:**

- `review_history_preview`: latest review checkpoints for accumulated context
- `links`, `next_steps`, `params`: continuation metadata for immediate follow-up actions

#### Mark Snapshot Reviewed

```http
POST /api/v1/work-snapshots/{scope_type}/{scope_id}/review
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "reviewed_by": "alice@example.com",
  "note": "Weekly check-in",
  "metadata": {
    "session": "weekly-review"
  }
}
```

**Response highlights:**

- `links.snapshot` / `links.daily` for direct follow-up reads
- `next_steps` for immediate “observe what changed” flow

---

### Products API

#### Create Product

```http
POST /api/v1/products
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "name": "MyService",
  "description": "Core service",
  "vision": "Build the future",
  "repository_url": "https://github.com/org/repo",
  "owner": "alice@company.com",
  "product_type": "internal_platform"
}
```

`product_type` is intentionally open. Use a descriptive category that fits your
domain; PMS does not currently treat it as a closed enum.

**Response** (201 Created):

```json
{
  "id": "6c4c7184-b537-489a-a5c1-ecdc4c2f6935",
  "name": "MyService",
  "product_type": "internal_platform",
  "status": "active",
  "vision": "Build the future",
  "created_at": "2025-12-23T19:00:00Z"
}
```

#### List Products

```http
GET /api/v1/products?status=active&limit=50&offset=0
X-API-Key: <your-api-key>
```

#### Update Product

```http
PATCH /api/v1/products/{product_id}
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "name": "MyService",
  "description": "Updated description",
  "status": "active"
}
```

#### Get Product

```http
GET /api/v1/products/{product_id}
X-API-Key: <your-api-key>
```

#### Get Product Summary (with stats)

```http
GET /api/v1/products/{product_id}/summary
X-API-Key: <your-api-key>
```

**Response**:

```json
{
  "product": {...},
  "stats": {
    "total_projects": 5,
    "total_tasks": 42,
    "completed_tasks": 30,
    "total_complexity_points": 2100,
    "health_score": 85.5
  },
  "health_score": 85.5
}
```

#### Archive Product

```http
POST /api/v1/products/{product_id}/archive
X-API-Key: <your-api-key>
```

---

### Projects API

#### Create Project

```http
POST /api/v1/projects
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "name": "Q1 Platform",
  "description": "Quarterly initiatives",
  "tags": ["platform", "q1"]
}
```

#### List Projects

```http
GET /api/v1/projects?status=active&limit=50&offset=0
X-API-Key: <your-api-key>
```

#### Instance Project Dashboard

```http
GET /api/v1/dashboard
X-API-Key: <your-api-key>
```

**Response highlights:**

- `scope.population=all_non_archived_retained` for truthful instance-wide rollups
- `active_projects` and `recently_completed_projects` use the same lifecycle-aware
  project payload shape as project detail/summary surfaces
- `freshest_visible_activity` and `freshest_visible_transition` point at the
  freshest visible project across active + recent terminal work
- `completion_context` and `terminal_reason` explain the no-active-work case

#### Get Project

```http
GET /api/v1/projects/{project_id}
X-API-Key: <your-api-key>
```

#### Update Project

```http
PATCH /api/v1/projects/{project_id}
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "name": "Q1 Platform",
  "description": "Updated description",
  "status": "active",
  "tags": ["platform", "q1"]
}
```

---

### Goals API

#### Create Goal

```http
POST /api/v1/goals
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "name": "Launch V1",
  "description": "Ship core capabilities",
  "horizon": "short_term",
  "progress_percent": 10
}
```

#### List Goals

```http
GET /api/v1/goals?horizon=short_term&limit=50&offset=0
X-API-Key: <your-api-key>
```

Response highlights:

- each item keeps stored goal fields and adds execution-aware `effective_rollup`
- `last_activity_at` and `last_transition_at` are bubbled up from the linked
  goal/objective/key-result graph
- `terminal_reason` is surfaced directly on list items for terminal goal states

#### Update Goal

```http
PATCH /api/v1/goals/{goal_id}
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "progress_percent": 60,
  "status": "on_hold"
}
```

#### Goal Summary (rollup)

```http
GET /api/v1/goals/{goal_id}/summary
X-API-Key: <your-api-key>
```

Response highlights:

- `effective_rollup` and `effective_hierarchy` expose execution-aware goal state
- `terminal_reason` and `completion_context` are promoted to the top level for
  machine clients
- `last_activity_at` and `last_transition_at` expose the bubbled lifecycle
  timestamps for the full goal graph
- `links` and `next_steps` make the summary directly discoverable without
  reconstructing related routes

---

### Plans API

#### Create Plan

```http
POST /api/v1/plans
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "name": "Release Plan",
  "description": "Stages and checkpoints",
  "status": "draft",
  "format": "json",
  "content": {"stages": ["plan", "implement", "test"]},
  "project_id": "<project-id>"
}
```

#### List Plans

```http
GET /api/v1/plans?project_id=<project-id>&limit=50&offset=0
X-API-Key: <your-api-key>
```

#### Plan Lineage Dashboard

```http
GET /api/v1/plans/lineage?status=active&project_id=<project-id>&task_limit=5&test_limit=3
X-API-Key: <your-api-key>
```

Lineage responses include evidence rollups per plan (total evidence, type counts,
and latest `scm_*` reference) plus aggregate `total_evidence` and
`total_code_evidence` totals.

**Response highlights:**

- `links`, `next_steps`, `params` for lineage paging and follow-up execution
- `links.plan_template`, `links.plan_test_jobs_template`, `links.proof_bundle_template` for direct handoff from overview to action

#### Get Plan

```http
GET /api/v1/plans/{plan_id}
X-API-Key: <your-api-key>
```

#### Update Plan

```http
PATCH /api/v1/plans/{plan_id}
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "status": "active",
  "content": {"stages": ["plan", "ship"]}
}
```

#### Create Plan Test Job

```http
POST /api/v1/plans/{plan_id}/test-jobs
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "name": "Local smoke tests",
  "mode": "local",
  "project_path": ".",
  "test_command": "python -m pytest -q",
  "env_vars": [{"key": "PYTHONPATH", "value": "."}],
  "capture_logs": ["./logs/test.log"],
  "save_artifacts": ["./reports/junit.xml"]
}
```

#### List Plan Test Jobs

```http
GET /api/v1/plans/{plan_id}/test-jobs?limit=50&offset=0
X-API-Key: <your-api-key>
```

**Response highlights:**

- `links`, `next_steps`, `params` for list pagination and run/create follow-up
- `links.self` mirrors active plan/job filters and paging state

#### Get Plan Test Job

```http
GET /api/v1/plans/{plan_id}/test-jobs/{job_id}
X-API-Key: <your-api-key>
```

#### Update Plan Test Job

```http
PATCH /api/v1/plans/{plan_id}/test-jobs/{job_id}
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "test_command": "python -m pytest tests/integration",
  "timeout": 900
}
```

#### Run Plan Test Job

```http
POST /api/v1/plans/{plan_id}/test-jobs/{job_id}/run?include_output=false
X-API-Key: <your-api-key>
```

---

### Objectives API

#### Create Objective

```http
POST /api/v1/goals/{goal_id}/objectives
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "name": "Complete onboarding flow"
}
```

#### List Objectives

```http
GET /api/v1/goals/{goal_id}/objectives?limit=50&offset=0
X-API-Key: <your-api-key>
```

#### Update Objective

```http
PATCH /api/v1/objectives/{objective_id}
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "progress_percent": 50
}
```

---

### Key Results API

#### Create Key Result

```http
POST /api/v1/objectives/{objective_id}/key-results
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "name": "Activation rate",
  "current_value": 35,
  "target_value": 60,
  "unit": "%"
}
```

#### List Key Results

```http
GET /api/v1/objectives/{objective_id}/key-results?limit=50&offset=0
X-API-Key: <your-api-key>
```

#### Update Key Result

```http
PATCH /api/v1/key-results/{key_result_id}
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "current_value": 60,
  "target_value": 60
}
```

---

### Tasks API

#### Create Task

```http
POST /api/v1/tasks
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "project_id": "<project-id>",
  "title": "Implement feature X",
  "description": "Add new feature",
  "parent_id": "<parent-task-id>",
  "priority": "high",
  "complexity_points": 75,
  "tags": ["feature", "backend"]
}
```

**Response** (201):

```json
{
  "id": "<task-id>",
  "project_id": "<project-id>",
  "title": "Implement feature X",
  "status": "todo",
  "complexity_points": 75,
  "actual_hours": null,
  "current_progress_percent": 0,
  "checkout": null,
  "workflow_id": null
}
```

#### List Tasks

```http
GET /api/v1/tasks?project_id=<project-id>&status=todo&limit=50&offset=0
X-API-Key: <your-api-key>
```

#### Task Tree

```http
GET /api/v1/tasks/tree?project_id=<project-id>&root_task_id=<root-task-id>
X-API-Key: <your-api-key>
```

**Response** (200):

```json
{
  "project_id": "<project-id>",
  "root_task_id": "<root-task-id>",
  "nodes": [
    {
      "task": {
        "id": "<root-task-id>",
        "project_id": "<project-id>",
        "title": "Root task",
        "status": "todo",
        "priority": "medium",
        "created_at": "2025-12-27T12:00:00Z",
        "updated_at": "2025-12-27T12:00:00Z",
        "last_activity_at": "2025-12-27T12:00:00Z",
        "last_transition_at": null
      },
      "depth": 0,
      "children": [
        {
          "task": {
            "id": "<child-task-id>",
            "project_id": "<project-id>",
            "title": "Child task",
            "status": "todo",
            "priority": "medium",
            "created_at": "2025-12-27T12:00:00Z",
            "updated_at": "2025-12-27T12:00:00Z"
          },
          "depth": 1,
          "children": []
        }
      ]
    }
  ]
}
```

#### Search Tasks

```http
GET /api/v1/tasks/search?query=auth&status=todo&priority=high&limit=50
X-API-Key: <your-api-key>
```

**Response** (200) query wrapper:

```json
{
  "items": [
    {
      "id": "<task-id>",
      "project_id": "<project-id>",
      "title": "Implement auth",
      "status": "todo",
      "priority": "high",
      "last_activity_at": "2025-12-29T12:34:56Z",
      "last_transition_at": "2025-12-29T12:35:10Z"
    }
  ],
  "total_count": 1,
  "offset": 0,
  "limit": 50,
  "links": {
    "self": "/api/v1/tasks/search?query=auth&status=todo&priority=high&limit=50&offset=0",
    "next": null,
    "list": "/api/v1/tasks",
    "search": "/api/v1/tasks/search",
    "ready": "/api/v1/tasks/ready",
    "stale": "/api/v1/tasks/stale",
    "duplicates": "/api/v1/tasks/duplicates",
    "dashboard": "/dashboard",
    "guide": "/api/v1/",
    "task_detail_template": "/api/v1/tasks/{task_id}"
  },
  "next_steps": [
    "GET /api/v1/tasks/<task-id>",
    "PATCH /api/v1/tasks/<task-id>",
    "GET /api/v1/tasks/ready",
    "GET /api/v1/tasks/stale"
  ],
  "params": {
    "query": "auth",
    "status": ["todo"],
    "priority": ["high"],
    "limit": 50,
    "offset": 0
  }
}
```

#### Ready Tasks

```http
GET /api/v1/tasks/ready?project_id=<project-id>&exclude_checked_out=true
X-API-Key: <your-api-key>
```

**Response** (200): same query wrapper shape as Search Tasks (`items`, `total_count`,
`offset`, `limit`, `links`, `next_steps`, `params`).

#### Stale Tasks

```http
GET /api/v1/tasks/stale?project_id=<project-id>&stale_after_days=14
X-API-Key: <your-api-key>
```

**Response** (200): same query wrapper shape as Search Tasks (`items`, `total_count`,
`offset`, `limit`, `links`, `next_steps`, `params`).

#### Duplicate Tasks

```http
GET /api/v1/tasks/duplicates?project_id=<project-id>&min_count=2
X-API-Key: <your-api-key>
```

**Response** (200):

```json
{
  "items": [
    {
      "normalized_title": "implement auth",
      "count": 2,
      "suggested_primary_id": "<task-id>",
      "suggested_primary_reason": "score 6, status todo",
      "last_activity_at": "2025-12-29T12:34:56Z",
      "links": {
        "self": "/api/v1/tasks/duplicates?project_id=<project-id>&min_count=2&limit=100&offset=0",
        "primary_task": "/api/v1/tasks/<task-id>",
        "preview": "/api/v1/tasks/duplicates/preview",
        "merge": "/api/v1/tasks/duplicates/merge",
        "search": "/api/v1/tasks/search",
        "guide": "/api/v1/"
      },
      "next_steps": [
        "POST /api/v1/tasks/duplicates/preview (primary_task_id=<task-id>, duplicate_task_ids=[<task-id-2>])",
        "POST /api/v1/tasks/duplicates/merge (primary_task_id=<task-id>, duplicate_task_ids=[<task-id-2>])",
        "GET /api/v1/tasks/<task-id>",
        "GET /api/v1/tasks/search?query=<text>"
      ],
      "tasks": [
        {
          "id": "<task-id>",
          "project_id": "<project-id>",
          "title": "Implement Auth",
          "status": "todo"
        },
        {
          "id": "<task-id-2>",
          "project_id": "<project-id>",
          "title": "Implement auth",
          "status": "todo"
        }
      ]
    }
  ],
  "total_count": 1,
  "offset": 0,
  "limit": 100,
  "links": {
    "self": "/api/v1/tasks/duplicates?project_id=<project-id>&min_count=2&limit=100&offset=0",
    "next": null,
    "list": "/api/v1/tasks",
    "search": "/api/v1/tasks/search",
    "ready": "/api/v1/tasks/ready",
    "stale": "/api/v1/tasks/stale",
    "duplicates": "/api/v1/tasks/duplicates",
    "preview": "/api/v1/tasks/duplicates/preview",
    "merge": "/api/v1/tasks/duplicates/merge",
    "dashboard": "/dashboard",
    "guide": "/api/v1/",
    "task_detail_template": "/api/v1/tasks/{task_id}"
  },
  "next_steps": [
    "POST /api/v1/tasks/duplicates/preview (primary_task_id=<task-id>, duplicate_task_ids=[<task-id-2>, <task-id-3>])",
    "POST /api/v1/tasks/duplicates/merge (primary_task_id=<task-id>, duplicate_task_ids=[<task-id-2>, <task-id-3>])",
    "GET /api/v1/tasks/<task-id>",
    "GET /api/v1/tasks/search?query=<text>"
  ],
  "params": {
    "project_id": "<project-id>",
    "min_count": 2,
    "include_terminal": false,
    "limit": 100,
    "offset": 0
  }
}
```

#### Preview Duplicate Merge

```http
POST /api/v1/tasks/duplicates/preview
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "primary_task_id": "<task-id>",
  "duplicate_task_ids": ["<task-id-2>", "<task-id-3>"]
}
```

**Response** (200):

```json
{
  "primary_task": {
    "id": "<task-id>",
    "project_id": "<project-id>",
    "title": "Implement Auth",
    "status": "todo"
  },
  "duplicates": [],
  "missing_ids": [],
  "warnings": [],
  "can_merge": true,
  "suggested_primary_id": "<task-id>",
  "suggested_primary_reason": "score 6, status todo",
  "links": {
    "self": "/api/v1/tasks/duplicates/preview",
    "merge": "/api/v1/tasks/duplicates/merge",
    "duplicates": "/api/v1/tasks/duplicates",
    "primary_task": "/api/v1/tasks/<task-id>",
    "guide": "/api/v1/"
  },
  "next_steps": [
    "POST /api/v1/tasks/duplicates/merge (primary_task_id=<task_id>, duplicate_task_ids=[...])",
    "GET /api/v1/tasks/<task-id>",
    "GET /api/v1/tasks/duplicates"
  ]
}
```

#### Merge Duplicate Tasks

```http
POST /api/v1/tasks/duplicates/merge
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "primary_task_id": "<task-id>",
  "duplicate_task_ids": ["<task-id-2>", "<task-id-3>"],
  "cancel_duplicates": true
}
```

**Response** (200):

```json
{
  "primary_task": {
    "id": "<task-id>",
    "project_id": "<project-id>",
    "title": "Implement Auth",
    "status": "todo"
  },
  "duplicate_tasks": [
    {
      "id": "<task-id-2>",
      "project_id": "<project-id>",
      "title": "Implement auth",
      "status": "cancelled"
    }
  ],
  "links_added": 2,
  "duplicates_cancelled": 2,
  "links": {
    "self": "/api/v1/tasks/duplicates/merge",
    "preview": "/api/v1/tasks/duplicates/preview",
    "duplicates": "/api/v1/tasks/duplicates",
    "primary_task": "/api/v1/tasks/<task-id>",
    "guide": "/api/v1/"
  },
  "next_steps": [
    "GET /api/v1/tasks/<task-id>",
    "GET /api/v1/tasks/duplicates",
    "GET /api/v1/tasks/search?query=<text>"
  ]
}
```

#### Saved Search Queues

Create a saved search queue:

```http
POST /api/v1/queues
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "name": "Backend Queue",
  "description": "Backend tasks",
  "filters": {
    "tags": ["backend"],
    "statuses": ["todo", "in_progress"]
  },
  "sort_by": "priority",
  "sort_dir": "desc"
}
```

`sort_dir` is a closed value: use `asc` or `desc`.

Run a saved queue:

```http
GET /api/v1/queues/{queue_id}/run?limit=25
X-API-Key: <your-api-key>
```

List presets:

```http
GET /api/v1/queues/presets?project_id=<project-id>&limit=5
X-API-Key: <your-api-key>
```

**Response**:

```json
{
  "id": "<queue-id>",
  "name": "Backend Queue",
  "description": "Backend tasks",
  "filters": {
    "tags": ["backend"],
    "statuses": ["todo", "in_progress"]
  },
  "items": [
    {
      "task_id": "<task-id>",
      "title": "Implement auth middleware",
      "status": "in_progress"
    }
  ],
  "total_count": 1
}
```

#### Get Task

```http
GET /api/v1/tasks/{task_id}
X-API-Key: <your-api-key>
```

#### Start Task

```http
POST /api/v1/tasks/{task_id}/start
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "updated_by": "developer_alice",
  "reason": "Starting implementation"
}
```

#### Complete Task

```http
POST /api/v1/tasks/{task_id}/complete?notes=All%20tests%20passing
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "updated_by": "developer_alice",
  "reason": "Acceptance criteria met"
}
```

Notes are passed as a query parameter; structured actor/reason metadata is in the
request body.

#### Update Task (Partial)

```http
PATCH /api/v1/tasks/{task_id}
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "title": "Updated title",
  "description": "New details",
  "parent_id": "<parent-task-id>",
  "clear_parent": false,
  "priority": "high",
  "complexity_points": 55
}
```

All fields are optional.

#### Add Task Evidence (Manual)

```http
POST /api/v1/tasks/{task_id}/evidence
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "evidence_type": "scm_commit",
  "reference": "abc123",
  "description": "Manual commit reference",
  "metadata": {"scm": "git"},
  "created_by": "alice"
}
```

Evidence entries are self-declared; the API does not auto-detect SCM metadata.

#### List Task Evidence

```http
GET /api/v1/tasks/{task_id}/evidence?include_test_runs=true&include_output=false&limit=50&offset=0
X-API-Key: <your-api-key>
```

#### Get Task Proof Bundle

```http
GET /api/v1/tasks/{task_id}/proof-bundle?include_output=false&include_logs=false&include_artifacts=false
X-API-Key: <your-api-key>
```

Proof bundles include evidence summaries, test run outputs (optional), and byte
totals for logs/artifacts to support retention sizing.

#### Search Proof Bundles

```http
GET /api/v1/evidence/bundles?plan_id=<plan-id>&status=in_progress&created_from=2025-01-01T00:00:00Z&include_evidence=true&limit=50&offset=0
X-API-Key: <your-api-key>
```

Use `task_id` (repeatable), `plan_id`, `status` (repeatable), `evidence_type`
(repeatable), `created_from`, and `created_to` to filter results. Set
`include_evidence`, `include_test_runs`, or `include_output/include_logs/include_artifacts`
to expand the payload.

#### Diff Revisions

```http
GET /api/v1/revisions/{entity_type}/{entity_id}/diff?from_revision=1&to_revision=2
X-API-Key: <your-api-key>
```

Supported `entity_type` values include: `task`, `project`, `plan`, `goal`,
`objective`, `key_result`, `organization`, `team`, `portfolio`, `program`,
`product`, `label`, `label_category`, `label_gate_rule`, `evidence_gate_rule`,
`saved_search`, `plan_test_job`.

#### Export Revision History Bundle

```http
GET /api/v1/revisions/{entity_type}/{entity_id}/bundle?include_linked=false&include_linked_history=false&history_limit=20&history_offset=0&linked_limit=20&linked_history_limit=20
X-API-Key: <your-api-key>
```

Returns full revision history (including content snapshots) and optional linked
entity histories. Use `include_linked` and `include_linked_history` to expand
linked results.

---

### Test Runs API

#### Create Test Run

```http
POST /api/v1/test-runs
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "server_id": "local",
  "project_id": "<project-id>",
  "success": true,
  "exit_code": 0,
  "duration_seconds": 12.5,
  "started_at": "2025-12-27T12:00:00Z",
  "finished_at": "2025-12-27T12:00:12Z",
  "command": "pytest -v",
  "runner": "local",
  "plan_id": "<plan-id>",
  "task_ids": ["<task-id>", "<task-id-2>"],
  "stdout": "...",
  "stderr": "",
  "logs": {
    "/tmp/test.log": {
      "content": "...",
      "size_bytes": 2048
    }
  },
  "artifacts": {
    "coverage.xml": {
      "local_path": "/tmp/pms-artifacts/<run-id>/coverage.xml",
      "size_bytes": 40960
    }
  }
}
```

#### List Test Runs

```http
GET /api/v1/test-runs?project_id=<project-id>&success=true&limit=50&offset=0
X-API-Key: <your-api-key>
```

#### Get Test Run

```http
GET /api/v1/test-runs/{run_id}?include_output=true&include_logs=true&include_artifacts=true
X-API-Key: <your-api-key>
```

**Response** (200):

```json
{
  "id": "<run-id>",
  "server_id": "local",
  "project_id": "<project-id>",
  "success": true,
  "exit_code": 0,
  "duration_seconds": 12.5,
  "started_at": "2025-12-27T12:00:00Z",
  "finished_at": "2025-12-27T12:00:12Z",
  "command": "pytest -v",
  "runner": "local",
  "plan_id": "<plan-id>",
  "task_ids": ["<task-id>", "<task-id-2>"],
  "stdout": "...",
  "stderr": "",
  "logs": {
    "/tmp/test.log": {
      "content": "...",
      "size_bytes": 2048,
      "captured_at": "2025-12-27T12:00:12Z",
      "modified_at": "2025-12-27T11:58:00Z"
    }
  },
  "artifacts": {
    "coverage.xml": {
      "local_path": "/tmp/pms-artifacts/<run-id>/coverage.xml",
      "size_bytes": 40960,
      "captured_at": "2025-12-27T12:00:12Z",
      "modified_at": "2025-12-27T11:59:50Z"
    }
  }
}
```

#### Test Run Retention

```http
GET /api/v1/test-runs/retention?limit=10&sort=largest&project_id=<project-id>
X-API-Key: <your-api-key>
```

`sort` is a closed value: use `largest` or `recent`.

**Response** (200):

```json
{
  "total_runs": 12,
  "total_log_bytes_combined": 120000000,
  "total_artifact_bytes": 600000000,
  "total_bytes": 720000000,
  "max_log_bytes": 500000000,
  "max_artifact_bytes": 2000000000,
  "max_age_days": 30,
  "sorted_by": "largest",
  "policies": [],
  "alerts": [],
  "items": [
    {
      "run_id": "<run-id>",
      "finished_at": "2025-12-27T12:00:12Z",
      "server_id": "local",
      "project_id": "<project-id>",
      "log_total_bytes": 20480,
      "artifact_bytes": 40960,
      "total_bytes": 61440,
      "artifacts_missing": 0
    }
  ]
}
```

#### Prune Test Runs

```http
POST /api/v1/test-runs/prune?max_log_bytes=50000000&max_artifact_bytes=200000000&max_age_days=30&dry_run=true&project_id=<project-id>
X-API-Key: <your-api-key>
```

**Response** (200):

```json
{
  "runs_scanned": 12,
  "runs_pruned": 3,
  "runs_logs_pruned": 3,
  "runs_artifacts_pruned": 2,
  "stdout_pruned": 3,
  "stderr_pruned": 1,
  "log_bytes_before": 120000000,
  "log_bytes_after": 50000000,
  "log_bytes_pruned": 70000000,
  "artifact_bytes_before": 600000000,
  "artifact_bytes_after": 200000000,
  "artifact_bytes_pruned": 400000000,
  "dry_run": true,
  "pruned_run_ids": ["<run-id>", "<run-id-2>"],
  "scopes": []
}
```

#### Test Run Retention Policies

```http
GET /api/v1/test-runs/retention/policies?scope_type=project&scope_id=<project-id>
X-API-Key: <your-api-key>
```

```http
POST /api/v1/test-runs/retention/policies?scope_type=project&scope_id=<project-id>&max_log_bytes=50000000&max_artifact_bytes=200000000&max_age_days=30
X-API-Key: <your-api-key>
```

```http
PATCH /api/v1/test-runs/retention/policies/{policy_id}?max_log_bytes=75000000
X-API-Key: <your-api-key>
```

```http
POST /api/v1/test-runs/retention/policies/{policy_id}/archive
X-API-Key: <your-api-key>
```

```http
POST /api/v1/test-runs/retention/policies/{policy_id}/restore
X-API-Key: <your-api-key>
```

**Response**:

```json
{
  "id": "<policy-id>",
  "scope_type": "project",
  "scope_id": "<project-id>",
  "max_log_bytes": 75000000,
  "max_artifact_bytes": 200000000,
  "max_age_days": 30,
  "is_active": true,
  "updated_at": "2026-02-21T00:00:00Z"
}
```

---

### Checkout API

#### Checkout Task

```http
POST /api/v1/tasks/{task_id}/checkout
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "agent_session_id": "agent_worker_1",
  "lease_seconds": 300
}
```

**Response** (200):

```json
{
  "task_id": "<task-id>",
  "checkout": {
    "agent_session_id": "agent_worker_1",
    "actor": {
      "ref": "agent-worker-1",
      "id": "<actor-id>",
      "actor": {
        "handle": "agent-worker-1",
        "kind": "runtime_agent"
      }
    },
    "checked_out_at": "2025-12-23T19:00:00Z",
    "lease_until": "2025-12-23T19:05:00Z",
    "version": 1,
    "expired": false
  }
}
```

**Error** (409 Conflict if already checked out):

```json
{
  "detail": "Task <task-id> is checked out by agent_worker_2 until 2025-12-23T19:10:00Z"
}
```

#### Renew Checkout (Heartbeat)

```http
POST /api/v1/tasks/{task_id}/checkout/renew?agent_session_id=agent_worker_1&lease_seconds=300
X-API-Key: <your-api-key>
```

#### Release Checkout

```http
POST /api/v1/tasks/{task_id}/checkout/release?agent_session_id=agent_worker_1
X-API-Key: <your-api-key>
```

#### Force Release Checkout

```http
POST /api/v1/tasks/{task_id}/checkout/force-release?released_by=admin&reason=override
X-API-Key: <your-api-key>
```

#### Get Available Tasks

```http
GET /api/v1/checkout/available?project_id=<project-id>&limit=10
X-API-Key: <your-api-key>
```

#### Get Agent Checkout Status

```http
GET /api/v1/checkout/status?agent_session_id=agent_worker_1&include_expired=false
X-API-Key: <your-api-key>
```

#### Cleanup Expired Checkouts

```http
POST /api/v1/checkout/cleanup?dry_run=false
X-API-Key: <your-api-key>
```

#### Checkout Log

```http
GET /api/v1/checkout/log?task_id=<task-id>&limit=50&success=true&include_metadata=false
X-API-Key: <your-api-key>
```

---

### Progress API

#### Update Progress

```http
POST /api/v1/tasks/{task_id}/progress
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "percent_complete": 75,
  "status_message": "Database integration complete, working on API",
  "updated_by": "agent_worker_1",
  "metadata": {
    "phase": "implementation",
    "blockers": []
  }
}
```

**Response**:

```json
{
  "task_id": "<task-id>",
  "percent_complete": 75,
  "status_message": "Database integration complete...",
  "updated_by": "agent_worker_1",
  "timestamp": "2025-12-23T19:00:00Z"
}
```

#### Get Progress Timeline

```http
GET /api/v1/tasks/{task_id}/progress/timeline
X-API-Key: <your-api-key>
```

**Response**:

```json
{
  "task_id": "<task-id>",
  "current_percent": 75,
  "total_duration_hours": 4.5,
  "velocity_percent_per_hour": 16.7,
  "estimated_completion": "2025-12-23T20:30:00Z",
  "updates_count": 8,
  "velocity_trend": "accelerating"
}
```

---

### Auth API

#### List Available Scopes

```http
GET /api/v1/auth/scopes
X-API-Key: <your-api-key>
```

#### Init Admin Key (Bootstrap)

```http
POST /api/v1/auth/init
Content-Type: application/json

{
  "name": "Initial Admin Key",
  "owner": "owner@example.com"
}
```

#### Create API Key

```http
POST /api/v1/auth/keys
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "name": "CI Key",
  "scopes": ["tasks:read", "tasks:write"],
  "expires_in_days": 30,
  "rate_limit": 1000,
  "metadata": {"service": "ci"}
}
```

**Requires**: `admin:keys`

#### List API Keys

```http
GET /api/v1/auth/keys
X-API-Key: <your-api-key>
```

**Requires**: `admin:keys`

#### Get API Key

```http
GET /api/v1/auth/keys/{key_id}
X-API-Key: <your-api-key>
```

**Requires**: `admin:keys`

#### Delete API Key

```http
DELETE /api/v1/auth/keys/{key_id}
X-API-Key: <your-api-key>
```

**Requires**: `admin:keys`

#### Deactivate API Key

```http
POST /api/v1/auth/keys/{key_id}/deactivate
X-API-Key: <your-api-key>
```

**Requires**: `admin:keys`

#### Restore API Key

```http
POST /api/v1/auth/keys/{key_id}/restore
X-API-Key: <your-api-key>
```

**Requires**: `admin:keys`

---

### Workflows API

#### List Workflows

```http
GET /api/v1/workflows
```

**Response**:

```json
{
  "workflows": [
    {
      "id": "wf_sdlc",
      "name": "software_development_lifecycle",
      "entity_type": "task",
      "states_count": 13,
      "initial_state": "concept"
    },
    {
      "id": "wf_agile",
      "name": "agile_sprint",
      "states_count": 6
    }
  ]
}
```

#### Assign Workflow

```http
POST /api/v1/tasks/{task_id}/workflow/assign
Content-Type: application/json

{
  "workflow_name": "sdlc",
  "initial_state": "concept"
}
```

**Goal/Objective assignment**:

```http
POST /api/v1/goals/{goal_id}/workflow/assign
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "workflow_name": "okr",
  "initial_state": "draft"
}
```

```http
POST /api/v1/objectives/{objective_id}/workflow/assign
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "workflow_name": "okr",
  "initial_state": "draft"
}
```

**Response**:

```json
{
  "status": "assigned",
  "task_id": "<task-id>",
  "workflow": "sdlc",
  "current_state": "concept"
}
```

#### Transition State

```http
POST /api/v1/tasks/{task_id}/workflow/transition
Content-Type: application/json

{
  "to_state": "implementing",
  "triggered_by": "developer_alice",
  "reason": "Design approved, starting implementation"
}
```

**Goal/Objective transitions**:

```http
POST /api/v1/goals/{goal_id}/workflow/transition
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "to_state": "active",
  "triggered_by": "owner@example.com",
  "reason": "Planning complete"
}
```

```http
POST /api/v1/objectives/{objective_id}/workflow/transition
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "to_state": "active",
  "triggered_by": "owner@example.com",
  "reason": "Ready for execution"
}
```

**For transitions requiring approval**:

```json
{
  "to_state": "production",
  "triggered_by": "developer_alice",
  "approved_by": "release_manager",
  "reason": "All quality gates passed"
}
```

**Response**:

```json
{
  "entity_id": "<task-id>",
  "from_state": "concept",
  "to_state": "implementing",
  "triggered_by": "developer_alice",
  "timestamp": "2026-02-21T00:00:00Z"
}
```

#### Align Workflow

```http
POST /api/v1/tasks/{task_id}/workflow/align
Content-Type: application/json

{
  "triggered_by": "developer_alice",
  "to_state": "done"
}
```

**Goal/Objective alignment**:

```http
POST /api/v1/workflow/align
Content-Type: application/json

{
  "entity_id": "<goal_or_objective_id>",
  "entity_type": "goal",
  "triggered_by": "developer_alice"
}
```

**Dry run (no changes)**:

```json
{
  "entity_id": "<task_id>",
  "entity_type": "task",
  "triggered_by": "developer_alice",
  "dry_run": true
}
```

**Response**:

```json
{
  "entity_id": "<task-id>",
  "from_state": "concept",
  "target_state": "done",
  "applied_transitions": [
    "concept->idea",
    "idea->implementing",
    "implementing->done"
  ],
  "remaining": [],
  "aligned": true
}
```

---

### Transition Timelines API

#### Get Workflow Transition Timeline

```http
GET /api/v1/transitions/workflow/{entity_type}/{entity_id}?triggered_by=alice&from_state=concept&to_state=implementing&start_time=2025-12-01T00:00:00Z&end_time=2025-12-31T23:59:59Z&transition_type=workflow&label=needs-review
X-API-Key: <your-api-key>
```

**Supported entity types**: `task`, `goal`, `objective`, `project`, `product`,
`plan`, `program`, `portfolio`, `organization`

**Filters**:

- `triggered_by`: actor ID (user/agent)
- `from_state`, `to_state`: transition states to match
- `start_time`, `end_time`: ISO date range filters
- `transition_type`: `workflow` or `status` (filters by transition metadata)
- `label`: label ID or name (matches current labels on the entity)

**Response**:

```json
{
  "entity_type": "task",
  "entity_id": "<task-id>",
  "kind": "workflow",
  "total_duration_seconds": 14400,
  "total_duration_hours": 4.0,
  "average_state_duration_hours": 2.0,
  "state_durations": {
    "concept": 3600,
    "implementing": 10800
  },
  "transitions": [
    {
      "id": "<event-id>",
      "entity_type": "task_workflow",
      "entity_id": "<task-id>",
      "from_state": "concept",
      "to_state": "implementing",
      "timestamp": "2025-12-29T02:15:00Z",
      "triggered_by": "developer_alice",
      "reason": "Design approved",
      "duration_in_state_seconds": 3600,
      "metadata": { "transition_kind": "workflow" }
    }
  ]
}
```

#### Get Status Transition Timeline

```http
GET /api/v1/transitions/status/{entity_type}/{entity_id}?triggered_by=alice&from_state=todo&to_state=in_progress&start_time=2025-12-01T00:00:00Z&end_time=2025-12-31T23:59:59Z&transition_type=status&label=needs-review
X-API-Key: <your-api-key>
```

**Response**:

```json
{
  "entity_type": "task",
  "entity_id": "<task-id>",
  "kind": "status",
  "total_duration_seconds": 7200,
  "total_duration_hours": 2.0,
  "average_state_duration_hours": 1.0,
  "state_durations": {
    "todo": 1800,
    "in_progress": 5400
  },
  "transitions": [
    {
      "id": "<event-id-2>",
      "entity_type": "task_status",
      "entity_id": "<task-id>",
      "from_state": "todo",
      "to_state": "in_progress",
      "timestamp": "2025-12-29T03:15:00Z",
      "triggered_by": "developer_alice",
      "reason": "Started work",
      "duration_in_state_seconds": 1800,
      "metadata": { "transition_kind": "status" }
    }
  ]
}
```

---

## Custom Fields API

### Create Custom Field Definition

```http
POST /api/v1/custom-fields
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "name": "risk_level",
  "entity_type": "task",
  "field_type": "select",
  "options": ["low", "medium", "high"],
  "is_required": false
}
```

### Set Custom Field Value

```http
POST /api/v1/custom-fields/{field_id}/values
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "entity_type": "task",
  "entity_id": "<task-id>",
  "value": "high",
  "created_by": "automation"
}
```

---

## Comments + Watchers API

### Add Comment

```http
POST /api/v1/comments
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "entity_type": "task",
  "entity_id": "<task-id>",
  "body": "Blocking on API credentials from ops",
  "created_by": "alice",
  "mentions": ["ops-team"]
}
```

### Add Watcher

```http
POST /api/v1/watchers
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "entity_type": "task",
  "entity_id": "<task-id>",
  "watcher": "alice"
}
```

---

## Automation Rules API

### Create Automation Rule

```http
POST /api/v1/automation/rules
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "name": "comment-on-task-complete",
  "event_pattern": "task.completed",
  "action_type": "add_comment",
  "action_payload": {
    "body": "Automation: task completed, ready for review.",
    "created_by": "automation"
  }
}
```

Allowed `action_type` values:

- `add_comment`
- `create_task`
- `update_task_status`
- `set_custom_field_value`

`event_pattern` remains intentionally open. Use exact event names such as
`task.completed` or wildcard selectors such as `task.*`.

### Run Automation Rules for an Event

```http
POST /api/v1/automation/run
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "event_id": "<event-id>",
  "dry_run": true
}
```

---

## Labels API

#### Create Label Category

```http
POST /api/v1/labels/categories
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "name": "Risk",
  "description": "Workflow risk gates",
  "is_exclusive": true,
  "sort_order": 0
}
```

#### Create Label

```http
POST /api/v1/labels
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "name": "needs-review",
  "category_id": "<label-category-id>",
  "color": "#f0b860"
}
```

#### Assign Label

```http
POST /api/v1/labels/assignments
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "entity_type": "task",
  "entity_id": "<task-id>",
  "label_id": "<label-id>",
  "applied_by": "agent@local"
}
```

#### Add Label Gate Rule

```http
POST /api/v1/labels/gates
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "workflow_id": "wf_sdlc",
  "entity_type": "task",
  "from_state": "code_review",
  "to_state": "unit_testing",
  "rule_type": "require_label",
  "label_id": "<label-id>",
  "message": "Add needs-review before unit testing"
}
```

#### Add Evidence Gate Rule

```http
POST /api/v1/evidence/gates
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "workflow_id": "wf_sdlc",
  "entity_type": "task",
  "from_state": "code_review",
  "to_state": "unit_testing",
  "evidence_type": "test_run",
  "min_count": 1,
  "require_success": true,
  "message": "Attach a successful test run before unit testing"
}
```

---

## Endpoint Completeness Addendum

This addendum documents operational endpoints that are frequently used in
automation, restoration, and admin flows.

### Health

#### Health Check

```http
GET /api/v1/health
```

Returns service health and version metadata for liveness checks.

### Project + Goal Graph

#### Get Project Summary

```http
GET /api/v1/projects/{project_id}/summary
X-API-Key: <your-api-key>
```

Returns aggregate project metrics (task/test/progress rollups).

#### Get Project Operator Overview

```http
GET /api/v1/projects/{project_id}/operator-overview?task_limit=5&test_limit=5&queue_limit=3&lineage_limit=3&history_limit=5&include_timeline=true&include_history=false&include_linked_history=false&view=overview
X-API-Key: <your-api-key>
```

Returns one project-level operator bundle so callers do not need to manually join:

- project summary / health
- work-daily queues, blockers, and next actions
- plan lineage rollups
- project revision history

**Response highlights:**

- `project`, `stats`, `health_score`: immediate project health and rollup context
- `daily`: queue-driven next actions and blockers for live operator review
- `lineage`: plan -> task -> test rollups for execution/evidence inspection
- `history`: revision bundle for project-level change traceability
- `links`: direct deep links into the underlying specialized APIs
- `next_steps`: concrete drill-down calls when the wrapper shows risk

**Example response** (200):

```json
{
  "project": {
    "id": "<project-id>",
    "name": "Gateway Launch Control",
    "description": "Launch-control workspace",
    "status": "active",
    "tags": [],
    "org_id": null,
    "portfolio_id": null,
    "program_id": null,
    "product_id": null,
    "created_at": "2026-04-04T13:40:00+00:00",
    "updated_at": "2026-04-04T13:42:00+00:00"
  },
  "stats": {
    "total_tasks": 6,
    "completed_tasks": 2,
    "blocked_tasks": 1,
    "total_test_runs": 3,
    "success_rate": 0.67
  },
  "health_score": 0.74,
  "daily": {
    "next_actions": [
      {
        "id": "<task-id-smoke>",
        "title": "Run final smoke validation",
        "status": "in_progress",
        "project_id": "<project-id>",
        "project_name": "Gateway Launch Control",
        "updated_at": "2026-04-04T13:41:00+00:00"
      }
    ],
    "blockers": [],
    "links": {
      "self": "pms work daily --scope-type project --scope-id <project-id> --format json"
    }
  },
  "lineage": {
    "totals": {
      "total_plans": 1,
      "total_tasks": 3,
      "total_test_runs": 1,
      "failed_test_runs": 0,
      "total_evidence": 2,
      "total_code_evidence": 1
    }
  },
  "history": {
    "entity_type": "project",
    "entity_id": "<project-id>"
  },
  "links": {
    "project_summary": "/api/v1/projects/<project-id>/summary",
    "daily": "/api/v1/work-snapshots/project/<project-id>/daily?task_limit=5&test_limit=5&queue_limit=3&include_timeline=true&include_history=false&history_limit=5&view=overview",
    "lineage": "/api/v1/plans/lineage?project_id=<project-id>&limit=3&task_limit=5&test_limit=5",
    "history_bundle": "/api/v1/revisions/project/<project-id>/bundle?include_linked=false&include_linked_history=false&history_limit=5&linked_limit=3"
  },
  "next_steps": [
    "GET /api/v1/work-snapshots/project/<project-id>/daily",
    "GET /api/v1/plans/lineage?project_id=<project-id>",
    "GET /api/v1/revisions/project/<project-id>/bundle"
  ]
}
```

#### Get Goal

```http
GET /api/v1/goals/{goal_id}
X-API-Key: <your-api-key>
```

Returns goal details including horizon and status.

#### Complete Goal

```http
POST /api/v1/goals/{goal_id}/complete
X-API-Key: <your-api-key>
```

Marks a goal complete and records transition history.

#### Archive Goal

```http
POST /api/v1/goals/{goal_id}/archive
X-API-Key: <your-api-key>
```

Archives a goal while preserving history.

#### Get Objective

```http
GET /api/v1/objectives/{objective_id}
X-API-Key: <your-api-key>
```

Returns a single objective with linked goal context.

#### Complete Objective

```http
POST /api/v1/objectives/{objective_id}/complete
X-API-Key: <your-api-key>
```

Marks an objective complete.

#### Archive Objective

```http
POST /api/v1/objectives/{objective_id}/archive
X-API-Key: <your-api-key>
```

Archives an objective.

#### Get Key Result

```http
GET /api/v1/key-results/{key_result_id}
X-API-Key: <your-api-key>
```

Returns a single key result.

#### Complete Key Result

```http
POST /api/v1/key-results/{key_result_id}/complete
X-API-Key: <your-api-key>
```

Marks a key result complete.

#### Archive Key Result

```http
POST /api/v1/key-results/{key_result_id}/archive
X-API-Key: <your-api-key>
```

Archives a key result.

### Task Actions + Dependencies

#### Block Task

```http
POST /api/v1/tasks/{task_id}/block
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "reason": "Waiting on external API key",
  "updated_by": "owner@example.com"
}
```

Transitions task state to blocked with reason metadata.

#### Unblock Task

```http
POST /api/v1/tasks/{task_id}/unblock
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "reason": "Dependencies resolved",
  "updated_by": "owner@example.com"
}
```

Returns task to active flow after blocker resolution.

#### Review Task

```http
POST /api/v1/tasks/{task_id}/review
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "reviewed_by": "reviewer@example.com",
  "notes": "Ready for merge"
}
```

Records review transition and notes.

#### Reopen Task

```http
POST /api/v1/tasks/{task_id}/reopen
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "reason": "Regression found in staging",
  "updated_by": "qa@example.com"
}
```

Reopens completed/cancelled task for further work.

#### Cancel Task

```http
POST /api/v1/tasks/{task_id}/cancel
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "reason": "Superseded by replacement design",
  "updated_by": "owner@example.com"
}
```

Cancels task while retaining lineage.

#### Add Task Dependency

```http
POST /api/v1/tasks/{task_id}/dependencies
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "depends_on_id": "<depends-on-task-id>",
  "dependency_type": "blocks",
  "created_by": "planner@example.com"
}
```

Creates graph edge between tasks.

#### Remove Task Dependency

```http
DELETE /api/v1/tasks/{task_id}/dependencies/{depends_on_id}
X-API-Key: <your-api-key>
```

Removes dependency edge.

#### Get Task Dependency Graph

```http
GET /api/v1/tasks/{task_id}/graph
X-API-Key: <your-api-key>
```

Returns upstream/downstream task dependency graph.

### Queues (Saved Searches)

#### List Saved Searches

```http
GET /api/v1/queues?owner=alice&scope_type=project&scope_id=<project-id>&limit=50&offset=0&include_archived=false
X-API-Key: <your-api-key>
```

Returns saved queue definitions available to caller.

#### Get Saved Search

```http
GET /api/v1/queues/{queue_id}
X-API-Key: <your-api-key>
```

Returns a single queue definition.

#### Update Saved Search

```http
PUT /api/v1/queues/{queue_id}
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "name": "Open blockers",
  "description": "Tasks blocked > 2 days",
  "filters": {
    "status": "blocked",
    "project_id": "<project-id>"
  },
  "updated_by": "alice"
}
```

Replaces queue metadata/filter payload.

#### Delete Saved Search

```http
DELETE /api/v1/queues/{queue_id}
X-API-Key: <your-api-key>
```

Soft-deletes queue definition.

#### Restore Saved Search

```http
POST /api/v1/queues/{queue_id}/restore
X-API-Key: <your-api-key>
```

Restores archived queue definition.

#### Get Queue Preset

```http
GET /api/v1/queues/presets/{preset}?project_id=<project-id>&limit=25&offset=0&stale_days=14&at_risk_days=7
X-API-Key: <your-api-key>
```

Returns computed result set for named preset.

**Response highlights:**

- `links`, `next_steps`, `params` for continuation and pagination follow-up

### Plan Test Jobs

#### Delete Plan Test Job

```http
DELETE /api/v1/plans/{plan_id}/test-jobs/{job_id}
X-API-Key: <your-api-key>
```

Archives/deletes a plan-attached test job.

#### Restore Plan Test Job

```http
POST /api/v1/plans/{plan_id}/test-jobs/{job_id}/restore
X-API-Key: <your-api-key>
```

Restores archived plan test job.

### Work Snapshots + Daily

#### Get Work Daily

```http
GET /api/v1/work-snapshots/{scope_type}/{scope_id}/daily?task_limit=10&test_limit=10&queue_limit=5&stale_days=14&at_risk_days=7&include_timeline=true&timeline_limit=20&include_history=true&history_limit=20&view=detail
X-API-Key: <your-api-key>
```

Returns daily standup-style digest with tasks/tests/timeline.

**Response highlights:**

- `api_links`: API-native continuation links (`self`, `snapshot`, `review`, `queues`)
- `next_steps_api`: endpoint-level next actions for clients

### Workflows

#### Show Workflow

```http
GET /api/v1/workflows/{workflow_ref}?view=full
X-API-Key: <your-api-key>
```

Returns workflow states/transitions and metadata.

### Test Retention Policies

#### Get Retention Policy

```http
GET /api/v1/test-runs/retention/policies/{policy_id}
X-API-Key: <your-api-key>
```

Returns one retention policy record.

### Custom Fields (Admin + Query)

#### List Custom Fields

```http
GET /api/v1/custom-fields?entity_type=task&include_archived=false
X-API-Key: <your-api-key>
```

Returns custom field definitions for an entity type.

#### Get Custom Field

```http
GET /api/v1/custom-fields/{field_id}
X-API-Key: <your-api-key>
```

Returns one custom field definition.

#### Update Custom Field

```http
PATCH /api/v1/custom-fields/{field_id}
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "description": "Risk level used in release gating",
  "options": ["low", "medium", "high", "critical"],
  "updated_by": "ops@example.com"
}
```

Updates definition metadata/options.

#### Delete Custom Field

```http
DELETE /api/v1/custom-fields/{field_id}
X-API-Key: <your-api-key>
```

Archives custom field definition.

#### Restore Custom Field

```http
POST /api/v1/custom-fields/{field_id}/restore
X-API-Key: <your-api-key>
```

Restores archived definition.

#### List Custom Field Values (Entity)

```http
GET /api/v1/custom-fields/values?entity_type=task&entity_id=<task-id>&include_history=true&limit=50&offset=0
X-API-Key: <your-api-key>
```

Returns custom field values currently set on an entity.

#### List Custom Field Values (Field)

```http
GET /api/v1/custom-fields/{field_id}/values?limit=50&offset=0
X-API-Key: <your-api-key>
```

Returns values for a specific field across entities.

### Comments + Watchers (Query + Restore)

#### List Comments

```http
GET /api/v1/comments?entity_type=task&entity_id=<task-id>&include_archived=false&limit=50&offset=0
X-API-Key: <your-api-key>
```

Returns comment thread for entity scope.

**Response highlights:**

- `links`, `next_steps`, `params` for pagination and continuation
- `links.entity` resolves to the entity endpoint when supported (`task`, `project`, etc.)

#### Get Comment

```http
GET /api/v1/comments/{comment_id}
X-API-Key: <your-api-key>
```

Returns single comment payload.

#### Delete Comment

```http
DELETE /api/v1/comments/{comment_id}
X-API-Key: <your-api-key>
```

Archives a comment.

#### Restore Comment

```http
POST /api/v1/comments/{comment_id}/restore
X-API-Key: <your-api-key>
```

Restores archived comment.

#### List Watchers

```http
GET /api/v1/watchers?entity_type=task&entity_id=<task-id>&include_archived=false&limit=50&offset=0
X-API-Key: <your-api-key>
```

Returns watcher records for an entity.

**Response highlights:**

- `links`, `next_steps`, `params` for pagination and continuation
- `links.comments` points to sibling comment thread query

#### Remove Watcher

```http
DELETE /api/v1/watchers?entity_type=task&entity_id=<task-id>&watcher=alice
X-API-Key: <your-api-key>
```

Removes watcher assignment.

#### Restore Watcher

```http
POST /api/v1/watchers/{watcher_id}/restore
X-API-Key: <your-api-key>
```

Restores archived watcher assignment.

### Automation Rules (Query + Lifecycle)

#### List Automation Rules

```http
GET /api/v1/automation/rules?include_archived=false&enabled=true&limit=50&offset=0
X-API-Key: <your-api-key>
```

Returns automation rules filtered by archived/enabled flags.

**Response highlights:**

- `offset`, `limit` pagination fields
- `links`, `next_steps`, `params` for continuation and run-history traversal

#### Get Automation Rule

```http
GET /api/v1/automation/rules/{rule_id}
X-API-Key: <your-api-key>
```

Returns one automation rule with trigger/action settings.

#### Update Automation Rule

```http
PATCH /api/v1/automation/rules/{rule_id}
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "enabled": true,
  "description": "Auto-comment when task transitions to done",
  "updated_by": "ops@example.com"
}
```

Updates automation rule metadata/behavior.

#### Delete Automation Rule

```http
DELETE /api/v1/automation/rules/{rule_id}
X-API-Key: <your-api-key>
```

Archives automation rule.

#### Restore Automation Rule

```http
POST /api/v1/automation/rules/{rule_id}/restore
X-API-Key: <your-api-key>
```

Restores archived automation rule.

#### List Automation Rule Runs

```http
GET /api/v1/automation/rules/{rule_id}/runs?limit=50&offset=0
X-API-Key: <your-api-key>
```

Returns execution history for a rule.

**Response highlights:**

- `links.rule` back-link to owning automation rule
- `links`, `next_steps`, `params` for pagination and follow-up execution

### Agent Loops

#### List Agent Loops

```http
GET /api/v1/agent-loops?project_id=<project-id>&include_ended=false&limit=50&offset=0
X-API-Key: <your-api-key>
```

Returns loop sessions for project/autonomous iteration flows.

**Response highlights:**

- `offset`, `limit` pagination fields
- `links`, `next_steps`, `params` for continuation into loop detail/messages/cancel

#### Get Agent Loop

```http
GET /api/v1/agent-loops/{loop_id}
X-API-Key: <your-api-key>
```

Returns state/details for one loop session.

#### Get Agent Loop Messages

```http
GET /api/v1/agent-loops/{loop_id}/messages?limit=200&offset=0
X-API-Key: <your-api-key>
```

Returns transcript/messages for loop execution.

**Response highlights:**

- `offset`, `limit` pagination fields
- `links.loop` to the parent loop summary
- `links`, `next_steps`, `params` for transcript paging and control actions

#### Cancel Agent Loop

```http
POST /api/v1/agent-loops/{loop_id}/cancel
X-API-Key: <your-api-key>
```

Requests graceful loop cancellation.

### Labels + Gates (Query + Lifecycle)

#### List Label Categories

```http
GET /api/v1/labels/categories?include_archived=false
X-API-Key: <your-api-key>
```

Returns category definitions.

#### Get Label Category

```http
GET /api/v1/labels/categories/{category_id}
X-API-Key: <your-api-key>
```

Returns single category definition.

#### Update Label Category

```http
PATCH /api/v1/labels/categories/{category_id}
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "description": "Quality and risk controls",
  "is_exclusive": true,
  "updated_by": "ops@example.com"
}
```

Updates category metadata.

#### Delete Label Category

```http
DELETE /api/v1/labels/categories/{category_id}
X-API-Key: <your-api-key>
```

Archives category.

#### Restore Label Category

```http
POST /api/v1/labels/categories/{category_id}/restore
X-API-Key: <your-api-key>
```

Restores archived category.

#### List Labels

```http
GET /api/v1/labels?category_id=<label-category-id>&include_archived=false
X-API-Key: <your-api-key>
```

Returns label definitions.

#### Get Label

```http
GET /api/v1/labels/{label_id}
X-API-Key: <your-api-key>
```

Returns single label definition.

#### Update Label

```http
PATCH /api/v1/labels/{label_id}
Content-Type: application/json
X-API-Key: <your-api-key>

{
  "name": "needs-verification",
  "color": "#e48b2a",
  "updated_by": "ops@example.com"
}
```

Updates label metadata.

#### Delete Label

```http
DELETE /api/v1/labels/{label_id}
X-API-Key: <your-api-key>
```

Archives label.

#### Restore Label

```http
POST /api/v1/labels/{label_id}/restore
X-API-Key: <your-api-key>
```

Restores archived label.

#### List Label Assignments

```http
GET /api/v1/labels/assignments?entity_type=task&entity_id=<task-id>&limit=50&offset=0
X-API-Key: <your-api-key>
```

Returns assignment records on an entity.

#### Remove Label Assignment

```http
DELETE /api/v1/labels/assignments?entity_type=task&entity_id=<task-id>&label_id=<label-id>
X-API-Key: <your-api-key>
```

Removes label from entity.

#### Get Label Assignment History

```http
GET /api/v1/labels/assignments/{assignment_id}/history?limit=50&offset=0
X-API-Key: <your-api-key>
```

Returns assignment lifecycle history.

#### List Label Gate Rules

```http
GET /api/v1/labels/gates?workflow_id=wf_sdlc&entity_type=task&from_state=code_review&to_state=unit_testing
X-API-Key: <your-api-key>
```

Returns label gate rules for workflow transition filters.

#### Delete Label Gate Rule

```http
DELETE /api/v1/labels/gates/{rule_id}
X-API-Key: <your-api-key>
```

Deletes label gate rule.

#### List Evidence Gate Rules

```http
GET /api/v1/evidence/gates?workflow_id=wf_sdlc&entity_type=task&from_state=code_review&to_state=unit_testing
X-API-Key: <your-api-key>
```

Returns evidence gate rules for transition filters.

#### Delete Evidence Gate Rule

```http
DELETE /api/v1/evidence/gates/{rule_id}
X-API-Key: <your-api-key>
```

Deletes evidence gate rule.

---

## Error Codes

| Code | Meaning      | Example                      |
| ---- | ------------ | ---------------------------- |
| 200  | Success      | Operation completed          |
| 201  | Created      | Resource created             |
| 400  | Bad Request  | Invalid data/transition      |
| 404  | Not Found    | Resource doesn't exist       |
| 409  | Conflict     | Task already checked out     |
| 423  | Locked       | Task blocked by dependencies |
| 500  | Server Error | Internal error               |

---

## Performance

**Measured**:

- Server startup: < 1 second
- Average request latency: ~50ms
- Concurrent requests: 100+ supported
- Database: Persistent connection (no cold starts)

---

## Examples

See `tests/api/test_api_server.py` for complete examples of:

- Creating products via API
- Creating and managing tasks
- Checkout operations
- Progress tracking
- Workflow transitions

---

**Status**: Manually curated endpoint guide backed by live route and depth audits
**Version**: Matches installed PMS version (`uv run pms version`)
