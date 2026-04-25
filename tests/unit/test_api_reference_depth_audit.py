from __future__ import annotations

from pathlib import Path

from scripts.audit_api_reference_depth import (
    _parse_contract_routes,
    audit_api_reference_depth,
)


def test_parse_contract_routes_reads_markdown_table() -> None:
    markdown = """
| Method | Path | Purpose | Request Body Type | Success Response |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/tasks` | List Tasks | `None` | `200` TaskListResponse |
| `POST` | `/api/v1/tasks` | Create Task | `TaskCreate` | `201` TaskResponse |
"""

    routes = _parse_contract_routes(markdown)
    assert len(routes) == 2
    assert routes[0].method == "GET"
    assert routes[0].path == "/api/v1/tasks"
    assert routes[1].method == "POST"
    assert routes[1].path == "/api/v1/tasks"


def test_audit_api_reference_depth_has_no_uncovered_routes() -> None:
    audit = audit_api_reference_depth(
        api_reference_path=Path("docs/API_REFERENCE.md"),
        contract_path=Path("docs/API_RESPONSE_CONTRACTS.md"),
    )

    assert audit.total_routes > 0
    assert audit.uncovered_total == 0
    assert audit.local_percent >= 20.0
