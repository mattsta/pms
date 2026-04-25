"""IPC Protocol for Plugin Communication.

Defines the JSON-RPC based protocol for communication between
the PMS host and sandboxed plugin processes.

Protocol Overview:
    - Transport: Unix Domain Sockets (local) or TCP (remote)
    - Format: JSON-RPC 2.0
    - Encoding: UTF-8 with newline-delimited messages

Message Types:
    - request: Function call from host to plugin
    - response: Result from plugin to host
    - notification: One-way message (no response expected)
    - event: Plugin-emitted event to host

Example Request:
    {
        "jsonrpc": "2.0",
        "id": "req-123",
        "method": "call_tool",
        "params": {
            "tool": "list_repos",
            "args": {"org": "my-org"}
        }
    }

Example Response:
    {
        "jsonrpc": "2.0",
        "id": "req-123",
        "result": {
            "repos": ["repo1", "repo2"]
        }
    }

Example Error:
    {
        "jsonrpc": "2.0",
        "id": "req-123",
        "error": {
            "code": -32000,
            "message": "Tool execution failed",
            "data": {"traceback": "..."}
        }
    }
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import tempfile
import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """Types of IPC messages."""

    REQUEST = "request"
    RESPONSE = "response"
    NOTIFICATION = "notification"
    EVENT = "event"
    PING = "ping"
    PONG = "pong"
    SHUTDOWN = "shutdown"


class ErrorCode(Enum):
    """JSON-RPC error codes."""

    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603

    # Custom error codes
    TOOL_NOT_FOUND = -32000
    TOOL_EXECUTION_ERROR = -32001
    TIMEOUT = -32002
    PERMISSION_DENIED = -32003
    PLUGIN_NOT_RUNNING = -32004


@dataclass
class IPCMessage:
    """IPC message structure."""

    type: MessageType
    id: str | None = None  # Required for request/response
    method: str | None = None  # For request/notification
    params: dict[str, Any] = field(default_factory=dict)
    result: Any = None  # For successful response
    error: dict[str, Any] | None = None  # For error response
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-RPC format."""
        msg: dict[str, Any] = {"jsonrpc": "2.0"}

        if self.id:
            msg["id"] = self.id

        match self.type:
            case MessageType.REQUEST:
                msg["method"] = self.method
                if self.params:
                    msg["params"] = self.params
            case MessageType.RESPONSE:
                if self.error:
                    msg["error"] = self.error
                else:
                    msg["result"] = self.result
            case MessageType.NOTIFICATION:
                msg["method"] = self.method
                if self.params:
                    msg["params"] = self.params
            case MessageType.EVENT:
                msg["method"] = "event"
                msg["params"] = {
                    "event": self.method,
                    "data": self.params,
                    "timestamp": self.timestamp.isoformat(),
                }
            case MessageType.PING:
                msg["method"] = "ping"
            case MessageType.PONG:
                msg["method"] = "pong"
            case MessageType.SHUTDOWN:
                msg["method"] = "shutdown"

        return msg

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())

    def to_bytes(self) -> bytes:
        """Convert to bytes for transmission (newline-delimited)."""
        return (self.to_json() + "\n").encode("utf-8")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IPCMessage:
        """Create from JSON-RPC dict."""
        msg_id = data.get("id")
        method = data.get("method")
        params = data.get("params", {})
        result = data.get("result")
        error = data.get("error")

        # Determine message type
        match (error is not None, result is not None, method, msg_id is not None):
            case (True, _, _, _):
                msg_type = MessageType.RESPONSE
            case (_, True, _, _):
                msg_type = MessageType.RESPONSE
            case (_, _, "ping", _):
                msg_type = MessageType.PING
            case (_, _, "pong", _):
                msg_type = MessageType.PONG
            case (_, _, "shutdown", _):
                msg_type = MessageType.SHUTDOWN
            case (_, _, "event", _):
                msg_type = MessageType.EVENT
                method = params.get("event")
                params = params.get("data", {})
            case (_, _, _, True):
                msg_type = MessageType.REQUEST
            case _:
                msg_type = MessageType.NOTIFICATION

        return cls(
            type=msg_type,
            id=msg_id,
            method=method,
            params=params,
            result=result,
            error=error,
        )

    @classmethod
    def from_json(cls, json_str: str) -> IPCMessage:
        """Create from JSON string."""
        return cls.from_dict(json.loads(json_str))

    @classmethod
    def from_bytes(cls, data: bytes) -> IPCMessage:
        """Create from bytes."""
        return cls.from_json(data.decode("utf-8").strip())

    @classmethod
    def request(cls, method: str, **params: Any) -> IPCMessage:
        """Create a request message."""
        return cls(
            type=MessageType.REQUEST,
            id=str(uuid.uuid4()),
            method=method,
            params=params,
        )

    @classmethod
    def response(cls, request_id: str, result: Any) -> IPCMessage:
        """Create a success response."""
        return cls(
            type=MessageType.RESPONSE,
            id=request_id,
            result=result,
        )

    @classmethod
    def error_response(
        cls,
        request_id: str | None,
        code: ErrorCode,
        message: str,
        data: Any = None,
    ) -> IPCMessage:
        """Create an error response."""
        error: dict[str, Any] = {
            "code": code.value,
            "message": message,
        }
        if data is not None:
            error["data"] = data

        return cls(
            type=MessageType.RESPONSE,
            id=request_id,
            error=error,
        )

    @classmethod
    def notification(cls, method: str, **params: Any) -> IPCMessage:
        """Create a notification (no response expected)."""
        return cls(
            type=MessageType.NOTIFICATION,
            method=method,
            params=params,
        )

    @classmethod
    def event(cls, event_name: str, **data: Any) -> IPCMessage:
        """Create an event message."""
        return cls(
            type=MessageType.EVENT,
            method=event_name,
            params=data,
        )

    @property
    def is_request(self) -> bool:
        return self.type == MessageType.REQUEST

    @property
    def is_response(self) -> bool:
        return self.type == MessageType.RESPONSE

    @property
    def is_success(self) -> bool:
        return self.type == MessageType.RESPONSE and self.error is None

    @property
    def is_error(self) -> bool:
        return self.type == MessageType.RESPONSE and self.error is not None


