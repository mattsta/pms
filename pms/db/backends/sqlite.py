"""SQLite database backend implementation."""

from __future__ import annotations

import asyncio
import sqlite3
import threading
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime
from itertools import count
from pathlib import Path
from typing import Any

import aiosqlite

from pms.db.backends.base import DatabaseBackend
from pms.db.types import DbRow, DbRows, DbValue, SqlParams


class SQLiteBackend(DatabaseBackend):
    """SQLite backend using aiosqlite."""

    def __init__(self) -> None:
        self._connection: aiosqlite.Connection | None = None
        self._db_path: Path | None = None
        self._busy_timeout_ms = 30_000
        self._lock_retry_count = 5
        self._lock_retry_delay_ms = 200
        self._journal_mode = "WAL"
        self._synchronous = "NORMAL"
        self._connection_lock = threading.Lock()
        self._transaction_owner: asyncio.Task[Any] | None = None
        self._transaction_depth = 0
        self._savepoint_counter = count(1)

    async def connect(
        self, connection_string: str, **kwargs: str | int | float | bool
    ) -> None:
        """Connect to SQLite database."""
        # Handle both sqlite:///path and direct /path formats
        if connection_string.startswith("sqlite://"):
            path_str = connection_string.replace("sqlite:///", "")
        else:
            path_str = connection_string

        self._db_path = Path(path_str)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._busy_timeout_ms = int(kwargs.get("sqlite_busy_timeout_ms", 30_000))
        self._lock_retry_count = int(kwargs.get("sqlite_lock_retry_count", 5))
        self._lock_retry_delay_ms = int(kwargs.get("sqlite_lock_retry_delay_ms", 200))
        self._journal_mode = str(kwargs.get("sqlite_journal_mode", "WAL")).upper()
        self._synchronous = str(kwargs.get("sqlite_synchronous", "NORMAL")).upper()

        self._connection = await aiosqlite.connect(
            str(self._db_path),
            isolation_level=None,  # Autocommit mode
            timeout=max(self._busy_timeout_ms / 1000, 0.1),
        )
        self._connection.row_factory = aiosqlite.Row

        await self._connection.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")
        await self._connection.execute(f"PRAGMA journal_mode = {self._journal_mode}")
        await self._connection.execute(f"PRAGMA synchronous = {self._synchronous}")
        await self._connection.execute("PRAGMA foreign_keys = ON")

    async def disconnect(self) -> None:
        """Disconnect from SQLite database."""
        if self._connection:
            await self._connection.close()
            self._connection = None

    async def execute(self, query: str, parameters: SqlParams = ()) -> aiosqlite.Cursor:
        """Execute query and return cursor."""
        if self._connection is None:
            raise RuntimeError("Not connected to database")

        if self._current_task_owns_transaction():
            return await self._execute_with_retry(query, parameters)

        await self._acquire_connection_lock()
        try:
            return await self._execute_with_retry(query, parameters)
        finally:
            self._connection_lock.release()

    async def fetch_one(self, query: str, parameters: SqlParams = ()) -> DbRow | None:
        """Fetch one row as dictionary."""
        if self._current_task_owns_transaction():
            cursor = await self._execute_with_retry(query, parameters)
            row = await cursor.fetchone()
        else:
            await self._acquire_connection_lock()
            try:
                cursor = await self._execute_with_retry(query, parameters)
                row = await cursor.fetchone()
            finally:
                self._connection_lock.release()

        if row is None:
            return None

        return _normalize_row(dict(row))

    async def fetch_all(self, query: str, parameters: SqlParams = ()) -> DbRows:
        """Fetch all rows as list of dictionaries."""
        if self._current_task_owns_transaction():
            cursor = await self._execute_with_retry(query, parameters)
            rows = await cursor.fetchall()
        else:
            await self._acquire_connection_lock()
            try:
                cursor = await self._execute_with_retry(query, parameters)
                rows = await cursor.fetchall()
            finally:
                self._connection_lock.release()

        return [_normalize_row(dict(row)) for row in rows]

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[None]:
        """Transaction context manager."""
        if self._connection is None:
            raise RuntimeError("Not connected to database")

        if self._current_task_owns_transaction():
            savepoint = f"pms_nested_tx_{next(self._savepoint_counter)}"
            self._transaction_depth += 1
            await self._execute_with_retry(f"SAVEPOINT {savepoint}")
            try:
                yield
                await self._execute_with_retry(f"RELEASE SAVEPOINT {savepoint}")
            except Exception:
                await self._execute_with_retry(f"ROLLBACK TO SAVEPOINT {savepoint}")
                await self._execute_with_retry(f"RELEASE SAVEPOINT {savepoint}")
                raise
            finally:
                self._transaction_depth -= 1
            return

        current_task = asyncio.current_task()
        if current_task is None:
            raise RuntimeError("SQLite transactions require an active asyncio task")

        # Hold exclusive access to the shared connection for the full lifetime of
        # the outer transaction so concurrent tasks cannot interleave statements
        # into the same underlying SQLite transaction.
        await self._acquire_connection_lock()
        self._transaction_owner = current_task
        self._transaction_depth = 1
        try:
            # Acquire a write lock up front so contention is surfaced and retried
            # before the caller starts issuing mutating statements.
            await self._execute_with_retry("BEGIN IMMEDIATE")
            try:
                yield
                await self._execute_with_retry("COMMIT")
            except Exception:
                await self._execute_with_retry("ROLLBACK")
                raise
        finally:
            self._transaction_depth = 0
            self._transaction_owner = None
            self._connection_lock.release()

    async def table_exists(self, table_name: str) -> bool:
        """Check if table exists."""
        result = await self.fetch_one(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        )
        return result is not None

    def translate_query(self, query: str) -> str:
        """SQLite uses queries as-is (no translation needed)."""
        return query

    @property
    def backend_name(self) -> str:
        """Backend name."""
        return "sqlite"

    @property
    def supports_returning(self) -> bool:
        """SQLite supports RETURNING (3.35+)."""
        return True

    @property
    def placeholder_style(self) -> str:
        """SQLite uses ? placeholders."""
        return "qmark"

    @property
    def transaction_active(self) -> bool:
        """Whether the current asyncio task owns the active SQLite transaction."""
        return self._current_task_owns_transaction()

    async def _execute_with_retry(
        self, query: str, parameters: SqlParams = ()
    ) -> aiosqlite.Cursor:
        if self._connection is None:
            raise RuntimeError("Not connected to database")

        attempts = max(self._lock_retry_count, 0) + 1
        for attempt in range(attempts):
            try:
                return await self._connection.execute(query, parameters)
            except sqlite3.OperationalError as exc:
                if not _is_locked_error(exc) or attempt + 1 >= attempts:
                    raise
                await asyncio.sleep((self._lock_retry_delay_ms / 1000) * (attempt + 1))

        raise RuntimeError("SQLite retry loop exhausted unexpectedly")

    def _current_task_owns_transaction(self) -> bool:
        current_task = asyncio.current_task()
        return (
            current_task is not None
            and self._transaction_owner is current_task
            and self._transaction_depth > 0
        )

    async def _acquire_connection_lock(self) -> None:
        await asyncio.to_thread(self._connection_lock.acquire)


def _normalize_row(raw_row: dict[str, DbValue | bytes]) -> DbRow:
    normalized: DbRow = {}
    for key, value in raw_row.items():
        normalized[str(key)] = _normalize_value(value)
    return normalized


def _normalize_value(value: DbValue | bytes) -> DbValue:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, datetime):
        return value
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _normalize_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_normalize_value(item) for item in value)
    return str(value)


def _is_locked_error(exc: sqlite3.OperationalError) -> bool:
    message = str(exc).lower()
    return "database is locked" in message or "database table is locked" in message
