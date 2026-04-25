"""Tests for PMS Web API server."""

import json
from datetime import datetime

import pytest

from pms import __version__
from pms.api.auth import Scopes
from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.models import ActorKind, TaskStatus
from pms.repositories.task_repository import TaskRepository
from pms.services.actor_service import ActorService
from pms.services.comment_service import CommentService
from pms.services.label_service import LabelService


@pytest.mark.asyncio
async def test_api_root(api_client):
    """Test root endpoint."""
    response = await api_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "PMS API"
    assert data["version"] == __version__
    assert data["links"]["health"] == "/api/v1/health"
    assert data["links"]["dashboard"] == "/dashboard"
    assert data["links"]["discoverability_graph"] == "/api/v1/discoverability/graph"
    assert data["links"]["observability_overview"] == "/api/v1/observability/overview"
    assert len(data["discoverability"]["entry_points"]) >= 3
    assert len(data["discoverability"]["observability"]) >= 4
    assert len(data["discoverability"]["scenarios"]) >= 4
    scenario_names = {
        scenario["name"] for scenario in data["discoverability"]["scenarios"]
    }
    assert "Drop-in Start Go Extend Grow" in scenario_names
    assert "User Start Go Observe" in scenario_names


@pytest.mark.asyncio
async def test_api_discoverability_graph(api_client):
    """Discoverability graph endpoint should expose actionable map output."""
    response = await api_client.get(
        "/api/v1/discoverability/graph?include_entry_points=true"
        "&include_observability=true&include_scenarios=true&max_next_steps=3"
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["links"]["self"].startswith("/api/v1/discoverability/graph?")
    assert payload["params"]["include_entry_points"] is True
    assert payload["params"]["include_observability"] is True
    assert payload["params"]["include_scenarios"] is True
    assert payload["params"]["max_next_steps"] == 3
    assert payload["nodes"]
    assert payload["edges"]
    assert payload["next_steps"]
    assert any(
        node["path"] == "/api/v1/discoverability/graph" for node in payload["nodes"]
    )
    assert any(
        node["path"] == "/api/v1/observability/overview" for node in payload["nodes"]
    )
    assert any(
        edge["from_node"].startswith("GET /api/v1/discoverability/graph")
        for edge in payload["edges"]
    )

    filtered = await api_client.get(
        "/api/v1/discoverability/graph?path_contains=plans/lineage"
    )
    assert filtered.status_code == 200
    filtered_payload = filtered.json()
    assert filtered_payload["nodes"]
    assert any("plans/lineage" in node["id"] for node in filtered_payload["nodes"])


@pytest.mark.asyncio
async def test_api_observability_overview(api_client):
    """Observability overview should unify live platform state and continuation hints."""
    org = await api_client.post(
        "/api/v1/organizations",
        json={"name": "Observability Org"},
    )
    org.raise_for_status()
    org_id = org.json()["id"]

    portfolio = await api_client.post(
        "/api/v1/portfolios",
        json={"name": "Observability Portfolio", "org_id": org_id},
    )
    portfolio.raise_for_status()
    portfolio_id = portfolio.json()["id"]

    program = await api_client.post(
        "/api/v1/programs",
        json={
            "name": "Observability Program",
            "org_id": org_id,
            "portfolio_id": portfolio_id,
        },
    )
    program.raise_for_status()
    program_id = program.json()["id"]

    project = await api_client.post(
        "/api/v1/projects",
        json={
            "name": "Observability Project",
            "org_id": org_id,
            "portfolio_id": portfolio_id,
            "program_id": program_id,
        },
    )
    project.raise_for_status()
    project_id = project.json()["id"]

    task = await api_client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Observability Task"},
    )
    task.raise_for_status()
    task_id = task.json()["id"]
    blocked = await api_client.post(f"/api/v1/tasks/{task_id}/block")
    blocked.raise_for_status()

    plan = await api_client.post(
        "/api/v1/plans",
        json={
            "name": "Observability Plan",
            "status": "active",
            "format": "json",
            "content": {"steps": ["observe"]},
            "project_id": project_id,
            "task_ids": [task_id],
        },
    )
    plan.raise_for_status()

    response = await api_client.get(
        "/api/v1/observability/overview?queue_limit=2&lineage_limit=5"
        "&retention_limit=3&timeline_days=3"
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["links"]["self"].startswith("/api/v1/observability/overview?")
    assert payload["params"]["timeline_days"] == 3
    assert payload["permissions"]["rollups"] is True
    assert payload["permissions"]["queues"] is True
    assert payload["permissions"]["lineage"] is True
    assert payload["permissions"]["retention"] is True
    assert payload["permissions"]["event_timeline"] is True
    assert payload["attention_summary"]["overall_status"] in {
        "attention",
        "watch",
        "healthy",
        "unknown",
    }
    assert payload["attention_summary"]["total_attention_items"] >= 1
    assert payload["attention_items"]
    assert (
        payload["top_risks_now"] or payload["stalled_flows"] or payload["needs_review"]
    )
    assert payload["recommended_actions"]
    assert payload["recommended_actions"][0]["api_call"].startswith("GET ")
    assert payload["recommended_actions"][0]["cli_command"].startswith(
        "<invoke-prefix> "
    )
    assert all(
        item["cli_command"].startswith("<invoke-prefix> ")
        for item in payload["attention_items"]
    )
    assert payload["rollups"]["projects"]["population"] == "all_non_archived_retained"
    assert payload["rollups"]["projects"]["total_projects"] >= 1
    assert payload["rollups"]["projects"]["blocked_tasks"] >= 1
    assert payload["rollups"]["organizations"]["total_organizations"] >= 1
    assert payload["rollups"]["portfolios"]["total_portfolios"] >= 1
    assert payload["rollups"]["programs"]["total_programs"] >= 1
    assert payload["queues"]
    assert payload["lineage"]["total_plans"] >= 1
    assert payload["retention"]["total_runs"] >= 0
    assert payload["event_timeline"]["window_days"] == 3
    assert len(payload["event_timeline"]["points"]) == 4
    assert payload["next_steps"]


@pytest.mark.asyncio
async def test_api_observability_overview_scope_aware(api_client):
    """Observability overview should degrade gracefully for narrow read keys."""
    from pms.api.dependencies import get_auth_service

    service = await get_auth_service()
    limited_key, _ = await service.create_api_key(
        name="Observability Limited Key",
        scopes=[Scopes.TASKS_READ],
    )

    limited_response = await api_client.get(
        "/api/v1/observability/overview",
        headers={"X-API-Key": limited_key},
    )
    assert limited_response.status_code == 200
    limited_payload = limited_response.json()
    assert limited_payload["permissions"]["rollups"] is False
    assert limited_payload["permissions"]["queues"] is True
    assert limited_payload["permissions"]["lineage"] is False
    assert limited_payload["permissions"]["retention"] is False
    assert limited_payload["permissions"]["event_timeline"] is False
    assert limited_payload["rollups"] is None
    assert limited_payload["queues"] is not None
    assert limited_payload["lineage"] is None
    assert limited_payload["retention"] is None
    assert limited_payload["event_timeline"] is None
    assert limited_payload["warnings"]
    assert limited_payload["attention_summary"]["total_attention_items"] >= 1
    assert limited_payload["top_risks_now"]
    assert limited_payload["recommended_actions"]
    assert any(
        item["category"] == "access" for item in limited_payload["top_risks_now"]
    )


@pytest.mark.asyncio
async def test_api_plan_detail_surfaces_links_focus_and_terminal_reason(api_client):
    """Plan detail should expose operator links and execution framing."""
    project = await api_client.post(
        "/api/v1/projects", json={"name": "Plan Detail Project"}
    )
    project.raise_for_status()
    project_id = project.json()["id"]

    task = await api_client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Plan Detail Task"},
    )
    task.raise_for_status()
    task_id = task.json()["id"]

    plan = await api_client.post(
        "/api/v1/plans",
        json={
            "name": "Plan Detail Plan",
            "status": "active",
            "format": "json",
            "content": {"steps": ["audit"]},
            "project_id": project_id,
            "task_ids": [task_id],
        },
    )
    plan.raise_for_status()
    plan_id = plan.json()["id"]

    response = await api_client.get(f"/api/v1/plans/{plan_id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["links"]["self"] == f"/api/v1/plans/{plan_id}"
    assert payload["links"]["lineage"] == f"/api/v1/plans/lineage?plan_id={plan_id}"
    assert payload["links"]["test_jobs"] == f"/api/v1/plans/{plan_id}/test-jobs"
    assert payload["next_steps"]
    assert payload["status"] == "active"
    assert payload["stored_status"] == "active"
    assert payload["focus_task"]["id"] == task_id
    assert payload["terminal_reason"] is None

    complete = await api_client.post(f"/api/v1/tasks/{task_id}/complete")
    complete.raise_for_status()
    completed_response = await api_client.get(f"/api/v1/plans/{plan_id}")
    completed_payload = completed_response.json()
    assert completed_payload["focus_task"] is None
    assert completed_payload["status"] == "completed"
    assert completed_payload["stored_status"] == "completed"
    assert completed_payload["terminal_reason"] == "plan is already marked completed"


@pytest.mark.asyncio
async def test_api_archived_plan_detail_and_lineage_surface_terminal_reason(api_client):
    """Archived plans should expose explicit terminal reasons across detail and lineage."""
    project = await api_client.post(
        "/api/v1/projects", json={"name": "API Archived Plan Project"}
    )
    project.raise_for_status()
    project_id = project.json()["id"]

    plan = await api_client.post(
        "/api/v1/plans",
        json={
            "name": "API Archived Plan",
            "status": "active",
            "format": "json",
            "content": {"steps": ["archive"]},
            "project_id": project_id,
        },
    )
    plan.raise_for_status()
    plan_id = plan.json()["id"]

    archive = await api_client.patch(
        f"/api/v1/plans/{plan_id}",
        json={"status": "archived"},
    )
    archive.raise_for_status()

    detail_response = await api_client.get(f"/api/v1/plans/{plan_id}")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["status"] == "archived"
    assert detail_payload["stored_status"] == "archived"
    assert detail_payload["terminal_reason"] == "plan is already archived"

    lineage_response = await api_client.get(f"/api/v1/plans/lineage?plan_id={plan_id}")
    assert lineage_response.status_code == 200
    lineage_payload = lineage_response.json()
    lineage_item = next(
        item for item in lineage_payload["items"] if item["plan"]["id"] == plan_id
    )
    assert lineage_item["plan"]["status"] == "archived"
    assert lineage_item["plan"]["stored_status"] == "archived"
    assert lineage_item["plan"]["terminal_reason"] == "plan is already archived"


@pytest.mark.asyncio
async def test_api_plan_list_derives_effective_status_from_terminal_graph(api_client):
    """Plan list should expose and filter by effective lifecycle status."""
    project = await api_client.post(
        "/api/v1/projects", json={"name": "API Effective Status Project"}
    )
    project.raise_for_status()
    project_id = project.json()["id"]

    task = await api_client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Already Done API Task"},
    )
    task.raise_for_status()
    task_id = task.json()["id"]
    complete = await api_client.post(f"/api/v1/tasks/{task_id}/complete")
    complete.raise_for_status()

    plan = await api_client.post(
        "/api/v1/plans",
        json={
            "name": "API Effective Status Plan",
            "status": "active",
            "format": "json",
            "content": {"steps": ["audit"]},
            "project_id": project_id,
            "task_ids": [task_id],
        },
    )
    plan.raise_for_status()
    plan_id = plan.json()["id"]

    completed_list = await api_client.get("/api/v1/plans?status=completed")
    completed_list.raise_for_status()
    completed_item = next(
        item for item in completed_list.json()["items"] if item["id"] == plan_id
    )
    assert completed_item["status"] == "completed"
    assert completed_item["stored_status"] == "active"
    assert completed_item["terminal_reason"] == "all linked tasks are already terminal"

    active_list = await api_client.get("/api/v1/plans?status=active")
    active_list.raise_for_status()
    assert all(item["id"] != plan_id for item in active_list.json()["items"])


