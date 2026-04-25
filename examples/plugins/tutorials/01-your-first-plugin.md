# Tutorial 1: Your First Plugin

**Time:** 10 minutes
**Level:** Beginner
**What you'll learn:** Create, validate, test, and use a complete plugin

---

## The Scenario

You want a plugin that helps you manage quick notes - capturing ideas, listing them, and clearing completed ones. By the end, you'll have a working plugin you can actually use.

## Step 1: Create the Plugin Structure

First, let's use the CLI to scaffold our plugin:

```bash
# Create a new plugin using the 'basic' template
pms plugin new quick-notes --template basic --description "Quick note-taking plugin"
```

This creates:

```
./quick-notes/
├── plugin.json    # Plugin manifest
└── main.py        # Implementation
```

## Step 2: Define Our Tools

Open `quick-notes/plugin.json` and replace with:

```json
{
  "name": "quick-notes",
  "version": "1.0.0",
  "description": "Quick note-taking plugin for capturing ideas",
  "author": "Your Name",
  "type": "extension",
  "entrypoint": "main.py",
  "sandbox": false,
  "tools": [
    {
      "name": "add",
      "description": "Add a new note",
      "parameters": {
        "text": {
          "type": "string",
          "required": true,
          "description": "The note text"
        },
        "tag": {
          "type": "string",
          "required": false,
          "default": "general",
          "description": "Optional tag for categorization"
        }
      }
    },
    {
      "name": "list",
      "description": "List all notes",
      "parameters": {
        "tag": {
          "type": "string",
          "required": false,
          "description": "Filter by tag"
        }
      }
    },
    {
      "name": "clear",
      "description": "Clear all notes or notes with a specific tag",
      "parameters": {
        "tag": {
          "type": "string",
          "required": false,
          "description": "Only clear notes with this tag"
        }
      }
    },
    {
      "name": "stats",
      "description": "Get note statistics",
      "parameters": {}
    }
  ]
}
```

## Step 3: Implement the Plugin

Open `quick-notes/main.py` and replace with:

```python
"""Quick Notes Plugin - Your First Plugin.

A simple but complete example of a PMS plugin.

Usage:
    pms plugin start quick-notes
    pms plugin call quick-notes.add --arg text="Remember to review PR"
    pms plugin call quick-notes.list
"""

from datetime import datetime
from typing import Any

# In-memory storage (in production, you'd persist this)
_notes: list[dict] = []
_config = {}


async def add(text: str, tag: str = "general") -> dict[str, Any]:
    """Add a new note.

    Args:
        text: The note content
        tag: Category tag (default: "general")

    Returns:
        The created note with ID and timestamp
    """
    note = {
        "id": len(_notes) + 1,
        "text": text,
        "tag": tag,
        "created_at": datetime.now().isoformat(),
    }
    _notes.append(note)

    print(f"[quick-notes] Added note #{note['id']}: {text[:30]}...")

    return {
        "success": True,
        "note": note,
        "message": f"Note #{note['id']} added with tag '{tag}'",
    }


async def list(tag: str = None) -> dict[str, Any]:
    """List all notes, optionally filtered by tag.

    Args:
        tag: If provided, only show notes with this tag

    Returns:
        List of matching notes
    """
    if tag:
        filtered = [n for n in _notes if n["tag"] == tag]
    else:
        filtered = _notes

    return {
        "notes": filtered,
        "count": len(filtered),
        "filter": tag,
    }


async def clear(tag: str = None) -> dict[str, Any]:
    """Clear notes.

    Args:
        tag: If provided, only clear notes with this tag

    Returns:
        Number of notes cleared
    """
    global _notes

    if tag:
        original_count = len(_notes)
        _notes = [n for n in _notes if n["tag"] != tag]
        cleared = original_count - len(_notes)
    else:
        cleared = len(_notes)
        _notes = []

    return {
        "cleared": cleared,
        "remaining": len(_notes),
        "filter": tag,
    }


async def stats() -> dict[str, Any]:
    """Get statistics about your notes.

    Returns:
        Statistics including count, tags, and oldest/newest notes
    """
    if not _notes:
        return {"total": 0, "message": "No notes yet!"}

    # Count by tag
    tags = {}
    for note in _notes:
        tag = note["tag"]
        tags[tag] = tags.get(tag, 0) + 1

    return {
        "total": len(_notes),
        "by_tag": tags,
        "oldest": _notes[0]["created_at"] if _notes else None,
        "newest": _notes[-1]["created_at"] if _notes else None,
    }


# Lifecycle hooks
async def on_load(config: dict = None):
    """Called when the plugin is loaded."""
    global _config
    if config:
        _config = config
    print("[quick-notes] Plugin loaded! Ready to capture your ideas.")


async def on_unload():
    """Called when the plugin is unloaded."""
    print(f"[quick-notes] Unloading. You had {len(_notes)} notes.")
```

## Step 4: Validate Your Plugin

Before using it, let's make sure everything is correct:

```bash
pms plugin validate ./quick-notes
```

Expected output:

