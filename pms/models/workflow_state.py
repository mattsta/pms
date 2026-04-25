"""Workflow state machine models for configurable lifecycle management."""

from __future__ import annotations

from dataclasses import dataclass, field

from pms.models.base import BaseModel
from pms.models.json_types import JsonObject, ModelObject


@dataclass
class WorkflowState(BaseModel):
    """
    A single state in a workflow.

    Represents a stage in an entity's lifecycle with:
    - Display information (name, color, icon)
    - Terminal flag (is this an end state?)
    - Metadata schema for state-specific data
    """

    workflow_id: str = ""
    state_name: str = ""  # Internal identifier (e.g., "implementing")
    display_name: str = ""  # User-facing name (e.g., "Implementing")
    description: str | None = None
    color: str | None = None  # Hex color for UI (e.g., "#purple")
    icon: str | None = None  # Icon identifier
    is_terminal: bool = False
    sort_order: int = 0
    metadata_schema: JsonObject | None = None  # JSON schema for validation

    def to_dict(self) -> ModelObject:
        """Convert to dictionary."""
        data = super().to_dict()
        data["is_terminal"] = self.is_terminal
        return data


@dataclass
class WorkflowTransition(BaseModel):
    """
    An allowed transition between two states.

    Defines rules for moving from one state to another:
    - Approval requirements
    - Validation rules
    - Auto-transition conditions
    """

    workflow_id: str = ""
    from_state: str = ""
    to_state: str = ""
    requires_approval: bool = False
    approval_roles: list[str] = field(default_factory=list)
    validation_rules: JsonObject = field(default_factory=dict)
    auto_transition: bool = False  # Auto-transition when conditions met
    condition_expr: str | None = None  # Expression for auto-transition
    metadata: JsonObject = field(default_factory=dict)


@dataclass
class WorkflowDefinition(BaseModel):
    """
    Complete workflow definition.

    A workflow defines:
    - All possible states
    - Allowed transitions between states
    - Initial and terminal states
    - Entity type it applies to
    """

    name: str = ""
    description: str | None = None
    entity_type: str = "task"  # task, project, product, workflow, etc.
    initial_state: str = "todo"
    terminal_states: list[str] = field(default_factory=list)
    is_default: bool = False  # Default workflow for entity type

    # States and transitions (loaded separately or embedded)
    states: list[WorkflowState] = field(default_factory=list)
    transitions: list[WorkflowTransition] = field(default_factory=list)

    metadata: JsonObject = field(default_factory=dict)

    def get_state(self, state_name: str) -> WorkflowState | None:
        """Get a state by name."""
        for state in self.states:
            if state.state_name == state_name:
                return state
        return None

    def is_valid_transition(self, from_state: str, to_state: str) -> bool:
        """Check if transition is defined in workflow."""
        for transition in self.transitions:
            if transition.to_state != to_state:
                continue
            if transition.from_state in (from_state, "*"):
                return True
        return False

    def get_available_transitions(self, from_state: str) -> list[WorkflowTransition]:
        """Get all valid transitions from a given state."""
        return [t for t in self.transitions if t.from_state in (from_state, "*")]

    def is_terminal_state(self, state_name: str) -> bool:
        """Check if a state is terminal."""
        return state_name in self.terminal_states


# ============================================================
# PREDEFINED WORKFLOWS
# ============================================================


