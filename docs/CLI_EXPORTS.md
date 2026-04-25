## CLI Export Matrix

Most list/detail commands support `--format table|json|csv` (or `text|json|csv` for
single-entity views). Use these to integrate PMS into scripts and reports.

### General

- `pms init` (add `--reset --force` for a fresh local database)
- `pms quickstart --defaults --org <name> --product <name> --project <name> --portfolio <name> --program <name> --task <title> --create-plan/--no-create-plan --create-rollups/--no-create-rollups`
- `pms claudo import [claudo-export.json] --source-path ~/.claude/tasks --claudo-repo ~/repos/claudo --session <id> --project-root <repo> --project <name> --dry-run --no-goals --no-plans --format text|json`
- `pms claudo export <project> -o claudo-export.json --session-id <id> --materialize-claude <dir> --overwrite-materialized --format text|json`

Claudo interop uses the `claudo.task_graph.v1` interchange format for bulk
Claude todo bootstrap and staged round-trips. See
[`docs/CLAUDO_INTEROP.md`](CLAUDO_INTEROP.md).

### Loops

- `pms loop init --config pms-loop.yml --prompt-file PROMPT.md`
- `pms loop prompt-template --project <name|id> --goal <name|id> --plan <name|id> --prompt-file PROMPT.md --force`
- `pms loop setup --defaults --config pms-loop.yml --prompt-file PROMPT.md --goal <name>`
- `pms loop run --agent claude|codex --project <name|id> --prompt-file PROMPT.md --completion-promise DONE --stop-when-goals-complete --goal <name|id>`
- `pms loop list --project <name|id> --include-ended --format table|json`
- `pms loop show <loop_id> --include-messages --format text|json`
- `pms loop messages <loop_id> --format text|json`
- `pms loop cancel <loop_id>`
- `pms loop guard --project <name|id> --goal-id <id> --hook --format json|text`

### Tasks

- Tip: task commands that accept `<task_id|title>` also accept `--pick` to interactively choose when titles are ambiguous (use with `--project`).
- `pms task list --view overview|detail|trace --include-history --include-linked --include-linked-history --history-limit <n> --linked-limit <n> --limit <n> --offset <n> --format table|json|csv`
- `pms task search --include-history --include-linked --include-linked-history --history-limit <n> --linked-limit <n> --format table|json|csv`
- `pms task duplicates --include-history --include-linked --include-linked-history --history-limit <n> --linked-limit <n> --format table|json|csv`
- `pms task add <project> <title> --parent-id <task_id> --format text|json` (or `pms task add --project <project> <title>`)
- `pms task create <project> <title> --parent-id <task_id> --format text|json` (or `pms task create --project <project> <title>`)
- `pms task merge-preview --format text|json`
- `pms task ready --include-history --include-linked --include-linked-history --history-limit <n> --linked-limit <n> --format table|json|csv`
- `pms task stale --include-history --include-linked --include-linked-history --history-limit <n> --linked-limit <n> --format table|json|csv`
- `pms task show <task_id|title> --project <name|id> --view overview|detail|trace --include-history --include-linked --include-linked-history --history-limit <n> --linked-limit <n> --format text|json|csv`
- `pms task resolve <task_id|title> --project <name|id> --format text|json`
- `pms task blocked --include-history --include-linked --include-linked-history --history-limit <n> --linked-limit <n> --format table|json|csv`
- `pms task available --include-history --include-linked --include-linked-history --history-limit <n> --linked-limit <n> --format table|json|csv`
- `pms task timeline <task_id|title> --project <name|id> --format table|json|csv`
- `pms task graph <task_id|title> --project <name|id> --format text|json|csv`
- `pms task tree --project <name|id> --root-task-id <id> --format text|json|csv`
- `pms task checkout-status --format table|json|csv`
- `pms task checkout-log --format table|json|csv`
- `pms task evidence list <task_id|title> --project <name|id> --view overview|detail|trace --include-test-runs --include-output --limit <n> --offset <n> --format table|json|csv`
- `pms task proof-bundle <task_id> --format text|json`
- `pms task proof-bundle-search --task-id <id> --plan-id <id> --status <status> --evidence-type <type> --created-from <iso> --created-to <iso> --include-evidence --include-test-runs --include-output --include-logs --include-artifacts --view overview|detail|trace --limit <n> --offset <n> --format table|json|csv`
- `pms task checkout <task_id|title> --project <name|id> --agent-id <id>`
- `pms task renew <task_id|title> --project <name|id> --agent-id <id>`
- `pms task release <task_id|title> --project <name|id> --agent-id <id>`
- `pms task force-release <task_id|title> --project <name|id>`
- `pms task progress <task_id|title> --project <name|id> <percent> <message> --by <id> --format text|json`
- `pms task start <task_id|title> --project <name|id> --format text|json`
- `pms task complete <task_id|title> --project <name|id> --format text|json`
- `pms task block <task_id|title> --project <name|id>`
- `pms task unblock <task_id|title> --project <name|id>`
- `pms task update <task_id|title> --project <name|id> --parent-id <task_id> --clear-parent`
- `pms task delete <task_id|title> --project <name|id>`
- `pms task evidence add <task_id|title> <type> <ref> --project <name|id>`

