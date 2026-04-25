"""Audit continuation-hint quality on key CLI and API entry surfaces."""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from pms.cli.app import cli  # noqa: E402
from pms.config.settings import reload_settings  # noqa: E402
from pms.models.json_types import JsonArray, JsonObject  # noqa: E402


@dataclass(frozen=True)
class CommandAuditSpec:
    """Expected continuation contract for a CLI entry command."""

    name: str
    setup: str
    args: tuple[str, ...]
    required_top_level: tuple[str, ...]
    required_links: tuple[str, ...] = ()
    purpose_prefix: str | None = None
    require_nonempty_next_steps: bool = True
    require_focus_task: bool = False
    require_nonempty_artifacts: bool = False


@dataclass(frozen=True)
class ApiRouteAuditSpec:
    """Expected continuation wrapper fields for a key API entry route."""

    file_path: str
    route_path: str
    required_keys: tuple[str, ...]


@dataclass(frozen=True)
class ContinuationIssue:
    """Single continuation quality issue."""

    target: str
    reason: str


@dataclass(frozen=True)
class ContinuationAuditResult:
    """Combined continuation-quality audit result."""

    command_specs_checked: int
    api_specs_checked: int
    issues: tuple[ContinuationIssue, ...]


CONTINUATION_ORG_NAME = "Continuation Active Org"
CONTINUATION_PRODUCT_NAME = "Continuation Active Product"
CONTINUATION_PROJECT_NAME = "Continuation Active Project"
CONTINUATION_PORTFOLIO_NAME = "Continuation Active Portfolio"
CONTINUATION_PROGRAM_NAME = "Continuation Active Program"
CONTINUATION_FOCUS_TASK = "Continuation Active Task"
CONTINUATION_FOLLOWUP_TASK = "Continuation Followup Task"


CLI_SPECS: tuple[CommandAuditSpec, ...] = (
    CommandAuditSpec(
        name="start",
        setup="active_workspace",
        args=("start", "--format", "json"),
        required_top_level=(
            "purpose",
            "artifacts_created",
            "live_state",
            "focus_task",
            "next_steps",
            "links",
        ),
        required_links=("dashboard", "guide", "quickstart"),
        purpose_prefix="Practical start -> go entry point",
        require_focus_task=True,
    ),
    CommandAuditSpec(
        name="quickstart",
        setup="empty_workspace",
        args=("quickstart", "--defaults", "--format", "json"),
        required_top_level=(
            "purpose",
            "fastest_start",
            "artifacts_created",
            "next_steps",
            "links",
        ),
        required_links=("guide", "project", "daily", "dashboard"),
        purpose_prefix="Bootstrap PMS",
        require_nonempty_artifacts=True,
    ),
    CommandAuditSpec(
        name="dashboard",
        setup="active_workspace",
        args=("dashboard", "--format", "json"),
        required_top_level=(
            "purpose",
            "artifacts_created",
            "focus_task",
            "links",
            "next_steps",
        ),
        required_links=("guide", "queues"),
        purpose_prefix="Overall live-state control plane",
        require_focus_task=True,
    ),
    CommandAuditSpec(
        name="work daily",
        setup="active_workspace",
        args=(
            "work",
            "daily",
            "--scope-type",
            "project",
            "--scope",
            CONTINUATION_PROJECT_NAME,
            "--format",
            "json",
        ),
        required_top_level=(
            "purpose",
            "artifacts_created",
            "focus_task",
            "links",
            "next_steps",
        ),
        required_links=("guide",),
        purpose_prefix="Scoped daily operator digest",
        require_focus_task=True,
    ),
    CommandAuditSpec(
        name="capabilities info",
        setup="empty_workspace",
        args=("capabilities", "info", "--format", "json"),
        required_top_level=("purpose", "links", "next_steps"),
        required_links=("self", "list", "docs", "schema", "guide"),
        purpose_prefix="Capability inventory entry point",
    ),
)

API_SPECS: tuple[ApiRouteAuditSpec, ...] = (
    ApiRouteAuditSpec(
        file_path="pms/api/app.py",
        route_path="/api/v1/discoverability/graph",
        required_keys=("links", "next_steps", "params"),
    ),
    ApiRouteAuditSpec(
        file_path="pms/api/routes/observability.py",
        route_path="/observability/overview",
        required_keys=("links", "next_steps", "params"),
    ),
    ApiRouteAuditSpec(
        file_path="pms/api/routes/projects.py",
        route_path="/projects/{project_id}/operator-overview",
        required_keys=("links", "next_steps", "params"),
    ),
)


def _load_json_object(text: str) -> JsonObject:
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("Expected JSON object payload.")
    return payload


def _string_value(payload: JsonObject, key: str) -> str | None:
    value = payload.get(key)
    if isinstance(value, str):
        return value
    return None


def _list_value(payload: JsonObject, key: str) -> JsonArray | None:
    value = payload.get(key)
    if isinstance(value, list):
        return value
    return None


