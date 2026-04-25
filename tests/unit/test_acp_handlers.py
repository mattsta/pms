from __future__ import annotations

import contextlib
import os
import signal
import sys
import time
from pathlib import Path

from pms.agents.acp.handlers import ACPHandlers


def test_terminal_wait_for_exit_returns_final_output_and_releases_handle() -> None:
    handlers = ACPHandlers(permission_mode="auto_approve")
    created = handlers.handle_terminal_create(
        {
            "command": [
                sys.executable,
                "-c",
                "import sys; print('boom'); sys.exit(1)",
            ]
        }
    )

    terminal_id = created["terminalId"]
    result = handlers.handle_terminal_wait_for_exit(
        {"terminalId": terminal_id, "timeout": 5}
    )

    assert result["done"] is True
    assert result["released"] is True
    assert result["exitCode"] == 1
    assert "boom" in result["output"]
    assert terminal_id not in handlers._terminals

    release = handlers.handle_terminal_release({"terminalId": terminal_id})
    assert release == {"success": True, "alreadyReleased": True}


def test_terminal_output_auto_releases_completed_handle() -> None:
    handlers = ACPHandlers(permission_mode="auto_approve")
    created = handlers.handle_terminal_create(
        {
            "command": [
                sys.executable,
                "-c",
                "print('done')",
            ]
        }
    )

    terminal_id = created["terminalId"]
    result = handlers.handle_terminal_output({"terminalId": terminal_id})

    # Short-lived processes may need one more read after the spawn boundary.
    if result["done"] is False:
        result = handlers.handle_terminal_wait_for_exit(
            {"terminalId": terminal_id, "timeout": 5}
        )

    assert result["done"] is True
    assert result["released"] is True
    assert result["exitCode"] == 0
    assert "done" in result["output"]
    assert terminal_id not in handlers._terminals


def test_terminal_kill_returns_final_state_and_releases_handle() -> None:
    handlers = ACPHandlers(permission_mode="auto_approve")
    created = handlers.handle_terminal_create(
        {
            "command": [
                sys.executable,
                "-c",
                "import time; print('start'); time.sleep(30)",
            ]
        }
    )

    terminal_id = created["terminalId"]
    result = handlers.handle_terminal_kill({"terminalId": terminal_id})

    assert result["success"] is True
    assert result["done"] is True
    assert result["released"] is True
    assert terminal_id not in handlers._terminals


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _wait_for_pid_exit(pid: int, *, timeout_seconds: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not _pid_exists(pid):
            return True
        time.sleep(0.05)
    return not _pid_exists(pid)


def test_terminal_kill_reaps_spawned_children(tmp_path: Path) -> None:
    handlers = ACPHandlers(permission_mode="auto_approve")
    child_pid_file = tmp_path / "child.pid"
    created = handlers.handle_terminal_create(
        {
            "command": [
                sys.executable,
                "-c",
                (
                    "import pathlib, subprocess, sys, time; "
                    f"pid_path = pathlib.Path({str(child_pid_file)!r}); "
                    "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']); "
                    "pid_path.write_text(str(child.pid), encoding='utf-8'); "
                    "time.sleep(30)"
                ),
            ]
        }
    )

    terminal_id = created["terminalId"]
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and not child_pid_file.exists():
        time.sleep(0.05)
    assert child_pid_file.exists()

    result = handlers.handle_terminal_kill({"terminalId": terminal_id})

    assert result["success"] is True
    assert result["released"] is True
    child_pid = int(child_pid_file.read_text(encoding="utf-8"))
    assert _wait_for_pid_exit(child_pid), (
        "ACP terminal kill leaked a spawned child process"
    )

    with contextlib.suppress(OSError):
        os.kill(child_pid, signal.SIGKILL)
