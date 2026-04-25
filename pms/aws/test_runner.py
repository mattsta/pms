"""TestRunner - Edit-sync-test cycle management."""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pms.aws.models import RemoteTestConfig, RemoteTestResult
from pms.core.events import (
    DomainEvent,
    EventMetadata,
    EventType,
    TestRunCompletedPayload,
    TestRunStartedPayload,
)
from pms.repositories.test_run_repository import TestRunRepository
from pms.services.task_evidence_service import TaskEvidenceService

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pms.aws.fleet_manager import FleetManager
    from pms.core.events import EventStore
    from pms.core.metrics import MetricsCollector
    from pms.db.connection import Database
    from pms.services.remote_service import RemoteService
    from pms.utils.rsync import SyncResult


class TestRunner:
    """Run tests on remote servers with sync support.

    Handles:
    - Syncing local project to remote server
    - Running test commands
    - Live output callbacks for interactive callers
    - Capturing logs and artifacts
    - Recording test results
    """

    def __init__(
        self,
        db: Database,
        event_store: EventStore,
        metrics: MetricsCollector,
        remote_service: RemoteService,
        fleet_manager: FleetManager,
    ) -> None:
        """Initialize TestRunner.

        Args:
            db: Database connection
            event_store: Event store for audit trail
            metrics: Metrics collector
            remote_service: Remote service for SSH/rsync
            fleet_manager: Fleet manager for server access
        """
        self.db = db
        self.events = event_store
        self.metrics = metrics
        self.remote = remote_service
        self.fleet = fleet_manager
        self._test_runs = TestRunRepository(db)
        self._evidence = TaskEvidenceService(db, metrics)

    async def sync_and_run(
        self,
        config: RemoteTestConfig,
        *,
        on_output_line: Callable[[str, str], Awaitable[None] | None] | None = None,
    ) -> RemoteTestResult:
        """Sync project and run tests.

        Args:
            config: Test run configuration

        Returns:
            RemoteTestResult with output and status

        Raises:
            RuntimeError: If server not found or sync fails
        """
        run_id = str(uuid.uuid4())
        started_at = datetime.now(UTC)

        # Get server
        server = await self.fleet.get_server(config.server_id)
        if server is None:
            raise RuntimeError(f"Server {config.server_id} not found")

        if not server.is_active:
            raise RuntimeError(
                f"Server {server.name} is not active (state: {server.state})"
            )

        host_name = f"aws-{server.name}"

        # Emit start event
        await self.events.append(
            DomainEvent(
                event_type=EventType.TEST_RUN_STARTED,
                aggregate_type="test_run",
                aggregate_id=run_id,
                payload=TestRunStartedPayload(
                    server_id=config.server_id,
                    command=config.test_command,
                    project_path=str(config.project_path),
                ),
                metadata=EventMetadata(source="test_runner"),
            )
        )

        # Record activity to reset idle timer
        await self.fleet.record_activity(config.server_id)

        # Sync project to remote
        sync_result = await self.remote.sync_push(
            identifier=host_name,
            local_path=config.project_path,
            remote_path=config.remote_path,
            exclude=list(config.exclude_patterns),
            delete=False,
        )

        if not sync_result.success:
            raise RuntimeError(f"Sync failed: {sync_result.stderr}")

        setup_failed = False

        # Run setup command if specified
        if config.setup_command:
            working_dir = config.working_dir or config.remote_path
            setup_cmd = f"cd {working_dir} && {config.setup_command}"

            # Set environment variables
            for key, value in config.env_vars:
                setup_cmd = f"export {key}='{value}' && {setup_cmd}"

            setup_result = await self._execute_remote_command(
                host_name,
                setup_cmd,
                timeout=config.timeout,
                stream_output=config.stream_output,
                on_output_line=on_output_line,
            )
            if not setup_result.success:
                stdout = setup_result.stdout
                stderr = f"Setup failed: {setup_result.stderr}"
                exit_code = setup_result.exit_code or 1
                setup_failed = True

        if not setup_failed:
            # Build test command
            working_dir = config.working_dir or config.remote_path
            test_cmd = f"cd {working_dir} && {config.test_command}"

            # Set environment variables
            for key, value in config.env_vars:
                test_cmd = f"export {key}='{value}' && {test_cmd}"

            cmd_result = await self._execute_remote_command(
                host_name,
                test_cmd,
                timeout=config.timeout,
                stream_output=config.stream_output,
                on_output_line=on_output_line,
            )
            stdout = cmd_result.stdout
            stderr = cmd_result.stderr
            exit_code = cmd_result.exit_code or 0

        finished_at = datetime.now(UTC)
        duration = (finished_at - started_at).total_seconds()
        success = exit_code == 0

        # Capture logs
        logs: dict[str, str] = {}
        for log_path in config.capture_logs:
            try:
                log_result = await self.remote.execute_command(
                    host_name,
                    f"cat {log_path}",
                    timeout=30,
                )
                if log_result.success:
                    logs[log_path] = log_result.stdout
            except Exception:
                pass

        # Download artifacts
        artifacts: dict[str, Path] = {}
        for artifact_path in config.save_artifacts:
            try:
                local_path = Path(
                    f"/tmp/pms-artifacts/{run_id}/{Path(artifact_path).name}"
                )
                local_path.parent.mkdir(parents=True, exist_ok=True)

                pull_result = await self.remote.sync_pull(
                    identifier=host_name,
                    remote_path=f"{config.remote_path}/{artifact_path}",
                    local_path=local_path.parent,
                )
                if pull_result.success:
                    artifacts[artifact_path] = local_path
            except Exception:
                pass

        # Create result
        result = RemoteTestResult(
            run_id=run_id,
            server_id=config.server_id,
            success=success,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=duration,
            started_at=started_at,
            finished_at=finished_at,
            logs=logs,
            artifacts=artifacts,
        )

        log_payload = self._build_log_payload(result.logs, finished_at)
        artifact_payload = self._build_artifact_payload(result.artifacts, finished_at)

        # Store result
        try:
            await self._store_result(result, config, log_payload, artifact_payload)
        except Exception:
            self._cleanup_downloaded_artifacts(result.artifacts)
            raise
        await self._attach_evidence(result, config, log_payload, artifact_payload)
        transition_result = await self._apply_workflow_transition(result, config)
        if transition_result is not None:
            result.workflow_transition = transition_result

        # Emit completion event
        await self.events.append(
            DomainEvent(
                event_type=EventType.TEST_RUN_COMPLETED,
                aggregate_type="test_run",
                aggregate_id=run_id,
                payload=TestRunCompletedPayload(
                    server_id=config.server_id,
                    success=success,
                    exit_code=exit_code,
                    duration_seconds=duration,
                    stdout_preview=stdout[:500] if stdout else "",
                    stderr_preview=stderr[:500] if stderr else "",
                ),
                metadata=EventMetadata(source="test_runner"),
            )
        )

        # Record metrics
        await self.metrics.record_counter(
            "aws.test_run",
            labels={"success": str(success)},
        )
        await self.metrics.record_timing(
            "aws.test_duration",
            duration * 1000,
            labels={"server_id": config.server_id},
        )
        await self.metrics.flush_best_effort(context="aws.test_runner.sync_and_run")

        # Update activity
        await self.fleet.record_activity(config.server_id)

        return result

    async def _execute_remote_command(
        self,
        host_name: str,
        command: str,
        *,
        timeout: float,
        stream_output: bool,
        on_output_line: Callable[[str, str], Awaitable[None] | None] | None,
    ):
        if stream_output and on_output_line is not None:
            return await self.remote.execute_command_and_stream(
                identifier=host_name,
                command=command,
                timeout=timeout,
                on_output=on_output_line,
            )
        return await self.remote.execute_command(
            identifier=host_name,
            command=command,
            timeout=timeout,
        )

    def _cleanup_downloaded_artifacts(self, artifacts: dict[str, Path]) -> None:
        """Delete downloaded local artifact paths when persistence never completed."""
        roots: set[Path] = set()
        for path in artifacts.values():
            with contextlib.suppress(OSError):
                if path.exists():
                    path.unlink()
            root = path.parent
            while root.name:
                roots.add(root)
                if root.name == "pms-artifacts":
                    break
                root = root.parent

        for root in sorted(roots, key=lambda item: len(item.parts), reverse=True):
            with contextlib.suppress(OSError):
                if root.exists():
                    root.rmdir()

    async def sync_only(
        self,
        server_id: str,
        project_path: Path,
        remote_path: str = "/home/ec2-user/project",
        exclude: list[str] | None = None,
    ) -> SyncResult:
        """Just sync project, don't run tests.

        Args:
            server_id: Server to sync to
            project_path: Local project path
            remote_path: Remote destination path
            exclude: Patterns to exclude

        Returns:
            SyncResult with operation details
        """
        server = await self.fleet.get_server(server_id)
        if server is None:
            raise RuntimeError(f"Server {server_id} not found")

        host_name = f"aws-{server.name}"

        default_exclude = [
            ".git",
            "__pycache__",
            "*.pyc",
            ".venv",
            "node_modules",
            ".pytest_cache",
            ".mypy_cache",
            "dist",
            "build",
        ]

        result = await self.remote.sync_push(
            identifier=host_name,
            local_path=project_path,
            remote_path=remote_path,
            exclude=exclude or default_exclude,
        )

        await self.fleet.record_activity(server_id)
        return result

    async def run_only(
        self,
        server_id: str,
        command: str,
        working_dir: str | None = None,
        timeout: float = 300.0,
    ) -> RemoteTestResult:
        """Run command without syncing.

        Args:
            server_id: Server to run on
            command: Command to run
            working_dir: Working directory (optional)
            timeout: Command timeout

        Returns:
            RemoteTestResult with output
        """
        run_id = str(uuid.uuid4())
        started_at = datetime.now(UTC)

        server = await self.fleet.get_server(server_id)
        if server is None:
            raise RuntimeError(f"Server {server_id} not found")

        host_name = f"aws-{server.name}"

        # Build command with working dir
        full_cmd = command
        if working_dir:
            full_cmd = f"cd {working_dir} && {command}"

        result = await self.remote.execute_command(
            identifier=host_name,
            command=full_cmd,
            timeout=timeout,
        )

        finished_at = datetime.now(UTC)

        await self.fleet.record_activity(server_id)

        return RemoteTestResult(
            run_id=run_id,
            server_id=server_id,
            success=result.success,
            exit_code=result.exit_code or 0,
            stdout=result.stdout,
            stderr=result.stderr,
            duration_seconds=result.duration_seconds,
            started_at=started_at,
            finished_at=finished_at,
        )

    async def tail_logs(
        self,
        server_id: str,
        log_paths: list[str],
        follow: bool = True,
        lines: int = 100,
    ) -> AsyncIterator[tuple[str, str]]:
        """Tail remote log files.

        Args:
            server_id: Server to tail logs from
            log_paths: List of log file paths
            follow: Follow logs in real-time
            lines: Number of initial lines to show

        Yields:
            Tuples of (log_path, line)
        """
        server = await self.fleet.get_server(server_id)
        if server is None:
            raise RuntimeError(f"Server {server_id} not found")

        host_name = f"aws-{server.name}"

        # Build tail command for all logs
        tail_opts = f"-n {lines}"
        if follow:
            tail_opts += " -f"

        # Use tail with multiple files
        paths_str = " ".join(log_paths)
        command = f"tail {tail_opts} {paths_str}"

        current_file = log_paths[0] if len(log_paths) == 1 else ""

        async for line in self.remote.execute_streaming(host_name, command):
            # Parse output to identify which file
            if line.startswith("==>") and line.endswith("<=="):
                # Header line like "==> /var/log/app.log <=="
                current_file = line[4:-4].strip()
            else:
                yield (current_file, line)

            # Record activity
            await self.fleet.record_activity(server_id)

    async def get_run_history(
        self,
        server_id: str | None = None,
        limit: int = 20,
    ) -> list[RemoteTestResult]:
        """Get recent test run history.

        Args:
            server_id: Filter by server (optional)
            limit: Maximum results to return

        Returns:
            List of RemoteTestResult objects
        """
        query = "SELECT * FROM test_runs WHERE 1=1"
        params: list[Any] = []

        if server_id:
            query += " AND server_id = ?"
            params.append(server_id)

        query += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)

        rows = await self.db.fetch_all(query, tuple(params))
        return [self._result_from_row(row) for row in rows]

    async def _store_result(
        self,
        result: RemoteTestResult,
        config: RemoteTestConfig,
        log_payload: dict[str, dict[str, Any]],
        artifact_payload: dict[str, dict[str, Any]],
    ) -> None:
        """Store test result in database."""
        config_payload = {
            "server_id": config.server_id,
            "project_path": str(config.project_path),
            "remote_path": config.remote_path,
            "test_command": config.test_command,
            "setup_command": config.setup_command,
            "working_dir": config.working_dir,
            "env_vars": list(config.env_vars),
            "timeout": config.timeout,
            "exclude_patterns": list(config.exclude_patterns),
            "stream_output": config.stream_output,
            "capture_logs": list(config.capture_logs),
            "save_artifacts": list(config.save_artifacts),
            "project_id": config.project_id,
            "plan_id": config.plan_id,
            "task_ids": list(config.task_ids),
            "transition_on_success": config.transition_on_success,
            "transition_on_failure": config.transition_on_failure,
            "transition_by": config.transition_by,
            "transition_reason": config.transition_reason,
            "runner": "aws",
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

    async def _attach_evidence(
        self,
        result: RemoteTestResult,
        config: RemoteTestConfig,
        log_payload: dict[str, dict[str, Any]],
        artifact_payload: dict[str, dict[str, Any]],
    ) -> None:
        if not config.task_ids:
            return
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
            created_by="aws_test_runner",
        )

    async def _apply_workflow_transition(
        self,
        result: RemoteTestResult,
        config: RemoteTestConfig,
    ):
        if not config.task_ids:
            return None

        from pms.services.test_run_workflow_service import (
            TestRunWorkflowService,
            TestRunWorkflowTransition,
        )

        transition = TestRunWorkflowTransition(
            on_success_state=config.transition_on_success,
            on_failure_state=config.transition_on_failure,
            triggered_by=config.transition_by or "aws_test_runner",
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

    def _build_log_payload(
        self,
        logs: dict[str, str],
        captured_at: datetime,
    ) -> dict[str, dict[str, Any]]:
        payload: dict[str, dict[str, Any]] = {}
        captured_at_iso = captured_at.isoformat()
        for path, content in logs.items():
            payload[path] = {
                "content": content,
                "size_bytes": self._content_size(content),
                "captured_at": captured_at_iso,
            }
        return payload

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
                stats = path.stat()
                entry["size_bytes"] = stats.st_size
                entry["modified_at"] = datetime.fromtimestamp(
                    stats.st_mtime, UTC
                ).isoformat()
                created_ts = getattr(stats, "st_birthtime", None)
                if created_ts:
                    entry["created_at"] = datetime.fromtimestamp(
                        created_ts, UTC
                    ).isoformat()
            payload[key] = entry
        return payload

    def _content_size(self, content: str) -> int:
        return len(content.encode("utf-8", errors="replace"))

    def _build_evidence_metadata(
        self,
        result: RemoteTestResult,
        config: RemoteTestConfig,
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
            "runner": "aws",
            "server_id": config.server_id,
            "command": config.test_command,
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

    def _result_from_row(self, row: dict[str, Any]) -> RemoteTestResult:
        """Convert database row to RemoteTestResult."""
        import json

        raw_logs = json.loads(row.get("logs", "{}"))
        logs: dict[str, str] = {}
        for path, entry in raw_logs.items():
            if isinstance(entry, dict):
                logs[path] = entry.get("content", "")
            else:
                logs[path] = str(entry)

        raw_artifacts = json.loads(row.get("artifacts", "{}"))
        artifacts: dict[str, Path] = {}
        for path, entry in raw_artifacts.items():
            local_path = entry.get("local_path") if isinstance(entry, dict) else entry
            if local_path:
                artifacts[path] = Path(local_path)

        return RemoteTestResult(
            run_id=row["id"],
            server_id=row["server_id"],
            success=bool(row["success"]),
            exit_code=row["exit_code"],
            stdout=row.get("stdout", ""),
            stderr=row.get("stderr", ""),
            duration_seconds=row["duration_seconds"],
            started_at=datetime.fromisoformat(row["started_at"]),
            finished_at=datetime.fromisoformat(row["finished_at"]),
            logs=logs,
            artifacts=artifacts,
        )
