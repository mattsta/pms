"""Unit tests for managed local runtime cleanup semantics."""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from pms.runtime import local_server as local_server_module
from pms.runtime.local_server import (
    ActiveLocalServerState,
    ManagedLocalServerStatus,
    _stop_pid,
    active_local_server_state_path,
    cleanup_managed_local_servers,
    list_unmanaged_local_server_processes,
    local_server_paths,
    replace_active_local_server,
)

_GENERIC_UVICORN_COMMAND = (
    f"{Path(__file__).resolve().parents[2] / '.venv' / 'bin' / 'python'} "
    "-m uvicorn pms.api.app:app --host 127.0.0.1 --port"
)


def _write_active_state(data_dir: Path, *, pid: int, port: int) -> None:
    path = active_local_server_state_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "pid": pid,
                "host": "127.0.0.1",
                "port": port,
                "server_url": f"http://127.0.0.1:{port}",
                "log_file": str(local_server_paths(data_dir, port).log_file),
            }
        ),
        encoding="utf-8",
    )


def _managed_status(data_dir: Path, *, pid: int, port: int) -> ManagedLocalServerStatus:
    paths = local_server_paths(data_dir, port)
    paths.runtime_dir.mkdir(parents=True, exist_ok=True)
    paths.pid_file.write_text(str(pid), encoding="utf-8")
    return ManagedLocalServerStatus(
        port=port,
        server_url=f"http://127.0.0.1:{port}",
        pid=pid,
        tracked=True,
        running=True,
        reachable=True,
        pid_file=str(paths.pid_file),
        log_file=str(paths.log_file),
        error=None,
    )


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


