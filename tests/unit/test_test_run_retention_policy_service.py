"""Transactional tests for TestRunRetentionPolicyService."""

from __future__ import annotations

import pytest

from pms.repositories.test_run_retention_policy_repository import (
    TestRunRetentionPolicyRepository as RetentionPolicyRepository,
)
from pms.services.test_run_retention_policy_service import (
    TestRunRetentionPolicyService as RetentionPolicyService,
)


def _build_service(db, metrics_collector) -> RetentionPolicyService:
    repo = RetentionPolicyRepository(db)
    return RetentionPolicyService(repo, metrics_collector)


@pytest.mark.asyncio
async def test_upsert_policy_create_rolls_back_when_metrics_flush_fails(
    db,
    metrics_collector,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(db, metrics_collector)

    async def fail_flush(*args, **kwargs):
        raise RuntimeError("metrics flush failed")

    monkeypatch.setattr(service.metrics, "flush", fail_flush)

    with pytest.raises(RuntimeError, match="metrics flush failed"):
        await service.upsert_policy(
            scope_type="project",
            scope_id="proj-retention-atomic",
            max_log_bytes=10,
            max_artifact_bytes=20,
            max_age_days=30,
            notes="atomic create",
        )

    row = await db.fetch_one(
        "SELECT COUNT(*) AS count FROM test_run_retention_policies"
    )
    assert row is not None
    assert int(row["count"]) == 0


@pytest.mark.asyncio
async def test_update_policy_rolls_back_when_metrics_flush_fails(
    db,
    metrics_collector,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(db, metrics_collector)
    policy = await service.upsert_policy(
        scope_type="project",
        scope_id="proj-retention-update",
        max_log_bytes=10,
        max_artifact_bytes=20,
        max_age_days=30,
        notes="before update",
    )

    async def fail_flush(*args, **kwargs):
        raise RuntimeError("metrics flush failed")

    monkeypatch.setattr(service.metrics, "flush", fail_flush)

    with pytest.raises(RuntimeError, match="metrics flush failed"):
        await service.update_policy(
            policy.id,
            max_log_bytes=99,
            max_artifact_bytes=88,
            max_age_days=77,
            notes="after update",
        )

    refreshed = await service.get_policy(policy.id)
    assert refreshed is not None
    assert refreshed.max_log_bytes == 10
    assert refreshed.max_artifact_bytes == 20
    assert refreshed.max_age_days == 30
    assert refreshed.notes == "before update"


@pytest.mark.asyncio
async def test_archive_policy_rolls_back_when_metrics_flush_fails(
    db,
    metrics_collector,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(db, metrics_collector)
    policy = await service.upsert_policy(
        scope_type="organization",
        scope_id="org-retention-archive",
        max_log_bytes=10,
        max_artifact_bytes=20,
        max_age_days=30,
    )

    async def fail_flush(*args, **kwargs):
        raise RuntimeError("metrics flush failed")

    monkeypatch.setattr(service.metrics, "flush", fail_flush)

    with pytest.raises(RuntimeError, match="metrics flush failed"):
        await service.archive_policy(policy.id)

    refreshed = await service.get_policy(policy.id)
    assert refreshed is not None
    assert refreshed.archived_at is None


@pytest.mark.asyncio
async def test_restore_policy_rolls_back_when_metrics_flush_fails(
    db,
    metrics_collector,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(db, metrics_collector)
    policy = await service.upsert_policy(
        scope_type="organization",
        scope_id="org-retention-restore",
        max_log_bytes=10,
        max_artifact_bytes=20,
        max_age_days=30,
    )
    await service._repo.delete(policy.id)

    async def fail_flush(*args, **kwargs):
        raise RuntimeError("metrics flush failed")

    monkeypatch.setattr(service.metrics, "flush", fail_flush)

    with pytest.raises(RuntimeError, match="metrics flush failed"):
        await service.restore_policy(policy.id)

    row = await db.fetch_one(
        "SELECT archived_at FROM test_run_retention_policies WHERE id = ?",
        (policy.id,),
    )
    assert row is not None
    assert row["archived_at"] is not None
