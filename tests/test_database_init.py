"""Test database initialization and schema bootstrap."""

import asyncio
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from pms.config.settings import reload_settings
from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.db.connection import Database
from pms.db.schema import initialize_schema
from pms.exceptions import ConstraintViolationError
from pms.services.goal_service import GoalService


@pytest.mark.asyncio
async def test_database_connect():
    """Test basic database connection."""
    # Use unique path every time
    db_path = Path(f"/tmp/claude/pms_test_{datetime.now().timestamp()}.db")
    db_path.unlink(missing_ok=True)

    db = Database(db_path)
    await db.connect()

    # Verify connection
    result = await db.fetch_one("SELECT 1 as test")
    assert result is not None
    assert result["test"] == 1

    await db.disconnect()
    print(f"✓ Database connect works: {db_path}")


@pytest.mark.asyncio
async def test_sqlite_connect_applies_configurable_pragmas(
    monkeypatch: pytest.MonkeyPatch,
):
    """SQLite backend should apply PMS-configured concurrency settings."""
    db_path = Path(f"/tmp/claude/pms_sqlite_pragmas_{datetime.now().timestamp()}.db")
    db_path.unlink(missing_ok=True)

    monkeypatch.setenv("PMS_DATABASE_PATH", str(db_path))
    monkeypatch.setenv("PMS_DATA_DIR", str(db_path.parent))
    monkeypatch.setenv("PMS_SQLITE_BUSY_TIMEOUT_MS", "7000")
    monkeypatch.setenv("PMS_SQLITE_JOURNAL_MODE", "WAL")
    monkeypatch.setenv("PMS_SQLITE_SYNCHRONOUS", "FULL")
    reload_settings()

    db = Database(db_path)
    try:
        await db.connect()

        timeout_row = await db.fetch_one("PRAGMA busy_timeout")
        journal_row = await db.fetch_one("PRAGMA journal_mode")
        synchronous_row = await db.fetch_one("PRAGMA synchronous")
        foreign_keys_row = await db.fetch_one("PRAGMA foreign_keys")

        assert timeout_row is not None
        assert journal_row is not None
        assert synchronous_row is not None
        assert foreign_keys_row is not None
        assert timeout_row["timeout"] == 7000
        assert str(journal_row["journal_mode"]).lower() == "wal"
        assert synchronous_row["synchronous"] == 2
        assert foreign_keys_row["foreign_keys"] == 1
    finally:
        await db.disconnect()
        reload_settings()


@pytest.mark.asyncio
async def test_sqlite_backend_retries_transient_lock_errors() -> None:
    """Transient SQLite lock errors should retry before succeeding."""
    backend = Database(Path("/tmp/claude/pms_retry_test.db"))._backend
    assert backend.backend_name == "sqlite"
    sqlite_backend = backend

    class _StubConnection:
        def __init__(self) -> None:
            self.calls = 0

        async def execute(self, query: str, parameters=()):
            self.calls += 1
            if self.calls < 3:
                raise sqlite3.OperationalError("database is locked")
            return query, parameters

    sqlite_backend._connection = _StubConnection()
    sqlite_backend._lock_retry_count = 3
    sqlite_backend._lock_retry_delay_ms = 1

    result = await sqlite_backend.execute("SELECT 1")
    assert result == ("SELECT 1", ())


@pytest.mark.asyncio
async def test_sqlite_nested_transactions_support_savepoints() -> None:
    """Nested SQLite transactions should commit outer work and roll back inner work safely."""
    db_path = Path(f"/tmp/claude/pms_nested_tx_{datetime.now().timestamp()}.db")
    db_path.unlink(missing_ok=True)

    db = Database(db_path)
    await db.connect()
    await db.execute("CREATE TABLE nested_tx_test (id INTEGER PRIMARY KEY, note TEXT)")

    async with db.transaction():
        await db.execute(
            "INSERT INTO nested_tx_test (id, note) VALUES (?, ?)",
            (1, "outer"),
        )

        with pytest.raises(RuntimeError, match="boom"):
            async with db.transaction():
                await db.execute(
                    "INSERT INTO nested_tx_test (id, note) VALUES (?, ?)",
                    (2, "inner"),
                )
                raise RuntimeError("boom")

        await db.execute(
            "INSERT INTO nested_tx_test (id, note) VALUES (?, ?)",
            (3, "after-inner-rollback"),
        )

    rows = await db.fetch_all("SELECT id, note FROM nested_tx_test ORDER BY id")
    assert rows == [
        {"id": 1, "note": "outer"},
        {"id": 3, "note": "after-inner-rollback"},
    ]

    await db.disconnect()


