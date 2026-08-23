from __future__ import annotations

import time
from typing import Any

from inventory import project_by_id
from probes import ssh_text


def restart_unit(project_id: str, unit: str) -> dict[str, Any]:
    if project_id == "cursordev":
        return {"ok": False, "error": "на cursordev нет прод-сервисов для restart"}
    cfg = project_by_id(project_id)
    allowed = set(cfg.get("heal_units", []) + cfg.get("core_units", []))
    if unit not in allowed:
        return {"ok": False, "error": f"юнит {unit} не в allowlist восстановления"}
    cmd = f"sudo -n systemctl restart {unit} && sleep 1 && systemctl is-active {unit}"
    rc, stdout, stderr = ssh_text(cfg["key"], cfg["user"], cfg["host"], cmd, timeout=45)
    active = (stdout or "").strip().splitlines()[-1] if stdout else ""
    return {
        "ok": rc == 0 and active == "active",
        "unit": unit,
        "project": project_id,
        "state": active,
        "error": "" if rc == 0 else (stderr or stdout)[:400],
    }


def maybe_heal(project: dict[str, Any], snapshot: dict[str, Any], store, auto_heal: bool) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if not auto_heal or project["id"] == "cursordev":
        return actions
    units = snapshot.get("units") or {}
    failed = set(snapshot.get("failed_units") or [])
    for unit in project.get("heal_units", []):
        state = units.get(unit)
        down = state not in (None, "active") or unit in failed
        if not down:
            store.resolve_by_target(project["id"], unit, "recovered")
            continue
        inc_id = store.open_incident(project["id"], unit, "critical", f"{unit} = {state or 'failed'}")
        key = f"heal:{project['id']}:{unit}"
        last = int(store.kv_get(key, "0") or "0")
        now = int(time.time())
        if now - last < 300:
            continue
        result = restart_unit(project["id"], unit)
        store.kv_set(key, str(now))
        store.log_command("watchdog", "auto", f"restart {project['id']} {unit}", str(result))
        if result.get("ok"):
            store.resolve_incident(inc_id, "restarted")
        actions.append(result)
    # disk is alert-only
    if snapshot.get("disk_hot"):
        store.open_incident(project["id"], "disk:/", "warning", "корневой диск ≥ 85%")
    return actions
