"""Database backend factory for auto-detection and creation."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pms.db.backends.base import DatabaseBackend


def create_backend(connection_string: str | Path) -> DatabaseBackend:
    """
    Create appropriate database backend based on connection string.

    Supports:
    - SQLite: sqlite:///path/to/db.db or /path/to/db.db
    - PostgreSQL: postgresql://user:pass@host:port/dbname

    Args:
        connection_string: Database connection string or path

    Returns:
        Appropriate DatabaseBackend instance

    Raises:
        ValueError: If connection string format is unknown
    """
    conn_str = str(connection_string)

    # PostgreSQL
    if conn_str.startswith("postgresql://") or conn_str.startswith("postgres://"):
        from pms.db.backends.postgresql import PostgreSQLBackend

        return PostgreSQLBackend()

    # SQLite (default)
    if (
        conn_str.startswith("sqlite://")
        or Path(conn_str).suffix == ".db"
        or "/" in conn_str
    ):
        from pms.db.backends.sqlite import SQLiteBackend

        return SQLiteBackend()

    raise ValueError(
        f"Unknown database connection string format: {conn_str}. "
        "Supported: sqlite:///path/to/db.db, /path/to/db.db, postgresql://..."
    )


def get_backend_name(connection_string: str | Path) -> str:
    """Get backend name without creating instance."""
    conn_str = str(connection_string)

    if conn_str.startswith("postgresql://") or conn_str.startswith("postgres://"):
        return "postgresql"

    return "sqlite"
