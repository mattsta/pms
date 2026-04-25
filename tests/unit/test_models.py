"""Unit tests for PMS models."""

from datetime import UTC, datetime

from pms.models import (
    Goal,
    GoalHorizon,
    GoalStatus,
    KeyResult,
    Milestone,
    MilestoneStatus,
    Objective,
    Organization,
    OrganizationStatus,
    Plan,
    PlanFormat,
    PlanStatus,
    Portfolio,
    PortfolioStatus,
    Priority,
    Program,
    ProgramStatus,
    Project,
    ProjectStatus,
    Task,
    TaskStatus,
    Team,
    TeamStatus,
)


class TestProject:
    """Tests for Project model."""

    def test_create_project(self):
        """Test project creation with defaults."""
        project = Project(name="Test Project")

        assert project.name == "Test Project"
        assert project.status == ProjectStatus.ACTIVE
        assert project.description is None
        assert project.tags == ()
        assert project.id is not None
        assert project.created_at is not None

    def test_create_project_with_all_fields(self):
        """Test project creation with all fields."""
        project = Project(
            name="Full Project",
            description="A complete project",
            tags=("tag1", "tag2"),
            status=ProjectStatus.ON_HOLD,
        )

        assert project.name == "Full Project"
        assert project.description == "A complete project"
        assert project.tags == ("tag1", "tag2")
        assert project.status == ProjectStatus.ON_HOLD

    def test_project_archive(self):
        """Test archiving a project."""
        project = Project(name="Active Project")
        assert project.status == ProjectStatus.ACTIVE

        project.archive()

        assert project.status == ProjectStatus.ARCHIVED
        assert project.updated_at > project.created_at

    def test_project_complete(self):
        """Test completing a project."""
        project = Project(name="Ongoing Project")

        project.complete()

        assert project.status == ProjectStatus.COMPLETED

    def test_project_to_dict(self):
        """Test serializing project to dict."""
        project = Project(
            name="Dict Project",
            description="For serialization",
            tags=("a", "b"),
        )

        data = project.to_dict()

        assert data["name"] == "Dict Project"
        assert data["description"] == "For serialization"
        assert data["tags"] == ["a", "b"]  # Tuple becomes list
        assert data["status"] == "active"
        assert "id" in data
        assert "created_at" in data


class TestTask:
    """Tests for Task model."""

    def test_create_task(self):
        """Test task creation with defaults."""
        task = Task(project_id="proj-1", title="Test Task")

        assert task.title == "Test Task"
        assert task.project_id == "proj-1"
        assert task.status == TaskStatus.TODO
        assert task.priority == Priority.MEDIUM
        assert task.complexity_points is None

    def test_task_start(self):
        """Test starting a task."""
        task = Task(project_id="proj-1", title="Task to Start")
        assert task.status == TaskStatus.TODO

        task.start()

        assert task.status == TaskStatus.IN_PROGRESS

    def test_task_complete(self):
        """Test completing a task."""
        task = Task(project_id="proj-1", title="Task to Complete")
        task.start()

        task.complete()

        assert task.status == TaskStatus.DONE
        assert task.completed_at is not None

    def test_task_block(self):
        """Test blocking a task."""
        task = Task(project_id="proj-1", title="Task to Block")
        task.start()

        task.block("Waiting for dependencies")

        assert task.status == TaskStatus.BLOCKED

    def test_task_cancel(self):
        """Test cancelling a task."""
        task = Task(project_id="proj-1", title="Task to Cancel")

        task.cancel()

        assert task.status == TaskStatus.CANCELLED

    def test_task_reopen(self):
        """Test reopening a completed task."""
        task = Task(project_id="proj-1", title="Task to Reopen")
        task.start()
        task.complete()
        assert task.status == TaskStatus.DONE

        task.reopen()

        assert task.status == TaskStatus.TODO
        assert task.completed_at is None

    def test_task_submit_for_review(self):
        """Test submitting task for review."""
        task = Task(project_id="proj-1", title="Task for Review")
        task.start()

        task.submit_for_review()

        assert task.status == TaskStatus.IN_REVIEW

    def test_task_is_overdue(self):
        """Test overdue detection."""
        # Not overdue without due date
        task = Task(project_id="proj-1", title="No Due Date")
        assert not task.is_overdue

        # Overdue with past due date
        past_date = datetime(2020, 1, 1, tzinfo=UTC)
        task_past = Task(
            project_id="proj-1",
            title="Past Due",
            due_date=past_date,
        )
        assert task_past.is_overdue

        # Not overdue if completed
        task_past.start()
        task_past.complete()
        assert not task_past.is_overdue

    def test_task_to_dict(self):
        """Test serializing task to dict."""
        task = Task(
            project_id="proj-1",
            title="Dict Task",
            description="For serialization",
            priority=Priority.HIGH,
            actual_hours=2.0,
            tags=("urgent", "bug"),
        )

        data = task.to_dict()

        assert data["title"] == "Dict Task"
        assert data["project_id"] == "proj-1"
        assert data["priority"] == "high"
        assert data["tags"] == ["urgent", "bug"]
        assert data["actual_hours"] == 2.0


