"""Pytest fixtures for PMS tests."""

from __future__ import annotations

import asyncio
import os
import re
import signal
import subprocess
import tempfile
import time
from collections.abc import AsyncGenerator, Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pms.config.settings import Settings, reload_settings
from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.db.connection import Database, set_database
from pms.db.schema import initialize_schema
from pms.repositories.actor_repository import ActorRepository
from pms.repositories.api_key_repository import ApiKeyRepository
from pms.repositories.goal_repository import GoalRepository
from pms.repositories.key_result_repository import KeyResultRepository
from pms.repositories.objective_repository import ObjectiveRepository
from pms.repositories.organization_repository import OrganizationRepository
from pms.repositories.plan_repository import PlanRepository
from pms.repositories.portfolio_repository import PortfolioRepository
from pms.repositories.program_repository import ProgramRepository
from pms.repositories.project_repository import ProjectRepository
from pms.repositories.task_repository import TaskRepository
from pms.repositories.team_repository import TeamRepository
from pms.services.auth_service import AuthService

_SERVER_COMMAND_PATTERNS = (
    re.compile(r"-m\s+pms\s+serve(?:\s|$)"),
    re.compile(r"-m\s+uvicorn\s+pms\.api\.app:app(?:\s|$)"),
)


def _workspace_local_server_processes() -> dict[int, tuple[int, str]]:
    """Return workspace-local PMS server processes keyed by PID."""
    repo_root = str(Path(__file__).resolve().parents[1])
    result = subprocess.run(
        ["ps", "-ax", "-o", "pid=,ppid=,command="],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return {}

    processes: dict[int, tuple[int, str]] = {}
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            pid_text, ppid_text, command = line.split(maxsplit=2)
            pid = int(pid_text)
            ppid = int(ppid_text)
        except ValueError:
            continue
        if repo_root not in command:
            continue
        if not any(pattern.search(command) for pattern in _SERVER_COMMAND_PATTERNS):
            continue
        processes[pid] = (ppid, command)
    return processes


def _descendant_pids(processes: dict[int, tuple[int, str]], root_pid: int) -> set[int]:
    """Return descendant PIDs for ``root_pid`` from a ``ps`` snapshot."""
    children: dict[int, set[int]] = {}
    for pid, (ppid, _command) in processes.items():
        children.setdefault(ppid, set()).add(pid)

    descendants: set[int] = set()
    stack = [root_pid]
    while stack:
        parent = stack.pop()
        for child in children.get(parent, set()):
            if child in descendants:
                continue
            descendants.add(child)
            stack.append(child)
    return descendants


def _workspace_local_server_pids(*, ancestor_pid: int | None = None) -> set[int]:
    """Return workspace-local PMS server PIDs currently running.

    When ``ancestor_pid`` is provided, only include server processes descended
    from that PID. This prevents one xdist worker from tearing down another
    worker's local uvicorn process during concurrent integration tests.
    """
    processes = _workspace_local_server_processes()
    if ancestor_pid is None:
        return set(processes)
    return _descendant_pids(processes, ancestor_pid) & set(processes)


def _stop_pid(pid: int, *, timeout_seconds: float = 5.0) -> None:
    """Stop a process robustly during test teardown."""
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            return
        time.sleep(0.1)

    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        return


# Reset global database before each test module
@pytest.fixture(autouse=True)
def reset_global_db():
    """Reset the global database instance before each test."""
    set_database(None)
    yield
    set_database(None)


@pytest.fixture(autouse=True)
def cleanup_workspace_local_server_processes() -> Generator[None]:
    """Stop any workspace-local PMS server processes spawned during a test.

    Tests legitimately start short-lived `pms serve` / `uvicorn pms.api.app:app`
    processes to validate runtime coordination behavior. If teardown misses one,
    it becomes reparented and pollutes later tests and local operator state.

    This fixture snapshots the pre-test server PID set and only kills PIDs that
    appeared during the test under the current worker process, so pre-existing
    user-managed local servers and servers spawned by other xdist workers are
    left alone.
    """

    worker_pid = os.getpid()
    baseline = _workspace_local_server_pids(ancestor_pid=worker_pid)
    yield
    for pid in sorted(_workspace_local_server_pids(ancestor_pid=worker_pid) - baseline):
        _stop_pid(pid)


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop]:
    """Create event loop for session scope."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_dir() -> Generator[Path]:
    """Create a temporary directory for test data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def test_settings(temp_dir: Path) -> Generator[Settings]:
    """Create test settings with temporary database."""
    import os

    # Set environment variables for test
    os.environ["PMS_DATABASE_PATH"] = str(temp_dir / "test.db")
    os.environ["PMS_DATA_DIR"] = str(temp_dir)
    os.environ["PMS_ENV_FILE"] = str(temp_dir / ".env")

    # Reload settings to pick up test config
    settings = reload_settings()
    yield settings

    # Clean up environment
    del os.environ["PMS_DATABASE_PATH"]
    del os.environ["PMS_DATA_DIR"]
    del os.environ["PMS_ENV_FILE"]
    reload_settings()


