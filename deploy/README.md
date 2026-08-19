# backwatch Deployment Runbook

Two deployables, two kinds of hosts. The **Backup API** runs on one central
server; the **backup agent** runs once per application server (5 servers here).

```
┌──────────────┐        HTTPS/API        ┌─────────────────────┐
│ app server 1 │──▶ backwatch-agent ────▶│   central server    │
│ app server 2 │──▶ backwatch-agent ────▶│  backup-api (FastAPI)│
│ app server 5 │──▶ backwatch-agent ────▶│  postgres/prom/graf │
└──────────────┘                         └─────────────────────┘
```

## 0. Pre-flight (one-time)

- [ ] Choose backup storage: `STORAGE_DRIVER=s3` (MinIO / Ceph RGW / AWS S3 /
      rustfs exposing an S3 API) or `STORAGE_DRIVER=local` (files on the agent
      disk) for the MVP. The S3 driver needs `STORAGE_ENDPOINT`,
      `STORAGE_ACCESS_KEY`, `STORAGE_SECRET_KEY`, and the bucket to exist.
- [ ] Set production `SECRET_KEY` on the API host (`openssl rand -hex 32`).
- [ ] Create one API key per application via `scripts/seed_applications.py` (keys print once).
- [ ] Get DNS + TLS cert for `backup.example.com` (or your domain).
- [ ] Optional: `ALERT_WEBHOOK_URL` for Telegram/Discord/email.
- [ ] Configure the GitHub Actions secrets for CI/CD (`DEPLOY_HOST`,
      `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `GHCR_USER`, `GHCR_TOKEN` — see the
      CI/CD section of the root README).

## 1. Deploy API (central server)

The `install.sh` below is **first-time provisioning only**. Once the
`.github/workflows/release.yml` pipeline is running, every `v*` tag builds the
API image, pushes it to GHCR, and SSHes here to pull + recreate the container
automatically.

```bash
sudo ./deploy/api/install.sh v0.1.0
# then edit /opt/backwatch-api/.env on first run, and re-run:
sudo ./deploy/api/install.sh v0.1.0
sudo cp deploy/api/nginx.conf /etc/nginx/sites-available/backwatch
sudo ln -sf /etc/nginx/sites-available/backwatch /etc/nginx/sites-enabled/backwatch
sudo nginx -t && sudo systemctl reload nginx
```

Ongoing updates (CI/CD):

```bash
git tag v0.1.1 && git push origin v0.1.1   # triggers release.yml
```

The installer also enables two host-level systemd timers:

- `backwatch-watcher.timer` — every 15 minutes, refreshes the `backup_overdue`
  metric and alerts on new FAILED/OVERDUE incidents (PRD §18, §20).
- `backwatch-autoheal.timer` — every minute, restarts any backwatch container
  that is exited or whose healthcheck reports `unhealthy`. Combined with the
  `restart: unless-stopped` policies and healthchecks in `compose.yaml`,
  this is the container self-healing layer.

Verify:
```bash
curl -s https://backup.example.com/health                    # {"status":"ok"}
curl -s https://backup.example.com/api/v1/health/backups
curl -s https://backup.example.com/metrics | grep backup_
podman ps --filter "label=com.docker.compose.project=backwatch"   # all healthy
sudo journalctl -u backwatch-autoheal.service -n 20               # watchdog log
```

## 2. Deploy agent (per application server, staggered)

The installer downloads the agent wheel + systemd templates from the GitHub
Release (`backwatch_agent-<ver>.whl` and `backwatch-agent-deploy.tar.gz`), so
no git checkout is needed on application servers. Roll out talenta first,
verify, then the rest (PRD §9 schedule):

```bash
# server talenta
sudo BACKWATCH_VERSION=v0.1.0 ./deploy/agent/install.sh talenta --schedule "*-*-* 00:00:00"
# server simaira
sudo BACKWATCH_VERSION=v0.1.0 ./deploy/agent/install.sh simaira --schedule "*-*-* 01:00:00"
# server cakra, liyatra, app-e: repeat with the next hour
```

Each server needs its own `/etc/backwatch/<app>.env` (from `env.example`)
with that application's DB credentials and per-application API key. To update
an already-deployed agent, re-run the installer with a newer
`BACKWATCH_VERSION`.

## 3. Rollout order (canary)

```
1. talenta     — pilot; watch one full cycle
2. simaira     — same stack as talenta
3. cakra       — introduces a third postgres schedule
4. liyatra     — first MySQL server
5. app-e       — MySQL, last
```

After each step, confirm in the API instead of trusting the server:

```bash
curl -s https://backup.example.com/api/v1/applications/{id}/backup-status
# status must be SUCCESS with a sane duration/size; else inspect:
journalctl -u backwatch-agent@<app>.service -f
```

## 4. Normal operations

- **Health**: dashboard at `/api/v1/health/backups` → `healthy` for all.
- **Metrics**: Grafana (provisioned dashboard) + Prometheus alerts in `monitoring/`.
- **Retention**: `backwatch-prune@<app>.timer` runs daily 02:30 and deletes
  local files older than `RETENTION_DAYS` (S3 lifecycle rules for remote files).
- **Upgrade**: release a tag → re-run both installers at the new version; the
  API upgrade first, then each agent.

## 5. Rollback

- **Agent**: `systemctl disable --now backwatch-agent@<app>.timer` — backups stop cleanly;
  manually restore the last good backup if needed. Downgrade by re-running
  `install.sh` with a previous `BACKWATCH_VERSION`.
- **API**: `podman-compose down` + `git checkout <previous-tag>` + re-run
  `install.sh`; data is safe in the Postgres volume. The autoheal watchdog
  stays enabled and will restart the re-deployed containers.

## 6. Incident quick reference

| Symptom | Check |
|---|---|
| Agent exits non-zero | `journalctl -u backwatch-agent@<app>.service` |
| Backup shows OVERDUE | timer enabled? `systemctl is-enabled backwatch-agent@<app>.timer`; schedule drop-in correct? |
| No metrics in Grafana | `curl /metrics` on API; Prometheus target Up? |
| Container flapping | `systemctl status backwatch-autoheal` + `journalctl -t backwatch-autoheal`; `podman logs <container>` |
| Alert noise | state file at `/var/backwatch/watcher-state.json` (resets after container restart is expected) |

## Files

```
deploy/
├── api/
│   ├── .env.production.example     # API env template
│   ├── install.sh                  # central-server installer (idempotent)
│   ├── nginx.conf                  # TLS reverse-proxy template
│   ├── backwatch-watcher.service   # 15-min overdue/alert pass
│   ├── backwatch-watcher.timer
│   ├── backwatch-autoheal.sh       # restart exited/unhealthy containers
│   ├── backwatch-autoheal.service  # 1-min self-healing pass
│   └── backwatch-autoheal.timer
└── agent/
    ├── env.example                 # per-app agent env template
    ├── install.sh                  # per-server installer (idempotent)
    ├── backwatch-agent@.service    # signed unit: run one backup + report
    ├── backwatch-agent@.timer      # daily trigger (drop-in overrides schedule)
    ├── backwatch-prune@.service
    └── backwatch-prune@.timer      # daily retention cleanup
```

Local-only examples (single server, no TLS) remain in `agent/schedulers/`.