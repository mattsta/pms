"""Actor identity graph models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Self

from pms.models.base import BaseModel, now_utc
from pms.models.enums import ActorKind, ActorMembershipRole, ActorStatus
from pms.models.json_types import JsonObject, ModelObject


@dataclass
class Actor(BaseModel):
    """Canonical identity node for humans, personas, teams, and runtime agents."""

    kind: ActorKind = ActorKind.HUMAN
    name: str = ""
    handle: str = ""
    description: str | None = None
    status: ActorStatus = ActorStatus.ACTIVE
    tags: tuple[str, ...] = ()
    metadata: JsonObject = field(default_factory=dict)
    archived_at: datetime | None = None

    def archive(self) -> Self:
        """Archive this actor."""
        self.status = ActorStatus.ARCHIVED
        self.archived_at = now_utc()
        self.updated_at = now_utc()
        return self

    def to_dict(self) -> ModelObject:
        """Serialize actor with enum values."""
        data = super().to_dict()
        data["kind"] = self.kind.value
        data["status"] = self.status.value
        data["tags"] = list(self.tags)
        data["metadata"] = dict(self.metadata)
        return data

    @classmethod
    def from_dict(cls, data: ModelObject) -> Self:
        """Deserialize actor payload."""
        payload = dict(data)
        if "kind" in payload and isinstance(payload["kind"], str):
            payload["kind"] = ActorKind(payload["kind"])
        if "status" in payload and isinstance(payload["status"], str):
            payload["status"] = ActorStatus(payload["status"])
        if "tags" in payload and isinstance(payload["tags"], list):
            payload["tags"] = tuple(str(item) for item in payload["tags"])
        return super().from_dict(payload)


@dataclass
class ActorAlias(BaseModel):
    """Alias that resolves to an actor."""

    actor_id: str = ""
    alias: str = ""
    normalized_alias: str = ""
    archived_at: datetime | None = None


@dataclass
class ActorMembership(BaseModel):
    """Membership edge between actors."""

    parent_actor_id: str = ""
    member_actor_id: str = ""
    role: ActorMembershipRole = ActorMembershipRole.MEMBER
    archived_at: datetime | None = None

    def to_dict(self) -> ModelObject:
        """Serialize membership with enum values."""
        data = super().to_dict()
        data["role"] = self.role.value
        return data

    @classmethod
    def from_dict(cls, data: ModelObject) -> Self:
        """Deserialize membership payload."""
        payload = dict(data)
        if "role" in payload and isinstance(payload["role"], str):
            payload["role"] = ActorMembershipRole(payload["role"])
        return super().from_dict(payload)
