"""Filter a Claudo graph to the sessions for one project root."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pms.integrations.claudo import (
    filter_claudo_graph_for_project,
    load_claudo_graph,
    write_claudo_graph,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Filter Claudo interchange JSON to one repository/project root."
    )
    parser.add_argument("input_path", type=Path)
    parser.add_argument(
        "--project-root",
        required=True,
        type=Path,
        help="Existing repository root whose Claudo sessions should be kept.",
    )
    parser.add_argument("-o", "--output", required=True, type=Path)
    args = parser.parse_args()

    try:
        graph = load_claudo_graph(args.input_path)
        result = filter_claudo_graph_for_project(graph, args.project_root)
        write_claudo_graph(result.graph.raw, args.output)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"claudo project filter failed: {exc}", file=sys.stderr)
        return 1

    payload = result.to_dict()
    payload["output_path"] = str(args.output)
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