@pytest.fixture
async def db(temp_dir: Path) -> AsyncGenerator[Database]:
    """Create a test database with the stable schema initialized."""
    db_path = temp_dir / "test.db"
    database = Database(db_path)

    # Set as global database
    set_database(database)

    # Connect and apply schema
    await database.connect()
    await initialize_schema(database)

    yield database

    # Cleanup
    await database.disconnect()


@pytest.fixture
async def event_store(db: Database) -> EventStore:
    """Create an event store for testing."""
    return EventStore(db)


@pytest.fixture
async def revision_store(db: Database) -> RevisionStore:
    """Create a revision store for testing."""
    return RevisionStore(db)


@pytest.fixture
async def metrics_collector(db: Database) -> MetricsCollector:
    """Create a metrics collector for testing."""
    return MetricsCollector(db)


@pytest.fixture
async def project_repo(
    db: Database,
    event_store: EventStore,
    revision_store: RevisionStore,
    metrics_collector: MetricsCollector,
) -> ProjectRepository:
    """Create a project repository for testing."""
    return ProjectRepository(db, event_store, revision_store, metrics_collector)


@pytest.fixture
async def actor_repo(
    db: Database,
    event_store: EventStore,
    revision_store: RevisionStore,
    metrics_collector: MetricsCollector,
) -> ActorRepository:
    """Create an actor repository for testing."""
    return ActorRepository(db, event_store, revision_store, metrics_collector)


@pytest.fixture
async def goal_repo(
    db: Database,
    event_store: EventStore,
    revision_store: RevisionStore,
    metrics_collector: MetricsCollector,
) -> GoalRepository:
    """Create a goal repository for testing."""
    return GoalRepository(db, event_store, revision_store, metrics_collector)


@pytest.fixture
async def objective_repo(
    db: Database,
    event_store: EventStore,
    revision_store: RevisionStore,
    metrics_collector: MetricsCollector,
) -> ObjectiveRepository:
    """Create an objective repository for testing."""
    return ObjectiveRepository(db, event_store, revision_store, metrics_collector)


@pytest.fixture
async def key_result_repo(
    db: Database,
    event_store: EventStore,
    revision_store: RevisionStore,
    metrics_collector: MetricsCollector,
) -> KeyResultRepository:
    """Create a key result repository for testing."""
    return KeyResultRepository(db, event_store, revision_store, metrics_collector)


@pytest.fixture
async def plan_repo(
    db: Database,
    event_store: EventStore,
    revision_store: RevisionStore,
    metrics_collector: MetricsCollector,
) -> PlanRepository:
    """Create a plan repository for testing."""
    return PlanRepository(db, event_store, revision_store, metrics_collector)


@pytest.fixture
async def task_repo(
    db: Database,
    event_store: EventStore,
    revision_store: RevisionStore,
    metrics_collector: MetricsCollector,
) -> TaskRepository:
    """Create a task repository for testing."""
    return TaskRepository(db, event_store, revision_store, metrics_collector)


@pytest.fixture
async def organization_repo(
    db: Database,
    event_store: EventStore,
    revision_store: RevisionStore,
    metrics_collector: MetricsCollector,
) -> OrganizationRepository:
    """Create an organization repository for testing."""
    return OrganizationRepository(db, event_store, revision_store, metrics_collector)


@pytest.fixture
async def team_repo(
    db: Database,
    event_store: EventStore,
    revision_store: RevisionStore,
    metrics_collector: MetricsCollector,
) -> TeamRepository:
    """Create a team repository for testing."""
    return TeamRepository(db, event_store, revision_store, metrics_collector)


@pytest.fixture
async def portfolio_repo(
    db: Database,
    event_store: EventStore,
    revision_store: RevisionStore,
    metrics_collector: MetricsCollector,
) -> PortfolioRepository:
    """Create a portfolio repository for testing."""
    return PortfolioRepository(db, event_store, revision_store, metrics_collector)


@pytest.fixture
async def program_repo(
    db: Database,
    event_store: EventStore,
    revision_store: RevisionStore,
    metrics_collector: MetricsCollector,
) -> ProgramRepository:
    """Create a program repository for testing."""
    return ProgramRepository(db, event_store, revision_store, metrics_collector)


