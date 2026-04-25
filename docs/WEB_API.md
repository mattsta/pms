# PMS Web API Server

**Version**: Matches installed PMS version (`uv run pms version`)
**Status**: Available (API keys required)

---

## Overview

PMS includes a **FastAPI-based Web API server** that exposes core functionality via RESTful HTTP endpoints. This enables:

- **Warm server-backed access** - repeated HTTP calls reuse one live runtime
- **Concurrent access** - multiple agents and tools can use one API surface
- **Client-server workflows** - CLI, MCP, and compiled clients can target the same server
- **Pluggable storage** - use SQLite by default or PostgreSQL via `PMS_DATABASE_PATH`

---

## Quick Start

### 1. Start the Server

```bash
# Development (SQLite, default local bind http://127.0.0.1:27541)
uv run pms serve

# PostgreSQL-backed server
uv sync --extra postgres
PMS_DATABASE_PATH=postgresql://user:pass@localhost/pms \
PMS_SERVER_BASE_URL=http://127.0.0.1:27541 \
uv run pms serve --host 0.0.0.0 --port 27541
```

If clients should use a different externally routable URL than the local
default, set `PMS_SERVER_BASE_URL` to that public URL before starting the
server.

### 2. Access API Documentation

**Interactive Swagger UI**: http://127.0.0.1:27541/docs
**Health Check**: http://127.0.0.1:27541/api/v1/health
**Dashboard UI**: http://127.0.0.1:27541/dashboard
**Guide**: [`docs/DASHBOARD_USAGE.md`](DASHBOARD_USAGE.md)

### 3. Create an API key

The API requires `X-API-Key` on all endpoints. Bootstrap the first admin key
locally:

```bash
uv run pms auth init --show-key
```

### 4. Use the API

**Create a task**:

```bash
curl -X POST http://127.0.0.1:27541/api/v1/tasks \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $PMS_API_KEY" \
  -d '{
    "project_id": "<project-id>",
    "title": "Implement feature",
    "complexity_points": 75,
    "priority": "high"
  }'
```

Use canonical stored IDs for `_id` fields. PMS treats task, project, goal, and
similar row IDs as opaque tokens unless a surface explicitly documents a
different contract.

**Checkout task (distributed agents)**:

```bash
curl -X POST http://127.0.0.1:27541/api/v1/tasks/<task-id>/checkout \
  -H "X-API-Key: $PMS_API_KEY" \
  -d '{"agent_session_id": "agent_worker_1", "lease_seconds": 300}'
```

**Update progress**:

```bash
curl -X POST http://127.0.0.1:27541/api/v1/tasks/<task-id>/progress \
  -H "X-API-Key: $PMS_API_KEY" \
  -d '{
    "percent_complete": 50,
    "status_message": "Halfway done",
    "updated_by": "<agent-session-id>"
  }'
```

**Attach manual evidence**:

```bash
curl -X POST http://127.0.0.1:27541/api/v1/tasks/<task-id>/evidence \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $PMS_API_KEY" \
  -d '{
    "evidence_type": "scm_commit",
    "reference": "abc123",
    "description": "Manual commit reference",
    "metadata": {"scm": "git"},
    "created_by": "alice"
  }'
```

**Search proof bundles**:

```bash
curl -X GET "http://127.0.0.1:27541/api/v1/evidence/bundles?plan_id=<plan-id>&status=in_progress&created_from=2025-01-01T00:00:00Z&include_evidence=true" \
  -H "X-API-Key: $PMS_API_KEY"
```

**Diff revisions**:

```bash
curl -X GET "http://127.0.0.1:27541/api/v1/revisions/project/<project-id>/diff?from_revision=1&to_revision=2" \
  -H "X-API-Key: $PMS_API_KEY"
```

**Export revision history bundle**:

```bash
curl -X GET "http://127.0.0.1:27541/api/v1/revisions/project/<project-id>/bundle?include_linked=true&include_linked_history=true&history_limit=20&linked_limit=10" \
  -H "X-API-Key: $PMS_API_KEY"
```

**Find duplicates**:

```bash
curl -X GET "http://127.0.0.1:27541/api/v1/tasks/duplicates?project_id=<project-id>" \
  -H "X-API-Key: $PMS_API_KEY"
```

**Merge duplicates**:

```bash
curl -X POST http://127.0.0.1:27541/api/v1/tasks/duplicates/merge \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $PMS_API_KEY" \
  -d '{
    "primary_task_id": "<primary-task-id>",
    "duplicate_task_ids": ["<duplicate-task-id-1>", "<duplicate-task-id-2>"],
    "cancel_duplicates": true
  }'
```

**List test runs**:

```bash
curl -X GET "http://127.0.0.1:27541/api/v1/test-runs?project_id=<project-id>" \
  -H "X-API-Key: $PMS_API_KEY"
```

**Get test run details**:

```bash
curl -X GET "http://127.0.0.1:27541/api/v1/test-runs/<run-id>?include_output=true&include_logs=true" \
  -H "X-API-Key: $PMS_API_KEY"
```

### 5. Start from machine-first entrypoints

If your caller is an autonomous agent or machine integration, do not start by
hardcoding entity routes. Start with the discoverability and observability
surfaces, then follow their continuation fields.

```text
GET /api/v1/discoverability/graph
GET /api/v1/observability/overview
GET /api/v1/tasks/{task_id}
GET /api/v1/plans?task_id={task_id}
```

Read these docs together:

- [`docs/MACHINE_INTERFACE_GUIDE.md`](MACHINE_INTERFACE_GUIDE.md)
- [`docs/API_REFERENCE.md`](API_REFERENCE.md)
- [`docs/API_ENDPOINT_CATALOG.md`](API_ENDPOINT_CATALOG.md)

---

## End-to-End API Walkthrough (Project -> Goal -> Tasks -> Proof)

This walkthrough mirrors the CLI/MCP examples but uses raw HTTP calls so every
event, transition, and evidence artifact is captured in a time-series form.

### 1) Create project + acceptance criteria graph

```bash
curl -s -H "X-API-Key: $PMS_API_KEY" -H "Content-Type: application/json" \
  -X POST http://127.0.0.1:27541/api/v1/projects \
  -d '{"name":"Resume Hosting Site","description":"Resume hosting MVP"}'

curl -s -H "X-API-Key: $PMS_API_KEY" -H "Content-Type: application/json" \
  -X POST http://127.0.0.1:27541/api/v1/goals \
  -d '{"name":"Launch resume hosting MVP","project_id":"<project_id>","horizon":"short_term"}'

curl -s -H "X-API-Key: $PMS_API_KEY" -H "Content-Type: application/json" \
  -X POST http://127.0.0.1:27541/api/v1/goals/<goal_id>/objectives \
  -d '{"name":"MVP acceptance criteria"}'

curl -s -H "X-API-Key: $PMS_API_KEY" -H "Content-Type: application/json" \
  -X POST http://127.0.0.1:27541/api/v1/objectives/<objective_id>/key-results \
  -d '{"name":"Landing page + upload flow"}'
```

### 2) Create plan + tasks

```bash
curl -s -H "X-API-Key: $PMS_API_KEY" -H "Content-Type: application/json" \
  -X POST http://127.0.0.1:27541/api/v1/plans \
  -d '{"name":"Resume Hosting MVP Plan","format":"json","content":{"acceptance_criteria":[{"id":"ac-1","description":"Landing page + upload flow"}]},"project_id":"<project_id>","goal_id":"<goal_id>","objective_id":"<objective_id>"}'

curl -s -H "X-API-Key: $PMS_API_KEY" -H "Content-Type: application/json" \
  -X POST http://127.0.0.1:27541/api/v1/tasks \
  -d '{"project_id":"<project_id>","title":"Implement static site skeleton"}'
```

