"""Projects API routes."""

from typing import TypedDict

from fastapi import APIRouter, Depends, HTTPException

from pms.api.actor_payloads import actor_reference_payload, resolve_actor_reference_map
from pms.api.auth import Scopes, check_resource_scope, get_api_key, require_scope
from pms.api.dependencies import (
    get_db,
    get_history_bundle_service,
    get_lineage_service,
    get_project_service,
    get_queue_service,
    get_task_service,
    get_test_run_service,
    get_work_snapshot_service,
)
from pms.api.models import ProjectCreate, ProjectResponse, ProjectUpdate
from pms.api.routes.detail_contracts import select_focus_task, task_focus_payload
from pms.api.routes.discoverability import (
    QueryParamMap,
    build_query_path,
    next_page_path,
    normalize_next_steps,
    paginated_links,
)
from pms.api.types import JsonObject, PaginatedResponse
from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.db.connection import Database
from pms.models import Project, ProjectStatus
from pms.models.api_key import ApiKey
from pms.repositories.state_transition_repository import StateTransitionRepository
from pms.services.actor_service import ActorService
from pms.services.generated_artifacts import (
    classify_project_operator_category,
    project_operator_category_label,
    project_operator_visibility_reason,
)
from pms.services.history_bundle_service import HistoryBundleService
from pms.services.lineage_service import LineageService, PlanLineageDashboard
from pms.services.project_service import ProjectService, ProjectSummary
from pms.services.queue_service import QueueService
from pms.services.rollup_utils import sort_items_by_bubbled_recency
from pms.services.task_service import TaskService
from pms.services.test_run_service import TestRunService
from pms.services.work_daily_service import WorkDailyService
from pms.services.work_snapshot_service import WorkSnapshotService

router = APIRouter()


class ProjectSummaryResponsePayload(TypedDict):
    """Project summary payload."""

    project: ProjectResponse
    stats: JsonObject | None
    health_score: float
    links: JsonObject
    next_steps: list[str]


class ProjectOperatorOverviewPayload(TypedDict):
    """Project operator control-plane payload."""

    project: ProjectResponse
    stats: JsonObject | None
    health_score: float
    daily: JsonObject
    lineage: JsonObject
    history: JsonObject
    focus_task: JsonObject | None
    links: JsonObject
    next_steps: list[str]
    params: JsonObject


class ProjectDashboardTotalsPayload(TypedDict):
    """Instance dashboard totals payload."""

    total_projects: int
    total_tasks: int
    completed_tasks: int
    blocked_tasks: int
    overdue_tasks: int


class ProjectDashboardCompletionContextPayload(TypedDict):
    """Recent terminal project context payload."""

    summary: str
    items: list[ProjectResponse]
    next_steps: list[str]


class ProjectDashboardResponsePayload(TypedDict):
    """Instance-wide project operator dashboard payload."""

    scope: JsonObject
    totals: ProjectDashboardTotalsPayload
    active_projects: list[ProjectResponse]
    recently_completed_projects: list[ProjectResponse]
    freshest_visible_activity: ProjectResponse | None
    freshest_visible_transition: ProjectResponse | None
    completion_context: ProjectDashboardCompletionContextPayload | None
    terminal_reason: str | None
    links: JsonObject
    next_steps: list[str]


def build_project_detail_links(project_id: str) -> JsonObject:
    """Build canonical project detail links for API surfaces."""
    return {
        "self": f"/api/v1/projects/{project_id}",
        "summary": f"/api/v1/projects/{project_id}/summary",
        "operator_overview": f"/api/v1/projects/{project_id}/operator-overview",
        "tasks": f"/api/v1/tasks?project_id={project_id}",
        "plans": f"/api/v1/plans?project_id={project_id}",
    }


