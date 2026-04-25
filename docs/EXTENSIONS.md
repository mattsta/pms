# PMS Extension Designs

## Overview

This document outlines well-encapsulated capability extensions for PMS. Each extension is designed to:

- Be self-contained with clear boundaries
- Integrate cleanly with existing services
- Follow the event-sourcing pattern
- Provide both CLI and Python API interfaces

---

## 1. AWS Spot Instance Test Server Management

### Problem Statement

Developers need cost-effective remote test environments that:

- Launch quickly when needed
- Run tests on real Linux servers (not just local machines)
- Support the edit-sync-test cycle with minimal friction
- Handle both single-server (library testing) and multi-server (network services) scenarios
- Auto-terminate to avoid cost overruns
- Stream logs reliably back to the developer

### Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        AWS Test Server Manager                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│      ┌──────────────┐     ┌──────────────┐     ┌──────────────┐     │
│      │  SpotFinder  │     │ FleetManager │     │  TestRunner  │     │
│      │              │     │              │     │              │     │
│      │ - Price API  │     │ - Launch     │     │ - Sync code  │     │
│      │ - AZ picker  │     │ - Monitor    │     │ - Run tests  │     │
│      │ - Instance   │     │ - Terminate  │     │ - Stream logs│     │
│      │   scoring    │     │ - Auto-stop  │     │ - Collect    │     │
│      └──────────────┘     └──────────────┘     │   results    │     │
│                                                └──────────────┘     │
│                                  ↓                                  │
│   ┌──────────────────────────────────────────────────────────────┐  │
│   │                    Existing PMS Services                     │  │
│   │  RemoteService (SSH/rsync) ←→ EventStore ←→ MetricsCollector │  │
│   └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Components

#### 1.1 SpotFinder - Cost-Effective Instance Discovery

```python
@dataclass(frozen=True)
class SpotOption:
    """A potential spot instance option."""
    instance_type: str           # e.g., "t3.medium"
    availability_zone: str       # e.g., "us-east-1a"
    current_price: Decimal       # USD per hour
    interruption_rate: float     # 0-1, historical interruption frequency
    vcpus: int
    memory_gb: float
    score: float                 # Computed value score

@dataclass(frozen=True)
class SpotQuery:
    """Query parameters for finding spot instances."""
    min_vcpus: int = 2
    min_memory_gb: float = 4.0
    max_price_per_hour: Decimal = Decimal("0.10")
    regions: tuple[str, ...] = ("us-east-1", "us-west-2")
    exclude_instance_types: tuple[str, ...] = ()  # e.g., ("t2.*",)
    prefer_low_interruption: bool = True

class SpotFinder:
    """Find cost-effective spot instances."""

    def __init__(self, boto_session: boto3.Session):
        self._ec2 = boto_session.client('ec2')
        self._pricing = boto_session.client('pricing', region_name='us-east-1')

    async def find_best_options(
        self,
        query: SpotQuery,
        limit: int = 5,
    ) -> list[SpotOption]:
        """
        Find the best spot instance options.

        Scoring considers:
        - Price per vCPU-hour
        - Interruption rate (lower is better)
        - Memory/vCPU ratio for the workload
        """
        ...

    async def get_current_price(
        self,
        instance_type: str,
        availability_zone: str,
    ) -> Decimal:
        """Get current spot price for an instance type."""
        ...

    async def get_interruption_stats(
        self,
        instance_type: str,
        region: str,
    ) -> float:
        """Get historical interruption rate (0-1)."""
        # Uses AWS Spot Instance Advisor data
        ...
```

**CLI:**

```bash
# Find cheapest spot instances for testing
pms aws spot find --vcpus 2 --memory 4 --max-price 0.05

# Output:
# Best Spot Options:
# ┏━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━┓
# ┃ Instance    ┃ Zone         ┃ Price/hr ┃ Interruption┃ Score ┃
# ┡━━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━┩
# │ t3.medium   │ us-east-1a   │ $0.0125  │ 5%          │ 0.95  │
# │ t3a.medium  │ us-east-1b   │ $0.0113  │ 8%          │ 0.92  │
# │ t3.medium   │ us-west-2c   │ $0.0118  │ 3%          │ 0.94  │
# └─────────────┴──────────────┴──────────┴─────────────┴───────┘
```

