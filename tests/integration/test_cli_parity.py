"""CLI parity guardrails for Python vs Rust command trees."""

from __future__ import annotations

import subprocess


def test_cli_parity_allowlist() -> None:
    result = subprocess.run(
        ["uv", "run", "python", "scripts/cli_parity_audit.py", "--check"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)
