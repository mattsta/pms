"""Claudo task graph import/export adapter."""

from __future__ import annotations

import json
import subprocess
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.models import (
    CustomFieldDefinition,
    CustomFieldType,
    DependencyType,
    GoalHorizon,
    GoalStatus,
    PlanFormat,
    PlanStatus,
    Priority,
    Project,
    Task,
    TaskStatus,
)
from pms.models.json_types import JsonObject
from pms.repositories.task_repository import TaskRepository
from pms.services.custom_field_service import CustomFieldService
from pms.services.goal_service import GoalService
from pms.services.plan_service import PlanService
from pms.services.project_service import ProjectService
from pms.services.task_service import TaskService

if TYPE_CHECKING:
    from pms.db.connection import Database


CLAUDO_SCHEMA_VERSION = "claudo.task_graph.v1"
CLAUDO_SOURCE = "claudo"

FIELD_CLAUDO_PROJECT_KEY = "claudo_project_key"
FIELD_CLAUDO_SESSION_ID = "claudo_session_id"
FIELD_CLAUDO_TASK_UID = "claudo_uid"
FIELD_CLAUDO_METADATA = "claudo_metadata"


@dataclass(frozen=True)
class ClaudoTaskRef:
    """Stable Claudo task reference."""

    session_id: str
    task_id: str

    @property
    def uid(self) -> str:
        return f"{self.session_id}:{self.task_id}"

    @classmethod
    def from_payload(cls, payload: Any) -> ClaudoTaskRef | None:
        if not isinstance(payload, dict):
            return None
        session_id = str(payload.get("session_id") or "").strip()
        task_id = str(payload.get("task_id") or "").strip()
        if not session_id or not task_id:
            raw_uid = str(payload.get("uid") or "")
            if ":" in raw_uid:
                session_id, task_id = raw_uid.split(":", 1)
        if not session_id or not task_id:
            return None
        return cls(session_id=session_id, task_id=task_id)

    def to_dict(self) -> dict[str, str]:
        return {
            "session_id": self.session_id,
            "task_id": self.task_id,
            "uid": self.uid,
        }


@dataclass(frozen=True)
class ClaudoTaskRecord:
    """Task record from Claudo interchange JSON."""

    source: str
    session_id: str
    task_id: str
    subject: str
    description: str
    status: str
    active_form: str
    owner: str | None
    blocks: tuple[str, ...]
    blocked_by: tuple[str, ...]
    path: str | None
    source_created_at: str | None
    source_modified_at: str | None
    metadata: dict[str, Any]
    raw: dict[str, Any]

    @property
    def ref(self) -> ClaudoTaskRef:
        return ClaudoTaskRef(self.session_id, self.task_id)

    @property
    def uid(self) -> str:
        return self.ref.uid

    @classmethod
    def from_payload(cls, payload: Any) -> ClaudoTaskRecord | None:
        if not isinstance(payload, dict):
            return None
        session_id = _payload_text(payload.get("session_id"))
        task_id = _payload_text(payload.get("task_id"))
        raw_uid = _payload_text(payload.get("uid"))
        if (not session_id or not task_id) and ":" in raw_uid:
            session_id, task_id = raw_uid.split(":", 1)
        if not session_id or not task_id:
            return None
        metadata = payload.get("metadata")
        return cls(
            source=_payload_text(payload.get("source"), default="claudo"),
            session_id=session_id,
            task_id=task_id,
            subject=_payload_text(payload.get("subject")),
            description=_payload_text(payload.get("description")),
            status=_payload_text(payload.get("status"), default="unknown"),
            active_form=_payload_text(payload.get("active_form")),
            owner=_optional_payload_text(payload.get("owner")),
            blocks=_payload_text_tuple(payload.get("blocks")),
            blocked_by=_payload_text_tuple(payload.get("blocked_by")),
            path=_optional_payload_text(payload.get("path")),
            source_created_at=_optional_payload_text(payload.get("source_created_at")),
            source_modified_at=_optional_payload_text(
                payload.get("source_modified_at")
            ),
            metadata=dict(metadata) if isinstance(metadata, dict) else {},
            raw=dict(payload),
        )

    def to_interchange(self) -> dict[str, Any]:
        return {
            "uid": self.uid,
            "source": self.source,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "subject": self.subject,
            "description": self.description,
            "status": self.status,
            "active_form": self.active_form,
            "owner": self.owner,
            "blocks": list(self.blocks),
            "blocked_by": list(self.blocked_by),
            "path": self.path,
            "source_created_at": self.source_created_at,
            "source_modified_at": self.source_modified_at,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class ClaudoEdgeRecord:
    """Claudo dependency edge from blocker to blocked task."""

    blocker: ClaudoTaskRef
    blocked: ClaudoTaskRef
    evidence: tuple[str, ...] = ()

    @property
    def uid(self) -> str:
        return f"{self.blocker.uid}->{self.blocked.uid}"

    @classmethod
    def from_payload(cls, payload: Any) -> ClaudoEdgeRecord | None:
        if not isinstance(payload, dict):
            return None
        blocker = ClaudoTaskRef.from_payload(payload.get("blocker"))
        blocked = ClaudoTaskRef.from_payload(payload.get("blocked"))
        if blocker is None or blocked is None:
            return None
        return cls(
            blocker=blocker,
            blocked=blocked,
            evidence=_payload_text_tuple(payload.get("evidence")),
        )

    def to_interchange(self) -> dict[str, Any]:
        return {
            "uid": self.uid,
            "kind": "blocks",
            "blocker": self.blocker.to_dict(),
            "blocked": self.blocked.to_dict(),
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class ClaudoSessionMetadata:
    """Session metadata carried by Claudo interchange."""

    session_id: str
    label: str | None = None
    summary: str | None = None
    project_path: str | None = None
    project_key: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Any) -> ClaudoSessionMetadata | None:
        if not isinstance(payload, dict):
            return None
        session_id = _payload_text(payload.get("session_id"))
        if not session_id:
            return None
        return cls(
            session_id=session_id,
            label=_optional_payload_text(payload.get("label")),
            summary=_optional_payload_text(payload.get("summary")),
            project_path=_optional_payload_text(payload.get("project_path")),
            project_key=_optional_payload_text(payload.get("project_key")),
            raw=dict(payload),
        )

    @property
    def display_name(self) -> str:
        return (
            self.label
            or self.summary
            or _path_name(self.project_path)
            or self.project_key
            or self.session_id[:8]
        )


@dataclass(frozen=True)
class ClaudoGraph:
    """Parsed Claudo interchange graph."""

    schema_version: str
    source: str
    source_path: str | None
    loaded_at: str | None
    summary: dict[str, Any]
    source_hierarchy: dict[str, Any]
    session_metadata: dict[str, ClaudoSessionMetadata]
    tasks: list[ClaudoTaskRecord]
    edges: list[ClaudoEdgeRecord]
    diagnostics: list[dict[str, Any]]
    raw: dict[str, Any]

    @property
    def task_by_uid(self) -> dict[str, ClaudoTaskRecord]:
        return {task.uid: task for task in self.tasks}

    @property
    def session_ids(self) -> list[str]:
        sessions = {task.session_id for task in self.tasks}
        sessions.update(self.session_metadata)
        return sorted(sessions)

    @classmethod
    def from_payload(cls, payload: Any) -> ClaudoGraph:
        if not isinstance(payload, dict):
            raise ValueError("Claudo interchange must be a JSON object.")

        tasks = [
            task
            for task in (
                ClaudoTaskRecord.from_payload(item)
                for item in _payload_items(payload.get("tasks"))
            )
            if task is not None
        ]
        edges = [
            edge
            for edge in (
                ClaudoEdgeRecord.from_payload(item)
                for item in _payload_items(payload.get("edges"))
            )
            if edge is not None
        ]
        metadata_items = [
            item
            for item in (
                ClaudoSessionMetadata.from_payload(raw)
                for raw in _payload_items(payload.get("session_metadata"))
            )
            if item is not None
        ]
        diagnostics = [
            dict(item) for item in _payload_items(payload.get("diagnostics"))
        ]
        summary = payload.get("summary")
        source_hierarchy = payload.get("source_hierarchy")
        return cls(
            schema_version=_payload_text(payload.get("schema_version")),
            source=_payload_text(payload.get("source"), default="unified"),
            source_path=_optional_payload_text(payload.get("source_path")),
            loaded_at=_optional_payload_text(payload.get("loaded_at")),
            summary=dict(summary) if isinstance(summary, dict) else {},
            source_hierarchy=(
                dict(source_hierarchy) if isinstance(source_hierarchy, dict) else {}
            ),
            session_metadata={
                metadata.session_id: metadata for metadata in metadata_items
            },
            tasks=tasks,
            edges=edges,
            diagnostics=diagnostics,
            raw=dict(payload),
        )


@dataclass(frozen=True)
class ClaudoCommandResult:
    """Result from shelling out to Claudo."""

    returncode: int
    stdout: str
    stderr: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


@dataclass(frozen=True)
class ClaudoProjectFilterResult:
    """Filtered graph scoped to one repository/project root."""

    graph: ClaudoGraph
    project_root: str
    project_key: str
    matched_sessions: tuple[str, ...]
    tasks_before: int
    edges_before: int
    tasks_after: int
    edges_after: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_root": self.project_root,
            "project_key": self.project_key,
            "matched_sessions": list(self.matched_sessions),
            "tasks_before": self.tasks_before,
            "edges_before": self.edges_before,
            "tasks_after": self.tasks_after,
            "edges_after": self.edges_after,
        }


