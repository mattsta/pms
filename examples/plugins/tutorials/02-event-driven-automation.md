# Tutorial 2: Event-Driven Automation

**Time:** 15 minutes
**Level:** Intermediate
**Prerequisites:** Tutorial 1
**What you'll learn:** React to PMS events, automate workflows, connect plugins

---

## The Scenario

You want a plugin that automatically:

1. Tags tasks when they're created based on keywords in the title
2. Notifies you when high-priority tasks are completed
3. Logs all task activity for reporting

This demonstrates **event hooks** - one of the most powerful plugin features.

## Understanding Event Hooks

PMS emits events for key actions:

| Event             | When It Fires       | Available Data                     |
| ----------------- | ------------------- | ---------------------------------- |
| `task_created`    | New task added      | task_id, title, tags, priority     |
| `task_completed`  | Task marked done    | task_id, title, tags, completed_at |
| `task_updated`    | Task modified       | task_id, changes                   |
| `project_created` | New project         | project_id, name                   |
| `plugin_started`  | Plugin comes online | plugin_name                        |

Your plugin can **subscribe** to any of these and react automatically.

## Step 1: Create the Plugin

```bash
pms plugin new task-automator --template automation \
    --description "Automate task management with event hooks"
```

## Step 2: Define Events in Manifest

Replace `task-automator/plugin.json`:

```json
{
  "name": "task-automator",
  "version": "1.0.0",
  "description": "Automated task management using event hooks",
  "author": "Your Name",
  "type": "runtime",
  "entrypoint": "main.py",
  "sandbox": false,
  "capabilities": ["events"],
  "tools": [
    {
      "name": "get_activity_log",
      "description": "Get the activity log",
      "parameters": {
        "limit": {
          "type": "int",
          "required": false,
          "default": 10
        }
      }
    },
    {
      "name": "get_stats",
      "description": "Get automation statistics",
      "parameters": {}
    },
    {
      "name": "configure_rules",
      "description": "Configure automation rules",
      "parameters": {
        "rules": {
          "type": "list",
          "required": true,
          "description": "List of {keyword, tag} rules"
        }
      }
    }
  ],
  "hooks": [
    {
      "event": "task_created",
      "handler": "on_task_created",
      "priority": 100
    },
    {
      "event": "task_completed",
      "handler": "on_task_completed",
      "priority": 100
    },
    {
      "event": "task_updated",
      "handler": "on_task_updated",
      "priority": 50
    },
    {
      "event": "project_created",
      "handler": "on_project_created",
      "priority": 100
    }
  ],
  "config_schema": {
    "auto_tag_rules": {
      "type": "list",
      "default": [
        { "keyword": "bug", "tag": "bug" },
        { "keyword": "fix", "tag": "bug" },
        { "keyword": "feature", "tag": "feature" },
        { "keyword": "urgent", "tag": "high-priority" },
        { "keyword": "asap", "tag": "high-priority" }
      ],
      "description": "Rules for auto-tagging based on title keywords"
    },
    "notify_on_complete": {
      "type": "bool",
      "default": true,
      "description": "Show notification when priority tasks complete"
    }
  }
}
```

**Key Points:**

- `capabilities: ["events"]` - Request permission to receive events
- `hooks` array - Map events to handler functions
- `priority` - Higher number = called earlier (100 before 50)

## Step 3: Implement Event Handlers

Replace `task-automator/main.py`:

