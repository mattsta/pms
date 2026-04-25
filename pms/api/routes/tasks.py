"""Tasks API routes."""

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, TypedDict
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query

from pms.api.actor_payloads import (
    actor_reference_payload,
    checkout_payload,
    resolve_actor_reference_map,
)
from pms.api.auth import Scopes, check_resource_scope, get_api_key, require_scope
from pms.api.dependencies import (
    get_plan_service,
    get_project_service,
    get_proof_bundle_service,
    get_task_evidence_service,
    get_task_service,
)
from pms.api.models import (
    DuplicateMergeConflictResponse,
    DuplicateMergePreviewItemResponse,
    DuplicateMergePreviewResponse,
    ProofBundleResponse,
    ProofBundleSearchItemResponse,
    ProofBundleSearchResponse,
    ProofBundleSummaryResponse,
    TaskActionRequest,
    TaskCompletionActionResponse,
    TaskCreate,
    TaskDependencyCreate,
    TaskDependencyDetailResponse,
    TaskDependencyGraphResponse,
    TaskDependencyResponse,
    TaskDuplicateMerge,
    TaskDuplicateMergePreview,
    TaskEvidenceCreate,
    TaskEvidenceResponse,
    TaskResponse,
    TaskTreeNode,
    TaskTreeResponse,
    TaskUpdate,
    TestRunResponse,
    TestRunSummaryResponse,
)
from pms.api.routes.detail_contracts import (
    build_plan_detail_links,
    build_task_detail_links,
    build_task_detail_next_steps,
)
from pms.api.types import JsonObject, PaginatedResponse
from pms.models import DependencyType, DuplicateTaskGroup, Priority, Task, TaskStatus
from pms.models.api_key import ApiKey
from pms.repositories.plan_repository import PlanRepository
from pms.services.actor_service import ActorService
from pms.services.plan_service import PlanService
from pms.services.project_service import ProjectService
from pms.services.proof_bundle_service import ProofBundleService
from pms.services.task_evidence_service import TaskEvidenceItem, TaskEvidenceService
from pms.services.task_service import TaskService, TaskTree
from pms.services.test_run_service import TestRunRecord

router = APIRouter()


class DuplicateTaskGroupPayload(TypedDict):
    """Duplicate task group payload."""

    normalized_title: str
    count: int
    suggested_primary_id: str | None
    suggested_primary_reason: str | None
    last_activity_at: datetime | None
    tasks: list[TaskResponse]
    links: dict[str, str | None]
    next_steps: list[str]


class DuplicateTaskListResponsePayload(TypedDict):
    """Duplicate task list response payload."""

    items: list[DuplicateTaskGroupPayload]
    total_count: int
    offset: int
    limit: int
    links: dict[str, str | None]
    next_steps: list[str]
    params: dict[str, str | int | bool | list[str] | None]


class MergeDuplicateTasksResponsePayload(TypedDict):
    """Duplicate merge response payload."""

    primary_task: TaskResponse
    duplicate_tasks: list[TaskResponse]
    links_added: int
    duplicates_cancelled: int
    links: dict[str, str]
    next_steps: list[str]


async def _run_task_action(
    operation: Callable[[], Awaitable[Task | None]],
) -> Task:
    """Run a task mutation and normalize common conflict/not-found responses."""
    try:
        task = await operation()
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    return task


def _parse_datetime(value: str | None, label: str) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=f"Invalid {label} timestamp"
        ) from exc


def _parse_statuses(values: list[str] | None) -> list[TaskStatus] | None:
    if not values:
        return None
    statuses: list[TaskStatus] = []
    for status in values:
        try:
            statuses.append(TaskStatus(status.lower()))
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Invalid status. Use: todo, in_progress, blocked, in_review, done, cancelled"
                ),
            ) from exc
    return statuses


def _parse_priorities(values: list[str] | None) -> list[Priority] | None:
    if not values:
        return None
    priorities: list[Priority] = []
    for priority in values:
        try:
            priorities.append(Priority(priority.lower()))
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail="Invalid priority. Use: low, medium, high, critical",
            ) from exc
    return priorities


type QueryParamValue = str | int | bool | list[str] | None
type QueryParamMap = dict[str, QueryParamValue]


def _build_query_path(path: str, params: QueryParamMap) -> str:
    query_items: list[tuple[str, str]] = []
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, list):
            for item in value:
                query_items.append((key, item))
            continue
        if isinstance(value, bool):
            query_items.append((key, str(value).lower()))
            continue
        query_items.append((key, str(value)))
    query_string = urlencode(query_items)
    return f"{path}?{query_string}" if query_string else path


def _task_query_links(
    *, self_path: str, next_path: str | None
) -> dict[str, str | None]:
    return {
        "self": self_path,
        "next": next_path,
        "list": "/api/v1/tasks",
        "search": "/api/v1/tasks/search",
        "ready": "/api/v1/tasks/ready",
        "stale": "/api/v1/tasks/stale",
        "duplicates": "/api/v1/tasks/duplicates",
        "dashboard": "/dashboard",
        "guide": "/api/v1/",
        "task_detail_template": "/api/v1/tasks/{task_id}",
    }


def _normalize_next_steps(*steps: str) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for step in steps:
        candidate = step.strip() if step else ""
        if not candidate:
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        normalized.append(candidate)
    return normalized


def _task_evidence_item_to_response(
    item: TaskEvidenceItem,
) -> TaskEvidenceResponse:
    return TaskEvidenceResponse(
        id=item.evidence.id,
        task_id=item.evidence.task_id,
        evidence_type=item.evidence.evidence_type,
        reference=item.evidence.reference,
        description=item.evidence.description,
        metadata=item.evidence.metadata,
        created_by=item.evidence.created_by,
        created_at=item.evidence.created_at,
        test_run=TestRunSummaryResponse(
            id=item.test_run.id,
            success=item.test_run.success,
            exit_code=item.test_run.exit_code,
            duration_seconds=item.test_run.duration_seconds,
            started_at=item.test_run.started_at,
            finished_at=item.test_run.finished_at,
            command=item.test_run.command,
            stdout=item.test_run.stdout,
            stderr=item.test_run.stderr,
        )
        if item.test_run
        else None,
    )


def _test_run_record_to_response(record: TestRunRecord) -> TestRunResponse:
    return TestRunResponse(
        id=record.id,
        server_id=record.server_id,
        project_id=record.project_id,
        success=record.success,
        exit_code=record.exit_code,
        duration_seconds=record.duration_seconds,
        started_at=record.started_at,
        finished_at=record.finished_at,
        command=record.command,
        runner=record.runner,
        plan_id=record.plan_id,
        task_ids=list(record.task_ids),
        stdout=record.stdout,
        stderr=record.stderr,
        logs=record.logs or None,
        artifacts=record.artifacts or None,
    )


