from __future__ import annotations

import json
from typing import Any, Callable

from inventory import PROJECTS, project_by_id
from probes import probe_project
from recovery import restart_unit


HELP = """Команды:
/status — сводка по всем проектам
/x5 /chizhik /pm — карточка проекта
/uptime — аптайм 24ч
/errors — открытые инциденты
/max — боты MAX
/llm — модели и учёт токенов
/hosts — железо и диск
/restart <x5|chizhik|pm> <unit|collector|dashboard>
/probe <x5|chizhik|pm|cursordev>
/ack <id> — закрыть инцидент
/note <текст> — запись в журнал
/help

Можно писать обычным текстом: «статус пятёрочки», «что горит», «рестарт коллектора чижик».
"""

ALIASES = {
    "x5": "x5",
    "5ka": "x5",
    "пятёроч": "x5",
    "пятероч": "x5",
    "cov": "x5",
    "chiz": "chizhik",
    "чиж": "chizhik",
    "chizhik": "chizhik",
    "pm": "pm",
    "пм": "pm",
    "менедж": "pm",
}


def _resolve_project(text: str) -> str | None:
    low = text.lower()
    for needle, pid in ALIASES.items():
        if needle in low:
            return pid
    return None


def _unit_alias(project_id: str, token: str) -> str | None:
    token = token.lower().strip()
    cfg = project_by_id(project_id)
    if token in {u.replace(".service", "") for u in cfg.get("heal_units", [])}:
        return token if token.endswith(".service") else token + ".service"
    mapping = {
        "x5": {
            "collector": "max-chat-collector.service",
            "dashboard": "max-collector-dashboard.service",
            "mail": "max-mail-idle.service",
            "nginx": "nginx.service",
        },
        "chizhik": {
            "collector": "ie-bot-parallel-collector.service",
            "dashboard": "ie-bot-parallel-chizhik-dashboard.service",
            "mail": "ie-bot-parallel-wrs-report-mail.service",
        },
        "pm": {
            "collector": "project-manager.service",
            "dashboard": "project-manager.service",
            "field": "project-manager.service",
            "platform": "cov-platform.service",
            "ops": "ops-desk.service",
        },
    }
    return mapping.get(project_id, {}).get(token)


def format_status(snaps: dict[str, dict[str, Any]], store) -> str:
    lines = ["Мониторинг ЦОВ · независимое облако"]
    for pid in ["x5", "chizhik", "pm", "cursordev"]:
        snap = snaps.get(pid) or {}
        title = snap.get("title") or pid
        if snap.get("ok"):
            mark = "OK"
        elif snap:
            mark = "FAIL"
        else:
            mark = "NO DATA"
        load = snap.get("load") or ["?", "?", "?"]
        mem = snap.get("mem") or {}
        disk = next((d for d in snap.get("disks") or [] if d.get("mount") == "/"), {})
        up = store.uptime_ratio(pid, 24)
        up_s = f"{up*100:.1f}%" if up is not None else "—"
        extra = snap.get("extra") or {}
        extra_bits = []
        if "process_instances" in extra:
            extra_bits.append(f"заявки {extra['process_instances']}")
        if "messages" in extra:
            extra_bits.append(f"msg {extra['messages']}")
        if "b24_tasks" in extra:
            extra_bits.append(f"b24 {extra['b24_tasks']}")
        lines.append(
            f"{mark} {title} load {load[0]} mem {mem.get('pct','?')}% disk {disk.get('pct','?')}% up {up_s}"
            + (f" · {', '.join(extra_bits)}" if extra_bits else "")
        )
        if snap.get("error"):
            lines.append(f"  err: {snap['error'][:180]}")
        failed = snap.get("failed_units") or []
        if failed:
            lines.append(f"  failed: {', '.join(failed)}")
        mx = snap.get("max") or {}
        if mx.get("ok"):
            lines.append(f"  MAX {mx.get('name')} @{mx.get('username')}")
        elif pid != "cursordev":
            lines.append(f"  MAX: {mx.get('error') or 'нет данных'}")
    open_n = len(store.open_incidents())
    lines.append(f"Инциденты открытые: {open_n}")
    return "\n".join(lines)


def format_project(pid: str, snap: dict[str, Any], store) -> str:
    cfg = None
    try:
        cfg = project_by_id(pid)
    except KeyError:
        pass
    title = (cfg or {}).get("title") or snap.get("title") or pid
    lines = [f"{title} · {snap.get('host','')}"]
    if not snap:
        return f"{title}: нет снимка, /probe {pid}"
    lines.append("состояние " + ("норма" if snap.get("ok") else "проблема"))
    if snap.get("error"):
        lines.append(snap["error"][:300])
    load = snap.get("load") or []
    mem = snap.get("mem") or {}
    lines.append(f"нагрузка {load}  CPU {snap.get('nproc')}  RAM {mem.get('pct')}%")
    for disk in snap.get("disks") or []:
        lines.append(f"диск {disk.get('mount')} {disk.get('pct')}%")
    for unit, state in (snap.get("units") or {}).items():
        lines.append(f"{state} {unit}")
    for http in snap.get("http") or []:
        lines.append(f"HTTP {http.get('code')} {http.get('ms')}ms {http.get('url')}")
    mx = snap.get("max") or {}
    if mx:
        lines.append(f"MAX {mx}")
    extra = snap.get("extra") or {}
    if extra:
        lines.append("метрики " + json.dumps(extra, ensure_ascii=False))
    if cfg:
        lines.append("LLM " + str(cfg.get("llm_model")))
        for note in cfg.get("notes") or []:
            lines.append("· " + note)
    up = store.uptime_ratio(pid, 24)
    if up is not None:
        lines.append(f"аптайм 24ч {up*100:.1f}%")
    return "\n".join(lines)


