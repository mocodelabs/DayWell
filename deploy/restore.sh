#!/usr/bin/env sh
# Restore a DayWell backup into the running database. DESTRUCTIVE: existing data is replaced.
#
#   ./deploy/restore.sh backups/daywell-20261009T030000Z.dump
#
# Procedure (see docs/DEPLOYMENT.md §Backup and restore):
#   1. stop the app containers so nothing writes during the restore,
#   2. restore with --clean --if-exists,
#   3. run migrations (in case the dump predates the current code), start the app.
set -eu
FILE="${1:?usage: restore.sh <dump file>}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
ENV_FILE="${ENV_FILE:-.env.prod}"
dc() { docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"; }
[ -f "$FILE" ] || { echo "No such file: $FILE" >&2; exit 1; }

printf 'This will REPLACE the DayWell database with %s. Type RESTORE to continue: ' "$FILE"
read -r answer
[ "$answer" = "RESTORE" ] || { echo "Aborted."; exit 1; }

dc stop backend worker beat web
dc exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner' < "$FILE"
dc run --rm migrate
dc start backend worker beat web
echo "Restore complete. Check /health/ready/ and /health/scheduler/."
