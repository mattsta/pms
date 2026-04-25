"""Helpers for normalizing generated Markdown artifacts."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

PRETTIER_VERSION = "3.6.2"


def format_markdown_with_prettier(markdown: str, *, filepath: str | Path) -> str:
    """Normalize markdown with the maintained Prettier formatter."""
    prettier_bin = shutil.which("prettier")
    if prettier_bin is None:
        raise RuntimeError(
            "prettier is required to generate maintained markdown docs. "
            f"Install it with `npm install -g prettier@{PRETTIER_VERSION}`."
        )

    completed = subprocess.run(
        [prettier_bin, "--stdin-filepath", str(filepath)],
        input=markdown,
        capture_output=True,
        check=False,
        text=True,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.strip() or "unknown prettier failure"
        raise RuntimeError(f"prettier failed for {filepath}: {stderr}")
    return completed.stdout