Task list JSON shape:

- Wrapper: `{ "items": [...], "page": {...}, "links": {...}, "next_steps": [...], "params": {...} }`
- Overview item fields: `id`, `title`, `status`, `priority`, `description`, `project_id`, `project_name`, `created_at`, `updated_at`, `due_date`, `completed_at`, `assignee`, `tags`, `labels`, `current_progress_percent`, `workflow_id`, `current_state`, `is_overdue`, `last_activity_at`, `last_transition_at`, `links`

Task ready/stale JSON shape:

- Top-level: array of task objects.
- Task object fields include standard task fields plus `project_name`, `last_activity_at`, `links`, and `next_steps`.
- `links` includes task actions (`self`, `timeline`, `graph`, `evidence`) and continuation anchors (`guide`, `dashboard`, plus command-specific list/query links).

Task blocked/available JSON shape:

- Top-level: array of task objects.
- Task object fields include task identity fields plus `project_name`, `last_activity_at`, `links`, and `next_steps`.
- `links` includes task actions (`self`, `timeline`, `graph`, `evidence`) and continuation anchors (`guide`, `dashboard`, plus command-specific query links).

Task duplicates JSON shape:

- Top-level: array of duplicate-group objects.
- Duplicate-group fields include `normalized_title`, `count`, `suggested_primary_id`, `suggested_primary_reason`, `last_activity_at`, `projects`, `tasks`, `links`, and `next_steps`.
- Each group `tasks` item includes standard task fields plus `project_name`, `last_activity_at`, `links`, and `next_steps`.

### Revisions

- `pms revision diff <entity_type> <entity_id> --from <rev> --to <rev> --format table|json|csv`
- `pms revision bundle <entity_type> <entity_id> --include-linked --include-linked-history --history-limit <n> --history-offset <n> --linked-limit <n> --linked-history-limit <n> --format table|json|csv`

### Queues

- `pms queue list --view overview|detail|trace --include-history --include-linked --include-linked-history --history-limit <n> --linked-limit <n> --limit <n> --offset <n> --format table|json|csv`
- `pms queue show <queue_id_or_name> --view overview|detail|trace --include-history --include-linked --include-linked-history --history-limit <n> --linked-limit <n> --format text|json|csv`
- `pms queue run <queue_id_or_name> --include-history --include-linked --include-linked-history --history-limit <n> --linked-limit <n> --format table|json|csv`
- `pms queue restore <queue_id_or_name>`
- `pms queue delete <queue_id_or_name>`
- `pms queue presets --view overview|detail|trace --limit <n> --stale-days <n> --at-risk-days <n> --format table|json|csv`

### Work Snapshots

- `pms work snapshot --view overview|detail|trace --include-history --history-limit <n> --format text|json`
- `pms work review --scope-type project --scope <name> --reviewed-by <id> --note <text> --metadata <json> --view overview|detail|trace --include-history --history-limit <n> --format text|json`
- `pms work daily --scope-type project --scope <name> --view overview|detail|trace --include-history --include-timeline --export <path> --attach-task <task_id> --attach-strategy auto|ready|recent --format text|json|csv`

