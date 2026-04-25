# End-to-End Project Modeling in PMS

This guide explains how to represent an entire development effort from inception
through completion using PMS structures, workflow state machines, and graph task
tracking. It also provides a realistic, end-to-end example.

If you are approaching PMS as an agent or machine integration, read
[`docs/MACHINE_INTERFACE_GUIDE.md`](MACHINE_INTERFACE_GUIDE.md) first. Then use
this guide to see how those machine-readable surfaces behave across larger,
realistic workflows.

## How PMS Represents Work

- Product: long-lived product entity (vision, owner, metadata).
- Project: execution container under a product (scope, timeline, tasks).
- Goal: outcome you are trying to achieve (horizon, progress rollup).
- Objective: measurable objective under a goal.
- Key Result: acceptance criteria tracked as measurable outcomes.
- Plan: structured plan content that links goals/objectives to tasks.
- Task: units of work (status + workflow states + progress updates).
- Evidence: proof attached to tasks (artifacts, test runs, manual notes).
- Workflow: state machine per entity (task/goal/objective) with transitions.
- Graph: task dependencies for blocking/ordering and graph inspection.

Important: PMS does not have a dedicated "acceptance criteria" entity. The
practical pattern is to represent acceptance criteria as Objective + Key Results
and to store the detailed criteria in a Plan that links to the tasks.

## How to Read This Guide (Feature Interaction Map)

This guide is structured to show how features cross-interact in a single
workflow, then repeats the pattern in multiple contexts (CLI, MCP, API).

Core interaction chain:

- Structure layer: product -> project -> goal -> objective -> key results -> plan.
- Execution layer: tasks with status + workflow transitions + dependencies.
- Proof layer: evidence (notes/artifacts/test runs) + proof bundles.
- Temporal layer: progress updates, status/workflow transitions, revisions.
- Visibility layer: queues, work snapshots, dashboards, reports.
- Automation layer: agent loops (CLI, MCP, API) that read/act/update continuously.

Where to find complete examples:

- "Full Example: Resume Hosting Site" shows the entire flow in CLI form.
- "Running the Same Flow with Loops" shows agent-driven execution.
- "API-First Walkthrough" shows the same flow via HTTP endpoints.
- "MCP Tool Usage" + "MCP Agent Loop Prompt" show tool call structure.
- "Cross-Project Dependencies + Rollups" shows program/portfolio rollups.

## Core Concepts and Commands

### 1) Acceptance Criteria = Objective + Key Results

Create a goal, then an objective named for acceptance criteria. Each criterion
becomes a key result. Update key results as work completes.

```bash
uv run pms goal create "Launch resume hosting MVP" \
  --project "Resume Hosting Site" \
  --horizon short_term \
  -d "Deliver a working resume hosting MVP"

uv run pms objective create "MVP acceptance criteria" \
  --goal "Launch resume hosting MVP" \
  -d "Acceptance criteria tracked as key results"

uv run pms keyresult create "Landing page + upload flow" \
  --objective "MVP acceptance criteria" --goal "Launch resume hosting MVP"
```

### 2) Plan = Structured Criteria + Task Links

Plans hold structured acceptance criteria and link tasks to the goal/objective.

```bash
cat > plan.yml <<'EOF'
acceptance_criteria:
  - id: ac-1
    description: Public landing page with resume preview + upload flow
  - id: ac-2
    description: Upload API stub wired to local storage
  - id: ac-3
    description: README with run instructions + architecture notes
  - id: ac-4
    description: Every task has evidence attached
  - id: ac-5
    description: Tests (or smoke checks) are recorded as evidence
EOF

uv run pms plan create "Resume Hosting MVP Plan" \
  --project "Resume Hosting Site" \
  --goal "Launch resume hosting MVP" \
  --objective "MVP acceptance criteria" \
  --format yaml \
  --file plan.yml
```

### 3) Tasks = Execution Units + Workflow + Evidence

Tasks are the execution layer. Track progress, use workflows, and attach evidence.

```bash
uv run pms task create "Resume Hosting Site" "Define UX and requirements"
uv run pms task start "Define UX and requirements" --project "Resume Hosting Site"
uv run pms task progress "Define UX and requirements" --project "Resume Hosting Site" \
  50 "Drafted requirements" --by loop-agent
uv run pms task complete "Define UX and requirements" --project "Resume Hosting Site"
uv run pms task evidence add "Define UX and requirements" artifact docs/requirements.md \
  --project "Resume Hosting Site"
```

Link tasks to the plan (this is the canonical way to attach tasks to goals):

```bash
uv run pms plan update "Resume Hosting MVP Plan" \
  --project "Resume Hosting Site" \
  --task "Define UX and requirements"
```

### 4) Workflow State Machines

PMS ships with built-in workflows (sdlc, agile, product_lifecycle). Assign a
workflow to tasks/goals/objectives, then transition states explicitly.

```bash
uv run pms workflow list
uv run pms workflow show sdlc

uv run pms workflow assign <task_id> sdlc concept --entity-type task
uv run pms workflow transition <task_id> implementing --by loop-agent
```

You can align workflow state to entity status:

```bash
uv run pms workflow align <task_id> --by loop-agent --entity-type task
```

### 5) Task Graph Dependencies

Use dependencies to enforce ordering, then inspect the graph.

```bash
uv run pms task dep add <task_id> <depends_on_id> --type blocks
uv run pms task graph <task_id> --project "Resume Hosting Site"
```

### 6) Evidence, Tests, and Proof Bundles

Evidence is mandatory for high-integrity workflows. Attach test runs or manual
artifact references.

```bash
uv run pms test run .
uv run pms task evidence add <task_id> test_run <run_id> \
  --project "Resume Hosting Site"

uv run pms task proof-bundle <task_id>
```

### 7) Goal Validation and Completion

Update key results and objective progress as acceptance criteria are met, then
complete the goal when all criteria are satisfied.

```bash
uv run pms keyresult update "Landing page + upload flow" \
  --goal "Launch resume hosting MVP" --progress 100

uv run pms objective update "MVP acceptance criteria" \
  --goal "Launch resume hosting MVP" --progress 100

uv run pms goal complete "Launch resume hosting MVP"
```

---

## Full Example: Resume Hosting Site (End-to-End)

### A) Setup

```bash
uv run pms init --reset --force

uv run pms product create "Resume Hosting" \
  -v "Host resumes with simple uploads and sharable pages"

uv run pms project create "Resume Hosting Site" --product "Resume Hosting" \
  -d "Static resume site with upload and hosting workflow"
```

### B) Acceptance Criteria (Objective + Key Results)

```bash
uv run pms goal create "Launch resume hosting MVP" \
  --project "Resume Hosting Site" \
  --horizon short_term \
  -d "Deliver a working site with upload, hosting, admin review"

uv run pms objective create "MVP acceptance criteria" \
  --goal "Launch resume hosting MVP" \
  -d "Acceptance criteria tracked as key results"

uv run pms keyresult create "Landing page + upload flow" \
  --objective "MVP acceptance criteria" --goal "Launch resume hosting MVP"
uv run pms keyresult create "Upload API stub works locally" \
  --objective "MVP acceptance criteria" --goal "Launch resume hosting MVP"
uv run pms keyresult create "README + run instructions complete" \
  --objective "MVP acceptance criteria" --goal "Launch resume hosting MVP"
uv run pms keyresult create "Evidence captured for all tasks" \
  --objective "MVP acceptance criteria" --goal "Launch resume hosting MVP"
```

### C) Plan and Tasks

```bash
cat > plan.yml <<'EOF'
acceptance_criteria:
  - id: ac-1
    description: Public landing page with resume preview + upload flow
  - id: ac-2
    description: Upload API stub wired to local storage
  - id: ac-3
    description: README with run instructions + architecture notes
  - id: ac-4
    description: Every task has evidence attached
  - id: ac-5
    description: Tests (or smoke checks) are recorded as evidence
EOF

uv run pms plan create "Resume Hosting MVP Plan" \
  --project "Resume Hosting Site" \
  --goal "Launch resume hosting MVP" \
  --objective "MVP acceptance criteria" \
  --format yaml \
  --file plan.yml

uv run pms task create "Resume Hosting Site" "Define UX and requirements"
uv run pms task create "Resume Hosting Site" "Write information architecture + page flow"
uv run pms task create "Resume Hosting Site" "Draft wireframes and copy"
uv run pms task create "Resume Hosting Site" "Implement static site skeleton"
uv run pms task create "Resume Hosting Site" "Build resume upload form (client)"
uv run pms task create "Resume Hosting Site" "Add upload + storage stub API"
uv run pms task create "Resume Hosting Site" "Create resume preview page"
uv run pms task create "Resume Hosting Site" "Add basic admin review page"
uv run pms task create "Resume Hosting Site" "Write README and run instructions"
uv run pms task create "Resume Hosting Site" "Run tests / smoke checks and capture evidence"

uv run pms plan update "Resume Hosting MVP Plan" \
  --project "Resume Hosting Site" \
  --task "Define UX and requirements" \
  --task "Write information architecture + page flow" \
  --task "Draft wireframes and copy" \
  --task "Implement static site skeleton" \
  --task "Build resume upload form (client)" \
  --task "Add upload + storage stub API" \
  --task "Create resume preview page" \
  --task "Add basic admin review page" \
  --task "Write README and run instructions" \
  --task "Run tests / smoke checks and capture evidence"
```

### D) Dependency Graph + Workflow Assignment

Map the task graph and assign workflows up front. Use IDs from `task list` when
adding dependencies.

```bash
uv run pms task list --project "Resume Hosting Site" --format json

# Example dependency wiring (replace with real task IDs):
uv run pms task dep add <task_id_upload_form> <task_id_site_skeleton> --type blocks
uv run pms task dep add <task_id_preview_page> <task_id_upload_form> --type blocks
uv run pms task dep add <task_id_admin_review> <task_id_preview_page> --type blocks

uv run pms task graph <task_id_preview_page> --project "Resume Hosting Site"
```

Assign SDLC workflow to the tasks you will execute:

