"""API routes for test run records."""

from __future__ import annotations

from typing import TypedDict

from fastapi import APIRouter, Depends, HTTPException

from pms.api.auth import Scopes, require_scope
from pms.api.dependencies import (
    get_test_run_retention_policy_service,
    get_test_run_retention_service,
    get_test_run_service,
)
from pms.api.models import (
    TestRunCreate,
    TestRunPruneResponse,
    TestRunResponse,
    TestRunRetentionPolicyResponse,
    TestRunRetentionResponse,
)
from pms.api.routes.discoverability import (
    QueryParamMap,
    build_query_path,
    next_page_path,
    normalize_next_steps,
    paginated_links,
)
from pms.api.types import PaginatedResponse
from pms.models.api_key import ApiKey
from pms.models.value_contracts import RetentionUsageSort
from pms.services.test_run_retention_policy_service import (
    TestRunRetentionPolicyService,
)
from pms.services.test_run_retention_service import (
    TestRunRetentionService,
)
from pms.services.test_run_service import TestRunRecord, TestRunService

router = APIRouter()


class RetentionPoliciesPagePayload(TypedDict):
    """Pagination payload for retention policies."""

    total_count: int
    limit: int
    offset: int
    has_more: bool
    next_offset: int | None


class RetentionPoliciesResponsePayload(TypedDict):
    """List retention policies payload."""

    items: list[TestRunRetentionPolicyResponse]
    page: RetentionPoliciesPagePayload


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


@router.post("/test-runs", response_model=TestRunResponse, status_code=201)
async def create_test_run(
    data: TestRunCreate,
    test_run_service: TestRunService = Depends(get_test_run_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.TEST_RUNS_WRITE)),
) -> TestRunResponse:
    """Create a test run record."""
    from pms.models.base import generate_id

    run_id = data.run_id or generate_id()
    config = dict(data.config or {})
    if data.command is not None:
        config["command"] = data.command
    if data.runner is not None:
        config["runner"] = data.runner
    if data.plan_id is not None:
        config["plan_id"] = data.plan_id
    if data.task_ids:
        config["task_ids"] = list(data.task_ids)

    try:
        record = await test_run_service.create_test_run(
            run_id=run_id,
            server_id=data.server_id,
            project_id=data.project_id,
            config=config,
            success=data.success,
            exit_code=data.exit_code,
            stdout=data.stdout,
            stderr=data.stderr,
            duration_seconds=data.duration_seconds,
            started_at=data.started_at,
            finished_at=data.finished_at,
            logs=data.logs,
            artifacts=data.artifacts,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _run_to_response(record)


@router.get("/test-runs")
async def list_test_runs(
    server_id: str | None = None,
    project_id: str | None = None,
    success: bool | None = None,
    include_output: bool = False,
    include_logs: bool = False,
    include_artifacts: bool = False,
    limit: int = 100,
    offset: int = 0,
    test_run_service: TestRunService = Depends(get_test_run_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.TEST_RUNS_READ)),
) -> PaginatedResponse[TestRunResponse]:
    """List test runs with optional filters."""
    result = await test_run_service.list_test_runs(
        server_id=server_id,
        project_id=project_id,
        success=success,
        limit=limit,
        offset=offset,
        include_output=include_output,
        include_logs=include_logs,
        include_artifacts=include_artifacts,
    )
    params: QueryParamMap = {
        "server_id": server_id,
        "project_id": project_id,
        "success": success,
        "include_output": include_output,
        "include_logs": include_logs,
        "include_artifacts": include_artifacts,
        "limit": limit,
        "offset": offset,
    }
    self_path = build_query_path("/api/v1/test-runs", params)
    next_path = next_page_path(
        path="/api/v1/test-runs",
        params=params,
        total_count=result.total_count,
        offset=result.offset,
        limit=result.limit,
    )
    next_steps = normalize_next_steps(
        "GET /api/v1/test-runs/{run_id}",
        "GET /api/v1/test-runs/retention",
        "POST /api/v1/test-runs/prune",
    )

    return {
        "items": [_run_to_response(run) for run in result.items],
        "total_count": result.total_count,
        "offset": result.offset,
        "limit": result.limit,
        "links": paginated_links(self_path=self_path, next_path=next_path),
        "next_steps": next_steps,
        "params": params,
    }