def _proof_bundle_search_item_to_response(
    item: ProofBundleService.SearchItem,
    task_map: dict[str, TaskResponse],
    include_evidence: bool,
    include_test_runs: bool,
    include_output: bool,
    include_logs: bool,
    include_artifacts: bool,
) -> ProofBundleSearchItemResponse:
    task_response = task_map[item.task.id]
    evidence_items: list[TaskEvidenceResponse] = []
    if include_evidence:
        for evidence_item in item.evidence:
            entry = _task_evidence_item_to_response(evidence_item)
            if not include_test_runs:
                entry.test_run = None
            evidence_items.append(entry)

    test_runs: list[TestRunResponse] = []
    if include_output or include_logs or include_artifacts:
        test_runs = [_test_run_record_to_response(record) for record in item.test_runs]

    return ProofBundleSearchItemResponse(
        task=task_response,
        summary=ProofBundleSummaryResponse(**item.summary.to_dict()),
        last_evidence_at=item.last_evidence_at,
        evidence=evidence_items,
        test_runs=test_runs,
    )


async def _build_task_responses(
    task_service: TaskService, tasks: list[Task]
) -> list[TaskResponse]:
    task_ids = [task.id for task in tasks]
    activity_map = await task_service.get_last_activity_map(task_ids)
    workflow_map = await task_service.get_last_transition_map(task_ids, kind="workflow")
    status_map = await task_service.get_last_transition_map(task_ids, kind="status")
    actor_service = ActorService(
        task_service.db,
        task_service.events,
        task_service.revisions,
        task_service.metrics,
    )
    actor_refs: list[str] = []
    for task in tasks:
        if task.assignee_id:
            actor_refs.append(task.assignee_id)
        if task.assignee:
            actor_refs.append(task.assignee)
    assignee_map = await resolve_actor_reference_map(actor_service, actor_refs)
    checkout_actor_map: dict[str, Any] = {}
    for task in tasks:
        if task.checkout_actor_id and task.checkout_actor_id not in checkout_actor_map:
            checkout_actor_map[task.checkout_actor_id] = await actor_service.get_actor(
                task.checkout_actor_id
            )

    responses: list[TaskResponse] = []
    for task in tasks:
        last_transition = (
            workflow_map.get(task.id) if task.workflow_id else status_map.get(task.id)
        )
        responses.append(
            _task_to_response(
                task,
                last_activity_at=activity_map.get(task.id),
                last_transition_at=last_transition,
                assignee_map=assignee_map,
                checkout_actor_map=checkout_actor_map,
            )
        )
    return responses


def _task_dependency_detail(
    task_id: str,
    *,
    task_map: dict[str, Task],
    project_names: dict[str, str | None],
    activity_map: dict[str, datetime | None],
    workflow_map: dict[str, datetime | None],
    status_map: dict[str, datetime | None],
) -> TaskDependencyDetailResponse:
    task_obj = task_map.get(task_id)
    if task_obj is None:
        return TaskDependencyDetailResponse(
            id=task_id,
            title=None,
            status=None,
            priority=None,
            project_id=None,
            project_name=None,
            updated_at=None,
            last_activity_at=None,
            last_transition_at=None,
        )

    last_transition = (
        workflow_map.get(task_obj.id)
        if task_obj.workflow_id
        else status_map.get(task_obj.id)
    )

    return TaskDependencyDetailResponse(
        id=task_obj.id,
        title=task_obj.title,
        status=task_obj.status.value,
        priority=task_obj.priority.value,
        project_id=task_obj.project_id,
        project_name=project_names.get(task_obj.project_id),
        updated_at=task_obj.updated_at,
        last_activity_at=activity_map.get(task_obj.id),
        last_transition_at=last_transition,
    )


def _task_service_with_user(
    task_service: TaskService,
    api_key: ApiKey,
    updated_by: str | None,
) -> TaskService:
    user_id = updated_by or api_key.name or "api"
    return task_service.with_context(user_id=user_id)


@router.post("/tasks", response_model=TaskResponse, status_code=201)
async def create_task(
    data: TaskCreate,
    task_service: TaskService = Depends(get_task_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.TASKS_WRITE)),
) -> TaskResponse:
    """Create a new task."""
    try:
        task = await task_service.create_task(
            project_id=data.project_id,
            title=data.title,
            description=data.description,
            parent_id=data.parent_id,
            priority=Priority(data.priority),
            complexity_points=data.complexity_points,
            tags=data.tags,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    responses = await _build_task_responses(task_service, [task])
    return responses[0]


@router.get("/tasks")
async def list_tasks(
    project_id: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    task_service: TaskService = Depends(get_task_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.TASKS_READ)),
) -> PaginatedResponse[TaskResponse]:
    """List tasks with optional filters."""
    status_filter = TaskStatus(status) if status else None
    result = await task_service.list_tasks(
        project_id=project_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    items = await _build_task_responses(task_service, result.items)
    params: QueryParamMap = {
        "project_id": project_id,
        "status": status,
        "limit": result.limit,
        "offset": result.offset,
    }
    self_path = _build_query_path("/api/v1/tasks", params)
    next_path = (
        _build_query_path(
            "/api/v1/tasks",
            {
                **params,
                "offset": result.offset + result.limit,
            },
        )
        if result.offset + result.limit < result.total_count
        else None
    )
    first_task = items[0] if items else None
    next_steps = _normalize_next_steps(
        f"GET /api/v1/tasks/{first_task.id}" if first_task else "",
        f"POST /api/v1/tasks/{first_task.id}/start" if first_task else "",
        "GET /api/v1/tasks/ready",
        "GET /api/v1/tasks/search?query=<text>",
    )

    return {
        "items": items,
        "total_count": result.total_count,
        "offset": result.offset,
        "limit": result.limit,
        "links": _task_query_links(self_path=self_path, next_path=next_path),
        "next_steps": next_steps,
        "params": params,
    }


def _build_task_tree_nodes(
    trees: list[TaskTree],
    *,
    activity_map: dict[str, datetime | None],
    workflow_map: dict[str, datetime | None],
    status_map: dict[str, datetime | None],
) -> list[TaskTreeNode]:
    nodes: list[TaskTreeNode] = []
    for tree in trees:
        task_obj = tree.task
        last_transition = (
            workflow_map.get(task_obj.id)
            if task_obj.workflow_id
            else status_map.get(task_obj.id)
        )
        nodes.append(
            TaskTreeNode(
                task=_task_to_response(
                    task_obj,
                    last_activity_at=activity_map.get(task_obj.id),
                    last_transition_at=last_transition,
                ),
                depth=tree.depth,
                children=_build_task_tree_nodes(
                    tree.children,
                    activity_map=activity_map,
                    workflow_map=workflow_map,
                    status_map=status_map,
                ),
            )
        )
    return nodes


@router.get("/tasks/tree", response_model=TaskTreeResponse)
async def get_task_tree(
    project_id: str,
    root_task_id: str | None = None,
    task_service: TaskService = Depends(get_task_service),
    project_service: ProjectService = Depends(get_project_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.TASKS_READ)),
) -> TaskTreeResponse:
    """Get hierarchical task tree for a project."""
    project = await project_service.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    trees = await task_service.get_task_tree(
        project_id=project_id,
        root_task_id=root_task_id,
    )
    if root_task_id and not trees:
        raise HTTPException(status_code=404, detail="Root task not found")

    task_ids: list[str] = []

    def _collect(tree: TaskTree) -> None:
        task_ids.append(tree.task.id)
        for child in tree.children:
            _collect(child)

    for tree in trees:
        _collect(tree)

    activity_map: dict[str, datetime | None] = {}
    workflow_map: dict[str, datetime | None] = {}
    status_map: dict[str, datetime | None] = {}
    if task_ids:
        activity_map = await task_service.get_last_activity_map(task_ids)
        workflow_map = await task_service.get_last_transition_map(
            task_ids, kind="workflow"
        )
        status_map = await task_service.get_last_transition_map(task_ids, kind="status")

    return TaskTreeResponse(
        project_id=project_id,
        root_task_id=root_task_id,
        nodes=_build_task_tree_nodes(
            trees,
            activity_map=activity_map,
            workflow_map=workflow_map,
            status_map=status_map,
        ),
    )


