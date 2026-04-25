"""FastAPI application for PMS Web API server."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Literal, Protocol, TypedDict

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from pms import __version__
from pms.api.auth import get_api_key
from pms.api.dependencies import init_services
from pms.api.routes.discoverability import (
    QueryParamMap,
    build_query_path,
    normalize_next_steps,
)
from pms.db.connection import init_database
from pms.exceptions import (
    ConstraintViolationError,
    DuplicateError,
    NotFoundError,
    TaskCheckoutBlocked,
    TaskCheckoutConflict,
    ValidationError,
)
from pms.models.api_key import ApiKey

# Track server start time
_start_time = time.time()


class SupportsStop(Protocol):
    """Background service protocol with async stop."""

    async def stop(self) -> None: ...


class HealthCheckPayload(TypedDict):
    """Health check response payload."""

    status: Literal["healthy", "degraded"]
    database: str
    backend: str
    schema_version: int
    schema_name: str
    uptime_seconds: float


class RootLinksPayload(TypedDict):
    """Top-level discoverability links for API consumers."""

    docs: str
    openapi_json: str
    health: str
    dashboard: str
    auth_scopes: str
    discoverability_graph: str
    observability_overview: str
    api_reference: str
    getting_started: str
    immediate_start: str


class RootEntryPointPayload(TypedDict):
    """Single API entrypoint with continuation hints."""

    name: str
    method: str
    path: str
    why: str
    what_next: list[str]


class RootScenarioPayload(TypedDict):
    """Scenario bootstrap path for real-world usage."""

    name: str
    goal: str
    start_with: str
    continue_with: list[str]


class RootDiscoverabilityPayload(TypedDict):
    """Structured navigation map for the API surface."""

    entry_points: list[RootEntryPointPayload]
    observability: list[RootEntryPointPayload]
    scenarios: list[RootScenarioPayload]


class RootPayload(TypedDict):
    """Root endpoint payload."""

    name: str
    version: str
    status: str
    docs: str
    health: str
    links: RootLinksPayload
    discoverability: RootDiscoverabilityPayload


class DiscoverabilityGraphNodePayload(TypedDict):
    """Single node in discoverability graph output."""

    id: str
    category: str
    name: str
    method: str
    path: str
    why: str
    what_next: list[str]


class DiscoverabilityGraphEdgePayload(TypedDict):
    """Directed continuation edge in discoverability graph."""

    from_node: str
    to_node: str
    reason: str


class DiscoverabilityGraphParamsPayload(TypedDict):
    """Echoed query params for discoverability graph requests."""

    include_entry_points: bool
    include_observability: bool
    include_scenarios: bool
    max_next_steps: int
    path_contains: str | None


class DiscoverabilityGraphLinksPayload(TypedDict):
    """Discoverability graph continuation links."""

    self: str
    root: str
    auth_scopes: str
    api_reference: str
    web_api: str


class DiscoverabilityGraphPayload(TypedDict):
    """Discoverability graph endpoint response payload."""

    generated_at: str
    nodes: list[DiscoverabilityGraphNodePayload]
    edges: list[DiscoverabilityGraphEdgePayload]
    scenarios: list[RootScenarioPayload]
    links: DiscoverabilityGraphLinksPayload
    next_steps: list[str]
    params: DiscoverabilityGraphParamsPayload


_HTTP_METHODS: frozenset[str] = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})


def _build_root_discoverability() -> RootDiscoverabilityPayload:
    """Build the root discoverability catalog."""
    return {
        "entry_points": [
            {
                "name": "Discoverability Graph",
                "method": "GET",
                "path": "/api/v1/discoverability/graph",
                "why": "Load the full entry-point/continuation graph for guided usage.",
                "what_next": [
                    "GET /api/v1/auth/scopes",
                    "GET /api/v1/organizations/dashboard",
                ],
            },
            {
                "name": "Authentication Scopes",
                "method": "GET",
                "path": "/api/v1/auth/scopes",
                "why": "Discover permission model before key creation/integration.",
                "what_next": [
                    "POST /api/v1/auth/keys",
                    "GET /api/v1/projects",
                ],
            },
            {
                "name": "Instance Project Dashboard",
                "method": "GET",
                "path": "/api/v1/dashboard",
                "why": "Get instance-wide lifecycle rollups + terminal context for operator decisions.",
                "what_next": [
                    "GET /api/v1/projects",
                    "GET /api/v1/portfolios/dashboard",
                    "GET /api/v1/programs/dashboard",
                ],
            },
            {
                "name": "Work Snapshot",
                "method": "GET",
                "path": "/api/v1/work-snapshots/{scope_type}/{scope_id}",
                "why": "Fetch a scope-level digest with evidence and lineage.",
                "what_next": [
                    "GET /api/v1/work-snapshots/{scope_type}/{scope_id}/daily",
                    "POST /api/v1/work-snapshots/{scope_type}/{scope_id}/review",
                ],
            },
        ],
        "observability": [
            {
                "name": "Observability Overview",
                "method": "GET",
                "path": "/api/v1/observability/overview",
                "why": "Fetch unified live state, risks, queues, lineage, and activity timeline.",
                "what_next": [
                    "GET /api/v1/organizations/dashboard",
                    "GET /api/v1/work-snapshots/{scope_type}/{scope_id}/daily",
                ],
            },
            {
                "name": "Web Dashboard",
                "method": "GET",
                "path": "/dashboard",
                "why": "Live rollups + retention + queues + snapshots in one UI.",
                "what_next": [
                    "GET /api/v1/organizations/dashboard",
                    "GET /api/v1/plans/lineage",
                ],
            },
            {
                "name": "Queue Presets",
                "method": "GET",
                "path": "/api/v1/queues/presets",
                "why": "Ready/blocker/at-risk queue view for immediate action.",
                "what_next": [
                    "GET /api/v1/queues/{queue_id}/run",
                    "GET /api/v1/tasks/ready",
                ],
            },
            {
                "name": "Plan Lineage",
                "method": "GET",
                "path": "/api/v1/plans/lineage",
                "why": "Trace plan -> task -> test evidence over time.",
                "what_next": [
                    "GET /api/v1/tasks/{task_id}/proof-bundle",
                    "GET /api/v1/revisions/project/{project_id}/bundle",
                ],
            },
        ],
        "scenarios": [
            {
                "name": "Drop-in Start Go Extend Grow",
                "goal": "Spin up, execute, extend, and export in one flow.",
                "start_with": "scripts/run_dropin_start_go_extend_grow.sh",
                "continue_with": [
                    "scripts/run_dropin_contract_smoke.sh",
                    "examples/real_world/README.md#scenario-dropin",
                ],
            },
            {
                "name": "Team Handoff",
                "goal": "Coordinate cross-team rollout with handoff evidence.",
                "start_with": "scripts/run_team_handoff_flow.sh",
                "continue_with": [
                    "scripts/run_team_handoff_contract_smoke.sh",
                    "examples/real_world/README.md#scenario-team-handoff",
                ],
            },
            {
                "name": "Incident Response",
                "goal": "Triage -> mitigate -> communicate -> postmortem quickly.",
                "start_with": "scripts/run_incident_response_flow.sh",
                "continue_with": [
                    "scripts/run_incident_response_contract_smoke.sh",
                    "examples/real_world/README.md#scenario-incident-response",
                ],
            },
            {
                "name": "User Start Go Observe",
                "goal": "Bootstrap quickly, execute work, and validate observability.",
                "start_with": "scripts/run_user_start_go_observe_flow.sh",
                "continue_with": [
                    "scripts/run_user_start_go_observe_contract_smoke.sh",
                    "examples/real_world/README.md#scenario-user-start-go-observe",
                ],
            },
            {
                "name": "Operational Review",
                "goal": "Run a recurring operator review and export the next-action control surface.",
                "start_with": "scripts/run_operational_review_flow.sh",
                "continue_with": [
                    "scripts/run_operational_review_contract_smoke.sh",
                    "examples/real_world/README.md#scenario-operational-review",
                ],
            },
            {
                "name": "Backlog Triage",
                "goal": "Prioritize ready work, inspect duplicates, and export actionable backlog decisions.",
                "start_with": "scripts/run_backlog_triage_flow.sh",
                "continue_with": [
                    "scripts/run_backlog_triage_contract_smoke.sh",
                    "examples/real_world/README.md#scenario-backlog-triage",
                ],
            },
            {
                "name": "Portfolio Steering",
                "goal": "Inspect multi-project rollups and cross-project dependencies from one steering surface.",
                "start_with": "scripts/run_portfolio_steering_flow.sh",
                "continue_with": [
                    "scripts/run_portfolio_steering_contract_smoke.sh",
                    "examples/real_world/README.md#scenario-portfolio-steering",
                ],
            },
            {
                "name": "Agent Execution Loop",
                "goal": "Generate a live loop prompt/config, run the loop, and close work with proof and a recorded test run.",
                "start_with": "scripts/run_agent_execution_loop_flow.sh",
                "continue_with": [
                    "scripts/run_agent_execution_loop_contract_smoke.sh",
                    "examples/real_world/README.md#scenario-agent-execution-loop",
                ],
            },
        ],
    }


def _parse_route_reference(route_reference: str) -> tuple[str, str]:
    """Parse `METHOD /path` style references."""
    normalized = route_reference.strip()
    parts = normalized.split(" ", 1)
    if len(parts) == 2 and parts[0] in _HTTP_METHODS:
        return parts[0], parts[1]
    return "GET", normalized


def _node_id(method: str, path: str) -> str:
    return f"{method} {path}"


def _matches_path_filter(path_contains: str | None, values: tuple[str, ...]) -> bool:
    if path_contains is None or not path_contains.strip():
        return True
    normalized = path_contains.lower()
    return any(normalized in value.lower() for value in values)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Lifespan context manager for FastAPI.

    Handles startup (initialize database, services) and shutdown (cleanup).
    """
    # Startup
    print("🚀 Starting PMS API Server...")

    # Initialize database (persistent connection!)
    db = await init_database()
    print(f"✓ Database connected: {db.backend_name}")

    # Initialize services
    await init_services(db)
    print("✓ Services initialized")

    # Start background retention pruning
    from pms.api.dependencies import get_test_run_retention_service

    retention_service_runtime = await get_test_run_retention_service()
    await retention_service_runtime.start()
    app.state.retention_service = retention_service_runtime

    # Store in app state
    app.state.db = db
    app.state.start_time = _start_time

    print("✅ PMS API Server ready")
    print("📚 API docs: /docs")

    yield

    # Shutdown
    print("🛑 Shutting down PMS API Server...")
    retention_service_state: SupportsStop | None = getattr(
        app.state, "retention_service", None
    )
    if retention_service_state:
        await retention_service_state.stop()
    await db.disconnect()
    print("✓ Database disconnected")


