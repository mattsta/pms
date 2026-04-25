"""Integration tests for MCP tools with CLI outputs."""

import asyncio
from pathlib import Path

import pytest
from click.testing import CliRunner

from pms.cli.app import cli
from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.db.connection import Database
from pms.db.schema import initialize_schema
from pms.services import (
    OrganizationService,
    PortfolioService,
    ProgramService,
    ProjectService,
    TaskService,
    TeamService,
)
from pms.tools import project_tools


@pytest.fixture
def cli_runner() -> CliRunner:
    """Create a CLI test runner."""
    return CliRunner()


@pytest.fixture
def temp_env(tmp_path: Path):
    """Set up temporary environment for tool/CLI tests."""
    import os

    original_env = os.environ.copy()

    os.environ["PMS_DATABASE_PATH"] = str(tmp_path / "tool_cli.db")
    os.environ["PMS_DATA_DIR"] = str(tmp_path)

    yield tmp_path

    os.environ.clear()
    os.environ.update(original_env)


@pytest.mark.asyncio
async def test_tool_create_project_visible_in_cli(
    cli_runner: CliRunner, temp_env: Path
):
    """Tool-created project should show in CLI list."""
    from pms.config.settings import reload_settings

    reload_settings()

    db_path = temp_env / "tool_cli.db"
    db = Database(db_path)
    await db.connect()
    await initialize_schema(db)

    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)
    project_service = ProjectService(db, event_store, revision_store, metrics)
    task_service = TaskService(db, event_store, revision_store, metrics)
    project_tools.set_services(project_service, task_service)

    try:
        result = await project_tools.create_project.handler(
            {"name": "Tool Project", "description": "Created by tool", "tags": ""}
        )
        assert "Tool Project" in result["content"][0]["text"]

        cli_result = await asyncio.to_thread(
            cli_runner.invoke, cli, ["project", "list"]
        )
        assert cli_result.exit_code == 0
        assert "Tool Project" in cli_result.output
    finally:
        await db.disconnect()


@pytest.mark.asyncio
async def test_tool_create_task_visible_in_cli(cli_runner: CliRunner, temp_env: Path):
    """Tool-created task should show in CLI list."""
    from pms.config.settings import reload_settings

    reload_settings()

    db_path = temp_env / "tool_cli.db"
    db = Database(db_path)
    await db.connect()
    await initialize_schema(db)

    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)
    project_service = ProjectService(db, event_store, revision_store, metrics)
    task_service = TaskService(db, event_store, revision_store, metrics)
    project_tools.set_services(project_service, task_service)

    try:
        project = await project_service.create_project(name="Tool Task Project")
        result = await project_tools.create_task.handler(
            {
                "project": project.id,
                "title": "Tool Task",
                "description": "Created by tool",
                "priority": "high",
                "complexity_points": 40,
                "tags": "",
            }
        )
        assert "Tool Task" in result["content"][0]["text"]

        cli_result = await asyncio.to_thread(
            cli_runner.invoke, cli, ["task", "list", "-p", "Tool Task Project"]
        )
        assert cli_result.exit_code == 0
        assert "Tool Task" in cli_result.output
    finally:
        await db.disconnect()


@pytest.mark.asyncio
async def test_tool_create_org_visible_in_cli(cli_runner: CliRunner, temp_env: Path):
    """Tool-created organization should show in CLI list."""
    from pms.config.settings import reload_settings

    reload_settings()

    db_path = temp_env / "tool_cli.db"
    db = Database(db_path)
    await db.connect()
    await initialize_schema(db)

    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)
    project_service = ProjectService(db, event_store, revision_store, metrics)
    task_service = TaskService(db, event_store, revision_store, metrics)
    org_service = OrganizationService(db, event_store, revision_store, metrics)
    team_service = TeamService(db, event_store, revision_store, metrics)
    portfolio_service = PortfolioService(db, event_store, revision_store, metrics)
    program_service = ProgramService(db, event_store, revision_store, metrics)
    project_tools.set_services(
        project_service,
        task_service,
        organization_service=org_service,
        team_service=team_service,
        portfolio_service=portfolio_service,
        program_service=program_service,
    )

    try:
        result = await project_tools.create_organization.handler(
            {"name": "Tool Org", "description": "Created by tool"}
        )
        assert "Tool Org" in result["content"][0]["text"]

        cli_result = await asyncio.to_thread(cli_runner.invoke, cli, ["org", "list"])
        assert cli_result.exit_code == 0
        assert "Tool Org" in cli_result.output
    finally:
        await db.disconnect()


