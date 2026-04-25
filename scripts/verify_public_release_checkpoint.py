"""Verify the live PMS workspace is in a clean public-release checkpoint state."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Any

DEFAULT_RELEASE_PROJECT = "PMS Release Readiness and Public Documentation"


@dataclass(frozen=True)
class ReleaseCheckpointIssue:
    surface: str
    reason: str


def _run_pms_json(args: list[str], *, direct_mode: bool = False) -> dict[str, Any]:
    env = os.environ.copy()
    if direct_mode:
        env["PMS_WRITE_MODE"] = "direct"
        env.pop("PMS_SERVER_BASE_URL", None)
        env.pop("PMS_API_KEY", None)
        env.pop("PMS_API_KEY_PATH", None)

    result = subprocess.run(
        [sys.executable, "-m", "pms", *args],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"command failed: python -m pms {' '.join(args)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return json.loads(result.stdout)


def collect_live_payloads(
    project_name: str = DEFAULT_RELEASE_PROJECT,
) -> dict[str, dict[str, Any]]:
    return {
        "project_task_list": _run_pms_json(
            ["task", "list", "--project", project_name, "--format", "json"],
            direct_mode=True,
        ),
        "start": _run_pms_json(["start", "--format", "json"], direct_mode=True),
        "dashboard": _run_pms_json(["dashboard", "--format", "json"], direct_mode=True),
        "runtime": _run_pms_json(
            ["runtime", "status", "--format", "json"], direct_mode=True
        ),
    }


def audit_payloads(
    payloads: dict[str, dict[str, Any]],
    *,
    project_name: str = DEFAULT_RELEASE_PROJECT,
) -> tuple[ReleaseCheckpointIssue, ...]:
    issues: list[ReleaseCheckpointIssue] = []

    project_task_list = payloads["project_task_list"]
    visible_totals = project_task_list.get("visible_totals", {})
    for field in (
        "todo_tasks",
        "in_progress_tasks",
        "blocked_tasks",
        "in_review_tasks",
    ):
        if visible_totals.get(field, 0) != 0:
            issues.append(
                ReleaseCheckpointIssue(
                    "project_task_list",
                    f"{project_name} still reports non-terminal work via {field}={visible_totals.get(field)}",
                )
            )
    if project_task_list.get("focus_task") is not None:
        issues.append(
            ReleaseCheckpointIssue(
                "project_task_list",
                f"{project_name} still exposes a focus_task instead of a terminal scoped view",
            )
        )

    start_payload = payloads["start"]
    start_focus = start_payload.get("focus_task")
    if (
        isinstance(start_focus, dict)
        and start_focus.get("project_name") == project_name
    ):
        issues.append(
            ReleaseCheckpointIssue(
                "start",
                f"start still surfaces {project_name} as the current focus project",
            )
        )

    dashboard_payload = payloads["dashboard"]
    dashboard_focus = dashboard_payload.get("focus_task")
    if (
        isinstance(dashboard_focus, dict)
        and dashboard_focus.get("project_name") == project_name
    ):
        issues.append(
            ReleaseCheckpointIssue(
                "dashboard",
                f"dashboard still surfaces {project_name} as the current focus project",
            )
        )

    for project in dashboard_payload.get("active_projects", []):
        if project.get("project_name") == project_name:
            issues.append(
                ReleaseCheckpointIssue(
                    "dashboard",
                    f"{project_name} still appears in dashboard active_projects",
                )
            )

    for task_group in ("ready_tasks", "in_progress_tasks"):
        for task in dashboard_payload.get(task_group, []):
            if task.get("project_name") == project_name:
                issues.append(
                    ReleaseCheckpointIssue(
                        "dashboard",
                        f"{project_name} still appears in dashboard {task_group}",
                    )
                )

    for item in dashboard_payload.get("blocked_items", []):
        item_project_name = item.get("project_name")
        if item_project_name is None and isinstance(item.get("project"), dict):
            item_project_name = item["project"].get("name")
        if item_project_name == project_name:
            issues.append(
                ReleaseCheckpointIssue(
                    "dashboard",
                    f"{project_name} still appears in dashboard blocked_items",
                )
            )

    runtime_payload = payloads["runtime"]
    if runtime_payload.get("items"):
        issues.append(
            ReleaseCheckpointIssue(
                "runtime",
                "managed local servers are still registered in runtime status",
            )
        )
    if runtime_payload.get("unmanaged_local_processes"):
        issues.append(
            ReleaseCheckpointIssue(
                "runtime",
                "unmanaged local PMS server processes are still running",
            )
        )

    return tuple(issues)


def run_audit(
    project_name: str = DEFAULT_RELEASE_PROJECT,
) -> tuple[ReleaseCheckpointIssue, ...]:
    return audit_payloads(
        collect_live_payloads(project_name), project_name=project_name
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify the live PMS workspace is in a clean public-release checkpoint state."
    )
    parser.add_argument(
        "--project-name",
        default=DEFAULT_RELEASE_PROJECT,
        help="Release-readiness project name to verify.",
    )
    parser.add_argument("--check", action="store_true", help="Exit non-zero on issues.")
    parser.add_argument("--json", action="store_true", help="Emit JSON payload.")
    args = parser.parse_args()

    payloads = collect_live_payloads(args.project_name)
    issues = audit_payloads(payloads, project_name=args.project_name)

    if args.json:
        print(
            json.dumps(
                {
                    "project_name": args.project_name,
                    "issues": [
                        {"surface": issue.surface, "reason": issue.reason}
                        for issue in issues
                    ],
                    "summary": {
                        "release_project_terminal": payloads["project_task_list"].get(
                            "focus_task"
                        )
                        is None,
                        "start_focus_task": payloads["start"].get("focus_task"),
                        "dashboard_focus_task": payloads["dashboard"].get("focus_task"),
                        "managed_runtime_items": len(
                            payloads["runtime"].get("items", [])
                        ),
                        "unmanaged_runtime_processes": len(
                            payloads["runtime"].get("unmanaged_local_processes", [])
                        ),
                    },
                },
                indent=2,
            )
        )
    else:
        print(
            "Public release checkpoint audit\n"
            f"project={args.project_name}\n"
            f"issues={len(issues)}"
        )
        if issues:
            for issue in issues:
                print(f"- {issue.surface}: {issue.reason}")
        else:
            print("- project task list is terminal")
            print("- start does not focus the release project")
            print("- dashboard does not surface the release project as active work")
            print("- runtime is clean")

    if args.check and issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
