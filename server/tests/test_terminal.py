from maxxing.api import terminal


def test_terminal_runs_in_the_workspace(client, mx):
    (mx["ws"] / "hello.txt").write_text("hello")
    r = client.post("/api/terminal/run", json={"command": "printf '%s:' \"$PWD\"; cat hello.txt"})
    assert r.status_code == 200
    data = r.json()
    assert data["code"] == 0 and data["cwd"] == str(mx["ws"])
    assert data["stdout"] == f"{mx['ws']}:hello"


def test_terminal_validation_and_timeout(client, monkeypatch):
    assert client.post("/api/terminal/run", json={"command": "   "}).status_code == 422
    monkeypatch.setattr(terminal, "TIMEOUT_S", 0.01)
    r = client.post("/api/terminal/run", json={"command": "sleep 1"})
    assert r.status_code == 200
    assert r.json()["timed_out"] is True and r.json()["code"] == 124