Example: export + attach evidence

```
pms work daily --scope-type project --scope "My Project" \
  --format json --export ./reports --attach-strategy ready
```

Good practice:

- use `--export` by itself when you only need a file artifact
- use `--export` with `--attach-task` or `--attach-strategy` when the export
  should become authoritative task evidence
- the combined export+attach path is self-cleaning: if evidence attachment
  fails late, PMS removes the just-written export instead of leaving an orphan
  file behind

### Labels

- `pms label category list --view overview|detail|trace --include-history --history-limit <n> --limit <n> --offset <n> --format table|json|csv`
- `pms label category show <category_id_or_name> --view overview|detail|trace --include-history --include-linked --include-linked-history --history-limit <n> --linked-limit <n> --format text|json|csv`
- `pms label category restore <category_id>`
- `pms label list --view overview|detail|trace --include-history --history-limit <n> --limit <n> --offset <n> --format table|json|csv`
- `pms label show <label_id_or_name> --view overview|detail|trace --include-history --include-linked --history-limit <n> --format text|json|csv`
- `pms label restore <label_id>`
- `pms label list-entity <entity_type> <entity_id> --sort name|category|applied --order asc|desc --view overview|detail|trace --limit <n> --offset <n> --format table|json|csv`
- `pms label assignment history <assignment_id> --limit <n> --offset <n> --format table|json|csv`
- `pms label gate list --workflow-id <id> --from-state <state> --to-state <state> --entity-type <type> --view overview|detail|trace --include-history --history-limit <n> --limit <n> --offset <n> --format table|json|csv`
- `pms evidence gate list --workflow-id <id> --from-state <state> --to-state <state> --entity-type <type> --view overview|detail|trace --include-history --history-limit <n> --limit <n> --offset <n> --format table|json|csv`

### Projects

- `pms project list --view overview|detail|trace --include-history --include-linked --include-linked-history --history-limit <n> --linked-limit <n> --limit <n> --offset <n> --format table|json|csv`
- `pms project show "<name|id>" --view overview|detail|trace --include-history --include-linked --include-linked-history --history-limit <n> --linked-limit <n> --format text|json|csv`
- `pms project summary <project_id|name> --format text|json|csv`
- `pms project complete "<name>"`
- `pms project history "<name>" --format table|json|csv`

Project show JSON stats fields (when present): `total_tasks`, `completed_tasks`, `in_progress_tasks`, `blocked_tasks`, `total_milestones`, `completed_milestones`, `total_complexity_points`, `avg_complexity_per_task`, `total_duration_hours`, `avg_duration_per_task`, `avg_efficiency_score`, `overdue_tasks`, `total_goals`, `completed_goals`, `avg_goal_progress`, `completion_percent`, `complexity_velocity`, `health_score`.

### Products

- `pms product list --view overview|detail|trace --include-history --include-linked --include-linked-history --history-limit <n> --linked-limit <n> --limit <n> --offset <n> --format table|json|csv`
- `pms product show <product_id> --format text|json|csv`
- `pms product summary <product_id> --format text|json|csv`

### Organizations

- `pms org list --view overview|detail|trace --include-history --include-linked --include-linked-history --history-limit <n> --linked-limit <n> --limit <n> --offset <n> --format table|json|csv`
- `pms org show <org_id|name> --view overview|detail|trace --include-history --include-linked --include-linked-history --history-limit <n> --linked-limit <n> --format text|json|csv`
- `pms org summary <org_id|name> --format text|json|csv`
- `pms org dashboard --include-digest/--no-digest --include-next-actions/--no-next-actions --include-evidence/--no-evidence --include-retention/--no-retention --next-limit <n> --format table|json|csv`

### Teams

- `pms team list --view overview|detail|trace --include-history --include-linked --include-linked-history --history-limit <n> --linked-limit <n> --limit <n> --offset <n> --format table|json|csv`
- `pms team show <team_id|name> --view overview|detail|trace --include-history --include-linked --include-linked-history --history-limit <n> --format text|json|csv`

### Portfolios

