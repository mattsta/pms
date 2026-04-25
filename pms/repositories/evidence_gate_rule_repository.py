"""Repository for evidence gate rules."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from pms.core.events import DomainEvent, EventStore, EventType
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.models.evidence_gate_rule import EvidenceGateRule
from pms.models.json_types import JsonObject
from pms.repositories.base import EventSourcedRepository

if TYPE_CHECKING:
    from pms.db.connection import Database
    from pms.db.types import DbRow, DbValue

type GateRuleEventPayload = JsonObject
type GateRuleEvents = list[DomainEvent[GateRuleEventPayload]]


class EvidenceGateRuleRepository(EventSourcedRepository[EvidenceGateRule]):
    """Repository for evidence gate rules."""

    def __init__(self, db: Database) -> None:
        super().__init__(
            db,
            EventStore(db),
            RevisionStore(db),
            MetricsCollector(db),
        )

    @property
    def entity_type(self) -> str:
        return "evidence_gate_rule"

    @property
    def table_name(self) -> str:
        return "evidence_gate_rules"

    @property
    def archive_column(self) -> str | None:
        return "archived_at"

    async def create(
        self,
        workflow_id: str,
        entity_type: str,
        from_state: str,
        to_state: str,
        evidence_type: str,
        min_count: int = 1,
        require_success: bool = False,
        message: str | None = None,
    ) -> EvidenceGateRule:
        rule = EvidenceGateRule(
            workflow_id=workflow_id,
            entity_type=entity_type,
            from_state=from_state,
            to_state=to_state,
            evidence_type=evidence_type,
            min_count=min_count,
            require_success=require_success,
            message=message,
        )
        payload = {
            "workflow_id": workflow_id,
            "entity_type": entity_type,
            "from_state": from_state,
            "to_state": to_state,
            "evidence_type": evidence_type,
            "min_count": min_count,
            "require_success": require_success,
            "message": message,
        }

        return await self.save(
            rule,
            EventType.EVIDENCE_GATE_RULE_CREATED,
            payload,
            message="Created evidence gate rule",
        )

    async def list_for_transition(
        self,
        workflow_id: str,
        entity_type: str,
        from_state: str,
        to_state: str,
    ) -> list[EvidenceGateRule]:
        rows = await self.db.fetch_all(
            """
            SELECT * FROM evidence_gate_rules
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
        result = await super().delete(
            rule_id,
            soft_delete=soft_delete,
            message=message or "Deleted evidence gate rule",
        )
        return bool(result)

    def _row_to_model(self, row: DbRow) -> EvidenceGateRule:
        return EvidenceGateRule(
            id=str(row["id"]),
            workflow_id=str(row["workflow_id"]),
            entity_type=str(row["entity_type"]),
            from_state=str(row["from_state"]),
            to_state=str(row["to_state"]),
            evidence_type=str(row["evidence_type"]),
            min_count=_as_int(row.get("min_count"), 1),
            require_success=_as_bool(row.get("require_success")),
            message=_as_optional_text(row.get("message")),
            created_at=_parse_datetime_required(row.get("created_at"), "created_at"),
            updated_at=_parse_datetime_required(row.get("updated_at"), "updated_at"),
            last_event_sequence=_as_int(row.get("last_event_sequence")),
            last_revision_number=_as_int(row.get("last_revision_number")),
        )

    def _model_from_row(self, row: DbRow) -> EvidenceGateRule:
        return self._row_to_model(row)

    def _row_from_model(self, model: EvidenceGateRule) -> JsonObject:
        return {
            "id": model.id,
            "workflow_id": model.workflow_id,
            "entity_type": model.entity_type,
            "from_state": model.from_state,
            "to_state": model.to_state,
            "evidence_type": model.evidence_type,
            "min_count": model.min_count,
            "require_success": 1 if model.require_success else 0,
            "message": model.message,
            "created_at": model.created_at.isoformat(),
            "updated_at": model.updated_at.isoformat(),
            "last_event_sequence": model.last_event_sequence,
            "last_revision_number": model.last_revision_number,
        }

    async def _apply_events(self, events: GateRuleEvents) -> EvidenceGateRule | None:
        if not events:
            return None

        rule: EvidenceGateRule | None = None
        for event in events:
            match event.event_type:
                case EventType.EVIDENCE_GATE_RULE_CREATED:
                    payload = event.payload
                    rule = EvidenceGateRule(
                        id=event.aggregate_id,
                        workflow_id=_as_text(payload.get("workflow_id")),
                        entity_type=_as_text(payload.get("entity_type"), "task"),
                        from_state=_as_text(payload.get("from_state")),
                        to_state=_as_text(payload.get("to_state")),
                        evidence_type=_as_text(payload.get("evidence_type")),
                        min_count=_as_int(payload.get("min_count"), 1),
                        require_success=_as_bool(payload.get("require_success")),
                        message=_as_optional_text(payload.get("message")),
                    )
                case EventType.EVIDENCE_GATE_RULE_UPDATED if rule:
                    changes = event.payload.get("changes", {})
                    if not isinstance(changes, dict):
                        continue
                    for field, change_entry in changes.items():
                        if not isinstance(field, str):
                            continue
                        if (
                            not isinstance(change_entry, list | tuple)
                            or len(change_entry) != 2
                        ):
                            continue
                        new_val = change_entry[1]
                        match field:
                            case "workflow_id":
                                rule.workflow_id = _as_text(new_val)
                            case "entity_type":
                                rule.entity_type = _as_text(new_val)
                            case "from_state":
                                rule.from_state = _as_text(new_val)
                            case "to_state":
                                rule.to_state = _as_text(new_val)
                            case "evidence_type":
                                rule.evidence_type = _as_text(new_val)
                            case "min_count":
                                rule.min_count = _as_int(new_val)
                            case "require_success":
                                rule.require_success = _as_bool(new_val)
                            case "message":
                                rule.message = _as_optional_text(new_val)
                case EventType.EVIDENCE_GATE_RULE_DELETED:
                    rule = None
                case EventType.EVIDENCE_GATE_RULE_RESTORED:
                    payload = event.payload
                    content = payload.get("content") or {}
                    if not isinstance(content, dict):
                        content = {}
                    rule = EvidenceGateRule(
                        id=_as_text(content.get("id"), event.aggregate_id),
                        workflow_id=_as_text(content.get("workflow_id")),
                        entity_type=_as_text(content.get("entity_type"), "task"),
                        from_state=_as_text(content.get("from_state")),
                        to_state=_as_text(content.get("to_state")),
                        evidence_type=_as_text(content.get("evidence_type")),
                        min_count=_as_int(content.get("min_count"), 1),
                        require_success=_as_bool(content.get("require_success")),
                        message=_as_optional_text(content.get("message")),
                    )

        return rule


def _parse_datetime_required(
    value: DbValue | datetime | None, field_name: str
) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    msg = f"Invalid datetime value for {field_name}: {value!r}"
    raise ValueError(msg)


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


def _as_int(value: DbValue | datetime | None, default: int = 0) -> int:
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
            return default
    return default


def _as_bool(value: DbValue | datetime | None) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, float):
        return value != 0.0
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "y"}
    return False