@router.get("/tasks/search")
async def search_tasks(
    query: str | None = None,
    project_id: str | None = None,
    status: list[str] | None = Query(None),
    priority: list[str] | None = Query(None),
    assignee: str | None = None,
    tags: list[str] | None = Query(None),
    label_id: list[str] | None = Query(None),
    label_category_id: list[str] | None = Query(None),
    created_from: str | None = None,
    created_to: str | None = None,
    updated_from: str | None = None,
    updated_to: str | None = None,
    due_from: str | None = None,
    due_to: str | None = None,
    include_terminal: bool = False,
    sort_by: str | None = None,
    sort_dir: str | None = None,
    limit: int = 100,
    offset: int = 0,
    task_service: TaskService = Depends(get_task_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.TASKS_READ)),
) -> PaginatedResponse[TaskResponse]:
    """Search tasks with rich filters."""
    statuses = _parse_statuses(status)
    priorities = _parse_priorities(priority)

    result = await task_service.search_tasks(
        query=query,
        project_id=project_id,
        statuses=statuses,
        priorities=priorities,
        assignee=assignee,
        created_from=_parse_datetime(created_from, "created_from"),
        created_to=_parse_datetime(created_to, "created_to"),
        updated_from=_parse_datetime(updated_from, "updated_from"),
        updated_to=_parse_datetime(updated_to, "updated_to"),
        due_from=_parse_datetime(due_from, "due_from"),
        due_to=_parse_datetime(due_to, "due_to"),
        tags=tags or None,
        label_ids=label_id or None,
        label_category_ids=label_category_id or None,
        include_terminal=include_terminal,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )

    items = await _build_task_responses(task_service, result.items)
    params: QueryParamMap = {
        "query": query,
        "project_id": project_id,
        "status": status,
        "priority": priority,
        "assignee": assignee,
        "tags": tags,
        "label_id": label_id,
        "label_category_id": label_category_id,
        "created_from": created_from,
        "created_to": created_to,
        "updated_from": updated_from,
        "updated_to": updated_to,
        "due_from": due_from,
        "due_to": due_to,
        "include_terminal": include_terminal,
        "sort_by": sort_by,
        "sort_dir": sort_dir,
        "limit": result.limit,
        "offset": result.offset,
    }
    self_path = _build_query_path("/api/v1/tasks/search", params)
    next_path = (
        _build_query_path(
            "/api/v1/tasks/search",
            {
                **params,
                "offset": result.offset + result.limit,
            },
        )
        if result.offset + result.limit < result.total_count
        else None
    )
    first_task = items[0] if items else None
    next_steps = _normalize_next_steps(
        f"GET /api/v1/tasks/{first_task.id}" if first_task else "",
        f"PATCH /api/v1/tasks/{first_task.id}" if first_task else "",
        "GET /api/v1/tasks/ready",
        "GET /api/v1/tasks/stale",
    )

    return {
        "items": items,
        "total_count": result.total_count,
        "offset": result.offset,
        "limit": result.limit,
        "links": _task_query_links(self_path=self_path, next_path=next_path),
        "next_steps": next_steps,
        "params": params,
    }


@router.get("/tasks/ready")
async def list_ready_tasks(
    project_id: str | None = None,
    status: list[str] | None = Query(None),
    exclude_checked_out: bool = True,
    limit: int = 100,
    offset: int = 0,
    task_service: TaskService = Depends(get_task_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.TASKS_READ)),
) -> PaginatedResponse[TaskResponse]:
    """List tasks ready to start (no blocking dependencies)."""
    statuses = _parse_statuses(status)
    result = await task_service.list_ready_tasks(
        project_id=project_id,
        statuses=statuses,
        exclude_checked_out=exclude_checked_out,
        limit=limit,
        offset=offset,
    )

    items = await _build_task_responses(task_service, result.items)
    params: QueryParamMap = {
        "project_id": project_id,
        "status": status,
        "exclude_checked_out": exclude_checked_out,
        "limit": result.limit,
        "offset": result.offset,
    }
    self_path = _build_query_path("/api/v1/tasks/ready", params)
    next_path = (
        _build_query_path(
            "/api/v1/tasks/ready",
            {
                **params,
                "offset": result.offset + result.limit,
            },
        )
        if result.offset + result.limit < result.total_count
        else None
    )
    first_task = items[0] if items else None
    next_steps = _normalize_next_steps(
        f"GET /api/v1/tasks/{first_task.id}" if first_task else "",
        f"POST /api/v1/tasks/{first_task.id}/start" if first_task else "",
        "GET /api/v1/tasks/search?query=<text>",
        "GET /api/v1/tasks/stale",
    )

    return {
        "items": items,
        "total_count": result.total_count,
        "offset": result.offset,
        "limit": result.limit,
        "links": _task_query_links(self_path=self_path, next_path=next_path),
        "next_steps": next_steps,
        "params": params,
    }


