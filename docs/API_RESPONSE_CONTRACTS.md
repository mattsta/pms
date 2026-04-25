# API Response Contracts

Generated from live OpenAPI route + schema contracts. This supplements (does not replace) `docs/API_REFERENCE.md`.

Regenerate:

```bash
uv run python scripts/generate_api_response_contracts.py
```

## Summary

- Endpoint contracts: **206**
- Referenced schemas: **276**

## `actors` (5)

| Method | Path                                 | Purpose              | Request Body Type       | Success Response                       |
| ------ | ------------------------------------ | -------------------- | ----------------------- | -------------------------------------- |
| `GET`  | `/api/v1/actors`                     | List Actors          | `None`                  | `200 PaginatedResponse_ActorResponse_` |
| `POST` | `/api/v1/actors`                     | Create Actor         | `ActorCreate`           | `201 ActorResponse`                    |
| `GET`  | `/api/v1/actors/{actor}`             | Get Actor            | `None`                  | `200 ActorGraphResponse`               |
| `POST` | `/api/v1/actors/{actor}/aliases`     | Add Actor Alias      | `ActorAliasCreate`      | `201 ActorAliasResponse`               |
| `POST` | `/api/v1/actors/{actor}/memberships` | Add Actor Membership | `ActorMembershipCreate` | `201 ActorMembershipResponse`          |

## `agent-loops` (4)

| Method | Path                                     | Purpose                 | Request Body Type | Success Response                |
| ------ | ---------------------------------------- | ----------------------- | ----------------- | ------------------------------- |
| `GET`  | `/api/v1/agent-loops`                    | List Agent Loops        | `None`            | `200 AgentLoopListResponse`     |
| `GET`  | `/api/v1/agent-loops/{loop_id}`          | Get Agent Loop          | `None`            | `200 AgentLoopSummaryResponse`  |
| `POST` | `/api/v1/agent-loops/{loop_id}/cancel`   | Cancel Agent Loop       | `None`            | `200 AgentLoopSummaryResponse`  |
| `GET`  | `/api/v1/agent-loops/{loop_id}/messages` | Get Agent Loop Messages | `None`            | `200 AgentLoopMessagesResponse` |

## `auth` (8)

| Method   | Path                                    | Purpose               | Request Body Type     | Success Response              |
| -------- | --------------------------------------- | --------------------- | --------------------- | ----------------------------- |
| `POST`   | `/api/v1/auth/init`                     | Init Admin Key        | `InitApiKeyRequest`   | `201 CreateApiKeyResponse`    |
| `GET`    | `/api/v1/auth/keys`                     | List Api Keys         | `None`                | `200 ApiKeyResponse`          |
| `POST`   | `/api/v1/auth/keys`                     | Create Api Key        | `CreateApiKeyRequest` | `201 CreateApiKeyResponse`    |
| `DELETE` | `/api/v1/auth/keys/{key_id}`            | Delete Api Key        | `None`                | `204 No body`                 |
| `GET`    | `/api/v1/auth/keys/{key_id}`            | Get Api Key           | `None`                | `200 ApiKeyResponse`          |
| `POST`   | `/api/v1/auth/keys/{key_id}/deactivate` | Deactivate Api Key    | `None`                | `200 ApiKeyResponse`          |
| `POST`   | `/api/v1/auth/keys/{key_id}/restore`    | Restore Api Key       | `None`                | `200 ApiKeyResponse`          |
| `GET`    | `/api/v1/auth/scopes`                   | List Available Scopes | `None`                | `200 AvailableScopesResponse` |

## `automation` (8)

| Method   | Path                                         | Purpose                   | Request Body Type          | Success Response                    |
| -------- | -------------------------------------------- | ------------------------- | -------------------------- | ----------------------------------- |
| `GET`    | `/api/v1/automation/rules`                   | List Automation Rules     | `None`                     | `200 AutomationRuleListResponse`    |
| `POST`   | `/api/v1/automation/rules`                   | Create Automation Rule    | `AutomationRuleCreate`     | `201 AutomationRuleResponse`        |
| `DELETE` | `/api/v1/automation/rules/{rule_id}`         | Delete Automation Rule    | `None`                     | `200 map<string, string>`           |
| `GET`    | `/api/v1/automation/rules/{rule_id}`         | Get Automation Rule       | `None`                     | `200 AutomationRuleResponse`        |
| `PATCH`  | `/api/v1/automation/rules/{rule_id}`         | Update Automation Rule    | `AutomationRuleUpdate`     | `200 AutomationRuleResponse`        |
| `POST`   | `/api/v1/automation/rules/{rule_id}/restore` | Restore Automation Rule   | `None`                     | `200 AutomationRuleResponse`        |
| `GET`    | `/api/v1/automation/rules/{rule_id}/runs`    | List Automation Rule Runs | `None`                     | `200 AutomationRuleRunListResponse` |
| `POST`   | `/api/v1/automation/run`                     | Run Automation Rules      | `AutomationRuleRunRequest` | `200 AutomationRuleRunResponse`     |

## `checkout` (4)

| Method | Path                         | Purpose                   | Request Body Type | Success Response              |
| ------ | ---------------------------- | ------------------------- | ----------------- | ----------------------------- |
| `GET`  | `/api/v1/checkout/available` | Get Available Tasks       | `None`            | `200 AvailableTasksResponse`  |
| `POST` | `/api/v1/checkout/cleanup`   | Cleanup Expired Checkouts | `None`            | `200 CheckoutCleanupResponse` |
| `GET`  | `/api/v1/checkout/log`       | Get Checkout Log          | `None`            | `200 CheckoutLogResponse`     |
| `GET`  | `/api/v1/checkout/status`    | Get Checkout Status       | `None`            | `200 CheckoutStatusResponse`  |

## `comments` (5)

| Method   | Path                                    | Purpose         | Request Body Type | Success Response          |
| -------- | --------------------------------------- | --------------- | ----------------- | ------------------------- |
| `GET`    | `/api/v1/comments`                      | List Comments   | `None`            | `200 CommentListResponse` |
| `POST`   | `/api/v1/comments`                      | Add Comment     | `CommentCreate`   | `201 CommentResponse`     |
| `DELETE` | `/api/v1/comments/{comment_id}`         | Delete Comment  | `None`            | `200 map<string, string>` |
| `GET`    | `/api/v1/comments/{comment_id}`         | Get Comment     | `None`            | `200 CommentResponse`     |
| `POST`   | `/api/v1/comments/{comment_id}/restore` | Restore Comment | `None`            | `200 CommentResponse`     |

## `custom-fields` (9)

| Method   | Path                                       | Purpose                            | Request Body Type             | Success Response                                 |
| -------- | ------------------------------------------ | ---------------------------------- | ----------------------------- | ------------------------------------------------ |
| `GET`    | `/api/v1/custom-fields`                    | List Custom Fields                 | `None`                        | `200 map<string, CustomFieldDefinitionResponse>` |
| `POST`   | `/api/v1/custom-fields`                    | Create Custom Field                | `CustomFieldDefinitionCreate` | `201 CustomFieldDefinitionResponse`              |
| `GET`    | `/api/v1/custom-fields/values`             | List Custom Field Values           | `None`                        | `200 CustomFieldValuesResponse`                  |
| `DELETE` | `/api/v1/custom-fields/{field_id}`         | Delete Custom Field                | `None`                        | `200 map<string, string>`                        |
| `GET`    | `/api/v1/custom-fields/{field_id}`         | Get Custom Field                   | `None`                        | `200 CustomFieldDefinitionResponse`              |
| `PATCH`  | `/api/v1/custom-fields/{field_id}`         | Update Custom Field                | `CustomFieldDefinitionUpdate` | `200 CustomFieldDefinitionResponse`              |
| `POST`   | `/api/v1/custom-fields/{field_id}/restore` | Restore Custom Field               | `None`                        | `200 CustomFieldDefinitionResponse`              |
| `GET`    | `/api/v1/custom-fields/{field_id}/values`  | List Custom Field Values For Field | `None`                        | `200 CustomFieldValuesResponse`                  |
| `POST`   | `/api/v1/custom-fields/{field_id}/values`  | Set Custom Field Value             | `CustomFieldValueCreate`      | `201 CustomFieldValueItemResponse`               |

## `dashboard` (1)

| Method | Path                | Purpose                        | Request Body Type | Success Response                      |
| ------ | ------------------- | ------------------------------ | ----------------- | ------------------------------------- |
| `GET`  | `/api/v1/dashboard` | Get Instance Project Dashboard | `None`            | `200 ProjectDashboardResponsePayload` |

## `discoverability` (1)

| Method | Path                            | Purpose               | Request Body Type | Success Response                  |
| ------ | ------------------------------- | --------------------- | ----------------- | --------------------------------- |
| `GET`  | `/api/v1/discoverability/graph` | Discoverability Graph | `None`            | `200 DiscoverabilityGraphPayload` |

## `evidence` (4)

| Method   | Path                               | Purpose                   | Request Body Type        | Success Response                     |
| -------- | ---------------------------------- | ------------------------- | ------------------------ | ------------------------------------ |
| `GET`    | `/api/v1/evidence/bundles`         | Search Evidence Bundles   | `None`                   | `200 ProofBundleSearchResponse`      |
| `GET`    | `/api/v1/evidence/gates`           | List Evidence Gate Rules  | `None`                   | `200 EvidenceGateRuleResponse`       |
| `POST`   | `/api/v1/evidence/gates`           | Create Evidence Gate Rule | `EvidenceGateRuleCreate` | `201 EvidenceGateRuleResponse`       |
| `DELETE` | `/api/v1/evidence/gates/{rule_id}` | Delete Evidence Gate Rule | `None`                   | `200 DeleteEvidenceGateRuleResponse` |

## `goals` (11)

| Method  | Path                                          | Purpose                        | Request Body Type    | Success Response                                   |
| ------- | --------------------------------------------- | ------------------------------ | -------------------- | -------------------------------------------------- |
| `GET`   | `/api/v1/goals`                               | List Goals                     | `None`               | `200 PaginatedResponse_GoalListItemResponse_`      |
| `POST`  | `/api/v1/goals`                               | Create Goal                    | `GoalCreate`         | `201 GoalResponse`                                 |
| `GET`   | `/api/v1/goals/{goal_id}`                     | Get Goal                       | `None`               | `200 GoalDetailResponse`                           |
| `PATCH` | `/api/v1/goals/{goal_id}`                     | Update Goal                    | `GoalUpdate`         | `200 GoalResponse`                                 |
| `POST`  | `/api/v1/goals/{goal_id}/archive`             | Archive Goal                   | `None`               | `200 map<string, string>`                          |
| `POST`  | `/api/v1/goals/{goal_id}/complete`            | Complete Goal                  | `None`               | `200 map<string, string>`                          |
| `GET`   | `/api/v1/goals/{goal_id}/objectives`          | List Objectives                | `None`               | `200 PaginatedResponse_ObjectiveListItemResponse_` |
| `POST`  | `/api/v1/goals/{goal_id}/objectives`          | Create Objective               | `ObjectiveCreate`    | `201 ObjectiveResponse`                            |
| `GET`   | `/api/v1/goals/{goal_id}/summary`             | Get Goal Summary               | `None`               | `200 GoalSummaryResponse`                          |
| `POST`  | `/api/v1/goals/{goal_id}/workflow/assign`     | Assign Workflow To Goal        | `WorkflowAssign`     | `200 JsonObject`                                   |
| `POST`  | `/api/v1/goals/{goal_id}/workflow/transition` | Transition Goal Workflow State | `WorkflowTransition` | `200 WorkflowTransitionResponse`                   |

## `health` (1)

| Method | Path             | Purpose      | Request Body Type | Success Response         |
| ------ | ---------------- | ------------ | ----------------- | ------------------------ |
| `GET`  | `/api/v1/health` | Health Check | `None`            | `200 HealthCheckPayload` |

## `key-results` (4)

| Method  | Path                                           | Purpose             | Request Body Type | Success Response              |
| ------- | ---------------------------------------------- | ------------------- | ----------------- | ----------------------------- |
| `GET`   | `/api/v1/key-results/{key_result_id}`          | Get Key Result      | `None`            | `200 KeyResultDetailResponse` |
| `PATCH` | `/api/v1/key-results/{key_result_id}`          | Update Key Result   | `KeyResultUpdate` | `200 KeyResultResponse`       |
| `POST`  | `/api/v1/key-results/{key_result_id}/archive`  | Archive Key Result  | `None`            | `200 map<string, string>`     |
| `POST`  | `/api/v1/key-results/{key_result_id}/complete` | Complete Key Result | `None`            | `200 map<string, string>`     |

## `labels` (19)

| Method   | Path                                                 | Purpose                      | Request Body Type       | Success Response                            |
| -------- | ---------------------------------------------------- | ---------------------------- | ----------------------- | ------------------------------------------- |
| `GET`    | `/api/v1/labels`                                     | List Labels                  | `None`                  | `200 map<string, LabelResponse>`            |
| `POST`   | `/api/v1/labels`                                     | Create Label                 | `LabelCreate`           | `201 LabelResponse`                         |
| `DELETE` | `/api/v1/labels/assignments`                         | Remove Label Assignment      | `None`                  | `200 map<string, string>`                   |
| `GET`    | `/api/v1/labels/assignments`                         | List Label Assignments       | `None`                  | `200 LabelAssignmentsResponsePayload`       |
| `POST`   | `/api/v1/labels/assignments`                         | Assign Label                 | `LabelAssignmentCreate` | `201 LabelAssignmentResponse`               |
| `GET`    | `/api/v1/labels/assignments/{assignment_id}/history` | Get Label Assignment History | `None`                  | `200 LabelAssignmentHistoryResponsePayload` |
| `GET`    | `/api/v1/labels/categories`                          | List Label Categories        | `None`                  | `200 map<string, LabelCategoryResponse>`    |
| `POST`   | `/api/v1/labels/categories`                          | Create Label Category        | `LabelCategoryCreate`   | `201 LabelCategoryResponse`                 |
| `DELETE` | `/api/v1/labels/categories/{category_id}`            | Delete Label Category        | `None`                  | `200 map<string, string>`                   |
| `GET`    | `/api/v1/labels/categories/{category_id}`            | Get Label Category           | `None`                  | `200 LabelCategoryResponse`                 |
| `PATCH`  | `/api/v1/labels/categories/{category_id}`            | Update Label Category        | `LabelCategoryUpdate`   | `200 LabelCategoryResponse`                 |
| `POST`   | `/api/v1/labels/categories/{category_id}/restore`    | Restore Label Category       | `None`                  | `200 LabelCategoryResponse`                 |
| `GET`    | `/api/v1/labels/gates`                               | List Label Gate Rules        | `None`                  | `200 map<string, LabelGateRuleResponse>`    |
| `POST`   | `/api/v1/labels/gates`                               | Create Label Gate Rule       | `LabelGateRuleCreate`   | `201 LabelGateRuleResponse`                 |
| `DELETE` | `/api/v1/labels/gates/{rule_id}`                     | Delete Label Gate Rule       | `None`                  | `200 map<string, string>`                   |
| `DELETE` | `/api/v1/labels/{label_id}`                          | Delete Label                 | `None`                  | `200 map<string, string>`                   |
| `GET`    | `/api/v1/labels/{label_id}`                          | Get Label                    | `None`                  | `200 LabelResponse`                         |
| `PATCH`  | `/api/v1/labels/{label_id}`                          | Update Label                 | `LabelUpdate`           | `200 LabelResponse`                         |
| `POST`   | `/api/v1/labels/{label_id}/restore`                  | Restore Label                | `None`                  | `200 LabelResponse`                         |

## `objectives` (8)

| Method  | Path                                                    | Purpose                             | Request Body Type    | Success Response                                   |
| ------- | ------------------------------------------------------- | ----------------------------------- | -------------------- | -------------------------------------------------- |
| `GET`   | `/api/v1/objectives/{objective_id}`                     | Get Objective                       | `None`               | `200 ObjectiveDetailResponse`                      |
| `PATCH` | `/api/v1/objectives/{objective_id}`                     | Update Objective                    | `ObjectiveUpdate`    | `200 ObjectiveResponse`                            |
| `POST`  | `/api/v1/objectives/{objective_id}/archive`             | Archive Objective                   | `None`               | `200 map<string, string>`                          |
| `POST`  | `/api/v1/objectives/{objective_id}/complete`            | Complete Objective                  | `None`               | `200 map<string, string>`                          |
| `GET`   | `/api/v1/objectives/{objective_id}/key-results`         | List Key Results                    | `None`               | `200 PaginatedResponse_KeyResultListItemResponse_` |
| `POST`  | `/api/v1/objectives/{objective_id}/key-results`         | Create Key Result                   | `KeyResultCreate`    | `201 KeyResultResponse`                            |
| `POST`  | `/api/v1/objectives/{objective_id}/workflow/assign`     | Assign Workflow To Objective        | `WorkflowAssign`     | `200 JsonObject`                                   |
| `POST`  | `/api/v1/objectives/{objective_id}/workflow/transition` | Transition Objective Workflow State | `WorkflowTransition` | `200 WorkflowTransitionResponse`                   |

## `observability` (1)

| Method | Path                             | Purpose                    | Request Body Type | Success Response                   |
| ------ | -------------------------------- | -------------------------- | ----------------- | ---------------------------------- |
| `GET`  | `/api/v1/observability/overview` | Get Observability Overview | `None`            | `200 ObservabilityOverviewPayload` |

## `organizations` (6)

| Method  | Path                                     | Purpose                    | Request Body Type    | Success Response                              |
| ------- | ---------------------------------------- | -------------------------- | -------------------- | --------------------------------------------- |
| `GET`   | `/api/v1/organizations`                  | List Organizations         | `None`               | `200 PaginatedResponse_OrganizationResponse_` |
| `POST`  | `/api/v1/organizations`                  | Create Organization        | `OrganizationCreate` | `201 OrganizationResponse`                    |
| `GET`   | `/api/v1/organizations/dashboard`        | Get Organization Dashboard | `None`               | `200 OrganizationDashboardResponsePayload`    |
| `GET`   | `/api/v1/organizations/{org_id}`         | Get Organization           | `None`               | `200 OrganizationResponse`                    |
| `PATCH` | `/api/v1/organizations/{org_id}`         | Update Organization        | `OrganizationUpdate` | `200 OrganizationResponse`                    |
| `GET`   | `/api/v1/organizations/{org_id}/summary` | Get Organization Summary   | `None`               | `200 OrganizationSummaryPayload`              |

## `plans` (12)

| Method   | Path                                                 | Purpose                    | Request Body Type   | Success Response                      |
| -------- | ---------------------------------------------------- | -------------------------- | ------------------- | ------------------------------------- |
| `GET`    | `/api/v1/plans`                                      | List Plans                 | `None`              | `200 PaginatedResponse_PlanResponse_` |
| `POST`   | `/api/v1/plans`                                      | Create Plan                | `PlanCreate`        | `201 PlanResponse`                    |
| `GET`    | `/api/v1/plans/lineage`                              | Get Plan Lineage Dashboard | `None`              | `200 PlanLineageDashboardPayload`     |
| `GET`    | `/api/v1/plans/{plan_id}`                            | Get Plan                   | `None`              | `200 PlanResponse`                    |
| `PATCH`  | `/api/v1/plans/{plan_id}`                            | Update Plan                | `PlanUpdate`        | `200 PlanResponse`                    |
| `GET`    | `/api/v1/plans/{plan_id}/test-jobs`                  | List Plan Test Jobs        | `None`              | `200 PlanTestJobListResponse`         |
| `POST`   | `/api/v1/plans/{plan_id}/test-jobs`                  | Create Plan Test Job       | `PlanTestJobCreate` | `201 PlanTestJobResponse`             |
| `DELETE` | `/api/v1/plans/{plan_id}/test-jobs/{job_id}`         | Delete Plan Test Job       | `None`              | `200 map<string, string>`             |
| `GET`    | `/api/v1/plans/{plan_id}/test-jobs/{job_id}`         | Get Plan Test Job          | `None`              | `200 PlanTestJobResponse`             |
| `PATCH`  | `/api/v1/plans/{plan_id}/test-jobs/{job_id}`         | Update Plan Test Job       | `PlanTestJobUpdate` | `200 PlanTestJobResponse`             |
| `POST`   | `/api/v1/plans/{plan_id}/test-jobs/{job_id}/restore` | Restore Plan Test Job      | `None`              | `200 PlanTestJobResponse`             |
| `POST`   | `/api/v1/plans/{plan_id}/test-jobs/{job_id}/run`     | Run Plan Test Job          | `None`              | `200 PlanTestJobRunResponse`          |

## `portfolios` (6)

| Method  | Path                                        | Purpose                 | Request Body Type | Success Response                           |
| ------- | ------------------------------------------- | ----------------------- | ----------------- | ------------------------------------------ |
| `GET`   | `/api/v1/portfolios`                        | List Portfolios         | `None`            | `200 PaginatedResponse_PortfolioResponse_` |
| `POST`  | `/api/v1/portfolios`                        | Create Portfolio        | `PortfolioCreate` | `201 PortfolioResponse`                    |
| `GET`   | `/api/v1/portfolios/dashboard`              | Get Portfolio Dashboard | `None`            | `200 PortfolioDashboardResponsePayload`    |
| `GET`   | `/api/v1/portfolios/{portfolio_id}`         | Get Portfolio           | `None`            | `200 PortfolioResponse`                    |
| `PATCH` | `/api/v1/portfolios/{portfolio_id}`         | Update Portfolio        | `PortfolioUpdate` | `200 PortfolioResponse`                    |
| `GET`   | `/api/v1/portfolios/{portfolio_id}/summary` | Get Portfolio Summary   | `None`            | `200 PortfolioSummaryPayload`              |

## `products` (6)

| Method  | Path                                    | Purpose             | Request Body Type | Success Response                         |
| ------- | --------------------------------------- | ------------------- | ----------------- | ---------------------------------------- |
| `GET`   | `/api/v1/products`                      | List Products       | `None`            | `200 PaginatedResponse_ProductResponse_` |
| `POST`  | `/api/v1/products`                      | Create Product      | `ProductCreate`   | `201 ProductResponse`                    |
| `GET`   | `/api/v1/products/{product_id}`         | Get Product         | `None`            | `200 ProductResponse`                    |
| `PATCH` | `/api/v1/products/{product_id}`         | Update Product      | `ProductUpdate`   | `200 ProductResponse`                    |
| `POST`  | `/api/v1/products/{product_id}/archive` | Archive Product     | `None`            | `200 map<string, string>`                |
| `GET`   | `/api/v1/products/{product_id}/summary` | Get Product Summary | `None`            | `200 ProductSummaryResponsePayload`      |

## `programs` (6)

| Method  | Path                                    | Purpose               | Request Body Type | Success Response                         |
| ------- | --------------------------------------- | --------------------- | ----------------- | ---------------------------------------- |
| `GET`   | `/api/v1/programs`                      | List Programs         | `None`            | `200 PaginatedResponse_ProgramResponse_` |
| `POST`  | `/api/v1/programs`                      | Create Program        | `ProgramCreate`   | `201 ProgramResponse`                    |
| `GET`   | `/api/v1/programs/dashboard`            | Get Program Dashboard | `None`            | `200 ProgramDashboardResponsePayload`    |
| `GET`   | `/api/v1/programs/{program_id}`         | Get Program           | `None`            | `200 ProgramResponse`                    |
| `PATCH` | `/api/v1/programs/{program_id}`         | Update Program        | `ProgramUpdate`   | `200 ProgramResponse`                    |
| `GET`   | `/api/v1/programs/{program_id}/summary` | Get Program Summary   | `None`            | `200 ProgramSummaryPayload`              |

## `projects` (6)

| Method  | Path                                              | Purpose                       | Request Body Type | Success Response                         |
| ------- | ------------------------------------------------- | ----------------------------- | ----------------- | ---------------------------------------- |
| `GET`   | `/api/v1/projects`                                | List Projects                 | `None`            | `200 PaginatedResponse_ProjectResponse_` |
| `POST`  | `/api/v1/projects`                                | Create Project                | `ProjectCreate`   | `201 ProjectResponse`                    |
| `GET`   | `/api/v1/projects/{project_id}`                   | Get Project                   | `None`            | `200 ProjectResponse`                    |
| `PATCH` | `/api/v1/projects/{project_id}`                   | Update Project                | `ProjectUpdate`   | `200 ProjectResponse`                    |
| `GET`   | `/api/v1/projects/{project_id}/operator-overview` | Get Project Operator Overview | `None`            | `200 ProjectOperatorOverviewPayload`     |
| `GET`   | `/api/v1/projects/{project_id}/summary`           | Get Project Summary           | `None`            | `200 ProjectSummaryResponsePayload`      |

## `queues` (9)

| Method   | Path                                | Purpose              | Request Body Type          | Success Response              |
| -------- | ----------------------------------- | -------------------- | -------------------------- | ----------------------------- |
| `GET`    | `/api/v1/queues`                    | List Saved Searches  | `None`                     | `200 SavedSearchListResponse` |
| `POST`   | `/api/v1/queues`                    | Create Saved Search  | `SavedSearchRequest`       | `201 SavedSearchResponse`     |
| `GET`    | `/api/v1/queues/presets`            | List Queue Presets   | `None`                     | `200 QueuePresetResponse`     |
| `GET`    | `/api/v1/queues/presets/{preset}`   | Get Queue Preset     | `None`                     | `200 QueuePresetResponse`     |
| `DELETE` | `/api/v1/queues/{queue_id}`         | Delete Saved Search  | `None`                     | `200 map<string, string>`     |
| `GET`    | `/api/v1/queues/{queue_id}`         | Get Saved Search     | `None`                     | `200 SavedSearchResponse`     |
| `PUT`    | `/api/v1/queues/{queue_id}`         | Update Saved Search  | `SavedSearchUpdateRequest` | `200 SavedSearchResponse`     |
| `POST`   | `/api/v1/queues/{queue_id}/restore` | Restore Saved Search | `None`                     | `200 SavedSearchResponse`     |
| `GET`    | `/api/v1/queues/{queue_id}/run`     | Run Saved Search     | `None`                     | `200 SavedSearchRunResponse`  |

## `revisions` (2)

