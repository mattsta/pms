"""Authentication and authorization for API endpoints."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

from pms.models.api_key import ApiKey

if TYPE_CHECKING:
    pass


# API Key header scheme
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


class AuthenticationError(HTTPException):
    """Raised when authentication fails."""

    def __init__(self, detail: str = "Invalid or missing API key"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "ApiKey"},
        )


class AuthorizationError(HTTPException):
    """Raised when user lacks required permissions."""

    def __init__(self, detail: str = "Insufficient permissions"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
        )


class RateLimitError(HTTPException):
    """Raised when rate limit is exceeded."""

    def __init__(self, retry_after: int = 60):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )


async def get_api_key(
    x_api_key: str | None = Depends(api_key_header),
) -> ApiKey:
    """
    Dependency to validate API key from header.

    Raises:
        AuthenticationError: If key is missing or invalid
    """
    if not x_api_key:
        raise AuthenticationError("Missing API key")

    # Import here to avoid circular dependency
    from pms.api.dependencies import get_auth_service

    auth_service = await get_auth_service()
    api_key = await auth_service.validate_api_key(x_api_key)

    if not api_key:
        raise AuthenticationError("Invalid API key")

    return api_key


async def check_rate_limit(
    api_key: ApiKey,
) -> None:
    """
    Dependency to check rate limits.

    Raises:
        RateLimitError: If rate limit is exceeded
    """
    if api_key.rate_limit is None:
        return  # No limit

    # Import here to avoid circular dependency
    from pms.api.dependencies import get_auth_service

    auth_service = await get_auth_service()
    allowed, current, limit = await auth_service.check_rate_limit(api_key)

    if not allowed:
        raise RateLimitError(retry_after=60)


def check_resource_scope(
    api_key: ApiKey, resource_type: str, resource_id: str, operation: str
) -> None:
    """
    Check if API key has access to a specific resource.

    Args:
        api_key: The authenticated API key
        resource_type: Resource type (e.g., "projects", "tasks")
        resource_id: Specific resource ID
        operation: Operation (e.g., "read", "write", "delete")

    Raises:
        AuthorizationError: If key lacks required scope

    Example:
        check_resource_scope(api_key, "projects", "<project-id>", "read")
        # Checks for: projects:<project-id>:read
    """
    row_scope = f"{resource_type}:{resource_id}:{operation}"
    if not api_key.matches_scope(row_scope):
        raise AuthorizationError(f"Missing required scope: {row_scope}")


def require_scope(scope: str) -> Callable[..., Awaitable[ApiKey]]:
    """
    Dependency factory to require specific scope.

    Usage:
        @app.get("/tasks", dependencies=[Depends(require_scope("tasks:read"))])

    Args:
        scope: Required scope (e.g., "tasks:write")

    Returns:
        Dependency function
    """

    async def check_scope(api_key: ApiKey = Depends(get_api_key)) -> ApiKey:
        if not api_key.matches_scope(scope):
            raise AuthorizationError(f"Missing required scope: {scope}")

        # Check rate limit
        await check_rate_limit(api_key)

        return api_key

    return check_scope


# Common dependency combinations
RequireAuth = Annotated[ApiKey, Depends(get_api_key)]
RequireReadAccess = Annotated[ApiKey, Depends(require_scope("*:read"))]
RequireWriteAccess = Annotated[ApiKey, Depends(require_scope("*:write"))]


# Scope definitions for different resources
class Scopes:
    """Standard scope definitions."""

    # Admin
    ADMIN = "*"
    ADMIN_KEYS = "admin:keys"  # Manage API keys

    # Products
    PRODUCTS_READ = "products:read"
    PRODUCTS_WRITE = "products:write"
    PRODUCTS_DELETE = "products:delete"

    # Organizations
    ORGS_READ = "orgs:read"
    ORGS_WRITE = "orgs:write"
    ORGS_DELETE = "orgs:delete"

    # Teams
    TEAMS_READ = "teams:read"
    TEAMS_WRITE = "teams:write"
    TEAMS_DELETE = "teams:delete"

    # Actors
    ACTORS_READ = "actors:read"
    ACTORS_WRITE = "actors:write"

    # Portfolios
    PORTFOLIOS_READ = "portfolios:read"
    PORTFOLIOS_WRITE = "portfolios:write"
    PORTFOLIOS_DELETE = "portfolios:delete"

    # Programs
    PROGRAMS_READ = "programs:read"
    PROGRAMS_WRITE = "programs:write"
    PROGRAMS_DELETE = "programs:delete"

    # Goals
    GOALS_READ = "goals:read"
    GOALS_WRITE = "goals:write"
    GOALS_DELETE = "goals:delete"

    # Plans
    PLANS_READ = "plans:read"
    PLANS_WRITE = "plans:write"
    PLANS_DELETE = "plans:delete"

    # Projects
    PROJECTS_READ = "projects:read"
    PROJECTS_WRITE = "projects:write"
    PROJECTS_DELETE = "projects:delete"

    # Tasks
    TASKS_READ = "tasks:read"
    TASKS_WRITE = "tasks:write"
    TASKS_DELETE = "tasks:delete"

    # Labels
    LABELS_READ = "labels:read"
    LABELS_WRITE = "labels:write"
    LABELS_DELETE = "labels:delete"

    # Custom fields
    CUSTOM_FIELDS_READ = "custom_fields:read"
    CUSTOM_FIELDS_WRITE = "custom_fields:write"
    CUSTOM_FIELDS_DELETE = "custom_fields:delete"

    # Automation rules
    AUTOMATION_READ = "automation:read"
    AUTOMATION_WRITE = "automation:write"
    AUTOMATION_DELETE = "automation:delete"

    # Workflows
    WORKFLOWS_READ = "workflows:read"
    WORKFLOWS_WRITE = "workflows:write"

    # Test runs
    TEST_RUNS_READ = "test_runs:read"
    TEST_RUNS_WRITE = "test_runs:write"

    # Checkout (for agent coordination)
    CHECKOUT_WRITE = "checkout:write"

    # Agent loops
    AGENT_LOOPS_READ = "agent_loops:read"
    AGENT_LOOPS_WRITE = "agent_loops:write"

    @classmethod
    def all_scopes(cls) -> list[str]:
        """Get all defined scopes."""
        return [
            value
            for name, value in vars(cls).items()
            if not name.startswith("_") and isinstance(value, str) and ":" in value
        ]


# Optional auth (for endpoints that work with or without auth)
async def get_optional_api_key(
    x_api_key: str | None = Depends(api_key_header),
) -> ApiKey | None:
    """
    Optional authentication - returns None if no key provided.

    Use for endpoints that work better with auth but don't require it.
    """
    if not x_api_key:
        return None

    try:
        from pms.api.dependencies import get_auth_service

        auth_service = await get_auth_service()
        return await auth_service.validate_api_key(x_api_key)
    except Exception:
        return None
