#!/usr/bin/env python3
"""Run a command with a hard timeout and kill its whole process group on overrun."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import time
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a command with a hard timeout and process-group cleanup."
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        required=True,
        help="Maximum runtime before the process group is terminated.",
    )
    parser.add_argument(
        "--cwd",
        type=Path,
        default=None,
        help="Optional working directory for the child command.",
    )
    parser.add_argument(
        "--stdout-file",
        type=Path,
        default=None,
        help="Optional file to receive stdout.",
    )
    parser.add_argument(
        "--stderr-file",
        type=Path,
        default=None,
        help="Optional file to receive stderr.",
    )
    parser.add_argument(
        "--kill-grace-seconds",
        type=float,
        default=5.0,
        help="How long to wait after SIGTERM before SIGKILL.",
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Command to run. Prefix with -- to separate runner flags from the command.",
    )
    args = parser.parse_args()
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        parser.error("a command is required after --")
    return args


def _open_stream(path: Path | None):
    if path is None:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.open("w", encoding="utf-8")


def _terminate_process_group(
    process: subprocess.Popen[bytes], grace_seconds: float
) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return

    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return
        time.sleep(0.1)

    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return


def main() -> int:
    args = _parse_args()
    stdout_handle = _open_stream(args.stdout_file)
    stderr_handle = _open_stream(args.stderr_file)

    try:
        process = subprocess.Popen(
            args.command,
            cwd=str(args.cwd) if args.cwd is not None else None,
            stdout=stdout_handle or None,
            stderr=stderr_handle or None,
            start_new_session=True,
        )
        try:
            return process.wait(timeout=args.timeout_seconds)
        except subprocess.TimeoutExpired:
            _terminate_process_group(process, args.kill_grace_seconds)
            return 124
    finally:
        if stdout_handle is not None:
            stdout_handle.close()
        if stderr_handle is not None and stderr_handle is not stdout_handle:
            stderr_handle.close()


if __name__ == "__main__":
    raise SystemExit(main())
