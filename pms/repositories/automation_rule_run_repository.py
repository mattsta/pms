"""Repository for automation rule run history."""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING

from pms.models.automation_rule import AutomationRuleRun, JsonObject, JsonValue
from pms.repositories.base import QueryResult

if TYPE_CHECKING:
    from pms.db.connection import Database
    from pms.db.types import DbRow, DbValue


class AutomationRuleRunRepository:
    """Repository for automation rule executions."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def record(self, run: AutomationRuleRun) -> AutomationRuleRun:
        """Insert an automation rule run record."""
        await self.db.execute(
            """
            INSERT INTO automation_rule_runs (
                id, rule_id, event_id, status, started_at, completed_at, error, output
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run.id,
                run.rule_id,
                run.event_id,
                run.status,
                run.started_at.isoformat(),
                run.completed_at.isoformat() if run.completed_at else None,
                run.error,
                json.dumps(run.output),
            ),
        )
        return run

    async def list_by_rule(
        self,
        rule_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[AutomationRuleRun]:
        """List run history for a rule."""
        count_row = await self.db.fetch_one(
            "SELECT COUNT(*) as count FROM automation_rule_runs WHERE rule_id = ?",
            (rule_id,),
        )
        total = _as_int(count_row.get("count")) if count_row else 0

        rows = await self.db.fetch_all(
            """
            SELECT * FROM automation_rule_runs
            WHERE rule_id = ?
            ORDER BY started_at DESC
            LIMIT ? OFFSET ?
            """,
            (rule_id, limit, offset),
        )
        items = [self._row_to_model(row) for row in rows]
        return QueryResult(items=items, total_count=total, limit=limit, offset=offset)

    async def get_last_run_at(self, rule_id: str) -> datetime | None:
        """Get most recent run timestamp for a rule."""
        row = await self.db.fetch_one(
            """
            SELECT MAX(started_at) as ts
            FROM automation_rule_runs
            WHERE rule_id = ?
            """,
            (rule_id,),
        )
        if not row or not row.get("ts"):
            return None
        try:
            return datetime.fromisoformat(str(row["ts"]))
        except ValueError:
            return None

    def _row_to_model(self, row: DbRow) -> AutomationRuleRun:
        output: JsonObject = {}
        if row.get("output"):
            try:
                parsed = json.loads(str(row["output"]))
                if isinstance(parsed, dict):
                    output = {
                        str(key): self._coerce_json_value(value)
                        for key, value in parsed.items()
                    }
            except json.JSONDecodeError:
                output = {}
        started_at = datetime.fromisoformat(str(row["started_at"]))
        completed_at = (
            datetime.fromisoformat(str(row["completed_at"]))
            if row.get("completed_at")
            else None
        )
        return AutomationRuleRun(
            id=str(row["id"]),
            rule_id=str(row["rule_id"]),
            event_id=str(row["event_id"]) if row.get("event_id") else None,
            status=str(row["status"]),
            started_at=started_at,
            completed_at=completed_at,
            error=str(row["error"]) if row.get("error") else None,
            output=output,
        )

    def _coerce_json_value(self, raw: JsonValue | None) -> JsonValue:
        if isinstance(raw, dict):
            return {
                str(key): self._coerce_json_value(value) for key, value in raw.items()
            }
        if isinstance(raw, list):
            return [self._coerce_json_value(value) for value in raw]
        if isinstance(raw, (str, int, float, bool)) or raw is None:
            return raw
        return str(raw)


def _as_int(value: DbValue | None) -> int:
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
