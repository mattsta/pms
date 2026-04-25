"""ACP JSON-RPC protocol helpers."""

from __future__ import annotations

import json
from enum import Enum, auto
from typing import Any


class ACPMessageType(Enum):
    """Classifies ACP JSON-RPC messages."""

    REQUEST = auto()
    NOTIFICATION = auto()
    RESPONSE = auto()
    ERROR = auto()
    PARSE_ERROR = auto()
    INVALID = auto()


class ACPProtocol:
    """Encode and decode JSON-RPC 2.0 messages for ACP."""

    JSONRPC_VERSION = "2.0"

    def __init__(self) -> None:
        self._request_id = 0

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def create_request(self, method: str, params: dict[str, Any]) -> tuple[int, str]:
        request_id = self._next_id()
        payload = {
            "jsonrpc": self.JSONRPC_VERSION,
            "id": request_id,
            "method": method,
            "params": params,
        }
        return request_id, json.dumps(payload)

    def create_notification(self, method: str, params: dict[str, Any]) -> str:
        payload = {
            "jsonrpc": self.JSONRPC_VERSION,
            "method": method,
            "params": params,
        }
        return json.dumps(payload)

    def create_response(self, request_id: int, result: Any) -> str:
        payload = {
            "jsonrpc": self.JSONRPC_VERSION,
            "id": request_id,
            "result": result,
        }
        return json.dumps(payload)

    def create_error_response(
        self,
        request_id: int,
        code: int,
        message: str,
        data: Any = None,
    ) -> str:
        error_obj: dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            error_obj["data"] = data
        payload = {
            "jsonrpc": self.JSONRPC_VERSION,
            "id": request_id,
            "error": error_obj,
        }
        return json.dumps(payload)

    def parse_message(self, raw: str) -> dict[str, Any]:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            return {
                "type": ACPMessageType.PARSE_ERROR,
                "error": f"JSON parse error: {exc}",
            }

        if payload.get("jsonrpc") != self.JSONRPC_VERSION:
            return {
                "type": ACPMessageType.INVALID,
                "error": "Invalid or missing jsonrpc version",
            }

        has_id = "id" in payload
        has_method = "method" in payload
        has_result = "result" in payload
        has_error = "error" in payload

        match (has_id, has_method, has_result, has_error):
            case (True, True, False, False):
                return {
                    "type": ACPMessageType.REQUEST,
                    "id": payload["id"],
                    "method": payload["method"],
                    "params": payload.get("params", {}),
                }
            case (False, True, False, False):
                return {
                    "type": ACPMessageType.NOTIFICATION,
                    "method": payload["method"],
                    "params": payload.get("params", {}),
                }
            case (True, False, True, False):
                return {
                    "type": ACPMessageType.RESPONSE,
                    "id": payload["id"],
                    "result": payload.get("result"),
                }
            case (True, False, False, True):
                return {
                    "type": ACPMessageType.ERROR,
                    "id": payload["id"],
                    "error": payload.get("error"),
                }
            case _:
                return {
                    "type": ACPMessageType.INVALID,
                    "error": "Invalid JSON-RPC message structure",
                }
