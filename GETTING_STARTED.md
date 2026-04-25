# PMS - Getting Started Guide

**From Zero to Maximum Usage: A Complete Walkthrough**

PMS (Project Management System) is a self-evolving, autonomous development platform that bridges the gap between AI assistants and persistent project state. Unlike traditional project management tools, PMS is designed to be operated _by_ AI agents while remaining fully accessible to humans.

---

## Table of Contents

1. [What is PMS?](#what-is-pms)
2. [Installation](#installation)
3. [Automated Zero-to-Go](#automated-zero-to-go)
4. [First-Time Setup](#first-time-setup)
5. [Adding PMS as an MCP Server](#adding-pms-as-an-mcp-server)
6. [How AI Tools Use PMS](#how-ai-tools-use-pms)
7. [Core Workflow Patterns](#core-workflow-patterns)
8. [Feature Reference](#feature-reference)
9. [Generating Reports](#generating-reports)
10. [Tracking Usage & Metrics](#tracking-usage--metrics)
11. [Remote Operations & AWS](#remote-operations--aws)
12. [Advanced: Plugins & Automation](#advanced-plugins--automation)
13. [Why PMS vs Fragmented Approaches](#why-pms-vs-fragmented-approaches)

---

## What is PMS?

PMS is a **persistent state layer** for AI-assisted development. It solves a fundamental problem: AI assistants have no memory between sessions, making it impossible to track projects, tasks, decisions, and progress over time.

### The Problem with Fragmented Workflows

```
Traditional AI + Project Management:
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Claude/GPT     │     │   Jira/Linear   │     │   Your Brain    │
│  (No Memory)    │────▶│  (Manual Entry) │────▶│  (Context Lost) │
└─────────────────┘     └─────────────────┘     └─────────────────┘
       ▲                        │
       │    Copy/Paste Loop     │
       └────────────────────────┘
```

### The PMS Solution

```
PMS Architecture:
┌─────────────────────────────────────────────────────────────────┐
│                        Claude Code / AI Agent                   │
│   ┌──────────────────────────────────────────────────────────┐  │
│   │                    MCP Protocol Layer                    │  │
│   │  Live tool surface: projects, tasks, goals, plans, MCP...│  │
│   └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                          PMS Server                             │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌──────────┐   │
│  │  Projects  │  │   Tasks    │  │   Memory   │  │ Learning │   │
│  │  Service   │  │  Service   │  │   System   │  │  Engine  │   │
│  └────────────┘  └────────────┘  └────────────┘  └──────────┘   │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌──────────┐   │
│  │   Remote   │  │    AWS     │  │  Plugins   │  │ Automaton│   │
│  │  Service   │  │  Service   │  │   System   │  │ Workflow │   │
│  └────────────┘  └────────────┘  └────────────┘  └──────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     SQLite + Event Store                        │
│  Persistent • Event-Sourced • Auditable • Time-Travel Queries   │
└─────────────────────────────────────────────────────────────────┘
```

**Key Benefits:**

- AI agents can create, track, and complete tasks across sessions
- Full audit trail with event sourcing (never lose data)
- Project state persists forever, not just in one conversation
- Remote operations (SSH, rsync, AWS spot instances)
- Learning from patterns and outcomes
- Plugin system for extensibility

---

## Installation

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager (recommended)

### Quick Install

```bash
# Clone the repository
git clone https://github.com/mattsta/pms
cd pms

# Install with uv (recommended)
uv sync

# Verify installation
uv run pms version
```

### Optional Dependencies

```bash
# For AWS spot instance support
uv add boto3 boto3-stubs[ec2]

# For advanced features
uv add anthropic  # Claude Agent SDK
```

---

## Automated Zero-to-Go

Use these scripts when you want a ready-to-use PMS workflow immediately:

```bash
./scripts/run_demo_smoke.sh
```

Production-like onboarding (`drop in -> start -> go -> extend -> grow`):

```bash
./scripts/run_dropin_start_go_extend_grow.sh
```

Run the same flow plus strict artifact-contract verification:

```bash
./scripts/run_dropin_contract_smoke.sh
```

Cross-team handoff flow (`build -> release`) for practical rollout validation:

```bash
./scripts/run_team_handoff_flow.sh
```

Run the same handoff flow plus strict artifact-contract verification:

```bash
./scripts/run_team_handoff_contract_smoke.sh
```

Incident response flow (`triage -> mitigation -> comms -> postmortem`):

```bash
./scripts/run_incident_response_flow.sh
```

Run the same incident flow plus strict artifact-contract verification:

```bash
./scripts/run_incident_response_contract_smoke.sh
```

User-centric bootstrap + observability validation (`start -> go -> observe`):

```bash
./scripts/run_user_start_go_observe_flow.sh
```

Run the same user flow plus strict artifact-contract verification:

```bash
./scripts/run_user_start_go_observe_contract_smoke.sh
```

Recurring operational review validation (`review -> decide -> continue`):

```bash
./scripts/run_operational_review_flow.sh
```

Run the same operational-review flow plus strict artifact-contract verification:

```bash
./scripts/run_operational_review_contract_smoke.sh
```

Backlog triage + prioritization validation (`prioritize -> de-duplicate -> continue`):

```bash
./scripts/run_backlog_triage_flow.sh
```

Run the same backlog-triage flow plus strict artifact-contract verification:

```bash
./scripts/run_backlog_triage_contract_smoke.sh
```

Multi-project portfolio steering validation (`roll up -> inspect -> coordinate`):

```bash
./scripts/run_portfolio_steering_flow.sh
```

Run the same portfolio-steering flow plus strict artifact-contract verification:

```bash
./scripts/run_portfolio_steering_contract_smoke.sh
```

Agent-driven execution-loop validation (`plan -> loop -> prove -> close`):

```bash
./scripts/run_agent_execution_loop_flow.sh
```

Run the same agent-loop flow plus strict artifact-contract verification:

```bash
./scripts/run_agent_execution_loop_contract_smoke.sh
```

Broader audit pass (smoke + parity + tests):

```bash
./scripts/run_audit_checks.sh
```

Use `examples/real_world/dropin.env.example` and
`examples/real_world/team_handoff.env.example` and
`examples/real_world/incident_response.env.example` and
`examples/real_world/user_start_go_observe.env.example` and
`examples/real_world/operational_review.env.example` and
`examples/real_world/backlog_triage.env.example` and
`examples/real_world/portfolio_steering.env.example` and
`examples/real_world/agent_execution_loop.env.example` and
`examples/real_world/release_readiness.env.example` as editable starter values.

See `docs/IMMEDIATE_START_GO.md`, `examples/real_world/README.md`,
`docs/DOCUMENTATION_MAP.md`, and `docs/CAPABILITIES_REFERENCE.md`
for the live onboarding, scenario, navigation, and feature-reference paths.

---

## First-Time Setup

This section is the practical onboarding path. Each step should tell you:

- what PMS is for at this stage
- the fastest command to run
- which local artifacts/state it creates
- what to do next

### 1. Initialize the Database

```bash
# Initialize PMS (creates ~/.pms/ directory and database)
uv run pms init

# Show immediate "what comes next" guidance from live state
uv run pms start
```

This creates:

- `~/.pms/pms.db` - SQLite database
- `~/.pms/knowledge/` - Knowledge store
- `~/.pms/patterns/` - Learned patterns
- `~/.pms/plugins/` - Plugin directory

What `uv run pms start` itself does:

- purpose: practical start -> go entry point for discovering live state, fastest first action, and where to extend next
- creates: no new state; it is a read-only control-plane entry surface
- returns: live counts, current focus task, observability paths, scenario paths, and exact next commands
- use it when: you are not sure whether to bootstrap, inspect, continue active work, or jump into a real-world scenario

What to do next:

- run `uv run pms start` to see the live control plane
- run `uv run pms quickstart --defaults` to create a usable starter workspace
- run `uv run pms quickstart --defaults --format json` when another tool or agent needs the created IDs and next steps back as structured output
- repeating `uv run pms quickstart --defaults` reuses the generated bootstrap plan/tasks instead of piling up duplicate live quickstart plans
- run `uv run pms config show --format json` to confirm you are pointed at the correct state
- if `uv run pms start` shows a `focus_task`, follow its first `next_steps` command before creating new work

### 2. Custom Data Location (Optional)

You can place `PMS_*` values in a local `.env` file and skip exporting them
every shell session.

```bash
# Use a custom data directory
export PMS_DATA_DIR=/path/to/your/data
uv run pms init

# Or use a specific database path
export PMS_DATABASE_PATH=/path/to/pms.db

# Or place logs in a custom directory
export PMS_LOG_DIR=/path/to/your/data/logs
```

Check exactly which state you are about to use:

```bash
uv run pms config show
uv run pms config show --format json
```

If you expect multiple shells, agents, or automations to write at once, prefer
starting a local PMS API process and recording that runtime mode:

```bash
uv run pms runtime prefer-server --host 127.0.0.1 --port 8000
```

That command:

- starts or reuses the local PMS API server
- recovers `.pms-admin-key` if needed
- persists `prefer_server` into workspace config
- optionally installs `./.bin/pms-client`

Architecture and fallback details:

- `docs/WRITE_COORDINATION_ARCHITECTURE.md`

If you want the preferred fast server-backed binary path for repeated reads and reports:

```bash
./scripts/install_pms_client.sh
export PATH="$PWD/.bin:$PATH"
export PMS_API_KEY="$(cat .pms-admin-key)"
pms-client task list --project "<project-name>"
```

For safe experimentation, create a scratch PMS root instead of reusing your
live workspace database:

```bash
uv run pms init --data-dir ./.pms-scratch
PMS_DATA_DIR=$PWD/.pms-scratch PMS_DATABASE_PATH=$PWD/.pms-scratch/pms.db \
  uv run pms quickstart --defaults
```

This keeps demos, contract smokes, and manual experiments isolated from the
state you care about.

### 3. Create an Organization + Portfolio (Optional)

```bash
# Create an organization
uv run pms org create "Acme Org" \
  --owner owner@example.com \
  --member owner@example.com

# Create a team under the org
uv run pms team create "Core Team" \
  --org-id org_123 \
  --owner lead@example.com

# Create a portfolio and program (group projects/goals)
uv run pms portfolio create "Platform Portfolio" \
  --org-id org_123

uv run pms program create "Delivery Program" \
  --org-id org_123 \
  --portfolio-id portfolio_123
```

### 4. Create Your First Project

```bash
# Create a project
uv run pms project create "My First Project" \
  --description "Learning how PMS works" \
  --tag "tutorial" \
  --tag "learning"

# Verify it was created
uv run pms project list
```

### 5. Add Some Tasks

```bash
# Get your project ID
PROJECT_ID=$(uv run pms project list -f json | jq -r '.[0].id')

# Add tasks
uv run pms task add "$PROJECT_ID" "Set up development environment" \
  --priority high \
  --hours 2

uv run pms task add "$PROJECT_ID" "Read the documentation" \
  --priority medium \
  --hours 1

uv run pms task add "$PROJECT_ID" "Build first feature" \
  --priority high \
  --hours 4

# View tasks
uv run pms task list --project "$PROJECT_ID"
uv run pms task list --project "$PROJECT_ID" --format json --view overview

# Find ready or stale tasks
uv run pms task ready --project "$PROJECT_ID"
uv run pms task stale --days 14
```

#### Optional: Add labels + workflow gates

Labels are structured (distinct from free-form tags) and can gate workflow transitions.

```bash
# Create a category and label
uv run pms label category create "Risk" --exclusive
uv run pms label create "needs-review" --category-id <CATEGORY_ID>

# Assign to a task
uv run pms label assign task <TASK_ID> needs-review

# Require the label before moving to unit testing
uv run pms label gate add \
  --workflow-id wf_sdlc \
  --entity-type task \
  --from-state code_review \
  --to-state unit_testing \
  --rule-type require_label \
  --label needs-review
```

### 6. Add Goals, Objectives, and Key Results

```bash
# Create a short-term goal
uv run pms goal create "Launch V1" --horizon short_term -d "Ship core capabilities"

# Create an objective under the goal (replace goal ID)
uv run pms objective create --goal-id goal_123 "Complete onboarding flow"

# Create a key result under the objective (replace objective ID)
uv run pms keyresult create --objective-id obj_123 "Activation rate" --current 35 --target 60 --unit "%"

# View goal rollup summary
uv run pms goal summary goal_123
```

### 7. Create a Plan Artifact

```bash
# Create a plan linked to the project (JSON format)
uv run pms plan create "Release Plan" \
  --project-id "$PROJECT_ID" \
  --format json \
  --content '{"stages":["plan","implement","test"]}'

# List plans for the project
uv run pms plan list --project-id "$PROJECT_ID"
```

### 8. Work Through Tasks

```bash
# Start a task
uv run pms task start <task_id>

# Or start by title (scoped to a project)
uv run pms task start "Build first feature" --project "$PROJECT_ID"

# Resolve a title to its ID (handy for scripts)
uv run pms task resolve "Build first feature" --project "$PROJECT_ID" --format json

# Show or visualize tasks by title (scoped to a project)
uv run pms task show "Build first feature" --project "$PROJECT_ID" --format json
uv run pms task timeline "Build first feature" --project "$PROJECT_ID" --format table
uv run pms task graph "Build first feature" --project "$PROJECT_ID" --format text

# Deep trace view with history + linked items (JSON export)
uv run pms task show "Build first feature" --project "$PROJECT_ID" \
  --view trace --include-linked-history --format json

# Attach manual evidence
uv run pms task evidence add <task_id> scm_commit abc123 --description "Manual commit"
# Or attach by title (scoped to a project)
uv run pms task evidence add "Build first feature" scm_commit abc123 \
  --project "$PROJECT_ID" --description "Manual commit"

# Run local tests and attach results
uv run pms test run . -c "pytest -v" --task-id <task_id>

# Complete it when done
uv run pms task complete <task_id> --hours 1.5

# Or complete by title (scoped to a project)
uv run pms task complete "Build first feature" --project "$PROJECT_ID" --hours 1.5

# View progress
uv run pms dashboard

# Project trace export with linked tasks and history
uv run pms project show "User Profile Feature" \
  --view trace --include-linked-history --format json
```

### Daily Review Export

```bash
# Export a daily review and attach evidence to the most recent task
uv run pms work daily \
  --scope-type project \
  --scope "$PROJECT_ID" \
  --include-timeline \
  --export ./reports \
  --attach-strategy recent
```

---

## Adding PMS as an MCP Server

The real power of PMS comes when AI tools can use it directly. Here's how to add it to Claude Code or other MCP-compatible tools.

If you want maintained guidance for stop hooks, session-end audit dumps, and
wrapper automation around common agent harnesses, use
[`docs/AGENT_INTEGRATION_GUIDE.md`](docs/AGENT_INTEGRATION_GUIDE.md).

### Method 1: Automatic Installation

```bash
# Install MCP server configuration
uv run pms install

# Verify installation
uv run pms verify-install
```

### Method 2: Manual Configuration

Add to your Claude Code MCP settings (`~/.config/claude-code/mcp.json` or similar):

```json
{
  "mcpServers": {
    "pms": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/path/to/pms",
        "python",
        "-m",
        "pms.tools.server"
      ],
      "env": {
        "PMS_DATA_DIR": "/path/to/your/data"
      }
    }
  }
}
```

### Method 3: Project-Local Configuration

Create `.mcp.json` in your project root:

```json
{
  "mcpServers": {
    "pms": {
      "command": "uv",
      "args": ["run", "python", "-m", "pms.tools.server"]
    }
  }
}
```

### Verify MCP Integration

Once configured, the AI tool should see 31 new tools:

```
Core Tools (always loaded):
  - create_project, list_projects, get_project, get_dashboard
  - create_task, list_tasks, start_task, complete_task

Extended Tools (loaded on demand via Tool Search):
  - update_project, delete_project, archive_project
  - update_task, delete_task, block_task, unblock_task
  - add_task_dependency, get_task_tree, bulk_create_tasks
  - list_remote_hosts, execute_remote_command, sync_push, sync_pull
  - find_spot_instances, launch_test_server, run_tests_on_server
  ... and more
```

---

## How AI Tools Use PMS

When you use Claude Code with PMS installed, the interaction becomes stateful:

### Example Conversation Flow

**Session 1 (Monday morning):**

```
You: Let's start the authentication feature for the webapp

Claude: I'll create a project and tasks to track this work.
        [Uses create_project tool]
        [Uses create_task tool x3]

        Created project "Webapp Authentication" with tasks:
        1. Design auth flow (2h) - high priority
        2. Implement JWT tokens (4h) - high priority
        3. Add login UI (3h) - medium priority
        4. Write tests (2h) - high priority

        Starting on "Design auth flow"...
        [Uses start_task tool]
```

**Session 2 (Monday afternoon, different conversation):**

```
You: What was I working on?

Claude: [Uses get_dashboard tool]

        You're working on "Webapp Authentication":
        - "Design auth flow" is IN PROGRESS (started 3 hours ago)
        - 3 tasks pending
        - 0% complete

        Should I continue with the auth flow design?
```

**Session 3 (Tuesday):**

```
You: I finished the auth design yesterday, let's implement JWT

Claude: [Uses complete_task tool for "Design auth flow"]
        [Uses start_task tool for "Implement JWT tokens"]

        Marked "Design auth flow" complete (actual: 2.5h).
        Now working on "Implement JWT tokens"...
```

### What the AI Can Do Automatically

1. **Track Progress**: Start/complete tasks as work happens
2. **Maintain Context**: Remember decisions, blockers, and dependencies
3. **Generate Reports**: Pull project status at any time
4. **Remote Operations**: Push code to servers, run tests remotely
5. **Learn Patterns**: Remember what worked for future projects

---

## Core Workflow Patterns

### Pattern 1: Feature Development

```bash
# 1. Create project for feature
uv run pms project create "User Profile Feature" --tag "frontend" --tag "q1-2025"

# 2. Break down into tasks
uv run pms task add <proj_id> "Design profile page mockup" --priority high --hours 4
uv run pms task add <proj_id> "Implement profile API endpoints" --priority high --hours 6
uv run pms task add <proj_id> "Build profile UI components" --priority medium --hours 8
uv run pms task add <proj_id> "Add profile edit functionality" --priority medium --hours 4
uv run pms task add <proj_id> "Write integration tests" --priority high --hours 3

# 3. Work through tasks (AI or manual)
uv run pms task start <task_id>
# ... do the work ...
uv run pms task complete <task_id> --hours 5

# 4. Check progress
uv run pms dashboard
```

### Pattern 2: Bug Triage

```bash
# Create project for bug backlog
uv run pms project create "Bug Triage - Sprint 42" --tag "bugs" --tag "sprint-42"

# Add bugs with priority
uv run pms task add <proj_id> "Fix login timeout" --priority critical
uv run pms task add <proj_id> "Resolve memory leak in worker" --priority high
uv run pms task add <proj_id> "UI alignment issue on mobile" --priority low

# Block a task if waiting on something
uv run pms task block <task_id> --reason "Waiting for database team to provide access"
# Or block by title (scoped to a project)
uv run pms task block "Fix login timeout" --project "Bug Triage - Sprint 42" \
  --reason "Waiting for database team to provide access"

# Unblock and continue
uv run pms task unblock <task_id>
# Or unblock by title (scoped to a project)
uv run pms task unblock "Fix login timeout" --project "Bug Triage - Sprint 42"
```

### Pattern 3: Remote Testing

```bash
# Add a remote server
uv run pms remote add production \
  --host prod.example.com \
  --username deploy \
  --key ~/.ssh/prod_key \
  --tag "production"

# Sync code to remote
uv run pms remote sync push production ./src /var/www/app

# Run tests remotely
uv run pms remote exec production "cd /var/www/app && npm test"
```

### Pattern 4: AWS Spot Instances for Testing

```bash
# Find cheap spot instances
uv run pms aws spot find --vcpus 4 --memory 8 --max-price 0.10

# Launch a test server
uv run pms aws server launch test-runner \
  --instance-type c5.xlarge \
  --max-hours 2

# Run tests on spot instance
uv run pms aws test run <server_id> ./my-project \
  --command "npm test" \
  --workdir . \
  --exclude .venv \
  --env NODE_ENV=test

# Clean up
uv run pms aws server terminate <server_id>
```

---

## Feature Reference

### Project Management

| Command                     | Description          |
| --------------------------- | -------------------- |
| `pms project create <name>` | Create new project   |
| `pms project list`          | List all projects    |
| `pms project show <id>`     | Show project details |
| `pms project history <id>`  | View audit trail     |
| `pms project update <id>`   | Update project       |
| `pms project delete <id>`   | Delete project       |

### Organization Management

| Command                       | Description               |
| ----------------------------- | ------------------------- |
| `pms org create <name>`       | Create organization       |
| `pms org list`                | List organizations        |
| `pms org show <id>`           | Show organization details |
| `pms org update <id>`         | Update organization       |
| `pms org summary <id>`        | Org rollup summary        |
| `pms team create <name>`      | Create team               |
| `pms team list`               | List teams                |
| `pms team show <id>`          | Show team details         |
| `pms team update <id>`        | Update team               |
| `pms portfolio create <name>` | Create portfolio          |
| `pms portfolio list`          | List portfolios           |
| `pms portfolio show <id>`     | Show portfolio details    |
| `pms portfolio summary <id>`  | Portfolio rollup summary  |
| `pms program create <name>`   | Create program            |
| `pms program list`            | List programs             |
| `pms program show <id>`       | Show program details      |
| `pms program summary <id>`    | Program rollup summary    |

### Task Management

| Command                       | Description            |
| ----------------------------- | ---------------------- |
| `pms task add <proj> <title>` | Add task to project    |
| `pms task list`               | List tasks             |
| `pms task show <id>`          | Show task details      |
| `pms task start <id>`         | Start working on task  |
| `pms task complete <id>`      | Mark task done         |
| `pms task block <id>`         | Block task with reason |
| `pms task unblock <id>`       | Unblock task           |
| `pms task update <id>`        | Update task            |
| `pms task delete <id>`        | Delete task            |

Tip: `task start/complete/block/unblock/delete/review/reopen` also accept a task title
when you provide `--project <name|id>`.

### Remote Operations

| Command                        | Description          |
| ------------------------------ | -------------------- |
| `pms remote add <name>`        | Configure SSH host   |
| `pms remote list`              | List hosts           |
| `pms remote test <name>`       | Test connection      |
| `pms remote exec <name> <cmd>` | Run command          |
| `pms remote sync push`         | Push files via rsync |
| `pms remote sync pull`         | Pull files via rsync |

### Local Test Operations

| Command         | Description              |
| --------------- | ------------------------ |
| `pms test run`  | Run local tests + record |
| `pms test list` | List recorded test runs  |
| `pms test show` | Show a recorded test run |

### AWS Operations

| Command                    | Description          |
| -------------------------- | -------------------- |
| `pms aws spot find`        | Find cheap instances |
| `pms aws server launch`    | Start spot instance  |
| `pms aws server list`      | List active servers  |
| `pms aws server terminate` | Stop server          |
| `pms aws test run`         | Sync + run tests     |
| `pms aws logs`             | Tail remote logs     |

### System & Discovery

| Command                   | Description        |
| ------------------------- | ------------------ |
| `pms dashboard`           | Overall status     |
| `pms capabilities list`   | List all features  |
| `pms capabilities docs`   | Generate docs      |
| `pms capabilities health` | Health check       |
| `pms namespace list`      | List ID namespaces |
| `pms plugin list`         | List plugins       |

---

## Generating Reports

PMS supports multiple export formats for historical documentation and analysis.

### Quick Status Reports

```bash
# Dashboard view
uv run pms dashboard

# Project summary with stats
uv run pms project show <id> --verbose
```

### JSON Export (for processing)

```bash
# Export all projects
uv run pms project list -f json > projects.json

# Export all tasks for a project
uv run pms task list --project <id> -f json > tasks.json
```

### Report Generation

```bash
# Generate comprehensive project report
uv run pms report project <project_id> --format markdown > project_report.md
uv run pms report project <project_id> --format html > project_report.html

# Generate historical report (last 30 days)
uv run pms report history --days 30 --format markdown > monthly_report.md

# Export metrics and analytics
uv run pms report metrics --project <id> --format csv > metrics.csv
```

### System Documentation

```bash
# Generate full system documentation
uv run pms capabilities docs --format markdown > SYSTEM_DOCS.md

# Export system schema (for integrations)
uv run pms capabilities schema > schema.json
```

### Audit Trail Export

```bash
# Export project history (event-sourced audit log)
uv run pms project history <id> -f json > audit_trail.json

# Get state at specific point in time
uv run pms project show <id> --revision 5
```

---

## Tracking Usage & Metrics

### Built-in Metrics

PMS automatically tracks:

- **Task Metrics**: Actual hours and completion rates
- **Project Health**: Based on blocked tasks, overdue items, velocity
- **Session Metrics**: API costs, token usage (when using agents)
- **Operation Timing**: Performance metrics for all operations

### Viewing Metrics

```bash
# Dashboard shows key metrics
uv run pms dashboard

# Project summary with health score
uv run pms project show <id> --verbose

# Example output:
#   Health Score: 85/100
#   Completion: 60% (6/10 tasks)
#   Actual: 18h
#   Blocked: 1 task
#   Overdue: 0 tasks
```

### Metrics Export

```bash
# Export metrics for analysis
uv run pms report metrics --format csv > metrics.csv

# Fields include:
#   project_id, task_count, completed_count, blocked_count
#   actual_hours, health_score
#   created_at, updated_at
```

### AI Session Tracking

When using the Claude Agent SDK:

```bash
# Run agent with tracking
uv run pms run "Create a new feature for user settings"

# Session data stored includes:
#   - Token usage per message
#   - Cost per session
#   - Context summary
#   - Decision history
```

Use saved context to prime agent runs, or compact it between sessions:

```bash
uv run pms context show
uv run pms run --no-prime-context "List all blocked tasks"
uv run pms context compact --reason "weekly-reset"
```

---

## Remote Operations & AWS

### SSH Remote Hosts

```bash
# Add development server
uv run pms remote add dev-server \
  --host dev.example.com \
  --username developer \
  --key ~/.ssh/dev_key \
  --path /home/developer/projects \
  --tag "development"

# Add production server
uv run pms remote add prod-server \
  --host prod.example.com \
  --username deploy \
  --key ~/.ssh/prod_key \
  --tag "production"

# List all servers
uv run pms remote list

# Test connectivity
uv run pms remote test dev-server
```

### File Synchronization

```bash
# Push local changes to remote
uv run pms remote sync push dev-server ./src /home/developer/project/src

# With exclusions
uv run pms remote sync push dev-server . /home/developer/project \
  --exclude "*.log" \
  --exclude "node_modules"

# Dry run first
uv run pms remote sync push dev-server . /remote/path --dry-run

# Pull from remote
uv run pms remote sync pull dev-server /remote/logs ./local-logs
```

### AWS Spot Instances

```bash
# Find cost-effective instances
uv run pms aws spot find \
  --vcpus 4 \
  --memory 16 \
  --max-price 0.15 \
  --region us-east-1

# Launch a test server
uv run pms aws server launch my-test-server \
  --instance-type c5.xlarge \
  --region us-east-1 \
  --max-hours 4 \
  --docker  # Pre-install Docker

# List running servers
uv run pms aws server list

# Run tests on server
uv run pms aws test run <server_id> ./my-project \
  --command "pytest tests/ -v" \
  --setup "pip install -r requirements.txt" \
  --workdir . \
  --exclude .venv \
  --env PYTHONUNBUFFERED=1

# View logs
uv run pms aws logs <server_id> --follow

# Terminate when done
uv run pms aws server terminate <server_id>

# Terminate all (cleanup)
uv run pms aws server terminate-all
```

---

## Advanced: Plugins & Automation

### Plugin System

```bash
# List available plugins
uv run pms plugin list

# Discover plugins in directory
uv run pms plugin discover ~/.pms/plugins

# Start a plugin
uv run pms plugin start my-plugin

# View plugin tools
uv run pms plugin tools --plugin my-plugin

# Call plugin tool directly
uv run pms plugin call my-plugin.my_tool '{"arg": "value"}'
```

### Creating Plugins

Create `~/.pms/plugins/my-plugin/plugin.json`:

```json
{
  "name": "my-plugin",
  "version": "1.0.0",
  "description": "My custom PMS plugin",
  "tools": [
    {
      "name": "my_tool",
      "description": "Does something useful",
      "parameters": {
        "type": "object",
        "properties": {
          "input": { "type": "string" }
        }
      }
    }
  ]
}
```

### Automation & Workflows

PMS includes an event-driven automation system:

```python
# Example workflow definition
from pms.automation.workflows import workflow, parallel

@workflow("deploy-and-test")
async def deploy_and_test(ctx):
    # Parallel deployment
    with parallel():
        await ctx.run("sync-to-staging")
        await ctx.run("prepare-test-data")

    # Sequential testing
    await ctx.run("run-integration-tests")
    await ctx.run("run-e2e-tests")

    # Approval gate
    with ctx.approval("qa-team"):
        await ctx.run("deploy-to-production")
```

### Event Triggers

```python
# Trigger on task completion
from pms.automation.triggers import on_event

@on_event("task.completed")
async def notify_on_completion(event):
    task = event.data
    if task.priority == "critical":
        await send_notification(f"Critical task completed: {task.title}")
```

---

## Why PMS vs Fragmented Approaches

### Problem 1: AI Has No Memory

**Legacy:** Every Claude conversation starts fresh. You re-explain context every time.

**PMS:** Context persists in the database. Ask "what was I working on?" and get a real answer.

### Problem 2: Manual Project Updates

**Legacy:** You finish coding, then manually update Jira/Linear/Notion.

**PMS:** AI automatically tracks task progress as you work. Completion is captured in real-time.

### Problem 3: Lost Decisions

**Legacy:** "Why did we choose PostgreSQL?" - lost in Slack history somewhere.

**PMS:** Decisions stored in project history with full audit trail. Event sourcing means nothing is ever lost.

### Problem 4: Context Switching Cost

**Legacy:** Switch projects, spend 15 minutes re-reading where you left off.

**PMS:** `pms dashboard` shows all active work. AI can instantly resume any project.

### Problem 5: Remote Operations are Manual

**Legacy:** SSH into server, manually run commands, copy-paste results.

**PMS:** `pms remote exec` or let AI handle it. Results captured and logged.

### Problem 6: No Learning Across Sessions

**Legacy:** Make the same mistakes repeatedly. No institutional memory.

**PMS:** Learning engine captures patterns. "Last time we did X, Y happened."

### Comparison Table

| Capability                 | Legacy (Jira + Claude) | PMS                          |
| -------------------------- | ---------------------- | ---------------------------- |
| AI can create tasks        | No (manual)            | Yes (maintained MCP surface) |
| AI can track progress      | No                     | Yes (automatic)              |
| Persistent across sessions | No (re-explain)        | Yes (database)               |
| Audit trail                | Limited                | Full event sourcing          |
| Remote operations          | Manual SSH             | Integrated                   |
| AWS spot testing           | Custom scripts         | Built-in                     |
| Learning from patterns     | None                   | Learning engine              |
| Plugin extensibility       | None                   | Full plugin system           |
| Self-documenting           | No                     | Introspection API            |
| Report generation          | Manual export          | Automated                    |

---

## Quick Reference Card

```bash
# Initialize
uv run pms init

# Project CRUD
uv run pms project create "Name" -d "Description" -t tag1 -t tag2
uv run pms project list
uv run pms project show <id>
uv run pms project delete <id>

# Task CRUD
uv run pms task add <proj> "Title" --priority high --hours 4
uv run pms task list --project <proj>
uv run pms task start <id>
uv run pms task complete <id> --hours 3.5
uv run pms task block <id> "Reason"

# Remote
uv run pms remote add name --host x --user y --key z
uv run pms remote exec name "command"
uv run pms remote sync push name ./local /remote

# AWS
uv run pms aws spot find --vcpus 4 --memory 8
uv run pms aws server launch name --type c5.large
uv run pms aws test run <server> --command "pytest"
uv run pms aws server terminate-all

# Reports
uv run pms dashboard
uv run pms report project <id> --format markdown
uv run pms project list -f json

# System
uv run pms capabilities docs
uv run pms capabilities health
uv run pms verify-install
```

---

## Next Steps

1. **Install PMS** and run through the first-time setup
2. **Add as MCP server** to your AI tool
3. **Create your first project** with tasks
4. **Let AI track progress** as you work
5. **Export reports** for stakeholders
6. **Explore plugins** for customization

For detailed API documentation, run:

```bash
uv run pms capabilities docs --format markdown
```

For help:

```bash
uv run pms --help
uv run pms <command> --help
```

---

_PMS - Making AI-assisted development stateful, traceable, and continuously improving._