@pytest.mark.asyncio
async def test_sqlite_serializes_concurrent_outer_transactions() -> None:
    """Concurrent tasks should not issue overlapping BEGINs on one SQLite connection."""
    db_path = Path(f"/tmp/claude/pms_concurrent_tx_{datetime.now().timestamp()}.db")
    db_path.unlink(missing_ok=True)

    db = Database(db_path)
    await db.connect()
    await db.execute("CREATE TABLE tx_queue_test (id INTEGER PRIMARY KEY, note TEXT)")

    tx1_started = asyncio.Event()
    release_tx1 = asyncio.Event()
    steps: list[str] = []

    async def tx1() -> None:
        async with db.transaction():
            steps.append("tx1-enter")
            await db.execute(
                "INSERT INTO tx_queue_test (id, note) VALUES (?, ?)",
                (1, "tx1"),
            )
            tx1_started.set()
            await asyncio.wait_for(release_tx1.wait(), timeout=2)
        steps.append("tx1-exit")

    async def tx2() -> None:
        await tx1_started.wait()
        steps.append("tx2-waiting")
        async with db.transaction():
            steps.append("tx2-enter")
            await db.execute(
                "INSERT INTO tx_queue_test (id, note) VALUES (?, ?)",
                (2, "tx2"),
            )
        steps.append("tx2-exit")

    task1 = asyncio.create_task(tx1())
    task2 = asyncio.create_task(tx2())

    await tx1_started.wait()
    await asyncio.sleep(0.05)
    assert not task2.done()

    release_tx1.set()
    await asyncio.gather(task1, task2)

    rows = await db.fetch_all("SELECT id, note FROM tx_queue_test ORDER BY id")
    assert rows == [
        {"id": 1, "note": "tx1"},
        {"id": 2, "note": "tx2"},
    ]
    assert steps.index("tx1-exit") < steps.index("tx2-enter")

    await db.disconnect()


@pytest.mark.asyncio
async def test_sqlite_blocks_non_owner_execute_during_active_transaction() -> None:
    """Non-owner statements should wait instead of joining another task's transaction."""
    db_path = Path(f"/tmp/claude/pms_tx_execute_gate_{datetime.now().timestamp()}.db")
    db_path.unlink(missing_ok=True)

    db = Database(db_path)
    await db.connect()
    await db.execute(
        "CREATE TABLE tx_execute_gate_test (id INTEGER PRIMARY KEY, note TEXT)"
    )

    tx_started = asyncio.Event()
    release_tx = asyncio.Event()

    async def tx_owner() -> None:
        async with db.transaction():
            await db.execute(
                "INSERT INTO tx_execute_gate_test (id, note) VALUES (?, ?)",
                (1, "owner"),
            )
            tx_started.set()
            await asyncio.wait_for(release_tx.wait(), timeout=2)

    owner_task = asyncio.create_task(tx_owner())
    await tx_started.wait()

    write_task = asyncio.create_task(
        db.execute(
            "INSERT INTO tx_execute_gate_test (id, note) VALUES (?, ?)",
            (2, "after-owner"),
        )
    )

    await asyncio.sleep(0.05)
    assert not write_task.done()

    release_tx.set()
    await asyncio.gather(owner_task, write_task)

    rows = await db.fetch_all("SELECT id, note FROM tx_execute_gate_test ORDER BY id")
    assert rows == [
        {"id": 1, "note": "owner"},
        {"id": 2, "note": "after-owner"},
    ]

    await db.disconnect()


@pytest.mark.asyncio
async def test_sqlite_connection_gate_works_across_event_loops() -> None:
    """Shared SQLite access should serialize cleanly even across event-loop threads."""
    db_path = Path(f"/tmp/claude/pms_cross_loop_tx_{datetime.now().timestamp()}.db")
    db_path.unlink(missing_ok=True)

    db = Database(db_path)
    await db.connect()
    await db.execute(
        "CREATE TABLE cross_loop_gate_test (id INTEGER PRIMARY KEY, note TEXT)"
    )

    tx_started = asyncio.Event()
    release_tx = asyncio.Event()

    async def tx_owner() -> None:
        async with db.transaction():
            await db.execute(
                "INSERT INTO cross_loop_gate_test (id, note) VALUES (?, ?)",
                (1, "owner"),
            )
            tx_started.set()
            await asyncio.wait_for(release_tx.wait(), timeout=2)

    def _cross_loop_write() -> None:
        asyncio.run(
            db.execute(
                "INSERT INTO cross_loop_gate_test (id, note) VALUES (?, ?)",
                (2, "other-loop"),
            )
        )

    owner_task = asyncio.create_task(tx_owner())
    await tx_started.wait()

    cross_loop_task = asyncio.create_task(asyncio.to_thread(_cross_loop_write))

    await asyncio.sleep(0.05)
    assert not cross_loop_task.done()

    release_tx.set()
    await asyncio.gather(owner_task, cross_loop_task)

    rows = await db.fetch_all("SELECT id, note FROM cross_loop_gate_test ORDER BY id")
    assert rows == [
        {"id": 1, "note": "owner"},
        {"id": 2, "note": "other-loop"},
    ]

    await db.disconnect()


@pytest.mark.asyncio
async def test_schema_bootstrap():
    """Test schema bootstrap runs successfully."""
    # Unique path
    db_path = Path(f"/tmp/claude/pms_migrate_{datetime.now().timestamp()}.db")
    db_path.unlink(missing_ok=True)

    db = Database(db_path)
    await db.connect()

    # Initialize schema
    await initialize_schema(db)

    # Verify key tables exist
    tables_result = await db.fetch_all(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row["name"] for row in tables_result]

    expected = [
        "products",
        "projects",
        "tasks",
        "milestones",
        "task_state_transitions",
        "task_checkout_log",
        "task_progress_updates",
        "workflow_definitions",
    ]

    for table in expected:
        assert table in tables, f"Missing table: {table}"
        print(f"  ✓ {table}")

    await db.disconnect()
    print(f"\n✓ Schema bootstrap successful on {db_path}")


