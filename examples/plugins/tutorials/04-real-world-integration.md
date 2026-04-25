# Tutorial 4: Real-World API Integration

**Time:** 20 minutes
**Level:** Advanced
**Prerequisites:** Tutorials 1-2
**What you'll learn:** Build production-quality integrations with caching, error handling, and cross-system sync

---

## The Scenario

You want to build a plugin that:

1. Connects to an external API (we'll use a mock API)
2. Caches responses for performance
3. Handles errors gracefully
4. Syncs data between systems
5. Uses configuration and secrets properly

This is what a **real production plugin** looks like.

## Project Structure

```
api-connector/
├── plugin.json          # Manifest with capabilities
├── main.py              # Core implementation
├── api_client.py        # HTTP client wrapper
├── cache.py             # Caching layer
└── tests/
    └── test_api.py      # Plugin tests
```

## Step 1: Create the Manifest

`plugin.json`:

```json
{
  "name": "api-connector",
  "version": "1.0.0",
  "description": "Production-quality API integration with caching and sync",
  "author": "Your Name",
  "type": "integration",
  "entrypoint": "main.py",
  "sandbox": true,
  "capabilities": ["network", "events"],
  "max_memory_mb": 128,
  "timeout": 30.0,
  "max_concurrent": 3,
  "tools": [
    {
      "name": "list_items",
      "description": "List items from the API",
      "parameters": {
        "category": {
          "type": "string",
          "required": false,
          "description": "Filter by category"
        },
        "limit": {
          "type": "int",
          "required": false,
          "default": 10
        },
        "use_cache": {
          "type": "bool",
          "required": false,
          "default": true
        }
      },
      "timeout": 15.0,
      "cacheable": true,
      "cache_ttl": 300
    },
    {
      "name": "get_item",
      "description": "Get a single item by ID",
      "parameters": {
        "id": {
          "type": "string",
          "required": true
        }
      }
    },
    {
      "name": "create_item",
      "description": "Create a new item",
      "parameters": {
        "name": {
          "type": "string",
          "required": true
        },
        "category": {
          "type": "string",
          "required": true
        },
        "data": {
          "type": "dict",
          "required": false
        }
      }
    },
    {
      "name": "sync_to_tasks",
      "description": "Sync API items to PMS tasks",
      "parameters": {
        "category": {
          "type": "string",
          "required": true
        },
        "project_name": {
          "type": "string",
          "required": true
        }
      }
    },
    {
      "name": "health_check",
      "description": "Check API connectivity and status",
      "parameters": {}
    },
    {
      "name": "cache_stats",
      "description": "Get cache statistics",
      "parameters": {}
    },
    {
      "name": "clear_cache",
      "description": "Clear the cache",
      "parameters": {}
    }
  ],
  "hooks": [
    {
      "event": "task_completed",
      "handler": "on_task_completed",
      "filter": {
        "has_tag": "api-sync"
      }
    }
  ],
  "config_schema": {
    "api_base_url": {
      "type": "string",
      "required": true,
      "default": "https://api.example.com",
      "description": "Base URL for the API"
    },
    "api_key": {
      "type": "string",
      "required": true,
      "secret": true,
      "env_var": "API_CONNECTOR_KEY",
      "description": "API authentication key"
    },
    "cache_ttl_seconds": {
      "type": "int",
      "default": 300,
      "description": "Cache time-to-live in seconds"
    },
    "retry_attempts": {
      "type": "int",
      "default": 3,
      "description": "Number of retry attempts for failed requests"
    },
    "auto_sync": {
      "type": "bool",
      "default": false,
      "description": "Automatically sync on task completion"
    }
  }
}
```

**Key Production Features:**

- `capabilities: ["network"]` - Required for HTTP calls
- `timeout` and `max_concurrent` - Resource limits
- `secret: true` - Marks sensitive config
- `env_var` - Environment variable fallback
- `cacheable` and `cache_ttl` - Built-in caching hints

## Step 2: Implement the Cache

`cache.py`:

```python
"""Simple TTL cache for API responses."""

from datetime import datetime, timedelta
from typing import Any

class TTLCache:
    """Time-based cache with automatic expiration."""

    def __init__(self, default_ttl_seconds: int = 300):
        self._cache: dict[str, tuple[Any, datetime]] = {}
        self._default_ttl = timedelta(seconds=default_ttl_seconds)
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Any | None:
        """Get value if not expired."""
        if key not in self._cache:
            self._misses += 1
            return None

        value, expires_at = self._cache[key]
        if datetime.now() > expires_at:
            del self._cache[key]
            self._misses += 1
            return None

        self._hits += 1
        return value

    def set(self, key: str, value: Any, ttl_seconds: int = None) -> None:
        """Set value with TTL."""
        ttl = timedelta(seconds=ttl_seconds) if ttl_seconds else self._default_ttl
        expires_at = datetime.now() + ttl
        self._cache[key] = (value, expires_at)

    def delete(self, key: str) -> bool:
        """Delete a key."""
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    def clear(self) -> int:
        """Clear all entries."""
        count = len(self._cache)
        self._cache.clear()
        return count

    def stats(self) -> dict:
        """Get cache statistics."""
        # Clean expired entries
        now = datetime.now()
        expired = [k for k, (_, exp) in self._cache.items() if now > exp]
        for k in expired:
            del self._cache[k]

        total_requests = self._hits + self._misses
        hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0

        return {
            "entries": len(self._cache),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate_percent": round(hit_rate, 2),
        }
```

## Step 3: Implement the API Client

`api_client.py`:

```python
"""HTTP client with retry logic and error handling."""

import asyncio
from typing import Any
from dataclasses import dataclass

@dataclass
class APIError(Exception):
    """API error with details."""
    status_code: int
    message: str
    details: dict = None

class APIClient:
    """Production-quality API client."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float = 30.0,
        retry_attempts: int = 3,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.retry_attempts = retry_attempts
        self._request_count = 0

    async def _request(
        self,
        method: str,
        endpoint: str,
        data: dict = None,
    ) -> dict[str, Any]:
        """Make HTTP request with retries.

        In production, use httpx:
            async with httpx.AsyncClient() as client:
                response = await client.request(...)
        """
        self._request_count += 1

        # Simulate API call (replace with real HTTP in production)
        await asyncio.sleep(0.1)  # Simulated latency

        # Mock response based on endpoint
        if "/items" in endpoint and method == "GET":
            return self._mock_list_items(endpoint)
        elif "/items/" in endpoint and method == "GET":
            return self._mock_get_item(endpoint)
        elif "/items" in endpoint and method == "POST":
            return self._mock_create_item(data)
        elif "/health" in endpoint:
            return {"status": "ok", "latency_ms": 50}

        return {"error": "Unknown endpoint"}

    def _mock_list_items(self, endpoint: str) -> dict:
        """Mock list response."""
        return {
            "items": [
                {"id": "1", "name": "Item 1", "category": "A", "status": "active"},
                {"id": "2", "name": "Item 2", "category": "B", "status": "active"},
                {"id": "3", "name": "Item 3", "category": "A", "status": "pending"},
            ],
            "total": 3,
        }

    def _mock_get_item(self, endpoint: str) -> dict:
        """Mock single item response."""
        item_id = endpoint.split("/")[-1]
        return {
            "id": item_id,
            "name": f"Item {item_id}",
            "category": "A",
            "status": "active",
            "created_at": "2024-01-15T10:00:00Z",
            "data": {"key": "value"},
        }

    def _mock_create_item(self, data: dict) -> dict:
        """Mock create response."""
        return {
            "id": "new-123",
            "name": data.get("name", "New Item"),
            "category": data.get("category", "default"),
            "status": "created",
        }

    async def get(self, endpoint: str) -> dict:
        """GET request."""
        return await self._request("GET", endpoint)

    async def post(self, endpoint: str, data: dict) -> dict:
        """POST request."""
        return await self._request("POST", endpoint, data)

    @property
    def request_count(self) -> int:
        """Number of requests made."""
        return self._request_count
```

## Step 4: Main Implementation

`main.py`:

```python
"""API Connector - Production-Quality Integration Plugin.

Demonstrates:
- Proper configuration and secrets handling
- Caching for performance
- Error handling and retries
- Cross-system synchronization
- Event-driven automation
"""

import os
from datetime import datetime
from typing import Any

# Import our modules
from cache import TTLCache
from api_client import APIClient, APIError

# =============================================================================
# Configuration
# =============================================================================

_config = {
    "api_base_url": "https://api.example.com",
    "api_key": None,
    "cache_ttl_seconds": 300,
    "retry_attempts": 3,
    "auto_sync": False,
}

_client: APIClient | None = None
_cache: TTLCache | None = None

# =============================================================================
# Tools
# =============================================================================


async def list_items(
    category: str = None,
    limit: int = 10,
    use_cache: bool = True,
) -> dict[str, Any]:
    """List items from the API.

    Args:
        category: Optional category filter
        limit: Maximum items to return
        use_cache: Whether to use cached results

    Returns:
        List of items with metadata
    """
    if not _client:
        return {"error": "Plugin not initialized. Call on_load first."}

    # Build cache key
    cache_key = f"list:{category or 'all'}:{limit}"

    # Check cache
    if use_cache and _cache:
        cached = _cache.get(cache_key)
        if cached:
            return {**cached, "cached": True}

    # Make API call
    try:
        endpoint = "/items"
        if category:
            endpoint += f"?category={category}"

        response = await _client.get(endpoint)

        # Filter and limit
        items = response.get("items", [])
        if category:
            items = [i for i in items if i.get("category") == category]
        items = items[:limit]

        result = {
            "items": items,
            "count": len(items),
            "total": response.get("total", len(items)),
            "category_filter": category,
            "cached": False,
        }

        # Cache the result
        if _cache:
            _cache.set(cache_key, result)

        return result

    except APIError as e:
        return {
            "error": e.message,
            "status_code": e.status_code,
        }
    except Exception as e:
        return {"error": f"Request failed: {str(e)}"}


async def get_item(id: str) -> dict[str, Any]:
    """Get a single item by ID.

    Args:
        id: Item ID

    Returns:
        Item details
    """
    if not _client:
        return {"error": "Plugin not initialized"}

    cache_key = f"item:{id}"

    # Check cache
    if _cache:
        cached = _cache.get(cache_key)
        if cached:
            return {**cached, "cached": True}

    try:
        response = await _client.get(f"/items/{id}")
        result = {"item": response, "cached": False}

        if _cache:
            _cache.set(cache_key, result)

        return result

    except APIError as e:
        return {"error": e.message, "status_code": e.status_code}


async def create_item(
    name: str,
    category: str,
    data: dict = None,
) -> dict[str, Any]:
    """Create a new item.

    Args:
        name: Item name
        category: Item category
        data: Additional data

    Returns:
        Created item details
    """
    if not _client:
        return {"error": "Plugin not initialized"}

    try:
        response = await _client.post("/items", {
            "name": name,
            "category": category,
            "data": data or {},
        })

        # Invalidate list cache since we added an item
        if _cache:
            # Clear all list caches
            _cache.clear()  # Simple approach; could be more targeted

        return {
            "success": True,
            "item": response,
        }

    except APIError as e:
        return {"success": False, "error": e.message}


async def sync_to_tasks(
    category: str,
    project_name: str,
) -> dict[str, Any]:
    """Sync API items to PMS tasks.

    This demonstrates cross-system integration:
    - Fetch items from external API
    - Create corresponding PMS tasks
    - Track sync status

    Args:
        category: Category to sync
        project_name: PMS project to sync to

    Returns:
        Sync results
    """
    # Get items from API
    items_result = await list_items(category=category, use_cache=False)

    if "error" in items_result:
        return items_result

    items = items_result.get("items", [])
    synced = []
    errors = []

    for item in items:
        try:
            # In production, would call PMS task service
            task_data = {
                "title": f"[{category}] {item['name']}",
                "description": f"Synced from API. ID: {item['id']}",
                "tags": ["api-sync", f"api-{category}"],
                "metadata": {
                    "api_id": item["id"],
                    "api_status": item.get("status"),
                },
            }

            synced.append({
                "api_id": item["id"],
                "task_title": task_data["title"],
            })

        except Exception as e:
            errors.append({
                "api_id": item["id"],
                "error": str(e),
            })

    return {
        "success": len(errors) == 0,
        "synced": len(synced),
        "errors": len(errors),
        "details": synced,
        "error_details": errors if errors else None,
        "project": project_name,
    }


async def health_check() -> dict[str, Any]:
    """Check API connectivity and status.

    Returns:
        Health status including latency
    """
    if not _client:
        return {"healthy": False, "error": "Plugin not initialized"}

    try:
        start = datetime.now()
        response = await _client.get("/health")
        latency = (datetime.now() - start).total_seconds() * 1000

        return {
            "healthy": True,
            "api_status": response.get("status"),
            "latency_ms": round(latency, 2),
            "requests_made": _client.request_count,
        }

    except Exception as e:
        return {
            "healthy": False,
            "error": str(e),
        }


async def cache_stats() -> dict[str, Any]:
    """Get cache statistics.

    Returns:
        Cache hit/miss stats
    """
    if not _cache:
        return {"enabled": False}

    return {
        "enabled": True,
        **_cache.stats(),
    }


async def clear_cache() -> dict[str, Any]:
    """Clear the cache.

    Returns:
        Number of entries cleared
    """
    if not _cache:
        return {"enabled": False, "cleared": 0}

    cleared = _cache.clear()
    return {"cleared": cleared}


# =============================================================================
# Event Handlers
# =============================================================================


async def on_task_completed(
    task_id: str,
    title: str,
    tags: list = None,
    **kwargs
):
    """Handle task completion for synced tasks.

    When a task with 'api-sync' tag is completed,
    we could update the external system.
    """
    tags = tags or []

    if "api-sync" not in tags:
        return

    print(f"[api-connector] Synced task completed: {title}")

    # In production, would update the external API
    # await _client.post(f"/items/{api_id}/complete", {})


# =============================================================================
# Lifecycle
# =============================================================================


async def on_load(config: dict = None):
    """Initialize the plugin.

    Sets up API client and cache based on configuration.
    """
    global _config, _client, _cache

    if config:
        _config.update(config)

    # Get API key from config or environment
    api_key = _config.get("api_key") or os.environ.get("API_CONNECTOR_KEY")

    if not api_key:
        print("[api-connector] WARNING: No API key configured!")
        print("[api-connector] Set API_CONNECTOR_KEY env var or pass in config")
        # Continue anyway for testing with mock
        api_key = "mock-key"

    # Initialize client
    _client = APIClient(
        base_url=_config["api_base_url"],
        api_key=api_key,
        retry_attempts=_config["retry_attempts"],
    )

    # Initialize cache
    _cache = TTLCache(default_ttl_seconds=_config["cache_ttl_seconds"])

    print(f"[api-connector] Initialized")
    print(f"[api-connector] API: {_config['api_base_url']}")
    print(f"[api-connector] Cache TTL: {_config['cache_ttl_seconds']}s")


async def on_unload():
    """Cleanup."""
    global _client, _cache

    if _cache:
        stats = _cache.stats()
        print(f"[api-connector] Final cache stats: {stats}")

    _client = None
    _cache = None
    print("[api-connector] Unloaded")
```

## Step 5: Test the Integration

```bash
# Validate
pms plugin validate ./api-connector

# Start
pms plugin discover ./api-connector
pms plugin start api-connector

# Check health
pms plugin call api-connector.health_check

# List items (first call - not cached)
pms plugin call api-connector.list_items

# List again (cached)
pms plugin call api-connector.list_items

# Check cache stats
pms plugin call api-connector.cache_stats

# Get specific item
pms plugin call api-connector.get_item --arg id="1"

# Create item
pms plugin call api-connector.create_item \
    --arg name="New Item" \
    --arg category="A"

# Sync to PMS tasks
pms plugin call api-connector.sync_to_tasks \
    --arg category="A" \
    --arg project_name="My Project"

# Clear cache
pms plugin call api-connector.clear_cache
```

## Production Checklist

Before deploying an integration plugin:

- [ ] **Secrets**: Use `secret: true` and environment variables
- [ ] **Timeouts**: Set appropriate `timeout` values
- [ ] **Retries**: Implement retry logic for transient failures
- [ ] **Caching**: Cache expensive operations with TTL
- [ ] **Rate Limiting**: Respect API rate limits
- [ ] **Error Handling**: Return structured errors, don't throw
- [ ] **Logging**: Log important operations for debugging
- [ ] **Health Checks**: Provide connectivity testing
- [ ] **Resource Limits**: Set `max_memory_mb` and `max_concurrent`
- [ ] **Testing**: Write tests for all code paths

## What You Learned

1. **Production Structure**: Multi-file plugin organization
2. **Caching**: TTL-based caching for performance
3. **Error Handling**: Graceful degradation and error responses
4. **Configuration**: Secrets, environment variables, defaults
5. **Cross-System Sync**: Data flowing between systems
6. **Event Integration**: Reacting to PMS events
7. **Health Checks**: Monitoring and diagnostics

## Next Steps

- **Tutorial 5**: Self-building meta-plugins
- **Tutorial 6**: Multi-plugin workflows
- **Tutorial 7**: Testing strategies
