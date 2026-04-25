# Interactive Plan Builder Prompt (Agent Intake)

Use this file as the starting prompt for an AI agent. The agent must build a
complete PMS project plan interactively, store every detail in PMS, and then
handoff to a loop run that works until goals are complete.

Core rules:

- PMS is the only source of truth. Every idea becomes a goal, objective,
  key result, plan entry, task, dependency, workflow transition, or evidence.
- Use `uv run pms` for all commands. Prefer `--format json` for listings.
- If names are ambiguous, list and pick or use `--pick`.
- Acceptance criteria are modeled as key results and also stored in plan
  content. Tasks map to acceptance criteria.
- Do not modify local agent settings. If hooks are needed, explain them and
  let the user apply them.

Related templates:

- `docs/AGENT_PROMPT_MINIMAL.md` for a short intake flow.
- `docs/AGENT_PROMPT_MCP_LOOP.md` for MCP-only agents.

---

## Phase 0 - Scope and constraints (ask first)

Ask the user for:

- Org, product, project names
- Goal(s), horizon (short_term, medium_term, long_term)
- Definition of done and acceptance criteria
- Risks, constraints, target dates, owners
- Required artifacts or tests

Capture the answers, then create PMS entities.

---

## Phase 1 - Create org, product, project

Commands (examples):

```bash
uv run pms org list --format json
uv run pms org create "Acme Org"

uv run pms product list --format json
uv run pms product create "Resume Hosting"

uv run pms project list --format json
uv run pms project create "Resume Hosting Site" --product "Resume Hosting"
```

---

## Phase 2 - Create goal, objective, acceptance criteria (key results)

Create a goal, then an objective for acceptance criteria, then one key result
per criterion.

```bash
uv run pms goal create "Launch resume hosting MVP" \
  --project "Resume Hosting Site" \
  --horizon short_term

uv run pms objective create "MVP acceptance criteria" \
  --goal "Launch resume hosting MVP"

uv run pms keyresult create "Landing page + upload flow" \
  --objective "MVP acceptance criteria" \
  --goal "Launch resume hosting MVP"
```

Repeat key results for every acceptance criterion.

---

## Phase 3 - Create the plan (acceptance criteria + task map)

Create a plan file that includes acceptance criteria and a task map. Use YAML
or JSON. If you can write files, create `plan.yml`. Otherwise output the
contents and ask the user to save it.

Example `plan.yml` (fill ids after you create key results and tasks):

```yaml
acceptance_criteria:
  - id: ac-1
    description: Landing page + upload flow
    key_result: "<key_result_id>"
  - id: ac-2
    description: Upload API stub works locally
    key_result: "<key_result_id>"
task_map: []
```

Create the plan in PMS:

```bash
uv run pms plan create "Resume Hosting MVP Plan" \
  --project "Resume Hosting Site" \
  --goal "Launch resume hosting MVP" \
  --objective "MVP acceptance criteria" \
  --format yaml \
  --file plan.yml
```

---

## Phase 4 - Create tasks and the dependency graph

For each task:

- Provide a short title and a clear description.
- Tag horizon or intent (`short_term`, `medium_term`, `long_term`, `future`).
- Map the task to one or more acceptance criteria.
- Add dependencies where ordering matters.

```bash
uv run pms task create "Resume Hosting Site" "Define UX and requirements" \
  --description "Draft user flow, copy, and constraints" \
  --tag short_term

uv run pms task create "Resume Hosting Site" "Add upload + storage stub API" \
  --description "Local storage API stub for uploads" \
  --tag short_term

uv run pms task list --project "Resume Hosting Site" --format json
uv run pms task dep add <task_id_api> <task_id_ux> --type blocks
```

Update the plan with task links:

```bash
uv run pms plan update "Resume Hosting MVP Plan" \
  --project "Resume Hosting Site" \
  --task "Define UX and requirements" \
  --task "Add upload + storage stub API"
```

Update `plan.yml` to include a task map and re-apply:

```yaml
task_map:
  - task: "Define UX and requirements"
    acceptance_criteria: ["ac-1"]
    horizon: short_term
  - task: "Add upload + storage stub API"
    acceptance_criteria: ["ac-2"]
    horizon: short_term
    notes: "Blocked by requirements"
```

```bash
uv run pms plan update "Resume Hosting MVP Plan" \
  --project "Resume Hosting Site" \
  --format yaml \
  --file plan.yml
```

---

## Phase 5 - Workflow, evidence, and test pipelines

Assign workflows and add evidence gates when required.

```bash
uv run pms workflow list --format json
uv run pms workflow assign <task_id> sdlc concept --entity-type task
```

