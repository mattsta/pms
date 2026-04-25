"""Plans API routes."""

from dataclasses import replace
from datetime import datetime
from typing import TypedDict

from fastapi import APIRouter, Depends, HTTPException

from pms.api.actor_payloads import actor_reference_payload, resolve_actor_reference_map
from pms.api.auth import Scopes, require_scope
from pms.api.dependencies import (
    get_db,
    get_lineage_service,
    get_plan_service,
    get_plan_test_job_service,
    get_task_service,
    get_test_run_service,
)
from pms.api.models import (
    EnvVarPair,
    PlanCreate,
    PlanResponse,
    PlanTestJobCreate,
    PlanTestJobListResponse,
    PlanTestJobResponse,
    PlanTestJobRunResponse,
    PlanTestJobUpdate,
    PlanUpdate,
    TestRunResponse,
)
from pms.api.routes.detail_contracts import (
    build_plan_detail_links,
    build_plan_detail_next_steps,
    select_focus_task,
    task_focus_payload,
)
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
from pms.models import Plan, PlanFormat, PlanStatus
from pms.models.api_key import ApiKey
from pms.models.plan_test_job import PlanTestJob
from pms.services.actor_service import ActorService
from pms.services.lineage_service import LineageService
from pms.services.plan_service import PlanService
from pms.services.plan_test_job_service import PlanTestJobService
from pms.services.task_service import TaskService
from pms.services.test_run_service import TestRunRecord, TestRunService

router = APIRouter()


class PlanLineagePlanPayload(TypedDict):
    """Plan summary payload for lineage dashboard."""

    id: str
    name: str
    description: str | None
    status: str
    stored_status: str | None
    format: str
    project_id: str | None
    goal_id: str | None
    objective_id: str | None
    task_ids: list[str]
    tags: list[str]
    created_at: datetime
    updated_at: datetime
    terminal_reason: str | None


class PlanLineageStatsPayload(TypedDict):
    """Lineage stats payload."""

    total_tasks: int
    completed_tasks: int
    blocked_tasks: int
    total_test_runs: int
    latest_test_success: bool | None
    latest_test_run_id: str | None


class PlanLineageEvidencePayload(TypedDict):
    """Lineage evidence summary payload."""

    total: int
    types: dict[str, int]
    code_total: int
    latest_code_reference: str | None
    latest_code_created_at: datetime | None


class PlanLineageTaskPayload(TypedDict):
    """Lineage task payload."""

    id: str
    title: str
    status: str
    project_id: str | None
    assignee: JsonObject | None
    due_date: datetime | None
    evidence_gate: JsonObject | None


class PlanLineageRunPayload(TypedDict):
    """Lineage test run payload."""

    id: str
    server_id: str
    success: bool
    exit_code: int | None
    duration_seconds: float | None
    started_at: datetime
    finished_at: datetime
    project_id: str | None
    plan_id: str | None
    task_ids: list[str]
    command: str | None


class PlanLineageItemPayload(TypedDict):
    """Lineage dashboard item payload."""

    plan: PlanLineagePlanPayload
    stats: PlanLineageStatsPayload
    last_activity_at: datetime | None
    last_transition_at: datetime | None
    evidence: PlanLineageEvidencePayload
    tasks: list[PlanLineageTaskPayload]
    test_runs: list[PlanLineageRunPayload]


class PlanLineageTotalsPayload(TypedDict):
    """Lineage dashboard totals payload."""

    total_plans: int
    total_tasks: int
    total_test_runs: int
    failed_test_runs: int
    total_evidence: int
    total_code_evidence: int


class PlanLineageDashboardPayload(TypedDict):
    """Plan lineage dashboard response payload."""

    items: list[PlanLineageItemPayload]
    totals: PlanLineageTotalsPayload
    total_count: int
    offset: int
    limit: int
    links: JsonObject
    next_steps: list[str]
    params: JsonObject


