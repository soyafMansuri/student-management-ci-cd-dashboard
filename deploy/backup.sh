#!/usr/bin/env bash
# Consistent online backup of the SQLite database (uses SQLite's backup API, safe while the app is running).
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backups
FILE="backups/students-$(date +%Y%m%d-%H%M%S).db"
docker compose exec -T app python - <<'PY'
import os, sqlite3
src = sqlite3.connect(os.environ["DATABASE_PATH"])
dst = sqlite3.connect("/tmp/backup.db")
src.backup(dst)
dst.close(); src.close()
PY
docker compose cp app:/tmp/backup.db "$FILE"
docker compose exec -T app rm -f /tmp/backup.db
chmod 600 "$FILE"
echo "Backup saved to $FILE"
