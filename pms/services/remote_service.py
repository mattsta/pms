"""Remote service for SSH and sync operations."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.exceptions import NotFoundError, RemoteError
from pms.models import HostType, RemoteHost
from pms.models.json_types import JsonValue
from pms.utils.rsync import SyncResult, pull, push, sync_project
from pms.utils.ssh import (
    CommandResult,
    SSHConfig,
    SSHSession,
    test_connection,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from pms.db.connection import Database
    from pms.utils.ssh import OutputCallback

type RemoteHostRow = dict[str, JsonValue]


@dataclass
class RemoteHostInfo:
    """Information about a remote host."""

    host: RemoteHost
    is_reachable: bool = False
    last_checked: datetime | None = None
    connection_error: str | None = None


@dataclass
class SyncOperation:
    """A sync operation record."""

    id: str
    project_id: str
    remote_host_id: str
    direction: str
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    files_transferred: int = 0
    bytes_transferred: int = 0
    error_message: str | None = None


class RemoteService:
    """
    Service for remote host operations.

    Handles SSH connections, command execution, and file synchronization.
    """

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
        self._hosts: dict[str, RemoteHost] = {}  # In-memory cache

    async def add_host(
        self,
        name: str,
        host: str,
        username: str,
        port: int = 22,
        key_path: str | None = None,
        host_type: HostType = HostType.SSH,
        aws_instance_id: str | None = None,
        aws_region: str | None = None,
        default_remote_path: str | None = None,
        tags: list[str] | None = None,
    ) -> RemoteHost:
        """
        Add a new remote host configuration.

        Args:
            name: Friendly name for the host
            host: Hostname or IP address
            username: SSH username
            port: SSH port
            key_path: Path to SSH private key
            host_type: Type of host (SSH or AWS_EC2)
            aws_instance_id: AWS EC2 instance ID
            aws_region: AWS region
            default_remote_path: Default sync destination path
            tags: Host tags

        Returns:
            Created RemoteHost instance
        """
        import uuid

        remote_host = RemoteHost(
            id=str(uuid.uuid4()),
            name=name,
            host=host,
            username=username,
            port=port,
            key_path=key_path,
            host_type=host_type,
            aws_instance_id=aws_instance_id,
            aws_region=aws_region,
            default_remote_path=default_remote_path,
            tags=tuple(tags) if tags else (),
        )

        async with self.db.transaction():
            await self.db.execute(
                """
                INSERT INTO remote_hosts (
                    id, name, host, port, username, key_path,
                    host_type, aws_instance_id, aws_region,
                    default_remote_path, tags, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    remote_host.id,
                    remote_host.name,
                    remote_host.host,
                    remote_host.port,
                    remote_host.username,
                    remote_host.key_path,
                    remote_host.host_type.value,
                    remote_host.aws_instance_id,
                    remote_host.aws_region,
                    remote_host.default_remote_path,
                    json.dumps(list(remote_host.tags)),
                    remote_host.created_at.isoformat(),
                    remote_host.updated_at.isoformat(),
                ),
            )
            await self.metrics.record_counter("remote_host.added")
            await self.metrics.flush()

        self._hosts[remote_host.id] = remote_host
        self._hosts[remote_host.name] = remote_host

        return remote_host

    async def get_host(self, identifier: str) -> RemoteHost | None:
        """
        Get a remote host by ID or name.

        Args:
            identifier: Host ID or name

        Returns:
            RemoteHost or None if not found
        """
        # Check cache
        if identifier in self._hosts:
            return self._hosts[identifier]

        # Query database
        row = await self.db.fetch_one(
            "SELECT * FROM remote_hosts WHERE id = ? OR name = ?",
            (identifier, identifier),
        )

        if row is None:
            return None

        host = self._host_from_row(row)
        self._hosts[host.id] = host
        self._hosts[host.name] = host

        return host

    async def list_hosts(
        self,
        host_type: HostType | None = None,
        tag: str | None = None,
    ) -> list[RemoteHost]:
        """
        List all remote hosts.

        Args:
            host_type: Filter by host type
            tag: Filter by tag

        Returns:
            List of RemoteHost instances
        """
        query = "SELECT * FROM remote_hosts WHERE 1=1"
        params: list[str] = []

        if host_type:
            query += " AND host_type = ?"
            params.append(host_type.value)

        if tag:
            query += " AND tags LIKE ?"
            params.append(f'%"{tag}"%')

        query += " ORDER BY name"

        rows = await self.db.fetch_all(query, tuple(params))
        return [self._host_from_row(row) for row in rows]

    async def delete_host(self, identifier: str) -> bool:
        """
        Delete a remote host.

        Args:
            identifier: Host ID or name

        Returns:
            True if deleted
        """
        host = await self.get_host(identifier)
        if host is None:
            return False

        async with self.db.transaction():
            await self.db.execute(
                "DELETE FROM remote_hosts WHERE id = ?",
                (host.id,),
            )
            await self.metrics.record_counter("remote_host.deleted")
            await self.metrics.flush()

        self._hosts.pop(host.id, None)
        self._hosts.pop(host.name, None)

        return True

    async def test_host(self, identifier: str) -> RemoteHostInfo:
        """
        Test connection to a remote host.

        Args:
            identifier: Host ID or name

        Returns:
            RemoteHostInfo with connection status
        """
        host = await self.get_host(identifier)
        if host is None:
            raise NotFoundError("Remote host", identifier)

        config = SSHConfig(
            host=host.host,
            username=host.username,
            port=host.port,
            private_key_path=Path(host.key_path) if host.key_path else None,
        )

        success, message = await test_connection(config)

        return RemoteHostInfo(
            host=host,
            is_reachable=success,
            last_checked=datetime.now(UTC),
            connection_error=message if not success else None,
        )

    async def execute_command(
        self,
        identifier: str,
        command: str,
        timeout: float | None = None,
    ) -> CommandResult:
        """
        Execute a command on a remote host.

        Args:
            identifier: Host ID or name
            command: Command to execute
            timeout: Optional timeout in seconds

        Returns:
            CommandResult with output

        Raises:
            NotFoundError: If host not found
            SSHExecutionError: If command fails
        """
        host = await self.get_host(identifier)
        if host is None:
            raise NotFoundError("Remote host", identifier)

        config = SSHConfig(
            host=host.host,
            username=host.username,
            port=host.port,
            private_key_path=Path(host.key_path) if host.key_path else None,
        )

        async with SSHSession(config) as session:
            result = await session.execute(command, timeout=timeout)

        await self.metrics.record_counter(
            "remote.command_executed",
            labels={"host": host.name, "success": str(result.success)},
        )
        await self.metrics.record_timing(
            "remote.command_duration",
            result.duration_seconds * 1000,
            labels={"host": host.name},
        )
        await self.metrics.flush_best_effort(context="remote.execute_command")

        return result

    async def execute_streaming(
        self,
        identifier: str,
        command: str,
    ) -> AsyncIterator[str]:
        """
        Execute a command with streaming output.

        Args:
            identifier: Host ID or name
            command: Command to execute

        Yields:
            Lines of output as they arrive
        """
        host = await self.get_host(identifier)
        if host is None:
            raise NotFoundError("Remote host", identifier)

        config = SSHConfig(
            host=host.host,
            username=host.username,
            port=host.port,
            private_key_path=Path(host.key_path) if host.key_path else None,
        )

        async with SSHSession(config) as session:
            async for line in session.execute_streaming(command):
                yield line

    async def execute_command_and_stream(
        self,
        identifier: str,
        command: str,
        timeout: float | None = None,
        *,
        on_output: OutputCallback | None = None,
    ) -> CommandResult:
        """Execute a command, emit live output callbacks, and return the result."""
        host = await self.get_host(identifier)
        if host is None:
            raise NotFoundError("Remote host", identifier)

        config = SSHConfig(
            host=host.host,
            username=host.username,
            port=host.port,
            private_key_path=Path(host.key_path) if host.key_path else None,
        )

        async with SSHSession(config) as session:
            result = await session.execute_and_stream(
                command,
                timeout=timeout,
                on_output=on_output,
            )

        await self.metrics.record_counter(
            "remote.command_executed",
            labels={"host": host.name, "success": str(result.success)},
        )
        await self.metrics.record_timing(
            "remote.command_duration",
            result.duration_seconds * 1000,
            labels={"host": host.name},
        )
        await self.metrics.flush_best_effort(
            context="remote.execute_command_and_stream"
        )

        return result

    async def sync_push(
        self,
        identifier: str,
        local_path: Path,
        remote_path: str | None = None,
        exclude: list[str] | None = None,
        delete: bool = False,
        dry_run: bool = False,
    ) -> SyncResult:
        """
        Push local files to remote host.

        Args:
            identifier: Host ID or name
            local_path: Local path to sync
            remote_path: Remote destination (uses default if not specified)
            exclude: Patterns to exclude
            delete: Delete extraneous files on destination
            dry_run: Perform trial run without changes

        Returns:
            SyncResult with operation details
        """
        host = await self.get_host(identifier)
        if host is None:
            raise NotFoundError("Remote host", identifier)

        dest_path = remote_path or host.default_remote_path
        if not dest_path:
            raise RemoteError("No remote path specified and host has no default path")

        result = await push(
            local_path=local_path,
            remote_host=host.host,
            remote_path=dest_path,
            username=host.username,
            port=host.port,
            ssh_key=Path(host.key_path) if host.key_path else None,
            exclude=exclude,
            delete=delete,
            dry_run=dry_run,
        )

        if not dry_run:
            await self.metrics.record_counter(
                "remote.sync_push",
                labels={"host": host.name, "success": str(result.success)},
            )
            await self.metrics.record_gauge(
                "remote.sync_files",
                float(result.files_transferred),
                labels={"host": host.name, "direction": "push"},
            )
            await self.metrics.flush_best_effort(context="remote.sync_push")

        return result

    async def sync_pull(
        self,
        identifier: str,
        remote_path: str,
        local_path: Path,
        exclude: list[str] | None = None,
        delete: bool = False,
        dry_run: bool = False,
    ) -> SyncResult:
        """
        Pull files from remote host to local.

        Args:
            identifier: Host ID or name
            remote_path: Remote source path
            local_path: Local destination
            exclude: Patterns to exclude
            delete: Delete extraneous files on destination
            dry_run: Perform trial run without changes

        Returns:
            SyncResult with operation details
        """
        host = await self.get_host(identifier)
        if host is None:
            raise NotFoundError("Remote host", identifier)

        result = await pull(
            remote_host=host.host,
            remote_path=remote_path,
            local_path=local_path,
            username=host.username,
            port=host.port,
            ssh_key=Path(host.key_path) if host.key_path else None,
            exclude=exclude,
            delete=delete,
            dry_run=dry_run,
        )

        if not dry_run:
            await self.metrics.record_counter(
                "remote.sync_pull",
                labels={"host": host.name, "success": str(result.success)},
            )
            await self.metrics.record_gauge(
                "remote.sync_files",
                float(result.files_transferred),
                labels={"host": host.name, "direction": "pull"},
            )
            await self.metrics.flush_best_effort(context="remote.sync_pull")

        return result

    async def sync_project_to_host(
        self,
        identifier: str,
        project_path: Path,
        remote_path: str | None = None,
        direction: str = "push",
        delete: bool = False,
        dry_run: bool = False,
    ) -> SyncResult:
        """
        Sync a project with sensible defaults (excludes .git, node_modules, etc.).

        Args:
            identifier: Host ID or name
            project_path: Local project path
            remote_path: Remote path (uses default if not specified)
            direction: "push" or "pull"
            delete: Delete extraneous files on destination
            dry_run: Perform trial run without changes

        Returns:
            SyncResult with operation details
        """
        host = await self.get_host(identifier)
        if host is None:
            raise NotFoundError("Remote host", identifier)

        dest_path = remote_path or host.default_remote_path
        if not dest_path:
            raise RemoteError("No remote path specified and host has no default path")

        return await sync_project(
            project_path=project_path,
            remote_host=host.host,
            remote_path=dest_path,
            username=host.username,
            direction=direction,
            port=host.port,
            ssh_key=Path(host.key_path) if host.key_path else None,
            delete=delete,
            dry_run=dry_run,
        )

    def _host_from_row(self, row: RemoteHostRow) -> RemoteHost:
        """Convert database row to RemoteHost."""
        tags_raw_value = row.get("tags", "")
        tags_raw = tags_raw_value if isinstance(tags_raw_value, str) else ""
        parsed_tags = json.loads(tags_raw) if tags_raw else []
        tags = tuple(str(tag).strip() for tag in parsed_tags if str(tag).strip())
        port_raw = row.get("port", 22)
        if isinstance(port_raw, int):
            port = port_raw
        elif isinstance(port_raw, str) and port_raw.isdigit():
            port = int(port_raw)
        else:
            port = 22

        host_type_raw = row.get("host_type", "ssh")
        host_type_value = host_type_raw if isinstance(host_type_raw, str) else "ssh"

        created_raw = row.get("created_at")
        created_at = (
            datetime.fromisoformat(created_raw)
            if isinstance(created_raw, str) and created_raw
            else datetime.now(UTC)
        )
        updated_raw = row.get("updated_at")
        updated_at = (
            datetime.fromisoformat(updated_raw)
            if isinstance(updated_raw, str) and updated_raw
            else datetime.now(UTC)
        )
        key_path_raw = row.get("key_path")
        key_path = key_path_raw if isinstance(key_path_raw, str) else None

        aws_instance_id_raw = row.get("aws_instance_id")
        aws_instance_id = (
            aws_instance_id_raw if isinstance(aws_instance_id_raw, str) else None
        )

        aws_region_raw = row.get("aws_region")
        aws_region = aws_region_raw if isinstance(aws_region_raw, str) else None

        default_remote_path_raw = row.get("default_remote_path")
        default_remote_path = (
            default_remote_path_raw
            if isinstance(default_remote_path_raw, str)
            else None
        )

        return RemoteHost(
            id=str(row["id"]),
            name=str(row["name"]),
            host=str(row["host"]),
            port=port,
            username=str(row["username"]),
            key_path=key_path,
            host_type=HostType(host_type_value),
            aws_instance_id=aws_instance_id,
            aws_region=aws_region,
            default_remote_path=default_remote_path,
            tags=tags,
            created_at=created_at,
            updated_at=updated_at,
        )
