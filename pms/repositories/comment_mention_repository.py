"""Repository for comment mentions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pms.models.base import generate_id, now_utc
from pms.models.comment import CommentMention
from pms.repositories.base import OwnedTransactionRepository

if TYPE_CHECKING:
    from pms.db.connection import Database


class CommentMentionRepository(OwnedTransactionRepository):
    """Repository for comment mentions."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def add_mentions(
        self,
        comment_id: str,
        mentions: list[str],
    ) -> list[CommentMention]:
        async def _add() -> list[CommentMention]:
            return await self._add_mentions_in_transaction(
                comment_id=comment_id,
                mentions=mentions,
            )

        return await self._run_in_owned_transaction(
            _add,
            operation_name="add_mentions",
        )

    async def _add_mentions_in_transaction(
        self,
        *,
        comment_id: str,
        mentions: list[str],
    ) -> list[CommentMention]:
        """Insert comment mentions assuming the caller already owns the transaction."""
        self._assert_owned_transaction("_add_mentions_in_transaction")
        unique_mentions = [m for m in dict.fromkeys(mentions) if m]
        items: list[CommentMention] = []
        for mention in unique_mentions:
            record = CommentMention(
                id=generate_id(),
                comment_id=comment_id,
                mention=mention,
                created_at=now_utc(),
            )
            items.append(record)
            await self.db.execute(
                """
                INSERT INTO comment_mentions (id, comment_id, mention, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.comment_id,
                    record.mention,
                    record.created_at.isoformat(),
                ),
            )
        return items

    async def list_by_comment(self, comment_id: str) -> list[CommentMention]:
        rows = await self.db.fetch_all(
            """
            SELECT id, comment_id, mention, created_at
            FROM comment_mentions
            WHERE comment_id = ?
            ORDER BY created_at
            """,
            (comment_id,),
        )
        return [
            CommentMention(
                id=row["id"],
                comment_id=row["comment_id"],
                mention=row["mention"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    async def list_for_comments(
        self, comment_ids: list[str]
    ) -> dict[str, list[CommentMention]]:
        if not comment_ids:
            return {}
        unique_ids = list(dict.fromkeys(comment_ids))
        placeholders = ", ".join("?" * len(unique_ids))
        rows = await self.db.fetch_all(
            f"""
            SELECT id, comment_id, mention, created_at
            FROM comment_mentions
            WHERE comment_id IN ({placeholders})
            ORDER BY created_at
            """,
            tuple(unique_ids),
        )
        mentions_map: dict[str, list[CommentMention]] = {cid: [] for cid in unique_ids}
        for row in rows:
            mention = CommentMention(
                id=row["id"],
                comment_id=row["comment_id"],
                mention=row["mention"],
                created_at=row["created_at"],
            )
            mentions_map.setdefault(row["comment_id"], []).append(mention)
        return mentions_map
