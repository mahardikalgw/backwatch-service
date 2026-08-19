# backwatch — Centralized Database Backup & Monitoring

Agent-based database backup system that centralizes backup execution, metadata
recording, monitoring, and alerting for multiple applications (PostgreSQL and
MySQL) into a single place. It answers one question:

> Have the databases of all applications been successfully backed up, and are those backups safe to use?

Built from the requirements in
[`centralized-database-backup-monitoring-prd.md`](centralized-database-backup-monitoring-prd.md).

## Features

- **Per-server backup agents** — run `pg_dump` / `mysqldump`, compress to gzip, compute a SHA-256 checksum, upload, and verify the object before reporting.
- **Centralized Backup API** — FastAPI service that authenticates agents, records every backup as a structured run, and serves history/status/health endpoints.
- **Cross-engine support** — PostgreSQL and MySQL out of the box.
- **S3-compatible object storage** — works with MinIO, Ceph RGW, AWS S3, or any S3-compatible service (rustfs with an S3 API). A local-filesystem driver is included for a runnable MVP.
- **Status model** — every backup results in `SUCCESS`, `FAILED`, `RUNNING`, or `OVERDUE`; never "nothing happened".
- **Container self-healing** — every service carries a healthcheck + `restart:
  unless-stopped`, and a host watchdog (`backwatch-autoheal.timer`) restarts
  any exited or unhealthy container every minute.
- **Overdue detection** — schedule-aware (`daily`, `hourly`, `weekly`, or `24h`-style strings) with metric refresh + first-incident alerts run by a 15-minute watcher.
- **Prometheus metrics + Grafana** — dashboards and alert rules included; optional OpenTelemetry instrumentation.
- **Per-application API keys** — each app has a unique key; only a salted digest is stored.
- **Retention pruning** — local backups older than `RETENTION_DAYS` are pruned on a daily systemd timer.
- **Alerting** — generic webhook channel (Telegram/Discord/email compatible via `{"text": ...}`) for failed and overdue backups.

## Architecture

```text
                    ┌──────────────────┐
                    │    Application   │
                    │     Servers      │
                    └────────┬─────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
           Backup           Backup        Backup
           Agent            Agent         Agent
              │              │              │
              └──────────────┼──────────────┘
                             │
                         HTTPS/API
                             │
                             ▼
                  ┌────────────────────┐
                  │   Backup API       │
                  │      FastAPI       │
                  └─────────┬──────────┘
                            │
                    ┌───────┴────────┐
                    │                │
                    ▼                ▼
             PostgreSQL          S3 storage
             Metadata            Backup Files
                    │
                    ▼
                Dashboard
                    │
                    ▼
              Monitoring / Ops
```

Two deployables:

| Deployable | Runs on | Entry point |
|---|---|---|
| **Backup API** (`app/`) | one central server | `uvicorn app.main:app` |
| **Backup agent** (`agent/`) | every application/database server | `python -m agent.main run --report` |

The API only stores metadata. Backup files live in object storage; the API
never runs `pg_dump` itself.

## Repository structure

```text
app/                 Backup API (FastAPI)
├── api/v1/endpoints    health, backups, applications, backup_health
├── core/               settings, async database, API-key security
├── metrics/            Prometheus metric families
├── models/             Application, BackupRun, BackupEvent (SQLAlchemy)
├── repositories/       async data-access layer
├── schemas/            Pydantic request/response models
└── services/           business logic incl. overdue detection + alerting
agent/               Backup agent (runs on each database server)
├── backup.py           pipeline: dump → validate → upload → verify → report
├── database.py         pg_dump/mysqldump + gzip
├── storage.py          local + S3-compatible drivers
├── validator.py        size/checksum/object-existence checks
├── config.py           agent settings (env-driven)
├── logger.py           structured JSON logging
├── main.py             CLI (run, prune)
└── schedulers/         systemd/cron examples
deploy/              Production deployment scaffolds + runbook
├── README.md           rollout, verification, rollback instructions
├── api/                installer, Nginx TLS template, watcher timer
└── agent/              idempotent installer, systemd unit templates
scripts/             seed_applications.py, overdue_watcher.py
monitoring/          Prometheus config, alert rules, Grafana dashboard
tests/               pytest suite (API + agent)
alembic/             migration scaffolding (no migrations yet)
compose.yaml         local full stack: postgres + api + prometheus + grafana
```

## Backup record

Every backup produces a structured record (`backup_runs`), e.g.:

```json
{
  "application": "talenta",
  "database_type": "postgresql",
  "database_name": "talenta",
  "status": "success",
  "started_at": "2026-08-12T00:00:00Z",
  "finished_at": "2026-08-12T00:03:12Z",
  "duration_seconds": 192,
  "size_bytes": 2483920128,
  "storage": "s3",
  "storage_path": "talenta/2026/08/12/backup.sql.gz",
  "checksum": "sha256:...",
  "error": null
}
```

