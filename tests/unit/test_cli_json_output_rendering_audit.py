from __future__ import annotations

from pathlib import Path

from scripts.audit_cli_json_output_rendering import audit_source, run_audit


def test_cli_json_output_rendering_audit_accepts_click_echo_json_branch(
    tmp_path: Path,
) -> None:
    app_path = tmp_path / "pms/cli/app.py"
    app_path.parent.mkdir(parents=True, exist_ok=True)
    app_path.write_text(
        """
import click
import json

async def sample(output_format: str, payload: dict[str, str]) -> None:
    if output_format == "json":
        click.echo(json.dumps(payload))
        return
    console.print("ok")
""".strip(),
        encoding="utf-8",
    )

    assert run_audit(root_dir=tmp_path) == ()


def test_cli_json_output_rendering_audit_flags_console_print_in_json_branch() -> None:
    issues = audit_source(
        """
async def sample(output_format: str) -> None:
    if output_format == "json":
        console.print("bad")
        return
""".strip(),
        path=Path("fixture.py"),
    )

    assert len(issues) == 1
    assert issues[0].function == "sample"
    assert issues[0].line == 3
    assert "console.print()" in issues[0].reason


def test_cli_json_output_rendering_audit_flags_nested_console_render_calls() -> None:
    issues = audit_source(
        """
async def sample(output_format: str, show_extra: bool) -> None:
    if output_format == "json":
        if show_extra:
            console.rule("bad")
        return
""".strip(),
        path=Path("fixture.py"),
    )

    assert len(issues) == 1
    assert issues[0].function == "sample"
    assert issues[0].line == 4
    assert "console.rule()" in issues[0].reason
