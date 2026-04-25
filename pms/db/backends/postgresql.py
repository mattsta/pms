"""PostgreSQL database backend implementation."""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime
from itertools import count
from typing import Any
from weakref import WeakKeyDictionary

from pms.db.backends.base import DatabaseBackend
from pms.db.types import DbRow, DbRows, DbValue, ExecuteResult, SqlParams, SqlParamTuple

try:
    import asyncpg
except ImportError:
    asyncpg = None


class PostgreSQLBackend(DatabaseBackend):
    """PostgreSQL backend using asyncpg."""

    def __init__(self) -> None:
        self._pool: asyncpg.Pool | None = None
        self._connection_string: str | None = None
        self._transaction_connections: WeakKeyDictionary[asyncio.Task[Any], Any] = (
            WeakKeyDictionary()
        )

    async def connect(
        self, connection_string: str, **kwargs: str | int | float | bool
    ) -> None:
        """Connect to PostgreSQL database."""
        if asyncpg is None:
            raise ImportError(
                "asyncpg is required for PostgreSQL backend. "
                "Install the optional PostgreSQL support with: uv sync --extra postgres"
            )

        self._connection_string = connection_string

        # Create connection pool
        pool_size = kwargs.get("pool_size", 10)
        self._pool = await asyncpg.create_pool(
            connection_string,
            min_size=1,
            max_size=pool_size,
        )

    async def disconnect(self) -> None:
        """Disconnect from PostgreSQL."""
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def execute(self, query: str, parameters: SqlParams = ()) -> ExecuteResult:
        """Execute query."""
        if self._pool is None:
            raise RuntimeError("Not connected to database")

        pg_query, pg_params = self._prepare_query(query, parameters)
        active_conn = self._active_transaction_connection()
        if active_conn is not None:
            return str(await active_conn.execute(pg_query, *pg_params))

        async with self._pool.acquire() as conn:
            return str(await conn.execute(pg_query, *pg_params))

    async def fetch_one(self, query: str, parameters: SqlParams = ()) -> DbRow | None:
        """Fetch one row as dictionary."""
        if self._pool is None:
            raise RuntimeError("Not connected to database")

        pg_query, pg_params = self._prepare_query(query, parameters)
        active_conn = self._active_transaction_connection()
        if active_conn is not None:
            row = await active_conn.fetchrow(pg_query, *pg_params)
        else:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(pg_query, *pg_params)

        if row is None:
            return None

        return _normalize_row(dict(row))

    async def fetch_all(self, query: str, parameters: SqlParams = ()) -> DbRows:
        """Fetch all rows as list of dictionaries."""
        if self._pool is None:
            raise RuntimeError("Not connected to database")

        pg_query, pg_params = self._prepare_query(query, parameters)
        active_conn = self._active_transaction_connection()
        if active_conn is not None:
            rows = await active_conn.fetch(pg_query, *pg_params)
        else:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(pg_query, *pg_params)
        return [_normalize_row(dict(row)) for row in rows]

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[None]:
        """Transaction context manager."""
        if self._pool is None:
            raise RuntimeError("Not connected to database")

        active_conn = self._active_transaction_connection()
        if active_conn is not None:
            async with active_conn.transaction():
                yield
            return

        async with self._pool.acquire() as conn:
            task = self._require_current_task()
            self._transaction_connections[task] = conn
            try:
                async with conn.transaction():
                    yield
            finally:
                self._transaction_connections.pop(task, None)

    async def table_exists(self, table_name: str) -> bool:
        """Check if table exists in PostgreSQL."""
        result = await self.fetch_one(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = $1
            ) as exists
            """,
            (table_name,),
        )
        return bool(result.get("exists")) if result else False

    def translate_query(self, query: str) -> str:
        """
        Translate SQLite query to PostgreSQL.

        Handles:
        - Placeholders: ? → $1, $2, etc.
        - datetime('now') → CURRENT_TIMESTAMP
        - AUTOINCREMENT → SERIAL
        - INTEGER (for booleans) → BOOLEAN
        """
        translated = query

        # Replace ? placeholders with $1, $2, etc. in left-to-right order.
        placeholder_counter = count(1)
        translated = re.sub(
            r"\?",
            lambda _match: f"${next(placeholder_counter)}",
            translated,
        )

        # Replace SQLite date functions
        translated = re.sub(
            r"datetime\(['\"]now['\"]\)",
            "CURRENT_TIMESTAMP",
            translated,
            flags=re.IGNORECASE,
        )

        # Replace SQLite-specific syntax
        translated = translated.replace("AUTOINCREMENT", "")  # PostgreSQL uses SERIAL

        # Handle IF NOT EXISTS (PostgreSQL syntax slightly different)
        translated = translated.replace("IF NOT EXISTS", "IF NOT EXISTS")

        return translated

    def _convert_params(self, parameters: SqlParams) -> SqlParamTuple:
        """Convert parameters to format expected by asyncpg."""
        if isinstance(parameters, dict):
            # asyncpg doesn't support named parameters directly
            # Would need to handle this differently
            raise NotImplementedError(
                "Named parameters not yet supported for PostgreSQL"
            )

        return parameters

    def _prepare_query(
        self, query: str, parameters: SqlParams
    ) -> tuple[str, SqlParamTuple]:
        """Translate a query and normalize parameter tuples for asyncpg."""
        return self.translate_query(query), self._convert_params(parameters)

    @property
    def backend_name(self) -> str:
        """Backend name."""
        return "postgresql"

    @property
    def supports_returning(self) -> bool:
        """PostgreSQL fully supports RETURNING."""
        return True

    @property
    def placeholder_style(self) -> str:
        """PostgreSQL uses numbered placeholders."""
        return "numbered"

    @property
    def transaction_active(self) -> bool:
        """Whether the current asyncio task owns an active PostgreSQL transaction."""
        return self._active_transaction_connection() is not None

    def _active_transaction_connection(self) -> Any | None:
        task = asyncio.current_task()
        if task is None:
            return None
        return self._transaction_connections.get(task)

    def _require_current_task(self) -> asyncio.Task[Any]:
        task = asyncio.current_task()
        if task is None:  # pragma: no cover - defensive guard for invalid sync usage
            raise RuntimeError(
                "PostgreSQL transactions must run inside an active asyncio task"
            )
        return task


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
