"""Helpers for managing a local PMS API server process."""

from __future__ import annotations

import contextlib
import json
import os
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from pms.runtime.write_coordination import probe_server_health


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


LOCAL_SERVER_PROBE_TIMEOUT_SECONDS = 3.0
LOCAL_SERVER_STARTUP_TIMEOUT_SECONDS = _float_env(
    "PMS_LOCAL_SERVER_STARTUP_TIMEOUT_SECONDS", 60.0
)


@dataclass(frozen=True)
class LocalServerPaths:
    """Filesystem paths used for a managed local PMS server."""

    runtime_dir: Path
    pid_file: Path
    log_file: Path


@dataclass(frozen=True)
class LocalServerBootstrapResult:
    """Outcome of ensuring a local PMS server is available."""

    server_url: str
    reachable: bool
    started_now: bool
    pid: int | None
    pid_file: str
    log_file: str
    error: str | None


@dataclass(frozen=True)
class ManagedLocalServerStatus:
    """Observed state for a managed local PMS server slot."""

    port: int
    server_url: str
    pid: int | None
    tracked: bool
    running: bool
    reachable: bool
    pid_file: str
    log_file: str
    error: str | None


@dataclass(frozen=True)
class UnmanagedLocalServerProcess:
    """Observed local PMS server process not tracked in managed runtime state."""

    pid: int
    port: int | None
    command: str
    kind: str


@dataclass(frozen=True)
class ActiveLocalServerState:
    """Single active local PMS server for a PMS data directory."""

    pid: int
    host: str
    port: int
    server_url: str
    log_file: str


@dataclass(frozen=True)
class ActiveLocalServerReplacementResult:
    """Outcome of replacing one active local PMS server with another."""

    previous_server_url: str
    previous_pid: int
    replaced: bool
    error: str | None


def local_server_paths(data_dir: Path, port: int) -> LocalServerPaths:
    """Return runtime paths for a managed local server."""
    runtime_dir = data_dir / "runtime"
    return LocalServerPaths(
        runtime_dir=runtime_dir,
        pid_file=runtime_dir / f"server-{port}.pid",
        log_file=runtime_dir / f"server-{port}.log",
    )


def active_local_server_state_path(data_dir: Path) -> Path:
    """Return the path used to track the active local PMS server."""
    return data_dir / "runtime" / "active-server.json"


def _read_active_local_server_state(data_dir: Path) -> ActiveLocalServerState | None:
    path = active_local_server_state_path(data_dir)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError, ValueError, TypeError:
        path.unlink(missing_ok=True)
        return None
    try:
        return ActiveLocalServerState(
            pid=int(payload["pid"]),
            host=str(payload["host"]),
            port=int(payload["port"]),
            server_url=str(payload["server_url"]),
            log_file=str(payload["log_file"]),
        )
    except KeyError, TypeError, ValueError:
        path.unlink(missing_ok=True)
        return None


def write_active_local_server_state(
    data_dir: Path,
    *,
    pid: int,
    host: str,
    port: int,
    log_file: str,
) -> None:
    """Persist the single active local PMS server for this PMS data dir."""
    path = active_local_server_state_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "pid": pid,
        "host": host,
        "port": port,
        "server_url": f"http://{host}:{port}",
        "log_file": log_file,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def clear_active_local_server_state(
    data_dir: Path,
    *,
    pid: int | None = None,
    server_url: str | None = None,
) -> None:
    """Remove the active-server marker when it matches the expected server."""
    path = active_local_server_state_path(data_dir)
    state = _read_active_local_server_state(data_dir)
    if state is None:
        path.unlink(missing_ok=True)
        return
    if pid is not None and state.pid != pid:
        return
    if server_url is not None and state.server_url != server_url:
        return
    path.unlink(missing_ok=True)


def get_active_local_server(
    data_dir: Path, *, timeout_seconds: float = LOCAL_SERVER_PROBE_TIMEOUT_SECONDS
) -> ActiveLocalServerState | None:
    """Return the live active local PMS server for a PMS data dir, if any."""
    state = _read_active_local_server_state(data_dir)
    if state is None:
        return None
    if not is_pid_running(state.pid):
        clear_active_local_server_state(data_dir, pid=state.pid)
        return None
    health = probe_server_health(state.server_url, timeout_seconds=timeout_seconds)
    if not health.reachable:
        clear_active_local_server_state(data_dir, pid=state.pid)
        return None
    return state


