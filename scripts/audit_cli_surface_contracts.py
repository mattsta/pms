#!/usr/bin/env python3
"""Audit broad CLI JSON surface contracts for runnable command guidance."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


@dataclass(frozen=True)
class CommandSurfaceSpec:
    """Single CLI JSON surface to audit."""

    name: str
    setup: str
    args: tuple[str, ...]
    required_keys: tuple[str, ...] = ()
    require_next_steps: bool = True
    require_cli_prefix: bool = False
    root_type: str = "object"
    expect_completion_context: bool = False
    expect_terminal_reason: bool = False
    expected_active_visible_projects: int | None = None
    expected_active_visible_plans: int | None = None


@dataclass(frozen=True)
class SurfaceIssue:
    """Single CLI surface contract issue."""

    surface: str
    reason: str


@dataclass(frozen=True)
class SurfaceAuditResult:
    """Combined CLI surface audit result."""

    checked: int
    issues: tuple[SurfaceIssue, ...]


@dataclass(frozen=True)
class WorkspaceContext:
    """Unique names used by a single audit workspace."""

    organization: str
    product: str
    project: str
    portfolio: str
    program: str
    active_task: str
    followup_task: str
    goal: str
    plan: str


SPECS: tuple[CommandSurfaceSpec, ...] = (
    CommandSurfaceSpec(
        name="start",
        setup="active_workspace",
        args=("start", "--format", "json"),
        required_keys=("purpose", "live_state", "links", "next_steps"),
        require_cli_prefix=True,
    ),
    CommandSurfaceSpec(
        name="dashboard",
        setup="active_workspace",
        args=("dashboard", "--format", "json"),
        required_keys=("purpose", "scope", "queue_presets", "links", "next_steps"),
        require_cli_prefix=True,
    ),
    CommandSurfaceSpec(
        name="dashboard terminal",
        setup="terminal_workspace",
        args=("dashboard", "--format", "json"),
        required_keys=(
            "purpose",
            "scope",
            "completion_context",
            "terminal_reason",
            "links",
            "next_steps",
        ),
        require_cli_prefix=True,
        expect_completion_context=True,
        expect_terminal_reason=True,
        expected_active_visible_projects=0,
    ),
    CommandSurfaceSpec(
        name="queue presets",
        setup="active_workspace",
        args=("queue", "presets", "--format", "json"),
        required_keys=("items", "page", "links", "next_steps"),
        require_cli_prefix=True,
    ),
    CommandSurfaceSpec(
        name="work daily",
        setup="active_workspace",
        args=(
            "work",
            "daily",
            "--scope-type",
            "project",
            "--scope",
            "{project}",
            "--format",
            "json",
        ),
        required_keys=("purpose", "links", "next_steps"),
        require_cli_prefix=True,
    ),
    CommandSurfaceSpec(
        name="project list",
        setup="active_workspace",
        args=("project", "list", "--format", "json"),
        required_keys=(
            "items",
            "page",
            "scope",
            "links",
            "next_steps",
            "modeling_tips",
            "modeling_recipes",
        ),
        require_cli_prefix=True,
    ),
    CommandSurfaceSpec(
        name="project list terminal",
        setup="terminal_workspace",
        args=("project", "list", "--format", "json"),
        required_keys=(
            "items",
            "page",
            "scope",
            "completion_context",
            "terminal_reason",
            "links",
            "next_steps",
            "modeling_tips",
            "modeling_recipes",
        ),
        require_cli_prefix=True,
        expect_completion_context=True,
        expect_terminal_reason=True,
        expected_active_visible_projects=0,
    ),
    CommandSurfaceSpec(
        name="project show",
        setup="active_workspace",
        args=("project", "show", "{project}", "--format", "json"),
        required_keys=(
            "id",
            "links",
            "next_steps",
            "modeling_tips",
            "modeling_recipes",
        ),
        require_cli_prefix=True,
    ),
    CommandSurfaceSpec(
        name="project summary",
        setup="active_workspace",
        args=("project", "summary", "{project}", "--format", "json"),
        required_keys=("project", "stats", "links", "next_steps"),
        require_cli_prefix=True,
    ),
    CommandSurfaceSpec(
        name="product summary",
        setup="active_workspace",
        args=("product", "summary", "{product}", "--format", "json"),
        required_keys=("product", "stats", "links", "next_steps"),
        require_cli_prefix=True,
    ),
    CommandSurfaceSpec(
        name="task list",
        setup="active_workspace",
        args=("task", "list", "--project", "{project}", "--format", "json"),
        required_keys=("items", "page", "links", "next_steps"),
        require_cli_prefix=True,
    ),
    CommandSurfaceSpec(
        name="task show",
        setup="active_workspace",
        args=(
            "task",
            "show",
            "{active_task}",
            "--project",
            "{project}",
            "--format",
            "json",
        ),
        required_keys=("id", "links", "next_steps"),
        require_cli_prefix=True,
    ),
    CommandSurfaceSpec(
        name="task blocked",
        setup="active_workspace",
        args=("task", "blocked", "--project", "{project}", "--format", "json"),
        required_keys=("items", "page", "scope", "links", "next_steps"),
        require_cli_prefix=True,
    ),
    CommandSurfaceSpec(
        name="goal list",
        setup="active_workspace",
        args=("goal", "list", "--project", "{project}", "--format", "json"),
        required_keys=("items", "page", "links", "next_steps"),
        require_cli_prefix=True,
    ),
    CommandSurfaceSpec(
        name="goal summary",
        setup="active_workspace",
        args=("goal", "summary", "{goal}", "--format", "json"),
        required_keys=("goal", "execution", "next_steps"),
        require_cli_prefix=False,
    ),
    CommandSurfaceSpec(
        name="org summary",
        setup="active_workspace",
        args=("org", "summary", "{organization}", "--format", "json"),
        required_keys=("organization", "stats", "links", "next_steps"),
        require_cli_prefix=True,
    ),
    CommandSurfaceSpec(
        name="portfolio summary",
        setup="active_workspace",
        args=("portfolio", "summary", "{portfolio}", "--format", "json"),
        required_keys=("portfolio", "stats", "links", "next_steps"),
        require_cli_prefix=True,
    ),
    CommandSurfaceSpec(
        name="program summary",
        setup="active_workspace",
        args=("program", "summary", "{program}", "--format", "json"),
        required_keys=("program", "stats", "links", "next_steps"),
        require_cli_prefix=True,
    ),
    CommandSurfaceSpec(
        name="plan list",
        setup="active_plan_workspace",
        args=("plan", "list", "--project", "{project}", "--format", "json"),
        required_keys=("items", "page", "scope", "links", "next_steps"),
        require_cli_prefix=True,
    ),
    CommandSurfaceSpec(
        name="plan list terminal",
        setup="terminal_plan_workspace",
        args=("plan", "list", "--project", "{project}", "--format", "json"),
        required_keys=(
            "items",
            "page",
            "scope",
            "completion_context",
            "terminal_reason",
            "links",
            "next_steps",
            "status_groups",
        ),
        require_cli_prefix=True,
        expect_completion_context=True,
        expect_terminal_reason=True,
        expected_active_visible_plans=0,
    ),
    CommandSurfaceSpec(
        name="plan show",
        setup="active_plan_workspace",
        args=(
            "plan",
            "show",
            "{plan}",
            "--project",
            "{project}",
            "--format",
            "json",
        ),
        required_keys=("id", "links", "next_steps"),
        require_cli_prefix=True,
    ),
    CommandSurfaceSpec(
        name="plan lineage",
        setup="active_plan_workspace",
        args=("plan", "lineage", "--project", "{project}", "--format", "json"),
        required_keys=("items", "totals", "links", "next_steps"),
        require_cli_prefix=True,
    ),
)


def _with_temp_env() -> dict[str, str]:
    temp_dir = Path(tempfile.mkdtemp(prefix="surface-audit-", dir=REPO_ROOT / ".tmp"))
    env = os.environ.copy()
    env["PMS_DATA_DIR"] = str(temp_dir)
    env["PMS_DATABASE_PATH"] = str(temp_dir / "audit.db")
    env["PMS_LOG_DIR"] = str(temp_dir / "logs")
    env["PMS_ENV_FILE"] = str(temp_dir / ".env")
    env["PMS_WRITE_MODE"] = "direct"
    env.pop("PMS_SERVER_BASE_URL", None)
    env.pop("PMS_API_KEY", None)
    env.pop("PMS_API_KEY_PATH", None)
    return env


def _workspace_context(env: dict[str, str]) -> WorkspaceContext:
    suffix = Path(env["PMS_DATA_DIR"]).name.replace("surface-audit-", "")
    return WorkspaceContext(
        organization=f"Surface Org {suffix}",
        product=f"Surface Product {suffix}",
        project=f"Surface Project {suffix}",
        portfolio=f"Surface Portfolio {suffix}",
        program=f"Surface Program {suffix}",
        active_task=f"Surface Active Task {suffix}",
        followup_task=f"Surface Followup Task {suffix}",
        goal=f"Surface Goal {suffix}",
        plan=f"Surface Plan {suffix}",
    )


def _render_args(args: tuple[str, ...], context: WorkspaceContext) -> tuple[str, ...]:
    substitutions = {
        "organization": context.organization,
        "product": context.product,
        "project": context.project,
        "portfolio": context.portfolio,
        "program": context.program,
        "active_task": context.active_task,
        "followup_task": context.followup_task,
        "goal": context.goal,
        "plan": context.plan,
    }
    return tuple(arg.format(**substitutions) for arg in args)


def _run_cli(
    args: tuple[str, ...] | list[str], env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "pms", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _invoke(
    args: tuple[str, ...],
    env: dict[str, str],
    context: WorkspaceContext,
) -> object:
    rendered_args = _render_args(args, context)
    result = _run_cli(rendered_args, env)
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(rendered_args)}\n{result.stdout}{result.stderr}"
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Command emitted invalid JSON: {' '.join(rendered_args)}\n{result.stdout}"
        ) from exc
    return payload


def _apply_runtime_env(env: dict[str, str]) -> None:
    managed_keys = (
        "PMS_DATA_DIR",
        "PMS_DATABASE_PATH",
        "PMS_LOG_DIR",
        "PMS_ENV_FILE",
        "PMS_WRITE_MODE",
        "PMS_SERVER_BASE_URL",
        "PMS_API_KEY",
        "PMS_API_KEY_PATH",
    )
    for key in managed_keys:
        value = env.get(key)
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    from pms.config.settings import reload_settings

    reload_settings()


async def _prepare_workspace_async(
    setup: str,
    context: WorkspaceContext,
) -> None:
    from pms.core.events import EventStore
    from pms.core.metrics import MetricsCollector
    from pms.core.revisions import RevisionStore
    from pms.db.connection import Database
    from pms.db.schema import initialize_schema
    from pms.models import GoalHorizon, PlanFormat, PlanStatus, Priority, ProjectStatus
    from pms.services.goal_service import GoalService
    from pms.services.organization_service import OrganizationService
    from pms.services.plan_service import PlanService
    from pms.services.portfolio_service import PortfolioService
    from pms.services.product_service import ProductService
    from pms.services.program_service import ProgramService
    from pms.services.project_service import ProjectService
    from pms.services.task_service import TaskService

    db = Database()
    await db.connect()
    await initialize_schema(db)
    try:
        event_store = EventStore(db)
        revision_store = RevisionStore(db)
        metrics = MetricsCollector(db)
        org_service = OrganizationService(db, event_store, revision_store, metrics)
        portfolio_service = PortfolioService(db, event_store, revision_store, metrics)
        product_service = ProductService(db, event_store, revision_store, metrics)
        program_service = ProgramService(db, event_store, revision_store, metrics)
        project_service = ProjectService(db, event_store, revision_store, metrics)
        task_service = TaskService(db, event_store, revision_store, metrics)
        goal_service = GoalService(db, event_store, revision_store, metrics)
        plan_service = PlanService(db, event_store, revision_store, metrics)

        if setup == "empty_workspace":
            return

        org = await org_service.create_organization(name=context.organization)
        product = await product_service.create_product(
            name=context.product,
            owner=org.owner or None,
        )
        project = await project_service.create_project(
            name=context.project,
            description="Surface audit project",
            product_id=product.id,
        )
        portfolio = await portfolio_service.create_portfolio(
            name=context.portfolio,
            org_id=org.id,
            description="Surface audit portfolio",
            project_ids=[project.id],
        )
        await program_service.create_program(
            name=context.program,
            org_id=org.id,
            portfolio_id=portfolio.id,
            description="Surface audit program",
            project_ids=[project.id],
        )

        task_one = await task_service.create_task(
            project_id=project.id,
            title=context.active_task,
            description="Surface audit task",
            priority=Priority.MEDIUM,
            tags=["surface-audit"],
        )
        task_two = await task_service.create_task(
            project_id=project.id,
            title=context.followup_task,
            description="Surface audit task",
            priority=Priority.MEDIUM,
            tags=["surface-audit"],
        )
        await goal_service.create_goal(
            name=context.goal,
            project_id=project.id,
            horizon=GoalHorizon.SHORT_TERM,
        )

        if setup in {"active_workspace", "active_plan_workspace"}:
            await task_service.start_task(task_one.id, reason="surface-audit")

        if setup == "active_plan_workspace":
            await plan_service.create_plan(
                name=context.plan,
                description="Surface audit plan",
                status=PlanStatus.ACTIVE,
                format=PlanFormat.JSON,
                content={},
                project_id=project.id,
                task_ids=[task_one.id, task_two.id],
            )
            return

        if setup == "terminal_workspace":
            await task_service.complete_task(task_one.id)
            await task_service.complete_task(task_two.id)
            await project_service.update_project(
                project.id,
                status=ProjectStatus.COMPLETED,
            )
            return

        if setup == "terminal_plan_workspace":
            await plan_service.create_plan(
                name=context.plan,
                description="Surface audit plan",
                status=PlanStatus.COMPLETED,
                format=PlanFormat.JSON,
                content={},
                project_id=project.id,
                task_ids=[task_one.id, task_two.id],
            )
            return
    finally:
        await db.disconnect()


def _prepare_workspace(
    setup: str,
    env: dict[str, str],
    context: WorkspaceContext,
) -> None:
    _apply_runtime_env(env)
    asyncio.run(_prepare_workspace_async(setup, context))


def _is_bare_pms_command(value: str) -> bool:
    return value.startswith("pms ")


def _is_runnable_command(value: str) -> bool:
    return value.startswith("uv run pms ") or value.startswith("./")


def _collect_command_strings(value: object, parent_key: str | None = None) -> list[str]:
    commands: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "links" and isinstance(item, dict):
                for link_value in item.values():
                    commands.extend(_collect_command_strings(link_value, "links"))
            elif key == "next_steps" and isinstance(item, list):
                for step in item:
                    commands.extend(_collect_command_strings(step, "next_steps"))
            else:
                commands.extend(_collect_command_strings(item, key))
        return commands
    if isinstance(value, list):
        for item in value:
            commands.extend(_collect_command_strings(item, parent_key))
        return commands
    if isinstance(value, str) and parent_key in {"links", "next_steps"}:
        commands.append(value)
    return commands


def _audit_surface(spec: CommandSurfaceSpec) -> tuple[SurfaceIssue, ...]:
    env = _with_temp_env()
    context = _workspace_context(env)
    _prepare_workspace(spec.setup, env, context)
    return _audit_surface_with_workspace(spec, env, context)


def _audit_surface_with_workspace(
    spec: CommandSurfaceSpec,
    env: dict[str, str],
    context: WorkspaceContext,
) -> tuple[SurfaceIssue, ...]:
    payload = _invoke(spec.args, env, context)

    issues: list[SurfaceIssue] = []
    if spec.root_type == "object":
        if not isinstance(payload, dict):
            issues.append(
                SurfaceIssue(
                    spec.name,
                    f"expected top-level JSON object, got {type(payload).__name__}",
                )
            )
            return tuple(issues)
        for key in spec.required_keys:
            if key not in payload:
                issues.append(SurfaceIssue(spec.name, f"missing top-level key '{key}'"))
    elif spec.root_type == "list":
        if not isinstance(payload, list):
            issues.append(
                SurfaceIssue(
                    spec.name,
                    f"expected top-level JSON list, got {type(payload).__name__}",
                )
            )
            return tuple(issues)
    else:
        raise ValueError(f"Unknown root type: {spec.root_type}")

    if spec.require_next_steps:
        if not isinstance(payload, dict):
            issues.append(SurfaceIssue(spec.name, "missing non-empty next_steps"))
            return tuple(issues)
        next_steps = payload.get("next_steps")
        if not isinstance(next_steps, list) or not next_steps:
            issues.append(SurfaceIssue(spec.name, "missing non-empty next_steps"))

    if spec.require_cli_prefix:
        if not isinstance(payload, dict):
            issues.append(SurfaceIssue(spec.name, "missing cli prefix metadata"))
            return tuple(issues)
        cli_payload = payload.get("cli")
        if not isinstance(cli_payload, dict):
            issues.append(SurfaceIssue(spec.name, "missing cli prefix metadata"))
        else:
            canonical_prefix = cli_payload.get("canonical_prefix")
            if canonical_prefix != "uv run pms":
                issues.append(
                    SurfaceIssue(
                        spec.name,
                        f"unexpected canonical_prefix: {canonical_prefix!r}",
                    )
                )

    if (
        spec.expect_completion_context
        and isinstance(payload, dict)
        and payload.get("completion_context") is None
    ):
        issues.append(SurfaceIssue(spec.name, "expected non-null completion_context"))

    if (
        spec.expect_terminal_reason
        and isinstance(payload, dict)
        and payload.get("terminal_reason") is None
    ):
        issues.append(SurfaceIssue(spec.name, "expected non-null terminal_reason"))

    if spec.expected_active_visible_projects is not None and isinstance(payload, dict):
        scope = payload.get("scope")
        if not isinstance(scope, dict):
            issues.append(SurfaceIssue(spec.name, "missing scope metadata"))
        elif (
            scope.get("active_visible_projects")
            != spec.expected_active_visible_projects
        ):
            issues.append(
                SurfaceIssue(
                    spec.name,
                    "unexpected active_visible_projects: "
                    f"{scope.get('active_visible_projects')!r}",
                )
            )

    if spec.expected_active_visible_plans is not None and isinstance(payload, dict):
        scope = payload.get("scope")
        if not isinstance(scope, dict):
            issues.append(SurfaceIssue(spec.name, "missing scope metadata"))
        elif scope.get("active_visible_plans") != spec.expected_active_visible_plans:
            issues.append(
                SurfaceIssue(
                    spec.name,
                    f"unexpected active_visible_plans: {scope.get('active_visible_plans')!r}",
                )
            )

    for command in _collect_command_strings(payload):
        if _is_bare_pms_command(command):
            issues.append(
                SurfaceIssue(spec.name, f"bare pms command in JSON surface: {command}")
            )
        if " | " in command:
            issues.append(
                SurfaceIssue(
                    spec.name, f"pipe-merged command hint in JSON surface: {command}"
                )
            )
        if command and command.startswith(("uv run pms ", "./")):
            continue
        if command and any(
            token in command
            for token in ("pms ", "--format json", "--project", "--scope")
        ):
            issues.append(
                SurfaceIssue(
                    spec.name, f"non-runnable command hint in JSON surface: {command}"
                )
            )

    return tuple(issues)


def run_audit() -> SurfaceAuditResult:
    issues: list[SurfaceIssue] = []
    prepared_workspaces: dict[str, tuple[dict[str, str], WorkspaceContext]] = {}
    for spec in SPECS:
        workspace = prepared_workspaces.get(spec.setup)
        if workspace is None:
            env = _with_temp_env()
            context = _workspace_context(env)
            _prepare_workspace(spec.setup, env, context)
            workspace = (env, context)
            prepared_workspaces[spec.setup] = workspace
        issues.extend(_audit_surface_with_workspace(spec, workspace[0], workspace[1]))
    return SurfaceAuditResult(checked=len(SPECS), issues=tuple(issues))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    result = run_audit()
    if result.issues:
        for issue in result.issues:
            print(f"{issue.surface}: {issue.reason}")
        if args.check:
            raise SystemExit(1)
    print(f"checked={result.checked} issues={len(result.issues)}")


if __name__ == "__main__":
    main()
