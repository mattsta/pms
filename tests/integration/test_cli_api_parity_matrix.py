"""Coverage for the maintained CLI/API parity matrix capture helper."""

import json

from scripts.audit_cli_api_contract_parity import run_audit as run_cli_api_parity_audit
from scripts.capture_cli_api_parity_matrix import (
    compare_surface,
    summarize_contract_gaps,
)


def test_compare_surface_highlights_cli_vs_api_contract_gaps() -> None:
    cli_payload = {
        "id": "x",
        "links": {"self": "cmd"},
        "next_steps": ["cmd"],
        "focus_task": {"id": "t"},
        "terminal_reason": None,
    }
    api_payload = {
        "id": "x",
        "status": "active",
    }

    result = compare_surface(
        surface_name="plan_detail",
        cli_payload=cli_payload,
        api_payload=api_payload,
        cli_command="uv run pms plan show x --format json",
        api_path="/api/v1/plans/x",
    )

    assert result["surface"] == "plan_detail"
    assert result["cli_only_keys"] == [
        "focus_task",
        "links",
        "next_steps",
        "terminal_reason",
    ]
    assert result["api_only_keys"] == ["status"]
    assert result["contracts"]["cli_has_links"] is True
    assert result["contracts"]["api_has_links"] is False
    assert result["contracts"]["cli_has_next_steps"] is True
    assert result["contracts"]["api_has_next_steps"] is False


def test_summarize_contract_gaps_reports_missing_focus_and_terminal_reason() -> None:
    matrix = {
        "surfaces": [
            {
                "surface": "plan_detail",
                "contracts": {
                    "api_has_links": True,
                    "api_has_next_steps": True,
                    "cli_has_focus_task": True,
                    "api_has_focus_task": False,
                    "cli_has_terminal_reason": True,
                    "api_has_terminal_reason": False,
                },
            },
            {
                "surface": "task_detail",
                "contracts": {
                    "api_has_links": True,
                    "api_has_next_steps": False,
                    "cli_has_focus_task": False,
                    "api_has_focus_task": False,
                    "cli_has_terminal_reason": False,
                    "api_has_terminal_reason": False,
                },
            },
        ]
    }

    summary = summarize_contract_gaps(matrix)

    assert summary["surfaces_missing_api_links"] == []
    assert summary["surfaces_missing_api_next_steps"] == ["task_detail"]
    assert summary["surfaces_missing_api_focus_task"] == ["plan_detail"]
    assert summary["surfaces_missing_api_terminal_reason"] == ["plan_detail"]


def test_cli_api_parity_audit_reads_artifact_and_reports_issues(tmp_path) -> None:
    artifact = tmp_path / "latest.json"
    artifact.write_text(
        json.dumps(
            {
                "surfaces": [
                    {
                        "surface": "task_detail",
                        "contracts": {
                            "api_has_links": False,
                            "api_has_next_steps": False,
                            "cli_has_focus_task": False,
                            "api_has_focus_task": False,
                            "cli_has_terminal_reason": False,
                            "api_has_terminal_reason": False,
                        },
                    },
                    {
                        "surface": "dashboard",
                        "contracts": {
                            "api_has_links": True,
                            "api_has_next_steps": True,
                            "cli_has_focus_task": True,
                            "api_has_focus_task": False,
                            "cli_has_terminal_reason": False,
                            "api_has_terminal_reason": False,
                        },
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    issues = run_cli_api_parity_audit(artifact_path=artifact)

    assert {issue.contract for issue in issues} == {
        "api_has_links",
        "api_has_next_steps",
    }
