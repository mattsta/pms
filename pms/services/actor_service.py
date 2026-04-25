"""Service for actor identity graph operations."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.models import (
    Actor,
    ActorAlias,
    ActorKind,
    ActorMembership,
    ActorMembershipRole,
    ActorStatus,
    Task,
    TaskStatus,
)
from pms.repositories import (
    ActorAliasRepository,
    ActorMembershipRepository,
    ActorRepository,
    TaskRepository,
)
from pms.repositories.base import QueryResult, RepositoryContext
from pms.repositories.state_transition_repository import StateTransitionRepository
from pms.services.rollup_utils import (
    fetch_grouped_max_timestamps,
    max_datetime,
    parse_timestamp,
    sort_items_by_bubbled_recency,
)

if TYPE_CHECKING:
    from pms.db.connection import Database


_HANDLE_INVALID_RE = re.compile(r"[^a-z0-9._/-]+")
_HANDLE_DUP_SEP_RE = re.compile(r"[-_/]{2,}")


def normalize_actor_handle(value: str) -> str:
    """Normalize a display name or handle to a stable actor handle."""
    normalized = value.strip().casefold()
    normalized = normalized.replace(" ", "-")
    normalized = _HANDLE_INVALID_RE.sub("-", normalized)
    normalized = _HANDLE_DUP_SEP_RE.sub("-", normalized)
    normalized = normalized.strip("-")
    return normalized


@dataclass
class ActorGraphSnapshot:
    """Resolved actor graph view for CLI/API surfaces."""

    actor: Actor
    last_activity_at: datetime | None = None
    last_transition_at: datetime | None = None
    aliases: list[ActorAlias] = field(default_factory=list)
    parent_memberships: list[ActorMembership] = field(default_factory=list)
    child_memberships: list[ActorMembership] = field(default_factory=list)
    assigned_tasks: QueryResult[Task] | None = None
    workload: ActorWorkloadSummary | None = None
    checked_out_tasks: QueryResult[Task] | None = None
    checkout_summary: ActorCheckoutRollup | None = None
    ownership: dict[str, Any] = field(default_factory=dict)
    project_workloads: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ActorTaskRollup:
    """Task-count rollup for an actor assignment population."""

    total_tasks: int = 0
    active_tasks: int = 0
    terminal_tasks: int = 0
    todo_tasks: int = 0
    in_progress_tasks: int = 0
    in_review_tasks: int = 0
    blocked_tasks: int = 0
    done_tasks: int = 0
    cancelled_tasks: int = 0

    def to_dict(self) -> dict[str, int]:
        """Serialize workload counts for machine-readable output."""
        return {
            "total_tasks": self.total_tasks,
            "active_tasks": self.active_tasks,
            "terminal_tasks": self.terminal_tasks,
            "todo_tasks": self.todo_tasks,
            "in_progress_tasks": self.in_progress_tasks,
            "in_review_tasks": self.in_review_tasks,
            "blocked_tasks": self.blocked_tasks,
            "done_tasks": self.done_tasks,
            "cancelled_tasks": self.cancelled_tasks,
        }

    @classmethod
    def from_dict(cls, data: dict[str, int]) -> ActorTaskRollup:
        """Build a rollup from repository counts."""
        return cls(**{field: int(data.get(field, 0)) for field in cls().__dict__})


@dataclass
class ActorWorkloadSummary:
    """Assignment rollups for direct and inherited actor workload."""

    direct: ActorTaskRollup = field(default_factory=ActorTaskRollup)
    effective: ActorTaskRollup = field(default_factory=ActorTaskRollup)
    inherited_only: ActorTaskRollup = field(default_factory=ActorTaskRollup)

    def to_dict(self) -> dict[str, dict[str, int]]:
        """Serialize workload summaries."""
        return {
            "direct": self.direct.to_dict(),
            "effective": self.effective.to_dict(),
            "inherited_only": self.inherited_only.to_dict(),
        }


@dataclass
class ActorCheckoutRollup:
    """Checkout lease rollup for a canonical actor."""

    total_checkouts: int = 0
    active_checkouts: int = 0
    expired_checkouts: int = 0
    distinct_agents: int = 0

    def to_dict(self) -> dict[str, int]:
        """Serialize checkout rollups."""
        return {
            "total_checkouts": self.total_checkouts,
            "active_checkouts": self.active_checkouts,
            "expired_checkouts": self.expired_checkouts,
            "distinct_agents": self.distinct_agents,
        }

    @classmethod
    def from_dict(cls, data: dict[str, int]) -> ActorCheckoutRollup:
        """Build a rollup from repository counts."""
        return cls(**{field: int(data.get(field, 0)) for field in cls().__dict__})


class ActorService:
    """Service for actor creation, graph traversal, and workload reads."""

    def __init__(
        self,
        db: Database,
        event_store: EventStore,
        revision_store: RevisionStore,
        metrics: MetricsCollector,
    ) -> None:
        self.db = db
        self.events = event_store
        self.revisions = revision_store
        self.metrics = metrics

        self._actor_repo = ActorRepository(db, event_store, revision_store, metrics)
        self._alias_repo = ActorAliasRepository(
            db, event_store, revision_store, metrics
        )
        self._membership_repo = ActorMembershipRepository(
            db, event_store, revision_store, metrics
        )
        self._task_repo = TaskRepository(db, event_store, revision_store, metrics)
        self._context = RepositoryContext()

    def with_context(
        self,
        user_id: str | None = None,
        session_id: str | None = None,
        correlation_id: str | None = None,
    ) -> ActorService:
        """Set context for subsequent operations."""
        self._context = RepositoryContext(
            user_id=user_id,
            session_id=session_id,
            correlation_id=correlation_id,
        )
        self._actor_repo.with_context(self._context)
        self._alias_repo.with_context(self._context)
        self._membership_repo.with_context(self._context)
        self._task_repo.with_context(self._context)
        return self

    async def create_actor(
        self,
        *,
        name: str,
        kind: ActorKind,
        handle: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Actor:
        """Create a canonical actor."""
        normalized_handle = normalize_actor_handle(handle or name)
        if not normalized_handle:
            raise ValueError("Actor handle cannot be empty after normalization")
        existing = await self._actor_repo.get_by_handle(normalized_handle)
        if existing is not None:
            raise ValueError(f"Actor handle '{normalized_handle}' already exists")

        async with self._actor_repo.db.transaction():
            actor = await self._actor_repo.create(
                kind=kind,
                name=name,
                handle=normalized_handle,
                description=description,
                tags=tags,
                metadata=metadata,
                message=f"Created actor '{name}'",
            )
            await self.metrics.record_counter(
                "actor.created",
                labels={"kind": kind.value},
            )
            await self.metrics.flush()
        return actor

    async def update_actor(
        self,
        actor_id: str,
        *,
        name: str | None = None,
        handle: str | None = None,
        description: str | None = None,
        status: ActorStatus | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Actor | None:
        """Update actor details."""
        normalized_handle = normalize_actor_handle(handle) if handle else None
        if normalized_handle:
            existing = await self._actor_repo.get_by_handle(normalized_handle)
            if existing is not None and existing.id != actor_id:
                raise ValueError(f"Actor handle '{normalized_handle}' already exists")
        async with self._actor_repo.db.transaction():
            actor = await self._actor_repo.update(
                actor_id,
                name=name,
                handle=normalized_handle,
                description=description,
                status=status,
                tags=tags,
                metadata=metadata,
            )
            if actor is not None:
                await self.metrics.record_counter("actor.updated")
                await self.metrics.flush()
        return actor

    async def archive_actor(self, actor_id: str) -> Actor | None:
        """Archive an actor."""
        async with self._actor_repo.db.transaction():
            actor = await self._actor_repo.archive(actor_id)
            if actor is not None:
                await self.metrics.record_counter("actor.archived")
                await self.metrics.flush()
        return actor

    async def get_actor(self, actor: str) -> Actor | None:
        """Resolve actor by id, handle, or alias."""
        resolved_actor = await self._actor_repo.get_by_id(actor)
        if resolved_actor is not None:
            return resolved_actor

        normalized_actor = normalize_actor_handle(actor)
        resolved_actor = await self._actor_repo.get_by_handle(normalized_actor or actor)
        if resolved_actor is not None:
            return resolved_actor

        alias = await self._alias_repo.get_by_alias(normalized_actor or actor)
        if alias is None:
            return None
        return await self._actor_repo.get_by_id(alias.actor_id)

    async def canonicalize_actor_reference(
        self,
        actor: str | None,
    ) -> tuple[str | None, str | None]:
        """Resolve an actor reference to canonical display value and actor id."""
        if actor is None:
            return None, None
        normalized = actor.strip()
        if not normalized:
            return None, None
        resolved_actor = await self.get_actor(normalized)
        if resolved_actor is None:
            return normalized, None
        return resolved_actor.handle, resolved_actor.id

    async def resolve_checkout_actor(
        self,
        *,
        agent_session_id: str,
        actor: str | None = None,
    ) -> Actor:
        """Resolve an explicit checkout actor or auto-create a runtime agent actor."""
        requested_actor = actor.strip() if actor else ""
        if requested_actor:
            resolved_actor = await self.get_actor(requested_actor)
            if resolved_actor is None:
                raise ValueError(f"Actor '{requested_actor}' not found")
            return resolved_actor

        existing_actor = await self.get_actor(agent_session_id)
        if existing_actor is not None:
            return existing_actor

        normalized_handle = normalize_actor_handle(agent_session_id)
        if not normalized_handle:
            raise ValueError(
                "Agent session id cannot be normalized into an actor handle"
            )

        try:
            return await self.create_actor(
                name=agent_session_id,
                kind=ActorKind.RUNTIME_AGENT,
                handle=normalized_handle,
                metadata={
                    "agent_session_id": agent_session_id,
                    "auto_created_for_checkout": True,
                },
            )
        except ValueError:
            resolved_actor = await self.get_actor(normalized_handle)
            if resolved_actor is None:
                raise
            return resolved_actor

    async def canonicalize_actor_references(
        self,
        actors: list[str] | tuple[str, ...] | None,
    ) -> tuple[list[str] | None, list[str]]:
        """Resolve a list of actor references to canonical values and actor ids."""
        if actors is None:
            return None, []

        canonical_refs: list[str] = []
        actor_ids: list[str] = []
        seen_refs: set[str] = set()
        seen_actor_ids: set[str] = set()

        for actor_key in actors:
            canonical_ref, actor_id = await self.canonicalize_actor_reference(actor_key)
            if canonical_ref and canonical_ref not in seen_refs:
                seen_refs.add(canonical_ref)
                canonical_refs.append(canonical_ref)
            if actor_id and actor_id not in seen_actor_ids:
                seen_actor_ids.add(actor_id)
                actor_ids.append(actor_id)

        return canonical_refs, actor_ids

    async def list_actors(
        self,
        *,
        kind: ActorKind | None = None,
        status: ActorStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Actor]:
        """List actors with filters."""
        initial_page = await self._actor_repo.list_filtered(
            kind=kind,
            status=status,
            limit=1,
            offset=0,
        )
        total_count = initial_page.total_count
        if total_count == 0:
            return QueryResult(items=[], total_count=0, offset=offset, limit=limit)

        full_page = await self._actor_repo.list_filtered(
            kind=kind,
            status=status,
            limit=total_count,
            offset=0,
        )
        actor_ids = [actor.id for actor in full_page.items]
        activity_map = await self.get_last_activity_map(actor_ids)
        transition_map = await self.get_last_transition_map(actor_ids)
        sorted_items = sort_items_by_bubbled_recency(
            full_page.items,
            activity_of=lambda actor: activity_map.get(actor.id),
            transition_of=lambda actor: transition_map.get(actor.id),
            updated_of=lambda actor: actor.updated_at,
            label_of=lambda actor: actor.handle,
            id_of=lambda actor: actor.id,
        )
        return QueryResult(
            items=sorted_items[offset : offset + limit],
            total_count=total_count,
            offset=offset,
            limit=limit,
        )

    async def _get_related_task_rollup_maps(
        self,
        actor_ids: list[str],
    ) -> tuple[dict[str, datetime | None], dict[str, datetime | None]]:
        """Return deep task-backed activity and transition maps keyed by actor id."""
        unique_ids = list(dict.fromkeys(actor_id for actor_id in actor_ids if actor_id))
        if not unique_ids:
            return {}, {}

        token_to_actor_ids: dict[str, set[str]] = {}
        for actor_id in unique_ids:
            tokens = await self.resolve_assignment_tokens(
                actor_id,
                include_inherited=True,
            )
            for token in tokens:
                token_to_actor_ids.setdefault(token, set()).add(actor_id)

        task_where: list[str] = []
        task_params: list[str] = []
        if token_to_actor_ids:
            token_placeholders = ", ".join("?" * len(token_to_actor_ids))
            task_where.append(
                f"(assignee IN ({token_placeholders}) "
                f"OR assignee_id IN ({token_placeholders}))"
            )
            token_values = list(token_to_actor_ids)
            task_params.extend(token_values)
            task_params.extend(token_values)

        checkout_placeholders = ", ".join("?" * len(unique_ids))
        task_where.append(f"checkout_actor_id IN ({checkout_placeholders})")
        task_params.extend(unique_ids)

        task_rows = await self.db.fetch_all(
            f"""
            SELECT id, assignee, assignee_id, checkout_actor_id
            FROM tasks
            WHERE {" OR ".join(task_where)}
            """,
            tuple(task_params),
        )

        activity_by_actor: dict[str, datetime | None] = {
            actor_id: None for actor_id in unique_ids
        }
        transition_by_actor: dict[str, datetime | None] = {
            actor_id: None for actor_id in unique_ids
        }
        if not task_rows:
            return activity_by_actor, transition_by_actor

        task_ids = [str(row["id"]) for row in task_rows]
        task_activity = await self._task_repo.get_last_activity_map(task_ids)
        task_transition = await self._task_repo.get_last_transition_map(task_ids)

        unique_actor_ids = set(unique_ids)
        for row in task_rows:
            matched_actor_ids: set[str] = set()
            for token_value in (row.get("assignee"), row.get("assignee_id")):
                if token_value:
                    matched_actor_ids.update(
                        token_to_actor_ids.get(str(token_value), set())
                    )
            checkout_actor_id = row.get("checkout_actor_id")
            if checkout_actor_id and str(checkout_actor_id) in unique_actor_ids:
                matched_actor_ids.add(str(checkout_actor_id))

            for actor_id in matched_actor_ids:
                activity_by_actor[actor_id] = max_datetime(
                    [
                        activity_by_actor.get(actor_id),
                        task_activity.get(str(row["id"])),
                    ]
                )
                transition_by_actor[actor_id] = max_datetime(
                    [
                        transition_by_actor.get(actor_id),
                        task_transition.get(str(row["id"])),
                    ]
                )

        return activity_by_actor, transition_by_actor

    async def get_last_activity_map(
        self,
        actor_ids: list[str],
    ) -> dict[str, datetime | None]:
        """Return deep activity timestamps keyed by actor id."""
        unique_ids = list(dict.fromkeys(actor_id for actor_id in actor_ids if actor_id))
        if not unique_ids:
            return {}

        placeholders = ", ".join("?" * len(unique_ids))
        params = tuple(unique_ids)
        activity_map: dict[str, datetime | None] = {
            actor_id: None for actor_id in unique_ids
        }

        actor_rows = await self.db.fetch_all(
            f"SELECT id, updated_at FROM actors WHERE id IN ({placeholders})",
            params,
        )
        for row in actor_rows:
            activity_map[str(row["id"])] = parse_timestamp(row.get("updated_at"))

        alias_activity = await fetch_grouped_max_timestamps(
            self.db,
            f"""
            SELECT actor_id, MAX(COALESCE(archived_at, updated_at, created_at)) as ts
            FROM actor_aliases
            WHERE actor_id IN ({placeholders})
            GROUP BY actor_id
            """,
            params,
            key_name="actor_id",
        )
        parent_membership_activity = await fetch_grouped_max_timestamps(
            self.db,
            f"""
            SELECT parent_actor_id as actor_id,
                   MAX(COALESCE(archived_at, updated_at, created_at)) as ts
            FROM actor_memberships
            WHERE parent_actor_id IN ({placeholders})
            GROUP BY parent_actor_id
            """,
            params,
            key_name="actor_id",
        )
        child_membership_activity = await fetch_grouped_max_timestamps(
            self.db,
            f"""
            SELECT member_actor_id as actor_id,
                   MAX(COALESCE(archived_at, updated_at, created_at)) as ts
            FROM actor_memberships
            WHERE member_actor_id IN ({placeholders})
            GROUP BY member_actor_id
            """,
            params,
            key_name="actor_id",
        )
        actor_field_activity = await fetch_grouped_max_timestamps(
            self.db,
            f"""
            SELECT entity_id as actor_id, MAX(updated_at) as ts
            FROM custom_field_values
            WHERE entity_type = 'actor' AND entity_id IN ({placeholders})
            GROUP BY entity_id
            """,
            params,
            key_name="actor_id",
        )
        actor_comment_activity = await fetch_grouped_max_timestamps(
            self.db,
            f"""
            SELECT entity_id as actor_id, MAX(updated_at) as ts
            FROM comments
            WHERE entity_type = 'actor' AND entity_id IN ({placeholders})
            GROUP BY entity_id
            """,
            params,
            key_name="actor_id",
        )
        actor_label_activity = await fetch_grouped_max_timestamps(
            self.db,
            f"""
            SELECT entity_id as actor_id,
                   MAX(COALESCE(archived_at, updated_at, created_at)) as ts
            FROM label_assignments
            WHERE entity_type = 'actor' AND entity_id IN ({placeholders})
            GROUP BY entity_id
            """,
            params,
            key_name="actor_id",
        )
        actor_watcher_activity = await fetch_grouped_max_timestamps(
            self.db,
            f"""
            SELECT entity_id as actor_id,
                   MAX(COALESCE(archived_at, updated_at, created_at)) as ts
            FROM entity_watchers
            WHERE entity_type = 'actor' AND entity_id IN ({placeholders})
            GROUP BY entity_id
            """,
            params,
            key_name="actor_id",
        )
        task_activity, task_transition = await self._get_related_task_rollup_maps(
            unique_ids
        )

        for actor_id in unique_ids:
            activity_map[actor_id] = max_datetime(
                [
                    activity_map.get(actor_id),
                    alias_activity.get(actor_id),
                    parent_membership_activity.get(actor_id),
                    child_membership_activity.get(actor_id),
                    actor_field_activity.get(actor_id),
                    actor_comment_activity.get(actor_id),
                    actor_label_activity.get(actor_id),
                    actor_watcher_activity.get(actor_id),
                    task_activity.get(actor_id),
                    task_transition.get(actor_id),
                ]
            )

        return activity_map

    async def get_last_transition_map(
        self,
        actor_ids: list[str],
    ) -> dict[str, datetime | None]:
        """Return deep transition timestamps keyed by actor id."""
        unique_ids = list(dict.fromkeys(actor_id for actor_id in actor_ids if actor_id))
        if not unique_ids:
            return {}

        state_repo = StateTransitionRepository(self.db)
        actor_status = await state_repo.get_last_transition_map(
            "actor_status",
            unique_ids,
        )
        _, task_transition = await self._get_related_task_rollup_maps(unique_ids)

        transition_map: dict[str, datetime | None] = {
            actor_id: None for actor_id in unique_ids
        }
        for actor_id in unique_ids:
            transition_map[actor_id] = max_datetime(
                [
                    actor_status.get(actor_id),
                    task_transition.get(actor_id),
                ]
            )

        return transition_map

    async def add_alias(self, actor: str, alias: str) -> ActorAlias:
        """Add an alias for an actor."""
        resolved_actor = await self.get_actor(actor)
        if resolved_actor is None:
            raise ValueError(f"Actor '{actor}' not found")
        normalized_alias = normalize_actor_handle(alias)
        if not normalized_alias:
            raise ValueError("Alias cannot be empty after normalization")
        if normalized_alias == resolved_actor.handle.casefold():
            raise ValueError("Alias duplicates the actor handle")
        existing_alias = await self._alias_repo.get_by_alias(normalized_alias)
        if existing_alias is not None:
            if existing_alias.actor_id != resolved_actor.id:
                raise ValueError(f"Alias '{normalized_alias}' already exists")
            return existing_alias
        async with self._alias_repo.db.transaction():
            alias_model = await self._alias_repo.create(
                actor_id=resolved_actor.id,
                alias=alias,
                normalized_alias=normalized_alias,
            )
            await self.metrics.record_counter("actor.alias.created")
            await self.metrics.flush()
        return alias_model

    async def list_aliases(self, actor: str) -> list[ActorAlias]:
        """List aliases for an actor."""
        resolved_actor = await self.get_actor(actor)
        if resolved_actor is None:
            return []
        return await self._alias_repo.list_by_actor(resolved_actor.id)

    async def add_membership(
        self,
        *,
        parent_actor: str,
        member_actor: str,
        role: ActorMembershipRole = ActorMembershipRole.MEMBER,
    ) -> ActorMembership:
        """Add a membership edge to the actor graph."""
        parent = await self.get_actor(parent_actor)
        if parent is None:
            raise ValueError(f"Actor '{parent_actor}' not found")
        member = await self.get_actor(member_actor)
        if member is None:
            raise ValueError(f"Actor '{member_actor}' not found")
        if parent.id == member.id:
            raise ValueError("Actor cannot be a member of itself")

        existing = await self._membership_repo.list_by_parent(parent.id)
        for membership in existing:
            if membership.member_actor_id == member.id and membership.role == role:
                return membership

        async with self._membership_repo.db.transaction():
            model = await self._membership_repo.create(
                parent_actor_id=parent.id,
                member_actor_id=member.id,
                role=role,
            )
            await self.metrics.record_counter(
                "actor.membership.created",
                labels={"role": role.value},
            )
            await self.metrics.flush()
        return model

    async def list_parent_memberships(self, actor: str) -> list[ActorMembership]:
        """List memberships where the actor is the member."""
        resolved_actor = await self.get_actor(actor)
        if resolved_actor is None:
            return []
        return await self._membership_repo.list_by_member(resolved_actor.id)

    async def list_child_memberships(self, actor: str) -> list[ActorMembership]:
        """List memberships where the actor is the parent/group."""
        resolved_actor = await self.get_actor(actor)
        if resolved_actor is None:
            return []
        return await self._membership_repo.list_by_parent(resolved_actor.id)

    async def resolve_assignment_tokens(
        self,
        actor: str,
        *,
        include_inherited: bool = True,
    ) -> list[str]:
        """Resolve assignee strings that should map to an actor."""
        resolved_actor = await self.get_actor(actor)
        if resolved_actor is None:
            raise ValueError(f"Actor '{actor}' not found")

        tokens: set[str] = {
            resolved_actor.id,
            resolved_actor.handle,
            resolved_actor.name,
        }
        aliases = await self._alias_repo.list_by_actor(resolved_actor.id)
        tokens.update(alias.alias for alias in aliases)
        tokens.update(alias.normalized_alias for alias in aliases)

        if include_inherited:
            seen: set[str] = {resolved_actor.id}
            queue = [resolved_actor.id]
            while queue:
                member_id = queue.pop(0)
                memberships = await self._membership_repo.list_by_member(member_id)
                for membership in memberships:
                    parent_id = membership.parent_actor_id
                    if parent_id in seen:
                        continue
                    seen.add(parent_id)
                    queue.append(parent_id)
                    parent = await self._actor_repo.get_by_id(parent_id)
                    if parent is None:
                        continue
                    tokens.update({parent.id, parent.handle, parent.name})
                    parent_aliases = await self._alias_repo.list_by_actor(parent.id)
                    tokens.update(alias.alias for alias in parent_aliases)
                    tokens.update(alias.normalized_alias for alias in parent_aliases)

        return sorted(token for token in tokens if token)

    async def list_assigned_tasks(
        self,
        actor: str,
        *,
        include_inherited: bool = True,
        project_id: str | None = None,
        status: TaskStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Task]:
        """List tasks assigned to an actor via direct or inherited tokens."""
        tokens = await self.resolve_assignment_tokens(
            actor,
            include_inherited=include_inherited,
        )
        if project_id:
            result = await self._task_repo.get_by_project(
                project_id,
                status=status,
                limit=limit,
                offset=offset,
                assignee_any=tokens,
            )
        else:
            result = await self._task_repo.get_all(
                limit=limit,
                offset=offset,
                status=status,
                assignee_any=tokens,
            )
        return result

    async def get_workload_summary(
        self,
        actor: str,
        *,
        include_inherited: bool = True,
        project_id: str | None = None,
    ) -> ActorWorkloadSummary:
        """Return direct and inherited workload rollups for an actor."""
        direct_tokens = await self.resolve_assignment_tokens(
            actor,
            include_inherited=False,
        )
        effective_tokens = (
            await self.resolve_assignment_tokens(actor, include_inherited=True)
            if include_inherited
            else list(direct_tokens)
        )
        direct_rollup = ActorTaskRollup.from_dict(
            await self._task_repo.get_assignment_rollup(
                assignee_any=direct_tokens,
                project_id=project_id,
            )
        )
        effective_rollup = ActorTaskRollup.from_dict(
            await self._task_repo.get_assignment_rollup(
                assignee_any=effective_tokens,
                project_id=project_id,
            )
        )
        inherited_rollup = ActorTaskRollup(
            **{
                field: max(
                    0,
                    getattr(effective_rollup, field) - getattr(direct_rollup, field),
                )
                for field in direct_rollup.__dict__
            }
        )
        return ActorWorkloadSummary(
            direct=direct_rollup,
            effective=effective_rollup,
            inherited_only=inherited_rollup,
        )

    async def list_checked_out_tasks(
        self,
        actor: str,
        *,
        include_expired: bool = True,
        project_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Task]:
        """List tasks currently leased by a canonical checkout actor."""
        resolved_actor = await self.get_actor(actor)
        if resolved_actor is None:
            return QueryResult(items=[], total_count=0, offset=offset, limit=limit)
        return await self._task_repo.get_checkouts_by_actor(
            checkout_actor_ids=[resolved_actor.id],
            project_id=project_id,
            include_expired=include_expired,
            limit=limit,
            offset=offset,
        )

    async def get_checkout_summary(
        self,
        actor: str,
        *,
        include_expired: bool = True,
        project_id: str | None = None,
    ) -> ActorCheckoutRollup:
        """Return checkout lease rollups for a canonical actor."""
        resolved_actor = await self.get_actor(actor)
        if resolved_actor is None:
            return ActorCheckoutRollup()
        return ActorCheckoutRollup.from_dict(
            await self._task_repo.get_checkout_rollup(
                checkout_actor_ids=[resolved_actor.id],
                project_id=project_id,
                include_expired=include_expired,
            )
        )

    async def get_project_workloads(
        self,
        actor: str,
        *,
        include_inherited: bool = True,
        include_expired_checkouts: bool = True,
    ) -> list[dict[str, Any]]:
        """Return workload and checkout rollups grouped by project for an actor."""
        resolved_actor = await self.get_actor(actor)
        if resolved_actor is None:
            return []

        direct_tokens = await self.resolve_assignment_tokens(
            resolved_actor.id,
            include_inherited=False,
        )
        effective_tokens = (
            await self.resolve_assignment_tokens(
                resolved_actor.id,
                include_inherited=True,
            )
            if include_inherited
            else list(direct_tokens)
        )

        direct_rows = await self._task_repo.get_assignment_rollup_by_project(
            assignee_any=direct_tokens,
        )
        effective_rows = await self._task_repo.get_assignment_rollup_by_project(
            assignee_any=effective_tokens,
        )
        checkout_rows = await self._task_repo.get_checkout_rollup_by_project(
            checkout_actor_ids=[resolved_actor.id],
            include_expired=include_expired_checkouts,
        )

        direct_map = {
            str(row["project_id"]): ActorTaskRollup.from_dict(row)
            for row in direct_rows
            if row.get("project_id")
        }
        effective_map = {
            str(row["project_id"]): ActorTaskRollup.from_dict(row)
            for row in effective_rows
            if row.get("project_id")
        }
        checkout_map = {
            str(row["project_id"]): ActorCheckoutRollup.from_dict(row)
            for row in checkout_rows
            if row.get("project_id")
        }
        project_ids = sorted(set(direct_map) | set(effective_map) | set(checkout_map))
        if not project_ids:
            return []

        placeholders = ", ".join("?" * len(project_ids))
        project_rows = await self.db.fetch_all(
            f"""
            SELECT id, name, status
            FROM projects
            WHERE id IN ({placeholders})
            """,
            tuple(project_ids),
        )
        project_map = {
            str(row["id"]): {
                "name": row["name"],
                "status": row["status"],
            }
            for row in project_rows
        }

        workloads: list[dict[str, Any]] = []
        for project_id in project_ids:
            direct_rollup = direct_map.get(project_id, ActorTaskRollup())
            effective_rollup = effective_map.get(project_id, ActorTaskRollup())
            inherited_rollup = ActorTaskRollup(
                **{
                    field: max(
                        0,
                        getattr(effective_rollup, field)
                        - getattr(direct_rollup, field),
                    )
                    for field in direct_rollup.__dict__
                }
            )
            checkout_rollup = checkout_map.get(project_id, ActorCheckoutRollup())
            workloads.append(
                {
                    "project_id": project_id,
                    "project_name": project_map.get(project_id, {}).get("name"),
                    "project_status": project_map.get(project_id, {}).get("status"),
                    "direct": direct_rollup.to_dict(),
                    "effective": effective_rollup.to_dict(),
                    "inherited_only": inherited_rollup.to_dict(),
                    "checkouts": checkout_rollup.to_dict(),
                }
            )

        workloads.sort(
            key=lambda item: (
                -int(item["effective"]["active_tasks"]),
                -int(item["effective"]["total_tasks"]),
                -int(item["checkouts"]["active_checkouts"]),
                str(item.get("project_name") or item["project_id"]),
            )
        )
        return workloads

    async def get_ownership_summary(
        self,
        actor: str,
        *,
        limit_per_type: int = 5,
    ) -> dict[str, Any]:
        """Return owned strategic and management entities for an actor."""
        resolved_actor = await self.get_actor(actor)
        if resolved_actor is None:
            return {"counts": {"total_owned": 0}, "items": {}}

        specs = (
            ("goals", "goals", "name", "status"),
            ("objectives", "objectives", "name", "status"),
            ("key_results", "key_results", "name", "status"),
            ("products", "products", "name", "status"),
            ("organizations", "organizations", "name", "status"),
            ("teams", "teams", "name", "status"),
            ("portfolios", "portfolios", "name", "status"),
            ("programs", "programs", "name", "status"),
            ("queues", "saved_searches", "name", None),
        )

        counts: dict[str, int] = {}
        items: dict[str, list[dict[str, Any]]] = {}
        total_owned = 0

        for label, table_name, name_column, status_column in specs:
            count_row = await self.db.fetch_one(
                f"SELECT COUNT(*) AS count FROM {table_name} WHERE owner_id = ?",
                (resolved_actor.id,),
            )
            count = int(count_row["count"] or 0) if count_row else 0
            counts[label] = count
            total_owned += count

            if status_column is None:
                rows = await self.db.fetch_all(
                    f"""
                    SELECT
                        id,
                        {name_column} AS name,
                        CASE
                            WHEN archived_at IS NULL THEN 'active'
                            ELSE 'archived'
                        END AS status
                    FROM {table_name}
                    WHERE owner_id = ?
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (resolved_actor.id, limit_per_type),
                )
            else:
                rows = await self.db.fetch_all(
                    f"""
                    SELECT
                        id,
                        {name_column} AS name,
                        {status_column} AS status
                    FROM {table_name}
                    WHERE owner_id = ?
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (resolved_actor.id, limit_per_type),
                )

            items[label] = [
                {
                    "id": row["id"],
                    "name": row["name"],
                    "status": row.get("status"),
                }
                for row in rows
            ]

        counts["total_owned"] = total_owned
        return {"counts": counts, "items": items}

    async def get_actor_graph(
        self,
        actor: str,
        *,
        include_inherited: bool = True,
        task_limit: int = 25,
    ) -> ActorGraphSnapshot | None:
        """Resolve actor graph details for operator surfaces."""
        resolved_actor = await self.get_actor(actor)
        if resolved_actor is None:
            return None
        aliases = await self._alias_repo.list_by_actor(resolved_actor.id)
        parent_memberships = await self._membership_repo.list_by_member(
            resolved_actor.id
        )
        child_memberships = await self._membership_repo.list_by_parent(
            resolved_actor.id
        )
        assigned_tasks = await self.list_assigned_tasks(
            resolved_actor.id,
            include_inherited=include_inherited,
            limit=task_limit,
            offset=0,
        )
        workload = await self.get_workload_summary(
            resolved_actor.id,
            include_inherited=include_inherited,
        )
        checked_out_tasks = await self.list_checked_out_tasks(
            resolved_actor.id,
            include_expired=True,
            limit=task_limit,
            offset=0,
        )
        checkout_summary = await self.get_checkout_summary(
            resolved_actor.id,
            include_expired=True,
        )
        ownership = await self.get_ownership_summary(resolved_actor.id)
        project_workloads = await self.get_project_workloads(
            resolved_actor.id,
            include_inherited=include_inherited,
            include_expired_checkouts=True,
        )
        last_activity = (await self.get_last_activity_map([resolved_actor.id])).get(
            resolved_actor.id
        )
        last_transition = (await self.get_last_transition_map([resolved_actor.id])).get(
            resolved_actor.id
        )
        return ActorGraphSnapshot(
            actor=resolved_actor,
            last_activity_at=last_activity,
            last_transition_at=last_transition,
            aliases=aliases,
            parent_memberships=parent_memberships,
            child_memberships=child_memberships,
            assigned_tasks=assigned_tasks,
            workload=workload,
            checked_out_tasks=checked_out_tasks,
            checkout_summary=checkout_summary,
            ownership=ownership,
            project_workloads=project_workloads,
        )
