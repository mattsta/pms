"""Metrics collection and time-series tracking."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pms.db.connection import Database

logger = logging.getLogger(__name__)


class MetricType(StrEnum):
    """Types of metrics that can be collected."""

    # Timing metrics
    OPERATION_DURATION = "operation.duration"
    QUERY_DURATION = "query.duration"
    API_LATENCY = "api.latency"

    # Count metrics
    TASK_COUNT = "task.count"
    PROJECT_COUNT = "project.count"
    EVENT_COUNT = "event.count"
    ERROR_COUNT = "error.count"

    # Size metrics
    SYNC_BYTES = "sync.bytes"
    RESPONSE_SIZE = "response.size"

    # Rate metrics
    TASKS_PER_HOUR = "tasks.per_hour"
    COMPLETIONS_PER_DAY = "completions.per_day"

    # Cost metrics
    AGENT_COST = "agent.cost"
    TOKEN_USAGE = "token.usage"

    # Custom
    CUSTOM = "custom"


@dataclass(frozen=True)
class MetricLabel:
    """A label/tag for categorizing metrics."""

    key: str
    value: str


@dataclass(frozen=True)
class Metric:
    """
    A single metric data point in a time series.

    Metrics are immutable and append-only - we never update metrics,
    only add new data points.
    """

    metric_id: str
    metric_type: MetricType
    name: str
    value: float
    unit: str  # e.g., "ms", "bytes", "count", "usd"
    timestamp: datetime
    labels: tuple[MetricLabel, ...] = ()
    metadata: dict[str, str] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        metric_type: MetricType,
        name: str,
        value: float,
        unit: str,
        labels: list[MetricLabel] | None = None,
        metadata: dict[str, str] | None = None,
    ) -> Metric:
        """Create a new metric with current timestamp."""
        return cls(
            metric_id=str(uuid.uuid4()),
            metric_type=metric_type,
            name=name,
            value=value,
            unit=unit,
            timestamp=datetime.now(UTC),
            labels=tuple(labels) if labels else (),
            metadata=metadata or {},
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize metric to dictionary."""
        return {
            "metric_id": self.metric_id,
            "metric_type": self.metric_type.value,
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "timestamp": self.timestamp.isoformat(),
            "labels": {label.key: label.value for label in self.labels},
            "metadata": self.metadata,
        }


@dataclass
class OperationTimer:
    """Context manager for timing operations and recording metrics."""

    operation_name: str
    labels: list[MetricLabel] = field(default_factory=list)
    _start_time: float = field(default=0, init=False)
    _end_time: float = field(default=0, init=False)
    _collector: MetricsCollector | None = field(default=None, init=False)

    @property
    def duration_ms(self) -> float:
        """Get duration in milliseconds."""
        if self._end_time == 0:
            return (time.perf_counter() - self._start_time) * 1000
        return (self._end_time - self._start_time) * 1000

    def start(self) -> OperationTimer:
        """Start the timer."""
        self._start_time = time.perf_counter()
        return self

    def stop(self) -> float:
        """Stop the timer and return duration in ms."""
        self._end_time = time.perf_counter()
        return self.duration_ms

    def to_metric(self) -> Metric:
        """Convert to a Metric instance."""
        return Metric.create(
            metric_type=MetricType.OPERATION_DURATION,
            name=self.operation_name,
            value=self.duration_ms,
            unit="ms",
            labels=self.labels,
        )


@dataclass
class AggregatedMetric:
    """Aggregated statistics for a metric over a time period."""

    name: str
    count: int
    total: float
    min_value: float
    max_value: float
    avg_value: float
    unit: str
    period_start: datetime
    period_end: datetime
    labels: dict[str, str] = field(default_factory=dict)

    @property
    def sum(self) -> float:
        """Alias for total."""
        return self.total


