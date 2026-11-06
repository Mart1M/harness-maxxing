"""Processes: long-running commands (dev servers, builds, agents) started in a repository, with a status, logs and an
optional URL protected by a password.  Page `/process`, API `/api/processes`.

* Each process is a transient systemd unit `maxxing-proc-<name>` (`systemd-run`): it survives the browser, the Harness
  service restarting and a crash of the UI. Tests / dev (`MAXXING_SPAWN=direct`): a detached subprocess instead.
* Output goes to `<state>/processes/<name>.log` (`StandardOutput=append:`), read back for the logs.
* Registry: `<state>/processes.json` (mode 600: it holds the passwords of published processes).
* Publishing = a Caddy site (`infra/caddy.py`) in front of the process' local port, with HTTP basic auth: a path site
  `https://<harness address>/p-<name>/` (sandboxed, no DNS needed) or, with a host name, `https://<host>/`.
  The password is generated, shown in the page on request, and stored hashed in Caddy.
"""
from __future__ import annotations

import os
import re
import secrets
import shutil
import signal
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from . import config
from .sessions import spawn

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}\Z")
PORT_RANGE = (20000, 29999)
LOG_MAX_BYTES = 1_000_000            # a log file above this is cut to its last half when the process starts
LOG_TAIL_BYTES = 200_000
AUTH_USER = "maxxing"
SITE_PREFIX = "p-"
_lock = threading.RLock()
_cpu: dict[str, tuple[float, int]] = {}      # name -> (monotonic time, cpu ns) of the last sample


class ProcessError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


# ---- registry ------------------------------------------------------------------------------------
def _path() -> Path:
    return config.STATE / "processes.json"


def _load() -> dict[str, dict]:
    d = config.read_json(_path(), {})
    return d if isinstance(d, dict) else {}


def _save(d: dict[str, dict]) -> None:
    config.write_json(_path(), d, mode=0o600)


def unit_name(name: str) -> str:
    return f"maxxing-proc-{name}"


def log_path(name: str) -> Path:
    return config.state_dir("processes") / f"{name}.log"


def _use_systemd() -> bool:
    return os.environ.get("MAXXING_SPAWN") != "direct" and bool(shutil.which("systemd-run"))


def check_repo(repo: str) -> str:
    """Absolute, existing folder, outside what Harness protects (its state, code, ssh keys)."""
    raw = (repo or "").strip()
    if not raw or "\x00" in raw:
        raise ProcessError(400, "invalid_repo", "Give the folder of the repository")
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = config.workspace() / p
    p = p.resolve()
    if not p.is_dir():
        raise ProcessError(400, "invalid_repo", f"{p} is not a folder")
    home = Path(os.environ.get("HOME") or "/root")
    for never in (config.STATE, config.CODE, home / ".ssh", Path("/etc"), Path("/proc"), Path("/sys")):
        if p == never or p.is_relative_to(never):
            raise ProcessError(400, "invalid_repo", f"{p} cannot be used (system or secret folder)")
    return str(p)


def _free_port(taken: set[int]) -> int:
    for port in range(PORT_RANGE[0], PORT_RANGE[1] + 1):
        if port in taken:
            continue
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
            except OSError:
                continue
        return port
    raise ProcessError(409, "no_port", "No free port left in the process range")