@pytest.mark.asyncio
async def test_schema_bootstrap_exposes_current_first_release_schema() -> None:
    """Fresh bootstrap should expose the complete first-release schema."""
    db_path = Path(f"/tmp/claude/pms_release_schema_{datetime.now().timestamp()}.db")
    db_path.unlink(missing_ok=True)

    db = Database(db_path)
    await db.connect()
    await initialize_schema(db)

    project_columns = {
        str(row["name"]) for row in await db.fetch_all("PRAGMA table_info(projects)")
    }
    assert {
        "org_id",
        "portfolio_id",
        "program_id",
        "product_id",
        "workflow_id",
        "current_state",
        "workflow_metadata",
    }.issubset(project_columns)

    task_columns = {
        str(row["name"]) for row in await db.fetch_all("PRAGMA table_info(tasks)")
    }
    assert {"actual_hours", "assignee_id", "checkout_actor_id"}.issubset(task_columns)

    goal_columns = {
        str(row["name"]) for row in await db.fetch_all("PRAGMA table_info(goals)")
    }
    objective_columns = {
        str(row["name"]) for row in await db.fetch_all("PRAGMA table_info(objectives)")
    }
    key_result_columns = {
        str(row["name"]) for row in await db.fetch_all("PRAGMA table_info(key_results)")
    }
    product_columns = {
        str(row["name"]) for row in await db.fetch_all("PRAGMA table_info(products)")
    }
    organization_columns = {
        str(row["name"])
        for row in await db.fetch_all("PRAGMA table_info(organizations)")
    }
    team_columns = {
        str(row["name"]) for row in await db.fetch_all("PRAGMA table_info(teams)")
    }
    organization_member_columns = {
        str(row["name"])
        for row in await db.fetch_all("PRAGMA table_info(organization_members)")
    }
    team_member_columns = {
        str(row["name"])
        for row in await db.fetch_all("PRAGMA table_info(team_members)")
    }
    portfolio_columns = {
        str(row["name"]) for row in await db.fetch_all("PRAGMA table_info(portfolios)")
    }
    program_columns = {
        str(row["name"]) for row in await db.fetch_all("PRAGMA table_info(programs)")
    }
    saved_search_columns = {
        str(row["name"])
        for row in await db.fetch_all("PRAGMA table_info(saved_searches)")
    }

    assert "owner_id" in goal_columns
    assert "owner_id" in objective_columns
    assert "owner_id" in key_result_columns
    assert "owner_id" in product_columns
    assert "owner_id" in organization_columns
    assert "owner_id" in team_columns
    assert {"organization_id", "actor_id", "position"}.issubset(
        organization_member_columns
    )
    assert {"team_id", "actor_id", "position"}.issubset(team_member_columns)
    assert "member_ids" not in organization_columns
    assert "member_ids" not in team_columns
    assert "owner_id" in portfolio_columns
    assert "owner_id" in program_columns
    assert "project_ids" not in portfolio_columns
    assert "goal_ids" not in portfolio_columns
    assert "objective_ids" not in portfolio_columns
    assert "project_ids" not in program_columns
    assert "goal_ids" not in program_columns
    assert "objective_ids" not in program_columns
    assert "owner_id" in saved_search_columns

    actor_columns = {
        str(row["name"]) for row in await db.fetch_all("PRAGMA table_info(actors)")
    }
    alias_columns = {
        str(row["name"])
        for row in await db.fetch_all("PRAGMA table_info(actor_aliases)")
    }
    membership_columns = {
        str(row["name"])
        for row in await db.fetch_all("PRAGMA table_info(actor_memberships)")
    }
    assert {"kind", "handle", "normalized_handle", "metadata"}.issubset(actor_columns)
    assert {"actor_id", "normalized_alias"}.issubset(alias_columns)
    assert {"parent_actor_id", "member_actor_id", "role"}.issubset(membership_columns)

    label_category_columns = {
        str(row["name"])
        for row in await db.fetch_all("PRAGMA table_info(label_categories)")
    }
    label_columns = {
        str(row["name"]) for row in await db.fetch_all("PRAGMA table_info(labels)")
    }
    assignment_columns = {
        str(row["name"])
        for row in await db.fetch_all("PRAGMA table_info(label_assignments)")
    }
    job_columns = {
        str(row["name"])
        for row in await db.fetch_all("PRAGMA table_info(plan_test_jobs)")
    }
    plan_task_columns = {
        str(row["name"]) for row in await db.fetch_all("PRAGMA table_info(plan_tasks)")
    }
    plan_test_job_task_columns = {
        str(row["name"])
        for row in await db.fetch_all("PRAGMA table_info(plan_test_job_tasks)")
    }
    network_environment_server_columns = {
        str(row["name"])
        for row in await db.fetch_all("PRAGMA table_info(network_environment_servers)")
    }
    api_key_columns = {
        str(row["name"]) for row in await db.fetch_all("PRAGMA table_info(api_keys)")
    }
    test_server_columns = {
        str(row["name"]): str(row["type"])
        for row in await db.fetch_all("PRAGMA table_info(test_servers)")
    }
    aws_cost_columns = {
        str(row["name"]): str(row["type"])
        for row in await db.fetch_all("PRAGMA table_info(aws_costs)")
    }
    spot_price_columns = {
        str(row["name"]): str(row["type"])
        for row in await db.fetch_all("PRAGMA table_info(spot_price_cache)")
    }
    assert {"archived_at", "last_event_sequence", "last_revision_number"}.issubset(
        label_category_columns
    )
    assert {"network_environment_id", "server_id", "server_role", "position"}.issubset(
        network_environment_server_columns
    )
    assert "task_ids" not in job_columns
    assert "task_ids" not in {
        str(row["name"]) for row in await db.fetch_all("PRAGMA table_info(plans)")
    }
    assert "server_ids" not in {
        str(row["name"])
        for row in await db.fetch_all("PRAGMA table_info(network_environments)")
    }
    assert test_server_columns["hourly_price"].upper() == "REAL"
    assert test_server_columns["estimated_cost"].upper() == "REAL"
    assert aws_cost_columns["cost_usd"].upper() == "REAL"
    assert spot_price_columns["price"].upper() == "REAL"
    assert {"archived_at", "last_event_sequence", "last_revision_number"}.issubset(
        label_columns
    )
    assert {
        "created_at",
        "updated_at",
        "archived_at",
        "last_event_sequence",
        "last_revision_number",
    }.issubset(assignment_columns)
    assert {"archived_at", "last_event_sequence", "last_revision_number"}.issubset(
        job_columns
    )
    assert {"plan_id", "task_id", "position"}.issubset(plan_task_columns)
    assert {"plan_test_job_id", "task_id", "position"}.issubset(
        plan_test_job_task_columns
    )
    assert {
        "updated_at",
        "archived_at",
        "last_event_sequence",
        "last_revision_number",
    }.issubset(api_key_columns)

    result = await db.fetch_all(
        "SELECT id, name, org_id, portfolio_id, program_id FROM projects LIMIT 1"
    )
    assert result == []

    archived_filter_result = await db.fetch_all(
        """
        SELECT la.id
        FROM label_assignments AS la
        WHERE la.archived_at IS NULL
        LIMIT 1
        """
    )
    assert archived_filter_result == []

    await db.disconnect()


