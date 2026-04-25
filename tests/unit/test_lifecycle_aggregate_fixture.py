"""Unit coverage for shared lifecycle aggregate fixture helpers."""

from __future__ import annotations

import pytest

from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.db.connection import Database
from pms.db.schema import initialize_schema
from pms.services.comment_service import CommentService
from pms.services.goal_service import GoalService
from pms.services.plan_service import PlanService
from pms.services.project_service import ProjectService
from pms.services.task_service import TaskService
from scripts.lifecycle_aggregate_fixture import (
    build_goal_lifecycle_expectations,
    build_key_result_lifecycle_expectations,
    build_objective_lifecycle_expectations,
    seed_goal_lifecycle_fixture,
    seed_key_result_lifecycle_fixture,
    seed_objective_lifecycle_fixture,
    seed_project_lifecycle_fixture,
)
from scripts.project_lifecycle_contract_utils import (
    expectation_from_summary as project_expectation_from_summary,
)


async def _make_services(tmp_path):
    db = Database(tmp_path / "audit.db")
    await db.connect()
    await initialize_schema(db)
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)
    return db, {
        "project_service": ProjectService(db, event_store, revision_store, metrics),
        "task_service": TaskService(db, event_store, revision_store, metrics),
        "goal_service": GoalService(db, event_store, revision_store, metrics),
        "plan_service": PlanService(db, event_store, revision_store, metrics),
        "comment_service": CommentService(db, metrics),
    }


@pytest.mark.asyncio
async def test_seed_goal_lifecycle_fixture_builds_active_and_terminal_expectations(
    tmp_path,
):
    db, services = await _make_services(tmp_path)
    try:
        fixture = await seed_goal_lifecycle_fixture(
            services["project_service"],
            services["goal_service"],
            services["task_service"],
            active_project_name="Fixture Goal Active Project",
            active_goal_name="Fixture Goal Active Goal",
            active_task_title="Fixture Goal Active Task",
            active_progress_percent=45,
            active_status_message="Implementing",
            active_updated_by="fixture-audit",
            terminal_project_name="Fixture Goal Terminal Project",
            terminal_goal_name="Fixture Goal Terminal Goal",
            terminal_task_title="Fixture Goal Terminal Task",
        )
        expectations, project_ids = await build_goal_lifecycle_expectations(
            services["goal_service"],
            [fixture.active_goal_id, fixture.terminal_goal_id],
        )

        active_expectation = expectations[fixture.active_goal_id]
        terminal_expectation = expectations[fixture.terminal_goal_id]

        assert project_ids[fixture.active_goal_id] == fixture.active_project_id
        assert active_expectation.execution_focus_task_id == fixture.active_task_id
        assert active_expectation.terminal_reason is None

        assert project_ids[fixture.terminal_goal_id] == fixture.terminal_project_id
        assert terminal_expectation.execution_focus_task_id is None
        assert terminal_expectation.terminal_reason is not None
    finally:
        await db.disconnect()


@pytest.mark.asyncio
async def test_seed_objective_lifecycle_fixture_builds_active_and_terminal_expectations(
    tmp_path,
):
    db, services = await _make_services(tmp_path)
    try:
        fixture = await seed_objective_lifecycle_fixture(
            services["project_service"],
            services["goal_service"],
            active_project_name="Fixture Objective Active Project",
            active_goal_name="Fixture Objective Active Goal",
            active_objective_name="Fixture Objective Active Objective",
            active_key_result_a_name="Fixture Objective KR A",
            active_key_result_b_name="Fixture Objective KR B",
            terminal_project_name="Fixture Objective Terminal Project",
            terminal_goal_name="Fixture Objective Terminal Goal",
            terminal_objective_name="Fixture Objective Terminal Objective",
            terminal_key_result_name="Fixture Objective Terminal KR",
        )
        expectations = await build_objective_lifecycle_expectations(
            services["goal_service"],
            [fixture.active_objective_id, fixture.terminal_objective_id],
        )

        active_expectation = expectations[fixture.active_objective_id]
        terminal_expectation = expectations[fixture.terminal_objective_id]

        assert active_expectation.project_id == fixture.active_project_id
        assert active_expectation.goal_id == fixture.active_goal_id
        assert active_expectation.key_result_count == 2
        assert active_expectation.completed_key_results == 0
        assert active_expectation.terminal_reason is None

        assert terminal_expectation.project_id == fixture.terminal_project_id
        assert terminal_expectation.goal_id == fixture.terminal_goal_id
        assert terminal_expectation.key_result_count == 1
        assert terminal_expectation.completed_key_results == 1
        assert terminal_expectation.terminal_reason is not None
    finally:
        await db.disconnect()