- `pms portfolio list --org <name|id> --org-id <id> --view overview|detail|trace --include-history --include-linked --include-linked-history --history-limit <n> --linked-limit <n> --limit <n> --offset <n> --format table|json|csv`
- `pms portfolio show <portfolio_id|name> --view overview|detail|trace --include-history --include-linked --include-linked-history --history-limit <n> --linked-limit <n> --format text|json|csv`
- `pms portfolio summary <portfolio_id|name> --format text|json|csv`
- `pms portfolio dashboard --org <name|id> --org-id <id> --include-digest/--no-digest --include-next-actions/--no-next-actions --include-evidence/--no-evidence --include-retention/--no-retention --next-limit <n> --format table|json|csv`

### Programs

- `pms program list --org <name|id> --org-id <id> --portfolio <name|id> --portfolio-id <id> --view overview|detail|trace --include-history --include-linked --include-linked-history --history-limit <n> --linked-limit <n> --limit <n> --offset <n> --format table|json|csv`
- `pms program show <program_id|name> --view overview|detail|trace --include-history --include-linked --include-linked-history --history-limit <n> --linked-limit <n> --format text|json|csv`
- `pms program summary <program_id|name> --format text|json|csv`
- `pms program dashboard --org <name|id> --org-id <id> --portfolio <name|id> --portfolio-id <id> --include-digest/--no-digest --include-next-actions/--no-next-actions --include-evidence/--no-evidence --include-retention/--no-retention --next-limit <n> --format table|json|csv`

### Goals/OKRs

- Tip: goal/objective/keyresult commands that accept `<name|id>` also accept `--pick` to disambiguate.
- `pms goal list --view overview|detail|trace --include-history --include-linked --include-linked-history --history-limit <n> --linked-limit <n> --limit <n> --offset <n> --format table|json|csv`
- `pms goal show <goal_id|name> --view overview|detail|trace --include-history --include-linked --include-linked-history --history-limit <n> --linked-limit <n> --format text|json|csv`
- `pms goal summary <goal_id|name> --format text|json|csv`
- `pms objective list --goal <name|id> --goal-id <id> --view overview|detail|trace --include-history --include-linked --include-linked-history --history-limit <n> --linked-limit <n> --limit <n> --offset <n> --format table|json|csv`
- `pms objective show <objective_id|name> --goal <name|id> --view overview|detail|trace --include-history --include-linked --include-linked-history --history-limit <n> --linked-limit <n> --format text|json|csv`
- `pms keyresult list --objective <name|id> --objective-id <id> --goal <name|id> --view overview|detail|trace --include-history --include-linked --include-linked-history --history-limit <n> --linked-limit <n> --limit <n> --offset <n> --format table|json|csv`
- `pms keyresult show <key_result_id|name> --objective <name|id> --goal <name|id> --view overview|detail|trace --include-history --include-linked --include-linked-history --history-limit <n> --format text|json|csv`

### Plans

- Tip: plan name filters accept `--pick` for ambiguous names (especially with `--project`).
- `pms plan list --project <name|id> --product <name|id> --goal <name|id> --objective <name|id> --view overview|detail|trace --include-history --include-linked --include-linked-history --history-limit <n> --linked-limit <n> --limit <n> --offset <n> --format table|json|csv`
- `pms plan lineage --project <name|id> --project-id <id> --plan <name|id> --plan-id <id> --format table|json|csv`
- `pms plan show <plan_id|name> --project <name|id> --view overview|detail|trace --include-history --include-linked --include-linked-history --history-limit <n> --linked-limit <n> --format text|json`
- `pms plan test-job list <plan_id> --view overview|detail|trace --include-history --include-linked --include-linked-history --history-limit <n> --linked-limit <n> --limit <n> --offset <n> --format table|json|csv`
- `pms plan test-job show <job_id> --view overview|detail|trace --include-history --include-linked --include-linked-history --history-limit <n> --linked-limit <n> --format text|json`
- `pms plan test-job restore <job_id>`
- `pms plan test-job run <job_id> [or <plan_id> <job_id>]`

### Workflows

- `pms workflow list --view overview|detail|trace --limit <n> --offset <n> --format table|json|csv`
- `pms workflow show <workflow_key|id> --view overview|detail|trace --format text|json`

### Transitions

