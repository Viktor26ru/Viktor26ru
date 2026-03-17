-- 0002_invite_redeem_transaction.sql
-- Atomic redeem helper to prevent double-use of invite token.

CREATE OR REPLACE FUNCTION redeem_invite_atomic(
  p_token_hash TEXT,
  p_recipient_user_id UUID
)
RETURNS TABLE(contact_id UUID, issuer_user_id UUID)
LANGUAGE plpgsql
AS $$
DECLARE
  v_invite RECORD;
  v_contact_id UUID;
BEGIN
  SELECT *
  INTO v_invite
  FROM invites
  WHERE token_hash = p_token_hash
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'INVITE_NOT_FOUND' USING ERRCODE = 'P0001';
  END IF;

  IF v_invite.revoked_at IS NOT NULL THEN
    RAISE EXCEPTION 'INVITE_REVOKED' USING ERRCODE = 'P0001';
  END IF;

  IF v_invite.expires_at <= now() THEN
    RAISE EXCEPTION 'INVITE_EXPIRED' USING ERRCODE = 'P0001';
  END IF;

  IF v_invite.uses_count >= v_invite.max_uses THEN
    RAISE EXCEPTION 'INVITE_ALREADY_USED' USING ERRCODE = 'P0001';
  END IF;

  IF v_invite.issuer_user_id = p_recipient_user_id THEN
    RAISE EXCEPTION 'SELF_REDEEM_FORBIDDEN' USING ERRCODE = 'P0001';
  END IF;

  UPDATE invites
  SET uses_count = uses_count + 1
  WHERE id = v_invite.id;

  INSERT INTO contacts(user_a_id, user_b_id, created_via_invite_id)
  VALUES (v_invite.issuer_user_id, p_recipient_user_id, v_invite.id)
  ON CONFLICT ((LEAST(user_a_id, user_b_id)), (GREATEST(user_a_id, user_b_id))) DO NOTHING
  RETURNING id INTO v_contact_id;

  IF v_contact_id IS NULL THEN
    SELECT id INTO v_contact_id
    FROM contacts
    WHERE LEAST(user_a_id, user_b_id) = LEAST(v_invite.issuer_user_id, p_recipient_user_id)
      AND GREATEST(user_a_id, user_b_id) = GREATEST(v_invite.issuer_user_id, p_recipient_user_id);
  END IF;

  RETURN QUERY SELECT v_contact_id, v_invite.issuer_user_id;
END;
$$;
