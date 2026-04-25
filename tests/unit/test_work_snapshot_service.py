"""Unit tests for work snapshot mutation ownership."""

from __future__ import annotations

import pytest

from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.repositories.work_snapshot_review_repository import (
    WorkSnapshotReviewRepository,
)
from pms.services.lineage_service import LineageService
from pms.services.organization_service import OrganizationService
from pms.services.portfolio_service import PortfolioService
from pms.services.program_service import ProgramService
from pms.services.project_service import ProjectService
from pms.services.test_run_retention_service import TestRunRetentionService
from pms.services.work_snapshot_service import WorkSnapshotService


@pytest.mark.asyncio
async def test_mark_reviewed_rolls_back_when_metrics_flush_fails(
    db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)

    project_service = ProjectService(db, event_store, revision_store, metrics)
    organization_service = OrganizationService(db, event_store, revision_store, metrics)
    portfolio_service = PortfolioService(db, event_store, revision_store, metrics)
    program_service = ProgramService(db, event_store, revision_store, metrics)
    lineage_service = LineageService(db, event_store, revision_store, metrics)
    retention_service = TestRunRetentionService(db, metrics)
    snapshot_service = WorkSnapshotService(
        db,
        metrics,
        project_service=project_service,
        organization_service=organization_service,
        program_service=program_service,
        portfolio_service=portfolio_service,
        lineage_service=lineage_service,
        retention_service=retention_service,
    )
    review_repo = WorkSnapshotReviewRepository(db)
    project = await project_service.create_project(name="Atomic Snapshot Project")

    async def fail_flush(*args, **kwargs):
        raise RuntimeError("metrics flush failed")

    monkeypatch.setattr(snapshot_service.metrics, "flush", fail_flush)

    with pytest.raises(RuntimeError, match="metrics flush failed"):
        await snapshot_service.mark_reviewed(
            scope_type="project",
            scope_id=project.id,
            reviewed_by="tester",
            note="atomic review",
        )

    latest = await review_repo.get_latest("project", project.id)
    assert latest is None


@pytest.mark.asyncio
async def test_get_snapshot_ignores_observational_metrics_flush_failures(
    db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)

    project_service = ProjectService(db, event_store, revision_store, metrics)
    organization_service = OrganizationService(db, event_store, revision_store, metrics)
    portfolio_service = PortfolioService(db, event_store, revision_store, metrics)
    program_service = ProgramService(db, event_store, revision_store, metrics)
    lineage_service = LineageService(db, event_store, revision_store, metrics)
    retention_service = TestRunRetentionService(db, metrics)
    snapshot_service = WorkSnapshotService(
        db,
        metrics,
        project_service=project_service,
        organization_service=organization_service,
        program_service=program_service,
        portfolio_service=portfolio_service,
        lineage_service=lineage_service,
        retention_service=retention_service,
    )
    project = await project_service.create_project(
        name="Observational Snapshot Project"
    )

    async def fail_flush(*args, **kwargs):
        raise RuntimeError("metrics flush failed")

    monkeypatch.setattr(snapshot_service.metrics, "flush", fail_flush)

    snapshot = await snapshot_service.get_snapshot("project", project.id)

    assert snapshot is not None
    assert snapshot.scope_id == project.id
