#!/usr/bin/env bash
# Deploy/update the backwatch backup agent on one application server.
#
# Idempotent. Deploy one per application server; the only thing that differs
# between servers is /etc/backwatch/<app>.env.
#
# Usage (run as root):
#   ./deploy/agent/install.sh <app> [--schedule "*-*-* 01:00:00"]
#
# Example:
#   ./deploy/agent/install.sh talenta --schedule "*-*-* 00:00:00"
#   ./deploy/agent/install.sh simaira --schedule "*-*-* 01:00:00"

set -euo pipefail

APP="${1:?usage: install.sh <app> [--schedule '*-*-* HH:MM:SS']}"
SCHEDULE="*-*-* 00:00:00"
if [[ "${2:-}" == "--schedule" ]]; then
    SCHEDULE="${3:?--schedule requires a systemd calendar expression, e.g. '*-*-* 01:00:00'}"
fi

APP_DIR="${BACKWATCH_APP_DIR:-/opt/backwatch}"
REPO_URL="${BACKWATCH_REPO_URL:-https://github.com/example/backwatch.git}"
VERSION="${BACKWATCH_VERSION:-v0.1.0}"
ENV_FILE="/etc/backwatch/${APP}.env"

log() { printf '[install:%s] %s\n' "$APP" "$*"; }

if [[ $EUID -ne 0 ]]; then
    echo "run as root (sudo)" >&2
    exit 1
fi

# 1. System prerequisites: Python venv support and the dump CLI tools.
if command -v apt-get >/dev/null; then
    apt-get update
    apt-get install -y python3-venv python3-pip postgresql-client
elif command -v yum >/dev/null; then
    yum install -y python3 python3-pip postgresql
else
    echo "unsupported package manager (add pg_dump/mysqldump + python3-venv manually)" >&2
fi

# 2. Application code at a pinned version.
mkdir -p "$APP_DIR"
if [[ ! -d "$APP_DIR/.git" ]]; then
    log "cloning repository into $APP_DIR"
    git clone "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"
git fetch --tags --prune
git checkout "$VERSION"

# 3. Dedicated service user.
id -u backwatch &>/dev/null || useradd --system --create-home --shell /usr/sbin/nologin backwatch

# 4. Python venv (idempotent; reinstall keeps it in sync with the pinned code).
#    The agent runtime needs only the lean requirements-agent.txt; the API
#    stack (fastapi, uvicorn, ...) is intentionally not installed on app servers.
if [[ ! -d "$APP_DIR/venv" ]]; then
    python3 -m venv "$APP_DIR/venv"
fi
"$APP_DIR/venv/bin/pip" install --upgrade pip
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements-agent.txt"

# 5. Per-application environment. Refuse to run without explicit credentials.
if [[ ! -f "$ENV_FILE" ]]; then
    echo "missing $ENV_FILE — create it from deploy/agent/env.example, set DB_* and API_KEY." >&2
    exit 1
fi

# 6. systemd unit + timer, with a per-application schedule override.
cp "$APP_DIR/deploy/agent/backwatch-agent@.service" /etc/systemd/system/
cp "$APP_DIR/deploy/agent/backwatch-agent@.timer" /etc/systemd/system/
DROP_IN="/etc/systemd/system/backwatch-agent@${APP}.timer.d"
mkdir -p "$DROP_IN"
printf '[Timer]\nOnCalendar=%s\n' "$SCHEDULE" > "$DROP_IN/schedule.conf"
systemctl daemon-reload
systemctl enable --now "backwatch-agent@${APP}.timer"
log "enabled backwatch-agent@${APP}.timer (schedule: $SCHEDULE)"
log "verify with: journalctl -u backwatch-agent@${APP}.service -f"
log "first run manually: sudo -u backwatch $APP_DIR/venv/bin/python -m agent.main run --report"

# 7. Per-application local retention maintenance (PRD section 13).
cp "$APP_DIR/deploy/agent/backwatch-prune@.service" /etc/systemd/system/
cp "$APP_DIR/deploy/agent/backwatch-prune@.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now "backwatch-prune@${APP}.timer"
log "enabled daily prune for ${APP} (retention from RETENTION_DAYS)"