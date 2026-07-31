#!/usr/bin/env bash
#
# Dump the application database to a timestamped file and drop old ones.
#
# The Docker volume survives a container restart and nothing else: not a bad
# migration, not a mistaken DROP, not `docker compose down -v`, not a dead disk.
# This is the copy that does.
#
#   ./scripts/backup.sh                 # writes to ./backups
#   BACKUP_DIR=/srv/backups ./scripts/backup.sh
#
# Restore into an empty database with:
#
#   pg_restore --clean --if-exists -U "$POSTGRES_USER" -d "$POSTGRES_DB" <file>

set -euo pipefail

cd "$(dirname "$0")/.."

BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
CONTAINER="${POSTGRES_CONTAINER:-askit_postgres}"

if [ ! -f .env ]; then
  echo "backup: .env not found; run from the project root" >&2
  exit 1
fi

# shellcheck disable=SC1091
set -a && . ./.env && set +a

: "${POSTGRES_USER:?POSTGRES_USER is not set in .env}"
: "${POSTGRES_DB:?POSTGRES_DB is not set in .env}"

if ! docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null | grep -q true; then
  echo "backup: container '$CONTAINER' is not running" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="$BACKUP_DIR/askit-$stamp.dump"

# Write to a temporary name first: a dump interrupted halfway must not be left
# behind looking like a usable backup.
docker exec "$CONTAINER" pg_dump \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --format=custom \
  --compress=9 \
  > "$target.partial"

mv "$target.partial" "$target"

# Only prune once the new dump is safely in place.
find "$BACKUP_DIR" -name 'askit-*.dump' -type f -mtime "+$RETENTION_DAYS" -delete

echo "backup: $target ($(du -h "$target" | cut -f1))"
