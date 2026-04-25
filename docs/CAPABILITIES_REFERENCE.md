# PMS - Project Management System

**Version:** 0.1.0
**Total Capabilities:** 277

Self-evolving autonomous development platform

---

## Namespaces (Entity Types)

| Prefix   | Name          | Description                                    |
| -------- | ------------- | ---------------------------------------------- |
| `apikey` | api_key       | API keys and authentication credentials        |
| `ctx`    | context       | Context sessions                               |
| `ctxi`   | context_item  | Context items                                  |
| `dep`    | dependency    | Task dependencies                              |
| `doc`    | document      | Documents                                      |
| `evt`    | event         | System events                                  |
| `fb`     | feedback      | Feedback signals                               |
| `goal`   | goal          | Strategic goals with time horizons             |
| `host`   | remote_host   | SSH remote hosts                               |
| `know`   | knowledge     | Knowledge entries                              |
| `kr`     | key_result    | Objective key results with measurable targets  |
| `met`    | metric        | Metrics                                        |
| `mile`   | milestone     | Project milestones                             |
| `obj`    | objective     | Goal objectives with measurable outcomes       |
| `org`    | organization  | Organization containers and ownership          |
| `out`    | outcome       | Operation outcomes                             |
| `pat`    | pattern       | Reusable patterns                              |
| `plan`   | plan          | Plan artifacts for execution and decomposition |
| `port`   | portfolio     | Portfolio grouping of projects and goals       |
| `prog`   | program       | Program grouping under a portfolio             |
| `proj`   | project       | Project containers                             |
| `ref`    | reference     | Entity relationships                           |
| `rev`    | revision      | Entity revisions                               |
| `sess`   | session       | User sessions                                  |
| `srv`    | test_server   | AWS test servers                               |
| `step`   | workflow_step | Workflow steps                                 |
| `sug`    | suggestion    | System suggestions                             |
| `tag`    | tag           | Entity tags                                    |
| `task`   | task          | Work items and subtasks                        |
| `team`   | team          | Organization teams and membership              |
| `trig`   | trigger       | Workflow triggers                              |
| `trun`   | test_run      | Test execution runs                            |
| `wf`     | workflow      | Workflow definitions                           |
| `wfrun`  | workflow_run  | Workflow executions                            |

Namespace-generated IDs use the typed-ID `{prefix}_{uuid}` format for
families that participate in that utility layer. That registry surface is
separate from the full public runtime row-ID contract.

### Namespace Schema Details

#### `api_key` (`apikey`)

- Namespace-generated ID format: `apikey_<uuid>`
- Runtime row-ID contract scope: `public_stored_entity_family`
- Runtime row-ID style: `prefix_native`
- Fields: `name`, `scopes`, `rate_limit`, `expires_at`, `is_active`
- Required: `name`, `scopes`

#### `goal` (`goal`)

- Namespace-generated ID format: `goal_<uuid>`
- Runtime row-ID contract scope: `public_stored_entity_family`
- Runtime row-ID style: `uuid_native`
- Fields: `name`, `description`, `status`, `horizon`
- Required: `name`, `horizon`

#### `remote_host` (`host`)

- Namespace-generated ID format: `host_<uuid>`
- Runtime row-ID contract scope: `public_stored_entity_family`
- Runtime row-ID style: `uuid_native`
- Fields: `name`, `hostname`, `username`
- Required: `name`, `hostname`

#### `knowledge` (`know`)

- Namespace-generated ID format: `know_<uuid>`
- Runtime row-ID contract scope: `internal_or_non_public_namespace`
- Runtime row-ID style: not applicable
- Fields: `type`, `title`, `content`, `tags`
- Required: `type`, `title`

#### `key_result` (`kr`)

- Namespace-generated ID format: `kr_<uuid>`
- Runtime row-ID contract scope: `public_stored_entity_family`
- Runtime row-ID style: `uuid_native`
- Fields: `objective_id`, `name`, `status`, `target_value`
- Required: `objective_id`, `name`

#### `milestone` (`mile`)

- Namespace-generated ID format: `mile_<uuid>`
- Runtime row-ID contract scope: `public_stored_entity_family`
- Runtime row-ID style: `uuid_native`
- Fields: `name`, `due_date`, `status`
- Required: `name`