# Type for message handlers
MessageHandler = Callable[[IPCMessage], Coroutine[Any, Any, IPCMessage | None]]


class IPCProtocol:
    """Protocol handler for IPC communication.

    Handles message parsing, routing, and response management.
    """

    def __init__(self) -> None:
        """Initialize protocol handler."""
        self._handlers: dict[str, MessageHandler] = {}
        self._pending_requests: dict[str, asyncio.Future[IPCMessage]] = {}
        self._event_listeners: list[Callable[[str, dict[str, Any]], None]] = []

    def register_handler(self, method: str, handler: MessageHandler) -> None:
        """Register a method handler."""
        self._handlers[method] = handler

    def unregister_handler(self, method: str) -> None:
        """Unregister a method handler."""
        self._handlers.pop(method, None)

    def add_event_listener(
        self, listener: Callable[[str, dict[str, Any]], None]
    ) -> None:
        """Add event listener."""
        self._event_listeners.append(listener)

    async def handle_message(self, message: IPCMessage) -> IPCMessage | None:
        """Handle an incoming message.

        Args:
            message: Incoming IPC message

        Returns:
            Response message if applicable, None otherwise
        """
        match message.type:
            case MessageType.RESPONSE:
                # Handle response to pending request
                if message.id and message.id in self._pending_requests:
                    future = self._pending_requests.pop(message.id)
                    future.set_result(message)
                return None
            case MessageType.REQUEST:
                # Handle request
                handler = self._handlers.get(message.method or "")
                if not handler:
                    return IPCMessage.error_response(
                        message.id,
                        ErrorCode.METHOD_NOT_FOUND,
                        f"Method not found: {message.method}",
                    )

                try:
                    response = await handler(message)
                    return response
                except Exception as e:
                    logger.exception(f"Error handling {message.method}")
                    return IPCMessage.error_response(
                        message.id,
                        ErrorCode.INTERNAL_ERROR,
                        str(e),
                    )
            case MessageType.NOTIFICATION:
                # Handle notification (no response)
                handler = self._handlers.get(message.method or "")
                if handler:
                    try:
                        await handler(message)
                    except Exception as e:
                        logger.error(
                            f"Error handling notification {message.method}: {e}"
                        )
                return None
            case MessageType.EVENT:
                # Dispatch event to listeners
                for listener in self._event_listeners:
                    try:
                        listener(message.method or "", message.params)
                    except Exception as e:
                        logger.error(f"Error in event listener: {e}")
                return None
            case MessageType.PING:
                return IPCMessage(type=MessageType.PONG, id=message.id)
            case _:
                return None

    async def send_request(
        self,
        writer: asyncio.StreamWriter,
        method: str,
        timeout: float = 30.0,
        **params: Any,
    ) -> IPCMessage:
        """Send a request and wait for response.

        Args:
            writer: Stream to write to
            method: Method name
            timeout: Timeout in seconds
            **params: Method parameters

        Returns:
            Response message

        Raises:
            asyncio.TimeoutError: If timeout exceeded
        """
        request = IPCMessage.request(method, **params)

        # Create future for response
        future: asyncio.Future[IPCMessage] = asyncio.Future()
        if request.id is None:
            raise RuntimeError("Request ID missing")
        self._pending_requests[request.id] = future

        try:
            # Send request
            writer.write(request.to_bytes())
            await writer.drain()

            # Wait for response
            response = await asyncio.wait_for(future, timeout=timeout)
            return response

        except TimeoutError:
            if request.id is not None:
                self._pending_requests.pop(request.id, None)
            raise

    async def send_notification(
        self,
        writer: asyncio.StreamWriter,
        method: str,
        **params: Any,
    ) -> None:
        """Send a notification (no response expected)."""
        notification = IPCMessage.notification(method, **params)
        writer.write(notification.to_bytes())
        await writer.drain()


