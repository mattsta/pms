"""Tests for remote utilities and service."""

import contextlib
import os
import signal
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pms.exceptions import RemoteError
from pms.models import HostType, RemoteHost
from pms.utils.rsync import RsyncConfig, SyncResult, sync
from pms.utils.ssh import CommandResult, SSHConfig


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


class TestSSHConfig:
    """Tests for SSHConfig dataclass."""

    def test_basic_config(self) -> None:
        """Test creating basic SSH config."""
        config = SSHConfig(
            host="example.com",
            username="admin",
        )
        assert config.host == "example.com"
        assert config.username == "admin"
        assert config.port == 22
        assert config.private_key_path is None

    def test_config_with_key(self) -> None:
        """Test SSH config with private key."""
        config = SSHConfig(
            host="example.com",
            username="admin",
            port=2222,
            private_key_path=Path("~/.ssh/id_rsa"),
        )
        assert config.port == 2222
        assert config.private_key_path == Path("~/.ssh/id_rsa")

    def test_to_connect_options(self) -> None:
        """Test conversion to asyncssh connect options."""
        config = SSHConfig(
            host="example.com",
            username="admin",
            port=22,
        )
        options = config.to_connect_options()
        assert options["host"] == "example.com"
        assert options["username"] == "admin"
        assert options["port"] == 22

    def test_to_connect_options_with_key(self) -> None:
        """Test connect options includes private key."""
        config = SSHConfig(
            host="example.com",
            username="admin",
            private_key_path=Path("/home/user/.ssh/id_rsa"),
        )
        options = config.to_connect_options()
        assert "client_keys" in options
        assert options["client_keys"] == ["/home/user/.ssh/id_rsa"]


class TestCommandResult:
    """Tests for CommandResult dataclass."""

    def test_successful_command(self) -> None:
        """Test successful command result."""
        now = datetime.now(UTC)
        result = CommandResult(
            command="echo hello",
            exit_code=0,
            stdout="hello\n",
            stderr="",
            started_at=now,
            finished_at=now,
            host="example.com",
        )
        assert result.success is True
        assert result.duration_seconds == 0.0

    def test_failed_command(self) -> None:
        """Test failed command result."""
        now = datetime.now(UTC)
        result = CommandResult(
            command="false",
            exit_code=1,
            stdout="",
            stderr="command failed",
            started_at=now,
            finished_at=now,
            host="example.com",
        )
        assert result.success is False


class TestRsyncConfig:
    """Tests for RsyncConfig dataclass."""

    def test_basic_config(self) -> None:
        """Test basic rsync configuration."""
        config = RsyncConfig(
            source="/local/path/",
            destination="user@host:/remote/path/",
        )
        assert config.source == "/local/path/"
        assert config.recursive is True
        assert config.archive is True

    def test_to_args_basic(self) -> None:
        """Test conversion to rsync arguments."""
        config = RsyncConfig(
            source="/local/",
            destination="user@host:/remote/",
        )
        args = config.to_args()
        assert args[0] == "rsync"
        assert "-a" in args  # archive
        assert "-z" in args  # compress
        assert "--progress" in args
        assert "/local/" in args
        assert "user@host:/remote/" in args

    def test_to_args_with_exclude(self) -> None:
        """Test rsync args with exclude patterns."""
        config = RsyncConfig(
            source="/local/",
            destination="/remote/",
            exclude=["*.pyc", "__pycache__"],
        )
        args = config.to_args()
        assert "--exclude" in args
        idx = args.index("--exclude")
        assert args[idx + 1] == "*.pyc"

    def test_to_args_with_delete(self) -> None:
        """Test rsync args with delete option."""
        config = RsyncConfig(
            source="/local/",
            destination="/remote/",
            delete=True,
        )
        args = config.to_args()
        assert "--delete" in args

    def test_to_args_dry_run(self) -> None:
        """Test rsync args with dry run."""
        config = RsyncConfig(
            source="/local/",
            destination="/remote/",
            dry_run=True,
        )
        args = config.to_args()
        assert "--dry-run" in args

    def test_to_args_ssh_options(self) -> None:
        """Test rsync args with SSH options."""
        config = RsyncConfig(
            source="/local/",
            destination="user@host:/remote/",
            ssh_port=2222,
            ssh_key=Path("/home/user/.ssh/id_rsa"),
        )
        args = config.to_args()
        assert "-e" in args
        idx = args.index("-e")
        ssh_cmd = args[idx + 1]
        assert "ssh" in ssh_cmd
        assert "-p 2222" in ssh_cmd
        assert "-i /home/user/.ssh/id_rsa" in ssh_cmd