```python
"""Task Automator - Event-Driven Automation.

This plugin demonstrates the power of event hooks:
- Automatically tag tasks based on title keywords
- Track all task activity
- Provide statistics on automation actions

The event system allows plugins to react to changes
WITHOUT polling - they're notified immediately.
"""

from datetime import datetime
from typing import Any

# =============================================================================
# State
# =============================================================================

_config = {
    "auto_tag_rules": [
        {"keyword": "bug", "tag": "bug"},
        {"keyword": "fix", "tag": "bug"},
        {"keyword": "feature", "tag": "feature"},
        {"keyword": "urgent", "tag": "high-priority"},
        {"keyword": "asap", "tag": "high-priority"},
    ],
    "notify_on_complete": True,
}

_activity_log: list[dict] = []
_stats = {
    "tasks_processed": 0,
    "auto_tags_applied": 0,
    "completions_notified": 0,
}


def _log_activity(action: str, details: dict):
    """Add entry to activity log."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "action": action,
        **details,
    }
    _activity_log.append(entry)
    # Keep only last 1000 entries
    if len(_activity_log) > 1000:
        _activity_log.pop(0)


# =============================================================================
# Event Handlers
# =============================================================================


async def on_task_created(
    task_id: str,
    title: str,
    tags: list = None,
    priority: str = None,
    **kwargs
):
    """React to new task creation.

    This is called AUTOMATICALLY when any task is created in PMS.
    We use it to:
    1. Apply auto-tags based on title keywords
    2. Log the activity
    """
    tags = tags or []
    _stats["tasks_processed"] += 1

    print(f"[task-automator] New task detected: {title}")

    # Check for keyword matches
    title_lower = title.lower()
    applied_tags = []

    for rule in _config["auto_tag_rules"]:
        keyword = rule["keyword"].lower()
        tag = rule["tag"]

        if keyword in title_lower and tag not in tags:
            applied_tags.append(tag)
            _stats["auto_tags_applied"] += 1

    # Log the activity
    _log_activity("task_created", {
        "task_id": task_id,
        "title": title,
        "original_tags": tags,
        "auto_applied_tags": applied_tags,
    })

    if applied_tags:
        print(f"[task-automator] Auto-applied tags: {applied_tags}")
        # In a real implementation, we'd call the task service to apply these tags
        # For now, we just log what we WOULD do
        return {
            "action": "auto_tag",
            "task_id": task_id,
            "applied_tags": applied_tags,
        }


async def on_task_completed(
    task_id: str,
    title: str,
    tags: list = None,
    completed_at: str = None,
    **kwargs
):
    """React to task completion.

    We use this to:
    1. Notify about high-priority completions
    2. Track completion patterns
    """
    tags = tags or []

    print(f"[task-automator] Task completed: {title}")

    # Log the activity
    _log_activity("task_completed", {
        "task_id": task_id,
        "title": title,
        "tags": tags,
        "completed_at": completed_at,
    })

    # Check if this was a high-priority task
    is_priority = "high-priority" in tags or "urgent" in tags

    if is_priority and _config["notify_on_complete"]:
        _stats["completions_notified"] += 1
        notification = f"🎉 High-priority task completed: {title}"
        print(f"[task-automator] NOTIFICATION: {notification}")

        return {
            "action": "notify",
            "message": notification,
            "task_id": task_id,
        }


async def on_task_updated(
    task_id: str,
    changes: dict = None,
    **kwargs
):
    """React to task updates.

    Track what's being changed for analytics.
    """
    changes = changes or {}

    _log_activity("task_updated", {
        "task_id": task_id,
        "changes": list(changes.keys()),
    })

    print(f"[task-automator] Task updated: {task_id} (changed: {list(changes.keys())})")


async def on_project_created(
    project_id: str,
    name: str,
    **kwargs
):
    """React to project creation.

    Could be used to set up default automations for new projects.
    """
    _log_activity("project_created", {
        "project_id": project_id,
        "name": name,
    })

    print(f"[task-automator] New project: {name}")
    print(f"[task-automator] Tip: Tasks in this project will be auto-tagged!")


# =============================================================================
# Tools
# =============================================================================


async def get_activity_log(limit: int = 10) -> dict[str, Any]:
    """Get recent activity log entries.

    Args:
        limit: Maximum entries to return

    Returns:
        Recent activity entries
    """
    recent = _activity_log[-limit:] if limit else _activity_log
    return {
        "entries": list(reversed(recent)),  # Newest first
        "total_entries": len(_activity_log),
        "showing": len(recent),
    }


async def get_stats() -> dict[str, Any]:
    """Get automation statistics.

    Returns:
        Statistics about automation actions taken
    """
    return {
        "stats": _stats,
        "rules_configured": len(_config["auto_tag_rules"]),
        "notify_enabled": _config["notify_on_complete"],
    }


async def configure_rules(rules: list[dict]) -> dict[str, Any]:
    """Configure auto-tagging rules.

    Args:
        rules: List of {keyword, tag} rule objects

    Returns:
        Updated configuration

    Example:
        configure_rules([
            {"keyword": "security", "tag": "security"},
            {"keyword": "perf", "tag": "performance"}
        ])
    """
    # Validate rules
    for rule in rules:
        if "keyword" not in rule or "tag" not in rule:
            return {
                "success": False,
                "error": "Each rule must have 'keyword' and 'tag'",
            }

    # Merge with existing rules (avoid duplicates)
    existing_keywords = {r["keyword"].lower() for r in _config["auto_tag_rules"]}

    added = 0
    for rule in rules:
        if rule["keyword"].lower() not in existing_keywords:
            _config["auto_tag_rules"].append(rule)
            added += 1

    return {
        "success": True,
        "rules_added": added,
        "total_rules": len(_config["auto_tag_rules"]),
        "all_rules": _config["auto_tag_rules"],
    }


# =============================================================================
# Lifecycle
# =============================================================================


async def on_load(config: dict = None):
    """Initialize the automator."""
    global _config
    if config:
        _config.update(config)

    print("[task-automator] 🤖 Task Automator initialized!")
    print(f"[task-automator] Loaded {len(_config['auto_tag_rules'])} auto-tag rules")
    print("[task-automator] Listening for: task_created, task_completed, task_updated, project_created")


async def on_unload():
    """Cleanup."""
    print(f"[task-automator] Shutting down. Processed {_stats['tasks_processed']} tasks total.")
```

