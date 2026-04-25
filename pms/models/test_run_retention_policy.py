"""Retention policy model for test run outputs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pms.models.base import BaseModel


@dataclass
class TestRunRetentionPolicy(BaseModel):
    """Scoped retention limits for test run outputs."""

    scope_type: str = "project"
    scope_id: str = ""
    max_log_bytes: int = 0
    max_artifact_bytes: int = 0
    max_age_days: int = 0
    notes: str | None = None
    archived_at: datetime | None = None
