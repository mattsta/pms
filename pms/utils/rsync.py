"""Rsync utilities for file synchronization."""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import signal
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from pms.exceptions import RemoteError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@dataclass(frozen=True)
class RsyncConfig:
    """Rsync operation configuration."""

    source: str  # Local path or remote (user@host:path)
    destination: str  # Local path or remote (user@host:path)

    # Common options
    recursive: bool = True
    delete: bool = False  # Delete extraneous files from dest
    compress: bool = True
    archive: bool = True  # Preserve permissions, times, etc.
    verbose: bool = False
    dry_run: bool = False

    # Filtering
    exclude: list[str] = field(default_factory=list)
    include: list[str] = field(default_factory=list)

    # SSH options
    ssh_port: int = 22
    ssh_key: Path | None = None

    # Performance
    bandwidth_limit: int | None = None  # KB/s

    def to_args(self) -> list[str]:
        """Convert configuration to rsync command arguments."""
        args = ["rsync"]

        if self.archive:
            args.append("-a")
        elif self.recursive:
            args.append("-r")

        if self.compress:
            args.append("-z")

        if self.verbose:
            args.append("-v")

        if self.delete:
            args.append("--delete")

        if self.dry_run:
            args.append("--dry-run")

        # SSH options
        ssh_cmd = f"ssh -p {self.ssh_port}"
        if self.ssh_key:
            ssh_cmd += f" -i {self.ssh_key}"
        args.extend(["-e", ssh_cmd])

        # Filtering
        for pattern in self.exclude:
            args.extend(["--exclude", pattern])

        for pattern in self.include:
            args.extend(["--include", pattern])

        # Performance
        if self.bandwidth_limit:
            args.extend(["--bwlimit", str(self.bandwidth_limit)])

        # Progress for better output
        args.append("--progress")

        # Source and destination
        args.append(self.source)
        args.append(self.destination)

        return args


@dataclass
class SyncResult:
    """Result of an rsync operation."""

    source: str
    destination: str
    exit_code: int
    stdout: str
    stderr: str
    started_at: datetime
    finished_at: datetime
    files_transferred: int = 0
    bytes_transferred: int = 0
    dry_run: bool = False

    @property
    def success(self) -> bool:
        """Check if sync succeeded."""
        return self.exit_code == 0

    @property
    def duration_seconds(self) -> float:
        """Get operation duration in seconds."""
        return (self.finished_at - self.started_at).total_seconds()


def _check_rsync_available() -> bool:
    """Check if rsync is available on the system."""
    return shutil.which("rsync") is not None


async def _terminate_process_group(
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


async def sync(
    config: RsyncConfig,
    timeout: float | None = None,
) -> SyncResult:
    """
    Execute an rsync operation.

    Args:
        config: Rsync configuration
        timeout: Optional timeout in seconds

    Returns:
        SyncResult with operation details

    Raises:
        RemoteError: If rsync fails or is not available
    """
    if not _check_rsync_available():
        raise RemoteError("rsync is not installed or not in PATH")

    args = config.to_args()
    started_at = datetime.now(UTC)

    try:
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )

        if timeout:
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )
            except TimeoutError:
                await _terminate_process_group(process)
                raise RemoteError(f"rsync timed out after {timeout}s")
        else:
            stdout, stderr = await process.communicate()

        finished_at = datetime.now(UTC)

        # Parse output for statistics
        stdout_text = stdout.decode("utf-8", errors="replace")
        stderr_text = stderr.decode("utf-8", errors="replace")

        files_transferred = 0
        bytes_transferred = 0

        # Try to parse rsync statistics from output
        for line in stdout_text.split("\n"):
            if "files transferred" in line.lower():
                with contextlib.suppress(IndexError, ValueError):
                    files_transferred = int(line.split(":")[1].strip().split()[0])

        return SyncResult(
            source=config.source,
            destination=config.destination,
            exit_code=process.returncode or 0,
            stdout=stdout_text,
            stderr=stderr_text,
            started_at=started_at,
            finished_at=finished_at,
            files_transferred=files_transferred,
            bytes_transferred=bytes_transferred,
            dry_run=config.dry_run,
        )

    except FileNotFoundError as e:
        raise RemoteError("rsync executable not found") from e


