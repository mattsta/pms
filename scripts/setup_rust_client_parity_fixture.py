#!/usr/bin/env python3
"""Create a real fixture workspace for Rust client parity smoke tests."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from pms.utils.atomic_files import write_text_atomic


def _run_quickstart() -> dict[str, object]:
    process = subprocess.run(
        ["uv", "run", "pms", "quickstart", "--defaults", "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if process.returncode != 0:
        raise SystemExit(
            process.stderr.strip() or process.stdout.strip() or "quickstart failed"
        )
    try:
        payload = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"quickstart emitted invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit("quickstart payload was not a JSON object")
    return payload


def _required_id(mapping: object, key: str) -> str:
    if not isinstance(mapping, dict):
        raise SystemExit(f"fixture payload missing object for {key}")
    value = mapping.get("id")
    if not isinstance(value, str) or not value:
        raise SystemExit(f"fixture payload missing id for {key}")
    return value


def _required_task_id(tasks: object) -> str:
    if not isinstance(tasks, list) or not tasks:
        raise SystemExit("fixture payload missing seeded tasks")
    first = tasks[0]
    if not isinstance(first, dict):
        raise SystemExit("fixture payload seeded task entry was not an object")
    value = first.get("id")
    if not isinstance(value, str) or not value:
        raise SystemExit("fixture payload missing first task id")
    return value


def _run_task_list(project_id: str) -> dict[str, object]:
    process = subprocess.run(
        [
            "uv",
            "run",
            "pms",
            "task",
            "list",
            "--project",
            project_id,
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if process.returncode != 0:
        raise SystemExit(
            process.stderr.strip() or process.stdout.strip() or "task list failed"
        )
    try:
        payload = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"task list emitted invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit("task list payload was not a JSON object")
    return payload


def _run_task_ready(project_id: str) -> dict[str, object]:
    process = subprocess.run(
        [
            "uv",
            "run",
            "pms",
            "task",
            "ready",
            "--project",
            project_id,
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if process.returncode != 0:
        raise SystemExit(
            process.stderr.strip() or process.stdout.strip() or "task ready failed"
        )
    try:
        payload = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"task ready emitted invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit("task ready payload was not a JSON object")
    return payload


def _create_startable_task(project_id: str) -> str:
    process = subprocess.run(
        [
            "uv",
            "run",
            "pms",
            "task",
            "add",
            project_id,
            "Rust parity smoke task",
            "--description",
            "Auto-created parity fallback task",
            "--priority",
            "medium",
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if process.returncode != 0:
        raise SystemExit(
            process.stderr.strip() or process.stdout.strip() or "task add failed"
        )
    try:
        payload = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"task add emitted invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit("task add payload was not a JSON object")
    task = payload.get("task")
    if not isinstance(task, dict):
        raise SystemExit("task add payload missing task object")
    value = task.get("id")
    if not isinstance(value, str) or not value:
        raise SystemExit("task add payload missing task id")
    return value


def _required_startable_task_id(
    task_list_payload: dict[str, object], project_id: str
) -> str:
    items = task_list_payload.get("items")
    if not isinstance(items, list) or not items:
        raise SystemExit("task list payload missing items")
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("status") != "todo":
            continue
        value = item.get("id")
        if isinstance(value, str) and value:
            return value
    ready_payload = _run_task_ready(project_id)
    ready_items = ready_payload.get("items")
    if isinstance(ready_items, list):
        for item in ready_items:
            if not isinstance(item, dict):
                continue
            value = item.get("id")
            if isinstance(value, str) and value:
                return value
    focus_task = ready_payload.get("focus_task")
    if isinstance(focus_task, dict):
        value = focus_task.get("id")
        if isinstance(value, str) and value:
            return value
    return _create_startable_task(project_id)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-env", required=True, type=Path)
    args = parser.parse_args()

    payload = _run_quickstart()
    artifacts = payload.get("artifacts_created")
    if not isinstance(artifacts, dict):
        raise SystemExit("quickstart payload missing artifacts_created")

    project_id = _required_id(artifacts.get("project"), "project")
    plan_id = _required_id(artifacts.get("plan"), "plan")
    tasks = artifacts.get("tasks")
    first_task_id = _required_task_id(tasks)
    task_list_payload = _run_task_list(project_id)
    startable_task_id = _required_startable_task_id(task_list_payload, project_id)

    output_lines = [
        f"PROJECT_ID={project_id}",
        f"PLAN_ID={plan_id}",
        f"FIRST_TASK_ID={first_task_id}",
        f"STARTABLE_TASK_ID={startable_task_id}",
        f"TASK_COUNT={len(tasks)}",
    ]
    write_text_atomic(args.output_env, "\n".join(output_lines) + "\n")


if __name__ == "__main__":
    main()
