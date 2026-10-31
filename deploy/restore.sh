#!/usr/bin/env bash
# Restore the database from a backup file. Usage: ./deploy/restore.sh backups/students-YYYYMMDD-HHMMSS.db
set -euo pipefail
FILE="${1:?usage: restore.sh <backup-file>}"
cd "$(dirname "$0")/.."
[ -f "$FILE" ] || { echo "File not found: $FILE"; exit 1; }
read -r -p "This REPLACES the live database with $FILE. Type 'yes' to continue: " ok
[ "$ok" = "yes" ] || exit 1

./deploy/backup.sh                       # safety copy of the current data first
docker compose stop app
VOLUME="$(docker volume ls -q | grep -E '(^|_)student_data$' | head -1)"
docker run --rm -v "$VOLUME":/data -v "$(pwd)/$(dirname "$FILE")":/backups:ro alpine:3.20 \
  sh -c "cp /backups/$(basename "$FILE") /data/students.db && rm -f /data/students.db-wal /data/students.db-shm && chown 1000:1000 /data/students.db"
docker compose start app
echo "Restore complete."
