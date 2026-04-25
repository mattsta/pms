"""Service for evidence gate rules and enforcement."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pms.core.entity_type_contract import validate_entity_type
from pms.core.metrics import MetricsCollector
from pms.models.evidence_gate_rule import EvidenceGateRule
from pms.models.json_types import ModelObject
from pms.models.workflow_state import get_workflow_by_id
from pms.repositories.evidence_gate_rule_repository import (
    EvidenceGateRuleRepository,
)
from pms.repositories.task_evidence_repository import TaskEvidenceRepository
from pms.repositories.test_run_repository import TestRunRepository

if TYPE_CHECKING:
    from pms.db.connection import Database


@dataclass
class EvidenceGateResult:
    """Result of evaluating evidence gates."""

    allowed: bool
    reason: str | None = None


@dataclass
class EvidenceGateIndicator:
    """Summary of evidence gate blocking for a task."""

    blocked: bool
    blocked_transitions: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> ModelObject:
        return {
            "blocked": self.blocked,
            "blocked_transitions": list(self.blocked_transitions),
            "reasons": list(self.reasons),
        }


class EvidenceGateService:
    """Service for evidence gate rule management and evaluation."""

    _ALLOWED_ENTITY_TYPES = {"task"}

    def __init__(self, db: Database, metrics: MetricsCollector) -> None:
        self.db = db
        self.metrics = metrics
        self._repo = EvidenceGateRuleRepository(db)
        self._evidence_repo = TaskEvidenceRepository(db)
        self._test_runs = TestRunRepository(db)

    async def add_gate_rule(
        self,
        workflow_id: str,
        entity_type: str,
        from_state: str,
        to_state: str,
        evidence_type: str,
        min_count: int = 1,
        require_success: bool = False,
        message: str | None = None,
    ) -> EvidenceGateRule:
        normalized_type = validate_entity_type(
            entity_type, allowed=self._ALLOWED_ENTITY_TYPES
        )
        return await self._repo.create(
            workflow_id=workflow_id,
            entity_type=normalized_type,
            from_state=from_state,
            to_state=to_state,
            evidence_type=evidence_type,
            min_count=min_count,
            require_success=require_success,
            message=message,
        )

    async def list_gate_rules(
        self,
        workflow_id: str,
        entity_type: str,
        from_state: str,
        to_state: str,
    ) -> list[EvidenceGateRule]:
        normalized_type = validate_entity_type(
            entity_type, allowed=self._ALLOWED_ENTITY_TYPES
        )
        return await self._repo.list_for_transition(
            workflow_id=workflow_id,
            entity_type=normalized_type,
            from_state=from_state,
            to_state=to_state,
        )

    async def remove_gate_rule(self, rule_id: str) -> bool:
        """Remove an evidence gate rule."""
        return await self._repo.delete(rule_id)

    async def evaluate_gates(
        self,
        workflow_id: str,
        entity_type: str,
        entity_id: str,
        from_state: str | None,
        to_state: str,
    ) -> EvidenceGateResult:
        """Evaluate evidence gate rules for a workflow transition."""
        normalized_type = validate_entity_type(
            entity_type, allowed=self._ALLOWED_ENTITY_TYPES
        )
        if normalized_type != "task":
            return EvidenceGateResult(allowed=True)

        if not from_state:
            return EvidenceGateResult(allowed=True)

        rules = await self._repo.list_for_transition(
            workflow_id=workflow_id,
            entity_type=normalized_type,
            from_state=from_state,
            to_state=to_state,
        )
        if not rules:
            return EvidenceGateResult(allowed=True)

        evidence_items = await self._evidence_repo.list_by_task_ids([entity_id])
        evidence_by_type: dict[str, list[str]] = {}
        for evidence in evidence_items:
            evidence_by_type.setdefault(evidence.evidence_type, []).append(
                evidence.reference
            )

        for rule in rules:
            references = evidence_by_type.get(rule.evidence_type, [])
            count = len(references)

            if rule.require_success and rule.evidence_type == "test_run":
                rows = await self._test_runs.get_by_ids(references)
                count = sum(1 for row in rows if bool(row.get("success")))

            if count < rule.min_count:
                message = rule.message or (
                    "Evidence gate requires "
                    f"{rule.min_count} '{rule.evidence_type}' evidence item(s)"
                )
                await self.metrics.record_counter(
                    "evidence_gate.blocked",
                    labels={
                        "workflow_id": workflow_id,
                        "evidence_type": rule.evidence_type,
                    },
                )
                await self.metrics.flush_best_effort(
                    context="evidence_gate.evaluate_gates.blocked"
                )
                return EvidenceGateResult(allowed=False, reason=message)

        await self.metrics.record_counter(
            "evidence_gate.allowed",
            labels={"workflow_id": workflow_id},
        )
        await self.metrics.flush_best_effort(
            context="evidence_gate.evaluate_gates.allowed"
        )
        return EvidenceGateResult(allowed=True)

    async def get_task_indicator(
        self,
        task_id: str,
        workflow_id: str | None,
        current_state: str | None,
    ) -> EvidenceGateIndicator | None:
        """Evaluate evidence gate status across available transitions for a task."""
        if not workflow_id or not current_state:
            return None

        workflow = get_workflow_by_id(workflow_id)
        if not workflow:
            return None

        transitions = workflow.get_available_transitions(current_state)
        blocked_transitions: list[str] = []
        reasons: list[str] = []

        for transition in transitions:
            result = await self.evaluate_gates(
                workflow_id=workflow_id,
                entity_type="task",
                entity_id=task_id,
                from_state=current_state,
                to_state=transition.to_state,
            )
            if not result.allowed:
                blocked_transitions.append(transition.to_state)
                if result.reason and result.reason not in reasons:
                    reasons.append(result.reason)

        if not blocked_transitions:
            return EvidenceGateIndicator(blocked=False)

        return EvidenceGateIndicator(
            blocked=True,
            blocked_transitions=blocked_transitions,
            reasons=reasons,
        )
