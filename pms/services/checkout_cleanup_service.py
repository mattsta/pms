"""Background service for cleaning up expired task checkouts."""

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pms.repositories.task_repository import TaskRepository

logger = logging.getLogger(__name__)


class CheckoutCleanupService:
    """
    Background service that periodically cleans up expired task checkouts.

    Runs on a configurable interval (default: 60 seconds) to:
    - Find tasks with expired checkout leases
    - Automatically release them
    - Log expiration events
    - Emit domain events for monitoring

    This ensures agents can't indefinitely hold locks if they crash
    or lose connection.
    """

    def __init__(
        self,
        task_repo: TaskRepository,
        interval_seconds: int = 60,
    ) -> None:
        """
        Initialize cleanup service.

        Args:
            task_repo: TaskRepository for checkout operations
            interval_seconds: How often to run cleanup (default: 60s)
        """
        self.task_repo = task_repo
        self.interval_seconds = interval_seconds
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the cleanup service."""
        if self._running:
            logger.warning("Checkout cleanup service already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            f"Checkout cleanup service started (interval={self.interval_seconds}s)"
        )

    async def stop(self) -> None:
        """Stop the cleanup service gracefully."""
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("Checkout cleanup service stopped")

    async def run_once(self) -> list[str]:
        """
        Run cleanup once (useful for manual triggers or testing).

        Returns:
            List of task IDs that were cleaned up
        """
        try:
            expired_ids = await self.task_repo.cleanup_expired_checkouts()

            if expired_ids:
                logger.info(
                    f"Cleaned up {len(expired_ids)} expired checkouts: "
                    f"{expired_ids[:5]}{'...' if len(expired_ids) > 5 else ''}"
                )

            return expired_ids
        except Exception as e:
            logger.error(f"Error during cleanup: {e}", exc_info=True)
            return []

    async def _run_loop(self) -> None:
        """Main cleanup loop."""
        while self._running:
            try:
                await self.run_once()
                await asyncio.sleep(self.interval_seconds)

            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}", exc_info=True)
                # Continue running even if one iteration fails
                await asyncio.sleep(self.interval_seconds)
