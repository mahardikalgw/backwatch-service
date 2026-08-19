#!/usr/bin/env bash
# Deploy the backwatch Backup API to the central server (initial provisioning).
#
# Ongoing releases are deployed by CI/CD (.github/workflows/release.yml), which
# pushes the API image to GHCR and SSHes here to pull + recreate the container.
# This script clones the pinned release for the first bootstrapping, seeds the
# applications, and installs the host-level systemd timers.
#
# Prerequisites on the host: docker, docker compose, git, curl.
#
# Usage:
#   BACKWATCH_API_DIR=/opt/backwatch-api ./deploy/api/install.sh <version-tag>
#   e.g. ./deploy/api/install.sh v0.1.0
#
# Idempotent: safe to re-run; only the masked steps (seed keys, migrations)
# require manual attention after the first run.

set -euo pipefail

VERSION="${1:?usage: install.sh <version-tag> e.g. v0.1.0}"
API_DIR="${BACKWATCH_API_DIR:-/opt/backwatch-api}"
REPO_URL="${BACKWATCH_REPO_URL:-https://github.com/mahardikalgw/backwatch-service.git}"
DOMAIN="${BACKWATCH_DOMAIN:-backup.example.com}"

log() { printf '[install] %s\n' "$*"; }

if [[ $EUID -ne 0 ]]; then
    echo "run as root (sudo)" >&2
    exit 1
fi

mkdir -p "$API_DIR"
cd "$API_DIR"

# 1. Fetch the pinned release.
if [[ ! -d .git ]]; then
    log "cloning repository into $API_DIR"
    git clone "$REPO_URL" .
fi
log "checking out $VERSION"
git fetch --tags --prune
git checkout "$VERSION"

# 2. Environment configuration (kept outside the repo checkout).
ENV_FILE="$API_DIR/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    log "creating .env from deploy/api/.env.production.example"
    cp deploy/api/.env.production.example "$ENV_FILE"
    log "EDIT $ENV_FILE and set DATABASE_URL, SECRET_KEY, CORS_ORIGINS"
    exit 1
fi

# 3. Load runtime and bring up the stack.
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

log "starting postgres, backup-api, prometheus, grafana"
docker compose up -d --wait --scale backup-api=1

# 4. Schema: prefer alembic when migrations exist, else let startup create_all.
if compgen -G "alembic/versions/*.py" >/dev/null; then
    log "applying alembic migrations"
    docker compose exec backup-api alembic upgrade head
else
    log "no migrations present; tables are created by the app lifespan"
fi

# 5. Seed applications and print API keys (only first run; skips existing).
log "seeding applications (capture the printed API keys!)"
docker compose exec backup-api python scripts/seed_applications.py

# 6. Install the overdue-metrics alerting watcher on the host.
log "installing backwatch-watcher timer (every 15 minutes)"
cp deploy/api/backwatch-watcher.service /etc/systemd/system/
cp deploy/api/backwatch-watcher.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now backwatch-watcher.timer

# 7. Install the container self-healing watchdog on the host.
log "installing backwatch-autoheal watchdog (every minute)"
mkdir -p /usr/local/lib
cp deploy/api/backwatch-autoheal.sh /usr/local/lib/backwatch-autoheal.sh
chmod +x /usr/local/lib/backwatch-autoheal.sh
cp deploy/api/backwatch-autoheal.service /etc/systemd/system/
cp deploy/api/backwatch-autoheal.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now backwatch-autoheal.timer

log "install the reverse proxy next:"
log "  sed -i 's/backup.example.com/$DOMAIN/g' deploy/api/nginx.conf"
log "  cp deploy/api/nginx.conf /etc/nginx/sites-available/backwatch"
log "  ln -sf /etc/nginx/sites-available/backwatch /etc/nginx/sites-enabled/backwatch"
log "  nginx -t && systemctl reload nginx"
log "done: health check on https://$DOMAIN/health and https://$DOMAIN/api/v1/health/backups"