### 3) Workflow + progress + evidence

```bash
curl -s -H "X-API-Key: $PMS_API_KEY" -H "Content-Type: application/json" \
  -X POST http://127.0.0.1:27541/api/v1/tasks/<task_id>/workflow/assign \
  -d '{"workflow_name":"sdlc","initial_state":"concept"}'

curl -s -H "X-API-Key: $PMS_API_KEY" -H "Content-Type: application/json" \
  -X POST http://127.0.0.1:27541/api/v1/tasks/<task_id>/start \
  -d '{"updated_by":"api-user"}'

curl -s -H "X-API-Key: $PMS_API_KEY" -H "Content-Type: application/json" \
  -X POST http://127.0.0.1:27541/api/v1/tasks/<task_id>/progress \
  -d '{"percent_complete":35,"status_message":"Scaffolded layout","updated_by":"api-user"}'

curl -s -H "X-API-Key: $PMS_API_KEY" -H "Content-Type: application/json" \
  -X POST http://127.0.0.1:27541/api/v1/tasks/<task_id>/workflow/transition \
  -d '{"to_state":"idea","triggered_by":"api-user"}'

curl -s -H "X-API-Key: $PMS_API_KEY" -H "Content-Type: application/json" \
  -X POST http://127.0.0.1:27541/api/v1/tasks/<task_id>/evidence \
  -d '{"evidence_type":"artifact","reference":"src/index.html","description":"Initial layout"}'
```

### 4) Time-series timelines + audit bundles

```bash
curl -s -H "X-API-Key: $PMS_API_KEY" \
  http://127.0.0.1:27541/api/v1/tasks/<task_id>/progress/timeline

curl -s -H "X-API-Key: $PMS_API_KEY" \
  http://127.0.0.1:27541/api/v1/transitions/workflow/task/<task_id>

curl -s -H "X-API-Key: $PMS_API_KEY" \
  "http://127.0.0.1:27541/api/v1/revisions/task/<task_id>/bundle?include_linked=true&include_linked_history=true"

curl -s -H "X-API-Key: $PMS_API_KEY" \
  http://127.0.0.1:27541/api/v1/work-snapshots/project/<project_id>
```

### 5) Multi-horizon planning (short/medium/long)

```bash
curl -s -H "X-API-Key: $PMS_API_KEY" -H "Content-Type: application/json" \
  -X POST http://127.0.0.1:27541/api/v1/goals \
  -d '{"name":"Stabilize MVP","project_id":"<project_id>","horizon":"short_term"}'

curl -s -H "X-API-Key: $PMS_API_KEY" -H "Content-Type: application/json" \
  -X POST http://127.0.0.1:27541/api/v1/goals \
  -d '{"name":"Scale usage","project_id":"<project_id>","horizon":"medium_term"}'

curl -s -H "X-API-Key: $PMS_API_KEY" -H "Content-Type: application/json" \
  -X POST http://127.0.0.1:27541/api/v1/goals \
  -d '{"name":"Platform expansion","project_id":"<project_id>","horizon":"long_term"}'
```

---

## API vs CLI vs MCP Parity Matrix (Appendix)

This appendix maps each API endpoint to its CLI command and MCP tool. Use it to
translate workflows across interfaces and confirm feature coverage.

### Organizations

| Action        | CLI                       | MCP Tool                               | API Endpoint                             |
| ------------- | ------------------------- | -------------------------------------- | ---------------------------------------- |
| Create org    | `pms org create "<name>"` | `mcp__pms__create_organization`        | `POST /api/v1/organizations`             |
| List orgs     | `pms org list`            | `mcp__pms__list_organizations`         | `GET /api/v1/organizations`              |
| Show org      | `pms org show <id>`       | `mcp__pms__get_organization`           | `GET /api/v1/organizations/<id>`         |
| Update org    | `pms org update <id>`     | `mcp__pms__update_organization`        | `PATCH /api/v1/organizations/<id>`       |
| Org summary   | `pms org summary <id>`    | `mcp__pms__get_organization_summary`   | `GET /api/v1/organizations/<id>/summary` |
| Org dashboard | `pms org dashboard`       | `mcp__pms__get_organization_dashboard` | `GET /api/v1/organizations/dashboard`    |

### Instance Operator Dashboard

| Action             | CLI             | MCP Tool                  | API Endpoint            |
| ------------------ | --------------- | ------------------------- | ----------------------- |
| Instance dashboard | `pms dashboard` | `mcp__pms__get_dashboard` | `GET /api/v1/dashboard` |

### Teams

| Action      | CLI                                      | MCP Tool                | API Endpoint               |
| ----------- | ---------------------------------------- | ----------------------- | -------------------------- |
| Create team | `pms team create "<name>" --org "<org>"` | `mcp__pms__create_team` | `POST /api/v1/teams`       |
| List teams  | `pms team list`                          | `mcp__pms__list_teams`  | `GET /api/v1/teams`        |
| Show team   | `pms team show <id>`                     | `mcp__pms__get_team`    | `GET /api/v1/teams/<id>`   |
| Update team | `pms team update <id>`                   | `mcp__pms__update_team` | `PATCH /api/v1/teams/<id>` |

### Portfolios

| Action              | CLI                                           | MCP Tool                            | API Endpoint                          |
| ------------------- | --------------------------------------------- | ----------------------------------- | ------------------------------------- |
| Create portfolio    | `pms portfolio create "<name>" --org "<org>"` | `mcp__pms__create_portfolio`        | `POST /api/v1/portfolios`             |
| List portfolios     | `pms portfolio list`                          | `mcp__pms__list_portfolios`         | `GET /api/v1/portfolios`              |
| Show portfolio      | `pms portfolio show <id>`                     | `mcp__pms__get_portfolio`           | `GET /api/v1/portfolios/<id>`         |
| Update portfolio    | `pms portfolio update <id>`                   | `mcp__pms__update_portfolio`        | `PATCH /api/v1/portfolios/<id>`       |
| Portfolio summary   | `pms portfolio summary <id>`                  | `mcp__pms__get_portfolio_summary`   | `GET /api/v1/portfolios/<id>/summary` |
| Portfolio dashboard | `pms portfolio dashboard --org "<org>"`       | `mcp__pms__get_portfolio_dashboard` | `GET /api/v1/portfolios/dashboard`    |

### Programs

| Action            | CLI                                                                   | MCP Tool                          | API Endpoint                        |
| ----------------- | --------------------------------------------------------------------- | --------------------------------- | ----------------------------------- |
| Create program    | `pms program create "<name>" --org "<org>" --portfolio "<portfolio>"` | `mcp__pms__create_program`        | `POST /api/v1/programs`             |
| List programs     | `pms program list`                                                    | `mcp__pms__list_programs`         | `GET /api/v1/programs`              |
| Show program      | `pms program show <id>`                                               | `mcp__pms__get_program`           | `GET /api/v1/programs/<id>`         |
| Update program    | `pms program update <id>`                                             | `mcp__pms__update_program`        | `PATCH /api/v1/programs/<id>`       |
| Program summary   | `pms program summary <id>`                                            | `mcp__pms__get_program_summary`   | `GET /api/v1/programs/<id>/summary` |
| Program dashboard | `pms program dashboard --org "<org>" --portfolio "<portfolio>"`       | `mcp__pms__get_program_dashboard` | `GET /api/v1/programs/dashboard`    |