#### 1.2 FleetManager - Instance Lifecycle

```python
@dataclass(frozen=True)
class TestServerConfig:
    """Configuration for a test server."""
    name: str
    instance_type: str
    availability_zone: str
    ami_id: str | None = None              # None = latest Amazon Linux 2
    key_name: str | None = None            # SSH key pair name
    security_group_ids: tuple[str, ...] = ()
    subnet_id: str | None = None
    root_volume_gb: int = 20
    spot_max_price: Decimal | None = None  # None = on-demand price cap

    # Auto-termination
    max_runtime_hours: float = 4.0         # Auto-terminate after this
    idle_terminate_minutes: int = 30       # Terminate if idle

    # Bootstrap
    user_data: str | None = None           # Cloud-init script
    setup_commands: tuple[str, ...] = ()   # Run after boot

@dataclass
class TestServer:
    """A running test server instance."""
    id: str                                # PMS internal ID
    instance_id: str                       # EC2 instance ID
    name: str
    config: TestServerConfig
    public_ip: str | None
    private_ip: str | None
    state: ServerState                     # pending, running, stopping, terminated
    launched_at: datetime
    estimated_cost: Decimal                # Running cost so far
    last_activity: datetime                # For idle detection

class ServerState(Enum):
    PENDING = "pending"
    RUNNING = "running"
    STOPPING = "stopping"
    TERMINATED = "terminated"
    INTERRUPTED = "interrupted"            # Spot interruption

class FleetManager:
    """Manage test server fleet lifecycle."""

    def __init__(
        self,
        db: Database,
        event_store: EventStore,
        metrics: MetricsCollector,
        boto_session: boto3.Session,
    ):
        ...

    async def launch_server(
        self,
        config: TestServerConfig,
        wait_for_ready: bool = True,
        timeout: float = 300.0,
    ) -> TestServer:
        """
        Launch a spot instance test server.

        1. Request spot instance
        2. Wait for running state
        3. Wait for SSH connectivity
        4. Run setup commands
        5. Register with RemoteService
        """
        ...

    async def launch_fleet(
        self,
        configs: list[TestServerConfig],
        wait_for_all: bool = True,
    ) -> list[TestServer]:
        """Launch multiple servers in parallel."""
        ...

    async def terminate_server(
        self,
        server_id: str,
        force: bool = False,
    ) -> None:
        """Terminate a test server."""
        ...

    async def terminate_all(
        self,
        project_id: str | None = None,
    ) -> int:
        """Terminate all test servers, optionally filtered by project."""
        ...

    async def get_server(self, server_id: str) -> TestServer | None:
        ...

    async def list_servers(
        self,
        state: ServerState | None = None,
        project_id: str | None = None,
    ) -> list[TestServer]:
        ...

    async def refresh_state(self, server_id: str) -> TestServer:
        """Refresh server state from AWS."""
        ...

    async def handle_interruption(self, instance_id: str) -> None:
        """Handle spot interruption notice (2-minute warning)."""
        # 1. Log event
        # 2. Attempt to save any in-progress work
        # 3. Update state
        ...

    # Background tasks
    async def start_monitors(self) -> None:
        """Start background monitoring tasks."""
        # - Idle detection
        # - Max runtime enforcement
        # - Spot interruption polling
        # - Cost tracking
        ...
```

**CLI:**

```bash
# Launch a single test server
pms aws server launch mytest --type t3.medium --max-hours 2

# Output:
# Launching spot instance t3.medium in us-east-1a...
# Instance i-0abc123def456 launched
# Waiting for SSH connectivity... ready!
# Running setup commands... done
#
# Test server ready:
#   Name: mytest
#   IP: 54.123.45.67
#   SSH: ssh -i ~/.ssh/pms-key.pem ec2-user@54.123.45.67
#   Auto-terminate: 2 hours (or 30 min idle)
#   Estimated cost: ~$0.025/hr

# Launch a fleet for network testing
pms aws server launch-fleet \
  --config server1:t3.medium \
  --config server2:t3.medium \
  --config server3:t3.small \
  --max-hours 1

# List running servers
pms aws server list

# Terminate all
pms aws server terminate-all --yes
```

