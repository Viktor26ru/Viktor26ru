#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "[WARN] docker not found; running docs/schema validation only"
  bash scripts/validate_artifacts.sh
  exit 2
fi

if ! command -v psql >/dev/null 2>&1; then
  echo "[WARN] psql not found; running docs/schema validation only"
  bash scripts/validate_artifacts.sh
  exit 2
fi

echo "[INFO] Starting PostgreSQL via docker compose"
docker compose up -d postgres

export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/messenger_mvp"
bash scripts/wait_for_postgres.sh

bash scripts/validate_artifacts.sh
bash scripts/run_pg_checks.sh

echo "[OK] Full local checks passed"
