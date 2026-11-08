"""Sub-agents: `maxxing agent …` and maxxing.sessions.agents (sessions that a session delegates)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from maxxing import cli
from maxxing.sessions import agents, service
from maxxing.sessions.service import SessionError

from conftest import wait_idle

GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "init.defaultBranch=main"]


def git(repo: Path, *args: str) -> str:
    return subprocess.run([*GIT, "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repo(mx, topic) -> Path:
    d = mx["ws"] / topic
    git(d, "init", "-q")
    (d / "a.txt").write_text("a\n")
    git(d, "add", "a.txt")
    git(d, "commit", "-qm", "first")
    return d


@pytest.fixture
def root(client, topic) -> dict:
    s = client.post("/api/sessions", json={"path": topic, "message": "lead"}).json()
    return wait_idle(client, s["id"])


def test_a_sub_agent_is_a_session_of_the_parents_topic(client, topic, root, mx):
    child = agents.spawn(root["id"], "do the thing")
    assert child["parent"] == root["id"] and child["path"] == topic and child["worktree"] == ""
    assert [s["id"] for s in agents.children(root["id"])] == [child["id"]]
    wait_idle(client, child["id"])
    assert agents.answer(child["id"]) == "Echo: do the thing"
    assert "assistant: Echo: do the thing" in agents.transcript(child["id"])
    # it shows in the API list like any session
    assert child["id"] in [s["id"] for s in client.get("/api/sessions", params={"path": topic}).json()]
    envs = [json.loads(x)["env"] for x in (mx["fake_dir"] / "calls.jsonl").read_text().splitlines()]
    assert root["id"] in [e.get("MAXXING_SESSION_ID") for e in envs]       # the turn knows its own id


def test_sub_agent_in_a_new_worktree_and_merge(client, topic, repo, root, mx):
    child = agents.spawn(root["id"], "add b", worktree="new:feat-b", agent=None)
    wt = child["worktree"]
    assert wt.endswith("/.worktrees/feat-b")
    wait_idle(client, child["id"])
    assert agents.diff(child["id"]) == ""                                   # nothing changed yet
    with pytest.raises(SessionError) as e:
        agents.merge(root["id"])
    assert e.value.code == "no_worktree"
    work = mx["ws"] / wt
    (work / "b.txt").write_text("b\n")
    with pytest.raises(SessionError) as e:
        agents.merge(child["id"])
    assert e.value.code == "dirty"
    git(work, "add", "b.txt")
    git(work, "commit", "-qm", "b")
    assert "b.txt" in agents.diff(child["id"])
    r = agents.merge(child["id"], delete=True)
    assert r == {"merged": "feat-b", "into": "main", "deleted": True, "path": wt}
    assert (repo / "b.txt").is_file() and not work.exists()
    assert "feat-b" not in git(repo, "branch", "--list")
    assert service.get_session(child["id"])["worktree"] == ""


def test_conflicting_merge_is_aborted(client, topic, repo, root, mx):
    child = agents.spawn(root["id"], "edit a", worktree="new:feat-a")
    wait_idle(client, child["id"])
    work = mx["ws"] / child["worktree"]
    (work / "a.txt").write_text("from the sub-agent\n")
    git(work, "commit", "-qam", "child")
    (repo / "a.txt").write_text("from main\n")
    git(repo, "commit", "-qam", "main")
    with pytest.raises(SessionError) as e:
        agents.merge(child["id"])
    assert e.value.code == "conflict"
    assert git(repo, "status", "--porcelain", "--untracked-files=no").strip() == ""   # aborted: nothing half-merged
    assert (repo / "a.txt").read_text() == "from main\n"


def test_existing_worktree_by_branch_name(client, topic, repo, root):
    first = agents.spawn(root["id"], "x", worktree="new:shared")
    again = agents.spawn(root["id"], "y", worktree="shared")
    assert again["worktree"] == first["worktree"]
    with pytest.raises(SessionError) as e:
        agents.spawn(root["id"], "z", worktree="nope")
    assert e.value.code == "bad_worktree"


def test_depth_and_fan_out_limits(client, topic, root, monkeypatch):
    a = agents.spawn(root["id"], "a")
    b = agents.spawn(a["id"], "b")
    assert agents.depth(b["id"]) == 2
    with pytest.raises(SessionError) as e:
        agents.spawn(b["id"], "c")
    assert e.value.code == "too_deep" and e.value.status == 429
    monkeypatch.setattr(agents, "MAX_ACTIVE", 1)
    monkeypatch.setattr(agents, "_active", lambda s: True)
    with pytest.raises(SessionError) as e:
        agents.spawn(root["id"], "d")
    assert e.value.code == "too_many"
    with pytest.raises(SessionError) as e:
        agents.spawn("nope", "e")
    assert e.value.code in ("bad_parent", "not_found")


def test_without_a_parent_a_topic_is_needed(client, topic):
    with pytest.raises(SessionError) as e:
        agents.spawn(None, "x")
    assert e.value.code == "bad_path"
    s = agents.spawn(None, "x", path=topic)
    assert s["parent"] == ""


def test_cli_spawn_wait_list(client, topic, root, monkeypatch, capsys):
    monkeypatch.setenv("MAXXING_SESSION_ID", root["id"])
    assert cli.main(["agent", "spawn", "say hi", "--wait", "--timeout", "30"]) == 0
    out = capsys.readouterr()
    assert "Echo: say hi" in out.out
    assert cli.main(["agent", "list"]) == 0
    assert "say hi" in capsys.readouterr().out
    kid = agents.children(root["id"])[0]["id"]
    assert cli.main(["agent", "read", kid[:8]]) == 0
    assert "user: say hi" in capsys.readouterr().out
    monkeypatch.delenv("MAXXING_SESSION_ID")
    assert cli.main(["agent", "list"]) == 1                                  # no session around: needs --all