@pytest.mark.asyncio
async def test_api_plan_list_keeps_completed_plan_terminal_after_nested_task_comment(
    api_client,
):
    """Completed plans stay terminal after fresh nested task activity."""
    active_project = await api_client.post(
        "/api/v1/projects", json={"name": "API Still Active Plan Project"}
    )
    active_project.raise_for_status()
    active_project_id = active_project.json()["id"]

    active_task = await api_client.post(
        "/api/v1/tasks",
        json={"project_id": active_project_id, "title": "API Active Task"},
    )
    active_task.raise_for_status()
    active_task_id = active_task.json()["id"]

    active_plan = await api_client.post(
        "/api/v1/plans",
        json={
            "name": "API Still Active Plan",
            "status": "active",
            "format": "json",
            "content": {"steps": ["stay-active"]},
            "project_id": active_project_id,
            "task_ids": [active_task_id],
        },
    )
    active_plan.raise_for_status()

    completed_project = await api_client.post(
        "/api/v1/projects", json={"name": "API Fresh Completed Plan Project"}
    )
    completed_project.raise_for_status()
    completed_project_id = completed_project.json()["id"]

    completed_task = await api_client.post(
        "/api/v1/tasks",
        json={"project_id": completed_project_id, "title": "API Done Task"},
    )
    completed_task.raise_for_status()
    completed_task_id = completed_task.json()["id"]
    complete_task = await api_client.post(f"/api/v1/tasks/{completed_task_id}/complete")
    complete_task.raise_for_status()

    completed_plan = await api_client.post(
        "/api/v1/plans",
        json={
            "name": "API Fresh Completed Plan",
            "status": "completed",
            "format": "json",
            "content": {"steps": ["done"]},
            "project_id": completed_project_id,
            "task_ids": [completed_task_id],
        },
    )
    completed_plan.raise_for_status()
    completed_plan_id = completed_plan.json()["id"]

    comment = await api_client.post(
        "/api/v1/comments",
        json={
            "entity_type": "task",
            "entity_id": completed_task_id,
            "body": "API fresh terminal activity",
            "created_by": "tester",
        },
    )
    comment.raise_for_status()

    completed_list = await api_client.get("/api/v1/plans?status=completed")
    completed_list.raise_for_status()
    completed_item = next(
        item
        for item in completed_list.json()["items"]
        if item["id"] == completed_plan_id
    )
    assert completed_item["status"] == "completed"
    assert completed_item["stored_status"] == "completed"
    assert completed_item["terminal_reason"] == "plan is already marked completed"
    assert completed_item["last_activity_at"] is not None

    active_list = await api_client.get("/api/v1/plans?status=active")
    active_list.raise_for_status()
    assert all(item["id"] != completed_plan_id for item in active_list.json()["items"])


@pytest.mark.asyncio
async def test_api_task_detail_surfaces_links_and_next_steps(api_client):
    """Task detail should expose direct continuation links and next steps."""
    project = await api_client.post(
        "/api/v1/projects", json={"name": "Task Detail Project"}
    )
    project.raise_for_status()
    project_id = project.json()["id"]

    task = await api_client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Task Detail Task"},
    )
    task.raise_for_status()
    task_id = task.json()["id"]

    response = await api_client.get(f"/api/v1/tasks/{task_id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["links"]["self"] == f"/api/v1/tasks/{task_id}"
    assert payload["links"]["plans"] == f"/api/v1/plans?task_id={task_id}"
    assert payload["links"]["graph"] == f"/api/v1/tasks/{task_id}/graph"
    assert payload["links"]["evidence"] == f"/api/v1/tasks/{task_id}/evidence"
    assert payload["links"]["proof_bundle"] == f"/api/v1/tasks/{task_id}/proof-bundle"
    assert payload["next_steps"] == [
        f"GET /api/v1/plans?task_id={task_id}",
        f"GET /api/v1/tasks/{task_id}/graph",
        f"GET /api/v1/tasks/{task_id}/evidence",
        f"GET /api/v1/tasks/{task_id}/proof-bundle",
    ]


@pytest.mark.asyncio
async def test_project_operator_overview_surfaces_focus_task(api_client):
    """Project operator overview should expose a project-level task focus."""
    project = await api_client.post(
        "/api/v1/projects",
        json={"name": "Project Operator Focus Project"},
    )
    project.raise_for_status()
    project_id = project.json()["id"]

    task = await api_client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Project Operator Focus Task"},
    )
    task.raise_for_status()
    task_id = task.json()["id"]

    response = await api_client.get(f"/api/v1/projects/{project_id}/operator-overview")
    assert response.status_code == 200
    payload = response.json()
    assert payload["focus_task"]["id"] == task_id
    assert payload["focus_task"]["status"] == "todo"


@pytest.mark.asyncio
async def test_api_health(api_client):
    """Test health check endpoint."""
    response = await api_client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "backend" in data
    assert data["backend"] in ["sqlite", "postgresql"]


@pytest.mark.asyncio
async def test_dashboard_contains_operator_console(api_client):
    """Dashboard UI should expose the operator-console surface."""
    response = await api_client.get("/dashboard")
    assert response.status_code == 200
    body = response.text
    assert "Project Operator Console" in body
    assert 'id="project-operator-panel"' in body
    assert 'id="operator-project-id"' in body
    assert 'id="operator-refresh"' in body


@pytest.mark.asyncio
async def test_create_product_via_api(api_client):
    """Test creating a product via API."""
    response = await api_client.post(
        "/api/v1/products",
        json={
            "name": "API Test Product",
            "description": "Created via API",
            "vision": "Test the API",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "API Test Product"
    assert "id" in data


@pytest.mark.asyncio
async def test_product_api_accepts_custom_open_product_type(api_client):
    """Product type should remain an intentionally open descriptive field."""
    created = await api_client.post(
        "/api/v1/products",
        json={
            "name": "Open Product Type Product",
            "product_type": "internal_capability_mesh",
        },
    )
    assert created.status_code == 201
    assert created.json()["product_type"] == "internal_capability_mesh"

    product_id = created.json()["id"]
    updated = await api_client.patch(
        f"/api/v1/products/{product_id}",
        json={"product_type": "agent_control_plane"},
    )
    assert updated.status_code == 200
    assert updated.json()["product_type"] == "agent_control_plane"


@pytest.mark.asyncio
async def test_update_and_archive_product_via_api(api_client):
    """Test updating and archiving a product via API."""
    created = await api_client.post(
        "/api/v1/products",
        json={"name": "Updatable Product"},
    )
    product_id = created.json()["id"]

    updated = await api_client.patch(
        f"/api/v1/products/{product_id}",
        json={"description": "Updated", "status": "active"},
    )
    assert updated.status_code == 200
    assert updated.json()["description"] == "Updated"

    archived = await api_client.post(f"/api/v1/products/{product_id}/archive")
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"


@pytest.mark.asyncio
async def test_org_team_portfolio_program_flow(api_client):
    """Test organization/team/portfolio/program lifecycle via API."""
    org = await api_client.post(
        "/api/v1/organizations",
        json={
            "name": "API Org",
            "description": "Org via API",
            "owner": "owner@example.com",
            "members": ["owner@example.com"],
        },
    )
    assert org.status_code == 201
    org_id = org.json()["id"]

    teams = await api_client.post(
        "/api/v1/teams",
        json={
            "name": "API Team",
            "org_id": org_id,
            "owner": "lead@example.com",
        },
    )
    assert teams.status_code == 201
    team_id = teams.json()["id"]

    portfolio = await api_client.post(
        "/api/v1/portfolios",
        json={"name": "API Portfolio", "org_id": org_id},
    )
    assert portfolio.status_code == 201
    portfolio_id = portfolio.json()["id"]

    program = await api_client.post(
        "/api/v1/programs",
        json={"name": "API Program", "org_id": org_id, "portfolio_id": portfolio_id},
    )
    assert program.status_code == 201
    program_id = program.json()["id"]

    listed_orgs = await api_client.get("/api/v1/organizations")
    assert listed_orgs.status_code == 200
    assert any(o["id"] == org_id for o in listed_orgs.json()["items"])

    listed_teams = await api_client.get(f"/api/v1/teams?org_id={org_id}")
    assert listed_teams.status_code == 200
    assert any(t["id"] == team_id for t in listed_teams.json()["items"])

    listed_portfolios = await api_client.get(f"/api/v1/portfolios?org_id={org_id}")
    assert listed_portfolios.status_code == 200
    assert any(p["id"] == portfolio_id for p in listed_portfolios.json()["items"])

    listed_programs = await api_client.get(
        f"/api/v1/programs?portfolio_id={portfolio_id}"
    )
    assert listed_programs.status_code == 200
    assert any(p["id"] == program_id for p in listed_programs.json()["items"])

    updated_org = await api_client.patch(
        f"/api/v1/organizations/{org_id}", json={"status": "archived"}
    )
    assert updated_org.status_code == 200
    assert updated_org.json()["status"] == "archived"

    updated_team = await api_client.patch(
        f"/api/v1/teams/{team_id}", json={"status": "archived"}
    )
    assert updated_team.status_code == 200
    assert updated_team.json()["status"] == "archived"

    updated_portfolio = await api_client.patch(
        f"/api/v1/portfolios/{portfolio_id}", json={"status": "archived"}
    )
    assert updated_portfolio.status_code == 200
    assert updated_portfolio.json()["status"] == "archived"

    updated_program = await api_client.patch(
        f"/api/v1/programs/{program_id}", json={"status": "archived"}
    )
    assert updated_program.status_code == 200
    assert updated_program.json()["status"] == "archived"

    summary = await api_client.get(f"/api/v1/organizations/{org_id}/summary")
    assert summary.status_code == 200
    summary_data = summary.json()
    assert summary_data["stats"]["total_teams"] == 1
    assert summary_data["stats"]["total_portfolios"] == 1
    assert summary_data["stats"]["total_programs"] == 1
    assert summary_data["links"]["self"] == f"/api/v1/organizations/{org_id}/summary"
    assert summary_data["params"]["org_id"] == org_id
    assert summary_data["next_steps"]

    portfolio_summary = await api_client.get(
        f"/api/v1/portfolios/{portfolio_id}/summary"
    )
    assert portfolio_summary.status_code == 200
    portfolio_summary_data = portfolio_summary.json()
    assert (
        portfolio_summary_data["links"]["self"]
        == f"/api/v1/portfolios/{portfolio_id}/summary"
    )
    assert portfolio_summary_data["params"]["portfolio_id"] == portfolio_id
    assert portfolio_summary_data["next_steps"]

    program_summary = await api_client.get(f"/api/v1/programs/{program_id}/summary")
    assert program_summary.status_code == 200
    program_summary_data = program_summary.json()
    assert (
        program_summary_data["links"]["self"]
        == f"/api/v1/programs/{program_id}/summary"
    )
    assert program_summary_data["params"]["program_id"] == program_id
    assert program_summary_data["next_steps"]


@pytest.mark.asyncio
async def test_actor_api_routes_and_workload_graph(api_client, api_db):
    """Actor API should expose graph links, ownership, memberships, and workload."""
    actor_service = ActorService(
        api_db,
        EventStore(api_db),
        RevisionStore(api_db),
        MetricsCollector(api_db),
    )
    persona = await actor_service.create_actor(
        name="Security Persona",
        kind=ActorKind.PERSONA,
    )
    alice = await actor_service.create_actor(
        name="Alice Example",
        kind=ActorKind.HUMAN,
    )

    alias_response = await api_client.post(
        f"/api/v1/actors/{persona.handle}/aliases",
        json={"alias": "sec"},
    )
    assert alias_response.status_code == 201

    membership_response = await api_client.post(
        f"/api/v1/actors/{persona.handle}/memberships",
        json={"member": alice.handle, "role": "member"},
    )
    assert membership_response.status_code == 201

    project = await api_client.post(
        "/api/v1/projects", json={"name": "Actor API Project"}
    )
    project_id = project.json()["id"]
    task = await api_client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Persona-Owned Task"},
    )
    task_id = task.json()["id"]
    await api_db.execute(
        "UPDATE tasks SET assignee = ?, assignee_id = ? WHERE id = ?",
        (persona.handle, persona.id, task_id),
    )
    goal = await api_client.post(
        "/api/v1/goals",
        json={
            "name": "Owned Goal",
            "horizon": "short_term",
            "project_id": project_id,
            "owner": alice.handle,
        },
    )
    assert goal.status_code == 201
    goal_id = goal.json()["id"]
    queue = await api_client.post(
        "/api/v1/queues",
        json={
            "name": "Owned Queue",
            "owner": alice.handle,
            "scope_type": "project",
            "scope_id": project_id,
            "filters": {"status": ["todo", "in_progress"]},
        },
    )
    assert queue.status_code == 201
    queue_id = queue.json()["id"]

    listed = await api_client.get("/api/v1/actors")
    assert listed.status_code == 200
    handles = {item["handle"] for item in listed.json()["items"]}
    assert persona.handle in handles
    assert alice.handle in handles

    actor_payload = (await api_client.get(f"/api/v1/actors/{alice.handle}")).json()
    assert actor_payload["actor"]["handle"] == alice.handle
    assert actor_payload["aliases"] == []
    assert (
        actor_payload["memberships"]["parents"][0]["actor"]["handle"] == persona.handle
    )
    assert actor_payload["workload"]["effective"]["total_tasks"] == 1
    assert actor_payload["workload"]["inherited_only"]["total_tasks"] == 1
    assert actor_payload["workload"]["tasks"][0]["title"] == "Persona-Owned Task"
    assert actor_payload["ownership"]["counts"]["goals"] == 1
    assert actor_payload["ownership"]["counts"]["queues"] == 1
    assert actor_payload["ownership"]["items"]["goals"][0]["id"] == goal_id
    assert actor_payload["ownership"]["items"]["queues"][0]["id"] == queue_id
    assert actor_payload["project_workloads"][0]["project_id"] == project_id
    assert actor_payload["project_workloads"][0]["effective"]["total_tasks"] == 1
    assert actor_payload["graph_navigation"]["basis"] == "actor"
    assert (
        actor_payload["graph_navigation"]["links"]["project"]
        == f"/api/v1/projects/{project_id}"
    )
    assert (
        actor_payload["graph_navigation"]["links"]["goal"] == f"/api/v1/goals/{goal_id}"
    )
    assert (
        actor_payload["graph_navigation"]["links"]["queue"]
        == f"/api/v1/queues/{queue_id}"
    )

    persona_payload = (await api_client.get(f"/api/v1/actors/{persona.handle}")).json()
    assert persona_payload["aliases"][0]["alias"] == "sec"
    assert (
        persona_payload["memberships"]["children"][0]["actor"]["handle"] == alice.handle
    )
    assert persona_payload["links"]["tasks"].endswith(f"assignee={persona.handle}")


@pytest.mark.asyncio
async def test_actor_api_surfaces_include_bubbled_activity_and_transition_timestamps(
    api_client, api_db
):
    """Actor API list/show responses should expose deep activity and transition timestamps."""
    actor_service = ActorService(
        api_db,
        EventStore(api_db),
        RevisionStore(api_db),
        MetricsCollector(api_db),
    )
    actor = await actor_service.create_actor(
        name="Alice Example",
        kind=ActorKind.HUMAN,
    )
    label_service = LabelService(api_db, MetricsCollector(api_db))
    comment_service = CommentService(api_db, MetricsCollector(api_db))

    category = await label_service.create_category("Actor API Labels")
    label = await label_service.create_label("actor-api-audit", category_id=category.id)
    await comment_service.add_comment(
        "actor",
        actor.id,
        "Actor API activity note",
        created_by="codex",
    )
    await label_service.assign_label("actor", actor.id, label.id, applied_by="codex")
    await comment_service.add_watcher("actor", actor.id, "codex")

    project = await api_client.post(
        "/api/v1/projects",
        json={"name": "Actor API Recency Project"},
    )
    project_id = project.json()["id"]
    task = await api_client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Actor API Transition Task"},
    )
    task_id = task.json()["id"]
    await api_db.execute(
        "UPDATE tasks SET assignee = ?, assignee_id = ? WHERE id = ?",
        (actor.handle, actor.id, task_id),
    )
    task_repo = TaskRepository(
        api_db,
        EventStore(api_db),
        RevisionStore(api_db),
        MetricsCollector(api_db),
    )
    updated_task = await task_repo.update_status(task_id, TaskStatus.IN_PROGRESS)
    assert updated_task is not None

    listed = await api_client.get("/api/v1/actors")
    assert listed.status_code == 200
    listed_payload = listed.json()
    matching_item = next(
        item for item in listed_payload["items"] if item["id"] == actor.id
    )
    assert matching_item["last_activity_at"] is not None
    assert matching_item["last_transition_at"] is not None

    actor_payload = (await api_client.get(f"/api/v1/actors/{actor.handle}")).json()
    assert actor_payload["last_activity_at"] is not None
    assert actor_payload["last_transition_at"] is not None
    assert (
        actor_payload["actor"]["last_activity_at"] == actor_payload["last_activity_at"]
    )
    assert (
        actor_payload["actor"]["last_transition_at"]
        == actor_payload["last_transition_at"]
    )


