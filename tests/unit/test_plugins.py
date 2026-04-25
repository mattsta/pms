"""Tests for the Plugin System."""

import json

import pytest

from pms.plugins.dsl import (
    DSLCompiler,
    DSLParser,
    DSLType,
    SafeExpressionEvaluator,
    ToolDefinition,
)
from pms.plugins.lifecycle import PluginLifecycle, PluginState
from pms.plugins.manifest import (
    PluginCapability,
    PluginManifest,
    PluginParameter,
    PluginTool,
    PluginType,
)
from pms.plugins.protocol import ErrorCode, IPCMessage, IPCProtocol, MessageType
from pms.plugins.registry import PluginRegistry, RegisteredTool

# =============================================================================
# Manifest Tests
# =============================================================================


class TestPluginParameter:
    """Tests for PluginParameter."""

    def test_create_parameter(self):
        """Test creating a parameter."""
        param = PluginParameter(
            name="test",
            type="string",
            required=True,
        )
        assert param.name == "test"
        assert param.type == "string"
        assert param.required is True
        assert param.default is None

    def test_optional_parameter(self):
        """Test optional parameter with default."""
        param = PluginParameter(
            name="count",
            type="int",
            required=False,
            default=10,
        )
        assert param.required is False
        assert param.default == 10

    def test_from_dict(self):
        """Test creating parameter from dict."""
        param = PluginParameter.from_dict(
            "test",
            {
                "type": "string",
                "required": True,
                "description": "Test param",
            },
        )
        assert param.name == "test"
        assert param.type == "string"
        assert param.required is True

    def test_to_dict(self):
        """Test serialization to dict."""
        param = PluginParameter(
            name="test",
            type="string",
            required=True,
            description="Test param",
        )
        data = param.to_dict()
        assert data["name"] == "test"
        assert data["type"] == "string"
        assert data["required"] is True


class TestPluginTool:
    """Tests for PluginTool."""

    def test_create_tool(self):
        """Test creating a tool."""
        tool = PluginTool(
            name="list_repos",
            description="List GitHub repos",
            handler="list_repos_handler",
        )
        assert tool.name == "list_repos"
        assert tool.async_handler is True
        assert tool.timeout == 30.0

    def test_from_dict(self):
        """Test creating tool from dict."""
        data = {
            "name": "create_issue",
            "description": "Create GitHub issue",
            "parameters": {
                "title": {"type": "string", "required": True},
                "body": {"type": "string", "required": False},
            },
        }
        tool = PluginTool.from_dict(data)
        assert tool.name == "create_issue"
        assert "title" in tool.parameters
        assert tool.parameters["title"].required is True

    def test_to_dict(self):
        """Test serialization."""
        tool = PluginTool(name="test", description="Test tool")
        data = tool.to_dict()
        assert data["name"] == "test"
        assert "parameters" in data


