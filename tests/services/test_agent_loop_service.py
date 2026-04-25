from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from pms.agents.loop import LoopConfig, LoopResponse
from pms.services.agent_loop_service import AgentLoopService
from pms.services.goal_service import GoalService


@dataclass
class FakeAdapter:
    name: str
    outputs: list[str]
    success: bool = True
    available: bool = True

    def __post_init__(self) -> None:
        self.config = type(
            "Cfg",
            (),
            {"max_retries": 0, "timeout_seconds": 1},
        )()
        self._index = 0

    async def run(self, prompt: str) -> LoopResponse:
        if self._index >= len(self.outputs):
            return LoopResponse(success=False, output="", error="no output")
        output = self.outputs[self._index]
        self._index += 1
        return LoopResponse(success=self.success, output=output, duration_seconds=0.01)


@pytest.mark.asyncio
async def test_agent_loop_completion_promise(
    db, event_store, revision_store, metrics_collector
):
    adapter = FakeAdapter(
        name="fake",
        outputs=[
            "working on it",
            "done <promise>DONE</promise>",
        ],
    )
    service = AgentLoopService(
        db,
        event_store,
        revision_store,
        metrics_collector,
        adapters={"fake": adapter},
    )
    config = LoopConfig(
        prompt_text="Do the thing",
        agent="fake",
        max_iterations=5,
        completion_promise="DONE",
    )

    summary = await service.run_loop(config)

    assert summary.stop_reason == "completion_promise"
    assert summary.iterations == 2

    session = await service._session_repo.get_by_id(summary.session_id)
    assert session is not None
    assert session.state["loop"]["iterations"] == 2

    messages = await service._session_repo.get_messages(summary.session_id)
    assert messages[0].metadata["iteration"] == 1
    assert messages[1].metadata["iteration"] == 1
    assert messages[2].metadata["iteration"] == 2
    assert messages[3].metadata["iteration"] == 2


@pytest.mark.asyncio
async def test_agent_loop_max_iterations(
    db, event_store, revision_store, metrics_collector
):
    adapter = FakeAdapter(
        name="fake",
        outputs=["output 1", "output 2", "output 3"],
    )
    service = AgentLoopService(
        db,
        event_store,
        revision_store,
        metrics_collector,
        adapters={"fake": adapter},
    )
    config = LoopConfig(
        prompt_text="Do the thing",
        agent="fake",
        max_iterations=2,
    )

    summary = await service.run_loop(config)

    assert summary.stop_reason == "max_iterations"
    assert summary.iterations == 2


@pytest.mark.asyncio
async def test_agent_loop_bootstrap_rolls_back_when_initial_loop_state_save_fails(
    db, event_store, revision_store, metrics_collector, monkeypatch: pytest.MonkeyPatch
):
    adapter = FakeAdapter(name="fake", outputs=["output 1"])
    service = AgentLoopService(
        db,
        event_store,
        revision_store,
        metrics_collector,
        adapters={"fake": adapter},
    )
    config = LoopConfig(
        prompt_text="Do the thing",
        agent="fake",
        max_iterations=1,
    )

    original_save = service._session_repo._save_in_transaction
    call_count = 0

    async def fail_on_second_save(*, model, event_type, payload, message=None):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("boom")
        return await original_save(
            model=model,
            event_type=event_type,
            payload=payload,
            message=message,
        )

    monkeypatch.setattr(
        service._session_repo,
        "_save_in_transaction",
        fail_on_second_save,
    )

    with pytest.raises(RuntimeError, match="boom"):
        await service.run_loop(config)

    assert await service._session_repo.list_sessions() == []


@pytest.mark.asyncio
async def test_agent_loop_blocks_soft_stop_until_goals_complete(
    db, event_store, revision_store, metrics_collector
):
    goal_service = GoalService(db, event_store, revision_store, metrics_collector)
    goal = await goal_service.create_goal(name="Guarded Goal")
    adapter = FakeAdapter(
        name="fake",
        outputs=[
            "working",
            "working",
        ],
    )
    service = AgentLoopService(
        db,
        event_store,
        revision_store,
        metrics_collector,
        adapters={"fake": adapter},
        goal_service=goal_service,
    )
    config = LoopConfig(
        prompt_text="Do the thing\nSTOP_NOW",
        agent="fake",
        max_iterations=5,
        completion_marker="STOP_NOW",
        stop_when_goals_complete=True,
        goal_ids=[goal.id],
    )

    original_record_guard_block = service._record_guard_block
    guard_blocked = asyncio.Event()
    guard_block_count = 0

    async def record_guard_block_and_signal(*args, **kwargs) -> None:
        nonlocal guard_block_count
        await original_record_guard_block(*args, **kwargs)
        guard_block_count += 1
        if guard_block_count >= 2:
            guard_blocked.set()

    service._record_guard_block = record_guard_block_and_signal

    completion_task = asyncio.create_task(
        _complete_goal_after_guard(goal_service, goal.id, guard_blocked)
    )

    summary = await service.run_loop(config)
    await completion_task

    assert summary.stop_reason == "completion_marker"
    assert summary.iterations == 2

    session = await service._session_repo.get_by_id(summary.session_id)
    assert session is not None
    assert session.state["loop"]["stop_blocked_count"] >= 2


async def _complete_goal_after_guard(
    goal_service: GoalService,
    goal_id: str,
    guard_blocked: asyncio.Event,
) -> None:
    await guard_blocked.wait()
    await goal_service.complete_goal(goal_id)
