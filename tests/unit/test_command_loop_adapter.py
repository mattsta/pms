from __future__ import annotations

import contextlib
import os
import signal
import sys
import time
from pathlib import Path

import pytest

from pms.agents.loop import AdapterConfig, CommandLoopAdapter


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


@pytest.mark.asyncio
async def test_command_loop_adapter_kills_spawned_children_on_timeout(
    tmp_path: Path,
) -> None:
    child_pid_file = tmp_path / "child.pid"
    config = AdapterConfig(
        name="timeout-child-cleanup",
        command=sys.executable,
        args=[
            "-c",
            (
                "import pathlib, subprocess, sys, time; "
                f"pid_path = pathlib.Path({str(child_pid_file)!r}); "
                "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']); "
                "pid_path.write_text(str(child.pid), encoding='utf-8'); "
                "time.sleep(30)"
            ),
        ],
        timeout_seconds=1,
        max_retries=0,
    )
    adapter = CommandLoopAdapter("timeout-child-cleanup", config)

    response = await adapter.run("ignored")

    assert response.success is False
    assert response.error == "Command timed out after 1s"
    child_pid = int(child_pid_file.read_text(encoding="utf-8"))
    assert _wait_for_pid_exit(child_pid), (
        "child subprocess leaked after adapter timeout and parent teardown"
    )

    with contextlib.suppress(OSError):
        os.kill(child_pid, signal.SIGKILL)


@pytest.mark.asyncio
async def test_command_loop_adapter_cleans_up_prompt_file_on_timeout(
    tmp_path: Path,
) -> None:
    prompt_capture = tmp_path / "prompt-path.txt"
    config = AdapterConfig(
        name="timeout-file-cleanup",
        command=sys.executable,
        args=[
            "-c",
            (
                "import os, pathlib, time; "
                f"path = pathlib.Path({str(prompt_capture)!r}); "
                "path.write_text(os.environ['PMS_PROMPT_FILE'], encoding='utf-8'); "
                "time.sleep(30)"
            ),
        ],
        timeout_seconds=1,
        prompt_mode="file",
        max_retries=0,
    )
    adapter = CommandLoopAdapter("timeout-file-cleanup", config)

    response = await adapter.run("prompt body")

    assert response.success is False
    assert response.error == "Command timed out after 1s"
    prompt_path = Path(prompt_capture.read_text(encoding="utf-8"))
    assert not prompt_path.exists()
