"""Shared actor payload helpers for API routes."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus


async def resolve_actor_reference_map(
    actor_service: Any,
    actor_keys: list[str | None],
) -> dict[str, Any]:
    """Resolve actor selectors into actor models keyed by the original input."""
    actor_map: dict[str, Any] = {}
    for actor_key in actor_keys:
        if actor_key and actor_key not in actor_map:
            actor_map[actor_key] = await actor_service.get_actor(actor_key)
    return actor_map


async def resolve_owner_map(
    actor_service: Any,
    entities: list[Any],
) -> dict[str, Any]:
    """Resolve owner actor refs for a list of entities."""
    return await resolve_actor_reference_map(
        actor_service,
        [
            actor_key
            for entity in entities
            for actor_key in (
                getattr(entity, "owner_id", None),
                getattr(entity, "owner", None),
            )
        ],
    )


def actor_reference_payload(
    actor_key: str | None,
    actor_map: dict[str, Any],
    *,
    actor_id: str | None = None,
) -> dict[str, Any]:
    """Build a standard API actor reference payload."""
    actor_obj = actor_map.get(actor_id) if actor_id else None
    if actor_obj is None and actor_key:
        actor_obj = actor_map.get(actor_key)
    if actor_obj is None:
        return {
            "ref": actor_key,
            "id": actor_id,
            "actor": None,
            "links": {"actor": None, "tasks": None},
        }
    encoded_handle = quote_plus(actor_obj.handle)
    return {
        "ref": actor_key,
        "id": actor_id or actor_obj.id,
        "actor": actor_obj.to_dict(),
        "links": {
            "actor": f"/api/v1/actors/{encoded_handle}",
            "tasks": f"/api/v1/tasks/search?assignee={encoded_handle}",
        },
    }


def resolved_actor_payload(actor_obj: Any | None) -> dict[str, Any] | None:
    """Build a standard actor payload from a resolved actor model."""
    if actor_obj is None:
        return None
    encoded_handle = quote_plus(actor_obj.handle)
    return {
        "ref": actor_obj.handle,
        "id": actor_obj.id,
        "actor": actor_obj.to_dict(),
        "links": {
            "actor": f"/api/v1/actors/{encoded_handle}",
            "tasks": f"/api/v1/tasks/search?assignee={encoded_handle}",
        },
    }


def checkout_payload(
    *,
    agent_session_id: str | None,
    actor_obj: Any | None,
    checked_out_at: Any = None,
    lease_until: Any = None,
    version: int | None = None,
    expired: bool | None = None,
) -> dict[str, Any] | None:
    """Build a standard checkout payload."""
    if (
        agent_session_id is None
        and actor_obj is None
        and checked_out_at is None
        and lease_until is None
        and version is None
        and expired is None
    ):
        return None
    return {
        "agent_session_id": agent_session_id,
        "actor": resolved_actor_payload(actor_obj),
        "checked_out_at": checked_out_at,
        "lease_until": lease_until,
        "version": version,
        "expired": expired,
    }


def member_payloads(
    member_refs: list[str] | tuple[str, ...],
    actor_map: dict[str, Any],
    *,
    actor_ids: list[str] | tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    """Build actor reference payloads for membership lists."""
    actor_ids_list = list(actor_ids or [])
    return [
        actor_reference_payload(
            member_ref,
            actor_map,
            actor_id=actor_ids_list[idx] if idx < len(actor_ids_list) else None,
        )
        for idx, member_ref in enumerate(member_refs)
    ]
