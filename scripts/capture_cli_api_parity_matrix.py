"""Capture a maintained parity matrix between CLI and HTTP API operator surfaces."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from pms.utils.atomic_files import write_json_atomic

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "cli_api_parity"


@dataclass(frozen=True)
class SurfaceSpec:
    """One CLI/API comparison target."""

    name: str
    cli_args: tuple[str, ...]
    api_path_template: str


SURFACES: tuple[SurfaceSpec, ...] = (
    SurfaceSpec(
        name="dashboard",
        cli_args=("dashboard", "--format", "json"),
        api_path_template="/api/v1/observability/overview",
    ),
    SurfaceSpec(
        name="project_operator_overview",
        cli_args=("project", "show", "{project_id}", "--format", "json"),
        api_path_template="/api/v1/projects/{project_id}/operator-overview",
    ),
    SurfaceSpec(
        name="plan_detail",
        cli_args=("plan", "show", "{plan_id}", "--format", "json"),
        api_path_template="/api/v1/plans/{plan_id}",
    ),
    SurfaceSpec(
        name="task_detail",
        cli_args=("task", "show", "{task_id}", "--format", "json"),
        api_path_template="/api/v1/tasks/{task_id}",
    ),
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _load_api_key() -> str:
    env_key = os.environ.get("PMS_API_KEY", "").strip()
    if env_key:
        return env_key

    candidate_paths = [
        os.environ.get("PMS_API_KEY_PATH", "").strip(),
        str(REPO_ROOT / ".pms-admin-key"),
    ]
    for candidate in candidate_paths:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    raise RuntimeError("No PMS API key available for parity capture.")


def _cli_prefix() -> list[str]:
    raw = (
        os.environ.get("PMS_INVOKE_ARGV0")
        or os.environ.get("PMS_CLI_ARGV0")
        or os.environ.get("PMS_ARGV0")
        or "uv run pms"
    )
    return shlex.split(raw)


def _run_cli_json(
    args: tuple[str, ...], substitutions: dict[str, str]
) -> dict[str, Any]:
    command = [part.format(**substitutions) for part in args]
    completed = subprocess.run(
        [*_cli_prefix(), *command],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def _fetch_api_json(
    path_template: str,
    substitutions: dict[str, str],
    *,
    server_url: str,
    api_key: str,
) -> dict[str, Any]:
    path = path_template.format(**substitutions)
    response = httpx.get(
        f"{server_url.rstrip('/')}{path}",
        headers={"X-API-Key": api_key},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def compare_surface(
    *,
    surface_name: str,
    cli_payload: dict[str, Any],
    api_payload: dict[str, Any],
    cli_command: str,
    api_path: str,
) -> dict[str, Any]:
    """Build a machine-readable parity summary for one surface."""
    cli_keys = sorted(cli_payload.keys())
    api_keys = sorted(api_payload.keys())
    cli_key_set = set(cli_keys)
    api_key_set = set(api_keys)

    common_keys = sorted(cli_key_set & api_key_set)
    cli_only_keys = sorted(cli_key_set - api_key_set)
    api_only_keys = sorted(api_key_set - cli_key_set)

    return {
        "surface": surface_name,
        "cli_command": cli_command,
        "api_path": api_path,
        "cli_keys": cli_keys,
        "api_keys": api_keys,
        "common_keys": common_keys,
        "cli_only_keys": cli_only_keys,
        "api_only_keys": api_only_keys,
        "contracts": {
            "cli_has_links": "links" in cli_payload,
            "api_has_links": "links" in api_payload,
            "cli_has_next_steps": "next_steps" in cli_payload,
            "api_has_next_steps": "next_steps" in api_payload,
            "cli_has_focus_task": "focus_task" in cli_payload,
            "api_has_focus_task": "focus_task" in api_payload,
            "cli_has_terminal_reason": "terminal_reason" in cli_payload,
            "api_has_terminal_reason": "terminal_reason" in api_payload,
        },
    }


def summarize_contract_gaps(matrix: dict[str, Any]) -> dict[str, list[str]]:
    """Summarize missing core contracts from a captured matrix payload."""
    surfaces = matrix.get("surfaces", [])
    missing_api_links = [
        item["surface"] for item in surfaces if not item["contracts"]["api_has_links"]
    ]
    missing_api_next_steps = [
        item["surface"]
        for item in surfaces
        if not item["contracts"]["api_has_next_steps"]
    ]
    missing_api_focus_task = [
        item["surface"]
        for item in surfaces
        if item["contracts"]["cli_has_focus_task"]
        and not item["contracts"]["api_has_focus_task"]
    ]
    missing_api_terminal_reason = [
        item["surface"]
        for item in surfaces
        if item["contracts"]["cli_has_terminal_reason"]
        and not item["contracts"]["api_has_terminal_reason"]
    ]
    return {
        "surfaces_missing_api_links": missing_api_links,
        "surfaces_missing_api_next_steps": missing_api_next_steps,
        "surfaces_missing_api_focus_task": missing_api_focus_task,
        "surfaces_missing_api_terminal_reason": missing_api_terminal_reason,
    }


def capture_matrix(
    *,
    project_id: str,
    plan_id: str,
    task_id: str,
    server_url: str,
) -> dict[str, Any]:
    """Capture parity data for the maintained core surfaces."""
    api_key = _load_api_key()
    substitutions = {
        "project_id": project_id,
        "plan_id": plan_id,
        "task_id": task_id,
    }
    surfaces: list[dict[str, Any]] = []
    for spec in SURFACES:
        cli_payload = _run_cli_json(spec.cli_args, substitutions)
        api_payload = _fetch_api_json(
            spec.api_path_template,
            substitutions,
            server_url=server_url,
            api_key=api_key,
        )
        cli_command = " ".join(
            [*_cli_prefix(), *[part.format(**substitutions) for part in spec.cli_args]]
        )
        api_path = spec.api_path_template.format(**substitutions)
        surfaces.append(
            compare_surface(
                surface_name=spec.name,
                cli_payload=cli_payload,
                api_payload=api_payload,
                cli_command=cli_command,
                api_path=api_path,
            )
        )

    return {
        "generated_at": _now_iso(),
        "cli_prefix": " ".join(_cli_prefix()),
        "server_url": server_url,
        "surfaces": surfaces,
        "summary": {
            "surface_count": len(surfaces),
            **summarize_contract_gaps({"surfaces": surfaces}),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture a CLI/API parity matrix for maintained operator surfaces."
    )
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--plan-id", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument(
        "--server-url",
        default=os.environ.get("PMS_SERVER_BASE_URL", "http://127.0.0.1:27541"),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    payload = capture_matrix(
        project_id=args.project_id,
        plan_id=args.plan_id,
        task_id=args.task_id,
        server_url=args.server_url,
    )

    output_path = args.output
    if output_path is None:
        DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = DEFAULT_OUTPUT_DIR / "latest.json"
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(output_path, payload, encoding="utf-8")
    print(str(output_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