def replace_active_local_server(
    *,
    data_dir: Path,
    timeout_seconds: float = 5.0,
) -> ActiveLocalServerReplacementResult | None:
    """Stop and clear the currently active local PMS server for this data dir."""
    active = get_active_local_server(
        data_dir, timeout_seconds=LOCAL_SERVER_PROBE_TIMEOUT_SECONDS
    )
    if active is None:
        return None

    stopped = _stop_pid(
        active.pid,
        timeout_seconds=timeout_seconds,
        process_group=True,
    )
    unreachable = _wait_for_server_health(
        active.server_url,
        reachable=False,
        timeout_seconds=timeout_seconds,
    )

    error: str | None = None
    if stopped and unreachable and not is_pid_running(active.pid):
        old_paths = local_server_paths(data_dir, active.port)
        old_paths.pid_file.unlink(missing_ok=True)
        clear_active_local_server_state(
            data_dir,
            pid=active.pid,
            server_url=active.server_url,
        )
    else:
        error = (
            "Failed to stop the previously active local PMS server before replacement."
        )

    return ActiveLocalServerReplacementResult(
        previous_server_url=active.server_url,
        previous_pid=active.pid,
        replaced=error is None,
        error=error,
    )


def read_pid(pid_file: Path) -> int | None:
    """Read a managed PID file if it exists and is valid."""
    if not pid_file.exists():
        return None
    content = pid_file.read_text().strip()
    if not content.isdigit():
        return None
    return int(content)


def is_pid_running(pid: int) -> bool:
    """Check whether a process is currently running."""
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _dedicated_process_group_id(pid: int) -> int | None:
    """Return a safe process-group target when the PID owns its own group."""
    try:
        process_group_id = os.getpgid(pid)
    except OSError:
        return None

    # Only tear down dedicated groups owned by the target PID. Shell-launched
    # background processes often share the caller's group, and killing that
    # group would take down unrelated siblings or the current command itself.
    if process_group_id != pid:
        return None

    try:
        if process_group_id == os.getpgrp():
            return None
    except OSError:
        return None

    return process_group_id


def _stop_process_group(process_group_id: int, *, timeout_seconds: float = 5.0) -> bool:
    try:
        os.killpg(process_group_id, signal.SIGTERM)
    except OSError:
        return False

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not is_pid_running(process_group_id):
            return True
        time.sleep(0.2)

    try:
        os.killpg(process_group_id, signal.SIGKILL)
    except OSError:
        return not is_pid_running(process_group_id)
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not is_pid_running(process_group_id):
            return True
        time.sleep(0.1)
    return not is_pid_running(process_group_id)


def _stop_pid(
    pid: int,
    *,
    timeout_seconds: float = 5.0,
    process_group: bool = False,
) -> bool:
    if process_group and os.name != "nt" and hasattr(os, "killpg"):
        process_group_id = _dedicated_process_group_id(pid)
        if process_group_id is not None:
            return _stop_process_group(
                process_group_id, timeout_seconds=timeout_seconds
            )

    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return False

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not is_pid_running(pid):
            return True
        time.sleep(0.2)

    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        return not is_pid_running(pid)
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not is_pid_running(pid):
            return True
        time.sleep(0.1)
    return not is_pid_running(pid)


def _stop_pids(pids: list[int], *, timeout_seconds: float = 5.0) -> set[int]:
    """Stop many local server processes without waiting serially per PID."""
    remaining = {pid for pid in pids if is_pid_running(pid)}
    if not remaining:
        return set()

    for pid in remaining:
        with contextlib.suppress(OSError):
            os.kill(pid, signal.SIGTERM)

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline and remaining:
        done = {pid for pid in remaining if not is_pid_running(pid)}
        remaining -= done
        time.sleep(0.1)

    if remaining:
        for pid in list(remaining):
            with contextlib.suppress(OSError):
                os.kill(pid, signal.SIGKILL)

        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline and remaining:
            done = {pid for pid in remaining if not is_pid_running(pid)}
            remaining -= done
            time.sleep(0.1)

    return {pid for pid in pids if not is_pid_running(pid)}


