"""Database schema bootstrap for a fresh PMS install."""

from __future__ import annotations

from pathlib import Path

from pms.db.connection import Database
from pms.exceptions.base import DatabaseError
from pms.models.base import now_utc

SCHEMA_VERSION = 1
SCHEMA_NAME = "stable"


def _schema_path() -> Path:
    return Path(__file__).with_name("schema.sql")


def _strip_sql_comments(raw: str) -> str:
    """Remove SQL line comments while preserving executable SQL."""
    cleaned_lines: list[str] = []
    for line in raw.splitlines():
        if "--" in line:
            prefix, _comment = line.split("--", 1)
            if prefix.strip():
                cleaned_lines.append(prefix.rstrip())
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


def load_schema_statements() -> list[str]:
    """Load schema SQL statements from the bundled schema file."""
    raw = _schema_path().read_text()
    raw = _strip_sql_comments(raw)
    statements = [stmt.strip() for stmt in raw.split(";") if stmt.strip()]
    return [stmt + ";" for stmt in statements]


def _is_schema_duplicate_error(exc: DatabaseError) -> bool:
    message = str(exc).lower()
    return "already exists" in message or "duplicate" in message


async def initialize_schema(db: Database) -> None:
    """Create the full schema for a first-release database."""
    for statement in load_schema_statements():
        try:
            await db.execute(statement)
        except DatabaseError as exc:
            if _is_schema_duplicate_error(exc):
                continue
            raise

    await _backfill_native_relationship_edges(db)

    existing = await db.fetch_one(
        "SELECT version FROM schema_info WHERE version = ?",
        (SCHEMA_VERSION,),
    )
    if existing:
        return

    try:
        await db.execute(
            """
            INSERT INTO schema_info (version, name, created_at)
            VALUES (?, ?, ?)
            """,
            (SCHEMA_VERSION, SCHEMA_NAME, now_utc().isoformat()),
        )
    except DatabaseError as exc:
        if _is_schema_duplicate_error(exc):
            return
        raise


async def _table_columns(db: Database, table_name: str) -> set[str]:
    rows = await db.fetch_all(f"PRAGMA table_info({table_name})")
    return {str(row["name"]) for row in rows}


async def _backfill_json_edge_table(
    db: Database,
    *,
    source_table: str,
    source_id_column: str,
    source_json_column: str,
    target_table: str,
    target_parent_column: str,
    target_child_column: str,
    referenced_table: str,
    referenced_id_column: str = "id",
) -> None:
    source_columns = await _table_columns(db, source_table)
    if source_json_column not in source_columns:
        return

    await db.execute(
        f"""
        INSERT OR IGNORE INTO {target_table} ({target_parent_column}, {target_child_column}, position)
        SELECT
            src.{source_id_column},
            rel.value,
            CAST(rel.key AS INTEGER)
        FROM {source_table} src
        JOIN json_each(src.{source_json_column}) rel
        JOIN {referenced_table} ref
          ON ref.{referenced_id_column} = rel.value
        WHERE src.{source_json_column} IS NOT NULL
          AND json_valid(src.{source_json_column})
          AND rel.value IS NOT NULL
          AND rel.value != ''
        """
    )


async def _backfill_native_relationship_edges(db: Database) -> None:
    """Populate native edge tables from prior JSON-array projection columns when present."""
    await _backfill_json_edge_table(
        db,
        source_table="organizations",
        source_id_column="id",
        source_json_column="member_ids",
        target_table="organization_members",
        target_parent_column="organization_id",
        target_child_column="actor_id",
        referenced_table="actors",
    )
    await _backfill_json_edge_table(
        db,
        source_table="teams",
        source_id_column="id",
        source_json_column="member_ids",
        target_table="team_members",
        target_parent_column="team_id",
        target_child_column="actor_id",
        referenced_table="actors",
    )
    await _backfill_json_edge_table(
        db,
        source_table="plans",
        source_id_column="id",
        source_json_column="task_ids",
        target_table="plan_tasks",
        target_parent_column="plan_id",
        target_child_column="task_id",
        referenced_table="tasks",
    )
    await _backfill_json_edge_table(
        db,
        source_table="plan_test_jobs",
        source_id_column="id",
        source_json_column="task_ids",
        target_table="plan_test_job_tasks",
        target_parent_column="plan_test_job_id",
        target_child_column="task_id",
        referenced_table="tasks",
    )
    await _backfill_json_edge_table(
        db,
        source_table="portfolios",
        source_id_column="id",
        source_json_column="goal_ids",
        target_table="portfolio_goals",
        target_parent_column="portfolio_id",
        target_child_column="goal_id",
        referenced_table="goals",
    )
    await _backfill_json_edge_table(
        db,
        source_table="portfolios",
        source_id_column="id",
        source_json_column="objective_ids",
        target_table="portfolio_objectives",
        target_parent_column="portfolio_id",
        target_child_column="objective_id",
        referenced_table="objectives",
    )
    await _backfill_json_edge_table(
        db,
        source_table="programs",
        source_id_column="id",
        source_json_column="goal_ids",
        target_table="program_goals",
        target_parent_column="program_id",
        target_child_column="goal_id",
        referenced_table="goals",
    )
    await _backfill_json_edge_table(
        db,
        source_table="programs",
        source_id_column="id",
        source_json_column="objective_ids",
        target_table="program_objectives",
        target_parent_column="program_id",
        target_child_column="objective_id",
        referenced_table="objectives",
    )
    await _backfill_json_edge_table(
        db,
        source_table="network_environments",
        source_id_column="id",
        source_json_column="server_ids",
        target_table="network_environment_servers",
        target_parent_column="network_environment_id",
        target_child_column="server_id",
        referenced_table="test_servers",
    )