```bash
uv run pms workflow list
uv run pms workflow assign <task_id_site_skeleton> sdlc concept --entity-type task
uv run pms workflow assign <task_id_upload_form> sdlc concept --entity-type task
uv run pms workflow assign <task_id_preview_page> sdlc concept --entity-type task
```

Optional: add evidence gates to enforce proof before workflow transitions.

```bash
uv run pms evidence gate add \
  --workflow-id wf_sdlc \
  --from-state idea \
  --to-state planning \
  --evidence-type note \
  --min-count 1 \
  --message "Add a planning note before moving to planning"
```

### E) Execution + Evidence (Workflow + Status + Proof)

```bash
uv run pms task start "Implement static site skeleton" --project "Resume Hosting Site"
uv run pms task progress "Implement static site skeleton" --project "Resume Hosting Site" \
  70 "Scaffolded layout and styles" --by loop-agent
uv run pms task review "Implement static site skeleton" --project "Resume Hosting Site" \
  --by loop-agent
uv run pms workflow transition <task_id_site_skeleton> idea --by loop-agent
uv run pms workflow transition <task_id_site_skeleton> planning --by loop-agent
uv run pms workflow transition <task_id_site_skeleton> detailed_plan --by loop-agent
uv run pms workflow transition <task_id_site_skeleton> implementing --by loop-agent
uv run pms task complete "Implement static site skeleton" --project "Resume Hosting Site"
uv run pms workflow transition <task_id_site_skeleton> unit_testing --by loop-agent
uv run pms workflow transition <task_id_site_skeleton> integration_testing --by loop-agent
uv run pms workflow transition <task_id_site_skeleton> staging --by loop-agent
uv run pms workflow transition <task_id_site_skeleton> confirmation --by loop-agent
uv run pms workflow transition <task_id_site_skeleton> production --by loop-agent --approved-by lead
uv run pms task evidence add "Implement static site skeleton" artifact src/index.html \
  --project "Resume Hosting Site"

uv run pms test run .
uv run pms task evidence add "Run tests / smoke checks and capture evidence" \
  test_run <run_id> --project "Resume Hosting Site"
```

### F) Validation and Completion

```bash
uv run pms keyresult update "Landing page + upload flow" \
  --goal "Launch resume hosting MVP" --progress 100
uv run pms keyresult update "Upload API stub works locally" \
  --goal "Launch resume hosting MVP" --progress 100
uv run pms keyresult update "README + run instructions complete" \
  --goal "Launch resume hosting MVP" --progress 100
uv run pms keyresult update "Evidence captured for all tasks" \
  --goal "Launch resume hosting MVP" --progress 100

uv run pms goal complete "Launch resume hosting MVP"
```

### G) Reporting

```bash
uv run pms goal summary "Launch resume hosting MVP"
uv run pms project summary "Resume Hosting Site"
uv run pms task list --project "Resume Hosting Site"
uv run pms task proof-bundle <task_id>
```

### H) JSON + History Exports (Full Audit Trail)

Use JSON outputs with history flags to capture full change and evidence trails.

```bash
uv run pms task show "Implement static site skeleton" \
  --project "Resume Hosting Site" \
  --format json \
  --include-history \
  --include-linked-history \
  --history-limit 50

uv run pms project show "Resume Hosting Site" \
  --format json \
  --include-history \
  --include-linked-history

uv run pms project history "Resume Hosting Site" --format json --limit 50

uv run pms work snapshot \
  --scope-type project \
  --scope "Resume Hosting Site" \
  --format json \
  --include-history

uv run pms evidence gate list \
  --workflow-id wf_sdlc \
  --from-state idea \
  --to-state planning \
  --format json \
  --include-history
```

---

## Extreme Feature Combination: Multi-Horizon Roadmap + Temporal Tracking

This section demonstrates how to combine horizons, workflows, labels, evidence,
tests, and time-series reporting into a single operating loop that keeps short,
medium, and long term work aligned.

### 1) Create the scope (org/portfolio/program/product/project)

```bash
uv run pms org create "Atlas"
uv run pms portfolio create "Platform Portfolio" --org "Atlas"
uv run pms program create "Platform Program" --org "Atlas" --portfolio "Platform Portfolio"

uv run pms product create "Distributed Platform" \
  -v "End-to-end project execution with evidence and timelines"
uv run pms project create "Platform Core" --product "Distributed Platform" \
  --org "Atlas" --portfolio "Platform Portfolio" --program "Platform Program"
```

### 2) Multi-horizon goals (short/medium/long)

```bash
uv run pms goal create "Ship MVP stability pass" \
  --project "Platform Core" --horizon short_term
uv run pms goal create "Scale to 10x usage" \
  --project "Platform Core" --horizon medium_term
uv run pms goal create "Platform expansion roadmap" \
  --project "Platform Core" --horizon long_term

uv run pms goal list --project "Platform Core" --horizon short_term
uv run pms goal list --project "Platform Core" --horizon medium_term
uv run pms goal list --project "Platform Core" --horizon long_term

uv run pms objective create "MVP acceptance criteria" \
  --goal "Ship MVP stability pass"
uv run pms keyresult create "Critical bugs fixed" \
  --objective "MVP acceptance criteria" --goal "Ship MVP stability pass"
uv run pms keyresult create "Core workflows documented" \
  --objective "MVP acceptance criteria" --goal "Ship MVP stability pass"

uv run pms objective create "Scale acceptance criteria" \
  --goal "Scale to 10x usage"
uv run pms keyresult create "Perf baseline captured" \
  --objective "Scale acceptance criteria" --goal "Scale to 10x usage"
```

### 3) A single plan ties horizons to tasks

```bash
cat > roadmap-plan.yml <<'EOF'
horizons:
  short_term:
    - Fix critical bugs and stabilize core workflow
    - Add evidence and test reporting
  medium_term:
    - Performance baselines, load tests, retention budgets
  long_term:
    - Expand automation and multi-agent governance
EOF

uv run pms plan create "Platform Roadmap Plan" \
  --project "Platform Core" \
  --goal "Ship MVP stability pass" \
  --objective "MVP acceptance criteria" \
  --format yaml \
  --file roadmap-plan.yml
```

### 4) Tasks + dependencies (short -> medium -> long)

```bash
uv run pms task create "Platform Core" "Fix workflow transition edge cases"
uv run pms task create "Platform Core" "Add evidence gate policies"
uv run pms task create "Platform Core" "Capture performance baseline"
uv run pms task create "Platform Core" "Automate multi-agent regression checks"

uv run pms task list --project "Platform Core" --format json

uv run pms plan update "Platform Roadmap Plan" --project "Platform Core" \
  --task "Fix workflow transition edge cases" \
  --task "Add evidence gate policies" \
  --task "Capture performance baseline" \
  --task "Automate multi-agent regression checks"

# Short-term tasks block medium-term work
uv run pms task dep add <task_id_perf_baseline> <task_id_fix_workflows> --type blocks
uv run pms task dep add <task_id_regression> <task_id_perf_baseline> --type blocks
```

### 5) Label taxonomy + label gates (workflow safety)

```bash
uv run pms label category create "horizon" --exclusive
uv run pms label create "now" --category "horizon"
uv run pms label create "next" --category "horizon"
uv run pms label create "later" --category "horizon"

uv run pms label category list --format json

uv run pms label assign task <task_id_fix_workflows> now --by lead
uv run pms label assign task <task_id_perf_baseline> next --by lead
uv run pms label assign task <task_id_regression> later --by lead

# Require a horizon label before leaving idea -> planning
uv run pms label gate add \
  --workflow-id wf_sdlc \
  --from-state idea \
  --to-state planning \
  --rule-type require_category \
  --category-id <horizon_category_id> \
  --message "Assign a horizon label before planning"
```

### 6) Evidence gates + workflow transitions

```bash
uv run pms evidence gate add \
  --workflow-id wf_sdlc \
  --from-state idea \
  --to-state planning \
  --evidence-type note \
  --min-count 1 \
  --message "Add a planning note before moving to planning"

uv run pms workflow assign <task_id_fix_workflows> sdlc concept --entity-type task
uv run pms workflow transition <task_id_fix_workflows> idea --by agent-a
uv run pms task evidence add <task_id_fix_workflows> note planning-note \
  --description "Planned fixes and test approach"
uv run pms workflow transition <task_id_fix_workflows> planning --by agent-a
```

### 7) Execution, testing, and proof

```bash
uv run pms task start <task_id_fix_workflows> --project "Platform Core"
uv run pms task progress <task_id_fix_workflows> --project "Platform Core" \
  60 "Edge case transitions patched" --by agent-a
uv run pms test run .
uv run pms task evidence add <task_id_fix_workflows> test_run <run_id> \
  --project "Platform Core"
uv run pms task complete <task_id_fix_workflows> --project "Platform Core"
uv run pms task proof-bundle <task_id_fix_workflows>
```

This is also the pattern PMS uses on itself. When evolving the framework, split
the work into separate tasks for audit, normalization, docs, and validation
instead of doing one long untracked refactor pass.

### 8) Temporal reporting + status memory

```bash
uv run pms queue presets --project "Platform Core"
uv run pms work snapshot --scope-type project --scope "Platform Core" --format json
uv run pms work daily --scope-type project --scope "Platform Core" \
  --include-timeline --export reports/daily.json --attach-task <task_id_fix_workflows>

uv run pms task show <task_id_fix_workflows> --format json \
  --include-history --include-linked-history
```

### 9) Rollups and completion checks

```bash
uv run pms project summary "Platform Core"
uv run pms goal summary "Ship MVP stability pass"
uv run pms program dashboard --org "Atlas" --portfolio "Platform Portfolio"
uv run pms portfolio dashboard --org "Atlas"
```

When the short-term goal is complete, update key results and mark the goal done.
Then repeat the same workflow for medium and long term goals to maintain
continuity across horizons.

---

## Extreme Feature Combination: Distributed Multi-Agent Execution + Proof and Retention

This scenario shows how multiple agents coordinate execution, track evidence,
preserve revisions, and enforce retention budgets while driving short, medium,
and long term goals to completion.

### 1) Scope: org -> portfolio -> program -> product -> project

