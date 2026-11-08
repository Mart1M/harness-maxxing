"""Worktrees of a topic: the new-session picker (GET /api/worktrees, worktree / new_worktree on POST /api/sessions)."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

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


def listing(client, topic) -> list[dict]:
    r = client.get("/api/worktrees", params={"path": topic})
    assert r.status_code == 200, r.text
    return r.json()


def test_topic_without_repository_has_no_worktree(client, topic):
    assert listing(client, topic) == []
    r = client.post("/api/sessions", json={"path": topic, "new_worktree": {"branch": "feat"}})
    assert r.status_code == 404 and r.json()["error"] == "no_repo"


def test_listing_shows_the_main_working_tree(client, topic, repo):
    (w,) = listing(client, topic)
    assert w["main"] is True and w["path"] == topic and w["branch"] == "main" and w["repo"] == topic


def test_new_session_in_a_new_worktree(client, topic, repo, mx):
    r = client.post("/api/sessions", json={"path": topic, "message": "hi", "new_worktree": {"branch": "feat/login"}})
    assert r.status_code == 200, r.text
    s = r.json()
    wt = f"{topic}/.worktrees/feat-login"
    assert s["worktree"] == wt and s["path"] == topic
    assert (mx["ws"] / wt / "a.txt").is_file() and git(repo, "branch", "--list", "feat/login").strip()
    assert ".worktrees" not in git(repo, "status", "--porcelain")      # excluded: never shown as untracked
    wait_idle(client, s["id"])
    cwd = (mx["fake_dir"] / "calls.jsonl").read_text().splitlines()[-1]
    assert str((mx["ws"] / wt).resolve()) in cwd or str(mx["ws"] / wt) in cwd
    names = {w["path"]: w for w in listing(client, topic)}
    assert names[wt]["branch"] == "feat/login" and names[wt]["main"] is False and names[topic]["main"] is True


def test_new_session_in_an_existing_worktree(client, topic, repo):
    first = client.post("/api/sessions", json={"path": topic, "new_worktree": {"branch": "fix"}}).json()
    wt = first["worktree"]
    again = client.post("/api/sessions", json={"path": topic, "worktree": wt})
    assert again.status_code == 200 and again.json()["worktree"] == wt
    plain = client.post("/api/sessions", json={"path": topic}).json()
    assert plain["worktree"] == ""


def test_existing_branch_is_checked_out_and_taken_branch_refused(client, topic, repo):
    git(repo, "branch", "old")
    r = client.post("/api/sessions", json={"path": topic, "new_worktree": {"branch": "old"}})
    assert r.status_code == 200 and r.json()["worktree"].endswith("/.worktrees/old")
    r = client.post("/api/sessions", json={"path": topic, "new_worktree": {"branch": "main"}})
    assert r.status_code == 409                                         # `main` is checked out in the topic folder


@pytest.mark.parametrize("branch", ["-x", "a..b", "a b", "x.lock", "", "/abs", "a//b"])
def test_bad_branch_name(client, topic, repo, branch):
    r = client.post("/api/sessions", json={"path": topic, "new_worktree": {"branch": branch}})
    assert r.status_code in (400, 422), r.text


def test_worktree_must_belong_to_the_topic(client, topic, repo, mx):
    for bad in ("projects/acme/topics/blog/../../..", "projects", f"{topic}/a.txt", "/etc"):
        r = client.post("/api/sessions", json={"path": topic, "worktree": bad})
        assert r.status_code == 400 and r.json()["error"] == "bad_worktree"


def test_moving_a_session_leaves_its_worktree(client, topic, repo):
    client.post("/api/workspace/projects/acme/topics", json={"name": "other"})
    s = client.post("/api/sessions", json={"path": topic, "new_worktree": {"branch": "mv"}}).json()
    r = client.patch(f"/api/sessions/{s['id']}", json={"path": "projects/acme/topics/other"})
    assert r.status_code == 200 and r.json()["worktree"] == "" and r.json()["path"].endswith("/other")
