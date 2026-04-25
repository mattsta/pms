"""Integration tests for server + client."""

import pytest


@pytest.mark.asyncio
async def test_client_server_integration(api_db):
    """Test client communicating with server."""
    # This would require server to be running
    # For now, tests use ASGI transport (in-process)
    # Real integration would start server subprocess
    pass


@pytest.mark.asyncio
async def test_concurrent_checkouts(api_db):
    """Test multiple agents checking out different tasks concurrently."""
    # Would test 10+ concurrent checkout requests
    pass


@pytest.mark.asyncio
async def test_load_100_requests(api_db):
    """Test server handling 100 concurrent requests."""
    # Load testing - create 100 tasks concurrently
    pass