```bash
uv run pms org create "Relay"
uv run pms portfolio create "Payments Portfolio" --org "Relay"
uv run pms program create "Reliability Q1" --org "Relay" --portfolio "Payments Portfolio"

uv run pms product create "Payments API"
uv run pms project create "Payments API Reliability" \
  --product "Payments API" \
  --org "Relay" \
  --portfolio "Payments Portfolio" \
  --program "Reliability Q1"
```

### 2) Multi-horizon goals + acceptance criteria

```bash
uv run pms goal create "Stop failed checkouts" \
  --project "Payments API Reliability" --horizon short_term
uv run pms goal create "Reduce latency regressions" \
  --project "Payments API Reliability" --horizon medium_term
uv run pms goal create "Zero incident posture" \
  --project "Payments API Reliability" --horizon long_term

uv run pms objective create "Short-term acceptance criteria" \
  --goal "Stop failed checkouts"
uv run pms keyresult create "Failed checkouts under 0.5%" \
  --objective "Short-term acceptance criteria" \
  --goal "Stop failed checkouts"
uv run pms keyresult create "Evidence bundle includes test runs + logs" \
  --objective "Short-term acceptance criteria" \
  --goal "Stop failed checkouts"
```

### 3) Plan + tasks + dependencies

```bash
cat > reliability-plan.yml <<'EOF'
acceptance_criteria:
  - "Error budget back under 0.5% for 7 days"
  - "Evidence bundle includes test runs and log artifacts"
tasks:
  - title: "Reproduce checkout failures"
  - title: "Add tracing + metrics for payment retries"
  - title: "Fix retry logic and timeouts"
  - title: "Run load test baseline"
  - title: "Create post-incident runbook"
EOF

uv run pms plan create "Payments Reliability Plan" \
  --project "Payments API Reliability" \
  --goal "Stop failed checkouts" \
  --objective "Short-term acceptance criteria" \
  --format yaml \
  --file reliability-plan.yml

uv run pms task list --project "Payments API Reliability" --format json

# Dependencies: tracing before fix, fix before load test
uv run pms task dep add <task_id_fix_retry> <task_id_tracing> --type blocks
uv run pms task dep add <task_id_load_test> <task_id_fix_retry> --type blocks

# Optional subtasks (hierarchy)
uv run pms task create "Payments API Reliability" "Trace retry span attributes" \
  --parent-id <task_id_tracing>
uv run pms task create "Payments API Reliability" "Trace retry error codes" \
  --parent-id <task_id_tracing>

uv run pms task tree --project "Payments API Reliability"
```

### 4) Label taxonomy + evidence gates

```bash
uv run pms label category create "timebox" --exclusive
uv run pms label create "now" --category "timebox"
uv run pms label create "next" --category "timebox"
uv run pms label create "later" --category "timebox"

uv run pms label assign task <task_id_tracing> now --by lead
uv run pms label assign task <task_id_fix_retry> now --by lead
uv run pms label assign task <task_id_load_test> next --by lead
uv run pms label assign task <task_id_runbook> later --by lead

uv run pms evidence gate add \
  --workflow-id wf_sdlc \
  --from-state planning \
  --to-state implementing \
  --evidence-type note \
  --min-count 1 \
  --message "Add a planning note before implementation"
```

### 5) Workflow assignment + multi-agent checkout

```bash
uv run pms workflow assign <task_id_tracing> sdlc concept --entity-type task
uv run pms workflow assign <task_id_fix_retry> sdlc concept --entity-type task

# Agent A (tracing)
uv run pms task checkout <task_id_tracing> --project "Payments API Reliability" --agent-id agent-a
uv run pms workflow transition <task_id_tracing> idea --by agent-a
uv run pms workflow transition <task_id_tracing> planning --by agent-a
uv run pms task start <task_id_tracing> --project "Payments API Reliability"
uv run pms task progress <task_id_tracing> --project "Payments API Reliability" \
  35 "Tracing spans added to retry path" --by agent-a
uv run pms task renew <task_id_tracing> --project "Payments API Reliability" --agent-id agent-a

# Agent B (retry fix)
uv run pms task checkout <task_id_fix_retry> --project "Payments API Reliability" --agent-id agent-b
uv run pms workflow transition <task_id_fix_retry> idea --by agent-b
uv run pms task start <task_id_fix_retry> --project "Payments API Reliability"
uv run pms task progress <task_id_fix_retry> --project "Payments API Reliability" \
  25 "Retry backoff updated" --by agent-b
```

### 6) Evidence + tests + proof bundle

```bash
uv run pms task evidence add <task_id_tracing> note planning-note \
  --description "Rollout plan: tracing first, retry fixes second"
uv run pms workflow transition <task_id_tracing> implementing --by agent-a

uv run pms test run .
uv run pms test list --format json

# Remote runner can record a test run directly via API.
curl -X POST http://127.0.0.1:27541/api/v1/test-runs \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $PMS_API_KEY" \
  -d '{
    "server_id": "local",
    "project_id": "<project_id>",
    "success": true,
    "started_at": "2026-01-01T00:00:00Z",
    "finished_at": "2026-01-01T00:00:05Z",
    "command": "pytest -q",
    "runner": "remote",
    "logs": {"/tmp/run.log": {"content": "log-data"}}
  }'

uv run pms task evidence add <task_id_fix_retry> test_run <run_id> \
  --project "Payments API Reliability"
uv run pms task evidence add <task_id_fix_retry> artifact logs/retry-metrics.log \
  --project "Payments API Reliability"

uv run pms task proof-bundle <task_id_fix_retry>
uv run pms task evidence list <task_id_fix_retry> --project "Payments API Reliability"
```

### 7) Duplicate detection + merge workflow

```bash
uv run pms task duplicates --format json

uv run pms task merge-preview <primary_task_id> \
  --duplicate-id <dup_task_id_1> \
  --duplicate-id <dup_task_id_2> \
  --format json

uv run pms task merge-duplicates <primary_task_id> \
  --duplicate-id <dup_task_id_1> \
  --duplicate-id <dup_task_id_2>
```

### 8) Timelines + revisions + snapshots

```bash
uv run pms timeline workflow task <task_id_fix_retry> --format json
uv run pms timeline status task <task_id_fix_retry> --format json

uv run pms task show <task_id_fix_retry> --format json \
  --include-history --include-linked-history
uv run pms revision diff task <task_id_fix_retry> --from 1 --to 2 --format json

uv run pms work snapshot --scope-type project --scope "Payments API Reliability" --format json
```

### 9) Retention policy + prune safety

```bash
uv run pms project list --format json
uv run pms test retention-policy set project <project_id> \
  --max-log-bytes 10000000 \
  --max-artifact-bytes 50000000 \
  --max-age-days 14 \
  --notes "Reliability sprint budget"

uv run pms test retention --project "Payments API Reliability"
uv run pms test prune --project-id <project_id> --max-age-days 14 --dry-run --format json
```

### 10) Daily review + next actions

```bash
uv run pms queue presets --project "Payments API Reliability" --view detail
uv run pms work daily --scope-type project --scope "Payments API Reliability" \
  --include-timeline \
  --export reports/payments-daily.json \
  --attach-task <task_id_fix_retry> \
  --attach-strategy ready

uv run pms project summary "Payments API Reliability"
uv run pms goal summary "Stop failed checkouts"
```

Use this loop until the short-term goal is complete, then repeat for medium and
long term goals with the same evidence, timeline, and retention discipline.

---

## Running the Same Flow with Loops (Claude + Codex)

The end-to-end workflow above is the canonical source of truth. The loop systems
should follow the same model: read PMS state, update tasks, attach evidence, and
advance key results/objectives/goals as work is completed.

### Prompt-to-Loop Setup Wizard

Use `pms loop setup` to capture goals, acceptance criteria, tasks, and
dependencies interactively. It generates `PROMPT.md` and `pms-loop.yml` with
goal guard enabled.

```bash
uv run pms loop setup --defaults
```

Or interactive:

```bash
uv run pms loop setup \
  --org "Acme Org" \
  --product "Resume Hosting" \
  --project "Resume Hosting Site" \
  --goal "Launch resume hosting MVP" \
  --goal-horizon short_term
```

Run the loop after setup:

```bash
uv run pms loop run --config pms-loop.yml
```

### Render a Prompt Template from Existing Plans

If you already have a project/goal/plan in PMS and want a prompt with IDs
prefilled, generate it directly:

```bash
uv run pms loop prompt-template \
  --project "Resume Hosting Site" \
  --goal "Launch resume hosting MVP" \
  --plan "Resume Hosting MVP Plan" \
  --prompt-file PROMPT.md \
  --force
```

Related prompt templates:

- [`docs/AGENT_PROMPT_MINIMAL.md`](AGENT_PROMPT_MINIMAL.md) for a short intake flow.
- [`docs/AGENT_PROMPT_MCP_LOOP.md`](AGENT_PROMPT_MCP_LOOP.md) for MCP-only agents.

### Interactive Plan Builder Prompt (Agent Intake)

If you want an agent to build the entire plan interactively (org -> product ->
project -> goal -> objective -> key results -> plan -> tasks -> dependencies),
use [`docs/AGENT_PROMPT_INTERACTIVE_PLAN.md`](AGENT_PROMPT_INTERACTIVE_PLAN.md) as the agent's starting prompt. It
guides intake questions, builds the PMS graph, writes the loop prompt, and
outputs the final `uv run pms loop run --config pms-loop.yml` command.

Example interactive input (abbreviated):

```text
Organization name [Loop Org]: Acme Org
Product name [Loop Product]: Resume Hosting
Project name [Loop Project]: Resume Hosting Site
Primary goal [Ship MVP]: Launch resume hosting MVP
Objective name [Acceptance criteria]: MVP acceptance criteria
Acceptance criterion (blank to finish): Landing page + upload flow
Acceptance criterion (blank to finish): Upload API stub works locally
Acceptance criterion (blank to finish): README + run instructions complete
Acceptance criterion (blank to finish):
Task title (blank to finish): Define UX and requirements
Description for 'Define UX and requirements': Draft user flow + copy
Acceptance criteria numbers for 'Define UX and requirements' (comma-separated): 1
Is 'Define UX and requirements' a forward-looking task? [y/N]: N
Task title (blank to finish): Implement upload stub
Description for 'Implement upload stub': Basic local storage handler
Acceptance criteria numbers for 'Implement upload stub' (comma-separated): 2
Task title (blank to finish):
Add dependencies between tasks? [y/N]: y
Task number that depends on others (blank to finish): 2
Depends on task numbers (comma-separated): 1
Dependency type (blocks, relates_to, duplicates) [blocks]: blocks
```

