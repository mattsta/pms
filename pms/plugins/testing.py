"""Plugin Testing Framework.

This module provides utilities for testing plugins:
- Mock registry for isolated testing
- Test fixtures for common scenarios
- Assertions for plugin behavior
- Harness for running plugin tools

Usage:
    import pytest
    from pms.plugins.testing import PluginTestHarness, mock_registry

    @pytest.fixture
    def harness(tmp_path):
        return PluginTestHarness(tmp_path)

    @pytest.mark.asyncio
    async def test_my_plugin(harness):
        # Load plugin
        await harness.load_plugin("path/to/my-plugin")

        # Call tool
        result = await harness.call_tool("my-plugin.my_tool", arg1="value")

        # Assert
        assert result["status"] == "success"
        harness.assert_no_errors()
"""

import asyncio
import json
import sys
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .lifecycle import PluginLifecycle, PluginState
from .manifest import PluginManifest, PluginType

# =============================================================================
# Mock Registry
# =============================================================================


@dataclass
class MockTool:
    """Mock tool for testing."""

    name: str
    plugin: str
    handler: Callable[..., Any] | None = None
    call_count: int = 0
    last_args: dict[str, Any] = field(default_factory=dict)
    mock_result: Any = None

    async def __call__(self, **kwargs: Any) -> Any:
        """Call the tool."""
        self.call_count += 1
        self.last_args = kwargs

        if self.handler:
            return await self.handler(**kwargs)
        elif self.mock_result is not None:
            return self.mock_result
        else:
            return {"status": "ok", "tool": self.name, "args": kwargs}


@dataclass
class MockPlugin:
    """Mock plugin for testing."""

    name: str
    manifest: PluginManifest
    state: PluginState = PluginState.DISCOVERED
    tools: dict[str, MockTool] = field(default_factory=dict)
    events_received: list[dict[str, Any]] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)

    def add_tool(
        self,
        name: str,
        handler: Callable[..., Any] | None = None,
        mock_result: Any = None,
    ) -> MockTool:
        """Add a mock tool."""
        tool = MockTool(
            name=name,
            plugin=self.name,
            handler=handler,
            mock_result=mock_result,
        )
        self.tools[name] = tool
        return tool


class MockRegistry:
    """Mock plugin registry for testing.

    Provides isolated testing without loading real plugins.
    """

    def __init__(self) -> None:
        self.plugins: dict[str, MockPlugin] = {}
        self.tools: dict[str, MockTool] = {}
        self.events: list[dict[str, Any]] = []
        self.hooks: dict[str, list[Callable[..., Any]]] = {}

    def add_plugin(
        self,
        name: str,
        tools: list[str] | None = None,
        manifest: PluginManifest | None = None,
    ) -> MockPlugin:
        """Add a mock plugin."""
        if manifest is None:
            manifest = PluginManifest(
                name=name,
                version="1.0.0",
                description=f"Mock plugin: {name}",
            )

        plugin = MockPlugin(name=name, manifest=manifest)

        for tool_name in tools or []:
            tool = plugin.add_tool(tool_name)
            self.tools[f"{name}.{tool_name}"] = tool

        self.plugins[name] = plugin
        return plugin

    def mock_tool(
        self,
        full_name: str,
        result: Any = None,
        handler: Callable[..., Any] | None = None,
    ) -> MockTool:
        """Set up a mock tool response."""
        if full_name not in self.tools:
            # Create plugin and tool if needed
            parts = full_name.split(".")
            if len(parts) == 2:
                plugin_name, tool_name = parts
                if plugin_name not in self.plugins:
                    self.add_plugin(plugin_name)
                tool = self.plugins[plugin_name].add_tool(
                    tool_name, handler=handler, mock_result=result
                )
                self.tools[full_name] = tool

        tool = self.tools[full_name]
        if result is not None:
            tool.mock_result = result
        if handler is not None:
            tool.handler = handler
        return tool

    async def call_tool(self, name: str, **kwargs: Any) -> Any:
        """Call a mock tool."""
        if name not in self.tools:
            raise ValueError(f"Tool not found: {name}")
        return await self.tools[name](**kwargs)

    def emit_event(self, event: str, **data: Any) -> None:
        """Emit an event to registered hooks."""
        event_data = {"event": event, "timestamp": datetime.now().isoformat(), **data}
        self.events.append(event_data)

        for handler in self.hooks.get(event, []):
            if asyncio.iscoroutinefunction(handler):
                asyncio.create_task(handler(**data))
            else:
                handler(**data)

    def register_hook(self, event: str, handler: Callable[..., Any]) -> None:
        """Register an event hook."""
        if event not in self.hooks:
            self.hooks[event] = []
        self.hooks[event].append(handler)

    def get_tool_calls(self, tool_name: str) -> list[dict[str, Any]]:
        """Get all calls made to a tool."""
        if tool_name in self.tools:
            tool = self.tools[tool_name]
            return [tool.last_args] if tool.call_count > 0 else []
        return []

    def assert_tool_called(self, tool_name: str, **expected_args: Any) -> None:
        """Assert a tool was called with specific arguments."""
        if tool_name not in self.tools:
            raise AssertionError(f"Tool not found: {tool_name}")

        tool = self.tools[tool_name]
        if tool.call_count == 0:
            raise AssertionError(f"Tool {tool_name} was never called")

        for key, value in expected_args.items():
            if key not in tool.last_args:
                raise AssertionError(
                    f"Tool {tool_name} was not called with arg '{key}'"
                )
            if tool.last_args[key] != value:
                raise AssertionError(
                    f"Tool {tool_name} arg '{key}' was {tool.last_args[key]!r}, "
                    f"expected {value!r}"
                )

    def assert_event_emitted(self, event: str, **expected_data: Any) -> None:
        """Assert an event was emitted."""
        matching = [e for e in self.events if e["event"] == event]
        if not matching:
            raise AssertionError(f"Event '{event}' was never emitted")

        for key, value in expected_data.items():
            found = False
            for e in matching:
                if e.get(key) == value:
                    found = True
                    break
            if not found:
                raise AssertionError(
                    f"Event '{event}' was not emitted with {key}={value!r}"
                )


