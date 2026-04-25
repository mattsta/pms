from __future__ import annotations

from pathlib import Path

from scripts.audit_api_reference import (
    ApiRoute,
    audit_api_reference,
    extract_documented_routes,
)


def test_extract_documented_routes_parses_http_blocks() -> None:
    markdown = """
```http
GET /api/v1/tasks?limit=10
X-API-Key: <key>
```

```bash
curl http://localhost:8000/api/v1/tasks
```

```http
POST /api/v1/tasks
Content-Type: application/json
```
"""

    documented = extract_documented_routes(markdown)

    assert documented.http_block_count == 2
    assert documented.routes == (
        ApiRoute(method="GET", path="/api/v1/tasks"),
        ApiRoute(method="POST", path="/api/v1/tasks"),
    )
    assert documented.routes_with_inline_json_body == ()


def test_extract_documented_routes_tracks_inline_json_body_examples() -> None:
    markdown = """
```http
PATCH /api/v1/tasks/{task_id}
Content-Type: application/json

{
  "title": "New title"
}
```
"""

    documented = extract_documented_routes(markdown)
    assert documented.routes_with_inline_json_body == (
        ApiRoute(method="PATCH", path="/api/v1/tasks/{task_id}"),
    )


def test_audit_api_reference_collects_live_and_documented_routes() -> None:
    audit = audit_api_reference(Path("docs/API_REFERENCE.md"))

    assert audit.openapi_total > 0
    assert audit.documented_total > 0
    assert audit.extra_total == 0
    assert audit.missing_body_example_total == 0