@router.get("/test-runs/retention", response_model=TestRunRetentionResponse)
async def get_test_run_retention(
    limit: int = 20,
    sort: RetentionUsageSort = "largest",
    project_id: str | None = None,
    org_id: str | None = None,
    retention_service: TestRunRetentionService = Depends(
        get_test_run_retention_service
    ),
    _api_key: ApiKey = Depends(require_scope(Scopes.TEST_RUNS_READ)),
) -> TestRunRetentionResponse:
    """Get test run retention usage summary."""
    if project_id and org_id:
        raise HTTPException(
            status_code=400, detail="Use project_id or org_id, not both"
        )

    summary = await retention_service.get_usage(
        limit=limit,
        sort=sort,
        project_ids=[project_id] if project_id else None,
        org_id=org_id,
    )
    return TestRunRetentionResponse(**summary.to_dict())


@router.get("/test-runs/{run_id}", response_model=TestRunResponse)
async def get_test_run(
    run_id: str,
    include_output: bool = True,
    include_logs: bool = True,
    include_artifacts: bool = True,
    test_run_service: TestRunService = Depends(get_test_run_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.TEST_RUNS_READ)),
) -> TestRunResponse:
    """Get a test run by ID."""
    run = await test_run_service.get_test_run(
        run_id,
        include_output=include_output,
        include_logs=include_logs,
        include_artifacts=include_artifacts,
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Test run not found")

    return _run_to_response(run)


@router.post("/test-runs/prune", response_model=TestRunPruneResponse)
async def prune_test_runs(
    max_log_bytes: int | None = None,
    max_artifact_bytes: int | None = None,
    max_age_days: int | None = None,
    dry_run: bool = False,
    project_id: str | None = None,
    org_id: str | None = None,
    use_policies: bool = True,
    retention_service: TestRunRetentionService = Depends(
        get_test_run_retention_service
    ),
    _api_key: ApiKey = Depends(require_scope(Scopes.TEST_RUNS_WRITE)),
) -> TestRunPruneResponse:
    """Prune stored test run outputs by age and size."""
    if project_id and org_id:
        raise HTTPException(
            status_code=400, detail="Use project_id or org_id, not both"
        )
    summary = await retention_service.prune(
        max_log_bytes=max_log_bytes,
        max_artifact_bytes=max_artifact_bytes,
        max_age_days=max_age_days,
        dry_run=dry_run,
        project_ids=[project_id] if project_id else None,
        org_id=org_id,
        use_policies=use_policies,
    )
    return TestRunPruneResponse(**summary.to_dict())


@router.get("/test-runs/retention/policies")
async def list_retention_policies(
    scope_type: str | None = None,
    scope_id: str | None = None,
    include_archived: bool = False,
    limit: int = 100,
    offset: int = 0,
    policy_service: TestRunRetentionPolicyService = Depends(
        get_test_run_retention_policy_service
    ),
    _api_key: ApiKey = Depends(require_scope(Scopes.TEST_RUNS_READ)),
) -> RetentionPoliciesResponsePayload:
    """List retention policies."""
    if scope_type:
        try:
            scope_type = policy_service.normalize_scope_type(scope_type)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    policies = await policy_service.list_policies(
        scope_type=scope_type,
        scope_id=scope_id,
        limit=limit,
        offset=offset,
        include_archived=include_archived,
    )
    return {
        "items": [
            TestRunRetentionPolicyResponse(**policy.to_dict())
            for policy in policies.items
        ],
        "page": {
            "total_count": policies.total_count,
            "limit": policies.limit,
            "offset": policies.offset,
            "has_more": policies.has_more,
            "next_offset": policies.offset + policies.limit
            if policies.has_more
            else None,
        },
    }


@router.post(
    "/test-runs/retention/policies",
    response_model=TestRunRetentionPolicyResponse,
)
async def upsert_retention_policy(
    scope_type: str,
    scope_id: str,
    max_log_bytes: int = 0,
    max_artifact_bytes: int = 0,
    max_age_days: int = 0,
    notes: str | None = None,
    policy_service: TestRunRetentionPolicyService = Depends(
        get_test_run_retention_policy_service
    ),
    _api_key: ApiKey = Depends(require_scope(Scopes.TEST_RUNS_WRITE)),
) -> TestRunRetentionPolicyResponse:
    """Create or update a retention policy for a scope."""
    try:
        scope_type = policy_service.normalize_scope_type(scope_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    policy = await policy_service.upsert_policy(
        scope_type=scope_type,
        scope_id=scope_id,
        max_log_bytes=max_log_bytes,
        max_artifact_bytes=max_artifact_bytes,
        max_age_days=max_age_days,
        notes=notes,
    )
    return TestRunRetentionPolicyResponse(**policy.to_dict())


@router.get(
    "/test-runs/retention/policies/{policy_id}",
    response_model=TestRunRetentionPolicyResponse,
)
async def get_retention_policy(
    policy_id: str,
    policy_service: TestRunRetentionPolicyService = Depends(
        get_test_run_retention_policy_service
    ),
    _api_key: ApiKey = Depends(require_scope(Scopes.TEST_RUNS_READ)),
) -> TestRunRetentionPolicyResponse:
    """Get a retention policy by ID."""
    policy = await policy_service.get_policy(policy_id)
    if policy is None:
        raise HTTPException(status_code=404, detail="Retention policy not found")
    return TestRunRetentionPolicyResponse(**policy.to_dict())


@router.patch(
    "/test-runs/retention/policies/{policy_id}",
    response_model=TestRunRetentionPolicyResponse,
)
async def update_retention_policy(
    policy_id: str,
    max_log_bytes: int | None = None,
    max_artifact_bytes: int | None = None,
    max_age_days: int | None = None,
    notes: str | None = None,
    policy_service: TestRunRetentionPolicyService = Depends(
        get_test_run_retention_policy_service
    ),
    _api_key: ApiKey = Depends(require_scope(Scopes.TEST_RUNS_WRITE)),
) -> TestRunRetentionPolicyResponse:
    """Update a retention policy by ID."""
    policy = await policy_service.update_policy(
        policy_id,
        max_log_bytes=max_log_bytes,
        max_artifact_bytes=max_artifact_bytes,
        max_age_days=max_age_days,
        notes=notes,
    )
    if policy is None:
        raise HTTPException(status_code=404, detail="Retention policy not found")
    return TestRunRetentionPolicyResponse(**policy.to_dict())


@router.post("/test-runs/retention/policies/{policy_id}/archive")
async def archive_retention_policy(
    policy_id: str,
    policy_service: TestRunRetentionPolicyService = Depends(
        get_test_run_retention_policy_service
    ),
    _api_key: ApiKey = Depends(require_scope(Scopes.TEST_RUNS_WRITE)),
) -> dict[str, bool]:
    """Archive a retention policy."""
    archived = await policy_service.archive_policy(policy_id)
    if not archived:
        raise HTTPException(status_code=404, detail="Retention policy not found")
    return {"archived": True}


@router.post(
    "/test-runs/retention/policies/{policy_id}/restore",
    response_model=TestRunRetentionPolicyResponse,
)
async def restore_retention_policy(
    policy_id: str,
    policy_service: TestRunRetentionPolicyService = Depends(
        get_test_run_retention_policy_service
    ),
    _api_key: ApiKey = Depends(require_scope(Scopes.TEST_RUNS_WRITE)),
) -> TestRunRetentionPolicyResponse:
    """Restore an archived retention policy."""
    policy = await policy_service.restore_policy(policy_id)
    if policy is None:
        raise HTTPException(status_code=404, detail="Retention policy not found")
    return TestRunRetentionPolicyResponse(**policy.to_dict())
