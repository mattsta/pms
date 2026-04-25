"""Agent tools for project and task operations."""

from __future__ import annotations

import contextlib
import json
from typing import TYPE_CHECKING, Any

from claude_code_sdk import tool

if TYPE_CHECKING:
    from pms.services import (
        AutomationRuleService,
        CommentService,
        CustomFieldService,
        GoalService,
        OrganizationService,
        PlanService,
        PlanTestJobService,
        PortfolioService,
        ProgramService,
        ProjectService,
        QueueService,
        SavedSearchService,
        TaskService,
        TeamService,
        TestRunRetentionService,
        TestRunService,
        WorkSnapshotService,
    )


# Global service instances - set by server initialization
_project_service: ProjectService | None = None
_task_service: TaskService | None = None
_goal_service: GoalService | None = None
_plan_service: PlanService | None = None
_plan_test_job_service: PlanTestJobService | None = None
_organization_service: OrganizationService | None = None
_team_service: TeamService | None = None
_portfolio_service: PortfolioService | None = None
_program_service: ProgramService | None = None
_test_run_service: TestRunService | None = None
_test_run_retention_service: TestRunRetentionService | None = None
_saved_search_service: SavedSearchService | None = None
_queue_service: QueueService | None = None
_work_snapshot_service: WorkSnapshotService | None = None
_custom_field_service: CustomFieldService | None = None
_comment_service: CommentService | None = None
_automation_rule_service: AutomationRuleService | None = None


def set_services(
    project_service: ProjectService,
    task_service: TaskService,
    goal_service: GoalService | None = None,
    plan_service: PlanService | None = None,
    plan_test_job_service: PlanTestJobService | None = None,
    organization_service: OrganizationService | None = None,
    team_service: TeamService | None = None,
    portfolio_service: PortfolioService | None = None,
    program_service: ProgramService | None = None,
    test_run_service: TestRunService | None = None,
    test_run_retention_service: TestRunRetentionService | None = None,
    saved_search_service: SavedSearchService | None = None,
    queue_service: QueueService | None = None,
    work_snapshot_service: WorkSnapshotService | None = None,
    custom_field_service: CustomFieldService | None = None,
    comment_service: CommentService | None = None,
    automation_rule_service: AutomationRuleService | None = None,
) -> None:
    """Set the service instances for tools to use."""
    global _project_service, _task_service, _goal_service, _plan_service
    global _plan_test_job_service
    global _organization_service, _team_service, _portfolio_service, _program_service
    global _test_run_service, _test_run_retention_service
    global _saved_search_service, _queue_service, _work_snapshot_service
    global _custom_field_service, _comment_service, _automation_rule_service
    _project_service = project_service
    _task_service = task_service
    _goal_service = goal_service
    _plan_service = plan_service
    _plan_test_job_service = plan_test_job_service
    _organization_service = organization_service
    _team_service = team_service
    _portfolio_service = portfolio_service
    _program_service = program_service
    _test_run_service = test_run_service
    _test_run_retention_service = test_run_retention_service
    _saved_search_service = saved_search_service
    _queue_service = queue_service
    _work_snapshot_service = work_snapshot_service
    if custom_field_service is None:
        try:
            from pms.services.custom_field_service import CustomFieldService

            custom_field_service = CustomFieldService(
                task_service.db,
                task_service.metrics,
            )
        except Exception:
            custom_field_service = None
    _custom_field_service = custom_field_service
    if comment_service is None:
        try:
            from pms.services.comment_service import CommentService

            comment_service = CommentService(
                task_service.db,
                task_service.metrics,
            )
        except Exception:
            comment_service = None
    _comment_service = comment_service
    if automation_rule_service is None:
        try:
            from pms.services.automation_rule_service import AutomationRuleService

            automation_rule_service = AutomationRuleService(
                task_service.db,
                task_service.metrics,
                task_service=task_service,
                comment_service=comment_service,
                custom_field_service=custom_field_service,
            )
        except Exception:
            automation_rule_service = None
    _automation_rule_service = automation_rule_service


def _get_project_service() -> ProjectService:
    """Get project service or raise if not initialized."""
    if _project_service is None:
        raise RuntimeError("Project service not initialized. Call set_services first.")
    return _project_service


def _get_task_service() -> TaskService:
    """Get task service or raise if not initialized."""
    if _task_service is None:
        raise RuntimeError("Task service not initialized. Call set_services first.")
    return _task_service


def _get_test_run_service() -> TestRunService:
    """Get test run service or raise if not initialized."""
    if _test_run_service is None:
        raise RuntimeError("Test run service not initialized. Call set_services first.")
    return _test_run_service


def _get_test_run_retention_service() -> TestRunRetentionService:
    """Get test run retention service or raise if not initialized."""
    if _test_run_retention_service is None:
        raise RuntimeError(
            "Test run retention service not initialized. Call set_services first."
        )
    return _test_run_retention_service


def _get_goal_service() -> GoalService:
    """Get goal service or raise if not initialized."""
    if _goal_service is None:
        raise RuntimeError("Goal service not initialized. Call set_services first.")
    return _goal_service


def _get_custom_field_service() -> CustomFieldService:
    """Get custom field service or raise if not initialized."""
    if _custom_field_service is None:
        raise RuntimeError(
            "Custom field service not initialized. Call set_services first."
        )
    return _custom_field_service


def _get_comment_service() -> CommentService:
    """Get comment service or raise if not initialized."""
    if _comment_service is None:
        raise RuntimeError("Comment service not initialized. Call set_services first.")
    return _comment_service


def _get_automation_rule_service() -> AutomationRuleService:
    """Get automation rule service or raise if not initialized."""
    if _automation_rule_service is None:
        raise RuntimeError(
            "Automation rule service not initialized. Call set_services first."
        )
    return _automation_rule_service


def _get_plan_test_job_service() -> PlanTestJobService:
    """Get plan test job service or raise if not initialized."""
    if _plan_test_job_service is None:
        raise RuntimeError(
            "Plan test job service not initialized. Call set_services first."
        )
    return _plan_test_job_service


def _get_saved_search_service() -> SavedSearchService:
    """Get saved search service or raise if not initialized."""
    if _saved_search_service is None:
        raise RuntimeError(
            "Saved search service not initialized. Call set_services first."
        )
    return _saved_search_service


def _get_queue_service() -> QueueService:
    """Get queue service or raise if not initialized."""
    if _queue_service is None:
        raise RuntimeError("Queue service not initialized. Call set_services first.")
    return _queue_service


def _page_payload(total_count: int, limit: int, offset: int) -> dict[str, Any]:
    limit_value = max(int(limit), 0)
    offset_value = max(int(offset), 0)
    has_more = False
    next_offset = None
    if limit_value > 0 and offset_value + limit_value < total_count:
        has_more = True
        next_offset = offset_value + limit_value
    return {
        "total_count": total_count,
        "limit": limit_value,
        "offset": offset_value,
        "has_more": has_more,
        "next_offset": next_offset,
    }


def _get_work_snapshot_service() -> WorkSnapshotService:
    """Get work snapshot service or raise if not initialized."""
    if _work_snapshot_service is None:
        raise RuntimeError(
            "Work snapshot service not initialized. Call set_services first."
        )
    return _work_snapshot_service


def _get_plan_service() -> PlanService:
    """Get plan service or raise if not initialized."""
    if _plan_service is None:
        raise RuntimeError("Plan service not initialized. Call set_services first.")
    return _plan_service


def _get_organization_service() -> OrganizationService:
    """Get organization service or raise if not initialized."""
    if _organization_service is None:
        raise RuntimeError(
            "Organization service not initialized. Call set_services first."
        )
    return _organization_service


def _get_team_service() -> TeamService:
    """Get team service or raise if not initialized."""
    if _team_service is None:
        raise RuntimeError("Team service not initialized. Call set_services first.")
    return _team_service


def _get_portfolio_service() -> PortfolioService:
    """Get portfolio service or raise if not initialized."""
    if _portfolio_service is None:
        raise RuntimeError(
            "Portfolio service not initialized. Call set_services first."
        )
    return _portfolio_service


def _get_program_service() -> ProgramService:
    """Get program service or raise if not initialized."""
    if _program_service is None:
        raise RuntimeError("Program service not initialized. Call set_services first.")
    return _program_service


def _get_actor_service():
    """Get actor service derived from the task-service runtime."""
    task_service = _get_task_service()
    from pms.services.actor_service import ActorService

    return ActorService(
        task_service.db,
        task_service.events,
        task_service.revisions,
        task_service.metrics,
    )


# =============================================================================
# Actor Tools
# =============================================================================


@tool(
    "create_actor",
    "Create a canonical actor for a human, persona, team, or runtime agent",
    {
        "name": str,
        "kind": str,
        "handle": str,
        "description": str,
        "tags": str,
    },
)
async def create_actor(args: dict[str, Any]) -> dict[str, Any]:
    """Create a new actor."""
    from pms.models import ActorKind

    service = _get_actor_service()
    tags = [t.strip() for t in args.get("tags", "").split(",") if t.strip()]
    kind_value = str(args.get("kind", "human")).lower()
    try:
        actor = await service.create_actor(
            name=args["name"],
            kind=ActorKind(kind_value),
            handle=args.get("handle"),
            description=args.get("description"),
            tags=tags or None,
        )
    except ValueError as exc:
        return {
            "content": [{"type": "text", "text": str(exc)}],
            "is_error": True,
        }
    return {
        "content": [
            {
                "type": "text",
                "text": f"Created actor '{actor.name}' ({actor.handle}) with ID: {actor.id}",
            }
        ]
    }


@tool(
    "list_actors",
    "List actors with optional kind or status filters",
    {"kind": str, "status": str},
)
async def list_actors(args: dict[str, Any]) -> dict[str, Any]:
    """List actors."""
    from pms.models import ActorKind, ActorStatus

    service = _get_actor_service()
    kind = None
    status = None
    if args.get("kind"):
        try:
            kind = ActorKind(str(args["kind"]).lower())
        except ValueError:
            return {
                "content": [{"type": "text", "text": "Invalid actor kind."}],
                "is_error": True,
            }
    if args.get("status"):
        try:
            status = ActorStatus(str(args["status"]).lower())
        except ValueError:
            return {
                "content": [{"type": "text", "text": "Invalid actor status."}],
                "is_error": True,
            }
    result = await service.list_actors(kind=kind, status=status)
    if not result.items:
        return {"content": [{"type": "text", "text": "No actors found."}]}
    lines = [f"Found {result.total_count} actor(s):"]
    for actor in result.items:
        lines.append(
            f"- {actor.name} ({actor.handle}) [{actor.kind.value}/{actor.status.value}] - ID: {actor.id}"
        )
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "get_actor",
    "Get actor graph details and workload by actor handle or id",
    {"identifier": str},
)
async def get_actor(args: dict[str, Any]) -> dict[str, Any]:
    """Get actor details and workload."""
    service = _get_actor_service()
    snapshot = await service.get_actor_graph(args["identifier"], include_inherited=True)
    if snapshot is None:
        return {
            "content": [
                {"type": "text", "text": f"Actor '{args['identifier']}' not found."}
            ],
            "is_error": True,
        }
    workload = snapshot.workload
    lines = [
        f"Actor: {snapshot.actor.name}",
        f"Handle: {snapshot.actor.handle}",
        f"Kind: {snapshot.actor.kind.value}",
        f"Status: {snapshot.actor.status.value}",
    ]
    if workload is not None:
        lines.append(
            "Workload: "
            f"{workload.effective.total_tasks} total "
            f"({workload.direct.total_tasks} direct, "
            f"{workload.inherited_only.total_tasks} inherited)"
        )
    if snapshot.child_memberships:
        lines.append(f"Members: {len(snapshot.child_memberships)}")
    if snapshot.parent_memberships:
        lines.append(f"Parents: {len(snapshot.parent_memberships)}")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "add_actor_alias",
    "Add an alias to an actor",
    {"actor": str, "alias": str},
)
async def add_actor_alias(args: dict[str, Any]) -> dict[str, Any]:
    """Add an alias to an actor."""
    service = _get_actor_service()
    try:
        alias = await service.add_alias(args["actor"], args["alias"])
    except ValueError as exc:
        return {
            "content": [{"type": "text", "text": str(exc)}],
            "is_error": True,
        }
    return {
        "content": [
            {
                "type": "text",
                "text": f"Added alias '{alias.alias}' to actor {args['actor']}",
            }
        ]
    }


@tool(
    "add_actor_membership",
    "Add a membership edge between actors",
    {"parent": str, "member": str, "role": str},
)
async def add_actor_membership(args: dict[str, Any]) -> dict[str, Any]:
    """Add actor membership."""
    from pms.models import ActorMembershipRole

    service = _get_actor_service()
    try:
        membership = await service.add_membership(
            parent_actor=args["parent"],
            member_actor=args["member"],
            role=ActorMembershipRole(str(args.get("role", "member")).lower()),
        )
    except ValueError as exc:
        return {
            "content": [{"type": "text", "text": str(exc)}],
            "is_error": True,
        }
    return {
        "content": [
            {
                "type": "text",
                "text": (
                    "Created membership "
                    f"{membership.member_actor_id} -> {membership.parent_actor_id} "
                    f"({membership.role.value})"
                ),
            }
        ]
    }


# =============================================================================
# Project Tools
# =============================================================================


def _tool_json_content(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a tool payload encoded as JSON text."""
    return {"content": [{"type": "text", "text": json.dumps(payload, default=str)}]}


async def _resolve_project_identifier(identifier: str):
    """Resolve a project by name first, then by id."""
    service = _get_project_service()
    project = await service.get_project_by_name(identifier)
    if project is None:
        project = await service.get_project(identifier)
    return project


def _project_tool_links(project_id: str) -> dict[str, Any]:
    """Build machine-readable follow-up references for MCP project surfaces."""
    return {
        "self": {"tool": "get_project", "args": {"identifier": project_id}},
        "summary": {"tool": "get_project_summary", "args": {"identifier": project_id}},
        "tasks": {"tool": "list_tasks", "args": {"project": project_id}},
        "dashboard": {"tool": "get_dashboard", "args": {}},
    }


def _project_tool_next_steps(
    project_id: str,
    *,
    focus_task_id: str | None = None,
) -> list[str]:
    """Build next-step guidance for MCP project surfaces."""
    steps = [
        f"Use get_project_summary with identifier={project_id}",
        f"Use list_tasks with project={project_id}",
        "Use get_dashboard for instance-wide project state",
    ]
    if focus_task_id is not None:
        steps.insert(0, f"Use get_task with identifier={focus_task_id}")
    return steps


def _project_focus_task_payload(task: Any | None) -> dict[str, Any] | None:
    """Serialize the selected focus task for MCP payloads."""
    if task is None:
        return None
    return {
        "id": task.id,
        "title": task.title,
        "status": task.status.value,
        "project_id": task.project_id,
        "current_progress_percent": task.current_progress_percent,
    }


async def _project_focus_task(project_id: str) -> Any | None:
    """Resolve the best focus task for a project."""
    from pms.api.routes.detail_contracts import select_focus_task

    task_service = _get_task_service()
    result = await task_service.list_tasks(
        project_id=project_id,
        include_subtasks=True,
        limit=1000,
        offset=0,
    )
    return select_focus_task(result.items)


def _project_summary_payload(
    summary: ProjectSummary,
    *,
    focus_task: Any | None = None,
) -> dict[str, Any]:
    """Serialize a lifecycle-aware project summary for MCP surfaces."""
    from pms.services.generated_artifacts import (
        classify_project_operator_category,
        project_operator_category_label,
        project_operator_visibility_reason,
    )

    effective_status = summary.effective_status or summary.project.status
    category = classify_project_operator_category(
        summary.project,
        effective_status=effective_status.value,
    )
    stats = summary.stats
    return {
        "id": summary.project.id,
        "name": summary.project.name,
        "project_id": summary.project.id,
        "project_name": summary.project.name,
        "description": summary.project.description,
        "status": effective_status.value,
        "stored_status": summary.project.status.value,
        "tags": list(summary.project.tags),
        "org_id": summary.project.org_id,
        "portfolio_id": summary.project.portfolio_id,
        "program_id": summary.project.program_id,
        "product_id": summary.project.product_id,
        "created_at": summary.project.created_at,
        "updated_at": summary.project.updated_at,
        "last_activity_at": summary.last_activity_at,
        "last_transition_at": summary.last_transition_at,
        "terminal_reason": summary.terminal_reason,
        "operator_category": category,
        "operator_category_label": project_operator_category_label(category),
        "operator_visibility_reason": project_operator_visibility_reason(category),
        "focus_task": _project_focus_task_payload(focus_task),
        "total_tasks": stats.total_tasks if stats is not None else 0,
        "completed_tasks": stats.completed_tasks if stats is not None else 0,
        "in_progress_tasks": stats.in_progress_tasks if stats is not None else 0,
        "blocked_tasks": stats.blocked_tasks if stats is not None else 0,
        "completion_percent": stats.completion_percent if stats is not None else 0.0,
        "health_score": summary.health_score,
        "links": _project_tool_links(summary.project.id),
        "next_steps": _project_tool_next_steps(
            summary.project.id,
            focus_task_id=focus_task.id if focus_task is not None else None,
        ),
    }


async def _sorted_project_summaries(
    *, status: Any | None = None
) -> list[ProjectSummary]:
    """List lifecycle-aware project summaries sorted by bubbled recency."""
    from pms.services.rollup_utils import sort_items_by_bubbled_recency

    service = _get_project_service()
    projects = await service.list_all_projects(status=status)
    summary_map = await service.build_project_summary_map(projects)
    sorted_projects = sort_items_by_bubbled_recency(
        projects,
        activity_of=lambda project: summary_map[project.id].last_activity_at,
        transition_of=lambda project: summary_map[project.id].last_transition_at,
        updated_of=lambda project: project.updated_at,
    )
    return [summary_map[project.id] for project in sorted_projects]


@tool(
    "create_project",
    "Create a new project with a name, optional description, tags, and scope links",
    {
        "name": str,
        "description": str,
        "tags": str,
        "org_id": str,
        "portfolio_id": str,
        "program_id": str,
        "product_id": str,
    },
)
async def create_project(args: dict[str, Any]) -> dict[str, Any]:
    """Create a new project."""
    service = _get_project_service()

    tags = None
    if args.get("tags"):
        tags = [t.strip() for t in args["tags"].split(",") if t.strip()]

    try:
        project = await service.create_project(
            name=args["name"],
            description=args.get("description"),
            tags=tags,
            org_id=args.get("org_id"),
            portfolio_id=args.get("portfolio_id"),
            program_id=args.get("program_id"),
            product_id=args.get("product_id"),
        )
    except ValueError as exc:
        return {
            "content": [{"type": "text", "text": str(exc)}],
            "is_error": True,
        }

    return {
        "content": [
            {
                "type": "text",
                "text": f"Created project '{project.name}' with ID: {project.id}",
            }
        ]
    }


@tool(
    "list_projects",
    "List all projects, optionally filtered by status (active, archived, completed)",
    {"status": str},
)
async def list_projects(args: dict[str, Any]) -> dict[str, Any]:
    """List projects with optional status filter."""
    from pms.models import ProjectStatus

    status = None
    if args.get("status"):
        try:
            status = ProjectStatus(args["status"].lower())
        except ValueError:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Invalid status. Use: active, archived, or completed",
                    }
                ],
                "is_error": True,
            }

    summaries = await _sorted_project_summaries(status=status)
    items = [_project_summary_payload(summary) for summary in summaries]
    terminal_reason = None
    if items and all(item["status"] != "active" for item in items):
        terminal_reason = "all surfaced projects are already terminal"

    return _tool_json_content(
        {
            "items": items,
            "page": _page_payload(len(summaries), len(summaries), 0),
            "scope": {
                "kind": "mcp_project_list",
                "status_filter": status.value if status is not None else None,
            },
            "terminal_reason": terminal_reason,
        }
    )


@tool(
    "get_project",
    "Get details of a project by name or ID",
    {"identifier": str},
)
async def get_project(args: dict[str, Any]) -> dict[str, Any]:
    """Get project by name or ID."""
    service = _get_project_service()
    identifier = args["identifier"]

    project = await _resolve_project_identifier(identifier)
    if project is None:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Project '{identifier}' not found.",
                }
            ],
            "is_error": True,
        }

    summary = await service.get_project_summary(project.id)
    if summary is None:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Could not get project summary for '{identifier}'.",
                }
            ],
            "is_error": True,
        }

    focus_task = await _project_focus_task(project.id)
    if summary.terminal_reason is not None:
        focus_task = None

    return _tool_json_content(_project_summary_payload(summary, focus_task=focus_task))


# =============================================================================
# Goal Tools
# =============================================================================


async def _resolve_goal_identifier(identifier: str):
    """Resolve a goal by name first, then by id."""
    service = _get_goal_service()
    goal = await service.get_goal_by_name(identifier)
    if goal is None:
        goal = await service.get_goal(identifier)
    return goal


def _goal_summary_tool_links(
    goal_id: str, *, project_id: str | None = None
) -> dict[str, Any]:
    """Build machine-readable follow-up references for MCP goal summary surfaces."""
    links: dict[str, Any] = {
        "self": {"tool": "get_goal_summary", "args": {"identifier": goal_id}},
        "goal": {"tool": "get_goal", "args": {"identifier": goal_id}},
        "objectives": {"tool": "list_objectives", "args": {"goal_id": goal_id}},
        "plans": {"tool": "list_plans", "args": {"goal_id": goal_id}},
    }
    if project_id:
        links["project"] = {"tool": "get_project", "args": {"identifier": project_id}}
        links["tasks"] = {"tool": "list_tasks", "args": {"project": project_id}}
    return links


def _goal_detail_tool_links(
    goal_id: str, *, project_id: str | None = None
) -> dict[str, Any]:
    """Build machine-readable follow-up references for MCP goal detail/list surfaces."""
    links: dict[str, Any] = {
        "self": {"tool": "get_goal", "args": {"identifier": goal_id}},
        "summary": {"tool": "get_goal_summary", "args": {"identifier": goal_id}},
        "objectives": {"tool": "list_objectives", "args": {"goal_id": goal_id}},
        "plans": {"tool": "list_plans", "args": {"goal_id": goal_id}},
    }
    if project_id:
        links["project"] = {"tool": "get_project", "args": {"identifier": project_id}}
        links["tasks"] = {"tool": "list_tasks", "args": {"project": project_id}}
    return links


def _goal_tool_next_steps(
    goal_id: str,
    *,
    project_id: str | None = None,
    focus_task_id: str | None = None,
    terminal_reason: str | None = None,
) -> list[str]:
    """Build next-step guidance for MCP goal summary surfaces."""
    steps: list[str] = []
    if focus_task_id is not None:
        steps.append(f"Use get_task with identifier={focus_task_id}")
    else:
        steps.append(f"Use get_goal with identifier={goal_id}")
    if terminal_reason is not None:
        if project_id is not None:
            steps.append(f"Use list_tasks with project={project_id}")
        steps.append("Use list_goals with status=completed")
        return steps

    steps.append(f"Use list_objectives with goal_id={goal_id}")
    steps.append(f"Use list_plans with goal_id={goal_id}")
    if project_id is not None:
        steps.append(f"Use list_tasks with project={project_id}")
    return steps


def _goal_focus_task_payload(focus_task: Any | None) -> dict[str, Any] | None:
    """Serialize the selected focus task for MCP goal execution payloads."""
    if focus_task is None:
        return None
    return {
        "id": focus_task.id,
        "title": focus_task.title,
        "status": focus_task.status,
        "current_progress_percent": focus_task.current_progress_percent,
        "reason": focus_task.reason,
        "completion_criteria_count": focus_task.completion_criteria_count,
        "has_completion_criteria": focus_task.has_completion_criteria,
        "links": {"self": {"tool": "get_task", "args": {"identifier": focus_task.id}}},
    }


def _goal_effective_rollup_payload(rollup: Any | None) -> dict[str, Any] | None:
    """Serialize a goal effective rollup."""
    if rollup is None:
        return None
    return {
        "progress_percent": rollup.progress_percent,
        "status": rollup.status,
        "basis": rollup.basis,
        "reason": rollup.reason,
    }


def _goal_effective_hierarchy_payload(hierarchy: Any | None) -> dict[str, Any] | None:
    """Serialize a goal effective hierarchy."""
    if hierarchy is None:
        return None
    return {
        "objective_count": hierarchy.objective_count,
        "completed_objectives": hierarchy.completed_objectives,
        "key_result_count": hierarchy.key_result_count,
        "completed_key_results": hierarchy.completed_key_results,
        "average_progress": hierarchy.average_progress,
        "basis": hierarchy.basis,
        "reason": hierarchy.reason,
    }


def _goal_execution_payload(execution: Any | None) -> dict[str, Any] | None:
    """Serialize a goal execution summary."""
    if execution is None:
        return None
    return {
        "total_tasks": execution.total_tasks,
        "completed_tasks": execution.completed_tasks,
        "in_progress_tasks": execution.in_progress_tasks,
        "blocked_tasks": execution.blocked_tasks,
        "average_task_progress": execution.average_task_progress,
        "completion_percent": execution.completion_percent,
        "readiness_state": execution.readiness_state,
        "consistency_status": execution.consistency_status,
        "consistency_reason": execution.consistency_reason,
        "terminal_reason": execution.terminal_reason,
        "population_basis": execution.population_basis,
        "scoped_goal_count": execution.scoped_goal_count,
        "focus_task": _goal_focus_task_payload(execution.focus_task),
    }


def _goal_completion_context_payload(
    goal_id: str,
    *,
    project_id: str | None,
    terminal_reason: str | None,
) -> dict[str, Any] | None:
    """Build completion context for terminal MCP goal surfaces."""
    if terminal_reason is None:
        return None
    return {
        "summary": (
            "This goal is terminal. Inspect linked tasks, project state, "
            "or completed goals instead of treating it as active work."
        ),
        "next_steps": _goal_tool_next_steps(
            goal_id,
            project_id=project_id,
            terminal_reason=terminal_reason,
        ),
    }


def _goal_list_item_payload(
    goal: Any,
    *,
    effective_rollup: Any | None,
    execution: Any | None,
    last_activity_at: Any,
    last_transition_at: Any,
    project_name: str | None = None,
) -> dict[str, Any]:
    """Serialize one lifecycle-aware goal list item."""
    from pms.services.goal_service import goal_lifecycle_terminal_reason

    terminal_reason = (
        goal_lifecycle_terminal_reason(
            goal,
            effective_rollup=effective_rollup,
            execution=execution,
        )
        if effective_rollup is not None
        else None
    )
    next_steps = _goal_tool_next_steps(
        goal.id,
        project_id=goal.project_id,
        focus_task_id=(
            execution.focus_task.id
            if execution is not None and execution.focus_task is not None
            else None
        ),
        terminal_reason=terminal_reason,
    )
    payload = goal.to_dict()
    payload.update(
        {
            "project_name": project_name,
            "effective_rollup": _goal_effective_rollup_payload(effective_rollup),
            "last_activity_at": last_activity_at,
            "last_transition_at": last_transition_at,
            "terminal_reason": terminal_reason,
            "links": _goal_detail_tool_links(goal.id, project_id=goal.project_id),
            "next_steps": next_steps,
        }
    )
    return payload


def _goal_detail_payload(
    summary: Any,
    *,
    last_activity_at: Any,
    last_transition_at: Any,
    project_name: str | None = None,
) -> dict[str, Any]:
    """Serialize a lifecycle-aware goal detail payload."""
    from pms.services.goal_service import goal_lifecycle_terminal_reason

    terminal_reason = goal_lifecycle_terminal_reason(
        summary.goal,
        effective_rollup=summary.effective_rollup,
        execution=summary.execution,
    )
    completion_context = _goal_completion_context_payload(
        summary.goal.id,
        project_id=summary.goal.project_id,
        terminal_reason=terminal_reason,
    )
    next_steps = (
        list(completion_context["next_steps"])
        if completion_context is not None
        else _goal_tool_next_steps(
            summary.goal.id,
            project_id=summary.goal.project_id,
            focus_task_id=(
                summary.execution.focus_task.id
                if summary.execution is not None
                and summary.execution.focus_task is not None
                else None
            ),
            terminal_reason=terminal_reason,
        )
    )
    payload = summary.goal.to_dict()
    payload.update(
        {
            "project_name": project_name,
            "stats": {
                "objective_count": summary.objective_count,
                "completed_objectives": summary.completed_objectives,
                "key_result_count": summary.key_result_count,
                "completed_key_results": summary.completed_key_results,
                "average_progress": summary.average_progress,
            },
            "effective_hierarchy": _goal_effective_hierarchy_payload(
                summary.effective_hierarchy
            ),
            "effective_rollup": _goal_effective_rollup_payload(
                summary.effective_rollup
            ),
            "execution": _goal_execution_payload(summary.execution),
            "last_activity_at": last_activity_at,
            "last_transition_at": last_transition_at,
            "terminal_reason": terminal_reason,
            "completion_context": completion_context,
            "links": _goal_detail_tool_links(
                summary.goal.id,
                project_id=summary.goal.project_id,
            ),
            "next_steps": next_steps,
        }
    )
    return payload


def _goal_summary_payload(
    summary: Any,
    *,
    last_activity_at: Any,
    last_transition_at: Any,
) -> dict[str, Any]:
    """Serialize a lifecycle-aware goal summary payload."""
    from pms.services.goal_service import goal_lifecycle_terminal_reason

    terminal_reason = goal_lifecycle_terminal_reason(
        summary.goal,
        effective_rollup=summary.effective_rollup,
        execution=summary.execution,
    )
    completion_context = _goal_completion_context_payload(
        summary.goal.id,
        project_id=summary.goal.project_id,
        terminal_reason=terminal_reason,
    )
    next_steps = (
        list(completion_context["next_steps"])
        if completion_context is not None
        else _goal_tool_next_steps(
            summary.goal.id,
            project_id=summary.goal.project_id,
            focus_task_id=(
                summary.execution.focus_task.id
                if summary.execution is not None
                and summary.execution.focus_task is not None
                else None
            ),
            terminal_reason=terminal_reason,
        )
    )
    return {
        "goal": summary.goal.to_dict(),
        "stats": {
            "objective_count": summary.objective_count,
            "completed_objectives": summary.completed_objectives,
            "key_result_count": summary.key_result_count,
            "completed_key_results": summary.completed_key_results,
            "average_progress": summary.average_progress,
        },
        "effective_hierarchy": _goal_effective_hierarchy_payload(
            summary.effective_hierarchy
        ),
        "effective_rollup": _goal_effective_rollup_payload(summary.effective_rollup),
        "execution": _goal_execution_payload(summary.execution),
        "last_activity_at": last_activity_at,
        "last_transition_at": last_transition_at,
        "terminal_reason": terminal_reason,
        "completion_context": completion_context,
        "links": _goal_summary_tool_links(
            summary.goal.id,
            project_id=summary.goal.project_id,
        ),
        "next_steps": next_steps,
    }


async def _goal_project_name_map(goals: list[Any]) -> dict[str, str]:
    """Resolve project names for one goal collection."""
    project_service = _get_project_service()
    project_names: dict[str, str] = {}
    for project_id in dict.fromkeys(
        goal.project_id for goal in goals if getattr(goal, "project_id", None)
    ):
        if project_id is None:
            continue
        project = await project_service.get_project(project_id)
        if project is not None:
            project_names[project_id] = project.name
    return project_names


def _objective_effective_hierarchy_payload(
    hierarchy: Any | None,
) -> dict[str, Any] | None:
    """Serialize an objective effective hierarchy."""
    if hierarchy is None:
        return None
    return {
        "key_result_count": hierarchy.key_result_count,
        "completed_key_results": hierarchy.completed_key_results,
        "average_progress": hierarchy.average_progress,
        "basis": hierarchy.basis,
        "reason": hierarchy.reason,
    }


def _objective_tool_links(
    objective_id: str,
    *,
    goal_id: str,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Build machine-readable follow-up references for MCP objective surfaces."""
    links: dict[str, Any] = {
        "self": {"tool": "get_objective", "args": {"objective_id": objective_id}},
        "goal": {"tool": "get_goal", "args": {"identifier": goal_id}},
        "goal_summary": {"tool": "get_goal_summary", "args": {"identifier": goal_id}},
        "key_results": {
            "tool": "list_key_results",
            "args": {"objective_id": objective_id},
        },
    }
    if project_id:
        links["project"] = {"tool": "get_project", "args": {"identifier": project_id}}
    return links


def _objective_tool_next_steps(
    objective_id: str,
    *,
    goal_id: str,
    project_id: str | None = None,
    terminal_reason: str | None = None,
) -> list[str]:
    """Build next-step guidance for MCP objective surfaces."""
    steps = [
        f"Use get_objective with objective_id={objective_id}",
        f"Use list_key_results with objective_id={objective_id}",
        f"Use get_goal with identifier={goal_id}",
        f"Use get_goal_summary with identifier={goal_id}",
    ]
    if project_id is not None:
        steps.append(f"Use get_project with identifier={project_id}")
    if terminal_reason is not None:
        steps.append(f"Use list_objectives with goal_id={goal_id} status=completed")
        return steps
    steps.append(f"Use update_objective with objective_id={objective_id}")
    return steps


def _objective_completion_context_payload(
    objective_id: str,
    *,
    goal_id: str,
    project_id: str | None,
    terminal_reason: str | None,
) -> dict[str, Any] | None:
    """Build completion context for terminal MCP objective surfaces."""
    if terminal_reason is None:
        return None
    return {
        "summary": (
            "This objective is terminal. Inspect linked key results, the parent "
            "goal, or completed objectives instead of treating it as active work."
        ),
        "next_steps": _objective_tool_next_steps(
            objective_id,
            goal_id=goal_id,
            project_id=project_id,
            terminal_reason=terminal_reason,
        ),
    }


def _objective_list_item_payload(
    summary: Any,
    *,
    last_activity_at: Any,
    last_transition_at: Any,
    project_name: str | None = None,
) -> dict[str, Any]:
    """Serialize one lifecycle-aware objective list item."""
    from pms.services.goal_service import objective_lifecycle_terminal_reason

    objective = summary.objective
    terminal_reason = objective_lifecycle_terminal_reason(
        objective,
        effective_rollup=summary.effective_rollup,
    )
    payload = objective.to_dict()
    payload.update(
        {
            "project_id": getattr(objective, "project_id", None),
            "project_name": project_name,
            "effective_rollup": _goal_effective_rollup_payload(
                summary.effective_rollup
            ),
            "effective_hierarchy": _objective_effective_hierarchy_payload(
                summary.effective_hierarchy
            ),
            "last_activity_at": last_activity_at,
            "last_transition_at": last_transition_at,
            "terminal_reason": terminal_reason,
            "links": _objective_tool_links(
                objective.id,
                goal_id=objective.goal_id,
                project_id=getattr(objective, "project_id", None),
            ),
            "next_steps": _objective_tool_next_steps(
                objective.id,
                goal_id=objective.goal_id,
                project_id=getattr(objective, "project_id", None),
                terminal_reason=terminal_reason,
            ),
        }
    )
    return payload


def _objective_detail_payload(
    summary: Any,
    *,
    last_activity_at: Any,
    last_transition_at: Any,
    project_name: str | None = None,
) -> dict[str, Any]:
    """Serialize a lifecycle-aware objective detail payload."""
    from pms.services.goal_service import objective_lifecycle_terminal_reason

    objective = summary.objective
    terminal_reason = objective_lifecycle_terminal_reason(
        objective,
        effective_rollup=summary.effective_rollup,
    )
    completion_context = _objective_completion_context_payload(
        objective.id,
        goal_id=objective.goal_id,
        project_id=getattr(objective, "project_id", None),
        terminal_reason=terminal_reason,
    )
    next_steps = (
        list(completion_context["next_steps"])
        if completion_context is not None
        else _objective_tool_next_steps(
            objective.id,
            goal_id=objective.goal_id,
            project_id=getattr(objective, "project_id", None),
            terminal_reason=terminal_reason,
        )
    )
    payload = objective.to_dict()
    payload.update(
        {
            "project_id": getattr(objective, "project_id", None),
            "project_name": project_name,
            "stats": {
                "key_result_count": summary.key_result_count,
                "completed_key_results": summary.completed_key_results,
                "average_progress": summary.average_progress,
            },
            "effective_rollup": _goal_effective_rollup_payload(
                summary.effective_rollup
            ),
            "effective_hierarchy": _objective_effective_hierarchy_payload(
                summary.effective_hierarchy
            ),
            "last_activity_at": last_activity_at,
            "last_transition_at": last_transition_at,
            "terminal_reason": terminal_reason,
            "completion_context": completion_context,
            "links": _objective_tool_links(
                objective.id,
                goal_id=objective.goal_id,
                project_id=getattr(objective, "project_id", None),
            ),
            "next_steps": next_steps,
        }
    )
    return payload


async def _objective_goal_context_map(
    objectives: list[Any],
) -> dict[str, tuple[Any, str | None]]:
    """Resolve goal objects and project names for objective collections."""
    goal_service = _get_goal_service()
    project_service = _get_project_service()
    context: dict[str, tuple[Any, str | None]] = {}
    project_names: dict[str, str] = {}
    for objective in objectives:
        goal_id = getattr(objective, "goal_id", None)
        if not goal_id or goal_id in context:
            continue
        goal = await goal_service.get_goal(goal_id)
        if goal is None:
            continue
        project_name = None
        if goal.project_id:
            if goal.project_id not in project_names:
                project = await project_service.get_project(goal.project_id)
                if project is not None:
                    project_names[goal.project_id] = project.name
            project_name = project_names.get(goal.project_id)
        context[goal_id] = (goal, project_name)
    return context


@tool(
    "create_goal",
    "Create a new goal with horizon, optional description, and tags",
    {
        "name": str,
        "description": str,
        "horizon": str,
        "target_date": str,
        "owner": str,
        "product_id": str,
        "project_id": str,
        "tags": str,
        "progress_percent": int,
    },
)
async def create_goal(args: dict[str, Any]) -> dict[str, Any]:
    """Create a new goal."""
    from datetime import datetime

    from pms.models import GoalHorizon

    service = _get_goal_service()

    tags = None
    if args.get("tags"):
        tags = [t.strip() for t in args["tags"].split(",") if t.strip()]

    target_date = None
    if args.get("target_date"):
        try:
            target_date = datetime.fromisoformat(args["target_date"])
        except ValueError:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "Invalid target_date format (use ISO).",
                    }
                ],
                "is_error": True,
            }

    progress = args.get("progress_percent", 0)
    if progress is not None and (progress < 0 or progress > 100):
        return {
            "content": [
                {
                    "type": "text",
                    "text": "progress_percent must be 0-100.",
                }
            ],
            "is_error": True,
        }

    horizon_value = str(args.get("horizon", "short_term")).lower()
    try:
        horizon = GoalHorizon(horizon_value)
    except ValueError:
        return {
            "content": [
                {
                    "type": "text",
                    "text": "Invalid horizon. Use short_term, medium_term, long_term.",
                }
            ],
            "is_error": True,
        }

    goal = await service.create_goal(
        name=args["name"],
        description=args.get("description"),
        horizon=horizon,
        target_date=target_date,
        owner=args.get("owner"),
        product_id=args.get("product_id"),
        project_id=args.get("project_id"),
        tags=tags,
        progress_percent=progress,
    )

    return {
        "content": [
            {
                "type": "text",
                "text": f"Created goal '{goal.name}' with ID: {goal.id}",
            }
        ]
    }


