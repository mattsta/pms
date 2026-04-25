"""Unit tests for PMS services."""

import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest

from pms.core.events import EventStore, EventType
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.db.connection import Database
from pms.models import (
    DependencyType,
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
    TaskStatus,
    TeamStatus,
)
from pms.repositories.progress_repository import ProgressRepository
from pms.repositories.state_transition_repository import StateTransitionRepository
from pms.repositories.task_repository import TaskRepository
from pms.services import (
    GoalService,
    LineageService,
    OrganizationService,
    PlanService,
    PortfolioService,
    ProgramService,
    ProjectService,
    SavedSearchService,
    TaskService,
    TeamService,
)
from pms.services.product_service import ProductService
from pms.services.test_run_retention_service import TestRunRetentionService
from pms.services.work_snapshot_service import WorkSnapshotService
from pms.workflows.transition import get_workflow_registry


@pytest.fixture
async def product_service(
    db: Database,
    event_store: EventStore,
    revision_store: RevisionStore,
    metrics_collector: MetricsCollector,
) -> ProductService:
    """Create a product service for testing."""
    return ProductService(db, event_store, revision_store, metrics_collector)


@pytest.fixture
async def project_service(
    db: Database,
    event_store: EventStore,
    revision_store: RevisionStore,
    metrics_collector: MetricsCollector,
) -> ProjectService:
    """Create a project service for testing."""
    return ProjectService(db, event_store, revision_store, metrics_collector)


@pytest.fixture
async def goal_service(
    db: Database,
    event_store: EventStore,
    revision_store: RevisionStore,
    metrics_collector: MetricsCollector,
) -> GoalService:
    """Create a goal service for testing."""
    return GoalService(db, event_store, revision_store, metrics_collector)


@pytest.fixture
async def task_service(
    db: Database,
    event_store: EventStore,
    revision_store: RevisionStore,
    metrics_collector: MetricsCollector,
) -> TaskService:
    """Create a task service for testing."""
    return TaskService(db, event_store, revision_store, metrics_collector)


@pytest.fixture
async def plan_service(
    db: Database,
    event_store: EventStore,
    revision_store: RevisionStore,
    metrics_collector: MetricsCollector,
) -> PlanService:
    """Create a plan service for testing."""
    return PlanService(db, event_store, revision_store, metrics_collector)


@pytest.fixture
async def saved_search_service(
    db: Database,
    task_service: TaskService,
    metrics_collector: MetricsCollector,
) -> SavedSearchService:
    """Create a saved search service for testing."""
    from pms.repositories.saved_search_repository import SavedSearchRepository

    return SavedSearchService(
        SavedSearchRepository(db),
        task_service,
        metrics_collector,
        db,
    )


@pytest.fixture
async def lineage_service(
    db: Database,
    event_store: EventStore,
    revision_store: RevisionStore,
    metrics_collector: MetricsCollector,
) -> LineageService:
    """Create a lineage service for testing."""
    return LineageService(db, event_store, revision_store, metrics_collector)


def _build_work_snapshot_service(
    db: Database,
    metrics: MetricsCollector,
    *,
    project_service: ProjectService,
    organization_service: OrganizationService,
    portfolio_service: PortfolioService,
    program_service: ProgramService,
    lineage_service: LineageService,
) -> WorkSnapshotService:
    return WorkSnapshotService(
        db,
        metrics,
        project_service=project_service,
        organization_service=organization_service,
        program_service=program_service,
        portfolio_service=portfolio_service,
        lineage_service=lineage_service,
        retention_service=TestRunRetentionService(db, metrics),
    )


async def _assign_task_workflow(
    task_repo: TaskRepository,
    task,
    workflow_name: str,
    state: str,
) -> None:
    workflow = get_workflow_registry()[workflow_name]
    task.assign_workflow(workflow.id, state)
    await task_repo.save(
        task,
        EventType.TASK_UPDATED,
        {"workflow_assigned": workflow.name},
    )


@pytest.fixture
async def organization_service(
    db: Database,
    event_store: EventStore,
    revision_store: RevisionStore,
    metrics_collector: MetricsCollector,
) -> OrganizationService:
    """Create an organization service for testing."""
    return OrganizationService(db, event_store, revision_store, metrics_collector)


@pytest.fixture
async def team_service(
    db: Database,
    event_store: EventStore,
    revision_store: RevisionStore,
    metrics_collector: MetricsCollector,
) -> TeamService:
    """Create a team service for testing."""
    return TeamService(db, event_store, revision_store, metrics_collector)


@pytest.fixture
async def portfolio_service(
    db: Database,
    event_store: EventStore,
    revision_store: RevisionStore,
    metrics_collector: MetricsCollector,
) -> PortfolioService:
    """Create a portfolio service for testing."""
    return PortfolioService(db, event_store, revision_store, metrics_collector)


@pytest.fixture
async def program_service(
    db: Database,
    event_store: EventStore,
    revision_store: RevisionStore,
    metrics_collector: MetricsCollector,
) -> ProgramService:
    """Create a program service for testing."""
    return ProgramService(db, event_store, revision_store, metrics_collector)


