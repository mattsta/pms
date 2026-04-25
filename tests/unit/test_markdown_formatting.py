from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from pms.utils import markdown_formatting


def test_format_markdown_with_prettier_uses_prettier(monkeypatch) -> None:
    def fake_run(cmd, *, input, capture_output, check, text):
        assert cmd == ["/usr/bin/prettier", "--stdin-filepath", "docs/out.md"]
        assert input == "# title\n"
        assert capture_output is True
        assert check is False
        assert text is True
        return subprocess.CompletedProcess(cmd, 0, stdout="# title\n", stderr="")

    monkeypatch.setattr(
        markdown_formatting.shutil, "which", lambda name: "/usr/bin/prettier"
    )
    monkeypatch.setattr(markdown_formatting.subprocess, "run", fake_run)

    rendered = markdown_formatting.format_markdown_with_prettier(
        "# title\n",
        filepath=Path("docs/out.md"),
    )

    assert rendered == "# title\n"


def test_format_markdown_with_prettier_requires_prettier(monkeypatch) -> None:
    monkeypatch.setattr(markdown_formatting.shutil, "which", lambda name: None)

    with pytest.raises(RuntimeError, match="prettier is required"):
        markdown_formatting.format_markdown_with_prettier(
            "# title\n",
            filepath=Path("docs/out.md"),
        )