@pytest.mark.asyncio
async def test_schema_bootstrap_enforces_foreign_keys_on_tasks() -> None:
    """Fresh schema should reject dangling task.project_id values."""
    db_path = Path(f"/tmp/claude/pms_fk_schema_{datetime.now().timestamp()}.db")
    db_path.unlink(missing_ok=True)

    db = Database(db_path)
    await db.connect()
    await initialize_schema(db)

    now = datetime.now().isoformat()
    with pytest.raises(ConstraintViolationError) as exc_info:
        await db.execute(
            """
            INSERT INTO tasks (id, project_id, title, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("task_fk_missing_project", "proj_missing", "Dangling Task", now, now),
        )

    assert exc_info.value.constraint_kind == "foreign_key"
    await db.disconnect()


@pytest.mark.asyncio
async def test_schema_bootstrap_rejects_invalid_json_on_projects() -> None:
    """Fresh schema should reject malformed JSON for structured columns."""
    db_path = Path(f"/tmp/claude/pms_json_schema_{datetime.now().timestamp()}.db")
    db_path.unlink(missing_ok=True)

    db = Database(db_path)
    await db.connect()
    await initialize_schema(db)

    now = datetime.now().isoformat()
    with pytest.raises(ConstraintViolationError) as exc_info:
        await db.execute(
            """
            INSERT INTO projects (
                id, name, description, status, tags, created_at, updated_at,
                last_event_sequence, last_revision_number, workflow_metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "proj_invalid_json",
                "Invalid JSON Project",
                None,
                "active",
                "not-json",
                now,
                now,
                0,
                0,
                "{}",
            ),
        )

    assert exc_info.value.constraint_kind == "check"
    await db.disconnect()


@pytest.mark.asyncio
async def test_schema_bootstrap_rejects_invalid_boolean_flags() -> None:
    """Fresh schema should reject non-boolean integer flags."""
    db_path = Path(f"/tmp/claude/pms_bool_schema_{datetime.now().timestamp()}.db")
    db_path.unlink(missing_ok=True)

    db = Database(db_path)
    await db.connect()
    await initialize_schema(db)

    now = datetime.now().isoformat()
    with pytest.raises(ConstraintViolationError) as exc_info:
        await db.execute(
            """
            INSERT INTO workflow_definitions (
                id, name, description, entity_type, initial_state, terminal_states,
                is_default, created_at, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "wf_invalid_bool",
                "Invalid Bool Workflow",
                None,
                "task",
                "todo",
                '["done"]',
                2,
                now,
                "{}",
            ),
        )

    assert exc_info.value.constraint_kind == "check"
    assert exc_info.value.columns == ["is_default"]
    await db.disconnect()


@pytest.mark.asyncio
async def test_schema_bootstrap_rejects_invalid_remote_ports() -> None:
    """Fresh schema should reject invalid network port values."""
    db_path = Path(f"/tmp/claude/pms_port_schema_{datetime.now().timestamp()}.db")
    db_path.unlink(missing_ok=True)

    db = Database(db_path)
    await db.connect()
    await initialize_schema(db)

    now = datetime.now().isoformat()
    with pytest.raises(ConstraintViolationError) as exc_info:
        await db.execute(
            """
            INSERT INTO remote_hosts (
                id, name, host, port, username, tags, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "remote_bad_port",
                "Bad Port Host",
                "127.0.0.1",
                70000,
                "deploy",
                "[]",
                now,
                now,
            ),
        )

    assert exc_info.value.constraint_kind == "check"
    assert exc_info.value.columns == ["port"]
    await db.disconnect()


