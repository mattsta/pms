"""Plugin Manifest Definitions.

Defines the structure and validation for plugin manifests.
Plugins are defined via JSON or YAML manifest files.

Example manifest (plugin.json):
    {
        "name": "github-integration",
        "version": "1.0.0",
        "description": "GitHub integration for PMS",
        "author": "PMS Team",
        "type": "extension",
        "entrypoint": "main.py",
        "tools": [
            {
                "name": "list_repos",
                "description": "List GitHub repositories",
                "parameters": {
                    "org": {"type": "string", "required": true}
                }
            }
        ],
        "hooks": [
            {"event": "task_completed", "handler": "on_task_complete"}
        ],
        "dependencies": [
            {"name": "requests", "version": ">=2.28.0"}
        ],
        "capabilities": ["network", "filesystem_read"],
        "config_schema": {
            "github_token": {"type": "string", "secret": true}
        }
    }
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class PluginType(Enum):
    """Type of plugin."""

    EXTENSION = "extension"  # Adds new tools/capabilities
    INTEGRATION = "integration"  # Integrates external services
    THEME = "theme"  # UI/output customization
    LANGUAGE = "language"  # Adds DSL/language support
    RUNTIME = "runtime"  # Custom execution runtime
    PROVIDER = "provider"  # Data/service provider


class PluginCapability(Enum):
    """Capabilities a plugin can request."""

    # Filesystem access
    FILESYSTEM_READ = "filesystem_read"
    FILESYSTEM_WRITE = "filesystem_write"

    # Network access
    NETWORK = "network"
    NETWORK_LOCAL = "network_local"  # localhost only

    # Process execution
    SUBPROCESS = "subprocess"
    SUBPROCESS_SANDBOXED = "subprocess_sandboxed"

    # Database access
    DATABASE_READ = "database_read"
    DATABASE_WRITE = "database_write"

    # Platform integration
    EVENTS = "events"  # Subscribe to platform events
    TOOLS = "tools"  # Register tools
    HOOKS = "hooks"  # Register hooks
    NAMESPACES = "namespaces"  # Register namespaces

    # Secrets
    SECRETS_READ = "secrets_read"

    # Full access (dangerous)
    UNRESTRICTED = "unrestricted"


@dataclass
class PluginParameter:
    """Parameter definition for a plugin tool."""

    name: str
    type: str  # string, int, float, bool, list, dict, any
    description: str = ""
    required: bool = False
    default: Any = None
    enum: list[str] | None = None
    pattern: str | None = None  # Regex for validation

    def to_dict(self) -> dict[str, Any]:
        result = {
            "name": self.name,
            "type": self.type,
            "description": self.description,
            "required": self.required,
        }
        if self.default is not None:
            result["default"] = self.default
        if self.enum:
            result["enum"] = self.enum
        if self.pattern:
            result["pattern"] = self.pattern
        return result

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> PluginParameter:
        return cls(
            name=name,
            type=data.get("type", "string"),
            description=data.get("description", ""),
            required=data.get("required", False),
            default=data.get("default"),
            enum=data.get("enum"),
            pattern=data.get("pattern"),
        )


@dataclass
class PluginTool:
    """Tool definition within a plugin."""

    name: str
    description: str
    handler: str = ""  # Function name in entrypoint
    parameters: dict[str, PluginParameter] = field(default_factory=dict)
    returns: str = "any"  # Return type
    async_handler: bool = True  # Whether handler is async
    timeout: float = 30.0  # Timeout in seconds
    cacheable: bool = False
    cache_ttl: int = 300  # Cache TTL in seconds

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "handler": self.handler,
            "parameters": {
                name: param.to_dict() for name, param in self.parameters.items()
            },
            "returns": self.returns,
            "async_handler": self.async_handler,
            "timeout": self.timeout,
            "cacheable": self.cacheable,
            "cache_ttl": self.cache_ttl,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PluginTool:
        parameters = {}
        if "parameters" in data:
            for name, param_data in data["parameters"].items():
                if isinstance(param_data, dict):
                    parameters[name] = PluginParameter.from_dict(name, param_data)
                else:
                    # Simple type definition
                    parameters[name] = PluginParameter(name=name, type=str(param_data))

        return cls(
            name=data["name"],
            description=data.get("description", ""),
            handler=data.get("handler", data["name"]),
            parameters=parameters,
            returns=data.get("returns", "any"),
            async_handler=data.get("async_handler", True),
            timeout=data.get("timeout", 30.0),
            cacheable=data.get("cacheable", False),
            cache_ttl=data.get("cache_ttl", 300),
        )


@dataclass
class PluginHook:
    """Hook definition for event subscription."""

    event: str  # Event name (e.g., task_completed, project_created)
    handler: str  # Function name in entrypoint
    priority: int = 100  # Lower = higher priority
    async_handler: bool = True
    filter: dict[str, Any] | None = None  # Optional event filter

    def to_dict(self) -> dict[str, Any]:
        result = {
            "event": self.event,
            "handler": self.handler,
            "priority": self.priority,
            "async_handler": self.async_handler,
        }
        if self.filter:
            result["filter"] = self.filter
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PluginHook:
        return cls(
            event=data["event"],
            handler=data.get("handler", f"on_{data['event']}"),
            priority=data.get("priority", 100),
            async_handler=data.get("async_handler", True),
            filter=data.get("filter"),
        )


@dataclass
class PluginDependency:
    """Dependency on another plugin or package."""

    name: str
    version: str = "*"  # Version constraint
    optional: bool = False
    type: str = "python"  # python, plugin, system

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "optional": self.optional,
            "type": self.type,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PluginDependency:
        if isinstance(data, str):
            return cls(name=data)
        return cls(
            name=data["name"],
            version=data.get("version", "*"),
            optional=data.get("optional", False),
            type=data.get("type", "python"),
        )


@dataclass
class PluginConfigField:
    """Configuration field schema."""

    name: str
    type: str = "string"
    description: str = ""
    required: bool = False
    default: Any = None
    secret: bool = False  # Should be stored securely
    env_var: str | None = None  # Environment variable override

    def to_dict(self) -> dict[str, Any]:
        result = {
            "name": self.name,
            "type": self.type,
            "description": self.description,
            "required": self.required,
            "secret": self.secret,
        }
        if self.default is not None:
            result["default"] = self.default
        if self.env_var:
            result["env_var"] = self.env_var
        return result

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> PluginConfigField:
        return cls(
            name=name,
            type=data.get("type", "string"),
            description=data.get("description", ""),
            required=data.get("required", False),
            default=data.get("default"),
            secret=data.get("secret", False),
            env_var=data.get("env_var"),
        )


@dataclass
class PluginManifest:
    """Complete plugin manifest.

    This is the primary definition for a plugin, containing all metadata,
    tools, hooks, dependencies, and configuration.
    """

    # Required fields
    name: str
    version: str

    # Metadata
    description: str = ""
    author: str = ""
    license: str = ""
    homepage: str = ""
    repository: str = ""
    keywords: list[str] = field(default_factory=list)

    # Plugin type and execution
    type: PluginType = PluginType.EXTENSION
    entrypoint: str = "main.py"
    runtime: str = "python"  # python, node, deno, wasm, native

    # Tools and hooks
    tools: list[PluginTool] = field(default_factory=list)
    hooks: list[PluginHook] = field(default_factory=list)

    # Dependencies
    dependencies: list[PluginDependency] = field(default_factory=list)
    pms_version: str = ">=1.0.0"  # Required PMS version

    # Capabilities and permissions
    capabilities: list[PluginCapability] = field(default_factory=list)

    # Configuration schema
    config_schema: dict[str, PluginConfigField] = field(default_factory=dict)

    # Execution settings
    sandbox: bool = True  # Run in sandbox
    max_memory_mb: int = 256  # Memory limit
    timeout: float = 60.0  # Overall timeout
    max_concurrent: int = 10  # Max concurrent tool calls

    # Lifecycle hooks (functions in entrypoint)
    on_load: str | None = None
    on_unload: str | None = None
    on_enable: str | None = None
    on_disable: str | None = None

    # Internal tracking
    path: Path | None = None  # Path to manifest file
    loaded_at: datetime | None = None
    checksum: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert manifest to dictionary."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "license": self.license,
            "homepage": self.homepage,
            "repository": self.repository,
            "keywords": self.keywords,
            "type": self.type.value,
            "entrypoint": self.entrypoint,
            "runtime": self.runtime,
            "tools": [t.to_dict() for t in self.tools],
            "hooks": [h.to_dict() for h in self.hooks],
            "dependencies": [d.to_dict() for d in self.dependencies],
            "pms_version": self.pms_version,
            "capabilities": [c.value for c in self.capabilities],
            "config_schema": {
                name: field.to_dict() for name, field in self.config_schema.items()
            },
            "sandbox": self.sandbox,
            "max_memory_mb": self.max_memory_mb,
            "timeout": self.timeout,
            "max_concurrent": self.max_concurrent,
            "on_load": self.on_load,
            "on_unload": self.on_unload,
            "on_enable": self.on_enable,
            "on_disable": self.on_disable,
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert manifest to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(
        cls, data: dict[str, Any], path: Path | None = None
    ) -> PluginManifest:
        """Create manifest from dictionary."""
        # Parse tools
        tools = []
        for tool_data in data.get("tools", []):
            tools.append(PluginTool.from_dict(tool_data))

        # Parse hooks
        hooks = []
        for hook_data in data.get("hooks", []):
            hooks.append(PluginHook.from_dict(hook_data))

        # Parse dependencies
        dependencies = []
        for dep_data in data.get("dependencies", []):
            dependencies.append(PluginDependency.from_dict(dep_data))

        # Parse capabilities
        capabilities = []
        for cap in data.get("capabilities", []):
            try:
                capabilities.append(PluginCapability(cap))
            except ValueError:
                logger.warning(f"Unknown capability: {cap}")

        # Parse config schema
        config_schema = {}
        for name, field_data in data.get("config_schema", {}).items():
            config_schema[name] = PluginConfigField.from_dict(name, field_data)

        return cls(
            name=data["name"],
            version=data["version"],
            description=data.get("description", ""),
            author=data.get("author", ""),
            license=data.get("license", ""),
            homepage=data.get("homepage", ""),
            repository=data.get("repository", ""),
            keywords=data.get("keywords", []),
            type=PluginType(data.get("type", "extension")),
            entrypoint=data.get("entrypoint", "main.py"),
            runtime=data.get("runtime", "python"),
            tools=tools,
            hooks=hooks,
            dependencies=dependencies,
            pms_version=data.get("pms_version", ">=1.0.0"),
            capabilities=capabilities,
            config_schema=config_schema,
            sandbox=data.get("sandbox", True),
            max_memory_mb=data.get("max_memory_mb", 256),
            timeout=data.get("timeout", 60.0),
            max_concurrent=data.get("max_concurrent", 10),
            on_load=data.get("on_load"),
            on_unload=data.get("on_unload"),
            on_enable=data.get("on_enable"),
            on_disable=data.get("on_disable"),
            path=path,
        )

    @classmethod
    def from_json(cls, json_str: str, path: Path | None = None) -> PluginManifest:
        """Create manifest from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data, path)

    @classmethod
    def from_file(cls, path: Path | str) -> PluginManifest:
        """Load manifest from file."""
        path = Path(path)
        content = path.read_text()

        if path.suffix in (".yaml", ".yml"):
            try:
                import yaml as yaml_module  # type: ignore[import-untyped]

                data = yaml_module.safe_load(content)
            except ImportError:
                raise ImportError("PyYAML required for YAML manifests")
        else:
            data = json.loads(content)

        manifest = cls.from_dict(data, path)
        manifest.loaded_at = datetime.now()
        return manifest

    def validate(self) -> list[str]:
        """Validate manifest and return list of errors."""
        errors = []

        # Required fields
        if not self.name:
            errors.append("Plugin name is required")
        if not self.version:
            errors.append("Plugin version is required")

        # Name format
        if self.name and not self.name.replace("-", "").replace("_", "").isalnum():
            errors.append("Plugin name must be alphanumeric with dashes/underscores")

        # Tools validation
        tool_names = set()
        for tool in self.tools:
            if tool.name in tool_names:
                errors.append(f"Duplicate tool name: {tool.name}")
            tool_names.add(tool.name)

            if not tool.name:
                errors.append("Tool name is required")
            if not tool.description:
                errors.append(f"Tool {tool.name} missing description")

        # Hooks validation
        for hook in self.hooks:
            if not hook.event:
                errors.append("Hook event is required")
            if not hook.handler:
                errors.append(f"Hook for {hook.event} missing handler")

        # Capability validation
        dangerous_caps = {PluginCapability.UNRESTRICTED, PluginCapability.SUBPROCESS}
        if any(c in self.capabilities for c in dangerous_caps) and self.sandbox:
            errors.append(
                "Plugins with dangerous capabilities should set sandbox=false"
            )

        return errors

    def get_tool(self, name: str) -> PluginTool | None:
        """Get tool by name."""
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None

    def get_hook(self, event: str) -> list[PluginHook]:
        """Get hooks for an event."""
        return [h for h in self.hooks if h.event == event]

    @property
    def is_valid(self) -> bool:
        """Check if manifest is valid."""
        return len(self.validate()) == 0

    @property
    def full_name(self) -> str:
        """Get full name with version."""
        return f"{self.name}@{self.version}"

    @property
    def requires_sandbox(self) -> bool:
        """Check if plugin should run in sandbox."""
        # Force sandbox for network/subprocess capabilities
        dangerous = {
            PluginCapability.NETWORK,
            PluginCapability.SUBPROCESS,
            PluginCapability.FILESYSTEM_WRITE,
        }
        return self.sandbox or any(c in self.capabilities for c in dangerous)
