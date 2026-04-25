"""Claudo interoperability adapter tests."""

from __future__ import annotations

import copy
from datetime import UTC, datetime

import pytest

from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.db.connection import Database
from pms.integrations.claudo import (
    CLAUDO_SCHEMA_VERSION,
    ClaudoGraph,
    ClaudoInteropService,
    filter_claudo_graph_for_project,
)
from pms.models import DependencyType, PlanStatus, TaskStatus
from pms.repositories.task_repository import TaskRepository
from pms.services.plan_service import PlanService
from pms.services.project_service import ProjectService
from pms.services.task_service import TaskService


def _sample_graph() -> ClaudoGraph:
    return ClaudoGraph.from_payload(
        {
            "schema_version": CLAUDO_SCHEMA_VERSION,
            "source": "claude",
            "source_path": "/tmp/claude/tasks",
            "loaded_at": "2026-05-23T12:00:00+00:00",
            "summary": {
                "task_count": 2,
                "edge_count": 1,
                "session_count": 1,
            },
            "source_hierarchy": {
                "projects": [
                    {
                        "label": "-Users-matt-repos-example-app",
                        "project_path": "/Users/matt/repos/example-app",
                        "project_key": "-Users-matt-repos-example-app",
                        "task_lists": [
                            {
                                "session_id": "session-a",
                                "task_count": 2,
                                "dependency_groups": [
                                    {
                                        "component_id": "component-0001",
                                        "edge_count": 1,
                                        "layers": [
                                            {
                                                "depth": 0,
                                                "task_count": 1,
                                                "tasks": ["session-a:1"],
                                            },
                                            {
                                                "depth": 1,
                                                "task_count": 1,
                                                "tasks": ["session-a:2"],
                                            },
                                        ],
                                        "leaf_uids": ["session-a:2"],
                                        "root_uids": ["session-a:1"],
                                        "task_count": 2,
                                        "task_uids": ["session-a:1", "session-a:2"],
                                    }
                                ],
                            }
                        ],
                    }
                ]
            },
            "session_metadata": [
                {
                    "session_id": "session-a",
                    "label": "Example App",
                    "summary": "Bootstrap example project.",
                    "project_path": "/Users/matt/repos/example-app",
                    "project_key": "-Users-matt-repos-example-app",
                }
            ],
            "tasks": [
                {
                    "uid": "session-a:1",
                    "source": "claude",
                    "session_id": "session-a",
                    "task_id": "1",
                    "subject": "Prepare repo",
                    "description": "Set up import fixture.",
                    "status": "completed",
                    "active_form": "",
                    "owner": None,
                    "blocks": ["2"],
                    "blocked_by": [],
                    "path": "/tmp/claude/tasks/session-a/1.json",
                    "source_created_at": "2026-05-23T12:00:00+00:00",
                    "source_modified_at": "2026-05-23T12:05:00+00:00",
                    "metadata": {"rank": 1},
                },
                {
                    "uid": "session-a:2",
                    "source": "claude",
                    "session_id": "session-a",
                    "task_id": "2",
                    "subject": "Import repo",
                    "description": "Consume the exported graph.",
                    "status": "pending",
                    "active_form": "",
                    "owner": "agent",
                    "blocks": [],
                    "blocked_by": ["1"],
                    "path": "/tmp/claude/tasks/session-a/2.json",
                    "source_created_at": "2026-05-23T12:00:00+00:00",
                    "source_modified_at": "2026-05-23T12:05:00+00:00",
                    "metadata": {"rank": 2},
                },
            ],
            "edges": [
                {
                    "uid": "session-a:1->session-a:2",
                    "kind": "blocks",
                    "blocker": {
                        "session_id": "session-a",
                        "task_id": "1",
                        "uid": "session-a:1",
                    },
                    "blocked": {
                        "session_id": "session-a",
                        "task_id": "2",
                        "uid": "session-a:2",
                    },
                    "evidence": ["session-a:1.blocks"],
                }
            ],
            "diagnostics": [],
        }
    )


