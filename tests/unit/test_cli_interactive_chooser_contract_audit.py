from __future__ import annotations

from scripts.audit_cli_interactive_chooser_contracts import (
    CliInteractiveChooserIssue,
    InteractiveChooserSurfaceSpec,
    evaluate_surface_outputs,
)


def test_cli_interactive_chooser_contract_accepts_required_fragments() -> None:
    spec = InteractiveChooserSurfaceSpec(
        name="sample",
        args=("demo",),
        width=80,
        input_text="1\n",
        required_fragments=("Pick item:", "Resolved"),
    )

    issues = evaluate_surface_outputs(
        spec,
        non_tty_output="Pick item:\nResolved\n",
        tty_output="Pick item:\nResolved\n",
    )

    assert issues == ()


def test_cli_interactive_chooser_contract_flags_ansi_in_non_tty_output() -> None:
    spec = InteractiveChooserSurfaceSpec(
        name="sample",
        args=("demo",),
        width=80,
        input_text="1\n",
        required_fragments=("Resolved",),
    )

    issues = evaluate_surface_outputs(
        spec,
        non_tty_output="\x1b[31mResolved\x1b[0m\n",
        tty_output="Resolved\n",
    )

    assert (
        CliInteractiveChooserIssue(
            surface="sample",
            mode="non_tty",
            reason="non-interactive output still contains ANSI escape sequences",
        )
        in issues
    )


def test_cli_interactive_chooser_contract_flags_missing_fragment_per_mode() -> None:
    spec = InteractiveChooserSurfaceSpec(
        name="sample",
        args=("demo",),
        width=80,
        input_text="1\n",
        required_fragments=("Pick item:", "Resolved"),
    )

    issues = evaluate_surface_outputs(
        spec,
        non_tty_output="Pick item:\n",
        tty_output="Pick item:\nResolved\n",
    )

    assert issues == (
        CliInteractiveChooserIssue(
            surface="sample",
            mode="non_tty",
            reason="missing required semantic fragment: Resolved",
        ),
    )
