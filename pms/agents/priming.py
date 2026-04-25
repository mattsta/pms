"""Helpers for injecting context primers into agent prompts."""

from __future__ import annotations

from pms.memory.priming import ContextPrimer


def build_system_prompt(
    base_prompt: str,
    context_primer: ContextPrimer | None,
    prime_context: bool,
) -> str:
    """Return a system prompt with optional context primer appended."""
    if not prime_context or context_primer is None:
        return base_prompt

    primer_text = context_primer.build_primer()
    if not primer_text:
        return base_prompt

    return f"{base_prompt}\n\n{primer_text}"
