"""Agent tools for AWS operations (spot instances, test servers)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

from claude_code_sdk import tool

if TYPE_CHECKING:
    from pms.aws import FleetManager, SpotFinder, TestRunner

# Global service instances - set by server initialization
_spot_finder: SpotFinder | None = None
_fleet_manager: FleetManager | None = None
_test_runner: TestRunner | None = None


def set_aws_services(
    spot_finder: SpotFinder | None = None,
    fleet_manager: FleetManager | None = None,
    test_runner: TestRunner | None = None,
) -> None:
    """Set the AWS service instances for tools to use."""
    global _spot_finder, _fleet_manager, _test_runner
    if spot_finder is not None:
        _spot_finder = spot_finder
    if fleet_manager is not None:
        _fleet_manager = fleet_manager
    if test_runner is not None:
        _test_runner = test_runner


def _get_spot_finder() -> SpotFinder:
    """Get spot finder or raise if not initialized."""
    if _spot_finder is None:
        raise RuntimeError("SpotFinder not initialized. Call set_aws_services first.")
    return _spot_finder


def _get_fleet_manager() -> FleetManager:
    """Get fleet manager or raise if not initialized."""
    if _fleet_manager is None:
        raise RuntimeError("FleetManager not initialized. Call set_aws_services first.")
    return _fleet_manager


def _get_test_runner() -> TestRunner:
    """Get test runner or raise if not initialized."""
    if _test_runner is None:
        raise RuntimeError("TestRunner not initialized. Call set_aws_services first.")
    return _test_runner


# =============================================================================
# Spot Instance Tools
# =============================================================================


@tool(
    "find_spot_instances",
    "Find cost-effective AWS spot instances for testing",
    {
        "min_vcpus": int,
        "min_memory_gb": float,
        "max_price": str,
        "architecture": str,
        "limit": int,
    },
)
async def find_spot_instances(args: dict[str, Any]) -> dict[str, Any]:
    """Find cost-effective spot instances."""
    from pms.aws.models import SpotQuery

    finder = _get_spot_finder()

    query = SpotQuery(
        min_vcpus=args.get("min_vcpus", 2),
        min_memory_gb=args.get("min_memory_gb", 4.0),
        max_price_per_hour=Decimal(args.get("max_price", "0.10")),
        architecture=args.get("architecture", "x86_64"),
    )

    limit = args.get("limit", 5)
    options = await finder.find_best_options(query, limit=limit)

    if not options:
        return {
            "content": [
                {
                    "type": "text",
                    "text": "No spot instances found matching criteria.",
                }
            ]
        }

    lines = [f"Found {len(options)} spot instance options:"]
    for opt in options:
        lines.append(
            f"- {opt.instance_type} in {opt.availability_zone}: "
            f"${opt.current_price}/hr, {opt.vcpus} vCPUs, {opt.memory_gb}GB RAM, "
            f"{opt.interruption_rate * 100:.0f}% interrupt rate, score: {opt.score:.2f}"
        )

    return {
        "content": [
            {
                "type": "text",
                "text": "\n".join(lines),
            }
        ]
    }


# =============================================================================
# Test Server Tools
# =============================================================================


@tool(
    "launch_test_server",
    "Launch a spot instance test server",
    {
        "name": str,
        "instance_type": str,
        "max_hours": float,
        "idle_minutes": int,
        "install_docker": bool,
        "project_id": str,
    },
)
async def launch_test_server(args: dict[str, Any]) -> dict[str, Any]:
    """Launch a test server."""
    from pms.aws.models import SpotServerConfig

    fleet = _get_fleet_manager()

    config = SpotServerConfig(
        name=args["name"],
        instance_type=args.get("instance_type", "t3.medium"),
        max_runtime_hours=args.get("max_hours", 4.0),
        idle_terminate_minutes=args.get("idle_minutes", 30),
        install_docker=args.get("install_docker", False),
        project_id=args.get("project_id"),
    )

    try:
        server = await fleet.launch_server(config, wait_for_ready=True)

        ssh_cmd = (
            f"ssh ec2-user@{server.public_ip}" if server.public_ip else "IP pending"
        )

        return {
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"Launched test server '{server.name}'.\n"
                        f"ID: {server.id}\n"
                        f"Instance: {server.instance_id}\n"
                        f"State: {server.state.value}\n"
                        f"Public IP: {server.public_ip or 'pending'}\n"
                        f"SSH: {ssh_cmd}\n"
                        f"Price: ${server.hourly_price}/hr\n"
                        f"Auto-terminate: {config.max_runtime_hours}h or {config.idle_terminate_minutes}m idle"
                    ),
                }
            ]
        }

    except Exception as e:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Error launching server: {e}",
                }
            ],
            "is_error": True,
        }


@tool(
    "list_test_servers",
    "List all test servers",
    {"project_id": str, "include_terminated": bool},
)
async def list_test_servers(args: dict[str, Any]) -> dict[str, Any]:
    """List test servers."""

    fleet = _get_fleet_manager()

    # If include_terminated is True, pass None to get all
    # Otherwise the default behavior excludes terminated
    state_filter = None if args.get("include_terminated") else None

    servers = await fleet.list_servers(
        state=state_filter,
        project_id=args.get("project_id"),
    )

    if not servers:
        return {
            "content": [
                {
                    "type": "text",
                    "text": "No test servers found.",
                }
            ]
        }

    lines = [f"Found {len(servers)} test server(s):"]
    for s in servers:
        ip = s.public_ip or "no IP"
        lines.append(
            f"- {s.name} ({s.state.value}): {s.config.instance_type}, "
            f"{ip}, ${s.estimated_cost:.4f} spent"
        )

    return {
        "content": [
            {
                "type": "text",
                "text": "\n".join(lines),
            }
        ]
    }


@tool(
    "get_test_server",
    "Get details of a test server by name or ID",
    {"identifier": str},
)
async def get_test_server(args: dict[str, Any]) -> dict[str, Any]:
    """Get test server details."""
    fleet = _get_fleet_manager()
    identifier = args["identifier"]

    server = await fleet.get_server(identifier)
    if server is None:
        # Try to find by name
        servers = await fleet.list_servers()
        server = next((s for s in servers if s.name == identifier), None)

    if server is None:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Test server '{identifier}' not found.",
                }
            ],
            "is_error": True,
        }

    # Refresh state from AWS
    refreshed = await fleet.refresh_state(server.id)
    if refreshed:
        server = refreshed

    # Type narrowing - server cannot be None after this point
    assert server is not None

    ssh_cmd = f"ssh ec2-user@{server.public_ip}" if server.public_ip else "N/A"

    return {
        "content": [
            {
                "type": "text",
                "text": (
                    f"Test Server: {server.name}\n"
                    f"ID: {server.id}\n"
                    f"Instance ID: {server.instance_id}\n"
                    f"State: {server.state.value}\n"
                    f"Region: {server.region} ({server.availability_zone})\n"
                    f"Instance Type: {server.config.instance_type}\n"
                    f"Public IP: {server.public_ip or 'none'}\n"
                    f"Private IP: {server.private_ip or 'none'}\n"
                    f"SSH: {ssh_cmd}\n"
                    f"Hourly Price: ${server.hourly_price}\n"
                    f"Estimated Cost: ${server.estimated_cost:.4f}\n"
                    f"Launched: {server.launched_at}\n"
                    f"Last Activity: {server.last_activity or 'none'}\n"
                    f"Max Runtime: {server.config.max_runtime_hours}h\n"
                    f"Idle Timeout: {server.config.idle_terminate_minutes}m"
                ),
            }
        ]
    }


@tool(
    "terminate_test_server",
    "Terminate a test server",
    {"identifier": str, "reason": str},
)
async def terminate_test_server(args: dict[str, Any]) -> dict[str, Any]:
    """Terminate a test server."""
    fleet = _get_fleet_manager()
    identifier = args["identifier"]
    reason = args.get("reason", "user_request")

    # Find server
    server = await fleet.get_server(identifier)
    if server is None:
        servers = await fleet.list_servers()
        server = next((s for s in servers if s.name == identifier), None)

    if server is None:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Test server '{identifier}' not found.",
                }
            ],
            "is_error": True,
        }

    try:
        terminated = await fleet.terminate_server(server.id, reason=reason)

        if terminated:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"Terminated test server '{server.name}'.\n"
                            f"Total cost: ${server.estimated_cost:.4f}"
                        ),
                    }
                ]
            }
        else:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Failed to terminate server '{server.name}'.",
                    }
                ],
                "is_error": True,
            }

    except Exception as e:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Error terminating server: {e}",
                }
            ],
            "is_error": True,
        }


@tool(
    "terminate_all_servers",
    "Terminate all test servers, optionally filtered by project",
    {"project_id": str},
)
async def terminate_all_servers(args: dict[str, Any]) -> dict[str, Any]:
    """Terminate all test servers."""
    fleet = _get_fleet_manager()
    project_id = args.get("project_id")

    try:
        count = await fleet.terminate_all(
            project_id=project_id,
            reason="batch_terminate",
        )

        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Terminated {count} test server(s).",
                }
            ]
        }

    except Exception as e:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Error terminating servers: {e}",
                }
            ],
            "is_error": True,
        }


# =============================================================================
# Test Runner Tools
# =============================================================================


@tool(
    "run_tests_on_server",
    "Sync a project to a test server and run tests",
    {
        "server_name": str,
        "project_path": str,
        "test_command": str,
        "setup_command": str,
        "remote_path": str,
        "timeout": float,
        "project_id": str,
        "plan_id": str,
        "task_ids": str,
    },
)
async def run_tests_on_server(args: dict[str, Any]) -> dict[str, Any]:
    """Sync project and run tests on a test server."""
    from pms.services.test_execution_service import (
        TestExecutionConfig,
        TestExecutionService,
    )

    runner = _get_test_runner()

    server_name = args["server_name"]
    project_path = Path(args["project_path"]).resolve()

    if not project_path.exists():
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Project path does not exist: {project_path}",
                }
            ],
            "is_error": True,
        }

    task_ids = ()
    if args.get("task_ids"):
        task_ids = tuple(
            task_id.strip()
            for task_id in args["task_ids"].split(",")
            if task_id.strip()
        )

    execution = TestExecutionService(remote_runner=runner)
    config = TestExecutionConfig(
        mode="aws",
        server_name=server_name,
        project_path=project_path,
        remote_path=args.get("remote_path", "/home/ec2-user/project"),
        test_command=args.get("test_command", "pytest"),
        setup_command=args.get("setup_command"),
        timeout=args.get("timeout", 600.0),
        stream_output=False,  # Don't stream for agent tools
        project_id=args.get("project_id"),
        plan_id=args.get("plan_id"),
        task_ids=task_ids,
    )

    try:
        result = await execution.run(config)

        output = result.stdout[:2000] if result.stdout else "(no output)"
        if len(result.stdout) > 2000:
            output += "\n... (truncated)"

        return {
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"Test run {result.summary}\n\n"
                        f"Output:\n{output}"
                        + (
                            f"\n\nErrors:\n{result.stderr[:500]}"
                            if result.stderr
                            else ""
                        )
                    ),
                }
            ]
        }

    except Exception as e:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Error running tests: {e}",
                }
            ],
            "is_error": True,
        }


@tool(
    "sync_to_server",
    "Sync project files to a test server without running tests",
    {"server_name": str, "project_path": str, "remote_path": str},
)
async def sync_to_server(args: dict[str, Any]) -> dict[str, Any]:
    """Sync project to test server."""
    fleet = _get_fleet_manager()
    runner = _get_test_runner()

    server_name = args["server_name"]
    project_path = Path(args["project_path"]).resolve()
    remote_path = args.get("remote_path", "/home/ec2-user/project")

    if not project_path.exists():
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Project path does not exist: {project_path}",
                }
            ],
            "is_error": True,
        }

    # Find server
    servers = await fleet.list_servers()
    server = next((s for s in servers if s.name == server_name), None)
    if server is None:
        server = await fleet.get_server(server_name)

    if server is None:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Test server '{server_name}' not found.",
                }
            ],
            "is_error": True,
        }

    try:
        result = await runner.sync_only(
            server_id=server.id,
            project_path=project_path,
            remote_path=remote_path,
        )

        status = "completed successfully" if result.success else "failed"

        return {
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"Sync {status}.\n"
                        f"Files transferred: {result.files_transferred}\n"
                        f"Duration: {result.duration_seconds:.2f}s"
                    ),
                }
            ]
        }

    except Exception as e:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Error syncing to server: {e}",
                }
            ],
            "is_error": True,
        }


@tool(
    "exec_on_server",
    "Execute a command on a test server without syncing",
    {"server_name": str, "command": str, "working_dir": str, "timeout": float},
)
async def exec_on_server(args: dict[str, Any]) -> dict[str, Any]:
    """Execute command on test server."""
    fleet = _get_fleet_manager()
    runner = _get_test_runner()

    server_name = args["server_name"]
    command = args["command"]
    working_dir = args.get("working_dir")
    timeout = args.get("timeout", 300.0)

    # Find server
    servers = await fleet.list_servers()
    server = next((s for s in servers if s.name == server_name), None)
    if server is None:
        server = await fleet.get_server(server_name)

    if server is None:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Test server '{server_name}' not found.",
                }
            ],
            "is_error": True,
        }

    try:
        result = await runner.run_only(
            server_id=server.id,
            command=command,
            working_dir=working_dir,
            timeout=timeout,
        )

        output_parts = []
        if result.stdout:
            output_parts.append(f"stdout:\n{result.stdout[:2000]}")
        if result.stderr:
            output_parts.append(f"stderr:\n{result.stderr[:500]}")

        output = "\n\n".join(output_parts) if output_parts else "(no output)"

        return {
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"Command {'succeeded' if result.success else 'failed'}.\n"
                        f"Exit code: {result.exit_code}\n"
                        f"Duration: {result.duration_seconds:.2f}s\n\n"
                        f"{output}"
                    ),
                }
            ]
        }

    except Exception as e:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Error executing command: {e}",
                }
            ],
            "is_error": True,
        }


# List of all AWS tools for export
ALL_AWS_TOOLS = [
    # Spot finder
    find_spot_instances,
    # Fleet manager
    launch_test_server,
    list_test_servers,
    get_test_server,
    terminate_test_server,
    terminate_all_servers,
    # Test runner
    run_tests_on_server,
    sync_to_server,
    exec_on_server,
]
