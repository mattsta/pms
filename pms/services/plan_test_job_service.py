"""Service for plan-linked test job operations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pms.repositories.plan_repository import PlanRepository
from pms.repositories.plan_test_job_repository import PlanTestJobRepository
from pms.services.test_execution_service import (
    TestExecutionConfig,
    TestExecutionService,
)
from pms.testing.local_runner import LocalTestRunner

if TYPE_CHECKING:
    from pms.aws.models import RemoteTestResult
    from pms.core.events import EventStore
    from pms.core.metrics import MetricsCollector
    from pms.core.revisions import RevisionStore
    from pms.db.connection import Database
    from pms.models.plan_test_job import PlanTestJob
    from pms.repositories.base import QueryResult
    from pms.testing.models import LocalTestResult


PlanTestJobMode = Literal["local", "aws"]
PLAN_TEST_JOB_STREAM_OUTPUT_MESSAGE = (
    "stream_output is not supported for persisted plan test jobs. "
    "Use `pms aws test run` for live console output, and read stdout/stderr from "
    "the resulting test run after completion."
)


@dataclass(frozen=True)
class PlanTestJobRun:
    """Result of running a plan test job."""

    job: PlanTestJob
    result: LocalTestResult | RemoteTestResult


class PlanTestJobService:
    """Service layer for plan test jobs."""

    __test__ = False

    def __init__(
        self,
        db: Database,
        event_store: EventStore,
        revision_store: RevisionStore,
        metrics: MetricsCollector,
    ) -> None:
        self.db = db
        self.events = event_store
        self.revisions = revision_store
        self.metrics = metrics
        self._plan_repo = PlanRepository(db, event_store, revision_store, metrics)
        self._repo = PlanTestJobRepository(db)

    async def create_job(
        self,
        plan_id: str,
        name: str,
        mode: PlanTestJobMode,
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
        await self._require_plan(plan_id)
        self._validate_mode(mode)
        self._validate_stream_output(stream_output)

        async with self.db.transaction():
            job = await self._repo.create(
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

            await self.metrics.record_counter("plan_test_job.created")
            await self.metrics.flush()
        return job

    async def update_job(
        self,
        job_id: str,
        plan_id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        mode: PlanTestJobMode | None = None,
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
        if plan_id is not None:
            await self._require_plan(plan_id)
        if mode is not None:
            self._validate_mode(mode)
        self._validate_stream_output(stream_output)

        async with self.db.transaction():
            job = await self._repo.update(
                job_id=job_id,
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

            if job is not None:
                await self.metrics.record_counter("plan_test_job.updated")
                await self.metrics.flush()
        return job

    async def delete_job(self, job_id: str) -> bool:
        async with self.db.transaction():
            deleted = await self._repo.delete(job_id)
            if deleted:
                await self.metrics.record_counter("plan_test_job.deleted")
                await self.metrics.flush()
        return deleted

    async def restore_job(self, job_id: str) -> PlanTestJob | None:
        async with self.db.transaction():
            restored = await self._repo.restore(job_id)
            if restored:
                await self.metrics.record_counter("plan_test_job.restored")
                await self.metrics.flush()
        return restored

    async def get_job(self, job_id: str) -> PlanTestJob | None:
        job = await self._repo.get_by_id(job_id)
        if job is not None:
            await self.metrics.record_counter("plan_test_job.viewed")
            await self.metrics.flush_best_effort(context="plan_test_job.get_job")
        return job

    async def list_jobs(
        self,
        plan_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
        *,
        include_archived: bool = False,
    ) -> QueryResult[PlanTestJob]:
        result = await self._repo.list(
            plan_id=plan_id,
            limit=limit,
            offset=offset,
            include_archived=include_archived,
        )
        await self.metrics.record_counter("plan_test_job.listed")
        await self.metrics.flush_best_effort(context="plan_test_job.list_jobs")
        return result

    async def run_job(self, job_id: str) -> PlanTestJobRun | None:
        job = await self._repo.get_by_id(job_id)
        if job is None:
            return None

        plan = await self._plan_repo.get_by_id(job.plan_id)
        if plan is None:
            raise ValueError("Plan not found")

        task_ids = job.task_ids or plan.task_ids
        project_id = job.project_id or plan.project_id

        execution = await self._build_execution(job.mode)
        config = TestExecutionConfig(
            mode=job.mode,
            project_path=Path(job.project_path),
            test_command=job.test_command,
            setup_command=job.setup_command,
            working_dir=job.working_dir,
            env_vars=job.env_vars,
            timeout=job.timeout,
            capture_logs=job.capture_logs,
            save_artifacts=job.save_artifacts,
            project_id=project_id,
            plan_id=plan.id,
            task_ids=task_ids,
            transition_on_success=job.transition_on_success,
            transition_on_failure=job.transition_on_failure,
            transition_by=job.transition_by,
            transition_reason=job.transition_reason,
            server_id=job.server_id,
            server_name=job.server_name,
            remote_path=job.remote_path,
            exclude_patterns=job.exclude_patterns,
            # Persisted plan jobs have no live caller sink, so deprecated
            # historical stream_output values are intentionally ignored here.
            stream_output=False,
        )

        result = await execution.run(config)
        await self.metrics.record_counter(
            "plan_test_job.run",
            labels={"mode": job.mode, "success": str(result.success)},
        )
        await self.metrics.flush_best_effort(context="plan_test_job.run_job")
        return PlanTestJobRun(job=job, result=result)

    async def _require_plan(self, plan_id: str) -> None:
        plan = await self._plan_repo.get_by_id(plan_id)
        if plan is None:
            raise ValueError("Plan not found")

    def _validate_mode(self, mode: str) -> None:
        match mode:
            case "local" | "aws":
                return
            case _:
                raise ValueError("Unsupported job mode")

    def _validate_stream_output(self, stream_output: bool | None) -> None:
        if stream_output:
            raise ValueError(PLAN_TEST_JOB_STREAM_OUTPUT_MESSAGE)

    async def _build_execution(self, mode: str) -> TestExecutionService:
        match mode:
            case "local":
                runner = LocalTestRunner(
                    db=self.db,
                    event_store=self.events,
                    metrics=self.metrics,
                )
                return TestExecutionService(local_runner=runner)
            case "aws":
                try:
                    import boto3
                except ImportError as exc:
                    raise RuntimeError(
                        "AWS support requires boto3. Install with: pip install pms[aws]"
                    ) from exc

                from pms.aws import FleetManager, TestRunner
                from pms.services import RemoteService

                remote_service = RemoteService(
                    self.db,
                    self.events,
                    self.revisions,
                    self.metrics,
                )

                session = boto3.Session()
                ec2_client = session.client("ec2", region_name="us-east-1")

                fleet = FleetManager(
                    db=self.db,
                    event_store=self.events,
                    metrics=self.metrics,
                    remote_service=remote_service,
                    ec2_client=ec2_client,
                    region="us-east-1",
                )

                runner = TestRunner(
                    db=self.db,
                    event_store=self.events,
                    metrics=self.metrics,
                    remote_service=remote_service,
                    fleet_manager=fleet,
                )
                return TestExecutionService(remote_runner=runner)
            case _:
                raise ValueError("Unsupported job mode")