class TestPluginManifest:
    """Tests for PluginManifest."""

    def test_create_manifest(self):
        """Test creating a manifest."""
        manifest = PluginManifest(
            name="my-plugin",
            version="1.0.0",
            description="My test plugin",
            tools=[
                PluginTool(name="my_tool", description="A tool"),
            ],
        )
        assert manifest.name == "my-plugin"
        assert manifest.version == "1.0.0"
        assert len(manifest.tools) == 1

    def test_from_dict(self):
        """Test creating from dict."""
        data = {
            "name": "github-integration",
            "version": "2.0.0",
            "type": "integration",
            "tools": [
                {"name": "list_repos", "description": "List repos"},
            ],
            "capabilities": ["network"],
        }
        manifest = PluginManifest.from_dict(data)
        assert manifest.name == "github-integration"
        assert manifest.type == PluginType.INTEGRATION
        assert PluginCapability.NETWORK in manifest.capabilities

    def test_to_dict(self):
        """Test serialization."""
        manifest = PluginManifest(
            name="test",
            version="1.0.0",
            capabilities=[PluginCapability.NETWORK],
        )
        data = manifest.to_dict()
        assert data["name"] == "test"
        assert "network" in data["capabilities"]

    def test_validate_valid(self):
        """Test validation passes for valid manifest."""
        manifest = PluginManifest(
            name="valid-plugin",
            version="1.0.0",
            tools=[
                PluginTool(name="tool1", description="First tool"),
            ],
        )
        errors = manifest.validate()
        assert len(errors) == 0

    def test_validate_missing_name(self):
        """Test validation fails for missing name."""
        manifest = PluginManifest(name="", version="1.0.0")
        errors = manifest.validate()
        assert any("name" in e.lower() for e in errors)

    def test_validate_duplicate_tools(self):
        """Test validation fails for duplicate tool names."""
        manifest = PluginManifest(
            name="test",
            version="1.0.0",
            tools=[
                PluginTool(name="tool1", description="First"),
                PluginTool(name="tool1", description="Duplicate"),
            ],
        )
        errors = manifest.validate()
        assert any("duplicate" in e.lower() for e in errors)

    def test_from_file(self, tmp_path):
        """Test loading from file."""
        manifest_data = {
            "name": "file-plugin",
            "version": "1.0.0",
            "description": "Plugin from file",
        }
        manifest_path = tmp_path / "plugin.json"
        manifest_path.write_text(json.dumps(manifest_data))

        manifest = PluginManifest.from_file(manifest_path)
        assert manifest.name == "file-plugin"
        assert manifest.path == manifest_path

    def test_get_tool(self):
        """Test getting tool by name."""
        manifest = PluginManifest(
            name="test",
            version="1.0.0",
            tools=[
                PluginTool(name="tool1", description="First"),
                PluginTool(name="tool2", description="Second"),
            ],
        )
        tool = manifest.get_tool("tool1")
        assert tool is not None
        assert tool.name == "tool1"

        assert manifest.get_tool("nonexistent") is None

    def test_requires_sandbox(self):
        """Test sandbox requirement detection."""
        # Plugin with network should require sandbox
        manifest = PluginManifest(
            name="test",
            version="1.0.0",
            capabilities=[PluginCapability.NETWORK],
        )
        assert manifest.requires_sandbox is True

        # Plugin without dangerous capabilities
        manifest2 = PluginManifest(
            name="test2",
            version="1.0.0",
            sandbox=False,
        )
        assert manifest2.requires_sandbox is False


# =============================================================================
# Lifecycle Tests
# =============================================================================


class TestPluginLifecycle:
    """Tests for PluginLifecycle."""

    @pytest.fixture
    def manifest(self):
        """Create test manifest."""
        return PluginManifest(
            name="test-plugin",
            version="1.0.0",
            tools=[PluginTool(name="test_tool", description="Test")],
        )

    @pytest.fixture
    def lifecycle(self, manifest):
        """Create lifecycle manager."""
        return PluginLifecycle(manifest)

    def test_initial_state(self, lifecycle):
        """Test initial state is DISCOVERED."""
        assert lifecycle.state == PluginState.DISCOVERED
        assert not lifecycle.is_running
        assert not lifecycle.is_error

    @pytest.mark.anyio
    async def test_load(self, lifecycle):
        """Test loading plugin."""
        result = await lifecycle.load()
        assert result is True
        assert lifecycle.state == PluginState.LOADED

    @pytest.mark.anyio
    async def test_load_invalid_manifest(self):
        """Test loading with invalid manifest."""
        manifest = PluginManifest(name="", version="1.0.0")  # Invalid
        lifecycle = PluginLifecycle(manifest)

        result = await lifecycle.load()
        assert result is False
        assert lifecycle.state == PluginState.ERROR
        assert lifecycle.error is not None

    @pytest.mark.anyio
    async def test_lifecycle_transitions(self, lifecycle):
        """Test full lifecycle transitions."""
        # DISCOVERED -> LOADED
        assert await lifecycle.load()
        assert lifecycle.state == PluginState.LOADED

        # LOADED -> INITIALIZED
        assert await lifecycle.initialize()
        assert lifecycle.state == PluginState.INITIALIZED

        # INITIALIZED -> RUNNING
        assert await lifecycle.start()
        assert lifecycle.state == PluginState.RUNNING
        assert lifecycle.is_running

        # RUNNING -> STOPPED
        assert await lifecycle.stop()
        assert lifecycle.state == PluginState.STOPPED

    @pytest.mark.anyio
    async def test_disable(self, lifecycle):
        """Test disabling plugin."""
        await lifecycle.load()
        assert await lifecycle.disable()
        assert lifecycle.state == PluginState.DISABLED

    def test_stats_recording(self, lifecycle):
        """Test stats recording."""
        lifecycle.stats.record_tool_call(100.0, success=True)
        lifecycle.stats.record_tool_call(50.0, success=False)

        assert lifecycle.stats.tool_calls == 2
        assert lifecycle.stats.tool_errors == 1
        assert lifecycle.stats.avg_execution_time_ms == 75.0

    def test_get_status(self, lifecycle):
        """Test getting status."""
        status = lifecycle.get_status()
        assert status["name"] == "test-plugin"
        assert status["state"] == "discovered"
        assert "stats" in status


