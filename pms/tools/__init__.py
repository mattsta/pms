"""Agent tools and MCP server factories.

This module provides:
- Tool functions for project/task management, remote operations, and AWS
- MCP server factory for integrating tools with Claude
- Tool registry with metadata for tool search and deferred loading

Tool Search Support:
    PMS supports Claude's Tool Search feature for efficient context management.
    Use the registry module to configure which tools should be immediately
    available vs discovered on-demand:

    ```python
    from pms.tools import CORE_TOOL_NAMES, get_defer_loading_config

    # Get config for defer_loading
    config = get_defer_loading_config()
    ```

See pms.tools.registry for detailed documentation.
"""

from pms.tools.project_tools import (
    ALL_PROJECT_TOOLS,
    set_services,
)
from pms.tools.registry import (
    CORE_TOOL_NAMES,
    DEFERRED_TOOL_NAMES,
    ToolCategory,
    ToolMetadata,
    get_defer_loading_config,
    get_tool_metadata,
    get_tools_summary,
    search_tools,
)
from pms.tools.remote_tools import (
    ALL_REMOTE_TOOLS,
    set_remote_service,
)
from pms.tools.server import (
    AWS_TOOL_NAMES,
    PMS_TOOL_NAMES,
    PROJECT_TOOL_NAMES,
    REMOTE_TOOL_NAMES,
    ServerMode,
    create_core_pms_server,
    create_pms_server,
    get_core_tools_config,
    get_defer_config_for_categories,
    get_tool_search_tools_config,
)

# Optional AWS tools (require boto3)
try:
    from pms.tools.aws_tools import (
        ALL_AWS_TOOLS,
        set_aws_services,
    )
except ImportError:
    from typing import Any as _Any  # Avoid redefinition

    ALL_AWS_TOOLS = []

    def set_aws_services(*args: _Any, **kwargs: _Any) -> None:  # type: ignore[misc]
        pass


__all__ = [
    # Tool lists
    "ALL_PROJECT_TOOLS",
    "ALL_REMOTE_TOOLS",
    "ALL_AWS_TOOLS",
    # Tool name constants (for allowed_tools config)
    "PMS_TOOL_NAMES",
    "PROJECT_TOOL_NAMES",
    "REMOTE_TOOL_NAMES",
    "AWS_TOOL_NAMES",
    # Tool search / deferred loading support (registry)
    "CORE_TOOL_NAMES",
    "DEFERRED_TOOL_NAMES",
    "ToolCategory",
    "ToolMetadata",
    "get_defer_loading_config",
    "get_tool_metadata",
    "get_tools_summary",
    "search_tools",
    # Tool search / deferred loading support (server)
    "ServerMode",
    "get_core_tools_config",
    "get_defer_config_for_categories",
    "get_tool_search_tools_config",
    # Server factories
    "create_pms_server",
    "create_core_pms_server",
    # Service initializers
    "set_services",
    "set_remote_service",
    "set_aws_services",
]
