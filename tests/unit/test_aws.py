"""Unit tests for AWS components."""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from pms.aws.models import (
    DeploymentConfig,
    NetworkEnvironment,
    NetworkTestConfig,
    RemoteTestConfig,
    RemoteTestResult,
    SecurityGroupRule,
    ServerState,
    SpotOption,
    SpotQuery,
    SpotServer,
    SpotServerConfig,
)


class TestSpotOption:
    """Tests for SpotOption dataclass."""

    def test_create_spot_option(self) -> None:
        """Test creating a valid spot option."""
        option = SpotOption(
            instance_type="t3.medium",
            availability_zone="us-east-1a",
            current_price=Decimal("0.0125"),
            interruption_rate=0.05,
            vcpus=2,
            memory_gb=4.0,
            score=0.95,
        )
        assert option.instance_type == "t3.medium"
        assert option.availability_zone == "us-east-1a"
        assert option.current_price == Decimal("0.0125")
        assert option.interruption_rate == 0.05
        assert option.vcpus == 2
        assert option.memory_gb == 4.0
        assert option.score == 0.95

    def test_invalid_interruption_rate(self) -> None:
        """Test that invalid interruption rate raises error."""
        with pytest.raises(ValueError, match="interruption_rate must be between"):
            SpotOption(
                instance_type="t3.medium",
                availability_zone="us-east-1a",
                current_price=Decimal("0.01"),
                interruption_rate=1.5,  # Invalid
                vcpus=2,
                memory_gb=4.0,
                score=0.9,
            )

    def test_invalid_score(self) -> None:
        """Test that negative score raises error."""
        with pytest.raises(ValueError, match="score must be non-negative"):
            SpotOption(
                instance_type="t3.medium",
                availability_zone="us-east-1a",
                current_price=Decimal("0.01"),
                interruption_rate=0.1,
                vcpus=2,
                memory_gb=4.0,
                score=-0.5,  # Invalid
            )


class TestSpotQuery:
    """Tests for SpotQuery dataclass."""

    def test_default_query(self) -> None:
        """Test default spot query values."""
        query = SpotQuery()
        assert query.min_vcpus == 2
        assert query.min_memory_gb == 4.0
        assert query.max_price_per_hour == Decimal("0.10")
        assert query.regions == ("us-east-1", "us-west-2")
        assert query.architecture == "x86_64"
        assert query.prefer_low_interruption is True

    def test_custom_query(self) -> None:
        """Test custom spot query."""
        query = SpotQuery(
            min_vcpus=4,
            min_memory_gb=8.0,
            max_price_per_hour=Decimal("0.05"),
            regions=("eu-west-1",),
            architecture="arm64",
            prefer_low_interruption=False,
        )
        assert query.min_vcpus == 4
        assert query.min_memory_gb == 8.0
        assert query.architecture == "arm64"

    def test_invalid_vcpus(self) -> None:
        """Test that invalid vcpus raises error."""
        with pytest.raises(ValueError, match="min_vcpus must be at least"):
            SpotQuery(min_vcpus=0)

    def test_invalid_memory(self) -> None:
        """Test that invalid memory raises error."""
        with pytest.raises(ValueError, match="min_memory_gb must be at least"):
            SpotQuery(min_memory_gb=0.1)


class TestSpotServerConfig:
    """Tests for SpotServerConfig dataclass."""

    def test_basic_config(self) -> None:
        """Test basic server configuration."""
        config = SpotServerConfig(
            name="mytest",
            instance_type="t3.medium",
        )
        assert config.name == "mytest"
        assert config.instance_type == "t3.medium"
        assert config.availability_zone is None
        assert config.max_runtime_hours == 4.0
        assert config.idle_terminate_minutes == 30
        assert config.python_version == "3.12"
        assert config.install_docker is False

    def test_full_config(self) -> None:
        """Test full server configuration."""
        config = SpotServerConfig(
            name="prodtest",
            instance_type="c5.large",
            availability_zone="us-west-2a",
            ami_id="ami-12345",
            key_name="my-key",
            security_group_ids=("sg-123", "sg-456"),
            root_volume_gb=50,
            spot_max_price=Decimal("0.05"),
            max_runtime_hours=2.0,
            idle_terminate_minutes=15,
            python_version="3.11",
            install_docker=True,
            project_id="proj-123",
            tags=(("env", "test"), ("team", "backend")),
        )
        assert config.availability_zone == "us-west-2a"
        assert config.root_volume_gb == 50
        assert config.spot_max_price == Decimal("0.05")
        assert config.install_docker is True
        assert len(config.tags) == 2

    def test_invalid_max_runtime(self) -> None:
        """Test that invalid max runtime raises error."""
        with pytest.raises(ValueError, match="max_runtime_hours must be positive"):
            SpotServerConfig(
                name="test",
                instance_type="t3.medium",
                max_runtime_hours=0,
            )

    def test_invalid_idle_timeout(self) -> None:
        """Test that negative idle timeout raises error."""
        with pytest.raises(
            ValueError, match="idle_terminate_minutes must be non-negative"
        ):
            SpotServerConfig(
                name="test",
                instance_type="t3.medium",
                idle_terminate_minutes=-10,
            )

    def test_invalid_volume_size(self) -> None:
        """Test that small volume size raises error."""
        with pytest.raises(ValueError, match="root_volume_gb must be at least"):
            SpotServerConfig(
                name="test",
                instance_type="t3.medium",
                root_volume_gb=5,
            )