class CommandRouter:
    def __init__(self, store, notify: Callable[[str], None] | None = None):
        self.store = store
        self.notify = notify or (lambda _msg: None)

    def handle(self, source: str, actor: str, text: str) -> str:
        raw = (text or "").strip()
        if not raw:
            return HELP
        low = raw.lower()
        try:
            result = self._dispatch(raw, low)
        except Exception as exc:
            result = f"ошибка команды: {type(exc).__name__}: {exc}"
        self.store.log_command(source, actor, raw, result)
        return result

    def _dispatch(self, raw: str, low: str) -> str:
        if low in {"/help", "help", "помощь", "?"}:
            return HELP
        if low in {"/status", "status", "статус", "сводка"} or low.startswith("/status"):
            return format_status(self.store.latest_snapshots(), self.store)
        if low in {"/errors", "errors", "ошибки", "что горит", "инциденты", "/incidents"}:
            items = self.store.open_incidents()
            if not items:
                return "открытых инцидентов нет"
            return "\n".join(f"#{i['id']} {i['project']} {i['target']}: {i['summary']}" for i in items)
        if low in {"/uptime", "uptime", "аптайм"}:
            lines = []
            for pid in ["x5", "chizhik", "pm", "cursordev"]:
                up = self.store.uptime_ratio(pid, 24)
                lines.append(f"{pid}: {up*100:.1f}%" if up is not None else f"{pid}: мало данных")
            return "\n".join(lines)
        if low in {"/max", "max", "макс"}:
            snaps = self.store.latest_snapshots()
            lines = []
            for pid in ["x5", "chizhik", "pm"]:
                mx = (snaps.get(pid) or {}).get("max") or {}
                lines.append(f"{pid}: {mx}")
            return "\n".join(lines)
        if low in {"/llm", "llm", "токены"}:
            rows = self.store.llm_totals()
            snaps = self.store.latest_snapshots()
            lines = ["модели с хостов:"]
            for p in PROJECTS:
                lines.append(f"{p['id']}: {p.get('llm_model')}")
            if rows:
                lines.append("учёт вызовов за 24ч:")
                for row in rows:
                    lines.append(str(dict(row)))
            else:
                lines.append("счётчика токенов ProxyAPI с хостов пока нет — пишем события, которые проходят через этот контур")
            return "\n".join(lines)
        if low in {"/hosts", "hosts", "хосты"}:
            snaps = self.store.latest_snapshots()
            lines = []
            for pid, snap in snaps.items():
                disk = next((d for d in snap.get("disks") or [] if d.get("mount") == "/"), {})
                lines.append(
                    f"{pid} {snap.get('host')} load {snap.get('load')} ram {snap.get('mem',{}).get('pct')}% disk {disk.get('pct')}%"
                )
            return "\n".join(lines) or "нет снимков"
        if low.startswith("/ack"):
            parts = raw.split()
            if len(parts) < 2:
                return "формат: /ack <id>"
            self.store.resolve_incident(int(parts[1]), "acked")
            return f"инцидент {parts[1]} закрыт"
        if low.startswith("/note"):
            self.store.open_incident("ops", "note", "info", raw[5:].strip() or "пусто")
            return "записал"
        if low.startswith("/probe") or low.startswith("проверь") or low.startswith("probe"):
            pid = _resolve_project(low) or (raw.split()[1] if len(raw.split()) > 1 else "")
            if pid not in {"x5", "chizhik", "pm", "cursordev"}:
                return "укажи проект: x5 / chizhik / pm / cursordev"
            snap = probe_project(pid)
            self.store.put_snapshot(pid, snap)
            return format_project(pid, snap, self.store)
        if low.startswith("/restart") or "рестарт" in low:
            pid = _resolve_project(low)
            parts = raw.replace("/restart", "").strip().split()
            if not pid and parts:
                pid = _resolve_project(parts[0]) or parts[0]
            unit_tok = ""
            for tok in parts:
                if _resolve_project(tok) == pid:
                    continue
                unit_tok = tok
                break
            if "коллектор" in low or "collector" in low:
                unit_tok = unit_tok or "collector"
            if "дашборд" in low or "dashboard" in low:
                unit_tok = unit_tok or "dashboard"
            if not pid:
                return "формат: /restart x5 collector"
            unit = _unit_alias(pid, unit_tok or "collector")
            if not unit:
                return f"не понял юнит {unit_tok!r}"
            result = restart_unit(pid, unit)
            return json.dumps(result, ensure_ascii=False)
        pid = _resolve_project(low)
        if low.startswith("/x5") or low.startswith("/chiz") or low.startswith("/pm") or (
            pid and any(w in low for w in ("статус", "как", "что"))
        ):
            pid = pid or ("x5" if "/x5" in low else "chizhik" if "chiz" in low else "pm")
            return format_project(pid, self.store.latest_snapshots().get(pid) or {}, self.store)
        if pid:
            return format_project(pid, self.store.latest_snapshots().get(pid) or {}, self.store)
        if any(w in low for w in ("статус", "сводка", "как дела", "монитор")):
            return format_status(self.store.latest_snapshots(), self.store)
        return "не понял. /help\n" + HELP
