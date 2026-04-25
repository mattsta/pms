"""API key model for authentication."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime

from pms.models.base import BaseModel


@dataclass
class ApiKey(BaseModel):
    """API key for authentication and authorization."""

    name: str = ""  # Human-readable name for the key
    key_hash: str = ""  # SHA-256 hash of the actual key
    prefix: str = ""  # First 8 chars for identification (e.g., "pms_1234...")
    expires_at: datetime | None = None  # None = never expires
    last_used_at: datetime | None = None
    is_active: bool = True
    scopes: list[str] = field(
        default_factory=list
    )  # Permissions (e.g., ["tasks:read", "tasks:write"])
    metadata: dict[str, str] = field(default_factory=dict)  # User-defined metadata
    rate_limit: int | None = None  # Requests per minute (None = no limit)
    archived_at: datetime | None = None

    @property
    def is_expired(self) -> bool:
        """Check if key is expired."""
        if self.expires_at is None:
            return False
        return datetime.now(UTC) > self.expires_at

    @property
    def is_valid(self) -> bool:
        """Check if key is valid (active and not expired)."""
        return self.is_active and not self.is_expired

    def matches_scope(self, required_scope: str) -> bool:
        """
        Check if key has required scope with hierarchical matching.

        Supports:
        - Resource-level: "tasks:read" grants access to read ANY task
        - Row-level: "project:<project-id>:read" grants read access to SPECIFIC project
        - Wildcards at any level:
          - "*" matches everything
          - "tasks:*" matches any task operation
          - "project:<project-id>:*" matches any operation on that project
          - "project:*:read" matches read on any project

        Examples:
            key.scopes = ["tasks:*"]
            key.matches_scope("tasks:read") -> True
            key.matches_scope("tasks:<task-id>:read") -> True

            key.scopes = ["project:<project-id>:*"]
            key.matches_scope("project:<project-id>:read") -> True
            key.matches_scope("project:<project-id-2>:read") -> False

            key.scopes = ["task:<task-id>:write"]
            key.matches_scope("task:<task-id>:write") -> True
            key.matches_scope("task:<task-id>:read") -> False
        """
        if "*" in self.scopes:
            return True

        if required_scope in self.scopes:
            return True

        # Parse required scope
        required_parts = required_scope.split(":")

        # Check each granted scope for hierarchical match
        for granted_scope in self.scopes:
            granted_parts = granted_scope.split(":")

            if _scope_matches(granted_parts, required_parts):
                return True

        return False


def _scope_matches(granted_parts: list[str], required_parts: list[str]) -> bool:
    """
    Check if granted scope matches required scope hierarchically.

    Examples:
        _scope_matches(["tasks", "*"], ["tasks", "read"]) -> True
        _scope_matches(["project", "<project-id>", "*"], ["project", "<project-id>", "read"]) -> True
        _scope_matches(["project", "*", "read"], ["project", "<project-id>", "read"]) -> True
        _scope_matches(["project", "*", "write"], ["project", "<project-id>", "read"]) -> False
        _scope_matches(["tasks", "read"], ["tasks", "<task-id>", "read"]) -> False (granted too short)
        _scope_matches(["project", "<project-id>", "read"], ["project", "<project-id-2>", "read"]) -> False
    """
    # Granted scope can't be longer than required scope
    if len(granted_parts) > len(required_parts):
        return False

    # Check each part from left to right
    for i, granted_part in enumerate(granted_parts):
        # Make sure we haven't run past the required scope
        if i >= len(required_parts):
            return False

        # Wildcard matches any value at this position
        if granted_part == "*":
            # If this is the last part of granted scope, wildcard matches everything remaining
            if i == len(granted_parts) - 1:
                return True
            # Otherwise, wildcard just matches this position - continue to check remaining parts
            continue

        # Parts must match exactly
        if granted_part != required_parts[i]:
            return False

    # All granted parts matched, and lengths must be equal
    # (if granted is shorter without wildcard, it doesn't match)
    return len(granted_parts) == len(required_parts)


def generate_api_key() -> tuple[str, str]:
    """
    Generate a new API key.

    Returns:
        Tuple of (plain_key, key_hash)
        - plain_key: The actual key to give to user (only shown once!)
        - key_hash: SHA-256 hash to store in database
    """
    import hashlib

    # Generate secure random key (32 bytes = 256 bits)
    random_bytes = secrets.token_bytes(32)
    plain_key = f"pms_{secrets.token_urlsafe(32)}"

    # Hash for storage
    key_hash = hashlib.sha256(plain_key.encode()).hexdigest()

    return plain_key, key_hash


def hash_api_key(plain_key: str) -> str:
    """Hash an API key for storage or validation."""
    import hashlib

    return hashlib.sha256(plain_key.encode()).hexdigest()


def get_key_prefix(plain_key: str) -> str:
    """Extract the prefix from a plain key for identification."""
    # Return first 12 chars (e.g., "pms_1234abcd")
    return plain_key[:12] if len(plain_key) >= 12 else plain_key
