"""Workflow Orchestrator - Multi-Plugin Integration Example.

This plugin demonstrates the power of plugin integration:
- Orchestrating multiple plugins in pipelines
- Data flowing between plugin tool calls
- Event-driven cross-plugin automation
- Template-based workflow creation

Architecture:
    ┌──────────────────────────────────────────────────────────┐
    │              Workflow Orchestrator                        │
    │  ┌──────────┐  ┌──────────┐  ┌──────────┐               │
    │  │ Pipeline │  │ Pipeline │  │ Pipeline │   ...          │
    │  │    A     │  │    B     │  │    C     │               │
    │  └────┬─────┘  └────┬─────┘  └────┬─────┘               │
    └───────┼──────────────┼──────────────┼────────────────────┘
            │              │              │
    ┌───────┴──────────────┴──────────────┴────────────────────┐
    │                    Plugin Registry                        │
    │  ┌───────────┐  ┌────────────┐  ┌──────────────────┐    │
    │  │file-utils │  │  github    │  │ plugin-factory   │    │
    │  └───────────┘  └────────────┘  └──────────────────┘    │
    └──────────────────────────────────────────────────────────┘

Usage Examples:

    # Define a pipeline
    pms plugin call workflow-orchestrator.define_pipeline \\
        --arg name=code-analysis \\
        --arg steps='[
            {"plugin": "file-utils", "tool": "count_lines", "args": {"path": "$input.directory"}},
            {"plugin": "file-utils", "tool": "search_content", "args": {"directory": "$input.directory", "query": "TODO"}},
            {"plugin": "file-utils", "tool": "search_content", "args": {"directory": "$input.directory", "query": "FIXME"}}
        ]'

    # Run the pipeline
    pms plugin call workflow-orchestrator.run_pipeline \\
        --arg pipeline=code-analysis \\
        --arg input='{"directory": "./src"}'

    # Comprehensive project analysis
    pms plugin call workflow-orchestrator.analyze_project \\
        --arg directory=./my-project

    # Set up automated workflows
    pms plugin call workflow-orchestrator.create_project_workflow \\
        --arg project_name="My App" \\
        --arg template=development
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

# =============================================================================
# Configuration
# =============================================================================

_config = {
    "pipelines_dir": "~/.pms/pipelines",
    "auto_analyze": True,
    "default_plugins": ["file-utils", "github-integration"],
}

# In-memory pipeline storage (would persist to disk in production)
_pipelines: dict[str, dict] = {}

# Built-in pipeline templates
PIPELINE_TEMPLATES = {
    "code-analysis": {
        "description": "Analyze codebase for metrics, TODOs, and patterns",
        "steps": [
            {
                "name": "count_lines",
                "plugin": "file-utils",
                "tool": "count_lines",
                "args": {"path": "$input.directory", "pattern": "*.py"},
            },
            {
                "name": "find_todos",
                "plugin": "file-utils",
                "tool": "search_content",
                "args": {"directory": "$input.directory", "query": "TODO"},
            },
            {
                "name": "find_fixmes",
                "plugin": "file-utils",
                "tool": "search_content",
                "args": {"directory": "$input.directory", "query": "FIXME"},
            },
        ],
    },
    "github-sync": {
        "description": "Sync GitHub issues to PMS and analyze",
        "steps": [
            {
                "name": "list_issues",
                "plugin": "github-integration",
                "tool": "list_issues",
                "args": {
                    "owner": "$input.owner",
                    "repo": "$input.repo",
                    "state": "open",
                },
            },
            {
                "name": "sync_tasks",
                "plugin": "github-integration",
                "tool": "sync_to_tasks",
                "args": {
                    "owner": "$input.owner",
                    "repo": "$input.repo",
                    "project_name": "$input.project_name",
                },
            },
        ],
    },
    "project-setup": {
        "description": "Full project setup with code analysis and GitHub sync",
        "steps": [
            {
                "name": "analyze_code",
                "plugin": "file-utils",
                "tool": "count_lines",
                "args": {"path": "$input.directory"},
            },
            {
                "name": "find_files",
                "plugin": "file-utils",
                "tool": "find_files",
                "args": {"directory": "$input.directory", "pattern": "**/*"},
            },
        ],
    },
}

# Workflow templates for different project types
WORKFLOW_TEMPLATES = {
    "development": {
        "description": "Standard development workflow",
        "triggers": [
            {
                "event": "task_created",
                "filter": {"has_tag": "feature"},
                "pipeline": "code-analysis",
            },
            {
                "event": "task_completed",
                "filter": {"has_tag": "github"},
                "action": "close_github_issue",
            },
        ],
        "pipelines": ["code-analysis"],
    },
    "devops": {
        "description": "DevOps-focused workflow with deployment tracking",
        "triggers": [
            {
                "event": "task_completed",
                "filter": {"has_tag": "deploy"},
                "action": "notify_deployment",
            },
        ],
        "pipelines": ["code-analysis", "github-sync"],
    },
    "documentation": {
        "description": "Documentation-focused workflow",
        "triggers": [
            {
                "event": "task_created",
                "filter": {"has_tag": "docs"},
                "pipeline": "code-analysis",
            },
        ],
        "pipelines": ["code-analysis"],
    },
}


# =============================================================================
# Pipeline Execution Engine
# =============================================================================


def _resolve_variable(value: Any, context: dict) -> Any:
    """Resolve $input.xxx and $step.xxx variables."""
    if not isinstance(value, str):
        return value

    # Match $input.key or $step.name.key patterns
    pattern = r"\$(\w+)\.(\w+)(?:\.(\w+))?"

    def replacer(match):
        source = match.group(1)  # input or step name
        key1 = match.group(2)
        key2 = match.group(3)

        if source == "input":
            result = context.get("input", {}).get(key1)
        else:
            # Reference to previous step output
            step_output = context.get("steps", {}).get(source, {})
            result = step_output.get(key1)
            if key2 and isinstance(result, dict):
                result = result.get(key2)

        return str(result) if result is not None else match.group(0)

    if value.startswith("$") and re.match(pattern, value):
        # Full variable replacement
        match = re.match(pattern, value)
        if match:
            source = match.group(1)
            key1 = match.group(2)
            key2 = match.group(3)

            if source == "input":
                result = context.get("input", {}).get(key1)
            else:
                step_output = context.get("steps", {}).get(source, {})
                result = step_output.get(key1)
                if key2 and isinstance(result, dict):
                    result = result.get(key2)

            return result if result is not None else value

    # Partial variable replacement in strings
    return re.sub(pattern, replacer, value)


def _resolve_args(args: dict, context: dict) -> dict:
    """Resolve all variables in step arguments."""
    resolved = {}
    for key, value in args.items():
        if isinstance(value, dict):
            resolved[key] = _resolve_args(value, context)
        elif isinstance(value, list):
            resolved[key] = [_resolve_variable(v, context) for v in value]
        else:
            resolved[key] = _resolve_variable(value, context)
    return resolved


async def _execute_step(
    step: dict,
    context: dict,
    registry: Any = None,
) -> dict[str, Any]:
    """Execute a single pipeline step.

    In a real implementation, this would call the plugin registry
    to execute the tool. For this example, we simulate the execution.
    """
    plugin = step.get("plugin")
    tool = step.get("tool")
    args = step.get("args", {})

    # Resolve variables
    resolved_args = _resolve_args(args, context)

    # In production: result = await registry.call_tool(f"{plugin}.{tool}", **resolved_args)
    # For demo, we simulate results
    result = {
        "plugin": plugin,
        "tool": tool,
        "args": resolved_args,
        "status": "success",
        "simulated": True,
        "timestamp": datetime.now().isoformat(),
    }

    # Simulate some realistic outputs based on tool
    if tool == "count_lines":
        result["output"] = {
            "total_lines": 1500,
            "total_files": 25,
            "path": resolved_args.get("path", "."),
        }
    elif tool == "search_content":
        result["output"] = {
            "total_matches": 12,
            "query": resolved_args.get("query", ""),
            "matches": [
                {
                    "file": "src/main.py",
                    "line": 42,
                    "content": f"{resolved_args.get('query', 'TODO')}: Fix this",
                },
            ],
        }
    elif tool == "list_issues":
        result["output"] = {
            "count": 5,
            "issues": [{"number": 1, "title": "Sample issue"}],
        }
    elif tool == "sync_to_tasks":
        result["output"] = {
            "synced": 5,
            "project": resolved_args.get("project_name", "Unknown"),
        }
    else:
        result["output"] = {"data": "simulated output"}

    return result


# =============================================================================
# Tool Implementations
# =============================================================================


async def define_pipeline(
    name: str,
    steps: list[dict],
    description: str = "",
) -> dict[str, Any]:
    """Create a reusable workflow pipeline.

    Pipelines define multi-step workflows that orchestrate multiple
    plugins. Steps can reference previous step outputs using variables.

    Args:
        name: Unique pipeline name
        steps: List of step definitions:
            - plugin: Plugin name
            - tool: Tool name
            - args: Arguments (can use $input.xxx, $stepname.xxx)
            - name: Optional step name for referencing
        description: Human-readable description

    Returns:
        Pipeline definition and validation status

    Example:
        define_pipeline(
            name="my-pipeline",
            steps=[
                {"plugin": "file-utils", "tool": "count_lines", "args": {"path": "$input.dir"}},
                {"name": "search", "plugin": "file-utils", "tool": "search_content",
                 "args": {"directory": "$input.dir", "query": "TODO"}}
            ]
        )
    """
    # Validate steps
    errors = []
    for i, step in enumerate(steps):
        if "plugin" not in step:
            errors.append(f"Step {i}: missing 'plugin'")
        if "tool" not in step:
            errors.append(f"Step {i}: missing 'tool'")

    if errors:
        return {"success": False, "errors": errors}

    # Store pipeline
    pipeline = {
        "name": name,
        "description": description,
        "steps": steps,
        "created_at": datetime.now().isoformat(),
    }
    _pipelines[name] = pipeline

    # Persist to disk
    pipelines_dir = Path(_config["pipelines_dir"]).expanduser()
    pipelines_dir.mkdir(parents=True, exist_ok=True)
    pipeline_file = pipelines_dir / f"{name}.json"
    pipeline_file.write_text(json.dumps(pipeline, indent=2))

    return {
        "success": True,
        "pipeline": name,
        "steps": len(steps),
        "file": str(pipeline_file),
    }


async def run_pipeline(
    pipeline: str,
    input: dict = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Execute a multi-step workflow pipeline.

    Runs all steps in sequence, passing data between them using
    the variable resolution system.

    Args:
        pipeline: Pipeline name or inline JSON definition
        input: Initial input data available as $input.xxx
        dry_run: If True, show what would be executed without running

    Returns:
        Results from all pipeline steps

    Example:
        run_pipeline(
            pipeline="code-analysis",
            input={"directory": "./src"}
        )
    """
    input = input or {}

    # Load pipeline
    if pipeline in _pipelines:
        pipeline_def = _pipelines[pipeline]
    elif pipeline in PIPELINE_TEMPLATES:
        pipeline_def = PIPELINE_TEMPLATES[pipeline]
    else:
        # Try to load from disk
        pipelines_dir = Path(_config["pipelines_dir"]).expanduser()
        pipeline_file = pipelines_dir / f"{pipeline}.json"
        if pipeline_file.exists():
            pipeline_def = json.loads(pipeline_file.read_text())
        else:
            # Try parsing as inline JSON
            try:
                pipeline_def = json.loads(pipeline)
            except json.JSONDecodeError:
                return {
                    "success": False,
                    "error": f"Pipeline not found: {pipeline}",
                    "available": list(_pipelines.keys())
                    + list(PIPELINE_TEMPLATES.keys()),
                }

    steps = pipeline_def.get("steps", [])

    if dry_run:
        # Preview mode
        preview = []
        context = {"input": input, "steps": {}}

        for i, step in enumerate(steps):
            resolved_args = _resolve_args(step.get("args", {}), context)
            preview.append(
                {
                    "step": i + 1,
                    "name": step.get("name", f"step_{i}"),
                    "plugin": step.get("plugin"),
                    "tool": step.get("tool"),
                    "resolved_args": resolved_args,
                }
            )
            # Simulate step output for subsequent variable resolution
            step_name = step.get("name", f"step_{i}")
            context["steps"][step_name] = {"simulated": True}

        return {
            "dry_run": True,
            "pipeline": pipeline_def.get("name", "inline"),
            "steps": preview,
        }

    # Execute pipeline
    context = {"input": input, "steps": {}}
    results = []
    start_time = datetime.now()

    for i, step in enumerate(steps):
        step_name = step.get("name", f"step_{i}")

        try:
            result = await _execute_step(step, context)
            context["steps"][step_name] = result.get("output", {})
            results.append(
                {
                    "step": i + 1,
                    "name": step_name,
                    "status": "success",
                    "result": result,
                }
            )
        except Exception as e:
            results.append(
                {
                    "step": i + 1,
                    "name": step_name,
                    "status": "error",
                    "error": str(e),
                }
            )
            # Stop pipeline on error
            break

    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    return {
        "success": all(r["status"] == "success" for r in results),
        "pipeline": pipeline_def.get("name", "inline"),
        "steps_completed": len([r for r in results if r["status"] == "success"]),
        "total_steps": len(steps),
        "duration_seconds": duration,
        "results": results,
    }


