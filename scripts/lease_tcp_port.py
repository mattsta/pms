#!/usr/bin/env python3
"""Allocate and release shared localhost TCP port leases for concurrent test flows."""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import shlex
import socket
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _default_lease_dir() -> Path:
    env_dir = os.environ.get("PMS_PORT_LEASE_DIR")
    if env_dir:
        return Path(env_dir)
    return Path(tempfile.gettempdir()) / "pms-port-leases"


@dataclass(frozen=True)
class PortLease:
    port: int
    lease_path: Path
    host: str
    owner_pid: int

    def to_payload(self) -> dict[str, Any]:
        return {
            "port": self.port,
            "lease_path": str(self.lease_path),
            "host": self.host,
            "owner_pid": self.owner_pid,
        }


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _load_lease_payload(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError, ValueError, TypeError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _list_lease_files(lease_dir: Path) -> list[Path]:
    return sorted(lease_dir.glob("lease-*.json"))


def cleanup_stale_leases(lease_dir: Path) -> None:
    lease_dir.mkdir(parents=True, exist_ok=True)
    for lease_file in _list_lease_files(lease_dir):
        payload = _load_lease_payload(lease_file)
        if payload is None:
            lease_file.unlink(missing_ok=True)
            continue
        owner_pid = payload.get("owner_pid")
        try:
            owner_pid = int(owner_pid)
        except TypeError, ValueError:
            lease_file.unlink(missing_ok=True)
            continue
        if not _pid_is_running(owner_pid):
            lease_file.unlink(missing_ok=True)


@contextlib.contextmanager
def _allocator_lock(lease_dir: Path):
    lease_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lease_dir / ".allocator.lock"
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _reserved_ports(lease_dir: Path) -> set[int]:
    ports: set[int] = set()
    for lease_file in _list_lease_files(lease_dir):
        payload = _load_lease_payload(lease_file)
        if payload is None:
            continue
        try:
            ports.add(int(payload["port"]))
        except KeyError, TypeError, ValueError:
            continue
    return ports


def _probe_ephemeral_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def allocate_port(
    *,
    lease_dir: Path,
    host: str = "127.0.0.1",
    owner_pid: int | None = None,
    attempts: int = 64,
) -> PortLease:
    resolved_owner_pid = owner_pid or os.getppid()
    with _allocator_lock(lease_dir):
        cleanup_stale_leases(lease_dir)
        reserved = _reserved_ports(lease_dir)
        for _ in range(max(1, attempts)):
            port = _probe_ephemeral_port(host)
            if port in reserved:
                continue
            lease_path = (
                lease_dir
                / f"lease-{port}-{resolved_owner_pid}-{uuid.uuid4().hex[:12]}.json"
            )
            lease = PortLease(
                port=port,
                lease_path=lease_path,
                host=host,
                owner_pid=resolved_owner_pid,
            )
            lease_path.write_text(
                json.dumps(lease.to_payload(), sort_keys=True),
                encoding="utf-8",
            )
            return lease
    raise RuntimeError("Could not allocate an unreserved TCP port lease.")


def release_port(*, lease_path: Path) -> bool:
    if not lease_path.exists():
        return False
    lease_path.unlink(missing_ok=True)
    return True


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Allocate and release shared localhost TCP port leases."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    allocate_parser = subparsers.add_parser("allocate")
    allocate_parser.add_argument("--lease-dir", type=Path, default=_default_lease_dir())
    allocate_parser.add_argument("--host", default="127.0.0.1")
    allocate_parser.add_argument("--owner-pid", type=int, default=None)
    allocate_parser.add_argument("--attempts", type=int, default=64)
    allocate_parser.add_argument(
        "--output",
        choices=("json", "shell"),
        default="json",
    )

    release_parser = subparsers.add_parser("release")
    release_parser.add_argument("--lease-path", type=Path, required=True)

    cleanup_parser = subparsers.add_parser("cleanup-stale")
    cleanup_parser.add_argument("--lease-dir", type=Path, default=_default_lease_dir())

    return parser.parse_args()


def _print_shell_assignment(name: str, value: str) -> None:
    print(f"{name}={shlex.quote(value)}")


def main() -> int:
    args = _parse_args()
    if args.command == "allocate":
        lease = allocate_port(
            lease_dir=args.lease_dir,
            host=args.host,
            owner_pid=args.owner_pid,
            attempts=args.attempts,
        )
        if args.output == "shell":
            _print_shell_assignment("PMS_ALLOCATED_PORT", str(lease.port))
            _print_shell_assignment(
                "PMS_ALLOCATED_PORT_LEASE_PATH", str(lease.lease_path)
            )
            return 0
        print(json.dumps(lease.to_payload(), sort_keys=True))
        return 0
    if args.command == "release":
        return 0 if release_port(lease_path=args.lease_path) else 0
    if args.command == "cleanup-stale":
        cleanup_stale_leases(args.lease_dir)
        return 0
    raise SystemExit(2)


if __name__ == "__main__":
    raise SystemExit(main())
