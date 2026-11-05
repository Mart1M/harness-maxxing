"""Providers: Codex and Cursor turns through the same runner, log and normaliser as Claude."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import all_events, wait_idle
from maxxing.sessions import providers

HERE = Path(__file__).resolve().parent
CODEX_SAMPLE = [  # recorded from `codex exec --json` (codex-cli 0.160.0)
    '{"type":"thread.started","thread_id":"01a1ae01-baae-7c83-aad3-2d124f7fed77"}',
    '{"type":"turn.started"}',
    '{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"ok"}}',
    '{"type":"turn.completed","usage":{"input_tokens":19743,"cached_input_tokens":7936,"cache_write_input_tokens":0,'
    '"output_tokens":5,"reasoning_output_tokens":0}}']


def test_codex_adapter_translates_a_recorded_turn():
    ad = providers.make_adapter("codex")
    evs = [e for line in CODEX_SAMPLE for e in ad.feed(line)]
    assert [e["type"] for e in evs] == ["system", "assistant", "result"]
    assert ad.thread_id == "01a1ae01-baae-7c83-aad3-2d124f7fed77"
    assert evs[0]["subtype"] == "init" and evs[0]["session_id"] == ad.thread_id
    assert evs[1]["message"]["content"][0] == {"type": "text", "text": "ok"}
    assert evs[2]["result"] == "ok" and not evs[2]["is_error"]
    assert evs[2]["usage"]["input_tokens"] == 19743 and evs[2]["usage"]["cache_read_input_tokens"] == 7936


def test_codex_tool_items_and_failures():
    ad = providers.make_adapter("codex")
    started = ad.feed(json.dumps({"type": "item.started", "item": {"id": "i1", "type": "command_execution",
                                                                   "command": "ls", "status": "in_progress"}}))
    done = ad.feed(json.dumps({"type": "item.completed", "item": {"id": "i1", "type": "command_execution",
                                                                  "command": "ls", "aggregated_output": "x",
                                                                  "exit_code": 2, "status": "failed"}}))
    assert started[0]["message"]["content"][0]["name"] == "Bash"
    assert len(done) == 1 and done[0]["message"]["content"][0]["is_error"] is True      # tool_use not repeated
    failed = ad.feed(json.dumps({"type": "turn.failed", "error": {"message": "quota"}}))[0]
    assert failed["is_error"] and failed["errors"] == ["quota"]
    assert ad.feed("not json") == []


def test_cursor_adapter_drops_noise_and_maps_usage():
    ad = providers.make_adapter("cursor")
    lines = [
        {"type": "system", "subtype": "init", "session_id": "S1", "model": "Auto"},
        {"type": "user", "message": {"role": "user", "content": []}, "session_id": "S1"},
        {"type": "thinking", "subtype": "delta", "text": "x", "session_id": "S1"},
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "ok"}]}},
        {"type": "result", "subtype": "success", "is_error": False, "result": "ok",
         "usage": {"inputTokens": 10, "outputTokens": 2, "cacheReadTokens": 4, "cacheWriteTokens": 0}}]
    evs = [e for ln in lines for e in ad.feed(json.dumps(ln))]
    assert [e["type"] for e in evs] == ["system", "assistant", "result"]
    assert ad.thread_id == "S1"
    assert evs[2]["usage"] == {"input_tokens": 10, "cache_read_input_tokens": 4, "cache_creation_input_tokens": 0,
                               "output_tokens": 2}


def test_argv_builders():
    a = providers.build_args("codex", "codex", mode="plan", model="gpt-5", csid="T", fresh=False, cwd="/w")
    assert a[:3] == ["codex", "exec", "--json"] and "read-only" in a and a[-3:] == ["resume", "T", "-"]
    assert a.index("-m") < a.index("resume")                       # exec options come before `resume`
    b = providers.build_args("codex", "codex", mode="bypass", model="", csid="", fresh=True, cwd="/w")
    assert "--dangerously-bypass-approvals-and-sandbox" in b and "resume" not in b and b[-1] == "-"
    c = providers.build_args("cursor", "cursor-agent", mode="plan", model="", csid="C", fresh=False, cwd="/w")
    assert ["--mode", "plan"] == c[c.index("--mode"):c.index("--mode") + 2] and c[-2:] == ["--resume", "C"]
    assert "--force" in providers.build_args("cursor", "cursor-agent", mode="bypass", model="", csid="",
                                             fresh=True, cwd="/w")
    with pytest.raises(ValueError):
        providers.build_args("claude", "claude", mode="bypass", model="", csid="", fresh=True, cwd="/w")


@pytest.fixture
def agents(mx, monkeypatch):
    for name in ("fake_codex.py", "fake_cursor.py"):
        (HERE / name).chmod(0o755)
    monkeypatch.setenv("MAXXING_CODEX_BIN", str(HERE / "fake_codex.py"))
    monkeypatch.setenv("MAXXING_CURSOR_BIN", str(HERE / "fake_cursor.py"))
    monkeypatch.setenv("FAKE_CODEX_DIR", str(mx["tmp"] / "fc"))
    monkeypatch.setenv("FAKE_CURSOR_DIR", str(mx["tmp"] / "fu"))
    return mx


def _calls(d: Path) -> list[dict]:
    return [json.loads(x) for x in (d / "calls.jsonl").read_text().splitlines()]


def _texts(events: list[dict]) -> list[str]:
    return [e.get("text") or "" for e in events if e.get("type") in ("assistant_text", "text", "assistant")]


@pytest.mark.parametrize("provider,dirname", [("codex", "fc"), ("cursor", "fu")])
def test_session_runs_resumes_and_survives_a_lost_thread(client, topic, agents, provider, dirname):
    r = client.post("/api/sessions", json={"path": topic, "message": "hello", "provider": provider})
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    assert r.json()["provider"] == provider
    s = wait_idle(client, sid)
    assert s["error"] is None and s["turns"] == 1, s
    events = all_events(client, sid)
    blob = json.dumps(events)
    assert f"{provider} says ok" in blob and "echo hi" in blob                 # answer + the shell tool card
    d = agents["tmp"] / dirname
    first = _calls(d)[0]
    assert "hello" in first["prompt"] and ("resume" not in first["argv"] and "--resume" not in first["argv"])

    assert client.post(f"/api/sessions/{sid}/messages", json={"text": "again"}).status_code == 200
    wait_idle(client, sid)
    second = _calls(d)[-1]
    assert "resume" in second["argv"] or "--resume" in second["argv"]          # the id the CLI gave us is reused

    for f in d.iterdir():                                                       # the CLI forgets its threads
        if f.name != "calls.jsonl":
            f.unlink()
    assert client.post(f"/api/sessions/{sid}/messages", json={"text": "third"}).status_code == 200
    s = wait_idle(client, sid)
    assert s["error"] is None and s["turns"] == 3
    assert "no longer available" in json.dumps(all_events(client, sid))


def test_failed_turn_reports_the_provider_error(client, topic, agents):
    sid = client.post("/api/sessions", json={"path": topic, "message": "FAIL please", "provider": "codex"}).json()["id"]
    s = wait_idle(client, sid)
    assert s["error"] and "boom" in s["error"]


def test_default_provider_setting_and_validation(client, topic, agents):
    assert client.post("/api/sessions", json={"path": topic, "provider": "gemini"}).status_code == 400
    assert client.put("/api/claude/settings", json={"default_provider": "nope"}).status_code == 400
    assert client.put("/api/claude/settings", json={"default_provider": "cursor"}).status_code == 200
    s = client.post("/api/sessions", json={"path": topic, "message": "hi"}).json()
    assert s["provider"] == "cursor"
    wait_idle(client, s["id"])
    assert _calls(agents["tmp"] / "fu")


def test_providers_endpoint(client, agents):
    r = client.get("/api/claude/providers")
    assert r.status_code == 200
    by = {p["id"]: p for p in r.json()["providers"]}
    assert set(by) == {"claude", "codex", "cursor"}
    assert by["codex"]["installed"] and by["codex"]["signed_in"] is True
    assert by["cursor"]["installed"] and by["cursor"]["signed_in"] is True


def test_switching_provider_starts_a_new_thread_and_keeps_history(client, topic, agents):
    sid = client.post("/api/sessions", json={"path": topic, "message": "one"}).json()["id"]    # claude (fake)
    wait_idle(client, sid)
    assert client.patch(f"/api/sessions/{sid}", json={"provider": "codex"}).status_code == 200
    client.post(f"/api/sessions/{sid}/messages", json={"text": "two"})
    s = wait_idle(client, sid)
    assert s["provider"] == "codex" and s["error"] is None
    call = _calls(agents["tmp"] / "fc")[0]
    assert "resume" not in call["argv"]                                         # fresh Codex thread
    assert "codex says ok" in json.dumps(all_events(client, sid))


def test_provider_keys_and_test_endpoint(client, agents):
    assert client.post("/api/claude/providers/claude/key", json={"value": "x" * 20}).status_code == 404
    assert client.post("/api/claude/providers/codex/key", json={"value": "short"}).status_code == 400
    assert client.post("/api/claude/providers/codex/key", json={"value": "sk-test-1234567890"}).status_code == 200
    by = {p["id"]: p for p in client.get("/api/claude/providers").json()["providers"]}
    assert by["codex"]["key_set"] is True and by["cursor"]["key_set"] is False
    assert by["codex"]["install"] and by["cursor"]["login"] == "cursor-agent login"
    assert "sk-test-1234567890" not in json.dumps(by)                       # the key is never sent back
    t = client.post("/api/claude/providers/codex/test").json()
    assert t["ok"] is True and t["answer"] == "codex says ok"
    env_call = _calls(agents["tmp"] / "fc")[-1]
    assert "read-only" in env_call["argv"]
    assert client.post("/api/claude/providers/cursor/test").json()["ok"] is True
    assert client.delete("/api/claude/providers/codex/key").status_code == 200
    by = {p["id"]: p for p in client.get("/api/claude/providers").json()["providers"]}
    assert by["codex"]["key_set"] is False


def test_provider_key_reaches_the_turn_environment(mx):
    from maxxing import config
    from maxxing.sessions import spawn
    config.set_secret("openai_api_key", "sk-test-1234567890")
    config.set_secret("cursor_api_key", "key_abcdefghij")
    assert spawn.provider_env("codex") == {"OPENAI_API_KEY": "sk-test-1234567890", "CODEX_API_KEY": "sk-test-1234567890"}
    assert spawn.provider_env("cursor") == {"CURSOR_API_KEY": "key_abcdefghij"}
    assert spawn.provider_env("claude") == {}


def test_codex_limits_are_read_from_the_newest_rollout(tmp_path, monkeypatch):
    from maxxing import provider_usage
    day = tmp_path / "codex" / "sessions" / "2026" / "11" / "06"
    day.mkdir(parents=True)
    now = 1_800_000_000.0
    old = {"timestamp": "t", "payload": {"type": "token_count", "rate_limits": {
        "primary": {"used_percent": 99.0, "window_minutes": 300, "resets_at": now + 100}}}}
    new = {"timestamp": "t", "payload": {"type": "token_count", "rate_limits": {
        "plan_type": "plus",
        "primary": {"used_percent": 12.5, "window_minutes": 300, "resets_at": now + 3600},
        "secondary": {"used_percent": 40.0, "window_minutes": 10080, "resets_at": now - 5}}}}
    (day / "rollout-a.jsonl").write_text(json.dumps(old) + "\n")
    f = day / "rollout-b.jsonl"
    f.write_text("garbage\n" + json.dumps(new) + "\n" + json.dumps({"payload": {"type": "agent_message"}}) + "\n")
    import os
    os.utime(day / "rollout-a.jsonl", (now - 500, now - 500))
    os.utime(f, (now, now))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    lim = provider_usage.codex_limits(now)
    assert lim["five_hour"] == {"pct": 12.5, "resets_at": now + 3600}
    assert lim["seven_day"] == {"pct": 0.0, "resets_at": None}              # its reset time has passed
    assert lim["plan"] == "Plus"
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "nothing"))
    assert provider_usage.codex_limits(now) is None


def test_usage_endpoint_counts_tokens_by_agent(client, topic, agents, monkeypatch, tmp_path):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "no-codex"))
    for provider in ("codex", "cursor"):
        sid = client.post("/api/sessions", json={"path": topic, "message": "hi", "provider": provider}).json()["id"]
        wait_idle(client, sid)
    r = client.get("/api/usage/providers", params={"force": "true"})
    assert r.status_code == 200
    u = r.json()
    assert set(u) == {"codex", "cursor"}
    assert u["codex"]["available"] is False and u["cursor"]["available"] is False       # no plan limits readable
    assert u["codex"]["tokens"]["today"] == 145 and u["codex"]["tokens"]["week"] == 145     # 100 + 5 + 40
    assert u["cursor"]["tokens"]["today"] == 145
