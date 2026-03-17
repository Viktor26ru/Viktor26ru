import secrets
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ts(dt: datetime) -> str:
    return dt.isoformat()


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


@dataclass
class Invite:
    invite_id: str
    issuer_user_id: str
    token: str
    expires_at: str
    uses_count: int
    max_uses: int


class MessengerService:
    """Minimal working invite-only messenger backend prototype (sqlite)."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
              id TEXT PRIMARY KEY,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS invites (
              id TEXT PRIMARY KEY,
              issuer_user_id TEXT NOT NULL,
              token TEXT NOT NULL UNIQUE,
              expires_at TEXT NOT NULL,
              max_uses INTEGER NOT NULL,
              uses_count INTEGER NOT NULL DEFAULT 0,
              revoked_at TEXT,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS contacts (
              id TEXT PRIMARY KEY,
              user_a_id TEXT NOT NULL,
              user_b_id TEXT NOT NULL,
              created_via_invite_id TEXT NOT NULL,
              created_at TEXT NOT NULL,
              normalized_pair TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS chats (
              id TEXT PRIMARY KEY,
              chat_type TEXT NOT NULL,
              created_at TEXT NOT NULL,
              normalized_pair TEXT UNIQUE
            );

            CREATE TABLE IF NOT EXISTS messages (
              id TEXT PRIMARY KEY,
              chat_id TEXT NOT NULL,
              sender_user_id TEXT NOT NULL,
              ciphertext TEXT NOT NULL,
              msg_type TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            """
        )
        self.conn.commit()

    @contextmanager
    def tx(self):
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            yield
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def bootstrap_user(self) -> str:
        user_id = f"usr_{secrets.token_hex(8)}"
        self.conn.execute(
            "INSERT INTO users(id, created_at) VALUES(?, ?)",
            (user_id, ts(utc_now())),
        )
        self.conn.commit()
        return user_id

    def create_invite(self, issuer_user_id: str, ttl_seconds: int = 600, max_uses: int = 1) -> Invite:
        invite_id = f"inv_{secrets.token_hex(8)}"
        token = f"inv1.{secrets.token_urlsafe(24)}"
        expires_at = ts(utc_now() + timedelta(seconds=ttl_seconds))
        self.conn.execute(
            """
            INSERT INTO invites(id, issuer_user_id, token, expires_at, max_uses, uses_count, created_at)
            VALUES (?, ?, ?, ?, ?, 0, ?)
            """,
            (invite_id, issuer_user_id, token, expires_at, max_uses, ts(utc_now())),
        )
        self.conn.commit()
        return Invite(invite_id, issuer_user_id, token, expires_at, 0, max_uses)

    def redeem_invite(self, token: str, recipient_user_id: str) -> str:
        with self.tx():
            row = self.conn.execute("SELECT * FROM invites WHERE token = ?", (token,)).fetchone()
            if not row:
                raise ValueError("INVITE_NOT_FOUND")
            if row["revoked_at"] is not None:
                raise ValueError("INVITE_REVOKED")
            if parse_ts(row["expires_at"]) <= utc_now():
                raise ValueError("INVITE_EXPIRED")
            if row["uses_count"] >= row["max_uses"]:
                raise ValueError("INVITE_ALREADY_USED")
            if row["issuer_user_id"] == recipient_user_id:
                raise ValueError("SELF_REDEEM_FORBIDDEN")

            self.conn.execute("UPDATE invites SET uses_count = uses_count + 1 WHERE id = ?", (row["id"],))

            a, b = sorted([row["issuer_user_id"], recipient_user_id])
            pair = f"{a}:{b}"
            existing = self.conn.execute(
                "SELECT id FROM contacts WHERE normalized_pair = ?", (pair,)
            ).fetchone()
            if existing:
                return existing["id"]

            contact_id = f"cnt_{secrets.token_hex(8)}"
            self.conn.execute(
                """
                INSERT INTO contacts(id, user_a_id, user_b_id, created_via_invite_id, created_at, normalized_pair)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (contact_id, row["issuer_user_id"], recipient_user_id, row["id"], ts(utc_now()), pair),
            )
            return contact_id

    def list_contacts(self, user_id: str) -> list[str]:
        rows = self.conn.execute(
            """
            SELECT user_a_id, user_b_id FROM contacts
            WHERE user_a_id = ? OR user_b_id = ?
            """,
            (user_id, user_id),
        ).fetchall()
        result = []
        for r in rows:
            peer = r["user_b_id"] if r["user_a_id"] == user_id else r["user_a_id"]
            result.append(peer)
        return result

    def create_or_get_direct_chat(self, user_a: str, user_b: str) -> str:
        a, b = sorted([user_a, user_b])
        pair = f"{a}:{b}"
        row = self.conn.execute("SELECT id FROM chats WHERE normalized_pair = ?", (pair,)).fetchone()
        if row:
            return row["id"]
        chat_id = f"chat_{secrets.token_hex(8)}"
        self.conn.execute(
            "INSERT INTO chats(id, chat_type, created_at, normalized_pair) VALUES(?, 'direct', ?, ?)",
            (chat_id, ts(utc_now()), pair),
        )
        self.conn.commit()
        return chat_id

    def send_message(self, chat_id: str, sender_user_id: str, ciphertext: str, msg_type: str = "text") -> str:
        msg_id = f"msg_{secrets.token_hex(8)}"
        self.conn.execute(
            "INSERT INTO messages(id, chat_id, sender_user_id, ciphertext, msg_type, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (msg_id, chat_id, sender_user_id, ciphertext, msg_type, ts(utc_now())),
        )
        self.conn.commit()
        return msg_id
