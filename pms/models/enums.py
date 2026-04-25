"""Enumerations for PMS domain models."""

from enum import StrEnum


class ProductStatus(StrEnum):
    """Status of a product."""

    PLANNING = "planning"  # Product being planned
    ACTIVE = "active"  # Active development/maintenance
    MATURE = "mature"  # Stable, maintenance mode
    SUNSET = "sunset"  # Being phased out
    ARCHIVED = "archived"  # No longer active


class ProjectStatus(StrEnum):
    """Status of a project."""

    ACTIVE = "active"
    ARCHIVED = "archived"
    COMPLETED = "completed"
    ON_HOLD = "on_hold"


class TaskStatus(StrEnum):
    """Status of a task."""

    TODO = "todo"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    IN_REVIEW = "in_review"
    DONE = "done"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        """Check if this is a terminal status (no further transitions)."""
        return self in (TaskStatus.DONE, TaskStatus.CANCELLED)

    @property
    def is_active(self) -> bool:
        """Check if this is an active (in-flight) status."""
        return self in (TaskStatus.IN_PROGRESS, TaskStatus.IN_REVIEW)


class MilestoneStatus(StrEnum):
    """Status of a milestone."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    MISSED = "missed"


class GoalStatus(StrEnum):
    """Status of a goal."""

    ACTIVE = "active"
    COMPLETED = "completed"
    ON_HOLD = "on_hold"
    ARCHIVED = "archived"


class ActorKind(StrEnum):
    """Type of actor node in the identity graph."""

    HUMAN = "human"
    PERSONA = "persona"
    TEAM = "team"
    SERVICE_ACCOUNT = "service_account"
    RUNTIME_AGENT = "runtime_agent"


class ActorStatus(StrEnum):
    """Lifecycle status for an actor."""

    ACTIVE = "active"
    ARCHIVED = "archived"


class ActorMembershipRole(StrEnum):
    """Relationship role between a member actor and a parent actor."""

    MEMBER = "member"
    LEAD = "lead"
    REPRESENTATIVE = "representative"


class GoalHorizon(StrEnum):
    """Time horizon for a goal."""

    SHORT_TERM = "short_term"
    MEDIUM_TERM = "medium_term"
    LONG_TERM = "long_term"


class PlanStatus(StrEnum):
    """Status of a plan artifact."""

    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class PlanFormat(StrEnum):
    """Serialization format for plan content."""

    JSON = "json"
    YAML = "yaml"


class OrganizationStatus(StrEnum):
    """Status of an organization."""

    ACTIVE = "active"
    ARCHIVED = "archived"


class TeamStatus(StrEnum):
    """Status of a team."""

    ACTIVE = "active"
    ARCHIVED = "archived"


class PortfolioStatus(StrEnum):
    """Status of a portfolio."""

    ACTIVE = "active"
    ARCHIVED = "archived"


class ProgramStatus(StrEnum):
    """Status of a program."""

    ACTIVE = "active"
    ARCHIVED = "archived"


class Priority(StrEnum):
    """Task priority levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def sort_order(self) -> int:
        """Get numeric sort order (higher = more urgent)."""
        return {
            Priority.LOW: 1,
            Priority.MEDIUM: 2,
            Priority.HIGH: 3,
            Priority.CRITICAL: 4,
        }[self]


class DependencyType(StrEnum):
    """Type of task dependency."""

    BLOCKS = "blocks"  # Task A blocks Task B
    RELATES_TO = "relates_to"  # Related but not blocking
    DUPLICATES = "duplicates"  # Task is a duplicate


class HostType(StrEnum):
    """Type of remote host."""

    SSH = "ssh"
    AWS_EC2 = "aws_ec2"


class SyncDirection(StrEnum):
    """Direction of file sync."""

    PUSH = "push"  # Local to remote
    PULL = "pull"  # Remote to local


class SyncMode(StrEnum):
    """Mode of file synchronization."""

    MIRROR = "mirror"  # Make remote match local exactly
    UPDATE = "update"  # Only copy newer files
    BACKUP = "backup"  # Archive before overwriting


class SyncStatus(StrEnum):
    """Status of a sync operation."""

    STARTED = "started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class DocType(StrEnum):
    """Type of document."""

    README = "readme"
    API_DOC = "api_doc"
    CHANGELOG = "changelog"
    ARCHITECTURE = "architecture"
    CONTRIBUTING = "contributing"
    LICENSE = "license"
    CUSTOM = "custom"


class SessionStatus(StrEnum):
    """Status of an agent session."""

    ACTIVE = "active"
    PAUSED = "paused"
    ENDED = "ended"
