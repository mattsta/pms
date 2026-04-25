"""Repository for plan-linked test jobs."""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pms.core.events import DomainEvent, EventStore, EventType
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.models.plan_test_job import PlanTestJob
from pms.repositories.base import EventSourcedRepository, QueryResult

if TYPE_CHECKING:
    from pms.db.connection import Database

PlanTestJobEvents = list[DomainEvent[dict[str, Any]]]


class PlanTestJobRepository(EventSourcedRepository[PlanTestJob]):
    """Repository for plan-linked test job configurations."""

    def __init__(self, db: Database) -> None:
        super().__init__(
            db,
            EventStore(db),
            RevisionStore(db),
            MetricsCollector(db),
        )

    @property
    def entity_type(self) -> str:
        return "plan_test_job"

    @property
    def table_name(self) -> str:
        return "plan_test_jobs"

    @property
    def archive_column(self) -> str | None:
        return "archived_at"

    async def _hydrate_task_links(self, jobs: list[PlanTestJob]) -> None:
        if not jobs:
            return

        ids = [job.id for job in jobs]
        placeholders = ", ".join("?" for _ in ids)
        rows = await self.db.fetch_all(
            f"""
            SELECT plan_test_job_id, task_id
            FROM plan_test_job_tasks
            WHERE plan_test_job_id IN ({placeholders})
            ORDER BY plan_test_job_id ASC, position ASC
            """,
            tuple(ids),
        )

        if not rows:
            return

        task_map: dict[str, list[str]] = {job.id: [] for job in jobs}
        for row in rows:
            task_map.setdefault(str(row["plan_test_job_id"]), []).append(
                str(row["task_id"])
            )

        for job in jobs:
            if task_map.get(job.id):
                job.task_ids = tuple(task_map[job.id])

    async def _sync_task_links(self, job: PlanTestJob) -> None:
        await self.db.execute(
            "DELETE FROM plan_test_job_tasks WHERE plan_test_job_id = ?",
            (job.id,),
        )
        if not job.task_ids:
            return
        await self.db.execute_many(
            """
            INSERT INTO plan_test_job_tasks (plan_test_job_id, task_id, position)
            VALUES (?, ?, ?)
            """,
            [
                (job.id, task_id, position)
                for position, task_id in enumerate(job.task_ids)
            ],
        )

    async def _update_projection(self, model: PlanTestJob, is_create: bool) -> None:
        await super()._update_projection(model, is_create)
        await self._sync_task_links(model)

    async def create(
        self,
        plan_id: str,
        name: str,
        mode: str,
        project_path: str,
        description: str | None = None,
        test_command: str = "pytest",
        setup_command: str | None = None,
        working_dir: str | None = None,
        env_vars: tuple[tuple[str, str], ...] = (),
        timeout: float = 600.0,
        capture_logs: tuple[str, ...] = (),
        save_artifacts: tuple[str, ...] = (),
        task_ids: tuple[str, ...] = (),
        transition_on_success: str | None = None,
        transition_on_failure: str | None = None,
        transition_by: str | None = None,
        transition_reason: str | None = None,
        project_id: str | None = None,
        server_id: str | None = None,
        server_name: str | None = None,
        remote_path: str = "/home/ec2-user/project",
        exclude_patterns: tuple[str, ...] | None = None,
        stream_output: bool = False,
    ) -> PlanTestJob:
        job = PlanTestJob(
            plan_id=plan_id,
            name=name,
            description=description,
            mode=mode,
            project_path=project_path,
            test_command=test_command,
            setup_command=setup_command,
            working_dir=working_dir,
            env_vars=env_vars,
            timeout=timeout,
            capture_logs=capture_logs,
            save_artifacts=save_artifacts,
            task_ids=task_ids,
            transition_on_success=transition_on_success,
            transition_on_failure=transition_on_failure,
            transition_by=transition_by,
            transition_reason=transition_reason,
            project_id=project_id,
            server_id=server_id,
            server_name=server_name,
            remote_path=remote_path,
            exclude_patterns=exclude_patterns,
            stream_output=stream_output,
        )

        payload = job.to_dict()

        return await self.save(
            job,
            EventType.PLAN_TEST_JOB_CREATED,
            payload,
            message=f"Created plan test job '{name}'",
        )

    async def update(
        self,
        job_id: str,
        plan_id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        mode: str | None = None,
        project_path: str | None = None,
        test_command: str | None = None,
        setup_command: str | None = None,
        working_dir: str | None = None,
        env_vars: tuple[tuple[str, str], ...] | None = None,
        timeout: float | None = None,
        capture_logs: tuple[str, ...] | None = None,
        save_artifacts: tuple[str, ...] | None = None,
        task_ids: tuple[str, ...] | None = None,
        transition_on_success: str | None = None,
        transition_on_failure: str | None = None,
        transition_by: str | None = None,
        transition_reason: str | None = None,
        project_id: str | None = None,
        server_id: str | None = None,
        server_name: str | None = None,
        remote_path: str | None = None,
        exclude_patterns: tuple[str, ...] | None = None,
        stream_output: bool | None = None,
    ) -> PlanTestJob | None:
        existing = await self.get_by_id(job_id)
        if existing is None:
            return None

        updated = PlanTestJob(
            id=existing.id,
            created_at=existing.created_at,
            updated_at=existing.updated_at,
            plan_id=plan_id if plan_id is not None else existing.plan_id,
            name=name if name is not None else existing.name,
            description=description
            if description is not None
            else existing.description,
            mode=mode if mode is not None else existing.mode,
            project_path=project_path
            if project_path is not None
            else existing.project_path,
            test_command=test_command
            if test_command is not None
            else existing.test_command,
            setup_command=setup_command
            if setup_command is not None
            else existing.setup_command,
            working_dir=working_dir
            if working_dir is not None
            else existing.working_dir,
            env_vars=env_vars if env_vars is not None else existing.env_vars,
            timeout=timeout if timeout is not None else existing.timeout,
            capture_logs=capture_logs
            if capture_logs is not None
            else existing.capture_logs,
            save_artifacts=save_artifacts
            if save_artifacts is not None
            else existing.save_artifacts,
            task_ids=task_ids if task_ids is not None else existing.task_ids,
            transition_on_success=(
                transition_on_success
                if transition_on_success is not None
                else existing.transition_on_success
            ),
            transition_on_failure=(
                transition_on_failure
                if transition_on_failure is not None
                else existing.transition_on_failure
            ),
            transition_by=transition_by
            if transition_by is not None
            else existing.transition_by,
            transition_reason=(
                transition_reason
                if transition_reason is not None
                else existing.transition_reason
            ),
            project_id=project_id if project_id is not None else existing.project_id,
            server_id=server_id if server_id is not None else existing.server_id,
            server_name=server_name
            if server_name is not None
            else existing.server_name,
            remote_path=remote_path
            if remote_path is not None
            else existing.remote_path,
            exclude_patterns=(
                exclude_patterns
                if exclude_patterns is not None
                else existing.exclude_patterns
            ),
            stream_output=(
                stream_output if stream_output is not None else existing.stream_output
            ),
        )
        updated.touch()
        changes: dict[str, Any] = {}
        fields = [
            "plan_id",
            "name",
            "description",
            "mode",
            "project_path",
            "test_command",
            "setup_command",
            "working_dir",
            "env_vars",
            "timeout",
            "capture_logs",
            "save_artifacts",
            "task_ids",
            "transition_on_success",
            "transition_on_failure",
            "transition_by",
            "transition_reason",
            "project_id",
            "server_id",
            "server_name",
            "remote_path",
            "exclude_patterns",
            "stream_output",
        ]
        for field in fields:
            old_val = getattr(existing, field)
            new_val = getattr(updated, field)
            if old_val != new_val:
                changes[field] = (old_val, new_val)

        if not changes:
            return existing

        return await self.save(
            updated,
            EventType.PLAN_TEST_JOB_UPDATED,
            {"changes": changes},
            message="Updated plan test job",
        )

    async def delete(
        self,
        job_id: str,
        soft_delete: bool = True,
        message: str | None = None,
    ) -> bool:
        return await super().delete(
            job_id,
            soft_delete=soft_delete,
            message=message or "Deleted plan test job",
        )

    async def get_by_id(self, job_id: str) -> PlanTestJob | None:
        row = await self.db.fetch_one(
            "SELECT * FROM plan_test_jobs WHERE id = ? AND archived_at IS NULL",
            (job_id,),
        )
        if row is None:
            return None
        job = self._row_to_model(row)
        await self._hydrate_task_links([job])
        return job

    async def list(
        self,
        plan_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
        *,
        include_archived: bool = False,
    ) -> QueryResult[PlanTestJob]:
        where_clauses = []
        params: list[Any] = []

        if plan_id:
            where_clauses.append("plan_id = ?")
            params.append(plan_id)

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        if not include_archived:
            where_sql = f"{where_sql} AND archived_at IS NULL"

        count_row = await self.db.fetch_one(
            f"SELECT COUNT(*) as count FROM plan_test_jobs WHERE {where_sql}",
            tuple(params),
        )
        total = count_row["count"] if count_row else 0

        rows = await self.db.fetch_all(
            f"""
            SELECT * FROM plan_test_jobs
            WHERE {where_sql}
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        )

        jobs = [self._row_to_model(row) for row in rows]
        await self._hydrate_task_links(jobs)

        return QueryResult(
            items=jobs,
            total_count=total,
            offset=offset,
            limit=limit,
        )

    def _model_from_row(self, row: dict[str, Any]) -> PlanTestJob:
        return self._row_to_model(row)

    def _row_from_model(self, model: PlanTestJob) -> dict[str, Any]:
        return {
            "id": model.id,
            "plan_id": model.plan_id,
            "name": model.name,
            "description": model.description,
            "mode": model.mode,
            "project_path": model.project_path,
            "test_command": model.test_command,
            "setup_command": model.setup_command,
            "working_dir": model.working_dir,
            "env_vars": json.dumps([list(pair) for pair in model.env_vars]),
            "timeout": model.timeout,
            "capture_logs": json.dumps(list(model.capture_logs)),
            "save_artifacts": json.dumps(list(model.save_artifacts)),
            "transition_on_success": model.transition_on_success,
            "transition_on_failure": model.transition_on_failure,
            "transition_by": model.transition_by,
            "transition_reason": model.transition_reason,
            "project_id": model.project_id,
            "server_id": model.server_id,
            "server_name": model.server_name,
            "remote_path": model.remote_path,
            "exclude_patterns": json.dumps(list(model.exclude_patterns))
            if model.exclude_patterns is not None
            else None,
            "stream_output": 1 if model.stream_output else 0,
            "created_at": model.created_at.isoformat(),
            "updated_at": model.updated_at.isoformat(),
            "archived_at": model.archived_at.isoformat() if model.archived_at else None,
            "last_event_sequence": model.last_event_sequence,
            "last_revision_number": model.last_revision_number,
        }

    async def _apply_events(self, events: PlanTestJobEvents) -> PlanTestJob | None:
        if not events:
            return None

        job: PlanTestJob | None = None
        for event in events:
            match event.event_type:
                case EventType.PLAN_TEST_JOB_CREATED:
                    payload = dict(event.payload)
                    payload["id"] = event.aggregate_id
                    job = PlanTestJob.from_dict(payload)
                case EventType.PLAN_TEST_JOB_UPDATED if job:
                    changes = event.payload.get("changes", {})
                    for field, (old_val, new_val) in changes.items():
                        if hasattr(job, field):
                            setattr(job, field, new_val)
                case EventType.PLAN_TEST_JOB_DELETED:
                    job = None
                case EventType.PLAN_TEST_JOB_RESTORED:
                    payload = event.payload
                    content = payload.get("content") or {}
                    content.setdefault("id", event.aggregate_id)
                    job = PlanTestJob.from_dict(content)

        return job

    def _row_to_model(self, row: dict[str, Any]) -> PlanTestJob:
        env_vars = self._parse_pairs(row.get("env_vars"))
        capture_logs = self._parse_list(row.get("capture_logs")) or ()
        save_artifacts = self._parse_list(row.get("save_artifacts")) or ()
        task_ids = self._parse_list(row.get("task_ids")) or ()
        exclude_patterns = self._parse_list(
            row.get("exclude_patterns"), allow_none=True
        )

        return PlanTestJob(
            id=row["id"],
            plan_id=row["plan_id"],
            name=row["name"],
            description=row.get("description"),
            mode=row.get("mode", "local"),
            project_path=row.get("project_path", "."),
            test_command=row.get("test_command", "pytest"),
            setup_command=row.get("setup_command"),
            working_dir=row.get("working_dir"),
            env_vars=env_vars,
            timeout=row.get("timeout", 600.0),
            capture_logs=capture_logs,
            save_artifacts=save_artifacts,
            task_ids=task_ids,
            transition_on_success=row.get("transition_on_success"),
            transition_on_failure=row.get("transition_on_failure"),
            transition_by=row.get("transition_by"),
            transition_reason=row.get("transition_reason"),
            project_id=row.get("project_id"),
            server_id=row.get("server_id"),
            server_name=row.get("server_name"),
            remote_path=row.get("remote_path") or "/home/ec2-user/project",
            exclude_patterns=exclude_patterns,
            stream_output=bool(row.get("stream_output", 0)),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            archived_at=datetime.fromisoformat(row["archived_at"])
            if row.get("archived_at")
            else None,
            last_event_sequence=row.get("last_event_sequence", 0),
            last_revision_number=row.get("last_revision_number", 0),
        )

    def _parse_pairs(self, value: Any) -> tuple[tuple[str, str], ...]:
        data = self._parse_json(value, default=[])
        if isinstance(data, dict):
            return tuple((str(k), str(v)) for k, v in data.items())
        if isinstance(data, list):
            pairs: list[tuple[str, str]] = []
            for item in data:
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    pairs.append((str(item[0]), str(item[1])))
            return tuple(pairs)
        return ()

    def _parse_list(
        self, value: Any, *, allow_none: bool = False
    ) -> tuple[str, ...] | None:
        if value is None and allow_none:
            return None
        data = self._parse_json(value, default=[])
        if isinstance(data, list):
            return tuple(str(item) for item in data)
        return () if not allow_none else None

    def _parse_json(self, value: Any, default: Any) -> Any:
        if value is None:
            return default
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return default
        return value
