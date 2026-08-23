from __future__ import annotations

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from commands import CommandRouter
from inventory import PROJECTS
from store import Store


STATIC = Path(__file__).resolve().parent / "static"


def build_snapshot(store: Store) -> dict:
    snaps = store.latest_snapshots()
    projects = []
    for item in PROJECTS:
        snap = snaps.get(item["id"], {})
        projects.append(
            {
                **item,
                "snapshot": snap,
                "uptime24": store.uptime_ratio(item["id"], 24),
            }
        )
    return {
        "generated_at": int(time.time()),
        "projects": projects,
        "cursordev": snaps.get("cursordev"),
        "incidents": store.recent_incidents(25),
        "open_incidents": store.open_incidents(),
        "commands": store.recent_commands(15),
        "llm": store.llm_totals(),
        "self": {
            "name": "ops-control",
            "place": "Cursor Cloud",
            "independent": True,
        },
    }


class Handler(BaseHTTPRequestHandler):
    store: Store
    router: CommandRouter
    dashboard_key: str

    def log_message(self, fmt: str, *args) -> None:
        return

    def _ok_auth(self) -> bool:
        if not self.dashboard_key:
            return True
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        if qs.get("key", [""])[0] == self.dashboard_key:
            return True
        cookie = self.headers.get("Cookie") or ""
        return f"ops_key={self.dashboard_key}" in cookie

    def _send(self, code: int, body: bytes, content_type: str, extra: list[tuple[str, str]] | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        for k, v in extra or []:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)
        if path in {"/", "/index.html"}:
            html = (STATIC / "index.html").read_bytes()
            extra = []
            key = qs.get("key", [""])[0]
            if key and key == self.dashboard_key:
                extra.append(("Set-Cookie", f"ops_key={key}; Path=/; HttpOnly; SameSite=Lax"))
            self._send(200, html, "text/html; charset=utf-8", extra)
            return
        if path == "/api/health":
            self._send(200, b'{"ok":true}', "application/json")
            return
        if not self._ok_auth():
            self._send(401, b'{"error":"auth"}', "application/json")
            return
        if path == "/api/snapshot":
            body = json.dumps(build_snapshot(self.store), ensure_ascii=False).encode()
            self._send(200, body, "application/json; charset=utf-8")
            return
        if path == "/api/plan":
            plan = Path(__file__).resolve().parent / "PLAN.md"
            self._send(200, plan.read_bytes() if plan.exists() else b"", "text/markdown; charset=utf-8")
            return
        self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:
        if not self._ok_auth():
            self._send(401, b'{"error":"auth"}', "application/json")
            return
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode() or "{}")
        except Exception:
            payload = {}
        if parsed.path == "/api/command":
            text = str(payload.get("text") or "")
            result = self.router.handle("dashboard", "web", text)
            self._send(200, json.dumps({"result": result}, ensure_ascii=False).encode(), "application/json; charset=utf-8")
            return
        self._send(404, b"not found", "text/plain")


def serve(host: str, port: int, store: Store, router: CommandRouter, dashboard_key: str):
    Handler.store = store
    Handler.router = router
    Handler.dashboard_key = dashboard_key
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.serve_forever()
