"""Service for automation rules and execution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from pms.core.events import DomainEvent, EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.models.automation_rule import (
    AutomationActionType,
    AutomationRule,
    AutomationRuleRun,
    JsonObject,
    JsonValue,
)
from pms.models.base import now_utc
from pms.models.enums import Priority
from pms.repositories.automation_rule_repository import AutomationRuleRepository
from pms.repositories.automation_rule_run_repository import AutomationRuleRunRepository
from pms.repositories.base import QueryResult
from pms.services.comment_service import CommentService
from pms.services.custom_field_service import CustomFieldService
from pms.services.task_service import TaskService

type EventPayload = dict[str, JsonValue]

if TYPE_CHECKING:
    from pms.db.connection import Database


@dataclass
class AutomationRunResult:
    """Result of evaluating a rule for an event."""

    rule: AutomationRule
    run: AutomationRuleRun


class AutomationRuleService:
    """Service for automation rule management and execution."""

    def __init__(
        self,
        db: Database,
        metrics: MetricsCollector,
        *,
        task_service: TaskService | None = None,
        comment_service: CommentService | None = None,
        custom_field_service: CustomFieldService | None = None,
    ) -> None:
        self.db = db
        self.metrics = metrics
        self._repo = AutomationRuleRepository(db)
        self._run_repo = AutomationRuleRunRepository(db)
        self._event_store = EventStore(db)
        self._task_service = task_service or TaskService(
            db,
            EventStore(db),
            RevisionStore(db),
            metrics,
        )
        self._comment_service = comment_service or CommentService(db, metrics)
        self._custom_field_service = custom_field_service or CustomFieldService(
            db, metrics
        )

    async def create_rule(
        self,
        *,
        name: str,
        event_pattern: str,
        action_type: AutomationActionType,
        action_payload: JsonObject,
        description: str | None = None,
        aggregate_type: str | None = None,
        aggregate_id: str | None = None,
        enabled: bool = True,
        cooldown_seconds: float = 0.0,
    ) -> AutomationRule:
        self._validate_action_payload(action_type, action_payload)
        if not event_pattern:
            raise ValueError("event_pattern is required")
        return await self._repo.create(
            name=name,
            event_pattern=event_pattern,
            action_type=action_type,
            action_payload=action_payload,
            description=description,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            enabled=enabled,
            cooldown_seconds=cooldown_seconds,
        )

    async def list_rules(
        self,
        *,
        include_archived: bool = False,
        enabled: bool | None = None,
    ) -> list[AutomationRule]:
        return await self._repo.list_all(
            include_archived=include_archived, enabled=enabled
        )

    async def get_rule(
        self,
        rule_ref: str,
        *,
        include_archived: bool = False,
    ) -> AutomationRule | None:
        rule = await self._repo.get_by_id(rule_ref, include_archived=include_archived)
        if rule is None:
            rule = await self._repo.get_by_name(
                rule_ref, include_archived=include_archived
            )
        return rule

    async def update_rule(
        self,
        rule_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        event_pattern: str | None = None,
        aggregate_type: str | None = None,
        aggregate_id: str | None = None,
        action_type: AutomationActionType | None = None,
        action_payload: JsonObject | None = None,
        enabled: bool | None = None,
        cooldown_seconds: float | None = None,
    ) -> AutomationRule | None:
        if action_payload is not None:
            target_action = action_type
            if target_action is None:
                existing = await self._repo.get_by_id(rule_id, include_archived=True)
                if existing:
                    target_action = existing.action_type
            if target_action is not None:
                self._validate_action_payload(target_action, action_payload)
        return await self._repo.update(
            rule_id,
            name=name,
            description=description,
            event_pattern=event_pattern,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            action_type=action_type,
            action_payload=action_payload,
            enabled=enabled,
            cooldown_seconds=cooldown_seconds,
        )

    async def delete_rule(self, rule_id: str) -> bool:
        return await self._repo.delete(rule_id)

    async def restore_rule(self, rule_id: str) -> AutomationRule | None:
        return await self._repo.restore(rule_id)

    async def list_runs(
        self,
        rule_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[AutomationRuleRun]:
        return await self._run_repo.list_by_rule(rule_id, limit=limit, offset=offset)

    async def run_for_event_id(
        self,
        event_id: str,
        *,
        rule_id: str | None = None,
        dry_run: bool = False,
    ) -> list[AutomationRunResult]:
        event = await self._event_store.get_event_by_id(event_id)
        if event is None:
            raise ValueError("Event not found")

        rules: list[AutomationRule]
        if rule_id:
            rule = await self._repo.get_by_id(rule_id, include_archived=True)
            if rule is None:
                raise ValueError("Automation rule not found")
            rules = [rule]
        else:
            rules = await self._repo.list_all(include_archived=False, enabled=True)

        results: list[AutomationRunResult] = []
        for rule in rules:
            result = await self._run_rule_for_event(rule, event, dry_run=dry_run)
            results.append(result)
        return results

    def _matches_rule(
        self, rule: AutomationRule, event: DomainEvent[EventPayload]
    ) -> bool:
        if rule.aggregate_type and rule.aggregate_type != event.aggregate_type:
            return False
        if rule.aggregate_id and rule.aggregate_id != event.aggregate_id:
            return False
        return self._match_pattern(rule.event_pattern, event.event_type.value)

    def _match_pattern(self, pattern: str, event_type: str) -> bool:
        if pattern in ("*", ""):
            return True
        if pattern.endswith(".*"):
            return event_type.startswith(pattern[:-2])
        return pattern == event_type

    async def _run_rule_for_event(
        self,
        rule: AutomationRule,
        event: DomainEvent[EventPayload],
        *,
        dry_run: bool = False,
    ) -> AutomationRunResult:
        run = AutomationRuleRun(
            rule_id=rule.id,
            status="running",
            event_id=event.metadata.event_id,
        )

        if not rule.is_active():
            run.status = "skipped"
            run.completed_at = run.started_at
            run.output = {"reason": "rule disabled or archived"}
            return AutomationRunResult(rule=rule, run=await self._run_repo.record(run))

        if not self._matches_rule(rule, event):
            run.status = "skipped"
            run.completed_at = run.started_at
            run.output = {"reason": "event did not match rule"}
            return AutomationRunResult(rule=rule, run=await self._run_repo.record(run))

        if rule.cooldown_seconds > 0:
            last_run_at = await self._run_repo.get_last_run_at(rule.id)
            if last_run_at:
                next_allowed = last_run_at + timedelta(seconds=rule.cooldown_seconds)
                if next_allowed > run.started_at:
                    run.status = "skipped"
                    run.completed_at = run.started_at
                    run.output = {
                        "reason": "cooldown",
                        "next_allowed": next_allowed.isoformat(),
                    }
                    return AutomationRunResult(
                        rule=rule, run=await self._run_repo.record(run)
                    )

        if dry_run:
            run.status = "dry_run"
            run.completed_at = run.started_at
            run.output = {"action_type": rule.action_type.value}
            return AutomationRunResult(rule=rule, run=await self._run_repo.record(run))

        async with self.db.transaction():
            try:
                output = await self._execute_action_in_transaction(rule, event)
                run.status = "success"
                run.output = output or {}
            except Exception as exc:
                run.status = "failed"
                run.error = str(exc)
                run.output = {"error": str(exc)}
            run.completed_at = now_utc()
            recorded = await self._run_repo.record(run)
            return AutomationRunResult(rule=rule, run=recorded)

    async def _execute_action_in_transaction(
        self, rule: AutomationRule, event: DomainEvent[EventPayload]
    ) -> JsonObject:
        payload = self._render_payload(rule.action_payload, event)
        match rule.action_type:
            case AutomationActionType.ADD_COMMENT:
                entity_type = (
                    self._as_str(payload.get("entity_type")) or event.aggregate_type
                )
                entity_id = self._as_str(payload.get("entity_id")) or event.aggregate_id
                body = self._as_str(payload.get("body")) or (
                    f"Automation '{rule.name}' triggered by {event.event_type.value}"
                )
                created_by = self._as_str(payload.get("created_by")) or "automation"
                mentions = self._as_list_str(payload.get("mentions"))
                metadata = self._as_object(payload.get("metadata"))
                comment_item = await self._comment_service.add_comment(
                    entity_type=entity_type,
                    entity_id=entity_id,
                    body=body,
                    created_by=created_by,
                    mentions=mentions,
                    metadata=metadata,
                    watch=bool(payload.get("watch", False)),
                )
                return {"comment_id": comment_item.comment.id}
            case AutomationActionType.CREATE_TASK:
                project_id = self._as_str(payload.get("project_id"))
                if not project_id:
                    raise ValueError("action_payload.project_id is required")
                title = self._as_str(payload.get("title")) or (
                    f"Follow-up: {event.event_type.value}"
                )
                description = self._as_str(payload.get("description"))
                priority_value = (
                    self._as_str(payload.get("priority")) or Priority.MEDIUM.value
                )
                try:
                    priority = Priority(priority_value)
                except ValueError as exc:
                    raise ValueError("Invalid priority") from exc
                task = await self._task_service.create_task(
                    project_id=project_id,
                    title=title,
                    description=description,
                    priority=priority,
                )
                return {"task_id": task.id}
            case AutomationActionType.UPDATE_TASK_STATUS:
                task_id = self._as_str(payload.get("task_id"))
                if not task_id and event.aggregate_type == "task":
                    task_id = event.aggregate_id
                if not task_id:
                    raise ValueError("action_payload.task_id is required")
                status = self._as_str(payload.get("status"))
                if not status:
                    raise ValueError("action_payload.status is required")
                reason = self._as_str(payload.get("reason"))
                notes = self._as_str(payload.get("notes"))
                status_task = None
                match status:
                    case "todo":
                        status_task = await self._task_service.reopen_task(task_id)
                    case "in_progress":
                        status_task = await self._task_service.start_task(
                            task_id, reason=reason
                        )
                    case "done":
                        status_task = await self._task_service.complete_task(
                            task_id,
                            notes=notes or reason,
                        )
                    case "blocked":
                        status_task = await self._task_service.block_task(
                            task_id, reason=reason
                        )
                    case "cancelled":
                        status_task = await self._task_service.cancel_task(
                            task_id, reason=reason
                        )
                    case "in_review":
                        status_task = await self._task_service.submit_for_review(
                            task_id
                        )
                    case "unblocked":
                        status_task = await self._task_service.unblock_task(task_id)
                    case _:
                        raise ValueError("Unsupported task status for automation")
                if status_task is None:
                    raise ValueError("Task not found")
                return {"task_id": status_task.id, "status": status}
            case AutomationActionType.SET_CUSTOM_FIELD_VALUE:
                field_ref = self._as_str(payload.get("field_ref"))
                if not field_ref:
                    raise ValueError("action_payload.field_ref is required")
                entity_type = (
                    self._as_str(payload.get("entity_type")) or event.aggregate_type
                )
                entity_id = self._as_str(payload.get("entity_id")) or event.aggregate_id
                value = payload.get("value")
                if value is None:
                    raise ValueError("action_payload.value is required")
                value_item = await self._custom_field_service.set_value(
                    field_ref,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    value=value,
                    created_by=self._as_str(payload.get("created_by")),
                    source=self._as_str(payload.get("source")),
                )
                return {"custom_field_value_id": value_item.value.id}
            case _:
                raise ValueError("Unsupported automation action type")

    def _validate_action_payload(
        self,
        action_type: AutomationActionType,
        action_payload: JsonObject,
    ) -> None:
        match action_type:
            case AutomationActionType.ADD_COMMENT:
                if not action_payload.get("body") and not action_payload.get(
                    "use_event_body"
                ):
                    return
            case AutomationActionType.CREATE_TASK:
                if "project_id" not in action_payload:
                    raise ValueError("action_payload.project_id is required")
            case AutomationActionType.UPDATE_TASK_STATUS:
                if "status" not in action_payload:
                    raise ValueError("action_payload.status is required")
            case AutomationActionType.SET_CUSTOM_FIELD_VALUE:
                if "field_ref" not in action_payload:
                    raise ValueError("action_payload.field_ref is required")
                if "value" not in action_payload:
                    raise ValueError("action_payload.value is required")
            case _:
                raise ValueError("Unsupported automation action type")

    def _render_payload(
        self, payload: JsonObject, event: DomainEvent[EventPayload]
    ) -> JsonObject:
        def render_value(value: JsonValue) -> JsonValue:
            if isinstance(value, str):
                return self._render_template(value, event)
            if isinstance(value, list):
                return [render_value(item) for item in value]
            if isinstance(value, dict):
                return {key: render_value(val) for key, val in value.items()}
            return value

        return {key: render_value(val) for key, val in payload.items()}

    def _render_template(self, template: str, event: DomainEvent[EventPayload]) -> str:
        tokens = {
            "event_type": event.event_type.value,
            "aggregate_type": event.aggregate_type,
            "aggregate_id": event.aggregate_id,
            "event_id": event.metadata.event_id,
            "event_timestamp": event.metadata.timestamp.isoformat(),
        }
        rendered = template
        for key, value in tokens.items():
            rendered = rendered.replace(f"{{{{{key}}}}}", str(value))
        return rendered

    def _as_str(self, value: JsonValue | None) -> str | None:
        return value if isinstance(value, str) else None

    def _as_list_str(self, value: JsonValue | None) -> list[str] | None:
        if not isinstance(value, list):
            return None
        parsed: list[str] = []
        for item in value:
            if isinstance(item, str):
                parsed.append(item)
        return parsed

    def _as_object(self, value: JsonValue | None) -> JsonObject | None:
        return value if isinstance(value, dict) else None
