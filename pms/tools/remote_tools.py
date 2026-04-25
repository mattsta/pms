"""Agent tools for remote operations (SSH, rsync)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from claude_code_sdk import tool

if TYPE_CHECKING:
    from pms.services import RemoteService

# Global service instance - set by server initialization
_remote_service: RemoteService | None = None


def set_remote_service(remote_service: RemoteService) -> None:
    """Set the remote service instance for tools to use."""
    global _remote_service
    _remote_service = remote_service


def _get_remote_service() -> RemoteService:
    """Get remote service or raise if not initialized."""
    if _remote_service is None:
        raise RuntimeError(
            "Remote service not initialized. Call set_remote_service first."
        )
    return _remote_service


# =============================================================================
# Remote Host Tools
# =============================================================================


@tool(
    "list_remote_hosts",
    "List all configured remote hosts with their connection details",
    {"tag": str},
)
async def list_remote_hosts(args: dict[str, Any]) -> dict[str, Any]:
    """List remote hosts."""
    service = _get_remote_service()

    hosts = await service.list_hosts(tag=args.get("tag"))

    if not hosts:
        return {
            "content": [
                {
                    "type": "text",
                    "text": "No remote hosts configured.",
                }
            ]
        }

    lines = [f"Found {len(hosts)} remote host(s):"]
    for h in hosts:
        tags_str = f" [{', '.join(h.tags)}]" if h.tags else ""
        lines.append(f"- {h.name}: {h.username}@{h.host}:{h.port}{tags_str}")

    return {
        "content": [
            {
                "type": "text",
                "text": "\n".join(lines),
            }
        ]
    }


@tool(
    "get_remote_host",
    "Get details of a remote host by name",
    {"name": str},
)
async def get_remote_host(args: dict[str, Any]) -> dict[str, Any]:
    """Get remote host details."""
    service = _get_remote_service()
    name = args["name"]

    host = await service.get_host(name)
    if host is None:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Remote host '{name}' not found.",
                }
            ],
            "is_error": True,
        }

    tags_str = ", ".join(host.tags) if host.tags else "none"

    return {
        "content": [
            {
                "type": "text",
                "text": (
                    f"Remote Host: {host.name}\n"
                    f"ID: {host.id}\n"
                    f"Host: {host.host}\n"
                    f"Username: {host.username}\n"
                    f"Port: {host.port}\n"
                    f"Key Path: {host.key_path or 'none'}\n"
                    f"Default Path: {host.default_remote_path or 'none'}\n"
                    f"Tags: {tags_str}\n"
                    f"Type: {host.host_type.value}"
                ),
            }
        ]
    }


@tool(
    "test_remote_connection",
    "Test SSH connection to a remote host",
    {"name": str},
)
async def test_remote_connection(args: dict[str, Any]) -> dict[str, Any]:
    """Test remote host connection."""
    service = _get_remote_service()
    name = args["name"]

    try:
        info = await service.test_host(name)

        if info.is_reachable:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Connection to '{name}' successful. Host: {info.host.host}",
                    }
                ]
            }
        else:
            error_msg = info.connection_error or "Unknown error"
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Connection to '{name}' failed: {error_msg}",
                    }
                ],
                "is_error": True,
            }

    except Exception as e:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Error testing connection to '{name}': {e}",
                }
            ],
            "is_error": True,
        }


@tool(
    "execute_remote_command",
    "Execute a shell command on a remote host via SSH",
    {"name": str, "command": str, "timeout": float},
)
async def execute_remote_command(args: dict[str, Any]) -> dict[str, Any]:
    """Execute command on remote host."""
    service = _get_remote_service()
    name = args["name"]
    command = args["command"]
    timeout = args.get("timeout")

    try:
        result = await service.execute_command(name, command, timeout=timeout)

        output_parts = []
        if result.stdout:
            output_parts.append(f"stdout:\n{result.stdout}")
        if result.stderr:
            output_parts.append(f"stderr:\n{result.stderr}")

        output = "\n\n".join(output_parts) if output_parts else "(no output)"
        status = "succeeded" if result.success else "failed"

        return {
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"Command {status} on '{name}'.\n"
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
                    "text": f"Error executing command on '{name}': {e}",
                }
            ],
            "is_error": True,
        }


@tool(
    "sync_push",
    "Push local files to a remote host using rsync",
    {
        "name": str,
        "local_path": str,
        "remote_path": str,
        "exclude": str,
        "dry_run": bool,
    },
)
async def sync_push(args: dict[str, Any]) -> dict[str, Any]:
    """Push files to remote host."""
    service = _get_remote_service()
    name = args["name"]
    local_path = Path(args["local_path"]).resolve()
    remote_path = args.get("remote_path")
    exclude = args.get("exclude")
    dry_run = args.get("dry_run", False)

    if not local_path.exists():
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Local path does not exist: {local_path}",
                }
            ],
            "is_error": True,
        }

    # Parse exclude patterns
    exclude_list = None
    if exclude:
        exclude_list = [e.strip() for e in exclude.split(",") if e.strip()]

    try:
        result = await service.sync_push(
            identifier=name,
            local_path=local_path,
            remote_path=remote_path,
            exclude=exclude_list,
            dry_run=dry_run,
        )

        mode = "(dry run) " if dry_run else ""
        status = "completed successfully" if result.success else "failed"

        text = (
            f"Sync {mode}{status}.\n"
            f"Files transferred: {result.files_transferred}\n"
            f"Duration: {result.duration_seconds:.2f}s"
        )

        if result.stderr:
            text += f"\n\nErrors:\n{result.stderr}"

        return {
            "content": [
                {
                    "type": "text",
                    "text": text,
                }
            ]
        }

    except Exception as e:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Error syncing to '{name}': {e}",
                }
            ],
            "is_error": True,
        }


@tool(
    "sync_pull",
    "Pull files from a remote host to local using rsync",
    {
        "name": str,
        "remote_path": str,
        "local_path": str,
        "exclude": str,
        "dry_run": bool,
    },
)
async def sync_pull(args: dict[str, Any]) -> dict[str, Any]:
    """Pull files from remote host."""
    service = _get_remote_service()
    name = args["name"]
    remote_path = args["remote_path"]
    local_path = Path(args["local_path"]).resolve()
    exclude = args.get("exclude")
    dry_run = args.get("dry_run", False)

    # Parse exclude patterns
    exclude_list = None
    if exclude:
        exclude_list = [e.strip() for e in exclude.split(",") if e.strip()]

    try:
        result = await service.sync_pull(
            identifier=name,
            remote_path=remote_path,
            local_path=local_path,
            exclude=exclude_list,
            dry_run=dry_run,
        )

        mode = "(dry run) " if dry_run else ""
        status = "completed successfully" if result.success else "failed"

        text = (
            f"Sync {mode}{status}.\n"
            f"Files transferred: {result.files_transferred}\n"
            f"Duration: {result.duration_seconds:.2f}s"
        )

        if result.stderr:
            text += f"\n\nErrors:\n{result.stderr}"

        return {
            "content": [
                {
                    "type": "text",
                    "text": text,
                }
            ]
        }

    except Exception as e:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Error syncing from '{name}': {e}",
                }
            ],
            "is_error": True,
        }


# List of all remote tools for export
ALL_REMOTE_TOOLS = [
    list_remote_hosts,
    get_remote_host,
    test_remote_connection,
    execute_remote_command,
    sync_push,
    sync_pull,
]