class IPCServer:
    """Unix socket server for plugin communication."""

    def __init__(
        self,
        socket_path: Path | str | None = None,
        protocol: IPCProtocol | None = None,
    ):
        """Initialize IPC server.

        Args:
            socket_path: Path to Unix socket (auto-generated if None)
            protocol: Protocol handler (created if None)
        """
        if socket_path is None:
            socket_path = (
                Path(tempfile.gettempdir()) / f"pms-plugin-{uuid.uuid4().hex[:8]}.sock"
            )
        self.socket_path = Path(socket_path)
        self.protocol = protocol or IPCProtocol()
        self._server: asyncio.Server | None = None
        self._clients: set[tuple[asyncio.StreamReader, asyncio.StreamWriter]] = set()
        self._running = False

    async def start(self) -> None:
        """Start the IPC server."""
        # Remove existing socket
        if self.socket_path.exists():
            self.socket_path.unlink()

        self._server = await asyncio.start_unix_server(
            self._handle_client,
            path=str(self.socket_path),
        )

        # Set permissions
        self.socket_path.chmod(0o600)

        self._running = True
        logger.info(f"IPC server started at {self.socket_path}")

    async def stop(self) -> None:
        """Stop the IPC server."""
        self._running = False

        # Close all client connections
        for reader, writer in list(self._clients):
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
        self._clients.clear()

        # Stop server
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        # Remove socket file
        if self.socket_path.exists():
            self.socket_path.unlink()

        logger.info("IPC server stopped")

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle client connection."""
        self._clients.add((reader, writer))

        try:
            while self._running:
                # Read message (newline-delimited)
                try:
                    line = await asyncio.wait_for(reader.readline(), timeout=60.0)
                except TimeoutError:
                    continue

                if not line:
                    break

                try:
                    message = IPCMessage.from_bytes(line)
                    response = await self.protocol.handle_message(message)

                    if response:
                        writer.write(response.to_bytes())
                        await writer.drain()

                except json.JSONDecodeError as e:
                    error = IPCMessage.error_response(
                        None,
                        ErrorCode.PARSE_ERROR,
                        f"Invalid JSON: {e}",
                    )
                    writer.write(error.to_bytes())
                    await writer.drain()

                except Exception as e:
                    logger.exception("Error handling message")
                    error = IPCMessage.error_response(
                        None,
                        ErrorCode.INTERNAL_ERROR,
                        str(e),
                    )
                    writer.write(error.to_bytes())
                    await writer.drain()

        finally:
            self._clients.discard((reader, writer))
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def broadcast(self, message: IPCMessage) -> None:
        """Broadcast message to all connected clients."""
        data = message.to_bytes()
        for reader, writer in list(self._clients):
            try:
                writer.write(data)
                await writer.drain()
            except Exception as e:
                logger.error(f"Error broadcasting: {e}")


class IPCClient:
    """Client for connecting to IPC server."""

    def __init__(
        self,
        socket_path: Path | str,
        protocol: IPCProtocol | None = None,
    ):
        """Initialize IPC client.

        Args:
            socket_path: Path to Unix socket
            protocol: Protocol handler
        """
        self.socket_path = Path(socket_path)
        self.protocol = protocol or IPCProtocol()
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._receive_task: asyncio.Task[None] | None = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        """Connect to IPC server."""
        self._reader, self._writer = await asyncio.open_unix_connection(
            path=str(self.socket_path)
        )
        self._connected = True

        # Start receive loop
        self._receive_task = asyncio.create_task(self._receive_loop())

    async def disconnect(self) -> None:
        """Disconnect from IPC server."""
        self._connected = False

        if self._receive_task:
            self._receive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._receive_task

        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()

        self._reader = None
        self._writer = None

    async def _receive_loop(self) -> None:
        """Receive messages from server."""
        while self._connected and self._reader:
            try:
                line = await self._reader.readline()
                if not line:
                    break

                message = IPCMessage.from_bytes(line)
                await self.protocol.handle_message(message)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error receiving: {e}")

    async def call(
        self,
        method: str,
        timeout: float = 30.0,
        **params: Any,
    ) -> Any:
        """Call a remote method.

        Args:
            method: Method name
            timeout: Timeout in seconds
            **params: Method parameters

        Returns:
            Method result

        Raises:
            RuntimeError: If call failed
            asyncio.TimeoutError: If timeout exceeded
        """
        if not self._connected or not self._writer:
            raise RuntimeError("Not connected")

        response = await self.protocol.send_request(
            self._writer,
            method,
            timeout=timeout,
            **params,
        )

        if response.is_error:
            error = response.error or {}
            raise RuntimeError(error.get("message", "Unknown error"))

        return response.result

    async def notify(self, method: str, **params: Any) -> None:
        """Send a notification."""
        if not self._connected or not self._writer:
            raise RuntimeError("Not connected")

        await self.protocol.send_notification(self._writer, method, **params)


async def create_ipc_server(
    socket_path: Path | str | None = None,
) -> IPCServer:
    """Create and start an IPC server.

    Args:
        socket_path: Path to Unix socket

    Returns:
        Running IPC server
    """
    server = IPCServer(socket_path)
    await server.start()
    return server