def build_project_detail_next_steps(
    project_id: str,
    *,
    focus_task_id: str | None = None,
) -> list[str]:
    """Build continuation hints for project detail-like surfaces."""
    steps = [
        f"GET /api/v1/projects/{project_id}/summary",
        f"GET /api/v1/projects/{project_id}/operator-overview",
        f"GET /api/v1/tasks?project_id={project_id}",
        f"GET /api/v1/plans?project_id={project_id}",
    ]
    if focus_task_id is not None:
        steps.insert(0, f"GET /api/v1/tasks/{focus_task_id}")
    return steps


def _project_to_response(
    project: Project,
    *,
    stored_status: ProjectStatus | None = None,
    last_activity_at: object | None = None,
    last_transition_at: object | None = None,
    operator_category: str | None = None,
    terminal_reason: str | None = None,
    focus_task: JsonObject | None = None,
    links: JsonObject | None = None,
    next_steps: list[str] | None = None,
) -> ProjectResponse:
    """Convert project data into a lifecycle-aware response payload."""
    category = operator_category or classify_project_operator_category(
        project,
        effective_status=project.status.value,
    )
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        status=project.status.value,
        stored_status=(
            stored_status.value if hasattr(stored_status, "value") else stored_status
        ),
        tags=list(project.tags),
        org_id=project.org_id,
        portfolio_id=project.portfolio_id,
        program_id=project.program_id,
        product_id=project.product_id,
        created_at=project.created_at,
        updated_at=project.updated_at,
        last_activity_at=last_activity_at,
        last_transition_at=last_transition_at,
        operator_category=category,
        operator_category_label=project_operator_category_label(category),
        operator_visibility_reason=project_operator_visibility_reason(category),
        terminal_reason=terminal_reason,
        focus_task=focus_task,
        links=links or {},
        next_steps=next_steps or [],
    )


def _project_summary_to_response(
    summary: ProjectSummary,
    *,
    focus_task: JsonObject | None = None,
    links: JsonObject | None = None,
    next_steps: list[str] | None = None,
) -> ProjectResponse:
    """Convert a project summary into a lifecycle-aware response payload."""
    effective_status = summary.effective_status or summary.project.status
    category = classify_project_operator_category(
        summary.project,
        effective_status=effective_status.value,
    )
    return _project_to_response(
        Project(
            id=summary.project.id,
            name=summary.project.name,
            description=summary.project.description,
            status=effective_status,
            tags=summary.project.tags,
            org_id=summary.project.org_id,
            portfolio_id=summary.project.portfolio_id,
            program_id=summary.project.program_id,
            product_id=summary.project.product_id,
            workflow_id=summary.project.workflow_id,
            current_state=summary.project.current_state,
            workflow_metadata=summary.project.workflow_metadata,
            created_at=summary.project.created_at,
            updated_at=summary.project.updated_at,
        ),
        stored_status=summary.project.status,
        last_activity_at=summary.last_activity_at,
        last_transition_at=summary.last_transition_at,
        operator_category=category,
        terminal_reason=summary.terminal_reason,
        focus_task=focus_task,
        links=links,
        next_steps=next_steps,
    )


def _dashboard_project_response(summary: ProjectSummary) -> ProjectResponse:
    """Convert a project summary into an API dashboard item payload."""
    project_id = summary.project.id
    return _project_summary_to_response(
        summary,
        links=build_project_detail_links(project_id),
        next_steps=normalize_next_steps(*build_project_detail_next_steps(project_id)),
    )


def _dashboard_completion_summary(*, no_other_visible_active_work: bool) -> str:
    """Summarize recent terminal context for the aggregate dashboard."""
    if no_other_visible_active_work:
        return (
            "Recently completed scoped work remains terminal. No other visible "
            "active work is currently surfaced in the default operator view."
        )
    return (
        "Recently completed scoped work remains terminal even though this "
        "dashboard still shows unrelated active instance work."
    )