@router.get("/tasks/stale")
async def list_stale_tasks(
    project_id: str | None = None,
    status: list[str] | None = Query(None),
    stale_after_days: int = 14,
    updated_before: str | None = None,
    include_terminal: bool = False,
    limit: int = 100,
    offset: int = 0,
    task_service: TaskService = Depends(get_task_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.TASKS_READ)),
) -> PaginatedResponse[TaskResponse]:
    """List tasks with no recent updates."""
    statuses = _parse_statuses(status)
    result = await task_service.list_stale_tasks(
        project_id=project_id,
        statuses=statuses,
        stale_after_days=stale_after_days,
        updated_before=_parse_datetime(updated_before, "updated_before"),
        include_terminal=include_terminal,
        limit=limit,
        offset=offset,
    )

    items = await _build_task_responses(task_service, result.items)
    params: QueryParamMap = {
        "project_id": project_id,
        "status": status,
        "stale_after_days": stale_after_days,
        "updated_before": updated_before,
        "include_terminal": include_terminal,
        "limit": result.limit,
        "offset": result.offset,
    }
    self_path = _build_query_path("/api/v1/tasks/stale", params)
    next_path = (
        _build_query_path(
            "/api/v1/tasks/stale",
            {
                **params,
                "offset": result.offset + result.limit,
            },
        )
        if result.offset + result.limit < result.total_count
        else None
    )
    first_task = items[0] if items else None
    next_steps = _normalize_next_steps(
        f"GET /api/v1/tasks/{first_task.id}" if first_task else "",
        f"PATCH /api/v1/tasks/{first_task.id}" if first_task else "",
        "GET /api/v1/tasks/ready",
        "GET /api/v1/tasks/search?query=<text>",
    )

    return {
        "items": items,
        "total_count": result.total_count,
        "offset": result.offset,
        "limit": result.limit,
        "links": _task_query_links(self_path=self_path, next_path=next_path),
        "next_steps": next_steps,
        "params": params,
    }


@router.get("/tasks/duplicates")
async def list_duplicate_tasks(
    project_id: str | None = None,
    status: list[str] | None = Query(None),
    include_terminal: bool = False,
    min_count: int = 2,
    limit: int = 100,
    offset: int = 0,
    task_service: TaskService = Depends(get_task_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.TASKS_READ)),
) -> DuplicateTaskListResponsePayload:
    """List groups of duplicate tasks by normalized title."""
    statuses = _parse_statuses(status)
    result = await task_service.find_duplicate_tasks(
        project_id=project_id,
        statuses=statuses,
        include_terminal=include_terminal,
        min_count=min_count,
        limit=limit,
        offset=offset,
    )

    all_tasks = [task for group in result.items for task in group.tasks]
    task_responses = await _build_task_responses(task_service, all_tasks)
    task_response_map = {task.id: task for task in task_responses}

    def group_last_activity(group: DuplicateTaskGroup) -> datetime | None:
        if not group.tasks:
            return None
        timestamps: list[datetime] = []
        for task_obj in group.tasks:
            response = task_response_map.get(task_obj.id)
            last_activity = response.last_activity_at if response else None
            timestamps.append(last_activity or task_obj.updated_at)
        return max(timestamps) if timestamps else None

    params: QueryParamMap = {
        "project_id": project_id,
        "status": status,
        "include_terminal": include_terminal,
        "min_count": min_count,
        "limit": result.limit,
        "offset": result.offset,
    }
    self_path = _build_query_path("/api/v1/tasks/duplicates", params)
    next_path = (
        _build_query_path(
            "/api/v1/tasks/duplicates",
            {
                **params,
                "offset": result.offset + result.limit,
            },
        )
        if result.offset + result.limit < result.total_count
        else None
    )
    first_group = result.items[0] if result.items else None
    first_primary_id = (
        first_group.suggested_primary_id
        if first_group and first_group.suggested_primary_id
        else first_group.tasks[0].id
        if first_group and first_group.tasks
        else None
    )
    first_duplicate_ids = (
        [task.id for task in first_group.tasks if task.id != first_primary_id][:2]
        if first_group and first_group.tasks and first_primary_id
        else []
    )
    preview_hint = (
        "POST /api/v1/tasks/duplicates/preview "
        f"(primary_task_id={first_primary_id}, duplicate_task_ids={first_duplicate_ids})"
        if first_primary_id and first_duplicate_ids
        else ""
    )
    merge_hint = (
        "POST /api/v1/tasks/duplicates/merge "
        f"(primary_task_id={first_primary_id}, duplicate_task_ids={first_duplicate_ids})"
        if first_primary_id and first_duplicate_ids
        else ""
    )
    next_steps = _normalize_next_steps(
        preview_hint,
        merge_hint,
        f"GET /api/v1/tasks/{first_primary_id}" if first_primary_id else "",
        "GET /api/v1/tasks/search?query=<text>",
    )

    items_payload: list[DuplicateTaskGroupPayload] = []
    for group in result.items:
        group_primary_id = (
            group.suggested_primary_id or group.tasks[0].id if group.tasks else None
        )
        group_duplicate_ids = (
            [task.id for task in group.tasks if task.id != group_primary_id][:2]
            if group_primary_id
            else []
        )
        group_preview_hint = (
            "POST /api/v1/tasks/duplicates/preview "
            f"(primary_task_id={group_primary_id}, duplicate_task_ids={group_duplicate_ids})"
            if group_primary_id and group_duplicate_ids
            else ""
        )
        group_merge_hint = (
            "POST /api/v1/tasks/duplicates/merge "
            f"(primary_task_id={group_primary_id}, duplicate_task_ids={group_duplicate_ids})"
            if group_primary_id and group_duplicate_ids
            else ""
        )
        items_payload.append(
            {
                "normalized_title": group.normalized_title,
                "count": group.count,
                "suggested_primary_id": group.suggested_primary_id,
                "suggested_primary_reason": group.suggested_primary_reason,
                "last_activity_at": group_last_activity(group),
                "tasks": [
                    task_response_map.get(task.id) or _task_to_response(task)
                    for task in group.tasks
                ],
                "links": {
                    "self": self_path,
                    "primary_task": (
                        f"/api/v1/tasks/{group_primary_id}"
                        if group_primary_id
                        else None
                    ),
                    "preview": "/api/v1/tasks/duplicates/preview",
                    "merge": "/api/v1/tasks/duplicates/merge",
                    "search": "/api/v1/tasks/search",
                    "guide": "/api/v1/",
                },
                "next_steps": _normalize_next_steps(
                    group_preview_hint,
                    group_merge_hint,
                    f"GET /api/v1/tasks/{group_primary_id}" if group_primary_id else "",
                    "GET /api/v1/tasks/search?query=<text>",
                ),
            }
        )

    return {
        "items": items_payload,
        "total_count": result.total_count,
        "offset": result.offset,
        "limit": result.limit,
        "links": {
            **_task_query_links(self_path=self_path, next_path=next_path),
            "preview": "/api/v1/tasks/duplicates/preview",
            "merge": "/api/v1/tasks/duplicates/merge",
        },
        "next_steps": next_steps,
        "params": params,
    }