async def list_pipelines() -> dict[str, Any]:
    """List all defined pipelines.

    Returns:
        Dictionary of available pipelines with their descriptions
    """
    # Combine in-memory, templates, and persisted pipelines
    all_pipelines = {}

    # Built-in templates
    for name, template in PIPELINE_TEMPLATES.items():
        all_pipelines[name] = {
            "type": "template",
            "description": template.get("description", ""),
            "steps": len(template.get("steps", [])),
        }

    # In-memory pipelines
    for name, pipeline in _pipelines.items():
        all_pipelines[name] = {
            "type": "custom",
            "description": pipeline.get("description", ""),
            "steps": len(pipeline.get("steps", [])),
            "created_at": pipeline.get("created_at"),
        }

    # Persisted pipelines
    pipelines_dir = Path(_config["pipelines_dir"]).expanduser()
    if pipelines_dir.exists():
        for pipeline_file in pipelines_dir.glob("*.json"):
            name = pipeline_file.stem
            if name not in all_pipelines:
                try:
                    data = json.loads(pipeline_file.read_text())
                    all_pipelines[name] = {
                        "type": "persisted",
                        "description": data.get("description", ""),
                        "steps": len(data.get("steps", [])),
                        "file": str(pipeline_file),
                    }
                except Exception:
                    pass

    return {"pipelines": all_pipelines, "count": len(all_pipelines)}