#### 1.3 TestRunner - Edit-Sync-Test Cycle

```python
@dataclass(frozen=True)
class TestRunConfig:
    """Configuration for a test run."""
    server_id: str
    project_path: Path                     # Local project to sync
    remote_path: str = "/home/ec2-user/project"

    # Test execution
    test_command: str = "pytest"           # Command to run tests
    setup_command: str | None = None       # Run before tests (e.g., pip install)
    working_dir: str | None = None         # Relative to remote_path
    env_vars: dict[str, str] = field(default_factory=dict)
    timeout: float = 600.0                 # Test timeout

    # Sync options
    exclude_patterns: tuple[str, ...] = (
        ".git", "__pycache__", "*.pyc", ".venv", "node_modules",
        ".pytest_cache", ".mypy_cache", "dist", "build",
    )

    # Output handling
    stream_output: bool = True             # Request live output when a caller provides a sink
    capture_logs: tuple[str, ...] = ()     # Log files to capture after
    save_artifacts: tuple[str, ...] = ()   # Files to download after

@dataclass
class TestResult:
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
    logs: dict[str, str]                   # Captured log contents
    artifacts: dict[str, Path]             # Downloaded artifact paths

class TestRunner:
    """Run tests on remote servers with sync support."""

    def __init__(
        self,
        remote_service: RemoteService,
        fleet_manager: FleetManager,
        event_store: EventStore,
    ):
        ...

    async def sync_and_run(
        self,
        config: TestRunConfig,
    ) -> TestResult:
        """
        Sync project and run tests.

        1. Sync local project to remote
        2. Run setup command if specified
        3. Run test command
        4. Capture output and logs
        5. Download artifacts
        """
        ...

    async def sync_only(
        self,
        server_id: str,
        project_path: Path,
        remote_path: str,
    ) -> SyncResult:
        """Just sync, don't run tests."""
        ...

    async def run_only(
        self,
        server_id: str,
        command: str,
        working_dir: str | None = None,
        stream: bool = True,
    ) -> CommandResult:
        """Run command without syncing."""
        ...

    async def watch_and_sync(
        self,
        server_id: str,
        project_path: Path,
        remote_path: str,
        debounce_seconds: float = 1.0,
    ) -> AsyncIterator[SyncResult]:
        """
        Watch local files and auto-sync on changes.

        Uses filesystem events (watchdog) to detect changes
        and automatically rsync to the remote server.
        """
        ...

    async def tail_logs(
        self,
        server_id: str,
        log_paths: list[str],
        follow: bool = True,
    ) -> AsyncIterator[tuple[str, str]]:
        """
        Tail remote log files.

        Yields: (log_path, line) tuples as logs arrive
        """
        ...

    async def get_run_history(
        self,
        server_id: str | None = None,
        limit: int = 20,
    ) -> list[TestResult]:
        """Get recent test run history."""
        ...
```

**CLI:**

```bash
# Full cycle: sync and run tests
pms aws test run mytest ./myproject --command "pytest -v"

# Output:
# Syncing ./myproject to mytest:/home/ec2-user/project...
# Files transferred: 47
# Running: pytest -v
#
# ========================= test session starts =========================
# platform linux -- Python 3.11.0, pytest-8.0.0
# collected 23 items
#
# tests/test_api.py::test_health_check PASSED
# tests/test_api.py::test_create_user PASSED
# ...
#
# ========================= 23 passed in 4.52s ==========================
#
# Test run completed: SUCCESS
# Duration: 12.3s (sync: 2.1s, tests: 4.5s)

# Watch mode: auto-sync on file changes
pms aws test watch mytest ./myproject
# Watching ./myproject for changes...
# [12:34:56] Changed: src/api.py -> syncing... done (0.3s)
# [12:35:02] Changed: tests/test_api.py -> syncing... done (0.2s)

# Tail remote logs
pms aws logs tail mytest /var/log/app/error.log /var/log/app/access.log

# Run arbitrary command
pms aws exec mytest "systemctl status nginx"
```

#### 1.4 Multi-Server Network Testing

