"""Report generators for various formats."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pms.models.project import Project, ProjectStats
    from pms.models.task import Task
    from pms.services.project_service import ProjectService
    from pms.services.task_service import TaskService


class ReportFormat(StrEnum):
    """Supported report formats."""

    MARKDOWN = "markdown"
    HTML = "html"
    JSON = "json"
    CSV = "csv"
    TEXT = "text"


@dataclass
class ProjectReportData:
    """Data structure for project reports."""

    project: Project
    stats: ProjectStats | None
    health_score: float  # 0-100 scale for display
    tasks: list[Task]
    generated_at: datetime
    labels_by_task_id: dict[str, list[str]] = field(default_factory=dict)
    evidence_counts: dict[str, int] = field(default_factory=dict)


async def gather_project_data(
    project_id: str,
    project_service: ProjectService,
    task_service: TaskService,
) -> ProjectReportData:
    """Gather all data needed for a project report."""
    project = await project_service.get_project(project_id)
    if project is None:
        raise ValueError(f"Project not found: {project_id}")

    summary = await project_service.get_project_summary(project_id)
    tasks_result = await task_service.list_tasks(project_id=project_id)

    labels_by_task_id: dict[str, list[str]] = {}
    evidence_counts: dict[str, int] = {}
    task_ids = [task.id for task in tasks_result.items]
    if task_ids:
        from pms.repositories.label_assignment_repository import (
            LabelAssignmentRepository,
        )
        from pms.repositories.label_repository import LabelRepository
        from pms.repositories.task_evidence_repository import TaskEvidenceRepository

        assignment_repo = LabelAssignmentRepository(project_service.db)
        label_repo = LabelRepository(project_service.db)
        evidence_repo = TaskEvidenceRepository(project_service.db)

        assignments = await assignment_repo.list_for_entities("task", task_ids)
        label_ids = {assignment.label_id for assignment in assignments}
        label_names: dict[str, str] = {}
        for label_id in label_ids:
            label = await label_repo.get_by_id(label_id)
            if label:
                label_names[label_id] = label.name

        for assignment in assignments:
            name = label_names.get(assignment.label_id)
            if name:
                labels_by_task_id.setdefault(assignment.entity_id, []).append(name)

        for task_id, labels in labels_by_task_id.items():
            labels.sort()

        evidence_records = await evidence_repo.list_by_task_ids(task_ids)
        for record in evidence_records:
            evidence_counts[record.task_id] = evidence_counts.get(record.task_id, 0) + 1

    # Extract stats and health_score from summary
    stats = summary.stats if summary else None
    health_score = (summary.health_score * 100) if summary else 0.0

    return ProjectReportData(
        project=project,
        stats=stats,
        health_score=health_score,
        tasks=list(tasks_result.items),
        generated_at=datetime.now(),
        labels_by_task_id=labels_by_task_id,
        evidence_counts=evidence_counts,
    )


def _format_duration(hours: float | None) -> str:
    """Format hours as human-readable duration."""
    if hours is None or hours == 0:
        return "-"
    if hours < 1:
        return f"{int(hours * 60)}m"
    if hours == int(hours):
        return f"{int(hours)}h"
    return f"{hours:.1f}h"


def _format_complexity(points: int | None) -> str:
    """Format complexity points."""
    if points is None or points == 0:
        return "-"
    return f"{points} pts"


def _format_efficiency(score: float | None) -> str:
    """Format efficiency score (complexity per hour)."""
    if score is None or score == 0:
        return "-"
    return f"{score:.1f} pts/hr"


def _status_emoji(status: str) -> str:
    """Get emoji for task status."""
    mapping = {
        "todo": "[ ]",
        "in_progress": "[~]",
        "blocked": "[!]",
        "in_review": "[?]",
        "done": "[x]",
        "cancelled": "[-]",
    }
    return mapping.get(status, "[ ]")


def _priority_indicator(priority: str) -> str:
    """Get indicator for priority."""
    mapping = {
        "critical": "!!!",
        "high": "!!",
        "medium": "!",
        "low": "",
    }
    return mapping.get(priority, "")


def generate_project_markdown(data: ProjectReportData) -> str:
    """Generate markdown project report."""
    from pms.models.workflow_state import get_workflow_by_id

    lines = [
        f"# Project Report: {data.project.name}",
        "",
        f"*Generated: {data.generated_at.strftime('%Y-%m-%d %H:%M')}*",
        "",
        "---",
        "",
        "## Overview",
        "",
        f"- **Status:** {data.project.status.value}",
        f"- **Created:** {data.project.created_at.strftime('%Y-%m-%d')}",
        f"- **Last Updated:** {data.project.updated_at.strftime('%Y-%m-%d %H:%M')}",
    ]

    if data.project.description:
        lines.extend(["", f"**Description:** {data.project.description}"])

    if data.project.tags:
        lines.extend(["", f"**Tags:** {', '.join(data.project.tags)}"])

    # Summary stats
    if data.stats:
        s = data.stats
        lines.extend(
            [
                "",
                "## Summary",
                "",
                "| Metric | Value |",
                "|--------|-------|",
                f"| Health Score | {data.health_score:.0f}/100 |",
                f"| Completion | {s.completion_percent:.0f}% |",
                f"| Total Tasks | {s.total_tasks} |",
                f"| Completed | {s.completed_tasks} |",
                f"| In Progress | {s.in_progress_tasks} |",
                f"| Blocked | {s.blocked_tasks} |",
                f"| Overdue | {s.overdue_tasks} |",
                f"| Total Complexity | {s.total_complexity_points} |",
                f"| Avg Complexity | {s.avg_complexity_per_task:.1f} |",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "## Summary",
                "",
                f"| Health Score | {data.health_score:.0f}/100 |",
                "| No task statistics available |",
            ]
        )

    # Task list
    if data.tasks:
        warnings: list[str] = []
        for task in data.tasks:
            if not task.workflow_id or not task.current_state:
                continue
            workflow = get_workflow_by_id(task.workflow_id)
            if workflow is None:
                continue
            workflow_terminal = task.current_state in workflow.terminal_states
            status_terminal = task.status.is_terminal
            if workflow_terminal and not status_terminal:
                warnings.append(
                    f"{task.title}: workflow is terminal ({task.current_state}) "
                    f"but status is {task.status.value}"
                )
            if status_terminal and not workflow_terminal:
                warnings.append(
                    f"{task.title}: status is terminal ({task.status.value}) "
                    f"but workflow is {task.current_state}"
                )

        if warnings:
            lines.extend(["", "## Warnings", ""])
            for warning in warnings:
                lines.append(f"- {warning}")

        lines.extend(
            [
                "",
                "## Tasks",
                "",
                "| Status | Priority | Title | Workflow | Labels | Evidence | Complexity | Progress |",
                "|--------|----------|-------|----------|--------|----------|------------|----------|",
            ]
        )

        # Sort by priority then status
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        status_order = {
            "in_progress": 0,
            "blocked": 1,
            "todo": 2,
            "in_review": 3,
            "done": 4,
            "cancelled": 5,
        }

        sorted_tasks = sorted(
            data.tasks,
            key=lambda t: (
                status_order.get(t.status.value, 9),
                priority_order.get(t.priority.value, 9),
            ),
        )

        for task in sorted_tasks:
            pri = _priority_indicator(task.priority.value)
            complexity = _format_complexity(task.complexity_points)
            progress = f"{task.current_progress_percent}%"
            workflow_state = task.current_state or "-"
            labels = ", ".join(data.labels_by_task_id.get(task.id, [])) or "-"
            evidence_count = str(data.evidence_counts.get(task.id, 0))

            lines.append(
                f"| {_status_emoji(task.status.value)} | {pri} {task.priority.value} | "
                f"{task.title} | {workflow_state} | {labels} | {evidence_count} | "
                f"{complexity} | {progress} |"
            )

    # Blocked tasks detail
    blocked = [t for t in data.tasks if t.status.value == "blocked"]
    if blocked:
        lines.extend(["", "## Blocked Tasks", ""])
        for task in blocked:
            lines.append(f"- **{task.title}**")
            if task.description:
                lines.append(f"  - Reason: {task.description}")

    lines.extend(["", "---", f"*Report ID: {data.project.id}*"])

    return "\n".join(lines)


def generate_project_html(data: ProjectReportData) -> str:
    """Generate HTML project report."""
    from pms.models.workflow_state import get_workflow_by_id

    s = data.stats

    # Get stats values safely
    completed = s.completed_tasks if s else 0
    total = s.total_tasks if s else 0
    blocked = s.blocked_tasks if s else 0
    total_complexity = s.total_complexity_points if s else 0
    total_duration = s.total_duration_hours if s else 0
    avg_efficiency = s.avg_efficiency_score if s else 0
    completion = s.completion_percent if s else 0

    health_class = (
        "health-good"
        if data.health_score >= 70
        else "health-warning"
        if data.health_score >= 40
        else "health-bad"
    )

    warnings: list[str] = []
    for task in data.tasks:
        if not task.workflow_id or not task.current_state:
            continue
        workflow = get_workflow_by_id(task.workflow_id)
        if workflow is None:
            continue
        workflow_terminal = task.current_state in workflow.terminal_states
        status_terminal = task.status.is_terminal
        if workflow_terminal and not status_terminal:
            warnings.append(
                f"{task.title}: workflow is terminal ({task.current_state}) "
                f"but status is {task.status.value}"
            )
        if status_terminal and not workflow_terminal:
            warnings.append(
                f"{task.title}: status is terminal ({task.status.value}) "
                f"but workflow is {task.current_state}"
            )

    # Simple HTML template
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Project Report: {data.project.name}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               max-width: 900px; margin: 0 auto; padding: 20px; line-height: 1.6; }}
        h1 {{ color: #1a1a2e; border-bottom: 2px solid #4a4e69; padding-bottom: 10px; }}
        h2 {{ color: #4a4e69; margin-top: 30px; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
        th {{ background-color: #4a4e69; color: white; }}
        tr:nth-child(even) {{ background-color: #f9f9f9; }}
        .status-done {{ color: #28a745; }}
        .status-blocked {{ color: #dc3545; }}
        .status-in_progress {{ color: #ffc107; }}
        .priority-critical {{ font-weight: bold; color: #dc3545; }}
        .priority-high {{ font-weight: bold; color: #fd7e14; }}
        .health-good {{ color: #28a745; }}
        .health-warning {{ color: #ffc107; }}
        .health-bad {{ color: #dc3545; }}
        .meta {{ color: #6c757d; font-size: 0.9em; }}
        .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; }}
        .summary-card {{ background: #f8f9fa; padding: 15px; border-radius: 8px; text-align: center; }}
        .summary-value {{ font-size: 2em; font-weight: bold; color: #4a4e69; }}
        .summary-label {{ color: #6c757d; font-size: 0.9em; }}
    </style>
</head>
<body>
    <h1>Project Report: {data.project.name}</h1>
    <p class="meta">Generated: {data.generated_at.strftime("%Y-%m-%d %H:%M")} | Status: {data.project.status.value}</p>

    {"<p>" + data.project.description + "</p>" if data.project.description else ""}

    <h2>Summary</h2>
    <div class="summary-grid">
        <div class="summary-card">
            <div class="summary-value {health_class}">{data.health_score:.0f}</div>
            <div class="summary-label">Health Score</div>
        </div>
        <div class="summary-card">
            <div class="summary-value">{completion:.0f}%</div>
            <div class="summary-label">Complete</div>
        </div>
        <div class="summary-card">
            <div class="summary-value">{completed}/{total}</div>
            <div class="summary-label">Tasks Done</div>
        </div>
        <div class="summary-card">
            <div class="summary-value {"status-blocked" if blocked > 0 else ""}">{blocked}</div>
            <div class="summary-label">Blocked</div>
        </div>
        <div class="summary-card">
            <div class="summary-value">{total_complexity}</div>
            <div class="summary-label">Complexity</div>
        </div>
    </div>

    {"<h2>Warnings</h2><ul>" + "".join(f"<li>{w}</li>" for w in warnings) + "</ul>" if warnings else ""}

    <h2>Tasks</h2>
    <table>
        <thead>
            <tr>
                <th>Status</th>
                <th>Priority</th>
                <th>Title</th>
                <th>Workflow</th>
                <th>Labels</th>
                <th>Evidence</th>
                <th>Complexity</th>
                <th>Progress</th>
                <th>Actual</th>
            </tr>
        </thead>
        <tbody>
"""

    # Sort tasks
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    status_order = {
        "in_progress": 0,
        "blocked": 1,
        "todo": 2,
        "in_review": 3,
        "done": 4,
        "cancelled": 5,
    }
    sorted_tasks = sorted(
        data.tasks,
        key=lambda t: (
            status_order.get(t.status.value, 9),
            priority_order.get(t.priority.value, 9),
        ),
    )

    for task in sorted_tasks:
        status_class = f"status-{task.status.value}"
        priority_class = f"priority-{task.priority.value}"
        workflow_state = task.current_state or "-"
        labels = ", ".join(data.labels_by_task_id.get(task.id, [])) or "-"
        evidence_count = data.evidence_counts.get(task.id, 0)
        progress = f"{task.current_progress_percent}%"
        html += f"""            <tr>
                <td class="{status_class}">{task.status.value}</td>
                <td class="{priority_class}">{task.priority.value}</td>
                <td>{task.title}</td>
                <td>{workflow_state}</td>
                <td>{labels}</td>
                <td>{evidence_count}</td>
                <td>{task.complexity_points or ""}</td>
                <td>{progress}</td>
                <td>{_format_duration(task.actual_hours)}</td>
            </tr>
"""

    html += f"""        </tbody>
    </table>

    <hr>
    <p class="meta">Report ID: {data.project.id}</p>
</body>
</html>"""

    return html


