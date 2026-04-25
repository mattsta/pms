#!/usr/bin/env python3
"""Audit dynamic maintained-client parity for task-list and plan-list semantics."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from pms.client.http_client import PMSClient
from scripts.cli_surface_audit_utils import (
    require_success,
    run_cli,
    run_runtime_prefer_server_with_retry,
    with_temp_env,
)
from scripts.setup_client_lifecycle_list_parity_fixture import create_fixture


@dataclass(frozen=True)
class ClientLifecycleListPayloadParityIssue:
    surface: str
    reason: str


def _parse_env_file(path: Path) -> dict[str, str]:
    payload: dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        payload[key.strip()] = value.strip().strip('"').strip("'")
    return payload


def _read_api_key(path: Path) -> str:
    api_key = path.read_text().strip()
    if not api_key:
        raise RuntimeError(f"API key file was empty: {path}")
    return api_key


def _require_items_list(payload: dict[str, Any], *, label: str) -> list[dict[str, Any]]:
    items = payload.get("items")
    if not isinstance(items, list):
        raise RuntimeError(f"{label} payload missing items list")
    normalized: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise RuntimeError(f"{label} payload item was not an object")
        normalized.append(item)
    return normalized


def _normalize_task_list_payload(payload: dict[str, Any]) -> dict[str, Any]:
    items = _require_items_list(payload, label="task list")
    return {
        "items": [
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "status": item.get("status"),
                "parent_id": item.get("parent_id"),
                "complexity_points": item.get("complexity_points"),
            }
            for item in items
        ],
        "total_count": payload.get("total_count", len(items)),
        "limit": payload.get("limit", len(items)),
        "offset": payload.get("offset", 0),
    }


def _normalize_plan_list_payload(payload: dict[str, Any]) -> dict[str, Any]:
    items = _require_items_list(payload, label="plan list")
    return {
        "items": [
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "status": item.get("status"),
                "task_ids": list(item.get("task_ids") or []),
            }
            for item in items
        ],
        "total_count": payload.get("total_count", len(items)),
        "limit": payload.get("limit", len(items)),
        "offset": payload.get("offset", 0),
    }


async def _collect_python_payloads(
    *, server_url: str, api_key: str, project_id: str, active_task_id: str
) -> dict[str, object]:
    async with PMSClient(base_url=server_url, api_key=api_key) as client:
        return {
            "task_project_page": _normalize_task_list_payload(
                await client.list_tasks(project_id=project_id, limit=2, offset=1)
            ),
            "task_status_in_progress": _normalize_task_list_payload(
                await client.list_tasks(
                    project_id=project_id,
                    status="in_progress",
                    limit=10,
                    offset=0,
                )
            ),
            "plan_project_page": _normalize_plan_list_payload(
                await client.list_plans(project_id=project_id, limit=1, offset=1)
            ),
            "plan_task_filter": _normalize_plan_list_payload(
                await client.list_plans(task_id=active_task_id, limit=10, offset=0)
            ),
        }


def _collect_rust_payloads(
    *, server_url: str, api_key: str, project_id: str, active_task_id: str
) -> dict[str, object]:
    process = subprocess.run(
        [
            "cargo",
            "run",
            "--manifest-path",
            str(REPO_ROOT / "client-rust" / "Cargo.toml"),
            "--quiet",
            "--example",
            "lifecycle_list_probe",
            "--",
            "--server",
            server_url,
            "--api-key",
            api_key,
            "--project-id",
            project_id,
            "--active-task-id",
            active_task_id,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if process.returncode != 0:
        raise RuntimeError(process.stderr.strip() or process.stdout.strip())
    try:
        payload = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Rust probe emitted invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Rust probe did not emit a JSON object")
    return payload


def run_audit() -> tuple[ClientLifecycleListPayloadParityIssue, ...]:
    env = with_temp_env("client-lifecycle-list-parity-")
    fixture_env_path = Path(env["PMS_DATA_DIR"]) / "client-lifecycle-list.env"
    issues: list[ClientLifecycleListPayloadParityIssue] = []

    init_result = run_cli(["init"], env, width=160)
    require_success(init_result, args=["init"])
    fixture = create_fixture(fixture_env_path, env=env)

    port, runtime_result = run_runtime_prefer_server_with_retry(
        env,
        width=160,
        install_client=False,
        sign=False,
        output_format="json",
    )
    require_success(
        runtime_result,
        args=[
            "runtime",
            "prefer-server",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--no-install-client",
            "--no-sign",
            "--format",
            "json",
        ],
    )

    runtime_env = _parse_env_file(Path(env["PMS_ENV_FILE"]))
    server_url = runtime_env.get("PMS_SERVER_BASE_URL")
    api_key_path = runtime_env.get("PMS_API_KEY_PATH")
    if not server_url:
        raise RuntimeError("runtime prefer-server did not persist PMS_SERVER_BASE_URL")
    if not api_key_path:
        raise RuntimeError("runtime prefer-server did not persist PMS_API_KEY_PATH")

    api_key = _read_api_key(Path(api_key_path))

    try:
        python_payloads = asyncio.run(
            _collect_python_payloads(
                server_url=server_url,
                api_key=api_key,
                project_id=fixture["PROJECT_ID"],
                active_task_id=fixture["ACTIVE_TASK_ID"],
            )
        )
        rust_payloads = _collect_rust_payloads(
            server_url=server_url,
            api_key=api_key,
            project_id=fixture["PROJECT_ID"],
            active_task_id=fixture["ACTIVE_TASK_ID"],
        )
    finally:
        run_cli(
            ["runtime", "stop-local-server", "--port", str(port)],
            env,
            width=160,
        )

    for surface in (
        "task_project_page",
        "task_status_in_progress",
        "plan_project_page",
        "plan_task_filter",
    ):
        if python_payloads.get(surface) != rust_payloads.get(surface):
            issues.append(
                ClientLifecycleListPayloadParityIssue(
                    surface=surface,
                    reason=(
                        "Python and Rust maintained clients returned different "
                        "normalized lifecycle-list semantics"
                    ),
                )
            )

    return tuple(issues)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Audit dynamic maintained-client parity for task-list and plan-list "
            "payload semantics."
        )
    )
    parser.add_argument("--check", action="store_true", help="Exit non-zero on drift")
    args = parser.parse_args()

    issues = run_audit()
    print(
        "Dynamic client lifecycle list payload parity audit\n"
        f"checked=4 issues={len(issues)}"
    )
    for issue in issues:
        print(f"- {issue.surface}: {issue.reason}")
    if args.check and issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