#### `objective` (`obj`)

- Namespace-generated ID format: `obj_<uuid>`
- Runtime row-ID contract scope: `public_stored_entity_family`
- Runtime row-ID style: `uuid_native`
- Fields: `goal_id`, `name`, `description`, `status`
- Required: `goal_id`, `name`

#### `organization` (`org`)

- Namespace-generated ID format: `org_<uuid>`
- Runtime row-ID contract scope: `public_stored_entity_family`
- Runtime row-ID style: `uuid_native`
- Fields: `name`, `description`, `owner`, `members`, `status`
- Required: `name`

#### `plan` (`plan`)

- Namespace-generated ID format: `plan_<uuid>`
- Runtime row-ID contract scope: `public_stored_entity_family`
- Runtime row-ID style: `uuid_native`
- Fields: `name`, `description`, `format`, `content`, `project_id`, `task_ids`
- Required: `name`, `format`, `content`

#### `portfolio` (`port`)

- Namespace-generated ID format: `port_<uuid>`
- Runtime row-ID contract scope: `public_stored_entity_family`
- Runtime row-ID style: `uuid_native`
- Fields: `name`, `description`, `project_ids`, `goal_ids`, `objective_ids`, `effective_goal_ids`, `effective_objective_ids`, `status`
- Required: `name`
- Field roles:
  - `project_ids`: Bulk scope-assignment input; portfolio readbacks expose authoritative project membership from child project foreign keys.
  - `goal_ids`: Direct portfolio-to-goal strategic links stored through native edge tables.
  - `objective_ids`: Direct portfolio-to-objective strategic links stored through native edge tables.
  - `effective_goal_ids`: Hydrated scope readback only: direct goal links plus project-derived goal scope.
  - `effective_objective_ids`: Hydrated scope readback only: direct objective links plus project-derived objective scope.

#### `program` (`prog`)

- Namespace-generated ID format: `prog_<uuid>`
- Runtime row-ID contract scope: `public_stored_entity_family`
- Runtime row-ID style: `uuid_native`
- Fields: `name`, `description`, `portfolio_id`, `project_ids`, `goal_ids`, `objective_ids`, `effective_goal_ids`, `effective_objective_ids`, `status`
- Required: `name`
- Field roles:
  - `project_ids`: Bulk scope-assignment input; program readbacks expose authoritative project membership from child project foreign keys.
  - `goal_ids`: Direct program-to-goal strategic links stored through native edge tables.
  - `objective_ids`: Direct program-to-objective strategic links stored through native edge tables.
  - `effective_goal_ids`: Hydrated scope readback only: direct goal links plus project-derived goal scope.
  - `effective_objective_ids`: Hydrated scope readback only: direct objective links plus project-derived objective scope.

#### `project` (`proj`)

- Namespace-generated ID format: `proj_<uuid>`
- Runtime row-ID contract scope: `public_stored_entity_family`
- Runtime row-ID style: `uuid_native`
- Fields: `name`, `description`, `status`
- Required: `name`

#### `reference` (`ref`)

- Namespace-generated ID format: `ref_<uuid>`
- Runtime row-ID contract scope: `internal_or_non_public_namespace`
- Runtime row-ID style: not applicable
- Fields: `source_id`, `target_id`, `relation`
- Required: `source_id`, `target_id`, `relation`

#### `task` (`task`)

- Namespace-generated ID format: `task_<uuid>`
- Runtime row-ID contract scope: `public_stored_entity_family`
- Runtime row-ID style: `uuid_native`
- Fields: `title`, `description`, `status`, `priority`
- Required: `title`

#### `team` (`team`)

- Namespace-generated ID format: `team_<uuid>`
- Runtime row-ID contract scope: `public_stored_entity_family`
- Runtime row-ID style: `uuid_native`
- Fields: `org_id`, `name`, `description`, `members`, `status`
- Required: `name`

#### `workflow` (`wf`)

- Namespace-generated ID format: `wf_<uuid>`
- Runtime row-ID contract scope: `internal_or_non_public_namespace`
- Runtime row-ID style: not applicable
- Fields: `name`, `description`, `steps`
- Required: `name`, `steps`