@router.post("/tasks/duplicates/preview", response_model=DuplicateMergePreviewResponse)
async def preview_duplicate_merge(
    data: TaskDuplicateMergePreview,
    task_service: TaskService = Depends(get_task_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.TASKS_READ)),
) -> DuplicateMergePreviewResponse:
    """Preview duplicate task merges and highlight conflicts."""
    if not data.duplicate_task_ids:
        raise HTTPException(status_code=400, detail="No duplicate_task_ids provided")

    preview = await task_service.preview_merge_duplicate_tasks(
        primary_task_id=data.primary_task_id,
        duplicate_task_ids=data.duplicate_task_ids,
    )
    if preview is None:
        raise HTTPException(status_code=404, detail="Primary task not found")

    merge_hint = (
        "POST /api/v1/tasks/duplicates/merge "
        "(primary_task_id=<task_id>, duplicate_task_ids=[...])"
    )
    preview_links: JsonObject = {
        "self": "/api/v1/tasks/duplicates/preview",
        "merge": "/api/v1/tasks/duplicates/merge",
        "duplicates": "/api/v1/tasks/duplicates",
        "primary_task": f"/api/v1/tasks/{data.primary_task_id}",
        "guide": "/api/v1/",
    }

    return DuplicateMergePreviewResponse(
        primary_task=_task_to_response(preview.primary_task),
        duplicates=[
            DuplicateMergePreviewItemResponse(
                task=_task_to_response(item.task),
                already_linked=item.already_linked,
                conflicts=[
                    DuplicateMergeConflictResponse(
                        field=conflict.field,
                        primary_value=conflict.primary_value,
                        duplicate_value=conflict.duplicate_value,
                        duplicate_task_id=conflict.duplicate_task_id,
                    )
                    for conflict in item.conflicts
                ],
            )
            for item in preview.duplicates
        ],
        missing_ids=preview.missing_ids,
        warnings=preview.warnings,
        can_merge=preview.can_merge,
        suggested_primary_id=preview.suggested_primary_id,
        suggested_primary_reason=preview.suggested_primary_reason,
        links=preview_links,
        next_steps=_normalize_next_steps(
            merge_hint,
            f"GET /api/v1/tasks/{data.primary_task_id}",
            "GET /api/v1/tasks/duplicates",
        ),
    )


@router.post("/tasks/duplicates/merge")
async def merge_duplicate_tasks(
    data: TaskDuplicateMerge,
    task_service: TaskService = Depends(get_task_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.TASKS_WRITE)),
) -> MergeDuplicateTasksResponsePayload:
    """Merge duplicate tasks by linking them to a primary task."""
    if not data.duplicate_task_ids:
        raise HTTPException(status_code=400, detail="No duplicate_task_ids provided")

    result = await task_service.merge_duplicate_tasks(
        primary_task_id=data.primary_task_id,
        duplicate_task_ids=data.duplicate_task_ids,
        cancel_duplicates=data.cancel_duplicates,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Primary task not found")

    return {
        "primary_task": _task_to_response(result.primary_task),
        "duplicate_tasks": [_task_to_response(task) for task in result.duplicate_tasks],
        "links_added": result.links_added,
        "duplicates_cancelled": result.duplicates_cancelled,
        "links": {
            "self": "/api/v1/tasks/duplicates/merge",
            "preview": "/api/v1/tasks/duplicates/preview",
            "duplicates": "/api/v1/tasks/duplicates",
            "primary_task": f"/api/v1/tasks/{result.primary_task.id}",
            "guide": "/api/v1/",
        },
        "next_steps": _normalize_next_steps(
            f"GET /api/v1/tasks/{result.primary_task.id}",
            "GET /api/v1/tasks/duplicates",
            "GET /api/v1/tasks/search?query=<text>",
        ),
    }


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str,
    task_service: TaskService = Depends(get_task_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.TASKS_READ)),
) -> TaskResponse:
    """Get a task by ID."""
    task = await task_service.get_task(task_id)

    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    responses = await _build_task_responses(task_service, [task])
    response = responses[0]
    plan_repo = PlanRepository(
        task_service.db,
        task_service.events,
        task_service.revisions,
        task_service.metrics,
    )
    linked_plans = await plan_repo.list_by_task_id(task_id)
    response.linked_plan_count = len(linked_plans)
    response.linked_plans = [
        {
            "id": plan.id,
            "name": plan.name,
            "status": plan.status.value,
            "project_id": plan.project_id,
            "goal_id": plan.goal_id,
            "objective_id": plan.objective_id,
            "updated_at": plan.updated_at,
            "links": build_plan_detail_links(plan.id),
        }
        for plan in linked_plans
    ]
    response.links = {
        **build_task_detail_links(task_id),
        **response.links,
    }
    response.next_steps = _normalize_next_steps(*build_task_detail_next_steps(task_id))
    return response


@router.post("/tasks/{task_id}/start")
async def start_task(
    task_id: str,
    data: TaskActionRequest | None = None,
    task_service: TaskService = Depends(get_task_service),
    api_key: ApiKey = Depends(require_scope(Scopes.TASKS_WRITE)),
) -> dict[str, str]:
    """Start a task (set to IN_PROGRESS)."""
    check_resource_scope(api_key, "tasks", task_id, "write")
    payload = data or TaskActionRequest()
    task_service = _task_service_with_user(
        task_service,
        api_key,
        payload.updated_by,
    )
    task = await _run_task_action(lambda: task_service.start_task(task_id))

    return {"status": "started", "task_id": task.id}


