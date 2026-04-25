"""Pydantic models for API requests and responses."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from pms.api.types import JsonObject, JsonValue
from pms.core.revisions import ChangeType
from pms.models.automation_rule import AutomationActionType
from pms.models.custom_field import CustomFieldType
from pms.models.enums import (
    ActorKind,
    ActorMembershipRole,
    ActorStatus,
    GoalHorizon,
    GoalStatus,
    OrganizationStatus,
    PlanFormat,
    PlanStatus,
    PortfolioStatus,
    Priority,
    ProductStatus,
    ProgramStatus,
    ProjectStatus,
    SessionStatus,
    TaskStatus,
    TeamStatus,
)
from pms.models.label_gate_rule import LabelGateRuleType
from pms.models.value_contracts import (
    QueuePopulation,
    RetentionUsageSort,
    RiskLevel,
    SortDirection,
)

_AUTOMATION_ACTION_TYPE_VALUES = [value.value for value in AutomationActionType]
SavedSearchScopeType = Literal["global", "organization", "program", "project"]
WorkSnapshotScopeType = Literal["organization", "portfolio", "program", "project"]
RetentionPolicyScopeType = Literal["project", "organization"]
RetentionSummaryScopeType = Literal["default", "project", "organization"]
RetentionAlertSeverity = Literal["warning", "critical"]
TransitionTimelineKind = Literal["workflow", "status"]
TaskCompletionStatus = Literal["completed"]
AutomationRunStatus = Literal["running", "skipped", "dry_run", "success", "failed"]
HealthStatus = Literal["healthy", "degraded"]

# ============================================================
# Actor Models
# ============================================================


class ActorCreate(BaseModel):
    """Request model for creating an actor."""

    name: str = Field(..., min_length=1, max_length=200)
    kind: str = "human"
    handle: str | None = None
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: JsonObject = Field(default_factory=dict)


class ActorAliasCreate(BaseModel):
    """Request model for creating an actor alias."""

    alias: str = Field(..., min_length=1, max_length=200)


class ActorMembershipCreate(BaseModel):
    """Request model for creating an actor membership."""

    member: str = Field(..., min_length=1, max_length=200)
    role: str = "member"


class ActorResponse(BaseModel):
    """Response model for actor."""

    id: str
    name: str
    handle: str
    kind: ActorKind
    description: str | None
    status: ActorStatus
    tags: list[str]
    metadata: JsonObject
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None
    last_activity_at: datetime | None = None
    last_transition_at: datetime | None = None


class ActorAliasResponse(BaseModel):
    """Response model for actor alias."""

    id: str
    actor_id: str
    alias: str
    normalized_alias: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None


class ActorMembershipResponse(BaseModel):
    """Response model for actor membership."""

    id: str
    parent_actor_id: str
    member_actor_id: str
    role: ActorMembershipRole
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None


class ActorReferencePayload(BaseModel):
    """Resolved actor reference payload."""

    ref: str | None = None
    id: str | None = None
    actor: JsonObject | None = None
    links: JsonObject = Field(default_factory=dict)


class CheckoutPayload(BaseModel):
    """Resolved checkout identity and lease payload."""

    agent_session_id: str | None = None
    actor: ActorReferencePayload | None = None
    checked_out_at: datetime | None = None
    lease_until: datetime | None = None
    version: int | None = None
    expired: bool | None = None


class ActorGraphResponse(BaseModel):
    """Actor graph and workload response."""

    actor: ActorResponse
    last_activity_at: datetime | None = None
    last_transition_at: datetime | None = None
    aliases: list[ActorAliasResponse] = Field(default_factory=list)
    memberships: JsonObject = Field(default_factory=dict)
    workload: JsonObject = Field(default_factory=dict)
    ownership: JsonObject = Field(default_factory=dict)
    project_workloads: list[JsonObject] = Field(default_factory=list)
    graph_navigation: JsonObject = Field(default_factory=dict)
    links: JsonObject = Field(default_factory=dict)
    next_steps: list[str] = Field(default_factory=list)


# ============================================================
# Product Models
# ============================================================


class ProductCreate(BaseModel):
    """Request model for creating a product."""

    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    vision: str | None = None
    repository_url: str | None = None
    owner: str | None = None
    product_type: str = Field(
        "service",
        description=(
            "Descriptive product category. Intentionally open; not a closed enum "
            "or product taxonomy."
        ),
    )
    tags: list[str] = Field(default_factory=list)


class ProductUpdate(BaseModel):
    """Request model for updating a product."""

    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    vision: str | None = None
    repository_url: str | None = None
    owner: str | None = None
    product_type: str | None = Field(
        None,
        description=(
            "Descriptive product category. Intentionally open; not a closed enum "
            "or product taxonomy."
        ),
    )
    status: str | None = None  # Allow status updates
    tags: list[str] | None = None


class ProductResponse(BaseModel):
    """Response model for product."""

    id: str
    name: str
    description: str | None
    status: ProductStatus
    vision: str | None
    repository_url: str | None
    owner: ActorReferencePayload | None = None
    product_type: str = Field(
        ...,
        description=(
            "Descriptive product category. Intentionally open; not a closed enum "
            "or product taxonomy."
        ),
    )
    tags: list[str]
    created_at: datetime
    updated_at: datetime


# ============================================================
# Organization Models
# ============================================================


class OrganizationCreate(BaseModel):
    """Request model for creating an organization."""

    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    owner: str | None = None
    members: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class OrganizationUpdate(BaseModel):
    """Request model for updating an organization."""

    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    status: str | None = None
    owner: str | None = None
    members: list[str] | None = None
    tags: list[str] | None = None


class OrganizationResponse(BaseModel):
    """Response model for organization."""

    id: str
    name: str
    description: str | None
    status: OrganizationStatus
    owner: ActorReferencePayload | None = None
    members: list[ActorReferencePayload] = Field(default_factory=list)
    tags: list[str]
    created_at: datetime
    updated_at: datetime


# ============================================================
# Team Models
# ============================================================


class TeamCreate(BaseModel):
    """Request model for creating a team."""

    name: str = Field(..., min_length=1, max_length=200)
    org_id: str | None = None
    description: str | None = None
    owner: str | None = None
    members: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class TeamUpdate(BaseModel):
    """Request model for updating a team."""

    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    status: str | None = None
    owner: str | None = None
    members: list[str] | None = None
    tags: list[str] | None = None


class TeamResponse(BaseModel):
    """Response model for team."""

    id: str
    org_id: str | None
    name: str
    description: str | None
    status: TeamStatus
    owner: ActorReferencePayload | None = None
    members: list[ActorReferencePayload] = Field(default_factory=list)
    tags: list[str]
    created_at: datetime
    updated_at: datetime


# ============================================================
# Portfolio Models
# ============================================================


class PortfolioCreate(BaseModel):
    """Request model for creating a portfolio."""

    name: str = Field(..., min_length=1, max_length=200)
    org_id: str | None = None
    description: str | None = None
    owner: str | None = None
    project_ids: list[str] = Field(default_factory=list)
    goal_ids: list[str] = Field(default_factory=list)
    objective_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class PortfolioUpdate(BaseModel):
    """Request model for updating a portfolio."""

    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    status: str | None = None
    owner: str | None = None
    project_ids: list[str] | None = None
    goal_ids: list[str] | None = None
    objective_ids: list[str] | None = None
    tags: list[str] | None = None


class PortfolioResponse(BaseModel):
    """Response model for portfolio."""

    id: str
    org_id: str | None
    name: str
    description: str | None
    status: PortfolioStatus
    owner: ActorReferencePayload | None = None
    project_ids: list[str]
    goal_ids: list[str]
    objective_ids: list[str]
    effective_goal_ids: list[str]
    effective_objective_ids: list[str]
    tags: list[str]
    created_at: datetime
    updated_at: datetime


# ============================================================
# Program Models
# ============================================================


class ProgramCreate(BaseModel):
    """Request model for creating a program."""

    name: str = Field(..., min_length=1, max_length=200)
    org_id: str | None = None
    portfolio_id: str | None = None
    description: str | None = None
    owner: str | None = None
    project_ids: list[str] = Field(default_factory=list)
    goal_ids: list[str] = Field(default_factory=list)
    objective_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class ProgramUpdate(BaseModel):
    """Request model for updating a program."""

    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    status: str | None = None
    owner: str | None = None
    project_ids: list[str] | None = None
    goal_ids: list[str] | None = None
    objective_ids: list[str] | None = None
    tags: list[str] | None = None


class ProgramResponse(BaseModel):
    """Response model for program."""

    id: str
    org_id: str | None
    portfolio_id: str | None
    name: str
    description: str | None
    status: ProgramStatus
    owner: ActorReferencePayload | None = None
    project_ids: list[str]
    goal_ids: list[str]
    objective_ids: list[str]
    effective_goal_ids: list[str]
    effective_objective_ids: list[str]
    tags: list[str]
    created_at: datetime
    updated_at: datetime


# ============================================================
# Goal Models
# ============================================================


class GoalCreate(BaseModel):
    """Request model for creating a goal."""

    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    horizon: str = "short_term"
    target_date: datetime | None = None
    owner: str | None = None
    product_id: str | None = None
    project_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    progress_percent: int = Field(0, ge=0, le=100)


class GoalUpdate(BaseModel):
    """Request model for updating a goal."""

    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    status: str | None = None
    horizon: str | None = None
    target_date: datetime | None = None
    owner: str | None = None
    product_id: str | None = None
    project_id: str | None = None
    tags: list[str] | None = None
    progress_percent: int | None = Field(None, ge=0, le=100)


class GoalResponse(BaseModel):
    """Response model for goal."""

    id: str
    name: str
    description: str | None
    status: GoalStatus
    horizon: GoalHorizon
    target_date: datetime | None
    owner: ActorReferencePayload | None = None
    product_id: str | None
    project_id: str | None
    tags: list[str]
    progress_percent: int
    workflow_id: str | None
    current_state: str | None
    created_at: datetime
    updated_at: datetime


class GoalEffectiveRollupResponse(BaseModel):
    """Execution-aware effective goal rollup."""

    progress_percent: int
    status: str
    basis: str
    reason: str | None = None


class GoalEffectiveHierarchyResponse(BaseModel):
    """Execution-aware hierarchy rollup for a goal."""

    objective_count: int
    completed_objectives: int
    key_result_count: int
    completed_key_results: int
    average_progress: float
    basis: str
    reason: str | None = None


class GoalExecutionFocusTaskResponse(BaseModel):
    """Minimal operator focus payload for goal execution."""

    id: str
    title: str
    status: str
    current_progress_percent: int
    reason: str
    completion_criteria_count: int
    has_completion_criteria: bool


class GoalExecutionSummaryResponse(BaseModel):
    """Execution summary payload for a goal."""

    total_tasks: int
    completed_tasks: int
    in_progress_tasks: int
    blocked_tasks: int
    average_task_progress: float
    completion_percent: float
    readiness_state: str
    consistency_status: str
    consistency_reason: str | None = None
    terminal_reason: str | None = None
    focus_task: GoalExecutionFocusTaskResponse | None = None
    population_basis: str
    scoped_goal_count: int


class GoalSummaryStatsResponse(BaseModel):
    """Rollup statistics for a goal summary."""

    objective_count: int
    completed_objectives: int
    key_result_count: int
    completed_key_results: int
    average_progress: float


class CompletionContextResponse(BaseModel):
    """Completion context for terminal operator views."""

    summary: str
    next_steps: list[str] = Field(default_factory=list)


class GoalListItemResponse(GoalResponse):
    """Lifecycle-aware goal payload used by list surfaces."""

    effective_rollup: GoalEffectiveRollupResponse | None = None
    last_activity_at: datetime | None = None
    last_transition_at: datetime | None = None
    terminal_reason: str | None = None
    links: JsonObject = Field(default_factory=dict)
    next_steps: list[str] = Field(default_factory=list)


class GoalDetailResponse(GoalListItemResponse):
    """Lifecycle-aware goal detail payload."""

    stats: GoalSummaryStatsResponse
    effective_hierarchy: GoalEffectiveHierarchyResponse
    execution: GoalExecutionSummaryResponse | None = None
    completion_context: CompletionContextResponse | None = None
    next_steps: list[str] = Field(default_factory=list)


class GoalSummaryResponse(BaseModel):
    """Goal summary payload."""

    goal: GoalResponse
    stats: GoalSummaryStatsResponse
    effective_rollup: GoalEffectiveRollupResponse
    effective_hierarchy: GoalEffectiveHierarchyResponse
    execution: GoalExecutionSummaryResponse | None = None
    terminal_reason: str | None = None
    completion_context: CompletionContextResponse | None = None
    last_activity_at: datetime | None = None
    last_transition_at: datetime | None = None
    links: JsonObject = Field(default_factory=dict)
    next_steps: list[str] = Field(default_factory=list)


# ============================================================
# Plan Models
# ============================================================


class PlanCreate(BaseModel):
    """Request model for creating a plan."""

    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    status: str = "draft"
    format: str = "json"
    content: JsonObject | list[JsonValue] | str
    product_id: str | None = None
    project_id: str | None = None
    goal_id: str | None = None
    objective_id: str | None = None
    task_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class PlanUpdate(BaseModel):
    """Request model for updating a plan."""

    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    status: str | None = None
    format: str | None = None
    content: JsonObject | list[JsonValue] | str | None = None
    product_id: str | None = None
    project_id: str | None = None
    goal_id: str | None = None
    objective_id: str | None = None
    task_ids: list[str] | None = None
    tags: list[str] | None = None


class PlanResponse(BaseModel):
    """Response model for plan."""

    id: str
    name: str
    description: str | None
    status: PlanStatus
    stored_status: PlanStatus | None = None
    format: PlanFormat
    content: str
    product_id: str | None
    project_id: str | None
    goal_id: str | None
    objective_id: str | None
    task_ids: list[str]
    tags: list[str]
    created_at: datetime
    updated_at: datetime
    last_activity_at: datetime | None = None
    last_transition_at: datetime | None = None
    links: JsonObject = Field(default_factory=dict)
    next_steps: list[str] = Field(default_factory=list)
    focus_task: JsonObject | None = None
    terminal_reason: str | None = None


# ============================================================
# Plan Test Job Models
# ============================================================


class EnvVarPair(BaseModel):
    """Key/value environment variable pair."""

    key: str = Field(..., min_length=1)
    value: str


class PlanTestJobCreate(BaseModel):
    """Request model for creating a plan test job."""

    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    mode: Literal["local", "aws"] = "local"
    project_path: str = Field(..., min_length=1)
    test_command: str = "pytest"
    setup_command: str | None = None
    working_dir: str | None = None
    env_vars: list[EnvVarPair] = Field(default_factory=list)
    timeout: float = Field(600.0, gt=0)
    capture_logs: list[str] = Field(default_factory=list)
    save_artifacts: list[str] = Field(default_factory=list)
    task_ids: list[str] = Field(default_factory=list)
    transition_on_success: str | None = None
    transition_on_failure: str | None = None
    transition_by: str | None = None
    transition_reason: str | None = None
    project_id: str | None = None
    server_id: str | None = None
    server_name: str | None = None
    remote_path: str = "/home/ec2-user/project"
    exclude_patterns: list[str] | None = None
    stream_output: bool = Field(
        False,
        description=(
            "Deprecated for persisted plan test jobs. Live output is only available "
            "through interactive `pms aws test run`; plan-job runs expose stdout/stderr "
            "after completion via the resulting test run."
        ),
        json_schema_extra={"deprecated": True},
    )


class PlanTestJobUpdate(BaseModel):
    """Request model for updating a plan test job."""

    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    mode: Literal["local", "aws"] | None = None
    project_path: str | None = None
    test_command: str | None = None
    setup_command: str | None = None
    working_dir: str | None = None
    env_vars: list[EnvVarPair] | None = None
    timeout: float | None = Field(None, gt=0)
    capture_logs: list[str] | None = None
    save_artifacts: list[str] | None = None
    task_ids: list[str] | None = None
    transition_on_success: str | None = None
    transition_on_failure: str | None = None
    transition_by: str | None = None
    transition_reason: str | None = None
    project_id: str | None = None
    server_id: str | None = None
    server_name: str | None = None
    remote_path: str | None = None
    exclude_patterns: list[str] | None = None
    stream_output: bool | None = Field(
        None,
        description=(
            "Deprecated for persisted plan test jobs. Live output is only available "
            "through interactive `pms aws test run`; plan-job runs expose stdout/stderr "
            "after completion via the resulting test run."
        ),
        json_schema_extra={"deprecated": True},
    )


class PlanTestJobResponse(BaseModel):
    """Response model for plan test jobs."""

    id: str
    plan_id: str
    name: str
    description: str | None
    mode: Literal["local", "aws"]
    project_path: str
    test_command: str
    setup_command: str | None
    working_dir: str | None
    env_vars: list[EnvVarPair]
    timeout: float
    capture_logs: list[str]
    save_artifacts: list[str]
    task_ids: list[str]
    transition_on_success: str | None
    transition_on_failure: str | None
    transition_by: str | None
    transition_reason: str | None
    project_id: str | None
    server_id: str | None
    server_name: str | None
    remote_path: str
    exclude_patterns: list[str] | None
    stream_output: bool = Field(
        ...,
        description=(
            "Deprecated persisted flag. Historical records may still contain it, but "
            "plan-job runs do not provide live streaming output."
        ),
        json_schema_extra={"deprecated": True},
    )
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None


class PlanTestJobListResponse(BaseModel):
    """Response model for listing plan test jobs."""

    items: list[PlanTestJobResponse] = Field(default_factory=list)
    total_count: int
    offset: int
    limit: int
    links: JsonObject = Field(default_factory=dict)
    next_steps: list[str] = Field(default_factory=list)
    params: JsonObject = Field(default_factory=dict)


class PlanTestJobRunResponse(BaseModel):
    """Response model for running a plan test job."""

    job: PlanTestJobResponse
    test_run: TestRunResponse


# ============================================================
# Objective Models
# ============================================================


class ObjectiveCreate(BaseModel):
    """Request model for creating an objective."""

    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    target_date: datetime | None = None
    owner: str | None = None
    tags: list[str] = Field(default_factory=list)
    progress_percent: int = Field(0, ge=0, le=100)


class ObjectiveUpdate(BaseModel):
    """Request model for updating an objective."""

    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    status: str | None = None
    target_date: datetime | None = None
    owner: str | None = None
    tags: list[str] | None = None
    progress_percent: int | None = Field(None, ge=0, le=100)


class ObjectiveResponse(BaseModel):
    """Response model for objective."""

    id: str
    goal_id: str
    name: str
    description: str | None
    status: GoalStatus
    target_date: datetime | None
    owner: ActorReferencePayload | None = None
    tags: list[str]
    progress_percent: int
    workflow_id: str | None
    current_state: str | None
    created_at: datetime
    updated_at: datetime


class ObjectiveEffectiveRollupResponse(BaseModel):
    """Key-result-aware effective objective rollup."""

    progress_percent: int
    status: str
    basis: str
    reason: str | None = None


class ObjectiveEffectiveHierarchyResponse(BaseModel):
    """Key-result-aware hierarchy rollup for an objective."""

    key_result_count: int
    completed_key_results: int
    average_progress: float
    basis: str
    reason: str | None = None


class ObjectiveSummaryStatsResponse(BaseModel):
    """Rollup statistics for one objective."""

    key_result_count: int
    completed_key_results: int
    average_progress: float


class ObjectiveListItemResponse(ObjectiveResponse):
    """Lifecycle-aware objective payload used by list surfaces."""

    project_id: str | None = None
    effective_rollup: ObjectiveEffectiveRollupResponse | None = None
    effective_hierarchy: ObjectiveEffectiveHierarchyResponse | None = None
    last_activity_at: datetime | None = None
    last_transition_at: datetime | None = None
    terminal_reason: str | None = None
    links: JsonObject = Field(default_factory=dict)
    next_steps: list[str] = Field(default_factory=list)


class ObjectiveDetailResponse(ObjectiveListItemResponse):
    """Lifecycle-aware objective detail payload."""

    stats: ObjectiveSummaryStatsResponse
    completion_context: CompletionContextResponse | None = None


# ============================================================
# Key Result Models
# ============================================================


class KeyResultCreate(BaseModel):
    """Request model for creating a key result."""

    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    current_value: float | None = None
    target_value: float | None = None
    unit: str | None = None
    owner: str | None = None
    tags: list[str] = Field(default_factory=list)
    progress_percent: int | None = Field(None, ge=0, le=100)


class KeyResultUpdate(BaseModel):
    """Request model for updating a key result."""

    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    status: str | None = None
    current_value: float | None = None
    target_value: float | None = None
    unit: str | None = None
    owner: str | None = None
    tags: list[str] | None = None
    progress_percent: int | None = Field(None, ge=0, le=100)


class KeyResultResponse(BaseModel):
    """Response model for key result."""

    id: str
    objective_id: str
    name: str
    description: str | None
    status: GoalStatus
    current_value: float | None
    target_value: float | None
    unit: str | None
    owner: ActorReferencePayload | None = None
    tags: list[str]
    progress_percent: int
    created_at: datetime
    updated_at: datetime


class KeyResultEffectiveRollupResponse(BaseModel):
    """Lifecycle rollup for one key result leaf."""

    progress_percent: int
    status: str
    basis: str
    reason: str | None = None


class KeyResultListItemResponse(KeyResultResponse):
    """Lifecycle-aware key result payload used by list surfaces."""

    goal_id: str
    project_id: str | None = None
    effective_rollup: KeyResultEffectiveRollupResponse | None = None
    last_activity_at: datetime | None = None
    last_transition_at: datetime | None = None
    terminal_reason: str | None = None
    links: JsonObject = Field(default_factory=dict)
    next_steps: list[str] = Field(default_factory=list)


class KeyResultDetailResponse(KeyResultListItemResponse):
    """Lifecycle-aware key result detail payload."""

    completion_context: CompletionContextResponse | None = None


# ============================================================
# Project Models
# ============================================================


class ProjectCreate(BaseModel):
    """Request model for creating a project."""

    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    org_id: str | None = None
    portfolio_id: str | None = None
    program_id: str | None = None
    product_id: str | None = None


class ProjectUpdate(BaseModel):
    """Request model for updating a project."""

    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    tags: list[str] | None = None
    org_id: str | None = None
    portfolio_id: str | None = None
    program_id: str | None = None
    product_id: str | None = None
    status: str | None = None  # Allow status updates


class ProjectResponse(BaseModel):
    """Response model for project."""

    id: str
    name: str
    description: str | None
    status: ProjectStatus
    tags: list[str]
    org_id: str | None
    portfolio_id: str | None
    program_id: str | None
    product_id: str | None
    created_at: datetime
    updated_at: datetime
    stored_status: ProjectStatus | None = None
    last_activity_at: datetime | None = None
    last_transition_at: datetime | None = None
    operator_category: str | None = None
    operator_category_label: str | None = None
    operator_visibility_reason: str | None = None
    terminal_reason: str | None = None
    focus_task: JsonObject | None = None
    links: JsonObject = Field(default_factory=dict)
    next_steps: list[str] = Field(default_factory=list)


# ============================================================
# Task Models
# ============================================================


class TaskCreate(BaseModel):
    """Request model for creating a task."""

    project_id: str
    title: str = Field(..., min_length=1, max_length=500)
    description: str | None = None
    parent_id: str | None = None
    priority: str = "medium"
    complexity_points: int | None = Field(None, ge=1, le=100)
    tags: list[str] = Field(default_factory=list)


class TaskResponse(BaseModel):
    """Response model for task."""

    id: str
    project_id: str
    parent_id: str | None
    title: str
    description: str | None
    status: TaskStatus
    priority: Priority
    complexity_points: int | None
    actual_hours: float | None
    current_progress_percent: int
    assignee: ActorReferencePayload | None = None
    checkout: CheckoutPayload | None = None
    workflow_id: str | None
    current_state: str | None
    completion_criteria: list[str] = Field(default_factory=list)
    completion_ready: bool = False
    created_at: datetime
    updated_at: datetime
    last_activity_at: datetime | None = None
    last_transition_at: datetime | None = None
    linked_plan_count: int = 0
    linked_plans: list[JsonObject] = Field(default_factory=list)
    links: JsonObject = Field(default_factory=dict)
    next_steps: list[str] = Field(default_factory=list)


class TaskUpdate(BaseModel):
    """Request model for updating a task."""

    title: str | None = None
    description: str | None = None
    parent_id: str | None = None
    clear_parent: bool = False
    priority: str | None = None
    complexity_points: int | None = Field(None, ge=1, le=100)
    completion_criteria: list[str] | None = None
    clear_completion_criteria: bool = False


class TaskActionRequest(BaseModel):
    """Request model for task status actions."""

    reason: str | None = None
    updated_by: str | None = None
    actual_hours: float | None = None


class TaskCompletionActionResponse(BaseModel):
    """Response model for task completion side effects."""

    status: TaskCompletionStatus
    task_id: str
    newly_unblocked: list[TaskResponse] = Field(default_factory=list)


class TaskDependencyCreate(BaseModel):
    """Request model for creating a task dependency."""

    depends_on_id: str
    dependency_type: str = "blocks"


class TaskDependencyResponse(BaseModel):
    """Response model for task dependencies."""

    id: str
    task_id: str
    depends_on_id: str
    dependency_type: Literal["blocks", "relates_to", "duplicates"]
    created_at: datetime
    updated_at: datetime


class TaskDependencyDetailResponse(BaseModel):
    """Response model for dependency task details."""

    id: str
    title: str | None
    status: TaskStatus | None
    priority: Priority | None
    project_id: str | None
    project_name: str | None
    updated_at: datetime | None
    last_activity_at: datetime | None
    last_transition_at: datetime | None


class TaskDependencyGraphResponse(BaseModel):
    """Response model for task dependency graph."""

    task_id: str
    task_title: str | None
    project_id: str | None
    project_name: str | None
    status: TaskStatus | None
    priority: Priority | None
    updated_at: datetime | None
    last_activity_at: datetime | None
    last_transition_at: datetime | None
    blocked_by: list[str] = Field(default_factory=list)
    blocking: list[str] = Field(default_factory=list)
    blocked_by_details: list[TaskDependencyDetailResponse] = Field(default_factory=list)
    blocking_details: list[TaskDependencyDetailResponse] = Field(default_factory=list)


class TaskTreeNode(BaseModel):
    """Response model for a task tree node."""

    task: TaskResponse
    depth: int = 0
    children: list[TaskTreeNode] = Field(default_factory=list)


class TaskTreeResponse(BaseModel):
    """Response model for a task tree response."""

    project_id: str
    root_task_id: str | None = None
    nodes: list[TaskTreeNode] = Field(default_factory=list)


class StateTransitionResponse(BaseModel):
    """Response model for a state transition."""

    id: str
    entity_type: str
    entity_id: str
    from_state: str | None
    to_state: str
    timestamp: datetime
    triggered_by: str
    reason: str | None
    duration_in_state_seconds: int | None
    metadata: JsonObject = Field(default_factory=dict)


class TransitionTimelineResponse(BaseModel):
    """Response model for a transition timeline."""

    entity_type: str
    entity_id: str
    kind: TransitionTimelineKind
    total_duration_seconds: int
    total_duration_hours: float
    average_state_duration_hours: float
    state_durations: dict[str, int]
    transitions: list[StateTransitionResponse] = Field(default_factory=list)


class RevisionChangeResponse(BaseModel):
    """Response model for a revision change."""

    field_name: str
    old_value: str | None
    new_value: str | None
    change_type: ChangeType


class RevisionDiffResponse(BaseModel):
    """Response model for a revision diff."""

    entity_type: str
    entity_id: str
    from_revision: int
    to_revision: int
    changes: list[RevisionChangeResponse] = Field(default_factory=list)
    intermediate_revisions: list[str] = Field(default_factory=list)


class RevisionEntryResponse(BaseModel):
    """Response model for a revision entry."""

    revision_id: str
    entity_type: str
    entity_id: str
    revision_number: int
    parent_revision_id: str | None
    content: JsonObject
    content_hash: str
    changes: list[RevisionChangeResponse] = Field(default_factory=list)
    change_type: ChangeType
    created_at: datetime
    created_by: str | None
    message: str | None
    metadata: dict[str, str] = Field(default_factory=dict)


class RevisionHistoryPageResponse(BaseModel):
    """Response model for paginated revision history."""

    items: list[RevisionEntryResponse] = Field(default_factory=list)
    page: JsonObject = Field(default_factory=dict)


class LinkedEntitySummaryResponse(BaseModel):
    """Response model for linked entity summary."""

    id: str
    entity_type: str
    name: str | None
    status: str | None
    updated_at: datetime | None


class RevisionHistoryBundleResponse(BaseModel):
    """Response model for revision history bundles."""

    entity_type: str
    entity_id: str
    generated_at: datetime
    history: RevisionHistoryPageResponse
    linked: dict[str, list[LinkedEntitySummaryResponse]] = Field(default_factory=dict)
    linked_history: dict[str, dict[str, RevisionHistoryPageResponse]] = Field(
        default_factory=dict
    )


class TaskDuplicateMerge(BaseModel):
    """Request model for merging duplicate tasks."""

    primary_task_id: str
    duplicate_task_ids: list[str] = Field(default_factory=list)
    cancel_duplicates: bool = True


class TaskDuplicateMergePreview(BaseModel):
    """Request model for previewing duplicate task merges."""

    primary_task_id: str
    duplicate_task_ids: list[str] = Field(default_factory=list)


class DuplicateMergeConflictResponse(BaseModel):
    """Response model for duplicate merge conflicts."""

    field: str
    primary_value: JsonValue
    duplicate_value: JsonValue
    duplicate_task_id: str


class DuplicateMergePreviewItemResponse(BaseModel):
    """Response model for a duplicate task preview."""

    task: TaskResponse
    already_linked: bool
    conflicts: list[DuplicateMergeConflictResponse] = Field(default_factory=list)


class DuplicateMergePreviewResponse(BaseModel):
    """Response model for duplicate merge preview."""

    primary_task: TaskResponse
    duplicates: list[DuplicateMergePreviewItemResponse] = Field(default_factory=list)
    missing_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    can_merge: bool
    suggested_primary_id: str | None = None
    suggested_primary_reason: str | None = None
    links: JsonObject = Field(default_factory=dict)
    next_steps: list[str] = Field(default_factory=list)


# ============================================================
# Saved Search / Queue Models
# ============================================================


class SavedSearchRequest(BaseModel):
    """Request model for creating a saved search."""

    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    owner: str | None = None
    scope_type: SavedSearchScopeType = "global"
    scope_id: str | None = None
    filters: JsonObject = Field(default_factory=dict)
    sort_by: str | None = None
    sort_dir: SortDirection | None = None


class SavedSearchUpdateRequest(BaseModel):
    """Request model for updating a saved search."""

    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    owner: str | None = None
    scope_type: SavedSearchScopeType | None = None
    scope_id: str | None = None
    filters: JsonObject | None = None
    sort_by: str | None = None
    sort_dir: SortDirection | None = None


class SavedSearchResponse(BaseModel):
    """Response model for saved search."""

    id: str
    name: str
    description: str | None
    owner: ActorReferencePayload | None = None
    scope_type: SavedSearchScopeType
    scope_id: str | None
    filters: JsonObject
    sort_by: str | None
    sort_dir: SortDirection | None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None


class SavedSearchListResponse(BaseModel):
    """Response model for listing saved searches."""

    items: list[SavedSearchResponse] = Field(default_factory=list)
    total_count: int
    offset: int
    limit: int
    links: JsonObject = Field(default_factory=dict)
    next_steps: list[str] = Field(default_factory=list)
    params: JsonObject = Field(default_factory=dict)


class SavedSearchRunResponse(BaseModel):
    """Response model for saved search execution."""

    saved_search: SavedSearchResponse
    items: list[TaskResponse] = Field(default_factory=list)
    total_count: int
    offset: int
    limit: int
    links: JsonObject = Field(default_factory=dict)
    next_steps: list[str] = Field(default_factory=list)
    params: JsonObject = Field(default_factory=dict)


class QueuePresetResponse(BaseModel):
    """Response model for smart queue presets."""

    name: str
    description: str
    population: QueuePopulation
    total_count: int
    items: list[TaskResponse] = Field(default_factory=list)
    links: JsonObject = Field(default_factory=dict)
    next_steps: list[str] = Field(default_factory=list)
    params: JsonObject = Field(default_factory=dict)


# ============================================================
# Work Snapshot Models
# ============================================================


class WorkSnapshotDigestResponse(BaseModel):
    """Response model for snapshot digest."""

    since: datetime | None
    note: str | None
    tasks_created: int
    tasks_completed: int
    tasks_updated: int
    plans_created: int
    plans_updated: int
    test_runs: int
    failed_test_runs: int
    evidence_added: int


class WorkSnapshotTotalsResponse(BaseModel):
    """Response model for snapshot totals."""

    total_projects: int | None = None
    total_goals: int | None = None
    total_objectives: int | None = None
    total_tasks: int | None = None
    completed_tasks: int | None = None
    blocked_tasks: int | None = None
    overdue_tasks: int | None = None
    health_score: float | None = None
    risk_level: RiskLevel | None = None


class WorkSnapshotEvidenceResponse(BaseModel):
    """Response model for snapshot evidence counts."""

    total_count: int
    new_count: int


class EvidenceGateIndicatorResponse(BaseModel):
    """Response model for evidence gate indicators."""

    blocked: bool
    blocked_transitions: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class WorkSnapshotTaskHighlightResponse(BaseModel):
    """Response model for recent task highlight."""

    id: str
    title: str
    status: TaskStatus
    project_id: str
    updated_at: datetime
    evidence_gate: EvidenceGateIndicatorResponse | None = None


class WorkSnapshotRunHighlightResponse(BaseModel):
    """Response model for recent test run highlight."""

    id: str
    project_id: str | None
    success: bool
    finished_at: datetime
    command: str | None = None


class WorkSnapshotReviewPreviewResponse(BaseModel):
    """Response model for snapshot review history preview."""

    id: str
    reviewed_at: datetime
    reviewed_by: str | None
    note: str | None
    metadata: JsonObject


class WorkSnapshotResponse(BaseModel):
    """Response model for work snapshot."""

    scope_type: WorkSnapshotScopeType
    scope_id: str
    scope_name: str | None
    generated_at: datetime
    last_reviewed_at: datetime | None
    totals: WorkSnapshotTotalsResponse
    digest: WorkSnapshotDigestResponse
    evidence: WorkSnapshotEvidenceResponse
    retention: JsonObject | None
    lineage: JsonObject | None
    recent_tasks: list[WorkSnapshotTaskHighlightResponse] = Field(default_factory=list)
    recent_test_runs: list[WorkSnapshotRunHighlightResponse] = Field(
        default_factory=list
    )
    review_history_preview: list[WorkSnapshotReviewPreviewResponse] = Field(
        default_factory=list
    )
    links: JsonObject = Field(default_factory=dict)
    next_steps: list[str] = Field(default_factory=list)
    params: JsonObject = Field(default_factory=dict)


class WorkSnapshotReviewRequest(BaseModel):
    """Request model for marking a snapshot review."""

    reviewed_by: str | None = None
    note: str | None = None
    metadata: JsonObject = Field(default_factory=dict)


class WorkSnapshotReviewResponse(BaseModel):
    """Response model for snapshot review."""

    id: str
    scope_type: WorkSnapshotScopeType
    scope_id: str
    reviewed_at: datetime
    reviewed_by: str | None
    note: str | None
    metadata: JsonObject
    links: JsonObject = Field(default_factory=dict)
    next_steps: list[str] = Field(default_factory=list)
    params: JsonObject = Field(default_factory=dict)


# ============================================================
# Task Evidence Models
# ============================================================


class TaskEvidenceCreate(BaseModel):
    """Request model for creating task evidence."""

    evidence_type: str = Field(..., min_length=1)
    reference: str = Field(..., min_length=1)
    description: str | None = None
    metadata: JsonObject = Field(default_factory=dict)
    created_by: str | None = None


class TestRunSummaryResponse(BaseModel):
    """Summary model for test run evidence."""

    id: str
    success: bool
    exit_code: int | None
    duration_seconds: float | None
    started_at: datetime
    finished_at: datetime
    command: str | None = None
    stdout: str | None = None
    stderr: str | None = None


class TaskEvidenceResponse(BaseModel):
    """Response model for task evidence."""

    id: str
    task_id: str
    evidence_type: str
    reference: str
    description: str | None
    metadata: JsonObject
    created_by: str
    created_at: datetime
    test_run: TestRunSummaryResponse | None = None


# ============================================================
# Proof Bundle Models
# ============================================================


class ProofBundleSummaryResponse(BaseModel):
    """Response model for proof bundle summary."""

    evidence_total: int
    evidence_types: dict[str, int]
    test_runs: int
    successful_test_runs: int
    log_bytes_total: int
    artifact_bytes_total: int


# ============================================================
# Test Run Models
# ============================================================


class TestRunResponse(BaseModel):
    """Response model for test run records."""

    id: str
    server_id: str
    project_id: str | None
    success: bool
    exit_code: int | None
    duration_seconds: float | None
    started_at: datetime
    finished_at: datetime
    command: str | None = None
    runner: str | None = None
    plan_id: str | None = None
    task_ids: list[str] = Field(default_factory=list)
    stdout: str | None = None
    stderr: str | None = None
    logs: JsonObject | None = None
    artifacts: JsonObject | None = None


class TestRunCreate(BaseModel):
    """Request model for creating a test run record."""

    run_id: str | None = None
    server_id: str
    project_id: str | None = None
    success: bool
    exit_code: int | None = None
    duration_seconds: float | None = None
    started_at: datetime
    finished_at: datetime
    stdout: str | None = None
    stderr: str | None = None
    logs: JsonObject = Field(default_factory=dict)
    artifacts: JsonObject = Field(default_factory=dict)
    config: JsonObject = Field(default_factory=dict)
    command: str | None = None
    runner: str | None = None
    plan_id: str | None = None
    task_ids: list[str] = Field(default_factory=list)


class ProofBundleResponse(BaseModel):
    """Response model for task proof bundles."""

    task: TaskResponse
    generated_at: datetime
    summary: ProofBundleSummaryResponse
    evidence: list[TaskEvidenceResponse] = Field(default_factory=list)
    test_runs: list[TestRunResponse] = Field(default_factory=list)


class ProofBundleSearchItemResponse(BaseModel):
    """Response model for proof bundle search results."""

    task: TaskResponse
    summary: ProofBundleSummaryResponse
    last_evidence_at: datetime | None
    evidence: list[TaskEvidenceResponse] = Field(default_factory=list)
    test_runs: list[TestRunResponse] = Field(default_factory=list)


class ProofBundleSearchResponse(BaseModel):
    """Response model for proof bundle search."""

    items: list[ProofBundleSearchItemResponse] = Field(default_factory=list)
    total_count: int
    limit: int
    offset: int


class TestRunPruneResponse(BaseModel):
    """Response model for test run pruning."""

    class Scope(BaseModel):
        """Per-scope prune summary."""

        scope_type: RetentionSummaryScopeType
        scope_id: str
        policy_id: str | None = None
        max_log_bytes: int
        max_artifact_bytes: int
        max_age_days: int
        runs_scanned: int
        runs_pruned: int
        runs_logs_pruned: int
        runs_artifacts_pruned: int
        stdout_pruned: int
        stderr_pruned: int
        log_bytes_before: int
        log_bytes_after: int
        log_bytes_pruned: int
        artifact_bytes_before: int
        artifact_bytes_after: int
        artifact_bytes_pruned: int
        pruned_run_ids: list[str] = Field(default_factory=list)

    runs_scanned: int
    runs_pruned: int
    runs_logs_pruned: int
    runs_artifacts_pruned: int
    stdout_pruned: int
    stderr_pruned: int
    log_bytes_before: int
    log_bytes_after: int
    log_bytes_pruned: int
    artifact_bytes_before: int
    artifact_bytes_after: int
    artifact_bytes_pruned: int
    dry_run: bool
    pruned_run_ids: list[str] = Field(default_factory=list)
    scopes: list[Scope] = Field(default_factory=list)


class TestRunUsageItemResponse(BaseModel):
    """Response model for per-run storage usage."""

    run_id: str
    finished_at: datetime
    server_id: str
    project_id: str | None
    stdout_bytes: int
    stderr_bytes: int
    log_bytes: int
    log_total_bytes: int
    artifact_bytes: int
    artifact_recorded_bytes: int
    artifacts_missing: int
    total_bytes: int


class TestRunRetentionResponse(BaseModel):
    """Response model for test run retention usage."""

    class PolicyUsage(BaseModel):
        """Retention policy usage summary."""

        policy_id: str
        scope_type: RetentionPolicyScopeType
        scope_id: str
        max_log_bytes: int
        max_artifact_bytes: int
        max_age_days: int
        total_log_bytes: int
        total_artifact_bytes: int
        total_bytes: int
        run_count: int
        older_than_max_age: int
        project_ids: list[str] = Field(default_factory=list)

    class Alert(BaseModel):
        """Retention policy alert."""

        policy_id: str
        scope_type: RetentionPolicyScopeType
        scope_id: str
        metric: str
        current_value: int
        limit_value: int
        ratio: float
        severity: RetentionAlertSeverity
        details: JsonObject = Field(default_factory=dict)

    total_runs: int
    total_stdout_bytes: int
    total_stderr_bytes: int
    total_log_bytes: int
    total_log_bytes_combined: int
    total_artifact_bytes: int
    total_artifact_recorded_bytes: int
    total_bytes: int
    max_log_bytes: int
    max_artifact_bytes: int
    max_age_days: int
    sorted_by: RetentionUsageSort
    items: list[TestRunUsageItemResponse] = Field(default_factory=list)
    policies: list[PolicyUsage] = Field(default_factory=list)
    alerts: list[Alert] = Field(default_factory=list)


class TestRunRetentionPolicyResponse(BaseModel):
    """Response model for test run retention policies."""

    id: str
    scope_type: RetentionPolicyScopeType
    scope_id: str
    max_log_bytes: int
    max_artifact_bytes: int
    max_age_days: int
    notes: str | None = None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None


# ============================================================
# Checkout Models
# ============================================================


class CheckoutRequest(BaseModel):
    """Request model for checking out a task."""

    agent_session_id: str
    lease_seconds: int = Field(300, ge=60, le=3600)
    actor: str | None = None


class CheckoutResponse(BaseModel):
    """Response model for checkout operation."""

    task_id: str
    checkout: CheckoutPayload


# ============================================================
# Progress Models
# ============================================================


class ProgressUpdate(BaseModel):
    """Request model for progress update."""

    percent_complete: int = Field(..., ge=0, le=100)
    status_message: str
    updated_by: str
    metadata: JsonObject = Field(default_factory=dict)


class ProgressResponse(BaseModel):
    """Response model for progress update."""

    task_id: str
    percent_complete: int
    status_message: str
    updated_by: str
    timestamp: datetime


# ============================================================
# Workflow Models
# ============================================================


class WorkflowAssign(BaseModel):
    """Request model for assigning workflow."""

    workflow_name: str  # sdlc, agile, product_lifecycle
    initial_state: str


class WorkflowTransition(BaseModel):
    """Request model for workflow state transition."""

    to_state: str
    triggered_by: str
    reason: str | None = None
    approved_by: str | None = None


class WorkflowAlign(BaseModel):
    """Request model for workflow alignment."""

    entity_id: str | None = Field(None, description="Entity ID to align")
    entity_type: str = Field("task", description="task, goal, or objective")
    to_state: str | None = None
    triggered_by: str
    reason: str | None = None
    approved_by: str | None = None
    auto: bool = True
    dry_run: bool = False


class WorkflowTransitionResponse(BaseModel):
    """Response model for workflow transition."""

    entity_id: str
    from_state: str | None
    to_state: str
    triggered_by: str
    timestamp: datetime


class WorkflowAlignResponse(BaseModel):
    """Response model for workflow alignment."""

    entity_id: str
    from_state: str | None
    target_state: str
    applied_transitions: list[str] = Field(default_factory=list)
    remaining: list[str] = Field(default_factory=list)
    aligned: bool = False


# ============================================================
# Label Models
# ============================================================


class LabelCategoryCreate(BaseModel):
    """Request model for creating a label category."""

    name: str = Field(..., min_length=1, max_length=120)
    description: str | None = None
    is_exclusive: bool = False
    sort_order: int = 0


class LabelCategoryUpdate(BaseModel):
    """Request model for updating a label category."""

    name: str | None = Field(None, min_length=1, max_length=120)
    description: str | None = None
    is_exclusive: bool | None = None
    sort_order: int | None = None


class LabelCategoryResponse(BaseModel):
    """Response model for label category."""

    id: str
    name: str
    description: str | None
    is_exclusive: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None


class LabelCreate(BaseModel):
    """Request model for creating a label."""

    name: str = Field(..., min_length=1, max_length=120)
    description: str | None = None
    category_id: str | None = None
    color: str | None = None
    is_system: bool = False


class LabelUpdate(BaseModel):
    """Request model for updating a label."""

    name: str | None = Field(None, min_length=1, max_length=120)
    description: str | None = None
    category_id: str | None = None
    color: str | None = None
    is_system: bool | None = None


class LabelResponse(BaseModel):
    """Response model for label."""

    id: str
    name: str
    description: str | None
    category_id: str | None
    color: str | None
    is_system: bool
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None


class LabelAssignmentCreate(BaseModel):
    """Request model for assigning a label to an entity."""

    entity_type: str
    entity_id: str
    label_id: str
    applied_by: str | None = None


class LabelAssignmentResponse(BaseModel):
    """Response model for label assignment."""

    id: str
    entity_type: str
    entity_id: str
    label_id: str
    applied_by: str | None
    applied_at: datetime


class LabelGateRuleCreate(BaseModel):
    """Request model for creating a label gate rule."""

    workflow_id: str
    entity_type: str
    from_state: str
    to_state: str
    rule_type: str
    label_id: str | None = None
    category_id: str | None = None
    message: str | None = None


class LabelGateRuleResponse(BaseModel):
    """Response model for label gate rule."""

    id: str
    workflow_id: str
    entity_type: str
    from_state: str
    to_state: str
    rule_type: LabelGateRuleType
    label_id: str | None
    category_id: str | None
    message: str | None
    created_at: datetime


# ============================================================
# Custom Field Models
# ============================================================


class CustomFieldDefinitionCreate(BaseModel):
    """Request model for creating a custom field definition."""

    name: str = Field(..., min_length=1, max_length=120)
    entity_type: str = Field(..., min_length=1, max_length=60)
    field_type: str = Field(..., min_length=1, max_length=60)
    description: str | None = None
    options: list[str] = Field(default_factory=list)
    is_required: bool = False


class CustomFieldDefinitionUpdate(BaseModel):
    """Request model for updating a custom field definition."""

    name: str | None = Field(None, min_length=1, max_length=120)
    field_type: str | None = Field(None, min_length=1, max_length=60)
    description: str | None = None
    options: list[str] | None = None
    is_required: bool | None = None


class CustomFieldDefinitionResponse(BaseModel):
    """Response model for custom field definitions."""

    id: str
    name: str
    entity_type: str
    field_type: CustomFieldType
    description: str | None
    options: list[str]
    is_required: bool
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None


class CustomFieldValueCreate(BaseModel):
    """Request model for setting a custom field value."""

    entity_type: str
    entity_id: str
    value: JsonValue
    created_by: str | None = None
    source: str | None = None
    metadata: JsonObject = Field(default_factory=dict)


class CustomFieldValueResponse(BaseModel):
    """Response model for custom field values."""

    id: str
    field_id: str
    entity_type: str
    entity_id: str
    value: JsonValue
    created_by: str | None
    source: str | None
    metadata: JsonObject
    created_at: datetime


class CustomFieldValueItemResponse(BaseModel):
    """Response model combining definition + value."""

    definition: CustomFieldDefinitionResponse | None
    value: CustomFieldValueResponse


class CustomFieldValuesResponse(BaseModel):
    """Response model for custom field value lists."""

    items: list[CustomFieldValueItemResponse] = Field(default_factory=list)
    total_count: int = 0
    offset: int = 0
    limit: int = 0


# ============================================================
# Comment and Watcher Models
# ============================================================


class CommentCreate(BaseModel):
    """Request model for creating a comment."""

    entity_type: str
    entity_id: str
    body: str = Field(..., min_length=1)
    created_by: str
    mentions: list[str] = Field(default_factory=list)
    metadata: JsonObject = Field(default_factory=dict)
    watch: bool = False


class CommentResponse(BaseModel):
    """Response model for a comment."""

    id: str
    entity_type: str
    entity_id: str
    body: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None
    metadata: JsonObject
    mentions: list[str] = Field(default_factory=list)


class CommentListResponse(BaseModel):
    """Response model for comment lists."""

    items: list[CommentResponse] = Field(default_factory=list)
    total_count: int = 0
    offset: int = 0
    limit: int = 0
    links: JsonObject = Field(default_factory=dict)
    next_steps: list[str] = Field(default_factory=list)
    params: JsonObject = Field(default_factory=dict)


class WatcherCreate(BaseModel):
    """Request model for adding a watcher."""

    entity_type: str
    entity_id: str
    watcher: str


class WatcherResponse(BaseModel):
    """Response model for watchers."""

    id: str
    entity_type: str
    entity_id: str
    watcher: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None


class WatcherListResponse(BaseModel):
    """Response model for watcher lists."""

    items: list[WatcherResponse] = Field(default_factory=list)
    total_count: int = 0
    offset: int = 0
    limit: int = 0
    links: JsonObject = Field(default_factory=dict)
    next_steps: list[str] = Field(default_factory=list)
    params: JsonObject = Field(default_factory=dict)


# ============================================================
# Automation Rule Models
# ============================================================


class AutomationRuleCreate(BaseModel):
    """Request model for creating an automation rule."""

    name: str
    event_pattern: str
    action_type: str = Field(
        ...,
        description=(
            "Canonical automation action type. Allowed values: "
            + ", ".join(_AUTOMATION_ACTION_TYPE_VALUES)
        ),
        json_schema_extra={"enum": _AUTOMATION_ACTION_TYPE_VALUES},
    )
    action_payload: JsonObject = Field(default_factory=dict)
    description: str | None = None
    aggregate_type: str | None = None
    aggregate_id: str | None = None
    enabled: bool = True
    cooldown_seconds: float = 0.0


class AutomationRuleUpdate(BaseModel):
    """Request model for updating an automation rule."""

    name: str | None = None
    event_pattern: str | None = None
    action_type: str | None = Field(
        default=None,
        description=(
            "Canonical automation action type. Allowed values: "
            + ", ".join(_AUTOMATION_ACTION_TYPE_VALUES)
        ),
        json_schema_extra={"enum": _AUTOMATION_ACTION_TYPE_VALUES},
    )
    action_payload: JsonObject | None = None
    description: str | None = None
    aggregate_type: str | None = None
    aggregate_id: str | None = None
    enabled: bool | None = None
    cooldown_seconds: float | None = None


class AutomationRuleResponse(BaseModel):
    """Response model for an automation rule."""

    id: str
    name: str
    event_pattern: str
    action_type: AutomationActionType = Field(
        ...,
        description=(
            "Canonical automation action type. Allowed values: "
            + ", ".join(_AUTOMATION_ACTION_TYPE_VALUES)
        ),
        json_schema_extra={"enum": _AUTOMATION_ACTION_TYPE_VALUES},
    )
    action_payload: JsonObject
    description: str | None = None
    aggregate_type: str | None = None
    aggregate_id: str | None = None
    enabled: bool
    cooldown_seconds: float
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None


class AutomationRuleListResponse(BaseModel):
    """Response model for automation rule lists."""

    items: list[AutomationRuleResponse] = Field(default_factory=list)
    total_count: int = 0
    offset: int = 0
    limit: int = 0
    links: JsonObject = Field(default_factory=dict)
    next_steps: list[str] = Field(default_factory=list)
    params: JsonObject = Field(default_factory=dict)


class AutomationRuleRunRequest(BaseModel):
    """Request model for executing automation rules for an event."""

    event_id: str
    dry_run: bool = False
    rule_id: str | None = None


class AutomationRuleRunResponse(BaseModel):
    """Response model for automation rule execution."""

    id: str
    rule_id: str
    event_id: str | None = None
    status: AutomationRunStatus
    started_at: datetime
    completed_at: datetime | None = None
    error: str | None = None
    output: JsonObject = Field(default_factory=dict)


class AutomationRuleRunListResponse(BaseModel):
    """Response model for automation run lists."""

    items: list[AutomationRuleRunResponse] = Field(default_factory=list)
    total_count: int = 0
    offset: int = 0
    limit: int = 0
    links: JsonObject = Field(default_factory=dict)
    next_steps: list[str] = Field(default_factory=list)
    params: JsonObject = Field(default_factory=dict)


class EvidenceGateRuleCreate(BaseModel):
    """Request model for creating an evidence gate rule."""

    workflow_id: str
    entity_type: str
    from_state: str
    to_state: str
    evidence_type: str
    min_count: int = Field(1, ge=1)
    require_success: bool = False
    message: str | None = None


class EvidenceGateRuleResponse(BaseModel):
    """Response model for evidence gate rule."""

    id: str
    workflow_id: str
    entity_type: str
    from_state: str
    to_state: str
    evidence_type: str
    min_count: int
    require_success: bool
    message: str | None
    created_at: datetime


# ============================================================
# Agent Loop Models
# ============================================================


class AgentLoopSummaryResponse(BaseModel):
    """Summary model for agent loops."""

    id: str
    agent: str
    status: SessionStatus
    iterations: int
    max_iterations: int
    max_runtime_seconds: int
    stop_reason: str | None
    created_at: datetime
    updated_at: datetime
    ended_at: datetime | None
    last_prompt: str | None
    last_response_summary: str | None


class AgentLoopListResponse(BaseModel):
    """Response model for listing agent loops."""

    items: list[AgentLoopSummaryResponse] = Field(default_factory=list)
    total_count: int = 0
    offset: int = 0
    limit: int = 0
    links: JsonObject = Field(default_factory=dict)
    next_steps: list[str] = Field(default_factory=list)
    params: JsonObject = Field(default_factory=dict)


class AgentLoopMessageResponse(BaseModel):
    """Response model for agent loop messages."""

    id: str
    session_id: str
    role: str = Field(
        ...,
        description=(
            "Open transcript role. Preferred built-ins are `system`, `user`, "
            "`assistant`, and `tool`, but custom roles remain valid for planners, "
            "reviewers, plugins, and other extension-mediated transcripts."
        ),
    )
    content: str
    tokens: int | None
    cost_usd: str | None
    timestamp: datetime
    metadata: JsonObject


class AgentLoopMessagesResponse(BaseModel):
    """Response model for agent loop messages."""

    items: list[AgentLoopMessageResponse] = Field(default_factory=list)
    total_count: int = 0
    offset: int = 0
    limit: int = 0
    links: JsonObject = Field(default_factory=dict)
    next_steps: list[str] = Field(default_factory=list)
    params: JsonObject = Field(default_factory=dict)


# ============================================================
# Common Models
# ============================================================


class HealthResponse(BaseModel):
    """Response model for health check."""

    status: HealthStatus
    database: str
    backend: str
    schema_version: int
    schema_name: str
    uptime_seconds: float


class ErrorResponse(BaseModel):
    """Response model for errors."""

    error: str
    detail: str | None = None
    code: str | None = None


TaskTreeNode.model_rebuild()
