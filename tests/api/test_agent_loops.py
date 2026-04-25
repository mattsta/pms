from __future__ import annotations

import pytest

from pms.core.events import EventStore, EventType
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.models.enums import SessionStatus
from pms.repositories.session_repository import SessionRepository


@pytest.mark.asyncio
async def test_agent_loop_endpoints(api_client, api_db) -> None:
    event_store = EventStore(api_db)
    revision_store = RevisionStore(api_db)
    metrics = MetricsCollector(api_db)
    repo = SessionRepository(api_db, event_store, revision_store, metrics)

    session = await repo.create(
        project_id=None,
        context_summary="agent_loop",
        initial_prompt="Do the thing",
    )
    session.state = {
        "loop": {
            "agent": "fake",
            "iterations": 1,
            "max_iterations": 5,
            "max_runtime_seconds": 60,
        }
    }
    session.status = SessionStatus.ACTIVE
    session.last_prompt = "Do the thing"
    session.last_response_summary = "Working on it"
    await repo.save(session, EventType.SESSION_UPDATED, {"loop_started": True})
    await repo.add_message(
        session.id,
        "user",
        "Do the thing",
        cost=0.0125,
        metadata={"iteration": 1},
    )

    list_resp = await api_client.get("/api/v1/agent-loops")
    assert list_resp.status_code == 200
    payload = list_resp.json()
    assert payload["items"]
    assert payload["links"]["guide"] == "/api/v1/"
    assert isinstance(payload["next_steps"], list)
    assert payload["next_steps"]
    assert payload["params"]["include_ended"] is False

    loop_id = payload["items"][0]["id"]
    detail_resp = await api_client.get(f"/api/v1/agent-loops/{loop_id}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["id"] == session.id

    messages_resp = await api_client.get(f"/api/v1/agent-loops/{loop_id}/messages")
    assert messages_resp.status_code == 200
    messages_payload = messages_resp.json()
    assert messages_payload["items"]
    assert messages_payload["links"]["guide"] == "/api/v1/"
    assert messages_payload["links"]["loop"] == f"/api/v1/agent-loops/{loop_id}"
    assert isinstance(messages_payload["next_steps"], list)
    assert messages_payload["next_steps"]
    assert messages_payload["total_count"] >= len(messages_payload["items"])
    assert messages_payload["items"][0]["cost_usd"] == "0.0125"

    cancel_resp = await api_client.post(f"/api/v1/agent-loops/{loop_id}/cancel")
    assert cancel_resp.status_code == 200