| Method | Path                                                 | Purpose                 | Request Body Type | Success Response                    |
| ------ | ---------------------------------------------------- | ----------------------- | ----------------- | ----------------------------------- |
| `GET`  | `/api/v1/revisions/{entity_type}/{entity_id}/bundle` | Revision History Bundle | `None`            | `200 RevisionHistoryBundleResponse` |
| `GET`  | `/api/v1/revisions/{entity_type}/{entity_id}/diff`   | Diff Revisions          | `None`            | `200 RevisionDiffResponse`          |

## `tasks` (33)

| Method   | Path                                                   | Purpose                   | Request Body Type           | Success Response                              |
| -------- | ------------------------------------------------------ | ------------------------- | --------------------------- | --------------------------------------------- |
| `GET`    | `/api/v1/tasks`                                        | List Tasks                | `None`                      | `200 PaginatedResponse_TaskResponse_`         |
| `POST`   | `/api/v1/tasks`                                        | Create Task               | `TaskCreate`                | `201 TaskResponse`                            |
| `GET`    | `/api/v1/tasks/duplicates`                             | List Duplicate Tasks      | `None`                      | `200 DuplicateTaskListResponsePayload`        |
| `POST`   | `/api/v1/tasks/duplicates/merge`                       | Merge Duplicate Tasks     | `TaskDuplicateMerge`        | `200 MergeDuplicateTasksResponsePayload`      |
| `POST`   | `/api/v1/tasks/duplicates/preview`                     | Preview Duplicate Merge   | `TaskDuplicateMergePreview` | `200 DuplicateMergePreviewResponse`           |
| `GET`    | `/api/v1/tasks/ready`                                  | List Ready Tasks          | `None`                      | `200 PaginatedResponse_TaskResponse_`         |
| `GET`    | `/api/v1/tasks/search`                                 | Search Tasks              | `None`                      | `200 PaginatedResponse_TaskResponse_`         |
| `GET`    | `/api/v1/tasks/stale`                                  | List Stale Tasks          | `None`                      | `200 PaginatedResponse_TaskResponse_`         |
| `GET`    | `/api/v1/tasks/tree`                                   | Get Task Tree             | `None`                      | `200 TaskTreeResponse`                        |
| `GET`    | `/api/v1/tasks/{task_id}`                              | Get Task                  | `None`                      | `200 TaskResponse`                            |
| `PATCH`  | `/api/v1/tasks/{task_id}`                              | Update Task               | `TaskUpdate`                | `200 TaskResponse`                            |
| `POST`   | `/api/v1/tasks/{task_id}/block`                        | Block Task                | `TaskActionRequest \| null` | `200 map<string, string>`                     |
| `POST`   | `/api/v1/tasks/{task_id}/cancel`                       | Cancel Task               | `TaskActionRequest \| null` | `200 map<string, string>`                     |
| `POST`   | `/api/v1/tasks/{task_id}/checkout`                     | Checkout Task             | `CheckoutRequest`           | `200 CheckoutResponse`                        |
| `POST`   | `/api/v1/tasks/{task_id}/checkout/force-release`       | Force Release Checkout    | `None`                      | `200 map<string, string>`                     |
| `POST`   | `/api/v1/tasks/{task_id}/checkout/release`             | Release Checkout          | `None`                      | `200 map<string, string>`                     |
| `POST`   | `/api/v1/tasks/{task_id}/checkout/renew`               | Renew Checkout            | `None`                      | `200 RenewCheckoutResponse`                   |
| `POST`   | `/api/v1/tasks/{task_id}/complete`                     | Complete Task             | `TaskActionRequest \| null` | `200 TaskCompletionActionResponse`            |
| `POST`   | `/api/v1/tasks/{task_id}/dependencies`                 | Add Task Dependency       | `TaskDependencyCreate`      | `201 TaskDependencyResponse`                  |
| `DELETE` | `/api/v1/tasks/{task_id}/dependencies/{depends_on_id}` | Remove Task Dependency    | `None`                      | `200 map<string, string>`                     |
| `GET`    | `/api/v1/tasks/{task_id}/evidence`                     | List Task Evidence        | `None`                      | `200 PaginatedResponse_TaskEvidenceResponse_` |
| `POST`   | `/api/v1/tasks/{task_id}/evidence`                     | Add Task Evidence         | `TaskEvidenceCreate`        | `201 TaskEvidenceResponse`                    |
| `GET`    | `/api/v1/tasks/{task_id}/graph`                        | Get Task Dependency Graph | `None`                      | `200 TaskDependencyGraphResponse`             |
| `POST`   | `/api/v1/tasks/{task_id}/progress`                     | Update Task Progress      | `ProgressUpdate`            | `200 ProgressResponse`                        |
| `GET`    | `/api/v1/tasks/{task_id}/progress/timeline`            | Get Progress Timeline     | `None`                      | `200 ProgressTimelinePayload`                 |
| `GET`    | `/api/v1/tasks/{task_id}/proof-bundle`                 | Get Task Proof Bundle     | `None`                      | `200 ProofBundleResponse`                     |
| `POST`   | `/api/v1/tasks/{task_id}/reopen`                       | Reopen Task               | `TaskActionRequest \| null` | `200 map<string, string>`                     |
| `POST`   | `/api/v1/tasks/{task_id}/review`                       | Review Task               | `TaskActionRequest \| null` | `200 map<string, string>`                     |
| `POST`   | `/api/v1/tasks/{task_id}/start`                        | Start Task                | `TaskActionRequest \| null` | `200 map<string, string>`                     |
| `POST`   | `/api/v1/tasks/{task_id}/unblock`                      | Unblock Task              | `TaskActionRequest \| null` | `200 map<string, string>`                     |
| `POST`   | `/api/v1/tasks/{task_id}/workflow/align`               | Align Task Workflow State | `WorkflowAlign`             | `200 WorkflowAlignResponse`                   |
| `POST`   | `/api/v1/tasks/{task_id}/workflow/assign`              | Assign Workflow To Task   | `WorkflowAssign`            | `200 JsonObject`                              |
| `POST`   | `/api/v1/tasks/{task_id}/workflow/transition`          | Transition Workflow State | `WorkflowTransition`        | `200 WorkflowTransitionResponse`              |

## `teams` (4)

| Method  | Path                      | Purpose     | Request Body Type | Success Response                      |
| ------- | ------------------------- | ----------- | ----------------- | ------------------------------------- |
| `GET`   | `/api/v1/teams`           | List Teams  | `None`            | `200 PaginatedResponse_TeamResponse_` |
| `POST`  | `/api/v1/teams`           | Create Team | `TeamCreate`      | `201 TeamResponse`                    |
| `GET`   | `/api/v1/teams/{team_id}` | Get Team    | `None`            | `200 TeamResponse`                    |
| `PATCH` | `/api/v1/teams/{team_id}` | Update Team | `TeamUpdate`      | `200 TeamResponse`                    |

## `test-runs` (11)

| Method  | Path                                                       | Purpose                  | Request Body Type | Success Response                         |
| ------- | ---------------------------------------------------------- | ------------------------ | ----------------- | ---------------------------------------- |
| `GET`   | `/api/v1/test-runs`                                        | List Test Runs           | `None`            | `200 PaginatedResponse_TestRunResponse_` |
| `POST`  | `/api/v1/test-runs`                                        | Create Test Run          | `TestRunCreate`   | `201 TestRunResponse`                    |
| `POST`  | `/api/v1/test-runs/prune`                                  | Prune Test Runs          | `None`            | `200 TestRunPruneResponse`               |
| `GET`   | `/api/v1/test-runs/retention`                              | Get Test Run Retention   | `None`            | `200 TestRunRetentionResponse`           |
| `GET`   | `/api/v1/test-runs/retention/policies`                     | List Retention Policies  | `None`            | `200 RetentionPoliciesResponsePayload`   |
| `POST`  | `/api/v1/test-runs/retention/policies`                     | Upsert Retention Policy  | `None`            | `200 TestRunRetentionPolicyResponse`     |
| `GET`   | `/api/v1/test-runs/retention/policies/{policy_id}`         | Get Retention Policy     | `None`            | `200 TestRunRetentionPolicyResponse`     |
| `PATCH` | `/api/v1/test-runs/retention/policies/{policy_id}`         | Update Retention Policy  | `None`            | `200 TestRunRetentionPolicyResponse`     |
| `POST`  | `/api/v1/test-runs/retention/policies/{policy_id}/archive` | Archive Retention Policy | `None`            | `200 map<string, boolean>`               |
| `POST`  | `/api/v1/test-runs/retention/policies/{policy_id}/restore` | Restore Retention Policy | `None`            | `200 TestRunRetentionPolicyResponse`     |
| `GET`   | `/api/v1/test-runs/{run_id}`                               | Get Test Run             | `None`            | `200 TestRunResponse`                    |

## `transitions` (2)

| Method | Path                                                     | Purpose               | Request Body Type       | Success Response                 |
| ------ | -------------------------------------------------------- | --------------------- | ----------------------- | -------------------------------- |
| `GET`  | `/api/v1/transitions/status/{entity_type}/{entity_id}`   | Get Status Timeline   | `array<string> \| null` | `200 TransitionTimelineResponse` |
| `GET`  | `/api/v1/transitions/workflow/{entity_type}/{entity_id}` | Get Workflow Timeline | `array<string> \| null` | `200 TransitionTimelineResponse` |

## `watchers` (4)

| Method   | Path                                    | Purpose         | Request Body Type | Success Response          |
| -------- | --------------------------------------- | --------------- | ----------------- | ------------------------- |
| `DELETE` | `/api/v1/watchers`                      | Remove Watcher  | `None`            | `200 map<string, string>` |
| `GET`    | `/api/v1/watchers`                      | List Watchers   | `None`            | `200 WatcherListResponse` |
| `POST`   | `/api/v1/watchers`                      | Add Watcher     | `WatcherCreate`   | `201 WatcherResponse`     |
| `POST`   | `/api/v1/watchers/{watcher_id}/restore` | Restore Watcher | `None`            | `200 WatcherResponse`     |

## `work-snapshots` (3)

| Method | Path                                                    | Purpose                     | Request Body Type           | Success Response                 |
| ------ | ------------------------------------------------------- | --------------------------- | --------------------------- | -------------------------------- |
| `GET`  | `/api/v1/work-snapshots/{scope_type}/{scope_id}`        | Get Work Snapshot           | `None`                      | `200 WorkSnapshotResponse`       |
| `GET`  | `/api/v1/work-snapshots/{scope_type}/{scope_id}/daily`  | Get Work Daily              | `None`                      | `200 WorkDailyPayload`           |
| `POST` | `/api/v1/work-snapshots/{scope_type}/{scope_id}/review` | Mark Work Snapshot Reviewed | `WorkSnapshotReviewRequest` | `201 WorkSnapshotReviewResponse` |

## `workflow` (1)

| Method | Path                     | Purpose              | Request Body Type | Success Response            |
| ------ | ------------------------ | -------------------- | ----------------- | --------------------------- |
| `POST` | `/api/v1/workflow/align` | Align Workflow State | `WorkflowAlign`   | `200 WorkflowAlignResponse` |

## `workflows` (2)

| Method | Path                               | Purpose        | Request Body Type | Success Response          |
| ------ | ---------------------------------- | -------------- | ----------------- | ------------------------- |
| `GET`  | `/api/v1/workflows`                | List Workflows | `None`            | `200 WorkflowListPayload` |
| `GET`  | `/api/v1/workflows/{workflow_ref}` | Show Workflow  | `None`            | `200 JsonObject`          |

## Referenced Schemas

### `ActorAliasCreate`

- Kind: `object`
- Description: Request model for creating an actor alias.

| Field   | Type     | Required | Description |
| ------- | -------- | -------- | ----------- |
| `alias` | `string` | yes      | -           |

### `ActorAliasResponse`

- Kind: `object`
- Description: Response model for actor alias.

| Field              | Type             | Required | Description |
| ------------------ | ---------------- | -------- | ----------- |
| `actor_id`         | `string`         | yes      | -           |
| `alias`            | `string`         | yes      | -           |
| `archived_at`      | `string \| null` | no       | -           |
| `created_at`       | `string`         | yes      | -           |
| `id`               | `string`         | yes      | -           |
| `normalized_alias` | `string`         | yes      | -           |
| `updated_at`       | `string`         | yes      | -           |

### `ActorCreate`

- Kind: `object`
- Description: Request model for creating an actor.

| Field         | Type             | Required | Description |
| ------------- | ---------------- | -------- | ----------- |
| `description` | `string \| null` | no       | -           |
| `handle`      | `string \| null` | no       | -           |
| `kind`        | `string`         | no       | -           |
| `metadata`    | `JsonObject`     | no       | -           |
| `name`        | `string`         | yes      | -           |
| `tags`        | `array<string>`  | no       | -           |

### `ActorGraphResponse`

- Kind: `object`
- Description: Actor graph and workload response.

| Field                | Type                 | Required | Description |
| -------------------- | -------------------- | -------- | ----------- |
| `actor`              | `ActorResponse`      | yes      | -           |
| `aliases`            | `ActorAliasResponse` | no       | -           |
| `graph_navigation`   | `JsonObject`         | no       | -           |
| `last_activity_at`   | `string \| null`     | no       | -           |
| `last_transition_at` | `string \| null`     | no       | -           |
| `links`              | `JsonObject`         | no       | -           |
| `memberships`        | `JsonObject`         | no       | -           |
| `next_steps`         | `array<string>`      | no       | -           |
| `ownership`          | `JsonObject`         | no       | -           |
| `project_workloads`  | `JsonObject`         | no       | -           |
| `workload`           | `JsonObject`         | no       | -           |

### `ActorKind`

- Kind: `enum`
- Description: Type of actor node in the identity graph.
- Allowed values: `'human'`, `'persona'`, `'team'`, `'service_account'`, `'runtime_agent'`
- Top-level fields: _none_

### `ActorMembershipCreate`

- Kind: `object`
- Description: Request model for creating an actor membership.

| Field    | Type     | Required | Description |
| -------- | -------- | -------- | ----------- |
| `member` | `string` | yes      | -           |
| `role`   | `string` | no       | -           |

### `ActorMembershipResponse`

- Kind: `object`
- Description: Response model for actor membership.

| Field             | Type                  | Required | Description |
| ----------------- | --------------------- | -------- | ----------- |
| `archived_at`     | `string \| null`      | no       | -           |
| `created_at`      | `string`              | yes      | -           |
| `id`              | `string`              | yes      | -           |
| `member_actor_id` | `string`              | yes      | -           |
| `parent_actor_id` | `string`              | yes      | -           |
| `role`            | `ActorMembershipRole` | yes      | -           |
| `updated_at`      | `string`              | yes      | -           |

### `ActorMembershipRole`

- Kind: `enum`
- Description: Relationship role between a member actor and a parent actor.
- Allowed values: `'member'`, `'lead'`, `'representative'`
- Top-level fields: _none_

### `ActorReferencePayload`

- Kind: `object`
- Description: Resolved actor reference payload.

| Field   | Type                 | Required | Description |
| ------- | -------------------- | -------- | ----------- |
| `actor` | `JsonObject \| null` | no       | -           |
| `id`    | `string \| null`     | no       | -           |
| `links` | `JsonObject`         | no       | -           |
| `ref`   | `string \| null`     | no       | -           |

### `ActorResponse`

- Kind: `object`
- Description: Response model for actor.

| Field                | Type             | Required | Description |
| -------------------- | ---------------- | -------- | ----------- |
| `archived_at`        | `string \| null` | no       | -           |
| `created_at`         | `string`         | yes      | -           |
| `description`        | `string \| null` | yes      | -           |
| `handle`             | `string`         | yes      | -           |
| `id`                 | `string`         | yes      | -           |
| `kind`               | `ActorKind`      | yes      | -           |
| `last_activity_at`   | `string \| null` | no       | -           |
| `last_transition_at` | `string \| null` | no       | -           |
| `metadata`           | `JsonObject`     | yes      | -           |
| `name`               | `string`         | yes      | -           |
| `status`             | `ActorStatus`    | yes      | -           |
| `tags`               | `array<string>`  | yes      | -           |
| `updated_at`         | `string`         | yes      | -           |

### `ActorStatus`

- Kind: `enum`
- Description: Lifecycle status for an actor.
- Allowed values: `'active'`, `'archived'`
- Top-level fields: _none_

### `AgentLoopListResponse`

- Kind: `object`
- Description: Response model for listing agent loops.

| Field         | Type                       | Required | Description |
| ------------- | -------------------------- | -------- | ----------- |
| `items`       | `AgentLoopSummaryResponse` | no       | -           |
| `limit`       | `integer`                  | no       | -           |
| `links`       | `JsonObject`               | no       | -           |
| `next_steps`  | `array<string>`            | no       | -           |
| `offset`      | `integer`                  | no       | -           |
| `params`      | `JsonObject`               | no       | -           |
| `total_count` | `integer`                  | no       | -           |

### `AgentLoopMessageResponse`

- Kind: `object`
- Description: Response model for agent loop messages.

| Field        | Type              | Required | Description                                                                                                                                                                                        |
| ------------ | ----------------- | -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `content`    | `string`          | yes      | -                                                                                                                                                                                                  |
| `cost_usd`   | `string \| null`  | yes      | -                                                                                                                                                                                                  |
| `id`         | `string`          | yes      | -                                                                                                                                                                                                  |
| `metadata`   | `JsonObject`      | yes      | -                                                                                                                                                                                                  |
| `role`       | `string`          | yes      | Open transcript role. Preferred built-ins are `system`, `user`, `assistant`, and `tool`, but custom roles remain valid for planners, reviewers, plugins, and other extension-mediated transcripts. |
| `session_id` | `string`          | yes      | -                                                                                                                                                                                                  |
| `timestamp`  | `string`          | yes      | -                                                                                                                                                                                                  |
| `tokens`     | `integer \| null` | yes      | -                                                                                                                                                                                                  |

### `AgentLoopMessagesResponse`

- Kind: `object`
- Description: Response model for agent loop messages.

| Field         | Type                       | Required | Description |
| ------------- | -------------------------- | -------- | ----------- |
| `items`       | `AgentLoopMessageResponse` | no       | -           |
| `limit`       | `integer`                  | no       | -           |
| `links`       | `JsonObject`               | no       | -           |
| `next_steps`  | `array<string>`            | no       | -           |
| `offset`      | `integer`                  | no       | -           |
| `params`      | `JsonObject`               | no       | -           |
| `total_count` | `integer`                  | no       | -           |

### `AgentLoopSummaryResponse`

- Kind: `object`
- Description: Summary model for agent loops.

| Field                   | Type             | Required | Description |
| ----------------------- | ---------------- | -------- | ----------- |
| `agent`                 | `string`         | yes      | -           |
| `created_at`            | `string`         | yes      | -           |
| `ended_at`              | `string \| null` | yes      | -           |
| `id`                    | `string`         | yes      | -           |
| `iterations`            | `integer`        | yes      | -           |
| `last_prompt`           | `string \| null` | yes      | -           |
| `last_response_summary` | `string \| null` | yes      | -           |
| `max_iterations`        | `integer`        | yes      | -           |
| `max_runtime_seconds`   | `integer`        | yes      | -           |
| `status`                | `SessionStatus`  | yes      | -           |
| `stop_reason`           | `string \| null` | yes      | -           |
| `updated_at`            | `string`         | yes      | -           |

### `Alert`

- Kind: `object`
- Description: Retention policy alert.

| Field           | Type                          | Required | Description |
| --------------- | ----------------------------- | -------- | ----------- |
| `current_value` | `integer`                     | yes      | -           |
| `details`       | `JsonObject`                  | no       | -           |
| `limit_value`   | `integer`                     | yes      | -           |
| `metric`        | `string`                      | yes      | -           |
| `policy_id`     | `string`                      | yes      | -           |
| `ratio`         | `number`                      | yes      | -           |
| `scope_id`      | `string`                      | yes      | -           |
| `scope_type`    | `'project' \| 'organization'` | yes      | -           |
| `severity`      | `'warning' \| 'critical'`     | yes      | -           |

### `ApiKeyResponse`

- Kind: `object`
- Description: API key information (without the actual key).

| Field          | Type                  | Required | Description |
| -------------- | --------------------- | -------- | ----------- |
| `archived_at`  | `string \| null`      | no       | -           |
| `created_at`   | `string`              | yes      | -           |
| `expires_at`   | `string \| null`      | yes      | -           |
| `id`           | `string`              | yes      | -           |
| `is_active`    | `boolean`             | yes      | -           |
| `last_used_at` | `string \| null`      | yes      | -           |
| `metadata`     | `map<string, string>` | yes      | -           |
| `name`         | `string`              | yes      | -           |
| `prefix`       | `string`              | yes      | -           |
| `rate_limit`   | `integer \| null`     | yes      | -           |
| `scopes`       | `array<string>`       | yes      | -           |

### `AutomationActionType`

- Kind: `enum`
- Description: Supported automation action types.
- Allowed values: `'add_comment'`, `'create_task'`, `'update_task_status'`, `'set_custom_field_value'`
- Top-level fields: _none_

### `AutomationRuleCreate`

- Kind: `object`
- Description: Request model for creating an automation rule.

| Field              | Type                                                                                 | Required | Description                                                                                                            |
| ------------------ | ------------------------------------------------------------------------------------ | -------- | ---------------------------------------------------------------------------------------------------------------------- |
| `action_payload`   | `JsonObject`                                                                         | no       | -                                                                                                                      |
| `action_type`      | `'add_comment' \| 'create_task' \| 'update_task_status' \| 'set_custom_field_value'` | yes      | Canonical automation action type. Allowed values: add_comment, create_task, update_task_status, set_custom_field_value |
| `aggregate_id`     | `string \| null`                                                                     | no       | -                                                                                                                      |
| `aggregate_type`   | `string \| null`                                                                     | no       | -                                                                                                                      |
| `cooldown_seconds` | `number`                                                                             | no       | -                                                                                                                      |
| `description`      | `string \| null`                                                                     | no       | -                                                                                                                      |
| `enabled`          | `boolean`                                                                            | no       | -                                                                                                                      |
| `event_pattern`    | `string`                                                                             | yes      | -                                                                                                                      |
| `name`             | `string`                                                                             | yes      | -                                                                                                                      |

### `AutomationRuleListResponse`

- Kind: `object`
- Description: Response model for automation rule lists.

| Field         | Type                     | Required | Description |
| ------------- | ------------------------ | -------- | ----------- |
| `items`       | `AutomationRuleResponse` | no       | -           |
| `limit`       | `integer`                | no       | -           |
| `links`       | `JsonObject`             | no       | -           |
| `next_steps`  | `array<string>`          | no       | -           |
| `offset`      | `integer`                | no       | -           |
| `params`      | `JsonObject`             | no       | -           |
| `total_count` | `integer`                | no       | -           |

### `AutomationRuleResponse`

- Kind: `object`
- Description: Response model for an automation rule.

| Field              | Type                   | Required | Description                                                                                                            |
| ------------------ | ---------------------- | -------- | ---------------------------------------------------------------------------------------------------------------------- |
| `action_payload`   | `JsonObject`           | yes      | -                                                                                                                      |
| `action_type`      | `AutomationActionType` | yes      | Canonical automation action type. Allowed values: add_comment, create_task, update_task_status, set_custom_field_value |
| `aggregate_id`     | `string \| null`       | no       | -                                                                                                                      |
| `aggregate_type`   | `string \| null`       | no       | -                                                                                                                      |
| `archived_at`      | `string \| null`       | no       | -                                                                                                                      |
| `cooldown_seconds` | `number`               | yes      | -                                                                                                                      |
| `created_at`       | `string`               | yes      | -                                                                                                                      |
| `description`      | `string \| null`       | no       | -                                                                                                                      |
| `enabled`          | `boolean`              | yes      | -                                                                                                                      |
| `event_pattern`    | `string`               | yes      | -                                                                                                                      |
| `id`               | `string`               | yes      | -                                                                                                                      |
| `name`             | `string`               | yes      | -                                                                                                                      |
| `updated_at`       | `string`               | yes      | -                                                                                                                      |

### `AutomationRuleRunListResponse`

- Kind: `object`
- Description: Response model for automation run lists.

| Field         | Type                        | Required | Description |
| ------------- | --------------------------- | -------- | ----------- |
| `items`       | `AutomationRuleRunResponse` | no       | -           |
| `limit`       | `integer`                   | no       | -           |
| `links`       | `JsonObject`                | no       | -           |
| `next_steps`  | `array<string>`             | no       | -           |
| `offset`      | `integer`                   | no       | -           |
| `params`      | `JsonObject`                | no       | -           |
| `total_count` | `integer`                   | no       | -           |

### `AutomationRuleRunRequest`

- Kind: `object`
- Description: Request model for executing automation rules for an event.

| Field      | Type             | Required | Description |
| ---------- | ---------------- | -------- | ----------- |
| `dry_run`  | `boolean`        | no       | -           |
| `event_id` | `string`         | yes      | -           |
| `rule_id`  | `string \| null` | no       | -           |

### `AutomationRuleRunResponse`

- Kind: `object`
- Description: Response model for automation rule execution.

| Field          | Type                                                           | Required | Description |
| -------------- | -------------------------------------------------------------- | -------- | ----------- |
| `completed_at` | `string \| null`                                               | no       | -           |
| `error`        | `string \| null`                                               | no       | -           |
| `event_id`     | `string \| null`                                               | no       | -           |
| `id`           | `string`                                                       | yes      | -           |
| `output`       | `JsonObject`                                                   | no       | -           |
| `rule_id`      | `string`                                                       | yes      | -           |
| `started_at`   | `string`                                                       | yes      | -           |
| `status`       | `'running' \| 'skipped' \| 'dry_run' \| 'success' \| 'failed'` | yes      | -           |

### `AutomationRuleUpdate`

- Kind: `object`
- Description: Request model for updating an automation rule.