@dataclass(frozen=True)
class ClaudoImportOptions:
    """Import behavior options."""

    dry_run: bool = False
    project_name: str | None = None
    project_prefix: str = ""
    create_goals: bool = True
    create_plans: bool = True


@dataclass
class ClaudoImportResult:
    """Import operation summary."""

    dry_run: bool
    schema_version: str
    source: str
    source_path: str | None
    sessions: int
    tasks_seen: int
    edges_seen: int
    projects_created: int = 0
    projects_reused: int = 0
    goals_created: int = 0
    goals_updated: int = 0
    goals_reused: int = 0
    plans_created: int = 0
    plans_updated: int = 0
    plans_reused: int = 0
    tasks_created: int = 0
    tasks_updated: int = 0
    tasks_reused: int = 0
    dependencies_created: int = 0
    dependencies_reused: int = 0
    dependencies_missing: int = 0
    status_changes: int = 0
    warnings: list[str] = field(default_factory=list)
    project_ids: dict[str, str] = field(default_factory=dict)
    goal_ids: dict[str, str] = field(default_factory=dict)
    plan_ids: dict[str, str] = field(default_factory=dict)
    task_ids: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "schema_version": self.schema_version,
            "source": self.source,
            "source_path": self.source_path,
            "sessions": self.sessions,
            "tasks_seen": self.tasks_seen,
            "edges_seen": self.edges_seen,
            "projects_created": self.projects_created,
            "projects_reused": self.projects_reused,
            "goals_created": self.goals_created,
            "goals_updated": self.goals_updated,
            "goals_reused": self.goals_reused,
            "plans_created": self.plans_created,
            "plans_updated": self.plans_updated,
            "plans_reused": self.plans_reused,
            "tasks_created": self.tasks_created,
            "tasks_updated": self.tasks_updated,
            "tasks_reused": self.tasks_reused,
            "dependencies_created": self.dependencies_created,
            "dependencies_reused": self.dependencies_reused,
            "dependencies_missing": self.dependencies_missing,
            "status_changes": self.status_changes,
            "warnings": self.warnings,
            "project_ids": self.project_ids,
            "goal_ids": self.goal_ids,
            "plan_ids": self.plan_ids,
            "task_ids": self.task_ids,
        }


def load_claudo_graph(path: str | Path) -> ClaudoGraph:
    """Load a Claudo interchange JSON file."""

    graph_path = Path(path).expanduser()
    payload = json.loads(graph_path.read_text(encoding="utf-8"))
    return ClaudoGraph.from_payload(payload)


def write_claudo_graph(payload: dict[str, Any], path: str | Path) -> None:
    """Write a Claudo interchange JSON payload."""

    output_path = Path(path).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def filter_claudo_graph_for_project(
    graph: ClaudoGraph,
    project_root: str | Path,
) -> ClaudoProjectFilterResult:
    """Return a graph containing only Claudo sessions for one project root."""

    root_path = _normalized_project_path(project_root)
    project_key = _claude_project_key(root_path)
    matched_sessions = _matching_project_sessions(
        graph.raw,
        root_path=root_path,
        project_key=project_key,
    )
    if not matched_sessions:
        raise ValueError(
            "No Claudo sessions matched project root "
            f"{root_path!r} or project key {project_key!r}."
        )

    matched_session_set = set(matched_sessions)
    task_payloads = [
        dict(task)
        for task in _payload_items(graph.raw.get("tasks"))
        if _payload_text(task.get("session_id")) in matched_session_set
    ]
    task_uids = {uid for task in task_payloads if (uid := _task_payload_uid(task))}
    edge_payloads = []
    for edge in _payload_items(graph.raw.get("edges")):
        edge_uids = _edge_payload_uids(edge)
        if len(edge_uids) == 2 and edge_uids <= task_uids:
            edge_payloads.append(dict(edge))
    metadata_payloads = [
        dict(metadata)
        for metadata in _payload_items(graph.raw.get("session_metadata"))
        if _payload_text(metadata.get("session_id")) in matched_session_set
    ]
    diagnostics = [
        dict(diagnostic)
        for diagnostic in _payload_items(graph.raw.get("diagnostics"))
        if _diagnostic_matches_project(diagnostic, matched_session_set, task_uids)
    ]

    filtered_payload = dict(graph.raw)
    filtered_payload["session_metadata"] = metadata_payloads
    filtered_payload["tasks"] = task_payloads
    filtered_payload["edges"] = edge_payloads
    filtered_payload["diagnostics"] = diagnostics
    filtered_payload["source_hierarchy"] = _filter_source_hierarchy_for_sessions(
        graph.raw.get("source_hierarchy"),
        matched_session_set,
        task_uids,
        edge_payloads,
        task_payloads,
    )
    filtered_payload["summary"] = _build_filtered_summary(
        task_payloads,
        edge_payloads,
        diagnostics,
        metadata_payloads,
        matched_sessions,
    )

    filtered_graph = ClaudoGraph.from_payload(filtered_payload)
    return ClaudoProjectFilterResult(
        graph=filtered_graph,
        project_root=root_path,
        project_key=project_key,
        matched_sessions=matched_sessions,
        tasks_before=len(graph.tasks),
        edges_before=len(graph.edges),
        tasks_after=len(filtered_graph.tasks),
        edges_after=len(filtered_graph.edges),
    )


def run_claudo_export(
    *,
    claudo_repo: str | Path,
    source_path: str | Path,
    session_id: str | None = None,
) -> ClaudoGraph:
    """Run `claudo export` and parse the emitted interchange graph."""

    command = [
        "uv",
        "run",
        "--directory",
        str(Path(claudo_repo).expanduser()),
        "claudo",
        "export",
        str(Path(source_path).expanduser()),
        "--format",
        "json",
    ]
    if session_id:
        command.extend(["--session", session_id])
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "Claudo export failed "
            f"(exit {completed.returncode}): {completed.stderr.strip()}"
        )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Claudo export did not emit valid JSON.") from exc
    return ClaudoGraph.from_payload(payload)


def materialize_claude_export(
    *,
    claudo_repo: str | Path,
    graph_path: str | Path,
    output_dir: str | Path,
    overwrite: bool = False,
) -> ClaudoCommandResult:
    """Run Claudo's Claude-layout materializer for a PMS-produced graph."""

    command = [
        "uv",
        "run",
        "--directory",
        str(Path(claudo_repo).expanduser()),
        "claudo",
        "materialize-claude",
        str(Path(graph_path).expanduser()),
        str(Path(output_dir).expanduser()),
    ]
    if overwrite:
        command.append("--overwrite")
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "Claudo materialize-claude failed "
            f"(exit {completed.returncode}): {completed.stderr.strip()}"
        )
    return ClaudoCommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


