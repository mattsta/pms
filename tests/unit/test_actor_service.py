"""Unit tests for actor identity graph services."""

from __future__ import annotations

from datetime import timedelta

import pytest

from pms.models import ActorKind, ActorMembershipRole, ActorStatus, TaskStatus
from pms.models.base import now_utc
from pms.services.actor_service import ActorService
from pms.services.comment_service import CommentService
from pms.services.label_service import LabelService


@pytest.fixture
async def actor_service(
    db, event_store, revision_store, metrics_collector
) -> ActorService:
    """Create an actor service for testing."""
    return ActorService(db, event_store, revision_store, metrics_collector)


@pytest.mark.asyncio
async def test_actor_service_creates_alias_and_resolves_by_alias(
    actor_service: ActorService,
):
    """Actors should resolve through canonical handle and alias."""
    actor = await actor_service.create_actor(
        name="Alice Example",
        kind=ActorKind.HUMAN,
    )
    assert actor.handle == "alice-example"

    alias = await actor_service.add_alias(actor.id, "alice")
    resolved = await actor_service.get_actor("alice")

    assert alias.normalized_alias == "alice"
    assert resolved is not None
    assert resolved.id == actor.id


@pytest.mark.asyncio
async def test_actor_assignment_tokens_include_inherited_persona_membership(
    actor_service: ActorService,
):
    """Inherited persona memberships should participate in assignee resolution."""
    alice = await actor_service.create_actor(name="Alice Example", kind=ActorKind.HUMAN)
    security = await actor_service.create_actor(
        name="Security Persona",
        kind=ActorKind.PERSONA,
    )
    await actor_service.add_membership(
        parent_actor=security.id,
        member_actor=alice.id,
        role=ActorMembershipRole.REPRESENTATIVE,
    )

    tokens = await actor_service.resolve_assignment_tokens(
        alice.id, include_inherited=True
    )

    assert alice.handle in tokens
    assert security.handle in tokens
    assert "Security Persona" in tokens


@pytest.mark.asyncio
async def test_actor_list_assigned_tasks_matches_direct_and_inherited_assignments(
    actor_service: ActorService,
    task_repo,
    sample_project,
):
    """Actor workload queries should match both direct and inherited assignee strings."""
    alice = await actor_service.create_actor(name="Alice Example", kind=ActorKind.HUMAN)
    marketing = await actor_service.create_actor(
        name="Marketing Persona",
        kind=ActorKind.PERSONA,
    )
    await actor_service.add_membership(
        parent_actor=marketing.id,
        member_actor=alice.id,
        role=ActorMembershipRole.MEMBER,
    )

    direct_task = await task_repo.create(
        project_id=sample_project.id,
        title="Direct task",
        assignee=alice.handle,
    )
    inherited_task = await task_repo.create(
        project_id=sample_project.id,
        title="Persona task",
        assignee=marketing.handle,
    )
    await task_repo.create(
        project_id=sample_project.id,
        title="Other task",
        assignee="someone-else",
        message="Created unrelated task",
    )

    result = await actor_service.list_assigned_tasks(
        alice.id,
        include_inherited=True,
        status=TaskStatus.TODO,
    )

    task_ids = {task.id for task in result.items}
    assert direct_task.id in task_ids
    assert inherited_task.id in task_ids
    assert result.total_count == 2


@pytest.mark.asyncio
async def test_actor_workload_summary_splits_direct_and_inherited_assignments(
    actor_service: ActorService,
    task_repo,
    sample_project,
):
    """Actor workload rollups should distinguish direct and inherited assignment math."""
    alice = await actor_service.create_actor(name="Alice Example", kind=ActorKind.HUMAN)
    design = await actor_service.create_actor(
        name="Design Persona",
        kind=ActorKind.PERSONA,
    )
    await actor_service.add_membership(
        parent_actor=design.id,
        member_actor=alice.id,
        role=ActorMembershipRole.REPRESENTATIVE,
    )

    await task_repo.create(
        project_id=sample_project.id,
        title="Direct task",
        assignee=alice.handle,
    )
    persona_task = await task_repo.create(
        project_id=sample_project.id,
        title="Persona task",
        assignee=design.handle,
    )
    updated_persona_task = await task_repo.update_status(
        persona_task.id,
        TaskStatus.IN_PROGRESS,
    )
    assert updated_persona_task is not None

    summary = await actor_service.get_workload_summary(alice.id, include_inherited=True)

    assert summary.direct.total_tasks == 1
    assert summary.effective.total_tasks == 2
    assert summary.inherited_only.total_tasks == 1
    assert summary.effective.in_progress_tasks == 1