## MCP Tools

### Aws Tools

- **find_spot_instances**: Find cost-effective AWS spot instances for testing
- **launch_test_server**: Launch a spot instance test server
- **list_test_servers**: List all test servers
- **get_test_server**: Get details of a test server by name or ID
- **terminate_test_server**: Terminate a test server
- **terminate_all_servers**: Terminate all test servers, optionally filtered by project
- **run_tests_on_server**: Sync a project to a test server and run tests
- **exec_on_server**: Execute a command on a test server without syncing

### General Tools

- **create_actor**: Create a canonical actor for a human, persona, team, or runtime agent
- **list_actors**: List actors with optional kind or status filters
- **get_actor**: Get actor graph details and workload by actor handle or id
- **add_actor_alias**: Add an alias to an actor
- **add_actor_membership**: Add a membership edge between actors
- **get_dashboard**: Get an overview dashboard of all projects and tasks
- **get_work_snapshot**: Get a unified work snapshot for an organization, portfolio, program, or project
- **mark_work_snapshot_reviewed**: Record a review checkpoint for a work snapshot
- **get_work_daily**: Get a daily review summary with snapshot and queues
- **create_goal**: Create a new goal with horizon, optional description, and tags
- **list_goals**: List goals, optionally filtered by status or horizon
- **get_goal**: Get details of a goal by name or ID
- **get_goal_summary**: Get a rollup summary for a goal (objectives, key results, tasks)
- **update_goal**: Update goal fields like name, description, status, horizon, progress
- **complete_goal**: Mark a goal as completed
- **archive_goal**: Archive a goal
- **create_objective**: Create a new objective under a goal
- **list_objectives**: List objectives, optionally filtered by goal or status
- **get_objective**: Get details of an objective by ID
- **update_objective**: Update objective fields like name, description, status, progress
- **complete_objective**: Mark an objective as completed
- **archive_objective**: Archive an objective
- **create_key_result**: Create a new key result under an objective
- **list_key_results**: List key results, optionally filtered by objective or status
- **get_key_result**: Get details of a key result by ID
- **update_key_result**: Update key result fields like name, status, progress, values
- **complete_key_result**: Mark a key result as completed
- **archive_key_result**: Archive a key result
- **create_plan**: Create a plan artifact with JSON/YAML content and optional links
- **list_plans**: List plans, optionally filtered by status or links
- **get_plan**: Get plan details by name or ID
- **update_plan**: Update plan fields like status, format, content, or links
- **create_plan_test_job**: Create a plan-linked test job
- **list_plan_test_jobs**: List test jobs for a plan
- **get_plan_test_job**: Get details for a plan test job by ID
- **update_plan_test_job**: Update a plan test job
- **delete_plan_test_job**: Delete a plan test job by ID
- **run_plan_test_job**: Run a plan test job and return the test run summary
- **create_organization**: Create a new organization with members and tags
- **list_organizations**: List organizations, optionally filtered by status
- **get_organization**: Get organization details by name or ID
- **update_organization**: Update organization fields like status, members, tags, or owner
- **get_organization_summary**: Get organization rollup summary with teams, portfolios, and programs
- **get_organization_dashboard**: Get organization dashboard rollups across teams, portfolios, programs, and work
- **create_team**: Create a new team within an organization
- **list_teams**: List teams, optionally filtered by organization or status
- **get_team**: Get team details by name or ID
- **update_team**: Update team fields like status, members, tags, or owner
- **create_portfolio**: Create a new portfolio with linked projects, goals, and objectives
- **list_portfolios**: List portfolios, optionally filtered by organization or status
- **get_portfolio**: Get portfolio details by name or ID
- **update_portfolio**: Update portfolio fields like status, linked projects, linked goals, linked objectives, or tags
- **get_portfolio_summary**: Get portfolio rollup summary with goals, objectives, and risk
- **get_portfolio_dashboard**: Get portfolio dashboard rollups across projects and goals
- **create_program**: Create a new program with linked projects, goals, and objectives
- **list_programs**: List programs, optionally filtered by org, portfolio, or status
- **get_program**: Get program details by name or ID
- **update_program**: Update program fields like status, linked projects, linked goals, linked objectives, or tags
- **get_program_summary**: Get program rollup summary with goals, objectives, and risk
- **get_program_dashboard**: Get program dashboard rollups across projects and goals
- **create_saved_search**: Create a saved search queue for tasks
- **list_saved_searches**: List saved search queues
- **get_saved_search**: Get a saved search queue by ID
- **update_saved_search**: Update a saved search queue
- **delete_saved_search**: Delete a saved search queue
- **run_saved_search**: Run a saved search queue and return matching tasks
- **list_queue_presets**: List smart queue presets (ready/stale/blocked/overdue/at_risk)
- **get_queue_preset**: Get tasks from a smart queue preset
- **create_custom_field**: Create a custom field definition
- **list_custom_fields**: List custom field definitions
- **get_custom_field**: Get details for a custom field definition
- **update_custom_field**: Update a custom field definition
- **delete_custom_field**: Archive a custom field definition
- **restore_custom_field**: Restore a custom field definition
- **set_custom_field_value**: Set a custom field value for an entity
- **list_custom_field_values**: List custom field values for an entity
- **list_custom_field_values_for_field**: List custom field values for a definition
- **add_comment**: Add a comment to an entity
- **list_comments**: List comments for an entity
- **get_comment**: Get a comment by ID
- **delete_comment**: Archive a comment by ID
- **restore_comment**: Restore a comment by ID
- **add_watcher**: Add a watcher for an entity
- **list_watchers**: List watchers for an entity
- **remove_watcher**: Remove a watcher from an entity
- **restore_watcher**: Restore a watcher subscription by ID
- **create_automation_rule**: Create an automation rule
- **list_automation_rules**: List automation rules
- **get_automation_rule**: Get details for an automation rule
- **update_automation_rule**: Update an automation rule
- **delete_automation_rule**: Archive an automation rule
- **restore_automation_rule**: Restore an automation rule
- **run_automation_rules**: Run automation rules for an event
- **list_automation_rule_runs**: List automation rule runs
- **create_evidence_gate_rule**: Create an evidence gate rule for workflow transitions
- **list_evidence_gate_rules**: List evidence gate rules for a workflow transition
- **delete_evidence_gate_rule**: Delete an evidence gate rule by ID
- **create_test_run**: Create a test run record with output, logs, and artifacts
- **list_test_runs**: List test runs with optional filters
- **get_test_run**: Get a test run with optional output, logs, and artifacts
- **prune_test_runs**: Prune stored test run outputs by size or age
- **get_test_run_retention**: Get test run retention usage summary
- **assign_workflow**: Assign a workflow to a task, goal, or objective
- **transition_workflow**: Transition a task, goal, or objective to a new workflow state

