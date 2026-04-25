"""Unit coverage for static cross-surface lifecycle aggregate source contracts."""

from pathlib import Path

from scripts.audit_cross_surface_lifecycle_aggregate_source_contracts import (
    CROSS_SURFACE_LIFECYCLE_AGGREGATE_SOURCE_CONTRACTS,
    audit_source,
    run_audit,
)


def _render_python_def(anchor: str, required: tuple[str, ...]) -> str:
    header = anchor if anchor.rstrip().endswith(":") else f"{anchor}:"
    body_lines: list[str] = []
    for snippet in required:
        for line in snippet.splitlines():
            body_lines.append(f"    {line}")
    return f"{header}\n" + "\n".join(body_lines) + "\n\n"


def _write_contract_file(
    root: Path,
    relative_path: str,
    contracts: tuple[object, ...],
) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = []
    for contract in contracts:
        rendered.append(_render_python_def(contract.anchor, contract.required))
    path.write_text("".join(rendered), encoding="utf-8")


def _contract(relative_path: str, anchor: str):
    return next(
        contract
        for contract in CROSS_SURFACE_LIFECYCLE_AGGREGATE_SOURCE_CONTRACTS[
            relative_path
        ]
        if contract.anchor == anchor
    )


def test_run_audit_accepts_consistent_cross_surface_tree(tmp_path: Path) -> None:
    for (
        relative_path,
        contracts,
    ) in CROSS_SURFACE_LIFECYCLE_AGGREGATE_SOURCE_CONTRACTS.items():
        _write_contract_file(tmp_path, relative_path, contracts)

    issues = run_audit(tmp_path)

    assert issues == ()


def test_audit_source_flags_missing_mcp_goal_detail_link_contract() -> None:
    issues = audit_source(
        """
def unrelated_goal_links(goal_id: str, *, project_id: str | None = None):
    links = {
        "plans": {"tool": "list_plans", "args": {"goal_id": goal_id}},
    }
    return links

def _goal_detail_tool_links(
    goal_id: str, *, project_id: str | None = None
) -> dict[str, object]:
    links: dict[str, object] = {
        "self": {"tool": "get_goal", "args": {"identifier": goal_id}},
        "summary": {"tool": "get_goal_summary", "args": {"identifier": goal_id}},
        "objectives": {"tool": "list_objectives", "args": {"goal_id": goal_id}},
    }
    if project_id:
        links["project"] = {"tool": "get_project", "args": {"identifier": project_id}}
        links["tasks"] = {"tool": "list_tasks", "args": {"project": project_id}}
    return links
""",
        path=Path("pms/tools/project_tools.py"),
        block_contracts=(
            CROSS_SURFACE_LIFECYCLE_AGGREGATE_SOURCE_CONTRACTS[
                "pms/tools/project_tools.py"
            ][3],
        ),
    )

    assert any('"plans": {"tool": "list_plans"' in issue.reason for issue in issues)


def test_audit_source_scopes_project_terminal_reason_to_summary_payload_block() -> None:
    issues = audit_source(
        """
def unrelated_project_payload(summary):
    return {
        "terminal_reason": summary.terminal_reason,
    }

def _project_summary_payload(
    summary,
    *,
    focus_task=None,
):
    return {
        "project_id": summary.project.id,
        "project_name": summary.project.name,
        "last_activity_at": summary.last_activity_at,
        "last_transition_at": summary.last_transition_at,
        "links": _project_tool_links(summary.project.id),
        "next_steps": _project_tool_next_steps(summary.project.id),
    }
""",
        path=Path("pms/tools/project_tools.py"),
        block_contracts=(
            CROSS_SURFACE_LIFECYCLE_AGGREGATE_SOURCE_CONTRACTS[
                "pms/tools/project_tools.py"
            ][1],
        ),
    )

    assert any(
        '"terminal_reason": summary.terminal_reason,' in issue.reason
        for issue in issues
    )


