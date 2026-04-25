"""MCP server installation helpers for Claude Desktop integration."""

import json
import sys
from pathlib import Path
from typing import Any

from loguru import logger


def get_claude_config_path() -> Path:
    """Get Claude Desktop configuration file path based on OS."""
    if sys.platform == "darwin":  # macOS
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "Claude"
            / "claude_desktop_config.json"
        )
    elif sys.platform == "win32":  # Windows
        return (
            Path.home()
            / "AppData"
            / "Roaming"
            / "Claude"
            / "claude_desktop_config.json"
        )
    else:  # Linux
        return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


def get_pms_server_config() -> dict[str, Any]:
    """Get PMS MCP server configuration."""
    return {
        "command": "uv",
        "args": [
            "--directory",
            str(Path(__file__).parent.parent.parent),  # PMS repo root
            "run",
            "pms-mcp-server",
        ],
        "env": {},
    }


def read_claude_config(config_path: Path) -> dict[str, Any]:
    """Read existing Claude Desktop config or create new one."""
    if config_path.exists():
        try:
            with config_path.open() as f:
                data: dict[str, Any] = json.load(f)
                return data
        except json.JSONDecodeError:
            logger.warning("Invalid JSON in Claude config, creating new config")
            return {"mcpServers": {}}
    else:
        return {"mcpServers": {}}


def write_claude_config(config_path: Path, config: dict[str, Any]) -> None:
    """Write Claude Desktop configuration."""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w") as f:
        json.dump(config, f, indent=2)
    logger.info("Wrote Claude config to {}", config_path)


def install_pms_server(
    server_name: str = "pms",
    force: bool = False,
) -> tuple[bool, str]:
    """
    Install PMS as an MCP server in Claude Desktop configuration.

    Args:
        server_name: Name for the MCP server (default: "pms")
        force: Overwrite if already exists

    Returns:
        Tuple of (success, message)
    """
    config_path = get_claude_config_path()

    # Read existing config
    config = read_claude_config(config_path)

    # Ensure mcpServers section exists
    if "mcpServers" not in config:
        config["mcpServers"] = {}

    # Check if already installed
    if server_name in config["mcpServers"] and not force:
        return (
            False,
            f"MCP server '{server_name}' already installed. Use --force to overwrite.",
        )

    # Add PMS server configuration
    config["mcpServers"][server_name] = get_pms_server_config()

    # Write config
    write_claude_config(config_path, config)

    return True, f"PMS installed as MCP server '{server_name}' in Claude Desktop"


def uninstall_pms_server(server_name: str = "pms") -> tuple[bool, str]:
    """
    Remove PMS from Claude Desktop configuration.

    Args:
        server_name: Name of the MCP server to remove

    Returns:
        Tuple of (success, message)
    """
    config_path = get_claude_config_path()

    if not config_path.exists():
        return False, "Claude Desktop configuration not found"

    config = read_claude_config(config_path)

    if "mcpServers" not in config or server_name not in config["mcpServers"]:
        return False, f"MCP server '{server_name}' not found in configuration"

    # Remove server
    del config["mcpServers"][server_name]

    # Write config
    write_claude_config(config_path, config)

    return True, f"Removed MCP server '{server_name}' from Claude Desktop"


def verify_installation(server_name: str = "pms") -> tuple[bool, str]:
    """
    Verify PMS is properly configured in Claude Desktop.

    Args:
        server_name: Name of the MCP server to check

    Returns:
        Tuple of (installed, status_message)
    """
    config_path = get_claude_config_path()

    if not config_path.exists():
        return False, "Claude Desktop configuration not found"

    config = read_claude_config(config_path)

    if "mcpServers" not in config:
        return False, "No MCP servers configured"

    if server_name not in config["mcpServers"]:
        return False, f"MCP server '{server_name}' not found"

    server_config = config["mcpServers"][server_name]

    # Validate configuration
    if "command" not in server_config:
        return False, f"Invalid configuration: missing 'command'"

    return True, f"MCP server '{server_name}' is properly configured"