### Project Tools

- **create_project**: Create a new project with a name, optional description, tags, and scope links
- **list_projects**: List all projects, optionally filtered by status (active, archived, completed)
- **get_project**: Get details of a project by name or ID
- **get_project_summary**: Get a summary of a project including stats and health score
- **archive_project**: Archive a project by name or ID
- **update_project**: Update project fields (name, description, tags, scope links, product_id)
- **delete_project**: Delete a project and all its tasks

### Remote Tools

- **list_remote_hosts**: List all configured remote hosts with their connection details
- **get_remote_host**: Get details of a remote host by name
- **test_remote_connection**: Test SSH connection to a remote host
- **execute_remote_command**: Execute a shell command on a remote host via SSH
- **sync_push**: Push local files to a remote host using rsync
- **sync_pull**: Pull files from a remote host to local using rsync
- **sync_to_server**: Sync project files to a test server without running tests

### Task Tools

- **create_task**: Create a new task in a project
- **list_tasks**: List tasks, optionally filtered by project and/or status
- **search_tasks**: Search tasks with rich filters (status, priority, tags, labels, dates)
- **find_duplicate_tasks**: Find duplicate tasks by normalized title
- **preview_merge_duplicate_tasks**: Preview duplicate task merges with conflicts and warnings
- **merge_duplicate_tasks**: Merge duplicate tasks by linking them to a primary task
- **get_task_proof_bundle**: Get a proof bundle for a task with evidence and test runs
- **list_ready_tasks**: List tasks ready to start (no blocking dependencies)
- **list_stale_tasks**: List tasks with no recent updates
- **start_task**: Start working on a task (change status to in_progress)
- **complete_task**: Mark a task as complete with optional actual hours worked
- **update_task_progress**: Update task progress with percent complete and status message
- **update_task**: Update task fields (title, description, parent_id, priority, complexity_points)
- **add_task_evidence**: Attach evidence to a task
- **checkout_task**: Checkout a task for exclusive work
- **renew_task_checkout**: Renew a task checkout lease
- **release_task_checkout**: Release a task checkout lease
- **delete_task**: Delete a task
- **block_task**: Mark a task as blocked with a reason
- **unblock_task**: Unblock a task (change status back to todo)
- **add_task_dependency**: Add a dependency: task_id depends on depends_on_id (must complete first)
- **get_task_tree**: Get hierarchical task tree for a project
- **get_blocked_tasks**: Get all blocked tasks, optionally filtered by project
- **bulk_create_tasks**: Create multiple tasks at once from a comma-separated list of titles

