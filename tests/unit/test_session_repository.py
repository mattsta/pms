"""Tests for SessionRepository."""

import pytest

from pms.models.enums import SessionStatus
from pms.repositories import SessionRepository


@pytest.mark.asyncio
async def test_create_session(db, event_store, revision_store, metrics_collector):
    """Test creating a session."""
    repo = SessionRepository(db, event_store, revision_store, metrics_collector)

    from pms.repositories.project_repository import ProjectRepository

    project_repo = ProjectRepository(db, event_store, revision_store, metrics_collector)
    project = await project_repo.create(name="Session Project")

    session = await repo.create(project_id=project.id, initial_prompt="test prompt")

    assert session.id
    assert session.project_id == project.id
    assert session.status == SessionStatus.ACTIVE


@pytest.mark.asyncio
async def test_add_message(db, event_store, revision_store, metrics_collector):
    """Test adding messages to session."""
    repo = SessionRepository(db, event_store, revision_store, metrics_collector)

    session = await repo.create()

    message = await repo.add_message(
        session_id=session.id, role="user", content="test message"
    )

    assert message.session_id == session.id
    assert message.role == "user"
    assert message.content == "test message"


@pytest.mark.asyncio
async def test_add_message_rolls_back_when_session_save_fails(
    db, event_store, revision_store, metrics_collector, monkeypatch: pytest.MonkeyPatch
):
    """Late session-save failure should not leave a transcript row behind."""
    repo = SessionRepository(db, event_store, revision_store, metrics_collector)

    session = await repo.create()

    async def explode(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(repo, "_save_in_transaction", explode)

    with pytest.raises(RuntimeError, match="boom"):
        await repo.add_message(session.id, "user", "test message")

    assert await repo.get_messages(session.id) == []
    reloaded = await repo.get_by_id(session.id)
    assert reloaded is not None
    assert reloaded.message_count == 0


@pytest.mark.asyncio
async def test_get_messages(db, event_store, revision_store, metrics_collector):
    """Test retrieving session messages."""
    repo = SessionRepository(db, event_store, revision_store, metrics_collector)

    session = await repo.create()
    await repo.add_message(session.id, "user", "hello")
    await repo.add_message(session.id, "assistant", "hi there")
    await repo.add_message(session.id, "user", "how are you")

    messages = await repo.get_messages(session.id)

    assert len(messages) == 3
    assert messages[0].role == "user"
    assert messages[1].role == "assistant"
    assert messages[2].role == "user"


@pytest.mark.asyncio
async def test_get_messages_preserves_custom_open_role(
    db, event_store, revision_store, metrics_collector
):
    """Custom transcript roles should round-trip without being normalized away."""
    repo = SessionRepository(db, event_store, revision_store, metrics_collector)

    session = await repo.create()
    await repo.add_message(session.id, "planner", "Plan the next slice")

    messages = await repo.get_messages(session.id)

    assert len(messages) == 1
    assert messages[0].role == "planner"
    assert messages[0].content == "Plan the next slice"


@pytest.mark.asyncio
async def test_update_costs(db, event_store, revision_store, metrics_collector):
    """Test updating session costs."""
    repo = SessionRepository(db, event_store, revision_store, metrics_collector)

    session = await repo.create()

    updated = await repo.update_costs(session_id=session.id, tokens=1000, cost=0.05)

    assert updated.token_count == 1000
    assert updated.cost_usd == 0.05


@pytest.mark.asyncio
async def test_end_session(db, event_store, revision_store, metrics_collector):
    """Test ending a session."""
    repo = SessionRepository(db, event_store, revision_store, metrics_collector)

    session = await repo.create()
    ended = await repo.end_session(session.id)

    assert ended.status == SessionStatus.ENDED


@pytest.mark.asyncio
async def test_get_active_sessions(db, event_store, revision_store, metrics_collector):
    """Test getting active sessions."""
    repo = SessionRepository(db, event_store, revision_store, metrics_collector)
    from pms.repositories.project_repository import ProjectRepository

    project_repo = ProjectRepository(db, event_store, revision_store, metrics_collector)
    project = await project_repo.create(name="Active Session Project")

    active1 = await repo.create(project_id=project.id)
    active2 = await repo.create(project_id=project.id)
    ended = await repo.create(project_id=project.id)
    await repo.end_session(ended.id)

    active_sessions = await repo.get_active_sessions(project_id=project.id)

    assert len(active_sessions) == 2
    assert all(s.status == SessionStatus.ACTIVE for s in active_sessions)


@pytest.mark.asyncio
async def test_session_with_multiple_cost_updates(
    db, event_store, revision_store, metrics_collector
):
    """Test accumulating costs across multiple updates."""
    repo = SessionRepository(db, event_store, revision_store, metrics_collector)

    session = await repo.create()

    await repo.update_costs(session.id, 100, 0.01)
    await repo.update_costs(session.id, 200, 0.02)
    updated = await repo.update_costs(session.id, 300, 0.03)

    assert updated.token_count == 600
    assert updated.cost_usd == 0.06
