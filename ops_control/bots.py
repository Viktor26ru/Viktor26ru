from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

from inventory import PROJECTS
from probes import ssh_text


class TelegramBot:
    def __init__(self, token: str, handle: Callable[[str, str, str], str], is_admin, add_admin, bind_code: str, admin_ids: list[int]):
        self.token = token
        self.handle = handle
        self.is_admin = is_admin
        self.add_admin = add_admin
        self.bind_code = bind_code
        self.admin_ids = set(admin_ids)
        self.offset = 0
        self.last_chat_id: int | None = None

    def api(self, method: str, payload: dict[str, Any] | None = None, timeout: int = 35) -> dict[str, Any]:
        url = f"https://api.telegram.org/bot{self.token}/{method}"
        data = urllib.parse.urlencode(payload or {}).encode()
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())

    def send(self, chat_id: int, text: str) -> None:
        # Telegram limit 4096
        chunk = text[:3900] or "(пусто)"
        try:
            self.api("sendMessage", {"chat_id": chat_id, "text": chunk})
            self.last_chat_id = int(chat_id)
        except Exception:
            pass

    def notify_admins(self, text: str, store=None) -> None:
        ids = set(self.admin_ids)
        if store:
            for row in store.admins():
                ids.add(int(row["tg_user_id"]))
        if self.last_chat_id:
            ids.add(int(self.last_chat_id))
        for chat_id in ids:
            self.send(chat_id, text)

    def poll_once(self) -> None:
        try:
            data = self.api(
                "getUpdates",
                {"offset": self.offset, "timeout": 25, "allowed_updates": json.dumps(["message"])},
                timeout=40,
            )
        except Exception:
            return
        for upd in data.get("result") or []:
            self.offset = int(upd["update_id"]) + 1
            msg = upd.get("message") or {}
            text = (msg.get("text") or "").strip()
            chat = msg.get("chat") or {}
            user = msg.get("from") or {}
            chat_id = chat.get("id")
            user_id = int(user.get("id") or 0)
            username = user.get("username") or ""
            if not text or not chat_id:
                continue
            self.last_chat_id = int(chat_id)
            if text.startswith("/start"):
                code = text.split(maxsplit=1)[1].strip() if len(text.split()) > 1 else ""
                if user_id in self.admin_ids or (self.bind_code and code == self.bind_code) or (
                    not self.admin_ids and self.bind_code and code == self.bind_code
                ):
                    self.add_admin(user_id, username)
                    self.admin_ids.add(user_id)
                    self.send(chat_id, "доступ открыт. /status или /help")
                elif not self.admin_ids and not code:
                    self.send(chat_id, f"напиши /start {self.bind_code}")
                else:
                    self.send(chat_id, "нет доступа. нужен код привязки.")
                continue
            if not self.is_admin(user_id) and user_id not in self.admin_ids:
                self.send(chat_id, "нет доступа")
                continue
            reply = self.handle("telegram", username or str(user_id), text)
            self.send(chat_id, reply)


def max_send_via_ssh(project_id: str, user_id: int, text: str) -> dict[str, Any]:
    cfg = next(p for p in PROJECTS if p["id"] == project_id)
    payload = json.dumps({"text": text[:3500]}, ensure_ascii=False)
    remote = f"""
python3 - <<'PY'
import json, ssl, urllib.request
from pathlib import Path
env={{}}
for line in Path({cfg["env_path"]!r}).read_text().splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k,v=line.split("=",1); env[k.strip()]=v.strip()
tok=env.get("MAX_BOT_TOKEN","")
body={payload!r}
req=urllib.request.Request(
    "https://platform-api2.max.ru/messages?user_id={user_id}",
    data=body.encode(),
    headers={{"Authorization": tok, "Content-Type": "application/json"}},
    method="POST",
)
ctx=ssl._create_unverified_context()
try:
    with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
        print(r.status, r.read()[:200].decode())
except Exception as e:
    print("ERR", type(e).__name__, e)
PY
"""
    rc, stdout, stderr = ssh_text(cfg["key"], cfg["user"], cfg["host"], remote, timeout=25)
    return {"ok": rc == 0 and "ERR" not in (stdout or ""), "out": stdout, "err": stderr}


class MaxInbox:
    """Long-poll MAX on each host so tokens never leave production."""

    def __init__(self, handle: Callable[[str, str, str], str], allow_ids: set[int]):
        self.handle = handle
        self.allow_ids = allow_ids
        self.markers: dict[str, str] = {}

    def poll_project(self, project_id: str) -> list[str]:
        cfg = next(p for p in PROJECTS if p["id"] == project_id)
        marker = self.markers.get(project_id, "")
        remote = f"""
python3 - <<'PY'
import json, ssl, urllib.parse, urllib.request
from pathlib import Path
env={{}}
for line in Path({cfg["env_path"]!r}).read_text().splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k,v=line.split("=",1); env[k.strip()]=v.strip()
tok=env.get("MAX_BOT_TOKEN","")
q={{"timeout": 5, "limit": 50}}
marker={marker!r}
if marker:
    q["marker"]=marker
url="https://platform-api2.max.ru/updates?"+urllib.parse.urlencode(q)
req=urllib.request.Request(url, headers={{"Authorization": tok}})
ctx=ssl._create_unverified_context()
try:
    with urllib.request.urlopen(req, timeout=12, context=ctx) as r:
        print(r.read().decode())
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
PY
"""
        rc, stdout, stderr = ssh_text(cfg["key"], cfg["user"], cfg["host"], remote, timeout=20)
        replies: list[str] = []
        if rc != 0 or not stdout:
            return replies
        try:
            data = json.loads(stdout[stdout.find("{") :])
        except Exception:
            return replies
        if data.get("marker"):
            self.markers[project_id] = str(data["marker"])
        for upd in data.get("updates") or []:
            msg = upd.get("message") or upd
            sender = (msg.get("sender") or msg.get("from") or {}) if isinstance(msg, dict) else {}
            user_id = int(sender.get("user_id") or sender.get("id") or 0)
            body = ""
            if isinstance(msg, dict):
                body = (msg.get("body") or {}).get("text") if isinstance(msg.get("body"), dict) else msg.get("text") or ""
            body = (body or "").strip()
            if not body or not user_id:
                continue
            if self.allow_ids and user_id not in self.allow_ids:
                continue
            reply = self.handle("max:" + project_id, str(user_id), body)
            max_send_via_ssh(project_id, user_id, reply)
            replies.append(reply)
        return replies