| Field              | Type                 | Required | Description                                                                                                            |
| ------------------ | -------------------- | -------- | ---------------------------------------------------------------------------------------------------------------------- |
| `action_payload`   | `JsonObject \| null` | no       | -                                                                                                                      |
| `action_type`      | `string \| null`     | no       | Canonical automation action type. Allowed values: add_comment, create_task, update_task_status, set_custom_field_value |
| `aggregate_id`     | `string \| null`     | no       | -                                                                                                                      |
| `aggregate_type`   | `string \| null`     | no       | -                                                                                                                      |
| `cooldown_seconds` | `number \| null`     | no       | -                                                                                                                      |
| `description`      | `string \| null`     | no       | -                                                                                                                      |
| `enabled`          | `boolean \| null`    | no       | -                                                                                                                      |
| `event_pattern`    | `string \| null`     | no       | -                                                                                                                      |
| `name`             | `string \| null`     | no       | -                                                                                                                      |

### `AvailableScopesResponse`

- Kind: `object`
- Description: List of available scopes.

| Field    | Type            | Required | Description |
| -------- | --------------- | -------- | ----------- |
| `scopes` | `array<string>` | yes      | -           |

### `AvailableTaskItem`

- Kind: `object`
- Description: Simplified available task payload.

| Field               | Type              | Required | Description |
| ------------------- | ----------------- | -------- | ----------- |
| `complexity_points` | `integer \| null` | yes      | -           |
| `id`                | `string`          | yes      | -           |
| `priority`          | `string`          | yes      | -           |
| `project_id`        | `string \| null`  | yes      | -           |
| `title`             | `string`          | yes      | -           |

### `AvailableTasksResponse`

- Kind: `object`
- Description: Available checkouts response.

| Field             | Type                | Required | Description |
| ----------------- | ------------------- | -------- | ----------- |
| `available_tasks` | `AvailableTaskItem` | yes      | -           |
| `count`           | `integer`           | yes      | -           |

### `ChangeType`

- Kind: `enum`
- Description: Type of change in a revision.
- Allowed values: `'create'`, `'update'`, `'delete'`, `'restore'`
- Top-level fields: _none_

### `CheckoutCleanupResponse`

- Kind: `object`
- Description: Cleanup checkouts response.

| Field              | Type            | Required | Description |
| ------------------ | --------------- | -------- | ----------- |
| `count`            | `integer`       | yes      | -           |
| `dry_run`          | `boolean`       | yes      | -           |
| `expired_task_ids` | `array<string>` | yes      | -           |

### `CheckoutLogResponse`

- Kind: `object`
- Description: Checkout log response.

| Field     | Type         | Required | Description |
| --------- | ------------ | -------- | ----------- |
| `count`   | `integer`    | yes      | -           |
| `entries` | `JsonObject` | yes      | -           |

### `CheckoutPayload`

- Kind: `object`
- Description: Resolved checkout identity and lease payload.

| Field              | Type                            | Required | Description |
| ------------------ | ------------------------------- | -------- | ----------- |
| `actor`            | `ActorReferencePayload \| null` | no       | -           |
| `agent_session_id` | `string \| null`                | no       | -           |
| `checked_out_at`   | `string \| null`                | no       | -           |
| `expired`          | `boolean \| null`               | no       | -           |
| `lease_until`      | `string \| null`                | no       | -           |
| `version`          | `integer \| null`               | no       | -           |

### `CheckoutRequest`

- Kind: `object`
- Description: Request model for checking out a task.

| Field              | Type             | Required | Description |
| ------------------ | ---------------- | -------- | ----------- |
| `actor`            | `string \| null` | no       | -           |
| `agent_session_id` | `string`         | yes      | -           |
| `lease_seconds`    | `integer`        | no       | -           |

### `CheckoutResponse`

- Kind: `object`
- Description: Response model for checkout operation.

| Field      | Type              | Required | Description |
| ---------- | ----------------- | -------- | ----------- |
| `checkout` | `CheckoutPayload` | yes      | -           |
| `task_id`  | `string`          | yes      | -           |

### `CheckoutStatusItem`

- Kind: `object`
- Description: Checkout status row.

| Field        | Type                 | Required | Description |
| ------------ | -------------------- | -------- | ----------- |
| `checkout`   | `JsonObject \| null` | yes      | -           |
| `id`         | `string`             | yes      | -           |
| `project_id` | `string \| null`     | yes      | -           |
| `title`      | `string`             | yes      | -           |

### `CheckoutStatusResponse`

- Kind: `object`
- Description: Checkout status response.

| Field              | Type                 | Required | Description |
| ------------------ | -------------------- | -------- | ----------- |
| `agent_session_id` | `string`             | yes      | -           |
| `checkouts`        | `CheckoutStatusItem` | yes      | -           |
| `count`            | `integer`            | yes      | -           |

### `CommentCreate`

- Kind: `object`
- Description: Request model for creating a comment.

| Field         | Type            | Required | Description |
| ------------- | --------------- | -------- | ----------- |
| `body`        | `string`        | yes      | -           |
| `created_by`  | `string`        | yes      | -           |
| `entity_id`   | `string`        | yes      | -           |
| `entity_type` | `string`        | yes      | -           |
| `mentions`    | `array<string>` | no       | -           |
| `metadata`    | `JsonObject`    | no       | -           |
| `watch`       | `boolean`       | no       | -           |

### `CommentListResponse`

- Kind: `object`
- Description: Response model for comment lists.

| Field         | Type              | Required | Description |
| ------------- | ----------------- | -------- | ----------- |
| `items`       | `CommentResponse` | no       | -           |
| `limit`       | `integer`         | no       | -           |
| `links`       | `JsonObject`      | no       | -           |
| `next_steps`  | `array<string>`   | no       | -           |
| `offset`      | `integer`         | no       | -           |
| `params`      | `JsonObject`      | no       | -           |
| `total_count` | `integer`         | no       | -           |

### `CommentResponse`

- Kind: `object`
- Description: Response model for a comment.

| Field         | Type             | Required | Description |
| ------------- | ---------------- | -------- | ----------- |
| `archived_at` | `string \| null` | no       | -           |
| `body`        | `string`         | yes      | -           |
| `created_at`  | `string`         | yes      | -           |
| `created_by`  | `string`         | yes      | -           |
| `entity_id`   | `string`         | yes      | -           |
| `entity_type` | `string`         | yes      | -           |
| `id`          | `string`         | yes      | -           |
| `mentions`    | `array<string>`  | no       | -           |
| `metadata`    | `JsonObject`     | yes      | -           |
| `updated_at`  | `string`         | yes      | -           |

### `CompletionContextResponse`

- Kind: `object`
- Description: Completion context for terminal operator views.

| Field        | Type            | Required | Description |
| ------------ | --------------- | -------- | ----------- |
| `next_steps` | `array<string>` | no       | -           |
| `summary`    | `string`        | yes      | -           |

### `CreateApiKeyRequest`

- Kind: `object`
- Description: Request to create a new API key.

| Field             | Type                  | Required | Description |
| ----------------- | --------------------- | -------- | ----------- |
| `expires_in_days` | `integer \| null`     | no       | -           |
| `metadata`        | `map<string, string>` | no       | -           |
| `name`            | `string`              | yes      | -           |
| `rate_limit`      | `integer \| null`     | no       | -           |
| `scopes`          | `array<string>`       | yes      | -           |

### `CreateApiKeyResponse`

- Kind: `object`
- Description: Response when creating an API key (includes plain key).

| Field      | Type             | Required | Description |
| ---------- | ---------------- | -------- | ----------- |
| `api_key`  | `string`         | yes      | -           |
| `key_info` | `ApiKeyResponse` | yes      | -           |

### `CustomFieldDefinitionCreate`

- Kind: `object`
- Description: Request model for creating a custom field definition.

| Field         | Type             | Required | Description |
| ------------- | ---------------- | -------- | ----------- |
| `description` | `string \| null` | no       | -           |
| `entity_type` | `string`         | yes      | -           |
| `field_type`  | `string`         | yes      | -           |
| `is_required` | `boolean`        | no       | -           |
| `name`        | `string`         | yes      | -           |
| `options`     | `array<string>`  | no       | -           |

### `CustomFieldDefinitionResponse`

- Kind: `object`
- Description: Response model for custom field definitions.

| Field         | Type              | Required | Description |
| ------------- | ----------------- | -------- | ----------- |
| `archived_at` | `string \| null`  | no       | -           |
| `created_at`  | `string`          | yes      | -           |
| `description` | `string \| null`  | yes      | -           |
| `entity_type` | `string`          | yes      | -           |
| `field_type`  | `CustomFieldType` | yes      | -           |
| `id`          | `string`          | yes      | -           |
| `is_required` | `boolean`         | yes      | -           |
| `name`        | `string`          | yes      | -           |
| `options`     | `array<string>`   | yes      | -           |
| `updated_at`  | `string`          | yes      | -           |

### `CustomFieldDefinitionUpdate`

- Kind: `object`
- Description: Request model for updating a custom field definition.

| Field         | Type                    | Required | Description |
| ------------- | ----------------------- | -------- | ----------- |
| `description` | `string \| null`        | no       | -           |
| `field_type`  | `string \| null`        | no       | -           |
| `is_required` | `boolean \| null`       | no       | -           |
| `name`        | `string \| null`        | no       | -           |
| `options`     | `array<string> \| null` | no       | -           |

### `CustomFieldType`

- Kind: `enum`
- Description: Supported custom field types.
- Allowed values: `'text'`, `'number'`, `'boolean'`, `'date'`, `'datetime'`, `'enum'`, `'json'`, `'url'`
- Top-level fields: _none_

### `CustomFieldValueCreate`

- Kind: `object`
- Description: Request model for setting a custom field value.

| Field         | Type             | Required | Description |
| ------------- | ---------------- | -------- | ----------- |
| `created_by`  | `string \| null` | no       | -           |
| `entity_id`   | `string`         | yes      | -           |
| `entity_type` | `string`         | yes      | -           |
| `metadata`    | `JsonObject`     | no       | -           |
| `source`      | `string \| null` | no       | -           |
| `value`       | `JsonValue`      | yes      | -           |

### `CustomFieldValueItemResponse`

- Kind: `object`
- Description: Response model combining definition + value.

| Field        | Type                                    | Required | Description |
| ------------ | --------------------------------------- | -------- | ----------- |
| `definition` | `CustomFieldDefinitionResponse \| null` | yes      | -           |
| `value`      | `CustomFieldValueResponse`              | yes      | -           |

### `CustomFieldValueResponse`

- Kind: `object`
- Description: Response model for custom field values.

| Field         | Type             | Required | Description |
| ------------- | ---------------- | -------- | ----------- |
| `created_at`  | `string`         | yes      | -           |
| `created_by`  | `string \| null` | yes      | -           |
| `entity_id`   | `string`         | yes      | -           |
| `entity_type` | `string`         | yes      | -           |
| `field_id`    | `string`         | yes      | -           |
| `id`          | `string`         | yes      | -           |
| `metadata`    | `JsonObject`     | yes      | -           |
| `source`      | `string \| null` | yes      | -           |
| `value`       | `JsonValue`      | yes      | -           |

### `CustomFieldValuesResponse`

- Kind: `object`
- Description: Response model for custom field value lists.

| Field         | Type                           | Required | Description |
| ------------- | ------------------------------ | -------- | ----------- |
| `items`       | `CustomFieldValueItemResponse` | no       | -           |
| `limit`       | `integer`                      | no       | -           |
| `offset`      | `integer`                      | no       | -           |
| `total_count` | `integer`                      | no       | -           |

### `DeleteEvidenceGateRuleResponse`

- Kind: `object`
- Description: Delete response payload for evidence gate rules.

| Field    | Type     | Required | Description |
| -------- | -------- | -------- | ----------- |
| `id`     | `string` | yes      | -           |
| `status` | `string` | yes      | -           |

### `DiscoverabilityGraphEdgePayload`

- Kind: `object`
- Description: Directed continuation edge in discoverability graph.

| Field       | Type     | Required | Description |
| ----------- | -------- | -------- | ----------- |
| `from_node` | `string` | yes      | -           |
| `reason`    | `string` | yes      | -           |
| `to_node`   | `string` | yes      | -           |

### `DiscoverabilityGraphLinksPayload`

- Kind: `object`
- Description: Discoverability graph continuation links.

| Field           | Type     | Required | Description |
| --------------- | -------- | -------- | ----------- |
| `api_reference` | `string` | yes      | -           |
| `auth_scopes`   | `string` | yes      | -           |
| `root`          | `string` | yes      | -           |
| `self`          | `string` | yes      | -           |
| `web_api`       | `string` | yes      | -           |

### `DiscoverabilityGraphNodePayload`

- Kind: `object`
- Description: Single node in discoverability graph output.

| Field       | Type            | Required | Description |
| ----------- | --------------- | -------- | ----------- |
| `category`  | `string`        | yes      | -           |
| `id`        | `string`        | yes      | -           |
| `method`    | `string`        | yes      | -           |
| `name`      | `string`        | yes      | -           |
| `path`      | `string`        | yes      | -           |
| `what_next` | `array<string>` | yes      | -           |
| `why`       | `string`        | yes      | -           |

### `DiscoverabilityGraphParamsPayload`

- Kind: `object`
- Description: Echoed query params for discoverability graph requests.

| Field                   | Type             | Required | Description |
| ----------------------- | ---------------- | -------- | ----------- |
| `include_entry_points`  | `boolean`        | yes      | -           |
| `include_observability` | `boolean`        | yes      | -           |
| `include_scenarios`     | `boolean`        | yes      | -           |
| `max_next_steps`        | `integer`        | yes      | -           |
| `path_contains`         | `string \| null` | yes      | -           |

### `DiscoverabilityGraphPayload`

- Kind: `object`
- Description: Discoverability graph endpoint response payload.

| Field          | Type                                | Required | Description |
| -------------- | ----------------------------------- | -------- | ----------- |
| `edges`        | `DiscoverabilityGraphEdgePayload`   | yes      | -           |
| `generated_at` | `string`                            | yes      | -           |
| `links`        | `DiscoverabilityGraphLinksPayload`  | yes      | -           |
| `next_steps`   | `array<string>`                     | yes      | -           |
| `nodes`        | `DiscoverabilityGraphNodePayload`   | yes      | -           |
| `params`       | `DiscoverabilityGraphParamsPayload` | yes      | -           |
| `scenarios`    | `RootScenarioPayload`               | yes      | -           |

### `DuplicateMergeConflictResponse`

- Kind: `object`
- Description: Response model for duplicate merge conflicts.

| Field               | Type        | Required | Description |
| ------------------- | ----------- | -------- | ----------- |
| `duplicate_task_id` | `string`    | yes      | -           |
| `duplicate_value`   | `JsonValue` | yes      | -           |
| `field`             | `string`    | yes      | -           |
| `primary_value`     | `JsonValue` | yes      | -           |

### `DuplicateMergePreviewItemResponse`

- Kind: `object`
- Description: Response model for a duplicate task preview.

| Field            | Type                             | Required | Description |
| ---------------- | -------------------------------- | -------- | ----------- |
| `already_linked` | `boolean`                        | yes      | -           |
| `conflicts`      | `DuplicateMergeConflictResponse` | no       | -           |
| `task`           | `TaskResponse`                   | yes      | -           |

### `DuplicateMergePreviewResponse`

- Kind: `object`
- Description: Response model for duplicate merge preview.

| Field                      | Type                                | Required | Description |
| -------------------------- | ----------------------------------- | -------- | ----------- |
| `can_merge`                | `boolean`                           | yes      | -           |
| `duplicates`               | `DuplicateMergePreviewItemResponse` | no       | -           |
| `links`                    | `JsonObject`                        | no       | -           |
| `missing_ids`              | `array<string>`                     | no       | -           |
| `next_steps`               | `array<string>`                     | no       | -           |
| `primary_task`             | `TaskResponse`                      | yes      | -           |
| `suggested_primary_id`     | `string \| null`                    | no       | -           |
| `suggested_primary_reason` | `string \| null`                    | no       | -           |
| `warnings`                 | `array<string>`                     | no       | -           |

### `DuplicateTaskGroupPayload`

- Kind: `object`
- Description: Duplicate task group payload.

| Field                      | Type                          | Required | Description |
| -------------------------- | ----------------------------- | -------- | ----------- |
| `count`                    | `integer`                     | yes      | -           |
| `last_activity_at`         | `string \| null`              | yes      | -           |
| `links`                    | `map<string, string \| null>` | yes      | -           |
| `next_steps`               | `array<string>`               | yes      | -           |
| `normalized_title`         | `string`                      | yes      | -           |
| `suggested_primary_id`     | `string \| null`              | yes      | -           |
| `suggested_primary_reason` | `string \| null`              | yes      | -           |
| `tasks`                    | `TaskResponse`                | yes      | -           |

### `DuplicateTaskListResponsePayload`

- Kind: `object`
- Description: Duplicate task list response payload.

| Field         | Type                                                                 | Required | Description |
| ------------- | -------------------------------------------------------------------- | -------- | ----------- |
| `items`       | `DuplicateTaskGroupPayload`                                          | yes      | -           |
| `limit`       | `integer`                                                            | yes      | -           |
| `links`       | `map<string, string \| null>`                                        | yes      | -           |
| `next_steps`  | `array<string>`                                                      | yes      | -           |
| `offset`      | `integer`                                                            | yes      | -           |
| `params`      | `map<string, string \| integer \| boolean \| array<string> \| null>` | yes      | -           |
| `total_count` | `integer`                                                            | yes      | -           |

### `EnvVarPair`

- Kind: `object`
- Description: Key/value environment variable pair.

| Field   | Type     | Required | Description |
| ------- | -------- | -------- | ----------- |
| `key`   | `string` | yes      | -           |
| `value` | `string` | yes      | -           |

### `EvidenceGateIndicatorResponse`

- Kind: `object`
- Description: Response model for evidence gate indicators.

| Field                 | Type            | Required | Description |
| --------------------- | --------------- | -------- | ----------- |
| `blocked`             | `boolean`       | yes      | -           |
| `blocked_transitions` | `array<string>` | no       | -           |
| `reasons`             | `array<string>` | no       | -           |

### `EvidenceGateRuleCreate`

- Kind: `object`
- Description: Request model for creating an evidence gate rule.

| Field             | Type             | Required | Description |
| ----------------- | ---------------- | -------- | ----------- |
| `entity_type`     | `string`         | yes      | -           |
| `evidence_type`   | `string`         | yes      | -           |
| `from_state`      | `string`         | yes      | -           |
| `message`         | `string \| null` | no       | -           |
| `min_count`       | `integer`        | no       | -           |
| `require_success` | `boolean`        | no       | -           |
| `to_state`        | `string`         | yes      | -           |
| `workflow_id`     | `string`         | yes      | -           |

### `EvidenceGateRuleResponse`

- Kind: `object`
- Description: Response model for evidence gate rule.

| Field             | Type             | Required | Description |
| ----------------- | ---------------- | -------- | ----------- |
| `created_at`      | `string`         | yes      | -           |
| `entity_type`     | `string`         | yes      | -           |
| `evidence_type`   | `string`         | yes      | -           |
| `from_state`      | `string`         | yes      | -           |
| `id`              | `string`         | yes      | -           |
| `message`         | `string \| null` | yes      | -           |
| `min_count`       | `integer`        | yes      | -           |
| `require_success` | `boolean`        | yes      | -           |
| `to_state`        | `string`         | yes      | -           |
| `workflow_id`     | `string`         | yes      | -           |

### `GoalCreate`

- Kind: `object`
- Description: Request model for creating a goal.

| Field              | Type             | Required | Description |
| ------------------ | ---------------- | -------- | ----------- |
| `description`      | `string \| null` | no       | -           |
| `horizon`          | `string`         | no       | -           |
| `name`             | `string`         | yes      | -           |
| `owner`            | `string \| null` | no       | -           |
| `product_id`       | `string \| null` | no       | -           |
| `progress_percent` | `integer`        | no       | -           |
| `project_id`       | `string \| null` | no       | -           |
| `tags`             | `array<string>`  | no       | -           |
| `target_date`      | `string \| null` | no       | -           |

### `GoalDetailResponse`

- Kind: `object`
- Description: Lifecycle-aware goal detail payload.

| Field                 | Type                                   | Required | Description |
| --------------------- | -------------------------------------- | -------- | ----------- |
| `completion_context`  | `CompletionContextResponse \| null`    | no       | -           |
| `created_at`          | `string`                               | yes      | -           |
| `current_state`       | `string \| null`                       | yes      | -           |
| `description`         | `string \| null`                       | yes      | -           |
| `effective_hierarchy` | `GoalEffectiveHierarchyResponse`       | yes      | -           |
| `effective_rollup`    | `GoalEffectiveRollupResponse \| null`  | no       | -           |
| `execution`           | `GoalExecutionSummaryResponse \| null` | no       | -           |
| `horizon`             | `GoalHorizon`                          | yes      | -           |
| `id`                  | `string`                               | yes      | -           |
| `last_activity_at`    | `string \| null`                       | no       | -           |
| `last_transition_at`  | `string \| null`                       | no       | -           |
| `links`               | `JsonObject`                           | no       | -           |
| `name`                | `string`                               | yes      | -           |
| `next_steps`          | `array<string>`                        | no       | -           |
| `owner`               | `ActorReferencePayload \| null`        | no       | -           |
| `product_id`          | `string \| null`                       | yes      | -           |
| `progress_percent`    | `integer`                              | yes      | -           |
| `project_id`          | `string \| null`                       | yes      | -           |
| `stats`               | `GoalSummaryStatsResponse`             | yes      | -           |
| `status`              | `GoalStatus`                           | yes      | -           |
| `tags`                | `array<string>`                        | yes      | -           |
| `target_date`         | `string \| null`                       | yes      | -           |
| `terminal_reason`     | `string \| null`                       | no       | -           |
| `updated_at`          | `string`                               | yes      | -           |
| `workflow_id`         | `string \| null`                       | yes      | -           |

### `GoalEffectiveHierarchyResponse`

- Kind: `object`
- Description: Execution-aware hierarchy rollup for a goal.

| Field                   | Type             | Required | Description |
| ----------------------- | ---------------- | -------- | ----------- |
| `average_progress`      | `number`         | yes      | -           |
| `basis`                 | `string`         | yes      | -           |
| `completed_key_results` | `integer`        | yes      | -           |
| `completed_objectives`  | `integer`        | yes      | -           |
| `key_result_count`      | `integer`        | yes      | -           |
| `objective_count`       | `integer`        | yes      | -           |
| `reason`                | `string \| null` | no       | -           |

### `GoalEffectiveRollupResponse`

- Kind: `object`
- Description: Execution-aware effective goal rollup.

| Field              | Type             | Required | Description |
| ------------------ | ---------------- | -------- | ----------- |
| `basis`            | `string`         | yes      | -           |
| `progress_percent` | `integer`        | yes      | -           |
| `reason`           | `string \| null` | no       | -           |
| `status`           | `string`         | yes      | -           |

### `GoalExecutionFocusTaskResponse`

- Kind: `object`
- Description: Minimal operator focus payload for goal execution.

| Field                       | Type      | Required | Description |
| --------------------------- | --------- | -------- | ----------- |
| `completion_criteria_count` | `integer` | yes      | -           |
| `current_progress_percent`  | `integer` | yes      | -           |
| `has_completion_criteria`   | `boolean` | yes      | -           |
| `id`                        | `string`  | yes      | -           |
| `reason`                    | `string`  | yes      | -           |
| `status`                    | `string`  | yes      | -           |
| `title`                     | `string`  | yes      | -           |

### `GoalExecutionSummaryResponse`

- Kind: `object`
- Description: Execution summary payload for a goal.

| Field                   | Type                                     | Required | Description |
| ----------------------- | ---------------------------------------- | -------- | ----------- |
| `average_task_progress` | `number`                                 | yes      | -           |
| `blocked_tasks`         | `integer`                                | yes      | -           |
| `completed_tasks`       | `integer`                                | yes      | -           |
| `completion_percent`    | `number`                                 | yes      | -           |
| `consistency_reason`    | `string \| null`                         | no       | -           |
| `consistency_status`    | `string`                                 | yes      | -           |
| `focus_task`            | `GoalExecutionFocusTaskResponse \| null` | no       | -           |
| `in_progress_tasks`     | `integer`                                | yes      | -           |
| `population_basis`      | `string`                                 | yes      | -           |
| `readiness_state`       | `string`                                 | yes      | -           |
| `scoped_goal_count`     | `integer`                                | yes      | -           |
| `terminal_reason`       | `string \| null`                         | no       | -           |
| `total_tasks`           | `integer`                                | yes      | -           |

### `GoalHorizon`

- Kind: `enum`
- Description: Time horizon for a goal.
- Allowed values: `'short_term'`, `'medium_term'`, `'long_term'`
- Top-level fields: _none_

### `GoalListItemResponse`

- Kind: `object`
- Description: Lifecycle-aware goal payload used by list surfaces.

| Field                | Type                                  | Required | Description |
| -------------------- | ------------------------------------- | -------- | ----------- |
| `created_at`         | `string`                              | yes      | -           |
| `current_state`      | `string \| null`                      | yes      | -           |
| `description`        | `string \| null`                      | yes      | -           |
| `effective_rollup`   | `GoalEffectiveRollupResponse \| null` | no       | -           |
| `horizon`            | `GoalHorizon`                         | yes      | -           |
| `id`                 | `string`                              | yes      | -           |
| `last_activity_at`   | `string \| null`                      | no       | -           |
| `last_transition_at` | `string \| null`                      | no       | -           |
| `links`              | `JsonObject`                          | no       | -           |
| `name`               | `string`                              | yes      | -           |
| `next_steps`         | `array<string>`                       | no       | -           |
| `owner`              | `ActorReferencePayload \| null`       | no       | -           |
| `product_id`         | `string \| null`                      | yes      | -           |
| `progress_percent`   | `integer`                             | yes      | -           |
| `project_id`         | `string \| null`                      | yes      | -           |
| `status`             | `GoalStatus`                          | yes      | -           |
| `tags`               | `array<string>`                       | yes      | -           |
| `target_date`        | `string \| null`                      | yes      | -           |
| `terminal_reason`    | `string \| null`                      | no       | -           |
| `updated_at`         | `string`                              | yes      | -           |
| `workflow_id`        | `string \| null`                      | yes      | -           |

### `GoalResponse`

- Kind: `object`
- Description: Response model for goal.