def test_filter_claudo_graph_for_project_keeps_one_repo_surface() -> None:
    payload = copy.deepcopy(_sample_graph().raw)
    payload["session_metadata"].append(
        {
            "session_id": "session-b",
            "label": "Other App",
            "project_path": "/Users/matt/repos/other-app",
            "project_key": "-Users-matt-repos-other-app",
        }
    )
    payload["tasks"].append(
        {
            "uid": "session-b:1",
            "source": "claude",
            "session_id": "session-b",
            "task_id": "1",
            "subject": "Other repo task",
            "description": "",
            "status": "pending",
            "active_form": "",
            "owner": None,
            "blocks": [],
            "blocked_by": [],
            "path": "/tmp/claude/tasks/session-b/1.json",
            "source_created_at": None,
            "source_modified_at": None,
            "metadata": {},
        }
    )
    payload["edges"].append(
        {
            "uid": "session-a:2->session-b:1",
            "kind": "blocks",
            "blocker": {
                "session_id": "session-a",
                "task_id": "2",
                "uid": "session-a:2",
            },
            "blocked": {
                "session_id": "session-b",
                "task_id": "1",
                "uid": "session-b:1",
            },
            "evidence": ["cross-project"],
        }
    )
    payload["source_hierarchy"]["projects"].append(
        {
            "label": "-Users-matt-repos-other-app",
            "project_path": "/Users/matt/repos/other-app",
            "project_key": "-Users-matt-repos-other-app",
            "task_lists": [{"session_id": "session-b", "task_count": 1}],
        }
    )

    result = filter_claudo_graph_for_project(
        ClaudoGraph.from_payload(payload),
        "/Users/matt/repos/example-app",
    )

    assert result.matched_sessions == ("session-a",)
    assert result.tasks_before == 3
    assert result.tasks_after == 2
    assert result.edges_after == 1
    assert {task.session_id for task in result.graph.tasks} == {"session-a"}
    assert result.graph.summary["session_count"] == 1
    assert result.graph.summary["task_count"] == 2
    projects = result.graph.source_hierarchy["projects"]
    assert len(projects) == 1
    assert projects[0]["project_key"] == "-Users-matt-repos-example-app"


def test_filter_claudo_graph_for_project_matches_project_key_fallback() -> None:
    payload = copy.deepcopy(_sample_graph().raw)
    payload["session_metadata"][0]["project_path"] = None
    payload["source_hierarchy"]["projects"][0]["project_path"] = None

    result = filter_claudo_graph_for_project(
        ClaudoGraph.from_payload(payload),
        "/Users/matt/repos/example-app",
    )

    assert result.project_key == "-Users-matt-repos-example-app"
    assert result.matched_sessions == ("session-a",)
    assert result.tasks_after == 2


def test_filter_claudo_graph_for_project_rejects_unmatched_repo() -> None:
    with pytest.raises(ValueError, match="No Claudo sessions matched project root"):
        filter_claudo_graph_for_project(
            _sample_graph(),
            "/Users/matt/repos/missing-app",
        )


@pytest.mark.asyncio
async def test_claudo_import_creates_connected_pms_graph(
    db: Database,
    event_store: EventStore,
    revision_store: RevisionStore,
    metrics_collector: MetricsCollector,
    task_repo: TaskRepository,
) -> None:
    interop = ClaudoInteropService(
        db,
        event_store,
        revision_store,
        metrics_collector,
    )

    result = await interop.import_graph(_sample_graph())

    assert result.projects_created == 1
    assert result.tasks_created == 2
    assert result.dependencies_created == 1
    assert result.goals_created == 1
    assert result.plans_created == 1

    task_service = TaskService(db, event_store, revision_store, metrics_collector)
    blocker = await task_service.get_task(result.task_ids["session-a:1"])
    blocked = await task_service.get_task(result.task_ids["session-a:2"])

    assert blocker is not None
    assert blocked is not None
    assert blocker.status == TaskStatus.DONE
    assert blocked.status == TaskStatus.TODO
    assert blocked.assignee == "agent"
    source_created = datetime(2026, 5, 23, 12, 0, tzinfo=UTC)
    source_modified = datetime(2026, 5, 23, 12, 5, tzinfo=UTC)
    assert blocker.created_at == source_created
    assert blocker.updated_at == source_modified
    assert blocker.completed_at == source_modified
    assert blocker.current_progress_percent == 100
    assert blocker.last_progress_update_at == source_modified
    assert blocked.created_at == source_created
    assert blocked.updated_at == source_modified

    dependencies = await task_repo.get_dependencies(blocked.id)
    assert len(dependencies) == 1
    assert dependencies[0].depends_on_id == blocker.id
    assert dependencies[0].dependency_type == DependencyType.BLOCKS

    plan_service = PlanService(db, event_store, revision_store, metrics_collector)
    plans = await plan_service.list_plans(project_id=result.project_ids["session-a"])
    assert len(plans.items) == 1
    assert plans.items[0].status == PlanStatus.ACTIVE
    assert plans.items[0].created_at == source_created.isoformat()
    assert plans.items[0].updated_at == source_modified.isoformat()
    assert set(plans.items[0].task_ids) == {blocker.id, blocked.id}

    custom_field_row = await db.fetch_one(
        """
        SELECT MAX(created_at) AS created_at, MAX(updated_at) AS updated_at
        FROM custom_field_values
        WHERE entity_type = 'task' AND entity_id = ? AND source = 'claudo'
        """,
        (blocker.id,),
    )
    assert custom_field_row is not None
    assert custom_field_row["created_at"] == source_created.isoformat()
    assert custom_field_row["updated_at"] == source_modified.isoformat()

    transition_row = await db.fetch_one(
        """
        SELECT MAX(timestamp) AS timestamp
        FROM state_transition_log
        WHERE entity_type = 'task_status' AND entity_id = ?
        """,
        (blocker.id,),
    )
    assert transition_row is not None
    assert transition_row["timestamp"] == source_modified.isoformat()


