"""Service for managing test run retention policies."""

from __future__ import annotations

from typing import TypedDict

from pms.core.metrics import MetricsCollector
from pms.models.test_run_retention_policy import TestRunRetentionPolicy
from pms.repositories.base import QueryResult
from pms.repositories.test_run_retention_policy_repository import (
    TestRunRetentionPolicyRepository,
)


class TestRunRetentionPolicyService:
    """Service for creating and updating retention budgets."""

    def __init__(
        self,
        repo: TestRunRetentionPolicyRepository,
        metrics: MetricsCollector,
    ) -> None:
        self._repo = repo
        self.metrics = metrics

    async def upsert_policy(
        self,
        scope_type: str,
        scope_id: str,
        max_log_bytes: int,
        max_artifact_bytes: int,
        max_age_days: int,
        notes: str | None = None,
    ) -> TestRunRetentionPolicy:
        async with self._repo.db.transaction():
            existing = await self._repo.get_by_scope(scope_type, scope_id)
            if existing:
                updated = await self._repo.update(
                    existing.id,
                    max_log_bytes=max_log_bytes,
                    max_artifact_bytes=max_artifact_bytes,
                    max_age_days=max_age_days,
                    notes=notes,
                )
                if updated:
                    await self.metrics.record_counter(
                        "test_run_retention_policy.updated",
                        labels={"scope_type": updated.scope_type},
                    )
                    await self.metrics.flush()
                    return updated

            created = await self._repo.create(
                scope_type=scope_type,
                scope_id=scope_id,
                max_log_bytes=max_log_bytes,
                max_artifact_bytes=max_artifact_bytes,
                max_age_days=max_age_days,
                notes=notes,
            )
            await self.metrics.record_counter(
                "test_run_retention_policy.created",
                labels={"scope_type": created.scope_type},
            )
            await self.metrics.flush()
            return created

    async def update_policy(
        self,
        policy_id: str,
        *,
        max_log_bytes: int | None = None,
        max_artifact_bytes: int | None = None,
        max_age_days: int | None = None,
        notes: str | None = None,
    ) -> TestRunRetentionPolicy | None:
        async with self._repo.db.transaction():
            updated = await self._repo.update(
                policy_id,
                max_log_bytes=max_log_bytes,
                max_artifact_bytes=max_artifact_bytes,
                max_age_days=max_age_days,
                notes=notes,
            )
            if updated:
                await self.metrics.record_counter(
                    "test_run_retention_policy.updated",
                    labels={"scope_type": updated.scope_type},
                )
                await self.metrics.flush()
            return updated

    async def list_policies(
        self,
        scope_type: str | None = None,
        scope_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
        *,
        include_archived: bool = False,
    ) -> QueryResult[TestRunRetentionPolicy]:
        return await self._repo.list(
            scope_type=scope_type,
            scope_id=scope_id,
            limit=limit,
            offset=offset,
            include_archived=include_archived,
        )

    async def get_policy(self, policy_id: str) -> TestRunRetentionPolicy | None:
        return await self._repo.get_by_id(policy_id)

    async def get_policy_by_scope(
        self, scope_type: str, scope_id: str
    ) -> TestRunRetentionPolicy | None:
        return await self._repo.get_by_scope(scope_type, scope_id)

    async def archive_policy(self, policy_id: str) -> bool:
        async with self._repo.db.transaction():
            archived = await self._repo.delete(policy_id)
            if archived:
                await self.metrics.record_counter("test_run_retention_policy.archived")
                await self.metrics.flush()
            return archived

    async def restore_policy(self, policy_id: str) -> TestRunRetentionPolicy | None:
        async with self._repo.db.transaction():
            restored = await self._repo.restore(policy_id)
            if restored:
                await self.metrics.record_counter("test_run_retention_policy.restored")
                await self.metrics.flush()
            return restored

    @staticmethod
    def normalize_scope_type(scope_type: str) -> str:
        scope = scope_type.strip().lower()
        if scope not in {"project", "organization"}:
            raise ValueError("scope_type must be project or organization")
        return scope

    class PolicyLimits(TypedDict):
        max_log_bytes: int
        max_artifact_bytes: int
        max_age_days: int

    @staticmethod
    def normalize_limits(
        max_log_bytes: int | None,
        max_artifact_bytes: int | None,
        max_age_days: int | None,
    ) -> PolicyLimits:
        return {
            "max_log_bytes": max_log_bytes or 0,
            "max_artifact_bytes": max_artifact_bytes or 0,
            "max_age_days": max_age_days or 0,
        }