| Field              | Type                            | Required | Description |
| ------------------ | ------------------------------- | -------- | ----------- |
| `created_at`       | `string`                        | yes      | -           |
| `current_state`    | `string \| null`                | yes      | -           |
| `description`      | `string \| null`                | yes      | -           |
| `horizon`          | `GoalHorizon`                   | yes      | -           |
| `id`               | `string`                        | yes      | -           |
| `name`             | `string`                        | yes      | -           |
| `owner`            | `ActorReferencePayload \| null` | no       | -           |
| `product_id`       | `string \| null`                | yes      | -           |
| `progress_percent` | `integer`                       | yes      | -           |
| `project_id`       | `string \| null`                | yes      | -           |
| `status`           | `GoalStatus`                    | yes      | -           |
| `tags`             | `array<string>`                 | yes      | -           |
| `target_date`      | `string \| null`                | yes      | -           |
| `updated_at`       | `string`                        | yes      | -           |
| `workflow_id`      | `string \| null`                | yes      | -           |

### `GoalStatus`

- Kind: `enum`
- Description: Status of a goal.
- Allowed values: `'active'`, `'completed'`, `'on_hold'`, `'archived'`
- Top-level fields: _none_

### `GoalSummaryResponse`

- Kind: `object`
- Description: Goal summary payload.

| Field                 | Type                                   | Required | Description |
| --------------------- | -------------------------------------- | -------- | ----------- |
| `completion_context`  | `CompletionContextResponse \| null`    | no       | -           |
| `effective_hierarchy` | `GoalEffectiveHierarchyResponse`       | yes      | -           |
| `effective_rollup`    | `GoalEffectiveRollupResponse`          | yes      | -           |
| `execution`           | `GoalExecutionSummaryResponse \| null` | no       | -           |
| `goal`                | `GoalResponse`                         | yes      | -           |
| `last_activity_at`    | `string \| null`                       | no       | -           |
| `last_transition_at`  | `string \| null`                       | no       | -           |
| `links`               | `JsonObject`                           | no       | -           |
| `next_steps`          | `array<string>`                        | no       | -           |
| `stats`               | `GoalSummaryStatsResponse`             | yes      | -           |
| `terminal_reason`     | `string \| null`                       | no       | -           |

### `GoalSummaryStatsResponse`

- Kind: `object`
- Description: Rollup statistics for a goal summary.

| Field                   | Type      | Required | Description |
| ----------------------- | --------- | -------- | ----------- |
| `average_progress`      | `number`  | yes      | -           |
| `completed_key_results` | `integer` | yes      | -           |
| `completed_objectives`  | `integer` | yes      | -           |
| `key_result_count`      | `integer` | yes      | -           |
| `objective_count`       | `integer` | yes      | -           |

### `GoalUpdate`

- Kind: `object`
- Description: Request model for updating a goal.

| Field              | Type                    | Required | Description |
| ------------------ | ----------------------- | -------- | ----------- |
| `description`      | `string \| null`        | no       | -           |
| `horizon`          | `string \| null`        | no       | -           |
| `name`             | `string \| null`        | no       | -           |
| `owner`            | `string \| null`        | no       | -           |
| `product_id`       | `string \| null`        | no       | -           |
| `progress_percent` | `integer \| null`       | no       | -           |
| `project_id`       | `string \| null`        | no       | -           |
| `status`           | `string \| null`        | no       | -           |
| `tags`             | `array<string> \| null` | no       | -           |
| `target_date`      | `string \| null`        | no       | -           |

### `HealthCheckPayload`

- Kind: `object`
- Description: Health check response payload.

| Field            | Type                      | Required | Description |
| ---------------- | ------------------------- | -------- | ----------- |
| `backend`        | `string`                  | yes      | -           |
| `database`       | `string`                  | yes      | -           |
| `schema_name`    | `string`                  | yes      | -           |
| `schema_version` | `integer`                 | yes      | -           |
| `status`         | `'healthy' \| 'degraded'` | yes      | -           |
| `uptime_seconds` | `number`                  | yes      | -           |

### `InitApiKeyRequest`

- Kind: `object`
- Description: Request to initialize the first admin API key.

| Field  | Type     | Required | Description |
| ------ | -------- | -------- | ----------- |
| `name` | `string` | no       | -           |

### `KeyResultCreate`

- Kind: `object`
- Description: Request model for creating a key result.

| Field              | Type              | Required | Description |
| ------------------ | ----------------- | -------- | ----------- |
| `current_value`    | `number \| null`  | no       | -           |
| `description`      | `string \| null`  | no       | -           |
| `name`             | `string`          | yes      | -           |
| `owner`            | `string \| null`  | no       | -           |
| `progress_percent` | `integer \| null` | no       | -           |
| `tags`             | `array<string>`   | no       | -           |
| `target_value`     | `number \| null`  | no       | -           |
| `unit`             | `string \| null`  | no       | -           |

### `KeyResultDetailResponse`

- Kind: `object`
- Description: Lifecycle-aware key result detail payload.

| Field                | Type                                       | Required | Description |
| -------------------- | ------------------------------------------ | -------- | ----------- |
| `completion_context` | `CompletionContextResponse \| null`        | no       | -           |
| `created_at`         | `string`                                   | yes      | -           |
| `current_value`      | `number \| null`                           | yes      | -           |
| `description`        | `string \| null`                           | yes      | -           |
| `effective_rollup`   | `KeyResultEffectiveRollupResponse \| null` | no       | -           |
| `goal_id`            | `string`                                   | yes      | -           |
| `id`                 | `string`                                   | yes      | -           |
| `last_activity_at`   | `string \| null`                           | no       | -           |
| `last_transition_at` | `string \| null`                           | no       | -           |
| `links`              | `JsonObject`                               | no       | -           |
| `name`               | `string`                                   | yes      | -           |
| `next_steps`         | `array<string>`                            | no       | -           |
| `objective_id`       | `string`                                   | yes      | -           |
| `owner`              | `ActorReferencePayload \| null`            | no       | -           |
| `progress_percent`   | `integer`                                  | yes      | -           |
| `project_id`         | `string \| null`                           | no       | -           |
| `status`             | `GoalStatus`                               | yes      | -           |
| `tags`               | `array<string>`                            | yes      | -           |
| `target_value`       | `number \| null`                           | yes      | -           |
| `terminal_reason`    | `string \| null`                           | no       | -           |
| `unit`               | `string \| null`                           | yes      | -           |
| `updated_at`         | `string`                                   | yes      | -           |

### `KeyResultEffectiveRollupResponse`

- Kind: `object`
- Description: Lifecycle rollup for one key result leaf.

| Field              | Type             | Required | Description |
| ------------------ | ---------------- | -------- | ----------- |
| `basis`            | `string`         | yes      | -           |
| `progress_percent` | `integer`        | yes      | -           |
| `reason`           | `string \| null` | no       | -           |
| `status`           | `string`         | yes      | -           |

### `KeyResultListItemResponse`

- Kind: `object`
- Description: Lifecycle-aware key result payload used by list surfaces.

| Field                | Type                                       | Required | Description |
| -------------------- | ------------------------------------------ | -------- | ----------- |
| `created_at`         | `string`                                   | yes      | -           |
| `current_value`      | `number \| null`                           | yes      | -           |
| `description`        | `string \| null`                           | yes      | -           |
| `effective_rollup`   | `KeyResultEffectiveRollupResponse \| null` | no       | -           |
| `goal_id`            | `string`                                   | yes      | -           |
| `id`                 | `string`                                   | yes      | -           |
| `last_activity_at`   | `string \| null`                           | no       | -           |
| `last_transition_at` | `string \| null`                           | no       | -           |
| `links`              | `JsonObject`                               | no       | -           |
| `name`               | `string`                                   | yes      | -           |
| `next_steps`         | `array<string>`                            | no       | -           |
| `objective_id`       | `string`                                   | yes      | -           |
| `owner`              | `ActorReferencePayload \| null`            | no       | -           |
| `progress_percent`   | `integer`                                  | yes      | -           |
| `project_id`         | `string \| null`                           | no       | -           |
| `status`             | `GoalStatus`                               | yes      | -           |
| `tags`               | `array<string>`                            | yes      | -           |
| `target_value`       | `number \| null`                           | yes      | -           |
| `terminal_reason`    | `string \| null`                           | no       | -           |
| `unit`               | `string \| null`                           | yes      | -           |
| `updated_at`         | `string`                                   | yes      | -           |

### `KeyResultResponse`

- Kind: `object`
- Description: Response model for key result.

| Field              | Type                            | Required | Description |
| ------------------ | ------------------------------- | -------- | ----------- |
| `created_at`       | `string`                        | yes      | -           |
| `current_value`    | `number \| null`                | yes      | -           |
| `description`      | `string \| null`                | yes      | -           |
| `id`               | `string`                        | yes      | -           |
| `name`             | `string`                        | yes      | -           |
| `objective_id`     | `string`                        | yes      | -           |
| `owner`            | `ActorReferencePayload \| null` | no       | -           |
| `progress_percent` | `integer`                       | yes      | -           |
| `status`           | `GoalStatus`                    | yes      | -           |
| `tags`             | `array<string>`                 | yes      | -           |
| `target_value`     | `number \| null`                | yes      | -           |
| `unit`             | `string \| null`                | yes      | -           |
| `updated_at`       | `string`                        | yes      | -           |

### `KeyResultUpdate`

- Kind: `object`
- Description: Request model for updating a key result.

| Field              | Type                    | Required | Description |
| ------------------ | ----------------------- | -------- | ----------- |
| `current_value`    | `number \| null`        | no       | -           |
| `description`      | `string \| null`        | no       | -           |
| `name`             | `string \| null`        | no       | -           |
| `owner`            | `string \| null`        | no       | -           |
| `progress_percent` | `integer \| null`       | no       | -           |
| `status`           | `string \| null`        | no       | -           |
| `tags`             | `array<string> \| null` | no       | -           |
| `target_value`     | `number \| null`        | no       | -           |
| `unit`             | `string \| null`        | no       | -           |

### `LabelAssignmentCreate`

- Kind: `object`
- Description: Request model for assigning a label to an entity.

| Field         | Type             | Required | Description |
| ------------- | ---------------- | -------- | ----------- |
| `applied_by`  | `string \| null` | no       | -           |
| `entity_id`   | `string`         | yes      | -           |
| `entity_type` | `string`         | yes      | -           |
| `label_id`    | `string`         | yes      | -           |

### `LabelAssignmentHistoryResponsePayload`

- Kind: `object`
- Description: Label assignment history response payload.

| Field        | Type                          | Required | Description |
| ------------ | ----------------------------- | -------- | ----------- |
| `assignment` | `LabelAssignmentInfoPayload`  | yes      | -           |
| `items`      | `JsonObject`                  | yes      | -           |
| `page`       | `LabelAssignmentsPagePayload` | yes      | -           |

### `LabelAssignmentInfoPayload`

- Kind: `object`
- Description: Label assignment metadata payload.

| Field         | Type             | Required | Description |
| ------------- | ---------------- | -------- | ----------- |
| `applied_at`  | `string`         | yes      | -           |
| `applied_by`  | `string \| null` | yes      | -           |
| `created_at`  | `string`         | yes      | -           |
| `entity_id`   | `string`         | yes      | -           |
| `entity_type` | `string`         | yes      | -           |
| `id`          | `string`         | yes      | -           |
| `label_id`    | `string`         | yes      | -           |
| `updated_at`  | `string`         | yes      | -           |

### `LabelAssignmentListItemPayload`

- Kind: `object`
- Description: Label with label-assignment metadata.

| Field         | Type                         | Required | Description |
| ------------- | ---------------------------- | -------- | ----------- |
| `archived_at` | `string \| null`             | yes      | -           |
| `assignment`  | `LabelAssignmentInfoPayload` | yes      | -           |
| `category_id` | `string \| null`             | yes      | -           |
| `color`       | `string \| null`             | yes      | -           |
| `created_at`  | `string`                     | yes      | -           |
| `description` | `string \| null`             | yes      | -           |
| `id`          | `string`                     | yes      | -           |
| `is_system`   | `boolean`                    | yes      | -           |
| `name`        | `string`                     | yes      | -           |
| `updated_at`  | `string`                     | yes      | -           |

### `LabelAssignmentResponse`

- Kind: `object`
- Description: Response model for label assignment.

| Field         | Type             | Required | Description |
| ------------- | ---------------- | -------- | ----------- |
| `applied_at`  | `string`         | yes      | -           |
| `applied_by`  | `string \| null` | yes      | -           |
| `entity_id`   | `string`         | yes      | -           |
| `entity_type` | `string`         | yes      | -           |
| `id`          | `string`         | yes      | -           |
| `label_id`    | `string`         | yes      | -           |

### `LabelAssignmentsPagePayload`

- Kind: `object`
- Description: Pagination metadata for label assignments.

| Field         | Type              | Required | Description |
| ------------- | ----------------- | -------- | ----------- |
| `has_more`    | `boolean`         | yes      | -           |
| `limit`       | `integer`         | yes      | -           |
| `next_offset` | `integer \| null` | yes      | -           |
| `offset`      | `integer`         | yes      | -           |
| `total_count` | `integer`         | yes      | -           |

### `LabelAssignmentsResponsePayload`

- Kind: `object`
- Description: Label assignments response payload.

| Field   | Type                             | Required | Description |
| ------- | -------------------------------- | -------- | ----------- |
| `items` | `LabelAssignmentListItemPayload` | yes      | -           |
| `page`  | `LabelAssignmentsPagePayload`    | yes      | -           |

### `LabelCategoryCreate`

- Kind: `object`
- Description: Request model for creating a label category.

| Field          | Type             | Required | Description |
| -------------- | ---------------- | -------- | ----------- |
| `description`  | `string \| null` | no       | -           |
| `is_exclusive` | `boolean`        | no       | -           |
| `name`         | `string`         | yes      | -           |
| `sort_order`   | `integer`        | no       | -           |

### `LabelCategoryResponse`

- Kind: `object`
- Description: Response model for label category.

| Field          | Type             | Required | Description |
| -------------- | ---------------- | -------- | ----------- |
| `archived_at`  | `string \| null` | no       | -           |
| `created_at`   | `string`         | yes      | -           |
| `description`  | `string \| null` | yes      | -           |
| `id`           | `string`         | yes      | -           |
| `is_exclusive` | `boolean`        | yes      | -           |
| `name`         | `string`         | yes      | -           |
| `sort_order`   | `integer`        | yes      | -           |
| `updated_at`   | `string`         | yes      | -           |

### `LabelCategoryUpdate`

- Kind: `object`
- Description: Request model for updating a label category.

| Field          | Type              | Required | Description |
| -------------- | ----------------- | -------- | ----------- |
| `description`  | `string \| null`  | no       | -           |
| `is_exclusive` | `boolean \| null` | no       | -           |
| `name`         | `string \| null`  | no       | -           |
| `sort_order`   | `integer \| null` | no       | -           |

### `LabelCreate`

- Kind: `object`
- Description: Request model for creating a label.

| Field         | Type             | Required | Description |
| ------------- | ---------------- | -------- | ----------- |
| `category_id` | `string \| null` | no       | -           |
| `color`       | `string \| null` | no       | -           |
| `description` | `string \| null` | no       | -           |
| `is_system`   | `boolean`        | no       | -           |
| `name`        | `string`         | yes      | -           |

### `LabelGateRuleCreate`

- Kind: `object`
- Description: Request model for creating a label gate rule.

| Field         | Type             | Required | Description |
| ------------- | ---------------- | -------- | ----------- |
| `category_id` | `string \| null` | no       | -           |
| `entity_type` | `string`         | yes      | -           |
| `from_state`  | `string`         | yes      | -           |
| `label_id`    | `string \| null` | no       | -           |
| `message`     | `string \| null` | no       | -           |
| `rule_type`   | `string`         | yes      | -           |
| `to_state`    | `string`         | yes      | -           |
| `workflow_id` | `string`         | yes      | -           |

### `LabelGateRuleResponse`

- Kind: `object`
- Description: Response model for label gate rule.

| Field         | Type                | Required | Description |
| ------------- | ------------------- | -------- | ----------- |
| `category_id` | `string \| null`    | yes      | -           |
| `created_at`  | `string`            | yes      | -           |
| `entity_type` | `string`            | yes      | -           |
| `from_state`  | `string`            | yes      | -           |
| `id`          | `string`            | yes      | -           |
| `label_id`    | `string \| null`    | yes      | -           |
| `message`     | `string \| null`    | yes      | -           |
| `rule_type`   | `LabelGateRuleType` | yes      | -           |
| `to_state`    | `string`            | yes      | -           |
| `workflow_id` | `string`            | yes      | -           |

### `LabelGateRuleType`

- Kind: `enum`
- Description: Types of label gate rules.
- Allowed values: `'require_label'`, `'forbid_label'`, `'require_category'`, `'forbid_category'`
- Top-level fields: _none_

### `LabelResponse`

- Kind: `object`
- Description: Response model for label.

| Field         | Type             | Required | Description |
| ------------- | ---------------- | -------- | ----------- |
| `archived_at` | `string \| null` | no       | -           |
| `category_id` | `string \| null` | yes      | -           |
| `color`       | `string \| null` | yes      | -           |
| `created_at`  | `string`         | yes      | -           |
| `description` | `string \| null` | yes      | -           |
| `id`          | `string`         | yes      | -           |
| `is_system`   | `boolean`        | yes      | -           |
| `name`        | `string`         | yes      | -           |
| `updated_at`  | `string`         | yes      | -           |

### `LabelUpdate`

- Kind: `object`
- Description: Request model for updating a label.

| Field         | Type              | Required | Description |
| ------------- | ----------------- | -------- | ----------- |
| `category_id` | `string \| null`  | no       | -           |
| `color`       | `string \| null`  | no       | -           |
| `description` | `string \| null`  | no       | -           |
| `is_system`   | `boolean \| null` | no       | -           |
| `name`        | `string \| null`  | no       | -           |

### `MergeDuplicateTasksResponsePayload`

- Kind: `object`
- Description: Duplicate merge response payload.

| Field                  | Type                  | Required | Description |
| ---------------------- | --------------------- | -------- | ----------- |
| `duplicate_tasks`      | `TaskResponse`        | yes      | -           |
| `duplicates_cancelled` | `integer`             | yes      | -           |
| `links`                | `map<string, string>` | yes      | -           |
| `links_added`          | `integer`             | yes      | -           |
| `next_steps`           | `array<string>`       | yes      | -           |
| `primary_task`         | `TaskResponse`        | yes      | -           |

### `ObjectiveCreate`

- Kind: `object`
- Description: Request model for creating an objective.

| Field              | Type             | Required | Description |
| ------------------ | ---------------- | -------- | ----------- |
| `description`      | `string \| null` | no       | -           |
| `name`             | `string`         | yes      | -           |
| `owner`            | `string \| null` | no       | -           |
| `progress_percent` | `integer`        | no       | -           |
| `tags`             | `array<string>`  | no       | -           |
| `target_date`      | `string \| null` | no       | -           |

### `ObjectiveDetailResponse`

- Kind: `object`
- Description: Lifecycle-aware objective detail payload.

| Field                 | Type                                          | Required | Description |
| --------------------- | --------------------------------------------- | -------- | ----------- |
| `completion_context`  | `CompletionContextResponse \| null`           | no       | -           |
| `created_at`          | `string`                                      | yes      | -           |
| `current_state`       | `string \| null`                              | yes      | -           |
| `description`         | `string \| null`                              | yes      | -           |
| `effective_hierarchy` | `ObjectiveEffectiveHierarchyResponse \| null` | no       | -           |
| `effective_rollup`    | `ObjectiveEffectiveRollupResponse \| null`    | no       | -           |
| `goal_id`             | `string`                                      | yes      | -           |
| `id`                  | `string`                                      | yes      | -           |
| `last_activity_at`    | `string \| null`                              | no       | -           |
| `last_transition_at`  | `string \| null`                              | no       | -           |
| `links`               | `JsonObject`                                  | no       | -           |
| `name`                | `string`                                      | yes      | -           |
| `next_steps`          | `array<string>`                               | no       | -           |
| `owner`               | `ActorReferencePayload \| null`               | no       | -           |
| `progress_percent`    | `integer`                                     | yes      | -           |
| `project_id`          | `string \| null`                              | no       | -           |
| `stats`               | `ObjectiveSummaryStatsResponse`               | yes      | -           |
| `status`              | `GoalStatus`                                  | yes      | -           |
| `tags`                | `array<string>`                               | yes      | -           |
| `target_date`         | `string \| null`                              | yes      | -           |
| `terminal_reason`     | `string \| null`                              | no       | -           |
| `updated_at`          | `string`                                      | yes      | -           |
| `workflow_id`         | `string \| null`                              | yes      | -           |

### `ObjectiveEffectiveHierarchyResponse`

- Kind: `object`
- Description: Key-result-aware hierarchy rollup for an objective.

| Field                   | Type             | Required | Description |
| ----------------------- | ---------------- | -------- | ----------- |
| `average_progress`      | `number`         | yes      | -           |
| `basis`                 | `string`         | yes      | -           |
| `completed_key_results` | `integer`        | yes      | -           |
| `key_result_count`      | `integer`        | yes      | -           |
| `reason`                | `string \| null` | no       | -           |

### `ObjectiveEffectiveRollupResponse`

- Kind: `object`
- Description: Key-result-aware effective objective rollup.

| Field              | Type             | Required | Description |
| ------------------ | ---------------- | -------- | ----------- |
| `basis`            | `string`         | yes      | -           |
| `progress_percent` | `integer`        | yes      | -           |
| `reason`           | `string \| null` | no       | -           |
| `status`           | `string`         | yes      | -           |

### `ObjectiveListItemResponse`

- Kind: `object`
- Description: Lifecycle-aware objective payload used by list surfaces.

| Field                 | Type                                          | Required | Description |
| --------------------- | --------------------------------------------- | -------- | ----------- |
| `created_at`          | `string`                                      | yes      | -           |
| `current_state`       | `string \| null`                              | yes      | -           |
| `description`         | `string \| null`                              | yes      | -           |
| `effective_hierarchy` | `ObjectiveEffectiveHierarchyResponse \| null` | no       | -           |
| `effective_rollup`    | `ObjectiveEffectiveRollupResponse \| null`    | no       | -           |
| `goal_id`             | `string`                                      | yes      | -           |
| `id`                  | `string`                                      | yes      | -           |
| `last_activity_at`    | `string \| null`                              | no       | -           |
| `last_transition_at`  | `string \| null`                              | no       | -           |
| `links`               | `JsonObject`                                  | no       | -           |
| `name`                | `string`                                      | yes      | -           |
| `next_steps`          | `array<string>`                               | no       | -           |
| `owner`               | `ActorReferencePayload \| null`               | no       | -           |
| `progress_percent`    | `integer`                                     | yes      | -           |
| `project_id`          | `string \| null`                              | no       | -           |
| `status`              | `GoalStatus`                                  | yes      | -           |
| `tags`                | `array<string>`                               | yes      | -           |
| `target_date`         | `string \| null`                              | yes      | -           |
| `terminal_reason`     | `string \| null`                              | no       | -           |
| `updated_at`          | `string`                                      | yes      | -           |
| `workflow_id`         | `string \| null`                              | yes      | -           |

### `ObjectiveResponse`

- Kind: `object`
- Description: Response model for objective.

| Field              | Type                            | Required | Description |
| ------------------ | ------------------------------- | -------- | ----------- |
| `created_at`       | `string`                        | yes      | -           |
| `current_state`    | `string \| null`                | yes      | -           |
| `description`      | `string \| null`                | yes      | -           |
| `goal_id`          | `string`                        | yes      | -           |
| `id`               | `string`                        | yes      | -           |
| `name`             | `string`                        | yes      | -           |
| `owner`            | `ActorReferencePayload \| null` | no       | -           |
| `progress_percent` | `integer`                       | yes      | -           |
| `status`           | `GoalStatus`                    | yes      | -           |
| `tags`             | `array<string>`                 | yes      | -           |
| `target_date`      | `string \| null`                | yes      | -           |
| `updated_at`       | `string`                        | yes      | -           |
| `workflow_id`      | `string \| null`                | yes      | -           |

### `ObjectiveSummaryStatsResponse`

- Kind: `object`
- Description: Rollup statistics for one objective.

| Field                   | Type      | Required | Description |
| ----------------------- | --------- | -------- | ----------- |
| `average_progress`      | `number`  | yes      | -           |
| `completed_key_results` | `integer` | yes      | -           |
| `key_result_count`      | `integer` | yes      | -           |

### `ObjectiveUpdate`

- Kind: `object`
- Description: Request model for updating an objective.

| Field              | Type                    | Required | Description |
| ------------------ | ----------------------- | -------- | ----------- |
| `description`      | `string \| null`        | no       | -           |
| `name`             | `string \| null`        | no       | -           |
| `owner`            | `string \| null`        | no       | -           |
| `progress_percent` | `integer \| null`       | no       | -           |
| `status`           | `string \| null`        | no       | -           |
| `tags`             | `array<string> \| null` | no       | -           |
| `target_date`      | `string \| null`        | no       | -           |

### `ObservabilityAttentionItemPayload`

- Kind: `object`
- Description: Actionable issue surfaced by the observability overview.

| Field         | Type     | Required | Description |
| ------------- | -------- | -------- | ----------- |
| `api_path`    | `string` | yes      | -           |
| `category`    | `string` | yes      | -           |
| `cli_command` | `string` | yes      | -           |
| `id`          | `string` | yes      | -           |
| `severity`    | `string` | yes      | -           |
| `summary`     | `string` | yes      | -           |
| `title`       | `string` | yes      | -           |
| `why`         | `string` | yes      | -           |

### `ObservabilityAttentionSummaryPayload`

- Kind: `object`
- Description: Stable export summary for immediate human or automation triage.

| Field                   | Type      | Required | Description |
| ----------------------- | --------- | -------- | ----------- |
| `highest_severity`      | `string`  | yes      | -           |
| `needs_review_count`    | `integer` | yes      | -           |
| `overall_status`        | `string`  | yes      | -           |
| `stalled_flow_count`    | `integer` | yes      | -           |
| `top_risk_count`        | `integer` | yes      | -           |
| `total_attention_items` | `integer` | yes      | -           |

### `ObservabilityEventTimelinePayload`

- Kind: `object`
- Description: Event activity timeline summary.