@router.post("/projects", response_model=ProjectResponse, status_code=201)
async def create_project(
    data: ProjectCreate,
    project_service: ProjectService = Depends(get_project_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.PROJECTS_WRITE)),
) -> ProjectResponse:
    """Create a new project."""
    try:
        project = await project_service.create_project(
            name=data.name,
            description=data.description,
            tags=data.tags,
            org_id=data.org_id,
            portfolio_id=data.portfolio_id,
            program_id=data.program_id,
            product_id=data.product_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    summary = await project_service.get_project_summary(project.id)
    if summary is None:
        return _project_to_response(
            project,
            stored_status=project.status,
            links=build_project_detail_links(project.id),
            next_steps=normalize_next_steps(
                *build_project_detail_next_steps(project.id)
            ),
        )
    return _project_summary_to_response(
        summary,
        links=build_project_detail_links(project.id),
        next_steps=normalize_next_steps(*build_project_detail_next_steps(project.id)),
    )


@router.get("/dashboard")
async def get_instance_project_dashboard(
    project_service: ProjectService = Depends(get_project_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.PROJECTS_READ)),
) -> ProjectDashboardResponsePayload:
    """Get an instance-wide lifecycle-aware project operator dashboard."""
    dashboard = await project_service.get_dashboard()
    projects = [
        project
        for project in await project_service.list_all_projects()
        if project.status != ProjectStatus.ARCHIVED
    ]
    summary_map = await project_service.build_project_summary_map(projects)
    sorted_projects = sort_items_by_bubbled_recency(
        projects,
        activity_of=lambda project: summary_map[project.id].last_activity_at,
        transition_of=lambda project: summary_map[project.id].last_transition_at,
        updated_of=lambda project: project.updated_at,
        label_of=lambda project: project.name,
        id_of=lambda project: project.id,
    )
    sorted_summaries = [
        summary_map[project.id]
        for project in sorted_projects
        if project.id in summary_map
    ]
    active_summaries = [
        summary
        for summary in sorted_summaries
        if (summary.effective_status or summary.project.status) == ProjectStatus.ACTIVE
    ]
    completed_summaries = [
        summary
        for summary in sorted_summaries
        if (summary.effective_status or summary.project.status)
        == ProjectStatus.COMPLETED
    ]
    visible_summaries = [*active_summaries, *completed_summaries[:5]]

    active_payloads = [
        _dashboard_project_response(summary) for summary in active_summaries
    ]
    completed_payloads = [
        _dashboard_project_response(summary) for summary in completed_summaries[:5]
    ]
    visible_payload_by_id = {
        payload.id: payload for payload in [*active_payloads, *completed_payloads]
    }

    def _activity_key(summary: ProjectSummary) -> tuple[str, str]:
        return (
            str(summary.last_activity_at or ""),
            str(summary.project.updated_at or ""),
        )

    def _transition_key(summary: ProjectSummary) -> tuple[str, str]:
        return (
            str(summary.last_transition_at or ""),
            str(summary.project.updated_at or ""),
        )

    completion_context: ProjectDashboardCompletionContextPayload | None = None
    terminal_reason: str | None = None
    if completed_payloads:
        completion_context = {
            "summary": _dashboard_completion_summary(
                no_other_visible_active_work=not active_payloads
            ),
            "items": completed_payloads,
            "next_steps": normalize_next_steps(
                f"GET /api/v1/projects/{completed_payloads[0].id}",
                "GET /api/v1/projects",
                "GET /api/v1/dashboard",
            ),
        }
        if not active_payloads:
            terminal_reason = "all surfaced projects are already terminal"

    next_steps = normalize_next_steps(
        *(
            [f"GET /api/v1/projects/{active_payloads[0].id}/operator-overview"]
            if active_payloads
            else []
        ),
        *(
            [f"GET /api/v1/projects/{completed_payloads[0].id}"]
            if completed_payloads
            else []
        ),
        "GET /api/v1/projects",
        "GET /api/v1/organizations/dashboard",
        "GET /dashboard",
    )

    return {
        "scope": {
            "kind": "instance_dashboard",
            "population": "all_non_archived_retained",
            "active_visible_projects": len(active_payloads),
            "recently_completed_projects": len(completed_payloads),
        },
        "totals": {
            "total_projects": dashboard.total_projects,
            "total_tasks": dashboard.total_tasks,
            "completed_tasks": dashboard.completed_tasks,
            "blocked_tasks": dashboard.blocked_tasks,
            "overdue_tasks": dashboard.overdue_tasks,
        },
        "active_projects": active_payloads,
        "recently_completed_projects": completed_payloads,
        "freshest_visible_activity": (
            visible_payload_by_id[max(visible_summaries, key=_activity_key).project.id]
            if visible_summaries
            else None
        ),
        "freshest_visible_transition": (
            visible_payload_by_id[
                max(visible_summaries, key=_transition_key).project.id
            ]
            if visible_summaries
            else None
        ),
        "completion_context": completion_context,
        "terminal_reason": terminal_reason,
        "links": {
            "self": "/api/v1/dashboard",
            "projects": "/api/v1/projects",
            "dashboard_ui": "/dashboard",
            "organizations_dashboard": "/api/v1/organizations/dashboard",
            "portfolios_dashboard": "/api/v1/portfolios/dashboard",
            "programs_dashboard": "/api/v1/programs/dashboard",
        },
        "next_steps": next_steps,
    }