class TestSyncResult:
    """Tests for SyncResult dataclass."""

    def test_successful_sync(self) -> None:
        """Test successful sync result."""
        now = datetime.now(UTC)
        result = SyncResult(
            source="/local/",
            destination="/remote/",
            exit_code=0,
            stdout="sent 100 bytes",
            stderr="",
            started_at=now,
            finished_at=now,
            files_transferred=5,
        )
        assert result.success is True
        assert result.files_transferred == 5

    def test_failed_sync(self) -> None:
        """Test failed sync result."""
        now = datetime.now(UTC)
        result = SyncResult(
            source="/local/",
            destination="/remote/",
            exit_code=1,
            stdout="",
            stderr="connection refused",
            started_at=now,
            finished_at=now,
        )
        assert result.success is False


@pytest.mark.asyncio
async def test_sync_timeout_kills_spawned_children(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    child_pid_file = tmp_path / "child.pid"
    parent_script = tmp_path / "spawn_child.py"
    parent_script.write_text(
        (
            "import pathlib, subprocess, sys, time\n"
            "pid_path = pathlib.Path(sys.argv[1])\n"
            "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
            "pid_path.write_text(str(child.pid), encoding='utf-8')\n"
            "time.sleep(30)\n"
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("pms.utils.rsync._check_rsync_available", lambda: True)
    monkeypatch.setattr(
        RsyncConfig,
        "to_args",
        lambda self: [sys.executable, str(parent_script), str(child_pid_file)],
    )

    config = RsyncConfig(source="/local/", destination="/remote/")

    with pytest.raises(RemoteError, match="rsync timed out after 1.0s"):
        await sync(config, timeout=1.0)

    child_pid = int(child_pid_file.read_text(encoding="utf-8"))
    assert _wait_for_pid_exit(child_pid), (
        "child subprocess leaked after rsync timeout teardown"
    )

    with contextlib.suppress(OSError):
        os.kill(child_pid, signal.SIGKILL)


class TestRemoteHost:
    """Tests for RemoteHost model."""

    def test_create_remote_host(self) -> None:
        """Test creating a remote host."""
        host = RemoteHost(
            id="test-id",
            name="myserver",
            host="192.168.1.100",
            username="admin",
        )
        assert host.name == "myserver"
        assert host.host == "192.168.1.100"
        assert host.username == "admin"
        assert host.port == 22
        assert host.host_type == HostType.SSH

    def test_remote_host_with_key(self) -> None:
        """Test remote host with SSH key."""
        host = RemoteHost(
            id="test-id",
            name="prod",
            host="example.com",
            username="deploy",
            port=2222,
            key_path="~/.ssh/deploy_key",
            default_remote_path="/var/www/app",
            tags=("production", "web"),
        )
        assert host.port == 2222
        assert host.key_path == "~/.ssh/deploy_key"
        assert host.default_remote_path == "/var/www/app"
        assert "production" in host.tags

    def test_aws_ec2_host(self) -> None:
        """Test AWS EC2 host type."""
        host = RemoteHost(
            id="test-id",
            name="aws-instance",
            host="ec2-1-2-3-4.compute.amazonaws.com",
            username="ec2-user",
            host_type=HostType.AWS_EC2,
            aws_instance_id="i-1234567890abcdef0",
            aws_region="us-east-1",
        )
        assert host.host_type == HostType.AWS_EC2
        assert host.aws_instance_id == "i-1234567890abcdef0"
        assert host.aws_region == "us-east-1"