@pytest.mark.asyncio
async def test_schema_bootstrap_rejects_invalid_task_status_enum() -> None:
    """Fresh schema should reject task statuses outside the canonical lifecycle."""
    db_path = Path(
        f"/tmp/claude/pms_task_status_schema_{datetime.now().timestamp()}.db"
    )
    db_path.unlink(missing_ok=True)

    db = Database(db_path)
    await db.connect()
    await initialize_schema(db)

    now = datetime.now().isoformat()
    await db.execute(
        """
        INSERT INTO projects (
            id, name, description, status, tags, created_at, updated_at,
            last_event_sequence, last_revision_number, workflow_metadata
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "proj_valid_for_task_status",
            "Task Status Host Project",
            None,
            "active",
            "[]",
            now,
            now,
            0,
            0,
            "{}",
        ),
    )

    with pytest.raises(ConstraintViolationError) as exc_info:
        await db.execute(
            """
            INSERT INTO tasks (
                id, project_id, title, status, priority, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "task_bad_status",
                "proj_valid_for_task_status",
                "Bad status task",
                "queued",
                "medium",
                now,
                now,
            ),
        )

    assert exc_info.value.constraint_kind == "check"
    assert exc_info.value.columns == ["status"]
    await db.disconnect()


@pytest.mark.asyncio
async def test_schema_bootstrap_rejects_invalid_sync_direction_enum() -> None:
    """Fresh schema should reject sync directions outside push/pull."""
    db_path = Path(
        f"/tmp/claude/pms_sync_direction_schema_{datetime.now().timestamp()}.db"
    )
    db_path.unlink(missing_ok=True)

    db = Database(db_path)
    await db.connect()
    await initialize_schema(db)

    now = datetime.now().isoformat()
    await db.execute(
        """
        INSERT INTO projects (
            id, name, description, status, tags, created_at, updated_at,
            last_event_sequence, last_revision_number, workflow_metadata
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "proj_valid_for_sync",
            "Sync Host Project",
            None,
            "active",
            "[]",
            now,
            now,
            0,
            0,
            "{}",
        ),
    )
    await db.execute(
        """
        INSERT INTO remote_hosts (
            id, name, host, port, username, host_type, tags, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "remote_for_sync",
            "sync-remote",
            "127.0.0.1",
            22,
            "deploy",
            "ssh",
            "[]",
            now,
            now,
        ),
    )
    await db.execute(
        """
        INSERT INTO sync_configs (
            id, project_id, remote_host_id, local_path, remote_path, exclude_patterns,
            sync_mode, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "sync_cfg_valid",
            "proj_valid_for_sync",
            "remote_for_sync",
            ".",
            "/srv/app",
            "[]",
            "mirror",
            now,
            now,
        ),
    )

    with pytest.raises(ConstraintViolationError) as exc_info:
        await db.execute(
            """
            INSERT INTO sync_history (
                id, sync_config_id, direction, status, files_transferred, bytes_transferred,
                started_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "sync_hist_bad_direction",
                "sync_cfg_valid",
                "sideways",
                "started",
                0,
                0,
                now,
            ),
        )

    assert exc_info.value.constraint_kind == "check"
    assert exc_info.value.columns == ["direction"]
    await db.disconnect()


@pytest.mark.asyncio
async def test_schema_bootstrap_rejects_invalid_plan_test_job_mode() -> None:
    """Fresh schema should reject plan test job modes outside local/aws."""
    db_path = Path(f"/tmp/claude/pms_plan_job_mode_{datetime.now().timestamp()}.db")
    db_path.unlink(missing_ok=True)

    db = Database(db_path)
    await db.connect()
    await initialize_schema(db)

    now = datetime.now().isoformat()
    await db.execute(
        """
        INSERT INTO plans (
            id, name, status, format, content, tags, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "plan_for_job_mode",
            "Plan For Invalid Job Mode",
            "draft",
            "json",
            "{}",
            "[]",
            now,
            now,
        ),
    )

    with pytest.raises(ConstraintViolationError) as exc_info:
        await db.execute(
            """
            INSERT INTO plan_test_jobs (
                id, plan_id, name, mode, project_path, test_command, env_vars,
                timeout, capture_logs, save_artifacts, stream_output, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "plan_job_bad_mode",
                "plan_for_job_mode",
                "Bad job mode",
                "remote",
                ".",
                "pytest -q",
                "{}",
                0,
                "[]",
                "[]",
                0,
                now,
                now,
            ),
        )

    assert exc_info.value.constraint_kind == "check"
    assert exc_info.value.columns == ["mode"]
    await db.disconnect()