```python
@dataclass(frozen=True)
class NetworkTestConfig:
    """Configuration for multi-server network testing."""
    name: str
    servers: dict[str, TestServerConfig]   # role -> config

    # Network setup
    security_group_rules: list[SecurityGroupRule] = field(default_factory=list)

    # Deployment
    deployments: dict[str, DeploymentConfig] = field(default_factory=dict)

@dataclass(frozen=True)
class DeploymentConfig:
    """How to deploy to a specific server role."""
    project_path: Path
    remote_path: str
    setup_command: str | None = None
    start_command: str | None = None       # e.g., "docker-compose up -d"
    health_check: str | None = None        # e.g., "curl localhost:8080/health"

@dataclass(frozen=True)
class SecurityGroupRule:
    """Security group rule for inter-server communication."""
    from_role: str                         # e.g., "web"
    to_role: str                           # e.g., "db"
    port: int
    protocol: str = "tcp"

class NetworkTestManager:
    """Manage multi-server network test environments."""

    async def create_environment(
        self,
        config: NetworkTestConfig,
    ) -> dict[str, TestServer]:
        """
        Create a complete test environment.

        1. Create security group with inter-server rules
        2. Launch all servers in parallel
        3. Configure /etc/hosts or DNS for service discovery
        4. Deploy to each server
        5. Run health checks
        """
        ...

    async def deploy_to_role(
        self,
        env_name: str,
        role: str,
    ) -> None:
        """Redeploy to a specific server role."""
        ...

    async def run_integration_tests(
        self,
        env_name: str,
        test_server_role: str,
        test_command: str,
    ) -> TestResult:
        """Run integration tests from one server."""
        ...

    async def destroy_environment(
        self,
        env_name: str,
    ) -> None:
        """Tear down entire environment."""
        ...
```

**CLI:**

```bash
# Define environment in YAML
cat > test-env.yaml << 'EOF'
name: api-test-env
servers:
  web:
    instance_type: t3.medium
    count: 2
  db:
    instance_type: t3.small
  redis:
    instance_type: t3.micro

network:
  - from: web, to: db, port: 5432
  - from: web, to: redis, port: 6379

deployments:
  web:
    path: ./api
    setup: pip install -r requirements.txt
    start: gunicorn app:app -b 0.0.0.0:8080
    health: curl -f localhost:8080/health
  db:
    path: ./db
    setup: ./init-db.sh
  redis:
    start: redis-server
EOF

# Launch environment
pms aws env create test-env.yaml

# Output:
# Creating environment: api-test-env
# Launching servers...
#   web-1: t3.medium in us-east-1a... running (54.1.2.3)
#   web-2: t3.medium in us-east-1b... running (54.1.2.4)
#   db: t3.small in us-east-1a... running (54.1.2.5)
#   redis: t3.micro in us-east-1a... running (54.1.2.6)
# Configuring network...
# Deploying...
#   web-1: syncing... setup... starting... healthy!
#   web-2: syncing... setup... starting... healthy!
#   db: syncing... setup... ready!
#   redis: starting... ready!
#
# Environment ready! Estimated cost: $0.08/hr
#
# Server IPs:
#   web-1: 54.1.2.3
#   web-2: 54.1.2.4
#   db: 54.1.2.5
#   redis: 54.1.2.6

# Run integration tests
pms aws env test api-test-env --from web-1 --command "pytest tests/integration/"

# Destroy when done
pms aws env destroy api-test-env --yes
```

### Database Schema Additions