class MetricsCollector:
    """
    Collects and stores metrics in an append-only time series.

    All metrics are stored, nothing is overwritten.
    Aggregations are computed on-demand from raw data.
    """

    def __init__(self, db: Database) -> None:
        self.db = db
        self._buffer: list[Metric] = []
        self._buffer_size = 100  # Flush after this many metrics
        self._flush_lock = asyncio.Lock()

    async def record(self, metric: Metric) -> None:
        """Record a single metric (buffered)."""
        should_flush = False
        async with self._flush_lock:
            self._buffer.append(metric)
            should_flush = len(self._buffer) >= self._buffer_size
        if should_flush:
            await self.flush()

    async def record_immediately(self, metric: Metric) -> None:
        """Record a metric immediately without buffering."""
        await self._store_metric(metric)

    async def flush(self) -> int:
        """Flush buffered metrics to storage."""
        async with self._flush_lock:
            if not self._buffer:
                return 0
            buffered_metrics = list(self._buffer)
            self._buffer.clear()

        count = len(buffered_metrics)
        for metric in buffered_metrics:
            await self._store_metric(metric)
        return count

    async def flush_best_effort(self, *, context: str | None = None) -> int:
        """Flush buffered metrics without letting observational telemetry fail callers."""
        try:
            return await self.flush()
        except Exception:
            detail = f" during {context}" if context else ""
            logger.warning(
                "Ignoring observational metrics flush failure%s",
                detail,
                exc_info=True,
            )
            return 0

    async def _store_metric(self, metric: Metric) -> None:
        """Store a single metric to the database."""
        await self.db.execute(
            """
            INSERT INTO metrics (
                metric_id, metric_type, name, value, unit,
                timestamp, labels, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                metric.metric_id,
                metric.metric_type.value,
                metric.name,
                metric.value,
                metric.unit,
                metric.timestamp.isoformat(),
                json.dumps({l.key: l.value for l in metric.labels}),
                json.dumps(metric.metadata),
            ),
        )

    @contextmanager
    def time_operation(
        self,
        operation_name: str,
        labels: list[MetricLabel] | None = None,
    ) -> Generator[OperationTimer]:
        """Context manager for timing operations."""
        timer = OperationTimer(
            operation_name=operation_name,
            labels=labels or [],
        )
        timer.start()
        try:
            yield timer
        finally:
            timer.stop()
            self._buffer.append(timer.to_metric())

    async def get_metrics(
        self,
        name: str | None = None,
        metric_type: MetricType | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        labels: dict[str, str] | None = None,
        limit: int = 1000,
    ) -> list[Metric]:
        """Query metrics with optional filters."""
        query = "SELECT * FROM metrics WHERE 1=1"
        params: list[Any] = []

        if name:
            query += " AND name = ?"
            params.append(name)

        if metric_type:
            query += " AND metric_type = ?"
            params.append(metric_type.value)

        if since:
            query += " AND timestamp >= ?"
            params.append(since.isoformat())

        if until:
            query += " AND timestamp <= ?"
            params.append(until.isoformat())

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        rows = await self.db.fetch_all(query, tuple(params))

        metrics = []
        for row in rows:
            label_dict = json.loads(row["labels"])
            if labels and not all(label_dict.get(k) == v for k, v in labels.items()):
                continue

            metrics.append(
                Metric(
                    metric_id=row["metric_id"],
                    metric_type=MetricType(row["metric_type"]),
                    name=row["name"],
                    value=row["value"],
                    unit=row["unit"],
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    labels=tuple(MetricLabel(k, v) for k, v in label_dict.items()),
                    metadata=json.loads(row["metadata"]),
                )
            )

        return metrics

    async def aggregate(
        self,
        name: str,
        since: datetime,
        until: datetime | None = None,
        group_by_labels: list[str] | None = None,
    ) -> list[AggregatedMetric]:
        """Compute aggregated statistics for metrics."""
        until = until or datetime.now(UTC)

        query = """
            SELECT
                name,
                unit,
                COUNT(*) as count,
                SUM(value) as total,
                MIN(value) as min_value,
                MAX(value) as max_value,
                AVG(value) as avg_value
            FROM metrics
            WHERE name = ? AND timestamp >= ? AND timestamp <= ?
            GROUP BY name, unit
        """
        params = (name, since.isoformat(), until.isoformat())

        rows = await self.db.fetch_all(query, params)

        return [
            AggregatedMetric(
                name=row["name"],
                count=row["count"],
                total=row["total"],
                min_value=row["min_value"],
                max_value=row["max_value"],
                avg_value=row["avg_value"],
                unit=row["unit"],
                period_start=since,
                period_end=until,
            )
            for row in rows
        ]

    async def count_by_type(
        self,
        since: datetime | None = None,
    ) -> dict[MetricType, int]:
        """Get count of metrics by type."""
        query = "SELECT metric_type, COUNT(*) as count FROM metrics"
        params: tuple[Any, ...] = ()

        if since:
            query += " WHERE timestamp >= ?"
            params = (since.isoformat(),)

        query += " GROUP BY metric_type"

        rows = await self.db.fetch_all(query, params)
        return {MetricType(row["metric_type"]): row["count"] for row in rows}

    async def record_counter(
        self,
        name: str,
        value: float = 1.0,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Record a counter metric (convenience method)."""
        metric_labels = [MetricLabel(k, v) for k, v in (labels or {}).items()]
        metric = Metric.create(
            metric_type=MetricType.CUSTOM,
            name=name,
            value=value,
            unit="count",
            labels=metric_labels,
        )
        await self.record(metric)

    async def record_gauge(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
        unit: str = "value",
    ) -> None:
        """Record a gauge metric (convenience method)."""
        metric_labels = [MetricLabel(k, v) for k, v in (labels or {}).items()]
        metric = Metric.create(
            metric_type=MetricType.CUSTOM,
            name=name,
            value=value,
            unit=unit,
            labels=metric_labels,
        )
        await self.record(metric)

    async def record_timing(
        self,
        name: str,
        duration_ms: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Record a timing metric (convenience method)."""
        metric_labels = [MetricLabel(k, v) for k, v in (labels or {}).items()]
        metric = Metric.create(
            metric_type=MetricType.OPERATION_DURATION,
            name=name,
            value=duration_ms,
            unit="ms",
            labels=metric_labels,
        )
        await self.record(metric)