@pytest.mark.asyncio
async def test_tool_create_team_visible_in_cli(cli_runner: CliRunner, temp_env: Path):
    """Tool-created team should show in CLI list."""
    from pms.config.settings import reload_settings

    reload_settings()

    db_path = temp_env / "tool_cli.db"
    db = Database(db_path)
    await db.connect()
    await initialize_schema(db)

    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)
    project_service = ProjectService(db, event_store, revision_store, metrics)
    task_service = TaskService(db, event_store, revision_store, metrics)
    org_service = OrganizationService(db, event_store, revision_store, metrics)
    team_service = TeamService(db, event_store, revision_store, metrics)
    portfolio_service = PortfolioService(db, event_store, revision_store, metrics)
    program_service = ProgramService(db, event_store, revision_store, metrics)
    project_tools.set_services(
        project_service,
        task_service,
        organization_service=org_service,
        team_service=team_service,
        portfolio_service=portfolio_service,
        program_service=program_service,
    )

    try:
        org = await org_service.create_organization(name="Tool Team Org")
        result = await project_tools.create_team.handler(
            {"name": "Tool Team", "org_id": org.id}
        )
        assert "Tool Team" in result["content"][0]["text"]

        cli_result = await asyncio.to_thread(
            cli_runner.invoke, cli, ["team", "list", "--org-id", org.id]
        )
        assert cli_result.exit_code == 0
        assert "Tool Team" in cli_result.output
    finally:
        await db.disconnect()


@pytest.mark.asyncio
async def test_tool_create_portfolio_visible_in_cli(
    cli_runner: CliRunner, temp_env: Path
):
    """Tool-created portfolio should show in CLI list."""
    from pms.config.settings import reload_settings

    reload_settings()

    db_path = temp_env / "tool_cli.db"
    db = Database(db_path)
    await db.connect()
    await initialize_schema(db)

    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)
    project_service = ProjectService(db, event_store, revision_store, metrics)
    task_service = TaskService(db, event_store, revision_store, metrics)
    org_service = OrganizationService(db, event_store, revision_store, metrics)
    team_service = TeamService(db, event_store, revision_store, metrics)
    portfolio_service = PortfolioService(db, event_store, revision_store, metrics)
    program_service = ProgramService(db, event_store, revision_store, metrics)
    project_tools.set_services(
        project_service,
        task_service,
        organization_service=org_service,
        team_service=team_service,
        portfolio_service=portfolio_service,
        program_service=program_service,
    )

    try:
        org = await org_service.create_organization(name="Tool Portfolio Org")
        result = await project_tools.create_portfolio.handler(
            {"name": "Tool Portfolio", "org_id": org.id}
        )
        assert "Tool Portfolio" in result["content"][0]["text"]

        cli_result = await asyncio.to_thread(
            cli_runner.invoke, cli, ["portfolio", "list", "--org-id", org.id]
        )
        assert cli_result.exit_code == 0
        assert "Tool Portfolio" in cli_result.output
    finally:
        await db.disconnect()


@pytest.mark.asyncio
async def test_tool_create_program_visible_in_cli(
    cli_runner: CliRunner, temp_env: Path
):
    """Tool-created program should show in CLI list."""
    from pms.config.settings import reload_settings

    reload_settings()

    db_path = temp_env / "tool_cli.db"
    db = Database(db_path)
    await db.connect()
    await initialize_schema(db)

    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)
    project_service = ProjectService(db, event_store, revision_store, metrics)
    task_service = TaskService(db, event_store, revision_store, metrics)
    org_service = OrganizationService(db, event_store, revision_store, metrics)
    team_service = TeamService(db, event_store, revision_store, metrics)
    portfolio_service = PortfolioService(db, event_store, revision_store, metrics)
    program_service = ProgramService(db, event_store, revision_store, metrics)
    project_tools.set_services(
        project_service,
        task_service,
        organization_service=org_service,
        team_service=team_service,
        portfolio_service=portfolio_service,
        program_service=program_service,
    )

    try:
        org = await org_service.create_organization(name="Tool Program Org")
        portfolio = await portfolio_service.create_portfolio(
            name="Tool Program Portfolio", org_id=org.id
        )
        result = await project_tools.create_program.handler(
            {
                "name": "Tool Program",
                "org_id": org.id,
                "portfolio_id": portfolio.id,
            }
        )
        assert "Tool Program" in result["content"][0]["text"]

        cli_result = await asyncio.to_thread(
            cli_runner.invoke,
            cli,
            ["program", "list", "--portfolio-id", portfolio.id, "--format", "json"],
        )
        assert cli_result.exit_code == 0
        assert "Tool Program" in cli_result.output
    finally:
        await db.disconnect()