```sql
-- Test servers
CREATE TABLE test_servers (
    id TEXT PRIMARY KEY,
    instance_id TEXT UNIQUE,
    name TEXT NOT NULL,
    project_id TEXT REFERENCES projects(id),
    config JSON NOT NULL,
    public_ip TEXT,
    private_ip TEXT,
    state TEXT NOT NULL DEFAULT 'pending',
    launched_at TIMESTAMP NOT NULL,
    terminated_at TIMESTAMP,
    last_activity TIMESTAMP,
    total_cost REAL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Test runs
CREATE TABLE test_runs (
    id TEXT PRIMARY KEY,
    server_id TEXT REFERENCES test_servers(id),
    project_id TEXT REFERENCES projects(id),
    config JSON NOT NULL,
    exit_code INTEGER,
    stdout TEXT,
    stderr TEXT,
    duration_seconds REAL,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Network environments
CREATE TABLE network_environments (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    config JSON NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    destroyed_at TIMESTAMP
);

CREATE TABLE network_environment_servers (
    network_environment_id TEXT NOT NULL REFERENCES network_environments(id),
    server_id TEXT NOT NULL REFERENCES test_servers(id),
    server_role TEXT,
    position INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (network_environment_id, server_id),
    UNIQUE (network_environment_id, server_role)
);

-- Cost tracking
CREATE TABLE aws_costs (
    id TEXT PRIMARY KEY,
    server_id TEXT REFERENCES test_servers(id),
    instance_type TEXT NOT NULL,
    hours REAL NOT NULL,
    cost_usd REAL NOT NULL,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Integration with Existing PMS

```python
# In RemoteService - auto-register launched servers
async def _register_test_server(self, server: TestServer) -> RemoteHost:
    """Register a test server as a remote host."""
    return await self.add_host(
        name=f"aws-{server.name}",
        host=server.public_ip,
        username="ec2-user",
        port=22,
        key_path=str(self._key_path),
        default_remote_path="/home/ec2-user/project",
        tags=["aws", "spot", "test-server"],
        host_type=HostType.AWS_EC2,
        aws_instance_id=server.instance_id,
        aws_region=self._region,
    )

# In ProjectService - link servers to projects
async def link_test_server(
    self,
    project_id: str,
    server_id: str,
) -> None:
    """Associate a test server with a project."""
    ...

# Events emitted
class ServerLaunched(Event): ...
class ServerTerminated(Event): ...
class ServerInterrupted(Event): ...
class TestRunCompleted(Event): ...
```

---

## 2. Documentation Generation

### Problem Statement

Projects need up-to-date documentation that:

- Generates README from code analysis
- Creates API documentation
- Maintains changelogs
- Stays in sync with code changes

### Components

```python
@dataclass(frozen=True)
class DocGenConfig:
    """Documentation generation configuration."""
    project_path: Path
    output_dir: Path

    # What to generate
    generate_readme: bool = True
    generate_api_docs: bool = True
    generate_changelog: bool = True

    # README options
    readme_sections: tuple[str, ...] = (
        "overview", "installation", "usage", "api", "contributing"
    )

    # API doc options
    api_format: str = "markdown"  # or "sphinx", "mkdocs"
    include_private: bool = False

    # Changelog options
    changelog_from_commits: bool = True
    changelog_from_events: bool = True  # PMS task completion events

class DocsService:
    """Generate and maintain documentation."""

    async def generate_readme(
        self,
        project_path: Path,
        output_path: Path | None = None,
    ) -> str:
        """
        Generate README.md from code analysis.

        Uses Claude to:
        - Analyze code structure
        - Extract docstrings
        - Generate usage examples
        - Create installation instructions
        """
        ...

    async def generate_api_docs(
        self,
        project_path: Path,
        output_dir: Path,
    ) -> list[Path]:
        """Generate API documentation for all modules."""
        ...

    async def generate_changelog(
        self,
        project_id: str,
        since: datetime | None = None,
    ) -> str:
        """
        Generate changelog from:
        - Git commits
        - PMS task completion events
        - Milestone completions
        """
        ...

    async def check_docs_freshness(
        self,
        project_path: Path,
    ) -> DocsFreshnessReport:
        """Check if docs are out of date with code."""
        ...
```

**CLI:**

```bash
pms docs generate ./myproject --readme --api
pms docs changelog "Web API" --since 2025-01-01
pms docs check ./myproject  # Check if docs need updating
```

---

## 3. CI/CD Integration

### Problem Statement

Connect PMS with CI/CD systems to:

- Track test results from CI runs
- Update task status based on CI outcomes
- Generate GitHub Actions workflows
- Link commits to tasks

### Components

```python
class CIService:
    """CI/CD integration service."""

    async def import_github_actions_run(
        self,
        repo: str,
        run_id: int,
    ) -> CIRunResult:
        """Import results from a GitHub Actions run."""
        ...

    async def generate_workflow(
        self,
        project_id: str,
        workflow_type: str,  # "test", "deploy", "release"
    ) -> str:
        """Generate GitHub Actions workflow YAML."""
        ...

    async def link_commit_to_task(
        self,
        task_id: str,
        commit_sha: str,
        repo: str,
    ) -> None:
        """Link a git commit to a task."""
        ...

    async def auto_complete_task_on_merge(
        self,
        task_id: str,
        pr_number: int,
    ) -> None:
        """Set up webhook to complete task when PR merges."""
        ...
