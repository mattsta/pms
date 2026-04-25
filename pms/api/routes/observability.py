"""Unified observability overview API routes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TypedDict

from fastapi import APIRouter, Depends, Query

from pms.api.auth import Scopes, check_rate_limit, get_api_key
from pms.api.dependencies import (
    get_db,
    get_lineage_service,
    get_organization_service,
    get_portfolio_service,
    get_program_service,
    get_project_service,
    get_queue_service,
    get_test_run_retention_service,
)
from pms.api.routes.discoverability import (
    QueryParamMap,
    build_query_path,
    cli_command_template,
    normalize_next_steps,
)
from pms.db.connection import Database
from pms.models.api_key import ApiKey
from pms.services.lineage_service import LineageService
from pms.services.organization_service import OrganizationService
from pms.services.portfolio_service import PortfolioService
from pms.services.program_service import ProgramService
from pms.services.project_service import ProjectService
from pms.services.queue_service import QueueService
from pms.services.test_run_retention_service import TestRunRetentionService

router = APIRouter()


class ObservabilityProjectTotalsPayload(TypedDict):
    """Project dashboard totals used by observability overview."""

    population: str
    total_projects: int
    total_tasks: int
    completed_tasks: int
    blocked_tasks: int
    overdue_tasks: int


class ObservabilityOrganizationTotalsPayload(TypedDict):
    """Organization dashboard totals used by observability overview."""

    total_organizations: int
    total_teams: int
    total_portfolios: int
    total_programs: int
    total_projects: int
    total_goals: int
    total_objectives: int
    total_tasks: int
    blocked_tasks: int


class ObservabilityPortfolioTotalsPayload(TypedDict):
    """Portfolio dashboard totals used by observability overview."""

    total_portfolios: int
    total_projects: int
    total_goals: int
    total_objectives: int
    total_tasks: int
    blocked_tasks: int


class ObservabilityProgramTotalsPayload(TypedDict):
    """Program dashboard totals used by observability overview."""

    total_programs: int
    total_projects: int
    total_goals: int
    total_objectives: int
    total_tasks: int
    blocked_tasks: int


class ObservabilityRollupsPayload(TypedDict, total=False):
    """Multi-scope rollups for fast state understanding."""

    projects: ObservabilityProjectTotalsPayload
    organizations: ObservabilityOrganizationTotalsPayload
    portfolios: ObservabilityPortfolioTotalsPayload
    programs: ObservabilityProgramTotalsPayload


class ObservabilityQueueTaskPayload(TypedDict):
    """Compact queue task summary."""

    id: str
    project_id: str
    title: str
    status: str
    priority: str
    updated_at: str
    due_date: str | None


class ObservabilityQueuePayload(TypedDict):
    """Queue preset summary for observability output."""

    name: str
    description: str
    total_count: int
    samples: list[ObservabilityQueueTaskPayload]


class ObservabilityLineagePayload(TypedDict):
    """Plan lineage totals for platform observability."""

    total_plans: int
    total_tasks: int
    total_test_runs: int
    failed_test_runs: int
    total_evidence: int
    total_code_evidence: int


class ObservabilityRetentionPayload(TypedDict):
    """Retention/storage health summary."""

    total_runs: int
    total_bytes: int
    total_log_bytes_combined: int
    total_artifact_bytes: int
    alert_count: int
    policy_count: int


class ObservabilityEventTimelinePointPayload(TypedDict):
    """Single bucket in event activity timeline."""

    bucket_start: str
    event_count: int


class ObservabilityEventTimelinePayload(TypedDict):
    """Event activity timeline summary."""

    window_days: int
    points: list[ObservabilityEventTimelinePointPayload]


class ObservabilityHealthPayload(TypedDict):
    """Computed health signal for quick operator triage."""

    status: str
    blocked_task_ratio: float
    overdue_task_ratio: float
    completion_ratio: float
    retention_alert_count: int


class ObservabilityAttentionItemPayload(TypedDict):
    """Actionable issue surfaced by the observability overview."""

    id: str
    category: str
    severity: str
    title: str
    summary: str
    why: str
    api_path: str
    cli_command: str


class ObservabilityRecommendedActionPayload(TypedDict):
    """Concrete follow-up action derived from current observability state."""

    id: str
    title: str
    why: str
    api_call: str
    cli_command: str


class ObservabilityAttentionSummaryPayload(TypedDict):
    """Stable export summary for immediate human or automation triage."""

    overall_status: str
    highest_severity: str
    total_attention_items: int
    top_risk_count: int
    stalled_flow_count: int
    needs_review_count: int


class ObservabilityPermissionsPayload(TypedDict):
    """Section-level visibility map for the current API key."""

    rollups: bool
    queues: bool
    lineage: bool
    retention: bool
    event_timeline: bool


class ObservabilityParamsPayload(TypedDict):
    """Echoed request parameters for overview calls."""

    include_rollups: bool
    include_queues: bool
    include_lineage: bool
    include_retention: bool
    include_event_timeline: bool
    queue_limit: int
    lineage_limit: int
    retention_limit: int
    timeline_days: int


class ObservabilityLinksPayload(TypedDict):
    """Continuation links for observability traversal."""

    self: str
    root: str
    dashboard: str
    discoverability_graph: str
    organizations_dashboard: str
    plans_lineage: str
    test_run_retention: str


class ObservabilityOverviewPayload(TypedDict):
    """Unified live observability overview payload."""

    generated_at: str
    health: ObservabilityHealthPayload
    attention_summary: ObservabilityAttentionSummaryPayload
    attention_items: list[ObservabilityAttentionItemPayload]
    top_risks_now: list[ObservabilityAttentionItemPayload]
    stalled_flows: list[ObservabilityAttentionItemPayload]
    needs_review: list[ObservabilityAttentionItemPayload]
    recommended_actions: list[ObservabilityRecommendedActionPayload]
    permissions: ObservabilityPermissionsPayload
    warnings: list[str]
    rollups: ObservabilityRollupsPayload | None
    queues: list[ObservabilityQueuePayload] | None
    lineage: ObservabilityLineagePayload | None
    retention: ObservabilityRetentionPayload | None
    event_timeline: ObservabilityEventTimelinePayload | None
    links: ObservabilityLinksPayload
    next_steps: list[str]
    params: ObservabilityParamsPayload


def _can_read_rollups(api_key: ApiKey) -> bool:
    return any(
        api_key.matches_scope(scope)
        for scope in (
            Scopes.PROJECTS_READ,
            Scopes.ORGS_READ,
            Scopes.PORTFOLIOS_READ,
            Scopes.PROGRAMS_READ,
        )
    )


def _section_enabled(*, requested: bool, allowed: bool) -> bool:
    return requested and allowed


def _build_health(
    *,
    project_totals: ObservabilityProjectTotalsPayload | None,
    retention: ObservabilityRetentionPayload | None,
) -> ObservabilityHealthPayload:
    total_tasks = project_totals["total_tasks"] if project_totals else 0
    blocked_tasks = project_totals["blocked_tasks"] if project_totals else 0
    overdue_tasks = project_totals["overdue_tasks"] if project_totals else 0
    completed_tasks = project_totals["completed_tasks"] if project_totals else 0
    retention_alert_count = retention["alert_count"] if retention else 0

    if total_tasks <= 0:
        blocked_ratio = 0.0
        overdue_ratio = 0.0
        completion_ratio = 0.0
    else:
        blocked_ratio = blocked_tasks / total_tasks
        overdue_ratio = overdue_tasks / total_tasks
        completion_ratio = completed_tasks / total_tasks

    if total_tasks <= 0 and retention_alert_count == 0:
        status = "unknown"
    elif retention_alert_count > 0 or blocked_ratio >= 0.20 or overdue_ratio >= 0.12:
        status = "attention"
    elif blocked_ratio >= 0.10 or overdue_ratio >= 0.06:
        status = "watch"
    else:
        status = "healthy"

    return {
        "status": status,
        "blocked_task_ratio": blocked_ratio,
        "overdue_task_ratio": overdue_ratio,
        "completion_ratio": completion_ratio,
        "retention_alert_count": retention_alert_count,
    }


def _attention_item(
    *,
    item_id: str,
    category: str,
    severity: str,
    title: str,
    summary: str,
    why: str,
    api_path: str,
    cli_command: str,
) -> ObservabilityAttentionItemPayload:
    return {
        "id": item_id,
        "category": category,
        "severity": severity,
        "title": title,
        "summary": summary,
        "why": why,
        "api_path": api_path,
        "cli_command": cli_command,
    }


def _recommended_action(
    *,
    action_id: str,
    title: str,
    why: str,
    api_call: str,
    cli_command: str,
) -> ObservabilityRecommendedActionPayload:
    return {
        "id": action_id,
        "title": title,
        "why": why,
        "api_call": api_call,
        "cli_command": cli_command,
    }


def _severity_rank(severity: str) -> int:
    if severity == "high":
        return 3
    if severity == "medium":
        return 2
    return 1


def _categorize_attention_items(
    *,
    health: ObservabilityHealthPayload,
    permissions: ObservabilityPermissionsPayload,
    warnings: list[str],
    rollups: ObservabilityRollupsPayload | None,
    queues: list[ObservabilityQueuePayload] | None,
    lineage: ObservabilityLineagePayload | None,
    retention: ObservabilityRetentionPayload | None,
) -> tuple[
    list[ObservabilityAttentionItemPayload],
    list[ObservabilityAttentionItemPayload],
    list[ObservabilityAttentionItemPayload],
]:
    top_risks_now: list[ObservabilityAttentionItemPayload] = []
    stalled_flows: list[ObservabilityAttentionItemPayload] = []
    needs_review: list[ObservabilityAttentionItemPayload] = []

    if retention is not None and retention["alert_count"] > 0:
        top_risks_now.append(
            _attention_item(
                item_id="retention-alerts",
                category="retention",
                severity="high",
                title="Retention alerts require cleanup",
                summary=(
                    f"{retention['alert_count']} retention alert(s) are active across "
                    f"{retention['total_runs']} stored run(s)."
                ),
                why="Stored logs and artifacts are above one or more retention guardrails.",
                api_path="/api/v1/test-runs/retention",
                cli_command=cli_command_template(
                    "pms test-run retention --format json"
                ),
            )
        )

    project_rollups = rollups["projects"] if rollups and "projects" in rollups else None
    if project_rollups is not None and project_rollups["blocked_tasks"] > 0:
        blocked_ratio = health["blocked_task_ratio"]
        stalled_flows.append(
            _attention_item(
                item_id="blocked-work",
                category="execution",
                severity="high" if blocked_ratio >= 0.20 else "medium",
                title="Blocked work needs operator attention",
                summary=(
                    f"{project_rollups['blocked_tasks']} blocked task(s) across "
                    f"{project_rollups['total_tasks']} total task(s)."
                ),
                why="Blocked tasks slow delivery and usually indicate missing decisions or dependencies.",
                api_path="/api/v1/queues/presets",
                cli_command=cli_command_template("pms queue preset list --format json"),
            )
        )

    if project_rollups is not None and project_rollups["overdue_tasks"] > 0:
        needs_review.append(
            _attention_item(
                item_id="overdue-work",
                category="review",
                severity="high" if health["overdue_task_ratio"] >= 0.12 else "medium",
                title="Overdue work should be re-triaged",
                summary=(
                    f"{project_rollups['overdue_tasks']} overdue task(s) across "
                    f"{project_rollups['total_tasks']} total task(s)."
                ),
                why="Overdue work needs owner, scope, or deadline review before it drifts further.",
                api_path="/api/v1/work-snapshots/{scope_type}/{scope_id}/daily?view=detail",
                cli_command=cli_command_template("pms work daily --format json"),
            )
        )

    if lineage is not None and lineage["failed_test_runs"] > 0:
        needs_review.append(
            _attention_item(
                item_id="failed-test-runs",
                category="quality",
                severity="medium",
                title="Failed test runs need investigation",
                summary=(
                    f"{lineage['failed_test_runs']} failed test run(s) across "
                    f"{lineage['total_test_runs']} total lineage-linked run(s)."
                ),
                why="Recent delivery evidence includes failing validation that may block release or merge.",
                api_path="/api/v1/plans/lineage",
                cli_command=cli_command_template("pms plan lineage --format json"),
            )
        )

    if queues is not None:
        for queue in queues:
            stale_samples = [
                sample for sample in queue["samples"] if sample["status"] == "blocked"
            ]
            if stale_samples:
                stalled_flows.append(
                    _attention_item(
                        item_id=f"queue-{queue['name'].lower().replace(' ', '-')}-blocked",
                        category="queue",
                        severity="medium",
                        title=f'Queue "{queue["name"]}" contains blocked samples',
                        summary=(
                            f"{len(stale_samples)} blocked sample task(s) are visible in "
                            f'the "{queue["name"]}" queue.'
                        ),
                        why="Queue samples show active blocked work that likely needs immediate routing.",
                        api_path="/api/v1/queues/presets",
                        cli_command=cli_command_template(
                            "pms queue preset list --format json"
                        ),
                    )
                )

    if warnings:
        missing_scope_count = sum(1 for warning in warnings if "missing" in warning)
        if missing_scope_count > 0:
            top_risks_now.append(
                _attention_item(
                    item_id="scope-gaps",
                    category="access",
                    severity="medium" if health["status"] != "unknown" else "high",
                    title="Observability scope gaps limit this overview",
                    summary=(
                        f"{missing_scope_count} section(s) were omitted because the API key "
                        "does not include all required read scopes."
                    ),
                    why="Operators cannot act confidently when parts of live state are hidden.",
                    api_path="/api/v1/discoverability/graph?path_contains=dashboard",
                    cli_command=cli_command_template("pms capabilities --format json"),
                )
            )

    if (
        health["status"] == "unknown"
        and not permissions["rollups"]
        and not permissions["lineage"]
        and not permissions["retention"]
    ):
        needs_review.append(
            _attention_item(
                item_id="limited-visibility",
                category="visibility",
                severity="medium",
                title="Live state visibility is too narrow",
                summary="The current key cannot read enough operational state to compute a confident health view.",
                why="Broader observability access is needed before this overview can guide production operations reliably.",
                api_path="/api/v1/observability/overview",
                cli_command=cli_command_template("pms config show --format json"),
            )
        )

    top_risks_now.sort(key=lambda item: _severity_rank(item["severity"]), reverse=True)
    stalled_flows.sort(key=lambda item: _severity_rank(item["severity"]), reverse=True)
    needs_review.sort(key=lambda item: _severity_rank(item["severity"]), reverse=True)
    return top_risks_now, stalled_flows, needs_review


def _build_recommended_actions(
    *,
    top_risks_now: list[ObservabilityAttentionItemPayload],
    stalled_flows: list[ObservabilityAttentionItemPayload],
    needs_review: list[ObservabilityAttentionItemPayload],
) -> list[ObservabilityRecommendedActionPayload]:
    actions: list[ObservabilityRecommendedActionPayload] = []
    seen_action_ids: set[str] = set()

    action_specs: list[tuple[str, str, list[ObservabilityAttentionItemPayload]]] = [
        ("risk", "Reduce the highest live risk", top_risks_now),
        ("stalled", "Unblock the slowest delivery flow", stalled_flows),
        ("review", "Review the next unstable area", needs_review),
    ]
    for prefix, title, items in action_specs:
        if not items:
            continue
        item = items[0]
        action_id = f"{prefix}-{item['id']}"
        if action_id in seen_action_ids:
            continue
        seen_action_ids.add(action_id)
        actions.append(
            _recommended_action(
                action_id=action_id,
                title=title,
                why=item["why"],
                api_call=f"GET {item['api_path']}",
                cli_command=item["cli_command"],
            )
        )

    if not actions:
        actions.append(
            _recommended_action(
                action_id="healthy-observe",
                title="Keep monitoring the live system",
                why="No immediate risk, stalled flow, or review hotspot is currently detected in this overview.",
                api_call="GET /api/v1/observability/overview",
                cli_command=cli_command_template("pms start --format json"),
            )
        )

    return actions


def _build_attention_summary(
    *,
    health: ObservabilityHealthPayload,
    top_risks_now: list[ObservabilityAttentionItemPayload],
    stalled_flows: list[ObservabilityAttentionItemPayload],
    needs_review: list[ObservabilityAttentionItemPayload],
) -> ObservabilityAttentionSummaryPayload:
    highest_rank = 0
    highest_severity = "low"
    for item in [*top_risks_now, *stalled_flows, *needs_review]:
        rank = _severity_rank(item["severity"])
        if rank > highest_rank:
            highest_rank = rank
            highest_severity = item["severity"]

    return {
        "overall_status": health["status"],
        "highest_severity": highest_severity,
        "total_attention_items": (
            len(top_risks_now) + len(stalled_flows) + len(needs_review)
        ),
        "top_risk_count": len(top_risks_now),
        "stalled_flow_count": len(stalled_flows),
        "needs_review_count": len(needs_review),
    }


async def _event_timeline_points(
    db: Database,
    *,
    timeline_days: int,
) -> list[ObservabilityEventTimelinePointPayload]:
    now = datetime.now(UTC)
    start = now - timedelta(days=timeline_days)
    rows = await db.fetch_all(
        """
        SELECT substr(timestamp, 1, 10) as bucket_start, COUNT(*) as event_count
        FROM events
        WHERE timestamp >= ?
        GROUP BY bucket_start
        ORDER BY bucket_start ASC
        """,
        (start.isoformat(),),
    )
    counts: dict[str, int] = {}
    for row in rows:
        bucket_start = str(row["bucket_start"])
        counts[bucket_start] = int(str(row["event_count"]))
    return [
        {
            "bucket_start": (start + timedelta(days=index)).date().isoformat(),
            "event_count": counts.get(
                (start + timedelta(days=index)).date().isoformat(),
                0,
            ),
        }
        for index in range(timeline_days + 1)
    ]


@router.get("/observability/overview")
async def get_observability_overview(
    include_rollups: bool = True,
    include_queues: bool = True,
    include_lineage: bool = True,
    include_retention: bool = True,
    include_event_timeline: bool = True,
    queue_limit: int = Query(5, ge=1, le=50),
    lineage_limit: int = Query(20, ge=1, le=100),
    retention_limit: int = Query(10, ge=1, le=100),
    timeline_days: int = Query(14, ge=1, le=90),
    db: Database = Depends(get_db),
    organization_service: OrganizationService = Depends(get_organization_service),
    portfolio_service: PortfolioService = Depends(get_portfolio_service),
    program_service: ProgramService = Depends(get_program_service),
    project_service: ProjectService = Depends(get_project_service),
    queue_service: QueueService = Depends(get_queue_service),
    lineage_service: LineageService = Depends(get_lineage_service),
    retention_service: TestRunRetentionService = Depends(
        get_test_run_retention_service
    ),
    api_key: ApiKey = Depends(get_api_key),
) -> ObservabilityOverviewPayload:
    """Get a unified platform observability overview with continuation hints."""
    await check_rate_limit(api_key)

    can_read_rollups = _can_read_rollups(api_key)
    can_read_queues = api_key.matches_scope(Scopes.TASKS_READ)
    can_read_lineage = api_key.matches_scope(Scopes.PLANS_READ)
    can_read_retention = api_key.matches_scope(Scopes.TEST_RUNS_READ)
    can_read_event_timeline = api_key.matches_scope(Scopes.ADMIN)

    permissions: ObservabilityPermissionsPayload = {
        "rollups": _section_enabled(
            requested=include_rollups, allowed=can_read_rollups
        ),
        "queues": _section_enabled(requested=include_queues, allowed=can_read_queues),
        "lineage": _section_enabled(
            requested=include_lineage,
            allowed=can_read_lineage,
        ),
        "retention": _section_enabled(
            requested=include_retention,
            allowed=can_read_retention,
        ),
        "event_timeline": _section_enabled(
            requested=include_event_timeline,
            allowed=can_read_event_timeline,
        ),
    }

    warnings: list[str] = []

    project_totals_for_health: ObservabilityProjectTotalsPayload | None = None
    rollups: ObservabilityRollupsPayload | None = None
    if include_rollups:
        rollup_data: ObservabilityRollupsPayload = {}
        if api_key.matches_scope(Scopes.PROJECTS_READ):
            project_dashboard = await project_service.get_dashboard()
            project_totals_for_health = {
                "population": "all_non_archived_retained",
                "total_projects": project_dashboard.total_projects,
                "total_tasks": project_dashboard.total_tasks,
                "completed_tasks": project_dashboard.completed_tasks,
                "blocked_tasks": project_dashboard.blocked_tasks,
                "overdue_tasks": project_dashboard.overdue_tasks,
            }
            rollup_data["projects"] = project_totals_for_health
        else:
            warnings.append("projects:read missing; project rollups omitted.")

        if api_key.matches_scope(Scopes.ORGS_READ):
            org_dashboard = await organization_service.get_organization_dashboard(
                status=None,
                limit=1,
                offset=0,
            )
            rollup_data["organizations"] = {
                "total_organizations": org_dashboard.total_organizations,
                "total_teams": org_dashboard.total_teams,
                "total_portfolios": org_dashboard.total_portfolios,
                "total_programs": org_dashboard.total_programs,
                "total_projects": org_dashboard.total_projects,
                "total_goals": org_dashboard.total_goals,
                "total_objectives": org_dashboard.total_objectives,
                "total_tasks": org_dashboard.total_tasks,
                "blocked_tasks": org_dashboard.blocked_tasks,
            }
        else:
            warnings.append("orgs:read missing; organization rollups omitted.")

        if api_key.matches_scope(Scopes.PORTFOLIOS_READ):
            portfolio_dashboard = await portfolio_service.get_portfolio_dashboard(
                status=None,
                org_id=None,
                limit=1,
                offset=0,
            )
            rollup_data["portfolios"] = {
                "total_portfolios": portfolio_dashboard.total_portfolios,
                "total_projects": portfolio_dashboard.total_projects,
                "total_goals": portfolio_dashboard.total_goals,
                "total_objectives": portfolio_dashboard.total_objectives,
                "total_tasks": portfolio_dashboard.total_tasks,
                "blocked_tasks": portfolio_dashboard.blocked_tasks,
            }
        else:
            warnings.append("portfolios:read missing; portfolio rollups omitted.")

        if api_key.matches_scope(Scopes.PROGRAMS_READ):
            program_dashboard = await program_service.get_program_dashboard(
                status=None,
                org_id=None,
                portfolio_id=None,
                limit=1,
                offset=0,
            )
            rollup_data["programs"] = {
                "total_programs": program_dashboard.total_programs,
                "total_projects": program_dashboard.total_projects,
                "total_goals": program_dashboard.total_goals,
                "total_objectives": program_dashboard.total_objectives,
                "total_tasks": program_dashboard.total_tasks,
                "blocked_tasks": program_dashboard.blocked_tasks,
            }
        else:
            warnings.append("programs:read missing; program rollups omitted.")

        rollups = rollup_data or None
        if rollups is None:
            warnings.append("No rollup scopes available for this API key.")

    queues: list[ObservabilityQueuePayload] | None = None
    if include_queues:
        if can_read_queues:
            preset_summaries = await queue_service.list_presets(
                project_id=None,
                limit=queue_limit,
            )
            queues = [
                {
                    "name": summary.name,
                    "description": summary.description,
                    "total_count": summary.total_count,
                    "samples": [
                        {
                            "id": task.id,
                            "project_id": task.project_id,
                            "title": task.title,
                            "status": task.status.value,
                            "priority": task.priority.value,
                            "updated_at": task.updated_at.isoformat(),
                            "due_date": (
                                task.due_date.isoformat() if task.due_date else None
                            ),
                        }
                        for task in summary.items
                    ],
                }
                for summary in preset_summaries
            ]
        else:
            warnings.append("tasks:read missing; queue summaries omitted.")

    lineage: ObservabilityLineagePayload | None = None
    if include_lineage:
        if can_read_lineage:
            lineage_dashboard = await lineage_service.get_plan_lineage_dashboard(
                status=None,
                project_id=None,
                plan_id=None,
                limit=lineage_limit,
                offset=0,
                task_limit=5,
                test_limit=3,
            )
            lineage = {
                "total_plans": lineage_dashboard.total_plans,
                "total_tasks": lineage_dashboard.total_tasks,
                "total_test_runs": lineage_dashboard.total_test_runs,
                "failed_test_runs": lineage_dashboard.failed_test_runs,
                "total_evidence": lineage_dashboard.total_evidence,
                "total_code_evidence": lineage_dashboard.total_code_evidence,
            }
        else:
            warnings.append("plans:read missing; plan lineage summary omitted.")

    retention: ObservabilityRetentionPayload | None = None
    if include_retention:
        if can_read_retention:
            usage = await retention_service.get_usage(
                limit=retention_limit,
                sort="largest",
            )
            retention = {
                "total_runs": usage.total_runs,
                "total_bytes": usage.total_bytes,
                "total_log_bytes_combined": usage.total_log_bytes_combined,
                "total_artifact_bytes": usage.total_artifact_bytes,
                "alert_count": len(usage.alerts),
                "policy_count": len(usage.policies),
            }
        else:
            warnings.append("test_runs:read missing; retention summary omitted.")

    event_timeline: ObservabilityEventTimelinePayload | None = None
    if include_event_timeline:
        if can_read_event_timeline:
            event_timeline = {
                "window_days": timeline_days,
                "points": await _event_timeline_points(
                    db,
                    timeline_days=timeline_days,
                ),
            }
        else:
            warnings.append("* scope missing; event timeline omitted.")

    params: ObservabilityParamsPayload = {
        "include_rollups": include_rollups,
        "include_queues": include_queues,
        "include_lineage": include_lineage,
        "include_retention": include_retention,
        "include_event_timeline": include_event_timeline,
        "queue_limit": queue_limit,
        "lineage_limit": lineage_limit,
        "retention_limit": retention_limit,
        "timeline_days": timeline_days,
    }
    query_params: QueryParamMap = {
        "include_rollups": include_rollups,
        "include_queues": include_queues,
        "include_lineage": include_lineage,
        "include_retention": include_retention,
        "include_event_timeline": include_event_timeline,
        "queue_limit": queue_limit,
        "lineage_limit": lineage_limit,
        "retention_limit": retention_limit,
        "timeline_days": timeline_days,
    }
    links: ObservabilityLinksPayload = {
        "self": build_query_path("/api/v1/observability/overview", query_params),
        "root": "/",
        "dashboard": "/dashboard",
        "discoverability_graph": "/api/v1/discoverability/graph",
        "organizations_dashboard": "/api/v1/organizations/dashboard",
        "plans_lineage": "/api/v1/plans/lineage",
        "test_run_retention": "/api/v1/test-runs/retention",
    }
    health = _build_health(
        project_totals=project_totals_for_health,
        retention=retention,
    )
    top_risks_now, stalled_flows, needs_review = _categorize_attention_items(
        health=health,
        permissions=permissions,
        warnings=warnings,
        rollups=rollups,
        queues=queues,
        lineage=lineage,
        retention=retention,
    )
    attention_items = [*top_risks_now, *stalled_flows, *needs_review]
    recommended_actions = _build_recommended_actions(
        top_risks_now=top_risks_now,
        stalled_flows=stalled_flows,
        needs_review=needs_review,
    )
    attention_summary = _build_attention_summary(
        health=health,
        top_risks_now=top_risks_now,
        stalled_flows=stalled_flows,
        needs_review=needs_review,
    )
    next_steps = normalize_next_steps(
        *[action["api_call"] for action in recommended_actions],
        "GET /api/v1/organizations/dashboard",
        "GET /api/v1/plans/lineage",
        "GET /api/v1/queues/presets",
        "GET /api/v1/work-snapshots/{scope_type}/{scope_id}/daily?view=detail",
        "GET /api/v1/discoverability/graph?path_contains=dashboard",
    )

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "health": health,
        "attention_summary": attention_summary,
        "attention_items": attention_items,
        "top_risks_now": top_risks_now,
        "stalled_flows": stalled_flows,
        "needs_review": needs_review,
        "recommended_actions": recommended_actions,
        "permissions": permissions,
        "warnings": warnings,
        "rollups": rollups,
        "queues": queues,
        "lineage": lineage,
        "retention": retention,
        "event_timeline": event_timeline,
        "links": links,
        "next_steps": next_steps,
        "params": params,
    }