@pytest.mark.asyncio
async def test_actor_ownership_payloads_propagate_across_api_surfaces(
    api_client, api_db
):
    """Management and strategic API surfaces should expose canonical actor ownership payloads."""
    actor_service = ActorService(
        api_db,
        EventStore(api_db),
        RevisionStore(api_db),
        MetricsCollector(api_db),
    )
    owner = await actor_service.create_actor(
        name="Alice Example",
        kind=ActorKind.HUMAN,
    )
    member = await actor_service.create_actor(
        name="Security Persona",
        kind=ActorKind.PERSONA,
    )

    product = await api_client.post(
        "/api/v1/products",
        json={"name": "Owned Product", "owner": owner.handle},
    )
    assert product.status_code == 201
    product_payload = product.json()
    assert product_payload["owner"]["id"] == owner.id
    assert product_payload["owner"]["actor"]["handle"] == owner.handle

    org = await api_client.post(
        "/api/v1/organizations",
        json={
            "name": "Owned Org",
            "owner": owner.handle,
            "members": [member.handle],
        },
    )
    assert org.status_code == 201
    org_payload = org.json()
    assert org_payload["owner"]["id"] == owner.id
    assert org_payload["owner"]["actor"]["handle"] == owner.handle
    assert org_payload["members"][0]["actor"]["handle"] == member.handle
    assert org_payload["members"][0]["id"] == member.id
    org_id = org_payload["id"]

    team = await api_client.post(
        "/api/v1/teams",
        json={
            "name": "Owned Team",
            "org_id": org_id,
            "owner": owner.handle,
            "members": [member.handle],
        },
    )
    assert team.status_code == 201
    team_payload = team.json()
    assert team_payload["owner"]["id"] == owner.id
    assert team_payload["members"][0]["actor"]["handle"] == member.handle
    assert team_payload["members"][0]["id"] == member.id

    project = await api_client.post(
        "/api/v1/projects", json={"name": "Owned Goal Project"}
    )
    project_id = project.json()["id"]
    goal = await api_client.post(
        "/api/v1/goals",
        json={
            "name": "Owned Goal",
            "horizon": "short_term",
            "project_id": project_id,
            "owner": owner.handle,
        },
    )
    assert goal.status_code == 201
    goal_payload = goal.json()
    assert goal_payload["owner"]["id"] == owner.id
    assert goal_payload["owner"]["actor"]["handle"] == owner.handle
    goal_id = goal_payload["id"]

    objective = await api_client.post(
        f"/api/v1/goals/{goal_id}/objectives",
        json={"name": "Owned Objective", "owner": owner.handle},
    )
    assert objective.status_code == 201
    objective_payload = objective.json()
    assert objective_payload["owner"]["id"] == owner.id
    assert objective_payload["owner"]["actor"]["handle"] == owner.handle
    objective_id = objective_payload["id"]

    key_result = await api_client.post(
        f"/api/v1/objectives/{objective_id}/key-results",
        json={"name": "Owned KR", "owner": owner.handle},
    )
    assert key_result.status_code == 201
    key_result_payload = key_result.json()
    assert key_result_payload["owner"]["id"] == owner.id
    assert key_result_payload["owner"]["actor"]["handle"] == owner.handle

    goal_summary = await api_client.get(f"/api/v1/goals/{goal_id}/summary")
    assert goal_summary.status_code == 200
    goal_summary_payload = goal_summary.json()
    assert goal_summary_payload["goal"]["owner"]["id"] == owner.id
    assert goal_summary_payload["goal"]["owner"]["actor"]["handle"] == owner.handle
    assert goal_summary_payload["effective_rollup"]["basis"] == "stored_goal"
    assert (
        goal_summary_payload["execution"]["population_basis"]
        == "project_scoped_execution_alias"
    )


@pytest.mark.asyncio
async def test_goal_summary_api_requires_explicit_links_for_multi_goal_projects(
    api_client,
):
    """Multi-goal project summaries should not alias shared project execution into one goal."""
    project = await api_client.post(
        "/api/v1/projects", json={"name": "Goal Scope API Project"}
    )
    project.raise_for_status()
    project_id = project.json()["id"]

    goal_one = await api_client.post(
        "/api/v1/goals",
        json={"name": "Goal Scope One", "project_id": project_id},
    )
    goal_one.raise_for_status()
    goal_one_id = goal_one.json()["id"]

    goal_two = await api_client.post(
        "/api/v1/goals",
        json={"name": "Goal Scope Two", "project_id": project_id},
    )
    goal_two.raise_for_status()

    task = await api_client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Shared Execution Task"},
    )
    task.raise_for_status()
    task_id = task.json()["id"]

    start = await api_client.post(f"/api/v1/tasks/{task_id}/start")
    start.raise_for_status()

    progress = await api_client.post(
        f"/api/v1/tasks/{task_id}/progress",
        json={
            "percent_complete": 35,
            "status_message": "Working",
            "updated_by": "tester",
        },
    )
    progress.raise_for_status()

    summary = await api_client.get(f"/api/v1/goals/{goal_one_id}/summary")
    assert summary.status_code == 200
    payload = summary.json()
    assert (
        payload["execution"]["population_basis"] == "goal_scope_requires_explicit_links"
    )
    assert payload["execution"]["scoped_goal_count"] == 2
    assert payload["execution"]["total_tasks"] == 0
    assert payload["execution"]["focus_task"] is None
    assert payload["execution"]["readiness_state"] == "execution_scope_unlinked"
    assert payload["execution"]["consistency_status"] == "unlinked_goal_execution_scope"
    assert payload["execution"]["consistency_reason"] == (
        "project has 2 retained goals; link tasks through goal/objective plans to claim execution"
    )


@pytest.mark.asyncio
async def test_org_portfolio_program_dashboard_via_api(api_client):
    """Test dashboard endpoints for org/portfolio/program."""
    org = await api_client.post(
        "/api/v1/organizations",
        json={"name": "Dashboard Org"},
    )
    org_id = org.json()["id"]

    portfolio = await api_client.post(
        "/api/v1/portfolios",
        json={"name": "Dashboard Portfolio", "org_id": org_id},
    )
    portfolio_id = portfolio.json()["id"]

    program = await api_client.post(
        "/api/v1/programs",
        json={
            "name": "Dashboard Program",
            "org_id": org_id,
            "portfolio_id": portfolio_id,
        },
    )
    program_id = program.json()["id"]

    org_dash = await api_client.get("/api/v1/organizations/dashboard")
    assert org_dash.status_code == 200
    org_payload = org_dash.json()
    assert "links" in org_payload
    assert "next_steps" in org_payload
    assert "params" in org_payload
    assert org_payload["links"]["self"].startswith("/api/v1/organizations/dashboard?")
    org_item = next(
        item for item in org_payload["items"] if item["organization"]["id"] == org_id
    )
    assert "digest" in org_item
    assert "next_actions" in org_item
    assert "evidence" in org_item
    assert "retention" in org_item

    portfolio_dash = await api_client.get(
        f"/api/v1/portfolios/dashboard?org_id={org_id}"
    )
    assert portfolio_dash.status_code == 200
    portfolio_payload = portfolio_dash.json()
    assert "links" in portfolio_payload
    assert "next_steps" in portfolio_payload
    assert "params" in portfolio_payload
    assert portfolio_payload["links"]["self"].startswith(
        "/api/v1/portfolios/dashboard?"
    )
    portfolio_item = next(
        item
        for item in portfolio_payload["items"]
        if item["portfolio"]["id"] == portfolio_id
    )
    assert "digest" in portfolio_item
    assert "next_actions" in portfolio_item
    assert "evidence" in portfolio_item
    assert "retention" in portfolio_item

    program_dash = await api_client.get(
        f"/api/v1/programs/dashboard?portfolio_id={portfolio_id}"
    )
    assert program_dash.status_code == 200
    program_payload = program_dash.json()
    assert "links" in program_payload
    assert "next_steps" in program_payload
    assert "params" in program_payload
    assert program_payload["links"]["self"].startswith("/api/v1/programs/dashboard?")
    program_item = next(
        item for item in program_payload["items"] if item["program"]["id"] == program_id
    )
    assert "digest" in program_item
    assert "next_actions" in program_item
    assert "evidence" in program_item
    assert "retention" in program_item