@router.post("/tasks/{task_id}/complete", response_model=TaskCompletionActionResponse)
async def complete_task(
    task_id: str,
    notes: str | None = None,
    data: TaskActionRequest | None = None,
    task_service: TaskService = Depends(get_task_service),
    api_key: ApiKey = Depends(require_scope(Scopes.TASKS_WRITE)),
) -> TaskCompletionActionResponse:
    """Complete a task."""
    check_resource_scope(api_key, "tasks", task_id, "write")
    payload = data or TaskActionRequest()
    task_service = _task_service_with_user(
        task_service,
        api_key,
        payload.updated_by,
    )
    current_task = await task_service.get_task(task_id)
    if current_task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if current_task.status.is_terminal:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot complete task in {current_task.status.value} status",
        )
    try:
        result = await task_service.complete_task_with_effects(
            task_id,
            notes=notes,
            actual_hours=payload.actual_hours,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if result is None or result.task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    newly_unblocked = await _build_task_responses(
        task_service,
        list(result.newly_unblocked_tasks),
    )
    return TaskCompletionActionResponse(
        status="completed",
        task_id=result.task.id,
        newly_unblocked=newly_unblocked,
    )


@router.post("/tasks/{task_id}/block")
async def block_task(
    task_id: str,
    data: TaskActionRequest | None = None,
    task_service: TaskService = Depends(get_task_service),
    api_key: ApiKey = Depends(require_scope(Scopes.TASKS_WRITE)),
) -> dict[str, str]:
    """Block a task."""
    check_resource_scope(api_key, "tasks", task_id, "write")
    payload = data or TaskActionRequest()
    task_service = _task_service_with_user(
        task_service,
        api_key,
        payload.updated_by,
    )

    task = await _run_task_action(
        lambda: task_service.block_task(task_id, reason=payload.reason)
    )

    return {"status": "blocked", "task_id": task.id}


@router.post("/tasks/{task_id}/unblock")
async def unblock_task(
    task_id: str,
    data: TaskActionRequest | None = None,
    task_service: TaskService = Depends(get_task_service),
    api_key: ApiKey = Depends(require_scope(Scopes.TASKS_WRITE)),
) -> dict[str, str]:
    """Unblock a task."""
    check_resource_scope(api_key, "tasks", task_id, "write")
    payload = data or TaskActionRequest()
    task_service = _task_service_with_user(
        task_service,
        api_key,
        payload.updated_by,
    )

    task = await _run_task_action(lambda: task_service.unblock_task(task_id))

    return {"status": "unblocked", "task_id": task.id}


@router.post("/tasks/{task_id}/review")
async def review_task(
    task_id: str,
    data: TaskActionRequest | None = None,
    task_service: TaskService = Depends(get_task_service),
    api_key: ApiKey = Depends(require_scope(Scopes.TASKS_WRITE)),
) -> dict[str, str]:
    """Submit a task for review."""
    check_resource_scope(api_key, "tasks", task_id, "write")
    payload = data or TaskActionRequest()
    task_service = _task_service_with_user(
        task_service,
        api_key,
        payload.updated_by,
    )

    task = await _run_task_action(lambda: task_service.submit_for_review(task_id))

    return {"status": "in_review", "task_id": task.id}


@router.post("/tasks/{task_id}/reopen")
async def reopen_task(
    task_id: str,
    data: TaskActionRequest | None = None,
    task_service: TaskService = Depends(get_task_service),
    api_key: ApiKey = Depends(require_scope(Scopes.TASKS_WRITE)),
) -> dict[str, str]:
    """Reopen a task."""
    check_resource_scope(api_key, "tasks", task_id, "write")
    payload = data or TaskActionRequest()
    task_service = _task_service_with_user(
        task_service,
        api_key,
        payload.updated_by,
    )

    task = await _run_task_action(lambda: task_service.reopen_task(task_id))

    return {"status": "reopened", "task_id": task.id}


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(
    task_id: str,
    data: TaskActionRequest | None = None,
    task_service: TaskService = Depends(get_task_service),
    api_key: ApiKey = Depends(require_scope(Scopes.TASKS_WRITE)),
) -> dict[str, str]:
    """Cancel a task."""
    check_resource_scope(api_key, "tasks", task_id, "write")
    payload = data or TaskActionRequest()
    task_service = _task_service_with_user(
        task_service,
        api_key,
        payload.updated_by,
    )

    task = await _run_task_action(
        lambda: task_service.cancel_task(task_id, reason=payload.reason)
    )

    return {"status": "cancelled", "task_id": task.id}


@router.post(
    "/tasks/{task_id}/dependencies",
    response_model=TaskDependencyResponse,
    status_code=201,
)
async def add_task_dependency(
    task_id: str,
    data: TaskDependencyCreate,
    task_service: TaskService = Depends(get_task_service),
    api_key: ApiKey = Depends(require_scope(Scopes.TASKS_WRITE)),
) -> TaskDependencyResponse:
    """Add a task dependency."""
    check_resource_scope(api_key, "tasks", task_id, "write")
    check_resource_scope(api_key, "tasks", data.depends_on_id, "write")

    try:
        dependency_type = DependencyType(data.dependency_type)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid dependency_type. Use: blocks, relates_to, duplicates",
        ) from exc

    dependency = await task_service.add_dependency(
        task_id=task_id,
        depends_on_id=data.depends_on_id,
        dependency_type=dependency_type,
    )
    if dependency is None:
        raise HTTPException(status_code=404, detail="Task not found")

    return TaskDependencyResponse(
        id=dependency.id,
        task_id=dependency.task_id,
        depends_on_id=dependency.depends_on_id,
        dependency_type=dependency.dependency_type.value,
        created_at=dependency.created_at,
        updated_at=dependency.updated_at,
    )


