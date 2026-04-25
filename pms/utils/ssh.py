"""SSH utilities for remote command execution."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import asyncssh

from pms.exceptions import SSHExecutionError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable


type OutputSource = Literal["stdout", "stderr"]
type OutputCallback = Callable[[OutputSource, str], Awaitable[None] | None]


@dataclass(frozen=True)
class SSHConfig:
    """SSH connection configuration."""

    host: str
    username: str
    port: int = 22
    private_key_path: Path | None = None
    password: str | None = None
    known_hosts: Path | None = None
    connect_timeout: float = 30.0

    def to_connect_options(self) -> dict[str, Any]:
        """Convert to asyncssh connect options."""
        options = {
            "host": self.host,
            "username": self.username,
            "port": self.port,
        }

        if self.private_key_path:
            options["client_keys"] = [str(self.private_key_path)]

        if self.password:
            options["password"] = self.password

        if self.known_hosts:
            options["known_hosts"] = str(self.known_hosts)
        else:
            # Use default known_hosts file for security
            # Users can explicitly set known_hosts=None if they want to bypass (not recommended)
            default_known_hosts = Path.home() / ".ssh" / "known_hosts"
            if default_known_hosts.exists():
                options["known_hosts"] = str(default_known_hosts)
            else:
                # If no known_hosts file exists, create it and allow new host additions
                # This is more secure than accepting all unknown hosts
                default_known_hosts.parent.mkdir(parents=True, exist_ok=True)
                default_known_hosts.touch(mode=0o600)
                options["known_hosts"] = str(default_known_hosts)

        return options


@dataclass
class CommandResult:
    """Result of an SSH command execution."""

    command: str
    exit_code: int
    stdout: str
    stderr: str
    started_at: datetime
    finished_at: datetime
    host: str

    @property
    def success(self) -> bool:
        """Check if command succeeded."""
        return self.exit_code == 0

    @property
    def duration_seconds(self) -> float:
        """Get command duration in seconds."""
        return (self.finished_at - self.started_at).total_seconds()


@dataclass
class SSHSession:
    """
    Manages an SSH connection for command execution.

    Supports both single command execution and streaming output.
    """

    config: SSHConfig
    _conn: asyncssh.SSHClientConnection | None = field(default=None, init=False)

    async def connect(self) -> None:
        """Establish SSH connection."""
        try:
            options = self.config.to_connect_options()
            self._conn = await asyncio.wait_for(
                asyncssh.connect(**options),
                timeout=self.config.connect_timeout,
            )
        except TimeoutError as e:
            raise SSHExecutionError(
                f"Connection to {self.config.host} timed out after {self.config.connect_timeout}s",
                exit_code=1,
            ) from e
        except asyncssh.Error as e:
            raise SSHExecutionError(
                f"Failed to connect to {self.config.host}: {e}", exit_code=1
            ) from e

    async def disconnect(self) -> None:
        """Close SSH connection."""
        if self._conn:
            self._conn.close()
            await self._conn.wait_closed()
            self._conn = None

    async def __aenter__(self) -> SSHSession:
        """Context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        await self.disconnect()

    async def execute(
        self,
        command: str,
        timeout: float | None = None,
        check: bool = False,
    ) -> CommandResult:
        """
        Execute a command and return the result.

        Args:
            command: Command to execute
            timeout: Optional timeout in seconds
            check: If True, raise on non-zero exit code

        Returns:
            CommandResult with output and exit code

        Raises:
            SSHExecutionError: If connection not established or command fails (when check=True)
        """
        if self._conn is None:
            raise SSHExecutionError("Not connected. Call connect() first.", exit_code=1)

        started_at = datetime.now(UTC)

        try:
            if timeout:
                result = await asyncio.wait_for(
                    self._conn.run(command),
                    timeout=timeout,
                )
            else:
                result = await self._conn.run(command)

            finished_at = datetime.now(UTC)

            cmd_result = CommandResult(
                command=command,
                exit_code=result.returncode or 0,
                stdout=str(result.stdout or ""),
                stderr=str(result.stderr or ""),
                started_at=started_at,
                finished_at=finished_at,
                host=self.config.host,
            )

            if check and not cmd_result.success:
                raise SSHExecutionError(
                    f"Command failed with exit code {cmd_result.exit_code}: {cmd_result.stderr}",
                    exit_code=cmd_result.exit_code,
                    stderr=cmd_result.stderr,
                )

            return cmd_result

        except TimeoutError as e:
            raise SSHExecutionError(
                f"Command '{command}' timed out after {timeout}s", exit_code=1
            ) from e
        except asyncssh.Error as e:
            raise SSHExecutionError(
                f"SSH error executing '{command}': {e}", exit_code=1
            ) from e

    async def execute_streaming(
        self,
        command: str,
    ) -> AsyncIterator[str]:
        """
        Execute a command with streaming output.

        Args:
            command: Command to execute

        Yields:
            Lines of output as they arrive
        """
        if self._conn is None:
            raise SSHExecutionError("Not connected. Call connect() first.", exit_code=1)

        try:
            async with self._conn.create_process(command) as process:
                if process.stdout:
                    async for line in process.stdout:
                        yield line.rstrip("\n")
        except asyncssh.Error as e:
            raise SSHExecutionError(f"SSH error: {e}", exit_code=1) from e

    async def execute_and_stream(
        self,
        command: str,
        *,
        timeout: float | None = None,
        check: bool = False,
        on_output: OutputCallback | None = None,
    ) -> CommandResult:
        """Execute a command, stream output as it arrives, and return the result."""
        if self._conn is None:
            raise SSHExecutionError("Not connected. Call connect() first.", exit_code=1)

        started_at = datetime.now(UTC)
        stdout_lines: list[str] = []
        stderr_lines: list[str] = []

        async def _consume(
            stream: AsyncIterator[str] | None,
            source: OutputSource,
            sink: list[str],
        ) -> None:
            if stream is None:
                return
            async for raw_line in stream:
                line = raw_line.rstrip("\n")
                sink.append(line)
                if on_output is not None:
                    callback_result = on_output(source, line)
                    if inspect.isawaitable(callback_result):
                        await callback_result

        try:
            async with self._conn.create_process(command) as process:
                stdout_task = asyncio.create_task(
                    _consume(process.stdout, "stdout", stdout_lines)
                )
                stderr_task = asyncio.create_task(
                    _consume(process.stderr, "stderr", stderr_lines)
                )
                try:
                    completed = await process.wait(timeout=timeout)
                except TimeoutError as e:
                    process.kill()
                    with contextlib.suppress(asyncssh.Error):
                        await process.wait_closed()
                    await asyncio.gather(
                        stdout_task,
                        stderr_task,
                        return_exceptions=True,
                    )
                    raise SSHExecutionError(
                        f"Command '{command}' timed out after {timeout}s",
                        exit_code=1,
                    ) from e

                await asyncio.gather(stdout_task, stderr_task)
                finished_at = datetime.now(UTC)
                cmd_result = CommandResult(
                    command=command,
                    exit_code=completed.returncode or 0,
                    stdout="\n".join(stdout_lines),
                    stderr="\n".join(stderr_lines),
                    started_at=started_at,
                    finished_at=finished_at,
                    host=self.config.host,
                )

                if check and not cmd_result.success:
                    raise SSHExecutionError(
                        f"Command failed with exit code {cmd_result.exit_code}: {cmd_result.stderr}",
                        exit_code=cmd_result.exit_code,
                        stderr=cmd_result.stderr,
                    )

                return cmd_result
        except asyncssh.Error as e:
            raise SSHExecutionError(
                f"SSH error executing '{command}': {e}", exit_code=1
            ) from e

    async def upload_file(
        self,
        local_path: Path,
        remote_path: str,
    ) -> None:
        """
        Upload a file via SFTP.

        Args:
            local_path: Local file path
            remote_path: Remote destination path
        """
        if self._conn is None:
            raise SSHExecutionError("Not connected. Call connect() first.", exit_code=1)

        try:
            async with self._conn.start_sftp_client() as sftp:
                await sftp.put(str(local_path), remote_path)
        except asyncssh.Error as e:
            raise SSHExecutionError(f"SFTP upload failed: {e}", exit_code=1) from e

    async def download_file(
        self,
        remote_path: str,
        local_path: Path,
    ) -> None:
        """
        Download a file via SFTP.

        Args:
            remote_path: Remote file path
            local_path: Local destination path
        """
        if self._conn is None:
            raise SSHExecutionError("Not connected. Call connect() first.", exit_code=1)

        try:
            async with self._conn.start_sftp_client() as sftp:
                await sftp.get(remote_path, str(local_path))
        except asyncssh.Error as e:
            raise SSHExecutionError(f"SFTP download failed: {e}", exit_code=1) from e


async def test_connection(config: SSHConfig) -> tuple[bool, str]:
    """
    Test an SSH connection.

    Args:
        config: SSH configuration to test

    Returns:
        Tuple of (success, message)
    """
    try:
        async with SSHSession(config) as session:
            result = await session.execute("echo 'Connection successful'", timeout=10.0)
            if result.success:
                return True, f"Connected to {config.host}"
            return False, f"Command failed: {result.stderr}"
    except SSHExecutionError as e:
        return False, str(e)


async def execute_remote_command(
    host: str,
    username: str,
    command: str,
    port: int = 22,
    private_key_path: Path | None = None,
    password: str | None = None,
    timeout: float | None = None,
) -> CommandResult:
    """
    Convenience function to execute a single remote command.

    Args:
        host: Remote hostname
        username: SSH username
        command: Command to execute
        port: SSH port
        private_key_path: Path to private key
        password: SSH password (if not using key)
        timeout: Command timeout

    Returns:
        CommandResult with output
    """
    config = SSHConfig(
        host=host,
        username=username,
        port=port,
        private_key_path=private_key_path,
        password=password,
    )

    async with SSHSession(config) as session:
        return await session.execute(command, timeout=timeout)