async def analyze_project(
    directory: str,
    plugins: list[str] = None,
) -> dict[str, Any]:
    """Run comprehensive project analysis using multiple plugins.

    This demonstrates integration: running multiple plugins in
    parallel/sequence to gather comprehensive project information.

    Args:
        directory: Project directory to analyze
        plugins: Specific plugins to use (default: all available)

    Returns:
        Comprehensive analysis results from all plugins
    """
    plugins = plugins or _config["default_plugins"]
    directory = str(Path(directory).expanduser().absolute())

    analysis = {
        "directory": directory,
        "timestamp": datetime.now().isoformat(),
        "plugins_used": plugins,
        "results": {},
    }

    # Run code analysis pipeline if file-utils is available
    if "file-utils" in plugins:
        code_result = await run_pipeline(
            pipeline="code-analysis",
            input={"directory": directory},
        )
        analysis["results"]["code_analysis"] = code_result

    # Check for GitHub repo if github-integration is available
    if "github-integration" in plugins:
        # Check if .git exists
        git_dir = Path(directory) / ".git"
        if git_dir.exists():
            analysis["results"]["github"] = {
                "has_git": True,
                "note": "GitHub integration available - use sync_to_tasks to import issues",
            }
        else:
            analysis["results"]["github"] = {"has_git": False}

    # Summary
    analysis["summary"] = {
        "plugins_checked": len(plugins),
        "analyses_completed": len(analysis["results"]),
    }

    return analysis


