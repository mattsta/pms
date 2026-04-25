"""ACP session state tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ACPSessionState:
    """Track ACP session output and tool activity."""

    output: str = ""
    thoughts: list[str] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)

    def reset(self) -> None:
        self.output = ""
        self.thoughts.clear()
        self.tool_calls.clear()

    def add_message(self, text: str) -> None:
        if text:
            self.output += text

    def add_thought(self, text: str) -> None:
        if text:
            self.thoughts.append(text)

    def register_tool_call(
        self,
        tool_name: str | None,
        tool_call_id: str | None,
        arguments: dict[str, Any] | None,
    ) -> None:
        self.tool_calls.append(
            {
                "tool_name": tool_name,
                "tool_call_id": tool_call_id,
                "arguments": arguments,
                "status": "pending",
            }
        )

    def update_tool_call(
        self,
        tool_call_id: str | None,
        status: str | None,
        result: Any | None,
        error: str | None,
    ) -> None:
        if not tool_call_id:
            return
        for tool_call in self.tool_calls:
            if tool_call.get("tool_call_id") == tool_call_id:
                if status:
                    tool_call["status"] = status
                if result is not None:
                    tool_call["result"] = result
                if error:
                    tool_call["error"] = error
                return
        self.tool_calls.append(
            {
                "tool_name": None,
                "tool_call_id": tool_call_id,
                "arguments": None,
                "status": status or "unknown",
                "result": result,
                "error": error,
            }
        )