@pytest.mark.asyncio
class TestProductService:
    """Tests for ProductService."""

    async def test_create_product_rolls_back_when_metrics_flush_fails(
        self,
        product_service: ProductService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Create should roll back if metrics flush fails after the repo write."""

        async def fail_flush(*args, **kwargs):
            raise RuntimeError("metrics flush failed")

        monkeypatch.setattr(product_service.metrics, "flush", fail_flush)

        with pytest.raises(RuntimeError, match="metrics flush failed"):
            await product_service.create_product(name="Atomic Create Product")

        assert (
            await product_service.get_product_by_name("Atomic Create Product") is None
        )

    async def test_update_product_rolls_back_when_metrics_flush_fails(
        self,
        product_service: ProductService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Update should roll back if metrics flush fails after the repo write."""
        product = await product_service.create_product(name="Atomic Update Product")

        async def fail_flush(*args, **kwargs):
            raise RuntimeError("metrics flush failed")

        monkeypatch.setattr(product_service.metrics, "flush", fail_flush)

        with pytest.raises(RuntimeError, match="metrics flush failed"):
            await product_service.update_product(
                product.id,
                description="after",
                product_type="integration",
            )

        refreshed = await product_service.get_product(product.id)
        assert refreshed is not None
        assert refreshed.description is None
        assert refreshed.product_type == "service"

    async def test_assign_project_to_product_rolls_back_when_metrics_flush_fails(
        self,
        product_service: ProductService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Assignment should roll back if metrics flush fails after the repo write."""
        product = await product_service.create_product(name="Atomic Assign Product")
        project = await product_service._project_repo.create(
            name="Atomic Assign Project"
        )

        async def fail_flush(*args, **kwargs):
            raise RuntimeError("metrics flush failed")

        monkeypatch.setattr(product_service.metrics, "flush", fail_flush)

        with pytest.raises(RuntimeError, match="metrics flush failed"):
            await product_service.assign_project_to_product(project.id, product.id)

        refreshed = await product_service._project_repo.get_by_id(project.id)
        assert refreshed is not None
        assert refreshed.product_id is None

    async def test_archive_product_rolls_back_when_metrics_flush_fails(
        self,
        product_service: ProductService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Archive should roll back if metrics flush fails after the repo write."""
        product = await product_service.create_product(name="Atomic Archive Product")

        async def fail_flush(*args, **kwargs):
            raise RuntimeError("metrics flush failed")

        monkeypatch.setattr(product_service.metrics, "flush", fail_flush)

        with pytest.raises(RuntimeError, match="metrics flush failed"):
            await product_service.archive_product(product.id)

        refreshed = await product_service.get_product(product.id)
        assert refreshed is not None
        assert refreshed.status == ProductStatus.ACTIVE

    async def test_sunset_product_rolls_back_when_metrics_flush_fails(
        self,
        product_service: ProductService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Sunset should roll back if metrics flush fails after the repo write."""
        product = await product_service.create_product(name="Atomic Sunset Product")

        async def fail_flush(*args, **kwargs):
            raise RuntimeError("metrics flush failed")

        monkeypatch.setattr(product_service.metrics, "flush", fail_flush)

        with pytest.raises(RuntimeError, match="metrics flush failed"):
            await product_service.sunset_product(product.id)

        refreshed = await product_service.get_product(product.id)
        assert refreshed is not None
        assert refreshed.status == ProductStatus.ACTIVE

    async def test_create_project_in_product_rolls_back_when_assignment_fails(
        self,
        product_service: ProductService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Product-scoped project creation should roll back if late assignment fails."""
        product = await product_service.create_product(name="Atomic Product")

        async def _fail_assign(*args, **kwargs):
            raise RuntimeError("product assignment failed")

        monkeypatch.setattr(
            product_service._project_repo,
            "assign_to_product",
            _fail_assign,
        )

        with pytest.raises(RuntimeError, match="product assignment failed"):
            await product_service.create_project_in_product(
                product.id,
                "Atomic Nested Project",
            )

        assert (
            await product_service._project_repo.get_by_name("Atomic Nested Project")
            is None
        )


@pytest.mark.asyncio
class TestProjectService:
    """Tests for ProjectService."""

    async def test_create_project_rolls_back_when_metrics_flush_fails(
        self,
        project_service: ProjectService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Create should roll back if metrics flush fails after the repo write."""

        async def fail_flush(*args, **kwargs):
            raise RuntimeError("metrics flush failed")

        monkeypatch.setattr(project_service.metrics, "flush", fail_flush)

        with pytest.raises(RuntimeError, match="metrics flush failed"):
            await project_service.create_project(name="Atomic Create Project")

        assert (
            await project_service.get_project_by_name("Atomic Create Project") is None
        )

    async def test_create_project(self, project_service: ProjectService):
        """Test creating a project through service."""
        project = await project_service.create_project(
            name="Service Test Project",
            description="Created via service",
            tags=["test", "service"],
        )

        assert project.id is not None
        assert project.name == "Service Test Project"
        assert project.description == "Created via service"
        assert set(project.tags) == {"test", "service"}

    async def test_get_project_by_name(self, project_service: ProjectService):
        """Test getting project by name."""
        await project_service.create_project(name="Findable Project")

        project = await project_service.get_project_by_name("Findable Project")

        assert project is not None
        assert project.name == "Findable Project"

    async def test_list_projects(self, project_service: ProjectService):
        """Test listing projects."""
        await project_service.create_project(name="List Project A")
        await project_service.create_project(name="List Project B")

        result = await project_service.list_projects()

        assert result.total_count >= 2
        names = [p.name for p in result.items]
        assert "List Project A" in names
        assert "List Project B" in names

    async def test_list_projects_by_status(self, project_service: ProjectService):
        """Test filtering projects by status."""
        p = await project_service.create_project(name="To Archive Project")
        await project_service.archive_project(p.id)

        archived = await project_service.list_projects(status=ProjectStatus.ARCHIVED)
        active = await project_service.list_projects(status=ProjectStatus.ACTIVE)

        archived_names = [p.name for p in archived.items]
        active_names = [p.name for p in active.items]

        assert "To Archive Project" in archived_names
        assert "To Archive Project" not in active_names

    async def test_update_project(self, project_service: ProjectService):
        """Test updating a project."""
        project = await project_service.create_project(name="Update Project")

        updated = await project_service.update_project(
            project.id,
            description="New description",
            tags=["updated"],
        )

        assert updated is not None
        assert updated.description == "New description"
        assert "updated" in updated.tags

    async def test_get_last_activity_map_includes_nested_task_activity(
        self,
        project_service: ProjectService,
        task_service: TaskService,
    ):
        """Project activity should bubble up nested task execution."""
        project = await project_service.create_project(name="Nested Activity Project")
        task = await task_service.create_task(project.id, "Nested Activity Task")

        await task_service.update_task_progress(
            task.id,
            percent_complete=25,
            status_message="Nested progress",
            updated_by="tester",
        )

        activity_map = await project_service.get_last_activity_map([project.id])
        refreshed_task = await task_service.get_task(task.id)

        assert refreshed_task is not None
        assert activity_map[project.id] == refreshed_task.updated_at

    async def test_get_last_activity_map_includes_direct_project_comment_activity(
        self,
        db: Database,
        project_service: ProjectService,
    ) -> None:
        """Project activity should include direct project discussion activity."""
        from pms.services.comment_service import CommentService

        project = await project_service.create_project(name="Project Comment Activity")
        comment_service = CommentService(db, MetricsCollector(db))
        item = await comment_service.add_comment(
            entity_type="project",
            entity_id=project.id,
            body="Project note",
            created_by="tester",
        )

        activity_map = await project_service.get_last_activity_map([project.id])

        assert activity_map[project.id] == item.comment.updated_at

    async def test_get_last_transition_map_includes_nested_goal_transition(
        self,
        project_service: ProjectService,
        goal_service: GoalService,
    ) -> None:
        """Project transitions should bubble up nested goal status changes."""
        project = await project_service.create_project(name="Project Goal Transition")
        goal = await goal_service.create_goal(
            name="Project Goal Transition Goal",
            project_id=project.id,
        )

        await goal_service.update_goal(
            goal.id,
            status=GoalStatus.ON_HOLD,
            progress_percent=10,
        )

        transition_map = await project_service.get_last_transition_map([project.id])
        goal_transition_map = await goal_service.get_last_transition_map([goal.id])

        assert transition_map[project.id] == goal_transition_map[goal.id]

    async def test_update_project_rolls_back_when_metrics_flush_fails(
        self,
        project_service: ProjectService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Update should roll back if metrics flush fails after the repo write."""
        project = await project_service.create_project(name="Atomic Metric Project")

        async def fail_flush(*args, **kwargs):
            raise RuntimeError("metrics flush failed")

        monkeypatch.setattr(project_service.metrics, "flush", fail_flush)

        with pytest.raises(RuntimeError, match="metrics flush failed"):
            await project_service.update_project(
                project.id,
                description="after",
                tags=["updated"],
            )

        refreshed = await project_service.get_project(project.id)
        assert refreshed is not None
        assert refreshed.description is None
        assert "updated" not in refreshed.tags

    async def test_update_project_rolls_back_when_scope_assignment_fails(
        self,
        project_service: ProjectService,
        sample_actor,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Project updates should roll back if a late scope assignment fails."""
        org = await project_service._org_repo.create(
            name="Atomic Org",
            owner="test-actor",
            owner_id=sample_actor.id,
            members=["test-actor"],
            member_ids=[sample_actor.id],
            tags=["test"],
        )
        portfolio = await project_service._portfolio_repo.create(
            name="Atomic Portfolio",
            org_id=org.id,
            owner="test-actor",
            owner_id=sample_actor.id,
            tags=["test"],
        )
        project = await project_service.create_project(
            name="Atomic Scope Project",
            description="before",
        )

        async def _fail_assign(*args, **kwargs):
            raise RuntimeError("portfolio assignment failed")

        monkeypatch.setattr(
            project_service._project_repo,
            "assign_to_portfolio",
            _fail_assign,
        )

        with pytest.raises(RuntimeError, match="portfolio assignment failed"):
            await project_service.update_project(
                project.id,
                description="after",
                portfolio_id=portfolio.id,
            )

        reloaded = await project_service.get_project(project.id)
        assert reloaded is not None
        assert reloaded.description == "before"
        assert reloaded.portfolio_id is None
        assert reloaded.org_id is None

    async def test_archive_project(self, project_service: ProjectService):
        """Test archiving a project."""
        project = await project_service.create_project(name="Archive Me")

        archived = await project_service.archive_project(project.id)

        assert archived is not None
        assert archived.status == ProjectStatus.ARCHIVED

    async def test_archive_project_rolls_back_when_metrics_flush_fails(
        self,
        project_service: ProjectService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Project archive should roll back if metrics flush fails late."""
        project = await project_service.create_project(name="Atomic Archive Project")

        async def fail_flush(*args, **kwargs):
            raise RuntimeError("metrics flush failed")

        monkeypatch.setattr(project_service.metrics, "flush", fail_flush)

        with pytest.raises(RuntimeError, match="metrics flush failed"):
            await project_service.archive_project(project.id)

        refreshed = await project_service.get_project(project.id)
        assert refreshed is not None
        assert refreshed.status == ProjectStatus.ACTIVE

    async def test_get_project_summary(self, project_service: ProjectService):
        """Test getting project summary with stats."""
        project = await project_service.create_project(name="Summary Project")

        summary = await project_service.get_project_summary(project.id)

        assert summary is not None
        assert summary.project.id == project.id
        assert summary.health_score >= 0
        assert summary.health_score <= 1

    async def test_get_dashboard(self, project_service: ProjectService):
        """Test getting dashboard view."""
        await project_service.create_project(name="Dashboard Project 1")
        await project_service.create_project(name="Dashboard Project 2")

        dashboard = await project_service.get_dashboard()

        assert dashboard.total_projects >= 2
        assert len(dashboard.active_projects) >= 2

    async def test_completed_project_with_only_draft_plan_residue_stays_completed(
        self,
        project_service: ProjectService,
        plan_service: PlanService,
        task_service: TaskService,
    ) -> None:
        """Draft plan residue should not reopen a project with only terminal execution."""
        project = await project_service.create_project(
            name="Terminal Draft Residue Project"
        )
        task = await task_service.create_task(project.id, "Terminal Draft Residue Task")
        await task_service.start_task(task.id)
        await task_service.complete_task(task.id)
        await plan_service.create_plan(
            name="Terminal Draft Residue Plan",
            description=None,
            status=PlanStatus.DRAFT,
            format=PlanFormat.JSON,
            content={},
            project_id=project.id,
        )
        await project_service.update_project(
            project.id,
            status=ProjectStatus.COMPLETED,
        )

        summary = await project_service.get_project_summary(project.id)
        assert summary is not None
        assert summary.project.status == ProjectStatus.COMPLETED
        assert summary.effective_status == ProjectStatus.COMPLETED
        assert (
            summary.terminal_reason
            == "all linked execution scopes are already terminal"
        )

    async def test_search_projects(self, project_service: ProjectService):
        """Test searching projects."""
        await project_service.create_project(
            name="Searchable API Project",
            description="REST API",
        )

        results = await project_service.search_projects("API")

        assert len(results) >= 1
        assert any("API" in p.name for p in results)


@pytest.mark.asyncio
class TestGoalService:
    """Tests for GoalService."""

    async def test_create_goal_rolls_back_when_metrics_flush_fails(
        self,
        goal_service: GoalService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Goal create should roll back if metrics flush fails late."""

        async def fail_flush(*args, **kwargs):
            raise RuntimeError("metrics flush failed")

        monkeypatch.setattr(goal_service.metrics, "flush", fail_flush)

        with pytest.raises(RuntimeError, match="metrics flush failed"):
            await goal_service.create_goal(name="Atomic Create Goal")

        assert await goal_service.get_goal_by_name("Atomic Create Goal") is None

    async def test_create_goal(self, goal_service: GoalService):
        """Test creating a goal through service."""
        goal = await goal_service.create_goal(
            name="Service Goal",
            description="Created via service",
            horizon=GoalHorizon.SHORT_TERM,
            progress_percent=20,
        )

        assert goal.id is not None
        assert goal.name == "Service Goal"
        assert goal.description == "Created via service"
        assert goal.horizon == GoalHorizon.SHORT_TERM
        assert goal.progress_percent == 20

    async def test_list_goals(self, goal_service: GoalService):
        """Test listing goals."""
        await goal_service.create_goal(name="Goal A")
        await goal_service.create_goal(name="Goal B")

        result = await goal_service.list_goals()

        assert result.total_count >= 2
        names = [g.name for g in result.items]
        assert "Goal A" in names
        assert "Goal B" in names

    async def test_update_goal(self, goal_service: GoalService):
        """Test updating a goal."""
        goal = await goal_service.create_goal(name="Update Goal")

        updated = await goal_service.update_goal(
            goal.id,
            description="New description",
            status=GoalStatus.ON_HOLD,
            progress_percent=50,
        )

        assert updated is not None
        assert updated.description == "New description"
        assert updated.status == GoalStatus.ON_HOLD
        assert updated.progress_percent == 50

    async def test_update_goal_rolls_back_when_metrics_flush_fails(
        self,
        goal_service: GoalService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Goal update should roll back if metrics flush fails late."""
        goal = await goal_service.create_goal(name="Atomic Update Goal")

        async def fail_flush(*args, **kwargs):
            raise RuntimeError("metrics flush failed")

        monkeypatch.setattr(goal_service.metrics, "flush", fail_flush)

        with pytest.raises(RuntimeError, match="metrics flush failed"):
            await goal_service.update_goal(
                goal.id,
                description="after",
                status=GoalStatus.ON_HOLD,
                progress_percent=50,
            )

        refreshed = await goal_service.get_goal(goal.id)
        assert refreshed is not None
        assert refreshed.description is None
        assert refreshed.status == GoalStatus.ACTIVE
        assert refreshed.progress_percent == 0

    async def test_complete_goal(self, goal_service: GoalService):
        """Test completing a goal."""
        goal = await goal_service.create_goal(name="Complete Goal")

        completed = await goal_service.complete_goal(goal.id)

        assert completed is not None
        assert completed.status == GoalStatus.COMPLETED
        assert completed.progress_percent == 100

    async def test_archive_goal_rolls_back_when_metrics_flush_fails(
        self,
        goal_service: GoalService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Goal archive should roll back if metrics flush fails late."""
        goal = await goal_service.create_goal(name="Atomic Goal Archive")

        async def fail_flush(*args, **kwargs):
            raise RuntimeError("metrics flush failed")

        monkeypatch.setattr(goal_service.metrics, "flush", fail_flush)

        with pytest.raises(RuntimeError, match="metrics flush failed"):
            await goal_service.archive_goal(goal.id)

        refreshed = await goal_service.get_goal(goal.id)
        assert refreshed is not None
        assert refreshed.status == GoalStatus.ACTIVE

    async def test_complete_goal_rolls_back_when_metrics_flush_fails(
        self,
        goal_service: GoalService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Goal completion should roll back if metrics flush fails late."""
        goal = await goal_service.create_goal(name="Atomic Goal Complete")

        async def fail_flush(*args, **kwargs):
            raise RuntimeError("metrics flush failed")

        monkeypatch.setattr(goal_service.metrics, "flush", fail_flush)

        with pytest.raises(RuntimeError, match="metrics flush failed"):
            await goal_service.complete_goal(goal.id)

        refreshed = await goal_service.get_goal(goal.id)
        assert refreshed is not None
        assert refreshed.status == GoalStatus.ACTIVE
        assert refreshed.progress_percent == 0

    async def test_goal_rollup_progress(self, goal_service: GoalService):
        """Test rollup progress from key results to objectives and goals."""
        goal = await goal_service.create_goal(name="Rollup Goal")
        objective = await goal_service.create_objective(
            goal_id=goal.id,
            name="Objective A",
        )

        key_result = await goal_service.create_key_result(
            objective_id=objective.id,
            name="KR A",
            current_value=40,
            target_value=100,
        )

        assert key_result.progress_percent == 40

        refreshed_objective = await goal_service.get_objective(objective.id)
        assert refreshed_objective is not None
        assert refreshed_objective.progress_percent == 40

        refreshed_goal = await goal_service.get_goal(goal.id)
        assert refreshed_goal is not None
        assert refreshed_goal.progress_percent == 40

    async def test_goal_last_activity_includes_key_result_comment_activity(
        self,
        db: Database,
        goal_service: GoalService,
    ) -> None:
        """Goal activity should bubble up nested key-result discussion activity."""
        from pms.services.comment_service import CommentService

        goal = await goal_service.create_goal(name="Goal Comment Rollup")
        objective = await goal_service.create_objective(
            goal_id=goal.id,
            name="Objective Comment Rollup",
        )
        key_result = await goal_service.create_key_result(
            objective_id=objective.id,
            name="Key Result Comment Rollup",
            current_value=1,
            target_value=10,
        )
        comment_service = CommentService(db, MetricsCollector(db))
        item = await comment_service.add_comment(
            entity_type="key_result",
            entity_id=key_result.id,
            body="KR note",
            created_by="tester",
        )

        activity_map = await goal_service.get_last_activity_map([goal.id])

        assert activity_map[goal.id] == item.comment.updated_at

    async def test_key_result_last_activity_map_includes_comment_activity(
        self,
        db: Database,
        goal_service: GoalService,
    ) -> None:
        """Key result activity should include direct discussion activity."""
        from pms.services.comment_service import CommentService

        goal = await goal_service.create_goal(name="Key Result Activity Goal")
        objective = await goal_service.create_objective(
            goal_id=goal.id,
            name="Key Result Activity Objective",
        )
        key_result = await goal_service.create_key_result(
            objective_id=objective.id,
            name="Key Result Activity Leaf",
            current_value=1,
            target_value=10,
        )
        comment_service = CommentService(db, MetricsCollector(db))
        item = await comment_service.add_comment(
            entity_type="key_result",
            entity_id=key_result.id,
            body="KR discussion",
            created_by="tester",
        )

        activity_map = await goal_service.get_key_result_last_activity_map(
            [key_result.id]
        )

        assert activity_map[key_result.id] == item.comment.updated_at

    async def test_create_objective_rolls_back_when_goal_rollup_fails(
        self,
        goal_service: GoalService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Objective creation should roll back if goal rollup recompute fails."""
        goal = await goal_service.create_goal(name="Atomic Goal")

        async def _fail_rollup(goal_id: str) -> None:
            raise RuntimeError(f"goal rollup failed for {goal_id}")

        monkeypatch.setattr(goal_service, "_update_goal_rollup", _fail_rollup)

        with pytest.raises(RuntimeError, match="goal rollup failed"):
            await goal_service.create_objective(
                goal_id=goal.id,
                name="Atomic Objective",
            )

        objectives = await goal_service.list_objectives(goal_id=goal.id)
        assert objectives.total_count == 0

    async def test_create_objective_rolls_back_when_metrics_flush_fails(
        self,
        goal_service: GoalService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Objective creation should roll back if metrics flush fails late."""
        goal = await goal_service.create_goal(name="Atomic Goal")

        async def fail_flush(*args, **kwargs):
            raise RuntimeError("metrics flush failed")

        monkeypatch.setattr(goal_service.metrics, "flush", fail_flush)

        with pytest.raises(RuntimeError, match="metrics flush failed"):
            await goal_service.create_objective(
                goal_id=goal.id,
                name="Atomic Objective",
            )

        objectives = await goal_service.list_objectives(goal_id=goal.id)
        assert objectives.total_count == 0

    async def test_update_objective_rolls_back_when_metrics_flush_fails(
        self,
        goal_service: GoalService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Objective update should roll back if metrics flush fails late."""
        goal = await goal_service.create_goal(name="Atomic Goal")
        objective = await goal_service.create_objective(
            goal_id=goal.id,
            name="Atomic Objective",
        )

        async def fail_flush(*args, **kwargs):
            raise RuntimeError("metrics flush failed")

        monkeypatch.setattr(goal_service.metrics, "flush", fail_flush)

        with pytest.raises(RuntimeError, match="metrics flush failed"):
            await goal_service.update_objective(
                objective.id,
                description="after",
                status=GoalStatus.ON_HOLD,
                progress_percent=50,
            )

        refreshed = await goal_service.get_objective(objective.id)
        assert refreshed is not None
        assert refreshed.description is None
        assert refreshed.status == GoalStatus.ACTIVE
        assert refreshed.progress_percent == 0

    async def test_update_objective_rolls_back_when_goal_rollup_fails(
        self,
        goal_service: GoalService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Objective update should roll back if goal rollup recompute fails."""
        goal = await goal_service.create_goal(name="Atomic Goal")
        objective = await goal_service.create_objective(
            goal_id=goal.id,
            name="Atomic Objective",
        )

        async def _fail_rollup(goal_id: str) -> None:
            raise RuntimeError(f"goal rollup failed for {goal_id}")

        monkeypatch.setattr(goal_service, "_update_goal_rollup", _fail_rollup)

        with pytest.raises(RuntimeError, match="goal rollup failed"):
            await goal_service.update_objective(
                objective.id,
                description="after",
                status=GoalStatus.ON_HOLD,
                progress_percent=50,
            )

        refreshed = await goal_service.get_objective(objective.id)
        assert refreshed is not None
        assert refreshed.description is None
        assert refreshed.status == GoalStatus.ACTIVE
        assert refreshed.progress_percent == 0

    async def test_complete_objective_rolls_back_when_metrics_flush_fails(
        self,
        goal_service: GoalService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Objective completion should roll back if metrics flush fails late."""
        goal = await goal_service.create_goal(name="Atomic Goal")
        objective = await goal_service.create_objective(
            goal_id=goal.id,
            name="Atomic Objective",
        )

        async def fail_flush(*args, **kwargs):
            raise RuntimeError("metrics flush failed")

        monkeypatch.setattr(goal_service.metrics, "flush", fail_flush)

        with pytest.raises(RuntimeError, match="metrics flush failed"):
            await goal_service.complete_objective(objective.id)

        refreshed = await goal_service.get_objective(objective.id)
        assert refreshed is not None
        assert refreshed.status == GoalStatus.ACTIVE
        assert refreshed.progress_percent == 0

    async def test_complete_objective_rolls_back_when_goal_rollup_fails(
        self,
        goal_service: GoalService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Objective completion should roll back if goal rollup recompute fails."""
        goal = await goal_service.create_goal(name="Atomic Goal")
        objective = await goal_service.create_objective(
            goal_id=goal.id,
            name="Atomic Objective",
        )

        async def _fail_rollup(goal_id: str) -> None:
            raise RuntimeError(f"goal rollup failed for {goal_id}")

        monkeypatch.setattr(goal_service, "_update_goal_rollup", _fail_rollup)

        with pytest.raises(RuntimeError, match="goal rollup failed"):
            await goal_service.complete_objective(objective.id)

        refreshed = await goal_service.get_objective(objective.id)
        assert refreshed is not None
        assert refreshed.status == GoalStatus.ACTIVE
        assert refreshed.progress_percent == 0

    async def test_archive_objective_rolls_back_when_metrics_flush_fails(
        self,
        goal_service: GoalService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Objective archive should roll back if metrics flush fails late."""
        goal = await goal_service.create_goal(name="Atomic Goal")
        objective = await goal_service.create_objective(
            goal_id=goal.id,
            name="Atomic Objective",
        )

        async def fail_flush(*args, **kwargs):
            raise RuntimeError("metrics flush failed")

        monkeypatch.setattr(goal_service.metrics, "flush", fail_flush)

        with pytest.raises(RuntimeError, match="metrics flush failed"):
            await goal_service.archive_objective(objective.id)

        refreshed = await goal_service.get_objective(objective.id)
        assert refreshed is not None
        assert refreshed.status == GoalStatus.ACTIVE

    async def test_archive_objective_rolls_back_when_goal_rollup_fails(
        self,
        goal_service: GoalService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Objective archive should roll back if goal rollup recompute fails."""
        goal = await goal_service.create_goal(name="Atomic Goal")
        objective = await goal_service.create_objective(
            goal_id=goal.id,
            name="Atomic Objective",
        )

        async def _fail_rollup(goal_id: str) -> None:
            raise RuntimeError(f"goal rollup failed for {goal_id}")

        monkeypatch.setattr(goal_service, "_update_goal_rollup", _fail_rollup)

        with pytest.raises(RuntimeError, match="goal rollup failed"):
            await goal_service.archive_objective(objective.id)

        refreshed = await goal_service.get_objective(objective.id)
        assert refreshed is not None
        assert refreshed.status == GoalStatus.ACTIVE

    async def test_create_key_result_rolls_back_when_metrics_flush_fails(
        self,
        goal_service: GoalService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Key-result creation should roll back if metrics flush fails late."""
        goal = await goal_service.create_goal(name="Atomic Goal")
        objective = await goal_service.create_objective(
            goal_id=goal.id,
            name="Atomic Objective",
        )

        async def fail_flush(*args, **kwargs):
            raise RuntimeError("metrics flush failed")

        monkeypatch.setattr(goal_service.metrics, "flush", fail_flush)

        with pytest.raises(RuntimeError, match="metrics flush failed"):
            await goal_service.create_key_result(
                objective_id=objective.id,
                name="Atomic Key Result",
            )

        key_results = await goal_service.list_key_results(objective_id=objective.id)
        assert key_results.total_count == 0

    async def test_create_key_result_rolls_back_when_objective_rollup_fails(
        self,
        goal_service: GoalService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Key-result creation should roll back if objective rollup recompute fails."""
        goal = await goal_service.create_goal(name="Atomic Goal")
        objective = await goal_service.create_objective(
            goal_id=goal.id,
            name="Atomic Objective",
        )

        async def _fail_rollup(objective_id: str) -> None:
            raise RuntimeError(f"objective rollup failed for {objective_id}")

        monkeypatch.setattr(
            goal_service, "_update_objective_rollup_in_transaction", _fail_rollup
        )

        with pytest.raises(RuntimeError, match="objective rollup failed"):
            await goal_service.create_key_result(
                objective_id=objective.id,
                name="Atomic Key Result",
            )

        key_results = await goal_service.list_key_results(objective_id=objective.id)
        assert key_results.total_count == 0

    async def test_update_key_result_rolls_back_when_metrics_flush_fails(
        self,
        goal_service: GoalService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Key-result update should roll back if metrics flush fails late."""
        goal = await goal_service.create_goal(name="Atomic Goal")
        objective = await goal_service.create_objective(
            goal_id=goal.id,
            name="Atomic Objective",
        )
        key_result = await goal_service.create_key_result(
            objective_id=objective.id,
            name="Atomic Key Result",
        )

        async def fail_flush(*args, **kwargs):
            raise RuntimeError("metrics flush failed")

        monkeypatch.setattr(goal_service.metrics, "flush", fail_flush)

        with pytest.raises(RuntimeError, match="metrics flush failed"):
            await goal_service.update_key_result(
                key_result.id,
                description="after",
                status=GoalStatus.ON_HOLD,
                progress_percent=50,
            )

        refreshed = await goal_service.get_key_result(key_result.id)
        assert refreshed is not None
        assert refreshed.description is None
        assert refreshed.status == GoalStatus.ACTIVE
        assert refreshed.progress_percent == 0

    async def test_update_key_result_rolls_back_when_objective_rollup_fails(
        self,
        goal_service: GoalService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Key-result update should roll back if objective rollup recompute fails."""
        goal = await goal_service.create_goal(name="Atomic Goal")
        objective = await goal_service.create_objective(
            goal_id=goal.id,
            name="Atomic Objective",
        )
        key_result = await goal_service.create_key_result(
            objective_id=objective.id,
            name="Atomic Key Result",
        )

        async def _fail_rollup(objective_id: str) -> None:
            raise RuntimeError(f"objective rollup failed for {objective_id}")

        monkeypatch.setattr(
            goal_service, "_update_objective_rollup_in_transaction", _fail_rollup
        )

        with pytest.raises(RuntimeError, match="objective rollup failed"):
            await goal_service.update_key_result(
                key_result.id,
                description="after",
                status=GoalStatus.ON_HOLD,
                progress_percent=50,
            )

        refreshed = await goal_service.get_key_result(key_result.id)
        assert refreshed is not None
        assert refreshed.description is None
        assert refreshed.status == GoalStatus.ACTIVE
        assert refreshed.progress_percent == 0

    async def test_complete_key_result_rolls_back_when_objective_rollup_fails(
        self,
        goal_service: GoalService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Key-result completion should roll back if objective rollup recompute fails."""
        goal = await goal_service.create_goal(name="Atomic Goal")
        objective = await goal_service.create_objective(
            goal_id=goal.id,
            name="Atomic Objective",
        )
        key_result = await goal_service.create_key_result(
            objective_id=objective.id,
            name="Atomic Key Result",
        )

        async def _fail_rollup(objective_id: str) -> None:
            raise RuntimeError(f"objective rollup failed for {objective_id}")

        monkeypatch.setattr(
            goal_service, "_update_objective_rollup_in_transaction", _fail_rollup
        )

        with pytest.raises(RuntimeError, match="objective rollup failed"):
            await goal_service.complete_key_result(key_result.id)

        reloaded_key_result = await goal_service.get_key_result(key_result.id)
        assert reloaded_key_result is not None
        assert reloaded_key_result.status != GoalStatus.COMPLETED

    async def test_complete_key_result_rolls_back_when_metrics_flush_fails(
        self,
        goal_service: GoalService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Key-result completion should roll back if metrics flush fails late."""
        goal = await goal_service.create_goal(name="Atomic Goal")
        objective = await goal_service.create_objective(
            goal_id=goal.id,
            name="Atomic Objective",
        )
        key_result = await goal_service.create_key_result(
            objective_id=objective.id,
            name="Atomic Key Result",
        )

        async def fail_flush(*args, **kwargs):
            raise RuntimeError("metrics flush failed")

        monkeypatch.setattr(goal_service.metrics, "flush", fail_flush)

        with pytest.raises(RuntimeError, match="metrics flush failed"):
            await goal_service.complete_key_result(key_result.id)

        refreshed = await goal_service.get_key_result(key_result.id)
        assert refreshed is not None
        assert refreshed.status == GoalStatus.ACTIVE
        assert refreshed.progress_percent == 0

    async def test_archive_key_result_rolls_back_when_metrics_flush_fails(
        self,
        goal_service: GoalService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Key-result archive should roll back if metrics flush fails late."""
        goal = await goal_service.create_goal(name="Atomic Goal")
        objective = await goal_service.create_objective(
            goal_id=goal.id,
            name="Atomic Objective",
        )
        key_result = await goal_service.create_key_result(
            objective_id=objective.id,
            name="Atomic Key Result",
        )

        async def fail_flush(*args, **kwargs):
            raise RuntimeError("metrics flush failed")

        monkeypatch.setattr(goal_service.metrics, "flush", fail_flush)

        with pytest.raises(RuntimeError, match="metrics flush failed"):
            await goal_service.archive_key_result(key_result.id)

        refreshed = await goal_service.get_key_result(key_result.id)
        assert refreshed is not None
        assert refreshed.status == GoalStatus.ACTIVE

    async def test_archive_key_result_rolls_back_when_objective_rollup_fails(
        self,
        goal_service: GoalService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Key-result archive should roll back if objective rollup recompute fails."""
        goal = await goal_service.create_goal(name="Atomic Goal")
        objective = await goal_service.create_objective(
            goal_id=goal.id,
            name="Atomic Objective",
        )
        key_result = await goal_service.create_key_result(
            objective_id=objective.id,
            name="Atomic Key Result",
        )

        async def _fail_rollup(objective_id: str) -> None:
            raise RuntimeError(f"objective rollup failed for {objective_id}")

        monkeypatch.setattr(
            goal_service, "_update_objective_rollup_in_transaction", _fail_rollup
        )

        with pytest.raises(RuntimeError, match="objective rollup failed"):
            await goal_service.archive_key_result(key_result.id)

        refreshed = await goal_service.get_key_result(key_result.id)
        assert refreshed is not None
        assert refreshed.status == GoalStatus.ACTIVE

    async def test_goal_summary_excludes_archived_objectives_and_key_results(
        self, goal_service: GoalService
    ):
        """Goal summary should report active roadmap counts, not archived totals."""
        goal = await goal_service.create_goal(name="Summary Goal")
        active_objective = await goal_service.create_objective(
            goal_id=goal.id,
            name="Active Objective",
        )
        archived_objective = await goal_service.create_objective(
            goal_id=goal.id,
            name="Archived Objective",
        )

        await goal_service.create_key_result(
            objective_id=active_objective.id,
            name="Active KR",
        )
        archived_key_result = await goal_service.create_key_result(
            objective_id=active_objective.id,
            name="Archived KR",
        )

        archived_repo = goal_service._objective_repo
        archived_key_result_repo = goal_service._key_result_repo
        archived = await archived_repo.archive(archived_objective.id)
        assert archived is not None
        archived_kr = await archived_key_result_repo.archive(archived_key_result.id)
        assert archived_kr is not None

        summary = await goal_service.get_goal_summary(goal.id)

        assert summary is not None
        assert summary.objective_count == 1
        assert summary.key_result_count == 1

    async def test_goal_summary_includes_linked_project_execution(
        self,
        goal_service: GoalService,
        project_service: ProjectService,
        task_service: TaskService,
    ):
        """Goal summary should expose task execution stats for linked projects."""
        project = await project_service.create_project(name="Execution Project")
        goal = await goal_service.create_goal(
            name="Execution Goal",
            project_id=project.id,
        )

        done_task = await task_service.create_task(project.id, "Done Task")
        in_progress_task = await task_service.create_task(
            project.id, "In Progress Task"
        )
        blocked_task = await task_service.create_task(project.id, "Blocked Task")

        await task_service.complete_task(done_task.id, actual_hours=1.0)
        await task_service.start_task(in_progress_task.id)
        await task_service.update_task_progress(
            in_progress_task.id,
            percent_complete=60,
            status_message="Implementing",
            updated_by="tester",
        )
        await task_service.block_task(blocked_task.id, reason="Waiting")
        await task_service.update_task_progress(
            blocked_task.id,
            percent_complete=10,
            status_message="Blocked",
            updated_by="tester",
        )
        from pms.services.plan_service import PlanService

        plan_service = PlanService(
            goal_service.db,
            goal_service.events,
            goal_service.revisions,
            goal_service.metrics,
        )
        await plan_service.create_plan(
            name="Execution Link Plan",
            description=None,
            status=PlanStatus.ACTIVE,
            format=PlanFormat.JSON,
            content={},
            project_id=project.id,
            goal_id=goal.id,
            task_ids=[done_task.id, in_progress_task.id, blocked_task.id],
        )

        summary = await goal_service.get_goal_summary(goal.id)

        assert summary is not None
        assert summary.execution is not None
        assert summary.execution.total_tasks == 3
        assert summary.execution.completed_tasks == 1
        assert summary.execution.in_progress_tasks == 1
        assert summary.execution.blocked_tasks == 1
        assert summary.execution.average_task_progress == 170 / 3
        assert summary.execution.completion_percent == pytest.approx(100 / 3)
        assert summary.execution.readiness_state == "execution_in_progress"
        assert summary.execution.consistency_status == "execution_ahead_of_goal_rollup"
        assert summary.execution.population_basis == "goal_plan_task_graph"
        assert summary.execution.consistency_reason == (
            "linked execution has completed tasks while goal rollups may still lag"
        )
        assert summary.execution.focus_task is not None
        assert summary.execution.focus_task.title == "In Progress Task"
        assert summary.execution.focus_task.status == "in_progress"
        assert summary.execution.focus_task.reason == "active execution in progress"
        assert summary.execution.focus_task.completion_criteria_count == 0
        assert summary.execution.focus_task.has_completion_criteria is False

    async def test_goal_summary_uses_goal_scoped_plan_graph_for_multi_goal_projects(
        self,
        goal_service: GoalService,
        project_service: ProjectService,
        task_service: TaskService,
    ):
        """Explicit goal-linked plans should scope execution even when multiple goals share a project."""
        from pms.services.plan_service import PlanService

        project = await project_service.create_project(
            name="Scoped Goal Execution Project"
        )
        goal_one = await goal_service.create_goal(
            name="Scoped Goal One",
            project_id=project.id,
        )
        goal_two = await goal_service.create_goal(
            name="Scoped Goal Two",
            project_id=project.id,
        )

        goal_one_task = await task_service.create_task(project.id, "Goal One Task")
        goal_two_task = await task_service.create_task(project.id, "Goal Two Task")
        await task_service.start_task(goal_one_task.id)
        await task_service.update_task_progress(
            goal_one_task.id,
            percent_complete=55,
            status_message="Working goal one",
            updated_by="tester",
        )
        await task_service.start_task(goal_two_task.id)
        await task_service.update_task_progress(
            goal_two_task.id,
            percent_complete=20,
            status_message="Working goal two",
            updated_by="tester",
        )

        plan_service = PlanService(
            goal_service.db,
            goal_service.events,
            goal_service.revisions,
            goal_service.metrics,
        )
        await plan_service.create_plan(
            name="Goal One Execution Plan",
            description=None,
            status=PlanStatus.ACTIVE,
            format=PlanFormat.JSON,
            content={},
            project_id=project.id,
            goal_id=goal_one.id,
            task_ids=[goal_one_task.id],
        )
        await plan_service.create_plan(
            name="Goal Two Execution Plan",
            description=None,
            status=PlanStatus.ACTIVE,
            format=PlanFormat.JSON,
            content={},
            project_id=project.id,
            goal_id=goal_two.id,
            task_ids=[goal_two_task.id],
        )

        summary = await goal_service.get_goal_summary(goal_one.id)

        assert summary is not None
        assert summary.execution is not None
        assert summary.execution.population_basis == "goal_plan_task_graph"
        assert summary.execution.scoped_goal_count == 2
        assert summary.execution.total_tasks == 1
        assert summary.execution.in_progress_tasks == 1
        assert summary.execution.focus_task is not None
        assert summary.execution.focus_task.title == "Goal One Task"
        assert summary.execution.readiness_state == "execution_in_progress"
        assert summary.execution.consistency_status == "execution_ahead_of_goal_rollup"
        assert summary.effective_rollup.basis == "execution_projection"
        assert summary.effective_rollup.progress_percent == 55

    async def test_goal_summary_focus_prefers_todo_over_blocked(
        self,
        goal_service: GoalService,
        project_service: ProjectService,
        task_service: TaskService,
    ):
        """Goal summary should prefer actionable todo tasks over blocked ones."""
        project = await project_service.create_project(name="Focus Priority Project")
        goal = await goal_service.create_goal(
            name="Focus Priority Goal",
            project_id=project.id,
        )

        blocked_task = await task_service.create_task(project.id, "Blocked First")
        await task_service.block_task(blocked_task.id, reason="Waiting")
        await task_service.create_task(project.id, "Todo Second")

        summary = await goal_service.get_goal_summary(goal.id)

        assert summary is not None
        assert summary.execution is not None
        assert summary.execution.focus_task is not None
        assert summary.execution.focus_task.title == "Todo Second"
        assert summary.execution.focus_task.status == "todo"
        assert summary.execution.focus_task.reason == "next ready work to start"

    async def test_goal_summary_focus_prefers_newer_todo_when_rank_ties(
        self,
        goal_service: GoalService,
        project_service: ProjectService,
        task_service: TaskService,
    ):
        """Goal summary should prefer the most recently activated todo task."""
        project = await project_service.create_project(name="Tie Break Goal Project")
        goal = await goal_service.create_goal(
            name="Tie Break Goal",
            project_id=project.id,
        )

        await task_service.create_task(project.id, "Older Todo")
        await task_service.create_task(project.id, "Newer Todo")

        summary = await goal_service.get_goal_summary(goal.id)

        assert summary is not None
        assert summary.execution is not None
        assert summary.execution.focus_task is not None
        assert summary.execution.focus_task.title == "Newer Todo"
        assert summary.execution.focus_task.status == "todo"

    async def test_goal_summary_focus_handles_string_updated_at_values(
        self,
        goal_service: GoalService,
        project_service: ProjectService,
        task_service: TaskService,
    ):
        """Goal focus sorting should tolerate string timestamps from loaded task rows."""
        project = await project_service.create_project(name="String Timestamp Project")
        goal = await goal_service.create_goal(
            name="String Timestamp Goal",
            project_id=project.id,
        )

        older_task = await task_service.create_task(project.id, "Older Todo")
        newer_task = await task_service.create_task(project.id, "Newer Todo")

        older_task.updated_at = "2026-04-04T10:00:00+00:00"
        newer_task.updated_at = "2026-04-04T11:00:00+00:00"

        original_get_by_project = goal_service._task_repo.get_by_project

        async def _get_tasks_with_string_timestamps(*args, **kwargs):
            result = await original_get_by_project(*args, **kwargs)
            return result.__class__(
                items=[older_task, newer_task],
                total_count=2,
                offset=result.offset,
                limit=result.limit,
            )

        goal_service._task_repo.get_by_project = _get_tasks_with_string_timestamps  # type: ignore[method-assign]
        try:
            summary = await goal_service.get_goal_summary(goal.id)
        finally:
            goal_service._task_repo.get_by_project = original_get_by_project  # type: ignore[method-assign]

        assert summary is not None
        assert summary.execution is not None
        assert summary.execution.focus_task is not None
        assert summary.execution.focus_task.title == "Newer Todo"

    async def test_goal_summary_skips_task_reopened_by_stale_progress_race(
        self,
        goal_service: GoalService,
        project_service: ProjectService,
        task_service: TaskService,
    ):
        """Goal summary should stay focused on actionable work after progress/complete races."""
        project = await project_service.create_project(name="Race Focus Project")
        goal = await goal_service.create_goal(
            name="Race Focus Goal",
            project_id=project.id,
        )

        raced_task = await task_service.create_task(project.id, "Raced Task")
        ready_task = await task_service.create_task(project.id, "Ready Follow-Up")
        await task_service.start_task(raced_task.id)

        await asyncio.gather(
            task_service.update_task_progress(
                raced_task.id,
                percent_complete=100,
                status_message="Late progress update",
                updated_by="tester",
            ),
            task_service.complete_task(raced_task.id, actual_hours=1.0),
        )

        refreshed = await task_service.get_task(raced_task.id)
        assert refreshed is not None
        assert refreshed.status == TaskStatus.DONE
        assert refreshed.current_progress_percent == 100

        summary = await goal_service.get_goal_summary(goal.id)

        assert summary is not None
        assert summary.execution is not None
        assert summary.execution.completed_tasks == 1
        assert summary.execution.in_progress_tasks == 0
        assert summary.execution.focus_task is not None
        assert summary.execution.focus_task.title == "Ready Follow-Up"
        assert summary.execution.focus_task.status == "todo"

    async def test_goal_summary_surfaces_execution_truth_when_goal_progress_lags(
        self,
        goal_service: GoalService,
        project_service: ProjectService,
        task_service: TaskService,
    ):
        """Goal summary should expose execution-derived readiness when raw goal progress is stale."""
        project = await project_service.create_project(name="Execution Truth Project")
        goal = await goal_service.create_goal(
            name="Execution Truth Goal",
            project_id=project.id,
        )
        task = await task_service.create_task(project.id, "Execution Truth Task")

        await task_service.start_task(task.id)
        await task_service.update_task_progress(
            task.id,
            percent_complete=45,
            status_message="Implementing",
            updated_by="tester",
        )

        summary = await goal_service.get_goal_summary(goal.id)

        assert summary is not None
        assert summary.goal.progress_percent == 0
        assert summary.execution is not None
        assert summary.execution.average_task_progress == 45
        assert summary.execution.completion_percent == 0
        assert summary.effective_rollup.progress_percent == 45
        assert summary.effective_rollup.status == GoalStatus.ACTIVE.value
        assert summary.effective_rollup.basis == "execution_projection"
        assert summary.effective_hierarchy.average_progress == 45
        assert summary.effective_hierarchy.basis == "execution_projection"
        assert summary.execution.readiness_state == "execution_in_progress"
        assert summary.execution.consistency_status == "execution_ahead_of_goal_rollup"
        assert summary.execution.consistency_reason == (
            "linked execution is progressing while goal rollups may still lag"
        )

    async def test_goal_summary_marks_project_scoped_execution_ambiguous_for_multi_goal_projects(
        self,
        goal_service: GoalService,
        project_service: ProjectService,
        task_service: TaskService,
    ):
        """Goal execution summaries should require explicit links in multi-goal projects."""
        project = await project_service.create_project(name="Ambiguous Goal Project")
        goal_one = await goal_service.create_goal(
            name="Ambiguous Goal One",
            project_id=project.id,
        )
        await goal_service.create_goal(
            name="Ambiguous Goal Two",
            project_id=project.id,
        )
        task = await task_service.create_task(project.id, "Shared Execution Task")
        await task_service.start_task(task.id)
        await task_service.update_task_progress(
            task.id,
            percent_complete=35,
            status_message="Working",
            updated_by="tester",
        )

        summary = await goal_service.get_goal_summary(goal_one.id)

        assert summary is not None
        assert summary.execution is not None
        assert (
            summary.execution.population_basis == "goal_scope_requires_explicit_links"
        )
        assert summary.execution.scoped_goal_count == 2
        assert summary.execution.total_tasks == 0
        assert summary.execution.focus_task is None
        assert summary.execution.readiness_state == "execution_scope_unlinked"
        assert summary.execution.consistency_status == "unlinked_goal_execution_scope"
        assert summary.execution.consistency_reason == (
            "project has 2 retained goals; link tasks through goal/objective plans to claim execution"
        )
        assert summary.effective_rollup.basis == "stored_goal"
        assert summary.effective_rollup.progress_percent == 0

    async def test_goal_summary_has_no_focus_when_all_execution_tasks_are_terminal(
        self,
        goal_service: GoalService,
        project_service: ProjectService,
        task_service: TaskService,
    ):
        """Completed execution should report a terminal state instead of a stale focus task."""
        project = await project_service.create_project(name="Terminal Goal Project")
        goal = await goal_service.create_goal(
            name="Terminal Goal",
            project_id=project.id,
        )

        done_task = await task_service.create_task(project.id, "Done Task")
        cancelled_task = await task_service.create_task(project.id, "Cancelled Task")
        await task_service.complete_task(done_task.id, actual_hours=1.0)
        await task_service.cancel_task(cancelled_task.id)

        summary = await goal_service.get_goal_summary(goal.id)

        assert summary is not None
        assert summary.execution is not None
        assert summary.execution.completed_tasks == 1
        assert summary.execution.completion_percent == 50
        assert summary.execution.readiness_state == "execution_complete"
        assert summary.execution.consistency_status == "execution_terminal"
        assert summary.execution.consistency_reason == (
            "all linked execution tasks are already terminal"
        )
        assert summary.effective_rollup.progress_percent == 100
        assert summary.effective_rollup.status == GoalStatus.COMPLETED.value
        assert summary.effective_rollup.basis == "execution_terminal"
        assert summary.effective_hierarchy.average_progress == 100
        assert summary.effective_hierarchy.basis == "execution_terminal"
        assert summary.execution.focus_task is None
        assert summary.execution.terminal_reason == (
            "all execution tasks are already complete"
        )

    async def test_execution_only_goal_auto_completes_when_project_tasks_finish(
        self,
        goal_service: GoalService,
        project_service: ProjectService,
        task_service: TaskService,
    ):
        """Execution-only goals should complete when all linked project tasks are terminal."""
        project = await project_service.create_project(
            name="Execution Only Goal Project"
        )
        goal = await goal_service.create_goal(
            name="Execution Only Goal",
            project_id=project.id,
        )

        task = await task_service.create_task(project.id, "Execution Task")
        await task_service.complete_task(task.id, actual_hours=1.0)

        refreshed_goal = await goal_service.get_goal(goal.id)

        assert refreshed_goal is not None
        assert refreshed_goal.status == GoalStatus.COMPLETED
        assert refreshed_goal.progress_percent == 100

    async def test_execution_only_goal_reopens_when_new_project_task_is_created(
        self,
        goal_service: GoalService,
        project_service: ProjectService,
        task_service: TaskService,
    ):
        """Execution-only goals should reopen if new project work appears after terminal execution."""
        project = await project_service.create_project(
            name="Reopen Execution Goal Project"
        )
        goal = await goal_service.create_goal(
            name="Reopen Execution Goal",
            project_id=project.id,
        )

        first_task = await task_service.create_task(
            project.id, "Initial Execution Task"
        )
        await task_service.complete_task(first_task.id, actual_hours=1.0)

        completed_goal = await goal_service.get_goal(goal.id)
        assert completed_goal is not None
        assert completed_goal.status == GoalStatus.COMPLETED

        await task_service.create_task(project.id, "New Execution Task")

        reopened_goal = await goal_service.get_goal(goal.id)

        assert reopened_goal is not None
        assert reopened_goal.status == GoalStatus.ACTIVE
        assert reopened_goal.progress_percent == 0

    async def test_new_project_task_auto_links_into_active_plan_lineage(
        self,
        project_service: ProjectService,
        task_service: TaskService,
        plan_service: PlanService,
    ):
        """New tasks should be appended into active plans for the same project."""
        project = await project_service.create_project(name="Plan Link Project")
        plan = await plan_service.create_plan(
            name="Active Delivery Plan",
            description=None,
            status=PlanStatus.ACTIVE,
            format=PlanFormat.JSON,
            content={"summary": "Active delivery"},
            project_id=project.id,
        )

        task = await task_service.create_task(project.id, "Linked Task")

        refreshed_plan = await plan_service.get_plan(plan.id)

        assert refreshed_plan is not None
        assert task.id in refreshed_plan.task_ids

    async def test_new_project_task_does_not_auto_link_into_draft_plan(
        self,
        project_service: ProjectService,
        task_service: TaskService,
        plan_service: PlanService,
    ):
        """Draft plans should not receive implicit execution-task linkage."""
        project = await project_service.create_project(name="Draft Plan Link Project")
        plan = await plan_service.create_plan(
            name="Draft Delivery Plan",
            description=None,
            status=PlanStatus.DRAFT,
            format=PlanFormat.JSON,
            content={"summary": "Draft delivery"},
            project_id=project.id,
        )

        task = await task_service.create_task(project.id, "Unlinked Task")

        refreshed_plan = await plan_service.get_plan(plan.id)

        assert refreshed_plan is not None
        assert task.id not in refreshed_plan.task_ids

    async def test_new_project_task_does_not_fan_out_into_multiple_active_plans(
        self,
        project_service: ProjectService,
        task_service: TaskService,
        plan_service: PlanService,
    ):
        """New task linkage is ambiguous when a project has multiple active plans."""
        project = await project_service.create_project(
            name="Ambiguous Active Plan Link Project"
        )
        first_plan = await plan_service.create_plan(
            name="First Active Plan",
            description=None,
            status=PlanStatus.ACTIVE,
            format=PlanFormat.JSON,
            content={"summary": "first"},
            project_id=project.id,
        )
        second_plan = await plan_service.create_plan(
            name="Second Active Plan",
            description=None,
            status=PlanStatus.ACTIVE,
            format=PlanFormat.JSON,
            content={"summary": "second"},
            project_id=project.id,
        )

        task = await task_service.create_task(project.id, "Ambiguous Follow-up")

        refreshed_first = await plan_service.get_plan(first_plan.id)
        refreshed_second = await plan_service.get_plan(second_plan.id)

        assert refreshed_first is not None
        assert refreshed_second is not None
        assert task.id not in refreshed_first.task_ids
        assert task.id not in refreshed_second.task_ids

    async def test_metadata_update_race_preserves_started_task_status(
        self,
        project_service: ProjectService,
        db: Database,
        event_store: EventStore,
        revision_store: RevisionStore,
    ) -> None:
        """Metadata-only updates must not revert a concurrently started task to todo."""
        project = await project_service.create_project(name="Metadata Race Project")
        task_service = TaskService(
            db,
            event_store,
            revision_store,
            MetricsCollector(db),
        )
        start_service = TaskService(
            db,
            event_store,
            revision_store,
            MetricsCollector(db),
        )
        update_service = TaskService(
            db,
            event_store,
            revision_store,
            MetricsCollector(db),
        )
        task = await task_service.create_task(project.id, "Metadata Race Task")

        await asyncio.gather(
            start_service.start_task(task.id),
            update_service.update_task(
                task.id,
                completion_criteria=["Preserve started status during metadata updates"],
            ),
        )

        refreshed = await task_service.get_task(task.id)
        assert refreshed is not None
        assert refreshed.status == TaskStatus.IN_PROGRESS
        assert refreshed.workflow_metadata["completion_criteria"] == [
            "Preserve started status during metadata updates"
        ]


@pytest.mark.asyncio
class TestPlanService:
    """Tests for PlanService."""

    async def test_create_plan(self, plan_service: PlanService):
        """Test creating a plan through service."""
        plan = await plan_service.create_plan(
            name="Service Plan",
            description="Created via service",
            status=PlanStatus.DRAFT,
            format=PlanFormat.JSON,
            content={"steps": []},
        )

        assert plan.id is not None
        assert plan.name == "Service Plan"
        assert plan.status == PlanStatus.DRAFT
        assert plan.format == PlanFormat.JSON
        assert "steps" in plan.content

    async def test_create_plan_rolls_back_when_metrics_flush_fails(
        self,
        plan_service: PlanService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Create should roll back if metrics flush fails after the repo write."""

        async def fail_flush(*args, **kwargs):
            raise RuntimeError("metrics flush failed")

        monkeypatch.setattr(plan_service.metrics, "flush", fail_flush)

        with pytest.raises(RuntimeError, match="metrics flush failed"):
            await plan_service.create_plan(
                name="Atomic Plan",
                description="Should roll back",
                status=PlanStatus.DRAFT,
                format=PlanFormat.JSON,
                content={"steps": []},
            )

        assert await plan_service.get_plan_by_name("Atomic Plan") is None

    async def test_list_plans(self, plan_service: PlanService):
        """Test listing plans."""
        await plan_service.create_plan(
            name="Plan A",
            description=None,
            status=PlanStatus.DRAFT,
            format=PlanFormat.JSON,
            content={},
        )
        await plan_service.create_plan(
            name="Plan B",
            description=None,
            status=PlanStatus.DRAFT,
            format=PlanFormat.JSON,
            content={},
        )

        result = await plan_service.list_plans()

        assert result.total_count >= 2
        names = [p.name for p in result.items]
        assert "Plan A" in names
        assert "Plan B" in names

    async def test_draft_plan_lifecycle_rollup_stays_draft_for_active_project_scope(
        self,
        plan_service: PlanService,
        project_service: ProjectService,
    ) -> None:
        """Draft plans should not be auto-promoted by linked active project scope."""
        project = await project_service.create_project(name="Draft Lifecycle Project")
        plan = await plan_service.create_plan(
            name="Draft Lifecycle Plan",
            description=None,
            status=PlanStatus.DRAFT,
            format=PlanFormat.JSON,
            content={},
            project_id=project.id,
        )

        rollup = (await plan_service.get_lifecycle_rollup_map([plan]))[plan.id]

        assert rollup.effective_status == PlanStatus.DRAFT
        assert rollup.terminal_reason is None

    async def test_get_last_activity_map_includes_linked_project_updates(
        self,
        db: Database,
        plan_service: PlanService,
        project_service: ProjectService,
    ) -> None:
        """Plan last-activity rollups should include directly linked project updates."""
        project = await project_service.create_project(name="Plan Activity Project")
        plan = await plan_service.create_plan(
            name="Project-linked Plan",
            description=None,
            status=PlanStatus.ACTIVE,
            format=PlanFormat.JSON,
            content={},
            project_id=project.id,
        )
        older = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        newer = datetime.now(UTC).isoformat()
        await db.execute(
            "UPDATE plans SET updated_at = ? WHERE id = ?",
            (older, plan.id),
        )
        await db.execute(
            "UPDATE projects SET updated_at = ? WHERE id = ?",
            (newer, project.id),
        )

        refreshed = await plan_service.get_plan(plan.id)
        assert refreshed is not None
        activity_map = await plan_service.get_last_activity_map([refreshed])

        assert activity_map[plan.id] is not None
        assert activity_map[plan.id] == datetime.fromisoformat(newer)

    async def test_create_completed_plan_reconciles_plan_only_project_to_completed(
        self,
        plan_service: PlanService,
        project_service: ProjectService,
    ) -> None:
        """Plan-only terminal execution should complete the linked project."""
        project = await project_service.create_project(
            name="Plan Only Completed Project"
        )

        await plan_service.create_plan(
            name="Plan Only Completed Plan",
            description=None,
            status=PlanStatus.COMPLETED,
            format=PlanFormat.JSON,
            content={},
            project_id=project.id,
        )

        refreshed = await project_service.get_project(project.id)
        assert refreshed is not None
        assert refreshed.status == ProjectStatus.COMPLETED

    async def test_update_plan_to_draft_does_not_reopen_completed_project_by_itself(
        self,
        plan_service: PlanService,
        project_service: ProjectService,
    ) -> None:
        """A draft-only plan should not resurrect an otherwise terminal project."""
        project = await project_service.create_project(name="Plan Only Reopen Project")
        plan = await plan_service.create_plan(
            name="Plan Only Reopen Plan",
            description=None,
            status=PlanStatus.COMPLETED,
            format=PlanFormat.JSON,
            content={},
            project_id=project.id,
        )

        await plan_service.update_plan(plan.id, status=PlanStatus.DRAFT)

        refreshed = await project_service.get_project(project.id)
        assert refreshed is not None
        assert refreshed.status == ProjectStatus.COMPLETED

    async def test_complete_goal_reconciles_goal_only_project_to_completed(
        self,
        goal_service: GoalService,
        project_service: ProjectService,
    ) -> None:
        """Goal-only terminal execution should complete the linked project."""
        project = await project_service.create_project(
            name="Goal Only Completed Project"
        )
        goal = await goal_service.create_goal(
            name="Goal Only Goal",
            project_id=project.id,
        )

        await goal_service.complete_goal(goal.id)

        refreshed = await project_service.get_project(project.id)
        assert refreshed is not None
        assert refreshed.status == ProjectStatus.COMPLETED

    async def test_get_last_activity_map_includes_project_scoped_task_activity(
        self,
        plan_service: PlanService,
        project_service: ProjectService,
        task_service: TaskService,
    ) -> None:
        """Plan activity should inherit nested project execution without direct task links."""
        project = await project_service.create_project(
            name="Project Scoped Plan Activity"
        )
        plan = await plan_service.create_plan(
            name="Project Scoped Plan",
            description=None,
            status=PlanStatus.ACTIVE,
            format=PlanFormat.JSON,
            content={},
            project_id=project.id,
        )
        task = await task_service.create_task(project.id, "Project Scoped Task")

        await task_service.update_task_progress(
            task.id,
            percent_complete=40,
            status_message="Scoped execution moved",
            updated_by="tester",
        )

        refreshed = await plan_service.get_plan(plan.id)
        refreshed_task = await task_service.get_task(task.id)
        assert refreshed is not None
        assert refreshed_task is not None

        activity_map = await plan_service.get_last_activity_map([refreshed])

        assert activity_map[plan.id] == refreshed_task.updated_at

    async def test_task_scoped_plan_activity_does_not_inherit_sibling_project_activity(
        self,
        db: Database,
        plan_service: PlanService,
        project_service: ProjectService,
        task_service: TaskService,
    ) -> None:
        """Explicit task links should isolate plan recency from sibling plans."""
        project = await project_service.create_project(
            name="Task Scoped Activity Isolation"
        )
        first_task = await task_service.create_task(project.id, "Fresh Plan Task")
        second_task = await task_service.create_task(project.id, "Quiet Plan Task")
        first_plan = await plan_service.create_plan(
            name="Fresh Task Plan",
            description=None,
            status=PlanStatus.ACTIVE,
            format=PlanFormat.JSON,
            content={},
            project_id=project.id,
            task_ids=[first_task.id],
        )
        second_plan = await plan_service.create_plan(
            name="Quiet Task Plan",
            description=None,
            status=PlanStatus.ACTIVE,
            format=PlanFormat.JSON,
            content={},
            project_id=project.id,
            task_ids=[second_task.id],
        )
        base = datetime.now(UTC) + timedelta(hours=1)
        quiet_ts = base.isoformat()
        fresh_ts = (base + timedelta(hours=1)).isoformat()
        await db.execute(
            "UPDATE tasks SET updated_at = ? WHERE id = ?",
            (fresh_ts, first_task.id),
        )
        await db.execute(
            "UPDATE tasks SET updated_at = ? WHERE id = ?",
            (quiet_ts, second_task.id),
        )
        await db.execute(
            """
            UPDATE state_transition_log
            SET timestamp = ?, created_at = ?
            WHERE entity_type = 'task_status' AND entity_id = ?
            """,
            (fresh_ts, fresh_ts, first_task.id),
        )
        await db.execute(
            """
            UPDATE state_transition_log
            SET timestamp = ?, created_at = ?
            WHERE entity_type = 'task_status' AND entity_id = ?
            """,
            (quiet_ts, quiet_ts, second_task.id),
        )

        refreshed_first = await plan_service.get_plan(first_plan.id)
        refreshed_second = await plan_service.get_plan(second_plan.id)
        assert refreshed_first is not None
        assert refreshed_second is not None

        activity_map = await plan_service.get_last_activity_map(
            [refreshed_first, refreshed_second]
        )
        transition_map = await plan_service.get_last_transition_map(
            [first_plan.id, second_plan.id]
        )

        assert activity_map[first_plan.id] == datetime.fromisoformat(fresh_ts)
        assert activity_map[second_plan.id] == datetime.fromisoformat(quiet_ts)
        assert transition_map[first_plan.id] == datetime.fromisoformat(fresh_ts)
        assert transition_map[second_plan.id] == datetime.fromisoformat(quiet_ts)

    async def test_legacy_multi_plan_auto_links_do_not_drive_plan_recency(
        self,
        db: Database,
        plan_service: PlanService,
        project_service: ProjectService,
        task_service: TaskService,
    ) -> None:
        """Old fan-out auto-links should not make every active plan look fresh."""
        from pms.services.plan_service import AUTO_LINK_PLAN_TASK_MESSAGE

        project = await project_service.create_project(
            name="Legacy Auto Link Activity Project"
        )
        task = await task_service.create_task(
            project.id, "Legacy Shared Auto Link Task"
        )
        first_plan = await plan_service.create_plan(
            name="Legacy Auto Link First",
            description=None,
            status=PlanStatus.ACTIVE,
            format=PlanFormat.JSON,
            content={},
            project_id=project.id,
        )
        second_plan = await plan_service.create_plan(
            name="Legacy Auto Link Second",
            description=None,
            status=PlanStatus.ACTIVE,
            format=PlanFormat.JSON,
            content={},
            project_id=project.id,
        )
        await plan_service.update_plan(
            first_plan.id,
            task_ids=[task.id],
            message=AUTO_LINK_PLAN_TASK_MESSAGE,
        )
        await plan_service.update_plan(
            second_plan.id,
            task_ids=[task.id],
            message=AUTO_LINK_PLAN_TASK_MESSAGE,
        )
        fresh_ts = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
        await db.execute(
            "UPDATE tasks SET updated_at = ? WHERE id = ?",
            (fresh_ts, task.id),
        )
        await db.execute(
            """
            UPDATE state_transition_log
            SET timestamp = ?, created_at = ?
            WHERE entity_type = 'task_status' AND entity_id = ?
            """,
            (fresh_ts, fresh_ts, task.id),
        )

        refreshed_first = await plan_service.get_plan(first_plan.id)
        refreshed_second = await plan_service.get_plan(second_plan.id)
        assert refreshed_first is not None
        assert refreshed_second is not None

        activity_map = await plan_service.get_last_activity_map(
            [refreshed_first, refreshed_second]
        )
        transition_map = await plan_service.get_last_transition_map(
            [first_plan.id, second_plan.id]
        )

        assert activity_map[first_plan.id] != datetime.fromisoformat(fresh_ts)
        assert activity_map[second_plan.id] != datetime.fromisoformat(fresh_ts)
        assert transition_map[first_plan.id] != datetime.fromisoformat(fresh_ts)
        assert transition_map[second_plan.id] != datetime.fromisoformat(fresh_ts)

    async def test_get_last_activity_map_includes_project_comment_activity(
        self,
        db: Database,
        plan_service: PlanService,
        project_service: ProjectService,
    ) -> None:
        """Plan activity should inherit direct project activity, not just task rows."""
        from pms.services.comment_service import CommentService

        project = await project_service.create_project(
            name="Plan Project Comment Rollup"
        )
        plan = await plan_service.create_plan(
            name="Project Comment Plan",
            description=None,
            status=PlanStatus.ACTIVE,
            format=PlanFormat.JSON,
            content={},
            project_id=project.id,
        )
        comment_service = CommentService(db, MetricsCollector(db))
        item = await comment_service.add_comment(
            entity_type="project",
            entity_id=project.id,
            body="Project discussion",
            created_by="tester",
        )

        refreshed = await plan_service.get_plan(plan.id)
        assert refreshed is not None

        activity_map = await plan_service.get_last_activity_map([refreshed])

        assert activity_map[plan.id] == item.comment.updated_at

    async def test_get_last_activity_map_includes_linked_product_comment_activity(
        self,
        db: Database,
        plan_service: PlanService,
        product_service: ProductService,
    ) -> None:
        """Plan activity should include direct activity on linked products."""
        from pms.services.comment_service import CommentService

        product = await product_service.create_product(name="Plan Product Activity")
        plan = await plan_service.create_plan(
            name="Product Activity Plan",
            description=None,
            status=PlanStatus.ACTIVE,
            format=PlanFormat.JSON,
            content={},
            product_id=product.id,
        )
        comment_service = CommentService(db, MetricsCollector(db))
        item = await comment_service.add_comment(
            entity_type="product",
            entity_id=product.id,
            body="Product note",
            created_by="tester",
        )

        refreshed = await plan_service.get_plan(plan.id)
        assert refreshed is not None

        activity_map = await plan_service.get_last_activity_map([refreshed])

        assert activity_map[plan.id] == item.comment.updated_at

    async def test_get_last_transition_map_includes_project_goal_transition(
        self,
        plan_service: PlanService,
        project_service: ProjectService,
        goal_service: GoalService,
    ) -> None:
        """Plan transitions should bubble up nested linked-project goal changes."""
        project = await project_service.create_project(name="Plan Transition Project")
        plan = await plan_service.create_plan(
            name="Plan Transition Rollup",
            description=None,
            status=PlanStatus.ACTIVE,
            format=PlanFormat.JSON,
            content={},
            project_id=project.id,
        )
        goal = await goal_service.create_goal(
            name="Plan Transition Goal",
            project_id=project.id,
        )

        await goal_service.update_goal(
            goal.id,
            status=GoalStatus.ON_HOLD,
            progress_percent=15,
        )

        transition_map = await plan_service.get_last_transition_map([plan.id])
        goal_transition_map = await goal_service.get_last_transition_map([goal.id])

        assert transition_map[plan.id] == goal_transition_map[goal.id]

    async def test_update_plan(self, plan_service: PlanService):
        """Test updating a plan."""
        plan = await plan_service.create_plan(
            name="Update Plan",
            description=None,
            status=PlanStatus.DRAFT,
            format=PlanFormat.JSON,
            content={},
        )

        updated = await plan_service.update_plan(
            plan_id=plan.id,
            status=PlanStatus.ACTIVE,
            content={"stage": "active"},
        )

        assert updated is not None
        assert updated.status == PlanStatus.ACTIVE

    async def test_upsert_quickstart_plan_archives_duplicate_live_plans(
        self,
        plan_service: PlanService,
        project_service: ProjectService,
    ):
        """Quickstart upsert should keep one live canonical plan and archive duplicates."""
        project = await project_service.create_project(name="Quickstart Atomic Project")
        first = await plan_service.create_plan(
            name="Quickstart Atomic Plan",
            description="Quickstart plan",
            status=PlanStatus.DRAFT,
            format=PlanFormat.JSON,
            content={"summary": "Starter plan generated by quickstart.", "seed": 1},
            project_id=project.id,
            tags=["generated", "quickstart"],
        )
        second = await plan_service.create_plan(
            name="Quickstart Atomic Plan",
            description="Quickstart plan",
            status=PlanStatus.DRAFT,
            format=PlanFormat.JSON,
            content={"summary": "Starter plan generated by quickstart.", "seed": 2},
            project_id=project.id,
            tags=["generated", "quickstart"],
        )

        result = await plan_service.upsert_quickstart_plan(
            name="Quickstart Atomic Plan",
            description="Quickstart plan",
            status=PlanStatus.ACTIVE,
            format=PlanFormat.JSON,
            content={
                "summary": "Starter plan generated by quickstart.",
                "steps": ["bootstrap"],
            },
            product_id=None,
            project_id=project.id,
            task_ids=None,
        )

        refreshed_first = await plan_service.get_plan(first.id)
        refreshed_second = await plan_service.get_plan(second.id)
        assert refreshed_first is not None
        assert refreshed_second is not None

        live_plans = [
            plan
            for plan in (refreshed_first, refreshed_second)
            if plan.status != PlanStatus.ARCHIVED
        ]

        assert result.reused_existing is True
        assert len(live_plans) == 1
        assert live_plans[0].id == result.plan.id
        assert live_plans[0].status == PlanStatus.ACTIVE
        assert set(result.archived_duplicate_plan_ids) == {
            first.id,
            second.id,
        } - {result.plan.id}

    async def test_upsert_quickstart_plan_rolls_back_when_duplicate_archive_fails(
        self,
        plan_service: PlanService,
        project_service: ProjectService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Quickstart upsert should roll back the canonical update if duplicate cleanup fails."""
        project = await project_service.create_project(
            name="Quickstart Atomic Rollback Project"
        )
        first = await plan_service.create_plan(
            name="Quickstart Rollback Plan",
            description="Quickstart plan",
            status=PlanStatus.DRAFT,
            format=PlanFormat.JSON,
            content={"summary": "Starter plan generated by quickstart.", "seed": 1},
            project_id=project.id,
            tags=["generated", "quickstart"],
        )
        second = await plan_service.create_plan(
            name="Quickstart Rollback Plan",
            description="Quickstart plan",
            status=PlanStatus.DRAFT,
            format=PlanFormat.JSON,
            content={"summary": "Starter plan generated by quickstart.", "seed": 2},
            project_id=project.id,
            tags=["generated", "quickstart"],
        )

        original_update = plan_service._plan_repo.update
        update_calls = 0

        async def fail_on_duplicate_archive(*args, **kwargs):
            nonlocal update_calls
            update_calls += 1
            if update_calls == 2:
                raise RuntimeError("duplicate archive failed")
            return await original_update(*args, **kwargs)

        monkeypatch.setattr(
            plan_service._plan_repo,
            "update",
            fail_on_duplicate_archive,
        )

        with pytest.raises(RuntimeError, match="duplicate archive failed"):
            await plan_service.upsert_quickstart_plan(
                name="Quickstart Rollback Plan",
                description="Quickstart plan",
                status=PlanStatus.ACTIVE,
                format=PlanFormat.JSON,
                content={
                    "summary": "Starter plan generated by quickstart.",
                    "steps": ["bootstrap"],
                },
                product_id=None,
                project_id=project.id,
                task_ids=None,
            )

        refreshed_first = await plan_service.get_plan(first.id)
        refreshed_second = await plan_service.get_plan(second.id)
        assert refreshed_first is not None
        assert refreshed_second is not None
        assert refreshed_first.status == PlanStatus.DRAFT
        assert refreshed_second.status == PlanStatus.DRAFT
        assert refreshed_first.content != refreshed_second.content


@pytest.mark.asyncio
class TestSavedSearchService:
    """Tests for SavedSearchService."""

    async def test_create_saved_search_rolls_back_when_metrics_flush_fails(
        self,
        saved_search_service: SavedSearchService,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Create should roll back if metrics flush fails after the repo write."""

        async def fail_flush(*args, **kwargs):
            raise RuntimeError("metrics flush failed")

        monkeypatch.setattr(saved_search_service.metrics, "flush", fail_flush)

        with pytest.raises(RuntimeError, match="metrics flush failed"):
            await saved_search_service.create(
                name="Atomic Saved Search",
                filters={"tags": ["backend"]},
            )

        assert await saved_search_service.get_by_name("Atomic Saved Search") is None

    async def test_update_saved_search_rolls_back_when_metrics_flush_fails(
        self,
        saved_search_service: SavedSearchService,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Update should roll back if metrics flush fails after the repo write."""
        saved = await saved_search_service.create(
            name="Atomic Queue",
            filters={"tags": ["backend"]},
        )

        async def fail_flush(*args, **kwargs):
            raise RuntimeError("metrics flush failed")

        monkeypatch.setattr(saved_search_service.metrics, "flush", fail_flush)

        with pytest.raises(RuntimeError, match="metrics flush failed"):
            await saved_search_service.update(
                saved.id,
                name="Updated Atomic Queue",
            )

        refreshed = await saved_search_service.get(saved.id)
        assert refreshed is not None
        assert refreshed.name == "Atomic Queue"

    async def test_delete_saved_search_rolls_back_when_metrics_flush_fails(
        self,
        saved_search_service: SavedSearchService,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Delete should roll back if metrics flush fails after archive write."""
        saved = await saved_search_service.create(
            name="Atomic Delete Queue",
            filters={"tags": ["backend"]},
        )

        async def fail_flush(*args, **kwargs):
            raise RuntimeError("metrics flush failed")

        monkeypatch.setattr(saved_search_service.metrics, "flush", fail_flush)

        with pytest.raises(RuntimeError, match="metrics flush failed"):
            await saved_search_service.delete(saved.id)

        refreshed = await saved_search_service.get(saved.id)
        assert refreshed is not None
        assert refreshed.archived_at is None

    async def test_restore_saved_search_rolls_back_when_metrics_flush_fails(
        self,
        saved_search_service: SavedSearchService,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Restore should roll back if metrics flush fails after unarchive write."""
        saved = await saved_search_service.create(
            name="Atomic Restore Queue",
            filters={"tags": ["backend"]},
        )
        assert await saved_search_service.delete(saved.id) is True
        assert await saved_search_service.get(saved.id) is None

        async def fail_flush(*args, **kwargs):
            raise RuntimeError("metrics flush failed")

        monkeypatch.setattr(saved_search_service.metrics, "flush", fail_flush)

        with pytest.raises(RuntimeError, match="metrics flush failed"):
            await saved_search_service.restore(saved.id)

        assert await saved_search_service.get(saved.id) is None
        archived = await saved_search_service.get_by_name(
            "Atomic Restore Queue",
            include_archived=True,
        )
        assert archived is not None
        assert archived.archived_at is not None

    async def test_run_saved_search_ignores_observational_metrics_flush_failures(
        self,
        saved_search_service: SavedSearchService,
        project_service: ProjectService,
        task_service: TaskService,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Saved-search execution should still return results if telemetry fails."""
        project = await project_service.create_project(name="Saved Search Run Project")
        task = await task_service.create_task(project.id, "Backend queue task")
        saved = await saved_search_service.create(
            name="Backend Queue",
            filters={"project_id": project.id, "query": "Backend"},
        )

        async def fail_flush(*args, **kwargs):
            raise RuntimeError("metrics flush failed")

        monkeypatch.setattr(saved_search_service.metrics, "flush", fail_flush)

        run = await saved_search_service.run(saved.id)

        assert run is not None
        assert run.saved_search.id == saved.id
        assert run.result.total_count == 1
        assert run.result.items[0].id == task.id

    async def test_find_duplicate_tasks_ignores_observational_metrics_flush_failures(
        self,
        task_service: TaskService,
        project_service: ProjectService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Duplicate detection should still return results if telemetry fails."""
        project = await project_service.create_project(name="Duplicate Search Project")
        primary = await task_service.create_task(project.id, "Duplicate Task")
        duplicate = await task_service.create_task(project.id, "Duplicate Task")

        async def fail_flush(*args, **kwargs):
            raise RuntimeError("metrics flush failed")

        monkeypatch.setattr(task_service.metrics, "flush", fail_flush)

        result = await task_service.find_duplicate_tasks(project_id=project.id)
        preview = await task_service.preview_merge_duplicate_tasks(
            primary_task_id=primary.id,
            duplicate_task_ids=[duplicate.id],
        )

        assert result.total_count == 1
        assert preview is not None
        assert preview.primary_task.id == primary.id

    async def test_search_tasks_ignores_observational_metrics_flush_failures(
        self,
        task_service: TaskService,
        project_service: ProjectService,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Task search should still return results if telemetry fails."""
        project = await project_service.create_project(name="Task Search Project")
        first = await task_service.create_task(project.id, "Backend search task")
        second = await task_service.create_task(project.id, "Backend queue task")

        async def fail_flush(*args, **kwargs):
            raise RuntimeError("metrics flush failed")

        monkeypatch.setattr(task_service.metrics, "flush", fail_flush)

        result = await task_service.search_tasks(
            project_id=project.id,
            query="Backend",
        )

        assert result.total_count == 2
        assert {item.id for item in result.items} == {first.id, second.id}

    async def test_list_ready_and_stale_tasks_ignore_observational_metrics_flush_failures(
        self,
        db: Database,
        task_service: TaskService,
        project_service: ProjectService,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Ready/stale readbacks should still return results if telemetry fails."""
        project = await project_service.create_project(name="Task Queue Project")
        ready = await task_service.create_task(project.id, "Ready task")
        stale = await task_service.create_task(project.id, "Stale task")
        stale_timestamp = (datetime.now(UTC) - timedelta(days=30)).isoformat()
        await db.execute(
            "UPDATE tasks SET updated_at = ? WHERE id = ?",
            (stale_timestamp, stale.id),
        )

        async def fail_flush(*args, **kwargs):
            raise RuntimeError("metrics flush failed")

        monkeypatch.setattr(task_service.metrics, "flush", fail_flush)

        ready_result = await task_service.list_ready_tasks(project_id=project.id)
        stale_result = await task_service.list_stale_tasks(
            project_id=project.id,
            stale_after_days=14,
        )

        assert ready_result.total_count == 2
        assert {item.id for item in ready_result.items} == {ready.id, stale.id}
        assert stale_result.total_count == 1
        assert stale_result.items[0].id == stale.id

    async def test_update_plan_rolls_back_when_metrics_flush_fails(
        self,
        plan_service: PlanService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Update should roll back if metrics flush fails after the repo write."""
        plan = await plan_service.create_plan(
            name="Atomic Update Plan",
            description=None,
            status=PlanStatus.DRAFT,
            format=PlanFormat.JSON,
            content={},
        )

        async def fail_flush(*args, **kwargs):
            raise RuntimeError("metrics flush failed")

        monkeypatch.setattr(plan_service.metrics, "flush", fail_flush)

        with pytest.raises(RuntimeError, match="metrics flush failed"):
            await plan_service.update_plan(
                plan_id=plan.id,
                status=PlanStatus.ACTIVE,
                content={"stage": "active"},
            )

        refreshed = await plan_service.get_plan(plan.id)
        assert refreshed is not None
        assert refreshed.status == PlanStatus.DRAFT
        assert refreshed.content == "{}"


@pytest.mark.asyncio
class TestPlanningLifecycleInvariants:
    """Lifecycle and reconciliation invariants between tasks, plans, and projects."""

    async def test_draft_plan_blocks_task_execution(
        self,
        project_service: ProjectService,
        task_service: TaskService,
        plan_service: PlanService,
    ):
        project = await project_service.create_project(name="Draft Locked Project")
        task = await task_service.create_task(project.id, "Locked Task")
        await plan_service.create_plan(
            name="Draft Locked Plan",
            description=None,
            status=PlanStatus.DRAFT,
            format=PlanFormat.JSON,
            content={"steps": ["wait"]},
            project_id=project.id,
            task_ids=[task.id],
        )

        with pytest.raises(ValueError, match="draft"):
            await task_service.start_task(task.id)

    async def test_task_completion_reconciles_plan_and_project_to_completed(
        self,
        project_service: ProjectService,
        task_service: TaskService,
        plan_service: PlanService,
        goal_service: GoalService,
    ):
        project = await project_service.create_project(
            name="Reconcile Complete Project"
        )
        goal = await goal_service.create_goal(
            name="Complete Goal",
            project_id=project.id,
        )
        task = await task_service.create_task(project.id, "Finish Work")
        plan = await plan_service.create_plan(
            name="Completion Plan",
            description=None,
            status=PlanStatus.ACTIVE,
            format=PlanFormat.JSON,
            content={"steps": ["do work"]},
            project_id=project.id,
            goal_id=goal.id,
            task_ids=[task.id],
        )

        await goal_service.complete_goal(goal.id)
        await task_service.start_task(task.id)
        await task_service.complete_task(task.id)

        refreshed_plan = await plan_service.get_plan(plan.id)
        refreshed_project = await project_service.get_project(project.id)

        assert refreshed_plan is not None
        assert refreshed_plan.status == PlanStatus.COMPLETED
        assert refreshed_project is not None
        assert refreshed_project.status == ProjectStatus.COMPLETED

    async def test_terminal_plan_completes_even_if_goal_rollup_lags(
        self,
        project_service: ProjectService,
        task_service: TaskService,
        plan_service: PlanService,
        goal_service: GoalService,
    ):
        project = await project_service.create_project(name="Lagging Goal Plan Project")
        goal = await goal_service.create_goal(
            name="Lagging Goal",
            project_id=project.id,
        )
        task = await task_service.create_task(project.id, "Finish Plan Work")
        plan = await plan_service.create_plan(
            name="Lagging Goal Plan",
            description=None,
            status=PlanStatus.ACTIVE,
            format=PlanFormat.JSON,
            content={"steps": ["finish work"]},
            project_id=project.id,
            goal_id=goal.id,
            task_ids=[task.id],
        )

        await task_service.start_task(task.id)
        await task_service.complete_task(task.id)

        refreshed_plan = await plan_service.get_plan(plan.id)
        refreshed_goal = await goal_service.get_goal(goal.id)

        assert refreshed_plan is not None
        assert refreshed_plan.status == PlanStatus.COMPLETED
        assert refreshed_goal is not None
        assert refreshed_goal.status == GoalStatus.COMPLETED

    async def test_reopening_completed_task_reactivates_plan_and_project(
        self,
        project_service: ProjectService,
        task_service: TaskService,
        plan_service: PlanService,
        goal_service: GoalService,
    ):
        project = await project_service.create_project(name="Reopen Project")
        goal = await goal_service.create_goal(
            name="Reopen Goal",
            project_id=project.id,
        )
        task = await task_service.create_task(project.id, "Reopen Task")
        plan = await plan_service.create_plan(
            name="Reopen Plan",
            description=None,
            status=PlanStatus.ACTIVE,
            format=PlanFormat.JSON,
            content={"steps": ["ship"]},
            project_id=project.id,
            goal_id=goal.id,
            task_ids=[task.id],
        )

        await goal_service.complete_goal(goal.id)
        await task_service.start_task(task.id)
        await task_service.complete_task(task.id)
        await task_service.reopen_task(task.id)

        refreshed_plan = await plan_service.get_plan(plan.id)
        refreshed_project = await project_service.get_project(project.id)

        assert refreshed_plan is not None
        assert refreshed_plan.status == PlanStatus.ACTIVE
        assert refreshed_project is not None
        assert refreshed_project.status == ProjectStatus.ACTIVE


@pytest.mark.asyncio
class TestLineageService:
    """Tests for LineageService."""

    async def test_plan_lineage_dashboard(
        self,
        lineage_service: LineageService,
        plan_service: PlanService,
        project_service: ProjectService,
        task_service: TaskService,
        db: Database,
    ):
        """Test plan lineage dashboard linking tasks and test runs."""
        from pms.core.metrics import MetricsCollector
        from pms.services.task_evidence_service import TaskEvidenceService

        project = await project_service.create_project(name="Lineage Project")
        task_one = await task_service.create_task(project.id, "Task One")
        task_two = await task_service.create_task(project.id, "Task Two")
        await task_service.block_task(task_two.id, reason="Waiting on dependency")

        plan = await plan_service.create_plan(
            name="Lineage Plan",
            description="Plan for lineage tests",
            status=PlanStatus.ACTIVE,
            format=PlanFormat.JSON,
            content={"steps": ["plan", "implement", "test"]},
            project_id=project.id,
            task_ids=[task_one.id, task_two.id],
        )

        now = datetime.now()
        await db.execute(
            """
            INSERT INTO test_servers (
                id, instance_id, name, project_id, config, public_ip, private_ip,
                state, region, availability_zone, hourly_price, estimated_cost,
                launched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "server-1",
                "i-123",
                "test-server",
                project.id,
                "{}",
                "127.0.0.1",
                "127.0.0.1",
                "running",
                "us-east-1",
                "us-east-1a",
                0.0,
                0.0,
                now.isoformat(),
            ),
        )

        await db.execute(
            """
            INSERT INTO test_runs (
                id, server_id, project_id, config, success, exit_code,
                stdout, stderr, duration_seconds, started_at, finished_at, logs, artifacts
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "run-1",
                "server-1",
                project.id,
                json.dumps(
                    {
                        "plan_id": plan.id,
                        "task_ids": [task_one.id, task_two.id],
                        "test_command": "pytest -q",
                    }
                ),
                1,
                0,
                "ok",
                "",
                4.2,
                now.isoformat(),
                now.isoformat(),
                "{}",
                "{}",
            ),
        )
        await db.commit()

        evidence_service = TaskEvidenceService(db, MetricsCollector(db))
        await evidence_service.add_evidence(
            task_id=task_one.id,
            evidence_type="scm_commit",
            reference="abc123",
            description="Commit evidence",
            created_by="tester",
        )

        dashboard = await lineage_service.get_plan_lineage_dashboard(
            project_id=project.id
        )

        assert dashboard.total_plans >= 1
        assert dashboard.total_tasks >= 2
        assert dashboard.total_test_runs >= 1

        item = next(
            (entry for entry in dashboard.items if entry.plan.id == plan.id), None
        )
        assert item is not None
        assert item.total_tasks == 2
        assert item.blocked_tasks == 1
        assert item.latest_test_success is True
        assert item.evidence.total == 1
        assert item.evidence.code_total == 1

    async def test_plan_lineage_dashboard_bubbles_nested_goal_transition(
        self,
        lineage_service: LineageService,
        plan_service: PlanService,
        project_service: ProjectService,
        goal_service: GoalService,
    ) -> None:
        """Lineage should use the deep plan transition rollup, not raw plan status only."""
        project = await project_service.create_project(
            name="Lineage Transition Project"
        )
        goal = await goal_service.create_goal(
            name="Lineage Transition Goal",
            project_id=project.id,
        )
        plan = await plan_service.create_plan(
            name="Lineage Transition Plan",
            description="Plan for transition rollup lineage coverage",
            status=PlanStatus.DRAFT,
            format=PlanFormat.JSON,
            content={"steps": ["audit", "bubble", "validate"]},
            project_id=project.id,
        )

        await goal_service.update_goal(
            goal.id,
            status=GoalStatus.ON_HOLD,
            progress_percent=10,
        )

        dashboard = await lineage_service.get_plan_lineage_dashboard(
            project_id=project.id,
        )
        item = next(entry for entry in dashboard.items if entry.plan.id == plan.id)
        plan_transition_map = await plan_service.get_last_transition_map([plan.id])

        assert item.last_transition_at == plan_transition_map[plan.id]


@pytest.mark.asyncio
class TestTaskService:
    """Tests for TaskService."""

    async def test_create_task(
        self,
        task_service: TaskService,
        project_service: ProjectService,
    ):
        """Test creating a task through service."""
        project = await project_service.create_project(name="Task Service Project")

        task = await task_service.create_task(
            project_id=project.id,
            title="Service Test Task",
            description="Created via service",
            priority=Priority.HIGH,
            complexity_points=40,
        )

        assert task.id is not None
        assert task.title == "Service Test Task"
        assert task.priority == Priority.HIGH
        assert task.complexity_points == 40

    async def test_create_task_rolls_back_when_project_reconcile_fails(
        self,
        task_service: TaskService,
        project_service: ProjectService,
        plan_service: PlanService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Create should roll back task and plan-link side effects on late failure."""
        project = await project_service.create_project(name="Create Rollback Project")
        plan = await plan_service.create_plan(
            name="Auto Link Plan",
            description=None,
            status=PlanStatus.ACTIVE,
            format=PlanFormat.JSON,
            content={"steps": ["do work"]},
            project_id=project.id,
        )

        async def fail_reconcile(*args, **kwargs):
            raise RuntimeError("project reconcile failed")

        monkeypatch.setattr(
            task_service,
            "_reconcile_project_execution_state",
            fail_reconcile,
        )

        with pytest.raises(RuntimeError, match="project reconcile failed"):
            await task_service.create_task(project.id, "Task That Rolls Back")

        result = await task_service.list_tasks(project_id=project.id)
        assert result.total_count == 0

        refreshed_plan = await plan_service.get_plan(plan.id)
        assert refreshed_plan is not None
        assert refreshed_plan.task_ids == ()

    async def test_start_task(
        self,
        task_service: TaskService,
        project_service: ProjectService,
    ):
        """Test starting a task."""
        project = await project_service.create_project(name="Start Task Project")
        task = await task_service.create_task(project.id, "Task to Start")

        started = await task_service.start_task(task.id)

        assert started is not None
        assert started.status == TaskStatus.IN_PROGRESS

    async def test_start_task_rolls_back_when_reconcile_fails(
        self,
        task_service: TaskService,
        project_service: ProjectService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Start should roll back if later execution reconciliation fails."""
        project = await project_service.create_project(name="Start Rollback Project")
        task = await task_service.create_task(project.id, "Task to Start")

        async def fail_reconcile(*args, **kwargs):
            raise RuntimeError("execution reconcile failed")

        monkeypatch.setattr(
            task_service,
            "_reconcile_linked_execution_state",
            fail_reconcile,
        )

        with pytest.raises(RuntimeError, match="execution reconcile failed"):
            await task_service.start_task(task.id)

        refreshed = await task_service.get_task(task.id)
        assert refreshed is not None
        assert refreshed.status == TaskStatus.TODO

    async def test_complete_task(
        self,
        task_service: TaskService,
        project_service: ProjectService,
    ):
        """Test completing a task."""
        project = await project_service.create_project(name="Complete Task Project")
        task = await task_service.create_task(project.id, "Task to Complete")

        completed = await task_service.complete_task(
            task.id,
            notes="Done",
            actual_hours=4.5,
        )

        assert completed is not None
        assert completed.status == TaskStatus.DONE
        assert completed.actual_hours == 4.5

    async def test_complete_task_with_effects_rolls_back_when_reconcile_fails(
        self,
        task_service: TaskService,
        project_service: ProjectService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Completion should roll back if later execution reconciliation fails."""
        project = await project_service.create_project(
            name="Completion Rollback Project"
        )
        task = await task_service.create_task(project.id, "Task to Complete")

        async def fail_reconcile(*args, **kwargs):
            raise RuntimeError("execution reconcile failed")

        monkeypatch.setattr(
            task_service,
            "_reconcile_linked_execution_state",
            fail_reconcile,
        )

        with pytest.raises(RuntimeError, match="execution reconcile failed"):
            await task_service.complete_task_with_effects(task.id)

        refreshed = await task_service.get_task(task.id)
        assert refreshed is not None
        assert refreshed.status == TaskStatus.TODO

    async def test_block_and_unblock_task(
        self,
        task_service: TaskService,
        project_service: ProjectService,
    ):
        """Test blocking and unblocking tasks."""
        project = await project_service.create_project(name="Block Task Project")
        task = await task_service.create_task(project.id, "Task to Block")

        blocked = await task_service.block_task(task.id, "Waiting for approval")
        assert blocked is not None
        assert blocked.status == TaskStatus.BLOCKED

        unblocked = await task_service.unblock_task(task.id)
        assert unblocked is not None
        assert unblocked.status == TaskStatus.TODO

    async def test_block_task_rolls_back_when_reconcile_fails(
        self,
        task_service: TaskService,
        project_service: ProjectService,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Block should roll back if later execution reconciliation fails."""
        project = await project_service.create_project(name="Block Rollback Project")
        task = await task_service.create_task(project.id, "Task to Block")

        async def fail_reconcile(*args, **kwargs):
            raise RuntimeError("execution reconcile failed")

        monkeypatch.setattr(
            task_service,
            "_reconcile_linked_execution_state",
            fail_reconcile,
        )

        with pytest.raises(RuntimeError, match="execution reconcile failed"):
            await task_service.block_task(task.id, "Waiting on review")

        refreshed = await task_service.get_task(task.id)
        assert refreshed is not None
        assert refreshed.status == TaskStatus.TODO

    async def test_unblock_task_rolls_back_when_reconcile_fails(
        self,
        task_service: TaskService,
        project_service: ProjectService,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Unblock should roll back if later execution reconciliation fails."""
        project = await project_service.create_project(name="Unblock Rollback Project")
        task = await task_service.create_task(project.id, "Task to Unblock")
        await task_service.block_task(task.id, "Waiting on review")

        async def fail_reconcile(*args, **kwargs):
            raise RuntimeError("execution reconcile failed")

        monkeypatch.setattr(
            task_service,
            "_reconcile_linked_execution_state",
            fail_reconcile,
        )

        with pytest.raises(RuntimeError, match="execution reconcile failed"):
            await task_service.unblock_task(task.id)

        refreshed = await task_service.get_task(task.id)
        assert refreshed is not None
        assert refreshed.status == TaskStatus.BLOCKED

    async def test_update_task(
        self,
        task_service: TaskService,
        project_service: ProjectService,
    ):
        """Test updating task fields."""
        project = await project_service.create_project(name="Update Task Project")
        task = await task_service.create_task(
            project.id,
            "Task to Update",
        )

        updated = await task_service.update_task(
            task.id,
            title="Updated Task Title",
            description="New description",
            priority=Priority.CRITICAL,
        )

        assert updated is not None
        assert updated.title == "Updated Task Title"
        assert updated.description == "New description"
        assert updated.priority == Priority.CRITICAL

    async def test_update_task_rolls_back_when_metrics_flush_fails(
        self,
        task_service: TaskService,
        project_service: ProjectService,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Task field updates should roll back on late metrics failure."""
        project = await project_service.create_project(
            name="Update Task Rollback Project"
        )
        task = await task_service.create_task(
            project.id,
            "Task to Roll Back",
            description="Original description",
            priority=Priority.HIGH,
        )

        async def fail_flush(*args, **kwargs):
            raise RuntimeError("metrics flush failed")

        monkeypatch.setattr(task_service.metrics, "flush", fail_flush)

        with pytest.raises(RuntimeError, match="metrics flush failed"):
            await task_service.update_task(
                task.id,
                title="Updated Task Title",
                description="New description",
                priority=Priority.CRITICAL,
            )

        refreshed = await task_service.get_task(task.id)
        assert refreshed is not None
        assert refreshed.title == "Task to Roll Back"
        assert refreshed.description == "Original description"
        assert refreshed.priority == Priority.HIGH

    async def test_cancel_task(
        self,
        task_service: TaskService,
        project_service: ProjectService,
    ):
        """Test cancelling a task."""
        project = await project_service.create_project(name="Cancel Task Project")
        task = await task_service.create_task(project.id, "Task to Cancel")

        cancelled = await task_service.cancel_task(task.id)

        assert cancelled is not None
        assert cancelled.status == TaskStatus.CANCELLED

    async def test_cancel_task_rolls_back_when_reconcile_fails(
        self,
        task_service: TaskService,
        project_service: ProjectService,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Cancel should roll back if later execution reconciliation fails."""
        project = await project_service.create_project(name="Cancel Rollback Project")
        task = await task_service.create_task(project.id, "Task to Cancel")

        async def fail_reconcile(*args, **kwargs):
            raise RuntimeError("execution reconcile failed")

        monkeypatch.setattr(
            task_service,
            "_reconcile_linked_execution_state",
            fail_reconcile,
        )

        with pytest.raises(RuntimeError, match="execution reconcile failed"):
            await task_service.cancel_task(task.id)

        refreshed = await task_service.get_task(task.id)
        assert refreshed is not None
        assert refreshed.status == TaskStatus.TODO

    async def test_find_and_merge_duplicates(
        self,
        task_service: TaskService,
        project_service: ProjectService,
    ):
        """Test duplicate detection and merge workflow."""
        project = await project_service.create_project(name="Duplicate Project")
        primary = await task_service.create_task(project.id, "Duplicate Task")
        dup_one = await task_service.create_task(project.id, "Duplicate Task")
        dup_two = await task_service.create_task(project.id, "Duplicate Task")

        result = await task_service.find_duplicate_tasks(project_id=project.id)

        assert result.total_count == 1
        group = result.items[0]
        assert group.normalized_title == "duplicate task"
        assert group.count == 3
        assert group.suggested_primary_id in {primary.id, dup_one.id, dup_two.id}
        assert group.suggested_primary_reason

        preview = await task_service.preview_merge_duplicate_tasks(
            primary_task_id=primary.id,
            duplicate_task_ids=[dup_one.id, dup_two.id],
        )

        assert preview is not None
        assert preview.primary_task.id == primary.id
        assert len(preview.duplicates) == 2
        assert preview.can_merge is True

        merged = await task_service.merge_duplicate_tasks(
            primary_task_id=primary.id,
            duplicate_task_ids=[dup_one.id, dup_two.id],
            cancel_duplicates=True,
        )

        assert merged is not None
        assert merged.links_added == 2
        assert merged.duplicates_cancelled == 2

        dup_one_context = await task_service.get_task_with_context(dup_one.id)
        assert dup_one_context is not None
        assert any(
            dep.dependency_type == DependencyType.DUPLICATES
            and dep.depends_on_id == primary.id
            for dep in dup_one_context.dependencies
        )

        dup_one_updated = await task_service.get_task(dup_one.id)
        dup_two_updated = await task_service.get_task(dup_two.id)
        assert dup_one_updated is not None
        assert dup_two_updated is not None
        assert dup_one_updated.status == TaskStatus.CANCELLED
        assert dup_two_updated.status == TaskStatus.CANCELLED

    async def test_merge_duplicate_tasks_rolls_back_when_late_cancel_fails(
        self,
        task_service: TaskService,
        project_service: ProjectService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Merge should roll back earlier duplicate changes if a later cancel fails."""
        project = await project_service.create_project(
            name="Duplicate Rollback Project"
        )
        primary = await task_service.create_task(project.id, "Duplicate Task")
        dup_one = await task_service.create_task(project.id, "Duplicate Task")
        dup_two = await task_service.create_task(project.id, "Duplicate Task")

        original_update_status = task_service._task_repo.update_status
        call_count = 0

        async def fail_on_second_cancel(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("duplicate cancel failed")
            return await original_update_status(*args, **kwargs)

        monkeypatch.setattr(
            task_service._task_repo,
            "update_status",
            fail_on_second_cancel,
        )

        with pytest.raises(RuntimeError, match="duplicate cancel failed"):
            await task_service.merge_duplicate_tasks(
                primary_task_id=primary.id,
                duplicate_task_ids=[dup_one.id, dup_two.id],
                cancel_duplicates=True,
            )

        dup_one_context = await task_service.get_task_with_context(dup_one.id)
        dup_two_context = await task_service.get_task_with_context(dup_two.id)
        assert dup_one_context is not None
        assert dup_two_context is not None
        assert not any(
            dep.dependency_type == DependencyType.DUPLICATES
            and dep.depends_on_id == primary.id
            for dep in dup_one_context.dependencies
        )
        assert not any(
            dep.dependency_type == DependencyType.DUPLICATES
            and dep.depends_on_id == primary.id
            for dep in dup_two_context.dependencies
        )

        dup_one_updated = await task_service.get_task(dup_one.id)
        dup_two_updated = await task_service.get_task(dup_two.id)
        assert dup_one_updated is not None
        assert dup_two_updated is not None
        assert dup_one_updated.status == TaskStatus.TODO
        assert dup_two_updated.status == TaskStatus.TODO

    async def test_submit_for_review(
        self,
        task_service: TaskService,
        project_service: ProjectService,
    ):
        """Test submitting task for review."""
        project = await project_service.create_project(name="Review Task Project")
        task = await task_service.create_task(project.id, "Task for Review")

        await task_service.start_task(task.id)
        in_review = await task_service.submit_for_review(task.id)

        assert in_review is not None
        assert in_review.status == TaskStatus.IN_REVIEW

    async def test_submit_for_review_rolls_back_when_reconcile_fails(
        self,
        task_service: TaskService,
        project_service: ProjectService,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Review submission should roll back if reconciliation fails late."""
        project = await project_service.create_project(name="Review Rollback Project")
        task = await task_service.create_task(project.id, "Task for Review")
        await task_service.start_task(task.id)

        async def fail_reconcile(*args, **kwargs):
            raise RuntimeError("execution reconcile failed")

        monkeypatch.setattr(
            task_service,
            "_reconcile_linked_execution_state",
            fail_reconcile,
        )

        with pytest.raises(RuntimeError, match="execution reconcile failed"):
            await task_service.submit_for_review(task.id)

        refreshed = await task_service.get_task(task.id)
        assert refreshed is not None
        assert refreshed.status == TaskStatus.IN_PROGRESS

    async def test_reopen_task_rolls_back_when_reconcile_fails(
        self,
        task_service: TaskService,
        project_service: ProjectService,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Reopen should roll back if later execution reconciliation fails."""
        project = await project_service.create_project(name="Reopen Rollback Project")
        task = await task_service.create_task(project.id, "Task to Reopen")
        await task_service.complete_task(task.id)

        async def fail_reconcile(*args, **kwargs):
            raise RuntimeError("execution reconcile failed")

        monkeypatch.setattr(
            task_service,
            "_reconcile_linked_execution_state",
            fail_reconcile,
        )

        with pytest.raises(RuntimeError, match="execution reconcile failed"):
            await task_service.reopen_task(task.id)

        refreshed = await task_service.get_task(task.id)
        assert refreshed is not None
        assert refreshed.status == TaskStatus.DONE

    async def test_add_dependency(
        self,
        task_service: TaskService,
        project_service: ProjectService,
    ):
        """Test adding task dependencies."""
        project = await project_service.create_project(name="Dependency Project")
        task1 = await task_service.create_task(project.id, "Prerequisite Task")
        task2 = await task_service.create_task(project.id, "Dependent Task")

        dep = await task_service.add_dependency(task2.id, task1.id)

        assert dep is not None
        assert dep.task_id == task2.id
        assert dep.depends_on_id == task1.id

    async def test_add_dependency_unblocks_stale_blocked_task_when_blocker_done(
        self,
        task_service: TaskService,
        project_service: ProjectService,
    ):
        """Adding a completed blocker should clear stale blocked status."""
        project = await project_service.create_project(
            name="Dependency Reconcile Project"
        )
        blocker = await task_service.create_task(project.id, "Completed Blocker")
        dependent = await task_service.create_task(
            project.id, "Previously Blocked Dependent"
        )

        await task_service.block_task(dependent.id, "Waiting on finished blocker")
        await task_service.complete_task(blocker.id)

        dep = await task_service.add_dependency(dependent.id, blocker.id)
        refreshed = await task_service.get_task(dependent.id)

        assert dep is not None
        assert refreshed is not None
        assert refreshed.status == TaskStatus.TODO

    async def test_add_dependency_rolls_back_when_block_step_fails(
        self,
        task_service: TaskService,
        project_service: ProjectService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Dependency add should roll back if late auto-block logic fails."""
        project = await project_service.create_project(name="Add Dep Rollback Project")
        blocker = await task_service.create_task(project.id, "Blocking Task")
        dependent = await task_service.create_task(project.id, "Dependent Task")

        async def fail_block(*args, **kwargs):
            raise RuntimeError("block transition failed")

        monkeypatch.setattr(task_service, "block_task", fail_block)

        with pytest.raises(RuntimeError, match="block transition failed"):
            await task_service.add_dependency(dependent.id, blocker.id)

        dependencies = await task_service._task_repo.get_dependencies(dependent.id)
        refreshed = await task_service.get_task(dependent.id)

        assert dependencies == []
        assert refreshed is not None
        assert refreshed.status == TaskStatus.TODO

    async def test_add_dependency_rolls_back_when_unblock_reconciliation_fails(
        self,
        task_service: TaskService,
        project_service: ProjectService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Dependency add should roll back if stale-unblock reconciliation fails."""
        project = await project_service.create_project(
            name="Add Dep Unblock Rollback Project"
        )
        blocker = await task_service.create_task(project.id, "Completed Blocker")
        dependent = await task_service.create_task(project.id, "Blocked Dependent")

        await task_service.block_task(dependent.id, "Waiting on finished blocker")
        await task_service.complete_task(blocker.id)

        async def fail_unblock(*args, **kwargs):
            raise RuntimeError("unblock reconciliation failed")

        monkeypatch.setattr(task_service, "_check_unblock_task", fail_unblock)

        with pytest.raises(RuntimeError, match="unblock reconciliation failed"):
            await task_service.add_dependency(dependent.id, blocker.id)

        dependencies = await task_service._task_repo.get_dependencies(dependent.id)
        refreshed = await task_service.get_task(dependent.id)

        assert dependencies == []
        assert refreshed is not None
        assert refreshed.status == TaskStatus.BLOCKED

    async def test_update_task_progress_rolls_back_when_reconcile_fails(
        self,
        task_service: TaskService,
        project_service: ProjectService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Progress updates should roll back if later execution reconciliation fails."""
        project = await project_service.create_project(name="Progress Rollback Project")
        task = await task_service.create_task(project.id, "Task With Progress")

        async def fail_reconcile(*args, **kwargs):
            raise RuntimeError("execution reconcile failed")

        monkeypatch.setattr(
            task_service,
            "_reconcile_linked_execution_state",
            fail_reconcile,
        )

        with pytest.raises(RuntimeError, match="execution reconcile failed"):
            await task_service.update_task_progress(
                task.id,
                percent_complete=60,
                status_message="Working",
                updated_by="tester",
            )

        refreshed = await task_service.get_task(task.id)
        assert refreshed is not None
        assert refreshed.status == TaskStatus.TODO
        assert refreshed.current_progress_percent == 0

        progress_repo = ProgressRepository(task_service.db)
        timeline = await progress_repo.get_timeline(task.id)
        assert timeline.updates == []

    async def test_complete_task_auto_unblocks_dependency_blocked_task(
        self,
        task_service: TaskService,
        project_service: ProjectService,
    ):
        """Completing the final blocker should automatically unblock the dependent."""
        project = await project_service.create_project(
            name="Dependency Auto Unblock Project"
        )
        blocker = await task_service.create_task(project.id, "Blocker")
        dependent = await task_service.create_task(project.id, "Dependent")

        await task_service.add_dependency(dependent.id, blocker.id)
        blocked = await task_service.get_task(dependent.id)
        assert blocked is not None
        assert blocked.status == TaskStatus.BLOCKED

        await task_service.complete_task(blocker.id)
        refreshed = await task_service.get_task(dependent.id)

        assert refreshed is not None
        assert refreshed.status == TaskStatus.TODO

    async def test_complete_task_with_effects_returns_newly_unblocked_dependents(
        self,
        task_service: TaskService,
        project_service: ProjectService,
    ):
        """Completion effects should surface newly unblocked dependent tasks."""
        project = await project_service.create_project(
            name="Dependency Completion Result Project"
        )
        blocker = await task_service.create_task(project.id, "Completion Blocker")
        dependent = await task_service.create_task(project.id, "Completion Dependent")

        await task_service.add_dependency(dependent.id, blocker.id)

        completion = await task_service.complete_task_with_effects(blocker.id)

        assert completion is not None
        assert completion.task.status == TaskStatus.DONE
        assert [task.id for task in completion.newly_unblocked_tasks] == [dependent.id]
        assert completion.newly_unblocked_tasks[0].status == TaskStatus.TODO

    async def test_complete_task_with_effects_skips_draft_locked_dependents(
        self,
        task_service: TaskService,
        project_service: ProjectService,
        plan_service: PlanService,
    ):
        """Completion should not fail when a dependent remains locked by a draft plan."""
        project = await project_service.create_project(
            name="Dependency Draft-Locked Completion Project"
        )
        blocker = await task_service.create_task(project.id, "Draft-Locked Blocker")
        dependent = await task_service.create_task(project.id, "Draft-Locked Dependent")

        await task_service.add_dependency(dependent.id, blocker.id)
        await plan_service.create_plan(
            name="Draft-Locked Dependent Plan",
            description=None,
            status=PlanStatus.DRAFT,
            format=PlanFormat.JSON,
            content={"steps": []},
            project_id=project.id,
            task_ids=[dependent.id],
        )

        completion = await task_service.complete_task_with_effects(blocker.id)
        refreshed = await task_service.get_task(dependent.id)

        assert completion is not None
        assert completion.task.status == TaskStatus.DONE
        assert completion.newly_unblocked_tasks == []
        assert refreshed is not None
        assert refreshed.status == TaskStatus.BLOCKED

    async def test_remove_dependency(
        self,
        task_service: TaskService,
        project_service: ProjectService,
    ):
        """Test removing task dependencies."""
        project = await project_service.create_project(name="Remove Dep Project")
        task1 = await task_service.create_task(project.id, "Prereq")
        task2 = await task_service.create_task(project.id, "Dependent")

        await task_service.add_dependency(task2.id, task1.id)
        removed = await task_service.remove_dependency(task2.id, task1.id)

        assert removed is True

    async def test_remove_dependency_rolls_back_when_unblock_step_fails(
        self,
        task_service: TaskService,
        project_service: ProjectService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Service dependency removal should roll back if later logic fails."""
        project = await project_service.create_project(
            name="Remove Dep Rollback Project"
        )
        blocker = await task_service.create_task(project.id, "Prereq")
        dependent = await task_service.create_task(project.id, "Dependent")

        await task_service.add_dependency(dependent.id, blocker.id)

        async def fail_unblock(*args, **kwargs):
            raise RuntimeError("unblock reconciliation failed")

        monkeypatch.setattr(task_service, "_check_unblock_task", fail_unblock)

        with pytest.raises(RuntimeError, match="unblock reconciliation failed"):
            await task_service.remove_dependency(dependent.id, blocker.id)

        dependencies = await task_service._task_repo.get_dependencies(dependent.id)
        assert len(dependencies) == 1
        assert dependencies[0].depends_on_id == blocker.id

    async def test_get_task_tree(
        self,
        task_service: TaskService,
        project_service: ProjectService,
    ):
        """Test getting task tree structure."""
        project = await project_service.create_project(name="Tree Project")
        parent = await task_service.create_task(project.id, "Parent Task")
        await task_service.create_task(project.id, "Child Task 1", parent_id=parent.id)
        await task_service.create_task(project.id, "Child Task 2", parent_id=parent.id)

        trees = await task_service.get_task_tree(project.id)

        # Find the parent tree
        parent_tree = next((t for t in trees if t.task.id == parent.id), None)
        assert parent_tree is not None
        assert len(parent_tree.children) == 2

    async def test_get_dependency_graph(
        self,
        task_service: TaskService,
        project_service: ProjectService,
    ):
        """Test getting dependency graph."""
        project = await project_service.create_project(name="Graph Project")
        task1 = await task_service.create_task(project.id, "Task 1")
        task2 = await task_service.create_task(project.id, "Task 2")

        await task_service.add_dependency(task2.id, task1.id)

        graph = await task_service.get_dependency_graph(task2.id)

        assert graph.task_id == task2.id
        assert task1.id in graph.blocked_by

    async def test_bulk_create_tasks(
        self,
        task_service: TaskService,
        project_service: ProjectService,
    ):
        """Test bulk task creation."""
        project = await project_service.create_project(name="Bulk Project")

        tasks_data = [
            {"title": "Bulk Task 1", "priority": "high"},
            {"title": "Bulk Task 2", "priority": "medium"},
            {"title": "Bulk Task 3", "priority": "low"},
        ]

        batch = await task_service.bulk_create_tasks(project.id, tasks_data)

        assert batch.success_count == 3
        assert batch.failure_count == 0
        assert len(batch.tasks) == 3

    async def test_get_blocked_tasks(
        self,
        task_service: TaskService,
        project_service: ProjectService,
    ):
        """Test getting blocked tasks."""
        project = await project_service.create_project(name="Blocked Tasks Project")
        task = await task_service.create_task(project.id, "Blocked Task")
        await task_service.block_task(task.id, "Test block")

        blocked = await task_service.get_blocked_tasks(project.id)

        assert len(blocked) >= 1
        assert any(t.id == task.id for t in blocked)

    async def test_get_blocked_tasks_reconciles_stale_done_blockers(
        self,
        task_service: TaskService,
        project_service: ProjectService,
        task_repo,
    ):
        """Blocked-task reads should clear stale rows whose blockers are done."""
        project = await project_service.create_project(name="Blocked Reconcile Project")
        blocker = await task_service.create_task(project.id, "Blocker")
        dependent = await task_service.create_task(project.id, "Dependent")
        await task_service.add_dependency(dependent.id, blocker.id)

        # Simulate a stale projection path that completes the blocker without
        # running the normal service-level downstream unblocking logic.
        await task_repo.complete(blocker.id, notes="Done")

        blocked = await task_service.get_blocked_tasks(project.id)
        refreshed = await task_service.get_task(dependent.id)

        assert all(task.id != dependent.id for task in blocked)
        assert refreshed is not None
        assert refreshed.status == TaskStatus.TODO


@pytest.mark.asyncio
class TestOrganizationService:
    """Tests for OrganizationService."""

    async def test_create_organization_rolls_back_when_metrics_flush_fails(
        self,
        organization_service: OrganizationService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Organization create should roll back if metrics flush fails late."""

        async def fail_flush(*args, **kwargs):
            raise RuntimeError("metrics flush failed")

        monkeypatch.setattr(organization_service.metrics, "flush", fail_flush)

        with pytest.raises(RuntimeError, match="metrics flush failed"):
            await organization_service.create_organization(name="Atomic Create Org")

        assert (
            await organization_service.get_organization_by_name("Atomic Create Org")
            is None
        )

    async def test_create_and_list_organizations(
        self, organization_service: OrganizationService
    ):
        """Test creating and listing organizations."""
        await organization_service.create_organization(name="Org A")
        await organization_service.create_organization(name="Org B")

        result = await organization_service.list_organizations()

        assert result.total_count >= 2
        names = [o.name for o in result.items]
        assert "Org A" in names
        assert "Org B" in names

    async def test_update_organization_status(
        self, organization_service: OrganizationService
    ):
        """Test updating organization status."""
        org = await organization_service.create_organization(name="Org Update")

        updated = await organization_service.update_organization(
            org_id=org.id, status=OrganizationStatus.ARCHIVED
        )

        assert updated is not None
        assert updated.status == OrganizationStatus.ARCHIVED

    async def test_update_organization_rolls_back_when_metrics_flush_fails(
        self,
        organization_service: OrganizationService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Organization update should roll back if metrics flush fails late."""
        org = await organization_service.create_organization(name="Atomic Update Org")

        async def fail_flush(*args, **kwargs):
            raise RuntimeError("metrics flush failed")

        monkeypatch.setattr(organization_service.metrics, "flush", fail_flush)

        with pytest.raises(RuntimeError, match="metrics flush failed"):
            await organization_service.update_organization(
                org_id=org.id,
                description="after",
                status=OrganizationStatus.ARCHIVED,
            )

        refreshed = await organization_service.get_organization(org.id)
        assert refreshed is not None
        assert refreshed.description is None
        assert refreshed.status == OrganizationStatus.ACTIVE

    async def test_get_organization_summary(
        self,
        organization_service: OrganizationService,
        team_service: TeamService,
        portfolio_service: PortfolioService,
        program_service: ProgramService,
    ):
        """Test organization summary rollups."""
        org = await organization_service.create_organization(name="Org Summary")
        await team_service.create_team(name="Team A", org_id=org.id)
        portfolio = await portfolio_service.create_portfolio(
            name="Portfolio A", org_id=org.id
        )
        await program_service.create_program(
            name="Program A",
            org_id=org.id,
            portfolio_id=portfolio.id,
        )

        summary = await organization_service.get_organization_summary(org.id)

        assert summary is not None
        assert summary.stats.total_teams == 1
        assert summary.stats.total_portfolios == 1
        assert summary.stats.total_programs == 1
        assert summary.risk_level == "low"

    async def test_organization_summary_includes_nested_task_comment_activity(
        self,
        db: Database,
        organization_service: OrganizationService,
        portfolio_service: PortfolioService,
        program_service: ProgramService,
        project_service: ProjectService,
        task_service: TaskService,
    ) -> None:
        """Organization activity should bubble up nested task discussion."""
        from pms.services.comment_service import CommentService

        org = await organization_service.create_organization(name="Org Activity")
        portfolio = await portfolio_service.create_portfolio(
            name="Org Activity Portfolio",
            org_id=org.id,
        )
        program = await program_service.create_program(
            name="Org Activity Program",
            org_id=org.id,
            portfolio_id=portfolio.id,
        )
        project = await project_service.create_project(
            name="Org Activity Project",
            org_id=org.id,
            portfolio_id=portfolio.id,
            program_id=program.id,
        )
        task = await task_service.create_task(project.id, "Org Activity Task")
        comment_service = CommentService(db, MetricsCollector(db))
        item = await comment_service.add_comment(
            entity_type="task",
            entity_id=task.id,
            body="Task note",
            created_by="tester",
        )

        summary = await organization_service.get_organization_summary(org.id)

        assert summary is not None
        assert summary.last_activity_at == item.comment.updated_at

    async def test_organization_summary_includes_team_status_transition(
        self,
        db: Database,
        organization_service: OrganizationService,
        team_service: TeamService,
    ) -> None:
        """Organization transitions should bubble up direct child team transitions."""
        org = await organization_service.create_organization(name="Org Transition")
        team = await team_service.create_team(name="Org Transition Team", org_id=org.id)

        await team_service.update_team(team.id, status=TeamStatus.ARCHIVED)

        summary = await organization_service.get_organization_summary(org.id)
        transition_repo = StateTransitionRepository(db)
        team_transition = await transition_repo.get_last_transition_map(
            "team_status",
            [team.id],
        )

        assert summary is not None
        assert summary.last_transition_at == team_transition[team.id]

    async def test_organization_summary_includes_direct_work_review_activity_without_changing_transition(
        self,
        db: Database,
        metrics_collector: MetricsCollector,
        organization_service: OrganizationService,
        project_service: ProjectService,
        portfolio_service: PortfolioService,
        program_service: ProgramService,
        lineage_service: LineageService,
    ) -> None:
        """Organization reviews should update activity without mutating transition recency."""
        org = await organization_service.create_organization(name="Org Review Activity")
        await organization_service.update_organization(
            org_id=org.id,
            status=OrganizationStatus.ARCHIVED,
        )
        transition_repo = StateTransitionRepository(db)
        org_transition = await transition_repo.get_last_transition_map(
            "organization_status",
            [org.id],
        )
        snapshot_service = _build_work_snapshot_service(
            db,
            metrics_collector,
            project_service=project_service,
            organization_service=organization_service,
            portfolio_service=portfolio_service,
            program_service=program_service,
            lineage_service=lineage_service,
        )

        review = await snapshot_service.mark_reviewed(
            scope_type="organization",
            scope_id=org.id,
            reviewed_by="tester",
            note="Org review",
        )
        summary = await organization_service.get_organization_summary(org.id)

        assert review is not None
        assert summary is not None
        assert summary.last_activity_at == review.reviewed_at
        assert summary.last_transition_at == org_transition[org.id]

    async def test_organization_summary_includes_child_portfolio_work_review_activity(
        self,
        db: Database,
        metrics_collector: MetricsCollector,
        organization_service: OrganizationService,
        project_service: ProjectService,
        portfolio_service: PortfolioService,
        program_service: ProgramService,
        lineage_service: LineageService,
    ) -> None:
        """Organization activity should bubble up direct child portfolio reviews."""
        org = await organization_service.create_organization(
            name="Org Portfolio Review Activity"
        )
        portfolio = await portfolio_service.create_portfolio(
            name="Org Reviewed Portfolio",
            org_id=org.id,
        )
        snapshot_service = _build_work_snapshot_service(
            db,
            metrics_collector,
            project_service=project_service,
            organization_service=organization_service,
            portfolio_service=portfolio_service,
            program_service=program_service,
            lineage_service=lineage_service,
        )

        review = await snapshot_service.mark_reviewed(
            scope_type="portfolio",
            scope_id=portfolio.id,
            reviewed_by="tester",
            note="Portfolio review",
        )
        summary = await organization_service.get_organization_summary(org.id)

        assert review is not None
        assert summary is not None
        assert summary.last_activity_at == review.reviewed_at

    async def test_organization_summary_includes_child_program_work_review_activity(
        self,
        db: Database,
        metrics_collector: MetricsCollector,
        organization_service: OrganizationService,
        project_service: ProjectService,
        portfolio_service: PortfolioService,
        program_service: ProgramService,
        lineage_service: LineageService,
    ) -> None:
        """Organization activity should bubble up direct child program reviews."""
        org = await organization_service.create_organization(
            name="Org Program Review Activity"
        )
        portfolio = await portfolio_service.create_portfolio(
            name="Org Program Review Portfolio",
            org_id=org.id,
        )
        program = await program_service.create_program(
            name="Org Reviewed Program",
            org_id=org.id,
            portfolio_id=portfolio.id,
        )
        snapshot_service = _build_work_snapshot_service(
            db,
            metrics_collector,
            project_service=project_service,
            organization_service=organization_service,
            portfolio_service=portfolio_service,
            program_service=program_service,
            lineage_service=lineage_service,
        )

        review = await snapshot_service.mark_reviewed(
            scope_type="program",
            scope_id=program.id,
            reviewed_by="tester",
            note="Program review",
        )
        summary = await organization_service.get_organization_summary(org.id)

        assert review is not None
        assert summary is not None
        assert summary.last_activity_at == review.reviewed_at

    async def test_organization_dashboard(
        self,
        organization_service: OrganizationService,
        team_service: TeamService,
    ):
        """Test organization dashboard rollups."""
        org = await organization_service.create_organization(name="Org Dash")
        await team_service.create_team(name="Team Dash", org_id=org.id)

        dashboard = await organization_service.get_organization_dashboard()

        assert dashboard.total_organizations >= 1
        assert dashboard.total_teams >= 1
        assert any(item.organization.id == org.id for item in dashboard.items)

    async def test_archive_organization_rolls_back_when_metrics_flush_fails(
        self,
        organization_service: OrganizationService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Organization archive should roll back if metrics flush fails late."""
        org = await organization_service.create_organization(name="Atomic Org Archive")

        async def fail_flush(*args, **kwargs):
            raise RuntimeError("metrics flush failed")

        monkeypatch.setattr(organization_service.metrics, "flush", fail_flush)

        with pytest.raises(RuntimeError, match="metrics flush failed"):
            await organization_service.archive_organization(org.id)

        refreshed = await organization_service.get_organization(org.id)
        assert refreshed is not None
        assert refreshed.status == OrganizationStatus.ACTIVE


@pytest.mark.asyncio
class TestTeamService:
    """Tests for TeamService."""

    async def test_create_team_rolls_back_when_metrics_flush_fails(
        self,
        team_service: TeamService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Team create should roll back if metrics flush fails late."""

        async def fail_flush(*args, **kwargs):
            raise RuntimeError("metrics flush failed")

        monkeypatch.setattr(team_service.metrics, "flush", fail_flush)

        with pytest.raises(RuntimeError, match="metrics flush failed"):
            await team_service.create_team(name="Atomic Create Team")

        assert await team_service.get_team_by_name("Atomic Create Team") is None

    async def test_create_update_team(self, team_service: TeamService):
        """Test creating and updating a team."""
        team = await team_service.create_team(name="Team Service")
        updated = await team_service.update_team(team.id, status=TeamStatus.ARCHIVED)

        assert updated is not None
        assert updated.status == TeamStatus.ARCHIVED

    async def test_update_team_rolls_back_when_metrics_flush_fails(
        self,
        team_service: TeamService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Team update should roll back if metrics flush fails late."""
        team = await team_service.create_team(name="Atomic Update Team")

        async def fail_flush(*args, **kwargs):
            raise RuntimeError("metrics flush failed")

        monkeypatch.setattr(team_service.metrics, "flush", fail_flush)

        with pytest.raises(RuntimeError, match="metrics flush failed"):
            await team_service.update_team(
                team.id,
                description="after",
                status=TeamStatus.ARCHIVED,
            )

        refreshed = await team_service.get_team(team.id)
        assert refreshed is not None
        assert refreshed.description is None
        assert refreshed.status == TeamStatus.ACTIVE

    async def test_archive_team_rolls_back_when_metrics_flush_fails(
        self,
        team_service: TeamService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Team archive should roll back if metrics flush fails late."""
        team = await team_service.create_team(name="Atomic Team Archive")

        async def fail_flush(*args, **kwargs):
            raise RuntimeError("metrics flush failed")

        monkeypatch.setattr(team_service.metrics, "flush", fail_flush)

        with pytest.raises(RuntimeError, match="metrics flush failed"):
            await team_service.archive_team(team.id)

        refreshed = await team_service.get_team(team.id)
        assert refreshed is not None
        assert refreshed.status == TeamStatus.ACTIVE


@pytest.mark.asyncio
class TestPortfolioService:
    """Tests for PortfolioService."""

    async def test_create_portfolio_rolls_back_when_metrics_flush_fails(
        self,
        portfolio_service: PortfolioService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Portfolio create should roll back if metrics flush fails late."""

        async def fail_flush(*args, **kwargs):
            raise RuntimeError("metrics flush failed")

        monkeypatch.setattr(portfolio_service.metrics, "flush", fail_flush)

        with pytest.raises(RuntimeError, match="metrics flush failed"):
            await portfolio_service.create_portfolio(name="Atomic Create Portfolio")

        assert (
            await portfolio_service.get_portfolio_by_name("Atomic Create Portfolio")
            is None
        )

    async def test_create_update_portfolio(self, portfolio_service: PortfolioService):
        """Test creating and updating a portfolio."""
        portfolio = await portfolio_service.create_portfolio(name="Portfolio Service")
        updated = await portfolio_service.update_portfolio(
            portfolio_id=portfolio.id,
            status=PortfolioStatus.ARCHIVED,
        )

        assert updated is not None
        assert updated.status == PortfolioStatus.ARCHIVED

    async def test_update_portfolio_rolls_back_when_metrics_flush_fails(
        self,
        portfolio_service: PortfolioService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Portfolio update should roll back if metrics flush fails late."""
        portfolio = await portfolio_service.create_portfolio(
            name="Atomic Update Portfolio"
        )

        async def fail_flush(*args, **kwargs):
            raise RuntimeError("metrics flush failed")

        monkeypatch.setattr(portfolio_service.metrics, "flush", fail_flush)

        with pytest.raises(RuntimeError, match="metrics flush failed"):
            await portfolio_service.update_portfolio(
                portfolio_id=portfolio.id,
                description="after",
                status=PortfolioStatus.ARCHIVED,
            )

        refreshed = await portfolio_service.get_portfolio(portfolio.id)
        assert refreshed is not None
        assert refreshed.description is None
        assert refreshed.status == PortfolioStatus.ACTIVE

    async def test_portfolio_summary(self, portfolio_service: PortfolioService):
        """Test portfolio summary rollups."""
        portfolio = await portfolio_service.create_portfolio(name="Portfolio Summary")

        summary = await portfolio_service.get_portfolio_summary(portfolio.id)

        assert summary is not None
        assert summary.stats.total_projects == 0
        assert summary.risk_level == "low"

    async def test_portfolio_summary_includes_nested_task_comment_activity(
        self,
        db: Database,
        portfolio_service: PortfolioService,
        project_service: ProjectService,
        task_service: TaskService,
    ) -> None:
        """Portfolio activity should bubble up nested task discussion."""
        from pms.services.comment_service import CommentService

        portfolio = await portfolio_service.create_portfolio(
            name="Portfolio Activity Summary"
        )
        project = await project_service.create_project(
            name="Portfolio Activity Project",
            portfolio_id=portfolio.id,
        )
        task = await task_service.create_task(project.id, "Portfolio Activity Task")
        comment_service = CommentService(db, MetricsCollector(db))
        item = await comment_service.add_comment(
            entity_type="task",
            entity_id=task.id,
            body="Portfolio task note",
            created_by="tester",
        )

        summary = await portfolio_service.get_portfolio_summary(portfolio.id)

        assert summary is not None
        assert summary.last_activity_at == item.comment.updated_at

    async def test_portfolio_summary_includes_program_status_transition(
        self,
        db: Database,
        portfolio_service: PortfolioService,
        program_service: ProgramService,
    ) -> None:
        """Portfolio transitions should bubble up child program status changes."""
        portfolio = await portfolio_service.create_portfolio(
            name="Portfolio Transition Summary"
        )
        program = await program_service.create_program(
            name="Portfolio Transition Program",
            portfolio_id=portfolio.id,
        )

        await program_service.update_program(program.id, status=ProgramStatus.ARCHIVED)

        summary = await portfolio_service.get_portfolio_summary(portfolio.id)
        transition_repo = StateTransitionRepository(db)
        program_transition = await transition_repo.get_last_transition_map(
            "program_status",
            [program.id],
        )

        assert summary is not None
        assert summary.last_transition_at == program_transition[program.id]

    async def test_portfolio_summary_includes_direct_work_review_activity_without_changing_transition(
        self,
        db: Database,
        metrics_collector: MetricsCollector,
        organization_service: OrganizationService,
        portfolio_service: PortfolioService,
        program_service: ProgramService,
        project_service: ProjectService,
        lineage_service: LineageService,
    ) -> None:
        """Portfolio reviews should update activity without mutating transition recency."""
        portfolio = await portfolio_service.create_portfolio(
            name="Portfolio Review Activity"
        )
        await portfolio_service.update_portfolio(
            portfolio_id=portfolio.id,
            status=PortfolioStatus.ARCHIVED,
        )
        transition_repo = StateTransitionRepository(db)
        portfolio_transition = await transition_repo.get_last_transition_map(
            "portfolio_status",
            [portfolio.id],
        )
        snapshot_service = _build_work_snapshot_service(
            db,
            metrics_collector,
            project_service=project_service,
            organization_service=organization_service,
            portfolio_service=portfolio_service,
            program_service=program_service,
            lineage_service=lineage_service,
        )

        review = await snapshot_service.mark_reviewed(
            scope_type="portfolio",
            scope_id=portfolio.id,
            reviewed_by="tester",
            note="Portfolio review",
        )
        summary = await portfolio_service.get_portfolio_summary(portfolio.id)

        assert review is not None
        assert summary is not None
        assert summary.last_activity_at == review.reviewed_at
        assert summary.last_transition_at == portfolio_transition[portfolio.id]

    async def test_portfolio_summary_includes_child_program_work_review_activity(
        self,
        db: Database,
        metrics_collector: MetricsCollector,
        organization_service: OrganizationService,
        portfolio_service: PortfolioService,
        program_service: ProgramService,
        project_service: ProjectService,
        lineage_service: LineageService,
    ) -> None:
        """Portfolio activity should bubble up direct child program reviews."""
        portfolio = await portfolio_service.create_portfolio(
            name="Portfolio Program Review Activity"
        )
        program = await program_service.create_program(
            name="Portfolio Reviewed Program",
            portfolio_id=portfolio.id,
        )
        snapshot_service = _build_work_snapshot_service(
            db,
            metrics_collector,
            project_service=project_service,
            organization_service=organization_service,
            portfolio_service=portfolio_service,
            program_service=program_service,
            lineage_service=lineage_service,
        )

        review = await snapshot_service.mark_reviewed(
            scope_type="program",
            scope_id=program.id,
            reviewed_by="tester",
            note="Program review",
        )
        summary = await portfolio_service.get_portfolio_summary(portfolio.id)

        assert review is not None
        assert summary is not None
        assert summary.last_activity_at == review.reviewed_at

    async def test_portfolio_dashboard(self, portfolio_service: PortfolioService):
        """Test portfolio dashboard rollups."""
        portfolio = await portfolio_service.create_portfolio(name="Portfolio Dash")

        dashboard = await portfolio_service.get_portfolio_dashboard()

        assert dashboard.total_portfolios >= 1
        assert any(item.portfolio.id == portfolio.id for item in dashboard.items)

    async def test_archive_portfolio_rolls_back_when_metrics_flush_fails(
        self,
        portfolio_service: PortfolioService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Portfolio archive should roll back if metrics flush fails late."""
        portfolio = await portfolio_service.create_portfolio(
            name="Atomic Portfolio Archive"
        )

        async def fail_flush(*args, **kwargs):
            raise RuntimeError("metrics flush failed")

        monkeypatch.setattr(portfolio_service.metrics, "flush", fail_flush)

        with pytest.raises(RuntimeError, match="metrics flush failed"):
            await portfolio_service.archive_portfolio(portfolio.id)

        refreshed = await portfolio_service.get_portfolio(portfolio.id)
        assert refreshed is not None
        assert refreshed.status == PortfolioStatus.ACTIVE


@pytest.mark.asyncio
class TestProgramService:
    """Tests for ProgramService."""

    async def test_create_program_rolls_back_when_metrics_flush_fails(
        self,
        program_service: ProgramService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Program create should roll back if metrics flush fails late."""

        async def fail_flush(*args, **kwargs):
            raise RuntimeError("metrics flush failed")

        monkeypatch.setattr(program_service.metrics, "flush", fail_flush)

        with pytest.raises(RuntimeError, match="metrics flush failed"):
            await program_service.create_program(name="Atomic Create Program")

        assert (
            await program_service.get_program_by_name("Atomic Create Program") is None
        )

    async def test_create_update_program(self, program_service: ProgramService):
        """Test creating and updating a program."""
        program = await program_service.create_program(name="Program Service")
        updated = await program_service.update_program(
            program_id=program.id,
            status=ProgramStatus.ARCHIVED,
        )

        assert updated is not None
        assert updated.status == ProgramStatus.ARCHIVED

    async def test_update_program_rolls_back_when_metrics_flush_fails(
        self,
        program_service: ProgramService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Program update should roll back if metrics flush fails late."""
        program = await program_service.create_program(name="Atomic Update Program")

        async def fail_flush(*args, **kwargs):
            raise RuntimeError("metrics flush failed")

        monkeypatch.setattr(program_service.metrics, "flush", fail_flush)

        with pytest.raises(RuntimeError, match="metrics flush failed"):
            await program_service.update_program(
                program_id=program.id,
                description="after",
                status=ProgramStatus.ARCHIVED,
            )

        refreshed = await program_service.get_program(program.id)
        assert refreshed is not None
        assert refreshed.description is None
        assert refreshed.status == ProgramStatus.ACTIVE

    async def test_program_summary(self, program_service: ProgramService):
        """Test program summary rollups."""
        program = await program_service.create_program(name="Program Summary")

        summary = await program_service.get_program_summary(program.id)

        assert summary is not None
        assert summary.stats.total_projects == 0
        assert summary.risk_level == "low"

    async def test_program_summary_includes_nested_task_comment_activity(
        self,
        db: Database,
        program_service: ProgramService,
        project_service: ProjectService,
        task_service: TaskService,
    ) -> None:
        """Program activity should bubble up nested task discussion."""
        from pms.services.comment_service import CommentService

        program = await program_service.create_program(name="Program Activity Summary")
        project = await project_service.create_project(
            name="Program Activity Project",
            program_id=program.id,
        )
        task = await task_service.create_task(project.id, "Program Activity Task")
        comment_service = CommentService(db, MetricsCollector(db))
        item = await comment_service.add_comment(
            entity_type="task",
            entity_id=task.id,
            body="Program task note",
            created_by="tester",
        )

        summary = await program_service.get_program_summary(program.id)

        assert summary is not None
        assert summary.last_activity_at == item.comment.updated_at

    async def test_program_summary_includes_nested_goal_transition(
        self,
        program_service: ProgramService,
        project_service: ProjectService,
        goal_service: GoalService,
    ) -> None:
        """Program transitions should bubble up nested goal status changes."""
        program = await program_service.create_program(
            name="Program Transition Summary"
        )
        project = await project_service.create_project(
            name="Program Transition Project",
            program_id=program.id,
        )
        goal = await goal_service.create_goal(
            name="Program Transition Goal",
            project_id=project.id,
        )

        await goal_service.update_goal(
            goal.id,
            status=GoalStatus.ON_HOLD,
            progress_percent=5,
        )

        summary = await program_service.get_program_summary(program.id)
        goal_transition = await goal_service.get_last_transition_map([goal.id])

        assert summary is not None
        assert summary.last_transition_at == goal_transition[goal.id]

    async def test_program_summary_includes_direct_work_review_activity_without_changing_transition(
        self,
        db: Database,
        metrics_collector: MetricsCollector,
        organization_service: OrganizationService,
        portfolio_service: PortfolioService,
        program_service: ProgramService,
        project_service: ProjectService,
        lineage_service: LineageService,
    ) -> None:
        """Program reviews should update activity without mutating transition recency."""
        program = await program_service.create_program(name="Program Review Activity")
        await program_service.update_program(
            program_id=program.id,
            status=ProgramStatus.ARCHIVED,
        )
        transition_repo = StateTransitionRepository(db)
        program_transition = await transition_repo.get_last_transition_map(
            "program_status",
            [program.id],
        )
        snapshot_service = _build_work_snapshot_service(
            db,
            metrics_collector,
            project_service=project_service,
            organization_service=organization_service,
            portfolio_service=portfolio_service,
            program_service=program_service,
            lineage_service=lineage_service,
        )

        review = await snapshot_service.mark_reviewed(
            scope_type="program",
            scope_id=program.id,
            reviewed_by="tester",
            note="Program review",
        )
        summary = await program_service.get_program_summary(program.id)

        assert review is not None
        assert summary is not None
        assert summary.last_activity_at == review.reviewed_at
        assert summary.last_transition_at == program_transition[program.id]

    async def test_program_dashboard(self, program_service: ProgramService):
        """Test program dashboard rollups."""
        program = await program_service.create_program(name="Program Dash")

        dashboard = await program_service.get_program_dashboard()

        assert dashboard.total_programs >= 1
        assert any(item.program.id == program.id for item in dashboard.items)

    async def test_archive_program_rolls_back_when_metrics_flush_fails(
        self,
        program_service: ProgramService,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Program archive should roll back if metrics flush fails late."""
        program = await program_service.create_program(name="Atomic Program Archive")

        async def fail_flush(*args, **kwargs):
            raise RuntimeError("metrics flush failed")

        monkeypatch.setattr(program_service.metrics, "flush", fail_flush)

        with pytest.raises(RuntimeError, match="metrics flush failed"):
            await program_service.archive_program(program.id)

        refreshed = await program_service.get_program(program.id)
        assert refreshed is not None
        assert refreshed.status == ProgramStatus.ACTIVE