## Step 4: Test Event Handling

```bash
# Validate the plugin
pms plugin validate ./task-automator

# Start the plugin
pms plugin discover ./task-automator
pms plugin start task-automator

# The plugin is now listening! Any task operations will trigger hooks.
```

## Step 5: Simulate Events

Since our plugin listens to PMS events, let's simulate what happens:

```bash
# Check current stats (should be zero)
pms plugin call task-automator.get_stats

# In a real scenario, when you create a task:
# pms task add "Fix urgent bug in login"
# The on_task_created hook fires automatically!

# Check activity log
pms plugin call task-automator.get_activity_log

# Add custom rules
pms plugin call task-automator.configure_rules \
    --arg rules='[{"keyword": "security", "tag": "security-review"}]'

# Check updated stats
pms plugin call task-automator.get_stats
```

## Understanding the Event Flow

```
User Action                    Plugin Response
───────────────────────────────────────────────────────
pms task add "Fix bug"    ──▶  on_task_created() fires
                               - Detects "bug" keyword
                               - Auto-tags with "bug"
                               - Logs activity

pms task complete <id>    ──▶  on_task_completed() fires
                               - Checks if high-priority
                               - Sends notification
                               - Logs completion

pms project create "API"  ──▶  on_project_created() fires
                               - Logs new project
                               - Could set up defaults
```

## Combining with Other Plugins

Event hooks become powerful when plugins work together:

```python
# In another plugin, you could react to task-automator's actions:

async def on_task_created(task_id: str, title: str, **kwargs):
    # Check if task-automator added certain tags
    # Then do something else, like notify Slack
    pass
```

## What You Learned

1. **Event Hooks**: Subscribe to PMS events in plugin.json
2. **Handler Functions**: Async functions that receive event data
3. **Priority**: Control execution order with priority numbers
4. **Capabilities**: Request `events` capability to receive events
5. **Stateful Plugins**: Track activity across multiple events
6. **Combining Features**: Tools + Events + Configuration together

## Next Steps

- **Tutorial 3**: Create a DSL-only plugin (no Python)
- **Tutorial 4**: Build a plugin that talks to external APIs
- **Tutorial 5**: Self-building plugins that create other plugins

---

## Key Takeaways

**When to use events:**

- Automation that reacts to user actions
- Cross-plugin communication
- Activity logging and analytics
- Notifications and alerts

**When NOT to use events:**

- One-time operations (use tools instead)
- User-initiated queries (use tools)
- Heavy processing (events should be fast)