# ---- state of one process -------------------------------------------------------------------------
def _systemd_state(name: str) -> dict:
    keys = ("ActiveState", "SubState", "MainPID", "MemoryCurrent", "CPUUsageNSec", "ActiveEnterTimestampMonotonic")
    try:
        r = subprocess.run(["systemctl", "show", unit_name(name), "--no-pager", *[f"-p{k}" for k in keys]],
                           capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return {"state": "unknown"}
    info = dict(line.split("=", 1) for line in r.stdout.splitlines() if "=" in line)
    active = info.get("ActiveState")
    out: dict[str, Any] = {"state": "running" if active in ("active", "activating", "reloading")
                           else "failed" if active == "failed" else "stopped"}
    pid = int(info.get("MainPID") or 0)
    out["pid"] = pid or None
    mem = info.get("MemoryCurrent", "")
    out["memory_mb"] = round(int(mem) / 1048576, 1) if mem.isdigit() and int(mem) < 2**63 else None
    cpu = info.get("CPUUsageNSec", "")
    if out["state"] == "running" and cpu.isdigit() and int(cpu) < 2**63:
        now, ns = time.monotonic(), int(cpu)
        prev = _cpu.get(name)
        _cpu[name] = (now, ns)
        out["cpu_pct"] = round(max(0.0, (ns - prev[1]) / 1e9 / (now - prev[0]) * 100), 1) if prev and now > prev[0] else None
    else:
        _cpu.pop(name, None)
        out["cpu_pct"] = None
    since = info.get("ActiveEnterTimestampMonotonic", "")
    out["uptime_s"] = int(time.monotonic() - int(since) / 1e6) if out["state"] == "running" and since.isdigit() and int(since) else None
    return out


def _direct_state(rec: dict) -> dict:
    pid = rec.get("pid")
    alive = False
    if isinstance(pid, int) and pid > 0:
        try:
            os.kill(pid, 0)
            alive = not _is_zombie(pid)
        except OSError:
            alive = False
    return {"state": "running" if alive else "stopped", "pid": pid if alive else None, "memory_mb": None,
            "cpu_pct": None, "uptime_s": int(time.time() - rec["started_at"]) if alive and rec.get("started_at") else None}


def _is_zombie(pid: int) -> bool:
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0] == "Z"
    except (OSError, IndexError):
        return False


def _public(rec: dict, with_state: bool = True) -> dict:
    out = {k: rec.get(k) for k in ("id", "name", "repo", "command", "port", "created", "started_at", "url", "mode")}
    out["published"] = bool(rec.get("url"))
    out["auth_user"] = AUTH_USER if rec.get("url") else None
    if with_state:
        out.update(_systemd_state(rec["name"]) if _use_systemd() else _direct_state(rec))
    return out


def list_processes() -> list[dict]:
    with _lock:
        recs = list(_load().values())
    return [_public(r) for r in sorted(recs, key=lambda r: r.get("created") or 0)]


def get(name: str) -> dict:
    rec = _load().get(name)
    if rec is None:
        raise ProcessError(404, "not_found", f"No process named {name}")
    return rec


def get_public(name: str) -> dict:
    return _public(get(name))


# ---- lifecycle ------------------------------------------------------------------------------------
def create(name: str, repo: str, command: str, port: int | None = None, start_now: bool = True) -> dict:
    name = (name or "").strip().lower()
    if not NAME_RE.match(name):
        raise ProcessError(400, "invalid_name", "Name: a-z, 0-9 and -, 40 characters at most")
    command = (command or "").strip()
    if not command or len(command) > 2000 or "\x00" in command:
        raise ProcessError(400, "invalid_command", "Give the command to run (2000 characters at most)")
    folder = check_repo(repo)
    if port is not None and not 1 <= int(port) <= 65535:
        raise ProcessError(400, "invalid_port", "Invalid port")
    with _lock:
        recs = _load()
        if name in recs:
            raise ProcessError(409, "exists", f"A process named {name} already exists")
        taken = {int(r["port"]) for r in recs.values() if r.get("port")}
        if port is not None and int(port) in taken:
            raise ProcessError(409, "port_taken", f"Port {port} belongs to another process")
        recs[name] = {"id": name, "name": name, "repo": folder, "command": command,
                      "port": int(port) if port is not None else _free_port(taken),
                      "created": time.time(), "started_at": None, "url": None, "mode": None, "pid": None}
        _save(recs)
    return start(name) if start_now else get_public(name)