@pytest.mark.asyncio
async def test_seed_key_result_lifecycle_fixture_builds_active_and_terminal_expectations(
    tmp_path,
):
    db, services = await _make_services(tmp_path)
    try:
        fixture = await seed_key_result_lifecycle_fixture(
            services["project_service"],
            services["goal_service"],
            active_project_name="Fixture Key Result Active Project",
            active_goal_name="Fixture Key Result Active Goal",
            active_objective_name="Fixture Key Result Active Objective",
            active_key_result_name="Fixture Key Result Active KR",
            terminal_project_name="Fixture Key Result Terminal Project",
            terminal_goal_name="Fixture Key Result Terminal Goal",
            terminal_objective_name="Fixture Key Result Terminal Objective",
            terminal_key_result_name="Fixture Key Result Terminal KR",
        )
        expectations = await build_key_result_lifecycle_expectations(
            services["goal_service"],
            [fixture.active_key_result_id, fixture.terminal_key_result_id],
        )

        active_expectation = expectations[fixture.active_key_result_id]
        terminal_expectation = expectations[fixture.terminal_key_result_id]

        assert active_expectation.project_id == fixture.active_project_id
        assert active_expectation.goal_id == fixture.active_goal_id
        assert active_expectation.stored_status == "active"
        assert active_expectation.terminal_reason is None

        assert terminal_expectation.project_id == fixture.terminal_project_id
        assert terminal_expectation.goal_id == fixture.terminal_goal_id
        assert terminal_expectation.stored_status == "completed"
        assert terminal_expectation.terminal_reason is not None
    finally:
        await db.disconnect()


@pytest.mark.asyncio
async def test_seed_project_lifecycle_fixture_keeps_terminal_project_completed(
    tmp_path,
):
    db, services = await _make_services(tmp_path)
    try:
        fixture = await seed_project_lifecycle_fixture(
            services["project_service"],
            services["task_service"],
            services["plan_service"],
            active_project_name="Fixture Project Active Project",
            active_task_title="Fixture Project Active Task",
            start_active_task=False,
            active_progress_percent=40,
            active_status_message="Active execution progress",
            active_updated_by="fixture-audit",
            terminal_project_name="Fixture Project Terminal Project",
            terminal_task_title="Fixture Project Terminal Task",
            terminal_plan_name="Fixture Project Draft Residue Plan",
            terminal_plan_content={"steps": ["planning residue only"]},
            comment_service=services["comment_service"],
            terminal_comment_body="Fresh terminal activity after project completion",
            terminal_comment_author="fixture-audit",
        )

        active_summary = await services["project_service"].get_project_summary(
            fixture.active_project_id
        )
        terminal_summary = await services["project_service"].get_project_summary(
            fixture.terminal_project_id
        )

        assert active_summary is not None
        assert terminal_summary is not None

        active_expectation = project_expectation_from_summary(
            active_summary,
            focus_task_id=fixture.active_task_id,
        )
        terminal_expectation = project_expectation_from_summary(
            terminal_summary,
            focus_task_id=None,
        )

        assert active_expectation.focus_task_id == fixture.active_task_id
        assert terminal_expectation.effective_status == "completed"
        assert terminal_expectation.terminal_reason is not None
        assert terminal_expectation.last_activity_at is not None
        assert terminal_expectation.last_transition_at is not None
        assert (
            terminal_expectation.last_activity_at
            >= terminal_expectation.last_transition_at
        )
    finally:
        await db.disconnect()