def _dict_value(payload: JsonObject, key: str) -> JsonObject | None:
    value = payload.get(key)
    if isinstance(value, dict):
        return value
    return None


def _is_rendered_cli_command(value: str) -> bool:
    return value.startswith("uv run pms ")


def _is_runnable_command_hint(value: str) -> bool:
    if _is_rendered_cli_command(value):
        return True
    if value.startswith("./"):
        return True
    return " uv run pms " in value


def _with_temp_env() -> tuple[Path, dict[str, str]]:
    temp_dir = Path(
        tempfile.mkdtemp(prefix="continuation-audit-", dir=REPO_ROOT / ".tmp")
    )
    env = os.environ.copy()
    env.pop("PMS_API_KEY", None)
    env.pop("PMS_API_KEY_PATH", None)
    env.pop("PMS_SERVER_BASE_URL", None)
    env["PMS_DATA_DIR"] = str(temp_dir)
    env["PMS_DATABASE_PATH"] = str(temp_dir / "audit.db")
    env["PMS_LOG_DIR"] = str(temp_dir / "logs")
    env["PMS_ENV_FILE"] = str(temp_dir / ".env")
    env["PMS_WRITE_MODE"] = "direct"
    return temp_dir, env


@contextmanager
def _patched_settings_env(env: dict[str, str]):
    """Temporarily make the audit env authoritative for cached settings."""
    with patch.dict(os.environ, env, clear=True):
        reload_settings()
        try:
            yield
        finally:
            reload_settings()


def _invoke_json(
    cli_runner: CliRunner, args: tuple[str, ...], env: dict[str, str]
) -> JsonObject:
    with _patched_settings_env(env):
        result = cli_runner.invoke(cli, list(args), env=env)
    if result.exit_code != 0:
        raise RuntimeError(f"Command failed: {' '.join(args)}\n{result.output}")
    return _load_json_object(result.output)


def _prepare_workspace(cli_runner: CliRunner, setup: str, env: dict[str, str]) -> None:
    with _patched_settings_env(env):
        init_result = cli_runner.invoke(cli, ["init"], env=env)
    if init_result.exit_code != 0:
        raise RuntimeError(f"init failed\n{init_result.output}")
    if setup == "empty_workspace":
        return
    if setup == "active_workspace":
        for args in (
            (
                "quickstart",
                "--defaults",
                "--org",
                CONTINUATION_ORG_NAME,
                "--product",
                CONTINUATION_PRODUCT_NAME,
                "--project",
                CONTINUATION_PROJECT_NAME,
                "--portfolio",
                CONTINUATION_PORTFOLIO_NAME,
                "--program",
                CONTINUATION_PROGRAM_NAME,
                "--task",
                CONTINUATION_FOCUS_TASK,
                "--task",
                CONTINUATION_FOLLOWUP_TASK,
                "--no-create-plan",
                "--format",
                "json",
            ),
            (
                "task",
                "start",
                CONTINUATION_FOCUS_TASK,
                "--project",
                CONTINUATION_PROJECT_NAME,
            ),
        ):
            with _patched_settings_env(env):
                result = cli_runner.invoke(cli, list(args), env=env)
            if result.exit_code != 0:
                raise RuntimeError(f"Setup failed: {' '.join(args)}\n{result.output}")
        return
    raise ValueError(f"Unknown setup kind: {setup}")


def _audit_cli_surface(spec: CommandAuditSpec) -> tuple[ContinuationIssue, ...]:
    cli_runner = CliRunner()
    _, env = _with_temp_env()
    _prepare_workspace(cli_runner, spec.setup, env)
    payload = _invoke_json(cli_runner, spec.args, env)

    issues: list[ContinuationIssue] = []
    for key in spec.required_top_level:
        if key not in payload:
            issues.append(
                ContinuationIssue(spec.name, f"missing top-level key '{key}'")
            )

    if spec.purpose_prefix is not None:
        purpose = _string_value(payload, "purpose")
        if purpose is None or not purpose.startswith(spec.purpose_prefix):
            issues.append(
                ContinuationIssue(spec.name, "purpose text missing or incorrect")
            )

    next_steps = _list_value(payload, "next_steps")
    if spec.require_nonempty_next_steps and (
        next_steps is None or len(next_steps) == 0
    ):
        issues.append(ContinuationIssue(spec.name, "next_steps missing or empty"))
    if next_steps is not None:
        for step in next_steps:
            if not isinstance(step, str):
                issues.append(
                    ContinuationIssue(spec.name, "next_steps contains non-string value")
                )
                continue
            if " | " in step:
                issues.append(
                    ContinuationIssue(
                        spec.name, "next_steps contains merged pipe-style suggestions"
                    )
                )
            if not _is_runnable_command_hint(step):
                issues.append(
                    ContinuationIssue(
                        spec.name,
                        f"next_steps contains non-runnable command hint: {step}",
                    )
                )

    links = _dict_value(payload, "links")
    for link_key in spec.required_links:
        if links is None or link_key not in links:
            issues.append(ContinuationIssue(spec.name, f"missing links.{link_key}"))
            continue
        link_value = links.get(link_key)
        if isinstance(link_value, str) and not _is_runnable_command_hint(link_value):
            issues.append(
                ContinuationIssue(
                    spec.name,
                    f"links.{link_key} is not rendered as a runnable command: {link_value}",
                )
            )

    if spec.require_focus_task:
        focus_task = _dict_value(payload, "focus_task")
        if focus_task is None:
            issues.append(ContinuationIssue(spec.name, "focus_task missing"))

    if spec.require_nonempty_artifacts:
        artifacts = _dict_value(payload, "artifacts_created")
        if artifacts is None or all(
            value is None or value == [] for value in artifacts.values()
        ):
            issues.append(
                ContinuationIssue(spec.name, "artifacts_created missing or empty")
            )

    return tuple(issues)


