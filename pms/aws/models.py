"""Data models for AWS test server management."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any


class ServerState(Enum):
    """State of a test server instance."""

    PENDING = "pending"
    RUNNING = "running"
    STOPPING = "stopping"
    TERMINATED = "terminated"
    INTERRUPTED = "interrupted"  # Spot interruption


@dataclass(frozen=True)
class SpotOption:
    """A potential spot instance option with pricing and availability info."""

    instance_type: str  # e.g., "t3.medium"
    availability_zone: str  # e.g., "us-east-1a"
    current_price: Decimal  # USD per hour
    interruption_rate: float  # 0-1, historical interruption frequency
    vcpus: int
    memory_gb: float
    score: float  # Computed value score (higher is better)

    def __post_init__(self) -> None:
        if not 0 <= self.interruption_rate <= 1:
            raise ValueError("interruption_rate must be between 0 and 1")
        if self.score < 0:
            raise ValueError("score must be non-negative")


@dataclass(frozen=True)
class SpotQuery:
    """Query parameters for finding spot instances."""

    min_vcpus: int = 2
    min_memory_gb: float = 4.0
    max_price_per_hour: Decimal = field(default_factory=lambda: Decimal("0.10"))
    regions: tuple[str, ...] = ("us-east-1", "us-west-2")
    exclude_instance_types: tuple[str, ...] = ()  # e.g., ("t2.*",)
    prefer_low_interruption: bool = True
    architecture: str = "x86_64"  # or "arm64" for Graviton

    def __post_init__(self) -> None:
        if self.min_vcpus < 1:
            raise ValueError("min_vcpus must be at least 1")
        if self.min_memory_gb < 0.5:
            raise ValueError("min_memory_gb must be at least 0.5")


@dataclass(frozen=True)
class SpotServerConfig:
    """Configuration for launching a test server."""

    name: str
    instance_type: str
    availability_zone: str | None = None  # None = auto-select
    ami_id: str | None = None  # None = latest Amazon Linux 2023
    key_name: str | None = None  # SSH key pair name
    security_group_ids: tuple[str, ...] = ()
    subnet_id: str | None = None
    root_volume_gb: int = 20
    spot_max_price: Decimal | None = None  # None = on-demand price cap

    # Auto-termination settings
    max_runtime_hours: float = 4.0  # Auto-terminate after this
    idle_terminate_minutes: int = 30  # Terminate if idle this long

    # Bootstrap configuration
    user_data: str | None = None  # Cloud-init script
    setup_commands: tuple[str, ...] = ()  # Run after boot
    python_version: str = "3.12"  # Python to install
    install_docker: bool = False

    # Project linkage
    project_id: str | None = None

    # Tags for organization
    tags: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if self.max_runtime_hours <= 0:
            raise ValueError("max_runtime_hours must be positive")
        if self.idle_terminate_minutes < 0:
            raise ValueError("idle_terminate_minutes must be non-negative")
        if self.root_volume_gb < 8:
            raise ValueError("root_volume_gb must be at least 8")


@dataclass
class SpotServer:
    """A running test server instance."""

    id: str  # PMS internal ID
    instance_id: str  # EC2 instance ID
    name: str
    config: SpotServerConfig
    state: ServerState
    launched_at: datetime
    region: str
    availability_zone: str

    # Network info (available when running)
    public_ip: str | None = None
    private_ip: str | None = None
    public_dns: str | None = None

    # Cost tracking
    hourly_price: Decimal = field(default_factory=lambda: Decimal(0))
    estimated_cost: Decimal = field(default_factory=lambda: Decimal(0))

    # Activity tracking
    last_activity: datetime | None = None
    terminated_at: datetime | None = None

    @property
    def ssh_command(self) -> str | None:
        """Generate SSH command to connect to this server."""
        if not self.public_ip:
            return None
        key_part = f"-i ~/.pms/keys/{self.name}.pem " if self.config.key_name else ""
        return f"ssh {key_part}ec2-user@{self.public_ip}"

    @property
    def is_active(self) -> bool:
        """Check if server is in an active state."""
        return self.state in (ServerState.PENDING, ServerState.RUNNING)


@dataclass(frozen=True)
class RemoteTestConfig:
    """Configuration for a test run on a remote server."""

    server_id: str
    project_path: Path  # Local project to sync
    remote_path: str = "/home/ec2-user/project"
    project_id: str | None = None
    plan_id: str | None = None
    task_ids: tuple[str, ...] = ()
    transition_on_success: str | None = None
    transition_on_failure: str | None = None
    transition_by: str | None = None
    transition_reason: str | None = None

    # Test execution
    test_command: str = "pytest"  # Command to run tests
    setup_command: str | None = None  # Run before tests (e.g., pip install)
    working_dir: str | None = None  # Relative to remote_path
    env_vars: tuple[tuple[str, str], ...] = ()
    timeout: float = 600.0  # Test timeout in seconds

    # Sync options
    exclude_patterns: tuple[str, ...] = (
        ".git",
        "__pycache__",
        "*.pyc",
        ".venv",
        "node_modules",
        ".pytest_cache",
        ".mypy_cache",
        "dist",
        "build",
        ".ruff_cache",
        ".coverage",
        "htmlcov",
    )

    # Output handling
    stream_output: bool = True  # Request live output when the caller has a sink
    capture_logs: tuple[str, ...] = ()  # Log files to capture after
    save_artifacts: tuple[str, ...] = ()  # Files to download after


@dataclass
class RemoteTestResult:
    """Result of a test run."""

    run_id: str
    server_id: str
    success: bool
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    started_at: datetime
    finished_at: datetime
    logs: dict[str, str] = field(default_factory=dict)  # path -> content
    artifacts: dict[str, Path] = field(
        default_factory=dict
    )  # remote path -> local path
    workflow_transition: Any | None = None

    @property
    def summary(self) -> str:
        """Generate a brief summary of the test result."""
        status = "PASSED" if self.success else "FAILED"
        return f"{status} (exit code {self.exit_code}) in {self.duration_seconds:.1f}s"


@dataclass(frozen=True)
class SecurityGroupRule:
    """Security group rule for inter-server communication."""

    from_role: str  # e.g., "web"
    to_role: str  # e.g., "db"
    port: int
    protocol: str = "tcp"
    description: str = ""


@dataclass(frozen=True)
class DeploymentConfig:
    """How to deploy to a specific server role."""

    project_path: Path
    remote_path: str = "/home/ec2-user/project"
    setup_command: str | None = None  # e.g., "pip install -r requirements.txt"
    start_command: str | None = None  # e.g., "docker-compose up -d"
    health_check: str | None = None  # e.g., "curl -f localhost:8080/health"
    health_check_timeout: float = 60.0
    exclude_patterns: tuple[str, ...] = (
        ".git",
        "__pycache__",
        "*.pyc",
        ".venv",
        "node_modules",
    )


@dataclass(frozen=True)
class NetworkTestConfig:
    """Configuration for multi-server network testing."""

    name: str
    servers: tuple[tuple[str, SpotServerConfig], ...]  # role -> config

    # Network setup
    security_group_rules: tuple[SecurityGroupRule, ...] = ()

    # Deployment per role
    deployments: tuple[tuple[str, DeploymentConfig], ...] = ()

    # Environment settings
    max_runtime_hours: float = 2.0
    auto_destroy: bool = True  # Destroy on test completion

    def get_server_config(self, role: str) -> SpotServerConfig | None:
        """Get server config for a role."""
        for r, config in self.servers:
            if r == role:
                return config
        return None

    def get_deployment(self, role: str) -> DeploymentConfig | None:
        """Get deployment config for a role."""
        for r, config in self.deployments:
            if r == role:
                return config
        return None


@dataclass
class NetworkEnvironment:
    """A running multi-server test environment."""

    id: str
    name: str
    config: NetworkTestConfig
    state: ServerState
    servers: dict[str, SpotServer]  # role -> server
    security_group_id: str | None = None
    created_at: datetime | None = None
    destroyed_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        """Check if environment is active."""
        return self.state in (ServerState.PENDING, ServerState.RUNNING)

    @property
    def all_servers_running(self) -> bool:
        """Check if all servers are running."""
        return all(s.state == ServerState.RUNNING for s in self.servers.values())

    @property
    def total_hourly_cost(self) -> Decimal:
        """Calculate total hourly cost of all servers."""
        return sum(
            (s.hourly_price for s in self.servers.values()),
            Decimal(0),
        )