@pytest.mark.asyncio
async def test_plan_lineage_dashboard_via_api(api_client, api_db):
    """Test plan lineage dashboard endpoint."""
    project = await api_client.post(
        "/api/v1/projects",
        json={"name": "Lineage API Project"},
    )
    project_id = project.json()["id"]

    task_one = await api_client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Lineage Task One"},
    )
    task_two = await api_client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Lineage Task Two"},
    )
    task_ids = [task_one.json()["id"], task_two.json()["id"]]

    plan = await api_client.post(
        "/api/v1/plans",
        json={
            "name": "Lineage Plan",
            "status": "active",
            "format": "json",
            "content": {"stages": ["plan", "test"]},
            "project_id": project_id,
            "task_ids": task_ids,
        },
    )
    plan_id = plan.json()["id"]

    evidence_resp = await api_client.post(
        f"/api/v1/tasks/{task_ids[0]}/evidence",
        json={
            "evidence_type": "scm_commit",
            "reference": "api-commit-1",
            "description": "Lineage evidence",
        },
    )
    evidence_resp.raise_for_status()

    now = datetime.now().isoformat()
    await api_db.execute(
        """
        INSERT INTO test_servers (
            id, instance_id, name, project_id, config, public_ip, private_ip,
            state, region, availability_zone, hourly_price, estimated_cost,
            launched_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "server-api-1",
            "i-api-123",
            "api-test-server",
            project_id,
            "{}",
            "127.0.0.1",
            "127.0.0.1",
            "running",
            "us-east-1",
            "us-east-1a",
            0.0,
            0.0,
            now,
        ),
    )
    await api_db.execute(
        """
        INSERT INTO test_runs (
            id, server_id, project_id, config, success, exit_code,
            stdout, stderr, duration_seconds, started_at, finished_at, logs, artifacts
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "run-api-1",
            "server-api-1",
            project_id,
            json.dumps({"plan_id": plan_id, "task_ids": task_ids}),
            1,
            0,
            "ok",
            "",
            3.3,
            now,
            now,
            "{}",
            "{}",
        ),
    )
    await api_db.commit()

    lineage = await api_client.get(f"/api/v1/plans/lineage?project_id={project_id}")
    assert lineage.status_code == 200
    data = lineage.json()
    assert data["totals"]["total_plans"] >= 1
    assert data["totals"]["total_test_runs"] >= 1
    lineage_item = next(item for item in data["items"] if item["plan"]["id"] == plan_id)
    assert lineage_item["plan"]["status"] == "active"
    assert lineage_item["plan"]["stored_status"] == "active"
    assert lineage_item["plan"]["terminal_reason"] is None
    assert data["totals"]["total_evidence"] >= 1
    assert data["totals"]["total_code_evidence"] >= 1
    assert "links" in data
    assert "next_steps" in data
    assert "params" in data
    assert data["links"]["guide"] == "/api/v1/"
    assert data["links"]["self"].startswith("/api/v1/plans/lineage?")
    assert lineage_item["tasks"]
    assert "evidence_gate" in lineage_item["tasks"][0]


