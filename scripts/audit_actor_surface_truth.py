#!/usr/bin/env python3
"""Audit actor summary surfaces for deep activity and transition truth."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


@dataclass(frozen=True)
class ActorSurfaceTruthIssue:
    """Single actor-surface truth issue."""

    surface: str
    reason: str


def _with_temp_env() -> dict[str, str]:
    temp_dir = Path(
        tempfile.mkdtemp(prefix="actor-surface-audit-", dir=REPO_ROOT / ".tmp")
    )
    env = os.environ.copy()
    env["PMS_DATA_DIR"] = str(temp_dir)
    env["PMS_DATABASE_PATH"] = str(temp_dir / "audit.db")
    env["PMS_LOG_DIR"] = str(temp_dir / "logs")
    env["PMS_ENV_FILE"] = str(temp_dir / ".env")
    env["PMS_WRITE_MODE"] = "direct"
    env["PMS_CLI_ARGV0"] = "uv run pms"
    env.pop("PMS_SERVER_BASE_URL", None)
    env.pop("PMS_API_KEY", None)
    env.pop("PMS_API_KEY_PATH", None)
    return env


def _run_cli(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "pms", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _invoke_json(args: list[str], env: dict[str, str]) -> dict[str, object]:
    result = _run_cli(args, env)
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(args)}\n{result.stdout}{result.stderr}"
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Command emitted invalid JSON: {' '.join(args)}\n{result.stdout}"
        ) from exc


def _record(
    issues: list[ActorSurfaceTruthIssue],
    *,
    surface: str,
    condition: bool,
    reason: str,
) -> None:
    if not condition:
        issues.append(ActorSurfaceTruthIssue(surface=surface, reason=reason))


def run_audit() -> tuple[ActorSurfaceTruthIssue, ...]:
    env = _with_temp_env()
    issues: list[ActorSurfaceTruthIssue] = []

    init_result = _run_cli(["init"], env)
    if init_result.returncode != 0:
        return (
            ActorSurfaceTruthIssue(
                surface="setup",
                reason=f"pms init failed\n{init_result.stdout}{init_result.stderr}",
            ),
        )

    alpha = _invoke_json(
        ["actor", "create", "Alpha Actor", "--kind", "human", "--format", "json"],
        env,
    )["actor"]
    alice = _invoke_json(
        ["actor", "create", "Alice Example", "--kind", "human", "--format", "json"],
        env,
    )["actor"]
    security = _invoke_json(
        [
            "actor",
            "create",
            "Security Persona",
            "--kind",
            "persona",
            "--format",
            "json",
        ],
        env,
    )["actor"]

    membership = _run_cli(
        [
            "actor",
            "membership",
            "add",
            str(security["handle"]),
            str(alice["handle"]),
            "--role",
            "representative",
            "--format",
            "json",
        ],
        env,
    )
    if membership.returncode != 0:
        return (
            ActorSurfaceTruthIssue(
                surface="setup",
                reason=membership.stdout + membership.stderr,
            ),
        )

    project = _invoke_json(
        ["project", "create", "Actor Surface Audit Project", "--format", "json"],
        env,
    )["project"]
    task = _invoke_json(
        [
            "task",
            "add",
            str(project["id"]),
            "Actor Surface Audit Task",
            "--assigned-to",
            str(security["handle"]),
            "--format",
            "json",
        ],
        env,
    )["task"]
    start_payload = _invoke_json(
        [
            "task",
            "start",
            str(task["id"]),
            "--by",
            "codex",
            "--format",
            "json",
        ],
        env,
    )
    _record(
        issues,
        surface="setup",
        condition="task" in start_payload,
        reason="task start did not return a task payload",
    )

    label_result = _run_cli(["label", "create", "actor-surface-audit"], env)
    if label_result.returncode != 0:
        return (
            ActorSurfaceTruthIssue(
                surface="setup",
                reason=label_result.stdout + label_result.stderr,
            ),
        )
    comment_result = _run_cli(
        [
            "comment",
            "add",
            "actor",
            str(alice["id"]),
            "Actor surface note",
            "--by",
            "codex",
            "--watch",
        ],
        env,
    )
    if comment_result.returncode != 0:
        return (
            ActorSurfaceTruthIssue(
                surface="setup",
                reason=comment_result.stdout + comment_result.stderr,
            ),
        )
    assign_result = _run_cli(
        [
            "label",
            "assign",
            "actor",
            str(alice["id"]),
            "actor-surface-audit",
            "--by",
            "codex",
        ],
        env,
    )
    if assign_result.returncode != 0:
        return (
            ActorSurfaceTruthIssue(
                surface="setup",
                reason=assign_result.stdout + assign_result.stderr,
            ),
        )

    actor_list = _invoke_json(["actor", "list", "--format", "json"], env)
    list_items = actor_list["items"]
    alice_item = next(item for item in list_items if item["id"] == alice["id"])

    _record(
        issues,
        surface="actor_list",
        condition=list_items[0]["id"] == alice["id"],
        reason=(
            "actor list did not bubble the freshest actor graph item to the top; "
            f"expected {alice['id']} ahead of {alpha['id']}"
        ),
    )
    _record(
        issues,
        surface="actor_list",
        condition=alice_item.get("last_activity_at") is not None,
        reason="actor list omitted bubbled last_activity_at",
    )
    _record(
        issues,
        surface="actor_list",
        condition=alice_item.get("last_transition_at") is not None,
        reason="actor list omitted bubbled last_transition_at",
    )

    actor_show = _invoke_json(
        ["actor", "show", str(alice["handle"]), "--format", "json"],
        env,
    )
    _record(
        issues,
        surface="actor_show",
        condition=actor_show.get("last_activity_at")
        == actor_show["actor"].get("last_activity_at"),
        reason="actor show top-level and nested last_activity_at diverged",
    )
    _record(
        issues,
        surface="actor_show",
        condition=actor_show.get("last_transition_at")
        == actor_show["actor"].get("last_transition_at"),
        reason="actor show top-level and nested last_transition_at diverged",
    )
    _record(
        issues,
        surface="actor_show",
        condition=actor_show["actor"].get("last_activity_at") is not None,
        reason="actor show omitted bubbled last_activity_at",
    )
    _record(
        issues,
        surface="actor_show",
        condition=actor_show["actor"].get("last_transition_at") is not None,
        reason="actor show omitted bubbled last_transition_at",
    )

    return tuple(issues)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero when actor surface truth issues are found.",
    )
    args = parser.parse_args()

    issues = run_audit()
    payload = {
        "checked": 2,
        "issues": len(issues),
        "items": [
            {
                "surface": issue.surface,
                "reason": issue.reason,
            }
            for issue in issues
        ],
    }
    print(json.dumps(payload, indent=2))

    if args.check and issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
