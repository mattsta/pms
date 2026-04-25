"""Base exceptions for PMS."""

from typing import Any


class PMSException(Exception):
    """Base exception for all PMS errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        self.message = message
        self.details = details or {}
        super().__init__(message)

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} - {self.details}"
        return self.message


class NotFoundError(PMSException):
    """Requested resource not found."""

    def __init__(self, resource_type: str, identifier: str) -> None:
        super().__init__(
            f"{resource_type} '{identifier}' not found",
            {"resource_type": resource_type, "identifier": identifier},
        )


class DuplicateError(PMSException):
    """Resource already exists."""

    def __init__(self, resource_type: str, identifier: str) -> None:
        super().__init__(
            f"{resource_type} '{identifier}' already exists",
            {"resource_type": resource_type, "identifier": identifier},
        )


class ValidationError(PMSException):
    """Input validation failed."""

    def __init__(
        self,
        message: str,
        field: str | None = None,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        merged_details = dict(details or {})
        if field is not None:
            merged_details.setdefault("field", field)
        super().__init__(message, merged_details)


class DatabaseError(PMSException):
    """Database operation failed."""

    pass


class ConstraintViolationError(DatabaseError):
    """Database constraint violation with preserved structure."""

    def __init__(
        self,
        message: str,
        *,
        constraint_kind: str,
        table: str | None = None,
        columns: list[str] | None = None,
        raw_message: str | None = None,
        suggestions: list[str] | None = None,
    ) -> None:
        details: dict[str, Any] = {"constraint_kind": constraint_kind}
        if table is not None:
            details["table"] = table
        if columns is not None:
            details["columns"] = columns
        if raw_message is not None:
            details["raw_message"] = raw_message
        if suggestions:
            details["suggestions"] = suggestions
        super().__init__(message, details)
        self.constraint_kind = constraint_kind
        self.table = table
        self.columns = columns or []
        self.raw_message = raw_message
        self.suggestions = suggestions or []


class RemoteError(PMSException):
    """Remote operation failed."""

    pass


class ConnectionError(RemoteError):
    """Failed to connect to remote host."""

    def __init__(self, host: str, reason: str) -> None:
        super().__init__(
            f"Failed to connect to '{host}': {reason}",
            {"host": host, "reason": reason},
        )


class SSHExecutionError(RemoteError):
    """SSH command execution failed."""

    def __init__(
        self, message: str, exit_code: int, stdout: str = "", stderr: str = ""
    ) -> None:
        super().__init__(
            message,
            {"exit_code": exit_code, "stdout": stdout, "stderr": stderr},
        )
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr


class TaskCheckoutConflict(PMSException):
    """Raised when task checkout conflicts with existing lease."""

    pass


class TaskCheckoutBlocked(PMSException):
    """Raised when task cannot be checked out due to dependencies or state."""

    pass