@pytest.mark.asyncio
async def test_create_task_via_api(api_client):
    """Test creating a task via API."""
    # First create a project
    proj_response = await api_client.post(
        "/api/v1/projects",
        json={"name": "API Test Project"},
    )
    project_id = proj_response.json()["id"]

    # Create task
    response = await api_client.post(
        "/api/v1/tasks",
        json={
            "project_id": project_id,
            "title": "API Test Task",
            "complexity_points": 50,
            "priority": "high",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "API Test Task"
    assert data["complexity_points"] == 50
    assert data["current_progress_percent"] == 0


@pytest.mark.asyncio
async def test_update_project_via_api(api_client):
    """Test updating a project via API."""
    created = await api_client.post(
        "/api/v1/projects",
        json={"name": "Updatable Project"},
    )
    project_id = created.json()["id"]

    updated = await api_client.patch(
        f"/api/v1/projects/{project_id}",
        json={"description": "Updated project", "status": "active"},
    )
    assert updated.status_code == 200
    assert updated.json()["description"] == "Updated project"


@pytest.mark.asyncio
async def test_update_task_via_api(api_client):
    """Test updating a task via API."""
    proj_response = await api_client.post(
        "/api/v1/projects",
        json={"name": "API Update Project"},
    )
    project_id = proj_response.json()["id"]

    task_response = await api_client.post(
        "/api/v1/tasks",
        json={
            "project_id": project_id,
            "title": "API Update Task",
            "priority": "medium",
        },
    )
    task_id = task_response.json()["id"]

    update = await api_client.patch(
        f"/api/v1/tasks/{task_id}",
        json={
            "title": "API Updated Title",
            "description": "Updated via API",
            "priority": "critical",
            "complexity_points": 60,
            "completion_criteria": [
                "Expose first-class attention items in the overview payload",
                "Document the response shape in the manual API reference",
            ],
        },
    )

    assert update.status_code == 200
    data = update.json()
    assert data["title"] == "API Updated Title"
    assert data["description"] == "Updated via API"
    assert data["priority"] == "critical"
    assert data["complexity_points"] == 60
    assert data["completion_criteria"] == [
        "Expose first-class attention items in the overview payload",
        "Document the response shape in the manual API reference",
    ]
    assert data["completion_ready"] is False


@pytest.mark.asyncio
async def test_create_update_complete_goal_via_api(api_client):
    """Test goal lifecycle via API."""
    created = await api_client.post(
        "/api/v1/goals",
        json={
            "name": "API Test Goal",
            "description": "Track outcome",
            "horizon": "short_term",
            "progress_percent": 15,
        },
    )
    assert created.status_code == 201
    goal_id = created.json()["id"]

    updated = await api_client.patch(
        f"/api/v1/goals/{goal_id}",
        json={"progress_percent": 55, "status": "on_hold"},
    )
    assert updated.status_code == 200
    assert updated.json()["progress_percent"] == 55
    assert updated.json()["status"] == "on_hold"

    completed = await api_client.post(f"/api/v1/goals/{goal_id}/complete")
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_goal_objective_key_result_flow(api_client):
    """Test objective and key result flow via API."""
    goal = await api_client.post(
        "/api/v1/goals",
        json={"name": "Goal for Objectives", "horizon": "short_term"},
    )
    goal_id = goal.json()["id"]

    objective = await api_client.post(
        f"/api/v1/goals/{goal_id}/objectives",
        json={"name": "Objective 1", "progress_percent": 0},
    )
    assert objective.status_code == 201
    objective_id = objective.json()["id"]

    key_result = await api_client.post(
        f"/api/v1/objectives/{objective_id}/key-results",
        json={"name": "KR 1", "current_value": 5, "target_value": 10},
    )
    assert key_result.status_code == 201
    key_result_id = key_result.json()["id"]

    updated = await api_client.patch(
        f"/api/v1/key-results/{key_result_id}",
        json={"current_value": 10, "target_value": 10},
    )
    assert updated.status_code == 200
    assert updated.json()["progress_percent"] == 100

    summary = await api_client.get(f"/api/v1/goals/{goal_id}/summary")
    assert summary.status_code == 200
    stats = summary.json()["stats"]
    assert stats["objective_count"] == 1
    assert stats["key_result_count"] == 1


@pytest.mark.asyncio
async def test_plan_lifecycle_via_api(api_client):
    """Test plan create/update via API."""
    proj = await api_client.post(
        "/api/v1/projects",
        json={"name": "Plan Project"},
    )
    project_id = proj.json()["id"]

    created = await api_client.post(
        "/api/v1/plans",
        json={
            "name": "API Plan",
            "description": "Plan content",
            "status": "draft",
            "format": "json",
            "content": {"steps": ["a", "b"]},
            "project_id": project_id,
            "task_ids": [],
        },
    )
    assert created.status_code == 201
    plan_id = created.json()["id"]
    assert created.json()["status"] == "draft"

    updated = await api_client.patch(
        f"/api/v1/plans/{plan_id}",
        json={"status": "active", "content": {"steps": ["a", "b", "c"]}},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "active"

    listed = await api_client.get(
        "/api/v1/plans",
        params={"project_id": project_id},
    )
    assert listed.status_code == 200
    assert listed.json()["total_count"] >= 1


@pytest.mark.asyncio
async def test_plan_create_via_api_is_not_rejected_by_nested_transaction(api_client):
    """Plan creation should not fail with nested transaction errors on the server path."""
    proj = await api_client.post(
        "/api/v1/projects",
        json={"name": "Nested Transaction Plan Project"},
    )
    project_id = proj.json()["id"]

    created = await api_client.post(
        "/api/v1/plans",
        json={
            "name": "Nested Transaction Safe Plan",
            "status": "draft",
            "format": "json",
            "content": {"summary": "no nested transaction"},
            "project_id": project_id,
            "task_ids": [],
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["name"] == "Nested Transaction Safe Plan"


@pytest.mark.asyncio
async def test_goal_objective_workflow_via_api(api_client):
    """Test workflow assignment and transitions for goals/objectives."""
    goal = await api_client.post(
        "/api/v1/goals",
        json={"name": "Workflow Goal", "horizon": "short_term"},
    )
    goal_id = goal.json()["id"]

    assign_goal = await api_client.post(
        f"/api/v1/goals/{goal_id}/workflow/assign",
        json={"workflow_name": "sdlc", "initial_state": "concept"},
    )
    assert assign_goal.status_code == 200

    transition_goal = await api_client.post(
        f"/api/v1/goals/{goal_id}/workflow/transition",
        json={"to_state": "idea", "triggered_by": "tester"},
    )
    assert transition_goal.status_code == 200
    assert transition_goal.json()["to_state"] == "idea"

    objective = await api_client.post(
        f"/api/v1/goals/{goal_id}/objectives",
        json={"name": "Workflow Objective"},
    )
    objective_id = objective.json()["id"]

    assign_objective = await api_client.post(
        f"/api/v1/objectives/{objective_id}/workflow/assign",
        json={"workflow_name": "sdlc", "initial_state": "concept"},
    )
    assert assign_objective.status_code == 200

    transition_objective = await api_client.post(
        f"/api/v1/objectives/{objective_id}/workflow/transition",
        json={"to_state": "idea", "triggered_by": "tester"},
    )
    assert transition_objective.status_code == 200
    assert transition_objective.json()["to_state"] == "idea"


@pytest.mark.asyncio
async def test_checkout_task_via_api(api_client, api_db):
    """Test task checkout via API."""
    actor_service = ActorService(
        api_db,
        EventStore(api_db),
        RevisionStore(api_db),
        MetricsCollector(api_db),
    )
    actor = await actor_service.create_actor(
        name="Security Persona",
        kind=ActorKind.PERSONA,
    )

    # Create project and task
    proj = await api_client.post("/api/v1/projects", json={"name": "Checkout Test"})
    project_id = proj.json()["id"]

    task = await api_client.post(
        "/api/v1/tasks",
        json={
            "project_id": project_id,
            "title": "Checkout Task",
            "complexity_points": 25,
        },
    )
    task_id = task.json()["id"]

    # Checkout
    checkout = await api_client.post(
        f"/api/v1/tasks/{task_id}/checkout",
        json={
            "agent_session_id": "test_agent",
            "lease_seconds": 300,
            "actor": actor.handle,
        },
    )
    assert checkout.status_code == 200
    data = checkout.json()
    assert data["checkout"]["agent_session_id"] == "test_agent"
    assert data["checkout"]["actor"]["id"] == actor.id
    assert data["checkout"]["actor"]["actor"]["handle"] == actor.handle
    assert "lease_until" in data["checkout"]

    task_show = await api_client.get(f"/api/v1/tasks/{task_id}")
    assert task_show.status_code == 200
    task_payload = task_show.json()
    assert task_payload["checkout"]["actor"]["id"] == actor.id
    assert task_payload["checkout"]["actor"]["actor"]["handle"] == actor.handle

    status = await api_client.get(
        "/api/v1/checkout/status",
        params={"agent_session_id": "test_agent"},
    )
    assert status.status_code == 200
    status_payload = status.json()
    assert status_payload["checkouts"][0]["checkout"]["actor"]["id"] == actor.id
    assert (
        status_payload["checkouts"][0]["checkout"]["actor"]["actor"]["handle"]
        == actor.handle
    )

    actor_graph = await api_client.get(f"/api/v1/actors/{actor.handle}")
    assert actor_graph.status_code == 200
    actor_payload = actor_graph.json()
    assert actor_payload["workload"]["checkout_scope"] == "direct_only"
    assert actor_payload["workload"]["checkouts"]["active_checkouts"] == 1
    assert actor_payload["workload"]["checkout_tasks"][0]["title"] == "Checkout Task"

    checkout_log = await api_client.get(
        "/api/v1/checkout/log",
        params={"task_id": task_id},
    )
    assert checkout_log.status_code == 200
    log_payload = checkout_log.json()
    assert log_payload["entries"][0]["actor"]["id"] == actor.id
    assert log_payload["entries"][0]["actor"]["actor"]["handle"] == actor.handle


@pytest.mark.asyncio
async def test_checkout_task_via_api_autocreates_runtime_actor(api_client):
    """Checkout without explicit actor should create a runtime-agent actor identity."""
    proj = await api_client.post(
        "/api/v1/projects", json={"name": "Runtime Checkout Test"}
    )
    project_id = proj.json()["id"]

    task = await api_client.post(
        "/api/v1/tasks",
        json={
            "project_id": project_id,
            "title": "Implicit Runtime Checkout Task",
        },
    )
    task_id = task.json()["id"]

    checkout = await api_client.post(
        f"/api/v1/tasks/{task_id}/checkout",
        json={
            "agent_session_id": "runtime-agent-1",
            "lease_seconds": 300,
        },
    )
    assert checkout.status_code == 200
    payload = checkout.json()
    assert payload["checkout"]["agent_session_id"] == "runtime-agent-1"
    assert payload["checkout"]["actor"]["id"]
    assert payload["checkout"]["actor"]["actor"]["kind"] == "runtime_agent"
    assert payload["checkout"]["actor"]["actor"]["handle"] == "runtime-agent-1"


@pytest.mark.asyncio
async def test_task_api_surfaces_resolve_assignee_actor_payloads(api_client, api_db):
    """Task API detail and search surfaces should expose canonical assignee payloads."""
    actor_service = ActorService(
        api_db,
        EventStore(api_db),
        RevisionStore(api_db),
        MetricsCollector(api_db),
    )
    actor = await actor_service.create_actor(
        name="Design Persona",
        kind=ActorKind.PERSONA,
    )

    proj = await api_client.post(
        "/api/v1/projects", json={"name": "Assigned API Project"}
    )
    project_id = proj.json()["id"]

    task = await api_client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Assigned API Task"},
    )
    task_id = task.json()["id"]

    await api_db.execute(
        "UPDATE tasks SET assignee = ?, assignee_id = ? WHERE id = ?",
        (actor.handle, actor.id, task_id),
    )

    task_show = await api_client.get(f"/api/v1/tasks/{task_id}")
    assert task_show.status_code == 200
    task_payload = task_show.json()
    assert task_payload["assignee"]["ref"] == actor.handle
    assert task_payload["assignee"]["id"] == actor.id
    assert task_payload["assignee"]["actor"]["handle"] == actor.handle
    assert task_payload["links"]["actor"] == f"/api/v1/actors/{actor.handle}"

    search = await api_client.get(
        "/api/v1/tasks/search",
        params={"assignee": actor.handle},
    )
    assert search.status_code == 200
    items = search.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == task_id
    assert items[0]["assignee"]["id"] == actor.id
    assert items[0]["assignee"]["actor"]["handle"] == actor.handle


@pytest.mark.asyncio
async def test_portfolio_and_program_api_readbacks_ignore_stale_cached_child_arrays(
    api_client, api_db
):
    """Portfolio/program API payloads should derive hierarchy from graph edges."""
    org = await api_client.post(
        "/api/v1/organizations", json={"name": "Authority API Org"}
    )
    org.raise_for_status()
    org_id = org.json()["id"]

    portfolio = await api_client.post(
        "/api/v1/portfolios",
        json={"name": "Authority API Portfolio", "org_id": org_id},
    )
    portfolio.raise_for_status()
    portfolio_id = portfolio.json()["id"]

    program = await api_client.post(
        "/api/v1/programs",
        json={
            "name": "Authority API Program",
            "org_id": org_id,
            "portfolio_id": portfolio_id,
        },
    )
    program.raise_for_status()
    program_id = program.json()["id"]

    project = await api_client.post(
        "/api/v1/projects",
        json={
            "name": "Authority API Project",
            "org_id": org_id,
            "portfolio_id": portfolio_id,
            "program_id": program_id,
        },
    )
    project.raise_for_status()
    project_id = project.json()["id"]

    goal = await api_client.post(
        "/api/v1/goals",
        json={"name": "Authority API Goal", "project_id": project_id},
    )
    goal.raise_for_status()
    goal_id = goal.json()["id"]

    objective = await api_client.post(
        f"/api/v1/goals/{goal_id}/objectives",
        json={"name": "Authority API Objective"},
    )
    objective.raise_for_status()
    objective_id = objective.json()["id"]

    portfolio_columns = {
        str(row["name"])
        for row in await api_db.fetch_all("PRAGMA table_info(portfolios)")
    }
    assert "project_ids" not in portfolio_columns
    assert "goal_ids" not in portfolio_columns
    assert "objective_ids" not in portfolio_columns

    program_columns = {
        str(row["name"])
        for row in await api_db.fetch_all("PRAGMA table_info(programs)")
    }
    assert "project_ids" not in program_columns
    assert "goal_ids" not in program_columns
    assert "objective_ids" not in program_columns

    portfolio_show = await api_client.get(f"/api/v1/portfolios/{portfolio_id}")
    assert portfolio_show.status_code == 200
    portfolio_payload = portfolio_show.json()
    assert portfolio_payload["project_ids"] == [project_id]
    assert portfolio_payload["goal_ids"] == []
    assert portfolio_payload["objective_ids"] == []
    assert portfolio_payload["effective_goal_ids"] == [goal_id]
    assert portfolio_payload["effective_objective_ids"] == [objective_id]

    program_show = await api_client.get(f"/api/v1/programs/{program_id}")
    assert program_show.status_code == 200
    program_payload = program_show.json()
    assert program_payload["project_ids"] == [project_id]
    assert program_payload["goal_ids"] == []
    assert program_payload["objective_ids"] == []
    assert program_payload["effective_goal_ids"] == [goal_id]
    assert program_payload["effective_objective_ids"] == [objective_id]

    portfolio_summary = await api_client.get(
        f"/api/v1/portfolios/{portfolio_id}/summary"
    )
    assert portfolio_summary.status_code == 200
    portfolio_summary_payload = portfolio_summary.json()
    assert portfolio_summary_payload["portfolio"]["project_ids"] == [project_id]
    assert portfolio_summary_payload["portfolio"]["goal_ids"] == []
    assert portfolio_summary_payload["portfolio"]["objective_ids"] == []
    assert portfolio_summary_payload["portfolio"]["effective_goal_ids"] == [goal_id]
    assert portfolio_summary_payload["portfolio"]["effective_objective_ids"] == [
        objective_id
    ]
    assert portfolio_summary_payload["stats"]["total_projects"] == 1
    assert portfolio_summary_payload["stats"]["total_goals"] == 1
    assert portfolio_summary_payload["stats"]["total_objectives"] == 1

    program_summary = await api_client.get(f"/api/v1/programs/{program_id}/summary")
    assert program_summary.status_code == 200
    program_summary_payload = program_summary.json()
    assert program_summary_payload["program"]["project_ids"] == [project_id]
    assert program_summary_payload["program"]["goal_ids"] == []
    assert program_summary_payload["program"]["objective_ids"] == []
    assert program_summary_payload["program"]["effective_goal_ids"] == [goal_id]
    assert program_summary_payload["program"]["effective_objective_ids"] == [
        objective_id
    ]
    assert program_summary_payload["stats"]["total_projects"] == 1
    assert program_summary_payload["stats"]["total_goals"] == 1
    assert program_summary_payload["stats"]["total_objectives"] == 1


@pytest.mark.asyncio
async def test_portfolio_and_program_api_expose_direct_and_effective_strategic_links(
    api_client,
):
    """Portfolio/program responses should separate direct links from effective scope."""
    org = await api_client.post(
        "/api/v1/organizations", json={"name": "Direct Link API Org"}
    )
    org.raise_for_status()
    org_id = org.json()["id"]

    seed_project = await api_client.post(
        "/api/v1/projects",
        json={"name": "Direct Link Seed Project", "org_id": org_id},
    )
    seed_project.raise_for_status()
    seed_project_id = seed_project.json()["id"]

    goal = await api_client.post(
        "/api/v1/goals",
        json={"name": "Direct Link Goal", "project_id": seed_project_id},
    )
    goal.raise_for_status()
    goal_id = goal.json()["id"]

    objective = await api_client.post(
        f"/api/v1/goals/{goal_id}/objectives",
        json={"name": "Direct Link Objective"},
    )
    objective.raise_for_status()
    objective_id = objective.json()["id"]

    portfolio = await api_client.post(
        "/api/v1/portfolios",
        json={
            "name": "Direct Link Portfolio",
            "org_id": org_id,
            "goal_ids": [goal_id],
            "objective_ids": [objective_id],
        },
    )
    portfolio.raise_for_status()
    portfolio_payload = portfolio.json()
    assert portfolio_payload["project_ids"] == []
    assert portfolio_payload["goal_ids"] == [goal_id]
    assert portfolio_payload["objective_ids"] == [objective_id]
    assert portfolio_payload["effective_goal_ids"] == [goal_id]
    assert portfolio_payload["effective_objective_ids"] == [objective_id]

    program = await api_client.post(
        "/api/v1/programs",
        json={
            "name": "Direct Link Program",
            "org_id": org_id,
            "portfolio_id": portfolio_payload["id"],
            "goal_ids": [goal_id],
            "objective_ids": [objective_id],
        },
    )
    program.raise_for_status()
    program_payload = program.json()
    assert program_payload["project_ids"] == []
    assert program_payload["goal_ids"] == [goal_id]
    assert program_payload["objective_ids"] == [objective_id]
    assert program_payload["effective_goal_ids"] == [goal_id]
    assert program_payload["effective_objective_ids"] == [objective_id]


@pytest.mark.asyncio
async def test_task_detail_exposes_linked_plan_refs_and_plan_list_filters_by_task(
    api_client,
):
    """Task detail and plan list should resolve reverse task→plan links symmetrically."""
    project = await api_client.post(
        "/api/v1/projects", json={"name": "Task Plan API Project"}
    )
    project.raise_for_status()
    project_id = project.json()["id"]

    linked_task = await api_client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Linked Plan Task"},
    )
    linked_task.raise_for_status()
    linked_task_id = linked_task.json()["id"]

    unrelated_task = await api_client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Unrelated Plan Task"},
    )
    unrelated_task.raise_for_status()
    unrelated_task_id = unrelated_task.json()["id"]

    linked_plan = await api_client.post(
        "/api/v1/plans",
        json={
            "name": "Linked Task Plan",
            "status": "active",
            "format": "json",
            "content": {"steps": ["trace"]},
            "project_id": project_id,
            "task_ids": [linked_task_id],
        },
    )
    linked_plan.raise_for_status()
    linked_plan_id = linked_plan.json()["id"]

    unrelated_plan = await api_client.post(
        "/api/v1/plans",
        json={
            "name": "Unrelated Task Plan",
            "status": "active",
            "format": "json",
            "content": {"steps": ["ignore"]},
            "project_id": project_id,
            "task_ids": [unrelated_task_id],
        },
    )
    unrelated_plan.raise_for_status()

    task_show = await api_client.get(f"/api/v1/tasks/{linked_task_id}")
    assert task_show.status_code == 200
    task_payload = task_show.json()
    assert task_payload["links"]["plans"] == f"/api/v1/plans?task_id={linked_task_id}"
    assert task_payload["linked_plan_count"] == 1
    assert task_payload["linked_plans"][0]["id"] == linked_plan_id
    assert (
        task_payload["linked_plans"][0]["links"]["self"]
        == f"/api/v1/plans/{linked_plan_id}"
    )

    filtered = await api_client.get("/api/v1/plans", params={"task_id": linked_task_id})
    assert filtered.status_code == 200
    filtered_payload = filtered.json()
    assert filtered_payload["params"]["task_id"] == linked_task_id
    assert filtered_payload["links"]["self"].endswith(
        f"task_id={linked_task_id}&limit=100&offset=0"
    )
    assert [item["id"] for item in filtered_payload["items"]] == [linked_plan_id]


@pytest.mark.asyncio
async def test_goal_summary_api_uses_goal_scoped_plan_graph_when_available(api_client):
    """Goal summary API should scope execution to goal-linked plans in multi-goal projects."""
    project = await api_client.post(
        "/api/v1/projects", json={"name": "Goal Summary API Project"}
    )
    project.raise_for_status()
    project_id = project.json()["id"]

    goal_one = await api_client.post(
        "/api/v1/goals",
        json={"name": "Goal One", "project_id": project_id},
    )
    goal_one.raise_for_status()
    goal_one_id = goal_one.json()["id"]

    goal_two = await api_client.post(
        "/api/v1/goals",
        json={"name": "Goal Two", "project_id": project_id},
    )
    goal_two.raise_for_status()
    goal_two_id = goal_two.json()["id"]

    task_one = await api_client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Goal One Task"},
    )
    task_one.raise_for_status()
    task_one_id = task_one.json()["id"]

    task_two = await api_client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Goal Two Task"},
    )
    task_two.raise_for_status()
    task_two_id = task_two.json()["id"]

    start_one = await api_client.post(f"/api/v1/tasks/{task_one_id}/start")
    start_one.raise_for_status()
    progress_one = await api_client.post(
        f"/api/v1/tasks/{task_one_id}/progress",
        json={
            "percent_complete": 55,
            "status_message": "Working goal one",
            "updated_by": "tester",
        },
    )
    progress_one.raise_for_status()

    start_two = await api_client.post(f"/api/v1/tasks/{task_two_id}/start")
    start_two.raise_for_status()
    progress_two = await api_client.post(
        f"/api/v1/tasks/{task_two_id}/progress",
        json={
            "percent_complete": 20,
            "status_message": "Working goal two",
            "updated_by": "tester",
        },
    )
    progress_two.raise_for_status()

    linked_plan = await api_client.post(
        "/api/v1/plans",
        json={
            "name": "Goal One Plan",
            "status": "active",
            "format": "json",
            "content": {"steps": ["goal-one"]},
            "project_id": project_id,
            "goal_id": goal_one_id,
            "task_ids": [task_one_id],
        },
    )
    linked_plan.raise_for_status()

    other_plan = await api_client.post(
        "/api/v1/plans",
        json={
            "name": "Goal Two Plan",
            "status": "active",
            "format": "json",
            "content": {"steps": ["goal-two"]},
            "project_id": project_id,
            "goal_id": goal_two_id,
            "task_ids": [task_two_id],
        },
    )
    other_plan.raise_for_status()

    summary = await api_client.get(f"/api/v1/goals/{goal_one_id}/summary")
    assert summary.status_code == 200
    payload = summary.json()
    assert payload["execution"]["population_basis"] == "goal_plan_task_graph"
    assert payload["execution"]["scoped_goal_count"] == 2
    assert payload["execution"]["total_tasks"] == 1
    assert payload["execution"]["in_progress_tasks"] == 1
    assert payload["execution"]["focus_task"]["title"] == "Goal One Task"
    assert (
        payload["execution"]["consistency_status"] == "execution_ahead_of_goal_rollup"
    )


