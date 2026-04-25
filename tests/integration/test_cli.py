"""Integration tests for PMS CLI."""

import asyncio
import json
import os
import re
import shlex
import socket
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from click.testing import CliRunner

from pms.cli.app import RuntimeServerPayload, RuntimeWriteDecision, cli

CLI_ARGV0 = "uv run pms"
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")
_PREFIX_LINE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 /_-]*:")
_GENERIC_LOCAL_SERVER_COMMAND = (
    f"{Path(__file__).resolve().parents[2] / '.venv' / 'bin' / 'python'} "
    "-m pms serve --host 127.0.0.1 --port 54132"
)


def _strip_ansi(text: str) -> str:
    return _ANSI_ESCAPE_RE.sub("", text)


def _normalize_cli_output(text: str) -> str:
    return " ".join(_strip_ansi(text).split())


def _assert_plain_output_contains(output: str, *fragments: str) -> str:
    plain_output = _strip_ansi(output)
    for fragment in fragments:
        assert fragment in plain_output
    return plain_output


def _assert_semantic_output_contains(output: str, *fragments: str) -> str:
    normalized_output = _normalize_cli_output(output)
    for fragment in fragments:
        assert _normalize_cli_output(fragment) in normalized_output
    return normalized_output


def _extract_id(output: str) -> str:
    for raw_line in output.splitlines():
        line = _strip_ansi(raw_line)
        if line.strip().startswith("ID:"):
            return line.split("ID:")[-1].strip().rstrip("...")
    raise AssertionError("No ID found in output")


def _extract_api_key(output: str) -> str:
    for line in _strip_ansi(output).splitlines():
        if line.strip().startswith("pms_"):
            return line.strip()
    raise AssertionError("No API key found in output")


def _extract_prefixed_value(output: str, prefix: str) -> str:
    lines = _strip_ansi(output).splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(prefix):
            pieces = []
            value = stripped[len(prefix) :].strip()
            if value:
                pieces.append(value)
            for wrapped_line in lines[index + 1 :]:
                wrapped_value = wrapped_line.strip()
                if not wrapped_value:
                    continue
                if _PREFIX_LINE_RE.match(wrapped_value):
                    break
                pieces.append(wrapped_value)
            if pieces:
                return "".join(pieces)
    raise AssertionError(f"No value found for prefix: {prefix}")


def _age_project_and_task_timestamps(project_name: str, *, days: int) -> None:
    db_path = os.environ["PMS_DATABASE_PATH"]
    stale_at = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE projects SET created_at = ?, updated_at = ? WHERE name = ?",
            (stale_at, stale_at, project_name),
        )
        conn.execute(
            """
            UPDATE tasks
            SET created_at = ?, updated_at = ?, last_progress_update_at = ?
            WHERE project_id IN (SELECT id FROM projects WHERE name = ?)
            """,
            (stale_at, stale_at, stale_at, project_name),
        )
        conn.commit()


_RELATIVE_TIME_RE = re.compile(r"(?:\bin\s+\d+[smhd]|\b\d+[smhd]\s+ago)")
_ISO_TIMESTAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")


def _assert_relative_table_times(output: str) -> None:
    normalized_output = _normalize_cli_output(output)
    table_normalized = re.sub(r"[\u2500-\u257f]+", " ", normalized_output)
    table_normalized = " ".join(table_normalized.split())
    has_iso_timestamp = _ISO_TIMESTAMP_RE.search(table_normalized) is not None
    has_relative_phrase = _RELATIVE_TIME_RE.search(table_normalized) is not None
    has_split_relative_tokens = (
        re.search(r"\b\d+[smhd]\b", table_normalized) is not None
        and "ago" in table_normalized
    )
    if (
        not has_iso_timestamp
        and not has_relative_phrase
        and not has_split_relative_tokens
    ):
        return
    assert has_relative_phrase or has_split_relative_tokens, (
        "Expected relative time output (e.g., '5m ago')"
    )
    for match in _ISO_TIMESTAMP_RE.finditer(table_normalized):
        assert match.start() > 0 and table_normalized[match.start() - 1] == "(", (
            "Table output should only include absolute timestamps inside "
            "relative time values"
        )


def _cli_step(command: str) -> str:
    return f"{CLI_ARGV0} {command}"


def _free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _invoke_runtime_prefer_server_with_retry(
    cli_runner: CliRunner,
    *,
    output_format: str = "json",
    install_client: bool = False,
    attempts: int = 5,
) -> tuple[int, object]:
    """Retry runtime bootstrap when a parallel worker steals the probed free port."""
    last_port: int | None = None
    last_result = None
    for _ in range(attempts):
        port = _free_tcp_port()
        args = [
            "runtime",
            "prefer-server",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ]
        if not install_client:
            args.append("--no-install-client")
        if output_format:
            args.extend(["--format", output_format])
        result = cli_runner.invoke(cli, args)
        if result.exit_code == 0:
            return port, result
        if "Local PMS server did not become ready." not in result.output:
            return port, result
        last_port = port
        last_result = result

    assert last_result is not None
    return last_port, last_result


def _setup_actor_assignment_surface_fixture(cli_runner: CliRunner) -> dict[str, str]:
    project_name = "Actor Surface Project"

    project_result = cli_runner.invoke(cli, ["project", "create", project_name])
    assert project_result.exit_code == 0, project_result.output
    project_id = _extract_id(project_result.output)

    for args in (
        ["actor", "create", "Alice Example", "--kind", "human"],
        ["actor", "create", "Security Persona", "--kind", "persona"],
        [
            "actor",
            "membership",
            "add",
            "security-persona",
            "alice-example",
            "--role",
            "representative",
        ],
    ):
        result = cli_runner.invoke(cli, args)
        assert result.exit_code == 0, result.output

    task_titles = {
        "ready": "Ready Actor Task",
        "stale": "Stale Actor Task",
        "blocker": "Blocking Actor Task",
        "blocked": "Blocked Actor Task",
        "duplicate_a": "Duplicate Actor Task",
        "duplicate_b": "Duplicate Actor Task",
        "in_progress": "In Progress Actor Task",
    }
    task_ids: dict[str, str] = {}
    for key, title in task_titles.items():
        result = cli_runner.invoke(
            cli,
            ["task", "add", project_name, title, "--format", "json"],
        )
        assert result.exit_code == 0, result.output
        task_ids[key] = json.loads(result.output)["task"]["id"]

    dep_result = cli_runner.invoke(
        cli,
        ["task", "dep", "add", task_ids["blocked"], task_ids["blocker"]],
    )
    assert dep_result.exit_code == 0, dep_result.output

    progress_result = cli_runner.invoke(
        cli,
        [
            "task",
            "progress",
            task_ids["in_progress"],
            "35",
            "Started",
            "--by",
            "tester",
        ],
    )
    assert progress_result.exit_code == 0, progress_result.output

    stale_at = (datetime.now(UTC) - timedelta(days=21)).isoformat()
    with sqlite3.connect(os.environ["PMS_DATABASE_PATH"]) as conn:
        assignment_updates = [
            ("alice-example", task_ids["ready"]),
            ("security-persona", task_ids["stale"]),
            ("alice-example", task_ids["blocker"]),
            ("security-persona", task_ids["blocked"]),
            ("alice-example", task_ids["duplicate_a"]),
            ("security-persona", task_ids["duplicate_b"]),
            ("alice-example", task_ids["in_progress"]),
        ]
        conn.executemany(
            "UPDATE tasks SET assignee = ? WHERE id = ?",
            assignment_updates,
        )
        conn.execute(
            """
            UPDATE tasks
            SET created_at = ?, updated_at = ?, last_progress_update_at = ?
            WHERE id = ?
            """,
            (stale_at, stale_at, stale_at, task_ids["stale"]),
        )
        conn.commit()

    return {
        "project_name": project_name,
        "project_id": project_id,
        **task_ids,
    }


def _setup_actor_strategic_fixture(cli_runner: CliRunner) -> dict[str, str]:
    project_name = "Actor Strategic Project"

    init_result = cli_runner.invoke(cli, ["project", "create", project_name])
    assert init_result.exit_code == 0, init_result.output
    project_id = _extract_id(init_result.output)

    for args in (
        ["actor", "create", "Alice Example", "--kind", "human", "--format", "json"],
        [
            "actor",
            "create",
            "Security Persona",
            "--kind",
            "persona",
            "--format",
            "json",
        ],
    ):
        result = cli_runner.invoke(cli, args)
        assert result.exit_code == 0, result.output

    task_result = cli_runner.invoke(
        cli,
        ["task", "add", project_name, "Strategic Focus Task", "--format", "json"],
    )
    assert task_result.exit_code == 0, task_result.output
    task_id = json.loads(task_result.output)["task"]["id"]

    with sqlite3.connect(os.environ["PMS_DATABASE_PATH"]) as conn:
        conn.execute(
            "UPDATE tasks SET assignee = ? WHERE id = ?",
            ("alice-example", task_id),
        )
        conn.commit()

    progress_result = cli_runner.invoke(
        cli,
        [
            "task",
            "progress",
            task_id,
            "45",
            "Execution started",
            "--by",
            "tester",
        ],
    )
    assert progress_result.exit_code == 0, progress_result.output

    goal_result = cli_runner.invoke(
        cli,
        [
            "goal",
            "create",
            "Strategic Goal",
            "--project",
            project_name,
            "--owner",
            "alice-example",
            "--format",
            "json",
        ],
    )
    assert goal_result.exit_code == 0, goal_result.output
    goal_id = json.loads(goal_result.output)["goal"]["id"]

    objective_result = cli_runner.invoke(
        cli,
        [
            "objective",
            "create",
            "Strategic Objective",
            "--goal-id",
            goal_id,
            "--owner",
            "security-persona",
            "--format",
            "json",
        ],
    )
    assert objective_result.exit_code == 0, objective_result.output
    objective_id = json.loads(objective_result.output)["objective"]["id"]

    key_result_result = cli_runner.invoke(
        cli,
        [
            "keyresult",
            "create",
            "Strategic Key Result",
            "--objective-id",
            objective_id,
            "--owner",
            "alice-example",
        ],
    )
    assert key_result_result.exit_code == 0, key_result_result.output
    key_result_id = _extract_id(key_result_result.output)

    plan_result = cli_runner.invoke(
        cli,
        [
            "plan",
            "create",
            "Strategic Plan",
            "--project",
            project_name,
            "--goal-id",
            goal_id,
            "--objective-id",
            objective_id,
            "--task-id",
            task_id,
            "--output-format",
            "json",
        ],
    )
    assert plan_result.exit_code == 0, plan_result.output
    plan_id = json.loads(plan_result.output)["plan"]["id"]

    return {
        "project_name": project_name,
        "project_id": project_id,
        "task_id": task_id,
        "goal_id": goal_id,
        "objective_id": objective_id,
        "key_result_id": key_result_id,
        "plan_id": plan_id,
    }


def _setup_graph_discoverability_fixture(cli_runner: CliRunner) -> dict[str, str]:
    import uuid

    project_name = "Graph Discoverability Project"

    project_result = cli_runner.invoke(cli, ["project", "create", project_name])
    assert project_result.exit_code == 0, project_result.output
    project_id = _extract_id(project_result.output)

    goal_result = cli_runner.invoke(
        cli,
        [
            "goal",
            "create",
            "Graph Goal",
            "--project",
            project_name,
            "--format",
            "json",
        ],
    )
    assert goal_result.exit_code == 0, goal_result.output
    goal_id = json.loads(goal_result.output)["goal"]["id"]

    objective_result = cli_runner.invoke(
        cli,
        [
            "objective",
            "create",
            "Graph Objective",
            "--goal-id",
            goal_id,
            "--format",
            "json",
        ],
    )
    assert objective_result.exit_code == 0, objective_result.output
    objective_id = json.loads(objective_result.output)["objective"]["id"]

    key_result_result = cli_runner.invoke(
        cli,
        [
            "keyresult",
            "create",
            "Graph Key Result",
            "--objective-id",
            objective_id,
        ],
    )
    assert key_result_result.exit_code == 0, key_result_result.output
    key_result_id = _extract_id(key_result_result.output)

    blocker_task_result = cli_runner.invoke(
        cli,
        ["task", "add", project_name, "Graph Blocker Task", "--format", "json"],
    )
    assert blocker_task_result.exit_code == 0, blocker_task_result.output
    blocker_task_id = json.loads(blocker_task_result.output)["task"]["id"]

    parent_task_result = cli_runner.invoke(
        cli,
        ["task", "add", project_name, "Graph Parent Task", "--format", "json"],
    )
    assert parent_task_result.exit_code == 0, parent_task_result.output
    parent_task_id = json.loads(parent_task_result.output)["task"]["id"]

    child_task_result = cli_runner.invoke(
        cli,
        [
            "task",
            "add",
            project_name,
            "Graph Child Task",
            "--parent-id",
            parent_task_id,
            "--format",
            "json",
        ],
    )
    assert child_task_result.exit_code == 0, child_task_result.output
    child_task_id = json.loads(child_task_result.output)["task"]["id"]

    dependency_result = cli_runner.invoke(
        cli,
        ["task", "dep", "add", parent_task_id, blocker_task_id],
    )
    assert dependency_result.exit_code == 0, dependency_result.output

    plan_result = cli_runner.invoke(
        cli,
        [
            "plan",
            "create",
            "Graph Plan",
            "--project",
            project_name,
            "--goal-id",
            goal_id,
            "--objective-id",
            objective_id,
            "--task-id",
            parent_task_id,
            "--task-id",
            child_task_id,
            "--content",
            "{}",
            "--format",
            "json",
            "--output-format",
            "json",
        ],
    )
    assert plan_result.exit_code == 0, plan_result.output
    plan_id = json.loads(plan_result.output)["plan"]["id"]

    milestone_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    with sqlite3.connect(os.environ["PMS_DATABASE_PATH"]) as conn:
        conn.execute(
            """
            INSERT INTO milestones (
                id,
                project_id,
                name,
                description,
                due_date,
                status,
                sort_order,
                created_at,
                updated_at,
                last_event_sequence
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                milestone_id,
                project_id,
                "Graph Milestone",
                "Graph milestone for task context coverage",
                None,
                "pending",
                0,
                now,
                now,
                0,
            ),
        )
        conn.execute(
            "UPDATE tasks SET milestone_id = ? WHERE id = ?",
            (milestone_id, parent_task_id),
        )
        conn.commit()

    return {
        "project_name": project_name,
        "project_id": project_id,
        "goal_id": goal_id,
        "objective_id": objective_id,
        "key_result_id": key_result_id,
        "plan_id": plan_id,
        "blocker_task_id": blocker_task_id,
        "parent_task_id": parent_task_id,
        "child_task_id": child_task_id,
        "milestone_id": milestone_id,
    }


def _setup_actor_management_fixture(cli_runner: CliRunner) -> dict[str, str]:
    for args in (
        ["actor", "create", "Alice Example", "--kind", "human", "--format", "json"],
        [
            "actor",
            "create",
            "Security Persona",
            "--kind",
            "persona",
            "--format",
            "json",
        ],
        ["actor", "alias", "add", "alice-example", "alice", "--format", "json"],
    ):
        result = cli_runner.invoke(cli, args)
        assert result.exit_code == 0, result.output

    product_result = cli_runner.invoke(
        cli,
        [
            "product",
            "create",
            "Actor Product",
            "--owner",
            "alice",
            "--format",
            "json",
        ],
    )
    assert product_result.exit_code == 0, product_result.output
    product_payload = json.loads(product_result.output)

    org_result = cli_runner.invoke(
        cli,
        [
            "org",
            "create",
            "Actor Org",
            "--owner",
            "alice",
            "--member",
            "security-persona",
            "--member",
            "alice",
            "--format",
            "json",
        ],
    )
    assert org_result.exit_code == 0, org_result.output
    org_payload = json.loads(org_result.output)

    team_result = cli_runner.invoke(
        cli,
        [
            "team",
            "create",
            "Actor Team",
            "--org",
            "Actor Org",
            "--owner",
            "security-persona",
            "--member",
            "alice",
            "--format",
            "json",
        ],
    )
    assert team_result.exit_code == 0, team_result.output
    team_payload = json.loads(team_result.output)

    portfolio_result = cli_runner.invoke(
        cli,
        [
            "portfolio",
            "create",
            "Actor Portfolio",
            "--org",
            "Actor Org",
            "--owner",
            "alice",
            "--format",
            "json",
        ],
    )
    assert portfolio_result.exit_code == 0, portfolio_result.output
    portfolio_payload = json.loads(portfolio_result.output)

    program_result = cli_runner.invoke(
        cli,
        [
            "program",
            "create",
            "Actor Program",
            "--org",
            "Actor Org",
            "--portfolio",
            "Actor Portfolio",
            "--owner",
            "security-persona",
            "--format",
            "json",
        ],
    )
    assert program_result.exit_code == 0, program_result.output
    program_payload = json.loads(program_result.output)

    queue_result = cli_runner.invoke(
        cli,
        [
            "queue",
            "create",
            "Actor Queue",
            "--owner",
            "alice",
            "--filters",
            "{}",
            "--format",
            "json",
        ],
    )
    assert queue_result.exit_code == 0, queue_result.output
    queue_payload = json.loads(queue_result.output)

    return {
        "product_id": product_payload["product"]["id"],
        "org_id": org_payload["organization"]["id"],
        "team_id": team_payload["team"]["id"],
        "portfolio_id": portfolio_payload["portfolio"]["id"],
        "program_id": program_payload["program"]["id"],
        "queue_id": queue_payload["queue"]["id"],
    }


def _setup_actor_reporting_fixture(cli_runner: CliRunner) -> dict[str, str]:
    fixture = _setup_actor_assignment_surface_fixture(cli_runner)

    goal_result = cli_runner.invoke(
        cli,
        [
            "goal",
            "create",
            "Actor Reporting Goal",
            "--project",
            fixture["project_name"],
            "--owner",
            "alice-example",
            "--format",
            "json",
        ],
    )
    assert goal_result.exit_code == 0, goal_result.output
    goal_id = json.loads(goal_result.output)["goal"]["id"]

    objective_result = cli_runner.invoke(
        cli,
        [
            "objective",
            "create",
            "Actor Reporting Objective",
            "--goal-id",
            goal_id,
            "--owner",
            "alice-example",
            "--format",
            "json",
        ],
    )
    assert objective_result.exit_code == 0, objective_result.output
    objective_id = json.loads(objective_result.output)["objective"]["id"]

    key_result_result = cli_runner.invoke(
        cli,
        [
            "keyresult",
            "create",
            "Actor Reporting Key Result",
            "--objective-id",
            objective_id,
            "--owner",
            "alice-example",
        ],
    )
    assert key_result_result.exit_code == 0, key_result_result.output
    key_result_id = _extract_id(key_result_result.output)

    product_result = cli_runner.invoke(
        cli,
        [
            "product",
            "create",
            "Actor Reporting Product",
            "--owner",
            "alice-example",
            "--format",
            "json",
        ],
    )
    assert product_result.exit_code == 0, product_result.output
    product_id = json.loads(product_result.output)["product"]["id"]

    org_result = cli_runner.invoke(
        cli,
        [
            "org",
            "create",
            "Actor Reporting Org",
            "--owner",
            "alice-example",
            "--member",
            "alice-example",
            "--format",
            "json",
        ],
    )
    assert org_result.exit_code == 0, org_result.output
    org_id = json.loads(org_result.output)["organization"]["id"]

    queue_result = cli_runner.invoke(
        cli,
        [
            "queue",
            "create",
            "Actor Reporting Queue",
            "--scope-type",
            "project",
            "--scope",
            fixture["project_name"],
            "--owner",
            "alice-example",
            "--filters",
            '{"status":["todo","in_progress"]}',
            "--format",
            "json",
        ],
    )
    assert queue_result.exit_code == 0, queue_result.output
    queue_id = json.loads(queue_result.output)["queue"]["id"]

    return {
        **fixture,
        "goal_id": goal_id,
        "objective_id": objective_id,
        "key_result_id": key_result_id,
        "product_id": product_id,
        "org_id": org_id,
        "queue_id": queue_id,
    }


@pytest.fixture
def cli_runner():
    """Create a CLI test runner."""
    return CliRunner()


@pytest.fixture
def temp_env(tmp_path: Path):
    """Set up temporary environment for CLI tests."""
    import os

    import pms.cli.app as cli_app

    original_env = os.environ.copy()
    original_console = cli_app.console

    os.environ["PMS_DATABASE_PATH"] = str(tmp_path / "test.db")
    os.environ["PMS_DATA_DIR"] = str(tmp_path)
    os.environ["PMS_LOG_DIR"] = str(tmp_path / "logs")
    os.environ["PMS_ENV_FILE"] = str(tmp_path / ".env")
    os.environ["PMS_CLI_ARGV0"] = CLI_ARGV0
    os.environ["PMS_WRITE_MODE"] = "direct"
    os.environ["NO_COLOR"] = "1"
    os.environ.pop("PMS_SERVER_BASE_URL", None)
    os.environ.pop("PMS_API_KEY", None)
    os.environ.pop("PMS_API_KEY_PATH", None)
    console_width = cli_app._resolve_console_width()
    cli_app.console = (
        cli_app.Console(width=console_width, no_color=True)
        if console_width
        else cli_app.Console(no_color=True)
    )

    yield tmp_path

    # Restore original environment
    cli_app.console = original_console
    os.environ.clear()
    os.environ.update(original_env)


class TestVersionCommand:
    """Tests for version command."""

    def test_version(self, cli_runner: CliRunner):
        """Test version command output."""
        result = cli_runner.invoke(cli, ["version"])

        assert result.exit_code == 0
        _assert_plain_output_contains(
            result.output, "PMS - Project Management System", "Version:"
        )


class TestHelpExamples:
    """Tests for dynamic help example rendering."""

    def test_start_help_surfaces_dynamic_examples(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        result = cli_runner.invoke(cli, ["start", "--help"])

        assert result.exit_code == 0
        _assert_plain_output_contains(
            result.output,
            "Examples:",
            _cli_step("start"),
            _cli_step("dashboard --format json"),
        )

    def test_runtime_prefer_server_help_surfaces_dynamic_examples(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        result = cli_runner.invoke(cli, ["runtime", "prefer-server", "--help"])

        assert result.exit_code == 0
        _assert_plain_output_contains(
            result.output,
            "Examples:",
            _cli_step("runtime prefer-server --host 127.0.0.1 --port 27541"),
            _cli_step("config show --format json"),
        )


class TestActorIdentityCommands:
    """Tests for actor identity graph CLI surfaces."""

    def test_actor_create_show_me_and_config_current_actor(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        create_result = cli_runner.invoke(
            cli,
            [
                "actor",
                "create",
                "Alice Example",
                "--kind",
                "human",
                "--format",
                "json",
            ],
        )

        assert create_result.exit_code == 0
        create_payload = json.loads(create_result.output)
        assert create_payload["actor"]["handle"] == "alice-example"

        alias_result = cli_runner.invoke(
            cli,
            [
                "actor",
                "alias",
                "add",
                "alice-example",
                "alice",
                "--format",
                "json",
            ],
        )
        assert alias_result.exit_code == 0

        config_set_result = cli_runner.invoke(
            cli,
            ["config", "set", "--current-actor", "alice-example"],
        )
        assert config_set_result.exit_code == 0
        assert "Current actor: alice-example" in config_set_result.output

        config_show_result = cli_runner.invoke(
            cli,
            ["config", "show", "--format", "json"],
        )
        assert config_show_result.exit_code == 0
        config_payload = json.loads(config_show_result.output)
        assert config_payload["actor"]["current_actor_id"] == "alice-example"

        show_result = cli_runner.invoke(
            cli,
            ["actor", "show", "me", "--format", "json"],
        )
        assert show_result.exit_code == 0
        show_payload = json.loads(show_result.output)
        assert show_payload["actor"]["handle"] == "alice-example"
        aliases = {alias["alias"] for alias in show_payload["aliases"]}
        assert "alice" in aliases
        assert show_payload["links"]["tasks"] == _cli_step(
            "task search --actor alice-example --format json"
        )

    def test_task_mine_uses_current_actor_and_inherited_memberships(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        cli_runner.invoke(cli, ["project", "create", "Identity Project"])
        cli_runner.invoke(cli, ["actor", "create", "Alice Example", "--kind", "human"])
        cli_runner.invoke(
            cli, ["actor", "create", "Security Persona", "--kind", "persona"]
        )
        membership_result = cli_runner.invoke(
            cli,
            [
                "actor",
                "membership",
                "add",
                "security-persona",
                "alice-example",
                "--role",
                "representative",
                "--format",
                "json",
            ],
        )
        assert membership_result.exit_code == 0

        direct_result = cli_runner.invoke(
            cli, ["task", "add", "Identity Project", "Direct Task", "--format", "json"]
        )
        persona_result = cli_runner.invoke(
            cli, ["task", "add", "Identity Project", "Persona Task", "--format", "json"]
        )
        other_result = cli_runner.invoke(
            cli, ["task", "add", "Identity Project", "Other Task", "--format", "json"]
        )
        assert direct_result.exit_code == 0
        assert persona_result.exit_code == 0
        assert other_result.exit_code == 0

        direct_id = json.loads(direct_result.output)["task"]["id"]
        persona_id = json.loads(persona_result.output)["task"]["id"]
        other_id = json.loads(other_result.output)["task"]["id"]

        with sqlite3.connect(os.environ["PMS_DATABASE_PATH"]) as conn:
            conn.execute(
                "UPDATE tasks SET assignee = ? WHERE id = ?",
                ("alice-example", direct_id),
            )
            conn.execute(
                "UPDATE tasks SET assignee = ? WHERE id = ?",
                ("security-persona", persona_id),
            )
            conn.execute(
                "UPDATE tasks SET assignee = ? WHERE id = ?",
                ("someone-else", other_id),
            )
            conn.commit()

        cli_runner.invoke(cli, ["config", "set", "--current-actor", "alice-example"])

        list_result = cli_runner.invoke(
            cli,
            ["task", "list", "--mine", "--format", "json"],
        )
        assert list_result.exit_code == 0
        list_payload = json.loads(list_result.output)
        titles = {item["title"] for item in list_payload["items"]}
        assert "Direct Task" in titles
        assert "Persona Task" in titles
        assert "Other Task" not in titles
        assert list_payload["assignment_scope"]["mode"] == "mine"
        assert list_payload["assignment_scope"]["actor_handle"] == "alice-example"
        assert "--mine" in list_payload["links"]["self"]
        list_items = {item["title"]: item for item in list_payload["items"]}
        assert (
            list_items["Direct Task"]["assignee"]["actor"]["handle"] == "alice-example"
        )
        assert (
            list_items["Persona Task"]["assignee"]["actor"]["handle"]
            == "security-persona"
        )
        assert list_items["Direct Task"]["links"]["actor"] == _cli_step(
            "actor show alice-example --format json"
        )

        search_result = cli_runner.invoke(
            cli,
            ["task", "search", "--mine", "--format", "json"],
        )
        assert search_result.exit_code == 0
        search_payload = json.loads(search_result.output)
        search_titles = {item["title"] for item in search_payload["items"]}
        assert "Direct Task" in search_titles
        assert "Persona Task" in search_titles
        assert "Other Task" not in search_titles
        assert search_payload["assignment_scope"]["actor_handle"] == "alice-example"
        assert "--mine" in search_payload["links"]["self"]
        search_items = {item["title"]: item for item in search_payload["items"]}
        assert (
            search_items["Direct Task"]["assignee"]["actor"]["handle"]
            == "alice-example"
        )
        assert (
            search_items["Persona Task"]["assignee"]["actor"]["handle"]
            == "security-persona"
        )

        actor_show_result = cli_runner.invoke(
            cli,
            ["actor", "show", "alice-example", "--format", "json"],
        )
        assert actor_show_result.exit_code == 0
        actor_payload = json.loads(actor_show_result.output)
        assert actor_payload["workload"]["direct"]["total_tasks"] == 1
        assert actor_payload["workload"]["effective"]["total_tasks"] == 2
        assert actor_payload["workload"]["inherited_only"]["total_tasks"] == 1
        assert actor_payload["workload"]["effective"]["todo_tasks"] == 2
        workload_titles = {item["title"] for item in actor_payload["workload"]["tasks"]}
        assert "Direct Task" in workload_titles
        assert "Persona Task" in workload_titles

        task_show_result = cli_runner.invoke(
            cli,
            ["task", "show", direct_id, "--format", "json"],
        )
        assert task_show_result.exit_code == 0
        task_payload = json.loads(task_show_result.output)
        assert task_payload["assignee"]["ref"] == "alice-example"
        assert task_payload["assignee"]["actor"]["handle"] == "alice-example"
        assert task_payload["links"]["actor"] == _cli_step(
            "actor show alice-example --format json"
        )

        persona_task_show_result = cli_runner.invoke(
            cli,
            ["task", "show", persona_id, "--format", "json"],
        )
        assert persona_task_show_result.exit_code == 0
        persona_task_payload = json.loads(persona_task_show_result.output)
        assert persona_task_payload["assignee"]["actor"]["handle"] == "security-persona"

    def test_actor_assignment_payloads_propagate_to_task_collection_surfaces(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        fixture = _setup_actor_assignment_surface_fixture(cli_runner)

        ready_result = cli_runner.invoke(
            cli,
            ["task", "ready", "--project", fixture["project_name"], "--format", "json"],
        )
        assert ready_result.exit_code == 0, ready_result.output
        ready_payload = json.loads(ready_result.output)
        ready_items = {item["title"]: item for item in ready_payload["items"]}
        assert ready_items["Ready Actor Task"]["assignee"]["actor"]["handle"] == (
            "alice-example"
        )
        assert ready_items["Ready Actor Task"]["links"]["actor"] == _cli_step(
            "actor show alice-example --format json"
        )

        stale_result = cli_runner.invoke(
            cli,
            [
                "task",
                "stale",
                "--project",
                fixture["project_name"],
                "--days",
                "7",
                "--format",
                "json",
            ],
        )
        assert stale_result.exit_code == 0, stale_result.output
        stale_payload = json.loads(stale_result.output)
        stale_items = {item["title"]: item for item in stale_payload["items"]}
        assert stale_items["Stale Actor Task"]["assignee"]["actor"]["handle"] == (
            "security-persona"
        )
        assert stale_items["Stale Actor Task"]["links"]["actor"] == _cli_step(
            "actor show security-persona --format json"
        )

        blocked_result = cli_runner.invoke(
            cli,
            [
                "task",
                "blocked",
                "--project",
                fixture["project_name"],
                "--format",
                "json",
            ],
        )
        assert blocked_result.exit_code == 0, blocked_result.output
        blocked_payload = json.loads(blocked_result.output)
        blocked_items = {item["title"]: item for item in blocked_payload["items"]}
        assert blocked_items["Blocked Actor Task"]["assignee"]["actor"]["handle"] == (
            "security-persona"
        )
        assert blocked_items["Blocked Actor Task"]["links"]["actor"] == _cli_step(
            "actor show security-persona --format json"
        )

        duplicates_result = cli_runner.invoke(
            cli,
            [
                "task",
                "duplicates",
                "--project",
                fixture["project_name"],
                "--format",
                "json",
            ],
        )
        assert duplicates_result.exit_code == 0, duplicates_result.output
        duplicates_payload = json.loads(duplicates_result.output)
        duplicate_group = next(
            group
            for group in duplicates_payload["items"]
            if any(task["title"] == "Duplicate Actor Task" for task in group["tasks"])
        )
        duplicate_task_assignments = {
            task["assignee"]["actor"]["handle"] for task in duplicate_group["tasks"]
        }
        assert duplicate_task_assignments == {"alice-example", "security-persona"}
        assert any(
            task["links"]["actor"]
            == _cli_step("actor show alice-example --format json")
            for task in duplicate_group["tasks"]
        )

    def test_actor_show_includes_ownership_project_workloads_and_graph_navigation(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        fixture = _setup_actor_reporting_fixture(cli_runner)

        actor_show_result = cli_runner.invoke(
            cli,
            ["actor", "show", "alice-example", "--format", "json"],
        )
        assert actor_show_result.exit_code == 0, actor_show_result.output
        payload = json.loads(actor_show_result.output)

        ownership = payload["ownership"]
        assert ownership["counts"]["goals"] == 1
        assert ownership["counts"]["objectives"] == 1
        assert ownership["counts"]["key_results"] == 1
        assert ownership["counts"]["products"] == 1
        assert ownership["counts"]["organizations"] == 1
        assert ownership["counts"]["queues"] == 1
        assert ownership["counts"]["total_owned"] >= 6
        assert ownership["items"]["goals"][0]["id"] == fixture["goal_id"]
        assert ownership["items"]["goals"][0]["links"]["self"] == _cli_step(
            f"goal show {fixture['goal_id']} --format json"
        )
        assert ownership["items"]["queues"][0]["links"]["self"] == _cli_step(
            f"queue show {fixture['queue_id']} --format json"
        )

        project_workload = next(
            item
            for item in payload["project_workloads"]
            if item["project_id"] == fixture["project_id"]
        )
        assert project_workload["effective"]["total_tasks"] >= 1
        assert project_workload["direct"]["total_tasks"] >= 1
        assert project_workload["links"]["project"] == _cli_step(
            f"project show {fixture['project_id']} --format json"
        )
        assert project_workload["links"]["tasks"] == _cli_step(
            f"task list --project {fixture['project_id']} --actor alice-example --format json"
        )

        graph_navigation = payload["graph_navigation"]
        assert graph_navigation["basis"] == "actor"
        assert graph_navigation["actor_handle"] == "alice-example"
        assert graph_navigation["links"]["tasks_list"] == _cli_step(
            "task list --actor alice-example --format json"
        )
        assert graph_navigation["links"]["goal"] == _cli_step(
            f"goal show {fixture['goal_id']} --format json"
        )
        assert graph_navigation["links"]["project"] == _cli_step(
            f"project show {fixture['project_id']} --format json"
        )

    def test_actor_show_text_surfaces_ownership_and_project_workload_summary(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        _setup_actor_reporting_fixture(cli_runner)

        actor_show_result = cli_runner.invoke(cli, ["actor", "show", "alice-example"])
        assert actor_show_result.exit_code == 0, actor_show_result.output
        assert "Ownership:" in actor_show_result.output
        assert "Project workload:" in actor_show_result.output
        assert "Actor Surface Project" in actor_show_result.output

    def test_actor_list_json_sorts_by_bubbled_actor_graph_activity(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        alpha_result = cli_runner.invoke(
            cli,
            [
                "actor",
                "create",
                "Alpha Actor",
                "--kind",
                "human",
                "--format",
                "json",
            ],
        )
        zulu_result = cli_runner.invoke(
            cli,
            [
                "actor",
                "create",
                "Zulu Actor",
                "--kind",
                "human",
                "--format",
                "json",
            ],
        )
        assert alpha_result.exit_code == 0
        assert zulu_result.exit_code == 0
        alpha_id = json.loads(alpha_result.output)["actor"]["id"]
        zulu_id = json.loads(zulu_result.output)["actor"]["id"]

        label_result = cli_runner.invoke(
            cli,
            ["label", "create", "actor-audit-label"],
        )
        assert label_result.exit_code == 0, label_result.output

        comment_result = cli_runner.invoke(
            cli,
            [
                "comment",
                "add",
                "actor",
                zulu_id,
                "Newest actor graph note",
                "--by",
                "codex",
                "--watch",
            ],
        )
        assert comment_result.exit_code == 0, comment_result.output
        assign_result = cli_runner.invoke(
            cli,
            ["label", "assign", "actor", zulu_id, "actor-audit-label", "--by", "codex"],
        )
        assert assign_result.exit_code == 0, assign_result.output

        list_result = cli_runner.invoke(
            cli,
            ["actor", "list", "--format", "json"],
        )
        assert list_result.exit_code == 0, list_result.output
        payload = json.loads(list_result.output)

        assert payload["items"][0]["id"] == zulu_id
        assert payload["items"][1]["id"] == alpha_id
        assert payload["items"][0]["last_activity_at"] is not None
        assert "last_transition_at" in payload["items"][0]

    def test_actor_show_json_surfaces_bubbled_activity_and_transition_timestamps(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        alice_result = cli_runner.invoke(
            cli,
            ["actor", "create", "Alice Example", "--kind", "human", "--format", "json"],
        )
        security_result = cli_runner.invoke(
            cli,
            [
                "actor",
                "create",
                "Security Persona",
                "--kind",
                "persona",
                "--format",
                "json",
            ],
        )
        assert alice_result.exit_code == 0, alice_result.output
        assert security_result.exit_code == 0, security_result.output
        alice_id = json.loads(alice_result.output)["actor"]["id"]
        membership_result = cli_runner.invoke(
            cli,
            [
                "actor",
                "membership",
                "add",
                "security-persona",
                "alice-example",
                "--role",
                "representative",
                "--format",
                "json",
            ],
        )
        assert membership_result.exit_code == 0, membership_result.output

        project_result = cli_runner.invoke(
            cli,
            ["project", "create", "Actor Recency Project", "--format", "json"],
        )
        assert project_result.exit_code == 0, project_result.output
        project_id = json.loads(project_result.output)["project"]["id"]
        task_result = cli_runner.invoke(
            cli,
            [
                "task",
                "add",
                project_id,
                "Inherited Recency Task",
                "--assigned-to",
                "security-persona",
                "--format",
                "json",
            ],
        )
        assert task_result.exit_code == 0, task_result.output
        task_id = json.loads(task_result.output)["task"]["id"]

        label_result = cli_runner.invoke(
            cli,
            ["label", "create", "actor-show-label"],
        )
        assert label_result.exit_code == 0, label_result.output
        comment_result = cli_runner.invoke(
            cli,
            [
                "comment",
                "add",
                "actor",
                alice_id,
                "Actor recency note",
                "--by",
                "codex",
                "--watch",
            ],
        )
        assert comment_result.exit_code == 0, comment_result.output
        assign_result = cli_runner.invoke(
            cli,
            [
                "label",
                "assign",
                "actor",
                alice_id,
                "actor-show-label",
                "--by",
                "codex",
            ],
        )
        assert assign_result.exit_code == 0, assign_result.output
        start_result = cli_runner.invoke(
            cli,
            ["task", "start", task_id, "--by", "codex", "--format", "json"],
        )
        assert start_result.exit_code == 0, start_result.output

        show_result = cli_runner.invoke(
            cli,
            ["actor", "show", "alice-example", "--format", "json"],
        )
        assert show_result.exit_code == 0, show_result.output
        payload = json.loads(show_result.output)

        assert payload["actor"]["last_activity_at"] is not None
        assert payload["actor"]["last_transition_at"] is not None
        assert payload["last_activity_at"] == payload["actor"]["last_activity_at"]
        assert payload["last_transition_at"] == payload["actor"]["last_transition_at"]

    def test_actor_assignment_payloads_propagate_to_queue_surfaces(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        fixture = _setup_actor_assignment_surface_fixture(cli_runner)

        queue_result = cli_runner.invoke(
            cli,
            [
                "queue",
                "create",
                "Actor Assignment Queue",
                "--filters",
                '{"status":["todo","in_progress"]}',
            ],
        )
        assert queue_result.exit_code == 0, queue_result.output
        queue_id = _extract_id(queue_result.output)

        run_result = cli_runner.invoke(
            cli,
            ["queue", "run", queue_id, "--format", "json", "--limit", "20"],
        )
        assert run_result.exit_code == 0, run_result.output
        run_payload = json.loads(run_result.output)
        run_items = {item["title"]: item for item in run_payload["items"]}
        assert run_items["Ready Actor Task"]["assignee"]["actor"]["handle"] == (
            "alice-example"
        )
        assert run_items["In Progress Actor Task"]["assignee"]["actor"]["handle"] == (
            "alice-example"
        )
        assert run_items["Ready Actor Task"]["links"]["actor"] == _cli_step(
            "actor show alice-example --format json"
        )

        presets_result = cli_runner.invoke(
            cli,
            [
                "queue",
                "presets",
                "--project",
                fixture["project_name"],
                "--format",
                "json",
                "--view",
                "detail",
            ],
        )
        assert presets_result.exit_code == 0, presets_result.output
        presets_payload = json.loads(presets_result.output)
        ready_entry = next(
            item for item in presets_payload["items"] if item["name"] == "ready"
        )
        ready_assignment_items = [
            item
            for item in ready_entry["items"]
            if item.get("assignee", {}).get("actor") is not None
        ]
        assert ready_assignment_items
        assert ready_assignment_items[0]["links"]["actor"] == _cli_step(
            f"actor show {ready_assignment_items[0]['assignee']['actor']['handle']} --format json"
        )

    def test_actor_assignment_payloads_propagate_to_dashboard_surface(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        _setup_actor_assignment_surface_fixture(cli_runner)

        dashboard_result = cli_runner.invoke(cli, ["dashboard", "--format", "json"])
        assert dashboard_result.exit_code == 0, dashboard_result.output
        payload = json.loads(dashboard_result.output)

        assert payload["focus_task"]["assignee"]["actor"]["handle"] == "alice-example"
        assert payload["focus_task"]["links"]["actor"] == _cli_step(
            "actor show alice-example --format json"
        )

        ready_items = {item["title"]: item for item in payload["ready_tasks"]}
        assert ready_items["Ready Actor Task"]["assignee"]["actor"]["handle"] == (
            "alice-example"
        )

        in_progress_items = {
            item["title"]: item for item in payload["in_progress_tasks"]
        }
        assert (
            in_progress_items["In Progress Actor Task"]["assignee"]["actor"]["handle"]
            == "alice-example"
        )

        blocked_items = {item["title"]: item for item in payload["blocked_items"]}
        assert blocked_items["Blocked Actor Task"]["assignee"]["actor"]["handle"] == (
            "security-persona"
        )

        ready_preset = next(
            item for item in payload["queue_presets"] if item["name"] == "ready"
        )
        ready_assignment_items = [
            item
            for item in ready_preset["items"]
            if item.get("assignee", {}).get("actor") is not None
        ]
        assert ready_assignment_items
        assert ready_assignment_items[0]["links"]["actor"] == _cli_step(
            f"actor show {ready_assignment_items[0]['assignee']['actor']['handle']} --format json"
        )

    def test_project_and_plan_surfaces_expose_actor_assignment_payloads(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        fixture = _setup_actor_strategic_fixture(cli_runner)

        project_show_result = cli_runner.invoke(
            cli,
            ["project", "show", fixture["project_name"], "--format", "json"],
        )
        assert project_show_result.exit_code == 0, project_show_result.output
        project_show_payload = json.loads(project_show_result.output)
        assert (
            project_show_payload["focus_task"]["assignee"]["actor"]["handle"]
            == "alice-example"
        )
        assert (
            project_show_payload["execution"]["active_tasks"][0]["assignee"]["actor"][
                "handle"
            ]
            == "alice-example"
        )

        project_summary_result = cli_runner.invoke(
            cli,
            ["project", "summary", fixture["project_name"], "--format", "json"],
        )
        assert project_summary_result.exit_code == 0, project_summary_result.output
        project_summary_payload = json.loads(project_summary_result.output)
        assert (
            project_summary_payload["focus_task"]["assignee"]["actor"]["handle"]
            == "alice-example"
        )

        plan_show_result = cli_runner.invoke(
            cli,
            [
                "plan",
                "show",
                fixture["plan_id"],
                "--format",
                "json",
                "--include-linked",
            ],
        )
        assert plan_show_result.exit_code == 0, plan_show_result.output
        plan_show_payload = json.loads(plan_show_result.output)
        assert (
            plan_show_payload["focus_task"]["assignee"]["actor"]["handle"]
            == "alice-example"
        )
        assert (
            plan_show_payload["linked"]["tasks"][0]["assignee"]["actor"]["handle"]
            == "alice-example"
        )

    def test_strategic_show_surfaces_expose_actor_owner_payloads(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        fixture = _setup_actor_strategic_fixture(cli_runner)

        goal_show_result = cli_runner.invoke(
            cli,
            [
                "goal",
                "show",
                fixture["goal_id"],
                "--format",
                "json",
                "--include-linked",
            ],
        )
        assert goal_show_result.exit_code == 0, goal_show_result.output
        goal_show_payload = json.loads(goal_show_result.output)
        assert goal_show_payload["ownership"]["actor"]["handle"] == "alice-example"
        assert goal_show_payload["links"]["owner"] == _cli_step(
            "actor show alice-example --format json"
        )
        assert (
            goal_show_payload["linked"]["objectives"][0]["ownership"]["actor"]["handle"]
            == "security-persona"
        )

        objective_show_result = cli_runner.invoke(
            cli,
            [
                "objective",
                "show",
                fixture["objective_id"],
                "--format",
                "json",
                "--include-linked",
            ],
        )
        assert objective_show_result.exit_code == 0, objective_show_result.output
        objective_show_payload = json.loads(objective_show_result.output)
        assert (
            objective_show_payload["ownership"]["actor"]["handle"] == "security-persona"
        )
        assert (
            objective_show_payload["linked"]["key_results"][0]["ownership"]["actor"][
                "handle"
            ]
            == "alice-example"
        )

        key_result_show_result = cli_runner.invoke(
            cli,
            [
                "keyresult",
                "show",
                fixture["key_result_id"],
                "--format",
                "json",
                "--include-linked",
            ],
        )
        assert key_result_show_result.exit_code == 0, key_result_show_result.output
        key_result_show_payload = json.loads(key_result_show_result.output)
        assert (
            key_result_show_payload["ownership"]["actor"]["handle"] == "alice-example"
        )
        assert (
            key_result_show_payload["linked"]["objective"]["ownership"]["actor"][
                "handle"
            ]
            == "security-persona"
        )

    def test_goal_summary_exposes_goal_owner_and_focus_task_assignment_payloads(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        fixture = _setup_actor_strategic_fixture(cli_runner)

        goal_summary_result = cli_runner.invoke(
            cli,
            ["goal", "summary", fixture["goal_id"], "--format", "json"],
        )
        assert goal_summary_result.exit_code == 0, goal_summary_result.output
        goal_summary_payload = json.loads(goal_summary_result.output)
        assert (
            goal_summary_payload["goal"]["ownership"]["actor"]["handle"]
            == "alice-example"
        )
        assert (
            goal_summary_payload["execution"]["focus_task"]["assignee"]["actor"][
                "handle"
            ]
            == "alice-example"
        )

    def test_strategic_and_control_surfaces_include_actor_rollups(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        fixture = _setup_actor_strategic_fixture(cli_runner)

        checkout_result = cli_runner.invoke(
            cli,
            [
                "task",
                "checkout",
                fixture["task_id"],
                "--agent-id",
                "strategic-runner",
                "--actor",
                "alice-example",
            ],
        )
        assert checkout_result.exit_code == 0, checkout_result.output

        project_show_result = cli_runner.invoke(
            cli,
            ["project", "show", fixture["project_name"], "--format", "json"],
        )
        assert project_show_result.exit_code == 0, project_show_result.output
        project_show_payload = json.loads(project_show_result.output)
        assert (
            project_show_payload["actor_rollups"]["population_basis"]
            == "project_visible_tasks"
        )
        assert (
            project_show_payload["actor_rollups"]["assignments"]["actors"][0]["handle"]
            == "alice-example"
        )
        assert (
            project_show_payload["actor_rollups"]["checkouts"]["actors"][0]["handle"]
            == "alice-example"
        )

        project_summary_result = cli_runner.invoke(
            cli,
            ["project", "summary", fixture["project_name"], "--format", "json"],
        )
        assert project_summary_result.exit_code == 0, project_summary_result.output
        project_summary_payload = json.loads(project_summary_result.output)
        assert (
            project_summary_payload["actor_rollups"]["assignments"]["actors"][0][
                "handle"
            ]
            == "alice-example"
        )

        goal_show_result = cli_runner.invoke(
            cli,
            [
                "goal",
                "show",
                fixture["goal_id"],
                "--format",
                "json",
                "--include-linked",
            ],
        )
        assert goal_show_result.exit_code == 0, goal_show_result.output
        goal_show_payload = json.loads(goal_show_result.output)
        assert (
            goal_show_payload["actor_rollups"]["population_basis"]
            == "goal_surface_visible_entities"
        )
        assert {
            actor["handle"]
            for actor in goal_show_payload["actor_rollups"]["ownership"]["actors"]
        } == {"alice-example", "security-persona"}

        goal_summary_result = cli_runner.invoke(
            cli,
            ["goal", "summary", fixture["goal_id"], "--format", "json"],
        )
        assert goal_summary_result.exit_code == 0, goal_summary_result.output
        goal_summary_payload = json.loads(goal_summary_result.output)
        assert (
            goal_summary_payload["actor_rollups"]["ownership"]["actors"][0]["handle"]
            == "alice-example"
        )
        assert (
            goal_summary_payload["actor_rollups"]["assignments"]["actors"][0]["handle"]
            == "alice-example"
        )

        objective_show_result = cli_runner.invoke(
            cli,
            [
                "objective",
                "show",
                fixture["objective_id"],
                "--format",
                "json",
                "--include-linked",
            ],
        )
        assert objective_show_result.exit_code == 0, objective_show_result.output
        objective_show_payload = json.loads(objective_show_result.output)
        assert (
            objective_show_payload["actor_rollups"]["population_basis"]
            == "objective_surface_visible_entities"
        )
        assert {
            actor["handle"]
            for actor in objective_show_payload["actor_rollups"]["ownership"]["actors"]
        } == {"alice-example", "security-persona"}

        plan_show_result = cli_runner.invoke(
            cli,
            [
                "plan",
                "show",
                fixture["plan_id"],
                "--format",
                "json",
                "--include-linked",
            ],
        )
        assert plan_show_result.exit_code == 0, plan_show_result.output
        plan_show_payload = json.loads(plan_show_result.output)
        assert (
            plan_show_payload["actor_rollups"]["population_basis"]
            == "plan_linked_graph"
        )
        assert {
            actor["handle"]
            for actor in plan_show_payload["actor_rollups"]["ownership"]["actors"]
        } == {"alice-example", "security-persona"}
        assert (
            plan_show_payload["actor_rollups"]["assignments"]["actors"][0]["handle"]
            == "alice-example"
        )
        assert (
            plan_show_payload["actor_rollups"]["checkouts"]["actors"][0]["handle"]
            == "alice-example"
        )

        dashboard_result = cli_runner.invoke(cli, ["dashboard", "--format", "json"])
        assert dashboard_result.exit_code == 0, dashboard_result.output
        dashboard_payload = json.loads(dashboard_result.output)
        assert (
            dashboard_payload["actor_rollups"]["population_basis"]
            == "dashboard_visible_tasks"
        )
        assert (
            dashboard_payload["actor_rollups"]["assignments"]["actors"][0]["handle"]
            == "alice-example"
        )

        start_result = cli_runner.invoke(cli, ["start", "--format", "json"])
        assert start_result.exit_code == 0, start_result.output
        start_payload = json.loads(start_result.output)
        assert (
            start_payload["actor_rollups"]["population_basis"] == "start_visible_tasks"
        )
        assert (
            start_payload["actor_rollups"]["assignments"]["actors"][0]["handle"]
            == "alice-example"
        )

    def test_work_graph_report_unifies_project_plan_task_actor_and_evidence_surfaces(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        fixture = _setup_actor_strategic_fixture(cli_runner)

        checkout_result = cli_runner.invoke(
            cli,
            [
                "task",
                "checkout",
                fixture["task_id"],
                "--agent-id",
                "strategic-runner",
                "--actor",
                "alice-example",
            ],
        )
        assert checkout_result.exit_code == 0, checkout_result.output

        evidence_result = cli_runner.invoke(
            cli,
            [
                "task",
                "evidence",
                "add",
                fixture["task_id"],
                "artifact",
                "docs/proof.txt",
            ],
        )
        assert evidence_result.exit_code == 0, evidence_result.output

        result = cli_runner.invoke(
            cli,
            [
                "work",
                "graph-report",
                "--scope-type",
                "project",
                "--scope",
                fixture["project_name"],
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)

        assert payload["scope"]["kind"] == "work_graph_report"
        assert payload["scope"]["scope_type"] == "project"
        assert payload["scope"]["scope_id"] == fixture["project_id"]
        assert payload["scope"]["detail_level"] == "project_full_graph"
        assert payload["focus_task"]["id"] == fixture["task_id"]
        assert payload["graph_navigation"]["basis"] == "focus_task"
        assert payload["graph_navigation"]["links"]["plans"] == _cli_step(
            f"plan list --task-id {fixture['task_id']} --format json"
        )
        assert payload["projects"]["items"][0]["id"] == fixture["project_id"]
        assert payload["goals"]["items"][0]["id"] == fixture["goal_id"]
        assert payload["objectives"]["items"][0]["id"] == fixture["objective_id"]
        assert payload["key_results"]["items"][0]["id"] == fixture["key_result_id"]
        assert payload["plans"]["items"][0]["id"] == fixture["plan_id"]
        assert payload["tasks"]["items"][0]["id"] == fixture["task_id"]
        assert payload["tasks"]["items"][0]["linked_plan_count"] >= 1
        assert payload["tasks"]["items"][0]["evidence_count"] >= 1
        assert payload["results"]["evidence"]["total_count"] >= 1
        assert (
            payload["actor_rollups"]["population_basis"]
            == "project_graph_visible_entities"
        )
        assert {
            actor["handle"] for actor in payload["actor_rollups"]["ownership"]["actors"]
        } == {"alice-example", "security-persona"}
        assert (
            payload["actor_rollups"]["assignments"]["actors"][0]["handle"]
            == "alice-example"
        )
        assert (
            payload["actor_rollups"]["checkouts"]["actors"][0]["handle"]
            == "alice-example"
        )

    def test_task_create_and_update_actor_assignment_resolution(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Actor Ref Project"])
        cli_runner.invoke(
            cli,
            ["actor", "create", "Alice Example", "--kind", "human", "--format", "json"],
        )
        cli_runner.invoke(
            cli,
            [
                "actor",
                "create",
                "Security Persona",
                "--kind",
                "persona",
                "--format",
                "json",
            ],
        )
        alias_result = cli_runner.invoke(
            cli,
            ["actor", "alias", "add", "alice-example", "alice", "--format", "json"],
        )
        assert alias_result.exit_code == 0, alias_result.output

        create_result = cli_runner.invoke(
            cli,
            [
                "task",
                "add",
                "Actor Ref Project",
                "Dual Write Task",
                "--assigned-to",
                "alice",
                "--format",
                "json",
            ],
        )
        assert create_result.exit_code == 0, create_result.output
        create_payload = json.loads(create_result.output)
        task_id = create_payload["task"]["id"]
        assert create_payload["task"]["assignee"]["ref"] == "alice-example"
        assert create_payload["task"]["assignee"]["id"]
        assert create_payload["task"]["assignee"]["actor"]["handle"] == "alice-example"

        update_result = cli_runner.invoke(
            cli,
            [
                "task",
                "update",
                task_id,
                "--assigned-to",
                "security-persona",
                "--format",
                "json",
            ],
        )
        assert update_result.exit_code == 0, update_result.output
        update_payload = json.loads(update_result.output)
        assert update_payload["task"]["assignee"]["ref"] == "security-persona"
        assert update_payload["task"]["assignee"]["id"]
        assert (
            update_payload["task"]["assignee"]["actor"]["handle"] == "security-persona"
        )

        clear_result = cli_runner.invoke(
            cli,
            [
                "task",
                "update",
                task_id,
                "--clear-assigned-to",
                "--format",
                "json",
            ],
        )
        assert clear_result.exit_code == 0, clear_result.output
        clear_payload = json.loads(clear_result.output)
        assert clear_payload["task"]["assignee"]["ref"] is None
        assert clear_payload["task"]["assignee"]["id"] is None
        assert clear_payload["task"]["assignee"]["actor"] is None

    def test_strategic_create_and_update_actor_owner_resolution(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Owner Ref Project"])
        cli_runner.invoke(
            cli,
            ["actor", "create", "Alice Example", "--kind", "human", "--format", "json"],
        )
        cli_runner.invoke(
            cli,
            ["actor", "alias", "add", "alice-example", "alice", "--format", "json"],
        )
        cli_runner.invoke(
            cli,
            [
                "actor",
                "create",
                "Security Persona",
                "--kind",
                "persona",
                "--format",
                "json",
            ],
        )

        goal_result = cli_runner.invoke(
            cli,
            [
                "goal",
                "create",
                "Owner Ref Goal",
                "--project",
                "Owner Ref Project",
                "--owner",
                "alice",
                "--format",
                "json",
            ],
        )
        assert goal_result.exit_code == 0, goal_result.output
        goal_payload = json.loads(goal_result.output)
        goal_id = goal_payload["goal"]["id"]
        assert goal_payload["goal"]["owner"] == "alice-example"
        assert goal_payload["goal"]["ownership"]["id"]

        objective_result = cli_runner.invoke(
            cli,
            [
                "objective",
                "create",
                "Owner Ref Objective",
                "--goal-id",
                goal_id,
                "--owner",
                "security-persona",
                "--format",
                "json",
            ],
        )
        assert objective_result.exit_code == 0, objective_result.output
        objective_payload = json.loads(objective_result.output)
        objective_id = objective_payload["objective"]["id"]
        assert objective_payload["objective"]["owner"] == "security-persona"
        assert objective_payload["objective"]["ownership"]["id"]

        key_result_create = cli_runner.invoke(
            cli,
            [
                "keyresult",
                "create",
                "Owner Ref Key Result",
                "--objective-id",
                objective_id,
                "--owner",
                "alice",
            ],
        )
        assert key_result_create.exit_code == 0, key_result_create.output
        key_result_id = _extract_id(key_result_create.output)

        key_result_show = cli_runner.invoke(
            cli,
            ["keyresult", "show", key_result_id, "--format", "json"],
        )
        assert key_result_show.exit_code == 0, key_result_show.output
        key_result_show_payload = json.loads(key_result_show.output)
        assert key_result_show_payload["owner"] == "alice-example"
        assert key_result_show_payload["ownership"]["id"]

        goal_clear = cli_runner.invoke(
            cli,
            ["goal", "update", goal_id, "--clear-owner", "--format", "json"],
        )
        assert goal_clear.exit_code == 0, goal_clear.output
        goal_clear_payload = json.loads(goal_clear.output)
        assert goal_clear_payload["goal"]["owner"] is None
        assert goal_clear_payload["goal"]["ownership"]["id"] is None

        objective_update = cli_runner.invoke(
            cli,
            [
                "objective",
                "update",
                objective_id,
                "--owner",
                "alice",
                "--format",
                "json",
            ],
        )
        assert objective_update.exit_code == 0, objective_update.output
        objective_update_payload = json.loads(objective_update.output)
        assert objective_update_payload["objective"]["owner"] == "alice-example"
        assert objective_update_payload["objective"]["ownership"]["id"]

        key_result_clear = cli_runner.invoke(
            cli,
            ["keyresult", "update", key_result_id, "--clear-owner"],
        )
        assert key_result_clear.exit_code == 0, key_result_clear.output

        key_result_cleared_show = cli_runner.invoke(
            cli,
            ["keyresult", "show", key_result_id, "--format", "json"],
        )
        assert key_result_cleared_show.exit_code == 0, key_result_cleared_show.output
        key_result_cleared_payload = json.loads(key_result_cleared_show.output)
        assert key_result_cleared_payload["owner"] is None
        assert key_result_cleared_payload["ownership"]["id"] is None

    def test_management_surfaces_create_and_update_actor_resolution(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        fixture = _setup_actor_management_fixture(cli_runner)

        product_show = cli_runner.invoke(
            cli, ["product", "show", fixture["product_id"], "--format", "json"]
        )
        assert product_show.exit_code == 0, product_show.output
        product_payload = json.loads(product_show.output)
        assert product_payload["owner"] == "alice-example"
        assert product_payload["ownership"]["id"]
        assert product_payload["ownership"]["actor"]["handle"] == "alice-example"

        org_show = cli_runner.invoke(
            cli, ["org", "show", fixture["org_id"], "--format", "json"]
        )
        assert org_show.exit_code == 0, org_show.output
        org_payload = json.loads(org_show.output)
        assert org_payload["owner"] == "alice-example"
        assert org_payload["ownership"]["id"]
        assert {item["actor"]["handle"] for item in org_payload["members"]} == {
            "alice-example",
            "security-persona",
        }

        team_show = cli_runner.invoke(
            cli, ["team", "show", fixture["team_id"], "--format", "json"]
        )
        assert team_show.exit_code == 0, team_show.output
        team_payload = json.loads(team_show.output)
        assert team_payload["owner"] == "security-persona"
        assert team_payload["ownership"]["id"]
        assert team_payload["members"][0]["actor"]["handle"] == "alice-example"

        portfolio_show = cli_runner.invoke(
            cli, ["portfolio", "show", fixture["portfolio_id"], "--format", "json"]
        )
        assert portfolio_show.exit_code == 0, portfolio_show.output
        portfolio_payload = json.loads(portfolio_show.output)
        assert portfolio_payload["owner"] == "alice-example"
        assert portfolio_payload["ownership"]["id"]
        assert portfolio_payload["ownership"]["actor"]["handle"] == "alice-example"

        program_show = cli_runner.invoke(
            cli, ["program", "show", fixture["program_id"], "--format", "json"]
        )
        assert program_show.exit_code == 0, program_show.output
        program_payload = json.loads(program_show.output)
        assert program_payload["owner"] == "security-persona"
        assert program_payload["ownership"]["id"]
        assert program_payload["ownership"]["actor"]["handle"] == "security-persona"

        queue_show = cli_runner.invoke(
            cli, ["queue", "show", fixture["queue_id"], "--format", "json"]
        )
        assert queue_show.exit_code == 0, queue_show.output
        queue_payload = json.loads(queue_show.output)
        assert queue_payload["owner"] == "alice-example"
        assert queue_payload["ownership"]["id"]
        assert queue_payload["ownership"]["actor"]["handle"] == "alice-example"

        product_update = cli_runner.invoke(
            cli,
            [
                "product",
                "update",
                fixture["product_id"],
                "--owner",
                "security-persona",
                "--format",
                "json",
            ],
        )
        assert product_update.exit_code == 0, product_update.output
        assert (
            json.loads(product_update.output)["product"]["owner"] == "security-persona"
        )

        org_update = cli_runner.invoke(
            cli,
            [
                "org",
                "update",
                fixture["org_id"],
                "--clear-owner",
                "--clear-members",
                "--format",
                "json",
            ],
        )
        assert org_update.exit_code == 0, org_update.output
        org_update_payload = json.loads(org_update.output)
        assert org_update_payload["organization"]["owner"] is None
        assert org_update_payload["ownership"]["id"] is None
        assert org_update_payload["members"] == []

        team_update = cli_runner.invoke(
            cli,
            [
                "team",
                "update",
                fixture["team_id"],
                "--clear-owner",
                "--clear-members",
                "--format",
                "json",
            ],
        )
        assert team_update.exit_code == 0, team_update.output
        team_update_payload = json.loads(team_update.output)
        assert team_update_payload["team"]["owner"] is None
        assert team_update_payload["ownership"]["id"] is None
        assert team_update_payload["members"] == []

        portfolio_update = cli_runner.invoke(
            cli,
            [
                "portfolio",
                "update",
                fixture["portfolio_id"],
                "--clear-owner",
                "--format",
                "json",
            ],
        )
        assert portfolio_update.exit_code == 0, portfolio_update.output
        portfolio_update_payload = json.loads(portfolio_update.output)
        assert portfolio_update_payload["portfolio"]["owner"] is None
        assert portfolio_update_payload["ownership"]["id"] is None

        program_update = cli_runner.invoke(
            cli,
            [
                "program",
                "update",
                fixture["program_id"],
                "--clear-owner",
                "--format",
                "json",
            ],
        )
        assert program_update.exit_code == 0, program_update.output
        program_update_payload = json.loads(program_update.output)
        assert program_update_payload["program"]["owner"] is None
        assert program_update_payload["ownership"]["id"] is None

        queue_list = cli_runner.invoke(
            cli,
            ["queue", "list", "--owner", "alice", "--format", "json"],
        )
        assert queue_list.exit_code == 0, queue_list.output
        queue_list_payload = json.loads(queue_list.output)
        assert queue_list_payload["items"][0]["ownership"]["actor"]["handle"] == (
            "alice-example"
        )

        queue_update = cli_runner.invoke(
            cli,
            [
                "queue",
                "update",
                fixture["queue_id"],
                "--clear-owner",
                "--format",
                "json",
            ],
        )
        assert queue_update.exit_code == 0, queue_update.output
        queue_update_payload = json.loads(queue_update.output)
        assert queue_update_payload["queue"]["owner"] is None
        assert queue_update_payload["ownership"]["id"] is None
        assert queue_update_payload["ownership"]["actor"] is None

    def test_management_list_show_and_summary_surfaces_expose_actor_payloads(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        fixture = _setup_actor_management_fixture(cli_runner)

        product_summary = cli_runner.invoke(
            cli, ["product", "summary", fixture["product_id"], "--format", "json"]
        )
        assert product_summary.exit_code == 0, product_summary.output
        assert (
            json.loads(product_summary.output)["ownership"]["actor"]["handle"]
            == "alice-example"
        )

        org_summary = cli_runner.invoke(
            cli, ["org", "summary", fixture["org_id"], "--format", "json"]
        )
        assert org_summary.exit_code == 0, org_summary.output
        org_summary_payload = json.loads(org_summary.output)
        assert org_summary_payload["ownership"]["actor"]["handle"] == "alice-example"
        assert {item["actor"]["handle"] for item in org_summary_payload["members"]} == {
            "alice-example",
            "security-persona",
        }

        team_list = cli_runner.invoke(cli, ["team", "list", "--format", "json"])
        assert team_list.exit_code == 0, team_list.output
        team_list_payload = json.loads(team_list.output)
        assert team_list_payload["items"][0]["ownership"]["actor"]["handle"] == (
            "security-persona"
        )

        portfolio_list = cli_runner.invoke(
            cli, ["portfolio", "list", "--format", "json"]
        )
        assert portfolio_list.exit_code == 0, portfolio_list.output
        assert (
            json.loads(portfolio_list.output)["items"][0]["ownership"]["actor"][
                "handle"
            ]
            == "alice-example"
        )

        portfolio_summary = cli_runner.invoke(
            cli, ["portfolio", "summary", fixture["portfolio_id"], "--format", "json"]
        )
        assert portfolio_summary.exit_code == 0, portfolio_summary.output
        assert (
            json.loads(portfolio_summary.output)["ownership"]["actor"]["handle"]
            == "alice-example"
        )

        program_list = cli_runner.invoke(cli, ["program", "list", "--format", "json"])
        assert program_list.exit_code == 0, program_list.output
        assert (
            json.loads(program_list.output)["items"][0]["ownership"]["actor"]["handle"]
            == "security-persona"
        )

        program_summary = cli_runner.invoke(
            cli, ["program", "summary", fixture["program_id"], "--format", "json"]
        )
        assert program_summary.exit_code == 0, program_summary.output
        assert (
            json.loads(program_summary.output)["ownership"]["actor"]["handle"]
            == "security-persona"
        )

        queue_list = cli_runner.invoke(
            cli, ["queue", "list", "--owner", "alice", "--format", "json"]
        )
        assert queue_list.exit_code == 0, queue_list.output
        queue_list_payload = json.loads(queue_list.output)
        assert queue_list_payload["items"][0]["ownership"]["actor"]["handle"] == (
            "alice-example"
        )

        queue_show = cli_runner.invoke(
            cli, ["queue", "show", fixture["queue_id"], "--format", "json"]
        )
        assert queue_show.exit_code == 0, queue_show.output
        assert (
            json.loads(queue_show.output)["ownership"]["actor"]["handle"]
            == "alice-example"
        )


class TestLocalTestServerCommands:
    """Tests for local test-server registration flows."""

    def test_test_server_ensure_local_json(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Ensure-local should expose machine-readable local registration output."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Release Project"])

        result = cli_runner.invoke(
            cli,
            [
                "test",
                "server",
                "ensure-local",
                "--project",
                "Release Project",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["server"]["id"] == "local"
        assert payload["server"]["created"] is True
        assert payload["links"]["test_runs"] == _cli_step(
            "test list --server-id local --format json"
        )
        assert payload["next_steps"][0].startswith(
            _cli_step("test record --server-id local")
        )

    def test_test_server_ensure_local_is_reusable(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Ensure-local should reuse the same registration after the first call."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])

        first = cli_runner.invoke(
            cli, ["test", "server", "ensure-local", "--format", "json"]
        )
        second = cli_runner.invoke(
            cli, ["test", "server", "ensure-local", "--format", "json"]
        )

        assert first.exit_code == 0
        assert second.exit_code == 0
        assert json.loads(first.output)["server"]["created"] is True
        assert json.loads(second.output)["server"]["created"] is False

    def test_test_server_ensure_local_fails_nonzero_for_conflicting_project_filters(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Release Project"])

        result = cli_runner.invoke(
            cli,
            [
                "test",
                "server",
                "ensure-local",
                "--project",
                "Release Project",
                "--project-id",
                "proj_conflict",
                "--format",
                "json",
            ],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert payload["error"] == "Use --project or --project-id, not both"

    def test_test_prune_fails_nonzero_for_conflicting_scope_filters(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(
            cli,
            [
                "test",
                "prune",
                "--project-id",
                "proj_123",
                "--org-id",
                "org_123",
                "--format",
                "json",
            ],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert payload["error"] == "Use --project-id or --org-id, not both"


class TestLoopCommands:
    """Tests for loop command validation contracts."""

    def test_loop_list_fails_nonzero_for_conflicting_project_filters(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Loop Project"])

        result = cli_runner.invoke(
            cli,
            [
                "loop",
                "list",
                "--project",
                "Loop Project",
                "--project-id",
                "proj_conflict",
                "--format",
                "json",
            ],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert payload["error"] == "Use --project or --project-id, not both"

    def test_loop_run_requires_prompt_source_nonzero(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(cli, ["loop", "run", "--dry-run"])

        assert result.exit_code != 0
        _assert_plain_output_contains(
            result.output, "Provide a prompt or --prompt-file"
        )

    def test_loop_guard_requires_project_or_goal_nonzero_in_json_mode(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(
            cli,
            ["loop", "guard", "--format", "json"],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert payload["error"] == "Provide --project or at least one goal"

    def test_loop_prompt_template_fails_nonzero_for_conflicting_goal_filters(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Prompt Project"])
        goal_result = cli_runner.invoke(
            cli,
            ["goal", "create", "Prompt Goal", "--project", "Prompt Project"],
        )
        goal_id = _extract_id(goal_result.output)

        result = cli_runner.invoke(
            cli,
            [
                "loop",
                "prompt-template",
                "--project",
                "Prompt Project",
                "--goal",
                "Prompt Goal",
                "--goal-id",
                goal_id,
                "--stdout",
            ],
        )
        assert result.exit_code != 0
        _assert_plain_output_contains(
            result.output, "Use --goal or --goal-id, not both"
        )


class TestLowFrequencyValidationContracts:
    """Tests for lower-frequency fail-loud validation surfaces."""

    def test_custom_field_value_set_requires_value_nonzero(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(
            cli,
            [
                "custom-field",
                "value",
                "set",
                "field_123",
                "--entity-type",
                "task",
                "--entity-id",
                "task_123",
            ],
        )
        assert result.exit_code != 0
        _assert_plain_output_contains(result.output, "Provide --value or --value-json")

    def test_custom_field_value_list_requires_scope_nonzero_in_json_mode(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(
            cli,
            ["custom-field", "value", "list", "--format", "json"],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert payload["error"] == "Provide --field-id or --entity-type + --entity-id"

    def test_automation_rule_update_fails_nonzero_for_conflicting_enable_flags(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(
            cli,
            ["automation", "rule", "update", "rule_123", "--enable", "--disable"],
        )
        assert result.exit_code != 0
        _assert_plain_output_contains(
            result.output, "Use either --enable or --disable, not both"
        )

    def test_retention_policy_update_requires_fields_nonzero_json(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(
            cli,
            [
                "test",
                "retention-policy",
                "update",
                "policy_123",
                "--format",
                "json",
            ],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert payload["error"] == "Provide at least one field to update"

    def test_program_create_fails_nonzero_for_conflicting_org_filters_json(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["org", "create", "Program Org"])

        result = cli_runner.invoke(
            cli,
            [
                "program",
                "create",
                "Program Conflict",
                "--org",
                "Program Org",
                "--org-id",
                "org_conflict",
                "--format",
                "json",
            ],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert payload["error"] == "Use --org or --org-id, not both"

    def test_program_list_fails_nonzero_for_conflicting_portfolio_filters_json(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(
            cli,
            [
                "program",
                "list",
                "--portfolio",
                "Portfolio A",
                "--portfolio-id",
                "portfolio_conflict",
                "--format",
                "json",
            ],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert payload["error"] == "Use --portfolio or --portfolio-id, not both"

    def test_program_dashboard_fails_nonzero_for_conflicting_org_filters_json(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["org", "create", "Dashboard Org"])

        result = cli_runner.invoke(
            cli,
            [
                "program",
                "dashboard",
                "--org",
                "Dashboard Org",
                "--org-id",
                "org_conflict",
                "--format",
                "json",
            ],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert payload["error"] == "Use --org or --org-id, not both"

    def test_team_create_fails_nonzero_for_conflicting_org_filters_json(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["org", "create", "Team Org"])

        result = cli_runner.invoke(
            cli,
            [
                "team",
                "create",
                "Team Conflict",
                "--org",
                "Team Org",
                "--org-id",
                "org_conflict",
                "--format",
                "json",
            ],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert payload["error"] == "Use --org or --org-id, not both"

    def test_portfolio_create_fails_nonzero_for_conflicting_org_filters_json(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["org", "create", "Portfolio Org"])

        result = cli_runner.invoke(
            cli,
            [
                "portfolio",
                "create",
                "Portfolio Conflict",
                "--org",
                "Portfolio Org",
                "--org-id",
                "org_conflict",
                "--format",
                "json",
            ],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert payload["error"] == "Use --org or --org-id, not both"

    def test_portfolio_list_fails_nonzero_for_conflicting_org_filters_json(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(
            cli,
            [
                "portfolio",
                "list",
                "--org",
                "Portfolio Org",
                "--org-id",
                "org_conflict",
                "--format",
                "json",
            ],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert payload["error"] == "Use --org or --org-id, not both"

    def test_plan_lineage_fails_nonzero_for_conflicting_project_filters_json(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Lineage Conflict Project"])

        result = cli_runner.invoke(
            cli,
            [
                "plan",
                "lineage",
                "--project",
                "Lineage Conflict Project",
                "--project-id",
                "proj_conflict",
                "--format",
                "json",
            ],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert payload["error"] == "Use --project or --project-id, not both"

    def test_plan_update_fails_nonzero_for_conflicting_goal_filters_json(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Plan Update Conflict Project"])
        plan_result = cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Plan Update Conflict Plan",
                "--project",
                "Plan Update Conflict Project",
                "--content",
                "{}",
                "--output-format",
                "json",
            ],
        )
        plan_id = json.loads(plan_result.output)["plan"]["id"]

        cli_runner.invoke(
            cli,
            [
                "goal",
                "create",
                "Plan Update Conflict Goal",
                "--project",
                "Plan Update Conflict Project",
            ],
        )

        result = cli_runner.invoke(
            cli,
            [
                "plan",
                "update",
                plan_id,
                "--project",
                "Plan Update Conflict Project",
                "--goal",
                "Plan Update Conflict Goal",
                "--goal-id",
                "goal_conflict",
                "--output-format",
                "json",
            ],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert payload["error"] == "Use --goal or --goal-id, not both"


class TestInitCommand:
    """Tests for init command."""

    def test_init(self, cli_runner: CliRunner, temp_env: Path):
        """Test database initialization."""
        from pms.config.settings import reload_settings

        reload_settings()

        result = cli_runner.invoke(cli, ["init"])

        assert result.exit_code == 0
        _assert_plain_output_contains(result.output, "Initialized PMS")
        assert (temp_env / "test.db").exists()

    def test_config_show_json(self, cli_runner: CliRunner, temp_env: Path):
        """Resolved config should expose state paths and runtime coordination guidance."""
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(
            cli,
            [
                "config",
                "set",
                "--write-mode",
                "prefer_server",
                "--server-url",
                "http://127.0.0.1:1",
            ],
        )

        result = cli_runner.invoke(cli, ["config", "show", "--format", "json"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["paths"]["data_dir"] == str(temp_env.resolve())
        assert payload["paths"]["database_path"] == str(
            (temp_env / "test.db").resolve()
        )
        assert payload["paths"]["log_dir"] == str((temp_env / "logs").resolve())
        assert payload["runtime"]["write_mode"] == "prefer_server"
        assert payload["runtime"]["server_base_url"] == "http://127.0.0.1:1"
        assert payload["runtime"]["server"]["checked"] is True
        assert payload["runtime"]["server"]["reachable"] is False
        assert (
            payload["runtime"]["coordination"]["state"] == "degraded_server_unreachable"
        )
        assert payload["runtime"]["coordination"]["can_delegate_writes"] is False
        assert (
            payload["runtime"]["coordination"]["recovery"]["kind"]
            == "restore_preferred_server"
        )
        assert payload["sqlite"]["journal_mode"] == "WAL"
        assert payload["next_steps"] == [
            _cli_step("runtime prefer-server --host 127.0.0.1 --port 27541"),
            _cli_step("runtime status --format json"),
            _cli_step("config show --format json"),
            _cli_step("start --format json"),
        ]

    def test_config_set_shows_log_dir(self, cli_runner: CliRunner, temp_env: Path):
        """Persisted config feedback should include the resolved log directory."""
        from pms.config.settings import reload_settings

        reload_settings()
        target_dir = temp_env / "workspace-state"
        with cli_runner.isolated_filesystem(temp_dir=str(temp_env)):
            result = cli_runner.invoke(
                cli,
                ["config", "set", "--data-dir", str(target_dir)],
            )

        assert result.exit_code == 0
        assert _extract_prefixed_value(result.output, "Data dir:") == str(target_dir)
        assert _extract_prefixed_value(result.output, "Database:") == str(
            target_dir / "pms.db"
        )
        assert _extract_prefixed_value(result.output, "Logs:") == str(
            target_dir / "logs"
        )

    def test_config_set_writes_to_isolated_env_file(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        result = cli_runner.invoke(
            cli,
            [
                "config",
                "set",
                "--write-mode",
                "prefer_server",
                "--server-url",
                "http://127.0.0.1:1",
            ],
        )

        assert result.exit_code == 0, result.output
        env_path = temp_env / ".env"
        assert env_path.exists()
        env_text = env_path.read_text()
        assert "PMS_WRITE_MODE=prefer_server" in env_text
        assert "PMS_SERVER_BASE_URL=http://127.0.0.1:1" in env_text

    def test_config_set_persists_server_preferred_runtime(
        self, cli_runner: CliRunner, temp_env: Path
    ):
        """Config set should persist write-mode and server URL for server-backed use."""
        from pms.config.settings import reload_settings

        reload_settings()
        port = _free_tcp_port()
        with cli_runner.isolated_filesystem(temp_dir=str(temp_env)):
            result = cli_runner.invoke(
                cli,
                [
                    "config",
                    "set",
                    "--write-mode",
                    "prefer_server",
                    "--server-url",
                    "http://127.0.0.1:1",
                ],
            )

            assert result.exit_code == 0
            assert _extract_prefixed_value(result.output, "Write mode:") == (
                "prefer_server"
            )
            assert _extract_prefixed_value(result.output, "Server URL:") == (
                "http://127.0.0.1:1"
            )

            reload_settings()
            show_result = cli_runner.invoke(cli, ["config", "show", "--format", "json"])

        assert show_result.exit_code == 0
        payload = json.loads(show_result.output)
        assert payload["runtime"]["write_mode"] == "prefer_server"
        assert payload["runtime"]["server_base_url"] == "http://127.0.0.1:1"
        assert payload["runtime"]["server"]["checked"] is True
        assert payload["runtime"]["server"]["reachable"] is False

    def test_runtime_prefer_server_bootstraps_local_runtime(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Runtime bootstrap should start a local server and persist prefer_server mode."""
        from pms.config.settings import reload_settings

        reload_settings()
        with cli_runner.isolated_filesystem(temp_dir=str(temp_env)):
            port, result = _invoke_runtime_prefer_server_with_retry(cli_runner)

            assert result.exit_code == 0
            payload = json.loads(result.output)
            assert payload["runtime"]["write_mode"] == "prefer_server"
            assert payload["runtime"]["server_base_url"] == f"http://127.0.0.1:{port}"
            assert payload["runtime"]["coordination"]["state"] == "server_coordinated"
            assert payload["server"]["reachable"] is True
            assert Path(".pms-admin-key").exists()
            assert oct(Path(".pms-admin-key").stat().st_mode & 0o777) == "0o600"
            assert (
                payload["next_steps"][0] == "export PMS_API_KEY=$(cat .pms-admin-key)"
            )

            reload_settings()
            show_result = cli_runner.invoke(cli, ["config", "show", "--format", "json"])
            assert show_result.exit_code == 0
            show_payload = json.loads(show_result.output)
            assert show_payload["runtime"]["write_mode"] == "prefer_server"
            assert (
                show_payload["runtime"]["server_base_url"] == f"http://127.0.0.1:{port}"
            )
            assert show_payload["runtime"]["server"]["reachable"] is True
            assert (
                show_payload["runtime"]["coordination"]["state"] == "server_coordinated"
            )

            stop_result = cli_runner.invoke(
                cli,
                ["runtime", "stop-local-server", "--port", str(port)],
            )
            assert stop_result.exit_code == 0

    def test_config_show_uses_local_admin_key_file_for_server_coordination(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Fresh CLI invocations should treat .pms-admin-key as valid server auth input."""
        from pms.config.settings import reload_settings

        reload_settings()
        with cli_runner.isolated_filesystem(temp_dir=str(temp_env)):
            port, result = _invoke_runtime_prefer_server_with_retry(cli_runner)
            assert result.exit_code == 0

            os.environ.pop("PMS_API_KEY", None)
            reload_settings()
            show_result = cli_runner.invoke(cli, ["config", "show", "--format", "json"])

            assert show_result.exit_code == 0
            show_payload = json.loads(show_result.output)
            assert show_payload["runtime"]["server"]["reachable"] is True
            assert show_payload["runtime"]["server"]["api_key_present"] is True
            assert (
                show_payload["runtime"]["coordination"]["state"] == "server_coordinated"
            )

            stop_result = cli_runner.invoke(
                cli,
                ["runtime", "stop-local-server", "--port", str(port)],
            )
            assert stop_result.exit_code == 0

    def test_config_show_and_start_surface_stale_configured_server_with_healthy_managed_runtime(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Runtime surfaces should distinguish a stale configured URL from a healthy managed server."""
        from pms.config.settings import reload_settings

        reload_settings()
        with cli_runner.isolated_filesystem(temp_dir=str(temp_env)):
            port, boot_result = _invoke_runtime_prefer_server_with_retry(cli_runner)
            assert boot_result.exit_code == 0

            cli_runner.invoke(
                cli,
                [
                    "config",
                    "set",
                    "--write-mode",
                    "prefer_server",
                    "--server-url",
                    "http://127.0.0.1:1",
                ],
            )

            reload_settings()
            config_result = cli_runner.invoke(
                cli, ["config", "show", "--format", "json"]
            )
            assert config_result.exit_code == 0
            config_payload = json.loads(config_result.output)
            assert (
                config_payload["runtime"]["coordination"]["state"]
                == "degraded_stale_server_url"
            )
            assert (
                config_payload["runtime"]["coordination"]["recovery"]["kind"]
                == "repair_server_url"
            )
            assert (
                config_payload["runtime"]["coordination"]["configured_server_url"]
                == "http://127.0.0.1:1"
            )
            assert (
                config_payload["runtime"]["coordination"]["discovered_server_url"]
                == f"http://127.0.0.1:{port}"
            )
            assert any(
                item["server_url"] == f"http://127.0.0.1:{port}"
                for item in config_payload["runtime"]["managed_servers"]
            )
            assert config_payload["next_steps"][0] == _cli_step(
                f"runtime prefer-server --host 127.0.0.1 --port {port}"
            )

            start_result = cli_runner.invoke(cli, ["start", "--format", "json"])
            assert start_result.exit_code == 0
            start_payload = json.loads(start_result.output)
            assert (
                start_payload["runtime"]["coordination"]["state"]
                == "degraded_stale_server_url"
            )
            assert (
                start_payload["runtime"]["coordination"]["recovery"]["kind"]
                == "repair_server_url"
            )
            assert (
                start_payload["runtime"]["coordination"]["discovered_server_url"]
                == f"http://127.0.0.1:{port}"
            )
            assert any(
                item["server_url"] == f"http://127.0.0.1:{port}"
                for item in start_payload["runtime"]["managed_servers"]
            )
            assert start_payload["next_steps"][0] == _cli_step(
                f"runtime prefer-server --host 127.0.0.1 --port {port}"
            )

            stop_result = cli_runner.invoke(
                cli,
                ["runtime", "stop-local-server", "--port", str(port)],
            )
            assert stop_result.exit_code == 0

    def test_runtime_status_and_cleanup_manage_tracked_local_servers(
        self, cli_runner: CliRunner, temp_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Managed runtime servers should be inspectable and cleanable through CLI surfaces."""
        from pms.config.settings import reload_settings

        monkeypatch.delenv("PMS_API_KEY", raising=False)
        reload_settings()
        with cli_runner.isolated_filesystem(temp_dir=str(temp_env)):
            port, boot_result = _invoke_runtime_prefer_server_with_retry(cli_runner)
            assert boot_result.exit_code == 0

            status_result = cli_runner.invoke(
                cli,
                ["runtime", "status", "--format", "json"],
            )
            assert status_result.exit_code == 0
            status_payload = json.loads(status_result.output)
            assert status_payload["coordination"]["state"] == "server_coordinated"
            assert status_payload["coordination"]["can_delegate_writes"] is True
            item = next(
                entry for entry in status_payload["items"] if entry["port"] == port
            )
            assert item["running"] is True

            cleanup_result = cli_runner.invoke(
                cli,
                ["runtime", "cleanup", "--format", "json"],
            )
            assert cleanup_result.exit_code == 0
            cleanup_payload = json.loads(cleanup_result.output)
            assert "coordination" in cleanup_payload
            assert any(
                entry["port"] == port for entry in cleanup_payload["preserved_managed"]
            )

            status_after = cli_runner.invoke(
                cli,
                ["runtime", "status", "--format", "json"],
            )
            assert status_after.exit_code == 0

    def test_runtime_status_surfaces_unmanaged_local_processes(
        self, cli_runner: CliRunner, temp_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from pms.config.settings import reload_settings
        from pms.runtime.local_server import UnmanagedLocalServerProcess

        monkeypatch.delenv("PMS_API_KEY", raising=False)
        reload_settings()
        with cli_runner.isolated_filesystem(temp_dir=str(temp_env)):
            monkeypatch.setattr(
                "pms.runtime.local_server.list_unmanaged_local_server_processes",
                lambda **_: [
                    UnmanagedLocalServerProcess(
                        pid=43210,
                        port=54132,
                        kind="pms_serve",
                        command=_GENERIC_LOCAL_SERVER_COMMAND,
                    )
                ],
            )

            status_result = cli_runner.invoke(
                cli,
                ["runtime", "status", "--format", "json"],
            )

        assert status_result.exit_code == 0, status_result.output
        payload = json.loads(status_result.output)
        assert payload["unmanaged_local_processes"][0]["pid"] == 43210
        assert payload["unmanaged_local_processes"][0]["port"] == 54132
        assert payload["unmanaged_local_processes"][0]["kind"] == "pms_serve"

    def test_runtime_status_prefers_configured_healthy_managed_server_when_multiple_exist(
        self, cli_runner: CliRunner, temp_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from pms.config.settings import reload_settings

        monkeypatch.delenv("PMS_API_KEY", raising=False)
        reload_settings()
        with cli_runner.isolated_filesystem(temp_dir=str(temp_env)):
            cli_runner.invoke(
                cli,
                [
                    "config",
                    "set",
                    "--write-mode",
                    "prefer_server",
                    "--server-url",
                    "http://127.0.0.1:27541",
                ],
            )

            monkeypatch.setattr(
                "pms.cli.app._managed_runtime_servers",
                lambda: [
                    {
                        "port": 63266,
                        "server_url": "http://127.0.0.1:63266",
                        "pid": 111,
                        "tracked": True,
                        "running": True,
                        "reachable": True,
                        "pid_file": "/tmp/server-63266.pid",
                        "log_file": "/tmp/server-63266.log",
                        "error": None,
                    },
                    {
                        "port": 27541,
                        "server_url": "http://127.0.0.1:27541",
                        "pid": 222,
                        "tracked": True,
                        "running": True,
                        "reachable": True,
                        "pid_file": "/tmp/server-27541.pid",
                        "log_file": "/tmp/server-27541.log",
                        "error": None,
                    },
                ],
            )
            monkeypatch.setattr(
                "pms.cli.app._runtime_server_payload",
                lambda: RuntimeServerPayload(
                    base_url="http://127.0.0.1:27541",
                    reachable=True,
                    status="healthy",
                    database="healthy",
                    error=None,
                    checked=True,
                    api_key_present=True,
                    api_key_authorized=True,
                    auth_error=None,
                    api_key_source="file",
                ),
            )

            status_result = cli_runner.invoke(
                cli, ["runtime", "status", "--format", "json"]
            )

        assert status_result.exit_code == 0, status_result.output
        payload = json.loads(status_result.output)
        assert payload["coordination"]["state"] == "server_coordinated"
        assert (
            payload["coordination"]["configured_server_url"] == "http://127.0.0.1:27541"
        )
        assert (
            payload["coordination"]["discovered_server_url"] == "http://127.0.0.1:27541"
        )

    def test_runtime_cleanup_can_stop_unmanaged_local_processes(
        self, cli_runner: CliRunner, temp_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from pms.config.settings import reload_settings
        from pms.runtime.local_server import UnmanagedLocalServerProcess

        monkeypatch.delenv("PMS_API_KEY", raising=False)
        reload_settings()
        with cli_runner.isolated_filesystem(temp_dir=str(temp_env)):
            monkeypatch.setattr(
                "pms.runtime.local_server.cleanup_unmanaged_local_server_processes",
                lambda **_: [
                    UnmanagedLocalServerProcess(
                        pid=43210,
                        port=54132,
                        kind="pms_serve",
                        command=_GENERIC_LOCAL_SERVER_COMMAND,
                    )
                ],
            )

            cleanup_result = cli_runner.invoke(
                cli,
                ["runtime", "cleanup", "--include-unmanaged-local", "--format", "json"],
            )

        assert cleanup_result.exit_code == 0, cleanup_result.output
        payload = json.loads(cleanup_result.output)
        assert payload["stopped_unmanaged"][0]["pid"] == 43210
        assert payload["stopped_unmanaged"][0]["port"] == 54132
        assert payload["unmanaged_filters"]["ports"] == []
        assert payload["unmanaged_filters"]["pids"] == []

    def test_runtime_cleanup_can_target_unmanaged_local_processes_by_port_and_pid(
        self, cli_runner: CliRunner, temp_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from pms.config.settings import reload_settings
        from pms.runtime.local_server import UnmanagedLocalServerProcess

        monkeypatch.delenv("PMS_API_KEY", raising=False)
        reload_settings()
        captured: dict[str, object] = {}
        with cli_runner.isolated_filesystem(temp_dir=str(temp_env)):

            def _fake_cleanup_unmanaged_local_server_processes(**kwargs):
                captured.update(kwargs)
                return [
                    UnmanagedLocalServerProcess(
                        pid=43210,
                        port=54132,
                        kind="pms_serve",
                        command=_GENERIC_LOCAL_SERVER_COMMAND,
                    )
                ]

            monkeypatch.setattr(
                "pms.runtime.local_server.cleanup_unmanaged_local_server_processes",
                _fake_cleanup_unmanaged_local_server_processes,
            )

            cleanup_result = cli_runner.invoke(
                cli,
                [
                    "runtime",
                    "cleanup",
                    "--include-unmanaged-local",
                    "--unmanaged-port",
                    "54132",
                    "--unmanaged-pid",
                    "43210",
                    "--format",
                    "json",
                ],
            )

        assert cleanup_result.exit_code == 0, cleanup_result.output
        payload = json.loads(cleanup_result.output)
        assert captured["ports"] == {54132}
        assert captured["pids"] == {43210}
        assert payload["unmanaged_filters"]["ports"] == [54132]
        assert payload["unmanaged_filters"]["pids"] == [43210]
        assert payload["stopped_unmanaged"][0]["port"] == 54132
        assert payload["stopped_unmanaged"][0]["pid"] == 43210

    def test_runtime_cleanup_rejects_targeted_unmanaged_filters_without_include_flag(
        self, cli_runner: CliRunner, temp_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from pms.config.settings import reload_settings

        monkeypatch.delenv("PMS_API_KEY", raising=False)
        reload_settings()
        with cli_runner.isolated_filesystem(temp_dir=str(temp_env)):
            cleanup_result = cli_runner.invoke(
                cli,
                [
                    "runtime",
                    "cleanup",
                    "--unmanaged-port",
                    "54132",
                    "--format",
                    "json",
                ],
            )

        assert cleanup_result.exit_code == 1
        payload = json.loads(cleanup_result.output)
        assert "require --include-unmanaged-local" in payload["error"].lower()

    def test_runtime_cleanup_preserves_preferred_managed_server_by_default(
        self, cli_runner: CliRunner, temp_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from pms.config.settings import reload_settings
        from pms.runtime.local_server import ManagedLocalServerStatus

        monkeypatch.delenv("PMS_API_KEY", raising=False)
        reload_settings()
        captured: dict[str, object] = {}
        with cli_runner.isolated_filesystem(temp_dir=str(temp_env)):
            cli_runner.invoke(
                cli,
                [
                    "config",
                    "set",
                    "--write-mode",
                    "prefer_server",
                    "--server-url",
                    "http://127.0.0.1:27541",
                ],
            )

            preserved = ManagedLocalServerStatus(
                port=27541,
                server_url="http://127.0.0.1:27541",
                pid=111,
                tracked=True,
                running=True,
                reachable=True,
                pid_file="/tmp/server-27541.pid",
                log_file="/tmp/server-27541.log",
                error=None,
            )
            cleaned = ManagedLocalServerStatus(
                port=63266,
                server_url="http://127.0.0.1:63266",
                pid=222,
                tracked=True,
                running=True,
                reachable=True,
                pid_file="/tmp/server-63266.pid",
                log_file="/tmp/server-63266.log",
                error=None,
            )

            def _fake_cleanup_managed_local_servers(**kwargs):
                captured.update(kwargs)
                return [cleaned], [preserved], []

            monkeypatch.setattr(
                "pms.runtime.local_server.cleanup_managed_local_servers",
                _fake_cleanup_managed_local_servers,
            )

            cleanup_result = cli_runner.invoke(
                cli,
                ["runtime", "cleanup", "--format", "json"],
            )

        assert cleanup_result.exit_code == 0, cleanup_result.output
        payload = json.loads(cleanup_result.output)
        assert captured["preserve_server_url"] == "http://127.0.0.1:27541"
        assert payload["stopped"][0]["port"] == 63266
        assert payload["preserved_managed"][0]["port"] == 27541

    def test_runtime_cleanup_can_stop_all_managed_servers_explicitly(
        self, cli_runner: CliRunner, temp_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from pms.config.settings import reload_settings

        monkeypatch.delenv("PMS_API_KEY", raising=False)
        reload_settings()
        captured: dict[str, object] = {}
        with cli_runner.isolated_filesystem(temp_dir=str(temp_env)):
            cli_runner.invoke(
                cli,
                [
                    "config",
                    "set",
                    "--write-mode",
                    "prefer_server",
                    "--server-url",
                    "http://127.0.0.1:27541",
                ],
            )

            def _fake_cleanup_managed_local_servers(**kwargs):
                captured.update(kwargs)
                return [], [], []

            monkeypatch.setattr(
                "pms.runtime.local_server.cleanup_managed_local_servers",
                _fake_cleanup_managed_local_servers,
            )

            cleanup_result = cli_runner.invoke(
                cli,
                ["runtime", "cleanup", "--stop-all-managed", "--format", "json"],
            )

        assert cleanup_result.exit_code == 0, cleanup_result.output
        assert captured["preserve_server_url"] is None

    def test_runtime_cleanup_surfaces_failed_managed_stops_truthfully(
        self, cli_runner: CliRunner, temp_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from pms.config.settings import reload_settings
        from pms.runtime.local_server import ManagedLocalServerStatus

        monkeypatch.delenv("PMS_API_KEY", raising=False)
        reload_settings()
        with cli_runner.isolated_filesystem(temp_dir=str(temp_env)):
            failed = ManagedLocalServerStatus(
                port=27541,
                server_url="http://127.0.0.1:27541",
                pid=111,
                tracked=True,
                running=True,
                reachable=True,
                pid_file="/tmp/server-27541.pid",
                log_file="/tmp/server-27541.log",
                error="still reachable after stop attempt",
            )

            monkeypatch.setattr(
                "pms.runtime.local_server.cleanup_managed_local_servers",
                lambda **kwargs: ([], [], [failed]),
            )

            cleanup_result = cli_runner.invoke(
                cli,
                ["runtime", "cleanup", "--stop-all-managed", "--format", "json"],
            )

        assert cleanup_result.exit_code == 0, cleanup_result.output
        payload = json.loads(cleanup_result.output)
        assert payload["stopped"] == []
        assert payload["failed_managed"][0]["port"] == 27541
        assert payload["failed_managed"][0]["reachable"] is True
        assert (
            payload["failed_managed"][0]["error"]
            == "still reachable after stop attempt"
        )

    def test_runtime_prefer_server_reports_resolved_env_file(
        self, cli_runner: CliRunner, temp_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Runtime bootstrap should report the resolved env target it persisted."""
        from pms.config.settings import reload_settings

        monkeypatch.delenv("PMS_API_KEY", raising=False)
        with cli_runner.isolated_filesystem(temp_dir=str(temp_env)):
            env_path = Path.cwd() / "runtime.env"
            monkeypatch.setenv("PMS_ENV_FILE", str(env_path))
            reload_settings()

            help_result = cli_runner.invoke(cli, ["runtime", "prefer-server", "--help"])
            assert help_result.exit_code == 0, help_result.output
            _assert_plain_output_contains(help_result.output, "resolved env file")

            port, json_result = _invoke_runtime_prefer_server_with_retry(cli_runner)
            assert json_result.exit_code == 0, json_result.output
            json_payload = json.loads(json_result.output)
            assert json_payload["config_path"] == str(env_path.resolve())

            text_result = cli_runner.invoke(
                cli,
                [
                    "runtime",
                    "prefer-server",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--no-install-client",
                ],
            )
            assert text_result.exit_code == 0, text_result.output
            assert _extract_prefixed_value(
                text_result.output, "Config saved to env file:"
            ) == str(env_path.resolve())

    def test_runtime_prefer_server_clears_stale_env_api_key_override(
        self, cli_runner: CliRunner, temp_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from pms.config.settings import reload_settings

        monkeypatch.setenv("PMS_API_KEY", "pms_stale_override")
        reload_settings()
        with cli_runner.isolated_filesystem(temp_dir=str(temp_env)):
            port, result = _invoke_runtime_prefer_server_with_retry(cli_runner)
            assert result.exit_code == 0, result.output
            assert "PMS_API_KEY" not in os.environ

            status_result = cli_runner.invoke(
                cli, ["runtime", "status", "--format", "json"]
            )

            assert status_result.exit_code == 0, status_result.output
            payload = json.loads(status_result.output)
            assert payload["coordination"]["state"] == "server_coordinated"
            assert payload["coordination"]["can_delegate_writes"] is True

    def test_managed_local_server_bootstrap_pins_runtime_paths_in_spawn_env(
        self, temp_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from types import SimpleNamespace

        from pms.runtime.local_server import (
            active_local_server_state_path,
            ensure_local_server,
        )

        data_dir = temp_env / "managed-runtime"
        database_path = data_dir / "runtime.db"
        log_dir = data_dir / "runtime-logs"
        captured: dict[str, object] = {}
        health_checks = {"count": 0}

        def _fake_probe_server_health(server_url: str, timeout_seconds: float = 0.5):
            health_checks["count"] += 1
            reachable = health_checks["count"] >= 2
            return SimpleNamespace(
                base_url=server_url,
                reachable=reachable,
                status="healthy" if reachable else None,
                database="healthy" if reachable else None,
                error=None,
            )

        class _FakeProcess:
            pid = 43210

        def _fake_popen(*args, **kwargs):
            captured["env"] = kwargs["env"]
            captured["cwd"] = kwargs["cwd"]
            return _FakeProcess()

        monkeypatch.setattr(
            "pms.runtime.local_server.probe_server_health",
            _fake_probe_server_health,
        )
        monkeypatch.setattr("subprocess.Popen", _fake_popen)

        result = ensure_local_server(
            data_dir=data_dir,
            database_path=database_path,
            log_dir=log_dir,
            host="127.0.0.1",
            port=27541,
            timeout_seconds=0.2,
        )

        assert result.reachable is True
        assert captured["cwd"] == Path(__file__).resolve().parents[2]
        env = captured["env"]
        assert env["PMS_DATA_DIR"] == str(data_dir)
        assert env["PMS_DATABASE_PATH"] == str(database_path)
        assert env["PMS_LOG_DIR"] == str(log_dir)
        assert active_local_server_state_path(data_dir).exists()

    def test_managed_local_server_bootstrap_reuses_existing_active_server_for_same_port(
        self, temp_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from types import SimpleNamespace

        from pms.runtime.local_server import (
            ensure_local_server,
            write_active_local_server_state,
        )

        data_dir = temp_env / "managed-runtime"
        runtime_dir = data_dir / "runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        pid = os.getpid()
        write_active_local_server_state(
            data_dir,
            pid=pid,
            host="127.0.0.1",
            port=27541,
            log_file=str(runtime_dir / "server-27541.log"),
        )

        monkeypatch.setattr(
            "pms.runtime.local_server.probe_server_health",
            lambda server_url, timeout_seconds=0.5: SimpleNamespace(
                base_url=server_url,
                reachable=server_url == "http://127.0.0.1:27541",
                status="healthy" if server_url == "http://127.0.0.1:27541" else None,
                database="healthy" if server_url == "http://127.0.0.1:27541" else None,
                error=None if server_url == "http://127.0.0.1:27541" else "not active",
            ),
        )

        result = ensure_local_server(
            data_dir=data_dir,
            database_path=data_dir / "runtime.db",
            log_dir=data_dir / "runtime-logs",
            host="127.0.0.1",
            port=27541,
            timeout_seconds=0.2,
        )

        assert result.reachable is True
        assert result.started_now is False
        assert result.server_url == "http://127.0.0.1:27541"

    def test_managed_local_server_bootstrap_replaces_active_server_for_requested_port(
        self, temp_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from types import SimpleNamespace

        from pms.runtime.local_server import (
            active_local_server_state_path,
            ensure_local_server,
            write_active_local_server_state,
        )

        data_dir = temp_env / "managed-runtime"
        runtime_dir = data_dir / "runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        old_url = "http://127.0.0.1:27541"
        new_url = "http://127.0.0.1:8976"
        old_pid = 43210
        new_pid = 54321
        state = {
            "old_reachable": True,
            "old_pid_running": True,
            "new_health_checks": 0,
        }

        write_active_local_server_state(
            data_dir,
            pid=old_pid,
            host="127.0.0.1",
            port=27541,
            log_file=str(runtime_dir / "server-27541.log"),
        )

        def _fake_probe_server_health(server_url: str, timeout_seconds: float = 0.5):
            if server_url == old_url:
                reachable = state["old_reachable"]
            elif server_url == new_url:
                state["new_health_checks"] += 1
                reachable = state["new_health_checks"] >= 2
            else:
                reachable = False
            return SimpleNamespace(
                base_url=server_url,
                reachable=reachable,
                status="healthy" if reachable else None,
                database="healthy" if reachable else None,
                error=None if reachable else "not active",
            )

        class _FakeProcess:
            pid = new_pid

        monkeypatch.setattr(
            "pms.runtime.local_server.probe_server_health",
            _fake_probe_server_health,
        )
        monkeypatch.setattr(
            "pms.runtime.local_server.is_pid_running",
            lambda pid: state["old_pid_running"] if pid == old_pid else pid == new_pid,
        )
        monkeypatch.setattr(
            "pms.runtime.local_server._stop_pid",
            lambda pid, timeout_seconds=5.0, **kwargs: (
                state.__setitem__("old_reachable", False)
                or state.__setitem__("old_pid_running", False)
                or True
            ),
        )
        monkeypatch.setattr("subprocess.Popen", lambda *args, **kwargs: _FakeProcess())

        result = ensure_local_server(
            data_dir=data_dir,
            database_path=data_dir / "runtime.db",
            log_dir=data_dir / "runtime-logs",
            host="127.0.0.1",
            port=8976,
            timeout_seconds=0.2,
        )

        assert result.reachable is True
        assert result.started_now is True
        assert result.server_url == new_url
        assert result.pid == new_pid
        active_payload = json.loads(
            active_local_server_state_path(data_dir).read_text(encoding="utf-8")
        )
        assert active_payload["server_url"] == new_url
        assert active_payload["pid"] == new_pid

    def test_runtime_status_flags_unmanaged_reachable_local_server(
        self,
        cli_runner: CliRunner,
        temp_env: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        with cli_runner.isolated_filesystem(temp_dir=str(temp_env)):
            cli_runner.invoke(
                cli,
                [
                    "config",
                    "set",
                    "--write-mode",
                    "prefer_server",
                    "--server-url",
                    "http://127.0.0.1:8000",
                ],
            )

            monkeypatch.setattr(
                "pms.cli.app._runtime_server_payload",
                lambda: RuntimeServerPayload(
                    base_url="http://127.0.0.1:8000",
                    reachable=True,
                    status=200,
                    database="sqlite:///tmp/pms.db",
                    error=None,
                    checked=True,
                    api_key_present=True,
                ),
            )
            monkeypatch.setattr(
                "pms.cli.app._healthy_managed_runtime_server",
                lambda: None,
            )

            status_result = cli_runner.invoke(
                cli, ["runtime", "status", "--format", "json"]
            )
            assert status_result.exit_code == 0
            status_payload = json.loads(status_result.output)
            assert (
                status_payload["coordination"]["state"]
                == "degraded_unmanaged_local_server"
            )
            assert (
                status_payload["coordination"]["recovery"]["kind"]
                == "verify_managed_local_server"
            )

            config_result = cli_runner.invoke(
                cli, ["config", "show", "--format", "json"]
            )
            assert config_result.exit_code == 0
            config_payload = json.loads(config_result.output)
            assert (
                config_payload["runtime"]["coordination"]["state"]
                == "degraded_unmanaged_local_server"
            )

    def test_runtime_status_flags_reachable_server_with_invalid_api_key(
        self,
        cli_runner: CliRunner,
        temp_env: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        with cli_runner.isolated_filesystem(temp_dir=str(temp_env)):
            cli_runner.invoke(
                cli,
                [
                    "config",
                    "set",
                    "--write-mode",
                    "prefer_server",
                    "--server-url",
                    "http://127.0.0.1:27541",
                ],
            )

            monkeypatch.setattr(
                "pms.cli.app._runtime_server_payload",
                lambda: RuntimeServerPayload(
                    base_url="http://127.0.0.1:27541",
                    reachable=True,
                    status="healthy",
                    database="healthy",
                    error=None,
                    checked=True,
                    api_key_present=True,
                    api_key_authorized=False,
                    auth_error="Invalid API key",
                    api_key_source="env",
                ),
            )
            monkeypatch.setattr(
                "pms.cli.app._healthy_managed_runtime_server",
                lambda: {
                    "server_url": "http://127.0.0.1:27541",
                    "tracked": True,
                    "running": True,
                    "reachable": True,
                },
            )

            status_result = cli_runner.invoke(
                cli, ["runtime", "status", "--format", "json"]
            )
            assert status_result.exit_code == 0
            status_payload = json.loads(status_result.output)
            assert status_payload["coordination"]["state"] == "degraded_invalid_api_key"
            assert status_payload["coordination"]["can_delegate_writes"] is False

            config_result = cli_runner.invoke(
                cli, ["config", "show", "--format", "json"]
            )
            assert config_result.exit_code == 0
            config_payload = json.loads(config_result.output)
            assert (
                config_payload["runtime"]["coordination"]["state"]
                == "degraded_invalid_api_key"
            )
            assert config_payload["runtime"]["server"]["api_key_authorized"] is False
            assert (
                config_payload["runtime"]["server"]["auth_error"] == "Invalid API key"
            )
            assert config_payload["runtime"]["server"]["api_key_source"] == "env"

            text_result = cli_runner.invoke(cli, ["runtime", "status"])
            assert text_result.exit_code == 0
            _assert_plain_output_contains(
                text_result.output,
                "Coordination: degraded_invalid_api_key",
                "API key source: env",
                "Server auth: rejected",
                "Server auth error: Invalid API key",
            )

    def test_runtime_cleanup_then_prefer_server_restarts_same_port_truthfully(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Cleanup followed by same-port bootstrap should not report stale managed health."""
        from pms.config.settings import reload_settings

        reload_settings()
        port = _free_tcp_port()
        with cli_runner.isolated_filesystem(temp_dir=str(temp_env)):
            first_boot = cli_runner.invoke(
                cli,
                [
                    "runtime",
                    "prefer-server",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--no-install-client",
                    "--format",
                    "json",
                ],
            )
            assert first_boot.exit_code == 0

            cleanup_result = cli_runner.invoke(
                cli,
                ["runtime", "cleanup", "--format", "json"],
            )
            assert cleanup_result.exit_code == 0

            second_boot = cli_runner.invoke(
                cli,
                [
                    "runtime",
                    "prefer-server",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--no-install-client",
                    "--format",
                    "json",
                ],
            )
            assert second_boot.exit_code == 0
            payload = json.loads(second_boot.output)
            assert payload["server"]["reachable"] is True
            assert payload["runtime"]["coordination"]["state"] == "server_coordinated"

            status_result = cli_runner.invoke(
                cli,
                ["runtime", "status", "--format", "json"],
            )
            assert status_result.exit_code == 0
            status_payload = json.loads(status_result.output)
            item = next(
                entry for entry in status_payload["items"] if entry["port"] == port
            )
            assert item["running"] is True
            assert item["reachable"] is True

            stop_result = cli_runner.invoke(
                cli,
                ["runtime", "stop-local-server", "--port", str(port)],
            )
            assert stop_result.exit_code == 0

    def test_require_server_blocks_direct_task_progress(
        self, cli_runner: CliRunner, temp_env: Path
    ):
        """Mutating CLI commands should refuse direct writes when server mode is required."""
        from pms.config.settings import reload_settings

        reload_settings()
        with cli_runner.isolated_filesystem(temp_dir=str(temp_env)):
            cli_runner.invoke(cli, ["init"])
            cli_runner.invoke(cli, ["project", "create", "Server Required Project"])
            task_result = cli_runner.invoke(
                cli,
                ["task", "add", "Server Required Project", "Server Required Task"],
            )
            task_id = _extract_id(task_result.output)

            config_result = cli_runner.invoke(
                cli,
                [
                    "config",
                    "set",
                    "--write-mode",
                    "require_server",
                    "--server-url",
                    "http://127.0.0.1:1",
                ],
            )
            assert config_result.exit_code == 0

            blocked_result = cli_runner.invoke(
                cli,
                [
                    "task",
                    "progress",
                    task_id,
                    "50",
                    "Should be blocked",
                    "--by",
                    "tester",
                ],
            )
            assert blocked_result.exit_code == 0
            assert "Write blocked:" in blocked_result.output

            show_result = cli_runner.invoke(
                cli,
                ["task", "show", task_id, "--format", "json"],
            )

        assert show_result.exit_code == 0
        payload = json.loads(show_result.output)
        assert payload["current_progress_percent"] == 0

    def test_prefer_server_delegates_task_progress_when_runtime_allows(
        self, cli_runner: CliRunner, temp_env: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Task progress should use the server delegation helper when enabled."""
        from pms.config.settings import reload_settings
        from pms.core.events import EventStore
        from pms.core.metrics import MetricsCollector
        from pms.core.revisions import RevisionStore
        from pms.db.connection import init_database
        from pms.services.task_service import TaskService

        reload_settings()
        delegation_used = {"value": False}

        async def _fake_delegate_task_progress_to_server(
            *,
            task_id: str,
            percent: int,
            message: str,
            actor_id: str,
        ) -> dict[str, object]:
            delegation_used["value"] = True
            db = await init_database()
            try:
                service = TaskService(
                    db,
                    EventStore(db),
                    RevisionStore(db),
                    MetricsCollector(db),
                )
                await service.update_task_progress(
                    task_id=task_id,
                    percent_complete=percent,
                    status_message=message,
                    updated_by=actor_id,
                )
            finally:
                await db.disconnect()
            return {
                "task_id": task_id,
                "percent_complete": percent,
                "status_message": message,
                "updated_by": actor_id,
                "timestamp": "2026-04-07T03:00:00+00:00",
            }

        monkeypatch.setattr(
            "pms.cli.app._resolve_runtime_write_decision",
            lambda _action_name: RuntimeWriteDecision(
                allowed=True,
                use_server=True,
                payload=RuntimeServerPayload(
                    base_url="http://127.0.0.1:8000",
                    reachable=True,
                    status="healthy",
                    database="healthy",
                    error=None,
                    checked=True,
                    api_key_present=True,
                ),
                block_reason=None,
            ),
        )
        monkeypatch.setattr(
            "pms.cli.app._delegate_task_progress_to_server",
            _fake_delegate_task_progress_to_server,
        )

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Delegated Progress Project"])
        task_result = cli_runner.invoke(
            cli,
            ["task", "add", "Delegated Progress Project", "Delegated Progress Task"],
        )
        task_id = _extract_id(task_result.output)

        result = cli_runner.invoke(
            cli,
            [
                "task",
                "progress",
                task_id,
                "70",
                "Delegated update",
                "--by",
                "tester",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0, result.output
        assert delegation_used["value"] is True
        payload = json.loads(result.output)
        assert payload["task"]["status"] == "in_progress"
        assert payload["progress"]["percent"] == 70
        assert payload["progress"]["updated_by"] == "tester"

    def test_prefer_server_task_progress_uses_committed_server_response_when_local_read_lags(
        self, cli_runner: CliRunner, temp_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Delegated progress output should prefer committed server response truth."""
        from pms.config.settings import reload_settings
        from pms.models.enums import TaskStatus
        from pms.services.task_service import TaskService

        reload_settings()

        async def _fake_delegate_task_progress_to_server(
            *,
            task_id: str,
            percent: int,
            message: str,
            actor_id: str,
        ) -> dict[str, object]:
            return {
                "task_id": task_id,
                "percent_complete": 65,
                "status_message": "Committed by server",
                "updated_by": actor_id,
                "timestamp": "2026-04-07T03:00:00+00:00",
            }

        original_get_task = TaskService.get_task

        async def _stale_get_task(self, task_id: str):
            task = await original_get_task(self, task_id)
            assert task is not None
            task.current_progress_percent = 40
            task.status = TaskStatus.TODO
            task.last_progress_update_at = None
            return task

        monkeypatch.setattr(
            "pms.cli.app._resolve_runtime_write_decision",
            lambda _action_name: RuntimeWriteDecision(
                allowed=True,
                use_server=True,
                payload=RuntimeServerPayload(
                    base_url="http://127.0.0.1:27541",
                    reachable=True,
                    status="healthy",
                    database="healthy",
                    error=None,
                    checked=True,
                    api_key_present=True,
                ),
                block_reason=None,
            ),
        )
        monkeypatch.setattr(
            "pms.cli.app._delegate_task_progress_to_server",
            _fake_delegate_task_progress_to_server,
        )
        monkeypatch.setattr(TaskService, "get_task", _stale_get_task)

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(
            cli, ["project", "create", "Delegated Progress Truth Project"]
        )
        task_result = cli_runner.invoke(
            cli,
            [
                "task",
                "add",
                "Delegated Progress Truth Project",
                "Delegated Progress Truth Task",
            ],
        )
        task_id = _extract_id(task_result.output)

        result = cli_runner.invoke(
            cli,
            [
                "task",
                "progress",
                task_id,
                "85",
                "Requested by client",
                "--by",
                "tester",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["task"]["status"] == "in_progress"
        assert payload["task"]["current_progress_percent"] == 65
        assert payload["progress"]["percent"] == 65
        assert payload["progress"]["message"] == "Committed by server"
        assert payload["progress"]["updated_by"] == "tester"

    def test_prefer_server_delegates_task_start_when_runtime_allows(
        self, cli_runner: CliRunner, temp_env: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Task start should use the server delegation helper when enabled."""
        from pms.config.settings import reload_settings
        from pms.core.events import EventStore
        from pms.core.metrics import MetricsCollector
        from pms.core.revisions import RevisionStore
        from pms.db.connection import init_database
        from pms.services.task_service import TaskService

        reload_settings()
        delegation_used = {"value": False}

        async def _fake_delegate_task_start_to_server(
            *,
            task_id: str,
            actor_id: str,
        ) -> None:
            delegation_used["value"] = True
            db = await init_database()
            try:
                service = TaskService(
                    db,
                    EventStore(db),
                    RevisionStore(db),
                    MetricsCollector(db),
                )
                await service.start_task(task_id)
            finally:
                await db.disconnect()

        monkeypatch.setattr(
            "pms.cli.app._resolve_runtime_write_decision",
            lambda _action_name: RuntimeWriteDecision(
                allowed=True,
                use_server=True,
                payload=RuntimeServerPayload(
                    base_url="http://127.0.0.1:8000",
                    reachable=True,
                    status="healthy",
                    database="healthy",
                    error=None,
                    checked=True,
                    api_key_present=True,
                ),
                block_reason=None,
            ),
        )
        monkeypatch.setattr(
            "pms.cli.app._delegate_task_start_to_server",
            _fake_delegate_task_start_to_server,
        )

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Delegated Start Project"])
        task_result = cli_runner.invoke(
            cli,
            ["task", "add", "Delegated Start Project", "Delegated Start Task"],
        )
        task_id = _extract_id(task_result.output)

        result = cli_runner.invoke(
            cli,
            ["task", "start", task_id, "--by", "tester", "--format", "json"],
        )

        assert result.exit_code == 0, result.output
        assert delegation_used["value"] is True
        payload = json.loads(result.output)
        assert payload["task"]["status"] == "in_progress"

    def test_prefer_server_task_start_recovers_when_server_response_fails_after_mutation(
        self, cli_runner: CliRunner, temp_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Task start should recover if the server mutates state before failing the response."""
        import httpx

        from pms.config.settings import reload_settings
        from pms.core.events import EventStore
        from pms.core.metrics import MetricsCollector
        from pms.core.revisions import RevisionStore
        from pms.db.connection import init_database
        from pms.services.task_service import TaskService

        reload_settings()

        async def _delegate_then_fail(*, task_id: str, actor_id: str) -> None:
            db = await init_database()
            try:
                service = TaskService(
                    db,
                    EventStore(db),
                    RevisionStore(db),
                    MetricsCollector(db),
                )
                await service.start_task(task_id)
            finally:
                await db.disconnect()

            request = httpx.Request(
                "POST",
                f"http://127.0.0.1:8000/api/v1/tasks/{task_id}/start",
            )
            response = httpx.Response(500, request=request)
            raise httpx.HTTPStatusError(
                "Server error '500 Internal Server Error'",
                request=request,
                response=response,
            )

        monkeypatch.setattr(
            "pms.cli.app._resolve_runtime_write_decision",
            lambda _action_name: RuntimeWriteDecision(
                allowed=True,
                use_server=True,
                payload=RuntimeServerPayload(
                    base_url="http://127.0.0.1:8000",
                    reachable=True,
                    status="healthy",
                    database="healthy",
                    error=None,
                    checked=True,
                    api_key_present=True,
                ),
                block_reason=None,
            ),
        )
        monkeypatch.setattr(
            "pms.cli.app._delegate_task_start_to_server",
            _delegate_then_fail,
        )

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Delegated Recovery Project"])
        task_result = cli_runner.invoke(
            cli,
            ["task", "add", "Delegated Recovery Project", "Delegated Recovery Task"],
        )
        task_id = _extract_id(task_result.output)

        result = cli_runner.invoke(
            cli,
            ["task", "start", task_id, "--by", "tester", "--format", "json"],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["task"]["status"] == "in_progress"
        assert payload["messages"][0]["level"] == "warning"
        assert (
            "response failed after the task transitioned"
            in payload["messages"][0]["message"]
        )

    def test_prefer_server_task_progress_recovers_when_server_response_fails_after_mutation(
        self, cli_runner: CliRunner, temp_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Task progress should recover if the server mutates state before failing the response."""
        import httpx

        from pms.config.settings import reload_settings
        from pms.core.events import EventStore
        from pms.core.metrics import MetricsCollector
        from pms.core.revisions import RevisionStore
        from pms.db.connection import init_database
        from pms.services.task_service import TaskService

        reload_settings()

        async def _delegate_then_fail(
            *,
            task_id: str,
            percent: int,
            message: str,
            actor_id: str,
        ) -> None:
            db = await init_database()
            try:
                service = TaskService(
                    db,
                    EventStore(db),
                    RevisionStore(db),
                    MetricsCollector(db),
                )
                await service.update_task_progress(
                    task_id=task_id,
                    percent_complete=percent,
                    status_message=message,
                    updated_by=actor_id,
                )
            finally:
                await db.disconnect()

            request = httpx.Request(
                "POST",
                f"http://127.0.0.1:8000/api/v1/tasks/{task_id}/progress",
            )
            response = httpx.Response(500, request=request)
            raise httpx.HTTPStatusError(
                "Server error '500 Internal Server Error'",
                request=request,
                response=response,
            )

        monkeypatch.setattr(
            "pms.cli.app._resolve_runtime_write_decision",
            lambda _action_name: RuntimeWriteDecision(
                allowed=True,
                use_server=True,
                payload=RuntimeServerPayload(
                    base_url="http://127.0.0.1:8000",
                    reachable=True,
                    status="healthy",
                    database="healthy",
                    error=None,
                    checked=True,
                    api_key_present=True,
                ),
                block_reason=None,
            ),
        )
        monkeypatch.setattr(
            "pms.cli.app._delegate_task_progress_to_server",
            _delegate_then_fail,
        )

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(
            cli, ["project", "create", "Delegated Progress Recovery Project"]
        )
        task_result = cli_runner.invoke(
            cli,
            [
                "task",
                "add",
                "Delegated Progress Recovery Project",
                "Delegated Progress Recovery Task",
            ],
        )
        task_id = _extract_id(task_result.output)

        result = cli_runner.invoke(
            cli,
            [
                "task",
                "progress",
                task_id,
                "55",
                "Recovered delegated progress",
                "--by",
                "tester",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["task"]["status"] == "in_progress"
        assert payload["progress"]["percent"] == 55
        assert payload["task"]["current_progress_percent"] == 55
        assert payload["messages"][0]["level"] == "warning"
        assert (
            "response failed after the task state was updated"
            in payload["messages"][0]["message"]
        )

        project_show = cli_runner.invoke(
            cli,
            [
                "project",
                "show",
                "Delegated Progress Recovery Project",
                "--format",
                "json",
            ],
        )
        assert project_show.exit_code == 0, project_show.output
        project_payload = json.loads(project_show.output)
        assert (
            project_payload["focus_task"]["title"] == "Delegated Progress Recovery Task"
        )
        assert project_payload["focus_task"]["current_progress_percent"] == 55
        assert project_payload["execution"]["active_tasks"][0]["progress_percent"] == 55

    def test_task_progress_auto_starts_todo_task(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Progress on a todo task should auto-transition it into in_progress."""
        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Progress Auto Start Project"])
        task_result = cli_runner.invoke(
            cli,
            ["task", "add", "Progress Auto Start Project", "Progress Auto Start Task"],
        )
        task_id = _extract_id(task_result.output)

        result = cli_runner.invoke(
            cli,
            [
                "task",
                "progress",
                task_id,
                "35",
                "Started by progress",
                "--by",
                "tester",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["task"]["status"] == "in_progress"
        assert payload["task"]["current_progress_percent"] == 35

    def test_project_show_reflects_progress_for_recently_started_task(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Project focus/readback should reflect progress immediately after start+progress."""
        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Recent Progress Project"])
        task_result = cli_runner.invoke(
            cli,
            ["task", "add", "Recent Progress Project", "Recent Progress Task"],
        )
        task_id = _extract_id(task_result.output)

        started = cli_runner.invoke(
            cli,
            [
                "task",
                "start",
                task_id,
                "--project",
                "Recent Progress Project",
                "--by",
                "tester",
                "--format",
                "json",
            ],
        )
        assert started.exit_code == 0, started.output

        progressed = cli_runner.invoke(
            cli,
            [
                "task",
                "progress",
                task_id,
                "20",
                "Recent progress update",
                "--project",
                "Recent Progress Project",
                "--by",
                "tester",
                "--format",
                "json",
            ],
        )
        assert progressed.exit_code == 0, progressed.output
        progress_payload = json.loads(progressed.output)
        assert progress_payload["task"]["current_progress_percent"] == 20

        project_show = cli_runner.invoke(
            cli,
            ["project", "show", "Recent Progress Project", "--format", "json"],
        )
        assert project_show.exit_code == 0, project_show.output
        project_payload = json.loads(project_show.output)
        assert project_payload["focus_task"]["title"] == "Recent Progress Task"
        assert project_payload["focus_task"]["current_progress_percent"] == 20
        assert project_payload["execution"]["active_tasks"][0]["progress_percent"] == 20
        assert any(
            step.startswith(_cli_step("task progress "))
            for step in project_payload["next_steps"]
        )
        assert any(
            step.startswith(_cli_step("task show "))
            for step in project_payload["next_steps"]
        )

    def test_goal_list_honors_status_and_project_together(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Goal list should honor combined status and project filters."""
        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Goal Filter Project A"])
        cli_runner.invoke(cli, ["project", "create", "Goal Filter Project B"])

        goal_a = cli_runner.invoke(
            cli,
            [
                "goal",
                "create",
                "Completed Goal A",
                "--project",
                "Goal Filter Project A",
                "--format",
                "json",
            ],
        )
        goal_b = cli_runner.invoke(
            cli,
            [
                "goal",
                "create",
                "Active Goal B",
                "--project",
                "Goal Filter Project A",
                "--format",
                "json",
            ],
        )
        goal_c = cli_runner.invoke(
            cli,
            [
                "goal",
                "create",
                "Completed Goal C",
                "--project",
                "Goal Filter Project B",
                "--format",
                "json",
            ],
        )
        goal_a_id = json.loads(goal_a.output)["goal"]["id"]
        goal_b_id = json.loads(goal_b.output)["goal"]["id"]
        goal_c_id = json.loads(goal_c.output)["goal"]["id"]

        cli_runner.invoke(cli, ["goal", "complete", goal_a_id])
        cli_runner.invoke(cli, ["goal", "complete", goal_c_id])

        result = cli_runner.invoke(
            cli,
            [
                "goal",
                "list",
                "--project",
                "Goal Filter Project A",
                "--status",
                "completed",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        item_ids = [item["id"] for item in payload["items"]]
        assert goal_a_id in item_ids
        assert {item["status"] for item in payload["items"]} == {"completed"}
        assert {item["project_name"] for item in payload["items"]} == {
            "Goal Filter Project A"
        }
        assert goal_b_id not in item_ids
        assert goal_c_id not in item_ids

    def test_goal_list_json_is_machine_parseable_with_long_goal_names(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Goal list JSON should remain parseable even when names are long."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Long Goal Project"])
        cli_runner.invoke(
            cli,
            [
                "goal",
                "create",
                "Re-architect PMS around authoritative query semantics, explicit population contracts, mutation-readback guarantees, parity audits, and failure-loud runtime safety",
                "--project",
                "Long Goal Project",
            ],
        )

        result = cli_runner.invoke(
            cli,
            ["goal", "list", "--project", "Long Goal Project", "--format", "json"],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["items"][0]["project_name"] == "Long Goal Project"
        assert "failure-loud runtime safety" in payload["items"][0]["name"]

    def test_objective_list_honors_status_and_goal_together(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Objective list should honor combined status and goal filters."""
        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Objective Filter Project"])
        goal_result = cli_runner.invoke(
            cli,
            [
                "goal",
                "create",
                "Objective Filter Goal",
                "--project",
                "Objective Filter Project",
                "--format",
                "json",
            ],
        )
        other_goal_result = cli_runner.invoke(
            cli,
            [
                "goal",
                "create",
                "Other Objective Goal",
                "--project",
                "Objective Filter Project",
                "--format",
                "json",
            ],
        )
        goal_id = json.loads(goal_result.output)["goal"]["id"]
        other_goal_id = json.loads(other_goal_result.output)["goal"]["id"]

        objective_a = cli_runner.invoke(
            cli,
            [
                "objective",
                "create",
                "Completed Objective A",
                "--goal-id",
                goal_id,
                "--format",
                "json",
            ],
        )
        objective_b = cli_runner.invoke(
            cli,
            [
                "objective",
                "create",
                "Active Objective B",
                "--goal-id",
                goal_id,
                "--format",
                "json",
            ],
        )
        objective_c = cli_runner.invoke(
            cli,
            [
                "objective",
                "create",
                "Completed Objective C",
                "--goal-id",
                other_goal_id,
                "--format",
                "json",
            ],
        )
        objective_a_id = json.loads(objective_a.output)["objective"]["id"]
        objective_b_id = json.loads(objective_b.output)["objective"]["id"]
        objective_c_id = json.loads(objective_c.output)["objective"]["id"]

        cli_runner.invoke(cli, ["objective", "complete", objective_a_id])
        cli_runner.invoke(cli, ["objective", "complete", objective_c_id])

        result = cli_runner.invoke(
            cli,
            [
                "objective",
                "list",
                "--goal-id",
                goal_id,
                "--status",
                "completed",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        item_ids = [item["id"] for item in payload["items"]]
        assert item_ids == [objective_a_id]
        assert {item["status"] for item in payload["items"]} == {"completed"}
        assert {item["goal_id"] for item in payload["items"]} == {goal_id}
        assert objective_b_id not in item_ids
        assert objective_c_id not in item_ids

    def test_objective_list_json_is_machine_parseable_with_long_names(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Objective list JSON should remain parseable when names are long."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Long Objective Project"])
        goal_result = cli_runner.invoke(
            cli,
            [
                "goal",
                "create",
                "Long Objective Goal",
                "--project",
                "Long Objective Project",
                "--format",
                "json",
            ],
        )
        goal_id = json.loads(goal_result.output)["goal"]["id"]
        cli_runner.invoke(
            cli,
            [
                "objective",
                "create",
                "Preserve machine-readable list outputs even when objective names are long enough to wrap in terminal display rendering",
                "--goal-id",
                goal_id,
            ],
        )

        result = cli_runner.invoke(
            cli,
            ["objective", "list", "--goal-id", goal_id, "--format", "json"],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["items"][0]["goal_id"] == goal_id
        assert "machine-readable list outputs" in payload["items"][0]["name"]

    def test_keyresult_list_honors_status_and_objective_together(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Key result list should honor combined status and objective filters."""
        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Key Result Filter Project"])
        goal_result = cli_runner.invoke(
            cli,
            [
                "goal",
                "create",
                "Key Result Goal",
                "--project",
                "Key Result Filter Project",
                "--format",
                "json",
            ],
        )
        goal_id = json.loads(goal_result.output)["goal"]["id"]
        objective_a = cli_runner.invoke(
            cli,
            [
                "objective",
                "create",
                "Key Result Objective A",
                "--goal-id",
                goal_id,
                "--format",
                "json",
            ],
        )
        objective_b = cli_runner.invoke(
            cli,
            [
                "objective",
                "create",
                "Key Result Objective B",
                "--goal-id",
                goal_id,
                "--format",
                "json",
            ],
        )
        objective_a_id = json.loads(objective_a.output)["objective"]["id"]
        objective_b_id = json.loads(objective_b.output)["objective"]["id"]

        key_result_a = cli_runner.invoke(
            cli,
            [
                "keyresult",
                "create",
                "Completed KR A",
                "--objective-id",
                objective_a_id,
                "--current",
                "0",
                "--target",
                "100",
            ],
        )
        key_result_b = cli_runner.invoke(
            cli,
            [
                "keyresult",
                "create",
                "Active KR B",
                "--objective-id",
                objective_a_id,
                "--current",
                "0",
                "--target",
                "100",
            ],
        )
        key_result_c = cli_runner.invoke(
            cli,
            [
                "keyresult",
                "create",
                "Completed KR C",
                "--objective-id",
                objective_b_id,
                "--current",
                "0",
                "--target",
                "100",
            ],
        )
        key_result_a_id = _extract_id(key_result_a.output)
        key_result_b_id = _extract_id(key_result_b.output)
        key_result_c_id = _extract_id(key_result_c.output)

        cli_runner.invoke(cli, ["keyresult", "complete", key_result_a_id])
        cli_runner.invoke(cli, ["keyresult", "complete", key_result_c_id])

        result = cli_runner.invoke(
            cli,
            [
                "keyresult",
                "list",
                "--objective-id",
                objective_a_id,
                "--status",
                "completed",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        item_ids = [item["id"] for item in payload["items"]]
        assert item_ids == [key_result_a_id]
        assert {item["status"] for item in payload["items"]} == {"completed"}
        assert {item["objective_id"] for item in payload["items"]} == {objective_a_id}
        assert key_result_b_id not in item_ids
        assert key_result_c_id not in item_ids

    def test_prefer_server_task_start_handles_conflict_without_traceback(
        self, cli_runner: CliRunner, temp_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Task start should surface server conflicts as structured guidance, not a traceback."""
        import httpx

        from pms.config.settings import reload_settings
        from pms.core.events import EventStore
        from pms.core.metrics import MetricsCollector
        from pms.core.revisions import RevisionStore
        from pms.db.connection import init_database
        from pms.services.task_service import TaskService

        reload_settings()

        async def _delegate_conflict(*, task_id: str, actor_id: str) -> None:
            request = httpx.Request(
                "POST",
                f"http://127.0.0.1:8000/api/v1/tasks/{task_id}/start",
            )
            response = httpx.Response(
                409,
                request=request,
                json={"detail": "Cannot start task in done status"},
            )
            raise httpx.HTTPStatusError(
                "Client error '409 Conflict'",
                request=request,
                response=response,
            )

        monkeypatch.setattr(
            "pms.cli.app._resolve_runtime_write_decision",
            lambda _action_name: RuntimeWriteDecision(
                allowed=True,
                use_server=True,
                payload=RuntimeServerPayload(
                    base_url="http://127.0.0.1:8000",
                    reachable=True,
                    status="healthy",
                    database="healthy",
                    error=None,
                    checked=True,
                    api_key_present=True,
                ),
                block_reason=None,
            ),
        )
        monkeypatch.setattr(
            "pms.cli.app._delegate_task_start_to_server",
            _delegate_conflict,
        )

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(
            cli, ["project", "create", "Delegated Start Conflict Project"]
        )
        task_result = cli_runner.invoke(
            cli,
            [
                "task",
                "add",
                "Delegated Start Conflict Project",
                "Delegated Start Conflict Task",
            ],
        )
        task_id = _extract_id(task_result.output)

        db = asyncio.run(init_database())
        try:
            service = TaskService(
                db,
                EventStore(db),
                RevisionStore(db),
                MetricsCollector(db),
            )
            asyncio.run(service.complete_task(task_id))
        finally:
            asyncio.run(db.disconnect())

        result = cli_runner.invoke(
            cli,
            ["task", "start", task_id, "--by", "tester", "--format", "json"],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["task"]["status"] == "done"
        assert payload["messages"][0]["level"] == "warning"
        assert "Cannot start task in done status" in payload["messages"][0]["message"]

    def test_prefer_server_delegates_goal_create_when_runtime_allows(
        self, cli_runner: CliRunner, temp_env: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Goal create should use the server delegation helper when enabled."""
        from pms.config.settings import reload_settings
        from pms.core.events import EventStore
        from pms.core.metrics import MetricsCollector
        from pms.core.revisions import RevisionStore
        from pms.db.connection import init_database
        from pms.models import GoalHorizon
        from pms.services.goal_service import GoalService

        reload_settings()
        delegation_used = {"value": False}

        async def _fake_delegate_goal_create_to_server(
            **kwargs: object,
        ) -> dict[str, object]:
            delegation_used["value"] = True
            db = await init_database()
            try:
                service = GoalService(
                    db,
                    EventStore(db),
                    RevisionStore(db),
                    MetricsCollector(db),
                )
                goal = await service.create_goal(
                    name=str(kwargs["name"]),
                    description=str(kwargs["description"])
                    if kwargs["description"] is not None
                    else None,
                    horizon=GoalHorizon(str(kwargs["horizon"])),
                    target_date=None,
                    owner=str(kwargs["owner"]) if kwargs["owner"] is not None else None,
                    product_id=(
                        str(kwargs["product_id"])
                        if kwargs["product_id"] is not None
                        else None
                    ),
                    project_id=(
                        str(kwargs["project_id"])
                        if kwargs["project_id"] is not None
                        else None
                    ),
                    tags=list(kwargs["tags"]) if kwargs["tags"] is not None else None,
                    progress_percent=int(kwargs["progress_percent"]),
                )
                return {"id": goal.id}
            finally:
                await db.disconnect()

        monkeypatch.setattr(
            "pms.cli.app._resolve_runtime_write_decision",
            lambda _action_name: RuntimeWriteDecision(
                allowed=True,
                use_server=True,
                payload=RuntimeServerPayload(
                    base_url="http://127.0.0.1:8000",
                    reachable=True,
                    status="healthy",
                    database="healthy",
                    error=None,
                    checked=True,
                    api_key_present=True,
                ),
                block_reason=None,
            ),
        )
        monkeypatch.setattr(
            "pms.cli.app._delegate_goal_create_to_server",
            _fake_delegate_goal_create_to_server,
        )

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Delegated Goal Project"])
        result = cli_runner.invoke(
            cli,
            [
                "goal",
                "create",
                "Delegated Goal",
                "--project",
                "Delegated Goal Project",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0, result.output
        assert delegation_used["value"] is True
        payload = json.loads(result.output)
        assert payload["goal"]["name"] == "Delegated Goal"
        assert payload["runtime_write"]["write_path"] == "server_delegated"
        assert payload["runtime_write"]["target_kind"] == "server"
        assert payload["runtime_write"]["target_location"] == "http://127.0.0.1:8000"

    def test_plan_create_text_omits_success_runtime_write_path(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Plan create text output should avoid noisy success runtime plumbing."""
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(
            cli,
            ["plan", "create", "Text Runtime Plan", "--content", "{}"],
        )

        assert result.exit_code == 0, result.output
        plain = _assert_plain_output_contains(result.output, "Created plan:")
        assert "Write path:" not in plain
        assert "Runtime: delegating write" not in plain

    def test_prefer_server_delegates_plan_create_when_runtime_allows(
        self, cli_runner: CliRunner, temp_env: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Plan create should use the server delegation helper when enabled."""
        from pms.config.settings import reload_settings
        from pms.core.events import EventStore
        from pms.core.metrics import MetricsCollector
        from pms.core.revisions import RevisionStore
        from pms.db.connection import init_database
        from pms.models import PlanFormat, PlanStatus
        from pms.services.plan_service import PlanService

        reload_settings()
        delegation_used = {"value": False}

        async def _fake_delegate_plan_create_to_server(
            **kwargs: object,
        ) -> dict[str, object]:
            delegation_used["value"] = True
            db = await init_database()
            try:
                service = PlanService(
                    db,
                    EventStore(db),
                    RevisionStore(db),
                    MetricsCollector(db),
                )
                plan = await service.create_plan(
                    name=str(kwargs["name"]),
                    description=str(kwargs["description"])
                    if kwargs["description"] is not None
                    else None,
                    status=PlanStatus(str(kwargs["status"])),
                    format=PlanFormat(str(kwargs["plan_format"])),
                    content=kwargs["content"],
                    product_id=(
                        str(kwargs["product_id"])
                        if kwargs["product_id"] is not None
                        else None
                    ),
                    project_id=(
                        str(kwargs["project_id"])
                        if kwargs["project_id"] is not None
                        else None
                    ),
                    goal_id=str(kwargs["goal_id"])
                    if kwargs["goal_id"] is not None
                    else None,
                    objective_id=(
                        str(kwargs["objective_id"])
                        if kwargs["objective_id"] is not None
                        else None
                    ),
                    task_ids=list(kwargs["task_ids"])
                    if kwargs["task_ids"] is not None
                    else None,
                    tags=list(kwargs["tags"]) if kwargs["tags"] is not None else None,
                )
                return {"id": plan.id}
            finally:
                await db.disconnect()

        monkeypatch.setattr(
            "pms.cli.app._resolve_runtime_write_decision",
            lambda _action_name: RuntimeWriteDecision(
                allowed=True,
                use_server=True,
                payload=RuntimeServerPayload(
                    base_url="http://127.0.0.1:8000",
                    reachable=True,
                    status="healthy",
                    database="healthy",
                    error=None,
                    checked=True,
                    api_key_present=True,
                ),
                block_reason=None,
            ),
        )
        monkeypatch.setattr(
            "pms.cli.app._delegate_plan_create_to_server",
            _fake_delegate_plan_create_to_server,
        )

        cli_runner.invoke(cli, ["init"])
        result = cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Delegated Plan",
                "--content",
                "{}",
                "--output-format",
                "json",
            ],
        )

        assert result.exit_code == 0, result.output
        assert delegation_used["value"] is True
        payload = json.loads(result.output)
        assert payload["plan"]["name"] == "Delegated Plan"
        assert payload["runtime_write"]["write_path"] == "server_delegated"
        assert payload["runtime_write"]["target_kind"] == "server"
        assert payload["runtime_write"]["target_location"] == "http://127.0.0.1:8000"
        assert payload["links"]["self"].startswith(_cli_step("plan show "))

        text_result = cli_runner.invoke(
            cli,
            ["plan", "create", "Delegated Plan Text", "--content", "{}"],
        )

        assert text_result.exit_code == 0, text_result.output
        plain = _assert_plain_output_contains(text_result.output, "Created plan:")
        assert "Runtime: delegating write" not in plain
        assert "Write path:" not in plain

    def test_prefer_server_plan_create_output_format_json_returns_machine_output(
        self, cli_runner: CliRunner, temp_env: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from pms.config.settings import reload_settings
        from pms.core.events import EventStore
        from pms.core.metrics import MetricsCollector
        from pms.core.revisions import RevisionStore
        from pms.db.connection import init_database
        from pms.models import PlanFormat, PlanStatus
        from pms.services.plan_service import PlanService

        reload_settings()
        delegation_used = {"value": False}

        async def _fake_delegate_plan_create_to_server(
            **kwargs: object,
        ) -> dict[str, object]:
            delegation_used["value"] = True
            db = await init_database()
            try:
                service = PlanService(
                    db,
                    EventStore(db),
                    RevisionStore(db),
                    MetricsCollector(db),
                )
                plan = await service.create_plan(
                    name=str(kwargs["name"]),
                    description=str(kwargs["description"])
                    if kwargs["description"] is not None
                    else None,
                    status=PlanStatus(str(kwargs["status"])),
                    format=PlanFormat(str(kwargs["plan_format"])),
                    content=kwargs["content"],
                    product_id=(
                        str(kwargs["product_id"])
                        if kwargs["product_id"] is not None
                        else None
                    ),
                    project_id=(
                        str(kwargs["project_id"])
                        if kwargs["project_id"] is not None
                        else None
                    ),
                    goal_id=str(kwargs["goal_id"])
                    if kwargs["goal_id"] is not None
                    else None,
                    objective_id=(
                        str(kwargs["objective_id"])
                        if kwargs["objective_id"] is not None
                        else None
                    ),
                    task_ids=list(kwargs["task_ids"])
                    if kwargs["task_ids"] is not None
                    else None,
                    tags=list(kwargs["tags"]) if kwargs["tags"] is not None else None,
                )
                return {"id": plan.id}
            finally:
                await db.disconnect()

        monkeypatch.setattr(
            "pms.cli.app._resolve_runtime_write_decision",
            lambda _action_name: RuntimeWriteDecision(
                allowed=True,
                use_server=True,
                payload=RuntimeServerPayload(
                    base_url="http://127.0.0.1:8000",
                    reachable=True,
                    status="healthy",
                    database="healthy",
                    error=None,
                    checked=True,
                    api_key_present=True,
                ),
                block_reason=None,
            ),
        )
        monkeypatch.setattr(
            "pms.cli.app._delegate_plan_create_to_server",
            _fake_delegate_plan_create_to_server,
        )

        cli_runner.invoke(cli, ["init"])
        result = cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Implicit Delegated JSON Output Plan",
                "--content",
                "{}",
                "--output-format",
                "json",
            ],
        )

        assert result.exit_code == 0, result.output
        assert delegation_used["value"] is True
        payload = json.loads(result.output)
        assert payload["plan"]["name"] == "Implicit Delegated JSON Output Plan"
        assert payload["runtime_write"]["write_path"] == "server_delegated"
        assert payload["runtime_write"]["target_location"] == "http://127.0.0.1:8000"

    def test_plan_create_json_includes_runtime_write_context(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Plan create JSON should expose the effective write path and target."""
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Runtime Write Plan",
                "--content",
                "{}",
                "--output-format",
                "json",
            ],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["plan"]["name"] == "Runtime Write Plan"
        assert payload["runtime_write"]["write_path"] == "direct_file"
        assert payload["runtime_write"]["target_kind"] == "workspace_sqlite"
        assert (
            payload["runtime_write"]["target_location"]
            == payload["runtime_write"]["workspace"]["database_path"]
        )

    def test_plan_create_output_format_json_returns_machine_readable_output(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Implicit JSON Output Plan",
                "--content",
                "{}",
                "--output-format",
                "json",
            ],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["plan"]["name"] == "Implicit JSON Output Plan"
        assert payload["runtime_write"]["write_path"] == "direct_file"

    def test_prefer_server_delegates_task_complete_with_actual_hours(
        self, cli_runner: CliRunner, temp_env: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Task complete should preserve actual hours when delegated through the server."""
        from pms.config.settings import reload_settings
        from pms.core.events import EventStore
        from pms.core.metrics import MetricsCollector
        from pms.core.revisions import RevisionStore
        from pms.db.connection import init_database
        from pms.services.task_service import TaskService

        reload_settings()
        delegation_used = {"value": False}

        async def _fake_delegate_task_complete_to_server(
            *,
            task_id: str,
            notes: str | None,
            actor_id: str | None,
            actual_hours: float | None,
        ) -> None:
            delegation_used["value"] = True
            db = await init_database()
            try:
                service = TaskService(
                    db,
                    EventStore(db),
                    RevisionStore(db),
                    MetricsCollector(db),
                )
                await service.complete_task(
                    task_id,
                    notes=notes,
                    actual_hours=actual_hours,
                )
            finally:
                await db.disconnect()

        monkeypatch.setattr(
            "pms.cli.app._resolve_runtime_write_decision",
            lambda _action_name: RuntimeWriteDecision(
                allowed=True,
                use_server=True,
                payload=RuntimeServerPayload(
                    base_url="http://127.0.0.1:8000",
                    reachable=True,
                    status="healthy",
                    database="healthy",
                    error=None,
                    checked=True,
                    api_key_present=True,
                ),
                block_reason=None,
            ),
        )
        monkeypatch.setattr(
            "pms.cli.app._delegate_task_complete_to_server",
            _fake_delegate_task_complete_to_server,
        )

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Delegated Complete Project"])
        task_result = cli_runner.invoke(
            cli,
            ["task", "add", "Delegated Complete Project", "Delegated Complete Task"],
        )
        task_id = _extract_id(task_result.output)
        cli_runner.invoke(cli, ["task", "start", task_id, "--by", "tester"])

        result = cli_runner.invoke(
            cli,
            [
                "task",
                "complete",
                task_id,
                "--by",
                "tester",
                "--actual-hours",
                "2.5",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0, result.output
        assert delegation_used["value"] is True
        payload = json.loads(result.output)
        assert payload["task"]["status"] == "done"
        assert payload["task"]["actual_hours"] == 2.5

    def test_prefer_server_task_complete_immediate_readback_is_consistent(
        self, cli_runner: CliRunner, temp_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Once delegated completion returns, task/project/goal/objective reads should agree."""
        from pms.config.settings import reload_settings
        from pms.core.events import EventStore
        from pms.core.metrics import MetricsCollector
        from pms.core.revisions import RevisionStore
        from pms.db.connection import init_database
        from pms.services.task_service import TaskService

        reload_settings()

        async def _fake_delegate_task_complete_to_server(
            *,
            task_id: str,
            notes: str | None,
            actor_id: str | None,
            actual_hours: float | None,
        ) -> dict[str, object]:
            db = await init_database()
            try:
                service = TaskService(
                    db,
                    EventStore(db),
                    RevisionStore(db),
                    MetricsCollector(db),
                )
                await service.complete_task(
                    task_id, notes=notes, actual_hours=actual_hours
                )
            finally:
                await db.disconnect()
            return {}

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Delegated Consistency Project"])
        goal_result = cli_runner.invoke(
            cli,
            [
                "goal",
                "create",
                "Delegated Consistency Goal",
                "--project",
                "Delegated Consistency Project",
                "--format",
                "json",
            ],
        )
        assert goal_result.exit_code == 0, goal_result.output
        goal_id = json.loads(goal_result.output)["goal"]["id"]
        objective_result = cli_runner.invoke(
            cli,
            [
                "objective",
                "create",
                "Delegated Consistency Objective",
                "--goal-id",
                goal_id,
                "--format",
                "json",
            ],
        )
        assert objective_result.exit_code == 0, objective_result.output
        task_result = cli_runner.invoke(
            cli,
            [
                "task",
                "add",
                "Delegated Consistency Project",
                "Delegated Consistency Task",
            ],
        )
        task_id = _extract_id(task_result.output)
        plan_result = cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Delegated Consistency Plan",
                "--project",
                "Delegated Consistency Project",
                "--goal-id",
                goal_id,
                "--task-id",
                task_id,
                "--content",
                "{}",
            ],
        )
        assert plan_result.exit_code == 0, plan_result.output
        plan_id = _extract_id(plan_result.output)
        activate_plan = cli_runner.invoke(
            cli,
            [
                "plan",
                "update",
                plan_id,
                "--status",
                "active",
            ],
        )
        assert activate_plan.exit_code == 0, activate_plan.output
        cli_runner.invoke(cli, ["task", "start", task_id, "--by", "tester"])

        monkeypatch.setattr(
            "pms.cli.app._resolve_runtime_write_decision",
            lambda _action_name: RuntimeWriteDecision(
                allowed=True,
                use_server=True,
                payload=RuntimeServerPayload(
                    base_url="http://127.0.0.1:8000",
                    reachable=True,
                    status="healthy",
                    database="healthy",
                    error=None,
                    checked=True,
                    api_key_present=True,
                ),
                block_reason=None,
            ),
        )
        monkeypatch.setattr(
            "pms.cli.app._delegate_task_complete_to_server",
            _fake_delegate_task_complete_to_server,
        )

        result = cli_runner.invoke(
            cli,
            ["task", "complete", task_id, "--by", "tester", "--format", "json"],
        )
        assert result.exit_code == 0, result.output
        completion_payload = json.loads(result.output)
        assert completion_payload["task"]["status"] == "done"

        task_show = cli_runner.invoke(
            cli, ["task", "show", task_id, "--format", "json"]
        )
        project_show = cli_runner.invoke(
            cli,
            ["project", "show", "Delegated Consistency Project", "--format", "json"],
        )
        goal_summary = cli_runner.invoke(
            cli,
            ["goal", "summary", goal_id, "--format", "json"],
        )
        objective_list = cli_runner.invoke(
            cli,
            [
                "objective",
                "list",
                "--goal-id",
                goal_id,
                "--format",
                "json",
            ],
        )
        plan_show = cli_runner.invoke(
            cli, ["plan", "show", plan_id, "--format", "json"]
        )
        dashboard = cli_runner.invoke(cli, ["dashboard", "--format", "json"])

        assert task_show.exit_code == 0, task_show.output
        assert project_show.exit_code == 0, project_show.output
        assert goal_summary.exit_code == 0, goal_summary.output
        assert objective_list.exit_code == 0, objective_list.output
        assert plan_show.exit_code == 0, plan_show.output
        assert dashboard.exit_code == 0, dashboard.output

        task_payload = json.loads(task_show.output)
        project_payload = json.loads(project_show.output)
        goal_payload = json.loads(goal_summary.output)
        objective_payload = json.loads(objective_list.output)
        plan_payload = json.loads(plan_show.output)
        dashboard_payload = json.loads(dashboard.output)
        plan_status = (
            plan_payload.get("plan", {}).get("status")
            if isinstance(plan_payload.get("plan"), dict)
            else plan_payload.get("status")
        )

        assert task_payload["status"] == "done"
        assert task_payload["current_progress_percent"] == 100
        assert plan_status == "completed"
        assert project_payload["stats"]["completed_tasks"] == 1
        assert project_payload["stats"]["completion_percent"] == 100.0
        assert goal_payload["goal"]["status"] == "completed"
        assert goal_payload["goal"]["progress_percent"] == 100
        assert {item["status"] for item in objective_payload["items"]} == {"completed"}
        assert {item["progress_percent"] for item in objective_payload["items"]} == {
            100
        }
        assert dashboard_payload["scope"]["active_visible_projects"] == 0
        assert dashboard_payload["scope"]["recently_completed_projects"] >= 1

    def test_prefer_server_task_complete_tolerates_newly_unblocked_payload_without_next_steps(
        self, cli_runner: CliRunner, temp_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Delegated completion should not crash if server unblocked payload omits next_steps."""
        from pms.config.settings import reload_settings
        from pms.core.events import EventStore
        from pms.core.metrics import MetricsCollector
        from pms.core.revisions import RevisionStore
        from pms.db.connection import init_database
        from pms.services.task_service import TaskService

        reload_settings()

        async def _fake_delegate_task_complete_to_server(
            *,
            task_id: str,
            notes: str | None,
            actor_id: str | None,
            actual_hours: float | None,
        ) -> dict[str, object]:
            db = await init_database()
            try:
                service = TaskService(
                    db,
                    EventStore(db),
                    RevisionStore(db),
                    MetricsCollector(db),
                )
                await service.complete_task(
                    task_id, notes=notes, actual_hours=actual_hours
                )
            finally:
                await db.disconnect()
            return {
                "newly_unblocked": [
                    {
                        "id": "dep-1",
                        "title": "Dependent Task",
                        "status": "todo",
                        "links": {
                            "self": _cli_step("task show dep-1"),
                        },
                    }
                ]
            }

        monkeypatch.setattr(
            "pms.cli.app._resolve_runtime_write_decision",
            lambda _action_name: RuntimeWriteDecision(
                allowed=True,
                use_server=True,
                payload=RuntimeServerPayload(
                    base_url="http://127.0.0.1:8000",
                    reachable=True,
                    status="healthy",
                    database="healthy",
                    error=None,
                    checked=True,
                    api_key_present=True,
                ),
                block_reason=None,
            ),
        )
        monkeypatch.setattr(
            "pms.cli.app._delegate_task_complete_to_server",
            _fake_delegate_task_complete_to_server,
        )

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Delegated Unblock Project"])
        task_result = cli_runner.invoke(
            cli,
            ["task", "add", "Delegated Unblock Project", "Delegated Parent Task"],
        )
        task_id = _extract_id(task_result.output)
        cli_runner.invoke(cli, ["task", "start", task_id, "--by", "tester"])

        result = cli_runner.invoke(
            cli,
            [
                "task",
                "complete",
                task_id,
                "--by",
                "tester",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["task"]["status"] == "done"
        assert payload["newly_unblocked"][0]["title"] == "Dependent Task"
        assert payload["next_steps"][0] == _cli_step("task show dep-1")

    def test_prefer_server_task_complete_text_tolerates_minimal_newly_unblocked_payload(
        self, cli_runner: CliRunner, temp_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Text completion output should handle delegated unblocked items with sparse payloads."""
        from pms.config.settings import reload_settings
        from pms.core.events import EventStore
        from pms.core.metrics import MetricsCollector
        from pms.core.revisions import RevisionStore
        from pms.db.connection import init_database
        from pms.services.task_service import TaskService

        reload_settings()

        async def _fake_delegate_task_complete_to_server(
            *,
            task_id: str,
            notes: str | None,
            actor_id: str | None,
            actual_hours: float | None,
        ) -> dict[str, object]:
            db = await init_database()
            try:
                service = TaskService(
                    db,
                    EventStore(db),
                    RevisionStore(db),
                    MetricsCollector(db),
                )
                await service.complete_task(
                    task_id, notes=notes, actual_hours=actual_hours
                )
            finally:
                await db.disconnect()
            return {
                "newly_unblocked": [
                    {
                        "id": "dep-2",
                        "title": "Text Dependent Task",
                    }
                ]
            }

        monkeypatch.setattr(
            "pms.cli.app._resolve_runtime_write_decision",
            lambda _action_name: RuntimeWriteDecision(
                allowed=True,
                use_server=True,
                payload=RuntimeServerPayload(
                    base_url="http://127.0.0.1:8000",
                    reachable=True,
                    status="healthy",
                    database="healthy",
                    error=None,
                    checked=True,
                    api_key_present=True,
                ),
                block_reason=None,
            ),
        )
        monkeypatch.setattr(
            "pms.cli.app._delegate_task_complete_to_server",
            _fake_delegate_task_complete_to_server,
        )

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Delegated Text Project"])
        task_result = cli_runner.invoke(
            cli,
            ["task", "add", "Delegated Text Project", "Delegated Text Parent Task"],
        )
        task_id = _extract_id(task_result.output)
        cli_runner.invoke(cli, ["task", "start", task_id, "--by", "tester"])

        result = cli_runner.invoke(
            cli,
            [
                "task",
                "complete",
                task_id,
                "--by",
                "tester",
            ],
        )

        assert result.exit_code == 0, result.output
        _assert_plain_output_contains(
            result.output, "Newly unblocked:", "Text Dependent Task"
        )


class TestProjectCommands:
    """Tests for project commands."""

    def test_project_create(self, cli_runner: CliRunner, temp_env: Path):
        """Test creating a project."""
        from pms.config.settings import reload_settings

        reload_settings()

        # Initialize first
        cli_runner.invoke(cli, ["init"])

        # Create project
        result = cli_runner.invoke(
            cli,
            ["project", "create", "Test Project", "-d", "A test project", "-t", "test"],
        )

        assert result.exit_code == 0
        _assert_plain_output_contains(result.output, "Created project", "Test Project")

    def test_project_create_json_output(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Project create should expose machine-readable artifact output."""
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(
            cli,
            ["project", "create", "JSON Project", "--format", "json"],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["project"]["name"] == "JSON Project"
        assert payload["links"]["self"].startswith(_cli_step("project show "))
        assert payload["links"]["task_create"].startswith(_cli_step("task create "))
        assert payload["modeling_tips"]
        assert payload["next_steps"][0].startswith(
            _cli_step('project show "JSON Project"')
        )
        assert payload["runtime_write"]["write_path"] == "direct_file"
        assert payload["runtime_write"]["target_kind"] == "workspace_sqlite"
        assert (
            payload["runtime_write"]["target_location"]
            == payload["runtime_write"]["workspace"]["database_path"]
        )

    def test_prefer_server_project_create_still_reports_direct_file_when_local_only(
        self,
        cli_runner: CliRunner,
        temp_env: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from pms.config.settings import reload_settings

        monkeypatch.setenv("PMS_WRITE_MODE", "prefer_server")
        monkeypatch.setenv("PMS_SERVER_BASE_URL", "http://127.0.0.1:8000")
        reload_settings()
        monkeypatch.setattr(
            "pms.cli.app._runtime_server_payload",
            lambda: RuntimeServerPayload(
                base_url="http://127.0.0.1:8000",
                reachable=True,
                status=200,
                database="sqlite:///tmp/pms.db",
                error=None,
                checked=True,
                api_key_present=True,
            ),
        )
        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(
            cli,
            ["project", "create", "Prefer Server Local Project", "--format", "json"],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["runtime_write"]["write_mode"] == "prefer_server"
        assert payload["runtime_write"]["write_path"] == "direct_file"
        assert payload["runtime_write"]["target_kind"] == "workspace_sqlite"

    def test_project_create_with_tags(self, cli_runner: CliRunner, temp_env: Path):
        """Test creating a project with multiple tags."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(
            cli,
            [
                "project",
                "create",
                "Tagged Project",
                "-t",
                "api",
                "-t",
                "backend",
                "-t",
                "python",
            ],
        )

        assert result.exit_code == 0
        _assert_plain_output_contains(result.output, "Created project")

    def test_task_start_json_includes_runtime_write_context(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Task start JSON should expose the effective write path and workspace target."""
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Runtime Write Project"])
        task_result = cli_runner.invoke(
            cli, ["task", "add", "Runtime Write Project", "Runtime Write Task"]
        )
        task_id = _extract_id(task_result.output)

        result = cli_runner.invoke(
            cli,
            ["task", "start", task_id, "--format", "json"],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["runtime_write"]["write_path"] == "direct_file"
        assert payload["runtime_write"]["target_kind"] == "workspace_sqlite"
        assert isinstance(
            payload["runtime_write"]["workspace"]["managed_state_in_cwd"], bool
        )
        assert payload["runtime_write"]["workspace"]["cwd"]
        assert payload["runtime_write"]["workspace"]["data_dir"]
        assert payload["runtime_write"]["workspace"]["database_path"]
        assert (
            payload["runtime_write"]["target_location"]
            == payload["runtime_write"]["workspace"]["database_path"]
        )

    def test_prefer_server_task_complete_json_includes_runtime_write_context(
        self,
        cli_runner: CliRunner,
        temp_env: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Delegated task completion JSON should expose the server write target."""
        from pms.config.settings import reload_settings

        reload_settings()

        monkeypatch.setattr(
            "pms.cli.app._resolve_runtime_write_decision",
            lambda _action_name: RuntimeWriteDecision(
                allowed=True,
                use_server=True,
                payload=RuntimeServerPayload(
                    base_url="http://127.0.0.1:8000",
                    reachable=True,
                    status=200,
                    database="sqlite:///tmp/pms.db",
                    error=None,
                    checked=True,
                    api_key_present=True,
                ),
                block_reason=None,
            ),
        )

        async def _fake_delegate_task_complete_to_server(
            *,
            task_id: str,
            notes: str | None,
            actor_id: str | None,
            actual_hours: float | None,
        ) -> dict[str, object]:
            from pms.core import EventStore, MetricsCollector, RevisionStore
            from pms.db.connection import init_database
            from pms.services.task_service import TaskService

            db = await init_database()
            try:
                event_store = EventStore(db)
                revision_store = RevisionStore(db)
                metrics = MetricsCollector(db)
                service = TaskService(db, event_store, revision_store, metrics)
                await service.complete_task_with_effects(
                    task_id,
                    actual_hours=actual_hours,
                )
            finally:
                await db.disconnect()
            return {"newly_unblocked": []}

        monkeypatch.setattr(
            "pms.cli.app._delegate_task_complete_to_server",
            _fake_delegate_task_complete_to_server,
        )

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Delegated Runtime Write Project"])
        task_result = cli_runner.invoke(
            cli,
            [
                "task",
                "add",
                "Delegated Runtime Write Project",
                "Delegated Runtime Task",
            ],
        )
        task_id = _extract_id(task_result.output)
        cli_runner.invoke(cli, ["task", "start", task_id, "--by", "tester"])

        result = cli_runner.invoke(
            cli,
            ["task", "complete", task_id, "--by", "tester", "--format", "json"],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["runtime_write"]["write_path"] == "server_delegated"
        assert payload["runtime_write"]["target_kind"] == "server"
        assert payload["runtime_write"]["target_location"] == "http://127.0.0.1:8000"
        assert (
            payload["runtime_write"]["delegated_server_url"] == "http://127.0.0.1:8000"
        )

    def test_prefer_server_task_start_fails_nonzero_when_api_key_invalid(
        self,
        cli_runner: CliRunner,
        temp_env: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        monkeypatch.setattr(
            "pms.cli.app._resolve_runtime_write_decision",
            lambda _action_name: RuntimeWriteDecision(
                allowed=True,
                use_server=True,
                payload=RuntimeServerPayload(
                    base_url="http://127.0.0.1:8000",
                    reachable=True,
                    status=200,
                    database="sqlite:///tmp/pms.db",
                    error=None,
                    checked=True,
                    api_key_present=True,
                ),
                block_reason=None,
            ),
        )

        async def _fake_delegate_task_start_to_server(**_: object) -> dict[str, object]:
            request = httpx.Request("POST", "http://127.0.0.1:8000/api/v1/tasks/start")
            response = httpx.Response(
                401, request=request, json={"detail": "Invalid API key"}
            )
            raise httpx.HTTPStatusError(
                "Invalid API key", request=request, response=response
            )

        monkeypatch.setattr(
            "pms.cli.app._delegate_task_start_to_server",
            _fake_delegate_task_start_to_server,
        )

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Delegated Invalid Auth Project"])
        task_result = cli_runner.invoke(
            cli,
            [
                "task",
                "add",
                "Delegated Invalid Auth Project",
                "Delegated Invalid Auth Task",
            ],
        )
        task_id = _extract_id(task_result.output)

        result = cli_runner.invoke(
            cli,
            ["task", "start", task_id, "--format", "json"],
        )

        assert result.exit_code == 1, result.output

    def test_prefer_server_task_complete_fails_nonzero_when_api_key_invalid(
        self,
        cli_runner: CliRunner,
        temp_env: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(
            cli, ["project", "create", "Delegated Invalid Auth Complete Project"]
        )
        task_result = cli_runner.invoke(
            cli,
            [
                "task",
                "add",
                "Delegated Invalid Auth Complete Project",
                "Delegated Invalid Auth Complete Task",
            ],
        )
        task_id = _extract_id(task_result.output)
        cli_runner.invoke(cli, ["task", "start", task_id, "--by", "tester"])

        monkeypatch.setattr(
            "pms.cli.app._resolve_runtime_write_decision",
            lambda _action_name: RuntimeWriteDecision(
                allowed=True,
                use_server=True,
                payload=RuntimeServerPayload(
                    base_url="http://127.0.0.1:8000",
                    reachable=True,
                    status=200,
                    database="sqlite:///tmp/pms.db",
                    error=None,
                    checked=True,
                    api_key_present=True,
                ),
                block_reason=None,
            ),
        )

        async def _fake_delegate_task_complete_to_server(
            **_: object,
        ) -> dict[str, object]:
            request = httpx.Request(
                "POST", "http://127.0.0.1:8000/api/v1/tasks/complete"
            )
            response = httpx.Response(
                401, request=request, json={"detail": "Invalid API key"}
            )
            raise httpx.HTTPStatusError(
                "Invalid API key", request=request, response=response
            )

        monkeypatch.setattr(
            "pms.cli.app._delegate_task_complete_to_server",
            _fake_delegate_task_complete_to_server,
        )

        result = cli_runner.invoke(
            cli,
            ["task", "complete", task_id, "--by", "tester", "--format", "json"],
        )

        assert result.exit_code == 1, result.output

    def test_prefer_server_task_progress_falls_back_direct_when_api_key_invalid(
        self,
        cli_runner: CliRunner,
        temp_env: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(
            cli, ["project", "create", "Delegated Invalid Auth Progress Project"]
        )
        task_result = cli_runner.invoke(
            cli,
            [
                "task",
                "add",
                "Delegated Invalid Auth Progress Project",
                "Delegated Invalid Auth Progress Task",
            ],
        )
        task_id = _extract_id(task_result.output)

        monkeypatch.setattr(
            "pms.cli.app._resolve_runtime_write_decision",
            lambda _action_name: RuntimeWriteDecision(
                allowed=True,
                use_server=False,
                payload=RuntimeServerPayload(
                    base_url="http://127.0.0.1:8000",
                    reachable=True,
                    status="healthy",
                    database="healthy",
                    error=None,
                    checked=True,
                    api_key_present=True,
                    api_key_authorized=False,
                    auth_error="Invalid API key",
                ),
                block_reason=None,
            ),
        )

        result = cli_runner.invoke(
            cli,
            [
                "task",
                "progress",
                task_id,
                "25",
                "Invalid auth should fail fast",
                "--by",
                "tester",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["task"]["current_progress_percent"] == 25
        assert payload["runtime_write"]["write_path"] == "direct_file"

    def test_project_add_alias(self, cli_runner: CliRunner, temp_env: Path):
        """Test project add alias."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(cli, ["project", "add", "Alias Project"])

        assert result.exit_code == 0
        _assert_plain_output_contains(result.output, "Created project", "Alias Project")

    def test_project_complete(self, cli_runner: CliRunner, temp_env: Path):
        """Test completing a project via CLI."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Complete Project"])

        result = cli_runner.invoke(cli, ["project", "complete", "Complete Project"])

        assert result.exit_code == 0
        _assert_plain_output_contains(result.output, "Completed: Complete Project")

        show_result = cli_runner.invoke(cli, ["project", "show", "Complete Project"])

        assert show_result.exit_code == 0
        _assert_plain_output_contains(show_result.output, "Status: completed")

    def test_project_list_table_includes_refs_and_modeling_hints(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Project list should stay navigable when names are long and surface modeling guidance."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        create_result = cli_runner.invoke(
            cli,
            [
                "project",
                "create",
                "Extremely Long Project Name For Human Table Navigation Audit",
            ],
        )
        project_id = _extract_id(create_result.output)
        short_ref = project_id.split("-", 1)[0]

        result = cli_runner.invoke(cli, ["project", "list"])
        normalized_output = _normalize_cli_output(result.output)

        assert result.exit_code == 0, result.output
        plain_output = _assert_plain_output_contains(
            result.output,
            "Ref",
            short_ref,
            "Modeling Tips:",
            "Every row includes a stable Ref",
            "Use org/portfolio/program/product links",
            "Model execution consistently from the project",
        )
        assert (
            _cli_step('plan create <name> --project "<project>"') in normalized_output
        )
        assert _cli_step("project show <ref>") in normalized_output

    def test_project_list_reports_terminal_reason_when_all_visible_projects_are_terminal(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Terminal Visible Project"])
        task_result = cli_runner.invoke(
            cli, ["task", "add", "Terminal Visible Project", "Done Task"]
        )
        task_id = _extract_id(task_result.output)
        cli_runner.invoke(cli, ["task", "complete", task_id, "--by", "tester"])
        cli_runner.invoke(cli, ["project", "complete", "Terminal Visible Project"])
        cli_runner.invoke(cli, ["project", "create", "Runtime Repro Project 12"])

        result = cli_runner.invoke(cli, ["project", "list", "--format", "json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["scope"]["active_visible_projects"] == 0
        assert (
            payload["terminal_reason"] == "all surfaced projects are already terminal"
        )
        assert (
            "No other visible active work is currently surfaced"
            in payload["completion_context"]["summary"]
        )
        assert payload["next_steps"][0] == _cli_step(
            'project show "Terminal Visible Project" --format json'
        )

    def test_project_list_json_includes_modeling_recipes(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Project List Modeling Audit"])

        result = cli_runner.invoke(cli, ["project", "list", "--format", "json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert "modeling_tips" in payload
        assert "modeling_recipes" in payload
        assert any(
            _cli_step('plan create <name> --project "<project>"') == step
            for step in payload["modeling_recipes"]["execution"]
        )
        assert any(
            _cli_step('goal create <name> --project "<project>"') == step
            for step in payload["modeling_recipes"]["execution"]
        )
        assert any(
            _cli_step(
                'project update <ref> --org "<org>" --portfolio "<portfolio>" --program "<program>" --product "<product>"'
            )
            == step
            for step in payload["modeling_recipes"]["structure"]
        )

    def test_project_list_surfaces_operator_categories_for_history_rows(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Bench Project"])
        cli_runner.invoke(cli, ["project", "complete", "Bench Project"])
        cli_runner.invoke(cli, ["project", "create", "Delivery Project"])
        cli_runner.invoke(cli, ["project", "complete", "Delivery Project"])

        result = cli_runner.invoke(cli, ["project", "list", "--format", "json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        categories = {
            item["name"]: item["operator_category"] for item in payload["items"]
        }
        category_labels = {
            item["name"]: item["operator_category_label"] for item in payload["items"]
        }
        visibility_reasons = {
            item["name"]: item["operator_visibility_reason"]
            for item in payload["items"]
        }
        assert categories["Bench Project"] == "benchmark_artifact"
        assert categories["Delivery Project"] == "project_history"
        assert category_labels["Bench Project"] == "Benchmark Artifact"
        assert category_labels["Delivery Project"] == "Project History"
        assert visibility_reasons["Bench Project"] == "performance proof/reference"
        assert visibility_reasons["Delivery Project"] == "retained historical lookup"
        assert payload["category_counts"]["benchmark_artifact"] == 1
        assert payload["category_counts"]["project_history"] == 1

        text_result = cli_runner.invoke(cli, ["project", "list"])
        assert text_result.exit_code == 0, text_result.output
        _assert_plain_output_contains(
            text_result.output,
            "Benchmark",
            "Benchmark Artifact",
            "Project History",
        )

    def test_project_list_treats_active_filter_fixture_projects_as_history(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Goal Filter Project A"])
        cli_runner.invoke(cli, ["project", "create", "Recent Progress Project"])
        cli_runner.invoke(cli, ["task", "add", "Recent Progress Project", "Live Task"])

        result = cli_runner.invoke(cli, ["project", "list", "--format", "json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        categories = {
            item["name"]: item["operator_category"] for item in payload["items"]
        }
        assert categories["Goal Filter Project A"] == "project_history"
        assert categories["Recent Progress Project"] == "active_work"

    def test_project_list_surfaces_active_work_counts_separately_from_raw_active_status(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Goal Filter Project A"])
        cli_runner.invoke(cli, ["project", "create", "Recent Progress Project"])
        live_task = cli_runner.invoke(
            cli, ["task", "add", "Recent Progress Project", "Recent Progress Task"]
        )
        live_task_id = _extract_id(live_task.output)
        cli_runner.invoke(cli, ["task", "start", live_task_id, "--by", "tester"])

        result = cli_runner.invoke(cli, ["project", "list", "--format", "json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["visible_totals"]["active_projects"] == 2
        assert payload["visible_totals"]["active_work_projects"] == 1
        assert payload["population_totals"]["active_work_projects"] == 1
        assert payload["scope"]["active_visible_projects"] == 2
        assert payload["scope"]["active_work_visible_projects"] == 1

    def test_project_list_reclassifies_stale_recent_progress_fixture_as_history(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Recent Progress Project"])
        task_result = cli_runner.invoke(
            cli, ["task", "add", "Recent Progress Project", "Recent Progress Task"]
        )
        task_id = _extract_id(task_result.output)
        cli_runner.invoke(cli, ["task", "start", task_id, "--by", "tester"])
        _age_project_and_task_timestamps("Recent Progress Project", days=2)

        result = cli_runner.invoke(cli, ["project", "list", "--format", "json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        project = next(
            item
            for item in payload["items"]
            if item["name"] == "Recent Progress Project"
        )
        assert project["operator_category"] == "project_history"
        assert payload["visible_totals"]["active_projects"] == 1
        assert payload["visible_totals"]["active_work_projects"] == 0
        assert payload["scope"]["active_visible_projects"] == 1
        assert payload["scope"]["active_work_visible_projects"] == 0

    def test_project_list_no_actionable_work_uses_truthful_summary_and_next_steps(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Goal Filter Project A"])

        result = cli_runner.invoke(cli, ["project", "list", "--format", "json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["scope"]["active_visible_projects"] == 1
        assert payload["scope"]["active_work_visible_projects"] == 0
        assert (
            "No operator-visible active work is currently surfaced"
            in payload["scope"]["summary"]
        )
        assert (
            payload["terminal_reason"]
            == "no operator-visible active work is currently surfaced"
        )
        assert any(
            step.startswith(_cli_step("project list"))
            and "--include-generated" in step
            and "--format json" in step
            for step in payload["next_steps"]
        )
        assert _cli_step("quickstart --defaults") in payload["next_steps"]
        assert all(
            "Goal Filter Project A" not in step for step in payload["next_steps"]
        )

    def test_project_list_no_actionable_next_steps_preserve_view_filters(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Goal Filter Project A"])

        result = cli_runner.invoke(
            cli, ["project", "list", "--view", "detail", "--format", "json"]
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert (
            "No operator-visible active work is currently surfaced"
            in payload["scope"]["summary"]
        )
        assert "--view detail" in payload["links"]["self"]
        assert any(
            step.startswith(_cli_step("project list"))
            and "--view detail" in step
            and "--include-generated" in step
            and "--format json" in step
            for step in payload["next_steps"]
        )

    def test_project_list_detail_self_link_preserves_linked_history_flags(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Linked Replay Project"])
        task_result = cli_runner.invoke(
            cli, ["task", "add", "Linked Replay Project", "Linked Task"]
        )
        assert task_result.exit_code == 0, task_result.output

        result = cli_runner.invoke(
            cli,
            [
                "project",
                "list",
                "--view",
                "detail",
                "--include-linked-history",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert "--view detail" in payload["links"]["self"]
        assert "--include-linked-history" in payload["links"]["self"]
        assert "--include-linked" in payload["links"]["self"]
        assert "--include-history" in payload["links"]["self"]

    def test_project_list_detail_linked_task_links_are_normalized(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Linked Replay Project"])
        task_result = cli_runner.invoke(
            cli, ["task", "add", "Linked Replay Project", "Linked Task"]
        )
        assert task_result.exit_code == 0, task_result.output
        task_id = _extract_id(task_result.output)

        result = cli_runner.invoke(
            cli,
            [
                "project",
                "list",
                "--view",
                "detail",
                "--include-linked",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        project_payload = next(
            item for item in payload["items"] if item["name"] == "Linked Replay Project"
        )
        linked_task = project_payload["linked"]["tasks"][0]
        assert linked_task["id"] == task_id
        assert linked_task["links"]["self"] == _cli_step(f"task show {task_id}")
        assert linked_task["links"]["timeline"] == _cli_step(f"task timeline {task_id}")
        assert linked_task["links"]["graph"] == _cli_step(f"task graph {task_id}")

    def test_project_list_can_filter_by_operator_category(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Bench Project"])
        cli_runner.invoke(cli, ["project", "complete", "Bench Project"])
        cli_runner.invoke(cli, ["project", "create", "Regular History Project"])
        cli_runner.invoke(cli, ["project", "complete", "Regular History Project"])

        result = cli_runner.invoke(
            cli,
            [
                "project",
                "list",
                "--format",
                "json",
                "--category",
                "benchmark_artifact",
            ],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["scope"]["operator_category_filter"] == "benchmark_artifact"
        assert payload["params"]["operator_category_filter"] == "benchmark_artifact"
        assert [item["name"] for item in payload["items"]] == ["Bench Project"]
        assert payload["items"][0]["operator_category"] == "benchmark_artifact"
        assert payload["completion_context"]["items"][0]["operator_category"] == (
            "benchmark_artifact"
        )

    def test_project_list_category_filter_applies_before_pagination(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        for idx in range(3):
            cli_runner.invoke(cli, ["project", "create", f"Regular History {idx}"])
            cli_runner.invoke(cli, ["project", "complete", f"Regular History {idx}"])
        cli_runner.invoke(cli, ["project", "create", "Bench Project"])
        cli_runner.invoke(cli, ["project", "complete", "Bench Project"])

        result = cli_runner.invoke(
            cli,
            [
                "project",
                "list",
                "--format",
                "json",
                "--category",
                "benchmark_artifact",
                "--limit",
                "1",
            ],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["page"]["total_count"] == 1
        assert [item["name"] for item in payload["items"]] == ["Bench Project"]

    def test_project_list_surfaces_freshest_visible_activity_and_transition(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Older Visible Project"])
        older_task_id = _extract_id(
            cli_runner.invoke(
                cli,
                ["task", "add", "Older Visible Project", "Older Task"],
            ).output
        )
        cli_runner.invoke(
            cli,
            ["task", "start", older_task_id, "--by", "tester", "--format", "json"],
        )
        cli_runner.invoke(cli, ["project", "create", "Fresher Visible Project"])
        fresher_task_id = _extract_id(
            cli_runner.invoke(
                cli,
                ["task", "add", "Fresher Visible Project", "Fresher Task"],
            ).output
        )
        cli_runner.invoke(
            cli,
            ["task", "start", fresher_task_id, "--by", "tester", "--format", "json"],
        )
        cli_runner.invoke(
            cli,
            [
                "task",
                "progress",
                fresher_task_id,
                "25",
                "Freshest visible project activity",
                "--by",
                "tester",
                "--format",
                "json",
            ],
        )

        result = cli_runner.invoke(cli, ["project", "list", "--format", "json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        freshest_activity = max(
            payload["items"],
            key=lambda item: str(item.get("last_activity_at") or ""),
        )
        freshest_transition = max(
            payload["items"],
            key=lambda item: str(item.get("last_transition_at") or ""),
        )
        assert (
            payload["freshest_visible_activity"]["project_id"]
            == freshest_activity["project_id"]
        )
        assert (
            payload["freshest_visible_transition"]["project_id"]
            == freshest_transition["project_id"]
        )
        assert "last_transition_at" in payload["freshest_visible_activity"]
        assert payload["freshest_visible_transition"]["last_transition_at"] is not None

        text_result = cli_runner.invoke(cli, ["project", "list"])
        assert text_result.exit_code == 0, text_result.output
        _assert_plain_output_contains(
            text_result.output,
            "Freshest Visible Activity:",
            "Freshest Visible Transition:",
        )

    def test_project_list_freshest_visible_activity_and_transition_survive_pagination_offset(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Older Offset Project"])
        older_task_id = _extract_id(
            cli_runner.invoke(
                cli,
                ["task", "add", "Older Offset Project", "Older Offset Task"],
            ).output
        )
        cli_runner.invoke(
            cli,
            ["task", "start", older_task_id, "--by", "tester", "--format", "json"],
        )
        cli_runner.invoke(cli, ["project", "create", "Fresher Offset Project"])
        fresher_task_id = _extract_id(
            cli_runner.invoke(
                cli,
                ["task", "add", "Fresher Offset Project", "Fresher Offset Task"],
            ).output
        )
        cli_runner.invoke(
            cli,
            ["task", "start", fresher_task_id, "--by", "tester", "--format", "json"],
        )
        cli_runner.invoke(
            cli,
            [
                "task",
                "progress",
                fresher_task_id,
                "30",
                "Freshest offset project activity",
                "--by",
                "tester",
                "--format",
                "json",
            ],
        )

        result = cli_runner.invoke(
            cli,
            ["project", "list", "--format", "json", "--limit", "1", "--offset", "1"],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert [item["project_name"] for item in payload["items"]] == [
            "Older Offset Project"
        ]
        assert payload["freshest_visible_activity"]["project_name"] == (
            "Fresher Offset Project"
        )
        assert payload["freshest_visible_transition"]["project_name"] == (
            "Fresher Offset Project"
        )
        assert (
            payload["freshest_visible_activity"]["project_id"]
            != payload["items"][0]["project_id"]
        )

    def test_project_list_generated_category_filter_applies_before_pagination(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        for idx in range(3):
            cli_runner.invoke(cli, ["project", "create", f"Regular History {idx}"])
            cli_runner.invoke(cli, ["project", "complete", f"Regular History {idx}"])
        cli_runner.invoke(cli, ["project", "create", "Bench Project"])
        cli_runner.invoke(cli, ["project", "complete", "Bench Project"])

        result = cli_runner.invoke(
            cli,
            [
                "project",
                "list",
                "--format",
                "json",
                "--include-generated",
                "--category",
                "benchmark_artifact",
                "--limit",
                "1",
            ],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["page"]["total_count"] == 1
        assert [item["name"] for item in payload["items"]] == ["Bench Project"]

    def test_project_auto_completes_when_all_tasks_become_terminal(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Auto Complete Project"])
        first_task = cli_runner.invoke(
            cli,
            [
                "task",
                "create",
                "First",
                "--project",
                "Auto Complete Project",
                "--format",
                "json",
            ],
        )
        second_task = cli_runner.invoke(
            cli,
            [
                "task",
                "create",
                "Second",
                "--project",
                "Auto Complete Project",
                "--format",
                "json",
            ],
        )
        first_task_id = json.loads(first_task.output)["task"]["id"]
        second_task_id = json.loads(second_task.output)["task"]["id"]

        cli_runner.invoke(cli, ["task", "complete", first_task_id, "--by", "tester"])
        mid_result = cli_runner.invoke(
            cli, ["project", "show", "Auto Complete Project", "--format", "json"]
        )
        assert mid_result.exit_code == 0, mid_result.output
        mid_payload = json.loads(mid_result.output)
        assert mid_payload["status"] == "active"
        assert mid_payload["stats"]["completion_percent"] == 50.0

        cli_runner.invoke(cli, ["task", "complete", second_task_id, "--by", "tester"])
        final_result = cli_runner.invoke(
            cli, ["project", "show", "Auto Complete Project", "--format", "json"]
        )
        assert final_result.exit_code == 0, final_result.output
        final_payload = json.loads(final_result.output)
        assert final_payload["status"] == "completed"
        assert final_payload["stats"]["completion_percent"] == 100.0

    def test_project_reactivates_when_terminal_execution_is_reopened(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Auto Reopen Project"])
        task_result = cli_runner.invoke(
            cli,
            [
                "task",
                "create",
                "Only Task",
                "--project",
                "Auto Reopen Project",
                "--format",
                "json",
            ],
        )
        task_id = json.loads(task_result.output)["task"]["id"]

        cli_runner.invoke(cli, ["task", "complete", task_id, "--by", "tester"])
        completed_result = cli_runner.invoke(
            cli, ["project", "show", "Auto Reopen Project", "--format", "json"]
        )
        assert completed_result.exit_code == 0, completed_result.output
        assert json.loads(completed_result.output)["status"] == "completed"

        cli_runner.invoke(cli, ["task", "reopen", task_id])
        reopened_result = cli_runner.invoke(
            cli, ["project", "show", "Auto Reopen Project", "--format", "json"]
        )
        assert reopened_result.exit_code == 0, reopened_result.output
        reopened_payload = json.loads(reopened_result.output)
        assert reopened_payload["status"] == "active"
        assert reopened_payload["stats"]["completion_percent"] == 0.0

    def test_goal_and_execution_backed_objectives_auto_complete_from_terminal_tasks(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Auto Goal Complete Project"])
        goal_result = cli_runner.invoke(
            cli,
            [
                "goal",
                "create",
                "Auto Goal Complete Goal",
                "--project",
                "Auto Goal Complete Project",
                "--format",
                "json",
            ],
        )
        assert goal_result.exit_code == 0, goal_result.output
        goal_id = json.loads(goal_result.output)["goal"]["id"]

        for objective_name in ("Execution Objective A", "Execution Objective B"):
            objective_result = cli_runner.invoke(
                cli,
                [
                    "objective",
                    "create",
                    objective_name,
                    "--goal",
                    "Auto Goal Complete Goal",
                    "--format",
                    "json",
                ],
            )
            assert objective_result.exit_code == 0, objective_result.output

        first_task = cli_runner.invoke(
            cli,
            [
                "task",
                "create",
                "First",
                "--project",
                "Auto Goal Complete Project",
                "--format",
                "json",
            ],
        )
        second_task = cli_runner.invoke(
            cli,
            [
                "task",
                "create",
                "Second",
                "--project",
                "Auto Goal Complete Project",
                "--format",
                "json",
            ],
        )
        first_task_id = json.loads(first_task.output)["task"]["id"]
        second_task_id = json.loads(second_task.output)["task"]["id"]

        cli_runner.invoke(cli, ["task", "complete", first_task_id, "--by", "tester"])
        cli_runner.invoke(cli, ["task", "complete", second_task_id, "--by", "tester"])

        goal_summary = cli_runner.invoke(
            cli, ["goal", "summary", goal_id, "--format", "json"]
        )
        assert goal_summary.exit_code == 0, goal_summary.output
        goal_payload = json.loads(goal_summary.output)
        assert goal_payload["goal"]["status"] == "completed"
        assert goal_payload["goal"]["progress_percent"] == 100

        objectives = cli_runner.invoke(
            cli,
            [
                "objective",
                "list",
                "--goal",
                "Auto Goal Complete Goal",
                "--format",
                "json",
            ],
        )
        assert objectives.exit_code == 0, objectives.output
        objective_payload = json.loads(objectives.output)
        assert {item["status"] for item in objective_payload["items"]} == {"completed"}
        assert {item["progress_percent"] for item in objective_payload["items"]} == {
            100
        }

    def test_goal_and_execution_backed_objectives_reopen_when_execution_reopens(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Auto Goal Reopen Project"])
        goal_result = cli_runner.invoke(
            cli,
            [
                "goal",
                "create",
                "Auto Goal Reopen Goal",
                "--project",
                "Auto Goal Reopen Project",
                "--format",
                "json",
            ],
        )
        assert goal_result.exit_code == 0, goal_result.output
        goal_id = json.loads(goal_result.output)["goal"]["id"]

        objective_result = cli_runner.invoke(
            cli,
            [
                "objective",
                "create",
                "Execution Objective",
                "--goal",
                "Auto Goal Reopen Goal",
                "--format",
                "json",
            ],
        )
        assert objective_result.exit_code == 0, objective_result.output

        task_result = cli_runner.invoke(
            cli,
            [
                "task",
                "create",
                "Only Task",
                "--project",
                "Auto Goal Reopen Project",
                "--format",
                "json",
            ],
        )
        assert task_result.exit_code == 0, task_result.output
        task_id = json.loads(task_result.output)["task"]["id"]

        cli_runner.invoke(cli, ["task", "complete", task_id, "--by", "tester"])
        cli_runner.invoke(cli, ["task", "reopen", task_id])
        cli_runner.invoke(
            cli,
            ["task", "progress", task_id, "35", "Reopened work", "--by", "tester"],
        )

        goal_summary = cli_runner.invoke(
            cli, ["goal", "summary", goal_id, "--format", "json"]
        )
        assert goal_summary.exit_code == 0, goal_summary.output
        goal_payload = json.loads(goal_summary.output)
        assert goal_payload["goal"]["status"] == "active"
        assert goal_payload["goal"]["progress_percent"] == 35

        objectives = cli_runner.invoke(
            cli,
            [
                "objective",
                "list",
                "--goal",
                "Auto Goal Reopen Goal",
                "--format",
                "json",
            ],
        )
        assert objectives.exit_code == 0, objectives.output
        objective_payload = json.loads(objectives.output)
        assert {item["status"] for item in objective_payload["items"]} == {"active"}
        assert {item["progress_percent"] for item in objective_payload["items"]} == {35}

    def test_goal_list_suppresses_generated_audit_goals_by_default(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(
            cli,
            [
                "quickstart",
                "--defaults",
                "--org",
                "Audit Org Example",
                "--product",
                "Audit Product Example",
                "--project",
                "Audit Project Example",
                "--task",
                "Audit Task Example",
                "--no-create-plan",
            ],
        )
        cli_runner.invoke(
            cli,
            [
                "goal",
                "create",
                "Audit Goal Example",
                "--project",
                "Audit Project Example",
            ],
        )
        cli_runner.invoke(cli, ["project", "create", "Visible Goal Project"])
        cli_runner.invoke(
            cli,
            [
                "goal",
                "create",
                "Visible Goal Example",
                "--project",
                "Visible Goal Project",
            ],
        )

        result = cli_runner.invoke(cli, ["goal", "list", "--format", "json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        goal_names = [item["name"] for item in payload["items"]]
        assert "Visible Goal Example" in goal_names
        assert "Audit Goal Example" not in goal_names
        assert payload["suppressed_generated_count"] >= 1

        include_generated = cli_runner.invoke(
            cli, ["goal", "list", "--format", "json", "--include-generated"]
        )
        assert include_generated.exit_code == 0, include_generated.output
        include_payload = json.loads(include_generated.output)
        include_names = [item["name"] for item in include_payload["items"]]
        assert "Audit Goal Example" in include_names

    def test_goal_list_fails_nonzero_for_conflicting_scope_filters(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Scope Project"])

        result = cli_runner.invoke(
            cli,
            [
                "goal",
                "list",
                "--format",
                "json",
                "--project",
                "Scope Project",
                "--project-id",
                "proj_conflict",
            ],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert payload["error"] == "Use --project or --project-id, not both"

    def test_goal_list_generated_suppression_applies_before_pagination(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        for idx in range(3):
            cli_runner.invoke(cli, ["project", "create", f"Audit Project {idx} abc123"])
            cli_runner.invoke(
                cli,
                [
                    "goal",
                    "create",
                    f"Audit Goal {idx}",
                    "--project",
                    f"Audit Project {idx} abc123",
                ],
            )
        cli_runner.invoke(cli, ["project", "create", "Visible Goal Project"])
        cli_runner.invoke(
            cli,
            [
                "goal",
                "create",
                "Visible Goal Example",
                "--project",
                "Visible Goal Project",
            ],
        )

        result = cli_runner.invoke(
            cli,
            ["goal", "list", "--format", "json", "--limit", "1"],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["page"]["total_count"] == 1
        assert [item["name"] for item in payload["items"]] == ["Visible Goal Example"]

    def test_project_show_surfaces_modeling_hints_when_unlinked(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Project show should tell operators how to add missing structure and tags."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Unlinked Project"])

        result = cli_runner.invoke(cli, ["project", "show", "Unlinked Project"])
        normalized_output = _normalize_cli_output(result.output)

        assert result.exit_code == 0, result.output
        _assert_plain_output_contains(
            result.output,
            "Modeling Tips:",
            "Modeling Recipes:",
            "Use org/portfolio/program/product links",
        )
        assert (
            _cli_step('plan create <name> --project "<project>"') in normalized_output
        )
        assert (
            _cli_step(
                'work review --scope-type project --scope "<project>" --reviewed-by <user>'
            )
            in normalized_output
        )
        assert _cli_step('project update <ref> --tag "<tag>"') in normalized_output

    def test_project_show_json_includes_modeling_recipes(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Recipe Project"])

        result = cli_runner.invoke(
            cli, ["project", "show", "Recipe Project", "--format", "json"]
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert "modeling_recipes" in payload
        assert payload["operator_category"] == "active_work"
        assert payload["operator_category_label"] == "Active Work"
        assert payload["operator_visibility_reason"] == "current actionable work"
        assert (
            _cli_step('plan create <name> --project "<project>"')
            in payload["modeling_recipes"]["execution"]
        )
        assert (
            _cli_step('goal create <name> --project "<project>"')
            in payload["modeling_recipes"]["execution"]
        )
        assert (
            _cli_step('work daily --scope-type project --scope "<project>"')
            in payload["modeling_recipes"]["review_and_closure"]
        )
        assert (
            _cli_step('goal summary "<goal>"')
            in payload["modeling_recipes"]["review_and_closure"]
        )

    def test_project_show_treats_cancelled_tasks_as_terminal_for_completion(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Project completion should treat cancelled tasks as terminal."""
        from pms.config.settings import reload_settings
        from pms.core.events import EventStore
        from pms.core.metrics import MetricsCollector
        from pms.core.revisions import RevisionStore
        from pms.db.connection import init_database
        from pms.services.task_service import TaskService

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        create = cli_runner.invoke(
            cli,
            ["project", "create", "Terminal Cancelled Project", "--format", "json"],
        )
        assert create.exit_code == 0, create.output
        project_id = json.loads(create.output)["project"]["id"]

        done_task = cli_runner.invoke(
            cli,
            ["task", "add", project_id, "Done Task", "--format", "json"],
        )
        assert done_task.exit_code == 0, done_task.output
        done_task_id = json.loads(done_task.output)["task"]["id"]

        cancelled_task = cli_runner.invoke(
            cli,
            ["task", "add", project_id, "Cancelled Task", "--format", "json"],
        )
        assert cancelled_task.exit_code == 0, cancelled_task.output
        cancelled_task_id = json.loads(cancelled_task.output)["task"]["id"]

        complete = cli_runner.invoke(
            cli, ["task", "complete", done_task_id, "--by", "tester"]
        )
        assert complete.exit_code == 0, complete.output

        async def _cancel_task() -> None:
            db = await init_database()
            try:
                service = TaskService(
                    db,
                    EventStore(db),
                    RevisionStore(db),
                    MetricsCollector(db),
                )
                cancelled = await service.cancel_task(cancelled_task_id, "superseded")
                assert cancelled is not None
            finally:
                await db.disconnect()

        import asyncio

        asyncio.run(_cancel_task())

        project_show = cli_runner.invoke(
            cli,
            ["project", "show", project_id, "--format", "json"],
        )
        assert project_show.exit_code == 0, project_show.output
        payload = json.loads(project_show.output)

        assert payload["stats"]["total_tasks"] == 2
        assert payload["stats"]["completed_tasks"] == 2
        assert payload["stats"]["completion_percent"] == 100


class TestGoalCommands:
    """Tests for goal commands."""

    def test_goal_create_json_output(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Goal create should expose machine-readable artifact output."""
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Goal JSON Project"])

        result = cli_runner.invoke(
            cli,
            [
                "goal",
                "create",
                "JSON Goal",
                "--project",
                "Goal JSON Project",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["goal"]["name"] == "JSON Goal"
        assert payload["links"]["self"].startswith(_cli_step("goal show "))
        assert payload["links"]["summary"].startswith(_cli_step("goal summary "))
        assert payload["next_steps"][0].startswith(_cli_step("goal show "))

    def test_goal_update_and_objective_json_output(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Goal/objective mutation commands should expose machine-readable payloads."""
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Goal Objective JSON Project"])

        goal_create = cli_runner.invoke(
            cli,
            [
                "goal",
                "create",
                "Mutable Goal",
                "--project",
                "Goal Objective JSON Project",
                "--format",
                "json",
            ],
        )
        goal_payload = json.loads(goal_create.output)
        goal_id = goal_payload["goal"]["id"]

        goal_update = cli_runner.invoke(
            cli,
            [
                "goal",
                "update",
                goal_id,
                "--description",
                "Updated goal description",
                "--format",
                "json",
            ],
        )
        assert goal_update.exit_code == 0, goal_update.output
        updated_goal_payload = json.loads(goal_update.output)
        assert updated_goal_payload["goal"]["description"] == "Updated goal description"
        assert updated_goal_payload["links"]["objectives"].startswith(
            _cli_step("objective list --goal ")
        )

        objective_create = cli_runner.invoke(
            cli,
            [
                "objective",
                "create",
                "Mutable Objective",
                "--goal-id",
                goal_id,
                "--format",
                "json",
            ],
        )
        assert objective_create.exit_code == 0, objective_create.output
        objective_payload = json.loads(objective_create.output)
        objective_id = objective_payload["objective"]["id"]
        assert objective_payload["links"]["self"].startswith(
            _cli_step("objective show ")
        )

        objective_update = cli_runner.invoke(
            cli,
            [
                "objective",
                "update",
                objective_id,
                "--goal",
                "Mutable Goal",
                "--description",
                "Updated objective description",
                "--format",
                "json",
            ],
        )
        assert objective_update.exit_code == 0, objective_update.output
        updated_objective_payload = json.loads(objective_update.output)
        assert (
            updated_objective_payload["objective"]["description"]
            == "Updated objective description"
        )
        assert updated_objective_payload["links"]["key_results"].startswith(
            _cli_step("keyresult list --objective ")
        )

    def test_objective_update_invalid_target_date_is_machine_readable_in_json_mode(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(
            cli, ["project", "create", "Objective Update Validation Project"]
        )
        cli_runner.invoke(
            cli,
            [
                "goal",
                "create",
                "Objective Update Goal",
                "--project",
                "Objective Update Validation Project",
            ],
        )
        objective_create = cli_runner.invoke(
            cli,
            [
                "objective",
                "create",
                "Objective To Update",
                "--goal",
                "Objective Update Goal",
            ],
        )
        objective_id = _extract_id(objective_create.output)

        result = cli_runner.invoke(
            cli,
            [
                "objective",
                "update",
                objective_id,
                "--goal",
                "Objective Update Goal",
                "--target-date",
                "not-a-date",
                "--format",
                "json",
            ],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert payload["error"] == "Invalid target date format (use ISO)"

    def test_objective_list_fails_nonzero_for_conflicting_goal_filters(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Objective Scope Project"])
        cli_runner.invoke(
            cli,
            ["goal", "create", "Scope Goal", "--project", "Objective Scope Project"],
        )

        result = cli_runner.invoke(
            cli,
            [
                "objective",
                "list",
                "--format",
                "json",
                "--goal",
                "Scope Goal",
                "--goal-id",
                "goal_conflict",
            ],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert payload["error"] == "Use --goal or --goal-id, not both"

    def test_objective_create_requires_goal_nonzero_in_json_mode(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(
            cli,
            ["objective", "create", "Orphan Objective", "--format", "json"],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert payload["error"] == "Goal is required (--goal or --goal-id)"

    def test_objective_create_invalid_target_date_is_machine_readable_in_json_mode(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Objective Validation Project"])
        cli_runner.invoke(
            cli,
            [
                "goal",
                "create",
                "Validation Goal",
                "--project",
                "Objective Validation Project",
            ],
        )

        result = cli_runner.invoke(
            cli,
            [
                "objective",
                "create",
                "Bad Date Objective",
                "--goal",
                "Validation Goal",
                "--target-date",
                "not-a-date",
                "--format",
                "json",
            ],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert payload["error"] == "Invalid target date format (use ISO)"

    def test_keyresult_list_fails_nonzero_for_conflicting_objective_filters(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "KR Scope Project"])
        cli_runner.invoke(
            cli,
            ["goal", "create", "Scope Goal", "--project", "KR Scope Project"],
        )
        cli_runner.invoke(
            cli,
            ["objective", "create", "Scope Objective", "--goal", "Scope Goal"],
        )

        result = cli_runner.invoke(
            cli,
            [
                "keyresult",
                "list",
                "--format",
                "json",
                "--objective",
                "Scope Objective",
                "--objective-id",
                "objective_conflict",
            ],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert payload["error"] == "Use --objective or --objective-id, not both"

    def test_keyresult_create_requires_objective_nonzero(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(cli, ["keyresult", "create", "Orphan KR"])
        assert result.exit_code != 0
        _assert_plain_output_contains(
            result.output, "Objective is required (--objective or --objective-id)"
        )

    def test_keyresult_create_conflicting_objective_filters_fail_nonzero(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(
            cli,
            [
                "keyresult",
                "create",
                "Conflicted KR",
                "--objective",
                "Objective Name",
                "--objective-id",
                "objective_conflict",
            ],
        )
        assert result.exit_code != 0
        _assert_plain_output_contains(
            result.output, "Use --objective or --objective-id, not both"
        )

    def test_keyresult_update_invalid_progress_fails_nonzero(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "KR Update Validation Project"])
        cli_runner.invoke(
            cli,
            [
                "goal",
                "create",
                "KR Update Goal",
                "--project",
                "KR Update Validation Project",
            ],
        )
        cli_runner.invoke(
            cli,
            ["objective", "create", "KR Update Objective", "--goal", "KR Update Goal"],
        )
        key_result_create = cli_runner.invoke(
            cli,
            [
                "keyresult",
                "create",
                "KR To Update",
                "--objective",
                "KR Update Objective",
                "--goal",
                "KR Update Goal",
            ],
        )
        key_result_id = _extract_id(key_result_create.output)

        result = cli_runner.invoke(
            cli,
            [
                "keyresult",
                "update",
                key_result_id,
                "--objective",
                "KR Update Objective",
                "--goal",
                "KR Update Goal",
                "--progress",
                "101",
            ],
        )
        assert result.exit_code != 0
        _assert_plain_output_contains(result.output, "Progress must be 0-100")


class TestTaskCommandErgonomics:
    """Tests for task CLI ergonomics and continuation behavior."""

    def test_task_progress_uses_env_actor_when_by_omitted(
        self, cli_runner: CliRunner, temp_env: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Task progress should not fail when actor identity is already in env."""
        from pms.config.settings import reload_settings

        reload_settings()
        monkeypatch.setenv("PMS_ACTOR", "loop-agent")

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Progress Project"])
        task_result = cli_runner.invoke(
            cli, ["task", "add", "Progress Project", "Progress Task"]
        )
        task_id = _extract_id(task_result.output)

        result = cli_runner.invoke(
            cli,
            [
                "task",
                "progress",
                task_id,
                "65",
                "Work is underway",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["progress"]["percent"] == 65
        assert payload["progress"]["updated_by"] == "loop-agent"
        assert payload["task"]["current_progress_percent"] == 65
        assert payload["next_steps"][1].endswith("--by loop-agent")


class TestGoalSummaryExecution:
    """Tests for goal-summary execution visibility."""

    def test_goal_summary_json_includes_execution_for_linked_project(
        self, cli_runner: CliRunner, temp_env: Path
    ):
        """Goal summary should expose linked task execution stats."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Goal Exec Project"])
        goal_result = cli_runner.invoke(
            cli,
            [
                "goal",
                "create",
                "Goal Exec Goal",
                "--project",
                "Goal Exec Project",
            ],
        )
        goal_id = _extract_id(goal_result.output)

        task_result = cli_runner.invoke(
            cli,
            ["task", "add", "Goal Exec Project", "Execution Task"],
        )
        task_id = _extract_id(task_result.output)
        criteria_result = cli_runner.invoke(
            cli,
            [
                "task",
                "update",
                task_id,
                "--done-when",
                "Expose active execution focus in goal summary",
                "--done-when",
                "Provide concrete next steps for the active task",
            ],
        )
        assert criteria_result.exit_code == 0
        start_result = cli_runner.invoke(
            cli, ["task", "start", task_id, "--by", "tester"]
        )
        assert start_result.exit_code == 0, start_result.output
        progress_result = cli_runner.invoke(
            cli,
            [
                "task",
                "progress",
                task_id,
                "40",
                "Implementing",
                "--by",
                "tester",
            ],
        )
        assert progress_result.exit_code == 0, progress_result.output
        plan_result = cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Goal Exec Plan",
                "--project",
                "Goal Exec Project",
                "--goal-id",
                goal_id,
                "--task-id",
                task_id,
                "--content",
                "{}",
                "--format",
                "json",
            ],
        )
        assert plan_result.exit_code == 0, plan_result.output

        result = cli_runner.invoke(
            cli,
            ["goal", "summary", goal_id, "--format", "json"],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["execution"]["total_tasks"] == 1
        assert payload["execution"]["completed_tasks"] == 0
        assert payload["execution"]["in_progress_tasks"] == 1
        assert payload["execution"]["blocked_tasks"] == 0
        assert payload["execution"]["average_task_progress"] == 40
        assert payload["execution"]["completion_percent"] == 0
        assert payload["execution"]["readiness_state"] == "execution_in_progress"
        assert payload["execution"]["consistency_status"] == (
            "execution_ahead_of_goal_rollup"
        )
        assert payload["execution"]["population_basis"] == "goal_plan_task_graph"
        assert payload["execution"]["scoped_goal_count"] == 1
        assert payload["execution"]["consistency_reason"] == (
            "linked execution is progressing while goal rollups may still lag"
        )
        assert payload["execution"]["focus_task"]["title"] == "Execution Task"
        assert payload["execution"]["focus_task"]["status"] == "in_progress"
        assert payload["execution"]["focus_task"]["reason"] == (
            "active execution in progress"
        )
        assert payload["execution"]["focus_task"]["completion_criteria_count"] == 2
        assert payload["execution"]["focus_task"]["has_completion_criteria"] is True
        assert payload["next_steps"][0] == _cli_step(
            'task show "Execution Task" --project "Goal Exec Project"'
        )

    def test_goal_summary_json_requires_explicit_links_for_multi_goal_projects(
        self, cli_runner: CliRunner, temp_env: Path
    ):
        """Multi-goal projects should not alias shared project execution into one goal."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Goal Scope CLI Project"])
        goal_one_result = cli_runner.invoke(
            cli,
            [
                "goal",
                "create",
                "Goal Scope One",
                "--project",
                "Goal Scope CLI Project",
            ],
        )
        goal_one_id = _extract_id(goal_one_result.output)
        goal_two_result = cli_runner.invoke(
            cli,
            [
                "goal",
                "create",
                "Goal Scope Two",
                "--project",
                "Goal Scope CLI Project",
            ],
        )
        assert goal_two_result.exit_code == 0, goal_two_result.output

        task_result = cli_runner.invoke(
            cli,
            ["task", "add", "Goal Scope CLI Project", "Shared Execution Task"],
        )
        task_id = _extract_id(task_result.output)
        start_result = cli_runner.invoke(
            cli, ["task", "start", task_id, "--by", "tester"]
        )
        assert start_result.exit_code == 0, start_result.output
        progress_result = cli_runner.invoke(
            cli,
            [
                "task",
                "progress",
                task_id,
                "35",
                "Working",
                "--by",
                "tester",
            ],
        )
        assert progress_result.exit_code == 0, progress_result.output

        result = cli_runner.invoke(
            cli,
            ["goal", "summary", goal_one_id, "--format", "json"],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert (
            payload["execution"]["population_basis"]
            == "goal_scope_requires_explicit_links"
        )
        assert payload["execution"]["scoped_goal_count"] == 2
        assert payload["execution"]["total_tasks"] == 0
        assert payload["execution"]["focus_task"] is None
        assert payload["execution"]["readiness_state"] == "execution_scope_unlinked"
        assert (
            payload["execution"]["consistency_status"]
            == "unlinked_goal_execution_scope"
        )
        assert payload["execution"]["consistency_reason"] == (
            "project has 2 retained goals; link tasks through goal/objective plans to claim execution"
        )

    def test_goal_summary_json_reports_terminal_execution_without_focus(
        self, cli_runner: CliRunner, temp_env: Path
    ):
        """Completed goal execution should not point at a stale done task."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Terminal Goal Project"])
        goal_result = cli_runner.invoke(
            cli,
            ["goal", "create", "Terminal Goal", "--project", "Terminal Goal Project"],
        )
        goal_id = _extract_id(goal_result.output)

        task_result = cli_runner.invoke(
            cli,
            ["task", "add", "Terminal Goal Project", "Done Task"],
        )
        task_id = _extract_id(task_result.output)
        cli_runner.invoke(cli, ["task", "complete", task_id, "--by", "tester"])

        result = cli_runner.invoke(
            cli,
            ["goal", "summary", goal_id, "--format", "json"],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["execution"]["completed_tasks"] == 1
        assert payload["execution"]["completion_percent"] == 100
        assert payload["execution"]["readiness_state"] == "execution_complete"
        assert payload["execution"]["consistency_status"] == "execution_terminal"
        assert payload["execution"]["consistency_reason"] == (
            "all linked execution tasks are already terminal"
        )
        assert payload["execution"]["focus_task"] is None
        assert payload["execution"]["terminal_reason"] == (
            "all execution tasks are already complete"
        )
        assert payload["terminal_reason"] == "all execution tasks are already complete"
        assert "This goal is terminal." in payload["completion_context"]["summary"]
        assert payload["next_steps"][0] == _cli_step(f"goal show {goal_id}")

        text_result = cli_runner.invoke(cli, ["goal", "summary", goal_id])
        assert text_result.exit_code == 0, text_result.output
        _assert_plain_output_contains(text_result.output, "This goal is terminal.")

    def test_goal_show_json_promotes_terminal_reason_and_completion_context(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        project_result = cli_runner.invoke(
            cli, ["project", "create", "Terminal Goal Show Project"]
        )
        assert project_result.exit_code == 0, project_result.output
        project_id = _extract_id(project_result.output)

        goal_result = cli_runner.invoke(
            cli,
            [
                "goal",
                "create",
                "Terminal Goal Show",
                "--project",
                "Terminal Goal Show Project",
                "--format",
                "json",
            ],
        )
        assert goal_result.exit_code == 0, goal_result.output
        goal_id = json.loads(goal_result.output)["goal"]["id"]

        task_result = cli_runner.invoke(
            cli,
            [
                "task",
                "add",
                "Terminal Goal Show Project",
                "Done Task",
                "--format",
                "json",
            ],
        )
        assert task_result.exit_code == 0, task_result.output
        task_id = json.loads(task_result.output)["task"]["id"]
        cli_runner.invoke(cli, ["task", "start", task_id, "--by", "tester"])
        cli_runner.invoke(cli, ["task", "complete", task_id, "--by", "tester"])

        result = cli_runner.invoke(cli, ["goal", "show", goal_id, "--format", "json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["execution"]["completed_tasks"] == 1
        assert payload["execution"]["focus_task"] is None
        assert payload["execution"]["terminal_reason"] == (
            "all execution tasks are already complete"
        )
        assert payload["terminal_reason"] == "all execution tasks are already complete"
        assert "This goal is terminal." in payload["completion_context"]["summary"]
        assert payload["links"]["plans"] == _cli_step(
            f"plan list --goal-id {goal_id} --format json"
        )
        assert payload["links"]["tasks"] == _cli_step(
            f"task list --project {project_id} --format json"
        )
        assert payload["next_steps"][0] == _cli_step(f"goal show {goal_id}")


class TestGraphDiscoverabilitySurfaces:
    """Ensure primary show surfaces expose traversable graph context and links."""

    def test_task_show_json_includes_context_graph_and_plan_links(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        fixture = _setup_graph_discoverability_fixture(cli_runner)

        parent_result = cli_runner.invoke(
            cli,
            [
                "task",
                "show",
                fixture["parent_task_id"],
                "--include-linked",
                "--format",
                "json",
            ],
        )
        assert parent_result.exit_code == 0, parent_result.output
        parent_payload = json.loads(parent_result.output)
        assert parent_payload["context"]["project"]["id"] == fixture["project_id"]
        assert parent_payload["context"]["milestone"]["id"] == fixture["milestone_id"]
        assert parent_payload["context"]["milestone"]["name"] == "Graph Milestone"
        assert parent_payload["context"]["parent"] is None
        assert parent_payload["context"]["subtask_count"] == 1
        assert parent_payload["context"]["dependency_count"] == 1
        assert parent_payload["context"]["dependent_count"] == 0
        assert (
            parent_payload["context"]["subtasks"][0]["id"] == fixture["child_task_id"]
        )
        assert parent_payload["links"]["project"] == _cli_step(
            f"project show {fixture['project_id']} --format json"
        )
        assert parent_payload["links"]["subtasks"] == _cli_step(
            "task tree --project "
            f"{fixture['project_id']} --root-task-id {fixture['parent_task_id']} --format json"
        )
        assert parent_payload["links"]["plans"] == _cli_step(
            f"plan list --task-id {fixture['parent_task_id']} --format json"
        )
        assert parent_payload["linked"]["project"]["id"] == fixture["project_id"]
        assert parent_payload["linked"]["subtasks"][0]["id"] == fixture["child_task_id"]
        assert parent_payload["linked"]["plans"][0]["id"] == fixture["plan_id"]
        assert (
            parent_payload["linked"]["dependencies"][0]["id"]
            == fixture["blocker_task_id"]
        )
        assert parent_payload["linked"]["subtasks"][0]["links"]["self"] == _cli_step(
            f"task show {fixture['child_task_id']}"
        )

        child_result = cli_runner.invoke(
            cli,
            [
                "task",
                "show",
                fixture["child_task_id"],
                "--include-linked",
                "--format",
                "json",
            ],
        )
        assert child_result.exit_code == 0, child_result.output
        child_payload = json.loads(child_result.output)
        assert child_payload["context"]["parent"]["id"] == fixture["parent_task_id"]
        assert child_payload["context"]["milestone"] is None
        assert child_payload["links"]["parent"] == _cli_step(
            f"task show {fixture['parent_task_id']}"
        )
        assert child_payload["linked"]["parent"]["id"] == fixture["parent_task_id"]

    def test_graph_show_surfaces_expose_symmetric_machine_links(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        fixture = _setup_graph_discoverability_fixture(cli_runner)

        project_show = cli_runner.invoke(
            cli,
            [
                "project",
                "show",
                fixture["project_id"],
                "--include-linked",
                "--format",
                "json",
            ],
        )
        assert project_show.exit_code == 0, project_show.output
        project_show_payload = json.loads(project_show.output)
        assert project_show_payload["links"]["goals"] == _cli_step(
            f"goal list --project-id {fixture['project_id']} --format json"
        )
        assert project_show_payload["links"]["plans"] == _cli_step(
            f"plan list --project-id {fixture['project_id']} --format json"
        )
        assert project_show_payload["linked"]["goals"][0]["id"] == fixture["goal_id"]
        assert project_show_payload["linked"]["goals"][0]["links"][
            "project"
        ] == _cli_step(f"project show {fixture['project_id']} --format json")
        assert project_show_payload["linked"]["plans"][0]["id"] == fixture["plan_id"]
        assert project_show_payload["linked"]["plans"][0]["links"]["goal"] == _cli_step(
            f"goal show {fixture['goal_id']}"
        )
        assert project_show_payload["linked"]["plans"][0]["links"][
            "objective"
        ] == _cli_step(f"objective show {fixture['objective_id']}")

        project_summary = cli_runner.invoke(
            cli,
            ["project", "summary", fixture["project_id"], "--format", "json"],
        )
        assert project_summary.exit_code == 0, project_summary.output
        project_summary_payload = json.loads(project_summary.output)
        assert project_summary_payload["links"]["goals"] == _cli_step(
            f"goal list --project-id {fixture['project_id']} --format json"
        )
        assert project_summary_payload["links"]["plans"] == _cli_step(
            f"plan list --project-id {fixture['project_id']} --format json"
        )

        goal_show = cli_runner.invoke(
            cli,
            [
                "goal",
                "show",
                fixture["goal_id"],
                "--include-linked",
                "--format",
                "json",
            ],
        )
        assert goal_show.exit_code == 0, goal_show.output
        goal_show_payload = json.loads(goal_show.output)
        assert goal_show_payload["links"]["summary"] == _cli_step(
            f"goal summary {fixture['goal_id']}"
        )
        assert goal_show_payload["links"]["project"] == _cli_step(
            f"project show {fixture['project_id']} --format json"
        )
        assert goal_show_payload["links"]["objectives"] == _cli_step(
            f"objective list --goal-id {fixture['goal_id']}"
        )
        assert goal_show_payload["linked"]["project"]["id"] == fixture["project_id"]
        assert (
            goal_show_payload["linked"]["objectives"][0]["id"]
            == fixture["objective_id"]
        )
        assert goal_show_payload["linked"]["objectives"][0]["links"][
            "goal"
        ] == _cli_step(f"goal show {fixture['goal_id']}")

        goal_summary = cli_runner.invoke(
            cli,
            ["goal", "summary", fixture["goal_id"], "--format", "json"],
        )
        assert goal_summary.exit_code == 0, goal_summary.output
        goal_summary_payload = json.loads(goal_summary.output)
        assert goal_summary_payload["links"]["goal"] == _cli_step(
            f"goal show {fixture['goal_id']}"
        )
        assert goal_summary_payload["links"]["project"] == _cli_step(
            f"project show {fixture['project_id']} --format json"
        )
        assert goal_summary_payload["links"]["objectives"] == _cli_step(
            f"objective list --goal-id {fixture['goal_id']} --format json"
        )
        assert goal_summary_payload["links"]["plans"] == _cli_step(
            f"plan list --goal-id {fixture['goal_id']} --format json"
        )

        objective_list = cli_runner.invoke(
            cli,
            [
                "objective",
                "list",
                "--goal-id",
                fixture["goal_id"],
                "--format",
                "json",
            ],
        )
        assert objective_list.exit_code == 0, objective_list.output
        objective_list_payload = json.loads(objective_list.output)
        objective_list_item = next(
            item
            for item in objective_list_payload["items"]
            if item["id"] == fixture["objective_id"]
        )
        assert objective_list_item["goal_id"] == fixture["goal_id"]
        assert objective_list_item["project_id"] == fixture["project_id"]
        assert objective_list_item["effective_rollup"]["status"] == "active"
        assert objective_list_item["effective_hierarchy"]["key_result_count"] == 1
        assert objective_list_item["last_activity_at"] is not None
        assert objective_list_item["last_transition_at"] is not None
        assert objective_list_item["terminal_reason"] is None
        assert objective_list_item["links"]["self"] == _cli_step(
            f"objective show {fixture['objective_id']}"
        )
        assert objective_list_item["links"]["key_results"] == _cli_step(
            f"keyresult list --objective-id {fixture['objective_id']} --format json"
        )
        assert objective_list_item["next_steps"][0] == _cli_step(
            f"objective show {fixture['objective_id']}"
        )

        objective_show = cli_runner.invoke(
            cli,
            [
                "objective",
                "show",
                fixture["objective_id"],
                "--include-linked",
                "--format",
                "json",
            ],
        )
        assert objective_show.exit_code == 0, objective_show.output
        objective_show_payload = json.loads(objective_show.output)
        assert objective_show_payload["project_id"] == fixture["project_id"]
        assert objective_show_payload["stats"]["key_result_count"] == 1
        assert objective_show_payload["effective_rollup"]["status"] == "active"
        assert objective_show_payload["effective_hierarchy"]["key_result_count"] == 1
        assert objective_show_payload["last_activity_at"] is not None
        assert objective_show_payload["last_transition_at"] is not None
        assert objective_show_payload["terminal_reason"] is None
        assert objective_show_payload["completion_context"] is None
        assert objective_show_payload["links"]["goal"] == _cli_step(
            f"goal show {fixture['goal_id']}"
        )
        assert objective_show_payload["links"]["goal_summary"] == _cli_step(
            f"goal summary {fixture['goal_id']}"
        )
        assert objective_show_payload["links"]["project"] == _cli_step(
            f"project show {fixture['project_id']} --format json"
        )
        assert objective_show_payload["links"]["key_results"] == _cli_step(
            f"keyresult list --objective-id {fixture['objective_id']} --format json"
        )
        assert objective_show_payload["next_steps"][0] == _cli_step(
            f"objective show {fixture['objective_id']}"
        )
        assert objective_show_payload["linked"]["goal"]["id"] == fixture["goal_id"]
        assert (
            objective_show_payload["linked"]["key_results"][0]["id"]
            == fixture["key_result_id"]
        )
        assert objective_show_payload["linked"]["key_results"][0]["links"][
            "objective"
        ] == _cli_step(f"objective show {fixture['objective_id']}")

        key_result_show = cli_runner.invoke(
            cli,
            [
                "keyresult",
                "show",
                fixture["key_result_id"],
                "--include-linked",
                "--format",
                "json",
            ],
        )
        assert key_result_show.exit_code == 0, key_result_show.output
        key_result_show_payload = json.loads(key_result_show.output)
        assert key_result_show_payload["links"]["objective"] == _cli_step(
            f"objective show {fixture['objective_id']}"
        )
        assert key_result_show_payload["links"]["goal"] == _cli_step(
            f"goal show {fixture['goal_id']}"
        )
        assert key_result_show_payload["links"]["goal_summary"] == _cli_step(
            f"goal summary {fixture['goal_id']}"
        )
        assert key_result_show_payload["links"]["project"] == _cli_step(
            f"project show {fixture['project_id']} --format json"
        )
        assert (
            key_result_show_payload["linked"]["objective"]["id"]
            == fixture["objective_id"]
        )
        assert key_result_show_payload["linked"]["goal"]["id"] == fixture["goal_id"]

        plan_show = cli_runner.invoke(
            cli,
            [
                "plan",
                "show",
                fixture["plan_id"],
                "--include-linked",
                "--format",
                "json",
            ],
        )
        assert plan_show.exit_code == 0, plan_show.output
        plan_show_payload = json.loads(plan_show.output)
        assert plan_show_payload["links"]["project"] == _cli_step(
            f"project show {fixture['project_id']} --format json"
        )
        assert plan_show_payload["links"]["goal"] == _cli_step(
            f"goal show {fixture['goal_id']}"
        )
        assert plan_show_payload["links"]["objective"] == _cli_step(
            f"objective show {fixture['objective_id']}"
        )
        assert plan_show_payload["links"]["lineage"] == _cli_step(
            f"plan lineage --plan-id {fixture['plan_id']} --format json"
        )
        assert {item["id"] for item in plan_show_payload["linked"]["tasks"]} == {
            fixture["parent_task_id"],
            fixture["child_task_id"],
        }

    def test_objective_show_json_surfaces_terminal_lifecycle_context(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Terminal Objective Project"])

        goal_result = cli_runner.invoke(
            cli,
            [
                "goal",
                "create",
                "Terminal Objective Goal",
                "--project",
                "Terminal Objective Project",
                "--format",
                "json",
            ],
        )
        assert goal_result.exit_code == 0, goal_result.output
        goal_id = json.loads(goal_result.output)["goal"]["id"]

        objective_result = cli_runner.invoke(
            cli,
            [
                "objective",
                "create",
                "Terminal Objective",
                "--goal-id",
                goal_id,
                "--format",
                "json",
            ],
        )
        assert objective_result.exit_code == 0, objective_result.output
        objective_id = json.loads(objective_result.output)["objective"]["id"]

        key_result = cli_runner.invoke(
            cli,
            [
                "keyresult",
                "create",
                "Terminal Objective KR",
                "--objective-id",
                objective_id,
            ],
        )
        assert key_result.exit_code == 0, key_result.output
        key_result_id = _extract_id(key_result.output)

        key_result_complete = cli_runner.invoke(
            cli, ["keyresult", "complete", key_result_id]
        )
        assert key_result_complete.exit_code == 0, key_result_complete.output

        objective_show = cli_runner.invoke(
            cli,
            ["objective", "show", objective_id, "--format", "json"],
        )
        assert objective_show.exit_code == 0, objective_show.output
        payload = json.loads(objective_show.output)

        assert payload["status"] == "completed"
        assert payload["effective_rollup"]["status"] == "completed"
        assert payload["effective_hierarchy"]["completed_key_results"] == 1
        assert payload["stats"]["key_result_count"] == 1
        assert (
            payload["terminal_reason"] == "all linked key results are already complete"
        )
        assert payload["completion_context"]["summary"].startswith(
            "This objective is terminal."
        )
        assert payload["completion_context"]["next_steps"][0] == _cli_step(
            f"objective show {objective_id}"
        )
        assert payload["next_steps"][0] == _cli_step(f"objective show {objective_id}")


class TestRelativeTimeTables:
    """Ensure table outputs always include relative time hints."""

    def test_table_outputs_use_relative_times(
        self, cli_runner: CliRunner, temp_env: Path
    ):
        """Table outputs should render timestamps as relative values."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        org_result = cli_runner.invoke(cli, ["org", "create", "Relative Org"])
        org_id = _extract_id(org_result.output)

        team_result = cli_runner.invoke(
            cli, ["team", "create", "Relative Team", "--org-id", org_id]
        )
        _extract_id(team_result.output)

        product_result = cli_runner.invoke(
            cli, ["product", "create", "Relative Product"]
        )
        _extract_id(product_result.output)

        project_result = cli_runner.invoke(
            cli,
            ["project", "create", "Relative Project", "--product", "Relative Product"],
        )
        _extract_id(project_result.output)

        portfolio_result = cli_runner.invoke(
            cli, ["portfolio", "create", "Relative Portfolio", "--org-id", org_id]
        )
        portfolio_id = _extract_id(portfolio_result.output)

        program_result = cli_runner.invoke(
            cli,
            [
                "program",
                "create",
                "Relative Program",
                "--org-id",
                org_id,
                "--portfolio-id",
                portfolio_id,
            ],
        )
        _extract_id(program_result.output)

        category_result = cli_runner.invoke(
            cli, ["label", "category", "create", "Relative Category"]
        )
        category_id = _extract_id(category_result.output)

        label_result = cli_runner.invoke(
            cli, ["label", "create", "Relative Label", "--category-id", category_id]
        )
        _extract_id(label_result.output)

        queue_result = cli_runner.invoke(
            cli, ["queue", "create", "Relative Queue", "--filters", "{}"]
        )
        queue_id = _extract_id(queue_result.output)

        task_result = cli_runner.invoke(
            cli,
            ["task", "add", "Relative Project", "Relative Task"],
        )
        task_id = _extract_id(task_result.output)
        checkout_agent = "agent-1"
        cli_runner.invoke(
            cli,
            ["task", "checkout", task_id, "--agent-id", checkout_agent],
        )
        cli_runner.invoke(
            cli,
            [
                "task",
                "evidence",
                "add",
                task_id,
                "note",
                "evidence-ref",
                "--created-by",
                "tester",
            ],
        )
        create_result = cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Relative Plan",
                "--project",
                "Relative Project",
                "--content",
                "{}",
            ],
        )
        cli_runner.invoke(
            cli,
            ["goal", "create", "Relative Goal", "--project", "Relative Project"],
        )

        outputs = {
            "org list": cli_runner.invoke(cli, ["org", "list"]),
            "team list": cli_runner.invoke(cli, ["team", "list"]),
            "product list": cli_runner.invoke(cli, ["product", "list"]),
            "project list": cli_runner.invoke(cli, ["project", "list"]),
            "portfolio list": cli_runner.invoke(cli, ["portfolio", "list"]),
            "program list": cli_runner.invoke(cli, ["program", "list"]),
            "task list": cli_runner.invoke(
                cli, ["task", "list", "--project", "Relative Project"]
            ),
            "plan list": cli_runner.invoke(
                cli, ["plan", "list", "--project", "Relative Project"]
            ),
            "goal list": cli_runner.invoke(
                cli, ["goal", "list", "--project", "Relative Project"]
            ),
            "label category list": cli_runner.invoke(
                cli, ["label", "category", "list"]
            ),
            "label list": cli_runner.invoke(cli, ["label", "list"]),
            "queue list": cli_runner.invoke(cli, ["queue", "list"]),
            "queue run": cli_runner.invoke(cli, ["queue", "run", queue_id]),
            "task checkout status": cli_runner.invoke(
                cli, ["task", "checkout-status", "--agent-id", checkout_agent]
            ),
            "task checkout log": cli_runner.invoke(
                cli, ["task", "checkout-log", "--task-id", task_id]
            ),
            "task evidence list": cli_runner.invoke(
                cli, ["task", "evidence", "list", task_id]
            ),
            "dashboard": cli_runner.invoke(cli, ["dashboard"]),
        }

        for name, result in outputs.items():
            assert result.exit_code == 0, f"{name} failed: {result.output}"
            try:
                _assert_relative_table_times(result.output)
            except AssertionError as exc:
                raise AssertionError(f"{name}: {exc}") from exc

    def test_project_list_empty(self, cli_runner: CliRunner, temp_env: Path):
        """Test listing projects when none exist."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(cli, ["project", "list"])

        assert result.exit_code == 0
        _assert_plain_output_contains(result.output, "Total: 0")

    def test_project_list_with_projects(self, cli_runner: CliRunner, temp_env: Path):
        """Test listing projects."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Project A"])
        cli_runner.invoke(cli, ["project", "create", "Project B"])

        result = cli_runner.invoke(cli, ["project", "list"])

        assert result.exit_code == 0
        _assert_plain_output_contains(result.output, "Ref", "Total: 2")

    def test_project_list_json(self, cli_runner: CliRunner, temp_env: Path):
        """Test listing projects in JSON format."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "JSON Project"])

        result = cli_runner.invoke(cli, ["project", "list", "-f", "json"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["visible_totals"]["population"] == "visible_operator"
        assert payload["scope"]["population"] == "visible_operator"
        assert payload["items"][0]["name"] == "JSON Project"
        assert "stats" in payload["items"][0]
        assert (
            payload["items"][0]["total_tasks"]
            == payload["items"][0]["stats"]["total_tasks"]
        )
        assert payload["items"][0]["completed_tasks"] == 0
        assert payload["items"][0]["stats"]["completed_milestones"] == 0
        assert (
            payload["items"][0]["completion_percent"]
            == payload["items"][0]["stats"]["completion_percent"]
        )

    def test_project_list_orders_projects_by_bubbled_graph_activity(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Graph Order Older Project"])
        cli_runner.invoke(
            cli,
            ["task", "add", "Graph Order Older Project", "Graph Order Older Task"],
        )

        goal_project_id = json.loads(
            cli_runner.invoke(
                cli,
                ["project", "create", "Graph Order Goal Project", "--format", "json"],
            ).output
        )["project"]["id"]
        goal_id = json.loads(
            cli_runner.invoke(
                cli,
                [
                    "goal",
                    "create",
                    "Graph Order Goal",
                    "--project-id",
                    goal_project_id,
                    "--format",
                    "json",
                ],
            ).output
        )["goal"]["id"]
        objective_id = json.loads(
            cli_runner.invoke(
                cli,
                [
                    "objective",
                    "create",
                    "Graph Order Objective",
                    "--goal-id",
                    goal_id,
                    "--format",
                    "json",
                ],
            ).output
        )["objective"]["id"]
        objective_update = cli_runner.invoke(
            cli,
            [
                "objective",
                "update",
                objective_id,
                "--status",
                "on_hold",
                "--progress",
                "25",
                "--format",
                "json",
            ],
        )
        assert objective_update.exit_code == 0, objective_update.output

        cli_runner.invoke(cli, ["project", "create", "Graph Order Planless Project"])
        planless_task_id = json.loads(
            cli_runner.invoke(
                cli,
                [
                    "task",
                    "add",
                    "Graph Order Planless Project",
                    "Graph Order Planless Task",
                    "--format",
                    "json",
                ],
            ).output
        )["task"]["id"]
        cli_runner.invoke(
            cli,
            ["task", "start", planless_task_id, "--by", "tester", "--format", "json"],
        )
        progress_result = cli_runner.invoke(
            cli,
            [
                "task",
                "progress",
                planless_task_id,
                "60",
                "Graph order freshest activity",
                "--by",
                "tester",
                "--format",
                "json",
            ],
        )
        assert progress_result.exit_code == 0, progress_result.output

        result = cli_runner.invoke(cli, ["project", "list", "--format", "json"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)

        matching = [
            item
            for item in payload["items"]
            if item["name"]
            in {
                "Graph Order Older Project",
                "Graph Order Goal Project",
                "Graph Order Planless Project",
            }
        ]
        assert [item["name"] for item in matching[:3]] == [
            "Graph Order Planless Project",
            "Graph Order Goal Project",
            "Graph Order Older Project",
        ]
        assert matching[0]["last_activity_at"] is not None
        assert matching[0]["last_transition_at"] is not None
        assert matching[1]["last_activity_at"] is not None
        assert matching[1]["last_transition_at"] is not None

    def test_project_show(self, cli_runner: CliRunner, temp_env: Path):
        """Test showing project details."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(
            cli,
            [
                "project",
                "create",
                "Show Project",
                "-d",
                "Detailed project",
                "-t",
                "demo",
            ],
        )

        result = cli_runner.invoke(cli, ["project", "show", "Show Project"])

        assert result.exit_code == 0
        _assert_plain_output_contains(
            result.output, "Show Project", "Detailed project", "demo"
        )

    def test_project_show_not_found(self, cli_runner: CliRunner, temp_env: Path):
        """Test showing non-existent project."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(cli, ["project", "show", "Non-existent"])

        assert result.exit_code == 0
        _assert_plain_output_contains(result.output, "not found")

    def test_project_show_verbose(self, cli_runner: CliRunner, temp_env: Path):
        """Test showing project with verbose stats."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Stats Project"])
        cli_runner.invoke(cli, ["task", "add", "Stats Project", "Task 1"])

        result = cli_runner.invoke(cli, ["project", "show", "Stats Project", "-v"])

        assert result.exit_code == 0
        _assert_plain_output_contains(result.output, "Statistics", "Tasks:")

    def test_project_history(self, cli_runner: CliRunner, temp_env: Path):
        """Test showing project history."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "History Project"])

        result = cli_runner.invoke(cli, ["project", "history", "History Project"])

        assert result.exit_code == 0
        _assert_plain_output_contains(result.output, "History:")


class TestProductCommands:
    """Tests for product commands."""

    def test_product_create_and_list(self, cli_runner: CliRunner, temp_env: Path):
        """Test creating and listing products."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        result = cli_runner.invoke(
            cli,
            ["product", "create", "Test Product", "-d", "Demo product"],
        )

        assert result.exit_code == 0
        _assert_plain_output_contains(result.output, "Created product")

        list_result = cli_runner.invoke(cli, ["product", "list"])
        assert list_result.exit_code == 0
        _assert_plain_output_contains(list_result.output, "Test Product")

    def test_product_show(self, cli_runner: CliRunner, temp_env: Path):
        """Test showing product details."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        create = cli_runner.invoke(
            cli,
            ["product", "create", "Show Product", "-v", "Vision"],
        )
        assert create.exit_code == 0
        product_id = _extract_id(create.output)

        show = cli_runner.invoke(cli, ["product", "show", product_id])
        assert show.exit_code == 0
        assert "Show Product" in show.output
        assert "Vision" in show.output

    def test_product_create_update_json_output(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Product create/update should expose machine-readable artifact payloads."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        create = cli_runner.invoke(
            cli,
            ["product", "create", "JSON Product", "--format", "json"],
        )
        assert create.exit_code == 0, create.output
        create_payload = json.loads(create.output)
        assert create_payload["product"]["name"] == "JSON Product"
        assert create_payload["links"]["self"].startswith(_cli_step("product show "))

        product_id = create_payload["product"]["id"]
        update = cli_runner.invoke(
            cli,
            [
                "product",
                "update",
                product_id,
                "--description",
                "Updated description",
                "--format",
                "json",
            ],
        )
        assert update.exit_code == 0, update.output
        update_payload = json.loads(update.output)
        assert update_payload["product"]["description"] == "Updated description"
        assert update_payload["links"]["summary"].startswith(
            _cli_step("product summary ")
        )


class TestOrgPortfolioCommands:
    """Tests for org/team/portfolio/program commands."""

    def test_org_create_json_output(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Organization create should expose machine-readable artifact payloads."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        result = cli_runner.invoke(
            cli,
            ["org", "create", "JSON Org", "--format", "json"],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["organization"]["name"] == "JSON Org"
        assert payload["links"]["self"].startswith(_cli_step("org show "))

    def test_team_create_update_json_output(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Team create/update should expose machine-readable artifact payloads."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        org_result = cli_runner.invoke(cli, ["org", "create", "Team JSON Org"])
        org_id = _extract_id(org_result.output)

        create = cli_runner.invoke(
            cli,
            [
                "team",
                "create",
                "JSON Team",
                "--org-id",
                org_id,
                "--format",
                "json",
            ],
        )
        assert create.exit_code == 0, create.output
        create_payload = json.loads(create.output)
        assert create_payload["team"]["name"] == "JSON Team"
        assert create_payload["links"]["self"].startswith(_cli_step("team show "))

        team_id = create_payload["team"]["id"]
        update = cli_runner.invoke(
            cli,
            [
                "team",
                "update",
                team_id,
                "--owner",
                "owner@example.com",
                "--format",
                "json",
            ],
        )
        assert update.exit_code == 0, update.output

    def test_portfolio_program_create_update_json_output(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Portfolio/program mutation commands should expose machine-readable payloads."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        org_create = cli_runner.invoke(cli, ["org", "create", "Portfolio JSON Org"])
        org_id = _extract_id(org_create.output)

        portfolio_create = cli_runner.invoke(
            cli,
            [
                "portfolio",
                "create",
                "JSON Portfolio",
                "--org-id",
                org_id,
                "--format",
                "json",
            ],
        )
        assert portfolio_create.exit_code == 0, portfolio_create.output
        portfolio_payload = json.loads(portfolio_create.output)
        assert portfolio_payload["portfolio"]["name"] == "JSON Portfolio"
        portfolio_id = portfolio_payload["portfolio"]["id"]
        assert portfolio_payload["links"]["self"].startswith(
            _cli_step("portfolio show ")
        )

        portfolio_update = cli_runner.invoke(
            cli,
            [
                "portfolio",
                "update",
                portfolio_id,
                "--owner",
                "owner@example.com",
                "--format",
                "json",
            ],
        )
        assert portfolio_update.exit_code == 0, portfolio_update.output
        updated_portfolio_payload = json.loads(portfolio_update.output)
        assert updated_portfolio_payload["portfolio"]["owner"] == "owner@example.com"
        assert updated_portfolio_payload["links"]["programs"].startswith(
            _cli_step("program list --portfolio ")
        )

        program_create = cli_runner.invoke(
            cli,
            [
                "program",
                "create",
                "JSON Program",
                "--org-id",
                org_id,
                "--portfolio-id",
                portfolio_id,
                "--format",
                "json",
            ],
        )
        assert program_create.exit_code == 0, program_create.output
        program_payload = json.loads(program_create.output)
        assert program_payload["program"]["name"] == "JSON Program"
        program_id = program_payload["program"]["id"]
        assert program_payload["links"]["self"].startswith(_cli_step("program show "))

        program_update = cli_runner.invoke(
            cli,
            [
                "program",
                "update",
                program_id,
                "--owner",
                "owner@example.com",
                "--format",
                "json",
            ],
        )
        assert program_update.exit_code == 0, program_update.output
        updated_program_payload = json.loads(program_update.output)
        assert updated_program_payload["program"]["owner"] == "owner@example.com"
        assert updated_program_payload["links"]["summary"].startswith(
            _cli_step("program summary ")
        )

    def test_org_team_portfolio_program_flow(
        self, cli_runner: CliRunner, temp_env: Path
    ):
        """Test org/team/portfolio/program create and list flow."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])

        org_create = cli_runner.invoke(
            cli,
            [
                "org",
                "create",
                "Acme Org",
                "--owner",
                "owner@example.com",
                "--member",
                "owner@example.com",
            ],
        )
        assert org_create.exit_code == 0
        org_id = _extract_id(org_create.output)

        team_create = cli_runner.invoke(
            cli,
            ["team", "create", "Core Team", "--org-id", org_id],
        )
        assert team_create.exit_code == 0
        team_id = _extract_id(team_create.output)

        portfolio_create = cli_runner.invoke(
            cli,
            ["portfolio", "create", "Core Portfolio", "--org-id", org_id],
        )
        assert portfolio_create.exit_code == 0
        portfolio_id = _extract_id(portfolio_create.output)

        program_create = cli_runner.invoke(
            cli,
            [
                "program",
                "create",
                "Core Program",
                "--org-id",
                org_id,
                "--portfolio-id",
                portfolio_id,
            ],
        )
        assert program_create.exit_code == 0
        program_id = _extract_id(program_create.output)

        org_list = cli_runner.invoke(cli, ["org", "list"])
        assert org_list.exit_code == 0
        assert "Acme Org" in org_list.output

        team_list = cli_runner.invoke(cli, ["team", "list", "--org-id", org_id])
        assert team_list.exit_code == 0
        assert "Core Team" in team_list.output

        portfolio_list = cli_runner.invoke(
            cli, ["portfolio", "list", "--org-id", org_id]
        )
        assert portfolio_list.exit_code == 0
        assert "Core Portfolio" in portfolio_list.output

        program_list = cli_runner.invoke(
            cli,
            ["program", "list", "--portfolio-id", portfolio_id, "--format", "json"],
        )
        assert program_list.exit_code == 0
        assert "Core Program" in program_list.output

        cli_runner.invoke(cli, ["team", "update", team_id, "--status", "archived"])
        cli_runner.invoke(
            cli, ["portfolio", "update", portfolio_id, "--status", "archived"]
        )
        cli_runner.invoke(
            cli, ["program", "update", program_id, "--status", "archived"]
        )

        team_completed_scope = cli_runner.invoke(
            cli,
            [
                "team",
                "list",
                "--org-id",
                org_id,
                "--status",
                "archived",
                "--format",
                "json",
            ],
        )
        assert team_completed_scope.exit_code == 0, team_completed_scope.output
        team_payload = json.loads(team_completed_scope.output)
        assert {item["status"] for item in team_payload["items"]} == {"archived"}
        assert {item["org_id"] for item in team_payload["items"]} == {org_id}
        assert team_id in {item["id"] for item in team_payload["items"]}

        portfolio_completed_scope = cli_runner.invoke(
            cli,
            [
                "portfolio",
                "list",
                "--org-id",
                org_id,
                "--status",
                "archived",
                "--format",
                "json",
            ],
        )
        assert portfolio_completed_scope.exit_code == 0, (
            portfolio_completed_scope.output
        )
        portfolio_payload = json.loads(portfolio_completed_scope.output)
        assert {item["status"] for item in portfolio_payload["items"]} == {"archived"}
        assert {item["org_id"] for item in portfolio_payload["items"]} == {org_id}
        assert portfolio_id in {item["id"] for item in portfolio_payload["items"]}

        program_completed_scope = cli_runner.invoke(
            cli,
            [
                "program",
                "list",
                "--portfolio-id",
                portfolio_id,
                "--status",
                "archived",
                "--format",
                "json",
            ],
        )
        assert program_completed_scope.exit_code == 0, program_completed_scope.output
        program_payload = json.loads(program_completed_scope.output)
        assert {item["status"] for item in program_payload["items"]} == {"archived"}
        assert {item["portfolio_id"] for item in program_payload["items"]} == {
            portfolio_id
        }
        assert program_id in {item["id"] for item in program_payload["items"]}

        org_show = cli_runner.invoke(cli, ["org", "show", org_id])
        assert org_show.exit_code == 0
        assert "Acme Org" in org_show.output

        team_show = cli_runner.invoke(cli, ["team", "show", team_id])
        assert team_show.exit_code == 0
        assert "Core Team" in team_show.output

        portfolio_summary = cli_runner.invoke(
            cli, ["portfolio", "summary", portfolio_id]
        )
        assert portfolio_summary.exit_code == 0
        assert "Projects:" in portfolio_summary.output

        program_summary = cli_runner.invoke(cli, ["program", "summary", program_id])
        assert program_summary.exit_code == 0
        assert "Projects:" in program_summary.output


class TestTaskCheckoutCommands:
    """Tests for task checkout/progress commands."""

    def test_task_checkout_and_release(self, cli_runner: CliRunner, temp_env: Path):
        """Test checkout and release via CLI."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Checkout Project"])
        task_result = cli_runner.invoke(
            cli,
            ["task", "add", "Checkout Project", "Checkout Task"],
        )
        assert task_result.exit_code == 0

        task_id = _extract_id(task_result.output)
        checkout = cli_runner.invoke(
            cli,
            ["task", "checkout", task_id, "--agent-id", "tester"],
        )
        assert checkout.exit_code == 0
        assert "Checked out" in checkout.output
        assert "Checkout actor" in checkout.output

        show_result = cli_runner.invoke(
            cli,
            ["task", "show", task_id, "--format", "json"],
        )
        assert show_result.exit_code == 0, show_result.output
        show_payload = json.loads(show_result.output)
        assert show_payload["checkout"]["agent_session_id"] == "tester"
        assert show_payload["checkout"]["actor"]["id"]
        assert show_payload["checkout"]["actor"]["actor"]["kind"] == "runtime_agent"
        assert show_payload["checkout"]["actor"]["actor"]["handle"] == "tester"

        release = cli_runner.invoke(
            cli,
            ["task", "release", task_id, "--agent-id", "tester"],
        )
        assert release.exit_code == 0
        assert "Released checkout" in release.output

    def test_task_timeline_formats(self, cli_runner: CliRunner, temp_env: Path):
        """Test task timeline in json/csv formats."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Timeline Project"])
        task_result = cli_runner.invoke(
            cli,
            ["task", "add", "Timeline Project", "Timeline Task"],
        )
        task_id = _extract_id(task_result.output)

        cli_runner.invoke(
            cli,
            ["task", "progress", task_id, "25", "Started", "--by", "tester"],
        )

        json_out = cli_runner.invoke(
            cli,
            ["task", "timeline", task_id, "--format", "json"],
        )
        assert json_out.exit_code == 0
        payload = json.loads(json_out.output)
        assert payload["task_title"] == "Timeline Task"
        assert payload["project_name"] == "Timeline Project"

        csv_out = cli_runner.invoke(
            cli,
            ["task", "timeline", task_id, "--format", "csv"],
        )
        assert csv_out.exit_code == 0
        assert (
            "task_id,percent_complete,status_message" in csv_out.output.splitlines()[0]
        )

        by_title = cli_runner.invoke(
            cli,
            [
                "task",
                "timeline",
                "Timeline Task",
                "--project",
                "Timeline Project",
                "--format",
                "json",
            ],
        )
        assert by_title.exit_code == 0
        by_title_payload = json.loads(by_title.output)
        assert by_title_payload["task_title"] == "Timeline Task"
        assert by_title_payload["project_name"] == "Timeline Project"

        text_out = cli_runner.invoke(
            cli,
            ["task", "timeline", "Timeline Task", "--project", "Timeline Project"],
        )
        assert text_out.exit_code == 0
        assert "Timeline Task" in text_out.output

    def test_task_timeline_reconciles_terminal_progress_when_no_updates_exist(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Terminal Timeline Project"])
        task_result = cli_runner.invoke(
            cli,
            ["task", "add", "Terminal Timeline Project", "Terminal Timeline Task"],
        )
        task_id = _extract_id(task_result.output)

        complete_result = cli_runner.invoke(
            cli,
            [
                "task",
                "complete",
                task_id,
                "--project",
                "Terminal Timeline Project",
                "--by",
                "tester",
            ],
        )
        assert complete_result.exit_code == 0, complete_result.output

        json_out = cli_runner.invoke(
            cli,
            [
                "task",
                "timeline",
                task_id,
                "--project",
                "Terminal Timeline Project",
                "--format",
                "json",
            ],
        )
        assert json_out.exit_code == 0, json_out.output
        payload = json.loads(json_out.output)
        assert payload["current_percent"] == 100
        assert payload["updates"]
        assert payload["updates"][0]["percent_complete"] == 100
        assert payload["updates"][0]["status_message"] == "Completed"

        text_out = cli_runner.invoke(
            cli,
            ["task", "timeline", task_id, "--project", "Terminal Timeline Project"],
        )
        assert text_out.exit_code == 0, text_out.output
        _assert_plain_output_contains(text_out.output, "Progress: 100% | Updates: 1")

    def test_task_list_and_blocked_formats(self, cli_runner: CliRunner, temp_env: Path):
        """Test task list and blocked outputs in json/csv formats."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Format Project"])
        task_result = cli_runner.invoke(
            cli, ["task", "add", "Format Project", "Blocked Task"]
        )
        task_id = _extract_id(task_result.output)
        cli_runner.invoke(
            cli, ["task", "block", task_id, "--reason", "waiting on dependency"]
        )

        blocked = cli_runner.invoke(
            cli,
            ["task", "blocked", "--project", "Format Project", "--format", "json"],
        )
        assert blocked.exit_code == 0
        payload = json.loads(blocked.output)
        assert payload["items"]
        assert "links" in payload["items"][0]
        assert payload["items"][0]["links"]["guide"] == _cli_step("start --format json")
        assert "next_steps" in payload["items"][0]
        assert payload["items"][0]["next_steps"]
        assert payload["items"][0]["blocked_summary"] == "No dependency detail recorded"

        blocked_csv = cli_runner.invoke(
            cli,
            ["task", "blocked", "--project", "Format Project", "--format", "csv"],
        )
        assert blocked_csv.exit_code == 0
        assert "id,title,project_id" in blocked_csv.output.splitlines()[0]

        list_json = cli_runner.invoke(
            cli,
            ["task", "list", "--project", "Format Project", "--format", "json"],
        )
        assert list_json.exit_code == 0
        payload = json.loads(list_json.output)
        assert "items" in payload
        assert "page" in payload
        assert "links" in payload
        assert payload["links"]["guide"] == _cli_step("start --format json")
        assert "next_steps" in payload
        assert "params" in payload

        list_text = cli_runner.invoke(
            cli,
            ["task", "list", "--project", "Format Project"],
        )
        assert list_text.exit_code == 0
        assert "Task Review" in list_text.output
        assert "Blocked" in list_text.output
        assert "(20" not in list_text.output

        list_csv = cli_runner.invoke(
            cli,
            ["task", "list", "--project", "Format Project", "--format", "csv"],
        )
        assert list_csv.exit_code == 0
        assert "id,title,status,priority" in list_csv.output.splitlines()[0]

    def test_task_blocked_json_includes_blocker_details(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Blocked Detail Project"])
        blocker_result = cli_runner.invoke(
            cli, ["task", "add", "Blocked Detail Project", "Blocked Root"]
        )
        blocker_id = _extract_id(blocker_result.output)
        blocked_result = cli_runner.invoke(
            cli, ["task", "add", "Blocked Detail Project", "Blocked Leaf"]
        )
        blocked_id = _extract_id(blocked_result.output)
        cli_runner.invoke(cli, ["task", "dep", "add", blocked_id, blocker_id])

        result = cli_runner.invoke(
            cli,
            [
                "task",
                "blocked",
                "--project",
                "Blocked Detail Project",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["scope"]["population"] == "scoped_project"
        assert payload["items"][0]["title"] == "Blocked Leaf"
        assert payload["items"][0]["blocked_by_details"][0]["title"] == "Blocked Root"
        assert payload["items"][0]["next_steps"][0] == _cli_step(
            'task show "Blocked Leaf" --project "Blocked Detail Project"'
        )

    def test_task_blocked_json_prefers_draft_plan_lock_summary_when_dependency_is_done(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Blocked Lock Project"])
        blocker_result = cli_runner.invoke(
            cli, ["task", "add", "Blocked Lock Project", "Blocked Root"]
        )
        blocker_id = _extract_id(blocker_result.output)
        blocked_result = cli_runner.invoke(
            cli, ["task", "add", "Blocked Lock Project", "Blocked Leaf"]
        )
        blocked_id = _extract_id(blocked_result.output)
        cli_runner.invoke(cli, ["task", "dep", "add", blocked_id, blocker_id])
        create_result = cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Draft Locked Dependent Plan",
                "--project",
                "Blocked Lock Project",
                "--task-id",
                blocked_id,
                "--content",
                "{}",
            ],
        )
        cli_runner.invoke(cli, ["task", "complete", blocker_id])

        result = cli_runner.invoke(
            cli,
            [
                "task",
                "blocked",
                "--project",
                "Blocked Lock Project",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["scope"]["population"] == "scoped_project"
        assert payload["items"][0]["title"] == "Blocked Leaf"
        assert payload["items"][0]["blocked_by"] == []
        assert payload["items"][0]["blocked_by_details"] == []
        assert payload["items"][0]["resolved_blocked_by_details"][0]["status"] == "done"
        assert payload["items"][0]["execution_lock_plans"] == [
            "Draft Locked Dependent Plan"
        ]
        assert (
            payload["items"][0]["blocked_summary"]
            == "Draft plan lock: Draft Locked Dependent Plan"
        )
        assert payload["items"][0]["next_steps"][0] == _cli_step(
            'task show "Blocked Leaf" --project "Blocked Lock Project"'
        )
        assert all(
            "Close whole-system hardening plan only after original roadmap themes are re-verified"
            not in step
            for step in payload["items"][0]["next_steps"]
        )

    def test_task_available_json_continuation_fields(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Task available JSON items should include continuation hints."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Available Project"])
        cli_runner.invoke(cli, ["task", "add", "Available Project", "Available Task"])

        result = cli_runner.invoke(
            cli,
            ["task", "available", "--project", "Available Project", "--format", "json"],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload
        first = payload[0]
        assert "links" in first
        assert first["links"]["guide"] == _cli_step("start --format json")
        assert first["links"]["available"].startswith(
            _cli_step("task available --format json")
        )
        assert "next_steps" in first
        assert first["next_steps"]

    def test_task_list_detail_json_without_history(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Detail JSON listing should work even when history is not requested."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Detail Project"])
        cli_runner.invoke(cli, ["task", "add", "Detail Project", "Detail Task"])

        result = cli_runner.invoke(
            cli,
            [
                "task",
                "list",
                "--project",
                "Detail Project",
                "--format",
                "json",
                "--view",
                "detail",
            ],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["items"]
        assert payload["items"][0]["title"] == "Detail Task"

    def test_task_show_and_graph_formats(self, cli_runner: CliRunner, temp_env: Path):
        """Test task show and graph outputs in json/csv formats."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Graph Project"])
        task_result = cli_runner.invoke(
            cli,
            ["task", "add", "Graph Project", "Graph Task"],
        )
        task_id = _extract_id(task_result.output)

        show_json = cli_runner.invoke(
            cli,
            ["task", "show", task_id, "--format", "json"],
        )
        assert show_json.exit_code == 0
        assert show_json.output.strip().startswith("{")

        show_csv = cli_runner.invoke(
            cli,
            ["task", "show", task_id, "--format", "csv"],
        )
        assert show_csv.exit_code == 0
        assert "id,title,status" in show_csv.output.splitlines()[0]

        graph_json = cli_runner.invoke(
            cli,
            ["task", "graph", task_id, "--format", "json"],
        )
        assert graph_json.exit_code == 0
        graph_payload = json.loads(graph_json.output)
        assert graph_payload["task_title"] == "Graph Task"
        assert graph_payload["project_name"] == "Graph Project"

        graph_csv = cli_runner.invoke(
            cli,
            ["task", "graph", task_id, "--format", "csv"],
        )
        assert graph_csv.exit_code == 0
        assert "task_id,direction,dependency_id" in graph_csv.output.splitlines()[0]

        show_by_title = cli_runner.invoke(
            cli,
            [
                "task",
                "show",
                "Graph Task",
                "--project",
                "Graph Project",
                "--format",
                "json",
            ],
        )
        assert show_by_title.exit_code == 0
        assert show_by_title.output.strip().startswith("{")

        graph_by_title = cli_runner.invoke(
            cli,
            [
                "task",
                "graph",
                "Graph Task",
                "--project",
                "Graph Project",
                "--format",
                "json",
            ],
        )
        assert graph_by_title.exit_code == 0
        graph_by_title_payload = json.loads(graph_by_title.output)
        assert graph_by_title_payload["task_title"] == "Graph Task"
        assert graph_by_title_payload["project_name"] == "Graph Project"

        graph_text = cli_runner.invoke(
            cli,
            ["task", "graph", "Graph Task", "--project", "Graph Project"],
        )
        assert graph_text.exit_code == 0
        assert "Graph Task" in graph_text.output

    def test_task_show_trace_includes_history(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Test task show trace includes history and linked data."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Trace Project"])
        parent_result = cli_runner.invoke(
            cli, ["task", "add", "Trace Project", "Trace Parent"]
        )
        parent_id = _extract_id(parent_result.output)
        child_result = cli_runner.invoke(
            cli, ["task", "add", "Trace Project", "Trace Child"]
        )
        child_id = _extract_id(child_result.output)

        cli_runner.invoke(cli, ["task", "dep", "add", child_id, parent_id])
        cli_runner.invoke(
            cli,
            [
                "task",
                "progress",
                parent_id,
                "25",
                "Started",
                "--by",
                "tester",
            ],
        )
        cli_runner.invoke(
            cli,
            [
                "task",
                "evidence",
                "add",
                parent_id,
                "note",
                "trace",
                "--description",
                "Trace evidence",
            ],
        )

        result = cli_runner.invoke(
            cli,
            [
                "task",
                "show",
                parent_id,
                "--view",
                "trace",
                "--include-linked-history",
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert "history" in payload
        assert "linked" in payload
        assert payload["history"]["progress_updates"]

    def test_task_ready_with_workflow(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Ensure task ready works with workflow-assigned tasks."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Ready Project"])
        task_result = cli_runner.invoke(
            cli,
            ["task", "add", "Ready Project", "Ready Task"],
        )
        task_id = _extract_id(task_result.output)

        assign = cli_runner.invoke(
            cli,
            ["workflow", "assign", task_id, "sdlc", "concept"],
        )
        assert assign.exit_code == 0

        ready = cli_runner.invoke(
            cli,
            ["task", "ready", "--project", "Ready Project"],
        )
        assert ready.exit_code == 0
        assert "Ready Tasks" in ready.output or "No ready tasks." in ready.output

    def test_task_ready_json_history_and_linked(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Ensure task ready supports history and linked JSON payloads."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Ready JSON Project"])
        cli_runner.invoke(cli, ["task", "add", "Ready JSON Project", "Ready JSON Task"])

        ready = cli_runner.invoke(
            cli,
            [
                "task",
                "ready",
                "--project",
                "Ready JSON Project",
                "--format",
                "json",
                "--include-history",
                "--include-linked",
            ],
        )
        assert ready.exit_code == 0
        payload = json.loads(ready.output)
        assert payload["scope"]["population"] == "scoped_project"
        assert payload["items"]
        assert "history" in payload["items"][0]
        assert "linked" in payload["items"][0]
        assert "links" in payload["items"][0]
        assert payload["items"][0]["links"]["guide"] == _cli_step("start --format json")
        assert "next_steps" in payload["items"][0]
        assert payload["items"][0]["next_steps"]

    def test_task_stale_json_links_and_next_steps(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Ensure task stale JSON output exposes continuation metadata."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Stale JSON Project"])
        cli_runner.invoke(cli, ["task", "add", "Stale JSON Project", "Stale JSON Task"])

        stale = cli_runner.invoke(
            cli,
            [
                "task",
                "stale",
                "--project",
                "Stale JSON Project",
                "--days",
                "0",
                "--format",
                "json",
            ],
        )
        assert stale.exit_code == 0
        payload = json.loads(stale.output)
        assert payload["scope"]["population"] == "scoped_project"
        assert payload["items"]
        assert "links" in payload["items"][0]
        assert payload["items"][0]["links"]["guide"] == _cli_step("start --format json")
        assert payload["items"][0]["links"]["stale"].startswith(
            _cli_step("task stale --format json")
        )
        assert "next_steps" in payload["items"][0]
        assert payload["items"][0]["next_steps"]

    def test_task_duplicates_json_links_and_next_steps(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Ensure task duplicates JSON output exposes merge continuation metadata."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Duplicate JSON Project"])
        cli_runner.invoke(
            cli, ["task", "add", "Duplicate JSON Project", "Duplicate JSON Task"]
        )
        cli_runner.invoke(
            cli, ["task", "add", "Duplicate JSON Project", "Duplicate JSON Task"]
        )

        duplicates = cli_runner.invoke(
            cli,
            [
                "task",
                "duplicates",
                "--project",
                "Duplicate JSON Project",
                "--format",
                "json",
            ],
        )
        assert duplicates.exit_code == 0
        payload = json.loads(duplicates.output)
        assert payload["scope"]["population"] == "scoped_project"
        assert payload["items"]
        group = payload["items"][0]
        assert "links" in group
        assert group["links"]["guide"] == _cli_step("start --format json")
        assert "next_steps" in group
        assert group["next_steps"]
        assert group["tasks"]
        assert "links" in group["tasks"][0]
        assert "next_steps" in group["tasks"][0]
        assert group["tasks"][0]["next_steps"]

    def test_task_merge_preview_json_links_and_next_steps(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Ensure task merge-preview JSON output exposes continuation metadata."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Merge Preview Project"])
        cli_runner.invoke(
            cli, ["task", "add", "Merge Preview Project", "Merge Preview Task"]
        )
        cli_runner.invoke(
            cli, ["task", "add", "Merge Preview Project", "Merge Preview Task"]
        )

        duplicates = cli_runner.invoke(
            cli,
            [
                "task",
                "duplicates",
                "--project",
                "Merge Preview Project",
                "--format",
                "json",
            ],
        )
        assert duplicates.exit_code == 0
        groups = json.loads(duplicates.output)
        assert groups["items"]
        first_group = groups["items"][0]
        primary_id = (
            first_group.get("suggested_primary_id") or first_group["tasks"][0]["id"]
        )
        duplicate_id = next(
            task["id"] for task in first_group["tasks"] if task["id"] != primary_id
        )

        preview = cli_runner.invoke(
            cli,
            [
                "task",
                "merge-preview",
                primary_id,
                "--duplicate-id",
                duplicate_id,
                "--format",
                "json",
            ],
        )
        assert preview.exit_code == 0
        payload = json.loads(preview.output)
        assert "links" in payload
        assert payload["links"]["guide"] == _cli_step("start --format json")
        assert "next_steps" in payload
        assert payload["next_steps"]

    def test_workflow_align_auto_advances(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Ensure workflow align auto-advances along the path to a terminal state."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Align Project"])
        task_result = cli_runner.invoke(
            cli,
            ["task", "add", "Align Project", "Align Task"],
        )
        task_id = _extract_id(task_result.output)

        assign = cli_runner.invoke(
            cli,
            ["workflow", "assign", task_id, "agile", "backlog"],
        )
        assert assign.exit_code == 0

        complete = cli_runner.invoke(
            cli,
            ["task", "complete", task_id],
        )
        assert complete.exit_code == 0

        align = cli_runner.invoke(
            cli,
            ["workflow", "align", task_id, "--by", "tester"],
        )
        assert align.exit_code == 0

        show = cli_runner.invoke(
            cli,
            ["task", "show", task_id, "--format", "json"],
        )
        assert show.exit_code == 0
        payload = json.loads(show.output)
        assert payload["current_state"] == "done"

    def test_workflow_align_dry_run(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Dry run should show plan and leave workflow unchanged."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Align Dry Project"])
        task_result = cli_runner.invoke(
            cli,
            ["task", "add", "Align Dry Project", "Align Dry Task"],
        )
        task_id = _extract_id(task_result.output)

        assign = cli_runner.invoke(
            cli,
            ["workflow", "assign", task_id, "agile", "backlog"],
        )
        assert assign.exit_code == 0

        complete = cli_runner.invoke(
            cli,
            ["task", "complete", task_id],
        )
        assert complete.exit_code == 0

        dry_run = cli_runner.invoke(
            cli,
            ["workflow", "align", task_id, "--by", "tester", "--dry-run"],
        )
        assert dry_run.exit_code == 0
        assert "Alignment plan" in dry_run.output

        show = cli_runner.invoke(
            cli,
            ["task", "show", task_id, "--format", "json"],
        )
        payload = json.loads(show.output)
        assert payload["current_state"] == "backlog"

    def test_workflow_align_goal(self, cli_runner: CliRunner, temp_env: Path) -> None:
        """Workflow align should work for goals via CLI."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        goal_result = cli_runner.invoke(cli, ["goal", "create", "Align CLI Goal"])
        goal_id = _extract_id(goal_result.output)

        assign = cli_runner.invoke(
            cli,
            [
                "workflow",
                "assign",
                goal_id,
                "agile",
                "backlog",
                "--entity-type",
                "goal",
            ],
        )
        assert assign.exit_code == 0

        complete = cli_runner.invoke(cli, ["goal", "complete", goal_id])
        assert complete.exit_code == 0

        align = cli_runner.invoke(
            cli,
            ["workflow", "align", goal_id, "--by", "tester", "--entity-type", "goal"],
        )
        assert align.exit_code == 0

        show = cli_runner.invoke(cli, ["goal", "show", goal_id, "--format", "json"])
        payload = json.loads(show.output)
        assert payload["current_state"] == "done"

    def test_task_complete_with_align_workflow(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Task complete should optionally align workflow when requested."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Complete Align Project"])
        task_result = cli_runner.invoke(
            cli,
            ["task", "add", "Complete Align Project", "Complete Align Task"],
        )
        task_id = _extract_id(task_result.output)

        assign = cli_runner.invoke(
            cli,
            ["workflow", "assign", task_id, "agile", "backlog"],
        )
        assert assign.exit_code == 0

        complete = cli_runner.invoke(
            cli,
            [
                "task",
                "complete",
                task_id,
                "--align-workflow",
                "--by",
                "tester",
            ],
        )
        assert complete.exit_code == 0

        show = cli_runner.invoke(
            cli,
            ["task", "show", task_id, "--format", "json"],
        )
        assert show.exit_code == 0
        payload = json.loads(show.output)
        assert payload["current_state"] == "done"

    def test_project_update_json_output(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Project update should expose machine-readable artifact payloads."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "JSON Update Project"])

        result = cli_runner.invoke(
            cli,
            [
                "project",
                "update",
                "JSON Update Project",
                "--description",
                "Updated from JSON",
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["project"]["description"] == "Updated from JSON"
        assert payload["links"]["self"].startswith(_cli_step("project show "))
        assert payload["links"]["summary"].startswith(_cli_step("project summary "))
        assert payload["links"]["tasks"].startswith(_cli_step("task list --project "))
        assert all(step.startswith("uv run pms ") for step in payload["next_steps"])

    def test_task_checkout_status_force_release_cleanup(
        self, cli_runner: CliRunner, temp_env: Path
    ):
        """Test checkout status, force release, and cleanup via CLI."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Checkout Status Project"])
        task_result = cli_runner.invoke(
            cli,
            ["task", "add", "Checkout Status Project", "Status Task"],
        )
        assert task_result.exit_code == 0
        task_id = _extract_id(task_result.output)

        checkout = cli_runner.invoke(
            cli,
            ["task", "checkout", task_id, "--agent-id", "tester"],
        )
        assert checkout.exit_code == 0

        status = cli_runner.invoke(
            cli,
            ["task", "checkout-status", "--agent-id", "tester"],
        )
        assert status.exit_code == 0
        assert "Status Task" in status.output

        force_release = cli_runner.invoke(
            cli,
            ["task", "force-release", task_id, "--released-by", "admin"],
        )
        assert force_release.exit_code == 0
        assert "Force released checkout" in force_release.output

        status_after = cli_runner.invoke(
            cli,
            ["task", "checkout-status", "--agent-id", "tester"],
        )
        assert status_after.exit_code == 0
        assert "No checkouts" in status_after.output

        status_json = cli_runner.invoke(
            cli,
            ["task", "checkout-status", "--agent-id", "tester", "--format", "json"],
        )
        assert status_json.exit_code == 0
        assert status_json.output.strip().startswith("[")

        status_csv = cli_runner.invoke(
            cli,
            ["task", "checkout-status", "--agent-id", "tester", "--format", "csv"],
        )
        assert status_csv.exit_code == 0
        assert "id,title,project_id" in status_csv.output.splitlines()[0]

        cleanup = cli_runner.invoke(
            cli,
            ["task", "cleanup-checkouts", "--dry-run"],
        )
        assert cleanup.exit_code == 0
        assert "No expired checkouts" in cleanup.output

        log = cli_runner.invoke(
            cli,
            ["task", "checkout-log", "--task-id", task_id, "--limit", "5"],
        )
        assert log.exit_code == 0
        assert "Checkout Log" in log.output

        log_verbose = cli_runner.invoke(
            cli,
            ["task", "checkout-log", "--task-id", task_id, "--verbose"],
        )
        assert log_verbose.exit_code == 0
        assert "Lease" in log_verbose.output

        log_json = cli_runner.invoke(
            cli,
            ["task", "checkout-log", "--task-id", task_id, "--format", "json"],
        )
        assert log_json.exit_code == 0
        assert log_json.output.strip().startswith("[")

        log_csv = cli_runner.invoke(
            cli,
            ["task", "checkout-log", "--task-id", task_id, "--format", "csv"],
        )
        assert log_csv.exit_code == 0
        assert "timestamp,task_id,agent_session_id" in log_csv.output

        log_csv_meta = cli_runner.invoke(
            cli,
            [
                "task",
                "checkout-log",
                "--task-id",
                task_id,
                "--format",
                "csv",
                "--include-metadata",
            ],
        )
        assert log_csv_meta.exit_code == 0
        assert "metadata" in log_csv_meta.output.splitlines()[0]

        log_verbose_meta = cli_runner.invoke(
            cli,
            [
                "task",
                "checkout-log",
                "--task-id",
                task_id,
                "--verbose",
                "--include-metadata",
            ],
        )
        assert log_verbose_meta.exit_code == 0
        assert "Meta" in log_verbose_meta.output

    def test_task_checkout_uses_current_actor_and_surfaces_checkout_payload(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Checkout should resolve current actor into lease payloads and status output."""
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        fixture = _setup_actor_assignment_surface_fixture(cli_runner)

        config_result = cli_runner.invoke(
            cli,
            ["config", "set", "--current-actor", "alice-example"],
        )
        assert config_result.exit_code == 0, config_result.output

        checkout_result = cli_runner.invoke(
            cli,
            [
                "task",
                "checkout",
                fixture["ready"],
                "--agent-id",
                "lease-agent",
            ],
        )
        assert checkout_result.exit_code == 0, checkout_result.output
        assert "Checkout actor" in checkout_result.output

        show_result = cli_runner.invoke(
            cli,
            ["task", "show", fixture["ready"], "--format", "json"],
        )
        assert show_result.exit_code == 0, show_result.output
        show_payload = json.loads(show_result.output)
        assert show_payload["checkout"]["agent_session_id"] == "lease-agent"
        assert show_payload["checkout"]["actor"]["id"]
        assert show_payload["checkout"]["actor"]["actor"]["handle"] == "alice-example"
        assert show_payload["links"]["checkout_actor"] == _cli_step(
            "actor show alice-example --format json"
        )

        status_result = cli_runner.invoke(
            cli,
            [
                "task",
                "checkout-status",
                "--agent-id",
                "lease-agent",
                "--format",
                "json",
            ],
        )
        assert status_result.exit_code == 0, status_result.output
        status_payload = json.loads(status_result.output)
        assert (
            status_payload[0]["checkout"]["actor"]["actor"]["handle"] == "alice-example"
        )

        status_csv = cli_runner.invoke(
            cli,
            [
                "task",
                "checkout-status",
                "--agent-id",
                "lease-agent",
                "--format",
                "csv",
            ],
        )
        assert status_csv.exit_code == 0, status_csv.output
        assert "checkout_actor" in status_csv.output.splitlines()[0]
        assert "alice-example" in status_csv.output

        actor_show_result = cli_runner.invoke(
            cli,
            ["actor", "show", "alice-example", "--format", "json"],
        )
        assert actor_show_result.exit_code == 0, actor_show_result.output
        actor_payload = json.loads(actor_show_result.output)
        assert actor_payload["workload"]["checkout_scope"] == "direct_only"
        assert actor_payload["workload"]["checkouts"]["active_checkouts"] == 1
        checkout_titles = {
            item["title"] for item in actor_payload["workload"]["checkout_tasks"]
        }
        assert "Ready Actor Task" in checkout_titles

        actor_show_csv = cli_runner.invoke(
            cli,
            ["actor", "show", "alice-example", "--format", "csv"],
        )
        assert actor_show_csv.exit_code == 0, actor_show_csv.output
        assert (
            "id,name,handle,kind,status,updated_at,last_activity_at,last_transition_at,"
            "assigned_tasks,active_checkouts,expired_checkouts"
            in actor_show_csv.output.splitlines()[0]
        )
        assert ",alice-example,human,active," in actor_show_csv.output

    def test_task_checkout_log_surfaces_checkout_actor_identity(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Checkout log should expose canonical checkout actor identity across formats."""
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        fixture = _setup_actor_assignment_surface_fixture(cli_runner)
        cli_runner.invoke(cli, ["config", "set", "--current-actor", "alice-example"])

        checkout_result = cli_runner.invoke(
            cli,
            [
                "task",
                "checkout",
                fixture["ready"],
                "--agent-id",
                "audit-agent",
            ],
        )
        assert checkout_result.exit_code == 0, checkout_result.output

        log_json = cli_runner.invoke(
            cli,
            [
                "task",
                "checkout-log",
                "--task-id",
                fixture["ready"],
                "--format",
                "json",
            ],
        )
        assert log_json.exit_code == 0, log_json.output
        log_payload = json.loads(log_json.output)
        assert log_payload[0]["checkout_actor"]["id"]
        assert log_payload[0]["checkout_actor"]["actor"]["handle"] == "alice-example"
        assert log_payload[0]["links"]["actor"] == _cli_step(
            "actor show alice-example --format json"
        )

        log_csv = cli_runner.invoke(
            cli,
            [
                "task",
                "checkout-log",
                "--task-id",
                fixture["ready"],
                "--format",
                "csv",
            ],
        )
        assert log_csv.exit_code == 0, log_csv.output
        assert "checkout_actor" in log_csv.output.splitlines()[0]
        assert "alice-example" in log_csv.output

    def test_checkout_actor_payloads_propagate_to_dashboard_and_project_surfaces(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Checkout actor identity should remain visible on summary/reporting surfaces."""
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        fixture = _setup_actor_assignment_surface_fixture(cli_runner)

        config_result = cli_runner.invoke(
            cli,
            ["config", "set", "--current-actor", "alice-example"],
        )
        assert config_result.exit_code == 0, config_result.output

        checkout_result = cli_runner.invoke(
            cli,
            [
                "task",
                "checkout",
                fixture["in_progress"],
                "--agent-id",
                "focus-agent",
            ],
        )
        assert checkout_result.exit_code == 0, checkout_result.output

        dashboard_result = cli_runner.invoke(cli, ["dashboard", "--format", "json"])
        assert dashboard_result.exit_code == 0, dashboard_result.output
        dashboard_payload = json.loads(dashboard_result.output)
        in_progress_items = {
            item["title"]: item for item in dashboard_payload["in_progress_tasks"]
        }
        assert (
            in_progress_items["In Progress Actor Task"]["checkout"]["actor"]["actor"][
                "handle"
            ]
            == "alice-example"
        )

        project_show = cli_runner.invoke(
            cli,
            [
                "project",
                "show",
                fixture["project_name"],
                "--format",
                "json",
            ],
        )
        assert project_show.exit_code == 0, project_show.output
        project_show_payload = json.loads(project_show.output)
        active_items = {
            item["title"]: item
            for item in project_show_payload["execution"]["active_tasks"]
        }
        assert (
            active_items["In Progress Actor Task"]["checkout"]["actor"]["actor"][
                "handle"
            ]
            == "alice-example"
        )

        project_summary = cli_runner.invoke(
            cli,
            [
                "project",
                "summary",
                fixture["project_name"],
                "--format",
                "json",
            ],
        )
        assert project_summary.exit_code == 0, project_summary.output
        project_summary_payload = json.loads(project_summary.output)
        summary_active_items = {
            item["title"]: item
            for item in project_summary_payload["execution"]["active_tasks"]
        }
        assert (
            summary_active_items["In Progress Actor Task"]["checkout"]["actor"][
                "actor"
            ]["handle"]
            == "alice-example"
        )


class TestWorkflowCommands:
    """Tests for workflow commands."""

    def test_workflow_list(self, cli_runner: CliRunner):
        """Test listing workflows."""
        result = cli_runner.invoke(cli, ["workflow", "list"])
        assert result.exit_code == 0
        _assert_plain_output_contains(result.output, "Workflows")

        result_json = cli_runner.invoke(cli, ["workflow", "list", "--format", "json"])
        assert result_json.exit_code == 0
        payload = json.loads(result_json.output)
        assert "items" in payload

        result_csv = cli_runner.invoke(cli, ["workflow", "list", "--format", "csv"])
        assert result_csv.exit_code == 0
        assert "key,name,id,entity_type" in result_csv.output.splitlines()[0]

    def test_workflow_assign_and_transition(
        self, cli_runner: CliRunner, temp_env: Path
    ):
        """Test workflow assign and transition."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Workflow Project"])
        task_result = cli_runner.invoke(
            cli,
            ["task", "add", "Workflow Project", "Workflow Task"],
        )
        task_id = _extract_id(task_result.output)

        assign = cli_runner.invoke(
            cli,
            ["workflow", "assign", task_id, "sdlc", "concept"],
        )
        assert assign.exit_code == 0
        assert "Assigned workflow" in assign.output

        transition = cli_runner.invoke(
            cli,
            ["workflow", "transition", task_id, "idea", "--by", "tester"],
        )
        assert transition.exit_code == 0
        assert "Transitioned" in transition.output

    def test_workflow_show(self, cli_runner: CliRunner):
        """Test workflow show output."""
        result = cli_runner.invoke(cli, ["workflow", "show", "sdlc"])
        assert result.exit_code == 0
        _assert_plain_output_contains(result.output, "States", "Transitions")

        result_json = cli_runner.invoke(
            cli,
            ["workflow", "show", "sdlc", "--format", "json"],
        )
        assert result_json.exit_code == 0
        assert '"states"' in result_json.output
        assert '"transitions"' in result_json.output


class TestProjectProductFormats:
    """Tests for project/product list format outputs."""

    def test_project_list_csv(self, cli_runner: CliRunner, temp_env: Path):
        """Test project list CSV output."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "CSV Project"])

        result = cli_runner.invoke(cli, ["project", "list", "--format", "csv"])
        assert result.exit_code == 0
        assert "id,name,status,tags" in result.output.splitlines()[0]

    def test_product_list_csv(self, cli_runner: CliRunner, temp_env: Path):
        """Test product list CSV output."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["product", "create", "CSV Product"])

        result = cli_runner.invoke(cli, ["product", "list", "--format", "csv"])
        assert result.exit_code == 0
        assert "id,name,status,product_type" in result.output.splitlines()[0]

    def test_product_list_json_wrapper(self, cli_runner: CliRunner, temp_env: Path):
        """Test product list JSON wrapper output."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["product", "create", "JSON Product"])

        result = cli_runner.invoke(cli, ["product", "list", "--format", "json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert "items" in payload
        assert payload["items"][0]["name"] == "JSON Product"
        assert payload["items"][0]["links"]["projects"].startswith(
            _cli_step("project list --product-id ")
        )

    def test_product_list_json_is_machine_parseable_with_long_names(
        self, cli_runner: CliRunner, temp_env: Path
    ):
        """Product list JSON should remain parseable when names are long."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(
            cli,
            [
                "product",
                "create",
                "Platform product for authoritative query semantics, mutation-readback contracts, cross-surface parity, and runtime truth",
            ],
        )

        result = cli_runner.invoke(cli, ["product", "list", "--format", "json"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert any(
            "mutation-readback contracts" in item["name"] for item in payload["items"]
        )

    def test_project_show_formats(self, cli_runner: CliRunner, temp_env: Path):
        """Test project show json/csv outputs."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Show Project"])

        show_json = cli_runner.invoke(
            cli,
            ["project", "show", "Show Project", "--format", "json"],
        )
        assert show_json.exit_code == 0
        payload = json.loads(show_json.output)
        assert "links" in payload
        assert payload["links"]["guide"] == _cli_step("start --format json")
        assert "next_steps" in payload
        assert payload["next_steps"]

        show_csv = cli_runner.invoke(
            cli,
            ["project", "show", "Show Project", "--format", "csv"],
        )
        assert show_csv.exit_code == 0
        assert "id,name,status" in show_csv.output.splitlines()[0]

    def test_project_show_json_surfaces_focus_task(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Project show JSON should surface the active incomplete task."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Focused Project"])
        cli_runner.invoke(cli, ["task", "add", "Focused Project", "Ready Follow-up"])
        cli_runner.invoke(cli, ["task", "add", "Focused Project", "Active Work"])
        cli_runner.invoke(
            cli,
            [
                "task",
                "start",
                "Active Work",
                "--project",
                "Focused Project",
                "--by",
                "tester",
            ],
        )

        show_json = cli_runner.invoke(
            cli,
            ["project", "show", "Focused Project", "--format", "json"],
        )

        assert show_json.exit_code == 0
        payload = json.loads(show_json.output)
        assert payload["focus_task"]["title"] == "Active Work"
        assert payload["focus_task"]["status"] == "in_progress"
        assert payload["total_tasks"] == 2
        assert payload["completed_tasks"] == 0
        assert payload["in_progress_tasks"] == 1

    def test_project_show_detail_linked_task_links_are_normalized(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Show Linked Project"])
        task_result = cli_runner.invoke(
            cli, ["task", "add", "Show Linked Project", "Linked Task"]
        )
        assert task_result.exit_code == 0, task_result.output
        task_id = _extract_id(task_result.output)

        show_json = cli_runner.invoke(
            cli,
            [
                "project",
                "show",
                "Show Linked Project",
                "--include-linked",
                "--format",
                "json",
            ],
        )

        assert show_json.exit_code == 0, show_json.output
        payload = json.loads(show_json.output)
        linked_task = payload["linked"]["tasks"][0]
        assert linked_task["id"] == task_id
        assert linked_task["links"]["self"] == _cli_step(f"task show {task_id}")
        assert linked_task["links"]["timeline"] == _cli_step(f"task timeline {task_id}")
        assert linked_task["links"]["graph"] == _cli_step(f"task graph {task_id}")
        assert linked_task["links"]["evidence"] == _cli_step(
            f"task evidence list {task_id}"
        )

    def test_project_list_hides_audit_generated_projects_by_default(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Operator Project"])
        cli_runner.invoke(cli, ["project", "create", "Audit Project abc123"])

        result = cli_runner.invoke(cli, ["project", "list", "--format", "json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert [item["name"] for item in payload["items"]] == ["Operator Project"]
        assert payload["suppressed_generated_count"] == 1
        assert (
            payload["freshest_visible_activity"]["project_name"] == "Operator Project"
        )
        assert (
            payload["freshest_visible_transition"]["project_name"] == "Operator Project"
        )

    def test_project_list_can_include_audit_generated_projects_when_requested(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Operator Project"])
        cli_runner.invoke(cli, ["project", "create", "Audit Project xyz789"])

        result = cli_runner.invoke(
            cli, ["project", "list", "--format", "json", "--include-generated"]
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert {item["name"] for item in payload["items"]} == {
            "Operator Project",
            "Audit Project xyz789",
        }
        assert payload["suppressed_generated_count"] == 0
        assert payload["scope"]["population"] == "all_retained"
        assert payload["visible_totals"]["population"] == "visible_operator"
        assert payload["visible_totals"]["total_projects"] == 1
        assert payload["population_totals"]["population"] == "all_retained"
        assert payload["population_totals"]["total_projects"] == 2
        audit_item = next(
            item for item in payload["items"] if item["name"] == "Audit Project xyz789"
        )
        assert audit_item["operator_category"] == "audit_artifact"
        assert audit_item["operator_category_label"] == "Audit Artifact"
        assert payload["category_counts"]["audit_artifact"] == 1

    def test_project_list_include_generated_separates_visible_and_retained_totals(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Operator Project"])
        cli_runner.invoke(cli, ["project", "create", "Audit Project xyz789"])
        cli_runner.invoke(cli, ["project", "create", "Archived Project"])
        cli_runner.invoke(
            cli,
            ["project", "update", "Archived Project", "--status", "archived"],
        )

        result = cli_runner.invoke(
            cli, ["project", "list", "--include-generated", "--format", "json"]
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["scope"]["population"] == "all_retained"
        assert payload["visible_totals"]["population"] == "visible_operator"
        assert payload["visible_totals"]["total_projects"] == 2
        assert payload["visible_totals"]["archived_projects"] == 1
        assert payload["population_totals"]["population"] == "all_retained"
        assert payload["population_totals"]["total_projects"] == 3
        assert payload["population_totals"]["archived_projects"] == 1
        assert payload["page"]["total_count"] == 3

    def test_project_list_include_generated_preserves_visible_active_work_counts(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Goal Filter Project A"])
        cli_runner.invoke(cli, ["project", "create", "Recent Progress Project"])
        cli_runner.invoke(cli, ["project", "create", "Audit Project audit123"])
        live_task = cli_runner.invoke(
            cli, ["task", "add", "Recent Progress Project", "Recent Progress Task"]
        )
        live_task_id = _extract_id(live_task.output)
        cli_runner.invoke(cli, ["task", "start", live_task_id, "--by", "tester"])

        result = cli_runner.invoke(
            cli, ["project", "list", "--include-generated", "--format", "json"]
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["visible_totals"]["active_projects"] == 2
        assert payload["visible_totals"]["active_work_projects"] == 1
        assert payload["population_totals"]["active_projects"] == 3
        assert payload["population_totals"]["active_work_projects"] == 1
        assert payload["scope"]["active_visible_projects"] == 2
        assert payload["scope"]["active_work_visible_projects"] == 1

    def test_project_list_keeps_real_quickstart_projects_visible(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        result = cli_runner.invoke(
            cli,
            [
                "quickstart",
                "--defaults",
                "--project",
                "Growth Project Visible",
                "--task",
                "Define delivery scope",
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0, result.output

        listed = cli_runner.invoke(cli, ["project", "list", "--format", "json"])

        assert listed.exit_code == 0, listed.output
        payload = json.loads(listed.output)
        assert "Growth Project Visible" in {item["name"] for item in payload["items"]}

    def test_project_list_paginates_over_visible_projects_not_raw_generated_rows(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Operator Project"])
        for index in range(3):
            cli_runner.invoke(cli, ["project", "create", f"Audit Project {index:02d}"])

        result = cli_runner.invoke(
            cli,
            ["project", "list", "--format", "json", "--limit", "2"],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert [item["name"] for item in payload["items"]] == ["Operator Project"]
        assert payload["page"]["total_count"] == 1
        assert payload["page"]["has_more"] is False
        assert payload["suppressed_generated_count"] == 3

    def test_task_list_json_reports_terminal_reason_when_all_tasks_are_done(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Terminal Task Project"])
        task_result = cli_runner.invoke(
            cli, ["task", "add", "Terminal Task Project", "Done Task"]
        )
        task_id = _extract_id(task_result.output)
        cli_runner.invoke(cli, ["task", "complete", task_id, "--by", "tester"])

        result = cli_runner.invoke(
            cli,
            [
                "task",
                "list",
                "--project",
                "Terminal Task Project",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["scope"]["population"] == "scoped_project"
        assert payload["population_totals"]["population"] == "scoped_project"
        assert payload["focus_task"] is None
        assert payload["terminal_reason"] == "all surfaced tasks are already complete"
        assert payload["next_steps"][0].startswith(_cli_step("task add "))

    def test_task_list_global_in_progress_uses_visible_operator_population_by_default(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Operator Project"])
        cli_runner.invoke(cli, ["project", "create", "Audit Project xyz789"])
        cli_runner.invoke(cli, ["project", "create", "Archived Project"])
        cli_runner.invoke(
            cli, ["project", "update", "Archived Project", "--status", "archived"]
        )
        operator_task_id = _extract_id(
            cli_runner.invoke(
                cli, ["task", "add", "Operator Project", "Operator Task"]
            ).output
        )
        audit_task_id = _extract_id(
            cli_runner.invoke(
                cli, ["task", "add", "Audit Project xyz789", "Audit Task"]
            ).output
        )
        archived_task_id = _extract_id(
            cli_runner.invoke(
                cli, ["task", "add", "Archived Project", "Archived Task"]
            ).output
        )
        for task_id in (operator_task_id, audit_task_id, archived_task_id):
            cli_runner.invoke(cli, ["task", "start", task_id, "--by", "tester"])

        result = cli_runner.invoke(
            cli, ["task", "list", "--status", "in_progress", "--format", "json"]
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["scope"]["population"] == "visible_operator"
        assert payload["visible_totals"]["population"] == "visible_operator"
        assert payload["population_totals"]["population"] == "visible_operator"
        assert payload["visible_totals"]["total_tasks"] == 1
        assert payload["population_totals"]["total_tasks"] == 1
        assert payload["page"]["total_count"] == 1
        assert payload["suppressed_hidden_count"] == 2
        assert [item["project_name"] for item in payload["items"]] == [
            "Operator Project"
        ]

    def test_task_list_global_in_progress_include_generated_separates_visible_and_retained_totals(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Operator Project"])
        cli_runner.invoke(cli, ["project", "create", "Audit Project xyz789"])
        cli_runner.invoke(cli, ["project", "create", "Archived Project"])
        cli_runner.invoke(
            cli, ["project", "update", "Archived Project", "--status", "archived"]
        )
        operator_task_id = _extract_id(
            cli_runner.invoke(
                cli, ["task", "add", "Operator Project", "Operator Task"]
            ).output
        )
        audit_task_id = _extract_id(
            cli_runner.invoke(
                cli, ["task", "add", "Audit Project xyz789", "Audit Task"]
            ).output
        )
        archived_task_id = _extract_id(
            cli_runner.invoke(
                cli, ["task", "add", "Archived Project", "Archived Task"]
            ).output
        )
        for task_id in (operator_task_id, audit_task_id, archived_task_id):
            cli_runner.invoke(cli, ["task", "start", task_id, "--by", "tester"])

        result = cli_runner.invoke(
            cli,
            [
                "task",
                "list",
                "--status",
                "in_progress",
                "--include-generated",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["scope"]["population"] == "all_retained"
        assert payload["visible_totals"]["population"] == "visible_operator"
        assert payload["visible_totals"]["total_tasks"] == 1
        assert payload["population_totals"]["population"] == "all_retained"
        assert payload["population_totals"]["total_tasks"] == 3
        assert payload["page"]["total_count"] == 3
        by_project = {item["project_name"]: item for item in payload["items"]}
        assert (
            by_project["Audit Project xyz789"]["project_operator_category"]
            == "audit_artifact"
        )

    def test_task_search_global_uses_visible_operator_population_by_default(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Operator Search Project"])
        cli_runner.invoke(cli, ["project", "create", "Audit Project search789"])
        cli_runner.invoke(cli, ["project", "create", "Archived Search Project"])
        cli_runner.invoke(
            cli,
            ["project", "update", "Archived Search Project", "--status", "archived"],
        )
        cli_runner.invoke(
            cli, ["task", "add", "Operator Search Project", "Shared Search Task"]
        )
        cli_runner.invoke(
            cli, ["task", "add", "Audit Project search789", "Shared Search Task"]
        )
        cli_runner.invoke(
            cli, ["task", "add", "Archived Search Project", "Shared Search Task"]
        )

        result = cli_runner.invoke(
            cli,
            ["task", "search", "--query", "Shared Search Task", "--format", "json"],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["scope"]["population"] == "visible_operator"
        assert payload["visible_totals"]["population"] == "visible_operator"
        assert payload["population_totals"]["population"] == "visible_operator"
        assert payload["visible_totals"]["total_tasks"] == 1
        assert payload["population_totals"]["total_tasks"] == 1
        assert payload["page"]["total_count"] == 1
        assert payload["suppressed_hidden_count"] == 2
        assert [item["project_name"] for item in payload["items"]] == [
            "Operator Search Project"
        ]

    def test_task_search_global_include_generated_separates_visible_and_retained_totals(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Operator Search Project"])
        cli_runner.invoke(cli, ["project", "create", "Audit Project search789"])
        cli_runner.invoke(cli, ["project", "create", "Archived Search Project"])
        cli_runner.invoke(
            cli,
            ["project", "update", "Archived Search Project", "--status", "archived"],
        )
        cli_runner.invoke(
            cli, ["task", "add", "Operator Search Project", "Shared Search Task"]
        )
        cli_runner.invoke(
            cli, ["task", "add", "Audit Project search789", "Shared Search Task"]
        )
        cli_runner.invoke(
            cli, ["task", "add", "Archived Search Project", "Shared Search Task"]
        )

        result = cli_runner.invoke(
            cli,
            [
                "task",
                "search",
                "--query",
                "Shared Search Task",
                "--include-generated",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["scope"]["population"] == "all_retained"
        assert payload["visible_totals"]["population"] == "visible_operator"
        assert payload["visible_totals"]["total_tasks"] == 1
        assert payload["population_totals"]["population"] == "all_retained"
        assert payload["population_totals"]["total_tasks"] == 3
        assert payload["page"]["total_count"] == 3
        by_project = {item["project_name"]: item for item in payload["items"]}
        assert (
            by_project["Audit Project search789"]["project_operator_category"]
            == "audit_artifact"
        )

    def test_task_ready_global_uses_visible_operator_population_by_default(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Operator Ready Project"])
        cli_runner.invoke(cli, ["project", "create", "Audit Project ready789"])
        cli_runner.invoke(cli, ["project", "create", "Archived Ready Project"])
        cli_runner.invoke(
            cli, ["project", "update", "Archived Ready Project", "--status", "archived"]
        )
        cli_runner.invoke(
            cli, ["task", "add", "Operator Ready Project", "Operator Ready Task"]
        )
        cli_runner.invoke(
            cli, ["task", "add", "Audit Project ready789", "Audit Ready Task"]
        )
        cli_runner.invoke(
            cli, ["task", "add", "Archived Ready Project", "Archived Ready Task"]
        )

        result = cli_runner.invoke(cli, ["task", "ready", "--format", "json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["scope"]["population"] == "visible_operator"
        assert payload["visible_totals"]["population"] == "visible_operator"
        assert payload["population_totals"]["population"] == "visible_operator"
        assert payload["visible_totals"]["total_tasks"] == 1
        assert payload["population_totals"]["total_tasks"] == 1
        assert payload["suppressed_hidden_count"] == 2
        assert [item["project_name"] for item in payload["items"]] == [
            "Operator Ready Project"
        ]

    def test_task_ready_global_include_generated_separates_visible_and_retained_totals(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Operator Ready Project"])
        cli_runner.invoke(cli, ["project", "create", "Audit Project ready789"])
        cli_runner.invoke(cli, ["project", "create", "Archived Ready Project"])
        cli_runner.invoke(
            cli, ["project", "update", "Archived Ready Project", "--status", "archived"]
        )
        cli_runner.invoke(
            cli, ["task", "add", "Operator Ready Project", "Operator Ready Task"]
        )
        cli_runner.invoke(
            cli, ["task", "add", "Audit Project ready789", "Audit Ready Task"]
        )
        cli_runner.invoke(
            cli, ["task", "add", "Archived Ready Project", "Archived Ready Task"]
        )

        result = cli_runner.invoke(
            cli, ["task", "ready", "--include-generated", "--format", "json"]
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["scope"]["population"] == "all_retained"
        assert payload["visible_totals"]["total_tasks"] == 1
        assert payload["population_totals"]["population"] == "all_retained"
        assert payload["population_totals"]["total_tasks"] == 3
        by_project = {item["project_name"]: item for item in payload["items"]}
        assert (
            by_project["Audit Project ready789"]["project_operator_category"]
            == "audit_artifact"
        )

    def test_task_stale_global_uses_visible_operator_population_by_default(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Operator Stale Project"])
        cli_runner.invoke(cli, ["project", "create", "Audit Project stale789"])
        cli_runner.invoke(cli, ["project", "create", "Archived Stale Project"])
        cli_runner.invoke(
            cli, ["project", "update", "Archived Stale Project", "--status", "archived"]
        )
        cli_runner.invoke(
            cli, ["task", "add", "Operator Stale Project", "Operator Stale Task"]
        )
        cli_runner.invoke(
            cli, ["task", "add", "Audit Project stale789", "Audit Stale Task"]
        )
        cli_runner.invoke(
            cli, ["task", "add", "Archived Stale Project", "Archived Stale Task"]
        )

        result = cli_runner.invoke(
            cli, ["task", "stale", "--days", "0", "--format", "json"]
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["scope"]["population"] == "visible_operator"
        assert payload["visible_totals"]["total_tasks"] == 1
        assert payload["population_totals"]["population"] == "visible_operator"
        assert payload["population_totals"]["total_tasks"] == 1
        assert payload["suppressed_hidden_count"] == 2
        assert [item["project_name"] for item in payload["items"]] == [
            "Operator Stale Project"
        ]

    def test_task_stale_global_include_generated_separates_visible_and_retained_totals(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Operator Stale Project"])
        cli_runner.invoke(cli, ["project", "create", "Audit Project stale789"])
        cli_runner.invoke(cli, ["project", "create", "Archived Stale Project"])
        cli_runner.invoke(
            cli, ["project", "update", "Archived Stale Project", "--status", "archived"]
        )
        cli_runner.invoke(
            cli, ["task", "add", "Operator Stale Project", "Operator Stale Task"]
        )
        cli_runner.invoke(
            cli, ["task", "add", "Audit Project stale789", "Audit Stale Task"]
        )
        cli_runner.invoke(
            cli, ["task", "add", "Archived Stale Project", "Archived Stale Task"]
        )

        result = cli_runner.invoke(
            cli,
            ["task", "stale", "--days", "0", "--include-generated", "--format", "json"],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["scope"]["population"] == "all_retained"
        assert payload["visible_totals"]["total_tasks"] == 1
        assert payload["population_totals"]["population"] == "all_retained"
        assert payload["population_totals"]["total_tasks"] == 3
        by_project = {item["project_name"]: item for item in payload["items"]}
        assert (
            by_project["Audit Project stale789"]["project_operator_category"]
            == "audit_artifact"
        )

    def test_task_blocked_global_uses_visible_operator_population_by_default(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Operator Blocked Project"])
        cli_runner.invoke(cli, ["project", "create", "Audit Project blocked789"])
        cli_runner.invoke(cli, ["project", "create", "Archived Blocked Project"])
        cli_runner.invoke(
            cli,
            ["project", "update", "Archived Blocked Project", "--status", "archived"],
        )
        operator_root = _extract_id(
            cli_runner.invoke(
                cli, ["task", "add", "Operator Blocked Project", "Operator Root"]
            ).output
        )
        operator_leaf = _extract_id(
            cli_runner.invoke(
                cli, ["task", "add", "Operator Blocked Project", "Operator Leaf"]
            ).output
        )
        audit_root = _extract_id(
            cli_runner.invoke(
                cli, ["task", "add", "Audit Project blocked789", "Audit Root"]
            ).output
        )
        audit_leaf = _extract_id(
            cli_runner.invoke(
                cli, ["task", "add", "Audit Project blocked789", "Audit Leaf"]
            ).output
        )
        archived_root = _extract_id(
            cli_runner.invoke(
                cli, ["task", "add", "Archived Blocked Project", "Archived Root"]
            ).output
        )
        archived_leaf = _extract_id(
            cli_runner.invoke(
                cli, ["task", "add", "Archived Blocked Project", "Archived Leaf"]
            ).output
        )
        cli_runner.invoke(cli, ["task", "dep", "add", operator_leaf, operator_root])
        cli_runner.invoke(cli, ["task", "dep", "add", audit_leaf, audit_root])
        cli_runner.invoke(cli, ["task", "dep", "add", archived_leaf, archived_root])

        result = cli_runner.invoke(cli, ["task", "blocked", "--format", "json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["scope"]["population"] == "visible_operator"
        assert payload["visible_totals"]["blocked_tasks"] == 1
        assert payload["population_totals"]["population"] == "visible_operator"
        assert payload["population_totals"]["blocked_tasks"] == 1
        assert payload["suppressed_hidden_count"] == 2
        assert [item["project_name"] for item in payload["items"]] == [
            "Operator Blocked Project"
        ]

    def test_task_blocked_global_include_generated_separates_visible_and_retained_totals(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Operator Blocked Project"])
        cli_runner.invoke(cli, ["project", "create", "Audit Project blocked789"])
        cli_runner.invoke(cli, ["project", "create", "Archived Blocked Project"])
        cli_runner.invoke(
            cli,
            ["project", "update", "Archived Blocked Project", "--status", "archived"],
        )
        operator_root = _extract_id(
            cli_runner.invoke(
                cli, ["task", "add", "Operator Blocked Project", "Operator Root"]
            ).output
        )
        operator_leaf = _extract_id(
            cli_runner.invoke(
                cli, ["task", "add", "Operator Blocked Project", "Operator Leaf"]
            ).output
        )
        audit_root = _extract_id(
            cli_runner.invoke(
                cli, ["task", "add", "Audit Project blocked789", "Audit Root"]
            ).output
        )
        audit_leaf = _extract_id(
            cli_runner.invoke(
                cli, ["task", "add", "Audit Project blocked789", "Audit Leaf"]
            ).output
        )
        archived_root = _extract_id(
            cli_runner.invoke(
                cli, ["task", "add", "Archived Blocked Project", "Archived Root"]
            ).output
        )
        archived_leaf = _extract_id(
            cli_runner.invoke(
                cli, ["task", "add", "Archived Blocked Project", "Archived Leaf"]
            ).output
        )
        cli_runner.invoke(cli, ["task", "dep", "add", operator_leaf, operator_root])
        cli_runner.invoke(cli, ["task", "dep", "add", audit_leaf, audit_root])
        cli_runner.invoke(cli, ["task", "dep", "add", archived_leaf, archived_root])

        result = cli_runner.invoke(
            cli, ["task", "blocked", "--include-generated", "--format", "json"]
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["scope"]["population"] == "all_retained"
        assert payload["visible_totals"]["blocked_tasks"] == 1
        assert payload["population_totals"]["population"] == "all_retained"
        assert payload["population_totals"]["blocked_tasks"] == 3
        by_project = {item["project_name"]: item for item in payload["items"]}
        assert (
            by_project["Audit Project blocked789"]["project_operator_category"]
            == "audit_artifact"
        )

    def test_task_duplicates_global_uses_visible_operator_population_by_default(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Operator Duplicate Project"])
        cli_runner.invoke(cli, ["project", "create", "Audit Project dup789"])
        cli_runner.invoke(cli, ["project", "create", "Archived Duplicate Project"])
        cli_runner.invoke(
            cli,
            ["project", "update", "Archived Duplicate Project", "--status", "archived"],
        )
        cli_runner.invoke(
            cli, ["task", "add", "Operator Duplicate Project", "Shared Duplicate Task"]
        )
        cli_runner.invoke(
            cli, ["task", "add", "Operator Duplicate Project", "Shared Duplicate Task"]
        )
        cli_runner.invoke(
            cli, ["task", "add", "Audit Project dup789", "Shared Duplicate Task"]
        )
        cli_runner.invoke(
            cli, ["task", "add", "Archived Duplicate Project", "Shared Duplicate Task"]
        )

        result = cli_runner.invoke(cli, ["task", "duplicates", "--format", "json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["scope"]["population"] == "visible_operator"
        assert payload["visible_totals"]["population"] == "visible_operator"
        assert payload["visible_totals"]["duplicate_groups"] == 1
        assert payload["visible_totals"]["duplicate_tasks"] == 2
        assert payload["population_totals"]["population"] == "visible_operator"
        assert payload["population_totals"]["duplicate_groups"] == 1
        assert payload["population_totals"]["duplicate_tasks"] == 2
        assert payload["suppressed_hidden_count"] == 2
        assert payload["page"]["total_count"] == 1
        assert payload["items"]
        group = payload["items"][0]
        assert group["count"] == 2
        assert [task["project_name"] for task in group["tasks"]] == [
            "Operator Duplicate Project",
            "Operator Duplicate Project",
        ]

    def test_task_duplicates_global_include_generated_separates_visible_and_retained_totals(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Operator Duplicate Project"])
        cli_runner.invoke(cli, ["project", "create", "Audit Project dup789"])
        cli_runner.invoke(cli, ["project", "create", "Archived Duplicate Project"])
        cli_runner.invoke(
            cli,
            ["project", "update", "Archived Duplicate Project", "--status", "archived"],
        )
        cli_runner.invoke(
            cli, ["task", "add", "Operator Duplicate Project", "Shared Duplicate Task"]
        )
        cli_runner.invoke(
            cli, ["task", "add", "Operator Duplicate Project", "Shared Duplicate Task"]
        )
        cli_runner.invoke(
            cli, ["task", "add", "Audit Project dup789", "Shared Duplicate Task"]
        )
        cli_runner.invoke(
            cli, ["task", "add", "Archived Duplicate Project", "Shared Duplicate Task"]
        )

        result = cli_runner.invoke(
            cli, ["task", "duplicates", "--include-generated", "--format", "json"]
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["scope"]["population"] == "all_retained"
        assert payload["visible_totals"]["population"] == "visible_operator"
        assert payload["visible_totals"]["duplicate_groups"] == 1
        assert payload["visible_totals"]["duplicate_tasks"] == 2
        assert payload["population_totals"]["population"] == "all_retained"
        assert payload["population_totals"]["duplicate_groups"] == 1
        assert payload["population_totals"]["duplicate_tasks"] == 4
        assert payload["suppressed_hidden_count"] == 2
        assert payload["page"]["total_count"] == 1
        group = payload["items"][0]
        by_project = {task["project_name"]: task for task in group["tasks"]}
        assert (
            by_project["Audit Project dup789"]["project_operator_category"]
            == "audit_artifact"
        )

    def test_project_summary_formats(self, cli_runner: CliRunner, temp_env: Path):
        """Test project summary json/csv outputs."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Summary Project"])

        summary_json = cli_runner.invoke(
            cli,
            ["project", "summary", "Summary Project", "--format", "json"],
        )
        assert summary_json.exit_code == 0
        payload = json.loads(summary_json.output)
        assert payload["project"]["name"] == "Summary Project"
        assert payload["stats"] is not None
        assert payload["links"]["self"] == _cli_step(
            'project summary "Summary Project"'
        )
        assert payload["links"]["tasks"] == _cli_step(
            'task list --project "Summary Project"'
        )

        summary_csv = cli_runner.invoke(
            cli,
            ["project", "summary", "Summary Project", "--format", "csv"],
        )
        assert summary_csv.exit_code == 0
        assert (
            "project_id,project_name,health_score" in summary_csv.output.splitlines()[0]
        )

    def test_project_show_and_summary_focus_task_reflect_latest_progress(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Focus Freshness Project"])
        task_result = cli_runner.invoke(
            cli,
            ["task", "add", "Focus Freshness Project", "Fresh Focus Task"],
        )
        task_id = _extract_id(task_result.output)

        start_result = cli_runner.invoke(
            cli,
            [
                "task",
                "start",
                task_id,
                "--project",
                "Focus Freshness Project",
                "--by",
                "tester",
            ],
        )
        assert start_result.exit_code == 0, start_result.output

        progress_result = cli_runner.invoke(
            cli,
            [
                "task",
                "progress",
                task_id,
                "--project",
                "Focus Freshness Project",
                "40",
                "Made progress",
                "--by",
                "tester",
            ],
        )
        assert progress_result.exit_code == 0, progress_result.output

        show_result = cli_runner.invoke(
            cli,
            ["project", "show", "Focus Freshness Project", "--format", "json"],
        )
        assert show_result.exit_code == 0, show_result.output
        show_payload = json.loads(show_result.output)
        assert show_payload["focus_task"]["title"] == "Fresh Focus Task"
        assert show_payload["focus_task"]["current_progress_percent"] == 40
        assert show_payload["execution"]["in_progress_tasks"] == 1
        assert show_payload["execution"]["active_tasks"][0]["progress_percent"] == 40

        summary_result = cli_runner.invoke(
            cli,
            ["project", "summary", "Focus Freshness Project", "--format", "json"],
        )
        assert summary_result.exit_code == 0, summary_result.output
        summary_payload = json.loads(summary_result.output)
        assert summary_payload["focus_task"]["title"] == "Fresh Focus Task"
        assert summary_payload["focus_task"]["current_progress_percent"] == 40
        assert summary_payload["execution"]["in_progress_tasks"] == 1
        assert summary_payload["execution"]["active_tasks"][0]["progress_percent"] == 40
        assert summary_payload["project"]["status"] == "active"
        assert summary_payload["project"]["stored_status"] == "active"
        assert (
            summary_payload["project"]["last_activity_at"]
            == summary_payload["last_activity_at"]
        )
        assert (
            summary_payload["project"]["last_transition_at"]
            == summary_payload["last_transition_at"]
        )
        assert summary_payload["project"]["operator_category"] == "active_work"
        assert summary_payload["project"]["terminal_reason"] is None
        assert (
            summary_payload["project"]["focus_task"]["id"]
            == show_payload["focus_task"]["id"]
        )

    def test_project_show_and_summary_stats_match_execution_after_task_completion(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Project Stats Consistency"])
        first_task = cli_runner.invoke(
            cli,
            ["task", "add", "Project Stats Consistency", "Complete Me"],
        )
        second_task = cli_runner.invoke(
            cli,
            ["task", "add", "Project Stats Consistency", "Still Active"],
        )
        first_task_id = _extract_id(first_task.output)
        second_task_id = _extract_id(second_task.output)

        start_first = cli_runner.invoke(
            cli,
            [
                "task",
                "start",
                first_task_id,
                "--project",
                "Project Stats Consistency",
                "--by",
                "tester",
            ],
        )
        assert start_first.exit_code == 0, start_first.output
        start_second = cli_runner.invoke(
            cli,
            [
                "task",
                "start",
                second_task_id,
                "--project",
                "Project Stats Consistency",
                "--by",
                "tester",
            ],
        )
        assert start_second.exit_code == 0, start_second.output
        complete_result = cli_runner.invoke(
            cli,
            [
                "task",
                "complete",
                first_task_id,
                "--project",
                "Project Stats Consistency",
                "--by",
                "tester",
            ],
        )
        assert complete_result.exit_code == 0, complete_result.output

        show_result = cli_runner.invoke(
            cli,
            ["project", "show", "Project Stats Consistency", "--format", "json"],
        )
        assert show_result.exit_code == 0, show_result.output
        show_payload = json.loads(show_result.output)
        assert show_payload["stats"]["completed_tasks"] == 1
        assert show_payload["stats"]["in_progress_tasks"] == 1
        assert (
            show_payload["stats"]["completed_tasks"]
            == show_payload["execution"]["completed_tasks"]
        )
        assert (
            show_payload["stats"]["in_progress_tasks"]
            == show_payload["execution"]["in_progress_tasks"]
        )

        summary_result = cli_runner.invoke(
            cli,
            ["project", "summary", "Project Stats Consistency", "--format", "json"],
        )
        assert summary_result.exit_code == 0, summary_result.output
        summary_payload = json.loads(summary_result.output)
        assert summary_payload["stats"]["completed_tasks"] == 1
        assert summary_payload["stats"]["in_progress_tasks"] == 1
        assert (
            summary_payload["stats"]["completed_tasks"]
            == summary_payload["execution"]["completed_tasks"]
        )
        assert (
            summary_payload["stats"]["in_progress_tasks"]
            == summary_payload["execution"]["in_progress_tasks"]
        )

    def test_project_show_and_summary_reflect_latest_progress_when_progress_decreases(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Progress Decrease Project"])
        task_result = cli_runner.invoke(
            cli,
            ["task", "add", "Progress Decrease Project", "Progress Can Move Backward"],
        )
        task_id = _extract_id(task_result.output)

        start_result = cli_runner.invoke(
            cli,
            [
                "task",
                "start",
                task_id,
                "--project",
                "Progress Decrease Project",
                "--by",
                "tester",
            ],
        )
        assert start_result.exit_code == 0, start_result.output

        first_progress = cli_runner.invoke(
            cli,
            [
                "task",
                "progress",
                task_id,
                "--project",
                "Progress Decrease Project",
                "95",
                "Initial estimate",
                "--by",
                "tester",
            ],
        )
        assert first_progress.exit_code == 0, first_progress.output

        second_progress = cli_runner.invoke(
            cli,
            [
                "task",
                "progress",
                task_id,
                "--project",
                "Progress Decrease Project",
                "92",
                "Refined estimate",
                "--by",
                "tester",
            ],
        )
        assert second_progress.exit_code == 0, second_progress.output

        show_result = cli_runner.invoke(
            cli,
            ["project", "show", "Progress Decrease Project", "--format", "json"],
        )
        assert show_result.exit_code == 0, show_result.output
        show_payload = json.loads(show_result.output)
        assert show_payload["focus_task"]["current_progress_percent"] == 92
        assert show_payload["execution"]["active_tasks"][0]["progress_percent"] == 92

        summary_result = cli_runner.invoke(
            cli,
            ["project", "summary", "Progress Decrease Project", "--format", "json"],
        )
        assert summary_result.exit_code == 0, summary_result.output
        summary_payload = json.loads(summary_result.output)
        assert summary_payload["focus_task"]["current_progress_percent"] == 92
        assert summary_payload["execution"]["active_tasks"][0]["progress_percent"] == 92

    def test_plan_show_focus_task_reflects_latest_progress(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Plan Focus Freshness Project"])
        task_result = cli_runner.invoke(
            cli,
            ["task", "add", "Plan Focus Freshness Project", "Plan Focus Task"],
        )
        task_id = _extract_id(task_result.output)
        plan_result = cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Plan Focus Freshness Plan",
                "--project",
                "Plan Focus Freshness Project",
                "--status",
                "active",
                "--task-id",
                task_id,
                "--content",
                "{}",
                "--output-format",
                "json",
            ],
        )
        assert plan_result.exit_code == 0, plan_result.output
        plan_payload = json.loads(plan_result.output)
        plan_id = plan_payload["plan"]["id"]

        start_result = cli_runner.invoke(
            cli,
            [
                "task",
                "start",
                task_id,
                "--project",
                "Plan Focus Freshness Project",
                "--by",
                "tester",
            ],
        )
        assert start_result.exit_code == 0, start_result.output

        progress_result = cli_runner.invoke(
            cli,
            [
                "task",
                "progress",
                task_id,
                "--project",
                "Plan Focus Freshness Project",
                "40",
                "Made progress for plan readback",
                "--by",
                "tester",
            ],
        )
        assert progress_result.exit_code == 0, progress_result.output

        show_result = cli_runner.invoke(
            cli,
            ["plan", "show", plan_id, "--format", "json"],
        )
        assert show_result.exit_code == 0, show_result.output
        show_payload = json.loads(show_result.output)
        assert show_payload["focus_task"]["title"] == "Plan Focus Task"
        assert show_payload["focus_task"]["current_progress_percent"] == 40

    def test_task_start_fails_nonzero_when_draft_plan_locks_execution(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Draft Lock Project"])
        task_result = cli_runner.invoke(
            cli, ["task", "add", "Draft Lock Project", "Draft Locked Task"]
        )
        task_id = _extract_id(task_result.output)
        create_result = cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Draft Lock Plan",
                "--project",
                "Draft Lock Project",
                "--task-id",
                task_id,
                "--content",
                "{}",
            ],
        )

        result = cli_runner.invoke(
            cli,
            [
                "task",
                "start",
                task_id,
                "--project",
                "Draft Lock Project",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 1, result.output
        payload = json.loads(result.output)
        assert payload["error"]["code"] == "draft_plan_execution_locked"
        assert payload["blocking_plans"][0]["name"] == "Draft Lock Plan"

    def test_task_progress_fails_nonzero_when_draft_plan_locks_execution(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Draft Lock Progress Project"])
        task_result = cli_runner.invoke(
            cli,
            [
                "task",
                "add",
                "Draft Lock Progress Project",
                "Draft Locked Progress Task",
            ],
        )
        task_id = _extract_id(task_result.output)
        create_result = cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Draft Lock Progress Plan",
                "--project",
                "Draft Lock Progress Project",
                "--task-id",
                task_id,
                "--content",
                "{}",
            ],
        )

        result = cli_runner.invoke(
            cli,
            [
                "task",
                "progress",
                task_id,
                "--project",
                "Draft Lock Progress Project",
                "20",
                "blocked by draft plan",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 1, result.output
        payload = json.loads(result.output)
        assert payload["error"]["code"] == "draft_plan_execution_locked"
        assert payload["blocking_plans"][0]["name"] == "Draft Lock Progress Plan"

    def test_runtime_status_and_project_show_normalize_guidance_commands(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Normalized Guidance Project"])

        runtime_result = cli_runner.invoke(
            cli,
            ["runtime", "status", "--format", "json"],
        )
        assert runtime_result.exit_code == 0, runtime_result.output
        runtime_payload = json.loads(runtime_result.output)
        assert runtime_payload["next_steps"] == [
            _cli_step("runtime cleanup"),
            _cli_step("config show --format json"),
        ]

        project_show = cli_runner.invoke(
            cli,
            ["project", "show", "Normalized Guidance Project", "--format", "json"],
        )
        assert project_show.exit_code == 0, project_show.output
        project_payload = json.loads(project_show.output)
        assert project_payload["links"]["guide"] == _cli_step("start --format json")
        assert (
            _cli_step('project summary "Normalized Guidance Project"')
            in project_payload["next_steps"]
        )
        assert (
            _cli_step('task list --project "Normalized Guidance Project"')
            in project_payload["next_steps"]
        )

    def test_hierarchy_json_links_are_normalized(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["org", "create", "Hierarchy Org"])
        cli_runner.invoke(
            cli,
            ["portfolio", "create", "Hierarchy Portfolio", "--org", "Hierarchy Org"],
        )
        cli_runner.invoke(
            cli,
            [
                "program",
                "create",
                "Hierarchy Program",
                "--org",
                "Hierarchy Org",
                "--portfolio",
                "Hierarchy Portfolio",
            ],
        )

        portfolio_list = cli_runner.invoke(
            cli, ["portfolio", "list", "--format", "json"]
        )
        assert portfolio_list.exit_code == 0, portfolio_list.output
        portfolio_payload = json.loads(portfolio_list.output)
        portfolio_item = next(
            item
            for item in portfolio_payload["items"]
            if item["name"] == "Hierarchy Portfolio"
        )
        assert portfolio_item["links"]["self"].startswith(_cli_step("portfolio show "))
        assert portfolio_item["links"]["summary"].startswith(
            _cli_step("portfolio summary ")
        )

        program_list = cli_runner.invoke(cli, ["program", "list", "--format", "json"])
        assert program_list.exit_code == 0, program_list.output
        program_payload = json.loads(program_list.output)
        program_item = next(
            item
            for item in program_payload["items"]
            if item["name"] == "Hierarchy Program"
        )
        assert program_item["links"]["self"].startswith(_cli_step("program show "))
        assert program_item["links"]["summary"].startswith(
            _cli_step("program summary ")
        )

        program_show = cli_runner.invoke(
            cli, ["program", "show", "Hierarchy Program", "--format", "json"]
        )
        assert program_show.exit_code == 0, program_show.output
        show_payload = json.loads(program_show.output)
        assert show_payload["links"]["self"].startswith(_cli_step("program show "))
        assert show_payload["links"]["summary"].startswith(
            _cli_step("program summary ")
        )

    def test_project_summary_json_surfaces_focus_task(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Project summary JSON should surface the next incomplete task."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Summary Focus Project"])
        cli_runner.invoke(
            cli, ["task", "add", "Summary Focus Project", "Ready Follow-up"]
        )
        review_result = cli_runner.invoke(
            cli, ["task", "add", "Summary Focus Project", "Review Task"]
        )
        review_task_id = _extract_id(review_result.output)
        cli_runner.invoke(cli, ["task", "start", review_task_id, "--by", "tester"])
        cli_runner.invoke(
            cli,
            [
                "task",
                "review",
                review_task_id,
                "--by",
                "tester",
            ],
        )

        summary_json = cli_runner.invoke(
            cli,
            ["project", "summary", "Summary Focus Project", "--format", "json"],
        )

        assert summary_json.exit_code == 0, summary_json.output
        payload = json.loads(summary_json.output)
        assert payload["links"]["self"] == _cli_step(
            'project summary "Summary Focus Project"'
        )
        assert payload["links"]["show"] == _cli_step(
            'project show "Summary Focus Project"'
        )
        assert payload["links"]["tasks"] == _cli_step(
            'task list --project "Summary Focus Project"'
        )
        assert payload["links"]["snapshot"] == _cli_step(
            'work snapshot --scope-type project --scope "Summary Focus Project"'
        )
        assert payload["links"]["daily"] == _cli_step(
            'work daily --scope-type project --scope "Summary Focus Project"'
        )
        assert payload["focus_task"]["title"] == "Review Task"
        assert payload["focus_task"]["status"] == "in_review"
        assert payload["next_steps"][0].startswith(_cli_step("task complete "))

    def test_project_summary_and_dashboard_use_effective_goal_rollups(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Project Rollup Truth"])
        cli_runner.invoke(
            cli,
            [
                "goal",
                "create",
                "Project Rollup Goal",
                "--project",
                "Project Rollup Truth",
                "--progress",
                "10",
            ],
        )
        task_id = _extract_id(
            cli_runner.invoke(
                cli, ["task", "add", "Project Rollup Truth", "Execution Task"]
            ).output
        )
        cli_runner.invoke(cli, ["task", "start", task_id, "--by", "tester"])
        cli_runner.invoke(
            cli,
            [
                "task",
                "progress",
                task_id,
                "45",
                "Implementing",
                "--by",
                "tester",
            ],
        )

        summary_json = cli_runner.invoke(
            cli,
            ["project", "summary", "Project Rollup Truth", "--format", "json"],
        )
        assert summary_json.exit_code == 0, summary_json.output
        summary_payload = json.loads(summary_json.output)
        assert summary_payload["stats"]["total_goals"] == 1
        assert summary_payload["stats"]["completed_goals"] == 0
        assert summary_payload["stats"]["avg_goal_progress"] == 45

        dashboard_json = cli_runner.invoke(cli, ["dashboard", "--format", "json"])
        assert dashboard_json.exit_code == 0, dashboard_json.output
        dashboard_payload = json.loads(dashboard_json.output)
        assert (
            dashboard_payload["goal_horizon_stats"]["short_term"]["avg_progress"] == 45
        )
        assert (
            dashboard_payload["goal_horizon_stats_population"]
            == "all_non_archived_retained"
        )
        assert (
            dashboard_payload["visible_goal_horizon_stats_population"]
            == "visible_operator"
        )
        assert (
            dashboard_payload["visible_goal_horizon_stats"]["short_term"][
                "avg_progress"
            ]
            == 45
        )

    def test_dashboard_goal_horizon_stats_separate_visible_and_instance_populations(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Visible Horizon Project"])
        visible_goal = cli_runner.invoke(
            cli,
            [
                "goal",
                "create",
                "Visible Horizon Goal",
                "--project",
                "Visible Horizon Project",
                "--horizon",
                "short_term",
                "--progress",
                "40",
            ],
        )
        visible_goal_id = _extract_id(visible_goal.output)

        cli_runner.invoke(cli, ["project", "create", "Audit Project hidden-horizon"])
        hidden_goal = cli_runner.invoke(
            cli,
            [
                "goal",
                "create",
                "Hidden Horizon Goal",
                "--project",
                "Audit Project hidden-horizon",
                "--horizon",
                "short_term",
                "--progress",
                "100",
            ],
        )
        _extract_id(hidden_goal.output)

        dashboard_json = cli_runner.invoke(cli, ["dashboard", "--format", "json"])
        assert dashboard_json.exit_code == 0, dashboard_json.output
        dashboard_payload = json.loads(dashboard_json.output)

        assert (
            dashboard_payload["goal_horizon_stats_population"]
            == "all_non_archived_retained"
        )
        assert (
            dashboard_payload["visible_goal_horizon_stats_population"]
            == "visible_operator"
        )
        assert (
            dashboard_payload["visible_goal_horizon_stats"]["short_term"]["total_goals"]
            == 1
        )
        assert (
            dashboard_payload["visible_goal_horizon_stats"]["short_term"][
                "avg_progress"
            ]
            == 40
        )
        assert dashboard_payload["goal_horizon_stats"]["short_term"]["total_goals"] >= 2

    def test_portfolio_program_and_org_summaries_use_effective_goal_rollups(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["org", "create", "Rollup Org"])
        cli_runner.invoke(
            cli, ["portfolio", "create", "Rollup Portfolio", "--org", "Rollup Org"]
        )
        cli_runner.invoke(
            cli,
            [
                "program",
                "create",
                "Rollup Program",
                "--org",
                "Rollup Org",
                "--portfolio",
                "Rollup Portfolio",
            ],
        )
        cli_runner.invoke(
            cli,
            [
                "project",
                "create",
                "Rollup Project",
                "--org",
                "Rollup Org",
                "--portfolio",
                "Rollup Portfolio",
                "--program",
                "Rollup Program",
            ],
        )
        cli_runner.invoke(
            cli,
            [
                "goal",
                "create",
                "Rollup Goal",
                "--project",
                "Rollup Project",
                "--progress",
                "10",
            ],
        )
        task_id = _extract_id(
            cli_runner.invoke(
                cli, ["task", "add", "Rollup Project", "Execution Task"]
            ).output
        )
        cli_runner.invoke(cli, ["task", "start", task_id, "--by", "tester"])
        cli_runner.invoke(
            cli,
            [
                "task",
                "progress",
                task_id,
                "45",
                "Implementing",
                "--by",
                "tester",
            ],
        )

        portfolio_json = cli_runner.invoke(
            cli, ["portfolio", "summary", "Rollup Portfolio", "--format", "json"]
        )
        assert portfolio_json.exit_code == 0, portfolio_json.output
        assert json.loads(portfolio_json.output)["stats"]["avg_goal_progress"] == 45

        program_json = cli_runner.invoke(
            cli, ["program", "summary", "Rollup Program", "--format", "json"]
        )
        assert program_json.exit_code == 0, program_json.output
        assert json.loads(program_json.output)["stats"]["avg_goal_progress"] == 45

        org_json = cli_runner.invoke(
            cli, ["org", "summary", "Rollup Org", "--format", "json"]
        )
        assert org_json.exit_code == 0, org_json.output
        assert json.loads(org_json.output)["stats"]["avg_goal_progress"] == 45

    def test_quickstart_defaults(self, cli_runner: CliRunner, temp_env: Path):
        """Quickstart should create baseline entities."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        result = cli_runner.invoke(cli, ["quickstart", "--defaults"])
        assert result.exit_code == 0

        list_json = cli_runner.invoke(
            cli, ["project", "list", "--include-generated", "--format", "json"]
        )
        assert list_json.exit_code == 0
        payload = json.loads(list_json.output)
        assert any(item["name"] == "Quickstart Project" for item in payload["items"])
        assert "links" in payload
        assert payload["links"]["guide"] == _cli_step("start --format json")
        assert "next_steps" in payload
        assert "params" in payload

    def test_quickstart_json_includes_artifacts_and_next_steps(
        self, cli_runner: CliRunner, temp_env: Path
    ):
        """Quickstart JSON should expose created artifacts and guided continuation."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        result = cli_runner.invoke(
            cli, ["quickstart", "--defaults", "--format", "json"]
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["purpose"].startswith("Bootstrap PMS with a usable workspace")
        assert payload["fastest_start"] == _cli_step("quickstart --defaults")
        assert payload["artifacts_created"]["project"]["name"] == "Quickstart Project"
        assert len(payload["artifacts_created"]["tasks"]) == 3
        assert payload["artifacts_created"]["plan"]["name"] == "Quickstart Project Plan"
        assert payload["links"]["guide"] == _cli_step("start --format json")
        assert payload["next_steps"][0] == _cli_step(
            'project show "Quickstart Project"'
        )

    def test_quickstart_reuses_bootstrap_plan_and_tasks(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Repeated quickstart should reuse generated bootstrap artifacts."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        first = cli_runner.invoke(cli, ["quickstart", "--defaults", "--format", "json"])
        second = cli_runner.invoke(
            cli, ["quickstart", "--defaults", "--format", "json"]
        )

        assert first.exit_code == 0
        assert second.exit_code == 0

        first_payload = json.loads(first.output)
        second_payload = json.loads(second.output)

        assert first_payload["artifacts_created"]["plan"]["reused_existing"] is False
        assert second_payload["artifacts_created"]["plan"]["reused_existing"] is True
        assert (
            first_payload["artifacts_created"]["plan"]["id"]
            == second_payload["artifacts_created"]["plan"]["id"]
        )
        assert [task["id"] for task in first_payload["artifacts_created"]["tasks"]] == [
            task["id"] for task in second_payload["artifacts_created"]["tasks"]
        ]

        plans_result = cli_runner.invoke(
            cli, ["plan", "list", "--include-generated", "--format", "json"]
        )
        assert plans_result.exit_code == 0
        plans_payload = json.loads(plans_result.output)
        live_quickstart_plans = [
            item
            for item in plans_payload["items"]
            if item["name"] == "Quickstart Project Plan"
            and item["status"] != "archived"
        ]
        assert len(live_quickstart_plans) == 1

    def test_quickstart_links_existing_rollups_via_project_scope_updates(
        self,
        cli_runner: CliRunner,
        temp_env: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Quickstart should link existing rollups by updating project scope."""
        from pms.config.settings import reload_settings
        from pms.services.portfolio_service import PortfolioService
        from pms.services.program_service import ProgramService

        reload_settings()

        cli_runner.invoke(cli, ["init"])

        for command in (
            ["org", "create", "Quickstart Org"],
            ["product", "create", "Quickstart Product"],
            ["project", "create", "Quickstart Project"],
            ["portfolio", "create", "Quickstart Portfolio", "--org", "Quickstart Org"],
            [
                "program",
                "create",
                "Quickstart Program",
                "--org",
                "Quickstart Org",
                "--portfolio",
                "Quickstart Portfolio",
            ],
        ):
            result = cli_runner.invoke(cli, command)
            assert result.exit_code == 0, result.output

        async def _unexpected_portfolio_update(self, *args, **kwargs):
            raise AssertionError(
                "quickstart should not use portfolio.update_portfolio for project linking"
            )

        async def _unexpected_program_update(self, *args, **kwargs):
            raise AssertionError(
                "quickstart should not use program.update_program for project linking"
            )

        monkeypatch.setattr(
            PortfolioService,
            "update_portfolio",
            _unexpected_portfolio_update,
        )
        monkeypatch.setattr(
            ProgramService,
            "update_program",
            _unexpected_program_update,
        )

        result = cli_runner.invoke(
            cli, ["quickstart", "--defaults", "--format", "json"]
        )
        assert result.exit_code == 0, result.output

        project_result = cli_runner.invoke(
            cli, ["project", "show", "Quickstart Project", "--format", "json"]
        )
        assert project_result.exit_code == 0, project_result.output
        project_payload = json.loads(project_result.output)
        assert project_payload["portfolio_name"] == "Quickstart Portfolio"
        assert project_payload["program_name"] == "Quickstart Program"

    def test_loop_setup_defaults(self, cli_runner: CliRunner, temp_env: Path):
        """Loop setup should create prompt/config files."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])

        config_path = temp_env / "pms-loop.yml"
        prompt_path = temp_env / "PROMPT.md"

        result = cli_runner.invoke(
            cli,
            [
                "loop",
                "setup",
                "--defaults",
                "--config",
                str(config_path),
                "--prompt-file",
                str(prompt_path),
            ],
        )

        assert result.exit_code == 0
        assert config_path.exists()
        assert prompt_path.exists()

    def test_loop_setup_retries_invalid_dependency_task_number_and_persists_dependency(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Loop setup should keep the wizard alive until dependency task selection is valid."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])

        config_path = temp_env / "pms-loop.yml"
        prompt_path = temp_env / "PROMPT.md"
        wizard_input = "\n".join(
            [
                "Loop Org",
                "Loop Product",
                "Loop Project",
                "Ship MVP",
                "Acceptance criteria",
                "criterion one",
                "",
                "Task A",
                "Task B",
                "",
                "desc A",
                "1",
                "n",
                "desc B",
                "1",
                "n",
                "y",
                "abc",
                "2",
                "1",
                "blocks",
                "",
                "n",
                "",
            ]
        )

        result = cli_runner.invoke(
            cli,
            [
                "loop",
                "setup",
                "--config",
                str(config_path),
                "--prompt-file",
                str(prompt_path),
            ],
            input=wizard_input,
        )

        assert result.exit_code == 0, result.output
        _assert_plain_output_contains(
            result.output, "Enter a task number", "Created plan: Loop Project Plan"
        )

        plan_list = cli_runner.invoke(cli, ["plan", "list", "--format", "json"])
        assert plan_list.exit_code == 0, plan_list.output
        plan_id = json.loads(plan_list.output)["items"][0]["id"]

        plan_show = cli_runner.invoke(
            cli, ["plan", "show", plan_id, "--format", "json"]
        )
        assert plan_show.exit_code == 0, plan_show.output
        plan_payload = json.loads(plan_show.output)
        plan_content = json.loads(plan_payload["content"])

        assert plan_content["dependencies"] == [
            {
                "depends_on_id": plan_content["tasks"][0]["id"],
                "depends_on_title": "Task A",
                "task_id": plan_content["tasks"][1]["id"],
                "task_title": "Task B",
                "type": "blocks",
            }
        ]

    def test_loop_setup_retries_out_of_range_dependency_task_number_until_valid(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Loop setup should reject out-of-range task numbers and continue prompting."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])

        config_path = temp_env / "pms-loop.yml"
        prompt_path = temp_env / "PROMPT.md"
        wizard_input = "\n".join(
            [
                "Loop Org",
                "Loop Product",
                "Loop Project",
                "Ship MVP",
                "Acceptance criteria",
                "criterion one",
                "",
                "Task A",
                "Task B",
                "",
                "desc A",
                "1",
                "n",
                "desc B",
                "1",
                "n",
                "y",
                "9",
                "2",
                "1",
                "blocks",
                "",
                "n",
                "",
            ]
        )

        result = cli_runner.invoke(
            cli,
            [
                "loop",
                "setup",
                "--config",
                str(config_path),
                "--prompt-file",
                str(prompt_path),
            ],
            input=wizard_input,
        )

        assert result.exit_code == 0, result.output
        _assert_plain_output_contains(
            result.output, "Invalid task number", "Created plan: Loop Project Plan"
        )

    def test_task_show_pick_retries_invalid_selection_and_returns_chosen_task(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Interactive `--pick` selection should retry after invalid choice and still resolve the chosen task."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Pick Project"])

        first_task = cli_runner.invoke(
            cli, ["task", "create", "Pick Project", "Duplicate Task"]
        )
        assert first_task.exit_code == 0, first_task.output

        second_task = cli_runner.invoke(
            cli, ["task", "create", "Pick Project", "Duplicate Task"]
        )
        assert second_task.exit_code == 0, second_task.output
        second_task_id = _extract_id(second_task.output)

        start_second = cli_runner.invoke(
            cli,
            [
                "task",
                "start",
                second_task_id,
                "--project",
                "Pick Project",
                "--by",
                "tester",
            ],
        )
        assert start_second.exit_code == 0, start_second.output

        result = cli_runner.invoke(
            cli,
            ["task", "show", "Duplicate Task", "--project", "Pick Project", "--pick"],
            input="9\n2\n",
        )

        assert result.exit_code == 0, result.output
        _assert_plain_output_contains(
            result.output,
            "Matching Tasks",
            "Error: 9 is not in the range 1<=x<=2.",
            "Duplicate Task",
            "Project: Pick Project",
            "Status: todo",
            "Next:",
        )

    def test_goal_summary_pick_retries_invalid_selection_and_returns_chosen_goal(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Goal chooser retries should stay in-place and resolve the selected duplicate goal."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Pick Project"])

        first_goal = cli_runner.invoke(
            cli, ["goal", "create", "Duplicate Goal", "--project", "Pick Project"]
        )
        assert first_goal.exit_code == 0, first_goal.output
        first_goal_id = _extract_id(first_goal.output)

        second_goal = cli_runner.invoke(
            cli, ["goal", "create", "Duplicate Goal", "--project", "Pick Project"]
        )
        assert second_goal.exit_code == 0, second_goal.output

        complete_first = cli_runner.invoke(cli, ["goal", "complete", first_goal_id])
        assert complete_first.exit_code == 0, complete_first.output

        result = cli_runner.invoke(
            cli,
            ["goal", "summary", "Duplicate Goal", "--pick"],
            input="9\n2\n",
        )

        assert result.exit_code == 0, result.output
        _assert_plain_output_contains(
            result.output,
            "Matching Goals",
            "Error: 9 is not in the range 1<=x<=2.",
            "Goal State: active | Progress: 0%",
        )

    def test_plan_show_pick_retries_invalid_selection_and_returns_chosen_plan(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Plan chooser retries should stay in-place and resolve the selected duplicate plan."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Pick Project"])

        first_plan = cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Duplicate Plan",
                "--project",
                "Pick Project",
                "--content",
                "{}",
                "--output-format",
                "json",
            ],
        )
        assert first_plan.exit_code == 0, first_plan.output

        second_plan = cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Duplicate Plan",
                "--project",
                "Pick Project",
                "--content",
                "{}",
                "--output-format",
                "json",
            ],
        )
        assert second_plan.exit_code == 0, second_plan.output

        result = cli_runner.invoke(
            cli,
            ["plan", "show", "Duplicate Plan", "--project", "Pick Project", "--pick"],
            input="9\n2\n",
        )

        assert result.exit_code == 0, result.output
        _assert_plain_output_contains(
            result.output,
            "Matching Plans",
            "Error: 9 is not in the range 1<=x<=2.",
            "Duplicate Plan",
            "Status: draft",
            "Content:",
        )

    def test_objective_show_pick_retries_invalid_selection_and_returns_chosen_objective(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Objective chooser retries should stay in-place and resolve the selected duplicate objective."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Pick Project"])
        cli_runner.invoke(
            cli, ["goal", "create", "Goal A", "--project", "Pick Project"]
        )

        first_objective = cli_runner.invoke(
            cli, ["objective", "create", "Duplicate Objective", "--goal", "Goal A"]
        )
        assert first_objective.exit_code == 0, first_objective.output
        first_objective_id = _extract_id(first_objective.output)

        second_objective = cli_runner.invoke(
            cli, ["objective", "create", "Duplicate Objective", "--goal", "Goal A"]
        )
        assert second_objective.exit_code == 0, second_objective.output

        complete_first = cli_runner.invoke(
            cli, ["objective", "complete", first_objective_id, "--goal", "Goal A"]
        )
        assert complete_first.exit_code == 0, complete_first.output

        result = cli_runner.invoke(
            cli,
            ["objective", "show", "Duplicate Objective", "--goal", "Goal A", "--pick"],
            input="9\n2\n",
        )

        assert result.exit_code == 0, result.output
        _assert_plain_output_contains(
            result.output,
            "Matching Objectives",
            "Error: 9 is not in the range 1<=x<=2.",
            "Duplicate Objective",
            "Status: active",
            "Goal: Goal A",
        )

    def test_keyresult_show_pick_retries_invalid_selection_and_returns_chosen_key_result(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Key-result chooser retries should stay in-place and resolve the selected duplicate key result."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Pick Project"])
        cli_runner.invoke(
            cli, ["goal", "create", "Goal A", "--project", "Pick Project"]
        )
        cli_runner.invoke(cli, ["objective", "create", "KR Parent", "--goal", "Goal A"])

        first_key_result = cli_runner.invoke(
            cli,
            [
                "keyresult",
                "create",
                "Duplicate KR",
                "--objective",
                "KR Parent",
                "--goal",
                "Goal A",
            ],
        )
        assert first_key_result.exit_code == 0, first_key_result.output
        first_key_result_id = _extract_id(first_key_result.output)

        second_key_result = cli_runner.invoke(
            cli,
            [
                "keyresult",
                "create",
                "Duplicate KR",
                "--objective",
                "KR Parent",
                "--goal",
                "Goal A",
            ],
        )
        assert second_key_result.exit_code == 0, second_key_result.output

        complete_first = cli_runner.invoke(
            cli,
            [
                "keyresult",
                "complete",
                first_key_result_id,
                "--objective",
                "KR Parent",
                "--goal",
                "Goal A",
            ],
        )
        assert complete_first.exit_code == 0, complete_first.output

        result = cli_runner.invoke(
            cli,
            [
                "keyresult",
                "show",
                "Duplicate KR",
                "--objective",
                "KR Parent",
                "--goal",
                "Goal A",
                "--pick",
            ],
            input="9\n2\n",
        )

        assert result.exit_code == 0, result.output
        _assert_plain_output_contains(
            result.output,
            "Matching Key Results",
            "Error: 9 is not in the range 1<=x<=2.",
            "Duplicate KR",
            "Status: active",
            "Objective: KR Parent",
        )

    def test_product_show_formats(self, cli_runner: CliRunner, temp_env: Path):
        """Test product show json/csv outputs."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        create = cli_runner.invoke(cli, ["product", "create", "Show Product"])
        product_id = _extract_id(create.output)

        show_json = cli_runner.invoke(
            cli,
            ["product", "show", product_id, "--format", "json"],
        )
        assert show_json.exit_code == 0
        payload = json.loads(show_json.output)
        assert payload["links"]["self"].startswith(_cli_step("product show "))
        assert payload["links"]["summary"].startswith(_cli_step("product summary "))
        assert payload["next_steps"][0].startswith(_cli_step("product summary "))

        show_csv = cli_runner.invoke(
            cli,
            ["product", "show", product_id, "--format", "csv"],
        )
        assert show_csv.exit_code == 0
        assert "id,name,status" in show_csv.output.splitlines()[0]

    def test_project_history_formats(self, cli_runner: CliRunner, temp_env: Path):
        """Test project history json/csv outputs."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "History Project"])

        history_json = cli_runner.invoke(
            cli,
            ["project", "history", "History Project", "--format", "json"],
        )
        assert history_json.exit_code == 0
        assert history_json.output.strip().startswith("[")

        history_csv = cli_runner.invoke(
            cli,
            ["project", "history", "History Project", "--format", "csv"],
        )
        assert history_csv.exit_code == 0
        assert "revision_number,change_type" in history_csv.output.splitlines()[0]

    def test_product_summary_formats(self, cli_runner: CliRunner, temp_env: Path):
        """Test product summary json/csv outputs."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        create = cli_runner.invoke(cli, ["product", "create", "Summary Product"])
        product_id = _extract_id(create.output)

        summary_json = cli_runner.invoke(
            cli,
            ["product", "summary", product_id, "--format", "json"],
        )
        assert summary_json.exit_code == 0
        payload = json.loads(summary_json.output)
        assert payload["links"]["self"].startswith(_cli_step("product summary "))
        assert payload["links"]["show"].startswith(_cli_step("product show "))
        assert payload["links"]["projects"].startswith(
            _cli_step("project list --product ")
        )
        assert payload["next_steps"][0].startswith(_cli_step("product show "))

        summary_csv = cli_runner.invoke(
            cli,
            ["product", "summary", product_id, "--format", "csv"],
        )
        assert summary_csv.exit_code == 0
        assert (
            "product_id,product_name,health_score" in summary_csv.output.splitlines()[0]
        )

    def test_org_portfolio_program_summaries_expose_links_and_next_steps(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["org", "create", "Summary Org"])
        cli_runner.invoke(
            cli, ["portfolio", "create", "Summary Portfolio", "--org", "Summary Org"]
        )
        cli_runner.invoke(
            cli,
            [
                "program",
                "create",
                "Summary Program",
                "--org",
                "Summary Org",
                "--portfolio",
                "Summary Portfolio",
            ],
        )

        org_json = cli_runner.invoke(
            cli, ["org", "summary", "Summary Org", "--format", "json"]
        )
        assert org_json.exit_code == 0, org_json.output
        org_payload = json.loads(org_json.output)
        assert org_payload["links"]["self"].startswith(_cli_step("org summary "))
        assert org_payload["next_steps"][0].startswith(
            _cli_step('org show "Summary Org"')
        )

        portfolio_json = cli_runner.invoke(
            cli, ["portfolio", "summary", "Summary Portfolio", "--format", "json"]
        )
        assert portfolio_json.exit_code == 0, portfolio_json.output
        portfolio_payload = json.loads(portfolio_json.output)
        assert portfolio_payload["links"]["self"].startswith(
            _cli_step("portfolio summary ")
        )
        assert portfolio_payload["next_steps"][0].startswith(
            _cli_step('portfolio show "Summary Portfolio"')
        )

        program_json = cli_runner.invoke(
            cli, ["program", "summary", "Summary Program", "--format", "json"]
        )
        assert program_json.exit_code == 0, program_json.output
        program_payload = json.loads(program_json.output)
        assert program_payload["links"]["self"].startswith(
            _cli_step("program summary ")
        )
        assert program_payload["next_steps"][0].startswith(
            _cli_step('program show "Summary Program"')
        )

    def test_portfolio_and_program_readbacks_ignore_stale_cached_child_arrays(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Portfolio/program show and summary should derive hierarchy from graph edges."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["org", "create", "Authority Org"])
        cli_runner.invoke(
            cli,
            ["portfolio", "create", "Authority Portfolio", "--org", "Authority Org"],
        )
        cli_runner.invoke(
            cli,
            [
                "program",
                "create",
                "Authority Program",
                "--org",
                "Authority Org",
                "--portfolio",
                "Authority Portfolio",
            ],
        )
        project_create = cli_runner.invoke(
            cli,
            [
                "project",
                "create",
                "Authority Project",
                "--org",
                "Authority Org",
                "--portfolio",
                "Authority Portfolio",
                "--program",
                "Authority Program",
            ],
        )
        assert project_create.exit_code == 0, project_create.output
        project_id = _extract_id(project_create.output)

        goal_create = cli_runner.invoke(
            cli,
            ["goal", "create", "Authority Goal", "--project", "Authority Project"],
        )
        assert goal_create.exit_code == 0, goal_create.output
        goal_id = _extract_id(goal_create.output)

        objective_create = cli_runner.invoke(
            cli,
            ["objective", "create", "Authority Objective", "--goal", "Authority Goal"],
        )
        assert objective_create.exit_code == 0, objective_create.output
        objective_id = _extract_id(objective_create.output)

        portfolio_show_initial = cli_runner.invoke(
            cli, ["portfolio", "show", "Authority Portfolio", "--format", "json"]
        )
        assert portfolio_show_initial.exit_code == 0, portfolio_show_initial.output
        portfolio_id = json.loads(portfolio_show_initial.output)["id"]

        program_show_initial = cli_runner.invoke(
            cli, ["program", "show", "Authority Program", "--format", "json"]
        )
        assert program_show_initial.exit_code == 0, program_show_initial.output
        program_id = json.loads(program_show_initial.output)["id"]

        with sqlite3.connect(os.environ["PMS_DATABASE_PATH"]) as conn:
            portfolio_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(portfolios)")
            }
            assert "project_ids" not in portfolio_columns
            assert "goal_ids" not in portfolio_columns
            assert "objective_ids" not in portfolio_columns

            program_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(programs)")
            }
            assert "project_ids" not in program_columns
            assert "goal_ids" not in program_columns
            assert "objective_ids" not in program_columns

        portfolio_show = cli_runner.invoke(
            cli,
            [
                "portfolio",
                "show",
                "Authority Portfolio",
                "--include-linked",
                "--format",
                "json",
            ],
        )
        assert portfolio_show.exit_code == 0, portfolio_show.output
        portfolio_payload = json.loads(portfolio_show.output)
        assert portfolio_payload["project_ids"] == [project_id]
        assert portfolio_payload["goal_ids"] == []
        assert portfolio_payload["objective_ids"] == []
        assert portfolio_payload["effective_goal_ids"] == [goal_id]
        assert portfolio_payload["effective_objective_ids"] == [objective_id]
        assert portfolio_payload["linked"]["projects"][0]["id"] == project_id
        assert portfolio_payload["linked"]["goals"][0]["id"] == goal_id
        assert portfolio_payload["linked"]["objectives"][0]["id"] == objective_id

        program_show = cli_runner.invoke(
            cli,
            [
                "program",
                "show",
                "Authority Program",
                "--include-linked",
                "--format",
                "json",
            ],
        )
        assert program_show.exit_code == 0, program_show.output
        program_payload = json.loads(program_show.output)
        assert program_payload["project_ids"] == [project_id]
        assert program_payload["goal_ids"] == []
        assert program_payload["objective_ids"] == []
        assert program_payload["effective_goal_ids"] == [goal_id]
        assert program_payload["effective_objective_ids"] == [objective_id]
        assert program_payload["linked"]["projects"][0]["id"] == project_id
        assert program_payload["linked"]["goals"][0]["id"] == goal_id
        assert program_payload["linked"]["objectives"][0]["id"] == objective_id

        portfolio_summary = cli_runner.invoke(
            cli, ["portfolio", "summary", "Authority Portfolio", "--format", "json"]
        )
        assert portfolio_summary.exit_code == 0, portfolio_summary.output
        portfolio_summary_payload = json.loads(portfolio_summary.output)
        assert portfolio_summary_payload["stats"]["total_projects"] == 1
        assert portfolio_summary_payload["stats"]["total_goals"] == 1
        assert portfolio_summary_payload["stats"]["total_objectives"] == 1
        assert portfolio_summary_payload["portfolio"]["project_ids"] == [project_id]
        assert portfolio_summary_payload["portfolio"]["goal_ids"] == []
        assert portfolio_summary_payload["portfolio"]["objective_ids"] == []
        assert portfolio_summary_payload["portfolio"]["effective_goal_ids"] == [goal_id]
        assert portfolio_summary_payload["portfolio"]["effective_objective_ids"] == [
            objective_id
        ]

        program_summary = cli_runner.invoke(
            cli, ["program", "summary", "Authority Program", "--format", "json"]
        )
        assert program_summary.exit_code == 0, program_summary.output
        program_summary_payload = json.loads(program_summary.output)
        assert program_summary_payload["stats"]["total_projects"] == 1
        assert program_summary_payload["stats"]["total_goals"] == 1
        assert program_summary_payload["stats"]["total_objectives"] == 1
        assert program_summary_payload["program"]["project_ids"] == [project_id]
        assert program_summary_payload["program"]["goal_ids"] == []
        assert program_summary_payload["program"]["objective_ids"] == []
        assert program_summary_payload["program"]["effective_goal_ids"] == [goal_id]
        assert program_summary_payload["program"]["effective_objective_ids"] == [
            objective_id
        ]

    def test_portfolio_and_program_json_readbacks_expose_direct_and_effective_links(
        self, cli_runner: CliRunner, temp_env: Path
    ):
        """Portfolio/program JSON should separate direct strategic links from effective scope."""
        from pms.config.settings import reload_settings

        reload_settings()

        org_create = cli_runner.invoke(
            cli, ["org", "create", "Direct Link CLI Org", "--format", "json"]
        )
        assert org_create.exit_code == 0, org_create.output

        project_create = cli_runner.invoke(
            cli,
            [
                "project",
                "create",
                "Direct Link CLI Project",
                "--org",
                "Direct Link CLI Org",
                "--format",
                "json",
            ],
        )
        assert project_create.exit_code == 0, project_create.output

        goal_create = cli_runner.invoke(
            cli,
            [
                "goal",
                "create",
                "Direct Link CLI Goal",
                "--project",
                "Direct Link CLI Project",
                "--format",
                "json",
            ],
        )
        assert goal_create.exit_code == 0, goal_create.output
        goal_id = json.loads(goal_create.output)["goal"]["id"]

        objective_create = cli_runner.invoke(
            cli,
            [
                "objective",
                "create",
                "Direct Link CLI Objective",
                "--goal",
                "Direct Link CLI Goal",
                "--format",
                "json",
            ],
        )
        assert objective_create.exit_code == 0, objective_create.output
        objective_id = json.loads(objective_create.output)["objective"]["id"]

        portfolio_create = cli_runner.invoke(
            cli,
            [
                "portfolio",
                "create",
                "Direct Link CLI Portfolio",
                "--org",
                "Direct Link CLI Org",
                "--goal-id",
                goal_id,
                "--objective-id",
                objective_id,
                "--format",
                "json",
            ],
        )
        assert portfolio_create.exit_code == 0, portfolio_create.output
        portfolio_payload = json.loads(portfolio_create.output)["portfolio"]
        assert portfolio_payload["project_ids"] == []
        assert portfolio_payload["goal_ids"] == [goal_id]
        assert portfolio_payload["objective_ids"] == [objective_id]
        assert portfolio_payload["effective_goal_ids"] == [goal_id]
        assert portfolio_payload["effective_objective_ids"] == [objective_id]

        program_create = cli_runner.invoke(
            cli,
            [
                "program",
                "create",
                "Direct Link CLI Program",
                "--org",
                "Direct Link CLI Org",
                "--portfolio",
                "Direct Link CLI Portfolio",
                "--goal-id",
                goal_id,
                "--objective-id",
                objective_id,
                "--format",
                "json",
            ],
        )
        assert program_create.exit_code == 0, program_create.output
        program_payload = json.loads(program_create.output)["program"]
        assert program_payload["project_ids"] == []
        assert program_payload["goal_ids"] == [goal_id]
        assert program_payload["objective_ids"] == [objective_id]
        assert program_payload["effective_goal_ids"] == [goal_id]
        assert program_payload["effective_objective_ids"] == [objective_id]


class TestTaskCommands:
    """Tests for task commands."""

    def test_task_add(self, cli_runner: CliRunner, temp_env: Path):
        """Test adding a task."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Task Project"])

        result = cli_runner.invoke(
            cli,
            [
                "task",
                "add",
                "Task Project",
                "New Task",
                "-d",
                "Task description",
                "-p",
                "high",
                "-c",
                "40",
            ],
        )

        assert result.exit_code == 0
        _assert_plain_output_contains(result.output, "Created task", "New Task")

    def test_task_create_alias(self, cli_runner: CliRunner, temp_env: Path):
        """Test task create alias."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Alias Task Project"])

        result = cli_runner.invoke(
            cli,
            [
                "task",
                "create",
                "Alias Task Project",
                "Alias Task",
                "-d",
                "Alias task description",
            ],
        )

        assert result.exit_code == 0
        _assert_plain_output_contains(result.output, "Created task", "Alias Task")

    def test_task_add_with_project_id(self, cli_runner: CliRunner, temp_env: Path):
        """Test adding a task using a project ID."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        project_result = cli_runner.invoke(cli, ["project", "create", "ID Project"])
        project_id = _extract_id(project_result.output)

        result = cli_runner.invoke(
            cli,
            [
                "task",
                "add",
                project_id,
                "ID Task",
                "-d",
                "Task via project id",
            ],
        )

        assert result.exit_code == 0
        _assert_plain_output_contains(result.output, "Created task", "ID Task")

    def test_task_tree_group_project_defaults_to_dependency_descriptions(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Tree Description Project"])
        blocker_result = cli_runner.invoke(
            cli,
            [
                "task",
                "add",
                "Tree Description Project",
                "Prepare blocker",
                "--description",
                "Long blocker body\nwith enough detail for an agent.",
            ],
        )
        blocked_result = cli_runner.invoke(
            cli,
            [
                "task",
                "add",
                "Tree Description Project",
                "Run blocked task",
                "--description",
                "Long blocked body\nwith downstream instructions.",
            ],
        )
        blocker_id = _extract_id(blocker_result.output)
        blocked_id = _extract_id(blocked_result.output)
        dep_result = cli_runner.invoke(
            cli,
            ["task", "dep", "add", blocked_id, blocker_id],
        )
        assert dep_result.exit_code == 0, dep_result.output

        result = cli_runner.invoke(
            cli,
            [
                "task",
                "--project",
                "Tree Description Project",
                "tree",
                "--description-lines",
                "1",
            ],
        )

        assert result.exit_code == 0, result.output
        plain = _assert_plain_output_contains(
            result.output,
            "Task Dependency Tree: Tree Description Project",
            "Prepare blocker",
            "Long blocker body",
            "Run blocked task",
            "Long blocked body",
            "View: dependencies",
        )
        assert "No such option" not in plain

    def test_task_tree_without_project_lists_all_projects_json(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Tree All Project A"])
        cli_runner.invoke(cli, ["project", "create", "Tree All Project B"])
        cli_runner.invoke(
            cli,
            [
                "task",
                "add",
                "Tree All Project A",
                "A task",
                "--description",
                "A body",
            ],
        )
        cli_runner.invoke(
            cli,
            [
                "task",
                "add",
                "Tree All Project B",
                "B task",
                "--description",
                "B body",
            ],
        )

        result = cli_runner.invoke(
            cli,
            ["task", "tree", "--format", "json"],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["project"] is None
        assert {project["name"] for project in payload["projects"]} == {
            "Tree All Project A",
            "Tree All Project B",
        }
        titles = {node["task"]["title"] for node in payload["nodes"]}
        assert {"A task", "B task"} <= titles
        assert payload["total_tasks"] == 2

    def test_task_add_with_tags(self, cli_runner: CliRunner, temp_env: Path):
        """Test adding a task with tags."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Tagged Task Project"])

        result = cli_runner.invoke(
            cli,
            [
                "task",
                "add",
                "Tagged Task Project",
                "Tagged Task",
                "-t",
                "urgent",
                "-t",
                "bug",
            ],
        )

        assert result.exit_code == 0
        _assert_plain_output_contains(result.output, "Created task")

    def test_task_add_json_normalizes_links_and_next_steps(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Task Json Project"])

        result = cli_runner.invoke(
            cli,
            [
                "task",
                "add",
                "Task Json Project",
                "Json Task",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["links"]["self"] == _cli_step(
            f"task show {payload['task']['id']}"
        )
        assert payload["links"]["project"] == _cli_step(
            f"project show {payload['project']['id']}"
        )
        assert payload["runtime_write"]["write_path"] == "direct_file"
        assert payload["runtime_write"]["target_kind"] == "workspace_sqlite"
        assert payload["next_steps"][0] == _cli_step(
            'task show "Json Task" --project "Task Json Project"'
        )

    def test_task_add_project_not_found(self, cli_runner: CliRunner, temp_env: Path):
        """Test adding task to non-existent project."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(cli, ["task", "add", "Non-existent", "Some Task"])

        assert result.exit_code == 0
        _assert_plain_output_contains(result.output, "not found")

    def test_task_list_all(self, cli_runner: CliRunner, temp_env: Path):
        """Test listing all tasks."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Project 1"])
        cli_runner.invoke(cli, ["project", "create", "Project 2"])
        cli_runner.invoke(cli, ["task", "add", "Project 1", "Task A"])
        cli_runner.invoke(cli, ["task", "add", "Project 2", "Task B"])

        result = cli_runner.invoke(cli, ["task", "list"])

        assert result.exit_code == 0
        _assert_plain_output_contains(result.output, "Task A", "Task B", "Task Review")

    def test_task_list_review_view_groups_focus_and_graph_walk(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Review View Project"])
        focus_result = cli_runner.invoke(
            cli, ["task", "add", "Review View Project", "Focus Review Task"]
        )
        focus_task_id = _extract_id(focus_result.output)
        cli_runner.invoke(cli, ["task", "start", focus_task_id])
        cli_runner.invoke(
            cli, ["task", "add", "Review View Project", "Ready Review Task"]
        )
        blocked_result = cli_runner.invoke(
            cli, ["task", "add", "Review View Project", "Blocked Review Task"]
        )
        blocked_task_id = _extract_id(blocked_result.output)
        cli_runner.invoke(
            cli, ["task", "block", blocked_task_id, "--reason", "waiting"]
        )

        result = cli_runner.invoke(
            cli, ["task", "list", "--project", "Review View Project"]
        )

        assert result.exit_code == 0, result.output
        _assert_plain_output_contains(
            result.output,
            "Task Review",
            "Focus",
            "Shown summary (current limit/page: 3 tasks): todo 1 | in_progress 1",
            "Total summary (all 3 matching tasks): todo 1 | in_progress 1",
            "graph walk:",
            "Ready",
            "Blocked",
            "uv run pms task graph",
            "uv run pms plan list --task-id",
        )

    def test_task_list_overview_view_retains_dense_table(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Overview View Project"])
        cli_runner.invoke(
            cli, ["task", "add", "Overview View Project", "Overview Task"]
        )

        result = cli_runner.invoke(
            cli,
            [
                "task",
                "list",
                "--project",
                "Overview View Project",
                "--view",
                "overview",
            ],
        )

        assert result.exit_code == 0, result.output
        _assert_plain_output_contains(result.output, "Tasks", "Workflow", "Ref")

    def test_task_list_by_project(self, cli_runner: CliRunner, temp_env: Path):
        """Test listing tasks for specific project."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Filtered Project"])
        cli_runner.invoke(cli, ["task", "add", "Filtered Project", "Project Task"])

        result = cli_runner.invoke(
            cli, ["task", "list", "-p", "Filtered Project", "--format", "json"]
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert any(task["title"] == "Project Task" for task in payload["items"])
        project_task = next(
            task for task in payload["items"] if task["title"] == "Project Task"
        )

    def test_task_list_status_filter_is_honored_instance_wide(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Global Filter Project A"])
        cli_runner.invoke(cli, ["project", "create", "Global Filter Project B"])
        done_result = cli_runner.invoke(
            cli, ["task", "add", "Global Filter Project A", "Done Global Task"]
        )
        done_task_id = _extract_id(done_result.output)
        cli_runner.invoke(cli, ["task", "start", done_task_id, "--by", "tester"])
        cli_runner.invoke(cli, ["task", "complete", done_task_id, "--by", "tester"])
        cli_runner.invoke(
            cli, ["task", "add", "Global Filter Project B", "Todo Global Task"]
        )

        result = cli_runner.invoke(
            cli, ["task", "list", "--status", "done", "--format", "json"]
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["scope"]["population"] == "visible_operator"
        assert payload["page"]["total_count"] == 0
        assert payload["suppressed_hidden_count"] >= 1

        retained_result = cli_runner.invoke(
            cli,
            [
                "task",
                "list",
                "--status",
                "done",
                "--include-generated",
                "--format",
                "json",
            ],
        )

        assert retained_result.exit_code == 0, retained_result.output
        retained_payload = json.loads(retained_result.output)
        assert retained_payload["scope"]["population"] == "all_retained"
        assert retained_payload["page"]["total_count"] == 1
        assert [item["title"] for item in retained_payload["items"]] == [
            "Done Global Task"
        ]
        assert all(item["status"] == "done" for item in retained_payload["items"])

    def test_project_list_json_escapes_multiline_descriptions(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Project list JSON must remain parseable even with multiline descriptions."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(
            cli,
            [
                "project",
                "create",
                "Wrapped Project",
                "--description",
                "Line one\nLine two",
            ],
        )

        result = cli_runner.invoke(cli, ["project", "list", "--format", "json"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        project_item = next(
            item for item in payload["items"] if item["name"] == "Wrapped Project"
        )
        assert project_item["description"] == "Line one\nLine two"

    def test_task_list_next_steps_prioritize_active_work(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Task list should guide the operator toward active work, not the first row."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Execution Project"])

        completed_result = cli_runner.invoke(
            cli, ["task", "add", "Execution Project", "Completed First"]
        )
        completed_id = _extract_id(completed_result.output)
        cli_runner.invoke(cli, ["task", "start", completed_id])
        cli_runner.invoke(cli, ["task", "complete", completed_id])

        active_result = cli_runner.invoke(
            cli, ["task", "add", "Execution Project", "Active Second"]
        )
        active_id = _extract_id(active_result.output)
        cli_runner.invoke(cli, ["task", "start", active_id])

        result = cli_runner.invoke(
            cli,
            ["task", "list", "--project", "Execution Project", "--format", "json"],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        next_steps = payload["next_steps"]
        assert payload["focus_task"]["title"] == "Active Second"
        assert payload["focus_task"]["status"] == "in_progress"
        assert payload["focus_task"]["reason"] == "active execution in progress"
        assert any("Active Second" in step for step in next_steps)
        assert all("Completed First" not in step for step in next_steps)

    def test_task_list_focus_prefers_todo_over_blocked(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Task list should prefer actionable todo work over blocked work."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Priority Project"])

        blocked_result = cli_runner.invoke(
            cli, ["task", "add", "Priority Project", "Blocked First"]
        )
        blocked_id = _extract_id(blocked_result.output)
        cli_runner.invoke(cli, ["task", "block", blocked_id, "--reason", "waiting"])

        cli_runner.invoke(cli, ["task", "add", "Priority Project", "Todo Second"])

        result = cli_runner.invoke(
            cli,
            ["task", "list", "--project", "Priority Project", "--format", "json"],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["focus_task"]["title"] == "Todo Second"
        assert payload["focus_task"]["status"] == "todo"
        assert payload["focus_task"]["reason"] == "next ready work to start"

    def test_task_list_focus_prefers_newer_todo_when_rank_ties(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Task list should prefer the most recently activated todo task."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Tie Break Project"])
        cli_runner.invoke(cli, ["task", "add", "Tie Break Project", "Older Todo"])
        cli_runner.invoke(cli, ["task", "add", "Tie Break Project", "Newer Todo"])

        result = cli_runner.invoke(
            cli,
            ["task", "list", "--project", "Tie Break Project", "--format", "json"],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["focus_task"]["title"] == "Newer Todo"
        assert payload["focus_task"]["status"] == "todo"

    def test_task_list_json_includes_graph_navigation_for_focus_task(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(
            cli,
            [
                "actor",
                "create",
                "Alice Example",
                "--kind",
                "human",
                "--handle",
                "alice-example",
            ],
        )
        cli_runner.invoke(cli, ["project", "create", "Graph Navigation Project"])
        task_result = cli_runner.invoke(
            cli,
            [
                "task",
                "add",
                "Graph Navigation Project",
                "Graph Navigation Task",
                "--assigned-to",
                "alice-example",
            ],
        )
        task_id = _extract_id(task_result.output)

        result = cli_runner.invoke(
            cli,
            [
                "task",
                "list",
                "--project",
                "Graph Navigation Project",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["params"]["view"] == "review"
        assert payload["graph_navigation"]["basis"] == "focus_task"
        assert payload["graph_navigation"]["task_id"] == task_id
        assert payload["graph_navigation"]["links"]["graph"] == _cli_step(
            'task graph "Graph Navigation Task" --project "Graph Navigation Project"'
        )
        assert payload["graph_navigation"]["links"]["plans"] == _cli_step(
            f"plan list --task-id {task_id} --format json"
        )
        assert payload["graph_navigation"]["links"]["actor"] == _cli_step(
            "actor show alice-example --format json"
        )

    def test_task_graph_json_with_dependencies(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Task graph JSON should include dependency details without crashing."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Graph Project"])
        blocked_result = cli_runner.invoke(
            cli, ["task", "add", "Graph Project", "Graph Blocked"]
        )
        blocked_id = _extract_id(blocked_result.output)
        dependency_result = cli_runner.invoke(
            cli, ["task", "add", "Graph Project", "Graph Dependency"]
        )
        dependency_id = _extract_id(dependency_result.output)
        cli_runner.invoke(cli, ["task", "dep", "add", blocked_id, dependency_id])

        result = cli_runner.invoke(
            cli,
            ["task", "graph", blocked_id, "--format", "json"],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["blocked_by"] == [dependency_id]
        assert payload["blocked_by_details"][0]["id"] == dependency_id

    def test_task_graph_json_hides_resolved_dependency_blockers_when_only_draft_lock_remains(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Graph Lock Project"])
        blocker_id = _extract_id(
            cli_runner.invoke(
                cli, ["task", "add", "Graph Lock Project", "Primary Blocker"]
            ).output
        )
        blocked_id = _extract_id(
            cli_runner.invoke(
                cli, ["task", "add", "Graph Lock Project", "Blocked Closer"]
            ).output
        )
        cli_runner.invoke(cli, ["task", "dep", "add", blocked_id, blocker_id])
        create_result = cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Draft Locked Dependent Plan",
                "--project",
                "Graph Lock Project",
                "--task-id",
                blocked_id,
                "--content",
                "{}",
            ],
        )
        cli_runner.invoke(cli, ["task", "complete", blocker_id])

        graph_json = cli_runner.invoke(
            cli, ["task", "graph", blocked_id, "--format", "json"]
        )

        assert graph_json.exit_code == 0, graph_json.output
        payload = json.loads(graph_json.output)
        assert payload["blocked_by"] == []
        assert payload["blocked_by_details"] == []
        assert payload["resolved_blocked_by_details"][0]["id"] == blocker_id
        assert payload["execution_lock_plans"] == ["Draft Locked Dependent Plan"]

    def test_task_search_json_continuation_fields(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Task search JSON payload should include continuation hints and scope metadata."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Search Project"])
        cli_runner.invoke(cli, ["task", "add", "Search Project", "Searchable Task"])

        result = cli_runner.invoke(
            cli,
            ["task", "search", "--query", "Searchable", "--format", "json"],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["scope"]["population"] == "visible_operator"
        assert payload["visible_totals"]["population"] == "visible_operator"
        assert payload["population_totals"]["population"] == "visible_operator"
        assert payload["items"]
        first = payload["items"][0]
        assert "links" in first
        assert first["links"]["guide"] == _cli_step("start --format json")
        assert "next_steps" in first
        assert first["next_steps"]

    def test_task_search_review_view_and_graph_navigation(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        fixture = _setup_actor_assignment_surface_fixture(cli_runner)

        text_result = cli_runner.invoke(
            cli,
            [
                "task",
                "search",
                "--project",
                fixture["project_name"],
                "--query",
                "Actor",
            ],
        )

        assert text_result.exit_code == 0, text_result.output
        _assert_plain_output_contains(text_result.output, "Task Review", "graph walk:")

        json_result = cli_runner.invoke(
            cli,
            [
                "task",
                "search",
                "--project",
                fixture["project_name"],
                "--query",
                "Actor",
                "--format",
                "json",
            ],
        )

        assert json_result.exit_code == 0, json_result.output
        payload = json.loads(json_result.output)
        assert payload["params"]["view"] == "review"
        assert payload["graph_navigation"]["basis"] == "focus_task"
        assert payload["graph_navigation"]["task_id"] == payload["focus_task"]["id"]

    def test_task_ready_review_view_and_graph_navigation(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        fixture = _setup_actor_assignment_surface_fixture(cli_runner)

        text_result = cli_runner.invoke(
            cli,
            ["task", "ready", "--project", fixture["project_name"]],
        )

        assert text_result.exit_code == 0, text_result.output
        _assert_plain_output_contains(
            text_result.output, "Ready Tasks", "graph walk:", "Ready"
        )

        json_result = cli_runner.invoke(
            cli,
            ["task", "ready", "--project", fixture["project_name"], "--format", "json"],
        )

        assert json_result.exit_code == 0, json_result.output
        payload = json.loads(json_result.output)
        assert payload["params"]["view"] == "review"
        assert payload["graph_navigation"]["basis"] == "focus_task"
        assert payload["graph_navigation"]["task_id"] == payload["focus_task"]["id"]

    def test_task_stale_review_view_and_graph_navigation(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        fixture = _setup_actor_assignment_surface_fixture(cli_runner)

        text_result = cli_runner.invoke(
            cli,
            [
                "task",
                "stale",
                "--project",
                fixture["project_name"],
                "--days",
                "14",
            ],
        )

        assert text_result.exit_code == 0, text_result.output
        _assert_plain_output_contains(text_result.output, "Task Review", "graph walk:")

        json_result = cli_runner.invoke(
            cli,
            [
                "task",
                "stale",
                "--project",
                fixture["project_name"],
                "--days",
                "14",
                "--format",
                "json",
            ],
        )

        assert json_result.exit_code == 0, json_result.output
        payload = json.loads(json_result.output)
        assert payload["params"]["view"] == "review"
        assert payload["graph_navigation"]["basis"] == "focus_task"
        assert payload["graph_navigation"]["task_id"] == payload["focus_task"]["id"]

    def test_task_blocked_review_view_and_graph_navigation(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        fixture = _setup_actor_assignment_surface_fixture(cli_runner)

        text_result = cli_runner.invoke(
            cli,
            ["task", "blocked", "--project", fixture["project_name"]],
        )

        assert text_result.exit_code == 0, text_result.output
        _assert_plain_output_contains(
            text_result.output, "Task Review", "graph walk:", "Blocked"
        )

        json_result = cli_runner.invoke(
            cli,
            [
                "task",
                "blocked",
                "--project",
                fixture["project_name"],
                "--format",
                "json",
            ],
        )

        assert json_result.exit_code == 0, json_result.output
        payload = json.loads(json_result.output)
        assert payload["params"]["view"] == "review"
        assert payload["graph_navigation"]["basis"] == "focus_task"
        assert payload["graph_navigation"]["task_id"] == payload["focus_task"]["id"]

    def test_project_and_control_surfaces_include_graph_navigation(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        fixture = _setup_graph_discoverability_fixture(cli_runner)

        project_show_result = cli_runner.invoke(
            cli,
            ["project", "show", fixture["project_id"], "--format", "json"],
        )
        assert project_show_result.exit_code == 0, project_show_result.output
        project_show_payload = json.loads(project_show_result.output)
        assert project_show_payload["graph_navigation"]["basis"] == "focus_task"
        assert (
            project_show_payload["graph_navigation"]["task_id"]
            == project_show_payload["focus_task"]["id"]
        )

        project_summary_result = cli_runner.invoke(
            cli,
            ["project", "summary", fixture["project_id"], "--format", "json"],
        )
        assert project_summary_result.exit_code == 0, project_summary_result.output
        project_summary_payload = json.loads(project_summary_result.output)
        assert project_summary_payload["graph_navigation"]["basis"] == "focus_task"
        assert (
            project_summary_payload["graph_navigation"]["task_id"]
            == project_summary_payload["focus_task"]["id"]
        )

        dashboard_result = cli_runner.invoke(cli, ["dashboard", "--format", "json"])
        assert dashboard_result.exit_code == 0, dashboard_result.output
        dashboard_payload = json.loads(dashboard_result.output)
        assert dashboard_payload["graph_navigation"]["basis"] == "focus_task"
        assert (
            dashboard_payload["graph_navigation"]["task_id"]
            == dashboard_payload["focus_task"]["id"]
        )

        start_result = cli_runner.invoke(cli, ["start", "--format", "json"])
        assert start_result.exit_code == 0, start_result.output
        start_payload = json.loads(start_result.output)
        assert start_payload["graph_navigation"]["basis"] == "focus_task"
        assert (
            start_payload["graph_navigation"]["task_id"]
            == start_payload["focus_task"]["id"]
        )

    def test_task_start_block_unblock(self, cli_runner: CliRunner, temp_env: Path):
        """Test task start/block/unblock commands."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "State Project"])
        task_result = cli_runner.invoke(
            cli,
            ["task", "add", "State Project", "State Task"],
        )
        task_id = _extract_id(task_result.output)

        started = cli_runner.invoke(cli, ["task", "start", task_id])
        assert started.exit_code == 0
        assert "Started" in started.output

        blocked = cli_runner.invoke(cli, ["task", "block", task_id, "--reason", "wait"])
        assert blocked.exit_code == 0
        assert "Blocked" in blocked.output

        unblocked = cli_runner.invoke(cli, ["task", "unblock", task_id])
        assert unblocked.exit_code == 0
        assert "Unblocked" in unblocked.output

    def test_task_complete_json_surfaces_newly_unblocked_dependents(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Task completion JSON should identify newly unblocked dependents."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Completion Effects Project"])
        blocker_result = cli_runner.invoke(
            cli, ["task", "add", "Completion Effects Project", "Finish Blocker"]
        )
        blocker_id = _extract_id(blocker_result.output)
        dependent_result = cli_runner.invoke(
            cli, ["task", "add", "Completion Effects Project", "Ready After Blocker"]
        )
        dependent_id = _extract_id(dependent_result.output)
        cli_runner.invoke(cli, ["task", "dep", "add", dependent_id, blocker_id])

        result = cli_runner.invoke(
            cli,
            ["task", "complete", blocker_id, "--format", "json"],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["task"]["status"] == "done"
        assert len(payload["newly_unblocked"]) == 1
        first = payload["newly_unblocked"][0]
        assert first["id"] == dependent_id
        assert first["status"] == "todo"
        assert first["links"]["self"] == _cli_step(
            f'task show "Ready After Blocker" --project "Completion Effects Project"'
        )
        assert first["next_steps"][0] == _cli_step(
            f'task show "Ready After Blocker" --project "Completion Effects Project"'
        )
        assert payload["next_steps"][0] == _cli_step(
            f'task show "Ready After Blocker" --project "Completion Effects Project"'
        )

    def test_task_complete_text_surfaces_newly_unblocked_dependents(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Task completion text output should call out newly unblocked dependents."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Completion Effects Project"])
        blocker_result = cli_runner.invoke(
            cli, ["task", "add", "Completion Effects Project", "Finish Blocker"]
        )
        blocker_id = _extract_id(blocker_result.output)
        dependent_result = cli_runner.invoke(
            cli, ["task", "add", "Completion Effects Project", "Ready After Blocker"]
        )
        dependent_id = _extract_id(dependent_result.output)
        cli_runner.invoke(cli, ["task", "dep", "add", dependent_id, blocker_id])

        result = cli_runner.invoke(cli, ["task", "complete", blocker_id])

        assert result.exit_code == 0
        _assert_plain_output_contains(
            result.output, "Newly unblocked:", "Ready After Blocker"
        )

    def test_task_complete_reconciles_already_done_task_with_stale_progress(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Completion Reconcile Project"])
        task_result = cli_runner.invoke(
            cli,
            ["task", "add", "Completion Reconcile Project", "Reconcile Done Task"],
        )
        task_id = _extract_id(task_result.output)

        cli_runner.invoke(
            cli,
            [
                "task",
                "start",
                task_id,
                "--project",
                "Completion Reconcile Project",
                "--by",
                "tester",
            ],
        )
        cli_runner.invoke(
            cli,
            [
                "task",
                "progress",
                task_id,
                "--project",
                "Completion Reconcile Project",
                "80",
                "Nearly done",
                "--by",
                "tester",
            ],
        )
        cli_runner.invoke(
            cli,
            [
                "task",
                "complete",
                task_id,
                "--project",
                "Completion Reconcile Project",
                "--by",
                "tester",
            ],
        )

        reconcile_result = cli_runner.invoke(
            cli,
            [
                "task",
                "complete",
                task_id,
                "--project",
                "Completion Reconcile Project",
                "--by",
                "tester",
                "--format",
                "json",
            ],
        )
        assert reconcile_result.exit_code == 0, reconcile_result.output
        payload = json.loads(reconcile_result.output)
        assert payload["task"]["status"] == "done"
        assert payload["task"]["current_progress_percent"] == 100

    def test_task_list_focus_moves_to_newly_unblocked_dependent(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Task list focus should shift to the dependent unblocked by completion."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Completion Focus Project"])
        blocker_result = cli_runner.invoke(
            cli, ["task", "add", "Completion Focus Project", "Focus Blocker"]
        )
        blocker_id = _extract_id(blocker_result.output)
        dependent_result = cli_runner.invoke(
            cli, ["task", "add", "Completion Focus Project", "Focus Dependent"]
        )
        dependent_id = _extract_id(dependent_result.output)
        cli_runner.invoke(cli, ["task", "dep", "add", dependent_id, blocker_id])

        cli_runner.invoke(cli, ["task", "complete", blocker_id])

        result = cli_runner.invoke(
            cli,
            [
                "task",
                "list",
                "--project",
                "Completion Focus Project",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["focus_task"]["id"] == dependent_id
        assert payload["focus_task"]["status"] == "todo"

    def test_task_start_by_title(self, cli_runner: CliRunner, temp_env: Path):
        """Test task start resolves by title with project."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Title Project"])
        cli_runner.invoke(cli, ["task", "add", "Title Project", "Title Task"])

        started = cli_runner.invoke(
            cli, ["task", "start", "Title Task", "--project", "Title Project"]
        )
        assert started.exit_code == 0

    def test_task_start_on_draft_plan_surfaces_activation_guidance(
        self, cli_runner: CliRunner, temp_env: Path
    ):
        """Task execution locks should tell the operator which draft plan to activate."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Draft Start Project"])
        task_result = cli_runner.invoke(
            cli,
            ["task", "add", "Draft Start Project", "Draft Start Task"],
        )
        task_id = _extract_id(task_result.output)
        plan_result = cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Draft Start Plan",
                "--project",
                "Draft Start Project",
                "--task-id",
                task_id,
                "--content",
                "{}",
            ],
        )
        plan_id = _extract_id(plan_result.output)

        started = cli_runner.invoke(cli, ["task", "start", task_id])

        assert started.exit_code == 0
        plain_output = _assert_plain_output_contains(
            started.output,
            "linked plan is still draft",
            f"Draft Start Plan ({plan_id})",
            f"uv run pms plan update {plan_id} --status active",
        )
        assert "Blocking draft plans:" in plain_output

    def test_task_progress_json_normalizes_next_steps_and_immediate_show_matches(
        self, cli_runner: CliRunner, temp_env: Path
    ):
        """Task progress JSON should emit normalized commands and immediate show should reflect the write."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Progress Readback Project"])
        cli_runner.invoke(
            cli,
            ["task", "add", "Progress Readback Project", "Progress Readback Task"],
        )
        cli_runner.invoke(
            cli,
            [
                "task",
                "start",
                "Progress Readback Task",
                "--project",
                "Progress Readback Project",
                "--format",
                "json",
            ],
        )

        progress_result = cli_runner.invoke(
            cli,
            [
                "task",
                "progress",
                "Progress Readback Task",
                "--project",
                "Progress Readback Project",
                "37",
                "Direct readback check",
                "--by",
                "tester",
                "--format",
                "json",
            ],
            env={"PMS_WRITE_MODE": "direct"},
        )

        assert progress_result.exit_code == 0
        progress_payload = json.loads(progress_result.output)
        assert progress_payload["progress"]["percent"] == 37
        assert progress_payload["next_steps"][0] == _cli_step(
            'task show "Progress Readback Task" --project "Progress Readback Project"'
        )
        assert progress_payload["next_steps"][1] == _cli_step(
            'task review "Progress Readback Task" --project "Progress Readback Project" --by tester'
        )

        show_result = cli_runner.invoke(
            cli,
            [
                "task",
                "show",
                "Progress Readback Task",
                "--project",
                "Progress Readback Project",
                "--format",
                "json",
            ],
            env={"PMS_WRITE_MODE": "direct"},
        )

        assert show_result.exit_code == 0
        show_payload = json.loads(show_result.output)
        assert show_payload["current_progress_percent"] == 37
        assert show_payload["progress"]["current_percent"] == 37
        assert (
            show_payload["progress"]["last_update"]["status_message"]
            == "Direct readback check"
        )

    def test_task_progress_to_100_auto_completes_and_project_readback_matches(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """A 100% progress update should complete the task and converge task/project readbacks immediately."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Auto Complete Progress Project"])
        cli_runner.invoke(
            cli,
            [
                "task",
                "add",
                "Auto Complete Progress Project",
                "Auto Complete Progress Task",
            ],
        )
        cli_runner.invoke(
            cli,
            [
                "task",
                "start",
                "Auto Complete Progress Task",
                "--project",
                "Auto Complete Progress Project",
                "--format",
                "json",
            ],
            env={"PMS_WRITE_MODE": "direct"},
        )

        progress_result = cli_runner.invoke(
            cli,
            [
                "task",
                "progress",
                "Auto Complete Progress Task",
                "--project",
                "Auto Complete Progress Project",
                "100",
                "Finished via progress update",
                "--by",
                "tester",
                "--format",
                "json",
            ],
            env={"PMS_WRITE_MODE": "direct"},
        )

        assert progress_result.exit_code == 0, progress_result.output
        progress_payload = json.loads(progress_result.output)
        assert progress_payload["task"]["status"] == "done"
        assert progress_payload["task"]["current_progress_percent"] == 100

        task_show = cli_runner.invoke(
            cli,
            [
                "task",
                "show",
                "Auto Complete Progress Task",
                "--project",
                "Auto Complete Progress Project",
                "--format",
                "json",
            ],
            env={"PMS_WRITE_MODE": "direct"},
        )
        assert task_show.exit_code == 0, task_show.output
        task_payload = json.loads(task_show.output)
        assert task_payload["status"] == "done"
        assert task_payload["current_progress_percent"] == 100

        project_show = cli_runner.invoke(
            cli,
            [
                "project",
                "show",
                "Auto Complete Progress Project",
                "--format",
                "json",
            ],
            env={"PMS_WRITE_MODE": "direct"},
        )
        assert project_show.exit_code == 0, project_show.output
        project_payload = json.loads(project_show.output)
        assert project_payload["focus_task"] is None
        assert project_payload["execution"]["in_progress_tasks"] == 0
        assert project_payload["execution"]["completed_tasks"] == 1

    def test_task_progress_on_draft_plan_returns_json_guidance(
        self, cli_runner: CliRunner, temp_env: Path
    ):
        """JSON task execution lock output should surface blocking draft plans and activation commands."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Draft Progress Project"])
        task_result = cli_runner.invoke(
            cli,
            ["task", "add", "Draft Progress Project", "Draft Progress Task"],
        )
        task_id = _extract_id(task_result.output)
        plan_result = cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Draft Progress Plan",
                "--project",
                "Draft Progress Project",
                "--task-id",
                task_id,
                "--content",
                "{}",
            ],
        )
        plan_id = _extract_id(plan_result.output)

        result = cli_runner.invoke(
            cli,
            ["task", "progress", task_id, "--format", "json", "20", "Blocked by draft"],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["error"]["code"] == "draft_plan_execution_locked"
        assert payload["blocking_plans"][0]["id"] == plan_id
        assert payload["next_steps"][0] == _cli_step(
            'task show "Draft Progress Task" --project "Draft Progress Project"'
        )
        assert (
            _cli_step(f"plan update {plan_id} --status active") in payload["next_steps"]
        )

    def test_task_show_reconciles_completed_progress_last_update_to_terminal_truth(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Completed Progress Project"])
        task_result = cli_runner.invoke(
            cli,
            ["task", "add", "Completed Progress Project", "Completed Progress Task"],
        )
        task_id = _extract_id(task_result.output)

        progress_result = cli_runner.invoke(
            cli,
            [
                "task",
                "progress",
                task_id,
                "--project",
                "Completed Progress Project",
                "50",
                "Halfway there",
                "--by",
                "tester",
                "--format",
                "json",
            ],
            env={"PMS_WRITE_MODE": "direct"},
        )
        assert progress_result.exit_code == 0, progress_result.output

        complete_result = cli_runner.invoke(
            cli,
            [
                "task",
                "complete",
                task_id,
                "--project",
                "Completed Progress Project",
                "--by",
                "tester",
                "--format",
                "json",
            ],
            env={"PMS_WRITE_MODE": "direct"},
        )
        assert complete_result.exit_code == 0, complete_result.output

        show_result = cli_runner.invoke(
            cli,
            [
                "task",
                "show",
                task_id,
                "--project",
                "Completed Progress Project",
                "--format",
                "json",
            ],
            env={"PMS_WRITE_MODE": "direct"},
        )

        assert show_result.exit_code == 0, show_result.output
        show_payload = json.loads(show_result.output)
        assert show_payload["status"] == "done"
        assert show_payload["current_progress_percent"] == 100
        assert show_payload["progress"]["current_percent"] == 100
        assert show_payload["progress"]["last_update"]["percent_complete"] == 100
        assert show_payload["progress"]["last_update"]["status_message"] == "Completed"

    def test_task_show_ambiguous_title_suggests_pick_and_search(
        self, cli_runner: CliRunner, temp_env: Path
    ):
        """Ambiguous title lookup should show exact recovery commands."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Ambiguous Project"])
        cli_runner.invoke(cli, ["task", "add", "Ambiguous Project", "Same Title"])
        cli_runner.invoke(cli, ["task", "add", "Ambiguous Project", "Same Title"])

        result = cli_runner.invoke(
            cli,
            ["task", "show", "Same Title", "--project", "Ambiguous Project"],
        )

        assert result.exit_code == 0
        _assert_plain_output_contains(
            result.output,
            "Multiple tasks match that title.",
            "--pick",
            'pms task show "Same Title" --project "Ambiguous Project" --pick',
            'pms task search --project "Ambiguous Project" --query "Same Title"',
        )

    def test_task_block_by_title(self, cli_runner: CliRunner, temp_env: Path):
        """Test task block resolves by title with project."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Block Title Project"])
        cli_runner.invoke(
            cli, ["task", "add", "Block Title Project", "Block Title Task"]
        )

        blocked = cli_runner.invoke(
            cli,
            [
                "task",
                "block",
                "Block Title Task",
                "--project",
                "Block Title Project",
                "--reason",
                "waiting",
            ],
        )
        assert blocked.exit_code == 0
        assert "Blocked" in blocked.output

    def test_task_update_by_title(self, cli_runner: CliRunner, temp_env: Path):
        """Test task update resolves by title with project."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Update Title Project"])
        cli_runner.invoke(
            cli, ["task", "add", "Update Title Project", "Update Title Task"]
        )

        updated = cli_runner.invoke(
            cli,
            [
                "task",
                "update",
                "Update Title Task",
                "--project",
                "Update Title Project",
                "--description",
                "Updated via title",
            ],
        )
        assert updated.exit_code == 0

        list_result = cli_runner.invoke(
            cli,
            ["task", "list", "--project", "Update Title Project", "--format", "json"],
        )
        payload = json.loads(list_result.output)
        entry = next(
            item for item in payload["items"] if item["title"] == "Update Title Task"
        )
        assert entry["description"] == "Updated via title"

    def test_task_update_json_output(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Task update should support machine-readable output for planning flows."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Update Json Project"])
        cli_runner.invoke(
            cli, ["task", "add", "Update Json Project", "Update Json Task"]
        )

        updated = cli_runner.invoke(
            cli,
            [
                "task",
                "update",
                "Update Json Task",
                "--project",
                "Update Json Project",
                "--done-when",
                "Criterion A",
                "--format",
                "json",
            ],
        )

        assert updated.exit_code == 0
        payload = json.loads(updated.output)
        assert payload["task"]["title"] == "Update Json Task"
        assert payload["task"]["workflow_metadata"]["completion_criteria"] == [
            "Criterion A"
        ]
        assert payload["links"]["self"].startswith(_cli_step("task show "))
        assert payload["next_steps"][0].startswith(
            _cli_step('task show "Update Json Task"')
        )

    def test_task_update_completion_criteria_and_show(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Task update should persist structured completion criteria."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Criteria Project"])
        task_result = cli_runner.invoke(
            cli, ["task", "add", "Criteria Project", "Criteria Task"]
        )
        task_id = _extract_id(task_result.output)

        updated = cli_runner.invoke(
            cli,
            [
                "task",
                "update",
                task_id,
                "--done-when",
                "Expose top risks now in the overview payload",
                "--done-when",
                "Document the operator-facing response example",
            ],
        )
        assert updated.exit_code == 0

        show_result = cli_runner.invoke(
            cli,
            ["task", "show", task_id, "--format", "json"],
        )
        assert show_result.exit_code == 0
        payload = json.loads(show_result.output)
        assert payload["completion_criteria"] == [
            "Expose top risks now in the overview payload",
            "Document the operator-facing response example",
        ]
        assert payload["completion_ready"] is False

    def test_task_update_fails_nonzero_for_conflicting_parent_selectors(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Parent Conflict Project"])
        task_result = cli_runner.invoke(
            cli, ["task", "add", "Parent Conflict Project", "Parent Conflict Task"]
        )
        task_id = _extract_id(task_result.output)

        result = cli_runner.invoke(
            cli,
            [
                "task",
                "update",
                task_id,
                "--project",
                "Parent Conflict Project",
                "--parent-id",
                "task_parent",
                "--clear-parent",
                "--format",
                "json",
            ],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert payload["error"] == "Use --parent-id or --clear-parent, not both"

    def test_task_update_fails_nonzero_for_conflicting_completion_selectors(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Done When Conflict Project"])
        task_result = cli_runner.invoke(
            cli,
            ["task", "add", "Done When Conflict Project", "Done When Conflict Task"],
        )
        task_id = _extract_id(task_result.output)

        result = cli_runner.invoke(
            cli,
            [
                "task",
                "update",
                task_id,
                "--project",
                "Done When Conflict Project",
                "--done-when",
                "Condition A",
                "--clear-done-when",
                "--format",
                "json",
            ],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert payload["error"] == "Use --done-when or --clear-done-when, not both"

    def test_task_evidence_add_by_title(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Test task evidence add resolves by title with project."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Evidence Title Project"])
        cli_runner.invoke(
            cli, ["task", "add", "Evidence Title Project", "Evidence Title Task"]
        )

        add_result = cli_runner.invoke(
            cli,
            [
                "task",
                "evidence",
                "add",
                "Evidence Title Task",
                "scm_commit",
                "abc123",
                "--project",
                "Evidence Title Project",
            ],
        )
        assert add_result.exit_code == 0

        list_result = cli_runner.invoke(
            cli,
            ["task", "list", "--project", "Evidence Title Project", "--format", "json"],
        )
        payload = json.loads(list_result.output)
        task_id = next(
            item["id"]
            for item in payload["items"]
            if item["title"] == "Evidence Title Task"
        )

        evidence_result = cli_runner.invoke(
            cli, ["task", "evidence", "list", task_id, "--format", "json"]
        )
        evidence_payload = json.loads(evidence_result.output)
        assert any(item["reference"] == "abc123" for item in evidence_payload["items"])

    def test_task_resolve_by_title(self, cli_runner: CliRunner, temp_env: Path) -> None:
        """Test task resolve returns ID for title with project."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Resolve Project"])
        task_result = cli_runner.invoke(
            cli, ["task", "add", "Resolve Project", "Resolve Task"]
        )
        task_id = _extract_id(task_result.output)

        resolve_result = cli_runner.invoke(
            cli,
            [
                "task",
                "resolve",
                "Resolve Task",
                "--project",
                "Resolve Project",
                "--format",
                "json",
            ],
        )
        assert resolve_result.exit_code == 0
        payload = json.loads(resolve_result.output)
        assert payload["id"] == task_id

    def test_task_checkout_by_title(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Test task checkout resolves by title with project."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Checkout Project"])
        cli_runner.invoke(cli, ["task", "add", "Checkout Project", "Checkout Task"])

        checkout_result = cli_runner.invoke(
            cli,
            [
                "task",
                "checkout",
                "Checkout Task",
                "--project",
                "Checkout Project",
                "--agent-id",
                "tester",
            ],
        )
        assert checkout_result.exit_code == 0
        assert "Checked out" in checkout_result.output

        release_result = cli_runner.invoke(
            cli,
            [
                "task",
                "release",
                "Checkout Task",
                "--project",
                "Checkout Project",
                "--agent-id",
                "tester",
            ],
        )
        assert release_result.exit_code == 0
        assert "Released" in release_result.output

    def test_task_dependency_add_remove(self, cli_runner: CliRunner, temp_env: Path):
        """Test task dependency add/remove commands."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Dep Project"])
        a = cli_runner.invoke(cli, ["task", "add", "Dep Project", "Task A"])
        b = cli_runner.invoke(cli, ["task", "add", "Dep Project", "Task B"])
        task_a = _extract_id(a.output)
        task_b = _extract_id(b.output)

        add = cli_runner.invoke(cli, ["task", "dep", "add", task_b, task_a])
        assert add.exit_code == 0
        assert "Added dependency" in add.output

        remove = cli_runner.invoke(cli, ["task", "dep", "remove", task_b, task_a])
        assert remove.exit_code == 0
        assert "Removed dependency" in remove.output


class TestPlanTestJobCommands:
    """Tests for plan test job commands."""

    def test_plan_test_job_run_with_plan_id(
        self, cli_runner: CliRunner, temp_env: Path
    ):
        """Test running a plan test job with plan + job ID."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])

        project_result = cli_runner.invoke(
            cli,
            ["project", "create", "Plan Job Project"],
        )
        project_id = _extract_id(project_result.output)

        task_result = cli_runner.invoke(
            cli,
            ["task", "add", project_id, "Plan Job Task"],
        )
        task_id = _extract_id(task_result.output)

        plan_result = cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Plan Job Plan",
                "--project-id",
                project_id,
                "--task-id",
                task_id,
            ],
        )
        plan_id = _extract_id(plan_result.output)

        python_cmd = f"{shlex.quote(sys.executable)} -c \"print('ok')\""
        job_result = cli_runner.invoke(
            cli,
            [
                "plan",
                "test-job",
                "add",
                plan_id,
                "Plan Job",
                ".",
                "--command",
                python_cmd,
            ],
        )
        job_id = _extract_id(job_result.output)

        run_result = cli_runner.invoke(
            cli,
            ["plan", "test-job", "run", plan_id, job_id, "--no-output"],
        )

        assert run_result.exit_code == 0
        assert "Run ID:" in run_result.output

    def test_plan_test_job_run_requires_valid_argument_shape(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(
            cli,
            ["plan", "test-job", "run", "a", "b", "c"],
        )

        assert result.exit_code != 0
        _assert_plain_output_contains(
            result.output, "Expected JOB_ID or PLAN_ID JOB_ID"
        )

    def test_plan_test_job_add_rejects_deprecated_stream_output(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        plan_result = cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Deprecated Stream Plan",
            ],
        )
        plan_id = _extract_id(plan_result.output)

        result = cli_runner.invoke(
            cli,
            [
                "plan",
                "test-job",
                "add",
                plan_id,
                "Deprecated Stream Job",
                ".",
                "--mode",
                "aws",
                "--server-name",
                "aws-test",
                "--stream-output",
            ],
        )

        assert result.exit_code == 0
        _assert_plain_output_contains(result.output, "stream_output is not supported")


class TestTaskEvidenceCommands:
    """Tests for task evidence commands."""

    def test_task_evidence_add_list(self, cli_runner: CliRunner, temp_env: Path):
        """Test adding and listing task evidence."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Evidence Project"])

        task_result = cli_runner.invoke(
            cli,
            ["task", "add", "Evidence Project", "Evidence Task"],
        )
        assert task_result.exit_code == 0
        task_id = _extract_id(task_result.output)

        add_result = cli_runner.invoke(
            cli,
            [
                "task",
                "evidence",
                "add",
                task_id,
                "scm_commit",
                "abc123",
                "--description",
                "Manual commit",
            ],
        )
        assert add_result.exit_code == 0
        assert "Added evidence" in add_result.output

        list_result = cli_runner.invoke(
            cli,
            ["task", "evidence", "list", task_id, "--format", "json"],
        )
        assert list_result.exit_code == 0
        payload = json.loads(list_result.output)
        assert payload["items"][0]["reference"] == "abc123"

    def test_task_proof_bundle_search(self, cli_runner: CliRunner, temp_env: Path):
        """Test searching proof bundles via CLI."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Bundle Project"])

        task_result = cli_runner.invoke(
            cli,
            ["task", "add", "Bundle Project", "Bundle Task"],
        )
        assert task_result.exit_code == 0
        task_id = _extract_id(task_result.output)

        add_result = cli_runner.invoke(
            cli,
            [
                "task",
                "evidence",
                "add",
                task_id,
                "scm_commit",
                "bundle123",
            ],
        )
        assert add_result.exit_code == 0

        search_result = cli_runner.invoke(
            cli,
            [
                "task",
                "proof-bundle-search",
                "--task-id",
                task_id,
                "--include-evidence",
                "--format",
                "json",
            ],
        )
        assert search_result.exit_code == 0
        payload = json.loads(search_result.output)
        assert payload["page"]["total_count"] == 1
        assert payload["items"][0]["task"]["id"] == task_id

    def test_test_record_fails_nonzero_and_machine_readable_when_server_missing(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from datetime import UTC, datetime

        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Record Failure Project"])
        task_result = cli_runner.invoke(
            cli,
            ["task", "add", "Record Failure Project", "Record Failure Task"],
        )
        assert task_result.exit_code == 0, task_result.output
        task_id = _extract_id(task_result.output)

        project_result = cli_runner.invoke(cli, ["project", "list", "--format", "json"])
        assert project_result.exit_code == 0, project_result.output
        project_id = next(
            item["id"]
            for item in json.loads(project_result.output)["items"]
            if item["name"] == "Record Failure Project"
        )

        stamp = datetime.now(UTC).replace(microsecond=0).isoformat()
        result = cli_runner.invoke(
            cli,
            [
                "test",
                "record",
                "--server-id",
                "missing-server",
                "--status",
                "passed",
                "--started-at",
                stamp,
                "--finished-at",
                stamp,
                "--project-id",
                project_id,
                "--task-id",
                task_id,
                "--format",
                "json",
            ],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output.splitlines()[0])
        assert payload["error"]["code"] == "test_record_failed"
        assert payload["error"]["message"] == "Test server not found"

    def test_test_record_invalid_timestamp_is_machine_readable_in_json_mode(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(
            cli,
            [
                "test",
                "record",
                "--server-id",
                "local",
                "--status",
                "passed",
                "--started-at",
                "not-a-timestamp",
                "--finished-at",
                "not-a-timestamp",
                "--format",
                "json",
            ],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output.splitlines()[0])
        assert payload["error"]["code"] == "test_record_failed"
        assert "Invalid timestamp format" in payload["error"]["message"]

    def test_test_record_invalid_json_payload_is_machine_readable_in_json_mode(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from datetime import UTC, datetime

        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        stamp = datetime.now(UTC).replace(microsecond=0).isoformat()
        result = cli_runner.invoke(
            cli,
            [
                "test",
                "record",
                "--server-id",
                "local",
                "--status",
                "passed",
                "--started-at",
                stamp,
                "--finished-at",
                stamp,
                "--logs",
                "{not-json}",
                "--format",
                "json",
            ],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output.splitlines()[0])
        assert payload["error"]["code"] == "test_record_failed"
        assert "Invalid JSON payload" in payload["error"]["message"]


class TestRevisionCommands:
    """Tests for revision diff commands."""

    def test_revision_diff_project(self, cli_runner: CliRunner, temp_env: Path):
        """Test diffing project revisions."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        create_result = cli_runner.invoke(
            cli, ["project", "create", "Revision Project"]
        )
        assert create_result.exit_code == 0
        project_id = _extract_id(create_result.output)

        update_result = cli_runner.invoke(
            cli,
            ["project", "update", "Revision Project", "--new-name", "Revision v2"],
        )
        assert update_result.exit_code == 0

        diff_result = cli_runner.invoke(
            cli,
            [
                "revision",
                "diff",
                "project",
                project_id,
                "--from",
                "1",
                "--to",
                "2",
                "--format",
                "json",
            ],
        )
        assert diff_result.exit_code == 0
        payload = json.loads(diff_result.output)
        assert payload["entity_id"] == project_id
        assert any(change["field_name"] == "name" for change in payload["changes"])

    def test_revision_bundle_project(self, cli_runner: CliRunner, temp_env: Path):
        """Test exporting revision history bundles."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        create_result = cli_runner.invoke(cli, ["project", "create", "Bundle Project"])
        assert create_result.exit_code == 0
        project_id = _extract_id(create_result.output)

        task_result = cli_runner.invoke(
            cli, ["task", "add", "Bundle Project", "Bundle Task"]
        )
        assert task_result.exit_code == 0
        task_id = _extract_id(task_result.output)

        update_result = cli_runner.invoke(
            cli,
            ["project", "update", "Bundle Project", "--description", "Updated"],
        )
        assert update_result.exit_code == 0

        bundle_result = cli_runner.invoke(
            cli,
            [
                "revision",
                "bundle",
                "project",
                project_id,
                "--include-linked",
                "--include-linked-history",
                "--format",
                "json",
            ],
        )
        assert bundle_result.exit_code == 0
        payload = json.loads(bundle_result.output)
        assert payload["entity_id"] == project_id
        linked_tasks = payload.get("linked", {}).get("tasks", [])
        assert any(task["id"] == task_id for task in linked_tasks)


class TestTimelineCommands:
    """Tests for timeline filtering commands."""

    def test_timeline_filters(self, cli_runner: CliRunner, temp_env: Path):
        """Timeline filters should narrow transitions."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        create_result = cli_runner.invoke(
            cli, ["project", "create", "Timeline Project"]
        )
        assert create_result.exit_code == 0

        task_result = cli_runner.invoke(
            cli, ["task", "add", "Timeline Project", "Timeline Task"]
        )
        assert task_result.exit_code == 0
        task_id = _extract_id(task_result.output)

        assign_result = cli_runner.invoke(
            cli, ["workflow", "assign", task_id, "sdlc", "concept"]
        )
        assert assign_result.exit_code == 0

        transition_result = cli_runner.invoke(
            cli,
            [
                "workflow",
                "transition",
                task_id,
                "idea",
                "--by",
                "timeline_tester",
            ],
        )
        assert transition_result.exit_code == 0

        label_create = cli_runner.invoke(cli, ["label", "create", "timeline-label"])
        assert label_create.exit_code == 0

        label_assign = cli_runner.invoke(
            cli, ["label", "assign", "task", task_id, "timeline-label"]
        )
        assert label_assign.exit_code == 0

        timeline_result = cli_runner.invoke(
            cli,
            [
                "timeline",
                "workflow",
                "task",
                task_id,
                "--by",
                "timeline_tester",
                "--label",
                "timeline-label",
                "--format",
                "json",
            ],
        )
        assert timeline_result.exit_code == 0
        payload = json.loads(timeline_result.output)
        assert payload["transitions"]
        assert all(
            item["triggered_by"] == "timeline_tester" for item in payload["transitions"]
        )


class TestLocalTestCommands:
    """Tests for local test commands."""

    def test_local_test_run_attaches_evidence(
        self, cli_runner: CliRunner, temp_env: Path
    ):
        """Test running local tests with task evidence."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Local Project"])

        task_result = cli_runner.invoke(
            cli,
            ["task", "add", "Local Project", "Local Task"],
        )
        assert task_result.exit_code == 0
        task_id = _extract_id(task_result.output)

        command = f"{sys.executable} -c \"print('ok')\""
        run_result = cli_runner.invoke(
            cli,
            [
                "test",
                "run",
                str(temp_env),
                "-c",
                command,
                "--project",
                "Local Project",
                "--task-id",
                task_id,
                "--no-output",
            ],
        )
        assert run_result.exit_code == 0

        list_result = cli_runner.invoke(
            cli,
            [
                "task",
                "evidence",
                "list",
                task_id,
                "--include-test-runs",
                "--format",
                "json",
            ],
        )
        assert list_result.exit_code == 0
        payload = json.loads(list_result.output)
        assert payload["items"][0]["evidence_type"] == "test_run"


class TestWorkSnapshotCommands:
    """Tests for work snapshot CLI commands."""

    def test_work_snapshot_resolves_scope_name(
        self, cli_runner: CliRunner, temp_env: Path
    ):
        """Test work snapshot scope resolution by name."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Snapshot Project"])

        result = cli_runner.invoke(
            cli,
            [
                "work",
                "snapshot",
                "--scope-type",
                "project",
                "--scope",
                "Snapshot Project",
            ],
        )

        assert result.exit_code == 0
        _assert_plain_output_contains(
            result.output, "Work Snapshot (project)", "Scope: Snapshot Project"
        )


class TestQueueScopeCommands:
    """Tests for queue scope resolution and output."""

    def test_queue_create_update_json_output(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Queue mutation commands should expose machine-readable payloads."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Queue JSON Project"])

        create = cli_runner.invoke(
            cli,
            [
                "queue",
                "create",
                "JSON Queue",
                "--scope-type",
                "project",
                "--scope",
                "Queue JSON Project",
                "--filters",
                '{"status":["todo"]}',
                "--format",
                "json",
            ],
        )
        assert create.exit_code == 0, create.output
        create_payload = json.loads(create.output)
        queue_id = create_payload["queue"]["id"]
        assert create_payload["queue"]["name"] == "JSON Queue"
        assert create_payload["links"]["run"].startswith(_cli_step("queue run "))

        update = cli_runner.invoke(
            cli,
            [
                "queue",
                "update",
                queue_id,
                "--description",
                "Updated queue description",
                "--format",
                "json",
            ],
        )
        assert update.exit_code == 0, update.output
        update_payload = json.loads(update.output)
        assert update_payload["queue"]["description"] == "Updated queue description"
        assert update_payload["links"]["self"].startswith(_cli_step("queue show "))

    def test_queue_list_scope_resolution(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Test queue list scope resolution by name."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Queue Scope Project"])

        queue_result = cli_runner.invoke(
            cli,
            [
                "queue",
                "create",
                "Scoped Queue",
                "--scope-type",
                "project",
                "--scope",
                "Queue Scope Project",
                "--filters",
                '{"status":["todo"]}',
            ],
        )
        assert queue_result.exit_code == 0

        result = cli_runner.invoke(
            cli,
            [
                "queue",
                "list",
                "--scope-type",
                "project",
                "--scope",
                "Queue Scope Project",
            ],
        )

        assert result.exit_code == 0
        _assert_plain_output_contains(result.output, "Scoped Queue")

    def test_queue_run_shows_project_names(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Test queue run includes project names."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Queue Run Project"])
        cli_runner.invoke(
            cli,
            ["task", "add", "Queue Run Project", "Queue Task"],
        )

        queue_result = cli_runner.invoke(
            cli,
            [
                "queue",
                "create",
                "Run Queue",
                "--scope-type",
                "project",
                "--scope",
                "Queue Run Project",
                "--filters",
                '{"status":["todo"]}',
            ],
        )
        queue_id = _extract_id(queue_result.output)

        run_result = cli_runner.invoke(cli, ["queue", "run", queue_id])

        assert run_result.exit_code == 0
        assert "Project" in run_result.output
        assert "Queue Run Project" in run_result.output

    def test_queue_run_by_name(self, cli_runner: CliRunner, temp_env: Path) -> None:
        """Test queue run resolves by name."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Queue Name Project"])
        cli_runner.invoke(
            cli,
            ["task", "add", "Queue Name Project", "Queue Name Task"],
        )

        cli_runner.invoke(
            cli,
            [
                "queue",
                "create",
                "Named Queue",
                "--scope-type",
                "project",
                "--scope",
                "Queue Name Project",
                "--filters",
                '{"status":["todo"]}',
            ],
        )

        run_result = cli_runner.invoke(cli, ["queue", "run", "Named Queue"])

        assert run_result.exit_code == 0
        assert "Named Queue" in run_result.output

    def test_queue_list_scope_fields_json(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Test queue list includes scope labels in JSON output."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Queue JSON Project"])
        cli_runner.invoke(
            cli,
            [
                "queue",
                "create",
                "JSON Queue",
                "--scope-type",
                "project",
                "--scope",
                "Queue JSON Project",
                "--filters",
                '{"status":["todo"]}',
            ],
        )

        result = cli_runner.invoke(
            cli,
            [
                "queue",
                "list",
                "--format",
                "json",
                "--scope-type",
                "project",
                "--scope",
                "Queue JSON Project",
            ],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["items"][0]["scope_name"] == "Queue JSON Project"
        assert "scope_label" in payload["items"][0]

    def test_queue_show_delete_restore_by_name(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Test queue show/delete/restore works with names."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Queue Ops Project"])

        cli_runner.invoke(
            cli,
            [
                "queue",
                "create",
                "Ops Queue",
                "--scope-type",
                "project",
                "--scope",
                "Queue Ops Project",
                "--filters",
                '{"status":["todo"]}',
            ],
        )

        show_result = cli_runner.invoke(
            cli, ["queue", "show", "Ops Queue", "--format", "json"]
        )
        assert show_result.exit_code == 0
        payload = json.loads(show_result.output)
        assert payload["name"] == "Ops Queue"

        delete_result = cli_runner.invoke(cli, ["queue", "delete", "Ops Queue"])
        assert delete_result.exit_code == 0
        assert "Deleted queue" in delete_result.output

        restore_result = cli_runner.invoke(cli, ["queue", "restore", "Ops Queue"])
        assert restore_result.exit_code == 0
        assert "Restored queue" in restore_result.output

    def test_queue_create_conflicting_scope_selectors_fail_nonzero_in_json_mode(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(
            cli,
            [
                "queue",
                "create",
                "Bad Queue",
                "--scope-type",
                "project",
                "--scope",
                "Project A",
                "--scope-id",
                "project_123",
                "--format",
                "json",
            ],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert payload["error"] == "Use --scope or --scope-id, not both"

    def test_queue_list_requires_scope_type_for_scope_json(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(
            cli,
            ["queue", "list", "--scope", "Project A", "--format", "json"],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert payload["error"] == "Use --scope-type with --scope"


class TestWorkSnapshotCommands:
    """Tests for work snapshot review commands."""

    def test_work_snapshot_json_wrapper(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Test work snapshot JSON output wrapper."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Snapshot Project"])

        result = cli_runner.invoke(
            cli,
            [
                "work",
                "snapshot",
                "--scope-type",
                "project",
                "--scope",
                "Snapshot Project",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert "snapshot" in payload
        assert "links" in payload
        assert "params" in payload
        assert payload["links"]["self"].startswith(
            _cli_step("work snapshot --scope-type ")
        )

    def test_work_review_json_wrapper(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Test work review JSON output wrapper."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Review Project"])

        result = cli_runner.invoke(
            cli,
            [
                "work",
                "review",
                "--scope-type",
                "project",
                "--scope",
                "Review Project",
                "--reviewed-by",
                "tester",
                "--note",
                "Review note",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["reviewed_by"] == "tester"
        assert payload["note"] == "Review note"
        assert "links" in payload
        assert "params" in payload
        assert payload["links"]["self"].startswith(
            _cli_step("work review --scope-type ")
        )

    def test_work_snapshot_fails_nonzero_for_conflicting_scope_filters_json(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Snapshot Conflict Project"])

        result = cli_runner.invoke(
            cli,
            [
                "work",
                "snapshot",
                "--scope-type",
                "project",
                "--scope",
                "Snapshot Conflict Project",
                "--scope-id",
                "proj_conflict",
                "--format",
                "json",
            ],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert payload["error"] == "Use --scope or --scope-id, not both"

    def test_work_review_fails_nonzero_for_conflicting_scope_filters_json(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Review Conflict Project"])

        result = cli_runner.invoke(
            cli,
            [
                "work",
                "review",
                "--scope-type",
                "project",
                "--scope",
                "Review Conflict Project",
                "--scope-id",
                "proj_conflict",
                "--reviewed-by",
                "tester",
                "--format",
                "json",
            ],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert payload["error"] == "Use --scope or --scope-id, not both"

    def test_work_daily_fails_nonzero_for_conflicting_scope_filters_json(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Daily Conflict Project"])

        result = cli_runner.invoke(
            cli,
            [
                "work",
                "daily",
                "--scope-type",
                "project",
                "--scope",
                "Daily Conflict Project",
                "--scope-id",
                "proj_conflict",
                "--format",
                "json",
            ],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert payload["error"] == "Use --scope or --scope-id, not both"


class TestWorkDailyCommands:
    """Tests for work daily review command."""

    def test_work_daily_project_scope(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Test daily review output with project scope name."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Daily Project"])

        result = cli_runner.invoke(
            cli,
            [
                "work",
                "daily",
                "--scope-type",
                "project",
                "--scope",
                "Daily Project",
            ],
        )

        assert result.exit_code == 0
        _assert_plain_output_contains(
            result.output, "Daily Review (project)", "Queues:"
        )

    def test_work_daily_missing_project_scope_shows_recovery_steps(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Missing project scopes should point directly at recovery commands."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(
            cli,
            [
                "work",
                "daily",
                "--scope-type",
                "project",
                "--scope",
                "Missing Project",
            ],
        )

        assert result.exit_code == 0
        _assert_plain_output_contains(
            result.output,
            "Project 'Missing Project' not found",
            "pms project list --format json",
            "pms start --format json",
        )

    def test_work_daily_include_history(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Test daily review includes history when requested."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "History Project"])
        cli_runner.invoke(
            cli,
            [
                "work",
                "review",
                "--scope-type",
                "project",
                "--scope",
                "History Project",
                "--reviewed-by",
                "tester",
                "--note",
                "Initial review",
            ],
        )

        result = cli_runner.invoke(
            cli,
            [
                "work",
                "daily",
                "--scope-type",
                "project",
                "--scope",
                "History Project",
                "--include-history",
            ],
        )

        assert result.exit_code == 0
        _assert_plain_output_contains(result.output, "Review History", "Initial review")

    def test_work_daily_json_includes_guide_link(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Daily review JSON should link back to the global start guide."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Daily JSON Project"])

        result = cli_runner.invoke(
            cli,
            [
                "work",
                "daily",
                "--scope-type",
                "project",
                "--scope",
                "Daily JSON Project",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["purpose"].startswith("Scoped daily operator digest")
        assert payload["links"]["guide"] == _cli_step("start --format json")
        assert payload["links"]["self"].startswith(
            _cli_step("work daily --scope-type ")
        )
        assert payload["links"]["snapshot"].startswith(
            _cli_step("work snapshot --scope-type ")
        )
        assert payload["next_steps"][0].startswith(
            _cli_step("work review --scope-type ")
        )

    def test_work_daily_include_timeline(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Test daily review includes transitions."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Timeline Daily Project"])
        task_result = cli_runner.invoke(
            cli,
            ["task", "add", "Timeline Daily Project", "Timeline Task"],
        )
        task_id = _extract_id(task_result.output)
        cli_runner.invoke(cli, ["task", "start", task_id, "--by", "tester"])

        result = cli_runner.invoke(
            cli,
            [
                "work",
                "daily",
                "--scope-type",
                "project",
                "--scope",
                "Timeline Daily Project",
                "--include-timeline",
            ],
        )

        assert result.exit_code == 0
        _assert_plain_output_contains(
            result.output, "Recent Transitions", "Timeline Task"
        )

    def test_work_daily_export_attaches_evidence(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Test daily review export attaches evidence to a task."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Daily Export Project"])
        task_result = cli_runner.invoke(
            cli,
            ["task", "add", "Daily Export Project", "Daily Export Task"],
        )
        task_id = _extract_id(task_result.output)
        export_dir = temp_env / "exports"

        result = cli_runner.invoke(
            cli,
            [
                "work",
                "daily",
                "--scope-type",
                "project",
                "--scope",
                "Daily Export Project",
                "--export",
                str(export_dir),
                "--attach-task",
                task_id,
            ],
        )

        assert result.exit_code == 0
        exported_files = list(export_dir.glob("work-daily-project-*"))
        assert exported_files

        list_result = cli_runner.invoke(
            cli,
            ["task", "evidence", "list", task_id, "--format", "json"],
        )
        assert list_result.exit_code == 0
        payload = json.loads(list_result.output)
        entry = next(
            item
            for item in payload["items"]
            if item["evidence_type"] == "work_daily_report"
        )
        assert entry["metadata"]["file_size_bytes"] > 0

    def test_work_daily_export_cleans_up_file_when_attachment_fails(
        self,
        cli_runner: CliRunner,
        temp_env: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Combined export+attach should not leave an orphan file on late failure."""
        from pms.config.settings import reload_settings
        from pms.services.task_evidence_service import TaskEvidenceService

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Daily Export Failure Project"])
        task_result = cli_runner.invoke(
            cli,
            [
                "task",
                "add",
                "Daily Export Failure Project",
                "Daily Export Failure Task",
            ],
        )
        task_id = _extract_id(task_result.output)
        export_dir = temp_env / "exports"

        async def fail_add_evidence(self, *args, **kwargs):
            raise RuntimeError("attach failed")

        monkeypatch.setattr(TaskEvidenceService, "add_evidence", fail_add_evidence)

        result = cli_runner.invoke(
            cli,
            [
                "work",
                "daily",
                "--scope-type",
                "project",
                "--scope",
                "Daily Export Failure Project",
                "--export",
                str(export_dir),
                "--attach-task",
                task_id,
            ],
        )

        assert result.exit_code != 0
        _assert_plain_output_contains(
            result.output, "Failed to export daily review: attach failed"
        )
        assert not list(export_dir.glob("work-daily-project-*"))

        list_result = cli_runner.invoke(
            cli,
            ["task", "evidence", "list", task_id, "--format", "json"],
        )
        assert list_result.exit_code == 0
        payload = json.loads(list_result.output)
        assert not any(
            item["evidence_type"] == "work_daily_report" for item in payload["items"]
        )

    def test_work_daily_json_wrapper(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Test daily review JSON output wrapper."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Daily JSON Project"])

        result = cli_runner.invoke(
            cli,
            [
                "work",
                "daily",
                "--scope-type",
                "project",
                "--scope",
                "Daily JSON Project",
                "--format",
                "json",
                "--view",
                "overview",
            ],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert "snapshot" in payload
        assert "queues" in payload
        assert "links" in payload
        assert "params" in payload

    def test_work_daily_csv_output(self, cli_runner: CliRunner, temp_env: Path) -> None:
        """Test daily review CSV output."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Daily CSV Project"])

        result = cli_runner.invoke(
            cli,
            [
                "work",
                "daily",
                "--scope-type",
                "project",
                "--scope",
                "Daily CSV Project",
                "--format",
                "csv",
            ],
        )

        assert result.exit_code == 0
        assert result.output.splitlines()[0] == "section,field,value"


class TestLabelEntityFormats:
    """Tests for label list-entity format outputs."""

    def test_label_list_entity_json(self, cli_runner: CliRunner, temp_env: Path):
        """Test label list-entity JSON output."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Label Entity Project"])
        task_result = cli_runner.invoke(
            cli, ["task", "add", "Label Entity Project", "Label Entity Task"]
        )
        task_id = _extract_id(task_result.output)
        label_result = cli_runner.invoke(cli, ["label", "create", "Assigned Label"])
        label_name = "Assigned Label"
        _extract_id(label_result.output)

        assign_result = cli_runner.invoke(
            cli,
            ["label", "assign", "task", task_id, label_name, "--by", "tester"],
        )
        assert assign_result.exit_code == 0

        list_result = cli_runner.invoke(
            cli,
            [
                "label",
                "list-entity",
                "task",
                task_id,
                "--format",
                "json",
                "--view",
                "detail",
            ],
        )
        assert list_result.exit_code == 0
        payload = json.loads(list_result.output)
        assert "items" in payload
        assert payload["items"]
        assert payload["items"][0]["assignment"]["applied_by"] == "tester"

        assignment_id = payload["items"][0]["assignment"]["id"]
        history_result = cli_runner.invoke(
            cli,
            [
                "label",
                "assignment",
                "history",
                assignment_id,
                "--format",
                "json",
            ],
        )
        assert history_result.exit_code == 0
        history_payload = json.loads(history_result.output)
        assert history_payload["assignment"]["id"] == assignment_id
        assert history_payload["items"]


class TestQueuePresetFormats:
    """Tests for queue preset format outputs."""

    def test_queue_presets_json_wrapper(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Test queue presets JSON output wrapper."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Preset Project"])
        cli_runner.invoke(cli, ["task", "add", "Preset Project", "Preset Task"])

        result = cli_runner.invoke(
            cli,
            [
                "queue",
                "presets",
                "--project",
                "Preset Project",
                "--format",
                "json",
                "--view",
                "detail",
            ],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert "items" in payload
        assert payload["items"]
        assert "page" in payload
        assert "links" in payload
        ready_entry = next(item for item in payload["items"] if item["name"] == "ready")
        assert ready_entry["population"] == "scoped_project"
        assert ready_entry["total_count"] >= ready_entry["displayed_count"]
        assert "items" in ready_entry

    def test_queue_run_json_wrapper(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Test queue run JSON output wrapper."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Queue Run Project"])
        cli_runner.invoke(cli, ["task", "add", "Queue Run Project", "Queue Task"])

        queue_result = cli_runner.invoke(
            cli,
            [
                "queue",
                "create",
                "Queue Run",
                "--filters",
                '{"status":["todo"]}',
            ],
        )
        queue_id = _extract_id(queue_result.output)

        result = cli_runner.invoke(
            cli,
            ["queue", "run", queue_id, "--format", "json", "--limit", "5"],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert "items" in payload
        assert "page" in payload
        assert "links" in payload
        assert payload["links"]["guide"] == _cli_step("start --format json")
        assert "next_steps" in payload
        assert payload["next_steps"]

    def test_queue_and_work_surfaces_include_graph_navigation(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        fixture = _setup_actor_assignment_surface_fixture(cli_runner)

        queue_result = cli_runner.invoke(
            cli,
            [
                "queue",
                "create",
                "Actor Queue",
                "--scope-type",
                "project",
                "--scope",
                fixture["project_name"],
                "--filters",
                '{"status":["todo","in_progress"]}',
            ],
        )
        assert queue_result.exit_code == 0, queue_result.output
        queue_id = _extract_id(queue_result.output)

        run_result = cli_runner.invoke(
            cli,
            [
                "queue",
                "run",
                queue_id,
                "--format",
                "json",
                "--view",
                "review",
            ],
        )
        assert run_result.exit_code == 0, run_result.output
        run_payload = json.loads(run_result.output)
        assert (
            run_payload["focus_task"]["assignee"]["actor"]["handle"] == "alice-example"
        )
        assert run_payload["focus_task"]["links"]["actor"] == _cli_step(
            "actor show alice-example --format json"
        )
        assert run_payload["graph_navigation"]["basis"] == "focus_task"
        assert (
            run_payload["graph_navigation"]["task_id"]
            == run_payload["focus_task"]["id"]
        )
        assert run_payload["graph_navigation"]["links"]["actor"] == _cli_step(
            "actor show alice-example --format json"
        )

        presets_result = cli_runner.invoke(
            cli,
            [
                "queue",
                "presets",
                "--project",
                fixture["project_name"],
                "--format",
                "json",
                "--view",
                "detail",
            ],
        )
        assert presets_result.exit_code == 0, presets_result.output
        presets_payload = json.loads(presets_result.output)
        preset_actor_handle = presets_payload["focus_task"]["assignee"]["actor"][
            "handle"
        ]
        assert preset_actor_handle in {"alice-example", "security-persona"}
        assert presets_payload["focus_task"]["links"]["actor"] == _cli_step(
            f"actor show {preset_actor_handle} --format json"
        )
        assert presets_payload["graph_navigation"]["basis"] == "focus_task"
        assert (
            presets_payload["graph_navigation"]["task_id"]
            == presets_payload["focus_task"]["id"]
        )
        assert presets_payload["graph_navigation"]["links"]["actor"] == _cli_step(
            f"actor show {preset_actor_handle} --format json"
        )

        review_result = cli_runner.invoke(
            cli,
            [
                "work",
                "review",
                "--scope-type",
                "project",
                "--scope",
                fixture["project_name"],
                "--reviewed-by",
                "alice-example",
                "--format",
                "json",
            ],
        )
        assert review_result.exit_code == 0, review_result.output
        review_payload = json.loads(review_result.output)
        assert review_payload["graph_navigation"]["basis"] == "scope"
        assert review_payload["graph_navigation"]["links"]["project"] == _cli_step(
            f"project show {fixture['project_id']} --format json"
        )

        daily_result = cli_runner.invoke(
            cli,
            [
                "work",
                "daily",
                "--scope-type",
                "project",
                "--scope",
                fixture["project_name"],
                "--format",
                "json",
            ],
        )
        assert daily_result.exit_code == 0, daily_result.output
        daily_payload = json.loads(daily_result.output)
        daily_actor_handle = daily_payload["focus_task"]["assignee"]["actor"]["handle"]
        assert daily_actor_handle in {"alice-example", "security-persona"}
        assert daily_payload["focus_task"]["links"]["actor"] == _cli_step(
            f"actor show {daily_actor_handle} --format json"
        )
        assert daily_payload["graph_navigation"]["basis"] == "focus_task"
        assert (
            daily_payload["graph_navigation"]["task_id"]
            == daily_payload["focus_task"]["id"]
        )
        assert daily_payload["graph_navigation"]["links"]["actor"] == _cli_step(
            f"actor show {daily_actor_handle} --format json"
        )


class TestPlanUsability:
    """Tests for human-usable plan list/show surfaces."""

    def test_plan_create_yaml_requires_content_nonzero_in_json_mode(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Yaml Plan",
                "--format",
                "yaml",
                "--output-format",
                "json",
            ],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert payload["error"] == "Content required for YAML plans"

    def test_plan_create_invalid_json_content_fails_nonzero_in_json_mode(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Broken JSON Plan",
                "--content",
                "probe",
                "--format",
                "json",
                "--output-format",
                "json",
            ],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert "JSON plan content must be valid JSON" in payload["error"]

    def test_prefer_server_plan_create_invalid_json_content_fails_before_delegation(
        self, cli_runner: CliRunner, temp_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        delegation_used = {"value": False}

        async def _fake_delegate_plan_create_to_server(
            **kwargs: object,
        ) -> dict[str, object]:
            delegation_used["value"] = True
            return {"id": "should-not-be-called"}

        monkeypatch.setattr(
            "pms.cli.app._resolve_runtime_write_decision",
            lambda _action_name: RuntimeWriteDecision(
                allowed=True,
                use_server=True,
                payload=RuntimeServerPayload(
                    base_url="http://127.0.0.1:27541",
                    reachable=True,
                    status="healthy",
                    database="healthy",
                    error=None,
                    checked=True,
                    api_key_present=True,
                ),
                block_reason=None,
            ),
        )
        monkeypatch.setattr(
            "pms.cli.app._delegate_plan_create_to_server",
            _fake_delegate_plan_create_to_server,
        )

        cli_runner.invoke(cli, ["init"])
        result = cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Broken Delegated JSON Plan",
                "--content",
                "probe",
                "--format",
                "json",
                "--output-format",
                "json",
            ],
        )

        assert result.exit_code != 0
        assert delegation_used["value"] is False
        payload = json.loads(result.output)
        assert "JSON plan content must be valid JSON" in payload["error"]

    def test_plan_list_shows_short_refs_and_runnable_next_steps(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Plan list should expose short refs and runnable follow-up commands."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["quickstart", "--defaults"])
        cli_runner.invoke(cli, ["quickstart", "--defaults"])

        result = cli_runner.invoke(cli, ["plan", "list"])
        normalized_output = _normalize_cli_output(result.output)

        assert result.exit_code == 0
        _assert_plain_output_contains(result.output, "Ref", "Next:\n- ")
        assert _cli_step("plan show ") in normalized_output
        assert _cli_step("plan lineage --plan-id ") in normalized_output

    def test_plan_list_prefers_active_plan_for_generic_next_steps(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Plan list should not anchor generic plan actions on archived rows."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Archived Plan Project"])
        active_task_result = cli_runner.invoke(
            cli, ["task", "add", "Archived Plan Project", "Active Plan Task"]
        )
        active_task_id = _extract_id(active_task_result.output)
        active_plan_result = cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Live Plan",
                "--project",
                "Archived Plan Project",
                "--status",
                "active",
                "--task-id",
                active_task_id,
                "--content",
                "{}",
                "--format",
                "json",
            ],
        )
        active_plan_id = _extract_id(active_plan_result.output)
        archived_plan_result = cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Archived Plan",
                "--project",
                "Archived Plan Project",
                "--status",
                "archived",
                "--content",
                "{}",
                "--format",
                "json",
            ],
        )
        archived_plan_id = _extract_id(archived_plan_result.output)

        result = cli_runner.invoke(cli, ["plan", "list"])

        assert result.exit_code == 0
        assert (
            _cli_step(f"plan show {active_plan_id.split('-', 1)[0]}") in result.output
        )
        assert (
            _cli_step(f"plan show {archived_plan_id.split('-', 1)[0]}")
            not in result.output
        )

    def test_plan_list_active_scope_does_not_append_completed_plan_next_steps(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Live Plan Scope Project"])
        active_task = cli_runner.invoke(
            cli, ["task", "add", "Live Plan Scope Project", "Active Plan Task"]
        )
        active_task_id = _extract_id(active_task.output)
        create_result = cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Live Scope Plan",
                "--project",
                "Live Plan Scope Project",
                "--status",
                "active",
                "--task-id",
                active_task_id,
                "--content",
                "{}",
                "--format",
                "json",
            ],
        )
        cli_runner.invoke(cli, ["project", "create", "Completed Plan Scope Project"])
        done_task = cli_runner.invoke(
            cli, ["task", "add", "Completed Plan Scope Project", "Done Task"]
        )
        done_task_id = _extract_id(done_task.output)
        cli_runner.invoke(cli, ["task", "complete", done_task_id, "--by", "tester"])
        cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Completed Scope Plan",
                "--project",
                "Completed Plan Scope Project",
                "--status",
                "completed",
                "--task-id",
                done_task_id,
                "--content",
                "{}",
                "--format",
                "json",
            ],
        )

        result = cli_runner.invoke(cli, ["plan", "list", "--format", "json"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["scope"]["active_visible_plans"] == 1
        assert all(
            step
            != _cli_step(
                'plan show "Completed Scope Plan" --project "Completed Plan Scope Project"'
            )
            for step in payload["next_steps"]
        )

    def test_plan_show_accepts_short_id_and_partial_project_name(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Plan resolution should accept short ID refs and unique name prefixes."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Platform Capability Extension"])
        create_result = cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Capability Extension Delivery Plan",
                "--project",
                "Platform Capability Extension",
                "--content",
                "{}",
            ],
        )
        plan_id = _extract_id(create_result.output)
        short_ref = plan_id.split("-", 1)[0]

        show_by_ref = cli_runner.invoke(cli, ["plan", "show", short_ref])
        assert show_by_ref.exit_code == 0
        assert "Capability Extension Delivery Plan" in show_by_ref.output

        show_by_prefix = cli_runner.invoke(
            cli,
            [
                "plan",
                "show",
                "Capability Extension",
                "--project",
                "Platform Capability",
            ],
        )
        assert show_by_prefix.exit_code == 0
        assert "Capability Extension Delivery Plan" in show_by_prefix.output

    def test_plan_json_surfaces_use_normalized_runnable_commands(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Plan JSON links and next steps should use the normalized CLI wrapper."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Plan Json Project"])
        plan_result = cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Plan Json Delivery",
                "--project",
                "Plan Json Project",
                "--content",
                "{}",
                "--format",
                "json",
                "--output-format",
                "json",
            ],
        )
        assert plan_result.exit_code == 0, plan_result.output
        plan_id = json.loads(plan_result.output)["plan"]["id"]

        list_result = cli_runner.invoke(cli, ["plan", "list", "--format", "json"])
        assert list_result.exit_code == 0
        list_payload = json.loads(list_result.output)
        assert list_payload["links"]["self"].startswith(_cli_step("plan list"))
        assert all(
            step.startswith("uv run pms ") for step in list_payload["next_steps"]
        )
        list_item = next(
            item for item in list_payload["items"] if item["id"] == plan_id
        )
        assert list_item["links"]["self"].startswith(_cli_step("plan show"))
        assert list_item["links"]["lineage"].startswith(_cli_step("plan lineage"))

        show_result = cli_runner.invoke(
            cli,
            ["plan", "show", plan_id, "--format", "json"],
        )
        assert show_result.exit_code == 0
        show_payload = json.loads(show_result.output)
        assert show_payload["links"]["self"].startswith(_cli_step("plan show"))
        assert show_payload["links"]["lineage"].startswith(_cli_step("plan lineage"))
        assert all(
            step.startswith("uv run pms ") for step in show_payload["next_steps"]
        )

        lineage_result = cli_runner.invoke(
            cli,
            ["plan", "lineage", "--plan-id", plan_id, "--format", "json"],
        )
        assert lineage_result.exit_code == 0
        lineage_payload = json.loads(lineage_result.output)
        assert lineage_payload["links"]["self"].startswith(_cli_step("plan lineage"))
        assert all(
            step.startswith("uv run pms ") for step in lineage_payload["next_steps"]
        )
        if lineage_payload["items"]:
            lineage_item = lineage_payload["items"][0]
            assert lineage_item["links"]["plan"].startswith(_cli_step("plan show"))
            assert lineage_item["links"]["lineage"].startswith(
                _cli_step("plan lineage")
            )

    def test_task_show_and_plan_list_preserve_reverse_plan_refs(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Reverse Link Project"])
        linked_task_id = _extract_id(
            cli_runner.invoke(
                cli, ["task", "add", "Reverse Link Project", "Reverse Linked Task"]
            ).output
        )
        unrelated_task_id = _extract_id(
            cli_runner.invoke(
                cli, ["task", "add", "Reverse Link Project", "Reverse Unrelated Task"]
            ).output
        )
        linked_plan_id = _extract_id(
            cli_runner.invoke(
                cli,
                [
                    "plan",
                    "create",
                    "Reverse Linked Plan",
                    "--project",
                    "Reverse Link Project",
                    "--task-id",
                    linked_task_id,
                    "--content",
                    "{}",
                ],
            ).output
        )
        cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Reverse Unrelated Plan",
                "--project",
                "Reverse Link Project",
                "--task-id",
                unrelated_task_id,
                "--content",
                "{}",
            ],
        )

        task_show = cli_runner.invoke(
            cli,
            ["task", "show", linked_task_id, "--include-linked", "--format", "json"],
        )
        assert task_show.exit_code == 0, task_show.output
        task_payload = json.loads(task_show.output)
        assert task_payload["links"]["plans"] == _cli_step(
            f"plan list --task-id {linked_task_id} --format json"
        )
        assert task_payload["linked_plan_count"] == 1
        assert task_payload["linked_plans"][0]["id"] == linked_plan_id
        assert task_payload["linked"]["plans"][0]["id"] == linked_plan_id

        filtered_list = cli_runner.invoke(
            cli,
            ["plan", "list", "--task-id", linked_task_id, "--format", "json"],
        )
        assert filtered_list.exit_code == 0, filtered_list.output
        filtered_payload = json.loads(filtered_list.output)
        assert filtered_payload["links"]["self"].startswith(
            _cli_step(f"plan list --format json --task-id {linked_task_id}")
        )
        assert [item["id"] for item in filtered_payload["items"]] == [linked_plan_id]

    def test_plan_list_surfaces_scope_status_groups_and_recent_completed(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Active Plan Project"])
        active_task_result = cli_runner.invoke(
            cli, ["task", "add", "Active Plan Project", "Active Task"]
        )
        active_task_id = _extract_id(active_task_result.output)
        cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Active Plan",
                "--project",
                "Active Plan Project",
                "--status",
                "active",
                "--task-id",
                active_task_id,
                "--content",
                "{}",
            ],
        )
        cli_runner.invoke(cli, ["project", "create", "Completed Plan Project"])
        completed_plan_result = cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Completed Plan",
                "--project",
                "Completed Plan Project",
                "--status",
                "completed",
                "--content",
                "{}",
                "--format",
                "json",
            ],
        )
        completed_plan_id = _extract_id(completed_plan_result.output)

        json_result = cli_runner.invoke(cli, ["plan", "list", "--format", "json"])

        assert json_result.exit_code == 0, json_result.output
        payload = json.loads(json_result.output)
        assert payload["scope"]["kind"] == "instance_plan_list"
        assert "Completed scoped work remains terminal" in payload["scope"]["summary"]
        assert (
            "Recently completed plans remain terminal"
            in payload["completion_context"]["summary"]
        )
        assert payload["status_groups"]["active"] >= 1
        assert payload["status_groups"]["completed"] >= 1
        assert set(payload["items_by_status"]) == {
            "active",
            "draft",
            "completed",
            "archived",
        }
        assert payload["status_groups"]["completed"] == len(
            payload["items_by_status"]["completed"]
        )
        completed_item = next(
            item
            for item in payload["recently_completed_plans"]
            if item["id"] == completed_plan_id
        )
        assert completed_item["status"] == "completed"
        assert completed_item["stored_status"] == "completed"
        assert completed_item["format"] == "json"
        assert completed_item["project_name"] == "Completed Plan Project"
        assert completed_item["last_activity_at"] is not None
        assert completed_item["last_transition_at"] is not None
        assert completed_item["terminal_reason"] == "plan is already marked completed"

        text_result = cli_runner.invoke(cli, ["plan", "list"])
        assert text_result.exit_code == 0, text_result.output
        _assert_plain_output_contains(
            text_result.output,
            "Scope: Instance-wide plan list view.",
            "Active Plans",
            "Draft Plans",
            "Completed Plans",
            "Archived Plans",
            "Recently Completed Plans:",
        )

    def test_plan_list_orders_active_plans_by_rolled_up_last_activity(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(
            cli, ["project", "create", "Plan Activity Ordering Project A"]
        )
        first_task_id = _extract_id(
            cli_runner.invoke(
                cli,
                [
                    "task",
                    "add",
                    "Plan Activity Ordering Project A",
                    "Earlier Linked Task",
                ],
            ).output
        )
        first_plan_id = _extract_id(
            cli_runner.invoke(
                cli,
                [
                    "plan",
                    "create",
                    "Earlier Plan",
                    "--project",
                    "Plan Activity Ordering Project A",
                    "--status",
                    "active",
                    "--task-id",
                    first_task_id,
                    "--content",
                    "{}",
                ],
            ).output
        )
        cli_runner.invoke(
            cli, ["project", "create", "Plan Activity Ordering Project B"]
        )
        second_task_id = _extract_id(
            cli_runner.invoke(
                cli,
                [
                    "task",
                    "add",
                    "Plan Activity Ordering Project B",
                    "Later Linked Task",
                ],
            ).output
        )
        second_plan_id = _extract_id(
            cli_runner.invoke(
                cli,
                [
                    "plan",
                    "create",
                    "Later Plan",
                    "--project",
                    "Plan Activity Ordering Project B",
                    "--status",
                    "active",
                    "--task-id",
                    second_task_id,
                    "--content",
                    "{}",
                ],
            ).output
        )
        progress_result = cli_runner.invoke(
            cli,
            [
                "task",
                "progress",
                first_task_id,
                "35",
                "Fresh linked execution activity",
                "--by",
                "tester",
                "--format",
                "json",
            ],
        )
        assert progress_result.exit_code == 0, progress_result.output

        list_result = cli_runner.invoke(cli, ["plan", "list", "--format", "json"])

        assert list_result.exit_code == 0, list_result.output
        payload = json.loads(list_result.output)
        active_items = [
            item
            for item in payload["items"]
            if item["status"] == "active"
            and item["id"] in {first_plan_id, second_plan_id}
        ]
        assert [item["id"] for item in active_items[:2]] == [
            first_plan_id,
            second_plan_id,
        ]
        assert active_items[0]["last_activity_at"] is not None

    def test_plan_list_orders_project_scoped_plans_by_nested_project_activity(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Plan Activity Project A"])
        first_plan_id = _extract_id(
            cli_runner.invoke(
                cli,
                [
                    "plan",
                    "create",
                    "Project Scoped Plan A",
                    "--project",
                    "Plan Activity Project A",
                    "--status",
                    "draft",
                    "--content",
                    "{}",
                ],
            ).output
        )
        cli_runner.invoke(cli, ["project", "create", "Plan Activity Project B"])
        second_plan_id = _extract_id(
            cli_runner.invoke(
                cli,
                [
                    "plan",
                    "create",
                    "Project Scoped Plan B",
                    "--project",
                    "Plan Activity Project B",
                    "--status",
                    "draft",
                    "--content",
                    "{}",
                ],
            ).output
        )
        task_id = _extract_id(
            cli_runner.invoke(
                cli,
                ["task", "add", "Plan Activity Project A", "Nested Project Task"],
            ).output
        )
        progress_result = cli_runner.invoke(
            cli,
            [
                "task",
                "progress",
                task_id,
                "55",
                "Nested project activity",
                "--by",
                "tester",
                "--format",
                "json",
            ],
        )
        assert progress_result.exit_code == 0, progress_result.output

        list_result = cli_runner.invoke(cli, ["plan", "list", "--format", "json"])

        assert list_result.exit_code == 0, list_result.output
        payload = json.loads(list_result.output)
        matching_items = [
            item
            for item in payload["items"]
            if item["id"] in {first_plan_id, second_plan_id}
        ]
        assert [item["id"] for item in matching_items[:2]] == [
            first_plan_id,
            second_plan_id,
        ]
        assert matching_items[0]["status"] == "draft"
        assert matching_items[0]["stored_status"] == "draft"
        assert matching_items[0]["last_activity_at"] is not None

    def test_plan_list_orders_project_scoped_plans_by_project_comment_activity(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        first_project_id = _extract_id(
            cli_runner.invoke(
                cli, ["project", "create", "Plan Comment Project A"]
            ).output
        )
        first_plan_id = _extract_id(
            cli_runner.invoke(
                cli,
                [
                    "plan",
                    "create",
                    "Project Comment Plan A",
                    "--project",
                    "Plan Comment Project A",
                    "--status",
                    "draft",
                    "--content",
                    "{}",
                ],
            ).output
        )
        cli_runner.invoke(cli, ["project", "create", "Plan Comment Project B"])
        second_plan_id = _extract_id(
            cli_runner.invoke(
                cli,
                [
                    "plan",
                    "create",
                    "Project Comment Plan B",
                    "--project",
                    "Plan Comment Project B",
                    "--status",
                    "draft",
                    "--content",
                    "{}",
                ],
            ).output
        )
        comment_result = cli_runner.invoke(
            cli,
            [
                "comment",
                "add",
                "project",
                first_project_id,
                "Fresh project discussion",
                "--by",
                "tester",
            ],
        )
        assert comment_result.exit_code == 0, comment_result.output

        list_result = cli_runner.invoke(cli, ["plan", "list", "--format", "json"])

        assert list_result.exit_code == 0, list_result.output
        payload = json.loads(list_result.output)
        matching_items = [
            item
            for item in payload["items"]
            if item["id"] in {first_plan_id, second_plan_id}
        ]
        assert [item["id"] for item in matching_items[:2]] == [
            first_plan_id,
            second_plan_id,
        ]
        assert matching_items[0]["status"] == "draft"
        assert matching_items[0]["stored_status"] == "draft"
        assert matching_items[0]["last_activity_at"] is not None

    def test_plan_list_surfaces_nested_goal_transition_as_last_transition(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Plan Transition CLI Project"])
        goal_id = _extract_id(
            cli_runner.invoke(
                cli,
                [
                    "goal",
                    "create",
                    "Plan Transition CLI Goal",
                    "--project",
                    "Plan Transition CLI Project",
                ],
            ).output
        )
        plan_id = _extract_id(
            cli_runner.invoke(
                cli,
                [
                    "plan",
                    "create",
                    "Plan Transition CLI Plan",
                    "--project",
                    "Plan Transition CLI Project",
                    "--status",
                    "draft",
                    "--content",
                    "{}",
                ],
            ).output
        )
        update_result = cli_runner.invoke(
            cli,
            [
                "goal",
                "update",
                goal_id,
                "--status",
                "on_hold",
                "--progress",
                "10",
                "--format",
                "json",
            ],
        )
        assert update_result.exit_code == 0, update_result.output

        list_result = cli_runner.invoke(cli, ["plan", "list", "--format", "json"])

        assert list_result.exit_code == 0, list_result.output
        payload = json.loads(list_result.output)
        item = next(item for item in payload["items"] if item["id"] == plan_id)
        assert item["last_transition_at"] is not None
        assert item["last_transition_at"] > item["updated_at"]

    def test_plan_list_reports_freshest_visible_graph_rollups(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Freshest Plan Project A"])
        cli_runner.invoke(cli, ["project", "create", "Freshest Plan Project B"])

        older_plan_id = _extract_id(
            cli_runner.invoke(
                cli,
                [
                    "plan",
                    "create",
                    "Older Visible Plan",
                    "--project",
                    "Freshest Plan Project A",
                    "--status",
                    "active",
                    "--content",
                    "{}",
                ],
            ).output
        )
        goal_id = _extract_id(
            cli_runner.invoke(
                cli,
                [
                    "goal",
                    "create",
                    "Freshest Plan Goal",
                    "--project",
                    "Freshest Plan Project B",
                ],
            ).output
        )
        freshest_plan_id = _extract_id(
            cli_runner.invoke(
                cli,
                [
                    "plan",
                    "create",
                    "Freshest Visible Plan",
                    "--project",
                    "Freshest Plan Project B",
                    "--status",
                    "draft",
                    "--content",
                    "{}",
                ],
            ).output
        )
        update_result = cli_runner.invoke(
            cli,
            [
                "goal",
                "update",
                goal_id,
                "--status",
                "on_hold",
                "--progress",
                "15",
                "--format",
                "json",
            ],
        )
        assert update_result.exit_code == 0, update_result.output

        list_result = cli_runner.invoke(cli, ["plan", "list", "--format", "json"])
        assert list_result.exit_code == 0, list_result.output
        payload = json.loads(list_result.output)

        assert payload["freshest_visible_activity"]["plan_id"] == freshest_plan_id
        assert payload["freshest_visible_transition"]["plan_id"] == freshest_plan_id
        assert payload["freshest_visible_activity"]["plan_id"] != older_plan_id

        text_result = cli_runner.invoke(cli, ["plan", "list"])
        assert text_result.exit_code == 0, text_result.output
        _assert_plain_output_contains(
            text_result.output,
            "Freshest Visible Activity:",
            "Freshest Visible Transition:",
            "Freshest Visible Plan",
        )

    def test_plan_list_freshest_visible_activity_and_transition_survive_pagination_offset(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Older Offset Plan Project"])
        older_plan_id = _extract_id(
            cli_runner.invoke(
                cli,
                [
                    "plan",
                    "create",
                    "Older Offset Plan",
                    "--project",
                    "Older Offset Plan Project",
                    "--status",
                    "active",
                    "--content",
                    "{}",
                    "--format",
                    "json",
                ],
            ).output
        )
        cli_runner.invoke(cli, ["project", "create", "Fresher Offset Plan Project"])
        fresher_plan_id = _extract_id(
            cli_runner.invoke(
                cli,
                [
                    "plan",
                    "create",
                    "Fresher Offset Plan",
                    "--project",
                    "Fresher Offset Plan Project",
                    "--status",
                    "active",
                    "--content",
                    "{}",
                    "--format",
                    "json",
                ],
            ).output
        )
        task_id = _extract_id(
            cli_runner.invoke(
                cli,
                ["task", "add", "Fresher Offset Plan Project", "Fresher Offset Task"],
            ).output
        )
        cli_runner.invoke(
            cli,
            ["task", "start", task_id, "--by", "tester", "--format", "json"],
        )
        cli_runner.invoke(
            cli,
            [
                "task",
                "progress",
                task_id,
                "20",
                "Freshest offset plan activity",
                "--by",
                "tester",
                "--format",
                "json",
            ],
        )

        result = cli_runner.invoke(
            cli,
            ["plan", "list", "--format", "json", "--limit", "1", "--offset", "1"],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert [item["name"] for item in payload["items"]] == ["Older Offset Plan"]
        assert payload["freshest_visible_activity"]["plan_id"] == fresher_plan_id
        assert payload["freshest_visible_transition"]["plan_id"] == fresher_plan_id
        assert payload["freshest_visible_activity"]["plan_id"] != older_plan_id

    def test_plan_list_text_shows_empty_status_categories(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Completed Only Project"])
        cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Completed Only Plan",
                "--project",
                "Completed Only Project",
                "--status",
                "completed",
                "--content",
                "{}",
            ],
        )

        result = cli_runner.invoke(cli, ["plan", "list"])
        assert result.exit_code == 0, result.output
        _assert_plain_output_contains(
            result.output,
            "Active Plans",
            "Draft Plans",
            "Completed Plans",
            "Archived Plans",
            "(none)",
        )

    def test_plan_list_hides_redundant_format_column_when_constant(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Column Noise Project"])
        cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Json Plan A",
                "--project",
                "Column Noise Project",
                "--status",
                "active",
                "--content",
                "{}",
            ],
        )
        cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Json Plan B",
                "--project",
                "Column Noise Project",
                "--status",
                "active",
                "--content",
                "{}",
            ],
        )

        result = cli_runner.invoke(cli, ["plan", "list"])
        assert result.exit_code == 0, result.output
        plain_output = _assert_plain_output_contains(
            result.output,
            "Active Plans",
            "Status groups: active 2",
        )
        assert "Format" not in plain_output

    def test_plan_update_supports_json_output_for_status_only_changes(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Plan Update Project"])
        create_result = cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Plan Update Plan",
                "--project",
                "Plan Update Project",
                "--status",
                "active",
                "--content",
                "{}",
            ],
        )
        assert create_result.exit_code == 0, create_result.output

        update_result = cli_runner.invoke(
            cli,
            [
                "plan",
                "update",
                "Plan Update Plan",
                "--project",
                "Plan Update Project",
                "--status",
                "archived",
                "--output-format",
                "json",
            ],
        )
        assert update_result.exit_code == 0, update_result.output
        payload = json.loads(update_result.output)
        assert payload["plan"]["status"] == "archived"
        assert payload["links"]["self"].startswith(_cli_step("plan show"))

        show_result = cli_runner.invoke(
            cli,
            [
                "plan",
                "show",
                "Plan Update Plan",
                "--project",
                "Plan Update Project",
                "--format",
                "json",
            ],
        )
        assert show_result.exit_code == 0, show_result.output
        assert json.loads(show_result.output)["status"] == "archived"

    def test_plan_update_format_flag_without_content_shows_clear_guidance(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Plan Format Project"])
        cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Plan Format Plan",
                "--project",
                "Plan Format Project",
                "--status",
                "active",
                "--content",
                "{}",
            ],
        )

        result = cli_runner.invoke(
            cli,
            [
                "plan",
                "update",
                "Plan Format Plan",
                "--project",
                "Plan Format Project",
                "--status",
                "archived",
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0, result.output
        _assert_plain_output_contains(
            result.output,
            "Use --format only when replacing plan content",
            "--output-format json",
        )

    def test_plan_update_task_links_are_additive_by_default_and_support_explicit_replace(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Plan Link Project"])
        first_task = cli_runner.invoke(
            cli,
            [
                "task",
                "create",
                "First Task",
                "--project",
                "Plan Link Project",
                "--format",
                "json",
            ],
        )
        second_task = cli_runner.invoke(
            cli,
            [
                "task",
                "create",
                "Second Task",
                "--project",
                "Plan Link Project",
                "--format",
                "json",
            ],
        )
        third_task = cli_runner.invoke(
            cli,
            [
                "task",
                "create",
                "Third Task",
                "--project",
                "Plan Link Project",
                "--format",
                "json",
            ],
        )
        assert first_task.exit_code == 0, first_task.output
        assert second_task.exit_code == 0, second_task.output
        assert third_task.exit_code == 0, third_task.output
        first_task_id = json.loads(first_task.output)["task"]["id"]
        second_task_id = json.loads(second_task.output)["task"]["id"]
        third_task_id = json.loads(third_task.output)["task"]["id"]

        create_result = cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Plan Link Plan",
                "--project",
                "Plan Link Project",
                "--status",
                "active",
                "--task-id",
                first_task_id,
                "--content",
                "{}",
            ],
        )
        assert create_result.exit_code == 0, create_result.output

        add_result = cli_runner.invoke(
            cli,
            [
                "plan",
                "update",
                "Plan Link Plan",
                "--project",
                "Plan Link Project",
                "--task-id",
                second_task_id,
                "--output-format",
                "json",
            ],
        )
        assert add_result.exit_code == 0, add_result.output
        add_payload = json.loads(add_result.output)
        assert add_payload["task_link_update"]["mode"] == "mutate"
        assert add_payload["plan"]["task_ids"] == [first_task_id, second_task_id]

        remove_result = cli_runner.invoke(
            cli,
            [
                "plan",
                "update",
                "Plan Link Plan",
                "--project",
                "Plan Link Project",
                "--remove-task-id",
                first_task_id,
                "--output-format",
                "json",
            ],
        )
        assert remove_result.exit_code == 0, remove_result.output
        remove_payload = json.loads(remove_result.output)
        assert remove_payload["plan"]["task_ids"] == [second_task_id]

        replace_result = cli_runner.invoke(
            cli,
            [
                "plan",
                "update",
                "Plan Link Plan",
                "--project",
                "Plan Link Project",
                "--replace-task-id",
                third_task_id,
                "--output-format",
                "json",
            ],
        )
        assert replace_result.exit_code == 0, replace_result.output
        replace_payload = json.loads(replace_result.output)
        assert replace_payload["task_link_update"]["mode"] == "replace"
        assert replace_payload["plan"]["task_ids"] == [third_task_id]

    def test_plan_update_rejects_mixed_replace_and_incremental_task_link_options(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Plan Replace Guard Project"])
        task_result = cli_runner.invoke(
            cli,
            [
                "task",
                "create",
                "Guard Task",
                "--project",
                "Plan Replace Guard Project",
                "--format",
                "json",
            ],
        )
        assert task_result.exit_code == 0, task_result.output
        task_id = json.loads(task_result.output)["task"]["id"]
        cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Plan Replace Guard",
                "--project",
                "Plan Replace Guard Project",
                "--status",
                "active",
                "--task-id",
                task_id,
                "--content",
                "{}",
            ],
        )

        result = cli_runner.invoke(
            cli,
            [
                "plan",
                "update",
                "Plan Replace Guard",
                "--project",
                "Plan Replace Guard Project",
                "--task-id",
                task_id,
                "--replace-task-id",
                task_id,
            ],
        )
        assert result.exit_code == 0, result.output
        _assert_plain_output_contains(
            result.output, "Do not mix --replace-task/--replace-task-id"
        )

    def test_default_operator_lists_hide_fixture_generated_projects_and_plans(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Operator Visible Project"])
        cli_runner.invoke(cli, ["project", "create", "Runtime Repro Project 9"])
        cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Operator Visible Plan",
                "--project",
                "Operator Visible Project",
                "--status",
                "active",
                "--content",
                "{}",
            ],
        )
        cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Runtime Repro Project 9 Plan",
                "--project",
                "Runtime Repro Project 9",
                "--status",
                "active",
                "--content",
                "{}",
            ],
        )

        project_list = cli_runner.invoke(cli, ["project", "list", "--format", "json"])
        assert project_list.exit_code == 0, project_list.output
        project_payload = json.loads(project_list.output)
        assert any(
            item["name"] == "Operator Visible Project"
            for item in project_payload["items"]
        )
        assert not any(
            item["name"] == "Runtime Repro Project 9"
            for item in project_payload["items"]
        )

        plan_list = cli_runner.invoke(cli, ["plan", "list", "--format", "json"])
        assert plan_list.exit_code == 0, plan_list.output
        plan_payload = json.loads(plan_list.output)
        assert any(
            item["name"] == "Operator Visible Plan" for item in plan_payload["items"]
        )
        assert not any(
            item["name"] == "Runtime Repro Project 9 Plan"
            for item in plan_payload["items"]
        )

        project_list_all = cli_runner.invoke(
            cli, ["project", "list", "--include-generated", "--format", "json"]
        )
        assert project_list_all.exit_code == 0, project_list_all.output
        project_payload_all = json.loads(project_list_all.output)
        assert any(
            item["name"] == "Runtime Repro Project 9"
            for item in project_payload_all["items"]
        )

        plan_list_all = cli_runner.invoke(
            cli, ["plan", "list", "--include-generated", "--format", "json"]
        )
        assert plan_list_all.exit_code == 0, plan_list_all.output
        plan_payload_all = json.loads(plan_list_all.output)
        assert any(
            item["name"] == "Runtime Repro Project 9 Plan"
            for item in plan_payload_all["items"]
        )

    def test_plan_show_human_view_renders_tasks_one_per_line(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Plan Human Project"])
        first_task_id = _extract_id(
            cli_runner.invoke(
                cli, ["task", "add", "Plan Human Project", "First Long Plan Task"]
            ).output
        )
        second_task_id = _extract_id(
            cli_runner.invoke(
                cli, ["task", "add", "Plan Human Project", "Second Long Plan Task"]
            ).output
        )
        cli_runner.invoke(cli, ["task", "start", second_task_id, "--by", "tester"])
        plan_id = _extract_id(
            cli_runner.invoke(
                cli,
                [
                    "plan",
                    "create",
                    "Human Plan",
                    "--project",
                    "Plan Human Project",
                    "--task-id",
                    first_task_id,
                    "--task-id",
                    second_task_id,
                    "--content",
                    "{}",
                ],
            ).output
        )

        result = cli_runner.invoke(cli, ["plan", "show", plan_id])

        assert result.exit_code == 0, result.output
        _assert_plain_output_contains(
            result.output,
            "Tasks (2):",
            "Summary: in_progress 1 | todo 1",
            "- First Long Plan Task (todo)",
            "- Second Long Plan Task (in_progress)",
        )

    def test_completed_plan_show_uses_terminal_completion_context(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Completed Show Project"])
        plan_result = cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Completed Show Plan",
                "--project",
                "Completed Show Project",
                "--status",
                "completed",
                "--content",
                "{}",
                "--format",
                "json",
            ],
        )
        plan_id = _extract_id(plan_result.output)

        json_result = cli_runner.invoke(
            cli, ["plan", "show", plan_id, "--format", "json"]
        )
        assert json_result.exit_code == 0, json_result.output
        payload = json.loads(json_result.output)
        assert payload["terminal_reason"] == "plan is already marked completed"
        assert "This plan is terminal." in payload["completion_context"]["summary"]
        assert not any("plan update" in step for step in payload["next_steps"])

        text_result = cli_runner.invoke(cli, ["plan", "show", plan_id])
        assert text_result.exit_code == 0, text_result.output
        _assert_plain_output_contains(text_result.output, "This plan is terminal.")
        assert "plan update" not in text_result.output

    def test_plan_create_and_update_reject_literal_null_link_ids(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        invalid_create = cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Bad Plan",
                "--project-id",
                "null",
                "--content",
                "{}",
            ],
        )
        assert invalid_create.exit_code != 0
        assert (
            "project_id cannot be the literal placeholder 'null'"
            in invalid_create.output
        )

        cli_runner.invoke(cli, ["project", "create", "Plan Link Project"])
        goal_result = cli_runner.invoke(
            cli,
            [
                "goal",
                "create",
                "Plan Link Goal",
                "--project",
                "Plan Link Project",
                "--format",
                "json",
            ],
        )
        goal_id = json.loads(goal_result.output)["goal"]["id"]
        plan_result = cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Valid Plan",
                "--project",
                "Plan Link Project",
                "--goal-id",
                goal_id,
                "--content",
                "{}",
                "--format",
                "json",
            ],
        )
        plan_id = _extract_id(plan_result.output)

        invalid_update = cli_runner.invoke(
            cli,
            ["plan", "update", plan_id, "--goal-id", "null"],
        )
        assert invalid_update.exit_code != 0
        assert (
            "goal_id cannot be the literal placeholder 'null'" in invalid_update.output
        )

    def test_plan_update_json_includes_runtime_write_context(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Runtime Update Project"])
        create_result = cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Runtime Update Plan",
                "--project",
                "Runtime Update Project",
                "--content",
                "{}",
                "--output-format",
                "json",
            ],
        )
        assert create_result.exit_code == 0, create_result.output
        plan_id = json.loads(create_result.output)["plan"]["id"]

        update_result = cli_runner.invoke(
            cli,
            [
                "plan",
                "update",
                plan_id,
                "--description",
                "Updated at runtime",
                "--output-format",
                "json",
            ],
        )

        assert update_result.exit_code == 0, update_result.output
        payload = json.loads(update_result.output)
        assert payload["plan"]["id"] == plan_id
        assert payload["runtime_write"]["write_path"] == "direct_file"
        assert payload["runtime_write"]["target_kind"] == "workspace_sqlite"
        assert (
            payload["runtime_write"]["target_location"]
            == payload["runtime_write"]["workspace"]["database_path"]
        )

    def test_prefer_server_plan_update_still_reports_direct_file_when_local_only(
        self,
        cli_runner: CliRunner,
        temp_env: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(
            cli, ["project", "create", "Prefer Server Local Update Project"]
        )
        create_result = cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Prefer Server Local Update Plan",
                "--project",
                "Prefer Server Local Update Project",
                "--content",
                "{}",
                "--output-format",
                "json",
            ],
        )
        assert create_result.exit_code == 0, create_result.output
        plan_id = json.loads(create_result.output)["plan"]["id"]

        monkeypatch.setenv("PMS_WRITE_MODE", "prefer_server")
        monkeypatch.setenv("PMS_SERVER_BASE_URL", "http://127.0.0.1:8000")
        reload_settings()
        monkeypatch.setattr(
            "pms.cli.app._runtime_server_payload",
            lambda: RuntimeServerPayload(
                base_url="http://127.0.0.1:8000",
                reachable=True,
                status=200,
                database="sqlite:///tmp/pms.db",
                error=None,
                checked=True,
                api_key_present=True,
            ),
        )

        update_result = cli_runner.invoke(
            cli,
            [
                "plan",
                "update",
                plan_id,
                "--description",
                "Updated locally under prefer-server",
                "--output-format",
                "json",
            ],
        )

        assert update_result.exit_code == 0, update_result.output
        payload = json.loads(update_result.output)
        assert payload["runtime_write"]["write_mode"] == "prefer_server"
        assert payload["runtime_write"]["write_path"] == "direct_file"
        assert payload["runtime_write"]["target_kind"] == "workspace_sqlite"

    def test_goal_summary_surfaces_effective_rollup_when_execution_leads(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Goal Rollup Project"])
        goal_result = cli_runner.invoke(
            cli,
            [
                "goal",
                "create",
                "Goal Rollup Goal",
                "--project",
                "Goal Rollup Project",
                "--progress",
                "10",
                "--format",
                "json",
            ],
        )
        goal_id = json.loads(goal_result.output)["goal"]["id"]
        task_id = _extract_id(
            cli_runner.invoke(
                cli, ["task", "add", "Goal Rollup Project", "Execution Task"]
            ).output
        )
        cli_runner.invoke(cli, ["task", "start", task_id, "--by", "tester"])
        cli_runner.invoke(
            cli,
            [
                "task",
                "progress",
                task_id,
                "45",
                "Implementing",
                "--by",
                "tester",
            ],
        )

        json_result = cli_runner.invoke(
            cli, ["goal", "summary", goal_id, "--format", "json"]
        )
        assert json_result.exit_code == 0, json_result.output
        payload = json.loads(json_result.output)
        assert payload["goal"]["progress_percent"] == 10
        assert payload["effective_rollup"]["progress_percent"] == 45
        assert payload["effective_rollup"]["basis"] == "execution_projection"
        assert payload["effective_hierarchy"]["average_progress"] == 45
        assert payload["effective_hierarchy"]["basis"] == "execution_projection"

        text_result = cli_runner.invoke(cli, ["goal", "summary", goal_id])
        assert text_result.exit_code == 0, text_result.output
        _assert_plain_output_contains(
            text_result.output,
            "Effective Rollup: active | 45% (execution_projection)",
        )

    def test_goal_show_surfaces_lifecycle_rollups_and_links(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        project_result = cli_runner.invoke(
            cli, ["project", "create", "Goal Show Rollup Project"]
        )
        assert project_result.exit_code == 0, project_result.output
        project_id = _extract_id(project_result.output)

        goal_result = cli_runner.invoke(
            cli,
            [
                "goal",
                "create",
                "Goal Show Rollup Goal",
                "--project",
                "Goal Show Rollup Project",
                "--progress",
                "10",
                "--format",
                "json",
            ],
        )
        assert goal_result.exit_code == 0, goal_result.output
        goal_id = json.loads(goal_result.output)["goal"]["id"]

        task_result = cli_runner.invoke(
            cli,
            [
                "task",
                "add",
                "Goal Show Rollup Project",
                "Execution Task",
                "--format",
                "json",
            ],
        )
        assert task_result.exit_code == 0, task_result.output
        task_id = json.loads(task_result.output)["task"]["id"]
        cli_runner.invoke(cli, ["task", "start", task_id, "--by", "tester"])
        cli_runner.invoke(
            cli,
            [
                "task",
                "progress",
                task_id,
                "45",
                "Implementing",
                "--by",
                "tester",
            ],
        )

        result = cli_runner.invoke(cli, ["goal", "show", goal_id, "--format", "json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["progress_percent"] == 10
        assert payload["stats"]["objective_count"] == 0
        assert payload["effective_rollup"]["progress_percent"] == 45
        assert payload["effective_rollup"]["basis"] == "execution_projection"
        assert payload["effective_hierarchy"]["average_progress"] == 45
        assert payload["last_activity_at"] is not None
        assert payload["last_transition_at"] is not None
        assert payload["execution"]["focus_task"]["id"] == task_id
        assert payload["links"]["summary"] == _cli_step(f"goal summary {goal_id}")
        assert payload["links"]["plans"] == _cli_step(
            f"plan list --goal-id {goal_id} --format json"
        )
        assert payload["links"]["tasks"] == _cli_step(
            f"task list --project {project_id} --format json"
        )
        assert payload["next_steps"][0].startswith(_cli_step("task show "))

    def test_goal_create_and_update_reject_literal_null_project_ids(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        invalid_create = cli_runner.invoke(
            cli,
            ["goal", "create", "Bad Goal", "--project-id", "null"],
        )
        assert invalid_create.exit_code != 0
        assert (
            "project_id cannot be the literal placeholder 'null'"
            in invalid_create.output
        )

        cli_runner.invoke(cli, ["project", "create", "Valid Goal Project"])
        valid_goal_result = cli_runner.invoke(
            cli,
            [
                "goal",
                "create",
                "Valid Goal",
                "--project",
                "Valid Goal Project",
                "--format",
                "json",
            ],
        )
        goal_id = json.loads(valid_goal_result.output)["goal"]["id"]

        invalid_update = cli_runner.invoke(
            cli,
            ["goal", "update", goal_id, "--project-id", "null"],
        )
        assert invalid_update.exit_code != 0
        assert (
            "project_id cannot be the literal placeholder 'null'"
            in invalid_update.output
        )

    def test_goal_list_surfaces_effective_rollups_when_execution_leads(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Goal List Rollup Project"])
        goal_result = cli_runner.invoke(
            cli,
            [
                "goal",
                "create",
                "Goal List Rollup Goal",
                "--project",
                "Goal List Rollup Project",
                "--progress",
                "10",
                "--format",
                "json",
            ],
        )
        goal_id = json.loads(goal_result.output)["goal"]["id"]
        task_id = _extract_id(
            cli_runner.invoke(
                cli, ["task", "add", "Goal List Rollup Project", "Execution Task"]
            ).output
        )
        cli_runner.invoke(cli, ["task", "start", task_id, "--by", "tester"])
        cli_runner.invoke(
            cli,
            [
                "task",
                "progress",
                task_id,
                "45",
                "Implementing",
                "--by",
                "tester",
            ],
        )

        json_result = cli_runner.invoke(
            cli,
            [
                "goal",
                "list",
                "--project",
                "Goal List Rollup Project",
                "--format",
                "json",
            ],
        )
        assert json_result.exit_code == 0, json_result.output
        payload = json.loads(json_result.output)
        goal_payload = next(item for item in payload["items"] if item["id"] == goal_id)
        assert goal_payload["progress_percent"] == 10
        assert goal_payload["effective_rollup"]["progress_percent"] == 45
        assert goal_payload["effective_rollup"]["basis"] == "execution_projection"
        assert goal_payload["last_activity_at"] is not None
        assert goal_payload["last_transition_at"] is not None
        assert goal_payload["terminal_reason"] is None
        assert goal_payload["links"]["self"] == _cli_step(f"goal show {goal_id}")
        assert goal_payload["links"]["summary"] == _cli_step(f"goal summary {goal_id}")
        assert goal_payload["links"]["plans"] == _cli_step(
            f"plan list --goal-id {goal_id} --format json"
        )
        assert goal_payload["links"]["project"] == _cli_step(
            f"project show {goal_payload['project_id']} --format json"
        )
        assert goal_payload["links"]["tasks"] == _cli_step(
            f"task list --project {goal_payload['project_id']} --format json"
        )

        text_result = cli_runner.invoke(
            cli,
            ["goal", "list", "--project", "Goal List Rollup Project"],
        )
        assert text_result.exit_code == 0, text_result.output
        _assert_plain_output_contains(text_result.output, "45% (stored 10%)")

    def test_goal_list_surfaces_terminal_reason_and_links(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Goal List Terminal Project"])
        goal_result = cli_runner.invoke(
            cli,
            [
                "goal",
                "create",
                "Goal List Terminal Goal",
                "--project",
                "Goal List Terminal Project",
                "--format",
                "json",
            ],
        )
        goal_id = json.loads(goal_result.output)["goal"]["id"]
        task_id = _extract_id(
            cli_runner.invoke(
                cli, ["task", "add", "Goal List Terminal Project", "Done Task"]
            ).output
        )
        cli_runner.invoke(cli, ["task", "complete", task_id, "--by", "tester"])

        json_result = cli_runner.invoke(
            cli,
            [
                "goal",
                "list",
                "--project",
                "Goal List Terminal Project",
                "--format",
                "json",
            ],
        )
        assert json_result.exit_code == 0, json_result.output
        payload = json.loads(json_result.output)
        goal_payload = next(item for item in payload["items"] if item["id"] == goal_id)
        assert (
            goal_payload["terminal_reason"]
            == "all execution tasks are already complete"
        )
        assert goal_payload["last_activity_at"] is not None
        assert goal_payload["last_transition_at"] is not None
        assert goal_payload["links"]["summary"] == _cli_step(f"goal summary {goal_id}")
        assert goal_payload["links"]["plans"] == _cli_step(
            f"plan list --goal-id {goal_id} --format json"
        )

    def test_keyresult_list_surfaces_lifecycle_rollups_and_discoverability(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(
            cli, ["project", "create", "Key Result List Lifecycle Project"]
        )
        goal_result = cli_runner.invoke(
            cli,
            [
                "goal",
                "create",
                "Key Result List Lifecycle Goal",
                "--project",
                "Key Result List Lifecycle Project",
                "--format",
                "json",
            ],
        )
        assert goal_result.exit_code == 0, goal_result.output
        goal_id = json.loads(goal_result.output)["goal"]["id"]
        objective_result = cli_runner.invoke(
            cli,
            [
                "objective",
                "create",
                "Key Result List Lifecycle Objective",
                "--goal-id",
                goal_id,
                "--format",
                "json",
            ],
        )
        assert objective_result.exit_code == 0, objective_result.output
        objective_id = json.loads(objective_result.output)["objective"]["id"]
        key_result_result = cli_runner.invoke(
            cli,
            [
                "keyresult",
                "create",
                "Key Result List Lifecycle Item",
                "--objective-id",
                objective_id,
                "--progress",
                "35",
            ],
        )
        assert key_result_result.exit_code == 0, key_result_result.output
        key_result_id = _extract_id(key_result_result.output)
        cli_runner.invoke(
            cli,
            [
                "keyresult",
                "update",
                key_result_id,
                "--status",
                "on_hold",
                "--progress",
                "35",
            ],
        )
        cli_runner.invoke(
            cli,
            [
                "keyresult",
                "update",
                key_result_id,
                "--status",
                "active",
                "--progress",
                "35",
            ],
        )

        result = cli_runner.invoke(
            cli,
            [
                "keyresult",
                "list",
                "--objective-id",
                objective_id,
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        item = next(entry for entry in payload["items"] if entry["id"] == key_result_id)
        assert item["goal_id"] == goal_id
        assert item["project_id"] is not None
        assert item["progress_percent"] == 35
        assert item["effective_rollup"]["progress_percent"] == 35
        assert item["effective_rollup"]["status"] == "active"
        assert item["effective_rollup"]["basis"] == "stored_key_result"
        assert item["last_activity_at"] is not None
        assert item["last_transition_at"] is not None
        assert item["terminal_reason"] is None
        assert item["links"]["self"] == _cli_step(f"keyresult show {key_result_id}")
        assert item["links"]["objective"] == _cli_step(f"objective show {objective_id}")
        assert item["links"]["key_results"] == _cli_step(
            f"keyresult list --objective-id {objective_id} --format json"
        )
        assert item["links"]["goal"] == _cli_step(f"goal show {goal_id}")
        assert item["links"]["goal_summary"] == _cli_step(f"goal summary {goal_id}")
        assert item["links"]["project"] == _cli_step(
            f"project show {item['project_id']} --format json"
        )
        assert item["next_steps"][0] == _cli_step(f"keyresult show {key_result_id}")

    def test_keyresult_show_surfaces_terminal_reason_and_completion_context(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(
            cli, ["project", "create", "Key Result Show Lifecycle Project"]
        )
        goal_result = cli_runner.invoke(
            cli,
            [
                "goal",
                "create",
                "Key Result Show Lifecycle Goal",
                "--project",
                "Key Result Show Lifecycle Project",
                "--format",
                "json",
            ],
        )
        assert goal_result.exit_code == 0, goal_result.output
        goal_id = json.loads(goal_result.output)["goal"]["id"]
        objective_result = cli_runner.invoke(
            cli,
            [
                "objective",
                "create",
                "Key Result Show Lifecycle Objective",
                "--goal-id",
                goal_id,
                "--format",
                "json",
            ],
        )
        assert objective_result.exit_code == 0, objective_result.output
        objective_id = json.loads(objective_result.output)["objective"]["id"]
        key_result_result = cli_runner.invoke(
            cli,
            [
                "keyresult",
                "create",
                "Key Result Show Lifecycle Item",
                "--objective-id",
                objective_id,
                "--progress",
                "100",
            ],
        )
        assert key_result_result.exit_code == 0, key_result_result.output
        key_result_id = _extract_id(key_result_result.output)
        cli_runner.invoke(cli, ["keyresult", "complete", key_result_id])

        result = cli_runner.invoke(
            cli, ["keyresult", "show", key_result_id, "--format", "json"]
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["goal_id"] == goal_id
        assert payload["project_id"] is not None
        assert payload["effective_rollup"]["progress_percent"] == 100
        assert payload["effective_rollup"]["status"] == "completed"
        assert payload["effective_rollup"]["basis"] == "stored_key_result"
        assert payload["last_activity_at"] is not None
        assert payload["last_transition_at"] is not None
        assert payload["terminal_reason"] == "key result is already marked completed"
        assert payload["completion_context"] is not None
        assert payload["links"]["self"] == _cli_step(f"keyresult show {key_result_id}")
        assert payload["links"]["objective"] == _cli_step(
            f"objective show {objective_id}"
        )
        assert payload["links"]["key_results"] == _cli_step(
            f"keyresult list --objective-id {objective_id} --format json"
        )
        assert payload["links"]["goal"] == _cli_step(f"goal show {goal_id}")
        assert payload["links"]["goal_summary"] == _cli_step(f"goal summary {goal_id}")
        assert payload["links"]["project"] == _cli_step(
            f"project show {payload['project_id']} --format json"
        )
        assert payload["next_steps"][0] == _cli_step(f"keyresult show {key_result_id}")
        assert (
            _cli_step(
                f"keyresult list --objective-id {objective_id} --status completed --format json"
            )
            in payload["completion_context"]["next_steps"]
        )

    def test_plan_list_json_surfaces_focus_task(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Plan list JSON should surface the active incomplete linked task."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Focus Plan Project"])
        todo_result = cli_runner.invoke(
            cli, ["task", "add", "Focus Plan Project", "Todo Task"]
        )
        active_result = cli_runner.invoke(
            cli, ["task", "add", "Focus Plan Project", "Active Task"]
        )
        active_task_id = _extract_id(active_result.output)
        cli_runner.invoke(cli, ["task", "start", active_task_id, "--by", "tester"])
        create_result = cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Focus Plan",
                "--project",
                "Focus Plan Project",
                "--status",
                "active",
                "--task-id",
                _extract_id(todo_result.output),
                "--task-id",
                active_task_id,
                "--content",
                "{}",
                "--format",
                "json",
            ],
        )
        assert create_result.exit_code == 0, create_result.output

        result = cli_runner.invoke(cli, ["plan", "list", "--format", "json"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["focus_task"]["title"] == "Active Task"
        assert payload["focus_task"]["status"] == "in_progress"
        assert payload["next_steps"][0].startswith(_cli_step("task progress "))

    def test_plan_show_json_surfaces_focus_task(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        """Plan show JSON should surface the review-ready linked task."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Plan Show Project"])
        todo_result = cli_runner.invoke(
            cli, ["task", "add", "Plan Show Project", "Todo Task"]
        )
        review_result = cli_runner.invoke(
            cli, ["task", "add", "Plan Show Project", "Review Task"]
        )
        review_task_id = _extract_id(review_result.output)
        cli_runner.invoke(cli, ["task", "start", review_task_id, "--by", "tester"])
        cli_runner.invoke(cli, ["task", "review", review_task_id, "--by", "tester"])
        create_result = cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Plan Show Focus",
                "--project",
                "Plan Show Project",
                "--status",
                "active",
                "--task-id",
                _extract_id(todo_result.output),
                "--task-id",
                review_task_id,
                "--content",
                "{}",
                "--format",
                "json",
            ],
        )
        plan_id = _extract_id(create_result.output)

        result = cli_runner.invoke(cli, ["plan", "show", plan_id, "--format", "json"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["focus_task"]["title"] == "Review Task"
        assert payload["focus_task"]["status"] == "in_review"
        assert payload["next_steps"][0].startswith(_cli_step("task complete "))

    def test_plan_list_json_reports_terminal_reason_when_all_linked_tasks_are_done(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Terminal Plan List Project"])
        task_result = cli_runner.invoke(
            cli, ["task", "add", "Terminal Plan List Project", "Done Task"]
        )
        task_id = _extract_id(task_result.output)
        cli_runner.invoke(cli, ["task", "complete", task_id, "--by", "tester"])
        create_result = cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Terminal Plan List",
                "--project",
                "Terminal Plan List Project",
                "--status",
                "active",
                "--task-id",
                task_id,
                "--content",
                "{}",
                "--format",
                "json",
            ],
        )
        plan_id = _extract_id(create_result.output)

        result = cli_runner.invoke(cli, ["plan", "list", "--format", "json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["focus_task"] is None
        assert payload["terminal_reason"] == "all surfaced tasks are already complete"
        plan_item = next(item for item in payload["items"] if item["id"] == plan_id)
        assert plan_item["status"] == "completed"
        assert plan_item["stored_status"] == "active"

    def test_plan_show_json_reports_terminal_reason_when_all_linked_tasks_are_done(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Terminal Plan Show Project"])
        task_result = cli_runner.invoke(
            cli, ["task", "add", "Terminal Plan Show Project", "Done Task"]
        )
        task_id = _extract_id(task_result.output)
        cli_runner.invoke(cli, ["task", "complete", task_id, "--by", "tester"])
        create_result = cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Terminal Plan Show",
                "--project",
                "Terminal Plan Show Project",
                "--status",
                "active",
                "--task-id",
                task_id,
                "--content",
                "{}",
                "--format",
                "json",
            ],
        )
        plan_id = _extract_id(create_result.output)

        result = cli_runner.invoke(cli, ["plan", "show", plan_id, "--format", "json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["focus_task"] is None
        assert payload["status"] == "completed"
        assert payload["stored_status"] == "active"
        assert payload["terminal_reason"] == "all linked tasks are already terminal"

    def test_archived_plan_show_and_lineage_report_terminal_reason(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Archived Plan Project"])
        create_result = cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Archived Plan",
                "--project",
                "Archived Plan Project",
                "--status",
                "active",
                "--content",
                "{}",
                "--format",
                "json",
            ],
        )
        plan_id = _extract_id(create_result.output)
        archive_result = cli_runner.invoke(
            cli,
            [
                "plan",
                "update",
                plan_id,
                "--status",
                "archived",
                "--output-format",
                "json",
            ],
        )
        assert archive_result.exit_code == 0, archive_result.output

        show_result = cli_runner.invoke(
            cli, ["plan", "show", plan_id, "--format", "json"]
        )

        assert show_result.exit_code == 0, show_result.output
        show_payload = json.loads(show_result.output)
        assert show_payload["status"] == "archived"
        assert show_payload["stored_status"] == "archived"
        assert show_payload["terminal_reason"] == "plan is already archived"

        lineage_result = cli_runner.invoke(
            cli, ["plan", "lineage", "--plan-id", plan_id, "--format", "json"]
        )

        assert lineage_result.exit_code == 0, lineage_result.output
        list_result = cli_runner.invoke(
            cli, ["plan", "list", "--status", "archived", "--format", "json"]
        )
        assert list_result.exit_code == 0, list_result.output
        list_payload = json.loads(list_result.output)
        list_item = next(
            item for item in list_payload["items"] if item["id"] == plan_id
        )
        lineage_payload = json.loads(lineage_result.output)
        assert lineage_payload["terminal_reason"] == "plan is already archived"
        lineage_item = next(
            item for item in lineage_payload["items"] if item["plan"]["id"] == plan_id
        )
        assert list_item["status"] == "archived"
        assert list_item["stored_status"] == "archived"
        assert list_item["terminal_reason"] == "plan is already archived"
        assert list_item["last_transition_at"] is not None
        assert show_payload["last_transition_at"] == list_item["last_transition_at"]
        assert lineage_item["plan"]["status"] == "archived"
        assert lineage_item["plan"]["stored_status"] == "archived"
        assert lineage_item["plan"]["terminal_reason"] == "plan is already archived"
        assert (
            lineage_item["plan"]["last_transition_at"]
            == list_item["last_transition_at"]
        )

    def test_plan_list_keeps_completed_plan_terminal_when_completed_task_gets_new_activity(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Fresh Active Plan Project"])
        active_task_result = cli_runner.invoke(
            cli, ["task", "add", "Fresh Active Plan Project", "Active Task"]
        )
        active_task_id = _extract_id(active_task_result.output)
        active_plan_result = cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Still Active Plan",
                "--project",
                "Fresh Active Plan Project",
                "--status",
                "active",
                "--task-id",
                active_task_id,
                "--content",
                "{}",
                "--format",
                "json",
            ],
        )
        assert active_plan_result.exit_code == 0, active_plan_result.output

        cli_runner.invoke(cli, ["project", "create", "Fresh Completed Plan Project"])
        done_task_result = cli_runner.invoke(
            cli, ["task", "add", "Fresh Completed Plan Project", "Done Task"]
        )
        done_task_id = _extract_id(done_task_result.output)
        cli_runner.invoke(cli, ["task", "start", done_task_id, "--by", "tester"])
        cli_runner.invoke(cli, ["task", "complete", done_task_id, "--by", "tester"])
        completed_plan_result = cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Fresh Completed Plan",
                "--project",
                "Fresh Completed Plan Project",
                "--status",
                "completed",
                "--task-id",
                done_task_id,
                "--content",
                "{}",
                "--format",
                "json",
            ],
        )
        completed_plan_id = _extract_id(completed_plan_result.output)
        cli_runner.invoke(cli, ["project", "complete", "Fresh Completed Plan Project"])
        comment_result = cli_runner.invoke(
            cli,
            [
                "comment",
                "add",
                "task",
                done_task_id,
                "Fresh terminal plan activity",
                "--by",
                "tester",
            ],
        )
        assert comment_result.exit_code == 0, comment_result.output

        result = cli_runner.invoke(cli, ["plan", "list", "--format", "json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["freshest_visible_activity"]["kind"] == "plan"
        assert payload["freshest_visible_activity"]["plan_id"] == completed_plan_id
        assert completed_plan_id not in {
            item["id"] for item in payload["items_by_status"]["active"]
        }
        completed_item = next(
            item
            for item in payload["recently_completed_plans"]
            if item["id"] == completed_plan_id
        )
        assert completed_item["status"] == "completed"
        assert completed_item["terminal_reason"] == "plan is already marked completed"

    def test_plan_list_derives_effective_status_from_terminal_graph(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Derived Status Project"])
        task_id = _extract_id(
            cli_runner.invoke(
                cli,
                ["task", "add", "Derived Status Project", "Already Done Task"],
            ).output
        )
        cli_runner.invoke(cli, ["task", "complete", task_id, "--by", "tester"])
        plan_id = _extract_id(
            cli_runner.invoke(
                cli,
                [
                    "plan",
                    "create",
                    "Derived Status Plan",
                    "--project",
                    "Derived Status Project",
                    "--status",
                    "active",
                    "--task-id",
                    task_id,
                    "--content",
                    "{}",
                    "--format",
                    "json",
                ],
            ).output
        )

        result = cli_runner.invoke(cli, ["plan", "list", "--format", "json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        item = next(item for item in payload["items"] if item["id"] == plan_id)
        assert item["status"] == "completed"
        assert item["stored_status"] == "active"

        text_result = cli_runner.invoke(cli, ["plan", "list"])
        assert text_result.exit_code == 0, text_result.output
        _assert_plain_output_contains(
            text_result.output, "completed*", "derived graph lifecycle"
        )

    def test_plan_list_surfaces_recent_projects_without_plans(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Planless Project"])
        task_id = _extract_id(
            cli_runner.invoke(
                cli,
                ["task", "add", "Planless Project", "Planless Work"],
            ).output
        )
        progress_result = cli_runner.invoke(
            cli,
            [
                "task",
                "progress",
                task_id,
                "40",
                "Fresh planless activity",
                "--by",
                "tester",
                "--format",
                "json",
            ],
        )
        assert progress_result.exit_code == 0, progress_result.output

        result = cli_runner.invoke(cli, ["plan", "list", "--format", "json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        project = next(
            item
            for item in payload["projects_without_plans"]
            if item["name"] == "Planless Project"
        )
        project_list_result = cli_runner.invoke(
            cli, ["project", "list", "--format", "json"]
        )
        assert project_list_result.exit_code == 0, project_list_result.output
        project_list_payload = json.loads(project_list_result.output)
        project_list_item = next(
            item
            for item in project_list_payload["items"]
            if item["project_id"] == project["project_id"]
        )
        dashboard_result = cli_runner.invoke(cli, ["dashboard", "--format", "json"])
        assert dashboard_result.exit_code == 0, dashboard_result.output
        dashboard_payload = json.loads(dashboard_result.output)
        dashboard_item = next(
            item
            for item in dashboard_payload["active_projects"]
            if item["project_id"] == project["project_id"]
        )
        assert project["project_id"] == project["id"]
        assert project["project_name"] == project["name"] == "Planless Project"
        assert project["last_activity_at"] is not None
        assert project["last_transition_at"] is not None
        assert project["status"] == "active"
        assert project_list_item["status"] == "active"
        assert project_list_item["last_activity_at"] == project["last_activity_at"]
        assert project_list_item["last_transition_at"] == project["last_transition_at"]
        assert dashboard_item["status"] == "active"
        assert dashboard_item["last_activity_at"] == project["last_activity_at"]
        assert dashboard_item["last_transition_at"] == project["last_transition_at"]
        assert project["links"]["self"] == _cli_step(
            f"project show {project['id']} --format json"
        )
        assert payload["freshest_visible_activity"]["kind"] == "project_without_plan"
        assert payload["freshest_visible_activity"]["project_id"] == project["id"]
        assert (
            payload["freshest_visible_activity"]["project_name"] == "Planless Project"
        )
        assert payload["freshest_visible_transition"]["kind"] == "project_without_plan"
        assert payload["freshest_visible_transition"]["project_id"] == project["id"]

        text_result = cli_runner.invoke(cli, ["plan", "list"])
        assert text_result.exit_code == 0, text_result.output
        _assert_semantic_output_contains(
            text_result.output,
            "Projects Without Plans",
            "Planless Project",
            "Freshest Visible Activity: Planless Project (project without plan)",
            "Freshest Visible Transition: Planless Project (project without plan)",
        )

    def test_plan_list_reports_planless_project_visibility_summary_and_categories(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        for idx in range(5):
            project_name = f"Visible Planless {idx}"
            cli_runner.invoke(cli, ["project", "create", project_name])
            task_id = _extract_id(
                cli_runner.invoke(
                    cli,
                    ["task", "add", project_name, f"Visible Task {idx}"],
                ).output
            )
            cli_runner.invoke(
                cli,
                ["task", "start", task_id, "--by", "tester", "--format", "json"],
            )
            cli_runner.invoke(
                cli,
                [
                    "task",
                    "progress",
                    task_id,
                    str(10 + idx),
                    f"Visible planless activity {idx}",
                    "--by",
                    "tester",
                    "--format",
                    "json",
                ],
            )

        cli_runner.invoke(cli, ["project", "create", "Historical Planless"])
        historical_task_id = _extract_id(
            cli_runner.invoke(
                cli,
                ["task", "add", "Historical Planless", "Historical Done Task"],
            ).output
        )
        cli_runner.invoke(
            cli,
            [
                "task",
                "complete",
                historical_task_id,
                "--by",
                "tester",
                "--format",
                "json",
            ],
        )
        cli_runner.invoke(cli, ["project", "complete", "Historical Planless"])

        extra_project_id = cli_runner.invoke(
            cli,
            ["project", "create", "Overflow Planless", "--format", "json"],
        )
        assert extra_project_id.exit_code == 0, extra_project_id.output

        result = cli_runner.invoke(
            cli, ["plan", "list", "--format", "json", "--limit", "1"]
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        summary = payload["projects_without_plans_summary"]
        assert summary["displayed_count"] == len(payload["projects_without_plans"]) == 5
        assert summary["total_count"] == 7
        assert summary["is_truncated"] is True
        assert summary["total_category_counts"]["active_work"] == 6
        assert summary["total_category_counts"]["project_history"] == 1
        assert "active_work" in payload["projects_without_plans_by_category"]
        assert "project_history" in payload["projects_without_plans_by_category"]
        assert summary["displayed_category_counts"]["project_history"] == 1
        assert (
            payload["projects_without_plans_by_category"]["project_history"][0]["name"]
            == "Historical Planless"
        )

        text_result = cli_runner.invoke(cli, ["plan", "list", "--limit", "1"])
        assert text_result.exit_code == 0, text_result.output
        _assert_plain_output_contains(
            text_result.output,
            "Projects Without Plans",
            "Active Work",
            "Project History",
        )

    def test_plan_list_planless_generated_projects_respect_include_generated(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Visible Planless Project"])
        visible_task_id = _extract_id(
            cli_runner.invoke(
                cli,
                ["task", "add", "Visible Planless Project", "Visible Planless Task"],
            ).output
        )
        cli_runner.invoke(
            cli,
            ["task", "start", visible_task_id, "--by", "tester", "--format", "json"],
        )
        cli_runner.invoke(
            cli,
            [
                "task",
                "progress",
                visible_task_id,
                "35",
                "Visible planless activity",
                "--by",
                "tester",
                "--format",
                "json",
            ],
        )

        cli_runner.invoke(cli, ["project", "create", "Audit Project planless123"])
        generated_task_id = _extract_id(
            cli_runner.invoke(
                cli,
                ["task", "add", "Audit Project planless123", "Generated Planless Task"],
            ).output
        )
        cli_runner.invoke(
            cli,
            ["task", "start", generated_task_id, "--by", "tester", "--format", "json"],
        )
        cli_runner.invoke(
            cli,
            [
                "task",
                "progress",
                generated_task_id,
                "90",
                "Generated planless activity",
                "--by",
                "tester",
                "--format",
                "json",
            ],
        )

        result = cli_runner.invoke(cli, ["plan", "list", "--format", "json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert [item["name"] for item in payload["projects_without_plans"]] == [
            "Visible Planless Project"
        ]
        assert payload["projects_without_plans_summary"]["total_count"] == 1
        assert (
            payload["projects_without_plans_summary"]["suppressed_generated_count"] == 1
        )
        assert (
            payload["freshest_visible_activity"]["project_name"]
            == "Visible Planless Project"
        )
        assert (
            payload["freshest_visible_transition"]["project_name"]
            == "Visible Planless Project"
        )

        text_result = cli_runner.invoke(cli, ["plan", "list"])
        assert text_result.exit_code == 0, text_result.output
        _assert_plain_output_contains(
            text_result.output, "Suppressed generated planless projects: 1"
        )

        include_generated = cli_runner.invoke(
            cli, ["plan", "list", "--format", "json", "--include-generated"]
        )

        assert include_generated.exit_code == 0, include_generated.output
        include_payload = json.loads(include_generated.output)
        assert [item["name"] for item in include_payload["projects_without_plans"]] == [
            "Audit Project planless123",
            "Visible Planless Project",
        ]
        assert include_payload["projects_without_plans_summary"]["total_count"] == 2
        assert (
            include_payload["projects_without_plans_summary"][
                "suppressed_generated_count"
            ]
            == 0
        )
        assert (
            include_payload["freshest_visible_activity"]["project_name"]
            == "Audit Project planless123"
        )
        assert (
            include_payload["freshest_visible_transition"]["project_name"]
            == "Audit Project planless123"
        )

    def test_plan_list_hides_audit_generated_plans_by_default(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Operator Project"])
        cli_runner.invoke(cli, ["project", "create", "Audit Project abc123"])
        cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Operator Plan",
                "--project",
                "Operator Project",
                "--status",
                "active",
                "--content",
                "{}",
                "--format",
                "json",
            ],
        )
        cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Audit Plan abc123",
                "--project",
                "Audit Project abc123",
                "--status",
                "active",
                "--tag",
                "audit-generated",
                "--content",
                "{}",
                "--format",
                "json",
            ],
        )

        result = cli_runner.invoke(cli, ["plan", "list", "--format", "json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert [item["name"] for item in payload["items"]] == ["Operator Plan"]
        assert payload["suppressed_generated_count"] == 1
        assert payload["freshest_visible_activity"]["plan_name"] == "Operator Plan"
        assert payload["freshest_visible_transition"]["plan_name"] == "Operator Plan"

    def test_plan_list_fails_nonzero_for_conflicting_scope_filters(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Operator Project"])

        result = cli_runner.invoke(
            cli,
            [
                "plan",
                "list",
                "--format",
                "json",
                "--project",
                "Operator Project",
                "--project-id",
                "proj_conflict",
            ],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert payload["error"] == "Use --project or --project-id, not both"

    def test_plan_list_can_include_audit_generated_plans_when_requested(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Operator Project"])
        cli_runner.invoke(cli, ["project", "create", "Audit Project xyz789"])
        cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Operator Plan",
                "--project",
                "Operator Project",
                "--status",
                "active",
                "--content",
                "{}",
                "--format",
                "json",
            ],
        )
        cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Audit Plan xyz789",
                "--project",
                "Audit Project xyz789",
                "--status",
                "active",
                "--tag",
                "audit-generated",
                "--content",
                "{}",
                "--format",
                "json",
            ],
        )

        result = cli_runner.invoke(
            cli, ["plan", "list", "--format", "json", "--include-generated"]
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert {item["name"] for item in payload["items"]} == {
            "Operator Plan",
            "Audit Plan xyz789",
        }
        assert payload["suppressed_generated_count"] == 0

    def test_plan_list_generated_suppression_applies_before_pagination(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        for idx in range(3):
            cli_runner.invoke(cli, ["project", "create", f"Audit Project {idx} xyz789"])
            cli_runner.invoke(
                cli,
                [
                    "plan",
                    "create",
                    f"Audit Plan {idx}",
                    "--project",
                    f"Audit Project {idx} xyz789",
                    "--status",
                    "active",
                    "--tag",
                    "audit-generated",
                    "--content",
                    "{}",
                    "--format",
                    "json",
                ],
            )
        cli_runner.invoke(cli, ["project", "create", "Operator Project"])
        cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Operator Plan",
                "--project",
                "Operator Project",
                "--status",
                "active",
                "--content",
                "{}",
                "--format",
                "json",
            ],
        )

        result = cli_runner.invoke(
            cli,
            ["plan", "list", "--format", "json", "--limit", "1"],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["page"]["total_count"] == 1
        assert [item["name"] for item in payload["items"]] == ["Operator Plan"]

    def test_plan_list_page_total_count_reports_full_visible_population(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Page Count Project A"])
        cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Page Count Plan A",
                "--project",
                "Page Count Project A",
                "--status",
                "active",
                "--content",
                "{}",
                "--format",
                "json",
            ],
        )
        cli_runner.invoke(cli, ["project", "create", "Page Count Project B"])
        cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Page Count Plan B",
                "--project",
                "Page Count Project B",
                "--status",
                "active",
                "--content",
                "{}",
                "--format",
                "json",
            ],
        )

        result = cli_runner.invoke(
            cli,
            ["plan", "list", "--format", "json", "--limit", "1"],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert len(payload["items"]) == 1
        assert payload["page"]["total_count"] == 2
        assert payload["page"]["has_more"] is True
        assert payload["page"]["next_offset"] == 1

    def test_goal_list_global_uses_visible_operator_population_by_default(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Operator Project"])
        cli_runner.invoke(cli, ["project", "create", "Audit Project audit123"])
        cli_runner.invoke(cli, ["project", "create", "Goal Filter Project A"])
        cli_runner.invoke(
            cli, ["goal", "create", "Operator Goal", "--project", "Operator Project"]
        )
        cli_runner.invoke(
            cli, ["goal", "create", "Audit Goal", "--project", "Audit Project audit123"]
        )
        cli_runner.invoke(
            cli,
            ["goal", "create", "History Goal", "--project", "Goal Filter Project A"],
        )

        result = cli_runner.invoke(cli, ["goal", "list", "--format", "json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["scope"]["population"] == "visible_operator"
        assert payload["visible_totals"]["population"] == "visible_operator"
        assert payload["population_totals"]["population"] == "visible_operator"
        assert [item["name"] for item in payload["items"]] == ["Operator Goal"]
        assert payload["items"][0]["project_operator_category"] == "active_work"
        assert payload["suppressed_generated_count"] == 1
        assert payload["suppressed_hidden_count"] == 1

    def test_goal_list_can_include_generated_and_history_when_requested(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Operator Project"])
        cli_runner.invoke(cli, ["project", "create", "Audit Project audit123"])
        cli_runner.invoke(cli, ["project", "create", "Goal Filter Project A"])
        cli_runner.invoke(
            cli, ["goal", "create", "Operator Goal", "--project", "Operator Project"]
        )
        cli_runner.invoke(
            cli, ["goal", "create", "Audit Goal", "--project", "Audit Project audit123"]
        )
        cli_runner.invoke(
            cli,
            ["goal", "create", "History Goal", "--project", "Goal Filter Project A"],
        )

        result = cli_runner.invoke(
            cli, ["goal", "list", "--format", "json", "--include-generated"]
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["scope"]["population"] == "all_retained"
        assert payload["visible_totals"]["population"] == "visible_operator"
        assert payload["population_totals"]["population"] == "all_retained"
        assert {item["name"] for item in payload["items"]} == {
            "Operator Goal",
            "Audit Goal",
            "History Goal",
        }
        by_name = {item["name"]: item for item in payload["items"]}
        assert by_name["Audit Goal"]["project_operator_category"] == "audit_artifact"
        assert by_name["History Goal"]["project_operator_category"] == "project_history"
        assert payload["suppressed_generated_count"] == 1
        assert payload["suppressed_hidden_count"] == 1

    def test_goal_list_no_visible_goals_guides_to_retained_view(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Audit Project audit123"])
        cli_runner.invoke(
            cli, ["goal", "create", "Audit Goal", "--project", "Audit Project audit123"]
        )

        result = cli_runner.invoke(cli, ["goal", "list", "--format", "json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["items"] == []
        assert payload["suppressed_generated_count"] == 1
        assert (
            _cli_step("goal list --include-generated --format json")
            in payload["next_steps"]
        )

    def test_plan_lineage_json_reports_terminal_reason_when_all_tasks_are_done(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Terminal Lineage Project"])
        task_result = cli_runner.invoke(
            cli, ["task", "add", "Terminal Lineage Project", "Done Task"]
        )
        task_id = _extract_id(task_result.output)
        cli_runner.invoke(cli, ["task", "complete", task_id, "--by", "tester"])
        create_result = cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Terminal Lineage",
                "--project",
                "Terminal Lineage Project",
                "--status",
                "active",
                "--task-id",
                task_id,
                "--content",
                "{}",
                "--format",
                "json",
            ],
        )
        plan_id = _extract_id(create_result.output)

        result = cli_runner.invoke(
            cli, ["plan", "lineage", "--plan-id", plan_id, "--format", "json"]
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["focus_task"] is None
        assert payload["terminal_reason"] == "all surfaced tasks are already complete"
        lineage_item = next(
            item for item in payload["items"] if item["plan"]["id"] == plan_id
        )
        assert lineage_item["plan"]["status"] == "completed"
        assert lineage_item["plan"]["stored_status"] == "active"
        assert (
            lineage_item["plan"]["terminal_reason"]
            == "all linked tasks are already terminal"
        )

    def test_plan_lineage_status_filter_uses_effective_status(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(
            cli, ["project", "create", "Lineage Effective Filter Project"]
        )
        task_result = cli_runner.invoke(
            cli, ["task", "add", "Lineage Effective Filter Project", "Done Task"]
        )
        task_id = _extract_id(task_result.output)
        cli_runner.invoke(cli, ["task", "complete", task_id, "--by", "tester"])
        create_result = cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Lineage Effective Filter Plan",
                "--project",
                "Lineage Effective Filter Project",
                "--status",
                "active",
                "--task-id",
                task_id,
                "--content",
                "{}",
                "--format",
                "json",
            ],
        )
        plan_id = _extract_id(create_result.output)

        result = cli_runner.invoke(
            cli,
            [
                "plan",
                "lineage",
                "--status",
                "completed",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        lineage_item = next(
            item for item in payload["items"] if item["plan"]["id"] == plan_id
        )
        assert lineage_item["plan"]["status"] == "completed"
        assert lineage_item["plan"]["stored_status"] == "active"

    def test_plan_lineage_json_uses_full_plan_tasks_for_focus_beyond_task_limit(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Lineage Focus Project"])
        done_result = cli_runner.invoke(
            cli, ["task", "add", "Lineage Focus Project", "Done Task"]
        )
        active_result = cli_runner.invoke(
            cli, ["task", "add", "Lineage Focus Project", "Active Task"]
        )
        done_task_id = _extract_id(done_result.output)
        active_task_id = _extract_id(active_result.output)
        cli_runner.invoke(cli, ["task", "complete", done_task_id, "--by", "tester"])
        cli_runner.invoke(cli, ["task", "start", active_task_id, "--by", "tester"])
        create_result = cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Lineage Focus Plan",
                "--project",
                "Lineage Focus Project",
                "--status",
                "active",
                "--task-id",
                done_task_id,
                "--task-id",
                active_task_id,
                "--content",
                "{}",
                "--format",
                "json",
            ],
        )
        plan_id = _extract_id(create_result.output)

        result = cli_runner.invoke(
            cli,
            [
                "plan",
                "lineage",
                "--plan-id",
                plan_id,
                "--task-limit",
                "1",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["focus_task"]["title"] == "Active Task"
        assert payload["focus_task"]["status"] == "in_progress"
        assert payload["terminal_reason"] is None


class TestHelpCommands:
    """Tests for help output."""

    def test_main_help(self, cli_runner: CliRunner):
        """Test main help output."""
        result = cli_runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        _assert_plain_output_contains(
            result.output,
            "PMS - Project Management System",
            "project",
            "product",
            "task",
            "workflow",
            "init",
        )

    def test_project_help(self, cli_runner: CliRunner):
        """Test project group help."""
        result = cli_runner.invoke(cli, ["project", "--help"])

        assert result.exit_code == 0
        _assert_plain_output_contains(
            result.output, "Manage projects", "create", "list"
        )

    def test_task_help(self, cli_runner: CliRunner):
        """Test task group help."""
        result = cli_runner.invoke(cli, ["task", "--help"])

        assert result.exit_code == 0
        _assert_plain_output_contains(result.output, "Manage tasks", "add", "list")

    def test_remote_help(self, cli_runner: CliRunner):
        """Test remote group help."""
        result = cli_runner.invoke(cli, ["remote", "--help"])

        assert result.exit_code == 0
        _assert_plain_output_contains(
            result.output, "Manage remote hosts", "add", "list", "exec", "sync"
        )


class TestRemoteCommands:
    """Tests for remote host commands."""

    def test_remote_add(self, cli_runner: CliRunner, temp_env: Path):
        """Test adding a remote host."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(
            cli,
            [
                "remote",
                "add",
                "testserver",
                "192.168.1.100",
                "admin",
                "-p",
                "2222",
                "-r",
                "/var/www",
            ],
        )

        assert result.exit_code == 0
        _assert_plain_output_contains(result.output, "Added remote host", "testserver")

    def test_remote_add_with_tags(self, cli_runner: CliRunner, temp_env: Path):
        """Test adding a remote host with tags."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(
            cli,
            [
                "remote",
                "add",
                "prodserver",
                "example.com",
                "deploy",
                "-t",
                "production",
                "-t",
                "web",
            ],
        )

        assert result.exit_code == 0
        _assert_plain_output_contains(result.output, "Added remote host")

    def test_remote_list_empty(self, cli_runner: CliRunner, temp_env: Path):
        """Test listing remote hosts when none exist."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(cli, ["remote", "list"])

        assert result.exit_code == 0
        _assert_plain_output_contains(result.output, "Total: 0")

    def test_remote_list_with_hosts(self, cli_runner: CliRunner, temp_env: Path):
        """Test listing remote hosts."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(
            cli, ["remote", "add", "server1", "host1.example.com", "user1"]
        )
        cli_runner.invoke(
            cli, ["remote", "add", "server2", "host2.example.com", "user2"]
        )

        result = cli_runner.invoke(cli, ["remote", "list"])

        assert result.exit_code == 0
        _assert_plain_output_contains(result.output, "server1", "server2", "Total: 2")

    def test_remote_list_json(self, cli_runner: CliRunner, temp_env: Path):
        """Test listing remote hosts in JSON format."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(
            cli, ["remote", "add", "jsonserver", "json.example.com", "admin"]
        )

        result = cli_runner.invoke(cli, ["remote", "list", "-f", "json"])

        assert result.exit_code == 0
        assert '"name": "jsonserver"' in result.output

    def test_remote_list_csv(self, cli_runner: CliRunner, temp_env: Path):
        """Test listing remote hosts in CSV format."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(
            cli, ["remote", "add", "csvserver", "csv.example.com", "admin"]
        )

        result = cli_runner.invoke(cli, ["remote", "list", "-f", "csv"])

        assert result.exit_code == 0
        assert "id,name,host,username,port,tags" in result.output.splitlines()[0]

    def test_remote_show(self, cli_runner: CliRunner, temp_env: Path):
        """Test showing remote host details."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(
            cli,
            [
                "remote",
                "add",
                "showserver",
                "show.example.com",
                "showuser",
                "-p",
                "22",
                "-r",
                "/home/app",
            ],
        )

        result = cli_runner.invoke(cli, ["remote", "show", "showserver"])

        assert result.exit_code == 0
        _assert_plain_output_contains(
            result.output, "showserver", "show.example.com", "showuser"
        )

    def test_remote_show_formats(self, cli_runner: CliRunner, temp_env: Path):
        """Test showing remote host details in json/csv."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["remote", "add", "showjson", "json.example.com", "ops"])

        result_json = cli_runner.invoke(
            cli, ["remote", "show", "showjson", "--format", "json"]
        )
        assert result_json.exit_code == 0
        assert result_json.output.strip().startswith("{")

        result_csv = cli_runner.invoke(
            cli, ["remote", "show", "showjson", "--format", "csv"]
        )
        assert result_csv.exit_code == 0
        assert "id,name,host,username,port" in result_csv.output.splitlines()[0]

    def test_remote_show_not_found(self, cli_runner: CliRunner, temp_env: Path):
        """Test showing non-existent remote host."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(cli, ["remote", "show", "nonexistent"])

        assert result.exit_code == 0
        _assert_plain_output_contains(result.output, "not found")

    def test_remote_delete(self, cli_runner: CliRunner, temp_env: Path):
        """Test deleting a remote host."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(
            cli, ["remote", "add", "deleteserver", "delete.example.com", "user"]
        )

        result = cli_runner.invoke(cli, ["remote", "delete", "deleteserver", "-y"])

        assert result.exit_code == 0
        _assert_plain_output_contains(result.output, "Deleted remote host")

    def test_remote_delete_not_found(self, cli_runner: CliRunner, temp_env: Path):
        """Test deleting non-existent remote host."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(cli, ["remote", "delete", "nonexistent", "-y"])

        assert result.exit_code == 0
        _assert_plain_output_contains(result.output, "not found")

    def test_sync_help(self, cli_runner: CliRunner):
        """Test sync subgroup help."""
        result = cli_runner.invoke(cli, ["remote", "sync", "--help"])

        assert result.exit_code == 0
        _assert_plain_output_contains(result.output, "push", "pull")


class TestAuthListFormats:
    """Tests for auth list output formats."""

    def test_auth_list_csv(self, cli_runner: CliRunner, temp_env: Path):
        """Test auth list CSV output."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        init = cli_runner.invoke(cli, ["auth", "init", "--show-key"])
        api_key = _extract_api_key(init.output)

        result = cli_runner.invoke(
            cli,
            ["auth", "list", "--api-key", api_key, "--format", "csv"],
        )
        assert result.exit_code == 0
        assert "id,name,prefix,scopes" in result.output.splitlines()[0]

    def test_auth_list_json(self, cli_runner: CliRunner, temp_env: Path):
        """Test auth list JSON output."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        init = cli_runner.invoke(cli, ["auth", "init", "--show-key"])
        api_key = _extract_api_key(init.output)

        result = cli_runner.invoke(
            cli,
            ["auth", "list", "--api-key", api_key, "--format", "json"],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert "items" in payload

    def test_auth_recover_local_admin_refreshes_stale_key(
        self, cli_runner: CliRunner, temp_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Recover-local-admin should mint a usable replacement key and refresh the file."""
        from pms.config.settings import reload_settings

        monkeypatch.chdir(temp_env)
        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["auth", "init", "--show-key"])
        (temp_env / ".pms-admin-key").write_text("pms_stale_key", encoding="utf-8")

        recover = cli_runner.invoke(cli, ["auth", "recover-local-admin", "--show-key"])
        assert recover.exit_code == 0

        recovered_key = _extract_api_key(recover.output)
        assert (temp_env / ".pms-admin-key").read_text(
            encoding="utf-8"
        ) == recovered_key

        result = cli_runner.invoke(
            cli,
            ["auth", "list", "--api-key", recovered_key, "--format", "json"],
        )
        assert result.exit_code == 0, result.output

    def test_auth_init_writes_admin_key_with_owner_only_permissions(
        self, cli_runner: CliRunner, temp_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Auth init should persist the local admin key as a 0600 secret file."""
        from pms.config.settings import reload_settings

        monkeypatch.chdir(temp_env)
        reload_settings()

        cli_runner.invoke(cli, ["init"])
        result = cli_runner.invoke(cli, ["auth", "init", "--show-key"])

        assert result.exit_code == 0
        key_file = temp_env / ".pms-admin-key"
        assert key_file.exists()
        assert oct(key_file.stat().st_mode & 0o777) == "0o600"

    def test_auth_init_next_steps_use_wrapped_commands(
        self, cli_runner: CliRunner, temp_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Auth init should emit continuation steps through the shared command wrapper."""
        from pms.config.settings import reload_settings

        monkeypatch.chdir(temp_env)
        reload_settings()

        cli_runner.invoke(cli, ["init"])
        result = cli_runner.invoke(cli, ["auth", "init"])

        assert result.exit_code == 0
        assert _cli_step("auth create --help") in result.output
        assert _cli_step("auth list") in result.output
        assert (
            "  2. Create additional keys: pms auth create --help" not in result.output
        )
        assert "  3. List keys: pms auth list" not in result.output

    def test_auth_recover_local_admin_preserves_owner_only_permissions(
        self, cli_runner: CliRunner, temp_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Recover-local-admin should refresh the key file with 0600 permissions."""
        from pms.config.settings import reload_settings

        monkeypatch.chdir(temp_env)
        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["auth", "init", "--show-key"])
        key_file = temp_env / ".pms-admin-key"
        key_file.chmod(0o644)

        result = cli_runner.invoke(cli, ["auth", "recover-local-admin", "--show-key"])

        assert result.exit_code == 0
        assert oct(key_file.stat().st_mode & 0o777) == "0o600"

    def test_auth_recover_local_admin_next_steps_use_wrapped_commands(
        self, cli_runner: CliRunner, temp_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Recover-local-admin should emit wrapped continuation steps for local operators."""
        from pms.config.settings import reload_settings

        monkeypatch.chdir(temp_env)
        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["auth", "init", "--show-key"])
        result = cli_runner.invoke(cli, ["auth", "recover-local-admin", "--show-key"])

        assert result.exit_code == 0
        assert _cli_step("auth list") in result.output
        assert "  2. Validate server auth: pms auth list" not in result.output

    def test_auth_restore_reactivates_inactive_key(
        self, cli_runner: CliRunner, temp_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Auth restore should make a deactivated key usable again, not only unarchive it."""
        from pms.config.settings import reload_settings

        monkeypatch.chdir(temp_env)
        reload_settings()

        cli_runner.invoke(cli, ["init"])
        init = cli_runner.invoke(cli, ["auth", "init", "--show-key"])
        admin_key = _extract_api_key(init.output)

        create = cli_runner.invoke(
            cli,
            [
                "auth",
                "create",
                "--name",
                "Reader",
                "--scope",
                "tasks:read",
                "--api-key",
                admin_key,
            ],
        )
        assert create.exit_code == 0, create.output
        created_key = _extract_api_key(create.output)
        created_id = _extract_prefixed_value(create.output, "Key ID:")

        deactivate = cli_runner.invoke(
            cli, ["auth", "deactivate", created_id, "--api-key", admin_key]
        )
        assert deactivate.exit_code == 0, deactivate.output

        restore = cli_runner.invoke(
            cli, ["auth", "restore", created_id, "--api-key", admin_key]
        )
        assert restore.exit_code == 0, restore.output
        assert "restored/reactivated" in restore.output

        get_result = cli_runner.invoke(
            cli,
            [
                "auth",
                "get",
                created_id,
                "--api-key",
                admin_key,
                "--format",
                "json",
            ],
        )
        assert get_result.exit_code == 0, get_result.output
        payload = json.loads(get_result.output)
        assert payload["is_active"] is True


class TestAWSCommands:
    """Tests for AWS command help output."""

    def test_aws_help(self, cli_runner: CliRunner):
        """Test AWS group help."""
        result = cli_runner.invoke(cli, ["aws", "--help"])

        assert result.exit_code == 0
        _assert_plain_output_contains(
            result.output,
            "AWS test server management",
            "spot",
            "server",
            "test",
            "logs",
        )

    def test_aws_spot_help(self, cli_runner: CliRunner):
        """Test AWS spot subgroup help."""
        result = cli_runner.invoke(cli, ["aws", "spot", "--help"])

        assert result.exit_code == 0
        plain_output = _assert_plain_output_contains(result.output, "find")
        assert "cost-effective" in plain_output.lower()

    def test_aws_spot_find_help(self, cli_runner: CliRunner):
        """Test AWS spot find command help."""
        result = cli_runner.invoke(cli, ["aws", "spot", "find", "--help"])

        assert result.exit_code == 0
        _assert_plain_output_contains(
            result.output, "--vcpus", "--memory", "--max-price", "--format"
        )

    def test_aws_spot_find_json_uses_decimal_strings(
        self, cli_runner: CliRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import types

        import pms.aws as aws_module
        from pms.aws.models import SpotOption

        fake_boto3 = types.ModuleType("boto3")
        fake_boto3.Session = lambda: object()
        monkeypatch.setitem(sys.modules, "boto3", fake_boto3)

        class FakeSpotFinder:
            @staticmethod
            def create(_session: object, _regions: tuple[str, ...]) -> FakeSpotFinder:
                return FakeSpotFinder()

            async def find_best_options(self, _query: object, limit: int = 5):
                return [
                    SpotOption(
                        instance_type="t3.medium",
                        availability_zone="us-east-1a",
                        current_price=Decimal("0.012500"),
                        interruption_rate=0.05,
                        vcpus=2,
                        memory_gb=4.0,
                        score=0.91,
                    )
                ][:limit]

        monkeypatch.setattr(aws_module, "SpotFinder", FakeSpotFinder)

        result = cli_runner.invoke(cli, ["aws", "spot", "find", "--format", "json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output.strip().splitlines()[-1])
        assert payload[0]["current_price"] == "0.0125"

    def test_aws_server_json_uses_decimal_strings(
        self,
        cli_runner: CliRunner,
        temp_env: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import types

        import pms.aws as aws_module
        from pms.aws.models import ServerState, SpotServer, SpotServerConfig

        fake_boto3 = types.ModuleType("boto3")

        class _FakeSession:
            def client(self, *_args, **_kwargs):
                return object()

        fake_boto3.Session = _FakeSession
        monkeypatch.setitem(sys.modules, "boto3", fake_boto3)

        server = SpotServer(
            id="srv_money_1",
            instance_id="i-money-1",
            name="money-server",
            config=SpotServerConfig(name="money-server", instance_type="t3.medium"),
            state=ServerState.RUNNING,
            launched_at=datetime.now(UTC),
            region="us-east-1",
            availability_zone="us-east-1a",
            public_ip="127.0.0.1",
            hourly_price=Decimal("0.010000"),
            estimated_cost=Decimal("1.250000"),
        )

        class FakeFleetManager:
            def __init__(self, **_kwargs):
                pass

            async def list_servers(self, state=None, project_id=None):
                return [server]

            async def get_server(self, name_or_id: str):
                if name_or_id in {server.id, server.name}:
                    return server
                return None

            async def refresh_state(self, _server_id: str):
                return server

        monkeypatch.setattr(aws_module, "FleetManager", FakeFleetManager)

        cli_runner.invoke(cli, ["init"])

        list_result = cli_runner.invoke(
            cli, ["aws", "server", "list", "--format", "json"]
        )
        assert list_result.exit_code == 0, list_result.output
        list_payload = json.loads(list_result.output)
        assert list_payload["items"][0]["hourly_price"] == "0.01"
        assert list_payload["items"][0]["estimated_cost"] == "1.25"

        show_result = cli_runner.invoke(
            cli, ["aws", "server", "show", "money-server", "--format", "json"]
        )
        assert show_result.exit_code == 0, show_result.output
        show_payload = json.loads(show_result.output)
        assert show_payload["hourly_price"] == "0.01"
        assert show_payload["estimated_cost"] == "1.25"


class TestDashboardFormats:
    """Tests for dashboard format outputs."""

    def test_dashboard_json_csv(self, cli_runner: CliRunner, temp_env: Path):
        """Test dashboard JSON/CSV output."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(
            cli,
            [
                "config",
                "set",
                "--write-mode",
                "prefer_server",
                "--server-url",
                "http://127.0.0.1:1",
            ],
        )
        cli_runner.invoke(cli, ["project", "create", "Dashboard Project"])
        cli_runner.invoke(cli, ["task", "add", "Dashboard Project", "Dashboard Task"])

        json_out = cli_runner.invoke(cli, ["dashboard", "--format", "json"])
        assert json_out.exit_code == 0
        assert json_out.output.strip().startswith("{")
        payload = json.loads(json_out.output)
        assert payload["purpose"].startswith("Overall live-state control plane")
        assert (
            payload["runtime"]["coordination"]["state"] == "degraded_server_unreachable"
        )
        assert (
            payload["runtime"]["coordination"]["recovery"]["kind"]
            == "restore_preferred_server"
        )
        assert "links" in payload
        assert "next_steps" in payload
        assert payload["focus_task"]["title"] == "Dashboard Task"
        assert payload["total_projects"] == 1
        assert payload["instance_totals"]["total_projects"] >= 1
        assert payload["visible_totals"]["population"] == "visible_operator"
        assert payload["instance_totals"]["population"] == "all_non_archived_retained"
        assert payload["links"]["guide"] == _cli_step("start --format json")
        assert payload["links"]["queues"] == _cli_step("queue presets --format json")
        assert payload["links"]["daily_focus"] == _cli_step(
            'work daily --scope-type project --scope "Dashboard Project" --format json'
        )
        assert payload["next_steps"][0] == _cli_step(
            "runtime prefer-server --host 127.0.0.1 --port 27541"
        )
        assert payload["next_steps"]
        assert payload["cli"]["alternate_prefix"] is None
        assert "fast_path" not in payload

        csv_out = cli_runner.invoke(cli, ["dashboard", "--format", "csv"])
        assert csv_out.exit_code == 0
        assert "total_projects,total_tasks" in csv_out.output.splitlines()[0]

    def test_dashboard_surfaces_freshest_visible_activity_and_transition(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Older Dashboard Project"])
        older_task_id = _extract_id(
            cli_runner.invoke(
                cli,
                ["task", "add", "Older Dashboard Project", "Older Dashboard Task"],
            ).output
        )
        cli_runner.invoke(
            cli,
            ["task", "start", older_task_id, "--by", "tester", "--format", "json"],
        )
        cli_runner.invoke(cli, ["project", "create", "Completed Dashboard Project"])
        completed_task_id = _extract_id(
            cli_runner.invoke(
                cli,
                ["task", "add", "Completed Dashboard Project", "Done Dashboard Task"],
            ).output
        )
        cli_runner.invoke(
            cli,
            [
                "task",
                "complete",
                completed_task_id,
                "--by",
                "tester",
                "--format",
                "json",
            ],
        )
        cli_runner.invoke(cli, ["project", "complete", "Completed Dashboard Project"])

        result = cli_runner.invoke(cli, ["dashboard", "--format", "json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        visible_projects = [
            *payload["active_projects"],
            *payload["recently_completed_projects"],
        ]
        freshest_activity = max(
            visible_projects,
            key=lambda item: str(item.get("last_activity_at") or ""),
        )
        freshest_transition = max(
            visible_projects,
            key=lambda item: str(item.get("last_transition_at") or ""),
        )
        assert (
            payload["freshest_visible_activity"]["project_id"]
            == freshest_activity["project_id"]
        )
        assert (
            payload["freshest_visible_transition"]["project_id"]
            == freshest_transition["project_id"]
        )
        assert payload["freshest_visible_activity"]["last_activity_at"] is not None
        assert payload["freshest_visible_transition"]["last_transition_at"] is not None

        text_result = cli_runner.invoke(cli, ["dashboard"])
        assert text_result.exit_code == 0, text_result.output
        _assert_plain_output_contains(
            text_result.output,
            "Freshest Visible Activity:",
            "Freshest Visible Transition:",
        )

    def test_dashboard_json_suppresses_audit_generated_projects_by_default(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Audit Project abc123"])
        cli_runner.invoke(
            cli, ["task", "add", "Audit Project abc123", "Audit Ready Task"]
        )
        cli_runner.invoke(cli, ["project", "create", "Operator Project"])
        cli_runner.invoke(
            cli, ["task", "add", "Operator Project", "Operator Ready Task"]
        )

        result = cli_runner.invoke(cli, ["dashboard", "--format", "json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["focus_task"]["title"] == "Operator Ready Task"
        assert payload["suppressed_generated_projects"] == 1
        assert [item["project_name"] for item in payload["active_projects"]] == [
            "Operator Project"
        ]
        active_project = payload["active_projects"][0]
        assert active_project["id"] == active_project["project_id"]
        assert (
            active_project["name"]
            == active_project["project_name"]
            == "Operator Project"
        )
        assert active_project["status"] == "active"
        assert active_project["updated_at"] is not None
        assert active_project["last_activity_at"] is not None
        assert active_project["last_transition_at"] is not None
        assert active_project["links"]["self"] == _cli_step(
            'project show "Operator Project" --format json'
        )
        assert all(
            item["project_name"] != "Audit Project abc123"
            for item in payload["ready_tasks"]
        )
        assert payload["total_projects"] == 1
        assert payload["instance_totals"]["total_projects"] == 2

    def test_dashboard_json_uses_visible_totals_and_blocked_details(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Audit Project abc123"])
        cli_runner.invoke(
            cli, ["task", "add", "Audit Project abc123", "Audit Ready Task"]
        )
        cli_runner.invoke(cli, ["project", "create", "Operator Project"])
        blocker_result = cli_runner.invoke(
            cli, ["task", "add", "Operator Project", "Operator Blocker"]
        )
        blocker_id = _extract_id(blocker_result.output)
        blocked_result = cli_runner.invoke(
            cli, ["task", "add", "Operator Project", "Operator Blocked"]
        )
        blocked_id = _extract_id(blocked_result.output)
        cli_runner.invoke(cli, ["task", "dep", "add", blocked_id, blocker_id])

        result = cli_runner.invoke(cli, ["dashboard", "--format", "json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["total_projects"] == 1
        assert payload["blocked_tasks"] == 1
        assert payload["visible_totals"]["blocked_tasks"] == 1
        assert payload["instance_totals"]["total_projects"] == 2
        assert payload["instance_totals"]["blocked_tasks"] >= 1
        assert payload["blocked_items"][0]["title"] == "Operator Blocked"
        assert payload["blocked_items"][0]["blocked_by_details"][0]["title"] == (
            "Operator Blocker"
        )

    def test_dashboard_instance_totals_count_all_non_archived_tasks(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Audit Project abc123"])
        cli_runner.invoke(
            cli, ["task", "add", "Audit Project abc123", "Hidden Ready Task"]
        )
        cli_runner.invoke(cli, ["project", "create", "Operator Count Project"])
        done_result = cli_runner.invoke(
            cli, ["task", "add", "Operator Count Project", "Visible Done Task"]
        )
        done_task_id = _extract_id(done_result.output)
        cli_runner.invoke(cli, ["task", "start", done_task_id, "--by", "tester"])
        cli_runner.invoke(cli, ["task", "complete", done_task_id, "--by", "tester"])
        cli_runner.invoke(
            cli, ["task", "add", "Operator Count Project", "Visible Todo Task"]
        )

        result = cli_runner.invoke(cli, ["dashboard", "--format", "json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["total_projects"] == 1
        assert payload["total_tasks"] == 2
        assert payload["completed_tasks"] == 1
        assert payload["visible_totals"]["population"] == "visible_operator"
        assert payload["visible_totals"]["total_tasks"] == 2
        assert payload["visible_totals"]["completed_tasks"] == 1
        assert payload["instance_totals"]["population"] == "all_non_archived_retained"
        assert payload["instance_totals"]["total_projects"] == 2
        assert payload["instance_totals"]["total_tasks"] == 3
        assert payload["instance_totals"]["completed_tasks"] == 1

    def test_dashboard_instance_totals_exclude_archived_projects(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Visible Project"])
        cli_runner.invoke(cli, ["task", "add", "Visible Project", "Visible Task"])
        cli_runner.invoke(cli, ["project", "create", "Archived Project"])
        cli_runner.invoke(cli, ["task", "add", "Archived Project", "Archived Task"])
        cli_runner.invoke(
            cli, ["project", "update", "Archived Project", "--status", "archived"]
        )

        result = cli_runner.invoke(cli, ["dashboard", "--format", "json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["instance_totals"]["population"] == "all_non_archived_retained"
        assert payload["instance_totals"]["total_projects"] == 1
        assert payload["instance_totals"]["total_tasks"] == 1

    def test_dashboard_json_uses_full_visible_active_population_beyond_first_raw_page(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Operator Project"])
        cli_runner.invoke(
            cli, ["task", "add", "Operator Project", "Operator Ready Task"]
        )
        for index in range(101):
            cli_runner.invoke(cli, ["project", "create", f"Audit Project {index:03d}"])

        result = cli_runner.invoke(cli, ["dashboard", "--format", "json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["total_projects"] == 1
        assert [item["project_name"] for item in payload["active_projects"]] == [
            "Operator Project"
        ]
        assert any(
            item["project_name"] == "Operator Project"
            for item in payload["ready_tasks"]
        )
        assert payload["suppressed_generated_projects"] >= 101

    def test_dashboard_surfaces_instance_scope_and_recent_completed_projects(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Active Project"])
        cli_runner.invoke(cli, ["task", "add", "Active Project", "Active Task"])
        cli_runner.invoke(cli, ["project", "create", "Completed Project"])
        done_result = cli_runner.invoke(
            cli, ["task", "add", "Completed Project", "Done Task"]
        )
        done_task_id = _extract_id(done_result.output)
        cli_runner.invoke(cli, ["task", "start", done_task_id, "--by", "tester"])
        cli_runner.invoke(cli, ["task", "complete", done_task_id, "--by", "tester"])
        cli_runner.invoke(cli, ["project", "complete", "Completed Project"])

        json_result = cli_runner.invoke(cli, ["dashboard", "--format", "json"])

        assert json_result.exit_code == 0, json_result.output
        payload = json.loads(json_result.output)
        assert payload["scope"]["kind"] == "instance_dashboard"
        assert "Completed scoped work remains terminal" in payload["scope"]["summary"]
        assert (
            "Recently completed scoped work remains terminal"
            in payload["completion_context"]["summary"]
        )
        assert (
            payload["recently_completed_projects"][0]["project_name"]
            == "Completed Project"
        )
        completed_project = payload["recently_completed_projects"][0]
        active_project = payload["active_projects"][0]
        assert completed_project["id"] == completed_project["project_id"]
        assert completed_project["name"] == completed_project["project_name"]
        assert completed_project["status"] == "completed"
        assert completed_project["last_activity_at"] is not None
        assert completed_project["last_transition_at"] is not None
        assert set(completed_project) == set(active_project)
        assert completed_project["total_tasks"] == 1
        assert completed_project["completed_tasks"] == 1
        assert completed_project["in_progress_tasks"] == 0
        assert completed_project["blocked_tasks"] == 0
        assert completed_project["completion_percent"] == 100
        assert completed_project["health_score"] == 1.0
        assert completed_project["links"]["summary"] == _cli_step(
            'project summary "Completed Project" --format json'
        )
        completion_item = payload["completion_context"]["items"][0]
        assert set(completed_project).issubset(set(completion_item))
        assert completion_item["project_id"] == completed_project["project_id"]
        assert (
            completion_item["last_activity_at"] == completed_project["last_activity_at"]
        )
        assert (
            completion_item["last_transition_at"]
            == completed_project["last_transition_at"]
        )
        assert any(
            step == _cli_step('project show "Completed Project" --format json')
            for step in completion_item["next_steps"]
        )
        assert any(
            step == _cli_step('project show "Completed Project" --format json')
            for step in payload["next_steps"]
        )

        text_result = cli_runner.invoke(cli, ["dashboard"])
        assert text_result.exit_code == 0, text_result.output
        _assert_plain_output_contains(
            text_result.output,
            "Scope: Instance-wide dashboard view.",
            "Recently Completed Projects:",
            "Completed Project",
        )

    def test_project_and_dashboard_keep_completed_project_terminal_when_completed_task_gets_new_activity(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Still Active Project"])
        cli_runner.invoke(cli, ["task", "add", "Still Active Project", "Active Task"])
        cli_runner.invoke(cli, ["project", "create", "Completed Fresh Project"])
        done_result = cli_runner.invoke(
            cli, ["task", "add", "Completed Fresh Project", "Done Task"]
        )
        done_task_id = _extract_id(done_result.output)
        cli_runner.invoke(cli, ["task", "start", done_task_id, "--by", "tester"])
        cli_runner.invoke(cli, ["task", "complete", done_task_id, "--by", "tester"])
        cli_runner.invoke(cli, ["project", "complete", "Completed Fresh Project"])
        comment_result = cli_runner.invoke(
            cli,
            [
                "comment",
                "add",
                "task",
                done_task_id,
                "Fresh terminal activity",
                "--by",
                "tester",
            ],
        )
        assert comment_result.exit_code == 0, comment_result.output

        project_list = cli_runner.invoke(cli, ["project", "list", "--format", "json"])
        assert project_list.exit_code == 0, project_list.output
        project_payload = json.loads(project_list.output)
        completed_project = next(
            item
            for item in project_payload["items"]
            if item["project_name"] == "Completed Fresh Project"
        )
        assert completed_project["status"] == "completed"
        assert completed_project["operator_category"] == "project_history"
        assert (
            project_payload["freshest_visible_activity"]["project_id"]
            == completed_project["project_id"]
        )

        dashboard_result = cli_runner.invoke(cli, ["dashboard", "--format", "json"])
        assert dashboard_result.exit_code == 0, dashboard_result.output
        dashboard_payload = json.loads(dashboard_result.output)
        assert {
            item["project_name"] for item in dashboard_payload["active_projects"]
        } == {"Still Active Project"}
        assert {
            item["project_name"]
            for item in dashboard_payload["recently_completed_projects"]
        } == {"Completed Fresh Project"}
        assert (
            dashboard_payload["freshest_visible_activity"]["project_id"]
            == completed_project["project_id"]
        )
        assert (
            "Recently completed scoped work remains terminal"
            in dashboard_payload["completion_context"]["summary"]
        )

    def test_dashboard_active_focus_does_not_append_completed_project_next_steps(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Live Dashboard Project"])
        live_task = cli_runner.invoke(
            cli, ["task", "add", "Live Dashboard Project", "Live Task"]
        )
        live_task_id = _extract_id(live_task.output)
        cli_runner.invoke(cli, ["task", "start", live_task_id, "--by", "tester"])
        cli_runner.invoke(cli, ["project", "create", "Completed Dashboard Project"])
        done_task = cli_runner.invoke(
            cli, ["task", "add", "Completed Dashboard Project", "Done Task"]
        )
        done_task_id = _extract_id(done_task.output)
        cli_runner.invoke(cli, ["task", "complete", done_task_id, "--by", "tester"])
        cli_runner.invoke(cli, ["project", "complete", "Completed Dashboard Project"])

        result = cli_runner.invoke(cli, ["dashboard", "--format", "json"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["scope"]["active_visible_projects"] == 1
        assert any(
            step
            == _cli_step('task show "Live Task" --project "Live Dashboard Project"')
            for step in payload["next_steps"]
        )
        assert all(
            step
            != _cli_step('project show "Completed Dashboard Project" --format json')
            for step in payload["next_steps"]
        )

    def test_dashboard_completion_context_is_truthful_when_no_visible_active_work_remains(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Completed Visible Project"])
        done_result = cli_runner.invoke(
            cli, ["task", "add", "Completed Visible Project", "Done Task"]
        )
        done_task_id = _extract_id(done_result.output)
        cli_runner.invoke(cli, ["task", "start", done_task_id, "--by", "tester"])
        cli_runner.invoke(cli, ["task", "complete", done_task_id, "--by", "tester"])
        cli_runner.invoke(cli, ["project", "complete", "Completed Visible Project"])
        cli_runner.invoke(cli, ["project", "create", "Runtime Repro Project 11"])

        result = cli_runner.invoke(cli, ["dashboard", "--format", "json"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["scope"]["active_visible_projects"] == 0
        assert (
            "No other visible active work is currently surfaced"
            in payload["completion_context"]["summary"]
        )
        item = payload["completion_context"]["items"][0]
        recent_item = payload["recently_completed_projects"][0]
        assert set(recent_item).issubset(set(item))
        assert item["project_id"] == recent_item["project_id"]
        assert item["last_activity_at"] == recent_item["last_activity_at"]
        assert item["last_transition_at"] == recent_item["last_transition_at"]
        assert item["operator_category"] == "project_history"
        assert item["operator_category_label"] == "Project History"
        assert item["operator_visibility_reason"] == "retained historical lookup"
        assert any(
            step == _cli_step('project show "Completed Visible Project" --format json')
            for step in item["next_steps"]
        )

    def test_dashboard_excludes_active_filter_fixture_projects_from_active_work(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Goal Filter Project A"])
        cli_runner.invoke(cli, ["project", "create", "Recent Progress Project"])
        live_task = cli_runner.invoke(
            cli, ["task", "add", "Recent Progress Project", "Recent Progress Task"]
        )
        live_task_id = _extract_id(live_task.output)
        cli_runner.invoke(cli, ["task", "start", live_task_id, "--by", "tester"])

        result = cli_runner.invoke(cli, ["dashboard", "--format", "json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["scope"]["active_visible_projects"] == 1
        active_names = {item["project_name"] for item in payload["active_projects"]}
        assert "Recent Progress Project" in active_names
        assert "Goal Filter Project A" not in active_names

    def test_dashboard_and_start_exclude_stale_recent_progress_fixture_project(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Recent Progress Project"])
        task_result = cli_runner.invoke(
            cli, ["task", "add", "Recent Progress Project", "Recent Progress Task"]
        )
        task_id = _extract_id(task_result.output)
        cli_runner.invoke(cli, ["task", "start", task_id, "--by", "tester"])
        _age_project_and_task_timestamps("Recent Progress Project", days=2)

        dashboard_result = cli_runner.invoke(cli, ["dashboard", "--format", "json"])
        assert dashboard_result.exit_code == 0, dashboard_result.output
        dashboard_payload = json.loads(dashboard_result.output)
        assert dashboard_payload["scope"]["active_visible_projects"] == 0
        assert dashboard_payload["active_projects"] == []

        start_result = cli_runner.invoke(cli, ["start", "--format", "json"])
        assert start_result.exit_code == 0, start_result.output
        start_payload = json.loads(start_result.output)
        assert start_payload["focus_task"] is None
        assert all(
            "Recent Progress Project" not in step
            for step in start_payload["next_steps"]
        )

    def test_start_surfaces_recent_terminal_work_when_no_active_focus_remains(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        project_result = cli_runner.invoke(
            cli, ["project", "create", "Completed Start Project"]
        )
        completed_project_id = _extract_id(project_result.output)
        done_result = cli_runner.invoke(
            cli, ["task", "add", "Completed Start Project", "Done Start Task"]
        )
        done_task_id = _extract_id(done_result.output)
        cli_runner.invoke(cli, ["task", "start", done_task_id, "--by", "tester"])
        cli_runner.invoke(cli, ["task", "complete", done_task_id, "--by", "tester"])
        cli_runner.invoke(cli, ["project", "complete", "Completed Start Project"])
        cli_runner.invoke(cli, ["project", "create", "Runtime Repro Project 13"])

        result = cli_runner.invoke(cli, ["start", "--format", "json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["focus_task"] is None
        assert (
            payload["terminal_reason"]
            == "no operator-visible active work is currently surfaced"
        )
        assert payload["scope"]["active_visible_projects"] == 0
        assert payload["scope"]["recently_completed_projects"] >= 1
        assert (
            "Recently completed scoped work remains terminal."
            in payload["completion_context"]["summary"]
        )
        completed_item = next(
            item
            for item in payload["recently_completed_projects"]
            if item["project_id"] == completed_project_id
        )
        assert completed_item["id"] == completed_project_id
        assert completed_item["name"] == "Completed Start Project"
        assert completed_item["project_name"] == "Completed Start Project"
        assert completed_item["status"] == "completed"
        assert completed_item["operator_category"] == "project_history"
        assert completed_item["total_tasks"] == 1
        assert completed_item["completed_tasks"] == 1
        assert completed_item["in_progress_tasks"] == 0
        assert completed_item["blocked_tasks"] == 0
        assert completed_item["completion_percent"] == 100
        assert completed_item["health_score"] == 1.0
        completion_item = payload["completion_context"]["items"][0]
        assert set(completed_item).issubset(set(completion_item))
        assert completion_item["project_id"] == completion_item["id"]
        assert completion_item["project_id"] == completed_project_id
        assert completion_item["last_activity_at"] == completed_item["last_activity_at"]
        assert (
            completion_item["last_transition_at"]
            == completed_item["last_transition_at"]
        )
        assert any(
            step == _cli_step('project show "Completed Start Project" --format json')
            for step in completion_item["next_steps"]
        )
        assert (
            payload["freshest_visible_activity"]["project_id"] == completed_project_id
        )
        assert (
            payload["freshest_visible_transition"]["project_id"] == completed_project_id
        )
        assert (
            payload["completion_context"]["items"][0]["project_id"]
            == completed_project_id
        )
        assert any(
            step == _cli_step('project show "Completed Start Project" --format json')
            for step in payload["next_steps"]
        )

    def test_task_list_and_ready_no_actionable_work_use_truthful_empty_guidance(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Recent Progress Project"])
        task_result = cli_runner.invoke(
            cli, ["task", "add", "Recent Progress Project", "Recent Progress Task"]
        )
        assert task_result.exit_code == 0, task_result.output
        _age_project_and_task_timestamps("Recent Progress Project", days=2)

        list_result = cli_runner.invoke(
            cli, ["task", "list", "--status", "todo", "--format", "json"]
        )
        assert list_result.exit_code == 0, list_result.output
        list_payload = json.loads(list_result.output)
        assert list_payload["items"] == []
        assert list_payload["suppressed_hidden_count"] == 1
        assert (
            list_payload["terminal_reason"]
            == "no operator-visible active work is currently surfaced"
        )
        assert (
            "No operator-visible active-project tasks are currently surfaced"
            in (list_payload["scope"]["summary"])
        )
        assert "--status todo" in list_payload["links"]["self"]
        assert any(
            step.startswith(_cli_step("task list"))
            and "--status todo" in step
            and "--include-generated" in step
            and "--format json" in step
            for step in list_payload["next_steps"]
        )
        assert _cli_step("quickstart --defaults") in list_payload["next_steps"]

        ready_result = cli_runner.invoke(
            cli, ["task", "ready", "--status", "todo", "--format", "json"]
        )
        assert ready_result.exit_code == 0, ready_result.output
        ready_payload = json.loads(ready_result.output)
        assert ready_payload["items"] == []
        assert ready_payload["suppressed_hidden_count"] == 1
        assert (
            "No operator-visible active-project tasks are currently surfaced"
            in (ready_payload["scope"]["summary"])
        )
        assert "--status todo" in ready_payload["links"]["self"]
        assert any(
            step.startswith(_cli_step("task ready"))
            and "--status todo" in step
            and "--include-generated" in step
            and "--format json" in step
            for step in ready_payload["next_steps"]
        )
        assert _cli_step("quickstart --defaults") in ready_payload["next_steps"]

    def test_task_search_and_stale_no_actionable_work_use_truthful_empty_guidance(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Recent Progress Project"])
        task_result = cli_runner.invoke(
            cli, ["task", "add", "Recent Progress Project", "Hidden Retained Task"]
        )
        assert task_result.exit_code == 0, task_result.output
        _age_project_and_task_timestamps("Recent Progress Project", days=2)

        search_result = cli_runner.invoke(
            cli,
            ["task", "search", "--query", "Hidden Retained", "--format", "json"],
        )
        assert search_result.exit_code == 0, search_result.output
        search_payload = json.loads(search_result.output)
        assert search_payload["items"] == []
        assert search_payload["suppressed_hidden_count"] == 1
        assert (
            "No operator-visible active-project tasks are currently surfaced"
            in (search_payload["scope"]["summary"])
        )
        assert "--query 'Hidden Retained'" in search_payload["links"]["self"]
        assert any(
            step.startswith(_cli_step("task search"))
            and "Hidden Retained" in step
            and "--include-generated" in step
            and "--format json" in step
            for step in search_payload["next_steps"]
        )
        assert _cli_step("quickstart --defaults") in search_payload["next_steps"]

        stale_result = cli_runner.invoke(
            cli,
            ["task", "stale", "--days", "0", "--format", "json"],
        )
        assert stale_result.exit_code == 0, stale_result.output
        stale_payload = json.loads(stale_result.output)
        assert stale_payload["items"] == []
        assert stale_payload["suppressed_hidden_count"] == 1
        assert (
            "No operator-visible active-project tasks are currently surfaced"
            in (stale_payload["scope"]["summary"])
        )
        assert "--days 0" in stale_payload["links"]["self"]
        assert any(
            step.startswith(_cli_step("task stale"))
            and "--include-generated" in step
            and "--format json" in step
            for step in stale_payload["next_steps"]
        )

    def test_task_blocked_and_duplicates_no_actionable_work_use_truthful_empty_guidance(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Recent Progress Project"])
        first = cli_runner.invoke(
            cli, ["task", "add", "Recent Progress Project", "Repeated Hidden Task"]
        )
        second = cli_runner.invoke(
            cli, ["task", "add", "Recent Progress Project", "Repeated Hidden Task"]
        )
        assert first.exit_code == 0, first.output
        assert second.exit_code == 0, second.output
        first_id = _extract_id(first.output)
        second_id = _extract_id(second.output)
        dep_result = cli_runner.invoke(cli, ["task", "dep", "add", second_id, first_id])
        assert dep_result.exit_code == 0, dep_result.output
        _age_project_and_task_timestamps("Recent Progress Project", days=2)

        blocked_result = cli_runner.invoke(cli, ["task", "blocked", "--format", "json"])
        assert blocked_result.exit_code == 0, blocked_result.output
        blocked_payload = json.loads(blocked_result.output)
        assert blocked_payload["items"] == []
        assert blocked_payload["suppressed_hidden_count"] >= 1
        assert (
            "No operator-visible active-project tasks are currently surfaced"
            in (blocked_payload["scope"]["summary"])
        )
        assert blocked_payload["links"]["self"] == _cli_step(
            "task blocked --format json"
        )
        assert any(
            step.startswith(_cli_step("task blocked"))
            and "--include-generated" in step
            and "--format json" in step
            for step in blocked_payload["next_steps"]
        )

        duplicates_result = cli_runner.invoke(
            cli, ["task", "duplicates", "--format", "json"]
        )
        assert duplicates_result.exit_code == 0, duplicates_result.output
        duplicates_payload = json.loads(duplicates_result.output)
        assert duplicates_payload["items"] == []
        assert duplicates_payload["suppressed_hidden_count"] >= 2
        assert (
            "No operator-visible active-project tasks are currently surfaced"
            in (duplicates_payload["scope"]["summary"])
        )
        assert "--min-count 2" in duplicates_payload["links"]["self"]
        assert any(
            step.startswith(_cli_step("task duplicates"))
            and "--include-generated" in step
            and "--format json" in step
            for step in duplicates_payload["next_steps"]
        )

    def test_task_stale_self_link_preserves_status_and_days_filters(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(
            cli,
            ["task", "stale", "--days", "7", "--status", "todo", "--format", "json"],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert "--days 7" in payload["links"]["self"]
        assert "--status todo" in payload["links"]["self"]

    def test_plan_list_completion_context_is_truthful_when_no_visible_active_work_remains(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Completed Visible Plan Project"])
        cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Completed Visible Plan",
                "--project",
                "Completed Visible Plan Project",
                "--status",
                "completed",
                "--content",
                "{}",
            ],
        )
        cli_runner.invoke(cli, ["project", "create", "Runtime Repro Project 12"])
        cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Runtime Repro Project 12 Plan",
                "--project",
                "Runtime Repro Project 12",
                "--status",
                "completed",
                "--content",
                "{}",
            ],
        )

        result = cli_runner.invoke(cli, ["plan", "list", "--format", "json"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["scope"]["active_visible_plans"] == 0
        assert (
            "No other visible active or draft plans are currently surfaced"
            in payload["completion_context"]["summary"]
        )

    def test_dashboard_and_start_treat_completed_plan_only_project_as_terminal(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Completed Visible Plan Project"])
        cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Completed Visible Plan",
                "--project",
                "Completed Visible Plan Project",
                "--status",
                "completed",
                "--content",
                "{}",
            ],
        )
        cli_runner.invoke(
            cli,
            [
                "project",
                "update",
                "Completed Visible Plan Project",
                "--status",
                "active",
            ],
        )
        cli_runner.invoke(cli, ["project", "create", "Runtime Repro Project 14"])

        dashboard_result = cli_runner.invoke(cli, ["dashboard", "--format", "json"])
        assert dashboard_result.exit_code == 0, dashboard_result.output
        dashboard_payload = json.loads(dashboard_result.output)
        assert dashboard_payload["scope"]["active_visible_projects"] == 0
        assert dashboard_payload["active_projects"] == []
        assert {
            item["project_name"]
            for item in dashboard_payload["recently_completed_projects"]
        } == {"Completed Visible Plan Project"}

        start_result = cli_runner.invoke(cli, ["start", "--format", "json"])
        assert start_result.exit_code == 0, start_result.output
        start_payload = json.loads(start_result.output)
        assert start_payload["scope"]["active_visible_projects"] == 0
        assert start_payload["focus_task"] is None
        assert (
            start_payload["terminal_reason"]
            == "no operator-visible active work is currently surfaced"
        )
        assert {
            item["project_name"]
            for item in start_payload["recently_completed_projects"]
        } == {"Completed Visible Plan Project"}

    def test_project_show_and_list_use_effective_terminal_status_for_plan_only_project(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Effective Status Plan Project"])
        cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Effective Status Plan",
                "--project",
                "Effective Status Plan Project",
                "--status",
                "completed",
                "--content",
                "{}",
            ],
        )
        cli_runner.invoke(
            cli,
            [
                "project",
                "update",
                "Effective Status Plan Project",
                "--status",
                "active",
            ],
        )

        show_result = cli_runner.invoke(
            cli,
            ["project", "show", "Effective Status Plan Project", "--format", "json"],
        )
        assert show_result.exit_code == 0, show_result.output
        show_payload = json.loads(show_result.output)
        assert show_payload["status"] == "completed"
        assert show_payload["stored_status"] == "active"
        assert (
            show_payload["terminal_reason"]
            == "all linked execution scopes are already terminal"
        )
        assert show_payload["operator_category"] == "project_history"

        list_result = cli_runner.invoke(
            cli,
            ["project", "list", "--status", "completed", "--format", "json"],
        )
        assert list_result.exit_code == 0, list_result.output
        list_payload = json.loads(list_result.output)
        assert [item["project_name"] for item in list_payload["items"]] == [
            "Effective Status Plan Project"
        ]
        assert list_payload["items"][0]["status"] == "completed"
        assert list_payload["items"][0]["stored_status"] == "active"

    def test_completed_project_with_only_draft_plan_residue_stays_terminal(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Completed Draft Residue Project"])
        task_result = cli_runner.invoke(
            cli,
            [
                "task",
                "add",
                "Completed Draft Residue Project",
                "Completed Draft Residue Task",
            ],
        )
        assert task_result.exit_code == 0, task_result.output
        task_id = _extract_id(task_result.output)
        cli_runner.invoke(cli, ["task", "start", task_id, "--by", "tester"])
        cli_runner.invoke(cli, ["task", "complete", task_id, "--by", "tester"])
        cli_runner.invoke(
            cli,
            [
                "plan",
                "create",
                "Completed Draft Residue Plan",
                "--project",
                "Completed Draft Residue Project",
                "--status",
                "draft",
                "--content",
                "{}",
            ],
        )
        cli_runner.invoke(
            cli,
            ["project", "complete", "Completed Draft Residue Project"],
        )
        cli_runner.invoke(cli, ["project", "create", "Runtime Repro Project 15"])

        dashboard_result = cli_runner.invoke(cli, ["dashboard", "--format", "json"])
        assert dashboard_result.exit_code == 0, dashboard_result.output
        dashboard_payload = json.loads(dashboard_result.output)
        assert all(
            item["project_name"] != "Completed Draft Residue Project"
            for item in dashboard_payload["active_projects"]
        )
        assert any(
            item["project_name"] == "Completed Draft Residue Project"
            for item in dashboard_payload["recently_completed_projects"]
        )

        show_result = cli_runner.invoke(
            cli,
            ["project", "show", "Completed Draft Residue Project", "--format", "json"],
        )
        assert show_result.exit_code == 0, show_result.output
        show_payload = json.loads(show_result.output)
        assert show_payload["status"] == "completed"
        assert show_payload["stored_status"] == "completed"
        assert (
            show_payload["terminal_reason"]
            == "all linked execution scopes are already terminal"
        )

    def test_dashboard_queue_presets_show_truncation_against_total_count(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Queue Truth Project"])
        blocker_ids: list[str] = []
        dependent_ids: list[str] = []
        for index in range(4):
            blocker_result = cli_runner.invoke(
                cli, ["task", "add", "Queue Truth Project", f"Blocker {index}"]
            )
            blocker_ids.append(_extract_id(blocker_result.output))
            dependent_result = cli_runner.invoke(
                cli, ["task", "add", "Queue Truth Project", f"Dependent {index}"]
            )
            dependent_ids.append(_extract_id(dependent_result.output))
            cli_runner.invoke(
                cli,
                ["task", "dep", "add", dependent_ids[-1], blocker_ids[-1]],
            )

        result = cli_runner.invoke(cli, ["dashboard", "--format", "json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        blocked_queue = next(
            item for item in payload["queue_presets"] if item["name"] == "blocked"
        )
        assert blocked_queue["total_count"] == 4
        assert blocked_queue["displayed_count"] == 3
        assert blocked_queue["is_truncated"] is True

    def test_queue_presets_json_normalizes_next_steps(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(
            cli,
            ["queue", "presets", "--format", "json", "--view", "detail"],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["next_steps"] == [
            _cli_step("queue list"),
            _cli_step("queue create <name> --filters '{}'"),
        ]
        assert all(
            item["population"] == "visible_operator" for item in payload["items"]
        )

    def test_queue_presets_project_json_marks_scoped_population(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Scoped Queue Project"])
        cli_runner.invoke(
            cli, ["task", "add", "Scoped Queue Project", "Scoped Ready Task"]
        )

        result = cli_runner.invoke(
            cli,
            [
                "queue",
                "presets",
                "--project",
                "Scoped Queue Project",
                "--format",
                "json",
                "--view",
                "detail",
            ],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert all(item["population"] == "scoped_project" for item in payload["items"])

    def test_dashboard_and_queue_presets_exclude_archived_project_work(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Archived Queue Project"])
        cli_runner.invoke(
            cli, ["task", "add", "Archived Queue Project", "Archived Ready Task"]
        )
        cli_runner.invoke(cli, ["project", "delete", "Archived Queue Project"])

        dashboard_result = cli_runner.invoke(cli, ["dashboard", "--format", "json"])
        assert dashboard_result.exit_code == 0, dashboard_result.output
        dashboard_payload = json.loads(dashboard_result.output)
        assert all(
            item["project_name"] != "Archived Queue Project"
            for item in dashboard_payload["ready_tasks"]
        )
        assert all(
            item["project_name"] != "Archived Queue Project"
            for item in dashboard_payload["active_projects"]
        )
        ready_queue = next(
            item
            for item in dashboard_payload["queue_presets"]
            if item["name"] == "ready"
        )
        assert all(
            item["project_name"] != "Archived Queue Project"
            for item in ready_queue["items"]
        )

        queue_result = cli_runner.invoke(
            cli, ["queue", "presets", "--format", "json", "--view", "detail"]
        )
        assert queue_result.exit_code == 0, queue_result.output
        queue_payload = json.loads(queue_result.output)
        queue_ready = next(
            item for item in queue_payload["items"] if item["name"] == "ready"
        )
        assert queue_ready["total_count"] == ready_queue["total_count"]
        assert queue_ready["displayed_count"] == ready_queue["displayed_count"]
        assert all(
            item["project_name"] != "Archived Queue Project"
            for item in queue_ready["items"]
        )

    def test_dashboard_and_queue_presets_use_visible_ready_counts(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        for index in range(4):
            cli_runner.invoke(
                cli,
                ["project", "create", f"Runtime Repro Project {index + 20}"],
            )
            cli_runner.invoke(
                cli,
                [
                    "task",
                    "add",
                    f"Runtime Repro Project {index + 20}",
                    f"Hidden Ready {index}",
                ],
            )

        dashboard_result = cli_runner.invoke(cli, ["dashboard", "--format", "json"])
        assert dashboard_result.exit_code == 0, dashboard_result.output
        dashboard_payload = json.loads(dashboard_result.output)
        ready_queue = next(
            item
            for item in dashboard_payload["queue_presets"]
            if item["name"] == "ready"
        )
        assert ready_queue["total_count"] == 0
        assert ready_queue["displayed_count"] == 0
        assert dashboard_payload["ready_tasks"] == []

        queue_result = cli_runner.invoke(
            cli, ["queue", "presets", "--format", "json", "--view", "detail"]
        )
        assert queue_result.exit_code == 0, queue_result.output
        queue_payload = json.loads(queue_result.output)
        ready_entry = next(
            item for item in queue_payload["items"] if item["name"] == "ready"
        )
        assert ready_entry["total_count"] == 0
        assert ready_entry["displayed_count"] == 0
        queue_payload = json.loads(queue_result.output)
        ready_queue = next(
            item for item in queue_payload["items"] if item["name"] == "ready"
        )
        assert all(
            item["project_name"] != "Archived Queue Project"
            for item in ready_queue["items"]
        )

    def test_queue_presets_matches_dashboard_visible_counts_beyond_candidate_limit(
        self, cli_runner: CliRunner, temp_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import pms.cli.app as cli_app
        from pms.config.settings import reload_settings

        reload_settings()
        monkeypatch.setattr(cli_app, "_OPERATOR_VIEW_CANDIDATE_LIMIT", 3)

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Visible Queue Project"])
        for index in range(2):
            cli_runner.invoke(
                cli,
                ["task", "add", "Visible Queue Project", f"Visible Ready {index}"],
            )

        for index in range(4):
            cli_runner.invoke(
                cli, ["project", "create", f"Audit Project hidden-{index}"]
            )
            cli_runner.invoke(
                cli,
                [
                    "task",
                    "add",
                    f"Audit Project hidden-{index}",
                    f"Hidden Ready {index}",
                ],
            )

        dashboard_result = cli_runner.invoke(cli, ["dashboard", "--format", "json"])
        assert dashboard_result.exit_code == 0, dashboard_result.output
        dashboard_payload = json.loads(dashboard_result.output)
        dashboard_ready = next(
            item
            for item in dashboard_payload["queue_presets"]
            if item["name"] == "ready"
        )

        queue_result = cli_runner.invoke(
            cli, ["queue", "presets", "--format", "json", "--view", "detail"]
        )
        assert queue_result.exit_code == 0, queue_result.output
        queue_payload = json.loads(queue_result.output)
        queue_ready = next(
            item for item in queue_payload["items"] if item["name"] == "ready"
        )

        assert dashboard_ready["total_count"] == 2
        assert queue_ready["total_count"] == dashboard_ready["total_count"]
        assert queue_ready["displayed_count"] == dashboard_ready["displayed_count"]

    def test_queue_presets_json_named_items_match_dashboard_queue_entries(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Queue Contract Project"])
        ready_result = cli_runner.invoke(
            cli, ["task", "add", "Queue Contract Project", "Queue Ready Task"]
        )
        blocked_result = cli_runner.invoke(
            cli, ["task", "add", "Queue Contract Project", "Queue Blocked Task"]
        )
        blocker_result = cli_runner.invoke(
            cli, ["task", "add", "Queue Contract Project", "Queue Blocker"]
        )

        blocked_id = _extract_id(blocked_result.output)
        blocker_id = _extract_id(blocker_result.output)
        cli_runner.invoke(cli, ["task", "dep", "add", blocked_id, blocker_id])

        cli_runner.invoke(
            cli,
            [
                "task",
                "progress",
                _extract_id(ready_result.output),
                "25",
                "--message",
                "Working",
                "--by",
                "tester",
            ],
        )

        dashboard_result = cli_runner.invoke(cli, ["dashboard", "--format", "json"])
        assert dashboard_result.exit_code == 0, dashboard_result.output
        dashboard_payload = json.loads(dashboard_result.output)
        dashboard_by_name = {
            item["name"]: item for item in dashboard_payload["queue_presets"]
        }

        queue_result = cli_runner.invoke(
            cli, ["queue", "presets", "--format", "json", "--view", "detail"]
        )
        assert queue_result.exit_code == 0, queue_result.output
        queue_payload = json.loads(queue_result.output)
        queue_by_name = {item["name"]: item for item in queue_payload["items"]}

        for preset_name in ("ready", "stale", "blocked", "overdue", "at_risk"):
            assert queue_by_name[preset_name]["population"] == "visible_operator"
            assert (
                queue_by_name[preset_name]["total_count"]
                == dashboard_by_name[preset_name]["total_count"]
            )
            assert (
                queue_by_name[preset_name]["displayed_count"]
                == dashboard_by_name[preset_name]["displayed_count"]
            )


class TestStartGuide:
    """Tests for top-level start guidance command."""

    def test_start_json_suppresses_broken_installed_binary_hint_when_server_is_unreachable(
        self, cli_runner: CliRunner, temp_env: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Start JSON should not advertise a broken Rust fast path."""
        from pms.config.settings import reload_settings

        monkeypatch.chdir(temp_env)
        installed_binary = temp_env / ".bin" / "pms-client"
        installed_binary.parent.mkdir(parents=True, exist_ok=True)
        installed_binary.write_text("#!/bin/sh\n", encoding="utf-8")

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(
            cli,
            [
                "config",
                "set",
                "--write-mode",
                "prefer_server",
                "--server-url",
                "http://127.0.0.1:1",
            ],
        )
        result = cli_runner.invoke(cli, ["start", "--format", "json"])
        assert result.exit_code == 0

        payload = json.loads(result.output)
        assert payload["cli"]["canonical_prefix"] == CLI_ARGV0
        assert payload["cli"]["alternate_prefix"] is None
        assert "fast_path" not in payload

    def test_project_summary_json_suppresses_broken_installed_binary_hint_when_server_is_unreachable(
        self, cli_runner: CliRunner, temp_env: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Project summary JSON should not advertise a broken Rust fast path."""
        from pms.config.settings import reload_settings

        monkeypatch.chdir(temp_env)
        installed_binary = temp_env / ".bin" / "pms-client"
        installed_binary.parent.mkdir(parents=True, exist_ok=True)
        installed_binary.write_text("#!/bin/sh\n", encoding="utf-8")

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Broken Prefix Project"])
        cli_runner.invoke(
            cli,
            [
                "config",
                "set",
                "--write-mode",
                "prefer_server",
                "--server-url",
                "http://127.0.0.1:1",
            ],
        )
        result = cli_runner.invoke(
            cli, ["project", "summary", "Broken Prefix Project", "--format", "json"]
        )
        assert result.exit_code == 0, result.output

        payload = json.loads(result.output)
        assert payload["cli"]["canonical_prefix"] == CLI_ARGV0
        assert payload["cli"]["alternate_prefix"] is None
        assert "fast_path" not in payload

    def test_start_json_payload(self, cli_runner: CliRunner, temp_env: Path):
        """Start command should expose live state + practical next steps."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        result = cli_runner.invoke(cli, ["start", "--format", "json"])
        assert result.exit_code == 0

        payload = json.loads(result.output)
        assert payload["purpose"].startswith("Practical start -> go entry point")
        assert payload["artifacts_created"] == []
        assert "live_state" in payload
        assert payload["runtime"]["coordination"]["state"] == "direct_file_mode"
        assert "observability_paths" in payload
        assert "scenario_paths" in payload
        assert "next_steps" in payload
        assert payload["links"]["guide"] == _cli_step("start --format json")
        assert payload["next_steps"][0] == _cli_step(
            "config set --write-mode prefer_server --server-url http://127.0.0.1:27541"
        )
        assert _cli_step("quickstart --defaults") in payload["next_steps"]
        assert payload["observability_paths"][0]["command"] == _cli_step(
            "dashboard --format json"
        )
        assert payload["observability_paths"][0]["continue_with"] == _cli_step(
            "work daily --scope-type project --scope <name> --format json"
        )

    def test_config_set_help_and_output_name_resolved_env_file(
        self, cli_runner: CliRunner, temp_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from pms.config.settings import reload_settings

        monkeypatch.chdir(temp_env)
        monkeypatch.setenv("PMS_ENV_FILE", str(temp_env / "isolated.env"))
        reload_settings()

        help_result = cli_runner.invoke(cli, ["config", "set", "--help"])
        assert help_result.exit_code == 0, help_result.output
        _assert_plain_output_contains(help_result.output, "resolved env file")

        result = cli_runner.invoke(
            cli,
            ["config", "set", "--server-url", "http://127.0.0.1:9999"],
        )
        assert result.exit_code == 0, result.output
        _assert_plain_output_contains(
            result.output, "Saved config to env file:", str(temp_env / "isolated.env")
        )
        assert not (temp_env / ".env").exists()
        assert "PMS_SERVER_BASE_URL=http://127.0.0.1:9999" in (
            temp_env / "isolated.env"
        ).read_text(encoding="utf-8")

    def test_config_show_surfaces_resolved_env_file(
        self, cli_runner: CliRunner, temp_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from pms.config.settings import reload_settings

        monkeypatch.chdir(temp_env)
        monkeypatch.setenv("PMS_ENV_FILE", str(temp_env / "isolated.env"))
        reload_settings()

        json_result = cli_runner.invoke(cli, ["config", "show", "--format", "json"])
        assert json_result.exit_code == 0, json_result.output
        payload = json.loads(json_result.output)
        assert payload["paths"]["env_file"] == str(
            (temp_env / "isolated.env").resolve()
        )

        text_result = cli_runner.invoke(cli, ["config", "show"])
        assert text_result.exit_code == 0, text_result.output
        assert _extract_prefixed_value(text_result.output, "Env file:") == str(
            (temp_env / "isolated.env").resolve()
        )

    def test_start_json_suppresses_audit_generated_project_focus(
        self, cli_runner: CliRunner, temp_env: Path
    ):
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Audit Project abc123"])
        cli_runner.invoke(
            cli, ["task", "add", "Audit Project abc123", "Audit Ready Task"]
        )
        cli_runner.invoke(cli, ["project", "create", "Operator Project"])
        cli_runner.invoke(
            cli, ["task", "add", "Operator Project", "Operator Ready Task"]
        )

        result = cli_runner.invoke(cli, ["start", "--format", "json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["focus_task"]["title"] == "Operator Ready Task"
        assert payload["live_state"]["suppressed_generated_projects"] == 1

    def test_start_json_prefers_in_progress_focus(
        self, cli_runner: CliRunner, temp_env: Path
    ):
        """Start guide should focus active execution before ready backlog."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(
            cli,
            [
                "config",
                "set",
                "--write-mode",
                "prefer_server",
                "--server-url",
                "http://127.0.0.1:1",
            ],
        )
        cli_runner.invoke(cli, ["project", "create", "Start Focus Project"])
        cli_runner.invoke(
            cli, ["task", "add", "Start Focus Project", "Ready Start Task"]
        )
        cli_runner.invoke(
            cli,
            ["task", "add", "Start Focus Project", "Active Start Task"],
        )
        cli_runner.invoke(
            cli,
            ["task", "start", "Active Start Task", "--project", "Start Focus Project"],
        )

        result = cli_runner.invoke(cli, ["start", "--format", "json"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["focus_task"]["title"] == "Active Start Task"
        assert payload["focus_task"]["status"] == "in_progress"
        assert payload["next_steps"][0] == _cli_step(
            "runtime prefer-server --host 127.0.0.1 --port 27541"
        )
        assert any(
            step.startswith(_cli_step("task progress"))
            for step in payload["next_steps"]
        )
        assert payload["links"]["daily_focus"] == _cli_step(
            'work daily --scope-type project --scope "Start Focus Project" --format json'
        )

    def test_work_daily_json_includes_purpose_and_focus(
        self, cli_runner: CliRunner, temp_env: Path
    ):
        """Work daily should explain purpose and current focus in JSON output."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Daily Focus Project"])
        cli_runner.invoke(
            cli, ["task", "add", "Daily Focus Project", "Ready Daily Task"]
        )

        result = cli_runner.invoke(
            cli,
            [
                "work",
                "daily",
                "--scope-type",
                "project",
                "--scope",
                "Daily Focus Project",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["purpose"].startswith("Scoped daily operator digest")
        assert payload["focus_task"]["title"] == "Ready Daily Task"
        assert payload["focus_task"]["reason"] == "next ready work to start"
        assert payload["artifacts_created"] == []

    def test_work_daily_json_prefers_in_progress_focus(
        self, cli_runner: CliRunner, temp_env: Path
    ):
        """Work daily should keep the operator on active execution before ready work."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Daily Active Project"])
        cli_runner.invoke(
            cli, ["task", "add", "Daily Active Project", "Ready Daily Task"]
        )
        cli_runner.invoke(
            cli,
            ["task", "add", "Daily Active Project", "Active Daily Task"],
        )
        cli_runner.invoke(
            cli,
            ["task", "start", "Active Daily Task", "--project", "Daily Active Project"],
        )

        result = cli_runner.invoke(
            cli,
            [
                "work",
                "daily",
                "--scope-type",
                "project",
                "--scope",
                "Daily Active Project",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["focus_task"]["title"] == "Active Daily Task"
        assert payload["focus_task"]["status"] == "in_progress"
        assert payload["next_steps"][0].startswith(_cli_step("task progress"))

    def test_start_text_output(self, cli_runner: CliRunner, temp_env: Path):
        """Text output should include discoverability sections."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        result = cli_runner.invoke(cli, ["start"])
        assert result.exit_code == 0
        _assert_plain_output_contains(
            result.output,
            "Start -> Go Guide",
            "Purpose: practical start -> go entry point",
            "Creates: no new state;",
            "Observability Paths",
            "Real-World Scenario Entry Points",
        )


class TestOrgPortfolioProgramDashboards:
    """Tests for org/portfolio/program dashboard CLI outputs."""

    def test_org_portfolio_program_dashboards(
        self, cli_runner: CliRunner, temp_env: Path
    ):
        """Ensure dashboards include objectives rollups."""
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        org_result = cli_runner.invoke(cli, ["org", "create", "Dash Org"])
        org_id = _extract_id(org_result.output)

        portfolio_result = cli_runner.invoke(
            cli, ["portfolio", "create", "Dash Portfolio", "--org-id", org_id]
        )
        portfolio_id = _extract_id(portfolio_result.output)

        cli_runner.invoke(
            cli,
            [
                "program",
                "create",
                "Dash Program",
                "--org-id",
                org_id,
                "--portfolio-id",
                portfolio_id,
            ],
        )

        org_dash = cli_runner.invoke(cli, ["org", "dashboard"])
        assert org_dash.exit_code == 0
        assert "Organization Dashboard" in org_dash.output
        assert "Objectives" in org_dash.output

        portfolio_dash = cli_runner.invoke(
            cli, ["portfolio", "dashboard", "--org-id", org_id]
        )
        assert portfolio_dash.exit_code == 0
        assert "Portfolio Dashboard" in portfolio_dash.output
        assert "Objectives" in portfolio_dash.output

        program_dash = cli_runner.invoke(
            cli,
            [
                "program",
                "dashboard",
                "--org-id",
                org_id,
                "--portfolio-id",
                portfolio_id,
            ],
        )
        assert program_dash.exit_code == 0
        assert "Program Dashboard" in program_dash.output
        assert "Objectives" in program_dash.output

    def test_scope_dashboards_bubble_freshest_nested_project_timestamps(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()

        cli_runner.invoke(cli, ["init"])
        org_payload = json.loads(
            cli_runner.invoke(
                cli, ["org", "create", "Bubble Org", "--format", "json"]
            ).output
        )
        org_id = org_payload["organization"]["id"]

        portfolio_payload = json.loads(
            cli_runner.invoke(
                cli,
                [
                    "portfolio",
                    "create",
                    "Bubble Portfolio",
                    "--org-id",
                    org_id,
                    "--format",
                    "json",
                ],
            ).output
        )
        portfolio_id = portfolio_payload["portfolio"]["id"]

        program_payload = json.loads(
            cli_runner.invoke(
                cli,
                [
                    "program",
                    "create",
                    "Bubble Program",
                    "--org-id",
                    org_id,
                    "--portfolio-id",
                    portfolio_id,
                    "--format",
                    "json",
                ],
            ).output
        )
        program_id = program_payload["program"]["id"]

        cli_runner.invoke(
            cli,
            [
                "project",
                "create",
                "Bubble Older Project",
                "--org",
                org_id,
                "--portfolio",
                portfolio_id,
                "--program",
                program_id,
            ],
        )
        goal_project_id = json.loads(
            cli_runner.invoke(
                cli,
                [
                    "project",
                    "create",
                    "Bubble Goal Project",
                    "--org",
                    org_id,
                    "--portfolio",
                    portfolio_id,
                    "--program",
                    program_id,
                    "--format",
                    "json",
                ],
            ).output
        )["project"]["id"]
        goal_id = json.loads(
            cli_runner.invoke(
                cli,
                [
                    "goal",
                    "create",
                    "Bubble Goal",
                    "--project-id",
                    goal_project_id,
                    "--format",
                    "json",
                ],
            ).output
        )["goal"]["id"]
        objective_id = json.loads(
            cli_runner.invoke(
                cli,
                [
                    "objective",
                    "create",
                    "Bubble Objective",
                    "--goal-id",
                    goal_id,
                    "--format",
                    "json",
                ],
            ).output
        )["objective"]["id"]
        cli_runner.invoke(
            cli,
            [
                "objective",
                "update",
                objective_id,
                "--status",
                "on_hold",
                "--progress",
                "30",
                "--format",
                "json",
            ],
        )

        cli_runner.invoke(
            cli,
            [
                "project",
                "create",
                "Bubble Freshest Project",
                "--org",
                org_id,
                "--portfolio",
                portfolio_id,
                "--program",
                program_id,
            ],
        )
        freshest_task_id = json.loads(
            cli_runner.invoke(
                cli,
                [
                    "task",
                    "add",
                    "Bubble Freshest Project",
                    "Bubble Freshest Task",
                    "--format",
                    "json",
                ],
            ).output
        )["task"]["id"]
        cli_runner.invoke(
            cli,
            ["task", "start", freshest_task_id, "--by", "tester", "--format", "json"],
        )
        cli_runner.invoke(
            cli,
            [
                "task",
                "progress",
                freshest_task_id,
                "75",
                "Bubble freshest activity",
                "--by",
                "tester",
                "--format",
                "json",
            ],
        )

        project_list = json.loads(
            cli_runner.invoke(cli, ["project", "list", "--format", "json"]).output
        )
        freshest_project = next(
            item
            for item in project_list["items"]
            if item["name"] == "Bubble Freshest Project"
        )

        org_dash = json.loads(
            cli_runner.invoke(cli, ["org", "dashboard", "--format", "json"]).output
        )
        portfolio_dash = json.loads(
            cli_runner.invoke(
                cli,
                [
                    "portfolio",
                    "dashboard",
                    "--org-id",
                    org_id,
                    "--format",
                    "json",
                ],
            ).output
        )
        program_dash = json.loads(
            cli_runner.invoke(
                cli,
                [
                    "program",
                    "dashboard",
                    "--org-id",
                    org_id,
                    "--portfolio-id",
                    portfolio_id,
                    "--format",
                    "json",
                ],
            ).output
        )

        assert (
            org_dash["items"][0]["last_activity_at"]
            == freshest_project["last_activity_at"]
        )
        assert (
            org_dash["items"][0]["last_transition_at"]
            == freshest_project["last_transition_at"]
        )
        assert (
            portfolio_dash["items"][0]["last_activity_at"]
            == freshest_project["last_activity_at"]
        )
        assert (
            portfolio_dash["items"][0]["last_transition_at"]
            == freshest_project["last_transition_at"]
        )
        assert (
            program_dash["items"][0]["last_activity_at"]
            == freshest_project["last_activity_at"]
        )
        assert (
            program_dash["items"][0]["last_transition_at"]
            == freshest_project["last_transition_at"]
        )


class TestCapabilitiesFormats:
    """Tests for capabilities format outputs."""

    def test_capabilities_list_json_is_machine_parseable(self, cli_runner: CliRunner):
        """Capabilities list JSON should be emitted as raw machine-parseable JSON."""
        result = cli_runner.invoke(cli, ["capabilities", "list", "--format", "json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert "items" in payload
        assert "page" in payload
        assert "links" in payload

    def test_capabilities_list_csv(self, cli_runner: CliRunner):
        """Test capabilities list CSV output."""
        result = cli_runner.invoke(cli, ["capabilities", "list", "--format", "csv"])
        assert result.exit_code == 0
        assert "category,name,value" in result.output.splitlines()[0]

    def test_capabilities_health_csv(self, cli_runner: CliRunner):
        """Test capabilities health CSV output."""
        result = cli_runner.invoke(cli, ["capabilities", "health", "--format", "csv"])
        assert result.exit_code == 0
        assert "key,value" in result.output.splitlines()[0]


class TestNamespacePluginFormats:
    """Tests for namespace and plugin format outputs."""

    def test_namespace_list_json_is_machine_parseable(self, cli_runner: CliRunner):
        """Namespace list JSON should be emitted as raw machine-parseable JSON."""
        result = cli_runner.invoke(cli, ["namespace", "list", "--format", "json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert "items" in payload
        assert "page" in payload
        assert "links" in payload
        project_item = next(
            item for item in payload["items"] if item["prefix"] == "proj"
        )
        assert project_item["namespace_generated_id_format"] == "proj_<uuid>"
        assert project_item["namespace_generated_id_kind"] == "prefix_uuid"
        assert (
            project_item["runtime_row_id_contract_scope"]
            == "public_stored_entity_family"
        )
        assert project_item["runtime_row_id_style"] == "uuid_native"

    def test_namespace_list_csv(self, cli_runner: CliRunner):
        """Test namespace list CSV output."""
        result = cli_runner.invoke(cli, ["namespace", "list", "--format", "csv"])
        assert result.exit_code == 0
        header = result.output.splitlines()[0]
        row = result.output.splitlines()[1]
        assert "namespace_generated_id_format" in header
        assert "runtime_row_id_contract_scope" in header
        assert "runtime_row_id_style" in header
        assert "apikey_<uuid>" in row
        assert "public_stored_entity_family" in row

    def test_namespace_show_json(self, cli_runner: CliRunner):
        """Test namespace show JSON output."""
        result = cli_runner.invoke(
            cli, ["namespace", "show", "task", "--format", "json"]
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["namespace_generated_id_format"] == "task_<uuid>"
        assert payload["namespace_generated_id_kind"] == "prefix_uuid"
        assert payload["runtime_row_id_contract_scope"] == "public_stored_entity_family"
        assert payload["runtime_row_id_style"] == "uuid_native"

    def test_namespace_show_csv(self, cli_runner: CliRunner):
        """Test namespace show CSV output."""
        result = cli_runner.invoke(
            cli, ["namespace", "show", "task", "--format", "csv"]
        )
        assert result.exit_code == 0
        header = result.output.splitlines()[0]
        row = result.output.splitlines()[1]
        assert "namespace_generated_id_format" in header
        assert "runtime_row_id_contract_scope" in header
        assert "runtime_row_id_style" in header
        assert "task_<uuid>" in row
        assert "public_stored_entity_family" in row
        assert "uuid_native" in row

    def test_plugin_list_csv(self, cli_runner: CliRunner):
        """Test plugin list CSV output."""
        result = cli_runner.invoke(cli, ["plugin", "list", "--format", "csv"])
        assert result.exit_code == 0
        assert "name,version,state" in result.output.splitlines()[0]

    def test_plugin_tools_csv(self, cli_runner: CliRunner):
        """Test plugin tools CSV output."""
        result = cli_runner.invoke(cli, ["plugin", "tools", "--format", "csv"])
        assert result.exit_code == 0
        assert "tool,plugin,description" in result.output.splitlines()[0]

    def test_plugin_tools_json_wrapper(self, cli_runner: CliRunner):
        """Test plugin tools JSON wrapper output."""
        result = cli_runner.invoke(cli, ["plugin", "tools", "--format", "json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert "items" in payload
        assert "page" in payload
        assert "links" in payload
        if payload["items"]:
            assert "full_name" in payload["items"][0]

    def test_plugin_stats_csv(self, cli_runner: CliRunner):
        """Test plugin stats CSV output."""
        result = cli_runner.invoke(cli, ["plugin", "stats", "--format", "csv"])
        assert result.exit_code == 0
        assert "key,value" in result.output.splitlines()[0]

    def test_plugin_stats_json_wrapper(self, cli_runner: CliRunner):
        """Test plugin stats JSON output."""
        result = cli_runner.invoke(cli, ["plugin", "stats", "--format", "json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert "total_plugins" in payload
        assert "total_tools" in payload
        assert "total_hooks" in payload
        assert "links" in payload


class TestCapabilitiesInfoFormats:
    """Tests for capabilities info format outputs."""

    def test_capabilities_info_csv(self, cli_runner: CliRunner):
        """Test capabilities info CSV output."""
        result = cli_runner.invoke(cli, ["capabilities", "info", "--format", "csv"])
        assert result.exit_code == 0
        assert "key,value" in result.output.splitlines()[0]

    def test_capabilities_info_json_includes_links_and_next_steps(
        self, cli_runner: CliRunner
    ):
        """Capabilities info JSON should guide follow-up exploration."""
        result = cli_runner.invoke(cli, ["capabilities", "info", "--format", "json"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["purpose"].startswith("Capability inventory entry point")
        assert payload["links"]["list"] == _cli_step("capabilities list --format json")
        assert payload["next_steps"][0] == _cli_step("capabilities list --format json")

    def test_aws_server_help(self, cli_runner: CliRunner):
        """Test AWS server subgroup help."""
        result = cli_runner.invoke(cli, ["aws", "server", "--help"])

        assert result.exit_code == 0
        _assert_plain_output_contains(
            result.output, "launch", "list", "show", "terminate", "terminate-all"
        )

    def test_aws_server_launch_help(self, cli_runner: CliRunner):
        """Test AWS server launch command help."""
        result = cli_runner.invoke(cli, ["aws", "server", "launch", "--help"])

        assert result.exit_code == 0
        _assert_plain_output_contains(
            result.output,
            "NAME",
            "--type",
            "--region",
            "--max-hours",
            "--idle-minutes",
            "--docker",
        )

    def test_aws_server_list_help(self, cli_runner: CliRunner):
        """Test AWS server list command help."""
        result = cli_runner.invoke(cli, ["aws", "server", "list", "--help"])

        assert result.exit_code == 0
        _assert_plain_output_contains(result.output, "--all", "--project", "--format")

    def test_aws_server_terminate_help(self, cli_runner: CliRunner):
        """Test AWS server terminate command help."""
        result = cli_runner.invoke(cli, ["aws", "server", "terminate", "--help"])

        assert result.exit_code == 0
        _assert_plain_output_contains(result.output, "NAME_OR_ID", "--yes")

    def test_aws_test_help(self, cli_runner: CliRunner):
        """Test AWS test subgroup help."""
        result = cli_runner.invoke(cli, ["aws", "test", "--help"])

        assert result.exit_code == 0
        _assert_plain_output_contains(result.output, "run", "sync", "exec")

    def test_aws_test_run_help(self, cli_runner: CliRunner):
        """Test AWS test run command help."""
        result = cli_runner.invoke(cli, ["aws", "test", "run", "--help"])

        assert result.exit_code == 0
        _assert_plain_output_contains(
            result.output,
            "SERVER_NAME",
            "PROJECT_PATH",
            "--command",
            "--setup",
            "--remote-path",
            "--timeout",
        )

    def test_aws_test_sync_help(self, cli_runner: CliRunner):
        """Test AWS test sync command help."""
        result = cli_runner.invoke(cli, ["aws", "test", "sync", "--help"])

        assert result.exit_code == 0
        _assert_plain_output_contains(
            result.output, "SERVER_NAME", "PROJECT_PATH", "--remote-path"
        )

    def test_aws_test_exec_help(self, cli_runner: CliRunner):
        """Test AWS test exec command help."""
        result = cli_runner.invoke(cli, ["aws", "test", "exec", "--help"])

        assert result.exit_code == 0
        _assert_plain_output_contains(
            result.output, "SERVER_NAME", "COMMAND", "--workdir", "--timeout"
        )

    def test_aws_logs_help(self, cli_runner: CliRunner):
        """Test AWS logs command help."""
        result = cli_runner.invoke(cli, ["aws", "logs", "--help"])

        assert result.exit_code == 0
        _assert_plain_output_contains(
            result.output, "SERVER_NAME", "LOG_PATHS", "--lines", "--follow"
        )


class TestLegacyValidationCleanup:
    """Focused regressions for remaining fail-loud cleanup surfaces."""

    def test_queue_show_missing_queue_fails_nonzero_in_json_mode(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(
            cli, ["queue", "show", "missing-queue", "--format", "json"]
        )

        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert payload["error"] == "Saved queue not found"

    def test_task_proof_bundle_search_invalid_timestamp_is_machine_readable(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(
            cli,
            [
                "task",
                "proof-bundle-search",
                "--created-from",
                "not-a-timestamp",
                "--format",
                "json",
            ],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert payload["error"] == "created-from must be ISO timestamp"

    def test_revision_diff_invalid_revision_is_machine_readable_in_json_mode(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(
            cli,
            [
                "revision",
                "diff",
                "project",
                "missing-project",
                "--from",
                "0",
                "--to",
                "1",
                "--format",
                "json",
            ],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert payload["error"] == "Revision numbers must be >= 1"

    def test_revision_diff_missing_revisions_is_machine_readable_in_json_mode(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(
            cli,
            [
                "revision",
                "diff",
                "project",
                "missing-project",
                "--from",
                "1",
                "--to",
                "2",
                "--format",
                "json",
            ],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert payload["error"] == "Revisions not found"

    def test_task_tree_root_mismatch_fails_nonzero_in_json_mode(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Tree Project"])
        cli_runner.invoke(cli, ["project", "create", "Other Project"])
        task_result = cli_runner.invoke(
            cli, ["task", "add", "Other Project", "Other Task"]
        )
        task_id = _extract_id(task_result.output)

        result = cli_runner.invoke(
            cli,
            [
                "task",
                "tree",
                "--project",
                "Tree Project",
                "--root-task-id",
                task_id,
                "--format",
                "json",
            ],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert payload["error"] == "Root task not found in the specified project"

    def test_task_dependency_remove_missing_fails_nonzero(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(
            cli, ["task", "dep", "remove", "missing-task", "missing-dependency"]
        )

        assert result.exit_code != 0
        _assert_plain_output_contains(result.output, "Dependency not found")

    def test_comment_add_invalid_metadata_json_fails_nonzero(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Comment Project"])
        task_result = cli_runner.invoke(
            cli, ["task", "add", "Comment Project", "Comment Task"]
        )
        task_id = _extract_id(task_result.output)

        result = cli_runner.invoke(
            cli,
            [
                "comment",
                "add",
                "task",
                task_id,
                "hello",
                "--by",
                "tester",
                "--metadata-json",
                "{not-json}",
            ],
        )

        assert result.exit_code != 0
        _assert_plain_output_contains(result.output, "Invalid JSON in --metadata-json")

    def test_automation_rule_create_invalid_payload_json_fails_nonzero(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(
            cli,
            [
                "automation",
                "rule",
                "create",
                "bad-rule",
                "task.updated",
                "log",
                "--action-payload-json",
                "{not-json}",
            ],
        )

        assert result.exit_code != 0
        _assert_plain_output_contains(
            result.output, "Invalid JSON in --action-payload-json"
        )

    def test_label_create_conflicting_category_selectors_fail_nonzero(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(
            cli,
            [
                "label",
                "create",
                "bad-label",
                "--category",
                "category-a",
                "--category-id",
                "cat_123",
            ],
        )
        assert result.exit_code != 0
        _assert_plain_output_contains(
            result.output, "Use --category or --category-id, not both"
        )

    def test_remote_show_missing_host_fails_nonzero_in_json_mode(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(
            cli,
            ["remote", "show", "missing-remote", "--format", "json"],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert payload["error"] == "Remote host 'missing-remote' not found"

    def test_plugin_validate_fails_nonzero_when_errors_exist(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        empty_dir = temp_env / "invalid-plugin"
        empty_dir.mkdir()

        result = cli_runner.invoke(cli, ["plugin", "validate", str(empty_dir)])

        assert result.exit_code != 0
        _assert_plain_output_contains(
            result.output, "Plugin has errors", "No plugin.json or .tools files found"
        )

    def test_generate_tool_generation_failure_fails_nonzero(
        self,
        cli_runner: CliRunner,
        temp_env: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from pms.agents.tool_generator import (
            GeneratedTool,
            GenerationStatus,
            ToolGenerator,
        )
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        async def fake_analyze(self, description: str):
            from pms.agents.tool_generator import ToolSpec
            from pms.tools.registry import ToolCategory

            return ToolSpec(
                name="broken_tool",
                description=description,
                category=ToolCategory.TASK,
                parameters={},
                search_keywords=["broken"],
                service_dependency=None,
                is_core=False,
            )

        async def fake_generate(self, spec):
            return GeneratedTool(
                spec=spec,
                tool_code="",
                test_code="",
                registry_entry="",
                status=GenerationStatus.FAILED,
                errors=["synthetic generator failure"],
            )

        monkeypatch.setattr(ToolGenerator, "analyze_description", fake_analyze)
        monkeypatch.setattr(ToolGenerator, "generate_tool", fake_generate)

        result = cli_runner.invoke(cli, ["generate", "tool", "broken tool"])

        assert result.exit_code != 0
        _assert_plain_output_contains(
            result.output, "Generation failed: synthetic generator failure"
        )

    def test_task_evidence_add_invalid_metadata_fails_nonzero(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Evidence Meta Project"])
        task_result = cli_runner.invoke(
            cli, ["task", "add", "Evidence Meta Project", "Evidence Meta Task"]
        )
        task_id = _extract_id(task_result.output)

        result = cli_runner.invoke(
            cli,
            [
                "task",
                "evidence",
                "add",
                task_id,
                "scm_commit",
                "abc123",
                "--metadata",
                "{not-json}",
            ],
        )
        assert result.exit_code != 0
        _assert_plain_output_contains(result.output, "Metadata must be valid JSON")

    def test_task_dep_add_fails_nonzero_when_dependency_not_created(
        self,
        cli_runner: CliRunner,
        temp_env: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from pms.config.settings import reload_settings
        from pms.services.task_service import TaskService

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        async def fake_add_dependency(
            self, task_id: str, depends_on_id: str, dependency_type
        ):
            return None

        monkeypatch.setattr(TaskService, "add_dependency", fake_add_dependency)

        result = cli_runner.invoke(cli, ["task", "dep", "add", "task-a", "task-b"])

        assert result.exit_code != 0
        _assert_plain_output_contains(result.output, "Dependency not created")

    def test_project_complete_fails_nonzero_when_update_returns_none(
        self,
        cli_runner: CliRunner,
        temp_env: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from types import SimpleNamespace

        from pms.config.settings import reload_settings
        from pms.repositories.project_repository import ProjectRepository
        from pms.services.project_service import ProjectService

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        async def fake_get_by_name(self, name: str):
            return SimpleNamespace(id="proj_test", name=name)

        async def fake_update_project(self, project_id: str, **kwargs):
            return None

        monkeypatch.setattr(ProjectRepository, "get_by_name", fake_get_by_name)
        monkeypatch.setattr(ProjectService, "update_project", fake_update_project)

        result = cli_runner.invoke(cli, ["project", "complete", "Test Project"])

        assert result.exit_code != 0
        _assert_plain_output_contains(result.output, "Update failed")

    def test_goal_create_fails_nonzero_when_server_reload_returns_none(
        self,
        cli_runner: CliRunner,
        temp_env: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import pms.cli.app as cli_app
        from pms.config.settings import reload_settings
        from pms.services.goal_service import GoalService

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        async def fake_delegate_goal_create_to_server(**kwargs):
            return {"id": "goal_test"}

        async def fake_get_goal(self, goal_id: str):
            return None

        monkeypatch.setattr(
            cli_app,
            "_ensure_runtime_write_mode",
            lambda *args, **kwargs: cli_app.RuntimeWriteDecision(
                allowed=True,
                use_server=True,
                payload=cli_app._runtime_server_payload(),
                block_reason=None,
            ),
        )

        monkeypatch.setattr(
            cli_app,
            "_delegate_goal_create_to_server",
            fake_delegate_goal_create_to_server,
        )
        monkeypatch.setattr(GoalService, "get_goal", fake_get_goal)

        result = cli_runner.invoke(
            cli,
            ["goal", "create", "Broken Goal", "--format", "json"],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert (
            payload["error"] == "Created goal on server but failed to reload it locally"
        )

    def test_workflow_align_without_current_state_fails_nonzero(
        self,
        cli_runner: CliRunner,
        temp_env: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from types import SimpleNamespace

        import pms.cli.app as cli_app
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        entity = SimpleNamespace(status="done", current_state=None)
        workflow = SimpleNamespace(terminal_states={"done"})

        async def fake_load_workflow_entity(**kwargs):
            return entity, object(), workflow, "event", "Task", None

        monkeypatch.setattr(cli_app, "_load_workflow_entity", fake_load_workflow_entity)
        monkeypatch.setattr(
            cli_app, "_status_is_terminal", lambda entity_type, status: True
        )

        result = cli_runner.invoke(
            cli,
            ["workflow", "align", "task_123", "--by", "tester"],
        )

        assert result.exit_code != 0
        _assert_plain_output_contains(
            result.output, "Workflow has no current state assigned"
        )

    def test_auth_list_requires_admin_key_nonzero_in_json_mode(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(cli, ["auth", "list", "--format", "json"])

        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert "Admin API key required" in payload["error"]

    def test_auth_get_invalid_admin_key_fails_nonzero_in_json_mode(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(
            cli,
            [
                "auth",
                "get",
                "missing-key",
                "--api-key",
                "bad-key",
                "--format",
                "json",
            ],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert payload["error"] == "Error: Invalid or unauthorized API key."

    def test_auth_create_requires_admin_key_nonzero_in_json_mode(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(
            cli,
            [
                "auth",
                "create",
                "--name",
                "Reader",
                "--scope",
                "tasks:read",
                "--format",
                "json",
            ],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert "Admin API key required" in payload["error"]

    def test_auth_deactivate_invalid_admin_key_fails_nonzero_in_json_mode(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(
            cli,
            [
                "auth",
                "deactivate",
                "missing-key",
                "--api-key",
                "bad-key",
                "--format",
                "json",
            ],
        )

        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert payload["error"] == "Error: Invalid or unauthorized API key."

    def test_auth_mutations_emit_machine_readable_json(
        self, cli_runner: CliRunner, temp_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from pms.config.settings import reload_settings

        monkeypatch.chdir(temp_env)
        reload_settings()

        cli_runner.invoke(cli, ["init"])
        init = cli_runner.invoke(cli, ["auth", "init", "--show-key"])
        admin_key = _extract_api_key(init.output)

        create = cli_runner.invoke(
            cli,
            [
                "auth",
                "create",
                "--name",
                "Machine Reader",
                "--scope",
                "tasks:read",
                "--api-key",
                admin_key,
                "--format",
                "json",
            ],
        )
        assert create.exit_code == 0, create.output
        create_payload = json.loads(create.output)
        created_id = create_payload["id"]
        assert create_payload["name"] == "Machine Reader"
        assert create_payload["plain_key"].startswith("pms_")

        deactivate = cli_runner.invoke(
            cli,
            [
                "auth",
                "deactivate",
                created_id,
                "--api-key",
                admin_key,
                "--format",
                "json",
            ],
        )
        assert deactivate.exit_code == 0, deactivate.output
        deactivate_payload = json.loads(deactivate.output)
        assert deactivate_payload["action"] == "deactivated"
        assert deactivate_payload["status"] == "inactive"

        restore = cli_runner.invoke(
            cli,
            [
                "auth",
                "restore",
                created_id,
                "--api-key",
                admin_key,
                "--format",
                "json",
            ],
        )
        assert restore.exit_code == 0, restore.output
        restore_payload = json.loads(restore.output)
        assert restore_payload["action"] == "restored"
        assert restore_payload["status"] == "active"

        revoke = cli_runner.invoke(
            cli,
            [
                "auth",
                "revoke",
                created_id,
                "--api-key",
                admin_key,
                "--yes",
                "--format",
                "json",
            ],
        )
        assert revoke.exit_code == 0, revoke.output
        revoke_payload = json.loads(revoke.output)
        assert revoke_payload["action"] == "revoked"
        assert revoke_payload["id"] == created_id

    def test_aws_logs_requires_log_paths_nonzero(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(cli, ["aws", "logs", "example-server"])

        assert result.exit_code != 0
        _assert_plain_output_contains(
            result.output, "Please specify at least one log path"
        )

    def test_generate_module_requires_tool_descriptions_nonzero(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        result = cli_runner.invoke(cli, ["generate", "module", "example-module"])

        assert result.exit_code != 0
        _assert_plain_output_contains(
            result.output, "Please provide at least one tool description"
        )

    def test_plugin_test_requires_manifest_nonzero(
        self, cli_runner: CliRunner, temp_env: Path
    ) -> None:
        from pms.config.settings import reload_settings

        reload_settings()
        cli_runner.invoke(cli, ["init"])

        empty_dir = temp_env / "empty-plugin"
        empty_dir.mkdir()

        result = cli_runner.invoke(cli, ["plugin", "test", str(empty_dir)])

        assert result.exit_code != 0
        _assert_plain_output_contains(result.output, "No plugin.json found")


class TestCliObservationalMetricsResilience:
    """CLI result/reporting commands should ignore late telemetry storage failures."""

    def test_work_daily_succeeds_when_cli_metrics_flush_fails(
        self,
        cli_runner: CliRunner,
        temp_env: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from pms.config.settings import reload_settings
        from pms.core.metrics import MetricsCollector

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        cli_runner.invoke(cli, ["project", "create", "Daily Metrics Project"])

        async def fail_flush(self) -> int:
            raise RuntimeError("metrics flush failed")

        monkeypatch.setattr(MetricsCollector, "flush", fail_flush)

        result = cli_runner.invoke(
            cli,
            [
                "work",
                "daily",
                "--scope-type",
                "project",
                "--scope",
                "Daily Metrics Project",
            ],
        )

        assert result.exit_code == 0, result.output
        _assert_plain_output_contains(result.output, "Daily Review (project)")

    def test_report_project_succeeds_when_cli_metrics_flush_fails(
        self,
        cli_runner: CliRunner,
        temp_env: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from pms.config.settings import reload_settings
        from pms.core.metrics import MetricsCollector

        reload_settings()
        cli_runner.invoke(cli, ["init"])
        create_result = cli_runner.invoke(
            cli, ["project", "create", "Report Metrics Project"]
        )
        project_id = _extract_id(create_result.output)
        output_path = temp_env / "project-report.md"

        async def fail_flush(self) -> int:
            raise RuntimeError("metrics flush failed")

        monkeypatch.setattr(MetricsCollector, "flush", fail_flush)

        result = cli_runner.invoke(
            cli,
            [
                "report",
                "project",
                project_id,
                "--output",
                str(output_path),
            ],
        )

        assert result.exit_code == 0, result.output
        assert output_path.exists()
        assert output_path.read_text(encoding="utf-8").strip()