# =============================================================================
# Protocol Tests
# =============================================================================


class TestIPCMessage:
    """Tests for IPCMessage."""

    def test_create_request(self):
        """Test creating request message."""
        msg = IPCMessage.request("call_tool", tool="list_repos", org="test")
        assert msg.type == MessageType.REQUEST
        assert msg.method == "call_tool"
        assert msg.id is not None
        assert msg.params["tool"] == "list_repos"

    def test_create_response(self):
        """Test creating response message."""
        msg = IPCMessage.response("req-123", {"repos": ["a", "b"]})
        assert msg.type == MessageType.RESPONSE
        assert msg.id == "req-123"
        assert msg.result == {"repos": ["a", "b"]}

    def test_create_error_response(self):
        """Test creating error response."""
        msg = IPCMessage.error_response(
            "req-123",
            ErrorCode.TOOL_NOT_FOUND,
            "Tool not found: foo",
        )
        assert msg.is_error
        assert msg.error["code"] == ErrorCode.TOOL_NOT_FOUND.value

    def test_to_json(self):
        """Test JSON serialization."""
        msg = IPCMessage.request("ping")
        json_str = msg.to_json()
        data = json.loads(json_str)
        assert data["jsonrpc"] == "2.0"
        assert data["method"] == "ping"

    def test_from_json(self):
        """Test JSON deserialization."""
        json_str = '{"jsonrpc": "2.0", "id": "1", "method": "test", "params": {}}'
        msg = IPCMessage.from_json(json_str)
        assert msg.type == MessageType.REQUEST
        assert msg.method == "test"

    def test_roundtrip(self):
        """Test serialization roundtrip."""
        original = IPCMessage.request("my_method", arg1="value1")
        json_str = original.to_json()
        restored = IPCMessage.from_json(json_str)

        assert restored.method == original.method
        assert restored.params == original.params


class TestIPCProtocol:
    """Tests for IPCProtocol."""

    @pytest.fixture
    def protocol(self):
        """Create protocol instance."""
        return IPCProtocol()

    @pytest.mark.anyio
    async def test_handle_request(self, protocol):
        """Test handling request with registered handler."""

        async def handler(msg):
            return IPCMessage.response(msg.id, "handled")

        protocol.register_handler("test_method", handler)

        request = IPCMessage.request("test_method")
        response = await protocol.handle_message(request)

        assert response is not None
        assert response.is_success
        assert response.result == "handled"

    @pytest.mark.anyio
    async def test_handle_unknown_method(self, protocol):
        """Test handling request with unknown method."""
        request = IPCMessage.request("unknown_method")
        response = await protocol.handle_message(request)

        assert response is not None
        assert response.is_error
        assert response.error["code"] == ErrorCode.METHOD_NOT_FOUND.value

    @pytest.mark.anyio
    async def test_handle_ping(self, protocol):
        """Test handling ping message."""
        ping = IPCMessage(type=MessageType.PING)
        response = await protocol.handle_message(ping)

        assert response is not None
        assert response.type == MessageType.PONG


# =============================================================================
# DSL Tests
# =============================================================================