@pytest.mark.asyncio
async def test_goal_list_api_surfaces_effective_rollup_and_lifecycle_timestamps(
    api_client,
):
    """Goal list API should surface execution-aware rollups and bubbled timestamps."""
    project = await api_client.post(
        "/api/v1/projects", json={"name": "Goal List API Lifecycle Project"}
    )
    project.raise_for_status()
    project_id = project.json()["id"]

    goal = await api_client.post(
        "/api/v1/goals",
        json={
            "name": "Goal List API Lifecycle Goal",
            "project_id": project_id,
            "progress_percent": 10,
        },
    )
    goal.raise_for_status()
    goal_id = goal.json()["id"]

    task = await api_client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Goal List API Execution Task"},
    )
    task.raise_for_status()
    task_id = task.json()["id"]

    start = await api_client.post(f"/api/v1/tasks/{task_id}/start")
    start.raise_for_status()
    progress = await api_client.post(
        f"/api/v1/tasks/{task_id}/progress",
        json={
            "percent_complete": 45,
            "status_message": "Implementing",
            "updated_by": "tester",
        },
    )
    progress.raise_for_status()

    listing = await api_client.get("/api/v1/goals", params={"project_id": project_id})
    listing.raise_for_status()
    payload = listing.json()
    item = next(goal for goal in payload["items"] if goal["id"] == goal_id)
    assert item["status"] == "active"
    assert item["progress_percent"] == 10
    assert item["effective_rollup"]["progress_percent"] == 45
    assert item["effective_rollup"]["status"] == "active"
    assert item["effective_rollup"]["basis"] == "execution_projection"
    assert item["last_activity_at"] is not None
    assert item["last_transition_at"] is not None
    assert item["terminal_reason"] is None
    assert item["links"]["self"] == f"/api/v1/goals/{goal_id}"
    assert item["links"]["summary"] == f"/api/v1/goals/{goal_id}/summary"
    assert item["links"]["objectives"] == f"/api/v1/goals/{goal_id}/objectives"
    assert item["links"]["plans"] == f"/api/v1/plans?goal_id={goal_id}"
    assert item["links"]["project"] == f"/api/v1/projects/{project_id}"
    assert item["links"]["tasks"] == f"/api/v1/tasks?project_id={project_id}"
    assert item["links"]["guide"] == "/api/v1/"
    assert item["next_steps"][0] == f"GET /api/v1/goals/{goal_id}/summary"
    assert f"GET /api/v1/goals/{goal_id}/objectives" in item["next_steps"]
    assert f"GET /api/v1/plans?goal_id={goal_id}" in item["next_steps"]
    assert f"GET /api/v1/projects/{project_id}" in item["next_steps"]
    assert f"GET /api/v1/tasks/{task_id}" in item["next_steps"]


@pytest.mark.asyncio
async def test_goal_list_api_promotes_terminal_reason_and_discoverability(
    api_client,
):
    """Goal list API should expose terminal next steps and full discoverability links."""
    project = await api_client.post(
        "/api/v1/projects", json={"name": "Goal List API Terminal Project"}
    )
    project.raise_for_status()
    project_id = project.json()["id"]

    goal = await api_client.post(
        "/api/v1/goals",
        json={"name": "Goal List API Terminal Goal", "project_id": project_id},
    )
    goal.raise_for_status()
    goal_id = goal.json()["id"]

    task = await api_client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Goal List API Terminal Task"},
    )
    task.raise_for_status()
    task_id = task.json()["id"]

    start = await api_client.post(f"/api/v1/tasks/{task_id}/start")
    start.raise_for_status()
    complete = await api_client.post(f"/api/v1/tasks/{task_id}/complete")
    complete.raise_for_status()

    listing = await api_client.get("/api/v1/goals", params={"project_id": project_id})
    listing.raise_for_status()
    payload = listing.json()
    item = next(goal for goal in payload["items"] if goal["id"] == goal_id)
    assert item["effective_rollup"]["status"] == "completed"
    assert item["terminal_reason"] == "all execution tasks are already complete"
    assert item["last_activity_at"] is not None
    assert item["last_transition_at"] is not None
    assert item["links"]["self"] == f"/api/v1/goals/{goal_id}"
    assert item["links"]["summary"] == f"/api/v1/goals/{goal_id}/summary"
    assert item["links"]["plans"] == f"/api/v1/plans?goal_id={goal_id}"
    assert item["links"]["tasks"] == f"/api/v1/tasks?project_id={project_id}"
    assert item["next_steps"][0] == f"GET /api/v1/goals/{goal_id}/summary"
    assert f"GET /api/v1/tasks?project_id={project_id}" in item["next_steps"]
    assert "GET /api/v1/goals?status=completed" in item["next_steps"]


@pytest.mark.asyncio
async def test_goal_detail_api_surfaces_lifecycle_rollups_and_links(api_client):
    """Goal detail API should expose the lifecycle aggregate contract."""
    project = await api_client.post(
        "/api/v1/projects", json={"name": "Goal Detail API Active Project"}
    )
    project.raise_for_status()
    project_id = project.json()["id"]

    goal = await api_client.post(
        "/api/v1/goals",
        json={
            "name": "Goal Detail API Active Goal",
            "project_id": project_id,
            "progress_percent": 10,
        },
    )
    goal.raise_for_status()
    goal_id = goal.json()["id"]

    task = await api_client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Goal Detail API Execution Task"},
    )
    task.raise_for_status()
    task_id = task.json()["id"]

    start = await api_client.post(f"/api/v1/tasks/{task_id}/start")
    start.raise_for_status()
    progress = await api_client.post(
        f"/api/v1/tasks/{task_id}/progress",
        json={
            "percent_complete": 45,
            "status_message": "Implementing",
            "updated_by": "tester",
        },
    )
    progress.raise_for_status()

    detail = await api_client.get(f"/api/v1/goals/{goal_id}")
    detail.raise_for_status()
    payload = detail.json()
    assert payload["id"] == goal_id
    assert payload["status"] == "active"
    assert payload["progress_percent"] == 10
    assert payload["stats"]["objective_count"] == 0
    assert payload["effective_rollup"]["progress_percent"] == 45
    assert payload["effective_rollup"]["status"] == "active"
    assert payload["effective_rollup"]["basis"] == "execution_projection"
    assert payload["effective_hierarchy"]["basis"] == "execution_projection"
    assert payload["execution"]["focus_task"]["id"] == task_id
    assert payload["last_activity_at"] is not None
    assert payload["last_transition_at"] is not None
    assert payload["terminal_reason"] is None
    assert payload["completion_context"] is None
    assert payload["links"]["self"] == f"/api/v1/goals/{goal_id}"
    assert payload["links"]["summary"] == f"/api/v1/goals/{goal_id}/summary"
    assert payload["links"]["objectives"] == f"/api/v1/goals/{goal_id}/objectives"
    assert payload["links"]["plans"] == f"/api/v1/plans?goal_id={goal_id}"
    assert payload["links"]["project"] == f"/api/v1/projects/{project_id}"
    assert payload["links"]["tasks"] == f"/api/v1/tasks?project_id={project_id}"
    assert any(step == f"GET /api/v1/tasks/{task_id}" for step in payload["next_steps"])


@pytest.mark.asyncio
async def test_goal_detail_api_promotes_terminal_reason_and_completion_context(
    api_client,
):
    """Goal detail API should promote terminal lifecycle state and continuation hints."""
    project = await api_client.post(
        "/api/v1/projects", json={"name": "Goal Detail API Terminal Project"}
    )
    project.raise_for_status()
    project_id = project.json()["id"]

    goal = await api_client.post(
        "/api/v1/goals",
        json={"name": "Goal Detail API Terminal Goal", "project_id": project_id},
    )
    goal.raise_for_status()
    goal_id = goal.json()["id"]

    task = await api_client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Goal Detail API Terminal Task"},
    )
    task.raise_for_status()
    task_id = task.json()["id"]

    start = await api_client.post(f"/api/v1/tasks/{task_id}/start")
    start.raise_for_status()
    complete = await api_client.post(f"/api/v1/tasks/{task_id}/complete")
    complete.raise_for_status()

    detail = await api_client.get(f"/api/v1/goals/{goal_id}")
    detail.raise_for_status()
    payload = detail.json()
    assert payload["effective_rollup"]["status"] == "completed"
    assert payload["terminal_reason"] == "all execution tasks are already complete"
    assert payload["execution"]["terminal_reason"] == payload["terminal_reason"]
    assert payload["completion_context"]["summary"].startswith("This goal is terminal.")
    assert payload["completion_context"]["next_steps"]
    assert payload["last_activity_at"] is not None
    assert payload["last_transition_at"] is not None
    assert payload["links"]["self"] == f"/api/v1/goals/{goal_id}"
    assert payload["links"]["summary"] == f"/api/v1/goals/{goal_id}/summary"
    assert payload["links"]["plans"] == f"/api/v1/plans?goal_id={goal_id}"
    assert payload["links"]["tasks"] == f"/api/v1/tasks?project_id={project_id}"
    assert payload["next_steps"]


@pytest.mark.asyncio
async def test_objective_list_api_surfaces_lifecycle_rollups_and_links(api_client):
    """Objective list API should expose lifecycle-aware list payloads."""
    project = await api_client.post(
        "/api/v1/projects", json={"name": "Objective List API Active Project"}
    )
    project.raise_for_status()
    project_id = project.json()["id"]

    goal = await api_client.post(
        "/api/v1/goals",
        json={"name": "Objective List API Active Goal", "project_id": project_id},
    )
    goal.raise_for_status()
    goal_id = goal.json()["id"]

    objective = await api_client.post(
        f"/api/v1/goals/{goal_id}/objectives",
        json={"name": "Objective List API Active Objective", "progress_percent": 10},
    )
    objective.raise_for_status()
    objective_id = objective.json()["id"]

    key_result_a = await api_client.post(
        f"/api/v1/objectives/{objective_id}/key-results",
        json={"name": "Objective List API KR A", "progress_percent": 20},
    )
    key_result_a.raise_for_status()
    key_result_a_id = key_result_a.json()["id"]
    key_result_b = await api_client.post(
        f"/api/v1/objectives/{objective_id}/key-results",
        json={"name": "Objective List API KR B", "progress_percent": 70},
    )
    key_result_b.raise_for_status()

    on_hold = await api_client.patch(
        f"/api/v1/key-results/{key_result_a_id}",
        json={"status": "on_hold", "progress_percent": 20},
    )
    on_hold.raise_for_status()

    listing = await api_client.get(f"/api/v1/goals/{goal_id}/objectives")
    listing.raise_for_status()
    payload = listing.json()
    item = next(obj for obj in payload["items"] if obj["id"] == objective_id)
    assert item["status"] == "active"
    assert item["progress_percent"] == 45
    assert item["project_id"] == project_id
    assert item["effective_rollup"]["progress_percent"] == 45
    assert item["effective_rollup"]["status"] == "active"
    assert item["effective_rollup"]["basis"] == "key_result_rollup"
    assert item["effective_hierarchy"]["key_result_count"] == 2
    assert item["effective_hierarchy"]["completed_key_results"] == 0
    assert item["effective_hierarchy"]["average_progress"] == 45.0
    assert item["last_activity_at"] is not None
    assert item["last_transition_at"] is not None
    assert item["terminal_reason"] is None
    assert item["links"]["self"] == f"/api/v1/objectives/{objective_id}"
    assert item["links"]["goal"] == f"/api/v1/goals/{goal_id}"
    assert item["links"]["goal_summary"] == f"/api/v1/goals/{goal_id}/summary"
    assert (
        item["links"]["key_results"] == f"/api/v1/objectives/{objective_id}/key-results"
    )
    assert item["links"]["project"] == f"/api/v1/projects/{project_id}"
    assert item["links"]["guide"] == "/api/v1/"
    assert item["next_steps"][0] == f"GET /api/v1/objectives/{objective_id}"
    assert f"GET /api/v1/objectives/{objective_id}/key-results" in item["next_steps"]
    assert f"GET /api/v1/goals/{goal_id}" in item["next_steps"]
    assert f"GET /api/v1/goals/{goal_id}/summary" in item["next_steps"]
    assert f"GET /api/v1/projects/{project_id}" in item["next_steps"]


