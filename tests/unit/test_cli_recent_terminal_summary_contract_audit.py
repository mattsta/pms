"""Unit coverage for the recent-terminal CLI summary contract audit."""

from scripts.audit_cli_recent_terminal_summary_contracts import (
    RecentTerminalSurfaceSpec,
    evaluate_surface_outputs,
)


def test_cli_recent_terminal_summary_contract_accepts_required_fragments() -> None:
    spec = RecentTerminalSurfaceSpec(
        name="start recent terminal summary",
        args=("start",),
        width=120,
        required_fragments=("Recent terminal work:", "Completed Start Project"),
    )

    issues = evaluate_surface_outputs(
        spec,
        non_tty_output="Recent terminal work:\nCompleted Start Project\n",
        tty_output="Recent terminal work:\nCompleted Start Project\n",
    )

    assert issues == ()


def test_cli_recent_terminal_summary_contract_flags_ansi_in_non_tty_output() -> None:
    spec = RecentTerminalSurfaceSpec(
        name="dashboard recent terminal summary",
        args=("dashboard",),
        width=120,
        required_fragments=("Recently Completed Projects:",),
    )

    issues = evaluate_surface_outputs(
        spec,
        non_tty_output="\x1b[32mRecently Completed Projects:\x1b[0m",
        tty_output="Recently Completed Projects:",
    )

    assert any(
        issue.mode == "non_tty" and "ANSI escape sequences" in issue.reason
        for issue in issues
    )


def test_cli_recent_terminal_summary_contract_flags_missing_fragment_per_mode() -> None:
    spec = RecentTerminalSurfaceSpec(
        name="plan list recent terminal summary",
        args=("plan", "list"),
        width=120,
        required_fragments=(
            "Execution State: all surfaced plans are already terminal",
        ),
    )

    issues = evaluate_surface_outputs(
        spec,
        non_tty_output="Execution State: all surfaced plans are already terminal",
        tty_output="missing",
    )

    assert len(issues) == 1
    assert issues[0].mode == "tty"
    assert "missing required semantic fragment" in issues[0].reason


def test_cli_recent_terminal_summary_contract_ignores_layout_wrapping() -> None:
    spec = RecentTerminalSurfaceSpec(
        name="dashboard recent terminal summary",
        args=("dashboard",),
        width=120,
        required_fragments=(
            'Completed-scope shortcuts: uv run pms project show "Completed Visible Project" --format json',
        ),
    )

    wrapped = (
        "Completed-scope shortcuts: uv run pms project \n"
        'show "Completed Visible Project" --format json\n'
    )
    issues = evaluate_surface_outputs(
        spec,
        non_tty_output=wrapped,
        tty_output=wrapped,
    )

    assert issues == ()
