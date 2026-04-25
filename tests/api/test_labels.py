"""API tests for label management and workflow gates."""

from __future__ import annotations


def test_label_gate_blocks_and_allows_transition(test_client, admin_api_key):
    headers = {"X-API-Key": admin_api_key}

    project_resp = test_client.post(
        "/api/v1/projects",
        headers=headers,
        json={"name": "Label Project", "description": "Label gate test", "tags": []},
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    task_resp = test_client.post(
        "/api/v1/tasks",
        headers=headers,
        json={
            "project_id": project_id,
            "title": "Gate Task",
            "description": "Needs review label",
            "priority": "high",
            "complexity_points": 5,
            "tags": [],
        },
    )
    assert task_resp.status_code == 201
    task_id = task_resp.json()["id"]

    category_resp = test_client.post(
        "/api/v1/labels/categories",
        headers=headers,
        json={"name": "Review", "description": "Review gate", "is_exclusive": True},
    )
    assert category_resp.status_code == 201
    category_id = category_resp.json()["id"]

    label_resp = test_client.post(
        "/api/v1/labels",
        headers=headers,
        json={
            "name": "needs-review",
            "category_id": category_id,
            "description": "Require review",
        },
    )
    assert label_resp.status_code == 201
    label_id = label_resp.json()["id"]

    gate_resp = test_client.post(
        "/api/v1/labels/gates",
        headers=headers,
        json={
            "workflow_id": "wf_sdlc",
            "entity_type": "task",
            "from_state": "code_review",
            "to_state": "unit_testing",
            "rule_type": "require_label",
            "label_id": label_id,
            "message": "Add needs-review before unit testing",
        },
    )
    assert gate_resp.status_code == 201

    assign_resp = test_client.post(
        f"/api/v1/tasks/{task_id}/workflow/assign",
        headers=headers,
        json={"workflow_name": "sdlc", "initial_state": "code_review"},
    )
    assert assign_resp.status_code == 200

    blocked_resp = test_client.post(
        f"/api/v1/tasks/{task_id}/workflow/transition",
        headers=headers,
        json={"to_state": "unit_testing", "triggered_by": "tester"},
    )
    assert blocked_resp.status_code == 400
    assert "needs-review" in blocked_resp.json()["detail"]

    assignment_resp = test_client.post(
        "/api/v1/labels/assignments",
        headers=headers,
        json={
            "entity_type": "task",
            "entity_id": task_id,
            "label_id": label_id,
            "applied_by": "tester",
        },
    )
    assert assignment_resp.status_code == 201

    allowed_resp = test_client.post(
        f"/api/v1/tasks/{task_id}/workflow/transition",
        headers=headers,
        json={"to_state": "unit_testing", "triggered_by": "tester"},
    )
    assert allowed_resp.status_code == 200
    assert allowed_resp.json()["to_state"] == "unit_testing"


def test_label_assignment_normalizes_entity_type_alias(test_client, admin_api_key):
    headers = {"X-API-Key": admin_api_key}

    org_resp = test_client.post(
        "/api/v1/organizations",
        headers=headers,
        json={"name": "Alias Org", "description": "Alias entity target", "tags": []},
    )
    assert org_resp.status_code == 201
    org_id = org_resp.json()["id"]

    category_resp = test_client.post(
        "/api/v1/labels/categories",
        headers=headers,
        json={"name": "Ops", "description": "Ops labels", "is_exclusive": False},
    )
    assert category_resp.status_code == 201
    category_id = category_resp.json()["id"]

    label_resp = test_client.post(
        "/api/v1/labels",
        headers=headers,
        json={
            "name": "tracked",
            "category_id": category_id,
            "description": "Tracked org",
        },
    )
    assert label_resp.status_code == 201
    label_id = label_resp.json()["id"]

    assignment_resp = test_client.post(
        "/api/v1/labels/assignments",
        headers=headers,
        json={
            "entity_type": "org",
            "entity_id": org_id,
            "label_id": label_id,
            "applied_by": "tester",
        },
    )
    assert assignment_resp.status_code == 201
    assert assignment_resp.json()["entity_type"] == "organization"
