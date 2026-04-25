"""Tool Generator Agent - Creates new PMS tools from natural language descriptions.

This agent enables PMS to write its own tools, following the patterns in TOOL_DEVELOPMENT.md.
It generates complete tool modules with tests and registers them in the system.

Usage:
    pms generate tool "Sync Linear issues to PMS tasks"
    pms generate tool --name linear_sync --category integrations "Import issues from Linear"
"""

from __future__ import annotations

import builtins
import contextlib
import re
import textwrap
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from claude_code_sdk import tool

from pms.tools.registry import ToolCategory

# =============================================================================
# Data Models
# =============================================================================


class GenerationStatus(Enum):
    """Status of tool generation."""

    PENDING = "pending"
    ANALYZING = "analyzing"
    GENERATING = "generating"
    TESTING = "testing"
    REGISTERING = "registering"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ToolSpec:
    """Specification for a tool to generate."""

    name: str
    description: str
    category: ToolCategory
    parameters: dict[str, dict[str, Any]]  # name -> {type, description, required}
    is_core: bool = False
    search_keywords: tuple[str, ...] = ()
    service_dependency: str | None = None  # e.g., "github_service", "slack_service"
    example_usage: str | None = None


@dataclass
class GeneratedTool:
    """Result of tool generation."""

    spec: ToolSpec
    tool_code: str
    test_code: str
    registry_entry: str
    status: GenerationStatus = GenerationStatus.PENDING
    errors: list[str] = field(default_factory=list)


# =============================================================================
# Tool Generator
# =============================================================================


