"""Tests for discoverability wrappers on major list endpoints."""

from __future__ import annotations

import pytest


def _assert_paginated_discoverability(
    payload: dict[str, object], self_prefix: str
) -> None:
    links_value = payload.get("links")
    assert isinstance(links_value, dict)
    assert links_value.get("guide") == "/api/v1/"
    self_link = links_value.get("self")
    assert isinstance(self_link, str)
    assert self_link.startswith(self_prefix)

    next_steps_value = payload.get("next_steps")
    assert isinstance(next_steps_value, list)
    assert next_steps_value

    params_value = payload.get("params")
    assert isinstance(params_value, dict)


@pytest.mark.asyncio
async def test_major_list_endpoints_include_discoverability_wrappers(
    api_client,
) -> None:
    """Core list/query endpoints should expose links/next_steps/params."""
    org_response = await api_client.post(
        "/api/v1/organizations",
        json={"name": "Discoverability Org"},
    )
    org_response.raise_for_status()
    org_id = org_response.json()["id"]

    team_response = await api_client.post(
        "/api/v1/teams",
        json={"name": "Discoverability Team", "org_id": org_id},
    )
    team_response.raise_for_status()

    portfolio_response = await api_client.post(
        "/api/v1/portfolios",
        json={"name": "Discoverability Portfolio", "org_id": org_id},
    )
    portfolio_response.raise_for_status()
    portfolio_id = portfolio_response.json()["id"]

    program_response = await api_client.post(
        "/api/v1/programs",
        json={
            "name": "Discoverability Program",
            "org_id": org_id,
            "portfolio_id": portfolio_id,
        },
    )
    program_response.raise_for_status()
    program_id = program_response.json()["id"]

    product_response = await api_client.post(
        "/api/v1/products",
        json={"name": "Discoverability Product"},
    )
    product_response.raise_for_status()
    product_id = product_response.json()["id"]

    project_response = await api_client.post(
        "/api/v1/projects",
        json={
            "name": "Discoverability Project",
            "org_id": org_id,
            "portfolio_id": portfolio_id,
            "program_id": program_id,
            "product_id": product_id,
        },
    )
    project_response.raise_for_status()
    project_id = project_response.json()["id"]

    goal_response = await api_client.post(
        "/api/v1/goals",
        json={
            "name": "Discoverability Goal",
            "horizon": "short_term",
            "project_id": project_id,
            "product_id": product_id,
        },
    )
    goal_response.raise_for_status()
    goal_id = goal_response.json()["id"]

    objective_response = await api_client.post(
        f"/api/v1/goals/{goal_id}/objectives",
        json={"name": "Discoverability Objective"},
    )
    objective_response.raise_for_status()
    objective_id = objective_response.json()["id"]

    key_result_response = await api_client.post(
        f"/api/v1/objectives/{objective_id}/key-results",
        json={"name": "Discoverability KR"},
    )
    key_result_response.raise_for_status()
    assert key_result_response.json()["id"]

    plan_response = await api_client.post(
        "/api/v1/plans",
        json={
            "name": "Discoverability Plan",
            "status": "active",
            "format": "json",
            "content": {"steps": ["discover"]},
            "project_id": project_id,
        },
    )
    plan_response.raise_for_status()
    plan_id = plan_response.json()["id"]

    job_response = await api_client.post(
        f"/api/v1/plans/{plan_id}/test-jobs",
        json={
            "name": "Discoverability Plan Job",
            "project_path": ".",
            "test_command": "echo ok",
        },
    )
    job_response.raise_for_status()

    queue_response = await api_client.post(
        "/api/v1/queues",
        json={
            "name": "Discoverability Queue",
            "scope_type": "project",
            "scope_id": project_id,
            "filters": {"statuses": ["todo", "in_progress"]},
        },
    )
    queue_response.raise_for_status()
    queue_id = queue_response.json()["id"]

    organizations_list = await api_client.get("/api/v1/organizations?limit=10&offset=0")
    organizations_list.raise_for_status()
    _assert_paginated_discoverability(
        organizations_list.json(),
        "/api/v1/organizations?",
    )

    teams_list = await api_client.get(
        f"/api/v1/teams?org_id={org_id}&limit=10&offset=0"
    )
    teams_list.raise_for_status()
    _assert_paginated_discoverability(teams_list.json(), "/api/v1/teams?")

    portfolios_list = await api_client.get(
        f"/api/v1/portfolios?org_id={org_id}&limit=10&offset=0"
    )
    portfolios_list.raise_for_status()
    _assert_paginated_discoverability(portfolios_list.json(), "/api/v1/portfolios?")

    programs_list = await api_client.get(
        f"/api/v1/programs?portfolio_id={portfolio_id}&limit=10&offset=0"
    )
    programs_list.raise_for_status()
    _assert_paginated_discoverability(programs_list.json(), "/api/v1/programs?")

    products_list = await api_client.get("/api/v1/products?limit=10&offset=0")
    products_list.raise_for_status()
    _assert_paginated_discoverability(products_list.json(), "/api/v1/products?")

    projects_list = await api_client.get("/api/v1/projects?limit=10&offset=0")
    projects_list.raise_for_status()
    _assert_paginated_discoverability(projects_list.json(), "/api/v1/projects?")

    goals_list = await api_client.get(
        f"/api/v1/goals?project_id={project_id}&limit=10&offset=0"
    )
    goals_list.raise_for_status()
    _assert_paginated_discoverability(goals_list.json(), "/api/v1/goals?")

    objectives_list = await api_client.get(
        f"/api/v1/goals/{goal_id}/objectives?limit=10&offset=0"
    )
    objectives_list.raise_for_status()
    _assert_paginated_discoverability(
        objectives_list.json(),
        f"/api/v1/goals/{goal_id}/objectives?",
    )

    key_results_list = await api_client.get(
        f"/api/v1/objectives/{objective_id}/key-results?limit=10&offset=0"
    )
    key_results_list.raise_for_status()
    _assert_paginated_discoverability(
        key_results_list.json(),
        f"/api/v1/objectives/{objective_id}/key-results?",
    )

    plans_list = await api_client.get(
        f"/api/v1/plans?project_id={project_id}&limit=10&offset=0"
    )
    plans_list.raise_for_status()
    _assert_paginated_discoverability(plans_list.json(), "/api/v1/plans?")

    plan_jobs_list = await api_client.get(
        f"/api/v1/plans/{plan_id}/test-jobs?limit=10&offset=0"
    )
    plan_jobs_list.raise_for_status()
    _assert_paginated_discoverability(
        plan_jobs_list.json(),
        f"/api/v1/plans/{plan_id}/test-jobs?",
    )

    queues_list = await api_client.get(
        f"/api/v1/queues?scope_id={project_id}&limit=10&offset=0"
    )
    queues_list.raise_for_status()
    _assert_paginated_discoverability(queues_list.json(), "/api/v1/queues?")

    queue_run = await api_client.get(f"/api/v1/queues/{queue_id}/run?limit=10&offset=0")
    queue_run.raise_for_status()
    queue_run_payload = queue_run.json()
    _assert_paginated_discoverability(
        queue_run_payload,
        f"/api/v1/queues/{queue_id}/run?",
    )
    run_links = queue_run_payload["links"]
    assert isinstance(run_links, dict)
    assert run_links.get("queue") == f"/api/v1/queues/{queue_id}"
