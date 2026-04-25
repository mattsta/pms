"""Data Pipeline Plugin - ETL and Data Flow Integration Example.

This plugin demonstrates data integration patterns:
- Extract data from multiple sources (files, APIs, other plugins)
- Transform data using composable operations
- Load data to various destinations
- Aggregate data across plugins

The key integration concept: data flows seamlessly between plugins,
enabling complex data processing workflows.

Usage Examples:

    # Simple transform
    pms plugin call data-pipeline.transform \\
        --arg data='{"values": [1, 2, 3, 4, 5]}' \\
        --arg operations='[{"op": "map", "field": "values", "fn": "x * 2"}]'

    # Extract from file-utils output
    pms plugin call data-pipeline.extract \\
        --arg source=plugin \\
        --arg path="file-utils.count_lines" \\
        --arg options='{"args": {"path": "./src"}}'

    # Run full ETL pipeline
    pms plugin call data-pipeline.run_etl \\
        --arg name="project-analysis" \\
        --arg extract_config='{"source": "plugin", "path": "file-utils.count_lines"}' \\
        --arg transform_operations='[{"op": "filter", "field": "files", "condition": "lines > 100"}]' \\
        --arg load_config='{"destination": "json", "path": "./report.json"}'

    # Aggregate from multiple plugins
    pms plugin call data-pipeline.aggregate \\
        --arg sources='[
            {"plugin": "file-utils", "tool": "count_lines", "args": {"path": "./src"}},
            {"plugin": "github-integration", "tool": "list_issues", "args": {"owner": "my-org", "repo": "my-repo"}}
        ]' \\
        --arg merge_strategy=merge

Data Flow Architecture:
    ┌──────────────────────────────────────────────────────────────┐
    │                      Data Pipeline                            │
    │                                                               │
    │   ┌─────────┐     ┌─────────────┐     ┌──────────┐          │
    │   │ EXTRACT │ ──▶ │  TRANSFORM  │ ──▶ │   LOAD   │          │
    │   └────┬────┘     └──────┬──────┘     └────┬─────┘          │
    │        │                 │                  │                │
    │   ┌────┴────┐       ┌────┴────┐       ┌────┴────┐           │
    │   │  JSON   │       │   MAP   │       │  JSON   │           │
    │   │  CSV    │       │ FILTER  │       │  CSV    │           │
    │   │  API    │       │  GROUP  │       │ Plugin  │           │
    │   │ Plugin  │       │  SORT   │       │  API    │           │
    │   └─────────┘       └─────────┘       └─────────┘           │
    └──────────────────────────────────────────────────────────────┘
"""

import csv
import json
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any

# =============================================================================
# Configuration
# =============================================================================

_config = {
    "default_output_dir": "~/.pms/data",
    "cache_enabled": True,
}

_cache: dict[str, Any] = {}


# =============================================================================
# Transform Operations
# =============================================================================

# Safe evaluation for transform expressions
SAFE_OPS = {
    "+": lambda x, y: x + y,
    "-": lambda x, y: x - y,
    "*": lambda x, y: x * y,
    "/": lambda x, y: x / y if y != 0 else 0,
    "%": lambda x, y: x % y if y != 0 else 0,
    ">": lambda x, y: x > y,
    "<": lambda x, y: x < y,
    ">=": lambda x, y: x >= y,
    "<=": lambda x, y: x <= y,
    "==": lambda x, y: x == y,
    "!=": lambda x, y: x != y,
}


def _safe_eval(expr: str, context: dict) -> Any:
    """Safely evaluate simple expressions.

    Supports:
    - Variable references: x, value, item.field
    - Arithmetic: x * 2, x + y
    - Comparisons: x > 10, lines >= 100
    - Simple string operations: upper(x), lower(x)
    """
    expr = expr.strip()

    # Simple variable lookup
    if expr in context:
        return context[expr]

    # Nested field access (item.field)
    if "." in expr and not any(op in expr for op in SAFE_OPS):
        parts = expr.split(".")
        value = context
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return None
        return value

    # String functions
    for func in ["upper", "lower", "strip", "len"]:
        if expr.startswith(f"{func}(") and expr.endswith(")"):
            inner = expr[len(func) + 1 : -1]
            inner_val = _safe_eval(inner, context)
            if func == "upper" and isinstance(inner_val, str):
                return inner_val.upper()
            elif func == "lower" and isinstance(inner_val, str):
                return inner_val.lower()
            elif func == "strip" and isinstance(inner_val, str):
                return inner_val.strip()
            elif func == "len":
                return len(inner_val) if inner_val else 0
            return inner_val

    # Binary operations
    for op, fn in SAFE_OPS.items():
        if f" {op} " in expr:
            left, right = expr.split(f" {op} ", 1)
            left_val = _safe_eval(left.strip(), context)
            right_val = _safe_eval(right.strip(), context)

            # Handle numeric conversion
            if isinstance(left_val, str) and left_val.isdigit():
                left_val = int(left_val)
            if isinstance(right_val, str) and right_val.isdigit():
                right_val = int(right_val)

            try:
                return fn(left_val, right_val)
            except TypeError, ValueError:
                return None

    # Numeric literal
    try:
        if "." in expr:
            return float(expr)
        return int(expr)
    except ValueError:
        pass

    # String literal
    if (expr.startswith('"') and expr.endswith('"')) or (
        expr.startswith("'") and expr.endswith("'")
    ):
        return expr[1:-1]

    return expr


