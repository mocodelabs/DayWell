#!/usr/bin/env sh
# Back up the DayWell PostgreSQL database (custom format, compressed) with a timestamped filename.
#
#   ./deploy/backup.sh                       # uses docker-compose.prod.yml
#   ENV_FILE=/secure/.env.prod ./deploy/backup.sh   # env file used by the stack (default .env.prod)
#   COMPOSE_PROJECT_NAME=daywell-prod ./deploy/backup.sh
#   KEEP_DAYS=30 ./deploy/backup.sh          # prune older dumps
#
# Redis holds only the task queue and caches — it does not need backing up (reminders live in PostgreSQL).
set -eu
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
ENV_FILE="${ENV_FILE:-.env.prod}"
dc() { docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"; }
OUT_DIR="${BACKUP_DIR:-./backups}"
KEEP_DAYS="${KEEP_DAYS:-14}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$OUT_DIR"
FILE="$OUT_DIR/daywell-$STAMP.dump"

dc exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner' > "$FILE"
# A dump that can't be listed is not a backup.
dc exec -T db pg_restore --list < "$FILE" > /dev/null
echo "Backup written: $FILE ($(wc -c < "$FILE") bytes)"
find "$OUT_DIR" -name 'daywell-*.dump' -mtime +"$KEEP_DAYS" -delete
