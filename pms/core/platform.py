"""Platform Integration - Unified access to all PMS subsystems.

The Platform provides a single entry point for:
- Cross-system operations
- Unified event emission
- Coordinated state management
- System-wide configuration

Architecture:
    ┌───────────────────────────────────────────────────────────────────┐
    │                         Platform                                   │
    │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐    │
    │  │Services │ │Automati-│ │ Memory  │ │Learning │ │  Core   │    │
    │  │         │ │  on     │ │         │ │         │ │         │    │
    │  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘    │
    │       │           │           │           │           │          │
    │       └───────────┴───────────┴───────────┴───────────┘          │
    │                              │                                    │
    │                    ┌─────────┴─────────┐                         │
    │                    │  Unified Events   │                         │
    │                    │  Cross-references │                         │
    │                    │  State Management │                         │
    │                    └───────────────────┘                         │
    └───────────────────────────────────────────────────────────────────┘

Usage:
    from pms.core import get_platform

    platform = get_platform()

    # Emit events that trigger automation and learning
    await platform.emit_task_completed(task_id, project_id)

    # Cross-system queries
    related = await platform.get_related_entities(task_id)

    # Coordinated operations
    await platform.execute_workflow("deploy", inputs={"env": "prod"})
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pms.core.ids import EntityType, get_entity_type
from pms.core.refs import Reference, ReferenceStore, ReferenceType, get_reference_store
from pms.core.registry import EntityInfo, EntityRegistry, get_entity_registry

if TYPE_CHECKING:
    from pms.automation import EventBus, TriggerManager, WorkflowEngine
    from pms.learning import LearningEngine
    from pms.memory import ContextManager, FeedbackStore, KnowledgeStore, PatternMatcher

logger = logging.getLogger(__name__)


@dataclass
class PlatformConfig:
    """Configuration for the platform.

    Attributes:
        data_dir: Base directory for data storage
        enable_learning: Whether to enable learning from operations
        enable_events: Whether to emit events
        enable_references: Whether to track cross-references
        auto_persist: Whether to auto-save changes
    """

    data_dir: Path = field(default_factory=lambda: Path.home() / ".pms")
    enable_learning: bool = True
    enable_events: bool = True
    enable_references: bool = True
    auto_persist: bool = True

    def ensure_dirs(self) -> None:
        """Ensure data directories exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "knowledge").mkdir(exist_ok=True)
        (self.data_dir / "feedback").mkdir(exist_ok=True)
        (self.data_dir / "references").mkdir(exist_ok=True)
        (self.data_dir / "registry").mkdir(exist_ok=True)


