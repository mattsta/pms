"""Service for comments, mentions, and watchers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from pms.core.entity_type_contract import entity_table_for_type, validate_entity_type
from pms.core.metrics import MetricsCollector
from pms.models.comment import Comment, CommentMention, EntityWatcher
from pms.repositories.comment_mention_repository import CommentMentionRepository
from pms.repositories.comment_repository import CommentRepository
from pms.repositories.entity_watcher_repository import EntityWatcherRepository

if TYPE_CHECKING:
    from pms.db.connection import Database

type JsonScalar = str | int | float | bool | datetime | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]

_MENTION_RE = re.compile(r"@([A-Za-z0-9_.:-]+)")


@dataclass
class CommentItem:
    """Comment with associated mentions."""

    comment: Comment
    mentions: list[CommentMention]

    def to_dict(self) -> JsonObject:
        return {
            "comment": self.comment.to_dict(),
            "mentions": [mention.to_dict() for mention in self.mentions],
        }


@dataclass
class CommentPage:
    """Paginated comments result."""

    items: list[CommentItem]
    total_count: int
    offset: int
    limit: int


@dataclass
class WatcherPage:
    """Paginated watcher result."""

    items: list[EntityWatcher]
    total_count: int
    offset: int
    limit: int


class CommentService:
    """Service for comment management and watchers."""

    def __init__(self, db: Database, metrics: MetricsCollector) -> None:
        self.db = db
        self.metrics = metrics
        self._comments = CommentRepository(db)
        self._mentions = CommentMentionRepository(db)
        self._watchers = EntityWatcherRepository(db)

    def _normalize_entity_type(self, entity_type: str) -> str:
        return validate_entity_type(entity_type)

    def _validate_entity_type(self, entity_type: str) -> None:
        validate_entity_type(entity_type)

    async def _ensure_entity_exists(self, entity_type: str, entity_id: str) -> None:
        table = entity_table_for_type(entity_type)
        if not table:
            return
        row = await self.db.fetch_one(
            f"SELECT id FROM {table} WHERE id = ?",
            (entity_id,),
        )
        if row is None:
            raise ValueError(f"{entity_type} '{entity_id}' not found")

    def _extract_mentions(self, body: str) -> list[str]:
        return [match.group(1) for match in _MENTION_RE.finditer(body or "")]

    async def add_comment(
        self,
        entity_type: str,
        entity_id: str,
        body: str,
        created_by: str,
        mentions: list[str] | None = None,
        metadata: JsonObject | None = None,
        watch: bool = False,
    ) -> CommentItem:
        normalized = self._normalize_entity_type(entity_type)
        self._validate_entity_type(normalized)
        await self._ensure_entity_exists(normalized, entity_id)

        extracted = self._extract_mentions(body)
        all_mentions = list(dict.fromkeys((mentions or []) + extracted))

        async with self.db.transaction():
            comment = await self._comments._create_in_transaction(
                entity_type=normalized,
                entity_id=entity_id,
                body=body,
                created_by=created_by,
                metadata=metadata,
            )

            mention_records: list[CommentMention] = []
            if all_mentions:
                mention_records = await self._mentions._add_mentions_in_transaction(
                    comment_id=comment.id,
                    mentions=all_mentions,
                )

            if watch and created_by:
                await self._watchers._add_in_transaction(
                    entity_type=normalized,
                    entity_id=entity_id,
                    watcher=created_by,
                )

            await self.metrics.record_counter(
                "comment.created",
                labels={"entity_type": normalized},
            )
            if watch and created_by:
                await self.metrics.record_counter(
                    "watcher.added",
                    labels={"entity_type": normalized},
                )
            await self.metrics.flush()
        return CommentItem(comment=comment, mentions=mention_records)

    async def list_comments(
        self,
        entity_type: str,
        entity_id: str,
        *,
        include_archived: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> CommentPage:
        normalized = self._normalize_entity_type(entity_type)
        self._validate_entity_type(normalized)
        await self._ensure_entity_exists(normalized, entity_id)

        page = await self._comments.list_by_entity(
            normalized,
            entity_id,
            include_archived=include_archived,
            limit=limit,
            offset=offset,
        )
        mentions_map = await self._mentions.list_for_comments(
            [comment.id for comment in page.items]
        )
        items = [
            CommentItem(
                comment=comment,
                mentions=mentions_map.get(comment.id, []),
            )
            for comment in page.items
        ]
        return CommentPage(
            items=items,
            total_count=page.total_count,
            offset=page.offset,
            limit=page.limit,
        )

    async def get_comment(
        self, comment_id: str, *, include_archived: bool = False
    ) -> CommentItem | None:
        comment = await self._comments.get_by_id(
            comment_id, include_archived=include_archived
        )
        if comment is None:
            return None
        mentions = await self._mentions.list_by_comment(comment_id)
        return CommentItem(comment=comment, mentions=mentions)

    async def delete_comment(self, comment_id: str) -> bool:
        return await self._comments.delete(comment_id, message="Archived comment")

    async def restore_comment(self, comment_id: str) -> Comment | None:
        return await self._comments.restore(comment_id)

    async def add_watcher(
        self,
        entity_type: str,
        entity_id: str,
        watcher: str,
    ) -> EntityWatcher:
        normalized = self._normalize_entity_type(entity_type)
        self._validate_entity_type(normalized)
        await self._ensure_entity_exists(normalized, entity_id)

        async with self.db.transaction():
            watcher_obj = await self._watchers._add_in_transaction(
                entity_type=normalized,
                entity_id=entity_id,
                watcher=watcher,
            )
            await self.metrics.record_counter(
                "watcher.added",
                labels={"entity_type": normalized},
            )
            await self.metrics.flush()
        return watcher_obj

    async def remove_watcher(
        self,
        entity_type: str,
        entity_id: str,
        watcher: str,
    ) -> bool:
        normalized = self._normalize_entity_type(entity_type)
        self._validate_entity_type(normalized)
        await self._ensure_entity_exists(normalized, entity_id)
        async with self.db.transaction():
            removed = await self._watchers._remove_in_transaction(
                entity_type=normalized,
                entity_id=entity_id,
                watcher=watcher,
            )
            if removed:
                await self.metrics.record_counter(
                    "watcher.removed",
                    labels={"entity_type": normalized},
                )
                await self.metrics.flush()
        return removed

    async def list_watchers(
        self,
        entity_type: str,
        entity_id: str,
        *,
        include_archived: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> WatcherPage:
        normalized = self._normalize_entity_type(entity_type)
        self._validate_entity_type(normalized)
        await self._ensure_entity_exists(normalized, entity_id)

        page = await self._watchers.list_by_entity(
            normalized,
            entity_id,
            include_archived=include_archived,
            limit=limit,
            offset=offset,
        )
        return WatcherPage(
            items=page.items,
            total_count=page.total_count,
            offset=page.offset,
            limit=page.limit,
        )

    async def restore_watcher(self, watcher_id: str) -> EntityWatcher | None:
        return await self._watchers.restore(watcher_id)
