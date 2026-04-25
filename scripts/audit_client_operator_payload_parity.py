#!/usr/bin/env python3
"""Audit dynamic maintained-client parity for operator dashboard-family payloads."""

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
from scripts.setup_client_operator_payload_parity_fixture import create_fixture

VOLATILE_KEYS = frozenset({"generated_at"})


@dataclass(frozen=True)
class ClientOperatorPayloadParityIssue:
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


def _normalize_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _normalize_payload(item)
            for key, item in value.items()
            if key not in VOLATILE_KEYS
        }
    if isinstance(value, list):
        return [_normalize_payload(item) for item in value]
    return value


def _read_api_key(path: Path) -> str:
    api_key = path.read_text().strip()
    if not api_key:
        raise RuntimeError(f"API key file was empty: {path}")
    return api_key


async def _collect_python_payloads(
    *, server_url: str, api_key: str, org_id: str, portfolio_id: str
) -> dict[str, object]:
    async with PMSClient(base_url=server_url, api_key=api_key) as client:
        return {
            "dashboard": await client.get_dashboard(),
            "dashboard_html": await client.get_dashboard_html(),
            "organization_dashboard": await client.get_organization_dashboard(
                limit=100,
                offset=0,
            ),
            "portfolio_dashboard": await client.get_portfolio_dashboard(
                org_id=org_id,
                limit=100,
                offset=0,
            ),
            "program_dashboard": await client.get_program_dashboard(
                org_id=org_id,
                portfolio_id=portfolio_id,
                limit=100,
                offset=0,
            ),
        }


def _collect_rust_payloads(
    *, server_url: str, api_key: str, org_id: str, portfolio_id: str
) -> dict[str, object]:
    process = subprocess.run(
        [
            "cargo",
            "run",
            "--manifest-path",
            str(REPO_ROOT / "client-rust" / "Cargo.toml"),
            "--quiet",
            "--example",
            "operator_surface_probe",
            "--",
            "--server",
            server_url,
            "--api-key",
            api_key,
            "--org-id",
            org_id,
            "--portfolio-id",
            portfolio_id,
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


def run_audit() -> tuple[ClientOperatorPayloadParityIssue, ...]:
    env = with_temp_env("client-operator-payload-parity-")
    fixture_env_path = Path(env["PMS_DATA_DIR"]) / "client-operator-payload.env"
    issues: list[ClientOperatorPayloadParityIssue] = []

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
                org_id=fixture["ORG_ID"],
                portfolio_id=fixture["PORTFOLIO_ID"],
            )
        )
        rust_payloads = _collect_rust_payloads(
            server_url=server_url,
            api_key=api_key,
            org_id=fixture["ORG_ID"],
            portfolio_id=fixture["PORTFOLIO_ID"],
        )
    finally:
        run_cli(
            ["runtime", "stop-local-server", "--port", str(port)],
            env,
            width=160,
        )

    for surface in (
        "dashboard",
        "dashboard_html",
        "organization_dashboard",
        "portfolio_dashboard",
        "program_dashboard",
    ):
        python_value = python_payloads.get(surface)
        rust_value = rust_payloads.get(surface)
        if _normalize_payload(python_value) != _normalize_payload(rust_value):
            issues.append(
                ClientOperatorPayloadParityIssue(
                    surface=surface,
                    reason="Python and Rust maintained clients returned different normalized payloads",
                )
            )

    return tuple(issues)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit dynamic maintained-client parity for dashboard-family methods."
    )
    parser.add_argument("--check", action="store_true", help="Exit non-zero on drift")
    args = parser.parse_args()

    issues = run_audit()
    print(
        f"Dynamic client operator payload parity audit\nchecked=5 issues={len(issues)}"
    )
    for issue in issues:
        print(f"- {issue.surface}: {issue.reason}")
    if args.check and issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
