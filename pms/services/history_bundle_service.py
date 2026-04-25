"""Service for exporting revision history bundles."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol

from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.models import (
    AutomationRule,
    EvidenceGateRule,
    Goal,
    KeyResult,
    Label,
    LabelCategory,
    LabelGateRule,
    Objective,
    Organization,
    Plan,
    PlanTestJob,
    Portfolio,
    Product,
    Program,
    Project,
    SavedSearch,
    Task,
    Team,
)
from pms.models.json_types import ModelObject
from pms.repositories.automation_rule_repository import AutomationRuleRepository
from pms.repositories.evidence_gate_rule_repository import EvidenceGateRuleRepository
from pms.repositories.goal_repository import GoalRepository
from pms.repositories.key_result_repository import KeyResultRepository
from pms.repositories.label_category_repository import LabelCategoryRepository
from pms.repositories.label_gate_rule_repository import LabelGateRuleRepository
from pms.repositories.label_repository import LabelRepository
from pms.repositories.objective_repository import ObjectiveRepository
from pms.repositories.organization_repository import OrganizationRepository
from pms.repositories.plan_repository import PlanRepository
from pms.repositories.plan_test_job_repository import PlanTestJobRepository
from pms.repositories.portfolio_repository import PortfolioRepository
from pms.repositories.product_repository import ProductRepository
from pms.repositories.program_repository import ProgramRepository
from pms.repositories.project_repository import ProjectRepository
from pms.repositories.saved_search_repository import SavedSearchRepository
from pms.repositories.task_repository import TaskRepository
from pms.repositories.team_repository import TeamRepository
from pms.services.hierarchy_scope_service import HierarchyScopeService

if TYPE_CHECKING:
    from pms.db.connection import Database

type PagePayload = dict[str, int | bool | None]
type RevisionContent = ModelObject
type LinkedEntitySummary = dict[str, str | datetime | None]
type LinkedEntityMap = dict[str, list[LinkedEntitySummary]]
type LinkedHistoryMap = dict[str, dict[str, HistoryPage]]
type HistoryEntity = (
    Task
    | Project
    | Plan
    | Goal
    | Objective
    | KeyResult
    | Organization
    | Team
    | Portfolio
    | Program
    | Product
    | Label
    | LabelCategory
    | LabelGateRule
    | EvidenceGateRule
    | AutomationRule
    | SavedSearch
    | PlanTestJob
)


class EntityHistoryRepository(Protocol):
    entity_type: str


class RevisionLike(Protocol):
    def to_dict(self) -> ModelObject: ...


def _page_payload(total_count: int, limit: int, offset: int) -> PagePayload:
    limit_value = max(limit, 0)
    offset_value = max(offset, 0)
    has_more = False
    next_offset = None
    if limit_value > 0 and offset_value + limit_value < total_count:
        has_more = True
        next_offset = offset_value + limit_value
    return {
        "total_count": total_count,
        "limit": limit_value,
        "offset": offset_value,
        "has_more": has_more,
        "next_offset": next_offset,
    }


@dataclass
class HistoryPage:
    """Paginated revision history for an entity."""

    items: list[RevisionLike]
    total_count: int
    limit: int
    offset: int

    def to_dict(self) -> ModelObject:
        return {
            "items": [item.to_dict() for item in self.items],
            "page": _page_payload(self.total_count, self.limit, self.offset),
        }


@dataclass
class HistoryBundle:
    """Revision history bundle for an entity and linked items."""

    entity_type: str
    entity_id: str
    history: HistoryPage
    generated_at: datetime
    linked: LinkedEntityMap = field(default_factory=dict)
    linked_history: LinkedHistoryMap = field(default_factory=dict)

    def to_dict(self) -> ModelObject:
        payload: ModelObject = {
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "generated_at": self.generated_at.isoformat(),
            "history": self.history.to_dict(),
        }
        if self.linked:
            payload["linked"] = self.linked
        if self.linked_history:
            payload["linked_history"] = {
                group: {
                    entity_id: page.to_dict() for entity_id, page in history_map.items()
                }
                for group, history_map in self.linked_history.items()
            }
        return payload


class HistoryBundleService:
    """Build revision history bundles for entities and linked items."""

    def __init__(self, db: Database) -> None:
        self._db = db
        self._event_store = EventStore(db)
        self._revision_store = RevisionStore(db)
        self._metrics = MetricsCollector(db)

        self._task_repo = TaskRepository(
            db, self._event_store, self._revision_store, self._metrics
        )
        self._project_repo = ProjectRepository(
            db, self._event_store, self._revision_store, self._metrics
        )
        self._plan_repo = PlanRepository(
            db, self._event_store, self._revision_store, self._metrics
        )
        self._goal_repo = GoalRepository(
            db, self._event_store, self._revision_store, self._metrics
        )
        self._objective_repo = ObjectiveRepository(
            db, self._event_store, self._revision_store, self._metrics
        )
        self._key_result_repo = KeyResultRepository(
            db, self._event_store, self._revision_store, self._metrics
        )
        self._organization_repo = OrganizationRepository(
            db, self._event_store, self._revision_store, self._metrics
        )
        self._team_repo = TeamRepository(
            db, self._event_store, self._revision_store, self._metrics
        )
        self._portfolio_repo = PortfolioRepository(
            db, self._event_store, self._revision_store, self._metrics
        )
        self._program_repo = ProgramRepository(
            db, self._event_store, self._revision_store, self._metrics
        )
        self._product_repo = ProductRepository(
            db, self._event_store, self._revision_store, self._metrics
        )
        self._label_repo = LabelRepository(db)
        self._label_category_repo = LabelCategoryRepository(db)
        self._label_gate_rule_repo = LabelGateRuleRepository(db)
        self._evidence_gate_rule_repo = EvidenceGateRuleRepository(db)
        self._automation_rule_repo = AutomationRuleRepository(db)
        self._saved_search_repo = SavedSearchRepository(db)
        self._plan_test_job_repo = PlanTestJobRepository(db)
        self._hierarchy = HierarchyScopeService(
            db,
            self._event_store,
            self._revision_store,
            self._metrics,
        )

    async def build_bundle(
        self,
        entity_type: str,
        entity_id: str,
        *,
        include_linked: bool = False,
        include_linked_history: bool = False,
        history_limit: int = 20,
        history_offset: int = 0,
        linked_limit: int = 20,
        linked_history_limit: int | None = None,
    ) -> HistoryBundle | None:
        if include_linked_history:
            include_linked = True

        repo, entity = await self._resolve_entity(entity_type, entity_id)
        if repo is None or entity is None:
            return None

        effective_history_limit = history_limit if history_limit > 0 else 1000
        effective_history_offset = max(history_offset, 0)
        effective_linked_limit = linked_limit if linked_limit > 0 else 1000
        effective_linked_history_limit = (
            linked_history_limit
            if linked_history_limit and linked_history_limit > 0
            else effective_history_limit
        )

        history_page = await self._build_history_page(
            repo,
            entity_id,
            limit=effective_history_limit,
            offset=effective_history_offset,
        )
        bundle = HistoryBundle(
            entity_type=entity_type,
            entity_id=entity_id,
            history=history_page,
            generated_at=datetime.now(UTC),
        )

        if include_linked:
            linked, linked_history = await self._build_linked(
                entity_type=entity_type,
                entity=entity,
                linked_limit=effective_linked_limit,
                history_limit=effective_linked_history_limit,
                include_linked_history=include_linked_history,
            )
            bundle.linked = linked
            bundle.linked_history = linked_history

        return bundle

    async def _build_history_page(
        self,
        repo: EntityHistoryRepository,
        entity_id: str,
        *,
        limit: int,
        offset: int,
    ) -> HistoryPage:
        total_count = await self._revision_store.get_revision_count(
            repo.entity_type, entity_id
        )
        items_raw = await self._revision_store.get_history(
            repo.entity_type, entity_id, limit=limit, offset=offset
        )
        items: list[RevisionLike] = [item for item in items_raw]
        return HistoryPage(
            items=items,
            total_count=total_count,
            limit=limit,
            offset=offset,
        )

    async def _resolve_entity(
        self, entity_type: str, entity_id: str
    ) -> tuple[EntityHistoryRepository | None, HistoryEntity | None]:
        match entity_type:
            case "task":
                return self._task_repo, await self._task_repo.get_by_id(entity_id)
            case "project":
                return (
                    self._project_repo,
                    await self._project_repo.get_by_id(entity_id),
                )
            case "plan":
                return self._plan_repo, await self._plan_repo.get_by_id(entity_id)
            case "goal":
                return self._goal_repo, await self._goal_repo.get_by_id(entity_id)
            case "objective":
                return (
                    self._objective_repo,
                    await self._objective_repo.get_by_id(entity_id),
                )
            case "key_result":
                return (
                    self._key_result_repo,
                    await self._key_result_repo.get_by_id(entity_id),
                )
            case "organization":
                return (
                    self._organization_repo,
                    await self._organization_repo.get_by_id(entity_id),
                )
            case "team":
                return self._team_repo, await self._team_repo.get_by_id(entity_id)
            case "portfolio":
                return (
                    self._portfolio_repo,
                    await self._portfolio_repo.get_by_id(entity_id),
                )
            case "program":
                return (
                    self._program_repo,
                    await self._program_repo.get_by_id(entity_id),
                )
            case "product":
                return (
                    self._product_repo,
                    await self._product_repo.get_by_id(entity_id),
                )
            case "label":
                return self._label_repo, await self._label_repo.get_by_id(entity_id)
            case "label_category":
                return (
                    self._label_category_repo,
                    await self._label_category_repo.get_by_id(entity_id),
                )
            case "label_gate_rule":
                return (
                    self._label_gate_rule_repo,
                    await self._label_gate_rule_repo.get_by_id(entity_id),
                )
            case "evidence_gate_rule":
                return (
                    self._evidence_gate_rule_repo,
                    await self._evidence_gate_rule_repo.get_by_id(entity_id),
                )
            case "automation_rule":
                return (
                    self._automation_rule_repo,
                    await self._automation_rule_repo.get_by_id(entity_id),
                )
            case "saved_search":
                return (
                    self._saved_search_repo,
                    await self._saved_search_repo.get_by_id(entity_id),
                )
            case "plan_test_job":
                return (
                    self._plan_test_job_repo,
                    await self._plan_test_job_repo.get_by_id(entity_id),
                )
            case _:
                return None, None

    async def _build_linked(
        self,
        *,
        entity_type: str,
        entity: HistoryEntity,
        linked_limit: int,
        history_limit: int,
        include_linked_history: bool,
    ) -> tuple[LinkedEntityMap, LinkedHistoryMap]:
        linked: LinkedEntityMap = {}
        linked_history: LinkedHistoryMap = {}

        match entity_type:
            case "task":
                if not isinstance(entity, Task):
                    return linked, linked_history
                project_links: list[LinkedEntitySummary] = []
                if entity.project_id:
                    project = await self._project_repo.get_by_id(entity.project_id)
                    if project:
                        project_links.append(self._summarize("project", project))
                        if include_linked_history:
                            linked_history["project"] = {
                                project.id: await self._build_history_page(
                                    self._project_repo,
                                    project.id,
                                    limit=history_limit,
                                    offset=0,
                                )
                            }
                if project_links:
                    linked["project"] = project_links

                dependencies = await self._task_repo.get_dependencies(entity.id)
                dependents = await self._task_repo.get_dependents(entity.id)
                dependency_ids = [
                    dep.depends_on_id for dep in dependencies[:linked_limit]
                ]
                dependent_ids = [dep.task_id for dep in dependents[:linked_limit]]
                linked_ids = list(dict.fromkeys(dependency_ids + dependent_ids))
                linked_tasks = (
                    await self._task_repo.get_by_ids(linked_ids) if linked_ids else []
                )
                task_map = {task.id: task for task in linked_tasks}
                if dependency_ids:
                    linked["dependencies"] = [
                        self._summarize("task", task_map[task_id])
                        for task_id in dependency_ids
                        if task_id in task_map
                    ]
                if dependent_ids:
                    linked["dependents"] = [
                        self._summarize("task", task_map[task_id])
                        for task_id in dependent_ids
                        if task_id in task_map
                    ]
                if include_linked_history and linked_tasks:
                    linked_history["dependencies"] = {
                        task_id: await self._build_history_page(
                            self._task_repo,
                            task_id,
                            limit=history_limit,
                            offset=0,
                        )
                        for task_id in dependency_ids
                        if task_id in task_map
                    }
                    linked_history["dependents"] = {
                        task_id: await self._build_history_page(
                            self._task_repo,
                            task_id,
                            limit=history_limit,
                            offset=0,
                        )
                        for task_id in dependent_ids
                        if task_id in task_map
                    }
            case "project":
                if not isinstance(entity, Project):
                    return linked, linked_history
                task_result = await self._task_repo.get_by_project(
                    entity.id, limit=linked_limit, offset=0
                )
                tasks = task_result.items
                if tasks:
                    linked["tasks"] = [self._summarize("task", task) for task in tasks]
                if include_linked_history and tasks:
                    linked_history["tasks"] = {
                        task.id: await self._build_history_page(
                            self._task_repo,
                            task.id,
                            limit=history_limit,
                            offset=0,
                        )
                        for task in tasks
                    }
            case "plan":
                if not isinstance(entity, Plan):
                    return linked, linked_history
                task_ids = list(entity.task_ids or [])[:linked_limit]
                tasks = await self._task_repo.get_by_ids(task_ids) if task_ids else []
                if tasks:
                    linked["tasks"] = [self._summarize("task", task) for task in tasks]
                if include_linked_history and tasks:
                    linked_history["tasks"] = {
                        task.id: await self._build_history_page(
                            self._task_repo,
                            task.id,
                            limit=history_limit,
                            offset=0,
                        )
                        for task in tasks
                    }
            case "goal":
                if not isinstance(entity, Goal):
                    return linked, linked_history
                objectives_result = await self._objective_repo.get_by_goal(
                    entity.id, limit=linked_limit, offset=0
                )
                objectives = objectives_result.items
                if objectives:
                    linked["objectives"] = [
                        self._summarize("objective", objective)
                        for objective in objectives
                    ]
                if include_linked_history and objectives:
                    linked_history["objectives"] = {
                        objective.id: await self._build_history_page(
                            self._objective_repo,
                            objective.id,
                            limit=history_limit,
                            offset=0,
                        )
                        for objective in objectives
                    }
            case "objective":
                if not isinstance(entity, Objective):
                    return linked, linked_history
                key_results_result = await self._key_result_repo.get_by_objective(
                    entity.id, limit=linked_limit, offset=0
                )
                key_results = key_results_result.items
                if key_results:
                    linked["key_results"] = [
                        self._summarize("key_result", key_result)
                        for key_result in key_results
                    ]
                if include_linked_history and key_results:
                    linked_history["key_results"] = {
                        key_result.id: await self._build_history_page(
                            self._key_result_repo,
                            key_result.id,
                            limit=history_limit,
                            offset=0,
                        )
                        for key_result in key_results
                    }
            case "key_result":
                if not isinstance(entity, KeyResult):
                    return linked, linked_history
                if entity.objective_id:
                    objective = await self._objective_repo.get_by_id(
                        entity.objective_id
                    )
                    if objective:
                        linked["objective"] = [self._summarize("objective", objective)]
                        if include_linked_history:
                            linked_history["objective"] = {
                                objective.id: await self._build_history_page(
                                    self._objective_repo,
                                    objective.id,
                                    limit=history_limit,
                                    offset=0,
                                )
                            }
            case "organization":
                if not isinstance(entity, Organization):
                    return linked, linked_history
                teams_result = await self._team_repo.get_by_org(
                    entity.id, limit=linked_limit, offset=0
                )
                portfolios_result = await self._portfolio_repo.get_by_org(
                    entity.id, limit=linked_limit, offset=0
                )
                programs_result = await self._program_repo.get_by_org(
                    entity.id, limit=linked_limit, offset=0
                )
                if teams_result.items:
                    linked["teams"] = [
                        self._summarize("team", team) for team in teams_result.items
                    ]
                if portfolios_result.items:
                    linked["portfolios"] = [
                        self._summarize("portfolio", portfolio)
                        for portfolio in portfolios_result.items
                    ]
                if programs_result.items:
                    linked["programs"] = [
                        self._summarize("program", program)
                        for program in programs_result.items
                    ]
                if include_linked_history:
                    if teams_result.items:
                        linked_history["teams"] = {
                            team.id: await self._build_history_page(
                                self._team_repo,
                                team.id,
                                limit=history_limit,
                                offset=0,
                            )
                            for team in teams_result.items
                        }
                    if portfolios_result.items:
                        linked_history["portfolios"] = {
                            portfolio.id: await self._build_history_page(
                                self._portfolio_repo,
                                portfolio.id,
                                limit=history_limit,
                                offset=0,
                            )
                            for portfolio in portfolios_result.items
                        }
                    if programs_result.items:
                        linked_history["programs"] = {
                            program.id: await self._build_history_page(
                                self._program_repo,
                                program.id,
                                limit=history_limit,
                                offset=0,
                            )
                            for program in programs_result.items
                        }
            case "team":
                if not isinstance(entity, Team):
                    return linked, linked_history
                if entity.org_id:
                    org = await self._organization_repo.get_by_id(entity.org_id)
                    if org:
                        linked["organization"] = [self._summarize("organization", org)]
                        if include_linked_history:
                            linked_history["organization"] = {
                                org.id: await self._build_history_page(
                                    self._organization_repo,
                                    org.id,
                                    limit=history_limit,
                                    offset=0,
                                )
                            }
            case "portfolio":
                if not isinstance(entity, Portfolio):
                    return linked, linked_history
                snapshot = await self._hierarchy.get_portfolio_snapshot(
                    entity.id,
                    limit=linked_limit,
                    offset=0,
                )
                projects = snapshot.projects.items
                goals = snapshot.goals.items
                objectives = snapshot.objectives.items
                programs_result = await self._program_repo.get_by_portfolio(
                    entity.id, limit=linked_limit, offset=0
                )
                if projects:
                    linked["projects"] = [
                        self._summarize("project", project) for project in projects
                    ]
                if goals:
                    linked["goals"] = [self._summarize("goal", goal) for goal in goals]
                if objectives:
                    linked["objectives"] = [
                        self._summarize("objective", objective)
                        for objective in objectives
                    ]
                if programs_result.items:
                    linked["programs"] = [
                        self._summarize("program", program)
                        for program in programs_result.items
                    ]
                if include_linked_history:
                    if projects:
                        linked_history["projects"] = {
                            project.id: await self._build_history_page(
                                self._project_repo,
                                project.id,
                                limit=history_limit,
                                offset=0,
                            )
                            for project in projects
                        }
                    if goals:
                        linked_history["goals"] = {
                            goal.id: await self._build_history_page(
                                self._goal_repo,
                                goal.id,
                                limit=history_limit,
                                offset=0,
                            )
                            for goal in goals
                        }
                    if objectives:
                        linked_history["objectives"] = {
                            objective.id: await self._build_history_page(
                                self._objective_repo,
                                objective.id,
                                limit=history_limit,
                                offset=0,
                            )
                            for objective in objectives
                        }
                    if programs_result.items:
                        linked_history["programs"] = {
                            program.id: await self._build_history_page(
                                self._program_repo,
                                program.id,
                                limit=history_limit,
                                offset=0,
                            )
                            for program in programs_result.items
                        }
            case "program":
                if not isinstance(entity, Program):
                    return linked, linked_history
                snapshot = await self._hierarchy.get_program_snapshot(
                    entity.id,
                    limit=linked_limit,
                    offset=0,
                )
                projects = snapshot.projects.items
                goals = snapshot.goals.items
                objectives = snapshot.objectives.items
                if projects:
                    linked["projects"] = [
                        self._summarize("project", project) for project in projects
                    ]
                if goals:
                    linked["goals"] = [self._summarize("goal", goal) for goal in goals]
                if objectives:
                    linked["objectives"] = [
                        self._summarize("objective", objective)
                        for objective in objectives
                    ]
                if include_linked_history:
                    if projects:
                        linked_history["projects"] = {
                            project.id: await self._build_history_page(
                                self._project_repo,
                                project.id,
                                limit=history_limit,
                                offset=0,
                            )
                            for project in projects
                        }
                    if goals:
                        linked_history["goals"] = {
                            goal.id: await self._build_history_page(
                                self._goal_repo,
                                goal.id,
                                limit=history_limit,
                                offset=0,
                            )
                            for goal in goals
                        }
                    if objectives:
                        linked_history["objectives"] = {
                            objective.id: await self._build_history_page(
                                self._objective_repo,
                                objective.id,
                                limit=history_limit,
                                offset=0,
                            )
                            for objective in objectives
                        }
            case "product":
                if not isinstance(entity, Product):
                    return linked, linked_history
                projects_result = await self._project_repo.get_by_product(
                    entity.id, limit=linked_limit, offset=0
                )
                projects = projects_result.items
                if projects:
                    linked["projects"] = [
                        self._summarize("project", project) for project in projects
                    ]
                if include_linked_history and projects:
                    linked_history["projects"] = {
                        project.id: await self._build_history_page(
                            self._project_repo,
                            project.id,
                            limit=history_limit,
                            offset=0,
                        )
                        for project in projects
                    }
            case "label_category":
                if not isinstance(entity, LabelCategory):
                    return linked, linked_history
                labels = await self._label_repo.list_all(category_id=entity.id)
                view_labels = labels[:linked_limit]
                if view_labels:
                    linked["labels"] = [
                        self._summarize("label", label_obj) for label_obj in view_labels
                    ]
                if include_linked_history and view_labels:
                    linked_history["labels"] = {
                        label_obj.id: await self._build_history_page(
                            self._label_repo,
                            label_obj.id,
                            limit=history_limit,
                            offset=0,
                        )
                        for label_obj in view_labels
                    }
            case "label":
                if not isinstance(entity, Label):
                    return linked, linked_history
                if entity.category_id:
                    category = await self._label_category_repo.get_by_id(
                        entity.category_id
                    )
                    if category:
                        linked["category"] = [
                            self._summarize("label_category", category)
                        ]
                        if include_linked_history:
                            linked_history["category"] = {
                                category.id: await self._build_history_page(
                                    self._label_category_repo,
                                    category.id,
                                    limit=history_limit,
                                    offset=0,
                                )
                            }
            case "label_gate_rule":
                if not isinstance(entity, LabelGateRule):
                    return linked, linked_history
                linked, linked_history = await self._build_gate_rule_links(
                    entity=entity,
                    history_limit=history_limit,
                    include_linked_history=include_linked_history,
                )
            case "plan_test_job":
                if not isinstance(entity, PlanTestJob):
                    return linked, linked_history
                if entity.plan_id:
                    plan = await self._plan_repo.get_by_id(entity.plan_id)
                    if plan:
                        linked.setdefault("plan", []).append(
                            self._summarize("plan", plan)
                        )
                        if include_linked_history:
                            linked_history["plan"] = {
                                plan.id: await self._build_history_page(
                                    self._plan_repo,
                                    plan.id,
                                    limit=history_limit,
                                    offset=0,
                                )
                            }
                task_ids = list(entity.task_ids or [])[:linked_limit]
                tasks = await self._task_repo.get_by_ids(task_ids) if task_ids else []
                if tasks:
                    linked["tasks"] = [self._summarize("task", task) for task in tasks]
                if include_linked_history and tasks:
                    linked_history["tasks"] = {
                        task.id: await self._build_history_page(
                            self._task_repo,
                            task.id,
                            limit=history_limit,
                            offset=0,
                        )
                        for task in tasks
                    }

        return linked, linked_history

    async def _build_gate_rule_links(
        self,
        *,
        entity: LabelGateRule,
        history_limit: int,
        include_linked_history: bool,
    ) -> tuple[LinkedEntityMap, LinkedHistoryMap]:
        linked: LinkedEntityMap = {}
        linked_history: LinkedHistoryMap = {}
        if entity.label_id:
            label = await self._label_repo.get_by_id(entity.label_id)
            if label:
                linked.setdefault("label", []).append(self._summarize("label", label))
                if include_linked_history:
                    linked_history["label"] = {
                        label.id: await self._build_history_page(
                            self._label_repo,
                            label.id,
                            limit=history_limit,
                            offset=0,
                        )
                    }
        if entity.category_id:
            category = await self._label_category_repo.get_by_id(entity.category_id)
            if category:
                linked.setdefault("category", []).append(
                    self._summarize("label_category", category)
                )
                if include_linked_history:
                    linked_history["category"] = {
                        category.id: await self._build_history_page(
                            self._label_category_repo,
                            category.id,
                            limit=history_limit,
                            offset=0,
                        )
                    }
        return linked, linked_history

    @staticmethod
    def _summarize(entity_type: str, entity: HistoryEntity) -> LinkedEntitySummary:
        name = HistoryBundleService._summary_name(entity)
        status = HistoryBundleService._summary_status(entity)
        return {
            "id": entity.id,
            "entity_type": entity_type,
            "name": name,
            "status": status,
            "updated_at": entity.updated_at,
        }

    @staticmethod
    def _summary_name(entity: HistoryEntity) -> str | None:
        if isinstance(entity, Task):
            return str(entity.title)
        if isinstance(
            entity,
            (
                Project,
                Plan,
                Goal,
                Objective,
                KeyResult,
                Organization,
                Team,
                Portfolio,
                Program,
                Product,
                Label,
                LabelCategory,
                AutomationRule,
                SavedSearch,
                PlanTestJob,
            ),
        ):
            return str(entity.name)
        return None

    @staticmethod
    def _summary_status(entity: HistoryEntity) -> str | None:
        if isinstance(
            entity,
            (
                Task,
                Project,
                Plan,
                Goal,
                Objective,
                KeyResult,
                Organization,
                Team,
                Portfolio,
                Program,
                Product,
            ),
        ):
            return str(entity.status.value)
        return None

    async def _load_goals_by_ids(self, goal_ids: list[str]) -> list[Goal]:
        goals: list[Goal] = []
        for goal_id in goal_ids:
            goal = await self._goal_repo.get_by_id(goal_id)
            if goal:
                goals.append(goal)
        return goals

    async def _load_objectives_by_ids(
        self, objective_ids: list[str]
    ) -> list[Objective]:
        objectives: list[Objective] = []
        for objective_id in objective_ids:
            objective = await self._objective_repo.get_by_id(objective_id)
            if objective:
                objectives.append(objective)
        return objectives
