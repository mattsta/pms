"""Transactional tests for RemoteService."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from pms.services.remote_service import RemoteService


async def _count_remote_hosts(db, *, host_id: str | None = None) -> int:
    if host_id is None:
        row = await db.fetch_one("SELECT COUNT(*) AS count FROM remote_hosts")
        return int(row["count"]) if row else 0

    row = await db.fetch_one(
        "SELECT COUNT(*) AS count FROM remote_hosts WHERE id = ?",
        (host_id,),
    )
    return int(row["count"]) if row else 0


@pytest.mark.asyncio
async def test_add_host_rolls_back_when_metrics_flush_fails(
    db,
    event_store,
    revision_store,
    metrics_collector,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Host creation should roll back fully on late metrics failure."""
    service = RemoteService(db, event_store, revision_store, metrics_collector)

    async def fail_flush(*args, **kwargs):
        raise RuntimeError("metrics flush failed")

    monkeypatch.setattr(service.metrics, "flush", fail_flush)

    with pytest.raises(RuntimeError, match="metrics flush failed"):
        await service.add_host(
            name="atomic-remote-host",
            host="example.com",
            username="deploy",
        )

    assert await _count_remote_hosts(db) == 0
    assert service._hosts == {}


@pytest.mark.asyncio
async def test_delete_host_rolls_back_when_metrics_flush_fails(
    db,
    event_store,
    revision_store,
    metrics_collector,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Host deletion should roll back fully on late metrics failure."""
    service = RemoteService(db, event_store, revision_store, metrics_collector)
    host = await service.add_host(
        name="stable-remote-host",
        host="example.org",
        username="deploy",
    )

    async def fail_flush(*args, **kwargs):
        raise RuntimeError("metrics flush failed")

    monkeypatch.setattr(service.metrics, "flush", fail_flush)

    with pytest.raises(RuntimeError, match="metrics flush failed"):
        await service.delete_host(host.id)

    assert await _count_remote_hosts(db, host_id=host.id) == 1
    assert service._hosts[host.id].id == host.id
    assert service._hosts[host.name].id == host.id

    fresh_service = RemoteService(db, event_store, revision_store, metrics_collector)
    persisted = await fresh_service.get_host(host.id)
    assert persisted is not None
    assert persisted.id == host.id


@pytest.mark.asyncio
async def test_execute_command_ignores_observational_metrics_flush_failures(
    db,
    event_store,
    revision_store,
    metrics_collector,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Successful command results should survive late observational metrics failure."""
    service = RemoteService(db, event_store, revision_store, metrics_collector)
    host = await service.add_host(
        name="observational-remote-host",
        host="example.net",
        username="deploy",
    )

    class _FakeSession:
        def __init__(self, config):
            self.config = config

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, command, timeout=None):
            from datetime import UTC, datetime

            started = datetime.now(UTC)
            return __import__(
                "pms.utils.ssh", fromlist=["CommandResult"]
            ).CommandResult(
                command=command,
                exit_code=0,
                stdout="ok\n",
                stderr="",
                started_at=started,
                finished_at=started,
                host=self.config.host,
            )

    async def fail_flush(*args, **kwargs):
        raise RuntimeError("metrics flush failed")

    monkeypatch.setattr("pms.services.remote_service.SSHSession", _FakeSession)
    monkeypatch.setattr(service.metrics, "flush", fail_flush)

    result = await service.execute_command(host.id, "echo ok")

    assert result.success is True
    assert result.stdout == "ok\n"


@pytest.mark.asyncio
async def test_sync_push_and_pull_ignore_observational_metrics_flush_failures(
    db,
    event_store,
    revision_store,
    metrics_collector,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Successful sync results should survive late observational metrics failure."""
    service = RemoteService(db, event_store, revision_store, metrics_collector)
    host = await service.add_host(
        name="observational-sync-host",
        host="example.sync",
        username="deploy",
        default_remote_path="/srv/pms",
    )

    def _sync_result(source: str, destination: str):
        result_cls = __import__("pms.utils.rsync", fromlist=["SyncResult"]).SyncResult
        started = datetime.now(UTC)
        return result_cls(
            source=source,
            destination=destination,
            exit_code=0,
            stdout="synced\n",
            stderr="",
            started_at=started,
            finished_at=started,
            files_transferred=2,
            bytes_transferred=128,
            dry_run=False,
        )

    async def fake_push(**kwargs):
        return _sync_result(str(kwargs["local_path"]), kwargs["remote_path"])

    async def fake_pull(**kwargs):
        return _sync_result(kwargs["remote_path"], str(kwargs["local_path"]))

    async def fail_flush(*args, **kwargs):
        raise RuntimeError("metrics flush failed")

    monkeypatch.setattr("pms.services.remote_service.push", fake_push)
    monkeypatch.setattr("pms.services.remote_service.pull", fake_pull)
    monkeypatch.setattr(service.metrics, "flush", fail_flush)

    push_result = await service.sync_push(host.id, tmp_path, remote_path="/srv/push")
    pull_result = await service.sync_pull(
        host.id,
        remote_path="/srv/pull",
        local_path=tmp_path,
    )

    assert push_result.success is True
    assert push_result.files_transferred == 2
    assert push_result.destination == "/srv/push"
    assert pull_result.success is True
    assert pull_result.files_transferred == 2
    assert pull_result.source == "/srv/pull"
