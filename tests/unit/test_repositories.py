"""Unit tests for PMS repositories."""

from datetime import timedelta

import pytest

from pms.core.events import EventType
from pms.models import (
    GoalHorizon,
    GoalStatus,
    Organization,
    OrganizationStatus,
    Plan,
    PlanFormat,
    PlanStatus,
    PortfolioStatus,
    Priority,
    ProgramStatus,
    ProjectStatus,
    TaskStatus,
    Team,
    TeamStatus,
)
from pms.models.enums import DependencyType
from pms.repositories.goal_repository import GoalRepository
from pms.repositories.key_result_repository import KeyResultRepository
from pms.repositories.objective_repository import ObjectiveRepository
from pms.repositories.organization_repository import OrganizationRepository
from pms.repositories.plan_repository import PlanRepository
from pms.repositories.portfolio_repository import PortfolioRepository
from pms.repositories.program_repository import ProgramRepository
from pms.repositories.project_repository import ProjectRepository
from pms.repositories.saved_search_repository import SavedSearchRepository
from pms.repositories.task_repository import TaskRepository
from pms.repositories.team_repository import TeamRepository


@pytest.mark.asyncio
class TestProjectRepository:
    """Tests for ProjectRepository."""

    async def test_create_project(self, project_repo: ProjectRepository):
        """Test creating a project."""
        project = await project_repo.create(
            name="New Project",
            description="A new project",
            tags=["api", "backend"],
        )

        assert project.id is not None
        assert project.name == "New Project"
        assert project.description == "A new project"
        assert set(project.tags) == {"api", "backend"}
        assert project.status == ProjectStatus.ACTIVE
        assert project.last_event_sequence == 1
        assert project.last_revision_number == 1

    async def test_get_by_id(self, project_repo: ProjectRepository, sample_project):
        """Test retrieving project by ID."""
        retrieved = await project_repo.get_by_id(sample_project.id)

        assert retrieved is not None
        assert retrieved.id == sample_project.id
        assert retrieved.name == sample_project.name

    async def test_get_by_name(self, project_repo: ProjectRepository, sample_project):
        """Test retrieving project by name."""
        retrieved = await project_repo.get_by_name(sample_project.name)

        assert retrieved is not None
        assert retrieved.id == sample_project.id

    async def test_get_by_name_not_found(self, project_repo: ProjectRepository):
        """Test retrieving non-existent project by name."""
        result = await project_repo.get_by_name("Non-existent Project")
        assert result is None

    async def test_update_project(
        self, project_repo: ProjectRepository, sample_project
    ):
        """Test updating a project."""
        updated = await project_repo.update(
            project_id=sample_project.id,
            description="Updated description",
            tags=["updated", "modified"],
        )

        assert updated is not None
        assert updated.description == "Updated description"
        assert set(updated.tags) == {"updated", "modified"}
        assert updated.last_revision_number == 2

    async def test_archive_project(
        self, project_repo: ProjectRepository, sample_project
    ):
        """Test archiving a project."""
        archived = await project_repo.archive(sample_project.id)

        assert archived is not None
        assert archived.status == ProjectStatus.ARCHIVED

    async def test_get_all_projects(self, project_repo: ProjectRepository):
        """Test getting all projects."""
        # Create multiple projects
        await project_repo.create(name="Project A")
        await project_repo.create(name="Project B")

        result = await project_repo.get_all()

        assert result.total_count >= 2
        assert len(result.items) >= 2

    async def test_get_by_status(self, project_repo: ProjectRepository):
        """Test filtering projects by status."""
        # Create projects with different statuses
        active = await project_repo.create(name="Active Project")
        archived = await project_repo.create(name="To Archive")
        await project_repo.archive(archived.id)

        active_result = await project_repo.get_by_status(ProjectStatus.ACTIVE)
        archived_result = await project_repo.get_by_status(ProjectStatus.ARCHIVED)

        active_names = [p.name for p in active_result.items]
        archived_names = [p.name for p in archived_result.items]

        assert "Active Project" in active_names
        assert "To Archive" in archived_names

    async def test_get_stats_bulk(
        self, project_repo: ProjectRepository, task_repo: TaskRepository
    ):
        """Test bulk project stats aggregation."""
        project_one = await project_repo.create(name="Project One")
        project_two = await project_repo.create(name="Project Two")

        task_one = await task_repo.create(project_one.id, "Task One")
        task_two = await task_repo.create(project_one.id, "Task Two")
        await task_repo.update_status(task_two.id, TaskStatus.DONE)
        await task_repo.create(project_two.id, "Task Three")

        stats_map = await project_repo.get_stats_bulk([project_one.id, project_two.id])

        stats_one = stats_map[project_one.id]
        stats_two = stats_map[project_two.id]

        assert stats_one.total_tasks == 2
        assert stats_one.completed_tasks == 1
        assert stats_two.total_tasks == 1

    async def test_project_history(
        self, project_repo: ProjectRepository, sample_project
    ):
        """Test getting project revision history."""
        # Make some updates
        await project_repo.update(sample_project.id, description="First update")
        await project_repo.update(sample_project.id, description="Second update")

        history = await project_repo.get_history(sample_project.id)

        assert len(history) >= 3  # Initial + 2 updates
        # History is returned newest first
        assert history[0].revision_number > history[-1].revision_number

    async def test_get_at_revision(
        self, project_repo: ProjectRepository, sample_project
    ):
        """Test getting project at specific revision."""
        # Update the project
        await project_repo.update(
            sample_project.id,
            description="Updated",
        )

        # Get at revision 1 (original)
        original = await project_repo.get_at_revision(sample_project.id, 1)

        assert original is not None
        assert original.description == sample_project.description

    async def test_create_project_rolls_back_when_projection_update_fails(
        self,
        db,
        project_repo: ProjectRepository,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Projection failure must roll back event, revision, and transition writes."""
        created_project_id: str | None = None

        async def fail_projection(model, is_create: bool) -> None:
            nonlocal created_project_id
            created_project_id = model.id
            raise RuntimeError("projection update failed")

        monkeypatch.setattr(project_repo, "_update_projection", fail_projection)

        with pytest.raises(RuntimeError, match="projection update failed"):
            await project_repo.create(name="Projection Rollback Project")

        assert created_project_id is not None
        assert await project_repo.get_by_id(created_project_id) is None
        assert await project_repo.events.get_events("project", created_project_id) == []
        assert (
            await project_repo.revisions.get_revision_count(
                "project", created_project_id
            )
            == 0
        )
        transition_count_row = await db.fetch_one(
            """
            SELECT COUNT(*) AS count
            FROM state_transition_log
            WHERE entity_type = ? AND entity_id = ?
            """,
            ("project_status", created_project_id),
        )
        assert transition_count_row is not None
        assert transition_count_row["count"] == 0

    async def test_search_projects(self, project_repo: ProjectRepository):
        """Test searching projects."""
        await project_repo.create(
            name="Searchable API",
            description="REST API project",
        )
        await project_repo.create(
            name="Frontend App",
            description="React application",
        )

        results = await project_repo.search("API")

        assert len(results) >= 1
        assert any("API" in p.name or "API" in (p.description or "") for p in results)


@pytest.mark.asyncio
class TestGoalRepository:
    """Tests for GoalRepository."""

    async def test_create_goal(self, goal_repo: GoalRepository):
        """Test creating a goal."""
        goal = await goal_repo.create(
            name="New Goal",
            description="A new goal",
            horizon=GoalHorizon.MEDIUM_TERM,
            progress_percent=10,
        )

        assert goal.id is not None
        assert goal.name == "New Goal"
        assert goal.description == "A new goal"
        assert goal.horizon == GoalHorizon.MEDIUM_TERM
        assert goal.progress_percent == 10
        assert goal.status == GoalStatus.ACTIVE
        assert goal.last_event_sequence == 1
        assert goal.last_revision_number == 1

    async def test_get_by_id(self, goal_repo: GoalRepository, sample_goal):
        """Test retrieving goal by ID."""
        retrieved = await goal_repo.get_by_id(sample_goal.id)

        assert retrieved is not None
        assert retrieved.id == sample_goal.id
        assert retrieved.name == sample_goal.name

    async def test_get_by_name(self, goal_repo: GoalRepository, sample_goal):
        """Test retrieving goal by name."""
        retrieved = await goal_repo.get_by_name(sample_goal.name)

        assert retrieved is not None
        assert retrieved.id == sample_goal.id

    async def test_update_goal(self, goal_repo: GoalRepository, sample_goal):
        """Test updating a goal."""
        updated = await goal_repo.update(
            goal_id=sample_goal.id,
            description="Updated description",
            horizon=GoalHorizon.LONG_TERM,
            progress_percent=30,
        )

        assert updated is not None
        assert updated.description == "Updated description"
        assert updated.horizon == GoalHorizon.LONG_TERM
        assert updated.progress_percent == 30

    async def test_archive_goal(self, goal_repo: GoalRepository, sample_goal):
        """Test archiving a goal."""
        archived = await goal_repo.archive(sample_goal.id)

        assert archived is not None
        assert archived.status == GoalStatus.ARCHIVED

    async def test_complete_goal(self, goal_repo: GoalRepository, sample_goal):
        """Test completing a goal."""
        completed = await goal_repo.complete(sample_goal.id)

        assert completed is not None
        assert completed.status == GoalStatus.COMPLETED
        assert completed.progress_percent == 100


@pytest.mark.asyncio
class TestObjectiveRepository:
    """Tests for ObjectiveRepository."""

    async def test_create_objective(
        self, objective_repo: ObjectiveRepository, sample_goal
    ):
        """Test creating an objective."""
        objective = await objective_repo.create(
            goal_id=sample_goal.id,
            name="New Objective",
            description="Objective description",
            progress_percent=25,
        )

        assert objective.id is not None
        assert objective.goal_id == sample_goal.id
        assert objective.name == "New Objective"
        assert objective.progress_percent == 25
        assert objective.status == GoalStatus.ACTIVE

    async def test_update_objective(
        self, objective_repo: ObjectiveRepository, sample_objective
    ):
        """Test updating an objective."""
        updated = await objective_repo.update(
            objective_id=sample_objective.id,
            description="Updated objective",
            progress_percent=60,
        )

        assert updated is not None
        assert updated.description == "Updated objective"
        assert updated.progress_percent == 60

    async def test_complete_objective(
        self, objective_repo: ObjectiveRepository, sample_objective
    ):
        """Test completing an objective."""
        completed = await objective_repo.complete(sample_objective.id)

        assert completed is not None
        assert completed.status == GoalStatus.COMPLETED
        assert completed.progress_percent == 100


@pytest.mark.asyncio
class TestKeyResultRepository:
    """Tests for KeyResultRepository."""

    async def test_create_key_result(
        self, key_result_repo: KeyResultRepository, sample_objective
    ):
        """Test creating a key result."""
        key_result = await key_result_repo.create(
            objective_id=sample_objective.id,
            name="New Key Result",
            description="Key result description",
            progress_percent=15,
        )

        assert key_result.id is not None
        assert key_result.objective_id == sample_objective.id
        assert key_result.name == "New Key Result"
        assert key_result.progress_percent == 15
        assert key_result.status == GoalStatus.ACTIVE

    async def test_update_key_result(
        self, key_result_repo: KeyResultRepository, sample_key_result
    ):
        """Test updating a key result."""
        updated = await key_result_repo.update(
            key_result_id=sample_key_result.id,
            description="Updated key result",
            progress_percent=70,
        )

        assert updated is not None
        assert updated.description == "Updated key result"
        assert updated.progress_percent == 70

    async def test_complete_key_result(
        self, key_result_repo: KeyResultRepository, sample_key_result
    ):
        """Test completing a key result."""
        completed = await key_result_repo.complete(sample_key_result.id)

        assert completed is not None
        assert completed.status == GoalStatus.COMPLETED
        assert completed.progress_percent == 100


@pytest.mark.asyncio
class TestPlanRepository:
    """Tests for PlanRepository."""

    async def test_create_plan(
        self, plan_repo: PlanRepository, sample_project, sample_task
    ):
        """Test creating a plan."""
        plan = await plan_repo.create(
            name="New Plan",
            description="A plan",
            status=PlanStatus.DRAFT,
            format=PlanFormat.JSON,
            content="{}",
            project_id=sample_project.id,
            task_ids=[sample_task.id],
            tags=["plan"],
        )

        assert plan.id is not None
        assert plan.name == "New Plan"
        assert plan.status == PlanStatus.DRAFT
        assert plan.format == PlanFormat.JSON
        assert plan.project_id == sample_project.id

    async def test_update_plan(self, plan_repo: PlanRepository, sample_plan):
        """Test updating a plan."""
        updated = await plan_repo.update(
            plan_id=sample_plan.id,
            status=PlanStatus.ACTIVE,
            content='{"stage": "active"}',
            tags=["updated"],
        )

        assert updated is not None
        assert updated.status == PlanStatus.ACTIVE
        assert "active" in updated.content
        assert updated.tags == ("updated",)

    async def test_list_plans(self, plan_repo: PlanRepository, sample_plan):
        """Test listing plans."""
        result = await plan_repo.list_plans(status=PlanStatus.DRAFT)

        assert result.total_count >= 1
        assert any(plan.id == sample_plan.id for plan in result.items)

    async def test_update_plan_preserves_newer_content_on_stale_task_link_save(
        self,
        plan_repo: PlanRepository,
        sample_plan,
        sample_task,
    ):
        """Stale task-id updates must not clobber newer plan content."""
        stale_plan = await plan_repo.get_by_id(sample_plan.id)
        assert stale_plan is not None

        await plan_repo.update(
            plan_id=sample_plan.id,
            content='{"delivery": "detailed"}',
        )

        stale_plan.task_ids = (sample_task.id,)
        stale_plan.touch()
        saved = await plan_repo.save(
            stale_plan,
            EventType.PLAN_UPDATED,
            {"changes": {"task_ids": ([], [sample_task.id])}},
            message="Auto-linked new project task into active plan lineage",
        )

        assert saved.task_ids == (sample_task.id,)

        refreshed = await plan_repo.get_by_id(sample_plan.id)
        assert refreshed is not None
        assert refreshed.task_ids == (sample_task.id,)
        assert refreshed.content == '{"delivery": "detailed"}'

    async def test_create_plan_rolls_back_when_task_link_sync_fails(
        self,
        plan_repo: PlanRepository,
        sample_project,
        sample_task,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Direct repo create must roll back if task-link projection sync fails."""
        created_plan_id: str | None = None

        async def fail_task_sync(plan: Plan) -> None:
            nonlocal created_plan_id
            created_plan_id = plan.id
            raise RuntimeError(f"task link sync failed for {list(plan.task_ids)!r}")

        monkeypatch.setattr(plan_repo, "_sync_task_links", fail_task_sync)

        with pytest.raises(RuntimeError, match="task link sync failed"):
            await plan_repo.create(
                name="Rollback Plan",
                description="should roll back",
                status=PlanStatus.DRAFT,
                format=PlanFormat.JSON,
                content="{}",
                project_id=sample_project.id,
                task_ids=[sample_task.id],
            )

        assert created_plan_id is not None
        assert await plan_repo.get_by_id(created_plan_id) is None
        assert await plan_repo.events.get_events("plan", created_plan_id) == []
        assert (
            await plan_repo.revisions.get_revision_count("plan", created_plan_id) == 0
        )

    async def test_update_plan_rolls_back_when_task_link_sync_fails(
        self,
        plan_repo: PlanRepository,
        sample_plan,
        sample_task,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Direct repo update must roll back if task-link projection sync fails."""

        async def fail_task_sync(plan: Plan) -> None:
            raise RuntimeError(f"task link sync failed for {list(plan.task_ids)!r}")

        monkeypatch.setattr(plan_repo, "_sync_task_links", fail_task_sync)

        with pytest.raises(RuntimeError, match="task link sync failed"):
            await plan_repo.update(
                plan_id=sample_plan.id,
                description="Should Roll Back",
                task_ids=[sample_task.id],
            )

        reloaded = await plan_repo.get_by_id(sample_plan.id)
        assert reloaded is not None
        assert reloaded.description == sample_plan.description
        assert await plan_repo.events.get_events("plan", sample_plan.id)
        assert await plan_repo.revisions.get_revision_count("plan", sample_plan.id) == 1


@pytest.mark.asyncio
class TestTaskRepository:
    """Tests for TaskRepository."""

    async def test_create_task(self, task_repo: TaskRepository, sample_project):
        """Test creating a task."""
        task = await task_repo.create(
            project_id=sample_project.id,
            title="New Task",
            description="Task description",
            priority=Priority.HIGH,
            complexity_points=40,
            tags=["feature", "urgent"],
        )

        assert task.id is not None
        assert task.title == "New Task"
        assert task.project_id == sample_project.id
        assert task.priority == Priority.HIGH
        assert task.complexity_points == 40
        assert task.status == TaskStatus.TODO
        assert task.last_event_sequence == 1

    async def test_get_by_id(self, task_repo: TaskRepository, sample_task):
        """Test retrieving task by ID."""
        retrieved = await task_repo.get_by_id(sample_task.id)

        assert retrieved is not None
        assert retrieved.id == sample_task.id
        assert retrieved.title == sample_task.title

    async def test_update_status(self, task_repo: TaskRepository, sample_task):
        """Test updating task status."""
        # Start task
        updated = await task_repo.update_status(sample_task.id, TaskStatus.IN_PROGRESS)

        assert updated is not None
        assert updated.status == TaskStatus.IN_PROGRESS
        assert updated.last_revision_number > sample_task.last_revision_number

    async def test_update_task(self, task_repo: TaskRepository, sample_task):
        """Test updating task fields."""
        updated = await task_repo.update_task(
            sample_task.id,
            title="Updated Title",
            description="Updated description",
            priority=Priority.CRITICAL,
            complexity_points=80,
        )

        assert updated is not None
        assert updated.title == "Updated Title"
        assert updated.description == "Updated description"
        assert updated.priority == Priority.CRITICAL
        assert updated.complexity_points == 80

    async def test_complete_task(self, task_repo: TaskRepository, sample_task):
        """Test completing a task."""
        completed = await task_repo.complete(
            sample_task.id,
            notes="Done successfully",
        )

        assert completed is not None
        assert completed.status == TaskStatus.DONE
        assert completed.completed_at is not None
        assert completed.current_progress_percent == 100
        assert completed.last_progress_update_at is not None

    async def test_stale_progress_save_does_not_reopen_completed_task(
        self, task_repo: TaskRepository, sample_task
    ):
        """A late stale progress save must not overwrite a newer completed status."""
        stale_snapshot = await task_repo.get_by_id(sample_task.id)
        assert stale_snapshot is not None

        completed = await task_repo.complete(sample_task.id, notes="Done successfully")
        assert completed is not None
        assert completed.status == TaskStatus.DONE

        stale_snapshot.current_progress_percent = 60
        stale_snapshot.last_progress_update_at = stale_snapshot.updated_at
        stale_snapshot.updated_at = stale_snapshot.updated_at

        await task_repo.save(
            stale_snapshot,
            EventType.TASK_PROGRESS_UPDATED,
            {
                "percent_complete": 60,
                "status_message": "Late stale progress write",
                "updated_by": "tester",
                "last_progress_update_at": stale_snapshot.updated_at.isoformat(),
            },
            message="Updated task progress",
        )

        persisted = await task_repo.get_by_id(sample_task.id)
        assert persisted is not None
        assert persisted.status == TaskStatus.DONE
        assert persisted.completed_at is not None
        assert persisted.current_progress_percent == 100

    async def test_get_by_project(
        self, task_repo: TaskRepository, sample_project, sample_task
    ):
        """Test getting tasks for a project."""
        # Create additional tasks
        await task_repo.create(
            project_id=sample_project.id,
            title="Another Task",
        )

        result = await task_repo.get_by_project(sample_project.id)

        assert result.total_count >= 2
        assert all(t.project_id == sample_project.id for t in result.items)

    async def test_get_by_project_with_status_filter(
        self, task_repo: TaskRepository, sample_project
    ):
        """Test filtering tasks by status."""
        # Create tasks with different statuses
        task1 = await task_repo.create(
            project_id=sample_project.id,
            title="Todo Task",
        )
        task2 = await task_repo.create(
            project_id=sample_project.id,
            title="In Progress Task",
        )
        await task_repo.update_status(task2.id, TaskStatus.IN_PROGRESS)

        todo_result = await task_repo.get_by_project(
            sample_project.id, status=TaskStatus.TODO
        )
        in_progress_result = await task_repo.get_by_project(
            sample_project.id, status=TaskStatus.IN_PROGRESS
        )

        assert all(t.status == TaskStatus.TODO for t in todo_result.items)
        assert all(t.status == TaskStatus.IN_PROGRESS for t in in_progress_result.items)

    async def test_search_tasks_filters(
        self, task_repo: TaskRepository, sample_project
    ):
        """Test searching tasks with filters."""
        task_alpha = await task_repo.create(
            project_id=sample_project.id,
            title="Alpha Task",
            description="Backend work",
            tags=["backend"],
        )
        task_beta = await task_repo.create(
            project_id=sample_project.id,
            title="Beta Task",
            description="Frontend work",
            tags=["frontend"],
        )

        result = await task_repo.search(query="Alpha")
        assert any(t.id == task_alpha.id for t in result.items)
        assert all(t.id != task_beta.id for t in result.items)

        tag_result = await task_repo.search(tags=["frontend"])
        assert any(t.id == task_beta.id for t in tag_result.items)

    async def test_ready_tasks_respects_dependencies(
        self, task_repo: TaskRepository, sample_project
    ):
        """Test ready tasks exclude blocked dependencies."""
        blocker = await task_repo.create(
            project_id=sample_project.id,
            title="Blocking Task",
        )
        blocked = await task_repo.create(
            project_id=sample_project.id,
            title="Blocked Task",
        )
        await task_repo.add_dependency(
            task_id=blocked.id,
            depends_on_id=blocker.id,
            dependency_type=DependencyType.BLOCKS,
        )

        ready = await task_repo.get_ready_tasks(project_id=sample_project.id)
        assert blocker.id in [t.id for t in ready.items]
        assert blocked.id not in [t.id for t in ready.items]

        await task_repo.complete(blocker.id, notes="Done")
        ready_after = await task_repo.get_ready_tasks(project_id=sample_project.id)
        assert blocked.id in [t.id for t in ready_after.items]

    async def test_stale_tasks(self, task_repo: TaskRepository, sample_project):
        """Test stale task detection."""
        task = await task_repo.create(
            project_id=sample_project.id,
            title="Old Task",
        )

        stale_time = task.updated_at - timedelta(days=30)
        await task_repo.db.execute(
            "UPDATE tasks SET updated_at = ? WHERE id = ?",
            (stale_time.isoformat(), task.id),
        )
        await task_repo.db.commit()

        result = await task_repo.get_stale_tasks(
            project_id=sample_project.id,
            stale_after_days=14,
        )
        assert task.id in [t.id for t in result.items]

    async def test_add_dependency(self, task_repo: TaskRepository, sample_project):
        """Test adding task dependency."""
        task1 = await task_repo.create(
            project_id=sample_project.id,
            title="First Task",
        )
        task2 = await task_repo.create(
            project_id=sample_project.id,
            title="Dependent Task",
        )

        dependency = await task_repo.add_dependency(
            task_id=task2.id,
            depends_on_id=task1.id,
            dependency_type=DependencyType.BLOCKS,
        )

        assert dependency is not None
        assert dependency.task_id == task2.id
        assert dependency.depends_on_id == task1.id

    async def test_add_dependency_in_transaction_requires_owned_transaction(
        self, task_repo: TaskRepository, sample_project
    ) -> None:
        """Internal dependency helpers must fail loudly without transaction ownership."""
        blocker = await task_repo.create(
            project_id=sample_project.id,
            title="Blocker",
        )
        dependent = await task_repo.create(
            project_id=sample_project.id,
            title="Dependent",
        )

        with pytest.raises(RuntimeError, match="requires an active transaction"):
            await task_repo._add_dependency_in_transaction(dependent.id, blocker.id)

    async def test_add_dependency_rolls_back_when_event_append_fails(
        self, task_repo: TaskRepository, sample_project, monkeypatch: pytest.MonkeyPatch
    ):
        """Dependency insert should roll back if event append fails."""
        blocker = await task_repo.create(
            project_id=sample_project.id,
            title="Blocker",
        )
        dependent = await task_repo.create(
            project_id=sample_project.id,
            title="Dependent",
        )

        async def fail_append(*args, **kwargs):
            raise RuntimeError("event append failed")

        monkeypatch.setattr(task_repo.events, "append", fail_append)

        with pytest.raises(RuntimeError, match="event append failed"):
            await task_repo.add_dependency(dependent.id, blocker.id)

        dependencies = await task_repo.get_dependencies(dependent.id)
        assert dependencies == []

    async def test_circular_dependency_detection(
        self, task_repo: TaskRepository, sample_project
    ):
        """Test that circular dependencies are rejected."""
        task1 = await task_repo.create(
            project_id=sample_project.id,
            title="Task A",
        )
        task2 = await task_repo.create(
            project_id=sample_project.id,
            title="Task B",
        )

        # A depends on B
        await task_repo.add_dependency(task1.id, task2.id)

        # B depends on A should fail
        with pytest.raises(ValueError, match="circular"):
            await task_repo.add_dependency(task2.id, task1.id)

    async def test_get_dependencies(self, task_repo: TaskRepository, sample_project):
        """Test getting task dependencies."""
        task1 = await task_repo.create(
            project_id=sample_project.id,
            title="Dependency",
        )
        task2 = await task_repo.create(
            project_id=sample_project.id,
            title="Main Task",
        )
        await task_repo.add_dependency(task2.id, task1.id)

        dependencies = await task_repo.get_dependencies(task2.id)

        assert len(dependencies) == 1
        assert dependencies[0].depends_on_id == task1.id

    async def test_get_dependents(self, task_repo: TaskRepository, sample_project):
        """Test getting tasks that depend on a task."""
        task1 = await task_repo.create(
            project_id=sample_project.id,
            title="Blocker",
        )
        task2 = await task_repo.create(
            project_id=sample_project.id,
            title="Blocked Task",
        )
        await task_repo.add_dependency(task2.id, task1.id)

        dependents = await task_repo.get_dependents(task1.id)

        assert len(dependents) == 1
        assert dependents[0].task_id == task2.id

    async def test_remove_dependency(self, task_repo: TaskRepository, sample_project):
        """Test removing a dependency."""
        task1 = await task_repo.create(
            project_id=sample_project.id,
            title="Task 1",
        )
        task2 = await task_repo.create(
            project_id=sample_project.id,
            title="Task 2",
        )
        await task_repo.add_dependency(task2.id, task1.id)

        removed = await task_repo.remove_dependency(task2.id, task1.id)

        assert removed is True
        dependencies = await task_repo.get_dependencies(task2.id)
        assert len(dependencies) == 0

    async def test_remove_dependency_rolls_back_when_event_append_fails(
        self, task_repo: TaskRepository, sample_project, monkeypatch: pytest.MonkeyPatch
    ):
        """Dependency delete should roll back if event append fails."""
        blocker = await task_repo.create(
            project_id=sample_project.id,
            title="Task 1",
        )
        dependent = await task_repo.create(
            project_id=sample_project.id,
            title="Task 2",
        )
        await task_repo.add_dependency(dependent.id, blocker.id)

        async def fail_append(*args, **kwargs):
            raise RuntimeError("event append failed")

        monkeypatch.setattr(task_repo.events, "append", fail_append)

        with pytest.raises(RuntimeError, match="event append failed"):
            await task_repo.remove_dependency(dependent.id, blocker.id)

        dependencies = await task_repo.get_dependencies(dependent.id)
        assert len(dependencies) == 1
        assert dependencies[0].depends_on_id == blocker.id

    async def test_get_with_context(
        self, task_repo: TaskRepository, sample_project, sample_task
    ):
        """Test getting task with full context."""
        context = await task_repo.get_with_context(sample_task.id)

        assert context is not None
        assert context.task.id == sample_task.id
        assert context.project_name == sample_project.name
        assert isinstance(context.subtasks, list)
        assert isinstance(context.dependencies, list)

    async def test_subtasks(self, task_repo: TaskRepository, sample_project):
        """Test creating and retrieving subtasks."""
        parent = await task_repo.create(
            project_id=sample_project.id,
            title="Parent Task",
        )
        child1 = await task_repo.create(
            project_id=sample_project.id,
            title="Child 1",
            parent_id=parent.id,
        )
        child2 = await task_repo.create(
            project_id=sample_project.id,
            title="Child 2",
            parent_id=parent.id,
        )

        subtasks = await task_repo.get_subtasks(parent.id)

        assert len(subtasks) == 2
        assert {s.title for s in subtasks} == {"Child 1", "Child 2"}

    async def test_task_history(self, task_repo: TaskRepository, sample_task):
        """Test task revision history."""
        # Make updates
        await task_repo.update_status(sample_task.id, TaskStatus.IN_PROGRESS)
        await task_repo.complete(sample_task.id, notes="Completed")

        history = await task_repo.get_history(sample_task.id)

        assert len(history) >= 3  # Create + status change + complete

    async def test_update_status_rolls_back_transition_log_when_projection_fails(
        self,
        db,
        task_repo: TaskRepository,
        sample_task,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Late projection failure must not leave an extra task status transition row."""
        baseline_count_row = await db.fetch_one(
            """
            SELECT COUNT(*) AS count
            FROM state_transition_log
            WHERE entity_type = ? AND entity_id = ?
            """,
            ("task_status", sample_task.id),
        )
        baseline_count = baseline_count_row["count"] if baseline_count_row else 0

        async def fail_projection(model, is_create: bool) -> None:
            raise RuntimeError("projection update failed")

        monkeypatch.setattr(task_repo, "_update_projection", fail_projection)

        with pytest.raises(RuntimeError, match="projection update failed"):
            await task_repo.update_status(sample_task.id, TaskStatus.IN_PROGRESS)

        reloaded = await task_repo.get_by_id(sample_task.id)
        assert reloaded is not None
        assert reloaded.status == TaskStatus.TODO
        assert await task_repo.events.get_events("task", sample_task.id) != []
        assert await task_repo.revisions.get_revision_count("task", sample_task.id) == 1

        transition_count_row = await db.fetch_one(
            """
            SELECT COUNT(*) AS count
            FROM state_transition_log
            WHERE entity_type = ? AND entity_id = ?
            """,
            ("task_status", sample_task.id),
        )
        assert transition_count_row is not None
        assert transition_count_row["count"] == baseline_count


@pytest.mark.asyncio
async def test_event_sourced_delete_rolls_back_when_projection_delete_fails(
    db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delete must not leave orphaned delete events or revisions on projection failure."""
    repo = SavedSearchRepository(db)
    saved = await repo.create(name="Delete Rollback Search")

    original_execute = db.execute

    async def fail_projection_delete(query: str, parameters=()):
        normalized = " ".join(query.split()).lower()
        if normalized.startswith("update saved_searches set archived_at = ?"):
            raise RuntimeError("projection delete failed")
        return await original_execute(query, parameters)

    monkeypatch.setattr(db, "execute", fail_projection_delete)

    with pytest.raises(RuntimeError, match="projection delete failed"):
        await repo.delete(saved.id)

    row = await db.fetch_one(
        "SELECT archived_at FROM saved_searches WHERE id = ?",
        (saved.id,),
    )
    assert row is not None
    assert row["archived_at"] is None
    assert len(await repo.events.get_events("saved_search", saved.id)) == 1
    assert await repo.revisions.get_revision_count("saved_search", saved.id) == 1


@pytest.mark.asyncio
async def test_event_sourced_restore_rolls_back_when_projection_restore_fails(
    db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Restore must roll back event/revision writes when projection restore fails."""
    repo = SavedSearchRepository(db)
    saved = await repo.create(name="Restore Rollback Search")
    assert await repo.delete(saved.id)

    original_execute = db.execute

    async def fail_projection_restore(query: str, parameters=()):
        normalized = " ".join(query.split()).lower()
        if normalized.startswith("update saved_searches set archived_at = null"):
            raise RuntimeError("projection restore failed")
        return await original_execute(query, parameters)

    monkeypatch.setattr(db, "execute", fail_projection_restore)

    with pytest.raises(RuntimeError, match="projection restore failed"):
        await repo.restore(saved.id)

    row = await db.fetch_one(
        "SELECT archived_at FROM saved_searches WHERE id = ?",
        (saved.id,),
    )
    assert row is not None
    assert row["archived_at"] is not None
    assert len(await repo.events.get_events("saved_search", saved.id)) == 2
    assert await repo.revisions.get_revision_count("saved_search", saved.id) == 2


@pytest.mark.asyncio
class TestOrganizationRepository:
    """Tests for OrganizationRepository."""

    async def test_create_organization(self, organization_repo: OrganizationRepository):
        """Test creating an organization."""
        org = await organization_repo.create(
            name="Repo Org",
            description="Org from repo",
            owner="owner@example.com",
            members=["owner@example.com"],
            tags=["platform"],
        )

        assert org.id is not None
        assert org.name == "Repo Org"
        assert org.status == OrganizationStatus.ACTIVE
        assert org.owner == "owner@example.com"

    async def test_get_by_name(
        self, organization_repo: OrganizationRepository, sample_organization
    ):
        """Test retrieving organization by name."""
        retrieved = await organization_repo.get_by_name(sample_organization.name)

        assert retrieved is not None
        assert retrieved.id == sample_organization.id

    async def test_update_organization(
        self, organization_repo: OrganizationRepository, sample_organization
    ):
        """Test updating an organization."""
        updated = await organization_repo.update(
            org_id=sample_organization.id,
            description="Updated org",
            status=OrganizationStatus.ARCHIVED,
        )

        assert updated is not None
        assert updated.description == "Updated org"
        assert updated.status == OrganizationStatus.ARCHIVED

    async def test_get_by_status(
        self, organization_repo: OrganizationRepository, sample_organization
    ):
        """Test filtering organizations by status."""
        result = await organization_repo.get_by_status(OrganizationStatus.ACTIVE)
        org_names = [o.name for o in result.items]
        assert sample_organization.name in org_names

    async def test_create_organization_rolls_back_when_member_sync_fails(
        self,
        organization_repo: OrganizationRepository,
        sample_actor,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Direct repo create must roll back if member sync fails."""
        created_org_id: str | None = None

        async def fail_member_sync(organization: Organization) -> None:
            nonlocal created_org_id
            created_org_id = organization.id
            raise RuntimeError(
                f"member sync failed for {list(organization.member_ids)!r}"
            )

        monkeypatch.setattr(organization_repo, "_sync_members", fail_member_sync)

        with pytest.raises(RuntimeError, match="member sync failed"):
            await organization_repo.create(
                name="Rollback Org",
                owner="owner@example.com",
                owner_id=sample_actor.id,
                members=["owner@example.com"],
                member_ids=[sample_actor.id],
            )

        assert created_org_id is not None
        assert await organization_repo.get_by_id(created_org_id) is None
        assert (
            await organization_repo.events.get_events("organization", created_org_id)
            == []
        )
        assert (
            await organization_repo.revisions.get_revision_count(
                "organization", created_org_id
            )
            == 0
        )

    async def test_update_organization_rolls_back_when_member_sync_fails(
        self,
        organization_repo: OrganizationRepository,
        sample_organization,
        sample_actor,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Direct repo update must roll back if member sync fails."""

        async def fail_member_sync(organization: Organization) -> None:
            raise RuntimeError(
                f"member sync failed for {list(organization.member_ids)!r}"
            )

        monkeypatch.setattr(organization_repo, "_sync_members", fail_member_sync)

        with pytest.raises(RuntimeError, match="member sync failed"):
            await organization_repo.update(
                org_id=sample_organization.id,
                description="Should Roll Back",
                members=["owner@example.com"],
                member_ids=[sample_actor.id],
            )

        reloaded = await organization_repo.get_by_id(sample_organization.id)
        assert reloaded is not None
        assert reloaded.description == sample_organization.description
        assert await organization_repo.events.get_events(
            "organization", sample_organization.id
        )
        assert (
            await organization_repo.revisions.get_revision_count(
                "organization", sample_organization.id
            )
            == 1
        )


@pytest.mark.asyncio
class TestTeamRepository:
    """Tests for TeamRepository."""

    async def test_create_team(self, team_repo: TeamRepository, sample_organization):
        """Test creating a team."""
        team = await team_repo.create(
            name="Repo Team",
            org_id=sample_organization.id,
            description="Team from repo",
            owner="lead@example.com",
            members=["lead@example.com"],
            tags=["delivery"],
        )

        assert team.id is not None
        assert team.org_id == sample_organization.id
        assert team.status == TeamStatus.ACTIVE

    async def test_get_by_org(self, team_repo: TeamRepository, sample_team):
        """Test listing teams by org."""
        result = await team_repo.get_by_org(sample_team.org_id)
        team_ids = [t.id for t in result.items]
        assert sample_team.id in team_ids

    async def test_update_team(self, team_repo: TeamRepository, sample_team):
        """Test updating a team."""
        updated = await team_repo.update(
            team_id=sample_team.id,
            status=TeamStatus.ARCHIVED,
        )
        assert updated is not None
        assert updated.status == TeamStatus.ARCHIVED

    async def test_create_team_rolls_back_when_member_sync_fails(
        self,
        team_repo: TeamRepository,
        sample_organization,
        sample_actor,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Direct repo create must roll back if member sync fails."""
        created_team_id: str | None = None

        async def fail_member_sync(team: Team) -> None:
            nonlocal created_team_id
            created_team_id = team.id
            raise RuntimeError(f"member sync failed for {list(team.member_ids)!r}")

        monkeypatch.setattr(team_repo, "_sync_members", fail_member_sync)

        with pytest.raises(RuntimeError, match="member sync failed"):
            await team_repo.create(
                name="Rollback Team",
                org_id=sample_organization.id,
                owner="lead@example.com",
                owner_id=sample_actor.id,
                members=["lead@example.com"],
                member_ids=[sample_actor.id],
            )

        assert created_team_id is not None
        assert await team_repo.get_by_id(created_team_id) is None
        assert await team_repo.events.get_events("team", created_team_id) == []
        assert (
            await team_repo.revisions.get_revision_count("team", created_team_id) == 0
        )

    async def test_update_team_rolls_back_when_member_sync_fails(
        self,
        team_repo: TeamRepository,
        sample_team,
        sample_actor,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Direct repo update must roll back if member sync fails."""

        async def fail_member_sync(team: Team) -> None:
            raise RuntimeError(f"member sync failed for {list(team.member_ids)!r}")

        monkeypatch.setattr(team_repo, "_sync_members", fail_member_sync)

        with pytest.raises(RuntimeError, match="member sync failed"):
            await team_repo.update(
                team_id=sample_team.id,
                description="Should Roll Back",
                members=["lead@example.com"],
                member_ids=[sample_actor.id],
            )

        reloaded = await team_repo.get_by_id(sample_team.id)
        assert reloaded is not None
        assert reloaded.description == sample_team.description
        assert await team_repo.events.get_events("team", sample_team.id)
        assert await team_repo.revisions.get_revision_count("team", sample_team.id) == 1


@pytest.mark.asyncio
class TestPortfolioRepository:
    """Tests for PortfolioRepository."""

    async def test_create_portfolio(
        self, portfolio_repo: PortfolioRepository, sample_organization
    ):
        """Test creating a portfolio."""
        portfolio = await portfolio_repo.create(
            name="Repo Portfolio",
            org_id=sample_organization.id,
            description="Portfolio from repo",
            owner="owner@example.com",
            goal_ids=[],
            objective_ids=[],
            tags=["okrs"],
        )

        assert portfolio.id is not None
        assert portfolio.org_id == sample_organization.id
        assert portfolio.status == PortfolioStatus.ACTIVE

    async def test_create_portfolio_in_transaction_requires_owned_transaction(
        self, portfolio_repo: PortfolioRepository, sample_organization
    ) -> None:
        """Internal portfolio create helpers must fail loudly without ownership."""
        with pytest.raises(RuntimeError, match="requires an active transaction"):
            await portfolio_repo._create_in_transaction(
                name="Unsafe Portfolio",
                org_id=sample_organization.id,
            )

    async def test_get_by_org(
        self, portfolio_repo: PortfolioRepository, sample_portfolio
    ):
        """Test listing portfolios by org."""
        result = await portfolio_repo.get_by_org(sample_portfolio.org_id)
        portfolio_ids = [p.id for p in result.items]
        assert sample_portfolio.id in portfolio_ids

    async def test_update_portfolio(
        self, portfolio_repo: PortfolioRepository, sample_portfolio
    ):
        """Test updating a portfolio."""
        updated = await portfolio_repo.update(
            portfolio_id=sample_portfolio.id,
            status=PortfolioStatus.ARCHIVED,
        )
        assert updated is not None
        assert updated.status == PortfolioStatus.ARCHIVED

    async def test_update_portfolio_in_transaction_requires_owned_transaction(
        self, portfolio_repo: PortfolioRepository, sample_portfolio
    ) -> None:
        """Internal portfolio update helpers must fail loudly without ownership."""
        with pytest.raises(RuntimeError, match="requires an active transaction"):
            await portfolio_repo._update_in_transaction(
                portfolio_id=sample_portfolio.id,
                description="Unsafe update",
            )

    async def test_sync_portfolio_links_in_transaction_requires_owned_transaction(
        self, portfolio_repo: PortfolioRepository, sample_portfolio
    ) -> None:
        """Internal portfolio link sync helpers must fail loudly without ownership."""
        with pytest.raises(RuntimeError, match="requires an active transaction"):
            await portfolio_repo._sync_goal_links_in_transaction(
                sample_portfolio.id,
                ["goal-1"],
            )

        with pytest.raises(RuntimeError, match="requires an active transaction"):
            await portfolio_repo._sync_objective_links_in_transaction(
                sample_portfolio.id,
                ["objective-1"],
            )

    async def test_create_portfolio_rolls_back_when_goal_link_sync_fails(
        self,
        portfolio_repo: PortfolioRepository,
        sample_organization,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Direct repo create must roll back save work if strategic link sync fails."""
        created_portfolio_id: str | None = None

        async def fail_goal_sync(portfolio_id: str, goal_ids: list[str]) -> None:
            nonlocal created_portfolio_id
            created_portfolio_id = portfolio_id
            raise RuntimeError(f"goal link sync failed for {goal_ids!r}")

        monkeypatch.setattr(
            portfolio_repo,
            "_sync_goal_links_in_transaction",
            fail_goal_sync,
        )

        with pytest.raises(RuntimeError, match="goal link sync failed"):
            await portfolio_repo.create(
                name="Rollback Portfolio",
                org_id=sample_organization.id,
                goal_ids=["goal-1"],
            )

        assert created_portfolio_id is not None
        assert await portfolio_repo.get_by_id(created_portfolio_id) is None
        assert (
            await portfolio_repo.events.get_events("portfolio", created_portfolio_id)
            == []
        )
        assert (
            await portfolio_repo.revisions.get_revision_count(
                "portfolio", created_portfolio_id
            )
            == 0
        )

    async def test_update_portfolio_rolls_back_when_goal_link_sync_fails(
        self,
        portfolio_repo: PortfolioRepository,
        sample_portfolio,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Direct repo update must roll back projection/event changes if link sync fails."""

        async def fail_goal_sync(_portfolio_id: str, goal_ids: list[str]) -> None:
            raise RuntimeError(f"goal link sync failed for {goal_ids!r}")

        monkeypatch.setattr(
            portfolio_repo,
            "_sync_goal_links_in_transaction",
            fail_goal_sync,
        )

        with pytest.raises(RuntimeError, match="goal link sync failed"):
            await portfolio_repo.update(
                portfolio_id=sample_portfolio.id,
                description="Should Roll Back",
                goal_ids=["goal-1"],
            )

        reloaded = await portfolio_repo.get_by_id(sample_portfolio.id)
        assert reloaded is not None
        assert reloaded.description == sample_portfolio.description
        assert await portfolio_repo.events.get_events("portfolio", sample_portfolio.id)
        assert (
            await portfolio_repo.revisions.get_revision_count(
                "portfolio", sample_portfolio.id
            )
            == 1
        )


@pytest.mark.asyncio
class TestProgramRepository:
    """Tests for ProgramRepository."""

    async def test_create_program(
        self,
        program_repo: ProgramRepository,
        sample_organization,
        sample_portfolio,
    ):
        """Test creating a program."""
        program = await program_repo.create(
            name="Repo Program",
            org_id=sample_organization.id,
            portfolio_id=sample_portfolio.id,
            description="Program from repo",
            owner="owner@example.com",
            goal_ids=[],
            objective_ids=[],
            tags=["delivery"],
        )

        assert program.id is not None
        assert program.org_id == sample_organization.id
        assert program.portfolio_id == sample_portfolio.id
        assert program.status == ProgramStatus.ACTIVE

    async def test_create_program_in_transaction_requires_owned_transaction(
        self,
        program_repo: ProgramRepository,
        sample_organization,
        sample_portfolio,
    ) -> None:
        """Internal program create helpers must fail loudly without ownership."""
        with pytest.raises(RuntimeError, match="requires an active transaction"):
            await program_repo._create_in_transaction(
                name="Unsafe Program",
                org_id=sample_organization.id,
                portfolio_id=sample_portfolio.id,
            )

    async def test_get_by_portfolio(
        self, program_repo: ProgramRepository, sample_program
    ):
        """Test listing programs by portfolio."""
        result = await program_repo.get_by_portfolio(sample_program.portfolio_id)
        program_ids = [p.id for p in result.items]
        assert sample_program.id in program_ids

    async def test_update_program(
        self, program_repo: ProgramRepository, sample_program
    ):
        """Test updating a program."""
        updated = await program_repo.update(
            program_id=sample_program.id,
            status=ProgramStatus.ARCHIVED,
        )
        assert updated is not None
        assert updated.status == ProgramStatus.ARCHIVED

    async def test_update_program_in_transaction_requires_owned_transaction(
        self, program_repo: ProgramRepository, sample_program
    ) -> None:
        """Internal program update helpers must fail loudly without ownership."""
        with pytest.raises(RuntimeError, match="requires an active transaction"):
            await program_repo._update_in_transaction(
                program_id=sample_program.id,
                description="Unsafe update",
            )

    async def test_sync_program_links_in_transaction_requires_owned_transaction(
        self, program_repo: ProgramRepository, sample_program
    ) -> None:
        """Internal program link sync helpers must fail loudly without ownership."""
        with pytest.raises(RuntimeError, match="requires an active transaction"):
            await program_repo._sync_goal_links_in_transaction(
                sample_program.id,
                ["goal-1"],
            )

        with pytest.raises(RuntimeError, match="requires an active transaction"):
            await program_repo._sync_objective_links_in_transaction(
                sample_program.id,
                ["objective-1"],
            )

    async def test_create_program_rolls_back_when_goal_link_sync_fails(
        self,
        program_repo: ProgramRepository,
        sample_organization,
        sample_portfolio,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Direct repo create must roll back save work if strategic link sync fails."""
        created_program_id: str | None = None

        async def fail_goal_sync(program_id: str, goal_ids: list[str]) -> None:
            nonlocal created_program_id
            created_program_id = program_id
            raise RuntimeError(f"goal link sync failed for {goal_ids!r}")

        monkeypatch.setattr(
            program_repo,
            "_sync_goal_links_in_transaction",
            fail_goal_sync,
        )

        with pytest.raises(RuntimeError, match="goal link sync failed"):
            await program_repo.create(
                name="Rollback Program",
                org_id=sample_organization.id,
                portfolio_id=sample_portfolio.id,
                goal_ids=["goal-1"],
            )

        assert created_program_id is not None
        assert await program_repo.get_by_id(created_program_id) is None
        assert await program_repo.events.get_events("program", created_program_id) == []
        assert (
            await program_repo.revisions.get_revision_count(
                "program", created_program_id
            )
            == 0
        )

    async def test_update_program_rolls_back_when_goal_link_sync_fails(
        self,
        program_repo: ProgramRepository,
        sample_program,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Direct repo update must roll back projection/event changes if link sync fails."""

        async def fail_goal_sync(_program_id: str, goal_ids: list[str]) -> None:
            raise RuntimeError(f"goal link sync failed for {goal_ids!r}")

        monkeypatch.setattr(
            program_repo,
            "_sync_goal_links_in_transaction",
            fail_goal_sync,
        )

        with pytest.raises(RuntimeError, match="goal link sync failed"):
            await program_repo.update(
                program_id=sample_program.id,
                description="Should Roll Back",
                goal_ids=["goal-1"],
            )

        reloaded = await program_repo.get_by_id(sample_program.id)
        assert reloaded is not None
        assert reloaded.description == sample_program.description
        assert await program_repo.events.get_events("program", sample_program.id)
        assert (
            await program_repo.revisions.get_revision_count(
                "program", sample_program.id
            )
            == 1
        )
