"""Structured logging configuration using loguru for PMS.

Loguru provides structured, beautiful logging out of the box with:
- Automatic JSON serialization
- Correlation ID support via context
- Easy configuration
- Lazy evaluation
- Stack trace capturing

Usage:
    from pms.config.logging import logger

    logger.info("Project created", project_id="<project-id>", duration_ms=42)

    # With correlation ID context
    with logger.contextualize(correlation_id="req_abc123"):
        logger.info("Operation started")
        # correlation_id automatically included in all logs
"""

from os import environ
from pathlib import Path
from sys import stderr
from uuid import uuid4

from loguru import logger

# =============================================================================
# Configuration
# =============================================================================

# Remove default handler
logger.remove()

# Add console handler (human-readable) - shows extra context
logger.add(
    stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level> | {extra}",
    level="INFO",
    colorize=True,
)

# Add file handler (JSON structured)
log_dir = Path(environ.get("PMS_LOG_DIR", str(Path.home() / ".pms" / "logs")))
log_dir.mkdir(parents=True, exist_ok=True)

logger.add(
    log_dir / "pms.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
    level="DEBUG",
    rotation="10 MB",
    retention="1 week",
    compression="gz",
    serialize=True,  # JSON output
)

# Add error file for easy error tracking
logger.add(
    log_dir / "errors.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
    level="ERROR",
    rotation="5 MB",
    retention="2 weeks",
    backtrace=True,
    diagnose=True,
)


# =============================================================================
# Helpers
# =============================================================================


def new_correlation_id() -> str:
    """Generate a new correlation ID."""
    return f"req_{uuid4().hex[:12]}"


# Export logger as the main interface
__all__ = ["logger", "new_correlation_id"]
