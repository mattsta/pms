---
name: pms-platform
description: Use when working in a repository that uses PMS as the source of truth for creating and managing organizations, products, projects, goals, objectives, key results, plans, tasks, reviews, and agent automation. This skill provides direct copy-paste PMS workflows for bootstrapping a workspace, building the execution graph, running work, reviewing status, and wiring agent hooks.
---

# PMS Platform

Use this skill when PMS is not just a task viewer, but the system used to create
and manage the actual project graph.

Examples below use `uv run pms` because they are directly runnable from a source
checkout.

## Core rule

Do not make the user reassemble PMS commands from multiple docs. Start from one
of the runnable flows below and adapt the names.

## 1. Fast bootstrap

If the workspace is empty and the user needs a real graph immediately:

```bash
uv run pms init
uv run pms quickstart --defaults --format json
uv run pms start --format json
uv run pms dashboard --format json
```

Use this when speed matters more than custom structure.

## 2. Manual bootstrap: create the graph from zero

If the user wants a real custom workspace, create the graph in this order.

### 2a. Create the actor

```bash
uv run pms actor create "Matt" --kind human --handle matt --format json
uv run pms config set --current-actor matt
uv run pms actor show me --format json
```

### 2b. Create the container entities

```bash
uv run pms org create "Acme Org" --owner matt --member matt --format json
uv run pms product create "Gateway Platform" --owner matt --format json
uv run pms project create "Gateway Launch" \
  -d "Release control for the public API launch" \
  --product "Gateway Platform" \
  --format json
```

### 2c. Create the strategy graph

```bash
uv run pms goal create "Ship Gateway v1" \
  --project "Gateway Launch" \
  --horizon short_term \
  --owner matt \
  --format json

uv run pms objective create "Stabilize launch flow" \
  --goal "Ship Gateway v1" \
  --owner matt \
  --format json

uv run pms keyresult create "Launch checklist completion" \
  --objective "Stabilize launch flow" \
  --current 0 \
  --target 100 \
  --unit percent \
  --owner matt \
  --format json
```

### 2d. Create the plan

```bash
uv run pms plan create "Gateway Launch Plan" \
  --project "Gateway Launch" \
  --goal "Ship Gateway v1" \
  --format yaml \
  --content $'phases:\n  - name: prep\n  - name: launch\n  - name: followup\n' \
  --output-format json
```

### 2e. Create the execution tasks

```bash
uv run pms task create "Gateway Launch" "Publish release notes" --format json
uv run pms task create "Gateway Launch" "Run smoke tests" --format json
uv run pms task create "Gateway Launch" "Approve rollout" --format json
```

### 2f. Link tasks to the plan

```bash
uv run pms plan update "Gateway Launch Plan" \
  --project "Gateway Launch" \
  --task "Publish release notes" \
  --task "Run smoke tests" \
  --task "Approve rollout"
```

### 2g. Read the graph back

```bash
uv run pms project show "Gateway Launch" --format json
uv run pms goal summary "Ship Gateway v1" --format json
uv run pms plan show "Gateway Launch Plan" --project "Gateway Launch" --format json
uv run pms task list --project "Gateway Launch" --format json
```

## 3. Daily execution loop

Once the graph exists, use this loop:

```bash
uv run pms task ready --project "Gateway Launch" --format json
uv run pms task start "Publish release notes" --project "Gateway Launch" --by matt --format json
uv run pms task progress "Publish release notes" --project "Gateway Launch" 50 "Draft complete" --by matt --format json
uv run pms task show "Publish release notes" --project "Gateway Launch" --include-linked --format json
uv run pms task complete "Publish release notes" --project "Gateway Launch" --by matt --format json
```

If the task produced evidence:

```bash
uv run pms task evidence add "Publish release notes" artifact docs/release-notes.md --project "Gateway Launch"
uv run pms task evidence list "Publish release notes" --project "Gateway Launch" --format json
uv run pms task timeline "Publish release notes" --project "Gateway Launch" --format json
```