class ClaudoInteropService:
    """Import Claudo graphs into PMS and export PMS projects as Claudo graphs."""

    def __init__(
        self,
        db: Database,
        event_store: EventStore,
        revision_store: RevisionStore,
        metrics: MetricsCollector,
    ) -> None:
        self.db = db
        self.event_store = event_store
        self.revision_store = revision_store
        self.metrics = metrics
        self.projects = ProjectService(db, event_store, revision_store, metrics)
        self.tasks = TaskService(db, event_store, revision_store, metrics)
        self.goals = GoalService(db, event_store, revision_store, metrics)
        self.plans = PlanService(db, event_store, revision_store, metrics)
        self.custom_fields = CustomFieldService(db, metrics)
        self.task_repo = TaskRepository(db, event_store, revision_store, metrics)

    async def import_graph(
        self,
        graph: ClaudoGraph,
        options: ClaudoImportOptions | None = None,
    ) -> ClaudoImportResult:
        """Import a Claudo task graph into PMS using PMS services."""

        options = options or ClaudoImportOptions()
        result = ClaudoImportResult(
            dry_run=options.dry_run,
            schema_version=graph.schema_version,
            source=graph.source,
            source_path=graph.source_path,
            sessions=len(graph.session_ids),
            tasks_seen=len(graph.tasks),
            edges_seen=len(graph.edges),
            warnings=self._graph_warnings(graph),
        )

        project_lookup = await self._external_value_lookup(
            "project", FIELD_CLAUDO_PROJECT_KEY
        )
        task_lookup = await self._external_value_lookup("task", FIELD_CLAUDO_TASK_UID)
        goal_lookup = await self._external_value_lookup("goal", FIELD_CLAUDO_SESSION_ID)
        plan_lookup = await self._external_value_lookup("plan", FIELD_CLAUDO_SESSION_ID)

        if options.dry_run:
            await self._preview_import(
                graph,
                options,
                result,
                project_lookup=project_lookup,
                task_lookup=task_lookup,
                goal_lookup=goal_lookup,
                plan_lookup=plan_lookup,
            )
            return result

        await self._ensure_claudo_fields()

        hierarchy_index = _source_hierarchy_task_index(graph.source_hierarchy)
        project_by_session = await self._ensure_projects(
            graph,
            options,
            result,
            project_lookup,
        )
        pms_task_by_uid = await self._ensure_tasks(
            graph,
            options,
            result,
            task_lookup,
            project_by_session,
            hierarchy_index,
        )
        await self._ensure_dependencies(graph, result, pms_task_by_uid)
        await self._reconcile_statuses(graph, result, pms_task_by_uid)
        if options.create_goals:
            goal_by_session = await self._ensure_goals(
                graph,
                result,
                goal_lookup,
                project_by_session,
            )
        else:
            goal_by_session = {}
        if options.create_plans:
            await self._ensure_plans(
                graph,
                result,
                plan_lookup,
                project_by_session,
                pms_task_by_uid,
                goal_by_session,
            )
        await self._reconcile_import_timestamps(graph, result)
        return result

    async def export_project(
        self,
        project_id: str,
        *,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Export one PMS project into Claudo interchange JSON."""

        project = await self.projects.get_project(project_id)
        if project is None:
            raise ValueError(f"Project not found: {project_id}")

        result = await self.tasks.list_tasks(
            project_id=project.id,
            include_subtasks=True,
            limit=100000,
            offset=0,
        )
        tasks = list(result.items)
        export_session_id = session_id or f"pms-{project.id}"
        pms_uid_by_task_id = {
            task.id: f"{export_session_id}:{task.id}" for task in tasks
        }

        edges, skipped_dependencies = await self._project_edges_for_export(
            tasks,
            export_session_id,
        )
        blocks_by_task_id: dict[str, list[str]] = defaultdict(list)
        blocked_by_task_id: dict[str, list[str]] = defaultdict(list)
        for edge in edges:
            blocks_by_task_id[edge.blocker.task_id].append(edge.blocked.task_id)
            blocked_by_task_id[edge.blocked.task_id].append(edge.blocker.task_id)

        task_payloads = [
            {
                "uid": pms_uid_by_task_id[task.id],
                "source": "pms",
                "session_id": export_session_id,
                "task_id": task.id,
                "subject": task.title,
                "description": task.description or "",
                "status": _pms_status_to_claudo(task.status),
                "active_form": task.title
                if task.status == TaskStatus.IN_PROGRESS
                else "",
                "owner": task.assignee,
                "blocks": sorted(blocks_by_task_id.get(task.id, [])),
                "blocked_by": sorted(blocked_by_task_id.get(task.id, [])),
                "path": None,
                "source_created_at": task.created_at.isoformat(),
                "source_modified_at": task.updated_at.isoformat(),
                "metadata": _export_task_metadata(task, project),
            }
            for task in tasks
        ]
        edge_payloads = [edge.to_interchange() for edge in edges]
        diagnostics = [
            {
                "level": "warning",
                "message": (
                    "Skipped cross-project PMS dependency during Claudo export: "
                    f"{task_id} depends on {depends_on_id}."
                ),
                "path": None,
                "task_uid": pms_uid_by_task_id.get(task_id),
            }
            for task_id, depends_on_id in skipped_dependencies
        ]
        source_hierarchy = _build_export_hierarchy(
            project,
            export_session_id,
            task_payloads,
            edges,
        )
        summary = _build_export_summary(
            task_payloads,
            edges,
            diagnostics,
            export_session_id,
        )
        return {
            "schema_version": CLAUDO_SCHEMA_VERSION,
            "source": "pms",
            "source_path": None,
            "loaded_at": datetime.now(UTC).isoformat(),
            "summary": summary,
            "source_hierarchy": source_hierarchy,
            "session_metadata": [
                {
                    "session_id": export_session_id,
                    "label": project.name,
                    "summary": project.description,
                    "project_path": None,
                    "project_key": project.id,
                    "task_dir": None,
                    "project_dir": None,
                    "transcript_path": None,
                    "session_dir": None,
                    "session_env_dir": None,
                    "file_history_dir": None,
                    "created_at": project.created_at.isoformat(),
                    "modified_at": project.updated_at.isoformat(),
                    "message_count": None,
                    "git_branch": None,
                    "is_sidechain": None,
                    "source_paths": [],
                    "metadata": {
                        "pms_project_id": project.id,
                        "pms_project_status": project.status.value,
                        "pms_tags": list(project.tags),
                    },
                }
            ],
            "tasks": task_payloads,
            "edges": edge_payloads,
            "diagnostics": diagnostics,
        }

    async def _preview_import(
        self,
        graph: ClaudoGraph,
        options: ClaudoImportOptions,
        result: ClaudoImportResult,
        *,
        project_lookup: dict[str, str],
        task_lookup: dict[str, str],
        goal_lookup: dict[str, str],
        plan_lookup: dict[str, str],
    ) -> None:
        project_keys = {
            self._project_key_for_session(graph, options, session_id)
            for session_id in graph.session_ids
        }
        for key in project_keys:
            if key in project_lookup:
                result.projects_reused += 1
            else:
                result.projects_created += 1
        for session_id in graph.session_ids:
            if options.create_goals:
                if session_id in goal_lookup:
                    result.goals_reused += 1
                else:
                    result.goals_created += 1
            if options.create_plans:
                if session_id in plan_lookup:
                    result.plans_reused += 1
                else:
                    result.plans_created += 1
        graph_task_uids = {task.uid for task in graph.tasks}
        for task in graph.tasks:
            if task.uid in task_lookup:
                result.tasks_reused += 1
                result.task_ids[task.uid] = task_lookup[task.uid]
            else:
                result.tasks_created += 1
        for edge in graph.edges:
            if (
                edge.blocker.uid not in graph_task_uids
                or edge.blocked.uid not in graph_task_uids
            ):
                result.dependencies_missing += 1
                continue
            blocker_id = task_lookup.get(edge.blocker.uid)
            blocked_id = task_lookup.get(edge.blocked.uid)
            if blocker_id is None or blocked_id is None:
                result.dependencies_created += 1
                continue
            dependencies = await self.task_repo.get_dependencies(blocked_id)
            if any(
                dependency.depends_on_id == blocker_id
                and dependency.dependency_type == DependencyType.BLOCKS
                for dependency in dependencies
            ):
                result.dependencies_reused += 1
            else:
                result.dependencies_created += 1

    async def _ensure_claudo_fields(self) -> None:
        for entity_type in ("project", "goal", "plan", "task"):
            await self._ensure_field(
                entity_type,
                FIELD_CLAUDO_METADATA,
                CustomFieldType.JSON,
                "Raw Claudo/PMS interop metadata for this imported entity.",
            )
        await self._ensure_field(
            "project",
            FIELD_CLAUDO_PROJECT_KEY,
            CustomFieldType.TEXT,
            "Stable Claudo project key used for idempotent imports.",
        )
        await self._ensure_field(
            "goal",
            FIELD_CLAUDO_SESSION_ID,
            CustomFieldType.TEXT,
            "Claudo session id represented by this PMS goal.",
        )
        await self._ensure_field(
            "plan",
            FIELD_CLAUDO_SESSION_ID,
            CustomFieldType.TEXT,
            "Claudo session id represented by this PMS plan.",
        )
        await self._ensure_field(
            "task",
            FIELD_CLAUDO_TASK_UID,
            CustomFieldType.TEXT,
            "Claudo task uid in the form session_id:task_id.",
        )

    async def _ensure_field(
        self,
        entity_type: str,
        name: str,
        field_type: CustomFieldType,
        description: str,
    ) -> CustomFieldDefinition:
        existing = await self.custom_fields.get_definition_by_name(
            name,
            entity_type,
            include_archived=True,
        )
        if existing is not None:
            if existing.archived_at is not None:
                restored = await self.custom_fields.restore_definition(existing.id)
                if restored is not None:
                    return restored
            return existing
        return await self.custom_fields.create_definition(
            name=name,
            entity_type=entity_type,
            field_type=field_type,
            description=description,
        )

    async def _external_value_lookup(
        self,
        entity_type: str,
        field_name: str,
    ) -> dict[str, str]:
        definition = await self.custom_fields.get_definition_by_name(
            field_name,
            entity_type,
            include_archived=True,
        )
        if definition is None:
            return {}
        page = await self.custom_fields.list_values_for_field(
            definition.id,
            limit=100000,
            offset=0,
        )
        lookup: dict[str, str] = {}
        for item in page.items:
            key = _stable_external_value(item.value.value)
            if key and key not in lookup:
                lookup[key] = item.value.entity_id
        return lookup

    async def _ensure_projects(
        self,
        graph: ClaudoGraph,
        options: ClaudoImportOptions,
        result: ClaudoImportResult,
        project_lookup: dict[str, str],
    ) -> dict[str, Project]:
        project_by_session: dict[str, Project] = {}
        for session_id in graph.session_ids:
            key = self._project_key_for_session(graph, options, session_id)
            name = self._project_name_for_session(graph, options, session_id)
            project = None
            if key in project_lookup:
                project = await self.projects.get_project(project_lookup[key])
            if project is None:
                project = await self.projects.get_project_by_name(name)
            if project is None:
                project = await self.projects.create_project(
                    name=name,
                    description="Imported from Claudo task graph.",
                    tags=["claudo-import"],
                )
                result.projects_created += 1
            else:
                result.projects_reused += 1
            await self._set_custom_value(
                "project",
                project.id,
                FIELD_CLAUDO_PROJECT_KEY,
                key,
                metadata={"session_id": session_id},
            )
            await self._set_custom_value(
                "project",
                project.id,
                FIELD_CLAUDO_METADATA,
                {
                    "source": graph.source,
                    "source_path": graph.source_path,
                    "project_hint": self._project_hint_for_session(graph, session_id),
                },
                metadata={"session_id": session_id},
            )
            result.project_ids[session_id] = project.id
            project_by_session[session_id] = project
        return project_by_session

    async def _ensure_tasks(
        self,
        graph: ClaudoGraph,
        options: ClaudoImportOptions,
        result: ClaudoImportResult,
        task_lookup: dict[str, str],
        project_by_session: dict[str, Project],
        hierarchy_index: dict[str, dict[str, Any]],
    ) -> dict[str, Task]:
        pms_task_by_uid: dict[str, Task] = {}
        for task_record in graph.tasks:
            project = project_by_session[task_record.session_id]
            title = _task_title(task_record)
            description = _task_description(task_record)
            existing = None
            if task_record.uid in task_lookup:
                existing = await self.tasks.get_task(task_lookup[task_record.uid])
            if existing is None:
                task = await self.tasks.create_task(
                    project_id=project.id,
                    title=title,
                    description=description,
                    priority=Priority.MEDIUM,
                    assignee=task_record.owner,
                    tags=[
                        "claudo-import",
                        f"claudo-session:{task_record.session_id}",
                    ],
                )
                result.tasks_created += 1
            else:
                task = existing
                if _task_needs_update(task, title, description, task_record.owner):
                    updated = await self.tasks.update_task(
                        task.id,
                        title=title,
                        description=description,
                        assignee=task_record.owner,
                        clear_assignee=task_record.owner is None,
                    )
                    if updated is not None:
                        task = updated
                    result.tasks_updated += 1
                else:
                    result.tasks_reused += 1
            await self._set_custom_value(
                "task",
                task.id,
                FIELD_CLAUDO_TASK_UID,
                task_record.uid,
                metadata={"session_id": task_record.session_id},
            )
            await self._set_custom_value(
                "task",
                task.id,
                FIELD_CLAUDO_METADATA,
                _task_import_metadata(
                    task_record, hierarchy_index.get(task_record.uid)
                ),
                metadata={"session_id": task_record.session_id},
            )
            result.task_ids[task_record.uid] = task.id
            pms_task_by_uid[task_record.uid] = task
        return pms_task_by_uid

    async def _ensure_dependencies(
        self,
        graph: ClaudoGraph,
        result: ClaudoImportResult,
        pms_task_by_uid: dict[str, Task],
    ) -> None:
        for edge in graph.edges:
            blocker = pms_task_by_uid.get(edge.blocker.uid)
            blocked = pms_task_by_uid.get(edge.blocked.uid)
            if blocker is None or blocked is None:
                result.dependencies_missing += 1
                result.warnings.append(
                    f"Missing PMS task for Claudo edge {edge.uid}; dependency skipped."
                )
                continue
            existing = await self.task_repo.get_dependencies(blocked.id)
            if any(
                dependency.depends_on_id == blocker.id
                and dependency.dependency_type == DependencyType.BLOCKS
                for dependency in existing
            ):
                result.dependencies_reused += 1
                continue
            try:
                dependency = await self.tasks.add_dependency(
                    task_id=blocked.id,
                    depends_on_id=blocker.id,
                    dependency_type=DependencyType.BLOCKS,
                )
            except ValueError as exc:
                result.warnings.append(f"Could not import dependency {edge.uid}: {exc}")
                continue
            if dependency is not None:
                result.dependencies_created += 1

    async def _reconcile_statuses(
        self,
        graph: ClaudoGraph,
        result: ClaudoImportResult,
        pms_task_by_uid: dict[str, Task],
    ) -> None:
        for task_record in graph.tasks:
            task = pms_task_by_uid.get(task_record.uid)
            if task is None:
                continue
            changed = await self._reconcile_task_status(task.id, task_record.status)
            if changed:
                result.status_changes += 1

    async def _reconcile_task_status(self, task_id: str, raw_status: str) -> bool:
        target = _claudo_status_to_pms(raw_status)
        task = await self.tasks.get_task(task_id)
        if task is None or task.status == target:
            return False

        if task.status.is_terminal and target != task.status:
            await self.tasks.reopen_task(task.id)
            task = await self.tasks.get_task(task_id)
            if task is None:
                return False

        if target == TaskStatus.TODO:
            if task.status == TaskStatus.BLOCKED:
                if await self._has_open_blockers(task.id):
                    return False
                await self.tasks.unblock_task(task.id)
                return True
            return False
        if target == TaskStatus.IN_PROGRESS:
            await self.tasks.start_task(task.id, reason="Claudo import status sync")
            return True
        if target == TaskStatus.IN_REVIEW:
            if task.status != TaskStatus.IN_PROGRESS:
                await self.tasks.start_task(task.id, reason="Claudo import status sync")
            await self.tasks.submit_for_review(task.id)
            return True
        if target == TaskStatus.BLOCKED:
            await self.tasks.block_task(task.id, reason="Claudo import status sync")
            return True
        if target == TaskStatus.DONE:
            await self.tasks.complete_task(task.id, notes="Claudo import status sync")
            return True
        if target == TaskStatus.CANCELLED:
            await self.tasks.cancel_task(task.id, reason="Claudo import status sync")
            return True
        return False

    async def _has_open_blockers(self, task_id: str) -> bool:
        dependencies = await self.task_repo.get_dependencies(task_id)
        for dependency in dependencies:
            if dependency.dependency_type != DependencyType.BLOCKS:
                continue
            blocker = await self.tasks.get_task(dependency.depends_on_id)
            if blocker is not None and blocker.status != TaskStatus.DONE:
                return True
        return False

    async def _ensure_goals(
        self,
        graph: ClaudoGraph,
        result: ClaudoImportResult,
        goal_lookup: dict[str, str],
        project_by_session: dict[str, Project],
    ) -> dict[str, str]:
        goal_by_session: dict[str, str] = {}
        tasks_by_session = _tasks_by_session(graph.tasks)
        for session_id in graph.session_ids:
            project = project_by_session[session_id]
            session_tasks = tasks_by_session.get(session_id, [])
            progress = _completion_percent(session_tasks)
            target_status = (
                GoalStatus.COMPLETED
                if progress == 100 and session_tasks
                else GoalStatus.ACTIVE
            )
            metadata = graph.session_metadata.get(session_id)
            name = f"Claudo: {metadata.display_name if metadata else session_id[:8]}"
            description = (
                metadata.summary
                if metadata and metadata.summary
                else "Imported Claudo session."
            )
            goal_id = goal_lookup.get(session_id)
            goal = await self.goals.get_goal(goal_id) if goal_id else None
            if goal is None:
                goal = await self.goals.create_goal(
                    name=name,
                    description=description,
                    horizon=GoalHorizon.SHORT_TERM,
                    project_id=project.id,
                    tags=["claudo-import", f"claudo-session:{session_id}"],
                    progress_percent=progress,
                )
                result.goals_created += 1
            else:
                updated = await self.goals.update_goal(
                    goal.id,
                    name=name,
                    description=description,
                    status=target_status,
                    project_id=project.id,
                    progress_percent=progress,
                )
                if updated is not None:
                    goal = updated
                    result.goals_updated += 1
                else:
                    result.goals_reused += 1
            if goal.status != target_status:
                updated = await self.goals.update_goal(
                    goal.id,
                    status=target_status,
                    progress_percent=progress,
                )
                if updated is not None:
                    goal = updated
            await self._set_custom_value(
                "goal",
                goal.id,
                FIELD_CLAUDO_SESSION_ID,
                session_id,
                metadata={"session_id": session_id},
            )
            await self._set_custom_value(
                "goal",
                goal.id,
                FIELD_CLAUDO_METADATA,
                {
                    "session_metadata": metadata.raw if metadata else {},
                    "status_counts": dict(
                        Counter(task.status for task in session_tasks)
                    ),
                    "source": graph.source,
                    "source_path": graph.source_path,
                },
                metadata={"session_id": session_id},
            )
            result.goal_ids[session_id] = goal.id
            goal_by_session[session_id] = goal.id
        return goal_by_session

    async def _ensure_plans(
        self,
        graph: ClaudoGraph,
        result: ClaudoImportResult,
        plan_lookup: dict[str, str],
        project_by_session: dict[str, Project],
        pms_task_by_uid: dict[str, Task],
        goal_by_session: dict[str, str],
    ) -> None:
        tasks_by_session = _tasks_by_session(graph.tasks)
        for session_id in graph.session_ids:
            project = project_by_session[session_id]
            session_tasks = tasks_by_session.get(session_id, [])
            pms_task_ids = [
                pms_task_by_uid[task.uid].id
                for task in session_tasks
                if task.uid in pms_task_by_uid
            ]
            metadata = graph.session_metadata.get(session_id)
            name = f"Claudo Import: {metadata.display_name if metadata else session_id[:8]}"
            content: dict[str, Any] = {
                "schema": "pms.claudo_import_plan.v1",
                "claudo_schema_version": graph.schema_version,
                "source": graph.source,
                "source_path": graph.source_path,
                "session_id": session_id,
                "session_metadata": metadata.raw if metadata else {},
                "task_uids": [task.uid for task in session_tasks],
                "edge_uids": [
                    edge.uid
                    for edge in graph.edges
                    if edge.blocker.session_id == session_id
                    or edge.blocked.session_id == session_id
                ],
            }
            content_payload = cast(JsonObject, content)
            plan_id = plan_lookup.get(session_id)
            plan = await self.plans.get_plan(plan_id) if plan_id else None
            if plan is None:
                plan = await self.plans.create_plan(
                    name=name,
                    description="Claudo import session plan.",
                    status=PlanStatus.ACTIVE,
                    format=PlanFormat.JSON,
                    content=content_payload,
                    project_id=project.id,
                    goal_id=goal_by_session.get(session_id),
                    task_ids=pms_task_ids,
                    tags=["claudo-import", f"claudo-session:{session_id}"],
                    message="Created Claudo import plan",
                )
                result.plans_created += 1
            else:
                updated = await self.plans.update_plan(
                    plan.id,
                    name=name,
                    description="Claudo import session plan.",
                    status=PlanStatus.ACTIVE,
                    format=PlanFormat.JSON,
                    content=content_payload,
                    project_id=project.id,
                    goal_id=goal_by_session.get(session_id),
                    task_ids=pms_task_ids,
                    tags=["claudo-import", f"claudo-session:{session_id}"],
                    message="Updated Claudo import plan",
                )
                if updated is not None:
                    plan = updated
                    result.plans_updated += 1
                else:
                    result.plans_reused += 1
            await self._set_custom_value(
                "plan",
                plan.id,
                FIELD_CLAUDO_SESSION_ID,
                session_id,
                metadata={"session_id": session_id},
            )
            await self._set_custom_value(
                "plan",
                plan.id,
                FIELD_CLAUDO_METADATA,
                content_payload,
                metadata={"session_id": session_id},
            )
            result.plan_ids[session_id] = plan.id

    async def _reconcile_import_timestamps(
        self,
        graph: ClaudoGraph,
        result: ClaudoImportResult,
    ) -> None:
        """Project source Claudo timestamps onto imported PMS rows."""

        session_created: dict[str, datetime] = {}
        session_modified: dict[str, datetime] = {}

        for task_record in graph.tasks:
            pms_task_id = result.task_ids.get(task_record.uid)
            if pms_task_id is None:
                continue

            created_at = _parse_import_datetime(task_record.source_created_at)
            modified_at = _parse_import_datetime(task_record.source_modified_at)
            source_created = created_at or modified_at
            source_modified = modified_at or created_at
            if source_created is None or source_modified is None:
                continue

            session_created[task_record.session_id] = min(
                session_created.get(task_record.session_id, source_created),
                source_created,
            )
            session_modified[task_record.session_id] = max(
                session_modified.get(task_record.session_id, source_modified),
                source_modified,
            )

            created_iso = source_created.isoformat()
            modified_iso = source_modified.isoformat()
            await self.db.execute(
                """
                UPDATE tasks
                SET created_at = ?,
                    updated_at = ?,
                    completed_at = CASE WHEN status = 'done' THEN ? ELSE NULL END,
                    current_progress_percent = CASE
                        WHEN status = 'done' THEN 100
                        ELSE current_progress_percent
                    END,
                    last_progress_update_at = CASE
                        WHEN status = 'done' THEN ?
                        ELSE last_progress_update_at
                    END
                WHERE id = ?
                """,
                (created_iso, modified_iso, modified_iso, modified_iso, pms_task_id),
            )
            await self._set_import_entity_timestamps(
                entity_type="task",
                entity_id=pms_task_id,
                created_at=source_created,
                updated_at=source_modified,
                status_transition_at=source_modified,
            )

        for session_id in graph.session_ids:
            source_created = session_created.get(session_id)
            source_modified = session_modified.get(session_id)
            if source_created is None or source_modified is None:
                continue
            for entity_type, entity_id in (
                ("project", result.project_ids.get(session_id)),
                ("goal", result.goal_ids.get(session_id)),
                ("plan", result.plan_ids.get(session_id)),
            ):
                if entity_id is None:
                    continue
                await self._set_import_projection_timestamps(
                    entity_type,
                    entity_id,
                    created_at=source_created,
                    updated_at=source_modified,
                )
                await self._set_import_entity_timestamps(
                    entity_type=entity_type,
                    entity_id=entity_id,
                    created_at=source_created,
                    updated_at=source_modified,
                    status_transition_at=source_modified,
                )

    async def _set_import_projection_timestamps(
        self,
        entity_type: str,
        entity_id: str,
        *,
        created_at: datetime,
        updated_at: datetime,
    ) -> None:
        table_by_entity = {
            "project": "projects",
            "goal": "goals",
            "plan": "plans",
        }
        table = table_by_entity.get(entity_type)
        if table is None:
            return
        await self.db.execute(
            f"UPDATE {table} SET created_at = ?, updated_at = ? WHERE id = ?",
            (created_at.isoformat(), updated_at.isoformat(), entity_id),
        )

    async def _set_import_entity_timestamps(
        self,
        *,
        entity_type: str,
        entity_id: str,
        created_at: datetime,
        updated_at: datetime,
        status_transition_at: datetime,
    ) -> None:
        await self.db.execute(
            """
            UPDATE custom_field_values
            SET created_at = ?, updated_at = ?
            WHERE entity_type = ? AND entity_id = ? AND source = ?
            """,
            (
                created_at.isoformat(),
                updated_at.isoformat(),
                entity_type,
                entity_id,
                CLAUDO_SOURCE,
            ),
        )
        await self.db.execute(
            """
            UPDATE state_transition_log
            SET created_at = ?, timestamp = ?
            WHERE entity_type = ? AND entity_id = ?
            """,
            (
                status_transition_at.isoformat(),
                status_transition_at.isoformat(),
                f"{entity_type}_status",
                entity_id,
            ),
        )
        if entity_type == "task":
            await self.db.execute(
                """
                UPDATE task_state_transitions
                SET created_at = ?, timestamp = ?
                WHERE task_id = ?
                """,
                (
                    status_transition_at.isoformat(),
                    status_transition_at.isoformat(),
                    entity_id,
                ),
            )

    async def _set_custom_value(
        self,
        entity_type: str,
        entity_id: str,
        field_name: str,
        value: Any,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await self.custom_fields.set_value(
            field_name,
            entity_type=entity_type,
            entity_id=entity_id,
            value=value,
            created_by="claudo-import",
            source=CLAUDO_SOURCE,
            metadata=metadata,
        )

    async def _project_edges_for_export(
        self,
        tasks: list[Task],
        session_id: str,
    ) -> tuple[list[ClaudoEdgeRecord], list[tuple[str, str]]]:
        task_ids = {task.id for task in tasks}
        edges: list[ClaudoEdgeRecord] = []
        skipped: list[tuple[str, str]] = []
        for task in tasks:
            dependencies = await self.task_repo.get_dependencies(task.id)
            for dependency in dependencies:
                if dependency.dependency_type != DependencyType.BLOCKS:
                    continue
                if dependency.depends_on_id not in task_ids:
                    skipped.append((task.id, dependency.depends_on_id))
                    continue
                edges.append(
                    ClaudoEdgeRecord(
                        blocker=ClaudoTaskRef(session_id, dependency.depends_on_id),
                        blocked=ClaudoTaskRef(session_id, task.id),
                        evidence=(f"pms:{dependency.id}",),
                    )
                )
        return edges, skipped

    def _project_key_for_session(
        self,
        graph: ClaudoGraph,
        options: ClaudoImportOptions,
        session_id: str,
    ) -> str:
        if options.project_name:
            return f"forced:{options.project_name}"
        hint = self._project_hint_for_session(graph, session_id)
        metadata = graph.session_metadata.get(session_id)
        return (
            _optional_payload_text(hint.get("project_path"))
            or _optional_payload_text(hint.get("project_key"))
            or _optional_payload_text(hint.get("label"))
            or (metadata.project_path if metadata else None)
            or (metadata.project_key if metadata else None)
            or session_id
        )

    def _project_name_for_session(
        self,
        graph: ClaudoGraph,
        options: ClaudoImportOptions,
        session_id: str,
    ) -> str:
        if options.project_name:
            return options.project_name
        hint = self._project_hint_for_session(graph, session_id)
        metadata = graph.session_metadata.get(session_id)
        candidate = (
            _path_name(_optional_payload_text(hint.get("project_path")))
            or _decoded_project_label(_optional_payload_text(hint.get("label")))
            or _path_name(metadata.project_path if metadata else None)
            or (metadata.project_key if metadata else None)
            or _optional_payload_text(hint.get("project_key"))
            or f"Claudo {session_id[:8]}"
        )
        return f"{options.project_prefix}{candidate}"

    def _project_hint_for_session(
        self,
        graph: ClaudoGraph,
        session_id: str,
    ) -> dict[str, Any]:
        projects = graph.source_hierarchy.get("projects")
        if not isinstance(projects, list):
            return {}
        for project in projects:
            if not isinstance(project, dict):
                continue
            task_lists = project.get("task_lists")
            if not isinstance(task_lists, list):
                continue
            for task_list in task_lists:
                if not isinstance(task_list, dict):
                    continue
                if _payload_text(task_list.get("session_id")) == session_id:
                    return project
        return {}

    def _graph_warnings(self, graph: ClaudoGraph) -> list[str]:
        warnings = []
        if graph.schema_version != CLAUDO_SCHEMA_VERSION:
            warnings.append(
                "Imported Claudo graph has schema_version "
                f"{graph.schema_version!r}; expected {CLAUDO_SCHEMA_VERSION!r}."
            )
        for diagnostic in graph.diagnostics:
            level = _payload_text(diagnostic.get("level"), default="info")
            if level in {"warning", "error"}:
                message = _payload_text(diagnostic.get("message"))
                if message:
                    warnings.append(message)
        return warnings


def _payload_text(value: Any, *, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _optional_payload_text(value: Any) -> str | None:
    text = _payload_text(value)
    return text or None


def _parse_import_datetime(value: Any) -> datetime | None:
    text = _optional_payload_text(value)
    if text is None:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _payload_text_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(str(item) for item in value if str(item))


def _payload_items(value: Any) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list):
        return ()
    return tuple(dict(item) for item in value if isinstance(item, dict))


def _stable_external_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, int | float | bool):
        return str(value)
    return json.dumps(value, sort_keys=True, default=str)


def _path_name(value: str | None) -> str | None:
    if not value:
        return None
    name = Path(value).expanduser().name
    return name or None


def _decoded_project_label(label: str | None) -> str | None:
    if not label:
        return None
    text = label.strip()
    if not text:
        return None
    if "-repos-" in text:
        suffix = text.rsplit("-repos-", 1)[1].strip("-")
        return suffix or None
    return text.strip("-") or text


def _normalized_project_path(path: str | Path) -> str:
    return str(Path(path).expanduser().resolve(strict=False))


def _claude_project_key(project_root: str) -> str:
    return Path(project_root).as_posix().replace("/", "-")


def _matching_project_sessions(
    payload: dict[str, Any],
    *,
    root_path: str,
    project_key: str,
) -> tuple[str, ...]:
    sessions: set[str] = set()
    for metadata in _payload_items(payload.get("session_metadata")):
        session_id = _payload_text(metadata.get("session_id"))
        if session_id and _project_marker_matches(
            metadata, root_path=root_path, project_key=project_key
        ):
            sessions.add(session_id)

    source_hierarchy = payload.get("source_hierarchy")
    if isinstance(source_hierarchy, dict):
        for project in _payload_items(source_hierarchy.get("projects")):
            if not _project_marker_matches(
                project, root_path=root_path, project_key=project_key
            ):
                continue
            task_lists = project.get("task_lists")
            for task_list in _payload_items(task_lists):
                session_id = _payload_text(task_list.get("session_id"))
                if session_id:
                    sessions.add(session_id)
    return tuple(sorted(sessions))


def _project_marker_matches(
    payload: dict[str, Any],
    *,
    root_path: str,
    project_key: str,
) -> bool:
    project_path = _optional_payload_text(payload.get("project_path"))
    if project_path and _path_matches_project(project_path, root_path):
        return True
    return project_key in {
        _payload_text(payload.get("project_key")),
        _payload_text(payload.get("label")),
    }


def _path_matches_project(candidate: str, root_path: str) -> bool:
    try:
        return _normalized_project_path(candidate) == root_path
    except OSError:
        return str(Path(candidate).expanduser()) == root_path


def _task_payload_uid(payload: dict[str, Any]) -> str:
    uid = _payload_text(payload.get("uid"))
    if uid:
        return uid
    session_id = _payload_text(payload.get("session_id"))
    task_id = _payload_text(payload.get("task_id"))
    return f"{session_id}:{task_id}" if session_id and task_id else ""


def _edge_payload_uids(payload: dict[str, Any]) -> set[str]:
    blocker_uid = _edge_ref_uid(payload.get("blocker"))
    blocked_uid = _edge_ref_uid(payload.get("blocked"))
    return {uid for uid in (blocker_uid, blocked_uid) if uid}


def _edge_ref_uid(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    uid = _payload_text(payload.get("uid"))
    if uid:
        return uid
    session_id = _payload_text(payload.get("session_id"))
    task_id = _payload_text(payload.get("task_id"))
    return f"{session_id}:{task_id}" if session_id and task_id else ""


def _diagnostic_matches_project(
    diagnostic: dict[str, Any],
    session_ids: set[str],
    task_uids: set[str],
) -> bool:
    session_id = _payload_text(diagnostic.get("session_id"))
    if session_id in session_ids:
        return True
    task_uid = _payload_text(diagnostic.get("task_uid") or diagnostic.get("uid"))
    if task_uid in task_uids or task_uid.split(":", 1)[0] in session_ids:
        return True
    haystack = " ".join(
        item
        for item in (
            _payload_text(diagnostic.get("path")),
            _payload_text(diagnostic.get("message")),
        )
        if item
    )
    return any(session_id in haystack for session_id in session_ids)


def _filter_source_hierarchy_for_sessions(
    source_hierarchy: Any,
    session_ids: set[str],
    task_uids: set[str],
    edges: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
) -> dict[str, Any]:
    if not isinstance(source_hierarchy, dict):
        return {}
    task_uids_by_session: dict[str, set[str]] = defaultdict(set)
    status_by_uid: dict[str, str] = {}
    for task in tasks:
        uid = _task_payload_uid(task)
        session_id = _payload_text(task.get("session_id"))
        if uid and session_id:
            task_uids_by_session[session_id].add(uid)
            status_by_uid[uid] = _payload_text(task.get("status"), default="unknown")

    edge_pairs = _edge_pairs(edges)
    projects = []
    for project in _payload_items(source_hierarchy.get("projects")):
        filtered_task_lists = []
        for task_list in _payload_items(project.get("task_lists")):
            session_id = _payload_text(task_list.get("session_id"))
            if session_id not in session_ids:
                continue
            session_task_uids = task_uids_by_session.get(session_id, set())
            filtered_task_list = dict(task_list)
            filtered_task_list["task_count"] = len(session_task_uids)
            filtered_task_list["dependency_groups"] = _filter_dependency_groups(
                task_list.get("dependency_groups"),
                session_task_uids,
                edge_pairs,
                status_by_uid,
            )
            filtered_task_lists.append(filtered_task_list)
        if not filtered_task_lists:
            continue
        filtered_project = dict(project)
        filtered_project["task_lists"] = filtered_task_lists
        filtered_project["task_count"] = sum(
            int(task_list.get("task_count") or 0) for task_list in filtered_task_lists
        )
        projects.append(filtered_project)

    filtered = dict(source_hierarchy)
    filtered["projects"] = projects
    return filtered


def _filter_dependency_groups(
    groups: Any,
    task_uids: set[str],
    edge_pairs: list[tuple[str, str]],
    status_by_uid: dict[str, str],
) -> list[dict[str, Any]]:
    payloads = []
    for group in _payload_items(groups):
        group_uids = set(_payload_text_tuple(group.get("task_uids")))
        if not group_uids:
            for layer in _payload_items(group.get("layers")):
                group_uids.update(_payload_text_tuple(layer.get("tasks")))
        group_uids &= task_uids
        if not group_uids:
            continue

        outgoing = {
            blocker
            for blocker, blocked in edge_pairs
            if blocker in group_uids and blocked in group_uids
        }
        incoming = {
            blocked
            for blocker, blocked in edge_pairs
            if blocker in group_uids and blocked in group_uids
        }
        roots = set(_payload_text_tuple(group.get("root_uids"))) & group_uids
        leaves = set(_payload_text_tuple(group.get("leaf_uids"))) & group_uids
        if not roots:
            roots = group_uids - incoming
        if not leaves:
            leaves = group_uids - outgoing

        filtered_group = dict(group)
        filtered_group["task_uids"] = sorted(group_uids)
        filtered_group["task_count"] = len(group_uids)
        filtered_group["edge_count"] = sum(
            1
            for blocker, blocked in edge_pairs
            if blocker in group_uids and blocked in group_uids
        )
        filtered_group["root_uids"] = sorted(roots)
        filtered_group["leaf_uids"] = sorted(leaves)
        filtered_group["status_counts"] = dict(
            Counter(status_by_uid.get(uid, "unknown") for uid in group_uids)
        )
        filtered_group["layers"] = _filter_layers(group.get("layers"), group_uids)
        payloads.append(filtered_group)
    return payloads


def _filter_layers(layers: Any, task_uids: set[str]) -> list[dict[str, Any]]:
    filtered_layers = []
    for layer in _payload_items(layers):
        layer_tasks = sorted(set(_payload_text_tuple(layer.get("tasks"))) & task_uids)
        if not layer_tasks:
            continue
        filtered_layer = dict(layer)
        filtered_layer["tasks"] = layer_tasks
        filtered_layer["task_count"] = len(layer_tasks)
        filtered_layers.append(filtered_layer)
    if filtered_layers:
        return filtered_layers
    return [{"depth": 0, "task_count": len(task_uids), "tasks": sorted(task_uids)}]


def _build_filtered_summary(
    tasks: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    diagnostics: list[dict[str, Any]],
    metadata: list[dict[str, Any]],
    session_ids: tuple[str, ...],
) -> dict[str, Any]:
    status_counts = Counter(
        _payload_text(task.get("status"), default="unknown") for task in tasks
    )
    task_uids_by_session: dict[str, set[str]] = defaultdict(set)
    tasks_by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for task in tasks:
        session_id = _payload_text(task.get("session_id"))
        uid = _task_payload_uid(task)
        if session_id and uid:
            task_uids_by_session[session_id].add(uid)
            tasks_by_session[session_id].append(task)

    edge_pairs = _edge_pairs(edges)
    ready_count, blocked_open_count = _raw_readiness_counts(tasks, edge_pairs)
    metadata_by_session = {
        _payload_text(item.get("session_id")): item for item in metadata
    }
    return {
        "task_count": len(tasks),
        "edge_count": len(edges),
        "session_count": len(session_ids),
        "status_counts": dict(status_counts),
        "missing_reference_count": len(diagnostics),
        "cycle_count": 0,
        "ready_count": ready_count,
        "blocked_open_count": blocked_open_count,
        "sessions": [
            {
                "session_id": session_id,
                "task_count": len(tasks_by_session.get(session_id, [])),
                "edge_count": sum(
                    1
                    for blocker, blocked in edge_pairs
                    if blocker in task_uids_by_session[session_id]
                    or blocked in task_uids_by_session[session_id]
                ),
                "status_counts": dict(
                    Counter(
                        _payload_text(task.get("status"), default="unknown")
                        for task in tasks_by_session.get(session_id, [])
                    )
                ),
                "metadata": metadata_by_session.get(session_id),
            }
            for session_id in session_ids
        ],
    }


def _edge_pairs(edges: list[dict[str, Any]]) -> list[tuple[str, str]]:
    pairs = []
    for edge in edges:
        blocker = _edge_ref_uid(edge.get("blocker"))
        blocked = _edge_ref_uid(edge.get("blocked"))
        if blocker and blocked:
            pairs.append((blocker, blocked))
    return pairs


def _raw_readiness_counts(
    tasks: list[dict[str, Any]],
    edge_pairs: list[tuple[str, str]],
) -> tuple[int, int]:
    task_by_uid = {uid: task for task in tasks if (uid := _task_payload_uid(task))}
    blockers_by_uid: dict[str, list[str]] = defaultdict(list)
    for blocker, blocked in edge_pairs:
        blockers_by_uid[blocked].append(blocker)
    ready_count = 0
    blocked_open_count = 0
    open_statuses = {"pending", "in_progress", "todo", "open", "blocked", "unknown"}
    for uid, task in task_by_uid.items():
        if _payload_text(task.get("status"), default="unknown") not in open_statuses:
            continue
        blockers = blockers_by_uid.get(uid, [])
        if not blockers:
            ready_count += 1
            continue
        if any(
            _payload_text(
                task_by_uid.get(blocker, {}).get("status"),
                default="unknown",
            )
            != "completed"
            for blocker in blockers
        ):
            blocked_open_count += 1
        else:
            ready_count += 1
    return ready_count, blocked_open_count


def _task_title(task: ClaudoTaskRecord) -> str:
    return task.subject or task.active_form or task.description or task.task_id


def _task_description(task: ClaudoTaskRecord) -> str | None:
    parts = []
    if task.description:
        parts.append(task.description)
    if task.active_form and task.active_form not in {task.subject, task.description}:
        parts.append(f"Active form: {task.active_form}")
    return "\n\n".join(parts) if parts else None


def _task_needs_update(
    task: Task,
    title: str,
    description: str | None,
    owner: str | None,
) -> bool:
    return (
        task.title != title
        or task.description != description
        or (owner is not None and task.assignee != owner)
        or (owner is None and task.assignee is not None)
    )


def _task_import_metadata(
    task: ClaudoTaskRecord,
    hierarchy: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "uid": task.uid,
        "source": task.source,
        "session_id": task.session_id,
        "task_id": task.task_id,
        "status": task.status,
        "path": task.path,
        "source_created_at": task.source_created_at,
        "source_modified_at": task.source_modified_at,
        "blocks": list(task.blocks),
        "blocked_by": list(task.blocked_by),
        "metadata": task.metadata,
        "hierarchy": hierarchy or {},
    }


def _source_hierarchy_task_index(
    source_hierarchy: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    projects = source_hierarchy.get("projects")
    if not isinstance(projects, list):
        return index
    for project in projects:
        if not isinstance(project, dict):
            continue
        task_lists = project.get("task_lists")
        if not isinstance(task_lists, list):
            continue
        for task_list in task_lists:
            if not isinstance(task_list, dict):
                continue
            groups = task_list.get("dependency_groups")
            if not isinstance(groups, list):
                continue
            for group in groups:
                if not isinstance(group, dict):
                    continue
                component_id = group.get("component_id")
                root_uids = set(_payload_text_tuple(group.get("root_uids")))
                leaf_uids = set(_payload_text_tuple(group.get("leaf_uids")))
                layers = group.get("layers")
                if not isinstance(layers, list):
                    continue
                for layer in layers:
                    if not isinstance(layer, dict):
                        continue
                    depth = layer.get("depth")
                    for uid in _payload_text_tuple(layer.get("tasks")):
                        index.setdefault(
                            uid,
                            {
                                "project_label": project.get("label"),
                                "project_path": project.get("project_path"),
                                "session_id": task_list.get("session_id"),
                                "component_id": component_id,
                                "depth": depth,
                                "is_root": uid in root_uids,
                                "is_leaf": uid in leaf_uids,
                            },
                        )
    return index


def _claudo_status_to_pms(raw_status: str) -> TaskStatus:
    status = raw_status.strip().lower().replace("-", "_")
    if status in {"completed", "complete", "done"}:
        return TaskStatus.DONE
    if status in {"in_progress", "active", "running"}:
        return TaskStatus.IN_PROGRESS
    if status in {"review", "in_review"}:
        return TaskStatus.IN_REVIEW
    if status == "blocked":
        return TaskStatus.BLOCKED
    if status in {"cancelled", "canceled"}:
        return TaskStatus.CANCELLED
    return TaskStatus.TODO


def _pms_status_to_claudo(status: TaskStatus) -> str:
    if status == TaskStatus.DONE:
        return "completed"
    if status == TaskStatus.IN_PROGRESS:
        return "in_progress"
    return "pending"


def _tasks_by_session(
    tasks: list[ClaudoTaskRecord],
) -> dict[str, list[ClaudoTaskRecord]]:
    grouped: dict[str, list[ClaudoTaskRecord]] = defaultdict(list)
    for task in tasks:
        grouped[task.session_id].append(task)
    return grouped


def _completion_percent(tasks: list[ClaudoTaskRecord]) -> int:
    if not tasks:
        return 0
    completed = sum(
        1 for task in tasks if _claudo_status_to_pms(task.status) == TaskStatus.DONE
    )
    return round((completed / len(tasks)) * 100)


def _export_task_metadata(task: Task, project: Project) -> dict[str, Any]:
    return {
        "pms_task_id": task.id,
        "pms_project_id": project.id,
        "pms_project_name": project.name,
        "pms_status": task.status.value,
        "pms_priority": task.priority.value,
        "pms_parent_id": task.parent_id,
        "pms_milestone_id": task.milestone_id,
        "pms_tags": list(task.tags),
        "pms_progress_percent": task.current_progress_percent,
        "pms_completed_at": task.completed_at.isoformat()
        if task.completed_at
        else None,
        "pms_due_date": task.due_date.isoformat() if task.due_date else None,
    }


def _build_export_summary(
    task_payloads: list[dict[str, Any]],
    edges: list[ClaudoEdgeRecord],
    diagnostics: list[dict[str, Any]],
    session_id: str,
) -> dict[str, Any]:
    status_counts = Counter(str(task["status"]) for task in task_payloads)
    ready_count, blocked_open_count = _export_readiness_counts(task_payloads, edges)
    return {
        "task_count": len(task_payloads),
        "edge_count": len(edges),
        "session_count": 1,
        "status_counts": dict(status_counts),
        "missing_reference_count": len(diagnostics),
        "cycle_count": 0,
        "ready_count": ready_count,
        "blocked_open_count": blocked_open_count,
        "sessions": [
            {
                "session_id": session_id,
                "task_count": len(task_payloads),
                "edge_count": len(edges),
                "status_counts": dict(status_counts),
                "metadata": None,
            }
        ],
    }


def _export_readiness_counts(
    task_payloads: list[dict[str, Any]],
    edges: list[ClaudoEdgeRecord],
) -> tuple[int, int]:
    task_by_uid = {str(task["uid"]): task for task in task_payloads}
    blockers_by_uid: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        blockers_by_uid[edge.blocked.uid].append(edge.blocker.uid)
    ready_count = 0
    blocked_open_count = 0
    for uid, task in task_by_uid.items():
        if task.get("status") not in {"pending", "in_progress", "todo", "open"}:
            continue
        blockers = blockers_by_uid.get(uid, [])
        if not blockers:
            ready_count += 1
            continue
        if any(
            task_by_uid[blocker].get("status") != "completed" for blocker in blockers
        ):
            blocked_open_count += 1
        else:
            ready_count += 1
    return ready_count, blocked_open_count


def _build_export_hierarchy(
    project: Project,
    session_id: str,
    task_payloads: list[dict[str, Any]],
    edges: list[ClaudoEdgeRecord],
) -> dict[str, Any]:
    components = _export_components(task_payloads, edges)
    return {
        "projects": [
            {
                "label": project.name,
                "project_path": None,
                "project_key": project.id,
                "task_lists": [
                    {
                        "session_id": session_id,
                        "task_count": len(task_payloads),
                        "dependency_groups": components,
                    }
                ],
            }
        ]
    }


def _export_components(
    task_payloads: list[dict[str, Any]],
    edges: list[ClaudoEdgeRecord],
) -> list[dict[str, Any]]:
    uids = [str(task["uid"]) for task in task_payloads]
    if not uids:
        return []
    undirected: dict[str, set[str]] = {uid: set() for uid in uids}
    incoming: dict[str, set[str]] = {uid: set() for uid in uids}
    outgoing: dict[str, set[str]] = {uid: set() for uid in uids}
    for edge in edges:
        if edge.blocker.uid not in undirected or edge.blocked.uid not in undirected:
            continue
        undirected[edge.blocker.uid].add(edge.blocked.uid)
        undirected[edge.blocked.uid].add(edge.blocker.uid)
        outgoing[edge.blocker.uid].add(edge.blocked.uid)
        incoming[edge.blocked.uid].add(edge.blocker.uid)

    components: list[list[str]] = []
    seen: set[str] = set()
    for uid in uids:
        if uid in seen:
            continue
        queue = deque([uid])
        seen.add(uid)
        component: list[str] = []
        while queue:
            current = queue.popleft()
            component.append(current)
            for neighbor in sorted(undirected[current]):
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append(neighbor)
        components.append(sorted(component))

    depths = _export_depths(uids, outgoing, incoming)
    payloads = []
    for index, component in enumerate(components, start=1):
        component_set = set(component)
        component_edges = [
            edge
            for edge in edges
            if edge.blocker.uid in component_set and edge.blocked.uid in component_set
        ]
        roots = sorted(uid for uid in component if not incoming[uid] & component_set)
        leaves = sorted(uid for uid in component if not outgoing[uid] & component_set)
        layer_map: dict[int, list[str]] = defaultdict(list)
        for uid in component:
            layer_map[depths.get(uid, 0)].append(uid)
        payloads.append(
            {
                "component_id": f"component-{index:04d}",
                "edge_count": len(component_edges),
                "layers": [
                    {
                        "depth": depth,
                        "task_count": len(layer_tasks),
                        "tasks": sorted(layer_tasks),
                    }
                    for depth, layer_tasks in sorted(layer_map.items())
                ],
                "leaf_uids": leaves,
                "root_uids": roots,
                "status_counts": {},
                "task_count": len(component),
                "task_uids": component,
            }
        )
    return payloads


def _export_depths(
    uids: list[str],
    outgoing: dict[str, set[str]],
    incoming: dict[str, set[str]],
) -> dict[str, int]:
    incoming_work = {uid: set(incoming[uid]) for uid in uids}
    depths = {uid: 0 for uid in uids}
    queue = deque(uid for uid in uids if not incoming_work[uid])
    seen = set(queue)
    while queue:
        current = queue.popleft()
        for blocked_uid in sorted(outgoing[current]):
            depths[blocked_uid] = max(depths[blocked_uid], depths[current] + 1)
            incoming_work[blocked_uid].discard(current)
            if not incoming_work[blocked_uid] and blocked_uid not in seen:
                seen.add(blocked_uid)
                queue.append(blocked_uid)
    return depths
