"""Helpers for atomic local file writes."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def write_text_atomic(
    path: Path,
    content: str,
    *,
    encoding: str = "utf-8",
    mode: int | None = None,
    fsync: bool = True,
) -> None:
    """Write text content atomically beside the target path."""

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path_str = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temp_path = Path(temp_path_str)
    try:
        if mode is not None:
            os.fchmod(fd, mode)
        with os.fdopen(fd, "w", encoding=encoding) as handle:
            handle.write(content)
            handle.flush()
            if fsync:
                os.fsync(handle.fileno())
        temp_path.replace(path)
        if mode is not None:
            path.chmod(mode)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def write_json_atomic(
    path: Path,
    payload: Any,
    *,
    indent: int | None = 2,
    ensure_trailing_newline: bool = True,
    encoding: str = "utf-8",
    mode: int | None = None,
    fsync: bool = True,
) -> None:
    """Serialize JSON and write it atomically."""

    rendered = json.dumps(payload, indent=indent)
    if ensure_trailing_newline and not rendered.endswith("\n"):
        rendered += "\n"
    write_text_atomic(
        path,
        rendered,
        encoding=encoding,
        mode=mode,
        fsync=fsync,
    )
