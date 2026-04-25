# Dashboard Usage Guide

This guide covers the dashboard UI, lineage views, and recommended workflows for
linking plan -> task -> test activity.

## Quick Start

1. Initialize and start the API server:

```bash
uv run pms init
uv run pms serve
```

2. Create an API key (if you do not already have one):

```bash
uv run pms auth init --show-key
```

3. Open the dashboard UI and paste the API key:

```
http://127.0.0.1:27541/dashboard
```

The dashboard is read-only and uses `X-API-Key` for requests.

## Dashboard Sections

### Project Operator Console

Use the **Project Operator Console** panel when you want the dashboard to answer
the core operator questions directly for one project:

- what changed since the last review
- what is blocked and why
- what should happen next
- where to jump next in the API

Enter a `project_id`, then click **Reload**. The panel composes:

- `GET /api/v1/projects/{project_id}/operator-overview`
- `GET /api/v1/observability/overview`

It surfaces digest deltas, last-review timing, scoped blockers, recommended
actions, and direct deep links into summary, daily, lineage, history, and
observability APIs.

### Organization / Portfolio / Program

Use the filters to scope rollups:

- `org_id` for portfolios
- `org_id` + `portfolio_id` for programs

Rollups include totals for projects, goals, objectives, tasks, and blocked tasks,
plus digest deltas since the last review, evidence totals, test retention usage,
and ready-task “next actions” previews.

### Plan Lineage (plan -> task -> test)

The Plan Lineage panel shows:

- Task rollups for each plan
- Recent test runs linked to the same plan or project

Filters:

- `plan_id` to focus on a single plan
- `project_id` to focus on a project
- `status` for plan status (draft, active, completed, archived)

### Work Snapshot

The Work Snapshot panel provides a unified view of an organization, portfolio,
program, or project with:

- Totals for work objects (projects, goals, tasks, blocked tasks)
- Digest counts since the last review
- Evidence and retention summaries
- Recent tasks and test runs

Set `scope_type` and `scope_id`, then click **Reload**. Use **Mark Reviewed** to
store a review checkpoint and reset the digest baseline.

## Linking Test Runs to Lineage

Lineage uses test run metadata to connect runs to plans and tasks. When running
remote tests, pass IDs explicitly:

```bash
uv run pms aws test run mytest ./myproject \
  --project-id <project-id> \
  --plan-id <plan-id> \
  --task-id <task-id> \
  --task-id <task-id-2>
```

If `plan_id` or `task_id` values are provided, the lineage view uses them first.
If not, it falls back to `project_id` on the test run.

You can also auto-transition tasks based on test outcomes by passing
`--on-success-state` and/or `--on-failure-state` alongside `--task-id`.

## CLI Companion

You can also view lineage from the CLI:

```bash
uv run pms plan lineage --format table
uv run pms plan lineage --format json --project-id <project-id>
```

Lineage cards include evidence rollups (total evidence + `scm_*` code evidence)
to connect plans to code changes alongside test results.

### Test Run Retention

The retention panel shows current log/artifact usage vs configured limits,
plus the largest recent test runs. Use it to spot runaway outputs before
they consume disk.

### Smart Queues

The Smart Queues panel shows ready/stale/blocked/overdue/at-risk task
counts with a few sample titles. Use the `project_id` filter to scope
queues to a single project.

## Troubleshooting

- "disconnected": API base or key is missing/invalid.
- "no linked test runs": run tests with `--project-id` and optionally `--plan-id`
  / `--task-id` to link them.
