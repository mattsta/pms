"""Audit real-world scenario packages for doc/script/smoke completeness."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIT_RUNNER_PATH = REPO_ROOT / "scripts" / "run_audit_checks.sh"
CONTINUATION_SNIPPETS: tuple[str, ...] = (
    "Recommended usage pattern",
    "Next steps",
    "what comes next",
    "continue",
    "follow-up",
)


@dataclass(frozen=True)
class ScenarioPackageSpec:
    """Expected assets and documentation for a real-world scenario package."""

    name: str
    doc_path: str
    flow_script: str
    contract_smoke: str
    summary_artifact: str


@dataclass(frozen=True)
class ScenarioAuditIssue:
    """Single scenario package issue."""

    scenario: str
    reason: str


SCENARIOS: tuple[ScenarioPackageSpec, ...] = (
    ScenarioPackageSpec(
        name="dropin",
        doc_path="examples/real_world/README.md",
        flow_script="scripts/run_dropin_start_go_extend_grow.sh",
        contract_smoke="scripts/run_dropin_contract_smoke.sh",
        summary_artifact="dropin-grow.summary.json",
    ),
    ScenarioPackageSpec(
        name="team_handoff",
        doc_path="examples/real_world/README.md",
        flow_script="scripts/run_team_handoff_flow.sh",
        contract_smoke="scripts/run_team_handoff_contract_smoke.sh",
        summary_artifact="team-handoff.summary.json",
    ),
    ScenarioPackageSpec(
        name="incident_response",
        doc_path="examples/real_world/README.md",
        flow_script="scripts/run_incident_response_flow.sh",
        contract_smoke="scripts/run_incident_response_contract_smoke.sh",
        summary_artifact="incident.summary.json",
    ),
    ScenarioPackageSpec(
        name="user_start_go_observe",
        doc_path="examples/real_world/README.md",
        flow_script="scripts/run_user_start_go_observe_flow.sh",
        contract_smoke="scripts/run_user_start_go_observe_contract_smoke.sh",
        summary_artifact="user-start.summary.json",
    ),
    ScenarioPackageSpec(
        name="release_readiness",
        doc_path="examples/real_world/README.md",
        flow_script="scripts/run_release_readiness_flow.sh",
        contract_smoke="scripts/run_release_readiness_contract_smoke.sh",
        summary_artifact="release-readiness.summary.json",
    ),
    ScenarioPackageSpec(
        name="operational_review",
        doc_path="examples/real_world/README.md",
        flow_script="scripts/run_operational_review_flow.sh",
        contract_smoke="scripts/run_operational_review_contract_smoke.sh",
        summary_artifact="operational-review.summary.json",
    ),
    ScenarioPackageSpec(
        name="backlog_triage",
        doc_path="examples/real_world/README.md",
        flow_script="scripts/run_backlog_triage_flow.sh",
        contract_smoke="scripts/run_backlog_triage_contract_smoke.sh",
        summary_artifact="backlog-triage.summary.json",
    ),
    ScenarioPackageSpec(
        name="portfolio_steering",
        doc_path="examples/real_world/README.md",
        flow_script="scripts/run_portfolio_steering_flow.sh",
        contract_smoke="scripts/run_portfolio_steering_contract_smoke.sh",
        summary_artifact="portfolio-steering.summary.json",
    ),
    ScenarioPackageSpec(
        name="agent_execution_loop",
        doc_path="examples/real_world/README.md",
        flow_script="scripts/run_agent_execution_loop_flow.sh",
        contract_smoke="scripts/run_agent_execution_loop_contract_smoke.sh",
        summary_artifact="agent-loop.summary.json",
    ),
)


def _file_contains(path: Path, snippet: str) -> bool:
    return snippet in path.read_text()


def _has_continuation_language(doc_text: str) -> bool:
    lowered = doc_text.lower()
    return any(snippet.lower() in lowered for snippet in CONTINUATION_SNIPPETS)


def run_audit() -> tuple[ScenarioAuditIssue, ...]:
    issues: list[ScenarioAuditIssue] = []
    audit_runner_text = AUDIT_RUNNER_PATH.read_text()

    for scenario in SCENARIOS:
        doc_path = REPO_ROOT / scenario.doc_path
        flow_path = REPO_ROOT / scenario.flow_script
        smoke_path = REPO_ROOT / scenario.contract_smoke

        if not doc_path.is_file():
            issues.append(
                ScenarioAuditIssue(scenario.name, f"missing doc {scenario.doc_path}")
            )
            continue
        if not flow_path.is_file():
            issues.append(
                ScenarioAuditIssue(
                    scenario.name, f"missing flow script {scenario.flow_script}"
                )
            )
        if not smoke_path.is_file():
            issues.append(
                ScenarioAuditIssue(
                    scenario.name, f"missing contract smoke {scenario.contract_smoke}"
                )
            )

        doc_text = doc_path.read_text()
        required_doc_snippets = (
            f"./{scenario.flow_script}",
            f"./{scenario.contract_smoke}",
            "PMS_DATA_DIR",
            scenario.summary_artifact,
        )
        for snippet in required_doc_snippets:
            if snippet not in doc_text:
                issues.append(
                    ScenarioAuditIssue(
                        scenario.name,
                        f"doc missing snippet: {snippet}",
                    )
                )

        if not _has_continuation_language(doc_text):
            issues.append(
                ScenarioAuditIssue(scenario.name, "doc missing continuation language")
            )

        if scenario.contract_smoke not in audit_runner_text:
            issues.append(
                ScenarioAuditIssue(
                    scenario.name,
                    f"audit runner missing {scenario.contract_smoke}",
                )
            )

    return tuple(issues)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit scenario package completeness.")
    parser.add_argument("--json", action="store_true", help="Emit JSON payload")
    parser.add_argument("--check", action="store_true", help="Exit non-zero on issues")
    args = parser.parse_args()

    issues = run_audit()
    if args.json:
        payload = {
            "checked": len(SCENARIOS),
            "issues": [
                {"scenario": issue.scenario, "reason": issue.reason} for issue in issues
            ],
        }
        print(json.dumps(payload, indent=2))
    else:
        print(f"Scenario package audit\nchecked={len(SCENARIOS)} issues={len(issues)}")
        for issue in issues:
            print(f"- {issue.scenario}: {issue.reason}")

    if args.check and issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