### Products

| Action          | CLI                           | MCP Tool | API Endpoint                         |
| --------------- | ----------------------------- | -------- | ------------------------------------ |
| Create product  | `pms product create "<name>"` | -        | `POST /api/v1/products`              |
| List products   | `pms product list`            | -        | `GET /api/v1/products`               |
| Show product    | `pms product show <id>`       | -        | `GET /api/v1/products/<id>`          |
| Update product  | `pms product update <id>`     | -        | `PATCH /api/v1/products/<id>`        |
| Product summary | `pms product summary <id>`    | -        | `GET /api/v1/products/<id>/summary`  |
| Archive product | `pms product archive <id>`    | -        | `POST /api/v1/products/<id>/archive` |

### Projects

| Action          | CLI                           | MCP Tool                        | API Endpoint                                  |
| --------------- | ----------------------------- | ------------------------------- | --------------------------------------------- |
| Create project  | `pms project create "<name>"` | `mcp__pms__create_project`      | `POST /api/v1/projects`                       |
| List projects   | `pms project list`            | `mcp__pms__list_projects`       | `GET /api/v1/projects`                        |
| Show project    | `pms project show <id>`       | `mcp__pms__get_project`         | `GET /api/v1/projects/<id>`                   |
| Update project  | `pms project update <id>`     | `mcp__pms__update_project`      | `PATCH /api/v1/projects/<id>`                 |
| Project summary | `pms project summary <id>`    | `mcp__pms__get_project_summary` | `GET /api/v1/projects/<id>/summary`           |
| Operator bundle | -                             | -                               | `GET /api/v1/projects/<id>/operator-overview` |

### Goals, Objectives, Key Results

| Action              | CLI                                                 | MCP Tool                        | API Endpoint                                         |
| ------------------- | --------------------------------------------------- | ------------------------------- | ---------------------------------------------------- |
| Create goal         | `pms goal create "<name>"`                          | `mcp__pms__create_goal`         | `POST /api/v1/goals`                                 |
| List goals          | `pms goal list`                                     | `mcp__pms__list_goals`          | `GET /api/v1/goals`                                  |
| Show goal           | `pms goal show <id>`                                | `mcp__pms__get_goal`            | `GET /api/v1/goals/<id>`                             |
| Update goal         | `pms goal update <id>`                              | `mcp__pms__update_goal`         | `PATCH /api/v1/goals/<id>`                           |
| Complete goal       | `pms goal complete <id>`                            | `mcp__pms__complete_goal`       | `POST /api/v1/goals/<id>/complete`                   |
| Archive goal        | `pms goal archive <id>`                             | `mcp__pms__archive_goal`        | `POST /api/v1/goals/<id>/archive`                    |
| Goal summary        | `pms goal summary <id>`                             | `mcp__pms__get_goal_summary`    | `GET /api/v1/goals/<id>/summary`                     |
| Create objective    | `pms objective create "<name>" --goal "<goal>"`     | `mcp__pms__create_objective`    | `POST /api/v1/goals/<goal_id>/objectives`            |
| List objectives     | `pms objective list --goal "<goal>"`                | `mcp__pms__list_objectives`     | `GET /api/v1/goals/<goal_id>/objectives`             |
| Show objective      | `pms objective show <id>`                           | `mcp__pms__get_objective`       | `GET /api/v1/objectives/<id>`                        |
| Update objective    | `pms objective update <id>`                         | `mcp__pms__update_objective`    | `PATCH /api/v1/objectives/<id>`                      |
| Complete objective  | `pms objective complete <id>`                       | `mcp__pms__complete_objective`  | `POST /api/v1/objectives/<id>/complete`              |
| Archive objective   | `pms objective archive <id>`                        | `mcp__pms__archive_objective`   | `POST /api/v1/objectives/<id>/archive`               |
| Create key result   | `pms keyresult create "<name>" --objective "<obj>"` | `mcp__pms__create_key_result`   | `POST /api/v1/objectives/<objective_id>/key-results` |
| List key results    | `pms keyresult list --objective "<obj>"`            | `mcp__pms__list_key_results`    | `GET /api/v1/objectives/<objective_id>/key-results`  |
| Show key result     | `pms keyresult show <id>`                           | `mcp__pms__get_key_result`      | `GET /api/v1/key-results/<id>`                       |
| Update key result   | `pms keyresult update <id>`                         | `mcp__pms__update_key_result`   | `PATCH /api/v1/key-results/<id>`                     |
| Complete key result | `pms keyresult complete <id>`                       | `mcp__pms__complete_key_result` | `POST /api/v1/key-results/<id>/complete`             |
| Archive key result  | `pms keyresult archive <id>`                        | `mcp__pms__archive_key_result`  | `POST /api/v1/key-results/<id>/archive`              |

### Plans + Plan Test Jobs

| Action                | CLI                                            | MCP Tool                         | API Endpoint                                         |
| --------------------- | ---------------------------------------------- | -------------------------------- | ---------------------------------------------------- |
| Create plan           | `pms plan create "<name>"`                     | `mcp__pms__create_plan`          | `POST /api/v1/plans`                                 |
| List plans            | `pms plan list`                                | `mcp__pms__list_plans`           | `GET /api/v1/plans`                                  |
| Plan lineage          | `pms plan lineage`                             | -                                | `GET /api/v1/plans/lineage`                          |
| Show plan             | `pms plan show <id>`                           | `mcp__pms__get_plan`             | `GET /api/v1/plans/<id>`                             |
| Update plan           | `pms plan update <id>`                         | `mcp__pms__update_plan`          | `PATCH /api/v1/plans/<id>`                           |
| Create plan test job  | `pms plan test-job create <plan_id>`           | `mcp__pms__create_plan_test_job` | `POST /api/v1/plans/<id>/test-jobs`                  |
| List plan test jobs   | `pms plan test-job list <plan_id>`             | `mcp__pms__list_plan_test_jobs`  | `GET /api/v1/plans/<id>/test-jobs`                   |
| Show plan test job    | `pms plan test-job show <plan_id> <job_id>`    | `mcp__pms__get_plan_test_job`    | `GET /api/v1/plans/<id>/test-jobs/<job_id>`          |
| Update plan test job  | `pms plan test-job update <plan_id> <job_id>`  | `mcp__pms__update_plan_test_job` | `PATCH /api/v1/plans/<id>/test-jobs/<job_id>`        |
| Delete plan test job  | `pms plan test-job delete <plan_id> <job_id>`  | `mcp__pms__delete_plan_test_job` | `DELETE /api/v1/plans/<id>/test-jobs/<job_id>`       |
| Restore plan test job | `pms plan test-job restore <plan_id> <job_id>` | -                                | `POST /api/v1/plans/<id>/test-jobs/<job_id>/restore` |
| Run plan test job     | `pms plan test-job run <plan_id> <job_id>`     | `mcp__pms__run_plan_test_job`    | `POST /api/v1/plans/<id>/test-jobs/<job_id>/run`     |

### Tasks + Execution

