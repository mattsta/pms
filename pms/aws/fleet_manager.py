"""FleetManager - EC2 spot instance lifecycle management."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pms.aws.models import ServerState, SpotServer, SpotServerConfig
from pms.core.events import (
    DomainEvent,
    EventMetadata,
    EventType,
    ServerLaunchedPayload,
    ServerLaunchingPayload,
    ServerTerminatedPayload,
)
from pms.models import HostType
from pms.utils.money import monetary_string

if TYPE_CHECKING:
    from mypy_boto3_ec2 import EC2Client

    from pms.core.events import EventStore
    from pms.core.metrics import MetricsCollector
    from pms.db.connection import Database
    from pms.services.remote_service import RemoteService
else:
    EC2Client = Any


# Default Amazon Linux 2023 AMIs by region (updated periodically)
DEFAULT_AMIS: dict[str, str] = {
    "us-east-1": "ami-0c7217cdde317cfec",
    "us-east-2": "ami-05fb0b8c1424f266b",
    "us-west-1": "ami-0ce2cb35386fc22e9",
    "us-west-2": "ami-008fe2fc65df48dac",
    "eu-west-1": "ami-0905a3c97561e0b69",
    "eu-central-1": "ami-0faab6bdbac9486fb",
    "ap-northeast-1": "ami-0310b105770df9334",
    "ap-southeast-1": "ami-0464f90f5928bccb8",
}

# Default user data script to set up the instance
DEFAULT_USER_DATA = """#!/bin/bash
set -e

# Update system
yum update -y

# Install essential tools
yum install -y git gcc make openssl-devel bzip2-devel libffi-devel zlib-devel

# Install Python {python_version}
amazon-linux-extras install python3.{python_minor} -y || true
yum install -y python3.{python_minor} python3.{python_minor}-pip python3.{python_minor}-devel || true

# Set up Python alternatives
update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.{python_minor} 1 || true

# Install pip and common tools
python3 -m pip install --upgrade pip
python3 -m pip install uv pytest

# Create project directory
mkdir -p /home/ec2-user/project
chown ec2-user:ec2-user /home/ec2-user/project

{docker_setup}

