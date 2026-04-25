# PMS Server Deployment Guide

**Version**: 0.1.0
**Server**: FastAPI + Uvicorn
**Status**: Operator guide for the built-in PMS HTTP server

---

## Scope

This guide covers the live, built-in PMS API server that runs from a source
checkout or installed environment.

Use it for:

- local server startup
- PostgreSQL-backed deployment from the checked-out repo
- health/auth smoke checks
- write-coordination expectations for multi-process local use

Do not use this guide as the authority for:

- fixed route counts
- benchmark numbers
- internet-facing hardening claims
- API schema details

For those, use:

- [`docs/API_ENDPOINT_CATALOG.md`](API_ENDPOINT_CATALOG.md)
- [`docs/API_RESPONSE_CONTRACTS.md`](API_RESPONSE_CONTRACTS.md)
- [`docs/WEB_API.md`](WEB_API.md)
- [`docs/WRITE_COORDINATION_ARCHITECTURE.md`](WRITE_COORDINATION_ARCHITECTURE.md)

---

## Local Quick Start

```bash
# Start the built-in server with the default local SQLite database.
uv run pms serve

# Development reload mode.
uv run pms serve --reload
```

Default bind and entrypoints:

- base URL: `http://127.0.0.1:27541`
- interactive docs: `http://127.0.0.1:27541/docs`
- OpenAPI schema: `http://127.0.0.1:27541/openapi.json`
- dashboard UI: `http://127.0.0.1:27541/dashboard`
- health endpoint: `http://127.0.0.1:27541/api/v1/health`

If you want a non-default bind, make it explicit:

```bash
uv run pms serve --host 0.0.0.0 --port 8000
```

---

## Backend And Runtime Configuration

PMS uses `PMS_*` settings. The main deployment-related ones are:

- `PMS_DATA_DIR`
- `PMS_DATABASE_PATH`
- `PMS_LOG_DIR`
- `PMS_WRITE_MODE`
- `PMS_SERVER_BASE_URL`
- `PMS_API_KEY_PATH`

SQLite example:

```bash
export PMS_DATA_DIR=$HOME/.pms
export PMS_DATABASE_PATH=$PMS_DATA_DIR/pms.db
export PMS_LOG_DIR=$PMS_DATA_DIR/logs

uv run pms serve
```

PostgreSQL example:

```bash
uv sync --extra postgres

# PMS_DATABASE_PATH is the live config field even for PostgreSQL connection strings.
export PMS_DATABASE_PATH=postgresql://pms_user:password@localhost:5432/pms_prod

uv run pms serve --host 0.0.0.0 --port 8000
```

If you want CLI writes and local clients to converge through the server instead
of direct-file SQLite writes, prefer the managed local-runtime flow:

```bash
uv run pms runtime prefer-server --host 127.0.0.1 --port 27541
export PMS_API_KEY="$(cat .pms-admin-key)"
```

Important runtime rule:

- PMS keeps one active local server per `PMS_DATA_DIR`
- rebinding the same data dir to a new host/port replaces the previous active
  local server instead of silently leaving duplicate authorities behind

See [`docs/WRITE_COORDINATION_ARCHITECTURE.md`](WRITE_COORDINATION_ARCHITECTURE.md)
for the full write-path contract.

---

## Authentication And Smoke Check

Protected API routes require `X-API-Key`.

Bootstrap a local admin key:

```bash
uv run pms auth init --show-key
export PMS_API_KEY="$(cat .pms-admin-key)"
```

Minimal smoke checks:

```bash
curl -s http://127.0.0.1:27541/api/v1/health | jq
curl -s -H "X-API-Key: $PMS_API_KEY" http://127.0.0.1:27541/api/v1/auth/scopes | jq
```

---

## Health Contract

`GET /api/v1/health` is implemented in `pms/api/app.py` and returns:

```json
{
  "status": "healthy",
  "database": "healthy",
  "backend": "sqlite",
  "schema_version": 1,
  "schema_name": "stable",
  "uptime_seconds": 12.34
}
```

Notes:

- `status` is `healthy` or `degraded`
- `database` is a plain string; it is `"healthy"` on success and an error-shaped
  string when the probe fails
- `backend` is the active backend name, such as `sqlite` or `postgresql`
- `schema_version` and `schema_name` come from the live schema bootstrapping path

---

## Supported Operator Entry Points

These are the main built-in server entry points:

- `GET /`
- `GET /docs`
- `GET /openapi.json`
- `GET /dashboard`
- `GET /api/v1/health`

Do not hardcode endpoint counts into deployment docs. Use the generated live
route inventory in [`docs/API_ENDPOINT_CATALOG.md`](API_ENDPOINT_CATALOG.md).

---

## Deployment Examples

These are source-checkout examples, not packaged-install guarantees.

### Container Example

```dockerfile
FROM python:3.14-slim

WORKDIR /app
COPY . .

RUN pip install uv
RUN uv sync --extra postgres

ENV PMS_DATABASE_PATH=postgresql://pms:password@db:5432/pms
EXPOSE 8000

CMD ["uv", "run", "pms", "serve", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
docker build -t pms-server .
docker run -p 8000:8000 \
  -e PMS_DATABASE_PATH=postgresql://pms:password@db:5432/pms \
  pms-server
```

### Systemd Example

```ini
[Unit]
Description=PMS API Server
After=network.target

[Service]
Type=simple
User=pms
WorkingDirectory=/opt/pms
Environment="PMS_DATA_DIR=/var/lib/pms"
Environment="PMS_DATABASE_PATH=postgresql://pms:password@localhost/pms"
Environment="PMS_LOG_DIR=/var/log/pms"
ExecStart=/usr/bin/env uv run pms serve --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

---

## Health Monitoring

Recommended checks:

- `GET /api/v1/health` for basic liveness and database reachability
- `GET /docs` and `GET /openapi.json` for HTTP surface discovery
- `uv run pms runtime status --format json` when coordinating local managed servers

PMS does not treat hand-maintained benchmark numbers as deployment truth. Measure
startup, latency, throughput, and pool sizing in your own environment.

---

## Security Notes

Current live behavior:

- protected API routes use API-key auth via `X-API-Key`
- the built-in server binds to loopback by default
- the app currently installs permissive CORS middleware (`allow_origins=["*"]`)

Before exposing PMS beyond loopback, add your own:

- TLS termination
- reverse proxy or network ACL boundary
- rate limiting
- origin restrictions
- external monitoring and APM if required

Treat this guide as operator truth for the built-in server, not as a claim that
PMS is already hardened for arbitrary internet exposure.