## Status model

- `RUNNING` — in progress.
- `SUCCESS` — dump produced a non-empty file, checksum computed, upload verified.
- `FAILED` — any step failed (dump, validation, upload, verification).
- `OVERDUE` — no successful backup within the application's schedule interval
  (`daily` → 24h, `hourly`, `weekly`, or custom like `12h30m`).
- `NO_BACKUP` — application registered but never backed up and not yet overdue.

## Storage

Backup files are never stored in the database.

| Driver | Config | Use case |
|---|---|---|
| `local` | `STORAGE_BASE_DIR` | runnable MVP; files on each agent host |
| `s3` | `STORAGE_ENDPOINT`, `STORAGE_ACCESS_KEY`, `STORAGE_SECRET_KEY`, `STORAGE_REGION`, `STORAGE_BUCKET` | production — MinIO, Ceph RGW, AWS S3, rustfs with S3 API |

The S3 bucket must already exist; the agent does not auto-create it. Keys are
namespaced as `<bucket>/<application>/<YYYY>/<MM>/<DD>/<name>.dump.gz`.

## Quickstart (local development)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 1. Start the API (SQLite by default)
uvicorn app.main:app --reload
# docs at http://127.0.0.1:8000/docs

# 2. Register the apps and capture the printed API keys
python scripts/seed_applications.py

# 3. Run one backup cycle for an application (agent side)
export APPLICATION=talenta DB_HOST=localhost DB_NAME=talenta DB_USER=talenta \
       DB_PASSWORD=... API_URL=http://127.0.0.1:8000 API_KEY=<key-from-seed>
python -m agent.main run --report
```

Copy `.env.example` to `.env` and adjust for persistent local configuration.

### Full stack with Podman Compose

```bash
podman-compose up -d
```

Brings up PostgreSQL (metadata), the Backup API, Prometheus, and Grafana
(dashboard provisioned from `monitoring/grafana-dashboard.json`). The stack
defines `backup-api` with `build: .` (built from `Containerfile` by
`podman build`); override the registry image with `BACKWATCH_IMAGE`.

## Environment configuration

### Backup API (`app/core/config.py`)

| Variable | Default | Description |
|---|---|---|
| `APP_NAME` | `Backup API` | OpenAPI title |
| `API_V1_PREFIX` | `/api/v1` | URL prefix for versioned endpoints |
| `DATABASE_URL` | `sqlite+aiosqlite:///./backwatch.db` | async SQLAlchemy connection string |
| `SECRET_KEY` | `change-me-in-production` | salt for API-key hashing (**set in prod**) |
| `CORS_ORIGINS` | `*` | comma-separated allowed origins |
| `API_KEY_HEADER` | `X-API-Key` | header carrying the per-app key |
| `ENABLE_METRICS` | `true` | expose `/metrics` |
| `BACKWATCH_STATE_FILE` | `/var/backwatch/watcher-state.json` | watcher alert-dedup state |

### Backup agent (`agent/config.py`)

| Variable | Default | Description |
|---|---|---|
| `APPLICATION` | `talenta` | application slug reported to the API |
| `DATABASE_TYPE` | `postgresql` | `postgresql` or `mysql` |
| `DB_HOST` / `DB_PORT` / `DB_NAME` / `DB_USER` / `DB_PASSWORD` | — | database being backed up |
| `STORAGE_DRIVER` | `local` | `local` or `s3` |
| `STORAGE_BASE_DIR` | `./backups` | local driver base path |
| `STORAGE_BUCKET` | `database-backups` | S3 bucket / path prefix |
| `STORAGE_ENDPOINT` / `STORAGE_ACCESS_KEY` / `STORAGE_SECRET_KEY` / `STORAGE_REGION` | — | S3 driver settings (`s3` only) |
| `API_URL` | `http://localhost:8000` | Backup API base URL |
| `API_KEY` | `change-me` | per-application API key |
| `RETENTION_DAYS` | `30` | local pruning window |
| `TEMP_DIR` | `./tmp` | temporary dump working directory |

