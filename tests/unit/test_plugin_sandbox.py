import asyncio
import contextlib
import os
import sys
import time
from pathlib import Path

import pytest

from pms.plugins.manifest import PluginManifest
from pms.plugins.sandbox import SandboxConfig, SandboxedPlugin


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    else:
        return True


def _wait_for_pid_exit(pid: int, timeout: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _pid_exists(pid):
            return True
        time.sleep(0.05)
    return not _pid_exists(pid)


@pytest.mark.skipif(
    os.name == "nt" or not hasattr(os, "killpg"),
    reason="process-group teardown regression is Unix-specific",
)
@pytest.mark.asyncio
async def test_stop_kills_spawned_children(tmp_path: Path):
    manifest = PluginManifest(name="sandbox-test", version="1.0.0")
    sandbox = SandboxedPlugin(
        manifest=manifest,
        config=SandboxConfig(shutdown_timeout=1.0),
        plugin_dir=tmp_path,
    )

    script = """
import subprocess
import sys
import time

child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
print(child.pid, flush=True)
time.sleep(30)
"""

    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        script,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )

    assert process.stdout is not None
    child_pid = int(
        (await asyncio.wait_for(process.stdout.readline(), timeout=2)).decode().strip()
    )
    assert _pid_exists(child_pid)

    sandbox._process = process

    await sandbox.stop()

    assert sandbox.pid is None
    assert _wait_for_pid_exit(child_pid), (
        "sandbox stop should tear down descendant processes"
    )

    with contextlib.suppress(ProcessLookupError):
        os.kill(process.pid, 0)