# Create FastAPI app
app = FastAPI(
    title="PMS API",
    description="Project Management System - Product-centric, complexity-driven, distributed coordination platform",
    version=__version__,
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# Root Endpoint
# ============================================================


@app.get("/")
async def root() -> RootPayload:
    """Root endpoint with API info."""
    links: RootLinksPayload = {
        "docs": "/docs",
        "openapi_json": "/openapi.json",
        "health": "/api/v1/health",
        "dashboard": "/dashboard",
        "api_dashboard": "/api/v1/dashboard",
        "auth_scopes": "/api/v1/auth/scopes",
        "discoverability_graph": "/api/v1/discoverability/graph",
        "observability_overview": "/api/v1/observability/overview",
        "api_reference": "docs/API_REFERENCE.md",
        "getting_started": "GETTING_STARTED.md",
        "immediate_start": "docs/IMMEDIATE_START_GO.md",
    }
    discoverability = _build_root_discoverability()
    return {
        "name": "PMS API",
        "version": __version__,
        "status": "operational",
        "docs": "/docs",
        "health": "/api/v1/health",
        "links": links,
        "discoverability": discoverability,
    }


@app.get("/api/v1/discoverability/graph")
async def discoverability_graph(
    include_entry_points: bool = True,
    include_observability: bool = True,
    include_scenarios: bool = True,
    max_next_steps: int = 8,
    path_contains: str | None = None,
    _api_key: ApiKey = Depends(get_api_key),
) -> DiscoverabilityGraphPayload:
    """Return entry points + continuation edges for guided API exploration."""
    discoverability = _build_root_discoverability()
    nodes: list[DiscoverabilityGraphNodePayload] = []
    edges: list[DiscoverabilityGraphEdgePayload] = []
    node_lookup: dict[str, DiscoverabilityGraphNodePayload] = {}

    def add_node(
        *,
        category: str,
        name: str,
        method: str,
        path: str,
        why: str,
        what_next: list[str],
    ) -> None:
        node_key = _node_id(method, path)
        if node_key in node_lookup:
            return
        node: DiscoverabilityGraphNodePayload = {
            "id": node_key,
            "category": category,
            "name": name,
            "method": method,
            "path": path,
            "why": why,
            "what_next": list(what_next[:max_next_steps]),
        }
        node_lookup[node_key] = node
        nodes.append(node)

    if include_entry_points:
        for entry in discoverability["entry_points"]:
            if not _matches_path_filter(
                path_contains,
                (
                    entry["name"],
                    entry["path"],
                    entry["why"],
                    *entry["what_next"],
                ),
            ):
                continue
            add_node(
                category="entry_point",
                name=entry["name"],
                method=entry["method"],
                path=entry["path"],
                why=entry["why"],
                what_next=entry["what_next"],
            )

    if include_observability:
        for entry in discoverability["observability"]:
            if not _matches_path_filter(
                path_contains,
                (
                    entry["name"],
                    entry["path"],
                    entry["why"],
                    *entry["what_next"],
                ),
            ):
                continue
            add_node(
                category="observability",
                name=entry["name"],
                method=entry["method"],
                path=entry["path"],
                why=entry["why"],
                what_next=entry["what_next"],
            )

    for source in list(nodes):
        for step in source["what_next"]:
            step_method, step_path = _parse_route_reference(step)
            if not _matches_path_filter(path_contains, (step, step_path)):
                continue
            target_key = _node_id(step_method, step_path)
            if target_key not in node_lookup:
                add_node(
                    category="follow_up",
                    name=step_path,
                    method=step_method,
                    path=step_path,
                    why=f"Continuation from {source['name']}",
                    what_next=[],
                )
            edges.append(
                {
                    "from_node": source["id"],
                    "to_node": target_key,
                    "reason": f"Suggested by {source['name']}",
                }
            )

    scenarios: list[RootScenarioPayload] = []
    if include_scenarios:
        scenarios = [
            scenario
            for scenario in discoverability["scenarios"]
            if _matches_path_filter(
                path_contains,
                (
                    scenario["name"],
                    scenario["goal"],
                    scenario["start_with"],
                    *scenario["continue_with"],
                ),
            )
        ]

    params: DiscoverabilityGraphParamsPayload = {
        "include_entry_points": include_entry_points,
        "include_observability": include_observability,
        "include_scenarios": include_scenarios,
        "max_next_steps": max_next_steps,
        "path_contains": path_contains,
    }
    query_params: QueryParamMap = {
        "include_entry_points": include_entry_points,
        "include_observability": include_observability,
        "include_scenarios": include_scenarios,
        "max_next_steps": max_next_steps,
        "path_contains": path_contains,
    }
    links: DiscoverabilityGraphLinksPayload = {
        "self": build_query_path("/api/v1/discoverability/graph", query_params),
        "root": "/",
        "auth_scopes": "/api/v1/auth/scopes",
        "api_reference": "docs/API_REFERENCE.md",
        "web_api": "docs/WEB_API.md",
    }
    next_steps = normalize_next_steps(
        "GET /api/v1/observability/overview",
        "GET /api/v1/auth/scopes",
        "GET /api/v1/organizations/dashboard",
        "GET /api/v1/work-snapshots/{scope_type}/{scope_id}",
    )

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "nodes": nodes,
        "edges": edges,
        "scenarios": scenarios,
        "links": links,
        "next_steps": next_steps,
        "params": params,
    }


