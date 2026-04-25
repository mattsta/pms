"""GitHub Integration Plugin - Advanced example.

This example demonstrates:
- Real-world API integration
- Complex tool implementations
- Secret/credential handling
- Caching for performance
- Event hooks for automation
- Cross-system synchronization (GitHub <-> PMS)
- Error handling and retries
- Rate limiting awareness

Usage:
    # Configure with your GitHub token
    echo '{"github_token": "ghp_xxx"}' > github-config.json
    pms plugin start github-integration --config github-config.json

    # Or use environment variable
    export GITHUB_TOKEN=ghp_xxx
    pms plugin start github-integration

    # Use the tools
    pms plugin call github.list_repos --arg owner=microsoft --arg limit=10
    pms plugin call github.create_issue --arg owner=my-org --arg repo=my-repo \
        --arg title="Bug: something broken" --arg body="Details here"

    # Sync GitHub issues to PMS tasks
    pms plugin call github.sync_to_tasks --arg owner=my-org --arg repo=my-repo \
        --arg project_name="My Project"
"""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from typing import Any

# Note: In a real plugin, httpx would be installed via dependencies
# For this example, we simulate API responses
MOCK_MODE = True

# =============================================================================
# Configuration
# =============================================================================

_config = {
    "github_token": None,
    "api_base_url": "https://api.github.com",
    "default_org": None,
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


def _set_cached(key: str, value: Any) -> None:
    """Cache a value."""
    _cache[key] = (value, datetime.now(UTC))


# =============================================================================
# HTTP Client (simulated for example)
# =============================================================================


async def _api_request(
    method: str,
    endpoint: str,
    data: dict | None = None,
) -> dict[str, Any]:
    """Make GitHub API request.

    In a real plugin, this would use httpx:
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method,
                url,
                headers={"Authorization": f"token {_config['github_token']}"},
                json=data,
            )
            return response.json()
    """
    if MOCK_MODE:
        return await _mock_api(method, endpoint, data)

    # Real implementation would go here
    raise NotImplementedError("Real HTTP client not implemented in example")


async def _mock_api(
    method: str,
    endpoint: str,
    data: dict | None = None,
) -> dict[str, Any]:
    """Mock API for demonstration."""
    await asyncio.sleep(0.1)  # Simulate network latency

    if "/repos" in endpoint and method == "GET":
        if "/issues" in endpoint:
            return _mock_issues()
        elif "/pulls" in endpoint:
            return _mock_prs()
        else:
            return _mock_repo()
    elif (
        "/orgs/" in endpoint
        and "/repos" in endpoint
        or "/users/" in endpoint
        and "/repos" in endpoint
    ):
        return _mock_repos()
    elif "/issues" in endpoint and method == "POST":
        return _mock_create_issue(data or {})

    return {"error": "Unknown endpoint"}


def _mock_repos() -> list[dict]:
    return [
        {
            "id": 1,
            "name": "awesome-project",
            "full_name": "example/awesome-project",
            "description": "An awesome project",
            "private": False,
            "html_url": "https://github.com/example/awesome-project",
            "stargazers_count": 1234,
            "forks_count": 56,
            "language": "Python",
            "updated_at": "2024-01-15T10:30:00Z",
        },
        {
            "id": 2,
            "name": "cool-library",
            "full_name": "example/cool-library",
            "description": "A cool library for doing things",
            "private": False,
            "html_url": "https://github.com/example/cool-library",
            "stargazers_count": 567,
            "forks_count": 23,
            "language": "TypeScript",
            "updated_at": "2024-01-14T15:45:00Z",
        },
    ]


def _mock_repo() -> dict:
    return {
        "id": 1,
        "name": "awesome-project",
        "full_name": "example/awesome-project",
        "description": "An awesome project",
        "private": False,
        "html_url": "https://github.com/example/awesome-project",
        "stargazers_count": 1234,
        "forks_count": 56,
        "open_issues_count": 12,
        "language": "Python",
        "default_branch": "main",
        "created_at": "2023-01-01T00:00:00Z",
        "updated_at": "2024-01-15T10:30:00Z",
    }


def _mock_issues() -> list[dict]:
    return [
        {
            "id": 101,
            "number": 42,
            "title": "Bug: Something is broken",
            "body": "When I try to do X, Y happens instead of Z",
            "state": "open",
            "labels": [{"name": "bug"}, {"name": "priority:high"}],
            "user": {"login": "reporter"},
            "html_url": "https://github.com/example/repo/issues/42",
            "created_at": "2024-01-10T09:00:00Z",
        },
        {
            "id": 102,
            "number": 43,
            "title": "Feature: Add dark mode",
            "body": "Please add dark mode support",
            "state": "open",
            "labels": [{"name": "enhancement"}],
            "user": {"login": "user123"},
            "html_url": "https://github.com/example/repo/issues/43",
            "created_at": "2024-01-11T14:30:00Z",
        },
    ]


def _mock_prs() -> list[dict]:
    return [
        {
            "id": 201,
            "number": 99,
            "title": "Fix: Resolve memory leak",
            "state": "open",
            "user": {"login": "contributor"},
            "html_url": "https://github.com/example/repo/pull/99",
            "created_at": "2024-01-14T11:00:00Z",
            "head": {"ref": "fix/memory-leak"},
            "base": {"ref": "main"},
        },
    ]


def _mock_create_issue(data: dict) -> dict:
    return {
        "id": 999,
        "number": 100,
        "title": data.get("title", "New Issue"),
        "body": data.get("body", ""),
        "state": "open",
        "html_url": "https://github.com/example/repo/issues/100",
        "created_at": datetime.now(UTC).isoformat(),
    }


# =============================================================================
# Tool Implementations
# =============================================================================


async def list_repos(
    owner: str,
    type: str = "all",
    limit: int = 30,
) -> dict[str, Any]:
    """List repositories for an organization or user.

    Args:
        owner: Organization or user name
        type: Filter type (all, public, private, forks, sources)
        limit: Maximum repositories to return

    Returns:
        List of repositories with metadata
    """
    cache_key = f"repos:{owner}:{type}"
    cached = _get_cached(cache_key)
    if cached:
        return {"repos": cached[:limit], "cached": True}

    # Determine if org or user
    endpoint = f"/orgs/{owner}/repos?type={type}&per_page={limit}"

    try:
        repos = await _api_request("GET", endpoint)

        # Format response
        result = []
        for repo in repos[:limit]:
            result.append(
                {
                    "name": repo["name"],
                    "full_name": repo["full_name"],
                    "description": repo.get("description"),
                    "url": repo["html_url"],
                    "stars": repo.get("stargazers_count", 0),
                    "forks": repo.get("forks_count", 0),
                    "language": repo.get("language"),
                    "updated": repo.get("updated_at"),
                }
            )

        _set_cached(cache_key, result)
        return {"repos": result, "count": len(result)}

    except Exception as e:
        return {"error": str(e)}


async def get_repo(owner: str, repo: str) -> dict[str, Any]:
    """Get detailed repository information.

    Args:
        owner: Repository owner
        repo: Repository name

    Returns:
        Detailed repository information
    """
    endpoint = f"/repos/{owner}/{repo}"

    try:
        data = await _api_request("GET", endpoint)

        return {
            "name": data["name"],
            "full_name": data["full_name"],
            "description": data.get("description"),
            "url": data["html_url"],
            "private": data.get("private", False),
            "stars": data.get("stargazers_count", 0),
            "forks": data.get("forks_count", 0),
            "open_issues": data.get("open_issues_count", 0),
            "language": data.get("language"),
            "default_branch": data.get("default_branch"),
            "created": data.get("created_at"),
            "updated": data.get("updated_at"),
        }

    except Exception as e:
        return {"error": str(e)}


async def list_issues(
    owner: str,
    repo: str,
    state: str = "open",
    labels: str = "",
) -> dict[str, Any]:
    """List repository issues.

    Args:
        owner: Repository owner
        repo: Repository name
        state: Issue state filter (open, closed, all)
        labels: Comma-separated label filter

    Returns:
        List of issues
    """
    endpoint = f"/repos/{owner}/{repo}/issues?state={state}"
    if labels:
        endpoint += f"&labels={labels}"

    try:
        issues = await _api_request("GET", endpoint)

        result = []
        for issue in issues:
            # Skip pull requests (they appear in issues API)
            if "pull_request" in issue:
                continue

            result.append(
                {
                    "number": issue["number"],
                    "title": issue["title"],
                    "state": issue["state"],
                    "labels": [l["name"] for l in issue.get("labels", [])],
                    "author": issue["user"]["login"],
                    "url": issue["html_url"],
                    "created": issue["created_at"],
                }
            )

        return {"issues": result, "count": len(result)}

    except Exception as e:
        return {"error": str(e)}


async def create_issue(
    owner: str,
    repo: str,
    title: str,
    body: str = "",
    labels: list[str] | None = None,
) -> dict[str, Any]:
    """Create a new issue.

    Args:
        owner: Repository owner
        repo: Repository name
        title: Issue title
        body: Issue body/description
        labels: List of labels to apply

    Returns:
        Created issue information
    """
    endpoint = f"/repos/{owner}/{repo}/issues"
    data = {"title": title, "body": body}
    if labels:
        data["labels"] = labels

    try:
        issue = await _api_request("POST", endpoint, data)

        return {
            "success": True,
            "number": issue["number"],
            "title": issue["title"],
            "url": issue["html_url"],
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


async def list_prs(
    owner: str,
    repo: str,
    state: str = "open",
) -> dict[str, Any]:
    """List pull requests.

    Args:
        owner: Repository owner
        repo: Repository name
        state: PR state (open, closed, all)

    Returns:
        List of pull requests
    """
    endpoint = f"/repos/{owner}/{repo}/pulls?state={state}"

    try:
        prs = await _api_request("GET", endpoint)

        result = []
        for pr in prs:
            result.append(
                {
                    "number": pr["number"],
                    "title": pr["title"],
                    "state": pr["state"],
                    "author": pr["user"]["login"],
                    "url": pr["html_url"],
                    "head": pr["head"]["ref"],
                    "base": pr["base"]["ref"],
                    "created": pr["created_at"],
                }
            )

        return {"pull_requests": result, "count": len(result)}

    except Exception as e:
        return {"error": str(e)}


async def sync_to_tasks(
    owner: str,
    repo: str,
    project_name: str,
    labels: str = "",
) -> dict[str, Any]:
    """Sync GitHub issues to PMS tasks.

    This demonstrates cross-system integration - taking data from
    GitHub and creating corresponding PMS tasks.

    Args:
        owner: Repository owner
        repo: Repository name
        project_name: PMS project to sync to
        labels: Only sync issues with these labels

    Returns:
        Sync results
    """
    # Get issues from GitHub
    issues_result = await list_issues(owner, repo, state="open", labels=labels)

    if "error" in issues_result:
        return issues_result

    issues = issues_result["issues"]
    synced = []
    errors = []

    for issue in issues:
        try:
            # In a real plugin, this would call PMS task service
            # For this example, we just track what would be created
            task_data = {
                "title": f"[GH#{issue['number']}] {issue['title']}",
                "description": f"Synced from GitHub: {issue['url']}",
                "tags": ["github", f"gh-{owner}/{repo}"] + issue["labels"],
                "priority": "high" if "priority:high" in issue["labels"] else "medium",
            }
            synced.append(
                {
                    "github_issue": issue["number"],
                    "task_title": task_data["title"],
                }
            )
        except Exception as e:
            errors.append(
                {
                    "github_issue": issue["number"],
                    "error": str(e),
                }
            )

    return {
        "synced": len(synced),
        "errors": len(errors),
        "details": synced,
        "error_details": errors or None,
    }


# =============================================================================
# Lifecycle Hooks
# =============================================================================


async def initialize(config: dict = None):
    """Initialize plugin with configuration.

    Called when plugin is loaded. Sets up credentials and connections.
    """
    global _config

    if config:
        _config.update(config)

    # Check for token in environment if not in config
    if not _config.get("github_token"):
        _config["github_token"] = os.environ.get("GITHUB_TOKEN")

    if not _config.get("github_token") and not MOCK_MODE:
        print("[github] Warning: No GitHub token configured!")
        print("[github] Set GITHUB_TOKEN env var or pass in config")
    else:
        print("[github] Plugin initialized successfully")
        if _config.get("default_org"):
            print(f"[github] Default org: {_config['default_org']}")


async def cleanup():
    """Cleanup when plugin is unloaded."""
    global _cache
    _cache.clear()
    print("[github] Plugin unloaded, cache cleared")


async def start_sync():
    """Called when plugin is enabled."""
    if _config.get("auto_sync"):
        print("[github] Auto-sync enabled")


async def stop_sync():
    """Called when plugin is disabled."""
    print("[github] Sync stopped")


# =============================================================================
# Event Hooks
# =============================================================================


async def on_task_completed(task_id: str, title: str, tags: list = None, **kwargs):
    """Handle task completion - update linked GitHub issue.

    When a PMS task linked to a GitHub issue is completed,
    this hook can automatically close the GitHub issue.
    """
    tags = tags or []

    # Check if this task is linked to GitHub
    github_tags = [t for t in tags if t.startswith("gh-")]
    if not github_tags:
        return

    print(f"[github] Task completed with GitHub link: {title}")

    # In a real plugin, we would:
    # 1. Parse the GitHub issue number from tags
    # 2. Call GitHub API to close the issue
    # 3. Add a comment linking to the PMS task


async def on_project_created(project_id: str, name: str, tags: list = None, **kwargs):
    """Handle project creation - offer to sync from GitHub.

    When a new project is created, offer to import issues from
    a linked GitHub repository.
    """
    if _config.get("auto_sync"):
        print(f"[github] New project '{name}' - checking for GitHub sync...")
        # Would check if project name matches a repo and auto-sync
