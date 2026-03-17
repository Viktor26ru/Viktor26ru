# Спецификация API (MVP) для invite-only мессенджера

## 1. Принципы API

- Базовый URL: `/v1`.
- Транспорт: HTTPS + WebSocket.
- Формат: JSON для control-plane, бинарный upload для медиа.
- Аутентификация: access token устройства (короткоживущий) + refresh token (длинный).
- В API отсутствуют любые endpoint'ы глобального поиска пользователей.

## 2. Онбординг и устройства

### POST `/auth/bootstrap`
Создать анонимный аккаунт и зарегистрировать первое устройство.

Request:
```json
{
  "device_pub_key": "base64",
  "identity_pub_key": "base64",
  "signed_prekey": "base64",
  "signed_prekey_sig": "base64",
  "one_time_prekeys": ["base64", "base64"]
}
```

Response:
```json
{
  "user_id": "usr_...",
  "device_id": "dev_...",
  "access_token": "...",
  "refresh_token": "..."
}
```

### POST `/auth/refresh`
Обновление access token.

### POST `/devices/prekeys`
Пополнить пакет one-time prekeys.

## 3. Инвайты и граф контактов

### POST `/invites`
Создать одноразовый invite-token.

Request:
```json
{
  "ttl_seconds": 600,
  "max_uses": 1,
  "label": "личный инвайт"
}
```

Response:
```json
{
  "invite_id": "inv_...",
  "invite_token": "opaque_token",
  "expires_at": "2026-03-06T11:22:33Z"
}
```

### POST `/invites/redeem`
Активировать инвайт и установить связь контактов.

Request:
```json
{
  "invite_token": "opaque_token",
  "recipient_identity_pub_key": "base64"
}
```

Response:
```json
{
  "contact_id": "cnt_...",
  "peer_user_ref": "opaque_peer_ref",
  "session_init": {
    "peer_identity_key": "base64",
    "peer_signed_prekey": "base64",
    "peer_one_time_prekey": "base64"
  }
}
```

### GET `/contacts`
Получить список только уже связанных контактов.

## 4. Чаты и сообщения

### POST `/chats/direct`
Создать или получить direct-чат с контактом.

### GET `/chats`
Список чатов пользователя.

### GET `/chats/{chat_id}/messages?cursor=...`
Пагинированная история.

### POST `/chats/{chat_id}/messages`
Отправка E2E ciphertext payload.

Request:
```json
{
  "client_msg_id": "uuid",
  "ciphertext": "base64",
  "msg_type": "text|voice|video|file|system",
  "media_ref": "optional"
}
```

### POST `/messages/{message_id}/ack`
Подтверждение доставки/прочтения.

## 5. Медиа и файлы

### POST `/media/upload-url`
Получить одноразовый URL загрузки.

Request:
```json
{
  "kind": "voice|video|file",
  "size": 123456,
  "sha256": "hex"
}
```

Response:
```json
{
  "media_id": "med_...",
  "upload_url": "https://...",
  "headers": {
    "x-amz-acl": "private"
  }
}
```

### GET `/media/{media_id}/download-url`
Получить короткоживущий URL скачивания зашифрованного blob.

## 6. Звонки (signal-plane)

### POST `/calls/start`
Инициировать голосовой/видеозвонок.

### POST `/calls/{call_id}/signal`
Передача SDP/ICE сигнальных данных.

### POST `/calls/{call_id}/end`
Завершение звонка.

## 7. Realtime gateway (WebSocket)

Endpoint: `wss://api.example.com/v1/ws`

События сервера:
- `message.new`
- `message.status`
- `invite.redeemed`
- `call.incoming`
- `call.signal`
- `presence.typing` (опционально)

События клиента:
- `ack`
- `typing.start` / `typing.stop`
- `call.signal`

## 8. Ошибки и анти-abuse

Коды ошибок:
- `401 UNAUTHORIZED`
- `403 FORBIDDEN`
- `404 NOT_FOUND`
- `409 CONFLICT` (инвайт уже использован)
- `410 GONE` (инвайт истёк)
- `429 RATE_LIMITED`

Anti-abuse:
- device-based rate limiting,
- per-IP burst control,
- checksum/nonce защита от replay,
- обязательный TTL и single-use для инвайтов.