def _apply_transform(data: Any, operation: dict) -> Any:
    """Apply a single transformation operation."""
    op = operation.get("op")
    field = operation.get("field")

    if op == "map":
        # Apply function to each item in a list
        fn_expr = operation.get("fn", "x")
        if isinstance(data, dict) and field and field in data:
            items = data[field]
            if isinstance(items, list):
                data[field] = [
                    _safe_eval(
                        fn_expr,
                        {"x": item, **item} if isinstance(item, dict) else {"x": item},
                    )
                    for item in items
                ]
        elif isinstance(data, list):
            data = [
                _safe_eval(
                    fn_expr,
                    {"x": item, **item} if isinstance(item, dict) else {"x": item},
                )
                for item in data
            ]

    elif op == "filter":
        # Filter items based on condition
        condition = operation.get("condition", "true")
        if isinstance(data, dict) and field and field in data:
            items = data[field]
            if isinstance(items, list):
                data[field] = [
                    item
                    for item in items
                    if _safe_eval(
                        condition, item if isinstance(item, dict) else {"x": item}
                    )
                ]
        elif isinstance(data, list):
            data = [
                item
                for item in data
                if _safe_eval(
                    condition, item if isinstance(item, dict) else {"x": item}
                )
            ]

    elif op == "sort":
        # Sort items
        key_field = operation.get("key", field)
        reverse = operation.get("reverse", False)
        if isinstance(data, dict) and field and field in data:
            items = data[field]
            if isinstance(items, list):
                data[field] = sorted(
                    items,
                    key=lambda x: x.get(key_field, 0) if isinstance(x, dict) else x,
                    reverse=reverse,
                )
        elif isinstance(data, list):
            data = sorted(data, reverse=reverse)

    elif op == "group":
        # Group items by field
        key_field = operation.get("key")
        if isinstance(data, dict) and field and field in data:
            items = data[field]
            if isinstance(items, list) and key_field:
                groups: dict[str, list] = {}
                for item in items:
                    if isinstance(item, dict):
                        group_key = str(item.get(key_field, "other"))
                        if group_key not in groups:
                            groups[group_key] = []
                        groups[group_key].append(item)
                data[field] = groups

    elif op == "select":
        # Select specific fields
        fields = operation.get("fields", [])
        if isinstance(data, dict) and field and field in data:
            items = data[field]
            if isinstance(items, list):
                data[field] = [
                    {k: item.get(k) for k in fields if k in item}
                    if isinstance(item, dict)
                    else item
                    for item in items
                ]
        elif isinstance(data, dict):
            data = {k: v for k, v in data.items() if k in fields}

    elif op == "rename":
        # Rename fields
        mapping = operation.get("mapping", {})
        if isinstance(data, dict):
            for old_name, new_name in mapping.items():
                if old_name in data:
                    data[new_name] = data.pop(old_name)

    elif op == "add_field":
        # Add computed field
        new_field = operation.get("name")
        value_expr = operation.get("value", "null")
        if isinstance(data, dict) and new_field:
            if field and field in data and isinstance(data[field], list):
                # Add to each item in list
                for item in data[field]:
                    if isinstance(item, dict):
                        item[new_field] = _safe_eval(value_expr, item)
            else:
                # Add to data itself
                data[new_field] = _safe_eval(value_expr, data)

    elif op == "flatten":
        # Flatten nested structure
        if isinstance(data, dict) and field and field in data:
            nested = data[field]
            if isinstance(nested, list):
                flattened = []
                for item in nested:
                    if isinstance(item, list):
                        flattened.extend(item)
                    else:
                        flattened.append(item)
                data[field] = flattened

    return data


# =============================================================================
# Tool Implementations
# =============================================================================


