from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    project TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snapshots_proj_ts ON snapshots(project, ts);

CREATE TABLE IF NOT EXISTS incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    project TEXT NOT NULL,
    target TEXT NOT NULL,
    severity TEXT NOT NULL,
    summary TEXT NOT NULL,
    resolved_ts INTEGER,
    heal_result TEXT
);

CREATE TABLE IF NOT EXISTS commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    source TEXT NOT NULL,
    actor TEXT NOT NULL,
    text TEXT NOT NULL,
    result TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS admins (
    tg_user_id INTEGER PRIMARY KEY,
    username TEXT,
    bound_ts INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS llm_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    project TEXT NOT NULL,
    model TEXT,
    tokens_in INTEGER,
    tokens_out INTEGER,
    note TEXT
);
"""


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def put_snapshot(self, project: str, payload: dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO snapshots(ts, project, payload) VALUES (?, ?, ?)",
                (int(time.time()), project, json.dumps(payload, ensure_ascii=False)),
            )
            self._conn.execute(
                "DELETE FROM snapshots WHERE id NOT IN (SELECT id FROM snapshots ORDER BY id DESC LIMIT 4000)"
            )
            self._conn.commit()

    def latest_snapshots(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        with self._lock:
            rows = self._conn.execute(
                "SELECT project, MAX(ts) AS ts FROM snapshots GROUP BY project"
            ).fetchall()
            for row in rows:
                snap = self._conn.execute(
                    "SELECT ts, payload FROM snapshots WHERE project=? ORDER BY ts DESC LIMIT 1",
                    (row["project"],),
                ).fetchone()
                if snap:
                    data = json.loads(snap["payload"])
                    data["_ts"] = snap["ts"]
                    out[row["project"]] = data
        return out

    def history(self, project: str, limit: int = 72) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT ts, payload FROM snapshots WHERE project=? ORDER BY ts DESC LIMIT ?",
                (project, limit),
            ).fetchall()
        items = []
        for row in rows:
            data = json.loads(row["payload"])
            data["_ts"] = row["ts"]
            items.append(data)
        return list(reversed(items))

    def open_incident(self, project: str, target: str, severity: str, summary: str) -> int:
        with self._lock:
            cur = self._conn.execute(
                "SELECT id FROM incidents WHERE project=? AND target=? AND resolved_ts IS NULL",
                (project, target),
            ).fetchone()
            if cur:
                return int(cur["id"])
            cur = self._conn.execute(
                "INSERT INTO incidents(ts, project, target, severity, summary) VALUES (?,?,?,?,?)",
                (int(time.time()), project, target, severity, summary),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def resolve_incident(self, incident_id: int, heal_result: str = "") -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE incidents SET resolved_ts=?, heal_result=? WHERE id=?",
                (int(time.time()), heal_result, incident_id),
            )
            self._conn.commit()

    def resolve_by_target(self, project: str, target: str, heal_result: str = "") -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE incidents SET resolved_ts=?, heal_result=? WHERE project=? AND target=? AND resolved_ts IS NULL",
                (int(time.time()), heal_result, project, target),
            )
            self._conn.commit()

    def open_incidents(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM incidents WHERE resolved_ts IS NULL ORDER BY ts DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def recent_incidents(self, limit: int = 30) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM incidents ORDER BY ts DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def log_command(self, source: str, actor: str, text: str, result: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO commands(ts, source, actor, text, result) VALUES (?,?,?,?,?)",
                (int(time.time()), source, actor, text, result[:4000]),
            )
            self._conn.commit()

    def recent_commands(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM commands ORDER BY ts DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def add_admin(self, tg_user_id: int, username: str = "") -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO admins(tg_user_id, username, bound_ts) VALUES (?,?,?)",
                (int(tg_user_id), username, int(time.time())),
            )
            self._conn.commit()

    def is_admin(self, tg_user_id: int) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM admins WHERE tg_user_id=?", (int(tg_user_id),)
            ).fetchone()
        return bool(row)

    def admins(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM admins").fetchall()
        return [dict(r) for r in rows]

    def kv_get(self, key: str, default: str = "") -> str:
        with self._lock:
            row = self._conn.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def kv_set(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO kv(key, value) VALUES (?, ?)", (key, value)
            )
            self._conn.commit()

    def add_llm(self, project: str, model: str, tokens_in: int, tokens_out: int, note: str = "") -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO llm_events(ts, project, model, tokens_in, tokens_out, note) VALUES (?,?,?,?,?,?)",
                (int(time.time()), project, model, tokens_in, tokens_out, note),
            )
            self._conn.commit()

    def llm_totals(self, since_ts: int | None = None) -> list[dict[str, Any]]:
        since_ts = since_ts or int(time.time()) - 86400
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT project, model,
                       COALESCE(SUM(tokens_in),0) AS tokens_in,
                       COALESCE(SUM(tokens_out),0) AS tokens_out,
                       COUNT(*) AS calls
                FROM llm_events WHERE ts>=?
                GROUP BY project, model
                """,
                (since_ts,),
            ).fetchall()
        return [dict(r) for r in rows]

    def uptime_ratio(self, project: str, hours: int = 24) -> float | None:
        since = int(time.time()) - hours * 3600
        with self._lock:
            rows = self._conn.execute(
                "SELECT payload FROM snapshots WHERE project=? AND ts>=?",
                (project, since),
            ).fetchall()
        if not rows:
            return None
        ok = 0
        for row in rows:
            data = json.loads(row["payload"])
            if data.get("ok"):
                ok += 1
        return ok / len(rows)
