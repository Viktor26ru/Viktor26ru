#!/usr/bin/env bash
set -euo pipefail

DB_URL="${DATABASE_URL:-postgresql://postgres:postgres@localhost:5432/messenger_mvp}"
TIMEOUT_SECONDS="${PG_WAIT_TIMEOUT:-60}"
SLEEP_SECONDS=2
ELAPSED=0

if ! command -v psql >/dev/null 2>&1; then
  echo "[ERROR] psql is required for wait_for_postgres.sh"
  exit 1
fi

until psql "$DB_URL" -c 'SELECT 1' >/dev/null 2>&1; do
  if (( ELAPSED >= TIMEOUT_SECONDS )); then
    echo "[ERROR] PostgreSQL did not become ready within ${TIMEOUT_SECONDS}s"
    exit 1
  fi
  sleep "$SLEEP_SECONDS"
  ELAPSED=$((ELAPSED + SLEEP_SECONDS))
  echo "[INFO] Waiting for PostgreSQL... ${ELAPSED}s"
done

echo "[OK] PostgreSQL is ready"