@router.delete("/tasks/{task_id}/dependencies/{depends_on_id}")
async def remove_task_dependency(
    task_id: str,
    depends_on_id: str,
    task_service: TaskService = Depends(get_task_service),
    api_key: ApiKey = Depends(require_scope(Scopes.TASKS_WRITE)),
) -> dict[str, str]:
    """Remove a task dependency."""
    check_resource_scope(api_key, "tasks", task_id, "write")
    check_resource_scope(api_key, "tasks", depends_on_id, "write")

    removed = await task_service.remove_dependency(task_id, depends_on_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Dependency not found")

    return {"status": "removed", "task_id": task_id, "depends_on_id": depends_on_id}


@router.get("/tasks/{task_id}/graph", response_model=TaskDependencyGraphResponse)
async def get_task_dependency_graph(
    task_id: str,
    task_service: TaskService = Depends(get_task_service),
    project_service: ProjectService = Depends(get_project_service),
    api_key: ApiKey = Depends(require_scope(Scopes.TASKS_READ)),
) -> TaskDependencyGraphResponse:
    """Get dependency graph for a task."""
    check_resource_scope(api_key, "tasks", task_id, "read")

    task = await task_service.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    graph = await task_service.get_dependency_graph(task_id)
    project_names: dict[str, str | None] = {}
    if task.project_id:
        project = await project_service.get_project(task.project_id)
        project_names[task.project_id] = project.name if project else None

    dep_ids = list(dict.fromkeys(graph.blocked_by + graph.blocking))
    tasks = await task_service.get_tasks_by_ids(dep_ids) if dep_ids else []
    task_map = {task_item.id: task_item for task_item in tasks}

    for task_obj in tasks:
        if task_obj.project_id and task_obj.project_id not in project_names:
            project = await project_service.get_project(task_obj.project_id)
            project_names[task_obj.project_id] = project.name if project else None

    activity_map = await task_service.get_last_activity_map(dep_ids)
    workflow_map = await task_service.get_last_transition_map(dep_ids, kind="workflow")
    status_map = await task_service.get_last_transition_map(dep_ids, kind="status")

    last_activity = await task_service.get_last_activity(task_id)
    last_transition = await task_service.get_last_transition(
        task_id, kind="workflow"
    ) or await task_service.get_last_transition(task_id, kind="status")

    return TaskDependencyGraphResponse(
        task_id=graph.task_id,
        task_title=task.title,
        project_id=task.project_id,
        project_name=project_names.get(task.project_id),
        status=task.status.value,
        priority=task.priority.value,
        updated_at=task.updated_at,
        last_activity_at=last_activity,
        last_transition_at=last_transition,
        blocked_by=graph.blocked_by,
        blocking=graph.blocking,
        blocked_by_details=[
            _task_dependency_detail(
                dep_id,
                task_map=task_map,
                project_names=project_names,
                activity_map=activity_map,
                workflow_map=workflow_map,
                status_map=status_map,
            )
            for dep_id in graph.blocked_by
        ],
        blocking_details=[
            _task_dependency_detail(
                dep_id,
                task_map=task_map,
                project_names=project_names,
                activity_map=activity_map,
                workflow_map=workflow_map,
                status_map=status_map,
            )
            for dep_id in graph.blocking
        ],
    )


@router.post(
    "/tasks/{task_id}/evidence",
    response_model=TaskEvidenceResponse,
    status_code=201,
)
async def add_task_evidence(
    task_id: str,
    data: TaskEvidenceCreate,
    task_service: TaskService = Depends(get_task_service),
    evidence_service: TaskEvidenceService = Depends(get_task_evidence_service),
    api_key: ApiKey = Depends(get_api_key),
) -> TaskEvidenceResponse:
    """Add evidence to a task."""
    check_resource_scope(api_key, "tasks", task_id, "write")
    task = await task_service.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    evidence = await evidence_service.add_evidence(
        task_id=task_id,
        evidence_type=data.evidence_type,
        reference=data.reference,
        description=data.description,
        metadata=data.metadata,
        created_by=data.created_by or api_key.name or "api",
    )

    return TaskEvidenceResponse(
        id=evidence.id,
        task_id=evidence.task_id,
        evidence_type=evidence.evidence_type,
        reference=evidence.reference,
        description=evidence.description,
        metadata=evidence.metadata,
        created_by=evidence.created_by,
        created_at=evidence.created_at,
        test_run=None,
    )


@router.get("/tasks/{task_id}/evidence")
async def list_task_evidence(
    task_id: str,
    include_test_runs: bool = False,
    include_output: bool = False,
    limit: int = 100,
    offset: int = 0,
    task_service: TaskService = Depends(get_task_service),
    evidence_service: TaskEvidenceService = Depends(get_task_evidence_service),
    api_key: ApiKey = Depends(get_api_key),
) -> PaginatedResponse[TaskEvidenceResponse]:
    """List evidence records for a task."""
    check_resource_scope(api_key, "tasks", task_id, "read")
    task = await task_service.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    result = await evidence_service.list_evidence(
        task_id=task_id,
        limit=limit,
        offset=offset,
        include_test_runs=include_test_runs,
        include_output=include_output,
    )
    params: QueryParamMap = {
        "include_test_runs": include_test_runs,
        "include_output": include_output,
        "limit": limit,
        "offset": offset,
    }
    evidence_path = f"/api/v1/tasks/{task_id}/evidence"
    self_path = _build_query_path(evidence_path, params)
    next_path = None
    if result.limit > 0 and result.offset + result.limit < result.total_count:
        next_path = _build_query_path(
            evidence_path,
            {
                **params,
                "offset": result.offset + result.limit,
            },
        )
    links: JsonObject = {
        "self": self_path,
        "next": next_path,
        "task": f"/api/v1/tasks/{task_id}",
        "proof_bundle": f"/api/v1/tasks/{task_id}/proof-bundle",
        "guide": "/api/v1/",
    }
    next_steps = _normalize_next_steps(
        f"GET /api/v1/tasks/{task_id}",
        f"GET /api/v1/tasks/{task_id}/proof-bundle",
        "GET /api/v1/evidence/bundles?task_id=<task_id>",
    )

    return {
        "items": [_task_evidence_item_to_response(item) for item in result.items],
        "total_count": result.total_count,
        "offset": result.offset,
        "limit": result.limit,
        "links": links,
        "next_steps": next_steps,
        "params": {"task_id": task_id, **params},
    }


@router.get("/tasks/{task_id}/proof-bundle", response_model=ProofBundleResponse)
async def get_task_proof_bundle(
    task_id: str,
    include_output: bool = False,
    include_logs: bool = False,
    include_artifacts: bool = False,
    task_service: TaskService = Depends(get_task_service),
    proof_bundle_service: ProofBundleService = Depends(get_proof_bundle_service),
    api_key: ApiKey = Depends(get_api_key),
) -> ProofBundleResponse:
    """Get a proof bundle for a task."""
    check_resource_scope(api_key, "tasks", task_id, "read")
    task = await task_service.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    bundle = await proof_bundle_service.build_task_bundle(
        task_id=task_id,
        include_output=include_output,
        include_logs=include_logs,
        include_artifacts=include_artifacts,
    )
    if bundle is None:
        raise HTTPException(status_code=404, detail="Task not found")

    summary = bundle.summary
    return ProofBundleResponse(
        task=_task_to_response(bundle.task),
        generated_at=bundle.generated_at,
        summary=ProofBundleSummaryResponse(
            evidence_total=summary.evidence_total,
            evidence_types=summary.evidence_types,
            test_runs=summary.test_runs,
            successful_test_runs=summary.successful_test_runs,
            log_bytes_total=summary.log_bytes_total,
            artifact_bytes_total=summary.artifact_bytes_total,
        ),
        evidence=[_task_evidence_item_to_response(item) for item in bundle.evidence],
        test_runs=[_test_run_record_to_response(run) for run in bundle.test_runs],
    )


@router.get("/evidence/bundles", response_model=ProofBundleSearchResponse)
async def search_evidence_bundles(
    task_id: list[str] | None = Query(None),
    plan_id: str | None = None,
    status: list[str] | None = Query(None),
    evidence_type: list[str] | None = Query(None),
    created_from: str | None = None,
    created_to: str | None = None,
    include_evidence: bool = False,
    include_test_runs: bool = False,
    include_output: bool = False,
    include_logs: bool = False,
    include_artifacts: bool = False,
    limit: int = 50,
    offset: int = 0,
    proof_bundle_service: ProofBundleService = Depends(get_proof_bundle_service),
    task_service: TaskService = Depends(get_task_service),
    plan_service: PlanService = Depends(get_plan_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.TASKS_READ)),
) -> ProofBundleSearchResponse:
    """Search proof bundles by task, plan, status, and date."""
    statuses = _parse_statuses(status)
    created_from_dt = _parse_datetime(created_from, "created_from")
    created_to_dt = _parse_datetime(created_to, "created_to")

    task_ids: list[str] | None = list(task_id) if task_id else None
    if plan_id:
        plan = await plan_service.get_plan(plan_id)
        if plan is None:
            raise HTTPException(status_code=404, detail="Plan not found")
        plan_tasks = list(plan.task_ids)
        if task_ids is None:
            task_ids = plan_tasks
        else:
            task_ids = [task for task in task_ids if task in plan_tasks]
        if task_ids == []:
            return ProofBundleSearchResponse(
                items=[],
                total_count=0,
                limit=limit,
                offset=offset,
            )

    if include_output:
        include_test_runs = True

    results = await proof_bundle_service.search_bundles(
        task_ids=task_ids,
        task_statuses=statuses,
        evidence_types=evidence_type,
        created_from=created_from_dt,
        created_to=created_to_dt,
        include_evidence=include_evidence,
        include_test_runs=include_test_runs,
        include_output=include_output,
        include_logs=include_logs,
        include_artifacts=include_artifacts,
        limit=limit,
        offset=offset,
    )

    tasks = [item.task for item in results.items]
    task_responses = await _build_task_responses(task_service, tasks)
    task_map = {task.id: task for task in task_responses}

    return ProofBundleSearchResponse(
        items=[
            _proof_bundle_search_item_to_response(
                item,
                task_map,
                include_evidence=include_evidence,
                include_test_runs=include_test_runs,
                include_output=include_output,
                include_logs=include_logs,
                include_artifacts=include_artifacts,
            )
            for item in results.items
        ],
        total_count=results.total_count,
        limit=results.limit,
        offset=results.offset,
    )


