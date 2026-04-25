# Claudo Interop

PMS can bootstrap from existing Claude todo state by consuming Claudo's
`claudo.task_graph.v1` interchange JSON. The adapter keeps PMS authoritative:
projects, goals, plans, tasks, dependencies, statuses, descriptions, ownership,
and source metadata are written through PMS services.

For a first-run repo bootstrap workflow using app-local PMS state, see
[`docs/CLAUDO_BOOTSTRAP_WORKFLOW.md`](CLAUDO_BOOTSTRAP_WORKFLOW.md).

## Import

Use a saved Claudo export:

```bash
pms claudo import ./claudo-export.json
```

Or let PMS call Claudo directly against the live Claude task directory:

```bash
pms claudo import --source-path ~/.claude/tasks --claudo-repo ~/repos/claudo
```

Useful options:

- `--dry-run`: preview creates/reuses without writing PMS.
- `--session <id>`: restrict live Claudo export to one session.
- `--project-root <path>`: filter to Claudo sessions whose repo metadata matches
  one existing project directory before importing.
- `--project <name>`: place all imported sessions into one PMS project.
- `--project-prefix <prefix>`: prefix projects inferred from Claudo metadata.
- `--no-goals` / `--no-plans`: skip session goal/plan creation.
- `--format json`: emit machine-readable import counts and id maps.

Idempotency is based on PMS custom fields:

- project `claudo_project_key`
- goal/plan `claudo_session_id`
- task `claudo_uid`
- all imported entity types `claudo_metadata`

Claudo dependency edges are `blocker -> blocked`; PMS stores that as
`blocked_task depends_on blocker_task` with dependency type `blocks`.

## Export

Export a PMS project back to Claudo interchange JSON:

```bash
pms claudo export "My Project" -o ./pms-claudo-export.json
```

To stage Claude-compatible todo JSON through Claudo:

```bash
pms claudo export "My Project" \
  -o ./pms-claudo-export.json \
  --materialize-claude ./claude-task-stage
```

PMS exports supported Claude todo surfaces: task title, description, pending /
in-progress / completed status, owner, blocks / blockedBy references, session
metadata, and PMS metadata. PMS-only features such as workflows, labels,
checkouts, evidence, objectives, and cross-project dependency targets are
preserved only as metadata or skipped with diagnostics.
