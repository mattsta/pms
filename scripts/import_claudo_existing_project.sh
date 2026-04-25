#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PMS_REPO="$(cd "$SCRIPT_DIR/.." && pwd)"
PMS_APP="$PMS_REPO/.bin/pms-app"

project_root="$PWD"
pms_project=""
claudo_repo="${CLAUDO_REPO:-$HOME/repos/claudo}"
claude_task_root="${CLAUDE_TASK_ROOT:-$HOME/.claude/tasks}"
session_id=""

usage() {
  cat <<'EOF'
Usage: scripts/import_claudo_existing_project.sh [options]

Bootstrap project-local PMS state from the current Claude todo graph via Claudo.
Only Claudo sessions whose repo metadata matches the project root are imported.

Run from an existing project directory, or pass --project-root.

Options:
  --project-root PATH      Existing project directory to import into. Default: cwd.
  --project NAME           PMS project name. Default: basename of project root.
  --claudo-repo PATH       Claudo checkout. Default: $CLAUDO_REPO or ~/repos/claudo.
  --claude-task-root PATH  Claude task root. Default: $CLAUDE_TASK_ROOT or ~/.claude/tasks.
  --session ID             Restrict Claudo export to one Claude session.
  -h, --help               Show this help.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-root)
      [[ $# -ge 2 ]] || { echo "--project-root requires a value" >&2; exit 2; }
      project_root="$2"
      shift 2
      ;;
    --project)
      [[ $# -ge 2 ]] || { echo "--project requires a value" >&2; exit 2; }
      pms_project="$2"
      shift 2
      ;;
    --claudo-repo)
      [[ $# -ge 2 ]] || { echo "--claudo-repo requires a value" >&2; exit 2; }
      claudo_repo="$2"
      shift 2
      ;;
    --claude-task-root)
      [[ $# -ge 2 ]] || { echo "--claude-task-root requires a value" >&2; exit 2; }
      claude_task_root="$2"
      shift 2
      ;;
    --session)
      [[ $# -ge 2 ]] || { echo "--session requires a value" >&2; exit 2; }
      session_id="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

require_dir() {
  local path="$1"
  local label="$2"
  if [[ ! -d "$path" ]]; then
    echo "$label does not exist or is not a directory: $path" >&2
    exit 1
  fi
}

require_cmd() {
  local name="$1"
  if ! command -v "$name" >/dev/null 2>&1; then
    echo "Required command not found: $name" >&2
    exit 1
  fi
}

require_cmd uv
require_dir "$project_root" "Project root"
require_dir "$claudo_repo" "Claudo repo"
require_dir "$claude_task_root" "Claude task root"

if [[ ! -x "$PMS_APP" ]]; then
  PMS_APP="$PMS_REPO/pms-app.sh"
fi
if [[ ! -x "$PMS_APP" ]]; then
  echo "Could not find executable pms-app runner under $PMS_REPO" >&2
  exit 1
fi

PROJECT_ROOT="$(cd "$project_root" && pwd -P)"
CLAUDO_REPO_ABS="$(cd "$claudo_repo" && pwd -P)"
CLAUDE_TASK_ROOT_ABS="$(cd "$claude_task_root" && pwd -P)"

if [[ -z "$pms_project" ]]; then
  pms_project="$(basename "$PROJECT_ROOT")"
fi

PMS_BOOTSTRAP_DIR="$PROJECT_ROOT/.pms/bootstrap"
RAW_EXPORT_DIR="$(mktemp -d "${TMPDIR:-/tmp}/pms-claudo-export.XXXXXX")"
CLAUDO_GRAPH="$RAW_EXPORT_DIR/claudo-live.graph.json"
FILTERED_CLAUDO_GRAPH="$PMS_BOOTSTRAP_DIR/claudo-project.graph.json"

cleanup() {
  local status=$?
  if [[ -n "${RAW_EXPORT_DIR:-}" && -d "$RAW_EXPORT_DIR" ]]; then
    rm -rf "$RAW_EXPORT_DIR"
  fi
  return "$status"
}
trap cleanup EXIT

export PMS_APP_ROOT="$PROJECT_ROOT"
export PMS_APP_NAME="$pms_project"
export PMS_DATA_DIR="$PROJECT_ROOT/.pms"
export PMS_DATABASE_PATH="$PMS_DATA_DIR/pms.db"
export PMS_LOG_DIR="$PMS_DATA_DIR/logs"
export PMS_ENV_FILE="$PMS_DATA_DIR/.env"
export PMS_WRITE_MODE=direct

mkdir -p "$PMS_BOOTSTRAP_DIR" "$PMS_LOG_DIR"

cd "$PROJECT_ROOT"

echo "Importing Claudo graph into project-local PMS"
echo "  project_root: $PROJECT_ROOT"
echo "  pms_project: $pms_project"
echo "  pms_database: $PMS_DATABASE_PATH"
echo "  claudo_repo: $CLAUDO_REPO_ABS"
echo "  claude_task_root: $CLAUDE_TASK_ROOT_ABS"
echo "  raw_claudo_graph: $CLAUDO_GRAPH"
echo "  project_graph: $FILTERED_CLAUDO_GRAPH"
if [[ -n "$session_id" ]]; then
  echo "  session: $session_id"
fi

"$PMS_APP" init >/dev/null

claudo_export=(
  uv run --directory "$CLAUDO_REPO_ABS" claudo export "$CLAUDE_TASK_ROOT_ABS"
  --format json
  -o "$CLAUDO_GRAPH"
)
if [[ -n "$session_id" ]]; then
  claudo_export+=(--session "$session_id")
fi

set -x
"${claudo_export[@]}"
uv run --directory "$PMS_REPO" python "$PMS_REPO/scripts/filter_claudo_graph_for_project.py" \
  "$CLAUDO_GRAPH" \
  --project-root "$PROJECT_ROOT" \
  -o "$FILTERED_CLAUDO_GRAPH"

uv run --directory "$CLAUDO_REPO_ABS" claudo summary "$FILTERED_CLAUDO_GRAPH" --source unified

"$PMS_APP" claudo import "$FILTERED_CLAUDO_GRAPH" \
  --project "$pms_project" \
  --project-root "$PROJECT_ROOT" \
  --dry-run \
  --format json

"$PMS_APP" claudo import "$FILTERED_CLAUDO_GRAPH" \
  --project "$pms_project" \
  --project-root "$PROJECT_ROOT"

"$PMS_APP" project show "$pms_project" --format json
"$PMS_APP" task list --project "$pms_project" --format table
"$PMS_APP" task ready --project "$pms_project" --format table
"$PMS_APP" task blocked --project "$pms_project" --format table
set +x

echo "Done."
echo "  PMS database: $PMS_DATABASE_PATH"
echo "  Project graph: $FILTERED_CLAUDO_GRAPH"
