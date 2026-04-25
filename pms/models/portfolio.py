"""Portfolio model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Self

from pms.models.base import BaseModel, now_utc
from pms.models.enums import PortfolioStatus
from pms.models.json_types import ModelObject


@dataclass
class Portfolio(BaseModel):
    """Portfolio entity linking programs, projects, and goals."""

    org_id: str | None = None
    name: str = ""
    description: str | None = None
    status: PortfolioStatus = PortfolioStatus.ACTIVE

    owner: str | None = None
    owner_id: str | None = None
    project_ids: tuple[str, ...] = ()
    goal_ids: tuple[str, ...] = ()
    objective_ids: tuple[str, ...] = ()
    effective_goal_ids: tuple[str, ...] = ()
    effective_objective_ids: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()

    def archive(self) -> Self:
        """Archive the portfolio."""
        self.status = PortfolioStatus.ARCHIVED
        self.updated_at = now_utc()
        return self

    def add_project(self, project_id: str) -> Self:
        """Add a project to the portfolio."""
        if project_id not in self.project_ids:
            self.project_ids = (*self.project_ids, project_id)
            self.updated_at = now_utc()
        return self

    def remove_project(self, project_id: str) -> Self:
        """Remove a project from the portfolio."""
        self.project_ids = tuple(pid for pid in self.project_ids if pid != project_id)
        self.updated_at = now_utc()
        return self

    def add_direct_goal(self, goal_id: str) -> Self:
        """Add a direct goal link to the portfolio."""
        if goal_id not in self.goal_ids:
            self.goal_ids = (*self.goal_ids, goal_id)
            self.updated_at = now_utc()
        return self

    def remove_direct_goal(self, goal_id: str) -> Self:
        """Remove a direct goal link from the portfolio."""
        self.goal_ids = tuple(gid for gid in self.goal_ids if gid != goal_id)
        self.updated_at = now_utc()
        return self

    def add_direct_objective(self, objective_id: str) -> Self:
        """Add a direct objective link to the portfolio."""
        if objective_id not in self.objective_ids:
            self.objective_ids = (*self.objective_ids, objective_id)
            self.updated_at = now_utc()
        return self

    def remove_direct_objective(self, objective_id: str) -> Self:
        """Remove a direct objective link from the portfolio."""
        self.objective_ids = tuple(
            oid for oid in self.objective_ids if oid != objective_id
        )
        self.updated_at = now_utc()
        return self

    def add_tag(self, tag: str) -> Self:
        """Add a tag to the portfolio."""
        if tag not in self.tags:
            self.tags = (*self.tags, tag)
            self.updated_at = now_utc()
        return self

    def remove_tag(self, tag: str) -> Self:
        """Remove a tag from the portfolio."""
        self.tags = tuple(t for t in self.tags if t != tag)
        self.updated_at = now_utc()
        return self

    def to_dict(self) -> ModelObject:
        """Convert to dictionary with enum serialization."""
        data = super().to_dict()
        data["status"] = self.status.value
        data["project_ids"] = list(self.project_ids)
        data["goal_ids"] = list(self.goal_ids)
        data["objective_ids"] = list(self.objective_ids)
        data["effective_goal_ids"] = list(self.effective_goal_ids)
        data["effective_objective_ids"] = list(self.effective_objective_ids)
        data["tags"] = list(self.tags)
        return data

    @classmethod
    def from_dict(cls, data: ModelObject) -> Self:
        """Create from dictionary."""
        if "status" in data and isinstance(data["status"], str):
            data["status"] = PortfolioStatus(data["status"])
        if "project_ids" in data and isinstance(data["project_ids"], list):
            data["project_ids"] = tuple(data["project_ids"])
        if "goal_ids" in data and isinstance(data["goal_ids"], list):
            data["goal_ids"] = tuple(data["goal_ids"])
        if "objective_ids" in data and isinstance(data["objective_ids"], list):
            data["objective_ids"] = tuple(data["objective_ids"])
        if "effective_goal_ids" in data and isinstance(
            data["effective_goal_ids"], list
        ):
            data["effective_goal_ids"] = tuple(data["effective_goal_ids"])
        if "effective_objective_ids" in data and isinstance(
            data["effective_objective_ids"], list
        ):
            data["effective_objective_ids"] = tuple(data["effective_objective_ids"])
        if "tags" in data and isinstance(data["tags"], list):
            data["tags"] = tuple(data["tags"])
        return super().from_dict(data)


@dataclass
class PortfolioStats:
    """Rollup statistics for a portfolio."""

    portfolio_id: str
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
            "portfolio_id": self.portfolio_id,
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
