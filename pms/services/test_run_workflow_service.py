"""Service for linking test run outcomes to workflow transitions."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field, replace

from pms.core.events import EventStore, EventType
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.core.state_machine import StateMachine
from pms.models.workflow_state import get_workflow_by_id
from pms.repositories.state_transition_repository import StateTransitionRepository
from pms.repositories.task_repository import TaskRepository
from pms.services.evidence_gate_service import EvidenceGateService
from pms.services.label_service import LabelService


@dataclass(frozen=True)
class TestRunWorkflowTransition:
    """Configuration for workflow transitions driven by test runs."""

    __test__ = False

    on_success_state: str | None = None
    on_failure_state: str | None = None
    triggered_by: str = "test_runner"
    reason: str | None = None

    def target_state(self, success: bool) -> str | None:
        """Get the target state based on test success."""
        return self.on_success_state if success else self.on_failure_state


@dataclass
class TestRunWorkflowResult:
    """Summary of workflow transitions driven by a test run."""

    __test__ = False

    tasks_considered: int = 0
    tasks_transitioned: int = 0
    tasks_skipped: int = 0
    skipped_reasons: dict[str, int] = field(default_factory=dict)

    def record_skip(self, reason: str) -> None:
        """Record a skipped transition with a reason."""
        self.tasks_skipped += 1
        self.skipped_reasons[reason] = self.skipped_reasons.get(reason, 0) + 1


class TestRunWorkflowService:
    """Apply workflow transitions based on test run outcomes."""

    __test__ = False

    def __init__(self, db, metrics: MetricsCollector) -> None:
        self.db = db
        self.metrics = metrics
        event_store = EventStore(db)
        revision_store = RevisionStore(db)

        self._task_repo = TaskRepository(db, event_store, revision_store, metrics)
        self._state_repo = StateTransitionRepository(db)
        self._label_service = LabelService(db, metrics)
        self._evidence_gate_service = EvidenceGateService(db, metrics)

    async def apply(
        self,
        task_ids: Iterable[str],
        success: bool,
        transition: TestRunWorkflowTransition,
        run_id: str | None = None,
    ) -> TestRunWorkflowResult:
        """Apply workflow transitions for tasks based on test success."""
        target_state = transition.target_state(success)
        if not target_state:
            return TestRunWorkflowResult()

        tasks = await self._task_repo.get_by_ids(list(task_ids))
        result = TestRunWorkflowResult(tasks_considered=len(tasks))

        async with self.db.transaction():
            for task in tasks:
                if not task.workflow_id or not task.current_state:
                    result.record_skip("missing_workflow")
                    continue

                workflow = get_workflow_by_id(task.workflow_id)
                if workflow is None:
                    result.record_skip("workflow_not_found")
                    continue
                if workflow.entity_type != "task":
                    workflow = replace(workflow, entity_type="task")

                if task.current_state == target_state:
                    result.record_skip("already_in_state")
                    continue

                gate_result = await self._label_service.evaluate_gates(
                    workflow_id=workflow.id,
                    entity_type=workflow.entity_type,
                    entity_id=task.id,
                    from_state=task.current_state,
                    to_state=target_state,
                )
                if not gate_result.allowed:
                    result.record_skip("label_gate_blocked")
                    continue

                evidence_result = await self._evidence_gate_service.evaluate_gates(
                    workflow_id=workflow.id,
                    entity_type=workflow.entity_type,
                    entity_id=task.id,
                    from_state=task.current_state,
                    to_state=target_state,
                )
                if not evidence_result.allowed:
                    result.record_skip("evidence_gate_blocked")
                    continue

                sm = StateMachine(workflow, self._state_repo)
                context = {"trigger": "test_run", "success": success}
                if run_id:
                    context["run_id"] = run_id
                can_transition, _error = sm.can_transition(
                    task.current_state,
                    target_state,
                    context=context,
                )
                if not can_transition:
                    result.record_skip("invalid_transition")
                    continue

                await sm.transition(
                    entity_id=task.id,
                    from_state=task.current_state,
                    to_state=target_state,
                    triggered_by=transition.triggered_by,
                    reason=transition.reason,
                    metadata=context,
                )

                previous_state = task.current_state
                task.transition_to(
                    target_state, transition.triggered_by, transition.reason
                )
                await self._task_repo.save(
                    task,
                    EventType.TASK_UPDATED,
                    {
                        "state_transition": f"{previous_state} -> {target_state}",
                        "test_run_id": run_id,
                    },
                )
                result.tasks_transitioned += 1

            if result.tasks_transitioned:
                await self.metrics.record_counter(
                    "test_run.workflow_transition.applied",
                    labels={"success": str(success)},
                )
                await self.metrics.flush()

        return result