class TestSafeExpressionEvaluator:
    """Tests for SafeExpressionEvaluator."""

    @pytest.fixture
    def evaluator(self):
        """Create evaluator with context."""
        return SafeExpressionEvaluator({"x": 10, "name": "test", "items": [1, 2, 3]})

    def test_literal_values(self, evaluator):
        """Test evaluating literal values."""
        assert evaluator.evaluate("42") == 42
        assert evaluator.evaluate('"hello"') == "hello"
        assert evaluator.evaluate("True") is True

    def test_variable_access(self, evaluator):
        """Test accessing context variables."""
        assert evaluator.evaluate("x") == 10
        assert evaluator.evaluate("name") == "test"

    def test_arithmetic(self, evaluator):
        """Test arithmetic operations."""
        assert evaluator.evaluate("x + 5") == 15
        assert evaluator.evaluate("x * 2") == 20
        assert evaluator.evaluate("x / 2") == 5.0
        assert evaluator.evaluate("x ** 2") == 100

    def test_comparison(self, evaluator):
        """Test comparison operations."""
        assert evaluator.evaluate("x > 5") is True
        assert evaluator.evaluate("x == 10") is True
        assert evaluator.evaluate("x != 5") is True

    def test_boolean_operations(self, evaluator):
        """Test boolean operations."""
        assert evaluator.evaluate("x > 5 and x < 20") is True
        assert evaluator.evaluate("x < 5 or x > 5") is True
        assert evaluator.evaluate("not (x < 5)") is True

    def test_list_operations(self, evaluator):
        """Test list operations."""
        assert evaluator.evaluate("len(items)") == 3
        assert evaluator.evaluate("items[0]") == 1
        assert evaluator.evaluate("2 in items") is True

    def test_string_operations(self, evaluator):
        """Test string operations."""
        assert evaluator.evaluate("upper(name)") == "TEST"
        assert evaluator.evaluate("len(name)") == 4

    def test_conditional(self, evaluator):
        """Test conditional expression."""
        assert evaluator.evaluate("'big' if x > 5 else 'small'") == "big"

    def test_unknown_variable(self, evaluator):
        """Test unknown variable raises error."""
        with pytest.raises(ValueError):
            evaluator.evaluate("unknown_var")

    def test_dangerous_operations_blocked(self, evaluator):
        """Test that dangerous operations are blocked."""
        with pytest.raises(ValueError):
            evaluator.evaluate("__import__('os')")


class TestDSLParser:
    """Tests for DSLParser."""

    @pytest.fixture
    def parser(self):
        return DSLParser()

    def test_parse_simple_tool(self, parser):
        """Test parsing simple tool."""
        source = """
tool greet:
    description: "Greet someone"
    return "Hello"
"""
        tools = parser.parse(source)
        assert len(tools) == 1
        assert tools[0].name == "greet"
        assert tools[0].description == "Greet someone"

    def test_parse_multiple_tools(self, parser):
        """Test parsing multiple tools."""
        source = """
tool tool1:
    description: "First tool"
    return 1

tool tool2:
    description: "Second tool"
    return 2
"""
        tools = parser.parse(source)
        assert len(tools) == 2
        assert tools[0].name == "tool1"
        assert tools[1].name == "tool2"

    def test_parse_with_conditions(self, parser):
        """Test parsing conditional tool."""
        source = """
tool check:
    description: "Check value"
    parameters:
        x: int
    when x > 10:
        return "big"
    otherwise:
        return "small"
"""
        tools = parser.parse(source)
        assert len(tools) == 1
        assert len(tools[0].conditions) == 1


class TestDSLCompiler:
    """Tests for DSLCompiler."""

    @pytest.fixture
    def compiler(self):
        return DSLCompiler()

    @pytest.mark.anyio
    async def test_compile_simple_tool(self, compiler):
        """Test compiling simple tool."""
        tool = ToolDefinition(
            name="add",
            description="Add two numbers",
            parameters={
                "a": type(
                    "Param",
                    (),
                    {
                        "name": "a",
                        "type": DSLType.INT,
                        "required": True,
                        "default": None,
                    },
                )(),
                "b": type(
                    "Param",
                    (),
                    {
                        "name": "b",
                        "type": DSLType.INT,
                        "required": True,
                        "default": None,
                    },
                )(),
            },
            body="a + b",
        )

        handler = compiler.compile(tool)
        result = await handler(a=5, b=3)
        assert result == 8

    @pytest.mark.anyio
    async def test_compile_with_defaults(self, compiler):
        """Test compiling tool with defaults."""
        from pms.plugins.dsl import DSLParameter

        tool = ToolDefinition(
            name="greet",
            parameters={
                "name": DSLParameter(
                    "name", DSLType.STRING, required=False, default="World"
                ),
            },
            body="'Hello, ' + name",
        )

        handler = compiler.compile(tool)
        result = await handler()
        assert result == "Hello, World"

        result = await handler(name="Test")
        assert result == "Hello, Test"


# =============================================================================
# Registry Tests
# =============================================================================


