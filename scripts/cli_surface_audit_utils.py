#!/usr/bin/env python3
"""Shared helpers for dynamic CLI surface audits."""

from __future__ import annotations

import errno
import fcntl
import os
import pty
import re
import socket
import struct
import subprocess
import tempfile
import termios
from collections.abc import Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def with_temp_env(prefix: str) -> dict[str, str]:
    tmp_root = REPO_ROOT / ".tmp"
    tmp_root.mkdir(exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix=prefix, dir=tmp_root))
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


def run_cli(
    args: Sequence[str],
    env: dict[str, str],
    *,
    width: int,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    command_env = dict(env)
    command_env["PMS_CONSOLE_WIDTH"] = str(width)
    return subprocess.run(
        ["uv", "run", "pms", *args],
        cwd=REPO_ROOT,
        env=command_env,
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
    )


def run_cli_tty(
    args: Sequence[str],
    env: dict[str, str],
    *,
    width: int,
    input_text: str | None = None,
) -> tuple[int, str]:
    command_env = dict(env)
    command_env["PMS_CONSOLE_WIDTH"] = str(width)
    master_fd, slave_fd = pty.openpty()
    fcntl.ioctl(
        slave_fd,
        termios.TIOCSWINSZ,
        struct.pack("HHHH", 40, width, 0, 0),
    )
    try:
        process = subprocess.Popen(
            ["uv", "run", "pms", *args],
            cwd=REPO_ROOT,
            env=command_env,
            stdin=slave_fd if input_text is not None else subprocess.DEVNULL,
            stdout=slave_fd,
            stderr=slave_fd,
            text=False,
        )
    finally:
        os.close(slave_fd)

    chunks: list[bytes] = []
    try:
        if input_text is not None:
            os.write(master_fd, input_text.encode("utf-8"))
        while True:
            try:
                chunk = os.read(master_fd, 4096)
            except OSError as exc:
                if exc.errno == errno.EIO:
                    break
                raise
            if not chunk:
                break
            chunks.append(chunk)
    finally:
        os.close(master_fd)

    return process.wait(), b"".join(chunks).decode("utf-8", errors="replace")


def strip_ansi(value: str) -> str:
    return ANSI_RE.sub("", value)


def free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def require_success(
    result: subprocess.CompletedProcess[str],
    *,
    args: Sequence[str],
) -> None:
    if result.returncode != 0:
        raise RuntimeError(
            f"command failed: {' '.join(args)}\n{result.stdout}{result.stderr}"
        )


def run_runtime_prefer_server_with_retry(
    env: dict[str, str],
    *,
    width: int,
    host: str = "127.0.0.1",
    install_client: bool = False,
    sign: bool = False,
    output_format: str = "json",
    attempts: int = 5,
) -> tuple[int, subprocess.CompletedProcess[str]]:
    """Retry runtime bootstrap across fresh ports for transient local startup failures."""
    last_port: int | None = None
    last_result: subprocess.CompletedProcess[str] | None = None
    for _ in range(attempts):
        port = free_tcp_port()
        args = [
            "runtime",
            "prefer-server",
            "--host",
            host,
            "--port",
            str(port),
        ]
        if not install_client:
            args.append("--no-install-client")
        if not sign:
            args.append("--no-sign")
        if output_format:
            args.extend(["--format", output_format])
        result = run_cli(args, env, width=width)
        if result.returncode == 0:
            return port, result
        combined_output = f"{result.stdout}{result.stderr}"
        if "Local PMS server did not become ready." not in combined_output:
            return port, result
        last_port = port
        last_result = result

    assert last_port is not None
    assert last_result is not None
    return last_port, last_result