| Field         | Type                                     | Required | Description |
| ------------- | ---------------------------------------- | -------- | ----------- |
| `points`      | `ObservabilityEventTimelinePointPayload` | yes      | -           |
| `window_days` | `integer`                                | yes      | -           |

### `ObservabilityEventTimelinePointPayload`

- Kind: `object`
- Description: Single bucket in event activity timeline.

| Field          | Type      | Required | Description |
| -------------- | --------- | -------- | ----------- |
| `bucket_start` | `string`  | yes      | -           |
| `event_count`  | `integer` | yes      | -           |

### `ObservabilityHealthPayload`

- Kind: `object`
- Description: Computed health signal for quick operator triage.

| Field                   | Type      | Required | Description |
| ----------------------- | --------- | -------- | ----------- |
| `blocked_task_ratio`    | `number`  | yes      | -           |
| `completion_ratio`      | `number`  | yes      | -           |
| `overdue_task_ratio`    | `number`  | yes      | -           |
| `retention_alert_count` | `integer` | yes      | -           |
| `status`                | `string`  | yes      | -           |

### `ObservabilityLineagePayload`

- Kind: `object`
- Description: Plan lineage totals for platform observability.

| Field                 | Type      | Required | Description |
| --------------------- | --------- | -------- | ----------- |
| `failed_test_runs`    | `integer` | yes      | -           |
| `total_code_evidence` | `integer` | yes      | -           |
| `total_evidence`      | `integer` | yes      | -           |
| `total_plans`         | `integer` | yes      | -           |
| `total_tasks`         | `integer` | yes      | -           |
| `total_test_runs`     | `integer` | yes      | -           |

### `ObservabilityLinksPayload`

- Kind: `object`
- Description: Continuation links for observability traversal.

| Field                     | Type     | Required | Description |
| ------------------------- | -------- | -------- | ----------- |
| `dashboard`               | `string` | yes      | -           |
| `discoverability_graph`   | `string` | yes      | -           |
| `organizations_dashboard` | `string` | yes      | -           |
| `plans_lineage`           | `string` | yes      | -           |
| `root`                    | `string` | yes      | -           |
| `self`                    | `string` | yes      | -           |
| `test_run_retention`      | `string` | yes      | -           |

### `ObservabilityOrganizationTotalsPayload`

- Kind: `object`
- Description: Organization dashboard totals used by observability overview.

| Field                 | Type      | Required | Description |
| --------------------- | --------- | -------- | ----------- |
| `blocked_tasks`       | `integer` | yes      | -           |
| `total_goals`         | `integer` | yes      | -           |
| `total_objectives`    | `integer` | yes      | -           |
| `total_organizations` | `integer` | yes      | -           |
| `total_portfolios`    | `integer` | yes      | -           |
| `total_programs`      | `integer` | yes      | -           |
| `total_projects`      | `integer` | yes      | -           |
| `total_tasks`         | `integer` | yes      | -           |
| `total_teams`         | `integer` | yes      | -           |

### `ObservabilityOverviewPayload`

- Kind: `object`
- Description: Unified live observability overview payload.

| Field                 | Type                                        | Required | Description |
| --------------------- | ------------------------------------------- | -------- | ----------- |
| `attention_items`     | `ObservabilityAttentionItemPayload`         | yes      | -           |
| `attention_summary`   | `ObservabilityAttentionSummaryPayload`      | yes      | -           |
| `event_timeline`      | `ObservabilityEventTimelinePayload \| null` | yes      | -           |
| `generated_at`        | `string`                                    | yes      | -           |
| `health`              | `ObservabilityHealthPayload`                | yes      | -           |
| `lineage`             | `ObservabilityLineagePayload \| null`       | yes      | -           |
| `links`               | `ObservabilityLinksPayload`                 | yes      | -           |
| `needs_review`        | `ObservabilityAttentionItemPayload`         | yes      | -           |
| `next_steps`          | `array<string>`                             | yes      | -           |
| `params`              | `ObservabilityParamsPayload`                | yes      | -           |
| `permissions`         | `ObservabilityPermissionsPayload`           | yes      | -           |
| `queues`              | `ObservabilityQueuePayload \| null`         | yes      | -           |
| `recommended_actions` | `ObservabilityRecommendedActionPayload`     | yes      | -           |
| `retention`           | `ObservabilityRetentionPayload \| null`     | yes      | -           |
| `rollups`             | `ObservabilityRollupsPayload \| null`       | yes      | -           |
| `stalled_flows`       | `ObservabilityAttentionItemPayload`         | yes      | -           |
| `top_risks_now`       | `ObservabilityAttentionItemPayload`         | yes      | -           |
| `warnings`            | `array<string>`                             | yes      | -           |

### `ObservabilityParamsPayload`

- Kind: `object`
- Description: Echoed request parameters for overview calls.

| Field                    | Type      | Required | Description |
| ------------------------ | --------- | -------- | ----------- |
| `include_event_timeline` | `boolean` | yes      | -           |
| `include_lineage`        | `boolean` | yes      | -           |
| `include_queues`         | `boolean` | yes      | -           |
| `include_retention`      | `boolean` | yes      | -           |
| `include_rollups`        | `boolean` | yes      | -           |
| `lineage_limit`          | `integer` | yes      | -           |
| `queue_limit`            | `integer` | yes      | -           |
| `retention_limit`        | `integer` | yes      | -           |
| `timeline_days`          | `integer` | yes      | -           |

### `ObservabilityPermissionsPayload`

- Kind: `object`
- Description: Section-level visibility map for the current API key.

| Field            | Type      | Required | Description |
| ---------------- | --------- | -------- | ----------- |
| `event_timeline` | `boolean` | yes      | -           |
| `lineage`        | `boolean` | yes      | -           |
| `queues`         | `boolean` | yes      | -           |
| `retention`      | `boolean` | yes      | -           |
| `rollups`        | `boolean` | yes      | -           |

### `ObservabilityPortfolioTotalsPayload`

- Kind: `object`
- Description: Portfolio dashboard totals used by observability overview.

| Field              | Type      | Required | Description |
| ------------------ | --------- | -------- | ----------- |
| `blocked_tasks`    | `integer` | yes      | -           |
| `total_goals`      | `integer` | yes      | -           |
| `total_objectives` | `integer` | yes      | -           |
| `total_portfolios` | `integer` | yes      | -           |
| `total_projects`   | `integer` | yes      | -           |
| `total_tasks`      | `integer` | yes      | -           |

### `ObservabilityProgramTotalsPayload`

- Kind: `object`
- Description: Program dashboard totals used by observability overview.

| Field              | Type      | Required | Description |
| ------------------ | --------- | -------- | ----------- |
| `blocked_tasks`    | `integer` | yes      | -           |
| `total_goals`      | `integer` | yes      | -           |
| `total_objectives` | `integer` | yes      | -           |
| `total_programs`   | `integer` | yes      | -           |
| `total_projects`   | `integer` | yes      | -           |
| `total_tasks`      | `integer` | yes      | -           |

### `ObservabilityProjectTotalsPayload`

- Kind: `object`
- Description: Project dashboard totals used by observability overview.

| Field             | Type      | Required | Description |
| ----------------- | --------- | -------- | ----------- |
| `blocked_tasks`   | `integer` | yes      | -           |
| `completed_tasks` | `integer` | yes      | -           |
| `overdue_tasks`   | `integer` | yes      | -           |
| `population`      | `string`  | yes      | -           |
| `total_projects`  | `integer` | yes      | -           |
| `total_tasks`     | `integer` | yes      | -           |

### `ObservabilityQueuePayload`

- Kind: `object`
- Description: Queue preset summary for observability output.

| Field         | Type                            | Required | Description |
| ------------- | ------------------------------- | -------- | ----------- |
| `description` | `string`                        | yes      | -           |
| `name`        | `string`                        | yes      | -           |
| `samples`     | `ObservabilityQueueTaskPayload` | yes      | -           |
| `total_count` | `integer`                       | yes      | -           |

### `ObservabilityQueueTaskPayload`

- Kind: `object`
- Description: Compact queue task summary.

| Field        | Type             | Required | Description |
| ------------ | ---------------- | -------- | ----------- |
| `due_date`   | `string \| null` | yes      | -           |
| `id`         | `string`         | yes      | -           |
| `priority`   | `string`         | yes      | -           |
| `project_id` | `string`         | yes      | -           |
| `status`     | `string`         | yes      | -           |
| `title`      | `string`         | yes      | -           |
| `updated_at` | `string`         | yes      | -           |

### `ObservabilityRecommendedActionPayload`

- Kind: `object`
- Description: Concrete follow-up action derived from current observability state.

| Field         | Type     | Required | Description |
| ------------- | -------- | -------- | ----------- |
| `api_call`    | `string` | yes      | -           |
| `cli_command` | `string` | yes      | -           |
| `id`          | `string` | yes      | -           |
| `title`       | `string` | yes      | -           |
| `why`         | `string` | yes      | -           |

### `ObservabilityRetentionPayload`

- Kind: `object`
- Description: Retention/storage health summary.

| Field                      | Type      | Required | Description |
| -------------------------- | --------- | -------- | ----------- |
| `alert_count`              | `integer` | yes      | -           |
| `policy_count`             | `integer` | yes      | -           |
| `total_artifact_bytes`     | `integer` | yes      | -           |
| `total_bytes`              | `integer` | yes      | -           |
| `total_log_bytes_combined` | `integer` | yes      | -           |
| `total_runs`               | `integer` | yes      | -           |

### `ObservabilityRollupsPayload`

- Kind: `object`
- Description: Multi-scope rollups for fast state understanding.

| Field           | Type                                     | Required | Description |
| --------------- | ---------------------------------------- | -------- | ----------- |
| `organizations` | `ObservabilityOrganizationTotalsPayload` | no       | -           |
| `portfolios`    | `ObservabilityPortfolioTotalsPayload`    | no       | -           |
| `programs`      | `ObservabilityProgramTotalsPayload`      | no       | -           |
| `projects`      | `ObservabilityProjectTotalsPayload`      | no       | -           |

### `OrganizationCreate`

- Kind: `object`
- Description: Request model for creating an organization.

| Field         | Type             | Required | Description |
| ------------- | ---------------- | -------- | ----------- |
| `description` | `string \| null` | no       | -           |
| `members`     | `array<string>`  | no       | -           |
| `name`        | `string`         | yes      | -           |
| `owner`       | `string \| null` | no       | -           |
| `tags`        | `array<string>`  | no       | -           |

### `OrganizationDashboardItemPayload`

- Kind: `object`
- Description: Organization dashboard item payload.

| Field                | Type                          | Required | Description |
| -------------------- | ----------------------------- | -------- | ----------- |
| `digest`             | `JsonObject \| null`          | no       | -           |
| `evidence`           | `JsonObject`                  | no       | -           |
| `last_activity_at`   | `string \| null`              | no       | -           |
| `last_reviewed_at`   | `string \| null`              | no       | -           |
| `last_transition_at` | `string \| null`              | no       | -           |
| `next_actions`       | `JsonObject`                  | no       | -           |
| `organization`       | `OrganizationResponse`        | no       | -           |
| `retention`          | `JsonObject \| null`          | no       | -           |
| `risk_level`         | `'low' \| 'medium' \| 'high'` | no       | -           |
| `stats`              | `JsonObject`                  | no       | -           |

### `OrganizationDashboardResponsePayload`

- Kind: `object`
- Description: Organization dashboard response payload.

| Field         | Type                                 | Required | Description |
| ------------- | ------------------------------------ | -------- | ----------- |
| `items`       | `OrganizationDashboardItemPayload`   | yes      | -           |
| `limit`       | `integer`                            | yes      | -           |
| `links`       | `JsonObject`                         | yes      | -           |
| `next_steps`  | `array<string>`                      | yes      | -           |
| `offset`      | `integer`                            | yes      | -           |
| `params`      | `JsonObject`                         | yes      | -           |
| `total_count` | `integer`                            | yes      | -           |
| `totals`      | `OrganizationDashboardTotalsPayload` | yes      | -           |

### `OrganizationDashboardTotalsPayload`

- Kind: `object`
- Description: Organization dashboard totals payload.

| Field                 | Type      | Required | Description |
| --------------------- | --------- | -------- | ----------- |
| `blocked_tasks`       | `integer` | yes      | -           |
| `total_goals`         | `integer` | yes      | -           |
| `total_objectives`    | `integer` | yes      | -           |
| `total_organizations` | `integer` | yes      | -           |
| `total_portfolios`    | `integer` | yes      | -           |
| `total_programs`      | `integer` | yes      | -           |
| `total_projects`      | `integer` | yes      | -           |
| `total_tasks`         | `integer` | yes      | -           |
| `total_teams`         | `integer` | yes      | -           |

### `OrganizationResponse`

- Kind: `object`
- Description: Response model for organization.

| Field         | Type                            | Required | Description |
| ------------- | ------------------------------- | -------- | ----------- |
| `created_at`  | `string`                        | yes      | -           |
| `description` | `string \| null`                | yes      | -           |
| `id`          | `string`                        | yes      | -           |
| `members`     | `ActorReferencePayload`         | no       | -           |
| `name`        | `string`                        | yes      | -           |
| `owner`       | `ActorReferencePayload \| null` | no       | -           |
| `status`      | `OrganizationStatus`            | yes      | -           |
| `tags`        | `array<string>`                 | yes      | -           |
| `updated_at`  | `string`                        | yes      | -           |

### `OrganizationStatus`

- Kind: `enum`
- Description: Status of an organization.
- Allowed values: `'active'`, `'archived'`
- Top-level fields: _none_

### `OrganizationSummaryPayload`

- Kind: `object`
- Description: Organization summary payload.

| Field          | Type                          | Required | Description |
| -------------- | ----------------------------- | -------- | ----------- |
| `links`        | `JsonObject`                  | yes      | -           |
| `next_steps`   | `array<string>`               | yes      | -           |
| `organization` | `OrganizationResponse`        | yes      | -           |
| `params`       | `JsonObject`                  | yes      | -           |
| `portfolios`   | `PortfolioResponse`           | yes      | -           |
| `programs`     | `ProgramResponse`             | yes      | -           |
| `risk_level`   | `'low' \| 'medium' \| 'high'` | yes      | -           |
| `stats`        | `JsonObject`                  | yes      | -           |
| `teams`        | `TeamResponse`                | yes      | -           |

### `OrganizationUpdate`

- Kind: `object`
- Description: Request model for updating an organization.

| Field         | Type                    | Required | Description |
| ------------- | ----------------------- | -------- | ----------- |
| `description` | `string \| null`        | no       | -           |
| `members`     | `array<string> \| null` | no       | -           |
| `name`        | `string \| null`        | no       | -           |
| `owner`       | `string \| null`        | no       | -           |
| `status`      | `string \| null`        | no       | -           |
| `tags`        | `array<string> \| null` | no       | -           |

### `PaginatedResponse_ActorResponse_`

- Kind: `object`
- Description: Standard page payload used by list endpoints.

| Field         | Type            | Required | Description |
| ------------- | --------------- | -------- | ----------- |
| `items`       | `ActorResponse` | yes      | -           |
| `limit`       | `integer`       | yes      | -           |
| `links`       | `JsonObject`    | no       | -           |
| `next_steps`  | `array<string>` | no       | -           |
| `offset`      | `integer`       | yes      | -           |
| `params`      | `JsonObject`    | no       | -           |
| `total_count` | `integer`       | yes      | -           |

### `PaginatedResponse_GoalListItemResponse_`

- Kind: `object`
- Description: Standard page payload used by list endpoints.

| Field         | Type                   | Required | Description |
| ------------- | ---------------------- | -------- | ----------- |
| `items`       | `GoalListItemResponse` | yes      | -           |
| `limit`       | `integer`              | yes      | -           |
| `links`       | `JsonObject`           | no       | -           |
| `next_steps`  | `array<string>`        | no       | -           |
| `offset`      | `integer`              | yes      | -           |
| `params`      | `JsonObject`           | no       | -           |
| `total_count` | `integer`              | yes      | -           |

### `PaginatedResponse_KeyResultListItemResponse_`

- Kind: `object`
- Description: Standard page payload used by list endpoints.

| Field         | Type                        | Required | Description |
| ------------- | --------------------------- | -------- | ----------- |
| `items`       | `KeyResultListItemResponse` | yes      | -           |
| `limit`       | `integer`                   | yes      | -           |
| `links`       | `JsonObject`                | no       | -           |
| `next_steps`  | `array<string>`             | no       | -           |
| `offset`      | `integer`                   | yes      | -           |
| `params`      | `JsonObject`                | no       | -           |
| `total_count` | `integer`                   | yes      | -           |

### `PaginatedResponse_ObjectiveListItemResponse_`

- Kind: `object`
- Description: Standard page payload used by list endpoints.

| Field         | Type                        | Required | Description |
| ------------- | --------------------------- | -------- | ----------- |
| `items`       | `ObjectiveListItemResponse` | yes      | -           |
| `limit`       | `integer`                   | yes      | -           |
| `links`       | `JsonObject`                | no       | -           |
| `next_steps`  | `array<string>`             | no       | -           |
| `offset`      | `integer`                   | yes      | -           |
| `params`      | `JsonObject`                | no       | -           |
| `total_count` | `integer`                   | yes      | -           |

### `PaginatedResponse_OrganizationResponse_`

- Kind: `object`
- Description: Standard page payload used by list endpoints.

| Field         | Type                   | Required | Description |
| ------------- | ---------------------- | -------- | ----------- |
| `items`       | `OrganizationResponse` | yes      | -           |
| `limit`       | `integer`              | yes      | -           |
| `links`       | `JsonObject`           | no       | -           |
| `next_steps`  | `array<string>`        | no       | -           |
| `offset`      | `integer`              | yes      | -           |
| `params`      | `JsonObject`           | no       | -           |
| `total_count` | `integer`              | yes      | -           |

### `PaginatedResponse_PlanResponse_`

- Kind: `object`
- Description: Standard page payload used by list endpoints.

| Field         | Type            | Required | Description |
| ------------- | --------------- | -------- | ----------- |
| `items`       | `PlanResponse`  | yes      | -           |
| `limit`       | `integer`       | yes      | -           |
| `links`       | `JsonObject`    | no       | -           |
| `next_steps`  | `array<string>` | no       | -           |
| `offset`      | `integer`       | yes      | -           |
| `params`      | `JsonObject`    | no       | -           |
| `total_count` | `integer`       | yes      | -           |

### `PaginatedResponse_PortfolioResponse_`

- Kind: `object`
- Description: Standard page payload used by list endpoints.

| Field         | Type                | Required | Description |
| ------------- | ------------------- | -------- | ----------- |
| `items`       | `PortfolioResponse` | yes      | -           |
| `limit`       | `integer`           | yes      | -           |
| `links`       | `JsonObject`        | no       | -           |
| `next_steps`  | `array<string>`     | no       | -           |
| `offset`      | `integer`           | yes      | -           |
| `params`      | `JsonObject`        | no       | -           |
| `total_count` | `integer`           | yes      | -           |

### `PaginatedResponse_ProductResponse_`

- Kind: `object`
- Description: Standard page payload used by list endpoints.

| Field         | Type              | Required | Description |
| ------------- | ----------------- | -------- | ----------- |
| `items`       | `ProductResponse` | yes      | -           |
| `limit`       | `integer`         | yes      | -           |
| `links`       | `JsonObject`      | no       | -           |
| `next_steps`  | `array<string>`   | no       | -           |
| `offset`      | `integer`         | yes      | -           |
| `params`      | `JsonObject`      | no       | -           |
| `total_count` | `integer`         | yes      | -           |

### `PaginatedResponse_ProgramResponse_`

- Kind: `object`
- Description: Standard page payload used by list endpoints.

| Field         | Type              | Required | Description |
| ------------- | ----------------- | -------- | ----------- |
| `items`       | `ProgramResponse` | yes      | -           |
| `limit`       | `integer`         | yes      | -           |
| `links`       | `JsonObject`      | no       | -           |
| `next_steps`  | `array<string>`   | no       | -           |
| `offset`      | `integer`         | yes      | -           |
| `params`      | `JsonObject`      | no       | -           |
| `total_count` | `integer`         | yes      | -           |

### `PaginatedResponse_ProjectResponse_`

- Kind: `object`
- Description: Standard page payload used by list endpoints.

| Field         | Type              | Required | Description |
| ------------- | ----------------- | -------- | ----------- |
| `items`       | `ProjectResponse` | yes      | -           |
| `limit`       | `integer`         | yes      | -           |
| `links`       | `JsonObject`      | no       | -           |
| `next_steps`  | `array<string>`   | no       | -           |
| `offset`      | `integer`         | yes      | -           |
| `params`      | `JsonObject`      | no       | -           |
| `total_count` | `integer`         | yes      | -           |

### `PaginatedResponse_TaskEvidenceResponse_`

- Kind: `object`
- Description: Standard page payload used by list endpoints.

| Field         | Type                   | Required | Description |
| ------------- | ---------------------- | -------- | ----------- |
| `items`       | `TaskEvidenceResponse` | yes      | -           |
| `limit`       | `integer`              | yes      | -           |
| `links`       | `JsonObject`           | no       | -           |
| `next_steps`  | `array<string>`        | no       | -           |
| `offset`      | `integer`              | yes      | -           |
| `params`      | `JsonObject`           | no       | -           |
| `total_count` | `integer`              | yes      | -           |

### `PaginatedResponse_TaskResponse_`

- Kind: `object`
- Description: Standard page payload used by list endpoints.

| Field         | Type            | Required | Description |
| ------------- | --------------- | -------- | ----------- |
| `items`       | `TaskResponse`  | yes      | -           |
| `limit`       | `integer`       | yes      | -           |
| `links`       | `JsonObject`    | no       | -           |
| `next_steps`  | `array<string>` | no       | -           |
| `offset`      | `integer`       | yes      | -           |
| `params`      | `JsonObject`    | no       | -           |
| `total_count` | `integer`       | yes      | -           |

### `PaginatedResponse_TeamResponse_`

- Kind: `object`
- Description: Standard page payload used by list endpoints.

| Field         | Type            | Required | Description |
| ------------- | --------------- | -------- | ----------- |
| `items`       | `TeamResponse`  | yes      | -           |
| `limit`       | `integer`       | yes      | -           |
| `links`       | `JsonObject`    | no       | -           |
| `next_steps`  | `array<string>` | no       | -           |
| `offset`      | `integer`       | yes      | -           |
| `params`      | `JsonObject`    | no       | -           |
| `total_count` | `integer`       | yes      | -           |

### `PaginatedResponse_TestRunResponse_`

- Kind: `object`
- Description: Standard page payload used by list endpoints.

| Field         | Type              | Required | Description |
| ------------- | ----------------- | -------- | ----------- |
| `items`       | `TestRunResponse` | yes      | -           |
| `limit`       | `integer`         | yes      | -           |
| `links`       | `JsonObject`      | no       | -           |
| `next_steps`  | `array<string>`   | no       | -           |
| `offset`      | `integer`         | yes      | -           |
| `params`      | `JsonObject`      | no       | -           |
| `total_count` | `integer`         | yes      | -           |

### `PlanCreate`

- Kind: `object`
- Description: Request model for creating a plan.

| Field          | Type                                | Required | Description |
| -------------- | ----------------------------------- | -------- | ----------- |
| `content`      | `JsonObject \| JsonValue \| string` | yes      | -           |
| `description`  | `string \| null`                    | no       | -           |
| `format`       | `string`                            | no       | -           |
| `goal_id`      | `string \| null`                    | no       | -           |
| `name`         | `string`                            | yes      | -           |
| `objective_id` | `string \| null`                    | no       | -           |
| `product_id`   | `string \| null`                    | no       | -           |
| `project_id`   | `string \| null`                    | no       | -           |
| `status`       | `string`                            | no       | -           |
| `tags`         | `array<string>`                     | no       | -           |
| `task_ids`     | `array<string>`                     | no       | -           |

### `PlanFormat`

- Kind: `enum`
- Description: Serialization format for plan content.
- Allowed values: `'json'`, `'yaml'`
- Top-level fields: _none_

### `PlanLineageDashboardPayload`

- Kind: `object`
- Description: Plan lineage dashboard response payload.

| Field         | Type                       | Required | Description |
| ------------- | -------------------------- | -------- | ----------- |
| `items`       | `PlanLineageItemPayload`   | yes      | -           |
| `limit`       | `integer`                  | yes      | -           |
| `links`       | `JsonObject`               | yes      | -           |
| `next_steps`  | `array<string>`            | yes      | -           |
| `offset`      | `integer`                  | yes      | -           |
| `params`      | `JsonObject`               | yes      | -           |
| `total_count` | `integer`                  | yes      | -           |
| `totals`      | `PlanLineageTotalsPayload` | yes      | -           |

### `PlanLineageEvidencePayload`

- Kind: `object`
- Description: Lineage evidence summary payload.

| Field                    | Type                   | Required | Description |
| ------------------------ | ---------------------- | -------- | ----------- |
| `code_total`             | `integer`              | yes      | -           |
| `latest_code_created_at` | `string \| null`       | yes      | -           |
| `latest_code_reference`  | `string \| null`       | yes      | -           |
| `total`                  | `integer`              | yes      | -           |
| `types`                  | `map<string, integer>` | yes      | -           |

### `PlanLineageItemPayload`

- Kind: `object`
- Description: Lineage dashboard item payload.

| Field                | Type                         | Required | Description |
| -------------------- | ---------------------------- | -------- | ----------- |
| `evidence`           | `PlanLineageEvidencePayload` | yes      | -           |
| `last_activity_at`   | `string \| null`             | yes      | -           |
| `last_transition_at` | `string \| null`             | yes      | -           |
| `plan`               | `PlanLineagePlanPayload`     | yes      | -           |
| `stats`              | `PlanLineageStatsPayload`    | yes      | -           |
| `tasks`              | `PlanLineageTaskPayload`     | yes      | -           |
| `test_runs`          | `PlanLineageRunPayload`      | yes      | -           |

### `PlanLineagePlanPayload`

- Kind: `object`
- Description: Plan summary payload for lineage dashboard.