def _spawn_session_leader_with_child(pid_file: Path) -> subprocess.Popen[str]:
    script = f"""
import subprocess
import sys
import time
from pathlib import Path

child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
Path({str(pid_file)!r}).write_text(str(child.pid), encoding="utf-8")
time.sleep(30)
"""
    return subprocess.Popen(
        [sys.executable, "-c", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        text=True,
    )


@pytest.mark.skipif(
    os.name == "nt" or not hasattr(os, "killpg"),
    reason="process-group teardown regression is Unix-specific",
)
def test_replace_active_local_server_kills_descendant_processes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir = tmp_path / "pms-data"
    port = 27541
    pid_file = tmp_path / "managed-child.pid"
    parent = _spawn_session_leader_with_child(pid_file)

    try:
        deadline = time.time() + 2.0
        while time.time() < deadline and not pid_file.exists():
            time.sleep(0.05)

        assert pid_file.exists()
        child_pid = int(pid_file.read_text(encoding="utf-8").strip())
        assert _pid_exists(child_pid)
        original_is_pid_running = local_server_module.is_pid_running

        paths = local_server_paths(data_dir, port)
        paths.runtime_dir.mkdir(parents=True, exist_ok=True)
        paths.pid_file.write_text(str(parent.pid), encoding="utf-8")
        _write_active_state(data_dir, pid=parent.pid, port=port)

        monkeypatch.setattr(
            "pms.runtime.local_server.get_active_local_server",
            lambda *args, **kwargs: ActiveLocalServerState(
                pid=parent.pid,
                host="127.0.0.1",
                port=port,
                server_url=f"http://127.0.0.1:{port}",
                log_file=str(paths.log_file),
            ),
        )
        monkeypatch.setattr(
            "pms.runtime.local_server._wait_for_server_health",
            lambda *args, **kwargs: True,
        )
        monkeypatch.setattr(
            "pms.runtime.local_server.is_pid_running",
            lambda pid: (
                parent.poll() is None
                if pid == parent.pid
                else original_is_pid_running(pid)
            ),
        )

        result = replace_active_local_server(data_dir=data_dir, timeout_seconds=1.0)

        assert result is not None
        assert result.replaced is True
        assert not paths.pid_file.exists()
        assert not active_local_server_state_path(data_dir).exists()
        assert _wait_for_pid_exit(child_pid), (
            "managed local server replacement should tear down descendant processes"
        )
    finally:
        with contextlib.suppress(ProcessLookupError):
            _stop_pid(parent.pid, timeout_seconds=1.0, process_group=True)
        with contextlib.suppress(subprocess.TimeoutExpired):
            parent.wait(timeout=1.0)


@pytest.mark.skipif(
    os.name == "nt" or not hasattr(os, "killpg"),
    reason="process-group teardown regression is Unix-specific",
)
def test_cleanup_managed_local_servers_kills_descendant_processes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir = tmp_path / "pms-data"
    port = 27541
    pid_file = tmp_path / "cleanup-child.pid"
    parent = _spawn_session_leader_with_child(pid_file)

    try:
        deadline = time.time() + 2.0
        while time.time() < deadline and not pid_file.exists():
            time.sleep(0.05)

        assert pid_file.exists()
        child_pid = int(pid_file.read_text(encoding="utf-8").strip())
        assert _pid_exists(child_pid)
        original_is_pid_running = local_server_module.is_pid_running

        status = _managed_status(data_dir, pid=parent.pid, port=port)
        _write_active_state(data_dir, pid=parent.pid, port=port)

        monkeypatch.setattr(
            "pms.runtime.local_server.list_managed_local_servers",
            lambda **kwargs: [status],
        )
        monkeypatch.setattr(
            "pms.runtime.local_server._wait_for_server_health",
            lambda *args, **kwargs: True,
        )
        monkeypatch.setattr(
            "pms.runtime.local_server.is_pid_running",
            lambda pid: (
                parent.poll() is None
                if pid == parent.pid
                else original_is_pid_running(pid)
            ),
        )

        cleaned, preserved, failed = cleanup_managed_local_servers(
            data_dir=data_dir,
            host="127.0.0.1",
            timeout_seconds=1.0,
        )

        assert [item.port for item in cleaned] == [port]
        assert preserved == []
        assert failed == []
        assert not Path(status.pid_file).exists()
        assert not active_local_server_state_path(data_dir).exists()
        assert _wait_for_pid_exit(child_pid), (
            "managed local server cleanup should tear down descendant processes"
        )
    finally:
        with contextlib.suppress(ProcessLookupError):
            _stop_pid(parent.pid, timeout_seconds=1.0, process_group=True)
        with contextlib.suppress(subprocess.TimeoutExpired):
            parent.wait(timeout=1.0)


def test_replace_active_local_server_preserves_state_when_stop_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir = tmp_path / "pms-data"
    port = 27541
    pid = 12345
    paths = local_server_paths(data_dir, port)
    paths.runtime_dir.mkdir(parents=True, exist_ok=True)
    paths.pid_file.write_text(str(pid), encoding="utf-8")
    _write_active_state(data_dir, pid=pid, port=port)

    monkeypatch.setattr(
        "pms.runtime.local_server.get_active_local_server",
        lambda *args, **kwargs: ActiveLocalServerState(
            pid=pid,
            host="127.0.0.1",
            port=port,
            server_url=f"http://127.0.0.1:{port}",
            log_file=str(paths.log_file),
        ),
    )
    monkeypatch.setattr(
        "pms.runtime.local_server._stop_pid", lambda *args, **kwargs: False
    )
    monkeypatch.setattr(
        "pms.runtime.local_server._wait_for_server_health",
        lambda *args, **kwargs: False,
    )
    monkeypatch.setattr("pms.runtime.local_server.is_pid_running", lambda _pid: True)

    result = replace_active_local_server(data_dir=data_dir, timeout_seconds=0.1)

    assert result is not None
    assert result.replaced is False
    assert "Failed to stop" in (result.error or "")
    assert paths.pid_file.exists()
    assert active_local_server_state_path(data_dir).exists()


def test_cleanup_managed_local_servers_preserves_state_when_stop_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir = tmp_path / "pms-data"
    port = 27541
    pid = 12345
    status = _managed_status(data_dir, pid=pid, port=port)
    _write_active_state(data_dir, pid=pid, port=port)

    monkeypatch.setattr(
        "pms.runtime.local_server.list_managed_local_servers",
        lambda **kwargs: [status],
    )
    monkeypatch.setattr(
        "pms.runtime.local_server._stop_pid", lambda *args, **kwargs: False
    )
    monkeypatch.setattr(
        "pms.runtime.local_server._wait_for_server_health",
        lambda *args, **kwargs: False,
    )
    monkeypatch.setattr(
        "pms.runtime.local_server.managed_local_server_status",
        lambda **kwargs: status,
    )
    monkeypatch.setattr("pms.runtime.local_server.is_pid_running", lambda _pid: True)

    cleaned, preserved, failed = cleanup_managed_local_servers(
        data_dir=data_dir,
        host="127.0.0.1",
        timeout_seconds=0.1,
    )

    assert cleaned == []
    assert preserved == []
    assert [item.port for item in failed] == [port]
    assert Path(status.pid_file).exists()
    assert active_local_server_state_path(data_dir).exists()


def test_cleanup_managed_local_servers_clears_stale_unreachable_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir = tmp_path / "pms-data"
    port = 27541
    pid = 12345
    paths = local_server_paths(data_dir, port)
    paths.runtime_dir.mkdir(parents=True, exist_ok=True)
    paths.pid_file.write_text(str(pid), encoding="utf-8")
    _write_active_state(data_dir, pid=pid, port=port)
    stale = ManagedLocalServerStatus(
        port=port,
        server_url=f"http://127.0.0.1:{port}",
        pid=pid,
        tracked=True,
        running=False,
        reachable=False,
        pid_file=str(paths.pid_file),
        log_file=str(paths.log_file),
        error="stale pid",
    )

    monkeypatch.setattr(
        "pms.runtime.local_server.list_managed_local_servers",
        lambda **kwargs: [stale],
    )

    cleaned, preserved, failed = cleanup_managed_local_servers(
        data_dir=data_dir,
        host="127.0.0.1",
        timeout_seconds=0.1,
    )

    assert [item.port for item in cleaned] == [port]
    assert preserved == []
    assert failed == []
    assert not paths.pid_file.exists()
    assert not active_local_server_state_path(data_dir).exists()


@pytest.mark.skipif(
    os.name == "nt" or not hasattr(os, "getpgid"),
    reason="process-group fallback semantics are Unix-specific",
)
def test_stop_pid_process_group_falls_back_for_non_group_leader() -> None:
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    original_is_pid_running = local_server_module.is_pid_running

    try:
        try:
            if os.getpgid(child.pid) == child.pid:
                pytest.skip("child unexpectedly owns its own process group")
        except ProcessLookupError:
            pytest.skip("child exited before process-group inspection")

        local_server_module.is_pid_running = lambda pid: (
            child.poll() is None if pid == child.pid else original_is_pid_running(pid)
        )
        assert _stop_pid(child.pid, timeout_seconds=1.0, process_group=True) is True
        assert _wait_for_pid_exit(child.pid), (
            "non-group-leader targets should fall back to leader-only termination"
        )
    finally:
        local_server_module.is_pid_running = original_is_pid_running
        with contextlib.suppress(ProcessLookupError):
            child.kill()
        with contextlib.suppress(subprocess.TimeoutExpired):
            child.wait(timeout=1.0)


def test_list_unmanaged_local_server_processes_filters_to_current_data_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_data_dir = tmp_path / "current-data"
    other_data_dir = tmp_path / "other-data"
    current_data_dir.mkdir()
    other_data_dir.mkdir()
    current_database_path = current_data_dir / "pms.db"
    other_database_path = other_data_dir / "pms.db"

    ps_output = "\n".join(
        (
            (
                f"111 {_GENERIC_UVICORN_COMMAND} 62001 "
                f"PMS_DATA_DIR={current_data_dir} "
                f"PMS_DATABASE_PATH={current_database_path}"
            ),
            (
                f"222 {_GENERIC_UVICORN_COMMAND} 62002 "
                f"PMS_DATA_DIR={other_data_dir} "
                f"PMS_DATABASE_PATH={other_database_path}"
            ),
        )
    )

    monkeypatch.setattr(
        "pms.runtime.local_server.list_managed_local_servers",
        lambda **kwargs: [],
    )
    monkeypatch.setattr("pms.runtime.local_server.os.getpid", lambda: 999999)
    monkeypatch.setattr(
        "pms.runtime.local_server.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout=ps_output,
            stderr="",
        ),
    )

    processes = list_unmanaged_local_server_processes(
        data_dir=current_data_dir,
        database_path=current_database_path,
    )

    assert [item.pid for item in processes] == [111]
    assert [item.port for item in processes] == [62001]


def test_list_unmanaged_local_server_processes_preserves_envless_workspace_servers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_data_dir = tmp_path / "current-data"
    current_data_dir.mkdir()
    current_database_path = current_data_dir / "pms.db"
    ps_output = f"333 {_GENERIC_UVICORN_COMMAND} 62003"

    monkeypatch.setattr(
        "pms.runtime.local_server.list_managed_local_servers",
        lambda **kwargs: [],
    )
    monkeypatch.setattr("pms.runtime.local_server.os.getpid", lambda: 999999)
    monkeypatch.setattr(
        "pms.runtime.local_server.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout=ps_output,
            stderr="",
        ),
    )

    processes = list_unmanaged_local_server_processes(
        data_dir=current_data_dir,
        database_path=current_database_path,
    )

    assert [item.pid for item in processes] == [333]
    assert [item.port for item in processes] == [62003]
