## Output Contracts

This document defines the JSON output contract for PMS CLI/API views. The goal
is stable, predictable shapes that are easy to consume programmatically.

### Common Rules

- Timestamps use ISO 8601 / RFC 3339 strings (UTC where possible).
- Missing values are `null`.
- List outputs include pagination metadata and navigation links.
- `links` contain CLI command strings that can be executed directly.
- `overview` is minimal, `detail` is full, `trace` adds history + linked data.

### List Outputs (JSON)

List commands return a wrapper object. Current coverage includes:

- product, project, task
- org, team, portfolio, program
- plan, goal, objective, keyresult
- queue, plan_test_job
- label_category, label, label_gate_rule, evidence_gate_rule
- queue_presets, label_list_entity, plugin_tools
- queue_run
- workflow, namespace, plugin, capabilities
- remote_host, test_run, aws_server, api_key
- work_snapshot, work_daily, work_review
- label_assignment_history

Other list endpoints should follow the same wrapper shape.

```
{
  "items": [ ... ],
  "page": {
    "total_count": 123,
    "limit": 100,
    "offset": 0,
    "has_more": true,
    "next_offset": 100
  },
  "links": {
    "self": "pms <entity> list ...",
    "next": "pms <entity> list --offset 100 --limit 100"
  }
}
```

### Show Outputs (JSON)

Show commands return a single object shaped by `--view`. Current coverage includes:

- product, project, task
- org, team, portfolio, program
- plan, goal, objective, keyresult
- queue, plan_test_job
- label_category, label
- workflow, namespace, plugin
- remote_host, test_run, aws_server

Other show endpoints should follow the same view profiles.

- `overview`: essential identity + status + activity + links.
- `detail`: full entity data plus related metadata.
- `trace`: `detail` plus history + linked items + linked history.

### Work Snapshot/Review Outputs (JSON)

Work snapshot/review commands return wrapper objects with links and parameters:

```
{
  "snapshot": { ... },
  "review_history": [ ... ],
  "links": { "self": "...", "daily": "...", "review": "..." },
  "params": { ... }
}
```

### Loop Guard Output (JSON)

`pms loop guard --format json` returns a detailed goal-completion report:

```
{
  "ok": true,
  "blocked": false,
  "reason": "All goals are completed.",
  "generated_at": "2026-01-13T19:30:00Z",
  "scope": {
    "project_id": "<project-id>",
    "project_name": "Resume Hosting Site",
    "goal_ids": ["<goal-id>"]
  },
  "counts": {
    "total_goals": 1,
    "completed_goals": 1,
    "incomplete_goals": 0,
    "archived_goals": 0
  },
  "goals": [
    {
      "id": "<goal-id>",
      "name": "Launch resume hosting MVP",
      "status": "completed",
      "horizon": "short_term",
      "progress_percent": 100,
      "project_id": "<project-id>",
      "product_id": "<product-id>",
      "created_at": "2026-01-01T10:00:00Z",
      "updated_at": "2026-01-02T12:00:00Z"
    }
  ],
  "incomplete": [],
  "completed": [],
  "archived": [],
  "missing_goals": [],
  "include_archived": false,
  "block_if_no_goals": true
}
```

Example snapshot (overview):

```
{
  "snapshot": {
    "scope_type": "project",
    "scope_id": "<project-id>",
    "scope_name": "Example Project",
    "generated_at": "2025-12-30T12:00:00Z",
    "last_reviewed_at": "2025-12-30T08:00:00Z",
    "totals": {
      "total_projects": 1,
      "total_goals": 2,
      "total_objectives": 5,
      "total_tasks": 12,
      "completed_tasks": 4,
      "blocked_tasks": 1,
      "overdue_tasks": 0,
      "health_score": 0.72,
      "risk_level": "medium"
    },
    "digest": {
      "since": "2025-12-30T08:00:00Z",
      "note": null,
      "tasks_created": 2,
      "tasks_completed": 1,
      "tasks_updated": 3,
      "plans_created": 0,
      "plans_updated": 1,
      "test_runs": 4,
      "failed_test_runs": 1,
      "evidence_added": 2
    },
    "evidence": { "total_count": 10, "new_count": 2 },
    "retention": {
      "total_runs": 8,
      "total_bytes": 120000,
      "policies": [ { "scope_type": "project", "scope_id": "<project-id>" } ],
      "alerts": []
    }
  },
  "links": {
    "self": "pms work snapshot --scope-type project --scope-id <project-id> --format json",
    "daily": "pms work daily --scope-type project --scope-id <project-id> --format json",
    "review": "pms work review --scope-type project --scope-id <project-id>"
  },
  "params": {
    "scope_type": "project",
    "scope_id": "<project-id>",
    "task_limit": 5,
    "test_limit": 5,
    "view": "overview",
    "include_history": false,
    "history_limit": 5
  }
}
```

