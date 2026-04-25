"""Local test runner with evidence attachment."""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pms.core.events import (
    DomainEvent,
    EventMetadata,
    EventType,
    TestRunCompletedPayload,
    TestRunStartedPayload,
)
from pms.repositories.test_run_repository import TestRunRepository
from pms.services.task_evidence_service import TaskEvidenceService
from pms.services.test_server_service import TestServerService
from pms.testing.models import LocalTestConfig, LocalTestResult

if TYPE_CHECKING:
    from pms.core.events import EventStore
    from pms.core.metrics import MetricsCollector
    from pms.db.connection import Database


@dataclass(frozen=True)
class _CommandResult:
    success: bool
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float


class LocalTestRunner:
    """Run local tests and record results."""

    def __init__(
        self,
        db: Database,
        event_store: EventStore,
        metrics: MetricsCollector,
    ) -> None:
        self.db = db
        self.events = event_store
        self.metrics = metrics
        self._test_runs = TestRunRepository(db)
        self._evidence = TaskEvidenceService(db, metrics)

    async def run(self, config: LocalTestConfig) -> LocalTestResult:
        """Run a local test command and store results."""
        run_id = str(uuid.uuid4())
        started_at = datetime.now(UTC)

        project_path = config.project_path.resolve()
        if not project_path.exists():
            raise FileNotFoundError(f"Project path not found: {project_path}")

        workdir = (
            project_path / config.working_dir if config.working_dir else project_path
        )
        if not workdir.exists():
            raise FileNotFoundError(f"Working directory not found: {workdir}")

        server_id = await self._ensure_local_server(config.project_id)

        await self.events.append(
            DomainEvent(
                event_type=EventType.TEST_RUN_STARTED,
                aggregate_type="test_run",
                aggregate_id=run_id,
                payload=TestRunStartedPayload(
                    server_id=server_id,
                    command=config.test_command,
                    project_path=str(project_path),
                ),
                metadata=EventMetadata(source="local_test_runner"),
            )
        )

        env = os.environ.copy()
        env.update({k: v for k, v in config.env_vars})

        logs: dict[str, str] = {}
        artifacts: dict[str, Path] = {}

        setup_result = None
        if config.setup_command:
            setup_result = await self._run_command(
                config.setup_command,
                workdir,
                env,
                config.timeout,
            )
            logs["setup_stdout"] = setup_result.stdout
            logs["setup_stderr"] = setup_result.stderr
            logs["setup_exit_code"] = str(setup_result.exit_code)

        if setup_result is not None and not setup_result.success:
            test_result = setup_result
        else:
            test_result = await self._run_command(
                config.test_command,
                workdir,
                env,
                config.timeout,
            )

        logs.update(await self._capture_logs(config.capture_logs, project_path))
        artifacts.update(self._capture_artifacts(config.save_artifacts, project_path))

        finished_at = datetime.now(UTC)
        duration = (finished_at - started_at).total_seconds()

        result = LocalTestResult(
            run_id=run_id,
            server_id=server_id,
            success=test_result.success,
            exit_code=test_result.exit_code,
            stdout=test_result.stdout,
            stderr=test_result.stderr,
            duration_seconds=duration,
            started_at=started_at,
            finished_at=finished_at,
            logs=logs,
            artifacts=artifacts,
        )

        log_payload = self._build_log_payload(
            logs,
            project_path=project_path,
            captured_at=finished_at,
        )
        artifact_payload = self._build_artifact_payload(
            artifacts,
            captured_at=finished_at,
        )

        await self._store_result(result, config, log_payload, artifact_payload)

        if config.task_ids:
            metadata = self._build_evidence_metadata(
                result,
                config,
                log_payload,
                artifact_payload,
            )
            await self._evidence.add_test_run_evidence_batch(
                config.task_ids,
                result.run_id,
                metadata=metadata,
                created_by="local_test_runner",
            )
            transition_result = await self._apply_workflow_transition(result, config)
            if transition_result is not None:
                result.workflow_transition = transition_result

        await self.events.append(
            DomainEvent(
                event_type=EventType.TEST_RUN_COMPLETED,
                aggregate_type="test_run",
                aggregate_id=run_id,
                payload=TestRunCompletedPayload(
                    server_id=server_id,
                    success=result.success,
                    exit_code=result.exit_code,
                    duration_seconds=duration,
                    stdout_preview=result.stdout[:500] if result.stdout else "",
                    stderr_preview=result.stderr[:500] if result.stderr else "",
                ),
                metadata=EventMetadata(source="local_test_runner"),
            )
        )

        await self.metrics.record_counter(
            "local.test_run",
            labels={"success": str(result.success)},
        )
        await self.metrics.record_timing(
            "local.test_duration",
            duration * 1000,
            labels={"server_id": server_id},
        )
        await self.metrics.flush_best_effort(context="local_test_runner.run")

        return result

    async def _ensure_local_server(self, project_id: str | None) -> str:
        registration = await TestServerService(self.db).ensure_local_server(project_id)
        return registration.id

    async def _store_result(
        self,
        result: LocalTestResult,
        config: LocalTestConfig,
        log_payload: dict[str, dict[str, Any]],
        artifact_payload: dict[str, dict[str, Any]],
    ) -> None:
        config_payload = {
            "project_path": str(config.project_path),
            "test_command": config.test_command,
            "setup_command": config.setup_command,
            "working_dir": config.working_dir,
            "env_vars": list(config.env_vars),
            "timeout": config.timeout,
            "capture_logs": list(config.capture_logs),
            "save_artifacts": list(config.save_artifacts),
            "project_id": config.project_id,
            "plan_id": config.plan_id,
            "task_ids": list(config.task_ids),
            "transition_on_success": config.transition_on_success,
            "transition_on_failure": config.transition_on_failure,
            "transition_by": config.transition_by,
            "transition_reason": config.transition_reason,
            "runner": "local",
        }
        await self._test_runs.create(
            run_id=result.run_id,
            server_id=result.server_id,
            project_id=config.project_id,
            config=config_payload,
            success=result.success,
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            duration_seconds=result.duration_seconds,
            started_at=result.started_at.isoformat(),
            finished_at=result.finished_at.isoformat(),
            logs=log_payload,
            artifacts=artifact_payload,
        )

    async def _run_command(
        self,
        command: str,
        workdir: Path,
        env: dict[str, str],
        timeout: float,
    ) -> _CommandResult:
        started_at = datetime.now(UTC)
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=str(workdir),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )
            exit_code = process.returncode or 0
            success = exit_code == 0
        except TimeoutError:
            await self._terminate_process_group(process)
            stdout_bytes, stderr_bytes = await process.communicate()
            exit_code = -1
            success = False
            timeout_msg = f"Timed out after {timeout:.0f}s"
            stderr_bytes = (stderr_bytes or b"") + f"\n{timeout_msg}".encode()

        finished_at = datetime.now(UTC)
        duration = (finished_at - started_at).total_seconds()
        stdout = (stdout_bytes or b"").decode(errors="replace")
        stderr = (stderr_bytes or b"").decode(errors="replace")
        return _CommandResult(
            success=success,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=duration,
        )

    async def _terminate_process_group(
        self,
        process: asyncio.subprocess.Process,
        *,
        grace_seconds: float = 1.0,
    ) -> None:
        if process.returncode is not None:
            return

        if os.name == "nt" or not hasattr(os, "killpg"):
            process.kill()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(process.wait(), timeout=grace_seconds)
            return

        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGTERM)

        try:
            await asyncio.wait_for(process.wait(), timeout=grace_seconds)
            return
        except TimeoutError:
            pass

        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)

        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(process.wait(), timeout=grace_seconds)

    def _build_log_payload(
        self,
        logs: dict[str, str],
        project_path: Path,
        captured_at: datetime,
    ) -> dict[str, dict[str, Any]]:
        payload: dict[str, dict[str, Any]] = {}
        captured_at_iso = captured_at.isoformat()
        for key, content in logs.items():
            entry: dict[str, Any] = {
                "content": content,
                "size_bytes": self._content_size(content),
                "captured_at": captured_at_iso,
            }
            path = Path(key)
            if not path.is_absolute():
                path = project_path / path
            if path.exists():
                entry.update(self._file_metadata(path))
            payload[key] = entry
        return payload

    async def _apply_workflow_transition(
        self,
        result: LocalTestResult,
        config: LocalTestConfig,
    ):
        from pms.services.test_run_workflow_service import (
            TestRunWorkflowService,
            TestRunWorkflowTransition,
        )

        transition = TestRunWorkflowTransition(
            on_success_state=config.transition_on_success,
            on_failure_state=config.transition_on_failure,
            triggered_by=config.transition_by or "local_test_runner",
            reason=config.transition_reason,
        )
        if transition.target_state(result.success) is None:
            return None

        service = TestRunWorkflowService(self.db, self.metrics)
        return await service.apply(
            task_ids=config.task_ids,
            success=result.success,
            transition=transition,
            run_id=result.run_id,
        )

    def _build_artifact_payload(
        self,
        artifacts: dict[str, Path],
        captured_at: datetime,
    ) -> dict[str, dict[str, Any]]:
        payload: dict[str, dict[str, Any]] = {}
        captured_at_iso = captured_at.isoformat()
        for key, path in artifacts.items():
            entry: dict[str, Any] = {
                "local_path": str(path),
                "captured_at": captured_at_iso,
            }
            if path.exists():
                entry.update(self._file_metadata(path))
            payload[key] = entry
        return payload

    def _file_metadata(self, path: Path) -> dict[str, Any]:
        stats = path.stat()
        metadata: dict[str, Any] = {
            "size_bytes": stats.st_size,
            "modified_at": datetime.fromtimestamp(stats.st_mtime, UTC).isoformat(),
        }
        created_ts = getattr(stats, "st_birthtime", None)
        if created_ts:
            metadata["created_at"] = datetime.fromtimestamp(created_ts, UTC).isoformat()
        return metadata

    def _content_size(self, content: str) -> int:
        return len(content.encode("utf-8", errors="replace"))

    def _build_evidence_metadata(
        self,
        result: LocalTestResult,
        config: LocalTestConfig,
        log_payload: dict[str, dict[str, Any]],
        artifact_payload: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        log_meta = {
            path: {k: v for k, v in meta.items() if k != "content"}
            for path, meta in log_payload.items()
        }
        log_bytes_total = sum(
            int(meta.get("size_bytes", 0)) for meta in log_meta.values()
        )
        artifact_bytes_total = sum(
            int(meta.get("size_bytes", 0)) for meta in artifact_payload.values()
        )
        return {
            "runner": "local",
            "command": config.test_command,
            "server_id": result.server_id,
            "success": result.success,
            "exit_code": result.exit_code,
            "stdout_preview": (result.stdout or "")[:500],
            "stderr_preview": (result.stderr or "")[:500],
            "stdout_bytes": self._content_size(result.stdout or ""),
            "stderr_bytes": self._content_size(result.stderr or ""),
            "logs": log_meta,
            "artifacts": artifact_payload,
            "log_bytes_total": log_bytes_total,
            "artifact_bytes_total": artifact_bytes_total,
            "run_started_at": result.started_at.isoformat(),
            "run_finished_at": result.finished_at.isoformat(),
        }

    async def _capture_logs(
        self,
        log_paths: tuple[str, ...],
        project_path: Path,
    ) -> dict[str, str]:
        logs: dict[str, str] = {}
        for log_path in log_paths:
            path = Path(log_path)
            if not path.is_absolute():
                path = project_path / path
            if not path.exists():
                continue
            try:
                logs[str(path)] = path.read_text(errors="replace")
            except OSError:
                continue
        return logs

    def _capture_artifacts(
        self,
        artifact_paths: tuple[str, ...],
        project_path: Path,
    ) -> dict[str, Path]:
        artifacts: dict[str, Path] = {}
        for artifact_path in artifact_paths:
            path = Path(artifact_path)
            if not path.is_absolute():
                path = project_path / path
            if not path.exists():
                continue
            artifacts[str(path)] = path
        return artifacts
