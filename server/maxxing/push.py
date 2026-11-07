"""Push notifications to the iPhone app (APNs). See docs/user/33-notifications.md.

Three parts:
  - credentials: the Apple Developer "APNs Auth Key" (.p8) + Key ID + Team ID + the app's bundle id (topic),
    kept in secrets.json (`apns`), set in Settings -> Notifications;
  - devices: `<state>/push.json` (mode 600) {devices: {token: {name, env, added, last_ok, last_error}}}. The iOS app
    gives its device token to the web page it hosts, which registers it here (`POST /api/push/devices`);
  - sending: HTTP/2 to api.push.apple.com (sandbox for a debug build), ES256 provider token reused for 50 minutes.
    A token Apple refuses as gone (410, BadDeviceToken, Unregistered) is forgotten.

What is sent (config `push`): a finished turn (`turns`: all | notify | off), a failed turn or an error event of the
feed (`errors`), the result of a scheduled job (`crons`). Every send is best effort and never raises.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import threading
import time
from typing import Any

import httpx

from . import config

log = logging.getLogger("maxxing.push")

HOSTS = {"production": "https://api.push.apple.com", "sandbox": "https://api.sandbox.push.apple.com"}
TURNS = ("all", "notify", "off")
DEFAULTS = {"enabled": True, "turns": "all", "errors": True, "crons": True}
TOKEN_RE = re.compile(r"^[0-9a-fA-F]{32,200}$")
BODY_MAX = 180
MAX_DEVICES = 20
JWT_TTL_S = 50 * 60                       # Apple accepts a provider token for 60 minutes, refuses one renewed too often
GONE = {"BadDeviceToken", "Unregistered", "DeviceTokenNotForTopic"}

_lock = threading.Lock()
_jwt: dict[str, Any] = {"key": None, "at": 0.0, "token": ""}


class PushError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


# ---- settings + credentials ------------------------------------------------------------------
def settings() -> dict:
    s = config.load_config().get("push")
    out = dict(DEFAULTS)
    if isinstance(s, dict):
        for k in ("enabled", "errors", "crons"):
            if isinstance(s.get(k), bool):
                out[k] = s[k]
        if s.get("turns") in TURNS:
            out["turns"] = s["turns"]
    return out


def save_settings(**changes: Any) -> dict:
    cur = settings()
    for k, v in changes.items():
        if v is None:
            continue
        if k == "turns" and v not in TURNS:
            raise PushError(400, "bad_turns", f"Turns: {', '.join(TURNS)}")
        if k in ("enabled", "errors", "crons") and not isinstance(v, bool):
            raise PushError(400, "bad_value", f"{k}: true or false")
        cur[k] = v
    config.update_config(push=cur)
    return settings()


def _creds() -> dict:
    c = config.load_secrets().get("apns")
    return c if isinstance(c, dict) else {}


def configured() -> bool:
    c = _creds()
    return all(c.get(k) for k in ("key", "key_id", "team_id", "topic"))


def credentials_public() -> dict:
    c = _creds()
    return {"configured": configured(), "key_set": bool(c.get("key")), "key_id": c.get("key_id", ""),
            "team_id": c.get("team_id", ""), "topic": c.get("topic", "")}


def _pem(text: str) -> str:
    """The .p8 content as pasted (with or without the BEGIN/END lines, newlines lost)."""
    body = re.sub(r"-----(BEGIN|END) PRIVATE KEY-----|\s+", "", text or "")
    if not body or not re.fullmatch(r"[A-Za-z0-9+/=]+", body):
        raise PushError(400, "bad_key", "The key is the content of the AuthKey_XXXXXXXXXX.p8 file")
    lines = [body[i:i + 64] for i in range(0, len(body), 64)]
    return "-----BEGIN PRIVATE KEY-----\n" + "\n".join(lines) + "\n-----END PRIVATE KEY-----\n"


def save_credentials(key: str | None = None, key_id: str | None = None, team_id: str | None = None,
                     topic: str | None = None) -> dict:
    c = dict(_creds())
    if key:
        c["key"] = _pem(key)
        _sign("test", c["key"])                                    # an unusable key is refused now, not at the first push
    for name, value, rx, label in (("key_id", key_id, r"[A-Z0-9]{10}", "Key ID: 10 letters or digits"),
                                   ("team_id", team_id, r"[A-Z0-9]{10}", "Team ID: 10 letters or digits"),
                                   ("topic", topic, r"[A-Za-z0-9.-]{3,200}", "Bundle id: com.example.app")):
        if value is None:
            continue
        value = value.strip()
        if value and not re.fullmatch(rx, value):
            raise PushError(400, "bad_" + name, label)
        c[name] = value
    config.set_secret("apns", {k: v for k, v in c.items() if v} or None)
    _jwt.update(key=None, token="", at=0.0)
    return credentials_public()


def clear_credentials() -> None:
    config.set_secret("apns", None)
    _jwt.update(key=None, token="", at=0.0)


# ---- provider token (ES256 JWT) ---------------------------------------------------------------
def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _sign(message: str, pem: str) -> bytes:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
    try:
        key = serialization.load_pem_private_key(pem.encode(), password=None)
        if not isinstance(key, ec.EllipticCurvePrivateKey):
            raise ValueError("not an EC key")
        r, s = decode_dss_signature(key.sign(message.encode(), ec.ECDSA(hashes.SHA256())))
    except Exception as e:  # noqa: BLE001
        raise PushError(400, "bad_key", f"Unusable key: {e}") from None
    return r.to_bytes(32, "big") + s.to_bytes(32, "big")        # JWS wants r||s, not DER


def provider_token(now: float | None = None) -> str:
    c = _creds()
    if not configured():
        raise PushError(409, "not_configured", "Add the Apple key in Settings -> Notifications")
    now = time.time() if now is None else now
    with _lock:
        ident = (c["key_id"], c["team_id"], c["key"])
        if _jwt["key"] == ident and now - _jwt["at"] < JWT_TTL_S:
            return _jwt["token"]
        head = _b64(json.dumps({"alg": "ES256", "kid": c["key_id"]}, separators=(",", ":")).encode())
        claims = _b64(json.dumps({"iss": c["team_id"], "iat": int(now)}, separators=(",", ":")).encode())
        signing = f"{head}.{claims}"
        token = f"{signing}.{_b64(_sign(signing, c['key']))}"
        _jwt.update(key=ident, at=now, token=token)
        return token


# ---- devices ----------------------------------------------------------------------------------
def _path():
    return config.state_dir() / "push.json"


def _load() -> dict:
    d = config.read_json(_path(), {"devices": {}})
    return d if isinstance(d.get("devices"), dict) else {"devices": {}}


def _save(d: dict) -> None:
    config.write_json(_path(), d, mode=0o600)


def list_devices() -> list[dict]:
    with _lock:
        d = _load()["devices"]
    return [{"id": t[:8], "name": v.get("name", ""), "env": v.get("env", "production"), "added": v.get("added", 0),
             "last_ok": v.get("last_ok"), "last_error": v.get("last_error", "")}
            for t, v in sorted(d.items(), key=lambda kv: kv[1].get("added", 0))]


def register(token: str, name: str = "", env: str = "production") -> dict:
    token = (token or "").strip().lower()
    if not TOKEN_RE.match(token):
        raise PushError(400, "bad_token", "Not a device token")
    if env not in HOSTS:
        raise PushError(400, "bad_env", "Environment: production or sandbox")
    with _lock:
        d = _load()
        cur = d["devices"].get(token)
        if cur is None and len(d["devices"]) >= MAX_DEVICES:
            raise PushError(409, "too_many", f"{MAX_DEVICES} devices at most")
        d["devices"][token] = {**(cur or {"added": time.time()}), "name": " ".join((name or "").split())[:60],
                               "env": env}
        _save(d)
    return {"id": token[:8], "registered": cur is None}


def unregister(device_id: str) -> bool:
    with _lock:
        d = _load()
        hit = [t for t in d["devices"] if t.startswith(device_id.lower())] if len(device_id) >= 8 else []
        if len(hit) != 1:
            return False
        d["devices"].pop(hit[0])
        _save(d)
    return True


def _mark(token: str, ok: bool, error: str = "", forget: bool = False) -> None:
    with _lock:
        d = _load()
        dev = d["devices"].get(token)
        if dev is None:
            return
        if forget:
            d["devices"].pop(token)
        elif ok:
            dev.update(last_ok=time.time(), last_error="")
        else:
            dev["last_error"] = error[:200]
        _save(d)


# ---- sending ----------------------------------------------------------------------------------
def _client() -> httpx.Client:
    """HTTP/2 client (APNs refuses HTTP/1.1). Replaced in tests."""
    return httpx.Client(http2=True, timeout=httpx.Timeout(10.0, connect=5.0))


def _payload(title: str, body: str, path: str, thread: str | None) -> dict:
    aps: dict[str, Any] = {"alert": {"title": title[:80], "body": body[:BODY_MAX]}, "sound": "default"}
    if thread:
        aps["thread-id"] = thread
    return {"aps": aps, "path": path if path.startswith("/") and not path.startswith("//") else ""}


def send(title: str, body: str = "", path: str = "", thread: str | None = None,
         collapse: str | None = None) -> dict:
    """Push to every device -> {sent, failed, removed}. Blocking (call from a worker thread). Never raises."""
    out = {"sent": 0, "failed": 0, "removed": 0}
    try:
        if not configured():
            return out
        with _lock:
            devices = dict(_load()["devices"])
        if not devices:
            return out
        auth = provider_token()
        topic = _creds()["topic"]
        payload = json.dumps(_payload(title, body, path, thread), separators=(",", ":"), ensure_ascii=False)
        with _client() as http:
            for token, dev in devices.items():
                headers = {"authorization": f"bearer {auth}", "apns-topic": topic, "apns-push-type": "alert",
                           "apns-priority": "10", "apns-expiration": str(int(time.time()) + 3600)}
                if collapse:
                    headers["apns-collapse-id"] = collapse[:64]
                try:
                    r = http.post(f"{HOSTS[dev.get('env', 'production')]}/3/device/{token}", content=payload,
                                  headers=headers)
                except httpx.HTTPError as e:
                    out["failed"] += 1
                    _mark(token, False, f"{type(e).__name__}: {e}")
                    continue
                if r.status_code == 200:
                    out["sent"] += 1
                    _mark(token, True)
                    continue
                try:
                    reason = r.json().get("reason", "")
                except ValueError:
                    reason = ""
                if r.status_code == 410 or reason in GONE:
                    out["removed"] += 1
                    _mark(token, False, reason, forget=True)
                else:
                    out["failed"] += 1
                    _mark(token, False, f"{r.status_code} {reason}".strip())
                    if reason in ("ExpiredProviderToken", "InvalidProviderToken"):
                        _jwt.update(key=None, token="", at=0.0)
    except PushError as e:
        log.warning("push: %s", e.message)
        out["failed"] += 1
    except Exception:  # noqa: BLE001
        log.exception("push: send failed")
        out["failed"] += 1
    return out


def send_async(*a: Any, **kw: Any) -> None:
    """Send without blocking the caller. On the event loop (or any thread of the server) a daemon thread does it; in a
    CLI process (a cron run) there is no loop and the process may exit right after: the send is made before returning."""
    if not settings()["enabled"] or not configured():
        return
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        if threading.current_thread() is threading.main_thread():
            send(*a, **kw)
            return
    threading.Thread(target=send, args=a, kwargs=kw, daemon=True, name="push").start()


def test() -> dict:
    if not list_devices():
        raise PushError(409, "no_device", "No iPhone registered yet: open the app and allow notifications")
    return send("WuitBot", "Notifications work.", "/", collapse="test")


# ---- events -> push ---------------------------------------------------------------------------
def _preview(text: str) -> str:
    t = re.sub(r"```.*?```", " ", text or "", flags=re.S)
    t = re.sub(r"[#*_`>\[\]()]|^\s*[-+] ", "", t, flags=re.M)
    return " ".join(t.split())[:BODY_MAX]


def on_turn_end(session: dict, result: dict | None = None) -> None:
    """sessions.service.on_turn_end callback: a finished or failed turn."""
    try:
        s = settings()
        if not s["enabled"] or not configured():
            return
        kind = (session.get("last_turn") or {}).get("kind") or "user"
        if kind in ("compact", "handoff", "seed") or session.get("source") == "cron" or session.get("cron"):
            return                                                # a summary, or a scheduled job (reported as such)
        sid, title = session.get("id", ""), session.get("title") or "Session"
        failed = session.get("state") == "error" or (isinstance(result, dict) and result.get("ok") is False)
        if failed:
            if s["errors"]:
                send_async(f"⚠️ {title}", _preview(str(session.get("error") or "The turn failed")),
                           path=f"/sessions/{sid}", thread=sid)
            return
        if s["turns"] == "off" or (s["turns"] == "notify" and not session.get("notify")):
            return
        send_async(f"✅ {title}", _preview(session.get("last_text") or "") or "Done", path=f"/sessions/{sid}",
                   thread=sid)
    except Exception:  # noqa: BLE001
        log.exception("push: turn end failed")


def on_feed(ev: dict) -> None:
    """feed.post hook: scheduled-job results and error events of any source."""
    try:
        s = settings()
        if not s["enabled"] or not configured():
            return
        src, level = ev.get("source"), ev.get("level")
        if src == "crons":
            if not s["crons"]:
                return
        elif not (s["errors"] and level == "error"):
            return
        icon = {"error": "🔴", "warning": "⚠️", "success": "✅"}.get(level, "ℹ️")
        send_async(f"{icon} {ev.get('title', '')}", _preview(ev.get("body") or ""), path=ev.get("url") or "/",
                   thread=f"feed-{src}")
    except Exception:  # noqa: BLE001
        log.exception("push: feed event failed")


_hooked = False


def install_hooks() -> None:
    global _hooked
    if _hooked:
        return
    from .sessions import service
    service.on_turn_end(on_turn_end)
    _hooked = True
