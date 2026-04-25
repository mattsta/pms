"""Abstract database backend interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from pms.db.types import DbRow, DbRows, ExecuteResult, SqlParams


class DatabaseBackend(ABC):
    """
    Abstract interface for database backends.

    Enables PMS to work with different databases (SQLite, PostgreSQL, etc.)
    by providing a consistent interface for common operations.
    """

    @abstractmethod
    async def connect(
        self, connection_string: str, **kwargs: str | int | float | bool
    ) -> None:
        """
        Connect to database.

        Args:
            connection_string: Database connection string
            **kwargs: Backend-specific options
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from database."""
        pass

    @abstractmethod
    async def execute(self, query: str, parameters: SqlParams = ()) -> ExecuteResult:
        """
        Execute a query.

        Args:
            query: SQL query
            parameters: Query parameters

        Returns:
            Backend-specific cursor/result
        """
        pass

    @abstractmethod
    async def fetch_one(self, query: str, parameters: SqlParams = ()) -> DbRow | None:
        """
        Fetch one row as dictionary.

        Args:
            query: SQL query
            parameters: Query parameters

        Returns:
            Row as dict or None
        """
        pass

    @abstractmethod
    async def fetch_all(self, query: str, parameters: SqlParams = ()) -> DbRows:
        """
        Fetch all rows as list of dictionaries.

        Args:
            query: SQL query
            parameters: Query parameters

        Returns:
            List of rows as dicts
        """
        pass

    @abstractmethod
    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[None]:
        """
        Context manager for transactions.

        Usage:
            async with backend.transaction():
                await backend.execute("INSERT ...")
                await backend.execute("UPDATE ...")
        """
        yield

    @abstractmethod
    async def table_exists(self, table_name: str) -> bool:
        """Check if a table exists."""
        pass

    @abstractmethod
    def translate_query(self, query: str) -> str:
        """
        Translate query for this backend's SQL dialect.

        Handles differences like:
        - Placeholders (? vs $1)
        - AUTO_INCREMENT vs SERIAL
        - datetime functions
        - JSON operations

        Args:
            query: Query in common/SQLite format

        Returns:
            Translated query for this backend
        """
        return query

    @property
    @abstractmethod
    def backend_name(self) -> str:
        """Get backend name (sqlite, postgresql, etc.)."""
        pass

    @property
    @abstractmethod
    def supports_returning(self) -> bool:
        """Whether backend supports RETURNING clause."""
        pass

    @property
    @abstractmethod
    def placeholder_style(self) -> str:
        """Placeholder style: 'qmark' (?) or 'numbered' ($1)."""
        pass

    @property
    @abstractmethod
    def transaction_active(self) -> bool:
        """Whether the current asyncio task already owns an active transaction."""
        pass