def _job_to_response(job: PlanTestJob) -> PlanTestJobResponse:
    return PlanTestJobResponse(
        id=job.id,
        plan_id=job.plan_id,
        name=job.name,
        description=job.description,
        mode=job.mode,
        project_path=job.project_path,
        test_command=job.test_command,
        setup_command=job.setup_command,
        working_dir=job.working_dir,
        env_vars=[EnvVarPair(key=key, value=value) for key, value in job.env_vars],
        timeout=job.timeout,
        capture_logs=list(job.capture_logs),
        save_artifacts=list(job.save_artifacts),
        task_ids=list(job.task_ids),
        transition_on_success=job.transition_on_success,
        transition_on_failure=job.transition_on_failure,
        transition_by=job.transition_by,
        transition_reason=job.transition_reason,
        project_id=job.project_id,
        server_id=job.server_id,
        server_name=job.server_name,
        remote_path=job.remote_path,
        exclude_patterns=list(job.exclude_patterns) if job.exclude_patterns else None,
        stream_output=job.stream_output,
        created_at=job.created_at,
        updated_at=job.updated_at,
        archived_at=job.archived_at,
    )


def _run_to_response(run: TestRunRecord) -> TestRunResponse:
    return TestRunResponse(
        id=run.id,
        server_id=run.server_id,
        project_id=run.project_id,
        success=run.success,
        exit_code=run.exit_code,
        duration_seconds=run.duration_seconds,
        started_at=run.started_at,
        finished_at=run.finished_at,
        command=run.command,
        runner=run.runner,
        plan_id=run.plan_id,
        task_ids=list(run.task_ids),
        stdout=run.stdout,
        stderr=run.stderr,
        logs=run.logs or None,
        artifacts=run.artifacts or None,
    )


def _plan_to_response(
    plan: Plan,
    *,
    stored_status: PlanStatus | None = None,
    last_activity_at: datetime | None = None,
    last_transition_at: datetime | None = None,
    links: JsonObject | None = None,
    next_steps: list[str] | None = None,
    focus_task: JsonObject | None = None,
    terminal_reason: str | None = None,
) -> PlanResponse:
    return PlanResponse(
        id=plan.id,
        name=plan.name,
        description=plan.description,
        status=plan.status.value,
        stored_status=(
            stored_status.value if hasattr(stored_status, "value") else stored_status
        ),
        format=plan.format.value,
        content=plan.content,
        product_id=plan.product_id,
        project_id=plan.project_id,
        goal_id=plan.goal_id,
        objective_id=plan.objective_id,
        task_ids=list(plan.task_ids),
        tags=list(plan.tags),
        created_at=plan.created_at,
        updated_at=plan.updated_at,
        last_activity_at=last_activity_at,
        last_transition_at=last_transition_at,
        links=links or {},
        next_steps=next_steps or [],
        focus_task=focus_task,
        terminal_reason=terminal_reason,
    )


