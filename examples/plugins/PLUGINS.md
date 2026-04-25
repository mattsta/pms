# PMS Plugin System Guide

A comprehensive guide to creating, managing, and extending PMS through plugins.

## Table of Contents

1. [Introduction](#introduction)
2. [Quick Start](#quick-start)
3. [Simple Plugins](#simple-plugins)
4. [Intermediate Plugins](#intermediate-plugins)
5. [Advanced Plugins](#advanced-plugins)
6. [Self-Building Plugins](#self-building-plugins)
7. [Integration Workflows](#integration-workflows)
8. [Best Practices](#best-practices)
9. [API Reference](#api-reference)

---

## Introduction

The PMS plugin system enables dynamic extension of the platform through:

- **Python Plugins**: Full-featured plugins with async tool implementations
- **DSL Plugins**: Declarative tool definitions without writing Python
- **Sandboxed Execution**: Isolated process execution with resource limits
- **Event Hooks**: React to system events automatically
- **Self-Building**: Plugins that create other plugins

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     PMS Core System                         │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │   Registry   │  │  Lifecycle   │  │     Sandbox      │   │
│  │   Manager    │  │   Manager    │  │     Manager      │   │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘   │
│         │                 │                   │             │
│         └─────────────────┴────────────────────┘            │
│                              │                              │
│                       ┌──────┴──────┐                       │
│                       │  IPC Layer  │                       │
│                       │ (Unix Sock) │                       │
│                       └──────┬──────┘                       │
└───────────────────────────┼─────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
   ┌────┴────┐        ┌─────┴─────┐       ┌────┴────┐
   │ Plugin  │        │  Plugin   │       │ Plugin  │
   │    A    │        │     B     │       │    C    │
   └─────────┘        └───────────┘       └─────────┘
   (Python)           (DSL .tools)        (Sandboxed)
```

### Plugin States

Plugins progress through a defined lifecycle:

```
DISCOVERED → LOADING → LOADED → INITIALIZING → INITIALIZED → STARTING → RUNNING
                ↓         ↓          ↓              ↓            ↓         ↓
              ERROR     ERROR      ERROR          ERROR        ERROR    STOPPING
                                                                           ↓
                                                                        STOPPED
```

---

## Quick Start

### Create Your First Plugin in 60 Seconds

1. **Create plugin directory:**

```bash
mkdir -p ~/.pms/plugins/my-first-plugin
cd ~/.pms/plugins/my-first-plugin
```

2. **Create `plugin.json`:**

```json
{
  "name": "my-first-plugin",
  "version": "1.0.0",
  "description": "My first PMS plugin",
  "tools": [
    {
      "name": "greet",
      "description": "Greet someone by name",
      "parameters": {
        "name": { "type": "string", "required": true }
      }
    }
  ]
}
```

3. **Create `main.py`:**

```python
async def greet(name: str) -> str:
    """Greet someone by name."""
    return f"Hello, {name}! Welcome to PMS plugins."
```

4. **Use your plugin:**

```bash
pms plugin discover ~/.pms/plugins
pms plugin start my-first-plugin
pms plugin call my-first-plugin.greet --arg name=World
```

---

## Simple Plugins

Simple plugins demonstrate the core concepts with minimal complexity.

### Example 1: Hello World Plugin

**Location:** `examples/plugins/simple/hello-world/`

The simplest possible plugin - demonstrates basic structure and parameter handling.

**plugin.json:**

```json
{
  "name": "hello-world",
  "version": "1.0.0",
  "description": "Simplest possible plugin - just says hello",
  "author": "PMS Examples",
  "type": "extension",
  "entrypoint": "main.py",
  "sandbox": false,
  "tools": [
    {
      "name": "say_hello",
      "description": "Say hello to someone",
      "parameters": {
        "name": {
          "type": "string",
          "required": false,
          "default": "World",
          "description": "Name to greet"
        }
      }
    },
    {
      "name": "get_greeting_count",
      "description": "Get how many times we've said hello",
      "parameters": {}
    }
  ]
}
```

**main.py:**

```python
"""Hello World Plugin - The simplest possible plugin."""

from typing import Any

# Plugin state (persists across tool calls)
_greeting_count = 0


async def say_hello(name: str = "World") -> str:
    """Say hello to someone.

    Args:
        name: The name to greet (default: "World")

    Returns:
        A greeting message
    """
    global _greeting_count
    _greeting_count += 1
    message = f"Hello, {name}!"
    print(message)
    return message


async def get_greeting_count() -> dict[str, Any]:
    """Get how many times we've said hello."""
    return {"count": _greeting_count}


# Lifecycle hooks
async def on_load(config: dict = None):
    """Called when plugin is loaded."""
    print("Hello World plugin loaded!")


async def on_unload():
    """Called when plugin is unloaded."""
    print("Hello World plugin unloaded. Goodbye!")
```

**Usage:**

```bash
# Discover and start
pms plugin discover examples/plugins/simple
pms plugin start hello-world

# Call tools
pms plugin call hello-world.say_hello
# Output: Hello, World!

pms plugin call hello-world.say_hello --arg name=Alice
# Output: Hello, Alice!

pms plugin call hello-world.get_greeting_count
# Output: {"count": 2}

# Stop plugin
pms plugin stop hello-world
```

### Example 2: DSL-Only Plugin (No Python Required)

**Location:** `examples/plugins/simple/math-dsl.tools`

The simplest way to create tools - pure declarative definitions.

**math-dsl.tools:**

```
## Math DSL - Simple mathematical tools
##
## This demonstrates PMS's DSL capability: create tools without any Python code.
## Just declare what the tool does, and the DSL compiler handles the rest.

tool double:
    description: "Double a number"
    param x: int
    return x * 2

tool triple:
    description: "Triple a number"
    param x: int
    return x * 3

tool is_even:
    description: "Check if a number is even"
    param n: int
    return n % 2 == 0

tool is_positive:
    description: "Check if a number is positive"
    param n: int
    return n > 0

tool factorial:
    description: "Calculate factorial of n"
    param n: int
    when n <= 1:
        return 1
    otherwise:
        return n * factorial(n - 1)

tool greet_number:
    description: "Generate a greeting based on a number's magnitude"
    param n: int
    when n > 100:
        return "That's a big number!"
    when n > 10:
        return "Nice number!"
    otherwise:
        return "Small but mighty!"
```

**Usage:**

```bash
pms plugin discover examples/plugins/simple
pms plugin call math-dsl.double --arg x=21
# Output: 42

pms plugin call math-dsl.is_even --arg n=42
# Output: true

pms plugin call math-dsl.greet_number --arg n=150
# Output: "That's a big number!"
```

### Key Concepts from Simple Plugins

| Concept         | Description                                                |
| --------------- | ---------------------------------------------------------- |
| `plugin.json`   | Manifest defining plugin metadata, tools, and capabilities |
| `main.py`       | Python implementation with async tool functions            |
| `.tools`        | DSL file for declarative tool definitions                  |
| Lifecycle hooks | `on_load`, `on_unload` for setup/cleanup                   |
| Parameters      | Typed inputs with defaults and validation                  |

---

## Intermediate Plugins

Intermediate plugins add real-world functionality with capabilities, configuration, and event hooks.

### Example: File Utilities Plugin

**Location:** `examples/plugins/intermediate/file-utils/`

A practical utility plugin demonstrating:

- Multiple related tools
- Capability requirements (filesystem access)
- Configuration schema
- Event hooks
- Structured error handling

**plugin.json:**

```json
{
  "name": "file-utils",
  "version": "1.0.0",
  "description": "File system utilities for counting, searching, and analyzing files",
  "author": "PMS Examples",
  "type": "extension",
  "entrypoint": "main.py",
  "sandbox": true,
  "capabilities": ["filesystem_read"],
  "tools": [
    {
      "name": "count_lines",
      "description": "Count lines in files",
      "parameters": {
        "path": {
          "type": "string",
          "required": true,
          "description": "File or directory path"
        },
        "pattern": {
          "type": "string",
          "required": false,
          "default": "*",
          "description": "Glob pattern for files"
        }
      }
    },
    {
      "name": "find_files",
      "description": "Find files matching a pattern",
      "parameters": {
        "directory": { "type": "string", "required": true },
        "pattern": { "type": "string", "required": true },
        "max_results": { "type": "int", "required": false, "default": 100 }
      }
    },
    {
      "name": "file_stats",
      "description": "Get detailed statistics about a file",
      "parameters": {
        "path": { "type": "string", "required": true }
      }
    },
    {
      "name": "search_content",
      "description": "Search for text content in files",
      "parameters": {
        "directory": { "type": "string", "required": true },
        "query": { "type": "string", "required": true },
        "file_pattern": { "type": "string", "required": false, "default": "*" }
      }
    }
  ],
  "hooks": [
    {
      "event": "task_created",
      "handler": "on_task_created",
      "priority": 100
    }
  ],
  "config_schema": {
    "default_directory": {
      "type": "string",
      "default": ".",
      "description": "Default directory for operations"
    },
    "ignore_patterns": {
      "type": "list",
      "default": ["node_modules", ".git", "__pycache__", ".venv"],
      "description": "Patterns to ignore when searching"
    }
  }
}
```

**main.py (key excerpts):**

```python
"""File Utilities Plugin - Intermediate complexity example."""

from pathlib import Path
from typing import Any

_config = {
    "default_directory": ".",
    "ignore_patterns": ["node_modules", ".git", "__pycache__", ".venv"],
}


def _should_ignore(path: Path) -> bool:
    """Check if path should be ignored based on config."""
    path_str = str(path)
    return any(pattern in path_str for pattern in _config["ignore_patterns"])


async def count_lines(path: str, pattern: str = "*") -> dict[str, Any]:
    """Count lines in files.

    Args:
        path: File or directory path
        pattern: Glob pattern for files (default: all files)

    Returns:
        Dictionary with line counts and statistics
    """
    target = Path(path).expanduser()

    if not target.exists():
        return {"error": f"Path not found: {path}"}

    results = {
        "path": str(target),
        "pattern": pattern,
        "files": [],
        "total_lines": 0,
        "total_files": 0,
    }

    if target.is_file():
        lines = len(target.read_text().splitlines())
        results["files"].append({"file": str(target), "lines": lines})
        results["total_lines"] = lines
        results["total_files"] = 1
    else:
        for file_path in target.rglob(pattern):
            if file_path.is_file() and not _should_ignore(file_path):
                try:
                    lines = len(file_path.read_text().splitlines())
                    results["files"].append({
                        "file": str(file_path.relative_to(target)),
                        "lines": lines,
                    })
                    results["total_lines"] += lines
                    results["total_files"] += 1
                except Exception:
                    pass  # Skip binary/unreadable files

    return results


async def search_content(
    directory: str,
    query: str,
    file_pattern: str = "*",
) -> dict[str, Any]:
    """Search for text content in files."""
    target = Path(directory).expanduser()

    if not target.exists():
        return {"error": f"Directory not found: {directory}"}

    results = {
        "directory": str(target),
        "query": query,
        "matches": [],
        "total_matches": 0,
    }

    query_lower = query.lower()

    for file_path in target.rglob(file_pattern):
        if not file_path.is_file() or _should_ignore(file_path):
            continue

        try:
            content = file_path.read_text()
            lines = content.splitlines()

            file_matches = []
            for i, line in enumerate(lines, 1):
                if query_lower in line.lower():
                    file_matches.append({
                        "line_number": i,
                        "content": line.strip()[:200],
                    })

            if file_matches:
                results["matches"].append({
                    "file": str(file_path.relative_to(target)),
                    "matches": file_matches[:10],
                    "total_in_file": len(file_matches),
                })
                results["total_matches"] += len(file_matches)
        except (UnicodeDecodeError, PermissionError):
            pass

    return results


# Event Hook
async def on_task_created(task_id: str, title: str, **kwargs):
    """React to task creation events."""
    if "/" in title or "." in title:
        print(f"[file-utils] New task may reference files: {title}")


# Lifecycle
async def on_load(config: dict = None):
    """Initialize plugin with configuration."""
    global _config
    if config:
        _config.update(config)
    print(f"File Utils loaded. Default directory: {_config['default_directory']}")
```

**Usage:**

```bash
# Start with custom config
echo '{"ignore_patterns": [".git", "node_modules"]}' > file-utils-config.json
pms plugin start file-utils --config file-utils-config.json

# Count lines in a project
pms plugin call file-utils.count_lines --arg path=./src --arg pattern="*.py"
# Output:
# {
#   "path": "/home/user/project/src",
#   "total_lines": 2847,
#   "total_files": 23,
#   "files": [...]
# }

# Search for function definitions
pms plugin call file-utils.search_content \
    --arg directory=./src \
    --arg query="async def" \
    --arg file_pattern="*.py"

# Get file statistics
pms plugin call file-utils.file_stats --arg path=./README.md
```

### Key Concepts from Intermediate Plugins

| Concept            | Description                                                          |
| ------------------ | -------------------------------------------------------------------- |
| Capabilities       | Declare required permissions (`filesystem_read`, `network`, etc.)    |
| Config Schema      | Define configurable options with types and defaults                  |
| Event Hooks        | Subscribe to system events (`task_created`, `project_created`, etc.) |
| Error Handling     | Return structured errors, handle exceptions gracefully               |
| Structured Returns | Return rich JSON objects, not just strings                           |

---

## Advanced Plugins

Advanced plugins integrate with external systems, manage state, and provide production-ready features.

### Example: GitHub Integration Plugin

**Location:** `examples/plugins/advanced/github-integration/`

A production-quality plugin demonstrating:

- External API integration
- Credential/secret management
- Caching strategies
- Cross-system synchronization
- Multiple event hooks
- Dependencies

**plugin.json:**

```json
{
  "name": "github-integration",
  "version": "1.0.0",
  "description": "Full GitHub integration - repos, issues, PRs, and automation",
  "author": "PMS Examples",
  "type": "integration",
  "entrypoint": "main.py",
  "sandbox": true,
  "capabilities": ["network", "events", "tools"],
  "max_memory_mb": 256,
  "timeout": 60.0,
  "max_concurrent": 5,
  "tools": [
    {
      "name": "list_repos",
      "description": "List repositories for an organization or user",
      "parameters": {
        "owner": { "type": "string", "required": true },
        "type": { "type": "string", "required": false },
        "limit": { "type": "int", "required": false }
      },
      "timeout": 30.0,
      "cacheable": true,
      "cache_ttl": 300
    },
    {
      "name": "create_issue",
      "description": "Create a new issue",
      "parameters": {
        "owner": { "type": "string", "required": true },
        "repo": { "type": "string", "required": true },
        "title": { "type": "string", "required": true },
        "body": { "type": "string", "required": false },
        "labels": { "type": "list", "required": false }
      }
    },
    {
      "name": "sync_to_tasks",
      "description": "Sync GitHub issues to PMS tasks",
      "parameters": {
        "owner": { "type": "string", "required": true },
        "repo": { "type": "string", "required": true },
        "project_name": { "type": "string", "required": true },
        "labels": { "type": "string", "required": false }
      }
    }
  ],
  "hooks": [
    {
      "event": "task_completed",
      "handler": "on_task_completed",
      "filter": { "has_tag": "github" }
    },
    {
      "event": "project_created",
      "handler": "on_project_created"
    }
  ],
  "dependencies": [
    { "name": "httpx", "version": ">=0.24.0", "type": "python" }
  ],
  "config_schema": {
    "github_token": {
      "type": "string",
      "required": true,
      "secret": true,
      "env_var": "GITHUB_TOKEN",
      "description": "GitHub personal access token"
    },
    "api_base_url": {
      "type": "string",
      "default": "https://api.github.com",
      "description": "GitHub API base URL (for Enterprise)"
    },
    "auto_sync": {
      "type": "bool",
      "default": false,
      "description": "Automatically sync issues on project creation"
    }
  },
  "on_load": "initialize",
  "on_unload": "cleanup"
}
```

**main.py (key excerpts):**

```python
"""GitHub Integration Plugin - Advanced example."""

import os
from datetime import UTC, datetime, timedelta
from typing import Any

_config = {
    "github_token": None,
    "api_base_url": "https://api.github.com",
    "auto_sync": False,
}

_cache: dict[str, tuple[Any, datetime]] = {}
_cache_ttl = timedelta(minutes=5)


def _get_cached(key: str) -> Any | None:
    """Get cached value if not expired."""
    if key in _cache:
        value, timestamp = _cache[key]
        if datetime.now(UTC) - timestamp < _cache_ttl:
            return value
        del _cache[key]
    return None


async def list_repos(
    owner: str,
    type: str = "all",
    limit: int = 30,
) -> dict[str, Any]:
    """List repositories for an organization or user."""
    cache_key = f"repos:{owner}:{type}"
    cached = _get_cached(cache_key)
    if cached:
        return {"repos": cached[:limit], "cached": True}

    # Make API request (implementation details omitted)
    repos = await _api_request("GET", f"/orgs/{owner}/repos?type={type}")

    result = [{
        "name": repo["name"],
        "description": repo.get("description"),
        "url": repo["html_url"],
        "stars": repo.get("stargazers_count", 0),
    } for repo in repos[:limit]]

    _set_cached(cache_key, result)
    return {"repos": result, "count": len(result)}


async def sync_to_tasks(
    owner: str,
    repo: str,
    project_name: str,
    labels: str = "",
) -> dict[str, Any]:
    """Sync GitHub issues to PMS tasks.

    Cross-system integration example: GitHub issues become PMS tasks.
    """
    issues_result = await list_issues(owner, repo, state="open", labels=labels)

    if "error" in issues_result:
        return issues_result

    synced = []
    for issue in issues_result["issues"]:
        task_data = {
            "title": f"[GH#{issue['number']}] {issue['title']}",
            "description": f"Synced from GitHub: {issue['url']}",
            "tags": ["github", f"gh-{owner}/{repo}"] + issue["labels"],
            "priority": "high" if "priority:high" in issue["labels"] else "medium",
        }
        synced.append({
            "github_issue": issue["number"],
            "task_title": task_data["title"],
        })

    return {
        "synced": len(synced),
        "details": synced,
    }


# Event hooks for automation
async def on_task_completed(task_id: str, title: str, tags: list = None, **kwargs):
    """Handle task completion - update linked GitHub issue."""
    tags = tags or []
    github_tags = [t for t in tags if t.startswith("gh-")]

    if github_tags:
        print(f"[github] Task completed with GitHub link: {title}")
        # Would close the linked GitHub issue here


async def initialize(config: dict = None):
    """Initialize plugin with configuration."""
    global _config
    if config:
        _config.update(config)

    # Check for token in environment
    if not _config.get("github_token"):
        _config["github_token"] = os.environ.get("GITHUB_TOKEN")

    if not _config.get("github_token"):
        print("[github] Warning: No GitHub token configured!")
    else:
        print("[github] Plugin initialized successfully")
```

**Usage:**

```bash
# Configure with token
export GITHUB_TOKEN=ghp_xxxxxxxxxxxx
pms plugin start github-integration

# List repositories
pms plugin call github.list_repos --arg owner=microsoft --arg limit=10

# Create an issue
pms plugin call github.create_issue \
    --arg owner=my-org \
    --arg repo=my-project \
    --arg title="Bug: Login fails" \
    --arg body="Steps to reproduce..."

# Sync issues to PMS tasks
pms plugin call github.sync_to_tasks \
    --arg owner=my-org \
    --arg repo=my-project \
    --arg project_name="My Project"
```

### Key Concepts from Advanced Plugins

| Concept           | Description                                                               |
| ----------------- | ------------------------------------------------------------------------- |
| Secret Management | `secret: true` marks sensitive config, `env_var` for environment fallback |
| Caching           | Implement TTL-based caching for expensive operations                      |
| Cross-System Sync | Bidirectional data flow between systems                                   |
| Event Automation  | Hooks that trigger actions on system events                               |
| Dependencies      | Declare Python package requirements                                       |
| Resource Limits   | `max_memory_mb`, `timeout`, `max_concurrent`                              |

---

## Self-Building Plugins

The most advanced capability: plugins that create other plugins. This enables the system to extend itself.

### Example: Plugin Factory

**Location:** `examples/plugins/self-building/plugin-factory/`

A meta-plugin that generates new plugins dynamically.

**Capabilities:**

- Generate complete plugins from specifications
- Add tools to existing plugins incrementally
- Generate DSL files without Python
- Analyze source code and create wrapper plugins
- Template-based plugin creation

**plugin.json:**

```json
{
  "name": "plugin-factory",
  "version": "1.0.0",
  "description": "Meta-plugin that creates other plugins dynamically",
  "type": "runtime",
  "capabilities": ["filesystem_write", "tools", "namespaces"],
  "tools": [
    {
      "name": "create_plugin",
      "description": "Generate a new plugin from a description",
      "parameters": {
        "name": { "type": "string", "required": true },
        "description": { "type": "string", "required": true },
        "tools": { "type": "list", "required": true }
      }
    },
    {
      "name": "create_tool",
      "description": "Add a tool to an existing plugin",
      "parameters": {
        "plugin_name": { "type": "string", "required": true },
        "tool_name": { "type": "string", "required": true },
        "description": { "type": "string", "required": true }
      }
    },
    {
      "name": "create_from_template",
      "description": "Create from predefined template",
      "parameters": {
        "template": { "type": "string", "required": true },
        "name": { "type": "string", "required": true }
      }
    },
    {
      "name": "analyze_and_generate",
      "description": "Analyze code and generate a plugin",
      "parameters": {
        "source": { "type": "string", "required": true },
        "plugin_name": { "type": "string", "required": true }
      }
    }
  ]
}
```

**Usage Examples:**

**1. Create a plugin from description:**

```bash
pms plugin call plugin-factory.create_plugin \
    --arg name=my-utils \
    --arg description="Utility functions for my workflow" \
    --arg tools='[
        {"name": "format_date", "description": "Format a date string", "params": {"date": "string", "format": "string"}},
        {"name": "slugify", "description": "Convert text to URL slug", "params": {"text": "string"}}
    ]'
```

**Output:**

```json
{
  "success": true,
  "plugin_name": "my-utils",
  "path": "~/.pms/plugins/my-utils",
  "files": ["plugin.json", "main.py", "README.md"],
  "tools": ["format_date", "slugify"],
  "next_steps": [
    "pms plugin discover ~/.pms/plugins",
    "pms plugin start my-utils"
  ]
}
```

**2. Create DSL-only tools:**

```bash
pms plugin call plugin-factory.create_dsl_tools \
    --arg name=math-helpers \
    --arg tools='[
        {"name": "percent", "description": "Calculate percentage", "logic": "x / total * 100"},
        {"name": "average", "description": "Calculate average", "logic": "sum(values) / len(values)"}
    ]'
```

**3. Use a template:**

```bash
pms plugin call plugin-factory.list_templates
# Output:
# {
#   "templates": {
#     "api-integration": {
#       "description": "Template for REST API integrations",
#       "capabilities": ["network"],
#       "default_tools": ["list", "get", "create", "update", "delete"]
#     },
#     "file-processor": {...},
#     "automation": {...},
#     "data-transformer": {...}
#   }
# }

pms plugin call plugin-factory.create_from_template \
    --arg template=api-integration \
    --arg name=slack-integration
```

**4. Analyze existing code:**

```bash
pms plugin call plugin-factory.analyze_and_generate \
    --arg source=./my_module.py \
    --arg plugin_name=my-module-tools
```

### The Self-Building Philosophy

> "The most powerful systems are those that can improve themselves."

By enabling plugins to create plugins, PMS becomes an infinitely extensible platform:

```
Need → "I need a tool to do X"
       ↓
Plugin Factory → Generates tool
       ↓
New Capability → Available immediately
       ↓
Use → Workflow continues uninterrupted
```

This creates a recursive enhancement loop:

1. User identifies need
2. Plugin factory creates solution
3. Solution becomes part of the platform
4. Platform capabilities expand
5. More sophisticated needs can be addressed
6. Repeat

---

## Integration Workflows

Combining multiple plugins for complex workflows.

### Workflow 1: Code Analysis Pipeline

```bash
# 1. Use file-utils to find files
pms plugin call file-utils.find_files \
    --arg directory=./src \
    --arg pattern="**/*.py" > files.json

# 2. Count lines per file
pms plugin call file-utils.count_lines \
    --arg path=./src \
    --arg pattern="*.py"

# 3. Search for specific patterns
pms plugin call file-utils.search_content \
    --arg directory=./src \
    --arg query="TODO" \
    --arg file_pattern="*.py"
```

### Workflow 2: GitHub → PMS Task Sync

```bash
# 1. Sync GitHub issues to PMS tasks
pms plugin call github.sync_to_tasks \
    --arg owner=my-org \
    --arg repo=my-project \
    --arg project_name="Q1 Sprint"

# 2. When tasks complete, GitHub issues auto-close
# (via on_task_completed hook)
pms task complete "Fix login bug"
# → GitHub issue #42 automatically closed
```

### Workflow 3: Self-Extending Development

```bash
# 1. Analyze existing utility module
pms plugin call plugin-factory.analyze_and_generate \
    --arg source=./utils/text_processing.py \
    --arg plugin_name=text-tools

# 2. Discover new plugin
pms plugin discover ~/.pms/plugins

# 3. Start and use immediately
pms plugin start text-tools
pms plugin call text-tools.clean_text --arg text="  hello   world  "
```

### Workflow 4: Event-Driven Automation

Configure plugins to react to system events:

```python
# In your plugin's main.py

async def on_project_created(project_id: str, name: str, **kwargs):
    """When a new project is created, set up GitHub integration."""
    # Check if project name matches a GitHub repo
    if await github_repo_exists(name):
        # Auto-sync issues
        await sync_to_tasks(owner="my-org", repo=name, project_name=name)
        print(f"Auto-synced GitHub issues for {name}")

async def on_task_completed(task_id: str, title: str, tags: list, **kwargs):
    """When a GitHub-linked task completes, close the issue."""
    for tag in tags:
        if tag.startswith("gh-"):
            # Parse and close GitHub issue
            await close_github_issue(tag)
```

---

## Best Practices

### Security

1. **Request minimum capabilities** - Only ask for what you need
2. **Validate all inputs** - Never trust user input
3. **Use secrets properly** - Mark sensitive config with `secret: true`
4. **Sandbox by default** - Set `sandbox: true` unless you have good reason not to

### Performance

1. **Cache expensive operations** - Especially API calls
2. **Use async throughout** - All tool functions must be `async def`
3. **Set appropriate timeouts** - Don't let operations hang forever
4. **Limit concurrent operations** - Use `max_concurrent` setting

### Reliability

1. **Return structured errors** - `{"error": "message"}` not exceptions
2. **Handle all exceptions** - Catch and convert to structured responses
3. **Implement idempotency** - Same input should produce same output
4. **Log appropriately** - Use `print()` for operational logs

### Code Quality

1. **Type hints everywhere** - Use proper Python type annotations
2. **Document tools thoroughly** - Docstrings become tool descriptions
3. **Keep tools focused** - One tool, one purpose
4. **Version your plugins** - Semantic versioning in `plugin.json`

### Testing

```python
# Example test for a plugin tool
import pytest
from my_plugin import count_lines

@pytest.mark.asyncio
async def test_count_lines_single_file(tmp_path):
    # Create test file
    test_file = tmp_path / "test.txt"
    test_file.write_text("line 1\nline 2\nline 3")

    # Call tool
    result = await count_lines(str(test_file))

    # Verify
    assert result["total_lines"] == 3
    assert result["total_files"] == 1
    assert not "error" in result
```

---

## API Reference

### Plugin Manifest Schema

```json
{
  "name": "string (required)",
  "version": "string (required, semver)",
  "description": "string",
  "author": "string",
  "license": "string",
  "homepage": "string (url)",
  "type": "extension | integration | runtime",
  "entrypoint": "string (default: main.py)",
  "runtime": "python",
  "sandbox": "boolean (default: true)",
  "capabilities": [
    "filesystem_read",
    "filesystem_write",
    "network",
    "subprocess",
    "events",
    "tools",
    "namespaces"
  ],
  "max_memory_mb": "integer",
  "timeout": "float (seconds)",
  "max_concurrent": "integer",
  "tools": [
    {
      "name": "string (required)",
      "description": "string",
      "parameters": {
        "param_name": {
          "type": "string | int | float | bool | list | dict",
          "required": "boolean",
          "default": "any",
          "description": "string"
        }
      },
      "timeout": "float",
      "cacheable": "boolean",
      "cache_ttl": "integer (seconds)"
    }
  ],
  "hooks": [
    {
      "event": "task_created | task_completed | project_created | ...",
      "handler": "string (function name)",
      "priority": "integer (higher = earlier)",
      "filter": { "has_tag": "string", "...": "..." }
    }
  ],
  "dependencies": [
    {
      "name": "string",
      "version": "string (pip specifier)",
      "type": "python"
    }
  ],
  "config_schema": {
    "option_name": {
      "type": "string | int | bool | list",
      "required": "boolean",
      "default": "any",
      "secret": "boolean",
      "env_var": "string",
      "description": "string"
    }
  },
  "on_load": "string (function name)",
  "on_unload": "string (function name)",
  "on_enable": "string (function name)",
  "on_disable": "string (function name)"
}
```

### CLI Commands

```bash
# Discovery and management
pms plugin discover <path>     # Find plugins in directory
pms plugin list                # List all known plugins
pms plugin show <name>         # Show plugin details

# Lifecycle
pms plugin start <name> [--config file.json]
pms plugin stop <name>
pms plugin restart <name>

# Tool execution
pms plugin tools [--plugin name]  # List available tools
pms plugin call <plugin.tool> --arg key=value ...
pms plugin stats [--plugin name]  # Show execution statistics
```

### DSL Syntax

```
## Comments start with ##

tool tool_name:
    description: "What this tool does"
    param param_name: type
    param optional_param: type = default_value

    when condition:
        return result_if_true
    when another_condition:
        return another_result
    otherwise:
        return default_result
```

---

## Next Steps

1. **Try the examples** - Start with `hello-world`, work up to `plugin-factory`
2. **Build your own** - Use the quick start guide to create something useful
3. **Share your plugins** - Contribute to the community
4. **Extend the factory** - Add new templates for common patterns

Happy plugin building!
