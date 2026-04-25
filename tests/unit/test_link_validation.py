"""Tests for linked-reference validation helpers."""

from __future__ import annotations

import pytest

from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.db.connection import Database
from pms.exceptions import ValidationError
from pms.repositories.product_repository import ProductRepository
from pms.repositories.project_repository import ProjectRepository
from pms.services.link_validation import (
    suggest_reference_matches,
    validate_optional_reference_id,
)


@pytest.fixture
async def product_repo(
    db: Database,
    event_store: EventStore,
    revision_store: RevisionStore,
    metrics_collector: MetricsCollector,
) -> ProductRepository:
    return ProductRepository(db, event_store, revision_store, metrics_collector)


@pytest.mark.asyncio
async def test_validate_optional_reference_id_suggests_id_when_name_is_used(
    project_repo: ProjectRepository,
):
    project = await project_repo.create(name="Gateway Launch")

    with pytest.raises(ValidationError) as exc_info:
        await validate_optional_reference_id(
            project_repo,
            "Gateway Launch",
            field_name="project_id",
            entity_label="Project",
        )

    message = str(exc_info.value)
    assert "project_id expects a project ID" in message
    assert project.id in message


@pytest.mark.asyncio
async def test_validate_optional_reference_id_includes_suggestions_for_partial_match(
    product_repo: ProductRepository,
):
    product = await product_repo.create(name="Gateway Platform")

    with pytest.raises(ValidationError) as exc_info:
        await validate_optional_reference_id(
            product_repo,
            "gateway",
            field_name="product_id",
            entity_label="Product",
        )

    message = str(exc_info.value)
    assert "Did you mean:" in message
    assert product.id in message
    assert "Gateway Platform" in message


@pytest.mark.asyncio
async def test_suggest_reference_matches_uses_name_column_when_available(
    project_repo: ProjectRepository,
):
    project = await project_repo.create(name="Release Control Plane")

    suggestions = await suggest_reference_matches(project_repo, "control")

    assert suggestions
    assert suggestions[0].ref == project.id
    assert suggestions[0].label == "Release Control Plane"
