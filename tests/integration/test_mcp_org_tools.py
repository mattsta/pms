"""Integration tests for organization MCP tools."""

from __future__ import annotations

import re

import pytest

from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.services.goal_service import GoalService
from pms.services.organization_service import OrganizationService
from pms.services.portfolio_service import PortfolioService
from pms.services.program_service import ProgramService
from pms.services.project_service import ProjectService
from pms.services.task_service import TaskService
from pms.services.team_service import TeamService
from pms.tools.project_tools import (
    create_organization,
    create_portfolio,
    create_program,
    create_team,
    get_organization,
    get_organization_dashboard,
    get_organization_summary,
    get_portfolio,
    get_portfolio_dashboard,
    get_portfolio_summary,
    get_program,
    get_program_dashboard,
    get_program_summary,
    get_team,
    list_organizations,
    list_portfolios,
    list_programs,
    list_teams,
    set_services,
    update_organization,
    update_portfolio,
    update_program,
    update_team,
)


def _extract_id(text: str) -> str:
    match = re.search(r"ID: ([a-f0-9-]+)", text)
    assert match, f"Expected ID in tool output: {text}"
    return match.group(1)


@pytest.mark.asyncio
async def test_org_team_portfolio_program_tools(db):
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)

    project_service = ProjectService(db, event_store, revision_store, metrics)
    task_service = TaskService(db, event_store, revision_store, metrics)
    goal_service = GoalService(db, event_store, revision_store, metrics)
    organization_service = OrganizationService(db, event_store, revision_store, metrics)
    team_service = TeamService(db, event_store, revision_store, metrics)
    portfolio_service = PortfolioService(db, event_store, revision_store, metrics)
    program_service = ProgramService(db, event_store, revision_store, metrics)

    set_services(
        project_service=project_service,
        task_service=task_service,
        goal_service=goal_service,
        organization_service=organization_service,
        team_service=team_service,
        portfolio_service=portfolio_service,
        program_service=program_service,
    )

    org_result = await create_organization.handler(
        {
            "name": "Tool Org",
            "description": "Integration org",
            "owner": "owner@example.com",
            "members": "owner@example.com,member@example.com",
            "tags": "tooling",
        }
    )
    org_text = org_result["content"][0]["text"]
    org_id = _extract_id(org_text)

    list_orgs = await list_organizations.handler({})
    assert "Tool Org" in list_orgs["content"][0]["text"]

    org_update = await update_organization.handler(
        {"org_id": org_id, "name": "Tool Org Updated", "status": "archived"}
    )
    assert "Updated organization" in org_update["content"][0]["text"]

    get_org = await get_organization.handler({"identifier": org_id})
    org_details = get_org["content"][0]["text"]
    assert org_id in org_details
    assert "Organization: Tool Org Updated" in org_details
    assert "Status: archived" in org_details

    team_result = await create_team.handler(
        {
            "name": "Tool Team",
            "org_id": org_id,
            "description": "Integration team",
            "owner": "lead@example.com",
            "members": "lead@example.com",
            "tags": "ops",
        }
    )
    team_id = _extract_id(team_result["content"][0]["text"])

    list_team = await list_teams.handler({"org_id": org_id})
    assert team_id in list_team["content"][0]["text"]

    team_update = await update_team.handler(
        {"team_id": team_id, "status": "archived", "owner": "lead@example.com"}
    )
    assert "Updated team" in team_update["content"][0]["text"]

    get_team_result = await get_team.handler({"identifier": team_id})
    team_details = get_team_result["content"][0]["text"]
    assert team_id in team_details
    assert "Status: archived" in team_details

    portfolio_result = await create_portfolio.handler(
        {
            "name": "Tool Portfolio",
            "org_id": org_id,
            "description": "Integration portfolio",
            "owner": "owner@example.com",
            "project_ids": "",
            "goal_ids": "",
            "objective_ids": "",
            "tags": "portfolio",
        }
    )
    portfolio_id = _extract_id(portfolio_result["content"][0]["text"])

    list_portfolio = await list_portfolios.handler({"org_id": org_id})
    assert portfolio_id in list_portfolio["content"][0]["text"]

    portfolio_update = await update_portfolio.handler(
        {
            "portfolio_id": portfolio_id,
            "name": "Tool Portfolio Updated",
            "status": "archived",
        }
    )
    assert "Updated portfolio" in portfolio_update["content"][0]["text"]

    get_portfolio_result = await get_portfolio.handler({"identifier": portfolio_id})
    portfolio_details = get_portfolio_result["content"][0]["text"]
    assert portfolio_id in portfolio_details
    assert "Portfolio: Tool Portfolio Updated" in portfolio_details
    assert "Status: archived" in portfolio_details

    portfolio_summary = await get_portfolio_summary.handler(
        {"portfolio_id": portfolio_id}
    )
    assert (
        "Portfolio: Tool Portfolio Updated" in portfolio_summary["content"][0]["text"]
    )

    program_result = await create_program.handler(
        {
            "name": "Tool Program",
            "org_id": org_id,
            "portfolio_id": portfolio_id,
            "description": "Integration program",
            "owner": "owner@example.com",
            "project_ids": "",
            "goal_ids": "",
            "objective_ids": "",
            "tags": "program",
        }
    )
    program_id = _extract_id(program_result["content"][0]["text"])

    list_program = await list_programs.handler({"org_id": org_id})
    assert program_id in list_program["content"][0]["text"]

    program_update = await update_program.handler(
        {"program_id": program_id, "name": "Tool Program Updated", "status": "archived"}
    )
    assert "Updated program" in program_update["content"][0]["text"]

    get_program_result = await get_program.handler({"identifier": program_id})
    program_details = get_program_result["content"][0]["text"]
    assert program_id in program_details
    assert "Program: Tool Program Updated" in program_details
    assert "Status: archived" in program_details

    program_summary = await get_program_summary.handler({"program_id": program_id})
    assert "Program: Tool Program Updated" in program_summary["content"][0]["text"]

    org_summary = await get_organization_summary.handler({"org_id": org_id})
    assert "Organization: Tool Org Updated" in org_summary["content"][0]["text"]

    org_dashboard = await get_organization_dashboard.handler({"status": "archived"})
    assert "Organization Dashboard" in org_dashboard["content"][0]["text"]

    portfolio_dashboard = await get_portfolio_dashboard.handler({"org_id": org_id})
    assert "Portfolio Dashboard" in portfolio_dashboard["content"][0]["text"]

    program_dashboard = await get_program_dashboard.handler(
        {"portfolio_id": portfolio_id}
    )
    assert "Program Dashboard" in program_dashboard["content"][0]["text"]