# =============================================================================
# Test Harness
# =============================================================================


class PluginTestHarness:
    """Test harness for plugin development.

    Provides a controlled environment for testing plugins
    with mock capabilities and assertions.
    """

    def __init__(self, work_dir: Path | None = None):
        self.work_dir = work_dir or Path()
        self.registry = MockRegistry()
        self.loaded_plugins: dict[str, Any] = {}
        self.errors: list[str] = []
        self.outputs: list[str] = []
        self._original_modules: dict[str, Any] = {}

    async def load_plugin(
        self,
        plugin_path: str | Path,
        config: dict[str, Any] | None = None,
    ) -> MockPlugin:
        """Load a plugin for testing.

        Args:
            plugin_path: Path to plugin directory
            config: Optional configuration

        Returns:
            Loaded mock plugin
        """
        path = Path(plugin_path)

        # Load manifest
        manifest_path = path / "plugin.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"No plugin.json found at {path}")

        manifest = PluginManifest.from_file(manifest_path)

        # Create mock plugin
        plugin = self.registry.add_plugin(
            manifest.name,
            tools=[t.name for t in manifest.tools],
            manifest=manifest,
        )
        plugin.config = config or {}

        # Load Python module if exists
        main_path = path / manifest.entrypoint
        if main_path.exists():
            # Import the module
            import importlib.util

            spec = importlib.util.spec_from_file_location(
                f"plugin_{manifest.name}", main_path
            )
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[f"plugin_{manifest.name}"] = module
                spec.loader.exec_module(module)

                # Wire up tool handlers
                for tool in manifest.tools:
                    if hasattr(module, tool.name):
                        handler = getattr(module, tool.name)
                        full_name = f"{manifest.name}.{tool.name}"
                        self.registry.mock_tool(full_name, handler=handler)

                # Call on_load if exists
                if hasattr(module, "on_load"):
                    await module.on_load(config)

                self.loaded_plugins[manifest.name] = module

        plugin.state = PluginState.RUNNING
        return plugin

    async def call_tool(self, tool_name: str, **kwargs: Any) -> Any:
        """Call a plugin tool.

        Args:
            tool_name: Full tool name (plugin.tool)
            **kwargs: Tool arguments

        Returns:
            Tool result
        """
        try:
            result = await self.registry.call_tool(tool_name, **kwargs)
            return result
        except Exception as e:
            self.errors.append(f"Tool {tool_name} failed: {e}")
            raise

    def mock_tool_result(self, tool_name: str, result: Any) -> None:
        """Set a mock result for a tool."""
        self.registry.mock_tool(tool_name, result=result)

    def emit_event(self, event: str, **data: Any) -> None:
        """Emit a system event."""
        self.registry.emit_event(event, **data)

    def capture_output(self, text: str) -> None:
        """Capture plugin output."""
        self.outputs.append(text)

    def assert_no_errors(self) -> None:
        """Assert no errors occurred during testing."""
        if self.errors:
            raise AssertionError(f"Errors occurred: {self.errors}")

    def assert_tool_called(self, tool_name: str, **kwargs: Any) -> None:
        """Assert a tool was called with arguments."""
        self.registry.assert_tool_called(tool_name, **kwargs)

    def assert_output_contains(self, text: str) -> None:
        """Assert output contains text."""
        for output in self.outputs:
            if text in output:
                return
        raise AssertionError(f"Output does not contain: {text}")

    def get_tool_call_count(self, tool_name: str) -> int:
        """Get number of times a tool was called."""
        if tool_name in self.registry.tools:
            return self.registry.tools[tool_name].call_count
        return 0

    @asynccontextmanager
    async def plugin_context(
        self, plugin_path: str | Path, config: dict[str, Any] | None = None
    ) -> AsyncIterator[MockPlugin]:
        """Context manager for plugin lifecycle.

        Usage:
            async with harness.plugin_context("path/to/plugin") as plugin:
                result = await harness.call_tool("plugin.tool")
        """
        plugin = await self.load_plugin(plugin_path, config)
        try:
            yield plugin
        finally:
            # Call on_unload if exists
            if plugin.name in self.loaded_plugins:
                module = self.loaded_plugins[plugin.name]
                if hasattr(module, "on_unload"):
                    await module.on_unload()


