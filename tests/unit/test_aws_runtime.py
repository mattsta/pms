"""Unit tests for AWS orchestration telemetry behavior."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from pms.aws.fleet_manager import FleetManager
from pms.aws.models import RemoteTestConfig, ServerState, SpotServer, SpotServerConfig
from pms.aws.test_runner import TestRunner as AwsTestRunner
from pms.core.events import EventType
from pms.repositories.test_run_repository import TestRunRepository


async def _ensure_test_server(db, server: SpotServer) -> None:
    row = await db.fetch_one(
        "SELECT id FROM test_servers WHERE id = ?",
        (server.id,),
    )
    if row:
        return
    await db.execute(
        """
        INSERT INTO test_servers (
            id, name, config, state, region,
            availability_zone, hourly_price, estimated_cost, launched_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            server.id,
            server.name,
            '{"kind": "aws"}',
            "running",
            server.region,
            server.availability_zone,
            float(server.hourly_price),
            float(server.estimated_cost),
            server.launched_at.isoformat(),
        ),
    )
    await db.commit()


@pytest.mark.asyncio
async def test_fleet_launch_ignores_observational_metrics_flush_failures(
    db,
    metrics_collector,
    temp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeEC2:
        def run_instances(self, **_kwargs):
            return {"Instances": [{"InstanceId": "i-launch-1"}]}

        def describe_spot_price_history(self, **_kwargs):
            return {"SpotPriceHistory": [{"SpotPrice": "0.0125"}]}

    event_store = SimpleNamespace(append=AsyncMock())
    remote_service = SimpleNamespace(add_host=AsyncMock())
    fleet = FleetManager(
        db=db,
        event_store=event_store,
        metrics=metrics_collector,
        remote_service=remote_service,
        ec2_client=FakeEC2(),
        region="us-east-1",
        key_dir=temp_dir / "keys",
    )

    monkeypatch.setattr(
        fleet, "_get_availability_zones", AsyncMock(return_value=["us-east-1a"])
    )
    monkeypatch.setattr(
        fleet, "_ensure_key_pair", AsyncMock(return_value=temp_dir / "keys" / "x.pem")
    )
    monkeypatch.setattr(
        fleet, "_ensure_default_security_group", AsyncMock(return_value="sg-123")
    )
    monkeypatch.setattr(fleet, "_store_server", AsyncMock())

    async def fail_flush(*args, **kwargs):
        raise RuntimeError("metrics flush failed")

    monkeypatch.setattr(metrics_collector, "flush", fail_flush)

    server = await fleet.launch_server(
        SpotServerConfig(name="launch-metrics", instance_type="t3.medium"),
        wait_for_ready=False,
    )

    assert server.instance_id == "i-launch-1"
    assert server.name == "launch-metrics"
    assert server.id in fleet._servers


@pytest.mark.asyncio
async def test_fleet_terminate_ignores_observational_metrics_flush_failures(
    db,
    metrics_collector,
    temp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeEC2:
        def terminate_instances(self, **_kwargs):
            return {"TerminatingInstances": [{"InstanceId": "i-term-1"}]}

    event_store = SimpleNamespace(append=AsyncMock())
    remote_service = SimpleNamespace(delete_host=AsyncMock())
    fleet = FleetManager(
        db=db,
        event_store=event_store,
        metrics=metrics_collector,
        remote_service=remote_service,
        ec2_client=FakeEC2(),
        region="us-east-1",
        key_dir=temp_dir / "keys",
    )

    server = SpotServer(
        id="srv-term-1",
        instance_id="i-term-1",
        name="term-metrics",
        config=SpotServerConfig(name="term-metrics", instance_type="t3.medium"),
        state=ServerState.RUNNING,
        launched_at=datetime.now(UTC),
        region="us-east-1",
        availability_zone="us-east-1a",
        hourly_price=Decimal("0.01"),
    )

    monkeypatch.setattr(fleet, "get_server", AsyncMock(return_value=server))
    monkeypatch.setattr(fleet, "_update_server", AsyncMock())

    async def fail_flush(*args, **kwargs):
        raise RuntimeError("metrics flush failed")

    monkeypatch.setattr(metrics_collector, "flush", fail_flush)

    terminated = await fleet.terminate_server(server.id, reason="test")

    assert terminated is True
    assert server.state == ServerState.TERMINATED
    remote_service.delete_host.assert_awaited_once_with("aws-term-metrics")


@pytest.mark.asyncio
async def test_aws_test_runner_sync_and_run_ignores_observational_metrics_flush_failures(
    db,
    event_store,
    metrics_collector,
    temp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = SpotServer(
        id="srv-run-1",
        instance_id="i-run-1",
        name="runner-metrics",
        config=SpotServerConfig(name="runner-metrics", instance_type="t3.medium"),
        state=ServerState.RUNNING,
        launched_at=datetime.now(UTC),
        region="us-east-1",
        availability_zone="us-east-1a",
        public_ip="127.0.0.1",
    )

    fleet = SimpleNamespace(
        get_server=AsyncMock(return_value=server),
        record_activity=AsyncMock(),
    )
    remote = SimpleNamespace(
        sync_push=AsyncMock(
            return_value=SimpleNamespace(
                success=True,
                stderr="",
                stdout="",
                files_transferred=1,
                duration_seconds=0.1,
            )
        ),
        execute_command=AsyncMock(
            return_value=SimpleNamespace(
                success=True,
                stdout="ok",
                stderr="",
                exit_code=0,
                duration_seconds=0.1,
            )
        ),
        execute_streaming=AsyncMock(),
    )
    runner = AwsTestRunner(
        db=db,
        event_store=event_store,
        metrics=metrics_collector,
        remote_service=remote,
        fleet_manager=fleet,
    )

    monkeypatch.setattr(runner, "_store_result", AsyncMock())
    monkeypatch.setattr(runner, "_attach_evidence", AsyncMock())
    monkeypatch.setattr(
        runner, "_apply_workflow_transition", AsyncMock(return_value=None)
    )

    async def fail_flush(*args, **kwargs):
        raise RuntimeError("metrics flush failed")

    monkeypatch.setattr(metrics_collector, "flush", fail_flush)

    result = await runner.sync_and_run(
        RemoteTestConfig(
            server_id=server.id,
            project_path=temp_dir,
            test_command="pytest",
            stream_output=False,
        )
    )

    assert result.success is True
    assert result.stdout == "ok"
    assert result.server_id == server.id
    runner._store_result.assert_awaited_once()
    fleet.record_activity.assert_awaited()


@pytest.mark.asyncio
async def test_aws_test_runner_sync_and_run_records_setup_failures(
    db,
    event_store,
    metrics_collector,
    temp_dir: Path,
) -> None:
    server = SpotServer(
        id="srv-setup-fail-1",
        instance_id="i-setup-fail-1",
        name="runner-setup-fail",
        config=SpotServerConfig(name="runner-setup-fail", instance_type="t3.medium"),
        state=ServerState.RUNNING,
        launched_at=datetime.now(UTC),
        region="us-east-1",
        availability_zone="us-east-1a",
        public_ip="127.0.0.1",
    )
    await _ensure_test_server(db, server)

    fleet = SimpleNamespace(
        get_server=AsyncMock(return_value=server),
        record_activity=AsyncMock(),
    )
    remote = SimpleNamespace(
        sync_push=AsyncMock(
            return_value=SimpleNamespace(
                success=True,
                stderr="",
                stdout="",
                files_transferred=1,
                duration_seconds=0.1,
            )
        ),
        execute_command=AsyncMock(
            return_value=SimpleNamespace(
                success=False,
                stdout="setup-out",
                stderr="setup-err",
                exit_code=7,
                duration_seconds=0.2,
            )
        ),
        execute_streaming=AsyncMock(),
        sync_pull=AsyncMock(),
    )
    runner = AwsTestRunner(
        db=db,
        event_store=event_store,
        metrics=metrics_collector,
        remote_service=remote,
        fleet_manager=fleet,
    )

    result = await runner.sync_and_run(
        RemoteTestConfig(
            server_id=server.id,
            project_path=temp_dir,
            test_command="pytest",
            setup_command="pip install -r requirements.txt",
            stream_output=False,
        )
    )

    assert result.success is False
    assert result.exit_code == 7
    assert result.stdout == "setup-out"
    assert result.stderr == "Setup failed: setup-err"
    assert fleet.record_activity.await_count == 2

    row = await TestRunRepository(db).get_by_id(result.run_id)
    assert row is not None
    assert row["server_id"] == server.id
    assert row["success"] == 0
    assert row["exit_code"] == 7
    assert row["stderr"] == "Setup failed: setup-err"

    events = await event_store.get_events("test_run", result.run_id)
    event_types = [event.event_type for event in events]
    assert event_types.count(EventType.TEST_RUN_STARTED) == 1
    assert event_types.count(EventType.TEST_RUN_COMPLETED) == 1
    assert event_types.count(EventType.TEST_RUN_FAILED) == 1


@pytest.mark.asyncio
async def test_aws_test_runner_stream_output_uses_same_command_result_exit_status(
    db,
    event_store,
    metrics_collector,
    temp_dir: Path,
) -> None:
    server = SpotServer(
        id="srv-stream-exit-1",
        instance_id="i-stream-exit-1",
        name="runner-stream-exit",
        config=SpotServerConfig(name="runner-stream-exit", instance_type="t3.medium"),
        state=ServerState.RUNNING,
        launched_at=datetime.now(UTC),
        region="us-east-1",
        availability_zone="us-east-1a",
        public_ip="127.0.0.1",
    )
    await _ensure_test_server(db, server)

    fleet = SimpleNamespace(
        get_server=AsyncMock(return_value=server),
        record_activity=AsyncMock(),
    )
    remote = SimpleNamespace(
        sync_push=AsyncMock(
            return_value=SimpleNamespace(
                success=True,
                stderr="",
                stdout="",
                files_transferred=1,
                duration_seconds=0.1,
            )
        ),
        execute_command=AsyncMock(
            return_value=SimpleNamespace(
                success=False,
                stdout="line-one\nline-two",
                stderr="streamed stderr",
                exit_code=9,
                duration_seconds=0.2,
            )
        ),
        execute_command_and_stream=AsyncMock(),
        execute_streaming=AsyncMock(),
        sync_pull=AsyncMock(),
    )
    runner = AwsTestRunner(
        db=db,
        event_store=event_store,
        metrics=metrics_collector,
        remote_service=remote,
        fleet_manager=fleet,
    )

    result = await runner.sync_and_run(
        RemoteTestConfig(
            server_id=server.id,
            project_path=temp_dir,
            test_command="pytest -q",
            stream_output=True,
        )
    )

    assert result.success is False
    assert result.exit_code == 9
    assert result.stdout == "line-one\nline-two"
    assert result.stderr == "streamed stderr"
    remote.execute_streaming.assert_not_called()
    remote.execute_command.assert_awaited_once()


@pytest.mark.asyncio
async def test_aws_test_runner_streams_live_output_when_callback_is_provided(
    db,
    event_store,
    metrics_collector,
    temp_dir: Path,
) -> None:
    server = SpotServer(
        id="srv-stream-live-1",
        instance_id="i-stream-live-1",
        name="runner-stream-live",
        config=SpotServerConfig(name="runner-stream-live", instance_type="t3.medium"),
        state=ServerState.RUNNING,
        launched_at=datetime.now(UTC),
        region="us-east-1",
        availability_zone="us-east-1a",
        public_ip="127.0.0.1",
    )
    await _ensure_test_server(db, server)

    fleet = SimpleNamespace(
        get_server=AsyncMock(return_value=server),
        record_activity=AsyncMock(),
    )

    async def execute_command_and_stream(*args, **kwargs):
        await kwargs["on_output"]("stdout", "live stdout")
        await kwargs["on_output"]("stderr", "live stderr")
        return SimpleNamespace(
            success=False,
            stdout="live stdout",
            stderr="live stderr",
            exit_code=4,
            duration_seconds=0.2,
        )

    remote = SimpleNamespace(
        sync_push=AsyncMock(
            return_value=SimpleNamespace(
                success=True,
                stderr="",
                stdout="",
                files_transferred=1,
                duration_seconds=0.1,
            )
        ),
        execute_command=AsyncMock(),
        execute_command_and_stream=AsyncMock(side_effect=execute_command_and_stream),
        execute_streaming=AsyncMock(),
        sync_pull=AsyncMock(),
    )
    runner = AwsTestRunner(
        db=db,
        event_store=event_store,
        metrics=metrics_collector,
        remote_service=remote,
        fleet_manager=fleet,
    )
    emitted: list[tuple[str, str]] = []

    async def on_output(source: str, line: str) -> None:
        emitted.append((source, line))

    result = await runner.sync_and_run(
        RemoteTestConfig(
            server_id=server.id,
            project_path=temp_dir,
            test_command="pytest -q",
            stream_output=True,
        ),
        on_output_line=on_output,
    )

    assert emitted == [("stdout", "live stdout"), ("stderr", "live stderr")]
    assert result.success is False
    assert result.exit_code == 4
    assert result.stdout == "live stdout"
    assert result.stderr == "live stderr"
    remote.execute_command_and_stream.assert_awaited_once()
    remote.execute_command.assert_not_called()


@pytest.mark.asyncio
async def test_aws_test_runner_cleans_downloaded_artifacts_when_store_fails(
    db,
    event_store,
    metrics_collector,
    temp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = SpotServer(
        id="srv-store-fail-1",
        instance_id="i-store-fail-1",
        name="runner-store-fail",
        config=SpotServerConfig(name="runner-store-fail", instance_type="t3.medium"),
        state=ServerState.RUNNING,
        launched_at=datetime.now(UTC),
        region="us-east-1",
        availability_zone="us-east-1a",
        public_ip="127.0.0.1",
    )

    fleet = SimpleNamespace(
        get_server=AsyncMock(return_value=server),
        record_activity=AsyncMock(),
    )

    async def sync_pull(*args, **kwargs):
        local_dir = kwargs["local_path"]
        artifact_file = local_dir / "artifact.txt"
        artifact_file.write_text("artifact-data", encoding="utf-8")
        return SimpleNamespace(
            success=True,
            stderr="",
            stdout="",
            files_transferred=1,
            duration_seconds=0.1,
        )

    remote = SimpleNamespace(
        sync_push=AsyncMock(
            return_value=SimpleNamespace(
                success=True,
                stderr="",
                stdout="",
                files_transferred=1,
                duration_seconds=0.1,
            )
        ),
        execute_command=AsyncMock(
            return_value=SimpleNamespace(
                success=True,
                stdout="ok",
                stderr="",
                exit_code=0,
                duration_seconds=0.1,
            )
        ),
        execute_streaming=AsyncMock(),
        sync_pull=AsyncMock(side_effect=sync_pull),
    )
    runner = AwsTestRunner(
        db=db,
        event_store=event_store,
        metrics=metrics_collector,
        remote_service=remote,
        fleet_manager=fleet,
    )

    async def fail_store(*args, **kwargs):
        raise RuntimeError("store failed")

    monkeypatch.setattr(runner, "_store_result", fail_store)

    with pytest.raises(RuntimeError, match="store failed"):
        await runner.sync_and_run(
            RemoteTestConfig(
                server_id=server.id,
                project_path=temp_dir,
                test_command="pytest",
                stream_output=False,
                save_artifacts=("artifact.txt",),
            )
        )

    artifact_root = Path("/tmp/pms-artifacts")
    assert not list(artifact_root.glob("*/artifact.txt"))
