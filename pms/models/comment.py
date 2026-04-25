"""Comment models for entity discussions and watchers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from pms.models.base import BaseModel
from pms.models.json_types import JsonObject, ModelObject


@dataclass
class Comment(BaseModel):
    """Append-only comment for an entity."""

    entity_type: str = ""
    entity_id: str = ""
    body: str = ""
    created_by: str = ""
    archived_at: datetime | None = None
    metadata: JsonObject = field(default_factory=dict)

    def to_dict(self) -> ModelObject:
        data = super().to_dict()
        data.update(
            {
                "entity_type": self.entity_type,
                "entity_id": self.entity_id,
                "body": self.body,
                "created_by": self.created_by,
                "archived_at": self.archived_at.isoformat()
                if self.archived_at
                else None,
                "metadata": self.metadata,
            }
        )
        return data


@dataclass
class CommentMention:
    """Mention record extracted from a comment."""

    id: str
    comment_id: str
    mention: str
    created_at: datetime

    def to_dict(self) -> JsonObject:
        return {
            "id": self.id,
            "comment_id": self.comment_id,
            "mention": self.mention,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class EntityWatcher(BaseModel):
    """Watcher subscription for an entity."""

    entity_type: str = ""
    entity_id: str = ""
    watcher: str = ""
    archived_at: datetime | None = None

    def to_dict(self) -> ModelObject:
        data = super().to_dict()
        data.update(
            {
                "entity_type": self.entity_type,
                "entity_id": self.entity_id,
                "watcher": self.watcher,
                "archived_at": self.archived_at.isoformat()
                if self.archived_at
                else None,
            }
        )
        return data