def generate_project_json(data: ProjectReportData) -> str:
    """Generate JSON project report."""
    from pms.models.workflow_state import get_workflow_by_id

    s = data.stats
    warnings: list[str] = []
    workflow_terminal_by_task: dict[str, bool] = {}
    status_terminal_by_task: dict[str, bool] = {}
    mismatch_by_task: dict[str, bool] = {}

    for task in data.tasks:
        status_terminal = task.status.is_terminal
        status_terminal_by_task[task.id] = status_terminal
        workflow_terminal = False
        if task.workflow_id and task.current_state:
            workflow = get_workflow_by_id(task.workflow_id)
            if workflow:
                workflow_terminal = task.current_state in workflow.terminal_states
        workflow_terminal_by_task[task.id] = workflow_terminal
        mismatch = workflow_terminal != status_terminal
        mismatch_by_task[task.id] = mismatch
        if mismatch and task.current_state:
            if workflow_terminal and not status_terminal:
                warnings.append(
                    f"{task.title}: workflow is terminal ({task.current_state}) "
                    f"but status is {task.status.value}"
                )
            if status_terminal and not workflow_terminal:
                warnings.append(
                    f"{task.title}: status is terminal ({task.status.value}) "
                    f"but workflow is {task.current_state}"
                )

    report: dict[str, Any] = {
        "generated_at": data.generated_at.isoformat(),
        "project": {
            "id": data.project.id,
            "name": data.project.name,
            "description": data.project.description,
            "status": data.project.status.value,
            "tags": list(data.project.tags) if data.project.tags else [],
            "created_at": data.project.created_at.isoformat(),
            "updated_at": data.project.updated_at.isoformat(),
        },
        "summary": {
            "health_score": data.health_score,
            "completion_percent": s.completion_percent if s else 0,
            "total_tasks": s.total_tasks if s else 0,
            "completed_tasks": s.completed_tasks if s else 0,
            "in_progress_tasks": s.in_progress_tasks if s else 0,
            "blocked_tasks": s.blocked_tasks if s else 0,
            "overdue_tasks": s.overdue_tasks if s else 0,
            "total_complexity_points": s.total_complexity_points if s else 0,
            "avg_complexity_per_task": s.avg_complexity_per_task if s else 0,
        },
        "warnings": warnings,
        "tasks": [
            {
                "id": t.id,
                "title": t.title,
                "description": t.description,
                "status": t.status.value,
                "priority": t.priority.value,
                "workflow_state": t.current_state,
                "workflow_terminal": workflow_terminal_by_task.get(t.id, False),
                "status_terminal": status_terminal_by_task.get(t.id, False),
                "workflow_status_mismatch": mismatch_by_task.get(t.id, False),
                "labels": data.labels_by_task_id.get(t.id, []),
                "evidence_count": data.evidence_counts.get(t.id, 0),
                "actual_hours": t.actual_hours,
                "complexity_points": t.complexity_points,
                "progress_percent": t.current_progress_percent,
                "created_at": t.created_at.isoformat(),
                "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            }
            for t in data.tasks
        ],
    }
    return json.dumps(report, indent=2)


def generate_project_csv(data: ProjectReportData) -> str:
    """Generate CSV of project tasks."""
    from pms.models.workflow_state import get_workflow_by_id

    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow(
        [
            "Task ID",
            "Title",
            "Status",
            "Priority",
            "Workflow State",
            "Labels",
            "Evidence Count",
            "Workflow Terminal",
            "Status Terminal",
            "Workflow/Status Mismatch",
            "Complexity Points",
            "Progress",
            "Actual Hours",
            "Created At",
            "Completed At",
            "Description",
        ]
    )

    # Tasks
    for task in data.tasks:
        workflow_terminal = ""
        status_terminal = str(task.status.is_terminal).lower()
        mismatch = ""
        if task.workflow_id and task.current_state:
            workflow = get_workflow_by_id(task.workflow_id)
            if workflow:
                workflow_terminal = str(
                    task.current_state in workflow.terminal_states
                ).lower()
                mismatch = str(
                    (task.current_state in workflow.terminal_states)
                    != task.status.is_terminal
                ).lower()
        writer.writerow(
            [
                task.id,
                task.title,
                task.status.value,
                task.priority.value,
                task.current_state or "",
                ", ".join(data.labels_by_task_id.get(task.id, [])),
                str(data.evidence_counts.get(task.id, 0)),
                workflow_terminal,
                status_terminal,
                mismatch,
                task.complexity_points or "",
                f"{task.current_progress_percent}%",
                task.actual_hours or "",
                task.created_at.isoformat(),
                task.completed_at.isoformat() if task.completed_at else "",
                task.description or "",
            ]
        )

    return output.getvalue()


def generate_project_text(data: ProjectReportData) -> str:
    """Generate plain text project report."""
    from pms.models.workflow_state import get_workflow_by_id

    s = data.stats
    lines = [
        "=" * 60,
        f"PROJECT REPORT: {data.project.name.upper()}",
        "=" * 60,
        "",
        f"Generated: {data.generated_at.strftime('%Y-%m-%d %H:%M')}",
        f"Status: {data.project.status.value}",
        "",
    ]

    if data.project.description:
        lines.extend([data.project.description, ""])

    lines.extend(
        [
            "-" * 40,
            "SUMMARY",
            "-" * 40,
            f"Health Score:     {data.health_score:.0f}/100",
        ]
    )

    if s:
        lines.extend(
            [
                f"Completion:       {s.completion_percent:.0f}%",
                f"Total Tasks:      {s.total_tasks}",
                f"Completed:        {s.completed_tasks}",
                f"In Progress:      {s.in_progress_tasks}",
                f"Blocked:          {s.blocked_tasks}",
                f"Total Complexity: {s.total_complexity_points}",
                f"Avg Complexity:   {s.avg_complexity_per_task:.1f}",
            ]
        )

    warnings: list[str] = []
    for task in data.tasks:
        if not task.workflow_id or not task.current_state:
            continue
        workflow = get_workflow_by_id(task.workflow_id)
        if workflow is None:
            continue
        workflow_terminal = task.current_state in workflow.terminal_states
        status_terminal = task.status.is_terminal
        if workflow_terminal and not status_terminal:
            warnings.append(
                f"{task.title}: workflow is terminal ({task.current_state}) "
                f"but status is {task.status.value}"
            )
        if status_terminal and not workflow_terminal:
            warnings.append(
                f"{task.title}: status is terminal ({task.status.value}) "
                f"but workflow is {task.current_state}"
            )
    if warnings:
        lines.extend(
            [
                "",
                "-" * 40,
                "WARNINGS",
                "-" * 40,
            ]
        )
        lines.extend(f"- {warning}" for warning in warnings)

    lines.extend(
        [
            "",
            "-" * 40,
            "TASKS",
            "-" * 40,
        ]
    )

    for task in data.tasks:
        status_mark = _status_emoji(task.status.value)
        workflow_state = task.current_state or "-"
        labels = ", ".join(data.labels_by_task_id.get(task.id, [])) or "-"
        evidence_count = data.evidence_counts.get(task.id, 0)
        lines.append(
            f"{status_mark} [{task.priority.value:8}] {task.title} "
            f"(workflow: {workflow_state}, labels: {labels}, evidence: {evidence_count})"
        )

    lines.extend(["", "=" * 60])

    return "\n".join(lines)


async def generate_project_report(
    project_id: str,
    project_service: ProjectService,
    task_service: TaskService,
    format: ReportFormat = ReportFormat.MARKDOWN,
) -> str:
    """Generate a project report in the specified format.

    Args:
        project_id: Project ID to report on
        project_service: Project service instance
        task_service: Task service instance
        format: Output format (markdown, html, json, csv, text)

    Returns:
        Report content as string
    """
    data = await gather_project_data(project_id, project_service, task_service)

    generators = {
        ReportFormat.MARKDOWN: generate_project_markdown,
        ReportFormat.HTML: generate_project_html,
        ReportFormat.JSON: generate_project_json,
        ReportFormat.CSV: generate_project_csv,
        ReportFormat.TEXT: generate_project_text,
    }

    generator = generators.get(format, generate_project_markdown)
    return generator(data)


async def generate_history_report(
    project_service: ProjectService,
    task_service: TaskService,
    days: int = 30,
    format: ReportFormat = ReportFormat.MARKDOWN,
) -> str:
    """Generate a historical report of all activity.

    Args:
        project_service: Project service instance
        task_service: Task service instance
        days: Number of days to look back
        format: Output format

    Returns:
        Report content as string
    """
    # Get all projects
    projects_result = await project_service.list_projects()
    projects = list(projects_result.items)

    # Gather data for each project
    all_data: list[ProjectReportData] = []
    for project in projects:
        try:
            data = await gather_project_data(project.id, project_service, task_service)
            all_data.append(data)
        except Exception:
            continue

    match format:
        case ReportFormat.JSON:
            return _generate_history_json(all_data, days)
        case ReportFormat.CSV:
            return _generate_history_csv(all_data)
        case _:
            return _generate_history_markdown(all_data, days)


def _generate_history_markdown(data: list[ProjectReportData], days: int) -> str:
    """Generate markdown history report."""
    lines = [
        f"# Activity Report - Last {days} Days",
        "",
        f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        "",
        "---",
        "",
        "## Summary",
        "",
    ]

    total_tasks = sum((d.stats.total_tasks if d.stats else 0) for d in data)
    completed_tasks = sum((d.stats.completed_tasks if d.stats else 0) for d in data)
    blocked_tasks = sum((d.stats.blocked_tasks if d.stats else 0) for d in data)
    total_hours = sum(
        (d.stats.total_duration_hours or 0) if d.stats else 0 for d in data
    )

    lines.extend(
        [
            f"- **Active Projects:** {len(data)}",
            f"- **Total Tasks:** {total_tasks}",
            f"- **Completed Tasks:** {completed_tasks}",
            f"- **Blocked Tasks:** {blocked_tasks}",
            f"- **Total Duration:** {_format_duration(total_hours)}",
            "",
            "## Projects",
            "",
        ]
    )

    # Sort by health score
    for report_data in sorted(data, key=lambda d: d.health_score, reverse=True):
        health = report_data.health_score
        health_indicator = "good" if health >= 70 else "warn" if health >= 40 else "bad"
        s = report_data.stats
        completed = s.completed_tasks if s else 0
        total = s.total_tasks if s else 0
        blocked = s.blocked_tasks if s else 0
        completion = s.completion_percent if s else 0
        lines.extend(
            [
                f"### {report_data.project.name}",
                "",
                f"- Health: {health:.0f}/100 ({health_indicator})",
                f"- Progress: {completion:.0f}% ({completed}/{total})",
                f"- Blocked: {blocked}",
                "",
            ]
        )

    return "\n".join(lines)


def _generate_history_json(data: list[ProjectReportData], days: int) -> str:
    """Generate JSON history report."""
    report: dict[str, Any] = {
        "generated_at": datetime.now().isoformat(),
        "period_days": days,
        "summary": {
            "active_projects": len(data),
            "total_tasks": sum((d.stats.total_tasks if d.stats else 0) for d in data),
            "completed_tasks": sum(
                (d.stats.completed_tasks if d.stats else 0) for d in data
            ),
            "blocked_tasks": sum(
                (d.stats.blocked_tasks if d.stats else 0) for d in data
            ),
            "total_duration_hours": sum(
                (d.stats.total_duration_hours or 0) if d.stats else 0 for d in data
            ),
        },
        "projects": [
            {
                "id": d.project.id,
                "name": d.project.name,
                "status": d.project.status.value,
                "health_score": d.health_score,
                "completion_percent": d.stats.completion_percent if d.stats else 0,
                "task_count": d.stats.total_tasks if d.stats else 0,
                "completed_count": d.stats.completed_tasks if d.stats else 0,
                "blocked_count": d.stats.blocked_tasks if d.stats else 0,
            }
            for d in data
        ],
    }
    return json.dumps(report, indent=2)


def _generate_history_csv(data: list[ProjectReportData]) -> str:
    """Generate CSV history report."""
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(
        [
            "Project ID",
            "Project Name",
            "Status",
            "Health Score",
            "Completion %",
            "Total Tasks",
            "Completed",
            "In Progress",
            "Blocked",
            "Total Complexity",
            "Avg Complexity",
        ]
    )

    for d in data:
        s = d.stats
        writer.writerow(
            [
                d.project.id,
                d.project.name,
                d.project.status.value,
                f"{d.health_score:.0f}",
                f"{s.completion_percent:.1f}" if s else "0",
                s.total_tasks if s else 0,
                s.completed_tasks if s else 0,
                s.in_progress_tasks if s else 0,
                s.blocked_tasks if s else 0,
                s.total_complexity_points if s else 0,
                f"{s.avg_complexity_per_task:.1f}" if s else "0",
            ]
        )

    return output.getvalue()


async def generate_metrics_report(
    project_service: ProjectService,
    task_service: TaskService,
    project_id: str | None = None,
    format: ReportFormat = ReportFormat.CSV,
) -> str:
    """Generate metrics report for analysis.

    Args:
        project_service: Project service instance
        task_service: Task service instance
        project_id: Optional specific project (None for all)
        format: Output format (CSV recommended for metrics)

    Returns:
        Report content as string
    """
    if project_id:
        project = await project_service.get_project(project_id)
        if project is None:
            raise ValueError(f"Project not found: {project_id}")
        projects = [project]
    else:
        result = await project_service.list_projects()
        projects = list(result.items)

    metrics: list[dict[str, Any]] = []

    for project in projects:
        summary = await project_service.get_project_summary(project.id)
        stats = summary.stats if summary else None

        metrics.append(
            {
                "project_id": project.id,
                "project_name": project.name,
                "status": project.status.value,
                "created_at": project.created_at.isoformat(),
                "updated_at": project.updated_at.isoformat(),
                "health_score": (summary.health_score * 100) if summary else 0,
                "completion_percent": stats.completion_percent if stats else 0,
                "total_tasks": stats.total_tasks if stats else 0,
                "completed_tasks": stats.completed_tasks if stats else 0,
                "in_progress_tasks": stats.in_progress_tasks if stats else 0,
                "blocked_tasks": stats.blocked_tasks if stats else 0,
                "overdue_tasks": stats.overdue_tasks if stats else 0,
                "total_complexity_points": stats.total_complexity_points
                if stats
                else 0,
                "avg_complexity_per_task": stats.avg_complexity_per_task
                if stats
                else 0,
                "avg_efficiency_score": stats.avg_efficiency_score if stats else 0,
            }
        )

    match format:
        case ReportFormat.JSON:
            return json.dumps(
                {"generated_at": datetime.now().isoformat(), "metrics": metrics},
                indent=2,
            )
        case ReportFormat.MARKDOWN:
            return _generate_metrics_markdown(metrics)
        case _:
            return _generate_metrics_csv(metrics)


def _generate_metrics_csv(metrics: list[dict[str, Any]]) -> str:
    """Generate CSV metrics report."""
    if not metrics:
        return ""

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(metrics[0].keys()))
    writer.writeheader()
    writer.writerows(metrics)
    return output.getvalue()


def _generate_metrics_markdown(metrics: list[dict[str, Any]]) -> str:
    """Generate markdown metrics report."""
    lines = [
        "# Metrics Report",
        "",
        f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        "",
        "| Project | Health | Complete | Tasks | Total Complexity | Avg Complexity | Efficiency |",
        "|---------|--------|----------|-------|------------------|----------------|------------|",
    ]

    for m in metrics:
        name = str(m["project_name"])[:20]
        lines.append(
            f"| {name} | {m['health_score']:.0f} | "
            f"{m['completion_percent']:.0f}% | {m['total_tasks']} | "
            f"{m['total_complexity_points']} | {m['avg_complexity_per_task']:.1f} | "
            f"{m['avg_efficiency_score']:.2f} |"
        )

    return "\n".join(lines)
