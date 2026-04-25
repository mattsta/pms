#!/usr/bin/env python3
"""Deterministic command adapter for real agent-loop scenario coverage."""

from __future__ import annotations

import argparse
import hashlib
import sys


def _read_prompt(mode: str, prompt_args: list[str]) -> str:
    if mode == "args":
        return " ".join(prompt_args).strip()
    return sys.stdin.read().strip()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Emit a stable response for PMS agent-loop scenario tests."
    )
    parser.add_argument(
        "--prompt-mode",
        choices=("stdin", "args"),
        default="stdin",
        help="How the command adapter receives the prompt.",
    )
    parser.add_argument("prompt", nargs="*")
    args = parser.parse_args()

    prompt = _read_prompt(args.prompt_mode, args.prompt)
    digest = (
        hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:12] if prompt else "empty"
    )

    response = "\n".join(
        [
            "Agent loop iteration complete.",
            f"Prompt digest: {digest}",
            "Recommended next actions:",
            "1. Confirm project, goal, plan, and task state in PMS.",
            "2. Record progress against the active task.",
            "3. Attach prompt/config artifacts plus a test run as proof before closure.",
        ]
    )
    print(response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