class Platform:
    """Unified platform integrating all PMS subsystems.

    Provides:
    - Coordinated access to all services
    - Cross-system event propagation
    - Automatic reference tracking
    - Learning from all operations
    """

    def __init__(self, config: PlatformConfig | None = None):
        """Initialize platform.

        Args:
            config: Platform configuration
        """
        self.config = config or PlatformConfig()

        # Core components (always available)
        self._registry = get_entity_registry()
        self._references = get_reference_store()

        # Optional components (lazily initialized)
        self._event_bus: EventBus | None = None
        self._workflow_engine: WorkflowEngine | None = None
        self._trigger_manager: TriggerManager | None = None
        self._knowledge_store: KnowledgeStore | None = None
        self._feedback_store: FeedbackStore | None = None
        self._pattern_matcher: PatternMatcher | None = None
        self._context_manager: ContextManager | None = None
        self._learning_engine: LearningEngine | None = None

        # Stats
        self._stats = {
            "events_emitted": 0,
            "references_created": 0,
            "entities_registered": 0,
            "operations_learned": 0,
        }

    # -------------------------------------------------------------------------
    # Component Access
    # -------------------------------------------------------------------------

    @property
    def registry(self) -> EntityRegistry:
        """Get entity registry."""
        return self._registry

    @property
    def references(self) -> ReferenceStore:
        """Get reference store."""
        return self._references

    @property
    def event_bus(self) -> EventBus:
        """Get event bus (lazily initialized)."""
        if self._event_bus is None:
            from pms.automation.events import get_event_bus

            self._event_bus = get_event_bus()
        return self._event_bus

    @property
    def workflow_engine(self) -> WorkflowEngine:
        """Get workflow engine (lazily initialized)."""
        if self._workflow_engine is None:
            from pms.automation.workflows import WorkflowEngine

            self._workflow_engine = WorkflowEngine()
        return self._workflow_engine

    @property
    def knowledge(self) -> KnowledgeStore:
        """Get knowledge store (lazily initialized)."""
        if self._knowledge_store is None:
            from pms.memory import get_knowledge_store

            self._knowledge_store = get_knowledge_store()
        return self._knowledge_store

    @property
    def feedback(self) -> FeedbackStore:
        """Get feedback store (lazily initialized)."""
        if self._feedback_store is None:
            from pms.memory import get_feedback_store

            self._feedback_store = get_feedback_store()
        return self._feedback_store

    @property
    def patterns(self) -> PatternMatcher:
        """Get pattern matcher (lazily initialized)."""
        if self._pattern_matcher is None:
            from pms.memory import get_pattern_matcher

            self._pattern_matcher = get_pattern_matcher()
        return self._pattern_matcher

    @property
    def context(self) -> ContextManager:
        """Get context manager (lazily initialized)."""
        if self._context_manager is None:
            from pms.memory import get_context_manager

            self._context_manager = get_context_manager()
        return self._context_manager

    @property
    def learning(self) -> LearningEngine:
        """Get learning engine (lazily initialized)."""
        if self._learning_engine is None:
            from pms.learning import get_learning_engine

            self._learning_engine = get_learning_engine()
        return self._learning_engine

    # -------------------------------------------------------------------------
    # Entity Operations
    # -------------------------------------------------------------------------

    async def register_entity(
        self,
        entity_id: str,
        name: str,
        entity_type: EntityType | None = None,
        parent_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> EntityInfo:
        """Register an entity in the platform.

        Args:
            entity_id: Entity ID
            name: Entity name
            entity_type: Type (auto-detected from ID if not provided)
            parent_id: Optional parent entity
            metadata: Additional metadata
            tags: Searchable tags

        Returns:
            Registered entity info
        """
        # Auto-detect type from ID
        if entity_type is None:
            entity_type = get_entity_type(entity_id)
            if entity_type is None:
                raise ValueError(f"Cannot determine entity type from ID: {entity_id}")

        info = EntityInfo(
            id=entity_id,
            type=entity_type,
            name=name,
            parent_id=parent_id,
            metadata=metadata or {},
            tags=tags or [],
        )

        self._registry.register(info)
        self._stats["entities_registered"] += 1

        # Create parent reference if applicable
        if parent_id and self.config.enable_references:
            await self._references.add(
                Reference(
                    source_id=entity_id,
                    target_id=parent_id,
                    relation=ReferenceType.BELONGS_TO,
                )
            )
            self._stats["references_created"] += 1

        return info

    async def get_entity(self, entity_id: str) -> EntityInfo | None:
        """Get entity information."""
        return self._registry.get(entity_id)

    async def get_related_entities(
        self,
        entity_id: str,
        relation: ReferenceType | None = None,
    ) -> list[EntityInfo]:
        """Get all entities related to an entity.

        Args:
            entity_id: Entity to find relations for
            relation: Optional relation filter

        Returns:
            List of related entity infos
        """
        related_ids = await self._references.get_related(entity_id, relation)
        return [
            info
            for info in [self._registry.get(rid) for rid in related_ids]
            if info is not None
        ]

    # -------------------------------------------------------------------------
    # Event Operations
    # -------------------------------------------------------------------------

    async def emit_event(
        self,
        event_type: str,
        data: dict[str, Any],
        source: str = "platform",
        correlation_id: str | None = None,
    ) -> str:
        """Emit an event to the event bus.

        Also triggers learning if enabled.

        Args:
            event_type: Type of event
            data: Event data
            source: Event source
            correlation_id: Optional correlation ID

        Returns:
            Event ID
        """
        if not self.config.enable_events:
            return ""

        from pms.automation.events import Event
        from pms.automation.events import EventType as AutoEventType

        # Create event
        try:
            evt_type = AutoEventType(event_type)
        except ValueError:
            evt_type = AutoEventType.CUSTOM

        event = Event(
            type=evt_type,
            data=data,
            source=source,
            correlation_id=correlation_id,
        )

        await self.event_bus.emit(event)
        self._stats["events_emitted"] += 1

        return event.id

    async def emit_task_completed(
        self,
        task_id: str,
        project_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Emit task completed event.

        Args:
            task_id: Completed task ID
            project_id: Optional project ID
            metadata: Additional metadata

        Returns:
            Event ID
        """
        data = {
            "task_id": task_id,
            "project_id": project_id,
            **(metadata or {}),
        }

        event_id = await self.emit_event("task.completed", data)

        # Learn from success
        if self.config.enable_learning:
            await self.feedback.record_outcome("complete_task", success=True)
            self._stats["operations_learned"] += 1

        return event_id

    async def emit_workflow_completed(
        self,
        workflow_name: str,
        workflow_id: str,
        success: bool,
        duration_seconds: float,
        error: str | None = None,
    ) -> str:
        """Emit workflow completed event.

        Args:
            workflow_name: Name of workflow
            workflow_id: Workflow run ID
            success: Whether succeeded
            duration_seconds: How long it took
            error: Error message if failed

        Returns:
            Event ID
        """
        event_type = "workflow.completed" if success else "workflow.failed"
        data = {
            "workflow_name": workflow_name,
            "workflow_id": workflow_id,
            "success": success,
            "duration_seconds": duration_seconds,
            "error": error,
        }

        event_id = await self.emit_event(event_type, data)

        # Learn from outcome
        if self.config.enable_learning:
            from pms.learning import WorkflowOutcome

            outcome = WorkflowOutcome(
                workflow_name=workflow_name,
                workflow_id=workflow_id,
                success=success,
                duration_seconds=duration_seconds,
                error=error,
            )
            await self.learning.learn_from_workflow(outcome)
            self._stats["operations_learned"] += 1

        return event_id

    # -------------------------------------------------------------------------
    # Reference Operations
    # -------------------------------------------------------------------------

    async def link_entities(
        self,
        source_id: str,
        target_id: str,
        relation: ReferenceType,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Create a reference between entities.

        Args:
            source_id: Source entity
            target_id: Target entity
            relation: Relationship type
            metadata: Additional metadata

        Returns:
            Reference ID
        """
        if not self.config.enable_references:
            return ""

        ref = Reference(
            source_id=source_id,
            target_id=target_id,
            relation=relation,
            metadata=metadata or {},
        )

        ref_id = await self._references.add(ref)
        self._stats["references_created"] += 1

        return ref_id

    async def get_entity_graph(
        self,
        entity_id: str,
        depth: int = 2,
    ) -> dict[str, Any]:
        """Get relationship graph for an entity.

        Args:
            entity_id: Starting entity
            depth: How many levels to traverse

        Returns:
            Graph with nodes and edges
        """
        graph = await self._references.get_reference_graph(entity_id, depth)

        # Enrich with entity info
        enriched_nodes = []
        for node_id in graph["nodes"]:
            if isinstance(node_id, str):
                info = self._registry.get(node_id)
                entity_type = get_entity_type(node_id)
                enriched_nodes.append(
                    {
                        "id": node_id,
                        "type": entity_type.value if entity_type else "unknown",
                        "name": info.name if info else node_id,
                    }
                )

        graph["nodes"] = enriched_nodes
        return graph

    # -------------------------------------------------------------------------
    # Learning Operations
    # -------------------------------------------------------------------------

    async def record_positive_feedback(
        self,
        category: str,
        subject: str,
        reason: str = "",
    ) -> str:
        """Record positive feedback.

        Args:
            category: Feedback category
            subject: What is being praised
            reason: Why

        Returns:
            Feedback ID
        """
        if not self.config.enable_learning:
            return ""

        return await self.feedback.add_positive(category, subject, reason=reason)

    async def record_negative_feedback(
        self,
        category: str,
        subject: str,
        reason: str = "",
    ) -> str:
        """Record negative feedback.

        Args:
            category: Feedback category
            subject: What is being criticized
            reason: Why

        Returns:
            Feedback ID
        """
        if not self.config.enable_learning:
            return ""

        return await self.feedback.add_negative(category, subject, reason=reason)

    async def get_suggestions(
        self,
        task: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Get suggestions for a task.

        Args:
            task: Task description
            limit: Maximum suggestions

        Returns:
            List of suggestions
        """
        suggestions = await self.learning.suggest(task, limit=limit)
        return [
            {
                "type": s.type.value,
                "title": s.title,
                "description": s.description,
                "confidence": s.confidence,
                "action": s.action,
            }
            for s in suggestions
        ]

    async def is_recommended(
        self,
        category: str,
        subject: str,
    ) -> bool:
        """Check if something is recommended based on feedback.

        Args:
            category: Category to check
            subject: Subject to check

        Returns:
            True if recommended
        """
        if not self.config.enable_learning:
            return True

        return await self.learning.is_recommended(category, subject)

    # -------------------------------------------------------------------------
    # Context Operations
    # -------------------------------------------------------------------------

    def set_context(
        self,
        project_id: str | None = None,
        task_id: str | None = None,
    ) -> None:
        """Set current context.

        Args:
            project_id: Active project
            task_id: Active task
        """
        if project_id:
            self.context.set_active_project(project_id)
        if task_id:
            self.context.set_active_task(task_id)

    def get_context_summary(self) -> str:
        """Get summary of current context."""
        return self.context.get_context_summary()

    def add_decision(self, description: str, reason: str = "") -> None:
        """Record a decision.

        Args:
            description: What was decided
            reason: Why
        """
        self.context.add_decision(description, reason)

    # -------------------------------------------------------------------------
    # Stats and Lifecycle
    # -------------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Get platform statistics."""
        return {
            **self._stats,
            "registry": self._registry.get_stats(),
            "references": self._references.get_stats(),
        }

    async def shutdown(self) -> None:
        """Graceful shutdown of platform."""
        logger.info("Platform shutting down...")

        # Cleanup learning
        if self._learning_engine:
            await self.learning.cleanup()

        logger.info("Platform shutdown complete")


# =============================================================================
# Global Instance
# =============================================================================

_global_platform: Platform | None = None


def get_platform() -> Platform:
    """Get the global platform instance."""
    global _global_platform
    if _global_platform is None:
        _global_platform = Platform()
    return _global_platform


def set_platform(platform: Platform) -> None:
    """Set the global platform instance."""
    global _global_platform
    _global_platform = platform
