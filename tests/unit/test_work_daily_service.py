"""Unit tests for work daily export ownership."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.services.project_service import ProjectService
from pms.services.task_evidence_service import TaskEvidenceService
from pms.services.task_service import TaskService
from pms.services.work_daily_service import WorkDailyService


def _build_work_daily_service(
    db,
) -> tuple[WorkDailyService, ProjectService, TaskService]:
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)
    project_service = ProjectService(db, event_store, revision_store, metrics)
    task_service = TaskService(db, event_store, revision_store, metrics)
    daily_service = WorkDailyService(
        snapshot_service=None,  # type: ignore[arg-type]
        queue_service=None,  # type: ignore[arg-type]
        task_service=task_service,
        project_service=project_service,
        transition_repo=None,  # type: ignore[arg-type]
        test_run_service=None,  # type: ignore[arg-type]
    )
    return daily_service, project_service, task_service


@pytest.mark.asyncio
async def test_export_report_attaches_evidence(db, tmp_path: Path) -> None:
    daily_service, project_service, task_service = _build_work_daily_service(db)
    project = await project_service.create_project(name="Daily Export Unit Project")
    task = await task_service.create_task(project.id, "Daily Export Unit Task")

    export_result = await daily_service.export_report(
        scope_type="project",
        scope_id=project.id,
        scope_name=project.name,
        generated_at=datetime.now(UTC),
        output_format="json",
        content='{"status":"ok"}',
        export_path=str(tmp_path),
        attach_task_id=task.id,
    )

    assert export_result.path.exists()
    evidence_service = TaskEvidenceService(task_service.db, task_service.metrics)
    page = await evidence_service.list_evidence(task.id)
    assert page.total_count == 1
    evidence = page.items[0].evidence
    assert evidence.evidence_type == "work_daily_report"
    assert evidence.reference == str(export_result.path)
    assert evidence.metadata["file_size_bytes"] == export_result.size_bytes


@pytest.mark.asyncio
async def test_export_report_removes_file_when_attachment_fails(
    db,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    daily_service, project_service, task_service = _build_work_daily_service(db)
    project = await project_service.create_project(name="Daily Export Failure Project")
    task = await task_service.create_task(project.id, "Daily Export Failure Task")

    async def fail_add_evidence(self, *args, **kwargs):
        raise RuntimeError("attach failed")

    monkeypatch.setattr(TaskEvidenceService, "add_evidence", fail_add_evidence)

    with pytest.raises(RuntimeError, match="attach failed"):
        await daily_service.export_report(
            scope_type="project",
            scope_id=project.id,
            scope_name=project.name,
            generated_at=datetime.now(UTC),
            output_format="json",
            content='{"status":"failed"}',
            export_path=str(tmp_path),
            attach_task_id=task.id,
        )

    assert not list(tmp_path.glob("work-daily-project-*"))
    evidence_service = TaskEvidenceService(task_service.db, task_service.metrics)
    page = await evidence_service.list_evidence(task.id)
    assert page.total_count == 0