def create_sdlc_workflow() -> WorkflowDefinition:
    """
    Software Development Lifecycle workflow.

    Complete pipeline from concept to production with quality gates.
    """
    return WorkflowDefinition(
        id="wf_sdlc",
        name="software_development_lifecycle",
        description="Complete SDLC: concept → idea → planning → implementation → testing → production",
        entity_type="task",
        initial_state="concept",
        terminal_states=["production", "cancelled"],
        is_default=True,
        states=[
            WorkflowState(
                id="wfs_concept",
                workflow_id="wf_sdlc",
                state_name="concept",
                display_name="Concept",
                description="Initial idea or concept phase",
                color="#6B7280",
                sort_order=1,
            ),
            WorkflowState(
                id="wfs_idea",
                workflow_id="wf_sdlc",
                state_name="idea",
                display_name="Idea",
                description="Idea being fleshed out",
                color="#3B82F6",
                sort_order=2,
            ),
            WorkflowState(
                id="wfs_planning",
                workflow_id="wf_sdlc",
                state_name="planning",
                display_name="Planning",
                description="Planning and design phase",
                color="#F59E0B",
                sort_order=3,
            ),
            WorkflowState(
                id="wfs_detailed_plan",
                workflow_id="wf_sdlc",
                state_name="detailed_plan",
                display_name="Detailed Plan",
                description="Concrete implementation plan",
                color="#F97316",
                sort_order=4,
            ),
            WorkflowState(
                id="wfs_implementing",
                workflow_id="wf_sdlc",
                state_name="implementing",
                display_name="Implementing",
                description="Active development",
                color="#8B5CF6",
                sort_order=5,
            ),
            WorkflowState(
                id="wfs_code_review",
                workflow_id="wf_sdlc",
                state_name="code_review",
                display_name="Code Review",
                description="Code review in progress",
                color="#14B8A6",
                sort_order=6,
            ),
            WorkflowState(
                id="wfs_unit_testing",
                workflow_id="wf_sdlc",
                state_name="unit_testing",
                display_name="Unit Testing",
                description="Unit tests being written/run",
                color="#10B981",
                sort_order=7,
            ),
            WorkflowState(
                id="wfs_integration_testing",
                workflow_id="wf_sdlc",
                state_name="integration_testing",
                display_name="Integration Testing",
                description="Integration tests in progress",
                color="#059669",
                sort_order=8,
            ),
            WorkflowState(
                id="wfs_staging",
                workflow_id="wf_sdlc",
                state_name="staging",
                display_name="Staging",
                description="Deployed to staging environment",
                color="#0EA5E9",
                sort_order=9,
            ),
            WorkflowState(
                id="wfs_confirmation",
                workflow_id="wf_sdlc",
                state_name="confirmation",
                display_name="Confirmation",
                description="Awaiting final confirmation",
                color="#F97316",
                sort_order=10,
            ),
            WorkflowState(
                id="wfs_production",
                workflow_id="wf_sdlc",
                state_name="production",
                display_name="Production",
                description="Deployed to production",
                color="#10B981",
                is_terminal=True,
                sort_order=11,
            ),
            WorkflowState(
                id="wfs_monitoring",
                workflow_id="wf_sdlc",
                state_name="monitoring",
                display_name="Monitoring",
                description="Production monitoring phase",
                color="#06B6D4",
                sort_order=12,
            ),
            WorkflowState(
                id="wfs_cancelled",
                workflow_id="wf_sdlc",
                state_name="cancelled",
                display_name="Cancelled",
                description="Work cancelled",
                color="#EF4444",
                is_terminal=True,
                sort_order=99,
            ),
        ],
        transitions=[
            WorkflowTransition(
                id="wft_1", workflow_id="wf_sdlc", from_state="concept", to_state="idea"
            ),
            WorkflowTransition(
                id="wft_2",
                workflow_id="wf_sdlc",
                from_state="idea",
                to_state="planning",
            ),
            WorkflowTransition(
                id="wft_3",
                workflow_id="wf_sdlc",
                from_state="planning",
                to_state="detailed_plan",
            ),
            WorkflowTransition(
                id="wft_4",
                workflow_id="wf_sdlc",
                from_state="detailed_plan",
                to_state="implementing",
            ),
            WorkflowTransition(
                id="wft_5",
                workflow_id="wf_sdlc",
                from_state="implementing",
                to_state="code_review",
            ),
            WorkflowTransition(
                id="wft_6",
                workflow_id="wf_sdlc",
                from_state="code_review",
                to_state="implementing",
            ),  # Back for changes
            WorkflowTransition(
                id="wft_7",
                workflow_id="wf_sdlc",
                from_state="code_review",
                to_state="unit_testing",
            ),
            WorkflowTransition(
                id="wft_8",
                workflow_id="wf_sdlc",
                from_state="unit_testing",
                to_state="integration_testing",
            ),
            WorkflowTransition(
                id="wft_9",
                workflow_id="wf_sdlc",
                from_state="integration_testing",
                to_state="staging",
            ),
            WorkflowTransition(
                id="wft_10",
                workflow_id="wf_sdlc",
                from_state="staging",
                to_state="confirmation",
            ),
            WorkflowTransition(
                id="wft_11",
                workflow_id="wf_sdlc",
                from_state="confirmation",
                to_state="production",
                requires_approval=True,
            ),
            WorkflowTransition(
                id="wft_12",
                workflow_id="wf_sdlc",
                from_state="production",
                to_state="monitoring",
            ),
            # Allow cancellation from any state
            WorkflowTransition(
                id="wft_cancel",
                workflow_id="wf_sdlc",
                from_state="*",
                to_state="cancelled",
            ),
        ],
    )


