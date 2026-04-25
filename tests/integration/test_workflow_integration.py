"""Integration test for complete workflow system."""

from datetime import datetime
from pathlib import Path

import pytest

from pms.core.events import EventStore, EventType
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.core.state_machine import StateMachine
from pms.db.connection import Database
from pms.db.schema import initialize_schema
from pms.models.workflow_state import create_agile_workflow, create_sdlc_workflow
from pms.repositories.project_repository import ProjectRepository
from pms.repositories.state_transition_repository import StateTransitionRepository
from pms.repositories.task_repository import TaskRepository


@pytest.fixture
async def workflow_db():
    """Create database for workflow testing."""
    timestamp = datetime.now().timestamp()
    db_path = Path(f"/tmp/claude/workflow_test_{timestamp}.db")
    db_path.unlink(missing_ok=True)

    db = Database(db_path)
    await db.connect()
    await initialize_schema(db)

    yield db

    await db.disconnect()
    db_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_complete_sdlc_workflow(workflow_db):
    """Test complete SDLC workflow from concept to production."""
    db = workflow_db
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)

    project_repo = ProjectRepository(db, event_store, revision_store, metrics)
    task_repo = TaskRepository(db, event_store, revision_store, metrics)
    state_repo = StateTransitionRepository(db)
    project = await project_repo.create(name="Workflow Integration Project")

    # Create SDLC workflow
    sdlc = create_sdlc_workflow()
    state_machine = StateMachine(sdlc, state_repo)

    # Create task and assign workflow
    task = await task_repo.create(
        project_id=project.id,
        title="Feature: Add login",
        complexity_points=75,
    )
    assert task is not None
    print(f"✓ Created task: {task.id}")

    # Assign SDLC workflow
    task.assign_workflow(sdlc.id, "concept")
    await task_repo.save(
        task,
        EventType.TASK_UPDATED,
        {"workflow_assigned": sdlc.name},
    )
    print(f"✓ Assigned SDLC workflow, initial state: {task.current_state}")

    # Transition through workflow states
    states = [
        "idea",
        "planning",
        "detailed_plan",
        "implementing",
        "code_review",
        "unit_testing",
        "integration_testing",
        "staging",
        "confirmation",
        "production",
    ]

    for new_state in states:
        # Prepare context (approval for production transition)
        context = {}
        if new_state == "production":
            context["approved_by"] = "release_manager"

        # Verify transition is allowed
        can_transition, error = state_machine.can_transition(
            task.current_state,
            new_state,
            context=context,
        )
        assert can_transition, (
            f"Cannot transition {task.current_state} → {new_state}: {error}"
        )

        # Perform transition
        transition = await state_machine.transition(
            entity_id=task.id,
            from_state=task.current_state,
            to_state=new_state,
            triggered_by="test_agent",
            reason=f"Moving to {new_state}",
            approved_by=context.get("approved_by"),
        )
        assert transition is not None
        print(f"✓ Transitioned: {transition.from_state} → {transition.to_state}")

        # Update task state
        task.transition_to(new_state, "test_agent", f"Moving to {new_state}")

    assert task.current_state == "production"
    assert state_machine.is_terminal_state("production")
    print(f"✓ Reached terminal state: {task.current_state}")

    # Verify transition history
    timeline = await state_repo.get_timeline("task", task.id)
    assert len(timeline.transitions) == len(states)
    print(f"✓ Complete transition timeline: {len(timeline.transitions)} transitions")


@pytest.mark.asyncio
async def test_workflow_prevents_invalid_transitions(workflow_db):
    """Test that workflow prevents invalid transitions."""
    db = workflow_db
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)

    project_repo = ProjectRepository(db, event_store, revision_store, metrics)
    task_repo = TaskRepository(db, event_store, revision_store, metrics)
    state_repo = StateTransitionRepository(db)
    project = await project_repo.create(name="Agile Workflow Integration Project")

    # Create Agile workflow
    agile = create_agile_workflow()
    state_machine = StateMachine(agile, state_repo)

    # Create task
    task = await task_repo.create(
        project_id=project.id,
        title="Agile task",
        complexity_points=25,
    )
    task.assign_workflow(agile.id, "backlog")

    # Try invalid transition (backlog → done, skipping in_progress)
    can_transition, error = state_machine.can_transition("backlog", "done")
    assert not can_transition
    assert error is not None
    print(f"✓ Invalid transition blocked: {error}")

    # Valid transition should work
    can_transition, error = state_machine.can_transition("backlog", "sprint_planned")
    assert can_transition
    print(f"✓ Valid transition allowed: backlog → sprint_planned")


if __name__ == "__main__":
    import asyncio

    async def run():
        timestamp = datetime.now().timestamp()
        db = Database(Path(f"/tmp/claude/workflow_manual_{timestamp}.db"))
        await db.connect()
        await initialize_schema(db)

        await test_complete_sdlc_workflow(db)
        await test_workflow_prevents_invalid_transitions(db)

        await db.disconnect()
        print("\n✅ All workflow integration tests passed!")

    asyncio.run(run())