- `pms timeline workflow <entity_type> <entity_id> --by <actor> --from-state <state> --to-state <state> --since <iso> --until <iso> --type workflow|status --label <label> --format table|json|csv`
- `pms timeline status <entity_type> <entity_id> --by <actor> --from-state <state> --to-state <state> --since <iso> --until <iso> --type workflow|status --label <label> --format table|json|csv`

### Remote/AWS

- `pms remote list --view overview|detail|trace --limit <n> --offset <n> --format table|json|csv`
- `pms remote show <name> --view overview|detail|trace --format text|json|csv`
- `pms aws spot find --format table|json|csv`
- `pms aws server list --view overview|detail|trace --limit <n> --offset <n> --format table|json|csv`
- `pms aws server show <name_or_id> --view overview|detail|trace --format text|json|csv`

### Tests

- `pms test run <project_path>`
- `pms test record --server-id <id> --status passed|failed --started-at <iso> --finished-at <iso> --project-id <id> --plan-id <id> --task-id <id>`
- `pms test list --view overview|detail|trace --include-output --include-logs --include-artifacts --limit <n> --offset <n> --format table|json|csv`
- `pms test show <run_id> --view overview|detail|trace --include-output --include-logs --include-artifacts --format text|json|csv`
- `pms test prune --max-log-bytes <n> --max-artifact-bytes <n> --max-age-days <n> --project-id <id> --org-id <id> --ignore-policies --dry-run --format text|json|csv`
- `pms test retention --project <name> --project-id <id> --org-id <id> --format table|json|csv`
- `pms test retention-policy set <project|organization> <scope_id> --max-log-bytes <n> --max-artifact-bytes <n> --max-age-days <n> --notes <text> --format text|json|csv`
- `pms test retention-policy list --scope-type <project|organization> --scope-id <id> --include-archived --limit <n> --offset <n> --format table|json|csv`
- `pms test retention-policy show <policy_id> --format text|json|csv`
- `pms test retention-policy update <policy_id> --max-log-bytes <n> --max-artifact-bytes <n> --max-age-days <n> --notes <text> --format text|json|csv`
- `pms test retention-policy archive <policy_id>`
- `pms test retention-policy restore <policy_id>`

### Auth/Introspection

- `pms auth list --view overview|detail|trace --include-history --history-limit <n> --limit <n> --offset <n> --format table|json|csv`
- `pms auth get <key_id> --format text|json|csv`
- `pms auth scopes --format text|json|csv`
- `pms auth restore <key_id>`
- `pms capabilities info --format table|json|csv`
- `pms capabilities list --view overview|detail|trace --limit <n> --offset <n> --format table|json|csv`
- `pms capabilities health --format table|json|csv`
- `pms namespace list --view overview|detail|trace --limit <n> --offset <n> --format table|json|csv`
- `pms namespace show <prefix> --view overview|detail|trace --format text|json|csv`
- `pms plugin list --view overview|detail|trace --limit <n> --offset <n> --format table|json|csv`
- `pms plugin show <name> --view overview|detail|trace --format text|json|csv`
- `pms plugin tools --plugin <name> --name <substring> --capability <cap> --sort name|plugin|discovered --order asc|desc --view overview|detail|trace --limit <n> --offset <n> --format table|json|csv`
- `pms plugin stats --view overview|detail|trace --format text|json|csv`

Namespace list/show JSON items and CSV rows now include the shared namespace
ID-contract fields:

- `namespace_generated_id_format`
  - prefix-based format generated by the namespace registry, such as `proj_<uuid>`
- `namespace_generated_id_kind`
  - namespace-generated ID family, currently `prefix_uuid`
- `runtime_row_id_contract_scope`
  - whether the namespace participates in the public stored-entity runtime row-ID contract
  - current values:
    - `public_stored_entity_family`
    - `internal_or_non_public_namespace`
- `runtime_row_id_style`
  - public runtime row-ID style when the namespace participates in that contract
  - current values:
    - `uuid_native`
    - `prefix_native`
  - JSON emits `null` and CSV emits an empty field when no public runtime row-ID
    contract applies for that namespace family

### Dashboard

- `pms dashboard --format table|json|csv`
