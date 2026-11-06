"""Processes: start / stop / logs / publish with a password, on the direct (no systemd) backend."""
from __future__ import annotations

import stat
import time
from pathlib import Path

import pytest

from conftest import wait_for
from maxxing import config


@pytest.fixture
def repo(mx) -> Path:
    d = mx["ws"] / "myrepo"
    d.mkdir()
    return d


@pytest.fixture
def fake_caddy(mx, monkeypatch) -> Path:
    d = mx["tmp"] / "caddy"
    (d / "maxxing-paths").mkdir(parents=True)
    (d / "claude-maxxing.caddy").write_text("ui.example.com {\n\treverse_proxy 127.0.0.1:8787\n}\n")
    binary = mx["tmp"] / "caddy-bin"
    binary.write_text('#!/bin/sh\nif [ "$1" = "hash-password" ]; then echo \'$2a$14$abcdefghijklmnopqrstuuABCDEFGHIJKLMNOPQRSTUVWXYZ0123\'; fi\nexit 0\n')
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("MAXXING_CADDY_DIR", str(d))
    monkeypatch.setenv("MAXXING_CADDY_BIN", str(binary))
    monkeypatch.setenv("MAXXING_CADDY_RELOAD", "true")
    monkeypatch.setenv("MAXXING_CADDY_API", "http://127.0.0.1:9")
    monkeypatch.setenv("MAXXING_CADDYFILE", str(d / "nothing"))
    config.update_config(public_url="https://ui.example.com")
    return d


def _stop_all(client):
    for p in client.get("/api/processes").json():
        client.delete(f"/api/processes/{p['name']}")


def test_lifecycle_logs_and_port(client, repo):
    try:
        r = client.post("/api/processes", json={"name": "dev", "repo": str(repo),
                                                "command": "echo started on $PORT; sleep 30"})
        assert r.status_code == 200, r.text
        p = r.json()
        assert p["state"] == "running" and 20000 <= p["port"] <= 29999 and p["repo"] == str(repo)
        out = wait_for(lambda: "started on" in " ".join(client.get("/api/processes/dev/logs").json()["lines"]) or None)
        assert out
        assert f"started on {p['port']}" in " ".join(client.get("/api/processes/dev/logs").json()["lines"])
        assert client.post("/api/processes/dev/stop").json()["state"] == "stopped"
        assert client.post("/api/processes/dev/start").json()["state"] == "running"
        assert client.post("/api/processes/dev/restart").json()["state"] == "running"
        assert [x["name"] for x in client.get("/api/processes").json()] == ["dev"]
    finally:
        _stop_all(client)
    assert client.get("/api/processes").json() == []
    assert client.get("/api/processes/dev").status_code == 404


def test_a_process_that_exits_is_stopped(client, repo):
    try:
        client.post("/api/processes", json={"name": "quick", "repo": str(repo), "command": "echo bye"})
        wait_for(lambda: client.get("/api/processes/quick").json()["state"] == "stopped")
    finally:
        _stop_all(client)


def test_validation(client, repo, mx):
    bad = [{"name": "Bad Name", "repo": str(repo), "command": "x"},
           {"name": "ok", "repo": str(mx["tmp"] / "missing"), "command": "x"},
           {"name": "ok", "repo": str(config.STATE), "command": "x"},
           {"name": "ok", "repo": str(repo), "command": "   "}]
    for body in bad:
        assert client.post("/api/processes", json=body).status_code == 400, body
    try:
        assert client.post("/api/processes", json={"name": "a", "repo": str(repo), "command": "sleep 20", "start": False}).status_code == 200
        assert client.post("/api/processes", json={"name": "a", "repo": str(repo), "command": "x"}).status_code == 409
        port = client.get("/api/processes/a").json()["port"]
        assert client.post("/api/processes", json={"name": "b", "repo": str(repo), "command": "x", "port": port, "start": False}).status_code == 409
    finally:
        _stop_all(client)


def test_publish_needs_a_password_and_can_be_removed(client, repo, fake_caddy):
    try:
        client.post("/api/processes", json={"name": "web", "repo": str(repo), "command": "sleep 20"})
        r = client.post("/api/processes/web/publish", json={})
        assert r.status_code == 200, r.text
        pub = r.json()
        assert pub["url"] == "https://ui.example.com/p-web/" and pub["user"] == "maxxing" and len(pub["password"]) >= 20
        conf = (fake_caddy / "maxxing-paths" / "p-web.caddy").read_text()
        assert "basic_auth {" in conf and "maxxing $2a$14$" in conf and pub["password"] not in conf     # hashed, never in clear
        assert conf.index("basic_auth") < conf.index("reverse_proxy")
        listed = client.get("/api/processes").json()[0]
        assert listed["published"] and listed["url"] == pub["url"] and "password" not in listed
        assert client.get("/api/processes/web/credentials").json()["password"] == pub["password"]
        assert client.post("/api/processes/web/publish", json={}).status_code == 409
        assert client.delete("/api/processes/web/publish").status_code == 200
        assert not (fake_caddy / "maxxing-paths" / "p-web.caddy").exists()
        assert client.get("/api/processes/web/credentials").status_code == 409
        client.post("/api/processes/web/publish", json={})
        assert client.delete("/api/processes/web").status_code == 200           # deleting also removes the URL
        assert not (fake_caddy / "maxxing-paths" / "p-web.caddy").exists()
    finally:
        _stop_all(client)


def test_registry_file_is_private(client, repo):
    try:
        client.post("/api/processes", json={"name": "x", "repo": str(repo), "command": "sleep 5", "start": False})
        mode = (config.STATE / "processes.json").stat().st_mode & 0o777
        assert mode == 0o600
    finally:
        _stop_all(client)