@router.post("/plans", response_model=PlanResponse, status_code=201)
async def create_plan(
    data: PlanCreate,
    plan_service: PlanService = Depends(get_plan_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.PLANS_WRITE)),
) -> PlanResponse:
    """Create a new plan."""
    try:
        status = PlanStatus(data.status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid plan status") from exc

    try:
        format = PlanFormat(data.format)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid plan format") from exc

    try:
        plan = await plan_service.create_plan(
            name=data.name,
            description=data.description,
            status=status,
            format=format,
            content=data.content,
            product_id=data.product_id,
            project_id=data.project_id,
            goal_id=data.goal_id,
            objective_id=data.objective_id,
            task_ids=data.task_ids,
            tags=data.tags,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    stored_status = plan.status
    lifecycle_rollup = (await plan_service.get_lifecycle_rollup_map([plan])).get(
        plan.id
    )
    if lifecycle_rollup is not None:
        plan = replace(plan, status=lifecycle_rollup.effective_status)
    activity_map = await plan_service.get_last_activity_map([plan])
    transition_map = await plan_service.get_last_transition_map([plan.id])
    return _plan_to_response(
        plan,
        stored_status=stored_status,
        last_activity_at=activity_map.get(plan.id),
        last_transition_at=transition_map.get(plan.id),
        terminal_reason=(
            lifecycle_rollup.terminal_reason if lifecycle_rollup is not None else None
        ),
    )


@router.get("/plans")
async def list_plans(
    status: str | None = None,
    project_id: str | None = None,
    product_id: str | None = None,
    goal_id: str | None = None,
    objective_id: str | None = None,
    task_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
    plan_service: PlanService = Depends(get_plan_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.PLANS_READ)),
) -> PaginatedResponse[PlanResponse]:
    """List plans with optional filters."""
    status_filter = PlanStatus(status) if status else None

    (
        result,
        lifecycle_rollups,
        stored_status_map,
    ) = await plan_service.list_effective_plans(
        status=status_filter,
        project_id=project_id,
        product_id=product_id,
        goal_id=goal_id,
        objective_id=objective_id,
        task_id=task_id,
        limit=limit,
        offset=offset,
    )
    activity_map = await plan_service.get_last_activity_map(result.items)
    plan_ids = [plan.id for plan in result.items]
    transition_map = await plan_service.get_last_transition_map(plan_ids)
    params: QueryParamMap = {
        "status": status,
        "project_id": project_id,
        "product_id": product_id,
        "goal_id": goal_id,
        "objective_id": objective_id,
        "task_id": task_id,
        "limit": limit,
        "offset": offset,
    }
    self_path = build_query_path("/api/v1/plans", params)
    next_path = next_page_path(
        path="/api/v1/plans",
        params=params,
        total_count=result.total_count,
        offset=result.offset,
        limit=result.limit,
    )
    next_steps = normalize_next_steps(
        "GET /api/v1/plans/{plan_id}",
        "GET /api/v1/plans/lineage?plan_id=<plan_id>",
        "GET /api/v1/plans/{plan_id}/test-jobs",
    )

    return {
        "items": [
            _plan_to_response(
                plan,
                stored_status=stored_status_map.get(plan.id),
                last_activity_at=activity_map.get(plan.id),
                last_transition_at=transition_map.get(plan.id),
                terminal_reason=(
                    lifecycle_rollups.get(plan.id).terminal_reason
                    if lifecycle_rollups.get(plan.id) is not None
                    else None
                ),
            )
            for plan in result.items
        ],
        "total_count": result.total_count,
        "offset": result.offset,
        "limit": result.limit,
        "links": paginated_links(self_path=self_path, next_path=next_path),
        "next_steps": next_steps,
        "params": params,
    }


@router.get("/plans/lineage")
async def get_plan_lineage_dashboard(
    status: str | None = None,
    project_id: str | None = None,
    plan_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
    task_limit: int = 10,
    test_limit: int = 5,
    db: Database = Depends(get_db),
    lineage_service: LineageService = Depends(get_lineage_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.PLANS_READ)),
) -> PlanLineageDashboardPayload:
    """Get plan → task → test lineage dashboard."""
    status_filter = PlanStatus(status) if status else None
    dashboard = await lineage_service.get_plan_lineage_dashboard(
        status=status_filter,
        project_id=project_id,
        plan_id=plan_id,
        limit=limit,
        offset=offset,
        task_limit=task_limit,
        test_limit=test_limit,
    )
    params: QueryParamMap = {
        "status": status,
        "project_id": project_id,
        "plan_id": plan_id,
        "limit": limit,
        "offset": offset,
        "task_limit": task_limit,
        "test_limit": test_limit,
    }
    self_path = build_query_path("/api/v1/plans/lineage", params)
    next_path = next_page_path(
        path="/api/v1/plans/lineage",
        params=params,
        total_count=dashboard.total_plans,
        offset=dashboard.offset,
        limit=dashboard.limit,
    )
    links: JsonObject = paginated_links(self_path=self_path, next_path=next_path)
    links.update(
        {
            "plan_template": "/api/v1/plans/{plan_id}",
            "plan_test_jobs_template": "/api/v1/plans/{plan_id}/test-jobs",
            "proof_bundle_template": "/api/v1/tasks/{task_id}/proof-bundle",
        }
    )
    next_steps = normalize_next_steps(
        "GET /api/v1/plans/{plan_id}",
        "GET /api/v1/plans/{plan_id}/test-jobs",
        "GET /api/v1/tasks/{task_id}/proof-bundle",
    )
    actor_service = ActorService(
        db,
        EventStore(db),
        RevisionStore(db),
        MetricsCollector(db),
    )
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
                    "stored_status": item.stored_status,
                    "format": item.plan.format.value,
                    "project_id": item.plan.project_id,
                    "goal_id": item.plan.goal_id,
                    "objective_id": item.plan.objective_id,
                    "task_ids": list(item.plan.task_ids),
                    "tags": list(item.plan.tags),
                    "created_at": item.plan.created_at,
                    "updated_at": item.plan.updated_at,
                    "terminal_reason": item.terminal_reason,
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
        "links": links,
        "next_steps": next_steps,
        "params": params,
    }


