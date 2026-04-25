"""Fixtures for API tests."""

from datetime import datetime
from pathlib import Path

import pytest

from pms.api.dependencies import init_services
from pms.db.connection import Database
from pms.db.schema import initialize_schema
from pms.repositories.api_key_repository import ApiKeyRepository
from pms.services.auth_service import AuthService


@pytest.fixture(scope="function")
async def api_db():
    """Create database and initialize services for API tests."""
    # Unique database for each test
    timestamp = datetime.now().timestamp()
    db_path = Path(f"/tmp/claude/api_test_{timestamp}.db")
    db_path.unlink(missing_ok=True)

    db = Database(db_path)
    await db.connect()
    await initialize_schema(db)

    # Initialize services (required for dependency injection)
    await init_services(db)

    yield db

    await db.disconnect()
    db_path.unlink(missing_ok=True)


@pytest.fixture
async def admin_api_key(api_db):
    """Create an admin API key for testing."""
    repo = ApiKeyRepository(api_db)
    service = AuthService(repo)

    plain_key, _ = await service.create_api_key(
        name="API Test Admin",
        scopes=["*"],
        expires_in_days=None,
        rate_limit=None,
    )

    return plain_key


@pytest.fixture
async def api_client(api_db, admin_api_key):
    """Create HTTP client for API testing with auth."""
    from httpx import ASGITransport, AsyncClient

    from pms.api.app import app

    # Override app state with test database
    app.state.db = api_db
    app.state.start_time = datetime.now().timestamp()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-API-Key": admin_api_key},
    ) as client:
        yield client