@pytest.mark.asyncio
async def test_schema_bootstrap_rejects_invalid_custom_field_type() -> None:
    """Fresh schema should reject custom field types outside the canonical set."""
    db_path = Path(f"/tmp/claude/pms_custom_field_type_{datetime.now().timestamp()}.db")
    db_path.unlink(missing_ok=True)

    db = Database(db_path)
    await db.connect()
    await initialize_schema(db)

    now = datetime.now().isoformat()
    with pytest.raises(ConstraintViolationError) as exc_info:
        await db.execute(
            """
            INSERT INTO custom_field_definitions (
                id, name, entity_type, field_type, description, options_json,
                is_required, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "custom_field_bad_type",
                "Deployment Phase",
                "task",
                "markdown",
                None,
                "[]",
                0,
                now,
                now,
            ),
        )

    assert exc_info.value.constraint_kind == "check"
    assert exc_info.value.columns == ["field_type"]
    await db.disconnect()


@pytest.mark.asyncio
async def test_schema_bootstrap_rejects_invalid_work_snapshot_scope_type() -> None:
    """Fresh schema should reject review scopes outside the supported rollup graph."""
    db_path = Path(f"/tmp/claude/pms_snapshot_scope_{datetime.now().timestamp()}.db")
    db_path.unlink(missing_ok=True)

    db = Database(db_path)
    await db.connect()
    await initialize_schema(db)

    now = datetime.now().isoformat()
    with pytest.raises(ConstraintViolationError) as exc_info:
        await db.execute(
            """
            INSERT INTO work_snapshot_reviews (
                id, scope_type, scope_id, reviewed_at, reviewed_by, note, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "snapshot_bad_scope",
                "team",
                "team_scope",
                now,
                "matt",
                None,
                "{}",
            ),
        )

    assert exc_info.value.constraint_kind == "check"
    assert exc_info.value.columns == ["scope_type"]
    await db.disconnect()


@pytest.mark.asyncio
async def test_schema_bootstrap_rejects_invalid_saved_search_scope_type() -> None:
    """Fresh schema should reject saved search scopes outside the supported set."""
    db_path = Path(
        f"/tmp/claude/pms_saved_search_scope_{datetime.now().timestamp()}.db"
    )
    db_path.unlink(missing_ok=True)

    db = Database(db_path)
    await db.connect()
    await initialize_schema(db)

    now = datetime.now().isoformat()
    with pytest.raises(ConstraintViolationError) as exc_info:
        await db.execute(
            """
            INSERT INTO saved_searches (
                id, name, scope_type, filters, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "saved_search_bad_scope",
                "Bad saved search scope",
                "team",
                "{}",
                now,
                now,
            ),
        )

    assert exc_info.value.constraint_kind == "check"
    assert exc_info.value.columns == ["scope_type"]
    await db.disconnect()


@pytest.mark.asyncio
async def test_schema_bootstrap_rejects_invalid_saved_search_sort_dir() -> None:
    """Fresh schema should reject saved search sort directions outside asc/desc."""
    db_path = Path(
        f"/tmp/claude/pms_saved_search_sort_dir_{datetime.now().timestamp()}.db"
    )
    db_path.unlink(missing_ok=True)

    db = Database(db_path)
    await db.connect()
    await initialize_schema(db)

    now = datetime.now().isoformat()
    with pytest.raises(ConstraintViolationError) as exc_info:
        await db.execute(
            """
            INSERT INTO saved_searches (
                id, name, scope_type, filters, sort_dir, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "saved_search_bad_sort",
                "Bad saved search sort",
                "global",
                "{}",
                "sideways",
                now,
                now,
            ),
        )

    assert exc_info.value.constraint_kind == "check"
    assert exc_info.value.columns == ["sort_dir"]
    await db.disconnect()