@router.get("/plans/{plan_id}", response_model=PlanResponse)
async def get_plan(
    plan_id: str,
    plan_service: PlanService = Depends(get_plan_service),
    task_service: TaskService = Depends(get_task_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.PLANS_READ)),
) -> PlanResponse:
    """Get a plan by ID."""
    plan = await plan_service.get_plan(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")

    stored_status = plan.status
    lifecycle_rollup = (await plan_service.get_lifecycle_rollup_map([plan])).get(
        plan.id
    )
    if lifecycle_rollup is not None:
        plan = replace(plan, status=lifecycle_rollup.effective_status)
    activity_map = await plan_service.get_last_activity_map([plan])
    transition_map = await plan_service.get_last_transition_map([plan.id])
    tasks = (
        await task_service.get_tasks_by_ids(list(plan.task_ids))
        if plan.task_ids
        else []
    )
    focus_task = select_focus_task(tasks)
    terminal_reason = (
        lifecycle_rollup.terminal_reason if lifecycle_rollup is not None else None
    )
    if terminal_reason is not None:
        focus_task = None
    links = build_plan_detail_links(plan.id)
    next_steps = normalize_next_steps(
        *build_plan_detail_next_steps(
            plan.id,
            focus_task_id=focus_task.id if focus_task is not None else None,
        )
    )
    return _plan_to_response(
        plan,
        stored_status=stored_status,
        last_activity_at=activity_map.get(plan.id),
        last_transition_at=transition_map.get(plan.id),
        links=links,
        next_steps=next_steps,
        focus_task=task_focus_payload(focus_task) if focus_task is not None else None,
        terminal_reason=terminal_reason,
    )


@router.patch("/plans/{plan_id}", response_model=PlanResponse)
async def update_plan(
    plan_id: str,
    data: PlanUpdate,
    plan_service: PlanService = Depends(get_plan_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.PLANS_WRITE)),
) -> PlanResponse:
    """Update a plan."""
    status_enum = PlanStatus(data.status) if data.status else None
    format_enum = PlanFormat(data.format) if data.format else None

    try:
        plan = await plan_service.update_plan(
            plan_id=plan_id,
            name=data.name,
            description=data.description,
            status=status_enum,
            format=format_enum,
            content=data.content,
            product_id=data.product_id,
            project_id=data.project_id,
            goal_id=data.goal_id,
            objective_id=data.objective_id,
            task_ids=data.task_ids,
            tags=data.tags,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")

    stored_status = plan.status
    lifecycle_rollup = (await plan_service.get_lifecycle_rollup_map([plan])).get(
        plan.id
    )
    if lifecycle_rollup is not None:
        plan = replace(plan, status=lifecycle_rollup.effective_status)
    activity_map = await plan_service.get_last_activity_map([plan])
    transition_map = await plan_service.get_last_transition_map([plan.id])
    return _plan_to_response(
        plan,
        stored_status=stored_status,
        last_activity_at=activity_map.get(plan.id),
        last_transition_at=transition_map.get(plan.id),
        terminal_reason=(
            lifecycle_rollup.terminal_reason if lifecycle_rollup is not None else None
        ),
    )


@router.post(
    "/plans/{plan_id}/test-jobs",
    response_model=PlanTestJobResponse,
    status_code=201,
)
async def create_plan_test_job(
    plan_id: str,
    data: PlanTestJobCreate,
    service: PlanTestJobService = Depends(get_plan_test_job_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.PLANS_WRITE)),
) -> PlanTestJobResponse:
    """Create a plan-linked test job."""
    env_vars = tuple((item.key, item.value) for item in data.env_vars)
    try:
        job = await service.create_job(
            plan_id=plan_id,
            name=data.name,
            description=data.description,
            mode=data.mode,
            project_path=data.project_path,
            test_command=data.test_command,
            setup_command=data.setup_command,
            working_dir=data.working_dir,
            env_vars=env_vars,
            timeout=data.timeout,
            capture_logs=tuple(data.capture_logs),
            save_artifacts=tuple(data.save_artifacts),
            task_ids=tuple(data.task_ids),
            transition_on_success=data.transition_on_success,
            transition_on_failure=data.transition_on_failure,
            transition_by=data.transition_by,
            transition_reason=data.transition_reason,
            project_id=data.project_id,
            server_id=data.server_id,
            server_name=data.server_name,
            remote_path=data.remote_path,
            exclude_patterns=tuple(data.exclude_patterns)
            if data.exclude_patterns is not None
            else None,
            stream_output=data.stream_output,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _job_to_response(job)


@router.get(
    "/plans/{plan_id}/test-jobs",
    response_model=PlanTestJobListResponse,
)
async def list_plan_test_jobs(
    plan_id: str,
    limit: int = 100,
    offset: int = 0,
    include_archived: bool = False,
    service: PlanTestJobService = Depends(get_plan_test_job_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.PLANS_READ)),
) -> PlanTestJobListResponse:
    """List test jobs for a plan."""
    result = await service.list_jobs(
        plan_id=plan_id,
        limit=limit,
        offset=offset,
        include_archived=include_archived,
    )
    params: QueryParamMap = {
        "limit": limit,
        "offset": offset,
        "include_archived": include_archived,
    }
    self_path = build_query_path(f"/api/v1/plans/{plan_id}/test-jobs", params)
    next_path = next_page_path(
        path=f"/api/v1/plans/{plan_id}/test-jobs",
        params=params,
        total_count=result.total_count,
        offset=result.offset,
        limit=result.limit,
    )
    next_steps = normalize_next_steps(
        "POST /api/v1/plans/{plan_id}/test-jobs",
        "GET /api/v1/plans/{plan_id}/test-jobs/{job_id}",
        "POST /api/v1/plans/{plan_id}/test-jobs/{job_id}/run",
    )

    return PlanTestJobListResponse(
        items=[_job_to_response(job) for job in result.items],
        total_count=result.total_count,
        offset=result.offset,
        limit=result.limit,
        links=paginated_links(self_path=self_path, next_path=next_path),
        next_steps=next_steps,
        params=params,
    )