async def create_project_workflow(
    project_name: str,
    template: str = "development",
) -> dict[str, Any]:
    """Set up automated workflows for a project.

    Creates triggers and pipelines based on workflow templates.

    Args:
        project_name: Name of the PMS project
        template: Workflow template (development, devops, documentation)

    Returns:
        Configured workflow information
    """
    if template not in WORKFLOW_TEMPLATES:
        return {
            "success": False,
            "error": f"Unknown template: {template}",
            "available": list(WORKFLOW_TEMPLATES.keys()),
        }

    workflow_def = WORKFLOW_TEMPLATES[template]

    # In production, this would register event hooks with the system
    workflow = {
        "project": project_name,
        "template": template,
        "description": workflow_def["description"],
        "triggers": workflow_def["triggers"],
        "pipelines": workflow_def["pipelines"],
        "created_at": datetime.now().isoformat(),
    }

    return {
        "success": True,
        "workflow": workflow,
        "next_steps": [
            f"Triggers registered for project '{project_name}'",
            f"Pipelines available: {', '.join(workflow_def['pipelines'])}",
            "Events will auto-trigger configured actions",
        ],
    }


# =============================================================================
# Event Hooks (Cross-Plugin Automation)
# =============================================================================


async def on_project_created(project_id: str, name: str, **kwargs):
    """Handle project creation - optionally auto-analyze.

    This demonstrates cross-plugin automation triggered by
    PMS core events.
    """
    if _config["auto_analyze"]:
        print(f"[workflow] New project '{name}' - triggering analysis...")
        # In production, would get project directory and run analysis
        # For now, just log
        print(f"[workflow] Project {name} ready for workflows")