Example evidence gate (require a test run before testing -> staging):

```bash
uv run pms evidence gate add \
  --workflow-id <workflow_id> \
  --entity-type task \
  --from-state integration_testing \
  --to-state staging \
  --evidence-type test_run \
  --min-count 1 \
  --require-success
```

Optional: define plan-linked test jobs:

```bash
uv run pms plan test-job add <plan_id> "Unit tests" . \
  --command "pytest" \
  --project-id <project_id>
```

---

## Phase 6 - Validate the plan state

Confirm everything is connected:

```bash
uv run pms goal summary "Launch resume hosting MVP"
uv run pms objective list --goal "Launch resume hosting MVP" --format json
uv run pms keyresult list --objective "MVP acceptance criteria" --goal "Launch resume hosting MVP" --format json
uv run pms plan show "Resume Hosting MVP Plan" --project "Resume Hosting Site" --format json
uv run pms task list --project "Resume Hosting Site" --view detail
uv run pms task graph <task_id> --project "Resume Hosting Site"
```

If anything is missing, add it now and update plan content.

---

## Phase 6.5 - Baseline snapshot (optional but recommended)

Capture a baseline snapshot and review checkpoint so future progress is
measured in relative time with a clear audit trail.

```bash
uv run pms work snapshot --scope-type project --scope "Resume Hosting Site" \
  --format json

uv run pms work review --scope-type project --scope "Resume Hosting Site" \
  --reviewed-by plan-agent \
  --note "Baseline snapshot before execution"
```

---

## Phase 7 - Generate loop files and handoff

Generate loop config + prompt files, then fill them with the plan you just
created. Do not start the loop until the prompt file is complete.

```bash
uv run pms loop init --config pms-loop.yml --prompt-file PROMPT.md
```

Write `PROMPT.md` using the template below (fill in the real names/ids). If you
can write files, do so. Otherwise output the contents for the user to save.

```
# Project
<Project name> (product: <Product name>)

# Goal
<Goal name>.

# Acceptance Criteria
Tracked as key results under "<Objective name>" and recorded in the plan
"<Plan name>". Keep both updated as work completes.

# Loop Rules
1) Read PMS state first:
   - `uv run pms product show "<Product name>"`
   - `uv run pms project show "<Project name>"`
   - `uv run pms goal list --project "<Project name>"`
   - `uv run pms objective list --goal "<Goal name>"`
   - `uv run pms keyresult list --objective "<Objective name>" --goal "<Goal name>"`
   - `uv run pms plan show "<Plan name>" --project "<Project name>"`
   - `uv run pms task list --project "<Project name>"`
2) Assign workflow for tasks without one:
   - `uv run pms workflow assign <task_id> sdlc concept --entity-type task`
3) Check out the task before work:
   - `uv run pms task checkout <task_id> --project "<Project name>" --agent-id loop-agent`
4) Update task status and progress:
   - `uv run pms task start <task_id> --project "<Project name>"`
   - `uv run pms task progress <task_id> --project "<Project name>" <percent> <message> --by loop-agent`
   - `uv run pms task complete <task_id> --project "<Project name>"`
5) Transition workflow states as you advance:
   - `uv run pms workflow transition <task_id> idea --by loop-agent`
   - `uv run pms workflow transition <task_id> planning --by loop-agent`
   - `uv run pms workflow transition <task_id> implementing --by loop-agent`
   - `uv run pms workflow transition <task_id> integration_testing --by loop-agent`
   - `uv run pms workflow transition <task_id> production --by loop-agent --approved-by lead`
6) Attach evidence for every task:
   - `uv run pms task evidence add <task_id> artifact <path> --project "<Project name>"`
   - For tests: `uv run pms test run .` then
     `uv run pms task evidence add <task_id> test_run <run_id> --project "<Project name>"`
7) Update key results and objective progress:
   - `uv run pms keyresult update <keyresult_id> --goal "<Goal name>" --progress <percent>`
   - `uv run pms objective update "<Objective name>" --goal "<Goal name>" --progress <percent>`
8) Use `uv run pms goal summary "<Goal name>"` each loop to confirm rollups.
9) When all criteria are complete, finish the goal:
   - `uv run pms goal complete "<Goal name>"`
10) When the goal is complete, output <promise>DONE</promise>.
```

Fill `pms-loop.yml`:

```yaml
agent: claude
prompt_file: PROMPT.md
completion_promise: DONE
stop_when_goals_complete: true
goal_ids:
  - <goal_id>
```

Finally, output the loop command for the user:

```bash
uv run pms loop run --config pms-loop.yml
```

If you need to continue later, always resume by reading PMS state first.