@tool(
    "list_goals",
    "List goals, optionally filtered by status or horizon",
    {
        "status": str,
        "horizon": str,
        "product_id": str,
        "project_id": str,
        "limit": int,
        "offset": int,
    },
)
async def list_goals(args: dict[str, Any]) -> dict[str, Any]:
    """List goals."""
    from pms.models import GoalHorizon, GoalStatus

    service = _get_goal_service()

    status = None
    horizon = None
    if args.get("status"):
        try:
            status = GoalStatus(args["status"].lower())
        except ValueError:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "Invalid status. Use active, completed, on_hold, archived.",
                    }
                ],
                "is_error": True,
            }
    if args.get("horizon"):
        try:
            horizon = GoalHorizon(args["horizon"].lower())
        except ValueError:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "Invalid horizon. Use short_term, medium_term, long_term.",
                    }
                ],
                "is_error": True,
            }

    result = await service.list_goals(
        status=status,
        horizon=horizon,
        product_id=args.get("product_id"),
        project_id=args.get("project_id"),
        limit=int(args.get("limit", 100) or 100),
        offset=int(args.get("offset", 0) or 0),
    )
    goal_ids = [goal.id for goal in result.items]
    effective_rollups = await service.get_effective_rollups_for_goals(result.items)
    execution_summaries = await service.get_execution_summaries_for_goals(result.items)
    activity_map = await service.get_last_activity_map(goal_ids)
    transition_map = await service.get_last_transition_map(goal_ids)
    project_names = await _goal_project_name_map(result.items)
    items = [
        _goal_list_item_payload(
            goal,
            effective_rollup=effective_rollups.get(goal.id),
            execution=execution_summaries.get(goal.id),
            last_activity_at=activity_map.get(goal.id),
            last_transition_at=transition_map.get(goal.id),
            project_name=project_names.get(goal.project_id)
            if goal.project_id
            else None,
        )
        for goal in result.items
    ]
    terminal_reason = None
    if items and all(item["terminal_reason"] is not None for item in items):
        terminal_reason = "all surfaced goals are already terminal"

    return _tool_json_content(
        {
            "items": items,
            "page": _page_payload(result.total_count, result.limit, result.offset),
            "scope": {
                "kind": "mcp_goal_list",
                "status_filter": status.value if status is not None else None,
                "horizon_filter": horizon.value if horizon is not None else None,
                "product_id": args.get("product_id"),
                "project_id": args.get("project_id"),
            },
            "terminal_reason": terminal_reason,
        }
    )


@tool(
    "get_goal",
    "Get details of a goal by name or ID",
    {"identifier": str},
)
async def get_goal(args: dict[str, Any]) -> dict[str, Any]:
    """Get goal by name or ID."""
    service = _get_goal_service()
    identifier = args["identifier"]

    goal = await _resolve_goal_identifier(identifier)

    if goal is None:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Goal '{identifier}' not found.",
                }
            ],
            "is_error": True,
        }

    summary = await service.get_goal_summary(goal.id)
    if summary is None:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Could not get goal details for '{identifier}'.",
                }
            ],
            "is_error": True,
        }

    activity_map = await service.get_last_activity_map([goal.id])
    transition_map = await service.get_last_transition_map([goal.id])
    project_names = await _goal_project_name_map([goal])
    return _tool_json_content(
        _goal_detail_payload(
            summary,
            last_activity_at=activity_map.get(goal.id),
            last_transition_at=transition_map.get(goal.id),
            project_name=project_names.get(goal.project_id)
            if goal.project_id
            else None,
        )
    )


@tool(
    "get_goal_summary",
    "Get a rollup summary for a goal (objectives, key results, tasks)",
    {"identifier": str},
)
async def get_goal_summary(args: dict[str, Any]) -> dict[str, Any]:
    """Get goal summary with rollup stats."""
    service = _get_goal_service()
    identifier = args["identifier"]

    goal = await _resolve_goal_identifier(identifier)

    if goal is None:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Goal '{identifier}' not found.",
                }
            ],
            "is_error": True,
        }

    summary = await service.get_goal_summary(goal.id)
    if summary is None:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Could not get summary for goal '{identifier}'.",
                }
            ],
            "is_error": True,
        }

    activity_map = await service.get_last_activity_map([goal.id])
    transition_map = await service.get_last_transition_map([goal.id])
    return _tool_json_content(
        _goal_summary_payload(
            summary,
            last_activity_at=activity_map.get(goal.id),
            last_transition_at=transition_map.get(goal.id),
        )
    )


@tool(
    "update_goal",
    "Update goal fields like name, description, status, horizon, progress",
    {
        "goal_id": str,
        "name": str,
        "description": str,
        "status": str,
        "horizon": str,
        "target_date": str,
        "owner": str,
        "product_id": str,
        "project_id": str,
        "tags": str,
        "progress_percent": int,
    },
)
async def update_goal(args: dict[str, Any]) -> dict[str, Any]:
    """Update a goal."""
    from datetime import datetime

    from pms.models import GoalHorizon, GoalStatus

    service = _get_goal_service()

    status = GoalStatus(args["status"].lower()) if args.get("status") else None
    horizon = GoalHorizon(args["horizon"].lower()) if args.get("horizon") else None

    target_date = None
    if args.get("target_date"):
        try:
            target_date = datetime.fromisoformat(args["target_date"])
        except ValueError:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "Invalid target_date format (use ISO).",
                    }
                ],
                "is_error": True,
            }

    tags = None
    if args.get("tags"):
        tags = [t.strip() for t in args["tags"].split(",") if t.strip()]

    updated = await service.update_goal(
        goal_id=args["goal_id"],
        name=args.get("name"),
        description=args.get("description"),
        status=status,
        horizon=horizon,
        target_date=target_date,
        owner=args.get("owner"),
        product_id=args.get("product_id"),
        project_id=args.get("project_id"),
        tags=tags,
        progress_percent=args.get("progress_percent"),
    )

    if updated is None:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Goal '{args['goal_id']}' not found.",
                }
            ],
            "is_error": True,
        }

    return {
        "content": [
            {
                "type": "text",
                "text": f"Updated goal '{updated.name}'.",
            }
        ]
    }


@tool(
    "complete_goal",
    "Mark a goal as completed",
    {"goal_id": str},
)
async def complete_goal(args: dict[str, Any]) -> dict[str, Any]:
    """Complete a goal."""
    service = _get_goal_service()

    goal = await service.complete_goal(args["goal_id"])
    if goal is None:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Goal '{args['goal_id']}' not found.",
                }
            ],
            "is_error": True,
        }

    return {
        "content": [
            {
                "type": "text",
                "text": f"Completed goal '{goal.name}'.",
            }
        ]
    }


@tool(
    "archive_goal",
    "Archive a goal",
    {"goal_id": str},
)
async def archive_goal(args: dict[str, Any]) -> dict[str, Any]:
    """Archive a goal."""
    service = _get_goal_service()

    goal = await service.archive_goal(args["goal_id"])
    if goal is None:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Goal '{args['goal_id']}' not found.",
                }
            ],
            "is_error": True,
        }

    return {
        "content": [
            {
                "type": "text",
                "text": f"Archived goal '{goal.name}'.",
            }
        ]
    }


# =============================================================================
# Objective Tools
# =============================================================================


@tool(
    "create_objective",
    "Create a new objective under a goal",
    {
        "goal_id": str,
        "name": str,
        "description": str,
        "target_date": str,
        "owner": str,
        "tags": str,
        "progress_percent": int,
    },
)
async def create_objective(args: dict[str, Any]) -> dict[str, Any]:
    """Create a new objective."""
    from datetime import datetime

    service = _get_goal_service()

    tags = None
    if args.get("tags"):
        tags = [t.strip() for t in args["tags"].split(",") if t.strip()]

    target_date = None
    if args.get("target_date"):
        try:
            target_date = datetime.fromisoformat(args["target_date"])
        except ValueError:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "Invalid target_date format (use ISO).",
                    }
                ],
                "is_error": True,
            }

    progress = args.get("progress_percent", 0)
    if progress is not None and (progress < 0 or progress > 100):
        return {
            "content": [{"type": "text", "text": "progress_percent must be 0-100."}],
            "is_error": True,
        }

    objective = await service.create_objective(
        goal_id=args["goal_id"],
        name=args["name"],
        description=args.get("description"),
        target_date=target_date,
        owner=args.get("owner"),
        tags=tags,
        progress_percent=progress,
    )

    return {
        "content": [
            {
                "type": "text",
                "text": f"Created objective '{objective.name}' with ID: {objective.id}",
            }
        ]
    }


@tool(
    "list_objectives",
    "List objectives, optionally filtered by goal or status",
    {"goal_id": str, "status": str, "limit": int, "offset": int},
)
async def list_objectives(args: dict[str, Any]) -> dict[str, Any]:
    """List objectives."""
    from pms.models import GoalStatus

    service = _get_goal_service()

    status = None
    if args.get("status"):
        try:
            status = GoalStatus(args["status"].lower())
        except ValueError:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "Invalid status. Use active, completed, on_hold, archived.",
                    }
                ],
                "is_error": True,
            }

    result = await service.list_objectives(
        goal_id=args.get("goal_id"),
        status=status,
        limit=int(args.get("limit", 100) or 100),
        offset=int(args.get("offset", 0) or 0),
    )

    if not result.items:
        return _tool_json_content(
            {
                "items": [],
                "page": _page_payload(result.total_count, result.limit, result.offset),
                "scope": {
                    "kind": "mcp_objective_list",
                    "goal_id": args.get("goal_id"),
                    "status_filter": status.value if status is not None else None,
                },
                "terminal_reason": None,
            }
        )

    summaries = await service.get_objective_summaries_for_objectives(result.items)
    activity_map = await service.get_objective_last_activity_map(
        [objective.id for objective in result.items]
    )
    transition_map = await service.get_objective_last_transition_map(
        [objective.id for objective in result.items]
    )
    goal_context = await _objective_goal_context_map(result.items)
    items = []
    for objective in result.items:
        goal_entry = goal_context.get(objective.goal_id)
        if goal_entry is not None:
            goal, project_name = goal_entry
            setattr(objective, "project_id", goal.project_id)
        else:
            project_name = None
        items.append(
            _objective_list_item_payload(
                summaries[objective.id],
                last_activity_at=activity_map.get(objective.id),
                last_transition_at=transition_map.get(objective.id),
                project_name=project_name,
            )
        )

    terminal_reason = None
    if items and all(item["terminal_reason"] is not None for item in items):
        terminal_reason = "all surfaced objectives are already terminal"

    return _tool_json_content(
        {
            "items": items,
            "page": _page_payload(result.total_count, result.limit, result.offset),
            "scope": {
                "kind": "mcp_objective_list",
                "goal_id": args.get("goal_id"),
                "status_filter": status.value if status is not None else None,
            },
            "terminal_reason": terminal_reason,
        }
    )


@tool(
    "get_objective",
    "Get details of an objective by ID",
    {"objective_id": str},
)
async def get_objective(args: dict[str, Any]) -> dict[str, Any]:
    """Get objective by ID."""
    service = _get_goal_service()
    objective = await service.get_objective(args["objective_id"])

    if objective is None:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Objective '{args['objective_id']}' not found.",
                }
            ],
            "is_error": True,
        }

    summary = await service.get_objective_summary(objective.id)
    if summary is None:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Could not get objective details for '{args['objective_id']}'.",
                }
            ],
            "is_error": True,
        }

    goal_context = await _objective_goal_context_map([objective])
    project_name = None
    goal_entry = goal_context.get(objective.goal_id)
    if goal_entry is not None:
        goal, project_name = goal_entry
        setattr(objective, "project_id", goal.project_id)
        setattr(summary.objective, "project_id", goal.project_id)
    activity_map = await service.get_objective_last_activity_map([objective.id])
    transition_map = await service.get_objective_last_transition_map([objective.id])
    return _tool_json_content(
        _objective_detail_payload(
            summary,
            last_activity_at=activity_map.get(objective.id),
            last_transition_at=transition_map.get(objective.id),
            project_name=project_name,
        )
    )


@tool(
    "update_objective",
    "Update objective fields like name, description, status, progress",
    {
        "objective_id": str,
        "name": str,
        "description": str,
        "status": str,
        "target_date": str,
        "owner": str,
        "tags": str,
        "progress_percent": int,
    },
)
async def update_objective(args: dict[str, Any]) -> dict[str, Any]:
    """Update an objective."""
    from datetime import datetime

    from pms.models import GoalStatus

    service = _get_goal_service()

    status = GoalStatus(args["status"].lower()) if args.get("status") else None

    target_date = None
    if args.get("target_date"):
        try:
            target_date = datetime.fromisoformat(args["target_date"])
        except ValueError:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "Invalid target_date format (use ISO).",
                    }
                ],
                "is_error": True,
            }

    tags = None
    if args.get("tags"):
        tags = [t.strip() for t in args["tags"].split(",") if t.strip()]

    updated = await service.update_objective(
        objective_id=args["objective_id"],
        name=args.get("name"),
        description=args.get("description"),
        status=status,
        target_date=target_date,
        owner=args.get("owner"),
        tags=tags,
        progress_percent=args.get("progress_percent"),
    )

    if updated is None:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Objective '{args['objective_id']}' not found.",
                }
            ],
            "is_error": True,
        }

    return {
        "content": [
            {
                "type": "text",
                "text": f"Updated objective '{updated.name}'.",
            }
        ]
    }


@tool(
    "complete_objective",
    "Mark an objective as completed",
    {"objective_id": str},
)
async def complete_objective(args: dict[str, Any]) -> dict[str, Any]:
    """Complete an objective."""
    service = _get_goal_service()

    objective = await service.complete_objective(args["objective_id"])
    if objective is None:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Objective '{args['objective_id']}' not found.",
                }
            ],
            "is_error": True,
        }

    return {
        "content": [
            {
                "type": "text",
                "text": f"Completed objective '{objective.name}'.",
            }
        ]
    }


@tool(
    "archive_objective",
    "Archive an objective",
    {"objective_id": str},
)
async def archive_objective(args: dict[str, Any]) -> dict[str, Any]:
    """Archive an objective."""
    service = _get_goal_service()

    objective = await service.archive_objective(args["objective_id"])
    if objective is None:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Objective '{args['objective_id']}' not found.",
                }
            ],
            "is_error": True,
        }

    return {
        "content": [
            {
                "type": "text",
                "text": f"Archived objective '{objective.name}'.",
            }
        ]
    }


def _key_result_effective_rollup_payload(key_result: Any) -> dict[str, Any]:
    """Serialize the lifecycle rollup for one key result leaf."""
    return {
        "progress_percent": key_result.progress_percent,
        "status": key_result.status.value,
        "basis": "stored_key_result",
        "reason": None,
    }