class TestGoal:
    """Tests for Goal model."""

    def test_create_goal(self):
        """Test goal creation with defaults."""
        goal = Goal(name="Test Goal")

        assert goal.name == "Test Goal"
        assert goal.status == GoalStatus.ACTIVE
        assert goal.horizon == GoalHorizon.SHORT_TERM
        assert goal.progress_percent == 0

    def test_complete_goal(self):
        """Test completing a goal."""
        goal = Goal(name="Goal to Complete")
        goal.complete()

        assert goal.status == GoalStatus.COMPLETED
        assert goal.progress_percent == 100

    def test_goal_to_dict(self):
        """Test serializing goal to dict."""
        goal = Goal(
            name="Dict Goal",
            description="For serialization",
            horizon=GoalHorizon.LONG_TERM,
            status=GoalStatus.ON_HOLD,
            tags=("a", "b"),
            progress_percent=45,
        )

        data = goal.to_dict()

        assert data["name"] == "Dict Goal"
        assert data["description"] == "For serialization"
        assert data["horizon"] == "long_term"
        assert data["status"] == "on_hold"
        assert data["tags"] == ["a", "b"]
        assert data["progress_percent"] == 45


class TestObjective:
    """Tests for Objective model."""

    def test_create_objective(self):
        """Test objective creation with defaults."""
        objective = Objective(goal_id="goal-1", name="Objective A")

        assert objective.goal_id == "goal-1"
        assert objective.name == "Objective A"
        assert objective.status == GoalStatus.ACTIVE
        assert objective.progress_percent == 0

    def test_complete_objective(self):
        """Test completing an objective."""
        objective = Objective(goal_id="goal-1", name="Objective Complete")
        objective.complete()

        assert objective.status == GoalStatus.COMPLETED
        assert objective.progress_percent == 100


class TestKeyResult:
    """Tests for KeyResult model."""

    def test_create_key_result(self):
        """Test key result creation with defaults."""
        key_result = KeyResult(objective_id="obj-1", name="KR A")

        assert key_result.objective_id == "obj-1"
        assert key_result.name == "KR A"
        assert key_result.status == GoalStatus.ACTIVE
        assert key_result.progress_percent == 0

    def test_complete_key_result(self):
        """Test completing a key result."""
        key_result = KeyResult(objective_id="obj-1", name="KR Complete")
        key_result.complete()

        assert key_result.status == GoalStatus.COMPLETED
        assert key_result.progress_percent == 100


class TestPlan:
    """Tests for Plan model."""

    def test_create_plan_defaults(self):
        """Test plan creation with defaults."""
        plan = Plan(name="Plan A")

        assert plan.name == "Plan A"
        assert plan.status == PlanStatus.DRAFT
        assert plan.format == PlanFormat.JSON
        assert plan.task_ids == ()

    def test_plan_activate(self):
        """Test activating a plan."""
        plan = Plan(name="Plan Activate")
        plan.activate()
        assert plan.status == PlanStatus.ACTIVE

    def test_plan_to_dict(self):
        """Test serializing plan to dict."""
        plan = Plan(
            name="Plan Dict",
            status=PlanStatus.ACTIVE,
            format=PlanFormat.YAML,
            content="steps: []",
            task_ids=("task-1", "task-2"),
            tags=("tag-a",),
        )

        data = plan.to_dict()
        assert data["status"] == "active"
        assert data["format"] == "yaml"
        assert data["task_ids"] == ["task-1", "task-2"]
        assert data["tags"] == ["tag-a"]


class TestOrganization:
    """Tests for Organization model."""

    def test_create_organization(self):
        """Test organization creation with defaults."""
        org = Organization(name="Org One")

        assert org.name == "Org One"
        assert org.status == OrganizationStatus.ACTIVE
        assert org.owner is None
        assert org.members == ()
        assert org.tags == ()

    def test_organization_archive(self):
        """Test archiving an organization."""
        org = Organization(name="Archive Org")
        org.archive()
        assert org.status == OrganizationStatus.ARCHIVED

    def test_organization_to_dict(self):
        """Test serializing organization to dict."""
        org = Organization(
            name="Dict Org",
            owner="owner@example.com",
            members=("alice", "bob"),
            tags=("platform",),
        )

        data = org.to_dict()

        assert data["name"] == "Dict Org"
        assert data["status"] == "active"
        assert data["members"] == ["alice", "bob"]
        assert data["tags"] == ["platform"]


