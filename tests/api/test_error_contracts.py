"""API tests for structured validation and constraint errors."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_goal_create_invalid_product_id_returns_suggestions(api_client):
    product_resp = await api_client.post(
        "/api/v1/products",
        json={"name": "Gateway Platform"},
    )
    product_resp.raise_for_status()
    product = product_resp.json()

    response = await api_client.post(
        "/api/v1/goals",
        json={
            "name": "Ship Gateway",
            "product_id": "Gateway Platform",
        },
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"] == "Validation error"
    assert payload["field"] == "product_id"
    assert "expects a product ID" in payload["detail"]
    assert product["id"] in payload["detail"]
    assert product["id"] in payload["suggestions"][0]


@pytest.mark.asyncio
async def test_project_create_duplicate_name_returns_structured_constraint_error(
    api_client,
):
    first = await api_client.post(
        "/api/v1/projects",
        json={"name": "Constraint Project"},
    )
    first.raise_for_status()

    duplicate = await api_client.post(
        "/api/v1/projects",
        json={"name": "Constraint Project"},
    )

    assert duplicate.status_code == 409
    payload = duplicate.json()
    assert payload["error"] == "Constraint violation"
    assert payload["constraint_kind"] == "unique"
    assert payload["table"] == "projects"
    assert payload["columns"] == ["name"]
    assert payload["suggestions"]
