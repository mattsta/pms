"""Codex adapter built on ACP."""

from __future__ import annotations

from pms.agents.acp.adapter import ACPLoopAdapter
from pms.config.logging import logger


def build_codex_args(
    base_args: list[str],
    model: str | None,
    reasoning_effort: str | None,
) -> list[str]:
    args = list(base_args)
    if model:
        args.extend(["-c", f'model="{model}"'])
    if reasoning_effort:
        args.extend(["-c", f'model_reasoning_effort="{reasoning_effort}"'])
    return args


class CodexLoopAdapter(ACPLoopAdapter):
    """Codex adapter using codex-acp with ACP protocol."""

    def __init__(self, name, config) -> None:  # type: ignore[no-untyped-def]
        if not config.agent_command and not config.command:
            config.agent_command = "codex-acp"

        config.agent_args = build_codex_args(
            list(config.agent_args or config.args),
            config.codex_model,
            config.codex_reasoning_effort,
        )

        super().__init__(name, config)

    def _check_available(self) -> bool:
        available = super()._check_available()
        if not available:
            logger.warning("Codex adapter unavailable: codex-acp not found")
        return available
