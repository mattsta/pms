"""Repository for managing API keys."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from pms.core.events import DomainEvent, EventStore, EventType
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.models.api_key import ApiKey
from pms.repositories.base import EventSourcedRepository

if TYPE_CHECKING:
    from pms.db.connection import Database


class ApiKeyRepository(EventSourcedRepository[ApiKey]):
    """Repository for API key persistence."""

    def __init__(self, db: Database):
        super().__init__(
            db,
            EventStore(db),
            RevisionStore(db),
            MetricsCollector(db),
        )

    @property
    def entity_type(self) -> str:
        return "api_key"

    @property
    def table_name(self) -> str:
        return "api_keys"

    @property
    def archive_column(self) -> str | None:
        return "archived_at"

    async def create(self, api_key: ApiKey) -> ApiKey:
        """Create a new API key."""
        payload = {
            "name": api_key.name,
            "key_hash": api_key.key_hash,
            "prefix": api_key.prefix,
            "expires_at": api_key.expires_at.isoformat()
            if api_key.expires_at
            else None,
            "last_used_at": api_key.last_used_at.isoformat()
            if api_key.last_used_at
            else None,
            "is_active": api_key.is_active,
            "scopes": list(api_key.scopes),
            "metadata": api_key.metadata,
            "rate_limit": api_key.rate_limit,
        }

        return await self.save(
            api_key,
            EventType.API_KEY_CREATED,
            payload,
            message="Created API key",
        )

    async def get_by_hash(self, key_hash: str) -> ApiKey | None:
        """Get API key by hash."""
        row = await self.db.fetch_one(
            "SELECT * FROM api_keys WHERE key_hash = ? AND archived_at IS NULL",
            (key_hash,),
        )
        return self._model_from_row(row) if row else None

    async def get_by_id(self, key_id: str) -> ApiKey | None:
        """Get API key by ID."""
        row = await self.db.fetch_one(
            "SELECT * FROM api_keys WHERE id = ? AND archived_at IS NULL",
            (key_id,),
        )
        return self._model_from_row(row) if row else None

    async def get_by_prefix(self, prefix: str) -> list[ApiKey]:
        """Get API keys by prefix."""
        rows = await self.db.fetch_all(
            "SELECT * FROM api_keys WHERE prefix = ? AND archived_at IS NULL",
            (prefix,),
        )
        return [self._model_from_row(row) for row in rows]

    async def list_all(
        self, include_inactive: bool = False, *, include_archived: bool = False
    ) -> list[ApiKey]:
        """List all API keys."""
        if include_inactive:
            if include_archived:
                rows = await self.db.fetch_all(
                    "SELECT * FROM api_keys ORDER BY created_at DESC"
                )
            else:
                rows = await self.db.fetch_all(
                    """
                    SELECT * FROM api_keys
                    WHERE archived_at IS NULL
                    ORDER BY created_at DESC
                    """
                )
        else:
            if include_archived:
                rows = await self.db.fetch_all(
                    """
                    SELECT * FROM api_keys
                    WHERE is_active = 1
                    ORDER BY created_at DESC
                    """
                )
            else:
                rows = await self.db.fetch_all(
                    """
                    SELECT * FROM api_keys
                    WHERE is_active = 1 AND archived_at IS NULL
                    ORDER BY created_at DESC
                    """
                )
        return [self._model_from_row(row) for row in rows]

    async def update_last_used(self, key_id: str) -> None:
        """Update last_used_at timestamp."""
        key = await self.get_by_id(key_id)
        if key is None:
            return

        now = datetime.now(UTC)
        old_value = key.last_used_at.isoformat() if key.last_used_at else None
        key.last_used_at = now
        key.touch()

        await self.save(
            key,
            EventType.API_KEY_UPDATED,
            {"changes": {"last_used_at": (old_value, now.isoformat())}},
            message="Updated API key last_used_at",
        )

    async def deactivate(self, key_id: str) -> None:
        """Deactivate an API key."""
        key = await self.get_by_id(key_id)
        if key is None:
            return

        if not key.is_active:
            return

        key.is_active = False
        key.touch()
        await self.save(
            key,
            EventType.API_KEY_DEACTIVATED,
            {"changes": {"is_active": (True, False)}},
            message="Deactivated API key",
        )

    async def reactivate(self, key_id: str) -> ApiKey | None:
        """Reactivate an inactive API key."""
        key = await self.get_by_id(key_id)
        if key is None:
            return None

        if key.is_active:
            return key

        key.is_active = True
        key.touch()
        await self.save(
            key,
            EventType.API_KEY_UPDATED,
            {"changes": {"is_active": (False, True)}},
            message="Reactivated API key",
        )
        return key

    async def delete(
        self,
        key_id: str,
        soft_delete: bool = True,
        message: str | None = None,
    ) -> bool:
        """Archive an API key without removing audit history."""
        return await super().delete(
            key_id,
            soft_delete=soft_delete,
            message=message or "Deleted API key",
        )

    def _model_from_row(self, row: dict[str, Any]) -> ApiKey:
        """Convert database row to ApiKey model."""
        scopes_value = row["scopes"]
        scopes = json.loads(scopes_value) if scopes_value else []
        if not isinstance(scopes, list):
            msg = f"Expected api_keys.scopes to deserialize to a list, got {type(scopes).__name__}"
            raise TypeError(msg)

        return ApiKey(
            id=row["id"],
            name=row["name"],
            key_hash=row["key_hash"],
            prefix=row["prefix"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            expires_at=datetime.fromisoformat(row["expires_at"])
            if row["expires_at"]
            else None,
            last_used_at=datetime.fromisoformat(row["last_used_at"])
            if row["last_used_at"]
            else None,
            is_active=bool(row["is_active"]),
            scopes=[str(scope) for scope in scopes],
            metadata=self._deserialize_metadata(row["metadata"]),
            rate_limit=row["rate_limit"],
            archived_at=datetime.fromisoformat(row["archived_at"])
            if row.get("archived_at")
            else None,
            last_event_sequence=row.get("last_event_sequence", 0),
            last_revision_number=row.get("last_revision_number", 0),
        )

    def _row_from_model(self, model: ApiKey) -> dict[str, Any]:
        return {
            "id": model.id,
            "name": model.name,
            "key_hash": model.key_hash,
            "prefix": model.prefix,
            "created_at": model.created_at.isoformat(),
            "updated_at": model.updated_at.isoformat(),
            "expires_at": model.expires_at.isoformat() if model.expires_at else None,
            "last_used_at": model.last_used_at.isoformat()
            if model.last_used_at
            else None,
            "is_active": 1 if model.is_active else 0,
            "scopes": json.dumps(model.scopes),
            "metadata": self._serialize_metadata(model.metadata),
            "rate_limit": model.rate_limit,
            "archived_at": model.archived_at.isoformat() if model.archived_at else None,
            "last_event_sequence": model.last_event_sequence,
            "last_revision_number": model.last_revision_number,
        }

    async def _apply_events(
        self, events: list[DomainEvent[dict[str, Any]]]
    ) -> ApiKey | None:
        if not events:
            return None

        key: ApiKey | None = None
        for event in events:
            match event.event_type:
                case EventType.API_KEY_CREATED:
                    payload = event.payload
                    key = ApiKey(
                        id=event.aggregate_id,
                        name=payload.get("name", ""),
                        key_hash=payload.get("key_hash", ""),
                        prefix=payload.get("prefix", ""),
                        expires_at=self._parse_dt(payload.get("expires_at")),
                        last_used_at=self._parse_dt(payload.get("last_used_at")),
                        is_active=bool(payload.get("is_active", True)),
                        scopes=payload.get("scopes", []) or [],
                        metadata=payload.get("metadata") or {},
                        rate_limit=payload.get("rate_limit"),
                    )
                case EventType.API_KEY_UPDATED if key:
                    changes = event.payload.get("changes", {})
                    for field, (old_val, new_val) in changes.items():
                        match field:
                            case "last_used_at":
                                key.last_used_at = self._parse_dt(new_val)
                            case "is_active":
                                key.is_active = bool(new_val)
                case EventType.API_KEY_DEACTIVATED if key:
                    key.is_active = False
                case EventType.API_KEY_DELETED:
                    key = None
                case EventType.API_KEY_RESTORED:
                    payload = event.payload
                    content = payload.get("content") or {}
                    key = ApiKey(
                        id=content.get("id", event.aggregate_id),
                        name=content.get("name", ""),
                        key_hash=content.get("key_hash", ""),
                        prefix=content.get("prefix", ""),
                        expires_at=self._parse_dt(content.get("expires_at")),
                        last_used_at=self._parse_dt(content.get("last_used_at")),
                        is_active=bool(content.get("is_active", True)),
                        scopes=content.get("scopes", []) or [],
                        metadata=content.get("metadata") or {},
                        rate_limit=content.get("rate_limit"),
                    )

        return key

    def _parse_dt(self, value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value)
        return None

    def _serialize_metadata(self, metadata: dict[str, str]) -> str:
        """Serialize metadata dict to string."""
        import json

        return json.dumps(metadata) if metadata else "{}"

    def _deserialize_metadata(self, metadata_str: str | None) -> dict[str, str]:
        """Deserialize metadata string to dict."""
        import json

        if not metadata_str:
            return {}
        try:
            parsed = json.loads(metadata_str)
            if not isinstance(parsed, dict):
                return {}
            return {str(key): str(value) for key, value in parsed.items()}
        except json.JSONDecodeError, TypeError:
            return {}