### Claude Loop

```bash
uv run pms loop run --agent claude --project "Resume Hosting Site" \
  --prompt-file PROMPT.md \
  --completion-promise DONE
```

### Codex Loop

```bash
uv run pms loop run --agent codex --project "Resume Hosting Site" \
  --prompt-file PROMPT.md \
  --completion-promise DONE \
  --codex-model gpt-5 \
  --codex-reasoning-effort medium
```

### Claude Code Stop Hook (Goal Completion Guard)

When running inside Claude Code, add a `Stop` hook that blocks stopping until
all PMS goals are complete. This keeps the agent running through interruptions.

Preferred maintained wrapper when you also want a task/state audit bundle:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "cd \"$CLAUDE_PROJECT_DIR\" && python3 scripts/agent_hooks/pms_stop_audit.py --project \"Resume Hosting Site\" --goal \"Launch resume hosting MVP\" --emit-claude-stop-payload"
          }
        ]
      }
    ]
  }
}
```

Minimal direct guard form:

Add to `.claude/settings.local.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "cd \"$CLAUDE_PROJECT_DIR\" && uv run pms loop guard --project \"Resume Hosting Site\" --hook"
          }
        ]
      }
    ]
  }
}
```

Options:

- `--goal-id <id>` (repeatable) to guard explicit goals only.
- `--allow-no-goals` to allow stopping when no goals exist.
- `scripts/agent_hooks/pms_stop_audit.py` is the maintained wrapper when you
  also want `start`, `dashboard`, `task ready`, `task list`, `work daily`, and
  goal summary artifacts at stop time.
- If permission prompts interrupt the loop, add a Claude Code
  `PermissionRequest` hook allowlist or use the Codex adapter
  `permission_allowlist`.

### Loop Guard in the Runner (Soft-Stop Gate)

You can also gate soft stops (completion markers/promises) inside the loop
runner itself:

```bash
uv run pms loop run --agent claude --project "Resume Hosting Site" \
  --prompt-file PROMPT.md \
  --completion-promise DONE \
  --stop-when-goals-complete \
  --goal "Launch resume hosting MVP"
```

Config form (`pms-loop.yml`):

```yaml
stop_when_goals_complete: true
goal_ids:
  - <goal-id>
include_archived_goals: false
allow_no_goals: false
```

Hard stops (max runtime, max cost, cancel) still apply.

### Claude Code PermissionRequest Allowlist Hook

Auto-approve safe PMS commands and MCP tool calls to keep loops unblocked:

```json
{
  "hooks": {
    "PermissionRequest": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "cd \"$CLAUDE_PROJECT_DIR\" && python3 scripts/claude_hooks/pms_permission_allowlist.py"
          }
        ]
      }
    ]
  }
}
```

Optional allowlist regex:

```
export PMS_HOOK_ALLOWLIST_REGEX="^uv run pms\\b,^pms\\b"
```

### Walkthrough: Continuous Claude Code Loop

1. Bootstrap project + goal:

```bash
uv run pms product create "Resume Hosting"
uv run pms project create "Resume Hosting Site" --product "Resume Hosting"
uv run pms goal create "Launch resume hosting MVP" --project "Resume Hosting Site"
```

2. Create prompt + loop config:

```bash
uv run pms loop init --config pms-loop.yml --prompt-file PROMPT.md
```

Edit `pms-loop.yml`:

```yaml
agent: claude
prompt_file: PROMPT.md
completion_promise: DONE
stop_when_goals_complete: true
goal_ids:
  - <goal-id>
```

3. Add hooks (Stop + PermissionRequest) in `.claude/settings.local.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "cd \"$CLAUDE_PROJECT_DIR\" && uv run pms loop guard --project \"Resume Hosting Site\" --hook"
          }
        ]
      }
    ],
    "PermissionRequest": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "cd \"$CLAUDE_PROJECT_DIR\" && python3 scripts/claude_hooks/pms_permission_allowlist.py"
          }
        ]
      }
    ]
  }
}
```

4. Run the loop:

```bash
uv run pms loop run --agent claude --project "Resume Hosting Site" \
  --prompt-file PROMPT.md \
  --completion-promise DONE \
  --stop-when-goals-complete \
  --goal "Launch resume hosting MVP"
```

5. Inspect progress + guard status:

```bash
uv run pms loop list --project "Resume Hosting Site"
uv run pms loop show <loop_id> --include-messages --format json
uv run pms loop guard --project "Resume Hosting Site" --format json
```

Suggested prompt structure (short form):

- Read current product/project/goal/objective/key results/plan/task state.
- Pick the next task, update progress, attach evidence.
- Update key results and objective progress.
- Complete the goal when all acceptance criteria are met.

### Full Prompt Template (PROMPT.md)

```markdown
# Project

Resume Hosting Site (product: Resume Hosting)

# Goal

Launch resume hosting MVP.

# Acceptance Criteria (modeled as Objective + Key Results)

Objective: MVP acceptance criteria
Key Results:

- Landing page + upload flow
- Upload API stub works locally
- README + run instructions complete
- Evidence captured for all tasks

# Plan

Resume Hosting MVP Plan (acceptance_criteria in plan.yml)

# Loop Rules (must follow exactly)

1. Read PMS state first:
   - `pms product show "Resume Hosting"`
   - `pms project show "Resume Hosting Site"`
   - `pms goal list --project "Resume Hosting Site"`
   - `pms objective list --goal "Launch resume hosting MVP"`
   - `pms keyresult list --objective "MVP acceptance criteria" --goal "Launch resume hosting MVP"`
   - `pms plan show "Resume Hosting MVP Plan" --project "Resume Hosting Site"`
   - `pms task list --project "Resume Hosting Site"`
2. For any task without a workflow, assign the SDLC workflow:
   - `pms workflow assign <task_id> sdlc concept --entity-type task`
3. Check out the task (distributed agents) before work:
   - `pms task checkout <task_id> --project "Resume Hosting Site" --agent-id loop-agent`
4. Pick the next task and update status:
   - `pms task start <task> --project "Resume Hosting Site"`
   - `pms task progress <task> --project "Resume Hosting Site" <percent> <message> --by loop-agent`
   - `pms task complete <task> --project "Resume Hosting Site"`
5. Transition the task workflow as you advance:
   - `pms workflow transition <task_id> idea --by loop-agent`
   - `pms workflow transition <task_id> planning --by loop-agent`
   - `pms workflow transition <task_id> detailed_plan --by loop-agent`
   - `pms workflow transition <task_id> implementing --by loop-agent`
   - `pms workflow transition <task_id> unit_testing --by loop-agent`
   - `pms workflow transition <task_id> integration_testing --by loop-agent`
   - `pms workflow transition <task_id> staging --by loop-agent`
   - `pms workflow transition <task_id> confirmation --by loop-agent`
   - `pms workflow transition <task_id> production --by loop-agent --approved-by lead`
6. If you discover missing work, add tasks immediately:
   - `pms task create "Resume Hosting Site" "<new task title>"`
7. Record evidence for each completed task:
   - `pms task evidence add <task> artifact <path> --project "Resume Hosting Site"`
   - For tests: `pms test run .` then `pms task evidence add <task> test_run <run_id>`
8. Add dependencies when ordering matters:
   - `pms task dep add <task_id> <depends_on_id> --type blocks`
   - `pms task graph <task_id> --project "Resume Hosting Site"`
9. Update key results/objective progress as criteria are met:
   - `pms keyresult update <keyresult> --goal "Launch resume hosting MVP" --progress <percent>`
   - `pms objective update "MVP acceptance criteria" --goal "Launch resume hosting MVP" --progress <percent>`
10. Use `pms goal summary "Launch resume hosting MVP"` each iteration to confirm rollups.
11. When all key results are complete, complete the goal:

- `pms goal complete "Launch resume hosting MVP"`

12. When everything is done, output <promise>DONE</promise>.
```

---

## API-First Walkthrough (HTTP)

Use the API when you want explicit time-series data, full audit trails, and
machine-readable responses for every action.

### A) Start the server and create an API key

```bash
uv run pms init --reset --force
uv run pms auth init --show-key
export PMS_API_KEY=$(cat .pms-admin-key)
uv run pms serve
```

### B) Create a project and acceptance criteria graph

```bash
curl -s -H "X-API-Key: $PMS_API_KEY" -H "Content-Type: application/json" \
  -X POST http://127.0.0.1:27541/api/v1/projects \
  -d '{"name":"Resume Hosting Site","description":"Resume hosting MVP"}'
```

Use the returned `id` values in the following requests:

```bash
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

Create a plan that links the acceptance criteria to tasks:

```bash
curl -s -H "X-API-Key: $PMS_API_KEY" -H "Content-Type: application/json" \
  -X POST http://127.0.0.1:27541/api/v1/plans \
  -d '{"name":"Resume Hosting MVP Plan","format":"json","content":{"acceptance_criteria":[{"id":"ac-1","description":"Landing page + upload flow"}]},"project_id":"<project_id>","goal_id":"<goal_id>","objective_id":"<objective_id>"}'
```

### C) Create tasks, run workflow, and attach evidence

```bash
curl -s -H "X-API-Key: $PMS_API_KEY" -H "Content-Type: application/json" \
  -X POST http://127.0.0.1:27541/api/v1/tasks \
  -d '{"project_id":"<project_id>","title":"Implement static site skeleton"}'

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

### D) Time-series, timelines, and audit bundles

```bash
curl -s -H "X-API-Key: $PMS_API_KEY" \
  http://127.0.0.1:27541/api/v1/tasks/<task_id>/progress/timeline