def _key_result_tool_links(
    key_result_id: str,
    *,
    objective_id: str,
    goal_id: str | None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Build machine-readable follow-up references for MCP key-result surfaces."""
    links: dict[str, Any] = {
        "self": {"tool": "get_key_result", "args": {"key_result_id": key_result_id}},
        "objective": {"tool": "get_objective", "args": {"objective_id": objective_id}},
        "key_results": {
            "tool": "list_key_results",
            "args": {"objective_id": objective_id},
        },
    }
    if goal_id:
        links["goal"] = {"tool": "get_goal", "args": {"identifier": goal_id}}
        links["goal_summary"] = {
            "tool": "get_goal_summary",
            "args": {"identifier": goal_id},
        }
    if project_id:
        links["project"] = {"tool": "get_project", "args": {"identifier": project_id}}
    return links


def _key_result_tool_next_steps(
    key_result_id: str,
    *,
    objective_id: str,
    goal_id: str | None,
    project_id: str | None = None,
    terminal_reason: str | None = None,
) -> list[str]:
    """Build next-step guidance for MCP key-result surfaces."""
    steps = [
        f"Use get_key_result with key_result_id={key_result_id}",
        f"Use get_objective with objective_id={objective_id}",
        f"Use list_key_results with objective_id={objective_id}",
    ]
    if goal_id is not None:
        steps.append(f"Use get_goal with identifier={goal_id}")
        steps.append(f"Use get_goal_summary with identifier={goal_id}")
    if project_id is not None:
        steps.append(f"Use get_project with identifier={project_id}")
    if terminal_reason is not None:
        steps.append(
            f"Use list_key_results with objective_id={objective_id} status=completed"
        )
        return steps
    steps.append(f"Use update_key_result with key_result_id={key_result_id}")
    return steps


def _key_result_completion_context_payload(
    key_result_id: str,
    *,
    objective_id: str,
    goal_id: str | None,
    project_id: str | None,
    terminal_reason: str | None,
) -> dict[str, Any] | None:
    """Build completion context for terminal MCP key-result surfaces."""
    if terminal_reason is None:
        return None
    return {
        "summary": (
            "This key result is terminal. Inspect the parent objective, goal, "
            "or completed key results instead of treating it as active work."
        ),
        "next_steps": _key_result_tool_next_steps(
            key_result_id,
            objective_id=objective_id,
            goal_id=goal_id,
            project_id=project_id,
            terminal_reason=terminal_reason,
        ),
    }


def _key_result_list_item_payload(
    key_result: Any,
    *,
    goal_id: str | None,
    goal_name: str | None,
    project_id: str | None,
    project_name: str | None,
    last_activity_at: Any,
    last_transition_at: Any,
) -> dict[str, Any]:
    """Serialize one lifecycle-aware key-result list item."""
    from pms.services.goal_service import key_result_lifecycle_terminal_reason

    terminal_reason = key_result_lifecycle_terminal_reason(key_result)
    payload = key_result.to_dict()
    payload.update(
        {
            "goal_id": goal_id,
            "goal_name": goal_name,
            "project_id": project_id,
            "project_name": project_name,
            "effective_rollup": _key_result_effective_rollup_payload(key_result),
            "last_activity_at": last_activity_at,
            "last_transition_at": last_transition_at,
            "terminal_reason": terminal_reason,
            "links": _key_result_tool_links(
                key_result.id,
                objective_id=key_result.objective_id,
                goal_id=goal_id,
                project_id=project_id,
            ),
            "next_steps": _key_result_tool_next_steps(
                key_result.id,
                objective_id=key_result.objective_id,
                goal_id=goal_id,
                project_id=project_id,
                terminal_reason=terminal_reason,
            ),
        }
    )
    return payload


def _key_result_detail_payload(
    key_result: Any,
    *,
    goal_id: str | None,
    goal_name: str | None,
    project_id: str | None,
    project_name: str | None,
    last_activity_at: Any,
    last_transition_at: Any,
) -> dict[str, Any]:
    """Serialize a lifecycle-aware key-result detail payload."""
    from pms.services.goal_service import key_result_lifecycle_terminal_reason

    terminal_reason = key_result_lifecycle_terminal_reason(key_result)
    completion_context = _key_result_completion_context_payload(
        key_result.id,
        objective_id=key_result.objective_id,
        goal_id=goal_id,
        project_id=project_id,
        terminal_reason=terminal_reason,
    )
    next_steps = (
        list(completion_context["next_steps"])
        if completion_context is not None
        else _key_result_tool_next_steps(
            key_result.id,
            objective_id=key_result.objective_id,
            goal_id=goal_id,
            project_id=project_id,
            terminal_reason=terminal_reason,
        )
    )
    payload = _key_result_list_item_payload(
        key_result,
        goal_id=goal_id,
        goal_name=goal_name,
        project_id=project_id,
        project_name=project_name,
        last_activity_at=last_activity_at,
        last_transition_at=last_transition_at,
    )
    payload["completion_context"] = completion_context
    payload["next_steps"] = next_steps
    return payload


async def _key_result_parent_context_map(
    key_results: list[Any],
) -> dict[str, dict[str, Any]]:
    """Resolve objective, goal, and project context for key-result collections."""
    goal_service = _get_goal_service()
    project_service = _get_project_service()
    objective_cache: dict[str, Any] = {}
    goal_cache: dict[str, Any] = {}
    project_name_cache: dict[str, str] = {}
    context: dict[str, dict[str, Any]] = {}
    for key_result in key_results:
        objective_id = getattr(key_result, "objective_id", None)
        if not objective_id:
            continue
        objective = objective_cache.get(objective_id)
        if objective is None:
            objective = await goal_service.get_objective(objective_id)
            if objective is None:
                continue
            objective_cache[objective_id] = objective
        goal = None
        goal_name = None
        project_id = None
        project_name = None
        goal_id = getattr(objective, "goal_id", None)
        if goal_id:
            goal = goal_cache.get(goal_id)
            if goal is None:
                goal = await goal_service.get_goal(goal_id)
                if goal is not None:
                    goal_cache[goal_id] = goal
            if goal is not None:
                goal_name = goal.name
                project_id = goal.project_id
                if project_id:
                    if project_id not in project_name_cache:
                        project = await project_service.get_project(project_id)
                        if project is not None:
                            project_name_cache[project_id] = project.name
                    project_name = project_name_cache.get(project_id)
        context[key_result.id] = {
            "objective": objective,
            "goal": goal,
            "goal_id": goal_id,
            "goal_name": goal_name,
            "project_id": project_id,
            "project_name": project_name,
        }
    return context


# =============================================================================
# Key Result Tools
# =============================================================================


@tool(
    "create_key_result",
    "Create a new key result under an objective",
    {
        "objective_id": str,
        "name": str,
        "description": str,
        "current_value": float,
        "target_value": float,
        "unit": str,
        "owner": str,
        "tags": str,
        "progress_percent": int,
    },
)
async def create_key_result(args: dict[str, Any]) -> dict[str, Any]:
    """Create a new key result."""
    service = _get_goal_service()

    tags = None
    if args.get("tags"):
        tags = [t.strip() for t in args["tags"].split(",") if t.strip()]

    key_result = await service.create_key_result(
        objective_id=args["objective_id"],
        name=args["name"],
        description=args.get("description"),
        current_value=args.get("current_value"),
        target_value=args.get("target_value"),
        unit=args.get("unit"),
        owner=args.get("owner"),
        tags=tags,
        progress_percent=args.get("progress_percent"),
    )

    return {
        "content": [
            {
                "type": "text",
                "text": f"Created key result '{key_result.name}' with ID: {key_result.id}",
            }
        ]
    }


@tool(
    "list_key_results",
    "List key results, optionally filtered by objective or status",
    {"objective_id": str, "status": str, "limit": int, "offset": int},
)
async def list_key_results(args: dict[str, Any]) -> dict[str, Any]:
    """List key results."""
    from pms.models import GoalStatus

    service = _get_goal_service()

    status = None
    if args.get("status"):
        try:
            status = GoalStatus(args["status"].lower())
        except ValueError:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "Invalid status. Use active, completed, on_hold, archived.",
                    }
                ],
                "is_error": True,
            }

    result = await service.list_key_results(
        objective_id=args.get("objective_id"),
        status=status,
        limit=int(args.get("limit", 100) or 100),
        offset=int(args.get("offset", 0) or 0),
    )

    if not result.items:
        return _tool_json_content(
            {
                "items": [],
                "page": _page_payload(result.total_count, result.limit, result.offset),
                "scope": {
                    "kind": "mcp_key_result_list",
                    "objective_id": args.get("objective_id"),
                    "status_filter": status.value if status is not None else None,
                },
                "terminal_reason": None,
            }
        )

    context_map = await _key_result_parent_context_map(result.items)
    activity_map = await service.get_key_result_last_activity_map(
        [key_result.id for key_result in result.items]
    )
    transition_map = await service.get_key_result_last_transition_map(
        [key_result.id for key_result in result.items]
    )
    items = []
    for key_result in result.items:
        context = context_map.get(key_result.id, {})
        items.append(
            _key_result_list_item_payload(
                key_result,
                goal_id=context.get("goal_id"),
                goal_name=context.get("goal_name"),
                project_id=context.get("project_id"),
                project_name=context.get("project_name"),
                last_activity_at=activity_map.get(key_result.id),
                last_transition_at=transition_map.get(key_result.id),
            )
        )

    terminal_reason = None
    if items and all(item["terminal_reason"] is not None for item in items):
        terminal_reason = "all surfaced key results are already terminal"

    return _tool_json_content(
        {
            "items": items,
            "page": _page_payload(result.total_count, result.limit, result.offset),
            "scope": {
                "kind": "mcp_key_result_list",
                "objective_id": args.get("objective_id"),
                "status_filter": status.value if status is not None else None,
            },
            "terminal_reason": terminal_reason,
        }
    )


@tool(
    "get_key_result",
    "Get details of a key result by ID",
    {"key_result_id": str},
)
async def get_key_result(args: dict[str, Any]) -> dict[str, Any]:
    """Get key result by ID."""
    service = _get_goal_service()
    key_result = await service.get_key_result(args["key_result_id"])

    if key_result is None:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Key result '{args['key_result_id']}' not found.",
                }
            ],
            "is_error": True,
        }
    context_map = await _key_result_parent_context_map([key_result])
    context = context_map.get(key_result.id, {})
    activity_map = await service.get_key_result_last_activity_map([key_result.id])
    transition_map = await service.get_key_result_last_transition_map([key_result.id])
    return _tool_json_content(
        _key_result_detail_payload(
            key_result,
            goal_id=context.get("goal_id"),
            goal_name=context.get("goal_name"),
            project_id=context.get("project_id"),
            project_name=context.get("project_name"),
            last_activity_at=activity_map.get(key_result.id),
            last_transition_at=transition_map.get(key_result.id),
        )
    )


@tool(
    "update_key_result",
    "Update key result fields like name, status, progress, values",
    {
        "key_result_id": str,
        "name": str,
        "description": str,
        "status": str,
        "current_value": float,
        "target_value": float,
        "unit": str,
        "owner": str,
        "tags": str,
        "progress_percent": int,
    },
)
async def update_key_result(args: dict[str, Any]) -> dict[str, Any]:
    """Update a key result."""
    from pms.models import GoalStatus

    service = _get_goal_service()

    status = GoalStatus(args["status"].lower()) if args.get("status") else None

    tags = None
    if args.get("tags"):
        tags = [t.strip() for t in args["tags"].split(",") if t.strip()]

    updated = await service.update_key_result(
        key_result_id=args["key_result_id"],
        name=args.get("name"),
        description=args.get("description"),
        status=status,
        current_value=args.get("current_value"),
        target_value=args.get("target_value"),
        unit=args.get("unit"),
        owner=args.get("owner"),
        tags=tags,
        progress_percent=args.get("progress_percent"),
    )

    if updated is None:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Key result '{args['key_result_id']}' not found.",
                }
            ],
            "is_error": True,
        }

    return {
        "content": [
            {
                "type": "text",
                "text": f"Updated key result '{updated.name}'.",
            }
        ]
    }


@tool(
    "complete_key_result",
    "Mark a key result as completed",
    {"key_result_id": str},
)
async def complete_key_result(args: dict[str, Any]) -> dict[str, Any]:
    """Complete a key result."""
    service = _get_goal_service()

    key_result = await service.complete_key_result(args["key_result_id"])
    if key_result is None:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Key result '{args['key_result_id']}' not found.",
                }
            ],
            "is_error": True,
        }

    return {
        "content": [
            {
                "type": "text",
                "text": f"Completed key result '{key_result.name}'.",
            }
        ]
    }


@tool(
    "archive_key_result",
    "Archive a key result",
    {"key_result_id": str},
)
async def archive_key_result(args: dict[str, Any]) -> dict[str, Any]:
    """Archive a key result."""
    service = _get_goal_service()

    key_result = await service.archive_key_result(args["key_result_id"])
    if key_result is None:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Key result '{args['key_result_id']}' not found.",
                }
            ],
            "is_error": True,
        }

    return {
        "content": [
            {
                "type": "text",
                "text": f"Archived key result '{key_result.name}'.",
            }
        ]
    }


@tool(
    "get_project_summary",
    "Get a summary of a project including stats and health score",
    {"identifier": str},
)
async def get_project_summary(args: dict[str, Any]) -> dict[str, Any]:
    """Get project summary with stats."""
    service = _get_project_service()
    identifier = args["identifier"]

    project = await _resolve_project_identifier(identifier)
    if project is None:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Project '{identifier}' not found.",
                }
            ],
            "is_error": True,
        }

    summary = await service.get_project_summary(project.id)
    if summary is None:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Could not get summary for project '{identifier}'.",
                }
            ],
            "is_error": True,
        }

    focus_task = await _project_focus_task(project.id)
    if summary.terminal_reason is not None:
        focus_task = None

    return _tool_json_content(
        {
            "project": _project_summary_payload(summary, focus_task=focus_task),
            "stats": summary.stats.to_dict() if summary.stats is not None else None,
            "health_score": summary.health_score,
            "recent_activity_count": summary.recent_activity_count,
        }
    )


@tool(
    "archive_project",
    "Archive a project by name or ID",
    {"identifier": str},
)
async def archive_project(args: dict[str, Any]) -> dict[str, Any]:
    """Archive a project."""
    service = _get_project_service()
    identifier = args["identifier"]

    # Find project
    project = await service.get_project_by_name(identifier)
    if project is None:
        project = await service.get_project(identifier)

    if project is None:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Project '{identifier}' not found.",
                }
            ],
            "is_error": True,
        }

    archived = await service.archive_project(project.id)
    if archived is None:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Failed to archive project '{identifier}'.",
                }
            ],
            "is_error": True,
        }

    return {
        "content": [
            {
                "type": "text",
                "text": f"Archived project '{archived.name}'.",
            }
        ]
    }


@tool(
    "update_project",
    "Update project fields (name, description, tags, scope links, product_id)",
    {
        "identifier": str,
        "name": str,
        "description": str,
        "tags": str,
        "org_id": str,
        "portfolio_id": str,
        "program_id": str,
        "product_id": str,
    },
)
async def update_project(args: dict[str, Any]) -> dict[str, Any]:
    """Update a project."""
    service = _get_project_service()
    identifier = args["identifier"]

    project = await service.get_project_by_name(identifier)
    if project is None:
        project = await service.get_project(identifier)

    if project is None:
        return {
            "content": [{"type": "text", "text": f"Project '{identifier}' not found."}],
            "is_error": True,
        }

    tags = None
    if args.get("tags"):
        tags = [t.strip() for t in args["tags"].split(",") if t.strip()]

    try:
        updated = await service.update_project(
            project_id=project.id,
            name=args.get("name"),
            description=args.get("description"),
            tags=tags,
            org_id=args.get("org_id"),
            portfolio_id=args.get("portfolio_id"),
            program_id=args.get("program_id"),
            product_id=args.get("product_id"),
        )
    except ValueError as exc:
        return {
            "content": [{"type": "text", "text": str(exc)}],
            "is_error": True,
        }

    if updated is None:
        return {
            "content": [{"type": "text", "text": "Update failed."}],
            "is_error": True,
        }

    return {"content": [{"type": "text", "text": f"Updated project '{updated.name}'."}]}


@tool(
    "delete_project",
    "Delete a project and all its tasks",
    {"identifier": str},
)
async def delete_project(args: dict[str, Any]) -> dict[str, Any]:
    """Delete a project."""
    service = _get_project_service()
    identifier = args["identifier"]

    project = await service.get_project_by_name(identifier)
    if project is None:
        project = await service.get_project(identifier)

    if project is None:
        return {
            "content": [{"type": "text", "text": f"Project '{identifier}' not found."}],
            "is_error": True,
        }

    # Archive instead of hard delete for safety
    archived = await service.archive_project(project.id)

    if archived is None:
        return {
            "content": [{"type": "text", "text": "Delete failed."}],
            "is_error": True,
        }

    return {
        "content": [
            {"type": "text", "text": f"Deleted (archived) project '{archived.name}'."}
        ]
    }


@tool(
    "get_dashboard",
    "Get an overview dashboard of all projects and tasks",
    {},
)
async def get_dashboard(args: dict[str, Any]) -> dict[str, Any]:
    """Get dashboard overview."""
    from pms.models import ProjectStatus
    from pms.services.rollup_utils import sort_items_by_bubbled_recency

    service = _get_project_service()
    dashboard = await service.get_dashboard()
    projects = [
        project
        for project in await service.list_all_projects()
        if project.status != ProjectStatus.ARCHIVED
    ]
    summary_map = await service.build_project_summary_map(projects)
    sorted_projects = sort_items_by_bubbled_recency(
        projects,
        activity_of=lambda project: summary_map[project.id].last_activity_at,
        transition_of=lambda project: summary_map[project.id].last_transition_at,
        updated_of=lambda project: project.updated_at,
    )
    sorted_summaries = [summary_map[project.id] for project in sorted_projects]
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

    payload = {
        "scope": {
            "kind": "mcp_project_dashboard",
            "population": "all_non_archived_retained",
            "active_visible_projects": len(active_summaries),
            "recently_completed_projects": len(completed_summaries[:5]),
        },
        "totals": {
            "total_projects": dashboard.total_projects,
            "total_tasks": dashboard.total_tasks,
            "completed_tasks": dashboard.completed_tasks,
            "blocked_tasks": dashboard.blocked_tasks,
            "overdue_tasks": dashboard.overdue_tasks,
        },
        "active_projects": [
            _project_summary_payload(summary) for summary in active_summaries
        ],
        "recently_completed_projects": [
            _project_summary_payload(summary) for summary in completed_summaries[:5]
        ],
        "freshest_visible_activity": (
            _project_summary_payload(max(visible_summaries, key=_activity_key))
            if visible_summaries
            else None
        ),
        "freshest_visible_transition": (
            _project_summary_payload(max(visible_summaries, key=_transition_key))
            if visible_summaries
            else None
        ),
        "terminal_reason": (
            "all surfaced projects are already terminal"
            if not active_summaries and completed_summaries
            else None
        ),
    }

    return _tool_json_content(payload)


@tool(
    "get_work_snapshot",
    "Get a unified work snapshot for an organization, portfolio, program, or project",
    {"scope_type": str, "scope_id": str, "task_limit": int, "test_limit": int},
)
async def get_work_snapshot(args: dict[str, Any]) -> dict[str, Any]:
    """Get a work snapshot."""
    service = _get_work_snapshot_service()
    scope_type = str(args.get("scope_type", "")).lower()

    match scope_type:
        case "organization" | "portfolio" | "program" | "project":
            pass
        case _:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Invalid scope_type. Use organization, portfolio, program, or project."
                        ),
                    }
                ],
                "is_error": True,
            }

    task_limit = int(args.get("task_limit", 5))
    test_limit = int(args.get("test_limit", 5))
    snapshot = await service.get_snapshot(
        scope_type=scope_type,
        scope_id=args["scope_id"],
        task_limit=task_limit,
        test_limit=test_limit,
    )
    if snapshot is None:
        return {
            "content": [{"type": "text", "text": "Work snapshot not found."}],
            "is_error": True,
        }

    totals = snapshot.totals
    digest = snapshot.digest
    evidence = snapshot.evidence
    retention = snapshot.retention or {}

    scope_name = snapshot.scope_name or "unknown"
    reviewed = (
        snapshot.last_reviewed_at.isoformat() if snapshot.last_reviewed_at else "never"
    )
    lines = [
        f"Work Snapshot ({snapshot.scope_type})",
        f"Scope: {scope_name} (ID: {snapshot.scope_id})",
        f"Last reviewed: {reviewed}",
        (
            "Totals: "
            f"projects {totals.total_projects or 0} | "
            f"goals {totals.total_goals or 0} | "
            f"objectives {totals.total_objectives or 0} | "
            f"tasks {totals.total_tasks or 0} | "
            f"blocked {totals.blocked_tasks or 0}"
        ),
        (
            "Digest: "
            f"tasks +{digest.tasks_created}, completed {digest.tasks_completed}, "
            f"updated {digest.tasks_updated} | plans +{digest.plans_created}, "
            f"updated {digest.plans_updated} | runs {digest.test_runs} "
            f"(failed {digest.failed_test_runs}) | evidence +{digest.evidence_added}"
        ),
        f"Evidence: total {evidence.total_count}, new {evidence.new_count}",
    ]

    if retention:
        lines.append(
            "Retention: "
            f"runs {retention.get('total_runs', 0)} | "
            f"bytes {retention.get('total_bytes', 0)}"
        )

    if snapshot.recent_tasks:
        lines.append("Recent Tasks:")
        for item in snapshot.recent_tasks:
            lines.append(
                f"- {item.title} ({item.status}) "
                f"project {item.project_id} updated {item.updated_at.isoformat()}"
            )

    if snapshot.recent_test_runs:
        lines.append("Recent Test Runs:")
        for item in snapshot.recent_test_runs:
            status = "pass" if item.success else "fail"
            command = item.command or "test run"
            lines.append(
                f"- {command} ({status}) "
                f"project {item.project_id or 'none'} "
                f"finished {item.finished_at.isoformat()}"
            )

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "mark_work_snapshot_reviewed",
    "Record a review checkpoint for a work snapshot",
    {
        "scope_type": str,
        "scope_id": str,
        "reviewed_by": str,
        "note": str,
        "metadata": str,
    },
)
async def mark_work_snapshot_reviewed(args: dict[str, Any]) -> dict[str, Any]:
    """Mark a work snapshot as reviewed."""
    service = _get_work_snapshot_service()
    scope_type = str(args.get("scope_type", "")).lower()

    match scope_type:
        case "organization" | "portfolio" | "program" | "project":
            pass
        case _:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Invalid scope_type. Use organization, portfolio, program, or project."
                        ),
                    }
                ],
                "is_error": True,
            }

    metadata: dict[str, Any] = {}
    if args.get("metadata"):
        import json

        try:
            metadata = json.loads(str(args["metadata"]))
            if not isinstance(metadata, dict):
                raise ValueError("metadata must be a JSON object")
        except ValueError:
            return {
                "content": [{"type": "text", "text": "metadata must be valid JSON."}],
                "is_error": True,
            }

    review = await service.mark_reviewed(
        scope_type=scope_type,
        scope_id=args["scope_id"],
        reviewed_by=args.get("reviewed_by"),
        note=args.get("note"),
        metadata=metadata or None,
    )
    if review is None:
        return {
            "content": [{"type": "text", "text": "Work snapshot not found."}],
            "is_error": True,
        }

    lines = [
        "Work Snapshot Reviewed",
        f"ID: {review.id}",
        f"Scope: {review.scope_type} {review.scope_id}",
        f"Reviewed at: {review.reviewed_at.isoformat()}",
    ]
    if review.reviewed_by:
        lines.append(f"Reviewed by: {review.reviewed_by}")
    if review.note:
        lines.append(f"Note: {review.note}")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "get_work_daily",
    "Get a daily review summary with snapshot and queues",
    {
        "scope_type": str,
        "scope_id": str,
        "task_limit": int,
        "test_limit": int,
        "queue_limit": int,
        "stale_days": int,
        "at_risk_days": int,
    },
)
async def get_work_daily(args: dict[str, Any]) -> dict[str, Any]:
    """Get a daily review summary."""
    import json

    snapshot_service = _get_work_snapshot_service()
    queue_service = _get_queue_service()

    scope_type = args.get("scope_type")
    scope_id = args.get("scope_id")
    if not scope_type or not scope_id:
        return {
            "content": [
                {
                    "type": "text",
                    "text": "scope_type and scope_id are required.",
                }
            ],
            "is_error": True,
        }

    task_limit = int(args.get("task_limit", 5))
    test_limit = int(args.get("test_limit", 5))
    queue_limit = int(args.get("queue_limit", 3))
    stale_days = int(args.get("stale_days", 14))
    at_risk_days = int(args.get("at_risk_days", 7))

    snapshot = await snapshot_service.get_snapshot(
        scope_type=str(scope_type),
        scope_id=str(scope_id),
        task_limit=task_limit,
        test_limit=test_limit,
    )
    if snapshot is None:
        return {
            "content": [{"type": "text", "text": "Work daily not found."}],
            "is_error": True,
        }

    project_filter = str(scope_id) if scope_type == "project" else None
    queues = await queue_service.list_presets(
        project_id=project_filter,
        limit=queue_limit,
        stale_days=stale_days,
        at_risk_days=at_risk_days,
    )
    queue_map = {summary.name: summary for summary in queues}
    ready_summary = queue_map.get("ready")
    blocked_summary = queue_map.get("blocked")

    queue_payload = []
    for summary in queues:
        queue_payload.append(
            {
                "name": summary.name,
                "description": summary.description,
                "total_count": summary.total_count,
                "items": [task.to_dict() for task in summary.items],
            }
        )

    payload = {
        "snapshot": snapshot.to_dict(),
        "queues": queue_payload,
        "next_actions": [
            task.to_dict()
            for task in (ready_summary.items if ready_summary else [])[:queue_limit]
        ],
        "blockers": [
            task.to_dict()
            for task in (blocked_summary.items if blocked_summary else [])[:queue_limit]
        ],
        "params": {
            "scope_type": scope_type,
            "scope_id": scope_id,
            "task_limit": task_limit,
            "test_limit": test_limit,
            "queue_limit": queue_limit,
            "stale_days": stale_days,
            "at_risk_days": at_risk_days,
        },
    }
    return {"content": [{"type": "text", "text": json.dumps(payload, default=str)}]}


# =============================================================================
# Plan Tools
# =============================================================================


@tool(
    "create_plan",
    "Create a plan artifact with JSON/YAML content and optional links",
    {
        "name": str,
        "description": str,
        "status": str,
        "format": str,
        "content": str,
        "product_id": str,
        "project_id": str,
        "goal_id": str,
        "objective_id": str,
        "task_ids": str,
        "tags": str,
    },
)
async def create_plan(args: dict[str, Any]) -> dict[str, Any]:
    """Create a new plan."""
    from pms.models import PlanFormat, PlanStatus

    service = _get_plan_service()

    status_value = str(args.get("status", "draft")).lower()
    format_value = str(args.get("format", "json")).lower()

    try:
        status = PlanStatus(status_value)
    except ValueError:
        return {
            "content": [
                {
                    "type": "text",
                    "text": "Invalid status. Use draft, active, completed, archived.",
                }
            ],
            "is_error": True,
        }

    try:
        plan_format = PlanFormat(format_value)
    except ValueError:
        return {
            "content": [{"type": "text", "text": "Invalid format. Use json or yaml."}],
            "is_error": True,
        }

    content = args.get("content")
    if content is None:
        match plan_format:
            case PlanFormat.JSON:
                content = "{}"
            case PlanFormat.YAML:
                return {
                    "content": [
                        {"type": "text", "text": "YAML plans require content."}
                    ],
                    "is_error": True,
                }
            case _:
                return {
                    "content": [
                        {"type": "text", "text": "Invalid format. Use json or yaml."}
                    ],
                    "is_error": True,
                }

    tags = None
    if args.get("tags"):
        tags = [t.strip() for t in args["tags"].split(",") if t.strip()]

    task_ids = None
    if args.get("task_ids"):
        task_ids = [t.strip() for t in args["task_ids"].split(",") if t.strip()]

    try:
        plan = await service.create_plan(
            name=args["name"],
            description=args.get("description"),
            status=status,
            format=plan_format,
            content=content,
            product_id=args.get("product_id"),
            project_id=args.get("project_id"),
            goal_id=args.get("goal_id"),
            objective_id=args.get("objective_id"),
            task_ids=task_ids,
            tags=tags,
        )
    except ValueError as exc:
        return {
            "content": [{"type": "text", "text": str(exc)}],
            "is_error": True,
        }

    return {
        "content": [
            {"type": "text", "text": f"Created plan '{plan.name}' with ID: {plan.id}"}
        ]
    }


@tool(
    "list_plans",
    "List plans, optionally filtered by status or links",
    {
        "status": str,
        "project_id": str,
        "product_id": str,
        "goal_id": str,
        "objective_id": str,
    },
)
async def list_plans(args: dict[str, Any]) -> dict[str, Any]:
    """List plans with optional filters."""
    from pms.models import PlanStatus

    service = _get_plan_service()

    status = None
    if args.get("status"):
        try:
            status = PlanStatus(args["status"].lower())
        except ValueError:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "Invalid status. Use draft, active, completed, archived.",
                    }
                ],
                "is_error": True,
            }

    result = await service.list_plans(
        status=status,
        project_id=args.get("project_id"),
        product_id=args.get("product_id"),
        goal_id=args.get("goal_id"),
        objective_id=args.get("objective_id"),
    )

    if not result.items:
        return {"content": [{"type": "text", "text": "No plans found."}]}

    lines = [f"Found {result.total_count} plan(s):"]
    for plan in result.items:
        project = plan.project_id or "none"
        lines.append(
            f"- {plan.name} ({plan.status.value}, {plan.format.value}) "
            f"project={project} tasks={len(plan.task_ids)} ID: {plan.id}"
        )

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "get_plan",
    "Get plan details by name or ID",
    {"identifier": str},
)
async def get_plan(args: dict[str, Any]) -> dict[str, Any]:
    """Get plan by name or ID."""
    service = _get_plan_service()
    identifier = args["identifier"]

    plan = await service.get_plan_by_name(identifier)
    if plan is None:
        plan = await service.get_plan(identifier)

    if plan is None:
        return {
            "content": [{"type": "text", "text": f"Plan '{identifier}' not found."}],
            "is_error": True,
        }

    return {
        "content": [
            {
                "type": "text",
                "text": (
                    f"Plan: {plan.name}\n"
                    f"ID: {plan.id}\n"
                    f"Status: {plan.status.value}\n"
                    f"Format: {plan.format.value}\n"
                    f"Project: {plan.project_id or 'none'}\n"
                    f"Tasks: {', '.join(plan.task_ids) if plan.task_ids else 'none'}\n"
                    f"Content:\n{plan.content}"
                ),
            }
        ]
    }


@tool(
    "update_plan",
    "Update plan fields like status, format, content, or links",
    {
        "plan_id": str,
        "name": str,
        "description": str,
        "status": str,
        "format": str,
        "content": str,
        "product_id": str,
        "project_id": str,
        "goal_id": str,
        "objective_id": str,
        "task_ids": str,
        "tags": str,
    },
)
async def update_plan(args: dict[str, Any]) -> dict[str, Any]:
    """Update a plan."""
    from pms.models import PlanFormat, PlanStatus

    service = _get_plan_service()

    status = None
    if args.get("status"):
        try:
            status = PlanStatus(args["status"].lower())
        except ValueError:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "Invalid status. Use draft, active, completed, archived.",
                    }
                ],
                "is_error": True,
            }

    plan_format = None
    if args.get("format"):
        try:
            plan_format = PlanFormat(args["format"].lower())
        except ValueError:
            return {
                "content": [
                    {"type": "text", "text": "Invalid format. Use json or yaml."}
                ],
                "is_error": True,
            }

    tags = None
    if args.get("tags"):
        tags = [t.strip() for t in args["tags"].split(",") if t.strip()]

    task_ids = None
    if args.get("task_ids"):
        task_ids = [t.strip() for t in args["task_ids"].split(",") if t.strip()]

    try:
        plan = await service.update_plan(
            plan_id=args["plan_id"],
            name=args.get("name"),
            description=args.get("description"),
            status=status,
            format=plan_format,
            content=args.get("content"),
            product_id=args.get("product_id"),
            project_id=args.get("project_id"),
            goal_id=args.get("goal_id"),
            objective_id=args.get("objective_id"),
            task_ids=task_ids,
            tags=tags,
        )
    except ValueError as exc:
        return {
            "content": [{"type": "text", "text": str(exc)}],
            "is_error": True,
        }

    if plan is None:
        return {
            "content": [{"type": "text", "text": "Plan not found."}],
            "is_error": True,
        }

    return {"content": [{"type": "text", "text": f"Updated plan '{plan.name}'."}]}


# =============================================================================
# Plan Test Job Tools
# =============================================================================


def _parse_csv_args(value: Any) -> list[str]:
    if value is None:
        return []
    text = str(value)
    if not text.strip():
        return []
    return [item.strip() for item in text.split(",") if item.strip()]


def _parse_env_pairs(value: Any) -> tuple[tuple[str, str], ...] | None:
    if value is None:
        return None
    raw = _parse_csv_args(value)
    if not raw:
        return ()
    pairs: list[tuple[str, str]] = []
    for item in raw:
        if "=" not in item:
            return None
        key, val = item.split("=", 1)
        pairs.append((key.strip(), val.strip()))
    return tuple(pairs)


@tool(
    "create_plan_test_job",
    "Create a plan-linked test job",
    {
        "plan_id": str,
        "name": str,
        "description": str,
        "mode": str,
        "project_path": str,
        "test_command": str,
        "setup_command": str,
        "working_dir": str,
        "env_vars": str,
        "timeout": float,
        "capture_logs": str,
        "save_artifacts": str,
        "task_ids": str,
        "transition_on_success": str,
        "transition_on_failure": str,
        "transition_by": str,
        "transition_reason": str,
        "project_id": str,
        "server_id": str,
        "server_name": str,
        "remote_path": str,
        "exclude_patterns": str,
    },
)
async def create_plan_test_job(args: dict[str, Any]) -> dict[str, Any]:
    """Create a plan test job."""
    service = _get_plan_test_job_service()

    mode = str(args.get("mode", "local")).lower()
    match mode:
        case "local" | "aws":
            pass
        case _:
            return {
                "content": [
                    {"type": "text", "text": "Invalid mode. Use local or aws."}
                ],
                "is_error": True,
            }

    env_pairs = _parse_env_pairs(args.get("env_vars"))
    if env_pairs is None:
        if args.get("env_vars") is not None:
            return {
                "content": [
                    {"type": "text", "text": "Invalid env_vars. Use KEY=VALUE pairs."}
                ],
                "is_error": True,
            }
        env_pairs = ()

    try:
        job = await service.create_job(
            plan_id=args["plan_id"],
            name=args["name"],
            description=args.get("description"),
            mode=mode,
            project_path=args.get("project_path") or ".",
            test_command=args.get("test_command") or "pytest",
            setup_command=args.get("setup_command"),
            working_dir=args.get("working_dir"),
            env_vars=env_pairs or (),
            timeout=float(args.get("timeout", 600.0)),
            capture_logs=tuple(_parse_csv_args(args.get("capture_logs"))),
            save_artifacts=tuple(_parse_csv_args(args.get("save_artifacts"))),
            task_ids=tuple(_parse_csv_args(args.get("task_ids"))),
            transition_on_success=args.get("transition_on_success"),
            transition_on_failure=args.get("transition_on_failure"),
            transition_by=args.get("transition_by"),
            transition_reason=args.get("transition_reason"),
            project_id=args.get("project_id"),
            server_id=args.get("server_id"),
            server_name=args.get("server_name"),
            remote_path=args.get("remote_path") or "/home/ec2-user/project",
            exclude_patterns=tuple(_parse_csv_args(args.get("exclude_patterns")))
            if args.get("exclude_patterns")
            else None,
            stream_output=bool(args.get("stream_output", False)),
        )
    except (ValueError, RuntimeError) as exc:
        return {
            "content": [{"type": "text", "text": str(exc)}],
            "is_error": True,
        }

    return {
        "content": [
            {"type": "text", "text": f"Created plan test job '{job.name}' ID: {job.id}"}
        ]
    }


@tool(
    "list_plan_test_jobs",
    "List test jobs for a plan",
    {"plan_id": str},
)
async def list_plan_test_jobs(args: dict[str, Any]) -> dict[str, Any]:
    """List plan test jobs."""
    service = _get_plan_test_job_service()
    result = await service.list_jobs(plan_id=args.get("plan_id"))

    if not result.items:
        return {"content": [{"type": "text", "text": "No plan test jobs found."}]}

    lines = [f"Found {result.total_count} plan test job(s):"]
    for job in result.items:
        lines.append(
            f"- {job.name} ({job.mode}) {job.test_command} "
            f"tasks={len(job.task_ids)} ID: {job.id}"
        )
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "get_plan_test_job",
    "Get details for a plan test job by ID",
    {"job_id": str},
)
async def get_plan_test_job(args: dict[str, Any]) -> dict[str, Any]:
    """Get plan test job details."""
    service = _get_plan_test_job_service()
    job_id = args.get("job_id")
    if not job_id:
        return {
            "content": [{"type": "text", "text": "job_id is required."}],
            "is_error": True,
        }

    job = await service.get_job(job_id)
    if job is None:
        return {
            "content": [{"type": "text", "text": "Plan test job not found."}],
            "is_error": True,
        }

    env_text = ", ".join(f"{key}={value}" for key, value in job.env_vars)
    lines = [
        f"Plan Test Job: {job.name}",
        f"ID: {job.id}",
        f"Plan: {job.plan_id}",
        f"Mode: {job.mode}",
        f"Project Path: {job.project_path}",
        f"Command: {job.test_command}",
        f"Timeout: {job.timeout}",
    ]
    if job.setup_command:
        lines.append(f"Setup: {job.setup_command}")
    if job.working_dir:
        lines.append(f"Workdir: {job.working_dir}")
    if env_text:
        lines.append(f"Env: {env_text}")
    if job.task_ids:
        lines.append(f"Tasks: {', '.join(job.task_ids)}")
    if job.transition_on_success or job.transition_on_failure:
        lines.append(
            "Transitions: "
            f"success={job.transition_on_success or '-'} "
            f"failure={job.transition_on_failure or '-'}"
        )
    if job.server_name or job.server_id:
        lines.append(f"Server: {job.server_name or job.server_id}")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "update_plan_test_job",
    "Update a plan test job",
    {
        "job_id": str,
        "plan_id": str,
        "name": str,
        "description": str,
        "mode": str,
        "project_path": str,
        "test_command": str,
        "setup_command": str,
        "working_dir": str,
        "env_vars": str,
        "timeout": float,
        "capture_logs": str,
        "save_artifacts": str,
        "task_ids": str,
        "transition_on_success": str,
        "transition_on_failure": str,
        "transition_by": str,
        "transition_reason": str,
        "project_id": str,
        "server_id": str,
        "server_name": str,
        "remote_path": str,
        "exclude_patterns": str,
    },
)
async def update_plan_test_job(args: dict[str, Any]) -> dict[str, Any]:
    """Update a plan test job."""
    service = _get_plan_test_job_service()
    job_id = args.get("job_id")
    if not job_id:
        return {
            "content": [{"type": "text", "text": "job_id is required."}],
            "is_error": True,
        }

    mode = args.get("mode")
    if mode is not None:
        mode = str(mode).lower()
        match mode:
            case "local" | "aws":
                pass
            case _:
                return {
                    "content": [
                        {"type": "text", "text": "Invalid mode. Use local or aws."}
                    ],
                    "is_error": True,
                }

    env_pairs = _parse_env_pairs(args.get("env_vars"))
    if env_pairs is None and args.get("env_vars") is not None:
        return {
            "content": [
                {"type": "text", "text": "Invalid env_vars. Use KEY=VALUE pairs."}
            ],
            "is_error": True,
        }

    try:
        job = await service.update_job(
            job_id=job_id,
            plan_id=args.get("plan_id"),
            name=args.get("name"),
            description=args.get("description"),
            mode=mode,
            project_path=args.get("project_path"),
            test_command=args.get("test_command"),
            setup_command=args.get("setup_command"),
            working_dir=args.get("working_dir"),
            env_vars=env_pairs,
            timeout=float(args["timeout"]) if args.get("timeout") is not None else None,
            capture_logs=tuple(_parse_csv_args(args.get("capture_logs")))
            if args.get("capture_logs") is not None
            else None,
            save_artifacts=tuple(_parse_csv_args(args.get("save_artifacts")))
            if args.get("save_artifacts") is not None
            else None,
            task_ids=tuple(_parse_csv_args(args.get("task_ids")))
            if args.get("task_ids") is not None
            else None,
            transition_on_success=args.get("transition_on_success"),
            transition_on_failure=args.get("transition_on_failure"),
            transition_by=args.get("transition_by"),
            transition_reason=args.get("transition_reason"),
            project_id=args.get("project_id"),
            server_id=args.get("server_id"),
            server_name=args.get("server_name"),
            remote_path=args.get("remote_path"),
            exclude_patterns=tuple(_parse_csv_args(args.get("exclude_patterns")))
            if args.get("exclude_patterns") is not None
            else None,
            stream_output=args.get("stream_output"),
        )
    except (ValueError, RuntimeError) as exc:
        return {
            "content": [{"type": "text", "text": str(exc)}],
            "is_error": True,
        }

    if job is None:
        return {
            "content": [{"type": "text", "text": "Plan test job not found."}],
            "is_error": True,
        }

    return {
        "content": [{"type": "text", "text": f"Updated plan test job '{job.name}'."}]
    }


@tool(
    "delete_plan_test_job",
    "Delete a plan test job by ID",
    {"job_id": str},
)
async def delete_plan_test_job(args: dict[str, Any]) -> dict[str, Any]:
    """Delete a plan test job."""
    service = _get_plan_test_job_service()
    job_id = args.get("job_id")
    if not job_id:
        return {
            "content": [{"type": "text", "text": "job_id is required."}],
            "is_error": True,
        }

    job = await service.get_job(job_id)
    if job is None:
        return {
            "content": [{"type": "text", "text": "Plan test job not found."}],
            "is_error": True,
        }

    await service.delete_job(job_id)
    return {"content": [{"type": "text", "text": f"Deleted plan test job {job_id}"}]}


@tool(
    "run_plan_test_job",
    "Run a plan test job and return the test run summary",
    {"job_id": str},
)
async def run_plan_test_job(args: dict[str, Any]) -> dict[str, Any]:
    """Run a plan test job."""
    service = _get_plan_test_job_service()
    job_id = args.get("job_id")
    if not job_id:
        return {
            "content": [{"type": "text", "text": "job_id is required."}],
            "is_error": True,
        }

    try:
        run = await service.run_job(job_id)
    except (ValueError, RuntimeError) as exc:
        return {
            "content": [{"type": "text", "text": str(exc)}],
            "is_error": True,
        }

    if run is None:
        return {
            "content": [{"type": "text", "text": "Plan test job not found."}],
            "is_error": True,
        }

    result = run.result
    status = "passed" if result.success else "failed"
    lines = [
        f"Plan test job '{run.job.name}' ({run.job.id})",
        f"Status: {status}",
        f"Run ID: {result.run_id}",
        f"Summary: {result.summary}",
    ]
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


# =============================================================================
# Organization/Portfolio Tools
# =============================================================================


@tool(
    "create_organization",
    "Create a new organization with members and tags",
    {"name": str, "description": str, "owner": str, "members": str, "tags": str},
)
async def create_organization(args: dict[str, Any]) -> dict[str, Any]:
    """Create a new organization."""
    service = _get_organization_service()

    members = None
    if args.get("members"):
        members = [m.strip() for m in args["members"].split(",") if m.strip()]

    tags = None
    if args.get("tags"):
        tags = [t.strip() for t in args["tags"].split(",") if t.strip()]

    org = await service.create_organization(
        name=args["name"],
        description=args.get("description"),
        owner=args.get("owner"),
        members=members,
        tags=tags,
    )

    return {
        "content": [
            {
                "type": "text",
                "text": f"Created organization '{org.name}' with ID: {org.id}",
            }
        ]
    }


@tool(
    "list_organizations",
    "List organizations, optionally filtered by status",
    {"status": str},
)
async def list_organizations(args: dict[str, Any]) -> dict[str, Any]:
    """List organizations with optional status filter."""
    from pms.models import OrganizationStatus

    service = _get_organization_service()

    status = None
    if args.get("status"):
        try:
            status = OrganizationStatus(args["status"].lower())
        except ValueError:
            return {
                "content": [
                    {"type": "text", "text": "Invalid status. Use active or archived."}
                ],
                "is_error": True,
            }

    result = await service.list_organizations(status=status)

    if not result.items:
        return {"content": [{"type": "text", "text": "No organizations found."}]}

    lines = [f"Found {result.total_count} organization(s):"]
    for org in result.items:
        lines.append(f"- {org.name} ({org.status.value}) ID: {org.id}")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "get_organization",
    "Get organization details by name or ID",
    {"identifier": str},
)
async def get_organization(args: dict[str, Any]) -> dict[str, Any]:
    """Get organization by name or ID."""
    service = _get_organization_service()
    identifier = args["identifier"]

    org = await service.get_organization_by_name(identifier)
    if org is None:
        org = await service.get_organization(identifier)

    if org is None:
        return {
            "content": [
                {"type": "text", "text": f"Organization '{identifier}' not found."}
            ],
            "is_error": True,
        }

    return {
        "content": [
            {
                "type": "text",
                "text": (
                    f"Organization: {org.name}\n"
                    f"ID: {org.id}\n"
                    f"Status: {org.status.value}\n"
                    f"Owner: {org.owner or 'none'}\n"
                    f"Members: {', '.join(org.members) if org.members else 'none'}\n"
                    f"Tags: {', '.join(org.tags) if org.tags else 'none'}"
                ),
            }
        ]
    }


@tool(
    "update_organization",
    "Update organization fields like status, members, tags, or owner",
    {
        "org_id": str,
        "name": str,
        "description": str,
        "status": str,
        "owner": str,
        "members": str,
        "tags": str,
    },
)
async def update_organization(args: dict[str, Any]) -> dict[str, Any]:
    """Update an organization."""
    from pms.models import OrganizationStatus

    service = _get_organization_service()

    status = None
    if args.get("status"):
        try:
            status = OrganizationStatus(args["status"].lower())
        except ValueError:
            return {
                "content": [
                    {"type": "text", "text": "Invalid status. Use active or archived."}
                ],
                "is_error": True,
            }

    members = None
    if args.get("members"):
        members = [m.strip() for m in args["members"].split(",") if m.strip()]

    tags = None
    if args.get("tags"):
        tags = [t.strip() for t in args["tags"].split(",") if t.strip()]

    org = await service.update_organization(
        org_id=args["org_id"],
        name=args.get("name"),
        description=args.get("description"),
        status=status,
        owner=args.get("owner"),
        members=members,
        tags=tags,
    )

    if org is None:
        return {
            "content": [{"type": "text", "text": "Organization not found."}],
            "is_error": True,
        }

    return {
        "content": [{"type": "text", "text": f"Updated organization '{org.name}'."}]
    }


@tool(
    "get_organization_summary",
    "Get organization rollup summary with teams, portfolios, and programs",
    {"org_id": str},
)
async def get_organization_summary(args: dict[str, Any]) -> dict[str, Any]:
    """Get organization summary."""
    service = _get_organization_service()
    summary = await service.get_organization_summary(args["org_id"])

    if summary is None:
        return {
            "content": [{"type": "text", "text": "Organization not found."}],
            "is_error": True,
        }

    stats = summary.stats
    lines = [
        f"Organization: {summary.organization.name}",
        f"ID: {summary.organization.id}",
        f"Teams: {stats.total_teams}",
        f"Portfolios: {stats.total_portfolios}",
        f"Programs: {stats.total_programs}",
        f"Projects: {stats.total_projects}",
        f"Goals: {stats.completed_goals}/{stats.total_goals} ({stats.avg_goal_progress:.0f}%)",
        f"Objectives: {stats.completed_objectives}/{stats.total_objectives} ({stats.avg_objective_progress:.0f}%)",
        f"Tasks blocked: {stats.blocked_tasks}/{stats.total_tasks}",
        f"Risk: {summary.risk_level}",
    ]

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "get_organization_dashboard",
    "Get organization dashboard rollups across teams, portfolios, programs, and work",
    {"status": str, "limit": int, "offset": int},
)
async def get_organization_dashboard(args: dict[str, Any]) -> dict[str, Any]:
    """Get organization dashboard rollups."""
    from pms.models import OrganizationStatus

    service = _get_organization_service()

    status = None
    if args.get("status"):
        try:
            status = OrganizationStatus(args["status"].lower())
        except ValueError:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "Invalid status. Use active or archived.",
                    }
                ],
                "is_error": True,
            }

    limit = int(args.get("limit", 100))
    offset = int(args.get("offset", 0))
    dashboard = await service.get_organization_dashboard(
        status=status,
        limit=limit,
        offset=offset,
    )

    lines = [
        "Organization Dashboard:",
        f"Total Organizations: {dashboard.total_organizations}",
        (
            "Totals: "
            f"teams {dashboard.total_teams} | portfolios {dashboard.total_portfolios} | "
            f"programs {dashboard.total_programs} | projects {dashboard.total_projects} | "
            f"goals {dashboard.total_goals} | objectives {dashboard.total_objectives} | "
            f"tasks {dashboard.total_tasks} | blocked {dashboard.blocked_tasks}"
        ),
    ]

    if dashboard.items:
        lines.append("Organizations:")
        for item in dashboard.items:
            stats = item.stats
            lines.append(
                f"- {item.organization.name} ({item.organization.status.value}) "
                f"ID: {item.organization.id} | "
                f"projects {stats.total_projects} | "
                f"goals {stats.completed_goals}/{stats.total_goals} | "
                f"objectives {stats.completed_objectives}/{stats.total_objectives} | "
                f"tasks {stats.total_tasks} ({stats.blocked_tasks} blocked) | "
                f"risk {item.risk_level}"
            )

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "create_team",
    "Create a new team within an organization",
    {
        "name": str,
        "org_id": str,
        "description": str,
        "owner": str,
        "members": str,
        "tags": str,
    },
)
async def create_team(args: dict[str, Any]) -> dict[str, Any]:
    """Create a new team."""
    service = _get_team_service()

    members = None
    if args.get("members"):
        members = [m.strip() for m in args["members"].split(",") if m.strip()]

    tags = None
    if args.get("tags"):
        tags = [t.strip() for t in args["tags"].split(",") if t.strip()]

    team = await service.create_team(
        name=args["name"],
        org_id=args.get("org_id"),
        description=args.get("description"),
        owner=args.get("owner"),
        members=members,
        tags=tags,
    )

    return {
        "content": [
            {"type": "text", "text": f"Created team '{team.name}' with ID: {team.id}"}
        ]
    }


@tool(
    "list_teams",
    "List teams, optionally filtered by organization or status",
    {"org_id": str, "status": str},
)
async def list_teams(args: dict[str, Any]) -> dict[str, Any]:
    """List teams."""
    from pms.models import TeamStatus

    service = _get_team_service()

    status = None
    if args.get("status"):
        try:
            status = TeamStatus(args["status"].lower())
        except ValueError:
            return {
                "content": [
                    {"type": "text", "text": "Invalid status. Use active or archived."}
                ],
                "is_error": True,
            }

    result = await service.list_teams(status=status, org_id=args.get("org_id"))

    if not result.items:
        return {"content": [{"type": "text", "text": "No teams found."}]}

    lines = [f"Found {result.total_count} team(s):"]
    for team in result.items:
        lines.append(
            f"- {team.name} ({team.status.value}) org={team.org_id or 'none'} ID: {team.id}"
        )

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "get_team",
    "Get team details by name or ID",
    {"identifier": str},
)
async def get_team(args: dict[str, Any]) -> dict[str, Any]:
    """Get team by name or ID."""
    service = _get_team_service()
    identifier = args["identifier"]

    team = await service.get_team_by_name(identifier)
    if team is None:
        team = await service.get_team(identifier)

    if team is None:
        return {
            "content": [{"type": "text", "text": f"Team '{identifier}' not found."}],
            "is_error": True,
        }

    return {
        "content": [
            {
                "type": "text",
                "text": (
                    f"Team: {team.name}\n"
                    f"ID: {team.id}\n"
                    f"Org: {team.org_id or 'none'}\n"
                    f"Status: {team.status.value}\n"
                    f"Owner: {team.owner or 'none'}\n"
                    f"Members: {', '.join(team.members) if team.members else 'none'}"
                ),
            }
        ]
    }


@tool(
    "update_team",
    "Update team fields like status, members, tags, or owner",
    {
        "team_id": str,
        "name": str,
        "description": str,
        "status": str,
        "owner": str,
        "members": str,
        "tags": str,
    },
)
async def update_team(args: dict[str, Any]) -> dict[str, Any]:
    """Update a team."""
    from pms.models import TeamStatus

    service = _get_team_service()

    status = None
    if args.get("status"):
        try:
            status = TeamStatus(args["status"].lower())
        except ValueError:
            return {
                "content": [
                    {"type": "text", "text": "Invalid status. Use active or archived."}
                ],
                "is_error": True,
            }

    members = None
    if args.get("members"):
        members = [m.strip() for m in args["members"].split(",") if m.strip()]

    tags = None
    if args.get("tags"):
        tags = [t.strip() for t in args["tags"].split(",") if t.strip()]

    team = await service.update_team(
        team_id=args["team_id"],
        name=args.get("name"),
        description=args.get("description"),
        status=status,
        owner=args.get("owner"),
        members=members,
        tags=tags,
    )

    if team is None:
        return {
            "content": [{"type": "text", "text": "Team not found."}],
            "is_error": True,
        }

    return {"content": [{"type": "text", "text": f"Updated team '{team.name}'."}]}


@tool(
    "create_portfolio",
    "Create a new portfolio with linked projects, goals, and objectives",
    {
        "name": str,
        "org_id": str,
        "description": str,
        "owner": str,
        "project_ids": str,
        "goal_ids": str,
        "objective_ids": str,
        "tags": str,
    },
)
async def create_portfolio(args: dict[str, Any]) -> dict[str, Any]:
    """Create a new portfolio."""
    service = _get_portfolio_service()

    project_ids = None
    if args.get("project_ids"):
        project_ids = [p.strip() for p in args["project_ids"].split(",") if p.strip()]
    goal_ids = None
    if args.get("goal_ids"):
        goal_ids = [g.strip() for g in args["goal_ids"].split(",") if g.strip()]
    objective_ids = None
    if args.get("objective_ids"):
        objective_ids = [
            o.strip() for o in args["objective_ids"].split(",") if o.strip()
        ]

    tags = None
    if args.get("tags"):
        tags = [t.strip() for t in args["tags"].split(",") if t.strip()]

    portfolio = await service.create_portfolio(
        name=args["name"],
        org_id=args.get("org_id"),
        description=args.get("description"),
        owner=args.get("owner"),
        project_ids=project_ids,
        goal_ids=goal_ids,
        objective_ids=objective_ids,
        tags=tags,
    )

    return {
        "content": [
            {
                "type": "text",
                "text": f"Created portfolio '{portfolio.name}' with ID: {portfolio.id}",
            }
        ]
    }


@tool(
    "list_portfolios",
    "List portfolios, optionally filtered by organization or status",
    {"org_id": str, "status": str},
)
async def list_portfolios(args: dict[str, Any]) -> dict[str, Any]:
    """List portfolios."""
    from pms.models import PortfolioStatus

    service = _get_portfolio_service()

    status = None
    if args.get("status"):
        try:
            status = PortfolioStatus(args["status"].lower())
        except ValueError:
            return {
                "content": [
                    {"type": "text", "text": "Invalid status. Use active or archived."}
                ],
                "is_error": True,
            }

    result = await service.list_portfolios(status=status, org_id=args.get("org_id"))

    if not result.items:
        return {"content": [{"type": "text", "text": "No portfolios found."}]}

    lines = [f"Found {result.total_count} portfolio(s):"]
    for portfolio in result.items:
        lines.append(
            f"- {portfolio.name} ({portfolio.status.value}) org={portfolio.org_id or 'none'} ID: {portfolio.id}"
        )

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "get_portfolio",
    "Get portfolio details by name or ID",
    {"identifier": str},
)
async def get_portfolio(args: dict[str, Any]) -> dict[str, Any]:
    """Get portfolio by name or ID."""
    service = _get_portfolio_service()
    identifier = args["identifier"]

    portfolio = await service.get_portfolio_by_name(identifier)
    if portfolio is None:
        portfolio = await service.get_portfolio(identifier)

    if portfolio is None:
        return {
            "content": [
                {"type": "text", "text": f"Portfolio '{identifier}' not found."}
            ],
            "is_error": True,
        }

    return {
        "content": [
            {
                "type": "text",
                "text": (
                    f"Portfolio: {portfolio.name}\n"
                    f"ID: {portfolio.id}\n"
                    f"Org: {portfolio.org_id or 'none'}\n"
                    f"Status: {portfolio.status.value}\n"
                    f"Projects: {len(portfolio.project_ids)}\n"
                    f"Goals: {len(portfolio.effective_goal_ids)} effective / {len(portfolio.goal_ids)} direct\n"
                    f"Objectives: {len(portfolio.effective_objective_ids)} effective / {len(portfolio.objective_ids)} direct"
                ),
            }
        ]
    }


@tool(
    "update_portfolio",
    "Update portfolio fields like status, linked projects, linked goals, linked objectives, or tags",
    {
        "portfolio_id": str,
        "name": str,
        "description": str,
        "status": str,
        "owner": str,
        "project_ids": str,
        "goal_ids": str,
        "objective_ids": str,
        "tags": str,
    },
)
async def update_portfolio(args: dict[str, Any]) -> dict[str, Any]:
    """Update a portfolio."""
    from pms.models import PortfolioStatus

    service = _get_portfolio_service()

    status = None
    if args.get("status"):
        try:
            status = PortfolioStatus(args["status"].lower())
        except ValueError:
            return {
                "content": [
                    {"type": "text", "text": "Invalid status. Use active or archived."}
                ],
                "is_error": True,
            }

    project_ids = None
    if args.get("project_ids"):
        project_ids = [p.strip() for p in args["project_ids"].split(",") if p.strip()]
    goal_ids = None
    if args.get("goal_ids"):
        goal_ids = [g.strip() for g in args["goal_ids"].split(",") if g.strip()]
    objective_ids = None
    if args.get("objective_ids"):
        objective_ids = [
            o.strip() for o in args["objective_ids"].split(",") if o.strip()
        ]

    tags = None
    if args.get("tags"):
        tags = [t.strip() for t in args["tags"].split(",") if t.strip()]

    portfolio = await service.update_portfolio(
        portfolio_id=args["portfolio_id"],
        name=args.get("name"),
        description=args.get("description"),
        status=status,
        owner=args.get("owner"),
        project_ids=project_ids,
        goal_ids=goal_ids,
        objective_ids=objective_ids,
        tags=tags,
    )

    if portfolio is None:
        return {
            "content": [{"type": "text", "text": "Portfolio not found."}],
            "is_error": True,
        }

    return {
        "content": [{"type": "text", "text": f"Updated portfolio '{portfolio.name}'."}]
    }


@tool(
    "get_portfolio_summary",
    "Get portfolio rollup summary with goals, objectives, and risk",
    {"portfolio_id": str},
)
async def get_portfolio_summary(args: dict[str, Any]) -> dict[str, Any]:
    """Get portfolio summary."""
    service = _get_portfolio_service()
    summary = await service.get_portfolio_summary(args["portfolio_id"])

    if summary is None:
        return {
            "content": [{"type": "text", "text": "Portfolio not found."}],
            "is_error": True,
        }

    stats = summary.stats
    lines = [
        f"Portfolio: {summary.portfolio.name}",
        f"ID: {summary.portfolio.id}",
        f"Projects: {stats.total_projects}",
        f"Goals: {stats.completed_goals}/{stats.total_goals} ({stats.avg_goal_progress:.0f}%)",
        f"Objectives: {stats.completed_objectives}/{stats.total_objectives} ({stats.avg_objective_progress:.0f}%)",
        f"Tasks blocked: {stats.blocked_tasks}/{stats.total_tasks}",
        f"Risk: {summary.risk_level}",
    ]

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "get_portfolio_dashboard",
    "Get portfolio dashboard rollups across projects and goals",
    {"org_id": str, "status": str, "limit": int, "offset": int},
)
async def get_portfolio_dashboard(args: dict[str, Any]) -> dict[str, Any]:
    """Get portfolio dashboard rollups."""
    from pms.models import PortfolioStatus

    service = _get_portfolio_service()

    status = None
    if args.get("status"):
        try:
            status = PortfolioStatus(args["status"].lower())
        except ValueError:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "Invalid status. Use active or archived.",
                    }
                ],
                "is_error": True,
            }

    limit = int(args.get("limit", 100))
    offset = int(args.get("offset", 0))
    dashboard = await service.get_portfolio_dashboard(
        status=status,
        org_id=args.get("org_id"),
        limit=limit,
        offset=offset,
    )

    lines = [
        "Portfolio Dashboard:",
        f"Total Portfolios: {dashboard.total_portfolios}",
        (
            "Totals: "
            f"projects {dashboard.total_projects} | goals {dashboard.total_goals} | "
            f"objectives {dashboard.total_objectives} | tasks {dashboard.total_tasks} | "
            f"blocked {dashboard.blocked_tasks}"
        ),
    ]

    if dashboard.items:
        lines.append("Portfolios:")
        for item in dashboard.items:
            stats = item.stats
            lines.append(
                f"- {item.portfolio.name} ({item.portfolio.status.value}) "
                f"ID: {item.portfolio.id} | org {item.portfolio.org_id or 'none'} | "
                f"projects {stats.total_projects} | "
                f"goals {stats.completed_goals}/{stats.total_goals} | "
                f"objectives {stats.completed_objectives}/{stats.total_objectives} | "
                f"tasks {stats.total_tasks} ({stats.blocked_tasks} blocked) | "
                f"risk {item.risk_level}"
            )

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "create_program",
    "Create a new program with linked projects, goals, and objectives",
    {
        "name": str,
        "org_id": str,
        "portfolio_id": str,
        "description": str,
        "owner": str,
        "project_ids": str,
        "goal_ids": str,
        "objective_ids": str,
        "tags": str,
    },
)
async def create_program(args: dict[str, Any]) -> dict[str, Any]:
    """Create a new program."""
    service = _get_program_service()

    project_ids = None
    if args.get("project_ids"):
        project_ids = [p.strip() for p in args["project_ids"].split(",") if p.strip()]
    goal_ids = None
    if args.get("goal_ids"):
        goal_ids = [g.strip() for g in args["goal_ids"].split(",") if g.strip()]
    objective_ids = None
    if args.get("objective_ids"):
        objective_ids = [
            o.strip() for o in args["objective_ids"].split(",") if o.strip()
        ]

    tags = None
    if args.get("tags"):
        tags = [t.strip() for t in args["tags"].split(",") if t.strip()]

    program = await service.create_program(
        name=args["name"],
        org_id=args.get("org_id"),
        portfolio_id=args.get("portfolio_id"),
        description=args.get("description"),
        owner=args.get("owner"),
        project_ids=project_ids,
        goal_ids=goal_ids,
        objective_ids=objective_ids,
        tags=tags,
    )

    return {
        "content": [
            {
                "type": "text",
                "text": f"Created program '{program.name}' with ID: {program.id}",
            }
        ]
    }


@tool(
    "list_programs",
    "List programs, optionally filtered by org, portfolio, or status",
    {"org_id": str, "portfolio_id": str, "status": str},
)
async def list_programs(args: dict[str, Any]) -> dict[str, Any]:
    """List programs."""
    from pms.models import ProgramStatus

    service = _get_program_service()

    status = None
    if args.get("status"):
        try:
            status = ProgramStatus(args["status"].lower())
        except ValueError:
            return {
                "content": [
                    {"type": "text", "text": "Invalid status. Use active or archived."}
                ],
                "is_error": True,
            }

    result = await service.list_programs(
        status=status,
        org_id=args.get("org_id"),
        portfolio_id=args.get("portfolio_id"),
    )

    if not result.items:
        return {"content": [{"type": "text", "text": "No programs found."}]}

    lines = [f"Found {result.total_count} program(s):"]
    for program in result.items:
        lines.append(
            f"- {program.name} ({program.status.value}) portfolio={program.portfolio_id or 'none'} ID: {program.id}"
        )

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "get_program",
    "Get program details by name or ID",
    {"identifier": str},
)
async def get_program(args: dict[str, Any]) -> dict[str, Any]:
    """Get program by name or ID."""
    service = _get_program_service()
    identifier = args["identifier"]

    program = await service.get_program_by_name(identifier)
    if program is None:
        program = await service.get_program(identifier)

    if program is None:
        return {
            "content": [{"type": "text", "text": f"Program '{identifier}' not found."}],
            "is_error": True,
        }

    return {
        "content": [
            {
                "type": "text",
                "text": (
                    f"Program: {program.name}\n"
                    f"ID: {program.id}\n"
                    f"Org: {program.org_id or 'none'}\n"
                    f"Portfolio: {program.portfolio_id or 'none'}\n"
                    f"Status: {program.status.value}\n"
                    f"Projects: {len(program.project_ids)}\n"
                    f"Goals: {len(program.effective_goal_ids)} effective / {len(program.goal_ids)} direct\n"
                    f"Objectives: {len(program.effective_objective_ids)} effective / {len(program.objective_ids)} direct"
                ),
            }
        ]
    }


@tool(
    "update_program",
    "Update program fields like status, linked projects, linked goals, linked objectives, or tags",
    {
        "program_id": str,
        "name": str,
        "description": str,
        "status": str,
        "owner": str,
        "project_ids": str,
        "goal_ids": str,
        "objective_ids": str,
        "tags": str,
    },
)
async def update_program(args: dict[str, Any]) -> dict[str, Any]:
    """Update a program."""
    from pms.models import ProgramStatus

    service = _get_program_service()

    status = None
    if args.get("status"):
        try:
            status = ProgramStatus(args["status"].lower())
        except ValueError:
            return {
                "content": [
                    {"type": "text", "text": "Invalid status. Use active or archived."}
                ],
                "is_error": True,
            }

    project_ids = None
    if args.get("project_ids"):
        project_ids = [p.strip() for p in args["project_ids"].split(",") if p.strip()]
    goal_ids = None
    if args.get("goal_ids"):
        goal_ids = [g.strip() for g in args["goal_ids"].split(",") if g.strip()]
    objective_ids = None
    if args.get("objective_ids"):
        objective_ids = [
            o.strip() for o in args["objective_ids"].split(",") if o.strip()
        ]

    tags = None
    if args.get("tags"):
        tags = [t.strip() for t in args["tags"].split(",") if t.strip()]

    program = await service.update_program(
        program_id=args["program_id"],
        name=args.get("name"),
        description=args.get("description"),
        status=status,
        owner=args.get("owner"),
        project_ids=project_ids,
        goal_ids=goal_ids,
        objective_ids=objective_ids,
        tags=tags,
    )

    if program is None:
        return {
            "content": [{"type": "text", "text": "Program not found."}],
            "is_error": True,
        }

    return {"content": [{"type": "text", "text": f"Updated program '{program.name}'."}]}


@tool(
    "get_program_summary",
    "Get program rollup summary with goals, objectives, and risk",
    {"program_id": str},
)
async def get_program_summary(args: dict[str, Any]) -> dict[str, Any]:
    """Get program summary."""
    service = _get_program_service()
    summary = await service.get_program_summary(args["program_id"])

    if summary is None:
        return {
            "content": [{"type": "text", "text": "Program not found."}],
            "is_error": True,
        }

    stats = summary.stats
    lines = [
        f"Program: {summary.program.name}",
        f"ID: {summary.program.id}",
        f"Projects: {stats.total_projects}",
        f"Goals: {stats.completed_goals}/{stats.total_goals} ({stats.avg_goal_progress:.0f}%)",
        f"Objectives: {stats.completed_objectives}/{stats.total_objectives} ({stats.avg_objective_progress:.0f}%)",
        f"Tasks blocked: {stats.blocked_tasks}/{stats.total_tasks}",
        f"Risk: {summary.risk_level}",
    ]

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "get_program_dashboard",
    "Get program dashboard rollups across projects and goals",
    {"org_id": str, "portfolio_id": str, "status": str, "limit": int, "offset": int},
)
async def get_program_dashboard(args: dict[str, Any]) -> dict[str, Any]:
    """Get program dashboard rollups."""
    from pms.models import ProgramStatus

    service = _get_program_service()

    status = None
    if args.get("status"):
        try:
            status = ProgramStatus(args["status"].lower())
        except ValueError:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "Invalid status. Use active or archived.",
                    }
                ],
                "is_error": True,
            }

    limit = int(args.get("limit", 100))
    offset = int(args.get("offset", 0))
    dashboard = await service.get_program_dashboard(
        status=status,
        org_id=args.get("org_id"),
        portfolio_id=args.get("portfolio_id"),
        limit=limit,
        offset=offset,
    )

    lines = [
        "Program Dashboard:",
        f"Total Programs: {dashboard.total_programs}",
        (
            "Totals: "
            f"projects {dashboard.total_projects} | goals {dashboard.total_goals} | "
            f"objectives {dashboard.total_objectives} | tasks {dashboard.total_tasks} | "
            f"blocked {dashboard.blocked_tasks}"
        ),
    ]

    if dashboard.items:
        lines.append("Programs:")
        for item in dashboard.items:
            stats = item.stats
            lines.append(
                f"- {item.program.name} ({item.program.status.value}) "
                f"ID: {item.program.id} | org {item.program.org_id or 'none'} | "
                f"portfolio {item.program.portfolio_id or 'none'} | "
                f"projects {stats.total_projects} | "
                f"goals {stats.completed_goals}/{stats.total_goals} | "
                f"objectives {stats.completed_objectives}/{stats.total_objectives} | "
                f"tasks {stats.total_tasks} ({stats.blocked_tasks} blocked) | "
                f"risk {item.risk_level}"
            )

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


# =============================================================================
# Task Tools
# =============================================================================


@tool(
    "create_task",
    "Create a new task in a project",
    {
        "project": str,
        "title": str,
        "description": str,
        "parent_id": str,
        "priority": str,
        "complexity_points": int,
        "tags": str,
    },
)
async def create_task(args: dict[str, Any]) -> dict[str, Any]:
    """Create a new task."""
    from pms.models import Priority

    project_service = _get_project_service()
    task_service = _get_task_service()

    # Find project
    project = await project_service.get_project_by_name(args["project"])
    if project is None:
        project = await project_service.get_project(args["project"])

    if project is None:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Project '{args['project']}' not found.",
                }
            ],
            "is_error": True,
        }

    # Parse priority
    priority = Priority.MEDIUM
    if args.get("priority"):
        try:
            priority = Priority(args["priority"].lower())
        except ValueError:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Invalid priority. Use: low, medium, high, or critical",
                    }
                ],
                "is_error": True,
            }

    # Parse tags
    tags = None
    if args.get("tags"):
        tags = [t.strip() for t in args["tags"].split(",") if t.strip()]

    try:
        task = await task_service.create_task(
            project_id=project.id,
            title=args["title"],
            description=args.get("description"),
            parent_id=args.get("parent_id"),
            priority=priority,
            complexity_points=args.get("complexity_points"),
            tags=tags,
        )
    except ValueError as exc:
        return {
            "content": [{"type": "text", "text": str(exc)}],
            "is_error": True,
        }

    return {
        "content": [
            {
                "type": "text",
                "text": f"Created task '{task.title}' in project '{project.name}' with ID: {task.id}",
            }
        ]
    }


@tool(
    "list_tasks",
    "List tasks, optionally filtered by project and/or status",
    {"project": str, "status": str},
)
async def list_tasks(args: dict[str, Any]) -> dict[str, Any]:
    """List tasks with optional filters."""
    from pms.models import TaskStatus

    project_service = _get_project_service()
    task_service = _get_task_service()

    project_id = None
    project_name = "all projects"

    if args.get("project"):
        project = await project_service.get_project_by_name(args["project"])
        if project is None:
            project = await project_service.get_project(args["project"])

        if project is None:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Project '{args['project']}' not found.",
                    }
                ],
                "is_error": True,
            }
        project_id = project.id
        project_name = project.name

    status = None
    if args.get("status"):
        try:
            status = TaskStatus(args["status"].lower())
        except ValueError:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Invalid status. Use: todo, in_progress, in_review, done, blocked, cancelled",
                    }
                ],
                "is_error": True,
            }

    result = await task_service.list_tasks(project_id=project_id, status=status)

    if not result.items:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"No tasks found in {project_name}.",
                }
            ]
        }

    lines = [f"Found {result.total_count} task(s) in {project_name}:"]
    for t in result.items:
        priority_icon = {"low": " ", "medium": "!", "high": "!!", "critical": "!!!"}
        icon = priority_icon.get(t.priority.value, "!")
        lines.append(f"[{icon}] {t.title} ({t.status.value}) - ID: {t.id}")

    return {
        "content": [
            {
                "type": "text",
                "text": "\n".join(lines),
            }
        ]
    }


@tool(
    "search_tasks",
    "Search tasks with rich filters (status, priority, tags, labels, dates)",
    {
        "query": str,
        "project": str,
        "status": str,
        "priority": str,
        "assignee": str,
        "tags": str,
        "label_ids": str,
        "label_category_ids": str,
        "created_from": str,
        "created_to": str,
        "updated_from": str,
        "updated_to": str,
        "due_from": str,
        "due_to": str,
        "include_terminal": bool,
        "sort_by": str,
        "sort_dir": str,
        "limit": int,
    },
)
async def search_tasks(args: dict[str, Any]) -> dict[str, Any]:
    """Search tasks with rich filters."""
    from datetime import datetime

    from pms.models import Priority, TaskStatus

    project_service = _get_project_service()
    task_service = _get_task_service()

    project_id = None
    if args.get("project"):
        project = await project_service.get_project_by_name(args["project"])
        if project is None:
            project = await project_service.get_project(args["project"])
        if project is None:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Project '{args['project']}' not found.",
                    }
                ],
                "is_error": True,
            }
        project_id = project.id

    statuses = None
    if args.get("status"):
        status_items = [s.strip() for s in args["status"].split(",") if s.strip()]
        try:
            statuses = [TaskStatus(item.lower()) for item in status_items]
        except ValueError:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "Invalid status. Use: todo, in_progress, blocked, in_review, done, cancelled",
                    }
                ],
                "is_error": True,
            }

    priorities = None
    if args.get("priority"):
        priority_items = [p.strip() for p in args["priority"].split(",") if p.strip()]
        try:
            priorities = [Priority(item.lower()) for item in priority_items]
        except ValueError:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "Invalid priority. Use: low, medium, high, critical",
                    }
                ],
                "is_error": True,
            }

    tags = None
    if args.get("tags"):
        tags = [t.strip() for t in args["tags"].split(",") if t.strip()]

    label_ids = None
    if args.get("label_ids"):
        label_ids = [t.strip() for t in args["label_ids"].split(",") if t.strip()]

    label_category_ids = None
    if args.get("label_category_ids"):
        label_category_ids = [
            t.strip() for t in args["label_category_ids"].split(",") if t.strip()
        ]

    sort_by = None
    if args.get("sort_by"):
        sort_by = str(args["sort_by"]).strip().lower()
        if sort_by not in {"updated_at", "created_at", "due_date", "priority"}:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "Invalid sort_by. Use: updated_at, created_at, due_date, priority",
                    }
                ],
                "is_error": True,
            }

    sort_dir = None
    if args.get("sort_dir"):
        sort_dir = str(args["sort_dir"]).strip().lower()
        if sort_dir not in {"asc", "desc"}:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "Invalid sort_dir. Use: asc or desc",
                    }
                ],
                "is_error": True,
            }

    def parse_dt(value: str | None) -> datetime | None:
        if not value:
            return None
        return datetime.fromisoformat(value)

    try:
        created_from = parse_dt(args.get("created_from"))
        created_to = parse_dt(args.get("created_to"))
        updated_from = parse_dt(args.get("updated_from"))
        updated_to = parse_dt(args.get("updated_to"))
        due_from = parse_dt(args.get("due_from"))
        due_to = parse_dt(args.get("due_to"))
    except ValueError:
        return {
            "content": [
                {
                    "type": "text",
                    "text": "Invalid timestamp (use ISO format)",
                }
            ],
            "is_error": True,
        }

    result = await task_service.search_tasks(
        query=args.get("query"),
        project_id=project_id,
        statuses=statuses,
        priorities=priorities,
        assignee=args.get("assignee"),
        created_from=created_from,
        created_to=created_to,
        updated_from=updated_from,
        updated_to=updated_to,
        due_from=due_from,
        due_to=due_to,
        tags=tags,
        label_ids=label_ids,
        label_category_ids=label_category_ids,
        include_terminal=bool(args.get("include_terminal")),
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=args.get("limit", 100),
    )

    if not result.items:
        return {"content": [{"type": "text", "text": "No matching tasks found."}]}

    lines = [f"Found {result.total_count} task(s):"]
    for task in result.items:
        lines.append(f"- {task.title} ({task.status.value}) ID: {task.id}")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "create_saved_search",
    "Create a saved search queue for tasks",
    {
        "name": str,
        "description": str,
        "owner": str,
        "scope_type": str,
        "scope_id": str,
        "filters": str,
        "sort_by": str,
        "sort_dir": str,
    },
)
async def create_saved_search(args: dict[str, Any]) -> dict[str, Any]:
    """Create a saved search queue for tasks."""
    import json

    service = _get_saved_search_service()

    name = args.get("name")
    if not name:
        return {
            "content": [{"type": "text", "text": "name is required."}],
            "is_error": True,
        }

    filters: dict[str, Any] = {}
    if args.get("filters"):
        try:
            filters = json.loads(str(args["filters"]))
        except json.JSONDecodeError:
            return {
                "content": [{"type": "text", "text": "filters must be valid JSON."}],
                "is_error": True,
            }

    saved = await service.create(
        name=str(name),
        description=args.get("description"),
        owner=args.get("owner"),
        scope_type=str(args.get("scope_type") or "global"),
        scope_id=args.get("scope_id"),
        filters=filters,
        sort_by=args.get("sort_by"),
        sort_dir=args.get("sort_dir"),
    )

    return {
        "content": [
            {
                "type": "text",
                "text": f"Saved search created: {saved.name} (ID: {saved.id})",
            }
        ]
    }


@tool(
    "list_saved_searches",
    "List saved search queues",
    {"owner": str, "scope_type": str, "scope_id": str, "limit": int, "offset": int},
)
async def list_saved_searches(args: dict[str, Any]) -> dict[str, Any]:
    """List saved search queues."""
    service = _get_saved_search_service()

    result = await service.list(
        owner=args.get("owner"),
        scope_type=args.get("scope_type"),
        scope_id=args.get("scope_id"),
        limit=int(args.get("limit", 50)),
        offset=int(args.get("offset", 0)),
    )

    if not result.items:
        return {"content": [{"type": "text", "text": "No saved searches found."}]}

    lines = [f"Saved searches ({result.total_count}):"]
    for item in result.items:
        scope = (
            f"{item.scope_type}:{item.scope_id}" if item.scope_id else item.scope_type
        )
        lines.append(f"- {item.name} ({scope}) ID: {item.id}")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "get_saved_search",
    "Get a saved search queue by ID",
    {"queue_id": str},
)
async def get_saved_search(args: dict[str, Any]) -> dict[str, Any]:
    """Get a saved search queue by ID."""
    import json

    service = _get_saved_search_service()

    queue_id = args.get("queue_id")
    if not queue_id:
        return {
            "content": [{"type": "text", "text": "queue_id is required."}],
            "is_error": True,
        }

    saved = await service.get(str(queue_id))
    if saved is None:
        return {
            "content": [{"type": "text", "text": "Saved search not found."}],
            "is_error": True,
        }

    return {
        "content": [{"type": "text", "text": json.dumps(saved.to_dict(), default=str)}]
    }


@tool(
    "update_saved_search",
    "Update a saved search queue",
    {
        "queue_id": str,
        "name": str,
        "description": str,
        "owner": str,
        "scope_type": str,
        "scope_id": str,
        "filters": str,
        "sort_by": str,
        "sort_dir": str,
    },
)
async def update_saved_search(args: dict[str, Any]) -> dict[str, Any]:
    """Update a saved search queue."""
    import json

    service = _get_saved_search_service()

    queue_id = args.get("queue_id")
    if not queue_id:
        return {
            "content": [{"type": "text", "text": "queue_id is required."}],
            "is_error": True,
        }

    filters = None
    if args.get("filters") is not None:
        try:
            filters = json.loads(str(args.get("filters") or "{}"))
        except json.JSONDecodeError:
            return {
                "content": [{"type": "text", "text": "filters must be valid JSON."}],
                "is_error": True,
            }

    saved = await service.update(
        search_id=str(queue_id),
        name=args.get("name"),
        description=args.get("description"),
        owner=args.get("owner"),
        scope_type=args.get("scope_type"),
        scope_id=args.get("scope_id"),
        filters=filters,
        sort_by=args.get("sort_by"),
        sort_dir=args.get("sort_dir"),
    )

    if saved is None:
        return {
            "content": [{"type": "text", "text": "Saved search not found."}],
            "is_error": True,
        }

    return {
        "content": [
            {
                "type": "text",
                "text": f"Saved search updated: {saved.name} (ID: {saved.id})",
            }
        ]
    }


@tool(
    "delete_saved_search",
    "Delete a saved search queue",
    {"queue_id": str},
)
async def delete_saved_search(args: dict[str, Any]) -> dict[str, Any]:
    """Delete a saved search queue."""
    service = _get_saved_search_service()

    queue_id = args.get("queue_id")
    if not queue_id:
        return {
            "content": [{"type": "text", "text": "queue_id is required."}],
            "is_error": True,
        }

    deleted = await service.delete(str(queue_id))
    if not deleted:
        return {
            "content": [{"type": "text", "text": "Saved search not found."}],
            "is_error": True,
        }
    return {"content": [{"type": "text", "text": f"Deleted saved search {queue_id}."}]}


@tool(
    "run_saved_search",
    "Run a saved search queue and return matching tasks",
    {"queue_id": str, "limit": int, "offset": int, "overrides": str},
)
async def run_saved_search(args: dict[str, Any]) -> dict[str, Any]:
    """Run a saved search queue and return matching tasks."""
    import json

    service = _get_saved_search_service()

    queue_id = args.get("queue_id")
    if not queue_id:
        return {
            "content": [{"type": "text", "text": "queue_id is required."}],
            "is_error": True,
        }

    overrides = None
    if args.get("overrides"):
        try:
            overrides = json.loads(str(args["overrides"]))
        except json.JSONDecodeError:
            return {
                "content": [{"type": "text", "text": "overrides must be valid JSON."}],
                "is_error": True,
            }

    run = await service.run(
        str(queue_id),
        overrides=overrides,
        limit=int(args.get("limit", 50)),
        offset=int(args.get("offset", 0)),
    )
    if run is None:
        return {
            "content": [{"type": "text", "text": "Saved search not found."}],
            "is_error": True,
        }

    if not run.result.items:
        return {"content": [{"type": "text", "text": "No matching tasks found."}]}

    lines = [f"Queue '{run.saved_search.name}' ({run.result.total_count} tasks):"]
    for task in run.result.items:
        lines.append(f"- {task.title} ({task.status.value}) ID: {task.id}")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "list_queue_presets",
    "List smart queue presets (ready/stale/blocked/overdue/at_risk)",
    {
        "project_id": str,
        "limit": int,
        "stale_days": int,
        "at_risk_days": int,
        "include_items": bool,
    },
)
async def list_queue_presets(args: dict[str, Any]) -> dict[str, Any]:
    """List smart queue presets."""
    import json

    service = _get_queue_service()

    include_items = bool(args.get("include_items", False))
    presets = await service.list_presets(
        project_id=args.get("project_id"),
        limit=int(args.get("limit", 5)),
        stale_days=int(args.get("stale_days", 14)),
        at_risk_days=int(args.get("at_risk_days", 7)),
    )

    items = []
    for summary in presets:
        payload = {
            "name": summary.name,
            "description": summary.description,
            "total_count": summary.total_count,
        }
        if include_items:
            payload["items"] = [task.to_dict() for task in summary.items]
        items.append(payload)

    payload = {
        "items": items,
        "page": _page_payload(len(items), len(items), 0),
        "params": {
            "project_id": args.get("project_id"),
            "task_limit": int(args.get("limit", 5)),
            "stale_days": int(args.get("stale_days", 14)),
            "at_risk_days": int(args.get("at_risk_days", 7)),
            "include_items": include_items,
        },
    }
    return {"content": [{"type": "text", "text": json.dumps(payload, default=str)}]}


@tool(
    "get_queue_preset",
    "Get tasks from a smart queue preset",
    {
        "preset": str,
        "project_id": str,
        "limit": int,
        "offset": int,
        "stale_days": int,
        "at_risk_days": int,
    },
)
async def get_queue_preset(args: dict[str, Any]) -> dict[str, Any]:
    """Get tasks from a smart queue preset."""
    import json

    service = _get_queue_service()

    preset = args.get("preset")
    if not preset:
        return {
            "content": [{"type": "text", "text": "preset is required."}],
            "is_error": True,
        }

    summary = await service.get_preset(
        name=str(preset),
        project_id=args.get("project_id"),
        limit=int(args.get("limit", 50)),
        offset=int(args.get("offset", 0)),
        stale_days=int(args.get("stale_days", 14)),
        at_risk_days=int(args.get("at_risk_days", 7)),
    )

    if summary is None:
        return {
            "content": [{"type": "text", "text": "Queue preset not found."}],
            "is_error": True,
        }

    items = [task.to_dict() for task in summary.items]
    payload = {
        "preset": {
            "name": summary.name,
            "description": summary.description,
            "total_count": summary.total_count,
        },
        "items": items,
        "page": _page_payload(
            summary.total_count,
            int(args.get("limit", 50)),
            int(args.get("offset", 0)),
        ),
        "params": {
            "preset": preset,
            "project_id": args.get("project_id"),
            "limit": int(args.get("limit", 50)),
            "offset": int(args.get("offset", 0)),
            "stale_days": int(args.get("stale_days", 14)),
            "at_risk_days": int(args.get("at_risk_days", 7)),
        },
    }
    return {"content": [{"type": "text", "text": json.dumps(payload, default=str)}]}


@tool(
    "list_ready_tasks",
    "List tasks ready to start (no blocking dependencies)",
    {"project": str, "status": str, "exclude_checked_out": bool, "limit": int},
)
async def list_ready_tasks(args: dict[str, Any]) -> dict[str, Any]:
    """List ready tasks."""
    from pms.models import TaskStatus

    project_service = _get_project_service()
    task_service = _get_task_service()

    project_id = None
    if args.get("project"):
        project = await project_service.get_project_by_name(args["project"])
        if project is None:
            project = await project_service.get_project(args["project"])
        if project is None:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Project '{args['project']}' not found.",
                    }
                ],
                "is_error": True,
            }
        project_id = project.id

    statuses = None
    if args.get("status"):
        status_items = [s.strip() for s in args["status"].split(",") if s.strip()]
        try:
            statuses = [TaskStatus(item.lower()) for item in status_items]
        except ValueError:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "Invalid status. Use: todo, in_progress, blocked, in_review, done, cancelled",
                    }
                ],
                "is_error": True,
            }

    result = await task_service.list_ready_tasks(
        project_id=project_id,
        statuses=statuses,
        exclude_checked_out=bool(args.get("exclude_checked_out", True)),
        limit=args.get("limit", 100),
    )

    if not result.items:
        return {"content": [{"type": "text", "text": "No ready tasks found."}]}

    lines = [f"Found {result.total_count} ready task(s):"]
    for task in result.items:
        lines.append(f"- {task.title} ({task.priority.value}) ID: {task.id}")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "list_stale_tasks",
    "List tasks with no recent updates",
    {
        "project": str,
        "status": str,
        "stale_after_days": int,
        "updated_before": str,
        "include_terminal": bool,
        "limit": int,
    },
)
async def list_stale_tasks(args: dict[str, Any]) -> dict[str, Any]:
    """List stale tasks."""
    from datetime import datetime

    from pms.models import TaskStatus

    project_service = _get_project_service()
    task_service = _get_task_service()

    project_id = None
    if args.get("project"):
        project = await project_service.get_project_by_name(args["project"])
        if project is None:
            project = await project_service.get_project(args["project"])
        if project is None:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Project '{args['project']}' not found.",
                    }
                ],
                "is_error": True,
            }
        project_id = project.id

    statuses = None
    if args.get("status"):
        status_items = [s.strip() for s in args["status"].split(",") if s.strip()]
        try:
            statuses = [TaskStatus(item.lower()) for item in status_items]
        except ValueError:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "Invalid status. Use: todo, in_progress, blocked, in_review, done, cancelled",
                    }
                ],
                "is_error": True,
            }

    updated_before = None
    if args.get("updated_before"):
        try:
            updated_before = datetime.fromisoformat(args["updated_before"])
        except ValueError:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "Invalid updated_before timestamp (use ISO format).",
                    }
                ],
                "is_error": True,
            }

    result = await task_service.list_stale_tasks(
        project_id=project_id,
        statuses=statuses,
        stale_after_days=args.get("stale_after_days", 14),
        updated_before=updated_before,
        include_terminal=bool(args.get("include_terminal")),
        limit=args.get("limit", 100),
    )

    if not result.items:
        return {"content": [{"type": "text", "text": "No stale tasks found."}]}

    lines = [f"Found {result.total_count} stale task(s):"]
    for task in result.items:
        updated_at = task.updated_at.isoformat() if task.updated_at else "unknown"
        lines.append(f"- {task.title} ({task.status.value}) updated {updated_at}")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "start_task",
    "Start working on a task (change status to in_progress)",
    {"task_id": str},
)
async def start_task(args: dict[str, Any]) -> dict[str, Any]:
    """Start a task."""
    task_service = _get_task_service()

    task = await task_service.start_task(args["task_id"])
    if task is None:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Task '{args['task_id']}' not found.",
                }
            ],
            "is_error": True,
        }

    return {
        "content": [
            {
                "type": "text",
                "text": f"Started task '{task.title}'. Status is now: {task.status.value}",
            }
        ]
    }


@tool(
    "complete_task",
    "Mark a task as complete with optional actual hours worked",
    {"task_id": str, "actual_hours": float},
)
async def complete_task(args: dict[str, Any]) -> dict[str, Any]:
    """Complete a task."""
    task_service = _get_task_service()

    task = await task_service.complete_task(
        args["task_id"],
        actual_hours=args.get("actual_hours"),
    )
    if task is None:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Task '{args['task_id']}' not found.",
                }
            ],
            "is_error": True,
        }

    hours_text = ""
    if task.actual_hours:
        hours_text = f" Actual hours: {task.actual_hours}"

    return {
        "content": [
            {
                "type": "text",
                "text": f"Completed task '{task.title}'.{hours_text}",
            }
        ]
    }


@tool(
    "update_task",
    "Update task fields (title, description, parent_id, priority, complexity_points)",
    {
        "task_id": str,
        "title": str,
        "description": str,
        "parent_id": str,
        "clear_parent": bool,
        "priority": str,
        "complexity_points": int,
    },
)
async def update_task(args: dict[str, Any]) -> dict[str, Any]:
    """Update a task."""
    from pms.models import Priority

    task_service = _get_task_service()

    task = await task_service.get_task(args["task_id"])
    if task is None:
        return {
            "content": [
                {"type": "text", "text": f"Task '{args['task_id']}' not found."}
            ],
            "is_error": True,
        }

    priority = None
    if args.get("priority"):
        with contextlib.suppress(ValueError):
            priority = Priority(args["priority"].lower())

    if args.get("clear_parent") and args.get("parent_id"):
        return {
            "content": [
                {
                    "type": "text",
                    "text": "Use parent_id or clear_parent, not both.",
                }
            ],
            "is_error": True,
        }

    try:
        updated = await task_service.update_task(
            task_id=task.id,
            title=args.get("title"),
            description=args.get("description"),
            parent_id=args.get("parent_id"),
            clear_parent=bool(args.get("clear_parent")),
            priority=priority,
            complexity_points=args.get("complexity_points"),
        )
    except ValueError as exc:
        return {
            "content": [{"type": "text", "text": str(exc)}],
            "is_error": True,
        }

    if updated is None:
        return {
            "content": [{"type": "text", "text": "Update failed."}],
            "is_error": True,
        }

    return {"content": [{"type": "text", "text": f"Updated task '{updated.title}'."}]}


@tool(
    "update_task_progress",
    "Update task progress with percent complete and status message",
    {
        "task_id": str,
        "percent_complete": int,
        "status_message": str,
        "updated_by": str,
        "metadata": str,
    },
)
async def update_task_progress(args: dict[str, Any]) -> dict[str, Any]:
    """Update task progress."""
    import json

    task_service = _get_task_service()

    if not args.get("status_message"):
        return {
            "content": [{"type": "text", "text": "status_message is required."}],
            "is_error": True,
        }
    if not args.get("updated_by"):
        return {
            "content": [{"type": "text", "text": "updated_by is required."}],
            "is_error": True,
        }

    try:
        percent_complete = int(args.get("percent_complete", 0))
    except TypeError, ValueError:
        return {
            "content": [
                {"type": "text", "text": "percent_complete must be an integer."}
            ],
            "is_error": True,
        }

    metadata = None
    if args.get("metadata"):
        try:
            metadata = json.loads(str(args["metadata"]))
        except json.JSONDecodeError:
            return {
                "content": [{"type": "text", "text": "metadata must be valid JSON."}],
                "is_error": True,
            }

    task = await task_service.update_task_progress(
        task_id=args["task_id"],
        percent_complete=percent_complete,
        status_message=str(args["status_message"]),
        updated_by=str(args["updated_by"]),
        metadata=metadata,
    )
    if task is None:
        return {
            "content": [
                {"type": "text", "text": f"Task '{args['task_id']}' not found."}
            ],
            "is_error": True,
        }

    return {
        "content": [
            {
                "type": "text",
                "text": (
                    f"Updated progress for '{task.title}' to {percent_complete}% "
                    f"({args['status_message']})."
                ),
            }
        ]
    }


@tool(
    "add_task_evidence",
    "Attach evidence to a task",
    {
        "task_id": str,
        "evidence_type": str,
        "reference": str,
        "description": str,
        "metadata": str,
        "created_by": str,
    },
)
async def add_task_evidence(args: dict[str, Any]) -> dict[str, Any]:
    """Attach evidence to a task."""
    import json

    from pms.services.task_evidence_service import TaskEvidenceService

    task_service = _get_task_service()
    evidence_service = TaskEvidenceService(task_service.db, task_service.metrics)

    metadata = None
    if args.get("metadata"):
        try:
            metadata = json.loads(str(args["metadata"]))
        except json.JSONDecodeError:
            return {
                "content": [{"type": "text", "text": "metadata must be valid JSON."}],
                "is_error": True,
            }

    evidence = await evidence_service.add_evidence(
        task_id=args["task_id"],
        evidence_type=args["evidence_type"],
        reference=args["reference"],
        description=args.get("description"),
        metadata=metadata,
        created_by=args.get("created_by") or "system",
    )

    return {
        "content": [
            {
                "type": "text",
                "text": (
                    f"Added evidence {evidence.id} to task {evidence.task_id} "
                    f"({evidence.evidence_type})."
                ),
            }
        ]
    }


@tool(
    "checkout_task",
    "Checkout a task for exclusive work",
    {"task_id": str, "agent_session_id": str, "lease_seconds": int},
)
async def checkout_task(args: dict[str, Any]) -> dict[str, Any]:
    """Checkout a task."""
    from pms.exceptions import TaskCheckoutBlocked, TaskCheckoutConflict
    from pms.repositories.task_repository import TaskRepository
    from pms.services.actor_service import ActorService

    task_service = _get_task_service()
    repo = TaskRepository(
        task_service.db,
        task_service.events,
        task_service.revisions,
        task_service.metrics,
    )
    actor_service = ActorService(
        task_service.db,
        task_service.events,
        task_service.revisions,
        task_service.metrics,
    )

    try:
        checkout_actor = await actor_service.resolve_checkout_actor(
            agent_session_id=args["agent_session_id"],
            actor=args.get("actor"),
        )
    except ValueError as exc:
        return {
            "content": [{"type": "text", "text": str(exc)}],
            "is_error": True,
        }

    try:
        task = await repo.checkout_task(
            task_id=args["task_id"],
            agent_session_id=args["agent_session_id"],
            lease_seconds=args.get("lease_seconds", 300),
            checkout_actor_id=checkout_actor.id,
        )
    except TaskCheckoutConflict as exc:
        return {
            "content": [{"type": "text", "text": str(exc)}],
            "is_error": True,
        }
    except TaskCheckoutBlocked as exc:
        return {
            "content": [{"type": "text", "text": str(exc)}],
            "is_error": True,
        }

    if task is None:
        return {
            "content": [{"type": "text", "text": "Task not found."}],
            "is_error": True,
        }

    lease_until = (
        task.checkout_lease_until.isoformat() if task.checkout_lease_until else "-"
    )
    return {
        "content": [
            {
                "type": "text",
                "text": (
                    f"Checked out task '{task.title}' by {task.checkout_agent_session_id} "
                    f"(lease until {lease_until})."
                ),
            }
        ]
    }


@tool(
    "renew_task_checkout",
    "Renew a task checkout lease",
    {"task_id": str, "agent_session_id": str, "lease_seconds": int},
)
async def renew_task_checkout(args: dict[str, Any]) -> dict[str, Any]:
    """Renew a checkout lease."""
    from pms.exceptions import TaskCheckoutConflict
    from pms.repositories.task_repository import TaskRepository
    from pms.services.actor_service import ActorService

    task_service = _get_task_service()
    repo = TaskRepository(
        task_service.db,
        task_service.events,
        task_service.revisions,
        task_service.metrics,
    )
    actor_service = ActorService(
        task_service.db,
        task_service.events,
        task_service.revisions,
        task_service.metrics,
    )

    try:
        checkout_actor = await actor_service.resolve_checkout_actor(
            agent_session_id=args["agent_session_id"],
            actor=args.get("actor"),
        )
    except ValueError as exc:
        return {
            "content": [{"type": "text", "text": str(exc)}],
            "is_error": True,
        }

    try:
        task = await repo.renew_checkout(
            args["task_id"],
            args["agent_session_id"],
            args.get("lease_seconds", 300),
            checkout_actor_id=checkout_actor.id,
        )
    except TaskCheckoutConflict as exc:
        return {
            "content": [{"type": "text", "text": str(exc)}],
            "is_error": True,
        }

    if task is None:
        return {
            "content": [{"type": "text", "text": "Task not found."}],
            "is_error": True,
        }

    lease_until = (
        task.checkout_lease_until.isoformat() if task.checkout_lease_until else "-"
    )
    return {
        "content": [
            {
                "type": "text",
                "text": f"Renewed checkout on task '{task.title}' (lease until {lease_until}).",
            }
        ]
    }


@tool(
    "release_task_checkout",
    "Release a task checkout lease",
    {"task_id": str, "agent_session_id": str},
)
async def release_task_checkout(args: dict[str, Any]) -> dict[str, Any]:
    """Release a checkout lease."""
    from pms.exceptions import TaskCheckoutConflict
    from pms.repositories.task_repository import TaskRepository

    task_service = _get_task_service()
    repo = TaskRepository(
        task_service.db,
        task_service.events,
        task_service.revisions,
        task_service.metrics,
    )

    try:
        task = await repo.release_checkout(args["task_id"], args["agent_session_id"])
    except TaskCheckoutConflict as exc:
        return {
            "content": [{"type": "text", "text": str(exc)}],
            "is_error": True,
        }

    if task is None:
        return {
            "content": [{"type": "text", "text": "Task not found."}],
            "is_error": True,
        }

    return {
        "content": [
            {
                "type": "text",
                "text": f"Released checkout for task '{task.title}'.",
            }
        ]
    }


@tool(
    "assign_workflow",
    "Assign a workflow to a task, goal, or objective",
    {
        "entity_id": str,
        "workflow_name": str,
        "initial_state": str,
        "entity_type": str,
    },
)
async def assign_workflow(args: dict[str, Any]) -> dict[str, Any]:
    """Assign a workflow to an entity."""
    from pms.workflows.transition import assign_workflow as assign_workflow_helper

    task_service = _get_task_service()

    entity, workflow, label, error = await assign_workflow_helper(
        db=task_service.db,
        event_store=task_service.events,
        revision_store=task_service.revisions,
        metrics=task_service.metrics,
        entity_type=args.get("entity_type", "task"),
        entity_id=args["entity_id"],
        workflow_name=args["workflow_name"],
        initial_state=args["initial_state"],
    )
    if error:
        return {
            "content": [{"type": "text", "text": error}],
            "is_error": True,
        }

    assert entity is not None
    assert workflow is not None
    return {
        "content": [
            {
                "type": "text",
                "text": (
                    f"Assigned workflow '{workflow.name}' to {label} "
                    f"(state: {entity.current_state})."
                ),
            }
        ]
    }


@tool(
    "transition_workflow",
    "Transition a task, goal, or objective to a new workflow state",
    {
        "entity_id": str,
        "to_state": str,
        "triggered_by": str,
        "reason": str,
        "approved_by": str,
        "entity_type": str,
    },
)
async def transition_workflow(args: dict[str, Any]) -> dict[str, Any]:
    """Transition workflow state for an entity."""
    from pms.repositories import StateTransitionRepository
    from pms.services.evidence_gate_service import EvidenceGateService
    from pms.services.label_service import LabelService
    from pms.workflows.transition import (
        execute_workflow_transition,
        load_workflow_entity,
    )

    task_service = _get_task_service()
    state_repo = StateTransitionRepository(task_service.db)
    label_service = LabelService(task_service.db, task_service.metrics)
    evidence_gate_service = EvidenceGateService(task_service.db, task_service.metrics)

    (
        entity,
        repo,
        workflow,
        update_event,
        label,
        error,
    ) = await load_workflow_entity(
        db=task_service.db,
        event_store=task_service.events,
        revision_store=task_service.revisions,
        metrics=task_service.metrics,
        entity_type=args.get("entity_type", "task"),
        entity_id=args["entity_id"],
    )
    if error:
        return {
            "content": [{"type": "text", "text": error}],
            "is_error": True,
        }

    assert entity is not None
    assert repo is not None
    assert workflow is not None
    assert update_event is not None

    transition, error, needs_approval = await execute_workflow_transition(
        entity=entity,
        repo=repo,
        workflow=workflow,
        update_event=update_event,
        entity_type=args.get("entity_type", "task"),
        to_state=args["to_state"],
        triggered_by=args["triggered_by"],
        reason=args.get("reason"),
        approved_by=args.get("approved_by"),
        state_repo=state_repo,
        label_service=label_service,
        evidence_gate_service=evidence_gate_service,
    )
    if error:
        message = f"Invalid transition: {error}"
        if needs_approval:
            message = f"{message} (provide approved_by)"
        return {
            "content": [{"type": "text", "text": message}],
            "is_error": True,
        }

    assert transition is not None
    return {
        "content": [
            {
                "type": "text",
                "text": (
                    f"Transitioned {label} {entity.id}: "
                    f"{transition.from_state} -> {transition.to_state}"
                ),
            }
        ]
    }


@tool(
    "delete_task",
    "Delete a task",
    {"task_id": str},
)
async def delete_task(args: dict[str, Any]) -> dict[str, Any]:
    """Delete a task."""
    task_service = _get_task_service()

    task = await task_service.get_task(args["task_id"])
    if task is None:
        return {
            "content": [
                {"type": "text", "text": f"Task '{args['task_id']}' not found."}
            ],
            "is_error": True,
        }

    # Cancel instead of hard delete
    cancelled = await task_service.cancel_task(task.id)

    if cancelled is None:
        return {
            "content": [{"type": "text", "text": "Delete failed."}],
            "is_error": True,
        }

    return {"content": [{"type": "text", "text": f"Deleted task '{cancelled.title}'."}]}


@tool(
    "block_task",
    "Mark a task as blocked with a reason",
    {"task_id": str, "reason": str},
)
async def block_task(args: dict[str, Any]) -> dict[str, Any]:
    """Block a task."""
    task_service = _get_task_service()

    task = await task_service.block_task(args["task_id"], reason=args.get("reason"))
    if task is None:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Task '{args['task_id']}' not found.",
                }
            ],
            "is_error": True,
        }

    reason_text = f" Reason: {args['reason']}" if args.get("reason") else ""

    return {
        "content": [
            {
                "type": "text",
                "text": f"Blocked task '{task.title}'.{reason_text}",
            }
        ]
    }


@tool(
    "unblock_task",
    "Unblock a task (change status back to todo)",
    {"task_id": str},
)
async def unblock_task(args: dict[str, Any]) -> dict[str, Any]:
    """Unblock a task."""
    task_service = _get_task_service()

    task = await task_service.unblock_task(args["task_id"])
    if task is None:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Task '{args['task_id']}' not found.",
                }
            ],
            "is_error": True,
        }

    return {
        "content": [
            {
                "type": "text",
                "text": f"Unblocked task '{task.title}'. Status is now: {task.status.value}",
            }
        ]
    }


@tool(
    "add_task_dependency",
    "Add a dependency: task_id depends on depends_on_id (must complete first)",
    {"task_id": str, "depends_on_id": str, "dependency_type": str},
)
async def add_task_dependency(args: dict[str, Any]) -> dict[str, Any]:
    """Add task dependency."""
    from pms.models import DependencyType

    task_service = _get_task_service()

    dependency_type = DependencyType.BLOCKS
    if args.get("dependency_type"):
        try:
            dependency_type = DependencyType(str(args["dependency_type"]).lower())
        except ValueError:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "Invalid dependency_type. Use blocks or relates.",
                    }
                ],
                "is_error": True,
            }

    dep = await task_service.add_dependency(
        args["task_id"],
        args["depends_on_id"],
        dependency_type=dependency_type,
    )
    if dep is None:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Could not add dependency. Check that both tasks exist.",
                }
            ],
            "is_error": True,
        }

    return {
        "content": [
            {
                "type": "text",
                "text": f"Added dependency: task {args['task_id']} now depends on task {args['depends_on_id']}",
            }
        ]
    }


@tool(
    "get_task_tree",
    "Get hierarchical task tree for a project",
    {"project": str},
)
async def get_task_tree(args: dict[str, Any]) -> dict[str, Any]:
    """Get task tree."""
    project_service = _get_project_service()
    task_service = _get_task_service()

    # Find project
    project = await project_service.get_project_by_name(args["project"])
    if project is None:
        project = await project_service.get_project(args["project"])

    if project is None:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Project '{args['project']}' not found.",
                }
            ],
            "is_error": True,
        }

    trees = await task_service.get_task_tree(project.id)

    if not trees:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"No tasks in project '{project.name}'.",
                }
            ]
        }

    lines = [f"Task Tree for '{project.name}':"]

    def render_tree(tree: Any, indent: int = 0) -> None:
        prefix = "  " * indent + ("└─ " if indent > 0 else "")
        status_icon = {
            "todo": "[ ]",
            "in_progress": "[~]",
            "done": "[x]",
            "blocked": "[!]",
            "cancelled": "[-]",
        }
        icon = status_icon.get(tree.task.status.value, "[ ]")
        lines.append(f"{prefix}{icon} {tree.task.title}")
        for child in tree.children:
            render_tree(child, indent + 1)

    for tree in trees:
        render_tree(tree)

    return {
        "content": [
            {
                "type": "text",
                "text": "\n".join(lines),
            }
        ]
    }


@tool(
    "find_duplicate_tasks",
    "Find duplicate tasks by normalized title",
    {
        "project": str,
        "status": str,
        "include_terminal": bool,
        "min_count": int,
        "limit": int,
        "offset": int,
    },
)
async def find_duplicate_tasks(args: dict[str, Any]) -> dict[str, Any]:
    """Find duplicate tasks by normalized title."""
    from pms.models import TaskStatus

    project_service = _get_project_service()
    task_service = _get_task_service()

    project_id = None
    if args.get("project"):
        project = await project_service.get_project_by_name(args["project"])
        if project is None:
            project = await project_service.get_project(args["project"])
        if project is None:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Project '{args['project']}' not found.",
                    }
                ],
                "is_error": True,
            }
        project_id = project.id

    statuses = None
    if args.get("status"):
        status_items = [s.strip() for s in args["status"].split(",") if s.strip()]
        try:
            statuses = [TaskStatus(item.lower()) for item in status_items]
        except ValueError:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "Invalid status. Use: todo, in_progress, blocked, in_review, done, cancelled",
                    }
                ],
                "is_error": True,
            }

    min_count = int(args.get("min_count", 2))
    limit = int(args.get("limit", 100))
    offset = int(args.get("offset", 0))

    result = await task_service.find_duplicate_tasks(
        project_id=project_id,
        statuses=statuses,
        include_terminal=bool(args.get("include_terminal", False)),
        min_count=min_count,
        limit=limit,
        offset=offset,
    )

    if not result.items:
        return {"content": [{"type": "text", "text": "No duplicate tasks found."}]}

    lines = [
        f"Found {result.total_count} duplicate group(s):",
    ]
    for group in result.items:
        lines.append(f"- {group.normalized_title} ({group.count} tasks)")
        if group.suggested_primary_id:
            reason = group.suggested_primary_reason or "suggested by score"
            lines.append(
                f"  Suggested primary: {group.suggested_primary_id} ({reason})"
            )
        for task_obj in group.tasks:
            lines.append(
                f"  - {task_obj.title} ({task_obj.status.value}) ID: {task_obj.id}"
            )

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "preview_merge_duplicate_tasks",
    "Preview duplicate task merges with conflicts and warnings",
    {"primary_task_id": str, "duplicate_task_ids": str},
)
async def preview_merge_duplicate_tasks(args: dict[str, Any]) -> dict[str, Any]:
    """Preview duplicate task merges."""
    task_service = _get_task_service()

    if not args.get("duplicate_task_ids"):
        return {
            "content": [{"type": "text", "text": "duplicate_task_ids is required."}],
            "is_error": True,
        }

    duplicate_ids = [
        item.strip()
        for item in str(args["duplicate_task_ids"]).split(",")
        if item.strip()
    ]
    preview = await task_service.preview_merge_duplicate_tasks(
        primary_task_id=args["primary_task_id"],
        duplicate_task_ids=duplicate_ids,
    )
    if preview is None:
        return {
            "content": [{"type": "text", "text": "Primary task not found."}],
            "is_error": True,
        }

    lines = [
        "Duplicate Merge Preview",
        f"Primary: {preview.primary_task.title} ({preview.primary_task.id})",
    ]

    if preview.suggested_primary_id and (
        preview.suggested_primary_id != preview.primary_task.id
    ):
        lines.append(
            "Suggested primary: "
            f"{preview.suggested_primary_id} ({preview.suggested_primary_reason})"
        )

    if preview.warnings:
        lines.append("Warnings:")
        for warning in preview.warnings:
            lines.append(f"- {warning}")

    if preview.missing_ids:
        lines.append("Missing IDs:")
        for missing_id in preview.missing_ids:
            lines.append(f"- {missing_id}")

    if preview.duplicates:
        lines.append("Duplicates:")
        for item in preview.duplicates:
            status = item.task.status.value
            linked = "linked" if item.already_linked else "unlinked"
            lines.append(f"- {item.task.title} ({status}) {item.task.id} [{linked}]")
            for conflict in item.conflicts:
                lines.append(
                    f"  * {conflict.field}: "
                    f"{conflict.primary_value} != {conflict.duplicate_value}"
                )

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "merge_duplicate_tasks",
    "Merge duplicate tasks by linking them to a primary task",
    {
        "primary_task_id": str,
        "duplicate_task_ids": str,
        "cancel_duplicates": bool,
    },
)
async def merge_duplicate_tasks(args: dict[str, Any]) -> dict[str, Any]:
    """Merge duplicate tasks by linking to a primary task."""
    task_service = _get_task_service()

    if not args.get("duplicate_task_ids"):
        return {
            "content": [{"type": "text", "text": "duplicate_task_ids is required."}],
            "is_error": True,
        }

    duplicate_ids = [
        item.strip() for item in args["duplicate_task_ids"].split(",") if item.strip()
    ]

    result = await task_service.merge_duplicate_tasks(
        primary_task_id=args["primary_task_id"],
        duplicate_task_ids=duplicate_ids,
        cancel_duplicates=bool(args.get("cancel_duplicates", True)),
    )

    if result is None:
        return {
            "content": [{"type": "text", "text": "Primary task not found."}],
            "is_error": True,
        }

    lines = [
        f"Primary task: {result.primary_task.title} (ID: {result.primary_task.id})",
        f"Links added: {result.links_added}",
        f"Duplicates cancelled: {result.duplicates_cancelled}",
    ]
    if result.duplicate_tasks:
        lines.append("Duplicates:")
        for task_obj in result.duplicate_tasks:
            lines.append(
                f"- {task_obj.title} ({task_obj.status.value}) ID: {task_obj.id}"
            )

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "get_task_proof_bundle",
    "Get a proof bundle for a task with evidence and test runs",
    {
        "task_id": str,
        "include_output": bool,
        "include_logs": bool,
        "include_artifacts": bool,
        "format": str,
    },
)
async def get_task_proof_bundle(args: dict[str, Any]) -> dict[str, Any]:
    """Get a proof bundle for a task."""
    import json

    from pms.services.proof_bundle_service import ProofBundleService
    from pms.services.task_evidence_service import TaskEvidenceService

    task_service = _get_task_service()
    test_run_service = _get_test_run_service()
    evidence_service = TaskEvidenceService(task_service.db, task_service.metrics)
    proof_bundle_service = ProofBundleService(
        task_service=task_service,
        evidence_service=evidence_service,
        test_run_service=test_run_service,
    )

    bundle = await proof_bundle_service.build_task_bundle(
        task_id=args["task_id"],
        include_output=bool(args.get("include_output", False)),
        include_logs=bool(args.get("include_logs", False)),
        include_artifacts=bool(args.get("include_artifacts", False)),
    )
    if bundle is None:
        return {
            "content": [{"type": "text", "text": "Task not found."}],
            "is_error": True,
        }

    output_format = str(args.get("format", "text")).lower()
    match output_format:
        case "json":
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(bundle.to_dict(), default=str),
                    }
                ]
            }

    summary = bundle.summary
    lines = [
        "Proof Bundle",
        f"Task: {bundle.task.title} ({bundle.task.id})",
        f"Generated: {bundle.generated_at.isoformat()}",
        (f"Evidence: total {summary.evidence_total} | types {summary.evidence_types}"),
        (f"Test runs: {summary.successful_test_runs}/{summary.test_runs} successful"),
        f"Log bytes: {summary.log_bytes_total}",
        f"Artifact bytes: {summary.artifact_bytes_total}",
    ]
    if bundle.evidence:
        lines.append("Evidence items:")
        for item in bundle.evidence:
            details = item.evidence.description or "-"
            if item.evidence.evidence_type == "test_run" and item.test_run:
                status = "passed" if item.test_run.success else "failed"
                details = f"{status} ({item.test_run.command or 'test run'})"
            lines.append(
                f"- {item.evidence.evidence_type} {item.evidence.reference} | {details}"
            )

    if bundle.test_runs:
        lines.append("Test runs:")
        for run in bundle.test_runs:
            status = "passed" if run.success else "failed"
            lines.append(f"- {run.id} ({status}) {run.command or 'test run'}")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "create_custom_field",
    "Create a custom field definition",
    {
        "name": str,
        "entity_type": str,
        "field_type": str,
        "description": str,
        "options": str,
        "is_required": bool,
    },
)
async def create_custom_field(args: dict[str, Any]) -> dict[str, Any]:
    """Create a custom field definition."""
    from pms.models.custom_field import CustomFieldType

    service = _get_custom_field_service()
    field_type = args.get("field_type") or "text"
    try:
        parsed_type = CustomFieldType(field_type)
    except ValueError:
        allowed = ", ".join(ft.value for ft in CustomFieldType)
        return {
            "content": [
                {"type": "text", "text": f"Invalid field_type. Use: {allowed}"}
            ],
            "is_error": True,
        }

    options = []
    if args.get("options"):
        options = [opt.strip() for opt in args["options"].split(",") if opt.strip()]

    try:
        definition = await service.create_definition(
            name=args["name"],
            entity_type=args["entity_type"],
            field_type=parsed_type,
            description=args.get("description"),
            options=options,
            is_required=bool(args.get("is_required", False)),
        )
    except ValueError as exc:
        return {"content": [{"type": "text", "text": str(exc)}], "is_error": True}

    return {
        "content": [
            {
                "type": "text",
                "text": (
                    f"Created custom field '{definition.name}' "
                    f"({definition.entity_type}) ID: {definition.id}"
                ),
            }
        ]
    }


@tool(
    "list_custom_fields",
    "List custom field definitions",
    {"entity_type": str, "include_archived": bool},
)
async def list_custom_fields(args: dict[str, Any]) -> dict[str, Any]:
    """List custom field definitions."""
    service = _get_custom_field_service()
    definitions = await service.list_definitions(
        entity_type=args.get("entity_type"),
        include_archived=bool(args.get("include_archived", False)),
    )
    if not definitions:
        return {"content": [{"type": "text", "text": "No custom fields found."}]}
    lines = [f"Found {len(definitions)} custom field(s):"]
    for definition in definitions:
        lines.append(
            f"- {definition.name} ({definition.entity_type}) "
            f"[{definition.field_type.value}] ID: {definition.id}"
        )
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "get_custom_field",
    "Get details for a custom field definition",
    {"field_ref": str, "entity_type": str},
)
async def get_custom_field(args: dict[str, Any]) -> dict[str, Any]:
    """Get custom field details."""
    service = _get_custom_field_service()
    definition = await service.get_definition(args["field_ref"], include_archived=True)
    if definition is None and args.get("entity_type"):
        definition = await service.get_definition_by_name(
            args["field_ref"], args["entity_type"], include_archived=True
        )
    if definition is None:
        return {
            "content": [{"type": "text", "text": "Custom field not found."}],
            "is_error": True,
        }
    payload = definition.to_dict()
    payload["field_type"] = definition.field_type.value
    return {"content": [{"type": "text", "text": json.dumps(payload, default=str)}]}


@tool(
    "update_custom_field",
    "Update a custom field definition",
    {
        "field_id": str,
        "name": str,
        "field_type": str,
        "description": str,
        "options": str,
        "is_required": bool,
    },
)
async def update_custom_field(args: dict[str, Any]) -> dict[str, Any]:
    """Update a custom field definition."""
    from pms.models.custom_field import CustomFieldType

    service = _get_custom_field_service()
    parsed_type = None
    if args.get("field_type"):
        try:
            parsed_type = CustomFieldType(args["field_type"])
        except ValueError:
            allowed = ", ".join(ft.value for ft in CustomFieldType)
            return {
                "content": [
                    {"type": "text", "text": f"Invalid field_type. Use: {allowed}"}
                ],
                "is_error": True,
            }

    options = None
    if args.get("options"):
        options = [opt.strip() for opt in args["options"].split(",") if opt.strip()]

    definition = await service.update_definition(
        args["field_id"],
        name=args.get("name"),
        description=args.get("description"),
        field_type=parsed_type,
        options=options,
        is_required=args.get("is_required"),
    )
    if definition is None:
        return {
            "content": [{"type": "text", "text": "Custom field not found."}],
            "is_error": True,
        }
    return {
        "content": [
            {
                "type": "text",
                "text": f"Updated custom field '{definition.name}' ({definition.id})",
            }
        ]
    }


@tool(
    "delete_custom_field",
    "Archive a custom field definition",
    {"field_id": str},
)
async def delete_custom_field(args: dict[str, Any]) -> dict[str, Any]:
    """Archive a custom field definition."""
    service = _get_custom_field_service()
    await service.delete_definition(args["field_id"])
    return {
        "content": [
            {
                "type": "text",
                "text": f"Archived custom field {args['field_id']}",
            }
        ]
    }


@tool(
    "restore_custom_field",
    "Restore a custom field definition",
    {"field_id": str},
)
async def restore_custom_field(args: dict[str, Any]) -> dict[str, Any]:
    """Restore a custom field definition."""
    service = _get_custom_field_service()
    definition = await service.restore_definition(args["field_id"])
    if definition is None:
        return {
            "content": [{"type": "text", "text": "Custom field not found."}],
            "is_error": True,
        }
    return {
        "content": [
            {
                "type": "text",
                "text": f"Restored custom field '{definition.name}' ({definition.id})",
            }
        ]
    }


@tool(
    "set_custom_field_value",
    "Set a custom field value for an entity",
    {
        "field_ref": str,
        "entity_type": str,
        "entity_id": str,
        "value": str,
        "value_json": str,
        "created_by": str,
        "source": str,
    },
)
async def set_custom_field_value(args: dict[str, Any]) -> dict[str, Any]:
    """Set a custom field value for an entity."""
    service = _get_custom_field_service()

    if args.get("value") and args.get("value_json"):
        return {
            "content": [{"type": "text", "text": "Use value or value_json, not both."}],
            "is_error": True,
        }

    value: Any = args.get("value")
    if args.get("value_json"):
        try:
            value = json.loads(args["value_json"])
        except json.JSONDecodeError:
            return {
                "content": [{"type": "text", "text": "Invalid JSON in value_json."}],
                "is_error": True,
            }

    try:
        item = await service.set_value(
            args["field_ref"],
            entity_type=args["entity_type"],
            entity_id=args["entity_id"],
            value=value,
            created_by=args.get("created_by"),
            source=args.get("source"),
        )
    except ValueError as exc:
        return {"content": [{"type": "text", "text": str(exc)}], "is_error": True}

    return {
        "content": [
            {
                "type": "text",
                "text": (
                    f"Set {item.definition.name} on "
                    f"{item.value.entity_type} {item.value.entity_id} "
                    f"(value id {item.value.id})"
                ),
            }
        ]
    }


@tool(
    "list_custom_field_values",
    "List custom field values for an entity",
    {
        "entity_type": str,
        "entity_id": str,
        "include_history": bool,
        "limit": int,
        "offset": int,
        "format": str,
    },
)
async def list_custom_field_values(args: dict[str, Any]) -> dict[str, Any]:
    """List custom field values for an entity."""
    service = _get_custom_field_service()
    page = await service.list_values_for_entity(
        entity_type=args["entity_type"],
        entity_id=args["entity_id"],
        include_history=bool(args.get("include_history", False)),
        limit=int(args.get("limit", 100)),
        offset=int(args.get("offset", 0)),
    )
    if not page.items:
        return {"content": [{"type": "text", "text": "No custom field values found."}]}

    output_format = str(args.get("format", "text")).lower()
    if output_format == "json":
        payload = {
            "items": [item.to_dict() for item in page.items],
            "total_count": page.total_count,
            "offset": page.offset,
            "limit": page.limit,
        }
        return {"content": [{"type": "text", "text": json.dumps(payload, default=str)}]}

    lines = [f"Found {page.total_count} custom field value(s):"]
    for item in page.items:
        field_name = item.definition.name if item.definition else item.value.field_id
        lines.append(f"- {field_name}: {item.value.value} (id {item.value.id})")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "list_custom_field_values_for_field",
    "List custom field values for a definition",
    {"field_id": str, "limit": int, "offset": int, "format": str},
)
async def list_custom_field_values_for_field(args: dict[str, Any]) -> dict[str, Any]:
    """List custom field values for a definition."""
    service = _get_custom_field_service()
    page = await service.list_values_for_field(
        args["field_id"],
        limit=int(args.get("limit", 100)),
        offset=int(args.get("offset", 0)),
    )
    if not page.items:
        return {"content": [{"type": "text", "text": "No custom field values found."}]}

    output_format = str(args.get("format", "text")).lower()
    if output_format == "json":
        payload = {
            "items": [item.to_dict() for item in page.items],
            "total_count": page.total_count,
            "offset": page.offset,
            "limit": page.limit,
        }
        return {"content": [{"type": "text", "text": json.dumps(payload, default=str)}]}

    lines = [f"Found {page.total_count} custom field value(s):"]
    for item in page.items:
        lines.append(
            f"- {item.value.entity_type} {item.value.entity_id}: {item.value.value}"
        )
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "add_comment",
    "Add a comment to an entity",
    {
        "entity_type": str,
        "entity_id": str,
        "body": str,
        "created_by": str,
        "mentions": str,
        "metadata_json": str,
        "watch": bool,
    },
)
async def add_comment(args: dict[str, Any]) -> dict[str, Any]:
    """Add a comment to an entity."""
    service = _get_comment_service()
    mentions: list[str] = []
    if args.get("mentions"):
        mentions = [
            item.strip() for item in args["mentions"].split(",") if item.strip()
        ]

    metadata = None
    if args.get("metadata_json"):
        try:
            metadata = json.loads(args["metadata_json"])
        except json.JSONDecodeError:
            return {
                "content": [{"type": "text", "text": "Invalid JSON in metadata_json."}],
                "is_error": True,
            }

    try:
        item = await service.add_comment(
            entity_type=args["entity_type"],
            entity_id=args["entity_id"],
            body=args["body"],
            created_by=args.get("created_by", "system"),
            mentions=mentions,
            metadata=metadata,
            watch=bool(args.get("watch", False)),
        )
    except ValueError as exc:
        return {"content": [{"type": "text", "text": str(exc)}], "is_error": True}

    return {
        "content": [
            {
                "type": "text",
                "text": f"Added comment {item.comment.id} to {item.comment.entity_type} {item.comment.entity_id}",
            }
        ]
    }


@tool(
    "list_comments",
    "List comments for an entity",
    {
        "entity_type": str,
        "entity_id": str,
        "include_archived": bool,
        "limit": int,
        "offset": int,
        "format": str,
    },
)
async def list_comments(args: dict[str, Any]) -> dict[str, Any]:
    """List comments for an entity."""
    service = _get_comment_service()
    try:
        page = await service.list_comments(
            entity_type=args["entity_type"],
            entity_id=args["entity_id"],
            include_archived=bool(args.get("include_archived", False)),
            limit=int(args.get("limit", 100)),
            offset=int(args.get("offset", 0)),
        )
    except ValueError as exc:
        return {"content": [{"type": "text", "text": str(exc)}], "is_error": True}

    if not page.items:
        return {"content": [{"type": "text", "text": "No comments found."}]}

    output_format = str(args.get("format", "text")).lower()
    if output_format == "json":
        payload = {
            "items": [item.to_dict() for item in page.items],
            **_page_payload(page.total_count, page.limit, page.offset),
        }
        return {"content": [{"type": "text", "text": json.dumps(payload, default=str)}]}

    lines = [f"Found {page.total_count} comment(s):"]
    for item in page.items:
        comment = item.comment
        mentions = ", ".join(m.mention for m in item.mentions) or "-"
        lines.append(
            f"- {comment.id} by {comment.created_by} ({comment.created_at}): {comment.body}"
        )
        lines.append(f"  mentions: {mentions}")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "get_comment",
    "Get a comment by ID",
    {"comment_id": str},
)
async def get_comment(args: dict[str, Any]) -> dict[str, Any]:
    """Get a comment by ID."""
    service = _get_comment_service()
    item = await service.get_comment(args["comment_id"], include_archived=True)
    if item is None:
        return {
            "content": [{"type": "text", "text": "Comment not found."}],
            "is_error": True,
        }
    return {
        "content": [{"type": "text", "text": json.dumps(item.to_dict(), default=str)}]
    }


@tool(
    "delete_comment",
    "Archive a comment by ID",
    {"comment_id": str},
)
async def delete_comment(args: dict[str, Any]) -> dict[str, Any]:
    """Archive a comment."""
    service = _get_comment_service()
    deleted = await service.delete_comment(args["comment_id"])
    if not deleted:
        return {
            "content": [{"type": "text", "text": "Comment not found."}],
            "is_error": True,
        }
    return {
        "content": [
            {"type": "text", "text": f"Archived comment {args['comment_id']}"},
        ]
    }


@tool(
    "restore_comment",
    "Restore a comment by ID",
    {"comment_id": str},
)
async def restore_comment(args: dict[str, Any]) -> dict[str, Any]:
    """Restore a comment."""
    service = _get_comment_service()
    comment = await service.restore_comment(args["comment_id"])
    if comment is None:
        return {
            "content": [{"type": "text", "text": "Comment not found."}],
            "is_error": True,
        }
    return {
        "content": [
            {"type": "text", "text": f"Restored comment {comment.id}"},
        ]
    }


@tool(
    "add_watcher",
    "Add a watcher for an entity",
    {"entity_type": str, "entity_id": str, "watcher": str},
)
async def add_watcher(args: dict[str, Any]) -> dict[str, Any]:
    """Add a watcher for an entity."""
    service = _get_comment_service()
    try:
        watcher = await service.add_watcher(
            entity_type=args["entity_type"],
            entity_id=args["entity_id"],
            watcher=args["watcher"],
        )
    except ValueError as exc:
        return {"content": [{"type": "text", "text": str(exc)}], "is_error": True}
    return {
        "content": [
            {
                "type": "text",
                "text": (
                    f"Added watcher {watcher.watcher} "
                    f"({watcher.id}) for {watcher.entity_type} {watcher.entity_id}"
                ),
            }
        ]
    }


@tool(
    "list_watchers",
    "List watchers for an entity",
    {
        "entity_type": str,
        "entity_id": str,
        "include_archived": bool,
        "limit": int,
        "offset": int,
        "format": str,
    },
)
async def list_watchers(args: dict[str, Any]) -> dict[str, Any]:
    """List watchers for an entity."""
    service = _get_comment_service()
    try:
        page = await service.list_watchers(
            entity_type=args["entity_type"],
            entity_id=args["entity_id"],
            include_archived=bool(args.get("include_archived", False)),
            limit=int(args.get("limit", 100)),
            offset=int(args.get("offset", 0)),
        )
    except ValueError as exc:
        return {"content": [{"type": "text", "text": str(exc)}], "is_error": True}

    if not page.items:
        return {"content": [{"type": "text", "text": "No watchers found."}]}

    output_format = str(args.get("format", "text")).lower()
    if output_format == "json":
        payload = {
            "items": [item.to_dict() for item in page.items],
            **_page_payload(page.total_count, page.limit, page.offset),
        }
        return {"content": [{"type": "text", "text": json.dumps(payload, default=str)}]}

    lines = [f"Found {page.total_count} watcher(s):"]
    for item in page.items:
        lines.append(
            f"- {item.watcher} ({item.id}) [{item.entity_type} {item.entity_id}]"
        )
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "remove_watcher",
    "Remove a watcher from an entity",
    {"entity_type": str, "entity_id": str, "watcher": str},
)
async def remove_watcher(args: dict[str, Any]) -> dict[str, Any]:
    """Remove a watcher from an entity."""
    service = _get_comment_service()
    try:
        removed = await service.remove_watcher(
            args["entity_type"], args["entity_id"], args["watcher"]
        )
    except ValueError as exc:
        return {"content": [{"type": "text", "text": str(exc)}], "is_error": True}
    if not removed:
        return {
            "content": [{"type": "text", "text": "Watcher not found."}],
            "is_error": True,
        }
    return {
        "content": [
            {"type": "text", "text": f"Removed watcher {args['watcher']}"},
        ]
    }


@tool(
    "restore_watcher",
    "Restore a watcher subscription by ID",
    {"watcher_id": str},
)
async def restore_watcher(args: dict[str, Any]) -> dict[str, Any]:
    """Restore a watcher subscription."""
    service = _get_comment_service()
    watcher = await service.restore_watcher(args["watcher_id"])
    if watcher is None:
        return {
            "content": [{"type": "text", "text": "Watcher not found."}],
            "is_error": True,
        }
    return {
        "content": [
            {"type": "text", "text": f"Restored watcher {watcher.watcher}"},
        ]
    }


@tool(
    "create_automation_rule",
    "Create an automation rule",
    {
        "name": str,
        "event_pattern": str,
        "action_type": str,
        "action_payload_json": str,
        "description": str,
        "aggregate_type": str,
        "aggregate_id": str,
        "enabled": bool,
        "cooldown_seconds": float,
    },
)
async def create_automation_rule(args: dict[str, Any]) -> dict[str, Any]:
    """Create an automation rule."""
    from pms.models.automation_rule import AutomationActionType

    service = _get_automation_rule_service()
    payload = {}
    if args.get("action_payload_json"):
        try:
            payload = json.loads(args["action_payload_json"])
        except json.JSONDecodeError:
            return {
                "content": [
                    {"type": "text", "text": "Invalid JSON in action_payload_json."}
                ],
                "is_error": True,
            }
    try:
        action_type = AutomationActionType(args["action_type"])
    except ValueError:
        allowed = ", ".join(value.value for value in AutomationActionType)
        return {
            "content": [
                {"type": "text", "text": f"Invalid action_type. Use: {allowed}"}
            ],
            "is_error": True,
        }
    try:
        rule = await service.create_rule(
            name=args["name"],
            event_pattern=args["event_pattern"],
            action_type=action_type,
            action_payload=payload,
            description=args.get("description"),
            aggregate_type=args.get("aggregate_type"),
            aggregate_id=args.get("aggregate_id"),
            enabled=bool(args.get("enabled", True)),
            cooldown_seconds=float(args.get("cooldown_seconds", 0.0)),
        )
    except ValueError as exc:
        return {"content": [{"type": "text", "text": str(exc)}], "is_error": True}
    return {
        "content": [
            {"type": "text", "text": f"Created automation rule {rule.name} ({rule.id})"}
        ]
    }


@tool(
    "list_automation_rules",
    "List automation rules",
    {"include_archived": bool, "enabled": bool, "format": str},
)
async def list_automation_rules(args: dict[str, Any]) -> dict[str, Any]:
    """List automation rules."""
    service = _get_automation_rule_service()
    rules = await service.list_rules(
        include_archived=bool(args.get("include_archived", False)),
        enabled=args.get("enabled"),
    )
    if not rules:
        return {"content": [{"type": "text", "text": "No automation rules found."}]}

    output_format = str(args.get("format", "text")).lower()
    if output_format == "json":
        payload = {
            "items": [rule.to_dict() for rule in rules],
            "total_count": len(rules),
        }
        return {"content": [{"type": "text", "text": json.dumps(payload, default=str)}]}

    lines = [f"Found {len(rules)} automation rule(s):"]
    for rule in rules:
        status = "enabled" if rule.enabled else "disabled"
        lines.append(
            f"- {rule.name} ({rule.event_pattern}) [{rule.action_type.value}] {status}"
        )
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "get_automation_rule",
    "Get details for an automation rule",
    {"rule_ref": str},
)
async def get_automation_rule(args: dict[str, Any]) -> dict[str, Any]:
    """Get automation rule details."""
    service = _get_automation_rule_service()
    rule = await service.get_rule(args["rule_ref"], include_archived=True)
    if rule is None:
        return {
            "content": [{"type": "text", "text": "Automation rule not found."}],
            "is_error": True,
        }
    return {
        "content": [{"type": "text", "text": json.dumps(rule.to_dict(), default=str)}]
    }


@tool(
    "update_automation_rule",
    "Update an automation rule",
    {
        "rule_id": str,
        "name": str,
        "description": str,
        "event_pattern": str,
        "aggregate_type": str,
        "aggregate_id": str,
        "action_type": str,
        "action_payload_json": str,
        "enabled": bool,
        "cooldown_seconds": float,
    },
)
async def update_automation_rule(args: dict[str, Any]) -> dict[str, Any]:
    """Update an automation rule."""
    from pms.models.automation_rule import AutomationActionType

    service = _get_automation_rule_service()
    payload = None
    if args.get("action_payload_json"):
        try:
            payload = json.loads(args["action_payload_json"])
        except json.JSONDecodeError:
            return {
                "content": [
                    {"type": "text", "text": "Invalid JSON in action_payload_json."}
                ],
                "is_error": True,
            }
    action_type = None
    if args.get("action_type"):
        try:
            action_type = AutomationActionType(args["action_type"])
        except ValueError:
            allowed = ", ".join(value.value for value in AutomationActionType)
            return {
                "content": [
                    {"type": "text", "text": f"Invalid action_type. Use: {allowed}"}
                ],
                "is_error": True,
            }
    rule = await service.update_rule(
        args["rule_id"],
        name=args.get("name"),
        description=args.get("description"),
        event_pattern=args.get("event_pattern"),
        aggregate_type=args.get("aggregate_type"),
        aggregate_id=args.get("aggregate_id"),
        action_type=action_type,
        action_payload=payload,
        enabled=args.get("enabled"),
        cooldown_seconds=args.get("cooldown_seconds"),
    )
    if rule is None:
        return {
            "content": [{"type": "text", "text": "Automation rule not found."}],
            "is_error": True,
        }
    return {
        "content": [
            {"type": "text", "text": f"Updated automation rule {rule.name} ({rule.id})"}
        ]
    }


@tool(
    "delete_automation_rule",
    "Archive an automation rule",
    {"rule_id": str},
)
async def delete_automation_rule(args: dict[str, Any]) -> dict[str, Any]:
    """Archive an automation rule."""
    service = _get_automation_rule_service()
    deleted = await service.delete_rule(args["rule_id"])
    if not deleted:
        return {
            "content": [{"type": "text", "text": "Automation rule not found."}],
            "is_error": True,
        }
    return {
        "content": [
            {"type": "text", "text": f"Archived automation rule {args['rule_id']}"},
        ]
    }


@tool(
    "restore_automation_rule",
    "Restore an automation rule",
    {"rule_id": str},
)
async def restore_automation_rule(args: dict[str, Any]) -> dict[str, Any]:
    """Restore an automation rule."""
    service = _get_automation_rule_service()
    rule = await service.restore_rule(args["rule_id"])
    if rule is None:
        return {
            "content": [{"type": "text", "text": "Automation rule not found."}],
            "is_error": True,
        }
    return {
        "content": [
            {
                "type": "text",
                "text": f"Restored automation rule {rule.name} ({rule.id})",
            }
        ]
    }


@tool(
    "run_automation_rules",
    "Run automation rules for an event",
    {"event_id": str, "rule_id": str, "dry_run": bool},
)
async def run_automation_rules(args: dict[str, Any]) -> dict[str, Any]:
    """Run automation rules for an event."""
    service = _get_automation_rule_service()
    try:
        results = await service.run_for_event_id(
            args["event_id"],
            rule_id=args.get("rule_id"),
            dry_run=bool(args.get("dry_run", False)),
        )
    except ValueError as exc:
        return {"content": [{"type": "text", "text": str(exc)}], "is_error": True}

    if not results:
        return {"content": [{"type": "text", "text": "No automation rules matched."}]}

    lines = ["Automation run results:"]
    for result in results:
        lines.append(f"- {result.rule.name}: {result.run.status} ({result.run.id})")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "list_automation_rule_runs",
    "List automation rule runs",
    {"rule_id": str, "limit": int, "offset": int, "format": str},
)
async def list_automation_rule_runs(args: dict[str, Any]) -> dict[str, Any]:
    """List automation rule run history."""
    service = _get_automation_rule_service()
    page = await service.list_runs(
        args["rule_id"],
        limit=int(args.get("limit", 100)),
        offset=int(args.get("offset", 0)),
    )
    if not page.items:
        return {"content": [{"type": "text", "text": "No automation runs found."}]}

    output_format = str(args.get("format", "text")).lower()
    if output_format == "json":
        payload = {
            "items": [run.__dict__ for run in page.items],
            **_page_payload(page.total_count, page.limit, page.offset),
        }
        return {"content": [{"type": "text", "text": json.dumps(payload, default=str)}]}

    lines = [f"Found {page.total_count} automation run(s):"]
    for run in page.items:
        lines.append(f"- {run.id} {run.status} event {run.event_id or '-'}")
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "create_evidence_gate_rule",
    "Create an evidence gate rule for workflow transitions",
    {
        "workflow_id": str,
        "entity_type": str,
        "from_state": str,
        "to_state": str,
        "evidence_type": str,
        "min_count": int,
        "require_success": bool,
        "message": str,
    },
)
async def create_evidence_gate_rule(args: dict[str, Any]) -> dict[str, Any]:
    """Create an evidence gate rule."""
    from pms.services.evidence_gate_service import EvidenceGateService

    task_service = _get_task_service()
    service = EvidenceGateService(task_service.db, task_service.metrics)

    rule = await service.add_gate_rule(
        workflow_id=args["workflow_id"],
        entity_type=args.get("entity_type", "task"),
        from_state=args["from_state"],
        to_state=args["to_state"],
        evidence_type=args["evidence_type"],
        min_count=int(args.get("min_count", 1)),
        require_success=bool(args.get("require_success", False)),
        message=args.get("message"),
    )

    return {
        "content": [
            {
                "type": "text",
                "text": f"Created evidence gate rule {rule.id}",
            }
        ]
    }


@tool(
    "list_evidence_gate_rules",
    "List evidence gate rules for a workflow transition",
    {"workflow_id": str, "entity_type": str, "from_state": str, "to_state": str},
)
async def list_evidence_gate_rules(args: dict[str, Any]) -> dict[str, Any]:
    """List evidence gate rules."""
    from pms.services.evidence_gate_service import EvidenceGateService

    task_service = _get_task_service()
    service = EvidenceGateService(task_service.db, task_service.metrics)

    rules = await service.list_gate_rules(
        workflow_id=args["workflow_id"],
        entity_type=args.get("entity_type", "task"),
        from_state=args["from_state"],
        to_state=args["to_state"],
    )
    if not rules:
        return {"content": [{"type": "text", "text": "No evidence gate rules found."}]}

    lines = [f"Found {len(rules)} evidence gate rule(s):"]
    for rule in rules:
        success_flag = "require_success" if rule.require_success else "any"
        lines.append(
            f"- {rule.id} {rule.evidence_type} min {rule.min_count} ({success_flag})"
        )
        if rule.message:
            lines.append(f"  message: {rule.message}")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "delete_evidence_gate_rule",
    "Delete an evidence gate rule by ID",
    {"rule_id": str},
)
async def delete_evidence_gate_rule(args: dict[str, Any]) -> dict[str, Any]:
    """Delete an evidence gate rule."""
    from pms.services.evidence_gate_service import EvidenceGateService

    task_service = _get_task_service()
    service = EvidenceGateService(task_service.db, task_service.metrics)

    deleted = await service.remove_gate_rule(args["rule_id"])
    if not deleted:
        return {
            "content": [{"type": "text", "text": "Evidence gate rule not found."}],
            "is_error": True,
        }

    return {
        "content": [
            {
                "type": "text",
                "text": f"Deleted evidence gate rule {args['rule_id']}",
            }
        ]
    }


@tool(
    "create_test_run",
    "Create a test run record with output, logs, and artifacts",
    {
        "run_id": str,
        "server_id": str,
        "project_id": str,
        "success": str,
        "exit_code": int,
        "duration_seconds": float,
        "started_at": str,
        "finished_at": str,
        "stdout": str,
        "stderr": str,
        "logs": str,
        "artifacts": str,
        "config": str,
        "command": str,
        "runner": str,
        "plan_id": str,
        "task_ids": str,
    },
)
async def create_test_run(args: dict[str, Any]) -> dict[str, Any]:
    """Create a test run record."""
    import json
    from datetime import UTC, datetime

    from pms.models.base import generate_id

    service = _get_test_run_service()

    def parse_dt(value: Any, label: str) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            parsed = value
        else:
            text = str(value).strip()
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            try:
                parsed = datetime.fromisoformat(text)
            except ValueError:
                raise ValueError(f"{label} must be an ISO-8601 timestamp.") from None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    def parse_json_object(value: Any, label: str) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        text = str(value).strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{label} must be valid JSON.") from exc
        if not isinstance(parsed, dict):
            raise ValueError(f"{label} must be a JSON object.")
        return parsed

    run_id = args.get("run_id") or generate_id()
    server_id = args.get("server_id")
    if not server_id:
        return {
            "content": [{"type": "text", "text": "server_id is required."}],
            "is_error": True,
        }

    success_raw = args.get("success")
    if isinstance(success_raw, bool):
        success = success_raw
    elif success_raw is None:
        return {
            "content": [{"type": "text", "text": "success is required."}],
            "is_error": True,
        }
    else:
        value = str(success_raw).strip().lower()
        if value in {"passed", "true", "yes"}:
            success = True
        elif value in {"failed", "false", "no"}:
            success = False
        else:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "Invalid success value. Use passed/failed or true/false.",
                    }
                ],
                "is_error": True,
            }

    try:
        started_at = parse_dt(args.get("started_at"), "started_at")
        finished_at = parse_dt(args.get("finished_at"), "finished_at")
    except ValueError as exc:
        return {
            "content": [{"type": "text", "text": str(exc)}],
            "is_error": True,
        }

    if started_at is None or finished_at is None:
        return {
            "content": [
                {"type": "text", "text": "started_at and finished_at are required."}
            ],
            "is_error": True,
        }

    duration_seconds = args.get("duration_seconds")
    if duration_seconds is None:
        duration_seconds = max(0.0, (finished_at - started_at).total_seconds())
    else:
        duration_seconds = float(duration_seconds)

    raw_task_ids = args.get("task_ids")
    if isinstance(raw_task_ids, (list, tuple)):
        task_ids = [str(item).strip() for item in raw_task_ids if str(item).strip()]
    else:
        task_ids = _parse_csv_args(raw_task_ids)

    try:
        config = parse_json_object(args.get("config"), "config")
        logs = parse_json_object(args.get("logs"), "logs")
        artifacts = parse_json_object(args.get("artifacts"), "artifacts")
    except ValueError as exc:
        return {
            "content": [{"type": "text", "text": str(exc)}],
            "is_error": True,
        }

    if args.get("command") is not None:
        config["command"] = args.get("command")
    if args.get("runner") is not None:
        config["runner"] = args.get("runner")
    if args.get("plan_id") is not None:
        config["plan_id"] = args.get("plan_id")
    if task_ids:
        config["task_ids"] = task_ids

    try:
        record = await service.create_test_run(
            run_id=run_id,
            server_id=server_id,
            project_id=args.get("project_id"),
            config=config,
            success=success,
            exit_code=args.get("exit_code"),
            stdout=args.get("stdout"),
            stderr=args.get("stderr"),
            duration_seconds=duration_seconds,
            started_at=started_at,
            finished_at=finished_at,
            logs=logs,
            artifacts=artifacts,
        )
    except ValueError as exc:
        return {
            "content": [{"type": "text", "text": str(exc)}],
            "is_error": True,
        }

    status = "passed" if record.success else "failed"
    return {
        "content": [
            {
                "type": "text",
                "text": f"Created test run {record.id} ({status})",
            }
        ]
    }


@tool(
    "list_test_runs",
    "List test runs with optional filters",
    {
        "project_id": str,
        "server_id": str,
        "success": str,
        "include_output": bool,
        "include_logs": bool,
        "include_artifacts": bool,
        "limit": int,
        "offset": int,
    },
)
async def list_test_runs(args: dict[str, Any]) -> dict[str, Any]:
    """List test runs with optional filters."""
    service = _get_test_run_service()

    success = None
    if args.get("success"):
        value = str(args["success"]).strip().lower()
        if value in {"passed", "true", "yes"}:
            success = True
        elif value in {"failed", "false", "no"}:
            success = False
        else:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "Invalid success value. Use passed/failed or true/false.",
                    }
                ],
                "is_error": True,
            }

    limit = int(args.get("limit", 50))
    offset = int(args.get("offset", 0))
    include_output = bool(args.get("include_output", False))
    include_logs = bool(args.get("include_logs", False))
    include_artifacts = bool(args.get("include_artifacts", False))

    result = await service.list_test_runs(
        server_id=args.get("server_id"),
        project_id=args.get("project_id"),
        success=success,
        limit=limit,
        offset=offset,
        include_output=include_output,
        include_logs=include_logs,
        include_artifacts=include_artifacts,
    )

    if not result.items:
        return {"content": [{"type": "text", "text": "No test runs found."}]}

    lines = [f"Found {result.total_count} test run(s):"]
    for run in result.items:
        status = "passed" if run.success else "failed"
        command = run.command or "test run"
        lines.append(
            f"- {run.id} ({status}) {command} | server {run.server_id} | project {run.project_id or 'none'}"
        )
        if include_output:
            if run.stdout:
                lines.append("  stdout:")
                lines.append(f"{run.stdout}")
            if run.stderr:
                lines.append("  stderr:")
                lines.append(f"{run.stderr}")
        if include_logs and run.logs:
            lines.append("  logs:")
            for path, content in run.logs.items():
                lines.append(f"  - {path}")
                lines.append(content)
        if include_artifacts and run.artifacts:
            lines.append("  artifacts:")
            for path, stored in run.artifacts.items():
                lines.append(f"  - {path} -> {stored}")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "get_test_run",
    "Get a test run with optional output, logs, and artifacts",
    {
        "run_id": str,
        "include_output": bool,
        "include_logs": bool,
        "include_artifacts": bool,
    },
)
async def get_test_run(args: dict[str, Any]) -> dict[str, Any]:
    """Get a test run with optional output, logs, and artifacts."""
    service = _get_test_run_service()

    run_id = args.get("run_id")
    if not run_id:
        return {
            "content": [{"type": "text", "text": "run_id is required."}],
            "is_error": True,
        }

    run = await service.get_test_run(
        run_id=run_id,
        include_output=bool(args.get("include_output", True)),
        include_logs=bool(args.get("include_logs", True)),
        include_artifacts=bool(args.get("include_artifacts", True)),
    )
    if run is None:
        return {
            "content": [{"type": "text", "text": "Test run not found."}],
            "is_error": True,
        }

    status = "passed" if run.success else "failed"
    lines = [
        f"Test Run: {run.id}",
        f"Status: {status}",
        f"Server: {run.server_id}",
    ]
    if run.project_id:
        lines.append(f"Project: {run.project_id}")
    if run.plan_id:
        lines.append(f"Plan: {run.plan_id}")
    if run.task_ids:
        lines.append(f"Tasks: {', '.join(run.task_ids)}")
    if run.command:
        lines.append(f"Command: {run.command}")
    if run.runner:
        lines.append(f"Runner: {run.runner}")
    if run.duration_seconds is not None:
        lines.append(f"Duration: {run.duration_seconds:.1f}s")
    if run.exit_code is not None:
        lines.append(f"Exit code: {run.exit_code}")

    if run.stdout:
        lines.append("Stdout:")
        lines.append(run.stdout)
    if run.stderr:
        lines.append("Stderr:")
        lines.append(run.stderr)
    if run.logs:
        lines.append("Logs:")
        for path, payload in run.logs.items():
            if isinstance(payload, dict):
                meta_bits = []
                size_bytes = payload.get("size_bytes")
                captured_at = payload.get("captured_at")
                if size_bytes is not None:
                    meta_bits.append(f"{size_bytes} bytes")
                if captured_at:
                    meta_bits.append(f"captured {captured_at}")
                suffix = f" ({', '.join(meta_bits)})" if meta_bits else ""
                lines.append(f"- {path}{suffix}")
                content = payload.get("content")
                if content:
                    lines.append(content)
            else:
                lines.append(f"- {path}")
                lines.append(str(payload))
    if run.artifacts:
        lines.append("Artifacts:")
        for path, payload in run.artifacts.items():
            if isinstance(payload, dict):
                local_path = payload.get("local_path") or "-"
                meta_bits = []
                size_bytes = payload.get("size_bytes")
                modified_at = payload.get("modified_at")
                if size_bytes is not None:
                    meta_bits.append(f"{size_bytes} bytes")
                if modified_at:
                    meta_bits.append(f"modified {modified_at}")
                suffix = f" ({', '.join(meta_bits)})" if meta_bits else ""
                lines.append(f"- {path} -> {local_path}{suffix}")
            else:
                lines.append(f"- {path} -> {payload}")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "prune_test_runs",
    "Prune stored test run outputs by size or age",
    {
        "max_log_bytes": int,
        "max_artifact_bytes": int,
        "max_age_days": int,
        "dry_run": bool,
    },
)
async def prune_test_runs(args: dict[str, Any]) -> dict[str, Any]:
    """Prune stored test run outputs by size or age."""
    service = _get_test_run_retention_service()

    summary = await service.prune(
        max_log_bytes=args.get("max_log_bytes"),
        max_artifact_bytes=args.get("max_artifact_bytes"),
        max_age_days=args.get("max_age_days"),
        dry_run=bool(args.get("dry_run", False)),
    )

    mode = "DRY RUN" if summary.dry_run else "APPLIED"
    lines = [
        f"Test Run Prune ({mode})",
        f"Runs scanned: {summary.runs_scanned}",
        f"Runs pruned: {summary.runs_pruned}",
        f"Logs pruned: {summary.runs_logs_pruned}",
        f"Artifacts pruned: {summary.runs_artifacts_pruned}",
        (
            f"Log bytes: {summary.log_bytes_before} -> {summary.log_bytes_after} "
            f"(freed {summary.log_bytes_pruned})"
        ),
        (
            f"Artifact bytes: {summary.artifact_bytes_before} -> "
            f"{summary.artifact_bytes_after} (freed {summary.artifact_bytes_pruned})"
        ),
    ]

    if summary.pruned_run_ids:
        lines.append(f"Pruned runs: {', '.join(summary.pruned_run_ids[:10])}")
        if len(summary.pruned_run_ids) > 10:
            lines.append("... (truncated)")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "get_test_run_retention",
    "Get test run retention usage summary",
    {
        "limit": int,
        "sort": str,
    },
)
async def get_test_run_retention(args: dict[str, Any]) -> dict[str, Any]:
    """Get test run retention usage summary."""
    service = _get_test_run_retention_service()

    sort = str(args.get("sort", "largest")).strip().lower()
    if sort not in {"largest", "recent"}:
        return {
            "content": [
                {
                    "type": "text",
                    "text": "Invalid sort value. Use largest or recent.",
                }
            ],
            "is_error": True,
        }

    limit = int(args.get("limit", 20))
    summary = await service.get_usage(limit=limit, sort=sort)

    def format_bytes(value: int) -> str:
        if value < 1024:
            return f"{value} B"
        size = float(value)
        for unit in ("KB", "MB", "GB", "TB", "PB"):
            size /= 1024
            if size < 1024:
                return f"{size:.1f} {unit}"
        return f"{size:.1f} EB"

    lines = [
        "Test Run Retention Usage",
        f"Total runs: {summary.total_runs}",
        (
            "Total log bytes: "
            f"{format_bytes(summary.total_log_bytes_combined)} "
            f"(stdout {format_bytes(summary.total_stdout_bytes)}, "
            f"stderr {format_bytes(summary.total_stderr_bytes)}, "
            f"logs {format_bytes(summary.total_log_bytes)})"
        ),
        (
            "Total artifact bytes: "
            f"{format_bytes(summary.total_artifact_bytes)} "
            f"(recorded {format_bytes(summary.total_artifact_recorded_bytes)})"
        ),
        f"Total bytes: {format_bytes(summary.total_bytes)}",
        (
            "Policy: "
            f"logs <= {format_bytes(summary.max_log_bytes)}, "
            f"artifacts <= {format_bytes(summary.max_artifact_bytes)}, "
            f"age <= {summary.max_age_days} day(s)"
        ),
        f"Sorted by: {summary.sorted_by}",
    ]

    if summary.items:
        lines.append("Runs:")
        for item in summary.items:
            missing = (
                f", missing {item.artifacts_missing}" if item.artifacts_missing else ""
            )
            lines.append(
                f"- {item.run_id} | total {format_bytes(item.total_bytes)} "
                f"(logs {format_bytes(item.log_total_bytes)}, "
                f"artifacts {format_bytes(item.artifact_bytes)}) | "
                f"finished {item.finished_at.isoformat()} | "
                f"project {item.project_id or 'none'} | "
                f"server {item.server_id}{missing}"
            )
    else:
        lines.append("No test runs found.")

    return {"content": [{"type": "text", "text": "\n".join(lines)}]}


@tool(
    "get_blocked_tasks",
    "Get all blocked tasks, optionally filtered by project",
    {"project": str},
)
async def get_blocked_tasks(args: dict[str, Any]) -> dict[str, Any]:
    """Get blocked tasks."""
    project_service = _get_project_service()
    task_service = _get_task_service()

    project_id = None
    project_name = "all projects"

    if args.get("project"):
        project = await project_service.get_project_by_name(args["project"])
        if project is None:
            project = await project_service.get_project(args["project"])

        if project:
            project_id = project.id
            project_name = project.name

    blocked = await task_service.get_blocked_tasks(project_id)

    if not blocked:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"No blocked tasks in {project_name}.",
                }
            ]
        }

    lines = [f"Blocked tasks in {project_name} ({len(blocked)}):"]
    for t in blocked:
        lines.append(f"- {t.title} (ID: {t.id})")

    return {
        "content": [
            {
                "type": "text",
                "text": "\n".join(lines),
            }
        ]
    }


@tool(
    "bulk_create_tasks",
    "Create multiple tasks at once from a comma-separated list of titles",
    {"project": str, "titles": str, "priority": str},
)
async def bulk_create_tasks(args: dict[str, Any]) -> dict[str, Any]:
    """Bulk create tasks."""

    project_service = _get_project_service()
    task_service = _get_task_service()

    # Find project
    project = await project_service.get_project_by_name(args["project"])
    if project is None:
        project = await project_service.get_project(args["project"])

    if project is None:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Project '{args['project']}' not found.",
                }
            ],
            "is_error": True,
        }

    # Parse titles
    titles = [t.strip() for t in args["titles"].split(",") if t.strip()]
    if not titles:
        return {
            "content": [
                {
                    "type": "text",
                    "text": "No task titles provided.",
                }
            ],
            "is_error": True,
        }

    # Parse priority
    priority = args.get("priority", "medium")

    tasks_data = [{"title": title, "priority": priority} for title in titles]
    batch = await task_service.bulk_create_tasks(project.id, tasks_data)

    return {
        "content": [
            {
                "type": "text",
                "text": (
                    f"Created {batch.success_count} tasks in '{project.name}'.\n"
                    f"Failures: {batch.failure_count}"
                ),
            }
        ]
    }


# List of all tools for export
ALL_PROJECT_TOOLS = [
    create_actor,
    list_actors,
    get_actor,
    add_actor_alias,
    add_actor_membership,
    create_project,
    list_projects,
    get_project,
    get_project_summary,
    archive_project,
    update_project,
    delete_project,
    get_dashboard,
    get_work_snapshot,
    mark_work_snapshot_reviewed,
    get_work_daily,
    create_goal,
    list_goals,
    get_goal,
    get_goal_summary,
    update_goal,
    complete_goal,
    archive_goal,
    create_objective,
    list_objectives,
    get_objective,
    update_objective,
    complete_objective,
    archive_objective,
    create_key_result,
    list_key_results,
    get_key_result,
    update_key_result,
    complete_key_result,
    archive_key_result,
    create_plan,
    list_plans,
    get_plan,
    update_plan,
    create_plan_test_job,
    list_plan_test_jobs,
    get_plan_test_job,
    update_plan_test_job,
    delete_plan_test_job,
    run_plan_test_job,
    create_organization,
    list_organizations,
    get_organization,
    update_organization,
    get_organization_summary,
    get_organization_dashboard,
    create_team,
    list_teams,
    get_team,
    update_team,
    create_portfolio,
    list_portfolios,
    get_portfolio,
    update_portfolio,
    get_portfolio_summary,
    get_portfolio_dashboard,
    create_program,
    list_programs,
    get_program,
    update_program,
    get_program_summary,
    get_program_dashboard,
    create_task,
    list_tasks,
    search_tasks,
    create_saved_search,
    list_saved_searches,
    get_saved_search,
    update_saved_search,
    delete_saved_search,
    run_saved_search,
    list_queue_presets,
    get_queue_preset,
    find_duplicate_tasks,
    preview_merge_duplicate_tasks,
    merge_duplicate_tasks,
    get_task_proof_bundle,
    create_custom_field,
    list_custom_fields,
    get_custom_field,
    update_custom_field,
    delete_custom_field,
    restore_custom_field,
    set_custom_field_value,
    list_custom_field_values,
    list_custom_field_values_for_field,
    add_comment,
    list_comments,
    get_comment,
    delete_comment,
    restore_comment,
    add_watcher,
    list_watchers,
    remove_watcher,
    restore_watcher,
    create_automation_rule,
    list_automation_rules,
    get_automation_rule,
    update_automation_rule,
    delete_automation_rule,
    restore_automation_rule,
    run_automation_rules,
    list_automation_rule_runs,
    create_evidence_gate_rule,
    list_evidence_gate_rules,
    delete_evidence_gate_rule,
    create_test_run,
    list_test_runs,
    get_test_run,
    prune_test_runs,
    get_test_run_retention,
    list_ready_tasks,
    list_stale_tasks,
    start_task,
    complete_task,
    update_task_progress,
    update_task,
    add_task_evidence,
    checkout_task,
    renew_task_checkout,
    release_task_checkout,
    assign_workflow,
    transition_workflow,
    delete_task,
    block_task,
    unblock_task,
    add_task_dependency,
    get_task_tree,
    get_blocked_tasks,
    bulk_create_tasks,
]
