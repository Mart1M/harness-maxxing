"""iPhone push (push.py): credentials, devices, APNs request shape, event routing. APNs is a mocked transport."""
from __future__ import annotations

import base64
import json

import httpx
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

from maxxing import push

TOKEN = "ab" * 32


@pytest.fixture
def pem() -> str:
    k = ec.generate_private_key(ec.SECP256R1())
    return k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                           serialization.NoEncryption()).decode()


@pytest.fixture
def apns(mx, monkeypatch, pem):
    """Credentials set, every APNs call recorded; `answer` decides the status."""
    calls: list[httpx.Request] = []
    answer = {"status": 200, "reason": ""}

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        body = {"reason": answer["reason"]} if answer["reason"] else {}
        return httpx.Response(answer["status"], json=body)

    monkeypatch.setattr(push, "_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(push, "send_async", lambda *a, **kw: push.send(*a, **kw))      # no thread: deterministic
    push.save_credentials(key=pem, key_id="ABCDE12345", team_id="TEAM123456", topic="com.example.app")
    push.register(TOKEN, "My iPhone")
    return {"calls": calls, "answer": answer, "pem": pem}


def test_credentials_validated_and_never_returned(mx, pem):
    pub = push.save_credentials(key=pem.replace("\n", ""), key_id="ABCDE12345", team_id="TEAM123456", topic="com.x.y")
    assert pub["configured"] and pub["key_set"] and "key" not in pub and "BEGIN" not in json.dumps(pub)
    for bad in ({"key": "not a key!"}, {"key_id": "short"}, {"team_id": "x"}, {"topic": "a b"}):
        with pytest.raises(push.PushError):
            push.save_credentials(**bad)
    # a base64 string that is not an EC key is refused when saved
    with pytest.raises(push.PushError):
        push.save_credentials(key="QUJDREVGRw==")
    push.clear_credentials()
    assert not push.configured()


def test_provider_token_is_es256_and_reused(apns):
    t = push.provider_token(now=1000.0)
    head, claims, sig = t.split(".")
    pad = lambda s: s + "=" * (-len(s) % 4)
    assert json.loads(base64.urlsafe_b64decode(pad(head))) == {"alg": "ES256", "kid": "ABCDE12345"}
    assert json.loads(base64.urlsafe_b64decode(pad(claims))) == {"iss": "TEAM123456", "iat": 1000}
    raw = base64.urlsafe_b64decode(pad(sig))
    assert len(raw) == 64
    pub = serialization.load_pem_private_key(apns["pem"].encode(), None).public_key()
    pub.verify(encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big")),
               f"{head}.{claims}".encode(), ec.ECDSA(hashes.SHA256()))
    assert push.provider_token(now=1000.0 + 600) == t               # reused
    assert push.provider_token(now=1000.0 + 3100) != t              # renewed before Apple's hour


def test_devices(mx):
    assert push.register(TOKEN.upper(), "  My   iPhone ", "sandbox")["registered"] is True
    assert push.register(TOKEN)["registered"] is False             # same token: updated, not duplicated
    assert [d["id"] for d in push.list_devices()] == [TOKEN[:8]]
    for bad in ("zz", "ab" * 3, ""):
        with pytest.raises(push.PushError):
            push.register(bad)
    with pytest.raises(push.PushError):
        push.register(TOKEN, env="moon")
    assert not push.unregister("ab")                                # too short to be an id
    assert push.unregister(TOKEN[:8]) and push.list_devices() == []
    assert push._path().stat().st_mode & 0o777 == 0o600


def test_send_request_shape(apns):
    res = push.send("✅ Build", "All green", path="/sessions/abc", thread="abc")
    assert res == {"sent": 1, "failed": 0, "removed": 0}
    req = apns["calls"][0]
    assert str(req.url) == f"https://api.push.apple.com/3/device/{TOKEN}"
    assert req.headers["apns-topic"] == "com.example.app" and req.headers["apns-push-type"] == "alert"
    assert req.headers["authorization"].startswith("bearer ")
    body = json.loads(req.content)
    assert body["aps"]["alert"] == {"title": "✅ Build", "body": "All green"} and body["aps"]["thread-id"] == "abc"
    assert body["path"] == "/sessions/abc"
    assert push.list_devices()[0]["last_ok"]


def test_sandbox_host_and_unsafe_path(apns):
    push.register(TOKEN, env="sandbox")
    push.send("x", "y", path="//evil.example")
    assert str(apns["calls"][0].url).startswith("https://api.sandbox.push.apple.com/")
    assert json.loads(apns["calls"][0].content)["path"] == ""       # a path stays inside the app


@pytest.mark.parametrize("status,reason", [(410, "Unregistered"), (400, "BadDeviceToken")])
def test_dead_token_forgotten(apns, status, reason):
    apns["answer"].update(status=status, reason=reason)
    assert push.send("x")["removed"] == 1 and push.list_devices() == []


def test_other_failure_keeps_device(apns):
    apns["answer"].update(status=429, reason="TooManyRequests")
    assert push.send("x")["failed"] == 1
    assert push.list_devices()[0]["last_error"] == "429 TooManyRequests"


def test_nothing_without_credentials_or_device(mx, monkeypatch):
    monkeypatch.setattr(push, "_client", lambda: pytest.fail("no call expected"))
    assert push.send("x") == {"sent": 0, "failed": 0, "removed": 0}


def _session(**kw):
    return {"id": "s1", "title": "Refactor", "state": "idle", "last_text": "**Done**: `3` files changed",
            "last_turn": {"kind": "user"}, **kw}


def test_turn_end_routing(apns):
    push.on_turn_end(_session())
    assert json.loads(apns["calls"][-1].content)["aps"]["alert"]["body"] == "Done: 3 files changed"
    n = len(apns["calls"])
    push.on_turn_end(_session(last_turn={"kind": "compact"}))        # a summary
    push.on_turn_end(_session(source="cron"))                        # a scheduled job
    assert len(apns["calls"]) == n
    push.save_settings(turns="notify")
    push.on_turn_end(_session())                                     # only sessions with Notify on
    assert len(apns["calls"]) == n
    push.on_turn_end(_session(notify=True))
    assert len(apns["calls"]) == n + 1
    push.save_settings(turns="off")
    push.on_turn_end(_session(notify=True))
    assert len(apns["calls"]) == n + 1


def test_failed_turn_and_errors_switch(apns):
    push.save_settings(turns="off")
    push.on_turn_end(_session(state="error", error="Claude exited with 1"))
    assert json.loads(apns["calls"][-1].content)["aps"]["alert"]["title"].startswith("⚠️")
    n = len(apns["calls"])
    push.save_settings(errors=False)
    push.on_turn_end(_session(state="error", error="boom"))
    assert len(apns["calls"]) == n


def test_feed_routing(apns):
    from maxxing import feed
    feed.post("Backup done", "ok", level="success", source="crons")
    assert len(apns["calls"]) == 1
    feed.post("Order paid", level="success", source="shop")          # not a job, not an error
    feed.post("Webhook failed", level="error", source="shop")
    assert len(apns["calls"]) == 2
    push.save_settings(crons=False, errors=False)
    feed.post("Backup done", level="success", source="crons")
    feed.post("Webhook failed", level="error", source="shop")
    assert len(apns["calls"]) == 2
    push.save_settings(enabled=True, crons=True)
    push.save_settings(enabled=False)
    feed.post("Backup", level="success", source="crons")
    assert len(apns["calls"]) == 2


def test_api(client, apns):
    r = client.get("/api/push").json()
    assert r["credentials"]["configured"] and r["devices"][0]["name"] == "My iPhone"
    assert client.put("/api/push/settings", json={"turns": "bad"}).status_code == 400
    assert client.put("/api/push/settings", json={"turns": "notify"}).json()["settings"]["turns"] == "notify"
    assert client.post("/api/push/devices", json={"token": "xx"}).status_code == 400
    assert client.post("/api/push/devices", json={"token": "cd" * 32, "name": "iPad"}).status_code == 200
    t = client.post("/api/push/test").json()
    assert t["sent"] == 2
    assert client.delete("/api/push/devices/cdcdcdcd").status_code == 200
    assert client.delete("/api/push/devices/cdcdcdcd").status_code == 404
    assert client.put("/api/push/credentials", json={"key": "###"}).status_code == 400
    assert client.delete("/api/push/credentials").json()["credentials"]["configured"] is False
    assert client.post("/api/push/test").status_code in (200, 409)
