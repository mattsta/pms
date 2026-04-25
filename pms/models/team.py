"""Team model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Self

from pms.models.base import BaseModel, now_utc
from pms.models.enums import TeamStatus
from pms.models.json_types import ModelObject


@dataclass
class Team(BaseModel):
    """Team entity within an organization."""

    org_id: str | None = None
    name: str = ""
    description: str | None = None
    status: TeamStatus = TeamStatus.ACTIVE

    owner: str | None = None
    owner_id: str | None = None
    members: tuple[str, ...] = ()
    member_ids: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()

    def archive(self) -> Self:
        """Archive the team."""
        self.status = TeamStatus.ARCHIVED
        self.updated_at = now_utc()
        return self

    def add_member(self, member: str) -> Self:
        """Add a member to the team."""
        if member not in self.members:
            self.members = (*self.members, member)
            self.updated_at = now_utc()
        return self

    def remove_member(self, member: str) -> Self:
        """Remove a member from the team."""
        self.members = tuple(m for m in self.members if m != member)
        self.updated_at = now_utc()
        return self

    def add_tag(self, tag: str) -> Self:
        """Add a tag to the team."""
        if tag not in self.tags:
            self.tags = (*self.tags, tag)
            self.updated_at = now_utc()
        return self

    def remove_tag(self, tag: str) -> Self:
        """Remove a tag from the team."""
        self.tags = tuple(t for t in self.tags if t != tag)
        self.updated_at = now_utc()
        return self

    def to_dict(self) -> ModelObject:
        """Convert to dictionary with enum serialization."""
        data = super().to_dict()
        data["status"] = self.status.value
        data["members"] = list(self.members)
        data["member_ids"] = list(self.member_ids)
        data["tags"] = list(self.tags)
        return data

    @classmethod
    def from_dict(cls, data: ModelObject) -> Self:
        """Create from dictionary."""
        if "status" in data and isinstance(data["status"], str):
            data["status"] = TeamStatus(data["status"])
        if "members" in data and isinstance(data["members"], list):
            data["members"] = tuple(data["members"])
        if "member_ids" in data and isinstance(data["member_ids"], list):
            data["member_ids"] = tuple(data["member_ids"])
        if "tags" in data and isinstance(data["tags"], list):
            data["tags"] = tuple(data["tags"])
        return super().from_dict(data)
