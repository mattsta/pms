#!/usr/bin/env python3
"""Validate the distributed multiwriter summary artifact."""

from __future__ import annotations

import json
import os
from pathlib import Path


def main() -> int:
    base = Path(os.environ["PMS_DATA_DIR"])
    summary = json.loads(
        (base / "distributed-multiwriter.summary.json").read_text(encoding="utf-8")
    )

    checkout = summary["checkout"]
    assert checkout["api_conflict_status"] == "409"
    assert "checked out by py-agent" in (checkout["api_conflict_detail"] or "")
    assert checkout["rust_conflict_mentions_checkout_status"] is True
    assert checkout["rust_conflict_mentions_force_release"] is True
    assert checkout["rust_conflict_mentions_task_show"] is True
    assert checkout["rust_success_checked_out"] is True
    assert checkout["rust_status_count"] == 1
    assert checkout["force_release_status"] == "force_released"
    assert checkout["python_recheckout_succeeded"] is True
    actions = set(checkout["log_actions"])
    assert {"checkout", "release", "force_release"} <= actions

    for artifact in summary["artifacts"].values():
        assert Path(artifact).is_file(), artifact

    print("Distributed multiwriter summary is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