### Test Run Retention Payload (JSON)

Example item from `pms test retention --format json`:

```
{
  "total_runs": 8,
  "total_log_bytes_combined": 120000,
  "total_artifact_bytes": 800000,
  "total_bytes": 920000,
  "max_log_bytes": 1000000,
  "max_artifact_bytes": 5000000,
  "max_age_days": 30,
  "sorted_by": "largest",
  "items": [
    {
      "run_id": "<test-run-id>",
      "finished_at": "2025-12-30T12:00:00Z",
      "server_id": "local",
      "project_id": "<project-id>",
      "log_total_bytes": 12000,
      "artifact_bytes": 40000,
      "total_bytes": 52000
    }
  ],
  "policies": [
    {
      "policy_id": "<policy-id>",
      "scope_type": "project",
      "scope_id": "<project-id>",
      "max_log_bytes": 500000,
      "max_artifact_bytes": 1000000,
      "max_age_days": 30,
      "total_log_bytes": 12000,
      "total_artifact_bytes": 40000,
      "total_bytes": 52000,
      "run_count": 1,
      "older_than_max_age": 0,
      "project_ids": ["<project-id>"]
    }
  ],
  "alerts": []
}
```

Example daily review (detail):

```

### Plugin Tool Payload (JSON)

Example item from `pms plugin tools --format json`:

```

### Label Assignment Payload (JSON)

Example item from `pms label list-entity ... --format json --view detail`:

```
{
  "id": "<label-id>",
  "name": "priority:high",
  "description": "Escalated work",
  "category_id": "cat_priority",
  "category_name": "Priority",
  "color": "#ff8844",
  "is_system": false,
  "created_at": "2025-12-30T12:00:00Z",
  "updated_at": "2025-12-30T12:05:00Z",
  "links": {
    "self": "pms label show <label-id>",
    "remove": "pms label remove task <task-id> <label-id>"
  },
  "assignment": {
    "id": "<assignment-id>",
    "entity_type": "task",
    "entity_id": "<task-id>",
    "label_id": "<label-id>",
    "applied_by": "tester",
    "applied_at": "2025-12-30T12:06:00Z",
    "created_at": "2025-12-30T12:06:00Z",
    "updated_at": "2025-12-30T12:06:00Z"
  }
}
```

{
"name": "list_repos",
"full_name": "github-integration.list_repos",
"plugin": "github-integration",
"description": "List GitHub repositories",
"links": {
"call": "pms plugin call github-integration.list_repos",
"plugin": "pms plugin show github-integration"
},
"plugin_version": "1.0.0",
"plugin_state": "running",
"plugin_enabled": true,
"tool_definition": {
"name": "list_repos",
"description": "List GitHub repositories",
"handler": "list_repos",
"parameters": {
"org": { "name": "org", "type": "string", "required": true }
},
"returns": "any",
"async_handler": true,
"timeout": 30.0,
"cacheable": false,
"cache_ttl": 300
}
}

```
{
  "snapshot": { "...": "..." },
  "queues": [
    {
      "name": "ready",
      "description": "Tasks ready to work on",
      "total_count": 3,
      "items": [ { "...": "..." } ]
    }
  ],
  "test_run_window": "since last review",
  "recent_test_runs": [ { "...": "..." } ],
  "evidence_delta": { "since_last_review": 2, "total": 10 },
  "next_actions": [ { "...": "..." } ],
  "blockers": [ { "...": "..." } ],
  "links": {
    "self": "pms work daily --scope-type project --scope-id <project-id> --format json"
  },
  "params": {
    "scope_type": "project",
    "scope_id": "<project-id>",
    "view": "detail"
  }
}
```

### History Shapes

