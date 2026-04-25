"""Audit captured CLI/API parity artifacts for missing operator contracts."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from scripts.capture_cli_api_parity_matrix import DEFAULT_OUTPUT_DIR


@dataclass(frozen=True)
class CliApiContractParityIssue:
    surface: str
    contract: str


REQUIRED_CONTRACTS: dict[str, tuple[str, ...]] = {
    "dashboard": ("api_has_links", "api_has_next_steps"),
    "project_operator_overview": ("api_has_links", "api_has_next_steps"),
    "plan_detail": (
        "api_has_links",
        "api_has_next_steps",
        "api_has_focus_task",
        "api_has_terminal_reason",
    ),
    "task_detail": ("api_has_links", "api_has_next_steps"),
}


def run_audit(
    *, artifact_path: Path | None = None
) -> tuple[CliApiContractParityIssue, ...]:
    """Validate the latest captured parity matrix artifact."""
    path = artifact_path or (DEFAULT_OUTPUT_DIR / "latest.json")
    if not path.exists():
        return (
            CliApiContractParityIssue(
                surface="artifact",
                contract=f"missing parity artifact: {path}",
            ),
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    issues: list[CliApiContractParityIssue] = []
    surfaces = payload.get("surfaces", [])
    for item in surfaces:
        surface = item.get("surface")
        contracts = item.get("contracts", {})
        for required in REQUIRED_CONTRACTS.get(surface, ()):
            if contracts.get(required) is True:
                continue
            issues.append(CliApiContractParityIssue(surface=surface, contract=required))
    return tuple(issues)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit captured CLI/API parity artifacts for missing contracts."
    )
    parser.add_argument("--artifact", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    issues = run_audit(artifact_path=args.artifact)
    if args.json:
        print(
            json.dumps(
                {
                    "checked_artifact": str(
                        args.artifact or (DEFAULT_OUTPUT_DIR / "latest.json")
                    ),
                    "issues": [
                        {"surface": issue.surface, "contract": issue.contract}
                        for issue in issues
                    ],
                },
                indent=2,
            )
        )
    else:
        print(f"CLI/API contract parity audit\nissues={len(issues)}")
        for issue in issues:
            print(f"- {issue.surface}: {issue.contract}")
    if args.check and issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
