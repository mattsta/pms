from __future__ import annotations

import httpx
import pytest

from pms.client.http_client import PMSClient


@pytest.mark.asyncio
async def test_pms_client_get_dashboard_uses_api_dashboard_route() -> None:
    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        return httpx.Response(
            200,
            json={"scope": {"kind": "instance_dashboard"}},
        )

    client = PMSClient(base_url="http://test")
    client._client = httpx.AsyncClient(
        base_url="http://test",
        transport=httpx.MockTransport(handler),
    )
    try:
        payload = await client.get_dashboard()
    finally:
        await client._client.aclose()

    assert seen_paths == ["/api/v1/dashboard"]
    assert payload["scope"]["kind"] == "instance_dashboard"


@pytest.mark.asyncio
async def test_dashboard_family_requests_omit_none_query_params() -> None:
    seen_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        return httpx.Response(
            200, json={"items": [], "links": {"self": str(request.url)}}
        )

    client = PMSClient(base_url="http://test")
    client._client = httpx.AsyncClient(
        base_url="http://test",
        transport=httpx.MockTransport(handler),
    )
    try:
        await client.get_organization_dashboard()
        await client.get_portfolio_dashboard(org_id="org-123")
        await client.get_program_dashboard(org_id="org-123", portfolio_id="pf-456")
    finally:
        await client._client.aclose()

    assert seen_urls == [
        "http://test/api/v1/organizations/dashboard?limit=100&offset=0&include_digest=true&include_next_actions=true&include_evidence=true&include_retention=true&next_limit=3",
        "http://test/api/v1/portfolios/dashboard?org_id=org-123&limit=100&offset=0&include_digest=true&include_next_actions=true&include_evidence=true&include_retention=true&next_limit=3",
        "http://test/api/v1/programs/dashboard?org_id=org-123&portfolio_id=pf-456&limit=100&offset=0&include_digest=true&include_next_actions=true&include_evidence=true&include_retention=true&next_limit=3",
    ]
