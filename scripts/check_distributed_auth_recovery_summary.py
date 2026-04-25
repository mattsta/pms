#!/usr/bin/env python3
"""Validate the distributed auth/bootstrap recovery summary artifact."""

from __future__ import annotations

import json
import os
from pathlib import Path


def main() -> int:
    base = Path(os.environ["PMS_DATA_DIR"])
    summary_path = base / "distributed-auth-recovery.summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    auth = summary["auth"]
    assert auth["limited_key_id"]
    assert auth["before_active"] is True
    assert auth["after_deactivate_active"] is False
    assert auth["after_restore_active"] is True
    assert auth["limited_key_admin_status"] == "403"

    stale = summary["stale_recovery"]
    assert stale["python_recovery_kind"] == "restore_preferred_server"
    assert stale["rust_mentions_config_show"] is True
    assert stale["rust_mentions_runtime_status"] is True
    assert stale["rust_mentions_prefer_server"] is True

    for artifact in summary["artifacts"].values():
        assert Path(artifact).is_file(), artifact

    print("Distributed auth recovery summary is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