# ============================================================
# Health Check
# ============================================================


@app.get("/api/v1/health")
async def health_check() -> HealthCheckPayload:
    """Health check endpoint."""
    from pms.api.dependencies import get_db

    db = await get_db()
    uptime = time.time() - app.state.start_time

    # Check database
    try:
        await db.fetch_one("SELECT 1")
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {e}"

    # Get schema version
    schema_version = await db.get_schema_version()
    from pms.db.schema import SCHEMA_NAME

    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "database": db_status,
        "backend": db.backend_name,
        "schema_version": schema_version,
        "schema_name": SCHEMA_NAME,
        "uptime_seconds": uptime,
    }


# ============================================================
# Import and register routes
# ============================================================

from pms.api.routes import (
    actors,
    agent_loops,
    auth,
    automation_rules,
    checkout,
    comments,
    custom_fields,
    dashboard,
    evidence_gates,
    goals,
    key_results,
    labels,
    objectives,
    observability,
    organizations,
    plans,
    portfolios,
    products,
    programs,
    progress,
    projects,
    queues,
    revisions,
    tasks,
    teams,
    test_runs,
    transitions,
    work_snapshots,
    workflows,
)

app.include_router(auth.router)  # Auth routes (already have /api/v1 prefix)
app.include_router(actors.router, prefix="/api/v1", tags=["actors"])
app.include_router(goals.router, prefix="/api/v1", tags=["goals"])
app.include_router(objectives.router, prefix="/api/v1", tags=["objectives"])
app.include_router(observability.router, prefix="/api/v1", tags=["observability"])
app.include_router(key_results.router, prefix="/api/v1", tags=["key_results"])
app.include_router(plans.router, prefix="/api/v1", tags=["plans"])
app.include_router(organizations.router, prefix="/api/v1", tags=["organizations"])
app.include_router(teams.router, prefix="/api/v1", tags=["teams"])
app.include_router(portfolios.router, prefix="/api/v1", tags=["portfolios"])
app.include_router(programs.router, prefix="/api/v1", tags=["programs"])
app.include_router(products.router, prefix="/api/v1", tags=["products"])
app.include_router(projects.router, prefix="/api/v1", tags=["projects"])
app.include_router(tasks.router, prefix="/api/v1", tags=["tasks"])
app.include_router(custom_fields.router, prefix="/api/v1", tags=["custom_fields"])
app.include_router(comments.router, prefix="/api/v1", tags=["comments"])
app.include_router(automation_rules.router, prefix="/api/v1", tags=["automation"])
app.include_router(queues.router, prefix="/api/v1", tags=["queues"])
app.include_router(test_runs.router, prefix="/api/v1", tags=["test_runs"])
app.include_router(evidence_gates.router, prefix="/api/v1", tags=["evidence_gates"])
app.include_router(work_snapshots.router, prefix="/api/v1", tags=["work_snapshots"])
app.include_router(labels.router, prefix="/api/v1", tags=["labels"])
app.include_router(checkout.router, prefix="/api/v1", tags=["checkout"])
app.include_router(progress.router, prefix="/api/v1", tags=["progress"])
app.include_router(workflows.router, prefix="/api/v1", tags=["workflows"])
app.include_router(agent_loops.router, prefix="/api/v1", tags=["agent_loops"])
app.include_router(transitions.router, prefix="/api/v1", tags=["transitions"])
app.include_router(revisions.router, prefix="/api/v1", tags=["revisions"])
app.include_router(dashboard.router, tags=["dashboard"])


