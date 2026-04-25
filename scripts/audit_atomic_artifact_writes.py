#!/usr/bin/env python3
"""Audit maintained file writers for shared atomic file-write usage."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TARGET_HELPERS: dict[str, str] = {
    "scripts/write_rust_server_benchmark_report.py": "write_json_atomic",
    "scripts/capture_network_interop_baseline.py": "write_json_atomic",
    "scripts/write_operational_review_summary.py": "write_json_atomic",
    "scripts/write_agent_execution_loop_summary.py": "write_json_atomic",
    "scripts/write_portfolio_steering_summary.py": "write_json_atomic",
    "scripts/write_backlog_triage_summary.py": "write_json_atomic",
    "scripts/capture_cli_api_parity_matrix.py": "write_json_atomic",
    "scripts/generate_api_endpoint_catalog.py": "write_text_atomic",
    "scripts/generate_api_response_contracts.py": "write_text_atomic",
    "scripts/setup_rust_client_parity_fixture.py": "write_text_atomic",
    "scripts/update_loop_config.py": "write_text_atomic",
    "scripts/run_proof_bundle_flow.sh": "write_json_atomic",
    "scripts/run_network_interop_benchmark_bundle.sh": "write_json_atomic",
    "scripts/run_distributed_auth_recovery_flow.sh": "write_json_atomic",
    "scripts/run_distributed_multiwriter_recovery_flow.sh": "write_json_atomic",
    "scripts/run_rust_degraded_runtime_recovery_flow.sh": "write_json_atomic",
    "scripts/run_user_start_go_observe_flow.sh": "write_json_atomic",
    "scripts/run_incident_response_flow.sh": "write_json_atomic",
    "scripts/run_dropin_start_go_extend_grow.sh": "write_json_atomic",
    "scripts/run_release_readiness_flow.sh": "write_json_atomic",
    "scripts/run_team_handoff_flow.sh": "write_json_atomic",
}
FORBIDDEN_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\.write_text\("), "raw .write_text() artifact write"),
    (re.compile(r"\bjson\.dump\("), "raw json.dump() artifact write"),
)


@dataclass(frozen=True)
class AtomicArtifactWriteIssue:
    file: str
    line: int
    reason: str


def _line_number(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def audit_source(
    source: str,
    *,
    path: Path,
    required_helper: str,
) -> tuple[AtomicArtifactWriteIssue, ...]:
    try:
        relative_file = str(path.relative_to(REPO_ROOT))
    except ValueError:
        relative_file = str(path)

    issues: list[AtomicArtifactWriteIssue] = []
    helper_call = re.compile(rf"\b{re.escape(required_helper)}\(")
    if helper_call.search(source) is None:
        issues.append(
            AtomicArtifactWriteIssue(
                file=relative_file,
                line=1,
                reason=f"missing required helper call {required_helper}()",
            )
        )

    for pattern, reason in FORBIDDEN_PATTERNS:
        for match in pattern.finditer(source):
            issues.append(
                AtomicArtifactWriteIssue(
                    file=relative_file,
                    line=_line_number(source, match.start()),
                    reason=reason,
                )
            )
    return tuple(issues)


def run_audit() -> tuple[AtomicArtifactWriteIssue, ...]:
    issues: list[AtomicArtifactWriteIssue] = []
    for relative_path, required_helper in sorted(TARGET_HELPERS.items()):
        path = REPO_ROOT / relative_path
        issues.extend(
            audit_source(
                path.read_text(encoding="utf-8"),
                path=path,
                required_helper=required_helper,
            )
        )
    return tuple(issues)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit maintained file writers for shared atomic file-write usage."
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON payload")
    parser.add_argument("--check", action="store_true", help="Exit non-zero on issues")
    args = parser.parse_args()

    issues = run_audit()
    if args.json:
        print(
            json.dumps(
                {
                    "checked": len(TARGET_HELPERS),
                    "issues": [
                        {
                            "file": issue.file,
                            "line": issue.line,
                            "reason": issue.reason,
                        }
                        for issue in issues
                    ],
                },
                indent=2,
            )
        )
    else:
        print(
            "Atomic artifact write audit\n"
            f"checked={len(TARGET_HELPERS)} issues={len(issues)}"
        )
        for issue in issues:
            print(f"- {issue.file}:{issue.line} {issue.reason}")

    if args.check and issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
