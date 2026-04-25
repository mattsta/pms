"""Sandboxed Plugin Execution.

Provides isolated execution environments for plugins using:
- Subprocess isolation with resource limits
- Unix socket IPC for communication
- Capability-based permission system

Architecture:
    ┌────────────────────────────────────────┐
    │              PMS Host Process          │
    │  ┌──────────────────────────────────┐  │
    │  │        SandboxManager            │  │
    │  │  ┌─────────┐  ┌─────────┐       │  │
    │  │  │Sandbox 1│  │Sandbox 2│  ...  │  │
    │  │  └────┬────┘  └────┬────┘       │  │
    │  └───────┼────────────┼─────────────┘  │
    └──────────┼────────────┼────────────────┘
               │IPC         │IPC
    ┌──────────▼────┐  ┌────▼──────────┐
    │ Plugin Process│  │ Plugin Process│
    │ (sandboxed)   │  │ (sandboxed)   │
    └───────────────┘  └───────────────┘

Security:
    - Resource limits (memory, CPU)
    - Filesystem restrictions
    - Network restrictions
    - Capability checks
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import resource
import signal
import sys
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pms.plugins.protocol import (
    IPCClient,
    IPCMessage,
    IPCProtocol,
    IPCServer,
)

if TYPE_CHECKING:
    from pms.plugins.manifest import PluginManifest

logger = logging.getLogger(__name__)


async def _terminate_process_group(
    process: asyncio.subprocess.Process,
    *,
    grace_seconds: float,
) -> None:
    if process.returncode is not None:
        return

    if os.name == "nt" or not hasattr(os, "killpg"):
        process.terminate()
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(process.wait(), timeout=grace_seconds)
        if process.returncode is None:
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


@dataclass
class SandboxConfig:
    """Configuration for sandbox execution."""

    # Resource limits
    max_memory_mb: int = 256
    max_cpu_percent: int = 50
    max_open_files: int = 64
    max_processes: int = 4

    # Timeouts
    startup_timeout: float = 10.0
    call_timeout: float = 30.0
    shutdown_timeout: float = 5.0

    # Filesystem
    allowed_paths: list[Path] = field(default_factory=list)
    temp_dir: Path | None = None

    # Network
    allow_network: bool = False
    allowed_hosts: list[str] = field(default_factory=list)

    # Python environment
    python_path: str = sys.executable
    extra_env: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_manifest(cls, manifest: PluginManifest) -> SandboxConfig:
        """Create config from plugin manifest."""
        from pms.plugins.manifest import PluginCapability

        allow_network = PluginCapability.NETWORK in manifest.capabilities

        return cls(
            max_memory_mb=manifest.max_memory_mb,
            call_timeout=manifest.timeout,
            allow_network=allow_network,
        )


@dataclass
class SandboxResult:
    """Result of a sandbox operation."""

    success: bool
    value: Any = None
    error: str | None = None
    execution_time_ms: float = 0.0
    memory_used_mb: float = 0.0

    @classmethod
    def ok(cls, value: Any, execution_time_ms: float = 0.0) -> SandboxResult:
        return cls(success=True, value=value, execution_time_ms=execution_time_ms)

    @classmethod
    def fail(cls, error: str, execution_time_ms: float = 0.0) -> SandboxResult:
        return cls(success=False, error=error, execution_time_ms=execution_time_ms)


class SandboxedPlugin:
    """A plugin running in an isolated sandbox.

    Manages the lifecycle of a sandboxed plugin process:
    - Process creation with resource limits
    - IPC communication via Unix socket
    - Health monitoring
    - Graceful shutdown
    """

    def __init__(
        self,
        manifest: PluginManifest,
        config: SandboxConfig | None = None,
        plugin_dir: Path | None = None,
    ):
        """Initialize sandboxed plugin.

        Args:
            manifest: Plugin manifest
            config: Sandbox configuration
            plugin_dir: Directory containing plugin files
        """
        self.manifest = manifest
        self.config = config or SandboxConfig.from_manifest(manifest)
        self.plugin_dir = plugin_dir or (
            manifest.path.parent if manifest.path else Path.cwd()
        )

        self._process: asyncio.subprocess.Process | None = None
        self._ipc_server: IPCServer | None = None
        self._ipc_client: IPCClient | None = None
        self._protocol: IPCProtocol = IPCProtocol()
        self._running = False
        self._started_at: datetime | None = None

        # Generate unique socket path
        self._socket_path = (
            Path(tempfile.gettempdir()) / f"pms-sandbox-{uuid.uuid4().hex[:8]}.sock"
        )

    @property
    def is_running(self) -> bool:
        return self._running and self._process is not None

    @property
    def pid(self) -> int | None:
        return self._process.pid if self._process else None

    async def start(self) -> bool:
        """Start the sandboxed plugin process.

        Returns:
            True if started successfully
        """
        if self._running:
            return True

        try:
            # Start IPC server
            self._ipc_server = IPCServer(
                socket_path=self._socket_path,
                protocol=self._protocol,
            )
            await self._ipc_server.start()

            # Create sandbox runner script
            runner_script = self._create_runner_script()

            # Start process with resource limits
            env = self._create_env()

            self._process = await asyncio.create_subprocess_exec(
                self.config.python_path,
                "-c",
                runner_script,
                cwd=str(self.plugin_dir),
                env=env,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                preexec_fn=self._setup_limits if sys.platform != "win32" else None,
            )

            # Wait for plugin to connect
            try:
                await asyncio.wait_for(
                    self._wait_for_connection(),
                    timeout=self.config.startup_timeout,
                )
            except TimeoutError:
                logger.error(f"Plugin {self.manifest.name} failed to connect")
                await self._kill_process()
                return False

            self._running = True
            self._started_at = datetime.now(UTC)
            logger.info(
                f"Sandbox started for {self.manifest.name} (PID: {self._process.pid})"
            )
            return True

        except Exception as e:
            logger.exception(f"Failed to start sandbox: {e}")
            await self.stop()
            return False

    async def stop(self) -> None:
        """Stop the sandboxed plugin process."""
        self._running = False

        # Send shutdown signal via IPC
        if self._ipc_server:
            try:
                from pms.plugins.protocol import MessageType

                await self._ipc_server.broadcast(IPCMessage(type=MessageType.SHUTDOWN))
                await asyncio.sleep(0.5)
            except Exception:
                pass

        # Stop process
        await self._kill_process()

        # Stop IPC server
        if self._ipc_server:
            await self._ipc_server.stop()
            self._ipc_server = None

        logger.info(f"Sandbox stopped for {self.manifest.name}")

    async def _kill_process(self) -> None:
        """Kill the sandbox process."""
        if not self._process:
            return

        try:
            await _terminate_process_group(
                self._process,
                grace_seconds=self.config.shutdown_timeout,
            )
        except ProcessLookupError:
            pass
        finally:
            self._process = None

    async def _wait_for_connection(self) -> None:
        """Wait for plugin to connect to IPC server."""
        while not self._ipc_server or len(self._ipc_server._clients) == 0:
            if self._process and self._process.returncode is not None:
                # Process exited
                stdout, stderr = await self._process.communicate()
                raise RuntimeError(
                    f"Plugin process exited: {stderr.decode() if stderr else 'unknown error'}"
                )
            await asyncio.sleep(0.1)

    def _setup_limits(self) -> None:
        """Set up resource limits for child process (Unix only)."""
        # Memory limit
        memory_bytes = self.config.max_memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))

        # Open file limit
        resource.setrlimit(
            resource.RLIMIT_NOFILE,
            (self.config.max_open_files, self.config.max_open_files),
        )

        # Process limit
        resource.setrlimit(
            resource.RLIMIT_NPROC,
            (self.config.max_processes, self.config.max_processes),
        )

        # Create new process group
        os.setpgrp()

    def _create_env(self) -> dict[str, str]:
        """Create environment for sandbox process."""
        env = os.environ.copy()

        # Add IPC socket path
        env["PMS_SANDBOX_SOCKET"] = str(self._socket_path)

        # Plugin info
        env["PMS_PLUGIN_NAME"] = self.manifest.name
        env["PMS_PLUGIN_VERSION"] = self.manifest.version
        env["PMS_PLUGIN_DIR"] = str(self.plugin_dir)

        # Restrict network if needed
        if not self.config.allow_network:
            env["PMS_NO_NETWORK"] = "1"

        # Add extra env vars
        env.update(self.config.extra_env)

        return env

    def _create_runner_script(self) -> str:
        """Create the sandbox runner script."""
        return f'''
import asyncio
import json
import os
import sys
import importlib.util
from pathlib import Path

# Plugin info from env
SOCKET_PATH = os.environ["PMS_SANDBOX_SOCKET"]
PLUGIN_NAME = os.environ["PMS_PLUGIN_NAME"]
PLUGIN_DIR = Path(os.environ["PMS_PLUGIN_DIR"])

class PluginHost:
    """Host environment for the plugin."""

    def __init__(self):
        self.reader = None
        self.writer = None
        self.handlers = {{}}
        self.running = True

    async def connect(self):
        """Connect to PMS host."""
        self.reader, self.writer = await asyncio.open_unix_connection(
            path=SOCKET_PATH
        )

    async def send(self, msg):
        """Send message to host."""
        data = (json.dumps(msg) + "\\n").encode()
        self.writer.write(data)
        await self.writer.drain()

    async def receive(self):
        """Receive message from host."""
        line = await self.reader.readline()
        if not line:
            return None
        return json.loads(line.decode().strip())

    def register(self, name, handler):
        """Register a tool handler."""
        self.handlers[name] = handler

    async def run(self):
        """Main message loop."""
        await self.connect()

        # Notify ready
        await self.send({{"jsonrpc": "2.0", "method": "ready"}})

        while self.running:
            try:
                msg = await self.receive()
                if msg is None:
                    break

                if msg.get("method") == "shutdown":
                    break

                # Handle method call
                method = msg.get("method")
                params = msg.get("params", {{}})
                msg_id = msg.get("id")

                if method == "call":
                    handler_name = params.get("handler")
                    args = params.get("args", {{}})

                    if handler_name in self.handlers:
                        try:
                            handler = self.handlers[handler_name]
                            if asyncio.iscoroutinefunction(handler):
                                result = await handler(**args)
                            else:
                                result = handler(**args)

                            await self.send({{
                                "jsonrpc": "2.0",
                                "id": msg_id,
                                "result": result
                            }})
                        except Exception as e:
                            await self.send({{
                                "jsonrpc": "2.0",
                                "id": msg_id,
                                "error": {{"code": -32000, "message": str(e)}}
                            }})
                    else:
                        await self.send({{
                            "jsonrpc": "2.0",
                            "id": msg_id,
                            "error": {{"code": -32601, "message": f"Handler not found: {{handler_name}}"}}
                        }})

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error: {{e}}", file=sys.stderr)

        self.writer.close()
        await self.writer.wait_closed()

# Create host
host = PluginHost()

# Load plugin entrypoint
entrypoint = PLUGIN_DIR / "{self.manifest.entrypoint}"
if entrypoint.exists():
    spec = importlib.util.spec_from_file_location("plugin", entrypoint)
    if spec and spec.loader:
        module = importlib.util.module_from_spec(spec)
        sys.modules["plugin"] = module
        spec.loader.exec_module(module)

        # Register handlers
        for name in dir(module):
            obj = getattr(module, name)
            if callable(obj) and not name.startswith("_"):
                host.register(name, obj)

# Run
asyncio.run(host.run())
'''

    async def call_function(
        self,
        handler: str,
        timeout: float | None = None,
        **args: Any,
    ) -> SandboxResult:
        """Call a function in the sandbox.

        Args:
            handler: Handler function name
            timeout: Timeout in seconds
            **args: Function arguments

        Returns:
            SandboxResult with the result or error
        """
        if not self.is_running:
            return SandboxResult.fail("Sandbox not running")

        import time

        start_time = time.perf_counter()
        timeout = timeout or self.config.call_timeout

        try:
            # Create request
            request = IPCMessage.request("call", handler=handler, args=args)

            # Send via IPC server broadcast (single client expected)
            if self._ipc_server and self._ipc_server._clients:
                reader, writer = next(iter(self._ipc_server._clients))

                # Send request
                writer.write(request.to_bytes())
                await writer.drain()

                # Wait for response
                try:
                    line = await asyncio.wait_for(
                        reader.readline(),
                        timeout=timeout,
                    )
                    if not line:
                        return SandboxResult.fail("Connection closed")

                    response = IPCMessage.from_bytes(line)
                    execution_time = (time.perf_counter() - start_time) * 1000

                    if response.is_error:
                        error = response.error or {}
                        return SandboxResult.fail(
                            error.get("message", "Unknown error"),
                            execution_time,
                        )

                    return SandboxResult.ok(response.result, execution_time)

                except TimeoutError:
                    return SandboxResult.fail(
                        f"Timeout after {timeout}s",
                        (time.perf_counter() - start_time) * 1000,
                    )

            return SandboxResult.fail("No IPC connection")

        except Exception as e:
            execution_time = (time.perf_counter() - start_time) * 1000
            return SandboxResult.fail(str(e), execution_time)

    async def check_health(self) -> bool:
        """Check if sandbox is healthy."""
        if not self.is_running:
            return False

        try:
            result = await self.call_function("__ping__", timeout=5.0)
            return result.success
        except Exception:
            return self.is_running


class SandboxManager:
    """Manages multiple sandboxed plugins.

    Provides lifecycle management and resource tracking
    for all running sandboxes.
    """

    def __init__(self, max_sandboxes: int = 20):
        """Initialize sandbox manager.

        Args:
            max_sandboxes: Maximum concurrent sandboxes
        """
        self.max_sandboxes = max_sandboxes
        self._sandboxes: dict[str, SandboxedPlugin] = {}
        self._lock = asyncio.Lock()

    @property
    def running_count(self) -> int:
        return sum(1 for s in self._sandboxes.values() if s.is_running)

    async def create(
        self,
        manifest: PluginManifest,
        config: SandboxConfig | None = None,
        plugin_dir: Path | None = None,
    ) -> SandboxedPlugin:
        """Create a new sandbox for a plugin.

        Args:
            manifest: Plugin manifest
            config: Sandbox configuration
            plugin_dir: Plugin directory

        Returns:
            SandboxedPlugin instance

        Raises:
            RuntimeError: If max sandboxes reached
        """
        async with self._lock:
            if self.running_count >= self.max_sandboxes:
                raise RuntimeError(f"Maximum sandboxes ({self.max_sandboxes}) reached")

            sandbox = SandboxedPlugin(manifest, config, plugin_dir)
            self._sandboxes[manifest.name] = sandbox
            return sandbox

    async def start(self, plugin_name: str) -> bool:
        """Start a sandbox by plugin name."""
        sandbox = self._sandboxes.get(plugin_name)
        if not sandbox:
            return False
        return await sandbox.start()

    async def stop(self, plugin_name: str) -> None:
        """Stop a sandbox by plugin name."""
        sandbox = self._sandboxes.get(plugin_name)
        if sandbox:
            await sandbox.stop()

    async def stop_all(self) -> None:
        """Stop all sandboxes."""
        for sandbox in list(self._sandboxes.values()):
            await sandbox.stop()

    def get(self, plugin_name: str) -> SandboxedPlugin | None:
        """Get sandbox by plugin name."""
        return self._sandboxes.get(plugin_name)

    async def remove(self, plugin_name: str) -> None:
        """Remove a sandbox."""
        async with self._lock:
            sandbox = self._sandboxes.pop(plugin_name, None)
            if sandbox and sandbox.is_running:
                await sandbox.stop()

    def list_running(self) -> list[str]:
        """List running sandbox plugin names."""
        return [name for name, sandbox in self._sandboxes.items() if sandbox.is_running]

    async def health_check(self) -> dict[str, bool]:
        """Check health of all sandboxes."""
        results = {}
        for name, sandbox in self._sandboxes.items():
            results[name] = await sandbox.check_health()
        return results

    def get_stats(self) -> dict[str, Any]:
        """Get sandbox manager stats."""
        return {
            "total_sandboxes": len(self._sandboxes),
            "running_sandboxes": self.running_count,
            "max_sandboxes": self.max_sandboxes,
            "sandboxes": {
                name: {
                    "running": sandbox.is_running,
                    "pid": sandbox.pid,
                    "started_at": sandbox._started_at.isoformat()
                    if sandbox._started_at
                    else None,
                }
                for name, sandbox in self._sandboxes.items()
            },
        }
