from __future__ import annotations

import base64
import json
import os
import ssl
import subprocess
import time
import urllib.request
from typing import Any

from inventory import CURSORDEV, PROJECTS, SSH_COMMON, project_by_id


REMOTE_SCRIPT = r'''
import base64, json, os, socket, ssl, subprocess, time, urllib.request
from pathlib import Path

def sh(cmd):
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()

def mem():
    info = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        k, v = line.split(":", 1)
        info[k] = int(v.strip().split()[0]) * 1024
    total = info.get("MemTotal", 1)
    avail = info.get("MemAvailable", 0)
    return {"total": total, "available": avail, "used": total - avail, "pct": round(100 * (total - avail) / total, 1)}

def disks():
    out = []
    rc, stdout, _ = sh("df -B1 -x tmpfs -x devtmpfs -x efivarfs --output=source,fstype,size,used,avail,pcent,target")
    lines = stdout.splitlines()[1:]
    for line in lines:
        parts = line.split()
        if len(parts) < 7:
            continue
        out.append({
            "source": parts[0], "fstype": parts[1], "size": int(parts[2]),
            "used": int(parts[3]), "avail": int(parts[4]),
            "pct": int(parts[5].rstrip("%")), "mount": parts[6],
        })
    return out

def units(names):
    result = {}
    for name in names:
        rc, stdout, _ = sh(f"systemctl is-active {name}")
        result[name] = stdout or "unknown"
    rc, stdout, _ = sh("systemctl --failed --no-legend --plain --no-pager")
    failed = []
    for line in stdout.splitlines():
        for tok in line.split():
            if tok.endswith(".service") or tok.endswith(".timer"):
                failed.append(tok)
                break
    return result, failed

def http_local(urls):
    ctx = ssl._create_unverified_context()
    out = []
    for item in urls:
        url = item["url"]
        t0 = time.time()
        rec = {"id": item["id"], "url": url, "ok": False, "code": 0, "ms": 0, "error": ""}
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=8, context=ctx) as r:
                rec["code"] = r.status
                rec["ok"] = 200 <= r.status < 400
                r.read(64)
        except Exception as e:
            rec["error"] = f"{type(e).__name__}: {e}"
        rec["ms"] = int((time.time() - t0) * 1000)
        out.append(rec)
    return out

def max_me(env_path):
    rec = {"ok": False, "name": "", "username": "", "user_id": None, "error": ""}
    if not env_path or not Path(env_path).exists():
        rec["error"] = "no env"
        return rec
    env = {}
    for line in Path(env_path).read_text(errors="replace").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    tok = env.get("MAX_BOT_TOKEN", "")
    if not tok:
        rec["error"] = "no token"
        return rec
    ctx = ssl._create_unverified_context()
    for base in ("https://platform-api2.max.ru", "https://platform-api.max.ru"):
        try:
            req = urllib.request.Request(base + "/me", headers={"Authorization": tok})
            with urllib.request.urlopen(req, timeout=12, context=ctx) as r:
                data = json.loads(r.read().decode())
            rec.update({"ok": True, "name": data.get("name") or data.get("first_name") or "",
                        "username": data.get("username") or "", "user_id": data.get("user_id"),
                        "base": base})
            return rec
        except Exception as e:
            rec["error"] = f"{base}: {type(e).__name__}"
    return rec

def extra_counts(project):
    extra = {}
    if project == "x5":
        rc, stdout, _ = sh("sudo -n -u postgres psql -d max_chat_collector -Atc \"SELECT 'messages,'||COUNT(*) FROM messages UNION ALL SELECT 'process_instances,'||COUNT(*) FROM process_instances UNION ALL SELECT 'sla_batches,'||COUNT(*) FROM sla_batches\"")
        if rc == 0:
            for line in stdout.splitlines():
                if "," in line:
                    k, v = line.split(",", 1)
                    extra[k] = int(v)
        extra["raw_dir"] = "/var/lib/max-chat-collector/raw"
    elif project == "chizhik":
        rc, stdout, _ = sh("sudo -n -u postgres psql -d ie_bot_parallel -Atc \"SELECT 'messages,'||COUNT(*) FROM messages UNION ALL SELECT 'ingest_log,'||COUNT(*) FROM ingest_log\"")
        if rc == 0:
            for line in stdout.splitlines():
                if "," in line:
                    k, v = line.split(",", 1)
                    extra[k] = int(v)
    elif project == "pm":
        try:
            import sqlite3
            c = sqlite3.connect("/var/lib/project-manager/cov_pm.sqlite")
            extra["pm_people"] = c.execute("SELECT COUNT(*) FROM people").fetchone()[0]
            extra["pm_tasks"] = c.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
            c.close()
            c = sqlite3.connect("/var/lib/project-manager/b24/projection.sqlite")
            extra["b24_users"] = c.execute("SELECT COUNT(*) FROM b24_users").fetchone()[0]
            extra["b24_tasks"] = c.execute("SELECT COUNT(*) FROM b24_tasks").fetchone()[0]
            c.close()
        except Exception as e:
            extra["sqlite_error"] = str(e)
    return extra

cfg = json.loads(base64.b64decode(os.environ["OPS_PROBE_CFG_B64"]))
load1, load5, load15 = os.getloadavg()
unit_names = list(dict.fromkeys(cfg.get("core_units", []) + cfg.get("watch_units", [])))
unit_map, failed = units(unit_names)
payload = {
    "project": cfg.get("id"),
    "hostname": socket.gethostname(),
    "ts": int(time.time()),
    "load": [round(load1, 2), round(load5, 2), round(load15, 2)],
    "nproc": os.cpu_count() or 1,
    "mem": mem(),
    "disks": disks(),
    "units": unit_map,
    "failed_units": failed,
    "http": http_local(cfg.get("http", [])),
    "max": max_me(cfg.get("env_path")),
    "extra": extra_counts(cfg.get("id")),
    "uptime_sec": int(float(Path("/proc/uptime").read_text().split()[0])),
}
core_ok = all(unit_map.get(u) == "active" for u in cfg.get("core_units", []))
http_ok = all(x.get("ok") for x in payload["http"]) if payload["http"] else True
disk_hot = any(d["pct"] > 90 and d["mount"] == "/" for d in payload["disks"])
payload["ok"] = core_ok and http_ok and not disk_hot
payload["core_ok"] = core_ok
payload["http_ok"] = http_ok
payload["disk_hot"] = disk_hot
print(json.dumps(payload, ensure_ascii=False))
'''


