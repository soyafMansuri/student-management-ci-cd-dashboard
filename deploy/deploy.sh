#!/usr/bin/env bash
# Deploy one image tag on the server, verify it, and roll back automatically if it is unhealthy.
# Usage: IMAGE_REPO=user/student-management-system ./deploy/deploy.sh <image-tag>
# Set AUTO_ROLLBACK=0 to disable the automatic rollback (used by rollback.sh).
set -euo pipefail

NEW_TAG="${1:?usage: deploy.sh <image-tag>}"
cd "$(dirname "$0")/.."
[ -f .env ] || { echo "ERROR: .env not found in $(pwd). Create it from .env.example first."; exit 1; }

log() { echo "[$(date -u +%H:%M:%S)] $*"; }
get_env() { grep -E "^$1=" .env | head -1 | cut -d= -f2- || true; }
set_env() {
  if grep -qE "^$1=" .env; then sed -i "s|^$1=.*|$1=$2|" .env; else echo "$1=$2" >> .env; fi
}
wait_healthy() {
  for _ in $(seq 1 30); do
    status=$(docker inspect --format '{{.State.Health.Status}}' student-app 2>/dev/null || echo none)
    [ "$status" = "healthy" ] && return 0
    sleep 4
  done
  return 1
}

[ -n "${IMAGE_REPO:-}" ] && set_env IMAGE_REPO "$IMAGE_REPO"
CURRENT_TAG="$(get_env IMAGE_TAG)"

log "Pulling image tag $NEW_TAG"
IMAGE_TAG="$NEW_TAG" docker compose pull app

set_env IMAGE_TAG "$NEW_TAG"
log "Starting containers"
docker compose up -d --remove-orphans

if wait_healthy; then
  [ -n "$CURRENT_TAG" ] && [ "$CURRENT_TAG" != "$NEW_TAG" ] && echo "$CURRENT_TAG" > .previous_tag
  echo "$(date -u +%FT%TZ) $NEW_TAG SUCCESS" >> deployments.log
  docker image prune -f >/dev/null
  log "Deployment of $NEW_TAG succeeded"
  exit 0
fi

echo "$(date -u +%FT%TZ) $NEW_TAG FAILED" >> deployments.log
log "Container did not become healthy. Last logs:"
docker compose logs --tail 50 app || true

if [ "${AUTO_ROLLBACK:-1}" = "1" ] && [ -n "$CURRENT_TAG" ] && [ "$CURRENT_TAG" != "local" ] && [ "$CURRENT_TAG" != "$NEW_TAG" ]; then
  log "Rolling back to previous tag $CURRENT_TAG"
  set_env IMAGE_TAG "$CURRENT_TAG"
  docker compose up -d --remove-orphans
  wait_healthy && log "Rollback to $CURRENT_TAG succeeded" || log "WARNING: rollback is also unhealthy, check logs"
else
  log "No previous version to roll back to"
fi
exit 1