# Signal completion
touch /home/ec2-user/.setup-complete
"""

DOCKER_SETUP = """
# Install Docker
yum install -y docker
systemctl start docker
systemctl enable docker
usermod -aG docker ec2-user
"""


class FleetManager:
    """Manage EC2 spot instance fleet for testing.

    Handles:
    - Instance launching with spot requests
    - Instance termination
    - Auto-termination (max runtime, idle timeout)
    - Cost tracking
    - Registration with RemoteService for SSH/rsync
    """

    def __init__(
        self,
        db: Database,
        event_store: EventStore,
        metrics: MetricsCollector,
        remote_service: RemoteService,
        ec2_client: EC2Client,
        region: str,
        key_dir: Path | None = None,
    ) -> None:
        """Initialize FleetManager.

        Args:
            db: Database connection
            event_store: Event store for audit trail
            metrics: Metrics collector
            remote_service: Remote service for SSH registration
            ec2_client: Boto3 EC2 client
            region: AWS region
            key_dir: Directory to store SSH keys (default: ~/.pms/keys)
        """
        self.db = db
        self.events = event_store
        self.metrics = metrics
        self.remote = remote_service
        self._ec2 = ec2_client
        self._region = region
        self._key_dir = key_dir or Path.home() / ".pms" / "keys"
        self._key_dir.mkdir(parents=True, exist_ok=True)

        # In-memory server cache
        self._servers: dict[str, SpotServer] = {}

        # Background task handle
        self._monitor_task: asyncio.Task[Any] | None = None

    async def launch_server(
        self,
        config: SpotServerConfig,
        wait_for_ready: bool = True,
        timeout: float = 300.0,
    ) -> SpotServer:
        """Launch a spot instance test server.

        Args:
            config: Server configuration
            wait_for_ready: Wait for instance to be SSH-ready
            timeout: Timeout for waiting (seconds)

        Returns:
            SpotServer instance

        Raises:
            RuntimeError: If launch fails
        """
        server_id = str(uuid.uuid4())
        now = datetime.now(UTC)

        # Determine AZ
        az = config.availability_zone
        if not az:
            # Use first AZ in region
            azs = await self._get_availability_zones()
            az = azs[0] if azs else f"{self._region}a"

        # Emit launching event
        await self.events.append(
            DomainEvent(
                event_type=EventType.SERVER_LAUNCHING,
                aggregate_type="test_server",
                aggregate_id=server_id,
                payload=ServerLaunchingPayload(
                    name=config.name,
                    instance_type=config.instance_type,
                    region=self._region,
                    availability_zone=az,
                    config_json=json.dumps(
                        {
                            "instance_type": config.instance_type,
                            "max_runtime_hours": config.max_runtime_hours,
                            "idle_terminate_minutes": config.idle_terminate_minutes,
                            "project_id": config.project_id,
                        }
                    ),
                ),
                metadata=EventMetadata(source="fleet_manager"),
            )
        )

        # Create or use existing key pair
        key_name = config.key_name or f"pms-{config.name}-{server_id[:8]}"
        key_path = await self._ensure_key_pair(key_name)

        # Get or create security group
        sg_ids = list(config.security_group_ids)
        if not sg_ids:
            sg_id = await self._ensure_default_security_group()
            sg_ids = [sg_id]

        # Get AMI
        ami_id = config.ami_id or DEFAULT_AMIS.get(self._region)
        if not ami_id:
            raise RuntimeError(f"No default AMI for region {self._region}")

        # Build user data
        python_minor = (
            config.python_version.split(".")[-1]
            if "." in config.python_version
            else "12"
        )
        user_data = DEFAULT_USER_DATA.format(
            python_version=config.python_version,
            python_minor=python_minor,
            docker_setup=DOCKER_SETUP if config.install_docker else "",
        )
        if config.user_data:
            user_data += f"\n{config.user_data}"

        # Build tags
        tags = [
            {"Key": "Name", "Value": f"pms-{config.name}"},
            {"Key": "pms-server-id", "Value": server_id},
            {"Key": "pms-managed", "Value": "true"},
        ]
        for key, value in config.tags:
            tags.append({"Key": key, "Value": value})
        if config.project_id:
            tags.append({"Key": "pms-project-id", "Value": config.project_id})

        # Launch spot instance
        loop = asyncio.get_event_loop()
        try:
            response = await loop.run_in_executor(
                None,
                lambda: self._ec2.run_instances(
                    ImageId=ami_id,
                    InstanceType=config.instance_type,  # type: ignore[arg-type]
                    MinCount=1,
                    MaxCount=1,
                    KeyName=key_name,
                    SecurityGroupIds=sg_ids,
                    SubnetId=config.subnet_id,  # type: ignore[arg-type]
                    UserData=base64.b64encode(user_data.encode()).decode(),
                    InstanceMarketOptions={
                        "MarketType": "spot",
                        "SpotOptions": {
                            "SpotInstanceType": "one-time",
                            "InstanceInterruptionBehavior": "terminate",
                            **(
                                {"MaxPrice": str(config.spot_max_price)}
                                if config.spot_max_price
                                else {}
                            ),
                        },
                    },
                    BlockDeviceMappings=[
                        {
                            "DeviceName": "/dev/xvda",
                            "Ebs": {
                                "VolumeSize": config.root_volume_gb,
                                "VolumeType": "gp3",
                                "DeleteOnTermination": True,
                            },
                        },
                    ],
                    TagSpecifications=[
                        {"ResourceType": "instance", "Tags": tags},  # type: ignore[list-item,misc]
                    ],
                ),
            )
        except Exception as e:
            raise RuntimeError(f"Failed to launch instance: {e}") from e

        instance = response["Instances"][0]
        instance_id = instance["InstanceId"]

        # Get spot price
        try:
            price_response = await loop.run_in_executor(
                None,
                lambda: self._ec2.describe_spot_price_history(
                    InstanceTypes=[config.instance_type],  # type: ignore[list-item]
                    ProductDescriptions=["Linux/UNIX"],
                    AvailabilityZone=az,
                    MaxResults=1,
                ),
            )
            hourly_price = Decimal(
                price_response["SpotPriceHistory"][0]["SpotPrice"]
                if price_response["SpotPriceHistory"]
                else "0"
            )
        except Exception:
            hourly_price = Decimal(0)

        # Create server object
        server = SpotServer(
            id=server_id,
            instance_id=instance_id,
            name=config.name,
            config=config,
            state=ServerState.PENDING,
            launched_at=now,
            region=self._region,
            availability_zone=az,
            hourly_price=hourly_price,
            last_activity=now,
        )

        # Store in database
        await self._store_server(server)
        self._servers[server_id] = server

        # Wait for running state and get IPs
        if wait_for_ready:
            server = await self._wait_for_running(server, timeout)
            await self._update_server(server)

            # Emit launched event
            await self.events.append(
                DomainEvent(
                    event_type=EventType.SERVER_LAUNCHED,
                    aggregate_type="test_server",
                    aggregate_id=server_id,
                    payload=ServerLaunchedPayload(
                        instance_id=instance_id,
                        public_ip=server.public_ip,
                        private_ip=server.private_ip,
                        hourly_price=monetary_string(server.hourly_price) or "0",
                    ),
                    metadata=EventMetadata(source="fleet_manager"),
                )
            )

            # Register with RemoteService
            await self.remote.add_host(
                name=f"aws-{config.name}",
                host=server.public_ip or "",
                username="ec2-user",
                port=22,
                key_path=str(key_path),
                host_type=HostType.AWS_EC2,
                aws_instance_id=instance_id,
                aws_region=self._region,
                default_remote_path="/home/ec2-user/project",
                tags=["aws", "spot", "pms-managed"],
            )

            # Wait for SSH and setup completion
            if wait_for_ready:
                await self._wait_for_ssh_ready(server, timeout)
                await self._run_setup_commands(server, config.setup_commands)

        await self.metrics.record_counter(
            "aws.server_launched",
            labels={"region": self._region, "instance_type": config.instance_type},
        )
        await self.metrics.flush_best_effort(context="aws.fleet.launch_server")

        return server

    async def terminate_server(
        self,
        server_id: str,
        reason: str = "user_request",
    ) -> bool:
        """Terminate a test server.

        Args:
            server_id: Server ID to terminate
            reason: Reason for termination

        Returns:
            True if terminated
        """
        server = await self.get_server(server_id)
        if server is None:
            return False

        if server.state == ServerState.TERMINATED:
            return True

        # Terminate instance
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(
                None,
                lambda: self._ec2.terminate_instances(InstanceIds=[server.instance_id]),
            )
        except Exception as e:
            raise RuntimeError(f"Failed to terminate instance: {e}") from e

        # Calculate runtime and cost
        runtime_hours = (datetime.now(UTC) - server.launched_at).total_seconds() / 3600
        total_cost = server.hourly_price * Decimal(str(runtime_hours))

        # Update state
        server.state = ServerState.TERMINATED
        server.terminated_at = datetime.now(UTC)
        server.estimated_cost = total_cost
        await self._update_server(server)

        # Emit terminated event
        await self.events.append(
            DomainEvent(
                event_type=EventType.SERVER_TERMINATED,
                aggregate_type="test_server",
                aggregate_id=server_id,
                payload=ServerTerminatedPayload(
                    reason=reason,
                    total_runtime_hours=runtime_hours,
                    total_cost=monetary_string(total_cost) or "0",
                ),
                metadata=EventMetadata(source="fleet_manager"),
            )
        )

        # Remove from RemoteService
        with contextlib.suppress(Exception):
            await self.remote.delete_host(f"aws-{server.name}")

        await self.metrics.record_counter(
            "aws.server_terminated",
            labels={"region": self._region, "reason": reason},
        )
        await self.metrics.record_gauge(
            "aws.server_cost",
            float(total_cost),
            labels={"server_id": server_id},
        )
        await self.metrics.flush_best_effort(context="aws.fleet.terminate_server")

        return True

    async def terminate_all(
        self,
        project_id: str | None = None,
        reason: str = "batch_terminate",
    ) -> int:
        """Terminate all servers, optionally filtered by project.

        Args:
            project_id: Optional project ID filter
            reason: Reason for termination

        Returns:
            Number of servers terminated
        """
        servers = await self.list_servers(
            state=None,  # All states
            project_id=project_id,
        )

        count = 0
        for server in servers:
            if server.is_active and await self.terminate_server(server.id, reason):
                count += 1

        return count

    async def get_server(self, server_id: str) -> SpotServer | None:
        """Get server by ID.

        Args:
            server_id: Server ID

        Returns:
            SpotServer or None
        """
        if server_id in self._servers:
            return self._servers[server_id]

        row = await self.db.fetch_one(
            "SELECT * FROM test_servers WHERE id = ?",
            (server_id,),
        )
        if row is None:
            return None

        server = self._server_from_row(row)
        self._servers[server_id] = server
        return server

    async def list_servers(
        self,
        state: ServerState | None = None,
        project_id: str | None = None,
    ) -> list[SpotServer]:
        """List all servers with optional filtering.

        Args:
            state: Filter by state (None = all except terminated)
            project_id: Filter by project ID

        Returns:
            List of servers
        """
        query = "SELECT * FROM test_servers WHERE 1=1"
        params: list[str] = []

        if state is not None:
            query += " AND state = ?"
            params.append(state.value)
        else:
            # By default, exclude terminated
            query += " AND state != ?"
            params.append(ServerState.TERMINATED.value)

        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)

        query += " ORDER BY launched_at DESC"

        rows = await self.db.fetch_all(query, tuple(params))
        return [self._server_from_row(row) for row in rows]

    async def refresh_state(self, server_id: str) -> SpotServer | None:
        """Refresh server state from AWS.

        Args:
            server_id: Server ID

        Returns:
            Updated SpotServer or None
        """
        server = await self.get_server(server_id)
        if server is None:
            return None

        loop = asyncio.get_event_loop()
        try:
            response = await loop.run_in_executor(
                None,
                lambda: self._ec2.describe_instances(InstanceIds=[server.instance_id]),
            )
        except Exception:
            return server

        if not response["Reservations"]:
            return server

        instance = response["Reservations"][0]["Instances"][0]
        aws_state = instance["State"]["Name"]

        # Map AWS state to our state
        state_map = {
            "pending": ServerState.PENDING,
            "running": ServerState.RUNNING,
            "shutting-down": ServerState.STOPPING,
            "terminated": ServerState.TERMINATED,
            "stopping": ServerState.STOPPING,
            "stopped": ServerState.TERMINATED,
        }
        server.state = state_map.get(aws_state, server.state)
        server.public_ip = instance.get("PublicIpAddress")
        server.private_ip = instance.get("PrivateIpAddress")
        server.public_dns = instance.get("PublicDnsName")

        await self._update_server(server)
        return server

    async def record_activity(self, server_id: str) -> None:
        """Record activity on a server (resets idle timer).

        Args:
            server_id: Server ID
        """
        server = await self.get_server(server_id)
        if server:
            server.last_activity = datetime.now(UTC)
            await self._update_server(server)

    async def start_monitors(self) -> None:
        """Start background monitoring tasks."""
        if self._monitor_task is None or self._monitor_task.done():
            self._monitor_task = asyncio.create_task(self._monitor_loop())

    async def stop_monitors(self) -> None:
        """Stop background monitoring tasks."""
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._monitor_task

    async def _monitor_loop(self) -> None:
        """Background loop for auto-termination and cost tracking."""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute

                servers = await self.list_servers()
                now = datetime.now(UTC)

                for server in servers:
                    if not server.is_active:
                        continue

                    # Check max runtime
                    runtime_hours = (now - server.launched_at).total_seconds() / 3600
                    if runtime_hours >= server.config.max_runtime_hours:
                        await self.terminate_server(server.id, "max_runtime_exceeded")
                        continue

                    # Check idle timeout
                    if server.last_activity:
                        idle_minutes = (now - server.last_activity).total_seconds() / 60
                        if idle_minutes >= server.config.idle_terminate_minutes:
                            await self.terminate_server(server.id, "idle_timeout")
                            continue

                    # Update cost estimate
                    server.estimated_cost = server.hourly_price * Decimal(
                        str(runtime_hours)
                    )
                    await self._update_server(server)

            except asyncio.CancelledError:
                break
            except Exception:
                pass  # Continue monitoring even on errors

    async def _get_availability_zones(self) -> list[str]:
        """Get available AZs in current region."""
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self._ec2.describe_availability_zones(
                Filters=[{"Name": "state", "Values": ["available"]}]
            ),
        )
        return [az["ZoneName"] for az in response["AvailabilityZones"]]

    async def _ensure_key_pair(self, key_name: str) -> Path:
        """Ensure SSH key pair exists, create if needed.

        Args:
            key_name: Name of the key pair

        Returns:
            Path to private key file
        """
        key_path = self._key_dir / f"{key_name}.pem"

        # Check if key already exists locally
        if key_path.exists():
            return key_path

        # Check if key exists in AWS
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(
                None,
                lambda: self._ec2.describe_key_pairs(KeyNames=[key_name]),
            )
            # Key exists in AWS but not locally - can't proceed
            raise RuntimeError(
                f"Key pair '{key_name}' exists in AWS but local key not found at {key_path}"
            )
        except self._ec2.exceptions.ClientError as e:
            if "InvalidKeyPair.NotFound" not in str(e):
                raise

        # Create new key pair
        response = await loop.run_in_executor(
            None,
            lambda: self._ec2.create_key_pair(KeyName=key_name),
        )

        # Save private key
        key_path.write_text(response["KeyMaterial"])
        key_path.chmod(0o600)

        return key_path

    async def _ensure_default_security_group(self) -> str:
        """Ensure default PMS security group exists.

        Returns:
            Security group ID
        """
        sg_name = "pms-test-servers"

        loop = asyncio.get_event_loop()

        # Check if exists
        try:
            response = await loop.run_in_executor(
                None,
                lambda: self._ec2.describe_security_groups(GroupNames=[sg_name]),
            )
            return str(response["SecurityGroups"][0]["GroupId"])
        except Exception:
            pass

        # Create security group
        try:
            create_response = await loop.run_in_executor(
                None,
                lambda: self._ec2.create_security_group(
                    GroupName=sg_name,
                    Description="Security group for PMS test servers",
                ),
            )
            sg_id: str = str(create_response["GroupId"])

            # Add SSH rule - restrict to user's current IP for security
            # Get user's public IP (falls back to localhost if detection fails)
            try:
                import urllib.request

                user_ip = (
                    urllib.request.urlopen("https://api.ipify.org", timeout=5)
                    .read()
                    .decode("utf8")
                )
                ssh_cidr = f"{user_ip}/32"
                description = f"SSH access from {user_ip}"
            except Exception:
                # Fallback to localhost only if IP detection fails
                ssh_cidr = "127.0.0.1/32"
                description = "SSH access from localhost only"

            await loop.run_in_executor(
                None,
                lambda: self._ec2.authorize_security_group_ingress(
                    GroupId=sg_id,
                    IpPermissions=[
                        {
                            "IpProtocol": "tcp",
                            "FromPort": 22,
                            "ToPort": 22,
                            "IpRanges": [
                                {"CidrIp": ssh_cidr, "Description": description}
                            ],
                        },
                    ],
                ),
            )

            return sg_id
        except Exception as e:
            raise RuntimeError(f"Failed to create security group: {e}") from e

    async def _wait_for_running(
        self, server: SpotServer, timeout: float = 300.0
    ) -> SpotServer:
        """Wait for instance to be in running state.

        Args:
            server: Server to wait for
            timeout: Timeout in seconds

        Returns:
            Updated server with IPs
        """
        loop = asyncio.get_event_loop()
        start_time = datetime.now(UTC)

        while True:
            elapsed = (datetime.now(UTC) - start_time).total_seconds()
            if elapsed > timeout:
                raise RuntimeError(
                    f"Timeout waiting for instance {server.instance_id} to start"
                )

            try:
                response = await loop.run_in_executor(
                    None,
                    lambda: self._ec2.describe_instances(
                        InstanceIds=[server.instance_id]
                    ),
                )
                instance = response["Reservations"][0]["Instances"][0]
                state = instance["State"]["Name"]

                if state == "running":
                    server.state = ServerState.RUNNING
                    server.public_ip = instance.get("PublicIpAddress")
                    server.private_ip = instance.get("PrivateIpAddress")
                    server.public_dns = instance.get("PublicDnsName")
                    return server

                if state in ("terminated", "shutting-down"):
                    raise RuntimeError(
                        f"Instance {server.instance_id} terminated unexpectedly"
                    )

            except Exception as e:
                if "terminated" in str(e).lower():
                    raise

            await asyncio.sleep(5)

    async def _wait_for_ssh_ready(self, server: SpotServer, timeout: float) -> None:
        """Wait for SSH to be accessible and setup complete.

        Args:
            server: Server to wait for
            timeout: Timeout in seconds
        """
        from pms.utils.ssh import SSHConfig, test_connection

        if not server.public_ip:
            raise RuntimeError("Server has no public IP")

        key_path = (
            self._key_dir / f"{server.config.key_name or f'pms-{server.name}'}.pem"
        )
        config = SSHConfig(
            host=server.public_ip,
            username="ec2-user",
            port=22,
            private_key_path=key_path,
        )

        start_time = datetime.now(UTC)
        while True:
            elapsed = (datetime.now(UTC) - start_time).total_seconds()
            if elapsed > timeout:
                raise RuntimeError(f"Timeout waiting for SSH on {server.public_ip}")

            success, _ = await test_connection(config)
            if success:
                # Also check if setup is complete
                try:
                    result = await self.remote.execute_command(
                        f"aws-{server.name}",
                        "test -f /home/ec2-user/.setup-complete && echo 'ready'",
                        timeout=10,
                    )
                    if result.success and "ready" in result.stdout:
                        return
                except Exception:
                    pass

            await asyncio.sleep(10)

    async def _run_setup_commands(
        self,
        server: SpotServer,
        commands: tuple[str, ...],
    ) -> None:
        """Run setup commands on server.

        Args:
            server: Server to run commands on
            commands: Commands to run
        """
        for command in commands:
            result = await self.remote.execute_command(
                f"aws-{server.name}",
                command,
                timeout=300,
            )
            if not result.success:
                raise RuntimeError(f"Setup command failed: {command}\n{result.stderr}")

    async def _store_server(self, server: SpotServer) -> None:
        """Store server in database."""
        await self.db.execute(
            """
            INSERT INTO test_servers (
                id, instance_id, name, project_id, config,
                public_ip, private_ip, state, region, availability_zone,
                hourly_price, estimated_cost, launched_at, last_activity
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                server.id,
                server.instance_id,
                server.name,
                server.config.project_id,
                json.dumps(
                    {
                        "instance_type": server.config.instance_type,
                        "max_runtime_hours": server.config.max_runtime_hours,
                        "idle_terminate_minutes": server.config.idle_terminate_minutes,
                        "root_volume_gb": server.config.root_volume_gb,
                    }
                ),
                server.public_ip,
                server.private_ip,
                server.state.value,
                server.region,
                server.availability_zone,
                float(server.hourly_price),
                float(server.estimated_cost),
                server.launched_at.isoformat(),
                server.last_activity.isoformat() if server.last_activity else None,
            ),
        )
        await self.db.commit()

    async def _update_server(self, server: SpotServer) -> None:
        """Update server in database."""
        await self.db.execute(
            """
            UPDATE test_servers SET
                public_ip = ?, private_ip = ?, state = ?,
                hourly_price = ?, estimated_cost = ?,
                last_activity = ?, terminated_at = ?
            WHERE id = ?
            """,
            (
                server.public_ip,
                server.private_ip,
                server.state.value,
                float(server.hourly_price),
                float(server.estimated_cost),
                server.last_activity.isoformat() if server.last_activity else None,
                server.terminated_at.isoformat() if server.terminated_at else None,
                server.id,
            ),
        )
        await self.db.commit()
        self._servers[server.id] = server

    def _server_from_row(self, row: dict[str, Any]) -> SpotServer:
        """Convert database row to SpotServer."""
        config_data = json.loads(row.get("config", "{}"))

        config = SpotServerConfig(
            name=row["name"],
            instance_type=config_data.get("instance_type", "t3.medium"),
            max_runtime_hours=config_data.get("max_runtime_hours", 4.0),
            idle_terminate_minutes=config_data.get("idle_terminate_minutes", 30),
            root_volume_gb=config_data.get("root_volume_gb", 20),
            project_id=row.get("project_id"),
        )

        return SpotServer(
            id=row["id"],
            instance_id=row["instance_id"],
            name=row["name"],
            config=config,
            state=ServerState(row["state"]),
            launched_at=datetime.fromisoformat(row["launched_at"]),
            region=row["region"],
            availability_zone=row["availability_zone"],
            public_ip=row.get("public_ip"),
            private_ip=row.get("private_ip"),
            hourly_price=Decimal(str(row.get("hourly_price", 0))),
            estimated_cost=Decimal(str(row.get("estimated_cost", 0))),
            last_activity=datetime.fromisoformat(row["last_activity"])
            if row.get("last_activity")
            else None,
            terminated_at=datetime.fromisoformat(row["terminated_at"])
            if row.get("terminated_at")
            else None,
        )
