"""Sub-agents: sessions that a session delegates (`maxxing agent …`, see cmd_agent.py).

A delegated session is an ordinary session (it shows in the web list like one made by hand) with meta `parent` = the
session that created it. A turn's environment carries MAXXING_SESSION_ID, which `spawn` reads as the parent.
Limits keep a runaway agent from fanning out: a session at depth MAX_DEPTH cannot delegate, and a session has at most
MAX_ACTIVE delegated sessions working at once.
"""
from __future__ import annotations

import time

from .. import worktrees
from . import service, store
from .service import SessionError

MAX_DEPTH = 2        # root = 0: a root and its children may delegate, their own children may not
MAX_ACTIVE = 4
POLL_S = 1.0


def parent_of(sid: str) -> str:
    return str((store.read(sid) or {}).get("parent") or "")


def depth(sid: str) -> int:
    n, seen = 0, {sid}
    p = parent_of(sid)
    while p and p not in seen and n < 10:
        seen.add(p)
        n += 1
        p = parent_of(p)
    return n


def children(sid: str) -> list[dict]:
    return [s for s in service.list_sessions(None, None) if s.get("parent") == sid]


def _active(s: dict) -> bool:
    return s["state"] == "running" or bool(s["queue"])


def check_parent(parent: str) -> None:
    if not store.is_valid_id(parent) or store.read(parent) is None:
        raise SessionError(404, "bad_parent", f"Parent session not found: {parent!r}")
    if depth(parent) >= MAX_DEPTH:
        raise SessionError(429, "too_deep", f"Sub-agents may not delegate more than {MAX_DEPTH} levels deep")
    if sum(1 for c in children(parent) if _active(c)) >= MAX_ACTIVE:
        raise SessionError(429, "too_many", f"{MAX_ACTIVE} sub-agents are already working: wait for one to finish")


def worktree_args(path: str, spec: str | None) -> dict:
    """`--worktree` -> create_session kwargs: `new:BRANCH[@BASE]`, or an existing worktree by path, folder or branch."""
    spec = (spec or "").strip()
    if not spec:
        return {}
    try:
        if spec.startswith("new:"):
            branch, _, base = spec[4:].partition("@")
            return {"new_worktree": {"branch": branch, "base": base}}
        for w in worktrees.listing(path):
            if spec in (w["path"], w["name"], w["branch"]):
                return {"worktree": w["path"]}
    except worktrees.WorktreeError as e:
        raise SessionError(e.status, e.code, e.message) from None
    raise SessionError(400, "bad_worktree", f"No worktree {spec!r} in this topic (use new:BRANCH to make one)")


def spawn(parent: str | None, prompt: str, *, path: str | None = None, agent: str | None = None,
          model: str | None = None, title: str | None = None, worktree: str | None = None,
          plan: bool = False) -> dict:
    if not (prompt or "").strip():
        raise SessionError(400, "empty_prompt", "Give the sub-agent a task")
    if path is None:
        if not parent:
            raise SessionError(400, "bad_path", "Give --path (the topic), or run this from inside a session")
        path = (store.read(parent) or {}).get("path") or ""
    return service.create_session(path, message=prompt, title=title, model=model, provider=agent, plan_mode=plan,
                                  parent=parent or None, **worktree_args(path, worktree))


def finished(s: dict | None) -> bool:
    return s is not None and s["state"] != "running" and not s["queue"]


def wait(sid: str, timeout: float | None = None) -> dict:
    """The session once its turn (and queue) is over; TimeoutError after `timeout` seconds."""
    end = time.monotonic() + timeout if timeout else None
    while True:
        s = service.get_session(sid)
        if s is None:
            raise SessionError(404, "not_found", "Session not found")
        if finished(s):
            return s
        if end is not None and time.monotonic() >= end:
            raise TimeoutError(sid)
        time.sleep(POLL_S)


def answer(sid: str) -> str:
    """The last thing the agent said in its latest turn."""
    for e in reversed(service._tail_events(sid)):
        if e["type"] == "assistant" and (e.get("text") or "").strip():
            return e["text"].strip()
        if e["type"] == "user":
            break
    return ""


def transcript(sid: str, tail: int = 20) -> list[str]:
    """The last `tail` exchanges as plain lines: `user: …`, `assistant: …`, `tool: …`, `note: …`."""
    lines = []
    for e in service._tail_events(sid):
        t = e["type"]
        if t in ("user", "assistant"):
            lines.append(f"{t}: {(e.get('text') or '').strip()}")
        elif t == "tool_use":
            lines.append(f"tool: {e.get('summary') or e.get('name')}")
        elif t == "note" and e.get("level") != "info":
            lines.append(f"note: {e.get('text')}")
    return lines[-tail:]


def _worktree_of(sid: str) -> tuple[str, str]:
    m = store.read(sid)
    if m is None:
        raise SessionError(404, "not_found", "Session not found")
    if not m.get("worktree"):
        raise SessionError(400, "no_worktree", "This session does not run in a worktree")
    return m.get("path") or "", m["worktree"]


def diff(sid: str) -> str:
    path, wt = _worktree_of(sid)
    try:
        return worktrees.diff(path, wt)
    except worktrees.WorktreeError as e:
        raise SessionError(e.status, e.code, e.message) from None


def merge(sid: str, delete: bool = False) -> dict:
    """Merge the session's worktree branch into the base branch; with `delete` remove the worktree and put the
    session back in the topic folder. Refused while the session works."""
    path, wt = _worktree_of(sid)
    s = service.get_session(sid)
    if s is not None and not finished(s):
        raise SessionError(409, "busy", "The sub-agent is still working")
    try:
        r = worktrees.merge(path, wt, delete)
    except worktrees.WorktreeError as e:
        raise SessionError(e.status, e.code, e.message) from None
    if delete:
        with store.edit(sid) as m:
            m["worktree"] = ""
        service.bus.invalidate("sessions")
    return r
