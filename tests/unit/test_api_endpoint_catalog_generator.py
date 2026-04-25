from __future__ import annotations

from pathlib import Path

from scripts import generate_api_endpoint_catalog as endpoint_catalog_script
from scripts.generate_api_endpoint_catalog import (
    EndpointCatalog,
    EndpointRoute,
    collect_api_v1_catalog,
    render_catalog_markdown,
)


def test_generate_api_endpoint_catalog_contains_expected_routes() -> None:
    catalog = collect_api_v1_catalog()

    assert catalog.api_v1_total > 0
    assert catalog.api_v1_without_health > 0
    assert catalog.api_v1_total >= catalog.api_v1_without_health

    markdown = render_catalog_markdown(catalog)
    assert "# API Endpoint Catalog" in markdown
    assert "/api/v1/auth/scopes" in markdown
    assert "/api/v1/tasks" in markdown
    assert "/api/v1/workflows" in markdown


def test_run_writes_catalog_with_atomic_helper(monkeypatch, tmp_path: Path) -> None:
    catalog = EndpointCatalog(
        routes=(EndpointRoute(method="GET", path="/api/v1/health"),),
        api_v1_total=1,
        api_v1_without_health=0,
    )
    written: list[tuple[Path, str]] = []

    monkeypatch.setattr(
        endpoint_catalog_script, "collect_api_v1_catalog", lambda: catalog
    )
    monkeypatch.setattr(
        endpoint_catalog_script,
        "format_markdown_with_prettier",
        lambda content, *, filepath: f"formatted::{filepath.name}\n{content}",
    )
    monkeypatch.setattr(
        endpoint_catalog_script,
        "write_text_atomic",
        lambda path, content, **_: written.append((path, content)),
    )

    output_path = tmp_path / "API_ENDPOINT_CATALOG.md"
    assert endpoint_catalog_script.run(output_path=output_path, check_only=False) == 0
    assert written == [
        (
            output_path,
            "formatted::API_ENDPOINT_CATALOG.md\n"
            + endpoint_catalog_script.render_catalog_markdown(catalog),
        )
    ]
