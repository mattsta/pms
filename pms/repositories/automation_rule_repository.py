"""Repository for automation rules."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from pms.core.events import DomainEvent, EventStore, EventType
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.models.automation_rule import AutomationActionType, AutomationRule
from pms.repositories.base import EventSourcedRepository

if TYPE_CHECKING:
    from pms.db.connection import Database


class AutomationRuleRepository(EventSourcedRepository[AutomationRule]):
    """Repository for automation rules."""

    def __init__(self, db: Database) -> None:
        super().__init__(
            db,
            EventStore(db),
            RevisionStore(db),
            MetricsCollector(db),
        )

    @property
    def entity_type(self) -> str:
        return "automation_rule"

    @property
    def table_name(self) -> str:
        return "automation_rules"

    @property
    def archive_column(self) -> str | None:
        return "archived_at"

    async def create(
        self,
        name: str,
        event_pattern: str,
        action_type: AutomationActionType,
        action_payload: dict[str, Any],
        description: str | None = None,
        aggregate_type: str | None = None,
        aggregate_id: str | None = None,
        enabled: bool = True,
        cooldown_seconds: float = 0.0,
    ) -> AutomationRule:
        rule = AutomationRule(
            name=name,
            description=description,
            event_pattern=event_pattern,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            action_type=action_type,
            action_payload=action_payload,
            enabled=enabled,
            cooldown_seconds=cooldown_seconds,
        )
        payload = {
            "name": name,
            "description": description,
            "event_pattern": event_pattern,
            "aggregate_type": aggregate_type,
            "aggregate_id": aggregate_id,
            "action_type": action_type.value,
            "action_payload": action_payload,
            "enabled": enabled,
            "cooldown_seconds": cooldown_seconds,
        }
        return await self.save(
            rule,
            EventType.AUTOMATION_RULE_CREATED,
            payload,
            message=f"Created automation rule '{name}'",
        )

    async def get_by_id(
        self, rule_id: str, *, include_archived: bool = False
    ) -> AutomationRule | None:
        if include_archived:
            row = await self.db.fetch_one(
                "SELECT * FROM automation_rules WHERE id = ?",
                (rule_id,),
            )
        else:
            row = await self.db.fetch_one(
                """
                SELECT * FROM automation_rules
                WHERE id = ? AND archived_at IS NULL
                """,
                (rule_id,),
            )
        return self._row_to_model(row) if row else None

    async def get_by_name(
        self, name: str, *, include_archived: bool = False
    ) -> AutomationRule | None:
        if include_archived:
            row = await self.db.fetch_one(
                "SELECT * FROM automation_rules WHERE name = ?",
                (name,),
            )
        else:
            row = await self.db.fetch_one(
                """
                SELECT * FROM automation_rules
                WHERE name = ? AND archived_at IS NULL
                """,
                (name,),
            )
        return self._row_to_model(row) if row else None

    async def list_all(
        self,
        *,
        include_archived: bool = False,
        enabled: bool | None = None,
    ) -> list[AutomationRule]:
        conditions: list[str] = []
        params: list[Any] = []
        if enabled is not None:
            conditions.append("enabled = ?")
            params.append(1 if enabled else 0)
        if not include_archived:
            conditions.append("archived_at IS NULL")
        where_sql = ""
        if conditions:
            where_sql = "WHERE " + " AND ".join(conditions)
        rows = await self.db.fetch_all(
            f"""
            SELECT * FROM automation_rules
            {where_sql}
            ORDER BY name
            """,
            tuple(params),
        )
        return [self._row_to_model(row) for row in rows]

    async def update(
        self,
        rule_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        event_pattern: str | None = None,
        aggregate_type: str | None = None,
        aggregate_id: str | None = None,
        action_type: AutomationActionType | None = None,
        action_payload: dict[str, Any] | None = None,
        enabled: bool | None = None,
        cooldown_seconds: float | None = None,
    ) -> AutomationRule | None:
        rule = await self.get_by_id(rule_id)
        if rule is None:
            return None

        changes: dict[str, Any] = {}
        if name is not None and name != rule.name:
            changes["name"] = (rule.name, name)
            rule.name = name
        if description is not None and description != rule.description:
            changes["description"] = (rule.description, description)
            rule.description = description
        if event_pattern is not None and event_pattern != rule.event_pattern:
            changes["event_pattern"] = (rule.event_pattern, event_pattern)
            rule.event_pattern = event_pattern
        if aggregate_type is not None and aggregate_type != rule.aggregate_type:
            changes["aggregate_type"] = (rule.aggregate_type, aggregate_type)
            rule.aggregate_type = aggregate_type
        if aggregate_id is not None and aggregate_id != rule.aggregate_id:
            changes["aggregate_id"] = (rule.aggregate_id, aggregate_id)
            rule.aggregate_id = aggregate_id
        if action_type is not None and action_type != rule.action_type:
            changes["action_type"] = (rule.action_type.value, action_type.value)
            rule.action_type = action_type
        if action_payload is not None and action_payload != rule.action_payload:
            changes["action_payload"] = (rule.action_payload, action_payload)
            rule.action_payload = action_payload
        if enabled is not None and enabled != rule.enabled:
            changes["enabled"] = (rule.enabled, enabled)
            rule.enabled = enabled
        if cooldown_seconds is not None and cooldown_seconds != rule.cooldown_seconds:
            changes["cooldown_seconds"] = (rule.cooldown_seconds, cooldown_seconds)
            rule.cooldown_seconds = cooldown_seconds

        if not changes:
            return rule

        rule.touch()
        payload = {"changes": changes}
        return await self.save(
            rule,
            EventType.AUTOMATION_RULE_UPDATED,
            payload,
            message="Updated automation rule",
        )

    async def delete(
        self,
        rule_id: str,
        soft_delete: bool = True,
        message: str | None = None,
    ) -> bool:
        return await super().delete(
            rule_id,
            soft_delete=soft_delete,
            message=message or "Archived automation rule",
        )

    def _row_to_model(self, row: dict[str, Any]) -> AutomationRule:
        payload: dict[str, Any] = {}
        if row.get("action_payload"):
            try:
                raw_payload = json.loads(row["action_payload"])
                if isinstance(raw_payload, dict):
                    payload = raw_payload
            except json.JSONDecodeError:
                payload = {}
        action_type_value = row.get("action_type", AutomationActionType.ADD_COMMENT)
        try:
            action_type = AutomationActionType(action_type_value)
        except ValueError:
            action_type = AutomationActionType.ADD_COMMENT
        return AutomationRule(
            id=row["id"],
            name=row["name"],
            description=row.get("description"),
            event_pattern=row.get("event_pattern", ""),
            aggregate_type=row.get("aggregate_type"),
            aggregate_id=row.get("aggregate_id"),
            action_type=action_type,
            action_payload=payload,
            enabled=bool(row.get("enabled", 1)),
            cooldown_seconds=float(row.get("cooldown_seconds", 0.0)),
            created_at=self._parse_datetime_required(row.get("created_at")),
            updated_at=self._parse_datetime_required(row.get("updated_at")),
            archived_at=self._parse_datetime_optional(row.get("archived_at")),
            last_event_sequence=row.get("last_event_sequence", 0),
            last_revision_number=row.get("last_revision_number", 0),
        )

    def _model_from_row(self, row: dict[str, Any]) -> AutomationRule:
        return self._row_to_model(row)

    def _row_from_model(self, model: AutomationRule) -> dict[str, Any]:
        return {
            "id": model.id,
            "name": model.name,
            "description": model.description,
            "event_pattern": model.event_pattern,
            "aggregate_type": model.aggregate_type,
            "aggregate_id": model.aggregate_id,
            "action_type": model.action_type.value,
            "action_payload": json.dumps(model.action_payload),
            "enabled": 1 if model.enabled else 0,
            "cooldown_seconds": model.cooldown_seconds,
            "created_at": model.created_at.isoformat(),
            "updated_at": model.updated_at.isoformat(),
            "archived_at": model.archived_at.isoformat() if model.archived_at else None,
            "last_event_sequence": model.last_event_sequence,
            "last_revision_number": model.last_revision_number,
        }

    async def _apply_events(
        self, events: list[DomainEvent[dict[str, Any]]]
    ) -> AutomationRule | None:
        if not events:
            return None

        rule: AutomationRule | None = None
        for event in events:
            match event.event_type:
                case EventType.AUTOMATION_RULE_CREATED:
                    payload = event.payload
                    action_type_value = payload.get(
                        "action_type", AutomationActionType.ADD_COMMENT
                    )
                    try:
                        action_type = AutomationActionType(action_type_value)
                    except ValueError:
                        action_type = AutomationActionType.ADD_COMMENT
                    rule = AutomationRule(
                        id=event.aggregate_id,
                        name=payload.get("name", ""),
                        description=payload.get("description"),
                        event_pattern=payload.get("event_pattern", ""),
                        aggregate_type=payload.get("aggregate_type"),
                        aggregate_id=payload.get("aggregate_id"),
                        action_type=action_type,
                        action_payload=payload.get("action_payload") or {},
                        enabled=bool(payload.get("enabled", True)),
                        cooldown_seconds=float(payload.get("cooldown_seconds", 0.0)),
                    )
                case EventType.AUTOMATION_RULE_UPDATED if rule:
                    changes = event.payload.get("changes", {})
                    for field, (_old_val, new_val) in changes.items():
                        match field:
                            case "name":
                                rule.name = new_val
                            case "description":
                                rule.description = new_val
                            case "event_pattern":
                                rule.event_pattern = new_val
                            case "aggregate_type":
                                rule.aggregate_type = new_val
                            case "aggregate_id":
                                rule.aggregate_id = new_val
                            case "action_type":
                                try:
                                    rule.action_type = AutomationActionType(new_val)
                                except ValueError:
                                    rule.action_type = AutomationActionType.ADD_COMMENT
                            case "action_payload":
                                rule.action_payload = new_val or {}
                            case "enabled":
                                rule.enabled = bool(new_val)
                            case "cooldown_seconds":
                                try:
                                    rule.cooldown_seconds = float(new_val)
                                except TypeError, ValueError:
                                    rule.cooldown_seconds = 0.0
                case EventType.AUTOMATION_RULE_DELETED if rule:
                    rule.archived_at = event.metadata.timestamp
                case EventType.AUTOMATION_RULE_RESTORED if rule:
                    rule.archived_at = None

        if rule:
            rule.last_event_sequence = events[-1].sequence_number
        return rule

    @staticmethod
    def _parse_datetime_required(value: Any) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str) and value:
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                pass
        return datetime.now(UTC)

    @staticmethod
    def _parse_datetime_optional(value: Any) -> datetime | None:
        if value is None:
            return None
        return AutomationRuleRepository._parse_datetime_required(value)
