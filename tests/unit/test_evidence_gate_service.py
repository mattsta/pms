"""Unit tests for evidence gate observational metrics behavior."""

from __future__ import annotations

import pytest

from pms.core.metrics import MetricsCollector
from pms.repositories.task_evidence_repository import TaskEvidenceRepository
from pms.services.evidence_gate_service import EvidenceGateService


@pytest.mark.asyncio
async def test_evidence_gate_blocked_result_ignores_metrics_flush_failures(
    db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metrics = MetricsCollector(db)
    service = EvidenceGateService(db, metrics)

    await service.add_gate_rule(
        workflow_id="wf_sdlc",
        entity_type="task",
        from_state="code_review",
        to_state="unit_testing",
        evidence_type="document",
        min_count=1,
        message="attach evidence first",
    )

    async def fail_flush(*args, **kwargs):
        raise RuntimeError("metrics flush failed")

    monkeypatch.setattr(service.metrics, "flush", fail_flush)

    result = await service.evaluate_gates(
        workflow_id="wf_sdlc",
        entity_type="task",
        entity_id="task-evidence-gate-1",
        from_state="code_review",
        to_state="unit_testing",
    )

    assert result.allowed is False
    assert result.reason == "attach evidence first"


@pytest.mark.asyncio
async def test_evidence_gate_allowed_result_ignores_metrics_flush_failures(
    db,
    project_repo,
    task_repo,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metrics = MetricsCollector(db)
    service = EvidenceGateService(db, metrics)
    evidence_repo = TaskEvidenceRepository(db)
    project = await project_repo.create(name="Evidence Gate Metrics Project")
    task = await task_repo.create(project.id, "Evidence Gate Metrics Task")

    await service.add_gate_rule(
        workflow_id="wf_sdlc",
        entity_type="task",
        from_state="code_review",
        to_state="unit_testing",
        evidence_type="document",
        min_count=1,
    )
    await evidence_repo.create(
        task_id=task.id,
        evidence_type="document",
        reference="doc-1",
        description="proof",
        created_by="tester",
    )

    async def fail_flush(*args, **kwargs):
        raise RuntimeError("metrics flush failed")

    monkeypatch.setattr(service.metrics, "flush", fail_flush)

    result = await service.evaluate_gates(
        workflow_id="wf_sdlc",
        entity_type="task",
        entity_id=task.id,
        from_state="code_review",
        to_state="unit_testing",
    )

    assert result.allowed is True
    assert result.reason is None
