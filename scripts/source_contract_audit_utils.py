#!/usr/bin/env python3
"""Shared helpers for block-scoped source contract audits."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class SourceBlockContract:
    """One block-scoped source contract anchored at a stable snippet."""

    anchor: str
    required: tuple[str, ...]
    forbidden: tuple[str, ...] = ()
    block_kind: Literal["brace", "python_def", "match_arm"] = "brace"
    occurrence: int = 1


def _find_nth(source: str, needle: str, occurrence: int) -> int:
    start = -1
    search_from = 0
    for _ in range(occurrence):
        start = source.find(needle, search_from)
        if start == -1:
            return -1
        search_from = start + len(needle)
    return start


def _extract_brace_block(source: str, contract: SourceBlockContract) -> str | None:
    start = _find_nth(source, contract.anchor, contract.occurrence)
    if start == -1:
        return None
    brace_start = source.find("{", start)
    if brace_start == -1:
        return None

    depth = 0
    for index in range(brace_start, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    return source[start:]


def _extract_python_def_block(source: str, contract: SourceBlockContract) -> str | None:
    start = _find_nth(source, contract.anchor, contract.occurrence)
    if start == -1:
        return None

    line_start = source.rfind("\n", 0, start) + 1
    lines = source[line_start:].splitlines()
    if not lines:
        return None

    first_line = lines[0]
    indent = len(first_line) - len(first_line.lstrip(" "))
    block_lines = [first_line]
    signature_complete = first_line.rstrip().endswith(":")

    for line in lines[1:]:
        if not signature_complete:
            block_lines.append(line)
            if line.rstrip().endswith(":"):
                signature_complete = True
            continue
        stripped = line.strip()
        current_indent = len(line) - len(line.lstrip(" "))
        if stripped and current_indent <= indent:
            break
        block_lines.append(line)
    return "\n".join(block_lines)


def _extract_match_arm_block(source: str, contract: SourceBlockContract) -> str | None:
    start = _find_nth(source, contract.anchor, contract.occurrence)
    if start == -1:
        return None

    arm_marker = source.find("=>", start)
    if arm_marker == -1:
        return None

    body_start = source.find("{", arm_marker)
    if body_start == -1:
        return None

    depth = 0
    for index in range(body_start, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    return source[start:]


def extract_block(source: str, contract: SourceBlockContract) -> str | None:
    """Extract the block governed by one source contract."""
    if contract.block_kind == "python_def":
        return _extract_python_def_block(source, contract)
    if contract.block_kind == "match_arm":
        return _extract_match_arm_block(source, contract)
    return _extract_brace_block(source, contract)


def audit_block_contracts(
    source: str,
    *,
    block_contracts: tuple[SourceBlockContract, ...],
    contract_label: str,
) -> tuple[str, ...]:
    """Return human-readable contract mismatches for one source file."""
    issues: list[str] = []
    for contract in block_contracts:
        block = extract_block(source, contract)
        if block is None:
            issues.append(
                f"missing {contract_label} block anchored at: {contract.anchor}"
            )
            continue
        for pattern in contract.required:
            if pattern not in block:
                issues.append(
                    "missing required "
                    f"{contract_label} snippet in block {contract.anchor}: {pattern}"
                )
        for pattern in contract.forbidden:
            if pattern in block:
                issues.append(
                    "forbidden "
                    f"{contract_label} snippet present in block {contract.anchor}: {pattern}"
                )
    return tuple(issues)
