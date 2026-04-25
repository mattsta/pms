"""Live PostgreSQL backend integration coverage."""

from __future__ import annotations

import asyncio
import secrets
import shutil
import subprocess
from collections.abc import Generator
from urllib.parse import quote

import pytest

from pms.db.backends.postgresql import PostgreSQLBackend


def _require_local_postgres() -> str:
    if pytest.importorskip("asyncpg") is None:  # pragma: no cover
        raise RuntimeError("asyncpg import unexpectedly returned None")

    for command in ("pg_isready", "psql", "createdb", "dropdb"):
        if shutil.which(command) is None:
            pytest.skip(f"{command} is required for live PostgreSQL backend tests")

    ready = subprocess.run(
        ["pg_isready"],
        capture_output=True,
        text=True,
        check=False,
    )
    if ready.returncode != 0:
        pytest.skip("Local PostgreSQL server is not accepting connections")

    user_result = subprocess.run(
        ["psql", "-Atqc", "select current_user", "postgres"],
        capture_output=True,
        text=True,
        check=False,
    )
    if user_result.returncode != 0 or not user_result.stdout.strip():
        pytest.skip("Could not resolve a usable local PostgreSQL user")

    return user_result.stdout.strip()


@pytest.fixture
def postgres_test_database() -> Generator[str]:
    user = _require_local_postgres()
    db_name = f"pms_backend_live_{secrets.token_hex(6)}"
    created = subprocess.run(
        ["createdb", db_name],
        capture_output=True,
        text=True,
        check=False,
    )
    if created.returncode != 0:
        pytest.skip(
            f"Could not create disposable PostgreSQL database: {created.stderr}"
        )

    dsn = f"postgresql://{quote(user)}@/{db_name}?host=/tmp"
    try:
        yield dsn
    finally:
        subprocess.run(
            ["dropdb", "--if-exists", db_name],
            capture_output=True,
            text=True,
            check=False,
        )


@pytest.mark.asyncio
async def test_postgresql_backend_transaction_rolls_back_and_reuses_connection(
    postgres_test_database: str,
) -> None:
    backend = PostgreSQLBackend()
    await backend.connect(postgres_test_database)

    try:
        await backend.execute(
            "CREATE TABLE backend_tx_test (id INTEGER PRIMARY KEY, value TEXT)"
        )

        with pytest.raises(RuntimeError, match="boom"):
            async with backend.transaction():
                await backend.execute(
                    "INSERT INTO backend_tx_test (id, value) VALUES (?, ?)",
                    (1, "before"),
                )
                row = await backend.fetch_one(
                    "SELECT value FROM backend_tx_test WHERE id = ?",
                    (1,),
                )
                assert row is not None
                assert row["value"] == "before"

                async with backend.transaction():
                    nested = await backend.fetch_one(
                        "SELECT value FROM backend_tx_test WHERE id = ?",
                        (1,),
                    )
                    assert nested is not None
                    assert nested["value"] == "before"

                raise RuntimeError("boom")

        rolled_back = await backend.fetch_one(
            "SELECT COUNT(*) AS count FROM backend_tx_test WHERE id = ?",
            (1,),
        )
        assert rolled_back is not None
        assert rolled_back["count"] == 0

        async with backend.transaction():
            await backend.execute(
                "INSERT INTO backend_tx_test (id, value) VALUES (?, ?)",
                (2, "committed"),
            )

        committed = await backend.fetch_one(
            "SELECT value FROM backend_tx_test WHERE id = ?",
            (2,),
        )
        assert committed is not None
        assert committed["value"] == "committed"
    finally:
        await backend.disconnect()


@pytest.mark.asyncio
async def test_postgresql_backend_child_task_does_not_reuse_released_transaction_connection(
    postgres_test_database: str,
) -> None:
    backend = PostgreSQLBackend()
    await backend.connect(postgres_test_database, pool_size=2)
    release_child = asyncio.Event()

    async def child() -> int:
        await release_child.wait()
        row = await backend.fetch_one("SELECT 1 AS value")
        assert row is not None
        return int(row["value"])

    try:
        async with backend.transaction():
            row = await backend.fetch_one("SELECT 41 + 1 AS value")
            assert row is not None
            assert int(row["value"]) == 42
            child_task = asyncio.create_task(child())

        release_child.set()
        assert await child_task == 1
    finally:
        await backend.disconnect()