curl -s -H "X-API-Key: $PMS_API_KEY" \
  http://127.0.0.1:27541/api/v1/transitions/workflow/task/<task_id>

curl -s -H "X-API-Key: $PMS_API_KEY" \
  http://127.0.0.1:27541/api/v1/transitions/status/task/<task_id>

curl -s -H "X-API-Key: $PMS_API_KEY" \
  "http://127.0.0.1:27541/api/v1/revisions/task/<task_id>/bundle?include_linked=true&include_linked_history=true"

curl -s -H "X-API-Key: $PMS_API_KEY" \
  http://127.0.0.1:27541/api/v1/work-snapshots/project/<project_id>
```

---

## Additional Real-World Examples

Each scenario uses the same modeling pattern:
Goal + Objective + Key Results + Plan + Tasks + Workflow + Evidence.

### Example: Public API Launch

Use case: ship a versioned API with docs, tests, and evidence.

```bash
uv run pms product create "Public API"
uv run pms project create "Public API v1" --product "Public API"

uv run pms goal create "Ship API v1" --project "Public API v1"
uv run pms objective create "API v1 acceptance criteria" --goal "Ship API v1"
uv run pms keyresult create "CRUD endpoints implemented" \
  --objective "API v1 acceptance criteria" --goal "Ship API v1"
uv run pms keyresult create "OpenAPI docs published" \
  --objective "API v1 acceptance criteria" --goal "Ship API v1"
uv run pms keyresult create "Integration tests passing" \
  --objective "API v1 acceptance criteria" --goal "Ship API v1"

cat > api-plan.yml <<'EOF'
acceptance_criteria:
  - id: api-1
    description: CRUD endpoints for core resources
  - id: api-2
    description: OpenAPI spec + docs site
  - id: api-3
    description: Integration test suite with evidence
EOF

uv run pms plan create "API v1 Plan" \
  --project "Public API v1" \
  --goal "Ship API v1" \
  --objective "API v1 acceptance criteria" \
  --format yaml \
  --file api-plan.yml

uv run pms task create "Public API v1" "Implement CRUD endpoints"
uv run pms task create "Public API v1" "Generate OpenAPI schema"
uv run pms task create "Public API v1" "Publish docs site"
uv run pms task create "Public API v1" "Write integration tests"
uv run pms task create "Public API v1" "Run tests + attach evidence"

uv run pms plan update "API v1 Plan" \
  --project "Public API v1" \
  --task "Implement CRUD endpoints" \
  --task "Generate OpenAPI schema" \
  --task "Publish docs site" \
  --task "Write integration tests" \
  --task "Run tests + attach evidence"

# Dependencies + workflow (replace task IDs from task list)
uv run pms task list --project "Public API v1" --format json
uv run pms task dep add <task_id_openapi> <task_id_crud> --type blocks
uv run pms task dep add <task_id_docs> <task_id_openapi> --type blocks
uv run pms workflow assign <task_id_crud> sdlc concept --entity-type task

# Execution example
uv run pms task start "Implement CRUD endpoints" --project "Public API v1"
uv run pms workflow transition <task_id_crud> idea --by api-agent
uv run pms workflow transition <task_id_crud> planning --by api-agent
uv run pms workflow transition <task_id_crud> implementing --by api-agent
uv run pms task progress "Implement CRUD endpoints" --project "Public API v1" \
  60 "Handlers and routes done" --by api-agent
uv run pms task complete "Implement CRUD endpoints" --project "Public API v1"
uv run pms task evidence add "Implement CRUD endpoints" artifact src/api/routes.py \
  --project "Public API v1"

uv run pms test run .
uv run pms task evidence add "Run tests + attach evidence" test_run <run_id> \
  --project "Public API v1"

uv run pms keyresult update "CRUD endpoints implemented" \
  --goal "Ship API v1" --progress 100
```

### Example: Data Pipeline + Reporting

Use case: deliver a pipeline with validation and dashboards.

```bash
uv run pms product create "Analytics Platform"
uv run pms project create "Daily Metrics Pipeline" --product "Analytics Platform"

uv run pms goal create "Daily metrics pipeline live" --project "Daily Metrics Pipeline"
uv run pms objective create "Pipeline acceptance criteria" --goal "Daily metrics pipeline live"
uv run pms keyresult create "Ingest + transform jobs succeed" \
  --objective "Pipeline acceptance criteria" --goal "Daily metrics pipeline live"
uv run pms keyresult create "Data validation checks passing" \
  --objective "Pipeline acceptance criteria" --goal "Daily metrics pipeline live"
uv run pms keyresult create "Dashboard published" \
  --objective "Pipeline acceptance criteria" --goal "Daily metrics pipeline live"

uv run pms task create "Daily Metrics Pipeline" "Define source schema"
uv run pms task create "Daily Metrics Pipeline" "Build ingestion job"
uv run pms task create "Daily Metrics Pipeline" "Add validation checks"
uv run pms task create "Daily Metrics Pipeline" "Build daily dashboard"
uv run pms task create "Daily Metrics Pipeline" "Run pipeline + attach evidence"

uv run pms task list --project "Daily Metrics Pipeline" --format json
uv run pms task dep add <task_id_validation> <task_id_ingest> --type blocks
uv run pms task dep add <task_id_dashboard> <task_id_validation> --type blocks
uv run pms workflow assign <task_id_ingest> sdlc concept --entity-type task

uv run pms task start "Build ingestion job" --project "Daily Metrics Pipeline"
uv run pms workflow transition <task_id_ingest> planning --by data-agent
uv run pms workflow transition <task_id_ingest> implementing --by data-agent
uv run pms task progress "Build ingestion job" --project "Daily Metrics Pipeline" \
  40 "Base ETL job scaffolded" --by data-agent
uv run pms task complete "Build ingestion job" --project "Daily Metrics Pipeline"
uv run pms task evidence add "Build ingestion job" artifact jobs/ingest.py \
  --project "Daily Metrics Pipeline"

uv run pms keyresult update "Ingest + transform jobs succeed" \
  --goal "Daily metrics pipeline live" --progress 100
```

### Example: Incident Response + Remediation

Use case: handle an outage with proof and postmortem tasks.

```bash
uv run pms product create "Payments"
uv run pms project create "Incident 2025-03-18" --product "Payments"

uv run pms goal create "Restore payments and prevent recurrence" \
  --project "Incident 2025-03-18"
uv run pms objective create "Incident acceptance criteria" \
  --goal "Restore payments and prevent recurrence"
uv run pms keyresult create "Service restored" \
  --objective "Incident acceptance criteria" --goal "Restore payments and prevent recurrence"
uv run pms keyresult create "Root cause documented" \
  --objective "Incident acceptance criteria" --goal "Restore payments and prevent recurrence"
uv run pms keyresult create "Remediations shipped" \
  --objective "Incident acceptance criteria" --goal "Restore payments and prevent recurrence"

uv run pms task create "Incident 2025-03-18" "Triage and mitigate"
uv run pms task create "Incident 2025-03-18" "Capture logs + evidence"
uv run pms task create "Incident 2025-03-18" "Root cause analysis"
uv run pms task create "Incident 2025-03-18" "Implement fix"
uv run pms task create "Incident 2025-03-18" "Postmortem write-up"

uv run pms task list --project "Incident 2025-03-18" --format json
uv run pms workflow assign <task_id_triage> sdlc concept --entity-type task

uv run pms task start "Triage and mitigate" --project "Incident 2025-03-18"
uv run pms workflow transition <task_id_triage> implementing --by incident-agent
uv run pms task progress "Triage and mitigate" --project "Incident 2025-03-18" \
  80 "Mitigation applied" --by incident-agent
uv run pms task complete "Triage and mitigate" --project "Incident 2025-03-18"
uv run pms task evidence add "Capture logs + evidence" artifact logs/incident.log \
  --project "Incident 2025-03-18"

uv run pms keyresult update "Service restored" \
  --goal "Restore payments and prevent recurrence" --progress 100
```

### Example: CLI Tool Release

Use case: ship a CLI with packaging, tests, and release notes.

```bash
uv run pms product create "DevTools CLI"
uv run pms project create "CLI v0.2 Release" --product "DevTools CLI"

uv run pms goal create "Release CLI v0.2" --project "CLI v0.2 Release"
uv run pms objective create "Release acceptance criteria" --goal "Release CLI v0.2"
uv run pms keyresult create "New commands implemented" \
  --objective "Release acceptance criteria" --goal "Release CLI v0.2"
uv run pms keyresult create "Tests + packaging complete" \
  --objective "Release acceptance criteria" --goal "Release CLI v0.2"
uv run pms keyresult create "Release notes published" \
  --objective "Release acceptance criteria" --goal "Release CLI v0.2"

uv run pms task create "CLI v0.2 Release" "Implement new commands"
uv run pms task create "CLI v0.2 Release" "Update packaging"
uv run pms task create "CLI v0.2 Release" "Write release notes"
uv run pms task create "CLI v0.2 Release" "Run tests + attach evidence"

uv run pms task list --project "CLI v0.2 Release" --format json
uv run pms workflow assign <task_id_commands> sdlc concept --entity-type task
uv run pms task start "Implement new commands" --project "CLI v0.2 Release"
uv run pms workflow transition <task_id_commands> implementing --by cli-agent
uv run pms task progress "Implement new commands" --project "CLI v0.2 Release" \
  55 "Core flags implemented" --by cli-agent
uv run pms task complete "Implement new commands" --project "CLI v0.2 Release"
uv run pms task evidence add "Implement new commands" artifact src/cli.py \
  --project "CLI v0.2 Release"

uv run pms test run .
uv run pms task evidence add "Run tests + attach evidence" test_run <run_id> \
  --project "CLI v0.2 Release"
```

### Example: Program + Portfolio Rollups (Multi-Team)

Use case: multiple teams ship related projects under a portfolio/program.

```bash
uv run pms org create "Acme"
uv run pms portfolio create "Platform Portfolio" --org "Acme"
uv run pms program create "Platform Q2" --org "Acme" --portfolio "Platform Portfolio"

