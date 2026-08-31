# Invite-only Messenger MVP (RU)

Репозиторий содержит спецификацию и стартовые инженерные артефакты для приватного мессенджера (iOS/Android), в котором контакт можно добавить только по приглашению.

## Что внутри

- Продукт и roadmap: `MESSENGER_PRODUCT_PLAN_RU.md`
- API спецификация: `MESSENGER_API_SPEC_RU.md`
- OpenAPI контракт: `openapi/messenger_mvp_openapi_ru.yaml`
- Схема БД: `MESSENGER_DB_SCHEMA_RU.md`
- SQL миграции: `db/migrations/0001_init_messenger.sql`, `db/migrations/0002_invite_redeem_transaction.sql`
- Протокол инвайтов: `INVITE_PROTOCOL_RU.md`
- Backlog Sprint 1: `SPRINT1_BACKLOG_RU.md`
- Runbook внедрения: `IMPLEMENTATION_RUNBOOK_RU.md`

## Локальные проверки

```bash
bash scripts/validate_artifacts.sh
```

Проверки PostgreSQL (если установлен `psql` и доступна БД):

```bash
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres bash scripts/run_pg_checks.sh
```

## Примечание

В MVP принципиально нет глобального поиска пользователей по логину/телефону/нику — только invite-only модель.

Локальный PostgreSQL в `docker-compose.yml` слушает только `127.0.0.1:5432`. Пароль задавайте через `.env` (см. `.env.example`), не публикуйте 5432 в сеть.

Защитный аудит среды и спецификации: `SECURITY_NETWORK_AUDIT_RU.md`.


## Быстрый старт проверок (одной командой)

```bash
bash scripts/full_local_check.sh
```

Что делает команда:
- поднимает PostgreSQL через `docker compose`,
- ждёт готовность БД,
- запускает `validate_artifacts.sh`,
- запускает SQL-проверки миграций и `redeem_invite_atomic`.

## Make targets

```bash
make validate
make pg-up
make pg-checks
make ci-local
make pg-down
```


## Рабочий прототип backend-логики (sqlite)

Минимальный исполняемый prototype invite-only логики расположен в `prototype_backend/messenger_service.py`.

Запуск демо-сценария:

```bash
make demo-flow
```

Запуск unit-тестов прототипа:

```bash
make prototype-test
```
