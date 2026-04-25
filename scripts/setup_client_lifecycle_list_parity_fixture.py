#!/usr/bin/env python3
"""Seed a live fixture for maintained client lifecycle list parity audits."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from collections.abc import Mapping
from pathlib import Path

from pms.utils.atomic_files import write_text_atomic


def _run_json_command(
    args: list[str], *, env: Mapping[str, str] | None = None
) -> dict[str, object]:
    process = subprocess.run(
        ["uv", "run", "pms", *args],
        env=dict(env) if env is not None else dict(os.environ),
        capture_output=True,
        text=True,
        check=False,
    )
    if process.returncode != 0:
        raise SystemExit(
            process.stderr.strip()
            or process.stdout.strip()
            or f"command failed: {args}"
        )
    try:
        payload = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"command emitted invalid JSON for {args}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"command did not emit a JSON object for {args}")
    return payload


def _require_mapping(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise SystemExit(f"payload missing object for {key}")
    return value


def _require_string(mapping: dict[str, object], key: str, label: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise SystemExit(f"payload missing string {key} for {label}")
    return value


def _create_task(
    project_id: str,
    title: str,
    *,
    description: str,
    env: Mapping[str, str] | None = None,
) -> str:
    payload = _run_json_command(
        [
            "task",
            "add",
            project_id,
            title,
            "--description",
            description,
            "--format",
            "json",
        ],
        env=env,
    )
    task = _require_mapping(payload, "task")
    return _require_string(task, "id", title)


def _create_plan(
    name: str,
    *,
    project_id: str,
    task_id: str,
    env: Mapping[str, str] | None = None,
) -> str:
    payload = _run_json_command(
        [
            "plan",
            "create",
            name,
            "--project",
            project_id,
            "--task-id",
            task_id,
            "--content",
            "{}",
            "--output-format",
            "json",
        ],
        env=env,
    )
    plan = _require_mapping(payload, "plan")
    return _require_string(plan, "id", name)


def create_fixture(
    output_env: Path, *, env: Mapping[str, str] | None = None
) -> dict[str, str]:
    project_payload = _run_json_command(
        [
            "project",
            "create",
            "Client Lifecycle List Payload Parity Project",
            "--description",
            "Live fixture for maintained Python/Rust task-list and plan-list parity audits.",
            "--format",
            "json",
        ],
        env=env,
    )
    project = _require_mapping(project_payload, "project")
    project_id = _require_string(project, "id", "project")
    project_name = _require_string(project, "name", "project")

    todo_task_id = _create_task(
        project_id,
        "Lifecycle Todo Task",
        description="Fixture todo task for project-scoped list parity.",
        env=env,
    )
    active_task_id = _create_task(
        project_id,
        "Lifecycle Active Task",
        description="Fixture active task for status-filtered task-list parity.",
        env=env,
    )
    completed_task_id = _create_task(
        project_id,
        "Lifecycle Completed Task",
        description="Fixture completed task for pagination parity.",
        env=env,
    )

    _run_json_command(
        [
            "task",
            "start",
            active_task_id,
            "--by",
            "client-lifecycle-parity",
            "--format",
            "json",
        ],
        env=env,
    )
    _run_json_command(
        [
            "task",
            "progress",
            active_task_id,
            "25",
            "Client lifecycle parity fixture progress update",
            "--by",
            "client-lifecycle-parity",
            "--format",
            "json",
        ],
        env=env,
    )
    _run_json_command(
        [
            "task",
            "start",
            completed_task_id,
            "--by",
            "client-lifecycle-parity",
            "--format",
            "json",
        ],
        env=env,
    )
    _run_json_command(
        [
            "task",
            "complete",
            completed_task_id,
            "--by",
            "client-lifecycle-parity",
            "--format",
            "json",
        ],
        env=env,
    )

    active_plan_id = _create_plan(
        "Lifecycle Active Plan",
        project_id=project_id,
        task_id=active_task_id,
        env=env,
    )
    todo_plan_id = _create_plan(
        "Lifecycle Todo Plan",
        project_id=project_id,
        task_id=todo_task_id,
        env=env,
    )

    payload = {
        "PROJECT_ID": project_id,
        "PROJECT_NAME": project_name,
        "TODO_TASK_ID": todo_task_id,
        "ACTIVE_TASK_ID": active_task_id,
        "COMPLETED_TASK_ID": completed_task_id,
        "ACTIVE_PLAN_ID": active_plan_id,
        "TODO_PLAN_ID": todo_plan_id,
    }
    env_text = "\n".join(f"{key}={value}" for key, value in payload.items()) + "\n"
    write_text_atomic(output_env, env_text)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-env", required=True, type=Path)
    args = parser.parse_args()
    create_fixture(args.output_env)


if __name__ == "__main__":
    main()