## Built-in Patterns

- **test_and_deploy** (workflow): Run tests, then build and deploy if tests pass
- **sync_and_test** (workflow): Sync to remote server and run tests
- **create_feature_branch** (workflow): Create a new feature branch with standard setup
- **async_crud_service** (code): Async CRUD service pattern
- **pytest_async_test** (code): Async pytest test pattern
- **import_cycle_fix** (error): Fix circular import errors
- **async_not_awaited_fix** (error): Fix 'coroutine was never awaited' warning
- **repository_pattern** (architecture): Repository pattern for data access

## Event Types

### Agent Events

- `agent.started`
- `agent.completed`
- `agent.failed`
- `agent.handoff`

### Custom Events

- `custom`

### Project Events

- `project.created`
- `project.updated`
- `project.archived`
- `project.completed`

### Remote Events

- `remote.command.started`
- `remote.command.completed`
- `remote.command.failed`

### Server Events

- `server.launched`
- `server.ready`
- `server.terminated`

### Sync Events

- `sync.started`
- `sync.completed`
- `sync.failed`

### System Events

- `system.started`
- `system.stopped`

### Task Events

- `task.created`
- `task.started`
- `task.completed`
- `task.blocked`
- `task.unblocked`
- `task.cancelled`

### Test Events

- `test.run.started`
- `test.run.completed`
- `test.run.failed`

### Tool Events

- `tool.invoked`
- `tool.completed`
- `tool.failed`
- `tool.generated`

### Workflow Events

- `workflow.started`
- `workflow.step.started`
- `workflow.step.completed`
- `workflow.step.failed`
- `workflow.completed`
- `workflow.failed`

## Reference Types

| Type           | Inverse        |
| -------------- | -------------- |
| `parent_of`    | `child_of`     |
| `child_of`     | `parent_of`    |
| `contains`     | `belongs_to`   |
| `belongs_to`   | `contains`     |
| `depends_on`   | `required_by`  |
| `blocks`       | `depends_on`   |
| `required_by`  | `depends_on`   |
| `triggered_by` | `triggers`     |
| `triggers`     | `triggered_by` |
| `caused_by`    | `causes`       |
| `causes`       | `caused_by`    |
| `related_to`   | `related_to`   |
| `references`   | `None`         |
| `uses`         | `used_by`      |
| `used_by`      | `uses`         |
| `executes`     | `executed_by`  |
| `executed_by`  | `executes`     |
| `produces`     | `produced_by`  |
| `produced_by`  | `produces`     |
| `learned_from` | `teaches`      |
| `teaches`      | `learned_from` |
| `similar_to`   | `similar_to`   |
| `derived_from` | `None`         |
| `positive_for` | `None`         |
| `negative_for` | `None`         |
| `feedback_on`  | `None`         |

## Knowledge Types

- `pattern`
- `solution`
- `procedure`
- `entity`
- `context`
- `preference`
- `template`
- `note`
- `tool_usage`
- `error_fix`

## Feedback Categories

- `behavior`
- `code_style`
- `communication`
- `workflow`
- `tool_use`
- `architecture`
- `testing`
- `documentation`
- `performance`
- `safety`