| Field             | Type             | Required | Description |
| ----------------- | ---------------- | -------- | ----------- |
| `created_at`      | `string`         | yes      | -           |
| `description`     | `string \| null` | yes      | -           |
| `format`          | `string`         | yes      | -           |
| `goal_id`         | `string \| null` | yes      | -           |
| `id`              | `string`         | yes      | -           |
| `name`            | `string`         | yes      | -           |
| `objective_id`    | `string \| null` | yes      | -           |
| `project_id`      | `string \| null` | yes      | -           |
| `status`          | `string`         | yes      | -           |
| `stored_status`   | `string \| null` | yes      | -           |
| `tags`            | `array<string>`  | yes      | -           |
| `task_ids`        | `array<string>`  | yes      | -           |
| `terminal_reason` | `string \| null` | yes      | -           |
| `updated_at`      | `string`         | yes      | -           |

### `PlanLineageRunPayload`

- Kind: `object`
- Description: Lineage test run payload.

| Field              | Type              | Required | Description |
| ------------------ | ----------------- | -------- | ----------- |
| `command`          | `string \| null`  | yes      | -           |
| `duration_seconds` | `number \| null`  | yes      | -           |
| `exit_code`        | `integer \| null` | yes      | -           |
| `finished_at`      | `string`          | yes      | -           |
| `id`               | `string`          | yes      | -           |
| `plan_id`          | `string \| null`  | yes      | -           |
| `project_id`       | `string \| null`  | yes      | -           |
| `server_id`        | `string`          | yes      | -           |
| `started_at`       | `string`          | yes      | -           |
| `success`          | `boolean`         | yes      | -           |
| `task_ids`         | `array<string>`   | yes      | -           |

### `PlanLineageStatsPayload`

- Kind: `object`
- Description: Lineage stats payload.

| Field                 | Type              | Required | Description |
| --------------------- | ----------------- | -------- | ----------- |
| `blocked_tasks`       | `integer`         | yes      | -           |
| `completed_tasks`     | `integer`         | yes      | -           |
| `latest_test_run_id`  | `string \| null`  | yes      | -           |
| `latest_test_success` | `boolean \| null` | yes      | -           |
| `total_tasks`         | `integer`         | yes      | -           |
| `total_test_runs`     | `integer`         | yes      | -           |

### `PlanLineageTaskPayload`

- Kind: `object`
- Description: Lineage task payload.

| Field           | Type                 | Required | Description |
| --------------- | -------------------- | -------- | ----------- |
| `assignee`      | `JsonObject \| null` | yes      | -           |
| `due_date`      | `string \| null`     | yes      | -           |
| `evidence_gate` | `JsonObject \| null` | yes      | -           |
| `id`            | `string`             | yes      | -           |
| `project_id`    | `string \| null`     | yes      | -           |
| `status`        | `string`             | yes      | -           |
| `title`         | `string`             | yes      | -           |

### `PlanLineageTotalsPayload`

- Kind: `object`
- Description: Lineage dashboard totals payload.

| Field                 | Type      | Required | Description |
| --------------------- | --------- | -------- | ----------- |
| `failed_test_runs`    | `integer` | yes      | -           |
| `total_code_evidence` | `integer` | yes      | -           |
| `total_evidence`      | `integer` | yes      | -           |
| `total_plans`         | `integer` | yes      | -           |
| `total_tasks`         | `integer` | yes      | -           |
| `total_test_runs`     | `integer` | yes      | -           |

### `PlanResponse`

- Kind: `object`
- Description: Response model for plan.

| Field                | Type                 | Required | Description |
| -------------------- | -------------------- | -------- | ----------- |
| `content`            | `string`             | yes      | -           |
| `created_at`         | `string`             | yes      | -           |
| `description`        | `string \| null`     | yes      | -           |
| `focus_task`         | `JsonObject \| null` | no       | -           |
| `format`             | `PlanFormat`         | yes      | -           |
| `goal_id`            | `string \| null`     | yes      | -           |
| `id`                 | `string`             | yes      | -           |
| `last_activity_at`   | `string \| null`     | no       | -           |
| `last_transition_at` | `string \| null`     | no       | -           |
| `links`              | `JsonObject`         | no       | -           |
| `name`               | `string`             | yes      | -           |
| `next_steps`         | `array<string>`      | no       | -           |
| `objective_id`       | `string \| null`     | yes      | -           |
| `product_id`         | `string \| null`     | yes      | -           |
| `project_id`         | `string \| null`     | yes      | -           |
| `status`             | `PlanStatus`         | yes      | -           |
| `stored_status`      | `PlanStatus \| null` | no       | -           |
| `tags`               | `array<string>`      | yes      | -           |
| `task_ids`           | `array<string>`      | yes      | -           |
| `terminal_reason`    | `string \| null`     | no       | -           |
| `updated_at`         | `string`             | yes      | -           |

### `PlanStatus`

- Kind: `enum`
- Description: Status of a plan artifact.
- Allowed values: `'draft'`, `'active'`, `'completed'`, `'archived'`
- Top-level fields: _none_

### `PlanTestJobCreate`

- Kind: `object`
- Description: Request model for creating a plan test job.

| Field                   | Type                    | Required | Description                                                                                                                                                                                    |
| ----------------------- | ----------------------- | -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `capture_logs`          | `array<string>`         | no       | -                                                                                                                                                                                              |
| `description`           | `string \| null`        | no       | -                                                                                                                                                                                              |
| `env_vars`              | `EnvVarPair`            | no       | -                                                                                                                                                                                              |
| `exclude_patterns`      | `array<string> \| null` | no       | -                                                                                                                                                                                              |
| `mode`                  | `'local' \| 'aws'`      | no       | -                                                                                                                                                                                              |
| `name`                  | `string`                | yes      | -                                                                                                                                                                                              |
| `project_id`            | `string \| null`        | no       | -                                                                                                                                                                                              |
| `project_path`          | `string`                | yes      | -                                                                                                                                                                                              |
| `remote_path`           | `string`                | no       | -                                                                                                                                                                                              |
| `save_artifacts`        | `array<string>`         | no       | -                                                                                                                                                                                              |
| `server_id`             | `string \| null`        | no       | -                                                                                                                                                                                              |
| `server_name`           | `string \| null`        | no       | -                                                                                                                                                                                              |
| `setup_command`         | `string \| null`        | no       | -                                                                                                                                                                                              |
| `stream_output`         | `boolean`               | no       | Deprecated for persisted plan test jobs. Live output is only available through interactive `pms aws test run`; plan-job runs expose stdout/stderr after completion via the resulting test run. |
| `task_ids`              | `array<string>`         | no       | -                                                                                                                                                                                              |
| `test_command`          | `string`                | no       | -                                                                                                                                                                                              |
| `timeout`               | `number`                | no       | -                                                                                                                                                                                              |
| `transition_by`         | `string \| null`        | no       | -                                                                                                                                                                                              |
| `transition_on_failure` | `string \| null`        | no       | -                                                                                                                                                                                              |
| `transition_on_success` | `string \| null`        | no       | -                                                                                                                                                                                              |
| `transition_reason`     | `string \| null`        | no       | -                                                                                                                                                                                              |
| `working_dir`           | `string \| null`        | no       | -                                                                                                                                                                                              |

### `PlanTestJobListResponse`

- Kind: `object`
- Description: Response model for listing plan test jobs.

| Field         | Type                  | Required | Description |
| ------------- | --------------------- | -------- | ----------- |
| `items`       | `PlanTestJobResponse` | no       | -           |
| `limit`       | `integer`             | yes      | -           |
| `links`       | `JsonObject`          | no       | -           |
| `next_steps`  | `array<string>`       | no       | -           |
| `offset`      | `integer`             | yes      | -           |
| `params`      | `JsonObject`          | no       | -           |
| `total_count` | `integer`             | yes      | -           |

### `PlanTestJobResponse`

- Kind: `object`
- Description: Response model for plan test jobs.

| Field                   | Type                    | Required | Description                                                                                                                 |
| ----------------------- | ----------------------- | -------- | --------------------------------------------------------------------------------------------------------------------------- |
| `archived_at`           | `string \| null`        | no       | -                                                                                                                           |
| `capture_logs`          | `array<string>`         | yes      | -                                                                                                                           |
| `created_at`            | `string`                | yes      | -                                                                                                                           |
| `description`           | `string \| null`        | yes      | -                                                                                                                           |
| `env_vars`              | `EnvVarPair`            | yes      | -                                                                                                                           |
| `exclude_patterns`      | `array<string> \| null` | yes      | -                                                                                                                           |
| `id`                    | `string`                | yes      | -                                                                                                                           |
| `mode`                  | `'local' \| 'aws'`      | yes      | -                                                                                                                           |
| `name`                  | `string`                | yes      | -                                                                                                                           |
| `plan_id`               | `string`                | yes      | -                                                                                                                           |
| `project_id`            | `string \| null`        | yes      | -                                                                                                                           |
| `project_path`          | `string`                | yes      | -                                                                                                                           |
| `remote_path`           | `string`                | yes      | -                                                                                                                           |
| `save_artifacts`        | `array<string>`         | yes      | -                                                                                                                           |
| `server_id`             | `string \| null`        | yes      | -                                                                                                                           |
| `server_name`           | `string \| null`        | yes      | -                                                                                                                           |
| `setup_command`         | `string \| null`        | yes      | -                                                                                                                           |
| `stream_output`         | `boolean`               | yes      | Deprecated persisted flag. Historical records may still contain it, but plan-job runs do not provide live streaming output. |
| `task_ids`              | `array<string>`         | yes      | -                                                                                                                           |
| `test_command`          | `string`                | yes      | -                                                                                                                           |
| `timeout`               | `number`                | yes      | -                                                                                                                           |
| `transition_by`         | `string \| null`        | yes      | -                                                                                                                           |
| `transition_on_failure` | `string \| null`        | yes      | -                                                                                                                           |
| `transition_on_success` | `string \| null`        | yes      | -                                                                                                                           |
| `transition_reason`     | `string \| null`        | yes      | -                                                                                                                           |
| `updated_at`            | `string`                | yes      | -                                                                                                                           |
| `working_dir`           | `string \| null`        | yes      | -                                                                                                                           |

### `PlanTestJobRunResponse`

- Kind: `object`
- Description: Response model for running a plan test job.

| Field      | Type                  | Required | Description |
| ---------- | --------------------- | -------- | ----------- |
| `job`      | `PlanTestJobResponse` | yes      | -           |
| `test_run` | `TestRunResponse`     | yes      | -           |

### `PlanTestJobUpdate`

- Kind: `object`
- Description: Request model for updating a plan test job.

| Field                   | Type                       | Required | Description                                                                                                                                                                                    |
| ----------------------- | -------------------------- | -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `capture_logs`          | `array<string> \| null`    | no       | -                                                                                                                                                                                              |
| `description`           | `string \| null`           | no       | -                                                                                                                                                                                              |
| `env_vars`              | `EnvVarPair \| null`       | no       | -                                                                                                                                                                                              |
| `exclude_patterns`      | `array<string> \| null`    | no       | -                                                                                                                                                                                              |
| `mode`                  | `'local' \| 'aws' \| null` | no       | -                                                                                                                                                                                              |
| `name`                  | `string \| null`           | no       | -                                                                                                                                                                                              |
| `project_id`            | `string \| null`           | no       | -                                                                                                                                                                                              |
| `project_path`          | `string \| null`           | no       | -                                                                                                                                                                                              |
| `remote_path`           | `string \| null`           | no       | -                                                                                                                                                                                              |
| `save_artifacts`        | `array<string> \| null`    | no       | -                                                                                                                                                                                              |
| `server_id`             | `string \| null`           | no       | -                                                                                                                                                                                              |
| `server_name`           | `string \| null`           | no       | -                                                                                                                                                                                              |
| `setup_command`         | `string \| null`           | no       | -                                                                                                                                                                                              |
| `stream_output`         | `boolean \| null`          | no       | Deprecated for persisted plan test jobs. Live output is only available through interactive `pms aws test run`; plan-job runs expose stdout/stderr after completion via the resulting test run. |
| `task_ids`              | `array<string> \| null`    | no       | -                                                                                                                                                                                              |
| `test_command`          | `string \| null`           | no       | -                                                                                                                                                                                              |
| `timeout`               | `number \| null`           | no       | -                                                                                                                                                                                              |
| `transition_by`         | `string \| null`           | no       | -                                                                                                                                                                                              |
| `transition_on_failure` | `string \| null`           | no       | -                                                                                                                                                                                              |
| `transition_on_success` | `string \| null`           | no       | -                                                                                                                                                                                              |
| `transition_reason`     | `string \| null`           | no       | -                                                                                                                                                                                              |
| `working_dir`           | `string \| null`           | no       | -                                                                                                                                                                                              |

### `PlanUpdate`

- Kind: `object`
- Description: Request model for updating a plan.

| Field          | Type                                        | Required | Description |
| -------------- | ------------------------------------------- | -------- | ----------- |
| `content`      | `JsonObject \| JsonValue \| string \| null` | no       | -           |
| `description`  | `string \| null`                            | no       | -           |
| `format`       | `string \| null`                            | no       | -           |
| `goal_id`      | `string \| null`                            | no       | -           |
| `name`         | `string \| null`                            | no       | -           |
| `objective_id` | `string \| null`                            | no       | -           |
| `product_id`   | `string \| null`                            | no       | -           |
| `project_id`   | `string \| null`                            | no       | -           |
| `status`       | `string \| null`                            | no       | -           |
| `tags`         | `array<string> \| null`                     | no       | -           |
| `task_ids`     | `array<string> \| null`                     | no       | -           |

### `PolicyUsage`

- Kind: `object`
- Description: Retention policy usage summary.

| Field                  | Type                          | Required | Description |
| ---------------------- | ----------------------------- | -------- | ----------- |
| `max_age_days`         | `integer`                     | yes      | -           |
| `max_artifact_bytes`   | `integer`                     | yes      | -           |
| `max_log_bytes`        | `integer`                     | yes      | -           |
| `older_than_max_age`   | `integer`                     | yes      | -           |
| `policy_id`            | `string`                      | yes      | -           |
| `project_ids`          | `array<string>`               | no       | -           |
| `run_count`            | `integer`                     | yes      | -           |
| `scope_id`             | `string`                      | yes      | -           |
| `scope_type`           | `'project' \| 'organization'` | yes      | -           |
| `total_artifact_bytes` | `integer`                     | yes      | -           |
| `total_bytes`          | `integer`                     | yes      | -           |
| `total_log_bytes`      | `integer`                     | yes      | -           |

### `PortfolioCreate`

- Kind: `object`
- Description: Request model for creating a portfolio.

| Field           | Type             | Required | Description |
| --------------- | ---------------- | -------- | ----------- |
| `description`   | `string \| null` | no       | -           |
| `goal_ids`      | `array<string>`  | no       | -           |
| `name`          | `string`         | yes      | -           |
| `objective_ids` | `array<string>`  | no       | -           |
| `org_id`        | `string \| null` | no       | -           |
| `owner`         | `string \| null` | no       | -           |
| `project_ids`   | `array<string>`  | no       | -           |
| `tags`          | `array<string>`  | no       | -           |

### `PortfolioDashboardItemPayload`

- Kind: `object`
- Description: Portfolio dashboard item payload.

| Field                | Type                          | Required | Description |
| -------------------- | ----------------------------- | -------- | ----------- |
| `digest`             | `JsonObject \| null`          | no       | -           |
| `evidence`           | `JsonObject`                  | no       | -           |
| `last_activity_at`   | `string \| null`              | no       | -           |
| `last_reviewed_at`   | `string \| null`              | no       | -           |
| `last_transition_at` | `string \| null`              | no       | -           |
| `next_actions`       | `JsonObject`                  | no       | -           |
| `portfolio`          | `PortfolioResponse`           | no       | -           |
| `retention`          | `JsonObject \| null`          | no       | -           |
| `risk_level`         | `'low' \| 'medium' \| 'high'` | no       | -           |
| `stats`              | `JsonObject`                  | no       | -           |

### `PortfolioDashboardResponsePayload`

- Kind: `object`
- Description: Portfolio dashboard response payload.

| Field         | Type                              | Required | Description |
| ------------- | --------------------------------- | -------- | ----------- |
| `items`       | `PortfolioDashboardItemPayload`   | yes      | -           |
| `limit`       | `integer`                         | yes      | -           |
| `links`       | `JsonObject`                      | yes      | -           |
| `next_steps`  | `array<string>`                   | yes      | -           |
| `offset`      | `integer`                         | yes      | -           |
| `params`      | `JsonObject`                      | yes      | -           |
| `total_count` | `integer`                         | yes      | -           |
| `totals`      | `PortfolioDashboardTotalsPayload` | yes      | -           |

### `PortfolioDashboardTotalsPayload`

- Kind: `object`
- Description: Portfolio dashboard totals payload.

| Field              | Type      | Required | Description |
| ------------------ | --------- | -------- | ----------- |
| `blocked_tasks`    | `integer` | yes      | -           |
| `total_goals`      | `integer` | yes      | -           |
| `total_objectives` | `integer` | yes      | -           |
| `total_portfolios` | `integer` | yes      | -           |
| `total_projects`   | `integer` | yes      | -           |
| `total_tasks`      | `integer` | yes      | -           |

### `PortfolioResponse`

- Kind: `object`
- Description: Response model for portfolio.

| Field                     | Type                            | Required | Description |
| ------------------------- | ------------------------------- | -------- | ----------- |
| `created_at`              | `string`                        | yes      | -           |
| `description`             | `string \| null`                | yes      | -           |
| `effective_goal_ids`      | `array<string>`                 | yes      | -           |
| `effective_objective_ids` | `array<string>`                 | yes      | -           |
| `goal_ids`                | `array<string>`                 | yes      | -           |
| `id`                      | `string`                        | yes      | -           |
| `name`                    | `string`                        | yes      | -           |
| `objective_ids`           | `array<string>`                 | yes      | -           |
| `org_id`                  | `string \| null`                | yes      | -           |
| `owner`                   | `ActorReferencePayload \| null` | no       | -           |
| `project_ids`             | `array<string>`                 | yes      | -           |
| `status`                  | `PortfolioStatus`               | yes      | -           |
| `tags`                    | `array<string>`                 | yes      | -           |
| `updated_at`              | `string`                        | yes      | -           |

### `PortfolioStatus`

- Kind: `enum`
- Description: Status of a portfolio.
- Allowed values: `'active'`, `'archived'`
- Top-level fields: _none_

### `PortfolioSummaryPayload`

- Kind: `object`
- Description: Portfolio summary payload.

| Field        | Type                          | Required | Description |
| ------------ | ----------------------------- | -------- | ----------- |
| `links`      | `JsonObject`                  | yes      | -           |
| `next_steps` | `array<string>`               | yes      | -           |
| `params`     | `JsonObject`                  | yes      | -           |
| `portfolio`  | `PortfolioResponse`           | yes      | -           |
| `risk_level` | `'low' \| 'medium' \| 'high'` | yes      | -           |
| `stats`      | `JsonObject`                  | yes      | -           |

### `PortfolioUpdate`

- Kind: `object`
- Description: Request model for updating a portfolio.

| Field           | Type                    | Required | Description |
| --------------- | ----------------------- | -------- | ----------- |
| `description`   | `string \| null`        | no       | -           |
| `goal_ids`      | `array<string> \| null` | no       | -           |
| `name`          | `string \| null`        | no       | -           |
| `objective_ids` | `array<string> \| null` | no       | -           |
| `owner`         | `string \| null`        | no       | -           |
| `project_ids`   | `array<string> \| null` | no       | -           |
| `status`        | `string \| null`        | no       | -           |
| `tags`          | `array<string> \| null` | no       | -           |

### `Priority`

- Kind: `enum`
- Description: Task priority levels.
- Allowed values: `'low'`, `'medium'`, `'high'`, `'critical'`
- Top-level fields: _none_

### `ProductCreate`

- Kind: `object`
- Description: Request model for creating a product.

| Field            | Type             | Required | Description                                                                              |
| ---------------- | ---------------- | -------- | ---------------------------------------------------------------------------------------- |
| `description`    | `string \| null` | no       | -                                                                                        |
| `name`           | `string`         | yes      | -                                                                                        |
| `owner`          | `string \| null` | no       | -                                                                                        |
| `product_type`   | `string`         | no       | Descriptive product category. Intentionally open; not a closed enum or product taxonomy. |
| `repository_url` | `string \| null` | no       | -                                                                                        |
| `tags`           | `array<string>`  | no       | -                                                                                        |
| `vision`         | `string \| null` | no       | -                                                                                        |

### `ProductResponse`

- Kind: `object`
- Description: Response model for product.

| Field            | Type                            | Required | Description                                                                              |
| ---------------- | ------------------------------- | -------- | ---------------------------------------------------------------------------------------- |
| `created_at`     | `string`                        | yes      | -                                                                                        |
| `description`    | `string \| null`                | yes      | -                                                                                        |
| `id`             | `string`                        | yes      | -                                                                                        |
| `name`           | `string`                        | yes      | -                                                                                        |
| `owner`          | `ActorReferencePayload \| null` | no       | -                                                                                        |
| `product_type`   | `string`                        | yes      | Descriptive product category. Intentionally open; not a closed enum or product taxonomy. |
| `repository_url` | `string \| null`                | yes      | -                                                                                        |
| `status`         | `ProductStatus`                 | yes      | -                                                                                        |
| `tags`           | `array<string>`                 | yes      | -                                                                                        |
| `updated_at`     | `string`                        | yes      | -                                                                                        |
| `vision`         | `string \| null`                | yes      | -                                                                                        |

### `ProductStatus`

- Kind: `enum`
- Description: Status of a product.
- Allowed values: `'planning'`, `'active'`, `'mature'`, `'sunset'`, `'archived'`
- Top-level fields: _none_

### `ProductSummaryResponsePayload`

- Kind: `object`
- Description: Product summary payload.

| Field          | Type                         | Required | Description |
| -------------- | ---------------------------- | -------- | ----------- |
| `health_score` | `number`                     | yes      | -           |
| `product`      | `ProductResponse`            | yes      | -           |
| `stats`        | `ProductSummaryStatsPayload` | yes      | -           |

### `ProductSummaryStatsPayload`

- Kind: `object`
- Description: Rollup statistics for a product summary.

| Field                     | Type      | Required | Description |
| ------------------------- | --------- | -------- | ----------- |
| `avg_goal_progress`       | `number`  | yes      | -           |
| `completed_goals`         | `integer` | yes      | -           |
| `completed_tasks`         | `integer` | yes      | -           |
| `health_score`            | `number`  | yes      | -           |
| `total_complexity_points` | `integer` | yes      | -           |
| `total_goals`             | `integer` | yes      | -           |
| `total_projects`          | `integer` | yes      | -           |
| `total_tasks`             | `integer` | yes      | -           |

### `ProductUpdate`

- Kind: `object`
- Description: Request model for updating a product.

| Field            | Type                    | Required | Description                                                                              |
| ---------------- | ----------------------- | -------- | ---------------------------------------------------------------------------------------- |
| `description`    | `string \| null`        | no       | -                                                                                        |
| `name`           | `string \| null`        | no       | -                                                                                        |
| `owner`          | `string \| null`        | no       | -                                                                                        |
| `product_type`   | `string \| null`        | no       | Descriptive product category. Intentionally open; not a closed enum or product taxonomy. |
| `repository_url` | `string \| null`        | no       | -                                                                                        |
| `status`         | `string \| null`        | no       | -                                                                                        |
| `tags`           | `array<string> \| null` | no       | -                                                                                        |
| `vision`         | `string \| null`        | no       | -                                                                                        |

### `ProgramCreate`

- Kind: `object`
- Description: Request model for creating a program.

| Field           | Type             | Required | Description |
| --------------- | ---------------- | -------- | ----------- |
| `description`   | `string \| null` | no       | -           |
| `goal_ids`      | `array<string>`  | no       | -           |
| `name`          | `string`         | yes      | -           |
| `objective_ids` | `array<string>`  | no       | -           |
| `org_id`        | `string \| null` | no       | -           |
| `owner`         | `string \| null` | no       | -           |
| `portfolio_id`  | `string \| null` | no       | -           |
| `project_ids`   | `array<string>`  | no       | -           |
| `tags`          | `array<string>`  | no       | -           |

### `ProgramDashboardItemPayload`

- Kind: `object`
- Description: Program dashboard item payload.

| Field                | Type                          | Required | Description |
| -------------------- | ----------------------------- | -------- | ----------- |
| `digest`             | `JsonObject \| null`          | no       | -           |
| `evidence`           | `JsonObject`                  | no       | -           |
| `last_activity_at`   | `string \| null`              | no       | -           |
| `last_reviewed_at`   | `string \| null`              | no       | -           |
| `last_transition_at` | `string \| null`              | no       | -           |
| `next_actions`       | `JsonObject`                  | no       | -           |
| `program`            | `ProgramResponse`             | no       | -           |
| `retention`          | `JsonObject \| null`          | no       | -           |
| `risk_level`         | `'low' \| 'medium' \| 'high'` | no       | -           |
| `stats`              | `JsonObject`                  | no       | -           |

### `ProgramDashboardResponsePayload`

- Kind: `object`
- Description: Program dashboard response payload.

| Field         | Type                            | Required | Description |
| ------------- | ------------------------------- | -------- | ----------- |
| `items`       | `ProgramDashboardItemPayload`   | yes      | -           |
| `limit`       | `integer`                       | yes      | -           |
| `links`       | `JsonObject`                    | yes      | -           |
| `next_steps`  | `array<string>`                 | yes      | -           |
| `offset`      | `integer`                       | yes      | -           |
| `params`      | `JsonObject`                    | yes      | -           |
| `total_count` | `integer`                       | yes      | -           |
| `totals`      | `ProgramDashboardTotalsPayload` | yes      | -           |

### `ProgramDashboardTotalsPayload`

- Kind: `object`
- Description: Program dashboard totals payload.

| Field              | Type      | Required | Description |
| ------------------ | --------- | -------- | ----------- |
| `blocked_tasks`    | `integer` | yes      | -           |
| `total_goals`      | `integer` | yes      | -           |
| `total_objectives` | `integer` | yes      | -           |
| `total_programs`   | `integer` | yes      | -           |
| `total_projects`   | `integer` | yes      | -           |
| `total_tasks`      | `integer` | yes      | -           |

### `ProgramResponse`

- Kind: `object`
- Description: Response model for program.

