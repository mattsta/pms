"""Integration tests for the complete refactor."""

from datetime import datetime
from pathlib import Path

import pytest

from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.db.connection import Database
from pms.db.schema import initialize_schema
from pms.models import Priority, ProductStatus
from pms.repositories.project_repository import ProjectRepository
from pms.repositories.task_repository import TaskRepository
from pms.services.product_service import ProductService
from pms.services.task_service import TaskService


@pytest.fixture
async def clean_db():
    """Create a fresh database with unique path for each test."""
    timestamp = datetime.now().timestamp()
    db_path = Path(f"/tmp/claude/integration_test_{timestamp}.db")
    db_path.unlink(missing_ok=True)

    db = Database(db_path)
    await db.connect()
    await initialize_schema(db)

    yield db

    await db.disconnect()
    db_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_product_hierarchy_integration(clean_db):
    """Test complete Product → Project → Task hierarchy."""
    db = clean_db
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)

    # Create services
    product_service = ProductService(db, event_store, revision_store, metrics)
    task_service = TaskService(db, event_store, revision_store, metrics)

    # Create product
    product = await product_service.create_product(
        name="TestProduct",
        description="Test product for integration",
        vision="Build amazing things",
    )
    assert product.name == "TestProduct"
    assert product.status == ProductStatus.ACTIVE
    print(f"✓ Created product: {product.id}")

    # Create project in product
    project = await product_service.create_project_in_product(
        product_id=product.id,
        project_name="TestProject",
        description="First project",
    )
    assert project.product_id == product.id
    print(f"✓ Created project in product: {project.id}")

    # Create task with complexity
    task = await task_service.create_task(
        project_id=project.id,
        title="Test Task",
        complexity_points=50,
        priority=Priority.HIGH,
    )
    assert task.complexity_points == 50
    assert task.current_progress_percent == 0
    print(f"✓ Created task with complexity: {task.id}")

    # Get product summary
    summary = await product_service.get_product_summary(product.id)
    assert summary is not None
    assert len(summary.projects) == 1
    assert summary.stats.total_tasks == 1
    print(f"✓ Product hierarchy validated")


@pytest.mark.asyncio
async def test_task_checkout_system(clean_db):
    """Test task checkout/ownership system."""
    db = clean_db
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)

    project_repo = ProjectRepository(db, event_store, revision_store, metrics)
    task_repo = TaskRepository(db, event_store, revision_store, metrics)
    project = await project_repo.create(name="Checkout Integration Project")

    # Create task
    task = await task_repo.create(
        project_id=project.id,
        title="Checkout Test",
        complexity_points=25,
    )
    print(f"✓ Created task: {task.id}")

    # Checkout task
    agent_id = "agent_test_123"
    task = await task_repo.checkout_task(task.id, agent_id, lease_seconds=300)
    assert task.checkout_agent_session_id == agent_id
    assert task.is_checked_out
    print(f"✓ Checked out task: {task.checkout_agent_session_id}")

    # Try concurrent checkout (should fail)
    from pms.exceptions.base import TaskCheckoutConflict

    with pytest.raises(TaskCheckoutConflict):
        await task_repo.checkout_task(task.id, "agent_other", lease_seconds=300)
    print(f"✓ Checkout conflict detected correctly")

    # Release
    task = await task_repo.release_checkout(task.id, agent_id)
    assert task.checkout_agent_session_id is None
    print(f"✓ Released checkout")


@pytest.mark.asyncio
async def test_progress_tracking(clean_db):
    """Test progressive effort update system."""
    db = clean_db
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)

    project_repo = ProjectRepository(db, event_store, revision_store, metrics)
    task_repo = TaskRepository(db, event_store, revision_store, metrics)
    from pms.repositories.progress_repository import ProgressRepository

    progress_repo = ProgressRepository(db)
    project = await project_repo.create(name="Progress Integration Project")

    # Create task
    task = await task_repo.create(
        project_id=project.id,
        title="Progress Test",
        complexity_points=100,
    )
    print(f"✓ Created task: {task.id}")

    # Record progress updates
    await progress_repo.record_progress(
        task_id=task.id,
        percent_complete=25,
        status_message="Quarter done",
        updated_by="agent_1",
    )
    await progress_repo.record_progress(
        task_id=task.id,
        percent_complete=75,
        status_message="Three quarters done",
        updated_by="agent_1",
    )
    print(f"✓ Recorded progress updates")

    # Get timeline
    timeline = await progress_repo.get_timeline(task.id)
    assert len(timeline.updates) == 2
    assert timeline.current_percent == 75
    assert timeline.average_velocity_percent_per_hour > 0
    print(f"✓ Progress timeline: {timeline.current_percent}% complete")
    print(f"✓ Velocity: {timeline.average_velocity_percent_per_hour:.2f}%/hour")


if __name__ == "__main__":
    import asyncio

    async def run_all():
        timestamp = datetime.now().timestamp()
        db_path = Path(f"/tmp/claude/manual_test_{timestamp}.db")
        db = Database(db_path)
        await db.connect()
        await initialize_schema(db)

        await test_product_hierarchy_integration(db)
        await test_task_checkout_system(db)
        await test_progress_tracking(db)

        await db.disconnect()
        print("\n✅ ALL INTEGRATION TESTS PASSED!")

    asyncio.run(run_all())