# =============================================================================
# Test Fixtures Factory
# =============================================================================


def create_test_manifest(
    name: str = "test-plugin",
    tools: list[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> PluginManifest:
    """Create a test manifest.

    Args:
        name: Plugin name
        tools: Tool definitions
        **kwargs: Additional manifest fields

    Returns:
        Test manifest
    """
    from .manifest import PluginParameter, PluginTool

    manifest_tools = []
    for tool_def in tools or []:
        params = {}
        for pname, pinfo in tool_def.get("parameters", {}).items():
            if isinstance(pinfo, str):
                params[pname] = PluginParameter(name=pname, type=pinfo)
            else:
                params[pname] = PluginParameter(
                    name=pname,
                    type=pinfo.get("type", "string"),
                    required=pinfo.get("required", True),
                    default=pinfo.get("default"),
                )
        manifest_tools.append(
            PluginTool(
                name=tool_def["name"],
                description=tool_def.get("description", ""),
                parameters=params,
            )
        )

    return PluginManifest(
        name=name,
        version=kwargs.get("version", "1.0.0"),
        description=kwargs.get("description", f"Test plugin: {name}"),
        type=kwargs.get("type", PluginType.EXTENSION),
        tools=manifest_tools,
        capabilities=kwargs.get("capabilities", []),
    )


def create_test_plugin_dir(
    base_path: Path,
    name: str,
    tools: list[dict[str, Any]] | None = None,
    main_code: str | None = None,
) -> Path:
    """Create a test plugin directory.

    Args:
        base_path: Base directory
        name: Plugin name
        tools: Tool definitions
        main_code: Python code for main.py

    Returns:
        Path to created plugin directory
    """
    plugin_dir = base_path / name
    plugin_dir.mkdir(parents=True, exist_ok=True)

    # Create manifest
    manifest = create_test_manifest(name=name, tools=tools)
    manifest_data = {
        "name": manifest.name,
        "version": manifest.version,
        "description": manifest.description,
        "type": manifest.type.value,
        "entrypoint": "main.py",
        "tools": [
            {
                "name": t.name,
                "description": t.description,
                "parameters": {
                    p.name: {"type": p.type, "required": p.required}
                    for p in t.parameters.values()
                },
            }
            for t in manifest.tools
        ],
    }
    (plugin_dir / "plugin.json").write_text(json.dumps(manifest_data, indent=2))

    # Create main.py
    if main_code is None:
        # Generate default implementations
        tool_funcs = []
        for tool_def in tools or []:
            params = ", ".join(
                f"{p}: str = None" for p in tool_def.get("parameters", {})
            )
            tool_funcs.append(f'''
async def {tool_def["name"]}({params}) -> dict:
    """Generated test tool."""
    return {{"status": "ok", "tool": "{tool_def["name"]}"}}
''')
        main_code = (
            '''"""Test plugin."""
from typing import Any

'''
            + "\n".join(tool_funcs)
            + """

async def on_load(config: dict = None):
    pass

async def on_unload():
    pass
"""
        )

    (plugin_dir / "main.py").write_text(main_code)

    return plugin_dir


# =============================================================================
# Assertions
# =============================================================================


class PluginAssertions:
    """Additional assertions for plugin testing."""

    @staticmethod
    def assert_manifest_valid(manifest: PluginManifest) -> None:
        """Assert manifest is valid."""
        errors = manifest.validate()
        if errors:
            raise AssertionError(f"Manifest validation failed: {errors}")

    @staticmethod
    def assert_tool_result_success(result: dict[str, Any]) -> None:
        """Assert tool returned success."""
        if "error" in result:
            raise AssertionError(f"Tool returned error: {result['error']}")
        if result.get("success") is False:
            raise AssertionError(f"Tool returned success=False: {result}")

    @staticmethod
    def assert_tool_result_has_fields(result: dict[str, Any], *fields: str) -> None:
        """Assert tool result has specific fields."""
        for field in fields:
            if field not in result:
                raise AssertionError(f"Result missing field: {field}")

    @staticmethod
    def assert_lifecycle_state(
        lifecycle: PluginLifecycle,
        expected: PluginState,
    ) -> None:
        """Assert plugin is in expected state."""
        if lifecycle.state != expected:
            raise AssertionError(
                f"Plugin state is {lifecycle.state}, expected {expected}"
            )


# Convenience functions
def mock_registry() -> MockRegistry:
    """Create a new mock registry."""
    return MockRegistry()


def test_harness(work_dir: Path | None = None) -> PluginTestHarness:
    """Create a new test harness."""
    return PluginTestHarness(work_dir)
