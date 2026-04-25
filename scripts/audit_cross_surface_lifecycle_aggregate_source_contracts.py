#!/usr/bin/env python3
"""Audit static cross-surface lifecycle aggregate source contracts."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from scripts.source_contract_audit_utils import (
    SourceBlockContract,
    audit_block_contracts,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class CrossSurfaceLifecycleAggregateSourceIssue:
    """One static cross-surface aggregate source contract failure."""

    file: str
    reason: str


CROSS_SURFACE_LIFECYCLE_AGGREGATE_SOURCE_CONTRACTS: dict[
    str, tuple[SourceBlockContract, ...]
] = {
    "pms/api/routes/goals.py": (
        SourceBlockContract(
            anchor="def _goal_summary_links(",
            block_kind="python_def",
            required=(
                '"self": f"/api/v1/goals/{goal_id}/summary",',
                '"goal": f"/api/v1/goals/{goal_id}",',
                '"objectives": f"/api/v1/goals/{goal_id}/objectives",',
                '"plans": f"/api/v1/plans?goal_id={goal_id}",',
                '"project": f"/api/v1/projects/{project_id}" if project_id else "",',
                '"tasks": f"/api/v1/tasks?project_id={project_id}" if project_id else "",',
                '"guide": "/api/v1/",',
            ),
        ),
        SourceBlockContract(
            anchor="def _goal_detail_links(",
            block_kind="python_def",
            required=(
                '"self": f"/api/v1/goals/{goal_id}",',
                '"summary": f"/api/v1/goals/{goal_id}/summary",',
                '"objectives": f"/api/v1/goals/{goal_id}/objectives",',
                '"plans": f"/api/v1/plans?goal_id={goal_id}",',
                '"project": f"/api/v1/projects/{project_id}" if project_id else "",',
                '"tasks": f"/api/v1/tasks?project_id={project_id}" if project_id else "",',
                '"guide": "/api/v1/",',
            ),
        ),
        SourceBlockContract(
            anchor="async def list_goals(",
            block_kind="python_def",
            required=(
                "GoalListItemResponse(",
                "effective_rollup=_goal_effective_rollup_response(effective_rollup),",
                "last_activity_at=activity_map.get(goal.id),",
                "last_transition_at=transition_map.get(goal.id),",
                "terminal_reason=terminal_reason,",
                "links=_goal_detail_links(goal.id, goal.project_id),",
                "next_steps=_goal_detail_next_steps(",
            ),
        ),
        SourceBlockContract(
            anchor="async def get_goal(",
            block_kind="python_def",
            required=(
                "GoalDetailResponse(",
                "stats=GoalSummaryStatsResponse(",
                "effective_rollup=_goal_effective_rollup_response(summary.effective_rollup),",
                "effective_hierarchy=_goal_effective_hierarchy_response(",
                "execution=_goal_execution_response(summary.execution),",
                "last_activity_at=activity_map.get(summary.goal.id),",
                "last_transition_at=transition_map.get(summary.goal.id),",
                "terminal_reason=terminal_reason,",
                "completion_context=completion_context,",
                "links=_goal_detail_links(summary.goal.id, summary.goal.project_id),",
                "next_steps=next_steps,",
            ),
        ),
        SourceBlockContract(
            anchor="async def get_goal_summary(",
            block_kind="python_def",
            required=(
                "goal=_goal_response(summary.goal, owner_map),",
                "stats=GoalSummaryStatsResponse(",
                "effective_rollup=_goal_effective_rollup_response(summary.effective_rollup),",
                "effective_hierarchy=_goal_effective_hierarchy_response(",
                "execution=_goal_execution_response(summary.execution),",
                "last_activity_at=activity_map.get(summary.goal.id),",
                "last_transition_at=transition_map.get(summary.goal.id),",
                "terminal_reason=terminal_reason,",
                "completion_context=completion_context,",
                "links=links,",
                "next_steps=next_steps,",
            ),
        ),
    ),
    "pms/api/routes/objectives.py": (
        SourceBlockContract(
            anchor="def _objective_links(",
            block_kind="python_def",
            required=(
                '"self": f"/api/v1/objectives/{objective_id}",',
                '"goal": f"/api/v1/goals/{goal_id}",',
                '"goal_summary": f"/api/v1/goals/{goal_id}/summary",',
                '"key_results": f"/api/v1/objectives/{objective_id}/key-results",',
                'links["project"] = f"/api/v1/projects/{project_id}"',
                'links["guide"] = "/api/v1/"',
            ),
        ),
        SourceBlockContract(
            anchor="def _objective_next_steps(",
            block_kind="python_def",
            required=(
                'f"GET /api/v1/objectives/{objective_id}",',
                'f"GET /api/v1/objectives/{objective_id}/key-results",',
                'f"GET /api/v1/goals/{goal_id}",',
                'f"GET /api/v1/goals/{goal_id}/summary",',
                'f"GET /api/v1/projects/{project_id}" if project_id else "",',
                'f"GET /api/v1/goals/{goal_id}/objectives?status=completed"',
            ),
        ),
        SourceBlockContract(
            anchor="def _objective_list_item_response(",
            block_kind="python_def",
            required=(
                "ObjectiveListItemResponse(",
                "project_id=project_id,",
                "effective_rollup=effective_rollup,",
                "effective_hierarchy=effective_hierarchy,",
                "last_activity_at=last_activity_at,",
                "last_transition_at=last_transition_at,",
                "terminal_reason=terminal_reason,",
                "links=_objective_links(",
                "next_steps=_objective_next_steps(",
            ),
        ),
        SourceBlockContract(
            anchor="def _objective_detail_response(",
            block_kind="python_def",
            required=(
                "ObjectiveDetailResponse(",
                "**list_payload.model_dump(),",
                "stats=ObjectiveSummaryStatsResponse(",
                "completion_context=_objective_completion_context(",
            ),
        ),
        SourceBlockContract(
            anchor="async def list_objectives(",
            block_kind="python_def",
            required=(
                "summaries = await goal_service.get_objective_summaries_for_objectives(",
                "activity_map = await goal_service.get_objective_last_activity_map(",
                "transition_map = await goal_service.get_objective_last_transition_map(",
                '"items": [',
                "_objective_list_item_response(",
                "last_activity_at=activity_map.get(objective.id),",
                "last_transition_at=transition_map.get(objective.id),",
            ),
        ),
        SourceBlockContract(
            anchor="async def get_objective(",
            block_kind="python_def",
            required=(
                "summary = await goal_service.get_objective_summary(objective_id)",
                "activity_map = await goal_service.get_objective_last_activity_map([objective_id])",
                "transition_map = await goal_service.get_objective_last_transition_map(",
                "return _objective_detail_response(",
                "last_activity_at=activity_map.get(objective_id),",
                "last_transition_at=transition_map.get(objective_id),",
            ),
        ),
    ),
    "pms/api/routes/key_results.py": (
        SourceBlockContract(
            anchor="def _key_result_links(",
            block_kind="python_def",
            required=(
                '"self": f"/api/v1/key-results/{key_result_id}",',
                '"objective": f"/api/v1/objectives/{objective_id}",',
                '"objective_key_results": f"/api/v1/objectives/{objective_id}/key-results",',
                '"goal": f"/api/v1/goals/{goal_id}",',
                '"goal_summary": f"/api/v1/goals/{goal_id}/summary",',
                'links["project"] = f"/api/v1/projects/{project_id}"',
                'links["guide"] = "/api/v1/"',
            ),
        ),
        SourceBlockContract(
            anchor="def _key_result_next_steps(",
            block_kind="python_def",
            required=(
                'f"GET /api/v1/key-results/{key_result_id}",',
                'f"GET /api/v1/objectives/{objective_id}",',
                'f"GET /api/v1/objectives/{objective_id}/key-results",',
                'f"GET /api/v1/goals/{goal_id}",',
                'f"GET /api/v1/goals/{goal_id}/summary",',
                'f"GET /api/v1/projects/{project_id}" if project_id else "",',
                'f"GET /api/v1/objectives/{objective_id}/key-results?status=completed"',
            ),
        ),
        SourceBlockContract(
            anchor="def _key_result_list_item_response(",
            block_kind="python_def",
            required=(
                "KeyResultListItemResponse(",
                "goal_id=goal_id,",
                "project_id=project_id,",
                "effective_rollup=_key_result_effective_rollup_response(key_result),",
                "last_activity_at=last_activity_at,",
                "last_transition_at=last_transition_at,",
                "terminal_reason=terminal_reason,",
                "links=_key_result_links(",
                "next_steps=_key_result_next_steps(",
            ),
        ),
        SourceBlockContract(
            anchor="def _key_result_detail_response(",
            block_kind="python_def",
            required=(
                "KeyResultDetailResponse(",
                "**list_payload.model_dump(),",
                "completion_context=_key_result_completion_context(",
            ),
        ),
        SourceBlockContract(
            anchor="async def list_key_results(",
            block_kind="python_def",
            required=(
                "activity_map = await goal_service.get_key_result_last_activity_map(",
                "transition_map = await goal_service.get_key_result_last_transition_map(",
                '"items": [',
                "_key_result_list_item_response(",
                "last_activity_at=activity_map.get(key_result.id),",
                "last_transition_at=transition_map.get(key_result.id),",
            ),
        ),
        SourceBlockContract(
            anchor="async def get_key_result(",
            block_kind="python_def",
            required=(
                "activity_map = await goal_service.get_key_result_last_activity_map([key_result_id])",
                "transition_map = await goal_service.get_key_result_last_transition_map(",
                "return _key_result_detail_response(",
                "last_activity_at=activity_map.get(key_result_id),",
                "last_transition_at=transition_map.get(key_result_id),",
            ),
        ),
    ),
    "pms/tools/project_tools.py": (
        SourceBlockContract(
            anchor="def _project_tool_links(",
            block_kind="python_def",
            required=(
                '"self": {"tool": "get_project", "args": {"identifier": project_id}},',
                '"summary": {"tool": "get_project_summary", "args": {"identifier": project_id}},',
                '"tasks": {"tool": "list_tasks", "args": {"project": project_id}},',
                '"dashboard": {"tool": "get_dashboard", "args": {}},',
            ),
        ),
        SourceBlockContract(
            anchor="def _project_summary_payload(",
            block_kind="python_def",
            required=(
                '"project_id": summary.project.id,',
                '"project_name": summary.project.name,',
                '"last_activity_at": summary.last_activity_at,',
                '"last_transition_at": summary.last_transition_at,',
                '"terminal_reason": summary.terminal_reason,',
                '"links": _project_tool_links(summary.project.id),',
                '"next_steps": _project_tool_next_steps(',
            ),
        ),
        SourceBlockContract(
            anchor="def _goal_summary_tool_links(",
            block_kind="python_def",
            required=(
                '"self": {"tool": "get_goal_summary", "args": {"identifier": goal_id}},',
                '"goal": {"tool": "get_goal", "args": {"identifier": goal_id}},',
                '"objectives": {"tool": "list_objectives", "args": {"goal_id": goal_id}},',
                '"plans": {"tool": "list_plans", "args": {"goal_id": goal_id}},',
                'links["project"] = {"tool": "get_project", "args": {"identifier": project_id}}',
                'links["tasks"] = {"tool": "list_tasks", "args": {"project": project_id}}',
            ),
        ),
        SourceBlockContract(
            anchor="def _goal_detail_tool_links(",
            block_kind="python_def",
            required=(
                '"self": {"tool": "get_goal", "args": {"identifier": goal_id}},',
                '"summary": {"tool": "get_goal_summary", "args": {"identifier": goal_id}},',
                '"objectives": {"tool": "list_objectives", "args": {"goal_id": goal_id}},',
                '"plans": {"tool": "list_plans", "args": {"goal_id": goal_id}},',
                'links["project"] = {"tool": "get_project", "args": {"identifier": project_id}}',
                'links["tasks"] = {"tool": "list_tasks", "args": {"project": project_id}}',
            ),
        ),
        SourceBlockContract(
            anchor="def _goal_list_item_payload(",
            block_kind="python_def",
            required=(
                '"effective_rollup": _goal_effective_rollup_payload(effective_rollup),',
                '"last_activity_at": last_activity_at,',
                '"last_transition_at": last_transition_at,',
                '"terminal_reason": terminal_reason,',
                '"links": _goal_detail_tool_links(goal.id, project_id=goal.project_id),',
                '"next_steps": next_steps,',
            ),
        ),
        SourceBlockContract(
            anchor="def _goal_detail_payload(",
            block_kind="python_def",
            required=(
                '"stats": {',
                '"effective_hierarchy": _goal_effective_hierarchy_payload(',
                '"effective_rollup": _goal_effective_rollup_payload(',
                '"execution": _goal_execution_payload(summary.execution),',
                '"last_activity_at": last_activity_at,',
                '"last_transition_at": last_transition_at,',
                '"terminal_reason": terminal_reason,',
                '"completion_context": completion_context,',
                '"links": _goal_detail_tool_links(',
                '"next_steps": next_steps,',
            ),
        ),
        SourceBlockContract(
            anchor="def _goal_summary_payload(",
            block_kind="python_def",
            required=(
                '"goal": summary.goal.to_dict(),',
                '"stats": {',
                '"effective_hierarchy": _goal_effective_hierarchy_payload(',
                '"effective_rollup": _goal_effective_rollup_payload(',
                '"execution": _goal_execution_payload(summary.execution),',
                '"last_activity_at": last_activity_at,',
                '"last_transition_at": last_transition_at,',
                '"terminal_reason": terminal_reason,',
                '"completion_context": completion_context,',
                '"links": _goal_summary_tool_links(',
                '"next_steps": next_steps,',
            ),
        ),
        SourceBlockContract(
            anchor="def _objective_tool_links(",
            block_kind="python_def",
            required=(
                '"self": {"tool": "get_objective", "args": {"objective_id": objective_id}},',
                '"goal": {"tool": "get_goal", "args": {"identifier": goal_id}},',
                '"goal_summary": {"tool": "get_goal_summary", "args": {"identifier": goal_id}},',
                '"key_results": {',
                '"tool": "list_key_results",',
                '"args": {"objective_id": objective_id},',
                'links["project"] = {"tool": "get_project", "args": {"identifier": project_id}}',
            ),
        ),
        SourceBlockContract(
            anchor="def _objective_tool_next_steps(",
            block_kind="python_def",
            required=(
                'f"Use get_objective with objective_id={objective_id}",',
                'f"Use list_key_results with objective_id={objective_id}",',
                'f"Use get_goal with identifier={goal_id}",',
                'f"Use get_goal_summary with identifier={goal_id}",',
                'steps.append(f"Use get_project with identifier={project_id}")',
                'steps.append(f"Use list_objectives with goal_id={goal_id} status=completed")',
                'steps.append(f"Use update_objective with objective_id={objective_id}")',
            ),
        ),
        SourceBlockContract(
            anchor="def _objective_completion_context_payload(",
            block_kind="python_def",
            required=(
                '"summary": (',
                '"This objective is terminal. Inspect linked key results, the parent "',
                '"next_steps": _objective_tool_next_steps(',
            ),
        ),
        SourceBlockContract(
            anchor="def _objective_list_item_payload(",
            block_kind="python_def",
            required=(
                '"project_id": getattr(objective, "project_id", None),',
                '"project_name": project_name,',
                '"effective_rollup": _goal_effective_rollup_payload(',
                '"effective_hierarchy": _objective_effective_hierarchy_payload(',
                '"last_activity_at": last_activity_at,',
                '"last_transition_at": last_transition_at,',
                '"terminal_reason": terminal_reason,',
                '"links": _objective_tool_links(',
                '"next_steps": _objective_tool_next_steps(',
            ),
        ),
        SourceBlockContract(
            anchor="def _objective_detail_payload(",
            block_kind="python_def",
            required=(
                '"project_id": getattr(objective, "project_id", None),',
                '"project_name": project_name,',
                '"stats": {',
                '"effective_rollup": _goal_effective_rollup_payload(',
                '"effective_hierarchy": _objective_effective_hierarchy_payload(',
                '"last_activity_at": last_activity_at,',
                '"last_transition_at": last_transition_at,',
                '"terminal_reason": terminal_reason,',
                '"completion_context": completion_context,',
                '"links": _objective_tool_links(',
                '"next_steps": next_steps,',
            ),
        ),
        SourceBlockContract(
            anchor="def _key_result_tool_links(",
            block_kind="python_def",
            required=(
                '"self": {"tool": "get_key_result", "args": {"key_result_id": key_result_id}},',
                '"objective": {"tool": "get_objective", "args": {"objective_id": objective_id}},',
                '"key_results": {',
                '"tool": "list_key_results",',
                '"args": {"objective_id": objective_id},',
                'links["goal"] = {"tool": "get_goal", "args": {"identifier": goal_id}}',
                'links["goal_summary"] = {',
                'links["project"] = {"tool": "get_project", "args": {"identifier": project_id}}',
            ),
        ),
        SourceBlockContract(
            anchor="def _key_result_tool_next_steps(",
            block_kind="python_def",
            required=(
                'f"Use get_key_result with key_result_id={key_result_id}",',
                'f"Use get_objective with objective_id={objective_id}",',
                'f"Use list_key_results with objective_id={objective_id}",',
                'steps.append(f"Use get_goal with identifier={goal_id}")',
                'steps.append(f"Use get_goal_summary with identifier={goal_id}")',
                'steps.append(f"Use get_project with identifier={project_id}")',
                'f"Use list_key_results with objective_id={objective_id} status=completed"',
                'steps.append(f"Use update_key_result with key_result_id={key_result_id}")',
            ),
        ),
        SourceBlockContract(
            anchor="def _key_result_completion_context_payload(",
            block_kind="python_def",
            required=(
                '"summary": (',
                '"This key result is terminal. Inspect the parent objective, goal, "',
                '"next_steps": _key_result_tool_next_steps(',
            ),
        ),
        SourceBlockContract(
            anchor="def _key_result_list_item_payload(",
            block_kind="python_def",
            required=(
                '"goal_id": goal_id,',
                '"goal_name": goal_name,',
                '"project_id": project_id,',
                '"project_name": project_name,',
                '"effective_rollup": _key_result_effective_rollup_payload(key_result),',
                '"last_activity_at": last_activity_at,',
                '"last_transition_at": last_transition_at,',
                '"terminal_reason": terminal_reason,',
                '"links": _key_result_tool_links(',
                '"next_steps": _key_result_tool_next_steps(',
            ),
        ),
        SourceBlockContract(
            anchor="def _key_result_detail_payload(",
            block_kind="python_def",
            required=(
                '"completion_context"] = completion_context',
                '"next_steps"] = next_steps',
            ),
        ),
        SourceBlockContract(
            anchor="async def list_key_results(",
            block_kind="python_def",
            required=(
                "context_map = await _key_result_parent_context_map(result.items)",
                "activity_map = await service.get_key_result_last_activity_map(",
                "transition_map = await service.get_key_result_last_transition_map(",
                "_key_result_list_item_payload(",
                '"kind": "mcp_key_result_list",',
                '"terminal_reason": terminal_reason,',
            ),
        ),
        SourceBlockContract(
            anchor="async def get_key_result(",
            block_kind="python_def",
            required=(
                "context_map = await _key_result_parent_context_map([key_result])",
                "activity_map = await service.get_key_result_last_activity_map([key_result.id])",
                "transition_map = await service.get_key_result_last_transition_map([key_result.id])",
                "_key_result_detail_payload(",
            ),
        ),
    ),
    "pms/cli/app.py": (
        SourceBlockContract(
            anchor="def _project_surface_payload(",
            block_kind="python_def",
            required=(
                '"project_id": getattr(project_obj, "id", None),',
                '"project_name": getattr(project_obj, "name", None),',
                '"last_activity_at": _to_iso(last_activity_at),',
                '"last_transition_at": _to_iso(last_transition_at),',
                '"terminal_reason": terminal_reason,',
                '"links": _normalize_command_links(links or {}),',
            ),
        ),
        SourceBlockContract(
            anchor="def _project_summary_surface_payload(",
            block_kind="python_def",
            required=(
                "status=effective_status,",
                "stored_status=project.status,",
                "terminal_reason=summary.terminal_reason,",
                "last_activity_at=summary.last_activity_at,",
                "last_transition_at=summary.last_transition_at,",
                '"self": f\'project show "{project.name}" --format json\',',
                '"tasks": f\'task list --project "{project.name}" --format json\',',
                '"summary": f\'project summary "{project.name}" --format json\',',
            ),
        ),
        SourceBlockContract(
            anchor="def _goal_detail_links(",
            block_kind="python_def",
            required=(
                '"self": f"goal show {goal_obj.id}",',
                '"summary": f"goal summary {goal_obj.id}",',
                '"objectives": f"objective list --goal-id {goal_obj.id}",',
                '"plans": f"plan list --goal-id {goal_obj.id} --format json",',
                '"project": _goal_project_show_command(goal_obj.project_id),',
                '"tasks": _goal_project_task_list_command(goal_obj.project_id),',
            ),
        ),
        SourceBlockContract(
            anchor="def _goal_summary_links(goal_obj: Any)",
            block_kind="python_def",
            required=(
                '"self": _cli_command(f"goal summary {goal_obj.id}"),',
                '"goal": _cli_command(f"goal show {goal_obj.id}"),',
                '"objectives": _cli_command(',
                '"project": (',
                '"tasks": (',
                '"plans": _cli_command(f"plan list --goal-id {goal_obj.id} --format json"),',
            ),
        ),
        SourceBlockContract(
            anchor="async def goal_list(",
            block_kind="python_def",
            required=(
                '"effective_rollup": _goal_effective_rollup_struct(',
                '"last_activity_at": goal_last_activity,',
                '"last_transition_at": goal_last_transition,',
                '"terminal_reason": goal_terminal_reason,',
                '"links": goal_links,',
                '"status_groups": status_groups,',
                '"items_by_status": {',
            ),
        ),
        SourceBlockContract(
            anchor="async def goal_show(",
            block_kind="python_def",
            required=(
                'payload["effective_rollup"] = _goal_effective_rollup_payload(',
                'payload["effective_hierarchy"] = _goal_effective_hierarchy_payload(',
                '"last_activity_at": _to_iso(goal_last_activity),',
                '"last_transition_at": _to_iso(goal_last_transition),',
                '"terminal_reason": goal_terminal_reason,',
                '"completion_context": goal_completion_context,',
                '"links": links,',
                'payload["execution"] = _goal_execution_payload(',
                "payload = _payload_with_normalized_next_steps(",
            ),
        ),
        SourceBlockContract(
            anchor="async def goal_summary(goal_ref: str, pick: bool, output_format: str) -> None:",
            block_kind="python_def",
            required=(
                '"goal": _public_entity_payload(summary.goal),',
                '"stats": _goal_stats_payload(summary),',
                '"effective_hierarchy": _goal_effective_hierarchy_payload(summary),',
                '"effective_rollup": _goal_effective_rollup_payload(summary),',
                '"last_activity_at": _to_iso(goal_last_activity),',
                '"last_transition_at": _to_iso(goal_last_transition),',
                '"terminal_reason": goal_terminal_reason,',
                '"completion_context": goal_completion_context,',
                '"links": _goal_summary_links(summary.goal),',
                'payload["execution"] = _goal_execution_payload(',
                "payload = _payload_with_normalized_next_steps(",
            ),
        ),
        SourceBlockContract(
            anchor="def _objective_completion_context_payload(",
            block_kind="python_def",
            required=(
                '"summary": (',
                '"This objective is terminal. Inspect linked key results, the parent "',
                'f"objective show {objective_id}",',
                'f"keyresult list --objective-id {objective_id} --format json",',
                'f"goal show {goal_id}",',
                'f"goal summary {goal_id}",',
                'f"objective list --goal-id {goal_id} --status completed --format json",',
            ),
        ),
        SourceBlockContract(
            anchor="def _objective_detail_links(",
            block_kind="python_def",
            required=(
                '"self": f"objective show {objective_obj.id}",',
                '"goal": f"goal show {objective_obj.goal_id}",',
                '"goal_summary": f"goal summary {objective_obj.goal_id}",',
                '"project": _goal_project_show_command(project_id),',
                '"key_results": f"keyresult list --objective-id {objective_obj.id} --format json",',
                '"owner": owner_link,',
            ),
        ),
        SourceBlockContract(
            anchor="def _objective_lifecycle_next_steps(",
            block_kind="python_def",
            required=(
                'objective_show_command = f"objective show {summary.objective.id}"',
                'f"keyresult list --objective-id {summary.objective.id} --format json"',
                'goal_show_command = f"goal show {summary.objective.goal_id}"',
                'goal_summary_command = f"goal summary {summary.objective.goal_id}"',
                'f"objective list --goal-id {summary.objective.goal_id} "',
                'f"objective update {summary.objective.id}",',
            ),
        ),
        SourceBlockContract(
            anchor="async def objective_list(",
            block_kind="python_def",
            required=(
                "objective_summaries = await service.get_objective_summaries_for_objectives(",
                "activity_map = await service.get_objective_last_activity_map(objective_ids)",
                "transition_map = await service.get_objective_last_transition_map(",
                "links = _objective_list_links(",
                "next_steps = (",
                '"effective_rollup": (',
                '"effective_hierarchy": (',
                '"stats": (',
                '"last_activity_at": objective_last_activity,',
                '"last_transition_at": objective_last_transition,',
                '"terminal_reason": terminal_reason,',
                '"completion_context": _objective_completion_context_payload(',
                "payload = _payload_with_normalized_next_steps(payload, *next_steps)",
            ),
        ),
        SourceBlockContract(
            anchor="async def objective_show(",
            block_kind="python_def",
            required=(
                "objective_summary = await service.get_objective_summary(objective.id)",
                "objective_activity_map = await service.get_objective_last_activity_map(",
                "objective_transition_map = await service.get_objective_last_transition_map(",
                "objective_completion_context = _objective_completion_context_payload(",
                "links = _objective_detail_links(",
                "next_steps = (",
                '"stats": (',
                '"effective_rollup": (',
                '"effective_hierarchy": (',
                '"last_activity_at": objective_last_activity,',
                '"last_transition_at": objective_last_transition,',
                '"terminal_reason": objective_terminal_reason,',
                '"completion_context": objective_completion_context,',
                "payload = _payload_with_normalized_next_steps(payload, *next_steps)",
            ),
        ),
        SourceBlockContract(
            anchor="def _key_result_completion_context_payload(",
            block_kind="python_def",
            required=(
                '"summary": (',
                '"This key result is terminal. Inspect the parent objective, goal, or "',
                'f"keyresult show {key_result_id}",',
                'f"objective show {objective_id}",',
                'f"keyresult list --objective-id {objective_id} --format json",',
                'f"goal show {goal_id}" if goal_id else "",',
                'f"goal summary {goal_id}" if goal_id else "",',
                'f"keyresult list --objective-id {objective_id} --status completed --format json",',
            ),
        ),
        SourceBlockContract(
            anchor="def _key_result_detail_links(",
            block_kind="python_def",
            required=(
                '"self": f"keyresult show {key_result_obj.id}",',
                '"objective": (',
                '"key_results": (',
                '"goal": f"goal show {goal_id}" if goal_id else None,',
                '"goal_summary": f"goal summary {goal_id}" if goal_id else None,',
                '"project": _goal_project_show_command(project_id),',
                '"owner": owner_link,',
            ),
        ),
        SourceBlockContract(
            anchor="def _key_result_lifecycle_next_steps(",
            block_kind="python_def",
            required=(
                'f"keyresult show {key_result_id}",',
                'f"objective show {objective_id}",',
                'f"keyresult list --objective-id {objective_id} --format json",',
                'f"goal show {goal_id}" if goal_id else "",',
                'f"goal summary {goal_id}" if goal_id else "",',
                '_goal_project_show_command(project_id) or "",',
                'f"keyresult list --objective-id {objective_id} --status completed --format json"',
                'f"keyresult update {key_result_id}" if terminal_reason is None else "",',
            ),
        ),
        SourceBlockContract(
            anchor="async def keyresult_list(",
            block_kind="python_def",
            required=(
                "activity_map = await service.get_key_result_last_activity_map(",
                "transition_map = await service.get_key_result_last_transition_map(",
                "terminal_reason = _key_result_terminal_reason(key_result)",
                "links = _key_result_list_links(",
                "next_steps = _key_result_lifecycle_next_steps(",
                '"effective_rollup": _key_result_effective_rollup_payload(',
                '"last_activity_at": _to_iso(activity_map.get(key_result.id)),',
                '"last_transition_at": _to_iso(',
                '"terminal_reason": terminal_reason,',
                '"links": links,',
            ),
        ),
        SourceBlockContract(
            anchor="async def keyresult_show(",
            block_kind="python_def",
            required=(
                "activity_map = await service.get_key_result_last_activity_map([key_result.id])",
                "transition_map = await service.get_key_result_last_transition_map(",
                "terminal_reason = _key_result_terminal_reason(key_result)",
                "links = _key_result_detail_links(",
                "next_steps = _key_result_lifecycle_next_steps(",
                '"effective_rollup": _key_result_effective_rollup_payload(',
                '"last_activity_at": _to_iso(activity_map.get(key_result.id)),',
                '"last_transition_at": _to_iso(',
                '"terminal_reason": terminal_reason,',
                '"completion_context": _key_result_completion_context_payload(',
                '"links": links,',
            ),
        ),
    ),
    "pms/api/routes/projects.py": (
        SourceBlockContract(
            anchor="def build_project_detail_links(",
            block_kind="python_def",
            required=(
                '"self": f"/api/v1/projects/{project_id}",',
                '"summary": f"/api/v1/projects/{project_id}/summary",',
                '"operator_overview": f"/api/v1/projects/{project_id}/operator-overview",',
                '"tasks": f"/api/v1/tasks?project_id={project_id}",',
                '"plans": f"/api/v1/plans?project_id={project_id}",',
            ),
        ),
        SourceBlockContract(
            anchor="def build_project_detail_next_steps(",
            block_kind="python_def",
            required=(
                'f"GET /api/v1/projects/{project_id}/summary",',
                'f"GET /api/v1/projects/{project_id}/operator-overview",',
                'f"GET /api/v1/tasks?project_id={project_id}",',
                'f"GET /api/v1/plans?project_id={project_id}",',
                'steps.insert(0, f"GET /api/v1/tasks/{focus_task_id}")',
            ),
        ),
        SourceBlockContract(
            anchor="def _project_to_response(",
            block_kind="python_def",
            required=(
                "ProjectResponse(",
                "stored_status=(",
                "last_activity_at=last_activity_at,",
                "last_transition_at=last_transition_at,",
                "terminal_reason=terminal_reason,",
                "focus_task=focus_task,",
                "links=links or {},",
                "next_steps=next_steps or [],",
            ),
        ),
        SourceBlockContract(
            anchor="def _project_summary_to_response(",
            block_kind="python_def",
            required=(
                "effective_status = summary.effective_status or summary.project.status",
                "last_activity_at=summary.last_activity_at,",
                "last_transition_at=summary.last_transition_at,",
                "terminal_reason=summary.terminal_reason,",
                "focus_task=focus_task,",
                "links=links,",
                "next_steps=next_steps,",
            ),
        ),
    ),
}


def audit_source(
    source: str,
    *,
    path: Path,
    block_contracts: tuple[SourceBlockContract, ...],
) -> tuple[CrossSurfaceLifecycleAggregateSourceIssue, ...]:
    """Audit one source file against the static aggregate contracts."""
    try:
        relative_file = str(path.relative_to(REPO_ROOT))
    except ValueError:
        relative_file = str(path)

    return tuple(
        CrossSurfaceLifecycleAggregateSourceIssue(file=relative_file, reason=reason)
        for reason in audit_block_contracts(
            source,
            block_contracts=block_contracts,
            contract_label="cross-surface lifecycle aggregate contract",
        )
    )


def run_audit(
    root_dir: Path = REPO_ROOT,
) -> tuple[CrossSurfaceLifecycleAggregateSourceIssue, ...]:
    """Audit the maintained source files that define aggregate lifecycle payloads."""
    issues: list[CrossSurfaceLifecycleAggregateSourceIssue] = []
    for (
        relative_path,
        block_contracts,
    ) in CROSS_SURFACE_LIFECYCLE_AGGREGATE_SOURCE_CONTRACTS.items():
        path = root_dir / relative_path
        source = path.read_text(encoding="utf-8")
        issues.extend(
            audit_source(
                source,
                path=path,
                block_contracts=block_contracts,
            )
        )
    return tuple(issues)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit static cross-surface lifecycle aggregate source contracts."
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON payload")
    parser.add_argument("--check", action="store_true", help="Exit non-zero on issues")
    args = parser.parse_args()

    issues = run_audit()
    checked = len(CROSS_SURFACE_LIFECYCLE_AGGREGATE_SOURCE_CONTRACTS)
    if args.json:
        print(
            json.dumps(
                {
                    "checked": checked,
                    "issues": [
                        {"file": issue.file, "reason": issue.reason} for issue in issues
                    ],
                },
                indent=2,
            )
        )
    else:
        print(
            "Cross-surface lifecycle aggregate source contract audit\n"
            f"checked={checked} issues={len(issues)}"
        )
        for issue in issues:
            print(f"- {issue.file}: {issue.reason}")

    if args.check and issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
