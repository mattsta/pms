#!/usr/bin/env python3
"""Capture a reusable baseline artifact for PMS network/runtime/client interop."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib import error, request

from pms.utils.atomic_files import write_json_atomic

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TIMEOUT_SECONDS = 20


@dataclass
class CommandResult:
    name: str
    argv: list[str]
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool


def utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def load_json(text: str) -> Any | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def run_command(
    name: str,
    argv: list[str],
    *,
    env: dict[str, str] | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> CommandResult:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    try:
        completed = subprocess.run(
            argv,
            cwd=ROOT,
            env=merged_env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return CommandResult(
            name=name,
            argv=argv,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            timed_out=False,
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            name=name,
            argv=argv,
            returncode=None,
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
            timed_out=True,
        )


def write_result(output_dir: Path, result: CommandResult) -> Any | None:
    payload = asdict(result)
    parsed = load_json(result.stdout)
    if parsed is not None:
        payload["parsed_stdout"] = parsed
    path = output_dir / f"{result.name}.json"
    write_json_atomic(path, payload, encoding="utf-8")
    return parsed


def probe_http(url: str, timeout: int = 5) -> dict[str, Any]:
    target = url.rstrip("/") + "/api/v1/health"
    try:
        with request.urlopen(target, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            return {
                "url": target,
                "reachable": True,
                "status": response.status,
                "body": body,
            }
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {
            "url": target,
            "reachable": False,
            "status": exc.code,
            "body": body,
            "error": str(exc),
        }
    except Exception as exc:  # pragma: no cover - defensive error capture
        return {
            "url": target,
            "reachable": False,
            "status": None,
            "body": "",
            "error": str(exc),
        }


def build_output_dir(path_arg: str | None) -> Path:
    if path_arg:
        out = Path(path_arg).expanduser().resolve()
    else:
        out = ROOT / "artifacts" / "network_interop_baseline" / utc_stamp()
    out.mkdir(parents=True, exist_ok=True)
    return out


def rust_env() -> dict[str, str]:
    env: dict[str, str] = {}
    key_path = ROOT / ".pms-admin-key"
    if key_path.exists():
        env["PMS_API_KEY"] = key_path.read_text(encoding="utf-8").strip()
    return env


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        help="Directory to write baseline artifacts into "
        "(default: artifacts/network_interop_baseline/<timestamp>)",
    )
    args = parser.parse_args()

    output_dir = build_output_dir(args.output_dir)
    summary: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "output_dir": str(output_dir),
        "issues": [],
        "artifacts": {},
    }

    commands: list[tuple[str, list[str], dict[str, str] | None]] = [
        (
            "config_show",
            ["uv", "run", "pms", "config", "show", "--format", "json"],
            None,
        ),
        (
            "runtime_status",
            ["uv", "run", "pms", "runtime", "status", "--format", "json"],
            None,
        ),
        ("start_json", ["uv", "run", "pms", "start", "--format", "json"], None),
        ("dashboard_json", ["uv", "run", "pms", "dashboard", "--format", "json"], None),
        (
            "plan_list_json",
            ["uv", "run", "pms", "plan", "list", "--format", "json"],
            None,
        ),
    ]

    parsed_outputs: dict[str, Any | None] = {}
    for name, argv, env in commands:
        result = run_command(name, argv, env=env)
        parsed_outputs[name] = write_result(output_dir, result)
        summary["artifacts"][name] = f"{name}.json"
        if result.timed_out:
            summary["issues"].append(f"{name} timed out")
        elif result.returncode not in (0, None):
            summary["issues"].append(f"{name} exited with code {result.returncode}")

    config_json = parsed_outputs.get("config_show") or {}
    runtime_json = parsed_outputs.get("runtime_status") or {}
    start_json = parsed_outputs.get("start_json") or {}

    configured_server_url = None
    runtime_status_server_url = None
    server_url = None
    if isinstance(config_json, dict):
        configured_server_url = (
            config_json.get("runtime", {}).get("server_base_url")
            or config_json.get("runtime", {}).get("server", {}).get("base_url")
            or config_json.get("settings", {}).get("server_base_url")
            or config_json.get("server_base_url")
        )
    if isinstance(runtime_json, dict):
        items = runtime_json.get("items") or []
        if items:
            runtime_status_server_url = items[0].get("server_url")
    if not server_url:
        server_url = configured_server_url or runtime_status_server_url
    if not server_url and isinstance(start_json, dict):
        server_url = start_json.get("runtime", {}).get("coordination", {}).get(
            "server_base_url"
        ) or start_json.get("runtime", {}).get("server_base_url")

    if (
        configured_server_url
        and runtime_status_server_url
        and configured_server_url != runtime_status_server_url
    ):
        summary["issues"].append(
            "Configured server URL and managed runtime status disagree: "
            f"{configured_server_url} vs {runtime_status_server_url}"
        )

    if server_url:
        http_probe = probe_http(server_url)
        write_json_atomic(
            output_dir / "server_probe.json", http_probe, encoding="utf-8"
        )
        summary["artifacts"]["server_probe"] = "server_probe.json"
        summary["server_url"] = server_url
        if not http_probe.get("reachable"):
            summary["issues"].append(
                f"Configured server is not healthy at {server_url}: {http_probe.get('error') or http_probe.get('status')}"
            )
    else:
        summary["issues"].append(
            "No server_base_url was discoverable from config/start output"
        )

    coordination_state = None
    if isinstance(runtime_json, dict):
        coordination_state = (
            runtime_json.get("runtime", {}).get("coordination", {}).get("state")
        )
    if coordination_state and coordination_state != "server_coordinated":
        summary["issues"].append(f"Runtime coordination is {coordination_state}")

    rust_client = ROOT / ".bin" / "pms-client"
    if rust_client.exists() and server_url:
        rust_result = run_command(
            "rust_start_json",
            [str(rust_client), "--server", server_url, "start", "--format", "json"],
            env=rust_env(),
        )
        parsed_outputs["rust_start_json"] = write_result(output_dir, rust_result)
        summary["artifacts"]["rust_start_json"] = "rust_start_json.json"
        if rust_result.timed_out:
            summary["issues"].append("Rust client start probe timed out")
        elif rust_result.returncode not in (0, None):
            summary["issues"].append(
                f"Rust client start probe failed with code {rust_result.returncode}"
            )
    else:
        summary["issues"].append(
            "Rust client probe skipped because binary or server URL was unavailable"
        )

    summary_path = output_dir / "summary.json"
    write_json_atomic(summary_path, summary, encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
