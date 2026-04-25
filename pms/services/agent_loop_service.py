"""Agent loop service for Ralph-style iteration."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Protocol, TypedDict

from pms.agents.acp.adapter import ACPLoopAdapter
from pms.agents.acp.codex import CodexLoopAdapter
from pms.agents.coordinator import CoordinatorAgent
from pms.agents.loop import (
    AdapterConfig,
    ClaudeLoopAdapter,
    CommandLoopAdapter,
    LoopAdapter,
    LoopConfig,
    LoopResponse,
)
from pms.core.events import EventStore, EventType
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.models import Goal
from pms.models.base import now_utc
from pms.models.enums import GoalStatus, SessionStatus
from pms.models.json_types import JsonObject, ModelObject
from pms.models.session import Session
from pms.repositories.base import QueryResult
from pms.repositories.session_repository import SessionRepository

if TYPE_CHECKING:
    from pms.db.connection import Database


class GoalServiceProtocol(Protocol):
    async def get_goal(self, goal_id: str) -> Goal | None: ...

    async def list_goals(
        self,
        project_id: str | None = None,
        status: GoalStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Goal]: ...


class GoalGuardSnapshot(TypedDict, total=False):
    error: str
    goal_ids: list[str]
    missing_goals: list[str]
    total_goals: int
    completed_goals: int
    incomplete_goals: int
    include_archived_goals: bool
    allow_no_goals: bool


type LoopStatePayload = JsonObject


@dataclass
class LoopIteration:
    """Single loop iteration output."""

    iteration: int
    success: bool
    output: str
    error: str | None
    duration_seconds: float
    tokens_used: int | None = None
    cost_usd: float | None = None


@dataclass
class LoopSummary:
    """Summary of a loop run."""

    session_id: str
    agent: str
    status: str
    iterations: int
    max_iterations: int
    max_runtime_seconds: int
    stop_reason: str | None
    created_at: datetime
    updated_at: datetime
    ended_at: datetime | None
    last_prompt: str | None
    last_response_summary: str | None


class AgentLoopService:
    """Run and inspect Ralph-style agent loops."""

    def __init__(
        self,
        db: Database,
        event_store: EventStore,
        revision_store: RevisionStore,
        metrics: MetricsCollector,
        coordinator_agent: CoordinatorAgent | None = None,
        adapters: dict[str, LoopAdapter] | None = None,
        goal_service: GoalServiceProtocol | None = None,
    ) -> None:
        self._session_repo = SessionRepository(
            db,
            event_store,
            revision_store,
            metrics,
        )
        self._coordinator_agent = coordinator_agent
        self._adapters = adapters or {}
        self._goal_service = goal_service

    async def run_loop(
        self,
        config: LoopConfig,
        project_id: str | None = None,
        on_iteration: Callable[[LoopIteration], None] | None = None,
    ) -> LoopSummary:
        prompt = self._prepare_prompt(config, config.load_prompt())
        adapters = self._build_adapters(config)
        adapter = self._resolve_adapter(config, adapters)

        loop_state: LoopStatePayload = {
            "agent": adapter.name,
            "prompt_source": config.prompt_source(),
            "max_iterations": config.max_iterations,
            "max_runtime_seconds": config.max_runtime_seconds,
            "max_cost_usd": config.max_cost_usd,
            "retry_delay_seconds": config.retry_delay_seconds,
            "completion_promise": config.completion_promise,
            "completion_marker": config.completion_marker,
            "stop_when_goals_complete": config.stop_when_goals_complete,
            "goal_ids": list(config.goal_ids),
            "include_archived_goals": config.include_archived_goals,
            "allow_no_goals": config.allow_no_goals,
            "iterations": 0,
            "last_iteration_at": None,
            "stop_reason": None,
            "cancel_requested": False,
        }

        session = await self._session_repo.create_loop_session(
            project_id=project_id,
            context_summary="agent_loop",
            initial_prompt=prompt,
            loop_state=loop_state,
        )

        start_time = time.monotonic()
        stop_reason = None

        try:
            while True:
                if config.max_runtime_seconds > 0:
                    elapsed = time.monotonic() - start_time
                    if elapsed >= config.max_runtime_seconds:
                        stop_reason = "max_runtime"
                        break

                loop_state = await self._get_loop_state(session.id)
                if loop_state.get("cancel_requested", False):
                    stop_reason = "cancel_requested"
                    break

                current_iterations = loop_state.get("iterations", 0)

                if (
                    config.max_iterations > 0
                    and current_iterations >= config.max_iterations
                ):
                    stop_reason = "max_iterations"
                    if await self._should_block_soft_stop(
                        config,
                        project_id,
                        stop_reason,
                        session.id,
                    ):
                        stop_reason = None
                    else:
                        break

                prompt = self._prepare_prompt(config, config.load_prompt())
                if config.completion_marker and config.completion_marker in prompt:
                    stop_reason = "completion_marker"
                    if await self._should_block_soft_stop(
                        config,
                        project_id,
                        stop_reason,
                        session.id,
                    ):
                        stop_reason = None
                    else:
                        break

                iteration_number = current_iterations + 1
                await self._session_repo.add_message(
                    session.id,
                    "user",
                    prompt,
                    metadata={
                        "iteration": iteration_number,
                        "kind": "prompt",
                        "adapter": adapter.name,
                    },
                )

                if config.dry_run:
                    response = LoopResponse(
                        success=True,
                        output="Dry run - no agent execution",
                        duration_seconds=0.0,
                    )
                else:
                    response = await self._execute_with_retries(
                        adapter,
                        prompt,
                        config.retry_delay_seconds,
                    )

                await self._session_repo.add_message(
                    session.id,
                    "assistant",
                    response.output,
                    tokens=response.tokens_used,
                    cost=response.cost_usd,
                    metadata={
                        "iteration": iteration_number,
                        "kind": "response",
                        "adapter": adapter.name,
                        "success": response.success,
                        "error": response.error,
                        "duration_seconds": response.duration_seconds,
                    },
                )

                reloaded_session = await self._session_repo.get_by_id(session.id)
                if reloaded_session is None:
                    raise RuntimeError("Session disappeared during loop run")
                session = reloaded_session

                if response.tokens_used:
                    session.token_count += response.tokens_used
                if response.cost_usd:
                    session.cost_usd += response.cost_usd

                session.last_prompt = prompt
                session.last_response_summary = _summarize(response.output)
                loop_state = self._ensure_loop_state(session)
                loop_state.update(
                    {
                        "iterations": iteration_number,
                        "last_iteration_at": now_utc().isoformat(),
                        "last_error": response.error,
                    }
                )

                await self._session_repo.save(
                    session,
                    EventType.SESSION_UPDATED,
                    {
                        "loop_iteration": iteration_number,
                        "success": response.success,
                    },
                    message="Loop iteration",
                )

                if on_iteration:
                    on_iteration(
                        LoopIteration(
                            iteration=iteration_number,
                            success=response.success,
                            output=response.output,
                            error=response.error,
                            duration_seconds=response.duration_seconds,
                            tokens_used=response.tokens_used,
                            cost_usd=response.cost_usd,
                        )
                    )

                if config.completion_promise:
                    completion_tag = config.completion_tag()
                    if completion_tag and completion_tag in response.output:
                        stop_reason = "completion_promise"
                        if await self._should_block_soft_stop(
                            config,
                            project_id,
                            stop_reason,
                            session.id,
                        ):
                            stop_reason = None
                        else:
                            break

                if config.max_cost_usd and session.cost_usd >= config.max_cost_usd:
                    stop_reason = "max_cost"
                    break
        finally:
            await self._close_adapter(adapter)

        finalized_session = await self._session_repo.get_by_id(session.id)
        if finalized_session is None:
            raise RuntimeError("Session not found during finalization")
        session = finalized_session

        session.end()
        loop_state = self._ensure_loop_state(session)
        loop_state["stop_reason"] = stop_reason
        if session.ended_at is None:
            raise RuntimeError("Session end timestamp missing")
        loop_state["ended_at"] = session.ended_at.isoformat()

        await self._session_repo.save(
            session,
            EventType.SESSION_ENDED,
            {"stop_reason": stop_reason},
            message="Loop ended",
        )

        return self._session_to_summary(session)

    async def _should_block_soft_stop(
        self,
        config: LoopConfig,
        project_id: str | None,
        stop_reason: str,
        session_id: str,
    ) -> bool:
        if not config.stop_when_goals_complete:
            return False
        blocked, guard_reason, guard_state = await self._evaluate_goal_guard(
            config,
            project_id,
        )
        if not blocked:
            return False
        await self._record_guard_block(
            session_id=session_id,
            stop_reason=stop_reason,
            guard_reason=guard_reason,
            guard_state=guard_state,
        )
        return True

    async def _evaluate_goal_guard(
        self,
        config: LoopConfig,
        project_id: str | None,
    ) -> tuple[bool, str, GoalGuardSnapshot]:
        if self._goal_service is None:
            return (
                True,
                "Goal guard enabled but GoalService is unavailable",
                {"error": "goal_service_missing"},
            )

        goals: list[Goal] = []
        missing_goals: list[str] = []

        if config.goal_ids:
            for goal_id in config.goal_ids:
                goal = await self._goal_service.get_goal(goal_id)
                if goal is None:
                    missing_goals.append(goal_id)
                else:
                    goals.append(goal)
        else:
            if not project_id:
                return (
                    True,
                    "Goal guard enabled but no project scope or goal IDs provided",
                    {"error": "missing_goal_scope"},
                )
            offset = 0
            limit = 200
            while True:
                result = await self._goal_service.list_goals(
                    project_id=project_id,
                    limit=limit,
                    offset=offset,
                )
                goals.extend(result.items)
                if not result.has_more:
                    break
                offset = result.offset + result.limit

        deduped = {goal.id: goal for goal in goals}
        goals = list(deduped.values())

        if not config.include_archived_goals:
            goals = [goal for goal in goals if goal.status != GoalStatus.ARCHIVED]

        incomplete = [goal for goal in goals if goal.status != GoalStatus.COMPLETED]

        blocked = False
        reasons = []

        if missing_goals:
            blocked = True
            reasons.append(f"Unknown goals: {', '.join(missing_goals)}")

        if not goals:
            if not config.allow_no_goals:
                blocked = True
                reasons.append("No goals found for the loop guard scope")
        elif incomplete:
            blocked = True
            names = ", ".join(goal.name for goal in incomplete[:5])
            suffix = "..." if len(incomplete) > 5 else ""
            reasons.append(f"{len(incomplete)} incomplete goal(s): {names}{suffix}")

        reason = "All goals are completed."
        if reasons:
            reason = " | ".join(reasons)

        guard_state: GoalGuardSnapshot = {
            "goal_ids": [goal.id for goal in goals],
            "missing_goals": missing_goals,
            "total_goals": len(goals),
            "completed_goals": len(goals) - len(incomplete),
            "incomplete_goals": len(incomplete),
            "include_archived_goals": config.include_archived_goals,
            "allow_no_goals": config.allow_no_goals,
        }

        return blocked, reason, guard_state

    async def _record_guard_block(
        self,
        session_id: str,
        stop_reason: str,
        guard_reason: str,
        guard_state: GoalGuardSnapshot,
    ) -> None:
        session = await self._session_repo.get_by_id(session_id)
        if session is None:
            return
        loop_state = self._ensure_loop_state(session)
        loop_state["stop_blocked_reason"] = guard_reason
        loop_state["stop_blocked_at"] = now_utc().isoformat()
        loop_state["stop_blocked_count"] = loop_state.get("stop_blocked_count", 0) + 1
        loop_state["stop_blocked_last_candidate"] = stop_reason
        loop_state["goal_guard"] = guard_state
        await self._session_repo.save(
            session,
            EventType.SESSION_UPDATED,
            {"stop_blocked": stop_reason},
            message="Stop blocked by goal guard",
        )

    async def cancel_loop(
        self, session_id: str, reason: str | None = None
    ) -> Session | None:
        session = await self._session_repo.get_by_id(session_id)
        if session is None:
            return None
        loop_state = self._ensure_loop_state(session)
        loop_state["cancel_requested"] = True
        loop_state["cancel_reason"] = reason or "cancelled"
        await self._session_repo.save(
            session,
            EventType.SESSION_UPDATED,
            {"cancel_requested": True},
            message="Loop cancel requested",
        )
        return session

    async def list_loops(
        self,
        project_id: str | None = None,
        include_ended: bool = False,
    ) -> list[LoopSummary]:
        sessions = await self._session_repo.list_sessions(project_id=project_id)
        loops = []
        for session in sessions:
            if not isinstance(session.state, dict):
                continue
            if "loop" not in session.state:
                continue
            if not include_ended and session.status != SessionStatus.ACTIVE:
                continue
            loops.append(self._session_to_summary(session))
        return loops

    async def get_loop(self, session_id: str) -> LoopSummary | None:
        session = await self._session_repo.get_by_id(session_id)
        if session is None:
            return None
        if not isinstance(session.state, dict) or "loop" not in session.state:
            return None
        return self._session_to_summary(session)

    async def get_loop_messages(self, session_id: str) -> list[ModelObject]:
        messages = await self._session_repo.get_messages(session_id)
        return [msg.to_dict() for msg in messages]

    def _build_adapters(self, config: LoopConfig) -> dict[str, LoopAdapter]:
        adapters: dict[str, LoopAdapter] = {}

        for name, adapter in self._adapters.items():
            adapters[name] = adapter

        if config.adapters:
            for name, adapter_cfg in config.adapters.items():
                if not adapter_cfg.enabled or name in adapters:
                    continue
                match adapter_cfg.type:
                    case "claude":
                        if self._coordinator_agent is None:
                            continue
                        adapters[name] = ClaudeLoopAdapter(
                            name,
                            adapter_cfg,
                            self._coordinator_agent,
                        )
                    case "codex":
                        adapters[name] = CodexLoopAdapter(name, adapter_cfg)
                    case "acp":
                        adapters[name] = ACPLoopAdapter(name, adapter_cfg)
                    case "general" | "command":
                        adapters[name] = CommandLoopAdapter(name, adapter_cfg)
                    case _:
                        adapters[name] = CommandLoopAdapter(name, adapter_cfg)

        if config.agent == "codex" and "codex" not in adapters:
            adapters["codex"] = CodexLoopAdapter(
                "codex",
                AdapterConfig(
                    name="codex",
                    type="codex",
                    agent_command="codex-acp",
                ),
            )

        if not config.adapters and self._coordinator_agent and "claude" not in adapters:
            adapters["claude"] = ClaudeLoopAdapter(
                "claude",
                AdapterConfig(name="claude", type="claude"),
                self._coordinator_agent,
            )

        return adapters

    def _resolve_adapter(
        self,
        config: LoopConfig,
        adapters: dict[str, LoopAdapter],
    ) -> LoopAdapter:
        if not adapters:
            raise ValueError("No adapters available for loop execution")

        if config.agent and config.agent != "auto":
            adapter = adapters.get(config.agent)
            if not adapter:
                raise ValueError(f"Unknown adapter: {config.agent}")
            if not adapter.available:
                raise ValueError(f"Adapter unavailable: {config.agent}")
            return adapter

        priority = config.agent_priority or list(adapters.keys())
        for name in priority:
            adapter = adapters.get(name)
            if adapter and adapter.available:
                return adapter

        raise ValueError("No available adapters found for auto selection")

    async def _execute_with_retries(
        self,
        adapter: LoopAdapter,
        prompt: str,
        retry_delay_seconds: float,
    ) -> LoopResponse:
        attempt = 0
        max_retries = adapter.config.max_retries
        response = await adapter.run(prompt)
        while not response.success and attempt < max_retries:
            attempt += 1
            await asyncio.sleep(retry_delay_seconds)
            response = await adapter.run(prompt)
        return response

    async def _get_loop_state(self, session_id: str) -> LoopStatePayload:
        session = await self._session_repo.get_by_id(session_id)
        if session is None:
            return {}
        return self._read_loop_state(session)

    async def _close_adapter(self, adapter: LoopAdapter) -> None:
        close = getattr(adapter, "close", None)
        if close is None or not callable(close):
            return
        result = close()
        if asyncio.iscoroutine(result):
            await result

    def _session_to_summary(self, session: Session) -> LoopSummary:
        loop_state = self._read_loop_state(session)
        return LoopSummary(
            session_id=session.id,
            agent=str(loop_state.get("agent", "unknown")),
            status=session.status.value
            if hasattr(session.status, "value")
            else str(session.status),
            iterations=int(loop_state.get("iterations", 0)),
            max_iterations=int(loop_state.get("max_iterations", 0)),
            max_runtime_seconds=int(loop_state.get("max_runtime_seconds", 0)),
            stop_reason=loop_state.get("stop_reason"),
            created_at=session.created_at,
            updated_at=session.updated_at,
            ended_at=session.ended_at,
            last_prompt=session.last_prompt,
            last_response_summary=session.last_response_summary,
        )

    @staticmethod
    def _ensure_loop_state(session: Session) -> LoopStatePayload:
        if session.state is None:
            session.state = {}
        loop_raw = session.state.get("loop")
        if isinstance(loop_raw, dict):
            return loop_raw
        loop_state: LoopStatePayload = {}
        session.state["loop"] = loop_state
        return loop_state

    @staticmethod
    def _read_loop_state(session: Session) -> LoopStatePayload:
        if not isinstance(session.state, dict):
            return {}
        loop_raw = session.state.get("loop")
        if isinstance(loop_raw, dict):
            return loop_raw
        return {}

    def _prepare_prompt(self, config: LoopConfig, prompt: str) -> str:
        completion_tag = config.completion_tag()
        if completion_tag and completion_tag not in prompt:
            return f"{prompt}\n\nCompletion signal:\n{completion_tag}\n"
        return prompt


def _summarize(text: str, limit: int = 400) -> str:
    if not text:
        return ""
    cleaned = text.strip().replace("\n", " ")
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit]}..."
