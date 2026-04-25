"""Workflow evidence gate rules."""

from __future__ import annotations

from dataclasses import dataclass

from pms.models.base import BaseModel


@dataclass
class EvidenceGateRule(BaseModel):
    """Gate rule linking workflow transitions to evidence requirements."""

    workflow_id: str = ""
    entity_type: str = "task"
    from_state: str = ""
    to_state: str = ""
    evidence_type: str = ""
    min_count: int = 1
    require_success: bool = False
    message: str | None = None
