"""Runtime helpers for PMS write coordination modes."""

from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class ServerHealthStatus:
    """Observed health state for the configured PMS server."""

    base_url: str
    reachable: bool
    status: str | None
    database: str | None
    error: str | None


@dataclass(frozen=True)
class ServerAuthStatus:
    """Observed auth viability for delegated PMS server writes."""

    base_url: str
    checked: bool
    authorized: bool
    error: str | None


def probe_server_health(
    base_url: str,
    timeout_seconds: float = 1.0,
) -> ServerHealthStatus:
    """Probe the configured PMS server health endpoint."""
    try:
        response = httpx.get(
            f"{base_url.rstrip('/')}/api/v1/health",
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            return ServerHealthStatus(
                base_url=base_url,
                reachable=False,
                status=None,
                database=None,
                error="Health endpoint returned a non-object payload",
            )
        raw_status = payload.get("status")
        raw_database = payload.get("database")
        return ServerHealthStatus(
            base_url=base_url,
            reachable=True,
            status=raw_status if isinstance(raw_status, str) else None,
            database=raw_database if isinstance(raw_database, str) else None,
            error=None,
        )
    except httpx.HTTPError as exc:
        return ServerHealthStatus(
            base_url=base_url,
            reachable=False,
            status=None,
            database=None,
            error=str(exc),
        )


def probe_server_auth(
    base_url: str,
    api_key: str,
    timeout_seconds: float = 1.0,
) -> ServerAuthStatus:
    """Probe whether the configured API key is actually authorized."""
    try:
        response = httpx.get(
            f"{base_url.rstrip('/')}/api/v1/auth/keys",
            headers={"X-API-Key": api_key},
            timeout=timeout_seconds,
        )
        if response.status_code in {401, 403}:
            detail = None
            try:
                payload = response.json()
            except ValueError:
                payload = None
            if isinstance(payload, dict):
                raw_detail = payload.get("detail")
                if isinstance(raw_detail, str):
                    detail = raw_detail
            return ServerAuthStatus(
                base_url=base_url,
                checked=True,
                authorized=False,
                error=detail or response.text or f"HTTP {response.status_code}",
            )
        response.raise_for_status()
        return ServerAuthStatus(
            base_url=base_url,
            checked=True,
            authorized=True,
            error=None,
        )
    except httpx.HTTPError as exc:
        return ServerAuthStatus(
            base_url=base_url,
            checked=True,
            authorized=False,
            error=str(exc),
        )