@pytest.mark.asyncio
async def test_objective_detail_api_promotes_terminal_reason_and_completion_context(
    api_client,
):
    """Objective detail API should expose terminal lifecycle state and continuation hints."""
    project = await api_client.post(
        "/api/v1/projects", json={"name": "Objective Detail API Terminal Project"}
    )
    project.raise_for_status()
    project_id = project.json()["id"]

    goal = await api_client.post(
        "/api/v1/goals",
        json={"name": "Objective Detail API Terminal Goal", "project_id": project_id},
    )
    goal.raise_for_status()
    goal_id = goal.json()["id"]

    objective = await api_client.post(
        f"/api/v1/goals/{goal_id}/objectives",
        json={"name": "Objective Detail API Terminal Objective"},
    )
    objective.raise_for_status()
    objective_id = objective.json()["id"]

    key_result = await api_client.post(
        f"/api/v1/objectives/{objective_id}/key-results",
        json={"name": "Objective Detail API Terminal KR", "progress_percent": 100},
    )
    key_result.raise_for_status()
    key_result_id = key_result.json()["id"]

    complete = await api_client.post(f"/api/v1/key-results/{key_result_id}/complete")
    complete.raise_for_status()

    detail = await api_client.get(f"/api/v1/objectives/{objective_id}")
    detail.raise_for_status()
    payload = detail.json()
    assert payload["id"] == objective_id
    assert payload["project_id"] == project_id
    assert payload["status"] == "completed"
    assert payload["progress_percent"] == 100
    assert payload["stats"]["key_result_count"] == 1
    assert payload["stats"]["completed_key_results"] == 1
    assert payload["stats"]["average_progress"] == 100.0
    assert payload["effective_rollup"]["status"] == "completed"
    assert payload["effective_rollup"]["basis"] == "key_result_rollup"
    assert payload["effective_hierarchy"]["key_result_count"] == 1
    assert payload["last_activity_at"] is not None
    assert payload["last_transition_at"] is not None
    assert payload["terminal_reason"] == "all linked key results are already complete"
    assert payload["completion_context"]["summary"].startswith(
        "This objective is terminal."
    )
    assert payload["completion_context"]["next_steps"]
    assert payload["links"]["self"] == f"/api/v1/objectives/{objective_id}"
    assert payload["links"]["goal"] == f"/api/v1/goals/{goal_id}"
    assert payload["links"]["goal_summary"] == f"/api/v1/goals/{goal_id}/summary"
    assert (
        payload["links"]["key_results"]
        == f"/api/v1/objectives/{objective_id}/key-results"
    )
    assert payload["links"]["project"] == f"/api/v1/projects/{project_id}"
    assert payload["next_steps"][0] == f"GET /api/v1/objectives/{objective_id}"
    assert (
        f"GET /api/v1/goals/{goal_id}/objectives?status=completed"
        in payload["next_steps"]
    )


@pytest.mark.asyncio
async def test_key_result_list_api_exposes_lifecycle_rollups_and_discoverability(
    api_client,
):
    """Key result list API should expose lifecycle metadata and parent links."""
    project = await api_client.post(
        "/api/v1/projects", json={"name": "Key Result List API Active Project"}
    )
    project.raise_for_status()
    project_id = project.json()["id"]

    goal = await api_client.post(
        "/api/v1/goals",
        json={"name": "Key Result List API Active Goal", "project_id": project_id},
    )
    goal.raise_for_status()
    goal_id = goal.json()["id"]

    objective = await api_client.post(
        f"/api/v1/goals/{goal_id}/objectives",
        json={"name": "Key Result List API Active Objective"},
    )
    objective.raise_for_status()
    objective_id = objective.json()["id"]

    key_result = await api_client.post(
        f"/api/v1/objectives/{objective_id}/key-results",
        json={"name": "Key Result List API Active KR", "progress_percent": 35},
    )
    key_result.raise_for_status()
    key_result_id = key_result.json()["id"]

    on_hold = await api_client.patch(
        f"/api/v1/key-results/{key_result_id}",
        json={"status": "on_hold", "progress_percent": 35},
    )
    on_hold.raise_for_status()

    back_to_active = await api_client.patch(
        f"/api/v1/key-results/{key_result_id}",
        json={"status": "active", "progress_percent": 35},
    )
    back_to_active.raise_for_status()

    listing = await api_client.get(f"/api/v1/objectives/{objective_id}/key-results")
    listing.raise_for_status()
    payload = listing.json()
    item = next(result for result in payload["items"] if result["id"] == key_result_id)
    assert item["objective_id"] == objective_id
    assert item["goal_id"] == goal_id
    assert item["project_id"] == project_id
    assert item["status"] == "active"
    assert item["progress_percent"] == 35
    assert item["effective_rollup"]["progress_percent"] == 35
    assert item["effective_rollup"]["status"] == "active"
    assert item["effective_rollup"]["basis"] == "stored_key_result"
    assert item["last_activity_at"] is not None
    assert item["last_transition_at"] is not None
    assert item["terminal_reason"] is None
    assert item["links"]["self"] == f"/api/v1/key-results/{key_result_id}"
    assert item["links"]["objective"] == f"/api/v1/objectives/{objective_id}"
    assert (
        item["links"]["objective_key_results"]
        == f"/api/v1/objectives/{objective_id}/key-results"
    )
    assert item["links"]["goal"] == f"/api/v1/goals/{goal_id}"
    assert item["links"]["goal_summary"] == f"/api/v1/goals/{goal_id}/summary"
    assert item["links"]["project"] == f"/api/v1/projects/{project_id}"
    assert item["links"]["guide"] == "/api/v1/"
    assert item["next_steps"][0] == f"GET /api/v1/key-results/{key_result_id}"
    assert f"GET /api/v1/objectives/{objective_id}" in item["next_steps"]
    assert f"GET /api/v1/objectives/{objective_id}/key-results" in item["next_steps"]
    assert f"GET /api/v1/goals/{goal_id}" in item["next_steps"]
    assert f"GET /api/v1/goals/{goal_id}/summary" in item["next_steps"]
    assert f"GET /api/v1/projects/{project_id}" in item["next_steps"]


@pytest.mark.asyncio
async def test_key_result_detail_api_promotes_terminal_reason_and_completion_context(
    api_client,
):
    """Key result detail API should expose terminal lifecycle state and hints."""
    project = await api_client.post(
        "/api/v1/projects", json={"name": "Key Result Detail API Terminal Project"}
    )
    project.raise_for_status()
    project_id = project.json()["id"]

    goal = await api_client.post(
        "/api/v1/goals",
        json={"name": "Key Result Detail API Terminal Goal", "project_id": project_id},
    )
    goal.raise_for_status()
    goal_id = goal.json()["id"]

    objective = await api_client.post(
        f"/api/v1/goals/{goal_id}/objectives",
        json={"name": "Key Result Detail API Terminal Objective"},
    )
    objective.raise_for_status()
    objective_id = objective.json()["id"]

    key_result = await api_client.post(
        f"/api/v1/objectives/{objective_id}/key-results",
        json={"name": "Key Result Detail API Terminal KR", "progress_percent": 100},
    )
    key_result.raise_for_status()
    key_result_id = key_result.json()["id"]

    complete = await api_client.post(f"/api/v1/key-results/{key_result_id}/complete")
    complete.raise_for_status()

    detail = await api_client.get(f"/api/v1/key-results/{key_result_id}")
    detail.raise_for_status()
    payload = detail.json()
    assert payload["id"] == key_result_id
    assert payload["objective_id"] == objective_id
    assert payload["goal_id"] == goal_id
    assert payload["project_id"] == project_id
    assert payload["status"] == "completed"
    assert payload["progress_percent"] == 100
    assert payload["effective_rollup"]["status"] == "completed"
    assert payload["effective_rollup"]["basis"] == "stored_key_result"
    assert payload["last_activity_at"] is not None
    assert payload["last_transition_at"] is not None
    assert payload["terminal_reason"] == "key result is already marked completed"
    assert payload["completion_context"]["summary"].startswith(
        "This key result is terminal."
    )
    assert payload["completion_context"]["next_steps"]
    assert payload["links"]["self"] == f"/api/v1/key-results/{key_result_id}"
    assert payload["links"]["objective"] == f"/api/v1/objectives/{objective_id}"
    assert (
        payload["links"]["objective_key_results"]
        == f"/api/v1/objectives/{objective_id}/key-results"
    )
    assert payload["links"]["goal"] == f"/api/v1/goals/{goal_id}"
    assert payload["links"]["goal_summary"] == f"/api/v1/goals/{goal_id}/summary"
    assert payload["links"]["project"] == f"/api/v1/projects/{project_id}"
    assert payload["links"]["guide"] == "/api/v1/"
    assert payload["next_steps"][0] == f"GET /api/v1/key-results/{key_result_id}"
    assert (
        f"GET /api/v1/objectives/{objective_id}/key-results?status=completed"
        in payload["next_steps"]
    )


@pytest.mark.asyncio
async def test_goal_summary_api_promotes_terminal_reason_and_timestamps(api_client):
    """Goal summary API should promote terminal execution state and timestamps."""
    project = await api_client.post(
        "/api/v1/projects", json={"name": "Goal Summary API Terminal Project"}
    )
    project.raise_for_status()
    project_id = project.json()["id"]

    goal = await api_client.post(
        "/api/v1/goals",
        json={"name": "Goal Summary API Terminal Goal", "project_id": project_id},
    )
    goal.raise_for_status()
    goal_id = goal.json()["id"]

    task = await api_client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Goal Summary API Terminal Task"},
    )
    task.raise_for_status()
    task_id = task.json()["id"]

    start = await api_client.post(f"/api/v1/tasks/{task_id}/start")
    start.raise_for_status()
    complete = await api_client.post(f"/api/v1/tasks/{task_id}/complete")
    complete.raise_for_status()

    summary = await api_client.get(f"/api/v1/goals/{goal_id}/summary")
    summary.raise_for_status()
    payload = summary.json()
    assert payload["terminal_reason"] == "all execution tasks are already complete"
    assert payload["execution"]["terminal_reason"] == payload["terminal_reason"]
    assert payload["completion_context"]["summary"].startswith("This goal is terminal.")
    assert payload["completion_context"]["next_steps"]
    assert payload["last_activity_at"] is not None
    assert payload["last_transition_at"] is not None
    assert payload["links"]["self"] == f"/api/v1/goals/{goal_id}/summary"
    assert payload["links"]["goal"] == f"/api/v1/goals/{goal_id}"
    assert payload["links"]["objectives"] == f"/api/v1/goals/{goal_id}/objectives"
    assert payload["links"]["plans"] == f"/api/v1/plans?goal_id={goal_id}"
    assert payload["next_steps"]


@pytest.mark.asyncio
async def test_renew_and_release_checkout_via_api(api_client):
    """Test renew and release checkout via API."""
    proj = await api_client.post("/api/v1/projects", json={"name": "Renew Test"})
    project_id = proj.json()["id"]

    task = await api_client.post(
        "/api/v1/tasks",
        json={
            "project_id": project_id,
            "title": "Renew Task",
            "complexity_points": 10,
        },
    )
    task_id = task.json()["id"]

    await api_client.post(
        f"/api/v1/tasks/{task_id}/checkout",
        json={"agent_session_id": "renew_agent", "lease_seconds": 300},
    )

    renewed = await api_client.post(
        f"/api/v1/tasks/{task_id}/checkout/renew",
        params={"agent_session_id": "renew_agent", "lease_seconds": 300},
    )
    assert renewed.status_code == 200

    released = await api_client.post(
        f"/api/v1/tasks/{task_id}/checkout/release",
        params={"agent_session_id": "renew_agent"},
    )
    assert released.status_code == 200


