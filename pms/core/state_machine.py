"""State machine engine for workflow management."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from pms.models.state_transition import StateTransition
from pms.models.workflow_state import WorkflowDefinition

if TYPE_CHECKING:
    from pms.repositories.state_transition_repository import StateTransitionRepository

logger = logging.getLogger(__name__)


class StateMachine:
    """
    Flexible state machine engine for workflow management.

    Manages state transitions with:
    - Validation against workflow definitions
    - Approval gates
    - Auto-transitions
    - State-specific metadata validation
    - Complete audit trail
    """

    def __init__(
        self,
        workflow: WorkflowDefinition,
        transition_repo: StateTransitionRepository,
    ):
        """
        Initialize state machine.

        Args:
            workflow: Workflow definition
            transition_repo: Repository for recording transitions
        """
        self.workflow = workflow
        self.transition_repo = transition_repo
        self.states = {s.state_name: s for s in workflow.states}

    def can_transition(
        self,
        from_state: str,
        to_state: str,
        context: dict[str, Any] | None = None,
    ) -> tuple[bool, str | None]:
        """
        Check if transition is allowed.

        Args:
            from_state: Current state
            to_state: Desired state
            context: Additional context for validation

        Returns:
            (is_allowed, error_message)
        """
        # Check if states exist
        if to_state not in self.states:
            return False, f"Unknown state: {to_state}"

        # Check if transition is defined
        if not self.workflow.is_valid_transition(from_state, to_state):
            return False, f"Invalid transition: {from_state} → {to_state}"

        # Check transition rules
        transitions = self.workflow.get_available_transitions(from_state)
        for trans in transitions:
            if trans.to_state == to_state:
                # Check approval requirements
                if trans.requires_approval and (
                    not context or not context.get("approved_by")
                ):
                    return False, "Transition requires approval"

                # Check validation rules
                if trans.validation_rules:
                    is_valid, error = self._validate_rules(
                        trans.validation_rules, context or {}
                    )
                    if not is_valid:
                        return False, error

                return True, None

        return False, f"No transition found: {from_state} → {to_state}"

    async def transition(
        self,
        entity_id: str,
        from_state: str,
        to_state: str,
        triggered_by: str,
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
        approved_by: str | None = None,
    ) -> StateTransition:
        """
        Execute state transition with validation.

        Args:
            entity_id: ID of entity transitioning
            from_state: Current state
            to_state: New state
            triggered_by: Who/what triggered transition
            reason: Human-readable explanation
            metadata: Additional context
            approved_by: Approver if required

        Returns:
            Created StateTransition

        Raises:
            ValueError: If transition is not allowed
        """
        # Validate transition
        context = dict(metadata) if metadata else {}
        if approved_by:
            context["approved_by"] = approved_by
        if "transition_kind" not in context:
            context["transition_kind"] = "workflow"

        can_transition, error = self.can_transition(from_state, to_state, context)
        if not can_transition:
            raise ValueError(f"Cannot transition: {error}")

        # Record transition
        transition = await self.transition_repo.record_transition(
            entity_type=self.workflow.entity_type,
            entity_id=entity_id,
            from_state=from_state,
            to_state=to_state,
            triggered_by=triggered_by,
            reason=reason,
            metadata=context,
        )

        logger.info(
            f"{self.workflow.entity_type} {entity_id}: {from_state} → {to_state} "
            f"(by {triggered_by})"
        )

        return transition

    def get_available_transitions(
        self,
        current_state: str,
        context: dict[str, Any] | None = None,
    ) -> list[str]:
        """
        Get all valid next states from current state.

        Args:
            current_state: Current state
            context: Context for validation

        Returns:
            List of available next state names
        """
        transitions = self.workflow.get_available_transitions(current_state)
        available = []

        for trans in transitions:
            can_go, _ = self.can_transition(current_state, trans.to_state, context)
            if can_go:
                available.append(trans.to_state)

        return available

    def is_terminal_state(self, state: str) -> bool:
        """Check if a state is terminal."""
        return self.workflow.is_terminal_state(state)

    def _validate_rules(
        self,
        rules: dict[str, Any],
        context: dict[str, Any],
    ) -> tuple[bool, str | None]:
        """
        Validate context against rules.

        Args:
            rules: Validation rules
            context: Context to validate

        Returns:
            (is_valid, error_message)
        """
        # Simple validation - can be enhanced with expression parsing
        for key, expected_value in rules.items():
            if key not in context:
                return False, f"Missing required field: {key}"
            if context[key] != expected_value:
                return False, f"Validation failed for {key}"

        return True, None


class StateMachineRegistry:
    """Registry of available workflows."""

    def __init__(self) -> None:
        self._workflows: dict[str, WorkflowDefinition] = {}
        self._default_workflows: dict[str, WorkflowDefinition] = {}

    def register(self, workflow: WorkflowDefinition) -> None:
        """Register a workflow."""
        self._workflows[workflow.name] = workflow

        if workflow.is_default:
            self._default_workflows[workflow.entity_type] = workflow

    def get_workflow(self, name: str) -> WorkflowDefinition | None:
        """Get workflow by name."""
        return self._workflows.get(name)

    def get_default_workflow(self, entity_type: str) -> WorkflowDefinition | None:
        """Get default workflow for entity type."""
        return self._default_workflows.get(entity_type)

    def list_workflows(
        self, entity_type: str | None = None
    ) -> list[WorkflowDefinition]:
        """List all workflows, optionally filtered by entity type."""
        workflows = list(self._workflows.values())

        if entity_type:
            workflows = [w for w in workflows if w.entity_type == entity_type]

        return workflows