uv run pms product create "Auth Service"
uv run pms project create "Auth Service v2" --product "Auth Service"
uv run pms goal create "Ship auth v2" --project "Auth Service v2"

uv run pms product create "Billing Service"
uv run pms project create "Billing Service v1" --product "Billing Service"
uv run pms goal create "Ship billing v1" --project "Billing Service v1"

# Attach goals to the program/portfolio for rollups (use IDs from goal list)
uv run pms goal list --format json
uv run pms program list --org "Acme" --portfolio "Platform Portfolio" --format json
uv run pms portfolio list --org "Acme" --format json
uv run pms program update <program_id> --goal-id <goal_id_auth_v2> --goal-id <goal_id_billing_v1>
uv run pms portfolio update <portfolio_id> --goal-id <goal_id_auth_v2> --goal-id <goal_id_billing_v1>

uv run pms program dashboard --org "Acme" --portfolio "Platform Portfolio"
uv run pms portfolio dashboard --org "Acme"
```

### Example: Distributed Agents + Checkout Workflow

Use case: multiple agents claim tasks, update progress, and release locks.

```bash
uv run pms task list --project "Resume Hosting Site" --format json

# Agent A checks out and updates a task
uv run pms task checkout <task_id_site_skeleton> --project "Resume Hosting Site" --agent-id agent-a
uv run pms task start <task_id_site_skeleton> --project "Resume Hosting Site"
uv run pms task progress <task_id_site_skeleton> --project "Resume Hosting Site" \
  45 "Layout scaffolding" --by agent-a
uv run pms task renew <task_id_site_skeleton> --project "Resume Hosting Site" --agent-id agent-a

# Agent B checks out dependent task
uv run pms task checkout <task_id_upload_form> --project "Resume Hosting Site" --agent-id agent-b
uv run pms task progress <task_id_upload_form> --project "Resume Hosting Site" \
  25 "Basic form markup" --by agent-b

# Release locks when done
uv run pms task release <task_id_site_skeleton> --project "Resume Hosting Site" --agent-id agent-a
uv run pms task release <task_id_upload_form> --project "Resume Hosting Site" --agent-id agent-b
```

### Example: MCP Tool Usage Inside Agents

Use case: run PMS as an MCP server and call tools from an agent runtime.

```bash
uv run pms install --name pms
uv run pms verify-install --name pms
uv run pms capabilities list --type tools
```

Example MCP tool calls (names are `mcp__pms__*`):

```json
{
  "tool": "mcp__pms__create_task",
  "input": {
    "project": "<project-id>",
    "title": "Implement upload form",
    "parent_id": "<root-task-id>"
  }
}
```

```json
{
  "tool": "mcp__pms__assign_workflow",
  "input": {
    "entity_id": "<task-id>",
    "workflow_name": "sdlc",
    "initial_state": "concept",
    "entity_type": "task"
  }
}
```

```json
{
  "tool": "mcp__pms__update_task",
  "input": {
    "task_id": "<task-id>",
    "parent_id": "<root-task-id>"
  }
}
```

```json
{
  "tool": "mcp__pms__get_task_tree",
  "input": {
    "project": "<project-id>"
  }
}
```

```json
{
  "tool": "mcp__pms__transition_workflow",
  "input": {
    "entity_id": "<task-id>",
    "to_state": "idea",
    "triggered_by": "agent-a",
    "reason": "Start implementation"
  }
}
```

```json
{
  "tool": "mcp__pms__update_task_progress",
  "input": {
    "task_id": "<task-id>",
    "percent_complete": 35,
    "status_message": "Form fields wired",
    "updated_by": "agent-a"
  }
}
```

```json
{
  "tool": "mcp__pms__add_task_dependency",
  "input": {
    "task_id": "<task-id-2>",
    "depends_on_id": "<task-id>",
    "dependency_type": "blocks"
  }
}
```

```json
{
  "tool": "mcp__pms__checkout_task",
  "input": {
    "task_id": "<task-id>",
    "agent_session_id": "agent-a",
    "lease_seconds": 300
  }
}
```

```json
{
  "tool": "mcp__pms__add_task_evidence",
  "input": {
    "task_id": "<task-id>",
    "evidence_type": "note",
    "reference": "manual-check",
    "description": "Uploaded sample resume in local test",
    "created_by": "agent-a"
  }
}
```

```json
{
  "tool": "mcp__pms__create_test_run",
  "input": {
    "server_id": "local",
    "project_id": "<project-id>",
    "success": "passed",
    "started_at": "2026-01-01T00:00:00Z",
    "finished_at": "2026-01-01T00:00:05Z",
    "command": "pytest -q",
    "runner": "mcp",
    "task_ids": "<task-id>,<task-id-2>",
    "logs": "{\"/tmp/run.log\": \"smoke-check ok\"}"
  }
}
```

### CLI vs MCP Quick Reference

Use this table to translate common actions between CLI and MCP tools.

| Intent                  | CLI                                                                     | MCP Tool                            |
| ----------------------- | ----------------------------------------------------------------------- | ----------------------------------- |
| Create a project        | `pms project create "<name>"`                                           | `mcp__pms__create_project`          |
| List tasks in a project | `pms task list --project "<name>"`                                      | `mcp__pms__list_tasks`              |
| Assign workflow         | `pms workflow assign <id> sdlc concept --entity-type task`              | `mcp__pms__assign_workflow`         |
| Transition workflow     | `pms workflow transition <id> idea --by <user>`                         | `mcp__pms__transition_workflow`     |
| Start a task            | `pms task start <task> --project "<name>"`                              | `mcp__pms__start_task`              |
| Update progress         | `pms task progress <task> --project "<name>" <pct> "<msg>" --by <user>` | `mcp__pms__update_task_progress`    |
| Add evidence            | `pms task evidence add <task> <type> <ref>`                             | `mcp__pms__add_task_evidence`       |
| Record test run         | `pms test run .`                                                        | `mcp__pms__create_test_run`         |
| Checkout task           | `pms task checkout <task_id> --agent-id <agent>`                        | `mcp__pms__checkout_task`           |
| Work snapshot           | `pms work snapshot --scope-type project --scope "<name>"`               | `mcp__pms__get_work_snapshot`       |
| Goal summary            | `pms goal summary "<goal>"`                                             | `mcp__pms__get_goal_summary`        |
| Program dashboard       | `pms program dashboard --org "<org>" --portfolio "<portfolio>"`         | `mcp__pms__get_program_dashboard`   |
| Portfolio dashboard     | `pms portfolio dashboard --org "<org>"`                                 | `mcp__pms__get_portfolio_dashboard` |

---

## MCP Agent Loop Prompt (Detailed)

This is a detailed prompt template for agents using MCP tools directly. It
instructs the agent to read PMS state, assign workflows, update tasks, attach
evidence, and validate goals/end criteria.

```text
You are running inside an MCP-enabled agent. Use PMS tools (mcp__pms__*).

Project: Resume Hosting Site
Goal: Launch resume hosting MVP
Objective: MVP acceptance criteria
Plan: Resume Hosting MVP Plan

Rules:
1) Read PMS state first:
   - mcp__pms__get_project
   - mcp__pms__get_goal
   - mcp__pms__get_goal_summary
   - mcp__pms__list_objectives
   - mcp__pms__list_key_results
   - mcp__pms__get_plan
   - mcp__pms__list_tasks
2) Assign workflows and transition states:
   - mcp__pms__assign_workflow
   - mcp__pms__transition_workflow
3) Checkout tasks while working:
   - mcp__pms__checkout_task
   - mcp__pms__renew_task_checkout
   - mcp__pms__release_task_checkout
4) Update progress and complete tasks:
   - mcp__pms__update_task_progress
   - mcp__pms__start_task
   - mcp__pms__complete_task
5) Add dependencies when ordering matters:
   - mcp__pms__add_task_dependency
   - mcp__pms__get_task_tree
6) Record tests and attach proof:
   - mcp__pms__create_test_run (for remote results)
   - mcp__pms__add_task_evidence
   - mcp__pms__get_task_proof_bundle
7) Update key results and objective progress:
   - mcp__pms__update_key_result
   - mcp__pms__update_objective
8) Validate the goal:
   - mcp__pms__get_goal_summary
   - mcp__pms__complete_goal when all criteria are met
