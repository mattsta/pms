"""File Utilities Plugin - Intermediate complexity example.

This example demonstrates:
- Multiple related tools in one plugin
- Capability requirements (filesystem_read)
- Configuration schema
- Event hooks
- Error handling
- Returning structured data

Usage:
    # Start with config
    pms plugin start file-utils --config file-utils-config.json

    # Use the tools
    pms plugin call file-utils.count_lines --arg path=./src
    pms plugin call file-utils.find_files --arg directory=. --arg pattern="**/*.py"
    pms plugin call file-utils.search_content --arg directory=./src --arg query="def main"
"""

from datetime import datetime
from pathlib import Path
from typing import Any

# Plugin configuration (set by on_load)
_config = {
    "default_directory": ".",
    "ignore_patterns": ["node_modules", ".git", "__pycache__", ".venv"],
}


def _should_ignore(path: Path) -> bool:
    """Check if path should be ignored based on config."""
    path_str = str(path)
    return any(pattern in path_str for pattern in _config["ignore_patterns"])


async def count_lines(path: str, pattern: str = "*") -> dict[str, Any]:
    """Count lines in files.

    Args:
        path: File or directory path
        pattern: Glob pattern for files (default: all files)

    Returns:
        Dictionary with line counts and statistics
    """
    target = Path(path).expanduser()

    if not target.exists():
        return {"error": f"Path not found: {path}"}

    results = {
        "path": str(target),
        "pattern": pattern,
        "files": [],
        "total_lines": 0,
        "total_files": 0,
    }

    if target.is_file():
        try:
            lines = len(target.read_text().splitlines())
            results["files"].append({"file": str(target), "lines": lines})
            results["total_lines"] = lines
            results["total_files"] = 1
        except Exception as e:
            results["files"].append({"file": str(target), "error": str(e)})
    else:
        for file_path in target.rglob(pattern):
            if file_path.is_file() and not _should_ignore(file_path):
                try:
                    lines = len(file_path.read_text().splitlines())
                    results["files"].append(
                        {
                            "file": str(file_path.relative_to(target)),
                            "lines": lines,
                        }
                    )
                    results["total_lines"] += lines
                    results["total_files"] += 1
                except Exception:
                    pass  # Skip binary/unreadable files

    return results


async def find_files(
    directory: str,
    pattern: str,
    max_results: int = 100,
) -> dict[str, Any]:
    """Find files matching a pattern.

    Args:
        directory: Directory to search
        pattern: Glob pattern (e.g., **/*.py)
        max_results: Maximum number of results

    Returns:
        List of matching files with metadata
    """
    target = Path(directory).expanduser()

    if not target.exists():
        return {"error": f"Directory not found: {directory}"}

    results = {
        "directory": str(target),
        "pattern": pattern,
        "files": [],
        "truncated": False,
    }

    count = 0
    for file_path in target.glob(pattern):
        if _should_ignore(file_path):
            continue

        if count >= max_results:
            results["truncated"] = True
            break

        stat = file_path.stat()
        results["files"].append(
            {
                "path": str(file_path.relative_to(target)),
                "size_bytes": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "is_dir": file_path.is_dir(),
            }
        )
        count += 1

    results["count"] = len(results["files"])
    return results


async def file_stats(path: str) -> dict[str, Any]:
    """Get detailed statistics about a file.

    Args:
        path: Path to file

    Returns:
        File statistics including size, dates, and content analysis
    """
    target = Path(path).expanduser()

    if not target.exists():
        return {"error": f"File not found: {path}"}

    stat = target.stat()

    result = {
        "path": str(target.absolute()),
        "name": target.name,
        "extension": target.suffix,
        "size_bytes": stat.st_size,
        "size_human": _human_size(stat.st_size),
        "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "accessed": datetime.fromtimestamp(stat.st_atime).isoformat(),
        "is_file": target.is_file(),
        "is_dir": target.is_dir(),
        "is_symlink": target.is_symlink(),
    }

    # Content analysis for text files
    if target.is_file() and stat.st_size < 1_000_000:  # < 1MB
        try:
            content = target.read_text()
            lines = content.splitlines()
            result["content_analysis"] = {
                "lines": len(lines),
                "characters": len(content),
                "words": len(content.split()),
                "blank_lines": sum(1 for line in lines if not line.strip()),
            }
        except UnicodeDecodeError:
            result["content_analysis"] = {"type": "binary"}

    return result


async def search_content(
    directory: str,
    query: str,
    file_pattern: str = "*",
) -> dict[str, Any]:
    """Search for text content in files.

    Args:
        directory: Directory to search
        query: Text to search for (case-insensitive)
        file_pattern: File pattern to search in

    Returns:
        Matching files with line numbers and context
    """
    target = Path(directory).expanduser()

    if not target.exists():
        return {"error": f"Directory not found: {directory}"}

    results = {
        "directory": str(target),
        "query": query,
        "matches": [],
        "total_matches": 0,
    }

    query_lower = query.lower()

    for file_path in target.rglob(file_pattern):
        if not file_path.is_file() or _should_ignore(file_path):
            continue

        try:
            content = file_path.read_text()
            lines = content.splitlines()

            file_matches = []
            for i, line in enumerate(lines, 1):
                if query_lower in line.lower():
                    file_matches.append(
                        {
                            "line_number": i,
                            "content": line.strip()[:200],  # Truncate long lines
                        }
                    )

            if file_matches:
                results["matches"].append(
                    {
                        "file": str(file_path.relative_to(target)),
                        "matches": file_matches[:10],  # Limit matches per file
                        "total_in_file": len(file_matches),
                    }
                )
                results["total_matches"] += len(file_matches)

        except UnicodeDecodeError, PermissionError:
            pass  # Skip binary/unreadable files

    return results


def _human_size(size_bytes: int) -> str:
    """Convert bytes to human-readable size."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


# =============================================================================
# Lifecycle Hooks
# =============================================================================


async def on_load(config: dict = None):
    """Initialize plugin with configuration."""
    global _config
    if config:
        _config.update(config)
    print(f"File Utils loaded. Default directory: {_config['default_directory']}")


async def on_unload():
    """Cleanup when plugin is unloaded."""
    print("File Utils plugin unloaded.")


# =============================================================================
# Event Hooks
# =============================================================================


async def on_task_created(task_id: str, title: str, **kwargs):
    """React to task creation events.

    This hook demonstrates how plugins can respond to PMS events.
    For example, auto-analyzing files mentioned in task titles.
    """
    # Look for file paths in task title
    if "/" in title or "." in title:
        print(f"[file-utils] New task may reference files: {title}")
        # Could auto-analyze mentioned files here
