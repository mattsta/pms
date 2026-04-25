"""Transactional tests for CommentService."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from pms.repositories.comment_mention_repository import CommentMentionRepository
from pms.repositories.comment_repository import CommentRepository
from pms.repositories.entity_watcher_repository import EntityWatcherRepository
from pms.services.comment_service import CommentService


async def _count_rows(db, table_name: str) -> int:
    row = await db.fetch_one(f"SELECT COUNT(*) as count FROM {table_name}")
    return int(row["count"]) if row else 0


@pytest.mark.asyncio
async def test_add_comment_rolls_back_when_partial_mention_insert_fails(
    db,
    metrics_collector,
    sample_task,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Late mention failure must roll back the created comment too."""
    service = CommentService(db, metrics_collector)

    async def fail_mentions(*, comment_id: str, mentions: list[str]):
        await db.execute(
            """
            INSERT INTO comment_mentions (id, comment_id, mention, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                comment_id,
                mentions[0],
                datetime.now(UTC).isoformat(),
            ),
        )
        raise RuntimeError("mention insert failed")

    monkeypatch.setattr(
        service._mentions, "_add_mentions_in_transaction", fail_mentions
    )

    with pytest.raises(RuntimeError, match="mention insert failed"):
        await service.add_comment(
            entity_type="task",
            entity_id=sample_task.id,
            body="Hello @alice",
            created_by="dev@example.com",
            mentions=["alice"],
            watch=False,
        )

    assert await _count_rows(db, "comments") == 0
    assert await _count_rows(db, "comment_mentions") == 0
    assert await _count_rows(db, "entity_watchers") == 0


@pytest.mark.asyncio
async def test_add_mentions_in_transaction_requires_owned_transaction(db) -> None:
    repo = CommentMentionRepository(db)

    with pytest.raises(RuntimeError, match="requires an active transaction"):
        await repo._add_mentions_in_transaction(
            comment_id="comment-direct-helper",
            mentions=["alice"],
        )


@pytest.mark.asyncio
async def test_create_comment_in_transaction_requires_owned_transaction(db) -> None:
    repo = CommentRepository(db)

    with pytest.raises(RuntimeError, match="requires an active transaction"):
        await repo._create_in_transaction(
            entity_type="task",
            entity_id="task-123",
            body="Unsafe comment",
            created_by="dev@example.com",
        )


@pytest.mark.asyncio
async def test_entity_watcher_helpers_require_owned_transaction(db) -> None:
    repo = EntityWatcherRepository(db)

    with pytest.raises(RuntimeError, match="requires an active transaction"):
        await repo._add_in_transaction(
            entity_type="task",
            entity_id="task-123",
            watcher="qa@example.com",
        )

    with pytest.raises(RuntimeError, match="requires an active transaction"):
        await repo._remove_in_transaction(
            entity_type="task",
            entity_id="task-123",
            watcher="qa@example.com",
        )

    with pytest.raises(RuntimeError, match="requires an active transaction"):
        await repo._restore_in_transaction(entity_id="watcher-123")


@pytest.mark.asyncio
async def test_add_comment_rolls_back_when_watcher_add_fails(
    db,
    metrics_collector,
    sample_task,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Watcher failure after comment/mentions must roll back the whole mutation."""
    service = CommentService(db, metrics_collector)

    async def fail_watcher_add(*, entity_type: str, entity_id: str, watcher: str):
        raise RuntimeError("watcher add failed")

    monkeypatch.setattr(service._watchers, "_add_in_transaction", fail_watcher_add)

    with pytest.raises(RuntimeError, match="watcher add failed"):
        await service.add_comment(
            entity_type="task",
            entity_id=sample_task.id,
            body="Hello @alice",
            created_by="dev@example.com",
            mentions=["alice"],
            watch=True,
        )

    assert await _count_rows(db, "comments") == 0
    assert await _count_rows(db, "comment_mentions") == 0
    assert await _count_rows(db, "entity_watchers") == 0


@pytest.mark.asyncio
async def test_add_watcher_rolls_back_when_metrics_flush_fails(
    db,
    metrics_collector,
    sample_task,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Watcher add should roll back if metrics flush fails late."""
    service = CommentService(db, metrics_collector)

    async def fail_flush(*args, **kwargs):
        raise RuntimeError("metrics flush failed")

    monkeypatch.setattr(service.metrics, "flush", fail_flush)

    with pytest.raises(RuntimeError, match="metrics flush failed"):
        await service.add_watcher(
            entity_type="task",
            entity_id=sample_task.id,
            watcher="qa@example.com",
        )

    active = await db.fetch_one(
        """
        SELECT COUNT(*) AS count
        FROM entity_watchers
        WHERE entity_type = ? AND entity_id = ? AND archived_at IS NULL
        """,
        ("task", sample_task.id),
    )
    assert int(active["count"]) == 0


@pytest.mark.asyncio
async def test_add_comment_rolls_back_when_metrics_flush_fails(
    db,
    metrics_collector,
    sample_task,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Comment creation should roll back if metrics flush fails after writes."""
    service = CommentService(db, metrics_collector)

    async def fail_flush(*args, **kwargs):
        raise RuntimeError("metrics flush failed")

    monkeypatch.setattr(service.metrics, "flush", fail_flush)

    with pytest.raises(RuntimeError, match="metrics flush failed"):
        await service.add_comment(
            entity_type="task",
            entity_id=sample_task.id,
            body="Hello @alice",
            created_by="dev@example.com",
            mentions=["alice"],
            watch=True,
        )

    assert await _count_rows(db, "comments") == 0
    assert await _count_rows(db, "comment_mentions") == 0
    assert await _count_rows(db, "entity_watchers") == 0


@pytest.mark.asyncio
async def test_remove_watcher_rolls_back_when_metrics_flush_fails(
    db,
    metrics_collector,
    sample_task,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Watcher remove should roll back if metrics flush fails late."""
    service = CommentService(db, metrics_collector)
    await service.add_watcher(
        entity_type="task",
        entity_id=sample_task.id,
        watcher="qa@example.com",
    )

    async def fail_flush(*args, **kwargs):
        raise RuntimeError("metrics flush failed")

    monkeypatch.setattr(service.metrics, "flush", fail_flush)

    with pytest.raises(RuntimeError, match="metrics flush failed"):
        await service.remove_watcher(
            entity_type="task",
            entity_id=sample_task.id,
            watcher="qa@example.com",
        )

    active = await db.fetch_one(
        """
        SELECT COUNT(*) AS count
        FROM entity_watchers
        WHERE entity_type = ? AND entity_id = ? AND watcher = ?
          AND archived_at IS NULL
        """,
        ("task", sample_task.id, "qa@example.com"),
    )
    assert int(active["count"]) == 1


@pytest.mark.asyncio
async def test_restore_watcher_round_trip(
    db,
    metrics_collector,
    sample_task,
) -> None:
    """Watcher remove/restore should use the watcher-specific event contract."""
    service = CommentService(db, metrics_collector)
    watcher = await service.add_watcher(
        entity_type="task",
        entity_id=sample_task.id,
        watcher="qa@example.com",
    )

    removed = await service.remove_watcher(
        entity_type="task",
        entity_id=sample_task.id,
        watcher="qa@example.com",
    )
    assert removed is True

    restored = await service.restore_watcher(watcher.id)
    assert restored is not None
    assert restored.archived_at is None

    active = await db.fetch_one(
        """
        SELECT COUNT(*) AS count
        FROM entity_watchers
        WHERE entity_type = ? AND entity_id = ? AND watcher = ?
          AND archived_at IS NULL
        """,
        ("task", sample_task.id, "qa@example.com"),
    )
    assert int(active["count"]) == 1