@router.get("/projects")
async def list_projects(
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    project_service: ProjectService = Depends(get_project_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.PROJECTS_READ)),
) -> PaginatedResponse[ProjectResponse]:
    """List all projects."""
    status_filter = ProjectStatus(status) if status else None
    result = await project_service.list_projects(
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    params: QueryParamMap = {
        "status": status,
        "limit": limit,
        "offset": offset,
    }
    self_path = build_query_path("/api/v1/projects", params)
    next_path = next_page_path(
        path="/api/v1/projects",
        params=params,
        total_count=result.total_count,
        offset=result.offset,
        limit=result.limit,
    )
    next_steps = normalize_next_steps(
        "GET /api/v1/projects/{project_id}",
        "GET /api/v1/projects/{project_id}/summary",
        "GET /api/v1/tasks?project_id=<project_id>",
    )
    summary_map = await project_service.build_project_summary_map(result.items)

    return {
        "items": [
            _project_summary_to_response(
                summary_map.get(project.id)
                or ProjectSummary(
                    project=project,
                    effective_status=project.status,
                ),
                links=build_project_detail_links(project.id),
                next_steps=normalize_next_steps(
                    *build_project_detail_next_steps(project.id)
                ),
            )
            for project in result.items
        ],
        "total_count": result.total_count,
        "offset": result.offset,
        "limit": result.limit,
        "links": paginated_links(self_path=self_path, next_path=next_path),
        "next_steps": next_steps,
        "params": params,
    }


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    project_service: ProjectService = Depends(get_project_service),
    task_service: TaskService = Depends(get_task_service),
    api_key: ApiKey = Depends(get_api_key),
) -> ProjectResponse:
    """Get a project by ID."""
    # Check row-level access
    check_resource_scope(api_key, "projects", project_id, "read")

    summary = await project_service.get_project_summary(project_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Project not found")
    task_result = await task_service.list_tasks(
        project_id=project_id,
        include_subtasks=True,
        limit=1000,
        offset=0,
    )
    focus_task = select_focus_task(task_result.items)
    if summary.terminal_reason is not None:
        focus_task = None
    return _project_summary_to_response(
        summary,
        focus_task=task_focus_payload(focus_task) if focus_task is not None else None,
        links=build_project_detail_links(project_id),
        next_steps=normalize_next_steps(
            *build_project_detail_next_steps(
                project_id,
                focus_task_id=focus_task.id if focus_task is not None else None,
            )
        ),
    )


@router.get("/projects/{project_id}/summary")
async def get_project_summary(
    project_id: str,
    project_service: ProjectService = Depends(get_project_service),
    task_service: TaskService = Depends(get_task_service),
    api_key: ApiKey = Depends(get_api_key),
) -> ProjectSummaryResponsePayload:
    """Get a project summary with stats."""
    check_resource_scope(api_key, "projects", project_id, "read")

    summary = await project_service.get_project_summary(project_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Project not found")

    task_result = await task_service.list_tasks(
        project_id=project_id,
        include_subtasks=True,
        limit=1000,
        offset=0,
    )
    focus_task = select_focus_task(task_result.items)
    if summary.terminal_reason is not None:
        focus_task = None
    stats = summary.stats
    return {
        "project": _project_summary_to_response(
            summary,
            focus_task=task_focus_payload(focus_task)
            if focus_task is not None
            else None,
            links=build_project_detail_links(project_id),
            next_steps=normalize_next_steps(
                *build_project_detail_next_steps(
                    project_id,
                    focus_task_id=focus_task.id if focus_task is not None else None,
                )
            ),
        ),
        "stats": stats.to_dict() if stats else None,
        "health_score": summary.health_score,
        "links": build_project_detail_links(project_id),
        "next_steps": normalize_next_steps(
            *build_project_detail_next_steps(
                project_id,
                focus_task_id=focus_task.id if focus_task is not None else None,
            )
        ),
    }


async def _lineage_dashboard_to_payload(
    dashboard: PlanLineageDashboard,
    actor_service: ActorService,
) -> JsonObject:
    """Convert lineage dashboard models into JSON-ready payload."""
    assignee_refs = [
        actor_key
        for item in dashboard.items
        for task in item.tasks
        for actor_key in (task.assignee_id, task.assignee)
        if actor_key
    ]
    assignee_map = await resolve_actor_reference_map(actor_service, assignee_refs)
    return {
        "items": [
            {
                "plan": {
                    "id": item.plan.id,
                    "name": item.plan.name,
                    "description": item.plan.description,
                    "status": item.plan.status.value,
                    "format": item.plan.format.value,
                    "project_id": item.plan.project_id,
                    "goal_id": item.plan.goal_id,
                    "objective_id": item.plan.objective_id,
                    "task_ids": list(item.plan.task_ids),
                    "tags": list(item.plan.tags),
                    "created_at": item.plan.created_at,
                    "updated_at": item.plan.updated_at,
                },
                "stats": {
                    "total_tasks": item.total_tasks,
                    "completed_tasks": item.completed_tasks,
                    "blocked_tasks": item.blocked_tasks,
                    "total_test_runs": item.total_test_runs,
                    "latest_test_success": item.latest_test_success,
                    "latest_test_run_id": item.latest_test_run_id,
                },
                "last_activity_at": item.last_activity_at,
                "last_transition_at": item.last_transition_at,
                "evidence": {
                    "total": item.evidence.total,
                    "types": item.evidence.types,
                    "code_total": item.evidence.code_total,
                    "latest_code_reference": item.evidence.latest_code_reference,
                    "latest_code_created_at": item.evidence.latest_code_created_at,
                },
                "tasks": [
                    {
                        "id": task.id,
                        "title": task.title,
                        "status": task.status,
                        "project_id": task.project_id,
                        "assignee": actor_reference_payload(
                            task.assignee,
                            assignee_map,
                            actor_id=task.assignee_id,
                        ),
                        "due_date": task.due_date,
                        "evidence_gate": (
                            {
                                "blocked": task.evidence_gate.blocked,
                                "blocked_transitions": list(
                                    task.evidence_gate.blocked_transitions
                                ),
                                "reasons": list(task.evidence_gate.reasons),
                            }
                            if task.evidence_gate
                            else None
                        ),
                    }
                    for task in item.tasks
                ],
                "test_runs": [
                    {
                        "id": run.id,
                        "server_id": run.server_id,
                        "success": run.success,
                        "exit_code": run.exit_code,
                        "duration_seconds": run.duration_seconds,
                        "started_at": run.started_at,
                        "finished_at": run.finished_at,
                        "project_id": run.project_id,
                        "plan_id": run.plan_id,
                        "task_ids": list(run.task_ids),
                        "command": run.command,
                    }
                    for run in item.test_runs
                ],
            }
            for item in dashboard.items
        ],
        "totals": {
            "total_plans": dashboard.total_plans,
            "total_tasks": dashboard.total_tasks,
            "total_test_runs": dashboard.total_test_runs,
            "failed_test_runs": dashboard.failed_test_runs,
            "total_evidence": dashboard.total_evidence,
            "total_code_evidence": dashboard.total_code_evidence,
        },
        "total_count": dashboard.total_plans,
        "offset": dashboard.offset,
        "limit": dashboard.limit,
    }


@router.get("/projects/{project_id}/operator-overview")
async def get_project_operator_overview(
    project_id: str,
    task_limit: int = 5,
    test_limit: int = 5,
    queue_limit: int = 3,
    lineage_limit: int = 3,
    history_limit: int = 5,
    include_timeline: bool = True,
    include_history: bool = False,
    include_linked_history: bool = False,
    view: str = "overview",
    db: Database = Depends(get_db),
    project_service: ProjectService = Depends(get_project_service),
    snapshot_service: WorkSnapshotService = Depends(get_work_snapshot_service),
    queue_service: QueueService = Depends(get_queue_service),
    task_service: TaskService = Depends(get_task_service),
    test_run_service: TestRunService = Depends(get_test_run_service),
    lineage_service: LineageService = Depends(get_lineage_service),
    history_service: HistoryBundleService = Depends(get_history_bundle_service),
    api_key: ApiKey = Depends(get_api_key),
) -> ProjectOperatorOverviewPayload:
    """Get a single-entry operator overview for a project."""
    check_resource_scope(api_key, "projects", project_id, "read")

    if view not in {"overview", "detail", "trace"}:
        raise HTTPException(status_code=400, detail="Invalid view")

    summary = await project_service.get_project_summary(project_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Project not found")

    daily_service = WorkDailyService(
        snapshot_service=snapshot_service,
        queue_service=queue_service,
        task_service=task_service,
        project_service=project_service,
        transition_repo=StateTransitionRepository(db),
        test_run_service=test_run_service,
    )
    daily_summary = await daily_service.build_summary(
        scope_type="project",
        scope_id=project_id,
        task_limit=task_limit,
        test_limit=test_limit,
        queue_limit=queue_limit,
        stale_days=14,
        at_risk_days=7,
        include_timeline=include_timeline,
        timeline_limit=5,
        include_history=include_history,
        history_limit=history_limit,
        view=view,
    )
    if daily_summary is None:
        raise HTTPException(status_code=404, detail="Project work snapshot not found")

    lineage_dashboard = await lineage_service.get_plan_lineage_dashboard(
        project_id=project_id,
        limit=lineage_limit,
        offset=0,
        task_limit=task_limit,
        test_limit=test_limit,
    )
    history_bundle = await history_service.build_bundle(
        "project",
        project_id,
        include_linked=include_linked_history,
        include_linked_history=include_linked_history,
        history_limit=history_limit,
        linked_limit=queue_limit,
    )
    if history_bundle is None:
        raise HTTPException(status_code=404, detail="Project history not found")

    actor_service = ActorService(
        db,
        EventStore(db),
        RevisionStore(db),
        MetricsCollector(db),
    )

    params: QueryParamMap = {
        "task_limit": task_limit,
        "test_limit": test_limit,
        "queue_limit": queue_limit,
        "lineage_limit": lineage_limit,
        "history_limit": history_limit,
        "include_timeline": include_timeline,
        "include_history": include_history,
        "include_linked_history": include_linked_history,
        "view": view,
    }
    self_path = build_query_path(
        f"/api/v1/projects/{project_id}/operator-overview", params
    )
    links: JsonObject = {
        "self": self_path,
        "project": f"/api/v1/projects/{project_id}",
        "project_summary": f"/api/v1/projects/{project_id}/summary",
        "daily": build_query_path(
            f"/api/v1/work-snapshots/project/{project_id}/daily",
            {
                "task_limit": task_limit,
                "test_limit": test_limit,
                "queue_limit": queue_limit,
                "include_timeline": include_timeline,
                "include_history": include_history,
                "history_limit": history_limit,
                "view": view,
            },
        ),
        "lineage": build_query_path(
            "/api/v1/plans/lineage",
            {
                "project_id": project_id,
                "limit": lineage_limit,
                "task_limit": task_limit,
                "test_limit": test_limit,
            },
        ),
        "history_bundle": build_query_path(
            f"/api/v1/revisions/project/{project_id}/bundle",
            {
                "include_linked": include_linked_history,
                "include_linked_history": include_linked_history,
                "history_limit": history_limit,
                "linked_limit": queue_limit,
            },
        ),
    }
    next_steps = normalize_next_steps(
        f"GET /api/v1/work-snapshots/project/{project_id}/daily",
        f"GET /api/v1/plans/lineage?project_id={project_id}",
        f"GET /api/v1/revisions/project/{project_id}/bundle",
        "GET /api/v1/tasks?project_id=<project_id>",
    )
    focus_result = await task_service.list_tasks(
        project_id=project_id,
        include_subtasks=True,
        limit=1000,
        offset=0,
    )
    focus_task = select_focus_task(focus_result.items)
    if summary.terminal_reason is not None:
        focus_task = None
    stats = summary.stats
    return {
        "project": _project_summary_to_response(
            summary,
            focus_task=task_focus_payload(focus_task)
            if focus_task is not None
            else None,
            links=build_project_detail_links(project_id),
            next_steps=normalize_next_steps(
                *build_project_detail_next_steps(
                    project_id,
                    focus_task_id=focus_task.id if focus_task is not None else None,
                )
            ),
        ),
        "stats": stats.to_dict() if stats else None,
        "health_score": summary.health_score,
        "daily": daily_summary.to_dict(),
        "lineage": await _lineage_dashboard_to_payload(
            lineage_dashboard, actor_service
        ),
        "history": history_bundle.to_dict(),
        "focus_task": task_focus_payload(focus_task)
        if focus_task is not None
        else None,
        "links": links,
        "next_steps": next_steps,
        "params": params,
    }


@router.patch("/projects/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str,
    data: ProjectUpdate,
    project_service: ProjectService = Depends(get_project_service),
    task_service: TaskService = Depends(get_task_service),
    api_key: ApiKey = Depends(get_api_key),
) -> ProjectResponse:
    """Update a project."""
    # Check row-level access
    check_resource_scope(api_key, "projects", project_id, "write")

    # Convert status string to enum if provided
    status_enum = ProjectStatus(data.status) if data.status else None

    try:
        project = await project_service.update_project(
            project_id=project_id,
            name=data.name,
            description=data.description,
            tags=data.tags,
            status=status_enum,
            product_id=data.product_id,
            org_id=data.org_id,
            portfolio_id=data.portfolio_id,
            program_id=data.program_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    summary = await project_service.get_project_summary(project.id)
    if summary is None:
        return _project_to_response(
            project,
            stored_status=project.status,
            links=build_project_detail_links(project.id),
            next_steps=normalize_next_steps(
                *build_project_detail_next_steps(project.id)
            ),
        )
    task_result = await task_service.list_tasks(
        project_id=project_id,
        include_subtasks=True,
        limit=1000,
        offset=0,
    )
    focus_task = select_focus_task(task_result.items)
    if summary.terminal_reason is not None:
        focus_task = None
    return _project_summary_to_response(
        summary,
        focus_task=task_focus_payload(focus_task) if focus_task is not None else None,
        links=build_project_detail_links(project.id),
        next_steps=normalize_next_steps(
            *build_project_detail_next_steps(
                project.id,
                focus_task_id=focus_task.id if focus_task is not None else None,
            )
        ),
    )
