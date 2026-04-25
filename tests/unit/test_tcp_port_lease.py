from __future__ import annotations

import json
import os
from pathlib import Path

from scripts.lease_tcp_port import (
    allocate_port,
    cleanup_stale_leases,
    release_port,
)


def test_allocate_port_creates_lease_file(tmp_path: Path) -> None:
    lease = allocate_port(lease_dir=tmp_path, owner_pid=os.getpid())

    assert lease.port > 0
    assert lease.lease_path.is_file()
    payload = json.loads(lease.lease_path.read_text(encoding="utf-8"))
    assert payload["port"] == lease.port
    assert payload["owner_pid"] == os.getpid()


def test_allocate_port_avoids_live_reserved_port(tmp_path: Path) -> None:
    first = allocate_port(lease_dir=tmp_path, owner_pid=os.getpid())
    second = allocate_port(lease_dir=tmp_path, owner_pid=os.getpid())

    assert first.port != second.port


def test_cleanup_stale_leases_removes_dead_owner(tmp_path: Path) -> None:
    stale_path = tmp_path / "lease-62000-999999-stale.json"
    stale_path.write_text(
        json.dumps(
            {
                "port": 62000,
                "lease_path": str(stale_path),
                "host": "127.0.0.1",
                "owner_pid": 999999,
            }
        ),
        encoding="utf-8",
    )

    cleanup_stale_leases(tmp_path)

    assert not stale_path.exists()


def test_release_port_removes_existing_lease(tmp_path: Path) -> None:
    lease = allocate_port(lease_dir=tmp_path, owner_pid=os.getpid())

    released = release_port(lease_path=lease.lease_path)

    assert released is True
    assert not lease.lease_path.exists()
