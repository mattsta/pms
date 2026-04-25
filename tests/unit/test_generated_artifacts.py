from __future__ import annotations

from pms.models import Plan, PlanFormat, PlanStatus, Project, ProjectStatus
from pms.services.generated_artifacts import (
    is_audit_generated_plan,
    is_audit_generated_project,
)


def _project(
    name: str,
    *,
    description: str | None = None,
    tags: list[str] | None = None,
) -> Project:
    return Project(
        id="project-1",
        name=name,
        description=description,
        status=ProjectStatus.ACTIVE,
        tags=tags or [],
    )


def _plan(
    name: str,
    *,
    project_id: str | None = None,
    goal_id: str | None = None,
    tags: list[str] | None = None,
) -> Plan:
    return Plan(
        id="plan-1",
        name=name,
        description=None,
        status=PlanStatus.ACTIVE,
        format=PlanFormat.JSON,
        content="{}",
        project_id=project_id,
        goal_id=goal_id,
        tags=tags or [],
        task_ids=[],
    )


def test_runtime_repro_project_is_hidden_from_operator_views() -> None:
    project = _project("Runtime Repro Project 4", description="Quickstart project")
    assert is_audit_generated_project(project) is True


def test_audit_active_project_is_hidden_from_operator_views() -> None:
    project = _project("Audit Active Project")
    assert is_audit_generated_project(project) is True


def test_normal_project_is_not_hidden() -> None:
    project = _project("Operator Delivery Project")
    assert is_audit_generated_project(project) is False


def test_placeholder_linked_plan_is_hidden_from_operator_views() -> None:
    plan = _plan("PMS Finality and Scope Clarity Delivery Plan", project_id="null")
    assert is_audit_generated_plan(plan, None) is True


def test_runtime_repro_plan_is_hidden_from_operator_views() -> None:
    plan = _plan("Runtime Repro Project 5 Plan", project_id="project-1")
    assert is_audit_generated_plan(plan, "Runtime Repro Project 5") is True


def test_normal_plan_is_not_hidden() -> None:
    plan = _plan("Operator Delivery Plan", project_id="project-1")
    assert is_audit_generated_plan(plan, "Operator Delivery Project") is False
