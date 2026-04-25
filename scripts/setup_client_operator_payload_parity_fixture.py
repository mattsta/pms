#!/usr/bin/env python3
"""Seed a live fixture for maintained client operator payload parity audits."""

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


def _run_task_list(
    project_id: str, *, env: Mapping[str, str] | None = None
) -> dict[str, object]:
    return _run_json_command(
        ["task", "list", "--project", project_id, "--format", "json"],
        env=env,
    )


def _run_task_ready(
    project_id: str, *, env: Mapping[str, str] | None = None
) -> dict[str, object]:
    return _run_json_command(
        ["task", "ready", "--project", project_id, "--format", "json"],
        env=env,
    )


def _create_startable_task(
    project_id: str, *, env: Mapping[str, str] | None = None
) -> str:
    payload = _run_json_command(
        [
            "task",
            "add",
            project_id,
            "Client operator payload parity fallback task",
            "--description",
            "Auto-created startable task for dynamic client parity fixture",
            "--format",
            "json",
        ],
        env=env,
    )
    task = _require_mapping(payload, "task")
    return _require_string(task, "id", "fallback task")


def _resolve_startable_task_id(
    project_id: str, *, env: Mapping[str, str] | None = None
) -> str:
    task_list_payload = _run_task_list(project_id, env=env)
    items = task_list_payload.get("items")
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("status") != "todo":
                continue
            value = item.get("id")
            if isinstance(value, str) and value:
                return value

    ready_payload = _run_task_ready(project_id, env=env)
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

    return _create_startable_task(project_id, env=env)


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


def create_fixture(
    output_env: Path, *, env: Mapping[str, str] | None = None
) -> dict[str, str]:
    quickstart = _run_json_command(
        ["quickstart", "--defaults", "--format", "json"],
        env=env,
    )
    artifacts = _require_mapping(quickstart, "artifacts_created")
    project = _require_mapping(artifacts, "project")
    project_id = _require_string(project, "id", "project")
    project_name = _require_string(project, "name", "project")

    tasks = artifacts.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise SystemExit("quickstart payload missing seeded tasks")
    first_task = tasks[0]
    if not isinstance(first_task, dict):
        raise SystemExit("first quickstart task entry was not an object")
    first_task_id = _require_string(first_task, "id", "first task")
    startable_task_id = _resolve_startable_task_id(project_id, env=env)

    org_payload = _run_json_command(
        ["org", "create", "Client Operator Payload Parity Org", "--format", "json"],
        env=env,
    )
    organization = _require_mapping(org_payload, "organization")
    org_id = _require_string(organization, "id", "organization")

    portfolio_payload = _run_json_command(
        [
            "portfolio",
            "create",
            "Client Operator Payload Parity Portfolio",
            "--org",
            org_id,
            "--format",
            "json",
        ],
        env=env,
    )
    portfolio = _require_mapping(portfolio_payload, "portfolio")
    portfolio_id = _require_string(portfolio, "id", "portfolio")

    program_payload = _run_json_command(
        [
            "program",
            "create",
            "Client Operator Payload Parity Program",
            "--org",
            org_id,
            "--portfolio",
            portfolio_id,
            "--format",
            "json",
        ],
        env=env,
    )
    program = _require_mapping(program_payload, "program")
    program_id = _require_string(program, "id", "program")

    _run_json_command(
        [
            "project",
            "update",
            project_name,
            "--org",
            org_id,
            "--portfolio",
            portfolio_id,
            "--program",
            program_id,
            "--format",
            "json",
        ],
        env=env,
    )
    _run_json_command(
        [
            "task",
            "start",
            startable_task_id,
            "--by",
            "client-operator-payload-parity",
            "--format",
            "json",
        ],
        env=env,
    )
    _run_json_command(
        [
            "task",
            "progress",
            startable_task_id,
            "25",
            "Client operator payload parity fixture progress update",
            "--by",
            "client-operator-payload-parity",
            "--format",
            "json",
        ],
        env=env,
    )

    payload = {
        "PROJECT_ID": project_id,
        "PROJECT_NAME": project_name,
        "ORG_ID": org_id,
        "PORTFOLIO_ID": portfolio_id,
        "PROGRAM_ID": program_id,
        "FIRST_TASK_ID": first_task_id,
        "STARTABLE_TASK_ID": startable_task_id,
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
