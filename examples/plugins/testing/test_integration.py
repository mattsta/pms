"""Example tests for integration plugins.

This demonstrates testing plugins that interact with each other,
using mocks for dependencies.

Run with:
    pytest examples/plugins/testing/test_integration.py -v
"""

from pathlib import Path

import pytest

from pms.plugins.testing import (
    MockRegistry,
    PluginAssertions,
    PluginTestHarness,
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
    """Create a mock registry with pre-configured plugins."""
    registry = MockRegistry()

    # Add mock file-utils plugin
    registry.add_plugin(
        "file-utils",
        tools=[
            "count_lines",
            "find_files",
            "search_content",
            "file_stats",
        ],
    )

    # Add mock github-integration plugin
    registry.add_plugin(
        "github-integration",
        tools=[
            "list_repos",
            "list_issues",
            "create_issue",
            "sync_to_tasks",
        ],
    )

    return registry


@pytest.fixture
def workflow_orchestrator_path():
    """Path to the workflow-orchestrator plugin."""
    return Path(__file__).parent.parent / "integration" / "workflow-orchestrator"


@pytest.fixture
def data_pipeline_path():
    """Path to the data-pipeline plugin."""
    return Path(__file__).parent.parent / "integration" / "data-pipeline"


# =============================================================================
# Mock Plugin Tests
# =============================================================================


class TestMockPluginInteraction:
    """Test plugin interactions using mock registry."""

    @pytest.mark.asyncio
    async def test_mock_file_utils(self, mock_registry):
        """Test mocking file-utils responses."""
        # Configure mock response
        mock_registry.mock_tool(
            "file-utils.count_lines",
            result={
                "total_lines": 1500,
                "total_files": 25,
                "files": [
                    {"file": "main.py", "lines": 500},
                    {"file": "utils.py", "lines": 300},
                ],
            },
        )

        # Call mock
        result = await mock_registry.call_tool(
            "file-utils.count_lines",
            path="./src",
            pattern="*.py",
        )

        assert result["total_lines"] == 1500
        assert result["total_files"] == 25
        mock_registry.assert_tool_called(
            "file-utils.count_lines",
            path="./src",
        )

    @pytest.mark.asyncio
    async def test_mock_github_integration(self, mock_registry):
        """Test mocking github-integration responses."""
        # Configure mock response
        mock_registry.mock_tool(
            "github-integration.list_issues",
            result={
                "issues": [
                    {"number": 1, "title": "Bug: Something broken", "labels": ["bug"]},
                    {
                        "number": 2,
                        "title": "Feature: Add feature",
                        "labels": ["enhancement"],
                    },
                ],
                "count": 2,
            },
        )

        result = await mock_registry.call_tool(
            "github-integration.list_issues",
            owner="test-org",
            repo="test-repo",
            state="open",
        )

        assert len(result["issues"]) == 2
        assert result["issues"][0]["number"] == 1

    @pytest.mark.asyncio
    async def test_cross_plugin_workflow(self, mock_registry):
        """Test workflow that uses multiple plugins."""
        # Mock file-utils
        mock_registry.mock_tool(
            "file-utils.count_lines",
            result={"total_lines": 1000, "files": []},
        )
        mock_registry.mock_tool(
            "file-utils.search_content",
            result={"matches": [{"file": "main.py", "line": 10}], "total_matches": 1},
        )

        # Mock github
        mock_registry.mock_tool(
            "github-integration.create_issue",
            result={"number": 42, "url": "https://github.com/test/issues/42"},
        )

        # Simulate workflow: analyze code, find TODOs, create issue
        lines = await mock_registry.call_tool("file-utils.count_lines", path="./src")
        todos = await mock_registry.call_tool(
            "file-utils.search_content",
            directory="./src",
            query="TODO",
        )

        # Create issue if TODOs found
        if todos["total_matches"] > 0:
            issue = await mock_registry.call_tool(
                "github-integration.create_issue",
                owner="test-org",
                repo="test-repo",
                title=f"Found {todos['total_matches']} TODOs in codebase",
                body=f"Lines of code: {lines['total_lines']}",
            )
            assert issue["number"] == 42


# =============================================================================
# Event Hook Tests
# =============================================================================


class TestEventHooks:
    """Test event-driven plugin integration."""

    @pytest.mark.asyncio
    async def test_event_emission(self, mock_registry):
        """Test that events are properly emitted."""
        events_received = []

        # Register hook
        async def on_task_completed(**kwargs):
            events_received.append(kwargs)

        mock_registry.register_hook("task_completed", on_task_completed)

        # Emit event
        mock_registry.emit_event(
            "task_completed",
            task_id="task-123",
            title="Fix bug",
            tags=["bug", "github"],
        )

        # Allow async processing
        import asyncio

        await asyncio.sleep(0.1)

        # Verify event was recorded
        mock_registry.assert_event_emitted("task_completed", task_id="task-123")

    @pytest.mark.asyncio
    async def test_event_triggers_tool_call(self, mock_registry):
        """Test that events can trigger tool calls."""
        # Setup mock
        mock_registry.mock_tool(
            "github-integration.sync_to_tasks",
            result={"synced": 5},
        )

        # Register hook that calls another plugin
        async def on_project_created(project_id: str, name: str, **kwargs):
            # Simulate syncing GitHub issues when project created
            await mock_registry.call_tool(
                "github-integration.sync_to_tasks",
                owner="test-org",
                repo=name,
                project_name=name,
            )

        mock_registry.register_hook("project_created", on_project_created)

        # Emit project creation event
        mock_registry.emit_event(
            "project_created",
            project_id="proj-123",
            name="my-project",
        )

        # Allow async processing
        import asyncio

        await asyncio.sleep(0.1)

        # Verify tool was called
        mock_registry.assert_tool_called(
            "github-integration.sync_to_tasks",
            repo="my-project",
        )


# =============================================================================
# Pipeline Tests
# =============================================================================


class TestDataPipelines:
    """Test data pipeline plugin functionality."""

    @pytest.mark.asyncio
    async def test_transform_operations(self, harness, data_pipeline_path):
        """Test data transformation operations."""
        if not data_pipeline_path.exists():
            pytest.skip("Data pipeline plugin not found")

        await harness.load_plugin(data_pipeline_path)

        # Test map operation
        result = await harness.call_tool(
            "data-pipeline.transform",
            data={"values": [1, 2, 3, 4, 5]},
            operations=[
                {"op": "map", "field": "values", "fn": "x * 2"},
            ],
        )

        assert result["data"]["values"] == [2, 4, 6, 8, 10]

    @pytest.mark.asyncio
    async def test_filter_operation(self, harness, data_pipeline_path):
        """Test filter transformation."""
        if not data_pipeline_path.exists():
            pytest.skip("Data pipeline plugin not found")

        await harness.load_plugin(data_pipeline_path)

        result = await harness.call_tool(
            "data-pipeline.transform",
            data={
                "files": [
                    {"name": "a.py", "lines": 50},
                    {"name": "b.py", "lines": 150},
                    {"name": "c.py", "lines": 200},
                ]
            },
            operations=[
                {"op": "filter", "field": "files", "condition": "lines > 100"},
            ],
        )

        assert len(result["data"]["files"]) == 2
        assert all(f["lines"] > 100 for f in result["data"]["files"])

    @pytest.mark.asyncio
    async def test_aggregate_from_multiple_sources(self, mock_registry):
        """Test aggregating data from multiple plugins."""
        # Setup mocks
        mock_registry.mock_tool(
            "file-utils.count_lines",
            result={"total_lines": 1000, "source": "file-utils"},
        )
        mock_registry.mock_tool(
            "github-integration.list_issues",
            result={"count": 5, "source": "github"},
        )

        # Collect from both
        file_data = await mock_registry.call_tool("file-utils.count_lines", path=".")
        github_data = await mock_registry.call_tool(
            "github-integration.list_issues",
            owner="test",
            repo="test",
        )

        # Aggregate
        aggregated = {
            "sources": 2,
            "data": {
                "code": file_data,
                "issues": github_data,
            },
        }

        assert aggregated["sources"] == 2
        assert aggregated["data"]["code"]["total_lines"] == 1000
        assert aggregated["data"]["issues"]["count"] == 5


# =============================================================================
# Workflow Orchestrator Tests
# =============================================================================


class TestWorkflowOrchestrator:
    """Test workflow orchestrator plugin."""

    @pytest.mark.asyncio
    async def test_pipeline_definition(self, harness, workflow_orchestrator_path):
        """Test defining a workflow pipeline."""
        if not workflow_orchestrator_path.exists():
            pytest.skip("Workflow orchestrator plugin not found")

        await harness.load_plugin(workflow_orchestrator_path)

        result = await harness.call_tool(
            "workflow-orchestrator.define_pipeline",
            name="test-pipeline",
            description="Test pipeline",
            steps=[
                {
                    "plugin": "file-utils",
                    "tool": "count_lines",
                    "args": {"path": "$input.directory"},
                },
            ],
        )

        assert result["success"] is True
        assert result["pipeline"] == "test-pipeline"

    @pytest.mark.asyncio
    async def test_pipeline_dry_run(self, harness, workflow_orchestrator_path):
        """Test pipeline dry run."""
        if not workflow_orchestrator_path.exists():
            pytest.skip("Workflow orchestrator plugin not found")

        await harness.load_plugin(workflow_orchestrator_path)

        # Run built-in template in dry-run mode
        result = await harness.call_tool(
            "workflow-orchestrator.run_pipeline",
            pipeline="code-analysis",
            input={"directory": "./src"},
            dry_run=True,
        )

        assert result["dry_run"] is True
        assert len(result["steps"]) > 0
        assert result["steps"][0]["resolved_args"]["path"] == "./src"

    @pytest.mark.asyncio
    async def test_list_pipelines(self, harness, workflow_orchestrator_path):
        """Test listing available pipelines."""
        if not workflow_orchestrator_path.exists():
            pytest.skip("Workflow orchestrator plugin not found")

        await harness.load_plugin(workflow_orchestrator_path)

        result = await harness.call_tool("workflow-orchestrator.list_pipelines")

        assert "pipelines" in result
        assert "code-analysis" in result["pipelines"]
        assert "github-sync" in result["pipelines"]


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestErrorHandling:
    """Test error handling in plugin integration."""

    @pytest.mark.asyncio
    async def test_missing_plugin_tool(self, mock_registry):
        """Test calling non-existent tool."""
        with pytest.raises(ValueError, match="Tool not found"):
            await mock_registry.call_tool("nonexistent.tool")

    @pytest.mark.asyncio
    async def test_tool_failure(self, mock_registry):
        """Test handling tool failures."""

        async def failing_handler(**kwargs):
            raise RuntimeError("Tool execution failed")

        mock_registry.mock_tool(
            "test.failing_tool",
            handler=failing_handler,
        )

        with pytest.raises(RuntimeError, match="failed"):
            await mock_registry.call_tool("test.failing_tool")

    @pytest.mark.asyncio
    async def test_tool_returns_error(self, mock_registry):
        """Test handling tool error responses."""
        mock_registry.mock_tool(
            "test.error_tool",
            result={"error": "Something went wrong"},
        )

        result = await mock_registry.call_tool("test.error_tool")

        # Tool returned but with error in response
        assert "error" in result

        # Assertion should fail
        with pytest.raises(AssertionError):
            PluginAssertions.assert_tool_result_success(result)
