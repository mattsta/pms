"""Plugin Lifecycle Management.

Manages plugin states and transitions through the lifecycle:
    DISCOVERED -> LOADED -> INITIALIZED -> RUNNING -> STOPPED

State Diagram:
    ┌──────────────┐
    │  DISCOVERED  │ <- discover()
    └──────┬───────┘
           │ load()
    ┌──────▼───────┐
    │    LOADED    │ <- validate & parse
    └──────┬───────┘
           │ initialize()
    ┌──────▼───────┐
    │ INITIALIZED  │ <- run on_load hook
    └──────┬───────┘
           │ start()
    ┌──────▼───────┐
    │   RUNNING    │ <- ready for tool calls
    └──────┬───────┘
           │ stop()
    ┌──────▼───────┐
    │   STOPPED    │ <- run on_unload hook
    └──────────────┘

Error handling:
    Any state can transition to ERROR state on failure.
    From ERROR, can retry or unload completely.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pms.plugins.manifest import PluginManifest
    from pms.plugins.sandbox import SandboxedPlugin

logger = logging.getLogger(__name__)


class PluginState(Enum):
    """Plugin lifecycle states."""

    DISCOVERED = "discovered"  # Found but not loaded
    LOADING = "loading"  # Currently loading
    LOADED = "loaded"  # Manifest parsed and validated
    INITIALIZING = "initializing"  # Running initialization
    INITIALIZED = "initialized"  # Ready to start
    STARTING = "starting"  # Starting up
    RUNNING = "running"  # Fully operational
    STOPPING = "stopping"  # Shutting down
    STOPPED = "stopped"  # Clean shutdown
    ERROR = "error"  # Error state
    DISABLED = "disabled"  # Manually disabled


@dataclass
class PluginEvent:
    """Event emitted during lifecycle transitions."""

    plugin_name: str
    event_type: str  # state_changed, error, tool_called, etc.
    from_state: PluginState | None
    to_state: PluginState | None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


LifecycleListener = Callable[[PluginEvent], None]


@dataclass
class PluginStats:
    """Runtime statistics for a plugin."""

    tool_calls: int = 0
    tool_errors: int = 0
    hook_calls: int = 0
    hook_errors: int = 0
    total_execution_time_ms: float = 0.0
    last_activity: datetime | None = None
    memory_usage_mb: float = 0.0
    restarts: int = 0

    def record_tool_call(self, duration_ms: float, success: bool = True) -> None:
        """Record a tool call."""
        self.tool_calls += 1
        if not success:
            self.tool_errors += 1
        self.total_execution_time_ms += duration_ms
        self.last_activity = datetime.now(UTC)

    def record_hook_call(self, success: bool = True) -> None:
        """Record a hook call."""
        self.hook_calls += 1
        if not success:
            self.hook_errors += 1
        self.last_activity = datetime.now(UTC)

    @property
    def error_rate(self) -> float:
        """Calculate error rate."""
        total = self.tool_calls + self.hook_calls
        if total == 0:
            return 0.0
        errors = self.tool_errors + self.hook_errors
        return errors / total

    @property
    def avg_execution_time_ms(self) -> float:
        """Calculate average execution time."""
        if self.tool_calls == 0:
            return 0.0
        return self.total_execution_time_ms / self.tool_calls


class PluginLifecycle:
    """Manages lifecycle for a single plugin.

    Handles state transitions, initialization, and shutdown.
    """

    # Valid state transitions
    TRANSITIONS = {
        PluginState.DISCOVERED: {PluginState.LOADING, PluginState.ERROR},
        PluginState.LOADING: {PluginState.LOADED, PluginState.ERROR},
        PluginState.LOADED: {
            PluginState.INITIALIZING,
            PluginState.ERROR,
            PluginState.DISABLED,
        },
        PluginState.INITIALIZING: {PluginState.INITIALIZED, PluginState.ERROR},
        PluginState.INITIALIZED: {
            PluginState.STARTING,
            PluginState.ERROR,
            PluginState.DISABLED,
        },
        PluginState.STARTING: {PluginState.RUNNING, PluginState.ERROR},
        PluginState.RUNNING: {
            PluginState.STOPPING,
            PluginState.ERROR,
            PluginState.DISABLED,
        },
        PluginState.STOPPING: {PluginState.STOPPED, PluginState.ERROR},
        PluginState.STOPPED: {PluginState.LOADING, PluginState.DISCOVERED},
        PluginState.ERROR: {
            PluginState.LOADING,
            PluginState.STOPPED,
            PluginState.DISABLED,
        },
        PluginState.DISABLED: {PluginState.LOADING, PluginState.STOPPED},
    }

    def __init__(
        self,
        manifest: PluginManifest,
        sandbox: SandboxedPlugin | None = None,
    ):
        """Initialize lifecycle manager.

        Args:
            manifest: Plugin manifest
            sandbox: Optional sandboxed plugin instance
        """
        self.manifest = manifest
        self.sandbox = sandbox
        self._state = PluginState.DISCOVERED
        self._state_history: list[tuple[PluginState, datetime]] = [
            (PluginState.DISCOVERED, datetime.now(UTC))
        ]
        self._listeners: list[LifecycleListener] = []
        self._error: str | None = None
        self._config: dict[str, Any] = {}
        self.stats = PluginStats()

    @property
    def state(self) -> PluginState:
        """Get current state."""
        return self._state

    @property
    def is_running(self) -> bool:
        """Check if plugin is running."""
        return self._state == PluginState.RUNNING

    @property
    def is_error(self) -> bool:
        """Check if plugin is in error state."""
        return self._state == PluginState.ERROR

    @property
    def error(self) -> str | None:
        """Get current error message."""
        return self._error

    @property
    def uptime(self) -> float | None:
        """Get uptime in seconds if running."""
        if self._state != PluginState.RUNNING:
            return None

        # Find when we entered RUNNING state
        for state, timestamp in reversed(self._state_history):
            if state == PluginState.RUNNING:
                return (datetime.now(UTC) - timestamp).total_seconds()
        return None

    def add_listener(self, listener: LifecycleListener) -> None:
        """Add lifecycle event listener."""
        self._listeners.append(listener)

    def remove_listener(self, listener: LifecycleListener) -> None:
        """Remove lifecycle event listener."""
        if listener in self._listeners:
            self._listeners.remove(listener)

    def _emit_event(
        self,
        event_type: str,
        from_state: PluginState | None = None,
        to_state: PluginState | None = None,
        data: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        """Emit a lifecycle event."""
        event = PluginEvent(
            plugin_name=self.manifest.name,
            event_type=event_type,
            from_state=from_state,
            to_state=to_state,
            data=data or {},
            error=error,
        )

        for listener in self._listeners:
            try:
                listener(event)
            except Exception as e:
                logger.error(f"Listener error: {e}")

    def _can_transition(self, to_state: PluginState) -> bool:
        """Check if transition is valid."""
        return to_state in self.TRANSITIONS.get(self._state, set())

    def _transition(self, to_state: PluginState, error: str | None = None) -> bool:
        """Perform state transition.

        Args:
            to_state: Target state
            error: Error message if transitioning to ERROR

        Returns:
            True if transition successful
        """
        if not self._can_transition(to_state):
            logger.warning(
                f"Invalid transition {self._state} -> {to_state} for {self.manifest.name}"
            )
            return False

        from_state = self._state
        self._state = to_state
        self._state_history.append((to_state, datetime.now(UTC)))

        if to_state == PluginState.ERROR:
            self._error = error
        else:
            self._error = None

        self._emit_event(
            event_type="state_changed",
            from_state=from_state,
            to_state=to_state,
            error=error,
        )

        logger.info(
            f"Plugin {self.manifest.name}: {from_state.value} -> {to_state.value}"
        )
        return True

    async def load(self) -> bool:
        """Load plugin (parse manifest, validate).

        Returns:
            True if loaded successfully
        """
        if not self._transition(PluginState.LOADING):
            return False

        try:
            # Validate manifest
            errors = self.manifest.validate()
            if errors:
                self._transition(PluginState.ERROR, f"Validation errors: {errors}")
                return False

            self._transition(PluginState.LOADED)
            return True

        except Exception as e:
            self._transition(PluginState.ERROR, str(e))
            return False

    async def initialize(self, config: dict[str, Any] | None = None) -> bool:
        """Initialize plugin (run on_load hook).

        Args:
            config: Plugin configuration

        Returns:
            True if initialized successfully
        """
        if not self._transition(PluginState.INITIALIZING):
            return False

        self._config = config or {}

        try:
            # Run on_load hook if sandbox is available
            if self.sandbox and self.manifest.on_load:
                result = await self.sandbox.call_function(
                    self.manifest.on_load,
                    config=self._config,
                )
                if not result.success:
                    self._transition(PluginState.ERROR, result.error)
                    return False

            self._transition(PluginState.INITIALIZED)
            return True

        except Exception as e:
            self._transition(PluginState.ERROR, str(e))
            return False

    async def start(self) -> bool:
        """Start plugin (make tools available).

        Returns:
            True if started successfully
        """
        if not self._transition(PluginState.STARTING):
            return False

        try:
            # Run on_enable hook
            if self.sandbox and self.manifest.on_enable:
                result = await self.sandbox.call_function(self.manifest.on_enable)
                if not result.success:
                    self._transition(PluginState.ERROR, result.error)
                    return False

            self._transition(PluginState.RUNNING)
            return True

        except Exception as e:
            self._transition(PluginState.ERROR, str(e))
            return False

    async def stop(self) -> bool:
        """Stop plugin gracefully.

        Returns:
            True if stopped successfully
        """
        if not self._transition(PluginState.STOPPING):
            return False

        try:
            # Run on_disable hook
            if self.sandbox and self.manifest.on_disable:
                try:
                    await asyncio.wait_for(
                        self.sandbox.call_function(self.manifest.on_disable),
                        timeout=5.0,
                    )
                except TimeoutError:
                    logger.warning(f"Plugin {self.manifest.name} on_disable timed out")

            # Run on_unload hook
            if self.sandbox and self.manifest.on_unload:
                try:
                    await asyncio.wait_for(
                        self.sandbox.call_function(self.manifest.on_unload),
                        timeout=5.0,
                    )
                except TimeoutError:
                    logger.warning(f"Plugin {self.manifest.name} on_unload timed out")

            self._transition(PluginState.STOPPED)
            return True

        except Exception as e:
            logger.error(f"Error stopping plugin {self.manifest.name}: {e}")
            self._transition(PluginState.ERROR, str(e))
            return False

    async def disable(self) -> bool:
        """Disable plugin (stop if running, prevent future starts).

        Returns:
            True if disabled successfully
        """
        if self._state == PluginState.RUNNING:
            await self.stop()

        return self._transition(PluginState.DISABLED)

    async def enable(self) -> bool:
        """Enable a disabled plugin.

        Returns:
            True if enabled successfully
        """
        if self._state != PluginState.DISABLED:
            return False

        # Transition back to LOADING and reinitialize
        self._transition(PluginState.LOADING)
        self._transition(PluginState.LOADED)
        return True

    async def restart(self) -> bool:
        """Restart plugin.

        Returns:
            True if restarted successfully
        """
        self.stats.restarts += 1

        if self._state == PluginState.RUNNING:
            await self.stop()

        # Reset to DISCOVERED and reload
        self._state = PluginState.DISCOVERED
        self._state_history.append((PluginState.DISCOVERED, datetime.now(UTC)))

        if not await self.load():
            return False
        if not await self.initialize(self._config):
            return False
        return await self.start()

    async def call_tool(
        self,
        tool_name: str,
        **kwargs: Any,
    ) -> Any:
        """Call a plugin tool.

        Args:
            tool_name: Name of tool to call
            **kwargs: Tool arguments

        Returns:
            Tool result

        Raises:
            RuntimeError: If plugin not running
            ValueError: If tool not found
        """
        if self._state != PluginState.RUNNING:
            raise RuntimeError(f"Plugin {self.manifest.name} is not running")

        tool = self.manifest.get_tool(tool_name)
        if not tool:
            raise ValueError(f"Tool {tool_name} not found in {self.manifest.name}")

        if not self.sandbox:
            raise RuntimeError("No sandbox available for tool execution")

        import time

        start_time = time.perf_counter()

        try:
            result = await asyncio.wait_for(
                self.sandbox.call_function(tool.handler, **kwargs),
                timeout=tool.timeout,
            )

            duration_ms = (time.perf_counter() - start_time) * 1000
            self.stats.record_tool_call(duration_ms, result.success)

            if not result.success:
                raise RuntimeError(result.error)

            return result.value

        except TimeoutError:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self.stats.record_tool_call(duration_ms, success=False)
            raise RuntimeError(f"Tool {tool_name} timed out after {tool.timeout}s")

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self.stats.record_tool_call(duration_ms, success=False)
            raise

    def get_status(self) -> dict[str, Any]:
        """Get plugin status summary."""
        return {
            "name": self.manifest.name,
            "version": self.manifest.version,
            "state": self._state.value,
            "error": self._error,
            "uptime": self.uptime,
            "stats": {
                "tool_calls": self.stats.tool_calls,
                "tool_errors": self.stats.tool_errors,
                "hook_calls": self.stats.hook_calls,
                "error_rate": self.stats.error_rate,
                "avg_execution_time_ms": self.stats.avg_execution_time_ms,
                "restarts": self.stats.restarts,
            },
            "tools": [t.name for t in self.manifest.tools],
            "hooks": [h.event for h in self.manifest.hooks],
        }