@pytest.mark.asyncio
async def test_actor_queries_match_canonical_actor_id_assignments(
    actor_service: ActorService,
    task_repo,
    sample_project,
):
    """Actor workload math should work even when only actor-id refs are persisted."""
    alice = await actor_service.create_actor(name="Alice Example", kind=ActorKind.HUMAN)
    security = await actor_service.create_actor(
        name="Security Persona",
        kind=ActorKind.PERSONA,
    )
    await actor_service.add_membership(
        parent_actor=security.id,
        member_actor=alice.id,
        role=ActorMembershipRole.REPRESENTATIVE,
    )

    await task_repo.create(
        project_id=sample_project.id,
        title="Direct id task",
        assignee=None,
        assignee_id=alice.id,
    )
    persona_task = await task_repo.create(
        project_id=sample_project.id,
        title="Inherited id task",
        assignee=None,
        assignee_id=security.id,
    )
    updated_persona_task = await task_repo.update_status(
        persona_task.id,
        TaskStatus.IN_PROGRESS,
    )
    assert updated_persona_task is not None

    result = await actor_service.list_assigned_tasks(alice.id, include_inherited=True)
    assert {task.title for task in result.items} == {
        "Direct id task",
        "Inherited id task",
    }

    summary = await actor_service.get_workload_summary(alice.id, include_inherited=True)
    assert summary.direct.total_tasks == 1
    assert summary.effective.total_tasks == 2
    assert summary.inherited_only.total_tasks == 1
    assert summary.effective.in_progress_tasks == 1


@pytest.mark.asyncio
async def test_actor_checkout_summary_and_graph_track_direct_execution_leases(
    actor_service: ActorService,
    task_repo,
    sample_project,
):
    """Actor graph should expose direct checkout leases separately from assignment math."""
    security = await actor_service.create_actor(
        name="Security Persona",
        kind=ActorKind.PERSONA,
    )

    active_task = await task_repo.create(
        project_id=sample_project.id,
        title="Active lease",
    )
    expired_task = await task_repo.create(
        project_id=sample_project.id,
        title="Expired lease",
    )

    await task_repo.checkout_task(
        active_task.id,
        "lease-agent-active",
        lease_seconds=300,
        checkout_actor_id=security.id,
    )
    await task_repo.checkout_task(
        expired_task.id,
        "lease-agent-expired",
        lease_seconds=300,
        checkout_actor_id=security.id,
    )
    await task_repo.db.execute(
        "UPDATE tasks SET checkout_lease_until = ? WHERE id = ?",
        ((now_utc() - timedelta(minutes=5)).isoformat(), expired_task.id),
    )

    summary = await actor_service.get_checkout_summary(
        security.id, include_expired=True
    )
    assert summary.total_checkouts == 2
    assert summary.active_checkouts == 1
    assert summary.expired_checkouts == 1
    assert summary.distinct_agents == 2

    snapshot = await actor_service.get_actor_graph(security.id, include_inherited=True)
    assert snapshot is not None
    assert snapshot.checkout_summary is not None
    assert snapshot.checkout_summary.active_checkouts == 1
    assert snapshot.checked_out_tasks is not None
    assert {task.title for task in snapshot.checked_out_tasks.items} == {
        "Active lease",
        "Expired lease",
    }


@pytest.mark.asyncio
async def test_create_actor_rolls_back_when_metrics_flush_fails(
    actor_service: ActorService,
    monkeypatch: pytest.MonkeyPatch,
):
    """Actor creation should roll back if metrics flush fails late."""

    async def fail_flush(*args, **kwargs):
        raise RuntimeError("metrics flush failed")

    monkeypatch.setattr(actor_service.metrics, "flush", fail_flush)

    with pytest.raises(RuntimeError, match="metrics flush failed"):
        await actor_service.create_actor(name="Atomic Actor", kind=ActorKind.HUMAN)

    assert await actor_service.get_actor("atomic-actor") is None


@pytest.mark.asyncio
async def test_update_actor_rolls_back_when_metrics_flush_fails(
    actor_service: ActorService,
    monkeypatch: pytest.MonkeyPatch,
):
    """Actor updates should roll back if metrics flush fails late."""
    actor = await actor_service.create_actor(name="Before Name", kind=ActorKind.HUMAN)

    async def fail_flush(*args, **kwargs):
        raise RuntimeError("metrics flush failed")

    monkeypatch.setattr(actor_service.metrics, "flush", fail_flush)

    with pytest.raises(RuntimeError, match="metrics flush failed"):
        await actor_service.update_actor(actor.id, name="After Name")

    refreshed = await actor_service.get_actor(actor.id)
    assert refreshed is not None
    assert refreshed.name == "Before Name"


@pytest.mark.asyncio
async def test_archive_actor_rolls_back_when_metrics_flush_fails(
    actor_service: ActorService,
    monkeypatch: pytest.MonkeyPatch,
):
    """Actor archive should roll back if metrics flush fails late."""
    actor = await actor_service.create_actor(
        name="Archive Target", kind=ActorKind.HUMAN
    )

    async def fail_flush(*args, **kwargs):
        raise RuntimeError("metrics flush failed")

    monkeypatch.setattr(actor_service.metrics, "flush", fail_flush)

    with pytest.raises(RuntimeError, match="metrics flush failed"):
        await actor_service.archive_actor(actor.id)

    refreshed = await actor_service.get_actor(actor.id)
    assert refreshed is not None
    assert refreshed.status == ActorStatus.ACTIVE


