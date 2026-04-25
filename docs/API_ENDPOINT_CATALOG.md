# API Endpoint Catalog

Generated from live route definitions in `pms.api.app`.

Regenerate:

```bash
uv run python scripts/generate_api_endpoint_catalog.py
```

## Summary

- `/api/v1/*` method+path routes: **206**
- `/api/v1/*` routes excluding `/api/v1/health`: **205**

## `actors` (5)

- `GET /api/v1/actors`
- `GET /api/v1/actors/{actor}`
- `POST /api/v1/actors`
- `POST /api/v1/actors/{actor}/aliases`
- `POST /api/v1/actors/{actor}/memberships`

## `agent-loops` (4)

- `GET /api/v1/agent-loops`
- `GET /api/v1/agent-loops/{loop_id}`
- `GET /api/v1/agent-loops/{loop_id}/messages`
- `POST /api/v1/agent-loops/{loop_id}/cancel`

## `auth` (8)

- `DELETE /api/v1/auth/keys/{key_id}`
- `GET /api/v1/auth/keys`
- `GET /api/v1/auth/keys/{key_id}`
- `GET /api/v1/auth/scopes`
- `POST /api/v1/auth/init`
- `POST /api/v1/auth/keys`
- `POST /api/v1/auth/keys/{key_id}/deactivate`
- `POST /api/v1/auth/keys/{key_id}/restore`

## `automation` (8)

- `DELETE /api/v1/automation/rules/{rule_id}`
- `GET /api/v1/automation/rules`
- `GET /api/v1/automation/rules/{rule_id}`
- `GET /api/v1/automation/rules/{rule_id}/runs`
- `PATCH /api/v1/automation/rules/{rule_id}`
- `POST /api/v1/automation/rules`
- `POST /api/v1/automation/rules/{rule_id}/restore`
- `POST /api/v1/automation/run`

## `checkout` (4)

- `GET /api/v1/checkout/available`
- `GET /api/v1/checkout/log`
- `GET /api/v1/checkout/status`
- `POST /api/v1/checkout/cleanup`

## `comments` (5)

- `DELETE /api/v1/comments/{comment_id}`
- `GET /api/v1/comments`
- `GET /api/v1/comments/{comment_id}`
- `POST /api/v1/comments`
- `POST /api/v1/comments/{comment_id}/restore`

## `custom-fields` (9)

- `DELETE /api/v1/custom-fields/{field_id}`
- `GET /api/v1/custom-fields`
- `GET /api/v1/custom-fields/values`
- `GET /api/v1/custom-fields/{field_id}`
- `GET /api/v1/custom-fields/{field_id}/values`
- `PATCH /api/v1/custom-fields/{field_id}`
- `POST /api/v1/custom-fields`
- `POST /api/v1/custom-fields/{field_id}/restore`
- `POST /api/v1/custom-fields/{field_id}/values`

## `dashboard` (1)

- `GET /api/v1/dashboard`

## `discoverability` (1)

- `GET /api/v1/discoverability/graph`

## `evidence` (4)

- `DELETE /api/v1/evidence/gates/{rule_id}`
- `GET /api/v1/evidence/bundles`
- `GET /api/v1/evidence/gates`
- `POST /api/v1/evidence/gates`

## `goals` (11)

- `GET /api/v1/goals`
- `GET /api/v1/goals/{goal_id}`
- `GET /api/v1/goals/{goal_id}/objectives`
- `GET /api/v1/goals/{goal_id}/summary`
- `PATCH /api/v1/goals/{goal_id}`
- `POST /api/v1/goals`
- `POST /api/v1/goals/{goal_id}/archive`
- `POST /api/v1/goals/{goal_id}/complete`
- `POST /api/v1/goals/{goal_id}/objectives`
- `POST /api/v1/goals/{goal_id}/workflow/assign`
- `POST /api/v1/goals/{goal_id}/workflow/transition`

## `health` (1)

- `GET /api/v1/health`

## `key-results` (4)

- `GET /api/v1/key-results/{key_result_id}`
- `PATCH /api/v1/key-results/{key_result_id}`
- `POST /api/v1/key-results/{key_result_id}/archive`
- `POST /api/v1/key-results/{key_result_id}/complete`

## `labels` (19)