If missing work is discovered, create it immediately:

```bash
uv run pms task create "Gateway Launch" "Document rollback procedure" --format json
uv run pms task list --project "Gateway Launch" --format json
```

## 4. Strategic updates

When progress on execution changes strategy, update the strategic nodes too:

```bash
uv run pms keyresult update "Launch checklist completion" \
  --goal "Ship Gateway v1" \
  --progress 50

uv run pms objective update "Stabilize launch flow" \
  --goal "Ship Gateway v1" \
  --progress 50

uv run pms goal summary "Ship Gateway v1" --format json
```

When the criteria are complete:

```bash
uv run pms goal complete "Ship Gateway v1"
uv run pms goal summary "Ship Gateway v1" --format json
```

## 5. Review and management surfaces

Use these to manage the system, not just mutate tasks:

```bash
uv run pms start --format json
uv run pms dashboard --format json
uv run pms project summary "Gateway Launch" --format json
uv run pms work snapshot --scope-type project --scope "Gateway Launch" --format json
uv run pms work daily --scope-type project --scope "Gateway Launch" --format json --no-attach
uv run pms work review --scope-type project --scope "Gateway Launch" --reviewed-by matt --note "Weekly review" --format json
uv run pms queue presets --view detail --format json
```

Use these when the user asks:

- what should we do next
- what is blocked
- what changed this week
- is the project actually healthy
- which tasks are ready versus just retained history

## 6. Write truth after mutations

After every create, update, start, progress, or complete command where runtime
provenance matters:

- request JSON output and inspect `runtime_write`
- treat text output as a compact human surface; successful runtime plumbing is intentionally omitted

Fields that matter:

- `runtime_write.write_mode`
- `runtime_write.write_path`
- `runtime_write.target_location`

Interpretation:

- `write_path=server_delegated` means the PMS API server handled the write
- `write_path=direct_file` means the local workspace SQLite file handled the write
- do not infer the actual write path from `write_mode` alone

## 7. Agent loop and stop-hook automation

If the user wants PMS wired into an agent harness, use these maintained paths.

### Minimal read set for an agent session

```bash
uv run pms start --format json
uv run pms dashboard --format json
uv run pms task ready --format json
uv run pms task list --project "Gateway Launch" --format json
uv run pms work daily --scope-type project --scope "Gateway Launch" --format json --no-attach
uv run pms goal summary "Ship Gateway v1" --format json
```

### Stop-hook / post-run audit bundle

```bash
python3 scripts/agent_hooks/pms_stop_audit.py \
  --project "Gateway Launch" \
  --goal "Ship Gateway v1"
```

Claude Code Stop-hook JSON plus audit bundle:

```bash
python3 scripts/agent_hooks/pms_stop_audit.py \
  --project "Gateway Launch" \
  --goal "Ship Gateway v1" \
  --emit-claude-stop-payload
```

Minimal stop gate only:

```bash
uv run pms loop guard --project "Gateway Launch" --hook
```

### Claude Code config

`.claude/settings.local.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "cd \"$CLAUDE_PROJECT_DIR\" && python3 scripts/agent_hooks/pms_stop_audit.py --project \"Gateway Launch\" --goal \"Ship Gateway v1\" --emit-claude-stop-payload"
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

### Generic shell wrapper

```bash
#!/usr/bin/env bash
set -euo pipefail

agent_exit=0
"$@" || agent_exit=$?

python3 scripts/agent_hooks/pms_stop_audit.py \
  --project "Gateway Launch" \
  --goal "Ship Gateway v1" \
  > .tmp/pms-stop-audit.json || true

exit "$agent_exit"
```

## 8. Use these docs only after the runnable flows above

- `README.md`
- `docs/AGENT_INTEGRATION_GUIDE.md`
- `docs/CLIENT_GUIDE.md`
- `docs/END_TO_END_WORKFLOWS.md`
