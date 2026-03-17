-- test_invite_redeem_function.sql
-- Integration-style SQL test for redeem_invite_atomic in PostgreSQL.

BEGIN;

-- seed users
INSERT INTO users(id, status) VALUES
  ('00000000-0000-0000-0000-000000000001', 'active'),
  ('00000000-0000-0000-0000-000000000002', 'active');

-- seed invite
INSERT INTO invites(
  id, issuer_user_id, token_hash, ttl_seconds, max_uses, uses_count, expires_at
) VALUES (
  '10000000-0000-0000-0000-000000000001',
  '00000000-0000-0000-0000-000000000001',
  'test_token_hash',
  600,
  1,
  0,
  now() + interval '10 minutes'
);

-- first redeem must succeed
SELECT * FROM redeem_invite_atomic('test_token_hash', '00000000-0000-0000-0000-000000000002');

DO $$
DECLARE
  v_count int;
BEGIN
  SELECT COUNT(*) INTO v_count FROM contacts
  WHERE LEAST(user_a_id, user_b_id) = LEAST('00000000-0000-0000-0000-000000000001'::uuid, '00000000-0000-0000-0000-000000000002'::uuid)
    AND GREATEST(user_a_id, user_b_id) = GREATEST('00000000-0000-0000-0000-000000000001'::uuid, '00000000-0000-0000-0000-000000000002'::uuid);

  IF v_count <> 1 THEN
    RAISE EXCEPTION 'Expected exactly one contact edge, got %', v_count;
  END IF;
END $$;

-- second redeem must fail
DO $$
BEGIN
  PERFORM redeem_invite_atomic('test_token_hash', '00000000-0000-0000-0000-000000000002');
  RAISE EXCEPTION 'Expected INVITE_ALREADY_USED but function succeeded';
EXCEPTION
  WHEN raise_exception THEN
    IF POSITION('INVITE_ALREADY_USED' IN SQLERRM) = 0 THEN
      RAISE;
    END IF;
END $$;

ROLLBACK;
