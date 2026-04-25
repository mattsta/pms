#!/usr/bin/env sh
set -eu

script_path=$0
while [ -L "$script_path" ]; do
    script_dir=$(CDPATH= cd "$(dirname "$script_path")" && pwd -P)
    link_target=$(readlink "$script_path")
    case "$link_target" in
        /*) script_path=$link_target ;;
        *) script_path=$script_dir/$link_target ;;
    esac
done

repo_root=$(CDPATH= cd "$(dirname "$script_path")" && pwd -P)

while [ "$#" -gt 0 ]; do
    case "$1" in
        --app-root)
            if [ "$#" -lt 2 ]; then
                echo "pms-app.sh: --app-root requires a value" >&2
                exit 2
            fi
            PMS_APP_ROOT=$2
            export PMS_APP_ROOT
            shift 2
            ;;
        --data-dir)
            if [ "$#" -lt 2 ]; then
                echo "pms-app.sh: --data-dir requires a value" >&2
                exit 2
            fi
            PMS_DATA_DIR=$2
            export PMS_DATA_DIR
            shift 2
            ;;
        --app-name)
            if [ "$#" -lt 2 ]; then
                echo "pms-app.sh: --app-name requires a value" >&2
                exit 2
            fi
            PMS_APP_NAME=$2
            export PMS_APP_NAME
            shift 2
            ;;
        --)
            shift
            break
            ;;
        *)
            break
            ;;
    esac
done

PMS_APP_ROOT=${PMS_APP_ROOT:-$PWD}
app_root=$(CDPATH= cd "$PMS_APP_ROOT" && pwd -P)
PMS_APP_ROOT=$app_root
export PMS_APP_ROOT

if [ -z "${PMS_APP_NAME:-}" ]; then
    PMS_APP_NAME=$(basename "$app_root")
    export PMS_APP_NAME
fi

if [ -z "${PMS_DATA_DIR:-}" ]; then
    PMS_DATA_DIR=$app_root/.pms
    export PMS_DATA_DIR
fi
if [ -z "${PMS_DATABASE_PATH:-}" ]; then
    PMS_DATABASE_PATH=$PMS_DATA_DIR/pms.db
    export PMS_DATABASE_PATH
fi
if [ -z "${PMS_LOG_DIR:-}" ]; then
    PMS_LOG_DIR=$PMS_DATA_DIR/logs
    export PMS_LOG_DIR
fi
if [ -z "${PMS_ENV_FILE:-}" ]; then
    PMS_ENV_FILE=$PMS_DATA_DIR/.env
    export PMS_ENV_FILE
fi
if [ -z "${PMS_INVOKE_ARGV0:-}" ]; then
    PMS_INVOKE_ARGV0=$0
    export PMS_INVOKE_ARGV0
fi

mkdir -p "$PMS_DATA_DIR" "$PMS_LOG_DIR"

exec uv run --directory "$repo_root" pms "$@"
