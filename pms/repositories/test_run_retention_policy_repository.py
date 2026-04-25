"""Repository for test run retention policies."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pms.core.events import DomainEvent, EventStore, EventType
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.models.json_types import JsonObject, JsonValue, ModelObject
from pms.models.test_run_retention_policy import TestRunRetentionPolicy
from pms.repositories.base import EventSourcedRepository, QueryResult

if TYPE_CHECKING:
    from pms.db.connection import Database
    from pms.db.types import DbRow, DbValue

type RetentionPolicyPayload = JsonObject
type RetentionPolicyEvents = list[DomainEvent[RetentionPolicyPayload]]
type RetentionChangePair = tuple[JsonValue | None, JsonValue | None]
type RetentionChanges = dict[str, RetentionChangePair]


class TestRunRetentionPolicyRepository(EventSourcedRepository[TestRunRetentionPolicy]):
    """Repository for test run retention policies."""

    def __init__(self, db: Database) -> None:
        super().__init__(
            db,
            EventStore(db),
            RevisionStore(db),
            MetricsCollector(db),
        )

    @property
    def entity_type(self) -> str:
        return "test_run_retention_policy"

    @property
    def table_name(self) -> str:
        return "test_run_retention_policies"

    @property
    def archive_column(self) -> str | None:
        return "archived_at"

    async def create(
        self,
        scope_type: str,
        scope_id: str,
        max_log_bytes: int,
        max_artifact_bytes: int,
        max_age_days: int,
        notes: str | None = None,
    ) -> TestRunRetentionPolicy:
        policy = TestRunRetentionPolicy(
            scope_type=scope_type,
            scope_id=scope_id,
            max_log_bytes=max_log_bytes,
            max_artifact_bytes=max_artifact_bytes,
            max_age_days=max_age_days,
            notes=notes,
        )
        payload = {
            "scope_type": scope_type,
            "scope_id": scope_id,
            "max_log_bytes": max_log_bytes,
            "max_artifact_bytes": max_artifact_bytes,
            "max_age_days": max_age_days,
            "notes": notes,
        }
        return await self.save(
            policy,
            EventType.TEST_RUN_RETENTION_POLICY_CREATED,
            payload,
            message="Created test run retention policy",
        )

    async def update(
        self,
        policy_id: str,
        *,
        max_log_bytes: int | None = None,
        max_artifact_bytes: int | None = None,
        max_age_days: int | None = None,
        notes: str | None = None,
    ) -> TestRunRetentionPolicy | None:
        existing = await self.get_by_id(policy_id)
        if existing is None:
            return None

        updated = TestRunRetentionPolicy(
            id=existing.id,
            scope_type=existing.scope_type,
            scope_id=existing.scope_id,
            max_log_bytes=max_log_bytes
            if max_log_bytes is not None
            else existing.max_log_bytes,
            max_artifact_bytes=max_artifact_bytes
            if max_artifact_bytes is not None
            else existing.max_artifact_bytes,
            max_age_days=max_age_days
            if max_age_days is not None
            else existing.max_age_days,
            notes=notes if notes is not None else existing.notes,
            created_at=existing.created_at,
            updated_at=datetime.now(UTC),
            archived_at=existing.archived_at,
            last_event_sequence=existing.last_event_sequence,
            last_revision_number=existing.last_revision_number,
        )

        changes: RetentionChanges = {}
        if max_log_bytes is not None and max_log_bytes != existing.max_log_bytes:
            changes["max_log_bytes"] = (existing.max_log_bytes, max_log_bytes)
        if (
            max_artifact_bytes is not None
            and max_artifact_bytes != existing.max_artifact_bytes
        ):
            changes["max_artifact_bytes"] = (
                existing.max_artifact_bytes,
                max_artifact_bytes,
            )
        if max_age_days is not None and max_age_days != existing.max_age_days:
            changes["max_age_days"] = (existing.max_age_days, max_age_days)
        if notes is not None and notes != existing.notes:
            changes["notes"] = (existing.notes, notes)

        if not changes:
            return existing

        return await self.save(
            updated,
            EventType.TEST_RUN_RETENTION_POLICY_UPDATED,
            {"changes": changes},
            message="Updated test run retention policy",
        )

    async def get_by_id(self, policy_id: str) -> TestRunRetentionPolicy | None:
        row = await self.db.fetch_one(
            """
            SELECT * FROM test_run_retention_policies
            WHERE id = ? AND archived_at IS NULL
            """,
            (policy_id,),
        )
        return self._row_to_model(row) if row else None

    async def get_by_scope(
        self,
        scope_type: str,
        scope_id: str,
        *,
        include_archived: bool = False,
    ) -> TestRunRetentionPolicy | None:
        where_sql = "scope_type = ? AND scope_id = ?"
        if not include_archived:
            where_sql += " AND archived_at IS NULL"
        row = await self.db.fetch_one(
            f"""
            SELECT * FROM test_run_retention_policies
            WHERE {where_sql}
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (scope_type, scope_id),
        )
        return self._row_to_model(row) if row else None

    async def list(
        self,
        scope_type: str | None = None,
        scope_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
        *,
        include_archived: bool = False,
    ) -> QueryResult[TestRunRetentionPolicy]:
        where_clauses = []
        params: list[str] = []

        if scope_type:
            where_clauses.append("scope_type = ?")
            params.append(scope_type)
        if scope_id:
            where_clauses.append("scope_id = ?")
            params.append(scope_id)

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        if not include_archived:
            where_sql = f"{where_sql} AND archived_at IS NULL"

        count_row = await self.db.fetch_one(
            f"""
            SELECT COUNT(*) as count
            FROM test_run_retention_policies
            WHERE {where_sql}
            """,
            tuple(params),
        )
        total = _as_int(count_row.get("count")) if count_row else 0

        rows = await self.db.fetch_all(
            f"""
            SELECT * FROM test_run_retention_policies
            WHERE {where_sql}
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        )
        return QueryResult(
            items=[self._row_to_model(row) for row in rows],
            total_count=total,
            offset=offset,
            limit=limit,
        )

    async def delete(
        self,
        policy_id: str,
        soft_delete: bool = True,
        message: str | None = None,
    ) -> bool:
        result = await super().delete(
            policy_id,
            soft_delete=soft_delete,
            message=message or "Archived test run policy",
        )
        return bool(result)

    async def restore(
        self,
        policy_id: str,
        message: str | None = None,
    ) -> TestRunRetentionPolicy | None:
        result = await super().restore(
            policy_id,
            message=message or "Restored test run policy",
        )
        if isinstance(result, TestRunRetentionPolicy):
            return result
        return None

    def _row_to_model(self, row: DbRow) -> TestRunRetentionPolicy:
        return TestRunRetentionPolicy(
            id=_as_text(row.get("id")),
            scope_type=_as_text(row.get("scope_type"), "project"),
            scope_id=_as_text(row.get("scope_id")),
            max_log_bytes=_as_int(row.get("max_log_bytes")),
            max_artifact_bytes=_as_int(row.get("max_artifact_bytes")),
            max_age_days=_as_int(row.get("max_age_days")),
            notes=_as_optional_text(row.get("notes")),
            created_at=_parse_datetime_required(row.get("created_at"), "created_at"),
            updated_at=_parse_datetime_required(row.get("updated_at"), "updated_at"),
            archived_at=_parse_datetime_optional(row.get("archived_at")),
            last_event_sequence=_as_int(row.get("last_event_sequence")),
            last_revision_number=_as_int(row.get("last_revision_number")),
        )

    def _model_from_row(self, row: DbRow) -> TestRunRetentionPolicy:
        return self._row_to_model(row)

    def _row_from_model(self, model: TestRunRetentionPolicy) -> JsonObject:
        created_at = (
            model.created_at.isoformat()
            if hasattr(model.created_at, "isoformat")
            else str(model.created_at)
        )
        updated_at = (
            model.updated_at.isoformat()
            if hasattr(model.updated_at, "isoformat")
            else str(model.updated_at)
        )
        archived_at = None
        if model.archived_at:
            archived_at = (
                model.archived_at.isoformat()
                if hasattr(model.archived_at, "isoformat")
                else str(model.archived_at)
            )
        return {
            "id": model.id,
            "scope_type": model.scope_type,
            "scope_id": model.scope_id,
            "max_log_bytes": model.max_log_bytes,
            "max_artifact_bytes": model.max_artifact_bytes,
            "max_age_days": model.max_age_days,
            "notes": model.notes,
            "created_at": created_at,
            "updated_at": updated_at,
            "archived_at": archived_at,
            "last_event_sequence": model.last_event_sequence,
            "last_revision_number": model.last_revision_number,
        }

    async def _apply_events(
        self, events: RetentionPolicyEvents
    ) -> TestRunRetentionPolicy | None:
        if not events:
            return None

        policy: TestRunRetentionPolicy | None = None
        for event in events:
            match event.event_type:
                case EventType.TEST_RUN_RETENTION_POLICY_CREATED:
                    payload = event.payload
                    policy = TestRunRetentionPolicy(
                        id=event.aggregate_id,
                        scope_type=_as_text(payload.get("scope_type"), "project"),
                        scope_id=_as_text(payload.get("scope_id")),
                        max_log_bytes=_as_int(payload.get("max_log_bytes")),
                        max_artifact_bytes=_as_int(payload.get("max_artifact_bytes")),
                        max_age_days=_as_int(payload.get("max_age_days")),
                        notes=_as_optional_text(payload.get("notes")),
                    )
                case EventType.TEST_RUN_RETENTION_POLICY_UPDATED if policy:
                    changes = event.payload.get("changes", {})
                    if not isinstance(changes, dict):
                        continue
                    for field, entry in changes.items():
                        if not isinstance(field, str):
                            continue
                        if not isinstance(entry, list | tuple) or len(entry) != 2:
                            continue
                        new_val = entry[1]
                        match field:
                            case "max_log_bytes":
                                policy.max_log_bytes = _as_int(new_val)
                            case "max_artifact_bytes":
                                policy.max_artifact_bytes = _as_int(new_val)
                            case "max_age_days":
                                policy.max_age_days = _as_int(new_val)
                            case "notes":
                                policy.notes = _as_optional_text(new_val)
                case EventType.TEST_RUN_RETENTION_POLICY_DELETED:
                    policy = None
                case EventType.TEST_RUN_RETENTION_POLICY_RESTORED:
                    payload = event.payload
                    content = payload.get("content") or {}
                    if not isinstance(content, dict):
                        content = {}
                    content.setdefault("id", event.aggregate_id)
                    policy = TestRunRetentionPolicy.from_dict(
                        _json_object_to_model_object(content)
                    )

        return policy


def _parse_datetime_required(
    value: DbValue | datetime | None, field_name: str
) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    msg = f"Invalid datetime value for {field_name}: {value!r}"
    raise ValueError(msg)


def _parse_datetime_optional(value: DbValue | datetime | None) -> datetime | None:
    if value is None:
        return None
    return _parse_datetime_required(value, "archived_at")


def _as_text(value: DbValue | datetime | None, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return default


def _as_optional_text(value: DbValue | datetime | None) -> str | None:
    text = _as_text(value)
    return text or None


def _as_int(value: DbValue | datetime | None) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return 0
    return 0


def _json_object_to_model_object(raw: dict[str, JsonValue]) -> ModelObject:
    payload: ModelObject = {}
    for key, value in raw.items():
        payload[str(key)] = _json_value_to_model_value(value)
    return payload


def _json_value_to_model_value(value: JsonValue) -> JsonValue:
    if isinstance(value, dict):
        return {
            str(key): _json_value_to_model_value(item) for key, item in value.items()
        }
    if isinstance(value, list):
        return [_json_value_to_model_value(item) for item in value]
    return value
