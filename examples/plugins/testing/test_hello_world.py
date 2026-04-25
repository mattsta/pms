"""Example tests for the hello-world plugin.

This demonstrates how to test plugins using the PMS testing framework.

Run with:
    pytest examples/plugins/testing/test_hello_world.py -v

Or from the plugin directory:
    cd examples/plugins/simple/hello-world
    pytest ../../testing/test_hello_world.py -v
"""

from pathlib import Path

import pytest

# Import testing utilities
from pms.plugins.testing import (
    MockRegistry,
    PluginAssertions,
    PluginTestHarness,
    create_test_plugin_dir,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def harness(tmp_path):
    """Create a test harness for each test."""
    return PluginTestHarness(tmp_path)


@pytest.fixture
def mock_registry():
    """Create a mock registry for isolated testing."""
    return MockRegistry()


@pytest.fixture
def hello_world_path():
    """Path to the hello-world plugin."""
    return Path(__file__).parent.parent / "simple" / "hello-world"


# =============================================================================
# Unit Tests
# =============================================================================


class TestHelloWorldTools:
    """Test the hello-world plugin tools."""

    @pytest.mark.asyncio
    async def test_say_hello_default(self, harness, hello_world_path):
        """Test say_hello with default name."""
        await harness.load_plugin(hello_world_path)

        result = await harness.call_tool("hello-world.say_hello")

        assert result == "Hello, World!"
        harness.assert_no_errors()

    @pytest.mark.asyncio
    async def test_say_hello_with_name(self, harness, hello_world_path):
        """Test say_hello with custom name."""
        await harness.load_plugin(hello_world_path)

        result = await harness.call_tool("hello-world.say_hello", name="Alice")

        assert result == "Hello, Alice!"

    @pytest.mark.asyncio
    async def test_greeting_count_increments(self, harness, hello_world_path):
        """Test that greeting count increments."""
        await harness.load_plugin(hello_world_path)

        # Call say_hello multiple times
        await harness.call_tool("hello-world.say_hello")
        await harness.call_tool("hello-world.say_hello", name="Bob")
        await harness.call_tool("hello-world.say_hello", name="Charlie")

        # Check count
        result = await harness.call_tool("hello-world.get_greeting_count")

        assert result["count"] == 3


class TestHelloWorldLifecycle:
    """Test plugin lifecycle hooks."""

    @pytest.mark.asyncio
    async def test_plugin_loads_successfully(self, harness, hello_world_path):
        """Test that plugin loads without errors."""
        plugin = await harness.load_plugin(hello_world_path)

        assert plugin.name == "hello-world"
        harness.assert_no_errors()

    @pytest.mark.asyncio
    async def test_plugin_context_manager(self, harness, hello_world_path):
        """Test plugin lifecycle using context manager."""
        async with harness.plugin_context(hello_world_path) as plugin:
            assert plugin.name == "hello-world"
            result = await harness.call_tool("hello-world.say_hello")
            assert "Hello" in result

        # Plugin should be unloaded after context


# =============================================================================
# Mock Tests
# =============================================================================


class TestWithMocks:
    """Test using mock registry for isolated testing."""

    @pytest.mark.asyncio
    async def test_mock_tool_result(self, mock_registry):
        """Test mocking tool results."""
        # Set up mock
        mock_registry.mock_tool(
            "hello-world.say_hello",
            result="Mocked greeting!",
        )

        # Call mocked tool
        result = await mock_registry.call_tool("hello-world.say_hello", name="Test")

        assert result == "Mocked greeting!"

    @pytest.mark.asyncio
    async def test_mock_tool_handler(self, mock_registry):
        """Test mocking with custom handler."""

        async def custom_handler(name: str = "Custom") -> str:
            return f"Custom handler says: {name}"

        mock_registry.mock_tool(
            "hello-world.say_hello",
            handler=custom_handler,
        )

        result = await mock_registry.call_tool("hello-world.say_hello", name="Test")

        assert result == "Custom handler says: Test"

    def test_assert_tool_called(self, mock_registry):
        """Test tool call assertions."""
        import asyncio

        mock_registry.mock_tool("hello-world.say_hello", result="Hello!")

        asyncio.run(mock_registry.call_tool("hello-world.say_hello", name="Alice"))

        # This should pass
        mock_registry.assert_tool_called("hello-world.say_hello", name="Alice")

        # This should fail
        with pytest.raises(AssertionError):
            mock_registry.assert_tool_called("hello-world.say_hello", name="Bob")


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests for hello-world plugin."""

    @pytest.mark.asyncio
    async def test_full_workflow(self, harness, hello_world_path):
        """Test complete workflow: load, use, verify."""
        # Load plugin
        plugin = await harness.load_plugin(hello_world_path)
        assert plugin.name == "hello-world"

        # Use tools
        greet1 = await harness.call_tool("hello-world.say_hello")
        greet2 = await harness.call_tool("hello-world.say_hello", name="Integration")

        # Verify state
        count = await harness.call_tool("hello-world.get_greeting_count")

        assert greet1 == "Hello, World!"
        assert greet2 == "Hello, Integration!"
        assert count["count"] == 2
        harness.assert_no_errors()

    @pytest.mark.asyncio
    async def test_with_config(self, harness, hello_world_path):
        """Test plugin with custom configuration."""
        config = {"custom_option": "test_value"}

        plugin = await harness.load_plugin(hello_world_path, config=config)

        assert plugin.config == config


# =============================================================================
# Fixture Generation Tests
# =============================================================================


class TestPluginFixtures:
    """Test creating test plugins programmatically."""

    @pytest.mark.asyncio
    async def test_create_test_plugin(self, harness, tmp_path):
        """Test creating a plugin directory for testing."""
        # Create test plugin
        plugin_path = create_test_plugin_dir(
            base_path=tmp_path,
            name="test-plugin",
            tools=[
                {"name": "test_tool", "parameters": {"arg1": "string"}},
            ],
        )

        # Load and test
        plugin = await harness.load_plugin(plugin_path)

        assert plugin.name == "test-plugin"
        assert "test-plugin.test_tool" in harness.registry.tools

    @pytest.mark.asyncio
    async def test_custom_tool_implementation(self, harness, tmp_path):
        """Test creating plugin with custom tool code."""
        custom_code = '''
"""Custom test plugin."""

async def my_tool(value: str = "default") -> dict:
    """Custom implementation."""
    return {"received": value, "processed": True}

async def on_load(config: dict = None):
    pass
'''

        plugin_path = create_test_plugin_dir(
            base_path=tmp_path,
            name="custom-plugin",
            tools=[
                {"name": "my_tool", "parameters": {"value": "string"}},
            ],
            main_code=custom_code,
        )

        await harness.load_plugin(plugin_path)
        result = await harness.call_tool("custom-plugin.my_tool", value="test")

        assert result["received"] == "test"
        assert result["processed"] is True


# =============================================================================
# Assertion Tests
# =============================================================================


class TestAssertions:
    """Test plugin assertion utilities."""

    def test_manifest_validation(self, hello_world_path):
        """Test manifest validation assertion."""
        from pms.plugins import PluginManifest

        manifest = PluginManifest.from_file(hello_world_path / "plugin.json")

        # This should pass
        PluginAssertions.assert_manifest_valid(manifest)

    def test_tool_result_success(self):
        """Test success result assertion."""
        # Should pass
        PluginAssertions.assert_tool_result_success({"status": "ok"})
        PluginAssertions.assert_tool_result_success({"data": "value"})

        # Should fail
        with pytest.raises(AssertionError):
            PluginAssertions.assert_tool_result_success({"error": "failed"})

        with pytest.raises(AssertionError):
            PluginAssertions.assert_tool_result_success({"success": False})

    def test_result_has_fields(self):
        """Test field presence assertion."""
        result = {"name": "test", "value": 42, "status": "ok"}

        # Should pass
        PluginAssertions.assert_tool_result_has_fields(
            result, "name", "value", "status"
        )

        # Should fail
        with pytest.raises(AssertionError):
            PluginAssertions.assert_tool_result_has_fields(result, "missing_field")