@router.get(
    "/plans/{plan_id}/test-jobs/{job_id}",
    response_model=PlanTestJobResponse,
)
async def get_plan_test_job(
    plan_id: str,
    job_id: str,
    service: PlanTestJobService = Depends(get_plan_test_job_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.PLANS_READ)),
) -> PlanTestJobResponse:
    """Get a plan test job by ID."""
    job = await service.get_job(job_id)
    if job is None or job.plan_id != plan_id:
        raise HTTPException(status_code=404, detail="Plan test job not found")
    return _job_to_response(job)


@router.patch(
    "/plans/{plan_id}/test-jobs/{job_id}",
    response_model=PlanTestJobResponse,
)
async def update_plan_test_job(
    plan_id: str,
    job_id: str,
    data: PlanTestJobUpdate,
    service: PlanTestJobService = Depends(get_plan_test_job_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.PLANS_WRITE)),
) -> PlanTestJobResponse:
    """Update a plan test job."""
    existing = await service.get_job(job_id)
    if existing is None or existing.plan_id != plan_id:
        raise HTTPException(status_code=404, detail="Plan test job not found")

    env_vars = None
    if data.env_vars is not None:
        env_vars = tuple((item.key, item.value) for item in data.env_vars)

    try:
        job = await service.update_job(
            job_id=job_id,
            plan_id=plan_id,
            name=data.name,
            description=data.description,
            mode=data.mode,
            project_path=data.project_path,
            test_command=data.test_command,
            setup_command=data.setup_command,
            working_dir=data.working_dir,
            env_vars=env_vars,
            timeout=data.timeout,
            capture_logs=tuple(data.capture_logs)
            if data.capture_logs is not None
            else None,
            save_artifacts=tuple(data.save_artifacts)
            if data.save_artifacts is not None
            else None,
            task_ids=tuple(data.task_ids) if data.task_ids is not None else None,
            transition_on_success=data.transition_on_success,
            transition_on_failure=data.transition_on_failure,
            transition_by=data.transition_by,
            transition_reason=data.transition_reason,
            project_id=data.project_id,
            server_id=data.server_id,
            server_name=data.server_name,
            remote_path=data.remote_path,
            exclude_patterns=tuple(data.exclude_patterns)
            if data.exclude_patterns is not None
            else None,
            stream_output=data.stream_output,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if job is None:
        raise HTTPException(status_code=404, detail="Plan test job not found")
    return _job_to_response(job)


@router.delete("/plans/{plan_id}/test-jobs/{job_id}")
async def delete_plan_test_job(
    plan_id: str,
    job_id: str,
    service: PlanTestJobService = Depends(get_plan_test_job_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.PLANS_WRITE)),
) -> dict[str, str]:
    """Delete a plan test job."""
    job = await service.get_job(job_id)
    if job is None or job.plan_id != plan_id:
        raise HTTPException(status_code=404, detail="Plan test job not found")
    await service.delete_job(job_id)
    return {"status": "deleted", "id": job_id}


