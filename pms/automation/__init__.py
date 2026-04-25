"""Automation subsystem for PMS.

This module provides:
- Event Bus: Pub/sub messaging between components
- Workflow Engine: Define and execute multi-step automations
- Triggers: Event-driven workflow initiation
- Scheduler: Time-based automation

Architecture:
    ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
    │   Trigger   │────▶│  Event Bus  │────▶│  Workflow   │
    │   System    │     │             │     │   Engine    │
    └─────────────┘     └─────────────┘     └─────────────┘
           │                   │                   │
           │                   ▼                   │
           │            ┌─────────────┐            │
           └───────────▶│   Actions   │◀───────────┘
                        │   (Tools)   │
                        └─────────────┘
"""

from pms.automation.events import (
    Event,
    EventBus,
    EventHandler,
    EventType,
)
from pms.automation.triggers import (
    Trigger,
    TriggerManager,
    TriggerType,
)
from pms.automation.workflows import (
    Workflow,
    WorkflowContext,
    WorkflowEngine,
    WorkflowStatus,
    WorkflowStep,
)

__all__ = [
    # Events
    "Event",
    "EventBus",
    "EventHandler",
    "EventType",
    # Workflows
    "Workflow",
    "WorkflowContext",
    "WorkflowEngine",
    "WorkflowStatus",
    "WorkflowStep",
    # Triggers
    "Trigger",
    "TriggerManager",
    "TriggerType",
]