class ToolGenerator:
    """Generates new PMS tools from specifications."""

    TOOL_TEMPLATE = textwrap.dedent('''
        @tool(
            "{name}",
            "{description}",
            {{{parameters}}},
        )
        async def {name}(args: dict[str, Any]) -> dict[str, Any]:
            """
            {docstring}

            Args:
                args: Tool arguments
                {args_doc}

            Returns:
                Tool response with content
            """
            {service_get}

            {implementation}

            return {{
                "content": [
                    {{
                        "type": "text",
                        "text": {result_text},
                    }}
                ]
            }}
    ''').strip()

    TEST_TEMPLATE = textwrap.dedent('''
        """Tests for {name} tool."""

        import pytest
        from unittest.mock import AsyncMock, MagicMock

        from pms.tools.{module}_tools import {name}, set_{service}_service


        class Test{class_name}:
            """Tests for {name} tool."""

            @pytest.fixture
            def mock_service(self):
                """Create mock service."""
                service = MagicMock()
                {mock_setup}
                set_{service}_service(service)
                return service

            @pytest.mark.asyncio
            async def test_{name}_success(self, mock_service):
                """Test successful {name} call."""
                result = await {name}({test_args})

                assert "content" in result
                assert len(result["content"]) > 0
                {assertions}

            @pytest.mark.asyncio
            async def test_{name}_error_handling(self, mock_service):
                """Test error handling in {name}."""
                mock_service.{method}.side_effect = Exception("Test error")

                result = await {name}({test_args})

                assert result.get("is_error", False) or "error" in result["content"][0]["text"].lower()
    ''').strip()

    REGISTRY_TEMPLATE = textwrap.dedent("""
        ToolMetadata(
            name="{name}",
            description="{description}",
            category=ToolCategory.{category},
            is_core={is_core},
            search_keywords={keywords},
        ),
    """).strip()

    def __init__(self, output_dir: Path | None = None):
        """Initialize generator.

        Args:
            output_dir: Directory for generated files (default: pms/tools/)
        """
        self.output_dir = output_dir or Path(__file__).parent.parent / "tools"

    async def analyze_description(self, description: str) -> ToolSpec:
        """Analyze natural language description to extract tool specification.

        This uses heuristics to extract:
        - Tool name from action verbs and objects
        - Category from domain keywords
        - Parameters from mentioned inputs
        - Keywords from description terms
        """
        # Normalize description
        desc_lower = description.lower()

        # Extract action and object for name
        name = self._extract_name(description)

        # Determine category
        category = self._determine_category(desc_lower)

        # Extract parameters
        parameters = self._extract_parameters(description)

        # Generate keywords
        keywords = self._generate_keywords(description, name)

        # Determine service dependency
        service = self._determine_service(category, desc_lower)

        return ToolSpec(
            name=name,
            description=description,
            category=category,
            parameters=parameters,
            search_keywords=keywords,
            service_dependency=service,
        )

    def _extract_name(self, description: str) -> str:
        """Extract tool name from description."""
        # Common action verbs
        actions = [
            "sync",
            "import",
            "export",
            "create",
            "delete",
            "update",
            "list",
            "get",
            "set",
            "send",
            "fetch",
            "push",
            "pull",
            "deploy",
            "run",
            "start",
            "stop",
            "restart",
            "check",
            "verify",
            "validate",
            "search",
            "find",
            "query",
            "trigger",
            "notify",
            "archive",
            "restore",
        ]

        desc_lower = description.lower()
        words = re.findall(r"\b\w+\b", desc_lower)

        # Find action verb
        action = None
        for word in words:
            if word in actions:
                action = word
                break

        if not action:
            action = "process"

        # Find object (nouns after action)
        objects = []
        found_action = False
        for word in words:
            if word == action:
                found_action = True
                continue
            if (
                found_action
                and len(word) > 2
                and word not in ["the", "to", "from", "for", "with", "and"]
            ):
                objects.append(word)
                if len(objects) >= 2:
                    break

        # Build name
        if objects:
            return f"{action}_{'_'.join(objects)}"
        return f"{action}_items"

    def _determine_category(self, desc_lower: str) -> ToolCategory:
        """Determine tool category from description."""
        category_keywords = {
            ToolCategory.PROJECT: ["project", "milestone", "goal"],
            ToolCategory.TASK: ["task", "todo", "issue", "ticket"],
            ToolCategory.REMOTE: ["ssh", "rsync", "server", "deploy", "remote"],
            ToolCategory.AWS_SPOT: ["aws", "ec2", "spot", "instance"],
            ToolCategory.AWS_TEST: ["test server", "test runner"],
        }

        for category, keywords in category_keywords.items():
            if any(kw in desc_lower for kw in keywords):
                return category

        # Check for integration keywords
        integrations = [
            "github",
            "gitlab",
            "jira",
            "linear",
            "slack",
            "notion",
            "discord",
        ]
        if any(svc in desc_lower for svc in integrations):
            # Default to PROJECT for now (would be INTEGRATIONS in full system)
            return ToolCategory.PROJECT

        return ToolCategory.PROJECT

    def _extract_parameters(self, description: str) -> dict[str, dict[str, Any]]:
        """Extract parameters from description."""
        params = {}

        # Common parameter patterns
        patterns = [
            (r"\b(repo(?:sitory)?)\b", "repo", str, "Repository name or URL"),
            (r"\b(project)\b", "project", str, "Project name"),
            (r"\b(task)\b", "task", str, "Task identifier"),
            (r"\b(user(?:name)?)\b", "username", str, "Username"),
            (r"\b(limit|count|max)\b", "limit", int, "Maximum number of results"),
            (r"\b(status)\b", "status", str, "Status filter"),
            (r"\b(labels?)\b", "labels", str, "Comma-separated labels"),
            (r"\b(message)\b", "message", str, "Message text"),
            (r"\b(path)\b", "path", str, "File or directory path"),
            (r"\b(url)\b", "url", str, "URL"),
            (r"\b(query|search)\b", "query", str, "Search query"),
        ]

        desc_lower = description.lower()
        for pattern, name, type_, desc in patterns:
            if re.search(pattern, desc_lower):
                params[name] = {
                    "type": type_,
                    "description": desc,
                    "required": name in ["project", "repo", "query"],
                }

        # Always include at least one optional parameter
        if not params:
            params["input"] = {
                "type": str,
                "description": "Input data",
                "required": False,
            }

        return params

    def _generate_keywords(self, description: str, name: str) -> tuple[str, ...]:
        """Generate search keywords from description."""
        # Extract meaningful words
        words = re.findall(r"\b\w{3,}\b", description.lower())

        # Remove common words
        stopwords = {
            "the",
            "and",
            "for",
            "from",
            "with",
            "that",
            "this",
            "have",
            "will",
            "can",
            "all",
            "are",
            "was",
            "were",
            "been",
            "being",
            "has",
            "had",
        }
        keywords = [w for w in words if w not in stopwords]

        # Add name parts
        name_parts = name.split("_")
        keywords.extend(name_parts)

        # Deduplicate and limit
        unique = list(dict.fromkeys(keywords))[:10]
        return tuple(unique)

    def _determine_service(self, category: ToolCategory, desc_lower: str) -> str | None:
        """Determine service dependency."""
        service_map = {
            ToolCategory.PROJECT: "project",
            ToolCategory.TASK: "task",
            ToolCategory.REMOTE: "remote",
            ToolCategory.AWS_SPOT: "aws",
            ToolCategory.AWS_TEST: "aws",
        }

        # Check for specific integrations
        if "github" in desc_lower:
            return "github"
        if "slack" in desc_lower:
            return "slack"
        if "jira" in desc_lower:
            return "jira"
        if "linear" in desc_lower:
            return "linear"

        return service_map.get(category)

    async def generate_tool(self, spec: ToolSpec) -> GeneratedTool:
        """Generate tool code from specification."""
        result = GeneratedTool(spec=spec, tool_code="", test_code="", registry_entry="")
        result.status = GenerationStatus.GENERATING

        try:
            # Generate tool code
            result.tool_code = self._generate_tool_code(spec)

            # Generate test code
            result.test_code = self._generate_test_code(spec)

            # Generate registry entry
            result.registry_entry = self._generate_registry_entry(spec)

            result.status = GenerationStatus.COMPLETED

        except Exception as e:
            result.status = GenerationStatus.FAILED
            result.errors.append(str(e))

        return result

    def _generate_tool_code(self, spec: ToolSpec) -> str:
        """Generate the tool function code."""
        # Format parameters
        params_str = ", ".join(
            f'"{name}": {p["type"].__name__}' for name, p in spec.parameters.items()
        )

        # Generate docstring args
        args_doc = "\n                ".join(
            f"{name}: {p['description']}" for name, p in spec.parameters.items()
        )

        # Service getter
        if spec.service_dependency:
            service_get = f"service = _get_{spec.service_dependency}_service()"
        else:
            service_get = "# No service dependency"

        # Basic implementation placeholder
        implementation = textwrap.dedent(f"""
            # TODO: Implement {spec.name}
            # This is a generated stub - implement the actual logic
            result_data = "Operation completed"
        """).strip()

        return self.TOOL_TEMPLATE.format(
            name=spec.name,
            description=spec.description,
            parameters=params_str,
            docstring=spec.description,
            args_doc=args_doc,
            service_get=service_get,
            implementation=implementation,
            result_text='f"Result: {result_data}"',
        )

    def _generate_test_code(self, spec: ToolSpec) -> str:
        """Generate test code for the tool."""
        # Determine module from category
        module = spec.category.value.split(".")[0]  # Handle hierarchical categories

        # Class name
        class_name = "".join(word.capitalize() for word in spec.name.split("_"))

        # Test args
        test_args = {}
        for name, p in spec.parameters.items():
            match p["type"]:
                case builtins.str:
                    test_args[name] = f'"{name}_value"'
                case builtins.int:
                    test_args[name] = "10"
                case _:
                    test_args[name] = "None"

        test_args_str = ", ".join(f'"{k}": {v}' for k, v in test_args.items())

        return self.TEST_TEMPLATE.format(
            name=spec.name,
            module=module,
            service=spec.service_dependency or "project",
            class_name=class_name,
            mock_setup="# Add mock setup here",
            test_args=f"{{{test_args_str}}}",
            method="process",  # Generic method name
            assertions="# Add assertions here",
        )

    def _generate_registry_entry(self, spec: ToolSpec) -> str:
        """Generate registry entry for the tool."""
        return self.REGISTRY_TEMPLATE.format(
            name=spec.name,
            description=spec.description,
            category=spec.category.name,
            is_core=str(spec.is_core),
            keywords=repr(spec.search_keywords),
        )

    async def save_generated_tool(
        self, generated: GeneratedTool, module_name: str
    ) -> Path:
        """Save generated tool to file.

        For new integrations, creates a new module.
        For existing categories, appends to existing module.
        """
        module_path = self.output_dir / f"{module_name}_tools.py"

        # Create or append
        if module_path.exists():
            # Append to existing module
            with module_path.open("a") as f:
                f.write(f"\n\n{generated.tool_code}\n")
        else:
            # Create new module
            header = textwrap.dedent(f'''
                """Agent tools for {module_name} operations.

                Auto-generated module - edit with care.
                """

                from __future__ import annotations

                from typing import TYPE_CHECKING, Any

                from claude_code_sdk import tool

                if TYPE_CHECKING:
                    pass

                # Global service instance
                _{module_name}_service = None


                def set_{module_name}_service(service) -> None:
                    """Set the service instance for tools to use."""
                    global _{module_name}_service
                    _{module_name}_service = service


                def _get_{module_name}_service():
                    """Get service or raise if not initialized."""
                    if _{module_name}_service is None:
                        raise RuntimeError("{module_name} service not initialized.")
                    return _{module_name}_service


                # =============================================================================
                # {module_name.title()} Tools
                # =============================================================================

            ''')

            with module_path.open("w") as f:
                f.write(header)
                f.write(generated.tool_code)
                f.write("\n\n")
                f.write(f"# Export all tools\n")
                f.write(f"ALL_{module_name.upper()}_TOOLS = [\n")
                f.write(f"    {generated.spec.name},\n")
                f.write("]\n")

        return module_path