class TestTeam:
    """Tests for Team model."""

    def test_create_team(self):
        """Test team creation with defaults."""
        team = Team(name="Team One", org_id="org-1")

        assert team.name == "Team One"
        assert team.org_id == "org-1"
        assert team.status == TeamStatus.ACTIVE

    def test_team_to_dict(self):
        """Test serializing team to dict."""
        team = Team(
            name="Dict Team",
            org_id="org-1",
            owner="lead@example.com",
            members=("alice", "bob"),
            tags=("infra",),
        )

        data = team.to_dict()

        assert data["name"] == "Dict Team"
        assert data["status"] == "active"
        assert data["members"] == ["alice", "bob"]
        assert data["tags"] == ["infra"]


class TestPortfolio:
    """Tests for Portfolio model."""

    def test_create_portfolio(self):
        """Test portfolio creation with defaults."""
        portfolio = Portfolio(name="Portfolio One", org_id="org-1")

        assert portfolio.name == "Portfolio One"
        assert portfolio.org_id == "org-1"
        assert portfolio.status == PortfolioStatus.ACTIVE

    def test_portfolio_to_dict(self):
        """Test serializing portfolio to dict."""
        portfolio = Portfolio(
            name="Dict Portfolio",
            org_id="org-1",
            project_ids=("proj-1",),
            goal_ids=("goal-1",),
            objective_ids=("obj-1",),
            effective_goal_ids=("goal-1", "goal-2"),
            effective_objective_ids=("obj-1", "obj-2"),
            tags=("okrs",),
        )

        data = portfolio.to_dict()

        assert data["name"] == "Dict Portfolio"
        assert data["status"] == "active"
        assert data["project_ids"] == ["proj-1"]
        assert data["goal_ids"] == ["goal-1"]
        assert data["objective_ids"] == ["obj-1"]
        assert data["effective_goal_ids"] == ["goal-1", "goal-2"]
        assert data["effective_objective_ids"] == ["obj-1", "obj-2"]
        assert data["tags"] == ["okrs"]


class TestProgram:
    """Tests for Program model."""

    def test_create_program(self):
        """Test program creation with defaults."""
        program = Program(name="Program One", org_id="org-1", portfolio_id="port-1")

        assert program.name == "Program One"
        assert program.org_id == "org-1"
        assert program.portfolio_id == "port-1"
        assert program.status == ProgramStatus.ACTIVE

    def test_program_to_dict(self):
        """Test serializing program to dict."""
        program = Program(
            name="Dict Program",
            org_id="org-1",
            portfolio_id="port-1",
            project_ids=("proj-1", "proj-2"),
            goal_ids=("goal-1",),
            objective_ids=("obj-1",),
            effective_goal_ids=("goal-1", "goal-2"),
            effective_objective_ids=("obj-1", "obj-2"),
            tags=("delivery",),
        )

        data = program.to_dict()

        assert data["name"] == "Dict Program"
        assert data["status"] == "active"
        assert data["project_ids"] == ["proj-1", "proj-2"]
        assert data["goal_ids"] == ["goal-1"]
        assert data["objective_ids"] == ["obj-1"]
        assert data["effective_goal_ids"] == ["goal-1", "goal-2"]
        assert data["effective_objective_ids"] == ["obj-1", "obj-2"]
        assert data["tags"] == ["delivery"]


class TestMilestone:
    """Tests for Milestone model."""

    def test_create_milestone(self):
        """Test milestone creation."""
        milestone = Milestone(
            project_id="proj-1",
            name="v1.0 Release",
        )

        assert milestone.name == "v1.0 Release"
        assert milestone.status == MilestoneStatus.PENDING

    def test_milestone_start(self):
        """Test starting a milestone."""
        milestone = Milestone(project_id="proj-1", name="Phase 1")

        milestone.start()

        assert milestone.status == MilestoneStatus.IN_PROGRESS

    def test_milestone_complete(self):
        """Test completing a milestone."""
        milestone = Milestone(project_id="proj-1", name="Phase 1")
        milestone.start()

        milestone.complete()

        assert milestone.status == MilestoneStatus.COMPLETED
        # updated_at should be updated when completed
        assert milestone.updated_at is not None


class TestTaskStatus:
    """Tests for TaskStatus enum."""

    def test_terminal_states(self):
        """Test identification of terminal states."""
        assert TaskStatus.DONE.is_terminal
        assert TaskStatus.CANCELLED.is_terminal
        assert not TaskStatus.TODO.is_terminal
        assert not TaskStatus.IN_PROGRESS.is_terminal
        assert not TaskStatus.BLOCKED.is_terminal

    def test_active_states(self):
        """Test identification of active states."""
        assert TaskStatus.IN_PROGRESS.is_active
        assert TaskStatus.IN_REVIEW.is_active
        assert not TaskStatus.TODO.is_active
        assert not TaskStatus.DONE.is_active
