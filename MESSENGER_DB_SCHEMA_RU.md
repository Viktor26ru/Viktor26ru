# Схема БД (MVP) для invite-only мессенджера

## 1. users
- `id` (pk, uuid)
- `created_at` (timestamptz)
- `status` (active/blocked)

> Публичный username отсутствует намеренно.

## 2. devices
- `id` (pk, uuid)
- `user_id` (fk -> users.id)
- `device_pub_key` (text)
- `identity_pub_key` (text)
- `signed_prekey` (text)
- `signed_prekey_sig` (text)
- `platform` (ios/android)
- `push_token` (text, nullable)
- `created_at`
- `last_seen_at`

Индексы:
- `(user_id)`
- `(last_seen_at)`

## 3. one_time_prekeys
- `id` (pk, uuid)
- `device_id` (fk -> devices.id)
- `prekey` (text)
- `is_used` (bool)
- `created_at`
- `used_at` (nullable)

Индексы:
- `(device_id, is_used)`

## 4. invites
- `id` (pk, uuid)
- `issuer_user_id` (fk -> users.id)
- `token_hash` (text, unique)
- `ttl_seconds` (int)
- `max_uses` (int default 1)
- `uses_count` (int default 0)
- `expires_at` (timestamptz)
- `created_at`
- `revoked_at` (nullable)

Индексы:
- `(issuer_user_id, created_at desc)`
- `(expires_at)`

## 5. contacts
- `id` (pk, uuid)
- `user_a_id` (fk -> users.id)
- `user_b_id` (fk -> users.id)
- `created_via_invite_id` (fk -> invites.id)
- `created_at`

Ограничения:
- unique нормализованной пары `(least(user_a_id, user_b_id), greatest(...))`

## 6. chats
- `id` (pk, uuid)
- `chat_type` (direct/group)
- `created_at`

## 7. chat_members
- `chat_id` (fk -> chats.id)
- `user_id` (fk -> users.id)
- `role` (member/admin)
- `joined_at`
- pk `(chat_id, user_id)`

## 8. messages
- `id` (pk, uuid)
- `chat_id` (fk -> chats.id)
- `sender_user_id` (fk -> users.id)
- `client_msg_id` (text)
- `ciphertext` (bytea/text)
- `msg_type` (text/voice/video/file/system)
- `media_id` (nullable, fk -> media_objects.id)
- `created_at`
- `deleted_at` (nullable)

Индексы:
- `(chat_id, created_at desc)`
- `(sender_user_id, created_at desc)`
- unique `(sender_user_id, client_msg_id)`

## 9. message_receipts
- `message_id` (fk -> messages.id)
- `user_id` (fk -> users.id)
- `status` (delivered/read)
- `updated_at`
- pk `(message_id, user_id)`

## 10. media_objects
- `id` (pk, uuid)
- `owner_user_id` (fk -> users.id)
- `storage_key` (text)
- `kind` (voice/video/file)
- `size_bytes` (bigint)
- `sha256` (text)
- `created_at`

## 11. calls
- `id` (pk, uuid)
- `chat_id` (fk -> chats.id)
- `initiator_user_id` (fk -> users.id)
- `call_type` (voice/video)
- `started_at`
- `ended_at` (nullable)
- `end_reason` (nullable)

## 12. audit_security_events
- `id` (pk, uuid)
- `user_id` (nullable)
- `device_id` (nullable)
- `event_type` (rate_limit/invalid_token/replay_suspected/...)
- `event_meta` (jsonb)
- `created_at`