@pytest.mark.asyncio
async def test_schema_bootstrap_rejects_invalid_automation_rule_action_type() -> None:
    """Fresh schema should reject automation rule action types outside the catalog."""
    db_path = Path(f"/tmp/claude/pms_rule_action_type_{datetime.now().timestamp()}.db")
    db_path.unlink(missing_ok=True)

    db = Database(db_path)
    await db.connect()
    await initialize_schema(db)

    now = datetime.now().isoformat()
    with pytest.raises(ConstraintViolationError) as exc_info:
        await db.execute(
            """
            INSERT INTO automation_rules (
                id, name, event_pattern, action_type, action_payload, enabled,
                cooldown_seconds, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "automation_rule_bad_action",
                "Bad Action Rule",
                "task.*",
                "comment",
                "{}",
                1,
                0,
                now,
                now,
            ),
        )

    assert exc_info.value.constraint_kind == "check"
    assert exc_info.value.columns == ["action_type"]
    assert "must be one of" in str(exc_info.value)
    await db.disconnect()


@pytest.mark.asyncio
async def test_schema_bootstrap_preserves_intentionally_open_vocabulary_fields() -> (
    None
):
    """Fresh schema should still accept representative custom values for open fields."""
    db_path = Path(f"/tmp/claude/pms_open_vocab_{datetime.now().timestamp()}.db")
    db_path.unlink(missing_ok=True)

    db = Database(db_path)
    await db.connect()
    await initialize_schema(db)

    now = datetime.now().isoformat()
    await db.execute(
        """
        INSERT INTO projects (
            id, name, description, status, tags, workflow_metadata,
            created_at, updated_at, last_event_sequence, last_revision_number
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "project_open_vocab",
            "Open Vocabulary Project",
            None,
            "active",
            "[]",
            "{}",
            now,
            now,
            0,
            0,
        ),
    )
    await db.execute(
        """
        INSERT INTO tasks (
            id, project_id, title, description, status, priority, tags,
            workflow_metadata, created_at, updated_at, last_event_sequence,
            last_revision_number
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "task_open_vocab",
            "project_open_vocab",
            "Open Vocabulary Task",
            None,
            "todo",
            "medium",
            "[]",
            "{}",
            now,
            now,
            0,
            0,
        ),
    )
    await db.execute(
        """
        INSERT INTO products (
            id, name, description, status, vision, repository_url, service_urls,
            owner, owner_id, team, tags, product_type, created_at, updated_at,
            last_event_sequence, last_revision_number, workflow_metadata
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "product_open_vocab",
            "Open Vocabulary Product",
            None,
            "active",
            None,
            None,
            "[]",
            None,
            None,
            "[]",
            "[]",
            "internal_capability_mesh",
            now,
            now,
            0,
            0,
            "{}",
        ),
    )
    await db.execute(
        """
        INSERT INTO sessions (
            id, project_id, state, cost_usd, token_count, message_count,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "session_open_vocab",
            "project_open_vocab",
            "{}",
            0,
            0,
            0,
            now,
            now,
        ),
    )

    await db.execute(
        """
        INSERT INTO workflow_definitions (
            id, name, description, entity_type, initial_state, terminal_states,
            is_default, created_at, metadata
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "wf_open_vocab",
            "Open Vocabulary Workflow",
            None,
            "plugin_entity",
            "draft",
            '["published"]',
            0,
            now,
            "{}",
        ),
    )
    await db.execute(
        """
        INSERT INTO automation_rules (
            id, name, event_pattern, action_type, action_payload, enabled,
            cooldown_seconds, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "automation_rule_open_pattern",
            "Open Pattern Rule",
            "vendor.signal.*",
            "add_comment",
            "{}",
            1,
            0,
            now,
            now,
        ),
    )
    await db.execute(
        """
        INSERT INTO task_evidence (
            id, task_id, evidence_type, reference, description, metadata, created_by
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "task_evidence_open_type",
            "task_open_vocab",
            "custom_probe",
            "probe://collector/42",
            None,
            "{}",
            "tester",
        ),
    )
    await db.execute(
        """
        INSERT INTO session_messages (
            id, session_id, role, content, tokens, cost_usd, timestamp, metadata
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "session_message_open_role",
            "session_open_vocab",
            "planner",
            "Open vocabulary role message",
            0,
            0,
            now,
            "{}",
        ),
    )
    await db.execute(
        """
        INSERT INTO activity_log (
            id, session_id, project_id, entity_type, entity_id, action, details,
            user_id, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "activity_log_open_vocab",
            "session_open_vocab",
            "project_open_vocab",
            "plugin_entity",
            "plugin-instance-42",
            "custom_transition",
            "{}",
            "tester",
            now,
        ),
    )

    product_row = await db.fetch_one(
        "SELECT product_type FROM products WHERE id = ?",
        ("product_open_vocab",),
    )
    workflow_row = await db.fetch_one(
        "SELECT entity_type FROM workflow_definitions WHERE id = ?",
        ("wf_open_vocab",),
    )
    session_message_row = await db.fetch_one(
        "SELECT role FROM session_messages WHERE id = ?",
        ("session_message_open_role",),
    )
    activity_row = await db.fetch_one(
        "SELECT entity_type, action FROM activity_log WHERE id = ?",
        ("activity_log_open_vocab",),
    )
    assert product_row is not None
    assert workflow_row is not None
    assert session_message_row is not None
    assert activity_row is not None
    assert product_row["product_type"] == "internal_capability_mesh"
    assert workflow_row["entity_type"] == "plugin_entity"
    assert session_message_row["role"] == "planner"
    assert activity_row["entity_type"] == "plugin_entity"
    assert activity_row["action"] == "custom_transition"

    await db.disconnect()


@pytest.mark.asyncio
async def test_schema_bootstrap_rejects_invalid_automation_rule_run_status() -> None:
    """Fresh schema should reject automation run statuses outside the lifecycle."""
    db_path = Path(f"/tmp/claude/pms_rule_run_status_{datetime.now().timestamp()}.db")
    db_path.unlink(missing_ok=True)

    db = Database(db_path)
    await db.connect()
    await initialize_schema(db)

    now = datetime.now().isoformat()
    await db.execute(
        """
        INSERT INTO automation_rules (
            id, name, event_pattern, action_type, action_payload, enabled,
            cooldown_seconds, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "automation_rule_for_status",
            "Status Host Rule",
            "task.*",
            "add_comment",
            "{}",
            1,
            0,
            now,
            now,
        ),
    )

    with pytest.raises(ConstraintViolationError) as exc_info:
        await db.execute(
            """
            INSERT INTO automation_rule_runs (
                id, rule_id, event_id, status, started_at, completed_at, error, output
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "automation_run_bad_status",
                "automation_rule_for_status",
                None,
                "completed",
                now,
                None,
                None,
                "{}",
            ),
        )

    assert exc_info.value.constraint_kind == "check"
    assert exc_info.value.columns == ["status"]
    await db.disconnect()


