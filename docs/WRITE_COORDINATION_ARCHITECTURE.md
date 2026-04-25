# Write Coordination Architecture

PMS supports three runtime write modes:

- `direct`
- `prefer_server`
- `require_server`

This document defines the intended architecture for server-preferred operation so multi-process PMS usage stays predictable and fast without losing local-first behavior.

## Goals

- keep single-user local PMS simple
- avoid SQLite lock contention and revision races under concurrent writers
- preserve direct-file fallback when no server is running
- make repeated reads fast through a warm local API server and Rust client
- keep Python CLI, HTTP API, and Rust client behavior aligned

## Current Runtime Model

Today PMS already has:

- config:
  - `PMS_WRITE_MODE`
  - `PMS_SERVER_BASE_URL`
- server probing in `pms/runtime/write_coordination.py`
- runtime enforcement in key mutating CLI commands
- delegated server-backed writes for:
  - `task progress`
  - `task start`
  - `task complete`
  - `goal create`
  - `plan create`

Current behavior:

- `direct`
  - write directly to SQLite
- `prefer_server`
  - probe server
  - use server-backed path when reachable and authenticated
  - otherwise fall back to direct SQLite writes
- `require_server`
  - probe server
  - refuse direct writes when the server is unavailable

## Intended Steady-State Architecture

### One warm local write authority

Preferred local topology:

- `pms serve` runs continuously on `127.0.0.1`
- Python CLI and Rust client both target the same local API server
- the server is the primary serialized writer for normal mutating operations

This avoids:

- repeated Python startup cost for read-heavy traffic
- multiple independent SQLite writers competing with each other
- revision/order races across separate local processes

### Direct-file fallback remains first-class

PMS must remain usable without a background server.

Fallback rules:

- if `write_mode=direct`, always write locally
- if `write_mode=prefer_server` and server probe fails, write locally
- if `write_mode=require_server` and server probe fails, fail loudly with exact recovery commands

## Mutation Truth Contract

Configured intent is not enough for operators or automation.

Machine-readable mutation surfaces should expose the effective write landing path:

- JSON mutation output includes `runtime_write`
- text mutation output suppresses successful runtime plumbing and only emits degraded or blocked coordination messages

Use these fields as truth:

- `runtime_write.write_mode`
- `runtime_write.write_path`
- `runtime_write.target_kind`
- `runtime_write.target_location`

This lets clients distinguish:

- intended server-backed coordination
- actual server delegation
- direct-file fallback into the current workspace database

Covered user-visible surfaces include:

- `project create`
- `task add` / `task create`
- `plan create` / `plan update`
- `goal create`
- `task start` / `task progress` / `task complete`

Truthfulness still matters for local-only commands. If a surface does not
actually delegate through the server yet, PMS must report `direct_file` even
when the workspace is configured for `prefer_server`.

Blocked execution is part of the same truth contract. If a task is linked to a
draft plan, PMS should fail `task start` and `task progress` non-zero and emit
machine-readable error output in JSON mode instead of pretending the mutation
succeeded.

Delegated auth failures belong to the same contract. If server-backed execution
returns `Invalid API key`, the CLI should fail non-zero and emit a
machine-readable JSON error instead of returning exit code `0`.

A reachable localhost target is not automatically trustworthy. If PMS reports a
reachable but unmanaged local server, operators should rebind to a managed
local runtime before trusting delegated writes, auth convergence, or workspace
identity.

This preserves:

- zero-setup local usage
- offline usage
- recovery when the local server is down

### Shared command surface, separate transport

The command contract should stay the same regardless of transport.

That means:

- same user-visible command shape
- same output fields
- same continuation hints
- same error semantics where possible

Only the transport changes:

- direct repository/service call in `direct`
- HTTP delegation in server-backed mode

### Warm-read fast path

For repeated reads and reports, prefer:

- local PMS server
- installed Rust client at `./.bin/pms-client`

Validated repeated-read performance on this repo:

- `uv run pms task list ...` about `1.0s`
- `./.bin/pms-client --server http://127.0.0.1:27541 task list ...` about `0.01s`

This is the main reason to keep the server path ergonomic and maintained.

## Write Path Requirements

Server-backed writes must guarantee:

- authenticated caller identity
- one authoritative state transition per request
- revision-safe write ordering
- event and revision history parity with direct mode
- no silent field loss between transports

The server-backed path should be considered complete only when:

- main mutating CLI flows delegate cleanly
- API/client parity audits stay green
- Rust and Python output parity stays operationally useful

## Reliability Requirements

The design should tolerate:

- transient local server restarts
- stale admin-key files
- temporary lock contention
- partial CLI adoption across tools

Expected operator recovery path:

1. `uv run pms config show --format json`
2. `uv run pms runtime prefer-server --host 127.0.0.1 --port 8000`
   This persists runtime bootstrap settings to the resolved env file for the
   current execution context, not blindly to the workspace `.env`.
3. `export PMS_API_KEY="$(cat .pms-admin-key)"`
4. `./.bin/pms-client --server http://127.0.0.1:27541 start --format json`

## Security Requirements

- local server binds to loopback by default
- server-backed writes require an API key
- CLI must not silently downgrade from `require_server`
- docs must not point users at unstable build paths for the Rust binary
- installed binary path remains stable at `./.bin/pms-client`

If PMS is exposed beyond loopback, stronger auth and deployment hardening are required. That is outside the local-first default contract.

## Remaining Implementation Work

The design is set, but several implementation slices still matter:

1. extend delegated server-backed writes beyond the current high-frequency commands where needed
2. keep Rust/API/Python parity audits active so transport drift is caught early
3. keep improving local server ergonomics so operators naturally adopt the warm-server path
4. prefer server-backed reads for repeated report traffic

## Operator Guidance

Recommended local multi-process setup:

```bash
uv run pms serve --host 127.0.0.1 --port 8000
uv run pms config set --write-mode prefer_server --server-url http://127.0.0.1:27541
export PMS_API_KEY="$(cat .pms-admin-key)"
```

When you need isolated config persistence for tests, audits, or scratch runs,
set `PMS_ENV_FILE` to an alternate env path before invoking `config set`.
Use `config show` afterward to verify the resolved target:

- JSON: `paths.env_file`
- text: `Env file: ...`

Recommended fast read path:

```bash
./scripts/install_pms_client.sh
PMS_API_KEY="$(cat .pms-admin-key)" ./.bin/pms-client --server http://127.0.0.1:27541 start --format json
```

Recommended fallback path:

```bash
uv run pms config set --write-mode direct
uv run pms start --format json
```

## Definition of Done

This design task is complete when:

- the architecture is documented in-repo
- the docs point operators to the intended local server workflow
- the runtime model and fallback behavior are explicit
- future implementation work can reference this contract instead of reconstructing intent