async def sync_streaming(
    config: RsyncConfig,
) -> AsyncIterator[str]:
    """
    Execute rsync with streaming output.

    Args:
        config: Rsync configuration

    Yields:
        Lines of output as they arrive
    """
    if not _check_rsync_available():
        raise RemoteError("rsync is not installed or not in PATH")

    args = config.to_args()

    process = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,
    )

    if process.stdout:
        async for line in process.stdout:
            yield line.decode("utf-8", errors="replace").rstrip("\n")

    await process.wait()


async def push(
    local_path: str | Path,
    remote_host: str,
    remote_path: str,
    username: str,
    port: int = 22,
    ssh_key: Path | None = None,
    exclude: list[str] | None = None,
    delete: bool = False,
    dry_run: bool = False,
) -> SyncResult:
    """
    Push local files to a remote host.

    Args:
        local_path: Local directory or file path
        remote_host: Remote hostname
        remote_path: Remote destination path
        username: SSH username
        port: SSH port
        ssh_key: Path to SSH private key
        exclude: Patterns to exclude
        delete: Delete extraneous files from destination
        dry_run: Perform trial run without changes

    Returns:
        SyncResult with operation details
    """
    # Ensure local path has trailing slash for directory contents
    source = str(local_path)
    if Path(local_path).is_dir() and not source.endswith("/"):
        source += "/"

    config = RsyncConfig(
        source=source,
        destination=f"{username}@{remote_host}:{remote_path}",
        ssh_port=port,
        ssh_key=ssh_key,
        exclude=exclude or [],
        delete=delete,
        dry_run=dry_run,
    )

    return await sync(config)


async def pull(
    remote_host: str,
    remote_path: str,
    local_path: str | Path,
    username: str,
    port: int = 22,
    ssh_key: Path | None = None,
    exclude: list[str] | None = None,
    delete: bool = False,
    dry_run: bool = False,
) -> SyncResult:
    """
    Pull files from a remote host to local.

    Args:
        remote_host: Remote hostname
        remote_path: Remote source path
        local_path: Local destination path
        username: SSH username
        port: SSH port
        ssh_key: Path to SSH private key
        exclude: Patterns to exclude
        delete: Delete extraneous files from destination
        dry_run: Perform trial run without changes

    Returns:
        SyncResult with operation details
    """
    # Ensure remote path has trailing slash for directory contents
    source = remote_path
    if not source.endswith("/"):
        source += "/"

    config = RsyncConfig(
        source=f"{username}@{remote_host}:{source}",
        destination=str(local_path),
        ssh_port=port,
        ssh_key=ssh_key,
        exclude=exclude or [],
        delete=delete,
        dry_run=dry_run,
    )

    return await sync(config)


async def sync_project(
    project_path: Path,
    remote_host: str,
    remote_path: str,
    username: str,
    direction: str = "push",
    port: int = 22,
    ssh_key: Path | None = None,
    delete: bool = False,
    dry_run: bool = False,
) -> SyncResult:
    """
    Sync a project directory with sensible defaults.

    Automatically excludes common development artifacts:
    - .git
    - node_modules
    - __pycache__
    - .venv / venv
    - .env files

    Args:
        project_path: Local project directory
        remote_host: Remote hostname
        remote_path: Remote project path
        username: SSH username
        direction: "push" or "pull"
        port: SSH port
        ssh_key: Path to SSH private key
        delete: Delete extraneous files from destination
        dry_run: Perform trial run without changes

    Returns:
        SyncResult with operation details
    """
    default_excludes = [
        ".git",
        "node_modules",
        "__pycache__",
        "*.pyc",
        ".venv",
        "venv",
        ".env",
        ".env.*",
        "*.egg-info",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "dist",
        "build",
        ".DS_Store",
    ]

    match direction:
        case "push":
            return await push(
                local_path=project_path,
                remote_host=remote_host,
                remote_path=remote_path,
                username=username,
                port=port,
                ssh_key=ssh_key,
                exclude=default_excludes,
                delete=delete,
                dry_run=dry_run,
            )
        case "pull":
            return await pull(
                remote_host=remote_host,
                remote_path=remote_path,
                local_path=project_path,
                username=username,
                port=port,
                ssh_key=ssh_key,
                exclude=default_excludes,
                delete=delete,
                dry_run=dry_run,
            )
        case _:
            raise ValueError(f"Invalid direction: {direction}. Use 'push' or 'pull'.")