def _trim_log(path: Path) -> None:
    try:
        if path.stat().st_size > LOG_MAX_BYTES:
            data = path.read_bytes()[-LOG_MAX_BYTES // 2:]
            path.write_bytes(data)
    except OSError:
        pass


def start(name: str) -> dict:
    with _lock:
        rec = get(name)
        if _public(rec)["state"] == "running":
            return _public(rec)
        folder = check_repo(rec["repo"])                  # the folder may have gone since
        log = log_path(name)
        _trim_log(log)
        env = spawn.base_env()
        env.update({"PORT": str(rec["port"]), "HOST": "127.0.0.1", "HOSTNAME": "127.0.0.1", "MAXXING_PROCESS": name})
        if _use_systemd():
            unit = unit_name(name)
            subprocess.run(["systemctl", "reset-failed", unit], capture_output=True, timeout=10)
            sets = [a for k in ("HOME", "PATH", "PORT", "HOST", "HOSTNAME", "MAXXING_PROCESS") for a in ("--setenv", f"{k}={env[k]}")]
            cmd = ["systemd-run", "--collect", "--quiet", "--unit", unit, "--description", f"Harness process {name}",
                   "--property", "KillMode=control-group", "--property", "TimeoutStopSec=15",
                   "--property", f"StandardOutput=append:{log}", "--property", f"StandardError=append:{log}",
                   *spawn.memory_properties(), *spawn.hardening_properties(),
                   "--working-directory", folder, *sets, "--", "/bin/sh", "-c", rec["command"]]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                raise ProcessError(500, "start_failed", (r.stderr or r.stdout).strip()[:300] or "systemd-run failed")
        else:
            with open(log, "ab") as lf:
                p = subprocess.Popen(["/bin/sh", "-c", rec["command"]], cwd=folder, env=env, stdin=subprocess.DEVNULL,
                                     stdout=lf, stderr=lf, start_new_session=True)
            threading.Thread(target=p.wait, daemon=True).start()        # reap: no zombie
            rec["pid"] = p.pid
        rec["started_at"] = time.time()
        recs = _load()
        recs[name] = rec
        _save(recs)
        return _public(rec)


def stop(name: str) -> dict:
    with _lock:
        rec = get(name)
        if _use_systemd():
            subprocess.run(["systemctl", "stop", unit_name(name)], capture_output=True, timeout=30)
        else:
            pid = rec.get("pid")
            if isinstance(pid, int) and pid > 0:
                for sig in (signal.SIGTERM, signal.SIGKILL):
                    try:
                        os.killpg(pid, sig)
                    except OSError:
                        break
                    deadline = time.time() + 3
                    while time.time() < deadline and _direct_state(rec)["state"] == "running":
                        time.sleep(0.05)
                    if _direct_state(rec)["state"] != "running":
                        break
        _cpu.pop(name, None)
        return _public(rec)


def restart(name: str) -> dict:
    stop(name)
    return start(name)


def delete(name: str) -> dict:
    with _lock:
        rec = get(name)
        stop(name)
        if rec.get("url"):
            try:
                unpublish(name)
            except Exception:  # noqa: BLE001  (Caddy missing or refusing: the process is removed anyway)
                pass
        recs = _load()
        recs.pop(name, None)
        _save(recs)
        log_path(name).unlink(missing_ok=True)
    return {"ok": True}


def logs(name: str, lines: int = 200) -> dict:
    get(name)
    lines = max(1, min(int(lines), 2000))
    try:
        with open(log_path(name), "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - LOG_TAIL_BYTES))
            text = f.read().decode("utf-8", "replace")
    except OSError:
        text = ""
    return {"lines": text.splitlines()[-lines:]}


# ---- URL -------------------------------------------------------------------------------------------
def publish(name: str, host: str | None = None) -> dict:
    """Put the process behind a Caddy site with basic auth. Returns {url, user, password}."""
    from .infra import caddy
    with _lock:
        rec = get(name)
        if rec.get("url"):
            raise ProcessError(409, "published", "Already published: unpublish it first")
        password = secrets.token_urlsafe(18)
        site = SITE_PREFIX + name
        try:
            res = caddy.add_site(site, port=rec["port"], host=(host or "").strip() or None, kind="process",
                                 basic_auth=(AUTH_USER, password))
        except caddy.CaddyError as e:
            raise ProcessError(400, e.code, str(e)) from None
        rec.update(url=res["url"], mode=res["mode"], password=password, site=site)
        recs = _load()
        recs[name] = rec
        _save(recs)
        return {"url": res["url"], "user": AUTH_USER, "password": password}


def unpublish(name: str) -> dict:
    from .infra import caddy
    with _lock:
        rec = get(name)
        if not rec.get("url"):
            return {"ok": True}
        try:
            caddy.remove_site(rec.get("site") or SITE_PREFIX + name)
        except caddy.CaddyError as e:
            if e.code != "not_found":
                raise ProcessError(400, e.code, str(e)) from None
        for k in ("url", "mode", "password", "site"):
            rec.pop(k, None)
        recs = _load()
        recs[name] = rec
        _save(recs)
    return {"ok": True}


def credentials(name: str) -> dict:
    rec = get(name)
    if not rec.get("url"):
        raise ProcessError(409, "not_published", "This process has no URL")
    return {"url": rec["url"], "user": AUTH_USER, "password": rec.get("password") or ""}