@router.patch("/tasks/{task_id}")
async def update_task(
    task_id: str,
    data: TaskUpdate,
    task_service: TaskService = Depends(get_task_service),
    api_key: ApiKey = Depends(get_api_key),
) -> TaskResponse:
    """Update task fields."""
    # Check row-level access
    check_resource_scope(api_key, "tasks", task_id, "write")

    # Get existing task
    task = await task_service.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    if data.clear_parent and data.parent_id:
        raise HTTPException(
            status_code=400,
            detail="Use parent_id or clear_parent, not both",
        )
    if data.clear_completion_criteria and data.completion_criteria:
        raise HTTPException(
            status_code=400,
            detail="Use completion_criteria or clear_completion_criteria, not both",
        )

    priority = Priority(data.priority) if data.priority else None

    try:
        updated = await task_service.update_task(
            task_id=task_id,
            title=data.title,
            description=data.description,
            parent_id=data.parent_id,
            clear_parent=data.clear_parent,
            priority=priority,
            complexity_points=data.complexity_points,
            completion_criteria=data.completion_criteria,
            clear_completion_criteria=data.clear_completion_criteria,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if updated is None:
        raise HTTPException(status_code=404, detail="Task not found")

    responses = await _build_task_responses(task_service, [updated])
    return responses[0]


def _task_to_response(
    task: Task,
    *,
    last_activity_at: datetime | None = None,
    last_transition_at: datetime | None = None,
    assignee_map: dict[str, Any] | None = None,
    checkout_actor_map: dict[str, Any] | None = None,
) -> TaskResponse:
    """Convert Task model to TaskResponse."""
    completion_criteria_raw = task.workflow_metadata.get("completion_criteria")
    completion_criteria = (
        [item for item in completion_criteria_raw if isinstance(item, str)]
        if isinstance(completion_criteria_raw, list)
        else []
    )
    assignee = actor_reference_payload(
        task.assignee,
        assignee_map or {},
        actor_id=task.assignee_id,
    )
    checkout_actor = None
    if checkout_actor_map and task.checkout_actor_id:
        checkout_actor = checkout_actor_map.get(task.checkout_actor_id)
    links = build_task_detail_links(task.id)
    assignee_links = assignee.get("links", {}) if assignee is not None else {}
    actor_link = assignee_links.get("actor")
    if isinstance(actor_link, str) and actor_link:
        links["actor"] = actor_link
    return TaskResponse(
        id=task.id,
        project_id=task.project_id,
        parent_id=task.parent_id,
        title=task.title,
        description=task.description,
        status=task.status.value,
        priority=task.priority.value,
        complexity_points=task.complexity_points,
        actual_hours=task.actual_hours,
        current_progress_percent=task.current_progress_percent,
        assignee=assignee,
        checkout=checkout_payload(
            agent_session_id=task.checkout_agent_session_id,
            actor_obj=checkout_actor,
            checked_out_at=task.checked_out_at,
            lease_until=task.checkout_lease_until,
            version=task.checkout_version,
            expired=task.checkout_expired,
        ),
        workflow_id=task.workflow_id,
        current_state=task.current_state,
        completion_criteria=completion_criteria,
        completion_ready=(
            task.status.value in {"in_review", "done"} and bool(completion_criteria)
        ),
        created_at=task.created_at,
        updated_at=task.updated_at,
        last_activity_at=last_activity_at,
        last_transition_at=last_transition_at,
        links=links,
        next_steps=_normalize_next_steps(*build_task_detail_next_steps(task.id)),
    )