async def extract(
    source: str,
    path: str,
    options: dict = None,
) -> dict[str, Any]:
    """Extract data from various sources.

    Args:
        source: Source type (json, csv, api, plugin)
        path: Path to source:
            - For json/csv: file path
            - For api: URL
            - For plugin: "plugin-name.tool-name"
        options: Source-specific options:
            - For csv: delimiter, headers
            - For api: headers, method
            - For plugin: args dict

    Returns:
        Extracted data with metadata
    """
    options = options or {}
    result = {
        "source": source,
        "path": path,
        "extracted_at": datetime.now().isoformat(),
    }

    if source == "json":
        file_path = Path(path).expanduser()
        if not file_path.exists():
            return {"error": f"File not found: {path}"}
        result["data"] = json.loads(file_path.read_text())
        result["rows"] = len(result["data"]) if isinstance(result["data"], list) else 1

    elif source == "csv":
        file_path = Path(path).expanduser()
        if not file_path.exists():
            return {"error": f"File not found: {path}"}
        delimiter = options.get("delimiter", ",")
        content = file_path.read_text()
        reader = csv.DictReader(StringIO(content), delimiter=delimiter)
        result["data"] = list(reader)
        result["rows"] = len(result["data"])

    elif source == "plugin":
        # Extract from another plugin's tool
        # In production, would call registry.call_tool()
        plugin_tool = path.split(".")
        if len(plugin_tool) != 2:
            return {"error": f"Invalid plugin path: {path}. Use 'plugin.tool'"}

        plugin_name, tool_name = plugin_tool
        args = options.get("args", {})

        # Simulate plugin call
        result["data"] = {
            "simulated": True,
            "plugin": plugin_name,
            "tool": tool_name,
            "args": args,
            "note": "In production, this would call the actual plugin",
        }
        result["rows"] = 1

    elif source == "api":
        # HTTP API extraction
        # In production, would use httpx
        result["data"] = {
            "simulated": True,
            "url": path,
            "note": "API extraction simulated",
        }
        result["rows"] = 1

    else:
        return {"error": f"Unknown source type: {source}"}

    return result


async def transform(
    data: dict,
    operations: list[dict],
) -> dict[str, Any]:
    """Apply transformations to data.

    Args:
        data: Input data to transform
        operations: List of transformation operations:
            - op: Operation type (map, filter, sort, group, select, rename, add_field, flatten)
            - field: Field to operate on (optional, for nested data)
            - Additional op-specific parameters

    Returns:
        Transformed data with operation log

    Examples:
        # Double all values
        {"op": "map", "field": "values", "fn": "x * 2"}

        # Filter to large files
        {"op": "filter", "field": "files", "condition": "lines > 100"}

        # Sort by size descending
        {"op": "sort", "field": "files", "key": "size", "reverse": true}

        # Group by language
        {"op": "group", "field": "repos", "key": "language"}

        # Select specific fields
        {"op": "select", "fields": ["name", "url", "stars"]}

        # Add computed field
        {"op": "add_field", "field": "files", "name": "is_large", "value": "lines > 100"}
    """
    result_data = data.copy() if isinstance(data, dict) else data
    operation_log = []

    for i, op in enumerate(operations):
        try:
            result_data = _apply_transform(result_data, op)
            operation_log.append(
                {
                    "step": i + 1,
                    "operation": op.get("op"),
                    "status": "success",
                }
            )
        except Exception as e:
            operation_log.append(
                {
                    "step": i + 1,
                    "operation": op.get("op"),
                    "status": "error",
                    "error": str(e),
                }
            )

    return {
        "data": result_data,
        "operations_applied": len(operations),
        "operation_log": operation_log,
    }