def _wait_for_server_health(
    server_url: str,
    *,
    reachable: bool,
    timeout_seconds: float,
) -> bool:
    """Wait until a server becomes reachable or unreachable."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        health = probe_server_health(
            server_url, timeout_seconds=LOCAL_SERVER_PROBE_TIMEOUT_SECONDS
        )
        if health.reachable is reachable:
            return True
        time.sleep(0.1)
    final_health = probe_server_health(
        server_url, timeout_seconds=LOCAL_SERVER_PROBE_TIMEOUT_SECONDS
    )
    return final_health.reachable is reachable


def managed_local_server_status(
    *, data_dir: Path, host: str, port: int
) -> ManagedLocalServerStatus:
    """Return the observed state for one managed local PMS server port."""
    server_url = f"http://{host}:{port}"
    paths = local_server_paths(data_dir, port)
    pid = read_pid(paths.pid_file)
    running = pid is not None and is_pid_running(pid)
    health = probe_server_health(
        server_url, timeout_seconds=LOCAL_SERVER_PROBE_TIMEOUT_SECONDS
    )
    return ManagedLocalServerStatus(
        port=port,
        server_url=server_url,
        pid=pid,
        tracked=pid is not None,
        running=running,
        reachable=health.reachable,
        pid_file=str(paths.pid_file),
        log_file=str(paths.log_file),
        error=health.error,
    )


def list_managed_local_servers(
    *, data_dir: Path, host: str = "127.0.0.1"
) -> list[ManagedLocalServerStatus]:
    """List all managed local PMS server slots tracked in the runtime directory."""
    runtime_dir = data_dir / "runtime"
    if not runtime_dir.exists():
        return []

    statuses: list[ManagedLocalServerStatus] = []
    for pid_file in sorted(runtime_dir.glob("server-*.pid")):
        stem = pid_file.stem
        try:
            port = int(stem.split("-", 1)[1])
        except IndexError, ValueError:
            continue
        statuses.append(
            managed_local_server_status(data_dir=data_dir, host=host, port=port)
        )
    return statuses


def list_unmanaged_local_server_processes(
    *,
    data_dir: Path,
    database_path: Path | None = None,
    host: str = "127.0.0.1",
    repo_root: Path | None = None,
) -> list[UnmanagedLocalServerProcess]:
    """List workspace-local PMS server processes that are not tracked as managed slots."""
    tracked_pids = {
        status.pid
        for status in list_managed_local_servers(data_dir=data_dir, host=host)
        if status.pid is not None
    }
    workspace_root = str((repo_root or Path(__file__).resolve().parents[2]).resolve())
    current_pid = os.getpid()
    result: subprocess.CompletedProcess[str] | None = None
    for command in (
        ["ps", "eww", "-ax", "-o", "pid=,command="],
        ["ps", "-ax", "-o", "pid=,command="],
    ):
        candidate = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
        if candidate.returncode == 0:
            result = candidate
            break
    if result is None:
        return []

    resolved_data_dir = str(data_dir.resolve())
    resolved_database_path = (
        str(database_path.resolve()) if database_path is not None else None
    )

    processes: list[UnmanagedLocalServerProcess] = []
    seen_pids: set[int] = set()
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            pid_text, command = line.split(maxsplit=1)
            pid = int(pid_text)
        except ValueError:
            continue
        if pid == current_pid or pid in tracked_pids or pid in seen_pids:
            continue
        if workspace_root not in command:
            continue

        kind: str | None = None
        if "-m pms serve" in command:
            kind = "pms_serve"
        elif "-m uvicorn pms.api.app:app" in command:
            kind = "uvicorn"
        if kind is None:
            continue

        process_data_dir_match = re.search(r"(?:^|\s)PMS_DATA_DIR=(\S+)", command)
        process_database_path_match = re.search(
            r"(?:^|\s)PMS_DATABASE_PATH=(\S+)", command
        )
        if process_data_dir_match is not None:
            with contextlib.suppress(OSError, RuntimeError):
                process_data_dir = str(Path(process_data_dir_match.group(1)).resolve())
                if process_data_dir != resolved_data_dir:
                    continue
        elif (
            resolved_database_path is not None
            and process_database_path_match is not None
        ):
            with contextlib.suppress(OSError, RuntimeError):
                process_database_path = str(
                    Path(process_database_path_match.group(1)).resolve()
                )
                if process_database_path != resolved_database_path:
                    continue

        host_match = re.search(r"--host\s+(\S+)", command)
        if host_match and host_match.group(1) != host:
            continue
        port_match = re.search(r"--port\s+(\d+)", command)
        port = int(port_match.group(1)) if port_match else None
        processes.append(
            UnmanagedLocalServerProcess(
                pid=pid,
                port=port,
                command=command,
                kind=kind,
            )
        )
        seen_pids.add(pid)

    return sorted(processes, key=lambda item: (item.port or 0, item.pid))


def cleanup_managed_local_servers(
    *,
    data_dir: Path,
    host: str = "127.0.0.1",
    timeout_seconds: float = 5.0,
    preserve_server_url: str | None = None,
) -> tuple[
    list[ManagedLocalServerStatus],
    list[ManagedLocalServerStatus],
    list[ManagedLocalServerStatus],
]:
    """Stop tracked managed local PMS servers, optionally preserving one URL."""
    cleaned: list[ManagedLocalServerStatus] = []
    preserved: list[ManagedLocalServerStatus] = []
    failed: list[ManagedLocalServerStatus] = []
    for status in list_managed_local_servers(data_dir=data_dir, host=host):
        if preserve_server_url and status.server_url == preserve_server_url:
            preserved.append(status)
            continue
        if status.pid is not None and status.running:
            stopped = _stop_pid(
                status.pid,
                timeout_seconds=timeout_seconds,
                process_group=True,
            )
            unreachable = _wait_for_server_health(
                status.server_url,
                reachable=False,
                timeout_seconds=timeout_seconds,
            )
            if not stopped or not unreachable or is_pid_running(status.pid):
                failed.append(
                    managed_local_server_status(
                        data_dir=data_dir,
                        host=host,
                        port=status.port,
                    )
                )
                continue
        elif status.reachable:
            failed.append(
                managed_local_server_status(
                    data_dir=data_dir,
                    host=host,
                    port=status.port,
                )
            )
            continue

        Path(status.pid_file).unlink(missing_ok=True)
        clear_active_local_server_state(
            data_dir,
            pid=status.pid,
            server_url=status.server_url,
        )
        cleaned.append(
            ManagedLocalServerStatus(
                port=status.port,
                server_url=status.server_url,
                pid=status.pid,
                tracked=False,
                running=False,
                reachable=False,
                pid_file=status.pid_file,
                log_file=status.log_file,
                error=None,
            )
        )
    return cleaned, preserved, failed


def cleanup_unmanaged_local_server_processes(
    *,
    data_dir: Path,
    database_path: Path | None = None,
    host: str = "127.0.0.1",
    timeout_seconds: float = 5.0,
    repo_root: Path | None = None,
    ports: set[int] | None = None,
    pids: set[int] | None = None,
) -> list[UnmanagedLocalServerProcess]:
    """Stop workspace-local PMS server processes that are not tracked as managed slots."""
    candidates: list[UnmanagedLocalServerProcess] = []
    for process in list_unmanaged_local_server_processes(
        data_dir=data_dir,
        database_path=database_path,
        host=host,
        repo_root=repo_root,
    ):
        if ports is not None and process.port not in ports:
            continue
        if pids is not None and process.pid not in pids:
            continue
        candidates.append(process)

    stopped = _stop_pids(
        [process.pid for process in candidates],
        timeout_seconds=timeout_seconds,
    )
    return [process for process in candidates if process.pid in stopped]


def ensure_local_server(
    *,
    data_dir: Path,
    database_path: Path | None = None,
    log_dir: Path | None = None,
    host: str,
    port: int,
    timeout_seconds: float = LOCAL_SERVER_STARTUP_TIMEOUT_SECONDS,
) -> LocalServerBootstrapResult:
    """Ensure a local PMS API server is running and reachable."""
    server_url = f"http://{host}:{port}"
    active_server = get_active_local_server(
        data_dir, timeout_seconds=LOCAL_SERVER_PROBE_TIMEOUT_SECONDS
    )
    if active_server is not None:
        if active_server.server_url == server_url:
            active_paths = local_server_paths(data_dir, active_server.port)
            return LocalServerBootstrapResult(
                server_url=active_server.server_url,
                reachable=True,
                started_now=False,
                pid=active_server.pid,
                pid_file=str(active_paths.pid_file),
                log_file=active_server.log_file,
                error=None,
            )
        replacement = replace_active_local_server(
            data_dir=data_dir,
            timeout_seconds=timeout_seconds,
        )
        if replacement is not None and not replacement.replaced:
            return LocalServerBootstrapResult(
                server_url=server_url,
                reachable=False,
                started_now=False,
                pid=None,
                pid_file=str(local_server_paths(data_dir, port).pid_file),
                log_file=str(local_server_paths(data_dir, port).log_file),
                error=replacement.error,
            )
    existing_health = probe_server_health(
        server_url, timeout_seconds=LOCAL_SERVER_PROBE_TIMEOUT_SECONDS
    )
    paths = local_server_paths(data_dir, port)
    paths.runtime_dir.mkdir(parents=True, exist_ok=True)

    tracked_pid = read_pid(paths.pid_file)
    if tracked_pid is not None and not is_pid_running(tracked_pid):
        paths.pid_file.unlink(missing_ok=True)
        tracked_pid = None
        existing_health = probe_server_health(
            server_url, timeout_seconds=LOCAL_SERVER_PROBE_TIMEOUT_SECONDS
        )
    if existing_health.reachable:
        return LocalServerBootstrapResult(
            server_url=server_url,
            reachable=True,
            started_now=False,
            pid=tracked_pid,
            pid_file=str(paths.pid_file),
            log_file=str(paths.log_file),
            error=None,
        )

    pid = tracked_pid
    if pid is not None and not is_pid_running(pid):
        paths.pid_file.unlink(missing_ok=True)
        pid = None
    elif pid is not None and is_pid_running(pid):
        # A tracked managed process is still alive but the server probe is unhealthy.
        # Stop it before spawning a replacement so managed bootstrap cannot orphan servers.
        _stop_pid(
            pid,
            timeout_seconds=timeout_seconds,
            process_group=True,
        )
        paths.pid_file.unlink(missing_ok=True)
        pid = None

    with paths.log_file.open("a", encoding="utf-8") as log_handle:
        managed_env = os.environ.copy()
        managed_env["PMS_DATA_DIR"] = str(data_dir)
        managed_env["PMS_DATABASE_PATH"] = str(database_path or (data_dir / "pms.db"))
        managed_env["PMS_LOG_DIR"] = str(log_dir or (data_dir / "logs"))
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "pms.api.app:app",
                "--host",
                host,
                "--port",
                str(port),
                "--log-level",
                "info",
            ],
            cwd=Path(__file__).resolve().parents[2],
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=managed_env,
        )
        pid = process.pid
        paths.pid_file.write_text(f"{pid}\n", encoding="utf-8")

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        health = probe_server_health(
            server_url, timeout_seconds=LOCAL_SERVER_PROBE_TIMEOUT_SECONDS
        )
        if health.reachable:
            write_active_local_server_state(
                data_dir,
                pid=pid,
                host=host,
                port=port,
                log_file=str(paths.log_file),
            )
            return LocalServerBootstrapResult(
                server_url=server_url,
                reachable=True,
                started_now=True,
                pid=pid,
                pid_file=str(paths.pid_file),
                log_file=str(paths.log_file),
                error=None,
            )
        time.sleep(0.2)

    return LocalServerBootstrapResult(
        server_url=server_url,
        reachable=False,
        started_now=True,
        pid=pid,
        pid_file=str(paths.pid_file),
        log_file=str(paths.log_file),
        error="Local PMS server did not become healthy before timeout",
    )


def stop_local_server(
    *, data_dir: Path, port: int, timeout_seconds: float = 5.0
) -> bool:
    """Stop a managed local PMS server if one is tracked."""
    paths = local_server_paths(data_dir, port)
    pid = read_pid(paths.pid_file)
    if pid is None:
        return False

    stopped = _stop_pid(
        pid,
        timeout_seconds=timeout_seconds,
        process_group=True,
    )
    if not stopped:
        paths.pid_file.unlink(missing_ok=True)
        clear_active_local_server_state(data_dir, pid=pid)
        return False
    paths.pid_file.unlink(missing_ok=True)
    clear_active_local_server_state(
        data_dir,
        pid=pid,
        server_url=f"http://127.0.0.1:{port}",
    )
    _wait_for_server_health(
        f"http://127.0.0.1:{port}",
        reachable=False,
        timeout_seconds=timeout_seconds,
    )
    return True
