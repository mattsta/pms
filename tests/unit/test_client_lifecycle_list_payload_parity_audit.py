from __future__ import annotations

from scripts.audit_client_lifecycle_list_payload_parity import (
    _normalize_plan_list_payload,
    _normalize_task_list_payload,
)


def test_normalize_task_list_payload_reduces_to_semantic_fields() -> None:
    payload = {
        "items": [
            {
                "id": "task-1",
                "title": "Task One",
                "status": "todo",
                "parent_id": None,
                "complexity_points": 3,
                "updated_at": "2026-04-24T00:00:00Z",
            }
        ],
        "total_count": 5,
        "limit": 2,
        "offset": 1,
        "links": {"self": "/api/v1/tasks"},
    }

    normalized = _normalize_task_list_payload(payload)

    assert normalized == {
        "items": [
            {
                "id": "task-1",
                "title": "Task One",
                "status": "todo",
                "parent_id": None,
                "complexity_points": 3,
            }
        ],
        "total_count": 5,
        "limit": 2,
        "offset": 1,
    }


def test_normalize_plan_list_payload_reduces_to_semantic_fields() -> None:
    payload = {
        "items": [
            {
                "id": "plan-1",
                "name": "Plan One",
                "status": "draft",
                "task_ids": ["task-1", "task-2"],
                "updated_at": "2026-04-24T00:00:00Z",
            }
        ],
        "total_count": 2,
        "limit": 1,
        "offset": 1,
        "links": {"self": "/api/v1/plans"},
    }

    normalized = _normalize_plan_list_payload(payload)

    assert normalized == {
        "items": [
            {
                "id": "plan-1",
                "name": "Plan One",
                "status": "draft",
                "task_ids": ["task-1", "task-2"],
            }
        ],
        "total_count": 2,
        "limit": 1,
        "offset": 1,
    }
