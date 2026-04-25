from scripts.verify_public_release_checkpoint import audit_payloads


def _base_payloads() -> dict[str, dict]:
    return {
        "project_task_list": {
            "visible_totals": {
                "todo_tasks": 0,
                "in_progress_tasks": 0,
                "blocked_tasks": 0,
                "in_review_tasks": 0,
            },
            "focus_task": None,
        },
        "start": {"focus_task": None},
        "dashboard": {
            "focus_task": None,
            "active_projects": [],
            "ready_tasks": [],
            "in_progress_tasks": [],
            "blocked_items": [],
        },
        "runtime": {"items": [], "unmanaged_local_processes": []},
    }


def test_audit_payloads_accepts_clean_release_checkpoint() -> None:
    issues = audit_payloads(_base_payloads())
    assert issues == ()


def test_audit_payloads_flags_nonterminal_release_project() -> None:
    payloads = _base_payloads()
    payloads["project_task_list"]["visible_totals"]["in_progress_tasks"] = 1

    issues = audit_payloads(payloads)

    assert len(issues) == 1
    assert issues[0].surface == "project_task_list"
    assert "in_progress_tasks=1" in issues[0].reason


def test_audit_payloads_flags_release_project_in_dashboard() -> None:
    payloads = _base_payloads()
    payloads["dashboard"]["active_projects"] = [
        {"project_name": "PMS Release Readiness and Public Documentation"}
    ]

    issues = audit_payloads(payloads)

    assert len(issues) == 1
    assert issues[0].surface == "dashboard"
    assert "active_projects" in issues[0].reason


def test_audit_payloads_flags_runtime_residue() -> None:
    payloads = _base_payloads()
    payloads["runtime"]["unmanaged_local_processes"] = [{"pid": 12345}]

    issues = audit_payloads(payloads)

    assert len(issues) == 1
    assert issues[0].surface == "runtime"
    assert "unmanaged" in issues[0].reason
