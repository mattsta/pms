"""Plugin Registry - Central management for all plugins.

The registry handles:
- Plugin discovery from filesystem
- Plugin loading and unloading
- Lifecycle management
- Tool registration with PMS
- Event hook subscription
- Hot-reload support

Usage:
    from pms.plugins import get_plugin_registry

    registry = get_plugin_registry()

    # Discover plugins
    await registry.discover("~/.pms/plugins")

    # Load all discovered plugins
    await registry.load_all()

    # Call a plugin tool
    result = await registry.call_tool("github.list_repos", org="my-org")

    # List all available tools
    tools = registry.list_tools()
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pms.plugins.dsl import DSLCompiler, DSLParser, ToolDefinition
from pms.plugins.lifecycle import PluginLifecycle, PluginState
from pms.plugins.manifest import PluginManifest, PluginTool
from pms.plugins.sandbox import SandboxedPlugin, SandboxManager

logger = logging.getLogger(__name__)


@dataclass
class PluginInfo:
    """Information about a registered plugin."""

    manifest: PluginManifest
    lifecycle: PluginLifecycle
    sandbox: SandboxedPlugin | None = None
    discovered_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    enabled: bool = True
    config: dict[str, Any] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def version(self) -> str:
        return self.manifest.version

    @property
    def state(self) -> PluginState:
        return self.lifecycle.state

    @property
    def is_running(self) -> bool:
        return self.lifecycle.is_running

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.manifest.description,
            "state": self.state.value,
            "enabled": self.enabled,
            "tools": [t.name for t in self.manifest.tools],
            "hooks": [h.event for h in self.manifest.hooks],
            "discovered_at": self.discovered_at.isoformat(),
        }


@dataclass
class RegisteredTool:
    """A tool registered from a plugin."""

    name: str
    plugin_name: str
    description: str
    handler: Callable[..., Any] | None = None
    tool_def: PluginTool | None = None
    dsl_def: ToolDefinition | None = None

    @property
    def full_name(self) -> str:
        """Get namespaced tool name."""
        return f"{self.plugin_name}.{self.name}"


class PluginRegistry:
    """Central registry for all plugins.

    Manages plugin lifecycle, tool registration, and hook subscription.
    """

    def __init__(
        self,
        plugin_dirs: list[Path] | None = None,
        sandbox_manager: SandboxManager | None = None,
    ):
        """Initialize plugin registry.

        Args:
            plugin_dirs: Directories to search for plugins
            sandbox_manager: Manager for sandboxed execution
        """
        self._plugins: dict[str, PluginInfo] = {}
        self._tools: dict[str, RegisteredTool] = {}
        self._hooks: dict[
            str, list[tuple[str, Callable[..., Any]]]
        ] = {}  # event -> [(plugin, handler)]
        self._plugin_dirs = plugin_dirs or []
        self._sandbox_manager = sandbox_manager or SandboxManager()
        self._dsl_parser = DSLParser()
        self._dsl_compiler = DSLCompiler()
        self._listeners: list[Callable[[str, PluginInfo], None]] = []
        self._lock = asyncio.Lock()

    # =========================================================================
    # Discovery
    # =========================================================================

    async def discover(self, path: Path | str) -> list[str]:
        """Discover plugins in a directory.

        Args:
            path: Directory to search

        Returns:
            List of discovered plugin names
        """
        path = Path(path).expanduser()
        if not path.exists():
            logger.warning(f"Plugin directory does not exist: {path}")
            return []

        discovered = []

        # Look for plugin manifests
        for manifest_path in path.rglob("plugin.json"):
            try:
                manifest = PluginManifest.from_file(manifest_path)

                if manifest.name in self._plugins:
                    logger.info(f"Plugin {manifest.name} already registered, skipping")
                    continue

                # Create lifecycle manager
                lifecycle = PluginLifecycle(manifest)

                # Create plugin info
                info = PluginInfo(
                    manifest=manifest,
                    lifecycle=lifecycle,
                )

                async with self._lock:
                    self._plugins[manifest.name] = info

                discovered.append(manifest.name)
                logger.info(f"Discovered plugin: {manifest.name} at {manifest_path}")

            except Exception as e:
                logger.error(f"Failed to load manifest {manifest_path}: {e}")

        # Also look for YAML manifests
        for manifest_path in path.rglob("plugin.yaml"):
            try:
                manifest = PluginManifest.from_file(manifest_path)

                if manifest.name not in self._plugins:
                    lifecycle = PluginLifecycle(manifest)
                    info = PluginInfo(manifest=manifest, lifecycle=lifecycle)

                    async with self._lock:
                        self._plugins[manifest.name] = info

                    discovered.append(manifest.name)

            except Exception as e:
                logger.error(f"Failed to load manifest {manifest_path}: {e}")

        # Look for DSL tool files
        for dsl_path in path.rglob("*.tools"):
            try:
                await self._load_dsl_tools(dsl_path)
            except Exception as e:
                logger.error(f"Failed to load DSL tools {dsl_path}: {e}")

        return discovered

    async def _load_dsl_tools(self, path: Path) -> list[str]:
        """Load tools from DSL file.

        Args:
            path: Path to .tools file

        Returns:
            List of registered tool names
        """
        content = path.read_text()
        tools = self._dsl_parser.parse(content)
        registered = []

        # Create a virtual plugin for DSL tools
        plugin_name = path.stem

        for tool in tools:
            handler = self._dsl_compiler.compile(tool)
            full_name = f"{plugin_name}.{tool.name}"

            self._tools[full_name] = RegisteredTool(
                name=tool.name,
                plugin_name=plugin_name,
                description=tool.description,
                handler=handler,
                dsl_def=tool,
            )
            registered.append(full_name)
            logger.info(f"Registered DSL tool: {full_name}")

        return registered

    # =========================================================================
    # Registration
    # =========================================================================

    async def register(
        self,
        manifest: PluginManifest,
        config: dict[str, Any] | None = None,
    ) -> PluginInfo:
        """Register a plugin from manifest.

        Args:
            manifest: Plugin manifest
            config: Plugin configuration

        Returns:
            PluginInfo for registered plugin
        """
        async with self._lock:
            if manifest.name in self._plugins:
                raise ValueError(f"Plugin {manifest.name} already registered")

            lifecycle = PluginLifecycle(manifest)
            info = PluginInfo(
                manifest=manifest,
                lifecycle=lifecycle,
                config=config or {},
            )

            self._plugins[manifest.name] = info
            self._notify_listeners("registered", info)

            logger.info(f"Registered plugin: {manifest.name}")
            return info

    async def unregister(self, plugin_name: str) -> bool:
        """Unregister a plugin.

        Args:
            plugin_name: Name of plugin to unregister

        Returns:
            True if unregistered successfully
        """
        async with self._lock:
            info = self._plugins.get(plugin_name)
            if not info:
                return False

            # Stop if running
            if info.is_running:
                await self.stop(plugin_name)

            # Remove tools
            tools_to_remove = [
                name
                for name, tool in self._tools.items()
                if tool.plugin_name == plugin_name
            ]
            for tool_name in tools_to_remove:
                del self._tools[tool_name]

            # Remove hooks
            for event in list(self._hooks.keys()):
                self._hooks[event] = [
                    (p, h) for p, h in self._hooks[event] if p != plugin_name
                ]

            del self._plugins[plugin_name]
            self._notify_listeners("unregistered", info)

            logger.info(f"Unregistered plugin: {plugin_name}")
            return True

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def load(self, plugin_name: str) -> bool:
        """Load a discovered plugin.

        Args:
            plugin_name: Name of plugin to load

        Returns:
            True if loaded successfully
        """
        info = self._plugins.get(plugin_name)
        if not info:
            logger.error(f"Plugin not found: {plugin_name}")
            return False

        return await info.lifecycle.load()

    async def load_all(self) -> dict[str, bool]:
        """Load all discovered plugins.

        Returns:
            Dict mapping plugin name to load success
        """
        results = {}
        for name in list(self._plugins.keys()):
            results[name] = await self.load(name)
        return results

    async def initialize(
        self,
        plugin_name: str,
        config: dict[str, Any] | None = None,
    ) -> bool:
        """Initialize a loaded plugin.

        Args:
            plugin_name: Name of plugin
            config: Plugin configuration

        Returns:
            True if initialized successfully
        """
        info = self._plugins.get(plugin_name)
        if not info:
            return False

        if info.state != PluginState.LOADED:
            logger.error(f"Plugin {plugin_name} not in LOADED state")
            return False

        # Create sandbox if needed
        if info.manifest.requires_sandbox:
            try:
                sandbox = await self._sandbox_manager.create(
                    info.manifest,
                    plugin_dir=info.manifest.path.parent
                    if info.manifest.path
                    else None,
                )
                info.sandbox = sandbox
                info.lifecycle.sandbox = sandbox

                # Start sandbox
                if not await sandbox.start():
                    logger.error(f"Failed to start sandbox for {plugin_name}")
                    return False

            except Exception as e:
                logger.error(f"Failed to create sandbox for {plugin_name}: {e}")
                return False

        # Update config
        if config:
            info.config.update(config)

        return await info.lifecycle.initialize(info.config)

    async def start(self, plugin_name: str) -> bool:
        """Start an initialized plugin.

        Args:
            plugin_name: Name of plugin

        Returns:
            True if started successfully
        """
        info = self._plugins.get(plugin_name)
        if not info:
            return False

        if not await info.lifecycle.start():
            return False

        # Register tools
        for tool in info.manifest.tools:
            self._register_plugin_tool(info, tool)

        # Register hooks
        for hook in info.manifest.hooks:
            self._register_plugin_hook(info, hook)

        self._notify_listeners("started", info)
        return True

    async def stop(self, plugin_name: str) -> bool:
        """Stop a running plugin.

        Args:
            plugin_name: Name of plugin

        Returns:
            True if stopped successfully
        """
        info = self._plugins.get(plugin_name)
        if not info:
            return False

        result = await info.lifecycle.stop()

        # Stop sandbox
        if info.sandbox:
            await info.sandbox.stop()

        self._notify_listeners("stopped", info)
        return result

    async def restart(self, plugin_name: str) -> bool:
        """Restart a plugin (hot-reload).

        Args:
            plugin_name: Name of plugin

        Returns:
            True if restarted successfully
        """
        info = self._plugins.get(plugin_name)
        if not info:
            return False

        # Reload manifest if path available
        if info.manifest.path and info.manifest.path.exists():
            try:
                new_manifest = PluginManifest.from_file(info.manifest.path)
                info.manifest = new_manifest
                info.lifecycle.manifest = new_manifest
            except Exception as e:
                logger.error(f"Failed to reload manifest: {e}")

        return await info.lifecycle.restart()

    async def start_all(self) -> dict[str, bool]:
        """Start all plugins (load, init, start).

        Returns:
            Dict mapping plugin name to success
        """
        results = {}

        for name, info in list(self._plugins.items()):
            while True:
                match info.state:
                    case PluginState.DISCOVERED:
                        if not await self.load(name):
                            results[name] = False
                            break
                    case PluginState.LOADED:
                        if not await self.initialize(name):
                            results[name] = False
                            break
                    case PluginState.INITIALIZED:
                        results[name] = await self.start(name)
                        break
                    case _:
                        results[name] = info.is_running
                        break

        return results

    async def stop_all(self) -> None:
        """Stop all running plugins."""
        for name, info in list(self._plugins.items()):
            if info.is_running:
                await self.stop(name)

        # Stop sandbox manager
        await self._sandbox_manager.stop_all()

    # =========================================================================
    # Tool Registration
    # =========================================================================

    def _register_plugin_tool(self, info: PluginInfo, tool: PluginTool) -> None:
        """Register a tool from a plugin."""
        full_name = f"{info.name}.{tool.name}"

        self._tools[full_name] = RegisteredTool(
            name=tool.name,
            plugin_name=info.name,
            description=tool.description,
            tool_def=tool,
        )

        logger.debug(f"Registered tool: {full_name}")

    def _register_plugin_hook(self, info: PluginInfo, hook: Any) -> None:
        """Register a hook from a plugin."""
        if hook.event not in self._hooks:
            self._hooks[hook.event] = []

        # Create hook handler
        async def hook_handler(**data: Any) -> Any:
            if info.sandbox:
                result = await info.sandbox.call_function(
                    hook.handler,
                    **data,
                )
                return result.value if result.success else None
            return None

        self._hooks[hook.event].append((info.name, hook_handler))
        logger.debug(f"Registered hook: {info.name} -> {hook.event}")

    # =========================================================================
    # Tool Execution
    # =========================================================================

    async def call_tool(
        self,
        tool_name: str,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> Any:
        """Call a registered tool.

        Args:
            tool_name: Full tool name (plugin.tool)
            timeout: Timeout in seconds
            **kwargs: Tool arguments

        Returns:
            Tool result

        Raises:
            ValueError: If tool not found
            RuntimeError: If plugin not running
        """
        tool = self._tools.get(tool_name)
        if not tool:
            raise ValueError(f"Tool not found: {tool_name}")

        # DSL-compiled tool
        if tool.handler:
            return await tool.handler(**kwargs)

        # Plugin tool
        info = self._plugins.get(tool.plugin_name)
        if not info:
            raise RuntimeError(f"Plugin not found: {tool.plugin_name}")

        if not info.is_running:
            raise RuntimeError(f"Plugin not running: {tool.plugin_name}")

        return await info.lifecycle.call_tool(tool.name, **kwargs)

    def list_tools(self, plugin_name: str | None = None) -> list[RegisteredTool]:
        """List registered tools.

        Args:
            plugin_name: Optional filter by plugin

        Returns:
            List of registered tools
        """
        if plugin_name:
            return [t for t in self._tools.values() if t.plugin_name == plugin_name]
        return list(self._tools.values())

    # =========================================================================
    # Event Hooks
    # =========================================================================

    async def emit_event(self, event: str, **data: Any) -> list[Any]:
        """Emit an event to all subscribed hooks.

        Args:
            event: Event name
            **data: Event data

        Returns:
            List of hook results
        """
        handlers = self._hooks.get(event, [])
        results = []

        for plugin_name, handler in handlers:
            try:
                result = await handler(**data)
                results.append(result)
            except Exception as e:
                logger.error(f"Hook error ({plugin_name}:{event}): {e}")

        return results

    # =========================================================================
    # Query
    # =========================================================================

    def get(self, plugin_name: str) -> PluginInfo | None:
        """Get plugin info by name."""
        return self._plugins.get(plugin_name)

    def list_plugins(
        self,
        state: PluginState | None = None,
        enabled_only: bool = False,
    ) -> list[PluginInfo]:
        """List registered plugins.

        Args:
            state: Optional filter by state
            enabled_only: Only return enabled plugins

        Returns:
            List of plugin info
        """
        plugins = list(self._plugins.values())

        if state:
            plugins = [p for p in plugins if p.state == state]

        if enabled_only:
            plugins = [p for p in plugins if p.enabled]

        return plugins

    def get_stats(self) -> dict[str, Any]:
        """Get registry statistics."""
        plugins_by_state: dict[str, int] = {}
        for info in self._plugins.values():
            state = info.state.value
            plugins_by_state[state] = plugins_by_state.get(state, 0) + 1

        return {
            "total_plugins": len(self._plugins),
            "total_tools": len(self._tools),
            "total_hooks": sum(len(h) for h in self._hooks.values()),
            "plugins_by_state": plugins_by_state,
            "sandbox_stats": self._sandbox_manager.get_stats(),
        }

    # =========================================================================
    # Listeners
    # =========================================================================

    def add_listener(self, listener: Callable[[str, PluginInfo], None]) -> None:
        """Add registry change listener."""
        self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[str, PluginInfo], None]) -> None:
        """Remove registry change listener."""
        if listener in self._listeners:
            self._listeners.remove(listener)

    def _notify_listeners(self, event: str, info: PluginInfo) -> None:
        """Notify all listeners of a change."""
        for listener in self._listeners:
            try:
                listener(event, info)
            except Exception as e:
                logger.error(f"Listener error: {e}")


# Global registry instance
_registry: PluginRegistry | None = None


def get_plugin_registry() -> PluginRegistry:
    """Get global plugin registry."""
    global _registry
    if _registry is None:
        _registry = PluginRegistry()
    return _registry


def set_plugin_registry(registry: PluginRegistry) -> None:
    """Set global plugin registry."""
    global _registry
    _registry = registry
