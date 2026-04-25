"""Helpers for writing local secret files safely."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def write_secret_file(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """Write secret content atomically with owner-only permissions.

    The temp file is created alongside the target so the final replace is atomic on
    the same filesystem. The final file is always forced to mode ``0o600``.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path_str = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temp_path_str)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding=encoding) as handle:
            handle.write(content)
        temp_path.replace(path)
        path.chmod(0o600)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
