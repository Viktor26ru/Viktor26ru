#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v psql >/dev/null 2>&1; then
  echo "[WARN] psql not found; skipping PostgreSQL checks"
  exit 2
fi

DB_URL="${DATABASE_URL:-postgresql://postgres:postgres@localhost:5432/postgres}"

psql "$DB_URL" -v ON_ERROR_STOP=1 -f db/migrations/0001_init_messenger.sql
psql "$DB_URL" -v ON_ERROR_STOP=1 -f db/migrations/0002_invite_redeem_transaction.sql
psql "$DB_URL" -v ON_ERROR_STOP=1 -f scripts/test_invite_redeem_function.sql

echo "[OK] PostgreSQL migration and function tests passed"
