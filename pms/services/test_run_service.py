"""Service for reading test run records."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from pms.core.metrics import MetricsCollector
from pms.models.json_types import JsonObject, JsonValue
from pms.repositories.base import QueryResult
from pms.repositories.test_run_repository import TestRunRepository

if TYPE_CHECKING:
    from pms.db.connection import Database


@dataclass
class TestRunRecord:
    """Stored test run record with optional payloads."""

    id: str
    server_id: str
    project_id: str | None
    success: bool
    exit_code: int | None
    duration_seconds: float | None
    started_at: datetime
    finished_at: datetime
    command: str | None = None
    runner: str | None = None
    plan_id: str | None = None
    task_ids: tuple[str, ...] = ()
    stdout: str | None = None
    stderr: str | None = None
    logs: JsonObject = field(default_factory=dict)
    artifacts: JsonObject = field(default_factory=dict)
    config: JsonObject = field(default_factory=dict)


class TestRunService:
    """Service for listing and retrieving test runs."""

    __test__ = False

    def __init__(self, db: Database, metrics: MetricsCollector) -> None:
        self.db = db
        self.metrics = metrics
        self._repo = TestRunRepository(db)

    async def list_test_runs(
        self,
        server_id: str | None = None,
        project_id: str | None = None,
        success: bool | None = None,
        limit: int = 100,
        offset: int = 0,
        include_output: bool = False,
        include_logs: bool = False,
        include_artifacts: bool = False,
    ) -> QueryResult[TestRunRecord]:
        """List test runs with optional filters."""
        result = await self._repo.list_runs(
            server_id=server_id,
            project_id=project_id,
            success=success,
            limit=limit,
            offset=offset,
        )

        items = [
            self._row_to_record(
                row,
                include_output=include_output,
                include_logs=include_logs,
                include_artifacts=include_artifacts,
            )
            for row in result.items
        ]

        await self.metrics.record_counter(
            "test_run.listed",
            labels={"project_id": project_id or "all"},
        )
        await self.metrics.flush_best_effort(context="test_run.list_test_runs")

        return QueryResult(
            items=items,
            total_count=result.total_count,
            offset=result.offset,
            limit=result.limit,
        )

    async def get_test_run(
        self,
        run_id: str,
        include_output: bool = True,
        include_logs: bool = True,
        include_artifacts: bool = True,
    ) -> TestRunRecord | None:
        """Get a single test run by ID."""
        row = await self._repo.get_by_id(run_id)
        if row is None:
            return None

        await self.metrics.record_counter(
            "test_run.viewed",
            labels={"run_id": run_id},
        )
        await self.metrics.flush_best_effort(context="test_run.get_test_run")

        return self._row_to_record(
            row,
            include_output=include_output,
            include_logs=include_logs,
            include_artifacts=include_artifacts,
        )

    async def create_test_run(
        self,
        *,
        run_id: str,
        server_id: str,
        project_id: str | None,
        config: JsonObject,
        success: bool,
        exit_code: int | None,
        stdout: str | None,
        stderr: str | None,
        duration_seconds: float | None,
        started_at: datetime,
        finished_at: datetime,
        logs: JsonObject,
        artifacts: JsonObject,
    ) -> TestRunRecord:
        """Create a test run record."""
        server_row = await self.db.fetch_one(
            "SELECT id FROM test_servers WHERE id = ?",
            (server_id,),
        )
        if server_row is None:
            raise ValueError("Test server not found")
        if project_id:
            project_row = await self.db.fetch_one(
                "SELECT id FROM projects WHERE id = ?",
                (project_id,),
            )
            if project_row is None:
                raise ValueError("Project not found")

        normalized_logs = self._normalize_logs(logs, finished_at)
        normalized_artifacts = self._normalize_artifacts(artifacts, finished_at)

        async with self.db.transaction():
            await self._repo._create_in_transaction(
                run_id=run_id,
                server_id=server_id,
                project_id=project_id,
                config=config,
                success=success,
                exit_code=exit_code,
                stdout=stdout or "",
                stderr=stderr or "",
                duration_seconds=duration_seconds,
                started_at=started_at.isoformat(),
                finished_at=finished_at.isoformat(),
                logs=normalized_logs,
                artifacts=normalized_artifacts,
            )

            await self.metrics.record_counter(
                "test_run.created",
                labels={"server_id": server_id, "project_id": project_id or "none"},
            )
            await self.metrics.flush()

        command_raw = config.get("test_command") or config.get("command")
        command = command_raw if isinstance(command_raw, str) else None
        runner_raw = config.get("runner")
        runner = runner_raw if isinstance(runner_raw, str) else None
        plan_id_raw = config.get("plan_id")
        plan_id = plan_id_raw if isinstance(plan_id_raw, str) else None
        task_ids_raw = config.get("task_ids", [])
        task_ids = (
            tuple(str(task_id) for task_id in task_ids_raw)
            if isinstance(task_ids_raw, list)
            else ()
        )

        return TestRunRecord(
            id=run_id,
            server_id=server_id,
            project_id=project_id,
            success=success,
            exit_code=exit_code,
            duration_seconds=duration_seconds,
            started_at=started_at,
            finished_at=finished_at,
            command=command,
            runner=runner,
            plan_id=plan_id,
            task_ids=task_ids,
            stdout=stdout,
            stderr=stderr,
            logs=normalized_logs,
            artifacts=normalized_artifacts,
            config=config,
        )

    async def get_test_runs_by_ids(
        self,
        run_ids: list[str],
        include_output: bool = False,
        include_logs: bool = False,
        include_artifacts: bool = False,
    ) -> dict[str, TestRunRecord]:
        """Get multiple test runs by ID."""
        if not run_ids:
            return {}
        rows = await self._repo.get_by_ids(run_ids)
        records = {
            str(row["id"]): self._row_to_record(
                row,
                include_output=include_output,
                include_logs=include_logs,
                include_artifacts=include_artifacts,
            )
            for row in rows
        }
        return records

    def _row_to_record(
        self,
        row: dict[str, JsonValue],
        include_output: bool,
        include_logs: bool,
        include_artifacts: bool,
    ) -> TestRunRecord:
        config_raw = row.get("config", {})
        config = self._coerce_json_object(config_raw)

        command_raw = config.get("test_command") or config.get("command")
        command = command_raw if isinstance(command_raw, str) else None
        runner_raw = config.get("runner")
        runner = runner_raw if isinstance(runner_raw, str) else None
        plan_id_raw = config.get("plan_id")
        plan_id = plan_id_raw if isinstance(plan_id_raw, str) else None
        task_ids_raw = config.get("task_ids", [])
        task_ids = (
            tuple(str(task_id) for task_id in task_ids_raw)
            if isinstance(task_ids_raw, list)
            else ()
        )

        started_at = self._coerce_datetime(row.get("started_at"))
        finished_at = self._coerce_datetime(row.get("finished_at"))

        logs: JsonObject = {}
        if include_logs:
            logs_raw = row.get("logs", {})
            logs_data = self._coerce_json_object(logs_raw)
            logs = self._normalize_logs(logs_data, finished_at)

        artifacts: JsonObject = {}
        if include_artifacts:
            artifacts_raw = row.get("artifacts", {})
            artifacts_data = self._coerce_json_object(artifacts_raw)
            artifacts = self._normalize_artifacts(artifacts_data, finished_at)

        exit_code_raw = row.get("exit_code")
        exit_code = exit_code_raw if isinstance(exit_code_raw, int) else None

        duration_raw = row.get("duration_seconds")
        duration_seconds = (
            float(duration_raw) if isinstance(duration_raw, (int, float)) else None
        )

        stdout_raw = row.get("stdout")
        stdout = stdout_raw if include_output and isinstance(stdout_raw, str) else None
        stderr_raw = row.get("stderr")
        stderr = stderr_raw if include_output and isinstance(stderr_raw, str) else None

        project_id_raw = row.get("project_id")
        project_id = project_id_raw if isinstance(project_id_raw, str) else None

        return TestRunRecord(
            id=str(row["id"]),
            server_id=str(row["server_id"]),
            project_id=project_id,
            success=bool(row.get("success")),
            exit_code=exit_code,
            duration_seconds=duration_seconds,
            started_at=started_at,
            finished_at=finished_at,
            command=command,
            runner=runner,
            plan_id=plan_id,
            task_ids=task_ids,
            stdout=stdout,
            stderr=stderr,
            logs=logs,
            artifacts=artifacts,
            config=config,
        )

    def _normalize_logs(
        self, logs: JsonValue, captured_at: datetime | None
    ) -> JsonObject:
        if not isinstance(logs, dict):
            return {}
        normalized: JsonObject = {}
        captured_at_iso = captured_at.isoformat() if captured_at else None
        for path, entry in logs.items():
            if isinstance(entry, dict):
                normalized_entry: JsonObject = {
                    str(key): value for key, value in entry.items()
                }
                if (
                    "size_bytes" not in normalized_entry
                    and "content" in normalized_entry
                ):
                    content = str(normalized_entry.get("content") or "")
                    normalized_entry["size_bytes"] = len(
                        content.encode("utf-8", errors="replace")
                    )
                if "captured_at" not in normalized_entry and captured_at_iso:
                    normalized_entry["captured_at"] = captured_at_iso
                normalized[str(path)] = normalized_entry
                continue
            content = "" if entry is None else str(entry)
            log_entry: JsonObject = {
                "content": content,
                "size_bytes": len(content.encode("utf-8", errors="replace")),
            }
            if captured_at_iso:
                log_entry["captured_at"] = captured_at_iso
            normalized[str(path)] = log_entry
        return normalized

    def _normalize_artifacts(
        self, artifacts: JsonValue, captured_at: datetime | None
    ) -> JsonObject:
        if not isinstance(artifacts, dict):
            return {}
        normalized: JsonObject = {}
        captured_at_iso = captured_at.isoformat() if captured_at else None
        for path, entry in artifacts.items():
            if isinstance(entry, dict):
                normalized_entry: JsonObject = {
                    str(key): value for key, value in entry.items()
                }
                local_path = str(normalized_entry.get("local_path") or "")
                if local_path:
                    metadata = self._artifact_metadata(local_path)
                    for key, value in metadata.items():
                        if key not in normalized_entry:
                            normalized_entry[key] = value
                if "captured_at" not in normalized_entry and captured_at_iso:
                    normalized_entry["captured_at"] = captured_at_iso
                normalized[str(path)] = normalized_entry
                continue
            local_path = "" if entry is None else str(entry)
            artifact_entry: JsonObject = {"local_path": local_path}
            if local_path:
                artifact_entry.update(self._artifact_metadata(local_path))
            if captured_at_iso:
                artifact_entry["captured_at"] = captured_at_iso
            normalized[str(path)] = artifact_entry
        return normalized

    def _artifact_metadata(self, local_path: str) -> JsonObject:
        path_obj = Path(local_path)
        if not path_obj.exists():
            return {}
        stats = path_obj.stat()
        metadata: JsonObject = {
            "size_bytes": stats.st_size,
            "modified_at": datetime.fromtimestamp(stats.st_mtime, UTC).isoformat(),
        }
        created_ts = getattr(stats, "st_birthtime", None)
        if created_ts:
            metadata["created_at"] = datetime.fromtimestamp(created_ts, UTC).isoformat()
        return metadata

    def _coerce_json_object(self, raw: JsonValue) -> JsonObject:
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                return {}
            if isinstance(parsed, dict):
                normalized = self._coerce_json_value(parsed)
                if isinstance(normalized, dict):
                    return normalized
            return {}
        if isinstance(raw, dict):
            return raw
        return {}

    def _coerce_json_value(self, value: JsonValue) -> JsonValue:
        if isinstance(value, dict):
            return {
                str(key): self._coerce_json_value(item) for key, item in value.items()
            }
        if isinstance(value, list):
            return [self._coerce_json_value(item) for item in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)

    def _coerce_datetime(self, raw: JsonValue | None) -> datetime:
        if isinstance(raw, datetime):
            return raw
        if isinstance(raw, str):
            return datetime.fromisoformat(raw)
        raise ValueError(f"Invalid datetime value: {raw!r}")