```
Validating plugin at: ./quick-notes
==================================================
✓ plugin.json found
  Name: quick-notes
  Version: 1.0.0
  Tools: 4
✓ Entrypoint found: main.py
✓ Python syntax valid
✓ Tool function found: add
✓ Tool function found: list
✓ Tool function found: clear
✓ Tool function found: stats

✓ Plugin is valid!
```

## Step 5: Test Your Plugin

Run automated tests:

```bash
pms plugin test ./quick-notes --verbose
```

Expected output:

```
Testing plugin at: ./quick-notes
==================================================

Loading plugin: quick-notes...
[quick-notes] Plugin loaded! Ready to capture your ideas.
✓ Plugin loaded

Testing tool: add
  Args: {'text': 'test'}
  Result: {'success': True, 'note': {...}, 'message': "Note #1 added..."}
  ✓ Tool executed successfully

Testing tool: list
  Args: {}
  Result: {'notes': [...], 'count': 1, 'filter': None}
  ✓ Tool executed successfully

...

==================================================
Test Summary
  Passed: 5
  Failed: 0
```

## Step 6: Use Your Plugin!

Now let's actually use it:

```bash
# Discover and start the plugin
pms plugin discover ./quick-notes
pms plugin start quick-notes

# Add some notes
pms plugin call quick-notes.add --arg text="Review the plugin architecture"
pms plugin call quick-notes.add --arg text="Write more tests" --arg tag="todo"
pms plugin call quick-notes.add --arg text="Coffee break" --arg tag="personal"

# List all notes
pms plugin call quick-notes.list

# List only todos
pms plugin call quick-notes.list --arg tag="todo"

# Get stats
pms plugin call quick-notes.stats

# Clear personal notes
pms plugin call quick-notes.clear --arg tag="personal"

# Stop the plugin
pms plugin stop quick-notes
```

## What You Learned

1. **Plugin Structure**: manifest.json defines metadata, main.py implements tools
2. **Tool Parameters**: Required vs optional, default values, types
3. **Lifecycle Hooks**: on_load and on_unload for setup/cleanup
4. **Validation**: Use `pms plugin validate` to check before running
5. **Testing**: Use `pms plugin test` for automated verification
6. **CLI Flow**: discover → start → call → stop

## Next Steps

- **Tutorial 2**: Add event hooks to react to PMS events
- **Tutorial 3**: Create a DSL-only plugin (no Python needed)
- **Tutorial 4**: Build an integration plugin with external APIs
- **Tutorial 5**: Create a self-building meta-plugin

---

## Complete Files

<details>
<summary>Click to see the complete plugin.json</summary>

```json
{
  "name": "quick-notes",
  "version": "1.0.0",
  "description": "Quick note-taking plugin for capturing ideas",
  "author": "Your Name",
  "type": "extension",
  "entrypoint": "main.py",
  "sandbox": false,
  "tools": [
    {
      "name": "add",
      "description": "Add a new note",
      "parameters": {
        "text": {
          "type": "string",
          "required": true,
          "description": "The note text"
        },
        "tag": {
          "type": "string",
          "required": false,
          "default": "general",
          "description": "Optional tag"
        }
      }
    },
    {
      "name": "list",
      "description": "List all notes",
      "parameters": {
        "tag": {
          "type": "string",
          "required": false,
          "description": "Filter by tag"
        }
      }
    },
    {
      "name": "clear",
      "description": "Clear notes",
      "parameters": {
        "tag": {
          "type": "string",
          "required": false,
          "description": "Only clear this tag"
        }
      }
    },
    {
      "name": "stats",
      "description": "Get note statistics",
      "parameters": {}
    }
  ]
}
```

</details>

<details>
<summary>Click to see the complete main.py</summary>

```python
"""Quick Notes Plugin."""

from datetime import datetime
from typing import Any

_notes: list[dict] = []
_config = {}

async def add(text: str, tag: str = "general") -> dict[str, Any]:
    note = {
        "id": len(_notes) + 1,
        "text": text,
        "tag": tag,
        "created_at": datetime.now().isoformat(),
    }
    _notes.append(note)
    return {"success": True, "note": note, "message": f"Note #{note['id']} added"}

async def list(tag: str = None) -> dict[str, Any]:
    filtered = [n for n in _notes if not tag or n["tag"] == tag]
    return {"notes": filtered, "count": len(filtered), "filter": tag}

async def clear(tag: str = None) -> dict[str, Any]:
    global _notes
    if tag:
        orig = len(_notes)
        _notes = [n for n in _notes if n["tag"] != tag]
        cleared = orig - len(_notes)
    else:
        cleared = len(_notes)
        _notes = []
    return {"cleared": cleared, "remaining": len(_notes)}

async def stats() -> dict[str, Any]:
    if not _notes:
        return {"total": 0, "message": "No notes yet!"}
    tags = {}
    for note in _notes:
        tags[note["tag"]] = tags.get(note["tag"], 0) + 1
    return {"total": len(_notes), "by_tag": tags}

async def on_load(config: dict = None):
    global _config
    _config = config or {}
    print("[quick-notes] Ready!")

async def on_unload():
    print(f"[quick-notes] Bye! Had {len(_notes)} notes.")
```

</details>
