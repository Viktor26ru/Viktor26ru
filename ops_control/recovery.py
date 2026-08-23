from __future__ import annotations

from typing import Any

from inventory import project_by_id
from probes import ssh_text

RESTART_HINTS = {
    ("x5", "max-chat-collector.service"): "/restart x5 collector",
    ("x5", "max-collector-dashboard.service"): "/restart x5 dashboard",
    ("x5", "max-mail-idle.service"): "/restart x5 mail",
    ("x5", "nginx.service"): "/restart x5 nginx",
    ("chizhik", "ie-bot-parallel-collector.service"): "/restart chizhik collector",
    ("chizhik", "ie-bot-parallel-chizhik-dashboard.service"): "/restart chizhik dashboard",
    ("chizhik", "ie-bot-parallel-dashboard.service"): "/restart chizhik dashboard",
    ("chizhik", "ie-bot-parallel-wrs-report-mail.service"): "/restart chizhik mail",
    ("pm", "project-manager.service"): "/restart pm dashboard",
    ("pm", "cov-platform.service"): "/restart pm platform",
    ("pm", "ops-desk.service"): "/restart pm ops",
}


def restart_hint(project_id: str, unit: str) -> str:
    return RESTART_HINTS.get((project_id, unit), f"/restart {project_id} {unit}")


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


def record_problems(project: dict[str, Any], snapshot: dict[str, Any], store) -> list[dict[str, Any]]:
    """Open/close incidents. Never restarts anything."""
    suggestions: list[dict[str, Any]] = []
    if project["id"] == "cursordev":
        return suggestions
    units = snapshot.get("units") or {}
    failed = set(snapshot.get("failed_units") or [])
    restartable = set(project.get("heal_units", []) + project.get("core_units", []))
    for unit in restartable:
        state = units.get(unit)
        down = (state not in (None, "active")) or unit in failed
        if not down:
            store.resolve_by_target(project["id"], unit, "recovered")
            continue
        summary = f"{unit} = {state or 'failed'}"
        inc_id = store.open_incident(project["id"], unit, "critical", summary)
        suggestions.append(
            {
                "incident_id": inc_id,
                "project": project["id"],
                "unit": unit,
                "command": restart_hint(project["id"], unit),
                "summary": summary,
            }
        )
    for unit in failed:
        if unit in restartable:
            continue
        store.open_incident(project["id"], unit, "warning", f"{unit} failed")
    for disk in snapshot.get("disks") or []:
        if disk.get("mount") != "/":
            continue
        pct = int(disk.get("pct") or 0)
        if pct >= 85:
            store.open_incident(project["id"], "disk:/", "critical", f"корневой диск {pct}%")
        elif pct >= 70:
            store.open_incident(project["id"], "disk:/", "warning", f"корневой диск {pct}%")
        else:
            store.resolve_by_target(project["id"], "disk:/", "ok")
    return suggestions