When `--include-history` or `--view trace` is used:

```
"history": {
  "progress_updates": [...],
  "workflow_transitions": [...],
  "status_transitions": [...],
  "evidence": [...]
}
```

When `--include-linked` is used:

```
"linked": {
  "<entity_type>": [ ... ],
  "page": { ... }
}
```

When `--include-linked-history` is used:

```
"linked_history": {
  "<linked_entity_id>": {
    "progress_updates": [...],
    "workflow_transitions": [...],
    "status_transitions": [...],
    "evidence": [...]
  }
}
```

### Links

All JSON views include a `links` object. Commands should be complete enough to
run without manual ID lookups.

Plugin-specific links:

- `plugin tools` list items include `links.call` and `links.plugin`.
- `plugin stats` includes `links.plugins` and `links.tools`.

### Relative Time

Relative time strings are reserved for human-facing text/table outputs. JSON
outputs always use absolute timestamps so machines can compute their own
durations.

### Proof Bundle Search JSON

Command: `pms task proof-bundle-search --format json --view detail`

```
{
  "items": [
    {
      "task": { "...": "..." },
      "summary": {
        "evidence_total": 3,
        "evidence_types": { "scm_commit": 1, "test_run": 2 },
        "test_runs": 2,
        "successful_test_runs": 1,
        "log_bytes_total": 1200,
        "artifact_bytes_total": 400
      },
      "last_evidence_at": "2025-01-02T12:00:00Z",
      "evidence": [
        { "evidence": { "...": "..." }, "test_run": { "...": "..." } }
      ],
      "test_runs": [ { "...": "..." } ]
    }
  ],
  "page": { "total_count": 1, "limit": 50, "offset": 0 },
  "links": {
    "self": "pms task proof-bundle-search --format json --limit 50 --offset 0",
    "next": null
  }
}
```

### Revision Diff JSON

Command: `pms revision diff project <project-id> --from 1 --to 2 --format json`

```
{
  "entity_type": "project",
  "entity_id": "<project-id>",
  "from_revision": 1,
  "to_revision": 2,
  "changes": [
    {
      "field_name": "name",
      "old_value": "Old Name",
      "new_value": "New Name",
      "change_type": "update"
    }
  ],
  "intermediate_revisions": ["rev_abc"]
}
```

### Revision History Bundle JSON

Command: `pms revision bundle project <project-id> --include-linked --include-linked-history --format json`

```
{
  "entity_type": "project",
  "entity_id": "<project-id>",
  "generated_at": "2025-01-05T12:00:00Z",
  "history": {
    "items": [
      {
        "revision_id": "<revision-id>",
        "entity_type": "project",
        "entity_id": "<project-id>",
        "revision_number": 2,
        "parent_revision_id": "<parent-revision-id>",
        "content": { "id": "<project-id>", "name": "Project v2" },
        "content_hash": "sha256",
        "changes": [
          {
            "field_name": "name",
            "old_value": "Project",
            "new_value": "Project v2",
            "change_type": "update"
          }
        ],
        "change_type": "update",
        "created_at": "2025-01-05T11:59:00Z",
        "created_by": "alice",
        "message": "Updated project name",
        "metadata": {}
      }
    ],
    "page": { "total_count": 2, "limit": 20, "offset": 0, "has_more": false, "next_offset": null }
  },
  "linked": {
    "tasks": [
      {
        "id": "<task-id>",
        "entity_type": "task",
        "name": "Design auth flow",
        "status": "in_progress",
        "updated_at": "2025-01-05T11:00:00Z"
      }
    ]
  },
  "linked_history": {
    "tasks": {
      "<task-id>": {
        "items": [
          {
            "revision_id": "rev_task_001",
            "entity_type": "task",
            "entity_id": "<task-id>",
            "revision_number": 1,
            "parent_revision_id": null,
            "content": { "id": "<task-id>", "title": "Design auth flow" },
            "content_hash": "sha256",
            "changes": [],
            "change_type": "create",
            "created_at": "2025-01-05T10:00:00Z",
            "created_by": "alice",
            "message": "Initial revision",
            "metadata": {}
          }
        ],
        "page": { "total_count": 1, "limit": 20, "offset": 0, "has_more": false, "next_offset": null }
      }
    }
  }
}
```
