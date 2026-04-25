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

if [ -z "${PMS_INVOKE_ARGV0:-}" ]; then
    PMS_INVOKE_ARGV0=$0
    export PMS_INVOKE_ARGV0
fi

exec uv run --directory "$repo_root" pms "$@"