@pytest.mark.asyncio
async def test_claudo_import_is_idempotent(
    db: Database,
    event_store: EventStore,
    revision_store: RevisionStore,
    metrics_collector: MetricsCollector,
    task_repo: TaskRepository,
) -> None:
    interop = ClaudoInteropService(
        db,
        event_store,
        revision_store,
        metrics_collector,
    )
    graph = _sample_graph()

    first = await interop.import_graph(graph)
    second = await interop.import_graph(graph)

    assert first.tasks_created == 2
    assert second.tasks_created == 0
    assert second.dependencies_created == 0
    assert second.dependencies_reused == 1

    task_service = TaskService(db, event_store, revision_store, metrics_collector)
    tasks = await task_service.list_tasks(
        project_id=first.project_ids["session-a"],
        include_subtasks=True,
        limit=10,
        offset=0,
    )
    assert tasks.total_count == 2

    blocked = await task_service.get_task(first.task_ids["session-a:2"])
    assert blocked is not None
    dependencies = await task_repo.get_dependencies(blocked.id)
    assert len(dependencies) == 1


@pytest.mark.asyncio
async def test_export_project_emits_claudo_graph(
    db: Database,
    event_store: EventStore,
    revision_store: RevisionStore,
    metrics_collector: MetricsCollector,
) -> None:
    project_service = ProjectService(db, event_store, revision_store, metrics_collector)
    task_service = TaskService(db, event_store, revision_store, metrics_collector)
    interop = ClaudoInteropService(
        db,
        event_store,
        revision_store,
        metrics_collector,
    )
    project = await project_service.create_project("Exported Project")
    blocker = await task_service.create_task(project.id, "First")
    blocked = await task_service.create_task(project.id, "Second")
    await task_service.add_dependency(blocked.id, blocker.id, DependencyType.BLOCKS)
    await task_service.complete_task(blocker.id)

    payload = await interop.export_project(project.id, session_id="pms-session")

    assert payload["schema_version"] == CLAUDO_SCHEMA_VERSION
    assert payload["source"] == "pms"
    assert payload["summary"]["task_count"] == 2
    assert payload["summary"]["edge_count"] == 1
    assert {task["uid"] for task in payload["tasks"]} == {
        f"pms-session:{blocker.id}",
        f"pms-session:{blocked.id}",
    }
    assert len(payload["edges"]) == 1
    edge = payload["edges"][0]
    assert edge["uid"] == f"pms-session:{blocker.id}->pms-session:{blocked.id}"
    assert edge["kind"] == "blocks"
    assert edge["blocker"] == {
        "session_id": "pms-session",
        "task_id": blocker.id,
        "uid": f"pms-session:{blocker.id}",
    }
    assert edge["blocked"] == {
        "session_id": "pms-session",
        "task_id": blocked.id,
        "uid": f"pms-session:{blocked.id}",
    }
    assert edge["evidence"][0].startswith("pms:")
