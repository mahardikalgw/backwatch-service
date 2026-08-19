#!/usr/bin/env bash
# Deploy/update the backwatch backup agent on one application server.
#
# Idempotent. The agent wheel + systemd templates are downloaded from a GitHub
# Release (built by .github/workflows/release.yml), NOT from a git checkout.
#
# Usage (run as root):
#   ./deploy/agent/install.sh <app> [--schedule "*-*-* 01:00:00"]
#
# Environment (optional):
#   BACKWATCH_VERSION   release tag to install (default v0.1.0)
#   BACKWATCH_REPO      "owner/repo" hosting the release (default mahardikalgw/backwatch-service)
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
REPO="${BACKWATCH_REPO:-mahardikalgw/backwatch-service}"
VERSION="${BACKWATCH_VERSION:-v0.1.0}"
ENV_FILE="/etc/backwatch/${APP}.env"
WORK="/tmp/backwatch-artifacts"

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

# 2. Download the agent wheel + deploy templates from the GitHub Release.
rm -rf "$WORK"
mkdir -p "$WORK"
RELEASE_BASE="https://github.com/${REPO}/releases/download/${VERSION}"
log "downloading artifacts from ${RELEASE_BASE}"
curl -fsSL -o "$WORK/backwatch_agent-${VERSION#v}-py3-none-any.whl" \
    "${RELEASE_BASE}/backwatch_agent-${VERSION#v}-py3-none-any.whl"
curl -fsSL -o "$WORK/backwatch-agent-deploy.tar.gz" \
    "${RELEASE_BASE}/backwatch-agent-deploy.tar.gz"
tar -xzf "$WORK/backwatch-agent-deploy.tar.gz" -C "$WORK"

# 3. Dedicated service user.
id -u backwatch &>/dev/null || useradd --system --create-home --shell /usr/sbin/nologin backwatch

# 4. Python venv + install the agent wheel (reinstall keeps it current).
if [[ ! -d "$APP_DIR/venv" ]]; then
    python3 -m venv "$APP_DIR/venv"
fi
"$APP_DIR/venv/bin/pip" install --upgrade pip
"$APP_DIR/venv/bin/pip" install "$WORK"/backwatch_agent-*.whl

# 5. Per-application environment. Refuse to run without explicit credentials.
if [[ ! -f "$ENV_FILE" ]]; then
    echo "missing $ENV_FILE - create it from deploy/agent/env.example (or the release's env.example), set DB_* and API_KEY." >&2
    exit 1
fi

# 6. systemd unit + timer, with a per-application schedule override.
cp "$WORK/backwatch-agent@.service" /etc/systemd/system/
cp "$WORK/backwatch-agent@.timer" /etc/systemd/system/
DROP_IN="/etc/systemd/system/backwatch-agent@${APP}.timer.d"
mkdir -p "$DROP_IN"
printf '[Timer]\nOnCalendar=%s\n' "$SCHEDULE" > "$DROP_IN/schedule.conf"
systemctl daemon-reload
systemctl enable --now "backwatch-agent@${APP}.timer"
log "enabled backwatch-agent@${APP}.timer (schedule: $SCHEDULE)"
log "verify with: journalctl -u backwatch-agent@${APP}.service -f"
log "first run manually: sudo -u backwatch $APP_DIR/venv/bin/python -m agent.main run --report"

# 7. Per-application local retention maintenance (PRD section 13).
cp "$WORK/backwatch-prune@.service" /etc/systemd/system/
cp "$WORK/backwatch-prune@.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now "backwatch-prune@${APP}.timer"
log "enabled daily prune for ${APP} (retention from RETENTION_DAYS)"