def _ssh_base(key: str, user: str, host: str) -> list[str]:
    return ["ssh", "-i", key, *SSH_COMMON, f"{user}@{host}"]


def ssh_json(key: str, user: str, host: str, remote: str, env: dict[str, str] | None = None, timeout: int = 40) -> dict[str, Any]:
    cmd = _ssh_base(key, user, host) + [remote]
    merged = os.environ.copy()
    if env:
        # env is applied on remote via prefix
        prefix = " ".join(f"{k}={json.dumps(v)}" for k, v in env.items())
        cmd[-1] = f"{prefix} {remote}"
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "ssh failed")[:500])
    text = (proc.stdout or "").strip()
    if not text:
        raise RuntimeError("empty ssh output")
    return json.loads(text.splitlines()[-1] if text.startswith("{") or "\n{" in text else text)


def ssh_text(key: str, user: str, host: str, remote: str, timeout: int = 40) -> tuple[int, str, str]:
    cmd = _ssh_base(key, user, host) + [remote]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()


def probe_http(url: str, timeout: int = 8) -> dict[str, Any]:
    ctx = ssl._create_unverified_context()
    t0 = time.time()
    rec = {"url": url, "ok": False, "code": 0, "ms": 0, "error": ""}
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            rec["code"] = resp.status
            rec["ok"] = 200 <= resp.status < 400
            resp.read(128)
    except Exception as exc:
        rec["error"] = f"{type(exc).__name__}: {exc}"
    rec["ms"] = int((time.time() - t0) * 1000)
    return rec