def test_audit_source_flags_missing_api_objective_key_results_link_contract() -> None:
    issues = audit_source(
        """
def _objective_links(
    *,
    objective_id: str,
    goal_id: str,
    project_id: str | None,
    include_guide: bool,
) -> dict[str, str]:
    links: dict[str, str] = {
        "self": f"/api/v1/objectives/{objective_id}",
        "goal": f"/api/v1/goals/{goal_id}",
        "goal_summary": f"/api/v1/goals/{goal_id}/summary",
    }
    if project_id:
        links["project"] = f"/api/v1/projects/{project_id}"
    if include_guide:
        links["guide"] = "/api/v1/"
    return links
""",
        path=Path("pms/api/routes/objectives.py"),
        block_contracts=(
            _contract("pms/api/routes/objectives.py", "def _objective_links("),
        ),
    )

    assert any(
        '"key_results": f"/api/v1/objectives/{objective_id}/key-results",'
        in issue.reason
        for issue in issues
    )


def test_audit_source_flags_missing_api_key_result_collection_link_contract() -> None:
    issues = audit_source(
        """
def _key_result_links(
    *,
    key_result_id: str,
    objective_id: str,
    goal_id: str,
    project_id: str | None,
    include_guide: bool,
) -> dict[str, str]:
    links: dict[str, str] = {
        "self": f"/api/v1/key-results/{key_result_id}",
        "objective": f"/api/v1/objectives/{objective_id}",
        "goal": f"/api/v1/goals/{goal_id}",
        "goal_summary": f"/api/v1/goals/{goal_id}/summary",
    }
    if project_id:
        links["project"] = f"/api/v1/projects/{project_id}"
    if include_guide:
        links["guide"] = "/api/v1/"
    return links
""",
        path=Path("pms/api/routes/key_results.py"),
        block_contracts=(
            _contract("pms/api/routes/key_results.py", "def _key_result_links("),
        ),
    )

    assert any(
        '"objective_key_results": f"/api/v1/objectives/{objective_id}/key-results",'
        in issue.reason
        for issue in issues
    )


def test_audit_source_scopes_objective_terminal_reason_to_mcp_detail_payload_block() -> (
    None
):
    issues = audit_source(
        """
def unrelated_objective_payload(summary):
    return {
        "terminal_reason": "not the right block",
        "completion_context": "not the right block",
    }

def _objective_detail_payload(
    summary: object,
    *,
    last_activity_at: object | None,
    last_transition_at: object | None,
    project_name: str | None = None,
) -> dict[str, object]:
    return {
        "project_id": getattr(summary.objective, "project_id", None),
        "project_name": project_name,
        "stats": {},
        "effective_rollup": {},
        "effective_hierarchy": {},
        "last_activity_at": last_activity_at,
        "last_transition_at": last_transition_at,
        "links": {},
        "next_steps": [],
    }
""",
        path=Path("pms/tools/project_tools.py"),
        block_contracts=(
            _contract("pms/tools/project_tools.py", "def _objective_detail_payload("),
        ),
    )

    assert any(
        '"terminal_reason": terminal_reason,' in issue.reason for issue in issues
    )


def test_audit_source_scopes_key_result_completion_context_to_cli_show_block() -> None:
    issues = audit_source(
        """
def unrelated_key_result_payload():
    return {
        "completion_context": "not the right block",
    }

async def keyresult_show(key_result_ref: str) -> None:
    payload = {
        "effective_rollup": {},
        "last_activity_at": "2026-04-24T12:00:00+00:00",
        "last_transition_at": "2026-04-24T12:05:00+00:00",
        "terminal_reason": "done",
        "links": {},
    }
    payload = _payload_with_normalized_next_steps(payload)
""",
        path=Path("pms/cli/app.py"),
        block_contracts=(_contract("pms/cli/app.py", "async def keyresult_show("),),
    )

    assert any(
        '"completion_context": _key_result_completion_context_payload(' in issue.reason
        for issue in issues
    )
