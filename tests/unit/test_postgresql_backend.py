"""Tests for PostgreSQL backend transaction scoping."""

from __future__ import annotations

import asyncio

import pytest

from pms.db.backends.postgresql import PostgreSQLBackend


class _FakeTransactionContext:
    def __init__(self, connection: _FakeConnection) -> None:
        self._connection = connection

    async def __aenter__(self) -> None:
        self._connection.transaction_entries += 1

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        self._connection.transaction_exits.append(
            "rollback" if exc_type is not None else "commit"
        )
        return False


class _FakeConnection:
    def __init__(self, name: str) -> None:
        self.name = name
        self.operations: list[tuple[str, str, tuple[object, ...]]] = []
        self.transaction_entries = 0
        self.transaction_exits: list[str] = []

    async def execute(self, query: str, *params: object) -> str:
        self.operations.append(("execute", query, params))
        return f"{self.name}:EXECUTE"

    async def fetchrow(self, query: str, *params: object) -> dict[str, object]:
        self.operations.append(("fetchrow", query, params))
        return {"connection": self.name, "query": query, "params": list(params)}

    async def fetch(self, query: str, *params: object) -> list[dict[str, object]]:
        self.operations.append(("fetch", query, params))
        return [
            {"connection": self.name, "query": query, "params": list(params)},
            {"connection": self.name, "query": query, "params": list(params)},
        ]

    def transaction(self) -> _FakeTransactionContext:
        return _FakeTransactionContext(self)


class _FakeAcquireContext:
    def __init__(self, pool: _FakePool, connection: _FakeConnection) -> None:
        self._pool = pool
        self._connection = connection

    async def __aenter__(self) -> _FakeConnection:
        self._pool.acquire_calls.append(self._connection.name)
        return self._connection

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        self._pool.release_calls.append(self._connection.name)
        return False


class _FakePool:
    def __init__(self, connections: list[_FakeConnection]) -> None:
        self._connections = connections
        self._next_index = 0
        self.acquire_calls: list[str] = []
        self.release_calls: list[str] = []

    def acquire(self) -> _FakeAcquireContext:
        connection = self._connections[self._next_index]
        self._next_index += 1
        return _FakeAcquireContext(self, connection)


@pytest.mark.asyncio
async def test_transaction_scopes_execute_and_fetch_to_one_connection() -> None:
    backend = PostgreSQLBackend()
    first = _FakeConnection("conn-1")
    second = _FakeConnection("conn-2")
    backend._pool = _FakePool([first, second])

    async with backend.transaction():
        execute_result = await backend.execute("SELECT ?", (1,))
        row = await backend.fetch_one("SELECT ?", (2,))
        rows = await backend.fetch_all("SELECT ?", (3,))

    assert execute_result == "conn-1:EXECUTE"
    assert row["connection"] == "conn-1"
    assert [item["connection"] for item in rows] == ["conn-1", "conn-1"]
    assert backend._pool.acquire_calls == ["conn-1"]
    assert backend._pool.release_calls == ["conn-1"]
    assert first.transaction_entries == 1
    assert first.transaction_exits == ["commit"]
    assert first.operations == [
        ("execute", "SELECT $1", (1,)),
        ("fetchrow", "SELECT $1", (2,)),
        ("fetch", "SELECT $1", (3,)),
    ]


def test_translate_query_preserves_parameter_order() -> None:
    backend = PostgreSQLBackend()

    translated = backend.translate_query(
        "INSERT INTO backend_tx_test (id, value, note) VALUES (?, ?, ?)"
    )

    assert translated == (
        "INSERT INTO backend_tx_test (id, value, note) VALUES ($1, $2, $3)"
    )


@pytest.mark.asyncio
async def test_nested_transactions_reuse_active_connection() -> None:
    backend = PostgreSQLBackend()
    first = _FakeConnection("conn-1")
    backend._pool = _FakePool([first])

    async with backend.transaction():
        await backend.execute("SELECT ?", (1,))
        async with backend.transaction():
            row = await backend.fetch_one("SELECT ?", (2,))

    assert row["connection"] == "conn-1"
    assert backend._pool.acquire_calls == ["conn-1"]
    assert first.transaction_entries == 2
    assert first.transaction_exits == ["commit", "commit"]


@pytest.mark.asyncio
async def test_transaction_rollback_resets_active_connection() -> None:
    backend = PostgreSQLBackend()
    first = _FakeConnection("conn-1")
    second = _FakeConnection("conn-2")
    backend._pool = _FakePool([first, second])

    with pytest.raises(RuntimeError, match="boom"):
        async with backend.transaction():
            await backend.execute("SELECT ?", (1,))
            raise RuntimeError("boom")

    execute_result = await backend.execute("SELECT ?", (2,))

    assert execute_result == "conn-2:EXECUTE"
    assert backend._pool.acquire_calls == ["conn-1", "conn-2"]
    assert first.transaction_exits == ["rollback"]
    assert second.operations == [("execute", "SELECT $1", (2,))]


@pytest.mark.asyncio
async def test_child_task_created_inside_transaction_does_not_inherit_parent_connection() -> (
    None
):
    backend = PostgreSQLBackend()
    first = _FakeConnection("conn-1")
    second = _FakeConnection("conn-2")
    backend._pool = _FakePool([first, second])
    release_child = asyncio.Event()

    async def child() -> str:
        await release_child.wait()
        return await backend.execute("SELECT ?", (2,))

    async with backend.transaction():
        parent_result = await backend.execute("SELECT ?", (1,))
        child_task = asyncio.create_task(child())

    release_child.set()
    child_result = await child_task

    assert parent_result == "conn-1:EXECUTE"
    assert child_result == "conn-2:EXECUTE"
    assert backend._pool.acquire_calls == ["conn-1", "conn-2"]
    assert backend._pool.release_calls == ["conn-1", "conn-2"]
    assert first.transaction_exits == ["commit"]
