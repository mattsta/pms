"""Repository for managing state transitions across all entity types."""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pms.core.ids import EntityType, generate_id
from pms.models.base import now_utc
from pms.models.state_transition import (
    StateTransition,
    StateTransitionQuery,
    TransitionTimeline,
)

if TYPE_CHECKING:
    from pms.db.connection import Database


class StateTransitionRepository:
    """
    Universal repository for state transition tracking.

    Provides immutable time-series logging for state changes across
    all entity types (tasks, projects, products, workflows, etc.)
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    def _table_info(self, entity_type: str) -> tuple[str, str, bool]:
        """Get transition table, id column, and whether to filter by entity_type."""
        if entity_type == "task":
            return "task_state_transitions", "task_id", False
        return "state_transition_log", "entity_id", True

    async def record_transition(
        self,
        entity_type: str,
        entity_id: str,
        from_state: str | None,
        to_state: str,
        triggered_by: str = "system",
        reason: str | None = None,
        caused_by_event_id: str | None = None,
        correlation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> StateTransition:
        """
        Record a state transition (append-only).

        Args:
            entity_type: Type of entity (task, project, product, etc.)
            entity_id: ID of the entity
            from_state: Previous state (None for initial)
            to_state: New state
            triggered_by: Who/what triggered this transition
            reason: Human-readable explanation
            caused_by_event_id: Event that caused this transition
            correlation_id: Links related transitions
            metadata: Arbitrary context data

        Returns:
            The recorded StateTransition
        """
        now = now_utc()

        # Calculate duration in previous state
        duration_in_state_seconds = None
        if from_state:
            duration_in_state_seconds = await self._calculate_duration_in_state(
                entity_type, entity_id, from_state, now
            )

        transition = StateTransition(
            id=generate_id(EntityType.EVENT),
            entity_type=entity_type,
            entity_id=entity_id,
            from_state=from_state,
            to_state=to_state,
            timestamp=now,
            triggered_by=triggered_by,
            reason=reason,
            caused_by_event_id=caused_by_event_id,
            correlation_id=correlation_id,
            duration_in_state_seconds=duration_in_state_seconds,
            metadata=metadata or {},
        )

        if entity_type == "task":
            # Insert into task_state_transitions table
            await self.db.execute(
                """
                INSERT INTO task_state_transitions (
                    id, task_id, from_state, to_state, timestamp,
                    reason, triggered_by, duration_in_state_seconds, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    transition.id,
                    entity_id,  # Using task_id column for tasks
                    from_state,
                    to_state,
                    now.isoformat(),
                    reason,
                    triggered_by,
                    duration_in_state_seconds,
                    json.dumps(metadata or {}),
                ),
            )
        else:
            # Use universal state_transition_log for non-task entities
            await self.db.execute(
                """
                INSERT INTO state_transition_log (
                    id, entity_type, entity_id, workflow_id, from_state, to_state,
                    timestamp, reason, triggered_by, duration_in_state_seconds,
                    requires_approval, approved_by, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    transition.id,
                    entity_type,
                    entity_id,
                    None,
                    from_state,
                    to_state,
                    now.isoformat(),
                    reason,
                    triggered_by,
                    duration_in_state_seconds,
                    0,
                    None,
                    json.dumps(metadata or {}),
                ),
            )

        return transition

    async def get_transitions(
        self,
        query: StateTransitionQuery,
    ) -> list[StateTransition]:
        """
        Query state transitions with flexible filtering.

        Args:
            query: Query parameters

        Returns:
            List of matching transitions, ordered by timestamp DESC
        """
        table, id_column, use_entity_type = self._table_info(
            query.entity_type or "task"
        )
        sql = f"SELECT * FROM {table} WHERE 1=1"
        params: list[Any] = []

        if use_entity_type and query.entity_type:
            sql += " AND entity_type = ?"
            params.append(query.entity_type)

        if query.entity_id:
            sql += f" AND {id_column} = ?"
            params.append(query.entity_id)

        if query.from_state:
            sql += " AND from_state = ?"
            params.append(query.from_state)

        if query.to_state:
            sql += " AND to_state = ?"
            params.append(query.to_state)

        if query.triggered_by:
            sql += " AND triggered_by = ?"
            params.append(query.triggered_by)

        if query.start_time:
            sql += " AND timestamp >= ?"
            params.append(query.start_time.isoformat())

        if query.end_time:
            sql += " AND timestamp <= ?"
            params.append(query.end_time.isoformat())

        sql += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([query.limit, query.offset])

        rows = await self.db.fetch_all(sql, tuple(params))

        transitions = [self._row_to_transition(row) for row in rows]
        if query.transition_kind:
            transitions = [
                transition
                for transition in transitions
                if transition.metadata.get("transition_kind") == query.transition_kind
            ]

        return transitions

    async def get_last_transition_map(
        self,
        entity_type: str,
        entity_ids: list[str],
    ) -> dict[str, datetime | None]:
        """Get the most recent transition timestamp per entity."""
        if not entity_ids:
            return {}

        table, id_column, use_entity_type = self._table_info(entity_type)
        unique_ids = list(dict.fromkeys(entity_ids))
        placeholders = ", ".join("?" * len(unique_ids))
        sql = f"""
            SELECT {id_column} as entity_id, MAX(timestamp) as ts
            FROM {table}
            WHERE {id_column} IN ({placeholders})
        """
        params: list[Any] = list(unique_ids)
        if use_entity_type:
            sql += " AND entity_type = ?"
            params.append(entity_type)
        sql += f" GROUP BY {id_column}"

        rows = await self.db.fetch_all(sql, tuple(params))
        results: dict[str, datetime | None] = {
            entity_id: None for entity_id in unique_ids
        }
        for row in rows:
            ts_raw = row.get("ts")
            ts = datetime.fromisoformat(ts_raw) if ts_raw else None
            results[row["entity_id"]] = ts

        return results

    async def get_task_transitions_for_projects(
        self,
        project_ids: list[str],
        start_time: datetime | None,
        limit: int,
        *,
        kinds: list[str] | None = None,
    ) -> list[StateTransition]:
        """Get recent task transitions for a set of project IDs."""
        if not project_ids:
            return []
        entity_types = kinds or ["task_status", "task_workflow"]
        if not entity_types:
            return []

        project_placeholders = ", ".join("?" * len(project_ids))
        type_placeholders = ", ".join("?" * len(entity_types))
        params: list[Any] = [*entity_types, *project_ids]

        sql = f"""
            SELECT st.*
            FROM state_transition_log st
            JOIN tasks t ON t.id = st.entity_id
            WHERE st.entity_type IN ({type_placeholders})
              AND t.project_id IN ({project_placeholders})
        """
        if start_time:
            sql += " AND st.timestamp >= ?"
            params.append(start_time.isoformat())

        sql += " ORDER BY st.timestamp DESC LIMIT ?"
        params.append(limit)

        rows = await self.db.fetch_all(sql, tuple(params))
        return [self._row_to_transition(row) for row in rows]

    async def get_timeline(
        self,
        entity_type: str,
        entity_id: str,
        *,
        triggered_by: str | None = None,
        from_state: str | None = None,
        to_state: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        transition_kind: str | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> TransitionTimeline:
        """
        Get complete transition timeline for an entity.

        Calculates:
        - All transitions in chronological order
        - Total duration across all states
        - Time spent in each state
        """
        transitions = await self.get_transitions(
            StateTransitionQuery(
                entity_type=entity_type,
                entity_id=entity_id,
                from_state=from_state,
                to_state=to_state,
                triggered_by=triggered_by,
                transition_kind=transition_kind,
                start_time=start_time,
                end_time=end_time,
                limit=limit,
                offset=offset,
            )
        )

        return self._build_timeline(entity_type, entity_id, transitions)

    async def get_timeline_for_kind(
        self,
        entity_type: str,
        entity_id: str,
        *,
        kind: str,
        triggered_by: str | None = None,
        from_state: str | None = None,
        to_state: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        transition_kind: str | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> TransitionTimeline:
        """Get timeline for a workflow/status kind with merged sources."""
        secondary_type: str | None
        match kind:
            case "workflow":
                primary_type = entity_type
                secondary_type = f"{entity_type}_workflow"
            case "status":
                primary_type = f"{entity_type}_status"
                secondary_type = None
            case _:
                raise ValueError("Unsupported timeline kind")

        transitions = await self.get_transitions(
            StateTransitionQuery(
                entity_type=primary_type,
                entity_id=entity_id,
                from_state=from_state,
                to_state=to_state,
                triggered_by=triggered_by,
                transition_kind=transition_kind,
                start_time=start_time,
                end_time=end_time,
                limit=limit,
                offset=offset,
            )
        )

        if secondary_type and secondary_type != primary_type:
            secondary = await self.get_transitions(
                StateTransitionQuery(
                    entity_type=secondary_type,
                    entity_id=entity_id,
                    from_state=from_state,
                    to_state=to_state,
                    triggered_by=triggered_by,
                    transition_kind=transition_kind,
                    start_time=start_time,
                    end_time=end_time,
                    limit=limit,
                    offset=offset,
                )
            )
            transitions.extend(secondary)

        transitions.sort(key=lambda item: item.timestamp, reverse=True)
        return self._build_timeline(primary_type, entity_id, transitions)

    @staticmethod
    def _build_timeline(
        entity_type: str,
        entity_id: str,
        transitions: list[StateTransition],
    ) -> TransitionTimeline:
        transitions_chrono = list(reversed(transitions))

        state_durations: dict[str, int] = {}
        total_duration_seconds = 0

        for transition in transitions_chrono:
            if transition.duration_in_state_seconds and transition.from_state:
                current = state_durations.get(transition.from_state, 0)
                state_durations[transition.from_state] = (
                    current + transition.duration_in_state_seconds
                )
                total_duration_seconds += transition.duration_in_state_seconds

        return TransitionTimeline(
            entity_type=entity_type,
            entity_id=entity_id,
            transitions=transitions,
            total_duration_seconds=total_duration_seconds,
            state_durations=state_durations,
        )

    async def get_current_state_entry_time(
        self,
        entity_type: str,
        entity_id: str,
        current_state: str,
    ) -> datetime | None:
        """
        Get timestamp when entity entered its current state.

        Args:
            entity_type: Type of entity
            entity_id: ID of entity
            current_state: Current state to find entry time for

        Returns:
            Timestamp of last transition to current_state, or None
        """
        table, id_column, use_entity_type = self._table_info(entity_type)
        sql = f"""
            SELECT timestamp
            FROM {table}
            WHERE {id_column} = ? AND to_state = ?
        """
        params: list[Any] = [entity_id, current_state]
        if use_entity_type:
            sql += " AND entity_type = ?"
            params.append(entity_type)
        sql += " ORDER BY timestamp DESC LIMIT 1"

        row = await self.db.fetch_one(sql, tuple(params))

        if row:
            return datetime.fromisoformat(row["timestamp"])
        return None

    async def get_total_duration(
        self,
        entity_type: str,
        entity_id: str,
        from_first_active: bool = True,
    ) -> int | None:
        """
        Calculate total duration for an entity.

        Args:
            entity_type: Type of entity
            entity_id: ID of entity
            from_first_active: If True, calculate from first non-TODO state
                              If False, calculate from creation to completion

        Returns:
            Total seconds, or None if no transitions
        """
        table, id_column, use_entity_type = self._table_info(entity_type)

        if from_first_active:
            sql = f"""
                SELECT timestamp
                FROM {table}
                WHERE {id_column} = ? AND from_state = 'todo'
            """
        else:
            sql = f"""
                SELECT timestamp
                FROM {table}
                WHERE {id_column} = ?
            """
        params: list[Any] = [entity_id]
        if use_entity_type:
            sql += " AND entity_type = ?"
            params.append(entity_type)
        sql += " ORDER BY timestamp ASC LIMIT 1"

        first_row = await self.db.fetch_one(sql, tuple(params))

        # Get first terminal state transition
        terminal_sql = f"""
            SELECT timestamp
            FROM {table}
            WHERE {id_column} = ? AND to_state IN ('done', 'cancelled')
        """
        terminal_params: list[Any] = [entity_id]
        if use_entity_type:
            terminal_sql += " AND entity_type = ?"
            terminal_params.append(entity_type)
        terminal_sql += " ORDER BY timestamp ASC LIMIT 1"

        terminal_row = await self.db.fetch_one(terminal_sql, tuple(terminal_params))

        if first_row and terminal_row:
            first_time = datetime.fromisoformat(first_row["timestamp"])
            terminal_time = datetime.fromisoformat(terminal_row["timestamp"])
            delta = terminal_time - first_time
            return int(delta.total_seconds())

        return None

    async def get_state_duration(
        self,
        entity_type: str,
        entity_id: str,
        state: str,
    ) -> int:
        """
        Get total time spent in a specific state.

        Args:
            entity_type: Type of entity
            entity_id: ID of entity
            state: State to calculate duration for

        Returns:
            Total seconds spent in state (may be across multiple entries)
        """
        table, id_column, use_entity_type = self._table_info(entity_type)
        sql = f"""
            SELECT SUM(COALESCE(duration_in_state_seconds, 0)) as total_seconds
            FROM {table}
            WHERE {id_column} = ? AND from_state = ?
        """
        params: list[Any] = [entity_id, state]
        if use_entity_type:
            sql += " AND entity_type = ?"
            params.append(entity_type)

        row = await self.db.fetch_one(sql, tuple(params))

        if row and row["total_seconds"]:
            return int(row["total_seconds"])
        return 0

    async def get_transition_count(
        self,
        entity_type: str,
        entity_id: str,
    ) -> int:
        """Get total number of state transitions for an entity."""
        table, id_column, use_entity_type = self._table_info(entity_type)
        sql = f"""
            SELECT COUNT(*) as count
            FROM {table}
            WHERE {id_column} = ?
        """
        params: list[Any] = [entity_id]
        if use_entity_type:
            sql += " AND entity_type = ?"
            params.append(entity_type)

        row = await self.db.fetch_one(sql, tuple(params))

        if row:
            return int(row["count"])
        return 0

    async def get_reopen_count(
        self,
        entity_type: str,
        entity_id: str,
    ) -> int:
        """
        Get number of times entity was reopened.

        Returns count of transitions FROM terminal states back to active states.
        """
        table, id_column, use_entity_type = self._table_info(entity_type)
        sql = f"""
            SELECT COUNT(*) as count
            FROM {table}
            WHERE {id_column} = ?
            AND from_state IN ('done', 'cancelled')
            AND to_state NOT IN ('done', 'cancelled')
        """
        params: list[Any] = [entity_id]
        if use_entity_type:
            sql += " AND entity_type = ?"
            params.append(entity_type)

        row = await self.db.fetch_one(sql, tuple(params))

        if row:
            return int(row["count"])
        return 0

    async def _calculate_duration_in_state(
        self,
        entity_type: str,
        entity_id: str,
        from_state: str,
        current_time: datetime,
    ) -> int | None:
        """Calculate time spent in from_state."""
        # Get most recent transition TO from_state
        table, id_column, use_entity_type = self._table_info(entity_type)
        sql = f"""
            SELECT timestamp
            FROM {table}
            WHERE {id_column} = ? AND to_state = ?
        """
        params: list[Any] = [entity_id, from_state]
        if use_entity_type:
            sql += " AND entity_type = ?"
            params.append(entity_type)
        sql += " ORDER BY timestamp DESC LIMIT 1"

        row = await self.db.fetch_one(sql, tuple(params))

        if row:
            entry_time = datetime.fromisoformat(row["timestamp"])
            delta = current_time - entry_time
            return int(delta.total_seconds())

        return None

    def _row_to_transition(self, row: dict[str, Any]) -> StateTransition:
        """Convert database row to StateTransition."""
        metadata_raw = row.get("metadata", "{}")
        metadata = (
            json.loads(metadata_raw) if isinstance(metadata_raw, str) else metadata_raw
        )

        entity_type = row.get("entity_type") or "task"
        entity_id_raw = row.get("entity_id") or row.get("task_id")
        entity_id = str(entity_id_raw) if entity_id_raw is not None else ""

        return StateTransition(
            id=row["id"],
            entity_type=entity_type,
            entity_id=entity_id,
            from_state=row.get("from_state"),
            to_state=row["to_state"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            triggered_by=row.get("triggered_by", "system"),
            reason=row.get("reason"),
            caused_by_event_id=row.get("caused_by_event_id"),
            correlation_id=row.get("correlation_id"),
            duration_in_state_seconds=row.get("duration_in_state_seconds"),
            metadata=metadata,
        )
