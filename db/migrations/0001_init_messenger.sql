-- 0001_init_messenger.sql
-- PostgreSQL schema for invite-only messenger MVP.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  status TEXT NOT NULL CHECK (status IN ('active', 'blocked')) DEFAULT 'active',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE devices (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  device_pub_key TEXT NOT NULL,
  identity_pub_key TEXT NOT NULL,
  signed_prekey TEXT NOT NULL,
  signed_prekey_sig TEXT NOT NULL,
  platform TEXT NOT NULL CHECK (platform IN ('ios', 'android')),
  push_token TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_devices_user_id ON devices(user_id);
CREATE INDEX idx_devices_last_seen_at ON devices(last_seen_at);

CREATE TABLE one_time_prekeys (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  device_id UUID NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
  prekey TEXT NOT NULL,
  is_used BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  used_at TIMESTAMPTZ
);
CREATE INDEX idx_prekeys_device_used ON one_time_prekeys(device_id, is_used);

CREATE TABLE invites (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  issuer_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL UNIQUE,
  ttl_seconds INT NOT NULL CHECK (ttl_seconds > 0),
  max_uses INT NOT NULL DEFAULT 1 CHECK (max_uses = 1),
  uses_count INT NOT NULL DEFAULT 0,
  expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  revoked_at TIMESTAMPTZ
);
CREATE INDEX idx_invites_issuer_created ON invites(issuer_user_id, created_at DESC);
CREATE INDEX idx_invites_expires_at ON invites(expires_at);

CREATE TABLE contacts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_a_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  user_b_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_via_invite_id UUID NOT NULL REFERENCES invites(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (user_a_id <> user_b_id)
);
CREATE UNIQUE INDEX uq_contacts_pair
  ON contacts (LEAST(user_a_id, user_b_id), GREATEST(user_a_id, user_b_id));

CREATE TABLE chats (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  chat_type TEXT NOT NULL CHECK (chat_type IN ('direct', 'group')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE chat_members (
  chat_id UUID NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('member', 'admin')) DEFAULT 'member',
  joined_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (chat_id, user_id)
);

CREATE TABLE media_objects (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  storage_key TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('voice', 'video', 'file')),
  size_bytes BIGINT NOT NULL CHECK (size_bytes > 0),
  sha256 TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  chat_id UUID NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
  sender_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  client_msg_id TEXT NOT NULL,
  ciphertext TEXT NOT NULL,
  msg_type TEXT NOT NULL CHECK (msg_type IN ('text', 'voice', 'video', 'file', 'system')),
  media_id UUID REFERENCES media_objects(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at TIMESTAMPTZ
);
CREATE INDEX idx_messages_chat_created ON messages(chat_id, created_at DESC);
CREATE INDEX idx_messages_sender_created ON messages(sender_user_id, created_at DESC);
CREATE UNIQUE INDEX uq_messages_sender_client_id ON messages(sender_user_id, client_msg_id);

CREATE TABLE message_receipts (
  message_id UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  status TEXT NOT NULL CHECK (status IN ('delivered', 'read')),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (message_id, user_id)
);

CREATE TABLE calls (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  chat_id UUID NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
  initiator_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  call_type TEXT NOT NULL CHECK (call_type IN ('voice', 'video')),
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  ended_at TIMESTAMPTZ,
  end_reason TEXT
);

CREATE TABLE audit_security_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES users(id) ON DELETE SET NULL,
  device_id UUID REFERENCES devices(id) ON DELETE SET NULL,
  event_type TEXT NOT NULL,
  event_meta JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_security_events_created ON audit_security_events(created_at DESC);

-- Recommended transaction pattern for invite redeem:
-- BEGIN;
--   SELECT * FROM invites WHERE token_hash = $1 FOR UPDATE;
--   -- validate expires_at/revoked_at/uses_count
--   -- update uses_count = uses_count + 1
--   -- insert contacts edge
-- COMMIT;