# ============================================================
# Error Handling
# ============================================================


def _error_payload(error: str, detail: str, **extras: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "error": error,
        "detail": detail,
    }
    payload.update({key: value for key, value in extras.items() if value is not None})
    return payload


@app.exception_handler(ValidationError)
async def validation_exception_handler(
    request: Request,
    exc: ValidationError,
) -> JSONResponse:
    """Render structured validation failures."""
    return JSONResponse(
        status_code=400,
        content=_error_payload(
            "Validation error",
            exc.message,
            **exc.details,
        ),
    )


@app.exception_handler(NotFoundError)
async def not_found_exception_handler(
    request: Request,
    exc: NotFoundError,
) -> JSONResponse:
    """Render structured not-found failures."""
    return JSONResponse(
        status_code=404,
        content=_error_payload(
            "Not found",
            exc.message,
            **exc.details,
        ),
    )


@app.exception_handler(DuplicateError)
async def duplicate_exception_handler(
    request: Request,
    exc: DuplicateError,
) -> JSONResponse:
    """Render structured duplicate failures."""
    return JSONResponse(
        status_code=409,
        content=_error_payload(
            "Duplicate resource",
            exc.message,
            **exc.details,
        ),
    )


@app.exception_handler(ConstraintViolationError)
async def constraint_exception_handler(
    request: Request,
    exc: ConstraintViolationError,
) -> JSONResponse:
    """Render structured database constraint failures."""
    status_code = 409 if exc.constraint_kind == "unique" else 400
    return JSONResponse(
        status_code=status_code,
        content=_error_payload(
            "Constraint violation",
            exc.message,
            **exc.details,
        ),
    )


@app.exception_handler(TaskCheckoutConflict)
async def checkout_conflict_exception_handler(
    request: Request,
    exc: TaskCheckoutConflict,
) -> JSONResponse:
    """Render checkout conflicts consistently."""
    return JSONResponse(
        status_code=409,
        content=_error_payload("Checkout conflict", str(exc)),
    )


@app.exception_handler(TaskCheckoutBlocked)
async def checkout_blocked_exception_handler(
    request: Request,
    exc: TaskCheckoutBlocked,
) -> JSONResponse:
    """Render checkout blocks consistently."""
    return JSONResponse(
        status_code=423,
        content=_error_payload("Checkout blocked", str(exc)),
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Global exception handler."""
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc),
        },
    )