@pytest.mark.asyncio
async def test_checkout_status_force_release_cleanup(api_client):
    """Test checkout status, force release, and cleanup via API."""
    proj = await api_client.post("/api/v1/projects", json={"name": "Status Test"})
    project_id = proj.json()["id"]

    task = await api_client.post(
        "/api/v1/tasks",
        json={
            "project_id": project_id,
            "title": "Status Task",
            "complexity_points": 10,
        },
    )
    task_id = task.json()["id"]

    await api_client.post(
        f"/api/v1/tasks/{task_id}/checkout",
        json={"agent_session_id": "status_agent", "lease_seconds": 300},
    )

    status = await api_client.get(
        "/api/v1/checkout/status",
        params={"agent_session_id": "status_agent"},
    )
    assert status.status_code == 200
    data = status.json()
    assert data["count"] == 1
    assert data["checkouts"][0]["id"] == task_id

    force_release = await api_client.post(
        f"/api/v1/tasks/{task_id}/checkout/force-release",
        params={"released_by": "admin", "reason": "override"},
    )
    assert force_release.status_code == 200
    assert force_release.json()["status"] == "force_released"

    status_after = await api_client.get(
        "/api/v1/checkout/status",
        params={"agent_session_id": "status_agent"},
    )
    assert status_after.status_code == 200
    assert status_after.json()["count"] == 0

    cleanup = await api_client.post(
        "/api/v1/checkout/cleanup",
        params={"dry_run": True},
    )
    assert cleanup.status_code == 200
    assert cleanup.json()["count"] == 0

    log = await api_client.get(
        "/api/v1/checkout/log",
        params={"task_id": task_id, "limit": 10},
    )
    assert log.status_code == 200
    log_data = log.json()
    assert log_data["count"] >= 2

    log_with_filters = await api_client.get(
        "/api/v1/checkout/log",
        params={
            "task_id": task_id,
            "action": "checkout",
            "success": True,
            "include_metadata": True,
        },
    )
    assert log_with_filters.status_code == 200
    log_payload = log_with_filters.json()
    assert log_payload["count"] >= 1


@pytest.mark.asyncio
async def test_progress_update_via_api(api_client):
    """Test progress update via API."""
    # Create project and task
    proj = await api_client.post("/api/v1/projects", json={"name": "Progress Test"})
    project_id = proj.json()["id"]

    task = await api_client.post(
        "/api/v1/tasks",
        json={
            "project_id": project_id,
            "title": "Progress Task",
            "complexity_points": 100,
        },
    )
    task_id = task.json()["id"]

    # Update progress
    progress = await api_client.post(
        f"/api/v1/tasks/{task_id}/progress",
        json={
            "percent_complete": 75,
            "status_message": "Almost done",
            "updated_by": "test_agent",
        },
    )
    assert progress.status_code == 200
    data = progress.json()
    assert data["percent_complete"] == 75


@pytest.mark.asyncio
async def test_progress_update_to_100_auto_completes_task_via_api(api_client):
    """A 100% progress update should complete the task on the API path too."""
    proj = await api_client.post(
        "/api/v1/projects", json={"name": "Progress Auto Complete Test"}
    )
    project_id = proj.json()["id"]

    task = await api_client.post(
        "/api/v1/tasks",
        json={
            "project_id": project_id,
            "title": "Progress Auto Complete Task",
            "complexity_points": 20,
        },
    )
    task_id = task.json()["id"]

    progress = await api_client.post(
        f"/api/v1/tasks/{task_id}/progress",
        json={
            "percent_complete": 100,
            "status_message": "Finished through progress",
            "updated_by": "test_agent",
        },
    )
    assert progress.status_code == 200
    assert progress.json()["percent_complete"] == 100

    refreshed_task = await api_client.get(f"/api/v1/tasks/{task_id}")
    assert refreshed_task.status_code == 200
    task_payload = refreshed_task.json()
    assert task_payload["status"] == "done"
    assert task_payload["current_progress_percent"] == 100


@pytest.mark.asyncio
async def test_progress_timeline_via_api(api_client):
    """Test progress timeline via API."""
    proj = await api_client.post("/api/v1/projects", json={"name": "Timeline Test"})
    project_id = proj.json()["id"]

    task = await api_client.post(
        "/api/v1/tasks",
        json={
            "project_id": project_id,
            "title": "Timeline Task",
            "complexity_points": 20,
        },
    )
    task_id = task.json()["id"]

    await api_client.post(
        f"/api/v1/tasks/{task_id}/progress",
        json={
            "percent_complete": 10,
            "status_message": "Started",
            "updated_by": "timeline_agent",
        },
    )

    timeline = await api_client.get(f"/api/v1/tasks/{task_id}/progress/timeline")
    assert timeline.status_code == 200
    assert timeline.json()["current_percent"] == 10


@pytest.mark.asyncio
async def test_workflow_list_assign_transition(api_client):
    """Test workflow list, assign, and transition."""
    workflows = await api_client.get("/api/v1/workflows")
    assert workflows.status_code == 200
    assert "workflows" in workflows.json()

    proj = await api_client.post("/api/v1/projects", json={"name": "Workflow API"})
    project_id = proj.json()["id"]

    task = await api_client.post(
        "/api/v1/tasks",
        json={
            "project_id": project_id,
            "title": "Workflow API Task",
            "complexity_points": 30,
        },
    )
    task_id = task.json()["id"]

    assign = await api_client.post(
        f"/api/v1/tasks/{task_id}/workflow/assign",
        json={"workflow_name": "sdlc", "initial_state": "concept"},
    )
    assert assign.status_code == 200

    transition = await api_client.post(
        f"/api/v1/tasks/{task_id}/workflow/transition",
        json={"to_state": "idea", "triggered_by": "tester"},
    )
    assert transition.status_code == 200


@pytest.mark.asyncio
async def test_transition_timeline_filters(api_client):
    """Timeline filters should limit transitions by actor/label/time."""
    from datetime import UTC, datetime, timedelta

    proj = await api_client.post("/api/v1/projects", json={"name": "Timeline Filters"})
    project_id = proj.json()["id"]

    task = await api_client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Timeline Task"},
    )
    task_id = task.json()["id"]

    assign = await api_client.post(
        f"/api/v1/tasks/{task_id}/workflow/assign",
        json={"workflow_name": "sdlc", "initial_state": "concept"},
    )
    assert assign.status_code == 200

    transition = await api_client.post(
        f"/api/v1/tasks/{task_id}/workflow/transition",
        json={"to_state": "idea", "triggered_by": "timeline_tester"},
    )
    assert transition.status_code == 200

    label_resp = await api_client.post(
        "/api/v1/labels", json={"name": "timeline-label"}
    )
    label_id = label_resp.json()["id"]
    assign_label = await api_client.post(
        "/api/v1/labels/assignments",
        json={
            "entity_type": "task",
            "entity_id": task_id,
            "label_id": label_id,
        },
    )
    assert assign_label.status_code == 201

    by_actor = await api_client.get(
        f"/api/v1/transitions/workflow/task/{task_id}",
        params={"triggered_by": "timeline_tester"},
    )
    assert by_actor.status_code == 200
    payload = by_actor.json()
    assert payload["transitions"]
    assert all(
        item["triggered_by"] == "timeline_tester" for item in payload["transitions"]
    )

    by_label = await api_client.get(
        f"/api/v1/transitions/workflow/task/{task_id}",
        params={"label": "timeline-label"},
    )
    assert by_label.status_code == 200
    assert by_label.json()["transitions"]

    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    empty = await api_client.get(
        f"/api/v1/transitions/workflow/task/{task_id}",
        params={"start_time": future},
    )
    assert empty.status_code == 200
    assert empty.json()["transitions"] == []


@pytest.mark.asyncio
async def test_transition_timeline_rejects_unknown_entity_type_with_suggestion(
    api_client,
):
    response = await api_client.get("/api/v1/transitions/workflow/tas/task_123")
    assert response.status_code == 400
    assert "Unknown entity_type 'tas'." in response.json()["detail"]
    assert "Did you mean 'task'?" in response.json()["detail"]


@pytest.mark.asyncio
async def test_workflow_invalid_transition(api_client):
    """Invalid workflow transition should return 400."""
    proj = await api_client.post("/api/v1/projects", json={"name": "Workflow Invalid"})
    project_id = proj.json()["id"]

    task = await api_client.post(
        "/api/v1/tasks",
        json={
            "project_id": project_id,
            "title": "Workflow Invalid Task",
            "complexity_points": 30,
        },
    )
    task_id = task.json()["id"]

    assign = await api_client.post(
        f"/api/v1/tasks/{task_id}/workflow/assign",
        json={"workflow_name": "sdlc", "initial_state": "concept"},
    )
    assert assign.status_code == 200

    bad = await api_client.post(
        f"/api/v1/tasks/{task_id}/workflow/transition",
        json={"to_state": "production", "triggered_by": "tester"},
    )
    assert bad.status_code == 400


@pytest.mark.asyncio
async def test_workflow_align_auto(api_client):
    """Workflow align should auto-advance to a terminal state."""
    proj = await api_client.post("/api/v1/projects", json={"name": "Workflow Align"})
    project_id = proj.json()["id"]

    task = await api_client.post(
        "/api/v1/tasks",
        json={
            "project_id": project_id,
            "title": "Workflow Align Task",
            "complexity_points": 5,
        },
    )
    task_id = task.json()["id"]

    assign = await api_client.post(
        f"/api/v1/tasks/{task_id}/workflow/assign",
        json={"workflow_name": "agile", "initial_state": "backlog"},
    )
    assert assign.status_code == 200

    complete = await api_client.post(f"/api/v1/tasks/{task_id}/complete")
    assert complete.status_code == 200

    align = await api_client.post(
        f"/api/v1/tasks/{task_id}/workflow/align",
        json={"triggered_by": "tester"},
    )
    assert align.status_code == 200
    assert align.json()["aligned"] is True

    task_state = await api_client.get(f"/api/v1/tasks/{task_id}")
    assert task_state.status_code == 200
    assert task_state.json()["current_state"] == "done"


@pytest.mark.asyncio
async def test_workflow_align_goal_objective(api_client):
    """Workflow align should work for goals and objectives."""
    goal = await api_client.post(
        "/api/v1/goals",
        json={"name": "Align Goal", "horizon": "short_term"},
    )
    goal_id = goal.json()["id"]

    objective = await api_client.post(
        f"/api/v1/goals/{goal_id}/objectives",
        json={"name": "Align Objective"},
    )
    objective_id = objective.json()["id"]

    goal_assign = await api_client.post(
        f"/api/v1/goals/{goal_id}/workflow/assign",
        json={"workflow_name": "agile", "initial_state": "backlog"},
    )
    assert goal_assign.status_code == 200

    objective_assign = await api_client.post(
        f"/api/v1/objectives/{objective_id}/workflow/assign",
        json={"workflow_name": "agile", "initial_state": "backlog"},
    )
    assert objective_assign.status_code == 200

    goal_complete = await api_client.post(f"/api/v1/goals/{goal_id}/complete")
    assert goal_complete.status_code == 200
    objective_complete = await api_client.post(
        f"/api/v1/objectives/{objective_id}/complete"
    )
    assert objective_complete.status_code == 200

    goal_align = await api_client.post(
        "/api/v1/workflow/align",
        json={
            "entity_id": goal_id,
            "entity_type": "goal",
            "triggered_by": "tester",
        },
    )
    assert goal_align.status_code == 200
    assert goal_align.json()["aligned"] is True

    objective_align = await api_client.post(
        "/api/v1/workflow/align",
        json={
            "entity_id": objective_id,
            "entity_type": "objective",
            "triggered_by": "tester",
        },
    )
    assert objective_align.status_code == 200
    assert objective_align.json()["aligned"] is True

    goal_state = await api_client.get(f"/api/v1/goals/{goal_id}")
    assert goal_state.status_code == 200
    assert goal_state.json()["current_state"] == "done"

    objective_state = await api_client.get(f"/api/v1/objectives/{objective_id}")
    assert objective_state.status_code == 200
    assert objective_state.json()["current_state"] == "done"


@pytest.mark.asyncio
async def test_checkout_conflict(api_client):
    """Second checkout should conflict."""
    proj = await api_client.post("/api/v1/projects", json={"name": "Conflict Test"})
    project_id = proj.json()["id"]

    task = await api_client.post(
        "/api/v1/tasks",
        json={
            "project_id": project_id,
            "title": "Conflict Task",
            "complexity_points": 10,
        },
    )
    task_id = task.json()["id"]

    first = await api_client.post(
        f"/api/v1/tasks/{task_id}/checkout",
        json={"agent_session_id": "agent_a", "lease_seconds": 300},
    )
    assert first.status_code == 200

    second = await api_client.post(
        f"/api/v1/tasks/{task_id}/checkout",
        json={"agent_session_id": "agent_b", "lease_seconds": 300},
    )
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_auth_scope_enforced(api_db, admin_api_key):
    """Write endpoints should reject read-only keys."""
    from httpx import ASGITransport, AsyncClient

    from pms.api.app import app
    from pms.repositories.api_key_repository import ApiKeyRepository
    from pms.services.auth_service import AuthService

    app.state.db = api_db

    repo = ApiKeyRepository(api_db)
    service = AuthService(repo)
    read_key, _ = await service.create_api_key(
        name="read-only",
        scopes=["tasks:read", "projects:read", "products:read"],
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-API-Key": read_key},
    ) as client:
        response = await client.post(
            "/api/v1/projects",
            json={"name": "Denied Project"},
        )
        assert response.status_code == 403