```

Example tool call sequence (abbreviated):

```json
{"tool":"mcp__pms__list_tasks","input":{"project":"<project-id>"}}
{"tool":"mcp__pms__assign_workflow","input":{"entity_id":"<task-id>","workflow_name":"sdlc","initial_state":"concept","entity_type":"task"}}
{"tool":"mcp__pms__transition_workflow","input":{"entity_id":"<task-id>","to_state":"idea","triggered_by":"agent-a"}}
{"tool":"mcp__pms__checkout_task","input":{"task_id":"<task-id>","agent_session_id":"agent-a","lease_seconds":300}}
{"tool":"mcp__pms__start_task","input":{"task_id":"<task-id>"}}
{"tool":"mcp__pms__update_task_progress","input":{"task_id":"<task-id>","percent_complete":40,"status_message":"Core flow wired","updated_by":"agent-a"}}
{"tool":"mcp__pms__update_task","input":{"task_id":"<task-id-2>","parent_id":"<task-id>"}}
{"tool":"mcp__pms__add_task_dependency","input":{"task_id":"<task-id-2>","depends_on_id":"<task-id>","dependency_type":"blocks"}}
{"tool":"mcp__pms__get_task_tree","input":{"project":"<project-id>"}}
{"tool":"mcp__pms__add_task_evidence","input":{"task_id":"<task-id>","evidence_type":"note","reference":"manual-check","description":"Upload flow verified","created_by":"agent-a"}}
{"tool":"mcp__pms__create_test_run","input":{"server_id":"local","project_id":"<project-id>","success":"passed","started_at":"2026-01-01T00:00:00Z","finished_at":"2026-01-01T00:00:05Z","command":"pytest -q","runner":"mcp","task_ids":"<task-id>"}}
{"tool":"mcp__pms__complete_task","input":{"task_id":"<task-id>"}}
{"tool":"mcp__pms__release_task_checkout","input":{"task_id":"<task-id>","agent_session_id":"agent-a"}}
{"tool":"mcp__pms__update_key_result","input":{"key_result_id":"<key-result-id>","progress_percent":100}}
{"tool":"mcp__pms__complete_goal","input":{"goal_id":"<goal-id>"}}
```

### MCP Loop Walkthrough (Explicit Steps)

Use this sequence as a deterministic agent loop. It shows a complete iteration
with workflow transitions, status updates, evidence, and goal rollup checks.

Step 1: Read current state and pick a ready task.

```json
{"tool":"mcp__pms__get_project","input":{"identifier":"Resume Hosting Site"}}
{"tool":"mcp__pms__get_goal","input":{"identifier":"Launch resume hosting MVP"}}
{"tool":"mcp__pms__get_goal_summary","input":{"identifier":"Launch resume hosting MVP"}}
{"tool":"mcp__pms__list_ready_tasks","input":{"project":"Resume Hosting Site","limit":5}}
```

Step 2: Assign workflow if missing and transition to idea.

```json
{"tool":"mcp__pms__assign_workflow","input":{"entity_id":"<task-id>","workflow_name":"sdlc","initial_state":"concept","entity_type":"task"}}
{"tool":"mcp__pms__transition_workflow","input":{"entity_id":"<task-id>","to_state":"idea","triggered_by":"agent-a"}}
```

Step 3: Checkout and start work, then report progress.

```json
{"tool":"mcp__pms__checkout_task","input":{"task_id":"<task-id>","agent_session_id":"agent-a","lease_seconds":300}}
{"tool":"mcp__pms__start_task","input":{"task_id":"<task-id>"}}
{"tool":"mcp__pms__update_task_progress","input":{"task_id":"<task-id>","percent_complete":35,"status_message":"Wire base UI and forms","updated_by":"agent-a"}}
```

Step 4: Add evidence and advance workflow. If the transition is blocked, add
required evidence and retry.

```json
{"tool":"mcp__pms__add_task_evidence","input":{"task_id":"<task-id>","evidence_type":"note","reference":"design-note","description":"Planning notes added","created_by":"agent-a"}}
{"tool":"mcp__pms__transition_workflow","input":{"entity_id":"<task-id>","to_state":"planning","triggered_by":"agent-a"}}
```

Step 5: Record tests and attach test evidence.

```json
{"tool":"mcp__pms__create_test_run","input":{"server_id":"local","project_id":"<project-id>","success":"passed","started_at":"2026-01-01T00:00:00Z","finished_at":"2026-01-01T00:00:05Z","command":"pytest -q","runner":"mcp","task_ids":"<task-id>","logs":"{\"/tmp/test.log\":\"ok\"}"}}
{"tool":"mcp__pms__add_task_evidence","input":{"task_id":"<task-id>","evidence_type":"test_run","reference":"<run_id>","description":"pytest -q","created_by":"agent-a"}}
```

Step 6: Complete task, attach proof bundle, and release checkout.

```json
{"tool":"mcp__pms__complete_task","input":{"task_id":"<task-id>"}}
{"tool":"mcp__pms__get_task_proof_bundle","input":{"task_id":"<task-id>","format":"json"}}
{"tool":"mcp__pms__release_task_checkout","input":{"task_id":"<task-id>","agent_session_id":"agent-a"}}
```

Step 7: Update key results, re-check goal summary, and finish if complete.

```json
{"tool":"mcp__pms__update_key_result","input":{"key_result_id":"<key-result-id>","progress_percent":100}}
{"tool":"mcp__pms__get_goal_summary","input":{"identifier":"Launch resume hosting MVP"}}
{"tool":"mcp__pms__complete_goal","input":{"goal_id":"<goal-id>"}}
```

---

## MCP Multi-Project Loop: Program Rollups + Cross-Dependencies

This loop shows a single agent coordinating work across two projects under a
program/portfolio. It creates the scope, wires cross-project dependencies,
records test runs, and updates rollups for visibility.

### Step 1: Create org/portfolio/program

```json
{"tool":"mcp__pms__create_organization","input":{"name":"OmniCorp","owner":"lead@omni.test","members":"lead@omni.test"}}
{"tool":"mcp__pms__create_portfolio","input":{"name":"Customer Experience","org_id":"<org_id>"}}
{"tool":"mcp__pms__create_program","input":{"name":"Q3 Launch","org_id":"<org_id>","portfolio_id":"<portfolio_id>"}}
```

### Step 2: Create products/projects

```json
{"tool":"mcp__pms__create_product","input":{"name":"Checkout API","vision":"Payment processing APIs"}}
{"tool":"mcp__pms__create_product","input":{"name":"Web Store","vision":"Customer storefront experience"}}
{"tool":"mcp__pms__create_project","input":{"name":"Checkout API v2","description":"Payments API upgrade","org_id":"<org_id>","portfolio_id":"<portfolio_id>","program_id":"<program_id>","product_id":"<product_api_id>"}}
{"tool":"mcp__pms__create_project","input":{"name":"Web Store v5","description":"Checkout UI overhaul","org_id":"<org_id>","portfolio_id":"<portfolio_id>","program_id":"<program_id>","product_id":"<product_web_id>"}}
```

### Step 3: Create goals + tasks per project

```json
{"tool":"mcp__pms__create_goal","input":{"name":"Ship Checkout API v2","project_id":"<project-id-api>","horizon":"short_term"}}
{"tool":"mcp__pms__create_goal","input":{"name":"Ship Web Store v5","project_id":"<project-id-web>","horizon":"short_term"}}

{"tool":"mcp__pms__create_task","input":{"project":"<project-id-api>","title":"Implement payment endpoint"}}
{"tool":"mcp__pms__create_task","input":{"project":"<project-id-api>","title":"Publish API docs"}}
{"tool":"mcp__pms__create_task","input":{"project":"<project-id-web>","title":"Checkout UI integration"}}
{"tool":"mcp__pms__create_task","input":{"project":"<project-id-web>","title":"E2E purchase flow tests"}}
```

### Step 4: Wire cross-project dependencies + task tree

```json
{"tool":"mcp__pms__add_task_dependency","input":{"task_id":"<task-id-ui>","depends_on_id":"<task-id-api>","dependency_type":"blocks"}}
{"tool":"mcp__pms__get_task_tree","input":{"project":"<project-id-web>"}}
```

### Step 5: Work loop + evidence + test runs

```json
{"tool":"mcp__pms__assign_workflow","input":{"entity_id":"<task-id-api>","workflow_name":"sdlc","initial_state":"concept","entity_type":"task"}}
{"tool":"mcp__pms__transition_workflow","input":{"entity_id":"<task-id-api>","to_state":"implementing","triggered_by":"agent-a"}}
{"tool":"mcp__pms__start_task","input":{"task_id":"<task-id-api>"}}
{"tool":"mcp__pms__update_task_progress","input":{"task_id":"<task-id-api>","percent_complete":60,"status_message":"Endpoint implemented","updated_by":"agent-a"}}
{"tool":"mcp__pms__create_test_run","input":{"server_id":"local","project_id":"<project-id-api>","success":"passed","started_at":"2026-01-01T00:00:00Z","finished_at":"2026-01-01T00:00:05Z","command":"pytest -q","runner":"mcp","task_ids":"<task-id-api>"}}
{"tool":"mcp__pms__add_task_evidence","input":{"task_id":"<task-id-api>","evidence_type":"test_run","reference":"<run_id>","description":"API tests passed","created_by":"agent-a"}}
{"tool":"mcp__pms__complete_task","input":{"task_id":"<task-id-api>"}}
```

### Step 6: Rollups and visibility

```json
{"tool":"mcp__pms__get_program_dashboard","input":{"org_id":"<org_id>","portfolio_id":"<portfolio_id>"}}
{"tool":"mcp__pms__get_portfolio_dashboard","input":{"org_id":"<org_id>"}}
{"tool":"mcp__pms__get_work_snapshot","input":{"scope_type":"project","scope_id":"<project-id-web>","task_limit":5,"test_limit":5}}
```

Use this loop to keep work synchronized across projects while maintaining a
single, shared view of progress at the program and portfolio level.

---

## Cross-Project Dependencies + Rollups

Use case: a frontend project depends on an API project. Tasks cross-link across
projects and roll up into program/portfolio dashboards.

```bash
uv run pms org create "OmniCorp"
uv run pms portfolio create "Customer Experience" --org "OmniCorp"
uv run pms program create "Q3 Launch" --org "OmniCorp" --portfolio "Customer Experience"

uv run pms product create "Checkout API"
uv run pms project create "Checkout API v2" --product "Checkout API"
uv run pms goal create "Ship Checkout API v2" --project "Checkout API v2"

uv run pms product create "Web Store"
uv run pms project create "Web Store v5" --product "Web Store"
uv run pms goal create "Ship Web Store v5" --project "Web Store v5"

uv run pms task create "Checkout API v2" "Implement payment endpoint"
uv run pms task create "Checkout API v2" "Publish API docs"
uv run pms task create "Web Store v5" "Checkout UI integration"
uv run pms task create "Web Store v5" "E2E purchase flow tests"

# Get task IDs for cross-project dependency wiring
uv run pms task list --project "Checkout API v2" --format json
uv run pms task list --project "Web Store v5" --format json

# Example: UI integration depends on payment endpoint
uv run pms task dep add <task_id_ui> <task_id_api> --type blocks
uv run pms task graph <task_id_ui> --project "Web Store v5"

# Attach goals to program/portfolio for rollups (use IDs from list output)
uv run pms goal list --format json
uv run pms program list --org "OmniCorp" --portfolio "Customer Experience" --format json
uv run pms portfolio list --org "OmniCorp" --format json
uv run pms program update <program_id> --goal-id <goal_id_api> --goal-id <goal_id_ui>
uv run pms portfolio update <portfolio_id> --goal-id <goal_id_api> --goal-id <goal_id_ui>

