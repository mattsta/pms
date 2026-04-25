"""Database backend implementations."""

from pms.db.backends.base import DatabaseBackend
from pms.db.backends.factory import create_backend, get_backend_name
from pms.db.backends.sqlite import SQLiteBackend

# PostgreSQL is optional
try:
    from pms.db.backends.postgresql import PostgreSQLBackend

    __all__ = [
        "DatabaseBackend",
        "SQLiteBackend",
        "PostgreSQLBackend",
        "create_backend",
        "get_backend_name",
    ]
except ImportError:
    __all__ = [
        "DatabaseBackend",
        "SQLiteBackend",
        "create_backend",
        "get_backend_name",
    ]
