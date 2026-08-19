#!/usr/bin/env bash
# backwatch container self-healing watchdog.
#
# Restarts backwatch Podman containers that are exited or marked unhealthy by
# their healthcheck. Designed to run every minute from a systemd timer:
#   deploy/api/backwatch-autoheal.timer
#
# Compose already restarts crashed services via `restart: unless-stopped`; this
# script covers the "running but unhealthy" case that restart policies miss.

set -u

PROJECT="${BACKWATCH_COMPOSE_PROJECT:-backwatch}"
LOGGER="logger -t backwatch-autoheal"

containers="$(podman ps -a --filter "label=com.docker.compose.project=$PROJECT" --format '{{.Names}}')"
if [[ -z "$containers" ]]; then
    echo "no backwatch containers found (project=$PROJECT)" | $LOGGER
    exit 0
fi

for container in $containers; do
    status="$(podman inspect -f '{{.State.Status}}' "$container")"
    health="$(podman inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container")"

    if [[ "$status" == "exited" || "$health" == "unhealthy" ]]; then
        echo "restarting $container (status=$status health=$health)" | $LOGGER
        podman restart "$container" || echo "restart failed for $container" | $LOGGER
        continue
    fi
    if [[ "$status" == "restarting" ]]; then
        echo "warning: $container keeps restarting; inspect with 'podman logs $container'" | $LOGGER
    fi
done

exit 0