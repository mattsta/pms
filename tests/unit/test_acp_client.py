from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

import pytest

from pms.agents.acp.adapter import ACPLoopAdapter
from pms.agents.acp.client import ACPClient
from pms.agents.loop import AdapterConfig


class _ExitedProcess:
    def __init__(self) -> None:
        self.returncode = 1
        self.terminate_called = False
        self.kill_called = False

    def terminate(self) -> None:
        self.terminate_called = True

    def kill(self) -> None:
        self.kill_called = True

    async def wait(self) -> int:
        return self.returncode


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


@pytest.mark.asyncio
async def test_acp_client_stop_cleans_up_exited_process_state() -> None:
    client = ACPClient(command=sys.executable)
    loop = asyncio.get_running_loop()

    client._process = _ExitedProcess()  # type: ignore[assignment]
    client._read_task = loop.create_task(asyncio.sleep(3600))
    client._stderr_task = loop.create_task(asyncio.sleep(3600))

    request_future = loop.create_future()
    client._pending[1] = request_future

    await client.stop()

    assert client._process is None
    assert client._read_task is None
    assert client._stderr_task is None
    assert request_future.cancelled()
    assert client._pending == {}


@pytest.mark.skipif(
    os.name == "nt" or not hasattr(os, "killpg"),
    reason="process-group teardown regression is Unix-specific",
)
@pytest.mark.asyncio
async def test_acp_client_stop_kills_spawned_children(tmp_path: Path) -> None:
    child_pid_file = tmp_path / "acp-child.pid"
    script = """
import os
import subprocess
import sys
import time
from pathlib import Path

child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
Path(os.environ["ACP_CHILD_PID_FILE"]).write_text(str(child.pid), encoding="utf-8")
time.sleep(30)
"""

    client = ACPClient(
        command=sys.executable,
        args=["-c", script],
        env={"ACP_CHILD_PID_FILE": str(child_pid_file)},
    )

    await client.start()

    deadline = time.time() + 2.0
    while time.time() < deadline and not child_pid_file.exists():
        await asyncio.sleep(0.05)

    assert child_pid_file.exists()
    child_pid = int(child_pid_file.read_text(encoding="utf-8").strip())
    assert _pid_exists(child_pid)

    await client.stop()

    assert client._process is None
    assert _wait_for_pid_exit(child_pid), (
        "ACP client stop should tear down descendant processes"
    )


@pytest.mark.asyncio
async def test_acp_loop_adapter_reinitializes_dead_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instances: list[_FakeACPClient] = []

    class _FakeACPClient:
        def __init__(
            self,
            command: str,
            args: list[str] | None = None,
            timeout: int = 300,
            stream_limit: int | None = None,
            env: dict[str, str] | None = None,
        ) -> None:
            self.command = command
            self.args = args or []
            self.timeout = timeout
            self.stream_limit = stream_limit
            self.env = env or {}
            self.running = False
            self.stopped = False
            instances.append(self)

        @property
        def is_running(self) -> bool:
            return self.running

        async def start(self) -> None:
            self.running = True

        async def stop(self) -> None:
            self.running = False
            self.stopped = True

        def on_notification(self, handler) -> None:  # type: ignore[no-untyped-def]
            return None

        def on_request(self, handler) -> None:  # type: ignore[no-untyped-def]
            return None

        def send_request(
            self, method: str, params: dict[str, object]
        ) -> asyncio.Future[object]:
            loop = asyncio.get_running_loop()
            future: asyncio.Future[object] = loop.create_future()
            if method == "initialize":
                future.set_result({"protocolVersion": 1})
            elif method == "session/new":
                future.set_result({"sessionId": f"session-{len(instances)}"})
            elif method == "session/prompt":
                future.set_result({"stopReason": "completed"})
            else:
                future.set_result({})
            return future

    monkeypatch.setattr("pms.agents.acp.adapter.ACPClient", _FakeACPClient)

    adapter = ACPLoopAdapter(
        "acp",
        AdapterConfig(
            name="acp",
            type="acp",
            command=sys.executable,
            agent_command=sys.executable,
            timeout_seconds=5,
        ),
    )

    first = await adapter.run("first")
    assert first.success is True
    assert len(instances) == 1

    instances[0].running = False

    second = await adapter.run("second")
    assert second.success is True
    assert len(instances) == 2
    assert instances[0].stopped is True