async def on_task_completed(task_id: str, title: str, tags: list = None, **kwargs):
    """Handle task completion - trigger workflow actions.

    Can trigger follow-up pipelines based on task tags.
    """
    tags = tags or []

    # Check for workflow triggers
    for tag in tags:
        if tag.startswith("workflow:"):
            pipeline_name = tag.replace("workflow:", "")
            print(
                f"[workflow] Task completed with workflow tag - triggering: {pipeline_name}"
            )
            # Would run the pipeline here


async def on_plugin_started(plugin_name: str, **kwargs):
    """Handle plugin startup - track available capabilities.

    Updates the orchestrator's understanding of available tools.
    """
    print(f"[workflow] Plugin '{plugin_name}' started - capabilities updated")


# =============================================================================
# Lifecycle
# =============================================================================


async def on_load(config: dict = None):
    """Initialize workflow orchestrator."""
    global _config
    if config:
        _config.update(config)

    # Ensure pipelines directory exists
    pipelines_dir = Path(_config["pipelines_dir"]).expanduser()
    pipelines_dir.mkdir(parents=True, exist_ok=True)

    # Load persisted pipelines
    for pipeline_file in pipelines_dir.glob("*.json"):
        try:
            data = json.loads(pipeline_file.read_text())
            _pipelines[data["name"]] = data
        except Exception:
            pass

    print(f"[workflow] Orchestrator initialized")
    print(f"[workflow] {len(PIPELINE_TEMPLATES)} built-in templates available")
    print(f"[workflow] {len(_pipelines)} custom pipelines loaded")


async def on_unload():
    """Cleanup workflow orchestrator."""
    print("[workflow] Orchestrator unloaded")