uv run pms program dashboard --org "OmniCorp" --portfolio "Customer Experience"
uv run pms portfolio dashboard --org "OmniCorp"
```

---

## Extreme Feature Combination: Multi-Project Trees + Cross-Dependencies + Proof Loop

This scenario ties short/medium/long horizons to multiple projects, with
subtasks, dependency graphs, evidence gates, and proof bundles. It is a
blueprint for large, distributed delivery.

### 1) Scope + horizons

```bash
uv run pms org create "Nova"
uv run pms portfolio create "Platform Portfolio" --org "Nova"
uv run pms program create "Scale Q4" --org "Nova" --portfolio "Platform Portfolio"

uv run pms product create "Inference Gateway"
uv run pms project create "Gateway Core" --product "Inference Gateway" \
  --org "Nova" --portfolio "Platform Portfolio" --program "Scale Q4"

uv run pms product create "Observability"
uv run pms project create "Telemetry Stack" --product "Observability" \
  --org "Nova" --portfolio "Platform Portfolio" --program "Scale Q4"

uv run pms goal create "Stabilize latency p95" --project "Gateway Core" --horizon short_term
uv run pms goal create "Increase throughput" --project "Gateway Core" --horizon medium_term
uv run pms goal create "Full autoscale roadmap" --project "Gateway Core" --horizon long_term
```

### 2) Objectives + key results (acceptance criteria)

```bash
uv run pms objective create "Short-term acceptance" \
  --goal "Stabilize latency p95"
uv run pms keyresult create "p95 under 250ms for 7 days" \
  --objective "Short-term acceptance" --goal "Stabilize latency p95"
uv run pms keyresult create "Proof bundle with tests + logs" \
  --objective "Short-term acceptance" --goal "Stabilize latency p95"
```

### 3) Plan + tasks + subtasks

```bash
cat > scale-plan.yml <<'EOF'
acceptance_criteria:
  - "p95 under 250ms for 7 days"
  - "All proof bundles include test runs + logs"
tasks:
  - title: "Instrument gateway request path"
  - title: "Tune retry and timeout policies"
  - title: "Add telemetry sampling controls"
  - title: "Run latency load test"
EOF

uv run pms plan create "Scale Q4 Plan" \
  --project "Gateway Core" \
  --goal "Stabilize latency p95" \
  --objective "Short-term acceptance" \
  --format yaml \
  --file scale-plan.yml

uv run pms task list --project "Gateway Core" --format json

uv run pms task create "Gateway Core" "Trace request span attributes" \
  --parent-id <task_id_instrument>
uv run pms task create "Gateway Core" "Trace retry failure codes" \
  --parent-id <task_id_instrument>

uv run pms task tree --project "Gateway Core"
```

### 4) Cross-project dependencies + linkage

```bash
uv run pms task create "Telemetry Stack" "Export gateway span metrics"
uv run pms task create "Telemetry Stack" "Deploy tail sampling rules"

uv run pms task list --project "Telemetry Stack" --format json

# Gateway tuning depends on telemetry exports
uv run pms task dep add <task_id_tune_retry> <task_id_export_metrics> --type blocks
uv run pms task graph <task_id_tune_retry>
```

### 5) Labels + gates + workflows

```bash
uv run pms label category create "horizon" --exclusive
uv run pms label create "now" --category "horizon"
uv run pms label create "next" --category "horizon"
uv run pms label create "later" --category "horizon"

uv run pms label assign task <task_id_instrument> now --by lead
uv run pms label assign task <task_id_tune_retry> now --by lead
uv run pms label assign task <task_id_load_test> next --by lead

uv run pms label gate add \
  --workflow-id wf_sdlc \
  --from-state idea \
  --to-state planning \
  --rule-type require_category \
  --category-id <horizon_category_id> \
  --message "Set horizon label before planning"

uv run pms evidence gate add \
  --workflow-id wf_sdlc \
  --from-state planning \
  --to-state implementing \
  --evidence-type note \
  --min-count 1 \
  --message "Add a planning note before implementation"
```

### 6) Execution + evidence + tests

```bash
uv run pms workflow assign <task_id_instrument> sdlc concept --entity-type task
uv run pms workflow transition <task_id_instrument> idea --by agent-core
uv run pms task start <task_id_instrument> --project "Gateway Core"
uv run pms task progress <task_id_instrument> --project "Gateway Core" \
  50 "Spans wired to retry path" --by agent-core
uv run pms task evidence add <task_id_instrument> note plan-note \
  --description "Instrumentation order + test plan"
uv run pms workflow transition <task_id_instrument> planning --by agent-core
uv run pms workflow transition <task_id_instrument> implementing --by agent-core

uv run pms test run .
uv run pms task evidence add <task_id_load_test> test_run <run_id> \
  --project "Gateway Core"

uv run pms task proof-bundle <task_id_load_test>
```

### 7) Timeline + revisions + daily review

```bash
uv run pms timeline workflow task <task_id_instrument> --format json
uv run pms timeline status task <task_id_instrument> --format json
uv run pms revision bundle task <task_id_instrument> --include-linked --format json

uv run pms work daily --scope-type project --scope "Gateway Core" \
  --include-timeline --export reports/gateway-daily.json --attach-strategy ready
```

### 8) Rollups + horizon continuity

```bash
uv run pms project summary "Gateway Core"
uv run pms goal summary "Stabilize latency p95"
uv run pms program dashboard --org "Nova" --portfolio "Platform Portfolio"
uv run pms portfolio dashboard --org "Nova"
```

Use this loop to complete the short-term goal, then repeat for medium and long
term goals, keeping the hierarchy and evidence trail intact across projects.

For portfolio/program hierarchy work, preserve direct strategic links as
first-class data. Program and portfolio goal/objective associations are native
edge-table relationships; the read surfaces then combine those direct links
with project-derived scope for effective rollups.

MCP tool call version (IDs come from create/list outputs):

```json
{"tool":"mcp__pms__create_organization","input":{"name":"OmniCorp"}}
{"tool":"mcp__pms__create_portfolio","input":{"name":"Customer Experience","org_id":"<org-id>"}}
{"tool":"mcp__pms__create_program","input":{"name":"Q3 Launch","org_id":"<org-id>","portfolio_id":"<portfolio-id>"}}

{"tool":"mcp__pms__create_project","input":{"name":"Checkout API v2","description":"API project","org_id":"<org-id>","portfolio_id":"<portfolio-id>","program_id":"<program-id>"}}
{"tool":"mcp__pms__create_project","input":{"name":"Web Store v5","description":"UI project","org_id":"<org-id>","portfolio_id":"<portfolio-id>","program_id":"<program-id>"}}

{"tool":"mcp__pms__create_goal","input":{"name":"Ship Checkout API v2","project_id":"<project-id-api>"}}
{"tool":"mcp__pms__create_goal","input":{"name":"Ship Web Store v5","project_id":"<project-id-ui>"}}

{"tool":"mcp__pms__create_task","input":{"project":"<project-id-api>","title":"Implement payment endpoint"}}
{"tool":"mcp__pms__create_task","input":{"project":"<project-id-ui>","title":"Checkout UI integration"}}

{"tool":"mcp__pms__list_tasks","input":{"project":"<project-id-api>"}}
{"tool":"mcp__pms__list_tasks","input":{"project":"<project-id-ui>"}}
{"tool":"mcp__pms__add_task_dependency","input":{"task_id":"<task-id-ui>","depends_on_id":"<task-id-api>","dependency_type":"blocks"}}
{"tool":"mcp__pms__get_task_tree","input":{"project":"<project-id-ui>"}}

{"tool":"mcp__pms__update_program","input":{"program_id":"<program-id>","goal_ids":"<goal-id-api>,<goal-id-ui>","objective_ids":"<objective-id-api>,<objective-id-ui>"}}
{"tool":"mcp__pms__update_portfolio","input":{"portfolio_id":"<portfolio-id>","goal_ids":"<goal-id-api>,<goal-id-ui>","objective_ids":"<objective-id-api>,<objective-id-ui>"}}

{"tool":"mcp__pms__get_program_summary","input":{"program_id":"<program-id>"}}
{"tool":"mcp__pms__get_portfolio_summary","input":{"portfolio_id":"<portfolio-id>"}}
{"tool":"mcp__pms__get_program_dashboard","input":{"org_id":"<org-id>","portfolio_id":"<portfolio-id>"}}
{"tool":"mcp__pms__get_portfolio_dashboard","input":{"org_id":"<org-id>"}}
```

---

## Automation + Custom Fields + Comments

Use custom fields to encode metadata, comments to capture context, and
automation rules to keep workflows moving without manual intervention.

```bash
uv run pms custom-field create risk_level --entity-type task --type enum \
  --option low --option medium --option high
uv run pms custom-field value set risk_level --entity-type task --entity-id <task_id> --value high --created-by automation

uv run pms comment add task <task_id> "Blocked on ops approval" --by alice --mention ops-team --watch
uv run pms watcher add task <task_id> alice

uv run pms automation rule create "comment-on-done" task.completed add_comment \
  --action-payload-json '{"body":"Automation: task completed.","created_by":"automation"}'

uv run pms automation run --event-id <event_id> --dry-run
```

MCP tool call version:

```json
{"tool":"mcp__pms__create_custom_field","input":{"name":"risk_level","entity_type":"task","field_type":"select","options":"low,medium,high"}}
{"tool":"mcp__pms__set_custom_field_value","input":{"field_ref":"risk_level","entity_type":"task","entity_id":"<task-id>","value":"high","created_by":"automation"}}
{"tool":"mcp__pms__add_comment","input":{"entity_type":"task","entity_id":"<task-id>","body":"Blocked on ops approval","created_by":"alice","mentions":"ops-team","watch":true}}
{"tool":"mcp__pms__add_watcher","input":{"entity_type":"task","entity_id":"<task-id>","watcher":"alice"}}
{"tool":"mcp__pms__create_automation_rule","input":{"name":"comment-on-done","event_pattern":"task.completed","action_type":"add_comment","action_payload_json":"{\"body\":\"Automation: task completed.\",\"created_by\":\"automation\"}"}}
{"tool":"mcp__pms__run_automation_rules","input":{"event_id":"<event-id>","dry_run":true}}
```
