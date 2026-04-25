"""PMS Plugin System.

A dynamic, sandboxed plugin architecture for extending PMS capabilities.

Features:
- Plugin manifest format (JSON/YAML)
- Runtime plugin discovery and loading
- Lifecycle management (init, start, stop, reload)
- IPC via Unix sockets for sandboxed execution
- Embedded DSL for dynamic tool definitions
- Hot-reload support
- Plugin marketplace integration

Usage:
    from pms.plugins import (
        PluginRegistry,
        PluginManifest,
        PluginState,
        load_plugin,
        get_plugin_registry,
    )

    # Discover and load plugins
    registry = get_plugin_registry()
    await registry.discover("~/.pms/plugins")
    await registry.load_all()

    # Create a plugin dynamically
    manifest = PluginManifest(
        name="my-plugin",
        version="1.0.0",
        tools=[...],
    )
    await registry.register(manifest)

Architecture:
    ┌─────────────────────────────────────────────┐
    │              Plugin Registry                │
    │  ┌─────────┐ ┌─────────┐ ┌─────────┐       │
    │  │ Plugin  │ │ Plugin  │ │ Plugin  │       │
    │  │Manifest │ │Manifest │ │Manifest │       │
    │  └────┬────┘ └────┬────┘ └────┬────┘       │
    │       │           │           │             │
    │  ┌────▼────┐ ┌────▼────┐ ┌────▼────┐       │
    │  │Lifecycle│ │Lifecycle│ │Lifecycle│       │
    │  │ Manager │ │ Manager │ │ Manager │       │
    │  └────┬────┘ └────┬────┘ └────┬────┘       │
    └───────┼───────────┼───────────┼─────────────┘
            │           │           │
    ┌───────▼───────────▼───────────▼─────────────┐
    │              IPC Layer (Unix Sockets)       │
    │         JSON-RPC Protocol Messages          │
    └───────┬───────────┬───────────┬─────────────┘
            │           │           │
    ┌───────▼───┐ ┌─────▼─────┐ ┌───▼───────┐
    │  Sandbox  │ │  Sandbox  │ │  Sandbox  │
    │ (Process) │ │ (Process) │ │ (Process) │
    └───────────┘ └───────────┘ └───────────┘
"""

from pms.plugins.dsl import (
    DSLCompiler,
    DSLParser,
    ToolDefinition,
    compile_tool,
    parse_tool_dsl,
)
from pms.plugins.lifecycle import (
    PluginLifecycle,
    PluginState,
)
from pms.plugins.manifest import (
    PluginCapability,
    PluginDependency,
    PluginHook,
    PluginManifest,
    PluginTool,
    PluginType,
)
from pms.plugins.protocol import (
    IPCMessage,
    IPCProtocol,
    MessageType,
    create_ipc_server,
)
from pms.plugins.registry import (
    PluginInfo,
    PluginRegistry,
    get_plugin_registry,
    set_plugin_registry,
)
from pms.plugins.sandbox import (
    SandboxConfig,
    SandboxedPlugin,
    SandboxManager,
)
from pms.plugins.testing import (
    MockPlugin,
    MockRegistry,
    MockTool,
    PluginAssertions,
    PluginTestHarness,
    create_test_manifest,
    create_test_plugin_dir,
    mock_registry,
    test_harness,
)

__all__ = [
    # Manifest
    "PluginManifest",
    "PluginTool",
    "PluginHook",
    "PluginDependency",
    "PluginCapability",
    "PluginType",
    # Registry
    "PluginRegistry",
    "PluginInfo",
    "get_plugin_registry",
    "set_plugin_registry",
    # Lifecycle
    "PluginLifecycle",
    "PluginState",
    # Protocol
    "IPCMessage",
    "IPCProtocol",
    "MessageType",
    "create_ipc_server",
    # Sandbox
    "SandboxConfig",
    "SandboxedPlugin",
    "SandboxManager",
    # DSL
    "DSLParser",
    "DSLCompiler",
    "ToolDefinition",
    "parse_tool_dsl",
    "compile_tool",
    # Testing
    "MockRegistry",
    "MockPlugin",
    "MockTool",
    "PluginTestHarness",
    "PluginAssertions",
    "create_test_manifest",
    "create_test_plugin_dir",
    "mock_registry",
    "test_harness",
]