```

**CLI:**

```bash
pms ci import-run owner/repo 12345
pms ci generate-workflow "Web API" --type test
pms ci link-commit abc123 --task 22ac9217
```

---

## 4. Time Tracking

### Problem Statement

Track actual time spent on tasks for:

- Estimation accuracy improvement
- Billing/invoicing
- Productivity analysis

### Components

```python
@dataclass
class TimeEntry:
    """A time tracking entry."""
    id: str
    task_id: str
    started_at: datetime
    ended_at: datetime | None
    duration_minutes: int
    notes: str | None
    billable: bool

class TimeService:
    """Track time spent on tasks."""

    async def start_timer(
        self,
        task_id: str,
        notes: str | None = None,
    ) -> TimeEntry:
        """Start tracking time on a task."""
        ...

    async def stop_timer(
        self,
        entry_id: str | None = None,  # None = stop active timer
    ) -> TimeEntry:
        """Stop the current timer."""
        ...

    async def log_time(
        self,
        task_id: str,
        minutes: int,
        date: date | None = None,
        notes: str | None = None,
    ) -> TimeEntry:
        """Manually log time."""
        ...

    async def get_report(
        self,
        project_id: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> TimeReport:
        """Generate time report."""
        ...
```

**CLI:**

```bash
pms time start 22ac9217 --notes "Working on auth"
pms time stop
pms time log 22ac9217 --minutes 90 --date 2025-01-15
pms time report --project "Web API" --week
```

---

## 5. Notifications

### Problem Statement

Get notified when:

- Test servers are ready
- Long-running tests complete
- Tasks become unblocked
- Servers are about to auto-terminate

### Components

```python
class NotificationService:
    """Send notifications via various channels."""

    async def configure_channel(
        self,
        channel_type: str,  # "slack", "discord", "email", "desktop"
        config: dict,
    ) -> None:
        ...

    async def notify(
        self,
        message: str,
        channel: str | None = None,  # None = all configured
        priority: str = "normal",  # "low", "normal", "high"
    ) -> None:
        ...

    # Automatic notification triggers
    async def on_server_ready(self, server: TestServer) -> None: ...
    async def on_test_complete(self, result: TestResult) -> None: ...
    async def on_task_unblocked(self, task: Task) -> None: ...
    async def on_server_terminating(self, server: TestServer, minutes: int) -> None: ...
```

**CLI:**

```bash
pms notify setup slack --webhook-url https://hooks.slack.com/...
pms notify setup desktop  # macOS notifications
pms notify test "Hello from PMS!"
```

---

## Implementation Priority

### Phase 1: AWS Core (Recommended First)

1. SpotFinder - Find cost-effective instances
2. FleetManager - Launch/terminate single servers
3. TestRunner - Sync and run tests
4. Basic CLI commands

### Phase 2: AWS Advanced

1. Multi-server NetworkTestManager
2. Watch mode for auto-sync
3. Log tailing
4. Cost tracking

### Phase 3: Developer Experience

1. Time tracking
2. Notifications
3. CI/CD integration

### Phase 4: Documentation

1. README generation
2. API docs
3. Changelog generation

---

## Dependencies to Add

```toml
[project.optional-dependencies]
aws = [
    "boto3>=1.34",
    "botocore>=1.34",
]
notifications = [
    "slack-sdk>=3.0",
    "discord.py>=2.0",
]
watch = [
    "watchdog>=4.0",
]
docs = [
    "mkdocs>=1.5",
    "mkdocstrings>=0.24",
]
```

---

## Open Questions

1. **Spot interruption handling**: Should we auto-migrate to on-demand, or just notify and terminate?
2. **Key management**: Generate per-session keys, or require user to provide?
3. **VPC setup**: Auto-create VPC/subnets, or require pre-existing?
4. **AMI selection**: Just Amazon Linux 2, or support Ubuntu/custom AMIs?
5. **Cost alerts**: Hard limits that terminate, or just warnings?