- `DELETE /api/v1/labels/assignments`
- `DELETE /api/v1/labels/categories/{category_id}`
- `DELETE /api/v1/labels/gates/{rule_id}`
- `DELETE /api/v1/labels/{label_id}`
- `GET /api/v1/labels`
- `GET /api/v1/labels/assignments`
- `GET /api/v1/labels/assignments/{assignment_id}/history`
- `GET /api/v1/labels/categories`
- `GET /api/v1/labels/categories/{category_id}`
- `GET /api/v1/labels/gates`
- `GET /api/v1/labels/{label_id}`
- `PATCH /api/v1/labels/categories/{category_id}`
- `PATCH /api/v1/labels/{label_id}`
- `POST /api/v1/labels`
- `POST /api/v1/labels/assignments`
- `POST /api/v1/labels/categories`
- `POST /api/v1/labels/categories/{category_id}/restore`
- `POST /api/v1/labels/gates`
- `POST /api/v1/labels/{label_id}/restore`

## `objectives` (8)

- `GET /api/v1/objectives/{objective_id}`
- `GET /api/v1/objectives/{objective_id}/key-results`
- `PATCH /api/v1/objectives/{objective_id}`
- `POST /api/v1/objectives/{objective_id}/archive`
- `POST /api/v1/objectives/{objective_id}/complete`
- `POST /api/v1/objectives/{objective_id}/key-results`
- `POST /api/v1/objectives/{objective_id}/workflow/assign`
- `POST /api/v1/objectives/{objective_id}/workflow/transition`

## `observability` (1)

- `GET /api/v1/observability/overview`

## `organizations` (6)

- `GET /api/v1/organizations`
- `GET /api/v1/organizations/dashboard`
- `GET /api/v1/organizations/{org_id}`
- `GET /api/v1/organizations/{org_id}/summary`
- `PATCH /api/v1/organizations/{org_id}`
- `POST /api/v1/organizations`

## `plans` (12)

- `DELETE /api/v1/plans/{plan_id}/test-jobs/{job_id}`
- `GET /api/v1/plans`
- `GET /api/v1/plans/lineage`
- `GET /api/v1/plans/{plan_id}`
- `GET /api/v1/plans/{plan_id}/test-jobs`
- `GET /api/v1/plans/{plan_id}/test-jobs/{job_id}`
- `PATCH /api/v1/plans/{plan_id}`
- `PATCH /api/v1/plans/{plan_id}/test-jobs/{job_id}`
- `POST /api/v1/plans`
- `POST /api/v1/plans/{plan_id}/test-jobs`
- `POST /api/v1/plans/{plan_id}/test-jobs/{job_id}/restore`
- `POST /api/v1/plans/{plan_id}/test-jobs/{job_id}/run`

## `portfolios` (6)

- `GET /api/v1/portfolios`
- `GET /api/v1/portfolios/dashboard`
- `GET /api/v1/portfolios/{portfolio_id}`
- `GET /api/v1/portfolios/{portfolio_id}/summary`
- `PATCH /api/v1/portfolios/{portfolio_id}`
- `POST /api/v1/portfolios`

## `products` (6)

- `GET /api/v1/products`
- `GET /api/v1/products/{product_id}`
- `GET /api/v1/products/{product_id}/summary`
- `PATCH /api/v1/products/{product_id}`
- `POST /api/v1/products`
- `POST /api/v1/products/{product_id}/archive`

## `programs` (6)

- `GET /api/v1/programs`
- `GET /api/v1/programs/dashboard`
- `GET /api/v1/programs/{program_id}`
- `GET /api/v1/programs/{program_id}/summary`
- `PATCH /api/v1/programs/{program_id}`
- `POST /api/v1/programs`

## `projects` (6)

- `GET /api/v1/projects`
- `GET /api/v1/projects/{project_id}`
- `GET /api/v1/projects/{project_id}/operator-overview`
- `GET /api/v1/projects/{project_id}/summary`
- `PATCH /api/v1/projects/{project_id}`
- `POST /api/v1/projects`

## `queues` (9)

