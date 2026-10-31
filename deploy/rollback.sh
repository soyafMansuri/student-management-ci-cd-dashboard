#!/usr/bin/env bash
# Manually roll back to the previously deployed image tag (stored in .previous_tag).
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .previous_tag ] || { echo "No previous tag recorded."; exit 1; }
PREV="$(cat .previous_tag)"
echo "Rolling back to $PREV"
AUTO_ROLLBACK=0 exec ./deploy/deploy.sh "$PREV"
