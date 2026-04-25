"""Remote host configuration model."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Self

from pms.models.base import BaseModel, now_utc
from pms.models.enums import HostType
from pms.models.json_types import ModelObject


@dataclass
class RemoteHost(BaseModel):
    """
    Configuration for a remote host (SSH or AWS EC2).

    Stores connection details and default paths for file synchronization.
    """

    name: str = ""  # Friendly name like "prod-server", "test-ec2"
    host: str = ""  # IP address or hostname
    port: int = 22
    username: str = ""
    key_path: str | None = None  # Path to SSH private key
    host_type: HostType = HostType.SSH
    aws_instance_id: str | None = None  # For EC2 instances
    aws_region: str | None = None
    default_remote_path: str | None = None  # Default sync destination
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate host configuration."""
        if self.host_type == HostType.AWS_EC2:
            if not self.aws_instance_id:
                raise ValueError("AWS EC2 hosts require aws_instance_id")
            if not self.aws_region:
                raise ValueError("AWS EC2 hosts require aws_region")

    @property
    def connection_string(self) -> str:
        """Get SSH connection string."""
        return f"{self.username}@{self.host}:{self.port}"

    @property
    def ssh_command_prefix(self) -> list[str]:
        """Get SSH command prefix with options."""
        cmd = ["ssh", "-p", str(self.port)]
        if self.key_path:
            cmd.extend(["-i", self.key_path])
        cmd.append(f"{self.username}@{self.host}")
        return cmd

    @property
    def rsync_host_path(self) -> str:
        """Get rsync-style host:path prefix."""
        return f"{self.username}@{self.host}:"

    def update_host(self, new_host: str) -> Self:
        """Update the host address."""
        self.host = new_host
        self.updated_at = now_utc()
        return self

    def update_credentials(
        self,
        username: str | None = None,
        key_path: str | None = None,
    ) -> Self:
        """Update connection credentials."""
        if username is not None:
            self.username = username
        if key_path is not None:
            self.key_path = key_path
        self.updated_at = now_utc()
        return self

    def add_tag(self, tag: str) -> Self:
        """Add a tag."""
        if tag not in self.tags:
            self.tags = (*self.tags, tag)
            self.updated_at = now_utc()
        return self

    def to_dict(self) -> ModelObject:
        """Convert to dictionary."""
        data = super().to_dict()
        data["host_type"] = self.host_type.value
        data["tags"] = list(self.tags)
        return data

    @classmethod
    def from_dict(cls, data: ModelObject) -> Self:
        """Create from dictionary."""
        if "host_type" in data and isinstance(data["host_type"], str):
            data["host_type"] = HostType(data["host_type"])
        if "tags" in data and isinstance(data["tags"], list):
            data["tags"] = tuple(data["tags"])
        return super().from_dict(data)


@dataclass
class SyncConfig:
    """Configuration for file synchronization between local and remote."""

    id: str = ""
    project_id: str = ""
    remote_host_id: str = ""
    local_path: str = ""
    remote_path: str = ""
    exclude_patterns: tuple[str, ...] = ()
    sync_mode: str = "mirror"

    @property
    def local_path_obj(self) -> Path:
        """Get local path as a Path instance."""
        return Path(self.local_path).expanduser().resolve()

    def to_dict(self) -> ModelObject:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "project_id": self.project_id,
            "remote_host_id": self.remote_host_id,
            "local_path": self.local_path,
            "remote_path": self.remote_path,
            "exclude_patterns": list(self.exclude_patterns),
            "sync_mode": self.sync_mode,
        }


@dataclass
class SyncResult:
    """Result of a sync operation."""

    sync_config_id: str
    direction: str  # push or pull
    status: str  # completed, failed
    files_transferred: int = 0
    bytes_transferred: int = 0
    started_at: str = ""
    completed_at: str = ""
    duration_seconds: float = 0
    error_message: str | None = None
    output: str = ""

    @property
    def success(self) -> bool:
        """Check if sync was successful."""
        return self.status == "completed"

    @property
    def bytes_human(self) -> str:
        """Get human-readable byte count."""
        b: float = self.bytes_transferred
        for unit in ["B", "KB", "MB", "GB"]:
            if b < 1024:
                return f"{b:.1f} {unit}"
            b /= 1024
        return f"{b:.1f} TB"