# =============================================================================
# MCP Tools for Tool Generation
# =============================================================================

_generator: ToolGenerator | None = None


def _get_generator() -> ToolGenerator:
    """Get or create the tool generator."""
    global _generator
    if _generator is None:
        _generator = ToolGenerator()
    return _generator


@tool(
    "generate_tool_spec",
    "Analyze a natural language description and generate a tool specification",
    {"description": str},
)
async def generate_tool_spec(args: dict[str, Any]) -> dict[str, Any]:
    """Generate a tool specification from description."""
    generator = _get_generator()
    description = args["description"]

    spec = await generator.analyze_description(description)

    # Format specification
    params_text = "\n".join(
        f"    - {name}: {p['type'].__name__} ({'required' if p['required'] else 'optional'})"
        for name, p in spec.parameters.items()
    )

    return {
        "content": [
            {
                "type": "text",
                "text": (
                    f"Tool Specification:\n"
                    f"  Name: {spec.name}\n"
                    f"  Description: {spec.description}\n"
                    f"  Category: {spec.category.value}\n"
                    f"  Service: {spec.service_dependency or 'none'}\n"
                    f"  Parameters:\n{params_text}\n"
                    f"  Keywords: {', '.join(spec.search_keywords)}"
                ),
            }
        ]
    }