| Field                     | Type                            | Required | Description |
| ------------------------- | ------------------------------- | -------- | ----------- |
| `created_at`              | `string`                        | yes      | -           |
| `description`             | `string \| null`                | yes      | -           |
| `effective_goal_ids`      | `array<string>`                 | yes      | -           |
| `effective_objective_ids` | `array<string>`                 | yes      | -           |
| `goal_ids`                | `array<string>`                 | yes      | -           |
| `id`                      | `string`                        | yes      | -           |
| `name`                    | `string`                        | yes      | -           |
| `objective_ids`           | `array<string>`                 | yes      | -           |
| `org_id`                  | `string \| null`                | yes      | -           |
| `owner`                   | `ActorReferencePayload \| null` | no       | -           |
| `portfolio_id`            | `string \| null`                | yes      | -           |
| `project_ids`             | `array<string>`                 | yes      | -           |
| `status`                  | `ProgramStatus`                 | yes      | -           |
| `tags`                    | `array<string>`                 | yes      | -           |
| `updated_at`              | `string`                        | yes      | -           |

### `ProgramStatus`

- Kind: `enum`
- Description: Status of a program.
- Allowed values: `'active'`, `'archived'`
- Top-level fields: _none_

### `ProgramSummaryPayload`

- Kind: `object`
- Description: Program summary payload.

| Field        | Type                          | Required | Description |
| ------------ | ----------------------------- | -------- | ----------- |
| `links`      | `JsonObject`                  | yes      | -           |
| `next_steps` | `array<string>`               | yes      | -           |
| `params`     | `JsonObject`                  | yes      | -           |
| `program`    | `ProgramResponse`             | yes      | -           |
| `risk_level` | `'low' \| 'medium' \| 'high'` | yes      | -           |
| `stats`      | `JsonObject`                  | yes      | -           |

### `ProgramUpdate`

- Kind: `object`
- Description: Request model for updating a program.

| Field           | Type                    | Required | Description |
| --------------- | ----------------------- | -------- | ----------- |
| `description`   | `string \| null`        | no       | -           |
| `goal_ids`      | `array<string> \| null` | no       | -           |
| `name`          | `string \| null`        | no       | -           |
| `objective_ids` | `array<string> \| null` | no       | -           |
| `owner`         | `string \| null`        | no       | -           |
| `project_ids`   | `array<string> \| null` | no       | -           |
| `status`        | `string \| null`        | no       | -           |
| `tags`          | `array<string> \| null` | no       | -           |

### `ProgressResponse`

- Kind: `object`
- Description: Response model for progress update.

| Field              | Type      | Required | Description |
| ------------------ | --------- | -------- | ----------- |
| `percent_complete` | `integer` | yes      | -           |
| `status_message`   | `string`  | yes      | -           |
| `task_id`          | `string`  | yes      | -           |
| `timestamp`        | `string`  | yes      | -           |
| `updated_by`       | `string`  | yes      | -           |

### `ProgressTimelinePayload`

- Kind: `object`
- Description: Progress timeline payload.

| Field                       | Type             | Required | Description |
| --------------------------- | ---------------- | -------- | ----------- |
| `current_percent`           | `integer`        | yes      | -           |
| `estimated_completion`      | `string \| null` | yes      | -           |
| `task_id`                   | `string`         | yes      | -           |
| `total_duration_hours`      | `number`         | yes      | -           |
| `updates_count`             | `integer`        | yes      | -           |
| `velocity_percent_per_hour` | `number`         | yes      | -           |
| `velocity_trend`            | `string`         | yes      | -           |

### `ProgressUpdate`

- Kind: `object`
- Description: Request model for progress update.

| Field              | Type         | Required | Description |
| ------------------ | ------------ | -------- | ----------- |
| `metadata`         | `JsonObject` | no       | -           |
| `percent_complete` | `integer`    | yes      | -           |
| `status_message`   | `string`     | yes      | -           |
| `updated_by`       | `string`     | yes      | -           |

### `ProjectCreate`

- Kind: `object`
- Description: Request model for creating a project.

| Field          | Type             | Required | Description |
| -------------- | ---------------- | -------- | ----------- |
| `description`  | `string \| null` | no       | -           |
| `name`         | `string`         | yes      | -           |
| `org_id`       | `string \| null` | no       | -           |
| `portfolio_id` | `string \| null` | no       | -           |
| `product_id`   | `string \| null` | no       | -           |
| `program_id`   | `string \| null` | no       | -           |
| `tags`         | `array<string>`  | no       | -           |

### `ProjectDashboardCompletionContextPayload`

- Kind: `object`
- Description: Recent terminal project context payload.

| Field        | Type              | Required | Description |
| ------------ | ----------------- | -------- | ----------- |
| `items`      | `ProjectResponse` | yes      | -           |
| `next_steps` | `array<string>`   | yes      | -           |
| `summary`    | `string`          | yes      | -           |

### `ProjectDashboardResponsePayload`

- Kind: `object`
- Description: Instance-wide project operator dashboard payload.

| Field                         | Type                                               | Required | Description |
| ----------------------------- | -------------------------------------------------- | -------- | ----------- |
| `active_projects`             | `ProjectResponse`                                  | yes      | -           |
| `completion_context`          | `ProjectDashboardCompletionContextPayload \| null` | yes      | -           |
| `freshest_visible_activity`   | `ProjectResponse \| null`                          | yes      | -           |
| `freshest_visible_transition` | `ProjectResponse \| null`                          | yes      | -           |
| `links`                       | `JsonObject`                                       | yes      | -           |
| `next_steps`                  | `array<string>`                                    | yes      | -           |
| `recently_completed_projects` | `ProjectResponse`                                  | yes      | -           |
| `scope`                       | `JsonObject`                                       | yes      | -           |
| `terminal_reason`             | `string \| null`                                   | yes      | -           |
| `totals`                      | `ProjectDashboardTotalsPayload`                    | yes      | -           |

### `ProjectDashboardTotalsPayload`

- Kind: `object`
- Description: Instance dashboard totals payload.

| Field             | Type      | Required | Description |
| ----------------- | --------- | -------- | ----------- |
| `blocked_tasks`   | `integer` | yes      | -           |
| `completed_tasks` | `integer` | yes      | -           |
| `overdue_tasks`   | `integer` | yes      | -           |
| `total_projects`  | `integer` | yes      | -           |
| `total_tasks`     | `integer` | yes      | -           |

### `ProjectOperatorOverviewPayload`

- Kind: `object`
- Description: Project operator control-plane payload.

| Field          | Type                 | Required | Description |
| -------------- | -------------------- | -------- | ----------- |
| `daily`        | `JsonObject`         | yes      | -           |
| `focus_task`   | `JsonObject \| null` | yes      | -           |
| `health_score` | `number`             | yes      | -           |
| `history`      | `JsonObject`         | yes      | -           |
| `lineage`      | `JsonObject`         | yes      | -           |
| `links`        | `JsonObject`         | yes      | -           |
| `next_steps`   | `array<string>`      | yes      | -           |
| `params`       | `JsonObject`         | yes      | -           |
| `project`      | `ProjectResponse`    | yes      | -           |
| `stats`        | `JsonObject \| null` | yes      | -           |

### `ProjectResponse`

- Kind: `object`
- Description: Response model for project.

| Field                        | Type                    | Required | Description |
| ---------------------------- | ----------------------- | -------- | ----------- |
| `created_at`                 | `string`                | yes      | -           |
| `description`                | `string \| null`        | yes      | -           |
| `focus_task`                 | `JsonObject \| null`    | no       | -           |
| `id`                         | `string`                | yes      | -           |
| `last_activity_at`           | `string \| null`        | no       | -           |
| `last_transition_at`         | `string \| null`        | no       | -           |
| `links`                      | `JsonObject`            | no       | -           |
| `name`                       | `string`                | yes      | -           |
| `next_steps`                 | `array<string>`         | no       | -           |
| `operator_category`          | `string \| null`        | no       | -           |
| `operator_category_label`    | `string \| null`        | no       | -           |
| `operator_visibility_reason` | `string \| null`        | no       | -           |
| `org_id`                     | `string \| null`        | yes      | -           |
| `portfolio_id`               | `string \| null`        | yes      | -           |
| `product_id`                 | `string \| null`        | yes      | -           |
| `program_id`                 | `string \| null`        | yes      | -           |
| `status`                     | `ProjectStatus`         | yes      | -           |
| `stored_status`              | `ProjectStatus \| null` | no       | -           |
| `tags`                       | `array<string>`         | yes      | -           |
| `terminal_reason`            | `string \| null`        | no       | -           |
| `updated_at`                 | `string`                | yes      | -           |

### `ProjectStatus`

- Kind: `enum`
- Description: Status of a project.
- Allowed values: `'active'`, `'archived'`, `'completed'`, `'on_hold'`
- Top-level fields: _none_

### `ProjectSummaryResponsePayload`

- Kind: `object`
- Description: Project summary payload.

| Field          | Type                 | Required | Description |
| -------------- | -------------------- | -------- | ----------- |
| `health_score` | `number`             | yes      | -           |
| `links`        | `JsonObject`         | yes      | -           |
| `next_steps`   | `array<string>`      | yes      | -           |
| `project`      | `ProjectResponse`    | yes      | -           |
| `stats`        | `JsonObject \| null` | yes      | -           |

### `ProjectUpdate`

- Kind: `object`
- Description: Request model for updating a project.

| Field          | Type                    | Required | Description |
| -------------- | ----------------------- | -------- | ----------- |
| `description`  | `string \| null`        | no       | -           |
| `name`         | `string \| null`        | no       | -           |
| `org_id`       | `string \| null`        | no       | -           |
| `portfolio_id` | `string \| null`        | no       | -           |
| `product_id`   | `string \| null`        | no       | -           |
| `program_id`   | `string \| null`        | no       | -           |
| `status`       | `string \| null`        | no       | -           |
| `tags`         | `array<string> \| null` | no       | -           |

### `ProofBundleResponse`

- Kind: `object`
- Description: Response model for task proof bundles.

| Field          | Type                         | Required | Description |
| -------------- | ---------------------------- | -------- | ----------- |
| `evidence`     | `TaskEvidenceResponse`       | no       | -           |
| `generated_at` | `string`                     | yes      | -           |
| `summary`      | `ProofBundleSummaryResponse` | yes      | -           |
| `task`         | `TaskResponse`               | yes      | -           |
| `test_runs`    | `TestRunResponse`            | no       | -           |

### `ProofBundleSearchItemResponse`

- Kind: `object`
- Description: Response model for proof bundle search results.

| Field              | Type                         | Required | Description |
| ------------------ | ---------------------------- | -------- | ----------- |
| `evidence`         | `TaskEvidenceResponse`       | no       | -           |
| `last_evidence_at` | `string \| null`             | yes      | -           |
| `summary`          | `ProofBundleSummaryResponse` | yes      | -           |
| `task`             | `TaskResponse`               | yes      | -           |
| `test_runs`        | `TestRunResponse`            | no       | -           |

### `ProofBundleSearchResponse`

- Kind: `object`
- Description: Response model for proof bundle search.

| Field         | Type                            | Required | Description |
| ------------- | ------------------------------- | -------- | ----------- |
| `items`       | `ProofBundleSearchItemResponse` | no       | -           |
| `limit`       | `integer`                       | yes      | -           |
| `offset`      | `integer`                       | yes      | -           |
| `total_count` | `integer`                       | yes      | -           |

### `ProofBundleSummaryResponse`

- Kind: `object`
- Description: Response model for proof bundle summary.

| Field                  | Type                   | Required | Description |
| ---------------------- | ---------------------- | -------- | ----------- |
| `artifact_bytes_total` | `integer`              | yes      | -           |
| `evidence_total`       | `integer`              | yes      | -           |
| `evidence_types`       | `map<string, integer>` | yes      | -           |
| `log_bytes_total`      | `integer`              | yes      | -           |
| `successful_test_runs` | `integer`              | yes      | -           |
| `test_runs`            | `integer`              | yes      | -           |

### `QueuePresetResponse`

- Kind: `object`
- Description: Response model for smart queue presets.

| Field         | Type                                     | Required | Description |
| ------------- | ---------------------------------------- | -------- | ----------- |
| `description` | `string`                                 | yes      | -           |
| `items`       | `TaskResponse`                           | no       | -           |
| `links`       | `JsonObject`                             | no       | -           |
| `name`        | `string`                                 | yes      | -           |
| `next_steps`  | `array<string>`                          | no       | -           |
| `params`      | `JsonObject`                             | no       | -           |
| `population`  | `'visible_operator' \| 'scoped_project'` | yes      | -           |
| `total_count` | `integer`                                | yes      | -           |

### `RenewCheckoutResponse`

- Kind: `object`
- Description: Checkout renewal response.

| Field         | Type             | Required | Description |
| ------------- | ---------------- | -------- | ----------- |
| `lease_until` | `string \| null` | yes      | -           |
| `status`      | `string`         | yes      | -           |

### `RetentionPoliciesPagePayload`

- Kind: `object`
- Description: Pagination payload for retention policies.

| Field         | Type              | Required | Description |
| ------------- | ----------------- | -------- | ----------- |
| `has_more`    | `boolean`         | yes      | -           |
| `limit`       | `integer`         | yes      | -           |
| `next_offset` | `integer \| null` | yes      | -           |
| `offset`      | `integer`         | yes      | -           |
| `total_count` | `integer`         | yes      | -           |

### `RetentionPoliciesResponsePayload`

- Kind: `object`
- Description: List retention policies payload.

| Field   | Type                             | Required | Description |
| ------- | -------------------------------- | -------- | ----------- |
| `items` | `TestRunRetentionPolicyResponse` | yes      | -           |
| `page`  | `RetentionPoliciesPagePayload`   | yes      | -           |

### `RevisionChangeResponse`

- Kind: `object`
- Description: Response model for a revision change.

| Field         | Type             | Required | Description |
| ------------- | ---------------- | -------- | ----------- |
| `change_type` | `ChangeType`     | yes      | -           |
| `field_name`  | `string`         | yes      | -           |
| `new_value`   | `string \| null` | yes      | -           |
| `old_value`   | `string \| null` | yes      | -           |

### `RevisionDiffResponse`

- Kind: `object`
- Description: Response model for a revision diff.

| Field                    | Type                     | Required | Description |
| ------------------------ | ------------------------ | -------- | ----------- |
| `changes`                | `RevisionChangeResponse` | no       | -           |
| `entity_id`              | `string`                 | yes      | -           |
| `entity_type`            | `string`                 | yes      | -           |
| `from_revision`          | `integer`                | yes      | -           |
| `intermediate_revisions` | `array<string>`          | no       | -           |
| `to_revision`            | `integer`                | yes      | -           |

### `RevisionEntryResponse`

- Kind: `object`
- Description: Response model for a revision entry.

| Field                | Type                     | Required | Description |
| -------------------- | ------------------------ | -------- | ----------- |
| `change_type`        | `ChangeType`             | yes      | -           |
| `changes`            | `RevisionChangeResponse` | no       | -           |
| `content`            | `JsonObject`             | yes      | -           |
| `content_hash`       | `string`                 | yes      | -           |
| `created_at`         | `string`                 | yes      | -           |
| `created_by`         | `string \| null`         | yes      | -           |
| `entity_id`          | `string`                 | yes      | -           |
| `entity_type`        | `string`                 | yes      | -           |
| `message`            | `string \| null`         | yes      | -           |
| `metadata`           | `map<string, string>`    | no       | -           |
| `parent_revision_id` | `string \| null`         | yes      | -           |
| `revision_id`        | `string`                 | yes      | -           |
| `revision_number`    | `integer`                | yes      | -           |

### `RevisionHistoryBundleResponse`

- Kind: `object`
- Description: Response model for revision history bundles.

| Field            | Type                                                    | Required | Description |
| ---------------- | ------------------------------------------------------- | -------- | ----------- |
| `entity_id`      | `string`                                                | yes      | -           |
| `entity_type`    | `string`                                                | yes      | -           |
| `generated_at`   | `string`                                                | yes      | -           |
| `history`        | `RevisionHistoryPageResponse`                           | yes      | -           |
| `linked`         | `map<string, LinkedEntitySummaryResponse>`              | no       | -           |
| `linked_history` | `map<string, map<string, RevisionHistoryPageResponse>>` | no       | -           |

### `RevisionHistoryPageResponse`

- Kind: `object`
- Description: Response model for paginated revision history.

| Field   | Type                    | Required | Description |
| ------- | ----------------------- | -------- | ----------- |
| `items` | `RevisionEntryResponse` | no       | -           |
| `page`  | `JsonObject`            | no       | -           |

### `RootScenarioPayload`

- Kind: `object`
- Description: Scenario bootstrap path for real-world usage.

| Field           | Type            | Required | Description |
| --------------- | --------------- | -------- | ----------- |
| `continue_with` | `array<string>` | yes      | -           |
| `goal`          | `string`        | yes      | -           |
| `name`          | `string`        | yes      | -           |
| `start_with`    | `string`        | yes      | -           |

### `SavedSearchListResponse`

- Kind: `object`
- Description: Response model for listing saved searches.

| Field         | Type                  | Required | Description |
| ------------- | --------------------- | -------- | ----------- |
| `items`       | `SavedSearchResponse` | no       | -           |
| `limit`       | `integer`             | yes      | -           |
| `links`       | `JsonObject`          | no       | -           |
| `next_steps`  | `array<string>`       | no       | -           |
| `offset`      | `integer`             | yes      | -           |
| `params`      | `JsonObject`          | no       | -           |
| `total_count` | `integer`             | yes      | -           |

### `SavedSearchRequest`

- Kind: `object`
- Description: Request model for creating a saved search.

| Field         | Type                                                   | Required | Description |
| ------------- | ------------------------------------------------------ | -------- | ----------- |
| `description` | `string \| null`                                       | no       | -           |
| `filters`     | `JsonObject`                                           | no       | -           |
| `name`        | `string`                                               | yes      | -           |
| `owner`       | `string \| null`                                       | no       | -           |
| `scope_id`    | `string \| null`                                       | no       | -           |
| `scope_type`  | `'global' \| 'organization' \| 'program' \| 'project'` | no       | -           |
| `sort_by`     | `string \| null`                                       | no       | -           |
| `sort_dir`    | `'asc' \| 'desc' \| null`                              | no       | -           |

### `SavedSearchResponse`

- Kind: `object`
- Description: Response model for saved search.

| Field         | Type                                                   | Required | Description |
| ------------- | ------------------------------------------------------ | -------- | ----------- |
| `archived_at` | `string \| null`                                       | no       | -           |
| `created_at`  | `string`                                               | yes      | -           |
| `description` | `string \| null`                                       | yes      | -           |
| `filters`     | `JsonObject`                                           | yes      | -           |
| `id`          | `string`                                               | yes      | -           |
| `name`        | `string`                                               | yes      | -           |
| `owner`       | `ActorReferencePayload \| null`                        | no       | -           |
| `scope_id`    | `string \| null`                                       | yes      | -           |
| `scope_type`  | `'global' \| 'organization' \| 'program' \| 'project'` | yes      | -           |
| `sort_by`     | `string \| null`                                       | yes      | -           |
| `sort_dir`    | `'asc' \| 'desc' \| null`                              | yes      | -           |
| `updated_at`  | `string`                                               | yes      | -           |

### `SavedSearchRunResponse`

- Kind: `object`
- Description: Response model for saved search execution.

| Field          | Type                  | Required | Description |
| -------------- | --------------------- | -------- | ----------- |
| `items`        | `TaskResponse`        | no       | -           |
| `limit`        | `integer`             | yes      | -           |
| `links`        | `JsonObject`          | no       | -           |
| `next_steps`   | `array<string>`       | no       | -           |
| `offset`       | `integer`             | yes      | -           |
| `params`       | `JsonObject`          | no       | -           |
| `saved_search` | `SavedSearchResponse` | yes      | -           |
| `total_count`  | `integer`             | yes      | -           |

### `SavedSearchUpdateRequest`

- Kind: `object`
- Description: Request model for updating a saved search.

| Field         | Type                                                           | Required | Description |
| ------------- | -------------------------------------------------------------- | -------- | ----------- |
| `description` | `string \| null`                                               | no       | -           |
| `filters`     | `JsonObject \| null`                                           | no       | -           |
| `name`        | `string \| null`                                               | no       | -           |
| `owner`       | `string \| null`                                               | no       | -           |
| `scope_id`    | `string \| null`                                               | no       | -           |
| `scope_type`  | `'global' \| 'organization' \| 'program' \| 'project' \| null` | no       | -           |
| `sort_by`     | `string \| null`                                               | no       | -           |
| `sort_dir`    | `'asc' \| 'desc' \| null`                                      | no       | -           |

### `Scope`

- Kind: `object`
- Description: Per-scope prune summary.

| Field                   | Type                                       | Required | Description |
| ----------------------- | ------------------------------------------ | -------- | ----------- |
| `artifact_bytes_after`  | `integer`                                  | yes      | -           |
| `artifact_bytes_before` | `integer`                                  | yes      | -           |
| `artifact_bytes_pruned` | `integer`                                  | yes      | -           |
| `log_bytes_after`       | `integer`                                  | yes      | -           |
| `log_bytes_before`      | `integer`                                  | yes      | -           |
| `log_bytes_pruned`      | `integer`                                  | yes      | -           |
| `max_age_days`          | `integer`                                  | yes      | -           |
| `max_artifact_bytes`    | `integer`                                  | yes      | -           |
| `max_log_bytes`         | `integer`                                  | yes      | -           |
| `policy_id`             | `string \| null`                           | no       | -           |
| `pruned_run_ids`        | `array<string>`                            | no       | -           |
| `runs_artifacts_pruned` | `integer`                                  | yes      | -           |
| `runs_logs_pruned`      | `integer`                                  | yes      | -           |
| `runs_pruned`           | `integer`                                  | yes      | -           |
| `runs_scanned`          | `integer`                                  | yes      | -           |
| `scope_id`              | `string`                                   | yes      | -           |
| `scope_type`            | `'default' \| 'project' \| 'organization'` | yes      | -           |
| `stderr_pruned`         | `integer`                                  | yes      | -           |
| `stdout_pruned`         | `integer`                                  | yes      | -           |

### `SessionStatus`

- Kind: `enum`
- Description: Status of an agent session.
- Allowed values: `'active'`, `'paused'`, `'ended'`
- Top-level fields: _none_

### `StateTransitionResponse`

- Kind: `object`
- Description: Response model for a state transition.

| Field                       | Type              | Required | Description |
| --------------------------- | ----------------- | -------- | ----------- |
| `duration_in_state_seconds` | `integer \| null` | yes      | -           |
| `entity_id`                 | `string`          | yes      | -           |
| `entity_type`               | `string`          | yes      | -           |
| `from_state`                | `string \| null`  | yes      | -           |
| `id`                        | `string`          | yes      | -           |
| `metadata`                  | `JsonObject`      | no       | -           |
| `reason`                    | `string \| null`  | yes      | -           |
| `timestamp`                 | `string`          | yes      | -           |
| `to_state`                  | `string`          | yes      | -           |
| `triggered_by`              | `string`          | yes      | -           |

### `TaskActionRequest`

- Kind: `object`
- Description: Request model for task status actions.

| Field          | Type             | Required | Description |
| -------------- | ---------------- | -------- | ----------- |
| `actual_hours` | `number \| null` | no       | -           |
| `reason`       | `string \| null` | no       | -           |
| `updated_by`   | `string \| null` | no       | -           |

### `TaskCompletionActionResponse`

- Kind: `object`
- Description: Response model for task completion side effects.

| Field             | Type           | Required | Description |
| ----------------- | -------------- | -------- | ----------- |
| `newly_unblocked` | `TaskResponse` | no       | -           |
| `status`          | `'completed'`  | yes      | -           |
| `task_id`         | `string`       | yes      | -           |

### `TaskCreate`

- Kind: `object`
- Description: Request model for creating a task.

| Field               | Type              | Required | Description |
| ------------------- | ----------------- | -------- | ----------- |
| `complexity_points` | `integer \| null` | no       | -           |
| `description`       | `string \| null`  | no       | -           |
| `parent_id`         | `string \| null`  | no       | -           |
| `priority`          | `string`          | no       | -           |
| `project_id`        | `string`          | yes      | -           |
| `tags`              | `array<string>`   | no       | -           |
| `title`             | `string`          | yes      | -           |

### `TaskDependencyCreate`

- Kind: `object`
- Description: Request model for creating a task dependency.

| Field             | Type     | Required | Description |
| ----------------- | -------- | -------- | ----------- |
| `dependency_type` | `string` | no       | -           |
| `depends_on_id`   | `string` | yes      | -           |

### `TaskDependencyDetailResponse`

- Kind: `object`
- Description: Response model for dependency task details.

| Field                | Type                 | Required | Description |
| -------------------- | -------------------- | -------- | ----------- |
| `id`                 | `string`             | yes      | -           |
| `last_activity_at`   | `string \| null`     | yes      | -           |
| `last_transition_at` | `string \| null`     | yes      | -           |
| `priority`           | `Priority \| null`   | yes      | -           |
| `project_id`         | `string \| null`     | yes      | -           |
| `project_name`       | `string \| null`     | yes      | -           |
| `status`             | `TaskStatus \| null` | yes      | -           |
| `title`              | `string \| null`     | yes      | -           |
| `updated_at`         | `string \| null`     | yes      | -           |

### `TaskDependencyGraphResponse`

- Kind: `object`
- Description: Response model for task dependency graph.

| Field                | Type                           | Required | Description |
| -------------------- | ------------------------------ | -------- | ----------- |
| `blocked_by`         | `array<string>`                | no       | -           |
| `blocked_by_details` | `TaskDependencyDetailResponse` | no       | -           |
| `blocking`           | `array<string>`                | no       | -           |
| `blocking_details`   | `TaskDependencyDetailResponse` | no       | -           |
| `last_activity_at`   | `string \| null`               | yes      | -           |
| `last_transition_at` | `string \| null`               | yes      | -           |
| `priority`           | `Priority \| null`             | yes      | -           |
| `project_id`         | `string \| null`               | yes      | -           |
| `project_name`       | `string \| null`               | yes      | -           |
| `status`             | `TaskStatus \| null`           | yes      | -           |
| `task_id`            | `string`                       | yes      | -           |
| `task_title`         | `string \| null`               | yes      | -           |
| `updated_at`         | `string \| null`               | yes      | -           |