- `DELETE /api/v1/queues/{queue_id}`
- `GET /api/v1/queues`
- `GET /api/v1/queues/presets`
- `GET /api/v1/queues/presets/{preset}`
- `GET /api/v1/queues/{queue_id}`
- `GET /api/v1/queues/{queue_id}/run`
- `POST /api/v1/queues`
- `POST /api/v1/queues/{queue_id}/restore`
- `PUT /api/v1/queues/{queue_id}`

## `revisions` (2)

- `GET /api/v1/revisions/{entity_type}/{entity_id}/bundle`
- `GET /api/v1/revisions/{entity_type}/{entity_id}/diff`

## `tasks` (33)

- `DELETE /api/v1/tasks/{task_id}/dependencies/{depends_on_id}`
- `GET /api/v1/tasks`
- `GET /api/v1/tasks/duplicates`
- `GET /api/v1/tasks/ready`
- `GET /api/v1/tasks/search`
- `GET /api/v1/tasks/stale`
- `GET /api/v1/tasks/tree`
- `GET /api/v1/tasks/{task_id}`
- `GET /api/v1/tasks/{task_id}/evidence`
- `GET /api/v1/tasks/{task_id}/graph`
- `GET /api/v1/tasks/{task_id}/progress/timeline`
- `GET /api/v1/tasks/{task_id}/proof-bundle`
- `PATCH /api/v1/tasks/{task_id}`
- `POST /api/v1/tasks`
- `POST /api/v1/tasks/duplicates/merge`
- `POST /api/v1/tasks/duplicates/preview`
- `POST /api/v1/tasks/{task_id}/block`
- `POST /api/v1/tasks/{task_id}/cancel`
- `POST /api/v1/tasks/{task_id}/checkout`
- `POST /api/v1/tasks/{task_id}/checkout/force-release`
- `POST /api/v1/tasks/{task_id}/checkout/release`
- `POST /api/v1/tasks/{task_id}/checkout/renew`
- `POST /api/v1/tasks/{task_id}/complete`
- `POST /api/v1/tasks/{task_id}/dependencies`
- `POST /api/v1/tasks/{task_id}/evidence`
- `POST /api/v1/tasks/{task_id}/progress`
- `POST /api/v1/tasks/{task_id}/reopen`
- `POST /api/v1/tasks/{task_id}/review`
- `POST /api/v1/tasks/{task_id}/start`
- `POST /api/v1/tasks/{task_id}/unblock`
- `POST /api/v1/tasks/{task_id}/workflow/align`
- `POST /api/v1/tasks/{task_id}/workflow/assign`
- `POST /api/v1/tasks/{task_id}/workflow/transition`

## `teams` (4)

- `GET /api/v1/teams`
- `GET /api/v1/teams/{team_id}`
- `PATCH /api/v1/teams/{team_id}`
- `POST /api/v1/teams`

## `test-runs` (11)

- `GET /api/v1/test-runs`
- `GET /api/v1/test-runs/retention`
- `GET /api/v1/test-runs/retention/policies`
- `GET /api/v1/test-runs/retention/policies/{policy_id}`
- `GET /api/v1/test-runs/{run_id}`
- `PATCH /api/v1/test-runs/retention/policies/{policy_id}`
- `POST /api/v1/test-runs`
- `POST /api/v1/test-runs/prune`
- `POST /api/v1/test-runs/retention/policies`
- `POST /api/v1/test-runs/retention/policies/{policy_id}/archive`
- `POST /api/v1/test-runs/retention/policies/{policy_id}/restore`

## `transitions` (2)

- `GET /api/v1/transitions/status/{entity_type}/{entity_id}`
- `GET /api/v1/transitions/workflow/{entity_type}/{entity_id}`

## `watchers` (4)

- `DELETE /api/v1/watchers`
- `GET /api/v1/watchers`
- `POST /api/v1/watchers`
- `POST /api/v1/watchers/{watcher_id}/restore`

## `work-snapshots` (3)

- `GET /api/v1/work-snapshots/{scope_type}/{scope_id}`
- `GET /api/v1/work-snapshots/{scope_type}/{scope_id}/daily`
- `POST /api/v1/work-snapshots/{scope_type}/{scope_id}/review`

## `workflow` (1)

- `POST /api/v1/workflow/align`

## `workflows` (2)

- `GET /api/v1/workflows`
- `GET /api/v1/workflows/{workflow_ref}`