@router.post(
    "/plans/{plan_id}/test-jobs/{job_id}/restore",
    response_model=PlanTestJobResponse,
)
async def restore_plan_test_job(
    plan_id: str,
    job_id: str,
    service: PlanTestJobService = Depends(get_plan_test_job_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.PLANS_WRITE)),
) -> PlanTestJobResponse:
    """Restore a plan test job."""
    job = await service.restore_job(job_id)
    if job is None or job.plan_id != plan_id:
        raise HTTPException(status_code=404, detail="Plan test job not found")
    return _job_to_response(job)


@router.post(
    "/plans/{plan_id}/test-jobs/{job_id}/run",
    response_model=PlanTestJobRunResponse,
)
async def run_plan_test_job(
    plan_id: str,
    job_id: str,
    include_output: bool = False,
    include_logs: bool = False,
    include_artifacts: bool = False,
    service: PlanTestJobService = Depends(get_plan_test_job_service),
    test_run_service: TestRunService = Depends(get_test_run_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.PLANS_WRITE)),
) -> PlanTestJobRunResponse:
    """Run a plan test job and return the resulting test run."""
    job = await service.get_job(job_id)
    if job is None or job.plan_id != plan_id:
        raise HTTPException(status_code=404, detail="Plan test job not found")

    try:
        run = await service.run_job(job_id)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if run is None:
        raise HTTPException(status_code=404, detail="Plan test job not found")

    test_run = await test_run_service.get_test_run(
        run.result.run_id,
        include_output=include_output,
        include_logs=include_logs,
        include_artifacts=include_artifacts,
    )
    if test_run is None:
        raise HTTPException(status_code=500, detail="Test run not found")

    return PlanTestJobRunResponse(
        job=_job_to_response(run.job),
        test_run=_run_to_response(test_run),
    )
