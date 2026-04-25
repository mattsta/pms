"""Configuration management using Pydantic Settings."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from pms.runtime.defaults import LOCAL_SERVER_DEFAULT_BASE_URL


def get_env_file_path() -> Path:
    """Return the config env file path for the current execution context."""
    override = os.environ.get("PMS_ENV_FILE")
    if override:
        return Path(override)
    return Path(".env")


def get_default_data_dir() -> Path:
    """Get the default data directory for PMS."""
    return Path.home() / ".pms"


def get_default_db_path() -> Path:
    """Get the default database path."""
    return get_default_data_dir() / "pms.db"


def get_default_log_dir() -> Path:
    """Get the default log directory."""
    return get_default_data_dir() / "logs"


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    model_config = SettingsConfigDict(
        env_prefix="PMS_",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database settings
    database_path: Path = Field(
        default_factory=get_default_db_path,
        description="Path to SQLite database file",
    )
    database_echo: bool = Field(
        default=False,
        description="Echo SQL queries for debugging",
    )
    sqlite_busy_timeout_ms: int = Field(
        default=30_000,
        description="SQLite busy timeout in milliseconds for transient lock contention",
    )
    sqlite_lock_retry_count: int = Field(
        default=5,
        description="How many times SQLite operations should retry on transient lock errors",
    )
    sqlite_lock_retry_delay_ms: int = Field(
        default=200,
        description="Base retry delay in milliseconds between SQLite lock retries",
    )
    sqlite_journal_mode: Literal[
        "DELETE", "TRUNCATE", "PERSIST", "MEMORY", "WAL", "OFF"
    ] = Field(
        default="WAL",
        description="SQLite journal mode",
    )
    sqlite_synchronous: Literal["OFF", "NORMAL", "FULL", "EXTRA"] = Field(
        default="NORMAL",
        description="SQLite synchronous mode",
    )
    write_mode: Literal["direct", "prefer_server", "require_server"] = Field(
        default="prefer_server",
        description=(
            "How PMS should handle writes: direct SQLite, prefer a local/server API "
            "when available, or require the server path"
        ),
    )
    server_base_url: str = Field(
        default=LOCAL_SERVER_DEFAULT_BASE_URL,
        description="Preferred PMS API server base URL for server-backed workflows",
    )
    api_key_path: Path | None = Field(
        default=None,
        description="Optional local API key file for server-backed CLI delegation",
    )
    current_actor_id: str | None = Field(
        default=None,
        description="Preferred current actor ref for --mine and actor-aware workflow commands",
    )

    # Data directory
    data_dir: Path = Field(
        default_factory=get_default_data_dir,
        description="Directory for PMS data files",
    )

    # Agent settings
    agent_model: str = Field(
        default="claude-sonnet-4-20250514",
        description="Default Claude model for agents",
    )
    agent_max_turns: int = Field(
        default=20,
        description="Maximum turns per agent interaction",
    )
    agent_max_budget_usd: float = Field(
        default=10.0,
        description="Maximum budget per agent run in USD",
    )
    agent_permission_mode: Literal["default", "acceptEdits", "bypassPermissions"] = (
        Field(
            default="acceptEdits",
            description="Permission mode for agent operations",
        )
    )

    # Remote settings
    default_ssh_key: Path | None = Field(
        default=None,
        description="Default SSH key path",
    )
    ssh_connection_timeout: int = Field(
        default=30,
        description="SSH connection timeout in seconds",
    )
    sync_exclude_patterns: list[str] = Field(
        default_factory=lambda: [
            ".git",
            "__pycache__",
            "node_modules",
            ".env",
            "*.pyc",
            ".venv",
        ],
        description="Default patterns to exclude from rsync",
    )

    # Display settings
    output_format: Literal["table", "json", "tree"] = Field(
        default="table",
        description="Default output format for CLI",
    )
    show_cost: bool = Field(
        default=True,
        description="Show cost information in agent output",
    )
    verbose: bool = Field(
        default=False,
        description="Enable verbose output",
    )

    # Logging settings
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO",
        description="Logging level",
    )
    log_file: Path | None = Field(
        default=None,
        description="Path to log file (None for stdout only)",
    )
    log_dir: Path = Field(
        default_factory=get_default_log_dir,
        description="Directory for PMS logs",
    )

    # Test run retention settings
    test_run_log_max_bytes: int = Field(
        default=500_000_000,
        description="Max bytes to retain for test run logs/stdout/stderr (0 disables)",
    )
    test_run_artifact_max_bytes: int = Field(
        default=2_000_000_000,
        description="Max bytes to retain for downloaded test artifacts (0 disables)",
    )
    test_run_retention_days: int = Field(
        default=30,
        description="Max age in days to retain test run logs/artifacts (0 disables)",
    )
    test_run_prune_interval_seconds: int = Field(
        default=3600,
        description="Interval in seconds for background test run pruning (0 disables)",
    )

    @model_validator(mode="after")
    def apply_derived_paths(self) -> Settings:
        """Derive path settings that should follow PMS_DATA_DIR by default."""
        if "PMS_LOG_DIR" not in os.environ:
            self.log_dir = self.data_dir / "logs"
        return self

    def ensure_data_dir(self) -> Path:
        """Ensure the data directory exists and return its path."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self.data_dir

    def ensure_database_dir(self) -> Path:
        """Ensure the database directory exists and return its path."""
        db_dir = self.database_path.parent
        db_dir.mkdir(parents=True, exist_ok=True)
        return db_dir

    def ensure_log_dir(self) -> Path:
        """Ensure the log directory exists and return its path."""
        self.log_dir.mkdir(parents=True, exist_ok=True)
        return self.log_dir


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings(_env_file=str(get_env_file_path()))


def reload_settings() -> Settings:
    """Reload settings (clears cache)."""
    get_settings.cache_clear()
    return get_settings()
