# PMS Tool Development Guide

This guide explains how to add new tools to PMS following the pluggable architecture pattern. The system is designed to scale to 1,000+ tools while maintaining discoverability through Claude's Tool Search feature.

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Quick Start: Adding a Tool](#quick-start-adding-a-tool)
- [Tool Categories and Organization](#tool-categories-and-organization)
- [Tool Search and Discoverability](#tool-search-and-discoverability)
- [Creating a New Tool Module](#creating-a-new-tool-module)
- [Best Practices for 1000+ Tools](#best-practices-for-1000-tools)
- [Testing Tools](#testing-tools)
- [Examples](#examples)

---

## Architecture Overview

PMS tools follow a **pluggable module pattern**:

```
pms/tools/
├── __init__.py              # Central exports and registration
├── server.py                # MCP server factory with tool search
├── registry.py              # Tool metadata for discoverability
├── project_tools.py         # Project/task tools (16 tools)
├── remote_tools.py          # SSH/rsync tools (6 tools)
├── aws_tools.py             # AWS spot/test tools (9 tools)
└── <your_module>_tools.py   # Your new tools
```

### Key Principles

1. **Self-contained modules**: Each tool module is independent
2. **Dependency injection**: Services injected via `set_*_service()` functions
3. **Registry-based discovery**: Tools registered with metadata for search
4. **Deferred loading**: Non-core tools discovered on-demand via tool search

### Data Flow

```
Tool Module                    Registry                      Server
─────────────                  ────────                      ──────
@tool decorator     ───────►   ToolMetadata      ───────►    MCP Server
set_*_service()                (category,                    (with defer_loading)
ALL_*_TOOLS                     keywords,
                                is_core)
```

---

## Quick Start: Adding a Tool

### Step 1: Add to Existing Module

For simple additions, add to an existing module:

```python
# In pms/tools/project_tools.py

@tool(
    "search_tasks",
    "Search tasks by keyword across all projects",
    {"query": str, "status": str, "limit": int},
)
async def search_tasks(args: dict[str, Any]) -> dict[str, Any]:
    """Search tasks by keyword."""
    service = _get_task_service()

    results = await service.search_tasks(
        query=args["query"],
        status=args.get("status"),
        limit=args.get("limit", 20),
    )

    # Format response
    lines = [f"Found {len(results)} tasks:"]
    for task in results:
        lines.append(f"- [{task.status.value}] {task.title}")

    return {
        "content": [{"type": "text", "text": "\n".join(lines)}]
    }
```

### Step 2: Add to ALL\_\*\_TOOLS List

```python
# At bottom of the module
ALL_PROJECT_TOOLS = [
    create_project,
    list_projects,
    # ... existing tools ...
    search_tasks,  # Add new tool
]
```

### Step 3: Register in Registry

```python
# In pms/tools/registry.py

TOOL_REGISTRY: list[ToolMetadata] = [
    # ... existing tools ...

    ToolMetadata(
        name="search_tasks",
        description="Search tasks by keyword across all projects",
        category=ToolCategory.TASK,
        is_core=False,  # Will be deferred for tool search
        search_keywords=("find", "filter", "query", "lookup"),
    ),
]
```

### Step 4: Update Tool Names

```python
# In pms/tools/server.py

PROJECT_TOOL_NAMES = [
    # ... existing names ...
    "mcp__pms__search_tasks",
]
```

---

## Tool Categories and Organization

### Existing Categories

```python
class ToolCategory(Enum):
    PROJECT = "project"      # Project CRUD, stats, dashboard
    TASK = "task"            # Task CRUD, status, dependencies
    REMOTE = "remote"        # SSH, rsync operations
    AWS_SPOT = "aws_spot"    # Spot instance discovery/management
    AWS_TEST = "aws_test"    # Test server operations
```

### Adding New Categories

For new domains (e.g., CI/CD, notifications, analytics):

```python
# In pms/tools/registry.py

class ToolCategory(Enum):
    # Existing
    PROJECT = "project"
    TASK = "task"
    REMOTE = "remote"
    AWS_SPOT = "aws_spot"
    AWS_TEST = "aws_test"

    # New categories
    CICD = "cicd"              # CI/CD pipelines
    NOTIFICATIONS = "notifications"  # Alerts, webhooks
    ANALYTICS = "analytics"    # Reports, metrics
    INTEGRATIONS = "integrations"  # Third-party services
```

### Category Guidelines

| Category        | Use For                | Example Tools          |
| --------------- | ---------------------- | ---------------------- |
| `PROJECT`       | Project lifecycle      | create, archive, stats |
| `TASK`          | Task management        | create, assign, track  |
| `REMOTE`        | Server operations      | SSH, rsync, deploy     |
| `AWS_*`         | Cloud infrastructure   | spot, EC2, S3          |
| `CICD`          | Build/deploy pipelines | trigger, status, logs  |
| `NOTIFICATIONS` | Alerts and messaging   | slack, email, webhook  |
| `ANALYTICS`     | Data and reporting     | reports, dashboards    |
| `INTEGRATIONS`  | External services      | github, jira, linear   |

---

## Tool Search and Discoverability

### How Tool Search Works

1. **Core tools** (8 tools): Always loaded, immediate access
2. **Extended tools**: Discovered via regex/BM25 search on:
   - Tool name
   - Description
   - Argument names
   - Search keywords (from registry)

### Making Tools Discoverable

#### Good Tool Name

```python
@tool("sync_project_to_github", ...)  # Clear, searchable
```

#### Bad Tool Name

```python
@tool("sp2gh", ...)  # Cryptic, won't be found
```

#### Good Description

```python
"Synchronize project files to a GitHub repository with commit message"
```

#### Bad Description

```python
"Sync to GH"  # Too short, missing keywords
```

#### Search Keywords

Add synonyms and related terms:

```python
ToolMetadata(
    name="deploy_to_production",
    description="Deploy project to production servers",
    category=ToolCategory.REMOTE,
    is_core=False,
    search_keywords=(
        "release",      # Synonym
        "ship",         # Colloquial
        "publish",      # Related action
        "live",         # Target environment
        "rollout",      # Process name
    ),
)
```

### Core vs Extended Tools

**Core tools** (`is_core=True`):

- Most frequently used (>50% of sessions)
- Essential for basic workflows
- Always loaded (no search needed)
- Limit to 10-15 tools max

**Extended tools** (`is_core=False`):

- Specialized functionality
- Discovered via search
- Can scale to 1000s
- Grouped by category for organization

---

## Creating a New Tool Module

For a new domain (e.g., GitHub integration), create a new module:

### Step 1: Create the Module

```python
# pms/tools/github_tools.py
"""Agent tools for GitHub integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from claude_code_sdk import tool

if TYPE_CHECKING:
    from pms.integrations.github import GitHubService

# Global service instance
_github_service: GitHubService | None = None


def set_github_service(github_service: GitHubService) -> None:
    """Set the GitHub service instance for tools to use."""
    global _github_service
    _github_service = github_service


def _get_github_service() -> GitHubService:
    """Get GitHub service or raise if not initialized."""
    if _github_service is None:
        raise RuntimeError("GitHub service not initialized. Call set_github_service first.")
    return _github_service


# =============================================================================
# GitHub Tools
# =============================================================================

@tool(
    "list_github_repos",
    "List GitHub repositories for the authenticated user or organization",
    {"org": str, "type": str, "limit": int},
)
async def list_github_repos(args: dict[str, Any]) -> dict[str, Any]:
    """List GitHub repositories."""
    service = _get_github_service()

    repos = await service.list_repos(
        org=args.get("org"),
        repo_type=args.get("type", "all"),
        limit=args.get("limit", 30),
    )

    lines = [f"Found {len(repos)} repositories:"]
    for repo in repos:
        lines.append(f"- {repo.full_name} ({repo.visibility})")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "create_github_issue",
    "Create a new issue in a GitHub repository",
    {"repo": str, "title": str, "body": str, "labels": str},
)
async def create_github_issue(args: dict[str, Any]) -> dict[str, Any]:
    """Create a GitHub issue."""
    service = _get_github_service()

    labels = None
    if args.get("labels"):
        labels = [l.strip() for l in args["labels"].split(",")]

    issue = await service.create_issue(
        repo=args["repo"],
        title=args["title"],
        body=args.get("body", ""),
        labels=labels,
    )

    return {
        "content": [{
            "type": "text",
            "text": f"Created issue #{issue.number}: {issue.title}\nURL: {issue.html_url}",
        }]
    }


@tool(
    "sync_github_issues_to_tasks",
    "Import GitHub issues as PMS tasks for a project",
    {"repo": str, "project": str, "labels": str, "state": str},
)
async def sync_github_issues_to_tasks(args: dict[str, Any]) -> dict[str, Any]:
    """Sync GitHub issues to PMS tasks."""
    service = _get_github_service()

    result = await service.sync_issues_to_tasks(
        repo=args["repo"],
        project_name=args["project"],
        labels=args.get("labels"),
        state=args.get("state", "open"),
    )

    return {
        "content": [{
            "type": "text",
            "text": f"Synced {result.created} new tasks, updated {result.updated} existing.",
        }]
    }


# Export all tools
ALL_GITHUB_TOOLS = [
    list_github_repos,
    create_github_issue,
    sync_github_issues_to_tasks,
]
```

### Step 2: Add to Registry

```python
# In pms/tools/registry.py

class ToolCategory(Enum):
    # ... existing ...
    GITHUB = "github"


TOOL_REGISTRY: list[ToolMetadata] = [
    # ... existing tools ...

    # GitHub Tools
    ToolMetadata(
        name="list_github_repos",
        description="List GitHub repositories for the authenticated user or organization",
        category=ToolCategory.GITHUB,
        is_core=False,
        search_keywords=("repositories", "repos", "git", "list"),
    ),
    ToolMetadata(
        name="create_github_issue",
        description="Create a new issue in a GitHub repository",
        category=ToolCategory.GITHUB,
        is_core=False,
        search_keywords=("issue", "bug", "feature", "ticket", "create"),
    ),
    ToolMetadata(
        name="sync_github_issues_to_tasks",
        description="Import GitHub issues as PMS tasks for a project",
        category=ToolCategory.GITHUB,
        is_core=False,
        search_keywords=("import", "sync", "issues", "tasks", "migrate"),
    ),
]
```

### Step 3: Update Server Factory

```python
# In pms/tools/server.py

# Add import (with optional handling)
try:
    from pms.tools.github_tools import (
        ALL_GITHUB_TOOLS,
        set_github_service,
    )
    _GITHUB_AVAILABLE = True
except ImportError:
    ALL_GITHUB_TOOLS = []
    _GITHUB_AVAILABLE = False
    def set_github_service(*args, **kwargs):
        pass

# Update create_pms_server signature
def create_pms_server(
    project_service: ProjectService,
    task_service: TaskService,
    remote_service: RemoteService | None = None,
    github_service: GitHubService | None = None,  # Add new service
    # ... other services ...
):
    # ... existing code ...

    # Initialize GitHub tools if service provided
    if _GITHUB_AVAILABLE and github_service is not None:
        set_github_service(github_service)
        all_tools.extend(ALL_GITHUB_TOOLS)

# Add tool names
GITHUB_TOOL_NAMES = [
    "mcp__pms__list_github_repos",
    "mcp__pms__create_github_issue",
    "mcp__pms__sync_github_issues_to_tasks",
]

PMS_TOOL_NAMES = PROJECT_TOOL_NAMES + REMOTE_TOOL_NAMES + AWS_TOOL_NAMES + GITHUB_TOOL_NAMES
```

### Step 4: Update Exports

```python
# In pms/tools/__init__.py

from pms.tools.github_tools import (
    ALL_GITHUB_TOOLS,
    set_github_service,
)

__all__ = [
    # ... existing ...
    "ALL_GITHUB_TOOLS",
    "set_github_service",
]
```

---

## Best Practices for 1000+ Tools

### 1. Hierarchical Categories

For large tool libraries, use hierarchical naming:

```python
class ToolCategory(Enum):
    # Top-level categories
    PROJECT = "project"
    TASK = "task"

    # Cloud providers (sub-categories)
    AWS_EC2 = "aws.ec2"
    AWS_S3 = "aws.s3"
    AWS_LAMBDA = "aws.lambda"
    GCP_COMPUTE = "gcp.compute"
    GCP_STORAGE = "gcp.storage"
    AZURE_VM = "azure.vm"

    # Integrations
    GITHUB = "integrations.github"
    GITLAB = "integrations.gitlab"
    JIRA = "integrations.jira"
    SLACK = "integrations.slack"
```

### 2. Tool Naming Conventions

```
<domain>_<action>_<object>

Examples:
- github_create_issue
- aws_launch_instance
- slack_send_message
- jira_update_ticket
```

### 3. Keyword Strategy

For 1000+ tools, keywords are critical for discovery:

```python
ToolMetadata(
    name="aws_s3_upload_file",
    description="Upload a file to an S3 bucket",
    category=ToolCategory.AWS_S3,
    is_core=False,
    search_keywords=(
        # Action synonyms
        "upload", "put", "store", "save",
        # Object synonyms
        "file", "object", "blob", "data",
        # Domain terms
        "s3", "bucket", "aws", "cloud", "storage",
        # Use cases
        "backup", "archive", "deploy",
    ),
)
```

### 4. Module Organization

For 1000+ tools, organize by domain:

```
pms/tools/
├── __init__.py
├── server.py
├── registry.py
│
├── core/                    # Core tools (always loaded)
│   ├── project_tools.py
│   └── task_tools.py
│
├── remote/                  # Remote operations
│   ├── ssh_tools.py
│   └── rsync_tools.py
│
├── cloud/                   # Cloud providers
│   ├── aws/
│   │   ├── ec2_tools.py
│   │   ├── s3_tools.py
│   │   └── lambda_tools.py
│   ├── gcp/
│   │   └── ...
│   └── azure/
│       └── ...
│
├── integrations/            # Third-party services
│   ├── github_tools.py
│   ├── gitlab_tools.py
│   ├── jira_tools.py
│   └── slack_tools.py
│
└── analytics/               # Reporting tools
    ├── reports_tools.py
    └── metrics_tools.py
```

### 5. Lazy Loading for Large Libraries

For very large tool sets, implement lazy loading:

```python
# In pms/tools/loader.py

from typing import Callable
import importlib

_TOOL_MODULES: dict[str, str] = {
    "github": "pms.tools.integrations.github_tools",
    "jira": "pms.tools.integrations.jira_tools",
    "aws_ec2": "pms.tools.cloud.aws.ec2_tools",
    # ... hundreds more ...
}

_loaded_modules: dict[str, any] = {}

def load_tool_module(name: str):
    """Lazy-load a tool module."""
    if name not in _loaded_modules:
        module_path = _TOOL_MODULES.get(name)
        if module_path:
            _loaded_modules[name] = importlib.import_module(module_path)
    return _loaded_modules.get(name)

def get_tools_for_category(category: str) -> list:
    """Load and return tools for a category."""
    module = load_tool_module(category)
    if module and hasattr(module, f"ALL_{category.upper()}_TOOLS"):
        return getattr(module, f"ALL_{category.upper()}_TOOLS")
    return []
```

### 6. Registry as Database

For 10,000+ tools, consider a database-backed registry:

```python
# pms/tools/registry_db.py

import sqlite3
from dataclasses import dataclass

@dataclass
class ToolRecord:
    name: str
    description: str
    category: str
    is_core: bool
    keywords: list[str]
    module_path: str

class ToolRegistry:
    def __init__(self, db_path: str):
        self.conn = sqlite3.connect(db_path)
        self._init_schema()

    def _init_schema(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS tools (
                name TEXT PRIMARY KEY,
                description TEXT,
                category TEXT,
                is_core BOOLEAN,
                keywords TEXT,  -- JSON array
                module_path TEXT
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_tools_category ON tools(category)
        """)
        self.conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS tools_fts USING fts5(
                name, description, keywords,
                content='tools'
            )
        """)

    def search(self, query: str, limit: int = 10) -> list[ToolRecord]:
        """Full-text search across tools."""
        cursor = self.conn.execute("""
            SELECT t.* FROM tools t
            JOIN tools_fts fts ON t.name = fts.name
            WHERE tools_fts MATCH ?
            LIMIT ?
        """, (query, limit))
        return [ToolRecord(*row) for row in cursor.fetchall()]

    def get_by_category(self, category: str) -> list[ToolRecord]:
        """Get all tools in a category."""
        cursor = self.conn.execute(
            "SELECT * FROM tools WHERE category = ?", (category,)
        )
        return [ToolRecord(*row) for row in cursor.fetchall()]
```

---

## Testing Tools

### Unit Tests

```python
# tests/unit/test_github_tools.py

import pytest
from pms.tools import ALL_GITHUB_TOOLS, GITHUB_TOOL_NAMES

class TestGitHubTools:
    def test_all_tools_defined(self):
        assert len(ALL_GITHUB_TOOLS) == 3
        assert len(GITHUB_TOOL_NAMES) == 3

    def test_tool_names_match(self):
        for name in GITHUB_TOOL_NAMES:
            assert name.startswith("mcp__pms__")

    def test_tools_have_handlers(self):
        for tool in ALL_GITHUB_TOOLS:
            assert hasattr(tool, "handler")
            assert callable(tool.handler)
```

### Integration Tests

```python
# tests/integration/test_github_tools.py

import pytest
from unittest.mock import AsyncMock, MagicMock

from pms.tools.github_tools import (
    list_github_repos,
    set_github_service,
)

@pytest.fixture
def mock_github_service():
    service = MagicMock()
    service.list_repos = AsyncMock(return_value=[
        MagicMock(full_name="org/repo1", visibility="public"),
        MagicMock(full_name="org/repo2", visibility="private"),
    ])
    set_github_service(service)
    return service

@pytest.mark.asyncio
async def test_list_github_repos(mock_github_service):
    result = await list_github_repos({"limit": 10})

    assert "content" in result
    assert "Found 2 repositories" in result["content"][0]["text"]
    mock_github_service.list_repos.assert_called_once()
```

---

## Examples

### Example 1: Simple Tool

```python
@tool(
    "get_task_count",
    "Get the total number of tasks across all projects",
    {},
)
async def get_task_count(args: dict[str, Any]) -> dict[str, Any]:
    service = _get_task_service()
    count = await service.get_total_count()
    return {"content": [{"type": "text", "text": f"Total tasks: {count}"}]}
```

### Example 2: Tool with Complex Input

```python
@tool(
    "create_milestone_with_tasks",
    "Create a milestone and associated tasks in one operation",
    {
        "project": str,
        "milestone_name": str,
        "due_date": str,
        "tasks": str,  # JSON array of task definitions
    },
)
async def create_milestone_with_tasks(args: dict[str, Any]) -> dict[str, Any]:
    import json

    service = _get_project_service()
    task_service = _get_task_service()

    # Parse tasks JSON
    tasks_data = json.loads(args.get("tasks", "[]"))

    # Create milestone
    milestone = await service.create_milestone(
        project_name=args["project"],
        name=args["milestone_name"],
        due_date=args.get("due_date"),
    )

    # Create tasks
    created_tasks = []
    for task_def in tasks_data:
        task = await task_service.create_task(
            project_id=milestone.project_id,
            milestone_id=milestone.id,
            title=task_def["title"],
            priority=task_def.get("priority", "medium"),
        )
        created_tasks.append(task)

    return {
        "content": [{
            "type": "text",
            "text": (
                f"Created milestone '{milestone.name}' "
                f"with {len(created_tasks)} tasks"
            ),
        }]
    }
```

### Example 3: Tool with Error Handling

```python
@tool(
    "deploy_to_environment",
    "Deploy a project to a specified environment",
    {"project": str, "environment": str, "version": str},
)
async def deploy_to_environment(args: dict[str, Any]) -> dict[str, Any]:
    service = _get_deploy_service()

    try:
        result = await service.deploy(
            project=args["project"],
            environment=args["environment"],
            version=args.get("version", "latest"),
        )

        return {
            "content": [{
                "type": "text",
                "text": (
                    f"Deployed {args['project']} v{result.version} "
                    f"to {args['environment']}\n"
                    f"URL: {result.url}\n"
                    f"Status: {result.status}"
                ),
            }]
        }

    except DeploymentError as e:
        return {
            "content": [{
                "type": "text",
                "text": f"Deployment failed: {e.message}",
            }],
            "is_error": True,
        }
```

---

## Checklist for New Tools

- [ ] Tool function with `@tool` decorator
- [ ] Clear, searchable name (`domain_action_object`)
- [ ] Descriptive description (50-100 chars)
- [ ] Added to `ALL_*_TOOLS` list
- [ ] Added to `TOOL_REGISTRY` with metadata
- [ ] Added to `*_TOOL_NAMES` constant
- [ ] Added to `PMS_TOOL_NAMES` combined list
- [ ] Updated `__init__.py` exports
- [ ] Unit tests for tool definition
- [ ] Integration tests for tool logic
- [ ] Keywords for discoverability (5-10 terms)
- [ ] Appropriate `is_core` setting (usually `False`)

---

## Summary

The PMS tool system is designed for scalability:

| Scale          | Approach                              |
| -------------- | ------------------------------------- |
| 10-50 tools    | Single registry file, manual exports  |
| 50-200 tools   | Module-per-domain, category-based     |
| 200-1000 tools | Hierarchical categories, lazy loading |
| 1000+ tools    | Database-backed registry, FTS search  |

Key principles:

1. **Discoverability**: Good names, descriptions, keywords
2. **Organization**: Clear categories and module structure
3. **Lazy loading**: Only load what's needed
4. **Tool search**: Let Claude discover tools on-demand