@tool(
    "generate_tool_code",
    "Generate complete tool code from a specification",
    {"description": str, "name": str, "category": str},
)
async def generate_tool_code(args: dict[str, Any]) -> dict[str, Any]:
    """Generate tool code from description."""
    generator = _get_generator()
    description = args["description"]

    # Analyze and generate
    spec = await generator.analyze_description(description)

    # Override name/category if provided
    if args.get("name"):
        spec.name = args["name"]
    if args.get("category"):
        with contextlib.suppress(ValueError):
            spec.category = ToolCategory(args["category"])

    generated = await generator.generate_tool(spec)

    match generated.status:
        case GenerationStatus.FAILED:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Generation failed:\n" + "\n".join(generated.errors),
                    }
                ],
                "is_error": True,
            }
        case _:
            pass

    return {
        "content": [
            {
                "type": "text",
                "text": (
                    f"Generated Tool: {spec.name}\n"
                    f"{'=' * 50}\n\n"
                    f"TOOL CODE:\n```python\n{generated.tool_code}\n```\n\n"
                    f"TEST CODE:\n```python\n{generated.test_code}\n```\n\n"
                    f"REGISTRY ENTRY:\n```python\n{generated.registry_entry}\n```"
                ),
            }
        ]
    }


@tool(
    "create_tool_module",
    "Create a complete new tool module with generated tools",
    {"module_name": str, "tools": str},
)
async def create_tool_module(args: dict[str, Any]) -> dict[str, Any]:
    """Create a new tool module.

    Args:
        module_name: Name for the module (e.g., "github", "slack")
        tools: JSON array of tool descriptions
    """
    import json

    generator = _get_generator()
    module_name = args["module_name"]

    try:
        tool_descriptions = json.loads(args["tools"])
    except json.JSONDecodeError:
        # Treat as single tool description
        tool_descriptions = [args["tools"]]

    created_tools = []
    for desc in tool_descriptions:
        spec = await generator.analyze_description(desc)
        generated = await generator.generate_tool(spec)

        match generated.status:
            case GenerationStatus.COMPLETED:
                path = await generator.save_generated_tool(generated, module_name)
                created_tools.append((spec.name, path))
            case _:
                continue

    return {
        "content": [
            {
                "type": "text",
                "text": (
                    f"Created {len(created_tools)} tools in {module_name}_tools.py:\n"
                    + "\n".join(f"  - {name}" for name, _ in created_tools)
                ),
            }
        ]
    }


# Export tools
ALL_GENERATOR_TOOLS = [
    generate_tool_spec,
    generate_tool_code,
    create_tool_module,
]