class TestSpotServer:
    """Tests for SpotServer dataclass."""

    def test_create_server(self) -> None:
        """Test creating a test server."""
        config = SpotServerConfig(
            name="mytest",
            instance_type="t3.medium",
        )
        now = datetime.now(UTC)
        server = SpotServer(
            id="srv-123",
            instance_id="i-abc123",
            name="mytest",
            config=config,
            state=ServerState.RUNNING,
            launched_at=now,
            region="us-east-1",
            availability_zone="us-east-1a",
            public_ip="54.1.2.3",
            private_ip="10.0.0.1",
            hourly_price=Decimal("0.012"),
        )
        assert server.id == "srv-123"
        assert server.instance_id == "i-abc123"
        assert server.state == ServerState.RUNNING
        assert server.public_ip == "54.1.2.3"
        assert server.is_active is True

    def test_ssh_command(self) -> None:
        """Test SSH command generation."""
        config = SpotServerConfig(
            name="mytest",
            instance_type="t3.medium",
            key_name="my-key",
        )
        server = SpotServer(
            id="srv-123",
            instance_id="i-abc123",
            name="mytest",
            config=config,
            state=ServerState.RUNNING,
            launched_at=datetime.now(UTC),
            region="us-east-1",
            availability_zone="us-east-1a",
            public_ip="54.1.2.3",
        )
        ssh_cmd = server.ssh_command
        assert ssh_cmd is not None
        assert "ec2-user@54.1.2.3" in ssh_cmd

    def test_ssh_command_no_ip(self) -> None:
        """Test SSH command when no IP available."""
        config = SpotServerConfig(
            name="mytest",
            instance_type="t3.medium",
        )
        server = SpotServer(
            id="srv-123",
            instance_id="i-abc123",
            name="mytest",
            config=config,
            state=ServerState.PENDING,
            launched_at=datetime.now(UTC),
            region="us-east-1",
            availability_zone="us-east-1a",
        )
        assert server.ssh_command is None

    def test_is_active(self) -> None:
        """Test is_active property for different states."""
        config = SpotServerConfig(name="test", instance_type="t3.medium")
        base_args = {
            "id": "srv-123",
            "instance_id": "i-abc",
            "name": "test",
            "config": config,
            "launched_at": datetime.now(UTC),
            "region": "us-east-1",
            "availability_zone": "us-east-1a",
        }

        # Active states
        for state in [ServerState.PENDING, ServerState.RUNNING]:
            server = SpotServer(**base_args, state=state)
            assert server.is_active is True

        # Inactive states
        for state in [
            ServerState.STOPPING,
            ServerState.TERMINATED,
            ServerState.INTERRUPTED,
        ]:
            server = SpotServer(**base_args, state=state)
            assert server.is_active is False


class TestRemoteTestConfig:
    """Tests for RemoteTestConfig dataclass."""

    def test_basic_config(self) -> None:
        """Test basic test run config."""
        config = RemoteTestConfig(
            server_id="srv-123",
            project_path=Path("/home/user/project"),
        )
        assert config.server_id == "srv-123"
        assert config.test_command == "pytest"
        assert config.remote_path == "/home/ec2-user/project"
        assert config.timeout == 600.0
        assert config.stream_output is True
        assert ".git" in config.exclude_patterns
        assert "__pycache__" in config.exclude_patterns

    def test_custom_config(self) -> None:
        """Test custom test run config."""
        config = RemoteTestConfig(
            server_id="srv-456",
            project_path=Path("/app"),
            remote_path="/var/www/app",
            test_command="pytest -v --cov",
            setup_command="pip install -r requirements.txt",
            working_dir="tests",
            env_vars=(("DEBUG", "1"), ("API_KEY", "test")),
            timeout=300.0,
            stream_output=False,
            capture_logs=("/var/log/app.log",),
            save_artifacts=("coverage.xml",),
        )
        assert config.test_command == "pytest -v --cov"
        assert config.setup_command == "pip install -r requirements.txt"
        assert len(config.env_vars) == 2