class TestPluginRegistry:
    """Tests for PluginRegistry."""

    @pytest.fixture
    def registry(self):
        """Create test registry."""
        return PluginRegistry()

    @pytest.fixture
    def manifest(self):
        """Create test manifest."""
        return PluginManifest(
            name="test-plugin",
            version="1.0.0",
            description="Test plugin",
            sandbox=False,  # Don't require sandbox for tests
            tools=[
                PluginTool(name="my_tool", description="A test tool"),
            ],
        )

    @pytest.mark.anyio
    async def test_register(self, registry, manifest):
        """Test registering a plugin."""
        info = await registry.register(manifest)

        assert info.name == "test-plugin"
        assert info.state == PluginState.DISCOVERED

    @pytest.mark.anyio
    async def test_register_duplicate(self, registry, manifest):
        """Test registering duplicate plugin."""
        await registry.register(manifest)

        with pytest.raises(ValueError):
            await registry.register(manifest)

    @pytest.mark.anyio
    async def test_unregister(self, registry, manifest):
        """Test unregistering a plugin."""
        await registry.register(manifest)

        result = await registry.unregister("test-plugin")
        assert result is True
        assert registry.get("test-plugin") is None

    @pytest.mark.anyio
    async def test_load(self, registry, manifest):
        """Test loading a plugin."""
        await registry.register(manifest)

        result = await registry.load("test-plugin")
        assert result is True
        assert registry.get("test-plugin").state == PluginState.LOADED

    @pytest.mark.anyio
    async def test_discover(self, registry, tmp_path):
        """Test discovering plugins."""
        # Create plugin directory
        plugin_dir = tmp_path / "my-plugin"
        plugin_dir.mkdir()

        # Create manifest
        manifest_data = {
            "name": "discovered-plugin",
            "version": "1.0.0",
            "description": "A discovered plugin",
        }
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest_data))

        # Discover
        discovered = await registry.discover(tmp_path)

        assert "discovered-plugin" in discovered
        assert registry.get("discovered-plugin") is not None

    def test_list_tools(self, registry):
        """Test listing tools."""
        tools = registry.list_tools()
        assert isinstance(tools, list)

    def test_list_plugins(self, registry):
        """Test listing plugins."""
        plugins = registry.list_plugins()
        assert isinstance(plugins, list)

    def test_get_stats(self, registry):
        """Test getting stats."""
        stats = registry.get_stats()
        assert "total_plugins" in stats
        assert "total_tools" in stats


class TestRegisteredTool:
    """Tests for RegisteredTool."""

    def test_full_name(self):
        """Test full name generation."""
        tool = RegisteredTool(
            name="my_tool",
            plugin_name="my-plugin",
            description="A tool",
        )
        assert tool.full_name == "my-plugin.my_tool"


# =============================================================================
# Integration Tests
# =============================================================================


class TestPluginIntegration:
    """Integration tests for plugin system."""

    @pytest.mark.anyio
    async def test_full_plugin_lifecycle(self, tmp_path):
        """Test complete plugin lifecycle."""
        # Create plugin
        plugin_dir = tmp_path / "test-plugin"
        plugin_dir.mkdir()

        manifest_data = {
            "name": "integration-test",
            "version": "1.0.0",
            "sandbox": False,
            "tools": [
                {"name": "hello", "description": "Say hello"},
            ],
        }
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest_data))

        # Create registry and discover
        registry = PluginRegistry()
        await registry.discover(tmp_path)

        # Load
        assert await registry.load("integration-test")

        # Initialize
        assert await registry.initialize("integration-test")

        # Start
        assert await registry.start("integration-test")

        # Verify running
        info = registry.get("integration-test")
        assert info is not None
        assert info.is_running

        # Stop
        await registry.stop_all()

    @pytest.mark.anyio
    async def test_dsl_tools(self, tmp_path):
        """Test DSL tool loading."""
        # Create DSL file
        dsl_content = """
tool add:
    description: "Add two numbers"
    return 1 + 2

tool greet:
    description: "Greet someone"
    return "hello"
"""
        (tmp_path / "math.tools").write_text(dsl_content)

        # Discover
        registry = PluginRegistry()
        await registry.discover(tmp_path)

        # Should have registered tools
        tools = registry.list_tools()
        tool_names = [t.full_name for t in tools]
        assert "math.add" in tool_names
        assert "math.greet" in tool_names

        # Call tool
        result = await registry.call_tool("math.add")
        assert result == 3