def get_workflow_registry() -> dict[str, WorkflowDefinition]:
    """Return the built-in workflow registry keyed by name."""
    return {
        "sdlc": create_sdlc_workflow(),
        "agile": create_agile_workflow(),
        "product_lifecycle": create_product_lifecycle_workflow(),
    }


def get_workflow_by_id(workflow_id: str) -> WorkflowDefinition | None:
    """Lookup a workflow definition by ID."""
    for workflow in get_workflow_registry().values():
        if workflow.id == workflow_id:
            return workflow
    return None


def create_agile_workflow() -> WorkflowDefinition:
    """Agile/Scrum sprint workflow."""
    return WorkflowDefinition(
        id="wf_agile",
        name="agile_sprint",
        description="Agile sprint workflow: backlog → sprint → in progress → review → done",
        entity_type="task",
        initial_state="backlog",
        terminal_states=["done", "cancelled"],
        states=[
            WorkflowState(
                id="wfs_backlog",
                workflow_id="wf_agile",
                state_name="backlog",
                display_name="Backlog",
                color="#6B7280",
                sort_order=1,
            ),
            WorkflowState(
                id="wfs_sprint",
                workflow_id="wf_agile",
                state_name="sprint_planned",
                display_name="Sprint Planned",
                color="#3B82F6",
                sort_order=2,
            ),
            WorkflowState(
                id="wfs_progress",
                workflow_id="wf_agile",
                state_name="in_progress",
                display_name="In Progress",
                color="#8B5CF6",
                sort_order=3,
            ),
            WorkflowState(
                id="wfs_review",
                workflow_id="wf_agile",
                state_name="in_review",
                display_name="In Review",
                color="#14B8A6",
                sort_order=4,
            ),
            WorkflowState(
                id="wfs_blocked",
                workflow_id="wf_agile",
                state_name="blocked",
                display_name="Blocked",
                color="#EF4444",
                sort_order=5,
            ),
            WorkflowState(
                id="wfs_done",
                workflow_id="wf_agile",
                state_name="done",
                display_name="Done",
                color="#10B981",
                is_terminal=True,
                sort_order=6,
            ),
        ],
        transitions=[
            WorkflowTransition(
                id="wft_a1",
                workflow_id="wf_agile",
                from_state="backlog",
                to_state="sprint_planned",
            ),
            WorkflowTransition(
                id="wft_a2",
                workflow_id="wf_agile",
                from_state="sprint_planned",
                to_state="in_progress",
            ),
            WorkflowTransition(
                id="wft_a3",
                workflow_id="wf_agile",
                from_state="in_progress",
                to_state="in_review",
            ),
            WorkflowTransition(
                id="wft_a4",
                workflow_id="wf_agile",
                from_state="in_progress",
                to_state="blocked",
            ),
            WorkflowTransition(
                id="wft_a5",
                workflow_id="wf_agile",
                from_state="blocked",
                to_state="in_progress",
            ),
            WorkflowTransition(
                id="wft_a6",
                workflow_id="wf_agile",
                from_state="in_review",
                to_state="in_progress",
            ),
            WorkflowTransition(
                id="wft_a7",
                workflow_id="wf_agile",
                from_state="in_review",
                to_state="done",
            ),
        ],
    )


