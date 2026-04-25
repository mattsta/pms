from __future__ import annotations

from pathlib import Path

from scripts.audit_discoverability_wrappers import (
    audit_discoverability_wrappers,
    audit_route_source,
)


def test_audit_route_source_detects_missing_discoverability_keys() -> None:
    source = """
from fastapi import APIRouter
from pms.api.types import PaginatedResponse

router = APIRouter()

@router.get("/api/v1/widgets")
async def list_widgets() -> PaginatedResponse[dict[str, str]]:
    return {
        "items": [],
        "total_count": 0,
        "offset": 0,
        "limit": 20,
    }
"""
    targets, issues = audit_route_source(source, file_path=Path("widgets.py"))

    assert len(targets) == 1
    assert targets[0].path == "/api/v1/widgets"
    assert len(issues) == 1
    assert issues[0].reason == "Missing discoverability wrapper keys"
    assert issues[0].missing_keys == ("links", "next_steps", "params")


def test_audit_route_source_accepts_variable_payload_with_wrappers() -> None:
    source = """
from fastapi import APIRouter
from pms.api.types import PaginatedResponse

router = APIRouter()

@router.get("/api/v1/widgets")
async def list_widgets() -> PaginatedResponse[dict[str, str]]:
    payload = {
        "items": [],
        "total_count": 0,
        "offset": 0,
        "limit": 20,
        "links": {"self": "/api/v1/widgets", "next": None, "guide": "/api/v1/"},
        "next_steps": ["GET /api/v1/widgets/{widget_id}"],
        "params": {"limit": 20, "offset": 0},
    }
    return payload
"""
    targets, issues = audit_route_source(source, file_path=Path("widgets.py"))

    assert len(targets) == 1
    assert issues == ()


def test_repo_paginated_routes_have_discoverability_wrappers() -> None:
    audit = audit_discoverability_wrappers(Path("pms/api/routes"))

    assert audit.route_total > 0
    assert audit.issue_total == 0
