"""Organization model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Self

from pms.models.base import BaseModel, now_utc
from pms.models.enums import OrganizationStatus
from pms.models.json_types import ModelObject


@dataclass
class Organization(BaseModel):
    """Organization entity for grouping portfolios, teams, and programs."""

    name: str = ""
    description: str | None = None
    status: OrganizationStatus = OrganizationStatus.ACTIVE

    owner: str | None = None
    owner_id: str | None = None
    members: tuple[str, ...] = ()
    member_ids: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()

    def archive(self) -> Self:
        """Archive the organization."""
        self.status = OrganizationStatus.ARCHIVED
        self.updated_at = now_utc()
        return self

    def add_member(self, member: str) -> Self:
        """Add a member to the organization."""
        if member not in self.members:
            self.members = (*self.members, member)
            self.updated_at = now_utc()
        return self

    def remove_member(self, member: str) -> Self:
        """Remove a member from the organization."""
        self.members = tuple(m for m in self.members if m != member)
        self.updated_at = now_utc()
        return self

    def add_tag(self, tag: str) -> Self:
        """Add a tag to the organization."""
        if tag not in self.tags:
            self.tags = (*self.tags, tag)
            self.updated_at = now_utc()
        return self

    def remove_tag(self, tag: str) -> Self:
        """Remove a tag from the organization."""
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
            data["status"] = OrganizationStatus(data["status"])
        if "members" in data and isinstance(data["members"], list):
            data["members"] = tuple(data["members"])
        if "member_ids" in data and isinstance(data["member_ids"], list):
            data["member_ids"] = tuple(data["member_ids"])
        if "tags" in data and isinstance(data["tags"], list):
            data["tags"] = tuple(data["tags"])
        return super().from_dict(data)


@dataclass
class OrganizationStats:
    """Rollup statistics for an organization."""

    organization_id: str
    total_teams: int = 0
    total_portfolios: int = 0
    total_programs: int = 0
    total_projects: int = 0
    total_goals: int = 0
    completed_goals: int = 0
    avg_goal_progress: float = 0.0
    total_objectives: int = 0
    completed_objectives: int = 0
    avg_objective_progress: float = 0.0
    total_tasks: int = 0
    blocked_tasks: int = 0
    horizon_breakdown: dict[str, int] = field(default_factory=dict)
    horizon_completion: dict[str, float] = field(default_factory=dict)
    risk_score: float = 0.0

    def to_dict(self) -> ModelObject:
        """Serialize stats for JSON outputs."""
        return {
            "organization_id": self.organization_id,
            "total_teams": self.total_teams,
            "total_portfolios": self.total_portfolios,
            "total_programs": self.total_programs,
            "total_projects": self.total_projects,
            "total_goals": self.total_goals,
            "completed_goals": self.completed_goals,
            "avg_goal_progress": self.avg_goal_progress,
            "total_objectives": self.total_objectives,
            "completed_objectives": self.completed_objectives,
            "avg_objective_progress": self.avg_objective_progress,
            "total_tasks": self.total_tasks,
            "blocked_tasks": self.blocked_tasks,
            "horizon_breakdown": dict(self.horizon_breakdown),
            "horizon_completion": dict(self.horizon_completion),
            "risk_score": self.risk_score,
        }
