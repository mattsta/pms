"""Service for structured labels and workflow gates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pms.core.entity_type_contract import entity_table_for_type, validate_entity_type
from pms.models.label import Label, LabelCategory
from pms.models.label_assignment import LabelAssignment
from pms.models.label_gate_rule import LabelGateRule, LabelGateRuleType
from pms.repositories.label_assignment_repository import (
    LabelAssignmentRepository,
    LabelAssignmentRevisionContent,
)
from pms.repositories.label_category_repository import LabelCategoryRepository
from pms.repositories.label_gate_rule_repository import LabelGateRuleRepository
from pms.repositories.label_repository import LabelRepository

if TYPE_CHECKING:
    from pms.core.metrics import MetricsCollector
    from pms.core.revisions import Revision
    from pms.db.connection import Database


@dataclass
class LabelGateResult:
    """Result of evaluating label gate rules."""

    allowed: bool
    reason: str | None = None


class LabelService:
    """Service for label management and gate evaluation."""

    def __init__(self, db: Database, metrics: MetricsCollector) -> None:
        self.db = db
        self.metrics = metrics
        self._categories = LabelCategoryRepository(db)
        self._labels = LabelRepository(db)
        self._assignments = LabelAssignmentRepository(db)
        self._gates = LabelGateRuleRepository(db)

    def _normalize_entity_type(self, entity_type: str) -> str:
        return validate_entity_type(entity_type)

    async def _ensure_entity_exists(self, entity_type: str, entity_id: str) -> None:
        table = entity_table_for_type(entity_type)
        if not table:
            return
        row = await self.db.fetch_one(
            f"SELECT id FROM {table} WHERE id = ?",
            (entity_id,),
        )
        if row is None:
            raise ValueError(f"{entity_type} '{entity_id}' not found")

    async def create_category(
        self,
        name: str,
        description: str | None = None,
        is_exclusive: bool = False,
        sort_order: int = 0,
    ) -> LabelCategory:
        async with self.db.transaction():
            category = await self._categories.create(
                name=name,
                description=description,
                is_exclusive=is_exclusive,
                sort_order=sort_order,
            )
            await self.metrics.record_counter(
                "label.category_created",
                labels={"category": name},
            )
            await self.metrics.flush()
        return category

    async def list_categories(
        self, *, include_archived: bool = False
    ) -> list[LabelCategory]:
        return await self._categories.list_all(include_archived=include_archived)

    async def get_category(self, category_id: str) -> LabelCategory | None:
        return await self._categories.get_by_id(category_id)

    async def get_category_by_name(self, name: str) -> LabelCategory | None:
        return await self._categories.get_by_name(name)

    async def update_category(
        self,
        category_id: str,
        name: str | None = None,
        description: str | None = None,
        is_exclusive: bool | None = None,
        sort_order: int | None = None,
    ) -> LabelCategory | None:
        return await self._categories.update(
            category_id=category_id,
            name=name,
            description=description,
            is_exclusive=is_exclusive,
            sort_order=sort_order,
        )

    async def delete_category(self, category_id: str) -> bool:
        return await self._categories.delete(category_id)

    async def create_label(
        self,
        name: str,
        description: str | None = None,
        category_id: str | None = None,
        color: str | None = None,
        is_system: bool = False,
    ) -> Label:
        async with self.db.transaction():
            label = await self._labels.create(
                name=name,
                description=description,
                category_id=category_id,
                color=color,
                is_system=is_system,
            )
            await self.metrics.record_counter(
                "label.created",
                labels={"label": name},
            )
            await self.metrics.flush()
        return label

    async def list_labels(
        self, category_id: str | None = None, *, include_archived: bool = False
    ) -> list[Label]:
        return await self._labels.list_all(
            category_id=category_id, include_archived=include_archived
        )

    async def get_label(self, label_id: str) -> Label | None:
        return await self._labels.get_by_id(label_id)

    async def get_label_by_name(self, name: str) -> Label | None:
        return await self._labels.get_by_name(name)

    async def update_label(
        self,
        label_id: str,
        name: str | None = None,
        description: str | None = None,
        category_id: str | None = None,
        color: str | None = None,
        is_system: bool | None = None,
    ) -> Label | None:
        return await self._labels.update(
            label_id=label_id,
            name=name,
            description=description,
            category_id=category_id,
            color=color,
            is_system=is_system,
        )

    async def delete_label(self, label_id: str) -> bool:
        return await self._labels.delete(label_id)

    async def restore_label(self, label_id: str) -> Label | None:
        return await self._labels.restore(label_id)

    async def restore_category(self, category_id: str) -> LabelCategory | None:
        return await self._categories.restore(category_id)

    async def assign_label(
        self,
        entity_type: str,
        entity_id: str,
        label_id: str,
        applied_by: str | None = None,
    ) -> LabelAssignment:
        normalized_type = self._normalize_entity_type(entity_type)
        await self._ensure_entity_exists(normalized_type, entity_id)
        label = await self._labels.get_by_id(label_id)
        if label is None:
            raise ValueError("Label not found")

        async with self.db.transaction():
            if label.category_id:
                category = await self._categories.get_by_id(label.category_id)
                if category and category.is_exclusive:
                    await self._assignments._remove_by_category_in_transaction(
                        entity_type=normalized_type,
                        entity_id=entity_id,
                        category_id=label.category_id,
                    )

            assignment = await self._assignments._assign_in_transaction(
                entity_type=normalized_type,
                entity_id=entity_id,
                label_id=label_id,
                applied_by=applied_by,
            )
            await self.metrics.record_counter(
                "label.assigned",
                labels={"entity_type": normalized_type, "label": label.name},
            )
            await self.metrics.flush()
        return assignment

    async def remove_label(
        self,
        entity_type: str,
        entity_id: str,
        label_id: str,
    ) -> bool:
        normalized_type = self._normalize_entity_type(entity_type)
        await self._ensure_entity_exists(normalized_type, entity_id)
        return await self._assignments.remove(normalized_type, entity_id, label_id)

    async def list_entity_labels(
        self,
        entity_type: str,
        entity_id: str,
    ) -> list[Label]:
        normalized_type = self._normalize_entity_type(entity_type)
        await self._ensure_entity_exists(normalized_type, entity_id)
        assignments = await self._assignments.list_for_entity(
            normalized_type, entity_id
        )
        label_ids = [a.label_id for a in assignments]
        if not label_ids:
            return []

        labels: list[Label] = []
        for label_id in label_ids:
            label = await self._labels.get_by_id(label_id)
            if label:
                labels.append(label)
        return labels

    async def list_entity_label_assignments(
        self,
        entity_type: str,
        entity_id: str,
    ) -> list[tuple[LabelAssignment, Label]]:
        """List label assignments with label details for an entity."""
        normalized_type = self._normalize_entity_type(entity_type)
        await self._ensure_entity_exists(normalized_type, entity_id)
        assignments = await self._assignments.list_for_entity(
            normalized_type, entity_id
        )
        if not assignments:
            return []

        labels: dict[str, Label] = {}
        for assignment in assignments:
            if assignment.label_id not in labels:
                label = await self._labels.get_by_id(assignment.label_id)
                if label:
                    labels[assignment.label_id] = label

        results: list[tuple[LabelAssignment, Label]] = []
        for assignment in assignments:
            label = labels.get(assignment.label_id)
            if label:
                results.append((assignment, label))
        return results

    async def get_assignment(
        self,
        assignment_id: str,
    ) -> LabelAssignment | None:
        """Fetch a label assignment by ID."""
        return await self._assignments.get_by_id(assignment_id)

    async def get_assignment_history(
        self,
        assignment_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Revision[LabelAssignmentRevisionContent]]:
        """Fetch assignment revision history."""
        return await self._assignments.get_assignment_history(
            assignment_id, limit=limit, offset=offset
        )

    async def get_assignment_history_count(self, assignment_id: str) -> int:
        """Count assignment revisions."""
        return await self._assignments.get_history_count(assignment_id)

    async def add_gate_rule(
        self,
        workflow_id: str,
        entity_type: str,
        from_state: str,
        to_state: str,
        rule_type: LabelGateRuleType,
        label_id: str | None = None,
        category_id: str | None = None,
        message: str | None = None,
    ) -> LabelGateRule:
        normalized_type = self._normalize_entity_type(entity_type)
        return await self._gates.create(
            workflow_id=workflow_id,
            entity_type=normalized_type,
            from_state=from_state,
            to_state=to_state,
            rule_type=rule_type,
            label_id=label_id,
            category_id=category_id,
            message=message,
        )

    async def list_gate_rules(
        self,
        workflow_id: str,
        entity_type: str,
        from_state: str,
        to_state: str,
    ) -> list[LabelGateRule]:
        normalized_type = self._normalize_entity_type(entity_type)
        return await self._gates.list_for_transition(
            workflow_id,
            normalized_type,
            from_state,
            to_state,
        )

    async def remove_gate_rule(self, rule_id: str) -> bool:
        """Remove a label gate rule."""
        return await self._gates.delete(rule_id)

    async def evaluate_gates(
        self,
        workflow_id: str,
        entity_type: str,
        entity_id: str,
        from_state: str,
        to_state: str,
    ) -> LabelGateResult:
        normalized_type = self._normalize_entity_type(entity_type)
        rules = await self._gates.list_for_transition(
            workflow_id,
            normalized_type,
            from_state,
            to_state,
        )
        if not rules:
            return LabelGateResult(allowed=True)

        assignments = await self._assignments.list_for_entity(
            normalized_type, entity_id
        )
        assigned_label_ids = {a.label_id for a in assignments}

        category_ids: set[str] = set()
        for label_id in assigned_label_ids:
            label = await self._labels.get_by_id(label_id)
            if label and label.category_id:
                category_ids.add(label.category_id)

        for rule in rules:
            match rule.rule_type:
                case LabelGateRuleType.REQUIRE_LABEL:
                    if not rule.label_id or rule.label_id not in assigned_label_ids:
                        return LabelGateResult(
                            allowed=False,
                            reason=rule.message
                            or "Missing required label for transition",
                        )
                case LabelGateRuleType.FORBID_LABEL:
                    if rule.label_id and rule.label_id in assigned_label_ids:
                        return LabelGateResult(
                            allowed=False,
                            reason=rule.message or "Label blocks this transition",
                        )
                case LabelGateRuleType.REQUIRE_CATEGORY:
                    if not rule.category_id or rule.category_id not in category_ids:
                        return LabelGateResult(
                            allowed=False,
                            reason=rule.message or "Required label category missing",
                        )
                case LabelGateRuleType.FORBID_CATEGORY:
                    if rule.category_id and rule.category_id in category_ids:
                        return LabelGateResult(
                            allowed=False,
                            reason=rule.message
                            or "Label category blocks this transition",
                        )

        return LabelGateResult(allowed=True)