### `TaskDependencyResponse`

- Kind: `object`
- Description: Response model for task dependencies.

| Field             | Type                                       | Required | Description |
| ----------------- | ------------------------------------------ | -------- | ----------- |
| `created_at`      | `string`                                   | yes      | -           |
| `dependency_type` | `'blocks' \| 'relates_to' \| 'duplicates'` | yes      | -           |
| `depends_on_id`   | `string`                                   | yes      | -           |
| `id`              | `string`                                   | yes      | -           |
| `task_id`         | `string`                                   | yes      | -           |
| `updated_at`      | `string`                                   | yes      | -           |

### `TaskDuplicateMerge`

- Kind: `object`
- Description: Request model for merging duplicate tasks.

| Field                | Type            | Required | Description |
| -------------------- | --------------- | -------- | ----------- |
| `cancel_duplicates`  | `boolean`       | no       | -           |
| `duplicate_task_ids` | `array<string>` | no       | -           |
| `primary_task_id`    | `string`        | yes      | -           |

### `TaskDuplicateMergePreview`

- Kind: `object`
- Description: Request model for previewing duplicate task merges.

| Field                | Type            | Required | Description |
| -------------------- | --------------- | -------- | ----------- |
| `duplicate_task_ids` | `array<string>` | no       | -           |
| `primary_task_id`    | `string`        | yes      | -           |

### `TaskEvidenceCreate`

- Kind: `object`
- Description: Request model for creating task evidence.

| Field           | Type             | Required | Description |
| --------------- | ---------------- | -------- | ----------- |
| `created_by`    | `string \| null` | no       | -           |
| `description`   | `string \| null` | no       | -           |
| `evidence_type` | `string`         | yes      | -           |
| `metadata`      | `JsonObject`     | no       | -           |
| `reference`     | `string`         | yes      | -           |

### `TaskEvidenceResponse`

- Kind: `object`
- Description: Response model for task evidence.

| Field           | Type                             | Required | Description |
| --------------- | -------------------------------- | -------- | ----------- |
| `created_at`    | `string`                         | yes      | -           |
| `created_by`    | `string`                         | yes      | -           |
| `description`   | `string \| null`                 | yes      | -           |
| `evidence_type` | `string`                         | yes      | -           |
| `id`            | `string`                         | yes      | -           |
| `metadata`      | `JsonObject`                     | yes      | -           |
| `reference`     | `string`                         | yes      | -           |
| `task_id`       | `string`                         | yes      | -           |
| `test_run`      | `TestRunSummaryResponse \| null` | no       | -           |

### `TaskResponse`

- Kind: `object`
- Description: Response model for task.

| Field                      | Type                            | Required | Description |
| -------------------------- | ------------------------------- | -------- | ----------- |
| `actual_hours`             | `number \| null`                | yes      | -           |
| `assignee`                 | `ActorReferencePayload \| null` | no       | -           |
| `checkout`                 | `CheckoutPayload \| null`       | no       | -           |
| `completion_criteria`      | `array<string>`                 | no       | -           |
| `completion_ready`         | `boolean`                       | no       | -           |
| `complexity_points`        | `integer \| null`               | yes      | -           |
| `created_at`               | `string`                        | yes      | -           |
| `current_progress_percent` | `integer`                       | yes      | -           |
| `current_state`            | `string \| null`                | yes      | -           |
| `description`              | `string \| null`                | yes      | -           |
| `id`                       | `string`                        | yes      | -           |
| `last_activity_at`         | `string \| null`                | no       | -           |
| `last_transition_at`       | `string \| null`                | no       | -           |
| `linked_plan_count`        | `integer`                       | no       | -           |
| `linked_plans`             | `JsonObject`                    | no       | -           |
| `links`                    | `JsonObject`                    | no       | -           |
| `next_steps`               | `array<string>`                 | no       | -           |
| `parent_id`                | `string \| null`                | yes      | -           |
| `priority`                 | `Priority`                      | yes      | -           |
| `project_id`               | `string`                        | yes      | -           |
| `status`                   | `TaskStatus`                    | yes      | -           |
| `title`                    | `string`                        | yes      | -           |
| `updated_at`               | `string`                        | yes      | -           |
| `workflow_id`              | `string \| null`                | yes      | -           |

### `TaskStatus`

- Kind: `enum`
- Description: Status of a task.
- Allowed values: `'todo'`, `'in_progress'`, `'blocked'`, `'in_review'`, `'done'`, `'cancelled'`
- Top-level fields: _none_

### `TaskTreeNode`

- Kind: `object`
- Description: Response model for a task tree node.

| Field      | Type           | Required | Description |
| ---------- | -------------- | -------- | ----------- |
| `children` | `TaskTreeNode` | no       | -           |
| `depth`    | `integer`      | no       | -           |
| `task`     | `TaskResponse` | yes      | -           |

### `TaskTreeResponse`

- Kind: `object`
- Description: Response model for a task tree response.

| Field          | Type             | Required | Description |
| -------------- | ---------------- | -------- | ----------- |
| `nodes`        | `TaskTreeNode`   | no       | -           |
| `project_id`   | `string`         | yes      | -           |
| `root_task_id` | `string \| null` | no       | -           |

### `TaskUpdate`

- Kind: `object`
- Description: Request model for updating a task.

| Field                       | Type                    | Required | Description |
| --------------------------- | ----------------------- | -------- | ----------- |
| `clear_completion_criteria` | `boolean`               | no       | -           |
| `clear_parent`              | `boolean`               | no       | -           |
| `completion_criteria`       | `array<string> \| null` | no       | -           |
| `complexity_points`         | `integer \| null`       | no       | -           |
| `description`               | `string \| null`        | no       | -           |
| `parent_id`                 | `string \| null`        | no       | -           |
| `priority`                  | `string \| null`        | no       | -           |
| `title`                     | `string \| null`        | no       | -           |

### `TeamCreate`

- Kind: `object`
- Description: Request model for creating a team.

| Field         | Type             | Required | Description |
| ------------- | ---------------- | -------- | ----------- |
| `description` | `string \| null` | no       | -           |
| `members`     | `array<string>`  | no       | -           |
| `name`        | `string`         | yes      | -           |
| `org_id`      | `string \| null` | no       | -           |
| `owner`       | `string \| null` | no       | -           |
| `tags`        | `array<string>`  | no       | -           |

### `TeamResponse`

- Kind: `object`
- Description: Response model for team.

| Field         | Type                            | Required | Description |
| ------------- | ------------------------------- | -------- | ----------- |
| `created_at`  | `string`                        | yes      | -           |
| `description` | `string \| null`                | yes      | -           |
| `id`          | `string`                        | yes      | -           |
| `members`     | `ActorReferencePayload`         | no       | -           |
| `name`        | `string`                        | yes      | -           |
| `org_id`      | `string \| null`                | yes      | -           |
| `owner`       | `ActorReferencePayload \| null` | no       | -           |
| `status`      | `TeamStatus`                    | yes      | -           |
| `tags`        | `array<string>`                 | yes      | -           |
| `updated_at`  | `string`                        | yes      | -           |

### `TeamStatus`

- Kind: `enum`
- Description: Status of a team.
- Allowed values: `'active'`, `'archived'`
- Top-level fields: _none_

### `TeamUpdate`

- Kind: `object`
- Description: Request model for updating a team.

| Field         | Type                    | Required | Description |
| ------------- | ----------------------- | -------- | ----------- |
| `description` | `string \| null`        | no       | -           |
| `members`     | `array<string> \| null` | no       | -           |
| `name`        | `string \| null`        | no       | -           |
| `owner`       | `string \| null`        | no       | -           |
| `status`      | `string \| null`        | no       | -           |
| `tags`        | `array<string> \| null` | no       | -           |

### `TestRunCreate`

- Kind: `object`
- Description: Request model for creating a test run record.

| Field              | Type              | Required | Description |
| ------------------ | ----------------- | -------- | ----------- |
| `artifacts`        | `JsonObject`      | no       | -           |
| `command`          | `string \| null`  | no       | -           |
| `config`           | `JsonObject`      | no       | -           |
| `duration_seconds` | `number \| null`  | no       | -           |
| `exit_code`        | `integer \| null` | no       | -           |
| `finished_at`      | `string`          | yes      | -           |
| `logs`             | `JsonObject`      | no       | -           |
| `plan_id`          | `string \| null`  | no       | -           |
| `project_id`       | `string \| null`  | no       | -           |
| `run_id`           | `string \| null`  | no       | -           |
| `runner`           | `string \| null`  | no       | -           |
| `server_id`        | `string`          | yes      | -           |
| `started_at`       | `string`          | yes      | -           |
| `stderr`           | `string \| null`  | no       | -           |
| `stdout`           | `string \| null`  | no       | -           |
| `success`          | `boolean`         | yes      | -           |
| `task_ids`         | `array<string>`   | no       | -           |

### `TestRunPruneResponse`

- Kind: `object`
- Description: Response model for test run pruning.

| Field                   | Type            | Required | Description |
| ----------------------- | --------------- | -------- | ----------- |
| `artifact_bytes_after`  | `integer`       | yes      | -           |
| `artifact_bytes_before` | `integer`       | yes      | -           |
| `artifact_bytes_pruned` | `integer`       | yes      | -           |
| `dry_run`               | `boolean`       | yes      | -           |
| `log_bytes_after`       | `integer`       | yes      | -           |
| `log_bytes_before`      | `integer`       | yes      | -           |
| `log_bytes_pruned`      | `integer`       | yes      | -           |
| `pruned_run_ids`        | `array<string>` | no       | -           |
| `runs_artifacts_pruned` | `integer`       | yes      | -           |
| `runs_logs_pruned`      | `integer`       | yes      | -           |
| `runs_pruned`           | `integer`       | yes      | -           |
| `runs_scanned`          | `integer`       | yes      | -           |
| `scopes`                | `Scope`         | no       | -           |
| `stderr_pruned`         | `integer`       | yes      | -           |
| `stdout_pruned`         | `integer`       | yes      | -           |

### `TestRunResponse`

- Kind: `object`
- Description: Response model for test run records.

| Field              | Type                 | Required | Description |
| ------------------ | -------------------- | -------- | ----------- |
| `artifacts`        | `JsonObject \| null` | no       | -           |
| `command`          | `string \| null`     | no       | -           |
| `duration_seconds` | `number \| null`     | yes      | -           |
| `exit_code`        | `integer \| null`    | yes      | -           |
| `finished_at`      | `string`             | yes      | -           |
| `id`               | `string`             | yes      | -           |
| `logs`             | `JsonObject \| null` | no       | -           |
| `plan_id`          | `string \| null`     | no       | -           |
| `project_id`       | `string \| null`     | yes      | -           |
| `runner`           | `string \| null`     | no       | -           |
| `server_id`        | `string`             | yes      | -           |
| `started_at`       | `string`             | yes      | -           |
| `stderr`           | `string \| null`     | no       | -           |
| `stdout`           | `string \| null`     | no       | -           |
| `success`          | `boolean`            | yes      | -           |
| `task_ids`         | `array<string>`      | no       | -           |

### `TestRunRetentionPolicyResponse`

- Kind: `object`
- Description: Response model for test run retention policies.

| Field                | Type                          | Required | Description |
| -------------------- | ----------------------------- | -------- | ----------- |
| `archived_at`        | `string \| null`              | no       | -           |
| `created_at`         | `string`                      | yes      | -           |
| `id`                 | `string`                      | yes      | -           |
| `max_age_days`       | `integer`                     | yes      | -           |
| `max_artifact_bytes` | `integer`                     | yes      | -           |
| `max_log_bytes`      | `integer`                     | yes      | -           |
| `notes`              | `string \| null`              | no       | -           |
| `scope_id`           | `string`                      | yes      | -           |
| `scope_type`         | `'project' \| 'organization'` | yes      | -           |
| `updated_at`         | `string`                      | yes      | -           |

### `TestRunRetentionResponse`

- Kind: `object`
- Description: Response model for test run retention usage.

| Field                           | Type                       | Required | Description |
| ------------------------------- | -------------------------- | -------- | ----------- |
| `alerts`                        | `Alert`                    | no       | -           |
| `items`                         | `TestRunUsageItemResponse` | no       | -           |
| `max_age_days`                  | `integer`                  | yes      | -           |
| `max_artifact_bytes`            | `integer`                  | yes      | -           |
| `max_log_bytes`                 | `integer`                  | yes      | -           |
| `policies`                      | `PolicyUsage`              | no       | -           |
| `sorted_by`                     | `'largest' \| 'recent'`    | yes      | -           |
| `total_artifact_bytes`          | `integer`                  | yes      | -           |
| `total_artifact_recorded_bytes` | `integer`                  | yes      | -           |
| `total_bytes`                   | `integer`                  | yes      | -           |
| `total_log_bytes`               | `integer`                  | yes      | -           |
| `total_log_bytes_combined`      | `integer`                  | yes      | -           |
| `total_runs`                    | `integer`                  | yes      | -           |
| `total_stderr_bytes`            | `integer`                  | yes      | -           |
| `total_stdout_bytes`            | `integer`                  | yes      | -           |

### `TestRunSummaryResponse`

- Kind: `object`
- Description: Summary model for test run evidence.

| Field              | Type              | Required | Description |
| ------------------ | ----------------- | -------- | ----------- |
| `command`          | `string \| null`  | no       | -           |
| `duration_seconds` | `number \| null`  | yes      | -           |
| `exit_code`        | `integer \| null` | yes      | -           |
| `finished_at`      | `string`          | yes      | -           |
| `id`               | `string`          | yes      | -           |
| `started_at`       | `string`          | yes      | -           |
| `stderr`           | `string \| null`  | no       | -           |
| `stdout`           | `string \| null`  | no       | -           |
| `success`          | `boolean`         | yes      | -           |

### `TestRunUsageItemResponse`

- Kind: `object`
- Description: Response model for per-run storage usage.

| Field                     | Type             | Required | Description |
| ------------------------- | ---------------- | -------- | ----------- |
| `artifact_bytes`          | `integer`        | yes      | -           |
| `artifact_recorded_bytes` | `integer`        | yes      | -           |
| `artifacts_missing`       | `integer`        | yes      | -           |
| `finished_at`             | `string`         | yes      | -           |
| `log_bytes`               | `integer`        | yes      | -           |
| `log_total_bytes`         | `integer`        | yes      | -           |
| `project_id`              | `string \| null` | yes      | -           |
| `run_id`                  | `string`         | yes      | -           |
| `server_id`               | `string`         | yes      | -           |
| `stderr_bytes`            | `integer`        | yes      | -           |
| `stdout_bytes`            | `integer`        | yes      | -           |
| `total_bytes`             | `integer`        | yes      | -           |

### `TransitionTimelineResponse`

- Kind: `object`
- Description: Response model for a transition timeline.

| Field                          | Type                      | Required | Description |
| ------------------------------ | ------------------------- | -------- | ----------- |
| `average_state_duration_hours` | `number`                  | yes      | -           |
| `entity_id`                    | `string`                  | yes      | -           |
| `entity_type`                  | `string`                  | yes      | -           |
| `kind`                         | `'workflow' \| 'status'`  | yes      | -           |
| `state_durations`              | `map<string, integer>`    | yes      | -           |
| `total_duration_hours`         | `number`                  | yes      | -           |
| `total_duration_seconds`       | `integer`                 | yes      | -           |
| `transitions`                  | `StateTransitionResponse` | no       | -           |

### `WatcherCreate`

- Kind: `object`
- Description: Request model for adding a watcher.

| Field         | Type     | Required | Description |
| ------------- | -------- | -------- | ----------- |
| `entity_id`   | `string` | yes      | -           |
| `entity_type` | `string` | yes      | -           |
| `watcher`     | `string` | yes      | -           |

### `WatcherListResponse`

- Kind: `object`
- Description: Response model for watcher lists.

| Field         | Type              | Required | Description |
| ------------- | ----------------- | -------- | ----------- |
| `items`       | `WatcherResponse` | no       | -           |
| `limit`       | `integer`         | no       | -           |
| `links`       | `JsonObject`      | no       | -           |
| `next_steps`  | `array<string>`   | no       | -           |
| `offset`      | `integer`         | no       | -           |
| `params`      | `JsonObject`      | no       | -           |
| `total_count` | `integer`         | no       | -           |

### `WatcherResponse`

- Kind: `object`
- Description: Response model for watchers.

| Field         | Type             | Required | Description |
| ------------- | ---------------- | -------- | ----------- |
| `archived_at` | `string \| null` | no       | -           |
| `created_at`  | `string`         | yes      | -           |
| `entity_id`   | `string`         | yes      | -           |
| `entity_type` | `string`         | yes      | -           |
| `id`          | `string`         | yes      | -           |
| `updated_at`  | `string`         | yes      | -           |
| `watcher`     | `string`         | yes      | -           |

### `WorkDailyPayload`

- Kind: `object`
- Top-level fields: _none_

### `WorkSnapshotDigestResponse`

- Kind: `object`
- Description: Response model for snapshot digest.

| Field              | Type             | Required | Description |
| ------------------ | ---------------- | -------- | ----------- |
| `evidence_added`   | `integer`        | yes      | -           |
| `failed_test_runs` | `integer`        | yes      | -           |
| `note`             | `string \| null` | yes      | -           |
| `plans_created`    | `integer`        | yes      | -           |
| `plans_updated`    | `integer`        | yes      | -           |
| `since`            | `string \| null` | yes      | -           |
| `tasks_completed`  | `integer`        | yes      | -           |
| `tasks_created`    | `integer`        | yes      | -           |
| `tasks_updated`    | `integer`        | yes      | -           |
| `test_runs`        | `integer`        | yes      | -           |

### `WorkSnapshotEvidenceResponse`

- Kind: `object`
- Description: Response model for snapshot evidence counts.

| Field         | Type      | Required | Description |
| ------------- | --------- | -------- | ----------- |
| `new_count`   | `integer` | yes      | -           |
| `total_count` | `integer` | yes      | -           |

### `WorkSnapshotResponse`

- Kind: `object`
- Description: Response model for work snapshot.

| Field                    | Type                                                      | Required | Description |
| ------------------------ | --------------------------------------------------------- | -------- | ----------- |
| `digest`                 | `WorkSnapshotDigestResponse`                              | yes      | -           |
| `evidence`               | `WorkSnapshotEvidenceResponse`                            | yes      | -           |
| `generated_at`           | `string`                                                  | yes      | -           |
| `last_reviewed_at`       | `string \| null`                                          | yes      | -           |
| `lineage`                | `JsonObject \| null`                                      | yes      | -           |
| `links`                  | `JsonObject`                                              | no       | -           |
| `next_steps`             | `array<string>`                                           | no       | -           |
| `params`                 | `JsonObject`                                              | no       | -           |
| `recent_tasks`           | `WorkSnapshotTaskHighlightResponse`                       | no       | -           |
| `recent_test_runs`       | `WorkSnapshotRunHighlightResponse`                        | no       | -           |
| `retention`              | `JsonObject \| null`                                      | yes      | -           |
| `review_history_preview` | `WorkSnapshotReviewPreviewResponse`                       | no       | -           |
| `scope_id`               | `string`                                                  | yes      | -           |
| `scope_name`             | `string \| null`                                          | yes      | -           |
| `scope_type`             | `'organization' \| 'portfolio' \| 'program' \| 'project'` | yes      | -           |
| `totals`                 | `WorkSnapshotTotalsResponse`                              | yes      | -           |

### `WorkSnapshotReviewPreviewResponse`

- Kind: `object`
- Description: Response model for snapshot review history preview.

| Field         | Type             | Required | Description |
| ------------- | ---------------- | -------- | ----------- |
| `id`          | `string`         | yes      | -           |
| `metadata`    | `JsonObject`     | yes      | -           |
| `note`        | `string \| null` | yes      | -           |
| `reviewed_at` | `string`         | yes      | -           |
| `reviewed_by` | `string \| null` | yes      | -           |

### `WorkSnapshotReviewRequest`

- Kind: `object`
- Description: Request model for marking a snapshot review.

| Field         | Type             | Required | Description |
| ------------- | ---------------- | -------- | ----------- |
| `metadata`    | `JsonObject`     | no       | -           |
| `note`        | `string \| null` | no       | -           |
| `reviewed_by` | `string \| null` | no       | -           |

### `WorkSnapshotReviewResponse`

- Kind: `object`
- Description: Response model for snapshot review.

| Field         | Type                                                      | Required | Description |
| ------------- | --------------------------------------------------------- | -------- | ----------- |
| `id`          | `string`                                                  | yes      | -           |
| `links`       | `JsonObject`                                              | no       | -           |
| `metadata`    | `JsonObject`                                              | yes      | -           |
| `next_steps`  | `array<string>`                                           | no       | -           |
| `note`        | `string \| null`                                          | yes      | -           |
| `params`      | `JsonObject`                                              | no       | -           |
| `reviewed_at` | `string`                                                  | yes      | -           |
| `reviewed_by` | `string \| null`                                          | yes      | -           |
| `scope_id`    | `string`                                                  | yes      | -           |
| `scope_type`  | `'organization' \| 'portfolio' \| 'program' \| 'project'` | yes      | -           |

### `WorkSnapshotRunHighlightResponse`

- Kind: `object`
- Description: Response model for recent test run highlight.

| Field         | Type             | Required | Description |
| ------------- | ---------------- | -------- | ----------- |
| `command`     | `string \| null` | no       | -           |
| `finished_at` | `string`         | yes      | -           |
| `id`          | `string`         | yes      | -           |
| `project_id`  | `string \| null` | yes      | -           |
| `success`     | `boolean`        | yes      | -           |

### `WorkSnapshotTaskHighlightResponse`

- Kind: `object`
- Description: Response model for recent task highlight.

| Field           | Type                                    | Required | Description |
| --------------- | --------------------------------------- | -------- | ----------- |
| `evidence_gate` | `EvidenceGateIndicatorResponse \| null` | no       | -           |
| `id`            | `string`                                | yes      | -           |
| `project_id`    | `string`                                | yes      | -           |
| `status`        | `TaskStatus`                            | yes      | -           |
| `title`         | `string`                                | yes      | -           |
| `updated_at`    | `string`                                | yes      | -           |

### `WorkSnapshotTotalsResponse`

- Kind: `object`
- Description: Response model for snapshot totals.

| Field              | Type                                  | Required | Description |
| ------------------ | ------------------------------------- | -------- | ----------- |
| `blocked_tasks`    | `integer \| null`                     | no       | -           |
| `completed_tasks`  | `integer \| null`                     | no       | -           |
| `health_score`     | `number \| null`                      | no       | -           |
| `overdue_tasks`    | `integer \| null`                     | no       | -           |
| `risk_level`       | `'low' \| 'medium' \| 'high' \| null` | no       | -           |
| `total_goals`      | `integer \| null`                     | no       | -           |
| `total_objectives` | `integer \| null`                     | no       | -           |
| `total_projects`   | `integer \| null`                     | no       | -           |
| `total_tasks`      | `integer \| null`                     | no       | -           |

### `WorkflowAlign`

- Kind: `object`
- Description: Request model for workflow alignment.

| Field          | Type             | Required | Description              |
| -------------- | ---------------- | -------- | ------------------------ |
| `approved_by`  | `string \| null` | no       | -                        |
| `auto`         | `boolean`        | no       | -                        |
| `dry_run`      | `boolean`        | no       | -                        |
| `entity_id`    | `string \| null` | no       | Entity ID to align       |
| `entity_type`  | `string`         | no       | task, goal, or objective |
| `reason`       | `string \| null` | no       | -                        |
| `to_state`     | `string \| null` | no       | -                        |
| `triggered_by` | `string`         | yes      | -                        |

### `WorkflowAlignResponse`

- Kind: `object`
- Description: Response model for workflow alignment.

| Field                 | Type             | Required | Description |
| --------------------- | ---------------- | -------- | ----------- |
| `aligned`             | `boolean`        | no       | -           |
| `applied_transitions` | `array<string>`  | no       | -           |
| `entity_id`           | `string`         | yes      | -           |
| `from_state`          | `string \| null` | yes      | -           |
| `remaining`           | `array<string>`  | no       | -           |
| `target_state`        | `string`         | yes      | -           |

### `WorkflowAssign`

- Kind: `object`
- Description: Request model for assigning workflow.

| Field           | Type     | Required | Description |
| --------------- | -------- | -------- | ----------- |
| `initial_state` | `string` | yes      | -           |
| `workflow_name` | `string` | yes      | -           |

### `WorkflowListPayload`

- Kind: `object`
- Description: Workflow list response payload.

| Field       | Type                     | Required | Description |
| ----------- | ------------------------ | -------- | ----------- |
| `workflows` | `WorkflowSummaryPayload` | yes      | -           |

### `WorkflowSummaryPayload`

- Kind: `object`
- Description: Workflow summary payload.

| Field             | Type             | Required | Description |
| ----------------- | ---------------- | -------- | ----------- |
| `description`     | `string \| null` | yes      | -           |
| `entity_type`     | `string`         | yes      | -           |
| `id`              | `string`         | yes      | -           |
| `initial_state`   | `string`         | yes      | -           |
| `name`            | `string`         | yes      | -           |
| `states_count`    | `integer`        | yes      | -           |
| `terminal_states` | `array<string>`  | yes      | -           |

### `WorkflowTransition`

- Kind: `object`
- Description: Request model for workflow state transition.

| Field          | Type             | Required | Description |
| -------------- | ---------------- | -------- | ----------- |
| `approved_by`  | `string \| null` | no       | -           |
| `reason`       | `string \| null` | no       | -           |
| `to_state`     | `string`         | yes      | -           |
| `triggered_by` | `string`         | yes      | -           |

### `WorkflowTransitionResponse`

- Kind: `object`
- Description: Response model for workflow transition.

| Field          | Type             | Required | Description |
| -------------- | ---------------- | -------- | ----------- |
| `entity_id`    | `string`         | yes      | -           |
| `from_state`   | `string \| null` | yes      | -           |
| `timestamp`    | `string`         | yes      | -           |
| `to_state`     | `string`         | yes      | -           |
| `triggered_by` | `string`         | yes      | -           |