def probe_project(project_id: str) -> dict[str, Any]:
    if project_id == "cursordev":
        return probe_cursordev()
    cfg = project_by_id(project_id)
    slim = {
        "id": cfg["id"],
        "core_units": cfg.get("core_units", []),
        "watch_units": cfg.get("watch_units", []),
        "http": cfg.get("http", []),
        "env_path": cfg.get("env_path", ""),
    }
    cfg_b64 = base64.b64encode(json.dumps(slim, ensure_ascii=False).encode()).decode()
    script = f"export OPS_PROBE_CFG_B64={cfg_b64}\npython3 - <<'PY'\n{REMOTE_SCRIPT}\nPY"
    rc, stdout, stderr = ssh_text(cfg["key"], cfg["user"], cfg["host"], script, timeout=50)
    if rc != 0:
        return {
            "project": project_id,
            "ok": False,
            "error": (stderr or stdout or f"ssh rc={rc}")[:600],
            "ts": int(time.time()),
        }
    try:
        data = json.loads(stdout[stdout.find("{") :])
    except Exception as exc:
        return {
            "project": project_id,
            "ok": False,
            "error": f"bad json: {exc} :: {stdout[:300]}",
            "ts": int(time.time()),
        }
    data["project"] = project_id
    data["title"] = cfg["title"]
    data["host"] = cfg["host"]
    data["llm_model"] = cfg.get("llm_model")
    data["max_expected"] = {
        "name": cfg.get("max_bot_name"),
        "username": cfg.get("max_bot_username"),
        "user_id": cfg.get("max_bot_user_id"),
    }
    return data


def probe_cursordev() -> dict[str, Any]:
    script = r"""
python3 - <<'PY'
import json, os, socket, time
from pathlib import Path
def mem():
    info={}
    for line in Path("/proc/meminfo").read_text().splitlines():
        k,v=line.split(":",1); info[k]=int(v.strip().split()[0])*1024
    total=info.get("MemTotal",1); avail=info.get("MemAvailable",0)
    return {"total":total,"available":avail,"used":total-avail,"pct":round(100*(total-avail)/total,1)}
def disks():
    import subprocess
    p=subprocess.run("df -B1 -x tmpfs -x devtmpfs --output=source,fstype,size,used,avail,pcent,target",shell=True,capture_output=True,text=True)
    out=[]
    for line in p.stdout.splitlines()[1:]:
        parts=line.split()
        if len(parts)>=7:
            out.append({"source":parts[0],"fstype":parts[1],"size":int(parts[2]),"used":int(parts[3]),"avail":int(parts[4]),"pct":int(parts[5].rstrip('%')),"mount":parts[6]})
    return out
load=os.getloadavg()
print(json.dumps({
  "project":"cursordev","hostname":socket.gethostname(),"ts":int(time.time()),
  "load":[round(load[0],2),round(load[1],2),round(load[2],2)],
  "nproc":os.cpu_count(),"mem":mem(),"disks":disks(),
  "units":{},"failed_units":[],"http":[],"max":{"ok":False,"error":"n/a"},
  "extra":{"projects":["x5","chizhik","project-manager"]},
  "uptime_sec": int(float(Path("/proc/uptime").read_text().split()[0])),
  "ok": True, "core_ok": True, "http_ok": True, "disk_hot": False,
}))
PY
"""
    rc, stdout, stderr = ssh_text(CURSORDEV["key"], CURSORDEV["user"], CURSORDEV["host"], script)
    if rc != 0:
        return {"project": "cursordev", "ok": False, "error": (stderr or stdout)[:500], "ts": int(time.time())}
    data = json.loads(stdout[stdout.find("{") :])
    data["title"] = CURSORDEV["title"]
    data["host"] = CURSORDEV["host"]
    return data


def probe_all() -> dict[str, dict[str, Any]]:
    out = {}
    for item in [{"id": "cursordev"}, *PROJECTS]:
        try:
            out[item["id"]] = probe_project(item["id"])
        except Exception as exc:
            out[item["id"]] = {
                "project": item["id"],
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "ts": int(time.time()),
            }
    return out