| Action                 | CLI                                         | MCP Tool                                  | API Endpoint                                     |
| ---------------------- | ------------------------------------------- | ----------------------------------------- | ------------------------------------------------ |
| Create task            | `pms task create "<project>" "<title>"`     | `mcp__pms__create_task`                   | `POST /api/v1/tasks`                             |
| List tasks             | `pms task list --project "<project>"`       | `mcp__pms__list_tasks`                    | `GET /api/v1/tasks`                              |
| Get task               | `pms task show <id>`                        | -                                         | `GET /api/v1/tasks/<id>`                         |
| Update task            | `pms task update <id>`                      | `mcp__pms__update_task`                   | `PATCH /api/v1/tasks/<id>`                       |
| Start task             | `pms task start <id>`                       | `mcp__pms__start_task`                    | `POST /api/v1/tasks/<id>/start`                  |
| Review task            | `pms task review <id>`                      | -                                         | `POST /api/v1/tasks/<id>/review`                 |
| Complete task          | `pms task complete <id>`                    | `mcp__pms__complete_task`                 | `POST /api/v1/tasks/<id>/complete`               |
| Reopen task            | `pms task reopen <id>`                      | -                                         | `POST /api/v1/tasks/<id>/reopen`                 |
| Cancel task            | `pms task cancel <id>`                      | -                                         | `POST /api/v1/tasks/<id>/cancel`                 |
| Block task             | `pms task block <id>`                       | `mcp__pms__block_task`                    | `POST /api/v1/tasks/<id>/block`                  |
| Unblock task           | `pms task unblock <id>`                     | `mcp__pms__unblock_task`                  | `POST /api/v1/tasks/<id>/unblock`                |
| Task progress          | `pms task progress <id> <pct> "<msg>"`      | `mcp__pms__update_task_progress`          | `POST /api/v1/tasks/<id>/progress`               |
| Task progress timeline | -                                           | -                                         | `GET /api/v1/tasks/<id>/progress/timeline`       |
| Task evidence add      | `pms task evidence add <id> <type> <ref>`   | `mcp__pms__add_task_evidence`             | `POST /api/v1/tasks/<id>/evidence`               |
| Task evidence list     | `pms task evidence list <id>`               | -                                         | `GET /api/v1/tasks/<id>/evidence`                |
| Task checkout          | `pms task checkout <id> --agent-id <agent>` | `mcp__pms__checkout_task`                 | `POST /api/v1/tasks/<id>/checkout`               |
| Checkout renew         | `pms task renew <id> --agent-id <agent>`    | `mcp__pms__renew_task_checkout`           | `POST /api/v1/tasks/<id>/checkout/renew`         |
| Checkout release       | `pms task release <id> --agent-id <agent>`  | `mcp__pms__release_task_checkout`         | `POST /api/v1/tasks/<id>/checkout/release`       |
| Checkout force release | `pms task force-release <id>`               | -                                         | `POST /api/v1/tasks/<id>/checkout/force-release` |
| Task dependencies add  | `pms task dep add <task> <depends_on>`      | `mcp__pms__add_task_dependency`           | `POST /api/v1/tasks/<id>/dependencies`           |
| Task dependency graph  | `pms task graph <id>`                       | -                                         | `GET /api/v1/tasks/<id>/graph`                   |
| Task tree (project)    | `pms task tree --project "<project>"`       | `mcp__pms__get_task_tree`                 | `GET /api/v1/tasks/tree?project_id=<id>`         |
| Duplicate detection    | `pms task duplicates`                       | `mcp__pms__find_duplicate_tasks`          | `GET /api/v1/tasks/duplicates`                   |
| Duplicate preview      | `pms task merge-preview`                    | `mcp__pms__preview_merge_duplicate_tasks` | `POST /api/v1/tasks/duplicates/preview`          |
| Duplicate merge        | `pms task merge-duplicates`                 | `mcp__pms__merge_duplicate_tasks`         | `POST /api/v1/tasks/duplicates/merge`            |
| Proof bundle           | `pms task proof-bundle <id>`                | `mcp__pms__get_task_proof_bundle`         | `GET /api/v1/tasks/<id>/proof-bundle`            |
| Proof bundle search    | `pms task proof-bundle-search`              | -                                         | `GET /api/v1/evidence/bundles`                   |

Paginated query/list wrapper conventions (for list/search endpoints such as
`/organizations`, `/teams`, `/portfolios`, `/programs`, `/products`,
`/projects`, `/goals`, `/goals/{goal_id}/objectives`,
`/objectives/{objective_id}/key-results`, `/plans`, `/queues`, and task query endpoints):

- `items`, `total_count`, `offset`, `limit`
- `links` (self/next + `guide`; endpoint-specific related links may be included)
- `next_steps` (practical follow-up API calls)
- `params` (echo of active filter/pagination inputs)

### Workflows + Gates

| Action               | CLI                                                        | MCP Tool                              | API Endpoint                                  |
| -------------------- | ---------------------------------------------------------- | ------------------------------------- | --------------------------------------------- |
| List workflows       | `pms workflow list`                                        | -                                     | `GET /api/v1/workflows`                       |
| Show workflow        | `pms workflow show <id>`                                   | -                                     | `GET /api/v1/workflows/<id>`                  |
| Assign workflow      | `pms workflow assign <id> sdlc concept --entity-type task` | `mcp__pms__assign_workflow`           | `POST /api/v1/tasks/<id>/workflow/assign`     |
| Transition workflow  | `pms workflow transition <id> idea --by <user>`            | `mcp__pms__transition_workflow`       | `POST /api/v1/tasks/<id>/workflow/transition` |
| Evidence gate add    | `pms evidence gate add ...`                                | `mcp__pms__create_evidence_gate_rule` | `POST /api/v1/evidence/gates`                 |
| Evidence gate list   | `pms evidence gate list ...`                               | `mcp__pms__list_evidence_gate_rules`  | `GET /api/v1/evidence/gates`                  |
| Evidence gate delete | `pms evidence gate delete <id>`                            | `mcp__pms__delete_evidence_gate_rule` | `DELETE /api/v1/evidence/gates/<id>`          |
| Label gate add       | `pms label gate add ...`                                   | -                                     | `POST /api/v1/labels/gates`                   |
| Label gate list      | `pms label gate list ...`                                  | -                                     | `GET /api/v1/labels/gates`                    |
| Label gate delete    | `pms label gate delete <id>`                               | -                                     | `DELETE /api/v1/labels/gates/<id>`            |

### Labels

| Action                  | CLI                                    | MCP Tool | API Endpoint                                  |
| ----------------------- | -------------------------------------- | -------- | --------------------------------------------- |
| Create label category   | `pms label category create "<name>"`   | -        | `POST /api/v1/labels/categories`              |
| List label categories   | `pms label category list`              | -        | `GET /api/v1/labels/categories`               |
| Show label category     | `pms label category show <id>`         | -        | `GET /api/v1/labels/categories/<id>`          |
| Update label category   | `pms label category update <id>`       | -        | `PATCH /api/v1/labels/categories/<id>`        |
| Delete label category   | `pms label category delete <id>`       | -        | `DELETE /api/v1/labels/categories/<id>`       |
| Restore label category  | `pms label category restore <id>`      | -        | `POST /api/v1/labels/categories/<id>/restore` |
| Create label            | `pms label create "<name>"`            | -        | `POST /api/v1/labels`                         |
| List labels             | `pms label list`                       | -        | `GET /api/v1/labels`                          |
| Show label              | `pms label show <id>`                  | -        | `GET /api/v1/labels/<id>`                     |
| Update label            | `pms label update <id>`                | -        | `PATCH /api/v1/labels/<id>`                   |
| Delete label            | `pms label delete <id>`                | -        | `DELETE /api/v1/labels/<id>`                  |
| Restore label           | `pms label restore <id>`               | -        | `POST /api/v1/labels/<id>/restore`            |
| Assign label            | `pms label assign <type> <id> <label>` | -        | `POST /api/v1/labels/assignments`             |
| List label assignments  | `pms label list-entity <type> <id>`    | -        | `GET /api/v1/labels/assignments`              |
| Assignment history      | `pms label assignment history <id>`    | -        | `GET /api/v1/labels/assignments/<id>/history` |
| Remove label assignment | `pms label remove <type> <id> <label>` | -        | `DELETE /api/v1/labels/assignments`           |

