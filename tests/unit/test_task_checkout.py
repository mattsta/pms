"""Unit tests for task checkout/ownership system."""

import pytest

from pms.exceptions.base import TaskCheckoutBlocked, TaskCheckoutConflict
from pms.models import TaskStatus


@pytest.mark.asyncio
class TestTaskCheckout:
    """Test task checkout/ownership functionality."""

    async def test_checkout_task_success(self, task_repo, sample_project):
        """Test successful task checkout."""
        # Create task
        task = await task_repo.create(
            project_id=sample_project.id,
            title="Checkout Test",
            complexity_points=25,
        )

        agent_id = "agent_123"

        # Checkout task
        checked_out = await task_repo.checkout_task(
            task.id,
            agent_id,
            lease_seconds=300,
        )

        assert checked_out is not None
        assert checked_out.checkout_agent_session_id == agent_id
        assert checked_out.checked_out_at is not None
        assert checked_out.checkout_lease_until is not None
        assert checked_out.checkout_version == 1
        assert checked_out.is_checked_out is True

    async def test_checkout_task_success(
        self, task_repo: TaskRepository, sample_task: Task
    ):
        """Test successful task checkout."""
        agent_id = "agent_123"

        # Checkout task
        task = await task_repo.checkout_task(
            sample_task.id,
            agent_id,
            lease_seconds=300,
        )

        assert task is not None
        assert task.checkout_agent_session_id == agent_id
        assert task.checked_out_at is not None
        assert task.checkout_lease_until is not None
        assert task.checkout_version == 1
        assert task.is_checked_out is True

    async def test_checkout_conflict(
        self, task_repo: TaskRepository, sample_task: Task
    ):
        """Test checkout conflict when task already checked out."""
        agent1 = "agent_1"
        agent2 = "agent_2"

        # Agent 1 checks out
        await task_repo.checkout_task(sample_task.id, agent1)

        # Agent 2 tries to checkout - should fail
        with pytest.raises(TaskCheckoutConflict):
            await task_repo.checkout_task(sample_task.id, agent2)

    async def test_checkout_in_transaction_requires_owned_transaction(
        self, task_repo: TaskRepository, sample_task: Task
    ):
        """Internal checkout helper must fail loudly without transaction ownership."""
        with pytest.raises(RuntimeError, match="requires an active transaction"):
            await task_repo._checkout_task_in_transaction(
                task_id=sample_task.id,
                agent_session_id="agent_unsafe",
            )

    async def test_checkout_renewal(self, task_repo: TaskRepository, sample_task: Task):
        """Test lease renewal (heartbeat)."""
        agent_id = "agent_123"

        # Checkout
        task = await task_repo.checkout_task(sample_task.id, agent_id, lease_seconds=60)
        first_lease = task.checkout_lease_until

        # Renew
        task = await task_repo.renew_checkout(
            sample_task.id, agent_id, lease_seconds=120
        )

        assert task.checkout_lease_until > first_lease
        assert task.checkout_agent_session_id == agent_id

    async def test_renew_checkout_in_transaction_requires_owned_transaction(
        self, task_repo: TaskRepository, sample_task: Task
    ):
        """Internal renew helper must fail loudly without transaction ownership."""
        agent_id = "agent_123"
        await task_repo.checkout_task(sample_task.id, agent_id, lease_seconds=60)

        with pytest.raises(RuntimeError, match="requires an active transaction"):
            await task_repo._renew_checkout_in_transaction(
                task_id=sample_task.id,
                agent_session_id=agent_id,
                lease_seconds=120,
            )

    async def test_checkout_persists_checkout_actor_id(
        self, task_repo, sample_task, actor_repo
    ):
        """Checkout should persist canonical actor identity alongside agent id."""
        from pms.models.enums import ActorKind

        checkout_actor = await actor_repo.create(
            kind=ActorKind.RUNTIME_AGENT,
            name="Security Runtime",
            handle="security-runtime",
        )
        renewed_actor = await actor_repo.create(
            kind=ActorKind.RUNTIME_AGENT,
            name="Security Runtime V2",
            handle="security-runtime-v2",
        )

        task = await task_repo.checkout_task(
            sample_task.id,
            "agent_123",
            lease_seconds=60,
            checkout_actor_id=checkout_actor.id,
        )

        assert task.checkout_actor_id == checkout_actor.id

        renewed = await task_repo.renew_checkout(
            sample_task.id,
            "agent_123",
            lease_seconds=120,
            checkout_actor_id=renewed_actor.id,
        )
        assert renewed.checkout_actor_id == renewed_actor.id

        released = await task_repo.release_checkout(sample_task.id, "agent_123")
        assert released.checkout_actor_id is None

    async def test_checkout_release(self, task_repo: TaskRepository, sample_task: Task):
        """Test explicit checkout release."""
        agent_id = "agent_123"

        # Checkout
        task = await task_repo.checkout_task(sample_task.id, agent_id)
        assert task.is_checked_out

        # Release
        task = await task_repo.release_checkout(sample_task.id, agent_id)

        assert task.checkout_agent_session_id is None
        assert task.checked_out_at is None
        assert task.checkout_lease_until is None
        assert task.is_checked_out is False

    async def test_release_checkout_in_transaction_requires_owned_transaction(
        self, task_repo: TaskRepository, sample_task: Task
    ):
        """Internal release helper must fail loudly without transaction ownership."""
        agent_id = "agent_123"
        await task_repo.checkout_task(sample_task.id, agent_id)

        with pytest.raises(RuntimeError, match="requires an active transaction"):
            await task_repo._release_checkout_in_transaction(
                task_id=sample_task.id,
                agent_session_id=agent_id,
            )

    async def test_force_release_checkout(
        self, task_repo: TaskRepository, sample_task: Task
    ):
        """Test forced checkout release."""
        agent_id = "agent_123"

        await task_repo.checkout_task(sample_task.id, agent_id)

        task = await task_repo.force_release_checkout(
            sample_task.id, released_by="admin", reason="override"
        )

        assert task is not None
        assert task.checkout_agent_session_id is None
        assert task.checkout_lease_until is None

        rows = await task_repo.db.fetch_all(
            "SELECT action FROM task_checkout_log WHERE task_id = ?",
            (sample_task.id,),
        )
        actions = [row["action"] for row in rows]
        assert "force_release" in actions

    async def test_force_release_checkout_in_transaction_requires_owned_transaction(
        self, task_repo: TaskRepository, sample_task: Task
    ):
        """Internal force-release helper must fail loudly without ownership."""
        agent_id = "agent_123"
        await task_repo.checkout_task(sample_task.id, agent_id)

        with pytest.raises(RuntimeError, match="requires an active transaction"):
            await task_repo._force_release_checkout_in_transaction(
                task_id=sample_task.id,
                released_by="admin",
                reason="override",
            )

    async def test_get_checkout_log(self, task_repo: TaskRepository, sample_task: Task):
        """Test fetching checkout log entries."""
        agent_id = "agent_log"

        await task_repo.checkout_task(sample_task.id, agent_id)
        await task_repo.release_checkout(sample_task.id, agent_id)

        entries = await task_repo.get_checkout_log(task_id=sample_task.id, limit=10)
        actions = [entry["action"] for entry in entries]
        assert "checkout" in actions
        assert "release" in actions

    async def test_expired_checkout_cleanup(
        self, task_repo: TaskRepository, sample_task: Task
    ):
        """Test automatic cleanup of expired checkouts."""
        agent_id = "agent_123"

        # Checkout with very short lease
        await task_repo.checkout_task(sample_task.id, agent_id, lease_seconds=1)

        # Wait for expiration
        import asyncio

        await asyncio.sleep(2)

        # Run cleanup
        expired_ids = await task_repo.cleanup_expired_checkouts()

        assert sample_task.id in expired_ids

        # Verify task is no longer checked out
        task = await task_repo.get_by_id(sample_task.id)
        assert task.checkout_agent_session_id is None

    async def test_get_available_tasks(self, task_repo, sample_project):
        """Test getting tasks available for checkout."""
        # Create task
        task = await task_repo.create(
            project_id=sample_project.id,
            title="Available Test",
            complexity_points=25,
        )

        agent_id = "agent_123"

        # Initially available
        available = await task_repo.get_available_tasks(project_id=sample_project.id)
        assert task.id in [t.id for t in available]

        # Checkout
        await task_repo.checkout_task(task.id, agent_id)

        # No longer available
        available = await task_repo.get_available_tasks(project_id=sample_project.id)
        assert task.id not in [t.id for t in available]

    async def test_get_agent_checkouts(
        self, task_repo: TaskRepository, sample_task: Task
    ):
        """Test getting all checkouts for an agent."""
        agent_id = "agent_123"

        # Checkout task
        await task_repo.checkout_task(sample_task.id, agent_id)

        # Get agent's checkouts
        checkouts = await task_repo.get_agent_checkouts(agent_id)

        assert len(checkouts) == 1
        assert checkouts[0].id == sample_task.id

    async def test_checkout_blocking_dependencies(
        self, task_repo: TaskRepository, sample_project
    ):
        """Test checkout blocked by incomplete dependencies."""
        # Create task with dependency
        task1 = await task_repo.create(
            project_id=sample_project.id,
            title="Task 1",
        )
        task2 = await task_repo.create(
            project_id=sample_project.id,
            title="Task 2",
        )

        # Task2 depends on Task1 (blocks)
        from pms.models.enums import DependencyType

        await task_repo.add_dependency(task2.id, task1.id, DependencyType.BLOCKS)

        # Try to checkout task2 - should fail (task1 not done)
        with pytest.raises(TaskCheckoutBlocked):
            await task_repo.checkout_task(task2.id, "agent_1")

        # Complete task1
        await task_repo.update_status(task1.id, TaskStatus.DONE)

        # Now checkout should succeed
        task2_checked = await task_repo.checkout_task(task2.id, "agent_1")
        assert task2_checked is not None
        assert task2_checked.is_checked_out

    async def test_checkout_version_optimistic_locking(
        self, task_repo: TaskRepository, sample_task: Task
    ):
        """Test optimistic locking with checkout_version."""
        agent1 = "agent_1"
        agent2 = "agent_2"

        # Agent 1 checks out
        task1 = await task_repo.checkout_task(sample_task.id, agent1)
        version1 = task1.checkout_version

        # Simulate agent 1 releasing
        await task_repo.release_checkout(sample_task.id, agent1)

        # Agent 2 checks out
        task2 = await task_repo.checkout_task(sample_task.id, agent2)
        version2 = task2.checkout_version

        # Version should have incremented
        assert version2 > version1

    async def test_checkout_audit_log(
        self, task_repo: TaskRepository, sample_task: Task
    ):
        """Test that checkout actions are logged."""
        agent_id = "agent_123"

        # Perform checkout operations
        await task_repo.checkout_task(sample_task.id, agent_id)
        await task_repo.renew_checkout(sample_task.id, agent_id)
        await task_repo.release_checkout(sample_task.id, agent_id)

        # Query audit log
        rows = await task_repo.db.fetch_all(
            "SELECT * FROM task_checkout_log WHERE task_id = ? ORDER BY timestamp",
            (sample_task.id,),
        )

        assert len(rows) >= 3  # checkout, renew, release
        actions = [row["action"] for row in rows]
        assert "checkout" in actions
        assert "renew" in actions
        assert "release" in actions

    async def test_force_checkout(self, task_repo: TaskRepository, sample_task: Task):
        """Test force checkout override."""
        agent1 = "agent_1"
        agent2 = "agent_2"

        # Agent 1 checks out
        await task_repo.checkout_task(sample_task.id, agent1)

        # Agent 2 force checkout
        task = await task_repo.checkout_task(
            sample_task.id,
            agent2,
            force=True,
        )

        assert task.checkout_agent_session_id == agent2  # Overridden

    async def test_same_agent_recheckout_renews(
        self, task_repo: TaskRepository, sample_task: Task
    ):
        """Test that same agent checking out again just renews."""
        agent_id = "agent_123"

        # First checkout
        task1 = await task_repo.checkout_task(
            sample_task.id, agent_id, lease_seconds=60
        )
        version1 = task1.checkout_version
        lease1 = task1.checkout_lease_until

        # Same agent checks out again - should renew
        task2 = await task_repo.checkout_task(
            sample_task.id, agent_id, lease_seconds=120
        )

        assert (
            task2.checkout_version == version1
        )  # Version unchanged (renewal, not new checkout)
        assert task2.checkout_lease_until > lease1  # Lease extended
