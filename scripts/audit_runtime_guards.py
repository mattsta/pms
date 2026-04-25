"""Audit maintained run_* scripts for required bounded-runtime guards."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIT_RUNNER_PATH = REPO_ROOT / "scripts" / "run_audit_checks.sh"
REQUIRED_BOUNDED_SMOKES: tuple[str, ...] = (
    "scripts/run_dropin_contract_smoke.sh",
    "scripts/run_team_handoff_contract_smoke.sh",
    "scripts/run_incident_response_contract_smoke.sh",
    "scripts/run_user_start_go_observe_contract_smoke.sh",
    "scripts/run_release_readiness_contract_smoke.sh",
    "scripts/run_operational_review_contract_smoke.sh",
    "scripts/run_backlog_triage_contract_smoke.sh",
    "scripts/run_portfolio_steering_contract_smoke.sh",
    "scripts/run_agent_execution_loop_contract_smoke.sh",
    "scripts/run_distributed_auth_recovery_contract_smoke.sh",
    "scripts/run_distributed_multiwriter_contract_smoke.sh",
    "scripts/run_rust_degraded_runtime_recovery_contract_smoke.sh",
    "scripts/run_network_interop_benchmark_contract_smoke.sh",
    "scripts/run_proof_bundle_contract_smoke.sh",
)
REQUIRED_ISOLATED_FLOWS: tuple[str, ...] = (
    "scripts/run_dropin_start_go_extend_grow.sh",
    "scripts/run_team_handoff_flow.sh",
    "scripts/run_incident_response_flow.sh",
    "scripts/run_user_start_go_observe_flow.sh",
    "scripts/run_release_readiness_flow.sh",
    "scripts/run_operational_review_flow.sh",
    "scripts/run_backlog_triage_flow.sh",
    "scripts/run_portfolio_steering_flow.sh",
    "scripts/run_agent_execution_loop_flow.sh",
    "scripts/run_distributed_auth_recovery_flow.sh",
    "scripts/run_distributed_multiwriter_recovery_flow.sh",
    "scripts/run_rust_degraded_runtime_recovery_flow.sh",
    "scripts/run_network_interop_benchmark_bundle.sh",
    "scripts/run_proof_bundle_flow.sh",
)


@dataclass(frozen=True)
class RuntimeGuardIssue:
    script: str
    reason: str


def _uses_runtime_guard_wrapper(text: str) -> bool:
    return "pms_run_bounded_script" in text or "pms_run_contract_flow" in text


def run_audit() -> tuple[RuntimeGuardIssue, ...]:
    issues: list[RuntimeGuardIssue] = []
    audit_runner_text = AUDIT_RUNNER_PATH.read_text()

    for relative_path in REQUIRED_BOUNDED_SMOKES:
        path = REPO_ROOT / relative_path
        if not path.is_file():
            issues.append(RuntimeGuardIssue(relative_path, "missing script"))
            continue

        text = path.read_text()
        if 'source "$ROOT_DIR/scripts/lib/run_helpers.sh"' not in text:
            issues.append(
                RuntimeGuardIssue(relative_path, "missing shared run helper import")
            )
        if not _uses_runtime_guard_wrapper(text):
            issues.append(
                RuntimeGuardIssue(relative_path, "missing bounded runtime wrapper")
            )
        if "CONTRACT_TIMEOUT_SECONDS" not in text:
            issues.append(
                RuntimeGuardIssue(
                    relative_path, "missing explicit contract timeout setting"
                )
            )
        if relative_path not in audit_runner_text:
            issues.append(RuntimeGuardIssue(relative_path, "missing from audit runner"))

    for relative_path in REQUIRED_ISOLATED_FLOWS:
        path = REPO_ROOT / relative_path
        if not path.is_file():
            issues.append(RuntimeGuardIssue(relative_path, "missing script"))
            continue

        text = path.read_text()
        if 'source "$ROOT_DIR/scripts/lib/run_helpers.sh"' not in text:
            issues.append(
                RuntimeGuardIssue(relative_path, "missing shared run helper import")
            )
        if "pms_use_isolated_direct_runtime" not in text:
            issues.append(
                RuntimeGuardIssue(relative_path, "missing isolated runtime guard")
            )

    return tuple(issues)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit maintained bounded-runtime guards."
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON payload")
    parser.add_argument("--check", action="store_true", help="Exit non-zero on issues")
    args = parser.parse_args()

    issues = run_audit()
    if args.json:
        print(
            json.dumps(
                {
                    "checked": len(REQUIRED_BOUNDED_SMOKES)
                    + len(REQUIRED_ISOLATED_FLOWS),
                    "issues": [
                        {"script": issue.script, "reason": issue.reason}
                        for issue in issues
                    ],
                },
                indent=2,
            )
        )
    else:
        print(
            "Runtime guard audit\n"
            f"checked={len(REQUIRED_BOUNDED_SMOKES) + len(REQUIRED_ISOLATED_FLOWS)} "
            f"issues={len(issues)}"
        )
        for issue in issues:
            print(f"- {issue.script}: {issue.reason}")

    if args.check and issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