### Queues (Saved Searches)

| Action        | CLI                                            | MCP Tool                        | API Endpoint                          |
| ------------- | ---------------------------------------------- | ------------------------------- | ------------------------------------- |
| Create queue  | `pms queue create "<name>" --filters '<json>'` | `mcp__pms__create_saved_search` | `POST /api/v1/queues`                 |
| List queues   | `pms queue list`                               | `mcp__pms__list_saved_searches` | `GET /api/v1/queues`                  |
| Show queue    | `pms queue show <id>`                          | `mcp__pms__get_saved_search`    | `GET /api/v1/queues/<id>`             |
| Update queue  | `pms queue update <id>`                        | `mcp__pms__update_saved_search` | `PUT /api/v1/queues/<id>`             |
| Delete queue  | `pms queue delete <id>`                        | `mcp__pms__delete_saved_search` | `DELETE /api/v1/queues/<id>`          |
| Restore queue | `pms queue restore <id>`                       | -                               | `POST /api/v1/queues/<id>/restore`    |
| Run queue     | `pms queue run <id>`                           | `mcp__pms__run_saved_search`    | `GET /api/v1/queues/<id>/run`         |
| Queue presets | `pms queue presets`                            | `mcp__pms__list_queue_presets`  | `GET /api/v1/queues/presets`          |
| Queue preset  | -                                              | `mcp__pms__get_queue_preset`    | `GET /api/v1/queues/presets/<preset>` |

### Work Snapshots + Daily Reviews

| Action          | CLI                                                       | MCP Tool                                | API Endpoint                                      |
| --------------- | --------------------------------------------------------- | --------------------------------------- | ------------------------------------------------- |
| Work snapshot   | `pms work snapshot --scope-type project --scope "<name>"` | `mcp__pms__get_work_snapshot`           | `GET /api/v1/work-snapshots/<scope>/<id>`         |
| Snapshot review | `pms work review --scope-type project --scope "<name>"`   | `mcp__pms__mark_work_snapshot_reviewed` | `POST /api/v1/work-snapshots/<scope>/<id>/review` |
| Daily review    | `pms work daily --scope-type project --scope "<name>"`    | `mcp__pms__get_work_daily`              | `GET /api/v1/work-snapshots/<scope>/<id>/daily`   |

### Timelines + Revisions

| Action            | CLI                                 | MCP Tool | API Endpoint                                   |
| ----------------- | ----------------------------------- | -------- | ---------------------------------------------- |
| Workflow timeline | `pms timeline workflow <type> <id>` | -        | `GET /api/v1/transitions/workflow/<type>/<id>` |
| Status timeline   | `pms timeline status <type> <id>`   | -        | `GET /api/v1/transitions/status/<type>/<id>`   |
| Revision diff     | `pms revision diff <type> <id>`     | -        | `GET /api/v1/revisions/<type>/<id>/diff`       |
| Revision bundle   | `pms revision bundle <type> <id>`   | -        | `GET /api/v1/revisions/<type>/<id>/bundle`     |

### Test Runs + Retention

| Action                   | CLI                                      | MCP Tool                           | API Endpoint                                             |
| ------------------------ | ---------------------------------------- | ---------------------------------- | -------------------------------------------------------- |
| Create test run record   | `pms test run <path>`                    | -                                  | `POST /api/v1/test-runs`                                 |
| List test runs           | `pms test list`                          | `mcp__pms__list_test_runs`         | `GET /api/v1/test-runs`                                  |
| Show test run            | `pms test show <id>`                     | `mcp__pms__get_test_run`           | `GET /api/v1/test-runs/<id>`                             |
| Prune test runs          | `pms test prune`                         | `mcp__pms__prune_test_runs`        | `POST /api/v1/test-runs/prune`                           |
| Retention summary        | `pms test retention`                     | `mcp__pms__get_test_run_retention` | `GET /api/v1/test-runs/retention`                        |
| List retention policies  | `pms test retention-policy list`         | -                                  | `GET /api/v1/test-runs/retention/policies`               |
| Set retention policy     | `pms test retention-policy set`          | -                                  | `POST /api/v1/test-runs/retention/policies`              |
| Show retention policy    | `pms test retention-policy show <id>`    | -                                  | `GET /api/v1/test-runs/retention/policies/<id>`          |
| Update retention policy  | -                                        | -                                  | `PATCH /api/v1/test-runs/retention/policies/<id>`        |
| Archive retention policy | `pms test retention-policy archive <id>` | -                                  | `POST /api/v1/test-runs/retention/policies/<id>/archive` |
| Restore retention policy | `pms test retention-policy restore <id>` | -                                  | `POST /api/v1/test-runs/retention/policies/<id>/restore` |

### Auth

| Action         | CLI                     | MCP Tool | API Endpoint                             |
| -------------- | ----------------------- | -------- | ---------------------------------------- |
| List scopes    | `pms auth scopes`       | -        | `GET /api/v1/auth/scopes`                |
| Init admin key | `pms auth init`         | -        | `POST /api/v1/auth/init`                 |
| Create key     | `pms auth create`       | -        | `POST /api/v1/auth/keys`                 |
| List keys      | `pms auth list`         | -        | `GET /api/v1/auth/keys`                  |
| Get key        | `pms auth get <id>`     | -        | `GET /api/v1/auth/keys/<id>`             |
| Revoke key     | `pms auth revoke <id>`  | -        | `DELETE /api/v1/auth/keys/<id>`          |
| Restore key    | `pms auth restore <id>` | -        | `POST /api/v1/auth/keys/<id>/restore`    |
| Deactivate key | -                       | -        | `POST /api/v1/auth/keys/<id>/deactivate` |

---

## Endpoint Catalog (high-coverage reference)

This section is intentionally workflow-oriented and does not enumerate every
route. For the full canonical list, use the live OpenAPI docs (`/docs`,
`/openapi.json`).

For an always-generated markdown inventory checked into the repo, see
[`docs/API_ENDPOINT_CATALOG.md`](API_ENDPOINT_CATALOG.md).

To inspect the current route inventory at runtime:

```bash
PMS_LOG_DIR=$PWD/.tmp/pms-logs PMS_DATA_DIR=$PWD/.tmp/pms-data \
  ./.venv/bin/python -c 'from pms.api.app import app; routes=[r.path for r in app.routes if getattr(r,"methods",None) and r.path.startswith("/api/v1")]; print("api_v1_total", len(routes)); print("api_v1_without_health", len([p for p in routes if p != "/api/v1/health"]))'
```

See [`docs/API_REFERENCE.md`](API_REFERENCE.md) for request/response details and auth scopes.

### Discoverability

- `GET /api/v1/discoverability/graph` - Entry-point + continuation graph
- `GET /api/v1/observability/overview` - Unified live-state observability snapshot

