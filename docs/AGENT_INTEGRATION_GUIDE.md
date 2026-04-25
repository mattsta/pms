# Agent Integration Guide

This is the live PMS guide for agent harness integration, hooks, and wrapper
automation.

Archived `docs/archive/reference/hooks.md` and
`docs/archive/reference/hooks-guide.md` are generic reference notes kept for
provenance. They are not the maintained PMS integration path.

## The Maintained PMS Automation Pattern

For agent harnesses, keep the control loop consistent:

1. session start discovery
   - `uv run pms start --format json`
   - `uv run pms dashboard --format json`
2. task selection and execution
   - `uv run pms task ready --format json`
   - `uv run pms task list --project "<project>" --format json`
3. scoped audit and next-step readback
   - `uv run pms work daily --scope-type project --scope "<project>" --format json --no-attach`
   - `uv run pms goal summary "<goal>" --format json`
4. session-stop policy
   - `uv run pms loop guard --project "<project>" --hook`
   - or the maintained stop-audit helper below when you also want artifact dumps

Use JSON for automation. Text/table output is for humans.

## Maintained Stop-Audit Helper

Use:

```bash
python3 scripts/agent_hooks/pms_stop_audit.py \
  --project "Resume Hosting Site" \
  --goal "Launch resume hosting MVP"
```

The helper writes a bundle under `PMS_DATA_DIR/hook-audits/` containing:

- `metadata.json`
- `start.json`
- `dashboard.json`
- `task-ready.json`
- `project-task-list.json` when `--project` or `--project-id` is provided
- `work-daily.json` when `--project` or `--project-id` is provided
- `goal-summary-*.json` when `--goal` or `--goal-id` is provided

Why this helper exists:

- it gives agents and operators one deterministic stop snapshot
- it captures next-step recommendations instead of only raw task rows
- it keeps hook output read-only and machine-readable

If you need Claude Code `Stop` hook JSON on stdout too, add
`--emit-claude-stop-payload`. The helper will still write the bundle and will
also store the emitted payload in `loop-guard-hook.json`.

## Common Harnesses

### Claude Code

Recommended layout:

1. install PMS as an MCP server
2. use the stop-audit helper in the `Stop` hook
3. use the PMS allowlist helper in the `PermissionRequest` hook

`.claude/settings.local.json`:

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

Use the direct `uv run pms loop guard ... --hook` form only when you want the
minimal completion gate and do not need the artifact bundle.

### PMS Loop Runner / Codex Adapter

When you can run the maintained loop runner, use it:

```bash
uv run pms loop run --agent claude --project "Resume Hosting Site" --prompt-file PROMPT.md
uv run pms loop run --agent codex --project "Resume Hosting Site" --prompt-file PROMPT.md
```

That gives you the maintained loop contract directly. If you still want a stop
bundle outside the runner, call `scripts/agent_hooks/pms_stop_audit.py` from the
wrapper that launches the loop.

### Generic Shell-Wrapped Agents

This pattern fits command-line harnesses and wrappers around tools such as Codex
CLI, Aider, OpenCode, Cline, or internal agents.

Wrapper pattern:

```bash
#!/usr/bin/env bash
set -euo pipefail

agent_exit=0
"$@" || agent_exit=$?

python3 scripts/agent_hooks/pms_stop_audit.py \
  --project "Resume Hosting Site" \
  --goal "Launch resume hosting MVP" \
  > /tmp/pms-stop-audit.json || true

exit "$agent_exit"
```

Use this when the harness does not have a native stop-hook protocol but you
still want deterministic PMS artifacts after each run.

### MCP-Only Hosts

For MCP hosts that do not expose shell hooks:

1. register PMS as an MCP server
2. call `start` and `dashboard` at session start
3. call `task ready`, `task list`, and `work daily` before yielding control
4. call `goal summary` before declaring completion

If the host can run external commands between sessions, run the stop-audit
helper there instead of inside the host.

### CI / Background Automation

Use the helper as an always-run post step so each automated run leaves a bundle:

```bash
python3 scripts/agent_hooks/pms_stop_audit.py \
  --project "Release Coordination" \
  --goal "Cut 0.1.0"
```

Publish the resulting bundle directory as a CI artifact.

## Best Practices

- scope hooks to a project and, when possible, explicit goals
- keep hook commands read-only; mutate work inside the agent loop, not in the
  stop hook
- prefer `--format json` everywhere inside automation
- use `work daily --no-attach` in audit flows so hooks do not create evidence
- use `loop guard` to decide whether stop is allowed
- use the stop-audit helper when you want review artifacts and next-step dumps
- store outputs under `PMS_DATA_DIR` so multiple repos and scratch workspaces do
  not collide

## Where This Fits In The Live Docs

- discovery and machine contracts:
  - [`docs/MACHINE_INTERFACE_GUIDE.md`](MACHINE_INTERFACE_GUIDE.md)
- detailed loop and client usage:
  - [`docs/CLIENT_GUIDE.md`](CLIENT_GUIDE.md)
- workflow walkthroughs:
  - [`docs/END_TO_END_WORKFLOWS.md`](END_TO_END_WORKFLOWS.md)
- live doc routing:
  - [`docs/DOCUMENTATION_MAP.md`](DOCUMENTATION_MAP.md)
