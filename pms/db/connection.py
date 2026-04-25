"""Database connection management with pluggable backend support."""

import sqlite3
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from pms.config import get_settings
from pms.db.backends.base import DatabaseBackend
from pms.db.backends.factory import create_backend
from pms.db.errors import translate_sqlite_integrity_error
from pms.db.types import DbRow, DbRows, ExecuteResult, SqlParams, SqlParamTuple
from pms.exceptions import DatabaseError


class Database:
    """Database connection manager with pluggable backend support (SQLite or PostgreSQL)."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        """
        Initialize database with pluggable backend.

        Args:
            db_path: Database path/connection string
                - Path or str for SQLite: /path/to/db.db
                - str for PostgreSQL: postgresql://user:pass@host/db
                - None: Uses settings.database_path
        """
        settings = get_settings()

        # Determine connection string
        self.db_path: Path | None
        if db_path is None:
            self.connection_string = str(settings.database_path)
            self.db_path = settings.database_path
        elif isinstance(db_path, (str, Path)):
            self.connection_string = str(db_path)
            self.db_path = (
                Path(db_path) if not str(db_path).startswith("postgresql") else None
            )
        else:
            self.connection_string = str(db_path)
            self.db_path = None

        # Create appropriate backend
        self._backend: DatabaseBackend = create_backend(self.connection_string)
        self._connected = False

        # Retain a shared backend alias for callers that still reference it.
        self._connection: DatabaseBackend | None = None

    async def connect(self) -> DatabaseBackend:
        """Establish database connection."""
        if self._connected:
            return self._backend

        settings = get_settings()

        # Ensure parent directory exists (for SQLite)
        if self.db_path:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        await self._backend.connect(
            self.connection_string,
            sqlite_busy_timeout_ms=settings.sqlite_busy_timeout_ms,
            sqlite_lock_retry_count=settings.sqlite_lock_retry_count,
            sqlite_lock_retry_delay_ms=settings.sqlite_lock_retry_delay_ms,
            sqlite_journal_mode=settings.sqlite_journal_mode,
            sqlite_synchronous=settings.sqlite_synchronous,
        )
        self._connected = True
        self._connection = self._backend  # Shared backend alias for callers

        return self._backend

    async def disconnect(self) -> None:
        """Close database connection."""
        if self._connected:
            await self._backend.disconnect()
            self._connected = False
            self._connection = None

    async def execute(self, query: str, parameters: SqlParams = ()) -> ExecuteResult:
        """Execute a query and return cursor."""
        await self.connect()
        try:
            return await self._backend.execute(query, parameters)
        except sqlite3.IntegrityError as e:
            raise translate_sqlite_integrity_error(e) from e
        except Exception as e:
            raise DatabaseError(f"Query execution failed: {e}") from e

    async def execute_many(self, query: str, parameters: list[SqlParamTuple]) -> None:
        """Execute a query with multiple parameter sets."""
        await self.connect()
        try:
            for params in parameters:
                await self._backend.execute(query, params)
        except sqlite3.IntegrityError as e:
            raise translate_sqlite_integrity_error(e) from e
        except sqlite3.Error as e:
            raise DatabaseError(f"Batch query execution failed: {e}") from e

    async def fetch_one(self, query: str, parameters: SqlParams = ()) -> DbRow | None:
        """Execute query and fetch one row as dict."""
        await self.connect()
        return await self._backend.fetch_one(query, parameters)

    async def fetch_all(self, query: str, parameters: SqlParams = ()) -> DbRows:
        """Execute query and fetch all rows as list of dicts."""
        await self.connect()
        return await self._backend.fetch_all(query, parameters)

    async def commit(self) -> None:
        """Commit current transaction (deprecated - use transaction context)."""
        # Backends handle transactions internally
        pass

    async def rollback(self) -> None:
        """Rollback current transaction (deprecated - use transaction context)."""
        # Backends handle transactions internally
        pass

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[None]:
        """Context manager for database transactions."""
        await self.connect()
        async with self._backend.transaction():
            yield

    async def table_exists(self, table_name: str) -> bool:
        """Check if a table exists in the database."""
        await self.connect()
        return await self._backend.table_exists(table_name)

    @property
    def transaction_active(self) -> bool:
        """Whether the current asyncio task owns an active transaction."""
        if not self._connected:
            return False
        return self._backend.transaction_active

    @property
    def backend_name(self) -> str:
        """Get backend name (sqlite, postgresql)."""
        return self._backend.backend_name

    async def get_schema_version(self) -> int:
        """Get current schema version from schema_info."""
        if not await self.table_exists("schema_info"):
            return 0
        result = await self.fetch_one("SELECT MAX(version) as version FROM schema_info")
        return result["version"] if result and result["version"] else 0


# Global database instance (can be overridden for testing)
_db_instance: Database | None = None


def get_database() -> Database:
    """Get or create the global database instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database()
    return _db_instance


def set_database(db: Database | None) -> None:
    """Set the global database instance (for testing)."""
    global _db_instance
    _db_instance = db


async def init_database() -> Database:
    """Initialize database and apply the stable schema."""
    from pms.db.schema import initialize_schema

    db = get_database()
    await db.connect()
    await initialize_schema(db)
    return db
