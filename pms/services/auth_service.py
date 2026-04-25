"""Authentication service for API key management."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from pms.core.ids import EntityType, generate_id
from pms.models.api_key import ApiKey, generate_api_key, hash_api_key

if TYPE_CHECKING:
    from pms.repositories.api_key_repository import ApiKeyRepository


class AuthService:
    """Service for authentication and API key management."""

    def __init__(self, api_key_repo: ApiKeyRepository):
        self.api_key_repo = api_key_repo

    async def create_api_key(
        self,
        name: str,
        scopes: list[str],
        expires_in_days: int | None = None,
        rate_limit: int | None = None,
        metadata: dict[str, str] | None = None,
    ) -> tuple[str, ApiKey]:
        """
        Create a new API key.

        Args:
            name: Human-readable name for the key
            scopes: List of permission scopes (e.g., ["tasks:read", "tasks:write"])
            expires_in_days: Days until expiration (None = never expires)
            rate_limit: Requests per minute (None = no limit)
            metadata: Additional metadata

        Returns:
            Tuple of (plain_key, api_key_model)
            - plain_key: The actual key (ONLY SHOWN ONCE!)
            - api_key_model: The stored model
        """
        plain_key, key_hash = generate_api_key()
        prefix = plain_key[:12]  # "pms_1234abcd"

        now = datetime.now(UTC)
        expires_at = now + timedelta(days=expires_in_days) if expires_in_days else None

        api_key = ApiKey(
            id=generate_id(EntityType.API_KEY),
            name=name,
            key_hash=key_hash,
            prefix=prefix,
            created_at=now,
            updated_at=now,
            expires_at=expires_at,
            last_used_at=None,
            is_active=True,
            scopes=scopes,
            metadata=metadata or {},
            rate_limit=rate_limit,
        )

        await self.api_key_repo.create(api_key)

        return plain_key, api_key

    async def validate_api_key(
        self, plain_key: str, required_scope: str | None = None
    ) -> ApiKey | None:
        """
        Validate an API key.

        Args:
            plain_key: The plain text API key
            required_scope: Optional scope to check (e.g., "tasks:write")

        Returns:
            ApiKey if valid, None if invalid
        """
        key_hash = hash_api_key(plain_key)
        api_key = await self.api_key_repo.get_by_hash(key_hash)

        if not api_key:
            return None

        if not api_key.is_valid:
            return None

        if required_scope and not api_key.matches_scope(required_scope):
            return None

        # Update last used timestamp
        await self.api_key_repo.update_last_used(api_key.id)

        return api_key

    async def deactivate_key(self, key_id: str) -> None:
        """Deactivate an API key."""
        await self.api_key_repo.deactivate(key_id)

    async def delete_key(self, key_id: str) -> None:
        """Permanently delete an API key."""
        await self.api_key_repo.delete(key_id)

    async def list_keys(
        self, include_inactive: bool = False, *, include_archived: bool = False
    ) -> list[ApiKey]:
        """List all API keys."""
        return await self.api_key_repo.list_all(
            include_inactive, include_archived=include_archived
        )

    async def get_key_by_id(self, key_id: str) -> ApiKey | None:
        """Get an API key by ID."""
        return await self.api_key_repo.get_by_id(key_id)

    async def restore_key(self, key_id: str) -> ApiKey | None:
        """Restore an archived key and reactivate it if needed."""
        async with self.api_key_repo.db.transaction():
            key = await self.api_key_repo.restore(key_id)
            if key is None:
                return None
            if not key.is_active:
                return await self.api_key_repo.reactivate(key_id)
            return key

    async def check_rate_limit(self, api_key: ApiKey) -> tuple[bool, int, int]:
        """
        Check if API key is within rate limit.

        Args:
            api_key: The API key to check

        Returns:
            Tuple of (allowed, current_count, limit)
            - allowed: True if within limit
            - current_count: Current requests in window
            - limit: Rate limit for this key
        """
        if api_key.rate_limit is None:
            return True, 0, 0

        # Get current minute window
        now = datetime.now(UTC)
        window_start = now.replace(second=0, microsecond=0)

        # Get current usage
        row = await self.api_key_repo.db.fetch_one(
            """
            SELECT request_count FROM rate_limit_usage
            WHERE api_key_id = ? AND window_start = ?
            """,
            (api_key.id, window_start.isoformat()),
        )

        current_count = row["request_count"] if row else 0

        # Check limit
        if current_count >= api_key.rate_limit:
            return False, current_count, api_key.rate_limit

        # Increment counter
        await self.api_key_repo.db.execute(
            """
            INSERT INTO rate_limit_usage (api_key_id, window_start, request_count)
            VALUES (?, ?, 1)
            ON CONFLICT(api_key_id, window_start) DO UPDATE SET
                request_count = request_count + 1
            """,
            (api_key.id, window_start.isoformat()),
        )
        await self.api_key_repo.db.commit()

        return True, current_count + 1, api_key.rate_limit

    async def cleanup_old_rate_limits(self, hours: int = 24) -> int:
        """
        Clean up old rate limit usage data.

        Args:
            hours: Remove data older than this many hours

        Returns:
            Number of records deleted
        """
        cutoff = datetime.now(UTC) - timedelta(hours=hours)

        result = await self.api_key_repo.db.execute(
            "DELETE FROM rate_limit_usage WHERE window_start < ?",
            (cutoff.isoformat(),),
        )
        await self.api_key_repo.db.commit()

        # Get row count (if supported by backend)
        return result if isinstance(result, int) else 0
