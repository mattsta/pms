from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import NoReturn


def fail(message: str) -> NoReturn:
    raise SystemExit(message)


def load_json(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        fail(f"{path} did not contain a JSON object")
    return value


def require_keys(payload: dict[str, object], keys: list[str], label: str) -> None:
    missing = [key for key in keys if key not in payload]
    if missing:
        fail(f"{label} missing keys: {', '.join(missing)}")


def require_command_prefix(payload: dict[str, object], label: str) -> str:
    cli_payload = payload.get("cli")
    if not isinstance(cli_payload, dict):
        fail(f"{label} cli must be an object")
    canonical_prefix = cli_payload.get("canonical_prefix")
    if not isinstance(canonical_prefix, str) or not canonical_prefix.strip():
        fail(f"{label} cli.canonical_prefix must be a non-empty string")
    return canonical_prefix


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-json", required=True, type=Path)
    parser.add_argument("--task-list-json", required=True, type=Path)
    parser.add_argument("--plan-list-json", type=Path)
    parser.add_argument("--task-start-json", type=Path)
    parser.add_argument("--task-progress-json", type=Path)
    parser.add_argument("--task-complete-json", type=Path)
    args = parser.parse_args()

    start_payload = load_json(args.start_json)
    task_payload = load_json(args.task_list_json)

    require_keys(
        start_payload,
        [
            "generated_at",
            "purpose",
            "artifacts_created",
            "live_state",
            "focus_task",
            "links",
            "next_steps",
            "cli",
        ],
        "start payload",
    )
    require_keys(
        task_payload,
        ["items", "total_count", "focus_task", "links", "next_steps", "cli"],
        "task-list payload",
    )
    items = task_payload["items"]
    if not isinstance(items, list) or not items:
        fail("task-list payload items must be a non-empty list")
    first_item = items[0]
    if not isinstance(first_item, dict):
        fail("task-list payload items must be objects")
    require_keys(first_item, ["id", "title", "status", "links"], "task-list item")
    item_links = first_item["links"]
    if not isinstance(item_links, dict):
        fail("task-list item links must be an object")
    require_keys(
        item_links,
        ["self", "timeline", "graph", "evidence"],
        "task-list item links",
    )
    task_prefix = require_command_prefix(task_payload, "task-list payload")
    if not all(
        isinstance(item_links[key], str)
        and item_links[key].startswith(f"{task_prefix} ")
        for key in ["self", "timeline", "graph", "evidence"]
    ):
        fail("task-list item links must use the payload canonical prefix")

    focus_task = task_payload["focus_task"]
    if not isinstance(focus_task, dict):
        fail("task-list payload focus_task must be an object")

    require_keys(
        focus_task,
        ["id", "title", "status", "reason"],
        "task-list focus_task",
    )

    next_steps = task_payload["next_steps"]
    if not isinstance(next_steps, list) or not next_steps:
        fail("task-list payload next_steps must be a non-empty list")

    if not all(
        isinstance(step, str) and step.startswith(f"{task_prefix} ")
        for step in next_steps
    ):
        fail("task-list payload next_steps must use the payload canonical prefix")

    if args.plan_list_json is not None:
        plan_payload = load_json(args.plan_list_json)
        require_keys(
            plan_payload,
            ["items", "focus_task", "page", "links", "next_steps", "cli"],
            "plan-list payload",
        )
        plan_items = plan_payload["items"]
        if not isinstance(plan_items, list) or not plan_items:
            fail("plan-list payload items must be a non-empty list")
        first_plan = plan_items[0]
        if not isinstance(first_plan, dict):
            fail("plan-list payload items must be objects")
        require_keys(first_plan, ["id", "name", "status", "links"], "plan-list item")
        plan_links = first_plan["links"]
        if not isinstance(plan_links, dict):
            fail("plan-list item links must be an object")
        require_keys(plan_links, ["self", "lineage"], "plan-list item links")
        plan_prefix = require_command_prefix(plan_payload, "plan-list payload")
        if not all(
            isinstance(plan_links[key], str)
            and plan_links[key].startswith(f"{plan_prefix} ")
            for key in ["self", "lineage"]
        ):
            fail("plan-list item links must use the payload canonical prefix")
        plan_steps = plan_payload["next_steps"]
        if not isinstance(plan_steps, list) or not plan_steps:
            fail("plan-list payload next_steps must be a non-empty list")
        if not all(
            isinstance(step, str) and step.startswith(f"{plan_prefix} ")
            for step in plan_steps
        ):
            fail("plan-list payload next_steps must use the payload canonical prefix")
        plan_focus = plan_payload["focus_task"]
        if plan_focus is not None and not isinstance(plan_focus, dict):
            fail("plan-list payload focus_task must be an object or null")

    for label, path, required_links in [
        ("task-start payload", args.task_start_json, ["self", "timeline", "progress"]),
        (
            "task-progress payload",
            args.task_progress_json,
            ["self", "timeline", "evidence", "progress"],
        ),
        (
            "task-complete payload",
            args.task_complete_json,
            ["self", "timeline", "evidence"],
        ),
    ]:
        if path is None:
            continue
        payload = load_json(path)
        require_keys(payload, ["task", "links", "next_steps", "cli"], label)
        prefix = require_command_prefix(payload, label)
        task = payload["task"]
        if not isinstance(task, dict):
            fail(f"{label} task must be an object")
        if not isinstance(payload["next_steps"], list) or not payload["next_steps"]:
            fail(f"{label} next_steps must be a non-empty list")
        links = payload["links"]
        if not isinstance(links, dict):
            fail(f"{label} links must be an object")
        require_keys(links, required_links, f"{label} links")
        if not all(
            isinstance(links[key], str) and links[key].startswith(f"{prefix} ")
            for key in required_links
        ):
            fail(f"{label} links must use the payload canonical prefix")
        if not all(
            isinstance(step, str) and step.startswith(f"{prefix} ")
            for step in payload["next_steps"]
        ):
            fail(f"{label} next_steps must use the payload canonical prefix")
        if label == "task-progress payload":
            require_keys(payload, ["progress"], label)
        if label == "task-complete payload":
            require_keys(payload, ["completion"], label)

    print("Rust client parity smoke passed")


if __name__ == "__main__":
    main()
