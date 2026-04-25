# PMS Runners And Environment

This repo ships shell runners that pin execution to this checkout while leaving
runtime state selectable by environment.

## Runners

Use the root runner when you want this repository's PMS implementation from any
working directory:

```bash
/Users/matt/repos/pms/pms.sh config show
/Users/matt/repos/pms/.bin/pms task list --format json
```

Both forms resolve symlinks and then execute:

```bash
uv run --directory <pms-repo-root> pms "$@"
```

Use the app-scoped runner when an application should keep its own PMS database
and logs under that application's root:

```bash
/Users/matt/repos/pms/pms-app.sh --app-root /path/to/app init
/Users/matt/repos/pms/pms-app.sh --app-root /path/to/app task list
```

If `--app-root` is omitted, `pms-app.sh` uses the current working directory.
The `.bin/pms-app` alias behaves the same way.

## App-Scoped Defaults

`pms-app.sh` preserves caller-provided `PMS_*` values. It only fills missing
path variables:

| Variable            | Default from `pms-app.sh`                   |
| ------------------- | ------------------------------------------- |
| `PMS_APP_ROOT`      | current directory, or `--app-root`          |
| `PMS_APP_NAME`      | basename of `PMS_APP_ROOT`, or `--app-name` |
| `PMS_DATA_DIR`      | `$PMS_APP_ROOT/.pms`, or `--data-dir`       |
| `PMS_DATABASE_PATH` | `$PMS_DATA_DIR/pms.db`                      |
| `PMS_LOG_DIR`       | `$PMS_DATA_DIR/logs`                        |
| `PMS_ENV_FILE`      | `$PMS_DATA_DIR/.env`                        |
| `PMS_INVOKE_ARGV0`  | runner path used for command hints          |

That means a sub-application can use a local SQLite PMS store with no setup:

```bash
cd /path/to/app
/Users/matt/repos/pms/.bin/pms-app init
/Users/matt/repos/pms/.bin/pms-app quickstart --defaults
```

For a PostgreSQL-backed app, provide the database connection explicitly:

```bash
PMS_DATABASE_PATH=postgresql://pms:password@localhost/app_pms \
/Users/matt/repos/pms/.bin/pms-app --app-root /path/to/app config show
```

## Environment Contract

Core state:

- `PMS_DATA_DIR`: base runtime directory. Local server tracking is scoped here.
- `PMS_DATABASE_PATH`: SQLite database path or PostgreSQL connection string.
- `PMS_LOG_DIR`: log directory. Defaults to `$PMS_DATA_DIR/logs`.
- `PMS_ENV_FILE`: env file read by settings and written by `pms config set`.

Runtime coordination:

- `PMS_WRITE_MODE`: `direct`, `prefer_server`, or `require_server`.
- `PMS_SERVER_BASE_URL`: preferred PMS API server URL.
- `PMS_API_KEY`: explicit API key value for server-backed commands.
- `PMS_API_KEY_PATH`: local API key file used when `PMS_API_KEY` is unset.
- `PMS_LOCAL_SERVER_STARTUP_TIMEOUT_SECONDS`: local server bootstrap timeout.

Actor and display:

- `PMS_CURRENT_ACTOR_ID`: configured actor for actor-aware commands.
- `PMS_ACTOR`, `PMS_USER`, `USER`, `LOGNAME`: fallback actor labels.
- `PMS_INVOKE_ARGV0`, `PMS_CLI_ARGV0`, `PMS_ARGV0`: command prefix shown in
  next-step output.
- `PMS_ALT_CLI_ARGV0`: alternate command prefix shown in links.
- `PMS_CONSOLE_WIDTH`: fixed console width for text rendering.

Agent defaults:

- `PMS_AGENT_MODEL`
- `PMS_AGENT_MAX_TURNS`
- `PMS_AGENT_MAX_BUDGET_USD`
- `PMS_AGENT_PERMISSION_MODE`

SQLite tuning:

- `PMS_SQLITE_BUSY_TIMEOUT_MS`
- `PMS_SQLITE_LOCK_RETRY_COUNT`
- `PMS_SQLITE_LOCK_RETRY_DELAY_MS`
- `PMS_SQLITE_JOURNAL_MODE`
- `PMS_SQLITE_SYNCHRONOUS`

## Multi-App Pattern

For independent app databases, call `pms-app.sh` from each app root:

```bash
cd ~/repos/app-a
~/repos/pms/.bin/pms-app init

cd ~/repos/app-b
~/repos/pms/.bin/pms-app init
```

Each app gets:

- `~/repos/app-a/.pms/pms.db`
- `~/repos/app-b/.pms/pms.db`

For shared orchestration across apps, set a common `PMS_DATA_DIR` and
`PMS_DATABASE_PATH` before calling either runner.

## Server-Backed Multi-Writer Mode

When multiple agents or processes write to the same PMS database, prefer one
managed local server for that `PMS_DATA_DIR`:

```bash
~/repos/pms/.bin/pms-app --app-root /path/to/app runtime prefer-server --host 127.0.0.1 --port 27541
~/repos/pms/.bin/pms-app --app-root /path/to/app runtime status --format json
~/repos/pms/.bin/pms-app --app-root /path/to/app config show --format json
```

This persists server settings into the app's `PMS_ENV_FILE`, so subsequent
runner calls converge through the same runtime unless the caller overrides the
environment.

`runtime prefer-server` also creates `.pms-admin-key` in the app root and
installs or refreshes the repo-local Rust client. Use that client for repeated
server-backed calls:

```bash
cd /path/to/app
export PMS_API_KEY="$(cat .pms-admin-key)"
~/repos/pms/.bin/pms-client --server http://127.0.0.1:27541 health
~/repos/pms/.bin/pms-client --server http://127.0.0.1:27541 start --format json
```

If a configured port returns `404 Not Found` for `/api/v1/health`, the port is
serving something other than PMS. Re-run `runtime prefer-server` with an
available port and then check `config show`.
