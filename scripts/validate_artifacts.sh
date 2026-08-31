#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

required_files=(
  "MESSENGER_PRODUCT_PLAN_RU.md"
  "MESSENGER_API_SPEC_RU.md"
  "MESSENGER_DB_SCHEMA_RU.md"
  "INVITE_PROTOCOL_RU.md"
  "SPRINT1_BACKLOG_RU.md"
  "IMPLEMENTATION_RUNBOOK_RU.md"
  "SECURITY_NETWORK_AUDIT_RU.md"
  "openapi/messenger_mvp_openapi_ru.yaml"
  "db/migrations/0001_init_messenger.sql"
  "db/migrations/0002_invite_redeem_transaction.sql"
)

for file in "${required_files[@]}"; do
  if [[ ! -f "$file" ]]; then
    echo "[ERROR] Missing required file: $file"
    exit 1
  fi
done

echo "[OK] All required files exist"

# OpenAPI sanity checks
if ! rg -q '^openapi:\s*3\.0\.3' openapi/messenger_mvp_openapi_ru.yaml; then
  echo "[ERROR] OpenAPI version is not 3.0.3"
  exit 1
fi

for path in '/auth/bootstrap' '/invites' '/invites/redeem' '/contacts' '/chats' '/media/upload-url' '/calls/start'; do
  if ! rg -q "^\s{2}${path}:" openapi/messenger_mvp_openapi_ru.yaml; then
    echo "[ERROR] Missing OpenAPI path: ${path}"
    exit 1
  fi
done

echo "[OK] OpenAPI basic checks passed"

# SQL migration checks
if [[ "$(rg -c '^CREATE TABLE ' db/migrations/0001_init_messenger.sql)" -lt 12 ]]; then
  echo "[ERROR] Expected at least 12 CREATE TABLE statements in 0001 migration"
  exit 1
fi

for token in 'CREATE TABLE invites' 'CREATE TABLE contacts' 'CREATE UNIQUE INDEX uq_contacts_pair'; do
  if ! rg -q "$token" db/migrations/0001_init_messenger.sql; then
    echo "[ERROR] 0001 migration missing: $token"
    exit 1
  fi
done

for token in 'CREATE OR REPLACE FUNCTION redeem_invite_atomic' 'FOR UPDATE' 'INVITE_ALREADY_USED' 'ON CONFLICT'; do
  if ! rg -q "$token" db/migrations/0002_invite_redeem_transaction.sql; then
    echo "[ERROR] 0002 migration missing: $token"
    exit 1
  fi
done

echo "[OK] SQL migration checks passed"

# Cross-doc consistency checks
if ! rg -q 'redeem_invite_atomic' IMPLEMENTATION_RUNBOOK_RU.md; then
  echo "[ERROR] Runbook does not reference redeem_invite_atomic"
  exit 1
fi

if ! rg -q 'db/migrations/0002_invite_redeem_transaction.sql' MESSENGER_PRODUCT_PLAN_RU.md; then
  echo "[ERROR] Product plan does not reference 0002 migration"
  exit 1
fi

echo "[OK] Cross-document consistency checks passed"

if ! rg -q '127\.0\.0\.1:5432:5432' docker-compose.yml; then
  echo "[ERROR] Postgres must be published on 127.0.0.1 only"
  exit 1
fi

if rg -q -- '- "5432:5432"' docker-compose.yml; then
  echo "[ERROR] Postgres must not bind 5432 on all interfaces"
  exit 1
fi

if ! rg -q 'SECURITY_NETWORK_AUDIT_RU.md' IMPLEMENTATION_RUNBOOK_RU.md; then
  echo "[ERROR] Runbook does not reference SECURITY_NETWORK_AUDIT_RU.md"
  exit 1
fi

echo "[OK] Local network hardening checks passed"

echo "Validation completed successfully"
