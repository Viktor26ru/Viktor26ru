# Sprint 1 backlog (Jira-ready) — 2 недели

## Цель спринта
Доставить рабочий vertical slice: bootstrap аккаунта, инвайт, добавление контакта, отправка E2E текстового сообщения 1:1.

## Эпики

### EPIC-1: Identity & Device Bootstrap
- MSG-101: API `POST /auth/bootstrap` (backend)
- MSG-102: Генерация identity/device key pair в клиенте
- MSG-103: Хранение ключей в Keychain/Keystore
- MSG-104: Refresh token flow

**DoD:** новый пользователь получает токены и может переподключаться без потери сессии.

### EPIC-2: Invite-only Contact Graph
- MSG-201: API `POST /invites` с TTL/single-use
- MSG-202: API `POST /invites/redeem` + транзакционная защита от гонок
- MSG-203: Таблицы `invites`, `contacts`, индексы и ограничения уникальности
- MSG-204: Экран «Пригласить» (QR/ссылка)

**DoD:** контакт появляется только после успешного redeem.

### EPIC-3: Direct Chat MVP
- MSG-301: API `POST /chats/direct` и `GET /chats`
- MSG-302: API `POST /chats/{id}/messages`
- MSG-303: WebSocket `message.new`
- MSG-304: UI списка чатов и экрана диалога

**DoD:** 2 устройства обмениваются текстом в near real-time.

### EPIC-4: E2E Crypto Foundation
- MSG-401: Пакет prekeys (`POST /devices/prekeys`)
- MSG-402: Инициализация X3DH-сессии при первом сообщении
- MSG-403: Шифрование/дешифрование payload на клиенте
- MSG-404: Интеграционные тесты на совместимость ключей

**DoD:** сервер не может прочитать содержимое сообщений.

### EPIC-5: Reliability & Observability
- MSG-501: Базовые метрики API/WS (latency, error rate)
- MSG-502: Rate limiting на invites/redeem
- MSG-503: Аудит-ивенты безопасности
- MSG-504: Crash reporting клиента

**DoD:** есть дешборд health + алерты на 5xx и всплеск 429.

## Технические задачи качества

- MSG-601: CI pipeline (lint + unit + integration)
- MSG-602: Contract tests для API (OpenAPI schema validation)
- MSG-603: Threat model v1 (STRIDE на invite flow)

## Риски и митигаторы

1. **Риск:** сложность E2E на старте.  
   **Митигатор:** ограничить Sprint 1 только direct-chat и минимальным набором crypto-функций.
2. **Риск:** abuse redeem endpoint.  
   **Митигатор:** strict rate limits + временная блокировка + telemetry.
3. **Риск:** нестабильность push на iOS.  
   **Митигатор:** fallback на websocket при активном приложении.

## KPI спринта

- p95 отправки текстового сообщения < 500ms (online-online).
- Invite redeem success rate > 95% в тестовой среде.
- Crash-free sessions > 99%.