Use query params `include_entry_points`, `include_observability`,
`include_scenarios`, `max_next_steps`, and `path_contains` to tune map depth
and focus. Responses include `nodes`, `edges`, `scenarios`, plus
`links`/`next_steps`/`params` for iterative discovery loops.

Observability overview supports `include_rollups`, `include_queues`,
`include_lineage`, `include_retention`, `include_event_timeline`,
`queue_limit`, `lineage_limit`, `retention_limit`, and `timeline_days`.
Use this endpoint as the first machine-readable "what is happening now?"
checkpoint before drilling into dashboards, queues, snapshots, or lineage.
Responses now include `attention_summary`, `attention_items`,
`top_risks_now`, `stalled_flows`, `needs_review`, and
`recommended_actions` so operators and automation can jump directly to the
next action instead of inferring it from raw rollups alone.

### Organizations

- `POST /api/v1/organizations` - Create
- `GET /api/v1/organizations` - List
- `GET /api/v1/organizations/dashboard` - Dashboard rollups
- `GET /api/v1/organizations/{id}` - Get
- `PATCH /api/v1/organizations/{id}` - Update
- `GET /api/v1/organizations/{id}/summary` - Rollup summary

Dashboard rollups include totals for teams/portfolios/programs/projects/goals/
objectives/tasks plus blocked task counts. Use the optional `status`, `limit`,
and `offset` query params to scope results. Add `include_digest=true`,
`include_next_actions=true`, and `next_limit=<n>` to attach review deltas and
ready-task suggestions. Add `include_evidence=true` and `include_retention=true`
to include evidence totals and test retention usage per organization.
Dashboard responses include `links`, `next_steps`, and `params` to preserve
query context and surface direct continuation calls.
Organization summary responses (`GET /api/v1/organizations/{id}/summary`) also
include `links`, `next_steps`, and `params` for handoff into dashboards and
work-daily views.

### Teams

- `POST /api/v1/teams` - Create
- `GET /api/v1/teams` - List
- `GET /api/v1/teams/{id}` - Get
- `PATCH /api/v1/teams/{id}` - Update

### Portfolios

- `POST /api/v1/portfolios` - Create
- `GET /api/v1/portfolios` - List
- `GET /api/v1/portfolios/dashboard` - Dashboard rollups
- `GET /api/v1/portfolios/{id}` - Get
- `PATCH /api/v1/portfolios/{id}` - Update
- `GET /api/v1/portfolios/{id}/summary` - Rollup summary

Portfolio dashboards accept `org_id`, `status`, `limit`, and `offset` query
params and return rollup totals plus per-portfolio activity/transition stamps.
Use `include_digest`, `include_next_actions`, `include_evidence`, and
`include_retention` for enriched evidence and retention summaries.
Dashboard responses include `links`, `next_steps`, and `params` to preserve
query context and surface direct continuation calls.
Portfolio summary responses (`GET /api/v1/portfolios/{id}/summary`) include the
same continuation metadata for dashboard/work-daily follow-ups.

### Programs

- `POST /api/v1/programs` - Create
- `GET /api/v1/programs` - List
- `GET /api/v1/programs/dashboard` - Dashboard rollups
- `GET /api/v1/programs/{id}` - Get
- `PATCH /api/v1/programs/{id}` - Update
- `GET /api/v1/programs/{id}/summary` - Rollup summary

Program dashboards accept `org_id`, `portfolio_id`, `status`, `limit`, and
`offset` query params and return rollup totals plus per-program activity/
transition stamps. Add `include_digest=true`, `include_next_actions=true`, and
`next_limit=<n>` to include review deltas and ready-task suggestions.
Add `include_evidence=true` and `include_retention=true` to attach evidence and
retention usage summaries per program.
Dashboard responses include `links`, `next_steps`, and `params` to preserve
query context and surface direct continuation calls.
Program summary responses (`GET /api/v1/programs/{id}/summary`) include the same
continuation metadata for dashboard/work-daily follow-ups.

### Work Snapshots

- `GET /api/v1/work-snapshots/{scope_type}/{scope_id}` - Unified snapshot
- `GET /api/v1/work-snapshots/{scope_type}/{scope_id}/daily` - Daily review summary
- `POST /api/v1/work-snapshots/{scope_type}/{scope_id}/review` - Mark reviewed

Work snapshot scopes accept `organization`, `portfolio`, `program`, or `project`.
Snapshots now include continuation metadata (`links`, `next_steps`, `params`) and
`review_history_preview` so API consumers can drive “what next” UX without
hardcoding route knowledge. The daily payload now includes `api_links` and
`next_steps_api` alongside CLI-oriented links.

### Agent Loops

- `GET /api/v1/agent-loops` - List loops
- `GET /api/v1/agent-loops/{id}` - Get loop summary
- `GET /api/v1/agent-loops/{id}/messages` - Loop transcript/messages
- `POST /api/v1/agent-loops/{id}/cancel` - Request cancellation

Use agent loops for Ralph-style iteration with stored transcripts and loop state.
Loop list/message responses include `links`, `next_steps`, and `params`, with
`limit`/`offset` pagination support for high-volume transcript browsing.

### Products

- `POST /api/v1/products` - Create
- `GET /api/v1/products` - List
- `GET /api/v1/products/{id}` - Get
- `GET /api/v1/products/{id}/summary` - Get with stats
- `PATCH /api/v1/products/{id}` - Update
- `POST /api/v1/products/{id}/archive` - Archive

Product create/update accept `tags` alongside `name`, `description`, `vision`,
`repository_url`, `owner`, `product_type`, and `status`.

### Projects

- `GET /api/v1/dashboard` - Instance-wide project operator dashboard
- `POST /api/v1/projects` - Create
- `GET /api/v1/projects` - List
- `GET /api/v1/projects/{id}` - Get
- `GET /api/v1/projects/{id}/summary` - Get with stats
- `GET /api/v1/projects/{id}/operator-overview` - Unified operator wrapper for summary + daily + lineage + history
- `PATCH /api/v1/projects/{id}` - Update

Project create/update accepts optional scope links: `org_id`, `portfolio_id`, `program_id`, and `product_id`.
The instance dashboard returns lifecycle-aware `active_projects`,
`recently_completed_projects`, freshest visible activity/transition pointers,
and terminal/completion context for the no-active-work case.

### Tasks

- `POST /api/v1/tasks` - Create
- `GET /api/v1/tasks` - List
- `GET /api/v1/tasks/search` - Search (rich filters)
- `GET /api/v1/tasks/ready` - Ready tasks (unblocked)
- `GET /api/v1/tasks/stale` - Stale tasks
- `GET /api/v1/tasks/duplicates` - Duplicate groups
- `POST /api/v1/tasks/duplicates/preview` - Preview duplicate merge
- `POST /api/v1/tasks/duplicates/merge` - Merge duplicates
- `GET /api/v1/tasks/tree` - Task tree for a project
- `GET /api/v1/tasks/{id}` - Get
- `POST /api/v1/tasks/{id}/start` - Start
- `POST /api/v1/tasks/{id}/complete` - Complete (notes via query param)
- `POST /api/v1/tasks/{id}/block` - Block
- `POST /api/v1/tasks/{id}/unblock` - Unblock
- `POST /api/v1/tasks/{id}/review` - Submit for review
- `POST /api/v1/tasks/{id}/reopen` - Reopen
- `POST /api/v1/tasks/{id}/cancel` - Cancel
- `PATCH /api/v1/tasks/{id}` - Update
- `POST /api/v1/tasks/{id}/dependencies` - Add dependency
- `DELETE /api/v1/tasks/{id}/dependencies/{depends_on_id}` - Remove dependency
- `GET /api/v1/tasks/{id}/graph` - Dependency graph
- `POST /api/v1/tasks/{id}/evidence` - Add evidence (manual)
- `GET /api/v1/tasks/{id}/evidence` - List evidence
- `GET /api/v1/tasks/{id}/proof-bundle` - Proof bundle export
- `GET /api/v1/evidence/bundles` - Search proof bundles
- `GET /api/v1/revisions/{entity_type}/{entity_id}/bundle` - Revision history bundle
- `GET /api/v1/revisions/{entity_type}/{entity_id}/diff` - Revision diff

