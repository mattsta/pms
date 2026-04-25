"""Checkout manager for workflow task leasing."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from pms.config.logging import logger
from pms.exceptions.base import TaskCheckoutConflict
from pms.repositories.task_repository import TaskRepository
from pms.services.actor_service import ActorService


class CheckoutManager:
    """Manage task checkout leases with safe release semantics."""

    def __init__(self, task_repo: TaskRepository) -> None:
        self.task_repo = task_repo

    @asynccontextmanager
    async def checkout_task(
        self,
        task_id: str,
        agent_session_id: str,
        lease_seconds: int = 300,
        checkout_actor_id: str | None = None,
        force: bool = False,
        checkout_parent: bool = True,
        release_on_failure: bool = True,
    ) -> AsyncIterator[None]:
        """Checkout a task for the duration of the context."""
        if checkout_actor_id is None:
            actor_service = ActorService(
                self.task_repo.db,
                self.task_repo.events,
                self.task_repo.revisions,
                self.task_repo.metrics,
            )
            checkout_actor = await actor_service.resolve_checkout_actor(
                agent_session_id=agent_session_id,
            )
            checkout_actor_id = checkout_actor.id
        task = await self.task_repo.checkout_task(
            task_id=task_id,
            agent_session_id=agent_session_id,
            lease_seconds=lease_seconds,
            checkout_actor_id=checkout_actor_id,
            force=force,
            checkout_parent=checkout_parent,
        )
        if task is None:
            raise ValueError(f"Task '{task_id}' not found")

        try:
            yield
        except Exception:
            if release_on_failure:
                await self._safe_release(task_id, agent_session_id)
            raise
        else:
            await self._safe_release(task_id, agent_session_id)

    async def _safe_release(self, task_id: str, agent_session_id: str) -> None:
        try:
            await self.task_repo.release_checkout(task_id, agent_session_id)
        except TaskCheckoutConflict as exc:
            logger.warning(
                "Checkout release skipped",
                task_id=task_id,
                agent_session_id=agent_session_id,
                error=str(exc),
            )