async def load(
    data: dict,
    destination: str,
    path: str,
) -> dict[str, Any]:
    """Load transformed data to destination.

    Args:
        data: Data to load
        destination: Destination type (json, csv, plugin)
        path: Destination path

    Returns:
        Load status and metadata
    """
    result = {
        "destination": destination,
        "path": path,
        "loaded_at": datetime.now().isoformat(),
    }

    if destination == "json":
        output_path = Path(path).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(data, indent=2))
        result["success"] = True
        result["bytes_written"] = output_path.stat().st_size

    elif destination == "csv":
        output_path = Path(path).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Handle list of dicts
        if isinstance(data, list) and data and isinstance(data[0], dict):
            with output_path.open("w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=data[0].keys())
                writer.writeheader()
                writer.writerows(data)
            result["success"] = True
            result["rows_written"] = len(data)
        elif isinstance(data, dict) and "data" in data:
            # Unwrap nested data
            inner = data["data"]
            if isinstance(inner, list) and inner and isinstance(inner[0], dict):
                with output_path.open("w", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=inner[0].keys())
                    writer.writeheader()
                    writer.writerows(inner)
                result["success"] = True
                result["rows_written"] = len(inner)
            else:
                result["success"] = False
                result["error"] = "Data not suitable for CSV format"
        else:
            result["success"] = False
            result["error"] = "Data must be a list of dicts for CSV output"

    elif destination == "plugin":
        # Send to another plugin
        # In production, would call registry.call_tool()
        result["success"] = True
        result["note"] = f"Would send data to plugin: {path}"
        result["simulated"] = True

    else:
        result["success"] = False
        result["error"] = f"Unknown destination: {destination}"

    return result


async def run_etl(
    name: str,
    extract_config: dict,
    transform_operations: list[dict],
    load_config: dict,
) -> dict[str, Any]:
    """Run complete ETL pipeline.

    Combines extract, transform, and load into a single operation.

    Args:
        name: Pipeline name for logging
        extract_config: Config for extract step (source, path, options)
        transform_operations: List of transform operations
        load_config: Config for load step (destination, path)

    Returns:
        Complete ETL results
    """
    start_time = datetime.now()

    result = {
        "pipeline": name,
        "started_at": start_time.isoformat(),
        "steps": {},
    }

    # Extract
    extract_result = await extract(
        source=extract_config.get("source", "json"),
        path=extract_config.get("path", ""),
        options=extract_config.get("options"),
    )

    if "error" in extract_result:
        result["success"] = False
        result["error"] = f"Extract failed: {extract_result['error']}"
        return result

    result["steps"]["extract"] = {
        "status": "success",
        "rows": extract_result.get("rows", 0),
    }

    # Transform
    transform_result = await transform(
        data=extract_result.get("data", {}),
        operations=transform_operations,
    )

    result["steps"]["transform"] = {
        "status": "success",
        "operations_applied": transform_result.get("operations_applied", 0),
    }

    # Load
    load_result = await load(
        data=transform_result.get("data", {}),
        destination=load_config.get("destination", "json"),
        path=load_config.get("path", ""),
    )

    result["steps"]["load"] = {
        "status": "success" if load_result.get("success") else "error",
        "destination": load_config.get("destination"),
    }

    end_time = datetime.now()
    result["completed_at"] = end_time.isoformat()
    result["duration_seconds"] = (end_time - start_time).total_seconds()
    result["success"] = all(
        step.get("status") == "success" for step in result["steps"].values()
    )

    return result


async def aggregate(
    sources: list[dict],
    merge_strategy: str = "concat",
) -> dict[str, Any]:
    """Aggregate data from multiple plugin sources.

    Demonstrates cross-plugin data collection and merging.

    Args:
        sources: List of source definitions:
            - plugin: Plugin name
            - tool: Tool name
            - args: Arguments for the tool
        merge_strategy: How to combine results:
            - concat: Concatenate lists
            - merge: Merge dicts (later overwrites earlier)
            - join: Join on common field (requires 'join_key' in sources)

    Returns:
        Aggregated data from all sources
    """
    collected = []

    for source in sources:
        plugin = source.get("plugin")
        tool = source.get("tool")
        args = source.get("args", {})

        # In production, would call registry.call_tool()
        # Simulate collection
        collected.append(
            {
                "source": f"{plugin}.{tool}",
                "args": args,
                "data": {
                    "simulated": True,
                    "plugin": plugin,
                    "tool": tool,
                },
            }
        )

    # Apply merge strategy
    if merge_strategy == "concat":
        merged_data = []
        for item in collected:
            data = item.get("data", {})
            if isinstance(data, list):
                merged_data.extend(data)
            else:
                merged_data.append(data)
        result_data = merged_data

    elif merge_strategy == "merge":
        result_data = {}
        for item in collected:
            data = item.get("data", {})
            if isinstance(data, dict):
                result_data.update(data)

    elif merge_strategy == "join":
        # More complex join would require join_key
        result_data = collected  # Simplified

    else:
        result_data = collected

    return {
        "sources_count": len(sources),
        "merge_strategy": merge_strategy,
        "data": result_data,
        "aggregated_at": datetime.now().isoformat(),
    }


# =============================================================================
# Lifecycle
# =============================================================================


async def on_load(config: dict = None):
    """Initialize data pipeline plugin."""
    global _config
    if config:
        _config.update(config)

    output_dir = Path(_config["default_output_dir"]).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[data-pipeline] Initialized. Output directory: {output_dir}")


async def on_unload():
    """Cleanup data pipeline plugin."""
    _cache.clear()
    print("[data-pipeline] Plugin unloaded")
