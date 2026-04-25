"""API tests for task tree endpoint."""

from __future__ import annotations

from typing import Any

import pytest


def _flatten_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for node in nodes:
        flattened.append(node)
        flattened.extend(_flatten_nodes(node.get("children", [])))
    return flattened


@pytest.mark.asyncio
async def test_task_tree(api_client) -> None:
    project_resp = await api_client.post(
        "/api/v1/projects",
        json={"name": "Tree Project"},
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    parent_resp = await api_client.post(
        "/api/v1/tasks",
        json={"project_id": project_id, "title": "Parent Task"},
    )
    assert parent_resp.status_code == 201
    parent_id = parent_resp.json()["id"]

    child_resp = await api_client.post(
        "/api/v1/tasks",
        json={
            "project_id": project_id,
            "title": "Child Task",
            "parent_id": parent_id,
        },
    )
    assert child_resp.status_code == 201
    child_id = child_resp.json()["id"]

    tree_resp = await api_client.get(
        "/api/v1/tasks/tree",
        params={"project_id": project_id},
    )
    assert tree_resp.status_code == 200
    payload = tree_resp.json()
    assert payload["project_id"] == project_id

    flattened = _flatten_nodes(payload["nodes"])
    ids = [node["task"]["id"] for node in flattened]
    assert parent_id in ids
    assert child_id in ids

    root_nodes = payload["nodes"]
    assert root_nodes[0]["task"]["id"] == parent_id
    assert root_nodes[0]["children"][0]["task"]["id"] == child_id

    subtree_resp = await api_client.get(
        "/api/v1/tasks/tree",
        params={"project_id": project_id, "root_task_id": child_id},
    )
    assert subtree_resp.status_code == 200
    subtree = subtree_resp.json()
    assert subtree["nodes"][0]["task"]["id"] == child_id