@pytest.fixture
async def sample_project(project_repo: ProjectRepository):
    """Create a sample project for testing."""
    return await project_repo.create(
        name="Test Project",
        description="A project for testing",
        tags=["test", "sample"],
    )


@pytest.fixture
async def sample_task(task_repo: TaskRepository, sample_project):
    """Create a sample task for testing."""
    return await task_repo.create(
        project_id=sample_project.id,
        title="Test Task",
        description="A task for testing",
        tags=["test"],
    )


@pytest.fixture
async def sample_actor(actor_repo: ActorRepository):
    """Create a sample actor for testing."""
    from pms.models.enums import ActorKind

    return await actor_repo.create(
        kind=ActorKind.HUMAN,
        name="Test Actor",
        handle="test-actor",
    )


@pytest.fixture
async def sample_goal(goal_repo: GoalRepository):
    """Create a sample goal for testing."""
    return await goal_repo.create(
        name="Test Goal",
        description="A goal for testing",
    )


@pytest.fixture
async def sample_objective(objective_repo: ObjectiveRepository, sample_goal):
    """Create a sample objective for testing."""
    return await objective_repo.create(
        goal_id=sample_goal.id,
        name="Test Objective",
        description="Objective for testing",
    )


@pytest.fixture
async def sample_plan(plan_repo: PlanRepository, sample_project):
    """Create a sample plan for testing."""
    from pms.models import PlanFormat, PlanStatus

    return await plan_repo.create(
        name="Test Plan",
        description="Plan for testing",
        status=PlanStatus.DRAFT,
        format=PlanFormat.JSON,
        content="{}",
        project_id=sample_project.id,
        task_ids=[],
        tags=["test"],
    )


@pytest.fixture
async def sample_key_result(key_result_repo: KeyResultRepository, sample_objective):
    """Create a sample key result for testing."""
    return await key_result_repo.create(
        objective_id=sample_objective.id,
        name="Test Key Result",
        description="Key result for testing",
    )


@pytest.fixture
async def sample_organization(organization_repo: OrganizationRepository):
    """Create a sample organization for testing."""
    return await organization_repo.create(
        name="Test Organization",
        description="An organization for testing",
        owner="owner@example.com",
        members=["owner@example.com", "member@example.com"],
        tags=["testing"],
    )


@pytest.fixture
async def sample_team(team_repo: TeamRepository, sample_organization):
    """Create a sample team for testing."""
    return await team_repo.create(
        name="Test Team",
        org_id=sample_organization.id,
        description="A team for testing",
        owner="lead@example.com",
        members=["lead@example.com", "member@example.com"],
        tags=["testing"],
    )


@pytest.fixture
async def sample_portfolio(
    portfolio_repo: PortfolioRepository,
    project_repo: ProjectRepository,
    sample_organization,
    sample_project,
    sample_goal,
):
    """Create a sample portfolio for testing."""
    portfolio = await portfolio_repo.create(
        name="Test Portfolio",
        org_id=sample_organization.id,
        description="A portfolio for testing",
        owner="owner@example.com",
        goal_ids=[sample_goal.id],
        objective_ids=[],
        tags=["testing"],
    )
    await project_repo.assign_to_portfolio(sample_project.id, portfolio.id)
    return await portfolio_repo.get_by_id(portfolio.id)


@pytest.fixture
async def sample_program(
    program_repo: ProgramRepository, sample_organization, sample_portfolio
):
    """Create a sample program for testing."""
    return await program_repo.create(
        name="Test Program",
        org_id=sample_organization.id,
        portfolio_id=sample_portfolio.id,
        description="A program for testing",
        owner="owner@example.com",
        goal_ids=[],
        objective_ids=[],
        tags=["testing"],
    )


# Auth fixtures


@pytest.fixture
async def test_db(db: Database) -> Database:
    """Alias for db fixture for clarity in auth tests."""
    return db


@pytest.fixture
async def test_client(db: Database) -> TestClient:
    """Create a FastAPI test client with test database."""
    from pms.api import app as app_module
    from pms.api.app import app
    from pms.api.dependencies import init_services

    # Initialize services with test database
    await init_services(db)

    original_init_database = app_module.init_database

    async def _init_database_override():
        return db

    app_module.init_database = _init_database_override
    app.state.db = db
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app_module.init_database = original_init_database


@pytest.fixture
async def admin_api_key(db: Database) -> str:
    """Create an admin API key for testing."""
    repo = ApiKeyRepository(db)
    service = AuthService(repo)

    plain_key, _ = await service.create_api_key(
        name="Test Admin",
        scopes=["*"],
        expires_in_days=None,
        rate_limit=None,
    )

    return plain_key
