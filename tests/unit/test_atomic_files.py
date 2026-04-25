"""Unit coverage for atomic local file writers."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from pms.utils.atomic_files import write_json_atomic, write_text_atomic


def test_write_text_atomic_replaces_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "artifact.txt"

    write_text_atomic(target, "first")
    write_text_atomic(target, "second")

    assert target.read_text(encoding="utf-8") == "second"


def test_write_json_atomic_renders_json_with_trailing_newline(tmp_path: Path) -> None:
    target = tmp_path / "artifact.json"

    write_json_atomic(target, {"status": "ok"})

    assert target.read_text(encoding="utf-8") == '{\n  "status": "ok"\n}\n'


def test_write_text_atomic_removes_temp_file_when_replace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "artifact.txt"
    target.write_text("stable", encoding="utf-8")

    def fail_replace(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        write_text_atomic(target, "new")

    assert target.read_text(encoding="utf-8") == "stable"
    assert list(tmp_path.glob("*.tmp")) == []
