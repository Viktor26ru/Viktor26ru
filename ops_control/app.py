#!/usr/bin/env python3
"""Independent COV ops-control plane. Stdlib only."""

from __future__ import annotations

import fcntl
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from bots import MaxInbox, TelegramBot, max_send_via_ssh  # noqa: E402
from commands import CommandRouter  # noqa: E402
from dashboard import serve  # noqa: E402
from inventory import PROJECTS  # noqa: E402
from probes import probe_all  # noqa: E402
from recovery import record_problems, restart_hint  # noqa: E402
from store import Store  # noqa: E402

DATA = ROOT / "data"
SECRETS = ROOT / ".secrets.env"
PID = DATA / "ops.pid"
LOCK = DATA / "ops.lock"
HOST = os.environ.get("OPS_HOST", "0.0.0.0")
PORT = int(os.environ.get("OPS_PORT", "8787"))


def load_env() -> dict[str, str]:
    env = {}
    if SECRETS.exists():
        for line in SECRETS.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    for key in (
        "TELEGRAM_BOT_TOKEN",
        "DASHBOARD_KEY",
        "BIND_CODE",
        "TELEGRAM_ADMIN_IDS",
    ):
        if os.environ.get(key):
            env[key] = os.environ[key]
    return env


class Supervisor:
    def __init__(self, env: dict[str, str]):
        DATA.mkdir(parents=True, exist_ok=True)
        self.env = env
        self.store = Store(DATA / "ops.sqlite")
        self.router = CommandRouter(self.store, notify=self.notify)
        self.stop = threading.Event()
        self.tg: TelegramBot | None = None
        self.max_inbox: MaxInbox | None = None
        admins = [int(x) for x in (env.get("TELEGRAM_ADMIN_IDS") or "").split(",") if x.strip().isdigit()]
        token = env.get("TELEGRAM_BOT_TOKEN") or ""
        if token:
            self.tg = TelegramBot(
                token,
                self.router.handle,
                self.store.is_admin,
                self.store.add_admin,
                env.get("BIND_CODE") or "",
                admins,
            )
        allow = {330798756, 63992802}
        self.max_inbox = MaxInbox(self.router.handle, allow)
        self._notified: set[int] = set()

    def notify(self, text: str) -> None:
        if self.tg:
            self.tg.notify_admins(text, self.store)
        for pid in ("x5", "chizhik", "pm"):
            try:
                max_send_via_ssh(pid, 330798756, text)
            except Exception:
                pass

    def collector_loop(self) -> None:
        while not self.stop.is_set():
            try:
                snaps = probe_all()
                for pid, snap in snaps.items():
                    self.store.put_snapshot(pid, snap)
                    cfg = next((p for p in PROJECTS if p["id"] == pid), None)
                    if cfg:
                        for sug in record_problems(cfg, snap, self.store):
                            if sug["incident_id"] in self._notified:
                                continue
                            self._notified.add(sug["incident_id"])
                            self.notify(
                                f"СБОЙ {sug['project']}: {sug['summary']}\n"
                                f"Сам не рестартую. Если надо — напиши в MAX или Telegram:\n"
                                f"{sug['command']}"
                            )
                    if not snap.get("ok"):
                        inc = self.store.open_incident(
                            pid, "health", "critical", snap.get("error") or "health failed"
                        )
                        if inc not in self._notified:
                            self._notified.add(inc)
                            self.notify(f"СБОЙ {pid}: {snap.get('error') or 'см. дашборд'}")
                    else:
                        self.store.resolve_by_target(pid, "health", "ok")
                for inc in self.store.open_incidents():
                    if inc["id"] in self._notified or inc["target"] == "note":
                        continue
                    self._notified.add(inc["id"])
                    cmd = ""
                    if str(inc["target"]).endswith(".service"):
                        cmd = "\nЕсли надо рестарт: " + restart_hint(inc["project"], inc["target"])
                    self.notify(
                        f"Инцидент #{inc['id']} {inc['project']} {inc['target']}: {inc['summary']}"
                        f"{cmd}\nСам не рестартую — команда только от тебя в MAX или Telegram."
                    )
            except Exception as exc:
                self.store.open_incident("ops", "collector", "warning", str(exc)[:300])
            self.stop.wait(45)

    def tg_loop(self) -> None:
        while not self.stop.is_set() and self.tg:
            try:
                self.tg.poll_once()
            except Exception:
                self.stop.wait(3)

    def max_loop(self) -> None:
        while not self.stop.is_set() and self.max_inbox:
            for pid in ("x5", "chizhik", "pm"):
                if self.stop.is_set():
                    break
                try:
                    self.max_inbox.poll_project(pid)
                except Exception:
                    pass
            self.stop.wait(8)

    def run(self) -> None:
        threads = [
            threading.Thread(target=self.collector_loop, name="collector", daemon=True),
            threading.Thread(target=lambda: serve(HOST, PORT, self.store, self.router, self.env.get("DASHBOARD_KEY") or ""), name="http", daemon=True),
        ]
        if self.tg:
            threads.append(threading.Thread(target=self.tg_loop, name="telegram", daemon=True))
        threads.append(threading.Thread(target=self.max_loop, name="max", daemon=True))
        for t in threads:
            t.start()
        PID.write_text(str(os.getpid()))
        print(f"ops-control up http://{HOST}:{PORT}/ health /api/health", flush=True)
        try:
            while not self.stop.is_set():
                for t in threads:
                    if not t.is_alive() and not self.stop.is_set():
                        self.store.open_incident("ops", t.name, "critical", f"thread {t.name} died")
                        if t.name == "http":
                            t2 = threading.Thread(
                                target=lambda: serve(HOST, PORT, self.store, self.router, self.env.get("DASHBOARD_KEY") or ""),
                                name="http",
                                daemon=True,
                            )
                            t2.start()
                            threads[1] = t2
                        elif t.name == "collector":
                            t2 = threading.Thread(target=self.collector_loop, name="collector", daemon=True)
                            t2.start()
                            threads[0] = t2
                self.stop.wait(5)
        except KeyboardInterrupt:
            self.stop.set()


def already_running() -> bool:
    if not PID.exists():
        return False
    try:
        pid = int(PID.read_text().strip())
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def main() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    if "--daemon" in sys.argv:
        if already_running():
            print("already running")
            return 0
        proc = subprocess.Popen(
            [sys.executable, str(ROOT / "app.py")],
            cwd=str(ROOT),
            stdout=open(DATA / "ops.out", "a"),
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        for _ in range(30):
            time.sleep(0.2)
            try:
                import urllib.request

                urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/health", timeout=1).read()
                print(f"daemon pid={proc.pid} port={PORT}")
                return 0
            except Exception:
                if proc.poll() is not None:
                    print("daemon exited")
                    return 1
        print("daemon started, health not ready yet")
        return 0

    lock_fh = open(LOCK, "w")
    try:
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("another ops-control holds the lock")
        return 0

    env = load_env()
    sup = Supervisor(env)

    def _stop(_s=None, _f=None):
        sup.stop.set()

    signal.signal(signal.SIGTERM, _stop)
    sup.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