### Custom Fields

- `POST /api/v1/custom-fields` - Create custom field definition
- `GET /api/v1/custom-fields` - List custom field definitions
- `GET /api/v1/custom-fields/{id}` - Get custom field definition
- `PATCH /api/v1/custom-fields/{id}` - Update custom field definition
- `DELETE /api/v1/custom-fields/{id}` - Archive custom field definition
- `POST /api/v1/custom-fields/{id}/restore` - Restore custom field definition
- `POST /api/v1/custom-fields/{id}/values` - Set custom field value
- `GET /api/v1/custom-fields/values` - List custom field values for an entity

### Comments + Watchers

- `POST /api/v1/comments` - Add comment to an entity
- `GET /api/v1/comments` - List comments for an entity
- `GET /api/v1/comments/{id}` - Get comment
- `DELETE /api/v1/comments/{id}` - Archive comment
- `POST /api/v1/comments/{id}/restore` - Restore comment
- `POST /api/v1/watchers` - Add watcher
- `GET /api/v1/watchers` - List watchers
- `DELETE /api/v1/watchers` - Remove watcher
- `POST /api/v1/watchers/{id}/restore` - Restore watcher

Comment/watcher list responses include `links`, `next_steps`, and `params` so
clients can continue from thread view to watcher management without extra routing logic.

### Automation Rules

- `POST /api/v1/automation/rules` - Create automation rule
- `GET /api/v1/automation/rules` - List automation rules
- `GET /api/v1/automation/rules/{id}` - Get automation rule
- `PATCH /api/v1/automation/rules/{id}` - Update automation rule
- `DELETE /api/v1/automation/rules/{id}` - Archive automation rule
- `POST /api/v1/automation/rules/{id}/restore` - Restore automation rule
- `POST /api/v1/automation/run` - Run automation rules for an event
- `GET /api/v1/automation/rules/{id}/runs` - List automation rule runs

Automation rule list/run-history responses include `links`, `next_steps`, and
`params`, with `limit`/`offset` support on rule listing for large rule sets.

### Queues

- `POST /api/v1/queues` - Create saved queue
- `GET /api/v1/queues` - List saved queues
- `GET /api/v1/queues/{id}` - Get saved queue
- `PUT /api/v1/queues/{id}` - Update saved queue
- `DELETE /api/v1/queues/{id}` - Delete saved queue
- `GET /api/v1/queues/{id}/run` - Run saved queue
- `GET /api/v1/queues/presets` - List smart queue presets
- `GET /api/v1/queues/presets/{preset}` - Get preset queue

Queue preset responses include `links`, `next_steps`, and `params` so clients can
page and pivot into task/query endpoints without hardcoding routing logic.

### Test Runs

- `POST /api/v1/test-runs` - Create test run record
- `GET /api/v1/test-runs` - List test runs
- `GET /api/v1/test-runs/retention` - Retention usage summary
- `GET /api/v1/test-runs/{id}` - Get test run details
- `POST /api/v1/test-runs/prune` - Prune stored test outputs
- `GET /api/v1/test-runs/retention/policies` - List retention policies
- `POST /api/v1/test-runs/retention/policies` - Create/update retention policy
- `GET /api/v1/test-runs/retention/policies/{id}` - Get retention policy
- `PATCH /api/v1/test-runs/retention/policies/{id}` - Update retention policy
- `POST /api/v1/test-runs/retention/policies/{id}/archive` - Archive retention policy
- `POST /api/v1/test-runs/retention/policies/{id}/restore` - Restore retention policy

### Labels

- `POST /api/v1/labels/categories` - Create category
- `GET /api/v1/labels/categories` - List categories
- `GET /api/v1/labels/categories/{id}` - Get category
- `PATCH /api/v1/labels/categories/{id}` - Update category
- `DELETE /api/v1/labels/categories/{id}` - Delete category
- `POST /api/v1/labels` - Create label
- `GET /api/v1/labels` - List labels
- `GET /api/v1/labels/{id}` - Get label
- `PATCH /api/v1/labels/{id}` - Update label
- `DELETE /api/v1/labels/{id}` - Delete label
- `POST /api/v1/labels/assignments` - Assign label
- `GET /api/v1/labels/assignments` - List labels for entity
- `GET /api/v1/labels/assignments/{id}/history` - Label assignment history
- `DELETE /api/v1/labels/assignments` - Remove label assignment
- `POST /api/v1/labels/gates` - Create gate rule
- `GET /api/v1/labels/gates` - List gate rules
- `DELETE /api/v1/labels/gates/{id}` - Delete gate rule

### Evidence Gates

- `POST /api/v1/evidence/gates` - Create evidence gate rule
- `GET /api/v1/evidence/gates` - List evidence gate rules
- `DELETE /api/v1/evidence/gates/{id}` - Delete evidence gate rule

### Goals

- `POST /api/v1/goals` - Create
- `GET /api/v1/goals` - List
- `GET /api/v1/goals/{id}` - Get
- `PATCH /api/v1/goals/{id}` - Update
- `POST /api/v1/goals/{id}/complete` - Complete
- `POST /api/v1/goals/{id}/archive` - Archive
- `GET /api/v1/goals/{id}/summary` - Rollup summary

### Plans

- `POST /api/v1/plans` - Create
- `GET /api/v1/plans` - List
- `GET /api/v1/plans/lineage` - Plan → task → test lineage dashboard
- `GET /api/v1/plans/{id}` - Get
- `PATCH /api/v1/plans/{id}` - Update
- `POST /api/v1/plans/{id}/test-jobs` - Create plan test job
- `GET /api/v1/plans/{id}/test-jobs` - List plan test jobs
- `GET /api/v1/plans/{id}/test-jobs/{job_id}` - Get plan test job
- `PATCH /api/v1/plans/{id}/test-jobs/{job_id}` - Update plan test job
- `DELETE /api/v1/plans/{id}/test-jobs/{job_id}` - Delete plan test job
- `POST /api/v1/plans/{id}/test-jobs/{job_id}/run` - Run plan test job

Plan lineage and plan-test-job list responses include `links`, `next_steps`, and
`params` so clients can page results and jump directly into plan detail/test/proof
operations without hardcoded routing.

### Objectives

- `POST /api/v1/goals/{goal_id}/objectives` - Create
- `GET /api/v1/goals/{goal_id}/objectives` - List
- `GET /api/v1/objectives/{id}` - Get
- `PATCH /api/v1/objectives/{id}` - Update
- `POST /api/v1/objectives/{id}/complete` - Complete
- `POST /api/v1/objectives/{id}/archive` - Archive

### Key Results