class TestRemoteTestResult:
    """Tests for RemoteTestResult dataclass."""

    def test_successful_result(self) -> None:
        """Test successful test result."""
        now = datetime.now(UTC)
        result = RemoteTestResult(
            run_id="run-123",
            server_id="srv-456",
            success=True,
            exit_code=0,
            stdout="All tests passed",
            stderr="",
            duration_seconds=12.5,
            started_at=now,
            finished_at=now,
        )
        assert result.success is True
        assert result.exit_code == 0
        assert "PASSED" in result.summary
        assert "12.5s" in result.summary

    def test_failed_result(self) -> None:
        """Test failed test result."""
        now = datetime.now(UTC)
        result = RemoteTestResult(
            run_id="run-789",
            server_id="srv-456",
            success=False,
            exit_code=1,
            stdout="",
            stderr="AssertionError",
            duration_seconds=5.0,
            started_at=now,
            finished_at=now,
        )
        assert result.success is False
        assert "FAILED" in result.summary

    def test_result_with_logs(self) -> None:
        """Test result with captured logs."""
        now = datetime.now(UTC)
        result = RemoteTestResult(
            run_id="run-123",
            server_id="srv-456",
            success=True,
            exit_code=0,
            stdout="OK",
            stderr="",
            duration_seconds=1.0,
            started_at=now,
            finished_at=now,
            logs={"/var/log/app.log": "Log content here"},
            artifacts={"/output/report.html": Path("/tmp/report.html")},
        )
        assert "/var/log/app.log" in result.logs
        assert "/output/report.html" in result.artifacts


class TestSecurityGroupRule:
    """Tests for SecurityGroupRule dataclass."""

    def test_basic_rule(self) -> None:
        """Test basic security group rule."""
        rule = SecurityGroupRule(
            from_role="web",
            to_role="db",
            port=5432,
        )
        assert rule.from_role == "web"
        assert rule.to_role == "db"
        assert rule.port == 5432
        assert rule.protocol == "tcp"

    def test_custom_rule(self) -> None:
        """Test custom security group rule."""
        rule = SecurityGroupRule(
            from_role="app",
            to_role="cache",
            port=6379,
            protocol="tcp",
            description="Redis access",
        )
        assert rule.description == "Redis access"


class TestDeploymentConfig:
    """Tests for DeploymentConfig dataclass."""

    def test_basic_deployment(self) -> None:
        """Test basic deployment config."""
        config = DeploymentConfig(
            project_path=Path("/app"),
        )
        assert config.remote_path == "/home/ec2-user/project"
        assert config.health_check_timeout == 60.0

    def test_full_deployment(self) -> None:
        """Test full deployment config."""
        config = DeploymentConfig(
            project_path=Path("/web"),
            remote_path="/var/www/html",
            setup_command="npm install",
            start_command="npm start",
            health_check="curl -f localhost:3000/health",
            health_check_timeout=120.0,
            exclude_patterns=(".git", "node_modules", "coverage"),
        )
        assert config.setup_command == "npm install"
        assert config.start_command == "npm start"


class TestNetworkTestConfig:
    """Tests for NetworkTestConfig dataclass."""

    def test_basic_config(self) -> None:
        """Test basic network test config."""
        web_config = SpotServerConfig(name="web", instance_type="t3.medium")
        db_config = SpotServerConfig(name="db", instance_type="t3.small")

        config = NetworkTestConfig(
            name="my-env",
            servers=(("web", web_config), ("db", db_config)),
        )
        assert config.name == "my-env"
        assert len(config.servers) == 2
        assert config.max_runtime_hours == 2.0
        assert config.auto_destroy is True

    def test_get_server_config(self) -> None:
        """Test getting server config by role."""
        web_config = SpotServerConfig(name="web", instance_type="t3.medium")
        config = NetworkTestConfig(
            name="test",
            servers=(("web", web_config),),
        )
        assert config.get_server_config("web") == web_config
        assert config.get_server_config("unknown") is None


class TestNetworkEnvironment:
    """Tests for NetworkEnvironment dataclass."""

    def test_create_environment(self) -> None:
        """Test creating a network environment."""
        web_config = SpotServerConfig(name="web", instance_type="t3.medium")
        config = NetworkTestConfig(
            name="my-env",
            servers=(("web", web_config),),
        )

        server = SpotServer(
            id="srv-1",
            instance_id="i-123",
            name="web",
            config=web_config,
            state=ServerState.RUNNING,
            launched_at=datetime.now(UTC),
            region="us-east-1",
            availability_zone="us-east-1a",
            hourly_price=Decimal("0.01"),
        )

        env = NetworkEnvironment(
            id="env-123",
            name="my-env",
            config=config,
            state=ServerState.RUNNING,
            servers={"web": server},
            security_group_id="sg-abc",
        )

        assert env.is_active is True
        assert env.all_servers_running is True
        assert env.total_hourly_cost == Decimal("0.01")

    def test_inactive_environment(self) -> None:
        """Test inactive environment."""
        config = NetworkTestConfig(
            name="test",
            servers=(),
        )
        env = NetworkEnvironment(
            id="env-1",
            name="test",
            config=config,
            state=ServerState.TERMINATED,
            servers={},
        )
        assert env.is_active is False


class SpotServerState:
    """Tests for ServerState enum."""

    def test_all_states(self) -> None:
        """Test all server states are defined."""
        states = [
            ServerState.PENDING,
            ServerState.RUNNING,
            ServerState.STOPPING,
            ServerState.TERMINATED,
            ServerState.INTERRUPTED,
        ]
        assert len(states) == 5
        assert ServerState.PENDING.value == "pending"
        assert ServerState.INTERRUPTED.value == "interrupted"