def _string_constant(value: ast.expr | None) -> str | None:
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        return value.value
    return None


def _dict_literal_keys(value: ast.expr) -> frozenset[str] | None:
    if not isinstance(value, ast.Dict):
        return None
    keys: list[str] = []
    for key_node in value.keys:
        key = _string_constant(key_node)
        if key is None:
            return None
        keys.append(key)
    return frozenset(keys)


def _collect_assignments(
    function_node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> dict[str, tuple[frozenset[str], ...]]:
    assignments: dict[str, list[frozenset[str]]] = {}
    for node in ast.walk(function_node):
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
        ):
            if node is not function_node:
                continue
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            key_set = _dict_literal_keys(node.value)
            if key_set is not None:
                assignments.setdefault(node.targets[0].id, []).append(key_set)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            key_set = _dict_literal_keys(node.value) if node.value is not None else None
            if key_set is not None:
                assignments.setdefault(node.target.id, []).append(key_set)
    return {name: tuple(key_sets) for name, key_sets in assignments.items()}


def _return_key_sets(
    function_node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[frozenset[str], ...]:
    assignments = _collect_assignments(function_node)
    key_sets: list[frozenset[str]] = []
    for node in ast.walk(function_node):
        if not isinstance(node, ast.Return) or node.value is None:
            continue
        dict_keys = _dict_literal_keys(node.value)
        if dict_keys is not None:
            key_sets.append(dict_keys)
            continue
        if isinstance(node.value, ast.Name):
            key_sets.extend(assignments.get(node.value.id, ()))
    return tuple(key_sets)


def _function_route_paths(
    function_node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[str, ...]:
    paths: list[str] = []
    for decorator in function_node.decorator_list:
        if not isinstance(decorator, ast.Call) or not isinstance(
            decorator.func, ast.Attribute
        ):
            continue
        path = _string_constant(decorator.args[0]) if decorator.args else None
        if path is not None:
            paths.append(path)
    return tuple(paths)


def _audit_api_surface(spec: ApiRouteAuditSpec) -> tuple[ContinuationIssue, ...]:
    source_path = REPO_ROOT / spec.file_path
    tree = ast.parse(source_path.read_text())
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if spec.route_path not in _function_route_paths(node):
            continue
        return_key_sets = _return_key_sets(node)
        if not return_key_sets:
            return (
                ContinuationIssue(
                    spec.route_path,
                    "no static return payload found for route",
                ),
            )
        for key_set in return_key_sets:
            missing = [key for key in spec.required_keys if key not in key_set]
            if not missing:
                return ()
        return (
            ContinuationIssue(
                spec.route_path,
                f"missing required keys: {', '.join(spec.required_keys)}",
            ),
        )
    return (ContinuationIssue(spec.route_path, f"route not found in {spec.file_path}"),)


def run_audit() -> ContinuationAuditResult:
    issues: list[ContinuationIssue] = []
    for spec in CLI_SPECS:
        issues.extend(_audit_cli_surface(spec))
    for spec in API_SPECS:
        issues.extend(_audit_api_surface(spec))
    return ContinuationAuditResult(
        command_specs_checked=len(CLI_SPECS),
        api_specs_checked=len(API_SPECS),
        issues=tuple(issues),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit continuation quality on key CLI/API surfaces."
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON payload")
    parser.add_argument("--check", action="store_true", help="Exit non-zero on issues")
    args = parser.parse_args()

    result = run_audit()
    if args.json:
        payload = {
            "checked_cli": result.command_specs_checked,
            "checked_api": result.api_specs_checked,
            "issues": [
                {"target": issue.target, "reason": issue.reason}
                for issue in result.issues
            ],
        }
        print(json.dumps(payload, indent=2))
    else:
        print(
            "Continuation quality audit\n"
            f"checked_cli={result.command_specs_checked} "
            f"checked_api={result.api_specs_checked} "
            f"issues={len(result.issues)}"
        )
        for issue in result.issues:
            print(f"- {issue.target}: {issue.reason}")

    if args.check and result.issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
