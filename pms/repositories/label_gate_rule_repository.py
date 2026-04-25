"""Repository for label gate rules."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from pms.core.events import DomainEvent, EventStore, EventType
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.models.label_gate_rule import LabelGateRule, LabelGateRuleType
from pms.repositories.base import EventSourcedRepository

if TYPE_CHECKING:
    from pms.db.connection import Database


class LabelGateRuleRepository(EventSourcedRepository[LabelGateRule]):
    """Repository for label gate rules."""

    def __init__(self, db: Database) -> None:
        super().__init__(
            db,
            EventStore(db),
            RevisionStore(db),
            MetricsCollector(db),
        )

    @property
    def entity_type(self) -> str:
        return "label_gate_rule"

    @property
    def table_name(self) -> str:
        return "label_gate_rules"

    @property
    def archive_column(self) -> str | None:
        return "archived_at"

    async def create(
        self,
        workflow_id: str,
        entity_type: str,
        from_state: str,
        to_state: str,
        rule_type: LabelGateRuleType,
        label_id: str | None = None,
        category_id: str | None = None,
        message: str | None = None,
    ) -> LabelGateRule:
        rule = LabelGateRule(
            workflow_id=workflow_id,
            entity_type=entity_type,
            from_state=from_state,
            to_state=to_state,
            rule_type=rule_type,
            label_id=label_id,
            category_id=category_id,
            message=message,
        )
        payload = {
            "workflow_id": workflow_id,
            "entity_type": entity_type,
            "from_state": from_state,
            "to_state": to_state,
            "rule_type": rule_type.value,
            "label_id": label_id,
            "category_id": category_id,
            "message": message,
        }

        return await self.save(
            rule,
            EventType.LABEL_GATE_RULE_CREATED,
            payload,
            message="Created label gate rule",
        )

    async def list_for_transition(
        self,
        workflow_id: str,
        entity_type: str,
        from_state: str,
        to_state: str,
    ) -> list[LabelGateRule]:
        rows = await self.db.fetch_all(
            """
            SELECT * FROM label_gate_rules
            WHERE workflow_id = ?
              AND entity_type = ?
              AND from_state = ?
              AND to_state = ?
              AND archived_at IS NULL
            ORDER BY created_at ASC
            """,
            (workflow_id, entity_type, from_state, to_state),
        )
        return [self._row_to_model(row) for row in rows]

    async def delete(
        self,
        rule_id: str,
        soft_delete: bool = True,
        message: str | None = None,
    ) -> bool:
        return await super().delete(
            rule_id,
            soft_delete=soft_delete,
            message=message or "Deleted label gate rule",
        )

    def _row_to_model(self, row: dict[str, Any]) -> LabelGateRule:
        return LabelGateRule(
            id=row["id"],
            workflow_id=row["workflow_id"],
            entity_type=row["entity_type"],
            from_state=row["from_state"],
            to_state=row["to_state"],
            rule_type=LabelGateRuleType(row["rule_type"]),
            label_id=row.get("label_id"),
            category_id=row.get("category_id"),
            message=row.get("message"),
            created_at=_parse_datetime_required(row.get("created_at"), "created_at"),
            updated_at=_parse_datetime_required(row.get("updated_at"), "updated_at"),
            last_event_sequence=row.get("last_event_sequence", 0),
            last_revision_number=row.get("last_revision_number", 0),
        )

    def _model_from_row(self, row: dict[str, Any]) -> LabelGateRule:
        return self._row_to_model(row)

    def _row_from_model(self, model: LabelGateRule) -> dict[str, Any]:
        return {
            "id": model.id,
            "workflow_id": model.workflow_id,
            "entity_type": model.entity_type,
            "from_state": model.from_state,
            "to_state": model.to_state,
            "rule_type": model.rule_type.value,
            "label_id": model.label_id,
            "category_id": model.category_id,
            "message": model.message,
            "created_at": model.created_at.isoformat(),
            "updated_at": model.updated_at.isoformat(),
            "last_event_sequence": model.last_event_sequence,
            "last_revision_number": model.last_revision_number,
        }

    async def _apply_events(
        self, events: list[DomainEvent[dict[str, Any]]]
    ) -> LabelGateRule | None:
        if not events:
            return None

        rule: LabelGateRule | None = None
        for event in events:
            match event.event_type:
                case EventType.LABEL_GATE_RULE_CREATED:
                    payload = event.payload
                    rule = LabelGateRule(
                        id=event.aggregate_id,
                        workflow_id=payload.get("workflow_id", ""),
                        entity_type=payload.get("entity_type", "task"),
                        from_state=payload.get("from_state", ""),
                        to_state=payload.get("to_state", ""),
                        rule_type=LabelGateRuleType(
                            payload.get("rule_type", LabelGateRuleType.REQUIRE_LABEL)
                        ),
                        label_id=payload.get("label_id"),
                        category_id=payload.get("category_id"),
                        message=payload.get("message"),
                    )
                case EventType.LABEL_GATE_RULE_UPDATED if rule:
                    changes = event.payload.get("changes", {})
                    for field, (old_val, new_val) in changes.items():
                        match field:
                            case "workflow_id":
                                rule.workflow_id = new_val
                            case "entity_type":
                                rule.entity_type = new_val
                            case "from_state":
                                rule.from_state = new_val
                            case "to_state":
                                rule.to_state = new_val
                            case "rule_type":
                                rule.rule_type = LabelGateRuleType(new_val)
                            case "label_id":
                                rule.label_id = new_val
                            case "category_id":
                                rule.category_id = new_val
                            case "message":
                                rule.message = new_val
                case EventType.LABEL_GATE_RULE_DELETED:
                    rule = None
                case EventType.LABEL_GATE_RULE_RESTORED:
                    payload = event.payload
                    content = payload.get("content") or {}
                    rule = LabelGateRule(
                        id=content.get("id", event.aggregate_id),
                        workflow_id=content.get("workflow_id", ""),
                        entity_type=content.get("entity_type", "task"),
                        from_state=content.get("from_state", ""),
                        to_state=content.get("to_state", ""),
                        rule_type=LabelGateRuleType(
                            content.get("rule_type", LabelGateRuleType.REQUIRE_LABEL)
                        ),
                        label_id=content.get("label_id"),
                        category_id=content.get("category_id"),
                        message=content.get("message"),
                    )

        return rule


def _parse_datetime_required(value: Any, field_name: str) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    msg = f"Invalid datetime value for {field_name}: {value!r}"
    raise ValueError(msg)
