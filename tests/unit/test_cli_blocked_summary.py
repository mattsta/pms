from pms.cli.app import _blocked_summary_for_details, _dependency_summary_for_details


def test_blocked_summary_prefers_draft_lock_when_dependencies_are_done() -> None:
    summary = _blocked_summary_for_details(
        [{"id": "a", "title": "Primary Blocker", "status": "done"}],
        ["Draft Locked Dependent Plan"],
        "Primary Blocker",
    )

    assert summary == "Draft plan lock: Draft Locked Dependent Plan"


def test_blocked_summary_keeps_active_dependency_when_lock_also_exists() -> None:
    summary = _blocked_summary_for_details(
        [{"id": "a", "title": "Primary Blocker", "status": "in_progress"}],
        ["Draft Locked Dependent Plan"],
        "Primary Blocker",
    )

    assert summary == "Primary Blocker; draft plan lock: Draft Locked Dependent Plan"


def test_blocked_summary_falls_back_to_dependency_summary_without_lock() -> None:
    summary = _blocked_summary_for_details(
        [{"id": "a", "title": "Primary Blocker", "status": "in_progress"}],
        [],
        "Primary Blocker",
    )

    assert summary == "Primary Blocker"


def test_dependency_summary_collapses_large_blocker_sets() -> None:
    summary = _dependency_summary_for_details(
        [
            {"id": "a", "title": "Done One", "status": "done"},
            {"id": "b", "title": "Active One", "status": "in_progress"},
            {"id": "c", "title": "Todo One", "status": "todo"},
            {"id": "d", "title": "Todo Two", "status": "todo"},
            {"id": "e", "title": "Done Two", "status": "done"},
        ]
    )

    assert summary == "5 blockers (3 active): Active One, Todo One, Todo Two"
