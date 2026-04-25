#!/usr/bin/env python3
"""Capture a PMS stop-audit bundle and optionally emit a Claude Stop hook payload."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _pms_command(root_dir: Path) -> list[str]:
    venv_python = root_dir / ".venv" / "bin" / "python"
    if venv_python.exists():
        return [str(venv_python), "-m", "pms"]
    if shutil.which("uv"):
        return ["uv", "run", "--directory", str(root_dir), "pms"]
    return [sys.executable, "-m", "pms"]


def _bundle_dir(root_dir: Path, explicit_path: str | None) -> Path:
    if explicit_path:
        return Path(explicit_path).expanduser().resolve()
    base_dir = Path.cwd()
    data_dir = Path.cwd() / ".pms-hook-audits"
    if "PMS_DATA_DIR" in os.environ:
        data_dir = Path(os.environ["PMS_DATA_DIR"]) / "hook-audits"
    timestamp = datetime.now(UTC).strftime("stop-%Y%m%dT%H%M%SZ")
    return (
        data_dir if data_dir.is_absolute() else base_dir / data_dir
    ) / f"{timestamp}-{os.getpid()}"


def _project_flags(args: argparse.Namespace) -> list[str]:
    if args.project_id:
        return ["--project-id", args.project_id]
    if args.project:
        return ["--project", args.project]
    return []


def _goal_selector_pairs(args: argparse.Namespace) -> list[tuple[str, str]]:
    selectors: list[tuple[str, str]] = []
    for goal_name in args.goal:
        selectors.append(("--goal", goal_name))
    for goal_id in args.goal_id:
        selectors.append(("--goal-id", goal_id))
    return selectors


def _scope_flags(args: argparse.Namespace) -> list[str]:
    if args.project_id:
        return ["--scope-id", args.project_id]
    if args.project:
        return ["--scope", args.project]
    return []


def _run_command(
    base_command: list[str],
    extra_args: list[str],
    *,
    allow_nonzero: bool = False,
) -> subprocess.CompletedProcess[str]:
    command = [*base_command, *extra_args]
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 and not allow_nonzero:
        joined = shlex.join(command)
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        detail = stderr or stdout or f"exit code {result.returncode}"
        raise RuntimeError(f"{joined} failed: {detail}")
    return result


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_json(path: Path, payload: Any) -> None:
    _write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _capture_json(
    bundle_dir: Path,
    base_command: list[str],
    artifact_name: str,
    command_args: list[str],
    *,
    artifacts: dict[str, str],
    commands: dict[str, str],
) -> None:
    result = _run_command(base_command, command_args)
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        joined = shlex.join([*base_command, *command_args])
        raise RuntimeError(f"{joined} emitted invalid JSON: {exc}") from exc
    artifact_path = bundle_dir / artifact_name
    _write_json(artifact_path, parsed)
    artifacts[artifact_name] = str(artifact_path)
    commands[artifact_name] = shlex.join([*base_command, *command_args])


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Capture a JSON stop-audit bundle from PMS and optionally emit a "
            "Claude Code Stop hook payload via `pms loop guard --hook`."
        )
    )
    project_group = parser.add_mutually_exclusive_group()
    project_group.add_argument(
        "--project", help="Project name for project-scoped captures"
    )
    project_group.add_argument(
        "--project-id", help="Project ID for project-scoped captures"
    )
    parser.add_argument(
        "--goal",
        action="append",
        default=[],
        help="Goal name for goal summary capture (repeatable)",
    )
    parser.add_argument(
        "--goal-id",
        action="append",
        default=[],
        help="Goal ID for goal summary capture / loop guard pinning (repeatable)",
    )
    parser.add_argument(
        "--allow-no-goals",
        action="store_true",
        help="Forward --allow-no-goals to `pms loop guard` when emitting hook payloads",
    )
    parser.add_argument(
        "--output-dir",
        help="Explicit output directory for the bundle (defaults under PMS_DATA_DIR/hook-audits)",
    )
    parser.add_argument(
        "--emit-claude-stop-payload",
        action="store_true",
        help="Emit `pms loop guard --hook` JSON to stdout instead of the bundle manifest",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    root_dir = _repo_root()
    base_command = _pms_command(root_dir)
    bundle_dir = _bundle_dir(root_dir, args.output_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)

    artifacts: dict[str, str] = {}
    commands: dict[str, str] = {}

    _capture_json(
        bundle_dir,
        base_command,
        "start.json",
        ["start", "--format", "json"],
        artifacts=artifacts,
        commands=commands,
    )
    _capture_json(
        bundle_dir,
        base_command,
        "dashboard.json",
        ["dashboard", "--format", "json"],
        artifacts=artifacts,
        commands=commands,
    )
    _capture_json(
        bundle_dir,
        base_command,
        "task-ready.json",
        ["task", "ready", "--format", "json"],
        artifacts=artifacts,
        commands=commands,
    )

    project_flags = _project_flags(args)
    if project_flags:
        _capture_json(
            bundle_dir,
            base_command,
            "project-task-list.json",
            ["task", "list", *project_flags, "--format", "json"],
            artifacts=artifacts,
            commands=commands,
        )
        _capture_json(
            bundle_dir,
            base_command,
            "work-daily.json",
            [
                "work",
                "daily",
                "--scope-type",
                "project",
                *_scope_flags(args),
                "--format",
                "json",
                "--no-attach",
            ],
            artifacts=artifacts,
            commands=commands,
        )

    goal_pairs = _goal_selector_pairs(args)
    for index, (flag, value) in enumerate(goal_pairs, start=1):
        artifact_name = f"goal-summary-{index}.json"
        _capture_json(
            bundle_dir,
            base_command,
            artifact_name,
            ["goal", "summary", value, "--format", "json"],
            artifacts=artifacts,
            commands=commands,
        )

    manifest = {
        "bundle_dir": str(bundle_dir),
        "generated_at": datetime.now(UTC).isoformat(),
        "selectors": {
            "project": args.project,
            "project_id": args.project_id,
            "goals": args.goal,
            "goal_ids": args.goal_id,
            "allow_no_goals": args.allow_no_goals,
        },
        "artifacts": artifacts,
        "commands": commands,
    }

    if args.emit_claude_stop_payload:
        guard_args = ["loop", "guard", *project_flags]
        for flag, value in goal_pairs:
            guard_args.extend([flag, value])
        if args.allow_no_goals:
            guard_args.append("--allow-no-goals")
        guard_args.append("--hook")
        guard_result = _run_command(base_command, guard_args)
        try:
            guard_payload = json.loads(guard_result.stdout)
        except json.JSONDecodeError as exc:
            joined = shlex.join([*base_command, *guard_args])
            raise RuntimeError(f"{joined} emitted invalid hook JSON: {exc}") from exc
        hook_path = bundle_dir / "loop-guard-hook.json"
        _write_json(hook_path, guard_payload)
        artifacts["loop-guard-hook.json"] = str(hook_path)
        commands["loop-guard-hook.json"] = shlex.join([*base_command, *guard_args])
        manifest["artifacts"] = artifacts
        manifest["commands"] = commands
        _write_json(bundle_dir / "metadata.json", manifest)
        print(json.dumps(guard_payload))
        print(f"PMS stop-audit bundle: {bundle_dir}", file=sys.stderr)
        return 0

    _write_json(bundle_dir / "metadata.json", manifest)
    print(json.dumps(manifest))
    print(f"PMS stop-audit bundle: {bundle_dir}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
