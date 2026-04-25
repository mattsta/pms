"""Label assignment models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from pms.models.base import BaseModel, now_utc


@dataclass
class LabelAssignment(BaseModel):
    """Assignment of a label to an entity."""

    entity_type: str = ""
    entity_id: str = ""
    label_id: str = ""
    applied_by: str | None = None
    applied_at: datetime = field(default_factory=now_utc)
