from __future__ import annotations

from scripts.audit_cli_text_summary_contracts import (
    CliTextSummaryIssue,
    TextSummarySurfaceSpec,
    evaluate_surface_outputs,
)


def test_cli_text_summary_contract_accepts_required_fragments() -> None:
    spec = TextSummarySurfaceSpec(
        name="sample",
        args=("demo",),
        width=80,
        required_fragments=("Alpha", "Beta"),
    )

    issues = evaluate_surface_outputs(
        spec,
        non_tty_output="Alpha\nBeta\n",
        tty_output="Alpha\nBeta\n",
    )

    assert issues == ()


def test_cli_text_summary_contract_flags_ansi_in_non_tty_output() -> None:
    spec = TextSummarySurfaceSpec(
        name="sample",
        args=("demo",),
        width=80,
        required_fragments=("Alpha",),
    )

    issues = evaluate_surface_outputs(
        spec,
        non_tty_output="\x1b[31mAlpha\x1b[0m\n",
        tty_output="Alpha\n",
    )

    assert (
        CliTextSummaryIssue(
            surface="sample",
            mode="non_tty",
            reason="non-interactive output still contains ANSI escape sequences",
        )
        in issues
    )


def test_cli_text_summary_contract_flags_missing_fragment_per_mode() -> None:
    spec = TextSummarySurfaceSpec(
        name="sample",
        args=("demo",),
        width=80,
        required_fragments=("Alpha", "Beta"),
    )

    issues = evaluate_surface_outputs(
        spec,
        non_tty_output="Alpha\n",
        tty_output="Alpha\nBeta\n",
    )

    assert issues == (
        CliTextSummaryIssue(
            surface="sample",
            mode="non_tty",
            reason="missing required semantic fragment: Beta",
        ),
    )
