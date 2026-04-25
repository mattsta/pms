"""API tests for custom field definitions and values."""

from __future__ import annotations


def test_custom_fields_api_roundtrip(test_client, admin_api_key) -> None:
    headers = {"X-API-Key": admin_api_key}

    project_resp = test_client.post(
        "/api/v1/projects",
        headers=headers,
        json={"name": "Custom Field API Project", "description": "CF test", "tags": []},
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    task_resp = test_client.post(
        "/api/v1/tasks",
        headers=headers,
        json={
            "project_id": project_id,
            "title": "Custom Field Task",
            "description": "CF task",
            "priority": "medium",
            "complexity_points": 1,
            "tags": [],
        },
    )
    assert task_resp.status_code == 201
    task_id = task_resp.json()["id"]

    field_resp = test_client.post(
        "/api/v1/custom-fields",
        headers=headers,
        json={
            "name": "effort",
            "entity_type": "task",
            "field_type": "number",
            "description": "Effort estimate",
            "options": [],
            "is_required": False,
        },
    )
    assert field_resp.status_code == 201
    field_id = field_resp.json()["id"]

    value_resp = test_client.post(
        f"/api/v1/custom-fields/{field_id}/values",
        headers=headers,
        json={
            "entity_type": "task",
            "entity_id": task_id,
            "value": 3,
            "created_by": "tester",
        },
    )
    assert value_resp.status_code == 201
    assert value_resp.json()["value"]["value"] == 3

    list_resp = test_client.get(
        "/api/v1/custom-fields/values",
        headers=headers,
        params={"entity_type": "task", "entity_id": task_id},
    )
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    assert items
    assert items[0]["definition"]["id"] == field_id
    assert items[0]["value"]["entity_id"] == task_id


def test_custom_fields_api_normalizes_entity_type_alias(
    test_client, admin_api_key
) -> None:
    headers = {"X-API-Key": admin_api_key}

    field_resp = test_client.post(
        "/api/v1/custom-fields",
        headers=headers,
        json={
            "name": "kr-health",
            "entity_type": "keyresult",
            "field_type": "text",
            "description": "KR health note",
            "options": [],
            "is_required": False,
        },
    )
    assert field_resp.status_code == 201
    assert field_resp.json()["entity_type"] == "key_result"


def test_custom_fields_api_rejects_unknown_entity_type_with_suggestion(
    test_client, admin_api_key
) -> None:
    headers = {"X-API-Key": admin_api_key}

    field_resp = test_client.post(
        "/api/v1/custom-fields",
        headers=headers,
        json={
            "name": "bad-type",
            "entity_type": "tas",
            "field_type": "text",
            "description": "Bad entity type",
            "options": [],
            "is_required": False,
        },
    )
    assert field_resp.status_code == 400
    assert "Unknown entity_type 'tas'." in field_resp.json()["detail"]
    assert "Did you mean 'task'?" in field_resp.json()["detail"]