def create_product_lifecycle_workflow() -> WorkflowDefinition:
    """Product lifecycle management workflow."""
    return WorkflowDefinition(
        id="wf_product_lifecycle",
        name="product_lifecycle",
        description="Product maturity stages: concept → planning → alpha → beta → GA → mature → EOL",
        entity_type="product",
        initial_state="concept",
        terminal_states=["eol"],
        states=[
            WorkflowState(
                id="wfs_p_concept",
                workflow_id="wf_product_lifecycle",
                state_name="concept",
                display_name="Concept",
                color="#6B7280",
                sort_order=1,
            ),
            WorkflowState(
                id="wfs_p_planning",
                workflow_id="wf_product_lifecycle",
                state_name="planning",
                display_name="Planning",
                color="#F59E0B",
                sort_order=2,
            ),
            WorkflowState(
                id="wfs_p_alpha",
                workflow_id="wf_product_lifecycle",
                state_name="alpha",
                display_name="Alpha",
                color="#8B5CF6",
                sort_order=3,
            ),
            WorkflowState(
                id="wfs_p_beta",
                workflow_id="wf_product_lifecycle",
                state_name="beta",
                display_name="Beta",
                color="#3B82F6",
                sort_order=4,
            ),
            WorkflowState(
                id="wfs_p_rc",
                workflow_id="wf_product_lifecycle",
                state_name="rc",
                display_name="Release Candidate",
                color="#0EA5E9",
                sort_order=5,
            ),
            WorkflowState(
                id="wfs_p_ga",
                workflow_id="wf_product_lifecycle",
                state_name="ga",
                display_name="General Availability",
                color="#10B981",
                sort_order=6,
            ),
            WorkflowState(
                id="wfs_p_mature",
                workflow_id="wf_product_lifecycle",
                state_name="mature",
                display_name="Mature",
                color="#059669",
                sort_order=7,
            ),
            WorkflowState(
                id="wfs_p_maintenance",
                workflow_id="wf_product_lifecycle",
                state_name="maintenance",
                display_name="Maintenance",
                color="#F59E0B",
                sort_order=8,
            ),
            WorkflowState(
                id="wfs_p_eol",
                workflow_id="wf_product_lifecycle",
                state_name="eol",
                display_name="End of Life",
                color="#EF4444",
                is_terminal=True,
                sort_order=9,
            ),
        ],
        transitions=[
            WorkflowTransition(
                id="wft_p1",
                workflow_id="wf_product_lifecycle",
                from_state="concept",
                to_state="planning",
            ),
            WorkflowTransition(
                id="wft_p2",
                workflow_id="wf_product_lifecycle",
                from_state="planning",
                to_state="alpha",
            ),
            WorkflowTransition(
                id="wft_p3",
                workflow_id="wf_product_lifecycle",
                from_state="alpha",
                to_state="beta",
            ),
            WorkflowTransition(
                id="wft_p4",
                workflow_id="wf_product_lifecycle",
                from_state="beta",
                to_state="rc",
            ),
            WorkflowTransition(
                id="wft_p5",
                workflow_id="wf_product_lifecycle",
                from_state="rc",
                to_state="ga",
                requires_approval=True,
            ),
            WorkflowTransition(
                id="wft_p6",
                workflow_id="wf_product_lifecycle",
                from_state="ga",
                to_state="mature",
            ),
            WorkflowTransition(
                id="wft_p7",
                workflow_id="wf_product_lifecycle",
                from_state="mature",
                to_state="maintenance",
            ),
            WorkflowTransition(
                id="wft_p8",
                workflow_id="wf_product_lifecycle",
                from_state="maintenance",
                to_state="eol",
                requires_approval=True,
            ),
        ],
    )