@pytest.mark.asyncio
async def test_add_alias_rolls_back_when_metrics_flush_fails(
    actor_service: ActorService,
    monkeypatch: pytest.MonkeyPatch,
):
    """Alias creation should roll back if metrics flush fails late."""
    actor = await actor_service.create_actor(name="Alias Target", kind=ActorKind.HUMAN)

    async def fail_flush(*args, **kwargs):
        raise RuntimeError("metrics flush failed")

    monkeypatch.setattr(actor_service.metrics, "flush", fail_flush)

    with pytest.raises(RuntimeError, match="metrics flush failed"):
        await actor_service.add_alias(actor.id, "alias-target-short")

    assert await actor_service.get_actor("alias-target-short") is None
    assert await actor_service.list_aliases(actor.id) == []


@pytest.mark.asyncio
async def test_add_membership_rolls_back_when_metrics_flush_fails(
    actor_service: ActorService,
    monkeypatch: pytest.MonkeyPatch,
):
    """Membership creation should roll back if metrics flush fails late."""
    parent = await actor_service.create_actor(
        name="Parent Persona", kind=ActorKind.PERSONA
    )
    member = await actor_service.create_actor(name="Member Human", kind=ActorKind.HUMAN)

    async def fail_flush(*args, **kwargs):
        raise RuntimeError("metrics flush failed")

    monkeypatch.setattr(actor_service.metrics, "flush", fail_flush)

    with pytest.raises(RuntimeError, match="metrics flush failed"):
        await actor_service.add_membership(
            parent_actor=parent.id,
            member_actor=member.id,
            role=ActorMembershipRole.MEMBER,
        )

    assert await actor_service.list_child_memberships(parent.id) == []
    assert await actor_service.list_parent_memberships(member.id) == []


@pytest.mark.asyncio
async def test_actor_graph_bubbles_direct_comment_label_and_watcher_activity(
    actor_service: ActorService,
    db,
    metrics_collector,
):
    """Actor graph activity should include direct actor comments, labels, and watchers."""
    actor = await actor_service.create_actor(
        name="Activity Actor", kind=ActorKind.HUMAN
    )
    comment_service = CommentService(db, metrics_collector)
    label_service = LabelService(db, metrics_collector)

    comment = await comment_service.add_comment(
        "actor",
        actor.id,
        "Fresh actor note",
        created_by="codex",
    )
    category = await label_service.create_category("Actor Audit Labels")
    label = await label_service.create_label(
        "graph-audit",
        category_id=category.id,
    )
    assignment = await label_service.assign_label(
        "actor",
        actor.id,
        label.id,
        applied_by="codex",
    )
    watcher = await comment_service.add_watcher("actor", actor.id, "codex")

    snapshot = await actor_service.get_actor_graph(actor.id, include_inherited=True)
    assert snapshot is not None
    expected_last_activity = max(
        comment.comment.updated_at,
        assignment.updated_at,
        watcher.updated_at,
    )
    assert snapshot.last_activity_at == expected_last_activity
    transition_map = await actor_service.get_last_transition_map([actor.id])
    assert snapshot.last_transition_at == transition_map[actor.id]

    activity_map = await actor_service.get_last_activity_map([actor.id])
    assert activity_map[actor.id] == expected_last_activity


@pytest.mark.asyncio
async def test_actor_graph_bubbles_inherited_task_transitions(
    actor_service: ActorService,
    task_repo,
    sample_project,
):
    """Actor graph transitions should bubble inherited assignment task state changes."""
    alice = await actor_service.create_actor(name="Alice Example", kind=ActorKind.HUMAN)
    security = await actor_service.create_actor(
        name="Security Persona",
        kind=ActorKind.PERSONA,
    )
    await actor_service.add_membership(
        parent_actor=security.id,
        member_actor=alice.id,
        role=ActorMembershipRole.REPRESENTATIVE,
    )
    task = await task_repo.create(
        project_id=sample_project.id,
        title="Inherited transition task",
        assignee=security.handle,
    )
    updated = await task_repo.update_status(task.id, TaskStatus.IN_PROGRESS)
    assert updated is not None

    snapshot = await actor_service.get_actor_graph(alice.id, include_inherited=True)
    assert snapshot is not None
    assert snapshot.last_activity_at is not None
    assert snapshot.last_transition_at is not None
    transition_map = await actor_service.get_last_transition_map([alice.id])
    assert snapshot.last_transition_at == transition_map[alice.id]


@pytest.mark.asyncio
async def test_actor_list_sorts_by_bubbled_activity_not_handle(
    actor_service: ActorService,
    db,
    metrics_collector,
):
    """Actor list should sort by bubbled graph recency before lexical handle order."""
    alpha = await actor_service.create_actor(name="Alpha Actor", kind=ActorKind.HUMAN)
    zulu = await actor_service.create_actor(name="Zulu Actor", kind=ActorKind.HUMAN)
    comment_service = CommentService(db, metrics_collector)

    await comment_service.add_comment(
        "actor",
        zulu.id,
        "Newest actor graph update",
        created_by="codex",
    )

    result = await actor_service.list_actors(limit=10, offset=0)
    assert [actor.id for actor in result.items[:2]] == [zulu.id, alpha.id]