@pytest.mark.asyncio
async def test_schema_bootstrap_rejects_invalid_document_type() -> None:
    """Fresh schema should reject document types outside the canonical catalog."""
    db_path = Path(f"/tmp/claude/pms_doc_type_{datetime.now().timestamp()}.db")
    db_path.unlink(missing_ok=True)

    db = Database(db_path)
    await db.connect()
    await initialize_schema(db)

    now = datetime.now().isoformat()
    with pytest.raises(ConstraintViolationError) as exc_info:
        await db.execute(
            """
            INSERT INTO documents (
                id, project_id, doc_type, file_path, title, auto_generated,
                last_generated_at, generation_prompt, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "document_bad_type",
                None,
                "spec",
                "docs/spec.md",
                "Spec",
                0,
                None,
                None,
                now,
                now,
            ),
        )

    assert exc_info.value.constraint_kind == "check"
    assert exc_info.value.columns == ["doc_type"]
    await db.disconnect()


@pytest.mark.asyncio
async def test_schema_bootstrap_rejects_negative_session_counters() -> None:
    """Fresh schema should reject negative session costs and counters."""
    db_path = Path(f"/tmp/claude/pms_session_schema_{datetime.now().timestamp()}.db")
    db_path.unlink(missing_ok=True)

    db = Database(db_path)
    await db.connect()
    await initialize_schema(db)

    now = datetime.now().isoformat()
    with pytest.raises(ConstraintViolationError) as exc_info:
        await db.execute(
            """
            INSERT INTO sessions (
                id, state, cost_usd, token_count, message_count, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "sess_negative_metrics",
                "{}",
                0,
                -1,
                0,
                now,
                now,
            ),
        )

    assert exc_info.value.constraint_kind == "check"
    assert exc_info.value.columns == ["token_count"]
    await db.disconnect()


@pytest.mark.asyncio
async def test_concurrent_goal_rollup_updates_retry_revision_conflicts() -> None:
    """Concurrent objective writes should not fail on duplicate revision numbers."""
    db_path = Path(
        f"/tmp/claude/pms_goal_revision_race_{datetime.now().timestamp()}.db"
    )
    db_path.unlink(missing_ok=True)

    primary_db = Database(db_path)
    await primary_db.connect()
    await initialize_schema(primary_db)

    primary_service = GoalService(
        primary_db,
        EventStore(primary_db),
        RevisionStore(primary_db),
        MetricsCollector(primary_db),
    )
    goal = await primary_service.create_goal(name="Concurrent Goal")

    db_one = Database(db_path)
    db_two = Database(db_path)
    await db_one.connect()
    await db_two.connect()

    service_one = GoalService(
        db_one,
        EventStore(db_one),
        RevisionStore(db_one),
        MetricsCollector(db_one),
    )
    service_two = GoalService(
        db_two,
        EventStore(db_two),
        RevisionStore(db_two),
        MetricsCollector(db_two),
    )

    try:
        results = await asyncio.gather(
            service_one.create_objective(
                goal.id,
                "Objective One",
                progress_percent=20,
            ),
            service_two.create_objective(
                goal.id,
                "Objective Two",
                progress_percent=80,
            ),
        )

        created_names = {result.name for result in results}
        assert created_names == {"Objective One", "Objective Two"}

        verification_db = Database(db_path)
        await verification_db.connect()
        try:
            verification_service = GoalService(
                verification_db,
                EventStore(verification_db),
                RevisionStore(verification_db),
                MetricsCollector(verification_db),
            )
            refreshed_goal = await verification_service.get_goal(goal.id)
            assert refreshed_goal is not None
            assert refreshed_goal.last_revision_number >= 2
            assert refreshed_goal.progress_percent == 50

            objectives = await verification_service.list_objectives(goal.id)
            assert objectives.total_count == 2
        finally:
            await verification_db.disconnect()
    finally:
        await db_one.disconnect()
        await db_two.disconnect()
        await primary_db.disconnect()


@pytest.mark.asyncio
async def test_schema_bootstrap_is_idempotent() -> None:
    """Repeated bootstrap should keep one stable schema record and stay queryable."""
    db_path = Path(f"/tmp/claude/pms_schema_idempotent_{datetime.now().timestamp()}.db")
    db_path.unlink(missing_ok=True)

    db = Database(db_path)
    await db.connect()

    await initialize_schema(db)
    await initialize_schema(db)

    schema_rows = await db.fetch_all(
        "SELECT version, name FROM schema_info ORDER BY version"
    )
    assert schema_rows == [{"version": 1, "name": "stable"}]

    tables = await db.fetch_all(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('projects', 'tasks', 'actors', 'schema_info') ORDER BY name"
    )
    assert [row["name"] for row in tables] == [
        "actors",
        "projects",
        "schema_info",
        "tasks",
    ]

    actor_indexes = await db.fetch_all(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'index' AND tbl_name = 'actors'
        ORDER BY name
        """
    )
    assert any(row["name"] == "idx_actors_kind" for row in actor_indexes)

    await db.disconnect()


if __name__ == "__main__":
    asyncio.run(test_database_connect())
    asyncio.run(test_schema_bootstrap())