- `POST /api/v1/objectives/{objective_id}/key-results` - Create
- `GET /api/v1/objectives/{objective_id}/key-results` - List
- `GET /api/v1/key-results/{id}` - Get
- `PATCH /api/v1/key-results/{id}` - Update
- `POST /api/v1/key-results/{id}/complete` - Complete
- `POST /api/v1/key-results/{id}/archive` - Archive

### Checkout

- `POST /api/v1/tasks/{id}/checkout` - Checkout
- `POST /api/v1/tasks/{id}/checkout/renew` - Renew lease
- `POST /api/v1/tasks/{id}/checkout/release` - Release
- `POST /api/v1/tasks/{id}/checkout/force-release` - Force release
- `GET /api/v1/checkout/available` - Get available
- `GET /api/v1/checkout/status` - List agent checkouts
- `POST /api/v1/checkout/cleanup` - Cleanup expired
- `GET /api/v1/checkout/log` - Checkout audit log

### Progress

- `POST /api/v1/tasks/{id}/progress` - Update
- `GET /api/v1/tasks/{id}/progress/timeline` - Get timeline

### Workflows

- `GET /api/v1/workflows` - List workflows
- `GET /api/v1/workflows/{workflow_ref}` - Workflow details
- `POST /api/v1/tasks/{id}/workflow/assign` - Assign
- `POST /api/v1/tasks/{id}/workflow/transition` - Transition
- `POST /api/v1/goals/{id}/workflow/assign` - Assign
- `POST /api/v1/goals/{id}/workflow/transition` - Transition
- `POST /api/v1/objectives/{id}/workflow/assign` - Assign
- `POST /api/v1/objectives/{id}/workflow/transition` - Transition

### Transition Timelines

- `GET /api/v1/transitions/workflow/{entity_type}/{entity_id}` - Workflow timeline
- `GET /api/v1/transitions/status/{entity_type}/{entity_id}` - Status timeline
  - Optional filters: `triggered_by`, `from_state`, `to_state`, `start_time`, `end_time`, `transition_type`, `label`

### Auth

- `GET /api/v1/auth/scopes` - List available scopes
- `POST /api/v1/auth/init` - Bootstrap first admin key
- `POST /api/v1/auth/keys` - Create API key (admin scope required)
- `GET /api/v1/auth/keys` - List API keys
- `GET /api/v1/auth/keys/{id}` - Get API key
- `DELETE /api/v1/auth/keys/{id}` - Delete API key
- `POST /api/v1/auth/keys/{id}/deactivate` - Deactivate API key

---

## Use Cases

### Distributed Agent Coordination

Multiple AI agents can work on different tasks concurrently:

```python
# Agent 1 checks out task A
POST /api/v1/tasks/taskA/checkout {"agent_session_id": "<agent-session-id>"}

# Agent 2 checks out task B
POST /api/v1/tasks/taskB/checkout {"agent_session_id": "<agent-session-id-2>"}

# Both work simultaneously with exclusive locks
# Heartbeat to keep leases alive
POST /api/v1/tasks/taskA/checkout/renew

# Release when done
POST /api/v1/tasks/taskA/checkout/release

# Force release or cleanup if a worker crashes
POST /api/v1/tasks/taskA/checkout/force-release?released_by=admin
POST /api/v1/checkout/cleanup
```

### Real-Time Progress Dashboard

Monitor task progress in real-time:

```python
# Agent updates progress
POST /api/v1/tasks/<task-id>/progress {
  "percent_complete": 75,
  "status_message": "Testing complete, deploying"
}

# Dashboard polls timeline
GET /api/v1/tasks/<task-id>/progress/timeline
# Returns: velocity, ETA, trend (accelerating/stable/decelerating)
```

### Goal/OKR Tracking

Model goals, objectives, and key results with rollups:

```python
# Create goal
POST /api/v1/goals { "name": "Launch V1", "horizon": "short_term" }

# Create objective
POST /api/v1/goals/<goal-id>/objectives { "name": "Complete onboarding flow" }

# Create key result
POST /api/v1/objectives/<objective-id>/key-results {
  "name": "Activation rate",
  "current_value": 35,
  "target_value": 60,
  "unit": "%"
}

# View rollup summary
GET /api/v1/goals/<goal-id>/summary
```

### Workflow Automation

Manage task lifecycle through workflows:

```python
# Assign SDLC workflow
POST /api/v1/tasks/<task-id>/workflow/assign {
  "workflow_name": "sdlc",
  "initial_state": "implementing"
}

# Progress through states
POST /api/v1/tasks/<task-id>/workflow/transition {
  "to_state": "code_review",
  "triggered_by": "developer_alice"
}

# Production requires approval
POST /api/v1/tasks/<task-id>/workflow/transition {
  "to_state": "production",
  "triggered_by": "developer_alice",
  "approved_by": "release_manager"
}
```

---

## Performance

**Measured**:

- Server startup: < 1 second
- Request latency: ~50ms average
- Concurrent requests: 100+ supported
- Database: Persistent connection (no reconnection overhead)

**Scalability**:

- SQLite: Good for single server, development
- PostgreSQL: Enterprise scale with connection pooling

---

## Client Integration

### Python Client

```python
import httpx

client = httpx.AsyncClient(base_url="http://127.0.0.1:27541")

# Create task
response = await client.post("/api/v1/tasks", json={
    "project_id": "<project-id>",
    "title": "API Task",
    "complexity_points": 50
})

task = response.json()
print(f"Created: {task['id']}")
```

### Compiled Client

Fast server-backed binary client for repeated reads:

```bash
./scripts/install_pms_client.sh
export PATH="$PWD/.bin:$PATH"
export PMS_API_KEY="$(cat .pms-admin-key)"
pms-client --server http://127.0.0.1:27541 task list --project-id <project-id>
```

This path is fast when the PMS API server is already running. It is not a
direct SQLite reader.

---

## Documentation

- **Machine Interface Guide**: [`docs/MACHINE_INTERFACE_GUIDE.md`](MACHINE_INTERFACE_GUIDE.md) - Progressive machine-first usage model across CLI, API, and graph exports
- **API Reference**: [`docs/API_REFERENCE.md`](API_REFERENCE.md) - Manually curated endpoint reference with practical request examples
- **API Endpoint Catalog**: [`docs/API_ENDPOINT_CATALOG.md`](API_ENDPOINT_CATALOG.md) - Generated route inventory from live app routes
- **API Response Contracts**: [`docs/API_RESPONSE_CONTRACTS.md`](API_RESPONSE_CONTRACTS.md) - Generated request/response schema contract index (endpoint + field-level types)
- **API Reference Audit**: `uv run python scripts/audit_api_reference.py --check --api-reference docs/API_REFERENCE.md` - Coverage check against live `/api/v1/*` routes (no overwrite)
- **API Reference Depth Audit**: `uv run python scripts/audit_api_reference_depth.py --check --api-reference docs/API_REFERENCE.md --contracts docs/API_RESPONSE_CONTRACTS.md` - Response documentation depth check (local examples/notes + contract-backed coverage)
- **OpenAPI Schema**: http://127.0.0.1:27541/openapi.json
- **Swagger UI**: http://127.0.0.1:27541/docs (interactive)

---

**Status**: Stable server-backed interface with audited route coverage
**Tests**: API endpoints validated in `tests/api/`
**Deployment**: See [`docs/SERVER_DEPLOYMENT.md`](SERVER_DEPLOYMENT.md) for the supported runtime contract and operator guidance
