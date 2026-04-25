#!/usr/bin/env python3
"""Audit canonical actor-reference integrity across actor-aware surfaces."""

from __future__ import annotations

import argparse
import json
import sqlite3

from pms.config.settings import get_settings, reload_settings

OWNER_TABLES: tuple[tuple[str, str], ...] = (
    ("goals", "name"),
    ("objectives", "name"),
    ("key_results", "name"),
    ("products", "name"),
    ("organizations", "name"),
    ("teams", "name"),
    ("portfolios", "name"),
    ("programs", "name"),
    ("saved_searches", "name"),
)

MEMBERSHIP_TABLES: tuple[tuple[str, str, str, str], ...] = (
    ("organizations", "name", "organization_members", "organization_id"),
    ("teams", "name", "team_members", "team_id"),
)


def _connect() -> sqlite3.Connection:
    reload_settings()
    settings = get_settings()
    conn = sqlite3.connect(str(settings.database_path))
    conn.row_factory = sqlite3.Row
    return conn


def _load_actor_handles(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute("SELECT id, handle FROM actors").fetchall()
    return {str(row["id"]): str(row["handle"]) for row in rows}


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row["name"]) for row in rows}


def _parse_json_list(raw_value: str | None) -> tuple[str, ...]:
    if raw_value is None or not raw_value.strip():
        return ()
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        return ()
    if not isinstance(parsed, list):
        return ()
    return tuple(str(item) for item in parsed if isinstance(item, str))


def _audit_owner_refs(
    conn: sqlite3.Connection,
    actor_handles: dict[str, str],
) -> list[str]:
    issues: list[str] = []
    for table_name, label_column in OWNER_TABLES:
        rows = conn.execute(
            f"""
            SELECT id, {label_column} AS label, owner, owner_id
            FROM {table_name}
            WHERE owner_id IS NOT NULL
            """
        ).fetchall()
        for row in rows:
            actor_id = str(row["owner_id"])
            handle = actor_handles.get(actor_id)
            label = row["label"]
            if handle is None:
                issues.append(
                    f"{table_name}:{row['id']} ({label}) references missing owner actor {actor_id}"
                )
                continue
            if row["owner"] != handle:
                issues.append(
                    f"{table_name}:{row['id']} ({label}) stores owner={row['owner']!r} but owner_id resolves to {handle!r}"
                )
    return issues


def _audit_task_refs(
    conn: sqlite3.Connection,
    actor_handles: dict[str, str],
) -> list[str]:
    issues: list[str] = []
    rows = conn.execute(
        """
        SELECT id, title, assignee, assignee_id, checkout_agent_session_id, checkout_actor_id
        FROM tasks
        WHERE assignee_id IS NOT NULL
           OR checkout_actor_id IS NOT NULL
           OR checkout_agent_session_id IS NOT NULL
        """
    ).fetchall()
    for row in rows:
        title = row["title"]
        assignee_id = row["assignee_id"]
        if assignee_id is not None:
            actor_id = str(assignee_id)
            handle = actor_handles.get(actor_id)
            if handle is None:
                issues.append(
                    f"tasks:{row['id']} ({title}) references missing assignee actor {actor_id}"
                )
            elif row["assignee"] != handle:
                issues.append(
                    f"tasks:{row['id']} ({title}) stores assignee={row['assignee']!r} but assignee_id resolves to {handle!r}"
                )

        checkout_actor_id = row["checkout_actor_id"]
        if checkout_actor_id is not None:
            actor_id = str(checkout_actor_id)
            if actor_handles.get(actor_id) is None:
                issues.append(
                    f"tasks:{row['id']} ({title}) references missing checkout actor {actor_id}"
                )
            if not row["checkout_agent_session_id"]:
                issues.append(
                    f"tasks:{row['id']} ({title}) has checkout_actor_id without checkout_agent_session_id"
                )
        elif row["checkout_agent_session_id"]:
            issues.append(
                f"tasks:{row['id']} ({title}) has checkout_agent_session_id without checkout_actor_id"
            )
    return issues


def _audit_member_refs(
    conn: sqlite3.Connection,
    actor_handles: dict[str, str],
) -> list[str]:
    issues: list[str] = []
    for table_name, label_column, edge_table, edge_parent_column in MEMBERSHIP_TABLES:
        columns = _table_columns(conn, table_name)
        if {"members", "member_ids"}.issubset(columns):
            rows = conn.execute(
                f"""
                SELECT id, {label_column} AS label, members, member_ids
                FROM {table_name}
                WHERE member_ids IS NOT NULL AND member_ids != '[]'
                """
            ).fetchall()
            for row in rows:
                member_handles = set(_parse_json_list(row["members"]))
                member_ids = _parse_json_list(row["member_ids"])
                for actor_id in member_ids:
                    handle = actor_handles.get(actor_id)
                    if handle is None:
                        issues.append(
                            f"{table_name}:{row['id']} ({row['label']}) references missing member actor {actor_id}"
                        )
                        continue
                    if handle not in member_handles:
                        issues.append(
                            f"{table_name}:{row['id']} ({row['label']}) is missing stored member handle {handle!r} for actor {actor_id}"
                        )
            continue

        rows = conn.execute(
            f"""
            SELECT parent.id, parent.{label_column} AS label, edge.actor_id
            FROM {edge_table} edge
            JOIN {table_name} parent
              ON parent.id = edge.{edge_parent_column}
            """
        ).fetchall()
        for row in rows:
            actor_id = str(row["actor_id"])
            if actor_handles.get(actor_id) is None:
                issues.append(
                    f"{table_name}:{row['id']} ({row['label']}) references missing member actor {actor_id}"
                )
    return issues


def run_audit() -> tuple[str, ...]:
    conn = _connect()
    try:
        actor_handles = _load_actor_handles(conn)
        issues: list[str] = []
        issues.extend(_audit_owner_refs(conn, actor_handles))
        issues.extend(_audit_task_refs(conn, actor_handles))
        issues.extend(_audit_member_refs(conn, actor_handles))
        return tuple(issues)
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Exit nonzero when issues are found"
    )
    args = parser.parse_args()

    issues = run_audit()
    print(json.dumps({"issue_count": len(issues), "issues": list(issues)}, indent=2))
    return 1 if args.check and issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
