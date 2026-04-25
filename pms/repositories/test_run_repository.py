"""Repository for test run records."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from pms.core.events import DomainEvent, EventStore, EventType
from pms.core.revisions import Change, ChangeType, Revision, RevisionStore
from pms.repositories.base import OwnedTransactionRepository, QueryResult

if TYPE_CHECKING:
    from pms.db.connection import Database

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]
type SqlParam = str | int | float | None
type TestRunRow = dict[str, JsonValue]


class TestRunRepository(OwnedTransactionRepository):
    """Repository for test run storage and lookup."""

    __test__ = False

    def __init__(self, db: Database) -> None:
        self.db = db
        self._events = EventStore(db)
        self._revisions = RevisionStore(db)

    async def create(
        self,
        run_id: str,
        server_id: str,
        project_id: str | None,
        config: JsonObject,
        success: bool,
        exit_code: int | None,
        stdout: str,
        stderr: str,
        duration_seconds: float | None,
        started_at: str,
        finished_at: str,
        logs: JsonObject,
        artifacts: JsonObject,
    ) -> None:
        """Create a test run record."""

        async def _create() -> None:
            await self._create_in_transaction(
                run_id=run_id,
                server_id=server_id,
                project_id=project_id,
                config=config,
                success=success,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                duration_seconds=duration_seconds,
                started_at=started_at,
                finished_at=finished_at,
                logs=logs,
                artifacts=artifacts,
            )

        await self._run_in_owned_transaction(
            _create,
            operation_name="create",
        )

    async def _create_in_transaction(
        self,
        run_id: str,
        server_id: str,
        project_id: str | None,
        config: JsonObject,
        success: bool,
        exit_code: int | None,
        stdout: str,
        stderr: str,
        duration_seconds: float | None,
        started_at: str,
        finished_at: str,
        logs: JsonObject,
        artifacts: JsonObject,
    ) -> None:
        """Create a test run record assuming the caller owns the transaction."""
        self._assert_owned_transaction("_create_in_transaction")
        payload = {
            "id": run_id,
            "server_id": server_id,
            "project_id": project_id,
            "config": config,
            "success": success,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "duration_seconds": duration_seconds,
            "started_at": started_at,
            "finished_at": finished_at,
            "logs": logs,
            "artifacts": artifacts,
        }
        await self.db.execute(
            """
            INSERT INTO test_runs (
                id, server_id, project_id, config, success, exit_code,
                stdout, stderr, duration_seconds,
                started_at, finished_at, logs, artifacts
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                server_id,
                project_id,
                json.dumps(config),
                1 if success else 0,
                exit_code,
                stdout,
                stderr,
                duration_seconds,
                started_at,
                finished_at,
                json.dumps(logs),
                json.dumps(artifacts),
            ),
        )

        event_type = (
            EventType.TEST_RUN_COMPLETED if success else EventType.TEST_RUN_FAILED
        )
        await self._events.append(
            DomainEvent(
                event_type=event_type,
                aggregate_type="test_run",
                aggregate_id=run_id,
                payload=payload,
            )
        )
        revision = Revision.create_initial(
            entity_type="test_run",
            entity_id=run_id,
            content=payload,
            message="Created test run",
        )
        await self._revisions.save_revision(revision)

    async def get_by_ids(self, run_ids: list[str]) -> list[TestRunRow]:
        """Fetch test runs by IDs."""
        if not run_ids:
            return []
        unique_ids = list(dict.fromkeys(run_ids))
        placeholders = ", ".join("?" * len(unique_ids))
        rows = await self.db.fetch_all(
            f"SELECT * FROM test_runs WHERE id IN ({placeholders})",
            tuple(unique_ids),
        )
        return rows

    async def get_by_id(self, run_id: str) -> TestRunRow | None:
        """Fetch a single test run by ID."""
        return await self.db.fetch_one(
            "SELECT * FROM test_runs WHERE id = ?",
            (run_id,),
        )

    async def list_runs(
        self,
        server_id: str | None = None,
        project_id: str | None = None,
        success: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[TestRunRow]:
        """List test runs with optional filters."""
        where_clauses = []
        params: list[SqlParam] = []

        if server_id:
            where_clauses.append("server_id = ?")
            params.append(server_id)

        if project_id:
            where_clauses.append("project_id = ?")
            params.append(project_id)

        if success is not None:
            where_clauses.append("success = ?")
            params.append(1 if success else 0)

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        count_row = await self.db.fetch_one(
            f"SELECT COUNT(*) as count FROM test_runs WHERE {where_sql}",
            tuple(params),
        )
        total = count_row["count"] if count_row else 0

        rows = await self.db.fetch_all(
            f"""
            SELECT * FROM test_runs
            WHERE {where_sql}
            ORDER BY started_at DESC
            LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        )

        return QueryResult(
            items=list(rows),
            total_count=total,
            offset=offset,
            limit=limit,
        )

    async def update_payloads(
        self,
        run_id: str,
        stdout: str,
        stderr: str,
        logs: JsonObject,
        artifacts: JsonObject,
    ) -> None:
        """Update stored payloads for a test run."""

        async def _update() -> None:
            await self._update_payloads_in_transaction(
                run_id=run_id,
                stdout=stdout,
                stderr=stderr,
                logs=logs,
                artifacts=artifacts,
            )

        await self._run_in_owned_transaction(
            _update,
            operation_name="update_payloads",
        )

    async def _update_payloads_in_transaction(
        self,
        run_id: str,
        stdout: str,
        stderr: str,
        logs: JsonObject,
        artifacts: JsonObject,
    ) -> None:
        """Update stored payloads assuming the caller owns the transaction."""
        self._assert_owned_transaction("_update_payloads_in_transaction")
        existing = await self.get_by_id(run_id)
        if existing is None:
            return

        existing_payload = dict(existing)
        for field in ("config", "logs", "artifacts"):
            raw = existing_payload.get(field)
            if isinstance(raw, str):
                try:
                    existing_payload[field] = json.loads(raw)
                except json.JSONDecodeError:
                    existing_payload[field] = {}

        await self.db.execute(
            """
            UPDATE test_runs
            SET stdout = ?, stderr = ?, logs = ?, artifacts = ?
            WHERE id = ?
            """,
            (
                stdout,
                stderr,
                json.dumps(logs),
                json.dumps(artifacts),
                run_id,
            ),
        )

        updated = dict(existing_payload)
        updated.update(
            {
                "stdout": stdout,
                "stderr": stderr,
                "logs": logs,
                "artifacts": artifacts,
            }
        )
        changes: list[Change] = []
        for field in ("stdout", "stderr", "logs", "artifacts"):
            old_val = existing_payload.get(field)
            new_val = updated.get(field)
            if old_val != new_val:
                changes.append(
                    Change(
                        field_name=field,
                        old_value=json.dumps(old_val) if old_val is not None else None,
                        new_value=json.dumps(new_val) if new_val is not None else None,
                        change_type=ChangeType.UPDATE,
                    )
                )

        prev_revision = await self._revisions.get_revision("test_run", run_id)
        if prev_revision:
            revision = Revision.create_from_parent(
                parent=prev_revision,
                new_content=updated,
                changes=changes,
                message="Updated test run payloads",
            )
        else:
            revision = Revision.create_initial(
                entity_type="test_run",
                entity_id=run_id,
                content=updated,
                message="Updated test run payloads",
            )
        await self._revisions.save_revision(revision)

        await self._events.append(
            DomainEvent(
                event_type=EventType.TEST_RUN_UPDATED,
                aggregate_type="test_run",
                aggregate_id=run_id,
                payload={
                    "changes": {
                        c.field_name: (c.old_value, c.new_value) for c in changes
                    }
                },
            )
        )
