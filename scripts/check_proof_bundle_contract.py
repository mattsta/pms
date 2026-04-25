#!/usr/bin/env python3
"""Validate maintained proof-bundle contract artifacts."""

from __future__ import annotations

import json
import os
from pathlib import Path


def main() -> int:
    base = Path(os.environ["PMS_DATA_DIR"])
    summary_path = base / "proof-bundle.summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    for artifact in summary["artifacts"].values():
        assert Path(artifact).is_file(), artifact

    bundle = json.loads(
        Path(summary["artifacts"]["proof_bundle"]).read_text(encoding="utf-8")
    )
    search = json.loads(
        Path(summary["artifacts"]["proof_search"]).read_text(encoding="utf-8")
    )
    evidence_list = json.loads(
        Path(summary["artifacts"]["evidence_list"]).read_text(encoding="utf-8")
    )

    task_id = summary["task"]["id"]
    test_run_id = summary["test_run_id"]

    assert bundle["task"]["id"] == task_id
    assert bundle["summary"]["evidence_total"] >= 2
    assert bundle["summary"]["test_runs"] >= 1
    assert bundle["summary"]["successful_test_runs"] >= 1
    assert bundle["summary"]["log_bytes_total"] > 0
    assert bundle["summary"]["artifact_bytes_total"] >= 0
    assert any(
        item["evidence"]["evidence_type"] == "artifact" for item in bundle["evidence"]
    )
    assert any(
        item["evidence"]["reference"] == test_run_id for item in bundle["evidence"]
    )
    assert len(bundle["test_runs"]) >= 1
    assert bundle["test_runs"][0]["id"] == test_run_id
    assert bundle["test_runs"][0]["logs"] is not None
    assert bundle["test_runs"][0]["artifacts"] is not None

    assert search["page"]["total_count"] >= 1
    assert search["items"][0]["task"]["id"] == task_id
    assert search["items"][0]["summary"]["successful_test_runs"] >= 1
    assert len(search["items"][0]["evidence"]) >= 2
    assert len(search["items"][0]["test_runs"]) >= 1

    assert evidence_list["task"]["id"] == task_id
    assert any(item["evidence_type"] == "artifact" for item in evidence_list["items"])
    assert any(
        item["evidence_type"] == "test_run" and item["reference"] == test_run_id
        for item in evidence_list["items"]
    )

    print("Proof bundle contract is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
