"""Session repository for agent conversation persistence."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import TYPE_CHECKING, Any

from loguru import logger

from pms.core import EventType
from pms.exceptions import NotFoundError
from pms.models.enums import SessionStatus
from pms.models.session import Session, SessionMessage
from pms.repositories.base import EventSourcedRepository, RepositoryContext

if TYPE_CHECKING:
    from pms.core import EventStore, MetricsCollector, RevisionStore
    from pms.db.connection import Database


class SessionRepository(EventSourcedRepository[Session]):
    """Repository for agent session persistence with event sourcing."""

    def __init__(
        self,
        db: Database,
        event_store: EventStore,
        revision_store: RevisionStore,
        metrics: MetricsCollector,
    ):
        super().__init__(db, event_store, revision_store, metrics)

    @property
    def entity_type(self) -> str:
        return "session"

    @property
    def table_name(self) -> str:
        return "sessions"

    async def create(
        self,
        project_id: str | None = None,
        context_summary: str | None = None,
        initial_prompt: str | None = None,
        context: RepositoryContext | None = None,
    ) -> Session:
        """Create a new agent session."""
        session = Session(
            project_id=project_id,
            status=SessionStatus.ACTIVE,
            context_summary=context_summary,
        )

        await self.save(
            session,
            EventType.SESSION_STARTED,
            {
                "project_id": project_id,
                "initial_prompt": initial_prompt,
            },
        )

        logger.info("Session created: {}", session.id)
        return session

    async def create_loop_session(
        self,
        *,
        project_id: str | None = None,
        context_summary: str = "agent_loop",
        initial_prompt: str,
        loop_state: dict[str, Any],
    ) -> Session:
        """Create a session and seed loop state in one atomic unit."""
        session = Session(
            project_id=project_id,
            status=SessionStatus.ACTIVE,
            context_summary=context_summary,
        )
        session.state = {"loop": deepcopy(loop_state)}
        session.last_prompt = initial_prompt

        async def _create() -> Session:
            await self._save_in_transaction(
                model=session,
                event_type=EventType.SESSION_STARTED,
                payload={
                    "project_id": project_id,
                    "initial_prompt": initial_prompt,
                },
                message="Session started",
            )
            await self._save_in_transaction(
                model=session,
                event_type=EventType.SESSION_UPDATED,
                payload={"loop_started": deepcopy(loop_state)},
                message="Started agent loop",
            )
            return session

        await self._run_in_owned_transaction(
            _create,
            operation_name="create_loop_session",
        )

        logger.info("Loop session created: {}", session.id)
        return session

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        tokens: int | None = None,
        cost: float | None = None,
        metadata: dict[str, Any] | None = None,
        context: RepositoryContext | None = None,
    ) -> SessionMessage:
        """Add message to session conversation history."""
        message = SessionMessage(
            session_id=session_id,
            role=role,
            content=content,
            tokens=tokens,
            cost_usd=cost,
            metadata=metadata or {},
        )

        async def _persist_message() -> SessionMessage:
            # Persist the transcript row and session rollup together so a late
            # failure cannot leave conversation history ahead of session state.
            await self.db.execute(
                """
                INSERT INTO session_messages (
                    id, session_id, role, content, tokens, cost_usd, timestamp, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message.id,
                    message.session_id,
                    message.role,
                    message.content,
                    message.tokens,
                    message.cost_usd,
                    message.timestamp.isoformat(),
                    json.dumps(message.metadata),
                ),
            )

            session = await self.get_by_id(session_id)
            if session:
                session.message_count += 1
                await self._save_in_transaction(
                    model=session,
                    event_type=EventType.SESSION_UPDATED,
                    payload={"message_added": message.id},
                )

            return message

        await self._run_in_owned_transaction(
            _persist_message,
            operation_name="add_message",
        )

        return message

    async def get_messages(self, session_id: str) -> list[SessionMessage]:
        """Get all messages for a session."""
        rows = await self.db.fetch_all(
            """
            SELECT * FROM session_messages
            WHERE session_id = ?
            ORDER BY timestamp
            """,
            (session_id,),
        )

        return [
            SessionMessage(
                id=row["id"],
                session_id=row["session_id"],
                role=row["role"],
                content=row["content"],
                tokens=row.get("tokens"),
                cost_usd=row.get("cost_usd"),
                metadata=json.loads(row["metadata"]) if row.get("metadata") else {},
            )
            for row in rows
        ]

    async def update_costs(
        self,
        session_id: str,
        tokens: int,
        cost: float,
        context: RepositoryContext | None = None,
    ) -> Session:
        """Update session token usage and cost."""
        session = await self.get_by_id(session_id)
        if not session:
            raise NotFoundError(session_id, f"Session {session_id} not found")

        session.token_count += tokens
        session.cost_usd += cost

        await self.save(
            session,
            EventType.SESSION_UPDATED,
            {
                "cost_update": {
                    "tokens": tokens,
                    "cost": cost,
                }
            },
        )

        return session

    async def end_session(
        self,
        session_id: str,
        context: RepositoryContext | None = None,
    ) -> Session:
        """End an active session."""
        session = await self.get_by_id(session_id)
        if not session:
            raise NotFoundError(session_id, f"Session {session_id} not found")

        session.status = SessionStatus.ENDED

        await self.save(
            session,
            EventType.SESSION_ENDED,
            {},
        )

        logger.info(
            "Session ended: {} (tokens: {}, cost: ${})",
            session.id,
            session.token_count,
            session.cost_usd,
        )
        return session

    async def get_active_sessions(self, project_id: str | None = None) -> list[Session]:
        """Get all active sessions."""
        # Get all sessions and filter in Python since status is in JSON state column
        query = "SELECT * FROM sessions"
        params: tuple[str, ...] = ()

        if project_id:
            query += " WHERE project_id = ?"
            params = (project_id,)

        query += " ORDER BY created_at DESC"

        rows = await self.db.fetch_all(query, params)
        sessions = [self._row_to_entity(row) for row in rows]

        # Filter to active only
        return [s for s in sessions if s.status == SessionStatus.ACTIVE]

    async def list_sessions(self, project_id: str | None = None) -> list[Session]:
        """List sessions ordered by creation time."""
        query = "SELECT * FROM sessions"
        params: tuple[str, ...] = ()

        if project_id:
            query += " WHERE project_id = ?"
            params = (project_id,)

        query += " ORDER BY created_at DESC"
        rows = await self.db.fetch_all(query, params)
        return [self._row_to_entity(row) for row in rows]

    async def _apply_events(self, events: list[Any]) -> Session | None:
        """Apply events to rebuild session state."""
        if not events:
            return None

        session = None
        for event in events:
            event_type = EventType(event["event_type"])
            data = event.get("event_data", {})

            match event_type:
                case EventType.SESSION_STARTED:
                    # Create initial session
                    payload = event.get("payload", {})
                    session = Session(
                        id=event.get("aggregate_id"),
                        project_id=payload.get("project_id"),
                        status=SessionStatus.ACTIVE,
                    )
                case EventType.SESSION_UPDATED if session and "cost_update" in data:
                    cost_data = data["cost_update"]
                    session.token_count += cost_data["tokens"]
                    session.cost_usd += cost_data["cost"]
                case EventType.SESSION_ENDED if session:
                    session.status = SessionStatus.ENDED
                case _:
                    pass

        return session

    def _model_from_row(self, row: dict[str, Any]) -> Session:
        """Convert database row to Session entity."""
        data = dict(row)
        # Extract status from state JSON if it exists
        if "state" in data and data["state"]:
            state = (
                json.loads(data["state"])
                if isinstance(data["state"], str)
                else data["state"]
            )
            data["status"] = state.get("status", "active")
            data["cost_usd"] = state.get("cost_usd", 0.0)
            data["token_count"] = state.get("token_count", 0)
            data["message_count"] = state.get(
                "message_count", data.get("message_count", 0)
            )
            data["state"] = state
        return Session.from_dict(data)

    def _row_from_model(self, entity: Session) -> dict[str, Any]:
        """Convert Session entity to database row."""
        return entity.to_dict()

    def _row_to_entity(self, row: dict[str, Any]) -> Session:
        """Convert database row to Session entity."""
        return self._model_from_row(row)

    def _entity_to_row(self, entity: Session) -> dict[str, Any]:
        """Convert Session entity to database row."""
        return entity.to_dict()

    async def _update_projection(
        self, entity: Session, is_create: bool = False
    ) -> None:
        """Update sessions projection table."""
        data = self._entity_to_row(entity)
        state = dict(data.get("state") or {})
        state.update(
            {
                "status": data.get("status"),
                "cost_usd": data.get("cost_usd", 0.0),
                "token_count": data.get("token_count", 0),
                "message_count": data.get("message_count", 0),
            }
        )

        await self.db.execute(
            """
            INSERT INTO sessions (
                id, project_id, claude_session_id, context_summary,
                last_prompt, last_response_summary, state,
                cost_usd, token_count, message_count,
                created_at, updated_at, ended_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                project_id = excluded.project_id,
                claude_session_id = excluded.claude_session_id,
                context_summary = excluded.context_summary,
                last_prompt = excluded.last_prompt,
                last_response_summary = excluded.last_response_summary,
                state = excluded.state,
                cost_usd = excluded.cost_usd,
                token_count = excluded.token_count,
                message_count = excluded.message_count,
                updated_at = excluded.updated_at,
                ended_at = excluded.ended_at
            """,
            (
                data["id"],
                data.get("project_id"),
                data.get("claude_session_id"),
                data.get("context_summary"),
                data.get("last_prompt"),
                data.get("last_response_summary"),
                json.dumps(state),
                data.get("cost_usd", 0.0),
                data.get("token_count", 0),
                data.get("message_count", 0),
                data["created_at"],
                data["updated_at"],
                data.get("ended_at"),
            ),
        )