## API reference

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/health` | — | API liveness |
| `GET` | `/metrics` | — | Prometheus metrics |
| `POST` | `/api/v1/backups` | `X-API-Key` | record a backup result (agent) |
| `GET` | `/api/v1/backups` | — | history; filters: `application`, `status`, `date`, `database_type` |
| `GET` | `/api/v1/backups/{id}` | — | single backup run |
| `GET` | `/api/v1/applications` | — | list registered applications |
| `POST` | `/api/v1/applications` | — | register an application + API key |
| `GET` | `/api/v1/applications/{id}/backup-status` | — | latest status of an application |
| `GET` | `/api/v1/health/backups` | — | aggregate health summary |

Interactive docs: `/docs` and `/redoc`.

## Monitoring & alerting

Prometheus metrics (PRD §16), exposed at `/metrics`:

```text
backup_success_total{application, database_type}
backup_failure_total{application, database_type}
backup_last_success_timestamp{application}
backup_last_failure_timestamp{application}
backup_duration_seconds{application}
backup_size_bytes{application}
backup_overdue{application}
```

- **Prometheus** config + alert rules in `monitoring/` (`prometheus.yml`,
  `prometheus-alerts.yml`).
- **Grafana** dashboard provisioned from `monitoring/grafana-dashboard.json`.
- **Watcher** (`scripts/overdue_watcher.py`) — runs on the API host every
  15 minutes (systemd timer), refreshes `backup_overdue`, and alerts once per
  new `FAILED`/`OVERDUE` incident. Configure the channel with `ALERT_WEBHOOK_URL`.

## Security

- **Credentials** are never hardcoded — everything comes from environment
  variables / secrets files.
- **API keys** are per application; only a salted SHA-256 digest
  (`hash_api_key`, HMAC with `SECRET_KEY`) is stored. A leaked key only
  affects one application.
- Set a strong `SECRET_KEY` in production and serve the API behind TLS (Nginx
  template in `deploy/api/nginx.conf`).
- DB passwords are passed to dump tools via `PGPASSWORD` / `MYSQL_PWD`
  environment variables, never on the command line.

## Testing & quality

```bash
.venv/bin/python -m pytest -q        # test suite (22 tests)
.venv/bin/ruff check app agent scripts tests
.venv/bin/ruff format --check app agent scripts tests
.venv/bin/mypy app agent scripts     # strict type checking
```

## CI/CD

GitHub Actions workflows in `.github/workflows/`:

- **`ci.yml`** — on push/PR to `main`: ruff lint + format, strict mypy, pytest.
- **`release.yml`** — on a `v*` tag:
  1. builds the **agent wheel** (`backwatch_agent-<ver>-py3-none-any.whl`) and a
     `backwatch-agent-deploy.tar.gz` (systemd templates), attached to a GitHub
     Release;
  2. builds the **API container image** with Podman and pushes it to GHCR
     (`ghcr.io/mahardikalgw/backwatch-service:<tag>` and `:latest`);
  3. **deploys the API** over SSH to the central server (`podman-compose pull`
     + `up -d --no-build`).

Required repository secrets (Settings → Secrets and variables → Actions):

| Secret | Used by | Description |
|---|---|---|
| `DEPLOY_HOST` | release.yml | IP/host of the central server |
| `DEPLOY_USER` | release.yml | SSH user on the central server |
| `DEPLOY_SSH_KEY` | release.yml | private SSH key of `DEPLOY_USER` |
| `GHCR_USER` | release.yml | GitHub user for the server's GHCR login |
| `GHCR_TOKEN` | release.yml | GitHub PAT with `read:packages` for the server to pull images |

Releasing:

```bash
git tag v0.1.0
git push origin v0.1.0
```

The **agent is not auto-deployed** by the pipeline — each application server
pulls its artifact from the GitHub Release when you run the installer:

```bash
sudo BACKWATCH_VERSION=v0.1.0 ./deploy/agent/install.sh talenta --schedule "*-*-* 00:00:00"
```

## Deployment

Two deployables on separate servers — the API once, the agent once per
application server. The API image is released via GitHub Actions (see
CI/CD above); the agent is installed from the release artifact. See
**[`deploy/README.md`](deploy/README.md)** for the full runbook
(prerequisites, installers, canary rollout order, verification, rollback,
incident reference).

Central server (first-time provisioning only):

```bash
sudo ./deploy/api/install.sh v0.1.0
```

Application servers (one per app, staggered schedule):

```bash
sudo ./deploy/agent/install.sh talenta --schedule "*-*-* 00:00:00"
sudo ./deploy/agent/install.sh simaira --schedule "*-*-* 01:00:00"
```

Canary order: `talenta → simaira → cakra → liyatra → app-e`. After each step,
confirm `GET /api/v1/applications/{id}/backup-status` reports `SUCCESS`.

## Agent CLI

```text
usage: backup-agent [-h] {run,prune} ...

positional commands:
  run     Run one backup and report the result
          --report    report the result to the Backup API
  prune   Delete backups older than retention
```

## Known limitations / next steps

- SQLite is the default local database; production uses PostgreSQL via the
  `DATABASE_URL` connection string.
- No Alembic migration files yet — tables are created by the app at startup
  (`Base.metadata.create_all`). Generate migrations before production rollout.
- S3 bucket must be created out of band (no auto-provisioning).
- Restore is a manual operation; restore-verification is a Phase-2 goal.
- The API filters backup history in Python rather than in SQL (fine for 5 apps).

## License

Internal infrastructure tooling — no public license.